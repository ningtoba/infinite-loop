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
    main_branch = _get_main_branch(cwd)
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
                if name and name != main_branch:
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
                if (
                    name
                    and name != main_branch
                    and not any(b["ref"] == name for b in branches)
                ):
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
                        existing_refs = {b["ref"]: i for i, b in enumerate(branches)}
                        if ref not in existing_refs:
                            branches.append(
                                {"ref": ref, "name": ref, "worktree_path": path}
                            )
                        else:
                            # Update existing entry with worktree_path (lost by the branch --list scan)
                            idx = existing_refs[ref]
                            if branches[idx].get("worktree_path") is None and path:
                                branches[idx]["worktree_path"] = path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return branches


def _detect_remote_worktree_branches(
    workdir: str | None, remote: str = "origin"
) -> list[dict]:
    """Find remote worktree branches (*hermes/*, *worktree/*) on the remote.

    Refreshes the remote tracking refs first via ``git fetch``.
    Excludes the main/master branch.

    Returns a list of dicts with ``ref`` (full remote ref like
    ``origin/hermes/abc``) and ``name`` (bare branch name like
    ``hermes/abc``).
    """
    cwd = workdir or os.getcwd()
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return []

    # Fetch from remote to ensure we have the latest refs
    try:
        subprocess.run(
            ["git", "fetch", remote],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    main_branch = _get_main_branch(cwd)
    branches: list[dict] = []

    try:
        r = subprocess.run(
            ["git", "branch", "-r", "--list", f"{remote}/hermes/*"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if r.returncode == 0:
            _parse_remote_branches(r.stdout, remote, main_branch, branches)

        r = subprocess.run(
            ["git", "branch", "-r", "--list", f"{remote}/worktree/*"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if r.returncode == 0:
            _parse_remote_branches(r.stdout, remote, main_branch, branches)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return branches


def _parse_remote_branches(
    stdout: str, remote: str, main_branch: str, branches: list[dict]
) -> None:
    """Parse ``git branch -r`` output, appending matching entries to *branches*.

    Each entry has ``ref`` (e.g. ``origin/hermes/abc``) and ``name``
    (e.g. ``hermes/abc`` — the bare branch name).
    """
    for line in stdout.strip().splitlines():
        name = line.strip()
        if not name:
            continue
        bare = name.removeprefix(f"{remote}/")
        if bare and bare != main_branch:
            if not any(b["ref"] == name for b in branches):
                branches.append({"ref": name, "name": bare})


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

    Returns True if the merge was applied OR if the branch is already
    up-to-date with main (changes were already committed by another
    process, e.g. git_commit mode).
    """
    try:
        r = subprocess.run(
            ["git", "merge", "--ff-only", branch],
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=30,
        )
        if r.returncode == 0:
            return True
        # "Already up to date" with non-zero exit is still a success
        # (the branch has no new changes beyond what's already on main)
        if (
            "already up to date" in r.stderr.lower()
            or "already up to date" in r.stdout.lower()
        ):
            return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _pull_main_branch(workdir: str | None, main_branch: str) -> bool:
    """Pull the latest main/master from remote before attempting merge.

    Returns True if pull succeeded or remote is unavailable (best-effort).
    """
    try:
        r = subprocess.run(
            ["git", "pull", "--ff-only", "origin", main_branch],
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=30,
        )
        # Non-zero exit on pull is normal if no remote or network issues
        if r.returncode == 0:
            _log(f"[WORKTREE-MERGE] ✓ Pulled latest '{main_branch}' from origin")
            return True
        # "Already up to date" is fine
        if "already up to date" in (r.stderr + r.stdout).lower():
            return True
        _log(f"[WORKTREE-MERGE] Pull skipped (non-fatal): {r.stderr.strip()[:80]}")
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _merge_with_conflict_tracking(
    workdir: str | None, branch: str, worker_id: int, iteration_count: int
) -> dict:
    """Attempt a recursive merge with conflict detection and file tracking.

    Uses ``--no-commit --no-ff`` to preview conflicts first. If conflicts
    exist, they are logged and committed with conflict markers left in place.

    Returns a dict with ``{"success": bool, "conflict_files": list[str]}``.
    """
    result: dict = {"success": False, "conflict_files": []}
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
            result["conflict_files"] = conflict_files
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
        result["success"] = True
        return result

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return result


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
    if not branch:
        return False
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

    Also attempts to delete the remote tracking branch if it exists.
    Returns True if the branch was deleted or didn't exist.
    """
    if not branch:
        return True
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


def _delete_remote_worktree_branch(
    workdir: str | None, branch: str, remote: str = "origin"
) -> bool:
    """Delete a remote worktree branch via push --delete.

    Also cleans up the local remote-tracking ref (e.g. origin/hermes/xyz).

    Returns True if the remote branch was deleted or never existed.
    """
    if not branch:
        return True
    cwd = workdir or os.getcwd()
    # Use the bare branch name (without origin/ prefix) for push --delete
    bare_branch = (
        branch.replace(f"{remote}/", "", 1)
        if branch.startswith(f"{remote}/")
        else branch
    )
    try:
        r = subprocess.run(
            ["git", "push", remote, "--delete", bare_branch],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=15,
        )
        if r.returncode == 0:
            _log(f"[WORKTREE-CLEANUP] ✓ Deleted remote '{remote}/{bare_branch}'")
            # Prune the local remote-tracking ref
            subprocess.run(
                ["git", "remote", "prune", remote],
                capture_output=True,
                cwd=cwd,
                timeout=10,
            )
            return True
        # "could not delete" / "no such ref" are non-fatal (branch already gone)
        if "does not exist" in r.stderr.lower() or "no such" in r.stderr.lower():
            return True
        return False
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


def _extract_worker_from_branch(branch_name: str) -> int | None:
    """Extract worker ID from a branch name like ``hermes/iter-7-w-0``.

    Returns the worker ID integer, or None if the branch doesn't follow
    the expected pattern.
    """
    import re

    m = re.search(r"[_-]w[_-](\d+)$", branch_name)
    if m:
        return int(m.group(1))
    # Also try patterns like hermes-iter7-w0
    m = re.search(r"w(\d+)$", branch_name)
    if m:
        return int(m.group(1))
    return None


def cleanup_stale_worktrees(workdir: str | None) -> dict:
    """Clean up stale worktree branches and directories before spawning.

    Hermes worktree creation fails if a branch name already exists. This
    function prunes leftover branches/worktrees from previous runs that
    weren't cleaned up (e.g. due to crashes or interrupted runs).

    Returns a dict with cleanup stats: ``{"pruned": int, "errors": int}``.
    """
    cwd = workdir or os.getcwd()
    result: dict = {"pruned": 0, "errors": 0, "details": []}

    if not os.path.isdir(os.path.join(cwd, ".git")):
        return result

    # 1. Prune stale worktree metadata first
    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            cwd=cwd,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 2. Detect stale branches
    branches = _detect_worktree_branches(cwd)
    if not branches:
        return result

    _log(
        f"[WORKTREE-CLEANUP] Found {len(branches)} stale worktree branch(es) "
        f"from previous runs — cleaning up"
    )

    # 3. Switch to main branch
    main_branch = _get_main_branch(cwd)
    original_branch = _get_current_branch(cwd)
    _abort_merge(cwd)

    try:
        subprocess.run(
            ["git", "checkout", main_branch],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 4. Try to merge and delete each stale branch.
    # Track names of branches that were actually pruned so we can clean up
    # remote tracking refs for only those (not all detected branches).
    pruned_branches: list[str] = []
    for branch_info in branches:
        branch = branch_info["name"]
        if not _branch_exists(cwd, branch):
            continue

        _log(f"[WORKTREE-CLEANUP] Cleaning up '{branch}'...")

        # Try to merge changes back (best effort — don't fail if conflicts)
        if _try_fast_forward_merge(cwd, branch, main_branch):
            _log(f"[WORKTREE-CLEANUP]   Merged '{branch}' into {main_branch}")
        else:
            # Try recursive merge, abort if conflicts
            merge_result = _merge_with_conflict_tracking(cwd, branch, 0, 0)
            if not merge_result.get("success"):
                _abort_merge(cwd)
                _log(f"[WORKTREE-CLEANUP]   Could not merge '{branch}' — discarding")
                # Force-delete the branch since we can't merge it
                try:
                    subprocess.run(
                        ["git", "branch", "-D", branch],
                        capture_output=True,
                        cwd=cwd,
                        timeout=10,
                    )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

        # Delete branch (if still exists) and remove worktree
        _delete_worktree_branch(cwd, branch)
        _remove_worktree_directory(cwd, branch, branch_info.get("worktree_path"))
        result["pruned"] += 1
        pruned_branches.append(branch)

    # Push only main branch (never worktree branches)
    if result["pruned"] > 0:
        # Delete remote tracking refs for branches that were actually pruned
        for branch in pruned_branches:
            _delete_remote_worktree_branch(cwd, branch)
        # Push main
        try:
            subprocess.run(
                ["git", "push", "origin", main_branch],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # 5. Return to original branch
    if (
        original_branch
        and original_branch != main_branch
        and _branch_exists(cwd, original_branch)
    ):
        try:
            subprocess.run(
                ["git", "checkout", original_branch],
                capture_output=True,
                cwd=cwd,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    _log(f"[WORKTREE-CLEANUP] Done — {result['pruned']} branch(es) cleaned up")
    return result


def _sweep_remaining_remote_branches(
    workdir: str | None, main_branch: str | None = None, remote: str = "origin"
) -> int:
    """Final sweep: delete any remaining hermes/* or worktree/* branches on remote.

    This is called after merges to ensure no worker branches pile up on GitHub.
    Returns the number of branches deleted in the sweep.
    """
    cwd = workdir or os.getcwd()
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return 0

    remaining = _detect_remote_worktree_branches(cwd, remote)
    if not remaining:
        return 0

    _log(
        f"[WORKTREE-SWEEP] Found {len(remaining)} remaining remote "
        f"worktree branch(es) — deleting..."
    )
    deleted = 0
    for rb in remaining:
        if _delete_remote_worktree_branch(cwd, rb["name"], remote):
            deleted += 1
    # Prune stale remote-tracking refs
    try:
        subprocess.run(
            ["git", "remote", "prune", remote],
            capture_output=True,
            cwd=cwd,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    _log(f"[WORKTREE-SWEEP] Deleted {deleted} remaining remote branch(es)")
    return deleted


def _cleanup_stale_remote_branches(workdir: str | None, remote: str = "origin") -> dict:
    """Comprehensive cleanup of stale remote worktree branches.

    This is called BEFORE each iteration (in addition to the local
    cleanup_stale_worktrees). It:

    1. Fetches remote refs and detects all ``hermes/*`` and ``worktree/*``
       branches on the remote.
    2. Creates local tracking branches for any remote branches that don't
       exist locally.
    3. Tries to merge each branch into the main branch (FF first, then
       recursive).
    4. After merging, deletes both the local and remote branches.
    5. Pushes only the main branch to remote.
    6. Does a final sweep to ensure no hermes/* or worktree/* branches
       remain on the remote.

    This prevents the accumulation of stale worker branches on GitHub
    when workers fail or the job is interrupted.

    Returns a dict with cleanup stats:
    ``{"merged": int, "deleted": int, "failed": int, "details": list[dict]}``.
    """
    cwd = workdir or os.getcwd()
    result: dict = {"merged": 0, "deleted": 0, "failed": 0, "details": []}

    if not os.path.isdir(os.path.join(cwd, ".git")):
        return result

    # 1. Detect remote worktree branches
    remote_branches = _detect_remote_worktree_branches(cwd, remote)
    if not remote_branches:
        _log("[WORKTREE-REMOTE] No remote worktree branches found — remote is clean")
        return result

    _log(
        f"[WORKTREE-REMOTE] Found {len(remote_branches)} remote worktree branch(es): "
        f"{', '.join(b['name'] for b in remote_branches)}"
    )

    main_branch = _get_main_branch(cwd)
    original_branch = _get_current_branch(cwd)
    _abort_merge(cwd)

    # 2. Switch to main branch
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
                f"[WORKTREE-REMOTE] Cannot checkout '{main_branch}': "
                f"{r.stderr.strip()[:120]}"
            )
            return result
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        _log(f"[WORKTREE-REMOTE] Git checkout failed: {e}")
        return result

    # Pull latest main from remote for up-to-date base
    _pull_main_branch(cwd, main_branch)

    # 3. Process each remote worktree branch
    for branch_info in remote_branches:
        branch = branch_info["name"]  # bare name like hermes/xyz
        full_remote_ref = branch_info["ref"]  # full ref like origin/hermes/xyz
        _log(f"[WORKTREE-REMOTE] Processing remote '{full_remote_ref}'...")

        # Create a local tracking branch for the remote branch
        try:
            r = subprocess.run(
                ["git", "checkout", "-b", branch, full_remote_ref],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=15,
            )
            if r.returncode != 0:
                # Branch may already exist locally — checkout what we have
                subprocess.run(
                    ["git", "checkout", branch],
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=15,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Switch back to main for the merge
        try:
            subprocess.run(
                ["git", "checkout", main_branch],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Try fast-forward merge
        merged = _try_fast_forward_merge(cwd, branch, main_branch)
        if merged:
            _log(f"[WORKTREE-REMOTE] ✓ Merged '{branch}' into {main_branch}")
            result["merged"] += 1
            result["details"].append(
                {"branch": branch, "status": "merged", "via": "ff"}
            )
        else:
            _abort_merge(cwd)
            # Try recursive merge with conflict tracking
            merge_result = _merge_with_conflict_tracking(cwd, branch, 0, 0)
            if merge_result.get("success"):
                _log(f"[WORKTREE-REMOTE] ✓ Merged '{branch}' via recursive merge")
                result["merged"] += 1
                result["details"].append(
                    {
                        "branch": branch,
                        "status": "merged",
                        "via": "recursive",
                        "conflict_files": merge_result.get("conflict_files", []),
                    }
                )
            else:
                _abort_merge(cwd)
                _log(
                    f"[WORKTREE-REMOTE] ✗ Could not merge '{branch}' — "
                    "force-deleting local copy"
                )
                result["failed"] += 1
                result["details"].append(
                    {"branch": branch, "status": "failed", "reason": "merge failed"}
                )
                # Force-delete the local branch since we can't merge
                try:
                    subprocess.run(
                        ["git", "branch", "-D", branch],
                        capture_output=True,
                        cwd=cwd,
                        timeout=10,
                    )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

        # 4. Delete the local branch (if it still exists after merge)
        _delete_worktree_branch(cwd, branch)
        # 5. Delete the remote branch
        remote_ok = _delete_remote_worktree_branch(cwd, branch, remote)
        if remote_ok:
            _log(f"[WORKTREE-REMOTE] ✓ Cleaned up '{branch}' locally and remotely")
            result["deleted"] += 1
        else:
            _log(f"[WORKTREE-REMOTE] ⚠ Could not delete remote '{branch}'")

    # 6. Push merged main to remote
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
                _log("[WORKTREE-REMOTE] ✓ Pushed merged changes to origin")
            else:
                _log(f"[WORKTREE-REMOTE] Push skipped: {r.stderr.strip()[:120]}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            _log(f"[WORKTREE-REMOTE] Push skipped: {e}")

    # 7. Final sweep: ensure no hermes/* or worktree/* remain on remote
    sweep_count = _sweep_remaining_remote_branches(cwd, main_branch, remote)
    if sweep_count > 0:
        # Push main again in case sweep removed remaining refs
        try:
            subprocess.run(
                ["git", "push", "origin", main_branch],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    else:
        _log("[WORKTREE-REMOTE] Sweep: no remaining hermes/* branches on remote")

    # 8. Return to original branch
    if (
        original_branch
        and original_branch != main_branch
        and _branch_exists(cwd, original_branch)
    ):
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
        f"[WORKTREE-REMOTE] Done — {result['merged']} merged, "
        f"{result['deleted']} deleted, {result['failed']} failed"
    )
    return result


def _merge_worktree_branches(
    workdir: str | None,
    iteration_count: int,
    worker_count: int,
    worker_ids: list[int] | None = None,
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
        ``{"merged": int, "failed": int, "skipped": int, "details": list[dict],
            "per_worker": dict, "total_conflicts": int, "source_branches": list[str]}``
    """
    cwd = workdir or os.getcwd()
    result: dict = {
        "merged": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
        "per_worker": {},
        "total_conflicts": 0,
        "source_branches": [],
    }

    if not os.path.isdir(os.path.join(cwd, ".git")):
        _log("[WORKTREE-MERGE] Not a git repository — skipping")
        return result

    # Pre-populate per_worker tracking
    worker_set = set(worker_ids) if worker_ids else set(range(worker_count))
    for wid in worker_set:
        result["per_worker"][str(wid)] = {"status": "not_found", "branch": None}

    # 1. Detect worktree branches
    branches = _detect_worktree_branches(cwd)
    if not branches:
        _log("[WORKTREE-MERGE] No worktree branches found — nothing to merge")
        # skipped = 0 is correct; nothing was attempted
        return result

    _log(
        f"[WORKTREE-MERGE] Found {len(branches)} worktree branch(es): "
        f"{', '.join(b['name'] for b in branches)}"
    )

    # Record source branches for the merge result (used by WebUI for display)
    result["source_branches"] = [b["name"] for b in branches]

    # Update per_worker: mark workers whose branches were found
    for branch_info in branches:
        branch = branch_info["name"]
        extracted_wid = _extract_worker_from_branch(branch)
        if extracted_wid is not None:
            wid_str = str(extracted_wid)
            if wid_str in result["per_worker"]:
                result["per_worker"][wid_str] = {
                    "status": "found",
                    "branch": branch,
                }

    # For workers still not_found after scanning all detected branches,
    # add a descriptive reason mentioning the branch pattern mismatch
    for _, pws in result["per_worker"].items():
        if pws["status"] == "not_found":
            pws["reason"] = (
                "no worktree branch matched this worker — "
                "branch naming differs from expected pattern"
            )

    # 2. Remember current branch
    original_branch = _get_current_branch(cwd)
    main_branch = _get_main_branch(cwd)

    # Abort any stale merge state left from a previous interrupted run
    _abort_merge(cwd)

    # Stash any local changes on main before merging (protects uncommitted work)
    _log(f"[WORKTREE-MERGE] Switching to '{main_branch}' for merges...")

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

    # 4. Pull latest main from remote (best-effort) to reduce merge conflicts
    _pull_main_branch(cwd, main_branch)

    # 5. Merge each worktree branch
    for idx, branch_info in enumerate(branches):
        branch = branch_info["name"]
        # Extract worker ID from branch name for accurate tracking
        extracted_wid = _extract_worker_from_branch(branch)
        worker_id = (
            extracted_wid
            if extracted_wid is not None
            else (idx if worker_ids is None or idx < len(worker_ids) else 0)
        )
        _log(f"[WORKTREE-MERGE] Merging '{branch}' (worker #{worker_id})...")

        # Mark per_worker status
        wid_str = str(worker_id)
        if wid_str in result["per_worker"]:
            result["per_worker"][wid_str] = {"status": "merging", "branch": branch}

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
            # Per-worker tracking
            result["per_worker"][wid_str] = {
                "status": "skipped",
                "branch": branch,
                "reason": "no longer exists",
            }
            continue

        # Try fast-forward first
        merged = _try_fast_forward_merge(cwd, branch, main_branch)
        merge_cf = []
        if not merged:
            _log(
                f"[WORKTREE-MERGE] Fast-forward failed for '{branch}', "
                "trying recursive merge..."
            )
            # Abort any partial state from the failed ff attempt
            _abort_merge(cwd)
            merge_result = _merge_with_conflict_tracking(
                cwd, branch, worker_id, iteration_count
            )
            if not merge_result.get("success"):
                _log(
                    f"[WORKTREE-MERGE] Recursive merge also failed for "
                    f"'{branch}' — skipping"
                )
                result["failed"] += 1
                result["details"].append(
                    {
                        "branch": branch,
                        "status": "failed",
                        "reason": "both ff and recursive merge failed",
                    }
                )
                result["per_worker"][wid_str] = {
                    "status": "failed",
                    "branch": branch,
                    "reason": "both ff and recursive merge failed",
                }
                continue
            # Recursive merge succeeded — store conflict files if any
            merge_cf = merge_result.get("conflict_files", [])
            if merge_cf:
                _log(
                    f"[WORKTREE-MERGE] Merged '{branch}' with "
                    f"{len(merge_cf)} conflict file(s): "
                    f"{', '.join(merge_cf[:5])}"
                )

        # Successful merge — delete branch and remove worktree
        _delete_worktree_branch(cwd, branch)
        _remove_worktree_directory(cwd, branch, branch_info.get("worktree_path"))
        # Also delete the remote tracking branch to prevent pile-up on GitHub
        _delete_remote_worktree_branch(cwd, branch)
        result["merged"] += 1
        detail_entry = {
            "branch": branch,
            "status": "merged",
        }
        # Capture conflict file info from the recursive merge result
        if merge_cf:
            detail_entry["conflict_files"] = merge_cf
        result["details"].append(detail_entry)
        result["per_worker"][wid_str] = {"status": "merged", "branch": branch}
        _log(f"[WORKTREE-MERGE] ✓ '{branch}' merged and cleaned up")

    # Aggregate total conflict count across all merge results
    for d in result["details"]:
        if d.get("conflict_files"):
            result["total_conflicts"] += len(d["conflict_files"])

    # 6. Push merged changes to remote if we merged anything
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

    # 7. Re-run merge with remaining unmerged branches if any failed
    #    (second pass: try recursive merge, then pull+rebase, for any FF failures)
    failed_branches = [d for d in result["details"] if d["status"] == "failed"]
    if failed_branches and not any(d.get("retried") for d in result["details"]):
        _log(
            f"[WORKTREE-MERGE] Retrying {len(failed_branches)} failed branch(es) "
            "with recursive merge as second attempt..."
        )
        for branch_info in branches:
            branch = branch_info["name"]
            # Check if this branch already failed
            failed_detail = next(
                (
                    d
                    for d in result["details"]
                    if d["branch"] == branch and d["status"] == "failed"
                ),
                None,
            )
            if not failed_detail:
                continue
            if not _branch_exists(cwd, branch):
                _log(
                    f"[WORKTREE-MERGE] Branch '{branch}' no longer exists "
                    "locally on retry — skipping"
                )
                failed_detail["status"] = "skipped"
                failed_detail["reason"] = "no longer exists on retry"
                result["failed"] -= 1
                result["skipped"] += 1
                continue
            _log(f"[WORKTREE-MERGE] Retrying '{branch}' with recursive merge...")
            _abort_merge(cwd)
            extracted_wid = _extract_worker_from_branch(branch)
            worker_id = extracted_wid if extracted_wid is not None else 0
            merge_result = _merge_with_conflict_tracking(
                cwd, branch, worker_id, iteration_count
            )
            if merge_result.get("success"):
                _delete_worktree_branch(cwd, branch)
                _remove_worktree_directory(
                    cwd, branch, branch_info.get("worktree_path")
                )
                # Also delete the remote tracking branch
                _delete_remote_worktree_branch(cwd, branch)
                result["merged"] += 1
                result["failed"] -= 1
                failed_detail["status"] = "merged"
                failed_detail["retried"] = True
                _log(f"[WORKTREE-MERGE] ✓ '{branch}' merged on retry")
                # Update per_worker status
                wid_str = str(worker_id)
                if wid_str in result["per_worker"]:
                    result["per_worker"][wid_str] = {
                        "status": "merged",
                        "branch": branch,
                    }
            else:
                _abort_merge(cwd)
                failed_detail["retried"] = True
                _log(f"[WORKTREE-MERGE] ✗ '{branch}' still failing after retry")
        # Push again if new merges succeeded on retry
        if result["merged"] > 0:
            try:
                subprocess.run(
                    ["git", "push", "origin", main_branch],
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=30,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    # 7b. Final sweep: delete any remaining remote hermes/* branches
    #     (catches branches that were pushed but never merged)
    _sweep_remaining_remote_branches(cwd, main_branch)

    # 8. Return to original branch if it still exists
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
