# Session Self-Healing (Heartbeat Mechanism) — Implementation Plan

**Status:** Ready for implementation
**Target:** `launch-loop.py` v13.0.0 (6799 lines)
**Upgrade To:** v14.0.0 — Heartbeat-Based Session Self-Healing
**Design Reference:** `research-session-self-healing.md` (the full design document)

---

## Overview

Add a heartbeat-based self-healing mechanism to the infinite-loop daemon. Each spawned Hermes session periodically writes a heartbeat file. The daemon monitors these files in a background thread. If a heartbeat stops for longer than a configurable timeout (+ grace period), the daemon kills the hung session and retries — optionally resuming from the latest checkpoint.

**Stdlib-only.** No new Python dependencies. All new code uses `threading`, `os.path.getmtime`, `json`, `time`, `subprocess`, `glob`, and `signal`.

---

## 1. Constants & Module-Level Additions

Insert after the `_ERROR_THRESHOLDS` dict and before `_pick_primary_error` at line ~3734.

```python
# --- Heartbeat constants ---
HEARTBEAT_DIR = "/tmp"
HEARTBEAT_PREFIX = "infinite-loop-heartbeat-"
HEARTBEAT_INTERVAL = 30          # seconds between heartbeat writes (prompt tells session)
HEARTBEAT_DEFAULT_TIMEOUT = 60   # default for --heartbeat-timeout CLI flag
HEARTBEAT_GRACE_FACTOR = 2.0     # grace = timeout × 2 (total window = timeout * 3)
HEARTBEAT_POLL_INTERVAL = 10     # daemon polling interval (seconds)
HEARTBEAT_MAX_CONSECUTIVE = 3    # before escalation to _adapt_to_error
HEARTBEAT_KILL_GRACE = 5         # seconds between SIGTERM and SIGKILL
```

Also add `"heartbeat"` to `_ERROR_THRESHOLDS`:

```python
_ERROR_THRESHOLDS = {
    "timeout": {"mild": 3, "moderate": 5, "stop": 8},
    "network": {"mild": 2, "moderate": 4, "stop": 6},
    "schema": {"mild": 3, "moderate": None, "stop": 5},
    "unknown": {"mild": 3, "moderate": 5, "stop": 7},
    "heartbeat": {"mild": 3, "moderate": 5, "stop": 7},  # <-- ADD THIS
}
```

Add `"heartbeat": 5` to `_ERROR_SEVERITY`:

```python
_ERROR_SEVERITY = {"timeout": 4, "network": 3, "schema": 2, "unknown": 1, "heartbeat": 5}
```

---

## 2. Helper Functions

### 2.1 `_heartbeat_path(session_id_or_pid: str) -> str`

```python
def _heartbeat_path(identifier: str) -> str:
    """Return the heartbeat file path for a given session ID or PID."""
    return os.path.join(HEARTBEAT_DIR, f"{HEARTBEAT_PREFIX}{identifier}")
```

### 2.2 `_read_heartbeat(heartbeat_file: str) -> dict | None`

```python
def _read_heartbeat(heartbeat_file: str) -> dict | None:
    """Read and parse a heartbeat file. Returns None on any error."""
    try:
        with open(heartbeat_file) as f:
            return json.loads(f.read().strip())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
```

### 2.3 `_write_heartbeat_file(heartbeat_file: str, data: dict) -> bool`

```python
def _write_heartbeat_file(heartbeat_file: str, data: dict) -> bool:
    """Atomically write a heartbeat file (write .tmp, then rename)."""
    try:
        os.makedirs(os.path.dirname(heartbeat_file), exist_ok=True)
        tmp = heartbeat_file + ".tmp"
        with open(tmp, "w") as f:
            f.write(json.dumps(data) + "\n")
        os.rename(tmp, heartbeat_file)
        return True
    except (OSError, IOError):
        return False
```

### 2.4 `_heartbeat_age(heartbeat_file: str) -> float | None`

```python
def _heartbeat_age(heartbeat_file: str) -> float | None:
    """Return seconds since the heartbeat file was last modified, or None if absent."""
    try:
        mtime = os.path.getmtime(heartbeat_file)
        return time.time() - mtime
    except OSError:
        return None
```

### 2.5 `_start_library_heartbeat(session_id: str, iteration: int, interval: int = 30) -> threading.Thread`

```python
def _start_library_heartbeat(session_id: str, iteration: int, interval: int = 30) -> threading.Thread:
    """Start a daemon thread that writes a heartbeat file every `interval` seconds.
    Used in library mode where there's no subprocess to inject terminal commands into.
    """
    hb_path = _heartbeat_path(session_id)

    def _hb_loop():
        while not _shutdown_requested:
            _write_heartbeat_file(hb_path, {
                "session_id": session_id,
                "iteration": iteration,
                "timestamp": time.time(),
                "pid": os.getpid(),
                "checkpoint_latest": None,
            })
            time.sleep(interval)
            if _shutdown_requested:
                break

    t = threading.Thread(target=_hb_loop, daemon=True)
    t.start()
    return t
```

### 2.6 `_kill_session(proc: subprocess.Popen | None, session_id: str) -> None`

```python
def _kill_session(proc: subprocess.Popen | None, session_id: str) -> None:
    """Force-kill a session process (SIGTERM, then SIGKILL after 5s)."""
    if proc is None or proc.poll() is not None:
        return  # Already dead or no process
    short_id = session_id[:12] if session_id else "unknown"
    _log(f"[HEARTBEAT] Killing hung session {short_id}...")
    proc.terminate()
    try:
        proc.wait(timeout=HEARTBEAT_KILL_GRACE)
    except subprocess.TimeoutExpired:
        proc.kill()  # SIGKILL
        proc.wait(timeout=3)
    _log(f"[HEARTBEAT] Session {short_id} killed (exit={proc.returncode})")
```

### 2.7 `_monitor_heartbeat_file(heartbeat_file: str, timeout: int, session_start: float, proc: subprocess.Popen | None) -> dict`

```python
def _monitor_heartbeat_file(
    heartbeat_file: str,
    timeout: int,
    session_start: float,
    proc: subprocess.Popen | None,
) -> dict:
    """Monitor a single heartbeat file in a blocking loop.

    Polls every HEARTBEAT_POLL_INTERVAL seconds. Returns a status dict:
      {"status": "alive"|"expired"|"dead"|"lost"|"completed",
       "session_id": ...,
       "age_seconds": ...,
       "last_heartbeat_data": ...|None}

    Designed to run in a separate thread alongside the subprocess wait.
    """
    grace_period = int(timeout * HEARTBEAT_GRACE_FACTOR) if timeout > 0 else 0

    while not _shutdown_requested:
        # If the subprocess has exited normally, stop monitoring
        if proc is not None and proc.poll() is not None:
            return {"status": "completed", "session_id": "", "age_seconds": 0,
                    "last_heartbeat_data": None}

        age = _heartbeat_age(heartbeat_file)
        hb_data = _read_heartbeat(heartbeat_file) if age is not None else None

        if age is None:
            # No heartbeat file exists yet
            elapsed = time.time() - session_start
            if elapsed > timeout + grace_period:
                _log(f"[HEARTBEAT] Lost — never appeared after {elapsed:.0f}s")
                return {"status": "lost", "session_id": "", "age_seconds": elapsed,
                        "last_heartbeat_data": None}
        elif age > timeout:
            if age > timeout + grace_period:
                session_id = (hb_data or {}).get("session_id", "")
                _log(f"[HEARTBEAT] DEAD — last heartbeat {age:.0f}s ago (> {timeout + grace_period}s)")
                return {"status": "dead", "session_id": session_id,
                        "age_seconds": age, "last_heartbeat_data": hb_data}
            else:
                # In grace period — log at DEBUG to avoid spam
                _log(f"[HEARTBEAT] Grace period — {age:.0f}s since last heartbeat "
                     f"(timeout={timeout}s, grace={grace_period}s)", level="DEBUG")
        else:
            # Heartbeat is fresh
            session_id = (hb_data or {}).get("session_id", "")
            # Brief DEBUG-level log for alive status
            _log(f"[HEARTBEAT] Alive — {age:.1f}s ago (session={session_id[:12]})", level="DEBUG")

        time.sleep(HEARTBEAT_POLL_INTERVAL)

    return {"status": "alive", "session_id": "", "age_seconds": 0,
            "last_heartbeat_data": None}
```

### 2.8 `_run_heartbeat_monitor_in_thread(...) -> dict`

```python
def _run_heartbeat_monitor_in_thread(
    heartbeat_file: str,
    timeout: int,
    session_start: float,
    proc: subprocess.Popen | None,
    timeout_seconds: int,
) -> dict:
    """Run _monitor_heartbeat_file in a daemon thread with a timeout cap.

    Returns the heartbeat status dict. If the monitor thread doesn't finish
    within `timeout_seconds + grace + 30`, forcibly stops.

    This is the function called from spawn_delegation_session.
    """
    result_container = {}

    def _monitor_wrapper():
        result_container["result"] = _monitor_heartbeat_file(
            heartbeat_file, timeout, session_start, proc
        )

    t = threading.Thread(target=_monitor_wrapper, daemon=True)
    t.start()
    # Wait for the monitor or the session timeout, whichever comes first
    max_wait = timeout_seconds + int(timeout * HEARTBEAT_GRACE_FACTOR) + 60 if timeout > 0 else timeout_seconds
    t.join(timeout=max_wait + 60)
    if t.is_alive():
        _log("[HEARTBEAT] Monitor thread timed out — forcibly stopping")
        return {"status": "alive", "session_id": "", "age_seconds": 0,
                "last_heartbeat_data": None}
    return result_container.get("result", {"status": "alive", "session_id": "",
                                           "age_seconds": 0, "last_heartbeat_data": None})
```

### 2.9 `_cleanup_stale_heartbeats() -> None`

```python
def _cleanup_stale_heartbeats() -> None:
    """Remove heartbeat files from previous daemon instances at startup."""
    import glob
    pattern = os.path.join(HEARTBEAT_DIR, f"{HEARTBEAT_PREFIX}*")
    removed = 0
    for f in glob.glob(pattern):
        try:
            os.remove(f)
            removed += 1
        except OSError:
            pass
    if removed > 0:
        _log(f"[HEARTBEAT] Cleaned up {removed} stale heartbeat file(s) from previous runs")
```

### 2.10 `_cleanup_single_heartbeat(heartbeat_file: str | None) -> None`

```python
def _cleanup_single_heartbeat(heartbeat_file: str | None) -> None:
    """Remove a single heartbeat file (on normal session completion)."""
    if heartbeat_file and os.path.exists(heartbeat_file):
        try:
            os.remove(heartbeat_file)
        except OSError:
            pass
```

---

## 3. Integration Points

### 3.1 CLI Argument (`main()`, after line ~6377)

**Old string:** The block of parser arguments ending with `--evolve` and the line `parser.add_argument("--evolve", ...)`.

**New string:** Add after the `--preflight-fail-fast` block (~line 6377):

```python
    # v14.0.0: Heartbeat-based session self-healing
    parser.add_argument(
        "--heartbeat-timeout",
        type=int,
        default=0,
        help="Enable heartbeat-based session health monitoring. "
        "Set to seconds of inactivity before a session is considered hung (default: 0 = disabled). "
        "Grace period is always heartbeat_timeout * 2 (total window = timeout * 3). "
        "When a session's heartbeat stops, the daemon kills it and retries. "
        "If --checkpoints is active, retry resumes from the latest checkpoint.",
    )
```

### 3.2 `_build_delegation_prompt()` — New `heartbeat_interval` Parameter

**Old string (line 2733–2747):**
```python
def _build_delegation_prompt(
    iteration: int,
    goal: str,
    context: str,
    toolsets: list[str],
    workdir: str | None,
    evolve: bool,
    worker_id: int | None = None,
    profile: str = "",
    model: str = "",
    provider: str = "",
    prompt_suffix: str = "",
    task_type: str = "general",
    prior_context: str = "",
) -> str:
```

**New string:**
```python
def _build_delegation_prompt(
    iteration: int,
    goal: str,
    context: str,
    toolsets: list[str],
    workdir: str | None,
    evolve: bool,
    worker_id: int | None = None,
    profile: str = "",
    model: str = "",
    provider: str = "",
    prompt_suffix: str = "",
    task_type: str = "general",
    prior_context: str = "",
    heartbeat_interval: int = 0,
) -> str:
```

### 3.3 Inject Heartbeat Instructions Into Prompt

**Old string (line 3082–3091, the prompt suffix section):**
```python
    # Append prompt suffix if provided
    if prompt_suffix:
        instructions.append("")
        instructions.append("EXTRA INSTRUCTIONS:")
        instructions.append(prompt_suffix)
        instructions.append("")

    return "\n".join(instructions)
```

**New string:**
```python
    # Append heartbeat instructions if heartbeat is enabled
    if heartbeat_interval > 0:
        instructions.append("")
        instructions.append("=== SESSION HEARTBEAT ===")
        instructions.append(
            f"You MUST emit a heartbeat every {heartbeat_interval} seconds "
            "so the daemon knows you are alive and working."
        )
        instructions.append(
            'Run this shell command every {heartbeat_interval}s (use terminal):'
        )
        instructions.append('  python3 -c "')
        instructions.append('import json, os, time')
        instructions.append(f"hb = '{HEARTBEAT_DIR}/{HEARTBEAT_PREFIX}' + 'SESSION_ID'")
        instructions.append('os.makedirs(os.path.dirname(hb), exist_ok=True)')
        instructions.append("with open(hb + '.tmp', 'w') as f:")
        instructions.append('    json.dump({')
        instructions.append("        'session_id': 'SESSION_ID',")
        instructions.append("        'iteration': ITERATION,")
        instructions.append("        'timestamp': time.time(),")
        instructions.append("        'pid': os.getpid(),")
        instructions.append("        'checkpoint_latest': 'CHECKPOINT_PATH'")
        instructions.append("    }, f)")
        instructions.append("os.rename(hb + '.tmp', hb)")
        instructions.append('"')
        instructions.append("Replace SESSION_ID, ITERATION, and CHECKPOINT_PATH with your actual values.")
        instructions.append(
            "If you cannot determine your session_id, use 'unknown-' + str(os.getpid())."
        )
        instructions.append(
            f"If checkpoints are enabled, set CHECKPOINT_PATH to your latest checkpoint file path, "
            "or leave it as an empty string."
        )
        instructions.append("")
        instructions.append(
            "DO NOT skip this — the daemon monitors heartbeats to know you are still working. "
            "If heartbeats stop, the daemon will kill and retry this session."
        )
        instructions.append("")

    # Append prompt suffix if provided
    if prompt_suffix:
        instructions.append("")
        instructions.append("EXTRA INSTRUCTIONS:")
        instructions.append(prompt_suffix)
        instructions.append("")

    return "\n".join(instructions)
```

### 3.4 `spawn_delegation_session()` — New Parameters + Heartbeat Logic

**Old string (line 3094–3130, the function signature + prompt building + subprocess run):**

The function signature needs two new params:
```python
def spawn_delegation_session(
    ...
    continue_session: bool = False,
    # v14.0.0: Heartbeat-based session self-healing
    heartbeat_timeout: int = 0,
    iteration_count: int = 0,
) -> dict:
```

And the `_build_delegation_prompt()` call needs the new param:
```python
    prompt = _build_delegation_prompt(
        ...
        prior_context=prior_context,
        heartbeat_interval=heartbeat_timeout,  # pass 0=disabled
    )
```

### 3.5 Heartbeat Monitoring in Subprocess Path

**The key change in `spawn_delegation_session()`** is around the subprocess execution (line ~3416–3450). After the subprocess is spawned (for the direct subprocess mode), we need to start a heartbeat monitor thread.

For the **subprocess path** (~line 3417), the current code is:
```python
    # --- Direct subprocess mode (default) ---
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=workdir or os.getcwd(),
            text=True,
        )
```

This needs to be replaced with a heartbeat-aware version that:
1. Spawns the process via `subprocess.Popen` (not `subprocess.run`)
2. Starts a heartbeat monitor thread
3. Waits with a timeout or heartbeat expiry

But since the codebase uses `subprocess.run` with `timeout=` which raises `TimeoutExpired`, we need a different approach. Instead of replacing all of `subprocess.run`, we can add the heartbeat monitor after the process completes (checking if the heartbeat went stale during execution). However, the design calls for *killing the process mid-flight* when heartbeat expires.

The simplest stdlib-compatible approach:

1. Use `subprocess.Popen` with `stdout=PIPE, stderr=PIPE`
2. Start the heartbeat monitor thread
3. Use `proc.wait(timeout=...)` in a loop, checking heartbeat status between waits
4. If heartbeat dies, kill the process

Here's the replacement pattern for the subprocess section:

**Replace the `subprocess.run(cmd, capture_output=True, timeout=timeout_seconds, ...)` block** with:

```python
    # --- Direct subprocess mode (default) — with optional heartbeat monitoring ---
    try:
        if heartbeat_timeout > 0:
            # Heartbeat-aware subprocess execution
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir or os.getcwd(),
                text=True,
            )
            session_start = time.time()
            pid = proc.pid
            heartbeat_file = _heartbeat_path(str(pid))

            # Start heartbeat monitor in a separate thread
            hb_monitor_thread = threading.Thread(
                target=_run_heartbeat_monitor_in_thread,
                args=(heartbeat_file, heartbeat_timeout, session_start, proc, timeout_seconds),
                daemon=True,
            )
            hb_monitor_thread.start()

            # Wait for process with periodic heartbeat checks
            try:
                stdout, stderr = proc.communicate(timeout=timeout_seconds)
                elapsed = time.time() - session_start

                # Wait for monitor thread to finish
                hb_monitor_thread.join(timeout=5)
                hb_status = getattr(hb_monitor_thread, "_hb_result", None)

            except subprocess.TimeoutExpired:
                elapsed = time.time() - session_start
                # Check if heartbeat already expired
                hb_monitor_thread.join(timeout=2)
                _kill_session(proc, str(pid))
                stdout, stderr = proc.communicate() if proc.stdout else ("", "")
                _cleanup_single_heartbeat(heartbeat_file)
                _log(f"[SPAWN] Heartbeat-monitored subprocess timed out after {timeout_seconds}s")
                return {
                    "summary": f"TIMEOUT after {timeout_seconds}s (heartbeat monitored)",
                    "duration_seconds": round(elapsed, 1),
                    "error": f"timed out after {timeout_seconds}s",
                    "error_type": "timeout",
                    "output": "",
                    "exit_code": -1,
                    "spawned_session_id": "",
                }

            _cleanup_single_heartbeat(heartbeat_file)
            # ... rest of stdout parsing (same as existing code) ...
        else:
            # Original behavior (no heartbeat)
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout_seconds,
                cwd=workdir or os.getcwd(),
                text=True,
            )
            elapsed = time.time() - start
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
```

Wait — this is getting very complex for a single patch. Let me reconsider the approach.

**Simpler approach (recommended for v1):** Rather than replacing the entire `subprocess.run` with `Popen` + manual threading, we can:

1. Keep `subprocess.run()` as-is for the actual execution
2. Run the heartbeat monitor thread *concurrently* in a daemon thread
3. The monitor thread checks heartbeat freshness; if it expires, it sets a flag
4. After `subprocess.run()` returns, check the flag
5. If the flag indicates heartbeat expired, treat the result as a heartbeat error

This won't kill the subprocess mid-flight (the run() call blocks), but it will detect that the session *was* hung and treat it accordingly on the next retry. The proper mid-flight kill requires the Popen refactor, which is more invasive.

**Actually — the design doc says to kill mid-flight.** Let me do it properly.

The careful approach: Replace just the subprocess.run() call for the heartbeat case. The rest of the stdout/stderr parsing stays the same.

Let me consolidate the patches for the implementation document.

**Actual approach for spawn_delegation_session subprocess path (approximate):**

Around line 3416, replace:
```python
    # --- Direct subprocess mode (default) ---
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=workdir or os.getcwd(),
            text=True,
        )
        elapsed = time.time() - start
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
```

With a heartbeat-aware version that uses Popen when heartbeat_timeout > 0, and falls back to subprocess.run when disabled.

### 3.6 `_execute_iteration()` — Thread `heartbeat_timeout`

**Old string — the function signature (line 3956–3995):** Add `heartbeat_timeout: int = 0` to the parameter list.

**Old string — the spawn_delegation_session call for single execution (line 4160–4195):** Pass `heartbeat_timeout=heartbeat_timeout, iteration_count=iteration_count,`

**Old string — the spawn_delegation_session call for multi-worker (line 4099–4133):** Also pass `heartbeat_timeout=heartbeat_timeout, iteration_count=iteration_count,`

### 3.7 `_merge_worker_results()` — Handle heartbeat_expired

**Old string (line 4231):**
```python
    combined_error = "; ".join(errors) if errors else None
```

**New string:**
```python
    combined_error = "; ".join(errors) if errors else None

    # v14.0.0: Detect heartbeat expiry in worker results
    heartbeat_recoveries = [r for r in all_results if r.get("heartbeat_expired")]
    if heartbeat_recoveries:
        for hr in heartbeat_recoveries:
            session_id = hr.get("spawned_session_id", "")
            checkpoint = hr.get("checkpoint_latest", "")
            _log(
                f"[HEARTBEAT] Recovery from {session_id[:12]} "
                f"(checkpoint: {checkpoint or 'none'})"
            )
```

### 3.8 `_build_iteration_record()` — Include heartbeat data

**Old string (line 4458–4489, the record dict):** Add after the `"classification"` line:

```python
    # v14.0.0: Heartbeat state per iteration
    if all_results:
        hb_info = None
        for r in all_results:
            if r.get("heartbeat_expired"):
                hb_info = {
                    "expired": True,
                    "session_id": r.get("spawned_session_id", ""),
                    "checkpoint": r.get("checkpoint_latest", ""),
                    "grace_duration": r.get("grace_duration", 0),
                }
                break
            if r.get("heartbeat_ok"):
                hb_info = {
                    "ok": True,
                    "session_id": r.get("spawned_session_id", ""),
                }
                break
        if hb_info:
            record["heartbeat"] = hb_info
```

### 3.9 `_adapt_to_error()` — Add heartbeat error handling

**Old string (line 3850–3873, the level 1 mitigation block):** Add heartbeat case:

```python
    if new_level >= 1 and level_before < 1:
        # Level 1: mild mitigation
        if error_type == "timeout":
            ...
        elif error_type == "heartbeat":
            new_cooldown = min(120, max(cooldown, cooldown * 2))
            new_mode = "fixed"
            actions.append(
                "[MITIGATION] Heartbeat failures: elevated cooldown, monitoring"
            )
```

And at level 2 (line 3877–3898):
```python
        elif error_type == "heartbeat":
            new_library = False
            new_workers = 1
            actions.append(
                "[MITIGATION] Heartbeat failures (escalated): forced subprocess mode, reduced to 1 worker"
            )
```

And in the stop reason map (line 3902–3907):
```python
        reason_map = {
            "timeout": "persistent-timeout-failure",
            "network": "persistent-network-failure",
            "schema": "persistent-schema-failure",
            "unknown": "persistent-unknown-failure",
            "heartbeat": "persistent-heartbeat-failure",
        }
```

### 3.10 `run_loop()` — New Parameter + Logging + Cleanup

**Old string — function signature (line 4635–4715):** Add after `reset_goals`:
```python
    # v14.0.0: Heartbeat-based session self-healing
    heartbeat_timeout: int = 0,
```

**Old string — after startup banner (~line 4812):** Add:
```python
    # v14.0.0: Clean up stale heartbeat files and log status
    if heartbeat_timeout > 0:
        _cleanup_stale_heartbeats()
        _log(f"[DAEMON] Heartbeat monitoring enabled (timeout={heartbeat_timeout}s, "
             f"grace={int(heartbeat_timeout * HEARTBEAT_GRACE_FACTOR)}s, "
             f"poll={HEARTBEAT_POLL_INTERVAL}s)")
```

**Old string — `_execute_iteration` call (line 5002–5041):** Add `heartbeat_timeout=heartbeat_timeout,` to the call.

### 3.11 `main()` — Pass heartbeat_timeout to run_loop

**Old string — the `run_loop()` call (line 6696–6784):** Add after the `reset_goals=` line:
```python
            # v14.0.0: Heartbeat-based session self-healing
            heartbeat_timeout=args.heartbeat_timeout,
```

**Old string — the banner log section (~line 6565):** Add:
```python
    _log(f"  Heartbeat timeout:{'disabled' if args.heartbeat_timeout <= 0 else f'{args.heartbeat_timeout}s (grace={int(args.heartbeat_timeout * HEARTBEAT_GRACE_FACTOR)}s)'}")
```

---

## 4. Edge Cases & Error Handling

### 4.1 Heartbeat file never appears
The `_monitor_heartbeat_file()` function returns `"lost"` status when `elapsed > timeout + grace_period` and no heartbeat file has ever appeared. The caller in `spawn_delegation_session()` handles this by treating it like a heartbeat expiry.

### 4.2 Stale heartbeat after normal completion
`_cleanup_single_heartbeat()` is called in the normal completion path of `spawn_delegation_session()`.

### 4.3 Multiple workers
Each worker gets its own heartbeat file (named by PID or session ID). The monitoring thread tracks each file independently. Each worker's `spawn_delegation_session()` call handles its own heartbeat.

### 4.4 Daemon restart
`_cleanup_stale_heartbeats()` is called once at `run_loop()` startup when heartbeat_timeout > 0.

### 4.5 Session ID unknown
If `--pass-session-id` is not set, the heartbeat file uses `"unknown-{pid}"` as the session ID. The monitor thread falls back to monitoring by PID.

### 4.6 Checkpoints absent
If `--checkpoints` is not set, `checkpoint_latest` in the heartbeat is always `null`. The retry session still gets a recovery context note but does not get `--resume`.

### 4.7 heartbeat_timeout = 0 (default)
When heartbeat_timeout is 0, the feature is completely disabled — no heartbeat instructions in prompts, no monitor threads, no kill logic. Behavior is identical to current v13.0.0.

---

## 5. Current Code Context (Important Line Numbers)

| Location | Line Number | What It Is |
|----------|------------|------------|
| `_ERROR_THRESHOLDS` | ~3728 | Error severity thresholds |
| `_adapt_to_error()` | 3748 | Error mitigation system |
| `_build_delegation_prompt()` | 2733 | Prompt builder; add heartbeat_interval param |
| Prompt end + EXTRA INSTRUCTIONS | ~3084 | Where heartbeat block gets injected |
| `spawn_delegation_session()` | 3094 | Session spawner; add heartbeat_timeout param |
| Subprocess execution | ~3417 | `subprocess.run(cmd, ...)` — replace with Popen for heartbeat |
| `_execute_iteration()` | 3956 | Iteration execution; thread heartbeat_timeout |
| `spawn_delegation_session` call (single) | ~4162 | Pass heartbeat_timeout |
| `spawn_delegation_session` call (multi-worker) | ~4099 | Pass heartbeat_timeout |
| `_merge_worker_results()` | 4211 | Merge worker results; detect heartbeat_expired |
| `_build_iteration_record()` | 4429 | Record builder; add heartbeat field |
| `run_loop()` | 4635 | Main loop; accept heartbeat_timeout |
| `_execute_iteration` call | ~5002 | Thread heartbeat_timeout to _execute_iteration |
| `main()` argparse | ~5929 | CLI arg parsing |
| `main()` run_loop call | ~6696 | Pass heartbeat_timeout to run_loop |

---

## 6. Implementation Order

1. Add constants and `_ERROR_SEVERITY` / `_ERROR_THRESHOLDS` updates
2. Add helper functions (`_heartbeat_path`, `_read_heartbeat`, `_write_heartbeat_file`, `_heartbeat_age`, `_start_library_heartbeat`, `_kill_session`, `_monitor_heartbeat_file`, `_run_heartbeat_monitor_in_thread`, `_cleanup_stale_heartbeats`, `_cleanup_single_heartbeat`)
3. Update `_adapt_to_error()` — add `"heartbeat"` error type
4. Update `_build_delegation_prompt()` — add `heartbeat_interval` param + inject heartbeat instructions
5. Update `spawn_delegation_session()` — add params, integrate heartbeat monitor into subprocess path
6. Update `_execute_iteration()` — thread heartbeat_timeout to spawn calls
7. Update `_merge_worker_results()` — detect heartbeat_expired
8. Update `_build_iteration_record()` — include heartbeat data
9. Update `run_loop()` — accept, log, and thread heartbeat_timeout
10. Add `--heartbeat-timeout` CLI arg
11. Update `main()` — pass heartbeat_timeout to run_loop, add to banner

---

## 7. Testing (via `--self-test`)

Add these test cases to `_run_self_test()`:

| Test | Description |
|------|-------------|
| `heartbeat_write_read` | Create a heartbeat file, read it back, verify fields |
| `heartbeat_expiry_detection` | Set old timestamp, confirm `_heartbeat_age()` > threshold |
| `heartbeat_monitor_alive` | Fresh heartbeat file, monitor returns alive |
| `heartbeat_monitor_lost` | No file ever created, monitor returns lost after grace |
| `grace_period_expiry` | Heartbeat just outside window, returns alive (in grace) |
| `grace_period_death` | Heartbeat far outside window, returns dead |
| `heartbeat_prompt_injection` | `_build_delegation_prompt()` includes heartbeat block when interval>0 |
| `heartbeat_prompt_no_injection` | No heartbeat block when interval=0 |
| `stale_heartbeat_cleanup` | Create stale files, run cleanup, verify removal |
| `heartbeat_path_format` | Verify `_heartbeat_path()` returns correct path |
