"""Error classification and progress classification utilities."""

from .file_utils import _log


def classify_error(error_str: str | None) -> str | None:
    """Categorize an error message for better diagnostics.

    Returns one of: 'timeout', 'network', 'schema', 'unknown', or None for no error.
    """
    if not error_str:
        return None
    error_lower = error_str.lower()
    if any(kw in error_lower for kw in ["timeout", "timed out"]):
        return "timeout"
    if any(
        kw in error_lower
        for kw in [
            "connection refused",
            "connectionerror",
            "connection error",
            "connection reset",
            "network",
            "dns",
            "resolve",
            "refused",
            "no route",
        ]
    ):
        return "network"
    if any(kw in error_lower for kw in ["schema", "validation", "invalid"]):
        return "schema"
    return "unknown"


def _classify_progress(
    summary: str,
    git_before: dict | None,
    git_after: dict | None,
    error: str | None,
) -> str:
    """Categorize iteration progress for ledger tracking.

    Analyzes the iteration summary, git diff state, and error field to classify
    the iteration's outcome into one of: 'completed', 'progress', 'partial',
    'stuck', 'regression', or 'unknown'.
    """
    # --- Determine whether git changes occurred ---
    has_git_changes = False
    if git_before and git_after:
        git_before_stat = git_before.get("diff_stat", "")
        git_after_stat = git_after.get("diff_stat", "")
        has_git_changes = git_before_stat != git_after_stat

    summary_lower = summary.lower().strip()
    summary_len = len(summary_lower)

    # --- Rule: completed ---
    completed_keywords = [
        "completed",
        "finished",
        "all done",
        "all tasks",
        "all fixes",
        "task complete",
        "goal achieved",
    ]
    if any(kw in summary_lower for kw in completed_keywords):
        return "completed"

    # --- Rule: regression (error + no git changes = things got worse) ---
    if error and not has_git_changes:
        return "regression"

    # --- Rule: stuck (no changes + short summary or repetitive failure language) ---
    stuck_failure_keywords = ["still working", "cannot", "unable", "failed to"]
    if not has_git_changes and (
        summary_len < 30 or any(kw in summary_lower for kw in stuck_failure_keywords)
    ):
        return "stuck"

    # --- Rule: progress (has git changes + positive language) ---
    positive_keywords = [
        "added",
        "fixed",
        "implemented",
        "created",
        "updated",
        "improved",
        "refactored",
        "modified",
    ]
    if has_git_changes and any(kw in summary_lower for kw in positive_keywords):
        return "progress"

    # --- Rule: partial (changes made but also errors or mentions remaining work) ---
    remaining_keywords = [
        "remaining",
        "in progress",
        "partial",
        "not yet",
        "still needs",
        "work in progress",
        "wip",
        "todo",
        "left to do",
    ]
    if has_git_changes and (
        error or any(kw in summary_lower for kw in remaining_keywords)
    ):
        return "partial"

    # --- Fallback ---
    return "unknown"
