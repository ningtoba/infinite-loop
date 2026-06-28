"""JSON Schema validation — validate spawned session output against a schema."""

import json

from .file_utils import _log

# Maximum recursion depth for nested object validation to prevent stack overflow
# on circular or excessively deep schemas. JSON Schema allows nesting of "items"
# (array) and "properties"/"additionalProperties" (object) in a chain.
_MAX_VALIDATION_DEPTH = 50


def validate_json_output(output: dict, schema: dict) -> tuple[bool, str]:
    """Validate a JSON object against a JSON Schema (draft-07 subset).

    Uses stdlib-only validation (no jsonschema dependency). Supports a
    practical subset: required fields, type checking, enum values, and
    string minLength/maxLength. Returns (is_valid, error_message).

    Protection: recursion depth is capped at ``_MAX_VALIDATION_DEPTH``
    (50) and an identity-based cycle detector tracks already-visited
    ``(id(schema_node), id(obj))`` pairs to prevent stack overflow on
    self-referencing or circular schemas.
    """
    if not schema:
        return True, ""

    def _check_type(value, expected: str, path: str) -> str | None:
        if expected == "string":
            if not isinstance(value, str):
                return f"{path}: expected string, got {type(value).__name__}"
        elif expected == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                return f"{path}: expected integer, got {type(value).__name__}"
        elif expected == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return f"{path}: expected number, got {type(value).__name__}"
        elif expected == "boolean":
            if not isinstance(value, bool):
                return f"{path}: expected boolean, got {type(value).__name__}"
        elif expected in ("array", "object"):
            if not isinstance(value, dict if expected == "object" else list):
                return f"{path}: expected {expected}, got {type(value).__name__}"
        return None

    def _validate(
        obj,
        schema_node: dict,
        path: str,
        *,
        _depth: int = 0,
        _seen: set | None = None,
    ) -> str | None:
        if _depth > _MAX_VALIDATION_DEPTH:
            return (
                f"{path}: maximum validation depth "
                f"({_MAX_VALIDATION_DEPTH}) exceeded"
            )

        # Cycle detection: track (schema_node, obj) identity pairs.
        # A well-formed schema won't revisit the same (schema, value) pair
        # on a valid path, so hitting one signals a circular reference.
        if _seen is None:
            _seen = set()
        pair_id = (id(schema_node), id(obj))
        # Only track for non-trivial objects (dicts/lists that can nest)
        if isinstance(obj, (dict, list)):
            if pair_id in _seen:
                return (
                    f"{path}: circular reference detected "
                    f"(schema id={id(schema_node)}, obj id={id(obj)})"
                )
            _seen.add(pair_id)

        required = schema_node.get("required", [])
        for field in required:
            if field not in obj:
                return f"{path}: missing required field '{field}'"

        properties = schema_node.get("properties", {})
        for field, field_schema in properties.items():
            if field not in obj:
                continue
            val = obj[field]
            field_path = f"{path}.{field}" if path else field

            expected_type = field_schema.get("type")

            if expected_type:
                err = _check_type(val, expected_type, field_path)
                if err:
                    return err

            enum_vals = field_schema.get("enum")
            if enum_vals is not None and val not in enum_vals:
                return f"{field_path}: expected one of {enum_vals}, got {val!r}"

            if isinstance(val, str):
                min_len = field_schema.get("minLength")
                max_len = field_schema.get("maxLength")
                if min_len is not None and len(val) < min_len:
                    return f"{field_path}: min length {min_len}, got {len(val)}"
                if max_len is not None and len(val) > max_len:
                    return f"{field_path}: max length {max_len}, got {len(val)}"

            if isinstance(val, (int, float)) and not isinstance(val, bool):
                minimum = field_schema.get("minimum")
                maximum = field_schema.get("maximum")
                if minimum is not None and val < minimum:
                    return f"{field_path}: minimum {minimum}, got {val}"
                if maximum is not None and val > maximum:
                    return f"{field_path}: maximum {maximum}, got {val}"

            if isinstance(val, dict) and "properties" in field_schema:
                err = _validate(
                    val,
                    field_schema,
                    field_path,
                    _depth=_depth + 1,
                    _seen=_seen,
                )
                if err:
                    return err

        return None

    error = _validate(output, schema, "root")
    if error:
        return False, error
    return True, ""


def load_json_schema(path: str) -> dict | None:
    """Load a JSON Schema from a file path. Returns None on failure."""
    try:
        with open(path) as f:
            schema = json.load(f)
        if not isinstance(schema, dict):
            _log(f"[SCHEMA] WARN: {path} is not a JSON object, ignoring")
            return None
        return schema
    except (FileNotFoundError, json.JSONDecodeError) as e:
        _log(f"[SCHEMA] WARN: Could not load {path}: {e}")
        return None
