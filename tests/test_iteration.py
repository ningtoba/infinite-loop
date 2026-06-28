"""Tests for iteration.py — _execute_iteration, _merge_worker_results, _handle_backoff,
_detect_convergence, _compact_summaries, _build_iteration_record, _handle_notifications,
_handle_callbacks, _sleep_with_shutdown_check."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from hermes_loop.iteration import (
    _sleep_with_shutdown_check,
    _merge_worker_results,
    _handle_backoff,
    _detect_convergence,
    _compact_summaries,
    _build_iteration_record,
    _handle_notifications,
    _handle_callbacks,
)

# ===================================================================
# _sleep_with_shutdown_check
# ===================================================================


class TestSleepWithShutdownCheck:
    def test_returns_false_when_no_shutdown(self):
        """Slept full duration — returns False."""
        with patch("hermes_loop.iteration._shutdown_requested", False):
            with patch("time.sleep"):
                result = _sleep_with_shutdown_check(5)
        assert result is False

    def test_returns_true_on_shutdown(self):
        """Shutdown requested during sleep — returns True immediately."""
        with patch("hermes_loop.iteration._shutdown_requested", True):
            with patch("time.sleep"):
                result = _sleep_with_shutdown_check(10)
        assert result is True

    def test_zero_seconds_no_block(self):
        """Zero seconds returns False immediately."""
        with patch("hermes_loop.iteration._shutdown_requested", False):
            with patch("time.sleep") as mock_sleep:
                result = _sleep_with_shutdown_check(0)
        assert result is False
        mock_sleep.assert_not_called()


# ===================================================================
# _merge_worker_results
# ===================================================================


class TestMergeWorkerResults:
    def test_single_success_worker(self):
        """Single worker with no error returns success."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "completed work",
                "duration_seconds": 30,
                "error": None,
                "output": "some output",
                "next_goal": "next task",
                "context": "context here",
            }
        ]
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=0,
            state={},
        )
        assert result["combined_error"] is None
        assert result["total_duration"] == 30
        assert result["combined_summary"] == "completed work"
        assert result["next_goal"] == "next task"
        assert result["next_context"] == "context here"

    def test_soft_error_exit_code_with_output(self):
        """Exit code error with meaningful summary is a soft error (not real failure)."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "Fixed the bug — this is a real summary from work done",
                "duration_seconds": 45,
                "error": "exit code 1",
                "output": "patch applied successfully and here is more meaningful content that exceeds 30 chars for soft detection",
                "next_goal": "",
                "context": "",
            }
        ]
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=2,
            state={},
        )
        # Soft error — not marked as failure, consecutive_errors resets to 0
        assert result["combined_error"] is None
        assert result["consecutive_errors"] == 0  # reset when no combined_error
        assert result["consecutive_successes"] == 1  # still incremented

    def test_hard_error_without_output(self):
        """Real error without meaningful output is a hard error."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "FAILED: connection refused",
                "duration_seconds": 10,
                "error": "network timeout after 30s",
                "output": "",
                "next_goal": "",
                "context": "",
            }
        ]
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=0,
            state={},
        )
        assert result["combined_error"] == "network timeout after 30s"
        assert result["consecutive_errors"] == 1
        assert result["consecutive_successes"] == 0

    def test_server_error_classification(self):
        """Error with 'exit code' but 'hermes exit' prefix and no output is hard."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "FAILED: hermes exited",
                "duration_seconds": 5,
                "error": "hermes exit 1",
                "output": "ab",
                "next_goal": "",
                "context": "",
            }
        ]
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=0,
            state={},
        )
        # output_len=2 which is <= 30, and summary starts with FAILED — hard error
        assert result["combined_error"] == "hermes exit 1"

    def test_multi_worker_all_hard_failures(self):
        """All workers have hard errors — combined error."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "FAILED: timeout",
                "duration_seconds": 30,
                "error": "timeout after 60s",
                "output": "",
                "next_goal": "",
                "context": "",
            },
            {
                "worker_id": 1,
                "summary": "FAILED: crash",
                "duration_seconds": 25,
                "error": "process crashed",
                "output": "",
                "next_goal": "",
                "context": "",
            },
        ]
        state = {"stats": {"consecutive_successes": 3}, "error_type_counts": {}}
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=0,
            state=state,
        )
        assert result["combined_error"] is not None
        assert "timeout after 60s" in result["combined_error"]
        assert result["total_duration"] == 30  # max of durations
        assert result["consecutive_successes"] == 0  # reset

    def test_multi_worker_one_success_one_soft(self):
        """One worker success, one soft error — not a failure."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "Implemented feature X",
                "duration_seconds": 60,
                "error": None,
                "output": "new file created",
                "next_goal": "",
                "context": "W0: done",
            },
            {
                "worker_id": 1,
                "summary": "Partially completed",
                "duration_seconds": 30,
                "error": "exit code 1",
                "output": "some work done here",
                "next_goal": "",
                "context": "W1: partial",
            },
        ]
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=0,
            state={"stats": {"consecutive_successes": 2}},
        )
        assert result["combined_error"] is None

    def test_error_type_counts_tracked(self):
        """Error type counts increment in state."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "FAILED",
                "duration_seconds": 5,
                "error": "timed out after 30s",
                "output": "",
                "error_type": "timeout",
                "next_goal": "",
                "context": "",
            }
        ]
        state = {"error_type_counts": {"timeout": 1}}
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=2,
            state=state,
        )
        assert result["combined_error"] is not None
        assert result["primary_error_type"] == "timeout"
        assert state["error_type_counts"]["timeout"] == 2

    def test_next_context_multi_worker(self):
        """Multiple workers provide context — concatenated with labels."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "done",
                "duration_seconds": 10,
                "error": None,
                "output": "",
                "next_goal": "next A",
                "context": "Context from worker 0",
            },
            {
                "worker_id": 1,
                "summary": "done",
                "duration_seconds": 20,
                "error": None,
                "output": "",
                "next_goal": "next B",
                "context": "Context from worker 1",
            },
        ]
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=0,
            state={"stats": {}},
        )
        assert "[Worker #0]" in result["next_context"]
        assert "[Worker #1]" in result["next_context"]
        assert "Context from worker 0" in result["next_context"]

    def test_empty_results_list(self):
        """Empty results list raises IndexError (actual behavior)."""
        with pytest.raises(IndexError):
            _merge_worker_results(
                all_results=[],
                max_output_chars=5000,
                consecutive_errors=0,
                state={"stats": {}},
            )

    def test_combined_summary_truncated(self):
        """Combined output is truncated to max_output_chars."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "done",
                "duration_seconds": 10,
                "error": None,
                "output": "A" * 200,
                "next_goal": "",
                "context": "",
            }
        ]
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=50,
            consecutive_errors=0,
            state={"stats": {}},
        )
        assert len(result["combined_output"]) <= 50

    def test_error_type_classification(self):
        """Pick primary error from error_types."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "FAILED",
                "duration_seconds": 5,
                "error": "network error",
                "error_type": "network",
                "output": "",
                "next_goal": "",
                "context": "",
            }
        ]
        state = {"error_type_counts": {}}
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=0,
            state=state,
        )
        assert result["primary_error_type"] == "network"

    def test_schema_error_marked_hard(self):
        """Schema error type is treated as a hard error (is_soft_error returns False)."""
        all_results = [
            {
                "worker_id": 0,
                "summary": "FAILED: schema validation",
                "duration_seconds": 5,
                "error": "exit code 1",
                "error_type": "schema",
                "output": "",
                "next_goal": "",
                "context": "",
            }
        ]
        state = {"error_type_counts": {}}
        result = _merge_worker_results(
            all_results=all_results,
            max_output_chars=5000,
            consecutive_errors=0,
            state=state,
        )
        assert result["combined_error"] == "exit code 1"


# ===================================================================
# _handle_backoff
# ===================================================================


class TestHandleBackoff:
    def test_no_backoff_when_no_error(self):
        """No backoff delay without error."""
        with patch(
            "hermes_loop.iteration._sleep_with_shutdown_check", return_value=False
        ):
            result = _handle_backoff(
                combined_error=None,
                retry_delay=10,
                consecutive_errors=0,
                adapt_actions=[],
                state={},
                status_file="",
                iteration_count=0,
            )
        assert result is False

    def test_backoff_applied_on_error(self):
        """Delay applied when error + retry_delay > 0."""
        with patch(
            "hermes_loop.iteration._sleep_with_shutdown_check", return_value=False
        ):
            result = _handle_backoff(
                combined_error="something failed",
                retry_delay=10,
                consecutive_errors=3,
                adapt_actions=[],
                state={},
                status_file="",
                iteration_count=0,
            )
        assert result is False

    def test_backoff_exponential_capped(self):
        """Delay is retry_delay * min(consecutive_errors, 5)."""
        with patch(
            "hermes_loop.iteration._sleep_with_shutdown_check", return_value=False
        ) as mock_sleep:
            _handle_backoff(
                combined_error="error",
                retry_delay=10,
                consecutive_errors=2,
                adapt_actions=[],
                state={},
                status_file="",
                iteration_count=0,
            )
        # delay = 10 * min(2, 5) = 20
        mock_sleep.assert_called_once_with(20)

    def test_backoff_shutdown_during_backoff(self):
        """Shutdown during backoff writes 'stopped: shutdown-during-backoff' state."""
        with patch(
            "hermes_loop.iteration._sleep_with_shutdown_check", return_value=True
        ):
            with patch("hermes_loop.iteration.write_ledger") as mock_write:
                state = {}
                result = _handle_backoff(
                    combined_error="error",
                    retry_delay=10,
                    consecutive_errors=3,
                    adapt_actions=[],
                    state=state,
                    status_file="/tmp/status",
                    iteration_count=5,
                )
        assert result is True
        assert state["status"] == "stopped: shutdown-during-backoff"
        mock_write.assert_called_once()

    def test_backoff_sleeps_even_with_adapt_actions(self):
        """Backoff still sleeps when adapt_actions is non-empty (only logging is suppressed)."""
        with patch(
            "hermes_loop.iteration._sleep_with_shutdown_check", return_value=False
        ) as mock_sleep:
            result = _handle_backoff(
                combined_error="error",
                retry_delay=10,
                consecutive_errors=1,
                adapt_actions=["reduced_workers"],
                state={},
                status_file="",
                iteration_count=0,
            )
        assert result is False
        mock_sleep.assert_called_once()

    def test_backoff_capped_at_max_five(self):
        """Consecutive errors > 5 use cap of 5."""
        with patch(
            "hermes_loop.iteration._sleep_with_shutdown_check", return_value=False
        ) as mock_sleep:
            _handle_backoff(
                combined_error="err",
                retry_delay=10,
                consecutive_errors=10,
                adapt_actions=[],
                state={},
                status_file="",
                iteration_count=0,
            )
        # delay = 10 * min(10, 5) = 50
        mock_sleep.assert_called_once_with(50)

    def test_no_backoff_when_retry_delay_zero(self):
        """Zero retry_delay skips backoff even on error."""
        with patch("hermes_loop.iteration._sleep_with_shutdown_check") as mock_sleep:
            result = _handle_backoff(
                combined_error="error",
                retry_delay=0,
                consecutive_errors=5,
                adapt_actions=[],
                state={},
                status_file="",
                iteration_count=0,
            )
        assert result is False
        mock_sleep.assert_not_called()


# ===================================================================
# _detect_convergence
# ===================================================================


class TestDetectConvergence:
    def test_not_enough_iterations(self):
        """Convergence check skipped when iteration_count < convergence_window."""
        result = _detect_convergence(
            convergence_stop=True,
            iteration_count=2,
            convergence_window=5,
            existing_summaries=[],
            combined_summary="test summary",
            convergence_threshold=0.9,
            state={},
            status_file="",
        )
        assert result is False

    def test_convergence_not_enabled(self):
        """Convergence skipped when convergence_stop is False."""
        result = _detect_convergence(
            convergence_stop=False,
            iteration_count=10,
            convergence_window=3,
            existing_summaries=[],
            combined_summary="test",
            convergence_threshold=0.9,
            state={},
            status_file="",
        )
        assert result is False

    def test_short_summary_skips_check(self):
        """Summary too short (< 20 chars) skips convergence check."""
        result = _detect_convergence(
            convergence_stop=True,
            iteration_count=5,
            convergence_window=3,
            existing_summaries=[],
            combined_summary="short",  # only 5 chars
            convergence_threshold=0.9,
            state={},
            status_file="",
        )
        assert result is False

    def test_convergence_detected(self):
        """Convergence detected when similarity exceeds threshold."""
        with patch(
            "hermes_loop.iteration.check_convergence", return_value=(True, 0.95)
        ):
            with patch("hermes_loop.iteration.write_ledger"):
                with patch("hermes_loop.iteration.write_status_file"):
                    state = {}
                    result = _detect_convergence(
                        convergence_stop=True,
                        iteration_count=10,
                        convergence_window=3,
                        existing_summaries=["summary 1", "summary 2", "summary 3"],
                        combined_summary="summary 4 that is long enough to pass the 20 char threshold",
                        convergence_threshold=0.9,
                        state=state,
                        status_file="/tmp/status",
                    )
        assert result is True
        assert "convergence" in state["status"]

    def test_convergence_not_met(self):
        """Similarity below threshold does not stop loop."""
        with patch(
            "hermes_loop.iteration.check_convergence", return_value=(False, 0.6)
        ):
            result = _detect_convergence(
                convergence_stop=True,
                iteration_count=10,
                convergence_window=3,
                existing_summaries=["a" * 60, "b" * 60, "c" * 60],
                combined_summary="d" * 60,
                convergence_threshold=0.9,
                state={},
                status_file="",
            )
        assert result is False

    def test_convergence_logs_near_threshold(self):
        """Similarity > 0.5 logs a warning even if not stopping."""
        with patch(
            "hermes_loop.iteration.check_convergence", return_value=(False, 0.7)
        ):
            with patch("hermes_loop.iteration._log"):
                result = _detect_convergence(
                    convergence_stop=True,
                    iteration_count=10,
                    convergence_window=3,
                    existing_summaries=["a" * 60, "b" * 60, "c" * 60],
                    combined_summary="d" * 60,
                    convergence_threshold=0.9,
                    state={},
                    status_file="",
                )
        assert result is False


# ===================================================================
# _compact_summaries
# ===================================================================


class TestCompactSummaries:
    def test_no_compaction_when_not_divisible(self):
        """No compaction when iteration_count % compact_every != 0."""
        existing = ["s1", "s2", "s3"]
        result, compacted = _compact_summaries(
            existing_summaries=existing,
            compact_every=5,
            iteration_count=3,
            combined_summary="new summary",
        )
        assert compacted is False
        assert result[-1] == "new summary"
        assert len(result) == 4  # original 3 + new 1

    def test_compaction_on_divisible(self):
        """Compaction when iteration_count % compact_every == 0."""
        existing = [f"s{i}" for i in range(10)]
        result, compacted = _compact_summaries(
            existing_summaries=existing,
            compact_every=5,
            iteration_count=5,
            combined_summary="new",
        )
        assert compacted is True

    def test_compaction_keeps_recent_entries(self):
        """Recent entries are kept, old ones condensed."""
        existing = [f"s{i}" for i in range(50)]
        result, compacted = _compact_summaries(
            existing_summaries=existing,
            compact_every=5,
            iteration_count=10,
            combined_summary="new",
        )
        assert compacted is True
        assert "[30 earlier iterations condensed]" in result

    def test_compact_summaries_appends_new(self):
        """New summary is always appended after compaction."""
        result, compacted = _compact_summaries(
            existing_summaries=[],
            compact_every=3,
            iteration_count=3,
            combined_summary="first summary after compaction",
        )
        assert compacted is True
        assert result[-1] == "first summary after compaction"


# ===================================================================
# _build_iteration_record
# ===================================================================


class MockGoalSpec:
    """Minimal GoalSpec-like object for testing."""

    def __init__(self, goal="", profile=None, model=None, provider=None):
        self.goal = goal
        self.profile = profile
        self.model = model
        self.provider = provider


class TestBuildIterationRecord:
    def test_basic_record_structure(self):
        """Record has all required fields."""
        with patch("hermes_loop.iteration.get_system_usage", return_value={}):
            with patch("hermes_loop.iteration.get_system_usage_diff", return_value={}):
                record = _build_iteration_record(
                    iteration_count=3,
                    task_type="research",
                    spawn_goal=MockGoalSpec(goal="find papers"),
                    goals_list=[MockGoalSpec(goal="find papers")],
                    iteration_start_time="2026-06-28T12:00:00",
                    total_duration=45.5,
                    combined_summary="Found 3 relevant papers",
                    is_compacted=False,
                    combined_error=None,
                    all_results=[
                        {"worker_id": 0, "summary": "ok", "duration_seconds": 45.5}
                    ],
                    workers=1,
                    toolsets=["terminal", "web"],
                    git_before={},
                    git_after={},
                    git=False,
                    git_commit_hash=None,
                    next_goal="search more",
                    next_context="look deeper",
                    resume=False,
                    pass_session_id=False,
                    state={},
                    sys_before={},
                )
        assert record["n"] == 3
        assert record["task_type"] == "research"
        assert record["duration_seconds"] == 45.5
        assert record["summary"] == "Found 3 relevant papers"
        assert record["error"] is None
        assert record["compacted"] is False
        assert record["next_goal"] == "search more"
        assert record["next_context"] == "look deeper"
        assert record["worker_results"] is None  # single worker

    def test_multi_worker_record(self):
        """Multi-worker mode includes worker_results sub-dict."""
        with patch("hermes_loop.iteration.get_system_usage", return_value={}):
            with patch("hermes_loop.iteration.get_system_usage_diff", return_value={}):
                record = _build_iteration_record(
                    iteration_count=5,
                    task_type="code-fix",
                    spawn_goal=MockGoalSpec(goal="fix bugs"),
                    goals_list=[],
                    iteration_start_time="2026-06-28T13:00:00",
                    total_duration=90.0,
                    combined_summary="Fixed 2 bugs across workers",
                    is_compacted=True,
                    combined_error=None,
                    all_results=[
                        {
                            "worker_id": 0,
                            "summary": "fixed bug A",
                            "duration_seconds": 45,
                            "error": None,
                        },
                        {
                            "worker_id": 1,
                            "summary": "fixed bug B",
                            "duration_seconds": 90,
                            "error": None,
                        },
                    ],
                    workers=2,
                    toolsets=["terminal"],
                    git_before={},
                    git_after={},
                    git=False,
                    git_commit_hash=None,
                    next_goal=None,
                    next_context=None,
                    resume=False,
                    pass_session_id=False,
                    state={},
                    sys_before={},
                )
        assert record["workers"] == 2
        assert record["worker_results"] is not None
        assert len(record["worker_results"]) == 2

    def test_record_with_error(self):
        """Record properly stores error information."""
        with patch("hermes_loop.iteration.get_system_usage", return_value={}):
            with patch("hermes_loop.iteration.get_system_usage_diff", return_value={}):
                record = _build_iteration_record(
                    iteration_count=2,
                    task_type="general",
                    spawn_goal=MockGoalSpec(goal="run tests"),
                    goals_list=[],
                    iteration_start_time="2026-06-28T14:00:00",
                    total_duration=10.0,
                    combined_summary="Tests failed",
                    is_compacted=False,
                    combined_error="timeout after 30s",
                    all_results=[
                        {
                            "worker_id": 0,
                            "summary": "FAILED",
                            "duration_seconds": 10,
                            "error": "timeout",
                        }
                    ],
                    workers=1,
                    toolsets=["terminal"],
                    git_before={},
                    git_after={},
                    git=False,
                    git_commit_hash=None,
                    next_goal=None,
                    next_context=None,
                    resume=False,
                    pass_session_id=False,
                    state={},
                    sys_before={},
                )
        assert record["error"] == "timeout after 30s"
        assert record["exit_code"] == 1

    def test_git_fields(self):
        """Git fields are included when git=True."""
        with patch("hermes_loop.iteration.get_system_usage", return_value={}):
            with patch("hermes_loop.iteration.get_system_usage_diff", return_value={}):
                record = _build_iteration_record(
                    iteration_count=1,
                    task_type="code-fix",
                    spawn_goal=MockGoalSpec(),
                    goals_list=[],
                    iteration_start_time="",
                    total_duration=10,
                    combined_summary="",
                    is_compacted=False,
                    combined_error=None,
                    all_results=[{}],
                    workers=1,
                    toolsets=[],
                    git_before={"diff_stat": "+3/-1"},
                    git_after={"diff_stat": "+5/-2"},
                    git=True,
                    git_commit_hash="abc123",
                    next_goal=None,
                    next_context=None,
                    resume=False,
                    pass_session_id=False,
                    state={},
                    sys_before={},
                )
        assert record["git_before"] == {"diff_stat": "+3/-1"}
        assert record["git_after"] == {"diff_stat": "+5/-2"}
        assert record["git_commit"] == "abc123"

    def test_session_id_propagation(self):
        """spawned_session_id is copied to record for single worker."""
        with patch("hermes_loop.iteration.get_system_usage", return_value={}):
            with patch("hermes_loop.iteration.get_system_usage_diff", return_value={}):
                record = _build_iteration_record(
                    iteration_count=1,
                    task_type="general",
                    spawn_goal=MockGoalSpec(),
                    goals_list=[],
                    iteration_start_time="",
                    total_duration=5,
                    combined_summary="",
                    is_compacted=False,
                    combined_error=None,
                    all_results=[{"spawned_session_id": "sess_abc123"}],
                    workers=1,
                    toolsets=[],
                    git_before={},
                    git_after={},
                    git=False,
                    git_commit_hash=None,
                    next_goal=None,
                    next_context=None,
                    resume=False,
                    pass_session_id=False,
                    state={},
                    sys_before={},
                )
        assert record["spawned_session_id"] == "sess_abc123"

    def test_classification_in_record(self):
        """Record includes classification field from _classify_progress."""
        with patch("hermes_loop.iteration.get_system_usage", return_value={}):
            with patch("hermes_loop.iteration.get_system_usage_diff", return_value={}):
                with patch(
                    "hermes_loop.iteration._classify_progress",
                    return_value="completed",
                ):
                    record = _build_iteration_record(
                        iteration_count=3,
                        task_type="research",
                        spawn_goal=MockGoalSpec(),
                        goals_list=[],
                        iteration_start_time="",
                        total_duration=10,
                        combined_summary="done",
                        is_compacted=False,
                        combined_error=None,
                        all_results=[{}],
                        workers=1,
                        toolsets=[],
                        git_before={},
                        git_after={},
                        git=False,
                        git_commit_hash=None,
                        next_goal=None,
                        next_context=None,
                        resume=False,
                        pass_session_id=False,
                        state={},
                        sys_before={},
                    )
        assert record["classification"] == "completed"

    def test_resume_session_id_tracking(self):
        """resume + pass_session_id tracks spawned session IDs in state."""
        state = {}
        with patch("hermes_loop.iteration.get_system_usage", return_value={}):
            with patch("hermes_loop.iteration.get_system_usage_diff", return_value={}):
                _build_iteration_record(
                    iteration_count=1,
                    task_type="general",
                    spawn_goal=MockGoalSpec(),
                    goals_list=[],
                    iteration_start_time="",
                    total_duration=5,
                    combined_summary="",
                    is_compacted=False,
                    combined_error=None,
                    all_results=[{"spawned_session_id": "sess_xyz"}],
                    workers=1,
                    toolsets=[],
                    git_before={},
                    git_after={},
                    git=False,
                    git_commit_hash=None,
                    next_goal=None,
                    next_context=None,
                    resume=True,
                    pass_session_id=True,
                    state=state,
                    sys_before={},
                )
        assert state["resume_session_id"] == "sess_xyz"
        assert "sess_xyz" in state.get("session_id_history", [])

    def test_system_diff_in_record(self):
        """System usage diff is included when available."""
        sys_diff = {"cpu_seconds": 5.0, "memory_rss_mb": 100}
        with patch("hermes_loop.iteration.get_system_usage", return_value={}):
            with patch(
                "hermes_loop.iteration.get_system_usage_diff", return_value=sys_diff
            ):
                record = _build_iteration_record(
                    iteration_count=1,
                    task_type="general",
                    spawn_goal=MockGoalSpec(),
                    goals_list=[],
                    iteration_start_time="",
                    total_duration=5,
                    combined_summary="",
                    is_compacted=False,
                    combined_error=None,
                    all_results=[{}],
                    workers=1,
                    toolsets=[],
                    git_before={},
                    git_after={},
                    git=False,
                    git_commit_hash=None,
                    next_goal=None,
                    next_context=None,
                    resume=False,
                    pass_session_id=False,
                    state={},
                    sys_before={},
                )
        assert record["system"] == sys_diff


# ===================================================================
# _handle_notifications
# ===================================================================


class TestHandleNotifications:
    def test_no_notifications_when_all_disabled(self):
        """No notifications dispatched when all disabled."""
        with patch(
            "hermes_loop.iteration._send_per_iteration_notifications"
        ) as mock_send:
            _handle_notifications(
                notify_desktop=False,
                notify_pushbullet="",
                notify_ntfy="",
                combined_summary="test",
                total_duration=10,
                combined_error=None,
                notify_ntfy_server="https://ntfy.sh",
            )
        mock_send.assert_not_called()

    def test_desktop_notification_sent(self):
        """Desktop notification dispatched when enabled."""
        with patch(
            "hermes_loop.iteration._send_per_iteration_notifications"
        ) as mock_send:
            _handle_notifications(
                notify_desktop=True,
                notify_pushbullet="",
                notify_ntfy="",
                combined_summary="Work done",
                total_duration=30,
                combined_error=None,
                notify_ntfy_server="https://ntfy.sh",
            )
        mock_send.assert_called_once()

    def test_pushbullet_notification_sent(self):
        """Pushbullet notification dispatched with token."""
        with patch(
            "hermes_loop.iteration._send_per_iteration_notifications"
        ) as mock_send:
            _handle_notifications(
                notify_desktop=False,
                notify_pushbullet="pb_token_123",
                notify_ntfy="",
                combined_summary="Push",
                total_duration=15,
                combined_error="error msg",
                notify_ntfy_server="https://ntfy.sh",
            )
        mock_send.assert_called_once()

    def test_combined_notifications(self):
        """Multiple notification types dispatched together."""
        with patch(
            "hermes_loop.iteration._send_per_iteration_notifications"
        ) as mock_send:
            _handle_notifications(
                notify_desktop=True,
                notify_pushbullet="token",
                notify_ntfy="topic",
                combined_summary="Multi notification",
                total_duration=60,
                combined_error=None,
                notify_ntfy_server="https://ntfy.sh",
            )
        mock_send.assert_called_once()

    def test_ntfy_with_custom_server(self):
        """Custom ntfy server URL is passed through."""
        with patch(
            "hermes_loop.iteration._send_per_iteration_notifications"
        ) as mock_send:
            _handle_notifications(
                notify_desktop=False,
                notify_pushbullet="",
                notify_ntfy="my_topic",
                combined_summary="test",
                total_duration=5,
                combined_error=None,
                notify_ntfy_server="https://custom.ntfy.com",
            )
        mock_send.assert_called_once()


# ===================================================================
# _handle_callbacks
# ===================================================================


class TestHandleCallbacks:
    def test_no_callbacks(self):
        """No callbacks dispatched when none configured."""
        with patch("hermes_loop.iteration.subprocess.run") as mock_run:
            _handle_callbacks(
                http_callback="",
                record={"n": 1},
                notify_cmd=None,
                on_error_cmd=None,
                combined_error=None,
                state=None,
            )
        mock_run.assert_not_called()

    def test_http_callback_sent(self):
        """HTTP callback is sent with record and state data."""
        with patch("urllib.request.Request") as mock_request:
            mock_request.return_value = MagicMock()
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.return_value.__enter__.return_value.status = 200
                _handle_callbacks(
                    http_callback="http://example.com/cb",
                    record={"n": 1, "summary": "test"},
                    notify_cmd=None,
                    on_error_cmd=None,
                    combined_error=None,
                    state={
                        "status": "running",
                        "total_iterations": 1,
                        "max_iterations": 10,
                        "started_at": "2026-01-01",
                        "last_updated": "2026-01-01",
                        "stats": {"consecutive_errors": 0},
                        "eta": {},
                    },
                )
        mock_request.assert_called_once()

    def test_notify_cmd(self):
        """Notify command is executed with record JSON on stdin."""
        with patch(
            "hermes_loop.iteration.subprocess.run",
            return_value=MagicMock(returncode=0),
        ) as mock_run:
            _handle_callbacks(
                http_callback="",
                record={"n": 1, "summary": "done"},
                notify_cmd="echo 'notify'",
                on_error_cmd=None,
                combined_error=None,
                state=None,
            )
        mock_run.assert_called_once()

    def test_on_error_cmd_with_error(self):
        """Error command executed when combined_error is set."""
        with patch(
            "hermes_loop.iteration.subprocess.run",
            return_value=MagicMock(returncode=0),
        ) as mock_run:
            _handle_callbacks(
                http_callback="",
                record={"n": 2, "summary": "FAILED"},
                notify_cmd=None,
                on_error_cmd="echo 'on-error'",
                combined_error="timeout",
                state=None,
            )
        mock_run.assert_called_once()

    def test_on_error_cmd_skipped_without_error(self):
        """Error command not executed when no error."""
        with patch("hermes_loop.iteration.subprocess.run") as mock_run:
            _handle_callbacks(
                http_callback="",
                record={"n": 3, "summary": "all good"},
                notify_cmd=None,
                on_error_cmd="echo 'on-error'",
                combined_error=None,
                state=None,
            )
        mock_run.assert_not_called()

    def test_http_callback_failure_logged(self):
        """HTTP callback failure is caught and logged."""
        with patch("hermes_loop.iteration._log") as mock_log:
            with patch(
                "urllib.request.Request",
                side_effect=Exception("network error"),
            ):
                _handle_callbacks(
                    http_callback="http://example.com/cb",
                    record={"n": 1},
                    notify_cmd=None,
                    on_error_cmd=None,
                    combined_error=None,
                    state={"status": "running"},
                )
                mock_log.assert_called_once()

    def test_notify_cmd_timeout(self):
        """Notify command timeout is caught and logged."""
        with patch(
            "hermes_loop.iteration.subprocess.run",
            side_effect=TimeoutError("timed out"),
        ):
            with patch("hermes_loop.iteration._log") as mock_log:
                _handle_callbacks(
                    http_callback="",
                    record={"n": 1},
                    notify_cmd="sleep 100",
                    on_error_cmd=None,
                    combined_error=None,
                    state=None,
                )
                mock_log.assert_called_once()

    def test_http_callback_with_state_payload(self):
        """HTTP callback includes state dict when state is provided."""
        with patch("urllib.request.Request") as mock_request:
            mock_request.return_value = MagicMock()
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.return_value.__enter__.return_value.status = 200
                _handle_callbacks(
                    http_callback="http://example.com/cb",
                    record={"n": 1, "summary": "iteration done"},
                    notify_cmd=None,
                    on_error_cmd=None,
                    combined_error=None,
                    state={
                        "status": "running",
                        "total_iterations": 5,
                        "max_iterations": 100,
                        "started_at": "2026-01-01T00:00:00",
                        "last_updated": "2026-01-01T01:00:00",
                        "cooldown": 0,
                        "initial_command": "fix bugs",
                        "evolved_goal": "",
                        "stats": {
                            "consecutive_errors": 0,
                            "success_count": 4,
                            "error_count": 1,
                            "total_duration_seconds": 300,
                            "avg_duration_seconds": 60,
                        },
                        "eta": {"remaining_formatted": "5m"},
                    },
                )
        mock_request.assert_called_once()
        # Verify payload contains state data
        call_args, call_kwargs = mock_request.call_args
        assert call_args[0] == "http://example.com/cb"
        payload_body = call_kwargs.get("data") or call_args[1]
        payload = json.loads(payload_body.decode("utf-8"))
        assert "state" in payload
        assert "stats" in payload
        assert payload["state"]["status"] == "running"
