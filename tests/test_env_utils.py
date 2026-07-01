"""Tests for omp_loop.env_utils — environment variable validation."""

from unittest.mock import patch

import pytest

from omp_loop.env_utils import (
    KNOWN_ENV_VARS,
    _decode_env_var_value,
    _find_closest_match,
    check_env_file,
    format_validation_results,
    parse_env_vars_from_file,
    validate_env_vars,
)


class TestFindClosestMatch:
    def test_finds_close_match(self):
        """_find_closest_match finds close matches for typos."""
        result = _find_closest_match("INFINITE_LOOP_GOAL_TYPO", KNOWN_ENV_VARS)
        assert result is not None
        assert "GOAL" in result


class TestParseEnvVarsFromFile:
    def test_parses_valid_content(self, tmp_path):
        """parse_env_vars_from_file extracts INFINITE_LOOP_* variables (and any var)."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_LOOP_GOAL=test\nINFINITE_LOOP_TIMEOUT=300\nPATH=/usr/bin\nSOME_OTHER=value\n")
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert "INFINITE_LOOP_GOAL" in vars_found
        assert "INFINITE_LOOP_TIMEOUT" in vars_found
        # Function returns ALL env vars, not just INFINITE_LOOP_*
        assert "PATH" in vars_found
        assert errors == []

    def test_empty_file(self, tmp_path):
        """parse_env_vars_from_file with empty file returns empty results."""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert vars_found == {}
        assert errors == []

    def test_parse_errors(self, tmp_path):
        """parse_env_vars_from_file reports malformed lines."""
        env_file = tmp_path / ".env"
        env_file.write_text("INVALID_LINE_NO_EQUALS\nINFINITE_LOOP_GOAL=ok\n")
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert "INFINITE_LOOP_GOAL" in vars_found
        assert len(errors) > 0

    def test_file_not_found(self, tmp_path):
        """parse_env_vars_from_file returns empty when file doesn't exist."""
        vars_found, errors = parse_env_vars_from_file(str(tmp_path / "nonexistent.env"))
        assert vars_found == {}
        assert errors == []

    def test_quoted_values(self, tmp_path):
        """parse_env_vars_from_file handles quoted values."""
        env_file = tmp_path / ".env"
        env_file.write_text('INFINITE_LOOP_GOAL="my goal"\nINFINITE_LOOP_CONTEXT="multi\nline"\n')
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert "INFINITE_LOOP_GOAL" in vars_found
        assert "INFINITE_LOOP_CONTEXT" in vars_found


class TestValidateEnvVars:
    def test_known_vars_return_ok(self):
        """validate_env_vars with known vars returns ok type."""
        result = validate_env_vars({"INFINITE_LOOP_GOAL": "test", "INFINITE_LOOP_SESSION_TIMEOUT": "300"})
        for r in result:
            assert r["type"] == "ok", f"Got {r['type']} for {r['key']}: {r.get('message', '')}"

    def test_typo_detected(self):
        """validate_env_vars detects typos."""
        result = validate_env_vars({"INFINITE_LOOP_GOAL_TYPO": "test"})
        has_typo = any(r["type"] == "typo" for r in result)
        assert has_typo

    def test_warning_for_non_infinite_loop_vars(self):
        """validate_env_vars returns 'warning' for non-INFINITE_LOOP_ vars."""
        result = validate_env_vars({"ZZZ_RANDOM_VAR": "test"})
        has_warning = any(r["type"] == "warning" for r in result)
        assert has_warning

    def test_mixed_results(self):
        """validate_env_vars handles mixed known/typo."""
        result = validate_env_vars({"INFINITE_LOOP_GOAL": "test", "INFINITE_LOOP_GOAL_TYPO": "test"})
        types = {r["type"] for r in result}
        assert "ok" in types
        assert "typo" in types

    def test_empty_input_has_missing_required(self):
        """validate_env_vars with empty input has a 'missing' entry for INFINITE_LOOP_GOAL."""
        result = validate_env_vars({})
        assert len(result) > 0
        # INFINITE_LOOP_GOAL is reported as 'missing'
        missing_goal = any(r.get("key") == "INFINITE_LOOP_GOAL" and r.get("type") == "missing" for r in result)
        assert missing_goal


class TestFormatValidationResults:
    def test_contains_keys(self):
        """format_validation_results output contains variable keys."""
        results = [
            {"key": "INFINITE_LOOP_GOAL", "type": "ok", "message": "recognized", "suggestion": ""},
            {"key": "UNKNOWN_VAR", "type": "unknown", "message": "not recognized", "suggestion": ""},
        ]
        output = format_validation_results(results, colorize=False)
        assert "INFINITE_LOOP_GOAL" in output
        assert "UNKNOWN_VAR" in output
        assert "recognized" in output

    def test_summary_line(self):
        """format_validation_results includes a summary."""
        results = [{"key": "VAR", "type": "ok", "message": "ok", "suggestion": ""}]
        output = format_validation_results(results, colorize=False)
        assert "1 recognized" in output

    def test_typo_prefix(self):
        """format_validation_results shows [TYPOS] for typo results."""
        results = [{"key": "VAR", "type": "typo", "message": "did you mean", "suggestion": "OTHER"}]
        output = format_validation_results(results, colorize=False)
        assert "typo" in output.lower() or "TYPOS" in output


class TestCheckEnvFile:
    def test_missing_file_returns_zero(self):
        """check_env_file with missing file returns 0."""
        with patch("os.path.isfile", return_value=False):
            result = check_env_file("/nonexistent/.env")
        assert result == 0

    def test_no_infinite_loop_vars_returns_zero(self):
        """check_env_file with no INFINITE_LOOP_* vars returns 0."""
        with (
            patch("os.path.isfile", return_value=True),
            patch("omp_loop.env_utils.parse_env_vars_from_file", return_value=({}, [])),
        ):
            result = check_env_file("/tmp/.env")
        assert result == 0

    def test_issues_return_one(self):
        """check_env_file with issues returns 1."""
        vars_found = {"UNKNOWN_VAR": "test"}
        with (
            patch("os.path.isfile", return_value=True),
            patch("omp_loop.env_utils.parse_env_vars_from_file", return_value=(vars_found, [])),
        ):
            result = check_env_file("/tmp/.env")
        assert result == 1

    def test_parse_errors_logged(self):
        """check_env_file logs parse errors."""
        vars_found = {"INFINITE_LOOP_GOAL": "test"}
        with (
            patch("os.path.isfile", return_value=True),
            patch("omp_loop.env_utils.parse_env_vars_from_file", return_value=(vars_found, ["line 1: bad format"])),
            patch("omp_loop.env_utils._log") as mock_log,
        ):
            check_env_file("/tmp/.env")
        assert mock_log.call_count > 0


class TestDecodeEnvVarValue:
    """Parametrized tests for ``_decode_env_var_value``."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            # Truthy booleans
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            # Falsy booleans
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("off", False),
        ],
    )
    def test_booleans(self, raw, expected):
        """_decode_env_var_value decodes boolean variants."""
        assert _decode_env_var_value(raw) is expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("-1", -1),
            ("2147483647", 2147483647),
            ("999999999999999", 999999999999999),
            ("42", 42),
            ("0x1A", 26),   # hex
            ("0o10", 8),    # octal
            ("0b101", 5),   # binary
        ],
    )
    def test_integers(self, raw, expected):
        """_decode_env_var_value decodes integer strings."""
        result = _decode_env_var_value(raw)
        assert result == expected
        assert isinstance(result, int)

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("3.14", 3.14),
            ("0.0", 0.0),
            ("-2.5", -2.5),
            ("1e10", 1e10),
            ("inf", float("inf")),
            ("-inf", float("-inf")),
            ("nan", float("nan")),
        ],
    )
    def test_floats(self, raw, expected):
        """_decode_env_var_value decodes float strings."""
        result = _decode_env_var_value(raw)
        assert isinstance(result, float)
        if raw == "nan":
            assert result != result  # nan is never equal to itself
        else:
            assert result == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ('''b"escaped\\nnewline"''', "escaped\nnewline"),
            ('''b"hello"''', "hello"),
            ('''b"tab\\there"''', "tab\there"),
            ('''b"carriage\\rreturn"''', "carriage\rreturn"),
            ('''b"back\\slash"''', 'back\\slash'),
            ('''b' "nested" ' ''', ' "nested" '),
        ],
    )
    def test_bytes_literals(self, raw, expected):
        """_decode_env_var_value decodes Python bytes literals."""
        result = _decode_env_var_value(raw)
        assert result == expected
        assert isinstance(result, str)

    @pytest.mark.parametrize(
        "raw",
        [None, "", "   ", "\t\n", "\r\n"],
    )
    def test_empty_and_none(self, raw):
        """_decode_env_var_value returns None for empty/None inputs."""
        assert _decode_env_var_value(raw) is None

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("  true  ", True),
            ("  false  ", False),
            ("  42  ", 42),
            ("  3.14  ", 3.14),
            ("  hello  ", "hello"),
        ],
    )
    def test_whitespace_handling(self, raw, expected):
        """_decode_env_var_value strips whitespace before decoding."""
        assert _decode_env_var_value(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("hello world", "hello world"),
            ("not-a-number", "not-a-number"),
            ("true-ish", "true-ish"),
            ("b'missing_quote", "b'missing_quote"),  # incomplete bytes literal
            ("""{ "not": "json" }""", """{ "not": "json" }"""),  # not JSON
            ("", None),  # empty -> None, NOT the empty string
        ],
    )
    def test_malformed_and_fallback(self, raw, expected):
        """_decode_env_var_value falls back to stripped string for unrecognised input."""
        assert _decode_env_var_value(raw) == expected
