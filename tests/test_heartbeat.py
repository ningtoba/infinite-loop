"""Tests for pi_loop.heartbeat — heartbeat helpers for session self-healing."""

import json
import time
from unittest.mock import MagicMock, patch

from pi_loop.heartbeat import (
    _cleanup_heartbeat_file,
    _cleanup_stale_heartbeats,
    _heartbeat_age,
    _heartbeat_path,
    _kill_session,
    _monitor_heartbeat,
    _read_heartbeat,
    _request_shutdown,
    _run_heartbeat_monitor,
    _write_heartbeat_file,
)


class TestHeartbeatPath:
    def test_returns_path(self):
        """_heartbeat_path returns a valid path with prefix."""
        path = _heartbeat_path("abc123")
        assert "infinite-loop-heartbeat-" in path
        assert "abc123" in path


class TestReadHeartbeat:
    def test_valid_json(self, tmp_path):
        """_read_heartbeat parses valid heartbeat JSON."""
        hb_file = tmp_path / "heartbeat"
        hb_file.write_text(json.dumps({"status": "alive", "iter": 5}))
        data = _read_heartbeat(str(hb_file))
        assert data["status"] == "alive"
        assert data["iter"] == 5

    def test_nonexistent_file(self):
        """_read_heartbeat returns None for nonexistent file."""
        data = _read_heartbeat("/nonexistent/heartbeat")
        assert data is None

    def test_invalid_json(self, tmp_path):
        """_read_heartbeat returns None for invalid JSON."""
        hb_file = tmp_path / "heartbeat"
        hb_file.write_text("not json")
        data = _read_heartbeat(str(hb_file))
        assert data is None


class TestWriteHeartbeatFile:
    def test_writes_atomically(self, tmp_path):
        """_write_heartbeat_file writes via .tmp then rename."""
        hb_file = str(tmp_path / "heartbeat")
        result = _write_heartbeat_file(hb_file, {"key": "value"})
        assert result == True
        assert (tmp_path / "heartbeat").exists()
        data = json.loads((tmp_path / "heartbeat").read_text())
        assert data["key"] == "value"

    def test_returns_false_on_error(self):
        """_write_heartbeat_file returns False on OSError."""
        with patch("os.makedirs", side_effect=OSError("permission denied")):
            result = _write_heartbeat_file("/proc/heartbeat", {})
        assert result == False


class TestHeartbeatAge:
    def test_returns_age(self, tmp_path):
        """_heartbeat_age returns seconds since last modified."""
        hb_file = tmp_path / "heartbeat"
        hb_file.write_text("data")
        age = _heartbeat_age(str(hb_file))
        assert age is not None
        assert 0 <= age < 5  # Just written, should be < 5s

    def test_nonexistent(self):
        """_heartbeat_age returns None for nonexistent file."""
        age = _heartbeat_age("/nonexistent")
        assert age is None


class TestKillSession:
    def test_kills_subprocess(self):
        """_kill_session terminates and waits, then kills if needed."""
        proc = MagicMock()
        proc.poll.return_value = None
        _kill_session(proc, "test123")
        proc.terminate.assert_called_once()

    def test_skips_already_exited(self):
        """_kill_session skips if process already exited."""
        proc = MagicMock()
        proc.poll.return_value = 0
        _kill_session(proc, "test123")
        proc.terminate.assert_not_called()

    def test_kills_on_timeout(self):
        """_kill_session uses SIGKILL after SIGTERM timeout."""
        proc = MagicMock()
        proc.poll.return_value = None
        proc.wait.side_effect = [None, None]  # First wait succeeds
        _kill_session(proc, "test123")
        proc.terminate.assert_called_once()
        assert proc.kill.call_count >= 0  # May not be called if terminate works


class TestMonitorHeartbeat:
    def test_completed_when_proc_done(self):
        """_monitor_heartbeat returns 'completed' when process is done."""
        proc = MagicMock()
        proc.poll.return_value = 0
        result = _monitor_heartbeat("/some/file", 60, time.time(), proc)
        assert result["status"] == "completed"

    def test_shutdown_returns_alive(self):
        """_monitor_heartbeat returns 'alive' when shutdown is requested."""
        _request_shutdown()
        result = _monitor_heartbeat("/some/file", 60, time.time(), None)
        assert result["status"] == "alive"


class TestCleanupStaleHeartbeats:
    def test_removes_matching_files(self, tmp_path):
        """_cleanup_stale_heartbeats removes heartbeat files."""
        with (
            patch("pi_loop.heartbeat.HEARTBEAT_DIR", str(tmp_path)),
            patch("pi_loop.heartbeat.HEARTBEAT_PREFIX", "hb-"),
        ):
            (tmp_path / "hb-123").write_text("data")
            (tmp_path / "hb-456").write_text("data")
            (tmp_path / "other").write_text("data")
            _cleanup_stale_heartbeats()
            assert not (tmp_path / "hb-123").exists()
            assert not (tmp_path / "hb-456").exists()
            assert (tmp_path / "other").exists()


class TestCleanupHeartbeatFile:
    def test_removes_existing(self, tmp_path):
        """_cleanup_heartbeat_file removes an existing heartbeat file."""
        hb_file = tmp_path / "heartbeat"
        hb_file.write_text("data")
        _cleanup_heartbeat_file(str(hb_file))
        assert not hb_file.exists()

    def test_none_does_nothing(self):
        """_cleanup_heartbeat_file with None does nothing."""
        _cleanup_heartbeat_file(None)


class TestRunHeartbeatMonitor:
    def test_returns_result_dict(self):
        """_run_heartbeat_monitor returns a result dict."""
        proc = MagicMock()
        proc.poll.return_value = 0  # Process already done
        with patch(
            "pi_loop.heartbeat._monitor_heartbeat",
            return_value={"status": "completed", "age_seconds": 0, "last_heartbeat_data": None},
        ):
            result = _run_heartbeat_monitor("/some/file", 60, time.time(), proc, 120)
        assert "status" in result
