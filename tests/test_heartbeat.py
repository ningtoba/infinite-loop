"""Tests for heartbeat.py — session health monitoring helpers."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch


from hermes_loop.heartbeat import (
    _heartbeat_path,
    _read_heartbeat,
    _write_heartbeat_file,
    _heartbeat_age,
    _monitor_heartbeat,
    _run_heartbeat_monitor,
    _kill_session,
    _cleanup_stale_heartbeats,
    _cleanup_heartbeat_file,
)
from hermes_loop.config import HEARTBEAT_DIR, HEARTBEAT_PREFIX

# ===================================================================
# _heartbeat_path
# ===================================================================


class TestHeartbeatPath:
    """Tests for _heartbeat_path helper."""

    def test_returns_joined_path(self):
        """Joins HEARTBEAT_DIR, HEARTBEAT_PREFIX, and identifier."""
        result = _heartbeat_path("my-123")
        assert HEARTBEAT_DIR in result
        assert HEARTBEAT_PREFIX in result
        assert "my-123" in result

    def test_uses_config_values(self):
        """Uses HEARTBEAT_DIR and HEARTBEAT_PREFIX from config."""
        result = _heartbeat_path("test-session")
        assert result.startswith(HEARTBEAT_DIR)
        assert HEARTBEAT_PREFIX in result

    def test_empty_identifier(self):
        """Empty identifier still returns a valid path."""
        result = _heartbeat_path("")
        assert result.startswith(HEARTBEAT_DIR)

    def test_identifier_with_pid(self):
        """PID string is included in path."""
        result = _heartbeat_path("12345")
        assert "12345" in result


# ===================================================================
# _read_heartbeat
# ===================================================================


class TestReadHeartbeat:
    """Tests for _read_heartbeat function."""

    def test_reads_valid_heartbeat(self, tmp_path: Path):
        """Read a valid heartbeat file."""
        hb_file = os.path.join(tmp_path, "test.hb")
        data = {"session_id": "abc", "timestamp": 100.0}
        with open(hb_file, "w") as f:
            f.write(json.dumps(data) + "\n")
        result = _read_heartbeat(hb_file)
        assert result == data

    def test_file_not_found(self):
        """Non-existent file returns None."""
        result = _read_heartbeat("/nonexistent/heartbeat.hb")
        assert result is None

    def test_invalid_json(self, tmp_path: Path):
        """File with invalid JSON returns None."""
        hb_file = os.path.join(tmp_path, "bad.hb")
        with open(hb_file, "w") as f:
            f.write("not json at all")
        result = _read_heartbeat(hb_file)
        assert result is None

    def test_empty_file(self, tmp_path: Path):
        """Empty file returns None."""
        hb_file = os.path.join(tmp_path, "empty.hb")
        with open(hb_file, "w") as f:
            f.write("")
        result = _read_heartbeat(hb_file)
        assert result is None

    def test_extra_whitespace(self, tmp_path: Path):
        """File with leading/trailing whitespace is handled."""
        hb_file = os.path.join(tmp_path, "spaced.hb")
        with open(hb_file, "w") as f:
            f.write('  {"k": "v"}  \n')
        result = _read_heartbeat(hb_file)
        assert result == {"k": "v"}


# ===================================================================
# _write_heartbeat_file
# ===================================================================


class TestWriteHeartbeatFile:
    """Tests for _write_heartbeat_file function."""

    def test_writes_file(self, tmp_path: Path):
        """Write a heartbeat file successfully."""
        hb_file = os.path.join(tmp_path, "test.hb")
        data = {"session_id": "abc", "timestamp": time.time()}
        result = _write_heartbeat_file(hb_file, data)
        assert result is True
        assert os.path.exists(hb_file)
        with open(hb_file) as f:
            assert json.loads(f.read()) == data

    def test_creates_parent_dirs(self, tmp_path: Path):
        """Create parent directories if they don't exist."""
        hb_file = os.path.join(tmp_path, "subdir", "test.hb")
        data = {"k": "v"}
        result = _write_heartbeat_file(hb_file, data)
        assert result is True
        assert os.path.exists(hb_file)

    def test_atomic_write(self, tmp_path: Path):
        """Writes .tmp file then renames (atomic)."""
        hb_file = os.path.join(tmp_path, "atomic.hb")
        data = {"k": "v"}
        result = _write_heartbeat_file(hb_file, data)
        assert result is True
        # .tmp should not exist after write
        assert not os.path.exists(hb_file + ".tmp")
        assert os.path.exists(hb_file)


# ===================================================================
# _heartbeat_age
# ===================================================================


class TestHeartbeatAge:
    """Tests for _heartbeat_age function."""

    def test_returns_age(self, tmp_path: Path):
        """Returns time since last modification."""
        hb_file = os.path.join(tmp_path, "age.hb")
        with open(hb_file, "w") as f:
            f.write("{}\n")
        age = _heartbeat_age(hb_file)
        assert age is not None
        assert 0 <= age < 5  # just written, should be < 5 seconds ago

    def test_file_not_found(self):
        """Non-existent file returns None."""
        result = _heartbeat_age("/nonexistent/file")
        assert result is None


# ===================================================================
# _monitor_heartbeat
# ===================================================================


class TestMonitorHeartbeat:
    """Tests for _monitor_heartbeat function."""

    def test_completed_when_proc_done(self, tmp_path: Path):
        """Process already exited returns 'completed'."""
        hb_file = os.path.join(tmp_path, "test.hb")
        with open(hb_file, "w") as f:
            f.write("{}\n")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0

        # Run in a thread with timeout since _monitor_heartbeat blocks
        result_wrapper = {}

        def runner():
            result_wrapper["result"] = _monitor_heartbeat(
                hb_file, 30, time.time(), mock_proc
            )

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        t.join(timeout=2)

        assert result_wrapper.get("result", {}).get("status") == "completed"

    @patch("hermes_loop.heartbeat._shutdown_requested", True)
    def test_shutdown_requested_returns_alive(self, tmp_path: Path):
        """When shutdown is requested, returns 'alive'."""
        hb_file = os.path.join(tmp_path, "test.hb")
        with open(hb_file, "w") as f:
            f.write("{}\n")
        result = _monitor_heartbeat(hb_file, 30, time.time(), None)
        assert result["status"] == "alive"


# ===================================================================
# _run_heartbeat_monitor
# ===================================================================


class TestRunHeartbeatMonitor:
    """Tests for _run_heartbeat_monitor function."""

    def test_runs_in_thread_and_returns(self, tmp_path: Path):
        """Runs monitor in daemon thread and returns result."""
        hb_file = os.path.join(tmp_path, "test.hb")
        with open(hb_file, "w") as f:
            f.write("{}\n")

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0

        result = _run_heartbeat_monitor(
            heartbeat_file=hb_file,
            timeout=30,
            session_start=time.time(),
            proc=mock_proc,
            timeout_seconds=60,
        )
        assert result["status"] in ("completed", "alive")

    def test_proc_none_large_timeout(self, tmp_path: Path):
        """None proc with large timeout_seconds runs the monitor."""
        hb_file = os.path.join(tmp_path, "test.hb")
        with open(hb_file, "w") as f:
            f.write("{}\n")

        # With a non-existent heartbeat file (age=None), the monitor checks
        # elapsed vs timeout. Use a very old session_start so it returns
        # quickly with status="lost".
        result = _run_heartbeat_monitor(
            heartbeat_file=hb_file + ".nonexistent",
            timeout=2,
            session_start=time.time() - 300,
            proc=None,
            timeout_seconds=2,
        )
        assert isinstance(result, dict)
        assert result.get("status") == "lost"


# ===================================================================
# _kill_session
# ===================================================================


class TestKillSession:
    """Tests for _kill_session function."""

    def test_none_proc_does_nothing(self):
        """None proc silently returns."""
        # Should not raise
        _kill_session(None, "session-123")

    def test_already_exited_does_nothing(self):
        """Already-exited proc does nothing."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        # Should not raise
        _kill_session(mock_proc, "session-123")
        mock_proc.terminate.assert_not_called()

    def test_terminates_running_proc(self):
        """Running proc is terminated."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0

        _kill_session(mock_proc, "session-456")

        mock_proc.terminate.assert_called_once()
        assert mock_proc.wait.called

    def test_terminate_then_kill(self):
        """SIGTERM followed by SIGKILL after timeout."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), 0]

        _kill_session(mock_proc, "session-789")

        mock_proc.terminate.assert_called_once()
        assert mock_proc.wait.call_count == 2
        mock_proc.kill.assert_called_once()

    def test_empty_session_id(self):
        """Empty session_id is handled without crash."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0

        _kill_session(mock_proc, "")
        mock_proc.terminate.assert_called_once()


# ===================================================================
# _cleanup_stale_heartbeats
# ===================================================================


class TestCleanupStaleHeartbeats:
    """Tests for _cleanup_stale_heartbeats function."""

    def test_removes_matching_files(self, tmp_path: Path):
        """Removes heartbeat files in HEARTBEAT_DIR matching prefix."""
        # Create a real heartbeat file in tmp_path
        hb_file = os.path.join(tmp_path, f"{HEARTBEAT_PREFIX}old-session")
        with open(hb_file, "w") as f:
            f.write("{}\n")

        with patch("hermes_loop.heartbeat.HEARTBEAT_DIR", str(tmp_path)):
            _cleanup_stale_heartbeats()
        assert not os.path.exists(hb_file)

    def test_leaves_other_files(self, tmp_path: Path):
        """Non-heartbeat files are not removed."""
        other = os.path.join(tmp_path, "other-file.txt")
        with open(other, "w") as f:
            f.write("data\n")

        with patch("hermes_loop.heartbeat.HEARTBEAT_DIR", str(tmp_path)):
            _cleanup_stale_heartbeats()
        assert os.path.exists(other)

    def test_no_files_does_nothing(self, tmp_path: Path):
        """No heartbeat files is a no-op."""
        with patch("hermes_loop.heartbeat.HEARTBEAT_DIR", str(tmp_path)):
            _cleanup_stale_heartbeats()  # Should not raise


# ===================================================================
# _cleanup_heartbeat_file
# ===================================================================


class TestCleanupHeartbeatFile:
    """Tests for _cleanup_heartbeat_file function."""

    def test_removes_existing_file(self, tmp_path: Path):
        """Removes a single heartbeat file."""
        hb_file = os.path.join(tmp_path, "test.hb")
        with open(hb_file, "w") as f:
            f.write("{}\n")
        assert os.path.exists(hb_file)
        _cleanup_heartbeat_file(hb_file)
        assert not os.path.exists(hb_file)

    def test_none_path_does_nothing(self):
        """None path is a no-op."""
        _cleanup_heartbeat_file(None)  # Should not raise

    def test_non_existent_file_does_nothing(self):
        """Non-existent file is a no-op."""
        _cleanup_heartbeat_file("/nonexistent/file.hb")  # Should not raise

    def test_empty_string_does_nothing(self):
        """Empty string path is a no-op."""
        _cleanup_heartbeat_file("")  # Should not raise
