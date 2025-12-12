import json
import pytest
from jsonschema import validate, ValidationError
from pathlib import Path

# --- Configuration ---
REPO_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
EXAMPLES_DIR = REPO_ROOT / "examples"
POSITIVE_DIR = EXAMPLES_DIR / "positive"
NEGATIVE_DIR = EXAMPLES_DIR / "negative"

def get_known_schemas():
    """
    Returns a dict mapping schema names (without extension) to their full paths.
    Example: {'audio-transcription': Path(.../audio-transcription.json)}
    """
    return {p.stem: p for p in SCHEMAS_DIR.glob("*.json")}

KNOWN_SCHEMAS = get_known_schemas()

def resolve_schema(example_path):
    """
    Finds the matching schema for a given example file by checking prefixes.
    Example: 'audio-transcription-bad-1.json' -> matches 'audio-transcription'
    """
    filename = example_path.name

    for schema_name, schema_path in sorted(KNOWN_SCHEMAS.items(), key=lambda x: len(x[0]), reverse=True):
        if filename.startswith(schema_name):
            return schema_path
            
    raise ValueError(f"Could not find a matching schema for example: {filename}")

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

# --- Tests ---

def get_positive_examples():
    if not POSITIVE_DIR.exists():
        return []
    return sorted(list(POSITIVE_DIR.glob("*.json")))

def get_negative_examples():
    if not NEGATIVE_DIR.exists():
        return []
    return sorted(list(NEGATIVE_DIR.glob("*.json")))

@pytest.mark.parametrize("example_path", get_positive_examples())
def test_positive_examples_are_valid(example_path):
    """
    Ensures that every file in examples/positive validates successfully.
    """
    instance = load_json(example_path)
    schema_path = resolve_schema(example_path)
    schema = load_json(schema_path)

    # Should NOT raise ValidationError
    validate(instance=instance, schema=schema)

@pytest.mark.parametrize("example_path", get_negative_examples())
def test_negative_examples_are_invalid(example_path):
    """
    Ensures that every file in examples/negative FAILS validation.
    If a negative example passes validation, this test fails.
    """
    instance = load_json(example_path)
    schema_path = resolve_schema(example_path)
    schema = load_json(schema_path)

    with pytest.raises(ValidationError, match=r".*"):
        validate(instance=instance, schema=schema)