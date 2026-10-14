import json
import tomllib
from collections.abc import Iterator
from pathlib import Path

import jsonschema_rs
import pytest

REPO_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
PYPROJECT = REPO_ROOT / "pyproject.toml"

PACKAGE_VERSION = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
ID_PREFIX = "https://dorsalhub.com/schemas/open/"
ROOT_KEY_ORDER = ["x-license", "$schema", "$id", "title", "version", "description"]
OPEN_SCHEMAS = {"geolocation.json"}
SHARED_GEOMETRY_SCHEMAS = [
    "document-extraction.json",
    "entity-extraction.json",
    "object-detection.json",
]
SHARED_GEOMETRY_DEFS = ["point", "box", "polygon", "multi_polygon"]
FORBIDDEN_KEYWORDS = {
    "default",
    "$dynamicRef",
    "$dynamicAnchor",
    "$recursiveRef",
    "$recursiveAnchor",
}
SCORE_RANGES = {(0, 1), (-1, 1)}

MAP_KEYWORDS = ("properties", "patternProperties", "$defs", "dependentSchemas")
SINGLE_KEYWORDS = (
    "items",
    "additionalProperties",
    "propertyNames",
    "contains",
    "unevaluatedItems",
    "unevaluatedProperties",
)
LIST_KEYWORDS = ("allOf", "anyOf", "oneOf", "prefixItems")
CONDITIONAL_KEYWORDS = ("if", "then", "else", "not")


def load_schemas() -> dict[str, dict]:
    return {
        p.name: json.loads(p.read_text()) for p in sorted(SCHEMAS_DIR.glob("*.json"))
    }


SCHEMAS = load_schemas()


def walk(
    node, path: str = "#", overlay: bool = False
) -> Iterator[tuple[str, dict, bool]]:
    """Yield (path, subschema, overlay) for every subschema; overlay marks partial schemas under if/then/else/not."""
    if not isinstance(node, dict):
        return
    yield path, node, overlay
    for key in MAP_KEYWORDS:
        for name, sub in node.get(key, {}).items():
            yield from walk(sub, f"{path}/{key}/{name}", overlay)
    for key in SINGLE_KEYWORDS:
        if isinstance(node.get(key), dict):
            yield from walk(node[key], f"{path}/{key}", overlay)
    for key in LIST_KEYWORDS:
        for i, sub in enumerate(node.get(key, [])):
            yield from walk(sub, f"{path}/{key}/{i}", overlay)
    for key in CONDITIONAL_KEYWORDS:
        if isinstance(node.get(key), dict):
            yield from walk(node[key], f"{path}/{key}", True)


def types_of(node: dict) -> list[str]:
    t = node.get("type")
    if t is None:
        return []
    return t if isinstance(t, list) else [t]


def style_violations(filename: str, schema: dict) -> list[str]:
    errors = []
    defs = schema.get("$defs", {})
    for path, node, overlay in walk(schema):
        types = types_of(node)

        for keyword in FORBIDDEN_KEYWORDS & node.keys():
            errors.append(f"{path}: The keyword '{keyword}' is forbidden.")

        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/$defs/"):
                errors.append(f"{path}: $ref '{ref}' must point to '#/$defs/...'.")
            elif ref.removeprefix("#/$defs/") not in defs:
                errors.append(f"{path}: $ref '{ref}' does not resolve.")

        if isinstance(node.get("type"), list):
            errors.append(f"{path}: Use 'anyOf' instead of a list of types.")

        if overlay:
            continue

        if "properties" in node and "object" not in types:
            errors.append(
                f"{path}: Objects with 'properties' must declare 'type': 'object'."
            )

        if (
            "string" in types
            and "enum" not in node
            and "const" not in node
            and "maxLength" not in node
        ):
            errors.append(
                f"{path}: String must have 'maxLength' (even if format is set)."
            )

        if "array" in types and "maxItems" not in node:
            errors.append(f"{path}: Array must have 'maxItems'.")

        if "object" in types:
            closed = node.get("additionalProperties") is False
            if "properties" in node and not closed and filename not in OPEN_SCHEMAS:
                errors.append(f"{path}: Object must set 'additionalProperties': false.")
            if not closed:
                if "maxProperties" not in node:
                    errors.append(f"{path}: Open object must have 'maxProperties'.")
                if "maxLength" not in node.get("propertyNames", {}):
                    errors.append(
                        f"{path}: Open object must bound key length with 'propertyNames.maxLength'."
                    )
            if "patternProperties" in node:
                errors.append(
                    f"{path}: 'patternProperties' is not allowed; use 'propertyNames'."
                )

        name = path.rsplit("/", 1)[-1]
        if (
            path.endswith("/properties/language")
            and node.get("pattern") != "^[a-z]{3}$"
        ):
            errors.append(
                f"{path}: 'language' must be an ISO 639-3 code (pattern '^[a-z]{{3}}$')."
            )
        if name == "score" and path.rsplit("/", 2)[-2] == "properties":
            bounds = (node.get("minimum"), node.get("maximum"))
            if bounds not in SCORE_RANGES:
                errors.append(
                    f"{path}: 'score' must range over [0, 1] or [-1, 1], not {bounds}."
                )
            elif bounds == (-1, 1) and "score_explanation" not in schema.get(
                "properties", {}
            ):
                errors.append(
                    f"{path}: Bipolar scores require a root 'score_explanation' field."
                )

    errors.extend(recursion_violations(schema))
    return errors


def refs_in(node) -> set[str]:
    if isinstance(node, dict):
        found = {node["$ref"]} if isinstance(node.get("$ref"), str) else set()
        return found.union(*(refs_in(v) for v in node.values()))
    if isinstance(node, list):
        return set().union(*(refs_in(v) for v in node))
    return set()


def recursion_violations(schema: dict) -> list[str]:
    if "#" in refs_in(schema):
        return ["#: Self-reference '#' allows unbounded nesting."]
    graph = {
        name: {
            r.removeprefix("#/$defs/") for r in refs_in(sub) if r.startswith("#/$defs/")
        }
        for name, sub in schema.get("$defs", {}).items()
    }

    def reachable(start: str) -> set[str]:
        seen: set[str] = set()
        stack = list(graph.get(start, ()))
        while stack:
            current = stack.pop()
            if current not in seen:
                seen.add(current)
                stack.extend(graph.get(current, ()))
        return seen

    return [
        f"#/$defs/{name}: Recursive definition allows unbounded nesting."
        for name in graph
        if name in reachable(name)
    ]


@pytest.mark.parametrize("filename, schema", SCHEMAS.items())
def test_schema_is_valid_json_schema(filename, schema):
    try:
        jsonschema_rs.meta.validate(schema)
    except jsonschema_rs.ValidationError as e:
        pytest.fail(f"Schema '{filename}' is invalid JSON Schema: {e}")


@pytest.mark.parametrize("filename, schema", SCHEMAS.items())
def test_schema_adheres_to_style_guide(filename, schema):
    """Enforces the 'Strict by Default' policy from STYLEGUIDE.md."""
    errors = style_violations(filename, schema)
    if errors:
        pytest.fail(f"Schema '{filename}' violates Style Guide:\n" + "\n".join(errors))


@pytest.mark.parametrize("filename, schema", SCHEMAS.items())
def test_schema_metadata(filename, schema):
    assert schema.get("version") == PACKAGE_VERSION, (
        f"{filename}: version must match pyproject.toml ({PACKAGE_VERSION})"
    )
    assert schema.get("$id") == ID_PREFIX + Path(filename).stem, (
        f"{filename}: unexpected $id {schema.get('$id')!r}"
    )
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", (
        f"{filename}: must declare draft 2020-12"
    )


@pytest.mark.parametrize("filename, schema", SCHEMAS.items())
def test_schema_key_order(filename, schema):
    errors = []
    if list(schema)[: len(ROOT_KEY_ORDER)] != ROOT_KEY_ORDER:
        errors.append(f"#: Root keys must start with {ROOT_KEY_ORDER}.")
    for path, node, _ in walk(schema):
        keys = list(node)
        if "additionalProperties" in keys and keys[-1] != "additionalProperties":
            errors.append(f"{path}: 'additionalProperties' must be the last key.")
    if errors:
        pytest.fail(f"Schema '{filename}' has misplaced keys:\n" + "\n".join(errors))


@pytest.mark.parametrize("definition", SHARED_GEOMETRY_DEFS)
def test_shared_geometry_definitions_are_identical(definition):
    variants = {
        name: SCHEMAS[name].get("$defs", {}).get(definition)
        for name in SHARED_GEOMETRY_SCHEMAS
    }
    reference = variants[SHARED_GEOMETRY_SCHEMAS[0]]
    assert reference is not None, (
        f"{SHARED_GEOMETRY_SCHEMAS[0]} is missing '#/$defs/{definition}'"
    )
    drifted = [name for name, value in variants.items() if value != reference]
    assert not drifted, (
        f"'#/$defs/{definition}' differs from {SHARED_GEOMETRY_SCHEMAS[0]} in: {drifted}"
    )


@pytest.mark.parametrize(
    "description, schema",
    [
        (
            "string in a type list",
            {
                "type": "object",
                "properties": {"a": {"type": ["string", "null"]}},
                "additionalProperties": False,
            },
        ),
        (
            "unbounded string",
            {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
        (
            "unbounded array",
            {
                "type": "object",
                "properties": {"a": {"type": "array"}},
                "additionalProperties": False,
            },
        ),
        (
            "relative file $ref",
            {
                "type": "object",
                "properties": {"a": {"$ref": "other.json#/$defs/x"}},
                "additionalProperties": False,
            },
        ),
        (
            "dangling $ref",
            {
                "type": "object",
                "properties": {"a": {"$ref": "#/$defs/missing"}},
                "additionalProperties": False,
            },
        ),
        (
            "$dynamicRef",
            {
                "type": "object",
                "properties": {"a": {"$dynamicRef": "#x"}},
                "additionalProperties": False,
            },
        ),
        (
            "default",
            {
                "type": "object",
                "properties": {"a": {"type": "number", "default": 1}},
                "additionalProperties": False,
            },
        ),
        (
            "untyped object",
            {
                "type": "object",
                "properties": {"a": {"properties": {}}},
                "additionalProperties": False,
            },
        ),
        ("open object", {"type": "object", "properties": {"a": {"type": "number"}}}),
        (
            "attributes without maxProperties",
            {
                "type": "object",
                "properties": {
                    "attributes": {
                        "type": "object",
                        "propertyNames": {"maxLength": 8},
                        "additionalProperties": {"type": "number"},
                    }
                },
                "additionalProperties": False,
            },
        ),
        (
            "attributes without key limit",
            {
                "type": "object",
                "properties": {
                    "attributes": {
                        "type": "object",
                        "maxProperties": 4,
                        "additionalProperties": {"type": "number"},
                    }
                },
                "additionalProperties": False,
            },
        ),
        (
            "self-reference",
            {
                "type": "object",
                "properties": {"c": {"$ref": "#"}},
                "additionalProperties": False,
            },
        ),
        (
            "recursive $defs",
            {
                "type": "object",
                "properties": {"c": {"$ref": "#/$defs/n"}},
                "$defs": {
                    "n": {
                        "type": "object",
                        "properties": {"c": {"$ref": "#/$defs/n"}},
                        "additionalProperties": False,
                    }
                },
                "additionalProperties": False,
            },
        ),
        (
            "bad language",
            {
                "type": "object",
                "properties": {"language": {"type": "string", "maxLength": 5}},
                "additionalProperties": False,
            },
        ),
        (
            "bad score range",
            {
                "type": "object",
                "properties": {
                    "score": {"type": "number", "minimum": 0, "maximum": 100}
                },
                "additionalProperties": False,
            },
        ),
    ],
)
def test_style_lint_rejects(description, schema):
    assert style_violations("probe.json", schema), f"Style lint accepted: {description}"


def test_style_lint_ignores_property_named_default():
    schema = {
        "type": "object",
        "properties": {"default": {"type": "number"}},
        "additionalProperties": False,
    }
    assert style_violations("probe.json", schema) == []
