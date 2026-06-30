"""Tests for omp_loop.git_utils — git state capture and auto-commit."""

import subprocess
from unittest.mock import MagicMock, patch

from omp_loop.git_utils import _capture_git_state, _git_auto_commit


class TestCaptureGitState:
    def test_no_git_dir(self):
        """Returns empty dict when no .git directory."""
        with patch("os.path.isdir", return_value=False):
            result = _capture_git_state("/tmp/nongit")
        assert result == {}

    def test_captures_diff_stat(self):
        """Captures git diff --stat output."""
        mock_run = MagicMock(
            side_effect=[
                MagicMock(stdout=" 1 file changed, 2 insertions(+)\n", returncode=0),
                MagicMock(stdout="(no staged changes)\n", returncode=0),
                MagicMock(stdout="abc1234\n", returncode=0),
            ]
        )
        with patch("os.path.isdir", return_value=True), patch("subprocess.run", mock_run):
            result = _capture_git_state("/tmp/repo")
        assert result["diff_stat"] == "1 file changed, 2 insertions(+)"
        assert result["diff_stat_cached"] == "(no staged changes)"
        assert result["head"] == "abc1234"

    def test_captures_empty_diff_stat(self):
        """Handles empty diff --stat output gracefully."""
        mock_run = MagicMock(
            side_effect=[
                MagicMock(stdout="", returncode=0),
                MagicMock(stdout="", returncode=0),
                MagicMock(stdout="def5678\n", returncode=0),
            ]
        )
        with patch("os.path.isdir", return_value=True), patch("subprocess.run", mock_run):
            result = _capture_git_state("/tmp/repo")
        assert result["diff_stat"] == "(no unstaged changes)"
        assert result["diff_stat_cached"] == "(no staged changes)"

    def test_stores_diff_when_requested(self):
        """Stores actual diff text when store_diff=True."""
        mock_run = MagicMock(
            side_effect=[
                MagicMock(stdout=" 1 file changed\n", returncode=0),
                MagicMock(stdout="(no staged changes)\n", returncode=0),
                MagicMock(stdout="abc1234\n", returncode=0),
                MagicMock(stdout="--- a/test.py\n+++ b/test.py\n+new line\n", returncode=0),
            ]
        )
        with patch("os.path.isdir", return_value=True), patch("subprocess.run", mock_run):
            result = _capture_git_state("/tmp/repo", store_diff=True)
        assert "diff" in result
        assert "new line" in result["diff"]

    def test_timeout_returns_empty(self):
        """Returns empty dict on subprocess timeout."""
        with (
            patch("os.path.isdir", return_value=True),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)),
        ):
            result = _capture_git_state("/tmp/repo")
        assert result == {}

    def test_missing_git_returns_empty(self):
        """Returns empty dict when git is not installed."""
        with (
            patch("os.path.isdir", return_value=True),
            patch("subprocess.run", side_effect=FileNotFoundError("git not found")),
        ):
            result = _capture_git_state("/tmp/repo")
        assert result == {}

    def test_diff_capped_at_10kb(self):
        """Store diff is capped at 10240 bytes."""
        large_diff = "x" * 20000
        mock_run = MagicMock(
            side_effect=[
                MagicMock(stdout=" 1 file changed\n", returncode=0),
                MagicMock(stdout="(no staged changes)\n", returncode=0),
                MagicMock(stdout="abc1234\n", returncode=0),
                MagicMock(stdout=large_diff, returncode=0),
            ]
        )
        with patch("os.path.isdir", return_value=True), patch("subprocess.run", mock_run):
            result = _capture_git_state("/tmp/repo", store_diff=True)
        assert len(result["diff"]) == 10240


class TestGitAutoCommit:
    def test_no_git_dir(self):
        """Returns None when no .git directory."""
        with patch("os.path.isdir", return_value=False):
            result = _git_auto_commit("/tmp/nongit", 1, "test summary")
        assert result is None

    def test_no_changes_returns_none(self):
        """Returns None when there are no staged changes."""
        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=0),
                MagicMock(returncode=0),
            ]
        )
        with patch("os.path.isdir", return_value=True), patch("subprocess.run", mock_run):
            result = _git_auto_commit("/tmp/repo", 1, "test summary")
        assert result is None

    def test_commits_with_summary(self):
        """Auto-commits with formatted message."""
        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=0),
                MagicMock(returncode=1),
                MagicMock(returncode=0),
                MagicMock(stdout="def5678\n", returncode=0),
            ]
        )
        with patch("os.path.isdir", return_value=True), patch("subprocess.run", mock_run):
            result = _git_auto_commit("/tmp/repo", 5, "Fixed lint errors")
        assert result == "def5678"

    def test_commit_message_format(self):
        """Commit message uses correct format."""
        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=0),
                MagicMock(returncode=1),
                MagicMock(returncode=0),
                MagicMock(stdout="abc123\n", returncode=0),
            ]
        )
        with patch("os.path.isdir", return_value=True), patch("subprocess.run", mock_run):
            _git_auto_commit("/tmp/repo", 42, "Short summary")
        commit_call = mock_run.call_args_list[2]
        assert "-m" in commit_call[0][0]
        msg_idx = commit_call[0][0].index("-m") + 1
        assert "infinite-loop iter #42: Short summary" in commit_call[0][0][msg_idx]

    def test_timeout_returns_none(self):
        """Returns None on subprocess timeout."""
        with (
            patch("os.path.isdir", return_value=True),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)),
        ):
            result = _git_auto_commit("/tmp/repo", 1, "test")
        assert result is None

    def test_missing_git_returns_none(self):
        """Returns None when git is not installed."""
        with (
            patch("os.path.isdir", return_value=True),
            patch("subprocess.run", side_effect=FileNotFoundError("git not found")),
        ):
            result = _git_auto_commit("/tmp/repo", 1, "test")
        assert result is None

    def test_summary_capped_at_80_chars(self):
        """Commit summary is capped to 80 characters."""
        long_summary = "a" * 200
        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=0),
                MagicMock(returncode=1),
                MagicMock(returncode=0),
                MagicMock(stdout="abc\n", returncode=0),
            ]
        )
        with patch("os.path.isdir", return_value=True), patch("subprocess.run", mock_run):
            _git_auto_commit("/tmp/repo", 1, long_summary)
        commit_call = mock_run.call_args_list[2]
        msg_idx = commit_call[0][0].index("-m") + 1
        msg = commit_call[0][0][msg_idx]
        assert len(msg) < 150
