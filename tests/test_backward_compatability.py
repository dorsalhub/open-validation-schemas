import copy
import json
import tomllib
from pathlib import Path
from typing import NamedTuple

import jsonschema_rs
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis.errors import InvalidArgument, Unsatisfiable
from hypothesis_jsonschema import from_schema
from packaging.version import Version

ROOT_DIR = Path(__file__).parent.parent
REFERENCE_DIR = ROOT_DIR / "reference" / "schemas"
WORKING_DIR = ROOT_DIR / "schemas"
PACKAGE_VERSION = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text())["project"][
    "version"
]

METADATA_KEYS = ("version", "description", "title", "x-license", "$id")
UPPER_BOUNDS = ("maxLength", "maxItems", "maxProperties", "maxContains")
LOWER_BOUNDS = ("minLength", "minItems", "minProperties", "minContains")
JSON_TYPES = {
    "string": str,
    "boolean": bool,
    "null": type(None),
    "array": list,
    "object": dict,
}
OPAQUE_KEYWORDS = (
    "pattern",
    "format",
    "multipleOf",
    "contentEncoding",
    "contentMediaType",
)
FUZZ_EXAMPLES = 50
STABLE_FROM = Version("1.0.0")


class Violation(NamedTuple):
    path: str
    rule: str
    message: str


def latest_reference_dir() -> Path | None:
    """Return the latest stable release; releases before 1.0.0 carry no compatibility promise."""
    versions = (
        [
            d
            for d in REFERENCE_DIR.iterdir()
            if d.is_dir() and Version(d.name) >= STABLE_FROM
        ]
        if REFERENCE_DIR.exists()
        else []
    )
    return max(versions, key=lambda d: Version(d.name)) if versions else None


def dereference(schema: dict) -> dict:
    """Inline every internal '#/$defs/...' reference so that changes behind a $ref are compared too."""
    defs = schema.get("$defs", {})

    def resolve(node, depth=0):
        if depth > 64:
            raise RecursionError("Schema references nest too deeply to compare.")
        if isinstance(node, list):
            return [resolve(n, depth) for n in node]
        if not isinstance(node, dict):
            return node
        if isinstance(node.get("$ref"), str) and node["$ref"].startswith("#/$defs/"):
            target = defs[node["$ref"].removeprefix("#/$defs/")]
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            return resolve({**target, **siblings}, depth + 1)
        resolved = {k: resolve(v, depth) for k, v in node.items() if k != "$defs"}
        if isinstance(resolved.get("type"), list):
            rest = {
                k: v
                for k, v in resolved.items()
                if k not in ("type", "description", "title")
            }
            resolved = {
                k: v for k, v in resolved.items() if k in ("description", "title")
            }
            resolved["anyOf"] = [{"type": t, **rest} for t in node["type"]]
        return resolved

    return resolve(schema)


def value_has_type(value, json_type: str) -> bool:
    if json_type in ("number", "integer"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        return json_type == "number" or float(value).is_integer()
    return isinstance(value, JSON_TYPES[json_type])


def implied_values(node: dict) -> list | None:
    if "const" in node:
        return [node["const"]]
    return node.get("enum")


def numeric_bound(
    node: dict, inclusive: str, exclusive: str
) -> tuple[float, bool] | None:
    candidates = []
    if inclusive in node:
        candidates.append((node[inclusive], False))
    if exclusive in node:
        candidates.append((node[exclusive], True))
    if not candidates:
        return None
    if inclusive == "minimum":
        return max(candidates, key=lambda c: (c[0], c[1]))
    return min(candidates, key=lambda c: (c[0], not c[1]))


def lower_tightened(
    old: tuple[float, bool] | None, new: tuple[float, bool] | None
) -> bool:
    if new is None:
        return False
    if old is None:
        return True
    return new[0] > old[0] or (new[0] == old[0] and new[1] and not old[1])


def upper_tightened(
    old: tuple[float, bool] | None, new: tuple[float, bool] | None
) -> bool:
    if new is None:
        return False
    if old is None:
        return True
    return new[0] < old[0] or (new[0] == old[0] and new[1] and not old[1])


def condition_narrowed(old_if, new_if) -> bool:
    """True if `new_if` matches a subset of what `old_if` matched, by only adding required fields."""
    if not isinstance(old_if, dict) or not isinstance(new_if, dict):
        return False
    old_rest = {k: v for k, v in old_if.items() if k != "required"}
    new_rest = {k: v for k, v in new_if.items() if k != "required"}
    return old_rest == new_rest and set(old_if.get("required", [])) <= set(
        new_if.get("required", [])
    )


def pair_branches(
    old_branches: list, new_branches: list
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Pair titled branches by title, and untitled branches by their order among untitled branches."""

    def title(branch):
        return branch.get("title") if isinstance(branch, dict) else None

    old_titled = {
        title(b): i for i, b in enumerate(old_branches) if title(b) is not None
    }
    pairs = [
        (old_titled[title(b)], j)
        for j, b in enumerate(new_branches)
        if title(b) in old_titled
    ]
    old_untitled = [i for i, b in enumerate(old_branches) if title(b) is None]
    new_untitled = [j for j, b in enumerate(new_branches) if title(b) is None]
    pairs.extend(zip(old_untitled, new_untitled))
    unmatched_old = sorted(set(range(len(old_branches))) - {i for i, _ in pairs})
    unmatched_new = sorted(set(range(len(new_branches))) - {j for _, j in pairs})
    return pairs, unmatched_old, unmatched_new


def types_of(node: dict) -> set[str] | None:
    t = node.get("type")
    if t is None:
        return None
    return set(t) if isinstance(t, list) else {t}


def compatibility_violations(old: dict, new: dict, path: str = "#") -> list[Violation]:
    """List every way `new` may reject data that `old` accepted. Deliberately conservative."""
    found: list[Violation] = []

    def flag(rule: str, message: str, at: str = path):
        found.append(Violation(at, rule, message))

    if not isinstance(old, dict) or not isinstance(new, dict):
        if old is not new and new is False:
            flag("schema-closed", "Subschema changed to 'false'.")
        return found

    old_types, new_types = types_of(old), types_of(new)
    if new_types is not None:
        values = implied_values(old)
        if old_types is None and values is not None:
            if not all(any(value_has_type(v, t) for t in new_types) for v in values):
                flag(
                    "type-added",
                    f"Type constraint {sorted(new_types)} excludes enumerated values.",
                )
        elif old_types is None:
            flag("type-added", f"Type constraint {sorted(new_types)} added.")
        else:
            for t in old_types:
                if t not in new_types and not (
                    t == "integer" and "number" in new_types
                ):
                    flag("type-removed", f"Type '{t}' removed.")

    if lower_tightened(
        numeric_bound(old, "minimum", "exclusiveMinimum"),
        numeric_bound(new, "minimum", "exclusiveMinimum"),
    ):
        flag("bound-tightened", "Numeric lower bound added or tightened.")
    if upper_tightened(
        numeric_bound(old, "maximum", "exclusiveMaximum"),
        numeric_bound(new, "maximum", "exclusiveMaximum"),
    ):
        flag("bound-tightened", "Numeric upper bound added or tightened.")

    for bound in UPPER_BOUNDS:
        if bound in new:
            if bound not in old:
                flag("bound-added", f"{bound} {new[bound]} added.")
            elif new[bound] < old[bound]:
                flag(
                    "bound-tightened",
                    f"{bound} tightened ({old[bound]} -> {new[bound]}).",
                )
    for bound in LOWER_BOUNDS:
        if bound in new:
            if bound not in old:
                flag("bound-added", f"{bound} {new[bound]} added.")
            elif new[bound] > old[bound]:
                flag(
                    "bound-tightened",
                    f"{bound} tightened ({old[bound]} -> {new[bound]}).",
                )

    if "enum" in new:
        if "enum" not in old:
            flag("enum-added", "Enum constraint added.")
        else:
            for value in old["enum"]:
                if value not in new["enum"]:
                    flag("enum-removed", f"Enum value {value!r} removed.")
    if "const" in new and old.get("const", object()) != new["const"]:
        flag("const-changed", f"Const {new['const']!r} added or changed.")

    for keyword in OPAQUE_KEYWORDS:
        if keyword in new and old.get(keyword) != new[keyword]:
            flag(
                f"{keyword}-changed",
                f"{keyword} added or changed ({old.get(keyword)!r} -> {new[keyword]!r}).",
            )
    if new.get("uniqueItems") and not old.get("uniqueItems"):
        flag("uniqueItems-added", "uniqueItems added.")

    added_required = set(new.get("required", [])) - set(old.get("required", []))
    if added_required:
        flag("required-added", f"Required fields added: {sorted(added_required)}.")
    for key, fields in new.get("dependentRequired", {}).items():
        added = set(fields) - set(old.get("dependentRequired", {}).get(key, []))
        if added:
            flag(
                "dependentRequired-added",
                f"Dependent requirements added for '{key}': {sorted(added)}.",
            )

    old_props, new_props = old.get("properties", {}), new.get("properties", {})
    old_additional = old.get("additionalProperties", True)
    for key, old_prop in old_props.items():
        if key not in new_props:
            if new.get("additionalProperties", True) is not True:
                flag(
                    "property-removed",
                    f"Property '{key}' removed.",
                    f"{path}/properties/{key}",
                )
            continue
        found.extend(
            compatibility_violations(
                old_prop, new_props[key], f"{path}/properties/{key}"
            )
        )
    for key in new_props.keys() - old_props.keys():
        if old_additional is not False:
            flag(
                "property-constrains-open-key",
                f"New property '{key}' constrains a previously open key.",
                f"{path}/properties/{key}",
            )

    new_additional = new.get("additionalProperties", True)
    if old_additional is not False and new_additional is not True:
        if old_additional is True:
            flag(
                "additionalProperties-added",
                "additionalProperties constraint added.",
                f"{path}/additionalProperties",
            )
        else:
            found.extend(
                compatibility_violations(
                    old_additional, new_additional, f"{path}/additionalProperties"
                )
            )

    for keyword in ("items", "propertyNames", "contains", "not"):
        if keyword in new:
            if keyword not in old:
                flag(
                    f"{keyword}-added",
                    f"'{keyword}' constraint added.",
                    f"{path}/{keyword}",
                )
            elif keyword == "not":
                if old["not"] != new["not"]:
                    flag("not-changed", "'not' constraint changed.", f"{path}/not")
            else:
                found.extend(
                    compatibility_violations(
                        old[keyword], new[keyword], f"{path}/{keyword}"
                    )
                )

    old_prefix, new_prefix = old.get("prefixItems", []), new.get("prefixItems", [])
    for i, sub in enumerate(new_prefix):
        if i < len(old_prefix):
            found.extend(
                compatibility_violations(old_prefix[i], sub, f"{path}/prefixItems/{i}")
            )
        else:
            flag(
                "prefixItems-added",
                f"prefixItems[{i}] added.",
                f"{path}/prefixItems/{i}",
            )

    for keyword in ("anyOf", "oneOf"):
        old_branches, new_branches = old.get(keyword), new.get(keyword)
        if new_branches is None:
            continue
        if old_branches is None:
            flag(
                f"{keyword}-added",
                f"'{keyword}' constraint added.",
                f"{path}/{keyword}",
            )
            continue
        pairs, unmatched_old, unmatched_new = pair_branches(old_branches, new_branches)
        for i in unmatched_old:
            flag(
                f"{keyword}-branch-removed",
                f"{keyword} branch {i} has no counterpart.",
                f"{path}/{keyword}/{i}",
            )
        if keyword == "oneOf":
            for j in unmatched_new:
                flag(
                    "oneOf-branch-added",
                    "A new oneOf branch may overlap an existing one.",
                    f"{path}/oneOf/{j}",
                )
        for i, j in pairs:
            found.extend(
                compatibility_violations(
                    old_branches[i], new_branches[j], f"{path}/{keyword}/{j}"
                )
            )

    old_all, new_all = old.get("allOf", []), new.get("allOf", [])
    for j, entry in enumerate(new_all):
        at = f"{path}/allOf/{j}"
        if entry in old_all:
            continue
        if "if" in entry:
            match = next(
                (
                    o
                    for o in old_all
                    if "if" in o and condition_narrowed(o["if"], entry["if"])
                ),
                None,
            )
            if match is None or "else" in entry:
                flag("allOf-added", "Conditional allOf entry added or changed.", at)
                continue
            if "then" in entry:
                found.extend(
                    compatibility_violations(
                        match.get("then", {}), entry["then"], f"{at}/then"
                    )
                )
        elif j < len(old_all) and "if" not in old_all[j]:
            found.extend(compatibility_violations(old_all[j], entry, at))
        else:
            flag("allOf-added", "allOf entry added.", at)

    if "if" in new and (
        "else" in new or not condition_narrowed(old.get("if"), new["if"])
    ):
        flag("conditional-changed", "Conditional 'if' added or changed.")
    elif "if" in new:
        for branch in ("then", "else"):
            if branch in new:
                found.extend(
                    compatibility_violations(
                        old.get(branch, {}), new[branch], f"{path}/{branch}"
                    )
                )

    return found


def functional_core(schema: dict) -> dict:
    core = copy.deepcopy(schema)
    for key in METADATA_KEYS:
        core.pop(key, None)
    return core


def get_schema_pairs():
    latest = latest_reference_dir()
    if not latest:
        return []
    pairs = []
    for working_file in sorted(WORKING_DIR.glob("*.json")):
        ref_file = latest / working_file.name
        if ref_file.exists():
            pairs.append(
                pytest.param(
                    working_file.stem,
                    latest.name,
                    json.loads(ref_file.read_text()),
                    json.loads(working_file.read_text()),
                    id=working_file.stem,
                )
            )
    return pairs


SCHEMA_PAIRS = get_schema_pairs()


def test_no_schema_was_removed():
    latest = latest_reference_dir()
    if not latest:
        pytest.skip("No reference release to compare against.")
    removed = {p.name for p in latest.glob("*.json")} - {
        p.name for p in WORKING_DIR.glob("*.json")
    }
    assert not removed, f"Schemas removed since {latest.name}: {sorted(removed)}"


@pytest.mark.parametrize("schema_name, v_old, old_schema, new_schema", SCHEMA_PAIRS)
class TestBackwardCompatibility:
    def test_no_breaking_changes(self, schema_name, v_old, old_schema, new_schema):
        """No change may reject data that the latest stable release accepted."""
        violations = compatibility_violations(
            dereference(old_schema), dereference(new_schema)
        )
        if violations:
            pytest.fail(
                f"[{schema_name}] {len(violations)} breaking change(s) since {v_old}:\n"
                + "\n".join(f"  {v.path} [{v.rule}] {v.message}" for v in violations)
            )

    def test_hypothesis_fuzzing(self, schema_name, v_old, old_schema, new_schema):
        """Generates valid payloads from the historical schema, and validates against the new schema."""
        if functional_core(old_schema) == functional_core(new_schema):
            pytest.skip(f"{schema_name} is unchanged from {v_old}.")

        validator_old = jsonschema_rs.Draft202012Validator(
            old_schema, validate_formats=True
        )
        validator_new = jsonschema_rs.Draft202012Validator(
            new_schema, validate_formats=True
        )

        @given(old_data=from_schema(old_schema))
        @settings(
            max_examples=FUZZ_EXAMPLES,
            deadline=None,
            suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        )
        def run_fuzzer(old_data):
            assume(validator_old.is_valid(old_data))
            try:
                validator_new.validate(old_data)
            except jsonschema_rs.ValidationError as e:
                pytest.fail(
                    f"[{schema_name} {v_old}->{PACKAGE_VERSION}] Backward compatibility broken!\n"
                    f"Valid {v_old} data failed on {PACKAGE_VERSION} schema.\n"
                    f"Data: {json.dumps(old_data, indent=2)}\nError: {e}"
                )

        try:
            run_fuzzer()
        except (Unsatisfiable, InvalidArgument) as e:
            pytest.skip(
                f"hypothesis-jsonschema cannot generate data for {schema_name} {v_old}: {e}"
            )


BASE = {
    "type": "object",
    "properties": {
        "n": {"type": "integer", "minimum": 0, "maximum": 10},
        "s": {"type": "string", "maxLength": 10},
        "attrs": {
            "type": "object",
            "maxProperties": 4,
            "additionalProperties": {
                "anyOf": [{"type": "string", "maxLength": 8}, {"type": "number"}]
            },
        },
        "geo": {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/point"}]},
    },
    "required": ["n"],
    "$defs": {
        "point": {
            "type": "object",
            "properties": {"x": {"type": "number"}},
            "additionalProperties": False,
        }
    },
    "additionalProperties": False,
}


def mutated(fn):
    schema = copy.deepcopy(BASE)
    fn(schema)
    return schema


@pytest.mark.parametrize(
    "description, new",
    [
        (
            "tightened value maxLength inside anyOf",
            mutated(
                lambda s: s["properties"]["attrs"]["additionalProperties"]["anyOf"][
                    0
                ].update(maxLength=4)
            ),
        ),
        (
            "removed anyOf branch",
            mutated(
                lambda s: s["properties"]["attrs"]["additionalProperties"][
                    "anyOf"
                ].pop()
            ),
        ),
        ("added pattern", mutated(lambda s: s["properties"]["s"].update(pattern="^a"))),
        (
            "added format",
            mutated(lambda s: s["properties"]["s"].update(format="email")),
        ),
        (
            "added exclusiveMaximum",
            mutated(lambda s: s["properties"]["n"].update(exclusiveMaximum=5)),
        ),
        (
            "added propertyNames",
            mutated(
                lambda s: s["properties"]["attrs"].update(
                    propertyNames={"maxLength": 2}
                )
            ),
        ),
        (
            "tightened bound behind $ref",
            mutated(lambda s: s["$defs"]["point"]["properties"]["x"].update(minimum=0)),
        ),
        ("added required field", mutated(lambda s: s["required"].append("s"))),
        (
            "added allOf conditional",
            mutated(
                lambda s: s.update(
                    allOf=[{"if": {"required": ["s"]}, "then": {"required": ["attrs"]}}]
                )
            ),
        ),
        (
            "narrowed number to integer",
            mutated(lambda s: s["properties"]["s"].update(type="integer")),
        ),
    ],
)
def test_compatibility_checker_detects(description, new):
    assert compatibility_violations(dereference(BASE), dereference(new)), (
        f"Checker missed: {description}"
    )


@pytest.mark.parametrize(
    "description, new",
    [
        (
            "widened integer to number",
            mutated(lambda s: s["properties"]["n"].update(type="number")),
        ),
        (
            "loosened maximum",
            mutated(lambda s: s["properties"]["n"].update(maximum=100)),
        ),
        (
            "added optional property to closed object",
            mutated(lambda s: s["properties"].update(extra={"type": "number"})),
        ),
        (
            "added anyOf branch",
            mutated(
                lambda s: s["properties"]["attrs"]["additionalProperties"][
                    "anyOf"
                ].append({"type": "boolean"})
            ),
        ),
        ("removed required field", mutated(lambda s: s.update(required=[]))),
    ],
)
def test_compatibility_checker_allows(description, new):
    assert compatibility_violations(dereference(BASE), dereference(new)) == [], (
        f"Checker flagged a loosening: {description}"
    )
