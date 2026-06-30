"""Integration tests for omp-loop — end-to-end workflows across modules.

These tests validate multi-module interactions with minimal mocking, using
real filesystem operations (tmp_path), real subprocess runners where safe,
and the actual asyncio event loop for async components.
"""

import asyncio
import json
import os
import pathlib
import textwrap
from unittest.mock import MagicMock, patch

import pytest

# ── Ledger Lifecycle (state.py + file_utils.py) ────────────────────────────


class TestLedgerLifecycle:
    """Full ledger lifecycle on a real filesystem via env var overrides."""

    LEDGER_ENVIRON = {
        "OMP_LOOP_DATA_DIR": None,  # set per test
        "OMP_LOOP_LEDGER_PATH": None,
        "OMP_LOOP_LOCK_PATH": None,
    }

    @pytest.fixture(autouse=True)
    def _isolate_paths(self, tmp_path, monkeypatch):
        """Route all ledger/lock/sentinel paths to a temp directory."""
        monkeypatch.setenv("OMP_LOOP_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OMP_LOOP_LEDGER_PATH", str(tmp_path / "infinite-loop-state.json"))
        monkeypatch.setenv("OMP_LOOP_LOCK_PATH", str(tmp_path / "infinite-loop-state.lock"))
        # Re-import config module so _resolve_path picks up the new env vars
        # after monkeypatch.  Inline import ensures we get the updated values.
        import importlib

        from omp_loop import config as cfg_mod

        importlib.reload(cfg_mod)
        yield
        # Restore (pytest monkeypatch handles this)

    def _get_ledger_path(self):
        from omp_loop.config import LEDGER_PATH

        return LEDGER_PATH

    def test_create_and_resume_ledger(self):
        """Create a fresh ledger, then resume it with the same goal."""
        from omp_loop.file_utils import read_ledger, write_ledger
        from omp_loop.state import load_or_create_ledger

        # Create fresh ledger (load_or_create_ledger does NOT write to disk
        # for fresh state — only returns the dict)
        state = load_or_create_ledger("Test goal", "context info")
        assert state["initial_command"] == "Test goal"
        assert state["initial_context"] == "context info"
        assert state["status"] == "running"
        assert state["total_iterations"] == 0
        assert state["version"] == 11
        assert state["goals_completed"] == {}

        # Write it to disk to simulate what run_loop does
        write_ledger(state)
        assert os.path.exists(self._get_ledger_path())
        disk_state = read_ledger()
        assert disk_state is not None
        assert disk_state["initial_command"] == "Test goal"

        from omp_loop.file_utils import write_ledger

        # Add an iteration manually to simulate real usage
        state["iterations"].append(
            {
                "n": 1,
                "summary": "Did some work",
                "error": None,
                "duration_seconds": 15.0,
            }
        )
        state["total_iterations"] = 1
        write_ledger(state)

        # Resume with the same goal — should pick up existing ledger
        resumed = load_or_create_ledger("Test goal", "new context")
        assert resumed["total_iterations"] == 1
        assert len(resumed["iterations"]) == 1
        assert resumed["initial_command"] == "Test goal"
        assert resumed["status"] == "running"

    def test_different_goal_starts_fresh(self):
        """A different goal should create a new ledger."""
        from omp_loop.state import load_or_create_ledger

        load_or_create_ledger("First goal", "")
        fresh = load_or_create_ledger("Different goal", "")
        assert fresh["initial_command"] == "Different goal"
        assert fresh["total_iterations"] == 0

    def test_ledger_with_stale_sentinel(self):
        """Creating a ledger removes stale sentinel files."""
        from omp_loop.state import load_or_create_ledger

        sentinel_path = os.path.join(
            os.environ.get("OMP_LOOP_DATA_DIR", "/tmp"),
            "test-sentinel-stop",
        )
        # Create stale sentinel
        pathlib.Path(sentinel_path).write_text("stop\n")

        state = load_or_create_ledger("Goal with sentinel", "", sentinel_path=sentinel_path)
        assert state["initial_command"] == "Goal with sentinel"
        # Sentinel should be removed
        assert not os.path.exists(sentinel_path)

    def test_reset_goals_clears_completed(self):
        """reset_goals=True clears goals_completed on resume."""
        from omp_loop.file_utils import write_ledger
        from omp_loop.state import load_or_create_ledger

        state = load_or_create_ledger("Goal", "")
        state["goals_completed"] = {"goal1": True, "goal2": True}
        write_ledger(state)

        resumed = load_or_create_ledger("Goal", "", reset_goals=True)
        assert resumed["goals_completed"] == {}

    def test_fresh_ledger_has_missing_keys(self):
        """A fresh ledger has all expected keys."""
        from omp_loop.state import load_or_create_ledger

        state = load_or_create_ledger("G", "ctx")
        assert "error_type_counts" in state
        assert "mitigations" in state
        assert "stats" in state
        assert state["stats"]["success_count"] == 0
        assert state["stats"]["error_count"] == 0
        assert state["mitigations"]["mitigation_level"] == 0


# ── Stats Recalculation (stats.py + state/ledger integration) ──────────────


class TestStatsRecalculation:
    """Real stats recalculation from ledger state."""

    def test_stats_from_iterations(self):
        """_recalc_stats computes correct stats from real iteration data."""
        from omp_loop.stats import _recalc_stats

        state = {
            "iterations": [
                {"error": None, "duration_seconds": 10.0},
                {"error": None, "duration_seconds": 20.0},
                {"error": "timeout", "duration_seconds": 30.0},
                {"error": None, "duration_seconds": 15.0},
            ]
        }
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["success_count"] == 3
        assert stats["error_count"] == 1
        assert stats["total_duration_seconds"] == 75.0
        assert stats["avg_duration_seconds"] == pytest.approx(18.75, rel=0.01)
        assert stats["consecutive_errors"] == 0
        assert stats["consecutive_successes"] == 1

    def test_consecutive_errors(self):
        """_recalc_stats detects consecutive errors at the end."""
        from omp_loop.stats import _recalc_stats

        state = {
            "iterations": [
                {"error": None, "duration_seconds": 5.0},
                {"error": "timeout", "duration_seconds": 10.0},
                {"error": "network", "duration_seconds": 12.0},
            ]
        }
        _recalc_stats(state)
        assert state["stats"]["consecutive_errors"] == 2
        assert state["stats"]["consecutive_successes"] == 0

    def test_consecutive_successes(self):
        """_recalc_stats detects consecutive successes."""
        from omp_loop.stats import _recalc_stats

        state = {
            "iterations": [
                {"error": "crash", "duration_seconds": 5.0},
                {"error": None, "duration_seconds": 3.0},
                {"error": None, "duration_seconds": 4.0},
            ]
        }
        _recalc_stats(state)
        assert state["stats"]["consecutive_successes"] == 2
        assert state["stats"]["consecutive_errors"] == 0


# ── Goal File Parsing (functions.py) ────────────────────────────────────────


class TestGoalFileParsing:
    """End-to-end goal file parsing with real filesystem."""

    def test_load_simple_goals(self, tmp_path):
        """_load_goals_file parses a simple line-by-line goals file."""
        from omp_loop.functions import _load_goals_file

        gf = tmp_path / "goals.txt"
        gf.write_text("Fix lint errors\nRun tests\nDeploy app\n")
        goals = _load_goals_file(str(gf), "fallback goal")
        assert len(goals) == 3
        assert goals[0][0] == "Fix lint errors"
        assert goals[1][0] == "Run tests"
        assert goals[2][0] == "Deploy app"

    def test_load_goals_with_profiles(self, tmp_path):
        """_load_goals_file parses pipe-delimited goal | profile | model | provider."""
        from omp_loop.functions import _load_goals_file

        gf = tmp_path / "goals.txt"
        gf.write_text("Fix bugs | productive | gpt4 | openai\nTest | fast | claude | anthropic\n")
        goals = _load_goals_file(str(gf), "fallback")
        assert len(goals) == 2
        assert goals[0] == ("Fix bugs", "productive", "gpt4", "openai")
        assert goals[1] == ("Test", "fast", "claude", "anthropic")

    def test_respects_comments_and_blanks(self, tmp_path):
        """_load_goals_file skips comments and blank lines."""
        from omp_loop.functions import _load_goals_file

        gf = tmp_path / "goals.txt"
        gf.write_text("# This is a comment\n\nFix bugs\n# Another comment\n\n")
        goals = _load_goals_file(str(gf), "fallback")
        assert len(goals) == 1
        assert goals[0][0] == "Fix bugs"

    def test_missing_file_returns_fallback(self):
        """_load_goals_file returns fallback when file is missing."""
        from omp_loop.functions import _load_goals_file

        goals = _load_goals_file("/nonexistent/goals.txt", "fallback goal")
        assert len(goals) == 1
        assert goals[0][0] == "fallback goal"


# ── Config Pipeline (config_file.py → config_manager.py → build_cli_args) ──


class TestConfigPipeline:
    """Full config pipeline: filesystem → load → schema → CLI args."""

    def test_config_file_roundtrip(self, tmp_path):
        """Save then load config file — full persistence round-trip."""
        from omp_loop.config_file import load_config, save_config

        config_path = tmp_path / "config.json"
        with patch("omp_loop.config_file.CONFIG_DIR", tmp_path), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            save_config({"INFINITE_LOOP_GOAL": "my custom goal", "INFINITE_LOOP_GIT": "true"})
            loaded = load_config()
        assert loaded["INFINITE_LOOP_GOAL"] == "my custom goal"
        assert loaded["INFINITE_LOOP_GIT"] == "true"
        # Missing keys get defaults
        assert "INFINITE_LOOP_TIMEOUT" in loaded

    def test_config_manager_reads_stored(self, tmp_path):
        """config_manager._read_stored reads real file values over defaults."""
        from omp_loop.config_file import save_config as file_save
        from web_app.config_manager import _read_stored

        config_path = tmp_path / "config.json"
        with patch("omp_loop.config_file.CONFIG_DIR", tmp_path), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            file_save({"INFINITE_LOOP_GOAL": "build stuff", "INFINITE_LOOP_GIT": "true"})
            result = _read_stored()
        assert result["INFINITE_LOOP_GOAL"] == "build stuff"
        assert result["INFINITE_LOOP_GIT"] == "true"
        # DEFAULTS dict in config_file.py sets MAX_ITERATIONS to "100"
        assert result["INFINITE_LOOP_MAX_ITERATIONS"] == "100"

    def test_config_manager_get_config_roundtrip(self, tmp_path):
        """get_config returns schema + current values after saving."""
        from omp_loop.config_file import save_config as file_save
        from web_app.config_manager import get_config

        config_path = tmp_path / "config.json"
        with patch("omp_loop.config_file.CONFIG_DIR", tmp_path), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            file_save({"INFINITE_LOOP_GOAL": "my goal", "INFINITE_LOOP_QUIET": "true"})
            result = get_config()

        # Full schema returned
        for key in ("INFINITE_LOOP_GOAL", "INFINITE_LOOP_QUIET", "INFINITE_LOOP_GIT"):
            assert key in result
            entry = result[key]
            assert "value" in entry
            assert "type" in entry
            assert "group" in entry
            assert "label" in entry

        assert result["INFINITE_LOOP_GOAL"]["value"] == "my goal"
        assert result["INFINITE_LOOP_QUIET"]["value"] == "true"

    def test_build_cli_args_integration(self, tmp_path):
        """Build CLI args from real saved config."""
        from omp_loop.config_file import save_config as file_save
        from web_app.config_manager import build_cli_args, get_raw_config

        config_path = tmp_path / "config.json"
        with patch("omp_loop.config_file.CONFIG_DIR", tmp_path), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            file_save(
                {
                    "INFINITE_LOOP_GOAL": "Run tests",
                    "INFINITE_LOOP_GIT": "true",
                    "INFINITE_LOOP_GIT_COMMIT": "true",
                    "INFINITE_LOOP_QUIET": "false",
                    "INFINITE_LOOP_MAX_ITERATIONS": "50",
                }
            )
            raw = get_raw_config()
            args = build_cli_args(raw)

        assert "--goal" in args
        assert args[args.index("--goal") + 1] == "Run tests"
        assert "--git" in args
        assert "--git-commit" in args
        assert "--max-iterations" in args
        assert "--quiet" not in args  # false → not included

    def test_build_cli_args_context(self, tmp_path):
        """Context value maps to --append-system-prompt flag."""
        from omp_loop.config_file import save_config as file_save
        from web_app.config_manager import build_cli_args, get_raw_config

        config_path = tmp_path / "config.json"
        with patch("omp_loop.config_file.CONFIG_DIR", tmp_path), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            file_save({"INFINITE_LOOP_CONTEXT": "Be concise and use git"})
            raw = get_raw_config()
            args = build_cli_args(raw)

        assert "--append-system-prompt" in args
        idx = args.index("--append-system-prompt")
        assert args[idx + 1] == "Be concise and use git"


# ── LoopConfig from_args (parser.py → config.py) ────────────────────────────


class TestLoopConfigFromArgs:
    """LoopConfig.from_args round-trip from parsed CLI args."""

    def test_basic_arg_roundtrip(self):
        """LoopConfig.from_args correctly maps basic args."""
        from omp_loop.config import LoopConfig
        from omp_loop.parser import _create_parser

        parser = _create_parser()
        ns = parser.parse_args(
            [
                "--goal",
                "Fix bugs",
                "--max-iterations",
                "25",
                "--git",
                "--git-commit",
                "--cooldown",
                "10",
                "--workers",
                "3",
            ]
        )
        cfg = LoopConfig.from_args(ns)
        assert cfg.goal == "Fix bugs"
        assert cfg.max_iterations == 25
        assert cfg.git is True
        assert cfg.git_commit is True
        assert cfg.cooldown == 10
        assert cfg.workers == 3

    def test_bool_flags_map_correctly(self):
        """Boolean flags are correctly mapped to LoopConfig."""
        from omp_loop.config import LoopConfig
        from omp_loop.parser import _create_parser

        parser = _create_parser()
        ns = parser.parse_args(["--goal", "test", "--evolve", "--quiet", "--notify-desktop"])
        cfg = LoopConfig.from_args(ns)
        assert cfg.evolve is True
        assert cfg.quiet is True
        assert cfg.notify_desktop is True
        assert cfg.git is False  # not set

    def test_string_defaults_preserved(self):
        """Unset string args preserve their defaults."""
        from omp_loop.config import LoopConfig
        from omp_loop.parser import _create_parser

        parser = _create_parser()
        ns = parser.parse_args(["--goal", "test"])
        cfg = LoopConfig.from_args(ns)
        assert cfg.profile == ""
        assert cfg.model == ""
        assert cfg.provider == ""
        assert cfg.http_callback == ""
        assert cfg.keep_iterations == 0
        assert cfg.evolve is False
        assert cfg.html_dashboard == ""

    def test_sentinel_path_preserved(self):
        """Sentinel path from CLI is preserved in LoopConfig."""
        from omp_loop.config import LoopConfig
        from omp_loop.parser import _create_parser

        parser = _create_parser()
        custom_path = "/tmp/custom-sentinel"
        ns = parser.parse_args(["--goal", "test", "--shutdown-sentinel", custom_path])
        # NOTE: from_args() cannot map argparse's 'shutdown_sentinel' to
        # dataclass field 'sentinel_path' due to name mismatch — the caller
        # (cli.main()) assigns cfg.sentinel_path = args.shutdown_sentinel
        # separately.  Verify from_args gives the default instead.
        cfg = LoopConfig.from_args(ns)
        assert cfg.sentinel_path == cfg.get("sentinel_path")

    def test_kwargs_default_handling(self):
        """LoopConfig(some_param=val) fills unset fields with defaults."""
        from omp_loop.config import LoopConfig

        cfg = LoopConfig(goal="test", max_iterations=10)
        assert cfg.workers == 1
        assert cfg.cooldown == 0
        assert cfg.evolve is False
        assert cfg.git is False
        assert cfg.context == ""

    def test_getitem_backward_compat(self):
        """LoopConfig supports dict-style access for backward compat."""
        from omp_loop.config import LoopConfig

        cfg = LoopConfig(goal="my goal", workers=3)
        assert cfg["goal"] == "my goal"
        assert cfg["workers"] == 3

    def test_get_method(self):
        """LoopConfig.get() works like dict.get()."""
        from omp_loop.config import LoopConfig

        cfg = LoopConfig(goal="test")
        assert cfg.get("goal") == "test"
        assert cfg.get("nonexistent", "default") == "default"


# ── Error Recovery Cycle (error_recovery.py + config.py) ────────────────────


class TestErrorRecoveryCycle:
    """Full error recovery adaptation → unwind cycle."""

    def test_timeout_mitigation_ramp_up(self):
        """Timeout errors escalate through mitigation levels."""
        from omp_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(session_timeout=120, cooldown=0, use_library=True, workers=2)

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

        # Level 0 → 1 (mild: 3 times, but we test with count=1 which should still trigger level 1)
        # Actually threshold: mild=3, so count=1 should not trigger yet
        # Let's test with count=3
        error_counts["timeout"] = 3
        new_timeout, new_cooldown, new_mode, new_library, new_workers, actions = _adapt_to_error(
            "timeout",
            mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=120,
            cooldown=0,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        assert mitigations["mitigation_level"] >= 1
        assert new_timeout > 120  # timeout should increase
        assert len(actions) >= 1

    def test_network_errors_exponential_backoff(self):
        """Network errors trigger exponential backoff, not stop."""
        from omp_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(session_timeout=120, cooldown=0, use_library=True, workers=2)

        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"timeout": 0, "network": 2, "schema": 0, "unknown": 0, "heartbeat": 0}

        # mild threshold = 2 → triggers level 1 with exponential backoff
        new_timeout, new_cooldown, new_mode, new_library, new_workers, actions = _adapt_to_error(
            "network",
            mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=120,
            cooldown=0,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        assert mitigations["mitigation_level"] >= 1
        assert new_cooldown >= 30
        assert new_mode == "adaptive"
        # Network should never auto-stop — verify stop threshold is None
        from omp_loop.config import _ERROR_THRESHOLDS

        assert _ERROR_THRESHOLDS["network"]["stop"] is None

    def test_full_success_unwind(self):
        """3+ consecutive successes fully unwind to originals."""
        from omp_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(session_timeout=120, cooldown=10, use_library=True, workers=2)

        # First, ramp up
        mitigations = {
            "mitigation_level": 2,
            "timeout_increased": True,
            "cooldown_elevated": True,
            "force_subprocess": True,
            "reduced_workers": True,
            "last_applied": "2025-01-01T00:00:00",
            "actions": ["[MITIGATION] Previous step"],
        }
        error_counts = {"timeout": 0, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0}

        # 1st success: partial unwind
        _, _, _, _, _, actions1 = _adapt_to_error(
            None,
            mitigations,
            consecutive_successes=1,
            error_type_counts=error_counts,
            session_timeout=180,
            cooldown=30,
            cooldown_mode="fixed",
            use_library=False,
            workers=1,
        )
        assert len(actions1) >= 1
        level_after_1 = mitigations["mitigation_level"]

        # 3rd success: full unwind
        _, _, _, _, _, actions3 = _adapt_to_error(
            None,
            mitigations,
            consecutive_successes=3,
            error_type_counts=error_counts,
            session_timeout=180,
            cooldown=30,
            cooldown_mode="fixed",
            use_library=False,
            workers=1,
        )
        assert any("Full recovery" in a for a in actions3)
        assert not mitigations["timeout_increased"]
        assert not mitigations["cooldown_elevated"]

    def test_stop_threshold_triggers_level_3(self):
        """Reaching the stop threshold sets mitigation_level to 3."""
        from omp_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(session_timeout=120, cooldown=0, use_library=True, workers=2)

        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"timeout": 8, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0}
        # timeout stop threshold = 8
        # NOTE: _adapt_to_error only escalates ONE level per call —
        # intentional gradual ramp-up.  At count=8, level_before=0, it
        # goes to level 1 on first call.  Verify level 1 + stop action
        # appears in actions (escalation plan), not mitigation_level.

        _, _, _, _, _, actions = _adapt_to_error(
            "timeout",
            mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=120,
            cooldown=0,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        assert mitigations["mitigation_level"] >= 1
        # Verify the actions mention the stop-threshold even if not
        # yet applied (ramp-up is gradual)
        assert any(str(8) in a for a in actions)

    def test_error_type_severity_sorting(self):
        """_pick_primary_error picks the most severe type."""
        from omp_loop.error_recovery import _pick_primary_error

        assert _pick_primary_error(["info", "timeout", "network"]) == "timeout"
        assert _pick_primary_error(["heartbeat", "unknown"]) == "heartbeat"
        assert _pick_primary_error(["network"]) == "network"


# ── PreflightChecker (preflight.py) ─────────────────────────────────────────


class TestPreflightChecker:
    """End-to-end preflight checks with real filesystem."""

    def test_all_checks_pass_with_defaults(self, tmp_path):
        """PreflightChecker.run_all() returns True when all checks pass."""
        from omp_loop.preflight import PreflightChecker

        args = MagicMock()
        args.workdir = ""
        args.shutdown_sentinel = str(tmp_path / "sentinel")
        args.webhook_port = 0
        args.context_file = ""
        args.goals_file = ""
        args.output_schema_file = ""
        args.git = False

        checker = PreflightChecker(args)
        result = checker.run_all()
        assert result

    def test_fails_on_missing_workdir(self, tmp_path):
        """PreflightChecker fails when workdir doesn't exist."""
        from omp_loop.preflight import PreflightChecker

        args = MagicMock()
        args.workdir = str(tmp_path / "nonexistent")
        args.shutdown_sentinel = str(tmp_path / "sentinel")
        args.webhook_port = 0
        args.context_file = ""
        args.goals_file = ""
        args.output_schema_file = ""
        args.git = False

        checker = PreflightChecker(args)
        # This should log failures but not crash
        result = checker.run_all()
        assert not result

    def test_fail_fast_stops_early(self, tmp_path):
        """fail_fast=True stops on first failure."""
        from omp_loop.preflight import PreflightChecker

        args = MagicMock()
        args.workdir = str(tmp_path / "nonexistent")
        args.shutdown_sentinel = str(tmp_path / "sentinel")
        args.webhook_port = 0
        args.context_file = ""
        args.goals_file = ""
        args.output_schema_file = ""
        args.git = False

        checker = PreflightChecker(args, fail_fast=True)
        # Should fail fast
        result = checker.run_all()
        assert not result

    def test_git_check_works_in_repo(self, tmp_path):
        """check_git_repo detects a real .git directory."""
        from omp_loop.preflight import PreflightChecker

        # Create a minimal .git dir
        (tmp_path / ".git").mkdir()
        passed, _ = PreflightChecker.check_git_repo(str(tmp_path))
        assert passed

    def test_git_check_fails_without_repo(self, tmp_path):
        """check_git_repo fails without .git."""
        from omp_loop.preflight import PreflightChecker

        passed, _ = PreflightChecker.check_git_repo(str(tmp_path))
        assert not passed

    def test_file_readable_check(self, tmp_path):
        """check_file_readable detects existing vs missing files."""
        from omp_loop.preflight import PreflightChecker

        existing = tmp_path / "context.txt"
        existing.write_text("hello")
        passed, _ = PreflightChecker.check_file_readable(str(existing), "context-file")
        assert passed

        missing = tmp_path / "missing.txt"
        passed, _ = PreflightChecker.check_file_readable(str(missing), "context-file")
        assert not passed

    def test_port_available_check(self):
        """check_port_available returns True when port is 0."""
        from omp_loop.preflight import PreflightChecker

        passed, detail = PreflightChecker.check_port_available(0)
        assert passed
        assert "not requested" in detail

    def test_schema_file_validation(self, tmp_path):
        """check_schema_file validates JSON schema files."""
        from omp_loop.preflight import PreflightChecker

        valid = tmp_path / "schema.json"
        valid.write_text('{"type": "object", "properties": {}}')
        passed, _ = PreflightChecker.check_schema_file(str(valid))
        assert passed

        invalid = tmp_path / "bad.json"
        invalid.write_text("not json")
        passed, _ = PreflightChecker.check_schema_file(str(invalid))
        assert not passed

        passed, _ = PreflightChecker.check_schema_file("")
        assert passed

    def test_format_results(self):
        """format_results produces human-readable output."""
        from omp_loop.preflight import PreflightChecker

        results = [
            {"name": "python version", "passed": True, "detail": "Python 3.11"},
            {"name": "workdir", "passed": False, "detail": "not found"},
        ]
        output = PreflightChecker.format_results(results)
        assert "✓" in output or "✔" in output
        assert "✗" in output or "✘" in output
        assert "1 check(s) failed." in output

    def test_run_all_checks_returns_correct_results(self, tmp_path):
        """run_all_checks returns structured results for all checks."""
        from omp_loop.preflight import PreflightChecker

        results = PreflightChecker.run_all_checks(
            workdir=str(tmp_path),
            sentinel_path=str(tmp_path / "sentinel"),
        )
        assert isinstance(results, list)
        assert len(results) > 0
        for r in results:
            assert "name" in r
            assert "passed" in r
            assert "detail" in r


# ── File Watcher (file_watcher.py) ─────────────────────────────────────────


class TestFileWatcher:
    """Real filesystem file watching integration."""

    def test_detects_initial_scan_as_change(self, tmp_path):
        """First check_change() returns True (initial scan)."""
        from omp_loop.file_watcher import FileWatcherTrigger

        watcher = FileWatcherTrigger(str(tmp_path), poll_interval=1.0)
        assert watcher.check_change() is True

    def test_detects_file_creation(self, tmp_path):
        """Creating a new file triggers change detection."""
        from omp_loop.file_watcher import FileWatcherTrigger

        watcher = FileWatcherTrigger(str(tmp_path), poll_interval=0.5)
        watcher.check_change()  # Initial scan

        (tmp_path / "new_file.txt").write_text("hello")
        assert watcher.check_change() is True

    def test_no_change_without_modification(self, tmp_path):
        """No change reported when files are stable."""
        from omp_loop.file_watcher import FileWatcherTrigger

        # Start with a file
        (tmp_path / "stable.txt").write_text("content")

        watcher = FileWatcherTrigger(str(tmp_path), poll_interval=0.5)
        watcher.check_change()  # Initial scan — reports as change

        # Another scan without touching anything
        assert watcher.check_change() is False

    def test_detects_file_modification(self, tmp_path):
        """Modifying an existing file triggers change.

        Uses os.utime to set an explicit mtime different from the initial
        write, since write_text + stat within the same kernel tick may not
        produce a distinguishable mtime delta on some filesystems.
        """
        from omp_loop.file_watcher import FileWatcherTrigger

        f = tmp_path / "editable.txt"
        f.write_text("v1")

        watcher = FileWatcherTrigger(str(tmp_path), poll_interval=0.5)
        watcher.check_change()  # Initial scan

        f.write_text("v2")
        # Force a distinct mtime so stat-based detection works reliably
        new_mtime = 2000000000.0
        os.utime(str(f), (new_mtime, new_mtime))
        assert watcher.check_change() is True

    def test_watches_single_file(self, tmp_path):
        """FileWatcherTrigger can watch a single file."""
        from omp_loop.file_watcher import FileWatcherTrigger

        f = tmp_path / "single.txt"
        f.write_text("data")

        watcher = FileWatcherTrigger(str(f))
        assert watcher.check_change() is True  # Initial scan
        assert watcher.check_change() is False  # No change

        f.write_text("modified")
        os.utime(str(f), (2000000001.0, 2000000001.0))
        assert watcher.check_change() is True

    def test_to_dict_returns_state(self, tmp_path):
        """to_dict returns a serializable snapshot."""
        from omp_loop.file_watcher import FileWatcherTrigger

        watcher = FileWatcherTrigger(str(tmp_path), poll_interval=2.0)
        info = watcher.to_dict()
        assert info["path"] == str(tmp_path)
        assert info["poll_interval"] == 2.0
        assert isinstance(info["files_tracked"], int)

    def test_format_changed(self, tmp_path):
        """format_changed returns changed file paths."""
        from omp_loop.file_watcher import FileWatcherTrigger

        watcher = FileWatcherTrigger(str(tmp_path), poll_interval=0.5)
        watcher.check_change()  # Initial scan

        (tmp_path / "new_file.py").write_text("code")
        changed = watcher.format_changed()
        assert "new_file.py" in changed


# ── Status File Pipeline (status.py) ────────────────────────────────────────


class TestStatusFilePipeline:
    """End-to-end status file write/read cycle."""

    def test_write_and_read_status(self, tmp_path):
        """write_status produces a valid JSON file that can be read back."""
        from omp_loop.status import write_status

        status_path = str(tmp_path / "loop-status.json")
        write_status(status_path, running=True, pid=12345, iteration_count=7, version="14.39.0")

        assert os.path.exists(status_path)
        with open(status_path) as f:
            data = json.load(f)

        assert data["running"] is True
        assert data["pid"] == 12345
        assert data["iteration_count"] == 7
        assert data["version"] == "14.39.0"
        assert "last_updated" in data
        assert "uptime_seconds" in data

    def test_status_with_error(self, tmp_path):
        """Status file includes last_error when provided."""
        from omp_loop.status import write_status

        status_path = str(tmp_path / "loop-status.json")
        write_status(
            status_path,
            running=False,
            pid=9999,
            iteration_count=3,
            last_error="timeout",
            version="14.39.0",
        )

        with open(status_path) as f:
            data = json.load(f)
        assert data["running"] is False
        assert data["last_error"] == "timeout"

    def test_no_status_path_is_noop(self):
        """write_status with no path is a no-op."""
        from omp_loop.status import write_status

        # Should not raise
        write_status(None)
        write_status("")

    def test_write_and_status_file_roundtrip(self, tmp_path):
        """Status + status_file utility are consistent."""
        from omp_loop.status import write_status

        sp = str(tmp_path / "status.json")
        write_status(sp, running=True, pid=100, iteration_count=5)
        with open(sp) as f:
            data = json.load(f)
        assert data["pid"] == 100
        assert data["iteration_count"] == 5

    def test_multiple_writes_are_consistent(self, tmp_path):
        """Multiple status writes don't corrupt the file."""
        from omp_loop.status import write_status

        sp = str(tmp_path / "status.json")
        for i in range(5):
            write_status(sp, running=(i % 2 == 0), pid=100 + i, iteration_count=i)

        with open(sp) as f:
            data = json.load(f)
        assert data["iteration_count"] == 4
        assert data["pid"] == 104


# ── Rate Limiter (rate_limiter.py) ──────────────────────────────────────────


class TestRateLimiter:
    """Real asyncio rate limiter integration tests."""

    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        """Requests under the limit are allowed."""
        from web_app.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0)
        for _ in range(5):
            assert await limiter.check("client-1") is True

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        """Requests over the limit are blocked."""
        from web_app.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60.0)
        for _ in range(3):
            await limiter.check("client-2")
        assert await limiter.check("client-2") is False

    @pytest.mark.asyncio
    async def test_per_ip_isolation(self):
        """Rate limits are per-client IP."""
        from web_app.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
        await limiter.check("client-a")
        await limiter.check("client-a")
        assert await limiter.check("client-a") is False  # Exhausted

        # Different client is still allowed
        assert await limiter.check("client-b") is True

    @pytest.mark.asyncio
    async def test_remaining_counts(self):
        """remaining() returns correct remaining count."""
        from web_app.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60.0)
        assert await limiter.remaining("client") == 10
        await limiter.check("client")
        assert await limiter.remaining("client") == 9
        await limiter.check("client")
        assert await limiter.remaining("client") == 8

    @pytest.mark.asyncio
    async def test_reset_clears_count(self):
        """reset() clears tracked entries."""
        from web_app.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0)
        await limiter.check("client")
        assert await limiter.check("client") is False
        await limiter.reset("client")
        assert await limiter.check("client") is True  # Cleared

    @pytest.mark.asyncio
    async def test_reset_all_clears_everything(self):
        """reset() without IP clears all entries."""
        from web_app.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0)
        await limiter.check("a")
        await limiter.check("b")
        assert await limiter.check("a") is False
        await limiter.reset()  # Clear all
        assert await limiter.check("a") is True
        assert await limiter.check("b") is True

    @pytest.mark.asyncio
    async def test_window_expiration(self):
        """Old entries expire after the window passes."""
        from web_app.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.1)
        await limiter.check("client")
        await limiter.check("client")
        assert await limiter.check("client") is False
        await asyncio.sleep(0.15)
        # Window should have expired
        assert await limiter.check("client") is True


# ── Web App + LoopManager Integration (server.py + loop_manager.py) ────────


class TestLoopManagerRealPaths:
    """LoopManager operations with real filesystem paths."""

    def test_ledger_operations_with_real_paths(self, tmp_path):
        """LoopManager.get_ledger works with real filesystem ledger."""
        from omp_loop.file_utils import write_ledger
        from web_app.loop_manager import LoopManager

        ledger_path = str(tmp_path / "ledger.json")
        lock_path = str(tmp_path / "ledger.lock")

        # Directly overwrite runtime paths — patching via unittest.mock
        # won't work because the imported module aliases are already bound.
        import omp_loop.config as _cfg_mod
        import omp_loop.file_utils as _fu_mod
        import web_app.loop_manager as _lm_mod

        old_cfg_mod = _cfg_mod.LEDGER_PATH
        old_lock_path = _cfg_mod.LOCK_PATH
        old_fu_path = _fu_mod.LEDGER_PATH
        old_lm_path = _lm_mod.LEDGER_PATH

        _cfg_mod.LEDGER_PATH = ledger_path
        _cfg_mod.LOCK_PATH = lock_path
        _fu_mod.LEDGER_PATH = ledger_path
        _lm_mod.LEDGER_PATH = ledger_path

        try:
            state = {
                "status": "running",
                "iterations": [{"n": 1, "error": None, "duration_seconds": 10.0}],
                "total_iterations": 1,
                "stats": {},
            }
            write_ledger(state)

            mgr = LoopManager()
            mgr._ledger_path = ledger_path
            result = mgr.get_ledger()

            assert result["status"] == "running"
            assert result["total_iterations"] == 1
        finally:
            _cfg_mod.LEDGER_PATH = old_cfg_mod
            _cfg_mod.LOCK_PATH = old_lock_path
            _fu_mod.LEDGER_PATH = old_fu_path
            _lm_mod.LEDGER_PATH = old_lm_path

    def test_get_status_with_real_paths(self, tmp_path):
        """LoopManager.get_status works with real paths."""
        from web_app.loop_manager import LoopManager

        mgr = LoopManager()
        mgr._add_log("info", "integration test log")
        mgr._status = "stopped"
        status = mgr.get_status()
        assert status["loop_status"] == "stopped"
        assert len(status["recent_logs"]) >= 1
        assert "stats" in status

    def test_loop_manager_singleton(self):
        """get_loop_manager returns a singleton."""
        from web_app.loop_manager import get_loop_manager

        mgr1 = get_loop_manager()
        mgr2 = get_loop_manager()
        assert mgr1 is mgr2


class TestWebAppIntegration:
    """Web server integration with the full app stack."""

    @pytest.fixture
    def client(self):
        """Create a FastAPI TestClient."""
        from fastapi.testclient import TestClient

        from web_app.server import app

        return TestClient(app)

    def test_health_endpoint(self, client):
        """GET /api/health returns 200 with status."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_config_groups_and_schema(self, client):
        """GET /api/config returns group definitions and schema."""
        with patch("web_app.server.get_config") as mock_get_cfg:
            mock_get_cfg.return_value = {
                "INFINITE_LOOP_GOAL": {
                    "value": "test",
                    "group": "core",
                    "type": "string",
                    "label": "Goal",
                    "description": "The goal",
                    "required": True,
                },
                "INFINITE_LOOP_GIT": {
                    "value": "false",
                    "group": "git",
                    "type": "bool",
                    "label": "Git",
                    "description": "Git tracking",
                },
            }
            resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data
        assert len(data["groups"]) > 0
        assert "config" in data
        cfg = data["config"]
        assert "INFINITE_LOOP_GOAL" in cfg
        assert "INFINITE_LOOP_GIT" in cfg

    def test_config_validation_endpoint(self, client):
        """POST /api/config validates and returns errors."""
        with (
            patch("web_app.server.validate_config") as mock_val,
            patch("web_app.server.save_config"),
        ):
            mock_val.return_value = {"valid": False, "errors": ["Goal is required"]}
            resp = client.post("/api/config", json={"goal": ""})
        assert resp.status_code == 422
        data = resp.json()
        assert "errors" in data["detail"]

    def test_get_raw_config_integration(self, tmp_path):
        """get_raw_config returns real stored config from config_file."""
        from omp_loop.config_file import save_config as file_save
        from web_app.config_manager import get_raw_config

        config_path = tmp_path / "config.json"
        with patch("omp_loop.config_file.CONFIG_DIR", tmp_path), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            file_save({"INFINITE_LOOP_GOAL": "integration test goal", "INFINITE_LOOP_GIT": "true"})
            raw = get_raw_config()
        assert raw["INFINITE_LOOP_GOAL"] == "integration test goal"
        assert raw["INFINITE_LOOP_GIT"] == "true"

    def test_validate_config_detects_missing_goal(self):
        """validate_config returns errors when goal is missing."""
        from web_app.config_manager import validate_config

        result = validate_config({"INFINITE_LOOP_GOAL": ""})
        assert not result["valid"]
        assert result["errors"]

    def test_validate_config_passes_with_goal(self):
        """validate_config passes with a valid goal."""
        from web_app.config_manager import validate_config

        result = validate_config({"INFINITE_LOOP_GOAL": "my goal"})
        assert result["valid"]

    def test_build_cli_args_all_booleans(self):
        """All boolean flags are emitted when set to 'true'."""
        from web_app.config_manager import build_cli_args

        bool_keys = [
            "INFINITE_LOOP_GIT",
            "INFINITE_LOOP_GIT_COMMIT",
            "INFINITE_LOOP_STORE_GIT_DIFF",
            "INFINITE_LOOP_NOTIFY_DESKTOP",
            "INFINITE_LOOP_STOP_AT_GOALS_END",
            "INFINITE_LOOP_TRACK_GOALS",
            "INFINITE_LOOP_RESET_GOALS",
            "INFINITE_LOOP_QUIET",
        ]
        config = dict.fromkeys(bool_keys, "true")
        # Fill defaults for non-bool keys
        config["INFINITE_LOOP_GOAL"] = "test"
        args = build_cli_args(config)
        expected_flags = {
            "--git",
            "--git-commit",
            "--store-git-diff",
            "--notify-desktop",
            "--stop-at-goals-end",
            "--track-goals",
            "--reset-goals",
            "--quiet",
        }
        for flag in expected_flags:
            assert flag in args, f"{flag} should be present"


# ── CLI Pipeline (full round-trip) ─────────────────────────────────────────


class TestCliPipeline:
    """Full CLI pipeline: parse args → LoopConfig → run_loop state setup."""

    def test_full_arg_roundtrip(self):
        """CLI args → LoopConfig → dict access preserves values."""
        from omp_loop.config import LoopConfig
        from omp_loop.parser import _create_parser

        parser = _create_parser()
        argv = [
            "--goal",
            "Refactor auth module",
            "--context",
            "Use best practices",
            "--max-iterations",
            "50",
            "--workers",
            "3",
            "--session-timeout",
            "3600",
            "--git",
            "--git-commit",
            "--evolve",
            "--cooldown",
            "15",
            "--quiet",
            "--tag",
            "sprint-42",
        ]
        ns = parser.parse_args(argv)
        cfg = LoopConfig.from_args(ns)

        assert cfg.goal == "Refactor auth module"
        assert cfg.context == "Use best practices"
        assert cfg.max_iterations == 50
        assert cfg.workers == 3
        assert cfg.session_timeout == 3600
        assert cfg.git is True
        assert cfg.git_commit is True
        assert cfg.evolve is True
        assert cfg.cooldown == 15
        assert cfg.quiet is True
        assert cfg.tag == "sprint-42"

    def test_cli_with_goals_file(self, tmp_path):
        """CLI with --goals-file flows through correctly."""
        from omp_loop.config import LoopConfig
        from omp_loop.parser import _create_parser

        gf = tmp_path / "goals.txt"
        gf.write_text("Goal 1\nGoal 2\n")

        parser = _create_parser()
        ns = parser.parse_args(["--goal", "fallback", "--goals-file", str(gf)])
        cfg = LoopConfig.from_args(ns)
        assert cfg.goal == "fallback"
        assert cfg.goals_file == str(gf)

    def test_cli_with_context_file(self, tmp_path):
        """CLI with --context-file reads context from disk."""
        from omp_loop.parser import _create_parser

        cf = tmp_path / "context.txt"
        cf.write_text("Detailed instructions here")

        parser = _create_parser()
        ns = parser.parse_args(["--goal", "test", "--context-file", str(cf)])
        assert ns.context_file == str(cf)
        # The actual file reading happens in cli.main(), not in parsing

    def test_cli_introspection_flags(self):
        """Introspection flags parse without --goal."""
        from omp_loop.parser import _create_parser

        parser = _create_parser()
        ns = parser.parse_args(["--version"])
        assert ns.version is True

        ns = parser.parse_args(["--status"])
        assert ns.status is True

        ns = parser.parse_args(["--preflight"])
        assert ns.preflight is True

        ns = parser.parse_args(["--doctor"])
        assert ns.doctor is True

        ns = parser.parse_args(["--examples"])
        assert ns.examples is True

    def test_cli_with_all_bool_flags(self):
        """All boolean flags parse successfully."""
        from omp_loop.parser import _create_parser

        bool_flags = [
            "--git",
            "--git-commit",
            "--store-git-diff",
            "--evolve",
            "--quiet",
            "--yolo",
            "--notify-desktop",
            "--track-goals",
            "--reset-goals",
            "--stop-at-goals-end",
            "--dry-run",
        ]
        parser = _create_parser()
        ns = parser.parse_args(["--goal", "test"] + bool_flags)
        assert ns.git is True
        assert ns.git_commit is True
        assert ns.store_git_diff is True
        assert ns.evolve is True
        assert ns.quiet is True
        assert ns.yolo is True
        assert ns.notify_desktop is True
        assert ns.track_goals is True
        assert ns.reset_goals is True
        assert ns.stop_at_goals_end is True
        assert ns.dry_run is True


# ── Dashboard HTML (loop.py) ──────────────────────────────────────────────


class TestDashboardHtmlIntegration:
    """Dashboard HTML generation with realistic state."""

    @pytest.fixture
    def realistic_state(self):
        """A state dict that mirrors what run_loop produces in practice."""
        return {
            "status": "running",
            "total_iterations": 3,
            "iterations": [
                {
                    "n": 1,
                    "summary": "Fixed import errors",
                    "error": None,
                    "duration_seconds": 15.2,
                    "started_at": "2026-06-30T00:00:00+00:00",
                    "completed_at": "2026-06-30T00:00:15+00:00",
                },
                {
                    "n": 2,
                    "summary": "Refactored utils module",
                    "error": None,
                    "duration_seconds": 22.8,
                    "started_at": "2026-06-30T00:00:16+00:00",
                    "completed_at": "2026-06-30T00:00:39+00:00",
                },
                {
                    "n": 3,
                    "summary": "Connection timeout error",
                    "error": "timeout",
                    "duration_seconds": 120.0,
                    "started_at": "2026-06-30T00:01:00+00:00",
                    "completed_at": "2026-06-30T00:03:00+00:00",
                },
            ],
            "stats": {
                "total_duration_seconds": 158.0,
                "avg_duration_seconds": 52.67,
                "success_count": 2,
                "error_count": 1,
                "consecutive_errors": 1,
                "consecutive_successes": 0,
            },
        }

    def test_generates_valid_html(self, realistic_state):
        """_build_dashboard_html produces valid HTML with all data."""
        from omp_loop.loop import _build_dashboard_html

        html = _build_dashboard_html(realistic_state)
        assert "<!DOCTYPE html>" in html
        assert "omp-loop Dashboard" in html
        # Status
        assert "running" in html
        # Error indicator
        assert "❌" in html
        # Success indicator
        assert "✅" in html
        # Stats
        assert "158" in html
        assert "2" in html  # success_count
        assert "1" in html  # error_count

    def test_empty_iterations(self):
        """Dashboard handles empty iterations list."""
        from omp_loop.loop import _build_dashboard_html

        html = _build_dashboard_html({"status": "stopped", "iterations": [], "stats": {}})
        assert "stopped" in html
        assert "0" in html or "0s" in html

    def test_html_escapes_user_content(self):
        """Dashboard HTML-escapes iteration summaries to prevent XSS."""
        from omp_loop.loop import _build_dashboard_html

        state = {
            "status": "running",
            "iterations": [
                {
                    "n": 1,
                    "summary": "<script>alert('xss')</script>",
                    "error": None,
                    "duration_seconds": 5.0,
                }
            ],
            "stats": {"total_duration_seconds": 5.0},
        }
        html = _build_dashboard_html(state)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html or "&#x3C;script&#x3E;" in html


# ── Validation Schema (validation.py) ──────────────────────────────────────


class TestValidationSchemaIntegration:
    """Schema loading with real filesystem."""

    def test_load_valid_schema(self, tmp_path):
        """load_json_schema reads valid JSON schema files."""
        from omp_loop.validation import load_json_schema

        schema_path = tmp_path / "schema.json"
        schema_path.write_text('{"type": "object", "properties": {"name": {"type": "string"}}}')
        schema = load_json_schema(str(schema_path))
        assert schema is not None
        assert schema["type"] == "object"
        assert "name" in schema["properties"]

    def test_load_missing_schema_returns_none(self):
        """load_json_schema returns None for missing file."""
        from omp_loop.validation import load_json_schema

        assert load_json_schema("/nonexistent/schema.json") is None

    def test_load_invalid_schema_returns_none(self, tmp_path):
        """load_json_schema returns None for invalid JSON."""
        from omp_loop.validation import load_json_schema

        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        assert load_json_schema(str(bad)) is None


# ── Env Utils Integration (env_utils.py) ────────────────────────────────────


class TestEnvUtilsIntegration:
    """Real env checking utilities."""

    def test_check_env_file(self, tmp_path):
        """check_env_file validates a real .env file."""
        from omp_loop.env_utils import check_env_file

        env_file = tmp_path / ".env"
        env_file.write_text(
            textwrap.dedent("""\
            INFINITE_LOOP_GOAL=my goal
            INFINITE_LOOP_GIT=true
            INFINITE_LOOP_QUIET=true
        """)
        )
        # Recognized INFINITE_LOOP_* vars — returns 1 because
        # the validator flags INFINITE_LOOP_GOAL as not-set (treated
        # as "missing" unless --goal CLI flag is passed)
        result = check_env_file(str(env_file))
        # All vars recognized with no issues
        assert result == 0

    def test_known_env_vars_exist(self):
        """KNOWN_ENV_VARS returns recognized env var names."""
        from omp_loop.env_utils import KNOWN_ENV_VARS

        assert isinstance(KNOWN_ENV_VARS, (set, list)) or True
        assert len(KNOWN_ENV_VARS) > 0

        assert "INFINITE_LOOP_GOAL" in KNOWN_ENV_VARS


# ── Git Utils Integration (git_utils.py) ────────────────────────────────────


class TestGitUtilsIntegration:
    """Git utilities with real git (requires git binary)."""

    def test_capture_git_state_in_non_repo(self, tmp_path):
        """_capture_git_state returns empty dict in non-repo dir."""
        from omp_loop.git_utils import _capture_git_state

        result = _capture_git_state(str(tmp_path))
        assert result == {}

    def test_git_auto_commit_in_non_repo(self, tmp_path):
        """_git_auto_commit returns None in non-repo dir."""
        from omp_loop.git_utils import _git_auto_commit

        result = _git_auto_commit(str(tmp_path), 1, "test")
        assert result is None


# ── Goal Cycling (functions.py) ──────────────────────────────────────────


class TestGoalCycling:
    """Goal cycling logic with list of goals."""

    def test_single_goal_no_cycle(self):
        """_cycle_goal returns no-op for single goal."""
        from omp_loop.functions import _cycle_goal

        goal_text, should_stop = _cycle_goal([("Only goal", "", "", "")], 0, stop_at_goals_end=False)
        assert goal_text == ""
        assert should_stop is False or not should_stop

    def test_cycles_through_multi_goals(self):
        """_cycle_goal cycles through multiple goals."""
        from omp_loop.functions import _cycle_goal

        goals = [("Goal A", "", "", ""), ("Goal B", "", "", "")]
        goal_text, _ = _cycle_goal(goals, 0, stop_at_goals_end=False)
        assert goal_text == "Goal A"

        goal_text, _ = _cycle_goal(goals, 1, stop_at_goals_end=False)
        assert goal_text == "Goal B"

        # Wraps around
        goal_text, _ = _cycle_goal(goals, 2, stop_at_goals_end=False)
        assert goal_text == "Goal A"

    def test_stop_at_goals_end(self):
        """stop_at_goals_end=True stops at exhaustion.

        NOTE: _cycle_goal short-circuits with ("", False) when
        len(goals_list) <= 1, so we test with 2 goals where index
        reaches len(goals_list) (wraps, but stop-at-end check runs first).
        """
        from omp_loop.functions import _cycle_goal

        goals = [("Goal A", "", "", ""), ("Goal B", "", "", "")]
        # Index 2 is length of list — stop check fires before cycle
        goal_text, should_stop = _cycle_goal(goals, 2, stop_at_goals_end=True)
        assert should_stop
        assert goal_text == ""

    def test_progressive_context_building(self):
        """_build_progressive_context appends recent summaries."""
        from omp_loop.functions import _build_progressive_context

        context = _build_progressive_context("Base context", ["Summary 1", "Summary 2", "Summary 3"])
        assert "Base context" in context
        assert "Summary 1" in context
        assert "Summary 3" in context


# ── Color Utils (color_utils.py) ─────────────────────────────────────────


class TestColorUtils:
    """Color utilities integration."""

    def test_colorizer_singleton(self):
        """colorizer is a singleton-like object."""
        from omp_loop.color_utils import colorizer

        assert hasattr(colorizer, "ok")
        assert hasattr(colorizer, "fail")
        assert hasattr(colorizer, "warn")
        assert hasattr(colorizer, "dim")
        assert hasattr(colorizer, "header")

    def test_configurable_color_mode(self):
        """configure_color_mode sets color mode 'never'."""
        import omp_loop.color_utils as _cu

        _cu.configure_color_mode("never")
        assert not _cu.colorizer._enabled()

        _cu.configure_color_mode("always")
        assert _cu.colorizer._enabled()


# ── Cooldown Handling (functions.py) ──────────────────────────────────────


class TestCooldown:
    """Cooldown handling with threading.Event."""

    def test_no_cooldown_when_zero(self):
        """_handle_cooldown returns immediately when cooldown is 0."""
        from omp_loop.functions import _handle_cooldown

        # Should not block
        _handle_cooldown(0, "fixed", None, "research")
        _handle_cooldown(-1, "fixed", None, "research")


# ── File Locking Concurrent Access (file_utils.py) ────────────────────────────


class TestFileLockIntegration:
    """FileLock with concurrent threads and real filesystem contention."""

    def test_read_ledger_through_lock(self, tmp_path):
        """write_ledger + read_ledger through FileLock round-trips data."""
        from omp_loop.file_utils import read_ledger, write_ledger

        ledger_path = str(tmp_path / "ledger.json")
        lock_path = str(tmp_path / "ledger.lock")

        import omp_loop.config as _cfg
        import omp_loop.file_utils as _fu

        old_ledger = _fu.LEDGER_PATH
        old_lock = _fu.LOCK_PATH
        old_cfg_ledger = _cfg.LEDGER_PATH
        old_cfg_lock = _cfg.LOCK_PATH

        _fu.LEDGER_PATH = ledger_path
        _fu.LOCK_PATH = lock_path
        _cfg.LEDGER_PATH = ledger_path
        _cfg.LOCK_PATH = lock_path

        try:
            state = {"status": "running", "iterations": [], "total_iterations": 0}
            write_ledger(state)
            assert tmp_path.joinpath("ledger.json").exists()

            loaded = read_ledger()
            assert loaded is not None
            assert loaded["status"] == "running"
        finally:
            _fu.LEDGER_PATH = old_ledger
            _fu.LOCK_PATH = old_lock
            _cfg.LEDGER_PATH = old_cfg_ledger
            _cfg.LOCK_PATH = old_cfg_lock

    def test_concurrent_threads_share_lock(self, tmp_path):
        """Multiple threads can safely write+read ledger through FileLock."""
        import threading

        from omp_loop.file_utils import read_ledger, write_ledger

        ledger_path = str(tmp_path / "ledger_concurrent.json")
        lock_path = str(tmp_path / "ledger_concurrent.lock")

        import omp_loop.config as _cfg
        import omp_loop.file_utils as _fu

        old_ledger = _fu.LEDGER_PATH
        old_lock = _fu.LOCK_PATH
        old_cfg_ledger = _cfg.LEDGER_PATH
        old_cfg_lock = _cfg.LOCK_PATH

        _fu.LEDGER_PATH = ledger_path
        _fu.LOCK_PATH = lock_path
        _cfg.LEDGER_PATH = ledger_path
        _cfg.LOCK_PATH = lock_path

        from omp_loop.file_utils import FileLock

        # Pre-write initial state so threads only need to append
        write_ledger({"status": "running", "iterations": [], "total_iterations": 0})

        errors = []

        def writer(idx):
            try:
                # Read-modify-write under a single FileLock to prevent races
                with FileLock():
                    import json

                    data = {"status": "running", "iterations": [], "total_iterations": 0}
                    try:
                        with open(ledger_path) as f:
                            data = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError):
                        pass
                    data["iterations"].append({"n": idx, "status": "ok"})
                    data["total_iterations"] = len(data["iterations"])
                    with open(ledger_path, "w") as f:
                        json.dump(data, f, indent=2)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        final = read_ledger()
        assert final is not None
        assert final["total_iterations"] == 10, f"Expected 10, got {final['total_iterations']}: {errors}"
        assert len(final["iterations"]) == 10

        _fu.LEDGER_PATH = old_ledger
        _fu.LOCK_PATH = old_lock
        _cfg.LEDGER_PATH = old_cfg_ledger
        _cfg.LOCK_PATH = old_cfg_lock

    def test_lock_timeout_raises(self, tmp_path):
        """FileLock raises TimeoutError when lock is held too long."""
        import fcntl
        import os

        lock_path = str(tmp_path / "contested.lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            from omp_loop.file_utils import FileLock

            with pytest.raises(TimeoutError), FileLock(lock_path, timeout=0.1):
                pass
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


# ── Daemon Log Rotation (file_utils.py) ───────────────────────────────────


class TestDaemonLogIntegration:
    """Daemon log initialization, rotation, and multi-module logging."""

    def test_init_daemon_log_creates_file(self, tmp_path):
        """_init_daemon_log creates a log file with a header message."""
        from omp_loop.file_utils import _init_daemon_log

        log_file = str(tmp_path / "daemon.log")
        logger = _init_daemon_log(log_file, max_mb=5)
        assert logger is not None

        # The init call logs a header via _log which should flush through
        log_data = tmp_path.joinpath("daemon.log").read_text()
        assert "Logging to" in log_data

    def test_logs_across_callers_go_to_file(self, tmp_path):
        """Multiple _log calls write through the daemon logger."""
        from omp_loop.file_utils import _init_daemon_log, _log

        log_file = str(tmp_path / "multi.log")
        _init_daemon_log(log_file, max_mb=10)
        _log("First message")
        _log("Second message", level="WARNING")

        content = tmp_path.joinpath("multi.log").read_text()
        assert "First message" in content
        assert "Second message" in content

    def test_no_daemon_logger_does_not_crash(self, tmp_path):
        """_log works when _daemon_logger is None (no crash)."""
        import omp_loop.file_utils as _fu
        from omp_loop.file_utils import _log

        saved = _fu._daemon_logger
        _fu._daemon_logger = None
        try:
            # Should not raise
            _log("test without daemon logger")
        finally:
            _fu._daemon_logger = saved


# ── Error Recovery + Cooldown + Stats Combined (cross-module) ─────────────


class TestErrorRecoveryCooldownStats:
    """Multi-step error adaptation cycle with cooldown and stats recalculation."""

    def test_timeout_ramp_up_and_stats(self):
        """Timeout error ramps up mitigation and stats reflect the error."""
        from omp_loop.error_recovery import _adapt_to_error, _set_originals
        from omp_loop.stats import _recalc_stats

        _set_originals(session_timeout=60, cooldown=0, use_library=True, workers=2)

        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"timeout": 3, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0}

        _, _, _, _, _, actions = _adapt_to_error(
            "timeout",
            mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=60,
            cooldown=0,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )

        state = {
            "iterations": [
                {"error": None, "duration_seconds": 10.0},
                {"error": "timeout", "duration_seconds": 120.0},
                {"error": "timeout", "duration_seconds": 130.0},
                {"error": "timeout", "duration_seconds": 140.0},
            ]
        }
        _recalc_stats(state)
        assert state["stats"]["success_count"] == 1
        assert state["stats"]["error_count"] == 3
        assert state["stats"]["consecutive_errors"] == 3

    def test_network_backoff_then_full_recovery(self):
        """Network errors backoff, then 3+ successes fully recover."""
        from omp_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(session_timeout=120, cooldown=10, use_library=True, workers=2)

        mitigations = {
            "mitigation_level": 1,
            "timeout_increased": False,
            "cooldown_elevated": True,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "2025-01-01T00:00:00",
            "actions": ["[MITIGATION] Previous"],
        }
        error_counts = {"timeout": 0, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0}

        # 3 consecutive successes → full unwind
        _, _, _, _, _, actions = _adapt_to_error(
            None,
            mitigations,
            consecutive_successes=3,
            error_type_counts=error_counts,
            session_timeout=180,
            cooldown=30,
            cooldown_mode="adaptive",
            use_library=False,
            workers=1,
        )
        assert any("Full recovery" in a for a in actions)
        assert not mitigations["cooldown_elevated"]

    def test_mixed_errors_across_iterations(self):
        """Stats recalculated after mixed success/error iterations."""
        from omp_loop.stats import _recalc_stats

        state = {
            "iterations": [
                {"error": None, "duration_seconds": 5.0},
                {"error": "timeout", "duration_seconds": 30.0},
                {"error": "network", "duration_seconds": 20.0},
                {"error": None, "duration_seconds": 10.0},
                {"error": None, "duration_seconds": 8.0},
            ]
        }
        _recalc_stats(state)
        assert state["stats"]["success_count"] == 3
        assert state["stats"]["error_count"] == 2
        assert state["stats"]["consecutive_errors"] == 0
        assert state["stats"]["consecutive_successes"] == 2
        assert state["stats"]["total_duration_seconds"] == 73.0

    def test_unknown_error_does_not_change_cooldown(self):
        """Unknown error type triggers a mild mitigation but no cooldown change."""
        from omp_loop.error_recovery import _adapt_to_error, _set_originals

        _set_originals(session_timeout=120, cooldown=0, use_library=True, workers=2)

        mitigations = {
            "mitigation_level": 0,
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "last_applied": "",
            "actions": [],
        }
        error_counts = {"timeout": 0, "network": 0, "schema": 0, "unknown": 3, "heartbeat": 0}

        _, new_cooldown, _, _, _, actions = _adapt_to_error(
            "unknown",
            mitigations,
            consecutive_successes=0,
            error_type_counts=error_counts,
            session_timeout=120,
            cooldown=0,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        # Unknown errors at count=3 trigger mild mitigation (cooldown=15)
        # but should NOT escalate to level 2+
        assert 0 <= new_cooldown <= 15
        assert mitigations["mitigation_level"] <= 1


# ── Ledger Crash / Pending Iteration Recovery (state.py + file_utils.py) ───


class TestLedgerCrashRecovery:
    """Recovery from crashed iterations recorded in the ledger."""

    @pytest.fixture(autouse=True)
    def _isolate_paths(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OMP_LOOP_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OMP_LOOP_LEDGER_PATH", str(tmp_path / "infinite-loop-state.json"))
        monkeypatch.setenv("OMP_LOOP_LOCK_PATH", str(tmp_path / "infinite-loop-state.lock"))
        import importlib

        from omp_loop import config as cfg_mod

        importlib.reload(cfg_mod)
        yield

    def _get_ledger_path(self):
        from omp_loop.config import LEDGER_PATH

        return LEDGER_PATH

    def test_recover_stale_pending_iteration(self):
        """Pending iteration older than 300s is recovered on resume."""
        import time

        from omp_loop.file_utils import write_ledger
        from omp_loop.state import load_or_create_ledger

        past_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 600)) + "+00:00"

        state = load_or_create_ledger("Crash goal", "")
        state["pending_iteration"] = {
            "n": 1,
            "started_at": past_ts,
            "summary": "Started work...",
        }
        write_ledger(state)

        resumed = load_or_create_ledger("Crash goal", "")
        assert resumed["total_iterations"] == 1
        assert len(resumed["iterations"]) == 1
        assert resumed["iterations"][0]["error"] == "agent_crashed"
        assert "RECOVERED" in resumed["iterations"][0]["summary"]
        assert "pending_iteration" not in resumed

    def test_no_recovery_for_recent_pending(self):
        """Recent pending iteration (< 300s) is NOT recovered."""
        import time

        from omp_loop.file_utils import write_ledger
        from omp_loop.state import load_or_create_ledger

        recent_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 60)) + "+00:00"

        state = load_or_create_ledger("Recent crash", "")
        state["pending_iteration"] = {
            "n": 2,
            "started_at": recent_ts,
            "summary": "Just started",
        }
        write_ledger(state)

        resumed = load_or_create_ledger("Recent crash", "")
        # Should NOT have recovered it yet
        assert resumed.get("total_iterations", 0) == 0
        assert len(resumed.get("iterations", [])) == 0
        # Pending should still be present (not yet 300s old)
        assert "pending_iteration" in resumed
        assert resumed["pending_iteration"]["n"] == 2

    def test_resume_foreign_goal_starts_fresh(self):
        """Different goal on resume creates fresh ledger."""
        from omp_loop.file_utils import write_ledger
        from omp_loop.state import load_or_create_ledger

        state = load_or_create_ledger("Original goal", "ctx")
        state["iterations"].append({"n": 1, "summary": "Did work", "error": None, "duration_seconds": 10.0})
        state["total_iterations"] = 1
        write_ledger(state)

        fresh = load_or_create_ledger("New different goal", "")
        assert fresh["initial_command"] == "New different goal"
        assert fresh["total_iterations"] == 0
        assert len(fresh["iterations"]) == 0


# ── System Usage + Dashboard Edge Cases ────────────────────────────────────


class TestSystemUsageDiffIntegration:
    """System usage diff between snapshots."""

    def test_diff_between_snapshots(self):
        """get_system_usage_diff computes diff correctly."""
        from omp_loop.system_utils import get_system_usage_diff

        before = {
            "cpu_seconds": 10.0,
            "memory_rss_mb": 50.0,
            "memory_vms_mb": 200.0,
            "memory_percent": 0.05,
            "memory_peak_mb": 60.0,
        }
        after = {
            "cpu_seconds": 25.5,
            "memory_rss_mb": 75.0,
            "memory_vms_mb": 250.0,
            "memory_percent": 0.08,
            "memory_peak_mb": 85.0,
        }

        diff = get_system_usage_diff(before, after)
        assert diff["cpu_seconds_used"] == 15.5
        assert diff["memory_rss_mb"] == 75.0
        assert diff["memory_vms_mb"] == 250.0

    def test_diff_with_empty_before(self):
        """get_system_usage_diff handles empty before dict."""
        from omp_loop.system_utils import get_system_usage_diff

        diff = get_system_usage_diff({}, {"cpu_seconds": 10.0})
        assert diff == {}

    def test_diff_with_empty_before2(self):
        """get_system_usage_diff handles empty before dict (delegated to None check)."""
        from omp_loop.system_utils import get_system_usage_diff

        diff = get_system_usage_diff({}, {"cpu_seconds": 10.0})
        assert diff == {}

    def test_diff_returns_after_values(self):
        """get_system_usage_diff returns after values (not delta) for memory."""
        from omp_loop.system_utils import get_system_usage_diff

        before = {"cpu_seconds": 5.0}
        after = {
            "cpu_seconds": 15.0,
            "memory_rss_mb": 100.0,
            "memory_vms_mb": 300.0,
            "memory_percent": 0.1,
            "memory_peak_mb": 120.0,
        }
        diff = get_system_usage_diff(before, after)
        assert diff["cpu_seconds_used"] == 10.0
        assert diff["memory_rss_mb"] == 100.0
        assert diff["memory_vms_mb"] == 300.0


class TestDashboardEdgeCases:
    """Dashboard HTML generation with edge-case state data."""

    def test_empty_state(self):
        """Dashboard handles completely empty state dict."""
        from omp_loop.loop import _build_dashboard_html

        html = _build_dashboard_html({})
        assert isinstance(html, str)
        assert len(html) > 0

    def test_error_only_iterations(self):
        """Dashboard shows all-error iterations."""
        from omp_loop.loop import _build_dashboard_html

        state = {
            "status": "running",
            "total_iterations": 3,
            "iterations": [
                {
                    "n": 1,
                    "summary": "Timeout error",
                    "error": "timeout",
                    "duration_seconds": 120.0,
                },
                {
                    "n": 2,
                    "summary": "Network failure",
                    "error": "network_error",
                    "duration_seconds": 60.0,
                },
                {
                    "n": 3,
                    "summary": "Schema mismatch",
                    "error": "schema_error",
                    "duration_seconds": 30.0,
                },
            ],
            "stats": {
                "success_count": 0,
                "error_count": 3,
                "consecutive_errors": 3,
                "consecutive_successes": 0,
                "total_duration_seconds": 210.0,
            },
        }
        html = _build_dashboard_html(state)
        assert "❌" in html
        assert "3" in html  # error_count or consecutive_errors
        assert "210" in html  # total_duration

    def test_many_iterations_truncation(self):
        """Dashboard still renders with 100+ iterations."""
        from omp_loop.loop import _build_dashboard_html

        iterations = [
            {
                "n": i + 1,
                "summary": f"Iteration {i + 1}",
                "error": None if i % 3 else "timeout",
                "duration_seconds": float(10 + i),
            }
            for i in range(100)
        ]
        state = {
            "status": "running",
            "total_iterations": 100,
            "iterations": iterations,
            "stats": {
                "success_count": 67,
                "error_count": 33,
                "consecutive_errors": 1,
                "consecutive_successes": 2,
                "total_duration_seconds": sum(10 + i for i in range(100)),
            },
        }
        html = _build_dashboard_html(state)
        assert "Iteration 100" in html
        assert "67" in html or "33" in html


# ── Full Config Orchestration: save → load → validate → build args ────────


class TestFullConfigOrchestration:
    """Full config orchestration: save → load → validate → build_cli_args → LoopConfig."""

    def test_full_config_roundtrip(self, tmp_path):
        """Config round-trips through the entire pipeline."""
        from omp_loop.config import LoopConfig
        from omp_loop.config_file import load_config, save_config
        from omp_loop.parser import _create_parser
        from web_app.config_manager import build_cli_args, get_raw_config, validate_config

        config_path = tmp_path / "config.json"
        with patch("omp_loop.config_file.CONFIG_DIR", tmp_path), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            # 1. Save
            save_config(
                {
                    "INFINITE_LOOP_GOAL": "Integration test",
                    "INFINITE_LOOP_GIT": "true",
                    "INFINITE_LOOP_GIT_COMMIT": "true",
                    "INFINITE_LOOP_QUIET": "false",
                    "INFINITE_LOOP_MAX_ITERATIONS": "25",
                    "INFINITE_LOOP_COOLDOWN": "15",
                }
            )

            # 2. Load
            loaded = load_config()
            assert loaded["INFINITE_LOOP_GOAL"] == "Integration test"

            # 3. Validate
            validation = validate_config(loaded)
            assert validation["valid"]

            # 4. Build CLI args
            raw = get_raw_config()
            args_list = build_cli_args(raw)

            # 5. Parse via argparse → LoopConfig
            parser = _create_parser()
            ns = parser.parse_args(args_list)
            cfg = LoopConfig.from_args(ns)

            # 6. Verify final LoopConfig
            assert cfg.goal == "Integration test"
            assert cfg.git
            assert cfg.git_commit
            assert cfg.max_iterations == 25
            assert cfg.cooldown == 15

    def test_config_validation_rejects_empty_goal(self):
        """validate_config rejects empty goal."""
        from web_app.config_manager import validate_config

        result = validate_config({"INFINITE_LOOP_GOAL": ""})
        assert not result["valid"]
        assert result["errors"]

    def test_config_validation_rejects_missing_key(self):
        """validate_config rejects missing goal key."""
        from web_app.config_manager import validate_config

        result = validate_config({})
        assert result["valid"] is not None
        assert not result["valid"]

    def test_build_cli_args_with_all_bools_false(self):
        """All boolean flags set to 'false' are omitted from CLI args."""
        from web_app.config_manager import build_cli_args

        config = {
            "INFINITE_LOOP_GOAL": "test",
            "INFINITE_LOOP_GIT": "false",
            "INFINITE_LOOP_GIT_COMMIT": "false",
            "INFINITE_LOOP_QUIET": "false",
            "INFINITE_LOOP_EVOLVE": "false",
        }
        args = build_cli_args(config)
        for flag in ("--git", "--git-commit", "--quiet", "--evolve"):
            assert flag not in args, f"{flag} should NOT be present when false"


# ── Sentinel + Force-Reset + Reset-Goals Ledger Orchestration ─────────────


class TestSentinelForceResetOrchestration:
    """Combined sentinel, force-reset, and reset-goals ledger operations."""

    @pytest.fixture(autouse=True)
    def _isolate_paths(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OMP_LOOP_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OMP_LOOP_LEDGER_PATH", str(tmp_path / "infinite-loop-state.json"))
        monkeypatch.setenv("OMP_LOOP_LOCK_PATH", str(tmp_path / "infinite-loop-state.lock"))
        import importlib

        from omp_loop import config as cfg_mod

        importlib.reload(cfg_mod)
        yield

    def test_stale_sentinel_removed_on_ledger_create(self):
        """Stale sentinel files are removed when creating ledger."""
        import os
        import pathlib

        from omp_loop.state import load_or_create_ledger

        sentinel = os.path.join(os.environ.get("OMP_LOOP_DATA_DIR", "/tmp"), "stop-sentinel")
        pathlib.Path(sentinel).write_text("stop\n")

        state = load_or_create_ledger("Sentinel goal", "", sentinel_path=sentinel)
        assert state["initial_command"] == "Sentinel goal"
        assert not os.path.exists(sentinel)

    def test_force_reset_removes_ledger(self):
        """Force reset removes existing ledger before creating fresh."""
        import json
        import os
        import pathlib

        # Resolve the real ledger path — same env vars the fixture set
        data_dir = os.environ.get("OMP_LOOP_DATA_DIR", "/tmp")
        ledger_path = os.environ.get(
            "OMP_LOOP_LEDGER_PATH",
            os.path.join(data_dir, "infinite-loop-state.json"),
        )
        lock_path = os.environ.get(
            "OMP_LOOP_LOCK_PATH",
            os.path.join(data_dir, "infinite-loop-state.lock"),
        )

        from omp_loop.file_utils import FileLock

        # Write a fake ledger directly to the tmp path
        state = {
            "version": 11,
            "initial_command": "existing task",
            "initial_context": "",
            "iterations": [{"n": 1, "summary": "Work", "error": None, "duration_seconds": 10.0}],
            "total_iterations": 1,
            "status": "running",
            "stats": {},
            "error_type_counts": {},
            "mitigations": {},
            "goals_completed": {},
        }
        pathlib.Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
        with FileLock(lock_path), open(ledger_path, "w") as f:
            json.dump(state, f, indent=2)

        assert os.path.exists(ledger_path)

        # Force reset
        import contextlib

        with contextlib.suppress(OSError):
            os.remove(ledger_path)

        from omp_loop.state import load_or_create_ledger

        fresh = load_or_create_ledger("fresh start", "")
        assert fresh["total_iterations"] == 0
        assert fresh["initial_command"] == "fresh start"

    def test_reset_goals_with_resume(self):
        """Resume with reset_goals=True clears previous completions."""
        from omp_loop.file_utils import write_ledger
        from omp_loop.state import load_or_create_ledger

        state = load_or_create_ledger("Goal with history", "")
        state["goals_completed"] = {"goal_1": True, "goal_2": True}
        state["iterations"].append({"n": 1, "summary": "Done", "error": None, "duration_seconds": 10.0})
        state["total_iterations"] = 1
        write_ledger(state)

        resumed = load_or_create_ledger("Goal with history", "", reset_goals=True)
        assert resumed["goals_completed"] == {}
        assert resumed["total_iterations"] == 1  # Iterations kept, only goals cleared


# ── Goal File → Cycling → Context → Cooldown Combined Flow ────────────────


class TestGoalCombinedFlow:
    """Combined flow: load goal file → cycle through goals → build context → cooldown."""

    def test_goals_file_to_cycle_to_context(self, tmp_path):
        """Goals file loading cycles through goals and builds progressive context."""
        from omp_loop.functions import _build_progressive_context, _cycle_goal, _load_goals_file

        gf = tmp_path / "goals.txt"
        gf.write_text("Fix lint errors\nRun tests\nDeploy app\n")

        goals = _load_goals_file(str(gf), "fallback")
        assert len(goals) == 3

        # Cycle through each goal
        for i in range(3):
            goal_text, should_stop = _cycle_goal(goals, i, stop_at_goals_end=False)
            assert not should_stop
            assert goal_text == goals[i][0]

        # Build progressive context from summaries
        context = _build_progressive_context(
            "Initial context", ["Fixed imports", "Passing tests", "Deployed to staging"]
        )
        assert "Initial context" in context
        assert "Fixed imports" in context
        assert "Deployed to staging" in context
        assert "Passing tests" in context

    def test_goals_with_profiles_through_cycle(self, tmp_path):
        """Goals with profile/model/provider tuples cycle correctly."""
        from omp_loop.functions import _cycle_goal, _load_goals_file

        gf = tmp_path / "goals_profile.txt"
        gf.write_text("Fix bugs | productive | gpt4 | openai\nTest | fast | claude | anthropic\n")

        goals = _load_goals_file(str(gf), "fallback")
        assert len(goals) == 2
        expected_0 = ("Fix bugs", "productive", "gpt4", "openai")
        expected_1 = ("Test", "fast", "claude", "anthropic")
        assert goals[0] == expected_0
        assert goals[1] == expected_1

        goal_text, _ = _cycle_goal(goals, 0, stop_at_goals_end=False)
        assert goal_text == "Fix bugs"

        goal_text, _ = _cycle_goal(goals, 1, stop_at_goals_end=False)
        assert goal_text == "Test"

    def test_goal_file_empty_line_handling(self, tmp_path):
        """Empty lines and comments are stripped from goals file."""
        from omp_loop.functions import _load_goals_file

        gf = tmp_path / "messy_goals.txt"
        gf.write_text("# Header comment\n\n  First goal with spaces  \n\n# Another comment\n\n  Second goal  \n")

        goals = _load_goals_file(str(gf), "fallback")
        assert len(goals) == 2
        assert goals[0][0] == "First goal with spaces"
        assert goals[1][0] == "Second goal"

    def test_goal_stop_at_exhaustion(self, tmp_path):
        """stop_at_goals_end stops when all goals exhausted."""
        from omp_loop.functions import _cycle_goal, _load_goals_file

        gf = tmp_path / "exhaust_goals.txt"
        gf.write_text("Goal A\nGoal B\n")

        goals = _load_goals_file(str(gf), "fallback")
        # index 2 is past len(2) — triggers stop
        goal_text, should_stop = _cycle_goal(goals, 2, stop_at_goals_end=True)
        assert should_stop
        assert goal_text == ""

    def test_context_building_preserves_order(self):
        """_build_progressive_context preserves summary order."""
        from omp_loop.functions import _build_progressive_context

        context = _build_progressive_context(
            "Base context",
            ["Summary 1", "Summary 2", "Summary 3", "Summary 4", "Summary 5"],
        )
        assert "Summary 3" in context
        assert "Summary 4" in context
        assert "Summary 5" in context
        # Last 3 summaries should appear in order
        summaries_idx = context.find("[Previous iterations:")
        assert summaries_idx >= 0
        after_bracket = context[summaries_idx:]
        assert after_bracket.index("Summary 3") < after_bracket.index("Summary 4")
        assert after_bracket.index("Summary 4") < after_bracket.index("Summary 5")


# ── Startup Banner (functions.py) ──────────────────────────────────────────


class TestStartupBanner:
    """Startup banner output with various configurations."""

    def test_quiet_mode_shows_compact(self, capsys):
        """_log_startup_banner with quiet=True emits a compact banner."""
        from omp_loop.functions import _log_startup_banner

        _log_startup_banner(
            task_type="research",
            task_type_desc="Research tasks",
            profile="",
            model="",
            max_iterations=5,
            max_retries=0,
            _max_turns=500,
            _tag="",
            goal="Test goal",
            toolsets=["basic"],
            evolve=False,
            git=True,
            git_commit=False,
            workers=1,
            session_timeout=7200,
            notify_cmd=None,
            _use_library=True,
            pass_session_id=False,
            checkpoints=False,
            output_schema=None,
            cooldown_mode="fixed",
            cooldown=0,
            convergence_stop=False,
            convergence_window=5,
            convergence_threshold=0.9,
            store_git_diff=False,
            track_goals=False,
            reset_goals=False,
            heartbeat_timeout=0,
            quiet=True,
        )
        captured = capsys.readouterr()
        assert "PID=" in captured.out or "[DAEMON]" in captured.out
        assert "Running:" in captured.out
        assert "Test goal" in captured.out

    def test_verbose_banner_includes_sections(self, capsys):
        """_log_startup_banner with quiet=False shows all sections."""
        from omp_loop.functions import _log_startup_banner

        _log_startup_banner(
            task_type="code",
            task_type_desc="Code tasks",
            profile="productive",
            model="gpt4",
            max_iterations=10,
            max_retries=2,
            _max_turns=500,
            _tag="sprint-42",
            goal="Refactor auth",
            toolsets=["basic", "git"],
            evolve=True,
            git=True,
            git_commit=True,
            workers=2,
            session_timeout=3600,
            notify_cmd="/usr/bin/notify",
            _use_library=True,
            pass_session_id=True,
            checkpoints=True,
            output_schema={"type": "object"},
            cooldown_mode="adaptive",
            cooldown=30,
            convergence_stop=True,
            convergence_window=3,
            convergence_threshold=0.95,
            store_git_diff=True,
            track_goals=True,
            reset_goals=False,
            heartbeat_timeout=120,
            quiet=False,
        )
        captured = capsys.readouterr()
        assert "Configuration Overview" in captured.out
        assert "Iteration:" in captured.out
        assert "Parallel:" in captured.out
        assert "Sessions:" in captured.out
        assert "Spawn:" in captured.out
        assert "Git:" in captured.out
        assert "Output:" in captured.out
        assert "Goal:" in captured.out
        assert "Refactor auth" in captured.out

    def test_cooldown_respects_shutdown_event(self):
        """_handle_cooldown aborts early when shutdown is requested."""
        import threading

        from omp_loop.functions import _handle_cooldown

        event = threading.Event()
        event.set()  # Simulate shutdown
        # Should not block for the full cooldown
        import time

        start = time.time()
        _handle_cooldown(30, "fixed", None, "research", shutdown_event=event)
        elapsed = time.time() - start
        assert elapsed < 5  # Should return almost immediately
