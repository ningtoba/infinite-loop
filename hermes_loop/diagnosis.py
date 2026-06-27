"""
diagnosis — Self-diagnosis ('--doctor') for the Infinite Loop Daemon.

Runs a comprehensive set of checks covering environment, dependencies,
configuration, filesystem, and optional extras. Produces a structured
pass/warn/fail report with actionable suggestions for each issue found.

Usage:
    hermes_loop --doctor
"""

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _check(
    label: str,
    result: bool | None,
    detail: str = "",
    suggestion: str = "",
) -> dict:
    return {
        "label": label,
        "result": "PASS" if result else ("WARN" if result is None else "FAIL"),
        "detail": detail,
        "suggestion": suggestion,
    }


# ── Individual checks ─────────────────────────────────────────────────────────


def _check_python() -> list[dict]:
    checks = []
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 10
    checks.append(
        _check(
            "Python version >= 3.10",
            ok,
            f"{v.major}.{v.minor}.{v.micro}",
            "Install Python 3.10+ from https://python.org" if not ok else "",
        )
    )
    # Stdlib-only verification
    missing = []
    for mod in (
        "argparse",
        "json",
        "os",
        "subprocess",
        "pathlib",
        "re",
        "time",
        "datetime",
        "hashlib",
        "math",
        "shutil",
        "signal",
        "tempfile",
        "threading",
        "multiprocessing",
        "logging",
        "http.server",
        "socketserver",
    ):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    checks.append(
        _check(
            "All stdlib modules available",
            not missing,
            f"Missing: {', '.join(missing)}" if missing else "All present",
            "This should never happen — reinstall Python" if missing else "",
        )
    )
    return checks


def _check_hermes() -> list[dict]:
    checks = []
    hermes_bin = shutil.which("hermes")
    checks.append(
        _check(
            "hermes binary on PATH",
            hermes_bin is not None,
            hermes_bin or "not found",
            "Install: curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash",
        )
    )
    if hermes_bin:
        try:
            result = subprocess.run(
                [hermes_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ver = result.stdout.strip() or result.stderr.strip() or "unknown"
            checks.append(
                _check(
                    "hermes --version works",
                    result.returncode == 0,
                    ver[:80],
                    "Check your hermes installation",
                )
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            checks.append(
                _check(
                    "hermes --version works",
                    False,
                    str(e),
                    "hermes binary may be broken — reinstall",
                )
            )
    else:
        checks.append(_check("hermes --version works", False, "skipped", ""))
    return checks


def _check_git() -> list[dict]:
    checks = []
    git_bin = shutil.which("git")
    checks.append(
        _check(
            "git binary on PATH",
            git_bin is not None,
            git_bin or "not found",
            "Install git via your package manager (e.g. sudo pacman -S git)",
        )
    )
    if git_bin:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            in_repo = result.returncode == 0
            checks.append(
                _check(
                    "Inside a git repository",
                    in_repo,
                    result.stdout.strip() if in_repo else "not a git repo",
                    "Run 'git init' or clone a repo first",
                )
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            checks.append(_check("Inside a git repository", False, str(e), ""))
    else:
        checks.append(_check("Inside a git repository", False, "skipped", ""))
    return checks


def _check_env_file() -> list[dict]:
    checks = []
    # Look for .env in cwd and parent directories
    candidates = []
    cwd = Path.cwd()
    for p in [cwd, cwd.parent, cwd / ".."]:
        resolved = p.resolve()
        env_path = resolved / ".env"
        if env_path.exists():
            candidates.append(str(env_path))

    if candidates:
        env_path = candidates[0]
        checks.append(
            _check(
                ".env file found",
                True,
                env_path,
                "",
            )
        )
        # Parse and check for common issues
        try:
            with open(env_path) as f:
                content = f.read()
            lines = content.strip().splitlines()
            total_vars = sum(
                1 for line in lines if "=" in line and not line.startswith("#")
            )
            checks.append(
                _check(
                    ".env has content",
                    total_vars > 0,
                    f"{total_vars} variable(s) defined",
                    "Run 'python3 -m hermes_loop --init' to create a .env",
                )
            )
            # Check for common typos
            known_prefix = "INFINITE_LOOP_"
            suspicious = []
            for line in lines:
                if "=" in line and not line.startswith("#"):
                    var = line.split("=", 1)[0].strip()
                    if var.startswith("INFINITE_") and not var.startswith(known_prefix):
                        suspicious.append(var)
            if suspicious:
                checks.append(
                    _check(
                        "No typos in INFINITE_LOOP_* variables",
                        False,
                        f"Suspicious: {', '.join(suspicious)}",
                        "Run 'python3 -m hermes_loop --check-env' for detailed validation",
                    )
                )
            else:
                checks.append(
                    _check(
                        "No typos in INFINITE_LOOP_* variables",
                        True,
                        "All look correct",
                        "",
                    )
                )
            # Check if INFINITE_LOOP_GOAL is set
            has_goal = any(
                re.match(r"^\s*INFINITE_LOOP_GOAL\s*=", line) for line in lines
            )
            checks.append(
                _check(
                    "INFINITE_LOOP_GOAL is set in .env",
                    has_goal,
                    "Set via INFINITE_LOOP_GOAL=..." if has_goal else "Not set",
                    "Set INFINITE_LOOP_GOAL in .env or pass --goal on CLI",
                )
            )
        except OSError as e:
            checks.append(
                _check(".env is readable", False, str(e), "Check file permissions")
            )
    else:
        checks.append(
            _check(
                ".env file found",
                False,
                "Not found in cwd or parent dirs",
                "Copy .env.example to .env: cp .env.example .env\n"
                "Or run: python3 -m hermes_loop --init",
            )
        )
    return checks


def _check_disk() -> list[dict]:
    checks = []
    # Check /tmp is writable (default ledger location)
    tmp_test = Path("/tmp/.hermes_loop_diagnosis_test")
    try:
        tmp_test.write_text("ok")
        tmp_test.unlink()
        checks.append(_check("/tmp is writable", True, "ok", ""))
    except OSError as e:
        checks.append(
            _check("/tmp is writable", False, str(e), "Check /tmp permissions")
        )

    # Check disk space on cwd
    try:
        stat = os.statvfs(Path.cwd())
        free_gb = (stat.f_frsize * stat.f_bavail) / (1024**3)
        low = free_gb < 0.5
        checks.append(
            _check(
                "Disk space (cwd)",
                not low,
                f"{free_gb:.1f} GB free{' (LOW!)' if low else ''}",
                (
                    "Free up disk space or move to a filesystem with more room"
                    if low
                    else ""
                ),
            )
        )
    except Exception:
        pass

    return checks


def _check_scripts() -> list[dict]:
    checks = []
    # Try to locate project root
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent

    required_scripts = [
        ("run.sh", "One-command entrypoint"),
        ("launch-loop.py", "Backward-compatible shim"),
        ("Makefile", "Convenience targets"),
        ("scripts/completion/bash", "Bash completion"),
        ("scripts/completion/zsh", "Zsh completion"),
    ]
    for name, desc in required_scripts:
        path = project_root / name
        exists = path.exists()
        checks.append(
            _check(
                f"Script: {name} ({desc})",
                exists,
                str(path) if exists else f"Missing: {path}",
                "File not found — check your checkout" if not exists else "",
            )
        )
    return checks


def _check_shell() -> list[dict]:
    checks = []
    shell = os.environ.get("SHELL", "")
    if shell:
        shell_name = os.path.basename(shell)
        checks.append(
            _check(
                "Shell detected",
                True,
                f"{shell_name} ({shell})",
                "",
            )
        )
        # Check for completion (look at project scripts/completion dir)
        script_dir = Path(__file__).parent.resolve()
        project_root = script_dir.parent
        has_completion = False
        completion_path = None
        if shell_name == "bash":
            completion_path = project_root / "scripts/completion/bash"
        elif shell_name == "zsh":
            completion_path = project_root / "scripts/completion/zsh"
        if completion_path:
            has_completion = completion_path.exists()
        else:
            completion_path = None
            has_completion = False
        if has_completion:
            checks.append(
                _check(
                    "Shell completion installed",
                    True,
                    str(completion_path),
                    "",
                )
            )
        else:
            checks.append(
                _check(
                    "Shell completion installed",
                    False,
                    "Not found",
                    "Run: make completion",
                )
            )
    else:
        checks.append(_check("Shell detected", False, "$SHELL not set", ""))
    return checks


def _check_gateway_connectivity() -> list[dict]:
    """Check if the Hermes gateway port responds."""
    checks = []
    gateway_port = os.environ.get("HERMES_GATEWAY_PORT", "8000")
    host = "127.0.0.1"
    try:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex((host, int(gateway_port)))
        s.close()
        if result == 0:
            checks.append(
                _check("Hermes gateway reachable", True, f"{host}:{gateway_port}", "")
            )
        else:
            checks.append(
                _check(
                    "Hermes gateway reachable",
                    None,
                    f"{host}:{gateway_port} — connection refused",
                    "Only needed for spawned sessions — start gateway if running via hermes chat",
                )
            )
    except Exception:
        checks.append(
            _check(
                "Hermes gateway reachable",
                None,
                f"{host}:{gateway_port} — check failed",
                "Only needed for spawned sessions",
            )
        )
    return checks


# ── Master diagnosis entry point ────────────────────────────────────────────────


def run_diagnosis() -> list[dict]:
    """Run all checks and return a combined report as a list of dicts."""

    all_checks = []
    all_checks.extend(_check_python())
    all_checks.extend(_check_hermes())
    all_checks.extend(_check_git())
    all_checks.extend(_check_env_file())
    all_checks.extend(_check_disk())
    all_checks.extend(_check_scripts())
    all_checks.extend(_check_shell())
    all_checks.extend(_check_gateway_connectivity())
    return all_checks


# ── Pretty-print ────────────────────────────────────────────────────────────────


def _colorize(status: str) -> str:
    if status == "PASS":
        return f"\033[92m{status}\033[0m"  # green
    elif status == "WARN":
        return f"\033[93m{status}\033[0m"  # yellow
    else:
        return f"\033[91m{status}\033[0m"  # red


def print_diagnosis_report(checks: list[dict], version: str = ""):
    """Pretty-print the diagnosis report to stdout."""

    print("━━━ Infinite Loop Daemon — Diagnosis ━━━")
    if version:
        print(f"  Version: {version}")
    print(f"  Ran at:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    summary = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for c in checks:
        summary[c.get("result", "FAIL")] += 1
        label = c.get("label", "?")
        result = c.get("result", "FAIL")
        detail = c.get("detail", "")
        suggestion = c.get("suggestion", "")
        color = _colorize(result)
        print(f"  [{color}] {label}")
        if detail:
            print(f"       {detail}")
        if suggestion:
            print(f"       \033[90m→ {suggestion}\033[0m")
        print()

    total = sum(summary.values())
    print(
        f"  Summary: {summary['PASS']} passed, {summary['WARN']} warnings, "
        f"{summary['FAIL']} failed (of {total})"
    )

    if summary["FAIL"] > 0:
        print()
        print("  \033[91mIssues found — review the FAIL items above.\033[0m")
        print("  Most issues have suggestions on the dimmed (grey) line.")
    elif summary["WARN"] > 0:
        print()
        print("  \033[93mSome warnings — not blocking but worth reviewing.\033[0m")
    else:
        print()
        print("  \033[92mAll checks passed! Ready to run.\033[0m")
        print()
        print("  Quick start:")
        print("    bash run.sh           # Launch with .env config")
        print("    make run              # Same via Makefile")
        print("    python3 -m hermes_loop --init  # Create .env interactively")
