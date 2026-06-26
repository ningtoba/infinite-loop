# Concurrent Library Mode Feasibility Study

Date: 2026-06-26
Target: launch-loop.py v11.14.0, AIAgent from Hermes core
Goal: Enable `--use-library` with `--workers > 1` by replacing `ThreadPoolExecutor` with `multiprocessing.Pool`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture](#2-current-architecture)
3. [AIAgent Picklability Analysis](#3-aiagent-picklability-analysis)
4. [Serializable Parameter Subset](#4-serializable-parameter-subset)
5. [Worker Function Design](#5-worker-function-design)
6. [Global State Risks](#6-global-state-risks)
7. [Fallback Strategy](#7-fallback-strategy)
8. [Implementation Plan](#8-implementation-plan)
9. [Edge Cases & Gotchas](#9-edge-cases--gotchas)
10. [Summary](#10-summary)

---

## 1. Executive Summary

**Feasible with moderate effort.** The Hermes `batch_runner.py` already uses `multiprocessing.Pool` to run `AIAgent.run_conversation()` in child processes — this is a proven pattern. The key insight is that AIAgent instances are **not pickled across the process boundary**; instead, each child process constructs a fresh `AIAgent(...)` from a serializable config dict. This is exactly the approach we should use.

The main changes needed:
- Extract the library-mode execution path from `spawn_delegation_session()` into a module-level function (`_library_worker`)
- Pass a flat config dict (picklable types only) instead of complex objects
- Replace `ThreadPoolExecutor` with `multiprocessing.Pool` in the multi-worker branch
- Leave the single-worker path (`workers=1`) unchanged — it's simpler and avoids process overhead

---

## 2. Current Architecture

### 2.1 The Problem

```python
# launch-loop.py line 3380-3428 — multi-worker path
if workers > 1:
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for w_id in range(workers):
            fut = executor.submit(
                spawn_delegation_session,
                ...
                use_library=False,  # ← Hardcoded False!
                ...
            )
```

Line 3413: `use_library=False` is hardcoded for multi-worker path because `threading` shares memory space — spawn_delegation_session() enters library mode at line 2500 only when `worker_id is None`.

Line 4438-4443: The CLI explicitly disables library mode when `--workers > 1`:
```python
if args.use_library and args.workers > 1:
    _log("[WARN] --use-library is incompatible with --workers > 1. ...")
    args.use_library = False
```

### 2.2 The Bridge: batch_runner.py's Pattern

The Hermes `batch_runner.py` demonstrates the correct approach:

```python
# batch_runner.py ~line 918-959
with Pool(processes=self.num_workers) as pool:
    tasks = [(batch_num, batch_data, str(output_dir), completed_prompts_set, config)]
    for result in pool.imap_unordered(_process_batch_worker, tasks):
        ...
```

Where each worker:
1. Receives a plain `config` dict (str, int, bool, list, dict — all picklable)
2. Calls `from run_agent import AIAgent` inside the worker function
3. Creates `AIAgent(...)` from scratch using config dict values
4. Returns a picklable result dict

**This is the pattern we replicate, adapted for the infinite-loop use case.**

---

## 3. AIAgent Picklability Analysis

### 3.1 Can AIAgent be pickled?

**No, and we should not try.** AIAgent has:
- No `__getstate__`/`__setstate__`/`__reduce__` methods
- Complex internal state: callbacks (`tool_progress_callback`, `status_callback`, etc.), logging state, open file handles for checkpoints, API client objects, thread locks
- A context engine with in-memory message history
- Provider connections (API clients, credential caches)

### 3.2 The Correct Approach: Create-from-Scratch per Process

This is proven by `batch_runner.py` `_process_single_prompt()` (line 244-397):

```python
def _process_single_prompt(prompt_index, prompt_data, batch_num, config):
    from run_agent import AIAgent  # ← fresh import each time
    agent = AIAgent(
        base_url=config.get("base_url"),
        api_key=config.get("api_key"),
        model=config["model"],
        max_iterations=config["max_iterations"],
        enabled_toolsets=selected_toolsets,
        ...
    )
    result = agent.run_conversation(prompt, task_id=task_id)
    # ...extract results, return picklable dict
```

This works because:
- `multiprocessing.Pool` uses `fork` (default on Linux) or `spawn`
- With `fork`, child processes inherit the parent's module cache — `run_agent` is already imported
- With `spawn`, each child starts fresh and imports everything
- `AIAgent.run_conversation()` is a synchronous method — it takes no callbacks (except optional stream_callback which we don't use)
- The constructor parameters are all basic types (str, bool, int, list, dict)

### 3.3 What the Child Process Gets

| Mechanism | Module State | File Descriptors | Open FDs inherit? |
|-----------|-------------|------------------|-------------------|
| `fork` | Inherits parent's module cache | Inherits parent's FDs (closed by `Pool` setup) | Inherited but `Pool` marks them CLOEXEC |
| `spawn` | Fresh import of everything | Only stdin/stdout/stderr | New process gets clean FDs |

The `multiprocessing.Pool` constructor (with default `ctx=None`) uses `fork` on Linux, which means:
- Imports are already cached in memory — no re-import overhead
- Python's `logging` module state is inherited (logger hierarchy, handlers)
- **BUT**: inherited log handlers try to write to the same file — use `QueueHandler`/`QueueListener` or suppress inherited handlers

---

## 4. Serializable Parameter Subset

From `spawn_delegation_session()`'s 25+ parameters, the library worker needs:

### 4.1 Required for AIAgent Constructor

| Parameter | Type | Picklable? | Notes |
|-----------|------|-----------|-------|
| `model` | str | ✓ | |
| `max_turns` | int | ✓ | Maps to `max_iterations` |
| `toolsets` | list[str] | ✓ | Maps to `enabled_toolsets` |
| `prompt` (from `_build_delegation_prompt`) | str | ✓ | This is `ephemeral_system_prompt` |
| `checkpoints` | bool | ✓ | Maps to `checkpoints_enabled=True` |
| `pass_session_id` | bool | ✓ | |

### 4.2 Required for Result Processing

| Parameter | Type | Picklable? | Notes |
|-----------|------|-----------|-------|
| `iteration` | int | ✓ | For logging |
| `worker_id` | int | ✓ | For tagging |
| `timeout_seconds` | int | ✓ | Used for timeout in parent |
| `output_schema` | dict or None | ✓ | |
| `max_output_chars` | int | ✓ | |

### 4.3 NOT Needed (subprocess-only flags)

`safe_mode`, `accept_hooks`, `worktree`, `continue_session`, `skills`, `ignore_rules`, `yolo`, `ignore_user_config`, `spawn_source`, `resume_session_id` — these only affect subprocess command-line construction. In library mode, AIAgent doesn't have equivalents for any of these.

### 4.4 The Config Dict Structure

```python
library_config = {
    "model": model,
    "max_iterations": max_turns,
    "enabled_toolsets": list(toolsets),
    "ephemeral_system_prompt": prompt,  # ← built by _build_delegation_prompt()
    "checkpoints_enabled": checkpoints,
    "pass_session_id": pass_session_id,
    "quiet_mode": True,
    "skip_memory": True,
    "session_id": resume_session_id or None,
    "timeout_seconds": timeout_seconds,
}
```

---

## 5. Worker Function Design

### 5.1 Module-Level Worker Function

Must be defined at **module level** (not nested inside another function) so `multiprocessing.Pool` can pickle it across the boundary.

```python
def _library_worker(config: dict, prompt: str, worker_id: int) -> dict:
    """Run a single AIAgent conversation in a child process.
    
    Args:
        config: Flat picklable dict with AIAgent params (see §4.4).
        prompt: The system prompt to execute.
        worker_id: Worker index for logging.
        
    Returns:
        Result dict matching spawn_delegation_session() output format.
    """
    from run_agent import AIAgent  # safe: module-level import in child process
    
    start = time.time()
    _setup_worker_logging(config.get("log_prefix", f"[LIBRARY (worker #{worker_id})]"))
    
    try:
        agent = AIAgent(
            model=config["model"] or None,
            max_iterations=config["max_iterations"],
            enabled_toolsets=config["enabled_toolsets"],
            quiet_mode=True,
            ephemeral_system_prompt=prompt,
            skip_memory=True,
            checkpoints_enabled=config.get("checkpoints_enabled", False),
            pass_session_id=config.get("pass_session_id", False),
            session_id=config.get("session_id", None),
        )
        conv_result = agent.run_conversation(user_message=prompt)
        
        elapsed = time.time() - start
        spawned_session_id = conv_result.get("session_id", "") or getattr(agent, "session_id", "")
        final_response = conv_result.get("final_response", "")
        
        return _build_library_result(
            conv_result, final_response, spawned_session_id,
            elapsed, config.get("max_output_chars", 2000),
            config.get("output_schema")
        )
    except Exception as e:
        elapsed = time.time() - start
        return {
            "summary": f"WORKER #{worker_id} FAILED: {e}",
            "duration_seconds": round(elapsed, 1),
            "error": str(e),
            "error_type": classify_error(str(e)),
            "output": "",
            "exit_code": -1,
            "spawned_session_id": "",
            "worker_id": worker_id,
        }
```

### 5.2 Helper: `_build_library_result`

This is the existing logic from lines 2542-2622 of launch-loop.py, refactored into a standalone function:

```python
def _build_library_result(
    conv_result: dict,
    final_response: str,
    spawned_session_id: str,
    elapsed: float,
    max_output_chars: int,
    output_schema: dict | None,
) -> dict:
    """Build the result dict from an AIAgent conversation result."""
    from run_agent import extract_json_from_output  # or import at module top level
    
    parsed_json = extract_json_from_output(final_response)
    
    if parsed_json:
        result_obj = {
            "summary": parsed_json.get("summary", final_response[:max_output_chars]),
            "duration_seconds": parsed_json.get("duration_seconds", round(elapsed, 1)),
            "error": parsed_json.get("error"),
            "next_goal": parsed_json.get("next_goal"),
            "context": parsed_json.get("context", final_response[:500]),
            "output": final_response[:max_output_chars] if max_output_chars > 0 else final_response,
            "stderr": "",
            "exit_code": 0,
            "total_output_bytes": len(final_response),
            "truncated": max_output_chars > 0 and len(final_response) > max_output_chars,
            "spawned_session_id": spawned_session_id,
        }
        if output_schema:
            schema_valid, schema_error = validate_json_output(parsed_json, output_schema)
            result_obj["schema_valid"] = schema_valid
            result_obj["schema_error"] = schema_error if not schema_valid else None
        output_len = len(final_response)
        result_obj["output_chars"] = output_len
        dur = result_obj["duration_seconds"]
        result_obj["chars_per_second"] = round(output_len / dur, 1) if dur > 0 else 0
        result_obj["error_type"] = classify_error(result_obj.get("error"))
        return result_obj
    
    # No JSON found
    return {
        "summary": final_response[:max_output_chars] if final_response else "(no output)",
        "duration_seconds": round(elapsed, 1),
        "error": None,
        "output": final_response[:max_output_chars] if max_output_chars > 0 else final_response,
        "exit_code": 0,
        "total_output_bytes": len(final_response),
        "truncated": max_output_chars > 0 and len(final_response) > max_output_chars,
        "spawned_session_id": spawned_session_id,
    }
```

### 5.3 Helper: `_setup_worker_logging`

```python
def _setup_worker_logging(prefix: str = ""):
    """Configure per-worker logging in child process.
    
    In a multiprocessing child, the inherited logging handlers point to
    the parent's log file. We suppress them and redirect to stdout so
    output gets captured by the parent's logging infrastructure.
    """
    import logging
    
    root = logging.getLogger()
    # Remove inherited handlers (they point to parent's file descriptor)
    for h in list(root.handlers):
        root.removeHandler(h)
    
    # Add stdout handler with the same format
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
```

### 5.4 Modified Multi-Worker Path

Replace the `ThreadPoolExecutor` block (lines 3380-3447) with:

```python
if workers > 1:
    if use_library:
        # Concurrent library mode — use multiprocessing instead of threading
        # because AIAgent cannot be safely shared across threads (GIL + state)
        try:
            import multiprocessing
            # 'spawn' avoids fork-related deadlocks with Hermes' event loop
            ctx = multiprocessing.get_context("spawn")
            
            tasks = []
            for w_id in range(workers):
                worker_goal = spawn_goal
                if len(goals_list) > 1:
                    idx = (goals_index + w_id) % len(goals_list)
                    worker_goal = goals_list[idx]
                    _log(f"[WORKER #{w_id}] Goal: {worker_goal[:100]}...")
                
                # Build prompt inside the loop (not picklable if built elsewhere)
                worker_prompt = _build_delegation_prompt(
                    iteration=iteration_count,
                    goal=worker_goal,
                    context=(f"{progressive_context}\n(worker #{w_id} of {workers})"),
                    toolsets=toolsets,
                    workdir=workdir,
                    evolve=evolve,
                    worker_id=w_id,
                    profile=profile,
                    model=model,
                    provider=provider,
                    prompt_suffix=prompt_suffix,
                    task_type=task_type,
                    prior_context=failure_context,
                )
                
                library_config = {
                    "model": model,
                    "max_iterations": max_turns,
                    "enabled_toolsets": list(toolsets),
                    "checkpoints_enabled": checkpoints,
                    "pass_session_id": pass_session_id,
                    "session_id": resume_session_id if resume_session_id else None,
                    "timeout_seconds": session_timeout,
                    "max_output_chars": max_output_chars,
                    "output_schema": output_schema,
                }
                tasks.append((library_config, worker_prompt, w_id))
            
            with ctx.Pool(processes=workers) as pool:
                results = pool.starmap(_library_worker, tasks)
            
            for r in results:
                all_results.append(r)
                
        except Exception as e:
            _log(f"[LIBRARY] Multiprocessing failed: {e}, falling back to subprocess mode")
            use_library = False  # Fall through to subprocess path below
            # Re-enter the worker dispatch with subprocess
            ...
    else:
        # Original ThreadPoolExecutor path (unchanged)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            ...
```

**Important**: `starmap` blocks until all workers complete. If a timeout per-worker is needed, use `starmap_async` with a timeout wrapper, or use `imap_unordered` with a per-result timeout.

---

## 6. Global State Risks

### 6.1 Logging (`_daemon_logger`, `_log`)

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Child process inherits parent's `RotatingFileHandler` | **HIGH** — concurrent file writes from multiple processes corrupts the log | Use `_setup_worker_logging()` to remove inherited handlers. Route child logs to stdout instead. |
| `_log()` module-level function uses global `_daemon_logger` | **MEDIUM** — child process sees `None` and falls back to `print()` | Actually safe: `_log()` already falls back to `print()` when `_daemon_logger is None` |
| Timestamps drift across processes | **LOW** — `datetime.now(timezone.utc)` is reliable | No action needed |
| Stdout interleaving (multiple workers printing) | **LOW** — each `print()` is atomic for lines < 4096 bytes | Acceptable for logging; parent collects structured results from return values |

### 6.2 File Descriptors

| Risk | Severity | Mitigation |
|------|----------|-----------|
| `fork()` + file handles (ledger, lock, log) | **HIGH** — concurrent writes corrupt: LEDGER_PATH, LOCK_PATH | Child processes should NOT write to ledger/lock. Use `multiprocessing.get_context("spawn")` to avoid fork+FD inheritance entirely. |
| Stdout/stderr capture | **LOW** — children inherit stdout | Worker function sets `_setup_worker_logging()` to clear inherited handlers |
| `FileLock` usage | **MEDIUM** — children inherit the lock FD | Children don't touch locking. The parent never holds the lock during worker execution. |

### 6.3 Signal Handlers

| Risk | Severity | Mitigation |
|------|----------|-----------|
| SIGTERM/SIGINT handler inherited by child | **LOW** — signals target the parent's PID, not child PIDs | Use `spawn` context: children get default signal dispositions. With `fork`, reset handlers in child. |
| `_shutdown_requested` global | **LOW** — child won't modify it | Child doesn't check it. Parent remains the sole reader. |

### 6.4 Hermes Core Global State

| Risk | Severity | Mitigation |
|------|----------|-----------|
| `get_hermes_home()` reads env var | **NONE** — env vars inherited by children | Safe. Each child process can read HERMES_HOME independently. |
| `hermes_config` module-level cache | **LOW** — each child builds its own cache on first import | This is the expected behavior (works in batch_runner.py). |
| Credential file handles (API keys in env/memory) | **NONE** — AIAgent re-reads config in each child | No shared credential state. |
| Plugin/Skill module cache | **NONE** — built per-process | No sharing. |

### 6.5 AIAgent Internal State

| Risk | Severity | Mitigation |
|------|----------|-----------|
| AIAgent's `_session_db` (sqlite) | **LOW** — concurrent sqlite writes could corrupt | Each child creates its own `AIAgent()`, which opens its own sqlite connection. SQLite with WAL mode supports concurrent readers but NOT concurrent writers from different processes. Use `skip_memory=True` to avoid session DB writes entirely. |
| Checkpoint file writes | **LOW** — each agent has unique session_id; files are per-session | Safe if session_ids are unique (auto-generated by AIAgent). |

### 6.6 Thread vs Process Safety Summary

```
ThreadPoolExecutor (current)              multiprocessing.Pool (proposed)
───────────────────────────────           ───────────────────────────────────
✓ No pickling needed                     ✗ Need picklable args/return values
✗ GIL-bound CPU work                     ✓ True parallelism (multiple CPUs)
✗ AIAgent not thread-safe                ✓ Each process has own AIAgent
✗ All callbacks shared                   ✓ No callback sharing issues
✓ No serialization overhead              ✗ Slightly more memory per worker
```

---

## 7. Fallback Strategy

### 7.1 When multiprocessing is Unavailable

Three scenarios require fallback:

**Scenario A: `multiprocessing` module not importable** (theoretical — it's stdlib)
- Catch `ImportError` at the import site

**Scenario B: `spawn` context not available** (some embedded Python, some BSDs)
- Fall back to `fork` context (default on Linux)

**Scenario C: Pool creation fails** (resource limits, seccomp restrictions, Docker with low pid_max)
- Fall back to sequential execution (worker-by-worker in a loop) or subprocess mode

```python
def _run_library_workers_parallel(tasks, workers):
    """Run library-mode workers in parallel using multiprocessing.
    
    Falls back gracefully if multiprocessing is unavailable.
    """
    try:
        import multiprocessing
        ctx = multiprocessing.get_context("spawn")
    except (ImportError, ValueError):
        # Fallback 1: use fork context
        try:
            import multiprocessing
            ctx = multiprocessing.get_context("fork")
        except (ImportError, ValueError):
            return _run_library_workers_sequential(tasks)
    
    try:
        with ctx.Pool(processes=min(workers, len(tasks))) as pool:
            return list(pool.starmap(_library_worker, tasks))
    except (OSError, RuntimeError) as e:
        _log(f"[LIBRARY] Pool creation failed ({e}), falling back to sequential")
        return _run_library_workers_sequential(tasks)


def _run_library_workers_sequential(tasks):
    """Run workers one at a time as a last resort fallback."""
    results = []
    for config, prompt, worker_id in tasks:
        try:
            r = _library_worker(config, prompt, worker_id)
            results.append(r)
        except Exception as e:
            results.append({
                "summary": f"WORKER #{worker_id} FAILED: {e}",
                "duration_seconds": 0,
                "error": str(e), "output": "", "exit_code": -1,
                "worker_id": worker_id,
            })
    return results
```

### 7.2 Subprocess Fallback (existing behavior)

When `_library_worker()` itself raises an exception (e.g., `ImportError` for AIAgent), the existing fallback in `spawn_delegation_session()` already handles this by catching and falling through to subprocess mode. For the multi-worker path, we add a similar catch at the task level:

```python
# In the multi-worker dispatch:
if use_library:
    try:
        # ... try multiprocessing pool ...
    except Exception:
        _log("[LIBRARY] Library mode failed in multi-worker, falling back to subprocess")
        use_library = False
        # Re-dispatch with subprocess (existing ThreadPoolExecutor path)
```

---

## 8. Implementation Plan

### 8.1 Files to Modify

**Primary**: `/home/nekophobia/.hermes/skills/software-development/infinite-loop/scripts/launch-loop.py`

### 8.2 Changes by Location

#### A. Module-level additions (~near line 200, after globals)

Add these function definitions after the `_log()` function (around line 260):

1. `_library_worker(config, prompt, worker_id) → dict` — the worker function
2. `_build_library_result(...) → dict` — result formatting helper  
3. `_setup_worker_logging(prefix)` — logging setup per child process
4. `_run_library_workers_parallel(tasks, workers) → list[dict]` — pool orchestrator
5. `_run_library_workers_sequential(tasks) → list[dict]` — fallback

#### B. CLI validation (line 4438-4443)

Remove the incompatibility warning:
```python
# BEFORE:
if args.use_library and args.workers > 1:
    _log("[WARN] --use-library is incompatible with --workers > 1. ...")
    args.use_library = False

# AFTER:
# (Nothing — --use-library is now compatible with --workers > 1)
```

Update the `--use-library` help text:
```python
parser.add_argument(
    "--use-library",
    action="store_true",
    help="Use AIAgent.run_conversation() in-process instead of spawning "
    "a subprocess. Falls back to subprocess mode automatically if the "
    "AIAgent library is not importable. Compatible with --workers > 1 "
    "(uses multiprocessing for true parallelism).",
)
```

#### C. Multi-worker path (lines 3380-3447)

Replace the `ThreadPoolExecutor` block with a conditional:

```python
if workers > 1:
    if use_library:
        # Build tasks for each worker
        tasks = []
        for w_id in range(workers):
            worker_goal = spawn_goal
            if len(goals_list) > 1:
                idx = (goals_index + w_id) % len(goals_list)
                worker_goal = goals_list[idx]
                _log(f"[WORKER #{w_id}] Goal: {worker_goal[:100]}...")
            
            worker_prompt = _build_delegation_prompt(
                iteration=iteration_count,
                goal=worker_goal,
                context=(f"{progressive_context}\n(worker #{w_id} of {workers})"),
                toolsets=toolsets, workdir=workdir,
                evolve=evolve, worker_id=w_id,
                profile=profile, model=model, provider=provider,
                prompt_suffix=prompt_suffix, task_type=task_type,
                prior_context=failure_context,
            )
            library_config = {
                "model": model,
                "max_iterations": max_turns,
                "enabled_toolsets": list(toolsets),
                "checkpoints_enabled": checkpoints,
                "pass_session_id": pass_session_id,
                "session_id": resume_session_id or None,
                "timeout_seconds": session_timeout,
                "max_output_chars": max_output_chars,
                "output_schema": output_schema,
            }
            tasks.append((library_config, worker_prompt, w_id))
        
        all_results = _run_library_workers_parallel(tasks, workers)
    else:
        # Original ThreadPoolExecutor path
        with ThreadPoolExecutor(max_workers=workers) as executor:
            ...
else:
    # Single execution path (unchanged)
    ...
```

#### D. Single-execution path (lines 3448-3495, the `else` block)

This path is unchanged. When `workers=1` and `use_library=True`, the existing `spawn_delegation_session()` handles it perfectly via the library mode check at line 2500.

### 8.3 What Stays Unchanged

- `spawn_delegation_session()` function signature and body (except removing `use_library and worker_id is None` constraint at line 2500)
- `_build_delegation_prompt()` function
- All subprocess-only flags and their handling
- Result merging logic (lines 3497+)
- Daemon loop, webhook, dashboard, notifications, convergence detection

### 8.4 Changes to `spawn_delegation_session()` Line 2500

The constraint `if use_library and worker_id is None` must be relaxed to just `if use_library`. Child processes never enter this function in the new design (they call `_library_worker` directly), but for the single-worker path the library mode should continue to work when `worker_id=None`:

```python
# BEFORE:
if use_library and worker_id is None:

# AFTER:
if use_library:
    # Note: In multi-worker mode (workers > 1), library mode is handled
    # directly by _library_worker() — this path is for single-execution only.
```

---

## 9. Edge Cases & Gotchas

### 9.1 Timeout Handling

With `multiprocessing.Pool.starmap()`, there's no built-in per-call timeout. Options:

**Option A**: Use `starmap_async(timeout=N)` — applies to the entire batch, not per worker.
**Option B**: Use `pool.imap_unordered(tasks, timeout=N)` — timeout per chunk.
**Option C (recommended)**: Wrap each worker call with a timeout in the worker itself:

```python
def _library_worker(config, prompt, worker_id):
    import multiprocessing as mp
    import queue
    
    result_queue = mp.Queue()
    proc = mp.Process(target=_worker_target, args=(config, prompt, worker_id, result_queue))
    proc.start()
    proc.join(timeout=config.get("timeout_seconds", 7200))
    
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
        return {"summary": f"WORKER #{worker_id} TIMEOUT", "error": "timeout", ...}
    
    return result_queue.get()
```

**Simpler approach** (uses timeouts in `pool.starmap_async`):
```python
with ctx.Pool(processes=workers) as pool:
    async_result = pool.starmap_async(_library_worker, tasks)
    results = async_result.get(timeout=session_timeout + 60)
```

### 9.2 Prompt Construction Timing

`_build_delegation_prompt()` uses module-level globals like `LAUNCH_LOOP_VERSION`, `BASE_TOOLSETS`, and `TASK_PATTERNS`. In child processes:

- With `fork`: globals are inherited — fine
- With `spawn`: module is re-imported, so globals exist — fine

**No issue here.**

### 9.3 `extract_json_from_output` and `validate_json_output`

These are module-level functions in `launch-loop.py`. They need to be importable in child processes. Since they're defined at module scope in the same file, they're available when the module is re-imported.

**Alternative**: Define `_build_library_result` (which calls these) as a module-level function in `launch-loop.py` using string imports.

### 9.4 Per-Process Memory

Each child process loads AIAgent + all tools + providers. This is ~200-500MB per process. With `workers=4`, expect ~1-2GB RSS. This matches the existing `batch_runner.py` behavior and is acceptable.

### 9.5 `goal` Parameter for Multi-Goal Mode

In multi-goal mode (`goals_list`), each worker gets the next goal from the list cyclically. The prompt is built per-worker (includes the worker's specific goal), so `_library_worker` receives the fully-formed prompt string — it doesn't know about goals at all. This is correct by design.

### 9.6 Python Version Compatibility

`multiprocessing` is stdlib and available in Python 3.8+. `get_context("spawn")` is available since Python 3.4. The `launch-loop.py` already uses stdlib-only imports (no external deps). No issues.

### 9.7 Windows Compatibility

The infinite-loop skill is documented as Linux-first (uses `fcntl`, `signal`, POSIX `flock`). However, `multiprocessing.get_context("spawn")` works on Windows too (it's the default there). No regressions on the target platform.

---

## 10. Summary

### Verdict: **FEASIBLE** — Medium effort (~100-150 LOC changed)

| Aspect | Assessment |
|--------|-----------|
| **AIAgent picklability** | Not picklable — create from scratch per process (proven pattern from `batch_runner.py`) |
| **Serializable params** | ~8 params needed (all strings/ints/bools/lists/dicts) |
| **Worker function design** | Module-level `_library_worker(config, prompt, worker_id) → dict` |
| **Global state risks** | Logging file handles (mitigated with `_setup_worker_logging`), ledger/lock FDs (mitigated by using `spawn` context) |
| **Fallback** | Sequential execution → subprocess mode (existing) |
| **Timeout handling** | Need wrapper in worker or `starmap_async(timeout=...)` |
| **batch_runner.py precedent** | Yes — uses identical pattern successfully |

### Key Design Decisions

1. **DO NOT import AIAgent at module level** in launch-loop.py — import it inside `_library_worker()` (lazy import per process)
2. **USE `multiprocessing.get_context("spawn")`** — avoids fork-related FD inheritance issues
3. **DO refactor result formatting** into `_build_library_result()` — shared between single-worker and multi-worker library paths
4. **KEEP single-worker path unchanged** — `spawn_delegation_session()` at line 2500 library mode still works for `workers=1`; only the multi-worker path changes
5. **DO NOT touch `_log()` or `_daemon_logger`** — children print to stdout, parent collects via return values

### Files to Modify

| File | Change |
|------|--------|
| `launch-loop.py` ≈ line 200 | Add `_library_worker()`, `_build_library_result()`, `_setup_worker_logging()`, `_run_library_workers_parallel()`, `_run_library_workers_sequential()` |
| `launch-loop.py` line 2500 | Relax `if use_library and worker_id is None` to `if use_library` |
| `launch-loop.py` lines 3380-3447 | Replace multi-worker `ThreadPoolExecutor` block with conditional (library + subprocess branches) |
| `launch-loop.py` line 4438-4443 | Remove `--use-library` + `--workers > 1` incompatibility check |
| `launch-loop.py` line 4273-4275 | Update `--use-library` help text |
| `--help` output (auto) | Updated help text reflects new compatibility |
