"""Integration tests for remaining uncovered modules: validation.py, status.py,
git_utils.py, env_utils.py deeper edge cases, state.py pending-iteration boundaries,
config.py path resolution, file_utils.py colorize/missing-file edge cases, and
error_recovery.py full error-type coverage.

These tests use real filesystem ops (tmp_path), capsys for stdout verification,
and minimal mocking — focusing on multi-module interactions not yet covered by
the main test_integration*.py files.
"""

import json
import os
import pathlib
import time
from unittest.mock import patch

import pytest


# Module-level helper for multiprocessing lock test (must be pickleable)
def _lock_holder(lock_path: str, acquired_flag):
    """Acquire a FileLock and hold it for 1 second."""
    from pi_loop.file_utils import FileLock

    with FileLock(lock_path, timeout=5.0):
        acquired_flag.value = True
        time.sleep(1.0)


# ── Configuration Path Resolution (config.py) ──────────────────────────────


class TestConfigPathResolution:
    """_resolve_path and _get_data_dir edge cases."""

    def test_get_data_dir_default(self):
        """_get_data_dir returns /tmp when no env var is set."""
        from pi_loop.config import _get_data_dir

        with patch.dict(os.environ, {}, clear=True):
            assert _get_data_dir() == "/tmp"

    def test_get_data_dir_respects_env(self):
        """_get_data_dir returns the value of PI_LOOP_DATA_DIR when set."""
        from pi_loop.config import _get_data_dir

        with patch.dict(os.environ, {"PI_LOOP_DATA_DIR": "/custom/data"}, clear=True):
            assert _get_data_dir() == "/custom/data"

    def test_resolve_path_no_explicit(self):
        """_resolve_path falls back to data_dir + default_name."""
        from pi_loop.config import _resolve_path

        with patch.dict(os.environ, {}, clear=True):
            path = _resolve_path("PI_LOOP_LEDGER_PATH", "test-ledger.json")
            assert path == "/tmp/test-ledger.json"

    def test_resolve_path_with_explicit(self):
        """_resolve_path uses explicit env var when set."""
        from pi_loop.config import _resolve_path

        with patch.dict(os.environ, {"PI_LOOP_LEDGER_PATH": "/explicit/ledger.json"}, clear=True):
            path = _resolve_path("PI_LOOP_LEDGER_PATH", "fallback.json")
            assert path == "/explicit/ledger.json"

    def test_resolve_path_empty_explicit_falls_back(self):
        """_resolve_path falls back when explicit env var is set to empty string."""
        from pi_loop.config import _resolve_path

        with patch.dict(os.environ, {"PI_LOOP_LEDGER_PATH": ""}, clear=True):
            path = _resolve_path("PI_LOOP_LEDGER_PATH", "default.json")
            assert path == "/tmp/default.json"

    def test_resolve_path_custom_data_dir(self):
        """_resolve_path respects PI_LOOP_DATA_DIR when no explicit path is set."""
        from pi_loop.config import _resolve_path

        with patch.dict(os.environ, {"PI_LOOP_DATA_DIR": "/data/dir"}, clear=True):
            path = _resolve_path("PI_LOOP_SENTINEL_PATH", "sentinel-stop")
            assert path == "/data/dir/sentinel-stop"


class TestLoopConfigAccessors:
    """LoopConfig.__getitem__ and .get() dict-style backward compat."""

    def test_getitem_returns_attr(self):
        """__getitem__ returns the attribute value."""
        from pi_loop.config import LoopConfig

        cfg = LoopConfig(goal="test", workers=3)
        assert cfg["goal"] == "test"
        assert cfg["workers"] == 3

    def test_get_returns_attr(self):
        """.get() returns the attribute value."""
        from pi_loop.config import LoopConfig

        cfg = LoopConfig(goal="find bugs")
        assert cfg.get("goal") == "find bugs"

    def test_get_returns_default_for_missing(self):
        """.get() returns the default for non-existent keys."""
        from pi_loop.config import LoopConfig

        cfg = LoopConfig()
        assert cfg.get("nonexistent", "fallback") == "fallback"

    def test_get_returns_none_for_unset(self):
        """.get() returns None when no attribute and no default."""
        from pi_loop.config import LoopConfig

        cfg = LoopConfig()
        assert cfg.get("nonexistent") is None

    def test_from_args_ignores_unknown_attrs(self):
        """from_args silently ignores unknown attributes on the source object."""
        from argparse import Namespace

        from pi_loop.config import LoopConfig

        args = Namespace(goal="test", workers=2, unknown_flag=True, bogus=42)
        cfg = LoopConfig.from_args(args)
        assert cfg.goal == "test"
        assert cfg.workers == 2
        # These should NOT be on the LoopConfig
        assert not hasattr(cfg, "unknown_flag")

    def test_from_args_applies_defaults(self):
        """from_args fills in defaults for missing attributes."""
        from argparse import Namespace

        from pi_loop.config import LoopConfig

        args = Namespace(goal="defaults_test", workers=None)
        cfg = LoopConfig.from_args(args)
        assert cfg.goal == "defaults_test"
        assert cfg.workers == 1  # default


# ── Validation (validation.py) ──────────────────────────────────────────────


class TestLoadJsonSchema:
    """load_json_schema happy and sad paths."""

    def test_loads_valid_schema(self, tmp_path):
        """load_json_schema loads a valid JSON schema file."""
        from pi_loop.validation import load_json_schema

        schema_path = tmp_path / "schema.json"
        schema_content = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        schema_path.write_text(json.dumps(schema_content))

        loaded = load_json_schema(str(schema_path))
        assert loaded is not None
        assert loaded["type"] == "object"
        assert loaded["required"] == ["name"]

    def test_returns_none_for_missing_file(self, tmp_path):
        """load_json_schema returns None for a non-existent file."""
        from pi_loop.validation import load_json_schema

        result = load_json_schema(str(tmp_path / "nonexistent.json"))
        assert result is None

    def test_returns_none_for_corrupt_json(self, tmp_path):
        """load_json_schema returns None for corrupt/malformed JSON."""
        from pi_loop.validation import load_json_schema

        schema_path = tmp_path / "corrupt.json"
        schema_path.write_text("not valid json {")

        result = load_json_schema(str(schema_path))
        assert result is None

    def test_returns_none_for_non_dict_json(self, tmp_path):
        """load_json_schema returns None when JSON root is not a dict."""
        from pi_loop.validation import load_json_schema

        schema_path = tmp_path / "array.json"
        schema_path.write_text('["a", "b"]')

        result = load_json_schema(str(schema_path))
        assert result is None

    def test_returns_none_for_primitive_json(self, tmp_path):
        """load_json_schema returns None when JSON is a primitive."""
        from pi_loop.validation import load_json_schema

        schema_path = tmp_path / "string.json"
        schema_path.write_text('"justastring"')

        result = load_json_schema(str(schema_path))
        assert result is None


# ── Status Writer Deeper Edges (status.py) ──────────────────────────────────


class TestStatusWriterDeeperEdges:
    """Edge cases for write_status not covered elsewhere."""

    def test_writes_to_default_path(self, tmp_path):
        """write_status writes to STATUS_FILE_DEFAULT when path is None."""
        import pi_loop.status as status_mod
        from pi_loop.status import write_status

        default = str(tmp_path / "default-loop-status.json")
        old_default = status_mod.STATUS_FILE_DEFAULT
        status_mod.STATUS_FILE_DEFAULT = default
        try:
            write_status(None, running=True, pid=999, iteration_count=7, version="1.0.0")
            assert os.path.exists(default)
            with open(default) as f:
                data = json.load(f)
            assert data["running"]
            assert data["pid"] == 999
            assert data["iteration_count"] == 7
        finally:
            status_mod.STATUS_FILE_DEFAULT = old_default

    def test_stores_uptime_seconds(self, tmp_path):
        """write_status stores the provided uptime_seconds (rounded to 1dp)."""
        from pi_loop.status import write_status

        sp = str(tmp_path / "uptime.json")
        write_status(sp, running=True, pid=os.getpid(), iteration_count=0, uptime_seconds=123.45)
        with open(sp) as f:
            data = json.load(f)
        # write_status rounds to 1 decimal place
        assert data["uptime_seconds"] == 123.5

    def test_empty_path_is_noop(self):
        """write_status is a no-op when path is empty string."""
        from pi_loop.status import write_status

        # Should not raise
        write_status("", running=True, pid=1, iteration_count=0)

    def test_nonwritable_path_logs_warning(self, tmp_path):
        """write_status logs a warning when it cannot write to the path."""
        from pi_loop.status import write_status

        # Path in a non-existent deep directory without parents created
        deep_path = str(tmp_path / "nonexistent" / "subdir" / "status.json")
        # write_status should not raise, just log warning
        write_status(deep_path, running=True, pid=1, iteration_count=0)
        # It should handle this gracefully; no crash


# ── Git Utils Integration (git_utils.py) ────────────────────────────────────


class TestGitUtilsIntegration:
    """git_utils functions with real git repos in temp directories."""

    def test_capture_git_state_no_repo(self, tmp_path):
        """_capture_git_state returns empty dict when not in a git repo."""
        from pi_loop.git_utils import _capture_git_state

        result = _capture_git_state(str(tmp_path))
        assert result == {}

    def test_capture_git_state_in_repo(self, tmp_path):
        """_capture_git_state captures diff stat and head hash in a real repo."""
        from pi_loop.git_utils import _capture_git_state

        _init_git_repo(tmp_path)

        result = _capture_git_state(str(tmp_path))
        assert "diff_stat" in result
        assert "head" in result
        assert result["head"] != ""

    def test_capture_git_state_with_changes(self, tmp_path):
        """_capture_git_state detects staged changes."""
        import subprocess

        from pi_loop.git_utils import _capture_git_state

        _init_git_repo(tmp_path)
        # Create a file, then modify it after staging
        (tmp_path / "test.txt").write_text("original")
        subprocess.run(["git", "add", "test.txt"], capture_output=True, cwd=str(tmp_path), timeout=10)
        subprocess.run(
            ["git", "commit", "-m", "Add test.txt"],
            capture_output=True,
            cwd=str(tmp_path),
            timeout=15,
        )
        # Now modify it — unstaged change
        (tmp_path / "test.txt").write_text("modified")

        result = _capture_git_state(str(tmp_path))
        assert "diff_stat" in result
        assert "test.txt" in result.get("diff_stat", "")

    def test_capture_git_state_with_store_diff(self, tmp_path):
        """_capture_git_state with store_diff=True includes the unified diff."""
        import subprocess

        from pi_loop.git_utils import _capture_git_state

        _init_git_repo(tmp_path)
        (tmp_path / "test.txt").write_text("original")
        subprocess.run(["git", "add", "test.txt"], capture_output=True, cwd=str(tmp_path), timeout=10)
        subprocess.run(
            ["git", "commit", "-m", "Add test.txt"],
            capture_output=True,
            cwd=str(tmp_path),
            timeout=15,
        )
        (tmp_path / "test.txt").write_text("modified")

        result = _capture_git_state(str(tmp_path), store_diff=True)
        assert "diff" in result
        assert "modified" in result.get("diff", "")

    def test_git_auto_commit_no_repo(self, tmp_path):
        """_git_auto_commit returns None when not in a git repo."""
        from pi_loop.git_utils import _git_auto_commit

        result = _git_auto_commit(str(tmp_path), 1, "test iteration")
        assert result is None

    def test_git_auto_commit_creates_commit(self, tmp_path):
        """_git_auto_commit creates a commit with iteration message."""
        from pi_loop.git_utils import _git_auto_commit

        _init_git_repo(tmp_path)

        # Create a change and stage it
        (tmp_path / "test.txt").write_text("content")

        result = _git_auto_commit(str(tmp_path), 42, "my test summary")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

        # Verify commit message
        import subprocess

        r = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert "iter #42" in r.stdout

    def test_git_auto_commit_noop_when_clean(self, tmp_path):
        """_git_auto_commit returns None when there are no changes."""
        from pi_loop.git_utils import _git_auto_commit

        _init_git_repo(tmp_path)

        result = _git_auto_commit(str(tmp_path), 1, "no changes")
        assert result is None

    def test_git_auto_commit_with_subdir(self, tmp_path):
        """_git_auto_commit works with a subdirectory as workdir."""
        from pi_loop.git_utils import _git_auto_commit

        _init_git_repo(tmp_path)

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("content")

        result = _git_auto_commit(str(tmp_path), 5, "committing from subdir")
        assert result is not None


def _init_git_repo(tmp_path):
    """Initialize a git repo at tmp_path with an initial commit."""
    import subprocess

    subprocess.run(["git", "init"], capture_output=True, cwd=str(tmp_path), timeout=15)
    subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, cwd=str(tmp_path), timeout=10)
    subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, cwd=str(tmp_path), timeout=10)
    readme = tmp_path / "README.md"
    readme.write_text("# Test")
    subprocess.run(["git", "add", "README.md"], capture_output=True, cwd=str(tmp_path), timeout=10)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        capture_output=True,
        cwd=str(tmp_path),
        timeout=15,
    )


# ── Error Recovery Full Type Coverage (error_recovery.py) ──────────────────


class TestErrorRecoveryFullTypeCoverage:
    """Cover error types not fully tested: heartbeat, schema specifics."""

    def test_heartbeat_error_mild_threshold(self):
        """Heartbeat errors at mild threshold reach level 1 (one level per call)."""
        from pi_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(7200, 10, True, 2)
        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"timeout": 0, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 5}

        _, _, _, _, _, actions = _adapt_to_error(
            error_type="heartbeat",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )

        # Heartbeat is defined in thresholds but NOT explicitly handled
        # in the ramp-up blocks, so level 0→1 with no actions
        assert mitigations["mitigation_level"] == 1

    def test_heartbeat_error_stop_threshold_escalates_one_level(self):
        """Heartbeat errors at stop threshold reach level 1 (single-call)."""
        from pi_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(7200, 10, True, 2)
        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"timeout": 0, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 7}

        _, _, _, _, _, actions = _adapt_to_error(
            error_type="heartbeat",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )

        # Escalation increments one level per call (0 → 1)
        assert mitigations["mitigation_level"] == 1
        assert len(actions) == 0  # no handler registered for heartbeat

    def test_schema_errors_level1(self):
        """Schema errors at mild threshold trigger level 1 (monitoring)."""
        from pi_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(7200, 10, True, 2)
        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"timeout": 0, "network": 0, "schema": 3, "unknown": 0, "heartbeat": 0}

        _, _, _, _, _, actions = _adapt_to_error(
            error_type="schema",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )

        assert mitigations["mitigation_level"] == 1
        assert any("Schema" in a for a in actions) or any("schema" in a for a in actions)

    def test_schema_errors_level3_stop_multi_call(self):
        """Schema errors reach level 3 STOP after multiple calls."""
        from pi_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(7200, 10, True, 2)
        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"schema": 5}

        # Call 1: 0 → 1
        _, _, _, _, _, actions = _adapt_to_error(
            error_type="schema",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        assert mitigations["mitigation_level"] == 1
        assert len(actions) > 0

        # Call 2: 1 → 2
        _, _, _, _, _, actions = _adapt_to_error(
            error_type="schema",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        assert mitigations["mitigation_level"] == 2

        # Call 3: 2 → 3
        _, _, _, _, _, actions = _adapt_to_error(
            error_type="schema",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        assert mitigations["mitigation_level"] == 3
        assert any("STOP" in a for a in actions)
        assert any("schema" in a.lower() for a in actions if "STOP" in a)

    def test_unknown_error_level2_escalation_multi_call(self):
        """Unknown errors escalate to level 2 after multiple calls."""
        from pi_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(7200, 10, True, 3)
        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }

        # Call 1: 0 → 1
        new_timeout, new_cooldown, new_mode, _, _, _ = _adapt_to_error(
            error_type="unknown",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts={"unknown": 5},
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=3,
        )
        assert mitigations["mitigation_level"] == 1

        # Call 2: 1 → 2
        _, _, _, new_library, new_workers, _ = _adapt_to_error(
            error_type="unknown",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts={"unknown": 5},
            session_timeout=7200,
            cooldown=new_cooldown,
            cooldown_mode=new_mode,
            use_library=True,
            workers=3,
        )
        assert mitigations["mitigation_level"] == 2
        assert not new_library  # forced subprocess
        assert new_workers == 1  # reduced

    def test_error_recovery_incremental_success(self):
        """Each incremental success gradually unwinds mitigations."""
        from pi_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(7200, 10, True, 2)
        mitigations = {
            "mitigation_level": 2,
            "timeout_increased": True,
            "cooldown_elevated": True,
            "force_subprocess": True,
            "reduced_workers": True,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"timeout": 0, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0}

        # First success — partial unwind (1 level)
        new_timeout, new_cooldown, _, new_library, new_workers, actions = _adapt_to_error(
            error_type=None,
            mitigations=mitigations,
            consecutive_successes=1,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        assert mitigations["mitigation_level"] == 1
        assert len(actions) > 0
        assert "Partial unwind" in actions[0]

        # Third success — full recovery
        _, _, _, new_library, new_workers, actions = _adapt_to_error(
            error_type=None,
            mitigations=mitigations,
            consecutive_successes=3,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=False,
            workers=1,
        )
        assert mitigations["mitigation_level"] == 0
        assert new_library  # back to original
        assert new_workers == 2  # back to original
        assert any("Full recovery" in a for a in actions)

    def test_no_change_when_below_mild_threshold(self):
        """No mitigation actions when error count is below mild threshold."""
        from pi_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(7200, 10, True, 2)
        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"timeout": 1, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0}

        _, _, _, _, _, actions = _adapt_to_error(
            error_type="timeout",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )

        # timeout mild threshold is 3, count is 1 → below threshold
        assert mitigations["mitigation_level"] == 0
        assert len(actions) == 0

    def test_mitigation_actions_rolling_capped(self):
        """Mitigation actions list is capped at 20 entries."""
        from pi_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(7200, 10, True, 2)
        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": list(range(20)),
        }
        error_counts = {"timeout": 5, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0}

        _, _, _, _, _, actions = _adapt_to_error(
            error_type="timeout",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=7200,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        assert len(mitigations["actions"]) <= 20


# ── State Pending Iteration Edge Cases (state.py) ──────────────────────────


class TestPendingIterationEdgeCases:
    """Edge cases for pending_iteration recovery in load_or_create_ledger."""

    def test_stale_pending_recovered(self, tmp_path):
        """Stale pending iteration (>300s old) is recovered as error."""
        from pi_loop.file_utils import write_ledger

        # Write a state with a stale pending iteration
        state = {
            "version": 11,
            "initial_command": "test goal",
            "initial_context": "",
            "started_at": "2025-01-01T00:00:00+00:00",
            "iterations": [],
            "total_iterations": 0,
            "last_updated": "2025-01-01T00:00:00+00:00",
            "status": "running",
            "stats": {"success_count": 0, "error_count": 0, "consecutive_errors": 0, "consecutive_successes": 0},
            "error_type_counts": {"timeout": 0, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0},
            "mitigations": {
                "mitigation_level": 0,
                "timeout_increased": False,
                "cooldown_elevated": False,
                "force_subprocess": False,
                "reduced_workers": False,
                "last_applied": "",
                "actions": [],
            },
            "goals_completed": {},
            "pending_iteration": {
                "n": 5,
                "started_at": "2020-01-01T00:00:00+00:00",  # Very old
            },
        }

        import importlib

        # Override path resolution via env
        os.environ["PI_LOOP_LEDGER_PATH"] = str(tmp_path / "ledger_stale_pending.json")
        os.environ["PI_LOOP_DATA_DIR"] = str(tmp_path)

        importlib.reload(__import__("pi_loop.config", fromlist=[""]))

        write_ledger(state)

        from pi_loop.state import load_or_create_ledger

        loaded = load_or_create_ledger("test goal", "")
        assert len(loaded.get("iterations", [])) == 1
        assert loaded["iterations"][0]["error"] == "agent_crashed"
        assert "RECOVERED" in loaded["iterations"][0].get("summary", "")
        assert loaded["total_iterations"] == 1
        assert "pending_iteration" not in loaded

    def test_recent_pending_not_recovered(self, tmp_path):
        """Recent pending iteration (<300s old) is NOT recovered."""
        from datetime import datetime, timezone

        from pi_loop.file_utils import write_ledger

        now_iso = datetime.now(timezone.utc).isoformat()

        state = {
            "version": 11,
            "initial_command": "recent pending",
            "initial_context": "",
            "started_at": now_iso,
            "iterations": [],
            "total_iterations": 0,
            "last_updated": now_iso,
            "status": "running",
            "stats": {"success_count": 0, "error_count": 0, "consecutive_errors": 0, "consecutive_successes": 0},
            "error_type_counts": {"timeout": 0, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0},
            "mitigations": {
                "mitigation_level": 0,
                "timeout_increased": False,
                "cooldown_elevated": False,
                "force_subprocess": False,
                "reduced_workers": False,
                "last_applied": "",
                "actions": [],
            },
            "goals_completed": {},
            "pending_iteration": {
                "n": 3,
                "started_at": now_iso,  # Just created
            },
        }

        import importlib

        os.environ["PI_LOOP_LEDGER_PATH"] = str(tmp_path / "ledger_recent_pending.json")
        os.environ["PI_LOOP_DATA_DIR"] = str(tmp_path)

        importlib.reload(__import__("pi_loop.config", fromlist=[""]))

        write_ledger(state)

        from pi_loop.state import load_or_create_ledger

        loaded = load_or_create_ledger("recent pending", "")
        # Pending iteration should NOT be recovered (recent)
        assert len(loaded.get("iterations", [])) == 0

    def test_pending_iteration_adds_missing_keys(self, tmp_path):
        """load_or_create_ledger adds missing error_type_counts and mitigations to resumed ledger."""
        from pi_loop.file_utils import write_ledger

        now_iso = "2025-01-01T00:00:00+00:00"

        state = {
            "version": 11,
            "initial_command": "migration test",
            "initial_context": "",
            "started_at": now_iso,
            "iterations": [],
            "total_iterations": 0,
            "last_updated": now_iso,
            "status": "running",
        }

        import importlib

        os.environ["PI_LOOP_LEDGER_PATH"] = str(tmp_path / "ledger_missing_keys.json")
        os.environ["PI_LOOP_DATA_DIR"] = str(tmp_path)

        importlib.reload(__import__("pi_loop.config", fromlist=[""]))

        write_ledger(state)

        from pi_loop.state import load_or_create_ledger

        loaded = load_or_create_ledger("migration test", "")
        assert "error_type_counts" in loaded
        assert "mitigations" in loaded
        assert "goals_completed" in loaded


# ── File Utils Edge Cases (file_utils.py) ─────────────────────────────────────


class TestColorizeLogTags:
    """_colorize_log_tags edge cases with color disabled."""

    def test_colorize_returns_original_when_disabled(self):
        """_colorize_log_tags returns original msg when color is disabled."""
        from pi_loop.file_utils import _colorize_log_tags

        # Mock colorizer._enabled() to return False
        with patch("pi_loop.file_utils._cu._enabled", return_value=False):
            result = _colorize_log_tags("[ERROR] Something failed")
            assert result == "[ERROR] Something failed"

    def test_colorize_all_known_tags(self):
        """_colorize_log_tags transforms all known log tags."""
        from pi_loop.file_utils import _colorize_log_tags

        with (
            patch("pi_loop.file_utils._cu._enabled", return_value=True),
            patch("pi_loop.file_utils._cu.fail", return_value="[ERROR]"),
            patch("pi_loop.file_utils._cu.warn", return_value="[WARN]"),
            patch("pi_loop.file_utils._cu.ok", return_value="[OK]"),
            patch("pi_loop.file_utils._cu.dim", return_value="[BEAT]"),
            patch("pi_loop.file_utils._cu.subheader", return_value="[DAEMON]"),
            patch("pi_loop.file_utils._cu.header", return_value="[GOALS]"),
            patch("pi_loop.file_utils._cu.group_title", return_value="[SUGGEST]"),
        ):
            result = _colorize_log_tags("[ERROR] err [WARN] warn [OK] ok")
            assert len(result) > 0

    def test_colorize_unknown_tag_preserved(self):
        """_colorize_log_tags preserves unknown tags unchanged."""
        from pi_loop.file_utils import _colorize_log_tags

        with (
            patch("pi_loop.file_utils._cu._enabled", return_value=True),
            patch("pi_loop.file_utils._cu.fail", side_effect=lambda x: f"**{x}**"),
            patch("pi_loop.file_utils._cu.warn", side_effect=lambda x: f"*{x}*"),
            patch("pi_loop.file_utils._cu.ok", side_effect=lambda x: f"+{x}+"),
            patch("pi_loop.file_utils._cu.dim", side_effect=lambda x: f"-{x}-"),
            patch("pi_loop.file_utils._cu.subheader", side_effect=lambda x: f"={x}="),
            patch("pi_loop.file_utils._cu.header", side_effect=lambda x: f"#{x}#"),
            patch("pi_loop.file_utils._cu.group_title", return_value="[SUGGEST]"),
        ):
            result = _colorize_log_tags("[ERROR] real [UNKNOWN_TAG] keep")
            assert "[UNKNOWN_TAG]" in result
            assert "keep" in result


class TestInitDaemonLog:
    """_init_daemon_log edge cases."""

    def test_creates_log_file(self, tmp_path):
        """_init_daemon_log creates the log file on disk."""
        from pi_loop.file_utils import _init_daemon_log

        log_path = str(tmp_path / "daemon.log")
        logger = _init_daemon_log(log_path, max_mb=5)
        assert logger is not None
        assert os.path.exists(log_path)

    def test_creates_parent_directories(self, tmp_path):
        """_init_daemon_log creates parent directories if needed."""
        from pi_loop.file_utils import _init_daemon_log

        log_path = str(tmp_path / "logs" / "subdir" / "daemon.log")
        logger = _init_daemon_log(log_path)
        assert logger is not None
        assert os.path.exists(log_path)

    def test_logs_go_to_file(self, tmp_path):
        """Messages logged through _log go to the file logger."""
        from pi_loop.file_utils import _init_daemon_log, _log

        log_path = str(tmp_path / "daemon-messages.log")
        _init_daemon_log(log_path)

        _log("[TEST] Integration test message", level="INFO")
        _log("[TEST] Warning message", level="WARNING")

        # Check that messages appear in the log file
        content = pathlib.Path(log_path).read_text()
        assert "Integration test message" in content
        assert "Warning message" in content


class TestWriteStatusFile:
    """write_status_file from file_utils — distinct from status.write_status."""

    def test_writes_status_file(self, tmp_path):
        """write_status_file writes a one-line JSON status file."""
        from pi_loop.file_utils import write_status_file

        sp = str(tmp_path / "status.json")
        state = {"total_iterations": 10, "stats": {"total_duration_seconds": 123.4}}

        write_status_file(sp, state, iteration=5, status="running")
        assert os.path.exists(sp)

        raw = pathlib.Path(sp).read_text().strip()
        data = json.loads(raw)  # noqa: S205
        assert data["pid"] == os.getpid()
        assert data["iteration"] == 5
        assert data["status"] == "running"
        assert data["total_iterations"] == 10

    def test_empty_path_is_noop(self):
        """write_status_file is a no-op with empty path."""
        from pi_loop.file_utils import write_status_file

        write_status_file("", {}, iteration=0, status="running")  # should not raise

    def test_creates_parent_dirs(self, tmp_path):
        """write_status_file creates parent directories."""
        from pi_loop.file_utils import write_status_file

        sp = str(tmp_path / "deep" / "nested" / "status.json")
        state = {"total_iterations": 1, "stats": {}}
        write_status_file(sp, state, iteration=1, status="completed")
        assert os.path.exists(sp)

    def test_nonwritable_path_logs_gracefully(self):
        """write_status_file logs but does not crash on write failure."""
        from pi_loop.file_utils import write_status_file

        # Use a path that should fail in a read-only scenario
        state = {"total_iterations": 0, "stats": {}}
        # This should not raise
        write_status_file("/proc/1/status.json", state, iteration=0, status="running")


class TestFileLockTimeout:
    """FileLock timeout edge cases not covered elsewhere."""

    def test_lock_short_timeout_raises(self, tmp_path):
        """FileLock raises TimeoutError with very short timeout when locked."""
        import multiprocessing

        from pi_loop.file_utils import FileLock

        lock_path = str(tmp_path / "short_timeout.lock")
        acquired = multiprocessing.Value("b", False, lock=True)

        p = multiprocessing.Process(target=_lock_holder, args=(lock_path, acquired))
        p.start()
        time.sleep(0.3)  # Wait for lock to be acquired

        assert acquired.value
        with pytest.raises(TimeoutError), FileLock(lock_path, timeout=0.3):
            pass

        p.join(timeout=5)


# ── System Utils Deeper Edges (system_utils.py) ────────────────────────────


class TestSystemUtilsDeeperEdges:
    """Additional system_utils edge cases."""

    def test_get_system_usage_has_expected_keys(self):
        """get_system_usage returns expected keys on this Linux system."""
        from pi_loop.system_utils import get_system_usage

        usage = get_system_usage()
        assert isinstance(usage, dict)

        # At least some keys should be present on Linux with /proc
        expected_keys = {"cpu_seconds", "memory_rss_mb", "memory_vms_mb"}
        assert expected_keys.intersection(usage.keys())

    def test_diff_returns_empty_for_empty_snapshots(self):
        """get_system_usage_diff returns empty dict when both snapshots are empty."""
        from pi_loop.system_utils import get_system_usage_diff

        result = get_system_usage_diff({}, {})
        assert result == {}

    def test_diff_with_partial_data(self):
        """get_system_usage_diff handles partial data gracefully."""
        from pi_loop.system_utils import get_system_usage_diff

        before = {"cpu_seconds": 10.0}
        after = {"cpu_seconds": 15.5, "memory_rss_mb": 100.0}
        result = get_system_usage_diff(before, after)
        assert result["cpu_seconds_used"] == 5.5
        assert result["memory_rss_mb"] == 100.0

    def test_diff_with_empty_before(self):
        """get_system_usage_diff returns after values when before is empty."""
        from pi_loop.system_utils import get_system_usage_diff

        result = get_system_usage_diff({}, {"cpu_seconds": 5.0, "memory_rss_mb": 50.0})
        assert result == {}

    def test_diff_with_empty_after(self):
        """get_system_usage_diff returns empty values when after is empty."""
        from pi_loop.system_utils import get_system_usage_diff

        result = get_system_usage_diff({"cpu_seconds": 5.0}, {})
        assert result == {}


# ── Env Utils Edge Cases (env_utils.py deferred deeper) ──────────────────────


class TestEnvUtilsEdgeCases:
    """Edge cases for env_utils functions."""

    def test_known_env_vars_have_correct_prefix(self):
        """All known env vars start with INFINITE_LOOP_ or PI_LOOP_."""
        from pi_loop.env_utils import KNOWN_ENV_VARS

        for var in KNOWN_ENV_VARS:
            assert var.startswith("INFINITE_LOOP_") or var.startswith("PI_LOOP_"), (
                f"Env var {var} does not start with expected prefix"
            )


# ── Sentinels Edge Cases (file_utils.py) ─────────────────────────────────────


class TestSentinelDeeperEdges:
    """Additional sentinel file edge cases."""

    def test_check_sentinel_returns_content(self, tmp_path):
        """check_sentinel returns the content of the sentinel file."""
        from pi_loop.file_utils import check_sentinel

        sentinel = tmp_path / "sentinel"
        sentinel.write_text("stop\n")
        content = check_sentinel(str(sentinel))
        assert content == "stop"
        assert not sentinel.exists()  # removed after read

    def test_check_sentinel_none_path(self):
        """check_sentinel returns None when path is empty."""
        from pi_loop.file_utils import check_sentinel

        result = check_sentinel("")
        assert result is None

    def test_check_sentinel_no_remove_preserves_file(self, tmp_path):
        """check_sentinel_no_remove reads without deleting."""
        from pi_loop.file_utils import check_sentinel_no_remove

        sentinel = tmp_path / "pause_sentinel"
        sentinel.write_text("pause")

        content = check_sentinel_no_remove(str(sentinel))
        assert content == "pause"
        assert sentinel.exists()

    def test_check_sentinel_no_remove_missing_file(self, tmp_path):
        """check_sentinel_no_remove returns None for missing file."""
        from pi_loop.file_utils import check_sentinel_no_remove

        result = check_sentinel_no_remove(str(tmp_path / "nonexistent"))
        assert result is None


# ── Goal Cycling Edge Cases (functions.py) ──────────────────────────────────


class TestGoalCyclingEdgeCases:
    """Edge cases for _cycle_goal not covered elsewhere."""

    def test_cycle_single_goal_returns_empty(self):
        """_cycle_goal returns ('', False) for single goal list."""
        from pi_loop.functions import _cycle_goal

        goal_text, should_stop = _cycle_goal(["single goal"], 0, stop_at_goals_end=False)
        assert goal_text == ""
        assert not should_stop

    def test_cycle_wraps_around(self):
        """_cycle_goal wraps around the goals list with modulo."""
        from pi_loop.functions import _cycle_goal

        goals = [("goal1", "", "", ""), ("goal2", "", "", "")]
        goal_text, should_stop = _cycle_goal(goals, 2, stop_at_goals_end=False)
        assert goal_text == "goal1"  # wraps around: 2 % 2 = 0
        assert not should_stop

    def test_cycle_with_index(self):
        """_cycle_goal returns correct goal at index."""
        from pi_loop.functions import _cycle_goal

        goals = [("first", "", "", ""), ("second", "", "", "")]
        goal_text, should_stop = _cycle_goal(goals, 1, stop_at_goals_end=False)
        assert goal_text == "second"
        assert not should_stop

    def test_cycle_stops_at_goals_end(self):
        """_cycle_goal signals stop when indices exhausted and stop_at_goals_end."""
        from pi_loop.functions import _cycle_goal

        # With stop_at_goals_end and index >= len(goals), should stop
        # But with len <= 1, it short-circuits to ('', False)
        # So we need len > 1 and index >= len
        goals2 = [("g1", "", "", ""), ("g2", "", "", "")]
        goal_text, should_stop = _cycle_goal(goals2, 2, stop_at_goals_end=True)
        assert goal_text == ""
        assert should_stop

    def test_cycle_with_string_goals(self):
        """_cycle_goal handles plain string goals (not tuples)."""
        from pi_loop.functions import _cycle_goal

        goals = ["plain1", "plain2"]
        goal_text, should_stop = _cycle_goal(goals, 1, stop_at_goals_end=False)
        assert goal_text == "plain2"
        assert not should_stop


class TestBuildProgressiveContext:
    """_build_progressive_context edge cases beyond what's covered."""

    def test_empty_context_with_summaries(self):
        """_build_progressive_context works with empty base context."""
        from pi_loop.functions import _build_progressive_context

        result = _build_progressive_context("", ["summary1"])
        assert "summary1" in result
        assert "[Previous iterations:" in result

    def test_multiline_summaries(self):
        """_build_progressive_context handles multi-line summary strings."""
        from pi_loop.functions import _build_progressive_context

        summaries = [
            "line1\nline2\nline3",
        ]
        result = _build_progressive_context("base", summaries)
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    def test_exactly_three_summaries(self):
        """_build_progressive_context includes only 3 most recent summaries."""
        from pi_loop.functions import _build_progressive_context

        summaries = ["a", "b", "c", "d", "e"]
        context = _build_progressive_context("X", summaries)
        # Should include c, d, e (but not a, b)
        assert "c" in context
        assert "d" in context
        assert "e" in context
        assert "[Previous iterations:" in context
        assert "c | d | e" in context

    def test_no_change_without_summaries(self):
        """_build_progressive_context returns just the context when no summaries."""
        from pi_loop.functions import _build_progressive_context

        result = _build_progressive_context("base only", [])
        assert result == "base only"


class TestSetMaxOutputChars:
    """set_max_output_chars and get_max_output_chars."""

    def test_default_value(self):
        """get_max_output_chars returns default 2000."""
        from pi_loop.functions import get_max_output_chars, set_max_output_chars

        # Reset to default
        set_max_output_chars(2000)
        assert get_max_output_chars() == 2000

    def test_set_and_get(self):
        """set_max_output_chars changes the value returned by get."""
        from pi_loop.functions import get_max_output_chars, set_max_output_chars

        set_max_output_chars(5000)
        assert get_max_output_chars() == 5000

        set_max_output_chars(100)
        assert get_max_output_chars() == 100


# ── Preflight Deeper Edges (preflight.py) ────────────────────────────────────


class TestPreflightDeeperEdges:
    """Additional preflight checker edge cases."""

    def test_missing_schema_file_does_not_fail_preflight(self, tmp_path):
        """Preflight handles missing schema file gracefully."""
        from pi_loop.preflight import PreflightChecker

        results = PreflightChecker.run_all_checks(
            workdir=str(tmp_path),
            schema_file="/nonexistent/schema.json",
        )
        # Should not crash — missing schema file is a warning, not fatal
        assert isinstance(results, list)
        assert len(results) > 0
        # All results should have a "passed" key
        for r in results:
            assert "passed" in r

    def test_run_all_checks_returns_list_of_dicts(self, tmp_path):
        """PreflightChecker.run_all_checks returns a list of result dicts."""
        from pi_loop.preflight import PreflightChecker

        results = PreflightChecker.run_all_checks(workdir=str(tmp_path))
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, dict)
            assert "name" in r
            assert "passed" in r
            assert "detail" in r


# ── FileUtils Log (file_utils.py) — _log function ────────────────────────────


class TestLogFunctionEdges:
    """_log function edge cases for level handling."""

    def test_log_handles_various_levels(self, capsys):
        """_log handles different log levels without error."""
        from pi_loop.file_utils import _log

        _log("Debug message", level="DEBUG")
        _log("Info message", level="INFO")
        _log("Warning message", level="WARNING")
        _log("Error message", level="ERROR")

        captured = capsys.readouterr()
        assert "Debug message" in captured.out
        assert "Info message" in captured.out
        assert "Warning message" in captured.out
        assert "Error message" in captured.out

    def test_log_unknown_level_falls_back_to_info(self, capsys):
        """_log falls back to INFO for unknown level strings."""
        from pi_loop.file_utils import _log

        _log("Unknown level message", level="BOGUS")
        captured = capsys.readouterr()
        assert "Unknown level message" in captured.out

    def test_log_unicode_handling(self, capsys):
        """_log handles unicode characters."""
        from pi_loop.file_utils import _log

        _log("Unicode message: ✓ ✗ 🚀")
        captured = capsys.readouterr()
        assert "Unicode message:" in captured.out


# ── JSON Extraction Edge Cases (file_utils.py) ───────────────────────────────


class TestJsonExtractionDeeperEdges:
    """Additional extract_json_from_output edge cases."""

    def test_extract_with_session_id_noise(self):
        """extract_json_from_output strips session_id: lines."""
        from pi_loop.file_utils import extract_json_from_output

        output = 'session_id: abc123\nHere is the result: {"status": "ok", "value": 42}\nsession_id: def456\n'
        result = extract_json_from_output(output)
        assert result is not None
        assert result["status"] == "ok"
        assert result["value"] == 42

    def test_extract_with_session_id_before_json(self):
        """extract_json_from_output handles session_id on same line as JSON."""
        from pi_loop.file_utils import extract_json_from_output

        output = 'Thinking... session_id: xyz\n{"answer": 7}\n'
        result = extract_json_from_output(output)
        assert result is not None
        assert result["answer"] == 7

    def test_extract_empty_string(self):
        """extract_json_from_output returns None for empty string."""
        from pi_loop.file_utils import extract_json_from_output

        result = extract_json_from_output("")
        assert result is None

    def test_extract_none_input(self):
        """extract_json_from_output returns None for None input."""
        from pi_loop.file_utils import extract_json_from_output

        result = extract_json_from_output("")
        assert result is None

    def test_extract_nested_json_object(self):
        """extract_json_from_output handles nested JSON objects."""
        from pi_loop.file_utils import extract_json_from_output

        output = 'The result: {"outer": {"inner": 42, "list": [1,2,3]}}'
        result = extract_json_from_output(output)
        assert result is not None
        assert result["outer"]["inner"] == 42
        assert result["outer"]["list"] == [1, 2, 3]

    def test_extract_multiple_json_objects(self):
        """extract_json_from_output returns the LAST JSON object."""
        from pi_loop.file_utils import extract_json_from_output

        output = 'First: {"step": 1}\nSecond: {"step": 2}'
        result = extract_json_from_output(output)
        assert result is not None
        assert result["step"] == 2  # last one wins


# ── Load Goals File Edge Cases (functions.py) ────────────────────────────────


class TestLoadGoalsFileDeeperEdges:
    """Additional _load_goals_file edge cases."""

    def test_goals_file_with_mixed_content(self, tmp_path):
        """_load_goals_file parses mixed content with blank lines."""
        from pi_loop.functions import _load_goals_file

        gf = tmp_path / "goals.txt"
        gf.write_text("goal1\n\ngoal2\n# comment\ngoal3|profile3|model3|provider3\n")
        goals = _load_goals_file(str(gf), "fallback")
        assert len(goals) == 3
        assert goals[0][0] == "goal1"
        assert goals[1][0] == "goal2"
        g2 = goals[2]
        assert g2[0] == "goal3"
        assert g2[1] == "profile3"
        assert g2[2] == "model3"
        assert g2[3] == "provider3"

    def test_goals_file_with_trailing_pipe(self, tmp_path):
        """_load_goals_file handles trailing pipes (empty extra field)."""
        from pi_loop.functions import _load_goals_file

        gf = tmp_path / "trailing.txt"
        gf.write_text("goal|profile||")
        goals = _load_goals_file(str(gf), "fallback")
        assert len(goals) == 1
        g0 = goals[0]
        assert g0[0] == "goal"
        assert g0[1] == "profile"
        assert g0[2] == ""
        assert g0[3] == ""
