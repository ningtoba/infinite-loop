"""Tests for pi_loop.preflight — preflight health checks."""

import json
from unittest.mock import Mock, patch

from pi_loop.preflight import PreflightChecker


class TestCheckPythonVersion:
    def test_meets_minimum(self):
        """check_python_version returns True for Python >= 3.10."""
        result = PreflightChecker.check_python_version()
        assert result[0] == True
        assert "Python" in result[1]


class TestCheckWorkdir:
    def test_empty_workdir(self):
        """check_workdir with empty string returns True."""
        result = PreflightChecker.check_workdir("")
        assert result[0] == True
        assert "current dir" in result[1]

    def test_exists(self, tmp_path):
        """check_workdir returns True when directory exists."""
        result = PreflightChecker.check_workdir(str(tmp_path))
        assert result[0] == True
        assert str(tmp_path) in result[1]

    def test_not_exists(self):
        """check_workdir returns False when directory does not exist."""
        result = PreflightChecker.check_workdir("/nonexistent/path")
        assert result[0] == False

    def test_not_a_directory(self, tmp_path):
        """check_workdir returns False when path is not a directory."""
        f = tmp_path / "file.txt"
        f.write_text("test")
        result = PreflightChecker.check_workdir(str(f))
        assert result[0] == False


class TestCheckGitRepo:
    def test_has_git_dir(self, tmp_path):
        """check_git_repo returns True when .git exists."""
        (tmp_path / ".git").mkdir()
        result = PreflightChecker.check_git_repo(str(tmp_path))
        assert result[0] == True

    def test_no_git_dir(self, tmp_path):
        """check_git_repo returns False when .git does not exist."""
        result = PreflightChecker.check_git_repo(str(tmp_path))
        assert result[0] == False

    def test_empty_workdir_uses_cwd(self):
        """check_git_repo with empty workdir uses os.getcwd."""
        # Should not crash, will check cwd
        with patch("os.path.isdir", return_value=False):
            result = PreflightChecker.check_git_repo("")
        assert result[0] == False


class TestCheckSentinelWritable:
    def test_writable(self, tmp_path):
        """check_sentinel_writable returns True for writable directory."""
        sentinel = str(tmp_path / "sentinel")
        result = PreflightChecker.check_sentinel_writable(sentinel)
        assert result[0] == True

    def test_not_writable(self):
        """check_sentinel_writable returns False for non-writable."""
        with patch("os.access", return_value=False):
            result = PreflightChecker.check_sentinel_writable("/proc/foo")
        assert result[0] == False


class TestCheckPortAvailable:
    def test_port_zero(self):
        """check_port_available with port <= 0 returns True."""
        result = PreflightChecker.check_port_available(0)
        assert result[0] == True

    def test_port_available(self):
        """check_port_available returns True when port can be bound."""
        with patch("socket.socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.bind.return_value = None
            result = PreflightChecker.check_port_available(12345)
        assert result[0] == True

    def test_port_in_use(self):
        """check_port_available returns False when port is in use."""
        with patch("socket.socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.bind.side_effect = OSError("Address in use")
            result = PreflightChecker.check_port_available(12345)
        assert result[0] == False


class TestCheckFileReadable:
    def test_empty_path(self):
        """check_file_readable with empty path returns True."""
        result = PreflightChecker.check_file_readable("", "test-file")
        assert result[0] == True

    def test_file_exists(self, tmp_path):
        """check_file_readable returns True for existing readable file."""
        f = tmp_path / "test.txt"
        f.write_text("data")
        result = PreflightChecker.check_file_readable(str(f), "test-file")
        assert result[0] == True
        assert str(f) in result[1]

    def test_file_not_found(self, tmp_path):
        """check_file_readable returns False when file doesn't exist."""
        result = PreflightChecker.check_file_readable(str(tmp_path / "nonexistent.txt"), "test-file")
        assert result[0] == False


class TestCheckSchemaFile:
    def test_empty_path(self):
        """check_schema_file with empty path returns True."""
        result = PreflightChecker.check_schema_file("")
        assert result[0] == True

    def test_valid_json(self, tmp_path):
        """check_schema_file returns True for valid JSON schema."""
        f = tmp_path / "schema.json"
        f.write_text(json.dumps({"type": "object"}))
        result = PreflightChecker.check_schema_file(str(f))
        assert result[0] == True

    def test_invalid_json(self, tmp_path):
        """check_schema_file returns False for invalid JSON."""
        f = tmp_path / "schema.json"
        f.write_text("not json")
        result = PreflightChecker.check_schema_file(str(f))
        assert result[0] == False


class TestCheckDiskSpace:
    def test_sufficient_space(self):
        """check_disk_space returns True when free space is sufficient."""
        with patch("os.statvfs") as mock_vfs:
            mock_vfs.return_value = Mock(f_frsize=4096, f_bavail=1024 * 1024 * 1024)
            result = PreflightChecker.check_disk_space("/tmp")
        assert result[0] == True


class TestRunAllChecks:
    def test_runs_all_checks(self):
        """run_all_checks runs all standard checks."""
        with (
            patch("pi_loop.preflight.PreflightChecker.check_python_version", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_workdir", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_sentinel_writable", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_port_available", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_file_readable", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_schema_file", return_value=(True, "OK")),
        ):
            results = PreflightChecker.run_all_checks()
        assert len(results) == 7
        assert all(r["passed"] for r in results)

    def test_fail_fast_stops(self):
        """run_all_checks with fail_fast=True stops after first failure."""
        with patch("pi_loop.preflight.PreflightChecker.check_python_version", return_value=(False, "FAIL")):
            results = PreflightChecker.run_all_checks(fail_fast=True)
        assert len(results) == 1
        assert results[0]["passed"] == False

    def test_includes_git_check(self):
        """run_all_checks includes git check when requested."""
        with (
            patch("pi_loop.preflight.PreflightChecker.check_python_version", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_workdir", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_sentinel_writable", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_port_available", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_file_readable", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_git_repo", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_schema_file", return_value=(True, "OK")),
        ):
            results = PreflightChecker.run_all_checks(check_git=True)
        assert len(results) == 8

    def test_includes_disk_check(self):
        """run_all_checks includes disk space check when requested."""
        with (
            patch("pi_loop.preflight.PreflightChecker.check_python_version", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_workdir", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_sentinel_writable", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_port_available", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_file_readable", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_disk_space", return_value=(True, "OK")),
            patch("pi_loop.preflight.PreflightChecker.check_schema_file", return_value=(True, "OK")),
        ):
            results = PreflightChecker.run_all_checks(check_disk="/tmp")
        assert len(results) == 8


class TestPreflightChecker:
    def test_constructor(self):
        """PreflightChecker can be instantiated with Mock args."""
        mock_args = Mock()
        mock_args.workdir = "/tmp"
        mock_args.shutdown_sentinel = "/tmp/sentinel"
        mock_args.webhook_port = 0
        mock_args.context_file = ""
        mock_args.goals_file = ""
        mock_args.output_schema_file = ""
        checker = PreflightChecker(mock_args, fail_fast=True)
        assert checker._fail_fast == True

    def test_run_all_true(self):
        """PreflightChecker.run_all returns True when all pass."""
        with patch.object(
            PreflightChecker,
            "run_all_checks",
            return_value=[
                {"name": "test1", "passed": True, "detail": "OK"},
                {"name": "test2", "passed": True, "detail": "OK"},
            ],
        ):
            mock_args = Mock()
            mock_args.workdir = "/tmp"
            mock_args.shutdown_sentinel = "/tmp/sentinel"
            mock_args.webhook_port = 0
            mock_args.context_file = ""
            mock_args.goals_file = ""
            mock_args.output_schema_file = ""
            mock_args.git = False
            mock_args.log_file = "/tmp/log"
            checker = PreflightChecker(mock_args, fail_fast=False)
            result = checker.run_all()
        assert result == True

    def test_format_results(self):
        """format_results produces readable output."""
        results = [
            {"name": "python version", "passed": True, "detail": "OK"},
            {"name": "workdir", "passed": False, "detail": "does not exist"},
        ]
        output = PreflightChecker.format_results(results)
        assert "✓" in output
        assert "✗" in output
        assert "All checks passed" not in output
        assert "1 check(s) failed" in output
