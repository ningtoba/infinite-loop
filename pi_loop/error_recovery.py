"""Automatic Error Recovery — per-type adaptation engine."""

from collections.abc import Callable
from datetime import datetime, timezone

from .config import _ERROR_SEVERITY, _ERROR_THRESHOLDS
from .file_utils import _log

# Original values snapshot (set via _set_originals, called from run_loop)
_ORIGINAL_SESSION_TIMEOUT: int = 0
_ORIGINAL_COOLDOWN: int = 0
_ORIGINAL_USE_LIBRARY: bool = False
_ORIGINAL_WORKERS: int = 1


def _set_originals(session_timeout: int, cooldown: int, use_library: bool, workers: int) -> None:
    """Set original baseline values from run_loop for mitigation comparisons."""
    global _ORIGINAL_SESSION_TIMEOUT, _ORIGINAL_COOLDOWN, _ORIGINAL_USE_LIBRARY, _ORIGINAL_WORKERS
    _ORIGINAL_SESSION_TIMEOUT = session_timeout
    _ORIGINAL_COOLDOWN = cooldown
    _ORIGINAL_USE_LIBRARY = use_library
    _ORIGINAL_WORKERS = workers


def _pick_primary_error(types: list[str]) -> str:
    """Return the most severe error type from a list."""
    return max(types, key=lambda t: _ERROR_SEVERITY.get(t, 0))


def _adapt_to_error(
    error_type: str | None,
    mitigations: dict,
    consecutive_successes: int,
    error_type_counts: dict,
    session_timeout: int,
    cooldown: int,
    cooldown_mode: str,
    use_library: bool,
    workers: int,
    log_fn: Callable | None = None,
) -> tuple:
    """Adapt runtime parameters based on error type and history."""
    global _ORIGINAL_SESSION_TIMEOUT, _ORIGINAL_COOLDOWN, _ORIGINAL_USE_LIBRARY, _ORIGINAL_WORKERS

    if log_fn is None:
        log_fn = _log

    actions: list[str] = []
    level_before = mitigations.get("mitigation_level", 0)
    new_timeout = session_timeout
    new_cooldown = cooldown
    new_mode = cooldown_mode
    new_library = use_library
    new_workers = workers
    new_level = level_before

    # --- Success: ramp down ---
    if error_type is None:
        if level_before > 0:
            if consecutive_successes == 1:
                new_timeout = max(
                    _ORIGINAL_SESSION_TIMEOUT,
                    int(session_timeout or 0) * 75 // 100,
                )
                if cooldown_mode != "adaptive" and cooldown > _ORIGINAL_COOLDOWN:
                    new_cooldown = max(
                        _ORIGINAL_COOLDOWN,
                        cooldown // 2,
                    )
                actions.append(
                    f"[RECOVERY] Partial unwind (1st success): timeout={new_timeout}s, cooldown={new_cooldown}s"
                )
                new_level = max(0, level_before - 1)

            elif consecutive_successes >= 3:
                new_timeout = _ORIGINAL_SESSION_TIMEOUT
                new_cooldown = _ORIGINAL_COOLDOWN
                new_mode = "fixed" if _ORIGINAL_COOLDOWN > 0 else cooldown_mode
                new_library = _ORIGINAL_USE_LIBRARY
                new_workers = _ORIGINAL_WORKERS
                actions.append("[RECOVERY] Full recovery: all mitigations reset to original values")
                new_level = 0

            mitigations["mitigation_level"] = new_level
            mitigations["timeout_increased"] = new_timeout > _ORIGINAL_SESSION_TIMEOUT
            mitigations["cooldown_elevated"] = new_cooldown > _ORIGINAL_COOLDOWN
            mitigations["force_subprocess"] = not new_library
            mitigations["reduced_workers"] = new_workers < _ORIGINAL_WORKERS

        return (
            new_timeout,
            new_cooldown,
            new_mode,
            new_library,
            new_workers,
            actions,
        )

    # --- Error: ramp up ---
    count = error_type_counts.get(error_type, 0)
    thresholds = _ERROR_THRESHOLDS.get(error_type, {"mild": 999, "moderate": 999, "stop": 999})

    stop_threshold = thresholds.get("stop")
    if stop_threshold is not None and count >= stop_threshold:
        target_level = 3
    elif thresholds.get("moderate") is not None and count >= (thresholds.get("moderate") or 999):
        target_level = 2
    elif count >= thresholds.get("mild", 999):
        target_level = 1
    else:
        target_level = 0

    new_level = max(level_before, target_level)

    if new_level >= 1 and level_before < 1:
        if error_type == "timeout":
            new_timeout = min(600, int(session_timeout or 0) * 150 // 100)
            actions.append(f"[MITIGATION] Timeout errors: increased timeout to {new_timeout}s")
        elif error_type == "network":
            # Exponential backoff: cooldown = base * 2^count, capped at 30 min.
            # This handles transient API outages without shutting down the daemon.
            base = max(_ORIGINAL_COOLDOWN, 15)
            backoff = min(1800, base * (2 ** min(count, 10)))
            new_cooldown = max(30, backoff)
            new_mode = "adaptive"
            actions.append(f"[MITIGATION] Network errors: exponential backoff → {new_cooldown}s (count={count})")
        elif error_type == "schema":
            actions.append("[MITIGATION] Schema errors: monitoring (no parameter changes yet)")
        elif error_type == "unknown":
            new_cooldown = min(120, max(_ORIGINAL_COOLDOWN, cooldown * 2))
            if new_cooldown < 15:
                new_cooldown = 15
            new_mode = "fixed"
            actions.append(f"[MITIGATION] Unknown errors: elevated cooldown to {new_cooldown}s")
        new_level = 1

    if new_level >= 2 and level_before < 2:
        if error_type == "timeout":
            new_cooldown = min(120, max(_ORIGINAL_COOLDOWN, cooldown * 2))
            new_mode = "fixed"
            actions.append(f"[MITIGATION] Timeout errors (escalated): cooldown → {new_cooldown}s")
        elif error_type == "network":
            new_library = False
            new_workers = 1
            actions.append("[MITIGATION] Network errors (escalated): forced subprocess mode, reduced to 1 worker")
        elif error_type == "unknown":
            new_library = False
            new_workers = 1
            actions.append("[MITIGATION] Unknown errors (escalated): forced subprocess mode, reduced to 1 worker")
        new_level = 2

    if new_level >= 3 and level_before < 3:
        reason_map = {
            "timeout": "persistent-timeout-failure",
            "network": "persistent-network-failure",
            "schema": "persistent-schema-failure",
            "unknown": "persistent-unknown-failure",
        }
        stop_reason = reason_map.get(error_type, "persistent-failure")
        actions.append(f"[MITIGATION] STOP: {stop_reason} after {count} {error_type} errors")
        new_level = 3

    mitigations["mitigation_level"] = new_level
    mitigations["timeout_increased"] = new_timeout > _ORIGINAL_SESSION_TIMEOUT
    mitigations["cooldown_elevated"] = new_cooldown > _ORIGINAL_COOLDOWN
    mitigations["force_subprocess"] = not new_library
    mitigations["reduced_workers"] = new_workers < _ORIGINAL_WORKERS
    mitigations["last_applied"] = datetime.now(timezone.utc).isoformat()

    rolling = mitigations.get("actions", [])
    rolling.extend(actions)
    mitigations["actions"] = rolling[-20:]

    return (
        new_timeout,
        new_cooldown,
        new_mode,
        new_library,
        new_workers,
        actions,
    )
