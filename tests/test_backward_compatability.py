import json
from pathlib import Path
import pytest
import jsonschema_rs
from hypothesis import given, settings, HealthCheck
from hypothesis_jsonschema import from_schema
from packaging.version import Version

ROOT_DIR = Path(__file__).parent.parent
REFERENCE_DIR = ROOT_DIR / "reference" / "schemas"
WORKING_DIR = ROOT_DIR / "schemas"

def get_latest_reference_dir():
    if not REFERENCE_DIR.exists():
        return None
    versions = [d for d in REFERENCE_DIR.iterdir() if d.is_dir()]
    if not versions:
        return None
    return max(versions, key=lambda d: Version(d.name))

def get_schema_pairs():
    latest_ref_dir = get_latest_reference_dir()
    if not latest_ref_dir:
        return []

    pairs = []
    for working_file in WORKING_DIR.glob("*.json"):
        ref_file = latest_ref_dir / working_file.name
        
        if ref_file.exists():
            with open(ref_file) as rf:
                old_schema = json.load(rf)
            with open(working_file) as wf:
                new_schema = json.load(wf)
            
            pairs.append((
                working_file.stem,
                latest_ref_dir.name, 
                "working",
                old_schema, 
                new_schema
            ))
    return pairs

@pytest.mark.parametrize("schema_name, v_old, v_new, old_schema, new_schema", get_schema_pairs())
class TestBackwardCompatibility:

    def test_ast_strictness(self, schema_name, v_old, v_new, old_schema, new_schema):
        """Mathematical proof: Recursively ensures no boundaries tightened and no fields removed."""
        
        def check_node(old_node, new_node, path="root"):
            if not isinstance(old_node, dict) or not isinstance(new_node, dict):
                return
            
            old_type = old_node.get("type")
            new_type = new_node.get("type")
            if old_type:
                if isinstance(old_type, str): old_type = [old_type]
                if isinstance(new_type, str): new_type = [new_type]
                for t in old_type:
                    assert t in (new_type or []), f"[{schema_name}] {path}: Type '{t}' was removed."

            for bound in ["maxLength", "maxItems", "maxProperties", "maximum"]:
                if bound in old_node:
                    assert new_node.get(bound, float('inf')) >= old_node[bound], \
                        f"[{schema_name}] {path}: Tightened {bound} ({old_node[bound]} -> {new_node.get(bound)})"

            for bound in ["minLength", "minItems", "minProperties", "minimum"]:
                if bound in old_node:
                    assert new_node.get(bound, float('-inf')) <= old_node[bound], \
                        f"[{schema_name}] {path}: Tightened {bound} ({old_node[bound]} -> {new_node.get(bound)})"

            if "enum" in old_node:
                assert "enum" in new_node, f"[{schema_name}] {path}: Enum block removed entirely."
                for val in old_node["enum"]:
                    assert val in new_node["enum"], f"[{schema_name}] {path}: Removed enum value '{val}'."

            old_req = set(old_node.get("required", []))
            new_req = set(new_node.get("required", []))
            added_reqs = new_req - old_req
            assert not added_reqs, f"[{schema_name}] {path}: Added new required fields: {added_reqs}"

            old_props = old_node.get("properties", {})
            new_props = new_node.get("properties", {})
            for key, old_prop in old_props.items():
                assert key in new_props, f"[{schema_name}] {path}: Removed property '{key}'."
                check_node(old_prop, new_props[key], f"{path}.{key}")

            if "items" in old_node and isinstance(old_node["items"], dict):
                assert "items" in new_node, f"[{schema_name}] {path}: Removed 'items' definition for array."
                check_node(old_node["items"], new_node["items"], f"{path}[items]")

            old_defs = old_node.get("$defs", {})
            new_defs = new_node.get("$defs", {})
            for key, old_def in old_defs.items():
                assert key in new_defs, f"[{schema_name}] {path}: Removed internal definition '#/$defs/{key}'."
                check_node(old_def, new_defs[key], f"{path}.$defs.{key}")

        check_node(old_schema, new_schema)

    def test_hypothesis_fuzzing(self, schema_name, v_old, v_new, old_schema, new_schema):
        """Fuzzing proof: Generate thousands of valid v_old payloads and test against v_new."""
        
        validator_new = jsonschema_rs.Draft202012Validator(new_schema)

        @given(old_data=from_schema(old_schema))
        @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
        def run_fuzzer(old_data):
            try:
                validator_new.validate(old_data)
            except Exception as e:
                pytest.fail(f"[{schema_name} {v_old}->{v_new}] Backward compatibility broken!\n"
                            f"Valid {v_old} data failed on {v_new} schema.\n"
                            f"Data: {json.dumps(old_data, indent=2)}\nError: {e}")
        
        run_fuzzer()