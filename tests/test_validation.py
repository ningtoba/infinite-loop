"""Tests for omp_loop/validation.py — JSON Schema validation."""

from omp_loop.validation import load_json_schema, validate_output


class TestValidateOutput:
    """validate_output() — validate JSON output against a JSON Schema."""

    def test_no_schema_returns_true(self):
        """When schema is None or empty, validation passes."""
        assert validate_output("any text", None) == (True, [])
        assert validate_output("any text", {}) == (True, [])

    def test_valid_json_matches_schema(self):
        """Valid JSON matching schema returns (True, [])."""
        schema = {
            "required": ["result"],
            "properties": {"result": {"type": "string"}},
        }
        valid, errors = validate_output('{"result": "success"}', schema)
        assert valid is True
        assert errors == []

    def test_valid_json_multiple_fields(self):
        """All specified property types pass validation."""
        schema = {
            "required": ["name", "count"],
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "active": {"type": "boolean"},
                "score": {"type": "number"},
                "tags": {"type": "array"},
                "meta": {"type": "object"},
            },
        }
        output = '{"name": "test", "count": 42, "active": true, "score": 3.14, "tags": ["a"], "meta": {"k": "v"}}'
        valid, errors = validate_output(output, schema)
        assert valid is True
        assert errors == []

    def test_missing_required_key(self):
        """Missing required key produces error."""
        schema = {
            "required": ["result"],
            "properties": {"result": {"type": "string"}},
        }
        valid, errors = validate_output('{"other": "data"}', schema)
        assert valid is False
        assert any("Missing required key: result" in e for e in errors)

    def test_wrong_type_returns_error(self):
        """Type mismatch produces error."""
        schema = {
            "properties": {"count": {"type": "integer"}},
        }
        valid, errors = validate_output('{"count": "not_an_integer"}', schema)
        assert valid is False
        assert any("should be integer" in e for e in errors)

    def test_non_json_output_skips_validation(self):
        """Plain text output that isn't JSON skips validation."""
        schema = {
            "required": ["result"],
            "properties": {"result": {"type": "string"}},
        }
        valid, errors = validate_output("This is plain text output from omp", schema)
        assert valid is True
        assert errors == []

    def test_json_extracted_from_text(self):
        """JSON block extracted from surrounding text is validated."""
        schema = {
            "required": ["result"],
            "properties": {"result": {"type": "string"}},
        }
        output = "Here is the result:\n{\"result\": \"found it\"}\nDone."
        valid, errors = validate_output(output, schema)
        assert valid is True
        assert errors == []

    def test_multiple_required_keys_all_missing(self):
        """Multiple missing required keys are all reported."""
        schema = {
            "required": ["key1", "key2", "key3"],
            "properties": {},
        }
        valid, errors = validate_output('{"irrelevant": 1}', schema)
        assert valid is False
        assert len(errors) == 3

    def test_type_validation_skips_absent_optional_keys(self):
        """Optional keys not in output are not flagged as type errors."""
        schema = {
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        valid, errors = validate_output('{"name": "alice"}', schema)
        assert valid is True
        assert errors == []

    def test_unknown_property_types_not_checked(self):
        """Unknown type specifiers are skipped without error."""
        schema = {
            "properties": {
                "data": {"type": "unknown_type"},
            },
        }
        valid, errors = validate_output('{"data": "anything"}', schema)
        assert valid is True
        assert errors == []

    def test_schema_with_no_properties(self):
        """Schema with no properties validates any JSON."""
        schema = {"required": []}
        valid, errors = validate_output('{"anything": "goes"}', schema)
        assert valid is True
        assert errors == []


class TestLoadJsonSchema:
    """load_json_schema() — load a JSON Schema from a file path."""

    def test_loads_valid_schema(self, tmp_path):
        """Returns parsed schema dict for valid JSON file."""
        schema_file = tmp_path / "schema.json"
        schema_file.write_text('{"type": "object", "required": ["result"]}')
        schema = load_json_schema(str(schema_file))
        assert schema == {"type": "object", "required": ["result"]}

    def test_nonexistent_file(self, tmp_path):
        """Returns None for missing file (no exception)."""
        schema = load_json_schema(str(tmp_path / "missing.json"))
        assert schema is None

    def test_invalid_json_file(self, tmp_path):
        """Returns None for malformed JSON (no exception)."""
        schema_file = tmp_path / "bad.json"
        schema_file.write_text("not json")
        schema = load_json_schema(str(schema_file))
        assert schema is None

    def test_non_dict_json(self, tmp_path):
        """Returns None when file is valid JSON but not an object."""
        schema_file = tmp_path / "arr.json"
        schema_file.write_text("[1, 2, 3]")
        schema = load_json_schema(str(schema_file))
        assert schema is None
