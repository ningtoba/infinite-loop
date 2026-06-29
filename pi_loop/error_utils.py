"""Error classification and progress classification utilities."""


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
            "connection closed",
            "network",
            "dns",
            "resolve",
            "refused",
            "no route",
            "unreachable",
            "host unreachable",
            "no host",
            "cannot connect",
            "rate limit",
            "too many requests",
            "service unavailable",
            "bad gateway",
            "gateway timeout",
            "server error",
            "internal server error",
            "503",
            "502",
            "504",
            "429",
            "econnrefused",
            "econnreset",
            "etimedout",
            "ehostunreach",
            "enetunreach",
            "socket",
            "tls",
            "ssl",
            "certificate",
        ]
    ):
        return "network"
    if any(kw in error_lower for kw in ["schema", "validation", "invalid"]):
        return "schema"
    return "unknown"


def _suggest_actionable_fix(
    error_type: str | None,
    classification: str,
    goal: str,
    workers: int = 1,
    use_library: bool = False,
    consecutive_errors: int = 0,
    git: bool = False,
    git_commit: bool = False,
    force_reset: bool = False,
) -> str | None:
    """Generate a human-readable, actionable suggestion based on the error/classification.

    Maps common failure patterns to specific CLI flags and configuration changes
    the user can make.  Considers already-enabled flags (``git``, ``git_commit``,
    ``force_reset``) to avoid stale advice.

    Returns None when no suggestion is warranted (e.g. completed successfully).

    Suggestion priority: errors > stuck/regression > partial > running fine.
    """
    goal_lower = goal.lower()

    # --- No suggestion for clean iterations ---
    if classification == "completed":
        return None
    if classification == "progress":
        return None
    if error_type is None and classification not in ("stuck", "regression", "unknown"):
        return None

    # ── Help map: error_type → (suggestion, condition_check) ─────────────────
    # Each entry: (suggestion_text, should_show_if_not_error)

    if error_type == "timeout":
        return (
            "Suggestions:"
            "\n  • Increase --session-timeout (default 7200s) for long-running tasks"
            "\n  • Reduce --max-turns if sessions are timing out from turn exhaustion"
            "\n  • Check --workers > 1 — concurrent sessions may each need more time"
        )

    if error_type == "network":
        tips = [
            "Suggestions:",
            "  • Check network connectivity and API endpoint availability",
            "  • Verify the pi provider config is correct",
            "  • Add --retry-delay 30 to wait between retries on network failures",
            "  • Run with --preflight to check the environment before the loop starts",
        ]
        return "\n".join(tips)

    if error_type == "schema":
        return (
            "Suggestions:"
            "\n  • Review --output-schema — the spawned session's output didn't match"
            "\n  • Check --output-schema-file for format or type mismatches"
            "\n  • Simplify the schema for more lenient validation"
        )

    # ── High consecutive errors (3+) — most actionable warning ──────────────
    # Check BEFORE error-type handlers so repeated failures get the escalation
    # treatment rather than a generic per-type message.
    if consecutive_errors >= 3 and error_type is not None and classification in ("stuck", "unknown", "regression"):
        return (
            "Suggestions:"
            "\n  • Run with --preflight to check the environment before the loop"
            "\n  • Reduce --workers to 1 to eliminate concurrency issues"
            "\n  • Check --goal text for ambiguities that confuse spawned sessions"
            "\n  • Add --context with more explicit instructions and constraints"
        )

    # ── Classification-based suggestions (no specific error type) ────────────
    if classification == "stuck":
        tips = [
            "Suggestions:",
        ]
        if workers > 1 and not use_library:
            tips.append("  • Set --workers 1 to isolate the issue (concurrent sessions may interfere)")
        if not use_library:
            tips.append("  • Try --use-library for in-process execution (bypasses subprocess issues)")
        tips.append("  • Add --evolve to let iterations self-direct when stuck in a loop")
        if "convergence" in goal_lower or "similar" in goal_lower:
            tips.append("  • Adjust --convergence-threshold (lower = less sensitive) or --convergence-window")
        return "\n".join(tips)

    if classification == "regression":
        tips = [
            "Suggestions:",
        ]
        if git:
            tips.append("  • Previous changes may have broken something — review the git diff")
        else:
            tips.append("  • Add --git to track file changes across iterations")
        if not force_reset:
            tips.append("  • Run with --force-reset to start with a clean ledger")
        if not git_commit:
            tips.append("  • Add --git-commit so each iteration is a revert-able commit")
        if not tips[1:]:  # only "Suggestions:" header, nothing useful
            return None
        # If the only tip is a review note (not an actionable flag change), skip it
        no_op_tip = "  • Previous changes may have broken something — review the git diff"
        if len(tips) == 2 and tips[1] == no_op_tip:
            return None
        return "\n".join(tips)

    if classification == "partial":
        return (
            "Tip: The iteration made some changes but reported remaining work."
            "\n  This may be expected for iterative tasks. Continue running or"
            "\n  consider adding --evolve to let the daemon self-direct."
        )

    if classification == "unknown":
        return (
            "Tip: The iteration's output didn't match any known pattern."
            "\n  This is usually fine for early iterations on novel goals."
        )

    return None
