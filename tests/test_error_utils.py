"""Tests for classify_error and _suggest_actionable_fix."""

from omp_loop.error_utils import _suggest_actionable_fix, classify_error

# ── classify_error ──────────────────────────────────────────────────────────


class TestClassifyError:
    """Tests for classify_error()."""

    def test_none_input(self):
        """None input returns None."""
        assert classify_error(None) is None

    def test_empty_string(self):
        """Empty string returns None."""
        assert classify_error("") is None

    def test_timeout_keyword(self):
        """Error containing 'timeout' returns 'timeout'."""
        assert classify_error("Operation timed out") == "timeout"

    def test_timed_out_keyword(self):
        """Error containing 'timed out' returns 'timeout'."""
        assert classify_error("The request timed out") == "timeout"

    def test_timeout_case_insensitive(self):
        """Classification is case-insensitive."""
        assert classify_error("TIMEOUT ERROR") == "timeout"

    def test_connection_refused(self):
        """Error containing 'connection refused' returns 'network'."""
        assert classify_error("Connection refused by host") == "network"

    def test_connection_error(self):
        """Error containing 'connectionerror' returns 'network'."""
        assert classify_error("ConnectionError: no route") == "network"

    def test_connection_reset(self):
        """Error containing 'connection reset' returns 'network'."""
        assert classify_error("Connection reset by peer") == "network"

    def test_network_keyword(self):
        """Error containing 'network' returns 'network'."""
        assert classify_error("Network is unreachable") == "network"

    def test_dns_keyword(self):
        """Error containing 'dns' returns 'network'."""
        assert classify_error("DNS resolution failed") == "network"

    def test_refused_keyword(self):
        """Error containing 'refused' returns 'network'."""
        assert classify_error("refused by server") == "network"

    def test_no_route_keyword(self):
        """Error containing 'no route' returns 'network'."""
        assert classify_error("No route to host") == "network"

    def test_schema_keyword(self):
        """Error containing 'schema' returns 'schema'."""
        assert classify_error("JSON schema validation error") == "schema"

    def test_validation_keyword(self):
        """Error containing 'validation' returns 'schema'."""
        assert classify_error("Validation failed on field") == "schema"

    def test_invalid_keyword(self):
        """Error containing 'invalid' returns 'schema'."""
        assert classify_error("Invalid input value") == "schema"

    def test_unknown_error(self):
        """Error that doesn't match known categories returns 'unknown'."""
        assert classify_error("Something went wrong") == "unknown"

    def test_unknown_crash(self):
        """Crash-like error returns 'unknown'."""
        assert classify_error("Segmentation fault") == "unknown"


# ── _suggest_actionable_fix ─────────────────────────────────────────────────


class TestSuggestActionableFix:
    """Tests for _suggest_actionable_fix()."""

    def test_completed_classification(self):
        """Completed classification returns None."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="completed",
            goal="do stuff",
        )
        assert result is None

    def test_progress_classification(self):
        """Progress classification returns None."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="progress",
            goal="do stuff",
        )
        assert result is None

    def test_timeout_suggestion(self):
        """Timeout error returns timeout-specific suggestion."""
        result = _suggest_actionable_fix(
            error_type="timeout",
            classification="stuck",
            goal="fix bugs",
        )
        assert result is not None
        assert "session-timeout" in result

    def test_network_suggestion(self):
        """Network error returns network-specific suggestion."""
        result = _suggest_actionable_fix(
            error_type="network",
            classification="stuck",
            goal="deploy app",
        )
        assert result is not None
        assert "network" in result.lower()
        assert "retry-delay" in result

    def test_schema_suggestion(self):
        """Schema error returns schema-specific suggestion."""
        result = _suggest_actionable_fix(
            error_type="schema",
            classification="stuck",
            goal="process data",
        )
        assert result is not None
        assert "schema" in result.lower()

    def test_unknown_suggestion(self):
        """Unknown error without consecutive errors returns unknown tip."""
        result = _suggest_actionable_fix(
            error_type="unknown",
            classification="unknown",
            goal="do stuff",
        )
        assert result is not None
        assert "didn't match any known pattern" in result.lower()

    def test_high_consecutive_errors(self):
        """3+ consecutive errors with unknown/stuck returns escalation.

        Note: timeout/network/schema error types return before the
        consecutive-errors check in the current code.
        """
        result = _suggest_actionable_fix(
            error_type="unknown",
            classification="stuck",
            goal="fix bugs",
            consecutive_errors=3,
        )
        assert result is not None
        assert "preflight" in result

    def test_stuck_classification(self):
        """Stuck classification returns stuck suggestion."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="stuck",
            goal="fix bugs",
            workers=1,
        )
        assert result is not None
        assert "use-library" in result

    def test_stuck_with_workers(self):
        """Stuck with >1 workers suggests reducing workers."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="stuck",
            goal="fix bugs",
            workers=4,
        )
        assert result is not None
        assert "workers" in result

    def test_regression_with_git(self):
        """Regression with git enabled but no force-reset and no git-commit.

        The function returns suggestions for --force-reset and --git-commit
        even when git is already enabled.
        """
        result = _suggest_actionable_fix(
            error_type=None,
            classification="regression",
            goal="fix bugs",
            git=True,
        )
        assert result is not None
        assert "force-reset" in result
        assert "git-commit" in result

    def test_regression_without_git(self):
        """Regression without git suggests adding --git."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="regression",
            goal="fix bugs",
            git=False,
        )
        assert result is not None
        assert "--git" in result

    def test_regression_suggests_force_reset(self):
        """Regression without force-reset suggests --force-reset."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="regression",
            goal="fix bugs",
            git=True,
            force_reset=False,
        )
        assert result is not None
        assert "force-reset" in result

    def test_regression_without_git_commit(self):
        """Regression without git-commit suggests --git-commit."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="regression",
            goal="fix bugs",
            git=True,
            git_commit=False,
            force_reset=True,
        )
        assert result is not None
        assert "--git-commit" in result

    def test_partial_classification(self):
        """Partial classification with no error_type returns None.

        The function only returns partial tips when error_type is set,
        because the early guard returns None when error_type is None
        and classification is not stuck/regression/unknown.
        """
        result = _suggest_actionable_fix(
            error_type=None,
            classification="partial",
            goal="fix bugs",
        )
        assert result is None

    def test_no_error_no_classification(self):
        """No error and no stuck/regression/unknown returns None."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="running",
            goal="fix bugs",
        )
        assert result is None

    def test_convergence_goal_stuck(self):
        """Stuck with convergence-related goal mentions threshold."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="stuck",
            goal="convergence analysis",
            workers=1,
        )
        assert result is not None
        assert "convergence" in result

    def test_regression_git_true_no_other(self):
        """Regression with git=True, force_reset=True, git_commit=True returns None."""
        result = _suggest_actionable_fix(
            error_type=None,
            classification="regression",
            goal="fix bugs",
            git=True,
            git_commit=True,
            force_reset=True,
        )
        assert result is None
