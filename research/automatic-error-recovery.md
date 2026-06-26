# Automatic Error Recovery — Research & Design

## 1. Analysis of Current Error Handling (lines 3853–3890)

### Current state

After every iteration, the end of `run_loop()` runs two sequential blocks:

#### Cooldown (lines 3852–3872)
- If `--cooldown N` is set, waits N seconds.
- If `--cooldown-mode adaptive`, calls `calc_adaptive_cooldown(avg_duration)` which interpolates between 2s and 60s based on iteration duration (shorter iterations → longer cooldown).
- Pure `time.sleep()` with interrupt check.

#### Backoff (lines 3874–3888)
- `consecutive_errors = 0 if not combined_error else consecutive_errors + 1`
- If there's an error AND `retry_delay > 0`: `delay = retry_delay * min(consecutive_errors, 5)`
- Pure sleep — no behavioral mitigation (no timeout changes, no mode switches).

### What's missing
1. **No per-error-type tracking** — `consecutive_errors` is a single counter for all errors.
2. **No behavioral mitigation** — the daemon never adjusts `session_timeout`, `cooldown`, workers, or `use_library` based on error patterns.
3. **No recovery on success** — after a successful iteration, `consecutive_errors` resets to 0 but any mitigation that was ramped up stays permanently. There's no ramp-down mechanism.
4. **No error storm protection** — rapid-fire recurring errors of the same type get the same linear backoff as mixed errors.

---

## 2. Design: `_adapt_to_error()` Function

### Location
Insert as a new module-level function before `run_loop()` (at approximately line 2835), or as a nested closure inside `run_loop()` since it needs to mutate loop-local variables (`session_timeout`, `cooldown`, etc.).

### Signature
```python
def _adapt_to_error(
    error_type: str | None,        # 'timeout' | 'network' | 'schema' | 'unknown' | None
    mitigations: dict,             # Mutable dict of active mitigations
    stats: dict,                   # Ledger stats with per-type counters
    session_timeout: int,
    cooldown: int,
    cooldown_mode: str,
    use_library: bool,
    workers: int,
) -> dict:
    """
    Adjust runtime parameters based on error type and history.

    Returns updated (session_timeout, cooldown, cooldown_mode, use_library, workers)
    plus a list of human-readable actions taken.
    """
```

### Design rationale
- **Immutability for caller params**: the function returns a new tuple rather than mutating arguments in-place, making idempotent logging easy.
- **Shared `state["mitigations"]` dict**: persists across iterations so mitigations accumulate and can be unwound.
- **Error-type counters live in `state["error_type_counts"]`**: persists in the ledger so recovery survives daemon restarts.

---

## 3. Per-Error-Type Counters in the Ledger

### New state keys

```python
state["error_type_counts"] = {
    "timeout": 0,
    "network": 0,
    "schema": 0,
    "unknown": 0,
}

state["mitigations"] = {
    "timeout_increased": False,       # Flag: session_timeout was raised
    "cooldown_elevated": False,       # Flag: cooldown was force-raised
    "force_subprocess": False,        # Flag: use_library forced to False
    "reduced_workers": False,         # Flag: workers reduced to 1
    "mitigation_level": 0,            # 0=none, 1=mild, 2=moderate, 3=aggressive
    "last_applied": "",               # ISO timestamp of last mitigation change
    "actions": [],                    # Rolling log of recent mitigations (last 20)
}
```

### Where counters are incremented
In `run_loop()` after `combined_error` is computed (line 3503) and before the record is written. The error type is extracted from `all_results`:

```python
if combined_error:
    # Collect error types from all workers
    error_types = []
    for r in all_results:
        et = r.get("error_type")
        if et:
            error_types.append(et)
    # If multiple types, use the most severe (timeout > network > schema > unknown)
    primary_error_type = _pick_primary_error(error_types) if error_types else "unknown"
    state.setdefault("error_type_counts", {})
    state["error_type_counts"][primary_error_type] = (
        state["error_type_counts"].get(primary_error_type, 0) + 1
    )
```

### `_pick_primary_error()` helper
```python
_ERROR_SEVERITY = {"timeout": 4, "network": 3, "schema": 2, "unknown": 1}
def _pick_primary_error(types: list[str]) -> str:
    """Return the most severe error type from a list."""
    return max(types, key=lambda t: _ERROR_SEVERITY.get(t, 0))
```

---

## 4. Recovery Strategies Per Error Type

### 4a. Timeout Errors
**Root cause**: Spawned Hermes session exceeded `--session-timeout`.

| Threshold | Mitigation | Rationale |
|-----------|-----------|-----------|
| 3 timeouts | Increase `session_timeout` by 50% (capped at 600s) | The task genuinely needs more time |
| 5 timeouts | Also increase cooldown by 100% (capped at 120s) | Rate-limits or resource contention |
| 8+ timeouts | Force subprocess mode if in library mode | Library mode has a different timeout mechanism; subprocess may be more reliable |

**Recovery**: On first successful iteration after any timeout mitigation:
- Decrease timeout by 25% (floor to original value)
- Decrease cooldown by 50% (floor to original value)
- Restore library mode if it was forced off

### 4b. Network Errors
**Root cause**: Hermes binary not found, DNS failure, connection refused, connection reset.

| Threshold | Mitigation | Rationale |
|-----------|-----------|-----------|
| 2 network errors | Increase cooldown by 300% (cap 300s) | Aggressive backoff for transient net issues |
| 4 network errors | Force subprocess mode (if library), reduce workers to 1 | Isolate networking to single process |
| 6+ network errors | Emit critical log + set `state["status"] = "stopped: persistent-network-failure"` | Infrastructure problem, not recoverable |

**Recovery**: On 2 consecutive successes:
- Halve the elevated cooldown each success
- Restore workers on next success after cooldown < 60s
- Restore library mode after 3 consecutive successes

### 4c. Schema Errors
**Root cause**: Spawned Hermes returned JSON that doesn't match `--output-schema`.

| Threshold | Mitigation | Rationale |
|-----------|-----------|-----------|
| 3 schema errors | Drop `--output-schema` for next iteration (log a warning) | Schema might be wrong; let it run free to diagnose |
| 5+ schema errors | Set `state["status"] = "stopped: persistent-schema-failure"` | Pointless to continue; schema needs fixing |

**Recovery**: If user re-runs with same schema (new daemon starts), counters are read from ledger and we may still stop immediately. This is intentional — persistent schema failures should not retry automatically.

### 4d. Unknown Errors
**Root cause**: Hermes exit code != 0, unhandled exceptions, unexpected failures.

| Threshold | Mitigation | Rationale |
|-----------|-----------|-----------|
| 3 unknown errors | Increase cooldown by 100% | Generic backpressure |
| 5 unknown errors | Force subprocess mode (if library), reduce workers to 1 | Simplify to debug |
| 7+ unknown errors | Set `state["status"] = "stopped: persistent-unknown-failure"` | Unrecoverable |

**Recovery**: Same as network recovery — taper mitigations on consecutive successes.

---

## 5. Gradual Mitigation Ramp-Up and Ramp-Down

### Ramp-Up Model

Each mitigation has a **threshold count** per error type. When the per-type counter reaches a threshold, the corresponding mitigation is applied. This is a **step function**, not linear — thresholds define clear escalation stages.

```
Level 0 (none):  0 errors              — no mitigation
Level 1 (mild):  2–3 errors            — timeout +50%, cooldown +100%
Level 2 (mod):   4–5 errors            — force subprocess, reduce workers
Level 3 (stop):  6+ errors (varies)    — stop daemon with status message
```

### Ramp-Down Model

Applied in `_adapt_to_error()` when `error_type is None` (successful iteration) AND `mitigation_level > 0`:

```
Step 1: On first success after mitigation → reduce timeout by 25%, halve cooldown, log "de-escalating"
Step 2: On second consecutive success    → restore original workers, restore library mode
Step 3: On third consecutive success     → reset all mitigations, log "fully recovered"
```

**Key decision**: Ramp-down only proceeds on **consecutive** successes to avoid oscillation (mitigate → succeed → un-mitigate → fail → mitigate → succeed → ...).

### Mitigation State Machine

```
                   ┌─────────────┐
                   │   NONE      │
                   │ (level 0)   │
                   └──────┬──────┘
                          │ error counter ≥ threshold[level1]
                          ▼
                   ┌─────────────┐
          ┌────────│  MILD       │◄────────┐
          │        │ (level 1)   │         │
          │        └──────┬──────┘         │
          │               │ error ≥ threshold[level2]
          │               ▼                │
          │        ┌─────────────┐         │
          │        │  MODERATE   │─────────┤ 1 consecutive success
          │        │ (level 2)   │         │
          │        └──────┬──────┘         │
          │               │ error ≥ threshold[level3]
          │               ▼                │
          │        ┌─────────────┐         │
          │        │  STOP       │         │
          │        │ (level 3)   │         │
          │        └─────────────┘         │
          │                                │
          └────────────────────────────────┘
                3 consecutive successes
```

---

## 6. Edge Cases

### 6a. Error Storms
**Definition**: 5+ errors of the same type within 10 iterations with no successful iterations interspersed.

**Handling**:
1. The per-type counter naturally accelerates through thresholds.
2. At level 2 (moderate) mitigations kick in: timeout +50%, cooldown +300%, force subprocess, reduce workers.
3. If errors continue after mitigations are in place for 3 iterations → escalate to stop.
4. **Special protection**: If `len(iterations) >= 5` and the last 5 iterations all have the same primary error type, and `mitigation_level >= 2`, emit `[ERROR-STORM]` log and fast-track to stop after 2 more errors instead of waiting for the normal threshold.

### 6b. Rapid Recovery
**Definition**: A successful iteration immediately after mitigations were applied.

**Handling**:
- Ramp-down begins immediately on the first success.
- However, after a single success, if the next iteration fails, mitigation jumps back to the previous level instantly (no re-accumulation needed).
- This prevents the "yo-yo" problem where the system oscillates between mitigated and unmitigated states.

**Implementation**: Store `mitigation_level` separately from `consecutive_successes`:
```python
if error_type is None:
    consecutive_successes += 1
    if mitigations["mitigation_level"] > 0:
        if consecutive_successes == 1:
            # Partial unwind
            _apply_ramp_down(mitigations, level="partial")
        elif consecutive_successes >= 3:
            # Full unwind
            _apply_ramp_down(mitigations, level="full")
else:
    consecutive_successes = 0
    # If mitigations were active and we got a new error, re-apply immediately
    if mitigations["mitigation_level"] > 0:
        # Stay at current level; don't re-escalate unless counter crosses another threshold
        pass
```

### 6c. Persistent Failures Across Daemon Restarts
**Definition**: Daemon is killed and restarted; error counters persist in the ledger.

**Handling**:
- `error_type_counts` is read from ledger on start (already done via `load_or_create_ledger()`).
- If the counts are already at a stop-threshold level, the first iteration will immediately apply level-2 mitigations and the next error will trigger a stop.
- This prevents the daemon from burning through expensive API calls only to fail again.

### 6d. Multi-Worker Error Mixing
**Definition**: With `--workers N`, different workers may produce different error types.

**Handling**:
- `combined_error` is the `; `-joined string of all worker errors.
- The primary error type is the **most severe** across all workers (timeout > network > schema > unknown).
- Mitigations affect the **next iteration** globally — all workers get the same adjusted parameters.
- Worker-level error types are available in `worker_results` for post-hoc analysis but don't drive individual-worker mitigations (that would require per-worker parameterization, which is out of scope).

### 6e. Schema Errors Mixed with Other Errors
If a worker has both a schema error and a timeout error, the timeout takes priority as the primary error type. Schema-specific mitigations (dropping output-schema) are only applied when schema is the **sole** error type.

---

## 7. Detailed Implementation Plan

### 7.1 State Schema Changes

**Add to `load_or_create_ledger()`** (around line 3902):
```python
# Ensure error type counters exist
if "error_type_counts" not in existing:
    existing["error_type_counts"] = {"timeout": 0, "network": 0, "schema": 0, "unknown": 0}
if "mitigations" not in existing:
    existing["mitigations"] = {
        "timeout_increased": False,
        "cooldown_elevated": False,
        "force_subprocess": False,
        "reduced_workers": False,
        "mitigation_level": 0,
        "last_applied": "",
        "actions": [],
    }
```

### 7.2 `_adapt_to_error()` — Full Implementation

```python
# Thresholds per error type (error count → mitigation level)
_ERROR_THRESHOLDS = {
    "timeout": {"mild": 3, "moderate": 5, "stop": 8},
    "network": {"mild": 2, "moderate": 4, "stop": 6},
    "schema": {"mild": 3, "moderate": None, "stop": 5},   # No moderate for schema
    "unknown": {"mild": 3, "moderate": 5, "stop": 7},
}

# Original values snapshot (set in run_loop)
_ORIGINAL_SESSION_TIMEOUT: int = 0
_ORIGINAL_COOLDOWN: int = 0
_ORIGINAL_USE_LIBRARY: bool = False
_ORIGINAL_WORKERS: int = 1


def _adapt_to_error(
    error_type: str | None,
    mitigations: dict,
    consecutive_successes: int,
    error_type_counts: dict,
    # Current runtime params (will be mutated)
    session_timeout: int,
    cooldown: int,
    cooldown_mode: str,
    use_library: bool,
    workers: int,
    # Notification callback
    log_fn: callable = _log,
) -> tuple:
    """
    Adapt runtime parameters based on error type and history.

    Returns (session_timeout, cooldown, cooldown_mode, use_library, workers, actions_taken)
    where actions_taken is a list of human-readable strings.
    """
    global _ORIGINAL_SESSION_TIMEOUT, _ORIGINAL_COOLDOWN
    global _ORIGINAL_USE_LIBRARY, _ORIGINAL_WORKERS

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
            # Ramp down logic
            if consecutive_successes == 1:
                new_timeout = max(
                    _ORIGINAL_SESSION_TIMEOUT,
                    int(session_timeout * 0.75),  # -25%
                )
                if cooldown_mode != "adaptive" and cooldown > _ORIGINAL_COOLDOWN:
                    new_cooldown = max(
                        _ORIGINAL_COOLDOWN,
                        cooldown // 2,
                    )
                actions.append(
                    f"[RECOVERY] Partial unwind (1st success): "
                    f"timeout={new_timeout}s, cooldown={new_cooldown}s"
                )
                new_level = max(0, level_before - 1)

            elif consecutive_successes >= 3:
                # Full recovery — restore all originals
                new_timeout = _ORIGINAL_SESSION_TIMEOUT
                new_cooldown = _ORIGINAL_COOLDOWN
                new_mode = "fixed" if _ORIGINAL_COOLDOWN > 0 else cooldown_mode
                new_library = _ORIGINAL_USE_LIBRARY
                new_workers = _ORIGINAL_WORKERS
                actions.append(
                    "[RECOVERY] Full recovery: all mitigations reset to original values"
                )
                new_level = 0

            # Persist changes
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

    # Determine target level from counter
    if count >= thresholds.get("stop", 999):
        target_level = 3
    elif count >= thresholds.get("moderate", 999):
        target_level = 2
    elif count >= thresholds.get("mild", 999):
        target_level = 1
    else:
        target_level = 0

    # Don't de-escalate on error — only go up
    new_level = max(level_before, target_level)

    if new_level >= 1 and level_before < 1:
        # Level 1: mild mitigation
        if error_type == "timeout":
            new_timeout = min(600, int(session_timeout * 1.5))
            actions.append(f"[MITIGATION] Timeout errors: increased timeout to {new_timeout}s")
        elif error_type == "network":
            new_cooldown = min(300, max(cooldown, cooldown * 4))  # +300%
            new_mode = "fixed"
            actions.append(f"[MITIGATION] Network errors: elevated cooldown to {new_cooldown}s")
        elif error_type == "schema":
            # Mild: no timeout/cooldown change — schema is content, not infra
            actions.append("[MITIGATION] Schema errors: monitoring (no parameter changes yet)")
        elif error_type == "unknown":
            new_cooldown = min(120, max(cooldown, cooldown * 2))  # +100%
            new_mode = "fixed"
            actions.append(f"[MITIGATION] Unknown errors: elevated cooldown to {new_cooldown}s")

        new_level = 1

    if new_level >= 2 and level_before < 2:
        # Level 2: moderate mitigation
        if error_type == "timeout":
            new_cooldown = min(120, max(cooldown, cooldown * 2))
            new_mode = "fixed"
            actions.append(f"[MITIGATION] Timeout errors (escalated): cooldown → {new_cooldown}s")
        elif error_type == "network":
            new_library = False
            new_workers = 1
            actions.append(
                "[MITIGATION] Network errors (escalated): forced subprocess mode, reduced to 1 worker"
            )
        elif error_type == "unknown":
            new_library = False
            new_workers = 1
            actions.append(
                "[MITIGATION] Unknown errors (escalated): forced subprocess mode, reduced to 1 worker"
            )

        new_level = 2

    if new_level >= 3 and level_before < 3:
        # Level 3: stop
        reason_map = {
            "timeout": "persistent-timeout-failure",
            "network": "persistent-network-failure",
            "schema": "persistent-schema-failure",
            "unknown": "persistent-unknown-failure",
        }
        stop_reason = reason_map.get(error_type, "persistent-failure")
        actions.append(f"[MITIGATION] STOP: {stop_reason} after {count} {error_type} errors")
        new_level = 3

    # Persist changes
    mitigations["mitigation_level"] = new_level
    mitigations["timeout_increased"] = new_timeout > _ORIGINAL_SESSION_TIMEOUT
    mitigations["cooldown_elevated"] = new_cooldown > _ORIGINAL_COOLDOWN
    mitigations["force_subprocess"] = not new_library
    mitigations["reduced_workers"] = new_workers < _ORIGINAL_WORKERS
    mitigations["last_applied"] = datetime.now(timezone.utc).isoformat()

    # Keep rolling log (last 20)
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
```

### 7.3 Integration Point in `run_loop()`

Replace lines 3874–3888 (the current Backoff block) with:

```python
        # --- Automatic Error Recovery ---
        # Classify error type(s) from all_results, update per-type counters,
        # and adapt runtime parameters for the next iteration.

        # Determine primary error type from worker results
        primary_error_type = None
        if combined_error:
            error_types_seen = []
            for r in all_results:
                et = r.get("error_type")
                if et:
                    error_types_seen.append(et)
            if error_types_seen:
                primary_error_type = _pick_primary_error(error_types_seen)
            else:
                # Fallback: classify the combined error string
                primary_error_type = classify_error(combined_error) or "unknown"

            # Update per-type counters
            state.setdefault("error_type_counts", {})
            state["error_type_counts"][primary_error_type] = (
                state["error_type_counts"].get(primary_error_type, 0) + 1
            )
            consecutive_successes = 0

            # Log error type diagnosis
            _log(
                f"[ERROR-TYPE] {primary_error_type} "
                f"(total: {state['error_type_counts'][primary_error_type]})"
            )
        else:
            consecutive_successes = state.get("consecutive_successes", 0) + 1

        # Run adaptation
        state.setdefault("mitigations", {
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "mitigation_level": 0,
            "last_applied": "",
            "actions": [],
        })

        (
            session_timeout,
            cooldown,
            cooldown_mode,
            use_library,
            workers,
            adapt_actions,
        ) = _adapt_to_error(
            error_type=primary_error_type,
            mitigations=state["mitigations"],
            consecutive_successes=consecutive_successes,
            error_type_counts=state["error_type_counts"],
            session_timeout=session_timeout,
            cooldown=cooldown,
            cooldown_mode=cooldown_mode,
            use_library=use_library,
            workers=workers,
        )

        state["consecutive_successes"] = consecutive_successes

        for action in adapt_actions:
            _log(f"[AUTO-RECOVERY] {action}")

        # --- Legado: Basic backoff (overlaid with the above) ---
        # Only applied if no automatic mitigation took over
        if combined_error and retry_delay > 0 and consecutive_errors > 0:
            delay = retry_delay * min(consecutive_errors, 5)
            if not adapt_actions:
                _log(f"[BACKOFF] Waiting {delay}s...")
            try:
                time.sleep(delay)
            except KeyboardInterrupt:
                _log("\n[STOP] KeyboardInterrupt")
                state["status"] = "stopped: ctrl-c"
                write_ledger(state)
                write_status_file(status_file, state, iteration_count, "stopped: ctrl-c")
                return

        # Stop daemon if mitigation reached level 3 (persistent failure)
        if state["mitigations"].get("mitigation_level", 0) >= 3:
            _log("[AUTO-RECOVERY] Persistent failure detected — stopping daemon")
            state["status"] = (
                f"stopped: {primary_error_type}-failure-"
                f"{state['error_type_counts'].get(primary_error_type, 0)}"
            )
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, state["status"])
            return
```

### 7.4 Additional: Store `error_type` in `worker_results`

In the record-building block (~line 3647–3663), add `error_type` to each worker result:

```python
"worker_results": (
    [
        {
            "worker": r.get("worker_id", 0),
            "summary": r.get("summary", "")[:200],
            "error": r.get("error"),
            "error_type": r.get("error_type"),        # <-- ADD
            "duration_seconds": r.get("duration_seconds", 0),
            ...
        }
        for r in all_results
    ]
    if workers > 1
    else None
),
```

### 7.5 Initialize Originals at Top of `run_loop()`

Near line 3094 (where `consecutive_errors` is initialized):

```python
    # Snapshot original runtime parameters for error recovery ramp-down
    global _ORIGINAL_SESSION_TIMEOUT, _ORIGINAL_COOLDOWN
    global _ORIGINAL_USE_LIBRARY, _ORIGINAL_WORKERS
    _ORIGINAL_SESSION_TIMEOUT = session_timeout
    _ORIGINAL_COOLDOWN = cooldown
    _ORIGINAL_USE_LIBRARY = use_library
    _ORIGINAL_WORKERS = workers
```

### 7.6 Test Scenarios

| Scenario | Input | Expected Behavior |
|----------|-------|-------------------|
| 3 timeouts → success | 3 consecutive timeout errors, then 1 success | Timeout +50%, then on success: -25% timeout, level drops to 0 |
| 2 network errors | 2 consecutive network errors | Cooldown +300%, force subprocess, level=2 |
| Error storm: 5 timeouts in 6 iters | Rapid-fire timeouts | Timeout +50% at 3, cooldown x2 at 5, fast-track to stop |
| Schema errors with recovery | 3 schema errors → fix → 2 successes | No infra changes for mild schema; reset to 0 on success |
| Mixed error types in multi-worker | Workers 1=timeout, 2=schema | Primary = timeout (higher severity); timeout mitigations applied |
| Daemon restart with ledger | Existing error_type_counts showing 6 network | First iteration applies level-2 mitigations immediately; next network error stops daemon |

---

## 8. Migration Path

1. **Add state schema defaults** to `load_or_create_ledger()` (backward-compatible — existing ledgers get the new keys).
2. **Add `_adapt_to_error()` function** at module level.
3. **Integrate into `run_loop()`** replacing the old Backoff block.
4. **Add `error_type` to `worker_results`** for multi-worker audit.
5. **Update `_recalc_stats()`** to include per-type counts in the stats output.
6. **Write tests** — ideally a mock `_adapt_to_error` test harness that simulates sequences of error/success and verifies parameter mutation.

---

## 9. Summary

The Automatic Error Recovery system adds:
- **Per-error-type counters** in the ledger (`error_type_counts`)
- **Mitigation state** in the ledger (`mitigations`) — survives restarts
- **`_adapt_to_error()` function** — the core policy engine that maps error type + count → parameter changes
- **Step-function ramp-up** with 3 levels (mild → moderate → stop)
- **Graceful ramp-down** over 3 consecutive successes
- **Edge case handling** for error storms, rapid recovery, and persistent failures
- **Backward-compatible** — existing ledgers get defaults, old backoff still runs as fallback
