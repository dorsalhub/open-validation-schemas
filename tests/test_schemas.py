import json
import pytest
from jsonschema.validators import validator_for
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
EXAMPLES_DIR = REPO_ROOT / "examples"
POSITIVE_DIR = EXAMPLES_DIR / "positive"


def get_schemas():
    """Yields (filename, json_content) for every schema."""
    for p in SCHEMAS_DIR.glob("*.json"):
        with open(p, "r") as f:
            yield p.name, json.load(f)


@pytest.mark.parametrize("filename, schema", get_schemas())
def test_schema_is_valid_json_schema(filename, schema):
    try:
        cls = validator_for(schema)
        cls.check_schema(schema)
    except Exception as e:
        pytest.fail(f"Schema '{filename}' is invalid JSON Schema: {e}")


def get_schema_names():
    return {p.stem for p in SCHEMAS_DIR.glob("*.json")}


def get_covered_schemas():
    covered = set()
    for p in POSITIVE_DIR.glob("*.json"):
        for schema_name in get_schema_names():
            if p.name.startswith(schema_name):
                covered.add(schema_name)
    return covered
