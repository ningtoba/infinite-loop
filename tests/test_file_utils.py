"""Tests for file_utils.py — ledger I/O, JSON extraction, sentinel checks, status file."""

from __future__ import annotations

import json
import os
from unittest.mock import patch


from hermes_loop.file_utils import (
    extract_json_from_output,
    read_ledger,
    write_ledger,
    write_status_file,
    check_sentinel,
    check_sentinel_no_remove,
    _colorize_log_tags,
    _log,
    _init_daemon_log,
)

# ---------------------------------------------------------------------------
# extract_json_from_output tests
# ---------------------------------------------------------------------------


class TestExtractJsonFromOutput:
    """Comprehensive tests for extract_json_from_output."""

    def test_single_line_json(self):
        """Basic single-line JSON extraction."""
        result = extract_json_from_output('{"summary": "hello", "error": null}')
        assert result is not None
        assert result["summary"] == "hello"
        assert result["error"] is None

    def test_multi_line_json(self):
        """Multi-line JSON extraction."""
        result = extract_json_from_output('{\n"summary": "hello",\n"error": null\n}')
        assert result is not None
        assert result["summary"] == "hello"

    def test_code_fence_json(self):
        """JSON inside markdown code fence."""
        result = extract_json_from_output(
            '```json\n{"summary": "hello", "error": null}\n```'
        )
        assert result is not None
        assert result["summary"] == "hello"

    def test_session_noise_prefix(self):
        """JSON with session_id noise lines before it."""
        result = extract_json_from_output(
            'session_id: abc-123\n{"summary": "hello", "error": null}'
        )
        assert result is not None
        assert result["summary"] == "hello"

    def test_empty_string(self):
        """Empty string returns None."""
        assert extract_json_from_output("") is None

    def test_none_input(self):
        """None input returns None."""
        assert extract_json_from_output(None) is None

    def test_no_json_in_output(self):
        """Plain text with no JSON returns None."""
        assert extract_json_from_output("just some text") is None

    def test_last_json_object_wins(self):
        """When multiple JSON objects exist, return the last valid one."""
        result = extract_json_from_output(
            '{"summary": "first"}\n{"summary": "second", "value": 42}'
        )
        assert result is not None
        assert result["summary"] == "second"
        assert result["value"] == 42

    def test_inner_json_ignored(self):
        """Correctly handles nested JSON-like patterns and braces in text."""
        result = extract_json_from_output(
            'text with {braces} then {"summary": "valid", "nested": {"a": 1}} ok'
        )
        assert result is not None
        assert result["summary"] == "valid"
        assert result["nested"]["a"] == 1

    def test_only_brackets_text(self):
        """Text with braces but not valid JSON."""
        result = extract_json_from_output("just {some} braces")
        assert result is None

    def test_truncated_json(self):
        """Incomplete/unclosed JSON returns None."""
        result = extract_json_from_output('{"summary": "hello"')
        assert result is None

    def test_multiple_session_lines(self):
        """Multiple session_id lines and trailing text."""
        result = extract_json_from_output(
            "session_id: aaa\nsession_id: bbb\n"
            '```json\n{"done": true, "count": 3}\n```\n'
            "session_id: ccc"
        )
        assert result is not None
        assert result["done"] is True
        assert result["count"] == 3

    def test_nested_json_with_escaped_chars(self):
        """Nested JSON with escaped characters."""
        result = extract_json_from_output(
            '{"summary": "hello\\nworld", "data": {"key": "val"}}'
        )
        assert result is not None
        assert result["summary"] == "hello\nworld"
        assert result["data"]["key"] == "val"

    def test_json_with_arrays(self):
        """JSON containing arrays."""
        result = extract_json_from_output('{"items": [1, 2, 3], "names": ["a", "b"]}')
        assert result is not None
        assert result["items"] == [1, 2, 3]

    def test_malformed_json_before_valid(self):
        """Malformed JSON followed by valid JSON returns valid one."""
        result = extract_json_from_output('{"bad} trailing\n{"summary": "valid"}')
        assert result is not None
        assert result["summary"] == "valid"

    def test_whitespace_only(self):
        """Whitespace-only input returns None."""
        assert extract_json_from_output("   \n  \t  ") is None

    def test_json_with_unicode(self):
        """Unicode characters in JSON."""
        result = extract_json_from_output('{"summary": "héllo wörld", "error": null}')
        assert result is not None
        assert result["summary"] == "héllo wörld"

    def test_log_line_around_json(self):
        """JSON embedded in log-like output (simulating real chat -q)."""
        result = extract_json_from_output(
            '[12:34:56] [OUTPUT] {"summary": "done", "error": null}'
        )
        assert result is not None
        assert result["summary"] == "done"

    def test_empty_object(self):
        """Empty JSON object {} is valid."""
        result = extract_json_from_output("{}")
        assert result is not None
        assert result == {}

    def test_boolean_and_null(self):
        """Boolean values and null handling."""
        result = extract_json_from_output('{"active": true, "data": null, "count": 0}')
        assert result is not None
        assert result["active"] is True
        assert result["data"] is None
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# write_ledger / read_ledger tests
# ---------------------------------------------------------------------------


class TestLedgerIO:
    """Tests for write_ledger and read_ledger with patched paths."""

    def test_write_and_read_ledger(self, temp_ledger_dir, ledger_data):
        """Write then read back a ledger file."""
        ledger_path = temp_ledger_dir / "test-ledger.json"
        lock_path = temp_ledger_dir / "test-ledger.lock"

        with (
            patch("hermes_loop.file_utils.LEDGER_PATH", str(ledger_path)),
            patch("hermes_loop.file_utils.LOCK_PATH", str(lock_path)),
        ):
            write_ledger(ledger_data)
            result = read_ledger()

        assert result is not None
        assert result["total_iterations"] == 3
        assert len(result["iterations"]) == 3
        assert result["iterations"][1]["error"] == "timeout"
        assert result["goals_completed"]["abc123"]["status"] == "completed"
        assert result["stats"]["success_count"] == 2

    def test_read_nonexistent_ledger(self, temp_ledger_dir):
        """Reading non-existent ledger returns None."""
        ledger_path = temp_ledger_dir / "nonexistent.json"
        lock_path = temp_ledger_dir / "nonexistent.lock"

        with (
            patch("hermes_loop.file_utils.LEDGER_PATH", str(ledger_path)),
            patch("hermes_loop.file_utils.LOCK_PATH", str(lock_path)),
        ):
            result = read_ledger()

        assert result is None

    def test_write_creates_directory(self, temp_ledger_dir, ledger_data):
        """write_ledger creates parent directories if they don't exist."""
        nested = temp_ledger_dir / "subdir" / "nested" / "ledger.json"
        lock_path = temp_ledger_dir / "lock"

        with (
            patch("hermes_loop.file_utils.LEDGER_PATH", str(nested)),
            patch("hermes_loop.file_utils.LOCK_PATH", str(lock_path)),
        ):
            write_ledger(ledger_data)
            assert nested.exists()
            result = read_ledger()
            assert result is not None
            assert result["total_iterations"] == 3

    def test_write_is_atomic(self, temp_ledger_dir, ledger_data):
        """Write uses atomic temp-file + replace pattern."""
        ledger_path = temp_ledger_dir / "atomic-ledger.json"
        lock_path = temp_ledger_dir / "atomic-ledger.lock"
        tmp_path = temp_ledger_dir / "atomic-ledger.json.tmp"

        with (
            patch("hermes_loop.file_utils.LEDGER_PATH", str(ledger_path)),
            patch("hermes_loop.file_utils.LOCK_PATH", str(lock_path)),
        ):
            write_ledger(ledger_data)
            # Temp file should not exist after write
            assert not tmp_path.exists()
            # Real file should exist
            assert ledger_path.exists()

    def test_corrupted_ledger_returns_none(self, temp_ledger_dir):
        """Read from a corrupted JSON file returns None."""
        ledger_path = temp_ledger_dir / "corrupted.json"
        lock_path = temp_ledger_dir / "corrupted.lock"
        ledger_path.write_text("{this is not valid json}")

        with (
            patch("hermes_loop.file_utils.LEDGER_PATH", str(ledger_path)),
            patch("hermes_loop.file_utils.LOCK_PATH", str(lock_path)),
        ):
            result = read_ledger()
        assert result is None

    def test_write_with_unserializable_types(self, temp_ledger_dir):
        """Non-serializable types use default=str serialization."""
        from datetime import datetime, timezone

        ledger_path = temp_ledger_dir / "unserial.json"
        lock_path = temp_ledger_dir / "unserial.lock"
        data = {
            "name": "test",
            "timestamp": datetime.now(timezone.utc),
            "iterations": [],
        }

        with (
            patch("hermes_loop.file_utils.LEDGER_PATH", str(ledger_path)),
            patch("hermes_loop.file_utils.LOCK_PATH", str(lock_path)),
        ):
            write_ledger(data)
            result = read_ledger()
        assert result is not None
        assert result["name"] == "test"
        assert isinstance(result["timestamp"], str)  # serialized via default=str


# ---------------------------------------------------------------------------
# write_status_file tests
# ---------------------------------------------------------------------------


class TestWriteStatusFile:
    """Tests for write_status_file."""

    def test_basic_status_write(self, temp_ledger_dir):
        """Write a basic status file with iteration info."""
        status_path = temp_ledger_dir / "status.json"
        state = {
            "total_iterations": 10,
            "stats": {"total_duration_seconds": 300},
        }

        write_status_file(str(status_path), state, iteration=5, status="running")
        assert status_path.exists()

        with open(status_path) as f:
            data = json.loads(f.read())

        assert data["pid"] > 0
        assert data["iteration"] == 5
        assert data["status"] == "running"
        assert data["total_iterations"] == 10
        assert data["total_duration_seconds"] == 300
        assert "last_updated" in data
        assert "T" in data["last_updated"]  # ISO format

    def test_empty_status_path(self):
        """Empty status_path is a no-op."""
        write_status_file("", {"total_iterations": 0}, iteration=1, status="paused")
        # Should not raise

    def test_status_with_paused(self, temp_ledger_dir):
        """Status file with paused status."""
        status_path = temp_ledger_dir / "paused.json"
        write_status_file(
            str(status_path),
            {"total_iterations": 5, "stats": {}},
            iteration=3,
            status="paused",
        )
        with open(status_path) as f:
            data = json.loads(f.read())
        assert data["status"] == "paused"
        assert data["iteration"] == 3

    def test_invalid_path_does_not_crash(self):
        """Invalid path is handled gracefully (logged, not raised)."""
        write_status_file("/nonexistent/path/status.json", {}, iteration=0)
        # Should not crash


# ---------------------------------------------------------------------------
# Sentinel tests
# ---------------------------------------------------------------------------


class TestSentinel:
    """Tests for check_sentinel and check_sentinel_no_remove."""

    def test_basic_sentinel(self, temp_ledger_dir):
        """Read sentinel file, file is removed after reading."""
        sentinel_path = temp_ledger_dir / "sentinel"
        sentinel_path.write_text("stop")

        result = check_sentinel(str(sentinel_path))
        assert result == "stop"
        assert not sentinel_path.exists()

    def test_sentinel_no_remove(self, temp_ledger_dir):
        """Read sentinel without removing."""
        sentinel_path = temp_ledger_dir / "pause-sentinel"
        sentinel_path.write_text("pause")

        result = check_sentinel_no_remove(str(sentinel_path))
        assert result == "pause"
        assert sentinel_path.exists()

    def test_nonexistent_sentinel(self):
        """Non-existent sentinel returns None."""
        assert check_sentinel("/nonexistent/sentinel") is None

    def test_sentinel_with_whitespace(self, temp_ledger_dir):
        """Sentinel content is stripped of whitespace."""
        sentinel_path = temp_ledger_dir / "whitespace-sentinel"
        sentinel_path.write_text("  resume  \n")

        result = check_sentinel(str(sentinel_path))
        assert result == "resume"
        assert not sentinel_path.exists()

    def test_none_path_sentinel(self):
        """None path for sentinel returns None."""
        assert check_sentinel(None) is None
        assert check_sentinel_no_remove(None) is None

    def test_empty_path_sentinel(self):
        """Empty string path returns None."""
        assert check_sentinel("") is None
        assert check_sentinel_no_remove("") is None


# ---------------------------------------------------------------------------
# _colorize_log_tags tests
# ---------------------------------------------------------------------------


class TestColorizeLogTags:
    """Tests for _colorize_log_tags."""

    def test_no_color_no_change(self):
        """When color is disabled, message is unchanged."""
        with patch("hermes_loop.color_utils.colorizer._enabled", return_value=False):
            result = _colorize_log_tags("[INFO] test message")
        assert result == "[INFO] test message"

    def test_known_tag_colored(self):
        """Known tags are colored when color is enabled."""
        with (
            patch("hermes_loop.color_utils.colorizer._enabled", return_value=True),
            patch(
                "hermes_loop.color_utils.colorizer.warn", return_value="[COLORED-WARN]"
            ),
        ):
            result = _colorize_log_tags("[WARN] something")
        assert "[COLORED-WARN]" in result or "[WARN]" not in result

    def test_unknown_tag_preserved(self):
        """Unknown tags are left untouched."""
        with (
            patch("hermes_loop.color_utils.colorizer._enabled", return_value=True),
            patch("hermes_loop.color_utils.colorizer.ok", return_value="[OK]"),
        ):
            result = _colorize_log_tags("[CUSTOM-TAG] hello")
        assert "[CUSTOM-TAG]" in result

    def test_multiple_tags(self):
        """Multiple known tags in one message."""
        with (
            patch("hermes_loop.color_utils.colorizer._enabled", return_value=True),
            patch(
                "hermes_loop.color_utils.colorizer.warn",
                side_effect=lambda s: f"**{s}**",
            ),
            patch(
                "hermes_loop.color_utils.colorizer.dim",
                side_effect=lambda s: f"~~{s}~~",
            ),
        ):
            result = _colorize_log_tags("[WARN] [BEAT] test")
        assert "**" in result or "~~" in result


# ---------------------------------------------------------------------------
# _log and _init_daemon_log tests
# ---------------------------------------------------------------------------


class TestLogging:
    """Tests for _log and _init_daemon_log."""

    def test_log_basic(self, capsys):
        """_log prints timestamped message to stdout."""
        _log("hello world", level="INFO")
        captured = capsys.readouterr()
        assert "hello world" in captured.out
        # Should have a timestamp prefix like [HH:MM:SS]
        assert captured.out.startswith("[")

    def test_log_different_levels(self, capsys):
        """_log with WARN/ERROR levels still prints."""
        _log("warning message", level="WARN")
        _log("error message", level="ERROR")
        captured = capsys.readouterr()
        assert "warning message" in captured.out
        assert "error message" in captured.out

    def test_init_daemon_log(self, temp_ledger_dir):
        """_init_daemon_log creates log file and returns logger."""
        log_file = str(temp_ledger_dir / "daemon.log")
        logger = _init_daemon_log(log_file, max_mb=5)
        assert logger is not None
        assert logger.name == "infinite-loop"
        assert os.path.exists(log_file)

    def test_init_daemon_log_creates_dir(self, temp_ledger_dir):
        """_init_daemon_log creates parent directory."""
        nested = temp_ledger_dir / "logs" / "subdir" / "daemon.log"
        logger = _init_daemon_log(str(nested), max_mb=5)
        assert logger is not None
        assert os.path.exists(nested)
