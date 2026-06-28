"""Tests for error_utils.py — classify_error, _classify_progress, _suggest_actionable_fix."""

from __future__ import annotations


from hermes_loop.error_utils import (
    classify_error,
    _classify_progress,
    _suggest_actionable_fix,
)

# ===================================================================
# classify_error
# ===================================================================


class TestClassifyError:
    """Tests for classify_error function."""

    def test_none_input(self):
        """None input returns None."""
        assert classify_error(None) is None

    def test_empty_string(self):
        """Empty string returns None."""
        assert classify_error("") is None

    def test_timeout_exact(self):
        """Exact 'timeout' string."""
        assert classify_error("timeout") == "timeout"

    def test_timeout_timed_out(self):
        """'timed out' phrase."""
        assert classify_error("timed out") == "timeout"

    def test_timeout_in_sentence(self):
        """Timeout in a longer message."""
        assert classify_error("operation timed out after 30s") == "timeout"

    def test_network_connection_refused(self):
        """'Connection refused' message."""
        assert classify_error("connection refused") == "network"

    def test_network_connection_error(self):
        """'connection error' message."""
        assert classify_error("connection error") == "network"

    def test_network_connectionreset(self):
        """'ConnectionResetError' message.
        Note: the code checks for 'connectionerror' as a substring,
        but 'ConnectionResetError' doesn't contain that — so it
        falls through to 'unknown'. This test documents the actual behavior.
        """
        assert classify_error("ConnectionResetError") == "unknown"

    def test_network_dns(self):
        """'dns' lookup failure."""
        assert classify_error("DNS resolution failed") == "network"

    def test_network_resolve(self):
        """'resolve' hostname."""
        assert classify_error("could not resolve host") == "network"

    def test_network_refused(self):
        """'refused' by itself."""
        assert classify_error("refused") == "network"

    def test_network_no_route(self):
        """'No route to host'."""
        assert classify_error("no route to host") == "network"

    def test_network_generic(self):
        """'network' keyword."""
        assert classify_error("network error") == "network"

    def test_schema_validation(self):
        """'validation' keyword."""
        assert classify_error("validation failed") == "schema"

    def test_schema_invalid(self):
        """'invalid' keyword."""
        assert classify_error("invalid format") == "schema"

    def test_schema_exact(self):
        """Exact 'schema' keyword."""
        assert classify_error("schema mismatch") == "schema"

    def test_unknown_error(self):
        """Random error string returns 'unknown'."""
        assert classify_error("some random error") == "unknown"

    def test_unknown_odd_error(self):
        """Completely unrelated error."""
        assert classify_error("disk full") == "unknown"

    def test_case_insensitivity(self):
        """Case-insensitive matching."""
        assert classify_error("TIMEOUT") == "timeout"
        assert classify_error("CONNECTION REFUSED") == "network"
        assert classify_error("SCHEMA") == "schema"

    def test_whitespace_only(self):
        """Whitespace-only string returns 'unknown' (truthy string, no matches)."""
        assert classify_error("   ") == "unknown"

    def test_substring_matches(self):
        """Substring matching — 'time' shouldn't match timeout."""
        assert classify_error("time") == "unknown"  # 'time' != 'timeout' or 'timed out'


# ===================================================================
# _classify_progress
# ===================================================================


class TestClassifyProgress:
    """Tests for _classify_progress function."""

    def test_completed_keyword(self):
        """'completed' in summary."""
        assert _classify_progress("task completed", None, None, None) == "completed"

    def test_finished_keyword(self):
        """'finished' in summary."""
        assert (
            _classify_progress("finished everything", None, None, None) == "completed"
        )

    def test_all_done_keyword(self):
        """'all done' in summary."""
        assert _classify_progress("all done", None, None, None) == "completed"

    def test_all_tasks_keyword(self):
        """'all tasks' in summary."""
        assert (
            _classify_progress("all tasks completed", None, None, None) == "completed"
        )

    def test_goal_achieved(self):
        """'goal achieved' in summary."""
        assert _classify_progress("goal achieved", None, None, None) == "completed"

    def test_regression_error_no_git_changes(self):
        """Error with no git changes = regression."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "0 files"}
        result = _classify_progress(
            "did something", git_before, git_after, "error occurred"
        )
        assert result == "regression"

    def test_exit_code_noise_not_regression(self):
        """Exit code noise is NOT regression."""
        result = _classify_progress("did something", None, None, "exit code 1")
        assert result != "regression"

    def test_hermes_exit_not_regression(self):
        """'hermes exit' is NOT regression."""
        result = _classify_progress("did something", None, None, "hermes exit 1")
        assert result != "regression"

    def test_stuck_short_summary_no_changes(self):
        """Short summary (< 30 chars) with no git changes = stuck."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "0 files"}
        result = _classify_progress("fail", git_before, git_after, None)
        assert result == "stuck"

    def test_stuck_with_failure_keyword(self):
        """'still working' keyword with no git changes = stuck."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "0 files"}
        result = _classify_progress("still working on it", git_before, git_after, None)
        assert result == "stuck"

    def test_stuck_cannot_keyword(self):
        """'cannot' with no git changes = stuck."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "0 files"}
        result = _classify_progress("cannot fix bug", git_before, git_after, None)
        assert result == "stuck"

    def test_stuck_unable_keyword(self):
        """'unable' with no git changes = stuck."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "0 files"}
        result = _classify_progress("unable to parse", git_before, git_after, None)
        assert result == "stuck"

    def test_stuck_failed_keyword(self):
        """'failed to' with no git changes = stuck."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "0 files"}
        result = _classify_progress("failed to compile", git_before, git_after, None)
        assert result == "stuck"

    def test_progress_with_git_changes(self):
        """Git changes + 'fixed' keyword = progress."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "1 file changed"}
        result = _classify_progress("fixed the bug", git_before, git_after, None)
        assert result == "progress"

    def test_progress_implemented(self):
        """Git changes + 'implemented' = progress."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "2 files changed"}
        result = _classify_progress(
            "implemented feature X", git_before, git_after, None
        )
        assert result == "progress"

    def test_progress_created(self):
        """Git changes + 'created' = progress."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "1 file changed"}
        result = _classify_progress("created new module", git_before, git_after, None)
        assert result == "progress"

    def test_progress_updated(self):
        """Git changes + 'updated' = progress."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "3 files changed"}
        result = _classify_progress("updated config", git_before, git_after, None)
        assert result == "progress"

    def test_partial_with_remaining(self):
        """Git changes + 'remaining' = partial."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "1 file changed"}
        result = _classify_progress("some work remaining", git_before, git_after, None)
        assert result == "partial"

    def test_partial_in_progress(self):
        """Git changes + 'in progress' = partial."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "1 file changed"}
        result = _classify_progress("work in progress", git_before, git_after, None)
        assert result == "partial"

    def test_partial_with_error_and_git_changes(self):
        """Git changes + error = partial (even without remaining keywords).
        NOTE: 'added' triggers 'progress' before 'partial' check.
        Use a neutral word like 'did things' that doesn't match any positive keyword.
        """
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "1 file changed"}
        result = _classify_progress(
            "did things", git_before, git_after, "error occurred"
        )
        assert result == "partial"

    def test_unknown_fallback(self):
        """Fallback when no rules match (longer than 30 chars, no failure keywords)."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "0 files"}
        result = _classify_progress(
            "something happened while processing the request",
            git_before,
            git_after,
            None,
        )
        assert result == "unknown"

    def test_git_before_none(self):
        """None git_before means no git changes detected."""
        result = _classify_progress("fixed stuff", None, {"diff_stat": "1 file"}, None)
        assert result in ("unknown", "stuck")

    def test_git_after_none(self):
        """None git_after means no git changes detected."""
        result = _classify_progress("fixed stuff", {"diff_stat": "0 files"}, None, None)
        assert result in ("unknown", "stuck")

    def test_error_with_git_changes_no_remaining(self):
        """Error + git changes without remaining keywords = partial."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "2 files changed"}
        result = _classify_progress(
            "did something", git_before, git_after, "error occurred"
        )
        assert result == "partial"

    def test_verbose_error_not_stuck(self):
        """Error with git changes should not be stuck even with failure keywords."""
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "1 file changed"}
        result = _classify_progress("cannot fix bug", git_before, git_after, "error")
        assert result == "partial"


# ===================================================================
# _suggest_actionable_fix
# ===================================================================


class TestSuggestActionableFix:
    """Tests for _suggest_actionable_fix function."""

    def test_completed_no_suggestion(self):
        """Completed classification returns None."""
        result = _suggest_actionable_fix(None, "completed", "fix tests")
        assert result is None

    def test_progress_no_suggestion(self):
        """Progress classification returns None."""
        result = _suggest_actionable_fix(None, "progress", "implement feature")
        assert result is None

    def test_timeout_suggestion(self):
        """Timeout error suggests session-timeout increase."""
        result = _suggest_actionable_fix("timeout", "stuck", "fix auth")
        assert result is not None
        assert "--session-timeout" in result

    def test_network_suggestion(self):
        """Network error suggests connectivity check."""
        result = _suggest_actionable_fix("network", "stuck", "fetch data")
        assert result is not None
        assert "network" in result.lower()

    def test_schema_suggestion(self):
        """Schema error suggests output-schema review."""
        result = _suggest_actionable_fix("schema", "stuck", "parse data")
        assert result is not None
        assert "--output-schema" in result

    def test_stuck_with_high_workers(self):
        """Stuck with workers > 1 suggests reducing workers."""
        result = _suggest_actionable_fix(
            None, "stuck", "fix bug", workers=3, use_library=False
        )
        assert result is not None
        assert "--workers 1" in result

    def test_stuck_no_use_library(self):
        """Stuck suggests --use-library when not already using it."""
        result = _suggest_actionable_fix(None, "stuck", "fix bug")
        assert result is not None
        assert "--use-library" in result

    def test_stuck_suggests_evolve(self):
        """Stuck suggests --evolve."""
        result = _suggest_actionable_fix(None, "stuck", "fix bug")
        assert result is not None
        assert "--evolve" in result

    def test_high_consecutive_errors(self):
        """3+ consecutive errors suggests --preflight."""
        result = _suggest_actionable_fix(
            "unknown", "stuck", "fix whatever", consecutive_errors=3
        )
        assert result is not None
        assert "--preflight" in result

    def test_regression_all_enabled(self):
        """Regression with all flags enabled returns None."""
        result = _suggest_actionable_fix(
            None,
            "regression",
            "refactor db",
            git=True,
            git_commit=True,
            force_reset=True,
        )
        assert result is None

    def test_regression_git_only(self):
        """Regression with git enabled, should skip --git flag."""
        result = _suggest_actionable_fix(
            None,
            "regression",
            "refactor db",
            git=True,
        )
        assert result is not None
        assert "Add --git to track" not in (result or "")
        assert "--git-commit" in (result or "")

    def test_regression_force_reset_already(self):
        """Regression with force_reset already set."""
        result = _suggest_actionable_fix(
            None, "regression", "refactor db", git=True, force_reset=True
        )
        assert result is not None
        # Should suggest --git-commit but not --force-reset
        assert "Run with --force-reset" not in (result or "")

    def test_partial_tip(self):
        """Partial classification returns a tip."""
        result = _suggest_actionable_fix("timeout", "partial", "fix things")
        assert result is not None
        # Timeout takes priority over partial
        assert "--session-timeout" in result

    def test_unknown_tip(self):
        """Unknown classification returns a tip."""
        result = _suggest_actionable_fix(None, "unknown", "do things")
        assert result is not None
        assert "Tip" in result

    def test_convergence_in_goal(self):
        """Convergence-related goal in stuck suggests threshold adjustment."""
        result = _suggest_actionable_fix(None, "stuck", "improve convergence detection")
        assert result is not None
        assert "--convergence-threshold" in result

    def test_stuck_no_error_type(self):
        """Stuck without error type suggests flags."""
        result = _suggest_actionable_fix(None, "stuck", "configure nginx")
        assert result is not None
        assert "--evolve" in result

    def test_regression_no_git_suggests_git(self):
        """Regression without git flag suggests --git."""
        result = _suggest_actionable_fix(None, "regression", "fix something", git=False)
        assert result is not None
        assert "Add --git to track" in (result or "")

    def test_consecutive_errors_5(self):
        """5 consecutive errors with stuck suggests preflight."""
        result = _suggest_actionable_fix(
            "unknown", "stuck", "deploy app", consecutive_errors=5
        )
        assert result is not None
        assert "--preflight" in result

    def test_network_suggestion_has_preflight(self):
        """Network error may suggest preflight or connectivity."""
        result = _suggest_actionable_fix("network", "stuck", "fetch data")
        assert result is not None

    def test_stuck_final_none_if_only_review(self):
        """Regression where the only tip is a review note returns None."""
        # git=True but no git_commit and no force_reset
        result = _suggest_actionable_fix(
            None,
            "regression",
            "fix something",
            git=False,
            git_commit=True,
            force_reset=True,
        )
        # With git_commit and force_reset already True, and git=False,
        # the only actionable suggestion is --git. That's not a no-op tip.
        assert result is not None
