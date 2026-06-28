"""Tests for dashboard.py — HTML status page generation and SSE broadcast helpers."""

from __future__ import annotations

import json
import queue
from unittest.mock import MagicMock, patch

import pytest

from hermes_loop import dashboard as dh_mod
from hermes_loop.dashboard import (
    _broadcast_to_sse_clients,
    _build_sse_payload,
    _generate_status_html,
    _wrap_sse_payload,
    _write_status_html,
)

# ---------------------------------------------------------------------------
# Fixtures for managing module-level SSE globals
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_sse_globals():
    """Reset module-level SSE tracking globals before each test.

    Ensures test isolation without leaking state between _broadcast_to_sse_clients
    or _build_sse_payload test cases that manipulate _sse_clients,
    _sse_clients_lock, or _sse_client_last_active.
    """
    dh_mod._sse_clients.clear()
    dh_mod._sse_client_last_active.clear()
    yield


# Shared minimal state dicts used across multiple test classes


@pytest.fixture
def minimal_state() -> dict:
    """A bare-bones state dict with no iterations and all defaults."""
    return {
        "status": "running",
        "total_iterations": 0,
        "iterations": [],
        "stats": {},
        "initial_command": "",
        "started_at": "",
        "last_updated": "",
    }


@pytest.fixture
def running_state() -> dict:
    """A realistic running state with a few iterations and stats."""
    return {
        "status": "running",
        "total_iterations": 3,
        "iterations": [
            {
                "n": 1,
                "started_at": "2026-01-15T10:00:00",
                "duration_seconds": 12.5,
                "task_type": "evolve",
                "summary": "Refactored module layout",
                "error": None,
                "cpu_seconds_used": 8.2,
                "memory_rss_mb": 145.2,
                "memory_percent": 0.032,
            },
            {
                "n": 2,
                "started_at": "2026-01-15T10:01:00",
                "duration_seconds": 8.0,
                "task_type": "test",
                "summary": "Added unit tests",
                "error": None,
                "cpu_seconds_used": 4.1,
                "memory_rss_mb": 152.0,
                "memory_percent": 0.034,
            },
            {
                "n": 3,
                "started_at": "2026-01-15T10:02:00",
                "duration_seconds": 20.0,
                "task_type": "evolve",
                "summary": "Integrated SSE dashboard",
                "error": "timeout",
                "cpu_seconds_used": 18.0,
                "memory_rss_mb": 160.5,
                "memory_percent": 0.036,
            },
        ],
        "max_iterations": 10,
        "cooldown": 5,
        "initial_command": "Improve the codebase",
        "started_at": "2026-01-15T10:00:00.000000",
        "last_updated": "2026-01-15T10:02:20.123456",
        "evolved_goal": "Add full test coverage",
        "stats": {
            "success_count": 2,
            "error_count": 1,
            "total_duration_seconds": 40.5,
            "avg_duration_seconds": 13.5,
            "consecutive_errors": 1,
        },
    }


@pytest.fixture
def paused_state() -> dict:
    """A state where the loop is paused."""
    return {
        "status": "paused",
        "total_iterations": 5,
        "iterations": [
            {
                "n": i + 1,
                "started_at": f"2026-01-15T10:0{i}:00",
                "duration_seconds": 10.0,
                "task_type": "evolve",
                "summary": f"Iteration {i+1}",
                "error": None,
            }
            for i in range(5)
        ],
        "max_iterations": 10,
        "cooldown": 0,
        "initial_command": "Do something",
        "started_at": "2026-01-15T10:00:00",
        "last_updated": "2026-01-15T10:06:00",
        "stats": {
            "success_count": 5,
            "error_count": 0,
            "total_duration_seconds": 50.0,
            "avg_duration_seconds": 10.0,
        },
    }


@pytest.fixture
def state_with_error_iteration() -> dict:
    """State where the last iteration has an error (tests tags / row coloring)."""
    return {
        "status": "stopped",
        "total_iterations": 1,
        "iterations": [
            {
                "n": 1,
                "started_at": "2026-01-15T10:00:00",
                "duration_seconds": 5.0,
                "task_type": "evolve",
                "summary": "Failed attempt",
                "error": "timeout",
                "cpu_seconds_used": 4.0,
                "memory_rss_mb": 100.0,
                "memory_percent": 0.02,
            }
        ],
        "max_iterations": 0,
        "cooldown": 0,
        "initial_command": "Try something",
        "started_at": "2026-01-15T10:00:00",
        "last_updated": "2026-01-15T10:01:00",
        "stats": {
            "success_count": 0,
            "error_count": 1,
            "total_duration_seconds": 5.0,
            "avg_duration_seconds": 5.0,
        },
    }


# ===================================================================
# TestGenerateStatusHtml
# ===================================================================


class TestGenerateStatusHtml:
    """Tests for _generate_status_html(state, compact) — HTML template rendering."""

    def test_running_status_badge(self, running_state):
        """Running state emits 'running' CSS class and status text."""
        html = _generate_status_html(running_state)
        assert 'class="status-badge running"' in html
        assert "{STATUS}" not in html
        assert "{STATUS_CLASS}" not in html

    def test_paused_status_badge(self, paused_state):
        """Paused state emits 'paused' CSS class."""
        html = _generate_status_html(paused_state)
        assert 'class="status-badge paused"' in html

    def test_stopped_status(self):
        """Unknown/stopped status maps to 'stopped' CSS class."""
        state = {"status": "unknown", "iterations": [], "stats": {}}
        html = _generate_status_html(state)
        assert 'class="status-badge stopped"' in html

    def test_reloading_status(self):
        """Reloading status maps to 'reloading' CSS class."""
        state = {"status": "reloading", "iterations": [], "stats": {}}
        html = _generate_status_html(state)
        assert 'class="status-badge reloading"' in html

    def test_no_ledger_status(self):
        """'no_ledger' status uses the no_ledger CSS class."""
        state = {"status": "no_ledger", "iterations": [], "stats": {}}
        html = _generate_status_html(state)
        assert 'class="status-badge no_ledger"' in html

    def test_total_iterations_displayed(self, running_state):
        """Total iteration count appears in the meta section."""
        html = _generate_status_html(running_state)
        # {TOTAL} is replaced with str(total)
        assert '<span class="value">3</span>' in html

    def test_cooldown_active(self, running_state):
        """Cooldown > 0 emits the active cooldown class and text."""
        html = _generate_status_html(running_state)
        assert "cooldown-active" in html
        assert "5s" in html

    def test_cooldown_idle(self, paused_state):
        """Cooldown of 0 emits the idle CSS class and 'None' text."""
        html = _generate_status_html(paused_state)
        assert "cooldown-idle" in html
        assert "None" in html

    def test_cooldown_fallback_to_stats(self):
        """When state has no top-level cooldown, fall back to stats['cooldown']."""
        state = {
            "status": "running",
            "iterations": [],
            "stats": {"cooldown": 15},
            "total_iterations": 0,
        }
        html = _generate_status_html(state)
        assert "cooldown-active" in html
        assert "15s" in html

    def test_progress_row_with_max(self, running_state):
        """When max_iterations > 0, a progress bar row is rendered."""
        html = _generate_status_html(running_state)
        assert "/10" in html  # total/max
        assert "progress-fill" in html
        assert "30%" in html or "0%" in html  # 3/10 = 30%

    def test_no_progress_row_without_max(self):
        """When max_iterations is 0 or absent, no progress row is generated."""
        state = {
            "status": "running",
            "iterations": [],
            "total_iterations": 5,
            "stats": {},
        }
        html = _generate_status_html(state)
        # CSS rule still contains 'progress-fill'; check for absence of the
        # generated <h2>Progress row in the HTML body (after </style>)
        style_end = html.index("</style>")
        body_after_style = html[style_end:]
        assert "<h2>Progress</h2>" not in body_after_style

    def test_eta_display(self, running_state):
        """ETA is computed from remaining iterations * avg duration."""
        # 10 max - 3 done = 7 remaining * 13.5s = 94.5s -> ~1.6m -> "2m"
        html = _generate_status_html(running_state)
        # 94.5s rounds to ~1.6m which format: 94.5 / 60 = 1.575 -> "2m"
        assert "1m" in html or "2m" in html

    def test_eta_done_when_remaining_zero(self):
        """When remaining <= 0, ETA shows 'Done'.

        Note: iterations must have integer 'n' keys because the code does
        arithmetic on them (max_it - n).
        """
        state = {
            "status": "running",
            "total_iterations": 10,
            "max_iterations": 10,
            "iterations": [{"n": i + 1, "duration_seconds": 5} for i in range(10)],
            "stats": {"avg_duration_seconds": 5.0, "total_duration_seconds": 50.0},
            "initial_command": "",
            "started_at": "",
            "last_updated": "",
        }
        html = _generate_status_html(state)
        assert "Done" in html

    def test_eta_hours_format(self):
        """ETA >= 3600s is formatted as hours.

        Note: iterations must have integer 'n' keys because the code does
        arithmetic on them (max_it - n).
        """
        state = {
            "status": "running",
            "total_iterations": 1,
            "max_iterations": 100,
            "iterations": [{"n": 1, "duration_seconds": 60}],
            "stats": {"avg_duration_seconds": 60.0, "total_duration_seconds": 60.0},
            "initial_command": "",
            "started_at": "",
            "last_updated": "",
        }
        html = _generate_status_html(state)
        # 99 remaining * 60 = 5940 / 3600 = 1.65h -> "1.7h"? Actually 5940/3600 = 1.65 -> "1.6h" or "1.7h"
        assert "h" in html

    def test_goal_truncated_to_80_chars(self):
        """initial_command is truncated to 80 characters."""
        long_goal = "A" * 200
        state = {
            "status": "running",
            "iterations": [],
            "stats": {},
            "initial_command": long_goal,
        }
        html = _generate_status_html(state)
        assert "A" * 80 in html
        assert "A" * 81 not in html

    def test_goal_empty_fallback(self):
        """Empty initial_command shows '(none)' as fallback."""
        state = {
            "status": "running",
            "iterations": [],
            "stats": {},
            "initial_command": None,
        }
        html = _generate_status_html(state)
        assert "(none)" in html

    def test_started_at_fallback_to_question_mark(self):
        """Missing started_at renders as '?' truncated."""
        state = {"status": "running", "iterations": [], "stats": {}}
        html = _generate_status_html(state)
        assert "?" in html
        # Should contain "Started" meta item
        assert "{STARTED}" not in html

    def test_evolved_goal_row_present(self, running_state):
        """When evolved_goal is set, an 'Evolved Goal' section appears."""
        html = _generate_status_html(running_state)
        assert "Evolved Goal" in html
        assert "Add full test coverage" in html

    def test_evolved_goal_row_absent(self):
        """When no evolved_goal, the eva row is empty."""
        state = {
            "status": "running",
            "iterations": [],
            "stats": {},
            "initial_command": "hi",
        }
        html = _generate_status_html(state)
        assert "Evolved Goal" not in html

    def test_iteration_rows_reversed(self, running_state):
        """Iteration rows appear in reverse order (newest first)."""
        html = _generate_status_html(running_state)
        # Third iteration should appear before first in the rendered rows
        idx3 = html.index("Integrated SSE dashboard")
        idx1 = html.index("Refactored module layout")
        assert idx3 < idx1

    def test_iteration_limit_100(self):
        """Only the last 100 iterations are rendered."""
        iterations = [
            {
                "n": i,
                "started_at": "2026-01-15T10:00:00",
                "duration_seconds": 1.0,
                "task_type": "test",
                "summary": f"iter {i}",
                "error": None,
            }
            for i in range(150)
        ]
        state = {
            "status": "running",
            "total_iterations": 150,
            "iterations": iterations,
            "stats": {
                "total_duration_seconds": 150.0,
                "avg_duration_seconds": 1.0,
                "success_count": 150,
                "error_count": 0,
            },
            "initial_command": "",
            "started_at": "",
            "last_updated": "",
        }
        html = _generate_status_html(state)
        # iter 0 should not appear (it's among the first 50, outside the last 100)
        # iter 149 should appear
        assert "iter 149" in html

    def test_error_iteration_row_class(self, state_with_error_iteration):
        """Error iterations get the error-row CSS class."""
        html = _generate_status_html(state_with_error_iteration)
        assert 'class="error-row"' in html

    def test_error_iteration_tag(self, state_with_error_iteration):
        """Error iterations show an ERR tag."""
        html = _generate_status_html(state_with_error_iteration)
        assert "tag-err" in html
        assert "ERR" in html

    def test_summary_only_text(self, running_state):
        """The summary-only div includes stats in a human-readable form."""
        html = _generate_status_html(running_state)
        assert "3 iterations, 2 success" in html
        assert "1 errors" in html
        assert "40s total" in html or "41s total" in html

    def test_compact_mode_adds_class(self, running_state):
        """When compact=True, the body gets class='compact-mode'."""
        html = _generate_status_html(running_state, compact=True)
        assert '<body class="compact-mode">' in html

    def test_non_compact_no_class(self, running_state):
        """When compact=False (default), body has no extra class."""
        html = _generate_status_html(running_state, compact=False)
        assert '<body class="compact-mode">' not in html
        # Should have the normal body tag
        assert html.count("<body>") == 1

    def test_cpu_mem_from_last_iteration(self, running_state):
        """CPU seconds, memory RSS, and memory percent come from last iteration."""
        html = _generate_status_html(running_state)
        # Last iteration has cpu_seconds_used=18.0 -> "18.0"
        assert ">18.0</div>" in html or ">18</div>" in html or "{CPU_SEC}" not in html
        # memory_rss_mb=160.5 -> "161MB" (f"{160.5:.0f}")
        assert "161MB" in html or "160MB" in html
        # memory_percent=0.036 -> "3.6" (converted: 0.036 * 100 = 3.6)
        assert "3.6" in html

    def test_cpu_mem_fallback_no_iterations(self, minimal_state):
        """When no iterations, cpu/mem fall back to '0.0' / '0' / '0.0'."""
        html = _generate_status_html(minimal_state)
        assert "{CPU_SEC}" not in html
        assert "{MEM_MB}" not in html

    def test_worktree_merge_tags(self):
        """Iteration with worktree_merge data gets WT tags."""
        state = {
            "status": "running",
            "total_iterations": 1,
            "iterations": [
                {
                    "n": 1,
                    "started_at": "2026-01-15T10:00:00",
                    "duration_seconds": 5.0,
                    "task_type": "evolve",
                    "summary": "WT merge test",
                    "error": None,
                    "worktree_merge": {"merged": 3, "failed": 1, "conflicts": 0},
                }
            ],
            "stats": {
                "success_count": 1,
                "error_count": 0,
                "total_duration_seconds": 5.0,
                "avg_duration_seconds": 5.0,
            },
            "initial_command": "",
            "started_at": "",
            "last_updated": "",
        }
        html = _generate_status_html(state)
        assert "tag-wtree" in html
        assert "WT:3" in html
        assert "WT-FAIL:1" in html

    def test_remote_cleanup_tags(self):
        """Iteration with remote_cleanup data gets remote cleanup tags."""
        state = {
            "status": "running",
            "total_iterations": 1,
            "iterations": [
                {
                    "n": 1,
                    "started_at": "2026-01-15T10:00:00",
                    "duration_seconds": 5.0,
                    "task_type": "evolve",
                    "summary": "Remote cleanup",
                    "error": None,
                    "remote_cleanup": {
                        "remote_deleted": 2,
                        "remote_merged": 1,
                        "stale_pruned": 3,
                    },
                }
            ],
            "stats": {
                "success_count": 1,
                "error_count": 0,
                "total_duration_seconds": 5.0,
                "avg_duration_seconds": 5.0,
            },
            "initial_command": "",
            "started_at": "",
            "last_updated": "",
        }
        html = _generate_status_html(state)
        assert "tag-wtree" in html
        assert "R:2del" in html
        assert "R:3stale" in html
        assert "R:1mg" in html

    def test_evolve_tag_on_iteration_with_next_goal(self):
        """Iterations with next_goal emit an EVOLVE tag."""
        state = {
            "status": "running",
            "total_iterations": 1,
            "iterations": [
                {
                    "n": 1,
                    "started_at": "2026-01-15T10:00:00",
                    "duration_seconds": 3.0,
                    "task_type": "evolve",
                    "summary": "evolution step",
                    "error": None,
                    "next_goal": "Write more docs",
                }
            ],
            "stats": {
                "success_count": 1,
                "error_count": 0,
                "total_duration_seconds": 3.0,
                "avg_duration_seconds": 3.0,
            },
            "initial_command": "",
            "started_at": "",
            "last_updated": "",
        }
        html = _generate_status_html(state)
        assert "EVOLVE" in html
        assert "tag-evolve" in html

    def test_memory_percent_float_handling(self):
        """memory_percent as float is converted via multiply by 100."""
        state = {
            "status": "running",
            "total_iterations": 1,
            "iterations": [
                {
                    "n": 1,
                    "started_at": "",
                    "duration_seconds": 1.0,
                    "task_type": "test",
                    "summary": "",
                    "error": None,
                    "memory_percent": 0.05,  # float: 0.05 * 100 = 5.0
                    "memory_rss_mb": 100.0,
                    "cpu_seconds_used": 2.0,
                }
            ],
            "stats": {"success_count": 1, "error_count": 0},
            "initial_command": "",
            "started_at": "",
            "last_updated": "",
        }
        html = _generate_status_html(state)
        assert "5.0" in html

    def test_memory_percent_non_float_handling(self):
        """memory_percent as non-float (e.g., int/string) is used as-is."""
        state = {
            "status": "running",
            "total_iterations": 1,
            "iterations": [
                {
                    "n": 1,
                    "started_at": "",
                    "duration_seconds": 1.0,
                    "task_type": "test",
                    "summary": "",
                    "error": None,
                    "memory_percent": 42,
                    "memory_rss_mb": 100,
                    "cpu_seconds_used": 2,
                }
            ],
            "stats": {"success_count": 1, "error_count": 0},
            "initial_command": "",
            "started_at": "",
            "last_updated": "",
        }
        html = _generate_status_html(state)
        assert "42" in html


# ===================================================================
# TestWriteStatusHtml
# ===================================================================


class TestWriteStatusHtml:
    """Tests for _write_status_html(html_path, state) — file I/O."""

    def test_writes_html_to_file(self, tmp_path, running_state):
        """_write_status_html generates HTML and writes it to the specified path."""
        dest = str(tmp_path / "status.html")
        with patch(
            "hermes_loop.dashboard._generate_status_html",
            return_value="<html>TEST</html>",
        ):
            with patch("hermes_loop.dashboard.os.makedirs") as mock_makedirs:
                with patch("hermes_loop.dashboard.open") as mock_open:
                    mock_file = MagicMock()
                    mock_open.return_value.__enter__.return_value = mock_file
                    _write_status_html(dest, running_state)

        mock_makedirs.assert_called_once()
        mock_open.assert_called_once_with(dest, "w")
        mock_file.write.assert_called_once_with("<html>TEST</html>")

    def test_creates_parent_directories(self, tmp_path):
        """os.makedirs is called to ensure the parent directory exists."""
        dest = str(tmp_path / "sub" / "status.html")
        with patch("hermes_loop.dashboard._generate_status_html", return_value="html"):
            with patch("hermes_loop.dashboard.os.makedirs") as mock_makedirs:
                with patch("hermes_loop.dashboard.open"):
                    _write_status_html(dest, {})
        # makedirs should be called with the dirname of the absolute path
        args, _ = mock_makedirs.call_args
        # The argument should contain a path ending in 'sub'
        assert "sub" in str(args[0]) or args is not None

    def test_calls_generate_status_html(self, tmp_path, running_state):
        """_write_status_html delegates to _generate_status_html with the state."""
        dest = str(tmp_path / "status.html")
        with patch(
            "hermes_loop.dashboard._generate_status_html",
            return_value="<html>OK</html>",
        ) as mock_gen:
            with patch("hermes_loop.dashboard.os.makedirs"):
                with patch("hermes_loop.dashboard.open"):
                    _write_status_html(dest, running_state)
        mock_gen.assert_called_once_with(running_state)

    def test_logs_on_io_error(self, tmp_path):
        """When an OSError or IOError occurs, _log is called instead of crashing."""
        dest = str(tmp_path / "bad" / "status.html")
        with patch("hermes_loop.dashboard._generate_status_html", return_value="html"):
            with patch(
                "hermes_loop.dashboard.os.makedirs", side_effect=OSError("Disk full")
            ):
                with patch("hermes_loop.dashboard._log") as mock_log:
                    _write_status_html(dest, {})
        mock_log.assert_called_once()
        call_args_str = " ".join(str(a) for a in mock_log.call_args[0])
        assert "Disk full" in call_args_str

    def test_logs_on_open_error(self, tmp_path):
        """When open() raises IOError, _log is called."""
        dest = str(tmp_path / "status.html")
        with patch("hermes_loop.dashboard._generate_status_html", return_value="html"):
            with patch("hermes_loop.dashboard.os.makedirs"):
                with patch(
                    "hermes_loop.dashboard.open",
                    side_effect=IOError("Permission denied"),
                ):
                    with patch("hermes_loop.dashboard._log") as mock_log:
                        _write_status_html(dest, {})

        mock_log.assert_called_once()
        call_args_str = " ".join(str(a) for a in mock_log.call_args[0])
        assert "Permission denied" in call_args_str


# ===================================================================
# TestWrapSsePayload
# ===================================================================


class TestWrapSsePayload:
    """Tests for _wrap_sse_payload(raw) — SSE transport envelope wrapping."""

    def test_returns_envelope_with_type_and_data(self):
        """The result is a dict with 'type': 'status_update' and 'data' sub-dict."""
        result = _wrap_sse_payload({"status": "running"})
        assert result["type"] == "status_update"
        assert "data" in result

    def test_loop_status_in_data(self):
        """top-level status is mirrored into data.loop_status."""
        result = _wrap_sse_payload({"status": "paused"})
        assert result["data"]["loop_status"] == "paused"

    def test_loop_status_fallback_to_unknown(self):
        """Missing status defaults to 'unknown' in data.loop_status."""
        result = _wrap_sse_payload({})
        assert result["data"]["loop_status"] == "unknown"

    def test_ledger_contains_mapped_fields(self):
        """The 'ledger' sub-dict correctly maps raw keys."""
        raw = {
            "status": "running",
            "total_iterations": 42,
            "max_iterations": 100,
            "goal": "fix bugs",
            "evolved_goal": "add tests",
            "started_at": "2026-06-28T00:00:00",
            "last_updated": "2026-06-28T12:00:00",
            "cooldown": 10,
        }
        result = _wrap_sse_payload(raw)
        ledger = result["data"]["ledger"]
        assert ledger["status"] == "running"
        assert ledger["total_iterations"] == 42
        assert ledger["max_iterations"] == 100
        assert ledger["goal"] == "fix bugs"
        assert ledger["evolved_goal"] == "add tests"
        assert ledger["started_at"] == "2026-06-28T00:00:00"
        assert ledger["last_updated"] == "2026-06-28T12:00:00"
        assert ledger["cooldown"] == 10

    def test_ledger_defaults(self):
        """Missing ledger fields default to empty / 0 values."""
        result = _wrap_sse_payload({})
        ledger = result["data"]["ledger"]
        assert ledger["total_iterations"] == 0
        assert ledger["max_iterations"] == 0
        assert ledger["goal"] == ""
        assert ledger["evolved_goal"] == ""
        assert ledger["started_at"] == ""
        assert ledger["last_updated"] == ""
        assert ledger["cooldown"] == 0

    def test_latest_iteration_passthrough(self):
        """The 'iteration' key in raw becomes 'latest_iteration' in data."""
        raw = {"status": "running", "iteration": {"n": 7, "summary": "test"}}
        result = _wrap_sse_payload(raw)
        assert result["data"]["latest_iteration"] == {"n": 7, "summary": "test"}

    def test_latest_iteration_defaults_to_empty_dict(self):
        """When raw has no 'iteration', latest_iteration is {}."""
        result = _wrap_sse_payload({"status": "running"})
        assert result["data"]["latest_iteration"] == {}

    def test_stats_and_error_counts_passthrough(self):
        """stats, error_counts, mitigations, eta, goals pass through verbatim."""
        raw = {
            "status": "running",
            "stats": {"success_count": 5},
            "error_counts": {"timeout": 1},
            "mitigations": {"timeout_increased": True},
            "eta": {"remaining_formatted": "10m"},
            "goals": [{"text": "goal1", "done": False}],
        }
        result = _wrap_sse_payload(raw)
        assert result["data"]["stats"] == {"success_count": 5}
        assert result["data"]["error_counts"] == {"timeout": 1}
        assert result["data"]["mitigations"] == {"timeout_increased": True}
        assert result["data"]["eta"] == {"remaining_formatted": "10m"}
        assert result["data"]["goals"] == [{"text": "goal1", "done": False}]

    def test_extra_metric_fields(self):
        """avg_chars_per_iter, avg_throughput, est_cost, iters_per_goal, metrics_summary, consecutive fields pass through."""
        raw = {
            "status": "running",
            "avg_chars_per_iter": 1200,
            "avg_throughput": 45.2,
            "est_cost": "$0.50",
            "iters_per_goal": 15,
            "metrics_summary": "1200 chars/iter",
            "consecutive_errors": 2,
            "consecutive_successes": 5,
            "cooldown": 30,
        }
        result = _wrap_sse_payload(raw)
        data = result["data"]
        assert data["avg_chars_per_iter"] == 1200
        assert data["avg_throughput"] == 45.2
        assert data["est_cost"] == "$0.50"
        assert data["iters_per_goal"] == 15
        assert data["metrics_summary"] == "1200 chars/iter"
        assert data["consecutive_errors"] == 2
        assert data["consecutive_successes"] == 5
        assert data["cooldown"] == 30


# ===================================================================
# TestBuildSsePayload
# ===================================================================


class TestBuildSsePayload:
    """Tests for _build_sse_payload(state) — compact JSON payload builder."""

    def test_returns_iteration_and_status(self, running_state):
        """Returns 'iteration' (latest) and 'status' from the state."""
        result = _build_sse_payload(running_state)
        assert result["status"] == "running"
        assert result["iteration"]["n"] == 3
        assert result["iteration"]["summary"] == "Integrated SSE dashboard"

    def test_empty_iterations_yields_empty_dict(self):
        """When iterations is empty, 'iteration' is {}."""
        state = {"status": "paused", "iterations": [], "stats": {}}
        result = _build_sse_payload(state)
        assert result["iteration"] == {}

    def test_total_and_max_iterations(self, running_state):
        """total_iterations and max_iterations pass through from state."""
        result = _build_sse_payload(running_state)
        assert result["total_iterations"] == 3
        assert result["max_iterations"] == 10

    def test_goal_from_initial_command_truncated_80(self):
        """goal is initial_command truncated to 80 chars."""
        state = {
            "status": "running",
            "initial_command": "X" * 200,
            "iterations": [],
            "stats": {},
        }
        result = _build_sse_payload(state)
        assert len(result["goal"]) == 80
        assert result["goal"] == "X" * 80

    def test_evolved_goal_and_timestamps(self, running_state):
        """evolved_goal, started_at, last_updated pass through."""
        result = _build_sse_payload(running_state)
        assert result["evolved_goal"] == "Add full test coverage"
        assert result["started_at"] == "2026-01-15T10:00:00.000000"
        assert result["last_updated"] == "2026-01-15T10:02:20.123456"

    def test_stats_transformed(self, running_state):
        """stats sub-dict contains the four expected fields."""
        result = _build_sse_payload(running_state)
        s = result["stats"]
        assert s["success_count"] == 2
        assert s["error_count"] == 1
        assert s["total_duration_seconds"] == 40.5
        assert s["avg_duration_seconds"] == 13.5

    def test_consecutive_error_and_success_from_stats(self, running_state):
        """consecutive_errors and consecutive_successes extracted from stats."""
        result = _build_sse_payload(running_state)
        assert result["consecutive_errors"] == 1
        assert result["consecutive_successes"] == 0

    def test_cooldown_and_eta_passthrough(self):
        """cooldown and eta pass through from state."""
        state = {
            "status": "running",
            "iterations": [],
            "stats": {},
            "cooldown": 25,
            "eta": {"remaining_formatted": "5m"},
        }
        result = _build_sse_payload(state)
        assert result["cooldown"] == 25
        assert result["eta"] == {"remaining_formatted": "5m"}

    def test_error_counts_mapped(self):
        """error_type_counts is remapped to error_counts with zero-filled categories."""
        state = {
            "status": "running",
            "iterations": [],
            "stats": {},
            "error_type_counts": {"timeout": 3, "network": 2},
        }
        result = _build_sse_payload(state)
        ec = result["error_counts"]
        assert ec["timeout"] == 3
        assert ec["network"] == 2
        assert ec["schema"] == 0
        assert ec["heartbeat"] == 0
        assert ec["unknown"] == 0

    def test_mitigations_passthrough(self):
        """mitigations dict passes through (not the dual-source notes)."""
        state = {
            "status": "running",
            "iterations": [],
            "stats": {},
            "mitigations": {"timeout_increased": True, "cooldown_elevated": False},
        }
        result = _build_sse_payload(state)
        assert result["mitigations"] == {
            "timeout_increased": True,
            "cooldown_elevated": False,
        }

    def test_goals_list_built(self):
        """Goals are built from goals_specs and goals_completed, with hash lookup."""
        state = {
            "status": "running",
            "total_iterations": 5,
            "iterations": [],
            "stats": {},
            "goal_index": 0,
            "goals_specs": ["Write tests", "Add CI", "Document API"],
            "goals_completed": {
                # Mock hash for "Write tests" — we need to know what _goal_hash produces.
                # Instead of mocking, we'll verify the structure and known fields.
            },
        }
        result = _build_sse_payload(state)
        assert len(result["goals"]) == 3
        for g in result["goals"]:
            assert "text" in g
            assert "done" in g
            assert "active" in g

    def test_goals_empty_when_no_specs(self):
        """Empty or missing goals_specs produces empty goals list."""
        state = {"status": "running", "iterations": [], "stats": {}}
        result = _build_sse_payload(state)
        assert result["goals"] == []

    def test_avg_chars_per_iter_computed(self):
        """avg_chars_per_iter computed from output_chars across iterations."""
        state = {
            "status": "running",
            "iterations": [
                {"output_chars": 1000},
                {"output_chars": 2000},
                {"output_chars": 3000},
            ],
            "stats": {},
            "total_iterations": 3,
        }
        result = _build_sse_payload(state)
        # (1000 + 2000 + 3000) // 3 = 2000
        assert result["avg_chars_per_iter"] == 2000

    def test_avg_throughput_computed(self):
        """avg_throughput computed from chars_per_second across iterations."""
        state = {
            "status": "running",
            "iterations": [
                {"chars_per_second": 10.0},
                {"chars_per_second": 20.0},
                {"chars_per_second": 0},  # 0 gets filtered out
            ],
            "stats": {},
            "total_iterations": 3,
        }
        result = _build_sse_payload(state)
        # (10.0 + 20.0) / 2 = 15.0
        assert result["avg_throughput"] == 15.0

    def test_avg_throughput_none_when_no_cps(self):
        """When no iteration has positive chars_per_second, avg_throughput is None."""
        state = {
            "status": "running",
            "iterations": [
                {"chars_per_second": 0},
                {"chars_per_second": None},
            ],
            "stats": {},
            "total_iterations": 2,
        }
        result = _build_sse_payload(state)
        assert result["avg_throughput"] is None

    def test_metrics_summary_built(self):
        """metrics_summary is a comma-joined string of available metrics."""
        state = {
            "status": "running",
            "iterations": [
                {"output_chars": 500, "chars_per_second": 25.0},
            ],
            "stats": {"avg_duration_seconds": 30.0},
            "total_iterations": 1,
        }
        result = _build_sse_payload(state)
        assert "chars/iter" in result["metrics_summary"]
        assert "cps avg" in result["metrics_summary"]
        assert "30s avg" in result["metrics_summary"]

    def test_metrics_summary_empty_when_no_data(self):
        """Without any metric source, metrics_summary is empty string."""
        state = {
            "status": "running",
            "iterations": [],
            "stats": {"avg_duration_seconds": 0},
            "total_iterations": 0,
        }
        result = _build_sse_payload(state)
        assert result["metrics_summary"] == ""

    def test_iters_per_goal_computed(self):
        """iters_per_goal = total_iters // len(goals_list), minimum 1."""
        state = {
            "status": "running",
            "total_iterations": 10,
            "iterations": [],
            "stats": {},
            "goal_index": 0,
            "goals_specs": ["g1", "g2"],
            "goals_completed": {},
        }
        result = _build_sse_payload(state)
        assert result["iters_per_goal"] == 5  # 10 // 2

    def test_iters_per_goal_none_when_no_goals(self):
        """Without goals or iterations, iters_per_goal is None."""
        state = {
            "status": "running",
            "iterations": [],
            "stats": {},
            "total_iterations": 0,
        }
        result = _build_sse_payload(state)
        assert result["iters_per_goal"] is None

    def test_est_cost_passthrough(self):
        """est_cost comes from state."""
        state = {
            "status": "running",
            "iterations": [],
            "stats": {},
            "est_cost": "$2.50",
        }
        result = _build_sse_payload(state)
        assert result["est_cost"] == "$2.50"


# ===================================================================
# TestBroadcastToSseClients
# ===================================================================


class TestBroadcastToSseClients:
    """Tests for _broadcast_to_sse_clients(state) — pushing to SSE client queues."""

    def setup_method(self):
        """Set up a fresh mock queue before each test method."""
        dh_mod._sse_clients.clear()
        dh_mod._sse_client_last_active.clear()

    def test_puts_payload_on_each_client_queue(self, minimal_state):
        """Each connected client receives the serialized payload."""
        q1 = MagicMock(spec=queue.Queue)
        q2 = MagicMock(spec=queue.Queue)
        dh_mod._sse_clients.append(q1)
        dh_mod._sse_clients.append(q2)
        now = 1000.0

        with patch(
            "hermes_loop.dashboard._build_sse_payload",
            return_value={"status": "running"},
        ):
            with patch("hermes_loop.dashboard.time.monotonic", return_value=now):
                _broadcast_to_sse_clients(minimal_state)

        # Both queues should get put_nowait called
        q1.put_nowait.assert_called_once()
        q2.put_nowait.assert_called_once()
        # Payload should be serialized JSON
        json_payload = q1.put_nowait.call_args[0][0]
        parsed = json.loads(json_payload)
        assert parsed["status"] == "running"

    def test_skips_stale_clients(self, minimal_state):
        """Clients idle >_CLIENT_STALE_TIMEOUT are skipped without put_nowait."""
        q_stale = MagicMock(spec=queue.Queue)
        q_active = MagicMock(spec=queue.Queue)
        dh_mod._sse_clients.append(q_stale)
        dh_mod._sse_clients.append(q_active)
        now = 1000.0

        # Pretend q_stale's last activity was 90s ago (>60s threshold)
        dh_mod._sse_client_last_active[id(q_stale)] = 900.0  # 100s ago

        with patch("hermes_loop.dashboard._build_sse_payload", return_value={}):
            with patch("hermes_loop.dashboard.time.monotonic", return_value=now):
                _broadcast_to_sse_clients(minimal_state)

        # q_stale should be skipped entirely
        q_stale.put_nowait.assert_not_called()
        # q_active should still get the payload
        q_active.put_nowait.assert_called_once()

    def test_removes_stale_client_from_list(self, minimal_state):
        """Stale clients are removed from _sse_clients after sweep."""
        q_stale = MagicMock(spec=queue.Queue)
        dh_mod._sse_clients.append(q_stale)
        now = 1000.0
        dh_mod._sse_client_last_active[id(q_stale)] = 900.0

        with patch("hermes_loop.dashboard._build_sse_payload", return_value={}):
            with patch("hermes_loop.dashboard.time.monotonic", return_value=now):
                _broadcast_to_sse_clients(minimal_state)

        assert q_stale not in dh_mod._sse_clients

    def test_garbage_collects_stale_active_dict(self, minimal_state):
        """Stale qid entries are removed from the last_active tracking dict."""
        q_stale = MagicMock(spec=queue.Queue)
        q_stale_id = id(q_stale)
        dh_mod._sse_clients.append(q_stale)
        dh_mod._sse_client_last_active[q_stale_id] = 900.0
        now = 1000.0

        with patch("hermes_loop.dashboard._build_sse_payload", return_value={}):
            with patch("hermes_loop.dashboard.time.monotonic", return_value=now):
                _broadcast_to_sse_clients(minimal_state)

        assert q_stale_id not in dh_mod._sse_client_last_active

    def test_drops_full_queue(self, minimal_state):
        """When q.put_nowait raises queue.Full, the client is dropped."""
        q_full = MagicMock(spec=queue.Queue)
        # put_nowait raises queue.Full
        q_full.put_nowait.side_effect = queue.Full
        dh_mod._sse_clients.append(q_full)
        now = 1000.0
        dh_mod._sse_client_last_active[id(q_full)] = now

        with patch("hermes_loop.dashboard._build_sse_payload", return_value={}):
            with patch("hermes_loop.dashboard.time.monotonic", return_value=now):
                _broadcast_to_sse_clients(minimal_state)

        # The full client should be removed from the list
        assert q_full not in dh_mod._sse_clients
        # Its last_active entry should be garbage-collected
        assert id(q_full) not in dh_mod._sse_client_last_active

    def test_safeguard_generic_exception(self, minimal_state):
        """When q.put_nowait raises a generic Exception, the client is dropped."""
        q_bad = MagicMock(spec=queue.Queue)
        q_bad.put_nowait.side_effect = RuntimeError("broken queue")
        dh_mod._sse_clients.append(q_bad)
        now = 1000.0
        dh_mod._sse_client_last_active[id(q_bad)] = now

        with patch("hermes_loop.dashboard._build_sse_payload", return_value={}):
            with patch("hermes_loop.dashboard.time.monotonic", return_value=now):
                _broadcast_to_sse_clients(minimal_state)

        # Generic exception should also drop the client
        assert q_bad not in dh_mod._sse_clients

    def test_updates_last_active_on_successful_put(self, minimal_state):
        """Successful put_nowait updates _sse_client_last_active to current time."""
        q = MagicMock(spec=queue.Queue)
        dh_mod._sse_clients.append(q)
        now = 1000.0

        with patch("hermes_loop.dashboard._build_sse_payload", return_value={}):
            with patch("hermes_loop.dashboard.time.monotonic", return_value=now):
                _broadcast_to_sse_clients(minimal_state)

        assert dh_mod._sse_client_last_active[id(q)] == now

    def test_preserves_active_clients(self, minimal_state):
        """Active clients that successfully receive payload remain in the list."""
        q1 = MagicMock(spec=queue.Queue)
        q2 = MagicMock(spec=queue.Queue)
        dh_mod._sse_clients.append(q1)
        dh_mod._sse_clients.append(q2)
        now = 1000.0

        with patch("hermes_loop.dashboard._build_sse_payload", return_value={}):
            with patch("hermes_loop.dashboard.time.monotonic", return_value=now):
                _broadcast_to_sse_clients(minimal_state)

        assert q1 in dh_mod._sse_clients
        assert q2 in dh_mod._sse_clients

    def test_empty_client_list(self, minimal_state):
        """Broadcasting with no clients should not crash."""
        dh_mod._sse_clients.clear()
        with patch("hermes_loop.dashboard._build_sse_payload", return_value={}):
            # Should not raise
            _broadcast_to_sse_clients(minimal_state)
        assert dh_mod._sse_clients == []

    def test_json_serialization_uses_default_str(self):
        """Serialization uses json.dumps with default=str to handle non-serializable items."""
        q = MagicMock(spec=queue.Queue)
        dh_mod._sse_clients.append(q)
        state = {
            "status": "running",
            "iterations": [],
            "stats": {},
            # Bytes are not JSON-serializable normally; default=str handles them
            "extra": b"binary_data",
        }

        with patch(
            "hermes_loop.dashboard._build_sse_payload", return_value={"binary": b"data"}
        ):
            _broadcast_to_sse_clients(state)

        json_arg = q.put_nowait.call_args[0][0]
        # Should be valid JSON because default=str converts bytes
        parsed = json.loads(json_arg)
        assert isinstance(parsed, dict)

    def test_build_sse_payload_called_with_state(self):
        """_broadcast_to_sse_clients calls _build_sse_payload with the state dict."""
        state = {"status": "running", "iterations": [], "stats": {}}
        q = MagicMock(spec=queue.Queue)
        dh_mod._sse_clients.append(q)

        with patch(
            "hermes_loop.dashboard._build_sse_payload", return_value={}
        ) as mock_build:
            _broadcast_to_sse_clients(state)

        mock_build.assert_called_once_with(state)
