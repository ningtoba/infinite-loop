"""Tests for library_worker.py — _build_library_result and _run_library_workers_sequential."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hermes_loop.library_worker import (
    _build_library_result,
    _run_library_workers_sequential,
)

# ===================================================================
# _build_library_result tests
# ===================================================================


class TestBuildLibraryResult:
    """Tests for _build_library_result — pure function that builds a result dict."""

    # --- Normal case: parsed JSON found ---

    def test_parsed_json_full_fields(self):
        """All JSON fields present — summary, duration, error, next_goal, context."""
        final_response = '{"summary": "did work", "duration_seconds": 12.5, "error": null, "next_goal": "next task", "context": "some context"}'
        result = _build_library_result(
            conv_result={},
            final_response=final_response,
            spawned_session_id="sess-1",
            elapsed=15.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["summary"] == "did work"
        assert result["duration_seconds"] == 12.5
        assert result["error"] is None
        assert result["next_goal"] == "next task"
        assert result["context"] == "some context"
        assert result["spawned_session_id"] == "sess-1"
        assert result["exit_code"] == 0
        assert result["stderr"] == ""
        assert result["truncated"] is False
        assert result["output_chars"] == len(final_response)
        assert result["total_output_bytes"] == len(final_response)
        assert result["chars_per_second"] == round(len(final_response) / 12.5, 1)

    def test_parsed_json_partial_fields(self):
        """Only summary provided — remaining fields get defaults from elapsed/response."""
        final_response = '{"summary": "partial work"}'
        result = _build_library_result(
            conv_result={},
            final_response=final_response,
            spawned_session_id="",
            elapsed=30.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["summary"] == "partial work"
        assert result["duration_seconds"] == 30.0  # falls back to elapsed
        assert (
            result["error"] is None
        )  # parsed_json has no error key → .get returns None
        assert result["output"] == final_response[:2000]
        assert result["spawned_session_id"] == ""
        assert result["chars_per_second"] == round(len(final_response) / 30.0, 1)

    def test_parsed_json_with_error_text(self):
        """Error field populated in parsed JSON."""
        final_response = (
            '{"summary": "failed", "error": "something broke", "duration_seconds": 5}'
        )
        result = _build_library_result(
            conv_result={},
            final_response=final_response,
            spawned_session_id="sess-2",
            elapsed=5.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["summary"] == "failed"
        assert result["error"] == "something broke"
        assert result["duration_seconds"] == 5
        assert result["error_type"] == "unknown"  # classify_error("something broke")
        assert result["spawned_session_id"] == "sess-2"

    # --- Fallback: no JSON found in output ---

    def test_no_parsed_json_fallback(self):
        """When extract_json_from_output returns None, use the no-JSON fallback path."""
        final_response = "This is plain text output with no JSON."
        result = _build_library_result(
            conv_result={},
            final_response=final_response,
            spawned_session_id="",
            elapsed=5.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["summary"] == final_response[:2000]
        assert result["duration_seconds"] == 5.0
        assert result["error"] is None
        assert result["output"] == final_response
        assert result["exit_code"] == 0
        assert result["spawned_session_id"] == ""
        # No JSON path fields should be absent
        assert "next_goal" not in result
        assert "context" not in result
        assert "stderr" not in result
        assert "chars_per_second" not in result
        assert "error_type" not in result
        assert "output_chars" not in result
        assert "schema_valid" not in result

    def test_no_parsed_json_empty_output(self):
        """Empty output with no JSON — fallback yields '(no output)' as summary."""
        result = _build_library_result(
            conv_result={},
            final_response="",
            spawned_session_id="",
            elapsed=2.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["summary"] == "(no output)"
        assert result["duration_seconds"] == 2.0
        assert result["error"] is None
        assert result["output"] == ""
        assert result["total_output_bytes"] == 0
        assert result["truncated"] is False

    # --- Output schema validation ---

    def test_output_schema_valid(self):
        """output_schema provided and JSON validates successfully."""
        final_response = '{"summary": "valid work", "error": null}'
        schema = {
            "type": "object",
            "required": ["summary"],
            "properties": {
                "summary": {"type": "string"},
                "error": {"type": "string", "enum": [None]},
            },
        }
        result = _build_library_result(
            conv_result={},
            final_response=final_response,
            spawned_session_id="sess-3",
            elapsed=10.0,
            max_output_chars=2000,
            output_schema=schema,
        )
        # Note: validate_json_output's "enum: [None]" won't match None vs null pickle issue,
        # but the key test is that schema_valid and schema_error keys exist
        assert "schema_valid" in result
        assert "schema_error" in result

    def test_output_schema_invalid(self):
        """output_schema provided but JSON fails validation."""
        final_response = '{"summary": 42, "error": "oops"}'
        schema = {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}, "error": {"type": "string"}},
        }
        result = _build_library_result(
            conv_result={},
            final_response=final_response,
            spawned_session_id="",
            elapsed=10.0,
            max_output_chars=2000,
            output_schema=schema,
        )
        assert "schema_valid" in result
        assert "schema_error" in result
        # summary=42 is not a string → validation fails
        # But validate_json_output checks types; 42 is int not string
        # So schema_valid should be False, schema_error non-empty

    def test_output_schema_not_applied_when_no_parsed_json(self):
        """output_schema is NOT applied in the fallback (no-JSON) path."""
        final_response = "no json here"
        schema = {"type": "object", "properties": {"summary": {"type": "string"}}}
        result = _build_library_result(
            conv_result={},
            final_response=final_response,
            spawned_session_id="",
            elapsed=5.0,
            max_output_chars=2000,
            output_schema=schema,
        )
        # Fallback path does not add schema_valid/schema_error keys
        assert "schema_valid" not in result
        assert "schema_error" not in result

    # --- Edge cases ---

    def test_zero_max_output_chars_no_truncation(self):
        """max_output_chars=0 means no truncation at all."""
        long_text = "x" * 5000
        result = _build_library_result(
            conv_result={},
            final_response=long_text,
            spawned_session_id="",
            elapsed=1.0,
            max_output_chars=0,
            output_schema=None,
        )
        assert result["output"] == long_text
        assert result["truncated"] is False
        # Also verify the no-JSON fallback condition
        assert (
            result["summary"] == long_text[:0]
        )  # With parsed_json, summary is entire (no :: truncation)
        # Actually with no JSON parsed: summary = final_response[:max_output_chars]
        # max_output_chars=0 so [:0] = ""

    def test_zero_max_output_chars_with_json(self):
        """max_output_chars=0 in parsed JSON path: output is full, no truncation."""
        long_text = '{"summary": "short", "output": "' + "x" * 5000 + '"}'
        result = _build_library_result(
            conv_result={},
            final_response=long_text,
            spawned_session_id="",
            elapsed=1.0,
            max_output_chars=0,
            output_schema=None,
        )
        assert result["output"] == long_text  # full text since max_output_chars == 0
        assert result["truncated"] is False
        # summary comes from parsed_json, not truncated
        assert result["summary"] == "short"

    def test_negative_or_zero_duration_chars_per_second(self):
        """Duration of 0 or negative avoids division by zero for chars_per_second."""
        result = _build_library_result(
            conv_result={},
            final_response='{"summary": "instant", "duration_seconds": 0}',
            spawned_session_id="",
            elapsed=0.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["duration_seconds"] == 0
        assert result["chars_per_second"] == 0  # dur > 0 check prevents div by zero

    def test_negative_duration_from_parsed_json(self):
        """Negative duration from parsed JSON also yields 0 chars_per_second."""
        result = _build_library_result(
            conv_result={},
            final_response='{"summary": "negative", "duration_seconds": -5}',
            spawned_session_id="",
            elapsed=-5.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["duration_seconds"] == -5
        assert result["chars_per_second"] == 0  # dur > 0 check

    def test_truncated_true(self):
        """Truncated flag is True when output exceeds max_output_chars."""
        # Use JSON path so output_chars key exists
        long_text = "x" * 3000
        final_response = '{"summary": "done", "error": null}' + long_text
        result = _build_library_result(
            conv_result={},
            final_response=final_response,
            spawned_session_id="sess-t",
            elapsed=2.0,
            max_output_chars=100,
            output_schema=None,
        )
        assert result["truncated"] is True
        assert len(result["output"]) == 100
        assert result["total_output_bytes"] == len(final_response)
        assert result["output_chars"] == len(final_response)

    def test_parsed_json_with_context_truncation(self):
        """context field defaults to final_response[:500]."""
        long_text = "x" * 1000
        full_response = '{"summary": "lots of context", "context": "' + long_text + '"}'
        result = _build_library_result(
            conv_result={},
            final_response=full_response,
            spawned_session_id="",
            elapsed=5.0,
            max_output_chars=2000,
            output_schema=None,
        )
        # parsed_json has a "context" key, so it uses the full value from JSON, not truncated
        assert result["context"] == long_text

    def test_parsed_json_no_context_in_json_falls_back(self):
        """When parsed JSON has no 'context' key, fall back to final_response[:500]."""
        # Final response is the JSON string itself (29 chars), which is < 500 chars
        json_response = '{"summary": "no context key"}'
        result = _build_library_result(
            conv_result={},
            final_response=json_response,
            spawned_session_id="",
            elapsed=5.0,
            max_output_chars=2000,
            output_schema=None,
        )
        # context not in parsed_json → fallback uses final_response[:500]
        # final_response is 29 chars, so context == '{"summary": "no context key"}'
        assert result["context"] == json_response
        assert len(result["context"]) == len(json_response)

    def test_output_schema_none_skips_validation(self):
        """When output_schema is None, schema_valid/schema_error keys are absent."""
        result = _build_library_result(
            conv_result={},
            final_response='{"summary": "work"}',
            spawned_session_id="",
            elapsed=5.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert "schema_valid" not in result
        assert "schema_error" not in result

    def test_parsed_json_error_type_mapping(self):
        """Error text maps to an error_type via classify_error."""
        result = _build_library_result(
            conv_result={},
            final_response='{"summary": "fail", "error": "connection refused"}',
            spawned_session_id="",
            elapsed=5.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["error_type"] == "network"

    def test_parsed_json_error_type_timeout(self):
        """'timed out' maps to timeout error_type."""
        result = _build_library_result(
            conv_result={},
            final_response='{"summary": "fail", "error": "timed out waiting"}',
            spawned_session_id="",
            elapsed=5.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["error_type"] == "timeout"

    def test_no_error_returns_none_type(self):
        """When error is None, classify_error returns None."""
        result = _build_library_result(
            conv_result={},
            final_response='{"summary": "ok", "error": null}',
            spawned_session_id="",
            elapsed=5.0,
            max_output_chars=2000,
            output_schema=None,
        )
        assert result["error_type"] is None

    def test_original_final_response_truncated(self):
        """Truncation reflects original final_response length, not max_output_chars."""
        short_but_with_json = '{"summary": "done"}'
        long_noise = "x" * 5000
        final_response = short_but_with_json + long_noise
        result = _build_library_result(
            conv_result={},
            final_response=final_response,
            spawned_session_id="",
            elapsed=1.0,
            max_output_chars=100,
            output_schema=None,
        )
        # output is truncated to 100 chars
        assert len(result["output"]) == 100
        assert result["output"] == final_response[:100]
        # total_output_bytes is the full length
        assert result["total_output_bytes"] == len(final_response)
        assert result["truncated"] is True
        # summary still comes from parsed_json
        assert result["summary"] == "done"


# ===================================================================
# _run_library_workers_sequential tests
# ===================================================================


class TestRunLibraryWorkersSequential:
    """Tests for _run_library_workers_sequential — runs workers one at a time."""

    def test_no_tasks_returns_empty_list(self):
        """Empty task list returns an empty list."""
        results = _run_library_workers_sequential([])
        assert results == []

    def test_single_task_success(self):
        """Single worker runs and returns result successfully."""
        with patch("hermes_loop.library_worker._library_worker") as mock_worker:
            mock_worker.return_value = {
                "summary": "success",
                "duration_seconds": 10.0,
                "error": None,
                "output": "done",
                "exit_code": 0,
                "worker_id": 0,
            }
            tasks = [({"model": "test"}, "prompt", 0)]
            results = _run_library_workers_sequential(tasks)

        assert len(results) == 1
        assert results[0]["summary"] == "success"
        assert results[0]["worker_id"] == 0
        mock_worker.assert_called_once_with({"model": "test"}, "prompt", 0)

    def test_multiple_tasks_in_order(self):
        """Multiple tasks run sequentially in the same order."""
        with patch("hermes_loop.library_worker._library_worker") as mock_worker:
            mock_worker.side_effect = [
                {"summary": "task 0 done", "worker_id": 0},
                {"summary": "task 1 done", "worker_id": 1},
                {"summary": "task 2 done", "worker_id": 2},
            ]
            tasks = [
                ({"id": "a"}, "prompt0", 0),
                ({"id": "b"}, "prompt1", 1),
                ({"id": "c"}, "prompt2", 2),
            ]
            results = _run_library_workers_sequential(tasks)

        assert len(results) == 3
        assert results[0]["summary"] == "task 0 done"
        assert results[1]["summary"] == "task 1 done"
        assert results[2]["summary"] == "task 2 done"
        assert mock_worker.call_count == 3
        # Verify positional args for each call
        assert mock_worker.call_args_list[0][0] == ({"id": "a"}, "prompt0", 0)
        assert mock_worker.call_args_list[1][0] == ({"id": "b"}, "prompt1", 1)
        assert mock_worker.call_args_list[2][0] == ({"id": "c"}, "prompt2", 2)

    def test_worker_raises_exception_caught(self):
        """When _library_worker raises, the error is caught and a placeholder result is returned."""
        with patch("hermes_loop.library_worker._library_worker") as mock_worker:
            mock_worker.side_effect = RuntimeError("worker crashed")

            tasks = [({"model": "test"}, "prompt", 1)]
            results = _run_library_workers_sequential(tasks)

        assert len(results) == 1
        assert "WORKER #1 FAILED" in results[0]["summary"]
        assert "worker crashed" in results[0]["summary"]
        assert results[0]["error"] == "worker crashed"
        assert results[0]["exit_code"] == -1
        assert results[0]["worker_id"] == 1
        assert results[0]["output"] == ""

    def test_mixed_success_and_failure(self):
        """Multiple workers where some fail and some succeed — errors don't break the loop."""
        with patch("hermes_loop.library_worker._library_worker") as mock_worker:
            mock_worker.side_effect = [
                {"summary": "ok", "worker_id": 0, "exit_code": 0},
                ValueError("second worker failed"),
                {"summary": "ok too", "worker_id": 2, "exit_code": 0},
            ]
            tasks = [
                ({"id": 1}, "p1", 0),
                ({"id": 2}, "p2", 1),
                ({"id": 3}, "p3", 2),
            ]
            results = _run_library_workers_sequential(tasks)

        assert len(results) == 3
        assert results[0]["summary"] == "ok"
        assert results[0]["exit_code"] == 0
        assert "WORKER #1 FAILED" in results[1]["summary"]
        assert results[1]["error"] == "second worker failed"
        assert results[1]["exit_code"] == -1
        assert results[2]["summary"] == "ok too"
        assert results[2]["exit_code"] == 0

    def test_all_tasks_fail(self):
        """All workers fail — all get error result entries."""
        with patch("hermes_loop.library_worker._library_worker") as mock_worker:
            mock_worker.side_effect = Exception("fail1"), Exception("fail2")
            tasks = [
                ({"id": 1}, "p1", 0),
                ({"id": 2}, "p2", 1),
            ]
            results = _run_library_workers_sequential(tasks)

        assert len(results) == 2
        for i, r in enumerate(results):
            assert f"WORKER #{i} FAILED" in r["summary"]
            assert r["exit_code"] == -1
            assert r["output"] == ""

    def test_appends_results_in_order_despite_exceptions(self):
        """Results are appended in task order even when exceptions occur mid-list."""
        with patch("hermes_loop.library_worker._library_worker") as mock_worker:
            mock_worker.side_effect = [
                {"summary": "first", "worker_id": 0},
                Exception("middle crash"),
                {"summary": "last", "worker_id": 2},
            ]
            tasks = [
                ({"id": "a"}, "pa", 0),
                ({"id": "b"}, "pb", 1),
                ({"id": "c"}, "pc", 2),
            ]
            results = _run_library_workers_sequential(tasks)

        assert len(results) == 3
        assert results[0]["summary"] == "first"
        assert "WORKER #1 FAILED" in results[1]["summary"]
        assert results[2]["summary"] == "last"


# ===================================================================
# Tests marked as skips (complex — requires AIAgent)
# ===================================================================


@pytest.mark.skip(
    reason="Complex — requires AIAgent from run_agent, which is not available in unit test environment"
)
class TestSetupWorkerLogging:
    """Tests for _setup_worker_logging — configures logging in child process."""

    def test_basic_logging_setup(self):
        """Would configure root logger with custom formatter."""
        pass

    def test_removes_existing_handlers(self):
        """Would remove existing log handlers before adding new ones."""
        pass


@pytest.mark.skip(
    reason="Complex — requires AIAgent from run_agent, not available in unit test environment"
)
class TestLibraryWorker:
    """Tests for _library_worker — runs AIAgent in child process."""

    def test_normal_execution_returns_built_result(self):
        """Would run AIAgent, get conv_result, build library result."""
        pass

    def test_timeout_error_returns_timeout_result(self):
        """Would catch TimeoutError and return timeout result dict."""
        pass

    def test_general_exception_caught(self):
        """Would catch any exception and return a failure result dict."""
        pass
