import json
from pathlib import Path

import jsonschema_rs
import pytest

REPO_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
EXAMPLES_DIR = REPO_ROOT / "reference" / "examples"
POSITIVE_DIR = EXAMPLES_DIR / "positive"
NEGATIVE_DIR = EXAMPLES_DIR / "negative"
NEGATIVE_EXPECTATIONS = EXAMPLES_DIR / "negative-expectations.json"

KNOWN_SCHEMAS = {p.stem: p for p in SCHEMAS_DIR.glob("*.json")}


def resolve_schema(example_path: Path) -> Path:
    """Return the schema whose name is the longest prefix of the example's filename."""
    matches = [name for name in KNOWN_SCHEMAS if example_path.name.startswith(name)]
    if not matches:
        raise ValueError(
            f"Could not find a matching schema for example: {example_path.name}"
        )
    return KNOWN_SCHEMAS[max(matches, key=len)]


def load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def validator_for(example_path: Path) -> jsonschema_rs.Draft202012Validator:
    return jsonschema_rs.Draft202012Validator(
        load_json(resolve_schema(example_path)), validate_formats=True
    )


def pointer(error: jsonschema_rs.ValidationError) -> str:
    return "".join(f"/{part}" for part in error.instance_path)


def covered_schemas(directory: Path) -> set[str]:
    return {resolve_schema(p).stem for p in directory.glob("*.json")}


POSITIVE_EXAMPLES = sorted(POSITIVE_DIR.glob("*.json"))
NEGATIVE_EXAMPLES = sorted(NEGATIVE_DIR.glob("*.json"))
EXPECTATIONS = load_json(NEGATIVE_EXPECTATIONS)


@pytest.mark.parametrize("example_path", POSITIVE_EXAMPLES, ids=lambda p: p.name)
def test_positive_examples_are_valid(example_path):
    """Every file in examples/positive validates successfully."""
    validator_for(example_path).validate(load_json(example_path))


@pytest.mark.parametrize("example_path", NEGATIVE_EXAMPLES, ids=lambda p: p.name)
def test_negative_examples_fail_for_the_expected_reason(example_path):
    """Every file in examples/negative fails, only at its expected location, with its expected message."""
    expected = EXPECTATIONS.get(example_path.name)
    assert expected, f"{example_path.name} has no entry in {NEGATIVE_EXPECTATIONS.name}"

    errors = list(validator_for(example_path).iter_errors(load_json(example_path)))
    assert errors, f"{example_path.name} unexpectedly passed validation"

    unrelated = [
        e for e in errors if not (pointer(e) + "/").startswith(expected["path"] + "/")
    ]
    assert not unrelated, (
        f"{example_path.name} also fails outside {expected['path'] or '/'}: "
        + "; ".join(f"{pointer(e)}: {e.message}" for e in unrelated)
    )
    assert any(expected["message"] in e.message for e in errors), (
        f"{example_path.name} did not fail with {expected['message']!r}: "
        + "; ".join(e.message for e in errors)
    )


def test_negative_expectations_have_no_stale_entries():
    names = {p.name for p in NEGATIVE_EXAMPLES}
    stale = set(EXPECTATIONS) - names
    assert not stale, (
        f"{NEGATIVE_EXPECTATIONS.name} lists missing examples: {sorted(stale)}"
    )


@pytest.mark.parametrize(
    "kind, directory", [("positive", POSITIVE_DIR), ("negative", NEGATIVE_DIR)]
)
def test_every_schema_has_examples(kind, directory):
    missing = set(KNOWN_SCHEMAS) - covered_schemas(directory)
    assert not missing, f"Schemas with no {kind} examples: {sorted(missing)}"
