#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# mock_omp.sh — A realistic mock of the `omp` binary for integration tests.
#
# Emits NDJSON on stdout matching the event stream that omp_loop/loop.py's
# _execute_task() function parses:
#
#   - message_update (text_delta, content_block_start, content_block_stop, usage)
#   - message_end    (final assistant text)
#
# Supports environment variable overrides to simulate various scenarios:
#
#   MOCK_OMP_EXIT_CODE     Exit code (default: 0)
#   MOCK_OMP_DELAY_S       Simulated processing delay (default: 0.1)
#   MOCK_OMP_OUTPUT_TEXT   Text content of the final assistant response
#   MOCK_OMP_LINE_PREFIX   Per-line text_delta content (default: "[mock]")
#   MOCK_OMP_LINE_COUNT    Number of text_delta lines (default: 2)
#   MOCK_OMP_TOOL_COUNT    Number of tool call/result pairs (default: 0)
#   MOCK_OMP_DISABLE_END   If set (any value), skips the message_end event
#   MOCK_OMP_END_ON_STDERR Emits the NDJSON to stderr instead of stdout
#   MOCK_OMP_STDERR_LINE   Print this text to stderr (simulates warnings/errors)
#   MOCK_OMP_NO_STDOUT     If set, do NOT write any NDJSON events to stdout
# ---------------------------------------------------------------------------
set -euo pipefail

# ---- Parse arguments --------------------------------------------------------
goal=""
while [[ $# -gt 0 ]]; do
	case "$1" in
	-a | --approve)
		shift
		;;
	--mode)
		# Consume the mode value (e.g. "json")
		if [[ -n "${2:-}" ]] && [[ "${2:0:1}" != "-" ]]; then
			shift 2
		else
			shift
		fi
		;;
	-q)
		# omp -q "goal" syntax
		if [[ -n "${2:-}" ]]; then
			goal="$2"
			shift 2
		else
			shift
		fi
		;;
	--goal)
		# omp --goal "..." (alternative)
		if [[ -n "${2:-}" ]]; then
			goal="$2"
			shift 2
		else
			shift
		fi
		;;
	-*)
		# Skip any other flags
		shift
		;;
	*)
		# First positional argument is the goal
		if [[ -z "$goal" ]]; then
			goal="$1"
		fi
		shift
		;;
	esac
done

# ---- Environment overrides with defaults ------------------------------------
exit_code="${MOCK_OMP_EXIT_CODE:-0}"
delay_s="${MOCK_OMP_DELAY_S:-0.1}"
output_text="${MOCK_OMP_OUTPUT_TEXT:-}"
line_prefix="${MOCK_OMP_LINE_PREFIX:-[mock]}"
line_count="${MOCK_OMP_LINE_COUNT:-2}"
tool_count="${MOCK_OMP_TOOL_COUNT:-0}"
disable_end="${MOCK_OMP_DISABLE_END:-}"
use_stderr="${MOCK_OMP_END_ON_STDERR:-}"
stderr_line="${MOCK_OMP_STDERR_LINE:-}"
no_stdout="${MOCK_OMP_NO_STDOUT:-}"

# Default output text when MOCK_OMP_OUTPUT_TEXT is unset
if [[ -z "$output_text" ]]; then
	output_text="Mock run completed for goal: ${goal:-unspecified}"
fi

# ---- Helper: write one NDJSON line (to stdout, or stderr if use_stderr set) --
_emit() {
	local json="$1"
	if [[ -n "$use_stderr" ]]; then
		echo "$json" >&2
	else
		echo "$json"
	fi
}

# ---- Simulated delay ---------------------------------------------------------
if [[ "$delay_s" != "0" ]]; then
	sleep "$delay_s"
fi

# ---- Optional stderr line (e.g. warnings, diagnostics) ----------------------
if [[ -n "$stderr_line" ]]; then
	echo "$stderr_line" >&2
fi

# ---- Emit NDJSON event stream -----------------------------------------------
if [[ -z "$no_stdout" ]]; then
	# 1. Text delta events (accumulated into terminal output)
	for ((i = 1; i <= line_count; i++)); do
		_emit "{\"type\":\"message_update\",\"assistantMessageEvent\":{\"type\":\"text_delta\",\"delta\":\"${line_prefix} line ${i}\\n\"}}"
	done

	# 2. Tool call/result pairs (if requested)
	for ((t = 1; t <= tool_count; t++)); do
		# content_block_start — tool_use
		_emit "{\"type\":\"message_update\",\"assistantMessageEvent\":{\"type\":\"content_block_start\",\"delta\":{\"type\":\"tool_use\",\"name\":\"mock_tool_${t}\",\"input\":{\"query\":\"mock query ${t}\"}}}}"
		# content_block_stop — tool_result
		_emit "{\"type\":\"message_update\",\"assistantMessageEvent\":{\"type\":\"content_block_stop\",\"delta\":{\"type\":\"tool_result\",\"content\":\"[Mock result ${t}]\"}}}"
	done

	# 3. Usage event (token consumption metadata)
	_emit "{\"type\":\"message_update\",\"assistantMessageEvent\":{\"type\":\"usage\",\"usage\":{\"totalTokens\":150,\"cost\":{\"total\":\"0.003\"}}}}"

	# 4. Final message_end with the full assistant response
	if [[ -z "$disable_end" ]]; then
		_emit "{\"type\":\"message_end\",\"message\":{\"content\":[{\"type\":\"text\",\"text\":\"${output_text}\"}]}}"
	fi
fi

# ---- Exit -------------------------------------------------------------------
exit "$exit_code"
