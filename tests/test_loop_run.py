"""Tests for loop.py — run_loop() control flow paths.

Heavy mocking of module-level imports. Each test class exercises one specific
exit/stop path in run_loop(). Uses contextlib.ExitStack to avoid Python's
static nesting limit on `with` blocks.
"""

from __future__ import annotations

import contextlib
import os

import pytest
from unittest.mock import MagicMock, PropertyMock, patch

from hermes_loop.goal_utils import GoalSpec
from hermes_loop.loop import run_loop

# ── constants ────────────────────────────────────────────────────────────────

GOALS_TUPLE_SINGLE = [("test goal", "", "", "")]
_GOAL_SPEC: GoalSpec = GoalSpec("test goal")

_SUCCESS_MERGE: dict = {
    "combined_error": None,
    "total_duration": 1.0,
    "combined_summary": "ok",
    "next_goal": "",
    "next_context": "",
    "primary_error_type": None,
    "consecutive_successes": 1,
    "consecutive_errors": 0,
}

_SUCCESS_EXEC = (
    [
        {
            "worker_id": 0,
            "summary": "done",
            "duration_seconds": 1,
            "error": None,
            "output": "",
            "next_goal": "",
            "context": "",
        }
    ],
    _GOAL_SPEC,
    False,
)

_SUCCESS_RECORD = {
    "n": 1,
    "summary": "done",
    "duration_seconds": 1,
    "error": None,
    "classification": "completed",
}

GOALS_TUPLE_DOUBLE = [("g1", "", "", ""), ("g2", "", "", "")]
GOALS_TUPLE_TRIPLE = [("g1", "", "", ""), ("g2", "", "", ""), ("g3", "", "", "")]


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_minimal_state(**overrides):
    """Return a state dict with all keys run_loop() reads on startup."""
    state = {
        "total_iterations": 0,
        "iterations": [],
        "status": "running",
        "stats": {
            "consecutive_errors": 0,
            "consecutive_successes": 0,
            "total_duration_seconds": 0,
        },
        "mitigations": {"mitigation_level": 0},
        "error_type_counts": {},
        "goals_specs": [],
        "goals_completed": {},
        "tag": "test",
    }
    state.update(overrides)
    return state


def _base_kwargs() -> dict:
    """Return minimum keyword arguments for run_loop()."""
    return {
        "goal": "test goal",
        "context": "",
        "toolsets": [],
        "workdir": None,
        "sentinel_path": "",
        "max_iterations": 0,
        "compact_every": 0,
        "retry_delay": 0,
        "session_timeout": 300,
        "status_file": "",
        "startup_delay": 0.0,
        "max_idle_iterations": 0,
        "evolve": False,
        "git": False,
        "git_commit": False,
        "workers": 1,
        "notify_cmd": None,
        "max_output_chars": 2000,
        "profile": "",
        "model": "",
        "provider": "",
        "http_callback": "",
        "keep_iterations": 0,
        "archive_dir": "",
        "archive_retention": 30,
        "archive_max_size": 0,
        "max_retries": 0,
        "on_error_cmd": None,
        "tag": "",
        "prompt_suffix": "",
        "max_turns": 500,
        "auto_toolsets": False,
        "failure_learning": False,
        "html_dashboard": "",
        "webhook_port": 0,
        "watch_dir": "",
        "watch_poll": 5.0,
        "worker_url": "",
        "cooldown": 0,
        "goals_file": "",
        "stop_at_goals_end": False,
        "output_schema": None,
        "cooldown_mode": "fixed",
        "convergence_threshold": 0.95,
        "convergence_window": 3,
        "convergence_stop": False,
        "store_git_diff": False,
        "notify_desktop": False,
        "notify_on_completion": False,
        "notify_pushbullet": "",
        "notify_ntfy": "",
        "notify_ntfy_server": "https://ntfy.sh",
        "use_library": False,
        "pass_session_id": False,
        "checkpoints": False,
        "resume": False,
        "resume_session_id": "",
        "skills": "",
        "ignore_rules": False,
        "yolo": False,
        "ignore_user_config": False,
        "spawn_source": "",
        "safe_mode": False,
        "accept_hooks": False,
        "worktree": False,
        "continue_session": False,
        "track_goals": False,
        "reset_goals": False,
        "heartbeat_timeout": 0,
        "quiet": True,
        "force_reset": False,
    }


class _SetupHelper:
    """Patch run_loop dependencies into ExitStack and expose mocks.

    Usage::

        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            # Access mocks: h.m["_load_goals_file"]
            run_loop(state=state, **kwargs)
    """

    def __init__(self, stack: contextlib.ExitStack, shutdown_requested: bool = False):
        self.m: dict = {}
        self._stack = stack
        self._do_patches(shutdown_requested)

    def _patch(self, name, mock_obj=None, **kw):
        if mock_obj is not None:
            m = mock_obj
        else:
            m = MagicMock(**kw)
        self.m[name] = m
        self._stack.enter_context(patch(f"hermes_loop.loop.{name}", m))
        return m

    def _do_patches(self, shutdown_requested: bool):
        # file_utils — patch at loop scope
        self.m["_log"] = self._stack.enter_context(patch("hermes_loop.loop._log"))
        self.m["write_ledger"] = self._stack.enter_context(
            patch("hermes_loop.loop.write_ledger")
        )
        self.m["write_status_file"] = self._stack.enter_context(
            patch("hermes_loop.loop.write_status_file")
        )
        # check_sentinel — local import inside run_loop; patch file_utils
        self.m["check_sentinel"] = self._stack.enter_context(
            patch("hermes_loop.file_utils.check_sentinel", return_value=None)
        )
        self.m["check_sentinel_no_remove"] = self._stack.enter_context(
            patch(
                "hermes_loop.file_utils.check_sentinel_no_remove",
                return_value=None,
            )
        )

        # _shutdown_requested — module-level bool
        self._stack.enter_context(
            patch("hermes_loop.loop._shutdown_requested", shutdown_requested)
        )

        # signal_handlers
        self._patch("init_auto_reload")
        self._patch("_check_auto_reload")
        self._patch("_build_exec_argv", return_value=["python3", "-m", "hermes_loop"])

        # goal_utils
        self._patch("GoalSpec", return_value=_GOAL_SPEC)
        self._patch("_is_goal_completed", return_value=False)
        self._patch("_mark_goal_completed")

        # error_recovery
        self._patch("_adapt_to_error", return_value=(300, 0, "fixed", False, 1, []))
        self._patch("_set_originals")

        # error_utils
        self._patch("_suggest_actionable_fix", return_value="")

        # tracker
        eta = MagicMock()
        eta.to_dict.return_value = {
            "remaining_seconds": 0,
            "remaining_formatted": "N/A",
        }
        eta.estimate_remaining.return_value = 0
        eta.format_eta.return_value = "N/A"
        self._patch("ETATracker", return_value=eta)

        # file_watcher
        self._patch("FileWatcherTrigger")

        # webhook
        self._patch("_start_webhook_server")

        # dashboard
        self._patch("_write_status_html")
        self._patch("_broadcast_to_sse_clients")

        # worker_manager
        wm = MagicMock()
        wm.start.return_value = "http://worker:8080"
        type(wm).is_running = PropertyMock(return_value=False)
        self._patch("HermesWorkerManager", return_value=wm)

        # hermes_utils
        self._patch("detect_task_type", return_value=("generic", "generic task", []))

        # git_utils
        self._patch("_capture_git_state", return_value={})
        self._patch("_git_auto_commit", return_value=None)

        # system_utils
        self._patch("get_system_usage", return_value={})
        self._patch("get_system_usage_diff", return_value={})

        # functions
        self._patch("_load_goals_file", return_value=GOALS_TUPLE_SINGLE)
        self._patch("_log_startup_banner")
        self._patch("_cycle_goal", return_value=("test goal", False))
        self._patch("_build_progressive_context", return_value="progressive context")
        self._patch("_handle_cooldown")

        # iteration
        self._patch("_execute_iteration", return_value=_SUCCESS_EXEC)
        self._patch("_merge_worker_results", return_value=dict(_SUCCESS_MERGE))
        self._patch("_handle_backoff", return_value=False)
        self._patch("_detect_convergence", return_value=False)
        self._patch("_compact_summaries", return_value=([], False))
        self._patch("_build_iteration_record", return_value=dict(_SUCCESS_RECORD))
        self._patch("_handle_notifications")
        self._patch("_handle_callbacks")
        self._patch("_sleep_with_shutdown_check", return_value=False)

        # worktree_merger
        self._patch("_merge_worktree_branches", return_value={})
        self._patch("cleanup_stale_worktrees", return_value={})
        self._patch("_cleanup_stale_remote_branches", return_value={})

        # stats
        self._patch("_recalc_stats")

        # archiving
        self._patch("_archive_iterations", return_value=True)
        self._patch("_cleanup_old_archives")
        self._patch("_enforce_archive_max_size")

        # _print_shutdown_summary is in loop.py itself
        self._patch("_print_shutdown_summary")

        # colorizer
        c = MagicMock()
        c.header.side_effect = lambda x: x
        c.value.side_effect = lambda x: x
        c.flag.side_effect = lambda x: x
        c.dim.side_effect = lambda x: x
        c.tag_ok.return_value = ""
        c.tag_fail.return_value = ""
        c.tag_summary.return_value = ""
        c.tag_suggest.return_value = ""
        c.group_title.side_effect = lambda x: x
        self._patch("colorizer", c)


# ═══════════════════════════════════════════════════════════════════
# 1. Worker auto-start  (lines 218-229)
# ═══════════════════════════════════════════════════════════════════


class TestWorkerAutoStart:
    """worker_url='auto' triggers HermesWorkerManager.start()."""

    def test_auto_start_worker(self):
        state = _make_minimal_state()
        kwargs = dict(_base_kwargs(), worker_url="auto")
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack, shutdown_requested=True)
            h.m["_load_goals_file"].return_value = GOALS_TUPLE_SINGLE
            wm = h.m["HermesWorkerManager"].return_value
            wm.start.return_value = "http://auto:8080"
            type(wm).is_running = PropertyMock(return_value=False)
            run_loop(state=state, **kwargs)

        wm = h.m["HermesWorkerManager"].return_value
        wm.start.assert_called_once()
        log_text = " ".join(str(c[0]) for c in h.m["_log"].call_args_list)
        assert "Worker URL" in log_text

    def test_auto_start_running_registers_atexit(self):
        state = _make_minimal_state()
        kwargs = dict(_base_kwargs(), worker_url="auto")
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack, shutdown_requested=True)
            h.m["_load_goals_file"].return_value = GOALS_TUPLE_SINGLE
            wm = h.m["HermesWorkerManager"].return_value
            wm.start.return_value = "http://auto:8080"
            type(wm).is_running = PropertyMock(return_value=True)
            atexit_register = stack.enter_context(
                patch("hermes_loop.loop.atexit.register")
            )
            run_loop(state=state, **kwargs)
        atexit_register.assert_called_once()

    def test_auto_start_not_running_skips_atexit(self):
        state = _make_minimal_state()
        kwargs = dict(_base_kwargs(), worker_url="auto")
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack, shutdown_requested=True)
            h.m["_load_goals_file"].return_value = GOALS_TUPLE_SINGLE
            wm = h.m["HermesWorkerManager"].return_value
            wm.start.return_value = "http://auto:8080"
            type(wm).is_running = PropertyMock(return_value=False)
            atexit_register = stack.enter_context(
                patch("hermes_loop.loop.atexit.register")
            )
            run_loop(state=state, **kwargs)
        atexit_register.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# 2. Startup delay  (lines 342-346)
# ═══════════════════════════════════════════════════════════════════


class TestStartupDelay:
    """startup_delay > 0 calls _sleep_with_shutdown_check."""

    def test_delay_triggers_sleep(self):
        state = _make_minimal_state()
        kwargs = dict(_base_kwargs(), startup_delay=5.0)
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack, shutdown_requested=True)
            run_loop(state=state, **kwargs)
        h.m["_sleep_with_shutdown_check"].assert_called_once_with(5.0)

    def test_delay_skipped_when_already_run(self):
        state = _make_minimal_state(total_iterations=5)
        kwargs = dict(_base_kwargs(), startup_delay=5.0)
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack, shutdown_requested=True)
            run_loop(state=state, **kwargs)
        h.m["_sleep_with_shutdown_check"].assert_not_called()

    def test_shutdown_during_delay_returns_early(self):
        state = _make_minimal_state()
        kwargs = dict(_base_kwargs(), startup_delay=5.0)
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            h.m["_sleep_with_shutdown_check"].return_value = True
            run_loop(state=state, **kwargs)
        log_text = " ".join(str(c[0]) for c in h.m["_log"].call_args_list)
        assert "Shutdown during startup delay" in log_text


# ═══════════════════════════════════════════════════════════════════
# 3. Auto-reload init  (line 349)
# ═══════════════════════════════════════════════════════════════════


class TestAutoReloadInit:
    """init_auto_reload is called before the main loop."""

    def test_init_auto_reload_called(self):
        state = _make_minimal_state()
        kwargs = dict(_base_kwargs(), workdir="/tmp/test")
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack, shutdown_requested=True)
            run_loop(state=state, **kwargs)
        h.m["init_auto_reload"].assert_called_once_with("/tmp/test")


# ═══════════════════════════════════════════════════════════════════
# 4. Shutdown signal in main loop  (lines 352-363)
# ═══════════════════════════════════════════════════════════════════


class TestShutdownSignal:
    """_shutdown_requested=True at loop entry triggers stop."""

    def test_shutdown_exits_immediately(self):
        state = _make_minimal_state()
        kwargs = _base_kwargs()
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack, shutdown_requested=True)
            run_loop(state=state, **kwargs)
        assert "stopped: signal" in state["status"]
        log_text = " ".join(str(c[0]) for c in h.m["_log"].call_args_list)
        assert "Shutdown signal" in log_text
        h.m["write_ledger"].assert_called()
        h.m["_broadcast_to_sse_clients"].assert_called()


# ═══════════════════════════════════════════════════════════════════
# 5. Sentinel pause / resume / stop  (lines 369-427)
# ═══════════════════════════════════════════════════════════════════


class TestSentinelPauseStop:
    """Sentinel with 'pause' then 'stop' stops immediately."""

    def test_pause_then_stop_inner_loop(self):
        state = _make_minimal_state()
        kwargs = dict(_base_kwargs(), sentinel_path="/tmp/sentinel")
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            h.m["check_sentinel"].return_value = "pause"
            h.m["check_sentinel_no_remove"].return_value = "stop"
            stack.enter_context(patch("hermes_loop.loop.os.remove"))
            run_loop(state=state, **kwargs)
        assert "paused-stop" in state.get("status", "")
        log_text = " ".join(str(c[0]) for c in h.m["_log"].call_args_list)
        assert "PAUSE" in log_text
        assert "STOP" in log_text
        assert "Sentinel contains 'stop' during pause" in log_text


class TestSentinelPauseResume:
    """Sentinel 'pause' then removal resumes."""

    def test_pause_then_resume_via_removal(self):
        state = _make_minimal_state()
        kwargs = dict(_base_kwargs(), sentinel_path="/tmp/sentinel")
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            # First check: "pause" enters inner loop
            # After resume, main loop runs again: return "stop" to exit
            sentinel_responses = ["pause", "stop"]

            def sentinel_side(*a):
                return sentinel_responses.pop(0) if sentinel_responses else None

            h.m["check_sentinel"].side_effect = sentinel_side
            no_remove_calls = [0]

            def no_remove_side(*a):
                no_remove_calls[0] += 1
                if no_remove_calls[0] <= 1:
                    return "pause"
                return None

            h.m["check_sentinel_no_remove"].side_effect = no_remove_side
            run_loop(state=state, **kwargs)
        log_text = " ".join(str(c[0]) for c in h.m["_log"].call_args_list)
        assert "PAUSE" in log_text
        assert "RESUME" in log_text


class TestSentinelStop:
    """Sentinel with non-pause content stops directly."""

    def test_sentinel_stop_direct(self):
        state = _make_minimal_state()
        kwargs = dict(_base_kwargs(), sentinel_path="/tmp/sentinel")
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            h.m["check_sentinel"].return_value = "stop"
            run_loop(state=state, **kwargs)
        assert "stopped: stop" in state["status"]


# ═══════════════════════════════════════════════════════════════════
# 6. Max iterations  (lines 429-446)
# ═══════════════════════════════════════════════════════════════════


class TestMaxIterations:
    """max_iterations > 0 stops when iteration_count >= max_iterations."""

    def test_max_iterations_reached(self):
        state = _make_minimal_state(total_iterations=5)
        kwargs = dict(_base_kwargs(), max_iterations=5)
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            run_loop(state=state, **kwargs)
        assert "max_iterations" in state["status"]
        log_text = " ".join(str(c[0]) for c in h.m["_log"].call_args_list)
        assert "max_iterations" in log_text


# ═══════════════════════════════════════════════════════════════════
# 7. Max idle iterations  (lines 448-463)
# ═══════════════════════════════════════════════════════════════════


class TestMaxIdleIterations:
    """max_idle_iterations > 0 stops on consecutive idle."""

    def test_idle_stop(self):
        state = _make_minimal_state(total_iterations=0)
        kwargs = dict(_base_kwargs(), max_idle_iterations=3, git=True)
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            h.m["_capture_git_state"].return_value = {
                "diff_stat": "",
                "diff_stat_cached": "",
                "head": "abc123",
            }
            h.m["_merge_worker_results"].return_value = dict(_SUCCESS_MERGE)
            h.m["_cycle_goal"].return_value = ("test goal", False)
            run_loop(state=state, **kwargs)
        assert "idle" in state.get("status", "")


# ═══════════════════════════════════════════════════════════════════
# 8. Goal cycling and goals-exhausted  (lines 491-523)
# ═══════════════════════════════════════════════════════════════════


class TestGoalCycling:
    """Multiple goals; cycling and exhaustion."""

    def test_goals_exhausted_stops(self):
        state = _make_minimal_state(total_iterations=0)
        kwargs = dict(_base_kwargs(), goals_file="/tmp/test_g.txt")
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            h.m["_load_goals_file"].return_value = GOALS_TUPLE_DOUBLE
            h.m["_cycle_goal"].return_value = ("g1", True)
            run_loop(state=state, **kwargs)
        assert "goals-exhausted" in state["status"]


# ═══════════════════════════════════════════════════════════════════
# 9. need_reload auto-reload  (lines 761-782)
# ═══════════════════════════════════════════════════════════════════


class TestNeedReload:
    """'need_reload' in next_goal triggers os.execv."""

    def test_need_reload_triggers_execv(self):
        """os.execv is called and status becomes 'reloading'."""
        state = _make_minimal_state(total_iterations=0)
        kwargs = _base_kwargs()
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            merge = dict(_SUCCESS_MERGE)
            merge["next_goal"] = "need_reload"
            h.m["_merge_worker_results"].return_value = merge
            h.m["_build_iteration_record"].return_value = dict(
                _SUCCESS_RECORD, classification="completed"
            )
            # Unset HERMES_LOOP_NO_AUTO_RELOAD so the reload path is taken
            old_env = os.environ.pop("HERMES_LOOP_NO_AUTO_RELOAD", None)
            mock_execv = stack.enter_context(
                patch("hermes_loop.loop.os.execv", side_effect=SystemExit(0))
            )
            with pytest.raises(SystemExit):
                run_loop(state=state, **kwargs)
            if old_env is not None:
                os.environ["HERMES_LOOP_NO_AUTO_RELOAD"] = old_env
        mock_execv.assert_called_once()
        assert state["status"] == "reloading"

    def test_need_reload_with_worker_manager(self):
        """Worker manager is stopped before execv when present."""
        state = _make_minimal_state(total_iterations=0)
        kwargs = dict(_base_kwargs(), worker_url="auto", max_iterations=1)
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            merge = dict(_SUCCESS_MERGE)
            merge["next_goal"] = "need_reload"
            h.m["_merge_worker_results"].return_value = merge
            h.m["_build_iteration_record"].return_value = dict(
                _SUCCESS_RECORD, classification="completed"
            )
            wm = h.m["HermesWorkerManager"].return_value
            type(wm).is_running = PropertyMock(return_value=True)
            old_env = os.environ.pop("HERMES_LOOP_NO_AUTO_RELOAD", None)
            mock_execv = stack.enter_context(patch("hermes_loop.loop.os.execv"))
            run_loop(state=state, **kwargs)
            if old_env is not None:
                os.environ["HERMES_LOOP_NO_AUTO_RELOAD"] = old_env
        mock_execv.assert_called_once()
        wm.stop.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# 10. Keep iterations archiving  (lines 951-977)
# ═══════════════════════════════════════════════════════════════════


class TestKeepIterationsArchiving:
    """keep_iterations > 0 triggers archiving."""

    def test_archiving_triggered(self):
        existing = [
            {"n": i, "summary": f"iter {i}", "duration_seconds": 1} for i in range(10)
        ]
        state = _make_minimal_state(
            total_iterations=10,
            iterations=existing,
        )
        kwargs = dict(_base_kwargs(), keep_iterations=3, max_iterations=11)
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            run_loop(state=state, **kwargs)
        h.m["_archive_iterations"].assert_called()
        assert len(state["iterations"]) <= 3

    def test_archiving_not_triggered_under_threshold(self):
        existing = [
            {"n": i, "summary": f"iter {i}", "duration_seconds": 1} for i in range(3)
        ]
        state = _make_minimal_state(
            total_iterations=3,
            iterations=existing,
        )
        kwargs = dict(_base_kwargs(), keep_iterations=3, max_iterations=4)
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            run_loop(state=state, **kwargs)
        h.m["_archive_iterations"].assert_not_called()

    def test_archiving_exception_handled(self):
        """Exception during archiving is caught and logged."""
        existing = [
            {"n": i, "summary": f"iter {i}", "duration_seconds": 1} for i in range(10)
        ]
        state = _make_minimal_state(
            total_iterations=10,
            iterations=existing,
        )
        kwargs = dict(_base_kwargs(), keep_iterations=3, max_iterations=11)
        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            h.m["_archive_iterations"].side_effect = Exception("disk full")
            run_loop(state=state, **kwargs)
        log_text = " ".join(str(c[0]) for c in h.m["_log"].call_args_list)
        assert "Failed to archive" in log_text
        assert "disk full" in log_text


# ═══════════════════════════════════════════════════════════════════
# 11. Mitigation level >= 3 persistent failure  (lines 1037-1050)
# ═══════════════════════════════════════════════════════════════════


class TestMitigationLevelStop:
    """mitigation_level >= 3 triggers persistent failure stop."""

    def test_mitigation_level_3_stops(self):
        state = _make_minimal_state(
            total_iterations=0,
            mitigations={"mitigation_level": 3},
            error_type_counts={"timeout": 5},
        )
        kwargs = _base_kwargs()
        error_merge = dict(_SUCCESS_MERGE)
        error_merge["combined_error"] = "persistent timeout"
        error_merge["primary_error_type"] = "timeout"
        error_merge["consecutive_errors"] = 5
        error_merge["consecutive_successes"] = 0

        with contextlib.ExitStack() as stack:
            h = _SetupHelper(stack)
            h.m["_merge_worker_results"].return_value = error_merge
            h.m["_build_iteration_record"].return_value = dict(
                _SUCCESS_RECORD,
                error="timeout",
                classification="error",
            )
            h.m["_handle_backoff"].return_value = False
            run_loop(state=state, **kwargs)

        assert "timeout" in state["status"]
        assert "failure" in state["status"]
        log_text = " ".join(str(c[0]) for c in h.m["_log"].call_args_list)
        assert "Persistent failure" in log_text
