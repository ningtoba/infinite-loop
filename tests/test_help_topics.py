"""Tests for help_topics.py — display, introspection, and diagnostics."""

import json
import os
import sys
from unittest import mock

import pytest

from omp_loop.help_topics import (
    _explain_flag,
    _help_topic,
    _list_examples,
    _list_flags,
    _render_status,
    _run_doctor,
    _run_healthcheck,
)
from omp_loop.parser import _create_parser


# ── Helpers ─────────────────────────────────────────────
@pytest.fixture
def parser():
    """Return a real introspection parser."""
    return _create_parser(for_introspection=True)


# ── TestHelpTopic ───────────────────────────────────────
class TestHelpTopic:
    """_help_topic: show all flags in a single argument group."""

    def test_with_valid_topic(self, capsys, parser):
        """Print flags for a known topic group."""
        _help_topic("Core", parser=parser)
        captured = capsys.readouterr()
        out = captured.out
        assert "[Core]" in out
        assert "--goal" in out

    def test_with_invalid_topic(self, capsys, parser):
        """Print error message for an unknown topic."""
        _help_topic("nonexistent_topic_xyz", parser=parser)
        captured = capsys.readouterr()
        out = captured.out
        assert "Unknown topic:" in out

    def test_introspection_topic(self, capsys, parser):
        """Passing 'introspection' prints introspection flags."""
        _help_topic("introspection", parser=parser)
        captured = capsys.readouterr()
        out = captured.out
        assert "[Introspection]" in out
        assert "--list-flags" in out

    def test_with_underscore_topic(self, capsys, parser):
        """Topic with underscores is normalized and matched."""
        _help_topic("parallel_timeout", parser=parser)
        captured = capsys.readouterr()
        out = captured.out
        assert "Parallel & Timeout" in out or "Parallel" in out


# ── TestExplainFlag ─────────────────────────────────────
class TestExplainFlag:
    """_explain_flag: show detailed help for a single CLI flag."""

    def test_explain_goal_flag(self, capsys, parser):
        """Explain the --goal flag."""
        _explain_flag("goal", parser=parser)
        captured = capsys.readouterr()
        out = captured.out
        assert "Flag:" in out
        assert "--goal" in out

    def test_explain_unknown_flag(self, capsys, parser):
        """Explain a flag that does not exist."""
        _explain_flag("nonexistent_flag_xyz", parser=parser)
        captured = capsys.readouterr()
        out = captured.out
        assert "Unknown flag:" in out

    def test_explain_with_dashes(self, capsys, parser):
        """Flag name with dashes matches the underscored variant."""
        _explain_flag("max-iterations", parser=parser)
        captured = capsys.readouterr()
        out = captured.out
        assert "Flag:" in out
        assert "--max-iterations" in out

    def test_explain_with_default_value(self, capsys, parser):
        """Printed output includes default value when set."""
        _explain_flag("workers", parser=parser)
        captured = capsys.readouterr()
        out = captured.out
        assert "Default:" in out
        assert "1" in out


# ── TestListFlags ───────────────────────────────────────
class TestListFlags:
    """_list_flags: print all CLI flags organized by group."""

    def test_list_flags_returns(self, capsys):
        """Print the full list of flags with help text."""
        _list_flags(show_help=True)
        captured = capsys.readouterr()
        out = captured.out
        assert "CLI Flags Reference" in out
        assert "--goal" in out
        assert "[Introspection]" in out

    def test_list_flags_compact(self, capsys):
        """Print only group names and flag counts."""
        _list_flags(show_help=False)
        captured = capsys.readouterr()
        out = captured.out
        assert "CLI Flags Reference" in out
        assert "flags)" in out
        assert "[Introspection]" in out

    def test_list_flags_with_custom_parser(self, capsys, parser):
        """Accept an explicit parser instance."""
        _list_flags(show_help=True, parser=parser)
        captured = capsys.readouterr()
        out = captured.out
        assert "CLI Flags Reference" in out


# ── TestListExamples ────────────────────────────────────
class TestListExamples:
    """_list_examples: print categorized usage examples."""

    def test_list_examples_returns(self, capsys):
        """Print usage examples output."""
        _list_examples()
        captured = capsys.readouterr()
        out = captured.out
        assert "Usage Examples" in out
        assert "omp-loop" in out
        assert "--goal" in out
        assert "--run" in out

    def test_sections_present(self, capsys):
        """Common sections are printed."""
        _list_examples()
        captured = capsys.readouterr()
        out = captured.out
        assert "Basic Single-Goal Loop" in out
        assert "Help & Diagnostics" in out


# ── TestRenderStatus ────────────────────────────────────
class TestRenderStatus:
    """_render_status: render a compact status summary from the ledger."""

    def test_with_complete_ledger(self, capsys):
        """Render status with iterations and stats."""
        state = {
            "iterations": [
                {"n": 1, "summary": "Fixed lint errors", "error": None},
                {"n": 2, "summary": "Formatted code", "error": None},
            ],
            "total_iterations": 2,
            "status": "running",
            "stats": {"total_duration_seconds": 120},
        }
        _render_status(state)
        captured = capsys.readouterr()
        out = captured.out
        assert "Status:" in out
        assert "running" in out
        assert "2" in out
        assert "Formatted code" in out

    def test_with_empty_ledger(self, capsys):
        """Render status with no iterations."""
        state = {
            "iterations": [],
            "total_iterations": 0,
            "status": "idle",
            "stats": {"total_duration_seconds": 0},
        }
        _render_status(state)
        captured = capsys.readouterr()
        out = captured.out
        assert "Status:" in out
        assert "idle" in out
        assert "0" in out

    def test_with_errors(self, capsys):
        """Render status showing error count."""
        state = {
            "iterations": [
                {"n": 1, "summary": "OK", "error": None},
                {"n": 2, "summary": "Failed", "error": "timeout"},
            ],
            "total_iterations": 2,
            "status": "running",
            "stats": {"total_duration_seconds": 30},
        }
        _render_status(state)
        captured = capsys.readouterr()
        out = captured.out
        assert "Errors:" in out

    def test_duration_format_minutes(self, capsys):
        """Duration longer than 60 seconds shows minutes."""
        state = {
            "iterations": [],
            "total_iterations": 0,
            "status": "done",
            "stats": {"total_duration_seconds": 125},
        }
        _render_status(state)
        captured = capsys.readouterr()
        out = captured.out
        assert "2.1m" in out or "125s" in out


# ── TestRunDoctor ───────────────────────────────────────
class TestRunDoctor:
    """_run_doctor: run comprehensive self-diagnosis."""

    def test_doctor_runs(self, capsys):
        """Doctor prints diagnosis output."""
        with (
            mock.patch("shutil.which") as mock_which,
            mock.patch("subprocess.run") as mock_run,
            mock.patch("os.path.exists") as mock_exists,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}" if cmd in ("omp", "git") else None
            mock_run.return_value = mock.Mock(stdout="omp 0.1.0", returncode=0)
            mock_exists.return_value = False
            _run_doctor()
        captured = capsys.readouterr()
        out = captured.out
        assert "Doctor" in out
        assert "Python:" in out

    def test_doctor_missing_pi(self, capsys):
        """Doctor handles missing omp binary."""
        with (
            mock.patch("shutil.which") as mock_which,
            mock.patch("subprocess.run") as mock_run,
            mock.patch("os.path.exists") as mock_exists,
            mock.patch("os.path.getsize") as mock_getsize,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            mock_which.side_effect = lambda cmd: "/usr/bin/git" if cmd == "git" else None
            mock_run.return_value = mock.Mock(stdout="git 2.40", returncode=0)
            mock_exists.return_value = True
            mock_getsize.return_value = 1024
            _run_doctor()
        captured = capsys.readouterr()
        out = captured.out
        assert "Not found on PATH" in out


# ── TestRunHealthcheck ──────────────────────────────────
class TestRunHealthcheck:
    """_run_healthcheck: run structured health check and exit."""

    @pytest.fixture(autouse=True)
    def _mock_exit(self):
        """Prevent sys.exit from aborting the test."""
        with mock.patch.object(sys, "exit") as m:
            yield m

    def test_healthcheck_runs(self, capsys, _mock_exit):
        """Healthcheck prints JSON report and exits."""
        with (
            mock.patch("shutil.which") as mock_which,
            mock.patch("os.path.exists") as mock_exists,
            mock.patch("omp_loop.help_topics.extract_json_from_output") as mock_extract,
            mock.patch("omp_loop.help_topics.write_ledger") as mock_write,
            mock.patch("omp_loop.help_topics.read_ledger") as mock_read,
        ):
            mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}" if cmd in ("omp", "git") else None
            mock_exists.return_value = True
            mock_extract.return_value = {"test": True}
            mock_write.return_value = None
            mock_read.return_value = {"healthcheck": True}
            _run_healthcheck()
        captured = capsys.readouterr()
        out = captured.out
        assert out.strip(), "Expected JSON output, got empty string"
        try:
            report = json.loads(out)
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON output: {out}")
        assert "status" in report
        assert "checks" in report
        assert "summary" in report
        assert report["status"] == "healthy"
        assert _mock_exit.called
        args, _ = _mock_exit.call_args
        assert args[0] == 0

    def test_healthcheck_critical(self, capsys, _mock_exit):
        """Healthcheck reports critical status when omp is missing."""
        with (
            mock.patch("shutil.which") as mock_which,
            mock.patch("os.path.exists") as mock_exists,
            mock.patch("omp_loop.help_topics.extract_json_from_output") as mock_extract,
            mock.patch("omp_loop.help_topics.write_ledger") as mock_write,
            mock.patch("omp_loop.help_topics.read_ledger") as mock_read,
        ):
            mock_which.return_value = None  # nothing on PATH
            mock_exists.return_value = False
            mock_extract.return_value = None
            mock_write.return_value = None
            mock_read.return_value = None
            _run_healthcheck()
        captured = capsys.readouterr()
        out = captured.out
        assert out.strip(), "Expected JSON output, got empty string"
        try:
            report = json.loads(out)
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON output: {out}")
        assert report["status"] == "critical"
        assert _mock_exit.called
        args, _ = _mock_exit.call_args
        assert args[0] == 2
