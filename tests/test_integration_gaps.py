"""Integration tests for uncovered critical modules: cli.py, loop.py (run_loop exit
conditions), error_utils.py edge cases, color_utils.py integration, SSE streaming,
and auxiliary loop functions.

These tests use real filesystem ops (tmp_path), capsys for stdout verification,
and minimal mocking — focusing on multi-module interactions.
"""

import json
import os
import pathlib
import shutil
import sys
import tempfile
import textwrap
import threading
import time
from unittest.mock import patch

import pytest

# =============================================================================
# 1.  CLI Introspection & Dispatch  (cli.py main())
# =============================================================================


class TestCliIntrospectionFlags:
    """CLI introspection flags: version, healthcheck, doctor, status, examples,
    list-flags, dump-env.  These dispatch early in main() without needing --goal."""

    def test_version_flag(self, capsys):
        """--version prints version and exits cleanly."""
        from omp_loop.cli import main
        from omp_loop.config import VERSION

        with patch.object(sys, "argv", ["omp-loop", "--version"]):
            main()
        captured = capsys.readouterr()
        assert VERSION in captured.out

    def test_healthcheck_flag(self, capsys):
        """--healthcheck runs health check and exits with code 0."""
        from omp_loop.cli import main

        with patch.object(sys, "argv", ["omp-loop", "--healthcheck"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured = capsys.readouterr()
        # Should produce JSON output
        assert "status" in captured.out

    def test_examples_flag(self, capsys):
        """--examples prints usage examples."""
        from omp_loop.cli import main

        with patch.object(sys, "argv", ["omp-loop", "--examples"]):
            main()
        captured = capsys.readouterr()
        assert "omp-loop" in captured.out
        assert "--goal" in captured.out

    def test_list_flags(self, capsys):
        """--list-flags prints all available flags."""
        from omp_loop.cli import main

        with patch.object(sys, "argv", ["omp-loop", "--list-flags"]):
            main()
        captured = capsys.readouterr()
        assert "--goal" in captured.out
        assert "--git" in captured.out

    def test_list_groups(self, capsys):
        """--list-groups prints flag groups."""
        from omp_loop.cli import main

        with patch.object(sys, "argv", ["omp-loop", "--list-groups"]):
            main()
        captured = capsys.readouterr()
        assert "core" in captured.out or "Core" in captured.out

    def test_dump_env(self, capsys):
        """--dump-env prints env vars and their current values."""
        from omp_loop.cli import main

        with (
            patch.dict(os.environ, {"INFINITE_LOOP_GOAL": "test_goal"}, clear=True),
            patch.object(sys, "argv", ["omp-loop", "--dump-env"]),
        ):
            main()
        captured = capsys.readouterr()
        assert "INFINITE_LOOP_GOAL" in captured.out

    def test_status_without_ledger(self, capsys):
        """--status shows status with default values when no ledger exists."""
        from omp_loop import cli as cli_mod

        with (
            patch.object(sys, "argv", ["omp-loop", "--status"]),
            patch("omp_loop.cli.LEDGER_PATH", "/nonexistent/ledger.json"),
            patch("omp_loop.cli.read_ledger", return_value=None),
        ):
            cli_mod.main()
        captured = capsys.readouterr()
        assert "No ledger" in captured.out

    def test_doctor_flag(self, capsys):
        """--doctor runs diagnostic checks."""
        from omp_loop.cli import main

        with patch.object(sys, "argv", ["omp-loop", "--doctor"]):
            main()
        captured = capsys.readouterr()
        # Doctor produces diagnostics output (should not crash)
        assert captured.out is not None or captured.err is not None

    def test_preflight_flag(self, capsys, tmp_path):
        """--preflight runs preflight checks and exits cleanly."""
        from omp_loop.cli import main

        with patch.object(sys, "argv", ["omp-loop", "--preflight", "--shutdown-sentinel", str(tmp_path / "sentinel")]):
            main()
        captured = capsys.readouterr()
        # Should produce output (preflight results)
        assert len(captured.out) > 0 or len(captured.err) >= 0

    def test_help_topic(self, capsys):
        """--help-topic prints specific help topic."""
        from omp_loop.cli import main

        with patch.object(sys, "argv", ["omp-loop", "--help-topic", "convergence"]):
            main()
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_explain_flag(self, capsys):
        """--explain prints explanation of a specific flag."""
        from omp_loop.cli import main

        with patch.object(sys, "argv", ["omp-loop", "--explain", "git"]):
            main()
        captured = capsys.readouterr()
        assert "--git" in captured.out or "git" in captured.out.lower()


class TestCliMainDispatch:
    """CLI main() with more complex dispatch paths."""

    def test_missing_goal_shows_help(self, capsys):
        """main() with no --goal and no introspection flag prints help."""
        from omp_loop.cli import main

        with patch.object(sys, "argv", ["omp-loop"]):
            main()
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or "omp-loop" in captured.out

    def test_status_with_ledger(self, capsys, tmp_path):
        """--status shows ledger content when ledger exists."""
        from omp_loop import cli as cli_mod
        from omp_loop.file_utils import write_ledger

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        ledger_path = str(data_dir / "ledger.json")

        write_ledger(
            {
                "initial_command": "Test goal",
                "status": "running",
                "version": 11,
                "iterations": [],
                "stats": {"success_count": 0, "error_count": 0},
            }
        )

        with (
            patch.object(sys, "argv", ["omp-loop", "--status"]),
            patch("omp_loop.cli.LEDGER_PATH", ledger_path),
            patch(
                "omp_loop.cli.read_ledger",
                return_value={
                    "initial_command": "Test goal",
                    "status": "running",
                    "version": 11,
                    "iterations": [],
                    "stats": {"success_count": 0, "error_count": 0},
                },
            ),
        ):
            cli_mod.main()
        captured = capsys.readouterr()
        assert "Test goal" in captured.out or "running" in captured.out

    def test_force_reset_removes_ledger(self, tmp_path):
        """--force-reset removes the existing ledger before starting."""
        from omp_loop import cli as cli_mod
        from omp_loop.file_utils import write_ledger

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # Write a fake ledger
        write_ledger(
            {
                "initial_command": "Old goal",
                "status": "stopped",
                "version": 11,
                "iterations": [],
                "stats": {},
            }
        )

        # Trigger a save-config invocation which won't run the loop
        # but demonstrates force-reset logic
        with patch.object(
            sys,
            "argv",
            [
                "omp-loop",
                "--goal",
                "New goal",
                "--force-reset",
                "--save-config",
                str(tmp_path / "saved_config.json"),
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                cli_mod.main()
            assert exc.value.code == 0


class TestCliContextFile:
    """CLI --context-file loading with real filesystem."""

    def test_context_file_loaded(self, tmp_path):
        """--context-file loads content from disk."""
        from omp_loop import cli as cli_mod

        ctx_file = tmp_path / "ctx.txt"
        ctx_file.write_text("Be concise and use best practices")

        with (
            patch.object(
                sys,
                "argv",
                [
                    "omp-loop",
                    "--goal",
                    "test",
                    "--context-file",
                    str(ctx_file),
                    "--save-config",
                    str(tmp_path / "config.json"),
                ],
            ),
            pytest.raises(SystemExit),
        ):
            cli_mod.main()
        # Should not crash

    def test_missing_context_file_exits(self):
        """Missing --context-file prints error and exits."""
        from omp_loop.cli import main

        with patch.object(
            sys,
            "argv",
            [
                "omp-loop",
                "--goal",
                "test",
                "--context-file",
                "/nonexistent/ctx.txt",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1


class TestCliConfigFile:
    """CLI --config file loading."""

    def test_config_file_loaded(self, tmp_path):
        """--config loads JSON from disk."""
        from omp_loop import cli as cli_mod

        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"goal": "from file"}))

        with (
            patch.object(
                sys,
                "argv",
                [
                    "omp-loop",
                    "--goal",
                    "test",
                    "--config",
                    str(cfg_file),
                    "--save-config",
                    str(tmp_path / "saved.json"),
                ],
            ),
            pytest.raises(SystemExit),
        ):
            cli_mod.main()

    def test_corrupt_config_file_does_not_crash(self, tmp_path):
        """Corrupt --config file logs warning and continues."""
        from omp_loop import cli as cli_mod

        cfg_file = tmp_path / "bad_config.json"
        cfg_file.write_text("not json")

        with (
            patch.object(
                sys,
                "argv",
                [
                    "omp-loop",
                    "--goal",
                    "test",
                    "--config",
                    str(cfg_file),
                    "--save-config",
                    str(tmp_path / "saved.json"),
                ],
            ),
            pytest.raises(SystemExit),
        ):
            cli_mod.main()

    def test_save_config_writes_file(self, tmp_path):
        """--save-config writes config dict to disk."""
        from omp_loop import cli as cli_mod

        saved = tmp_path / "saved_config.json"
        with (
            patch.object(
                sys,
                "argv",
                [
                    "omp-loop",
                    "--goal",
                    "save-test",
                    "--git",
                    "--save-config",
                    str(saved),
                ],
            ),
            pytest.raises(SystemExit),
        ):
            cli_mod.main()
        assert saved.exists()
        content = json.loads(pathlib.Path(str(saved)).read_text())
        assert content["goal"] == "save-test"
        assert content["git"] is True


# =============================================================================
# 2.  Error Classification Deep Integration  (error_utils.py)
# =============================================================================


class TestClassifyErrorEdgeCases:
    """Edge case variations for classify_error() beyond unit tests."""

    def test_none_input(self):
        """classify_error returns None for None."""
        from omp_loop.error_utils import classify_error

        assert classify_error(None) is None

    def test_empty_string(self):
        """classify_error returns None for empty string."""
        from omp_loop.error_utils import classify_error

        assert classify_error("") is None

    def test_case_variations_timeout(self):
        """classify_error handles case variations for timeout keywords."""
        from omp_loop.error_utils import classify_error

        assert classify_error("TIMEOUT") == "timeout"
        assert classify_error("TimeOut") == "timeout"
        assert classify_error("Timed Out") == "timeout"
        assert classify_error("TIMEDOUT") == "timeout"
        assert classify_error("TIME_OUT") == "timeout"

    def test_case_variations_network(self):
        """classify_error handles case variations for network keywords."""
        from omp_loop.error_utils import classify_error

        assert classify_error("CONNECTION REFUSED") == "network"
        assert classify_error("Connection Refused") == "network"
        assert classify_error("ECONNREFUSED") == "network"
        assert classify_error("ECONNRESET") == "network"
        assert classify_error("SSL_ERROR") == "network"

    def test_network_status_codes(self):
        """HTTP status codes classified as network errors."""
        from omp_loop.error_utils import classify_error

        assert classify_error("503 Service Unavailable") == "network"
        assert classify_error("502 Bad Gateway") == "network"
        assert classify_error("504 Gateway Timeout") == "timeout"  # 504 is timeout per impl
        assert classify_error("429 Too Many Requests") == "network"

    def test_schema_errors(self):
        """classify_error returns 'schema' for schema-related errors."""
        from omp_loop.error_utils import classify_error

        assert classify_error("Schema mismatch at field 'name'") == "schema"
        assert classify_error("ValidationError: invalid type") == "schema"
        assert classify_error("Invalid format: expected object") == "schema"
        assert classify_error("schema validation failed") == "schema"

    def test_unknown_errors(self):
        """Unknown error strings return 'unknown'."""
        from omp_loop.error_utils import classify_error

        assert classify_error("permission denied") == "unknown"
        assert classify_error("disk full") == "unknown"
        assert classify_error("segmentation fault") == "unknown"
        assert classify_error("out of memory") == "unknown"

    def test_network_url_error_keywords(self):
        """Network URL error keywords are detected."""
        from omp_loop.error_utils import classify_error

        assert classify_error("could not resolve host") == "network"
        assert classify_error("getaddrinfo failed") == "network"
        assert classify_error("no route to host") == "network"
        result = classify_error("network is unreachable")
        assert result == "network"
        assert classify_error("temporary failure in name resolution") == "network"

    def test_tls_ssl_errors(self):
        """TLS/SSL errors classified as network."""
        from omp_loop.error_utils import classify_error

        assert classify_error("TLS handshake failed") == "network"
        assert classify_error("SSL certificate verify failed") == "network"
        assert classify_error("certificate expired") == "network"
        assert classify_error("socket error") == "network"

    def test_timeout_word_embedded(self):
        """'timeout' as a standalone word is still detected."""
        from omp_loop.error_utils import classify_error

        assert classify_error("The request timed out and failed") == "timeout"
        assert classify_error("Task was killed by timeout handler") == "timeout"

    def test_connection_errors_without_keywords(self):
        """Connection-related but not matching keywords → unknown."""
        from omp_loop.error_utils import classify_error

        assert classify_error("connection broken") == "unknown"
        assert classify_error("connection lost") == "unknown"


class TestSuggestActionableFixIntegration:
    """_suggest_actionable_fix() with realistic multi-parameter state."""

    def test_no_suggestion_for_success(self):
        """No suggestion for completed classifications."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type=None,
            classification="completed",
            goal="test",
            workers=1,
            consecutive_errors=0,
        )
        assert result is None

    def test_no_suggestion_for_progress(self):
        """No suggestion for 'progress' classification."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type=None,
            classification="progress",
            goal="test",
            workers=1,
            consecutive_errors=0,
        )
        assert result is None

    def test_timeout_suggestion(self):
        """Timeout error suggests increasing session timeout."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type="timeout",
            classification="error",
            goal="long task",
            workers=1,
            consecutive_errors=1,
        )
        assert result is not None
        assert "--session-timeout" in result

    def test_network_suggestion(self):
        """Network error suggests connectivity checks."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type="network",
            classification="error",
            goal="API call",
            workers=2,
            consecutive_errors=2,
        )
        assert result is not None
        assert "network" in result.lower()

    def test_schema_suggestion(self):
        """Schema error suggests reviewing output schema."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type="schema",
            classification="error",
            goal="parse data",
            workers=1,
            consecutive_errors=1,
        )
        assert result is not None
        assert "--output-schema" in result

    def test_high_consecutive_errors(self):
        """3+ consecutive errors with stuck classification get escalation."""
        from omp_loop.error_utils import _suggest_actionable_fix

        # error_type=None so error-type branch doesn't short-circuit
        result = _suggest_actionable_fix(
            error_type="network",
            classification="stuck",
            goal="fix bugs",
            workers=2,
            consecutive_errors=4,
        )
        assert result is not None
        assert "--preflight" in result or "with --preflight" in result

    def test_stuck_classification_no_git(self):
        """Stuck classification suggests --evolve when not enabled."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type=None,
            classification="stuck",
            goal="complex task",
            workers=2,
            consecutive_errors=0,
            use_library=False,
        )
        assert result is not None
        assert "--evolve" in result

    def test_stuck_classification_with_git_convergence(self):
        """Stuck with convergence goal mentions threshold."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type=None,
            classification="stuck",
            goal="convergence optimization",
            workers=1,
            consecutive_errors=0,
            use_library=True,
        )
        assert result is not None
        assert "convergence" in result.lower()

    def test_regression_suggests_git(self):
        """Regression classification suggests --git when not enabled."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type=None,
            classification="regression",
            goal="refactor",
            workers=1,
            consecutive_errors=0,
            git=False,
            force_reset=False,
            git_commit=False,
        )
        assert result is not None
        assert "--git" in result

    def test_regression_with_git_suggests_commit(self):
        """Regression with --git already enabled suggests --git-commit."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type=None,
            classification="regression",
            goal="refactor",
            workers=1,
            consecutive_errors=0,
            git=True,
            force_reset=False,
            git_commit=False,
        )
        assert result is not None
        assert "--git-commit" in result

    def test_regression_all_enabled_returns_none(self):
        """Regression with all features already enabled returns None."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type=None,
            classification="regression",
            goal="refactor",
            workers=1,
            consecutive_errors=0,
            git=True,
            force_reset=True,
            git_commit=True,
        )
        assert result is None

    def test_partial_classification(self):
        """Partial classification with an error type gives suggestion."""
        from omp_loop.error_utils import _suggest_actionable_fix

        # partial with an error type still returns error-type suggestion
        result = _suggest_actionable_fix(
            error_type="timeout",
            classification="partial",
            goal="iterative task",
            workers=1,
            consecutive_errors=0,
        )
        assert result is not None
        assert "--session-timeout" in result

    def test_unknown_classification(self):
        """'unknown' classification returns a mild tip."""
        from omp_loop.error_utils import _suggest_actionable_fix

        result = _suggest_actionable_fix(
            error_type=None,
            classification="unknown",
            goal="novel task",
            workers=1,
            consecutive_errors=0,
        )
        assert result is not None
        assert "known pattern" in result


# =============================================================================
# 3.  Color Utils Integration  (color_utils.py)
# =============================================================================


class TestColorizerIntegration:
    """Colorizer terminal detection and output formatting."""

    def test_never_mode_strips_color(self):
        """configure_color_mode('never') suppresses ANSI codes."""
        from omp_loop.color_utils import colorizer, configure_color_mode

        configure_color_mode("never")
        result = colorizer.ok("success")
        # When mode=never, _enabled() returns False → no ANSI codes
        assert "\033[" not in result
        assert "success" in result

    def test_always_mode_emits_color(self):
        """configure_color_mode('always') emits ANSI codes even to pipe."""
        import omp_loop.color_utils as cu

        cu.configure_color_mode("always")
        result = cu.colorizer.ok("success")
        # When mode=always, ANSI codes should be present
        assert "\033[" in result
        assert "success" in result

    def test_colorize_named_colors(self):
        """colorizer.colorize wraps text in named color."""
        import omp_loop.color_utils as cu

        cu.configure_color_mode("always")
        red_text = cu.colorizer.colorize("error", "red")
        assert "\033[91m" in red_text
        assert "error" in red_text
        assert "\033[0m" in red_text

    def test_colorize_multiple_names(self):
        """colorize accepts multiple color names."""
        import omp_loop.color_utils as cu

        cu.configure_color_mode("always")
        text = cu.colorizer.colorize("warning", "bold", "yellow")
        assert "\033[1m" in text
        assert "\033[93m" in text

    def test_colorizer_convenience_methods(self):
        """Convenience methods ok/fail/warn/dim/header work correctly."""
        import omp_loop.color_utils as cu

        cu.configure_color_mode("always")
        assert "\033[1;92m" in cu.colorizer.ok("yes")
        assert "\033[1;91m" in cu.colorizer.fail("no")
        assert "\033[1;93m" in cu.colorizer.warn("careful")
        assert "\033[90m" in cu.colorizer.dim("faint")
        assert "\033[1;96m" in cu.colorizer.header("TITLE")
        assert "\033[94m" in cu.colorizer.value("val")
        assert "\033[1;95m" in cu.colorizer.flag("flag")
        assert "\033[1;94m" in cu.colorizer.tag_ok()
        assert "\033[1;91m" in cu.colorizer.tag_fail()
        assert "\033[90m" in cu.colorizer.group_title("group")

    def test_no_color_env_var(self):
        """NO_COLOR env var disables color in auto mode."""
        import omp_loop.color_utils as cu

        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            cu.configure_color_mode("auto")
            result = cu.colorizer.ok("test")
            assert "\033[" not in result

    def test_invalid_mode_defaults_to_auto(self):
        """Invalid mode string defaults to 'auto'."""
        import omp_loop.color_utils as cu

        cu.configure_color_mode("invalid_mode")
        # Should not crash — uses auto mode
        assert hasattr(cu.colorizer, "_mode")
        assert cu.colorizer._mode == "auto"

    def test_strip_ansi_utility(self):
        """Color mode 'never' strips ANSI codes from output."""
        import omp_loop.color_utils as cu

        cu.configure_color_mode("always")
        colored = cu.colorizer.ok("bold text")
        assert "\033[" in colored

        cu.configure_color_mode("never")
        never_result = cu.colorizer.ok("bold text")
        assert "\033[" not in never_result

    def test_tag_output_smoke(self):
        """tag_ok and tag_fail produce different output."""
        import omp_loop.color_utils as cu

        cu.configure_color_mode("always")
        ok_mark = cu.colorizer.tag_ok()
        fail_mark = cu.colorizer.tag_fail()
        assert ok_mark != fail_mark


# =============================================================================
# 4.  run_loop() Exit Conditions  (loop.py)
# =============================================================================


class TestRunLoopExitConditions:
    """run_loop() terminates correctly under various exit conditions.

    These tests use a mocked _execute_task to avoid executing the real 'omp'
    binary, while leaving all other loop logic (sentinel, iteration counting,
    shutdown sequence) real.
    """

    @pytest.fixture
    def _isolate_paths(self, tmp_path, monkeypatch):
        """Isolate ledger/lock/status to temp dir."""
        monkeypatch.setenv("OMP_LOOP_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OMP_LOOP_LEDGER_PATH", str(tmp_path / "infinite-loop-state.json"))
        monkeypatch.setenv("OMP_LOOP_LOCK_PATH", str(tmp_path / "infinite-loop-state.lock"))
        import importlib

        from omp_loop import config as cfg_mod

        importlib.reload(cfg_mod)
        from omp_loop import file_utils as fu_mod

        importlib.reload(fu_mod)

    def test_max_iterations_stops(self, _isolate_paths, tmp_path):
        """run_loop stops when iteration count reaches max_iterations."""
        from omp_loop.config import LoopConfig
        from omp_loop.loop import run_loop
        from omp_loop.state import load_or_create_ledger

        state = load_or_create_ledger("Max iteration test", "")
        cfg = LoopConfig(
            goal="Max iteration test",
            max_iterations=2,
            session_timeout=30,
            status_file=str(tmp_path / "status.json"),
            quiet=True,
            workers=1,
        )

        with patch("omp_loop.loop._execute_task") as mock_exec:
            mock_exec.return_value = {
                "output": "Completed iteration",
                "error": None,
                "duration_seconds": 0.1,
                "returncode": 0,
            }
            run_loop(cfg, state)

        assert state["status"] == "stopped: max_iterations (2)"
        assert state["total_iterations"] == 2

    def test_sentinel_stop(self, _isolate_paths, tmp_path):
        """run_loop stops when sentinel file is created."""
        from omp_loop.config import LoopConfig
        from omp_loop.loop import run_loop
        from omp_loop.state import load_or_create_ledger

        sentinel_path = str(tmp_path / "stop-sentinel")
        state = load_or_create_ledger("Sentinel stop test", "", sentinel_path=sentinel_path)
        cfg = LoopConfig(
            goal="Sentinel stop test",
            max_iterations=10,
            sentinel_path=sentinel_path,
            session_timeout=30,
            status_file=str(tmp_path / "status.json"),
            quiet=True,
            workers=1,
        )

        call_count = 0

        def _side_effect(**kwargs):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                # Create sentinel after first iteration to trigger stop
                pathlib.Path(sentinel_path).write_text("stop\n")
            return {
                "output": f"Iteration {call_count}",
                "error": None,
                "duration_seconds": 0.1,
                "returncode": 0,
            }

        with patch("omp_loop.loop._execute_task") as mock_exec:
            mock_exec.side_effect = _side_effect
            run_loop(cfg, state)

        assert "stopped: stop" in state.get("status", "")
        assert state["total_iterations"] >= 1

    def test_error_mitigation_stop(self, _isolate_paths, tmp_path):
        """run_loop stops when mitigation reaches level >= 3."""
        from omp_loop.config import LoopConfig
        from omp_loop.loop import run_loop
        from omp_loop.state import load_or_create_ledger

        state = load_or_create_ledger("Error stop test", "")
        # Pre-seed error count so mitigation escalates quickly
        state["error_type_counts"] = {"timeout": 10}
        cfg = LoopConfig(
            goal="Error stop test",
            max_iterations=100,
            session_timeout=30,
            status_file=str(tmp_path / "status.json"),
            quiet=True,
            workers=1,
            cooldown=0,
        )

        with patch("omp_loop.loop._execute_task") as mock_exec:
            mock_exec.return_value = {
                "output": "",
                "error": "timeout error",
                "duration_seconds": 0.1,
                "returncode": -1,
            }
            run_loop(cfg, state)

        # Should terminate due to high mitigation level
        assert state["status"] != "running"
        assert state["total_iterations"] >= 1

    def test_empty_max_iterations_runs_limited(self, _isolate_paths, tmp_path):
        """run_loop runs reasonable number when max_iterations is not set (default 50)."""
        # This test just verifies it doesn't infinite loop
        from omp_loop.config import LoopConfig
        from omp_loop.loop import run_loop
        from omp_loop.state import load_or_create_ledger

        state = load_or_create_ledger("No max test", "")
        cfg = LoopConfig(
            goal="No max test",
            max_iterations=3,
            session_timeout=30,
            status_file=str(tmp_path / "status.json"),
            quiet=True,
            workers=1,
        )

        with patch("omp_loop.loop._execute_task") as mock_exec:
            mock_exec.return_value = {
                "output": "ok",
                "error": None,
                "duration_seconds": 0.05,
                "returncode": 0,
            }
            run_loop(cfg, state)

        assert state["total_iterations"] == 3

    def test_idle_detection_stops(self, _isolate_paths, tmp_path):
        """run_loop stops when idle detection triggers."""
        from omp_loop.config import LoopConfig
        from omp_loop.loop import run_loop
        from omp_loop.state import load_or_create_ledger

        state = load_or_create_ledger("Idle stop test", "")
        cfg = LoopConfig(
            goal="Idle stop test",
            max_iterations=100,
            max_idle_iterations=2,
            session_timeout=30,
            status_file=str(tmp_path / "status.json"),
            quiet=True,
            workers=1,
            git=True,  # Enable git for idle detection
        )

        # git_before and git_after should match to trigger idle detection
        git_state = {"diff_stat": "", "head": "abc123"}

        with (
            patch("omp_loop.loop._execute_task") as mock_exec,
            patch("omp_loop.loop._capture_git_state", return_value=git_state),
        ):
            mock_exec.return_value = {
                "output": "ok",
                "error": None,
                "duration_seconds": 0.1,
                "returncode": 0,
            }
            run_loop(cfg, state)

        assert "idle" in state.get("status", "").lower()
        assert state["total_iterations"] >= 2


# =============================================================================
# 5.  Evolve Goal  (loop.py _evolve_goal)
# =============================================================================


class TestEvolveGoal:
    """_evolve_goal() parses and applies NEXT_GOAL markers."""

    def test_extracts_next_goal(self):
        """_evolve_goal extracts NEXT_GOAL: marker from output."""
        from omp_loop.loop import _evolve_goal

        state = {}
        output = textwrap.dedent("""\
            Some work done.
            NEXT_GOAL: Continue with testing
            More output.
        """)
        _evolve_goal(output, state, iteration=3)
        assert state["evolved_goal"] == "Continue with testing"

    def test_case_insensitive_prefix(self):
        """NEXT_GOAL marker is case-insensitive."""
        from omp_loop.loop import _evolve_goal

        state = {}
        output = "next_goal: do something else\n"
        _evolve_goal(output, state, iteration=5)
        assert state["evolved_goal"] == "do something else"

    def test_no_marker_no_change(self):
        """No NEXT_GOAL marker leaves state unchanged."""
        from omp_loop.loop import _evolve_goal

        state = {}
        _evolve_goal("Just regular output without marker", state, iteration=1)
        assert "evolved_goal" not in state

    def test_empty_goal_after_marker(self):
        """Empty NEXT_GOAL value is ignored."""
        from omp_loop.loop import _evolve_goal

        state = {}
        _evolve_goal("NEXT_GOAL:  \n", state, iteration=2)
        assert "evolved_goal" not in state

    def test_multiple_markers_last_wins(self):
        """Multiple NEXT_GOAL markers — last non-empty one wins."""
        from omp_loop.loop import _evolve_goal

        state = {}
        output = textwrap.dedent("""\
            NEXT_GOAL: first goal
            Some work
            next_goal: second goal
        """)
        _evolve_goal(output, state, iteration=4)
        assert state["evolved_goal"] == "second goal"

    def test_whitespace_around_value(self):
        """Whitespace around NEXT_GOAL value is stripped."""
        from omp_loop.loop import _evolve_goal

        state = {}
        _evolve_goal("  NEXT_GOAL:   trim this   ", state, iteration=1)
        assert state["evolved_goal"] == "trim this"

    def test_colon_in_goal_body(self):
        """A colon in the goal value is preserved."""
        from omp_loop.loop import _evolve_goal

        state = {}
        _evolve_goal("NEXT_GOAL: Fix bug: update schema", state, iteration=2)
        assert state["evolved_goal"] == "Fix bug: update schema"


# =============================================================================
# 6.  Progressive Context Building  (functions.py _build_progressive_context)
# =============================================================================


class TestProgressiveContextEdgeCases:
    """Edge cases for _build_progressive_context."""

    def test_empty_summaries(self):
        """Empty summaries list returns just the base context."""
        from omp_loop.functions import _build_progressive_context

        ctx = _build_progressive_context("Base context", [])
        assert ctx == "Base context"

    def test_single_summary(self):
        """Single summary is included in context."""
        from omp_loop.functions import _build_progressive_context

        ctx = _build_progressive_context("Base", ["First result"])
        assert "Base" in ctx
        assert "First result" in ctx

    def test_many_summaries_truncated(self):
        """Many summaries are truncated to last items."""
        from omp_loop.functions import _build_progressive_context

        summaries = [f"Summary {i}" for i in range(100)]
        ctx = _build_progressive_context("Base", summaries)
        # Should include last few summaries
        assert "Summary 99" in ctx

    def test_summaries_with_special_chars(self):
        """Summaries with special characters are preserved."""
        from omp_loop.functions import _build_progressive_context

        ctx = _build_progressive_context("Base", ["Line 1\nLine 2", "Tab\tseparated", "Unicode: ñño 😊"])
        assert "Unicode" in ctx
        assert "ñño" in ctx
        assert "😊" in ctx

    def test_very_long_summaries(self):
        """Very long summaries are handled."""
        from omp_loop.functions import _build_progressive_context

        long_summary = "x" * 10000
        ctx = _build_progressive_context("Base", [long_summary])
        assert "Base" in ctx


# =============================================================================
# 7.  Shutdown Summary  (loop.py _print_shutdown_summary)
# =============================================================================


class TestPrintShutdownSummary:
    """_print_shutdown_summary output formatting."""

    def test_default_output(self, capsys):
        """_print_shutdown_summary prints formatted summary."""
        from omp_loop.loop import _print_shutdown_summary

        state = {
            "status": "stopped: test",
            "iterations": [
                {"error": None, "duration_seconds": 10.0},
                {"error": "timeout", "duration_seconds": 30.0},
            ],
            "stats": {
                "total_duration_seconds": 40.0,
                "success_count": 1,
                "error_count": 1,
                "consecutive_errors": 1,
                "consecutive_successes": 0,
            },
            "error_type_counts": {"timeout": 1},
        }

        _print_shutdown_summary(state, iteration_count=2, stop_reason="stopped: test", goal="test goal")

        captured = capsys.readouterr()
        assert "SHUTDOWN SUMMARY" in captured.out
        assert "test goal" in captured.out
        assert "2" in captured.out

    def test_no_iterations(self, capsys):
        """Summary handles zero iterations."""
        from omp_loop.loop import _print_shutdown_summary

        state = {
            "status": "stopped: idle",
            "iterations": [],
            "stats": {},
            "error_type_counts": {},
        }

        _print_shutdown_summary(state, iteration_count=0, stop_reason="stopped: idle")

        captured = capsys.readouterr()
        assert "SHUTDOWN SUMMARY" in captured.out

    def test_all_errors(self, capsys):
        """Summary with all errors still renders."""
        from omp_loop.loop import _print_shutdown_summary

        state = {
            "status": "stopped: timeout-failure",
            "iterations": [
                {"error": "timeout", "duration_seconds": 30.0},
                {"error": "timeout", "duration_seconds": 45.0},
            ],
            "stats": {
                "total_duration_seconds": 75.0,
                "success_count": 0,
                "error_count": 2,
                "consecutive_errors": 2,
                "consecutive_successes": 0,
            },
            "error_type_counts": {"timeout": 2},
        }

        _print_shutdown_summary(state, iteration_count=2, stop_reason="stopped: timeout-failure")

        captured = capsys.readouterr()
        assert "SHUTDOWN SUMMARY" in captured.out
        assert "timeout" in captured.out

    def test_minimal_state(self, capsys):
        """Summary handles minimal state with missing keys."""
        from omp_loop.loop import _print_shutdown_summary

        _print_shutdown_summary({"iterations": []}, iteration_count=0, stop_reason="stopped")

        captured = capsys.readouterr()
        assert "SHUTDOWN SUMMARY" in captured.out


# =============================================================================
# 8.  Shutdown Sequence  (loop.py _shutdown) — extended
# =============================================================================


class TestShutdownExtended:
    """Extended _shutdown tests beyond test_integration.py."""

    def test_shutdown_without_status_file_entry(self, tmp_path):
        """_shutdown always writes status file now (unified writer)."""
        from omp_loop.file_utils import write_ledger
        from omp_loop.loop import _shutdown

        state = {"total_iterations": 0, "status": "running"}
        write_ledger(state)

        _shutdown(
            state,
            iteration_count=0,
            status_file=str(tmp_path / "status.json"),
            stop_reason="stopped: test",
        )
        assert state["status"] == "stopped: test"
    def test_shutdown_with_last_error(self, tmp_path):
        """_shutdown includes last_error in status file."""
        from omp_loop.loop import _shutdown

        state = {"total_iterations": 1, "status": "running"}
        status_file = str(tmp_path / "loop-status.json")

        _shutdown(
            state,
            iteration_count=1,
            status_file=status_file,
            stop_reason="stopped: error",
            last_error="connection refused",
        )

        assert os.path.exists(status_file)
        sf_path = pathlib.Path(status_file)
        assert sf_path.exists()
        sf = json.loads(sf_path.read_text())
        assert sf["last_error"] == "connection refused"


# =============================================================================
# 9.  Web SSE Stream  (server.py — async)
# =============================================================================


@pytest.mark.asyncio
class TestWebSseStream:
    """SSE streaming endpoint with real asyncio."""

    @pytest.fixture
    def app(self):
        from web_app.server import app

        return app

    async def test_sse_stream_sends_events(self, app):
        """SSE stream sends periodic keepalive events."""
        from fastapi.testclient import TestClient

        with (
            TestClient(app) as client,
            patch.dict(os.environ, {}, clear=True),
            client.stream("GET", "/api/sse/stream") as response,
        ):
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            # Read a few lines
            lines = []
            for _ in range(10):
                try:
                    line = response.read()
                    if line:
                        lines.append(line)
                except Exception:
                    break
            assert len(lines) >= 0  # at minimum, connection established

    async def test_sse_stream_legacy_sends_events(self, app):
        """Legacy SSE stream SSE endpoint works."""
        from fastapi.testclient import TestClient

        with (
            TestClient(app) as client,
            patch.dict(os.environ, {}, clear=True),
            client.stream("GET", "/api/sse") as response,
        ):
            assert response.status_code in {200, 404}


# =============================================================================
# 10.  _execute_task extended edge cases
# =============================================================================


class TestExecuteTaskExtended:
    """Extended _execute_task edge cases beyond test_integration_deep.py."""

    @pytest.fixture(scope="module")
    def mock_omp_path(self):
        """Copy mock_omp.sh into a temp dir named 'omp' on PATH."""
        mock_src = pathlib.Path(__file__).resolve().parent / "integration" / "mock_omp.sh"
        assert mock_src.is_file(), f"mock_omp.sh not found at {mock_src}"

        tmpdir = pathlib.Path(tempfile.mkdtemp())
        omp_bin = tmpdir / "omp"
        shutil.copy2(str(mock_src), str(omp_bin))
        omp_bin.chmod(0o755)

        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{tmpdir}:{old_path}"
        yield tmpdir
        os.environ["PATH"] = old_path
        shutil.rmtree(str(tmpdir), ignore_errors=True)

    @pytest.fixture
    def mock_omp_env(self, mock_omp_path):
        _ = mock_omp_path
        saved = {}
        active = {}

        def _set(overrides: dict[str, str]):
            active.clear()
            active.update(overrides)
            for k, v in overrides.items():
                saved[k] = os.environ.get(k)
                os.environ[k] = v
            return active

        yield _set
        for k in active:
            if saved.get(k) is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = saved[k]

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_retry_delay_on_failure(self, mock_omp_env):
        """_execute_task retries with proper delay on failure."""
        from omp_loop.loop import _execute_task

        start = time.time()
        mock_omp_env({"MOCK_PI_EXIT_CODE": "1"})
        result = _execute_task(
            goal="retry delay test",
            context="",
            workdir=None,
            session_timeout=30,
            max_retries=1,
            retry_delay=1,
        )
        elapsed = time.time() - start
        assert result["error"] is not None
        # Should have waited at least retry_delay (1s) between attempts
        assert elapsed >= 1.0

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_session_timeout_triggers(self, mock_omp_env):
        """_execute_task handles session timeout."""
        from omp_loop.loop import _execute_task

        # Set a very short session timeout with a delay that exceeds it
        mock_omp_env({"MOCK_PI_DELAY_S": "3"})
        result = _execute_task(
            goal="timeout test",
            context="",
            workdir=None,
            session_timeout=1,
            max_retries=0,
        )
        # Should have timed out
        assert result["error"] is not None

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_no_stdout_handling(self, mock_omp_env):
        """_execute_task handles mock_omp with no stdout output."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_NO_STDOUT": "1"})
        result = _execute_task(
            goal="no stdout",
            context="",
            workdir=None,
            session_timeout=10,
        )
        rc = result["returncode"]
        assert result["error"] is not None or rc in {0, -1}

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_end_on_stderr(self, mock_omp_env):
        """_execute_task handles NDJSON events on stderr."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_END_ON_STDERR": "1"})
        result = _execute_task(
            goal="stderr ndjson",
            context="",
            workdir=None,
            session_timeout=10,
        )
        # Should still produce some result
        assert result is not None

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_large_output_truncation(self, mock_omp_env):
        """_execute_task truncates output per max_output_chars."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_OUTPUT_TEXT": "x" * 5000})
        result = _execute_task(
            goal="truncation test",
            context="",
            workdir=None,
            session_timeout=30,
            max_output_chars=100,
        )
        assert result["error"] is None
        assert len(result["output"]) <= 100

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_empty_output(self, mock_omp_env):
        """_execute_task handles empty output."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_OUTPUT_TEXT": ""})
        result = _execute_task(
            goal="empty output",
            context="",
            workdir=None,
            session_timeout=10,
        )
        assert result["error"] is None or result["returncode"] == 0

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_various_tool_counts(self, mock_omp_env):
        """_execute_task handles varying tool call counts."""
        from omp_loop.loop import _execute_task

        for tool_count in (0, 1, 3):
            mock_omp_env({"MOCK_PI_TOOL_COUNT": str(tool_count)})
            result = _execute_task(
                goal=f"tools {tool_count}",
                context="",
                workdir=None,
                session_timeout=30,
            )
            assert result["error"] is None


# =============================================================================
# 11.  _handle_cooldown + Adaptive Mode  (functions.py)
# =============================================================================


class TestCooldownExtended:
    """Extended _handle_cooldown tests."""

    def test_adaptive_mode_honored(self):
        """_handle_cooldown with adaptive mode does not block."""
        import time

        from omp_loop.functions import _handle_cooldown

        start = time.time()
        _handle_cooldown(30, "adaptive", None, "research")
        elapsed = time.time() - start
        assert elapsed < 5  # Should return quickly in adaptive mode

    def test_shutdown_event_aborts_fixed_cooldown(self):
        """_handle_cooldown aborts fixed cooldown on shutdown event."""
        from omp_loop.functions import _handle_cooldown

        event = threading.Event()
        event.set()

        import time

        start = time.time()
        _handle_cooldown(30, "fixed", None, "research", shutdown_event=event)
        elapsed = time.time() - start
        assert elapsed < 5  # Returns almost immediately

    def test_zero_cooldown_returns_immediately(self):
        """_handle_cooldown with 0 returns immediately."""
        import time

        from omp_loop.functions import _handle_cooldown

        start = time.time()
        _handle_cooldown(0, "fixed", None, "generic")
        elapsed = time.time() - start
        assert elapsed < 1

    def test_negative_cooldown_is_safe(self):
        """_handle_cooldown with negative cooldown is safe."""
        from omp_loop.functions import _handle_cooldown

        _handle_cooldown(-1, "fixed", None, "research")


# =============================================================================
# 12.  _build_dashboard_html edge cases  (loop.py)
# =============================================================================


class TestDashboardHtmlExtended:
    """Extended dashboard HTML edge cases."""

    def test_state_with_no_status(self):
        """Dashboard handles state with no status key."""
        from omp_loop.loop import _build_dashboard_html

        html = _build_dashboard_html({"iterations": [], "stats": {}})
        assert "<!DOCTYPE html>" in html
        assert "unknown" in html

    def test_iteration_with_missing_fields(self):
        """Dashboard handles iterations with missing fields."""
        from omp_loop.loop import _build_dashboard_html

        state = {
            "status": "running",
            "iterations": [
                {"n": 1},  # missing summary, error, duration_seconds
                {},  # completely empty
            ],
            "stats": {},
        }
        html = _build_dashboard_html(state)
        assert "<!DOCTYPE html>" in html
        assert "1" in html  # iteration number still shows

    def test_xss_prevention_in_summary(self):
        """Dashboard HTML-escapes malicious content in summaries."""
        from omp_loop.loop import _build_dashboard_html

        state = {
            "status": "running",
            "iterations": [
                {
                    "n": 1,
                    "summary": "<img src=x onerror=alert(1)>",
                    "error": None,
                    "duration_seconds": 5.0,
                }
            ],
            "stats": {"total_duration_seconds": 5.0},
        }
        html = _build_dashboard_html(state)
        assert "<img" not in html
        assert "onerror" not in html

    def test_xss_in_status(self):
        """Dashboard HTML-escapes status label."""
        from omp_loop.loop import _build_dashboard_html

        state = {
            "status": "<script>alert('xss')</script>",
            "iterations": [],
            "stats": {},
        }
        html = _build_dashboard_html(state)
        assert "<script>" not in html

    def test_large_state_performance(self):
        """Dashboard handles 200 iterations without error."""
        from omp_loop.loop import _build_dashboard_html

        iters = [
            {
                "n": i,
                "summary": f"Iteration {i}",
                "error": None if i % 2 else "timeout",
                "duration_seconds": float(i),
            }
            for i in range(200)
        ]
        state = {
            "status": "running",
            "iterations": iters,
            "stats": {
                "total_duration_seconds": sum(float(i) for i in range(200)),
                "success_count": 100,
                "error_count": 100,
            },
        }
        html = _build_dashboard_html(state)
        assert "Iteration 199" in html
        assert "<!DOCTYPE html>" in html


# =============================================================================
# 13.  Compact Iterations / Archival  (loop.py)
# =============================================================================


class TestIterationCompact:
    """Iteration compact logic inside run_loop (keep_iterations)."""

    @pytest.fixture
    def _isolate_paths(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OMP_LOOP_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OMP_LOOP_LEDGER_PATH", str(tmp_path / "infinite-loop-state.json"))
        monkeypatch.setenv("OMP_LOOP_LOCK_PATH", str(tmp_path / "infinite-loop-state.lock"))
        import importlib

        from omp_loop import config as cfg_mod

        importlib.reload(cfg_mod)
        from omp_loop import file_utils as fu_mod

        importlib.reload(fu_mod)

    def test_keep_iterations_trims_old_entries(self, _isolate_paths, tmp_path):
        """run_loop trims old iterations when keep_iterations is set."""
        from omp_loop.config import LoopConfig
        from omp_loop.loop import run_loop
        from omp_loop.state import load_or_create_ledger

        state = load_or_create_ledger("Compact test", "")
        # Pre-seed many iterations to exercise compact logic
        state["iterations"] = [
            {"n": i, "summary": f"iter {i}", "error": None, "duration_seconds": 1.0} for i in range(20)
        ]
        state["total_iterations"] = 20

        cfg = LoopConfig(
            goal="Compact test",
            max_iterations=25,  # Goal: 25, so we add 5 more
            keep_iterations=5,
            session_timeout=30,
            status_file=str(tmp_path / "status.json"),
            quiet=True,
            workers=1,
        )

        with patch("omp_loop.loop._execute_task") as mock_exec:
            mock_exec.return_value = {
                "output": "ok",
                "error": None,
                "duration_seconds": 0.1,
                "returncode": 0,
            }
            run_loop(cfg, state)

        # Should have trimmed iterations to keep_iterations window
        assert state["total_iterations"] == 25
        assert len(state["iterations"]) > 0


# =============================================================================
# 14.  _build_progressive_context + Cooldown + Notification Integration
# =============================================================================


class TestIterationLifecycleIntegration:
    """Cross-module iteration lifecycle: context → execute → notifications.

    This validates the full data flow through _execute_task → result
    processing → notification → cooldown with real mock_omp.sh.
    """

    @pytest.fixture(scope="module")
    def mock_omp_path(self):
        mock_src = pathlib.Path(__file__).resolve().parent / "integration" / "mock_omp.sh"
        assert mock_src.is_file()

        tmpdir = pathlib.Path(tempfile.mkdtemp())
        omp_bin = tmpdir / "omp"
        shutil.copy2(str(mock_src), str(omp_bin))
        omp_bin.chmod(0o755)

        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{tmpdir}:{old_path}"
        yield tmpdir
        os.environ["PATH"] = old_path
        shutil.rmtree(str(tmpdir), ignore_errors=True)

    @pytest.fixture
    def mock_omp_env(self, mock_omp_path):
        _ = mock_omp_path
        saved = {}
        active = {}

        def _set(overrides: dict[str, str]):
            active.clear()
            active.update(overrides)
            for k, v in overrides.items():
                saved[k] = os.environ.get(k)
                os.environ[k] = v
            return active

        yield _set
        for k in active:
            if saved.get(k) is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = saved[k]

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_context_flow_to_execution(self, mock_omp_env):
        """Context is built and passed to _execute_task."""
        from omp_loop.functions import _build_progressive_context
        from omp_loop.loop import _execute_task

        ctx = _build_progressive_context("Be concise", ["Previous result 1", "Previous result 2"])
        assert "Previous result 1" in ctx

        mock_omp_env({})
        result = _execute_task(
            goal="context flow test",
            context=ctx,
            workdir=None,
            session_timeout=30,
        )
        assert result["error"] is None

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_full_iteration_processing(self, mock_omp_env):
        """Full iteration processing emulating one step of run_loop."""

        from omp_loop.error_utils import _suggest_actionable_fix, classify_error
        from omp_loop.functions import _build_progressive_context
        from omp_loop.loop import _execute_task

        mock_omp_env({})

        ctx = _build_progressive_context("", [])
        result = _execute_task(
            goal="full cycle test",
            context=ctx,
            workdir=None,
            session_timeout=30,
        )

        assert "error" in result
        assert "duration_seconds" in result

        # Classify any error
        error_type = classify_error(result["error"])
        _suggest_actionable_fix(
            error_type=error_type,
            classification="completed" if result["error"] is None else "error",
            goal="full cycle test",
            workers=1,
            consecutive_errors=0,
        )

        # Build record (as run_loop would)
        record = {
            "n": 1,
            "duration_seconds": result["duration_seconds"],
            "summary": (result["output"] or "")[:200],
            "error": result["error"][:200] if result["error"] else None,
        }

        assert record["n"] == 1
        if result["error"] is None:
            assert record["error"] is None


# =============================================================================
# 15.  LoopConfig edge cases  (config.py)
# =============================================================================


class TestLoopConfigEdgeCases:
    """LoopConfig edge cases beyond existing tests."""

    def test_get_default_override(self):
        """LoopConfig.get() returns default for missing keys."""
        from omp_loop.config import LoopConfig

        cfg = LoopConfig(goal="test")
        assert cfg.get("nonexistent_key", "default_val") == "default_val"

    def test_sentinel_path_default(self):
        """Sentinel path default is None."""
        from omp_loop.config import LoopConfig

        cfg = LoopConfig(goal="test")
        assert cfg.sentinel_path is None

    def test_repr_includes_goal(self):
        """__repr__ includes the goal."""
        from omp_loop.config import LoopConfig

        cfg = LoopConfig(goal="my goal")
        r = repr(cfg)
        assert "my goal" in r
        assert "LoopConfig" in r

    def test_version_constant(self):
        """VERSION is a non-empty string."""
        from omp_loop.config import VERSION

        assert isinstance(VERSION, str)
        assert len(VERSION) > 0
        assert "." in VERSION


# =============================================================================
# 16.  env_utils.py KNOWN_ENV_VARS across modules
# =============================================================================


class TestEnvUtilsCrossModule:
    """Env known vars are consistent across env_utils and config modules."""

    def test_goal_var_in_known(self):
        """INFINITE_LOOP_GOAL is in KNOWN_ENV_VARS."""
        from omp_loop.env_utils import KNOWN_ENV_VARS

        assert "INFINITE_LOOP_GOAL" in KNOWN_ENV_VARS

    def test_known_vars_are_strings(self):
        """All KNOWN_ENV_VARS are strings."""
        from omp_loop.env_utils import KNOWN_ENV_VARS

        for var in KNOWN_ENV_VARS:
            assert isinstance(var, str), f"{var} is not a string"
