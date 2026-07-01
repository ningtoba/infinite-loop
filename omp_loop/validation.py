"""JSON Schema validation — validate spawned session output against a schema."""

import json

from .file_utils import _log


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


def validate_output(output: str, schema: dict | None) -> tuple[bool, list[str]]:
    """Validate JSON output against a JSON Schema.

    Attempts to parse *output* as JSON (or extract a JSON block from it),
    then validates against *schema*.  Returns ``(is_valid, errors)`` where
    *errors* is a list of human-readable validation messages (empty when valid).

    If the output cannot be parsed as JSON, the validation is **skipped**
    (returns ``(True, [])``) because the output may be free-form text rather
    than a JSON response.  Only structured JSON output is validated.
    """
    if not schema:
        return True, []

    # Attempt to parse as full JSON
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        # Try to extract a JSON block (last object wins, matching extract_json_from_output)
        extracted = _extract_json_block(output)
        if extracted is None:
            return True, []  # not JSON output — skip validation
        try:
            data = json.loads(extracted)
        except json.JSONDecodeError:
            return True, []  # can't parse — skip

    errors: list[str] = []

    # Validate required top-level keys
    required_keys = schema.get("required", [])
    if isinstance(required_keys, list):
        for key in required_keys:
            if key not in data:
                errors.append(f"Missing required key: {key}")

    # Validate property types (simple type checking)
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for key, expected in properties.items():
            if key not in data:
                continue
            expected_type = expected.get("type", "") if isinstance(expected, dict) else ""
            actual = data[key]
            if expected_type == "string" and not isinstance(actual, str):
                errors.append(f"Key '{key}' should be string, got {type(actual).__name__}")
            elif expected_type == "integer" and not isinstance(actual, int):
                errors.append(f"Key '{key}' should be integer, got {type(actual).__name__}")
            elif expected_type == "number" and not isinstance(actual, (int, float)):
                errors.append(f"Key '{key}' should be number, got {type(actual).__name__}")
            elif expected_type == "boolean" and not isinstance(actual, bool):
                errors.append(f"Key '{key}' should be boolean, got {type(actual).__name__}")
            elif expected_type == "array" and not isinstance(actual, list):
                errors.append(f"Key '{key}' should be array, got {type(actual).__name__}")
            elif expected_type == "object" and not isinstance(actual, dict):
                errors.append(f"Key '{key}' should be object, got {type(actual).__name__}")

    return len(errors) == 0, errors


def _extract_json_block(text: str) -> str | None:
    """Extract the last top-level JSON object from *text*.

    Minimal brace-matcher that skips quoted strings.  Returns ``None``
    when no balanced JSON object is found.
    """
    depth = 0
    in_str = False
    escape = False
    start = -1
    last_valid: str | None = None

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue

        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                last_valid = text[start : i + 1]

    return last_valid
