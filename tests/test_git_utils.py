"""Tests for git_utils.py — _capture_git_state, _git_auto_commit."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch


from hermes_loop.git_utils import _capture_git_state, _git_auto_commit

# ===================================================================
# _capture_git_state tests
# ===================================================================


class TestCaptureGitState:
    """Tests for _capture_git_state — captures pre/post git state."""

    def test_no_git_dir_returns_empty_dict(self, tmp_path):
        """No .git directory returns empty dict."""
        result = _capture_git_state(str(tmp_path))
        assert result == {}

    def test_git_diff_stat(self, tmp_path):
        """Captures diff_stat from git diff --stat."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        mock_run = MagicMock()
        mock_run.stdout = "1 file changed, 5 insertions(+)"

        with patch("hermes_loop.git_utils.subprocess.run", return_value=mock_run):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path))

        assert result["diff_stat"] == "1 file changed, 5 insertions(+)"

    def test_no_unstaged_changes(self, tmp_path):
        """No unstaged changes returns fallback text."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        mock_run = MagicMock()
        mock_run.stdout = ""

        with patch("hermes_loop.git_utils.subprocess.run", return_value=mock_run):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path))

        assert result["diff_stat"] == "(no unstaged changes)"

    def test_staged_changes(self, tmp_path):
        """Captures staged changes diff_stat."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if "--cached" in args:
                mock.stdout = "1 file changed, 2 insertions(+)"
            elif "rev-parse" in args:
                mock.stdout = "abc1234"
                mock.returncode = 0
            else:
                mock.stdout = "1 file changed, 5 insertions(+)"
            return mock

        with patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path))

        assert result["diff_stat_cached"] == "1 file changed, 2 insertions(+)"
        assert result["head"] == "abc1234"

    def test_no_staged_changes(self, tmp_path):
        """No staged changes returns fallback text."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        mock_run = MagicMock()
        mock_run.return_value.stdout = ""

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if "--cached" in args:
                mock.stdout = ""
            elif "rev-parse" in args:
                mock.stdout = "abc1234"
                mock.returncode = 0
            else:
                mock.stdout = "1 file changed"
            return mock

        with patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path))

        assert result["diff_stat_cached"] == "(no staged changes)"

    def test_head_sha_captured(self, tmp_path):
        """Captures HEAD short SHA."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if "rev-parse" in args:
                mock.stdout = "deadbeef"
                mock.returncode = 0
            elif "--cached" in args:
                mock.stdout = ""
            else:
                mock.stdout = ""
            return mock

        with patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path))

        assert result["head"] == "deadbeef"

    def test_rev_parse_fails_head_empty(self, tmp_path):
        """When rev-parse fails, head is empty string."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if "rev-parse" in args:
                mock.returncode = 1
                mock.stdout = ""
            elif "--cached" in args:
                mock.stdout = ""
            else:
                mock.stdout = ""
            return mock

        with patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path))

        assert result["head"] == ""

    def test_store_diff(self, tmp_path):
        """When store_diff=True, captures unified diff capped at 10KB."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if args == ["git", "diff"]:
                mock.stdout = "--- a/file\n+++ b/file\n@@ -1 +1 @@\n-change\n+change"
            elif "--cached" in args:
                mock.stdout = ""
            elif "rev-parse" in args:
                mock.stdout = "abc1234"
                mock.returncode = 0
            else:
                mock.stdout = "1 file changed"
            return mock

        with patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path), store_diff=True)

        assert "diff" in result
        assert "change" in result["diff"]

    def test_store_diff_empty(self, tmp_path):
        """When store_diff=True but no diff, no diff key."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if args == ["git", "diff"]:
                mock.stdout = ""
            elif "--cached" in args:
                mock.stdout = ""
            elif "rev-parse" in args:
                mock.stdout = "abc1234"
                mock.returncode = 0
            else:
                mock.stdout = ""
            return mock

        with patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path), store_diff=True)

        assert "diff" not in result

    def test_diff_capped_at_10kb(self, tmp_path):
        """Diff text is capped at 10240 bytes."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if args == ["git", "diff"]:
                mock.stdout = "x" * 20000
            elif "--cached" in args:
                mock.stdout = ""
            elif "rev-parse" in args:
                mock.stdout = "abc1234"
                mock.returncode = 0
            else:
                mock.stdout = "1 file changed"
            return mock

        with patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path), store_diff=True)

        assert len(result["diff"]) == 10240

    def test_workdir_none_uses_cwd(self):
        """When workdir is None, uses os.getcwd()."""
        with (
            patch("hermes_loop.git_utils.os.path.isdir", return_value=False),
            patch("hermes_loop.git_utils.os.getcwd", return_value="/fake/cwd"),
        ):
            result = _capture_git_state(None)
        assert result == {}

    def test_subprocess_timeout_returns_empty(self, tmp_path):
        """subprocess.TimeoutExpired returns empty dict."""
        with (
            patch("hermes_loop.git_utils.os.path.isdir", return_value=True),
            patch(
                "hermes_loop.git_utils.subprocess.run",
                side_effect=subprocess.TimeoutExpired("git", 10),
            ),
        ):
            result = _capture_git_state(str(tmp_path))
        assert result == {}

    def test_file_not_found_returns_empty(self, tmp_path):
        """FileNotFoundError (git not installed) returns empty dict."""
        with (
            patch("hermes_loop.git_utils.os.path.isdir", return_value=True),
            patch(
                "hermes_loop.git_utils.subprocess.run",
                side_effect=FileNotFoundError("git not found"),
            ),
        ):
            result = _capture_git_state(str(tmp_path))
        assert result == {}

    def test_all_fields_present(self, tmp_path):
        """All result fields present when git is available."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if args == ["git", "diff", "--stat"]:
                mock.stdout = "1 file changed, 5 insertions(+)"
            elif args == ["git", "diff", "--cached", "--stat"]:
                mock.stdout = ""
            elif args == ["git", "rev-parse", "--short", "HEAD"]:
                mock.stdout = "abc1234"
                mock.returncode = 0
            else:  # git diff
                mock.stdout = ""
            return mock

        with patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess):
            with patch("hermes_loop.git_utils.os.path.isdir", return_value=True):
                result = _capture_git_state(str(tmp_path), store_diff=False)

        assert "diff_stat" in result
        assert "diff_stat_cached" in result
        assert "head" in result
        assert "diff" not in result


# ===================================================================
# _git_auto_commit tests
# ===================================================================


class TestGitAutoCommit:
    """Tests for _git_auto_commit — auto-commits changes after iteration."""

    def test_no_git_dir_returns_none(self, tmp_path):
        """No .git directory returns None."""
        result = _git_auto_commit(str(tmp_path), 1, "test summary")
        assert result is None

    def test_no_changes_returns_none(self, tmp_path):
        """No changes after git add -A returns None."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if "diff" in args and "--cached" in args and "--quiet" in args:
                mock.returncode = 0  # no diff
            return mock

        with (
            patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess),
            patch("hermes_loop.git_utils.os.path.isdir", return_value=True),
        ):
            result = _git_auto_commit(str(tmp_path), 5, "no changes made")

        assert result is None

    def test_commit_successful(self, tmp_path):
        """Successful commit returns commit hash."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        calls = []

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            calls.append(args)
            if args == ["git", "add", "-A"]:
                mock.returncode = 0
            elif args == ["git", "diff", "--cached", "--quiet"]:
                mock.returncode = 1  # has changes
            elif args[:2] == ["git", "commit"]:
                mock.returncode = 0
            elif args == ["git", "rev-parse", "--short", "HEAD"]:
                mock.stdout = "deadbeef"
                mock.returncode = 0
            else:
                mock.returncode = 0
            return mock

        with (
            patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess),
            patch("hermes_loop.git_utils.os.path.isdir", return_value=True),
        ):
            result = _git_auto_commit(str(tmp_path), 3, "Implemented feature X")

        assert result == "deadbeef"
        # Verify commit message format
        commit_call = [c for c in calls if c[:2] == ["git", "commit"]]
        assert len(commit_call) == 1
        msg = commit_call[0][3]  # -m argument
        assert "infinite-loop iter #3" in msg
        assert "Implemented feature X" in msg

    def test_commit_message_truncated(self, tmp_path):
        """Summary is truncated to 80 chars in commit message."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        long_summary = "x" * 200
        captured_args = []

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            captured_args.append(args)
            if args == ["git", "add", "-A"]:
                mock.returncode = 0
            elif args == ["git", "diff", "--cached", "--quiet"]:
                mock.returncode = 1
            elif args[:2] == ["git", "commit"]:
                mock.returncode = 0
            elif args == ["git", "rev-parse", "--short", "HEAD"]:
                mock.stdout = "deadbeef"
                mock.returncode = 0
            else:
                mock.returncode = 0
            return mock

        with (
            patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess),
            patch("hermes_loop.git_utils.os.path.isdir", return_value=True),
        ):
            _git_auto_commit(str(tmp_path), 10, long_summary)

        # Check that commit message was truncated
        commit_call = [c for c in captured_args if c[:2] == ["git", "commit"]]
        assert len(commit_call) == 1
        msg = commit_call[0][3]
        # prefix "infinite-loop iter #10: " (25 chars) + 80-char summary = 105
        assert len(msg) <= 105

    @patch("hermes_loop.git_utils.os.path.isdir", return_value=True)
    def test_timeout_expired_returns_none(self, mock_isdir, tmp_path):
        """subprocess.TimeoutExpired returns None."""
        with patch(
            "hermes_loop.git_utils.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 10),
        ):
            result = _git_auto_commit(str(tmp_path), 1, "test")
        assert result is None

    @patch("hermes_loop.git_utils.os.path.isdir", return_value=True)
    def test_file_not_found_returns_none(self, mock_isdir, tmp_path):
        """FileNotFoundError (git not installed) returns None."""
        with patch(
            "hermes_loop.git_utils.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = _git_auto_commit(str(tmp_path), 1, "test")
        assert result is None

    def test_rev_parse_fails_returns_none(self, tmp_path):
        """When rev-parse fails after successful commit, returns None."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            if args == ["git", "add", "-A"]:
                mock.returncode = 0
            elif args == ["git", "diff", "--cached", "--quiet"]:
                mock.returncode = 1
            elif args[:2] == ["git", "commit"]:
                mock.returncode = 0
            elif args == ["git", "rev-parse", "--short", "HEAD"]:
                mock.returncode = 1
                mock.stdout = ""
            else:
                mock.returncode = 0
            return mock

        with (
            patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess),
            patch("hermes_loop.git_utils.os.path.isdir", return_value=True),
        ):
            result = _git_auto_commit(str(tmp_path), 3, "test")

        assert result is None

    def test_workdir_none_uses_cwd(self):
        """When workdir is None, uses os.getcwd()."""
        with (
            patch("hermes_loop.git_utils.os.path.isdir", return_value=False),
            patch("hermes_loop.git_utils.os.getcwd", return_value="/fake/cwd"),
        ):
            result = _git_auto_commit(None, 1, "test")
        assert result is None

    def test_iteration_number_in_message(self, tmp_path):
        """Iteration number appears in commit message."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        calls = []

        def mock_subprocess(args, **kwargs):
            mock = MagicMock()
            calls.append(args)
            if args == ["git", "add", "-A"]:
                mock.returncode = 0
            elif args == ["git", "diff", "--cached", "--quiet"]:
                mock.returncode = 1
            elif args[:2] == ["git", "commit"]:
                mock.returncode = 0
            elif args == ["git", "rev-parse", "--short", "HEAD"]:
                mock.stdout = "abc1234"
                mock.returncode = 0
            else:
                mock.returncode = 0
            return mock

        with (
            patch("hermes_loop.git_utils.subprocess.run", side_effect=mock_subprocess),
            patch("hermes_loop.git_utils.os.path.isdir", return_value=True),
        ):
            _git_auto_commit(str(tmp_path), 42, "test")

        commit_call = [c for c in calls if c[:2] == ["git", "commit"]]
        assert len(commit_call) == 1
        assert "iter #42" in commit_call[0][3]
