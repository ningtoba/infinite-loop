"""Tests for pi_loop.env_utils — environment variable validation."""

from unittest.mock import patch

from pi_loop.env_utils import (
    KNOWN_ENV_VARS,
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
            patch("pi_loop.env_utils.parse_env_vars_from_file", return_value=({}, [])),
        ):
            result = check_env_file("/tmp/.env")
        assert result == 0

    def test_issues_return_one(self):
        """check_env_file with issues returns 1."""
        vars_found = {"UNKNOWN_VAR": "test"}
        with (
            patch("os.path.isfile", return_value=True),
            patch("pi_loop.env_utils.parse_env_vars_from_file", return_value=(vars_found, [])),
        ):
            result = check_env_file("/tmp/.env")
        assert result == 1

    def test_parse_errors_logged(self):
        """check_env_file logs parse errors."""
        vars_found = {"INFINITE_LOOP_GOAL": "test"}
        with (
            patch("os.path.isfile", return_value=True),
            patch("pi_loop.env_utils.parse_env_vars_from_file", return_value=(vars_found, ["line 1: bad format"])),
            patch("pi_loop.env_utils._log") as mock_log,
        ):
            check_env_file("/tmp/.env")
        assert mock_log.call_count > 0
