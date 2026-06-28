"""Unit tests for _run_healthcheck in cli.py.

Validates all status paths (healthy, degraded, critical) and the
SHELL_FORMAT=docker mode using mocked hermes/git/ledger dependencies.
"""

import json
import io
import sys
import subprocess
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _OkResult:
    returncode = 0
    stdout = "hermes 1.0.0"
    stderr = ""


_OK_RESULT = _OkResult()


def _find_both(cmd):
    if cmd in ("hermes", "git"):
        return f"/usr/bin/{cmd}"
    return None


def _find_none(cmd):
    return None


_UNSET = object()  # sentinel to distinguish "not provided" from "None"


def _run_healthcheck(
    *,
    env_override=None,
    which_side_effect=None,
    subprocess_side_effect=None,
    write_ledger_side_effect=None,
    read_ledger_return=_UNSET,
    read_ledger_side_effect=None,
    extract_json_return=_UNSET,
    extract_json_side_effect=None,
    os_remove_side_effect=None,
):
    """Call cli._run_healthcheck() under mock context and return (exit_code, stdout_str)."""
    from hermes_loop import cli as _cli

    if which_side_effect is None:
        which_side_effect = _find_both

    if subprocess_side_effect is None:
        subprocess_side_effect = lambda *a, **kw: _OK_RESULT

    if write_ledger_side_effect is None:
        write_ledger_side_effect = lambda s: None

    if read_ledger_return is _UNSET and read_ledger_side_effect is None:
        read_ledger_return = {"test": True}

    if os_remove_side_effect is None:
        os_remove_side_effect = lambda p: None

    patches = [
        patch("shutil.which", side_effect=which_side_effect),
        patch("subprocess.run", side_effect=subprocess_side_effect),
        patch("os.environ", env_override or {"SHELL_FORMAT": ""}),
        patch("os.remove", side_effect=os_remove_side_effect),
        patch(
            "hermes_loop.file_utils.write_ledger",
            side_effect=write_ledger_side_effect,
        ),
    ]

    if read_ledger_side_effect is not None:
        patches.append(
            patch(
                "hermes_loop.file_utils.read_ledger",
                side_effect=read_ledger_side_effect,
            )
        )
    elif read_ledger_return is not _UNSET:
        patches.append(
            patch(
                "hermes_loop.file_utils.read_ledger",
                return_value=read_ledger_return,
            )
        )

    if extract_json_side_effect is not None:
        patches.append(
            patch(
                "hermes_loop.file_utils.extract_json_from_output",
                side_effect=extract_json_side_effect,
            )
        )
    elif extract_json_return is not _UNSET:
        patches.append(
            patch(
                "hermes_loop.file_utils.extract_json_from_output",
                return_value=extract_json_return,
            )
        )

    captured_exit = [0]  # type: ignore[list-item]
    captured_stdout = [""]

    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            _cli._run_healthcheck()
        except SystemExit as e:
            captured_exit[0] = e.code if e.code is not None else 0
            captured_stdout[0] = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

    return captured_exit[0], captured_stdout[0]


# ===================================================================
# Tests: HEALTHY path
# ===================================================================


class TestHealthy:
    """All deps available => status='healthy', exit_code=0."""

    def test_all_deps_available(self):
        """Everything works — healthy exit."""
        exit_code, stdout = _run_healthcheck()
        assert exit_code == 0, f"expected 0, got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "healthy"
        assert report["summary"]["total"] > 0
        assert report["summary"]["failed"] == 0

    def test_report_has_required_keys(self):
        """Report JSON contains all required top-level keys."""
        _, stdout = _run_healthcheck()
        report = json.loads(stdout)
        for key in ("status", "version", "timestamp", "checks", "summary"):
            assert key in report, f"missing key: {key}"

    def test_summary_fields_correct(self):
        """Summary counts add up correctly."""
        _, stdout = _run_healthcheck()
        report = json.loads(stdout)
        s = report["summary"]
        assert s["healthy"] + s["degraded"] + s["failed"] == s["total"]
        assert s["failed"] == 0
        assert s["healthy"] == s["total"]

    def test_docker_mode_compact_output(self):
        """SHELL_FORMAT=docker produces compact {status, exit_code}."""
        exit_code, stdout = _run_healthcheck(env_override={"SHELL_FORMAT": "docker"})
        assert exit_code == 0
        parsed = json.loads(stdout.strip())
        assert set(parsed.keys()) == {"status", "exit_code"}
        assert parsed["status"] == "healthy"
        assert parsed["exit_code"] == 0


# ===================================================================
# Tests: DEGRADED path
# ===================================================================


class TestDegraded:
    """Partial failures => status='degraded', exit_code=1."""

    def test_git_repo_timeout_degraded(self):
        """Git rev-parse timeout => degraded exit."""

        def _subprocess(*a, **kw):
            args = a[0] if a else kw.get("args", [])
            if isinstance(args, list) and "hermes" in args[0]:
                return _OK_RESULT
            raise subprocess.TimeoutExpired(cmd=args, timeout=5)

        exit_code, stdout = _run_healthcheck(
            subprocess_side_effect=_subprocess,
        )
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"

    def test_hermes_version_timeout_degraded(self):
        """Hermes --version timeout => degraded exit."""

        class _GitOk:
            returncode = 0
            stdout = ".git"
            stderr = ""

        def _subprocess(*a, **kw):
            args = a[0] if a else kw.get("args", [])
            if isinstance(args, list) and "git" in args[0]:
                return _GitOk()
            raise subprocess.TimeoutExpired(cmd=args, timeout=10)

        exit_code, stdout = _run_healthcheck(
            subprocess_side_effect=_subprocess,
        )
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"

    def test_json_parsing_degraded(self):
        """extract_json returns None for all => json check fails => degraded."""
        exit_code, stdout = _run_healthcheck(extract_json_return=None)
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"

    def test_json_parsing_exception_degraded(self):
        """extract_json raises exception on non-empty => degraded."""
        call_count = [0]

        def _raise_later(*a, **kw):
            call_count[0] += 1
            raise ValueError(f"mock parse error #{call_count[0]}")

        exit_code, stdout = _run_healthcheck(
            extract_json_side_effect=_raise_later,
        )
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"

    def test_ledger_read_bad_data_degraded(self):
        """Ledger read returns unexpected data => degraded."""
        exit_code, stdout = _run_healthcheck(
            read_ledger_return={"unexpected": True},
        )
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"

    def test_git_binary_missing_degraded(self):
        """No git on PATH (hermes found) => degraded."""

        def _which_no_git(cmd):
            if cmd == "hermes":
                return "/usr/bin/hermes"
            return None

        exit_code, stdout = _run_healthcheck(
            which_side_effect=_which_no_git,
        )
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"
        git_checks = [c for c in report["checks"] if c["name"] == "git_binary"]
        assert git_checks
        assert git_checks[0]["status"] == "degraded"

    def test_hermes_version_nonzero_exit_degraded(self):
        """hermes --version returns non-zero => version check degraded."""

        class _NonZeroResult:
            returncode = 1
            stdout = ""
            stderr = "unknown command"

        exit_code, stdout = _run_healthcheck(
            subprocess_side_effect=lambda *a, **kw: _NonZeroResult(),
        )
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"
        ver_checks = [c for c in report["checks"] if c["name"] == "hermes_version"]
        assert ver_checks
        assert ver_checks[0]["status"] == "degraded"

    def test_git_repo_not_found_degraded(self):
        """git found but not in a repo => degraded."""

        class _GitNotRepo:
            returncode = 128
            stdout = ""
            stderr = "fatal: not a git repository"

        def _subprocess(*a, **kw):
            args = a[0] if a else kw.get("args", [])
            if isinstance(args, list) and "hermes" in args[0]:
                return _OK_RESULT
            return _GitNotRepo()

        exit_code, stdout = _run_healthcheck(
            subprocess_side_effect=_subprocess,
        )
        assert exit_code == 1
        report = json.loads(stdout)
        assert report["status"] == "degraded"


# ===================================================================
# Tests: CRITICAL path
# ===================================================================


class TestCritical:
    """Hard failures => status='critical', exit_code=2."""

    def test_no_hermes_binary_critical(self):
        """Hermes not found on PATH => critical."""
        exit_code, stdout = _run_healthcheck(which_side_effect=_find_none)
        assert exit_code == 2, f"expected 2 (critical), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "critical"
        hb = [c for c in report["checks"] if c["name"] == "hermes_binary"]
        assert hb
        assert hb[0]["status"] == "critical"

    def test_ledger_write_raises_critical(self):
        """write_ledger raises => ledger check critical => overall critical."""

        def _raise_io(*a, **kw):
            raise PermissionError("/tmp/ledger.json: Permission denied")

        exit_code, stdout = _run_healthcheck(
            write_ledger_side_effect=_raise_io,
        )
        assert exit_code == 2, f"expected 2 (critical), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "critical"

    def test_ledger_read_returns_unexpected_degraded(self):
        """write succeeds but read returns surprising data => degraded."""
        exit_code, stdout = _run_healthcheck(read_ledger_return=None)
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"
        ledger_checks = [c for c in report["checks"] if c["name"] == "ledger_io"]
        assert ledger_checks
        assert ledger_checks[0]["status"] == "degraded"


# ===================================================================
# Tests: EDGE CASES & error handling
# ===================================================================


class TestEdgeCases:
    """Resilience under exceptional conditions."""

    def test_ledger_cleanup_oserror_still_healthy(self):
        """os.remove on .tmp raises OSError => caught silently, still healthy."""

        def _remove_side_effect(p):
            if p.endswith(".tmp"):
                raise OSError("[Errno 13] Permission denied")

        exit_code, stdout = _run_healthcheck(
            os_remove_side_effect=_remove_side_effect,
        )
        assert exit_code == 0, f"expected 0 (healthy), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "healthy"

    def test_ledger_cleanup_general_exception_still_healthy(self):
        """read_ledger raises on cleanup phase => caught, still healthy."""
        reads = [0]

        def _read_with_exception():
            reads[0] += 1
            if reads[0] == 2:
                raise IOError("Corrupt ledger file")
            return {"test": True}

        exit_code, stdout = _run_healthcheck(
            read_ledger_side_effect=_read_with_exception,
        )
        assert exit_code == 0, f"expected 0 (healthy), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "healthy"

    def test_empty_json_input_defensive_branch(self):
        """extract returns data for empty/None input => defensive else branch."""
        call_count = [0]

        def _mock_extract(*a, **kw):
            call_count[0] += 1
            return {"summary": "test", "error": None}

        exit_code, stdout = _run_healthcheck(
            extract_json_side_effect=_mock_extract,
        )
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"

    def test_docker_mode_critical_output(self):
        """SHELL_FORMAT=docker with hermes missing => compact critical output."""
        exit_code, stdout = _run_healthcheck(
            which_side_effect=_find_none,
            env_override={"SHELL_FORMAT": "docker"},
        )
        assert exit_code == 2
        parsed = json.loads(stdout.strip())
        assert set(parsed.keys()) == {"status", "exit_code"}
        assert parsed["status"] == "critical"
        assert parsed["exit_code"] == 2

    def test_docker_mode_degraded_output(self):
        """SHELL_FORMAT=docker with git timeout => compact degraded output."""

        def _subprocess(*a, **kw):
            args = a[0] if a else kw.get("args", [])
            if isinstance(args, list) and "hermes" in args[0]:
                return _OK_RESULT
            raise subprocess.TimeoutExpired(cmd=args, timeout=5)

        exit_code, stdout = _run_healthcheck(
            subprocess_side_effect=_subprocess,
            env_override={"SHELL_FORMAT": "docker"},
        )
        assert exit_code == 1
        parsed = json.loads(stdout.strip())
        assert set(parsed.keys()) == {"status", "exit_code"}
        assert parsed["status"] == "degraded"
        assert parsed["exit_code"] == 1

    def test_hermes_version_file_not_found(self):
        """FileNotFoundError during hermes --version => degraded."""

        def _subprocess(*a, **kw):
            args = a[0] if a else kw.get("args", [])
            if isinstance(args, list) and "hermes" in args[0]:
                raise FileNotFoundError("hermes not found despite which")
            return _OK_RESULT

        exit_code, stdout = _run_healthcheck(
            subprocess_side_effect=_subprocess,
        )
        assert exit_code == 1, f"expected 1 (degraded), got {exit_code}"
        report = json.loads(stdout)
        assert report["status"] == "degraded"
