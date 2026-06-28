"""Preflight health checks — validates the environment before the loop starts."""

import json
import os
import socket as _sock
import sys

from .config import SENTINEL_PATH_DEFAULT
from .file_utils import _log


class PreflightChecker:
    """Runs configurable preflight health checks before the loop starts.

    Checks: Python version, workdir existence, git repo, sentinel writable,
    port availability, context/goals file readability, schema file validity,
    disk space. Returns a list of PreflightResult dicts.
    """

    def __init__(self, args, fail_fast: bool = False):
        """Initialize from argparse namespace."""
        self._args = args
        self._fail_fast = fail_fast

    def run_all(self) -> bool:
        """Run all preflight checks from args, log results, return True if all pass."""
        results = PreflightChecker.run_all_checks(
            workdir=self._args.workdir or "",
            sentinel_path=self._args.shutdown_sentinel,
            webhook_port=self._args.webhook_port or 0,
            context_file=self._args.context_file or "",
            goals_file=self._args.goals_file or "",
            schema_file=self._args.output_schema_file or "",
            check_git=getattr(self._args, "git", False),
            check_disk=getattr(self._args, "log_file", "") or "/tmp",
            fail_fast=self._fail_fast,
        )

        all_pass = True
        for r in results:
            if not r["passed"]:
                all_pass = False
                _log(f"[PREFLIGHT] \u2717 {r['name']}: {r['detail'][:120]}")
                if self._fail_fast:
                    _log("[PREFLIGHT] FAIL FAST \u2014 aborting.")
                    break
            else:
                _log(f"[PREFLIGHT] \u2713 {r['name']}: {r['detail'][:120]}")

        if all_pass:
            _log("[PREFLIGHT] All checks passed.")
        else:
            failed = sum(1 for r in results if not r["passed"])
            _log(f"[PREFLIGHT] {failed} check(s) failed.")

        return all_pass

    @staticmethod
    def check_python_version() -> tuple[bool, str]:
        """Check that Python >= 3.10 is available."""
        v = sys.version_info
        if v >= (3, 10):
            return True, f"Python {v.major}.{v.minor}.{v.micro} (>= 3.10 OK)"
        return False, f"Python {v.major}.{v.minor} < 3.10"

    @staticmethod
    def check_workdir(wd: str) -> tuple[bool, str]:
        """Check that workdir exists and is a directory."""
        if not wd:
            return True, "no workdir specified (using current dir)"
        p = os.path.expanduser(wd)
        if not os.path.exists(p):
            return False, f"workdir '{p}' does not exist"
        if not os.path.isdir(p):
            return False, f"'{p}' is not a directory"
        return True, f"'{p}' exists"

    @staticmethod
    def check_git_repo(wd: str) -> tuple[bool, str]:
        """Check that workdir is a git repo (only when --git is set)."""
        base = os.path.expanduser(wd) if wd else os.getcwd()
        git_dir = os.path.join(base, ".git")
        if os.path.isdir(git_dir):
            return True, f".git found at {git_dir}"
        return False, "no .git directory \u2014 git features will be no-ops"

    @staticmethod
    def check_sentinel_writable(sentinel_path: str) -> tuple[bool, str]:
        """Check that sentinel parent directory is writable."""
        parent = os.path.dirname(os.path.expanduser(sentinel_path)) or "."
        if os.access(parent, os.W_OK):
            return True, f"'{parent}' is writable"
        return False, f"'{parent}' is not writable"

    @staticmethod
    def check_port_available(port: int) -> tuple[bool, str]:
        """Check if a TCP port is available."""
        if port <= 0:
            return True, "port not requested"
        try:
            with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                s.bind(("", port))
            return True, f"port {port} is available"
        except OSError as e:
            return False, f"port {port} is in use: {e}"

    @staticmethod
    def check_file_readable(path: str, label: str) -> tuple[bool, str]:
        """Check that a file exists and is readable."""
        if not path:
            return True, f"--{label} not set"
        p = os.path.expanduser(path)
        if not os.path.isfile(p):
            return False, f"--{label} file '{p}' not found"
        if not os.access(p, os.R_OK):
            return False, f"--{label} file '{p}' not readable"
        return True, f"--{label} file '{p}' found"

    @staticmethod
    def check_schema_file(path: str) -> tuple[bool, str]:
        """Check that --output-schema-file is valid JSON."""
        if not path:
            return True, "not set"
        p = os.path.expanduser(path)
        if not os.path.isfile(p):
            return False, f"schema file '{p}' not found"
        try:
            with open(p) as f:
                json.load(f)
            return True, "valid JSON schema file"
        except (OSError, json.JSONDecodeError) as e:
            return False, f"invalid schema file: {e}"

    @staticmethod
    def check_disk_space(path: str = "/tmp", min_gb: float = 0.5) -> tuple[bool, str]:
        """Check minimum free disk space (Linux statvfs)."""
        try:
            if hasattr(os, "statvfs"):
                st = os.statvfs(os.path.dirname(os.path.abspath(path)))
                free_gb = (st.f_frsize * st.f_bavail) / (1024**3)
                if free_gb < min_gb:
                    return False, f"only {free_gb:.1f}GB free (need {min_gb}GB)"
                return True, f"{free_gb:.1f}GB free"
            return True, "unable to check (non-Linux)"
        except Exception:
            return True, "unable to check"

    @staticmethod
    def run_all_checks(
        workdir: str = "",
        sentinel_path: str = SENTINEL_PATH_DEFAULT,
        webhook_port: int = 0,
        context_file: str = "",
        goals_file: str = "",
        schema_file: str = "",
        check_git: bool = False,
        check_disk: str = "",
        fail_fast: bool = False,
    ) -> list[dict]:
        """Run all preflight checks and return results as list of dicts."""
        checks = [
            ("python version", PreflightChecker.check_python_version()),
            ("workdir", PreflightChecker.check_workdir(workdir)),
            (
                "sentinel writable",
                PreflightChecker.check_sentinel_writable(sentinel_path),
            ),
            ("port available", PreflightChecker.check_port_available(webhook_port)),
            (
                "context file",
                PreflightChecker.check_file_readable(context_file, "context-file"),
            ),
            (
                "goals file",
                PreflightChecker.check_file_readable(goals_file, "goals-file"),
            ),
            ("schema file", PreflightChecker.check_schema_file(schema_file)),
        ]

        if check_git:
            checks.append(("git repo", PreflightChecker.check_git_repo(workdir)))

        if check_disk:
            checks.append(("disk space", PreflightChecker.check_disk_space(check_disk)))

        results = []
        for name, (passed, detail) in checks:
            results.append({"name": name, "passed": passed, "detail": detail})
            if not passed and fail_fast:
                break

        return results

    @staticmethod
    def format_results(results: list[dict]) -> str:
        """Format preflight results as a table with \u2713/\u2717 indicators."""
        lines = ["", "--- Preflight Health Checks ---"]
        all_pass = True
        for r in results:
            icon = "\u2713" if r["passed"] else "\u2717"
            if not r["passed"]:
                all_pass = False
            detail = r["detail"][:80]
            lines.append(f"  {icon}  {r['name']}: {detail}")
        lines.append("")
        if all_pass:
            lines.append("  All checks passed.")
        else:
            lines.append(
                f"  {sum(1 for r in results if not r['passed'])} check(s) failed."
            )
        lines.append("")
        return "\n".join(lines)
