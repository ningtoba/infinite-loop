"""Tests for pi_loop.file_utils — file locking, logging, ledger I/O, and sentinel checks."""

import json
import logging
from unittest.mock import patch

import pytest

from pi_loop.file_utils import (
    FileLock,
    _colorize_log_tags,
    _init_daemon_log,
    _init_logger,
    _log,
    check_sentinel,
    check_sentinel_no_remove,
    extract_json_from_output,
    read_ledger,
    write_ledger,
    write_status_file,
)


class TestFileLock:
    def test_acquire_and_release(self, tmp_path):
        """FileLock acquires and releases a lock."""
        lock_path = str(tmp_path / "test.lock")
        with FileLock(lock_path, timeout=2.0) as lock:
            assert lock._fd is not None
        assert lock._fd is None  # Released after exit

    def test_timeout_raises(self, tmp_path):
        """FileLock raises TimeoutError when lock cannot be acquired."""
        lock_path = str(tmp_path / "test.lock")
        # Acquire the lock first
        fd = __import__("os").open(lock_path, __import__("os").O_CREAT | __import__("os").O_RDWR, 0o644)
        try:
            # Lock it
            __import__("fcntl").flock(fd, __import__("fcntl").LOCK_EX)
            # Try to acquire with short timeout
            with pytest.raises(TimeoutError), FileLock(lock_path, timeout=0.1):
                pass
        finally:
            __import__("fcntl").flock(fd, __import__("fcntl").LOCK_UN)
            __import__("os").close(fd)


class TestColorizeLogTags:
    def test_no_color_returns_original(self):
        """_colorize_log_tags returns original when color disabled."""
        with patch("pi_loop.file_utils._cu._enabled", return_value=False):
            result = _colorize_log_tags("[ERROR] something failed")
        assert result == "[ERROR] something failed"

    def test_color_on_returns_colored(self):
        """_colorize_log_tags returns modified when color enabled."""
        with patch("pi_loop.file_utils._cu._enabled", return_value=True):
            for tag in ("[ERROR]", "[WARN]", "[OK]", "[BEAT]", "[DAEMON]"):
                # Just verify it doesn't crash and returns a string
                result = _colorize_log_tags(f"{tag} something")
                assert isinstance(result, str)
                assert f"{tag}" in result or tag in result


class TestLog:
    def test_logs_to_stdout(self, capsys):
        """_log prints to stdout."""
        _log("test message", level="INFO")
        captured = capsys.readouterr()
        assert "test message" in captured.out

    def test_log_level_debug(self, capsys):
        """_log handles DEBUG level."""
        _log("debug msg", level="DEBUG")
        captured = capsys.readouterr()
        assert "debug msg" in captured.out


class TestInitLogger:
    def test_returns_logger(self, tmp_path):
        """_init_logger returns a configured Logger."""
        log_file = str(tmp_path / "test.log")
        logger = _init_logger(log_file, max_mb=5)
        assert isinstance(logger, logging.Logger)
        assert logger.level == logging.DEBUG

    def test_writes_to_file(self, tmp_path):
        """_init_logger writes log messages to file."""
        log_file = str(tmp_path / "test.log")
        logger = _init_logger(log_file, max_mb=5)
        logger.info("write me")
        logger.handlers[0].flush()
        content = open(log_file).read()
        assert "write me" in content


class TestInitDaemonLog:
    def test_initializes_global(self, tmp_path):
        """_init_daemon_log initializes the module-level logger."""
        log_file = str(tmp_path / "daemon.log")
        import pi_loop.file_utils

        _init_daemon_log(log_file, max_mb=5)
        assert pi_loop.file_utils._daemon_logger is not None


class TestWriteLedger:
    def test_writes_state(self, tmp_path):
        """write_ledger writes state to LEDGER_PATH."""
        state = {"iterations": [], "status": "running"}
        with patch("pi_loop.file_utils.LEDGER_PATH", str(tmp_path / "ledger.json")):
            with patch("pi_loop.file_utils.FileLock"):
                write_ledger(state)
                ledger_file = tmp_path / "ledger.json"
                assert ledger_file.exists()
                data = json.loads(ledger_file.read_text())
                assert data["status"] == "running"


class TestReadLedger:
    def test_reads_existing(self, tmp_path):
        """read_ledger reads an existing ledger file."""
        ledger_path = tmp_path / "ledger.json"
        ledger_path.write_text(json.dumps({"status": "running"}))
        with patch("pi_loop.file_utils.LEDGER_PATH", str(ledger_path)), patch("pi_loop.file_utils.FileLock"):
            data = read_ledger()
        assert data is not None
        assert data["status"] == "running"

    def test_nonexistent(self, tmp_path):
        """read_ledger returns None when file doesn't exist."""
        with patch("pi_loop.file_utils.LEDGER_PATH", str(tmp_path / "nonexistent.json")):
            result = read_ledger()
        assert result is None

    def test_invalid_json(self, tmp_path):
        """read_ledger returns None for invalid JSON."""
        ledger_path = tmp_path / "ledger.json"
        ledger_path.write_text("invalid json")
        with patch("pi_loop.file_utils.LEDGER_PATH", str(ledger_path)), patch("pi_loop.file_utils.FileLock"):
            data = read_ledger()
        assert data is None


class TestWriteStatusFile:
    def test_writes_file(self, tmp_path):
        """write_status_file writes a JSON status line."""
        status_path = str(tmp_path / "status.json")
        state = {"total_iterations": 5, "stats": {"total_duration_seconds": 30.0}}
        with patch("pi_loop.file_utils.os.getpid", return_value=12345):
            write_status_file(status_path, state, iteration=3, status="running")
        data = json.loads((tmp_path / "status.json").read_text())
        assert data["pid"] == 12345
        assert data["iteration"] == 3
        assert data["status"] == "running"
        assert data["total_iterations"] == 5

    def test_empty_path_does_nothing(self):
        """write_status_file with empty path does nothing."""
        with patch("builtins.open") as mock_open:
            write_status_file("", {}, iteration=0, status="running")
        mock_open.assert_not_called()

    def test_error_logged(self):
        """write_status_file logs on OSError."""
        with patch("pi_loop.file_utils._log") as mock_log:
            with patch("builtins.open", side_effect=OSError("permission denied")):
                write_status_file("/nonexistent/status.json", {}, iteration=0)
        # Check an error was logged (at least one call about the failure)
        assert mock_log.call_count > 0


class TestCheckSentinel:
    def test_present_and_removes(self, tmp_path):
        """check_sentinel reads content and removes the file."""
        sentinel = tmp_path / "sentinel"
        sentinel.write_text("stop")
        content = check_sentinel(str(sentinel))
        assert content == "stop"
        assert not sentinel.exists()

    def test_absent(self):
        """check_sentinel returns None when file doesn't exist."""
        content = check_sentinel("/nonexistent")
        assert content is None


class TestCheckSentinelNoRemove:
    def test_reads_without_removing(self, tmp_path):
        """check_sentinel_no_remove reads content without removing the file."""
        sentinel = tmp_path / "sentinel"
        sentinel.write_text("pause")
        content = check_sentinel_no_remove(str(sentinel))
        assert content == "pause"
        assert sentinel.exists()

    def test_absent(self):
        """check_sentinel_no_remove returns None when file doesn't exist."""
        content = check_sentinel_no_remove("/nonexistent")
        assert content is None


class TestExtractJsonFromOutput:
    def test_extracts_last_json_object(self):
        """extract_json_from_output finds the last JSON object."""
        output = 'prefix text {"key": "value1"} suffix {"nested": {"a": 1}} more'
        result = extract_json_from_output(output)
        assert result is not None
        assert result["nested"]["a"] == 1

    def test_single_json(self):
        """extract_json_from_output extracts single JSON object."""
        result = extract_json_from_output('{"status": "ok"}')
        assert result is not None
        assert result["status"] == "ok"

    def test_no_json(self):
        """extract_json_from_output returns None when no JSON found."""
        result = extract_json_from_output("just plain text without json")
        assert result is None

    def test_empty_output(self):
        """extract_json_from_output returns None for empty string."""
        result = extract_json_from_output("")
        assert result is None

    def test_strips_session_id_lines(self):
        """extract_json_from_output strips 'session_id:' lines."""
        output = 'session_id: abc123\n{"result": "good"}'
        result = extract_json_from_output(output)
        assert result is not None
        assert result["result"] == "good"

    def test_nested_json(self):
        """extract_json_from_output handles deeply nested objects."""
        output = '{"level1": {"level2": {"level3": {"value": 42}}}}'
        result = extract_json_from_output(output)
        assert result["level1"]["level2"]["level3"]["value"] == 42

    def test_malformed_json_returns_last_valid(self):
        """extract_json_from_output returns last valid JSON if multiple present."""
        output = '{"valid": 1} some garbage {"valid": 2}'
        result = extract_json_from_output(output)
        assert result["valid"] == 2

    def test_broken_json_returns_none(self):
        """extract_json_from_output returns None for broken JSON."""
        result = extract_json_from_output('{"key": "value"')
        assert result is None
