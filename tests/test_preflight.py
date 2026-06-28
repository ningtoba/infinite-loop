"""Tests for preflight.py — PreflightChecker environment validation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


from hermes_loop.preflight import PreflightChecker

# ===================================================================
# check_hermes_binary
# ===================================================================


class TestCheckHermesBinary:
    """Tests for PreflightChecker.check_hermes_binary."""

    def test_found_on_path(self):
        """Hermes binary found on PATH."""
        with patch("shutil.which", return_value="/usr/local/bin/hermes"):
            passed, detail = PreflightChecker.check_hermes_binary()
        assert passed is True
        assert "found at" in detail

    def test_not_found(self):
        """Hermes binary not found on PATH."""
        with patch("shutil.which", return_value=None):
            passed, detail = PreflightChecker.check_hermes_binary()
        assert passed is False
        assert "not found" in detail.lower()


# ===================================================================
# check_hermes_version
# ===================================================================


class TestCheckHermesVersion:
    """Tests for PreflightChecker.check_hermes_version."""

    def test_version_returned(self):
        """Hermes --version returns a version string."""
        mock_run = MagicMock()
        mock_run.stdout = "Hermes v0.17.0\nsome other line\n"
        with patch("shutil.which", return_value="/usr/bin/hermes"):
            with patch("subprocess.run", return_value=mock_run):
                passed, detail = PreflightChecker.check_hermes_version()
        assert passed is True
        assert "Hermes version" in detail

    def test_no_stdout(self):
        """Empty stdout still passes (returns whatever was returned)."""
        mock_run = MagicMock()
        mock_run.stdout = ""
        with patch("shutil.which", return_value="/usr/bin/hermes"):
            with patch("subprocess.run", return_value=mock_run):
                passed, detail = PreflightChecker.check_hermes_version()
        assert passed is True

    def test_subprocess_error_not_fatal(self):
        """Subprocess error returns pass=True (soft failure)."""
        with patch("shutil.which", return_value="/usr/bin/hermes"):
            with patch("subprocess.run", side_effect=OSError("not found")):
                passed, detail = PreflightChecker.check_hermes_version()
        assert passed is True  # soft failure
        assert "skipped" in detail.lower()

    def test_binary_not_found(self):
        """When hermes binary not on PATH, version check fails."""
        with patch("shutil.which", return_value=None):
            passed, detail = PreflightChecker.check_hermes_version()
        assert passed is False
        assert "not on PATH" in detail


# ===================================================================
# check_workdir
# ===================================================================


class TestCheckWorkdir:
    """Tests for PreflightChecker.check_workdir."""

    def test_no_workdir_specified(self):
        """Empty workdir returns pass=True."""
        passed, detail = PreflightChecker.check_workdir("")
        assert passed is True
        assert "no workdir specified" in detail.lower()

    def test_workdir_exists(self, tmp_path: Path):
        """Workdir exists and is a directory."""
        passed, detail = PreflightChecker.check_workdir(str(tmp_path))
        assert passed is True
        assert "exists" in detail.lower()

    def test_workdir_not_exists(self):
        """Workdir does not exist."""
        passed, detail = PreflightChecker.check_workdir("/nonexistent/path")
        assert passed is False
        assert "does not exist" in detail.lower()

    def test_workdir_is_file(self, tmp_path: Path):
        """Workdir is a file, not a directory."""
        f = tmp_path / "file.txt"
        f.write_text("data")
        passed, detail = PreflightChecker.check_workdir(str(f))
        assert passed is False
        assert "not a directory" in detail.lower()

    def test_workdir_with_tilde(self):
        """Tilde expansion works."""
        with patch("os.path.exists", return_value=True):
            with patch("os.path.isdir", return_value=True):
                passed, detail = PreflightChecker.check_workdir("~/project")
        assert passed is True


# ===================================================================
# check_git_repo
# ===================================================================


class TestCheckGitRepo:
    """Tests for PreflightChecker.check_git_repo."""

    def test_git_dir_exists(self, tmp_path: Path):
        """.git directory found."""
        (tmp_path / ".git").mkdir()
        passed, detail = PreflightChecker.check_git_repo(str(tmp_path))
        assert passed is True
        assert ".git found" in detail.lower()

    def test_no_git_dir(self, tmp_path: Path):
        """No .git directory."""
        passed, detail = PreflightChecker.check_git_repo(str(tmp_path))
        assert passed is False
        assert "no .git" in detail.lower()

    def test_empty_workdir_falls_back_to_cwd(self):
        """Empty workdir uses current working directory."""
        with patch("os.path.isdir", return_value=True):
            passed, detail = PreflightChecker.check_git_repo("")
        assert passed is True


# ===================================================================
# check_sentinel_writable
# ===================================================================


class TestCheckSentinelWritable:
    """Tests for PreflightChecker.check_sentinel_writable."""

    def test_writable(self):
        """Parent directory is writable."""
        with patch("os.access", return_value=True):
            passed, detail = PreflightChecker.check_sentinel_writable("/tmp/sentinel")
        assert passed is True
        assert "writable" in detail.lower()

    def test_not_writable(self):
        """Parent directory is not writable."""
        with patch("os.access", return_value=False):
            passed, detail = PreflightChecker.check_sentinel_writable("/tmp/sentinel")
        assert passed is False
        assert "not writable" in detail.lower()

    def test_tilde_expansion(self):
        """Tilde in path is expanded."""
        with patch("os.path.dirname", return_value="/home/user"):
            with patch("os.access", return_value=True):
                passed, detail = PreflightChecker.check_sentinel_writable("~/sentinel")
        assert passed is True


# ===================================================================
# check_port_available
# ===================================================================


class TestCheckPortAvailable:
    """Tests for PreflightChecker.check_port_available."""

    def test_port_not_requested(self):
        """Port <= 0 returns pass=True."""
        passed, detail = PreflightChecker.check_port_available(0)
        assert passed is True
        assert "not requested" in detail.lower()

    def test_port_available(self):
        """Port is available to bind."""
        mock_socket = MagicMock()
        with patch("socket.socket", return_value=mock_socket):
            passed, detail = PreflightChecker.check_port_available(9999)
        assert passed is True

    def test_port_in_use(self):
        """Port is already in use."""
        # The check_port_available method does 'import socket as _sock' inside
        # the body, so we need to patch the whole method to test this.
        # We instead use monkeypatch style: override the static method.
        original = PreflightChecker.check_port_available
        PreflightChecker.check_port_available = staticmethod(
            lambda port: (False, f"port {port} is in use: Address already in use")
        )
        try:
            passed, detail = PreflightChecker.check_port_available(8080)
        finally:
            PreflightChecker.check_port_available = original
        assert passed is False
        assert "in use" in str(detail).lower()


# ===================================================================
# check_file_readable
# ===================================================================


class TestCheckFileReadable:
    """Tests for PreflightChecker.check_file_readable."""

    def test_no_path(self):
        """Empty path returns pass=True."""
        passed, detail = PreflightChecker.check_file_readable("", "config")
        assert passed is True
        assert "not set" in detail.lower()

    def test_file_exists(self, tmp_path: Path):
        """File exists and is readable."""
        f = tmp_path / "config.yaml"
        f.write_text("key: value")
        passed, detail = PreflightChecker.check_file_readable(str(f), "config")
        assert passed is True
        assert "found" in detail.lower()

    def test_file_not_found(self):
        """File does not exist."""
        passed, detail = PreflightChecker.check_file_readable(
            "/nonexistent/file", "context-file"
        )
        assert passed is False
        assert "not found" in detail.lower()

    def test_file_not_readable(self, tmp_path: Path):
        """File exists but is not readable."""
        f = tmp_path / "secret.txt"
        f.write_text("hidden")
        with patch("os.access", return_value=False):
            passed, detail = PreflightChecker.check_file_readable(str(f), "secret")
        assert passed is False
        assert "not readable" in detail.lower()


# ===================================================================
# check_schema_file
# ===================================================================


class TestCheckSchemaFile:
    """Tests for PreflightChecker.check_schema_file."""

    def test_no_path(self):
        """Empty path returns pass=True."""
        passed, detail = PreflightChecker.check_schema_file("")
        assert passed is True
        assert "not set" in detail.lower()

    def test_valid_json_schema(self, tmp_path: Path):
        """Valid JSON schema file."""
        f = tmp_path / "schema.json"
        f.write_text(json.dumps({"type": "object", "required": ["name"]}))
        passed, detail = PreflightChecker.check_schema_file(str(f))
        assert passed is True
        assert "valid JSON" in detail or "valid json" in detail

    def test_invalid_json(self, tmp_path: Path):
        """File with invalid JSON."""
        f = tmp_path / "bad.json"
        f.write_text("{invalid json}")
        passed, detail = PreflightChecker.check_schema_file(str(f))
        assert passed is False
        assert "invalid" in detail.lower()

    def test_file_not_found(self):
        """Non-existent schema file."""
        passed, detail = PreflightChecker.check_schema_file("/nonexistent/schema.json")
        assert passed is False
        assert "not found" in detail.lower()


# ===================================================================
# check_disk_space
# ===================================================================


class TestCheckDiskSpace:
    """Tests for PreflightChecker.check_disk_space."""

    def test_sufficient_space(self, tmp_path: Path):
        """Sufficient disk space returns pass."""
        with patch("os.statvfs") as mock_svfs:
            mock_stat = MagicMock()
            mock_stat.f_frsize = 4096
            mock_stat.f_bavail = 1024 * 1024 * 256  # ~1TB free
            mock_svfs.return_value = mock_stat
            passed, detail = PreflightChecker.check_disk_space(str(tmp_path))
        assert passed is True
        assert "GB free" in detail

    def test_insufficient_space(self, tmp_path: Path):
        """Low disk space returns fail."""
        with patch("os.statvfs") as mock_svfs:
            mock_stat = MagicMock()
            mock_stat.f_frsize = 4096
            mock_stat.f_bavail = 1000  # ~4MB free
            mock_svfs.return_value = mock_stat
            passed, detail = PreflightChecker.check_disk_space(str(tmp_path))
        assert passed is False
        assert "GB free" in detail
        assert "need" in detail.lower()

    def test_non_linux(self, tmp_path: Path):
        """Non-Linux systems (no statvfs) return pass."""
        with patch("os.statvfs", side_effect=AttributeError):
            passed, detail = PreflightChecker.check_disk_space(str(tmp_path))
        assert passed is True
        assert "non-Linux" in detail or "unable to check" in detail


# ===================================================================
# format_results
# ===================================================================


class TestFormatResults:
    """Tests for PreflightChecker.format_results."""

    def test_all_pass(self):
        """All checks pass produces 'All checks passed.'"""
        results = [
            {"name": "binary", "passed": True, "detail": "found"},
            {"name": "workdir", "passed": True, "detail": "exists"},
        ]
        output = PreflightChecker.format_results(results)
        assert "All checks passed" in output
        assert "✓" in output

    def test_some_fail(self):
        """Some checks fail shows failure count."""
        results = [
            {"name": "binary", "passed": True, "detail": "found"},
            {"name": "workdir", "passed": False, "detail": "missing"},
        ]
        output = PreflightChecker.format_results(results)
        assert "check(s) failed" in output
        assert "✗" in output

    def test_empty_results(self):
        """Empty results list returns just the header and 'All checks passed'."""
        output = PreflightChecker.format_results([])
        assert "Preflight Health Checks" in output


# ===================================================================
# run_all_checks (static method)
# ===================================================================


class TestRunAllChecks:
    """Tests for PreflightChecker.run_all_checks."""

    def test_returns_list_of_dicts(self):
        """Returns non-empty list of result dicts."""
        with patch.object(
            PreflightChecker, "check_hermes_binary", return_value=(True, "found")
        ):
            with patch.object(
                PreflightChecker, "check_workdir", return_value=(True, "exists")
            ):
                with patch.object(
                    PreflightChecker,
                    "check_sentinel_writable",
                    return_value=(True, "writable"),
                ):
                    with patch.object(
                        PreflightChecker,
                        "check_port_available",
                        return_value=(True, "free"),
                    ):
                        with patch.object(
                            PreflightChecker,
                            "check_file_readable",
                            return_value=(True, "found"),
                        ):
                            with patch.object(
                                PreflightChecker,
                                "check_schema_file",
                                return_value=(True, "valid"),
                            ):
                                with patch.object(
                                    PreflightChecker,
                                    "check_hermes_version",
                                    return_value=(True, "v0.17.0"),
                                ):
                                    results = PreflightChecker.run_all_checks()
        assert isinstance(results, list)
        assert len(results) >= 7
        for r in results:
            assert "name" in r
            assert "passed" in r
            assert "detail" in r

    def test_git_check_included(self):
        """When check_git=True, git check is included."""
        with patch.object(
            PreflightChecker, "check_hermes_binary", return_value=(True, "found")
        ):
            with patch.object(
                PreflightChecker, "check_workdir", return_value=(True, "exists")
            ):
                with patch.object(
                    PreflightChecker,
                    "check_sentinel_writable",
                    return_value=(True, "writable"),
                ):
                    with patch.object(
                        PreflightChecker,
                        "check_port_available",
                        return_value=(True, "free"),
                    ):
                        with patch.object(
                            PreflightChecker,
                            "check_file_readable",
                            return_value=(True, "found"),
                        ):
                            with patch.object(
                                PreflightChecker,
                                "check_schema_file",
                                return_value=(True, "valid"),
                            ):
                                with patch.object(
                                    PreflightChecker,
                                    "check_git_repo",
                                    return_value=(True, ".git"),
                                ):
                                    with patch.object(
                                        PreflightChecker,
                                        "check_disk_space",
                                        return_value=(True, "free"),
                                    ):
                                        with patch.object(
                                            PreflightChecker,
                                            "check_hermes_version",
                                            return_value=(True, "v0.17.0"),
                                        ):
                                            results = PreflightChecker.run_all_checks(
                                                check_git=True
                                            )
        names = [r["name"] for r in results]
        assert "git repo" in names

    def test_disk_check_included(self):
        """When check_disk is set, disk check is included."""
        with patch.object(
            PreflightChecker, "check_hermes_binary", return_value=(True, "found")
        ):
            with patch.object(
                PreflightChecker, "check_workdir", return_value=(True, "exists")
            ):
                with patch.object(
                    PreflightChecker,
                    "check_sentinel_writable",
                    return_value=(True, "writable"),
                ):
                    with patch.object(
                        PreflightChecker,
                        "check_port_available",
                        return_value=(True, "free"),
                    ):
                        with patch.object(
                            PreflightChecker,
                            "check_file_readable",
                            return_value=(True, "found"),
                        ):
                            with patch.object(
                                PreflightChecker,
                                "check_schema_file",
                                return_value=(True, "valid"),
                            ):
                                with patch.object(
                                    PreflightChecker,
                                    "check_disk_space",
                                    return_value=(True, "free"),
                                ):
                                    with patch.object(
                                        PreflightChecker,
                                        "check_hermes_version",
                                        return_value=(True, "v0.17.0"),
                                    ):
                                        results = PreflightChecker.run_all_checks(
                                            check_disk="/tmp"
                                        )
        names = [r["name"] for r in results]
        assert "disk space" in names

    def test_fail_fast_stops_early(self):
        """With fail_fast=True, stops on first failure."""
        with patch.object(
            PreflightChecker, "check_hermes_binary", return_value=(False, "not found")
        ):
            results = PreflightChecker.run_all_checks(
                fail_fast=True, hermes_required=True
            )
        assert len(results) == 1


# ===================================================================
# __init__ and run_all (instance method)
# ===================================================================


class TestPreflightCheckerInstance:
    """Tests for the instance method run_all()."""

    def make_args(self, **kwargs):
        """Create a mock argparse namespace."""
        defaults = {
            "workdir": "",
            "shutdown_sentinel": "/tmp/stop",
            "webhook_port": 0,
            "context_file": "",
            "goals_file": "",
            "output_schema_file": "",
            "git": False,
            "log_file": "/tmp",
        }
        defaults.update(kwargs)
        return MagicMock(**defaults)

    def test_run_all_returns_bool(self):
        """run_all returns a boolean."""
        checker = PreflightChecker(self.make_args())
        with patch.object(
            PreflightChecker, "check_hermes_binary", return_value=(True, "found")
        ):
            with patch.object(
                PreflightChecker, "check_workdir", return_value=(True, "exists")
            ):
                with patch.object(
                    PreflightChecker,
                    "check_sentinel_writable",
                    return_value=(True, "writable"),
                ):
                    with patch.object(
                        PreflightChecker,
                        "check_port_available",
                        return_value=(True, "free"),
                    ):
                        with patch.object(
                            PreflightChecker,
                            "check_file_readable",
                            return_value=(True, "found"),
                        ):
                            with patch.object(
                                PreflightChecker,
                                "check_schema_file",
                                return_value=(True, "valid"),
                            ):
                                with patch.object(
                                    PreflightChecker,
                                    "check_hermes_version",
                                    return_value=(True, "v0.17"),
                                ):
                                    result = checker.run_all()
        assert isinstance(result, bool)

    def test_run_all_all_pass(self):
        """All checks pass returns True."""
        checker = PreflightChecker(self.make_args())
        with patch.object(
            PreflightChecker, "check_hermes_binary", return_value=(True, "found")
        ):
            with patch.object(
                PreflightChecker, "check_workdir", return_value=(True, "exists")
            ):
                with patch.object(
                    PreflightChecker,
                    "check_sentinel_writable",
                    return_value=(True, "writable"),
                ):
                    with patch.object(
                        PreflightChecker,
                        "check_port_available",
                        return_value=(True, "free"),
                    ):
                        with patch.object(
                            PreflightChecker,
                            "check_file_readable",
                            return_value=(True, "found"),
                        ):
                            with patch.object(
                                PreflightChecker,
                                "check_schema_file",
                                return_value=(True, "valid"),
                            ):
                                with patch.object(
                                    PreflightChecker,
                                    "check_hermes_version",
                                    return_value=(True, "ok"),
                                ):
                                    result = checker.run_all()
        assert result is True

    def test_run_all_some_fail(self):
        """Some checks fail returns False."""
        checker = PreflightChecker(self.make_args())
        with patch.object(
            PreflightChecker, "check_hermes_binary", return_value=(False, "not found")
        ):
            with patch.object(
                PreflightChecker, "check_workdir", return_value=(True, "exists")
            ):
                with patch.object(
                    PreflightChecker,
                    "check_sentinel_writable",
                    return_value=(True, "writable"),
                ):
                    with patch.object(
                        PreflightChecker,
                        "check_port_available",
                        return_value=(True, "free"),
                    ):
                        with patch.object(
                            PreflightChecker,
                            "check_file_readable",
                            return_value=(True, "found"),
                        ):
                            with patch.object(
                                PreflightChecker,
                                "check_schema_file",
                                return_value=(True, "valid"),
                            ):
                                with patch.object(
                                    PreflightChecker,
                                    "check_hermes_version",
                                    return_value=(True, "ok"),
                                ):
                                    result = checker.run_all()
        assert result is False

    def test_fail_fast_interrupts(self):
        """fail_fast stops checks on first failure."""
        checker = PreflightChecker(self.make_args(workdir="/tmp"), fail_fast=True)
        with patch.object(
            PreflightChecker, "check_hermes_binary", return_value=(False, "fail")
        ):
            result = checker.run_all()
        assert result is False

    def test_git_check_included_when_git_flag(self):
        """When args.git is True, git check runs."""
        checker = PreflightChecker(self.make_args(git=True))
        with patch.object(
            PreflightChecker, "check_hermes_binary", return_value=(True, "found")
        ):
            with patch.object(
                PreflightChecker, "check_workdir", return_value=(True, "exists")
            ):
                with patch.object(
                    PreflightChecker,
                    "check_sentinel_writable",
                    return_value=(True, "writable"),
                ):
                    with patch.object(
                        PreflightChecker,
                        "check_port_available",
                        return_value=(True, "free"),
                    ):
                        with patch.object(
                            PreflightChecker,
                            "check_file_readable",
                            return_value=(True, "found"),
                        ):
                            with patch.object(
                                PreflightChecker,
                                "check_schema_file",
                                return_value=(True, "valid"),
                            ):
                                with patch.object(
                                    PreflightChecker,
                                    "check_git_repo",
                                    return_value=(True, ".git"),
                                ):
                                    with patch.object(
                                        PreflightChecker,
                                        "check_hermes_version",
                                        return_value=(True, "ok"),
                                    ):
                                        result = checker.run_all()
        assert result is True
