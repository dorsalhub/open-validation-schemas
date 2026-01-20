import json
import pytest
import jsonschema_rs
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
EXAMPLES_DIR = REPO_ROOT / "examples"
POSITIVE_DIR = EXAMPLES_DIR / "positive"
NEGATIVE_DIR = EXAMPLES_DIR / "negative"


def get_schemas():
    """Yields (filename, json_content) for every schema."""
    for p in SCHEMAS_DIR.glob("*.json"):
        with open(p, "r") as f:
            yield p.name, json.load(f)


@pytest.mark.parametrize("filename, schema", get_schemas())
def test_schema_is_valid_json_schema(filename, schema):
    try:
        jsonschema_rs.meta.validate(schema)
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


def iter_nodes(schema, path=""):
    """Recursively yield (path, node) for every node in the schema."""
    if isinstance(schema, dict):
        yield path, schema
        for k, v in schema.items():
            yield from iter_nodes(v, path=f"{path}/{k}")
    elif isinstance(schema, list):
        for i, item in enumerate(schema):
            yield from iter_nodes(item, path=f"{path}[{i}]")

@pytest.mark.parametrize("filename, schema", get_schemas())
def test_schema_adheres_to_style_guide(filename, schema):
    """
    Enforces the 'Strict by Default' policy.
    Now strictly checks maxLength even for formatted strings.
    """
    errors = []
    
    # EXCEPTION: Geolocation is allowed to be open per Style Guide
    # (But we still check it for other rules like maxLength!)
    is_geolocation = (filename == "geolocation.json")

    for path, node in iter_nodes(schema):
        if not isinstance(node, dict):
            continue

        # 1. Ban 'default' (Behavioral Ambiguity)
        if "default" in node:
            errors.append(f"{path}: The keyword 'default' is forbidden.")

        # 2. Ban Remote References (Standalone Promise)
        if "$ref" in node:
            ref = node["$ref"]
            if ref.startswith("http") or ref.startswith("//"):
                errors.append(f"{path}: Remote $ref '{ref}' is forbidden. Use internal #/$defs.")

        # 3. Enforce Bounds on Strings (No Unbounded Structures)
        if node.get("type") == "string" and "enum" not in node and "const" not in node:
            if "maxLength" not in node:
                 errors.append(f"{path}: String must have 'maxLength' (even if format is set).")

        # 4. Enforce Bounds on Arrays
        if node.get("type") == "array":
            if "maxItems" not in node:
                errors.append(f"{path}: Array must have 'maxItems'.")

        # 5. strict additionalProperties
        # Skip this check for geolocation.json (it is explicitly open)
        if not is_geolocation and "properties" in node and node.get("type") == "object" and "attributes" not in path:
             if node.get("additionalProperties") is not False:
                  errors.append(f"{path}: Object must set 'additionalProperties': false.")

    if errors:
        pytest.fail(f"Schema '{filename}' violates Style Guide:\n" + "\n".join(errors))


def test_every_schema_has_negative_examples():
    """Ensure every schema has at least one invalid example to prove constraints work."""
    schema_names = get_schema_names()
    covered = set()
    
    for p in NEGATIVE_DIR.glob("*.json"):
        for name in schema_names:
            if p.name.startswith(name):
                covered.add(name)
    
    missing = schema_names - covered
    if missing:
        pytest.fail(f"The following schemas have NO negative examples: {missing}")