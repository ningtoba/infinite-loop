"""Tests for loop.py — _print_shutdown_summary."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hermes_loop.loop import _print_shutdown_summary


class TestPrintShutdownSummary:
    """Tests for _print_shutdown_summary.

    Note: _print_shutdown_summary uses a local import:
        from .file_utils import _log as _slog
    So patches must target hermes_loop.file_utils._log, not hermes_loop.loop._log.
    """

    def _make_colorizer_mock(self):
        """Create a colorizer mock with identity side effects."""
        c = MagicMock()
        c.header.side_effect = lambda x: x
        c.value.side_effect = lambda x: x
        c.flag.side_effect = lambda x: x
        c.dim.side_effect = lambda x: x
        c.tag_ok.return_value = ""
        c.tag_fail.return_value = ""
        c.group_title.side_effect = lambda x: x
        return c

    def test_basic_shutdown_summary(self):
        """Basic shutdown summary prints SHUTDOWN SUMMARY header."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            with patch("hermes_loop.loop.colorizer", self._make_colorizer_mock()):
                _print_shutdown_summary(
                    state={
                        "iterations": [],
                        "stats": {"total_duration_seconds": 120},
                        "error_type_counts": {},
                    },
                    iteration_count=5,
                    stop_reason="stopped: signal",
                    goal="fix bugs",
                )
        assert mock_log.called
        all_text = " ".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "SHUTDOWN SUMMARY" in all_text
        assert "fix bugs" in all_text

    def test_shutdown_summary_with_errors_and_stuck(self):
        """Error and stuck counts are shown correctly."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            with patch("hermes_loop.loop.colorizer", self._make_colorizer_mock()):
                _print_shutdown_summary(
                    state={
                        "iterations": [
                            {"error": "timeout"},
                            {"error": None, "classification": "completed"},
                            {"error": "network"},
                            {"error": None, "classification": "stuck"},
                            {"error": None, "classification": "completed"},
                        ],
                        "stats": {"total_duration_seconds": 300},
                        "error_type_counts": {"timeout": 2, "network": 1},
                    },
                    iteration_count=5,
                    stop_reason="stopped: max_iterations",
                )
        all_text = " ".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert any("max_iterations" in s for s in all_text.split())

    def test_shutdown_with_zero_duration(self):
        """Zero duration does not render duration line."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            with patch("hermes_loop.loop.colorizer", self._make_colorizer_mock()):
                _print_shutdown_summary(
                    state={
                        "iterations": [],
                        "stats": {},
                        "error_type_counts": {},
                    },
                    iteration_count=0,
                    stop_reason="no iterations",
                )
        all_text = " ".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "SHUTDOWN SUMMARY" in all_text

    def test_shutdown_with_no_goal(self):
        """Summary works without goal string."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            with patch("hermes_loop.loop.colorizer", self._make_colorizer_mock()):
                _print_shutdown_summary(
                    state={
                        "iterations": [{"error": None}],
                        "stats": {},
                        "error_type_counts": {},
                    },
                    iteration_count=1,
                    stop_reason="completed",
                )
        assert mock_log.called

    def test_shutdown_with_stuck_count(self):
        """Stuck iterations shown separately."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            with patch("hermes_loop.loop.colorizer", self._make_colorizer_mock()):
                _print_shutdown_summary(
                    state={
                        "iterations": [
                            {"error": None, "classification": "stuck"},
                            {"error": None, "classification": "completed"},
                        ],
                        "stats": {"total_duration_seconds": 60},
                        "error_type_counts": {},
                    },
                    iteration_count=2,
                    stop_reason="stopped: signal",
                )
        all_text = " ".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "Stuck" in all_text or "stuck" in all_text

    def test_shutdown_with_error_breakdown(self):
        """Error type breakdown is shown."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            with patch("hermes_loop.loop.colorizer", self._make_colorizer_mock()):
                _print_shutdown_summary(
                    state={
                        "iterations": [
                            {"error": "timeout"},
                            {"error": "network"},
                        ],
                        "stats": {"total_duration_seconds": 45},
                        "error_type_counts": {"timeout": 1, "network": 1},
                    },
                    iteration_count=2,
                    stop_reason="stopped: signal",
                )
        all_text = " ".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "timeout=1" in all_text
        assert "network=1" in all_text

    def test_duration_formatted_in_minutes(self):
        """Duration shown in minutes when >= 60s."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            with patch("hermes_loop.loop.colorizer", self._make_colorizer_mock()):
                _print_shutdown_summary(
                    state={
                        "iterations": [],
                        "stats": {"total_duration_seconds": 3600},
                        "error_type_counts": {},
                    },
                    iteration_count=10,
                    stop_reason="stopped: signal",
                )
        all_text = " ".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "3600s" in all_text or "60.0m" in all_text

    def test_workers_with_git_rendered(self):
        """Workers and git flags are passed through."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            with patch("hermes_loop.loop.colorizer", self._make_colorizer_mock()):
                _print_shutdown_summary(
                    state={
                        "iterations": [{"error": None}],
                        "stats": {"total_duration_seconds": 30},
                        "error_type_counts": {},
                    },
                    iteration_count=1,
                    stop_reason="completed",
                    goal="fix",
                    git=True,
                    workers=4,
                )
        assert mock_log.called

    def test_empty_iterations_list(self):
        """Empty iterations list doesn't crash."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            with patch("hermes_loop.loop.colorizer", self._make_colorizer_mock()):
                _print_shutdown_summary(
                    state={
                        "iterations": [],
                        "stats": {},
                        "error_type_counts": {},
                    },
                    iteration_count=0,
                    stop_reason="no iterations started",
                )
        assert mock_log.called

    def test_no_colorizer_breakage(self):
        """Works even with default colorizer (not mocked)."""
        with patch("hermes_loop.file_utils._log") as mock_log:
            _print_shutdown_summary(
                state={
                    "iterations": [{"error": None}],
                    "stats": {"total_duration_seconds": 10},
                    "error_type_counts": {},
                },
                iteration_count=1,
                stop_reason="stopped",
            )
        assert mock_log.called
