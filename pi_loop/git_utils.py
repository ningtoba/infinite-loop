"""Git state capture and auto-commit helpers."""

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def _capture_git_state(workdir: str | None, store_diff: bool = False) -> dict:
    """Capture pre/post git state.

    Args:
        workdir: Git repo working directory.
        store_diff: If True, also store the actual unified diff (capped at 10KB).
    """
    cwd = workdir or os.getcwd()
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return {}
    result: dict[str, str] = {}
    try:
        r = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        result["diff_stat"] = r.stdout.strip() or "(no unstaged changes)"
        r2 = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        result["diff_stat_cached"] = r2.stdout.strip() or "(no staged changes)"
        r3 = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        result["head"] = r3.stdout.strip() if r3.returncode == 0 else ""
        if store_diff:
            r4 = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=10,
            )
            diff_text = r4.stdout.strip()
            if diff_text:
                result["diff"] = diff_text[:10240]
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Git state capture failed: %s", e)
        return {}
    return result


def _git_auto_commit(workdir: str | None, iteration: int, summary: str) -> str | None:
    """Auto-commit changes after an iteration. Returns commit hash or None."""
    cwd = workdir or os.getcwd()
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return None
    try:
        subprocess.run(["git", "add", "-A"], capture_output=True, cwd=cwd, timeout=15)
        r = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
            cwd=cwd,
            timeout=10,
        )
        if r.returncode == 0:
            return None
        msg = f"infinite-loop iter #{iteration}: {summary[:80]}"
        subprocess.run(
            ["git", "commit", "-m", msg],
            capture_output=True,
            cwd=cwd,
            timeout=30,
        )
        r2 = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        return r2.stdout.strip() if r2.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Git auto-commit failed: %s", e)
        return None
