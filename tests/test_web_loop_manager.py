"""Tests for web_app.loop_manager — daemon lifecycle, worker parsing, status reporting."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


from web_app.loop_manager import LoopManager, get_loop_manager

# ============================================================================
# Section 1: Initial state (3 tests)
# ============================================================================


class TestLoopManagerInitialState:
    """Verify the default state of a freshly created LoopManager."""

    def test_status_is_stopped(self):
        lm = LoopManager()
        assert lm.status == "stopped"

    def test_is_running_is_false(self):
        lm = LoopManager()
        assert lm.is_running is False

    def test_logs_empty(self):
        lm = LoopManager()
        assert lm.logs == []


# ============================================================================
# Section 2: _add_log (4 tests)
# ============================================================================


class TestAddLog:
    """Tests for _add_log() internal method."""

    def test_adds_timestamped_entry(self):
        lm = LoopManager()
        lm._add_log("info", "test message")
        assert len(lm._logs) == 1
        entry = lm._logs[0]
        assert entry["level"] == "info"
        assert entry["message"] == "test message"
        assert "timestamp" in entry

    def test_trims_to_max_logs(self):
        lm = LoopManager()
        lm._max_logs = 10
        for i in range(15):
            lm._add_log("info", f"msg {i}")
        assert len(lm._logs) == 10
        assert lm._logs[0]["message"] == "msg 5"
        assert lm._logs[-1]["message"] == "msg 14"

    def test_writes_to_log_file(self, tmp_path: Path):
        lm = LoopManager()
        log_file = tmp_path / "loop.log"
        lm._log_file = str(log_file)
        lm._log_fp = None
        lm._add_log("info", "file test")
        assert log_file.exists()
        content = log_file.read_text()
        assert "[info]" in content
        assert "file test" in content

    def test_handles_oserror_gracefully(self):
        """_add_log should not crash if writing to log file fails."""
        lm = LoopManager()
        lm._log_file = "/nonexistent_dir/subdir/log.log"
        lm._log_fp = None
        # Should not raise
        lm._add_log("info", "should not crash")
        # Log entry still in memory even if file write failed
        assert len(lm._logs) == 1


# ============================================================================
# Section 3: get_ledger (3 tests)
# ============================================================================


class TestGetLedger:
    """Tests for get_ledger()."""

    def test_returns_ledger_data_from_file(self, tmp_path: Path):
        lm = LoopManager()
        ledger_path = tmp_path / "ledger.json"
        ledger_data = {"total_iterations": 5, "iterations": [], "status": "running"}
        ledger_path.write_text(json.dumps(ledger_data))
        with patch("web_app.loop_manager.LEDGER_PATH", str(ledger_path)):
            result = lm.get_ledger()
            assert result["total_iterations"] == 5
            assert result["status"] == "running"

    def test_returns_default_when_no_ledger(self):
        """Returns a default structure if ledger file doesn't exist."""
        lm = LoopManager()
        with patch("web_app.loop_manager.os.path.exists", return_value=False):
            result = lm.get_ledger()
            assert result == {
                "status": "no_ledger",
                "iterations": [],
                "total_iterations": 0,
            }

    def test_returns_default_on_corrupt_json(self, tmp_path: Path):
        lm = LoopManager()
        ledger_path = tmp_path / "corrupt.json"
        ledger_path.write_text("not json")
        with patch("web_app.loop_manager.LEDGER_PATH", str(ledger_path)):
            result = lm.get_ledger()
            assert result == {
                "status": "no_ledger",
                "iterations": [],
                "total_iterations": 0,
            }


# ============================================================================
# Section 4: get_status (5 tests)
# ============================================================================


class TestGetStatus:
    """Tests for get_status()."""

    def test_returns_basic_status_when_not_running(self):
        lm = LoopManager()
        with (patch("web_app.loop_manager.LEDGER_PATH", "/nonexistent/ledger.json"),):
            status = lm.get_status()
            assert status["loop_status"] == "stopped"
            assert status["pid"] is None
            assert "ledger" in status
            assert "stats" in status
            assert "recent_logs" in status

    def test_ledger_section_in_status(self):
        lm = LoopManager()
        with (patch("web_app.loop_manager.LEDGER_PATH", "/nonexistent/ledger.json"),):
            status = lm.get_status()
            ledger_info = status["ledger"]
            assert "total_iterations" in ledger_info
            assert "status" in ledger_info
            assert "goal" in ledger_info
            assert "evolved_goal" in ledger_info

    def test_stats_section_in_status(self):
        lm = LoopManager()
        with (patch("web_app.loop_manager.LEDGER_PATH", "/nonexistent/ledger.json"),):
            status = lm.get_status()
            stats = status["stats"]
            assert "success_count" in stats
            assert "error_count" in stats
            assert "total_duration_seconds" in stats

    def test_metrics_summary_empty_when_no_iterations(self):
        lm = LoopManager()
        with (patch("web_app.loop_manager.LEDGER_PATH", "/nonexistent/ledger.json"),):
            status = lm.get_status()
            assert status["metrics_summary"] == ""

    def test_computes_avg_chars_from_iterations(self, tmp_path: Path):
        lm = LoopManager()
        ledger_path = tmp_path / "ledger.json"
        ledger_data = {
            "total_iterations": 2,
            "iterations": [
                {"output_chars": 100, "chars_per_second": 10.0, "duration_seconds": 10},
                {"output_chars": 200, "chars_per_second": 10.0, "duration_seconds": 20},
            ],
            "stats": {
                "success_count": 2,
                "error_count": 0,
                "total_duration_seconds": 30,
                "avg_duration_seconds": 15,
            },
        }
        ledger_path.write_text(json.dumps(ledger_data))
        with patch("web_app.loop_manager.LEDGER_PATH", str(ledger_path)):
            status = lm.get_status()
            assert status["avg_chars_per_iter"] == 150  # (100+200)//2
            assert status["avg_throughput"] == 10.0  # avg of both 10.0


# ============================================================================
# Section 5: _kill_stale_daemons (2 tests)
# ============================================================================


class TestKillStaleDaemons:
    """Tests for _kill_stale_daemons()."""

    @patch("web_app.loop_manager.subprocess.run")
    def test_kill_calls_pkill(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0)
        lm = LoopManager()
        lm._kill_stale_daemons()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert "pkill" in args[0]

    @patch("web_app.loop_manager.subprocess.run")
    def test_kill_no_error_on_failure(self, mock_run: MagicMock):
        mock_run.side_effect = Exception("pkill not found")
        lm = LoopManager()
        # Should not raise
        lm._kill_stale_daemons()


# ============================================================================
# Section 6: _parse_daemon_line — iteration start (3 tests)
# ============================================================================


class TestParseDaemonLineIterationStart:
    """Tests for iteration-start header parsing."""

    def test_parses_iteration_start(self):
        lm = LoopManager()
        lm._parse_daemon_line("[12:34:56] Iteration 3")
        assert lm._live_iteration.get("n") == 3
        assert "started_at" in lm._live_iteration

    def test_handles_hash_in_iteration_number(self):
        lm = LoopManager()
        lm._parse_daemon_line("[12:00:00] Iteration #5")
        assert lm._live_iteration.get("n") == 5

    def test_does_not_match_still_running_line(self):
        lm = LoopManager()
        lm._parse_daemon_line("[12:00:00] Iteration 1 still running (10s)")
        # Should NOT update live_iteration["n"] because "still running" is in text
        assert lm._live_iteration.get("n") is None


# ============================================================================
# Section 7: _parse_daemon_line — worker events (6 tests)
# ============================================================================


class TestParseDaemonLineWorkerEvents:
    """Tests for worker-related structured prefix matching."""

    def test_parse_stdout_worker(self):
        lm = LoopManager()
        lm._parse_daemon_line("[STDOUT (worker #0)] Hello from worker")
        assert "0" in lm._worker_states
        assert lm._worker_states["0"]["status"] == "running"
        assert "0" in lm._worker_logs
        assert len(lm._worker_logs["0"]) == 1
        assert "Hello from worker" in lm._worker_logs["0"][-1]["message"]

    def test_parse_stderr_worker(self):
        lm = LoopManager()
        lm._parse_daemon_line("[STDERR (worker #2)] error detail")
        assert "2" in lm._worker_states
        assert "2" in lm._worker_logs
        assert "error detail" in lm._worker_logs["2"][-1]["message"]

    def test_parse_term_worker_stores_terminal_content(self):
        lm = LoopManager()
        lm._parse_daemon_line("[TERM (worker #1)] $ ls -la")
        assert "1" in lm._worker_term
        assert len(lm._worker_term["1"]) == 1
        assert lm._worker_term["1"][0] == "$ ls -la"
        # TERM lines should NOT be stored in worker_logs
        assert len(lm._worker_logs.get("1", [])) == 0

    def test_parse_spawn_worker(self):
        lm = LoopManager()
        lm._parse_daemon_line("[SPAWN (worker #3)]")
        assert "3" in lm._worker_states
        assert lm._worker_states["3"]["status"] == "running"
        assert "3" in lm._worker_logs

    def test_parse_worker_completion(self):
        lm = LoopManager()
        lm._parse_daemon_line("[WORKER (worker #1)] Response in 42.5s (status=success)")
        assert "1" in lm._worker_states
        assert lm._worker_states["1"]["status"] == "success"
        assert lm._worker_states["1"]["duration_seconds"] == 42.5
        assert "completed_at" in lm._worker_states["1"]

    def test_parse_worker_completion_with_error_status(self):
        lm = LoopManager()
        lm._parse_daemon_line("[WORKER (worker #1)] Response in 5.0s (status=error)")
        assert lm._worker_states["1"]["status"] == "error"
        assert lm._worker_states["1"]["duration_seconds"] == 5.0


# ============================================================================
# Section 8: _parse_daemon_line — heartbeat, error-type, worker logs (5 tests)
# ============================================================================


class TestParseDaemonLineHeartbeatAndErrors:
    """Tests for heartbeat, error-type, and worker log tracking."""

    def test_parse_heartbeat(self):
        lm = LoopManager()
        lm._parse_daemon_line("[BEAT] Iteration 1 still running (30s)")
        assert lm._live_iteration.get("elapsed_seconds") == 30

    def test_parse_error_type(self):
        lm = LoopManager()
        lm._parse_daemon_line("[ERROR-TYPE] timeout")
        assert lm._live_iteration.get("error_type") == "timeout"

    def test_parse_error_type_multiple(self):
        lm = LoopManager()
        lm._parse_daemon_line("[ERROR-TYPE] network")
        assert lm._live_iteration.get("error_type") == "network"

    def test_worker_logs_trimmed_at_200(self):
        lm = LoopManager()
        lm._parse_daemon_line("[SPAWN (worker #0)]")
        for i in range(250):
            lm._parse_daemon_line(f"[STDOUT (worker #0)] line {i}")
        assert len(lm._worker_logs["0"]) == 200

    def test_worker_term_trimmed_at_1000(self):
        lm = LoopManager()
        for i in range(1100):
            lm._parse_daemon_line(f"[TERM (worker #0)] $ cmd_{i}")
        assert len(lm._worker_term["0"]) == 1000


# ============================================================================
# Section 9: _parse_daemon_line — max lengths and edge cases (4 tests)
# ============================================================================


class TestParseDaemonLineEdgeCases:
    """Edge cases for daemon line parsing."""

    def test_term_content_extraction_removes_prefix(self):
        lm = LoopManager()
        lm._parse_daemon_line("[TERM (worker #5)] $ echo hello")
        assert lm._worker_term["5"][0] == "$ echo hello"

    def test_term_content_with_content_containing_brackets(self):
        """Only the TERM prefix is stripped, not subsequent structured content."""
        lm = LoopManager()
        lm._parse_daemon_line("[TERM (worker #1)] [some other info] more text")
        assert lm._worker_term["1"][0] == "[some other info] more text"

    def test_workers_list_in_live_iteration_syncs(self):
        lm = LoopManager()
        lm._parse_daemon_line("[SPAWN (worker #0)]")
        lm._parse_daemon_line("[SPAWN (worker #1)]")
        assert len(lm._live_iteration.get("workers", [])) == 2
        worker_ids = {w["id"] for w in lm._live_iteration["workers"]}
        assert worker_ids == {"0", "1"}

    def test_model_prefix_also_detects_worker(self):
        lm = LoopManager()
        lm._parse_daemon_line("[MODEL (worker #2)] some model output")
        assert "2" in lm._worker_states
        assert "2" in lm._worker_logs
        assert "some model output" in lm._worker_logs["2"][-1]["message"]


# ============================================================================
# Section 10: get_loop_manager singleton (2 tests)
# ============================================================================


class TestGetLoopManager:
    """Tests for get_loop_manager() singleton."""

    def test_returns_loop_manager_instance(self):
        lm = get_loop_manager()
        assert isinstance(lm, LoopManager)

    def test_singleton_returns_same_instance(self):
        lm1 = get_loop_manager()
        lm2 = get_loop_manager()
        assert lm1 is lm2


# ============================================================================
# Section 11: _parse_daemon_line — generic worker fallback (2 tests)
# ============================================================================


class TestParseDaemonLineGenericFallback:
    """Tests for generic (worker #N) fallback when no structured prefix matches."""

    def test_generic_fallback_logs_to_existing_worker(self):
        """Generic (worker #N) lines get logged to existing worker's logs."""
        lm = LoopManager()
        # First, seed the worker via a structured prefix
        lm._parse_daemon_line("[STDOUT (worker #7)] initial message")
        assert "7" in lm._worker_logs
        assert len(lm._worker_logs["7"]) == 1
        # Now send a generic log line referencing worker #7
        lm._parse_daemon_line("Some random log (worker #7) more detail")
        # The generic fallback should match, and the log should be added
        assert len(lm._worker_logs["7"]) == 2
        assert "more detail" in lm._worker_logs["7"][-1]["message"]

    def test_generic_fallback_does_not_override_structured_prefix(self):
        """When a structured prefix matches, the generic fallback is not used."""
        lm = LoopManager()
        # Line with both structured prefix AND generic (worker #N)
        # The structured match should take precedence
        lm._parse_daemon_line("[STDOUT (worker #3)] Some (worker #5) content")
        assert "3" in lm._worker_states  # structured match
        # worker #5 is just content, not a worker ID
        assert "5" not in lm._worker_states


# ============================================================================
# Section 12: Integration — is_running with process (2 tests)
# ============================================================================


class TestIsRunningProperty:
    """Tests for is_running property edge cases."""

    def test_is_running_false_when_no_process(self):
        lm = LoopManager()
        lm._status = "running"
        lm._process = None
        assert lm.is_running is False

    def test_is_running_true_when_running_and_process_set(self):
        lm = LoopManager()
        lm._status = "running"
        mock_process = MagicMock()
        mock_process.pid = 12345
        lm._process = mock_process
        assert lm.is_running is True
