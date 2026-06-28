"""Tests for worker_manager.py — HermesWorkerManager lifecycle."""

from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import MagicMock, patch


from hermes_loop.worker_manager import HermesWorkerManager

# ===================================================================
# HermesWorkerManager tests
# ===================================================================


class TestHermesWorkerManagerInit:
    """Tests for __init__ — default state."""

    def test_default_state(self):
        """New manager has no process and port 0."""
        manager = HermesWorkerManager()
        assert manager._process is None
        assert manager._port == 0
        assert manager.is_running is False

    def test_worker_script_path_constant(self):
        """WORKER_SCRIPT points to the expected location."""
        expected = os.path.expanduser("~/.hermes/plugins/hermes-mcp-worker/main.py")
        assert HermesWorkerManager.WORKER_SCRIPT == expected


class TestHermesWorkerManagerStart:
    """Tests for start() — worker subprocess lifecycle."""

    def test_script_missing_returns_empty_string(self):
        """When WORKER_SCRIPT does not exist, start returns ''."""
        with patch.object(
            HermesWorkerManager, "WORKER_SCRIPT", "/nonexistent/worker.py"
        ):
            with patch("hermes_loop.worker_manager._log") as mock_log:
                manager = HermesWorkerManager()
                result = manager.start()

        assert result == ""
        assert manager._process is None
        mock_log.assert_called_once()
        assert "Script not found" in mock_log.call_args[0][0]

    def test_start_success_health_check_passes(self):
        """Subprocess starts and health check returns 200 — returns URL."""
        # Patch all dependencies — note: socket is imported inside start() so
        # we patch the top-level 'socket.socket', not the module attribute.
        with (
            patch("hermes_loop.worker_manager.os.path.isfile", return_value=True),
            patch("hermes_loop.worker_manager.subprocess.Popen") as mock_popen,
            patch("hermes_loop.worker_manager.urllib.request.urlopen") as mock_urlopen,
            patch("hermes_loop.worker_manager._log") as mock_log,
            patch("socket.socket") as mock_socket_cls,
        ):
            # Mock socket instance
            mock_sock = MagicMock()
            mock_sock.getsockname.return_value = ("0.0.0.0", 12345)
            mock_socket_cls.return_value.__enter__.return_value = mock_sock
            mock_socket_cls.return_value.__exit__.return_value = None

            # Mock Popen — use a simple MagicMock, not spec=subprocess.Popen,
            # since Popen itself is patched
            mock_process = MagicMock()
            mock_process.pid = 9999
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            # Mock health check response
            mock_response = MagicMock()
            mock_response.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_response

            manager = HermesWorkerManager()
            result = manager.start()

        assert result == "http://127.0.0.1:12345"
        assert manager._port == 12345
        assert manager._process is not None
        mock_popen.assert_called_once()
        # Verify Popen args
        args, kwargs = mock_popen.call_args
        assert args[0][0] == sys.executable
        assert "--port" in args[0]
        assert "--host" in args[0]
        assert kwargs.get("stdout") == subprocess.DEVNULL
        assert kwargs.get("stderr") == subprocess.DEVNULL
        # Verify health check was called
        mock_urlopen.assert_called_once()
        health_url = mock_urlopen.call_args[0][0]
        assert "/health" in str(health_url)
        # Verify logging
        mock_log.assert_any_call(
            "[WORKER] Started on http://127.0.0.1:12345 (PID=9999)"
        )

    def test_start_health_check_fails_returns_empty(self):
        """Subprocess starts but health check never returns 200 — returns '' and stops process."""
        with (
            patch("hermes_loop.worker_manager.os.path.isfile", return_value=True),
            patch("hermes_loop.worker_manager.subprocess.Popen") as mock_popen,
            patch("hermes_loop.worker_manager.urllib.request.urlopen") as mock_urlopen,
            patch("hermes_loop.worker_manager._log") as mock_log,
            patch("socket.socket") as mock_socket_cls,
        ):
            mock_sock = MagicMock()
            mock_sock.getsockname.return_value = ("0.0.0.0", 12346)
            mock_socket_cls.return_value.__enter__.return_value = mock_sock
            mock_socket_cls.return_value.__exit__.return_value = None

            # Mock Popen — use simple MagicMock
            mock_process = MagicMock()
            mock_process.pid = 8888
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            # Mock health check to always raise (connection refused)
            mock_urlopen.side_effect = OSError("Connection refused")

            manager = HermesWorkerManager()
            result = manager.start()

        assert result == ""
        # stop() should have been called, which terminates the process
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called()
        mock_log.assert_any_call(
            "[WORKER] Failed to start within 10s, falling back to direct mode"
        )

    def test_start_popen_raises_exception(self):
        """subprocess.Popen itself raises an exception — returns ''."""
        with (
            patch("hermes_loop.worker_manager.os.path.isfile", return_value=True),
            patch("hermes_loop.worker_manager.subprocess.Popen") as mock_popen,
            patch("hermes_loop.worker_manager._log") as mock_log,
            patch("socket.socket") as mock_socket_cls,
        ):
            mock_sock = MagicMock()
            mock_sock.getsockname.return_value = ("0.0.0.0", 12347)
            mock_socket_cls.return_value.__enter__.return_value = mock_sock
            mock_socket_cls.return_value.__exit__.return_value = None

            mock_popen.side_effect = FileNotFoundError("python not found")

            manager = HermesWorkerManager()
            result = manager.start()

        assert result == ""
        assert manager._process is None  # Popen never returned
        mock_log.assert_any_call("[WORKER] Failed to start: python not found")


class TestHermesWorkerManagerStop:
    """Tests for stop() — worker process termination."""

    def test_stop_no_process_is_noop(self):
        """stop() with _process=None does nothing."""
        manager = HermesWorkerManager()
        manager._process = None

        with patch("hermes_loop.worker_manager._log") as _mock_log:
            manager.stop()

        # No log messages about stopping
        assert not any("Stopping" in c[0][0] for c in _mock_log.call_args_list)

    def test_stop_process_already_terminated_is_noop(self):
        """stop() when process.poll() returns non-None (already dead) does nothing."""
        manager = HermesWorkerManager()
        mock_process = MagicMock()
        mock_process.pid = 7777
        mock_process.poll.return_value = 0  # Already terminated
        manager._process = mock_process

        with patch("hermes_loop.worker_manager._log") as _mock_log:
            manager.stop()

        # terminate should NOT be called since poll() returned non-None
        mock_process.terminate.assert_not_called()
        mock_process.wait.assert_not_called()
        # The process is NOT set to None since stop() short-circuits
        assert manager._process is mock_process

    def test_stop_terminates_running_process(self):
        """stop() terminates a running process and waits for it."""
        manager = HermesWorkerManager()
        mock_process = MagicMock()
        mock_process.pid = 6666
        mock_process.poll.return_value = None  # Still running
        manager._process = mock_process

        with patch("hermes_loop.worker_manager._log") as _mock_log:
            manager.stop()

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)
        mock_process.kill.assert_not_called()  # Normal termination, not timeout
        assert manager._process is None  # Reset after stop
        _mock_log.assert_any_call("[WORKER] Stopping worker (PID=6666)")
        _mock_log.assert_any_call("[WORKER] Stopped")

    def test_stop_terminate_timeout_then_kill(self):
        """stop() calls kill() after terminate() times out."""
        manager = HermesWorkerManager()
        mock_process = MagicMock()
        mock_process.pid = 5555
        mock_process.poll.return_value = None  # Still running
        # First wait (timeout=5) raises TimeoutExpired
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]
        manager._process = mock_process

        with patch("hermes_loop.worker_manager._log") as _mock_log:
            manager.stop()

        mock_process.terminate.assert_called_once()
        # First wait with timeout=5 raised TimeoutExpired, second wait after kill
        assert mock_process.wait.call_count == 2
        # kill() should have been called after the timeout
        mock_process.kill.assert_called_once()
        assert manager._process is None

    def test_stop_multiple_calls_safe(self):
        """Calling stop() twice is safe — second call is no-op since _process is None."""
        manager = HermesWorkerManager()
        mock_process = MagicMock()
        mock_process.pid = 4444
        mock_process.poll.return_value = None
        manager._process = mock_process

        with patch("hermes_loop.worker_manager._log"):
            manager.stop()  # First call — terminates
            manager.stop()  # Second call — no-op

        mock_process.terminate.assert_called_once()  # Called only once


class TestHermesWorkerManagerIsRunning:
    """Tests for is_running property."""

    def test_is_running_process_none_returns_false(self):
        """When _process is None, is_running returns False."""
        manager = HermesWorkerManager()
        assert manager._process is None
        assert manager.is_running is False

    def test_is_running_process_poll_is_none_returns_true(self):
        """When _process.poll() is None (still running), is_running returns True."""
        manager = HermesWorkerManager()
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        manager._process = mock_process
        assert manager.is_running is True

    def test_is_running_process_poll_returns_int_returns_false(self):
        """When _process.poll() returns an int (exited), is_running returns False."""
        manager = HermesWorkerManager()
        mock_process = MagicMock()
        mock_process.poll.return_value = 0
        manager._process = mock_process
        assert manager.is_running is False

    def test_is_running_after_stop_returns_false(self):
        """After stop(), is_running returns False."""
        manager = HermesWorkerManager()
        mock_process = MagicMock()
        mock_process.pid = 3333
        mock_process.poll.return_value = None
        manager._process = mock_process

        with patch("hermes_loop.worker_manager._log"):
            manager.stop()

        assert manager._process is None
        assert manager.is_running is False

    def test_is_running_transitions_correctly(self):
        """is_running reflects process lifecycle: None→True→False after stop."""
        manager = HermesWorkerManager()

        # Before start
        assert manager.is_running is False

        # Simulate process running
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        manager._process = mock_process
        assert manager.is_running is True

        # Process exits naturally
        mock_process.poll.return_value = 1
        assert manager.is_running is False

        # Reset to None
        manager._process = None
        assert manager.is_running is False


# ===================================================================
# Integration-style: start → stop cycle (mocked)
# ===================================================================


class TestHermesWorkerManagerFullLifecycle:
    """Full lifecycle tests with mocks: start → is_running → stop."""

    def test_full_success_lifecycle(self):
        """Start succeeds → is_running is True → stop() works."""
        with (
            patch("hermes_loop.worker_manager.os.path.isfile", return_value=True),
            patch("hermes_loop.worker_manager.subprocess.Popen") as mock_popen,
            patch("hermes_loop.worker_manager.urllib.request.urlopen") as mock_urlopen,
            patch("hermes_loop.worker_manager._log"),
            patch("socket.socket") as mock_socket_cls,
        ):
            mock_sock = MagicMock()
            mock_sock.getsockname.return_value = ("0.0.0.0", 12348)
            mock_socket_cls.return_value.__enter__.return_value = mock_sock
            mock_socket_cls.return_value.__exit__.return_value = None

            mock_process = MagicMock()
            mock_process.pid = 2222
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            mock_response = MagicMock()
            mock_response.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_response

            manager = HermesWorkerManager()

            # Start
            url = manager.start()
            assert url == "http://127.0.0.1:12348"
            assert manager.is_running is True

            # Stop
            manager.stop()
            assert manager.is_running is False
            mock_process.terminate.assert_called_once()

    def test_start_failure_then_stop_is_safe(self):
        """When start fails, stop is still safe."""
        with (
            patch("hermes_loop.worker_manager.os.path.isfile", return_value=True),
            patch("hermes_loop.worker_manager.subprocess.Popen") as mock_popen,
            patch("hermes_loop.worker_manager._log"),
            patch("socket.socket") as mock_socket_cls,
        ):
            mock_sock = MagicMock()
            mock_sock.getsockname.return_value = ("0.0.0.0", 12349)
            mock_socket_cls.return_value.__enter__.return_value = mock_sock
            mock_socket_cls.return_value.__exit__.return_value = None

            mock_popen.side_effect = OSError("port unavailable")

            manager = HermesWorkerManager()
            url = manager.start()
            assert url == ""

            # stop() is safe even though start failed
            manager.stop()
            assert manager._process is None
            assert manager.is_running is False
