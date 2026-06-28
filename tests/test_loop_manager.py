"""Tests for web_app.loop_manager — LoopManager subprocess lifecycle."""

import asyncio
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web_app.loop_manager import LoopManager, get_loop_manager


class TestLoopManagerInit:
    def test_initial_state(self):
        """LoopManager starts in 'stopped' state."""
        mgr = LoopManager()
        assert mgr.status == "stopped"
        assert mgr.is_running == False
        assert mgr.live_iteration == {}
        assert mgr.logs == []


class TestLoopManagerStatus:
    def test_status_property(self):
        """status property returns internal _status."""
        mgr = LoopManager()
        assert mgr.status == "stopped"

    def test_not_running_when_stopped(self):
        """is_running is False when stopped."""
        mgr = LoopManager()
        assert mgr.is_running == False

    def test_not_running_when_no_process(self):
        """is_running is False when process is None."""
        mgr = LoopManager()
        mgr._status = "running"
        mgr._process = None
        assert mgr.is_running == False


class TestLoopManagerAddLog:
    def test_adds_log_entry(self):
        """_add_log creates a log entry."""
        mgr = LoopManager()
        mgr._add_log("info", "test message")
        assert len(mgr.logs) == 1
        assert mgr.logs[0]["level"] == "info"
        assert mgr.logs[0]["message"] == "test message"

    def test_limits_log_entries(self):
        """_add_log limits log entries to _max_logs."""
        mgr = LoopManager()
        mgr._max_logs = 5
        for i in range(10):
            mgr._add_log("info", f"message {i}")
        assert len(mgr.logs) == 5

    def test_writes_to_log_file(self, tmp_path):
        """_add_log also writes to log file."""
        log_file = tmp_path / "loop.log"
        mgr = LoopManager()
        mgr._log_file = str(log_file)
        with patch("pi_loop.config.DEFAULT_LOG_FILE", str(log_file)):
            mgr._add_log("info", "file message")
            assert log_file.exists()
            content = log_file.read_text()
            assert "file message" in content


class TestLoopManagerGetLedger:
    def test_no_ledger(self, tmp_path):
        """get_ledger returns default when no ledger exists."""
        mgr = LoopManager()
        mgr._ledger_path = str(tmp_path / "nonexistent.json")
        result = mgr.get_ledger()
        assert result["status"] == "no_ledger"

    def test_existing_ledger(self, tmp_path):
        """get_ledger reads existing ledger."""
        ledger_path = tmp_path / "ledger.json"
        ledger_path.write_text(json.dumps({"status": "running", "iterations": [{"n": 1}], "total_iterations": 1}))
        mgr = LoopManager()
        mgr._ledger_path = str(ledger_path)
        result = mgr.get_ledger()
        assert result["status"] == "running"
        assert result["total_iterations"] == 1

    def test_corrupted_ledger(self, tmp_path):
        """get_ledger returns default when ledger is corrupted."""
        ledger_path = tmp_path / "ledger.json"
        ledger_path.write_text("invalid json")
        mgr = LoopManager()
        mgr._ledger_path = str(ledger_path)
        result = mgr.get_ledger()
        assert result["status"] == "no_ledger"


class TestLoopManagerGetStatus:
    def test_returns_combined_status(self, tmp_path):
        """get_status returns combined status information."""
        mgr = LoopManager()
        mgr._status = "stopped"
        result = mgr.get_status()
        assert result["loop_status"] == "stopped"
        assert "ledger" in result
        assert "stats" in result
        assert "latest_iteration" in result

    def test_includes_pid_when_running(self):
        """get_status includes PID when process exists."""
        mgr = LoopManager()
        mgr._process = MagicMock()
        mgr._process.pid = 12345
        result = mgr.get_status()
        assert result["pid"] == 12345

    def test_includes_recent_logs(self):
        """get_status includes recent logs."""
        mgr = LoopManager()
        mgr._add_log("info", "log1")
        mgr._add_log("warn", "log2")
        result = mgr.get_status()
        assert len(result["recent_logs"]) == 2


@pytest.mark.asyncio
class TestLoopManagerStart:
    async def test_already_running(self):
        """start returns error when already running."""
        mgr = LoopManager()
        mgr._status = "running"
        mgr._process = MagicMock()
        result = await mgr.start()
        assert result["success"] == False
        assert "already running" in result["error"]

    async def test_start_success(self):
        """start creates subprocess and returns success."""
        mgr = LoopManager()
        mock_proc = AsyncMock()
        mock_proc.pid = 9999
        mock_proc.returncode = None

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.sleep"),
            patch("asyncio.create_task"),
        ):
            result = await mgr.start()

        assert result["success"] == True
        assert result["pid"] == 9999
        assert mgr._status == "running"

    async def test_immediate_exit(self):
        """start detects process that exits immediately."""
        mgr = LoopManager()
        mock_proc = AsyncMock()
        mock_proc.pid = 9999
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), patch("asyncio.sleep"):
            result = await mgr.start()

        assert result["success"] == False
        assert mgr._status == "error"

    async def test_start_timeout(self):
        """start handles timeout."""
        mgr = LoopManager()
        with (
            patch("asyncio.create_subprocess_exec", side_effect=asyncio.TimeoutError()),
            patch("asyncio.sleep"),
            patch.object(mgr, "close"),
        ):
            result = await mgr.start()

        assert result["success"] == False
        assert "Timed out" in result["error"]


@pytest.mark.asyncio
class TestLoopManagerStop:
    async def test_not_running(self):
        """stop returns error when not running."""
        mgr = LoopManager()
        result = await mgr.stop()
        assert result["success"] == False

    async def test_stop_success(self):
        """stop kills process group and cleans up."""
        mgr = LoopManager()
        mock_proc = AsyncMock()
        mock_proc.pid = 12345
        mgr._process = mock_proc
        mgr._status = "running"

        with (
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
            patch("os.kill"),
            patch("os.getpgid", return_value=12345),
            patch.object(mgr, "close"),
            patch("os.killpg"),
        ):
            result = await mgr.stop()

        assert result["success"] == True
        assert mgr._process is None


@pytest.mark.asyncio
class TestLoopManagerPauseResume:
    async def test_pause_not_running(self):
        """pause returns error when not running."""
        mgr = LoopManager()
        result = await mgr.pause()
        assert result["success"] == False

    async def test_pause_writes_sentinel(self):
        """pause writes sentinel and sets status to paused."""
        mgr = LoopManager()
        mgr._process = MagicMock()
        mgr._status = "running"
        with patch("builtins.open", MagicMock()):
            result = await mgr.pause()
        assert result["success"] == True
        assert mgr._status == "paused"

    async def test_resume_not_paused(self):
        """resume returns error when not paused."""
        mgr = LoopManager()
        result = await mgr.resume()
        assert result["success"] == False

    async def test_resume_removes_sentinel(self):
        """resume removes sentinel and sets status to running."""
        mgr = LoopManager()
        mgr._status = "paused"
        with patch("os.path.exists", return_value=True), patch("os.remove"):
            result = await mgr.resume()
        assert result["success"] == True
        assert mgr._status == "running"


class TestLoopManagerParseDaemonLine:
    def test_detects_iteration_start(self):
        """_parse_daemon_line detects iteration start."""
        mgr = LoopManager()
        mgr._parse_daemon_line("[10:30:00]  Iteration  #42")
        assert mgr._live_iteration.get("n") == 42

    def test_detects_worker_spawn(self):
        """_parse_daemon_line detects worker spawn."""
        mgr = LoopManager()
        mgr._parse_daemon_line("[SPAWN (worker #1)] pi --mode json -- goal")
        assert "1" in mgr._worker_states

    def test_detects_worker_response(self):
        """_parse_daemon_line detects worker completion."""
        mgr = LoopManager()
        mgr._parse_daemon_line("[WORKER (worker #2)] Response in 15.5s (status=ok)")
        assert mgr._worker_states["2"]["status"] == "ok"

    def test_detects_heartbeat(self):
        """_parse_daemon_line detects heartbeat for live iteration."""
        mgr = LoopManager()
        mgr._live_iteration["n"] = 42
        mgr._parse_daemon_line("[BEAT] Iteration #42 still running (30s)")
        assert mgr._live_iteration.get("elapsed_seconds") == 30

    def test_detects_error_type(self):
        """_parse_daemon_line detects error type."""
        mgr = LoopManager()
        mgr._parse_daemon_line("[ERROR-TYPE] timeout")
        assert mgr._live_iteration.get("error_type") == "timeout"

    def test_ignores_still_running_in_iteration_line(self):
        """_parse_daemon_line ignores iteration lines with 'still running'."""
        mgr = LoopManager()
        mgr._parse_daemon_line("[10:30:00]  Iteration  #42 still running (30s)")
        # Should NOT set n since 'still running' is present
        # _live_iteration may have 'workers': [] from unconditional code at end
        assert mgr._live_iteration.get("n") is None or mgr._live_iteration.get("n") != 42

    def test_captures_term_output(self):
        """_parse_daemon_line captures terminal output for xterm.js."""
        mgr = LoopManager()
        mgr._parse_daemon_line("[TERM (worker #1)] Building project...")
        assert "1" in mgr._worker_term
        assert "Building project..." in mgr._worker_term["1"][0]


class TestLoopManagerReadStream:
    @pytest.mark.asyncio
    async def test_reads_lines(self):
        """_read_stream reads lines from stream."""
        mgr = LoopManager()
        mgr._process = MagicMock()  # Must have process for loop to execute
        mock_stream = AsyncMock()
        mock_stream.readline = AsyncMock(
            side_effect=[
                b"[BEAT] Iteration #1 still running (5s)\n",
                b"",  # Empty → break
            ]
        )
        await mgr._read_stream(mock_stream, "stdout")
        assert len(mgr.logs) > 0

    @pytest.mark.asyncio
    async def test_handles_encoding_error(self):
        """_read_stream handles decode errors."""
        mgr = LoopManager()
        mock_stream = AsyncMock()
        mock_stream.readline = AsyncMock(
            side_effect=[
                b"\xff\xfe\x00",  # Invalid UTF-8
                b"",
            ]
        )
        await mgr._read_stream(mock_stream, "stdout")


class TestLoopManagerClose:
    def test_closes_log_file(self):
        """close closes the log file handle."""
        mgr = LoopManager()
        # Simulate an open log file
        mgr._log_fp = io.StringIO()  # type: ignore[assignment]
        mgr.close()
        assert mgr._log_fp is None

    def test_close_idempotent(self):
        """close is idempotent when no log file."""
        mgr = LoopManager()
        mgr.close()
        assert mgr._log_fp is None


class TestGetLoopManager:
    def test_returns_singleton(self):
        """get_loop_manager returns a singleton instance."""
        mgr1 = get_loop_manager()
        mgr2 = get_loop_manager()
        assert mgr1 is mgr2

    def test_returns_loop_manager(self):
        """get_loop_manager returns a LoopManager instance."""
        mgr = get_loop_manager()
        assert isinstance(mgr, LoopManager)
