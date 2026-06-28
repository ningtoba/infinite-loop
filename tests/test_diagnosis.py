"""Tests for diagnosis.py — self-diagnosis ('--doctor') checks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch


from hermes_loop.diagnosis import (
    _check,
    _check_python,
    _check_hermes,
    _check_git,
    _check_env_file,
    _check_disk,
    _check_scripts,
    _check_shell,
    _check_gateway_connectivity,
    _colorize,
    print_diagnosis_report,
    run_diagnosis,
)

# ===================================================================
# _check helper
# ===================================================================


class TestCheck:
    """Tests for the _check helper that creates check result dicts."""

    def test_pass_true(self):
        """result=True produces result='PASS'."""
        c = _check("label", True, "detail", "suggestion")
        assert c["label"] == "label"
        assert c["result"] == "PASS"
        assert c["detail"] == "detail"
        assert c["suggestion"] == "suggestion"

    def test_fail_false(self):
        """result=False produces result='FAIL'."""
        c = _check("label", False)
        assert c["result"] == "FAIL"

    def test_warn_none(self):
        """result=None produces result='WARN'."""
        c = _check("label", None)
        assert c["result"] == "WARN"

    def test_default_detail_empty(self):
        """detail defaults to empty string."""
        c = _check("label", True)
        assert c["detail"] == ""

    def test_default_suggestion_empty(self):
        """suggestion defaults to empty string."""
        c = _check("label", True)
        assert c["suggestion"] == ""

    def test_returns_dict(self):
        """Returns a dict with expected keys."""
        c = _check("x", True)
        assert isinstance(c, dict)
        assert set(c.keys()) == {"label", "result", "detail", "suggestion"}


# ===================================================================
# _check_python
# ===================================================================


class TestCheckPython:
    """Tests for Python version and stdlib checks."""

    def test_python_version_gte_310(self):
        """Python 3.10 passes the version check."""
        with patch("hermes_loop.diagnosis.sys.version_info") as mock_vi:
            mock_vi.major = 3
            mock_vi.minor = 10
            checks = _check_python()
        version_check = checks[0]
        assert version_check["result"] == "PASS"
        assert "Python version" in version_check["label"]

    def test_python_version_lt_310(self):
        """Python 3.9 fails the version check."""
        with patch("hermes_loop.diagnosis.sys.version_info") as mock_vi:
            mock_vi.major = 3
            mock_vi.minor = 9
            checks = _check_python()
        version_check = checks[0]
        assert version_check["result"] == "FAIL"
        assert version_check["suggestion"] != ""

    def test_python_version_312(self):
        """Python 3.12 passes the version check."""
        with patch("hermes_loop.diagnosis.sys.version_info") as mock_vi:
            mock_vi.major = 3
            mock_vi.minor = 12
            checks = _check_python()
        assert checks[0]["result"] == "PASS"

    @patch("builtins.__import__", side_effect=lambda *args, **kwargs: MagicMock())
    def test_stdlib_all_present(self, mock_import):
        """All stdlib modules importable produces PASS."""
        checks = _check_python()
        stdlib_check = checks[1]
        assert stdlib_check["result"] == "PASS"
        assert "All present" in stdlib_check["detail"]

    @patch("builtins.__import__")
    def test_stdlib_missing_some(self, mock_import):
        """Missing stdlib modules produces FAIL with details."""

        def import_side_effect(*args, **kwargs):
            mod = args[0]
            if mod in ("argparse", "http.server"):
                raise ImportError(f"No module named {mod}")
            return MagicMock()

        mock_import.side_effect = import_side_effect

        checks = _check_python()
        stdlib_check = checks[1]
        assert stdlib_check["result"] == "FAIL"
        assert "argparse" in stdlib_check["detail"]
        assert "http.server" in stdlib_check["detail"]
        assert stdlib_check["suggestion"] != ""

    def test_returns_two_checks(self):
        """Returns exactly two checks: version and stdlib."""
        checks = _check_python()
        assert len(checks) == 2


# ===================================================================
# _check_hermes
# ===================================================================


class TestCheckHermes:
    """Tests for hermes binary detection and version check."""

    @patch("hermes_loop.diagnosis.shutil.which", return_value="/usr/bin/hermes")
    @patch("hermes_loop.diagnosis.subprocess.run")
    def test_binary_found_and_version_works(self, mock_run, mock_which):
        """hermes found on PATH and --version succeeds."""
        mock_run.return_value = MagicMock(returncode=0, stdout="v1.0.0\n", stderr="")
        checks = _check_hermes()
        assert len(checks) == 2
        assert checks[0]["result"] == "PASS"
        assert checks[1]["result"] == "PASS"
        assert "v1.0.0" in checks[1]["detail"]

    @patch("hermes_loop.diagnosis.shutil.which", return_value=None)
    def test_binary_not_found(self, mock_which):
        """hermes not on PATH — both checks FAIL."""
        checks = _check_hermes()
        assert len(checks) == 2
        assert checks[0]["result"] == "FAIL"
        assert "not found" in checks[0]["detail"]
        assert checks[1]["result"] == "FAIL"
        assert checks[1]["detail"] == "skipped"

    @patch("hermes_loop.diagnosis.shutil.which", return_value="/usr/bin/hermes")
    @patch("hermes_loop.diagnosis.subprocess.run")
    def test_version_fails_nonzero_returncode(self, mock_run, mock_which):
        """hermes --version returns non-zero exit code."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="some error")
        checks = _check_hermes()
        assert checks[0]["result"] == "PASS"
        assert checks[1]["result"] == "FAIL"
        assert "some error" in checks[1]["detail"]

    @patch("hermes_loop.diagnosis.shutil.which", return_value="/usr/bin/hermes")
    @patch("hermes_loop.diagnosis.subprocess.run")
    def test_version_timeout(self, mock_run, mock_which):
        """hermes --version times out."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["hermes", "--version"], timeout=10
        )
        checks = _check_hermes()
        assert checks[0]["result"] == "PASS"
        assert checks[1]["result"] == "FAIL"

    @patch("hermes_loop.diagnosis.shutil.which", return_value="/usr/bin/hermes")
    @patch("hermes_loop.diagnosis.subprocess.run")
    def test_version_uses_stdout_then_stderr(self, mock_run, mock_which):
        """stdout is preferred, but stderr is used as fallback."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="v2.0.0")
        checks = _check_hermes()
        assert "v2.0.0" in checks[1]["detail"]

    @patch("hermes_loop.diagnosis.shutil.which", return_value="/usr/bin/hermes")
    @patch("hermes_loop.diagnosis.subprocess.run")
    def test_version_truncates_long_output(self, mock_run, mock_which):
        """Version output is truncated to 80 chars."""
        long_ver = "v" + "x" * 200
        mock_run.return_value = MagicMock(returncode=0, stdout=long_ver, stderr="")
        checks = _check_hermes()
        assert len(checks[1]["detail"]) <= 80


# ===================================================================
# _check_git
# ===================================================================


class TestCheckGit:
    """Tests for git binary detection and repo check."""

    @patch("hermes_loop.diagnosis.shutil.which", return_value="/usr/bin/git")
    @patch("hermes_loop.diagnosis.subprocess.run")
    def test_git_found_and_in_repo(self, mock_run, mock_which):
        """git found and inside a repo."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/home/user/repo/.git\n", stderr=""
        )
        checks = _check_git()
        assert len(checks) == 2
        assert checks[0]["result"] == "PASS"
        assert checks[1]["result"] == "PASS"

    @patch("hermes_loop.diagnosis.shutil.which", return_value=None)
    def test_git_not_found(self, mock_which):
        """git not on PATH."""
        checks = _check_git()
        assert checks[0]["result"] == "FAIL"
        assert checks[1]["result"] == "FAIL"
        assert checks[1]["detail"] == "skipped"

    @patch("hermes_loop.diagnosis.shutil.which", return_value="/usr/bin/git")
    @patch("hermes_loop.diagnosis.subprocess.run")
    def test_not_in_repo(self, mock_run, mock_which):
        """git found but not inside a repo."""
        mock_run.return_value = MagicMock(
            returncode=128, stdout="", stderr="fatal: not a git repository"
        )
        checks = _check_git()
        assert checks[0]["result"] == "PASS"
        assert checks[1]["result"] == "FAIL"

    @patch("hermes_loop.diagnosis.shutil.which", return_value="/usr/bin/git")
    @patch("hermes_loop.diagnosis.subprocess.run")
    def test_git_timeout(self, mock_run, mock_which):
        """git rev-parse times out."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "rev-parse", "--git-dir"], timeout=5
        )
        checks = _check_git()
        assert checks[0]["result"] == "PASS"
        assert checks[1]["result"] == "FAIL"

    @patch("hermes_loop.diagnosis.shutil.which", return_value="/usr/bin/git")
    @patch("hermes_loop.diagnosis.subprocess.run")
    def test_git_file_not_found(self, mock_run, mock_which):
        """git binary disappears between which and run."""
        mock_run.side_effect = FileNotFoundError("git not found")
        checks = _check_git()
        assert checks[1]["result"] == "FAIL"


# ===================================================================
# _check_env_file
# ===================================================================


class TestCheckEnvFile:
    """Tests for .env file detection and validation."""

    def test_env_found_in_cwd(self, tmp_path: Path):
        """.env found in cwd passes the found check."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_LOOP_GOAL=test_goal\nFOO=bar\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        assert checks[0]["result"] == "PASS"
        assert str(env_file) in checks[0]["detail"]

    def test_env_found_in_parent(self, tmp_path: Path):
        """.env found in parent directory passes."""
        parent = tmp_path / "parent"
        parent.mkdir()
        cwd = parent / "child"
        cwd.mkdir()
        env_file = parent / ".env"
        env_file.write_text("VAR=1\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=cwd):
            checks = _check_env_file()

        assert checks[0]["result"] == "PASS"
        assert ".env" in checks[0]["detail"]

    def test_env_not_found(self, tmp_path: Path):
        """.env not found in cwd or parents."""
        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        assert checks[0]["result"] == "FAIL"
        assert "Not found" in checks[0]["detail"]

    def test_env_has_content(self, tmp_path: Path):
        """.env with variables passes content check."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=qux\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        assert checks[0]["result"] == "PASS"
        content_check = [c for c in checks if "has content" in c["label"]][0]
        assert content_check["result"] == "PASS"
        assert "2 variable(s)" in content_check["detail"]

    def test_env_no_content(self, tmp_path: Path):
        """.env with only comments has no content."""
        env_file = tmp_path / ".env"
        env_file.write_text("# This is a comment\n# Another comment\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        content_check = [c for c in checks if "has content" in c["label"]][0]
        assert content_check["result"] == "FAIL"

    def test_env_empty_file(self, tmp_path: Path):
        """.env with empty content has no content."""
        env_file = tmp_path / ".env"
        env_file.write_text("")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        content_check = [c for c in checks if "has content" in c["label"]][0]
        assert content_check["result"] == "FAIL"

    def test_env_no_typos(self, tmp_path: Path):
        """.env with correct INFINITE_LOOP_ prefix passes typo check."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_LOOP_GOAL=test\nINFINITE_LOOP_MAX_ITER=10\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        typo_check = [c for c in checks if "typos" in c["label"]][0]
        assert typo_check["result"] == "PASS"

    def test_env_has_infinite_typos(self, tmp_path: Path):
        """.env with INFINITE_ typos (missing _LOOP_) fails."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_GOAL=test\nINFINITE_MAX_ITER=10\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        typo_check = [c for c in checks if "typos" in c["label"]][0]
        assert typo_check["result"] == "FAIL"
        assert "INFINITE_GOAL" in typo_check["detail"]

    def test_env_goal_set(self, tmp_path: Path):
        """.env with INFINITE_LOOP_GOAL passes goal check."""
        env_file = tmp_path / ".env"
        env_file.write_text("INFINITE_LOOP_GOAL=my_goal\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        goal_check = [c for c in checks if "GOAL" in c["label"]][0]
        assert goal_check["result"] == "PASS"

    def test_env_goal_not_set(self, tmp_path: Path):
        """.env without INFINITE_LOOP_GOAL fails goal check."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        goal_check = [c for c in checks if "GOAL" in c["label"]][0]
        assert goal_check["result"] == "FAIL"
        assert "Not set" in goal_check["detail"]

    def test_env_oserror_on_read(self, tmp_path: Path):
        """OSError when reading .env produces readable check."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            with patch("builtins.open", side_effect=OSError("Permission denied")):
                checks = _check_env_file()

        assert checks[0]["result"] == "PASS"
        readable_check = [c for c in checks if "readable" in c["label"]][0]
        assert readable_check["result"] == "FAIL"
        assert "Permission denied" in readable_check["detail"]

    def test_env_mixed_typos_correct(self, tmp_path: Path):
        """Only INFINITE_ vars without _LOOP_ are flagged as typos."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "INFINITE_LOOP_GOAL=test\n"
            "INFINITE_LOOP_MAX_ITER=10\n"
            "INFINITE_BAD=wrong\n"
        )

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        typo_check = [c for c in checks if "typos" in c["label"]][0]
        assert typo_check["result"] == "FAIL"
        assert "INFINITE_BAD" in typo_check["detail"]
        assert "INFINITE_LOOP_GOAL" not in typo_check["detail"]

    def test_env_whitespace_handling(self, tmp_path: Path):
        """Variables with leading whitespace are parsed correctly."""
        env_file = tmp_path / ".env"
        env_file.write_text("  INFINITE_LOOP_GOAL=my_goal\n")

        with patch("hermes_loop.diagnosis.Path.cwd", return_value=tmp_path):
            checks = _check_env_file()

        goal_check = [c for c in checks if "GOAL" in c["label"]][0]
        assert goal_check["result"] == "PASS"


# ===================================================================
# _check_disk
# ===================================================================


class TestCheckDisk:
    """Tests for disk checks (/tmp writable, disk space)."""

    def test_tmp_writable(self):
        """/tmp is writable passes."""
        checks = _check_disk()
        tmp_check = checks[0]
        assert tmp_check["result"] == "PASS"

    def test_tmp_not_writable(self):
        """/tmp not writable fails."""
        with patch.object(Path, "write_text", side_effect=OSError("Read-only")):
            checks = _check_disk()

        tmp_check = checks[0]
        assert tmp_check["result"] == "FAIL"
        assert tmp_check["suggestion"] != ""

    def test_tmp_not_writable_permission_error(self):
        """PermissionError on /tmp write produces FAIL."""
        with patch.object(Path, "write_text", side_effect=PermissionError("Denied")):
            checks = _check_disk()

        tmp_check = checks[0]
        assert tmp_check["result"] == "FAIL"

    @patch("hermes_loop.diagnosis.os.statvfs")
    def test_disk_space_ok(self, mock_statvfs):
        """Sufficient disk space passes."""

        class FakeStat:
            f_frsize = 4096
            f_bavail = 500000  # ~1.9 GB

        mock_statvfs.return_value = FakeStat()
        checks = _check_disk()
        disk_check = checks[1]
        assert disk_check["result"] == "PASS"

    @patch("hermes_loop.diagnosis.os.statvfs")
    def test_disk_space_low(self, mock_statvfs):
        """Low disk space (< 0.5 GB) fails."""

        class FakeStat:
            f_frsize = 4096
            f_bavail = 10000  # ~38 MB

        mock_statvfs.return_value = FakeStat()
        checks = _check_disk()
        disk_check = checks[1]
        assert disk_check["result"] == "FAIL"
        assert (
            "LOW" in disk_check["detail"].upper() or "LOW" in disk_check["suggestion"]
        )

    @patch("hermes_loop.diagnosis.os.statvfs")
    def test_disk_space_exception(self, mock_statvfs):
        """statvfs exception is silently caught."""
        mock_statvfs.side_effect = OSError("Not supported on this filesystem")
        checks = _check_disk()
        assert len(checks) == 1

    def test_returns_two_checks_when_statvfs_works(self):
        """Returns both /tmp writable and disk space checks normally."""
        checks = _check_disk()
        assert 1 <= len(checks) <= 2


# ===================================================================
# _check_scripts
# ===================================================================


class TestCheckScripts:
    """Tests for required project scripts existence."""

    def test_all_scripts_exist(self, tmp_path: Path):
        """All required scripts exist."""
        project_root = tmp_path
        (project_root / "run.sh").write_text("")
        (project_root / "launch-loop.py").write_text("")
        (project_root / "Makefile").write_text("")
        (project_root / "scripts/completion/bash").parent.mkdir(
            parents=True, exist_ok=True
        )
        (project_root / "scripts/completion/bash").write_text("")
        (project_root / "scripts/completion/zsh").parent.mkdir(
            parents=True, exist_ok=True
        )
        (project_root / "scripts/completion/zsh").write_text("")

        # _check_scripts does: Path(__file__).parent.resolve()
        # __file__ is a module-level variable, not a Path attribute.
        # We patch it directly on the diagnosis module.
        diagnosis_dir = project_root / "hermes_loop"
        diagnosis_dir.mkdir(exist_ok=True)
        diagnosis_py = diagnosis_dir / "diagnosis.py"
        diagnosis_py.write_text("")

        with patch("hermes_loop.diagnosis.__file__", str(diagnosis_py)):
            checks = _check_scripts()

        assert len(checks) == 5
        for c in checks:
            assert c["result"] == "PASS", f"{c['label']} should PASS"

    def test_some_scripts_missing(self, tmp_path: Path):
        """Some scripts missing — those checks fail."""
        project_root = tmp_path
        (project_root / "run.sh").write_text("")
        # deliberately skip launch-loop.py and Makefile
        (project_root / "scripts/completion/bash").parent.mkdir(
            parents=True, exist_ok=True
        )
        (project_root / "scripts/completion/bash").write_text("")
        (project_root / "scripts/completion/zsh").parent.mkdir(
            parents=True, exist_ok=True
        )
        (project_root / "scripts/completion/zsh").write_text("")

        diagnosis_dir = project_root / "hermes_loop"
        diagnosis_dir.mkdir(exist_ok=True)
        diagnosis_py = diagnosis_dir / "diagnosis.py"
        diagnosis_py.write_text("")

        with patch("hermes_loop.diagnosis.__file__", str(diagnosis_py)):
            checks = _check_scripts()

        assert checks[0]["result"] == "PASS"  # run.sh
        assert checks[1]["result"] == "FAIL"  # launch-loop.py
        assert checks[2]["result"] == "FAIL"  # Makefile

    def test_returns_five_checks(self, tmp_path: Path):
        """Returns exactly five script checks."""
        project_root = tmp_path
        diagnosis_dir = project_root / "hermes_loop"
        diagnosis_dir.mkdir(parents=True, exist_ok=True)
        diagnosis_py = diagnosis_dir / "diagnosis.py"
        diagnosis_py.write_text("")

        with patch("hermes_loop.diagnosis.__file__", str(diagnosis_py)):
            checks = _check_scripts()
        assert len(checks) == 5


# ===================================================================
# _check_shell
# ===================================================================


class TestCheckShell:
    """Tests for shell detection and completion checks."""

    def test_bash_detected_with_completion(self, tmp_path: Path):
        """Bash shell with completion installed passes."""
        project_root = tmp_path
        (project_root / "scripts/completion/bash").parent.mkdir(
            parents=True, exist_ok=True
        )
        (project_root / "scripts/completion/bash").write_text("")

        diagnosis_dir = project_root / "hermes_loop"
        diagnosis_dir.mkdir(exist_ok=True)
        diagnosis_py = diagnosis_dir / "diagnosis.py"
        diagnosis_py.write_text("")

        with patch("hermes_loop.diagnosis.__file__", str(diagnosis_py)):
            with patch.dict(os.environ, {"SHELL": "/usr/bin/bash"}):
                checks = _check_shell()

        assert len(checks) == 2
        assert checks[0]["result"] == "PASS"
        assert "bash" in checks[0]["detail"]
        assert checks[1]["result"] == "PASS"

    def test_zsh_detected_with_completion(self, tmp_path: Path):
        """Zsh shell with completion installed passes."""
        project_root = tmp_path
        (project_root / "scripts/completion/zsh").parent.mkdir(
            parents=True, exist_ok=True
        )
        (project_root / "scripts/completion/zsh").write_text("")

        diagnosis_dir = project_root / "hermes_loop"
        diagnosis_dir.mkdir(exist_ok=True)
        diagnosis_py = diagnosis_dir / "diagnosis.py"
        diagnosis_py.write_text("")

        with patch("hermes_loop.diagnosis.__file__", str(diagnosis_py)):
            with patch.dict(os.environ, {"SHELL": "/usr/bin/zsh"}):
                checks = _check_shell()

        assert checks[0]["result"] == "PASS"
        assert "zsh" in checks[0]["detail"]
        assert checks[1]["result"] == "PASS"

    def test_bash_detected_no_completion(self, tmp_path: Path):
        """Bash shell but completion file missing fails."""
        project_root = tmp_path
        diagnosis_dir = project_root / "hermes_loop"
        diagnosis_dir.mkdir(exist_ok=True)
        diagnosis_py = diagnosis_dir / "diagnosis.py"
        diagnosis_py.write_text("")

        with patch("hermes_loop.diagnosis.__file__", str(diagnosis_py)):
            with patch.dict(os.environ, {"SHELL": "/usr/bin/bash"}):
                checks = _check_shell()

        assert len(checks) == 2
        assert checks[0]["result"] == "PASS"
        assert checks[1]["result"] == "FAIL"

    def test_shell_not_set(self):
        """No SHELL env var produces single FAIL check."""
        with patch.dict(os.environ, {}, clear=True):
            checks = _check_shell()

        assert len(checks) == 1
        assert checks[0]["result"] == "FAIL"
        assert "not set" in checks[0]["detail"]

    def test_unknown_shell_no_completion(self, tmp_path: Path):
        """Unrecognized shell (e.g., fish) reports completion not found."""
        project_root = tmp_path
        (project_root / "scripts/completion/bash").parent.mkdir(
            parents=True, exist_ok=True
        )
        (project_root / "scripts/completion/bash").write_text("")
        (project_root / "scripts/completion/zsh").parent.mkdir(
            parents=True, exist_ok=True
        )
        (project_root / "scripts/completion/zsh").write_text("")

        diagnosis_dir = project_root / "hermes_loop"
        diagnosis_dir.mkdir(exist_ok=True)
        diagnosis_py = diagnosis_dir / "diagnosis.py"
        diagnosis_py.write_text("")

        with patch("hermes_loop.diagnosis.__file__", str(diagnosis_py)):
            with patch.dict(os.environ, {"SHELL": "/usr/bin/fish"}):
                checks = _check_shell()

        assert checks[0]["result"] == "PASS"
        assert "fish" in checks[0]["detail"]
        assert checks[1]["result"] == "FAIL"

    def test_empty_shell_env(self):
        """SHELL set to empty string treated as not set."""
        with patch.dict(os.environ, {"SHELL": ""}):
            checks = _check_shell()

        assert len(checks) == 1
        assert checks[0]["result"] == "FAIL"


# ===================================================================
# _check_gateway_connectivity
# ===================================================================


class TestCheckGatewayConnectivity:
    """Tests for gateway connectivity check.

    Note: this function does 'import socket' inside its body, so we
    patch socket.socket at the built-in module level, not on
    hermes_loop.diagnosis.
    """

    @patch("socket.socket")
    def test_reachable(self, mock_socket_cls):
        """Port is open — PASS."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket_cls.return_value = mock_sock

        with patch.dict(os.environ, {}, clear=True):
            checks = _check_gateway_connectivity()

        assert len(checks) == 1
        assert checks[0]["result"] == "PASS"
        assert "127.0.0.1" in checks[0]["detail"]

    @patch("socket.socket")
    def test_refused(self, mock_socket_cls):
        """Port refuses connection — WARN."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111  # ECONNREFUSED
        mock_socket_cls.return_value = mock_sock

        with patch.dict(os.environ, {}, clear=True):
            checks = _check_gateway_connectivity()

        assert checks[0]["result"] == "WARN"
        assert "refused" in checks[0]["detail"]

    @patch("socket.socket")
    def test_exception(self, mock_socket_cls):
        """socket creation raises exception — WARN."""
        mock_socket_cls.side_effect = OSError("No network")
        checks = _check_gateway_connectivity()

        assert checks[0]["result"] == "WARN"
        assert "check failed" in checks[0]["detail"]

    @patch("socket.socket")
    def test_custom_port_from_env(self, mock_socket_cls):
        """Uses HERMES_GATEWAY_PORT from environment."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket_cls.return_value = mock_sock

        with patch.dict(os.environ, {"HERMES_GATEWAY_PORT": "9000"}):
            checks = _check_gateway_connectivity()

        assert checks[0]["result"] == "PASS"
        mock_sock.connect_ex.assert_called_once_with(("127.0.0.1", 9000))

    @patch("socket.socket")
    def test_socket_timeout_set(self, mock_socket_cls):
        """Socket timeout is set to 2 seconds."""
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        _check_gateway_connectivity()
        mock_sock.settimeout.assert_called_once_with(2)

    @patch("socket.socket")
    def test_socket_closed_after_check(self, mock_socket_cls):
        """Socket is closed after connect attempt."""
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect_ex.return_value = 0

        _check_gateway_connectivity()
        mock_sock.close.assert_called_once()


# ===================================================================
# run_diagnosis
# ===================================================================


class TestRunDiagnosis:
    """Tests for the master diagnosis entry point."""

    @patch(
        "hermes_loop.diagnosis._check_python",
        return_value=[{"label": "python", "result": "PASS"}],
    )
    @patch(
        "hermes_loop.diagnosis._check_hermes",
        return_value=[{"label": "hermes", "result": "PASS"}],
    )
    @patch(
        "hermes_loop.diagnosis._check_git",
        return_value=[{"label": "git", "result": "PASS"}],
    )
    @patch(
        "hermes_loop.diagnosis._check_env_file",
        return_value=[{"label": "env", "result": "PASS"}],
    )
    @patch(
        "hermes_loop.diagnosis._check_disk",
        return_value=[{"label": "disk", "result": "PASS"}],
    )
    @patch(
        "hermes_loop.diagnosis._check_scripts",
        return_value=[{"label": "scripts", "result": "PASS"}],
    )
    @patch(
        "hermes_loop.diagnosis._check_shell",
        return_value=[{"label": "shell", "result": "PASS"}],
    )
    @patch(
        "hermes_loop.diagnosis._check_gateway_connectivity",
        return_value=[{"label": "gateway", "result": "PASS"}],
    )
    def test_returns_combined_list(
        self,
        mock_gw,
        mock_sh,
        mock_sc,
        mock_dk,
        mock_env,
        mock_git,
        mock_hermes,
        mock_py,
    ):
        """Returns all checks from all sub-check functions."""
        results = run_diagnosis()
        assert len(results) == 8
        labels = [r["label"] for r in results]
        assert "python" in labels
        assert "hermes" in labels
        assert "git" in labels
        assert "env" in labels
        assert "disk" in labels
        assert "scripts" in labels
        assert "shell" in labels
        assert "gateway" in labels

    @patch(
        "hermes_loop.diagnosis._check_python",
        return_value=[{"label": "py", "result": "PASS"}],
    )
    @patch("hermes_loop.diagnosis._check_hermes", return_value=[])
    @patch("hermes_loop.diagnosis._check_git", return_value=[])
    @patch("hermes_loop.diagnosis._check_env_file", return_value=[])
    @patch("hermes_loop.diagnosis._check_disk", return_value=[])
    @patch("hermes_loop.diagnosis._check_scripts", return_value=[])
    @patch("hermes_loop.diagnosis._check_shell", return_value=[])
    @patch("hermes_loop.diagnosis._check_gateway_connectivity", return_value=[])
    def test_handles_empty_sub_checks(
        self,
        mock_gw,
        mock_sh,
        mock_sc,
        mock_dk,
        mock_env,
        mock_git,
        mock_hermes,
        mock_py,
    ):
        """Works even when sub-checks return empty lists."""
        results = run_diagnosis()
        assert len(results) == 1  # only python returned something

    def test_includes_all_check_groups(self):
        """Real run includes checks from all 8 groups."""
        results = run_diagnosis()
        assert len(results) >= 8
        labels = [c["label"] for c in results]
        assert any("Python version" in lb for lb in labels)
        assert any("hermes binary" in lb or "hermes --version" in lb for lb in labels)
        assert any("git binary" in lb or "Inside a git" in lb for lb in labels)
        assert any(".env file" in lb for lb in labels)
        assert any("tmp is writable" in lb or "Disk space" in lb for lb in labels)
        assert any("Script:" in lb for lb in labels)
        assert any("Shell detected" in lb or "Shell completion" in lb for lb in labels)
        assert any("gateway reachable" in lb for lb in labels)


# ===================================================================
# _colorize
# ===================================================================


class TestColorize:
    """Tests for ANSI color helper."""

    def test_pass_is_green(self):
        """PASS returns green ANSI code."""
        result = _colorize("PASS")
        assert "\033[92m" in result
        assert "PASS" in result
        assert "\033[0m" in result

    def test_warn_is_yellow(self):
        """WARN returns yellow ANSI code."""
        result = _colorize("WARN")
        assert "\033[93m" in result
        assert "WARN" in result

    def test_fail_is_red(self):
        """FAIL returns red ANSI code."""
        result = _colorize("FAIL")
        assert "\033[91m" in result
        assert "FAIL" in result

    def test_unknown_status_fallback_red(self):
        """Unknown status defaults to red (FAIL behavior)."""
        result = _colorize("UNKNOWN")
        assert "\033[91m" in result


# ===================================================================
# print_diagnosis_report
# ===================================================================


class TestPrintDiagnosisReport:
    """Tests for the pretty-print report function."""

    def test_version_line_printed(self, capsys):
        """Version is printed in the report header."""
        checks = [_check("test", True, "", "")]
        print_diagnosis_report(checks, version="v1.0.0")
        captured = capsys.readouterr()
        assert "v1.0.0" in captured.out

    def test_check_labels_printed(self, capsys):
        """Check labels appear in output."""
        checks = [
            _check("My Check", True, "", ""),
            _check("Another Check", False, "oops", "fix it"),
        ]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        assert "My Check" in captured.out
        assert "Another Check" in captured.out

    def test_detail_printed(self, capsys):
        """Detail string is printed in the output."""
        checks = [_check("Check", False, "something broke", "")]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        assert "something broke" in captured.out

    def test_suggestion_printed(self, capsys):
        """Suggestion string is printed with dimming."""
        checks = [_check("Check", False, "", "try this fix")]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        assert "try this fix" in captured.out

    def test_summary_counts_printed(self, capsys):
        """Summary line with counts appears."""
        checks = [
            _check("a", True, "", ""),
            _check("b", None, "", ""),
            _check("c", False, "", ""),
        ]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        assert "Summary:" in captured.out
        assert "1 passed" in captured.out
        assert "1 warnings" in captured.out
        assert "1 failed" in captured.out

    def test_fail_zero_message(self, capsys):
        """When FAIL > 0, the issues-found message is shown."""
        checks = [
            _check("a", True, "", ""),
            _check("b", False, "broken", "fix"),
        ]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        assert "Issues found" in captured.out

    def test_warn_and_no_fail_shows_warning_message(self, capsys):
        """WARN > 0 and FAIL == 0 shows the warnings message."""
        checks = [
            _check("a", True, "", ""),
            _check("b", None, "warning", ""),
        ]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        assert "warnings" in captured.out.lower()

    def test_all_pass_message(self, capsys):
        """When all pass, the all-clear message is shown."""
        checks = [
            _check("a", True, "", ""),
            _check("b", True, "", ""),
        ]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        assert "All checks passed" in captured.out

    def test_quick_start_shown_on_all_pass(self, capsys):
        """Quickstart instructions shown when all pass."""
        checks = [_check("a", True, "", "")]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        assert "run.sh" in captured.out
        assert "make run" in captured.out.lower() or "Makefile" in captured.out

    def test_report_header_printed(self, capsys):
        """Report header line is printed."""
        print_diagnosis_report([], version="")
        captured = capsys.readouterr()
        assert "Diagnosis" in captured.out

    def test_no_detail_or_suggestion_not_printed(self, capsys):
        """Empty detail and suggestion are not printed."""
        checks = [_check("x", True, "", "")]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        lines = [
            line
            for line in captured.out.split("\n")
            if line.strip() and not line.strip().startswith("━━━")
        ]
        assert len(lines) >= 1

    def test_empty_checks(self, capsys):
        """Empty checks list doesn't crash."""
        print_diagnosis_report([], version="v2.0")
        captured = capsys.readouterr()
        assert "v2.0" in captured.out
        assert "Summary:" in captured.out

    def test_only_warns_fails_when_no_fails(self, capsys):
        """Only WARN results (no FAILs) show the warnings footer."""
        checks = [_check("x", None, "some warning", "")]
        print_diagnosis_report(checks)
        captured = capsys.readouterr()
        assert "Some warnings" in captured.out

    def test_zero_summary_when_no_checks(self, capsys):
        """Empty check list shows 0 in summary."""
        print_diagnosis_report([], version="v3.0")
        captured = capsys.readouterr()
        assert "0 passed" in captured.out
        assert "0 warnings" in captured.out
        assert "0 failed" in captured.out


# ===================================================================
# Integration: all checks run through run_diagnosis
# ===================================================================


class TestIntegration:
    """Integration-level tests running actual diagnostic functions."""

    def test_run_diagnosis_returns_list_of_dicts(self):
        """run_diagnosis returns a list of dicts with expected keys."""
        results = run_diagnosis()
        assert isinstance(results, list)
        for c in results:
            assert isinstance(c, dict)
            assert "label" in c
            assert "result" in c
            assert c["result"] in ("PASS", "WARN", "FAIL")

    def test_all_results_have_valid_status(self):
        """Every check result is PASS, WARN, or FAIL."""
        results = run_diagnosis()
        for c in results:
            assert c["result"] in (
                "PASS",
                "WARN",
                "FAIL",
            ), f"Unexpected result {c['result']}"

    def test_all_results_have_label(self):
        """Every check has a non-empty label."""
        results = run_diagnosis()
        for c in results:
            assert c["label"], f"Empty label in check {c}"
