# Open Validation Schemas

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Schemas: 10](https://img.shields.io/badge/Schemas-10-brightgreen.svg)](./schemas)
[![Status](https://github.com/dorsalhub/open-validation-schemas/actions/workflows/ci.yml/badge.svg)](https://github.com/dorsalhub/open-validation-schemas/actions)

**Open Validation Schemas** is a collection of strict, versioned JSON schemas for defining and validating structured metadata.

It provides a **unified contract** for many common data engineering tasks, standardizing outputs from a range of sources, including **machine learning models**, **workflow steps**, **annotation tasks**, and **ad-hoc scripts**.

These schemas are designed as a standalone open standard to decouple data producers from downstream consumers. They are used in production by [DorsalHub](https://dorsalhub.com) to structure and validate user-contributed file annotations.

## Why Open Validation Schemas?

Data pipelines are brittle when every tool defines its own output format. **Open Validation Schemas** provides a single, predictable standard, decoupling producers (models, scripts) from consumers (databases, UIs).

Instead of custom parsers for every model, validate against a common definition.

We enforce a "strict by default" philosophy. The schemas are designed to be:

* **Source-Agnostic:** A **classification** result can be structured and validated in the same way, whether it comes from a BERT model, a rule-based regex script, or a human reviewer.
* **Strict & Safe:** Schemas prevent arbitrary property nesting and enforce length limits, making them safe for databases and indexing.
* **Interoperable:** A unified shape for common tasks, ensuring downstream tools don't need custom parsers for every new model version.
* **Community-Driven:** This repository is the central place to discuss improvements and propose new schemas for common data shapes.

## Versioning

We use **Global Versioning**:

* **Lockstep Releases:** The version applies to **all** schemas.
* **Semantic Versioning:** We follow [SemVer 2.0.0](https://semver.org/).
    * **Beta Status (v0.x):** While in **v0.x**, we may make breaking changes to refine the standard. We aim to stabilize quickly, but we prioritize correctness over backward compatibility until v1.0.0.
    * **Major (v1.x -> v2.x):** Once stable (v1.0+), a breaking change to **any** schema (e.g., renaming a required field, tightening a constraint) triggers a major version bump for the entire collection.
    * **Minor (v1.1 -> v1.2):** Non-breaking additions (e.g., adding an optional field or a new schema).
    * **Patch (v1.1.0 -> v1.1.1):** Bug fixes, description updates, or non-functional changes.
* **Schema Metadata:** Every schema file contains a top-level `"version"` field matching the release it belongs to.

## Available Schemas

### `open/audio-transcription`
Store text transcribed from an audio source, supporting timed segments, speaker identification, and non-verbal events.
* [**View Schema**](./schemas/audio-transcription.json)
* [**View Example Record**](./examples/positive/audio-transcription-1.json)

### `open/classification`
Represent classification results, including predicted labels, normalized scoring, and references to the taxonomy or vocabulary.
* [**View Schema**](./schemas/classification.json)
* [**View Example Record**](./examples/positive/classification-1.json)

### `open/document-extraction`
Represent the layout and content of a document, including text blocks, geometric coordinates, and page structure.
* [**View Schema**](./schemas/document-extraction.json)
* [**View Example Record**](./examples/positive/document-extraction-1.json)

### `open/embedding`
Store a vector embedding, including the high-dimensional feature vector and metadata about the algorithm used to generate it.
* [**View Schema**](./schemas/embedding.json)
* [**View Example Record**](./examples/positive/embedding-1.json)

### `open/entity-extraction`
Represent named entities, structural slots, or visual concepts extracted from unstructured data. Links raw evidence (text spans or geometric regions) to normalized values and business concepts.
* [**View Schema**](./schemas/entity-extraction.json)
* [**View Example Record**](./examples/positive/entity-extraction-1.json)

### `open/generic`
Store arbitrary key-value data in a strictly typed structure to prevent uncontrolled nesting.
* [**View Schema**](./schemas/generic.json)
* [**View Example Record**](./examples/positive/generic-1.json)

### `open/geolocation`
Represent a geographic feature using a strict, safe subset of GeoJSON (RFC 7946) optimized for predictable parsing. Restricts the root to a single 'Feature', supports fixed-depth geometries, and disallows recursive collections.
* [**View Schema**](./schemas/geolocation.json)
* [**View Example Record**](./examples/positive/geolocation-1.json)

### `open/llm-output`
Store the full context of a single atomic Large Language Model (LLM) interaction, including the input prompt, generation parameters, and raw output and optional evaluation metrics.
* [**View Schema**](./schemas/llm-output.json)
* [**View Example Record**](./examples/positive/llm-output-1.json)

### `open/object-detection`
Represent objects detected within a file, supporting bounding boxes, polygons, hierarchical relationships (parent/child), and normalized scoring.
* [**View Schema**](./schemas/object-detection.json)
* [**View Example Record**](./examples/positive/object-detection-1.json)

### `open/regression`
Represent continuous numerical predictions. Supports point estimates, confidence intervals, and time-series forecasting.
* [**View Schema**](./schemas/regression.json)
* [**View Example Record**](./examples/positive/regression-1.json)

## Development & Testing

We use [`pytest`](https://docs.pytest.org/en/stable/) and [`jsonschema`](https://python-jsonschema.readthedocs.io/en/stable/) for validation.

### Running Tests Locally
We recommend [`uv`](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies and run tests
uv run pytest
```

This will validate every file in the `examples/` directory against its corresponding schema.

## How to Use These Schemas

These schemas can be used with any JSON Schema validation tool. The Python example below uses the [`jsonschema-rs`](https://github.com/Stranger6667/jsonschema/tree/master/crates/jsonschema-py) library:

```python
import json
import jsonschema_rs

# Load the schema
with open('schemas/classification.json') as f:
    schema = json.load(f)

# Initialize validator (enforcing formats like 'date-time' and 'uri')
validator = jsonschema_rs.Draft202012Validator(
    schema, 
    validate_formats=True
)

# Your data record
record = {
    "vocabulary": ["cat", "dog", "bird"],
    "labels": [
        { "label": "cat", "score": 0.98 }
    ]
}

# This will raise a ValidationError if the record is invalid
validator.validate(record)

print("Record is valid!")
```

## Contributing

We welcome contributions from the community! Whether you are suggesting an improvement to an existing schema or proposing a new one for a common use case, this is the place to do it.

Please read our `CONTRIBUTING.md` guide for the full process, but the general workflow is:

1.  **Open an Issue:** Start by [opening an issue](https://github.com/dorsalhub/open-validation-schemas/issues) to discuss your proposed change or new schema. This allows the community and maintainers to provide feedback before you do the work.
2.  **Submit a Pull Request:** Once the idea is discussed, you can submit a pull request with your changes.

## License

The schemas, examples, and documentation in this repository are licensed under the **Apache 2.0 License**.
