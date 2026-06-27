"""Smart git worktree branch merging.

Detects worktree branches (hermes/*, worktree/*) created by spawned Hermes
sessions and merges their changes back to the main branch after each iteration.
"""

import os
import subprocess

from .file_utils import _log


def _detect_worktree_branches(workdir: str | None) -> list[dict]:
    """Find candidate worktree branches created by Hermes sessions.

    Scans local branches matching ``hermes/*`` or ``worktree/*`` patterns.
    Also checks ``git worktree list`` for active worktrees.

    Returns a list of dicts with ``ref``, ``name``, and optional ``worktree_path``.
    """
    cwd = workdir or os.getcwd()
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return []

    branches: list[dict] = []

    # 1. Find branches matching worktree patterns
    try:
        r = subprocess.run(
            ["git", "branch", "--list", "hermes/*"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                name = line.strip().lstrip("* ")
                if name:
                    branches.append({"ref": name, "name": name})

        r = subprocess.run(
            ["git", "branch", "--list", "worktree/*"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                name = line.strip().lstrip("* ")
                if name and not any(b["ref"] == name for b in branches):
                    branches.append({"ref": name, "name": name})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    # 2. Also scan active worktrees from git worktree list
    try:
        r = subprocess.run(
            ["git", "worktree", "list"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    path = parts[0]
                    ref = parts[1].strip("[]")
                    # ref could be a branch name or commit hash in brackets e.g. [hermes/iter-3-w-0]
                    if ref.startswith("hermes/") or ref.startswith("worktree/"):
                        existing = {b["ref"] for b in branches}
                        if ref not in existing:
                            branches.append(
                                {"ref": ref, "name": ref, "worktree_path": path}
                            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return branches


def _get_current_branch(workdir: str | None) -> str | None:
    """Return the current git branch name, or None if unavailable."""
    cwd = workdir or os.getcwd()
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        if r.returncode == 0:
            name = r.stdout.strip()
            return name if name != "HEAD" else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _get_main_branch(workdir: str | None) -> str:
    """Detect the main/master branch name.

    Tries ``main`` first, then ``master``, falling back to ``main``.
    """
    cwd = workdir or os.getcwd()
    for candidate in ("main", "master"):
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--verify", candidate],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=5,
            )
            if r.returncode == 0:
                return candidate
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return "main"


def _try_fast_forward_merge(workdir: str | None, branch: str, main_branch: str) -> bool:
    """Attempt a fast-forward merge of *branch* into the current checkout.

    Returns True if the merge was applied.
    """
    try:
        r = subprocess.run(
            ["git", "merge", "--ff-only", branch],
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=30,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _try_recursive_merge(
    workdir: str | None, branch: str, worker_id: int, iteration_count: int
) -> bool:
    """Attempt a recursive merge with conflict detection.

    Uses ``--no-commit --no-ff`` to preview conflicts first. If conflicts
    exist, they are logged and committed with conflict markers left in place.
    Returns True if the merge was committed (or conflicts were committed).
    """
    try:
        # Preview merge
        r = subprocess.run(
            ["git", "merge", "--no-commit", "--no-ff", branch],
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=30,
        )

        has_conflicts = r.returncode != 0

        if has_conflicts:
            # Log conflict information
            conflict_files = _get_conflicted_files(workdir)
            if conflict_files:
                _log(
                    f"[WORKTREE-MERGE] Conflict(s) in: {', '.join(conflict_files[:10])}"
                )
            # Commit anyway with conflict markers left in place
            msg = (
                f"[worktree-merge] worker #{worker_id} from {branch} "
                f"(iteration #{iteration_count})"
                " — WITH CONFLICTS"
            )
        else:
            msg = (
                f"[worktree-merge] worker #{worker_id} from {branch} "
                f"(iteration #{iteration_count})"
            )

        subprocess.run(
            ["git", "commit", "-m", msg, "--allow-empty"],
            capture_output=True,
            cwd=workdir,
            timeout=30,
        )
        return True

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_conflicted_files(workdir: str | None) -> list[str]:
    """Return a list of files with merge conflicts."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=10,
        )
        if r.returncode == 0:
            return [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def _abort_merge(workdir: str | None) -> None:
    """Abort a merge in progress."""
    try:
        subprocess.run(
            ["git", "merge", "--abort"],
            capture_output=True,
            cwd=workdir,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def _branch_exists(workdir: str | None, branch: str) -> bool:
    """Check if a local git branch exists."""
    try:
        r = subprocess.run(
            ["git", "branch", "--list", branch],
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _delete_worktree_branch(workdir: str | None, branch: str) -> bool:
    """Delete a worktree branch (local) after successful merge.

    Returns True if the branch was deleted or didn't exist.
    """
    try:
        # Check if branch exists first
        check = subprocess.run(
            ["git", "branch", "--list", branch],
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=5,
        )
        if check.returncode == 0 and not check.stdout.strip():
            # Branch already deleted — nothing to do
            return True

        r = subprocess.run(
            ["git", "branch", "-d", branch],
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=10,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _remove_worktree_directory(
    workdir: str | None, branch: str, worktree_path: str | None
) -> bool:
    """Remove a git worktree directory.

    If *worktree_path* is known, uses ``git worktree remove``.
    Otherwise tries to prune stale worktrees.
    Gracefully handles already-removed worktrees.
    """
    try:
        if worktree_path:
            # Check if the worktree path still exists before trying to remove
            if not os.path.isdir(worktree_path):
                _log(
                    f"[WORKTREE-MERGE] Worktree path '{worktree_path}' "
                    f"for '{branch}' already removed — skipping"
                )
            else:
                subprocess.run(
                    ["git", "worktree", "remove", worktree_path],
                    capture_output=True,
                    cwd=workdir,
                    timeout=15,
                )
        # Prune any stale worktree metadata
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            cwd=workdir,
            timeout=10,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _merge_worktree_branches(
    workdir: str | None,
    iteration_count: int,
    worker_count: int,
) -> dict:
    """Detect and merge all worker worktree branches back to the main branch.

    This is called after all workers in an iteration complete. It:

    1. Detects branches matching ``hermes/*`` and ``worktree/*`` patterns.
    2. Notes the current branch and switches to the main/master branch.
    3. For each worktree branch:
       - Tries fast-forward merge first.
       - Falls back to recursive merge with conflict detection.
       - Commits with a descriptive message.
       - Deletes the worktree branch.
       - Removes the worktree directory (if applicable).
    4. Returns to the original branch.

    Args:
        workdir: Git repository working directory.
        iteration_count: Current iteration number (for commit messages).
        worker_count: Number of workers in this iteration (for logging).

    Returns:
        A dict with merge results:
        ``{"merged": int, "failed": int, "skipped": int, "details": list[dict]}``
    """
    cwd = workdir or os.getcwd()
    result: dict = {
        "merged": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
    }

    if not os.path.isdir(os.path.join(cwd, ".git")):
        _log("[WORKTREE-MERGE] Not a git repository — skipping")
        return result

    # 1. Detect worktree branches
    branches = _detect_worktree_branches(cwd)
    if not branches:
        _log("[WORKTREE-MERGE] No worktree branches found — nothing to merge")
        result["skipped"] = 0  # no-op when nothing was attempted
        return result

    _log(
        f"[WORKTREE-MERGE] Found {len(branches)} worktree branch(es): "
        f"{', '.join(b['name'] for b in branches)}"
    )

    # 2. Remember current branch
    original_branch = _get_current_branch(cwd)
    main_branch = _get_main_branch(cwd)

    # 3. Switch to main branch to perform merges
    try:
        r = subprocess.run(
            ["git", "checkout", main_branch],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=15,
        )
        if r.returncode != 0:
            _log(
                f"[WORKTREE-MERGE] Failed to checkout '{main_branch}': "
                f"{r.stderr.strip()[:120]}"
            )
            result["failed"] = len(branches)
            for b in branches:
                result["details"].append(
                    {
                        "branch": b["name"],
                        "status": "failed",
                        "reason": f"cannot checkout {main_branch}",
                    }
                )
            return result
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        _log(f"[WORKTREE-MERGE] Git checkout failed: {e}")
        result["failed"] = len(branches)
        return result

    # 4. Merge each worktree branch
    for idx, branch_info in enumerate(branches):
        branch = branch_info["name"]
        worker_id = idx  # approximate; real worker_id may differ
        _log(f"[WORKTREE-MERGE] Merging '{branch}' (worker #{worker_id})...")

        # Check if the branch still exists locally (may have been already
        # merged and deleted by another process)
        if not _branch_exists(cwd, branch):
            _log(
                f"[WORKTREE-MERGE] Branch '{branch}' no longer exists "
                "locally — skipping"
            )
            result["details"].append(
                {
                    "branch": branch,
                    "status": "skipped",
                    "reason": "branch no longer exists locally",
                }
            )
            result["skipped"] += 1
            continue

        # Try fast-forward first
        merged = _try_fast_forward_merge(cwd, branch, main_branch)
        if not merged:
            _log(
                f"[WORKTREE-MERGE] Fast-forward failed for '{branch}', "
                "trying recursive merge..."
            )
            # Abort any partial state from the failed ff attempt
            _abort_merge(cwd)
            merged = _try_recursive_merge(cwd, branch, worker_id, iteration_count)
            if not merged:
                _log(
                    f"[WORKTREE-MERGE] Recursive merge also failed for '{branch}' — "
                    "skipping"
                )
                result["failed"] += 1
                result["details"].append(
                    {
                        "branch": branch,
                        "status": "failed",
                        "reason": "both ff and recursive merge failed",
                    }
                )
                continue

        # Successful merge — delete branch and remove worktree
        _delete_worktree_branch(cwd, branch)
        _remove_worktree_directory(cwd, branch, branch_info.get("worktree_path"))
        result["merged"] += 1
        result["details"].append(
            {
                "branch": branch,
                "status": "merged",
            }
        )
        _log(f"[WORKTREE-MERGE] ✓ '{branch}' merged and cleaned up")

    # 5. Push merged changes to remote if we merged anything
    if result["merged"] > 0:
        try:
            r = subprocess.run(
                ["git", "push", "origin", main_branch],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=30,
            )
            if r.returncode == 0:
                _log("[WORKTREE-MERGE] ✓ Pushed merged changes to origin")
            else:
                _log(
                    f"[WORKTREE-MERGE] Push skipped (non-fatal): {r.stderr.strip()[:120]}"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            _log(f"[WORKTREE-MERGE] Push skipped: {e}")

    # 6. Return to original branch if it still exists
    if original_branch and original_branch != main_branch:
        if not _branch_exists(cwd, original_branch):
            _log(
                f"[WORKTREE-MERGE] Original branch '{original_branch}' no longer "
                "exists — staying on main"
            )
        else:
            try:
                subprocess.run(
                    ["git", "checkout", original_branch],
                    capture_output=True,
                    cwd=cwd,
                    timeout=15,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    _log(
        f"[WORKTREE-MERGE] Done — {result['merged']} merged, "
        f"{result['failed']} failed"
    )
    return result
