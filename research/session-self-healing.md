# Session Self-Healing — Design Document

**Status:** Draft for review
**Version:** 1.0
**Target:** `launch-loop.py` v13 (infinite-loop skill)
**Author:** Research subagent

---

## 1. Problem Statement

The infinite-loop daemon (`launch-loop.py`) spawns Hermes sessions via
`hermes chat -q` (subprocess), `AIAgent.run_conversation()` (library mode),
or an HTTP worker endpoint. When a spawned session crashes **mid-iteration**
— due to a network blip, OOM kill, process termination, or unhandled
exception — `spawn_delegation_session()` returns an error dict (e.g.,
`exit_code: -1` with error message), and the daemon moves on to the next
iteration via the existing retry/backoff machinery.

The gap: **the daemon has no awareness of partial progress within a running
session.** If a session was 70% through a complex task and got killed, the
daemon doesn't know:

- Whether the session was alive up to a certain point and then died.
- Whether checkpoint files exist from that session to resume from.
- Whether to give the session time to recover (e.g., a transient network
  issue resolves itself in 60 seconds).
- How to signal the *next* spawned session to pick up where the dead one
  left off.

There is also **no detection of a "hung but not dead" session** — a process
that is still alive but making no progress (e.g., stuck on an API call,
infinite loop inside the LLM).

---

## 2. Design Overview

The self-healing system adds **three layers** to the daemon:

1. **Heartbeat mechanism** — each spawned session periodically writes a
   heartbeat file. The daemon monitors these heartbeats.
2. **Expiry & grace period** — when a heartbeat stops, the daemon waits
   through a grace period before declaring the session dead, giving it time
   to recover.
3. **Checkpoint-aware resumption** — if the session was started with
   `--checkpoints`, the retry reads the latest checkpoint and resumes from
   there instead of starting from scratch.

All components use **Python stdlib only** — no new dependencies.

---

## 3. Architectural Decisions

### 3.1 Why a file-based heartbeat instead of signals or pipes?

| Mechanism     | Pros                                      | Cons                                           |
|---------------|-------------------------------------------|-------------------------------------------------|
| File touch    | Works across subprocess/library/worker modes; survives parent crash; visible for debugging | Slight I/O overhead every 30s                  |
| Signal (SIGUSR1) | Very light                                | Only works for subprocess mode; lost if parent dies during signal |
| Pipe/select   | Real-time detection                       | Only works for subprocess mode; complex to multiplex |
| Shared memory | Very fast                                 | Not stdlib; fragile across re-exec             |

**Decision: File-based heartbeat.** A spawned session touches a known
heartbeat file path every 30 seconds. The daemon polls these files. This
works identically in subprocess, library, and worker URL modes.

### 3.2 Where does the heartbeat file live?

```
/tmp/infinite-loop-heartbeat-{session_id}
```

The `session_id` is the spawned Hermes session ID (for subprocess mode,
extracted from stdout; for library mode, from `AIAgent.session_id`; for
worker mode, from the HTTP response).

If `session_id` is not available (e.g., the session failed before printing
it), fall back to a file named by **process PID**:

```
/tmp/infinite-loop-heartbeat-{pid}
```

### 3.3 What does the heartbeat file contain?

A single line of JSON:

```json
{"session_id": "uuid", "iteration": 42, "timestamp": 1719360000.0, "pid": 12345, "checkpoint_latest": "/path/to/checkpoint.json"}
```

Written atomically (write to `.tmp`, then `os.rename()`).

---

## 4. Detailed Design

### 4.1 Heartbeat Emission (spawned session side)

The instruction to emit heartbeats is injected into the spawned session's
**prompt** via `_build_delegation_prompt()`. A new section is appended to
the prompt instructions:

```
=== SESSION HEARTBEAT ===
You MUST emit a heartbeat every 30 seconds so the daemon knows you are alive.
Run this shell command every 30s (use terminal):
  python3 -c "
import json, os, time
hb = '/tmp/infinite-loop-heartbeat-SESSION_ID'
os.makedirs(os.path.dirname(hb), exist_ok=True)
with open(hb + '.tmp', 'w') as f:
    json.dump({'session_id':'SESSION_ID','iteration':ITERATION,
               'timestamp':time.time(),'pid':os.getpid()}, f)
os.rename(hb + '.tmp', hb)
"
Replace SESSION_ID with your actual session_id.
Replace ITERATION with the actual iteration number.
If you cannot determine your session_id, use 'unknown-SESSION_ID'.
DO NOT skip this — the daemon uses heartbeats to know you are still working.
If heartbeats stop, the daemon will kill and retry this session.
```

In **library mode**, the heartbeat cannot rely on the LLM remembering to
run a command. Instead, the daemon spawns a **background thread** before
calling `agent.run_conversation()` that touches the heartbeat file in a
loop:

```python
def _start_library_heartbeat(session_id: str, iteration: int, interval: int = 30):
    def _heartbeat_loop():
        hb_path = f"/tmp/infinite-loop-heartbeat-{session_id}"
        while not _shutdown_requested:
            try:
                os.makedirs(os.path.dirname(hb_path), exist_ok=True)
                tmp = hb_path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump({
                        "session_id": session_id,
                        "iteration": iteration,
                        "timestamp": time.time(),
                        "pid": os.getpid(),
                    }, f)
                os.rename(tmp, hb_path)
            except Exception:
                pass
            time.sleep(interval)
    t = threading.Thread(target=_heartbeat_loop, daemon=True)
    t.start()
    return t
```

In **worker URL mode**, the worker is expected to include a `hb_file` field
in its response, or the daemon polls the worker's health endpoint. This is
the weakest mode — see §6.

### 4.2 Heartbeat Injection Into `_build_delegation_prompt()`

A new parameter `heartbeat_interval: int = 0` is added to
`_build_delegation_prompt()`. When > 0, the heartbeat instruction block is
appended before the "EXTRA INSTRUCTIONS" section (i.e., at the same level as
the self-modification context block).

The instructions include a template with `{session_id_placeholder}` and
`{iteration_placeholder}` that are filled in at prompt-build time if
available (for library mode), or left as placeholders for the spawned session
to fill in.

### 4.3 Heartbeat Monitoring (daemon side)

A new function `_monitor_heartbeat()` is added:

```python
def _monitor_heartbeat(
    heartbeat_file: str,
    grace_period: int = 60,
    poll_interval: int = 10,
) -> tuple[str, float | None]:
    """Monitor a heartbeat file for a spawned session.

    Args:
        heartbeat_file: Path to the heartbeat file to monitor.
        grace_period: Seconds to wait after heartbeat expiry before
                      declaring the session dead.
        poll_interval: How often to check the heartbeat file (seconds).

    Returns:
        (status, age_seconds) where status is one of:
            "alive"       — heartbeat is current
            "expired"     — heartbeat stopped but within grace period
            "dead"        — heartbeat stopped past grace period
            "lost"        — heartbeat file never appeared
            "completed"   — the subprocess finished normally
    """
```

This function is called from within `spawn_delegation_session()` in a
**separate monitoring thread** while the main thread waits for the
subprocess/library call to complete.

The monitoring thread polls every 10 seconds:

1. Check if the heartbeat file exists.
2. If it exists, check the timestamp inside — if `time.time() - timestamp >
   heartbeat_timeout + grace_period`, mark as dead.
3. If it doesn't exist and the session started > `grace_period` seconds ago,
   mark as lost.
4. If `last_seen` timestamp is older than `heartbeat_timeout` (30s) but
   within the grace window, log a warning.
5. When the subprocess completes normally, the monitor thread exits.

### 4.4 Grace Period (60 seconds)

The grace period exists to handle transient failures:

- **Network blip**: The LLM API call hangs for 30-45s, then recovers. The
  heartbeat thread in the spawned session may also stall (it's a Python
  command running in `terminal`), but the session process is still alive.
  The grace period prevents premature kill.
- **OOM temporary**: If the system reclaims memory and the process resumes
  (unlikely for real OOM kills, but possible for cgroup soft limits), the
  grace period gives it a window.
- **Process preemption**: Under heavy load, the scheduler may pause the
  heartbeat-writing `terminal` command while the main LLM thread is still
  active.

The daemon waits `heartbeat_timeout + grace_period` seconds from the last
successful heartbeat before declaring the session dead.

### 4.5 Session Kill & Retry with Checkpoint Resumption

When heartbeat expiry is detected (and the subprocess has not exited
normally), the daemon:

1. **Kills the subprocess** (if still alive) via `process.terminate()`,
   then `process.kill()` after 5-second delay.

2. **Checks for checkpoints** — looks at the `checkpoint_latest` field from
   the last valid heartbeat file. If present and `--checkpoints` is enabled,
   passes `--resume LATEST_CHECKPOINT_PATH` to the retried spawned session.

3. **Appends checkpoint context to the prompt** — adds a note:

   ```
   === RECOVERY — RESUMING FROM CHECKPOINT ===
   The previous session crashed. Resuming from checkpoint:
     {checkpoint_path}
   Continue work from where the previous session left off.
   Do NOT restart from scratch.
   ```

4. **Logs** the recovery action to the ledger:

   ```json
   {
     "heartbeat_recovery": {
       "last_heartbeat": 1719360000.0,
       "session_id": "dead-session-uuid",
       "grace_elapsed": 65,
       "checkpoint_resumed": "/path/to/checkpoint.json",
       "retry_count": 1
     }
   }
   ```

5. If the retry *also* fails (heartbeat stops again), increment a
   `heartbeat_retry_count` in `state`. If it exceeds 3 consecutive
   heartbeat failures, escalate to `_adapt_to_error()` (the existing
   mitigation system) with a new error type `"heartbeat"`.

### 4.6 New CLI Flag: `--heartbeat-timeout`

```
parser.add_argument(
    "--heartbeat-timeout",
    type=int,
    default=60,
    help="Max seconds since last heartbeat before session is declared dead "
    "(default: 60). The grace period is always heartbeat_timeout * 2 "
    "(=120s total window). Set to 0 to disable heartbeat monitoring.",
)
```

When `--heartbeat-timeout 0` (or not set for backward compat), heartbeat
monitoring is entirely disabled. The existing behavior is preserved.

The flag flows through:

- `run_loop()` accepts `heartbeat_timeout: int = 0`
- `_execute_iteration()` receives and passes it to
  `spawn_delegation_session()`
- `spawn_delegation_session()` uses it to control the monitor thread
- `_build_delegation_prompt()` uses it to decide whether to inject heartbeat
  instructions

### 4.7 Ledger Storage

New field in the ledger state:

```json
{
  "heartbeat": {
    "enabled": true,
    "timeout": 60,
    "recoveries": 0,
    "last_recovery": "2025-06-26T06:30:00Z",
    "sessions": {
      "session-uuid-1": {
        "last_heartbeat": 1719360000.0,
        "pid": 12345,
        "state": "completed",
        "grace_triggered": false
      },
      "session-uuid-2": {
        "last_heartbeat": null,
        "pid": 12346,
        "state": "dead",
        "grace_triggered": true,
        "grace_duration": 62,
        "checkpoint": "/path/to/checkpoint.json",
        "recovered": true
      }
    }
  }
}
```

Each iteration record also gets a `heartbeat` field:

```json
{
  "n": 42,
  "heartbeat": {
    "session_id": "uuid",
    "last_seen": 1719360000.0,
    "grace_triggered": false,
    "recovered": false,
    "checkpoint_used": null
  }
}
```

The `_build_iteration_record()` function is updated to include this data.

### 4.8 Integration Points in launch-loop.py

#### 4.8.1 `_build_delegation_prompt()` (line 2733)

- New parameter: `heartbeat_interval: int = 0`
- When > 0, appends a heartbeat instruction block (see §4.1) to the prompt.
- The block includes placeholder tokens `{session_id}` and `{iteration}`.
- For library mode, substitutes the actual session_id at prompt-build time.
- For subprocess mode, leaves tokens for the spawned session to self-identify,
  but also includes a fallback: "If you cannot determine your session_id, use
  'unknown-{pid}' where {pid} is your process ID."

#### 4.8.2 `spawn_delegation_session()` (line 3094)

- New parameter: `heartbeat_timeout: int = 0`
- New parameter: `iteration_count: int = 0`
- After spawning the subprocess (or starting library mode), starts a
  **heartbeat monitor thread** if `heartbeat_timeout > 0`.
- The monitor thread runs concurrently with the main wait.
- On heartbeat expiry → kill + return early with a structured error dict that
  includes `heartbeat_expired: True` and `session_id` and `checkpoint_latest`.
- On normal completion, the monitor thread stops and the result is returned
  as usual.

#### 4.8.3 `_execute_iteration()` (line 3956)

- New parameter: `heartbeat_timeout: int`
- Passes it to `spawn_delegation_session()` calls.
- Also passes the current `iteration_count` so it ends up in heartbeat files.

#### 4.8.4 `_merge_worker_results()` (line 4211)

- Detects `heartbeat_expired: True` in any worker result.
- When detected, updates `combined_error` to include recovery info.
- Passes checkpoint path if available.

#### 4.8.5 `_adapt_to_error()` (line 3748)

- New error type `"heartbeat"` added to `_ERROR_THRESHOLDS`.
- After 3 consecutive heartbeat failures, escalates:
  - Removes `--checkpoints` (checkpoints may be the cause if they're slow).
  - Forces library mode → subprocess mode (library mode may be unstable).
  - Extends session_timeout by 2x (the session may be timing out on API).

#### 4.8.6 `run_loop()` (line 4635)

- New parameter: `heartbeat_timeout: int`
- Logs at startup: `[DAEMON] Heartbeat monitoring enabled (timeout={heartbeat_timeout}s, grace={grace_period}s)`
- Passes to `_execute_iteration()`.

#### 4.8.7 Argparse (line 5929)

- New flag: `--heartbeat-timeout` (default: 60, type: int)

### 4.9 Subprocess Kill Logic

When a heartbeat expires during subprocess execution:

```python
def _kill_session(proc: subprocess.Popen, session_id: str):
    """Force-kill a session process."""
    if proc.poll() is not None:
        return  # Already dead
    _log(f"[HEARTBEAT] Killing hung session {session_id[:12]}...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()  # SIGKILL
        proc.wait(timeout=3)
    _log(f"[HEARTBEAT] Session {session_id[:12]} killed (exit={proc.returncode})")
```

For library mode, killing is handled by setting `_shutdown_requested = True`
which the library heartbeat thread checks, plus calling `agent.stop()` if
available.

---

## 5. Edge Cases

### 5.1 Heartbeat file never appears

If the spawned session crashes before its first `terminal` command runs, no
heartbeat file ever appears. The monitor thread detects this after
`grace_period` seconds and marks the session as `"lost"`. The daemon kills
the session (if still alive) and retries.

### 5.2 Heartbeat file stale after normal completion

When the session completes normally, `spawn_delegation_session()` cleans up
the heartbeat file:

```python
# Clean up heartbeat file on normal completion
if heartbeat_file and os.path.exists(heartbeat_file):
    try:
        os.remove(heartbeat_file)
    except OSError:
        pass
```

The monitor thread checks the subprocess exit code — if it has exited with
code 0, the heartbeat is irrelevant.

### 5.3 Multiple workers

Each worker in a multi-worker iteration gets its own heartbeat file (named
by session ID or PID + worker_id). The monitor thread tracks each file
independently. If worker 2's heartbeat dies but worker 1's is fine, only
worker 2 is killed and retried (via `_execute_iteration()`'s per-worker
result handling).

### 5.4 Daemon restart mid-session

If the daemon itself crashes and restarts (e.g., via `os.execv()` for
self-modification), the old heartbeat files remain on disk. On restart, the
daemon cleans up stale heartbeat files:

```python
def _cleanup_stale_heartbeats():
    """Remove heartbeat files from previous daemon instances."""
    import glob
    for f in glob.glob("/tmp/infinite-loop-heartbeat-*"):
        try:
            os.remove(f)
        except OSError:
            pass
```

Called once at `run_loop()` startup.

### 5.5 Session ID unknown

If the spawned session fails before printing its session_id, the heartbeat
file uses `unknown-{pid}` as the ID. The daemon monitors this file by PID
instead of session ID. On retry, without a known session_id, checkpoint
resumption is not possible — the session restarts from scratch.

### 5.6 Checkpoints flag not set

If `--checkpoints` was not passed to the spawned session, the
`checkpoint_latest` field in the heartbeat is always `null`. The retry
session still gets the recovery context note ("The previous session
crashed...") but does not get `--resume` — it restarts from scratch with the
same prompt.

### 5.7 Heartbeat timeout = 0 (backward compatibility)

When `--heartbeat-timeout 0`, the feature is entirely disabled:
- No heartbeat instructions in prompts.
- No monitor threads.
- No kill logic.
- Behavior is identical to current v13.0.0.

This is the default for existing configs/users.

---

## 6. Worker URL Mode Considerations

In worker URL mode (`--worker-url http://...`), the daemon does not manage
the subprocess directly — it sends an HTTP POST and waits for a response.
Heartbeat monitoring is more limited in this mode:

**Option A (recommended):** The worker is expected to include a `heartbeat`
field in its periodic status responses. If the worker supports long-polling
or streaming responses, the daemon parses intermediate status lines looking
for `{"type": "heartbeat", ...}`.

**Option B (fallback):** The daemon polls the worker's health endpoint
(`{worker_url}/health`) every 30 seconds while waiting. If the health check
fails consistently for `heartbeat_timeout + grace_period` seconds, the
daemon declares the session dead, cancels the HTTP request, and retries
with a fresh worker URL (or falls back to subprocess mode).

**Implementation:** In `spawn_delegation_session()`, when `worker_url` is
set, a separate health-monitor thread polls the worker's health endpoint
every 30s. If the worker stops responding, the daemon treats it as a
heartbeat expiry.

---

## 7. Testing Strategy

### 7.1 Unit Tests (via `--self-test`)

Add these test cases to the existing `_run_self_test()` function:

| Test                           | Description                                                        |
|--------------------------------|--------------------------------------------------------------------|
| `heartbeat_write_read`         | Create a heartbeat file, read it back, verify fields.              |
| `heartbeat_expiry_detection`   | Set old timestamp, confirm `_monitor_heartbeat()` returns "expired". |
| `heartbeat_monitor_alive`      | Fresh heartbeat, confirm "alive".                                  |
| `heartbeat_monitor_lost`       | No file ever created, confirm "lost".                              |
| `grace_period_expiry`          | Heartbeat just outside window, confirm still in grace period.      |
| `grace_period_death`           | Heartbeat far outside window, confirm "dead".                      |
| `heartbeat_prompt_injection`   | Verify `_build_delegation_prompt()` includes heartbeat block when`heartbeat_interval>0`.|
| `heartbeat_prompt_no_injection`| Verify no heartbeat block when `heartbeat_interval=0`.             |
| `checkpoint_resumption_path`   | Verify retry constructs `--resume` with the right checkpoint path. |
| `kill_hung_session`            | Simulate a hung subprocess, verify kill logic runs.                |
| `ledger_heartbeat_field`       | Verify iteration record contains `heartbeat` field.                |
| `stale_heartbeat_cleanup`      | Create stale files, run cleanup, verify they're removed.           |

### 7.2 Integration Scenarios

1. **Normal operation with heartbeats**: Run loop with 1 worker,
   `--heartbeat-timeout 60`. Verify heartbeat files appear in `/tmp/`.
   Verify they contain correct session_id and iteration number.

2. **Network blip recovery**: Start a session, pause its network (e.g.,
   block the LLM API host via iptables). Heartbeat stops. Grace period
   triggers. Before expiry, unblock network — session should recover
   naturally and daemon should not kill it.

3. **OOM kill**: Run a memory-intensive task in the spawned session.
   Limit memory via cgroup (`memory.max=512M`). The process should get
   killed by OOM killer. Daemon should detect heartbeat expiry, kill
   (already dead), log recovery, retry.

4. **Checkpoint resumption**: Run with `--checkpoints`. Manually kill the
   spawned session mid-work. Verify daemon retries with `--resume` pointing
   to the latest checkpoint. Verify the new session continues from where
   the old one left off.

5. **Grace period transit**: Kill the spawned session. Wait 30s — daemon
   should log "heartbeat expired (grace period)". Wait 60s total — daemon
   should log "session dead, killing and retrying".

6. **Multiple workers, one failure**: Run with `--workers 3 --heartbeat-timeout 60`.
   Kill one worker's process. Verify that only the affected worker is
   retried, and the other two complete normally.

---

## 8. File Changes Summary

| File | Change |
|------|--------|
| `scripts/launch-loop.py` | Add `--heartbeat-timeout` CLI flag |
| `scripts/launch-loop.py` | Add heartbeat constants (`HEARTBEAT_DIR = "/tmp"`, `HEARTBEAT_PREFIX = "infinite-loop-heartbeat-"`) |
| `scripts/launch-loop.py` | Add `_start_heartbeat_monitor()` function |
| `scripts/launch-loop.py` | Add `_kill_session()` function |
| `scripts/launch-loop.py` | Add `_cleanup_stale_heartbeats()` function |
| `scripts/launch-loop.py` | Modify `_build_delegation_prompt()` — add `heartbeat_interval` param, inject heartbeat instructions |
| `scripts/launch-loop.py` | Modify `spawn_delegation_session()` — add `heartbeat_timeout` and `iteration_count` params, start monitor thread |
| `scripts/launch-loop.py` | Modify `_execute_iteration()` — thread `heartbeat_timeout` through |
| `scripts/launch-loop.py` | Modify `_merge_worker_results()` — handle `heartbeat_expired` flag |
| `scripts/launch-loop.py` | Modify `_build_iteration_record()` — include heartbeat data |
| `scripts/launch-loop.py` | Modify `_adapt_to_error()` — add `"heartbeat"` to error thresholds |
| `scripts/launch-loop.py` | Modify `run_loop()` — accept/thread `heartbeat_timeout` |
| `scripts/launch-loop.py` | Modify `write_ledger()` callers — store heartbeat state |
| `scripts/launch-loop.py` | Add heartbeat tests to `_run_self_test()` |
| `SKILL.md` | Document `--heartbeat-timeout` flag |

---

## 9. Constants and Defaults

| Name                     | Value               | Location                              |
|--------------------------|---------------------|---------------------------------------|
| `HEARTBEAT_INTERVAL`     | 30                  | `_start_library_heartbeat()` interval |
| `HEARTBEAT_DEFAULT_TIMEOUT` | 60               | argparse default                      |
| `HEARTBEAT_GRACE_FACTOR` | 2.0                 | grace = timeout × 2                   |
| `HEARTBEAT_POLL_INTERVAL`| 10                  | monitor thread poll period            |
| `HEARTBEAT_MAX_CONSECUTIVE` | 3                | before escalation to `_adapt_to_error`|
| `HEARTBEAT_KILL_GRACE`   | 5                   | seconds between SIGTERM and SIGKILL   |
| `HEARTBEAT_DIR`          | `/tmp`              | heartbeat file directory              |
| `HEARTBEAT_PREFIX`       | `infinite-loop-heartbeat-` | heartbeat file name prefix      |

---

## 10. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Heartbeat I/O slows session | Low | Low | File write every 30s is negligible; library mode uses a separate thread so it doesn't block the LLM call |
| Stale heartbeat file causes false recovery | Low | Medium | Monitor thread checks subprocess alive-ness in addition to file timestamps; clean up on normal exit |
| Library mode heartbeat thread interferes with AIAgent | Low | Low | Daemon thread, separate from agent; thread uses `_shutdown_requested` flag |
| Grace period too short for real recovery | Medium | Medium | Configurable via `--heartbeat-timeout`; default 60s × 2 = 120s total window |
| Worker URL mode lacks process control | Medium | High | Fall back to health-check polling; document that heartbeat is best-effort in worker mode |
| Spawned session forgets to emit heartbeat | Medium | Medium | Prompt includes explicit instruction; library mode auto-emits; subprocess mode fallback to `unknown-{pid}` |
| Heartbeat file path collision from parallel daemons | Low | Low | Each daemon instance calls `_cleanup_stale_heartbeats()` on startup |

---

## 11. Open Questions

1. Should the heartbeat instruction in the prompt be placed early (before
   the tool instructions) to maximize the chance the LLM reads it before
   starting work? **Yes — place right after "GOAL" and "CONTEXT".**

2. Should the daemon log heartbeats at DEBUG level to avoid spamming
   stdout? **Yes — heartbeat monitor thread logs use `_log(..., level="DEBUG")`
   to avoid cluttering normal output.**

3. Should checkpoint resumption automatically increment a
   `recovery_iteration` counter to prevent infinite recovery loops?
   **Yes — tracked via `heartbeat_retry_count` in state, max 3 per
   iteration before escalation.**

4. Do we need a `--heartbeat-dir` flag for custom file locations (e.g.,
   RAM-backed tmpfs)? **Not for v1 — `/tmp` is universally available. Add
   if users request it.**

5. Should the heartbeat file include the spawned session's prompt hash for
   debug traceability? **Not for v1 — adds complexity. The session_id is
   sufficient for traceability.**
