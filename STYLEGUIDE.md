# Schema Style Guide

Where possible, the Open Validation Schemas adhere to these design patterns.

### 1. Consistent Constraints

  * **No Unbounded Structures:** Every `string` must have a `maxLength`. Every `array` must have a `maxItems`.
  * **No Additional Properties:** `additionalProperties` must always be `false`. Use the standard `attributes` pattern for extensibility.
  * **No Unbounded Nesting:** Schemas should have a fixed-depth.

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


### 3. Exceptions

- :`open/geolocation`**: This schema implements a subset of GeoJSON ([RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946){:target="_blank"}). For this reason it does not include the `attributes` field, as GeoJSON already defines `properties` with a similar function.