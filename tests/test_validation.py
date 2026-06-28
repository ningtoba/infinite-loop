"""Tests for validate_json_output."""

from pi_loop.validation import validate_json_output


def test_valid_output_passes():
    """Valid output against a schema returns (True, '')."""
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
        },
    }
    output = {"name": "test", "count": 42}
    valid, msg = validate_json_output(output, schema)
    assert valid
    assert msg == ""


def test_missing_required_field():
    """Missing required field returns error."""
    schema = {
        "type": "object",
        "required": ["name", "status"],
        "properties": {
            "name": {"type": "string"},
            "status": {"type": "string"},
        },
    }
    output = {"name": "test"}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "missing required field" in msg
    assert "'status'" in msg


def test_type_mismatch_string():
    """Type mismatch for string field returns error."""
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    output = {"name": 42}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "expected string" in msg
    assert "int" in msg


def test_type_mismatch_integer():
    """Type mismatch for integer field returns error."""
    schema = {
        "type": "object",
        "required": ["count"],
        "properties": {"count": {"type": "integer"}},
    }
    output = {"count": "not-a-number"}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "expected integer" in msg


def test_type_mismatch_boolean():
    """Type mismatch for boolean field returns error."""
    schema = {
        "type": "object",
        "required": ["active"],
        "properties": {"active": {"type": "boolean"}},
    }
    output = {"active": "yes"}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "expected boolean" in msg


def test_type_mismatch_number():
    """Type mismatch for number field returns error."""
    schema = {
        "type": "object",
        "required": ["score"],
        "properties": {"score": {"type": "number"}},
    }
    output = {"score": "high"}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "expected number" in msg


def test_type_mismatch_array():
    """Type mismatch for array field returns error."""
    schema = {
        "type": "object",
        "required": ["tags"],
        "properties": {"tags": {"type": "array"}},
    }
    output = {"tags": "not-a-list"}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "expected array" in msg


def test_type_mismatch_object():
    """Type mismatch for object field returns error."""
    schema = {
        "type": "object",
        "required": ["meta"],
        "properties": {"meta": {"type": "object"}},
    }
    output = {"meta": "not-an-object"}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "expected object" in msg


def test_enum_validation():
    """Enum validation rejects invalid values."""
    schema = {
        "type": "object",
        "required": ["status"],
        "properties": {
            "status": {
                "type": "string",
                "enum": ["ok", "error", "pending"],
            },
        },
    }
    output = {"status": "invalid-value"}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "expected one of" in msg
    assert "invalid-value" in msg


def test_enum_valid():
    """Valid enum value passes."""
    schema = {
        "type": "object",
        "required": ["status"],
        "properties": {
            "status": {
                "type": "string",
                "enum": ["ok", "error", "pending"],
            },
        },
    }
    output = {"status": "ok"}
    valid, msg = validate_json_output(output, schema)
    assert valid


def test_string_min_length():
    """String shorter than minLength fails."""
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string", "minLength": 3}},
    }
    output = {"name": "ab"}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "min length" in msg
    assert "3" in msg


def test_string_max_length():
    """String longer than maxLength fails."""
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string", "maxLength": 5}},
    }
    output = {"name": "toolong"}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "max length" in msg
    assert "5" in msg


def test_string_length_within_bounds():
    """String within length bounds passes."""
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 10}},
    }
    output = {"name": "hello"}
    valid, msg = validate_json_output(output, schema)
    assert valid


def test_numeric_minimum():
    """Number below minimum fails."""
    schema = {
        "type": "object",
        "required": ["count"],
        "properties": {"count": {"type": "integer", "minimum": 0}},
    }
    output = {"count": -1}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "minimum" in msg


def test_numeric_maximum():
    """Number above maximum fails."""
    schema = {
        "type": "object",
        "required": ["count"],
        "properties": {"count": {"type": "integer", "maximum": 100}},
    }
    output = {"count": 200}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "maximum" in msg


def test_nested_object_validation():
    """Nested object properties are validated."""
    schema = {
        "type": "object",
        "required": ["meta"],
        "properties": {
            "meta": {
                "type": "object",
                "required": ["version"],
                "properties": {
                    "version": {"type": "integer", "minimum": 1},
                },
            },
        },
    }
    output = {"meta": {"version": 0}}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "minimum" in msg


def test_empty_schema():
    """Empty schema returns (True, '')."""
    valid, msg = validate_json_output({"key": "value"}, {})
    assert valid
    assert msg == ""


def test_none_schema():
    """None schema returns (True, '')."""
    valid, msg = validate_json_output({"key": "value"}, None)  # type: ignore[arg-type]
    assert valid
    assert msg == ""


def test_integer_rejects_bool():
    """Boolean is not accepted as integer."""
    schema = {
        "type": "object",
        "required": ["count"],
        "properties": {"count": {"type": "integer"}},
    }
    output = {"count": True}
    valid, msg = validate_json_output(output, schema)
    assert not valid
    assert "integer" in msg


def test_number_accepts_int():
    """Integer is accepted as number."""
    schema = {
        "type": "object",
        "required": ["score"],
        "properties": {"score": {"type": "number"}},
    }
    output = {"score": 42}
    valid, msg = validate_json_output(output, schema)
    assert valid


def test_enum_with_mixed_types():
    """Enum can contain non-string types."""
    schema = {
        "type": "object",
        "required": ["level"],
        "properties": {
            "level": {
                "enum": ["low", "medium", "high", 0, 1, 2],
            },
        },
    }
    valid, msg = validate_json_output({"level": "high"}, schema)
    assert valid
    valid, msg = validate_json_output({"level": 0}, schema)
    assert valid
    valid, msg = validate_json_output({"level": "unknown"}, schema)
    assert not valid
