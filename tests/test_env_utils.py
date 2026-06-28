"""Tests for env_utils.py — env variable validation and discovery."""

from __future__ import annotations

from unittest.mock import patch


from hermes_loop.env_utils import (
    KNOWN_ENV_VARS,
    _find_closest_match,
    _mask_sensitive,
    check_env_file,
    format_validation_results,
    parse_env_vars_from_file,
    validate_env_vars,
)

# ---------------------------------------------------------------------------
# _find_closest_match tests
# ---------------------------------------------------------------------------


class TestFindClosestMatch:
    """Tests for _find_closest_match()."""

    def test_exact_match(self):
        """Exact match returns the same variable."""
        result = _find_closest_match("INFINITE_LOOP_GOAL", KNOWN_ENV_VARS)
        assert result == "INFINITE_LOOP_GOAL"

    def test_close_typo(self):
        """Close typo returns the best match above cutoff."""
        result = _find_closest_match("INFINITE_LOOP_GOAl", KNOWN_ENV_VARS)
        assert result == "INFINITE_LOOP_GOAL"

    def test_no_match_below_cutoff(self):
        """Very different suffix returns None."""
        result = _find_closest_match("INFINITE_LOOP_ZZZZZZZ", KNOWN_ENV_VARS)
        assert result is None

    def test_non_infinite_loop_prefix(self):
        """Variables without INFINITE_LOOP_ prefix return None."""
        result = _find_closest_match("SOME_OTHER_VAR", KNOWN_ENV_VARS)
        assert result is None

    def test_just_prefix_no_suffix(self):
        """Only prefix with no suffix returns None."""
        result = _find_closest_match("INFINITE_LOOP_", KNOWN_ENV_VARS)
        assert result is None

    def test_empty_string(self):
        """Empty string returns None."""
        result = _find_closest_match("", KNOWN_ENV_VARS)
        assert result is None

    def test_cutoff_threshold(self):
        """Matches below the cutoff are rejected."""
        # Very different suffix should fail
        result = _find_closest_match("INFINITE_LOOP_XXXXXXXXX", KNOWN_ENV_VARS)
        assert result is None

    def test_match_model_similar(self):
        """Similar suffix matches the right candidate."""
        result = _find_closest_match("INFINITE_LOOP_MODEl", KNOWN_ENV_VARS)
        assert result == "INFINITE_LOOP_MODEL"

    def test_match_workers_similar(self):
        """Similar 'WORKER' vs 'WORKERS' or 'WORKTREE' picks best."""
        result = _find_closest_match("INFINITE_LOOP_WORKER", KNOWN_ENV_VARS)
        assert result is not None
        # Should match WORKER_URL or WORKERS
        assert "WORKER" in result

    def test_empty_candidates_set(self):
        """Empty candidates set returns None."""
        result = _find_closest_match("INFINITE_LOOP_GOAL", set())
        assert result is None

    def test_typo_in_middle(self):
        """Typo in middle of suffix still matches."""
        result = _find_closest_match(
            "INFINITE_LOOP_CONVERGENCE_THRESHOLd", KNOWN_ENV_VARS
        )
        assert result == "INFINITE_LOOP_CONVERGENCE_THRESHOLD"


# ---------------------------------------------------------------------------
# parse_env_vars_from_file tests
# ---------------------------------------------------------------------------


class TestParseEnvVarsFromFile:
    """Tests for parse_env_vars_from_file()."""

    def test_parse_simple_file(self, tmp_path):
        """Parse a simple .env file with KEY=VALUE pairs."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "INFINITE_LOOP_GOAL=test_goal\n" "INFINITE_LOOP_MODEL=test_model\n"
        )
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert vars_found == {
            "INFINITE_LOOP_GOAL": "test_goal",
            "INFINITE_LOOP_MODEL": "test_model",
        }
        assert errors == []

    def test_skip_comments_and_blanks(self, tmp_path):
        """Comments and blank lines are skipped."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# This is a comment\n"
            "\n"
            "  \n"
            "INFINITE_LOOP_GOAL=hello\n"
            "# Another comment\n"
        )
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert vars_found == {"INFINITE_LOOP_GOAL": "hello"}
        assert errors == []

    def test_skip_structural_markers(self, tmp_path):
        """Lines starting with --- or ``` are skipped."""
        env_file = tmp_path / ".env"
        env_file.write_text("---\n" "INFINITE_LOOP_GOAL=hello\n" "```\n")
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert vars_found == {"INFINITE_LOOP_GOAL": "hello"}
        assert errors == []

    def test_quoted_values_stripped(self, tmp_path):
        """Values wrapped in single or double quotes have quotes stripped."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            'INFINITE_LOOP_GOAL="quoted_value"\n'
            "INFINITE_LOOP_MODEL='single_quoted'\n"
        )
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert vars_found["INFINITE_LOOP_GOAL"] == "quoted_value"
        assert vars_found["INFINITE_LOOP_MODEL"] == "single_quoted"
        assert errors == []

    def test_line_without_equals(self, tmp_path):
        """Lines without '=' are recorded as errors."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_LOOP_GOAL=hello\n" "INVALID_LINE\n")
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert "INVALID_LINE" not in vars_found
        assert len(errors) == 1
        assert "No '=' found" in errors[0]
        assert "2" in errors[0]  # line number

    def test_empty_key_is_error(self, tmp_path):
        """Line with '=' but empty key is recorded as error."""
        env_file = tmp_path / ".env"
        env_file.write_text("=value\n")
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert errors == ["Line 1: Empty key in '=value'"]
        assert vars_found == {}

    def test_file_not_found(self):
        """Non-existent file returns empty vars and error."""
        vars_found, errors = parse_env_vars_from_file("/nonexistent/.env")
        assert vars_found == {}
        assert len(errors) == 1
        assert "File not found" in errors[0]

    def test_empty_file(self, tmp_path):
        """Empty .env file returns empty vars and no errors."""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert vars_found == {}
        assert errors == []

    def test_value_with_spaces(self, tmp_path):
        """Values containing spaces are handled."""
        env_file = tmp_path / ".env"
        env_file.write_text('INFINITE_LOOP_GOAL="hello world"\n')
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert vars_found["INFINITE_LOOP_GOAL"] == "hello world"

    def test_multiple_equals_in_value_allowed(self, tmp_path):
        """Multiple '=' in the value are handled (partition on first '=')."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_LOOP_GOAL=a=b=c\n")
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert vars_found["INFINITE_LOOP_GOAL"] == "a=b=c"
        assert errors == []

    def test_whitespace_around_key_value(self, tmp_path):
        """Whitespace around key and value is stripped."""
        env_file = tmp_path / ".env"
        env_file.write_text("  INFINITE_LOOP_GOAL = hello  \n")
        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert vars_found["INFINITE_LOOP_GOAL"] == "hello"


# ---------------------------------------------------------------------------
# validate_env_vars tests
# ---------------------------------------------------------------------------


class TestValidateEnvVars:
    """Tests for validate_env_vars()."""

    def test_known_var(self):
        """Known INFINITE_LOOP_ var gets type 'ok'."""
        results = validate_env_vars({"INFINITE_LOOP_GOAL": "test"})
        ok_results = [r for r in results if r["type"] == "ok"]
        assert len(ok_results) == 1
        assert ok_results[0]["key"] == "INFINITE_LOOP_GOAL"
        assert "Recognized" in ok_results[0]["message"]

    def test_unknown_var(self):
        """Unknown INFINITE_LOOP_ var gets type 'unknown'."""
        results = validate_env_vars({"INFINITE_LOOP_NONEXISTENT": "test"})
        unknown_results = [r for r in results if r["type"] == "unknown"]
        assert len(unknown_results) == 1
        assert unknown_results[0]["key"] == "INFINITE_LOOP_NONEXISTENT"

    def test_typo_var(self):
        """Typo var gets type 'typo' with suggestion."""
        results = validate_env_vars({"INFINITE_LOOP_GOAl": "test"})
        typo_results = [r for r in results if r["type"] == "typo"]
        assert len(typo_results) == 1
        assert typo_results[0]["key"] == "INFINITE_LOOP_GOAl"
        assert typo_results[0]["suggestion"] == "INFINITE_LOOP_GOAL"

    def test_non_infinite_loop_var(self):
        """Non-INFINITE_LOOP_ var gets type 'warning'."""
        results = validate_env_vars({"MY_CUSTOM_VAR": "test"})
        warning_results = [r for r in results if r["type"] == "warning"]
        assert len(warning_results) == 1
        assert "Non-INFINITE_LOOP_" in warning_results[0]["message"]

    def test_known_var_masked_value(self):
        """Known var with TOKEN in name has value masked."""
        results = validate_env_vars({"INFINITE_LOOP_NOTIFY_PUSHBULLET": "abc123token"})
        ok_results = [r for r in results if r["type"] == "ok"]
        assert len(ok_results) == 1
        # PUSHBULLET key triggers masking; "abc123token" (10 chars) → "abc****ken"
        assert "****" in ok_results[0]["message"]

    def test_missing_common_var(self):
        """Missing common required var (GOAL) reports 'missing' type."""
        results = validate_env_vars({})
        missing_results = [r for r in results if r["type"] == "missing"]
        assert len(missing_results) == 1
        assert missing_results[0]["key"] == "INFINITE_LOOP_GOAL"

    def test_multiple_vars_mixed(self):
        """Multiple vars with various statuses."""
        results = validate_env_vars(
            {
                "INFINITE_LOOP_GOAL": "test",
                "INFINITE_LOOP_ZZZZ": "bad",
                "CUSTOM_VAR": "custom",
            }
        )
        types = [r["type"] for r in results]
        assert "ok" in types
        assert "unknown" in types
        assert "warning" in types

    def test_sorted_by_key(self):
        """Results are sorted by key name."""
        results = validate_env_vars(
            {
                "INFINITE_LOOP_Z": "z",
                "INFINITE_LOOP_A": "a",
            }
        )
        keys = [r["key"] for r in results if r["type"] in ("ok", "unknown")]
        assert keys == sorted(keys)

    def test_empty_vars_no_results(self):
        """Empty vars dict triggers missing common var but no others."""
        results = validate_env_vars({})
        # Only missing results
        assert all(r["type"] == "missing" for r in results)


# ---------------------------------------------------------------------------
# _mask_sensitive tests
# ---------------------------------------------------------------------------


class TestMaskSensitive:
    """Tests for _mask_sensitive()."""

    def test_token_in_name(self):
        """Key with TOKEN gets masked."""
        result = _mask_sensitive("MY_TOKEN", "abcdef123456")
        assert result != "abcdef123456"
        assert "****" in result

    def test_key_in_name(self):
        """Key with KEY gets masked."""
        result = _mask_sensitive("API_KEY", "mysecretkey123")
        assert "****" in result

    def test_secret_in_name(self):
        """Key with SECRET gets masked."""
        result = _mask_sensitive("MY_SECRET", "supersecret")
        assert "****" in result

    def test_password_in_name(self):
        """Key with PASSWORD gets masked."""
        result = _mask_sensitive("DB_PASSWORD", "hunter2")
        assert "****" in result

    def test_pushbullet_in_name(self):
        """Key with PUSHBULLET gets masked."""
        result = _mask_sensitive("INFINITE_LOOP_NOTIFY_PUSHBULLET", "abc123")
        assert "****" in result

    def test_short_value_masked(self):
        """Short values (<= 4 chars) become '****'."""
        result = _mask_sensitive("MY_TOKEN", "ab")
        assert result == "****"
        result = _mask_sensitive("MY_TOKEN", "abcd")
        assert result == "****"

    def test_value_length_5_to_8_chars(self):
        """Values 5-8 chars show first 2 + **** + last 2."""
        result = _mask_sensitive("MY_TOKEN", "abcdef")
        assert result == "ab****ef"
        result = _mask_sensitive("MY_TOKEN", "abcdefgh")
        assert result == "ab****gh"

    def test_value_longer_than_8(self):
        """Values >8 chars show first 3 + **** + last 3."""
        result = _mask_sensitive("MY_TOKEN", "abcdefghij")
        assert result == "abc****hij"
        result = _mask_sensitive("MY_TOKEN", "abcdefghijk")
        assert result == "abc****ijk"

    def test_non_sensitive_returned_as_is(self):
        """Non-sensitive key returns value unchanged."""
        result = _mask_sensitive("INFINITE_LOOP_GOAL", "test_goal")
        assert result == "test_goal"

    def test_empty_value_sensitive(self):
        """Empty value for sensitive key returns '****'."""
        result = _mask_sensitive("MY_TOKEN", "")
        assert result == "****"

    def test_case_insensitive_matching(self):
        """Matching against key.upper() is case-insensitive."""
        result = _mask_sensitive("my_token", "secret123")
        assert "****" in result

    def test_value_exactly_4_chars_for_long_rule(self):
        """Value length 5-8 uses 2+2 masking."""
        result = _mask_sensitive("MY_TOKEN", "12345678")
        assert result == "12****78"


# ---------------------------------------------------------------------------
# format_validation_results tests
# ---------------------------------------------------------------------------


class TestFormatValidationResults:
    """Tests for format_validation_results()."""

    def test_basic_no_colorize(self):
        """Basic formatting without colorize."""
        results = [
            {
                "type": "ok",
                "key": "INFINITE_LOOP_GOAL",
                "message": "Recognized",
                "suggestion": None,
            },
        ]
        output = format_validation_results(results, colorize=False)
        assert "[OK]" in output
        assert "INFINITE_LOOP_GOAL" in output
        assert "Recognized" in output
        assert "1 recognized" in output
        assert "total: 1 vars" in output

    def test_with_suggestion(self):
        """Suggestion is included in output."""
        results = [
            {
                "type": "typo",
                "key": "INFINITE_LOOP_GOAl",
                "message": "Unknown variable — did you mean 'INFINITE_LOOP_GOAL'?",
                "suggestion": "INFINITE_LOOP_GOAL",
            },
        ]
        output = format_validation_results(results, colorize=False)
        assert "[TYPO]" in output
        assert "→" in output
        assert "INFINITE_LOOP_GOAL" in output

    def test_missing_type(self):
        """Missing type shows [MISSING]."""
        results = [
            {
                "type": "missing",
                "key": "INFINITE_LOOP_GOAL",
                "message": "Not set",
                "suggestion": "goal",
            },
        ]
        output = format_validation_results(results, colorize=False)
        assert "[MISSING]" in output
        assert "goal" in output

    def test_deprecated_type(self):
        """Deprecated type shows [DEPRECATED]."""
        results = [
            {
                "type": "deprecated",
                "key": "INFINITE_LOOP_OLD_VAR",
                "message": "Deprecated — variable is no longer used",
                "suggestion": None,
            },
        ]
        output = format_validation_results(results, colorize=False)
        assert "[DEPRECATED]" in output

    def test_unknown_type(self):
        """Unknown type shows [UNKNOWN]."""
        results = [
            {
                "type": "unknown",
                "key": "INFINITE_LOOP_ZZZZ",
                "message": "Unknown variable",
                "suggestion": None,
            },
        ]
        output = format_validation_results(results, colorize=False)
        assert "[UNKNOWN]" in output

    def test_warning_type(self):
        """Warning type shows [WARN]."""
        results = [
            {
                "type": "warning",
                "key": "MY_VAR",
                "message": "Not consumed by daemon",
                "suggestion": None,
            },
        ]
        output = format_validation_results(results, colorize=False)
        assert "[WARNING]" in output

    def test_mixed_results_summary(self):
        """Summary shows counts of recognized + problems."""
        results = [
            {"type": "ok", "key": "A", "message": "ok", "suggestion": None},
            {"type": "ok", "key": "B", "message": "ok", "suggestion": None},
            {"type": "typo", "key": "C", "message": "typo", "suggestion": "A"},
            {"type": "unknown", "key": "D", "message": "unknown", "suggestion": None},
            {"type": "warning", "key": "E", "message": "warn", "suggestion": None},
            {"type": "missing", "key": "F", "message": "missing", "suggestion": None},
        ]
        output = format_validation_results(results, colorize=False)
        assert "2 recognized" in output
        assert "4 issues" in output
        assert "1 typo" in output
        assert "1 unknown" in output
        assert "1 warnings" in output
        assert "1 missing" in output
        assert "total: 6 vars" in output

    def test_single_issue_uses_singular(self):
        """Single issue uses '1 issue' not '1 issues'."""
        results = [
            {"type": "ok", "key": "A", "message": "ok", "suggestion": None},
            {"type": "typo", "key": "B", "message": "typo", "suggestion": "A"},
        ]
        output = format_validation_results(results, colorize=False)
        assert "1 issue" in output

    def test_unknown_type_fallback(self):
        """Unknown type value uses fallback formatting."""
        results = [
            {
                "type": "custom_type",
                "key": "X",
                "message": "custom",
                "suggestion": None,
            },
        ]
        output = format_validation_results(results, colorize=False)
        assert "[CUSTOM_TYPE]" in output

    def test_colorize_calls_colorizer(self):
        """With colorize=True, colorizer methods are invoked."""
        # colorizer is imported inside format_validation_results via from .color_utils import colorizer
        # We patch the color_utils module-level instance
        with (
            patch("hermes_loop.color_utils.Colorizer.tag_ok", return_value="[OK]"),
            patch("hermes_loop.color_utils.Colorizer.tag_warn", return_value="[WARN]"),
            patch(
                "hermes_loop.color_utils.Colorizer.header",
                return_value="Environment Variable Validation:",
            ),
        ):

            results = [
                {
                    "type": "ok",
                    "key": "INFINITE_LOOP_GOAL",
                    "message": "Recognized",
                    "suggestion": None,
                },
                {
                    "type": "typo",
                    "key": "INFINITE_LOOP_GOAl",
                    "message": "typo",
                    "suggestion": "GOAL",
                },
            ]
            output = format_validation_results(results, colorize=True)

            # The output was produced with the mocked methods
            assert "[OK]" in output


# ---------------------------------------------------------------------------
# check_env_file tests
# ---------------------------------------------------------------------------


class TestCheckEnvFile:
    """Tests for check_env_file()."""

    # NOTE: check_env_file imports _log locally inside the function body
    # (from .file_utils import _log), so module-level patches of
    # hermes_loop.env_utils._log won't work. Instead we patch
    # hermes_loop.file_utils._log to capture log messages.

    def test_no_env_file_provided_uses_cwd(self, tmp_path):
        """No path defaults to cwd/.env."""
        with patch("hermes_loop.env_utils.os.getcwd", return_value=str(tmp_path)):
            env_file = tmp_path / ".env"
            env_file.write_text("INFINITE_LOOP_GOAL=test\n")

            with patch("hermes_loop.env_utils.print") as mock_print:
                result = check_env_file()

            assert result == 0  # no issues
            mock_print.assert_called_once()

    def test_file_with_parse_errors_logs_warnings(self, tmp_path):
        """Parse errors are logged via _log."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_LOOP_GOAL=test\nINVALID_LINE\n")

        with patch("hermes_loop.env_utils.print"):
            with patch("hermes_loop.file_utils._log") as mock_log:
                result = check_env_file(str(env_file))

        assert result == 0  # parse errors don't cause non-zero by themselves
        mock_log.assert_any_call("[WARN] Parse errors in .env file:")

    def test_empty_env_file_info_logged(self, tmp_path):
        """Empty env file logs info and returns 0."""
        env_file = tmp_path / ".env"
        env_file.write_text("")

        with patch("hermes_loop.file_utils._log") as mock_log:
            result = check_env_file(str(env_file))
        assert result == 0
        mock_log.assert_any_call(
            f"[INFO] No INFINITE_LOOP_* variables found in {env_file}"
        )

    def test_issues_cause_return_1(self, tmp_path):
        """Unknown/typo/deprecated/warning vars cause return code 1."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_LOOP_ZZZZZ=bad\n")

        with patch("hermes_loop.env_utils.print"):
            result = check_env_file(str(env_file))

        assert result == 1

    def test_only_ok_and_missing_returns_0(self, tmp_path):
        """Only 'ok' and 'missing' types still return 0."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_LOOP_GOAL=test\n")

        with patch("hermes_loop.env_utils.print"):
            result = check_env_file(str(env_file))

        assert result == 0

    def test_file_not_found_returns_0(self, tmp_path):
        """Non-existent env file returns 0 (handled by parse function)."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            result = check_env_file("/nonexistent/.env")
        assert result == 0
        mock_log.assert_called()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_flow_clean_env(self, tmp_path):
        """Full flow: parse → validate → format with a clean .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "INFINITE_LOOP_GOAL=build a rocket\n"
            "INFINITE_LOOP_MODEL=gpt-4\n"
            "INFINITE_LOOP_MAX_ITERATIONS=10\n"
        )

        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert errors == []
        assert len(vars_found) == 3

        results = validate_env_vars(vars_found)
        ok_count = sum(1 for r in results if r["type"] == "ok")
        assert ok_count == 3

        output = format_validation_results(results, colorize=False)
        assert "3 recognized" in output
        assert "total: 3 vars" in output
        assert "[OK]" in output

    def test_full_flow_with_issues(self, tmp_path):
        """Full flow with typo, warning, and missing vars."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "INFINITE_LOOP_GOAl=typo\n"
            "MY_CUSTOM_VAR=hello\n"
            "INFINITE_LOOP_MODEL=gpt-4\n"
        )

        vars_found, errors = parse_env_vars_from_file(str(env_file))
        assert errors == []

        results = validate_env_vars(vars_found)
        types = [r["type"] for r in results]

        assert "ok" in types
        assert "typo" in types
        assert "warning" in types
        assert "missing" in types  # GOAL not found (only GOAl)

        output = format_validation_results(results, colorize=False)
        assert "[TYPO]" in output
        assert "[WARNING]" in output
        assert "[MISSING]" in output
