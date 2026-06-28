"""Stats recalculation helpers."""


def _recalc_stats(state: dict) -> None:
    error_count = sum(1 for it in state.get("iterations", []) if it.get("error"))
    total = len(state.get("iterations", []))
    success_count = total - error_count
    total_dur = sum(it.get("duration_seconds", 0) for it in state.get("iterations", []))
    consecutive_errors = 0
    consecutive_successes = 0
    for it in reversed(state.get("iterations", [])):
        if it.get("error"):
            if consecutive_successes > 0:
                break
            consecutive_errors += 1
        else:
            if consecutive_errors > 0:
                break
            consecutive_successes += 1

    # Aggregate remote cleanup totals across all iterations
    rc_totals = {
        "remote_deleted": 0,
        "remote_merged": 0,
        "stale_pruned": 0,
        "remote_failed": 0,
    }
    for it in state.get("iterations", []):
        rc = it.get("remote_cleanup") or {}
        rc_totals["remote_deleted"] += rc.get("remote_deleted", 0)
        rc_totals["remote_merged"] += rc.get("remote_merged", 0)
        rc_totals["stale_pruned"] += rc.get("stale_pruned", 0)
        rc_totals["remote_failed"] += rc.get("remote_failed", 0)

    state["stats"] = {
        "total_duration_seconds": round(total_dur, 1),
        "avg_duration_seconds": round(total_dur / max(total, 1), 1),
        "success_count": success_count,
        "error_count": error_count,
        "consecutive_errors": consecutive_errors,
        "consecutive_successes": consecutive_successes,
        "remote_cleanup_totals": rc_totals,
    }
