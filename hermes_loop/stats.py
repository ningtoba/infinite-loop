"""Stats recalculation helpers."""


def _recalc_stats(state: dict) -> None:
    error_count = sum(1 for it in state.get("iterations", []) if it.get("error"))
    total = len(state.get("iterations", []))
    success_count = total - error_count
    total_dur = sum(it.get("duration_seconds", 0) for it in state.get("iterations", []))
    consecutive = 0
    for it in reversed(state.get("iterations", [])):
        if it.get("error"):
            consecutive += 1
        else:
            break
    state["stats"] = {
        "total_duration_seconds": round(total_dur, 1),
        "avg_duration_seconds": round(total_dur / max(total, 1), 1),
        "success_count": success_count,
        "error_count": error_count,
        "consecutive_errors": consecutive,
    }
