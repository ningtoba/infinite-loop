"""Tests for signal_handlers.py — signal handling and auto-reload functionality."""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# The module registers signal handlers at import time via signal.signal().
# We must patch signal.signal before the first import to prevent that.
_patch_sig = patch("hermes_loop.signal_handlers.signal.signal")
_patch_sig.start()

from hermes_loop.signal_handlers import (  # noqa: E402
    _build_exec_argv,
    _check_auto_reload,
    _handle_shutdown,
    _snapshot_file,
    init_auto_reload,
)

_patch_sig.stop()


# ---------------------------------------------------------------------------
# Fixtures to reset module-level mutable state between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level mutable state and env vars before each test."""
    import hermes_loop.signal_handlers as _shmod

    _shmod._shutdown_requested = False
    _shmod._shutdown_state_ref = None
    _shmod._hermes_worker_ref = None
    _shmod._startup_file_snapshots.clear()
    _shmod._startup_file_snapshots_initialized = False
    # Ensure HERMES_LOOP_NO_AUTO_RELOAD is absent by default for tests
    os.environ.pop("HERMES_LOOP_NO_AUTO_RELOAD", None)
    yield


# ===================================================================
# Module-level signal registration
# ===================================================================


class TestModuleLevelRegistration:
    """Verify signal handlers are registered at module level."""

    def test_signal_registered_for_sigterm(self):
        """signal.signal(SIGTERM, _handle_shutdown) is called."""
        import importlib

        with patch("hermes_loop.signal_handlers.signal.signal") as mock_signal:
            import hermes_loop.signal_handlers as sh

            importlib.reload(sh)

            # After reload, the mock records calls.  We can't compare
            # identity via ``is`` because reload creates a new function
            # object, but we can verify call_count and the signal constant.
            sigterm_calls = [
                c for c in mock_signal.call_args_list if c[0][0] == signal.SIGTERM
            ]
            assert len(sigterm_calls) >= 1
            assert callable(sigterm_calls[0][0][1])

    def test_signal_registered_for_sigint(self):
        """signal.signal(SIGINT, _handle_shutdown) is called."""
        import importlib

        with patch("hermes_loop.signal_handlers.signal.signal") as mock_signal:
            import hermes_loop.signal_handlers as sh

            importlib.reload(sh)

            sigint_calls = [
                c for c in mock_signal.call_args_list if c[0][0] == signal.SIGINT
            ]
            assert len(sigint_calls) >= 1
            assert callable(sigint_calls[0][0][1])

    def test_both_signals_use_same_handler(self):
        """Both SIGTERM and SIGINT use the same handler function."""
        import importlib

        with patch("hermes_loop.signal_handlers.signal.signal") as mock_signal:
            import hermes_loop.signal_handlers as sh

            importlib.reload(sh)

            calls = mock_signal.call_args_list
            sigterm_calls = [c for c in calls if c[0][0] == signal.SIGTERM]
            sigint_calls = [c for c in calls if c[0][0] == signal.SIGINT]
            assert len(sigterm_calls) >= 1
            assert len(sigint_calls) >= 1
            # Both calls should reference the same handler function
            assert sigterm_calls[0][0][1] is sigint_calls[0][0][1]


# ===================================================================
# _handle_shutdown
# ===================================================================


class TestHandleShutdownGuard:
    """Tests for the re-entrancy guard in _handle_shutdown."""

    def test_sets_shutdown_requested_flag(self):
        """Sets _shutdown_requested to True on first call."""
        import hermes_loop.signal_handlers as _shmod

        # Ensure clean starting state
        _shmod._shutdown_requested = False

        with (
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
        ):
            _handle_shutdown(signal.SIGTERM, None)
            # Check flag INSIDE the context manager while it's still set
            assert _shmod._shutdown_requested is True

    def test_double_call_returns_early(self):
        """Second call returns immediately without re-executing."""
        with patch("hermes_loop.signal_handlers._shutdown_requested", True):
            with patch("hermes_loop.signal_handlers._log") as mock_log:
                _handle_shutdown(signal.SIGTERM, None)
                assert mock_log.call_count == 0


class TestHandleShutdownLedgerWrite:
    """Tests for the state/ledger write path in _handle_shutdown."""

    def test_sigterm_writes_state_to_disk(self, tmp_path: Path):
        """SIGTERM writes state with 'stopped: SIGTERM' status to LEDGER_PATH."""
        state = {
            "status": "running",
            "iterations": [],
            "last_updated": "2024-01-01T00:00:00",
        }
        fake_ledger = os.path.join(tmp_path, "infinite-loop-state.json")

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers.LEDGER_PATH", fake_ledger),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", state),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

        assert os.path.exists(fake_ledger), "Ledger file should exist"
        with open(fake_ledger) as f:
            written = json.load(f)
        assert written["status"].startswith("stopped: SIGTERM")

    def test_sigint_writes_state_to_disk(self, tmp_path: Path):
        """SIGINT writes state with 'stopped: SIGINT' status."""
        state = {
            "status": "running",
            "iterations": [],
            "last_updated": "2024-01-01T00:00:00",
        }
        fake_ledger = os.path.join(tmp_path, "infinite-loop-state.json")

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers.LEDGER_PATH", fake_ledger),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", state),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGINT, None)

        assert os.path.exists(fake_ledger)
        with open(fake_ledger) as f:
            written = json.load(f)
        assert written["status"].startswith("stopped: SIGINT")

    def test_no_state_ref_skips_ledger_write(self):
        """When _shutdown_state_ref is None, no ledger write is attempted."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

    def test_state_write_exception_does_not_propagate(self):
        """Exception during state serialization is caught silently."""
        state = MagicMock()
        state.__getitem__.side_effect = RuntimeError("boom")

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", state),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

    def test_atomic_write_uses_tmp_then_rename(self, tmp_path: Path):
        """Writes to .sigterm.tmp file first, then renames to LEDGER_PATH."""
        state = {"status": "running", "iterations": []}
        fake_ledger = os.path.join(tmp_path, "infinite-loop-state.json")

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers.LEDGER_PATH", fake_ledger),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", state),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

        assert os.path.exists(fake_ledger)
        # The .sigterm.tmp file should NOT exist after rename
        assert not os.path.exists(fake_ledger + ".sigterm.tmp")


class TestHandleShutdownWorkerStop:
    """Tests for the worker.stop() call in _handle_shutdown."""

    def test_calls_worker_stop(self):
        """Calls worker.stop() when _hermes_worker_ref is set."""
        mock_worker = MagicMock()

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", mock_worker),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

        mock_worker.stop.assert_called_once()

    def test_worker_stop_exception_does_not_propagate(self):
        """Exception from worker.stop() is caught silently."""
        mock_worker = MagicMock()
        mock_worker.stop.side_effect = RuntimeError("worker crash")

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", mock_worker),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

    def test_no_worker_skips_stop(self):
        """When _hermes_worker_ref is None, stop() is not called."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)


class TestHandleShutdownKillPG:
    """Tests for the os.killpg process group killing path."""

    def test_killpg_called_with_sigterm(self):
        """os.killpg is called with SIGTERM first."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch(
                "hermes_loop.signal_handlers.os.getpgid", return_value=12345
            ) as mock_getpgid,
            patch("hermes_loop.signal_handlers.os.killpg") as mock_killpg,
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

        mock_getpgid.assert_called_once_with(os.getpid())
        mock_killpg.assert_any_call(12345, signal.SIGTERM)

    def test_killpg_sigkill_called_after_sleep(self):
        """os.killpg is called with SIGKILL after pkill and sleep."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=12345),
            patch("hermes_loop.signal_handlers.os.killpg") as mock_killpg,
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

        mock_killpg.assert_any_call(12345, signal.SIGKILL)

    def test_killpg_exceptions_are_caught(self):
        """ProcessLookupError/OSError/PermissionError from killpg are caught."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=12345),
            patch(
                "hermes_loop.signal_handlers.os.killpg",
                side_effect=PermissionError("no"),
            ),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)


class TestHandleShutdownPKill:
    """Tests for the pkill descendant process killing path."""

    def test_pkill_called_for_descendants(self):
        """pkill -15 -P and pkill -9 -P are called for descendant processes."""
        mock_pid = 99999

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.getpid", return_value=mock_pid),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=mock_pid),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers._subprocess.run") as mock_run,
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

        assert mock_run.call_count >= 2
        sigterm_call = call(
            ["pkill", "-15", "-P", str(mock_pid)],
            capture_output=True,
            timeout=3,
        )
        sigkill_call = call(
            ["pkill", "-9", "-P", str(mock_pid)],
            capture_output=True,
            timeout=3,
        )
        assert sigterm_call in mock_run.call_args_list
        assert sigkill_call in mock_run.call_args_list

    def test_pkill_exception_caught(self):
        """Exception from _subprocess.run during pkill is caught silently."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=123),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch(
                "hermes_loop.signal_handlers._subprocess.run",
                side_effect=RuntimeError("pkill failed"),
            ),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
        ):
            _handle_shutdown(signal.SIGTERM, None)

    def test_sleep_called_between_pkill(self):
        """time.sleep(2) is called between pkill -15 and pkill -9."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=123),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep") as mock_sleep,
        ):
            _handle_shutdown(signal.SIGTERM, None)

        assert call(2.0) in mock_sleep.call_args_list


class TestHandleShutdownSummary:
    """Tests for the shutdown summary logging path."""

    def test_shutdown_summary_logged(self):
        """Shutdown summary with colorized output is logged."""
        state = {"status": "interrupted", "iterations": [{"duration": 1}]}

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", state),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers.time.sleep"),
            patch("hermes_loop.signal_handlers._log") as mock_log,
        ):
            _handle_shutdown(signal.SIGTERM, None)

        summary_calls = [
            c for c in mock_log.call_args_list if "SHUTDOWN SUMMARY" in str(c)
        ]
        assert len(summary_calls) >= 1

    def test_summary_shows_signal_name(self):
        """Summary includes the signal name (SIGTERM or SIGINT)."""
        state = {"status": "stopped: SIGTERM", "iterations": []}

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", state),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers.time.sleep"),
            patch("hermes_loop.signal_handlers._log") as mock_log,
        ):
            _handle_shutdown(signal.SIGTERM, None)

        logged_text = " ".join(str(c) for c in mock_log.call_args_list)
        assert "SIGTERM" in logged_text

    def test_summary_shows_iteration_count(self):
        """Summary includes iteration count from state."""
        state = {"status": "stopped", "iterations": [{"i": 1}, {"i": 2}, {"i": 3}]}

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", state),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers.time.sleep"),
            patch("hermes_loop.signal_handlers._log") as mock_log,
        ):
            _handle_shutdown(signal.SIGTERM, None)

        logged_text = " ".join(str(c) for c in mock_log.call_args_list)
        assert "3" in logged_text

    def test_summary_logged_even_when_state_none(self):
        """Summary is still logged even when state is None."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers.time.sleep"),
            patch("hermes_loop.signal_handlers._log") as mock_log,
        ):
            _handle_shutdown(signal.SIGTERM, None)

        assert mock_log.call_count >= 1

    def test_exception_in_summary_does_not_propagate(self):
        """Exception during summary logging is caught and does not propagate.

        The source wraps the entire summary block in try/except Exception,
        so a failing _log call should be caught silently.
        """
        state = {"status": "interrupted", "iterations": [{"duration": 1}]}

        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", state),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers.time.sleep"),
            patch(
                "hermes_loop.signal_handlers._log",
                side_effect=[RuntimeError("log failed"), "ok"],
            ),
        ):
            # Should not raise -- the summary block catches Exception
            _handle_shutdown(signal.SIGTERM, None)

    def test_final_stop_message_logged(self):
        """Final '[STOP] SIGTERM received...' message is logged."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers.threading.Timer"),
            patch("hermes_loop.signal_handlers.time.sleep"),
            patch("hermes_loop.signal_handlers._log") as mock_log,
        ):
            _handle_shutdown(signal.SIGTERM, None)

        stop_calls = [c for c in mock_log.call_args_list if "[STOP]" in str(c[0][0])]
        assert len(stop_calls) >= 1


class TestHandleShutdownHardExit:
    """Tests for the hard-exit timer fallback."""

    def test_hard_exit_timer_started(self):
        """A 30-second threading.Timer with daemon=True is started."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
            patch("hermes_loop.signal_handlers.threading.Timer") as mock_timer,
        ):
            _handle_shutdown(signal.SIGTERM, None)

            mock_timer.assert_called_once()
            args, _ = mock_timer.call_args
            assert args[0] == 30.0
            assert callable(args[1])
            instance = mock_timer.return_value
            assert instance.daemon is True
            instance.start.assert_called_once()

    def test_hard_exit_timer_started_for_sigint(self):
        """Hard-exit timer is also started for SIGINT."""
        with (
            patch("hermes_loop.signal_handlers._shutdown_requested", False),
            patch("hermes_loop.signal_handlers._shutdown_state_ref", None),
            patch("hermes_loop.signal_handlers._hermes_worker_ref", None),
            patch("hermes_loop.signal_handlers.os.killpg"),
            patch("hermes_loop.signal_handlers.os.getpgid", return_value=999),
            patch("hermes_loop.signal_handlers._subprocess.run"),
            patch("hermes_loop.signal_handlers._log"),
            patch("hermes_loop.signal_handlers.time.sleep"),
            patch("hermes_loop.signal_handlers.threading.Timer") as mock_timer,
        ):
            _handle_shutdown(signal.SIGINT, None)

            mock_timer.assert_called_once()


# ===================================================================
# _snapshot_file
# ===================================================================


class TestSnapshotFile:
    """Tests for _snapshot_file helper."""

    def test_returns_mtime_and_size_for_existing_file(self, tmp_path: Path):
        """Returns (mtime, size) tuple for an existing file."""
        test_file = os.path.join(tmp_path, "test.py")
        with open(test_file, "w") as f:
            f.write("print('hello')")

        result = _snapshot_file(test_file)
        assert result is not None
        assert isinstance(result[0], float)  # mtime
        assert isinstance(result[1], int)  # size
        assert result[1] == len("print('hello')")

    def test_returns_none_for_missing_file(self):
        """Returns None for a non-existent file."""
        result = _snapshot_file("/nonexistent/path/to/file.py")
        assert result is None

    def test_returns_none_for_oserror(self):
        """Returns None when os.stat raises OSError."""
        with patch(
            "hermes_loop.signal_handlers.os.stat",
            side_effect=OSError("permission denied"),
        ):
            result = _snapshot_file("/some/protected/file")
            assert result is None

    def test_returns_none_for_file_not_found_error(self):
        """Returns None when os.stat raises FileNotFoundError."""
        with patch(
            "hermes_loop.signal_handlers.os.stat",
            side_effect=FileNotFoundError("not found"),
        ):
            result = _snapshot_file("/missing/file")
            assert result is None

    def test_zero_length_file(self, tmp_path: Path):
        """A zero-length file returns size 0."""
        test_file = os.path.join(tmp_path, "empty.py")
        open(test_file, "w").close()

        result = _snapshot_file(test_file)
        assert result is not None
        assert result[1] == 0

    def test_large_file(self, tmp_path: Path):
        """A large file returns correct size."""
        test_file = os.path.join(tmp_path, "large.py")
        content = "x" * 10000
        with open(test_file, "w") as f:
            f.write(content)

        result = _snapshot_file(test_file)
        assert result is not None
        assert result[1] == 10000


# ===================================================================
# _build_exec_argv
# ===================================================================


class TestBuildExecArgv:
    """Tests for _build_exec_argv helper."""

    def test_direct_invocation(self):
        """Direct invocation returns [sys.executable] + sys.argv."""
        with patch("hermes_loop.signal_handlers.sys.argv", ["launch-loop.py", "--run"]):
            result = _build_exec_argv()
            assert result == [sys.executable, "launch-loop.py", "--run"]

    def test_module_invocation(self):
        """-m invocation returns [sys.executable, '-m'] + rest of sys.argv[1:]."""
        with patch(
            "hermes_loop.signal_handlers.sys.argv",
            ["-m", "hermes_loop", "--run"],
        ):
            result = _build_exec_argv()
            assert result == [sys.executable, "-m", "hermes_loop", "--run"]

    def test_module_invocation_no_args(self):
        """-m invocation with no additional args."""
        with patch("hermes_loop.signal_handlers.sys.argv", ["-m", "hermes_loop"]):
            result = _build_exec_argv()
            assert result == [sys.executable, "-m", "hermes_loop"]

    def test_direct_invocation_no_args(self):
        """Direct invocation with script name only."""
        with patch("hermes_loop.signal_handlers.sys.argv", ["launch-loop.py"]):
            result = _build_exec_argv()
            assert result == [sys.executable, "launch-loop.py"]

    def test_direct_invocation_multiple_args(self):
        """Direct invocation with multiple script arguments."""
        with patch(
            "hermes_loop.signal_handlers.sys.argv",
            ["launch-loop.py", "--run", "--iterations", "5"],
        ):
            result = _build_exec_argv()
            assert result == [
                sys.executable,
                "launch-loop.py",
                "--run",
                "--iterations",
                "5",
            ]

    def test_module_invocation_multiple_args(self):
        """-m invocation with multiple arguments."""
        with patch(
            "hermes_loop.signal_handlers.sys.argv",
            ["-m", "hermes_loop", "--run", "--no-auto-reload"],
        ):
            result = _build_exec_argv()
            assert result == [
                sys.executable,
                "-m",
                "hermes_loop",
                "--run",
                "--no-auto-reload",
            ]


# ===================================================================
# init_auto_reload
# ===================================================================


class TestInitAutoReload:
    """Tests for init_auto_reload function.

    The autouse fixture ``reset_module_state`` clears
    ``_startup_file_snapshots`` and unsets ``HERMES_LOOP_NO_AUTO_RELOAD``
    before each test.
    """

    def test_snapshots_existing_files(self, tmp_path: Path):
        """Snapshots existing files in workdir."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        run_sh = os.path.join(workdir, "run.sh")
        env_file = os.path.join(workdir, ".env")

        with open(launch_loop, "w") as f:
            f.write("#!/usr/bin/env python3")
        with open(run_sh, "w") as f:
            f.write("#!/bin/bash")
        with open(env_file, "w") as f:
            f.write("API_KEY=***")
        init_auto_reload(workdir)

        import hermes_loop.signal_handlers as _sh

        assert _sh._startup_file_snapshots.get(launch_loop) is not None
        assert _sh._startup_file_snapshots.get(run_sh) is not None
        assert _sh._startup_file_snapshots.get(env_file) is not None
        assert _sh._startup_file_snapshots_initialized is True

    def test_skips_missing_files_gracefully(self, tmp_path: Path):
        """Missing files are simply not added to snapshots (no crash)."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("content")

        init_auto_reload(workdir)

        import hermes_loop.signal_handlers as _sh

        assert _sh._startup_file_snapshots.get(launch_loop) is not None
        assert os.path.join(workdir, "run.sh") not in _sh._startup_file_snapshots
        assert os.path.join(workdir, ".env") not in _sh._startup_file_snapshots
        assert _sh._startup_file_snapshots_initialized is True

    def test_disabled_via_env_var(self):
        """HERMES_LOOP_NO_AUTO_RELOAD=1 skips snapshotting."""
        with patch.dict(os.environ, {"HERMES_LOOP_NO_AUTO_RELOAD": "1"}):
            init_auto_reload("/some/workdir")

            import hermes_loop.signal_handlers as _sh

            assert _sh._startup_file_snapshots == {}
            assert _sh._startup_file_snapshots_initialized is True

    def test_logs_disabled_message(self):
        """Logs a message when auto-reload is disabled via env var."""
        with patch.dict(os.environ, {"HERMES_LOOP_NO_AUTO_RELOAD": "1"}):
            with patch("hermes_loop.signal_handlers._log") as mock_log:
                init_auto_reload("/some/workdir")
                mock_log.assert_called_once_with(
                    "[AUTO-RELOAD] Disabled via "
                    "HERMES_LOOP_NO_AUTO_RELOAD (web UI mode)"
                )

    def test_none_workdir_skips(self):
        """None workdir returns early without snapshotting."""
        init_auto_reload(None)

        import hermes_loop.signal_handlers as _sh

        assert _sh._startup_file_snapshots == {}
        assert _sh._startup_file_snapshots_initialized is False

    def test_empty_workdir_skips(self):
        """Empty string workdir returns early without snapshotting."""
        init_auto_reload("")

        import hermes_loop.signal_handlers as _sh

        assert _sh._startup_file_snapshots == {}
        assert _sh._startup_file_snapshots_initialized is False

    def test_logs_file_watching_message(self, tmp_path: Path):
        """Logs 'Watching N file(s) for changes' when snapshots exist."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("content")

        with patch("hermes_loop.signal_handlers._log") as mock_log:
            init_auto_reload(workdir)
            mock_log.assert_called_once_with(
                "[AUTO-RELOAD] Watching 1 file(s) for changes"
            )

    def test_no_log_when_no_files_exist(self, tmp_path: Path):
        """No log message when no files exist to watch."""
        workdir = str(tmp_path)

        with patch("hermes_loop.signal_handlers._log") as mock_log:
            init_auto_reload(workdir)
            watching_calls = [
                c for c in mock_log.call_args_list if "Watching" in str(c[0][0])
            ]
            assert len(watching_calls) == 0

    def test_initialized_flag_set_even_with_no_files(self, tmp_path: Path):
        """_startup_file_snapshots_initialized is set even with no files to watch."""
        workdir = str(tmp_path)

        init_auto_reload(workdir)

        import hermes_loop.signal_handlers as _sh

        assert _sh._startup_file_snapshots_initialized is True


# ===================================================================
# _check_auto_reload
# ===================================================================


class TestCheckAutoReload:
    """Tests for _check_auto_reload function."""

    def test_no_changes_returns_early(self, tmp_path: Path):
        """When no files have changed, returns without execv."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("content")

        init_auto_reload(workdir)
        state = {"status": "running"}

        with patch("hermes_loop.signal_handlers.os.execv") as mock_execv:
            _check_auto_reload(
                workdir=workdir,
                state=state,
                worker_manager=None,
                status_file="",
                iteration_count=0,
            )
            mock_execv.assert_not_called()

    def test_file_changed_triggers_execv(self, tmp_path: Path):
        """When a file changes, os.execv is called with correct args."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("original")

        init_auto_reload(workdir)

        with open(launch_loop, "w") as f:
            f.write("modified content")

        state = {"status": "running", "last_updated": "2024-01-01T00:00:00"}

        with (
            patch("hermes_loop.signal_handlers.os.execv") as mock_execv,
            patch("hermes_loop.signal_handlers.os.getpid", return_value=12345),
            patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "-m", "hermes_loop"],
            ),
        ):
            _check_auto_reload(
                workdir=workdir,
                state=state,
                worker_manager=None,
                status_file="",
                iteration_count=0,
            )
            mock_execv.assert_called_once_with(
                sys.executable, [sys.executable, "-m", "hermes_loop"]
            )

    def test_env_file_change_triggers_reload(self, tmp_path: Path):
        """Change in .env file triggers os.execv."""
        workdir = str(tmp_path)
        env_file = os.path.join(workdir, ".env")
        with open(env_file, "w") as f:
            f.write("KEY=old")

        init_auto_reload(workdir)

        with open(env_file, "w") as f:
            f.write("KEY=new")

        state = {"status": "running"}

        with patch("hermes_loop.signal_handlers.os.execv") as mock_execv:
            with patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "launch-loop.py"],
            ):
                _check_auto_reload(
                    workdir=workdir,
                    state=state,
                    worker_manager=None,
                    status_file="",
                    iteration_count=0,
                )
                mock_execv.assert_called_once()

    def test_run_sh_change_triggers_reload(self, tmp_path: Path):
        """Change in run.sh triggers os.execv."""
        workdir = str(tmp_path)
        run_sh = os.path.join(workdir, "run.sh")
        with open(run_sh, "w") as f:
            f.write("old script")

        init_auto_reload(workdir)

        with open(run_sh, "w") as f:
            f.write("new script")

        state = {"status": "running"}

        with patch("hermes_loop.signal_handlers.os.execv") as mock_execv:
            with patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "launch-loop.py"],
            ):
                _check_auto_reload(
                    workdir=workdir,
                    state=state,
                    worker_manager=None,
                    status_file="",
                    iteration_count=0,
                )
                mock_execv.assert_called_once()

    def test_disabled_via_env_var(self, tmp_path: Path):
        """HERMES_LOOP_NO_AUTO_RELOAD=1 skips checking entirely."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("content")

        init_auto_reload(workdir)

        with open(launch_loop, "w") as f:
            f.write("modified")

        state = {"status": "running"}

        with patch.dict(os.environ, {"HERMES_LOOP_NO_AUTO_RELOAD": "1"}):
            with patch("hermes_loop.signal_handlers.os.execv") as mock_execv:
                _check_auto_reload(
                    workdir=workdir,
                    state=state,
                    worker_manager=None,
                    status_file="",
                    iteration_count=0,
                )
                mock_execv.assert_not_called()

    def test_empty_snapshots_skips(self):
        """When _startup_file_snapshots is empty, returns early."""
        with patch("hermes_loop.signal_handlers._startup_file_snapshots", {}):
            with patch("hermes_loop.signal_handlers.os.execv") as mock_execv:
                _check_auto_reload(
                    workdir="/some/workdir",
                    state={},
                    worker_manager=None,
                    status_file="",
                    iteration_count=0,
                )
                mock_execv.assert_not_called()

    def test_none_workdir_skips(self):
        """When workdir is None, returns early."""
        with patch(
            "hermes_loop.signal_handlers._startup_file_snapshots",
            {"/some/file": (100.0, 10)},
        ):
            with patch("hermes_loop.signal_handlers.os.execv") as mock_execv:
                _check_auto_reload(
                    workdir=None,
                    state={},
                    worker_manager=None,
                    status_file="",
                    iteration_count=0,
                )
                mock_execv.assert_not_called()

    def test_sets_state_status_to_reloading(self, tmp_path: Path):
        """State['status'] is set to 'reloading' when changes detected."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("original")

        init_auto_reload(workdir)

        with open(launch_loop, "w") as f:
            f.write("modified")

        state = {"status": "running", "iterations": []}

        with (
            patch("hermes_loop.signal_handlers.os.execv"),
            patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "script.py"],
            ),
        ):
            _check_auto_reload(
                workdir=workdir,
                state=state,
                worker_manager=None,
                status_file="",
                iteration_count=0,
            )

        assert state["status"] == "reloading"

    def test_calls_write_ledger_and_write_status_file(self, tmp_path: Path):
        """write_ledger and write_status_file are called on change."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("original")

        init_auto_reload(workdir)

        with open(launch_loop, "w") as f:
            f.write("modified")

        state = {"status": "running", "iterations": []}
        status_file = os.path.join(tmp_path, "status.json")

        with (
            patch("hermes_loop.signal_handlers.os.execv"),
            patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "script.py"],
            ),
            patch("hermes_loop.signal_handlers.write_ledger") as mock_write_ledger,
            patch("hermes_loop.signal_handlers.write_status_file") as mock_write_status,
        ):
            _check_auto_reload(
                workdir=workdir,
                state=state,
                worker_manager=None,
                status_file=status_file,
                iteration_count=0,
            )

            mock_write_ledger.assert_called_once_with(state)
            mock_write_status.assert_called_once_with(
                status_file, state, 0, "reloading"
            )

    def test_calls_worker_manager_stop(self, tmp_path: Path):
        """worker_manager.stop() is called when worker_manager is provided."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("original")

        init_auto_reload(workdir)

        with open(launch_loop, "w") as f:
            f.write("modified")

        mock_worker_manager = MagicMock()
        state = {"status": "running", "iterations": []}

        with (
            patch("hermes_loop.signal_handlers.os.execv"),
            patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "script.py"],
            ),
            patch("hermes_loop.signal_handlers.write_ledger"),
            patch("hermes_loop.signal_handlers.write_status_file"),
        ):
            _check_auto_reload(
                workdir=workdir,
                state=state,
                worker_manager=mock_worker_manager,
                status_file="",
                iteration_count=0,
            )

            mock_worker_manager.stop.assert_called_once()

    def test_worker_manager_stop_exception_caught(self, tmp_path: Path):
        """Exception from worker_manager.stop() is caught silently."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("original")

        init_auto_reload(workdir)

        with open(launch_loop, "w") as f:
            f.write("modified")

        mock_worker_manager = MagicMock()
        mock_worker_manager.stop.side_effect = RuntimeError("stop failed")
        state = {"status": "running", "iterations": []}

        with (
            patch("hermes_loop.signal_handlers.os.execv"),
            patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "script.py"],
            ),
            patch("hermes_loop.signal_handlers.write_ledger"),
            patch("hermes_loop.signal_handlers.write_status_file"),
        ):
            _check_auto_reload(
                workdir=workdir,
                state=state,
                worker_manager=mock_worker_manager,
                status_file="",
                iteration_count=0,
            )

    def test_logs_changed_files(self, tmp_path: Path):
        """Logs the names of changed files."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("original")

        init_auto_reload(workdir)

        with open(launch_loop, "w") as f:
            f.write("modified")

        state = {"status": "running", "iterations": []}

        with (
            patch("hermes_loop.signal_handlers.os.execv"),
            patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "script.py"],
            ),
            patch("hermes_loop.signal_handlers._log") as mock_log,
            patch("hermes_loop.signal_handlers.write_ledger"),
            patch("hermes_loop.signal_handlers.write_status_file"),
        ):
            _check_auto_reload(
                workdir=workdir,
                state=state,
                worker_manager=None,
                status_file="",
                iteration_count=0,
            )

            mock_log.assert_any_call(
                "[AUTO-RELOAD] Detected changes in: launch-loop.py. "
                "Restarting daemon..."
            )

    def test_multiple_files_changed(self, tmp_path: Path):
        """Multiple changed files are listed in the log message."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        env_file = os.path.join(workdir, ".env")
        with open(launch_loop, "w") as f:
            f.write("original")
        with open(env_file, "w") as f:
            f.write("KEY=old")

        init_auto_reload(workdir)

        with open(launch_loop, "w") as f:
            f.write("modified")
        with open(env_file, "w") as f:
            f.write("KEY=new")

        state = {"status": "running", "iterations": []}

        with (
            patch("hermes_loop.signal_handlers.os.execv"),
            patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "script.py"],
            ),
            patch("hermes_loop.signal_handlers._log") as mock_log,
            patch("hermes_loop.signal_handlers.write_ledger"),
            patch("hermes_loop.signal_handlers.write_status_file"),
        ):
            _check_auto_reload(
                workdir=workdir,
                state=state,
                worker_manager=None,
                status_file="",
                iteration_count=0,
            )

            log_text = " ".join(str(c) for c in mock_log.call_args_list)
            assert "launch-loop.py" in log_text
            assert ".env" in log_text

    def test_last_updated_is_set(self, tmp_path: Path):
        """state['last_updated'] is set to an ISO-format timestamp."""
        workdir = str(tmp_path)
        launch_loop = os.path.join(workdir, "launch-loop.py")
        with open(launch_loop, "w") as f:
            f.write("original")

        init_auto_reload(workdir)

        with open(launch_loop, "w") as f:
            f.write("modified")

        state = {"status": "running", "last_updated": "old"}

        with (
            patch("hermes_loop.signal_handlers.os.execv"),
            patch(
                "hermes_loop.signal_handlers._build_exec_argv",
                return_value=[sys.executable, "script.py"],
            ),
            patch("hermes_loop.signal_handlers.write_ledger"),
            patch("hermes_loop.signal_handlers.write_status_file"),
        ):
            _check_auto_reload(
                workdir=workdir,
                state=state,
                worker_manager=None,
                status_file="",
                iteration_count=0,
            )

        assert "last_updated" in state
        assert "T" in str(state["last_updated"])
