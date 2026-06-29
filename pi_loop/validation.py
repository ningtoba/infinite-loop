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
