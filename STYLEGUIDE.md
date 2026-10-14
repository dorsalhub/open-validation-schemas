# Schema Style Guide

Where possible, the Open Validation Schemas adhere to these design patterns.

### 1. Consistent Constraints

  * **No Unbounded Structures:** Every `string` must have a `maxLength`. Every `array` must have a `maxItems`. Every open object (one that does not set `additionalProperties: false`) must have a `maxProperties` and must limit its key length with `"propertyNames": { "maxLength": 128 }`.
  * **No Additional Properties:** Objects with `properties` must set `additionalProperties` to `false`. Use the standard `attributes` pattern for extensibility.
  * **No Unbounded Nesting:** Schemas must have a fixed depth. Self-references (`"$ref": "#"`) and recursive `$defs` are forbidden.
  * **No Type Lists:** Write `"anyOf": [{ "type": "string", "maxLength": 128 }, { "type": "integer" }]` rather than `"type": ["string", "integer"]`, so that each type carries its own constraints.

#### String Length Tiers

Choose a string's `maxLength` from this table rather than inventing a new limit. When a field outgrows its limit, move it to the next tier.

| `maxLength` | Use for | Examples |
| :--- | :--- | :--- |
| `3` | ISO codes | `language` |
| `128` | Identifiers, labels, names and keys | `label`, `id`, `speaker.name`, `propertyNames` |
| `256` | Short explanations | `score_explanation`, `target` |
| `1024` | Free-text names and short values | `producer`, `model`, `attributes` values |
| `2048` | URLs | `vocabulary_url` |
| `4096` | A single unit of extracted text | a block, segment or entity `text` |
| `262144` | Long input text | `prompt`, `system_prompt` |
| `524288` | Long output text | `response_data`, a full transcription `text` |

### 2. Common Patterns

#### Producer vs Model

All schemas support a top-level identifier `producer` or `model` which indicates the **creator** (model, tool or author) of the record.

- If the record *could* be created manually or have a human author (e.g. `open/audio-transcription`) prefer `producer`. 
- If the schema describes a model's output (e.g. `open/llm-output`, `open/embedding`), prefer `model`. 

Example:

```json
 "producer": {
    "type": "string",
    "description": "The creator (model, tool or author) of this transcription (e.g., 'Whisper-v3', 'Manual Review').",
    "maxLength": 1024
}
```

#### Language Standardization

Where `language` is a field in a schema, constrain it to 3 lowercase letters. This is to be consistent with the [ISO 639-3](https://en.wikipedia.org/wiki/ISO_639-3) standard for the representation of the names of languages. This is the most comprehensive and coherent identifier for language identification.

Example:

```json
"language": {
    "type": "string",
    "description": "The 3-letter ISO-639-3 language code of the text (e.g., 'eng', 'fra').",
    "pattern": "^[a-z]{3}$",
    "maxLength": 3
}
```

#### Arbitrary Metadata

It's common to have additional metadata, specific to the **record**, which may not fit into the schema.

For this reason, most schemas feature a standardized `attributes` object on the record-level. 

Depending on the schema, it may also make sense to add attributes to individual **elements**.

```json
"attributes": {
    "type": "object",
    "description": "Arbitrary metadata relevant to this item.",
    "maxProperties": 16,
    "propertyNames": {
        "maxLength": 128
    },
    "additionalProperties": {
        "anyOf": [
            { "type": "string", "maxLength": 1024 },
            { "type": "number" },
            { "type": "boolean" },
            { "type": "null" }
        ]
    }
}
```

#### Scores & Confidence

Unless the schema is for a domain with its own established constraints for model scoring, prefer a field named `score` whose value is a normalized float:

| Type | Bounds | Semantics | Use Case |
| :--- | :--- | :--- | :--- |
| **Strict Probability** | `0.0` to `1.0` | 0 is "Uncertain/Absent", 1 is "Certain/Present". | Extraction, OCR, ASR. |
| **Bipolar Metric** | `-1.0` to `1.0` | Negative is "Reject/Bad", 0 is "Neutral", Positive is "Accept/Good". | Sentiment, RLHF, Classification. |

  *If using the Bipolar Metric, you should include a `score_explanation` field to clarify the semantics.*

Example:

```json
"score": {
    "type": "number",
    "description": "The confidence score for this segment's transcription, ranging from 0.0 (uncertain) to 1.0 (certain).",
    "minimum": 0,
    "maximum": 1
}
```

#### Vocabularies

Schemas with labels (`open/classification`, `open/entity-extraction`, `open/object-detection`) accept an inline `vocabulary` of up to 100 unique labels, or a `vocabulary_url` for anything larger. A vocabulary is repeated in every record, so a large inline one multiplies across a dataset. At 100 labels of up to 128 characters, it adds roughly 13 KB of ASCII text to each record.

#### Geometry

Schemas that carry 2D geometry (`open/document-extraction`, `open/entity-extraction`, `open/object-detection`) share identical inline `box`, `polygon` and `multi_polygon` definitions. Because remote references are forbidden, each schema holds its own copy; change all copies together (the tests check they are identical).

Coordinates are measured from the top-left corner and are never negative. Every coordinate is expressed in the record's `unit` (`px`, `pt`, `normalized` or `per_mille`), and `unit` is required whenever geometry is present.

#### Conditionals

An `if` that tests a property must also list that property in `required`. Otherwise the condition is true whenever the property is absent, and its `then` applies unexpectedly:

```json
"if": {
    "properties": { "unit": { "const": "normalized" } },
    "required": ["unit"]
}
```

#### Constraints JSON Schema Cannot Express

Some rules relate two values, such as an end time that must not be earlier than its start time, or a label that must belong to the record's `vocabulary`. JSON Schema cannot check these, so state them in the field's `description` with "must", and leave consumers to enforce them:

```json
"end_time": {
    "type": "number",
    "description": "Segment end time in seconds. Must not be earlier than start_time."
}
```

#### Common Field Locations

For readability and debugging purposes, common fields are in similar locations in each schema: `"x-license"` is always at the very top; it is followed by `"$schema"`, `"$id"`, `"title"`, `"version"` and `"description"`, all above `"properties"`; `"$defs"` comes after the validation keywords; and `"additionalProperties"` is always the last key of any object it constrains.

### 3. Language Constraints

All schemas align with the [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-core) specification, and thus all schemas must include `"$schema": "https://json-schema.org/draft/2020-12/schema"` in their root. 

While we support the 2020-12 spec, we specifically disallow specific features of the JSON Schema spec, to ensure schemas are portable, deterministic, and safe:

#### No `default`
* **Rule:** The `default` keyword is forbidden.
* **Reason:** While `default` is officially defined as an [annotation](https://json-schema.org/draft/2020-12/draft-bhutton-json-schema-validation-00#rfc.section.9.2), allowing it creates ambiguity between different validators. Some tools treat it as an annotation, while others treat it as a [transformation directive](https://ajv.js.org/guide/modifying-data.html#assigning-defaults) (e.g. injecting the value if missing). To avoid ambiguity, we forbid the keyword.

#### No External Dependencies (`$ref`)
* **Rule:** References must be internal (e.g., `#/$defs/name`). References to remote URLs (e.g., `https://example.com/schema.json`) are forbidden.
* **Reason:** Schemas must be fully self-contained/standalone. Validation must not depend on network availability or external server state.
* **Use sparingly:** Only move a subschema into `$defs` when it is reused within the same schema (as `open/geolocation` reuses `position`). Write single-use subschemas inline, where they are read.

#### No `patternProperties`
* **Rule:** The `patternProperties` keyword is forbidden.
* **Reason:** Regular-expression keys make a schema's shape depend on regex semantics, which differ between validators and are hard to index or translate. To constrain the keys of an open object, use `propertyNames`.

#### No Dynamic Scope
* **Rule:** `$dynamicRef` and `$dynamicAnchor` are forbidden.
* **Reason:** Scope resolution must be static and lexically determinable. This ensures schemas can be easily indexed, audited, and translated into other formats (like SQL tables or Avro) without complex runtime evaluation.

### 4. Exceptions

- **`open/geolocation`**: This schema implements a subset of GeoJSON ([RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)). For this reason it does not include the `attributes` field, as GeoJSON already defines `properties` with a similar function. Its objects also accept RFC 7946 foreign members, so they are open objects (bounded by `maxProperties` and `propertyNames`) rather than setting `additionalProperties: false`.