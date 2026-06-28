"""Tests for validation.py — validate_json_output and load_json_schema."""

from __future__ import annotations

from unittest.mock import mock_open, patch


from hermes_loop.validation import validate_json_output, load_json_schema

# ===================================================================
# validate_json_output
# ===================================================================


class TestValidateJsonOutput:
    """Tests for validate_json_output function."""

    def test_no_schema(self):
        """None schema returns (True, '')."""
        result = validate_json_output({"summary": "x"}, None)
        assert result == (True, "")

    def test_empty_dict_schema(self):
        """Empty dict schema returns (True, '')."""
        result = validate_json_output({"summary": "x"}, {})
        assert result == (True, "")

    def test_valid_object(self):
        """Valid object against schema returns (True, '')."""
        schema = {
            "type": "object",
            "required": ["summary", "status"],
            "properties": {
                "summary": {"type": "string"},
                "status": {"type": "string", "enum": ["ok", "error"]},
            },
        }
        output = {"summary": "done", "status": "ok"}
        result = validate_json_output(output, schema)
        assert result == (True, "")

    def test_missing_required_field(self):
        """Missing required field returns (False, error)."""
        schema = {
            "type": "object",
            "required": ["summary", "status"],
            "properties": {
                "summary": {"type": "string"},
                "status": {"type": "string", "enum": ["ok", "error"]},
            },
        }
        output = {"summary": "done"}
        result = validate_json_output(output, schema)
        assert result[0] is False
        assert "missing required field" in result[1].lower()

    def test_wrong_type_string(self):
        """Wrong type for string field returns error."""
        schema = {
            "type": "object",
            "required": ["summary"],
            "properties": {
                "summary": {"type": "string"},
            },
        }
        output = {"summary": 42}
        result = validate_json_output(output, schema)
        assert result[0] is False
        assert "expected string" in result[1].lower()

    def test_wrong_type_integer(self):
        """Wrong type for integer field."""
        schema = {
            "type": "object",
            "required": ["count"],
            "properties": {
                "count": {"type": "integer"},
            },
        }
        output = {"count": "not_a_number"}
        result = validate_json_output(output, schema)
        assert result[0] is False
        assert "expected integer" in result[1]

    def test_integer_rejects_bool(self):
        """Boolean is NOT an integer."""
        schema = {
            "type": "object",
            "required": ["flag"],
            "properties": {
                "flag": {"type": "integer"},
            },
        }
        output = {"flag": True}
        result = validate_json_output(output, schema)
        assert result[0] is False
        assert "expected integer" in result[1]

    def test_number_type(self):
        """Number type accepts both int and float."""
        schema = {
            "type": "object",
            "required": ["value"],
            "properties": {
                "value": {"type": "number"},
            },
        }
        assert validate_json_output({"value": 42}, schema) == (True, "")
        assert validate_json_output({"value": 3.14}, schema) == (True, "")

    def test_boolean_type(self):
        """Boolean type accepts True/False."""
        schema = {
            "type": "object",
            "required": ["active"],
            "properties": {
                "active": {"type": "boolean"},
            },
        }
        assert validate_json_output({"active": True}, schema) == (True, "")
        assert validate_json_output({"active": False}, schema) == (True, "")

    def test_boolean_rejects_int(self):
        """Integer is NOT a boolean."""
        schema = {
            "type": "object",
            "required": ["active"],
            "properties": {
                "active": {"type": "boolean"},
            },
        }
        output = {"active": 1}
        result = validate_json_output(output, schema)
        assert result[0] is False
        assert "expected boolean" in result[1]

    def test_array_type(self):
        """Array type accepts list."""
        schema = {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {"type": "array"},
            },
        }
        assert validate_json_output({"items": [1, 2, 3]}, schema) == (True, "")

    def test_array_rejects_dict(self):
        """Array type rejects dict."""
        schema = {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {"type": "array"},
            },
        }
        result = validate_json_output({"items": {"a": 1}}, schema)
        assert result[0] is False
        assert "expected array" in result[1]

    def test_object_type(self):
        """Object type accepts dict."""
        schema = {
            "type": "object",
            "required": ["data"],
            "properties": {
                "data": {"type": "object"},
            },
        }
        assert validate_json_output({"data": {"key": "val"}}, schema) == (True, "")

    def test_object_rejects_list(self):
        """Object type rejects list."""
        schema = {
            "type": "object",
            "required": ["data"],
            "properties": {
                "data": {"type": "object"},
            },
        }
        result = validate_json_output({"data": [1, 2]}, schema)
        assert result[0] is False
        assert "expected object" in result[1]

    def test_enum_validation(self):
        """Enum values are validated."""
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
        assert validate_json_output({"status": "ok"}, schema) == (True, "")
        assert validate_json_output({"status": "invalid"}, schema)[0] is False

    def test_min_length(self):
        """minLength validation for strings."""
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "minLength": 3},
            },
        }
        assert validate_json_output({"name": "abc"}, schema) == (True, "")
        assert validate_json_output({"name": "ab"}, schema)[0] is False

    def test_min_length_zero(self):
        """minLength=0 allows empty strings."""
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "minLength": 0},
            },
        }
        assert validate_json_output({"name": ""}, schema) == (True, "")

    def test_max_length(self):
        """maxLength validation for strings."""
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "maxLength": 5},
            },
        }
        assert validate_json_output({"name": "hello"}, schema) == (True, "")
        result = validate_json_output({"name": "too_long"}, schema)
        assert result[0] is False
        assert "max length" in result[1]

    def test_minimum(self):
        """minimum validation for numbers."""
        schema = {
            "type": "object",
            "required": ["age"],
            "properties": {
                "age": {"type": "integer", "minimum": 0},
            },
        }
        assert validate_json_output({"age": 0}, schema) == (True, "")
        assert validate_json_output({"age": -1}, schema)[0] is False

    def test_maximum(self):
        """maximum validation for numbers."""
        schema = {
            "type": "object",
            "required": ["age"],
            "properties": {
                "age": {"type": "integer", "maximum": 150},
            },
        }
        assert validate_json_output({"age": 150}, schema) == (True, "")
        assert validate_json_output({"age": 200}, schema)[0] is False

    def test_nested_object_validation(self):
        """Nested objects are validated recursively."""
        schema = {
            "type": "object",
            "required": ["meta"],
            "properties": {
                "meta": {
                    "type": "object",
                    "required": ["version"],
                    "properties": {
                        "version": {"type": "string"},
                    },
                },
            },
        }
        assert validate_json_output({"meta": {"version": "1.0"}}, schema) == (True, "")
        assert validate_json_output({"meta": {}}, schema)[0] is False

    def test_deeply_nested(self):
        """Validate deeply nested objects work correctly."""
        schema = {
            "type": "object",
            "required": ["outer"],
            "properties": {
                "outer": {
                    "type": "object",
                    "required": ["middle"],
                    "properties": {
                        "middle": {
                            "type": "object",
                            "required": ["inner"],
                            "properties": {
                                "inner": {"type": "number"},
                            },
                        },
                    },
                },
            },
        }
        assert validate_json_output({"outer": {"middle": {"inner": 42}}}, schema) == (
            True,
            "",
        )
        result = validate_json_output({"outer": {"middle": {}}}, schema)
        assert result[0] is False
        assert "missing required" in result[1]

    def test_empty_schema_object(self):
        """Empty properties dict is valid."""
        schema = {
            "type": "object",
            "properties": {},
        }
        assert validate_json_output({}, schema) == (True, "")
        assert validate_json_output({"anything": 1}, schema) == (True, "")

    def test_optional_field_missing(self):
        """Optional field (not in required) missing is OK."""
        schema = {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
            },
        }
        assert validate_json_output({"id": 1}, schema) == (True, "")

    def test_enum_with_numbers(self):
        """Enum works with non-string types too."""
        schema = {
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {
                    "enum": [200, 404, 500],
                },
            },
        }
        assert validate_json_output({"code": 200}, schema) == (True, "")
        assert validate_json_output({"code": 302}, schema)[0] is False

    def test_extra_field_ignored(self):
        """Extra fields not in schema are ignored."""
        schema = {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "integer"},
            },
        }
        assert validate_json_output({"id": 1, "extra": "ignored"}, schema) == (True, "")

    def test_minimum_on_float(self):
        """minimum works with float type numbers."""
        schema = {
            "type": "object",
            "required": ["temp"],
            "properties": {
                "temp": {"type": "number", "minimum": -10.0},
            },
        }
        assert validate_json_output({"temp": -5.0}, schema) == (True, "")
        assert validate_json_output({"temp": -15.0}, schema)[0] is False

    def test_maximum_on_float(self):
        """maximum works with float type numbers."""
        schema = {
            "type": "object",
            "required": ["temp"],
            "properties": {
                "temp": {"type": "number", "maximum": 100.5},
            },
        }
        assert validate_json_output({"temp": 100.5}, schema) == (True, "")
        assert validate_json_output({"temp": 101.0}, schema)[0] is False

    def test_bool_is_not_number(self):
        """Boolean should not pass as number."""
        schema = {
            "type": "object",
            "required": ["val"],
            "properties": {
                "val": {"type": "number"},
            },
        }
        result = validate_json_output({"val": True}, schema)
        assert result[0] is False


# ===================================================================
# load_json_schema
# ===================================================================


class TestLoadJsonSchema:
    """Tests for load_json_schema function."""

    def test_load_valid_schema(self):
        """Load a valid JSON schema file."""
        schema_data = '{"type": "object", "required": ["name"]}'
        with patch("builtins.open", mock_open(read_data=schema_data)):
            result = load_json_schema("/fake/schema.json")
        assert result is not None
        assert result["type"] == "object"
        assert result["required"] == ["name"]

    def test_file_not_found(self):
        """Non-existent file returns None."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = load_json_schema("/nonexistent/schema.json")
        assert result is None

    def test_invalid_json(self):
        """Invalid JSON file returns None."""
        with patch("builtins.open", mock_open(read_data="{invalid json}")):
            result = load_json_schema("/fake/bad.json")
        assert result is None

    def test_not_a_dict(self):
        """JSON that is not a dict returns None."""
        with patch("builtins.open", mock_open(read_data='["list", "not", "dict"]')):
            result = load_json_schema("/fake/list.json")
        assert result is None

    def test_empty_file(self):
        """Empty file returns None."""
        with patch("builtins.open", mock_open(read_data="")):
            result = load_json_schema("/fake/empty.json")
        assert result is None

    def test_large_schema(self):
        """Large schema files are handled."""
        props = {f"field_{i}": {"type": "string"} for i in range(100)}
        schema_data = (
            '{"type": "object", "properties": ' + str(props).replace("'", '"') + "}"
        )
        with patch("builtins.open", mock_open(read_data=schema_data)):
            result = load_json_schema("/fake/large.json")
        assert result is not None
        assert len(result["properties"]) == 100

    def test_nested_schema(self):
        """Load a schema with nested properties."""
        schema_data = '{"type": "object", "properties": {"nested": {"type": "object", "required": ["x"]}}}'
        with patch("builtins.open", mock_open(read_data=schema_data)):
            result = load_json_schema("/fake/nested.json")
        assert result is not None
        assert "properties" in result
