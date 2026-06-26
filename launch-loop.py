#!/usr/bin/env python3
VERSION = "14.2.0"
"""
launch-loop.py — Infinite loop daemon v14.2.0

v14.2.0 changes:
  - Makefile — convenience targets (run, dry-run, self-test, lint, status,
    stop, clean) for faster common operations
  - CONTRIBUTING.md — onboarding guide for new contributors with setup,
    workflow, code style, and troubleshooting
  - Improved run.sh --help — organized sections with quick reference for
    ledger, status, stop/pause/resume, and dashboard commands
  - run.sh --self-test and --version support — new CLI passthrough flags
  - SSE broadcast fix — added missing 'global _sse_clients' declaration in
    _broadcast_to_sse_clients() to prevent UnboundLocalError crash
  - Banner and version bumps across all entrypoints to v14.2.0

v14.1.0 changes:
  - P0: Dashboard XSS Fix — Replaced innerHTML string interpolation with
    createElement + textContent in SSE dashboard's addIterationRow().
    Eliminates DOM-based XSS from spawned session output.
  - P1: Dashboard Error Panel — Error type count cards (timeout, network,
    schema, unknown) with color-coded left-border accents and active
    mitigation tags. Populated via _build_sse_payload() from state.
  - P1: Dashboard Performance Metrics — Avg turns, estimated tokens/iter,
    cost estimate, iters/goal metric cards on SSE dashboard.
  - P1: Dashboard Goals Visualization — Per-goal status with progress bar,
    checkmark/play/pending indicators, scrollable list (max 30 visible).
    Populated from goals_specs + goals_completed via SSE payload.
  - P2: False Convergence Guard — _detect_convergence() skips Jaccard
    similarity check when combined summary is < 20 chars. Prevents false
    convergence stops from empty/error summaries.
  - P3: --quiet mode for run-loop.sh — New --quiet/-q flag suppresses the
    ASCII banner and startup info in CI/CD and scripted use.
  - Function Decomposition Phase 2 (P0): extracted _execute_iteration(),
    _merge_worker_results(), and _handle_backoff() from run_loop().
    run_loop() shrunk by ~250 more lines (total ~450 lines removed from v12.0.0).
  - Function Decomposition Phase 3 (P0): extracted _detect_convergence(),
    _compact_summaries(), _build_iteration_record(), _handle_notifications(),
    and _handle_callbacks() from the run_loop() post-processing chain.
    run_loop() shrunk by another ~220 lines.
  - Self-Test Mode (P1): --self-test flag runs ~40 in-process tests across 8
    daemon functions (extract_json_output, classify_error, text_similarity,
    check_convergence, validate_json_output, calc_adaptive_cooldown,
    GoalSpec, _classify_progress) with individual sub-test reporting.
  - Output Progress Classification (P1): _classify_progress() categorizes each
    iteration as 'completed', 'progress', 'partial', 'stuck', 'regression',
    or 'unknown' based on summary text, git diff changes, and error state.
    Stored in the ledger as 'classification' field on each iteration record.
  - Idempotent Goal Execution (P2): --track-goals and --reset-goals flags.
    When --track-goals is set with --goals-file, completed goals are tracked
    in the ledger via goal hash and automatically skipped on restart.
    --reset-goals clears the completion tracking for a fresh run.

v12.0.0 changes:
  - Concurrent Library Mode (P0): --use-library now works with --workers > 1
    via multiprocessing.Pool (replaces ThreadPoolExecutor).
    Each worker creates a fresh AIAgent in its own process.
    Automatic fallback to sequential if multiprocessing is unavailable.
  - Automatic Error Recovery (P1): _adapt_to_error() provides behavioral
    mitigation based on error type and history. 3 consecutive timeouts
    → double session_timeout. 2 network errors → force cooldown 120s.
    5 unknown errors → force subprocess for 10 iterations.
  - In-Process Ledger Archiving (P1): --archive-dir, --archive-retention,
    --archive-max-size flags. Trimmed iterations are auto-archived to
    gzip-compressed JSONL files before discarding.
    Archive dir: ~/.hermes/infinite-loop-archives/ by default.
  - Multi-Profile Goals File (P2): pipe-separated format in --goals-file
    supports per-goal profile/model/provider overrides.
    Format: goal|profile|model|provider
  - Function Decomposition Phase 1 (P2): extracted _load_goals_file(),
    _log_startup_banner(), _cycle_goal(), _build_progressive_context(),
    and _handle_cooldown() from run_loop(). run_loop() shrunk by ~200 lines.
  - New argparse flags: --archive-dir, --archive-retention, --archive-max-size

THE CORRECT WAY TO LOOP AND DELEGATE:
  This is the PRIMARY mode of the infinite-loop skill. It actually loops and
  actually delegates — each spawned Hermes session uses `chat -q` (non-oneshot)
  with BOTH real tools AND the delegation toolset, so spawned sessions can
  do direct work AND call delegate_task() for parallel sub-tasks.

HOW THIS WORKS:
  Run via `terminal(background=true)`. Each iteration spawns
  `hermes chat -q "<prompt>" -t terminal,file,delegation,... -Q --max-turns N`
  as a subprocess — a Hermes session with terminal, file, AND delegation
  tools (plus task-specific extras via auto-toolsets). The spawned session
  stays alive for multiple turns (not oneshot -z), so delegate_task()
  subagent results can arrive and be collected.

  Default toolsets: terminal,file,delegation,web,skills,browser,memory,
  session_search,code_execution,todo,vision

  v11.12.0 changes:
  - Session Chaining (--resume): chain spawned sessions across iterations by
    passing --resume SESSION_ID to each new spawned session. Requires --pass-session-id.
    The previous iteration's spawned_session_id is stored in state as resume_session_id
    and passed to the next iteration's spawned session.
  - Skills Flag (--skills): pass -s SKILLS to spawned hermes chat -q to preload
    specific skills (comma-separated or repeat flag). Subprocess mode only.
  - Ignore Rules Flag (--ignore-rules): start spawned sessions without loading
    AGENTS.md, memory, or rules (clean-slate mode).
  - Session ID History (session_id_history): rolling list of spawned_session_id
    values stored in the ledger state (last 100 entries), enabling audit and
    traceability across iterations.

  v11.13.0 changes:
  - YOLO mode (--yolo): passes --yolo to spawned sessions to bypass approval prompts
    for fully autonomous operation. Combine with --ignore-rules for max autonomy.
  - Ignore user config (--ignore-user-config): starts spawned sessions without
    loading ~/.hermes/config.yaml, falling back to built-in defaults.
  - Source tagging (--spawn-source): tags spawned sessions with a custom source
    label for filtering (default: 'infinite-loop').

  v11.11.0 changes:
  - AIAgent Library Mode (--use-library): run AIAgent.run_conversation() in-process
    instead of spawning a subprocess. Eliminates subprocess overhead, provides
    direct access to session_id, token usage, and cost data. Falls back to
    subprocess mode automatically if AIAgent is not importable.
  - Session Tracking (--pass-session-id): passes --pass-session-id to spawned
    sessions. The daemon extracts the session_id line from spawned stdout and
    stores it in the ledger as spawned_session_id. In library mode, obtained
    directly from the AIAgent object.
  - Checkpoints Flag (--checkpoints): enables file checkpoints in spawned
    sessions. Auto-enabled when --git is set.

  v11.10.0 changes:
  - Fixed output_cap undefined variable in worker URL mode (was using hacky 'in dir()' fallback)
  - Updated all DAEMON/startup banners to reflect v11.9.0 features (push notifications)
  - HTML dashboard now dynamically displays version from VERSION constant (no more hardcoded v11.8.0)
  - Added {VERSION} placeholder to dashboard footer and header, replaced at render time
  - DAEMON log banner now lists all current features: push notifications, preflight, API, etc.

  v11.9.0 changes:
  - Pushbullet mobile notifications: --notify-pushbullet TOKEN sends iteration
    results to your phone via Pushbullet API v2 (stdlib urllib only)
  - ntfy push notifications: --notify-ntfy TOPIC sends pushes via ntfy.sh or
    self-hosted ntfy server (stdlib urllib only)
  - Unified notification dispatcher: _send_per_iteration_notifications() sends
    to ALL configured channels (desktop, Pushbullet, ntfy) in a single call
  - Completion notification now uses all channels when Pushbullet/ntfy set
  - Removed dead code: old _send_completion_notification replaced with unified version

  v11.7.0 changes:
  - Daemon status API: GET /api/status at the webhook port returns full
    iteration state as JSON, enabling external monitoring and integration
  - Desktop notifications: --notify-desktop flag sends iteration results
    to the system notification daemon via notify-send (Linux)
  - Config file support: --save-config and --config flags for persisting
    and reloading daemon configurations as JSON files
  - Startup delay: --startup-delay N waits N seconds before the first
    iteration, useful for debugging and coordination with external services
  - Pager/event notification mode: --notify-on-completion sends a summary
    notification when the daemon finishes (success, error, convergence, etc.)
  - Error classification: iteration errors are classified as network,
    timeout, schema, or unknown in the ledger for better diagnostics
  - TASK_PATTERNS keywords expanded: 50+ new keywords for better task-type
    auto-detection across all categories (research, code-fix, system-admin,
    data-processing, content)
  - Full options summaries in --help output for all 45+ flags

  v11.8.0 changes:
  - /api/status endpoint: GET /api/status returns the COMPLETE ledger state dict
  - REST API control endpoints: POST /control/stop, /control/pause, /control/resume
  - Preflight health checks: --preflight and --preflight-fail-fast flags
  - Status dashboard improvements: auto-refresh (30s), SVG favicon, system resource
    cards (CPU/memory), ETA column, cooldown indicator, dark/light mode,
    compact summary-only mode

  v11.6.1 bug fixes:
  - Fixed missing logging.handlers import (crash with --log-file)
  - Fixed os.sysconf_names KeyError on some Python builds
  - Updated docstring to match actual default toolsets
  - Added missing 7 CLI flags to run-loop.sh wrapper
  - Stored output_schema config in ledger

  v11.0.0 changes:
  - Multi-line JSON parser: robust brace-counting extraction handles wrapped
    JSON (code fences, line breaks in JSON) — no more fragile single-line scan
  - Configurable --max-turns: spawned sessions get the turn budget they need
  - Pause/Resume sentinel: write "pause" to the sentinel file to suspend the
    loop; write "resume" to continue. Write "stop" to terminate.
  - Stderr captured per iteration: spawned session stderr is recorded in the
    ledger for debugging rate-limits, model-load warnings, etc.
  - session_id lines filtered: the trailing "session_id: <uuid>" from chat -q
    is explicitly stripped before JSON parsing
  - Throughput stats: output_chars, chars_per_second tracked in ledger

  v10.0.0 changes:
  - Switched from `hermes -z` (oneshot) to `hermes chat -q` (non-interactive query)
  - Added `delegation` to default toolsets — spawned sessions can delegate
  - With `chat -q --max-turns 90`, sessions stay alive for subagent results
  - Parallel workers now also include delegation tools
  - The spawned session has REAL tools + delegate_task() — best of both worlds

How the work flows:
  1. You run this script via terminal(background=true)
  2. On each iteration, it spawns `hermes chat -q -t terminal,file,delegation ...`
  3. The spawned Hermes has terminal + file + delegation tools
  4. It can do work directly OR delegate subtasks via delegate_task()
  5. It stays alive for multiple turns (unlike -z), so subagent results arrive
  6. It prints JSON summary with what it actually did → daemon parses it → loops

Usage:
  python3 scripts/launch-loop.py --goal "refactor auth module to use JWT" \
      --context "Code in src/auth/. Respond in English." \
      --workdir /path/to/project --git --evolve --run

Stop:
  echo "stop" > /tmp/infinite-loop-stop

Pause/Resume:
  echo "pause" > /tmp/infinite-loop-stop
  echo "resume" > /tmp/infinite-loop-stop
"""

LAUNCH_LOOP_VERSION = VERSION  # alias for backward compatibility

import argparse
import fcntl
import gzip
import http.server
import io
import json
import logging
import logging.handlers
import multiprocessing
import os
import pathlib
import re
import select
import shlex
import shutil
import signal
import socketserver
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

LEDGER_PATH = "/tmp/infinite-loop-state.json"
LOCK_PATH = "/tmp/infinite-loop-state.lock"
SENTINEL_PATH_DEFAULT = "/tmp/infinite-loop-stop"
STATUS_FILE_DEFAULT = ""  # no status file by default
HERMES_SESSION_TIMEOUT = 7200
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

# Convergence detection defaults
DEFAULT_CONVERGENCE_WINDOW = 5
DEFAULT_CONVERGENCE_THRESHOLD = 0.9

# Flag set by signal handler for graceful shutdown
_shutdown_requested = False
_daemon_logger = None  # Set during init
# References to current state for signal-safe ledger write
_shutdown_state_ref: dict | None = None

# SSE (Server-Sent Events) client tracking for live dashboard
_sse_clients: list[queue.Queue] = []
_sse_clients_lock = threading.Lock()


def _handle_shutdown(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True
    # Signal-safe write: immediately persist the current ledger state so
    # mid-subprocess SIGTERM/SIGINT doesn't lose data. We write to a
    # temporary file then atomically rename, which is signal-safe on POSIX.
    state = _shutdown_state_ref
    if state is not None:
        state["status"] = f"stopped: signal-{signum}"
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        try:
            tmp_path = LEDGER_PATH + ".sigterm.tmp"
            with open(tmp_path, "w") as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(tmp_path, LEDGER_PATH)
        except Exception:
            pass  # Best-effort in signal handler


signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)


# ---------------------------------------------------------------------------
# File locking (POSIX flock)
# ---------------------------------------------------------------------------


class FileLock:
    def __init__(self, path: str = LOCK_PATH, timeout: float = 10.0):
        self.path = path
        self.timeout = timeout
        self._fd: int | None = None

    def __enter__(self):
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return self
            except (IOError, OSError):
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise TimeoutError(
                        f"Could not acquire lock on {self.path} within {self.timeout}s"
                    )
                time.sleep(0.1)

    def __exit__(self, *args):
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)
    if _daemon_logger is not None:
        log_level = getattr(logging, level.upper(), logging.INFO)
        _daemon_logger.log(log_level, msg)


def _init_logger(log_file: str, max_mb: int = 10) -> logging.Logger:
    """Initialize a file logger with size-based rotation.

    Args:
        log_file: Path to the log file.
        max_mb: Max size in MB before rotation (old file gets .1 suffix).
    """
    logger = logging.getLogger("infinite-loop")
    logger.setLevel(logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_mb * 1024 * 1024, backupCount=1
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    logger.addHandler(handler)
    return logger


# ---------------------------------------------------------------------------
# Daemon log file management
# ---------------------------------------------------------------------------


def _init_daemon_log(log_file: str, max_mb: int = 10) -> logging.Logger:
    """Initialize logging to file. Must be called before the main loop."""
    global _daemon_logger
    log_dir = os.path.dirname(os.path.abspath(log_file))
    os.makedirs(log_dir, exist_ok=True)
    _daemon_logger = _init_logger(log_file, max_mb)
    _log(f"[LOG] Logging to {log_file} (max {max_mb}MB, rotation on overflow)")
    return _daemon_logger


# ---------------------------------------------------------------------------
# Goal completion tracking helpers (Idempotent Goal Execution)
# ---------------------------------------------------------------------------


def _goal_hash(goal_text: str) -> str:
    """Return a deterministic short hash of a goal text."""
    import hashlib

    return hashlib.md5(goal_text.encode()).hexdigest()[:16]


def _is_goal_completed(state: dict, goal_text: str) -> bool:
    """Check if a goal has already been marked completed in the ledger."""
    gh = _goal_hash(goal_text)
    completed = state.setdefault("goals_completed", {})
    return gh in completed and completed[gh].get("status") == "completed"


def _mark_goal_completed(state: dict, goal_text: str, iteration_num: int):
    """Mark a goal as completed in the ledger state (in-memory only)."""
    gh = _goal_hash(goal_text)
    completed = state.setdefault("goals_completed", {})
    completed[gh] = {
        "status": "completed",
        "iteration": iteration_num,
        "goal": goal_text[:200],
    }
    state["goals_completed"] = completed  # ensure serialization


# ---------------------------------------------------------------------------
# Function decomposition helpers (extracted from run_loop)
# ---------------------------------------------------------------------------


def _load_goals_file(goals_file: str, goal: str) -> list[tuple[str, str, str, str]]:
    """Parse goals file with GoalSpec support.

    Returns a list of (goal, profile, model, provider) tuples.
    Empty fields fall back to daemon-level CLI defaults.
    """
    result: list[tuple[str, str, str, str]] = [(goal, "", "", "")]
    if not goals_file:
        return result
    try:
        with open(goals_file) as gf:
            raw_lines = gf.read().strip().split("\n")
        parsed: list[tuple[str, str, str, str]] = []
        for ln in raw_lines:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if "|" in ln:
                parts = ln.split("|", 3)
                parsed.append(
                    (
                        parts[0].strip(),
                        parts[1].strip() if len(parts) > 1 and parts[1].strip() else "",
                        parts[2].strip() if len(parts) > 2 and parts[2].strip() else "",
                        parts[3].strip() if len(parts) > 3 and parts[3].strip() else "",
                    )
                )
            else:
                parsed.append((ln, "", "", ""))
        if parsed:
            result = parsed
            _log(f"[GOALS] Loaded {len(result)} goals from {goals_file}")
            _log(f"[GOALS] First goal: {result[0][0][:100]}")
    except (FileNotFoundError, IOError) as e:
        _log(f"[GOALS] WARN: Could not read {goals_file}: {e}")
    return result


def _log_startup_banner(
    task_type: str,
    task_type_desc: str,
    profile: str,
    model: str,
    max_retries: int,
    max_turns: int,
    tag: str,
    goal: str,
    toolsets: list[str],
    evolve: bool,
    git: bool,
    git_commit: bool,
    workers: int,
    session_timeout: int,
    notify_cmd: str | None,
    use_library: bool,
    pass_session_id: bool,
    checkpoints: bool,
    output_schema: dict | None,
    cooldown_mode: str,
    cooldown: int,
    convergence_stop: bool,
    convergence_window: int,
    convergence_threshold: float,
    store_git_diff: bool,
    track_goals: bool = False,
    reset_goals: bool = False,
    heartbeat_timeout: int = 0,
) -> None:
    """Log the startup banner (35 lines of DAEMON status info)."""
    _log(f"[DAEMON] PID={os.getpid()}")
    _log(f"[DAEMON] ledger={LEDGER_PATH}")
    _log(f"[DAEMON] sentinel={SENTINEL_PATH_DEFAULT}")
    _log(f"[DAEMON] workdir={os.getcwd()}")
    _log(
        f"[DAEMON] v{LAUNCH_LOOP_VERSION} -- Dashboard XSS Fix, Error Panel, "
        "Performance Metrics, Goals Visualization, "
        "Function Decomposition Phase 2 & 3, "
        "Self-Test Mode, Output Progress Classification, "
        "Idempotent Goal Execution, Concurrent Library Mode, "
        "Automatic Error Recovery, In-Process Archiving, "
        "Multi-Profile Goals File, GoalSpec pipe syntax, YOLO mode, "
        "clean-slate mode, AIAgent library, session tracking, checkpoints, "
        "session chaining, skills preloading, safe-mode, accept-hooks, "
        "worktree, continue, Pushbullet & ntfy push, preflight, "
        "/api/status, REST control, dashboard v2, dashboard v3 SSE, "
        "session self-healing heartbeat, config file, "
        "desktop notifications, startup delay, error classification, "
        "convergence detection, adaptive cooldown, "
        "context propagation, self-modification awareness"
    )
    _log(f"[DAEMON] Task type: {task_type} ({task_type_desc})")
    _log(f"[DAEMON] Profile: {profile or '(default)'}, Model: {model or '(default)'}")
    _log(
        f"[DAEMON] Max retries: {max_retries}, Max turns: {max_turns}, Tag: {tag or '(none)'}"
    )
    _log(f"[DAEMON] Goal: {goal}")
    _log(f"[DAEMON] Toolsets: {toolsets}")
    _log(f"[DAEMON] Evolve: {evolve}, Git: {git}, Git-commit: {git_commit}")
    _log(f"[DAEMON] Workers: {workers}, Session timeout: {session_timeout}s")
    _log(f"[DAEMON] Notify: {notify_cmd or 'none'}")
    _log(
        f"[DAEMON] Library mode: {'yes' if use_library else 'no'}, "
        f"Session ID: {'yes' if pass_session_id else 'no'}, "
        f"Checkpoints: {'yes' if checkpoints else 'no'}"
    )
    if output_schema:
        _log(
            f"[DAEMON] Output schema: {len(json.dumps(output_schema))} bytes, "
            "validating spawned output"
        )
    if cooldown_mode == "adaptive":
        _log("[DAEMON] Cooldown: adaptive (auto-calculated from iteration duration)")
    else:
        _log(f"[DAEMON] Cooldown: {cooldown}s ({cooldown_mode})")
    if convergence_stop:
        _log(
            f"[DAEMON] Convergence: stop if {convergence_window} consecutive "
            f"similar iterations (threshold={convergence_threshold})"
        )
    if store_git_diff:
        _log("[DAEMON] Git diff storage: enabled (capped at 10KB)")
    if track_goals:
        _log(
            f"[DAEMON] Goal tracking: enabled (reset={reset_goals}) — "
            "completed goals will be skipped on restart"
        )
    if heartbeat_timeout > 0:
        _log(
            f"[DAEMON] Heartbeat: enabled (timeout={heartbeat_timeout}s, "
            f"grace={heartbeat_timeout * 2}s, total window={heartbeat_timeout * 3}s)"
        )
    _log("")


def _cycle_goal(
    goals_list: list, goals_index: int, stop_at_goals_end: bool
) -> tuple[str, bool]:
    """Cycle to next goal from multi-goal list.

    Returns (current_goal_text_or_empty_string, should_stop).
    If should_stop is True, goals are exhausted and the caller should stop.
    If no cycling is needed (single goal), returns ('', False) and the
    caller should use the primary goal.
    """
    if len(goals_list) <= 1:
        return ("", False)
    idx = goals_index % len(goals_list)
    spec = goals_list[idx]
    if hasattr(spec, "goal"):
        goal_text = spec.goal  # GoalSpec object
    elif isinstance(spec, tuple):
        goal_text = spec[0]  # (goal, profile, model, provider) tuple
    else:
        goal_text = str(spec)
    if stop_at_goals_end and goals_index > len(goals_list):
        _log("[GOALS] Exhausted all goals (stop_at_goals_end=True). Stopping.")
        return ("", True)
    _log(f"[GOALS] Goal: {goal_text[:120]}...")
    return (goal_text, False)


def _build_progressive_context(context: str, summaries: list[str]) -> str:
    """Build progressive context from past summaries."""
    progressive_context = context
    if summaries:
        recent = summaries[-3:]
        progressive_context += f"\n\n[Previous iterations: {' | '.join(recent)}]"
    return progressive_context


def _handle_cooldown(
    cooldown: int,
    cooldown_mode: str,
    eta_tracker,
    task_type: str,
) -> None:
    """Fixed or adaptive cooldown wait.

    Only sleeps; does not track errors or shutdown in this function.
    """
    global _shutdown_requested
    if cooldown <= 0 and cooldown_mode != "adaptive":
        return
    effective_cooldown = cooldown
    if cooldown_mode == "adaptive":
        avg_dur = eta_tracker.avg_duration(task_type)
        effective_cooldown = calc_adaptive_cooldown(avg_dur)
        if effective_cooldown != cooldown:
            _log(
                f"[COOLDOWN] Adaptive: {effective_cooldown}s "
                f"(avg iter={avg_dur:.0f}s)"
            )
    if effective_cooldown > 0:
        _log(f"[COOLDOWN] Waiting {effective_cooldown}s before next iteration...")
        elapsed_cd = 0
        while elapsed_cd < effective_cooldown:
            if _shutdown_requested:
                break
            time.sleep(1)
            elapsed_cd += 1


# ---------------------------------------------------------------------------
# Concurrent Library Mode — multiprocessing workers for --use-library
# ---------------------------------------------------------------------------


def _setup_worker_logging(prefix: str = "") -> None:
    """Configure per-worker logging in child process.

    In a multiprocessing child, the inherited logging handlers point to
    the parent's log file. We suppress them and redirect to stdout so
    output gets captured by the parent's logging infrastructure.
    """
    import logging as _logging

    root = _logging.getLogger()
    # Remove inherited handlers (they point to parent's file descriptor)
    for h in list(root.handlers):
        root.removeHandler(h)
    # Add stdout handler with the same format
    handler = _logging.StreamHandler(sys.stdout)
    handler.setFormatter(_logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root.addHandler(handler)
    root.setLevel(_logging.DEBUG)


def _build_library_result(
    conv_result: dict,
    final_response: str,
    spawned_session_id: str,
    elapsed: float,
    max_output_chars: int,
    output_schema: dict | None,
) -> dict:
    """Build the result dict from an AIAgent conversation result."""
    parsed_json = extract_json_from_output(final_response)

    if parsed_json:
        result_obj = {
            "summary": parsed_json.get("summary", final_response[:max_output_chars]),
            "duration_seconds": parsed_json.get("duration_seconds", round(elapsed, 1)),
            "error": parsed_json.get("error"),
            "next_goal": parsed_json.get("next_goal"),
            "context": parsed_json.get("context", final_response[:500]),
            "output": (
                final_response[:max_output_chars]
                if max_output_chars > 0
                else final_response
            ),
            "stderr": "",
            "exit_code": 0,
            "total_output_bytes": len(final_response),
            "truncated": max_output_chars > 0
            and len(final_response) > max_output_chars,
            "spawned_session_id": spawned_session_id,
        }
        if output_schema:
            schema_valid, schema_error = validate_json_output(
                parsed_json, output_schema
            )
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
        "summary": (
            final_response[:max_output_chars] if final_response else "(no output)"
        ),
        "duration_seconds": round(elapsed, 1),
        "error": None,
        "output": (
            final_response[:max_output_chars]
            if max_output_chars > 0
            else final_response
        ),
        "exit_code": 0,
        "total_output_bytes": len(final_response),
        "truncated": max_output_chars > 0 and len(final_response) > max_output_chars,
        "spawned_session_id": spawned_session_id,
    }


def _library_worker(config: dict, prompt: str, worker_id: int) -> dict:
    """Run a single AIAgent conversation in a child process.

    Args:
        config: Flat picklable dict with AIAgent params.
        prompt: The system prompt to execute.
        worker_id: Worker index for logging.

    Returns:
        Result dict matching spawn_delegation_session() output format.
    """
    from run_agent import AIAgent  # safe: module-level import in child process

    start = time.time()
    _setup_worker_logging(f"[LIBRARY (worker #{worker_id})]")

    try:
        agent = AIAgent(
            model=config.get("model") or None,
            max_iterations=config.get("max_iterations", 500),
            enabled_toolsets=config.get("enabled_toolsets", []),
            quiet_mode=True,
            ephemeral_system_prompt=prompt,
            skip_memory=True,
            checkpoints_enabled=config.get("checkpoints_enabled", False),
            pass_session_id=config.get("pass_session_id", False),
            session_id=config.get("session_id", None),
        )
        # Run with timeout wrapper via ThreadPoolExecutor (same pattern as line 2670)
        import concurrent.futures as _cf

        try:
            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(agent.run_conversation, user_message=prompt)
                timeout_seconds = config.get("timeout_seconds", 7200)
                conv_result = future.result(timeout=timeout_seconds)
        except _cf.TimeoutError:
            elapsed = time.time() - start
            return {
                "summary": f"WORKER #{worker_id} TIMEOUT after {config.get('timeout_seconds', 7200)}s",
                "duration_seconds": round(elapsed, 1),
                "error": "timeout",
                "error_type": "timeout",
                "output": "",
                "exit_code": -1,
                "spawned_session_id": "",
                "worker_id": worker_id,
            }

        elapsed = time.time() - start
        spawned_session_id = conv_result.get("session_id", "") or getattr(
            agent, "session_id", ""
        )
        final_response = conv_result.get("final_response", "")

        return _build_library_result(
            conv_result,
            final_response,
            spawned_session_id,
            elapsed,
            config.get("max_output_chars", 2000),
            config.get("output_schema"),
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


def _run_library_workers_parallel(
    tasks: list[tuple[dict, str, int]], workers: int
) -> list[dict]:
    """Run library-mode workers in parallel using multiprocessing.

    Falls back gracefully if multiprocessing is unavailable.
    """
    try:
        import multiprocessing as _mp

        ctx = _mp.get_context("spawn")
    except (ImportError, ValueError):
        try:
            import multiprocessing as _mp

            ctx = _mp.get_context("fork")
        except (ImportError, ValueError):
            return _run_library_workers_sequential(tasks)

    try:
        with ctx.Pool(processes=min(workers, len(tasks))) as pool:
            return list(pool.starmap(_library_worker, tasks))
    except (OSError, RuntimeError, Exception) as e:
        _log(f"[LIBRARY] Pool creation failed ({e}), falling back to sequential")
        return _run_library_workers_sequential(tasks)


def _run_library_workers_sequential(tasks: list[tuple[dict, str, int]]) -> list[dict]:
    """Run workers one at a time as a last resort fallback."""
    results = []
    for config, prompt, worker_id in tasks:
        try:
            r = _library_worker(config, prompt, worker_id)
            results.append(r)
        except Exception as e:
            results.append(
                {
                    "summary": f"WORKER #{worker_id} FAILED: {e}",
                    "duration_seconds": 0,
                    "error": str(e),
                    "output": "",
                    "exit_code": -1,
                    "worker_id": worker_id,
                }
            )
    return results


# ---------------------------------------------------------------------------
# Hermes Worker Manager — auto-starts the worker as a child process
# When --worker-url=auto, the daemon spawns the worker internally.
# ---------------------------------------------------------------------------


class HermesWorkerManager:
    """Manages a Hermes MCP worker process lifecycle.

    When ``--worker-url auto`` is used, the daemon starts the worker
    as a background subprocess on a random port and kills it on shutdown.

    When ``--worker-url http://...`` is given, this manager is bypassed
    (the user manages the worker externally).

    When ``--worker-url`` is empty, the default subprocess mode is used.
    """

    WORKER_SCRIPT = os.path.expanduser("~/.hermes/plugins/hermes-mcp-worker/main.py")

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._port: int = 0

    def start(self) -> str:
        """Start the worker and return its URL. Returns '' on failure."""
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            self._port = s.getsockname()[1]
        worker_url = f"http://127.0.0.1:{self._port}"

        if not os.path.isfile(self.WORKER_SCRIPT):
            _log(
                f"[WORKER] Script not found at {self.WORKER_SCRIPT}, using direct mode"
            )
            return ""

        try:
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    self.WORKER_SCRIPT,
                    "--port",
                    str(self._port),
                    "--host",
                    "127.0.0.1",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(
                        f"{worker_url}/health", timeout=2
                    ) as resp:
                        if resp.status == 200:
                            _log(
                                f"[WORKER] Started on {worker_url} (PID={self._process.pid})"
                            )
                            return worker_url
                except Exception:
                    pass
                time.sleep(0.5)
            _log("[WORKER] Failed to start within 10s, falling back to direct mode")
            self.stop()
            return ""
        except Exception as e:
            _log(f"[WORKER] Failed to start: {e}")
            return ""

    def stop(self):
        """Kill the worker process."""
        if self._process and self._process.poll() is None:
            _log(f"[WORKER] Stopping worker (PID={self._process.pid})")
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
            self._process = None
            _log("[WORKER] Stopped")

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None


# ---------------------------------------------------------------------------
# Webhook server — lightweight HTTP server that triggers iterations
# ---------------------------------------------------------------------------


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    """Accepts POST /webhook to trigger the next iteration.

    Optional JSON body: {"goal": "override goal", "context": "override context"}
    Returns 200 with iteration state JSON on success.

    GET /status returns the current iteration state.
    GET /api/status returns the COMPLETE iteration state from the ledger (full dict).
    GET /health returns 200 when the daemon is running.

    POST /control/stop  writes "stop" to the shutdown sentinel file.
    POST /control/pause writes "pause" to the shutdown sentinel file.
    POST /control/resume deletes the shutdown sentinel file (or writes "resume").
    """

    _trigger_fn = None  # Callback set by the daemon
    _shutdown_sentinel = ""  # Path to sentinel file, set by the daemon

    def log_message(self, format, *args):
        _log(f"[WEBHOOK] {self.client_address[0]} - {format % args}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                200,
                {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()},
            )
        elif parsed.path == "/status":
            state = read_ledger()
            if state:
                stats = state.get("stats", {})
                self._send_json(
                    200,
                    {
                        "status": state.get("status", "unknown"),
                        "total_iterations": state.get("total_iterations", 0),
                        "success_count": stats.get("success_count", 0),
                        "error_count": stats.get("error_count", 0),
                        "last_updated": state.get("last_updated"),
                    },
                )
            else:
                self._send_json(200, {"status": "no_ledger"})
        elif parsed.path == "/api/status":
            state = read_ledger()
            if state:
                self._send_json(200, state)
            else:
                self._send_json(200, {"status": "no_ledger"})
        elif parsed.path == "/live":
            self._handle_sse()
        elif parsed.path == "/dashboard":
            self._serve_dashboard_html()
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/webhook":
            content_length = int(self.headers.get("Content-Length", 0))
            payload = {}
            if content_length > 0:
                try:
                    body = self.rfile.read(content_length).decode("utf-8")
                    payload = json.loads(body) if body.strip() else {}
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    self._send_json(400, {"error": f"invalid JSON: {e}"})
                    return

            trigger_fn = WebhookHandler._trigger_fn
            if trigger_fn:
                goal = payload.get("goal")
                context = payload.get("context")
                result = trigger_fn(goal=goal, context=context)
                self._send_json(200, {"triggered": True, "result": result})
            else:
                self._send_json(503, {"error": "trigger function not set"})
        elif parsed.path == "/control/stop":
            sentinel = WebhookHandler._shutdown_sentinel
            if not sentinel:
                self._send_json(503, {"error": "sentinel path not configured"})
                return
            try:
                with open(sentinel, "w") as f:
                    f.write("stop")
                self._send_json(200, {"action": "stop", "status": "sentinel_written"})
            except OSError as e:
                self._send_json(500, {"error": f"failed to write sentinel: {e}"})
        elif parsed.path == "/control/pause":
            sentinel = WebhookHandler._shutdown_sentinel
            if not sentinel:
                self._send_json(503, {"error": "sentinel path not configured"})
                return
            try:
                with open(sentinel, "w") as f:
                    f.write("pause")
                self._send_json(200, {"action": "pause", "status": "sentinel_written"})
            except OSError as e:
                self._send_json(500, {"error": f"failed to write sentinel: {e}"})
        elif parsed.path == "/control/resume":
            sentinel = WebhookHandler._shutdown_sentinel
            if not sentinel:
                self._send_json(503, {"error": "sentinel path not configured"})
                return
            try:
                if os.path.exists(sentinel):
                    os.remove(sentinel)
                self._send_json(200, {"action": "resume", "status": "sentinel_removed"})
            except OSError as e:
                self._send_json(500, {"error": f"failed to remove sentinel: {e}"})
        else:
            self._send_json(404, {"error": "not_found"})

    def _handle_sse(self):
        """Handle GET /live — Server-Sent Events stream.

        Creates a per-client Queue(maxsize=1), registers it in the module-level
        _sse_clients list, then enters a blocking loop:
          - q.get(timeout=30) → sends 'event: iteration' with JSON payload
          - queue.Empty after 30s → sends 'event: heartbeat' keepalive
        On client disconnect (BrokenPipeError / ConnectionResetError), removes
        the queue from _sse_clients in a finally block.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        q: queue.Queue = queue.Queue(maxsize=1)
        with _sse_clients_lock:
            _sse_clients.append(q)

        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    self.wfile.write(
                        f"event: iteration\ndata: {data}\n\n".encode("utf-8")
                    )
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b"event: heartbeat\ndata: {}\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # Client disconnected — thread will die
        finally:
            with _sse_clients_lock:
                try:
                    _sse_clients.remove(q)
                except ValueError:
                    pass

    def _serve_dashboard_html(self):
        """Serve the SSE-powered live dashboard HTML page."""
        html = _SSE_DASHBOARD_HTML_TPL
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _start_webhook_server(
    port: int, trigger_fn, sentinel_path: str = ""
) -> http.server.HTTPServer:
    """Start the webhook server in a daemon thread."""
    WebhookHandler._trigger_fn = trigger_fn
    WebhookHandler._shutdown_sentinel = sentinel_path
    server = ThreadedHTTPServer(("", port), WebhookHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    _log(f"[WEBHOOK] Server listening on http://0.0.0.0:{port}")
    return server


# ---------------------------------------------------------------------------
# Preflight health checks (v11.8.0)
# ---------------------------------------------------------------------------


class PreflightChecker:
    """Runs configurable preflight health checks before the loop starts.

    Checks: hermes binary, workdir existence, git repo, sentinel writable,
    port availability, context/goals file readability, schema file validity,
    disk space. Returns a list of PreflightResult dicts.

    Two modes:
      - Static: PreflightChecker.check_hermes_binary() for individual checks
      - Instance: PreflightChecker(args).run_all() for batch checks from CLI
    """

    def __init__(self, args, fail_fast: bool = False):
        """Initialize from argparse namespace."""
        self._args = args
        self._fail_fast = fail_fast

    def run_all(self) -> bool:
        """Run all preflight checks from args, log results, return True if all pass."""
        checks = [
            ("hermes binary", PreflightChecker.check_hermes_binary()),
            ("workdir", PreflightChecker.check_workdir(self._args.workdir or "")),
            (
                "sentinel writable",
                PreflightChecker.check_sentinel_writable(self._args.shutdown_sentinel),
            ),
            (
                "port available",
                PreflightChecker.check_port_available(self._args.webhook_port or 0),
            ),
            (
                "context file",
                PreflightChecker.check_file_readable(
                    self._args.context_file or "", "context-file"
                ),
            ),
            (
                "goals file",
                PreflightChecker.check_file_readable(
                    self._args.goals_file or "", "goals-file"
                ),
            ),
            (
                "schema file",
                PreflightChecker.check_schema_file(self._args.output_schema_file or ""),
            ),
        ]

        if getattr(self._args, "git", False):
            checks.append(
                ("git repo", PreflightChecker.check_git_repo(self._args.workdir or ""))
            )

        log_path = getattr(self._args, "log_file", "") or "/tmp"
        checks.append(("disk space", PreflightChecker.check_disk_space(log_path)))

        # Also check installed Hermes version (informational, not blocking)
        checks.append(("hermes version", PreflightChecker.check_hermes_version()))

        results = []
        all_pass = True
        for name, (passed, detail) in checks:
            results.append({"name": name, "passed": passed, "detail": detail})
            if not passed:
                all_pass = False
                _log(f"[PREFLIGHT] ✗ {name}: {detail[:120]}")
                if self._fail_fast:
                    _log("[PREFLIGHT] FAIL FAST — aborting.")
                    break
            else:
                _log(f"[PREFLIGHT] ✓ {name}: {detail[:120]}")

        if all_pass:
            _log("[PREFLIGHT] All checks passed.")
        else:
            failed = sum(1 for r in results if not r["passed"])
            _log(f"[PREFLIGHT] {failed} check(s) failed.")

        return all_pass

    @staticmethod
    def check_hermes_binary() -> tuple[bool, str]:
        """Check that hermes binary is on PATH and executable."""
        hermes = shutil.which("hermes")
        if hermes:
            return True, f"found at {hermes}"
        return False, "'hermes' not found on PATH"

    @staticmethod
    def check_hermes_version() -> tuple[bool, str]:
        """Check the installed Hermes version for compatibility."""
        hermes = shutil.which("hermes")
        if not hermes:
            return False, "'hermes' not on PATH — can't check version"
        try:
            r = subprocess.run(
                [hermes, "--version"], capture_output=True, text=True, timeout=10
            )
            version_line = (r.stdout or "").strip().split("\n")[0]
            return True, f"Hermes version: {version_line[:120]}"
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            return True, f"version check skipped: {e}"

    @staticmethod
    def check_workdir(wd: str) -> tuple[bool, str]:
        """Check that workdir exists and is a directory."""
        if not wd:
            return True, "no workdir specified (using current dir)"
        p = os.path.expanduser(wd)
        if not os.path.exists(p):
            return False, f"workdir '{p}' does not exist"
        if not os.path.isdir(p):
            return False, f"'{p}' is not a directory"
        return True, f"'{p}' exists"

    @staticmethod
    def check_git_repo(wd: str) -> tuple[bool, str]:
        """Check that workdir is a git repo (only when --git is set)."""
        base = os.path.expanduser(wd) if wd else os.getcwd()
        git_dir = os.path.join(base, ".git")
        if os.path.isdir(git_dir):
            return True, f".git found at {git_dir}"
        return False, "no .git directory — git features will be no-ops"

    @staticmethod
    def check_sentinel_writable(sentinel_path: str) -> tuple[bool, str]:
        """Check that sentinel parent directory is writable."""
        parent = os.path.dirname(os.path.expanduser(sentinel_path)) or "."
        if os.access(parent, os.W_OK):
            return True, f"'{parent}' is writable"
        return False, f"'{parent}' is not writable"

    @staticmethod
    def check_port_available(port: int) -> tuple[bool, str]:
        """Check if a TCP port is available."""
        if port <= 0:
            return True, "port not requested"
        try:
            import socket as _sock

            with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                s.bind(("", port))
            return True, f"port {port} is available"
        except OSError as e:
            return False, f"port {port} is in use: {e}"

    @staticmethod
    def check_file_readable(path: str, label: str) -> tuple[bool, str]:
        """Check that a file exists and is readable."""
        if not path:
            return True, f"--{label} not set"
        p = os.path.expanduser(path)
        if not os.path.isfile(p):
            return False, f"--{label} file '{p}' not found"
        if not os.access(p, os.R_OK):
            return False, f"--{label} file '{p}' not readable"
        return True, f"--{label} file '{p}' found"

    @staticmethod
    def check_schema_file(path: str) -> tuple[bool, str]:
        """Check that --output-schema-file is valid JSON."""
        if not path:
            return True, "not set"
        p = os.path.expanduser(path)
        if not os.path.isfile(p):
            return False, f"schema file '{p}' not found"
        try:
            with open(p) as f:
                json.load(f)
            return True, "valid JSON schema file"
        except (json.JSONDecodeError, IOError) as e:
            return False, f"invalid schema file: {e}"

    @staticmethod
    def check_disk_space(path: str = "/tmp", min_gb: float = 0.5) -> tuple[bool, str]:
        """Check minimum free disk space (Linux statvfs)."""
        try:
            if hasattr(os, "statvfs"):
                st = os.statvfs(os.path.dirname(os.path.abspath(path)))
                free_gb = (st.f_frsize * st.f_bavail) / (1024**3)
                if free_gb < min_gb:
                    return False, f"only {free_gb:.1f}GB free (need {min_gb}GB)"
                return True, f"{free_gb:.1f}GB free"
            return True, "unable to check (non-Linux)"
        except Exception:
            return True, "unable to check"

    @staticmethod
    def run_all(
        hermes_required: bool = True,
        workdir: str = "",
        sentinel_path: str = SENTINEL_PATH_DEFAULT,
        webhook_port: int = 0,
        context_file: str = "",
        goals_file: str = "",
        schema_file: str = "",
        check_git: bool = False,
        check_disk: str = "",
        fail_fast: bool = False,
    ) -> list[dict]:
        """Run all preflight checks and return results as list of dicts.

        Each result: {"name": str, "passed": bool, "detail": str}

        When fail_fast=True, stop on the first failure and return partial results.
        """
        checks = [
            ("hermes binary", PreflightChecker.check_hermes_binary()),
            ("workdir", PreflightChecker.check_workdir(workdir)),
            (
                "sentinel writable",
                PreflightChecker.check_sentinel_writable(sentinel_path),
            ),
            ("port available", PreflightChecker.check_port_available(webhook_port)),
            (
                "context file",
                PreflightChecker.check_file_readable(context_file, "context-file"),
            ),
            (
                "goals file",
                PreflightChecker.check_file_readable(goals_file, "goals-file"),
            ),
            ("schema file", PreflightChecker.check_schema_file(schema_file)),
        ]

        if check_git:
            checks.append(("git repo", PreflightChecker.check_git_repo(workdir)))

        if check_disk:
            checks.append(("disk space", PreflightChecker.check_disk_space(check_disk)))

        checks.append(("hermes version", PreflightChecker.check_hermes_version()))

        results = []
        for name, (passed, detail) in checks:
            results.append({"name": name, "passed": passed, "detail": detail})
            if not passed and fail_fast:
                break

        return results

    @staticmethod
    def format_results(results: list[dict]) -> str:
        """Format preflight results as a table with ✓/✗ indicators."""
        lines = ["", "--- Preflight Health Checks ---"]
        all_pass = True
        for r in results:
            icon = "✓" if r["passed"] else "✗"
            if not r["passed"]:
                all_pass = False
            detail = r["detail"][:80]
            lines.append(f"  {icon}  {r['name']}: {detail}")
        lines.append("")
        if all_pass:
            lines.append("  All checks passed.")
        else:
            lines.append(
                f"  {sum(1 for r in results if not r['passed'])} check(s) failed."
            )
        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ETA tracker — per-task-type average duration & time estimation
# ---------------------------------------------------------------------------


class ETATracker:
    """Tracks average iteration duration per task type and estimates remaining time."""

    def __init__(self):
        self._type_totals: dict[str, float] = {}
        self._type_counts: dict[str, int] = {}

    def record_iteration(self, task_type: str, duration_seconds: float):
        self._type_totals.setdefault(task_type, 0)
        self._type_totals[task_type] += duration_seconds
        self._type_counts.setdefault(task_type, 0)
        self._type_counts[task_type] += 1

    def avg_duration(self, task_type: str | None = None) -> float:
        if (
            task_type
            and task_type in self._type_counts
            and self._type_counts[task_type] > 0
        ):
            return self._type_totals[task_type] / self._type_counts[task_type]
        total = sum(self._type_totals.values())
        count = sum(self._type_counts.values())
        return round(total / count, 1) if count > 0 else 0.0

    def estimate_remaining(
        self, task_type: str, iterations_done: int, max_iterations: int
    ) -> float:
        if max_iterations <= 0:
            return 0.0
        remaining = max_iterations - iterations_done
        if remaining <= 0:
            return 0.0
        avg = self.avg_duration(task_type)
        return round(avg * remaining, 1)

    def format_eta(self, seconds: float) -> str:
        if seconds <= 0:
            return "N/A"
        if seconds >= 3600:
            return f"{seconds / 3600:.1f}h ({seconds / 60:.0f}m)"
        if seconds >= 60:
            return f"{seconds / 60:.0f}m"
        return f"{seconds:.0f}s"

    def to_dict(self) -> dict:
        return {
            "per_type": {
                tt: {
                    "avg": self.avg_duration(tt),
                    "count": self._type_counts[tt],
                }
                for tt in self._type_counts
            },
            "overall_avg": self.avg_duration(),
        }


# ---------------------------------------------------------------------------
# File watcher — poll a directory for changes and trigger iterations
# ---------------------------------------------------------------------------


class FileWatcherTrigger:
    """Poll a directory/file for modifications and trigger on change.

    Uses os.stat() polling — no external dependencies. Scans mtime of
    all files in the watched directory and triggers an iteration when
    any mtime changes.
    """

    def __init__(self, path: str, poll_interval: float = 5.0):
        self.path = path
        self.poll_interval = poll_interval
        self._last_state: dict[str, float] | None = None

    def _scan(self) -> dict[str, float]:
        """Return {filename: mtime} for all files under the watched path."""
        state = {}
        p = pathlib.Path(self.path)
        if p.is_file():
            try:
                state[self.path] = p.stat().st_mtime
            except OSError:
                pass
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    try:
                        state[str(child)] = child.stat().st_mtime
                    except OSError:
                        pass
        return state

    def check_change(self) -> bool:
        """Return True if any file has changed since last check."""
        current = self._scan()
        if self._last_state is None:
            self._last_state = current
            return True  # Initial scan counts as a "change"
        for path, mtime in current.items():
            old = self._last_state.get(path)
            if old is None or abs(mtime - old) > 0.01:
                self._last_state = current
                return True
        self._last_state = current
        return False

    def format_changed(self) -> str:
        """Human-readable list of changed files since last scan."""
        current = self._scan()
        changed = []
        for path, mtime in current.items():
            old = self._last_state.get(path)
            if old is None or abs(mtime - old) > 0.01:
                changed.append(path)
        self._last_state = current
        return ", ".join(changed[:10]) if changed else ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "poll_interval": self.poll_interval,
            "files_tracked": len(self._scan()),
        }


# ---------------------------------------------------------------------------
# JSON Schema validation — validate spawned session output against a schema
# ---------------------------------------------------------------------------


def validate_json_output(output: dict, schema: dict) -> tuple[bool, str]:
    """Validate a JSON object against a JSON Schema (draft-07 subset).

    Uses stdlib-only validation (no jsonschema dependency). Supports a
    practical subset: required fields, type checking, enum values, and
    string minLength/maxLength. Returns (is_valid, error_message).
    """
    if not schema:
        return True, ""

    def _check_type(value, expected: str, path: str) -> str | None:
        if expected == "string":
            if not isinstance(value, str):
                return f"{path}: expected string, got {type(value).__name__}"
        elif expected == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                return f"{path}: expected integer, got {type(value).__name__}"
        elif expected == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return f"{path}: expected number, got {type(value).__name__}"
        elif expected == "boolean":
            if not isinstance(value, bool):
                return f"{path}: expected boolean, got {type(value).__name__}"
        elif expected in ("array", "object"):
            # Type-based checking for nested types is limited in subset
            if not isinstance(value, dict if expected == "object" else list):
                return f"{path}: expected {expected}, got {type(value).__name__}"
        return None

    def _validate(obj, schema_node: dict, path: str) -> str | None:
        # Required fields
        required = schema_node.get("required", [])
        for field in required:
            if field not in obj:
                return f"{path}: missing required field '{field}'"

        # Type check + recursion for each defined property
        properties = schema_node.get("properties", {})
        for field, field_schema in properties.items():
            if field not in obj:
                continue
            val = obj[field]
            field_path = f"{path}.{field}" if path else field
            expected_type = field_schema.get("type")

            if expected_type:
                err = _check_type(val, expected_type, field_path)
                if err:
                    return err

            # Enum check
            enum_vals = field_schema.get("enum")
            if enum_vals is not None and val not in enum_vals:
                return f"{field_path}: expected one of {enum_vals}, got {val!r}"

            # String length checks
            if isinstance(val, str):
                min_len = field_schema.get("minLength")
                max_len = field_schema.get("maxLength")
                if min_len is not None and len(val) < min_len:
                    return f"{field_path}: min length {min_len}, got {len(val)}"
                if max_len is not None and len(val) > max_len:
                    return f"{field_path}: max length {max_len}, got {len(val)}"

            # Integer range checks
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                minimum = field_schema.get("minimum")
                maximum = field_schema.get("maximum")
                if minimum is not None and val < minimum:
                    return f"{field_path}: minimum {minimum}, got {val}"
                if maximum is not None and val > maximum:
                    return f"{field_path}: maximum {maximum}, got {val}"

            # Nested object
            if isinstance(val, dict) and "properties" in field_schema:
                err = _validate(val, field_schema, field_path)
                if err:
                    return err

        return None

    error = _validate(output, schema, "root")
    if error:
        return False, error
    return True, ""


def load_json_schema(path: str) -> dict | None:
    """Load a JSON Schema from a file path. Returns None on failure."""
    try:
        with open(path) as f:
            schema = json.load(f)
        if not isinstance(schema, dict):
            _log(f"[SCHEMA] WARN: {path} is not a JSON object, ignoring")
            return None
        return schema
    except (FileNotFoundError, json.JSONDecodeError) as e:
        _log(f"[SCHEMA] WARN: Could not load {path}: {e}")
        return None


# ---------------------------------------------------------------------------
# System resource tracking — /proc-based CPU/memory usage (stdlib only)
# ---------------------------------------------------------------------------


def get_system_usage() -> dict:
    """Read CPU and memory usage from /proc (Linux).

    Returns dict with:
      - cpu_percent: approximate CPU usage as fraction of one core (0.0+)
      - memory_rss_mb: RSS memory in MB
      - memory_vms_mb: virtual memory in MB
      - memory_percent: fraction of total RAM

    Uses stdlib only — no psutil dependency.
    """
    result: dict[str, float] = {}
    pid = os.getpid()

    # Memory from /proc/pid/status
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        result["memory_rss_mb"] = int(parts[1]) / 1024
                elif line.startswith("VmSize:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        result["memory_vms_mb"] = int(parts[1]) / 1024
                elif line.startswith("VmPeak:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        result["memory_peak_mb"] = int(parts[1]) / 1024
    except (FileNotFoundError, IOError, ValueError):
        pass

    # Total RAM
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        total_kb = int(parts[1])
                        rss_kb = result.get("memory_rss_mb", 0) * 1024
                        if total_kb > 0:
                            result["memory_percent"] = round(rss_kb / total_kb, 4)
                    break
    except (FileNotFoundError, IOError, ValueError):
        pass

    # CPU time from /proc/pid/stat (user + system ticks)
    try:
        with open(f"/proc/{pid}/stat") as f:
            stat_data = f.read()
        # Parse: field 13=utime, field 14=stime, field 21=starttime
        parts = stat_data.split(")")
        if len(parts) >= 2:
            fields = parts[1].strip().split()
            if len(fields) >= 20:
                utime = int(fields[11])
                stime = int(fields[12])
                starttime = int(fields[19])
                # Get CLK_TCK safely — os.sysconf_names may not have the key
                try:
                    clk_tck = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", 2))
                except (AttributeError, KeyError, ValueError, OSError):
                    clk_tck = 100  # Safe fallback — 100 is the Linux default
                total_ticks = utime + stime
                result["cpu_ticks_used"] = total_ticks
                result["cpu_seconds"] = total_ticks / clk_tck
    except (FileNotFoundError, IOError, ValueError, AttributeError):
        pass

    return result


def get_system_usage_diff(before: dict, after: dict) -> dict:
    """Compute system usage diff between two snapshots."""
    diff: dict = {}
    if before and after:
        cpu_b = before.get("cpu_seconds", 0)
        cpu_a = after.get("cpu_seconds", 0)
        diff["cpu_seconds_used"] = round(cpu_a - cpu_b, 3)
        diff["memory_rss_mb"] = after.get("memory_rss_mb", 0)
        diff["memory_vms_mb"] = after.get("memory_vms_mb", 0)
        diff["memory_percent"] = after.get("memory_percent", 0)
        diff["memory_peak_mb"] = after.get("memory_peak_mb", 0)
    return diff


# ---------------------------------------------------------------------------
# Text similarity for convergence detection (stdlib only)
# ---------------------------------------------------------------------------


def text_similarity(a: str, b: str) -> float:
    """Compute similarity between two strings using word overlap (Jaccard).

    Returns a float 0.0 (completely different) to 1.0 (identical).
    Uses only Python stdlib — no numpy/scikit-learn dependency.
    Handles short strings gracefully.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    # Normalize: lowercase, split into words
    import re

    words_a = set(re.findall(r"\w+", a.lower()))
    words_b = set(re.findall(r"\w+", b.lower()))

    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def check_convergence(
    summaries: list[str],
    threshold: float = DEFAULT_CONVERGENCE_THRESHOLD,
    window: int = DEFAULT_CONVERGENCE_WINDOW,
) -> tuple[bool, float]:
    """Check if the last N summaries indicate convergence.

    Returns (is_converged, avg_similarity) where is_converged is True
    when ALL pairs in the window exceed the threshold.
    """
    if len(summaries) < window:
        return False, 0.0

    recent = summaries[-window:]
    similarities = []
    for i in range(len(recent)):
        for j in range(i + 1, len(recent)):
            similarities.append(text_similarity(recent[i], recent[j]))

    if not similarities:
        return False, 0.0

    avg_sim = sum(similarities) / len(similarities)
    return avg_sim >= threshold, avg_sim


# ---------------------------------------------------------------------------
# Adaptive cooldown — dynamically adjust delay based on iteration duration
# ---------------------------------------------------------------------------


def calc_adaptive_cooldown(
    avg_duration: float,
    min_cooldown: int = 2,
    max_cooldown: int = 60,
) -> int:
    """Calculate adaptive cooldown based on iteration duration.

    Short iterations (< 30s) suggest fast cycles that may hit rate limits,
    so we apply longer cooldowns. Long iterations (> 5min) don't need
    significant cooldown since the iteration itself is slow.

    Returns cooldown in seconds (clamped to [min_cooldown, max_cooldown]).
    """
    if avg_duration <= 0:
        return min_cooldown
    if avg_duration >= 300:  # 5+ minutes
        return min_cooldown
    if avg_duration <= 5:  # Very fast — likely rate-limit sensitive
        return max_cooldown
    if avg_duration <= 15:
        return max_cooldown // 2
    # Linear interpolation between 15s and 300s
    ratio = (avg_duration - 15) / (300 - 15)
    cooldown = int(max_cooldown - ratio * (max_cooldown - min_cooldown))
    return max(min_cooldown, min(max_cooldown, cooldown))


# ---------------------------------------------------------------------------
# Status HTML dashboard — self-contained HTML page from ledger state
# ---------------------------------------------------------------------------


_STATUS_HTML_TPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>Infinite Loop Dashboard</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%99%BE%EF%B8%8F%3C/text%3E%3C/svg%3E">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root { --bg: #0d1117; --fg: #c9d1d9; --card-bg: #161b22; --border: #30363d; --border-row: #21262d; --accent: #58a6ff; --muted: #8b949e; --dim: #484f58; --err-bg: rgba(218, 54, 51, 0.1); }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --fg: #24292f; --card-bg: #ffffff; --border: #d0d7de; --border-row: #e1e4e8; --accent: #0969da; --muted: #656d76; --dim: #8b949e; --err-bg: rgba(218, 54, 51, 0.05); }
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--fg); padding: 20px; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; color: var(--accent); }
  h2 { font-size: 1.1rem; margin: 1.5rem 0 0.5rem; color: var(--muted); }
  .meta { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .meta-item { background: var(--card-bg); padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; }
  .meta-item .label { color: var(--muted); }
  .meta-item .value { color: var(--fg); font-weight: 600; }
  .status-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
  .running { background: #1f6feb; color: #fff; }
  .stopped { background: #da3633; color: #fff; }
  .paused { background: #d29922; color: #000; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); color: var(--muted); text-transform: uppercase; font-size: 0.75rem; }
  td { padding: 8px 6px; border-bottom: 1px solid var(--border-row); }
  .error-row td { background: var(--err-bg); }
  .summary { max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
  .tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; }
  .tag-ok { background: #1a3a1a; color: #3fb950; }
  .tag-err { background: #3a1a1a; color: #f85149; }
  .tag-evolve { background: #1a1a3a; color: #58a6ff; }
  .progress { height: 8px; background: var(--border); border-radius: 4px; margin: 8px 0; }
  .progress-fill { height: 8px; background: #1f6feb; border-radius: 4px; transition: width 0.3s; }
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .stat-card { background: var(--card-bg); padding: 12px; border-radius: 6px; text-align: center; }
  .stat-card .num { font-size: 1.5rem; font-weight: 700; color: var(--accent); }
  .stat-card .label { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
  .cooldown-active { color: #d29922; }
  .cooldown-idle { color: var(--muted); }
  .compact-toggle { float: right; font-size: 0.75rem; color: var(--accent); cursor: pointer; text-decoration: underline; margin-top: 1.5rem; }
  .compact-mode .meta, .compact-mode .stats-grid, .compact-mode h2, .compact-mode .progress, .compact-mode .cooldown-row, .compact-mode #iterations-table { display: none; }
  .compact-mode #summary-only { display: block; }
  #summary-only { display: none; }
</style>
</head>
<body>
<script>
function toggleCompact() {
  document.body.classList.toggle('compact-mode');
  localStorage.setItem('loop-dashboard-compact', document.body.classList.contains('compact-mode'));
}
(function() {
  if (localStorage.getItem('loop-dashboard-compact') === 'true') {
    document.body.classList.add('compact-mode');
  }
})();
</script>
<h1>&#x267E;&#xFE0F; Infinite Loop Dashboard <span style="font-size:0.7rem;color:var(--dim)">v{VERSION}</span></h1>
<div class="meta">
  <div class="meta-item"><span class="label">Status</span><br><span class="status-badge {STATUS_CLASS}">{STATUS}</span></div>
  <div class="meta-item"><span class="label">Iterations</span><br><span class="value">{TOTAL}</span></div>
  <div class="meta-item"><span class="label">Goal</span><br><span class="value">{GOAL}</span></div>
  <div class="meta-item"><span class="label">Started</span><br><span class="value">{STARTED}</span></div>
  <div class="meta-item"><span class="label">Last Updated</span><br><span class="value">{LAST_UPDATED}</span></div>
  <div class="meta-item"><span class="label">ETA</span><br><span class="value">{ETA}</span></div>
  <div class="meta-item"><span class="label">Cooldown</span><br><span class="value {COOLDOWN_CLASS}">{COOLDOWN}</span></div>
</div>

<h2>Stats <span class="compact-toggle" onclick="toggleCompact()">[toggle summary-mode]</span></h2>
<div class="stats-grid">
  <div class="stat-card"><div class="num">{SUCCESS}</div><div class="label">Success</div></div>
  <div class="stat-card"><div class="num">{ERRORS}</div><div class="label">Errors</div></div>
  <div class="stat-card"><div class="num">{TOTAL_DUR}s</div><div class="label">Total Time</div></div>
  <div class="stat-card"><div class="num">{AVG_DUR}s</div><div class="label">Avg / Iteration</div></div>
  <div class="stat-card"><div class="num">{CPU_SEC}s</div><div class="label">CPU Seconds</div></div>
  <div class="stat-card"><div class="num">{MEM_MB}MB</div><div class="label">Memory (RSS)</div></div>
  <div class="stat-card"><div class="num">{MEM_PCT}%</div><div class="label">Memory %</div></div>
</div>

{EVA_GOAL_ROW}

{PROGRESS_ROW}

<h2>Iterations</h2>
<table id="iterations-table"><thead><tr><th>#</th><th>Time</th><th>Duration</th><th>Type</th><th>Summary</th><th>ETA</th></tr></thead><tbody>
{ITER_ROWS}
</tbody></table>
<div id="summary-only">
<p style="color:var(--muted);font-size:0.85rem;">{SUMMARY_ONLY_TEXT}</p>
</div>
<p style="margin-top: 12px; font-size: 0.8rem; color: var(--dim);">Auto-generated by infinite-loop daemon v{VERSION}</p>
</body></html>"""

# SSE-powered live dashboard HTML template (no meta-refresh, uses EventSource)
_SSE_DASHBOARD_HTML_TPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Infinite Loop Dashboard (Live)</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%99%BE%EF%B8%8F%3C/text%3E%3C/svg%3E">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root { --bg: #0d1117; --fg: #c9d1d9; --card-bg: #161b22; --border: #30363d; --border-row: #21262d; --accent: #58a6ff; --muted: #8b949e; --dim: #484f58; --err-bg: rgba(218, 54, 51, 0.1); }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --fg: #24292f; --card-bg: #ffffff; --border: #d0d7de; --border-row: #e1e4e8; --accent: #0969da; --muted: #656d76; --dim: #8b949e; --err-bg: rgba(218, 54, 51, 0.05); }
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--fg); padding: 20px; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; color: var(--accent); }
  h2 { font-size: 1.1rem; margin: 1.5rem 0 0.5rem; color: var(--muted); }
  .meta { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .meta-item { background: var(--card-bg); padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; }
  .meta-item .label { color: var(--muted); }
  .meta-item .value { color: var(--fg); font-weight: 600; }
  #status-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
  .running { background: #1f6feb; color: #fff; }
  .stopped { background: #da3633; color: #fff; }
  .paused { background: #d29922; color: #000; }
  .reloading { background: #da3633; color: #fff; }
  .no_ledger { background: var(--dim); color: #fff; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); color: var(--muted); text-transform: uppercase; font-size: 0.75rem; }
  td { padding: 8px 6px; border-bottom: 1px solid var(--border-row); }
  .error-row td { background: var(--err-bg); }
  .summary { max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
  .tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; }
  .tag-ok { background: #1a3a1a; color: #3fb950; }
  .tag-err { background: #3a1a1a; color: #f85149; }
  .tag-evolve { background: #1a1a3a; color: #58a6ff; }
  .progress { height: 8px; background: var(--border); border-radius: 4px; margin: 8px 0; }
  .progress-fill { height: 8px; background: #1f6feb; border-radius: 4px; transition: width 0.3s; }
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .stat-card { background: var(--card-bg); padding: 12px; border-radius: 6px; text-align: center; }
  .stat-card .num { font-size: 1.5rem; font-weight: 700; color: var(--accent); }
  .stat-card .label { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
  #cooldown-display { font-size: 0.85rem; }
  .cooldown-active { color: #d29922; }
  .cooldown-idle { color: var(--muted); }
  .compact-toggle { float: right; font-size: 0.75rem; color: var(--accent); cursor: pointer; text-decoration: underline; margin-top: 1.5rem; }
  .compact-mode .meta, .compact-mode .stats-grid, .compact-mode h2, .compact-mode .progress, .compact-mode .cooldown-row, .compact-mode #iterations-table, .compact-mode #goals-panel, .compact-mode #error-panel, .compact-mode #metrics-panel { display: none; }
  .compact-mode #summary-only { display: block; }
  #summary-only { display: none; }
  #connection-status { font-size: 0.75rem; color: var(--muted); float: right; }
  .connected { color: #3fb950; }
  .disconnected { color: #f85149; }
  /* Error panel */
  .err-card { background: var(--err-bg); padding: 8px 12px; border-radius: 6px; font-size: 0.82rem; display: inline-block; margin: 4px 4px 0 0; }
  .err-card .num { font-weight: 700; margin-right: 4px; }
  .err-timeout { border-left: 3px solid #d29922; }
  .err-network { border-left: 3px solid #da3633; }
  .err-schema { border-left: 3px solid #a371f7; }
  .err-unknown { border-left: 3px solid var(--dim); }
  .mitigation-tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.72rem; background: #1a3a1a; color: #3fb950; margin: 2px; }
  .mitigation-active { background: #3a1a1a; color: #f85149; }
  /* Goals panel */
  .goal-row { display: flex; align-items: center; padding: 4px 0; font-size: 0.82rem; border-bottom: 1px solid var(--border-row); }
  .goal-row .gidx { color: var(--dim); width: 24px; }
  .goal-row .gstatus { width: 20px; text-align: center; margin-right: 6px; }
  .goal-row .gtext { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg); }
  .goal-done .gtext { color: var(--muted); text-decoration: line-through; }
  .goal-active .gtext { color: var(--accent); }

</style>
</head>
<body>
<h1>&#x267B;&#xFE0F; Infinite Loop <span id="connection-status" class="disconnected">&#x25CF; disconnected</span></h1>
<div class="meta" id="meta-cards">
  <div class="meta-item"><span class="label">Status</span><br><span id="status-badge" class="running">loading...</span></div>
  <div class="meta-item"><span class="label">Total Iterations</span><br><span class="value" id="total-iterations">-</span></div>
  <div class="meta-item"><span class="label">Goal</span><br><span class="value" id="goal">-</span></div>
  <div class="meta-item"><span class="label">Evolved Goal</span><br><span class="value" id="evolved-goal">-</span></div>
  <div class="meta-item"><span class="label">Started At</span><br><span class="value" id="started-at">-</span></div>
  <div class="meta-item"><span class="label">Last Updated</span><br><span class="value" id="last-updated">-</span></div>
</div>

<div class="stats-grid" id="stats-grid">
  <div class="stat-card"><div class="num" id="stat-success">-</div><div class="label">Success</div></div>
  <div class="stat-card"><div class="num" id="stat-error">-</div><div class="label">Errors</div></div>
  <div class="stat-card"><div class="num" id="stat-avg-duration">-</div><div class="label">Avg Duration</div></div>
  <div class="stat-card"><div class="num" id="stat-consec-errors">-</div><div class="label">Consec Errors</div></div>
  <div class="stat-card"><div class="num" id="stat-eta">-</div><div class="label">ETA</div></div>
</div>

<div id="cooldown-display" class="cooldown-idle">Cooldown: idle</div>

<h2>Progress</h2>
<div class="progress" id="progress-bar"><div class="progress-fill" id="progress-fill" style="width:0%"></div></div>

<h2>Errors <span id="error-summary" style="font-size:0.75rem;color:var(--muted);font-weight:400;"></span></h2>
<div id="error-panel" style="margin-bottom:0.5rem;display:flex;flex-wrap:wrap;gap:4px;">
  <div class="err-card err-timeout"><span class="num" id="err-timeout">0</span>timeout</div>
  <div class="err-card err-network"><span class="num" id="err-network">0</span>network</div>
  <div class="err-card err-schema"><span class="num" id="err-schema">0</span>schema</div>
  <div class="err-card err-unknown"><span class="num" id="err-unknown">0</span>unknown</div>
  <div id="mitigations-container" style="margin-left:8px;"></div>
</div>

<h2>Metrics <span id="metrics-summary" style="font-size:0.75rem;color:var(--muted);font-weight:400;"></span></h2>
<div id="metrics-panel" class="stats-grid" style="margin-bottom:0.5rem;">
  <div class="stat-card"><div class="num" id="metric-avg-turns">-</div><div class="label">Avg Turns</div></div>
  <div class="stat-card"><div class="num" id="metric-tokens">-</div><div class="label">Tokens/Iter</div></div>
  <div class="stat-card"><div class="num" id="metric-est-cost">-</div><div class="label">Est Cost</div></div>
  <div class="stat-card"><div class="num" id="metric-iters-per-goal">-</div><div class="label">Iters/Goal</div></div>
</div>

<h2>Goals <span id="goals-summary" style="font-size:0.75rem;color:var(--muted);font-weight:400;"></span></h2>
<div id="goals-panel" style="margin-bottom:0.5rem;"></div>

<h2>Latest Iteration <span class="compact-toggle" id="compact-toggle" onclick="toggleCompact()">[compact]</span></h2>
<div id="summary-only"></div>
<table id="iterations-table">
<thead><tr><th>#</th><th>Type</th><th>Duration</th><th>Summary</th><th>Classification</th><th>Error</th></tr></thead>
<tbody id="iterations-body"></tbody>
</table>

<p style="margin-top:1rem;font-size:0.75rem;color:var(--muted);">
  Live updates via SSE &mdash;
  <a href="/api/status" target="_blank" style="color:var(--accent);">JSON API</a> &middot;
  <a href="/status" target="_blank" style="color:var(--accent);">Simple Status</a> &middot;
  <a href="/health" target="_blank" style="color:var(--accent);">Health</a>
</p>

<script>
var compact = false;
function toggleCompact() {
    compact = !compact;
    document.body.classList.toggle('compact-mode', compact);
    document.getElementById('compact-toggle').textContent = compact ? '[expand]' : '[compact]';
}
function updateBadge(status) {
    var badge = document.getElementById('status-badge');
    badge.textContent = status;
    badge.className = '';
    if (status === 'running') badge.classList.add('running');
    else if (status === 'stopped') badge.classList.add('stopped');
    else if (status === 'paused') badge.classList.add('paused');
    else if (status === 'reloading') badge.classList.add('reloading');
    else badge.classList.add('no_ledger');
}
function updateErrorPanel(data) {
    var e = data.error_counts || {};
    document.getElementById('err-timeout').textContent = e.timeout || 0;
    document.getElementById('err-network').textContent = e.network || 0;
    document.getElementById('err-schema').textContent = e.schema || 0;
    document.getElementById('err-unknown').textContent = e.unknown || 0;
    var total = (e.timeout||0)+(e.network||0)+(e.schema||0)+(e.unknown||0);
    document.getElementById('error-summary').textContent = '(' + total + ' total errors)';
    // Active mitigations
    var mc = document.getElementById('mitigations-container');
    mc.innerHTML = '';
    var m = data.mitigations || {};
    var mItems = [];
    if (m.timeout_increased) mItems.push('timeout+' + (m.timeout_mult || ''));
    if (m.cooldown_elevated) mItems.push('cooldown+');
    if (m.force_subprocess) mItems.push('no-library');
    if (m.reduced_workers) mItems.push('workers-');
    if (m.consecutive_errors > 1) mItems.push(m.consecutive_errors + ' consec errs');
    if (mItems.length === 0) mItems.push('none active');
    mItems.forEach(function(t) {
        var sp = document.createElement('span');
        sp.className = 'mitigation-tag' + (t === 'none active' ? '' : ' mitigation-active');
        sp.textContent = t;
        mc.appendChild(sp);
    });
}
function updateMetricsPanel(data) {
    document.getElementById('metric-avg-turns').textContent = data.avg_turns_per_iter != null ? data.avg_turns_per_iter : '-';
    document.getElementById('metric-tokens').textContent = data.avg_tokens_per_iter != null ? data.avg_tokens_per_iter : '-';
    document.getElementById('metric-est-cost').textContent = data.est_cost || '-';
    document.getElementById('metric-iters-per-goal').textContent = data.iters_per_goal != null ? data.iters_per_goal : '-';
    document.getElementById('metrics-summary').textContent = data.metrics_summary || '';
}
function updateGoalsPanel(data) {
    var gp = document.getElementById('goals-panel');
    var goals = data.goals || [];
    var doneCnt = 0;
    goals.forEach(function(g) { if (g.done) doneCnt++; });
    document.getElementById('goals-summary').textContent = doneCnt + '/' + goals.length + ' complete';
    gp.innerHTML = '';
    if (goals.length === 0) {
        gp.innerHTML = '<p style="font-size:0.82rem;color:var(--muted)">No goals file loaded</p>';
        return;
    }
    // Progress bar
    var pct = goals.length > 0 ? Math.min(100.0 * doneCnt / goals.length, 100.0) : 0;
    var pbDiv = document.createElement('div');
    pbDiv.className = 'progress';
    pbDiv.style.height = '6px';
    var pbFill = document.createElement('div');
    pbFill.className = 'progress-fill';
    pbFill.style.width = pct + '%';
    pbFill.style.height = '6px';
    pbDiv.appendChild(pbFill);
    gp.appendChild(pbDiv);
    // Goal per-goal list (show max 30)
    var maxShow = Math.min(goals.length, 30);
    for (var i = 0; i < maxShow; i++) {
        var g = goals[i];
        var row = document.createElement('div');
        row.className = 'goal-row' + (g.done ? ' goal-done' : '') + (g.active ? ' goal-active' : '');
        var idxSpan = document.createElement('span');
        idxSpan.className = 'gidx';
        idxSpan.textContent = (i + 1);
        row.appendChild(idxSpan);
        var stSpan = document.createElement('span');
        stSpan.className = 'gstatus';
        stSpan.textContent = g.done ? '\u2713' : (g.active ? '\u25b6' : '\u25cb');
        row.appendChild(stSpan);
        var txtSpan = document.createElement('span');
        txtSpan.className = 'gtext';
        txtSpan.textContent = g.text || '';
        row.appendChild(txtSpan);
        gp.appendChild(row);
    }
    if (goals.length > 30) {
        var more = document.createElement('p');
        more.style.cssText = 'font-size:0.75rem;color:var(--muted);margin-top:4px;';
        more.textContent = '... and ' + (goals.length - 30) + ' more goals';
        gp.appendChild(more);
    }
}
function updateMeta(data) {
    document.getElementById('total-iterations').textContent = data.total_iterations != null ? data.total_iterations : '-';
    document.getElementById('goal').textContent = data.goal || '-';
    document.getElementById('evolved-goal').textContent = data.evolved_goal || '-';
    document.getElementById('started-at').textContent = data.started_at || '-';
    document.getElementById('last-updated').textContent = data.last_updated || '-';
    updateBadge(data.status || 'unknown');
}
function updateStats(data) {
    var s = data.stats || {};
    document.getElementById('stat-success').textContent = s.success_count != null ? s.success_count : '-';
    document.getElementById('stat-error').textContent = s.error_count != null ? s.error_count : '-';
    document.getElementById('stat-avg-duration').textContent = s.avg_duration_seconds != null ? s.avg_duration_seconds + 's' : '-';
    document.getElementById('stat-consec-errors').textContent = data.consecutive_errors != null ? data.consecutive_errors : '-';
    var eta = data.eta || {};
    document.getElementById('stat-eta').textContent = eta.remaining_formatted || '-';
}
function updateProgress(data) {
    var maxIt = data.max_iterations;
    var curIt = data.total_iterations;
    if (maxIt > 0) {
        var pct = Math.min(100.0 * curIt / maxIt, 100.0);
        document.getElementById('progress-fill').style.width = pct + '%';
    } else {
        document.getElementById('progress-fill').style.width = '0%';
    }
}
function updateCooldown(data) {
    var cd = document.getElementById('cooldown-display');
    var seconds = data.cooldown;
    if (seconds > 0) {
        cd.textContent = 'Cooldown: ' + seconds + 's';
        cd.className = 'cooldown-active';
    } else {
        cd.textContent = 'Cooldown: idle';
        cd.className = 'cooldown-idle';
    }
}
function createTag(text, cls) {
    var span = document.createElement('span');
    span.className = 'tag ' + cls;
    span.textContent = text;
    return span;
}
function addIterationRow(iter) {
    if (!iter || !iter.n) return;
    var tbody = document.getElementById('iterations-body');
    var tr = document.createElement('tr');
    if (iter.error && iter.error !== 'none' && iter.error !== '') {
        tr.className = 'error-row';
    }
    var tdN = document.createElement('td'); tdN.textContent = iter.n; tr.appendChild(tdN);
    var tdType = document.createElement('td');
    if (iter.task_type) {
        var cls = iter.task_type === 'error' ? 'tag-err' : 'tag-ok';
        tdType.appendChild(createTag(iter.task_type, cls));
    }
    tr.appendChild(tdType);
    var tdDur = document.createElement('td');
    tdDur.textContent = iter.duration_seconds != null ? iter.duration_seconds + 's' : '-';
    tr.appendChild(tdDur);
    var summary = iter.summary || iter.next_goal || '';
    var tdSum = document.createElement('td');
    tdSum.className = 'summary';
    tdSum.title = summary;
    tdSum.textContent = summary.substring(0, 80);
    tr.appendChild(tdSum);
    var tdCls = document.createElement('td');
    if (iter.classification) {
        var cCls = 'tag-ok';
        if (iter.classification === 'stuck' || iter.classification === 'regression') cCls = 'tag-err';
        else if (iter.classification === 'partial') cCls = 'tag-evolve';
        tdCls.appendChild(createTag(iter.classification, cCls));
    }
    tr.appendChild(tdCls);
    var tdErr = document.createElement('td');
    tdErr.textContent = iter.error && iter.error !== 'none' ? iter.error.substring(0, 60) + '...' : '';
    tr.appendChild(tdErr);
    tbody.insertBefore(tr, tbody.firstChild);
    while (tbody.children.length > 100) {
        tbody.removeChild(tbody.lastChild);
    }
}
function renderDashboard(data) {
    if (!data) return;
    updateMeta(data);
    updateStats(data);
    updateProgress(data);
    updateCooldown(data);
    updateErrorPanel(data);
    updateMetricsPanel(data);
    updateGoalsPanel(data);
    if (data.iteration && data.iteration.n) {
        addIterationRow(data.iteration);
    }
}
// Initial load: fetch full state from /api/status
fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (fullState) {
        var s = fullState.stats || {};
        var iters = fullState.iterations || [];
        var latest = iters.length > 0 ? iters[iters.length - 1] : {};
        var renderData = {
            iteration: latest,
            status: fullState.status || 'unknown',
            total_iterations: fullState.total_iterations || 0,
            max_iterations: fullState.max_iterations || 0,
            goal: (fullState.initial_command || '') || '-',
            evolved_goal: fullState.evolved_goal || '',
            started_at: fullState.started_at || '',
            last_updated: fullState.last_updated || '',
            stats: {
                success_count: s.success_count,
                error_count: s.error_count,
                total_duration_seconds: s.total_duration_seconds,
                avg_duration_seconds: s.avg_duration_seconds
            },
            consecutive_errors: s.consecutive_errors || 0,
            consecutive_successes: fullState.consecutive_successes || 0,
            cooldown: fullState.cooldown || 0,
            eta: fullState.eta || {}
        };
        renderDashboard(renderData);
        iters.forEach(function(it) {
            if (it.n) addIterationRow(it);
        });
    })
    .catch(function (err) {
        console.error('Initial fetch failed:', err);
        document.getElementById('connection-status').textContent = '\\u25CF fetch error';
        document.getElementById('connection-status').className = 'disconnected';
    });
// Open SSE connection
var evtSource = new EventSource('/live');
evtSource.addEventListener('iteration', function (event) {
    try {
        var data = JSON.parse(event.data);
        renderDashboard(data);
    } catch (e) {
        console.error('SSE parse error:', e);
    }
});
evtSource.addEventListener('heartbeat', function () {});
evtSource.onopen = function () {
    document.getElementById('connection-status').textContent = '\\u25CF connected';
    document.getElementById('connection-status').className = 'connected';
};
evtSource.onerror = function (err) {
    console.error('SSE error, reconnecting...', err);
    document.getElementById('connection-status').textContent = '\\u25CF disconnected (reconnecting...)';
    document.getElementById('connection-status').className = 'disconnected';
};
</script>
</body>
</html>"""


def _generate_status_html(state: dict, compact: bool = False) -> str:
    """Generate a self-contained HTML page from the current ledger state.
    compact: If True, render compact summary-only mode by default.
    """
    status = state.get("status", "unknown")
    status_cls = {"running": "running", "paused": "paused"}.get(status, "stopped")
    total = state.get("total_iterations", 0)
    goal = (state.get("initial_command") or "(none)")[:80]
    started = (state.get("started_at") or "?")[:19]
    last_upd = (state.get("last_updated") or "?")[:19]
    stats = state.get("stats", {})
    success = stats.get("success_count", 0)
    errors = stats.get("error_count", 0)
    total_dur = stats.get("total_duration_seconds", 0)
    avg_dur = stats.get("avg_duration_seconds", 0)

    # System resource cards from latest iteration data
    iterations = state.get("iterations", [])
    cpu_sec = "0.0"
    mem_mb = "0"
    mem_pct = "0.0"
    if iterations:
        last_it = iterations[-1]
        cpu_sec = str(last_it.get("cpu_seconds_used", last_it.get("cpu_seconds", 0)))
        mem_val = last_it.get("memory_rss_mb", 0)
        mem_mb = f"{mem_val:.0f}" if isinstance(mem_val, float) else str(mem_val)
        mp_val = last_it.get("memory_percent", 0)
        if isinstance(mp_val, float):
            mem_pct = f"{mp_val * 100:.1f}"
        else:
            mem_pct = str(mp_val)

    # ETA estimate
    eta_text = "N/A"
    max_it = state.get("max_iterations", 0)
    if max_it > 0 and total > 0:
        remaining = max_it - total
        if remaining > 0 and avg_dur > 0:
            eta_secs = remaining * avg_dur
            if eta_secs >= 3600:
                eta_text = f"{eta_secs / 3600:.1f}h"
            elif eta_secs >= 60:
                eta_text = f"{eta_secs / 60:.0f}m"
            else:
                eta_text = f"{eta_secs:.0f}s"
        elif remaining <= 0:
            eta_text = "Done"

    # Cooldown indicator
    cooldown_val = state.get("cooldown", 0) or stats.get("cooldown", 0)
    cooldown_text = f"{cooldown_val}s" if cooldown_val else "None"
    cooldown_cls = "cooldown-active" if cooldown_val else "cooldown-idle"

    # Progress bar
    progress_row = ""
    if max_it > 0:
        pct = min(100.0 * total / max_it, 100.0) if max_it > 0 else 0
        progress_row = f'<h2>Progress</h2><div class="progress"><div class="progress-fill" style="width:{pct:.0f}%"></div></div><p style="font-size:0.8rem;color:var(--muted)">{total}/{max_it} ({pct:.0f}%)</p>'

    # Evolved goal
    evolved = state.get("evolved_goal", "")
    eva_row = (
        f'<h2>Evolved Goal</h2><p style="color:var(--accent)">{evolved[:100]}</p>'
        if evolved
        else ""
    )

    # Summary-only text
    summary_only_text = f"{total} iterations, {success} success, {errors} errors, {total_dur:.0f}s total, {avg_dur:.0f}s avg"

    # Iteration rows
    rows = []
    for it in reversed(iterations[-100:]):
        n = it.get("n", "?")
        started_at = (it.get("started_at") or "?")[:16]
        dur = it.get("duration_seconds", 0)
        tt = it.get("task_type", "")
        summary = (it.get("summary") or "")[:100]
        err = it.get("error")
        has_err = bool(err)
        err_cls = ' class="error-row"' if has_err else ""
        has_evolve = bool(it.get("next_goal"))
        tags = ""
        if has_err:
            tags += '<span class="tag tag-err">ERR</span> '
        if has_evolve:
            tags += '<span class="tag tag-evolve">EVOLVE</span> '

        # Per-iteration ETA
        it_eta = "N/A"
        if avg_dur > 0:
            remaining_eta = max_it - n if max_it > 0 else 0
            if remaining_eta > 0:
                it_eta_secs = remaining_eta * avg_dur
                if it_eta_secs >= 3600:
                    it_eta = f"{it_eta_secs / 3600:.1f}h"
                elif it_eta_secs >= 60:
                    it_eta = f"{it_eta_secs / 60:.0f}m"
                else:
                    it_eta = f"{it_eta_secs:.0f}s"

        rows.append(
            f"<tr{err_cls}><td>{n}</td><td>{started_at}</td>"
            f'<td>{dur}s</td><td>{tags}<span class="tag" style="color:var(--muted)">{tt}</span></td>'
            f'<td class="summary" title="{summary.replace(chr(34), "&quot;")}">{summary}</td>'
            f"<td>{it_eta}</td></tr>"
        )

    # Apply compact mode class if requested
    compact_class = ' class="compact-mode"' if compact else ""

    html = (
        _STATUS_HTML_TPL.replace("{STATUS_CLASS}", status_cls)
        .replace("{STATUS}", status)
        .replace("{TOTAL}", str(total))
        .replace("{GOAL}", goal)
        .replace("{STARTED}", started)
        .replace("{LAST_UPDATED}", last_upd)
        .replace("{SUCCESS}", str(success))
        .replace("{ERRORS}", str(errors))
        .replace("{TOTAL_DUR}", f"{total_dur:.0f}")
        .replace("{AVG_DUR}", f"{avg_dur:.0f}")
        .replace("{CPU_SEC}", cpu_sec)
        .replace("{MEM_MB}", mem_mb)
        .replace("{MEM_PCT}", mem_pct)
        .replace("{ETA}", eta_text)
        .replace("{COOLDOWN}", cooldown_text)
        .replace("{COOLDOWN_CLASS}", cooldown_cls)
        .replace("{EVA_GOAL_ROW}", eva_row)
        .replace("{PROGRESS_ROW}", progress_row)
        .replace("{ITER_ROWS}", "".join(rows))
        .replace("{SUMMARY_ONLY_TEXT}", summary_only_text)
        .replace("{VERSION}", LAUNCH_LOOP_VERSION)
    )

    # Inject compact body class
    if compact:
        html = html.replace("<body>", '<body class="compact-mode">')

    return html


def _write_status_html(html_path: str, state: dict):
    """Write the status HTML dashboard to a file."""
    try:
        html = _generate_status_html(state)
        os.makedirs(os.path.dirname(os.path.abspath(html_path)), exist_ok=True)
        with open(html_path, "w") as f:
            f.write(html)
    except (OSError, IOError) as e:
        _log(f"[HTML-DASH] Failed to write status page {html_path}: {e}")


# ---------------------------------------------------------------------------
# SSE broadcast helpers
# ---------------------------------------------------------------------------


def _broadcast_to_sse_clients(state: dict) -> None:
    """Push the latest iteration state as an SSE event to all connected clients.

    Called from run_loop() after each iteration completes.
    Iterates the module-level _sse_clients list under lock and drops
    any queue whose put_nowait() raises queue.Full (dead client).
    """
    global _sse_clients
    payload = _build_sse_payload(state)
    payload_json = json.dumps(payload, default=str)
    with _sse_clients_lock:
        alive = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload_json)
                alive.append(q)
            except queue.Full:
                pass  # Client disconnected or too slow — drop
        _sse_clients = alive


def _build_sse_payload(state: dict) -> dict:
    """Build a compact JSON payload from the full ledger state for SSE push.

    The payload contains everything the live dashboard needs to render
    without additional fetches: the latest iteration record, top-level
    status fields, aggregated stats, ETA, error counts, goals, and metrics.
    """
    stats = state.get("stats", {})
    iterations = state.get("iterations", [])
    latest = iterations[-1] if iterations else {}
    et = state.get("error_type_counts", {})
    mitigations = state.get("mitigations", {})
    mitigations["consecutive_errors"] = stats.get("consecutive_errors", 0)
    # Build goals list from goals_completed + goals_file
    goals_completed = state.get("goals_completed", {})
    goals_specs = state.get("goals_specs", [])
    goals_list = []
    for idx, spec in enumerate(goals_specs):
        gtext = spec[0] if isinstance(spec, (tuple, list)) else spec
        gh = _goal_hash(gtext) if gtext else ""
        done = (
            gh in goals_completed and goals_completed[gh].get("status") == "completed"
        )
        active = False
        if state.get("goal_index") is not None:
            active = idx == state["goal_index"]
        goals_list.append({"text": gtext[:100], "done": done, "active": active})
    # Metrics estimates
    total_iters = state.get("total_iterations", 0)
    avg_turns = stats.get("avg_turns_per_iter", None) or latest.get("turns_used", None)
    avg_tokens = stats.get("avg_tokens_per_iter", None) or latest.get(
        "tokens_used", None
    )
    iters_per_goal = None
    if goals_list and total_iters > 0:
        iters_per_goal = max(1, total_iters // max(len(goals_list), 1))
    return {
        "iteration": latest,
        "status": state.get("status", "unknown"),
        "total_iterations": total_iters,
        "max_iterations": state.get("max_iterations", 0),
        "goal": (state.get("initial_command") or "")[:80],
        "evolved_goal": state.get("evolved_goal", ""),
        "started_at": state.get("started_at", ""),
        "last_updated": state.get("last_updated", ""),
        "stats": {
            "success_count": stats.get("success_count", 0),
            "error_count": stats.get("error_count", 0),
            "total_duration_seconds": stats.get("total_duration_seconds", 0),
            "avg_duration_seconds": stats.get("avg_duration_seconds", 0),
        },
        "consecutive_errors": stats.get("consecutive_errors", 0),
        "consecutive_successes": state.get("consecutive_successes", 0),
        "cooldown": state.get("cooldown", 0),
        "eta": state.get("eta", {}),
        "error_counts": {
            "timeout": et.get("timeout", 0),
            "network": et.get("network", 0),
            "schema": et.get("schema", 0),
            "unknown": et.get("unknown", 0),
        },
        "mitigations": mitigations,
        "goals": goals_list,
        "avg_turns_per_iter": avg_turns,
        "avg_tokens_per_iter": avg_tokens,
        "est_cost": state.get("est_cost", None),
        "iters_per_goal": iters_per_goal,
        "metrics_summary": "",
    }


def write_status_file(
    status_path: str, state: dict, iteration: int = 0, status: str = "running"
) -> None:
    """Write a lightweight one-line status file for external monitoring."""
    if not status_path:
        return
    try:
        os.makedirs(os.path.dirname(status_path) or ".", exist_ok=True)
        line = json.dumps(
            {
                "pid": os.getpid(),
                "iteration": iteration,
                "status": status,
                "total_iterations": state.get("total_iterations", 0),
                "total_duration_seconds": state.get("stats", {}).get(
                    "total_duration_seconds", 0
                ),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        )
        with open(status_path, "w") as f:
            f.write(line + "\n")
    except (OSError, IOError) as e:
        _log(f"[STATUS] Failed to write status file {status_path}: {e}")


def write_ledger(state: dict) -> None:
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    tmp_path = LEDGER_PATH + ".tmp"
    with FileLock():
        with open(tmp_path, "w") as f:
            json.dump(state, f, indent=2, default=str)
        os.replace(tmp_path, LEDGER_PATH)


def _archive_iterations(
    iterations: list[dict],
    archive_dir: str,
    tag: str = "",
) -> int:
    """
    Archive a list of iteration records to a gzip-compressed JSONL file.

    Args:
        iterations: List of iteration record dicts to archive (oldest-first).
        archive_dir: Directory for archive files (created if needed).
        tag: Optional run tag to embed in the filename.

    Returns:
        Number of iterations archived (0 if nothing to archive).
    """
    if not iterations:
        return 0

    os.makedirs(archive_dir, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = 0
    safe_tag = re.sub(r"[^a-zA-Z0-9_.-]", "_", tag) if tag else ""
    tag_part = f"-{safe_tag}" if safe_tag else ""
    while True:
        seq += 1
        basename = f"iterations-{today}{tag_part}-{seq:04d}.jsonl.gz"
        final_path = os.path.join(archive_dir, basename)
        if not os.path.exists(final_path):
            break

    tmp_path = final_path + ".tmp"
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
            # First line: metadata header (_meta)
            meta = {
                "_meta": {
                    "version": 1,
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(iterations),
                    "iteration_range": {
                        "first": iterations[0].get("n"),
                        "last": iterations[-1].get("n"),
                    },
                    "tag": tag or None,
                }
            }
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            # Data lines: one JSON per iteration
            for it in iterations:
                f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp_path, final_path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    _log(
        f"[ARCHIVE] Saved {len(iterations)} iterations to {basename} "
        f"(iter #{iterations[0].get('n')}–#{iterations[-1].get('n')})"
    )
    return len(iterations)


def _cleanup_old_archives(archive_dir: str, retention_days: int) -> None:
    """Remove archive files older than retention_days. Best-effort."""
    if retention_days <= 0:
        return
    if not os.path.isdir(archive_dir):
        return

    cutoff = time.time() - retention_days * 86400
    removed = 0
    for fname in os.listdir(archive_dir):
        if not fname.endswith(".jsonl.gz") or not fname.startswith("iterations-"):
            continue
        fpath = os.path.join(archive_dir, fname)
        try:
            # Try to parse date from filename: iterations-{YYYYMMDD}-...
            date_str = fname.split("-")[1]  # YYYYMMDD
            file_ts = datetime.strptime(date_str, "%Y%m%d").timestamp()
        except (IndexError, ValueError):
            # Fallback to mtime
            try:
                file_ts = os.path.getmtime(fpath)
            except OSError:
                continue
        if file_ts < cutoff:
            try:
                os.remove(fpath)
                removed += 1
            except OSError as e:
                _log(f"[ARCHIVE] Failed to remove old archive {fname}: {e}")
    if removed:
        _log(f"[ARCHIVE] Cleaned up {removed} old archive(s)")


def _enforce_archive_max_size(archive_dir: str, max_size_mb: int) -> None:
    """Remove oldest archive files until total size is under max_size_mb MB."""
    if max_size_mb <= 0:
        return
    if not os.path.isdir(archive_dir):
        return

    max_bytes = max_size_mb * 1024 * 1024
    files = []
    total_bytes = 0
    for fname in os.listdir(archive_dir):
        if not fname.endswith(".jsonl.gz") or not fname.startswith("iterations-"):
            continue
        fpath = os.path.join(archive_dir, fname)
        try:
            fsize = os.path.getsize(fpath)
            total_bytes += fsize
            files.append((fpath, fsize, fname))
        except OSError:
            continue

    if total_bytes <= max_bytes:
        return

    # Sort by mtime (oldest first)
    files.sort(key=lambda x: os.path.getmtime(x[0]))
    removed = 0
    for fpath, fsize, fname in files:
        if total_bytes <= max_bytes:
            break
        try:
            os.remove(fpath)
            total_bytes -= fsize
            removed += 1
            _log(f"[ARCHIVE] Purged {fname} to stay under {max_size_mb}MB limit")
        except OSError as e:
            _log(f"[ARCHIVE] Failed to purge {fname}: {e}")
    if removed:
        _log(f"[ARCHIVE] Purged {removed} archive file(s) to meet max size limit")


def read_ledger() -> dict | None:
    if not os.path.exists(LEDGER_PATH):
        return None
    try:
        with FileLock():
            with open(LEDGER_PATH) as f:
                return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, TimeoutError):
        return None


def check_sentinel(path: str) -> str | None:
    if path and os.path.exists(path):
        with open(path) as f:
            content = f.read().strip()
        os.remove(path)
        return content
    return None


def check_sentinel_no_remove(path: str) -> str | None:
    """Read sentinel without removing it. Used for pause/resume polling."""
    if path and os.path.exists(path):
        with open(path) as f:
            content = f.read().strip()
        return content
    return None


def extract_json_from_output(stdout: str) -> dict | None:
    """Extract a JSON object from spawned session output using brace-depth
    counting. Handles:
      - Multi-line JSON (line breaks inside the JSON object)
      - JSON wrapped in markdown code fences (```json ... ```)
      - JSON embedded in conversational text
      - session_id lines from chat -q

    Strategy: scan lines, when we see a '{' start collecting, count braces,
    when balanced try json.loads. Try parse on each line that has balanced
    braces (handles single-line). Also scans backwards for the LAST JSON
    in the output (most important result).
    """
    if not stdout:
        return None

    # Strip common trailing noise from chat -q
    lines = []
    for line in stdout.split("\n"):
        stripped = line.strip()
        # Filter session_id lines and common noise
        if stripped.startswith("session_id:"):
            continue
        lines.append(line)

    text = "\n".join(lines)

    # Strategy 1: Scan backwards looking for the LAST JSON object
    # Collect characters in reverse until braces are balanced
    brace_depth = 0
    in_json = False
    json_chars = []
    # We scan from the end to find the LAST JSON object
    found_open = False
    for ch in reversed(text):
        if ch == "}":
            brace_depth += 1
            in_json = True
            json_chars.insert(0, ch)
        elif ch == "{":
            brace_depth -= 1
            in_json = True
            json_chars.insert(0, ch)
            if brace_depth == 0:
                # Found a balanced JSON block at the end
                candidate = "".join(json_chars)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Might have leading non-JSON — try stripping it
                    pass
                in_json = False
                json_chars = []
                brace_depth = 0
        elif in_json:
            json_chars.insert(0, ch)

    # Strategy 2: Forward scan — find ALL JSON blocks, return last valid one
    json_objects = []
    i = 0
    while i < len(text):
        # Skip to next '{'
        start = text.find("{", i)
        if start < 0:
            break
        # Count braces from this position
        depth = 0
        j = start
        while j < len(text):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : j + 1]
                    try:
                        obj = json.loads(candidate)
                        json_objects.append(obj)
                        i = j + 1
                        break
                    except json.JSONDecodeError:
                        i = j + 1
                        break
            j += 1
        else:
            # Unbalanced — advance past the stray '{'
            i = start + 1

    if json_objects:
        return json_objects[-1]

    return None


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

    Args:
        summary: The iteration summary text (typically from spawned session output).
        git_before: Git state dict captured before the iteration (from
            _capture_git_state()).  May contain 'diff_stat', 'diff_stat_cached',
            'diff', 'head'.  None if git tracking is disabled.
        git_after: Git state dict captured after the iteration.  Same structure
            as git_before.
        error: Combined error string for the iteration, or None if no error.

    Returns:
        One of: 'completed', 'progress', 'partial', 'stuck', 'regression',
        or 'unknown'.
    """
    # --- Determine whether git changes occurred ---
    has_git_changes = False
    if git_before and git_after:
        # Compare diff_stat strings — if they differ, something changed
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


def _capture_git_state(workdir: str | None, store_diff: bool = False) -> dict:
    """Capture pre/post git state.

    Args:
        workdir: Git repo working directory.
        store_diff: If True, also store the actual unified diff (capped at 10KB).
    """
    cwd = workdir or os.getcwd()
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return {}
    result: dict[str, str] = {}
    try:
        r = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        result["diff_stat"] = r.stdout.strip() or "(no unstaged changes)"
        r2 = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        result["diff_stat_cached"] = r2.stdout.strip() or "(no staged changes)"
        r3 = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        result["head"] = r3.stdout.strip() if r3.returncode == 0 else ""
        if store_diff:
            r4 = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=10,
            )
            diff_text = r4.stdout.strip()
            # Cap at 10KB to avoid ledger bloat
            if diff_text:
                result["diff"] = diff_text[:10240]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {}
    return result


def _git_auto_commit(workdir: str | None, iteration: int, summary: str) -> str | None:
    """Auto-commit changes after an iteration. Returns commit hash or None."""
    cwd = workdir or os.getcwd()
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return None
    try:
        subprocess.run(["git", "add", "-A"], capture_output=True, cwd=cwd, timeout=15)
        r = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
            cwd=cwd,
            timeout=10,
        )
        if r.returncode == 0:
            return None
        msg = f"infinite-loop iter #{iteration}: {summary[:80]}"
        subprocess.run(
            ["git", "commit", "-m", msg],
            capture_output=True,
            cwd=cwd,
            timeout=30,
        )
        r2 = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        return r2.stdout.strip() if r2.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


# ---------------------------------------------------------------------------
# Find hermes binary
# ---------------------------------------------------------------------------


def find_hermes() -> str:
    candidates = [
        shutil.which("hermes"),
        os.path.expanduser("~/.local/bin/hermes"),
        os.path.expanduser("~/.hermes/hermes"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "hermes"


# ---------------------------------------------------------------------------
# Spawn Hermes session (chat -q mode with delegation)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task type auto-detection — smart toolset enrichment
# ---------------------------------------------------------------------------

TASK_PATTERNS = {
    "research": {
        "keywords": [
            "research",
            "investigate",
            "find",
            "search",
            "learn",
            "study",
            "analyze",
            "explore",
            "discover",
            "look up",
            "what is",
            "how does",
            "compare",
            "survey",
            "literature",
            "paper",
            "article",
            "audit",
            "review",
            "identify",
            "gather",
            "collect",
            "monitor",
            "track",
            "trace",
            "determine",
            "understand",
            "evaluate",
            "assess",
        ],
        "extra_toolsets": ["search", "web"],
        "description": "Information gathering and analysis",
    },
    "code-fix": {
        "keywords": [
            "fix",
            "bug",
            "error",
            "crash",
            "broken",
            "issue",
            "repair",
            "patch",
            "debug",
            "lint",
            "type error",
            "test fails",
            "refactor",
            "rewrite",
            "clean up",
            "resolve",
            "correct",
            "address",
            "remediate",
            "mitigate",
            "workaround",
            "hotfix",
            "revert",
            "rollback",
            "restore",
            "recover",
            "cleanup",
            "rework",
            "revise",
            "reorganize",
        ],
        "extra_toolsets": ["code_execution", "vision"],
        "description": "Code debugging and repair",
    },
    "code-build": {
        "keywords": [
            "build",
            "create",
            "implement",
            "write",
            "develop",
            "add feature",
            "new module",
            "scaffold",
            "generate",
            "construct",
            "compose",
            "architect",
            "design",
            "prototype",
            "extend",
            "enhance",
            "improve",
            "upgrade",
            "migrate",
            "port",
            "integrate",
            "wire up",
            "hook up",
            "connect",
            "initialize",
            "bootstrap",
            "template",
            "boilerplate",
            "skeleton",
        ],
        "extra_toolsets": ["code_execution", "vision"],
        "description": "New code and feature development",
    },
    "system-admin": {
        "keywords": [
            "deploy",
            "configure",
            "setup",
            "install",
            "migrate",
            "backup",
            "restore",
            "monitor",
            "optimize",
            "tune",
            "audit",
            "check health",
            "maintenance",
            "upgrade",
            "update",
            "manage",
            "provision",
            "orchestrate",
            "automate",
            "schedule",
            "scale",
            "replicate",
            "synchronize",
            "distribute",
            "load balance",
            "failover",
            "remediate",
            "patch",
            "harden",
            "secure",
            "encrypt",
        ],
        "extra_toolsets": ["code_execution"],
        "description": "System administration and DevOps",
    },
    "data-processing": {
        "keywords": [
            "process",
            "transform",
            "convert",
            "parse",
            "extract",
            "load",
            "clean",
            "normalize",
            "aggregate",
            "compute",
            "calculate",
            "statistics",
            "analyze data",
            "report",
            "dataset",
            "csv",
            "json",
            "import",
            "export",
            "merge",
            "join",
            "split",
            "deduplicate",
            "validate",
            "sanitize",
            "scrub",
            "anonymize",
            "summarize",
            "enrich",
            "augment",
            "sort",
            "filter",
            "query",
        ],
        "extra_toolsets": ["code_execution"],
        "description": "Data processing and analysis",
    },
    "content": {
        "keywords": [
            "write",
            "document",
            "documentation",
            "readme",
            "blog",
            "post",
            "article",
            "report",
            "summary",
            "explain",
            "describe",
            "draft",
            "tutorial",
            "guide",
            "manual",
            "specification",
            "spec",
            "changelog",
            "release notes",
            "announcement",
            "newsletter",
            "whitepaper",
            "case study",
            "proposal",
            "presentation",
            "slides",
        ],
        "extra_toolsets": ["vision", "image_gen"],
        "description": "Content and documentation creation",
    },
}

BASE_TOOLSETS = "terminal,file,delegation,web,skills,browser,memory,session_search,code_execution,todo,vision"


def detect_task_type(goal: str) -> tuple[str, str, set[str]]:
    """Analyze the goal and detect the primary task type.

    Returns (task_type, description, extra_tools) where extra_tools are
    toolset names to ADD on top of the base set.
    """
    goal_lower = goal.lower()
    scores: dict[str, int] = {}
    for task_type, config in TASK_PATTERNS.items():
        score = sum(1 for kw in config["keywords"] if kw in goal_lower)
        if score > 0:
            scores[task_type] = score

    if not scores:
        return "general", "General task", set()

    best = max(scores, key=scores.get)
    config = TASK_PATTERNS[best]
    return best, config["description"], set(config["extra_toolsets"])


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
    """Build the prompt for a spawned Hermes session.

    The spawned session runs via `hermes chat -q` (NOT -z), which means it
    stays alive for multiple turns. This allows delegate_task() subagent
    results to arrive and be collected. The session has BOTH real tools
    (terminal, file) AND the delegation toolset.

    It MUST print one JSON line as its last output so the daemon can parse it.

    Different task types get optimized prompts that emphasize the most
    relevant tools and strategies for that kind of work.
    """
    tools_str = ",".join(toolsets)
    worker_tag = f" (worker #{worker_id})" if worker_id is not None else ""

    # Base instructions common to all task types
    instructions = [
        f"You are iteration #{iteration}{worker_tag} of an autonomous loop daemon.",
        "",
        "Your job: use your available tools to accomplish the GOAL below, then",
        " report the result as a single JSON line.",
        "",
        f"GOAL: {goal}",
        f"TASK TYPE: {task_type}",
        "",
    ]
    if context:
        instructions.append(f"CONTEXT: {context}")
        instructions.append("")

    # Inject prior context from previous iterations (if available)
    if prior_context:
        instructions.append("=== PRIOR ITERATION CONTEXT ===")
        instructions.append(prior_context)
        instructions.append("")
        instructions.append(
            "The above context was recalled from previous iterations. Use it to"
        )
        instructions.append(
            "avoid repeating work or making the same mistakes. If something was"
        )
        instructions.append("already tried and failed, try a different approach.")
        instructions.append("")

    # Auto-inject skill directory if the goal refers to self-modification
    goal_lower = goal.lower()
    if any(
        kw in goal_lower
        for kw in ["infinite-loop", "launch-loop", "self-modif", "skill", "daemon"]
    ):
        skill_dir = os.path.expanduser(
            "~/.hermes/skills/software-development/infinite-loop"
        )
        if os.path.isdir(skill_dir):
            instructions.append("=== SELF-MODIFICATION CONTEXT ===")
            instructions.append(
                f"The daemon's source is at: {skill_dir}/scripts/launch-loop.py"
            )
            instructions.append(f"The skill documentation is at: {skill_dir}/SKILL.md")
            instructions.append(
                f"The Hermes Worker is at: ~/.hermes/plugins/hermes-mcp-worker/main.py"
            )
            instructions.append("")
            instructions.append(
                "To signal the daemon to restart with updated code, include"
            )
            instructions.append(
                '"next_goal": "NEXT_ITERATION need_reload" in your JSON output.'
            )
            instructions.append(
                "The daemon will detect this, persist the ledger, and call os.execv()."
            )
            instructions.append(
                "After restart, the NEXT iteration will run with the updated code."
            )
            instructions.append("")

    instructions.extend(
        [
            f"AVAILABLE TOOLS: {tools_str}",
            "",
            "You have full autonomy and these capabilities:",
            "  - terminal: shell commands, build, test, git, packages",
            "  - file: read_file, write_file, patch, search_files",
            "  - web: web_search, web_extract for internet research",
            "  - browser: visual web browsing and interaction",
            "  - skills: skill_view, skills_list for established workflows",
            "  - delegation: delegate_task() — run parallel subagents",
            "  - memory: hindsight_retain/recall/reflect for cross-iteration persistence",
            "  - session_search: find what previous iterations did",
            "  - code_execution: sandboxed Python (import hermes_tools for search/read/terminal)",
            "  - todo: in-session task tracking and planning",
            "  - vision: image analysis and understanding",
            "  - MCP tools: Chroma (vector DB), Cognee (knowledge graph), screenpipe (screen/audio)",
            "",
        ]
    )

    # Add task-type-specific prompt sections
    if task_type == "research":
        instructions.extend(
            [
                "=== RESEARCH STRATEGY ===",
                "",
                "1. Start with web_search() to find relevant information",
                "2. Use web_extract() to read key pages in detail",
                "3. If needed, use the browser tool for dynamic page content",
                "4. Use delegate_task() for parallel research threads:",
                "   - e.g., one subagent searches source A, another searches source B",
                "5. Synthesize findings into a clear summary",
                "6. Use hindsight_retain() to save key findings for future iterations",
                "7. Tag findings so future iterations can find them",
                "8. Use skills if workflows exist for this research area",
                "",
                "=== DEEP DELEGATION STRATEGY ===",
                "This session has a HIGH turn budget. Use it:",
                "",
                "1. Break your GOAL into independent research sub-topics",
                "2. Dispatch via delegate_task() — they run in parallel",
                "3. While subagents research, do direct research with your own tools",
                "4. YOUR subagents can ALSO call delegate_task() for multi-level trees",
                "5. Combine all results into the final output",
                "",
            ]
        )
    elif task_type in ("code-fix", "code-build"):
        instructions.extend(
            [
                "=== CODE STRATEGY ===",
                "",
                "1. First, read and understand the relevant files (read_file, search_files)",
                "2. For code-fix: identify the root cause BEFORE making changes",
                "3. For code-build: plan the structure before writing code",
                "4. Write code with write_file() or patch() for targeted edits",
                "5. Use code_execution for quick Python scripts (import hermes_tools)",
                "6. Verify with: linting, type checks, tests",
                "7. Use vision_analyze() for UI/screenshot bugs",
                "8. Use delegate_task() for parallel work:",
                "   - e.g., one subagent fixes module A, another fixes module B",
                "9. Save findings with hindsight_retain()",
                "10. Use todo() to track subtasks and progress",
                "11. Check skills for established coding workflows",
                "",
                "=== DEEP DELEGATION STRATEGY ===",
                "This session has a HIGH turn budget. Use it aggressively:",
                "",
                "1. Break your GOAL into independent sub-tasks",
                "2. Dispatch via delegate_task() — they run in parallel",
                "3. While subagents work, do direct work with your own tools",
                "4. YOUR subagents can ALSO call delegate_task() for multi-level trees",
                "5. Each subagent can delegate further — build deep trees",
                "6. Combine all results into the final output",
                "",
            ]
        )
    elif task_type == "system-admin":
        instructions.extend(
            [
                "=== SYSTEM ADMIN STRATEGY ===",
                "",
                "1. Check current state first (terminal commands for status, health)",
                "2. Plan changes carefully — consider rollback",
                "3. Use code_execution for automation scripts",
                "4. Verify changes took effect after each step",
                "5. Use delegate_task for parallel configuration:",
                "   - e.g., one subagent configures service A, another configures service B",
                "6. Save system state info with hindsight_retain()",
                "7. Check skills for established system workflows",
                "",
            ]
        )
    elif task_type == "data-processing":
        instructions.extend(
            [
                "=== DATA PROCESSING STRATEGY ===",
                "",
                "1. Examine the data structure first (head, schema, stats)",
                "2. Use code_execution for data transformation (pandas, csv, json)",
                "3. For large datasets, use terminal with command-line tools (jq, awk, sed)",
                "4. Use delegate_task() for parallel data processing:",
                "   - e.g., one subagent processes chunk A, another chunk B",
                "5. Verify output integrity",
                "6. Save results with write_file()",
                "",
            ]
        )
    elif task_type == "content":
        instructions.extend(
            [
                "=== CONTENT CREATION STRATEGY ===",
                "",
                "1. Research/gather source material first",
                "2. Plan the structure/outline before writing",
                "3. Write with write_file() using proper formatting",
                "4. Use vision_analyze() to understand existing images/diagrams",
                "5. Use delegate_task() for parallel content creation:",
                "   - e.g., one subagent writes section A, another writes section B",
                "6. Review and polish the final output",
                "7. Save with hindsight_retain() if the content is reference material",
                "",
            ]
        )
    else:
        # General task — standard prompt
        instructions.extend(
            [
                "=== GENERAL STRATEGY ===",
                "",
                "1. Understand the goal and plan your approach",
                "2. Use the most appropriate tools for each sub-task",
                "3. Use delegate_task() for parallel work where possible",
                "4. Verify your work is correct",
                "5. Print JSON summary when done",
                "",
                "=== DEEP DELEGATION STRATEGY ===",
                "This session has a HIGH turn budget. Use it aggressively:",
                "",
                "1. Break your GOAL into independent sub-tasks",
                "2. Dispatch via delegate_task() — they run in parallel",
                "3. While subagents work, do direct work with your own tools",
                "4. YOUR subagents can ALSO call delegate_task() for multi-level trees",
                "5. Combine all results into the final output",
                "",
            ]
        )

    # Common memory & knowledge persistence section
    instructions.extend(
        [
            "=== MEMORY & KNOWLEDGE PERSISTENCE ===",
            "You have cross-iteration memory. Use it:",
            "",
            "  hindsight_retain(content, context='infinite-loop', tags=[...])",
            "    - Save important findings for FUTURE iterations",
            "    - Tag with 'project:<name>' so you can find them later",
            "    - Example: hindsight_retain('lib X at v2.1, API change in Y', ",
            "              context='dependency update', tags=['project:fix-auth'])",
            "",
            "  hindsight_recall(query='deployment config')",
            "    - Retrieve facts saved by PREVIOUS iterations",
            "    - Use this at the start to understand what's already been done",
            "",
            "  memory(action='add', target='memory', content='...')",
            "    - Save durable facts that persist across all Hermes sessions",
            "    - Use for: project conventions, tool preferences, environment quirks",
            "",
            "  session_search(query='previous work on auth', limit=3)",
            "    - Look at PREVIOUS iterations' full output (beyond summaries)",
            "    - Use this to understand what was already tried and what decisions were made",
            "",
            "  Chroma MCP (chroma_query_documents) — vector search across past data",
            "  Cognee MCP (recall) — knowledge graph search",
            "  todo() — track your subtasks and progress in-session",
            "  code_execution — run sandboxed Python (import hermes_tools for tool access)",
            "",
            "=== TOOL USAGE GUIDELINES ===",
            "",
            "When calling delegate_task():",
            "  - Pass a detailed 'context' field so the subagent works independently",
            "  - Pass toolsets=['terminal','file'] for file-level sub-tasks",
            "  - Pass toolsets=['terminal','file','web'] for research sub-tasks",
            "  - Use batch mode ('tasks' array) for 2-3 parallel subagents",
            "  - Each subagent can delegate further — build deep trees",
            "  - DO use delegate_task() for: code review, testing, research, analysis",
            "  - DO NOT use delegate_task() for: simple file reads, quick commands",
            "",
            "CRITICAL RULES:",
            "1. Actually DO the work — use your tools, don't just describe what to do",
            "2. If you delegate, WAIT for the subagent results to arrive as new messages",
            "3. delegate_task is async — keep working while waiting for subagents",
            "4. Combine subagent results with your direct work into the final output",
            "5. Verify your work is correct (run tests, check output, review changes)",
            "6. Print ONE JSON object on the LAST line of your output",
            "7. Use web_search / web_extract when you need external information",
            "8. Use skills / skill_view when you need established workflows",
            "9. Use hindsight_recall at the START to check what previous iterations learned",
            "10. Use hindsight_retain at the END to save what THIS iteration discovered",
            "11. Use todo() to plan and track your work in-session",
            "12. Prefer direct tool use over delegation for quick operations",
            "13. SELF-MODIFICATION: If your goal is to enhance the daemon or the",
            "    infinite-loop skill itself, use delegate_task() to dispatch a subagent",
            "    that makes the file changes via write_file/patch, then WAIT for its",
            "    result. When done, include 'need_reload' in your JSON's next_goal:",
            '    {"summary": "...", "next_goal": "NEXT_ITERATION need_reload"}',
            "    The daemon will detect this and restart with the updated code.",
            "",
        ]
    )

    if evolve:
        instructions.extend(
            [
                "After completing, think about what the NEXT task should be.",
                "Include a 'next_goal' field in your JSON suggesting what to focus on next.",
                "This should be a natural progression from what you just accomplished.",
            ]
        )

    instructions.extend(
        [
            "",
            "JSON FORMAT (last line of stdout):",
            '  {"summary": "what was done with actual details", "duration_seconds": <int>,',
            (
                '   "error": null|"<error>", "next_goal": "<suggested next task>",'
                if evolve
                else '   "error": null|"<error>",'
            ),
            '   "context": "detailed context for the NEXT iteration to build on this work"}',
            "",
            "  CRITICAL — The 'context' field is how the NEXT iteration knows what you did.",
            "  Include enough detail that iteration N+1 can PICK UP where you left off.",
            "  Mention specific files changed, what was done, what's pending.",
            (
                "  With --evolve, 'next_goal' becomes the goal for the next iteration."
                if evolve
                else ""
            ),
            "  With SELF-MODIFICATION goals, 'context' should describe what files were changed",
            "  and what still needs to be done, so the next iteration doesn't start from zero.",
            "",
            "  SELF-MODIFICATION SIGNAL: If you modified launch-loop.py, the skill, or",
            '  daemon config, set next_goal to "NEXT_ITERATION need_reload" to trigger',
            "  a daemon restart with the updated code.",
            "",
            "ADDITIONAL CONTEXT:",
            f"  Working directory: {workdir or os.getcwd()}",
            f"  Iteration: {iteration}",
            f"  Worker: {worker_id or 'primary'}",
            f"  Task type: {task_type}",
            "  Language: respond in the same language as the context above.",
            "",
            "Do NOT chat or ask questions. Use your tools. Do the work. Print JSON.",
        ]
    )

    # Append heartbeat instructions if heartbeat is enabled
    if heartbeat_interval > 0:
        instructions.append("")
        instructions.append("=== SESSION HEARTBEAT ===")
        instructions.append(
            f"You MUST emit a heartbeat every {heartbeat_interval} seconds "
            "so the daemon knows you are alive and working."
        )
        instructions.append(
            "Run this shell command every {heartbeat_interval}s (use terminal):"
        )
        instructions.append('  python3 -c "')
        instructions.append("import json, os, time")
        instructions.append("hb = '/tmp/infinite-loop-heartbeat-SESSION_ID'")
        instructions.append("os.makedirs(os.path.dirname(hb), exist_ok=True)")
        instructions.append("with open(hb + '.tmp', 'w') as f:")
        instructions.append("    json.dump({")
        instructions.append("        'session_id': 'SESSION_ID',")
        instructions.append("        'timestamp': time.time(),")
        instructions.append("        'pid': os.getpid()")
        instructions.append("    }, f)")
        instructions.append("os.rename(hb + '.tmp', hb)")
        instructions.append('"')
        instructions.append(
            "Replace SESSION_ID with your actual session or 'unknown-PID'."
        )
        instructions.append(
            "DO NOT skip this — if heartbeats stop, the daemon "
            "will kill and retry this session."
        )
        instructions.append("")

    # Append prompt suffix if provided
    if prompt_suffix:
        instructions.append("")
        instructions.append("EXTRA INSTRUCTIONS:")
        instructions.append(prompt_suffix)
        instructions.append("")

    return "\n".join(instructions)


def spawn_delegation_session(
    iteration: int,
    goal: str,
    context: str,
    toolsets: list[str],
    workdir: str | None,
    timeout_seconds: int,
    max_output_chars: int = 2000,
    evolve: bool = False,
    worker_id: int | None = None,
    profile: str = "",
    model: str = "",
    provider: str = "",
    prompt_suffix: str = "",
    max_turns: int = 500,
    task_type: str = "general",
    prior_context: str = "",
    worker_url: str = "",
    output_schema: dict | None = None,
    # v11.11.0: AIAgent library mode, session tracking, checkpoints
    use_library: bool = False,
    pass_session_id: bool = False,
    checkpoints: bool = False,
    # v11.12.0: session chaining, skills, ignore-rules
    resume_session_id: str = "",
    skills: str = "",
    ignore_rules: bool = False,
    # v11.13.0: yolo mode, ignore-user-config, source tagging
    yolo: bool = False,
    ignore_user_config: bool = False,
    spawn_source: str = "",
    # v11.14.0: safe-mode, accept-hooks, worktree, continue
    safe_mode: bool = False,
    accept_hooks: bool = False,
    worktree: bool = False,
    continue_session: bool = False,
    # v14.0.0: Heartbeat-based session self-healing
    heartbeat_timeout: int = 0,
    iteration_count: int = 0,
) -> dict:
    hermes_bin = find_hermes()
    prompt = _build_delegation_prompt(
        iteration=iteration,
        goal=goal,
        context=context,
        toolsets=toolsets,
        workdir=workdir,
        evolve=evolve,
        worker_id=worker_id,
        profile=profile,
        model=model,
        provider=provider,
        prompt_suffix=prompt_suffix,
        task_type=task_type,
        prior_context=prior_context,
        heartbeat_interval=heartbeat_timeout,
    )
    # Use `hermes chat -q` (non-oneshot query mode) instead of `-z` (oneshot).
    # `chat -q` keeps the session alive for multiple turns with --max-turns,
    # so delegate_task() subagent results can arrive and be collected.
    tools_str = ",".join(toolsets)
    cmd = [
        hermes_bin,
        "chat",
        "-q",
        prompt,
        "-t",
        tools_str,
        "-Q",
        "--max-turns",
        str(max_turns),
    ]
    if profile:
        cmd.extend(["--profile", profile])
    if model:
        cmd.extend(["--model", model])
    if provider:
        cmd.extend(["--provider", provider])

    # v11.11.0: --pass-session-id and --checkpoints flags for spawned sessions
    spawned_session_id = ""
    if pass_session_id:
        cmd.append("--pass-session-id")
    if checkpoints:
        cmd.append("--checkpoints")

    # v11.12.0: --resume, --skills, --ignore-rules for spawned sessions
    if resume_session_id:
        cmd.extend(["--resume", resume_session_id])
    if skills:
        cmd.extend(["-s", skills])
    if ignore_rules:
        cmd.append("--ignore-rules")

    # v11.13.0: --yolo, --ignore-user-config, --source for spawned sessions
    if yolo:
        cmd.append("--yolo")
    if ignore_user_config:
        cmd.append("--ignore-user-config")
    if spawn_source:
        cmd.extend(["--source", spawn_source])

    # v11.14.0: --safe-mode, --accept-hooks, --worktree, --continue for spawned sessions
    if safe_mode:
        cmd.append("--safe-mode")
    if accept_hooks:
        cmd.append("--accept-hooks")
    if worktree:
        cmd.append("--worktree")
    if continue_session:
        cmd.append("--continue")

    worker_tag = f" (worker #{worker_id})" if worker_id is not None else ""
    _log(f"[SPAWN{worker_tag}] hermes chat -q -t {tools_str} (iter #{iteration})")
    _log(f"[SPAWN{worker_tag}] goal: {goal[:120]}...")
    if resume_session_id:
        _log(f"[SPAWN{worker_tag}] Resuming session: {resume_session_id[:12]}...")
    # Context window tracking: log estimated prompt size
    prompt_chars = len(prompt)
    prompt_tokens_est = prompt_chars // 4  # ~4 chars per token
    _log(
        f"[SPAWN{worker_tag}] Prompt: ~{prompt_chars} chars (~{prompt_tokens_est} tokens)"
    )

    start = time.time()

    # --- Library mode (--use-library): run AIAgent.run_conversation() in-process ---
    if use_library:
        # Note: In multi-worker mode (workers > 1), library mode is handled
        # directly by _library_worker() — this path is for single-execution only.
        try:
            _log(
                f"[LIBRARY{worker_tag}] Using AIAgent.run_conversation() in-process (iter #{iteration})"
            )
            if safe_mode or accept_hooks or worktree or continue_session:
                _log(
                    "[LIBRARY] Note: --safe-mode, --accept-hooks, --worktree, --continue are subprocess-only flags (no AIAgent equivalent)"
                )
            from run_agent import AIAgent

            agent = AIAgent(
                model=model or None,
                max_iterations=max_turns,
                enabled_toolsets=list(toolsets),
                quiet_mode=True,
                ephemeral_system_prompt=prompt,
                skip_memory=True,
                checkpoints_enabled=checkpoints,
                pass_session_id=pass_session_id,
                session_id=resume_session_id if resume_session_id else None,
            )
            # Run with timeout wrapper via ThreadPoolExecutor
            import concurrent.futures

            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(agent.run_conversation, user_message=prompt)
                    conv_result = future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                elapsed = time.time() - start
                _log(f"[LIBRARY{worker_tag}] Timed out after {timeout_seconds}s")
                return {
                    "summary": f"TIMEOUT after {timeout_seconds}s (library mode)",
                    "duration_seconds": round(elapsed, 1),
                    "error": f"timed out after {timeout_seconds}s",
                    "error_type": "timeout",
                    "output": "",
                    "exit_code": -1,
                    "spawned_session_id": "",
                }

            elapsed = time.time() - start
            # Get session_id from result dict or agent object
            spawned_session_id = conv_result.get("session_id", "") or getattr(
                agent, "session_id", ""
            )
            final_response = conv_result.get("final_response", "")
            parsed_json = extract_json_from_output(final_response)

            if parsed_json:
                result_obj = {
                    "summary": parsed_json.get(
                        "summary", final_response[:max_output_chars]
                    ),
                    "duration_seconds": parsed_json.get(
                        "duration_seconds", round(elapsed, 1)
                    ),
                    "error": parsed_json.get("error"),
                    "next_goal": parsed_json.get("next_goal"),
                    "context": parsed_json.get("context", final_response[:500]),
                    "output": (
                        final_response[:max_output_chars]
                        if max_output_chars > 0
                        else final_response
                    ),
                    "stderr": "",
                    "exit_code": 0,
                    "total_output_bytes": len(final_response),
                    "truncated": max_output_chars > 0
                    and len(final_response) > max_output_chars,
                    "spawned_session_id": spawned_session_id,
                }
                # Schema validation
                schema_valid = True
                schema_error = ""
                if output_schema:
                    schema_valid, schema_error = validate_json_output(
                        parsed_json, output_schema
                    )
                    if not schema_valid:
                        _log(
                            f"[SCHEMA] Library output validation failed: {schema_error}"
                        )
                    result_obj["schema_valid"] = schema_valid
                    result_obj["schema_error"] = (
                        schema_error if not schema_valid else None
                    )
                output_len = len(final_response)
                result_obj["output_chars"] = output_len
                dur = result_obj["duration_seconds"]
                result_obj["chars_per_second"] = (
                    round(output_len / dur, 1) if dur > 0 else 0
                )
                result_obj["error_type"] = classify_error(result_obj.get("error"))
                _log(
                    f"[LIBRARY{worker_tag}] Complete in {elapsed:.1f}s (session_id={spawned_session_id[:8]}...)"
                )
                return result_obj

            # No JSON found in response
            _log(
                f"[LIBRARY{worker_tag}] No JSON extracted from response ({len(final_response)} chars)"
            )
            return {
                "summary": (
                    final_response[:max_output_chars]
                    if final_response
                    else "(no output)"
                ),
                "duration_seconds": round(elapsed, 1),
                "error": None,
                "output": (
                    final_response[:max_output_chars]
                    if max_output_chars > 0
                    else final_response
                ),
                "exit_code": 0,
                "total_output_bytes": len(final_response),
                "truncated": max_output_chars > 0
                and len(final_response) > max_output_chars,
                "spawned_session_id": spawned_session_id,
            }
        except ImportError:
            _log(
                f"[LIBRARY{worker_tag}] AIAgent not importable, falling back to subprocess mode"
            )
            # Fall through to subprocess mode
        except Exception as e:
            elapsed = time.time() - start
            _log(f"[LIBRARY{worker_tag}] FAILED: {e}, falling back to subprocess mode")
            # Fall through to subprocess mode

    # --- Worker URL mode: call the Hermes worker over HTTP ---
    if worker_url:
        url = worker_url.rstrip("/") + "/chat"
        payload = json.dumps(
            {
                "prompt": prompt,
                "toolsets": tools_str,
                "timeout": timeout_seconds,
                "workdir": workdir or "",
            }
        )
        try:
            import urllib.request

            req = urllib.request.Request(
                url,
                data=payload.encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds + 10) as resp:
                raw = resp.read().decode()
            elapsed = time.time() - start
            result_data = json.loads(raw)
            stdout = (
                result_data.get("response", raw)[:max_output_chars]
                if max_output_chars > 0
                else result_data.get("response", raw)
            )
            stderr = (
                result_data.get("stderr", "")[:1000]
                if result_data.get("stderr")
                else ""
            )
            error = result_data.get("error")
            exit_code = 0 if error is None else 1
            _log(
                f"[WORKER{worker_tag}] Response in {elapsed:.1f}s (status={result_data.get('status')})"
            )
            cap = (
                max_output_chars
                if max_output_chars > 0
                else (len(stdout) if "\n" in stdout else len(raw))
            )
            return {
                "summary": stdout[:cap],
                "duration_seconds": round(elapsed, 1),
                "error": error,
                "output": stdout[:max_output_chars] if max_output_chars > 0 else stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "total_output_bytes": len(raw),
                "truncated": max_output_chars > 0 and len(raw) > max_output_chars,
            }
        except Exception as e:
            elapsed = time.time() - start
            _log(f"[WORKER{worker_tag}] FAILED: {e}")
            return {
                "summary": f"WORKER FAILED: {e}",
                "duration_seconds": round(elapsed, 1),
                "error": str(e),
                "output": "",
                "exit_code": 1,
            }

    # --- Direct subprocess mode (default) ---
    hb_heartbeat_file: str | None = None
    subprocess_exit_code: int = -1
    proc: subprocess.Popen | None = None
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
            hb_heartbeat_file = _heartbeat_path(str(pid))

            # Start heartbeat monitor in a daemon thread
            monitor_thread = threading.Thread(
                target=_run_heartbeat_monitor,
                args=(
                    hb_heartbeat_file,
                    heartbeat_timeout,
                    session_start,
                    proc,
                    timeout_seconds,
                ),
                daemon=True,
            )
            monitor_thread.start()

            # Wait for process with heartbeat monitoring
            try:
                stdout_b, stderr_b = proc.communicate(timeout=timeout_seconds)
                elapsed = time.time() - start
                stdout = (stdout_b or "").strip()
                stderr = (stderr_b or "").strip()
                subprocess_exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                elapsed = time.time() - start
                # Kill the hung process
                _kill_session(proc, str(pid))
                _cleanup_heartbeat_file(hb_heartbeat_file)
                return {
                    "summary": f"TIMEOUT after {timeout_seconds}s",
                    "duration_seconds": round(elapsed, 1),
                    "error": f"timed out after {timeout_seconds}s",
                    "error_type": "timeout",
                    "output": "",
                    "exit_code": -1,
                    "spawned_session_id": "",
                }
        else:
            # Standard subprocess mode (no heartbeat monitoring)
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
            subprocess_exit_code = result.returncode

        # After both paths converge, extract session_id
        # v11.11.0: Extract session_id from stdout BEFORE JSON parsing
        extracted_session_id = ""
        for line in (stdout or "").split("\n"):
            stripped = line.strip()
            if stripped.startswith("session_id:"):
                extracted_session_id = stripped.split(":", 1)[1].strip()
                break
        spawned_session_id = extracted_session_id

        # Use the robust multi-line JSON parser
        parsed_json = extract_json_from_output(stdout)

        output_cap = max_output_chars if max_output_chars > 0 else len(stdout)
        stderr_cap = max_output_chars if max_output_chars > 0 else len(stderr)
        actual_output_len = len(stdout)
        was_truncated = max_output_chars > 0 and actual_output_len > max_output_chars

        if parsed_json:
            # Validate against output schema if provided
            schema_valid = True
            schema_error = ""
            if output_schema:
                schema_valid, schema_error = validate_json_output(
                    parsed_json, output_schema
                )
                if not schema_valid:
                    _log(f"[SCHEMA] Output schema validation failed: {schema_error}")

            result_obj = {
                "summary": parsed_json.get("summary", stdout[:output_cap]),
                "duration_seconds": parsed_json.get(
                    "duration_seconds", round(elapsed, 1)
                ),
                "error": (
                    parsed_json.get("error") or schema_error
                    if not schema_valid
                    else parsed_json.get("error")
                ),
                "next_goal": parsed_json.get("next_goal"),
                "context": parsed_json.get("context", ""),
                "output": stdout[:output_cap],
                "stderr": stderr[:stderr_cap],
                "exit_code": subprocess_exit_code,
                "schema_valid": schema_valid,
                "schema_error": schema_error if not schema_valid else None,
            }
            # Track throughput stats
            output_len = len(stdout)
            result_obj["output_chars"] = output_len
            result_obj["total_output_bytes"] = actual_output_len
            result_obj["truncated"] = was_truncated
            dur = result_obj["duration_seconds"]
            result_obj["chars_per_second"] = (
                round(output_len / dur, 1) if dur > 0 else 0
            )
            result_obj["error_type"] = classify_error(result_obj.get("error"))
            result_obj["spawned_session_id"] = spawned_session_id
            return result_obj

        # No JSON found — try to extract a meaningful summary
        summary = stdout[:output_cap] if stdout else "(no output)"
        if subprocess_exit_code != 0:
            summary = f"FAILED (exit {subprocess_exit_code}): {stderr[:300]}"
            return {
                "summary": summary,
                "duration_seconds": round(elapsed, 1),
                "error": f"hermes exit {subprocess_exit_code}",
                "error_type": "unknown",
                "output": (stdout + "\n" + stderr)[:output_cap],
                "stderr": stderr[:stderr_cap],
                "exit_code": subprocess_exit_code,
                "total_output_bytes": actual_output_len,
                "truncated": was_truncated,
                "spawned_session_id": spawned_session_id,
            }

        return {
            "summary": summary,
            "duration_seconds": round(elapsed, 1),
            "error": None,
            "output": stdout[:output_cap],
            "stderr": stderr[:stderr_cap],
            "exit_code": subprocess_exit_code,
            "total_output_bytes": actual_output_len,
            "truncated": was_truncated,
            "spawned_session_id": spawned_session_id,
        }

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        _log(f"[TIMEOUT] Hermes session timed out after {timeout_seconds}s")
        return {
            "summary": f"TIMEOUT after {timeout_seconds}s",
            "duration_seconds": round(elapsed, 1),
            "error": f"timed out after {timeout_seconds}s",
            "error_type": "timeout",
            "output": "",
            "exit_code": -1,
            "spawned_session_id": spawned_session_id if spawned_session_id else "",
        }
    except FileNotFoundError:
        return {
            "summary": "FAILED: hermes binary not found",
            "duration_seconds": 0,
            "error": "hermes binary not found on PATH",
            "error_type": "network",
            "output": "",
            "exit_code": -1,
            "spawned_session_id": "",
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "summary": f"FAILED: {e}",
            "duration_seconds": round(elapsed, 1),
            "error": str(e),
            "error_type": classify_error(str(e)),
            "output": "",
            "exit_code": -1,
            "spawned_session_id": spawned_session_id if spawned_session_id else "",
        }


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


def _sleep_with_shutdown_check(seconds: float) -> bool:
    """Sleep for N seconds, checking for shutdown signals every second.

    Returns True if shutdown was requested (caller should exit), False if slept full duration.
    """
    elapsed = 0
    while elapsed < seconds:
        if _shutdown_requested:
            return True
        time.sleep(1)
        elapsed += 1
    return False


def _send_desktop_notification(
    summary: str, duration: float = 0, error: str | None = None
):
    """Send a desktop notification via notify-send (Linux only)."""
    notify_bin = shutil.which("notify-send")
    if not notify_bin:
        return
    try:
        title = "Infinite Loop"
        body = summary[:120]
        if duration > 0:
            body += f" ({duration:.0f}s)"
        if error:
            body += f" ⚠ {error[:60]}"
            subprocess.run([notify_bin, title, body], timeout=3)
        else:
            subprocess.run([notify_bin, "--", title, body], timeout=3)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _pushbullet_notify(api_token: str, title: str, body: str) -> bool:
    """Send a push notification via Pushbullet (https://www.pushbullet.com).

    Uses the Pushbullet API v2 POST /pushes endpoint.
    Returns True on success, False on failure.
    Requires a Pushbullet API access token (Settings → Account → Access Tokens).
    Uses stdlib urllib only — no external dependencies.
    """
    if not api_token:
        return False
    try:
        payload = json.dumps(
            {
                "type": "note",
                "title": title[:256],
                "body": body[:4096],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://api.pushbullet.com/v2/pushes",
            data=payload,
            headers={
                "Access-Token": api_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        _log(f"[PUSHBULLET] Notification failed: {e}", level="WARN")
        return False


def _ntfy_notify(
    topic: str, title: str, body: str, server: str = "https://ntfy.sh"
) -> bool:
    """Send a push notification via ntfy (https://ntfy.sh).

    Uses ntfy's simple HTTP PUT API.
    Returns True on success, False on failure.
    By default uses the public ntfy.sh server; you can also self-host an ntfy server.
    Uses stdlib urllib only — no external dependencies.
    """
    if not topic:
        return False
    topic = topic.strip().strip("/")
    if not topic:
        return False
    url = f"{server.rstrip('/')}/{topic}"
    try:
        payload = body[:4096].encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Title": title[:256],
                "Content-Type": "text/plain; charset=utf-8",
                "Priority": "default",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError) as e:
        _log(f"[NTFY] Notification failed: {e}", level="WARN")
        return False


def _send_per_iteration_notifications(
    summary: str,
    duration: float,
    error: str | None,
    notify_desktop_enabled: bool,
    notify_pushbullet: str,
    notify_ntfy: str,
    notify_ntfy_server: str,
):
    """Send per-iteration notifications to all configured channels."""
    if notify_desktop_enabled:
        _send_desktop_notification(summary, duration, error)
    title = "Infinite Loop Iteration"
    body = summary[:200]
    if duration > 0:
        body += f" ({duration:.0f}s)"
    if error:
        body += f" ⚠ {error[:100]}"
    if notify_pushbullet:
        _pushbullet_notify(notify_pushbullet, title, body)
    if notify_ntfy:
        _ntfy_notify(notify_ntfy, title, body, notify_ntfy_server)


def _send_completion_notification(
    state: dict,
    notify_pushbullet: str = "",
    notify_ntfy: str = "",
    notify_ntfy_server: str = "https://ntfy.sh",
) -> None:
    """Send a summary notification when the daemon finishes."""
    if not state:
        return
    stats = state.get("stats", {})
    total = state.get("total_iterations", 0)
    status = state.get("status", "unknown")
    msg = (
        f"Status: {status}\n"
        f"Iterations: {total}\n"
        f"Success: {stats.get('success_count', 0)}\n"
        f"Errors: {stats.get('error_count', 0)}\n"
        f"Total time: {stats.get('total_duration_seconds', 0):.0f}s"
    )

    # Desktop notify-send
    notify_bin = shutil.which("notify-send")
    if notify_bin:
        try:
            subprocess.run(["notify-send", "Infinite Loop Complete", msg], timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Pushbullet
    if notify_pushbullet:
        _pushbullet_notify(notify_pushbullet, "Infinite Loop Complete", msg)

    # ntfy
    if notify_ntfy:
        _ntfy_notify(notify_ntfy, "Infinite Loop Complete", msg, notify_ntfy_server)


# ======================================================
# Automatic Error Recovery — per-type adaptation engine
# ======================================================

_ERROR_SEVERITY = {
    "timeout": 4,
    "network": 3,
    "schema": 2,
    "unknown": 1,
    "heartbeat": 5,
}

_ERROR_THRESHOLDS = {
    "timeout": {"mild": 3, "moderate": 5, "stop": 8},
    "network": {"mild": 2, "moderate": 4, "stop": 6},
    "schema": {"mild": 3, "moderate": None, "stop": 5},
    "unknown": {"mild": 3, "moderate": 5, "stop": 7},
    "heartbeat": {"mild": 3, "moderate": 5, "stop": 7},
}

# --- Heartbeat constants for session self-healing ---
HEARTBEAT_DIR = "/tmp"
HEARTBEAT_PREFIX = "infinite-loop-heartbeat-"
HEARTBEAT_INTERVAL = 30  # seconds between heartbeat writes (prompt tells session)
HEARTBEAT_GRACE_FACTOR = 2.0  # grace = timeout * 2
HEARTBEAT_POLL_INTERVAL = 5  # daemon polling interval (seconds)
HEARTBEAT_KILL_GRACE = 5  # seconds between SIGTERM and SIGKILL


def _pick_primary_error(types: list[str]) -> str:
    """Return the most severe error type from a list."""
    return max(types, key=lambda t: _ERROR_SEVERITY.get(t, 0))


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
    log_fn: callable = None,
) -> tuple:
    """
    Adapt runtime parameters based on error type and history.

    Returns (session_timeout, cooldown, cooldown_mode, use_library, workers, actions_taken)
    where actions_taken is a list of human-readable strings.
    """
    global _ORIGINAL_SESSION_TIMEOUT, _ORIGINAL_COOLDOWN
    global _ORIGINAL_USE_LIBRARY, _ORIGINAL_WORKERS

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
    thresholds = _ERROR_THRESHOLDS.get(
        error_type, {"mild": 999, "moderate": 999, "stop": 999}
    )

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
            actions.append(
                f"[MITIGATION] Timeout errors: increased timeout to {new_timeout}s"
            )
        elif error_type == "network":
            new_cooldown = min(300, max(cooldown, cooldown * 4))  # +300%
            new_mode = "fixed"
            actions.append(
                f"[MITIGATION] Network errors: elevated cooldown to {new_cooldown}s"
            )
        elif error_type == "schema":
            # Mild: no timeout/cooldown change — schema is content, not infra
            actions.append(
                "[MITIGATION] Schema errors: monitoring (no parameter changes yet)"
            )
        elif error_type == "unknown":
            new_cooldown = min(120, max(cooldown, cooldown * 2))  # +100%
            new_mode = "fixed"
            actions.append(
                f"[MITIGATION] Unknown errors: elevated cooldown to {new_cooldown}s"
            )

        new_level = 1

    if new_level >= 2 and level_before < 2:
        # Level 2: moderate mitigation
        if error_type == "timeout":
            new_cooldown = min(120, max(cooldown, cooldown * 2))
            new_mode = "fixed"
            actions.append(
                f"[MITIGATION] Timeout errors (escalated): cooldown → {new_cooldown}s"
            )
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
        actions.append(
            f"[MITIGATION] STOP: {stop_reason} after {count} {error_type} errors"
        )
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


class GoalSpec:
    """A goal with optional profile/model/provider overrides.

    Parsed from pipe-separated goals file format: goal|profile|model|provider.
    Empty fields fall back to daemon-level CLI args.
    """

    def __init__(
        self, goal: str, profile: str = "", model: str = "", provider: str = ""
    ):
        self.goal = goal
        self.profile = profile
        self.model = model
        self.provider = provider

    def __str__(self):
        return self.goal[:60]


# ---------------------------------------------------------------------------
# Heartbeat helpers (Session Self-Healing)
# ---------------------------------------------------------------------------


def _heartbeat_path(identifier: str) -> str:
    """Return the heartbeat file path for a given session ID or PID."""
    return os.path.join(HEARTBEAT_DIR, f"{HEARTBEAT_PREFIX}{identifier}")


def _read_heartbeat(heartbeat_file: str) -> dict | None:
    """Read and parse a heartbeat file. Returns None on any error."""
    try:
        with open(heartbeat_file) as f:
            return json.loads(f.read().strip())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


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


def _heartbeat_age(heartbeat_file: str) -> float | None:
    """Return seconds since the heartbeat file was last modified, or None if absent."""
    try:
        mtime = os.path.getmtime(heartbeat_file)
        return time.time() - mtime
    except OSError:
        return None


def _monitor_heartbeat(
    heartbeat_file: str,
    timeout: int,
    session_start: float,
    proc: subprocess.Popen | None,
) -> dict:
    """Monitor a single heartbeat file in a blocking loop.

    Polls every HEARTBEAT_POLL_INTERVAL seconds. Returns a status dict:
      {"status": "alive"|"expired"|"lost"|"completed",
       "age_seconds": ...,
       "last_heartbeat_data": ...|None}

    Designed to run in a daemon thread alongside the subprocess.
    """
    grace_period = int(timeout * HEARTBEAT_GRACE_FACTOR) if timeout > 0 else 0

    while not _shutdown_requested:
        # If the subprocess has exited normally, stop monitoring
        if proc is not None and proc.poll() is not None:
            return {
                "status": "completed",
                "age_seconds": 0,
                "last_heartbeat_data": None,
            }

        age = _heartbeat_age(heartbeat_file)
        hb_data = _read_heartbeat(heartbeat_file) if age is not None else None

        if age is None:
            elapsed = time.time() - session_start
            if elapsed > timeout + grace_period:
                _log(f"[HEARTBEAT] Lost — never appeared after {elapsed:.0f}s")
                return {
                    "status": "lost",
                    "age_seconds": elapsed,
                    "last_heartbeat_data": None,
                }
        elif age > timeout:
            if age > timeout + grace_period:
                _log(
                    f"[HEARTBEAT] DEAD — last heartbeat {age:.0f}s ago (> {timeout + grace_period}s)"
                )
                return {
                    "status": "expired",
                    "age_seconds": age,
                    "last_heartbeat_data": hb_data,
                }
            else:
                _log(
                    f"[HEARTBEAT] Grace — {age:.0f}s since last heartbeat (timeout={timeout}s, grace={grace_period}s)",
                    level="DEBUG",
                )
        else:
            _log(f"[HEARTBEAT] Alive — {age:.1f}s ago", level="DEBUG")

        time.sleep(HEARTBEAT_POLL_INTERVAL)

    return {"status": "alive", "age_seconds": 0, "last_heartbeat_data": None}


def _run_heartbeat_monitor(
    heartbeat_file: str,
    timeout: int,
    session_start: float,
    proc: subprocess.Popen | None,
    timeout_seconds: int,
) -> dict:
    """Run _monitor_heartbeat in a daemon thread with a timeout cap.

    Returns the heartbeat status dict. If the monitor thread doesn't finish
    within ``timeout_seconds + grace + 60``, forcibly stops.
    """
    result_container: dict = {}

    def _monitor_wrapper():
        result_container["result"] = _monitor_heartbeat(
            heartbeat_file, timeout, session_start, proc
        )

    t = threading.Thread(target=_monitor_wrapper, daemon=True)
    t.start()
    max_wait = (
        timeout_seconds + int(timeout * HEARTBEAT_GRACE_FACTOR) + 60
        if timeout > 0
        else timeout_seconds
    )
    t.join(timeout=max_wait + 60)
    if t.is_alive():
        _log("[HEARTBEAT] Monitor thread timed out — forcibly stopping")
        return {"status": "alive", "age_seconds": 0, "last_heartbeat_data": None}
    return result_container.get(
        "result", {"status": "alive", "age_seconds": 0, "last_heartbeat_data": None}
    )


def _kill_session(proc: subprocess.Popen | None, session_id: str) -> None:
    """Force-kill a session process (SIGTERM, then SIGKILL after 5s)."""
    if proc is None or proc.poll() is not None:
        return
    short_id = session_id[:12] if session_id else "unknown"
    _log(f"[HEARTBEAT] Killing hung session {short_id}...")
    proc.terminate()
    try:
        proc.wait(timeout=HEARTBEAT_KILL_GRACE)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)
    _log(f"[HEARTBEAT] Session {short_id} killed (exit={proc.returncode})")


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
        _log(f"[HEARTBEAT] Cleaned up {removed} stale heartbeat file(s)")


def _cleanup_heartbeat_file(heartbeat_file: str | None) -> None:
    """Remove a single heartbeat file (on normal session completion)."""
    if heartbeat_file and os.path.exists(heartbeat_file):
        try:
            os.remove(heartbeat_file)
        except OSError:
            pass


def _execute_iteration(
    state: dict,
    workers: int,
    goals_list: list,
    goals_index: int,
    spawn_goal: GoalSpec,
    iteration_count: int,
    progressive_context: str,
    toolsets: list[str],
    workdir: str | None,
    evolve: bool,
    profile: str,
    model: str,
    provider: str,
    max_turns: int,
    task_type: str,
    failure_context: str,
    effective_worker_url: str,
    session_timeout: int,
    max_output_chars: int,
    use_library: bool,
    pass_session_id: bool,
    checkpoints: bool,
    resume_session_id: str,
    skills: str,
    ignore_rules: bool,
    yolo: bool,
    ignore_user_config: bool,
    spawn_source: str,
    safe_mode: bool,
    accept_hooks: bool,
    worktree: bool,
    continue_session: bool,
    prompt_suffix: str,
    max_retries: int,
    retry_delay: int,
    output_schema: dict | None,
    git: bool,
    store_git_diff: bool,
    heartbeat_timeout: int = 0,
) -> tuple[list[dict], GoalSpec, bool]:
    """Spawn one or more Hermes sessions for the current iteration.

    Handles both single-session (with optional retry) and multi-worker
    parallel execution (ThreadPoolExecutor or multiprocessing library mode).

    Returns:
        (all_results, spawn_goal, use_library) — the result list,
        the resolved spawn goal, and the possibly-mutated use_library flag.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_results: list[dict] = []

    # Use goals_file goal if active, otherwise the primary goal
    spawn_goal = spawn_goal if len(goals_list) > 1 else goals_list[0]

    if workers > 1:
        # Multi-goal parallel workers: distribute goals from goals_list
        # across workers cyclically. Worker 0 gets goal[goals_index],
        # worker 1 gets goal[goals_index+1], etc.
        if use_library:
            # Concurrent library mode — use multiprocessing instead of threading
            # because AIAgent cannot be safely shared across threads (GIL + state).
            # Each worker creates its own AIAgent from scratch.
            try:
                tasks = []
                for w_id in range(workers):
                    # Each worker gets the next goal from the list (if multi-goal mode)
                    worker_goal_spec = spawn_goal
                    if len(goals_list) > 1:
                        idx = (goals_index + w_id) % len(goals_list)
                        worker_goal_spec = goals_list[idx]
                        _log(f"[WORKER #{w_id}] Goal: {worker_goal_spec.goal[:100]}...")

                    # Merge daemon-level with goal-level overrides
                    effective_profile = worker_goal_spec.profile or profile
                    effective_model = worker_goal_spec.model or model
                    effective_provider = worker_goal_spec.provider or provider

                    worker_prompt = _build_delegation_prompt(
                        iteration=iteration_count,
                        goal=worker_goal_spec.goal,
                        context=f"{progressive_context}\n(worker #{w_id} of {workers})",
                        toolsets=toolsets,
                        workdir=workdir,
                        evolve=evolve,
                        worker_id=w_id,
                        profile=effective_profile,
                        model=effective_model,
                        provider=effective_provider,
                        max_turns=max_turns,
                        task_type=task_type,
                        prior_context=failure_context,
                    )

                    library_config = {
                        "model": effective_model,
                        "max_iterations": max_turns,
                        "enabled_toolsets": list(toolsets),
                        "checkpoints_enabled": checkpoints,
                        "pass_session_id": pass_session_id,
                        "session_id": (
                            resume_session_id if resume_session_id else None
                        ),
                        "timeout_seconds": session_timeout,
                        "max_output_chars": max_output_chars,
                        "output_schema": output_schema,
                    }
                    tasks.append((library_config, worker_prompt, w_id))

                all_results = _run_library_workers_parallel(tasks, workers)

                # Add worker_id to results (starmap doesn't auto-tag)
                for r in all_results:
                    r.setdefault("worker_id", 0)

            except Exception as e:
                _log(
                    f"[LIBRARY] Library mode failed in multi-worker: {e}, falling back to subprocess"
                )
                use_library = False
                # Fall through to subprocess path below
            else:
                # Skip subprocess path when library mode succeeded
                pass

        if not use_library:
            # Original ThreadPoolExecutor path (unchanged)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for w_id in range(workers):
                    # Each worker gets the next goal from the list (if multi-goal mode)
                    worker_goal_spec = spawn_goal
                    if len(goals_list) > 1:
                        idx = (goals_index + w_id) % len(goals_list)
                        worker_goal_spec = goals_list[idx]
                        _log(f"[WORKER #{w_id}] Goal: {worker_goal_spec.goal[:100]}...")

                    # Merge daemon-level with goal-level overrides
                    effective_profile = worker_goal_spec.profile or profile
                    effective_model = worker_goal_spec.model or model
                    effective_provider = worker_goal_spec.provider or provider

                    fut = executor.submit(
                        spawn_delegation_session,
                        iteration=iteration_count,
                        goal=worker_goal_spec.goal,
                        context=f"{progressive_context}\n(worker #{w_id} of {workers})",
                        toolsets=toolsets,
                        workdir=workdir,
                        timeout_seconds=session_timeout,
                        max_output_chars=max_output_chars,
                        evolve=evolve,
                        worker_id=w_id,
                        profile=effective_profile,
                        model=effective_model,
                        provider=effective_provider,
                        max_turns=max_turns,
                        task_type=task_type,
                        prior_context=failure_context,
                        worker_url=effective_worker_url,
                        output_schema=output_schema,
                        use_library=False,
                        pass_session_id=pass_session_id,
                        checkpoints=checkpoints,
                        # v11.12.0: session chaining, skills, ignore-rules
                        resume_session_id=resume_session_id,
                        skills=skills,
                        ignore_rules=ignore_rules,
                        yolo=yolo,
                        ignore_user_config=ignore_user_config,
                        spawn_source=spawn_source,
                        # v11.14.0: safe-mode, accept-hooks, worktree, continue
                        safe_mode=safe_mode,
                        accept_hooks=accept_hooks,
                        worktree=worktree,
                        continue_session=continue_session,
                        # v14.0.0: Heartbeat-based session self-healing
                        heartbeat_timeout=heartbeat_timeout,
                        iteration_count=iteration_count,
                    )
                    futures[fut] = w_id

                for fut in as_completed(futures):
                    w_id = futures[fut]
                    try:
                        result = fut.result()
                        result["worker_id"] = w_id
                        all_results.append(result)
                    except Exception as e:
                        all_results.append(
                            {
                                "worker_id": w_id,
                                "summary": f"WORKER #{w_id} FAILED: {e}",
                                "duration_seconds": 0,
                                "error": str(e),
                                "output": "",
                                "exit_code": -1,
                            }
                        )
    else:
        # Single execution with optional retry
        # Merge daemon-level with goal-level overrides
        single_profile = spawn_goal.profile or profile
        single_model = spawn_goal.model or model
        single_provider = spawn_goal.provider or provider

        result = None
        for attempt in range(max_retries + 1):
            result = spawn_delegation_session(
                iteration=iteration_count,
                goal=spawn_goal.goal,
                context=progressive_context,
                toolsets=toolsets,
                workdir=workdir,
                timeout_seconds=session_timeout,
                max_output_chars=max_output_chars,
                evolve=evolve,
                profile=single_profile,
                model=single_model,
                provider=single_provider,
                prompt_suffix=prompt_suffix,
                max_turns=max_turns,
                task_type=task_type,
                prior_context=failure_context,
                worker_url=effective_worker_url,
                output_schema=output_schema,
                use_library=use_library,
                pass_session_id=pass_session_id,
                checkpoints=checkpoints,
                # v11.12.0: session chaining, skills, ignore-rules
                resume_session_id=resume_session_id,
                skills=skills,
                ignore_rules=ignore_rules,
                yolo=yolo,
                ignore_user_config=ignore_user_config,
                spawn_source=spawn_source,
                # v11.14.0: safe-mode, accept-hooks, worktree, continue
                safe_mode=safe_mode,
                accept_hooks=accept_hooks,
                worktree=worktree,
                continue_session=continue_session,
                # v14.0.0: Heartbeat-based session self-healing
                heartbeat_timeout=heartbeat_timeout,
                iteration_count=iteration_count,
            )
            if not result.get("error") or attempt >= max_retries:
                break
            _log(
                f"[RETRY] Attempt {attempt + 1}/{max_retries} failed: {result.get('error', '')[:100]}"
            )
            if retry_delay > 0:
                delay = retry_delay * (attempt + 1)
                _log(f"[RETRY] Waiting {delay}s before retry...")
                time.sleep(delay)
        all_results.append(result)

    state.pop("pending_iteration", None)
    return all_results, spawn_goal, use_library


def _merge_worker_results(
    all_results: list[dict],
    max_output_chars: int,
    consecutive_errors: int,
    state: dict,
) -> dict:
    """Merge results from one or more workers into a single summary.

    Aggregates errors, durations, contexts, summaries, and outputs from all
    worker results. Classifies error types and updates per-type counters
    in state for automatic error recovery.

    Returns a dict with keys:
        combined_error, total_duration, primary_error_type,
        consecutive_successes, consecutive_errors, next_goal, next_context,
        combined_summary, combined_output
    """
    errors = [r.get("error") for r in all_results if r.get("error")]
    durations = [r.get("duration_seconds", 0) for r in all_results]
    total_duration = max(durations) if len(durations) > 1 else durations[0]
    combined_error = "; ".join(errors) if errors else None

    # --- Error type classification (for automatic error recovery) ---
    primary_error_type = None
    consecutive_successes = 0
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
            primary_error_type = "unknown"

        # Update per-type counters
        state.setdefault("error_type_counts", {})
        state["error_type_counts"][primary_error_type] = (
            state["error_type_counts"].get(primary_error_type, 0) + 1
        )

        # Log error type diagnosis
        _log(
            f"[ERROR-TYPE] {primary_error_type} "
            f"(total: {state['error_type_counts'][primary_error_type]})"
        )
    else:
        consecutive_successes = state.get("consecutive_successes", 0) + 1

    # Track consecutive errors for legacy backoff
    consecutive_errors = 0 if not combined_error else consecutive_errors + 1

    next_goal = None
    next_context = ""

    # Merge contexts from ALL workers — collect all, then combine
    worker_contexts = []
    for r in all_results:
        if r.get("next_goal"):
            next_goal = r["next_goal"]
        if r.get("context"):
            worker_contexts.append((r.get("worker_id", 0), r["context"]))
    if worker_contexts:
        if len(worker_contexts) == 1:
            next_context = worker_contexts[0][1]
        else:
            # Prefix each context with its worker ID for readability
            parts = [f"[Worker #{wid}]: {c}" for wid, c in worker_contexts]
            next_context = "\n\n".join(parts)

    summaries = [
        r.get("summary", f"Worker #{r.get('worker_id', 0)} completed")
        for r in all_results
    ]
    combined_summary = " | ".join(summaries) if len(summaries) > 1 else summaries[0]
    combined_output = "\n---\n".join(r.get("output", "") for r in all_results)[
        :max_output_chars
    ]

    if combined_error:
        _log(f"[FAIL] {combined_error}")
    else:
        _log(f"[OK] Completed in {total_duration}s")
    _log(f"[SUMMARY] {combined_summary[:180]}")

    return {
        "combined_error": combined_error,
        "total_duration": total_duration,
        "primary_error_type": primary_error_type,
        "consecutive_successes": consecutive_successes,
        "consecutive_errors": consecutive_errors,
        "next_goal": next_goal,
        "next_context": next_context,
        "combined_summary": combined_summary,
        "combined_output": combined_output,
    }


def _handle_backoff(
    combined_error: str | None,
    retry_delay: int,
    consecutive_errors: int,
    adapt_actions: list[str],
    state: dict,
    status_file: str,
    iteration_count: int,
) -> bool:
    """Apply exponential backoff delay when errors occur.

    Only applied if no automatic mitigation took over (adapt_actions is empty).
    Catches KeyboardInterrupt during the sleep and signals the loop should stop.

    Returns:
        True if the caller should return (KeyboardInterrupt caught),
        False otherwise.
    """
    # --- Legacy: Basic backoff (overlaid with the above) ---
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
            return True
    return False


def _detect_convergence(
    convergence_stop: bool,
    iteration_count: int,
    convergence_window: int,
    existing_summaries: list,
    combined_summary: str,
    convergence_threshold: float,
    state: dict,
    status_file: str,
) -> bool:
    """
    Check if recent iteration summaries have converged (stopped making progress).
    Returns True if converged (caller should stop the loop).
    """
    # Check if summaries have stopped making progress — all recent
    # iterations are saying essentially the same thing.
    if convergence_stop and iteration_count >= convergence_window:
        # Skip convergence check for empty or too-short summaries (false positive guard)
        trimmed = combined_summary[:200].strip()
        if len(trimmed) < 20:
            _log(
                f"[CONVERGENCE] SKIP — summary too short ({len(trimmed)} chars) "
                f"for meaningful comparison"
            )
            return False
        is_converged, avg_sim = check_convergence(
            existing_summaries + [combined_summary[:200]],
            threshold=convergence_threshold,
            window=convergence_window,
        )
        if is_converged:
            _log(
                f"[CONVERGENCE] STOP — Last {convergence_window} iterations have "
                f"{avg_sim:.2f} similarity (threshold={convergence_threshold})"
            )
            state["status"] = (
                f"stopped: convergence ({avg_sim:.2f} similarity "
                f"over {convergence_window} iters)"
            )
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            state["convergence"] = {
                "avg_similarity": round(avg_sim, 3),
                "window": convergence_window,
                "threshold": convergence_threshold,
            }
            write_ledger(state)
            write_status_file(
                status_file, state, iteration_count, "stopped: convergence"
            )
            return True
        elif avg_sim > 0.5:
            _log(
                f"[CONVERGENCE] {avg_sim:.2f} similarity over "
                f"{convergence_window} iters (threshold={convergence_threshold})"
            )
    return False


def _compact_summaries(
    existing_summaries: list,
    compact_every: int,
    iteration_count: int,
    combined_summary: str,
) -> tuple[list, bool]:
    """
    Compact the rolling window of summaries: keep last N entries as full summaries,
    condense older ones to one-liners. Returns (updated_summaries, was_compacted).
    """
    is_compacted = False
    if compact_every > 0 and iteration_count % compact_every == 0:
        is_compacted = True
        # Keep last N entries as full summaries, condense older ones
        keep_full = max(compact_every, 10)  # at least 10 full summaries
        condensed = 0
        new_summaries = []
        for i, s in enumerate(existing_summaries):
            if i >= len(existing_summaries) - keep_full:
                # Keep full summary
                new_summaries.append(s)
            else:
                # Condense to one-liner (first 80 chars)
                short = s[:80].replace("\n", " ")
                condensed += 1
        # Add the single condensed placeholder
        if condensed > 0:
            new_summaries.insert(0, f"[{condensed} earlier iterations condensed]")
        existing_summaries = new_summaries
    existing_summaries.append(combined_summary[:200])
    return existing_summaries, is_compacted


def _build_iteration_record(
    iteration_count: int,
    task_type: str,
    spawn_goal,
    goals_list: list,
    iteration_start_time: str,
    total_duration: float,
    combined_summary: str,
    is_compacted: bool,
    combined_error: str | None,
    all_results: list,
    workers: int,
    toolsets: list[str],
    git_before: dict,
    git_after: dict,
    git: bool,
    git_commit_hash: str | None,
    next_goal: str | None,
    next_context: str | None,
    resume: bool,
    pass_session_id: bool,
    state: dict,
    sys_before: dict,
) -> dict:
    """
    Build the per-iteration record dict with all fields (duration, error,
    git_after, system, classification, spawned_session_id, etc.).
    """
    # Record iteration
    record: dict = {
        "n": iteration_count,
        "task_type": task_type,
        "goal": spawn_goal.goal[:200] if len(goals_list) > 1 else "",
        "started_at": iteration_start_time,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": total_duration,
        "summary": combined_summary[:500],
        "compacted": is_compacted,
        "error": combined_error,
        "exit_code": 0 if not combined_error else 1,
        "toolsets": toolsets[:],  # snapshot of actual toolsets used
        "workers": workers if workers > 1 else None,
        "worker_results": (
            [
                {
                    "worker": r.get("worker_id", 0),
                    "summary": r.get("summary", "")[:200],
                    "error": r.get("error"),
                    "error_type": r.get("error_type"),
                    "duration_seconds": r.get("duration_seconds", 0),
                    "output_chars": r.get("output_chars", 0),
                    "chars_per_second": r.get("chars_per_second", 0),
                    "total_output_bytes": r.get("total_output_bytes", 0),
                    "truncated": r.get("truncated", False),
                }
                for r in all_results
            ]
            if workers > 1
            else None
        ),
    }
    if not workers > 1 and all_results:
        record["output_chars"] = all_results[0].get("output_chars", 0)
        record["chars_per_second"] = all_results[0].get("chars_per_second", 0)
        record["total_output_bytes"] = all_results[0].get("total_output_bytes", 0)
        record["truncated"] = all_results[0].get("truncated", False)
        if all_results[0].get("stderr"):
            record["stderr"] = all_results[0]["stderr"][:500]
        if all_results[0].get("schema_valid") is not None:
            record["schema_valid"] = all_results[0]["schema_valid"]
            if all_results[0].get("schema_error"):
                record["schema_error"] = all_results[0]["schema_error"]
    if git:
        record["git_before"] = git_before
        record["git_after"] = git_after
    if git_commit_hash:
        record["git_commit"] = git_commit_hash
    if next_goal:
        record["next_goal"] = next_goal
    if next_context:
        record["next_context"] = next_context

    # v11.11.0: Store spawned_session_id in ledger for session tracking
    if all_results and not workers > 1:
        sid = all_results[0].get("spawned_session_id", "")
        if sid:
            record["spawned_session_id"] = sid
    elif workers > 1:
        # Store per-worker session IDs in worker_results
        for wr in record.get("worker_results", []):
            w_id = wr.get("worker", 0)
            for r in all_results:
                if r.get("worker_id") == w_id and r.get("spawned_session_id"):
                    wr["spawned_session_id"] = r["spawned_session_id"]
                    break

    # v11.12.0: Session chaining — persist spawned_session_id as resume token
    if resume and pass_session_id and all_results:
        # Capture from single worker
        if not workers > 1:
            sid = all_results[0].get("spawned_session_id", "")
            if sid:
                state["resume_session_id"] = sid
        # Collect all session IDs into rolling history
        state.setdefault("session_id_history", [])
        for r in all_results:
            sid = r.get("spawned_session_id", "")
            if sid and sid not in state["session_id_history"][-100:]:
                state["session_id_history"].append(sid)
        state["session_id_history"] = state["session_id_history"][-100:]

    # System resource tracking
    sys_after = get_system_usage()
    sys_diff = get_system_usage_diff(sys_before, sys_after)
    if sys_diff:
        record["system"] = sys_diff

    # Classify iteration progress for analytics / dashboard
    record["classification"] = _classify_progress(
        summary=record.get("summary", ""),
        git_before=git_before if git else None,
        git_after=git_after if git else None,
        error=record.get("error"),
    )
    return record


def _handle_notifications(
    notify_desktop: bool,
    notify_pushbullet: str,
    notify_ntfy: str,
    combined_summary: str,
    total_duration: float,
    combined_error: str | None,
    notify_ntfy_server: str,
) -> None:
    """
    Dispatch desktop + pushbullet + ntfy notifications for each iteration.
    """
    if notify_desktop or notify_pushbullet or notify_ntfy:
        _send_per_iteration_notifications(
            combined_summary[:120],
            total_duration,
            combined_error,
            notify_desktop,
            notify_pushbullet,
            notify_ntfy,
            notify_ntfy_server,
        )


def _handle_callbacks(
    http_callback: str,
    record: dict,
    notify_cmd: str | None,
    on_error_cmd: str | None,
    combined_error: str | None,
    state: dict | None = None,
) -> None:
    """
    Dispatch HTTP callback, notify-cmd, and on-error-cmd for each iteration.

    When state is provided, the HTTP callback payload is enriched with
    daemon-level metrics including stats, ETA, and resource tracking.
    """
    # Build enriched payload if state is available
    if http_callback and state:
        payload = {
            "iteration": record,
            "state": {
                "status": state.get("status"),
                "total_iterations": state.get("total_iterations", 0),
                "max_iterations": state.get("max_iterations", 0),
                "started_at": state.get("started_at"),
                "last_updated": state.get("last_updated"),
                "goal": (state.get("initial_command") or "")[:200],
                "evolved_goal": state.get("evolved_goal", ""),
                "cooldown": state.get("cooldown", 0),
                "consecutive_errors": state.get("stats", {}).get(
                    "consecutive_errors", 0
                ),
                "eta": state.get("eta", {}),
            },
            "stats": {
                "success_count": state.get("stats", {}).get("success_count", 0),
                "error_count": state.get("stats", {}).get("error_count", 0),
                "total_duration_seconds": state.get("stats", {}).get(
                    "total_duration_seconds", 0
                ),
                "avg_duration_seconds": state.get("stats", {}).get(
                    "avg_duration_seconds", 0
                ),
            },
            "system": record.get("system", {}),
            "pid": os.getpid(),
        }
    else:
        payload = record

    # --- HTTP callback ---
    if http_callback:
        try:
            import urllib.request

            notify_data = json.dumps(payload, default=str).encode("utf-8")
            req = urllib.request.Request(
                http_callback,
                data=notify_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            _log(f"[HTTP CB] Callback to {http_callback} failed: {e}")

    # --- Notification callback ---
    if notify_cmd:
        try:
            notify_data = json.dumps(record, default=str)
            subprocess.run(
                ["sh", "-c", notify_cmd],
                input=notify_data,
                capture_output=True,
                timeout=30,
                text=True,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            _log(f"[NOTIFY] Callback failed: {e}")

    # --- Error callback ---
    if on_error_cmd and combined_error:
        try:
            err_data = json.dumps(record, default=str)
            subprocess.run(
                ["sh", "-c", on_error_cmd],
                input=err_data,
                capture_output=True,
                timeout=30,
                text=True,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            _log(f"[ON-ERR] Error callback failed: {e}")


def run_loop(
    goal: str,
    context: str,
    toolsets: list[str],
    workdir: str | None,
    sentinel_path: str,
    max_iterations: int,
    compact_every: int,
    retry_delay: int,
    session_timeout: int,
    state: dict,
    status_file: str = "",
    max_idle_iterations: int = 0,
    evolve: bool = False,
    git: bool = False,
    git_commit: bool = False,
    workers: int = 1,
    notify_cmd: str | None = None,
    max_output_chars: int = 2000,
    profile: str = "",
    model: str = "",
    provider: str = "",
    http_callback: str = "",
    keep_iterations: int = 0,
    archive_dir: str = "",
    archive_retention: int = 30,
    archive_max_size: int = 0,
    max_retries: int = 0,
    on_error_cmd: str | None = None,
    tag: str = "",
    prompt_suffix: str = "",
    max_turns: int = 500,
    auto_toolsets: bool = True,
    failure_learning: bool = True,
    # v11.2.0 new features
    html_dashboard: str = "",
    webhook_port: int = 0,
    watch_dir: str = "",
    watch_poll: float = 5.0,
    # v11.3.0: Hermes worker URL
    worker_url: str = "",
    # v11.4.0: cooldown and goals file
    cooldown: int = 0,
    goals_file: str = "",
    stop_at_goals_end: bool = False,
    # v11.5.0: structured output, resource tracking, convergence, diff storage
    output_schema: dict | None = None,
    cooldown_mode: str = "fixed",
    convergence_threshold: float = DEFAULT_CONVERGENCE_THRESHOLD,
    convergence_window: int = DEFAULT_CONVERGENCE_WINDOW,
    convergence_stop: bool = False,
    store_git_diff: bool = False,
    # v11.7.0: startup delay and desktop notifications
    startup_delay: float = 0.0,
    notify_desktop: bool = False,
    notify_on_completion: bool = False,
    notify_pushbullet: str = "",
    notify_ntfy: str = "",
    notify_ntfy_server: str = "https://ntfy.sh",
    # v11.11.0: AIAgent library mode, session tracking, checkpoints
    use_library: bool = False,
    pass_session_id: bool = False,
    checkpoints: bool = False,
    # v11.12.0: session chaining, skills, ignore-rules
    resume: bool = False,
    resume_session_id: str = "",
    skills: str = "",
    ignore_rules: bool = False,
    # v11.13.0: yolo mode, ignore-user-config, source tagging
    yolo: bool = False,
    ignore_user_config: bool = False,
    spawn_source: str = "",
    # v11.14.0: safe-mode, accept-hooks, worktree, continue
    safe_mode: bool = False,
    accept_hooks: bool = False,
    worktree: bool = False,
    continue_session: bool = False,
    # v13.1.0: Idempotent Goal Execution
    track_goals: bool = False,
    reset_goals: bool = False,
    # v14.0.0: Heartbeat-based session self-healing
    heartbeat_timeout: int = 0,
) -> None:
    global _shutdown_requested

    # Auto-start worker if --worker-url=auto
    worker_manager = None
    effective_worker_url = worker_url
    if worker_url == "auto":
        worker_manager = HermesWorkerManager()
        effective_worker_url = worker_manager.start()
        _log(
            f"[DAEMON] Worker URL: {effective_worker_url or '(direct subprocess mode)'}"
        )

    # Wire up signal-safe state reference for graceful shutdown
    global _shutdown_state_ref
    _shutdown_state_ref = state

    iteration_count = state["total_iterations"]
    existing_summaries = [it.get("summary", "") for it in state.get("iterations", [])]
    consecutive_errors = state.get("stats", {}).get("consecutive_errors", 0)
    consecutive_idle = 0

    # Snapshot original runtime parameters for error recovery ramp-down
    global _ORIGINAL_SESSION_TIMEOUT, _ORIGINAL_COOLDOWN
    global _ORIGINAL_USE_LIBRARY, _ORIGINAL_WORKERS
    _ORIGINAL_SESSION_TIMEOUT = session_timeout
    _ORIGINAL_COOLDOWN = cooldown
    _ORIGINAL_USE_LIBRARY = use_library
    _ORIGINAL_WORKERS = workers

    # Auto-detect task type
    task_type, task_type_desc, extra_tools = detect_task_type(goal)
    if auto_toolsets:
        for extra in extra_tools:
            if extra not in toolsets:
                toolsets.append(extra)
                _log(
                    f"[AUTO-DETECT] Added toolset '{extra}' for task type '{task_type}' ({task_type_desc})"
                )

    # Build failure context from past errors for learning
    failure_context = ""
    if failure_learning and state.get("iterations"):
        failed = [it for it in state["iterations"] if it.get("error")]
        if failed:
            last_fails = failed[-3:]
            fail_lines = []
            for it in last_fails:
                n = it.get("n", "?")
                err = it.get("error", "")[:200]
                summary = (it.get("summary") or "")[:100]
                fail_lines.append(f"  #{n}: {err} — {summary}")
            if fail_lines:
                failure_context = (
                    "Previous failed iterations (avoid repeating these approaches):\n"
                    + "\n".join(fail_lines)
                )
                _log(
                    f"[FAILURE-LEARN] Injected {len(last_fails)} past failure(s) as context"
                )

    # Load goals file if provided — one goal per line (non-empty, non-comment)
    # Supports pipe-separated format: goal|profile|model|provider
    goals_tuples = _load_goals_file(goals_file, goal)
    goals_list: list[GoalSpec] = [GoalSpec(g) for g, p, m, v in goals_tuples]
    goals_index = 0

    write_status_file(status_file, state, iteration_count, "running")

    _log_startup_banner(
        task_type=task_type,
        task_type_desc=task_type_desc,
        profile=profile,
        model=model,
        max_retries=max_retries,
        max_turns=max_turns,
        tag=tag,
        goal=goal,
        toolsets=toolsets,
        evolve=evolve,
        git=git,
        git_commit=git_commit,
        workers=workers,
        session_timeout=session_timeout,
        notify_cmd=notify_cmd,
        use_library=use_library,
        pass_session_id=pass_session_id,
        checkpoints=checkpoints,
        output_schema=output_schema,
        cooldown_mode=cooldown_mode,
        cooldown=cooldown,
        convergence_stop=convergence_stop,
        convergence_window=convergence_window,
        convergence_threshold=convergence_threshold,
        store_git_diff=store_git_diff,
        track_goals=track_goals,
        reset_goals=reset_goals,
        heartbeat_timeout=heartbeat_timeout,
    )

    # Initialize ETA tracker
    eta_tracker = ETATracker()
    state["eta"] = eta_tracker.to_dict()

    # Initialize webhook server
    webhook_server = None
    if webhook_port > 0:

        def _webhook_trigger(goal_override=None, context_override=None):
            # Signal the loop to trigger on next iteration
            return {"triggered": True, "iteration": "on_next_loop"}

        webhook_server = _start_webhook_server(
            webhook_port, _webhook_trigger, sentinel_path
        )
        state["webhook_port"] = webhook_port

    # Initialize file watcher
    file_watcher = None
    if watch_dir:
        file_watcher = FileWatcherTrigger(watch_dir, watch_poll)
        _log(
            f"[WATCH] Watching {watch_dir} for file changes (poll every {watch_poll}s)"
        )
        state["watch_dir"] = watch_dir

    # Initialize HTML dashboard path
    if html_dashboard:
        state["html_dashboard"] = html_dashboard
        _write_status_html(html_dashboard, state)
        _log(f"[HTML-DASH] Status dashboard at {html_dashboard}")

    # Register worker cleanup on shutdown
    if worker_manager and worker_manager.is_running:
        import atexit

        atexit.register(worker_manager.stop)

    # Startup delay — wait before first iteration
    if startup_delay > 0 and iteration_count == 0:
        _log(f"[DAEMON] Startup delay: {startup_delay}s before first iteration")
        _sleep_with_shutdown_check(startup_delay)

    while True:
        if _shutdown_requested:
            _log("[STOP] Shutdown signal received. Stopping.")
            state["status"] = "stopped: signal"
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, "stopped: signal")
            return

        # --- File watcher trigger ---
        if file_watcher and file_watcher.check_change():
            changed = file_watcher.format_changed()
            _log(f"[WATCH] File change detected: {changed[:120]}")
            # Fall through to normal iteration logic

        # --- Sentinel check ---
        stop_signal = check_sentinel(sentinel_path)
        if stop_signal:
            if stop_signal.lower() == "pause":
                _log("[PAUSE] Sentinel contains 'pause'. Entering paused state.")
                state["status"] = "paused"
                write_ledger(state)
                write_status_file(status_file, state, iteration_count, "paused")
                _log("[PAUSE] Waiting for 'resume' or 'stop' sentinel...")
                # Poll for resume or stop — don't delete the sentinel so user
                # writes it again when they want to resume
                while True:
                    if _shutdown_requested:
                        _log("[STOP] Shutdown signal received during pause.")
                        state["status"] = "stopped: signal"
                        state["last_updated"] = datetime.now(timezone.utc).isoformat()
                        write_ledger(state)
                        write_status_file(
                            status_file, state, iteration_count, "stopped: signal"
                        )
                        return
                    pause_check = check_sentinel_no_remove(sentinel_path)
                    if pause_check is None:
                        # Sentinel was deleted — resume
                        _log("[RESUME] Sentinel removed. Resuming loop.")
                        state["status"] = "running"
                        write_ledger(state)
                        break
                    if pause_check.lower() == "resume":
                        os.remove(sentinel_path)
                        _log("[RESUME] Sentinel contains 'resume'. Resuming loop.")
                        state["status"] = "running"
                        write_ledger(state)
                        break
                    if pause_check.lower() == "stop":
                        os.remove(sentinel_path)
                        _log("[STOP] Sentinel contains 'stop' during pause. Stopping.")
                        state["status"] = "stopped: paused-stop"
                        state["last_updated"] = datetime.now(timezone.utc).isoformat()
                        write_ledger(state)
                        write_status_file(
                            status_file, state, iteration_count, "stopped: paused-stop"
                        )
                        return
                    time.sleep(5)
                # Re-check max iterations after resume
                continue
            _log(f"[STOP] Sentinel detected ('{stop_signal}'). Stopping.")
            state["status"] = f"stopped: {stop_signal}"
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(
                status_file, state, iteration_count, f"stopped: {stop_signal}"
            )
            return

        # --- Max iterations check ---
        if max_iterations > 0 and iteration_count >= max_iterations:
            _log(f"[STOP] Reached max_iterations={max_iterations}. Stopping.")
            state["status"] = f"stopped: max_iterations ({max_iterations})"
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(
                status_file, state, iteration_count, "stopped: max_iterations"
            )
            return

        # --- Max idle iterations check ---
        if max_idle_iterations > 0 and consecutive_idle >= max_idle_iterations:
            _log(
                f"[STOP] No changes detected for {consecutive_idle} iterations (max_idle={max_idle_iterations}). Stopping."
            )
            state["status"] = (
                f"stopped: idle ({consecutive_idle} iterations without changes)"
            )
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, "stopped: idle")
            return

        iteration_count += 1

        iterations: list[dict] = state.setdefault("iterations", [])
        iteration_start_time = datetime.now(timezone.utc).isoformat()

        _log(f"\n{'=' * 60}")
        _log(f"  Iteration {iteration_count}")
        if max_iterations > 0:
            _log(f"  Progress: {iteration_count}/{max_iterations}")
        if workers > 1:
            _log(f"  Workers: {workers} concurrent sessions")
        _log(f"{'=' * 60}")

        # Cycle goals from goals_file if provided
        if len(goals_list) > 1:
            idx = goals_index % len(goals_list)
            current_goal_spec = goals_list[idx]
            goals_index += 1
            goal_text, exhausted = _cycle_goal(
                goals_list, goals_index - 1, stop_at_goals_end
            )
            if exhausted:
                state["status"] = "stopped: goals-exhausted"
                state["last_updated"] = datetime.now(timezone.utc).isoformat()
                write_ledger(state)
                write_status_file(
                    status_file, state, iteration_count, "stopped: goals-exhausted"
                )
                return

            # Idempotent Goal Execution: skip already-completed goals
            if track_goals and _is_goal_completed(state, goal_text):
                _log(
                    f"[TRACK-GOALS] Skipping already-completed goal: {goal_text[:120]}..."
                )
                continue  # back to while loop, bumps iteration_count

        # Build progressive context from past summaries
        progressive_context = _build_progressive_context(context, existing_summaries)

        # Use goals_file goal if active, otherwise the primary goal
        spawn_goal = current_goal_spec if len(goals_list) > 1 else goals_list[0]

        # Git snapshot before + system resource tracking
        git_before = (
            _capture_git_state(workdir, store_diff=store_git_diff) if git else {}
        )
        sys_before = get_system_usage()

        # Execute iteration — spawn sessions, retry, collect results
        all_results, spawn_goal, use_library = _execute_iteration(
            state=state,
            iteration_count=iteration_count,
            spawn_goal=spawn_goal,
            workers=workers,
            use_library=use_library,
            goals_list=goals_list,
            goals_index=goals_index,
            progressive_context=progressive_context,
            toolsets=toolsets,
            workdir=workdir,
            session_timeout=session_timeout,
            max_output_chars=max_output_chars,
            max_turns=max_turns,
            evolve=evolve,
            task_type=task_type,
            failure_context=failure_context,
            effective_worker_url=effective_worker_url,
            output_schema=output_schema,
            pass_session_id=pass_session_id,
            checkpoints=checkpoints,
            profile=profile,
            model=model,
            provider=provider,
            prompt_suffix=prompt_suffix,
            resume_session_id=resume_session_id,
            skills=skills,
            ignore_rules=ignore_rules,
            yolo=yolo,
            ignore_user_config=ignore_user_config,
            spawn_source=spawn_source,
            safe_mode=safe_mode,
            accept_hooks=accept_hooks,
            worktree=worktree,
            continue_session=continue_session,
            max_retries=max_retries,
            retry_delay=retry_delay,
            git=git,
            store_git_diff=store_git_diff,
            heartbeat_timeout=heartbeat_timeout,
        )

        state.pop("pending_iteration", None)

        # Merge worker results into combined summary/error/context
        merged = _merge_worker_results(
            all_results=all_results,
            state=state,
            max_output_chars=max_output_chars,
            consecutive_errors=consecutive_errors,
        )
        combined_error = merged["combined_error"]
        total_duration = merged["total_duration"]
        primary_error_type = merged["primary_error_type"]
        consecutive_successes = merged["consecutive_successes"]
        consecutive_errors = merged["consecutive_errors"]
        next_goal = merged["next_goal"]
        next_context = merged["next_context"]
        combined_summary = merged["combined_summary"]
        combined_output = merged["combined_output"]

        # --- Git snapshot after ---
        git_after = (
            _capture_git_state(workdir, store_diff=store_git_diff) if git else {}
        )
        git_commit_hash = None
        if git_commit and not combined_error:
            git_commit_hash = _git_auto_commit(
                workdir, iteration_count, combined_summary
            )
            if git_commit_hash:
                _log(f"[GIT] Committed as {git_commit_hash}")

        # Track idle iterations
        if git:
            before_ds = git_before.get("diff_stat", "")
            after_ds = git_after.get("diff_stat", "")
            before_cached = git_before.get("diff_stat_cached", "")
            after_cached = git_after.get("diff_stat_cached", "")
            diff_changed = before_ds != after_ds
            cached_changed = before_cached != after_cached
            head_before = git_before.get("head", "")
            head_after = git_after.get("head", "")
            head_changed = bool(
                head_before and head_after and head_before != head_after
            )
            had_changes = (
                diff_changed or cached_changed or bool(git_commit_hash) or head_changed
            )
            if not had_changes:
                consecutive_idle += 1
                _log(
                    f"[IDLE] No changes detected ({consecutive_idle}/{max_idle_iterations if max_idle_iterations > 0 else 'off'})"
                )
            else:
                consecutive_idle = 0

        # --- Convergence detection ---
        if _detect_convergence(
            convergence_stop=convergence_stop,
            iteration_count=iteration_count,
            convergence_window=convergence_window,
            existing_summaries=existing_summaries,
            combined_summary=combined_summary,
            convergence_threshold=convergence_threshold,
            state=state,
            status_file=status_file,
        ):
            return

        # Rolling window context compaction
        existing_summaries, is_compacted = _compact_summaries(
            existing_summaries=existing_summaries,
            compact_every=compact_every,
            iteration_count=iteration_count,
            combined_summary=combined_summary,
        )

        # Record iteration
        record = _build_iteration_record(
            iteration_count=iteration_count,
            task_type=task_type,
            spawn_goal=spawn_goal,
            goals_list=goals_list,
            iteration_start_time=iteration_start_time,
            total_duration=total_duration,
            combined_summary=combined_summary,
            is_compacted=is_compacted,
            combined_error=combined_error,
            all_results=all_results,
            workers=workers,
            toolsets=toolsets,
            git_before=git_before,
            git_after=git_after,
            git=git,
            git_commit_hash=git_commit_hash,
            next_goal=next_goal,
            next_context=next_context,
            resume=resume,
            pass_session_id=pass_session_id,
            state=state,
            sys_before=sys_before,
        )

        state["iterations"].append(record)
        state["total_iterations"] = iteration_count
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        state["status"] = "running"

        # Update current goal if evolving
        if evolve and next_goal and len(goals_list) <= 1:
            state["current_goal"] = goal
            goal = next_goal
            state["evolved_goal"] = goal
            _log(f"[EVOLVE] Next goal: {goal[:120]}...")

        # Inject context from spawned session as progressive context for next iteration
        if next_context:
            progressive_context = f"[Context from previous iteration]: {next_context}"

        # --- Self-modification reload signal ---
        # A spawned session that modified launch-loop.py or the skill can signal
        # need_reload in its JSON. The daemon detects this and calls os.execv()
        # to restart with the updated code.
        if combined_error is None and next_goal and "need_reload" in next_goal:
            _log("[RELOAD] Spawned session signaled need_reload. Restarting daemon...")
            state["status"] = "reloading"
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, "reloading")
            if worker_manager:
                worker_manager.stop()
            _log("[RELOAD] Executing os.execv() with updated code...")
            os.execv(sys.executable, [sys.executable] + sys.argv)

        _recalc_stats(state)
        eta_tracker.record_iteration(task_type, total_duration)
        state["eta"] = eta_tracker.to_dict()
        if max_iterations > 0:
            eta_remaining = eta_tracker.estimate_remaining(
                task_type, iteration_count, max_iterations
            )
            state["eta"]["remaining_seconds"] = eta_remaining
            state["eta"]["remaining_formatted"] = eta_tracker.format_eta(eta_remaining)
        # Idempotent Goal Execution: mark current goal as completed
        if track_goals and len(goals_list) > 1:
            _mark_goal_completed(state, goal_text, iteration_count)
        write_ledger(state)
        write_status_file(status_file, state, iteration_count, "running")

        _log(f"[DONE] Iteration {iteration_count}: {combined_summary[:120]}")

        # Notifications on each iteration (desktop, pushbullet, ntfy)
        _handle_notifications(
            notify_desktop=notify_desktop,
            notify_pushbullet=notify_pushbullet,
            notify_ntfy=notify_ntfy,
            combined_summary=combined_summary,
            total_duration=total_duration,
            combined_error=combined_error,
            notify_ntfy_server=notify_ntfy_server,
        )

        eta_str = ""
        if max_iterations > 0:
            eta_str = f" | ETA: {eta_tracker.format_eta(eta_tracker.estimate_remaining(task_type, iteration_count, max_iterations))}"
            # Compact progress bar
            pct = min(100.0 * iteration_count / max_iterations, 100.0)
            bar_width = 20
            filled = int(pct / 100.0 * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            _log(
                f"[PROGRESS] [{bar}] {iteration_count}/{max_iterations} ({pct:.0f}%){eta_str}"
            )
        _log(f"[STATS] {task_type} | {total_duration}s{eta_str}")

        # Write HTML dashboard after each iteration
        if html_dashboard:
            _write_status_html(html_dashboard, state)

        # --- HTTP / Notification / Error callbacks ---
        _handle_callbacks(
            http_callback=http_callback,
            record=record,
            notify_cmd=notify_cmd,
            on_error_cmd=on_error_cmd,
            combined_error=combined_error,
            state=state,
        )

        # Broadcast iteration state to SSE live dashboard clients
        _broadcast_to_sse_clients(state)

        if (
            keep_iterations > 0
            and len(state.get("iterations", [])) > keep_iterations * 2
        ):
            old_count = len(state["iterations"])
            # Save discarded iterations before trimming
            discarded = state["iterations"][: old_count - keep_iterations]
            if discarded:
                try:
                    archived = _archive_iterations(
                        discarded,
                        archive_dir=archive_dir,
                        tag=state.get("tag", ""),
                    )
                    if archived:
                        _cleanup_old_archives(archive_dir, archive_retention)
                        if archive_max_size > 0:
                            _enforce_archive_max_size(archive_dir, archive_max_size)
                except Exception as e:
                    _log(f"[ARCHIVE] Failed to archive iterations: {e}")
            state["iterations"] = state["iterations"][-keep_iterations:]
            state["total_iterations"] = iteration_count
            _log(
                f"[SHRINK] Trimmed ledger from {old_count} to {keep_iterations} iterations"
                f" (archived {len(discarded)} to archive)"
            )
            write_ledger(state)

        # --- Cooldown (rate-limit awareness) ---
        _handle_cooldown(
            cooldown=cooldown,
            cooldown_mode=cooldown_mode,
            eta_tracker=eta_tracker,
            task_type=task_type,
        )

        # --- Automatic Error Recovery ---
        # Classify error type(s) from all_results, update per-type counters,
        # and adapt runtime parameters for the next iteration.
        state.setdefault(
            "mitigations",
            {
                "timeout_increased": False,
                "cooldown_elevated": False,
                "force_subprocess": False,
                "reduced_workers": False,
                "mitigation_level": 0,
                "last_applied": "",
                "actions": [],
            },
        )

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
            error_type_counts=state.get("error_type_counts", {}),
            session_timeout=session_timeout,
            cooldown=cooldown,
            cooldown_mode=cooldown_mode,
            use_library=use_library,
            workers=workers,
        )

        state["consecutive_successes"] = consecutive_successes

        for action in adapt_actions:
            _log(f"[AUTO-RECOVERY] {action}")

        # --- Backoff + persistent failure check ---
        should_stop = _handle_backoff(
            combined_error=combined_error,
            retry_delay=retry_delay,
            consecutive_errors=consecutive_errors,
            adapt_actions=adapt_actions,
            state=state,
            status_file=status_file,
            iteration_count=iteration_count,
        )
        if should_stop:
            return

        # Stop daemon if mitigation reached level 3 (persistent failure)
        if state["mitigations"].get("mitigation_level", 0) >= 3:
            _log("[AUTO-RECOVERY] Persistent failure detected — stopping daemon")
            state["status"] = (
                f"stopped: {primary_error_type}-failure-"
                f"{state.get('error_type_counts', {}).get(primary_error_type, 0)}"
            )
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, state["status"])
            return


def load_or_create_ledger(
    goal: str, context: str, sentinel_path: str = "", reset_goals: bool = False
) -> dict:
    existing = read_ledger()

    # Clean up stale sentinel from previous runs
    if sentinel_path and os.path.exists(sentinel_path):
        try:
            os.remove(sentinel_path)
            _log(f"[CLEANUP] Removed stale sentinel file: {sentinel_path}")
        except OSError as e:
            _log(f"[WARN] Could not remove stale sentinel: {e}")

    if existing is not None:
        if existing.get("initial_command") == goal:
            _log(
                f"[INFO] Resuming from existing ledger ({existing['total_iterations']} iterations done)"
            )
            existing["status"] = "running"
            existing["last_updated"] = datetime.now(timezone.utc).isoformat()
            # Initialize goals_completed if not present (backward compat)
            if "goals_completed" not in existing:
                existing["goals_completed"] = {}
            if reset_goals:
                existing["goals_completed"] = {}
                _log("[INFO] --reset-goals: cleared goals_completed ledger")
            if existing.get("pending_iteration"):
                pending = existing["pending_iteration"]
                started_at = pending.get("started_at", "")
                try:
                    if "Z" in started_at or "+" in started_at:
                        started_ts = datetime.fromisoformat(started_at).timestamp()
                    else:
                        started_ts = datetime.fromisoformat(started_at[:19]).timestamp()
                except (ValueError, TypeError):
                    started_ts = 0
                elapsed = time.time() - started_ts
                if elapsed >= 300:
                    _log(
                        f"[RECOVER] Stale pending iteration #{pending.get('n')} ({elapsed:.0f}s old)"
                    )
                    record = {
                        "n": pending.get("n"),
                        "started_at": started_at,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "duration_seconds": round(elapsed, 1),
                        "summary": f"[RECOVERED] Agent crashed mid-iteration after {elapsed:.0f}s",
                        "compacted": False,
                        "error": "agent_crashed",
                    }
                    existing.setdefault("iterations", []).append(record)
                    existing["total_iterations"] = len(existing["iterations"])
                    existing.pop("pending_iteration", None)
                    _recalc_stats(existing)
            # Ensure error recovery state keys exist (backward compat)
            if "error_type_counts" not in existing:
                existing["error_type_counts"] = {
                    "timeout": 0,
                    "network": 0,
                    "schema": 0,
                    "unknown": 0,
                }
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
            write_ledger(existing)
            return existing
        else:
            _log("[INFO] Existing ledger has different goal, starting fresh")
    else:
        _log("[INFO] No existing ledger, starting fresh")

    return {
        "version": 11,
        "version_detail": f"v{LAUNCH_LOOP_VERSION} -- Dashboard XSS Fix, Error Panel, Performance Metrics, Goals Visualization, Function Decomposition Phase 2, Phase 3, Self-Test Mode, Output Progress Classification, Idempotent Goal Execution.",
        "initial_command": goal,
        "initial_context": context,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "iterations": [],
        "total_iterations": 0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "stats": {
            "total_duration_seconds": 0.0,
            "avg_duration_seconds": 0.0,
            "success_count": 0,
            "error_count": 0,
            "consecutive_errors": 0,
        },
        "error_type_counts": {
            "timeout": 0,
            "network": 0,
            "schema": 0,
            "unknown": 0,
        },
        "mitigations": {
            "timeout_increased": False,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
            "mitigation_level": 0,
            "last_applied": "",
            "actions": [],
        },
        "goals_completed": {},
    }


def _run_self_test() -> dict:
    """Run integrated self-test suite to verify daemon functions in isolation.

    Tests are organized by daemon function, with one or more sub-test cases
    per function. Each sub-test reports pass/fail independently.

    Returns a dict with keys: passed, failed, total, results.
    """
    # Import here to avoid polluting module namespace
    import math

    results: list[dict] = []
    passed_total = 0
    failed_total = 0

    def _record(test_name: str, passed: bool, detail: str = "") -> None:
        nonlocal passed_total, failed_total
        if passed:
            passed_total += 1
        else:
            failed_total += 1
        results.append({"name": test_name, "passed": passed, "detail": detail})

    def _run_subtests(group: str, cases: list[tuple[str, callable, callable]]) -> None:
        """Run a list of sub-tests under a group name.
        Each case is (case_name, callable_under_test, expected_validator).
        validator(result) returns (bool, str).
        """
        passed_cases = 0
        failed_cases: list[str] = []
        for case_name, func, validator in cases:
            try:
                result = func()
                ok, detail = validator(result)
                if ok:
                    passed_cases += 1
                else:
                    failed_cases.append(f"{case_name}: {detail}")
            except Exception as e:
                failed_cases.append(f"{case_name}: EXCEPTION: {e}")
        total_cases = len(cases)
        if failed_cases:
            detail = "; ".join(failed_cases)
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(
                f"[{ts}] [SELF-TEST] \u2717 {group} ({passed_cases}/{total_cases} cases passed): {detail}",
                flush=True,
            )
            _record(group, False, detail)
        else:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(
                f"[{ts}] [SELF-TEST] \u2713 {group} ({passed_cases}/{total_cases} cases passed)",
                flush=True,
            )
            _record(group, True, "")

    # ------------------------------------------------------------------
    # Test: extract_json_output
    # ------------------------------------------------------------------
    def _test_extract_json():
        cases = []
        # a) Simple single-line JSON
        cases.append(
            (
                "single-line",
                lambda: extract_json_from_output('{"summary": "hello", "error": null}'),
                lambda r: (r is not None and r.get("summary") == "hello", f"got {r}"),
            )
        )
        # b) Multi-line JSON
        cases.append(
            (
                "multi-line",
                lambda: extract_json_from_output(
                    '{\n"summary": "hello",\n"error": null\n}'
                ),
                lambda r: (r is not None and r.get("summary") == "hello", f"got {r}"),
            )
        )
        # c) JSON in code fences
        cases.append(
            (
                "code-fence",
                lambda: extract_json_from_output(
                    '```json\n{"summary": "hello", "error": null}\n```'
                ),
                lambda r: (r is not None and r.get("summary") == "hello", f"got {r}"),
            )
        )
        # d) JSON with session_id noise
        cases.append(
            (
                "session-noise",
                lambda: extract_json_from_output(
                    'session_id: abc-123\n{"summary": "hello", "error": null}'
                ),
                lambda r: (r is not None and r.get("summary") == "hello", f"got {r}"),
            )
        )
        # e) Empty/None input
        cases.append(
            (
                "empty",
                lambda: extract_json_from_output(""),
                lambda r: (r is None, f"expected None, got {r}"),
            )
        )
        cases.append(
            (
                "none-input",
                lambda: extract_json_from_output(None),
                lambda r: (r is None, f"expected None, got {r}"),
            )
        )
        return cases

    _run_subtests("test_extract_json_output", _test_extract_json())

    # ------------------------------------------------------------------
    # Test: classify_error
    # ------------------------------------------------------------------
    def _test_classify_error():
        cases = []
        cases.append(
            (
                "none",
                lambda: classify_error(None),
                lambda r: (r is None, f"expected None, got {r!r}"),
            )
        )
        cases.append(
            (
                "timeout",
                lambda: classify_error("timeout"),
                lambda r: (r == "timeout", f"expected 'timeout', got {r!r}"),
            )
        )
        cases.append(
            (
                "connection-refused",
                lambda: classify_error("connection refused"),
                lambda r: (r == "network", f"expected 'network', got {r!r}"),
            )
        )
        cases.append(
            (
                "schema-validation",
                lambda: classify_error("schema validation failed"),
                lambda r: (r == "schema", f"expected 'schema', got {r!r}"),
            )
        )
        cases.append(
            (
                "random-error",
                lambda: classify_error("random error"),
                lambda r: (r == "unknown", f"expected 'unknown', got {r!r}"),
            )
        )
        return cases

    _run_subtests("test_classify_error", _test_classify_error())

    # ------------------------------------------------------------------
    # Test: text_similarity
    # ------------------------------------------------------------------
    def _test_text_similarity():
        cases = []
        cases.append(
            (
                "identical",
                lambda: text_similarity("hello world", "hello world"),
                lambda r: (r == 1.0, f"expected 1.0, got {r}"),
            )
        )
        cases.append(
            (
                "completely-different",
                lambda: text_similarity("abc", "xyz"),
                lambda r: (r == 0.0, f"expected 0.0, got {r}"),
            )
        )
        cases.append(
            (
                "partial-overlap",
                lambda: text_similarity("hello world foo", "hello bar"),
                lambda r: (0.0 < r < 1.0, f"expected 0<r<1, got {r}"),
            )
        )
        cases.append(
            (
                "both-empty",
                lambda: text_similarity("", ""),
                lambda r: (r == 1.0, f"expected 1.0, got {r}"),
            )
        )
        cases.append(
            (
                "one-empty",
                lambda: text_similarity("hello", ""),
                lambda r: (r == 0.0, f"expected 0.0, got {r}"),
            )
        )
        return cases

    _run_subtests("test_text_similarity", _test_text_similarity())

    # ------------------------------------------------------------------
    # Test: check_convergence
    # ------------------------------------------------------------------
    def _test_check_convergence():
        cases = []

        # a) Fewer summaries than window → (False, 0.0)
        def _fewer():
            converged, sim = check_convergence(["a"], threshold=0.9, window=3)
            return not converged and sim == 0.0

        cases.append(
            (
                "fewer-than-window",
                lambda: check_convergence(["a"], threshold=0.9, window=3),
                lambda r: (not r[0] and r[1] == 0.0, f"got {r}"),
            )
        )
        # b) All identical → (True, 1.0)
        cases.append(
            (
                "all-identical",
                lambda: check_convergence(["hello world"] * 5, threshold=0.9, window=5),
                lambda r: (r[0] is True and r[1] == 1.0, f"got {r}"),
            )
        )
        # c) All different → (False, < 1.0)
        cases.append(
            (
                "all-different",
                lambda: check_convergence(
                    ["abc", "def", "ghi", "jkl", "mno"], threshold=0.9, window=5
                ),
                lambda r: (not r[0] and r[1] < 1.0, f"got {r}"),
            )
        )
        return cases

    _run_subtests("test_check_convergence", _test_check_convergence())

    # ------------------------------------------------------------------
    # Test: validate_json_output
    # ------------------------------------------------------------------
    def _test_validate_json():
        schema = {
            "type": "object",
            "required": ["summary", "status"],
            "properties": {
                "summary": {"type": "string"},
                "status": {"type": "string", "enum": ["ok", "error"]},
            },
        }
        # a) Valid output matching schema
        valid_out = {"summary": "done", "status": "ok"}
        cases = []
        cases.append(
            (
                "valid",
                lambda: validate_json_output(valid_out, schema),
                lambda r: (r[0] is True, f"expected True, got {r}"),
            )
        )
        # b) Missing required field
        cases.append(
            (
                "missing-field",
                lambda: validate_json_output({"summary": "done"}, schema),
                lambda r: (
                    r[0] is False and "missing required field" in r[1],
                    f"got {r}",
                ),
            )
        )
        # c) Wrong type
        cases.append(
            (
                "wrong-type",
                lambda: validate_json_output({"summary": 42, "status": "ok"}, schema),
                lambda r: (
                    r[0] is False and "expected string, got int" in r[1].lower(),
                    f"got {r}",
                ),
            )
        )
        # d) Invalid schema (None schema)
        cases.append(
            (
                "no-schema",
                lambda: validate_json_output({"summary": "x"}, None),
                lambda r: (r[0] is True, f"got {r}"),
            )
        )
        return cases

    _run_subtests("test_validate_json_output", _test_validate_json())

    # ------------------------------------------------------------------
    # Test: calc_adaptive_cooldown
    # ------------------------------------------------------------------
    def _test_calc_cooldown():
        cases = []
        # a) avg_duration=0 → min_cooldown
        cases.append(
            (
                "zero-duration",
                lambda: calc_adaptive_cooldown(0, min_cooldown=2, max_cooldown=60),
                lambda r: (r == 2, f"expected 2, got {r}"),
            )
        )
        # b) avg_duration=300+ → min_cooldown
        cases.append(
            (
                "long-duration",
                lambda: calc_adaptive_cooldown(300, min_cooldown=2, max_cooldown=60),
                lambda r: (r == 2, f"expected 2, got {r}"),
            )
        )
        # c) avg_duration=5 → max_cooldown
        cases.append(
            (
                "short-duration",
                lambda: calc_adaptive_cooldown(5, min_cooldown=2, max_cooldown=60),
                lambda r: (r == 60, f"expected 60, got {r}"),
            )
        )
        # d) avg_duration=30 → interpolated (between 15 and 300)
        cases.append(
            (
                "interpolated",
                lambda: calc_adaptive_cooldown(30, min_cooldown=2, max_cooldown=60),
                lambda r: (2 < r < 60, f"expected 2<r<60, got {r}"),
            )
        )
        return cases

    _run_subtests("test_calc_adaptive_cooldown", _test_calc_cooldown())

    # ------------------------------------------------------------------
    # Test: GoalSpec
    # ------------------------------------------------------------------
    def _test_goal_spec():
        cases = []

        # a) Basic goal
        def _basic():
            g = GoalSpec("fix auth")
            return (
                g.goal == "fix auth"
                and g.profile == ""
                and g.model == ""
                and g.provider == ""
            )

        cases.append(
            (
                "basic",
                lambda: _basic(),
                lambda r: (r is True, f"basic GoalSpec assertion failed"),
            )
        )

        # b) With profile
        def _with_profile():
            g = GoalSpec("fix auth", profile="work")
            return g.goal == "fix auth" and g.profile == "work"

        cases.append(
            (
                "with-profile",
                lambda: _with_profile(),
                lambda r: (r is True, f"with-profile GoalSpec assertion failed"),
            )
        )

        # c) Full spec
        def _full():
            g = GoalSpec("fix auth", profile="work", model="gpt4", provider="openai")
            return (
                g.goal == "fix auth"
                and g.profile == "work"
                and g.model == "gpt4"
                and g.provider == "openai"
            )

        cases.append(
            (
                "full-spec",
                lambda: _full(),
                lambda r: (r is True, f"full-spec GoalSpec assertion failed"),
            )
        )
        return cases

    _run_subtests("test_goal_spec", _test_goal_spec())

    # ------------------------------------------------------------------
    # Test: _classify_progress
    # ------------------------------------------------------------------
    def _test_classify_progress():
        cases = []
        # a) Summary containing "completed" → "completed"
        cases.append(
            (
                "completed",
                lambda: _classify_progress("task completed", None, None, None),
                lambda r: (r == "completed", f"expected 'completed', got {r!r}"),
            )
        )
        # b) Error with no git changes → "regression"
        cases.append(
            (
                "regression",
                lambda: _classify_progress(
                    "something broke", None, None, "error occurred"
                ),
                lambda r: (r == "regression", f"expected 'regression', got {r!r}"),
            )
        )
        # c) No changes, short summary → "stuck"
        cases.append(
            (
                "stuck",
                lambda: _classify_progress("fail", None, None, None),
                lambda r: (r == "stuck", f"expected 'stuck', got {r!r}"),
            )
        )
        # d) Git changes with positive keywords → "progress"
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "1 file changed"}
        cases.append(
            (
                "progress",
                lambda: _classify_progress(
                    "fixed the bug", git_before, git_after, None
                ),
                lambda r: (r == "progress", f"expected 'progress', got {r!r}"),
            )
        )
        return cases

    _run_subtests("test_classify_progress", _test_classify_progress())

    total = passed_total + failed_total
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    if failed_total == 0:
        print(
            f"[{ts}] [SELF-TEST] Result: {passed_total}/{total} tests passed, all OK",
            flush=True,
        )
    else:
        print(
            f"[{ts}] [SELF-TEST] Result: {passed_total}/{total} tests passed, {failed_total} FAILURES",
            flush=True,
        )

    return {
        "passed": passed_total,
        "failed": failed_total,
        "total": total,
        "results": results,
    }


def main():
    # Check --version before argparse to avoid required-arg conflicts
    if "--version" in sys.argv:
        print(f"infinite-loop daemon v{LAUNCH_LOOP_VERSION}")
        sys.exit(0)

    # Check --self-test before argparse to avoid required --goal conflict
    if "--self-test" in sys.argv:
        result = _run_self_test()
        sys.exit(0 if result["failed"] == 0 else 1)

    # Helpful early exit when --help or -h is passed
    if "--help" in sys.argv or "-h" in sys.argv:
        parser = _build_arg_parser()
        parser.print_help()
        sys.exit(0)

    # Friendly error if --goal is missing (before argparse dry error)
    standalone_flags = {"--version", "--self-test", "--dry-run", "--help", "-h"}
    arg_set = set(sys.argv[1:])
    has_goal = any(
        i + 1 < len(sys.argv) and sys.argv[i] == "--goal" for i in range(len(sys.argv))
    )
    has_goals_file = any(
        i + 1 < len(sys.argv) and sys.argv[i] == "--goals-file"
        for i in range(len(sys.argv))
    )
    if not has_goal and not has_goals_file and not arg_set & standalone_flags:
        parser = _build_arg_parser()
        print(
            "ERROR: --goal is required (or use --goals-file for batch mode)\n",
            file=sys.stderr,
        )
        parser.print_usage()
        print("\nSee 'python3 launch-loop.py --help' for full options", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description=(
            f"Infinite Loop Daemon v{VERSION} — Autonomous Hermes Agent Looping Framework\n\n"
            "Spawns Hermes sessions in a loop with real tools (terminal, file, delegation) + "
            "multi-level delegate_task() trees. Each iteration spawns a `hermes chat -q` session "
            "with configurable toolsets, max-turns, and context propagation.\n\n"
            "Features at a glance:\n"
            "  Iteration:  evolve, max-iterations, goals-file, convergence detection\n"
            "  Parallel:   workers, session-timeout, max-retries, cooldown\n"
            "  Notify:     desktop (Linux), Pushbullet, ntfy, HTTP callback, shell cmd\n"
            "  Sessions:   use-library, pass-session-id, checkpoints, resume, skills\n"
            "  Spawn:      profile, model, provider, yolo, safe-mode, worktree\n"
            "  Debug:      preflight, self-test, dry-run, heartbeat, status-html\n"
            "  Git:        auto-commit, store-git-diff, max-idle-iterations\n"
            "  Web:        webhook REST API, SSE dashboard v3, HTTP callback\n\n"
            "Common usage:\n"
            '  python3 launch-loop.py --goal "Fix lint errors" --run\n'
            '  python3 launch-loop.py --goal "Refactor auth" --git --git-commit --evolve --run\n'
            "  python3 launch-loop.py --goals-file goals.txt --track-goals --workers 5 --run\n"
            "  python3 launch-loop.py --self-test\n"
            "  python3 launch-loop.py --dry-run\n\n"
            "Stop:  echo 'stop' > /tmp/infinite-loop-stop\n"
            "Pause: echo 'pause' > /tmp/infinite-loop-stop\n"
            "Status: cat /tmp/infinite-loop-state.json | python3 -m json.tool"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--goal", required=True, help="The core task for spawned sessions"
    )
    parser.add_argument(
        "--context", default="", help="Initial context (paths, constraints, language)"
    )
    parser.add_argument(
        "--toolsets",
        default=BASE_TOOLSETS,
        help=(
            "Comma-separated toolsets for spawned Hermes sessions "
            f"(default: {BASE_TOOLSETS})"
        ),
    )
    parser.add_argument("--workdir", default="", help="Working directory")
    parser.add_argument(
        "--compact-every", type=int, default=5, help="Compact context every N iters"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Auto-stop after N iterations (0=infinite)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=500,
        help="Max turns per spawned Hermes session (default: 500 — high for deep delegation chains)",
    )
    parser.add_argument(
        "--retry-delay", type=int, default=0, help="Backoff delay on error"
    )
    parser.add_argument(
        "--session-timeout",
        type=int,
        default=HERMES_SESSION_TIMEOUT,
        help=f"Max seconds per Hermes session (default: {HERMES_SESSION_TIMEOUT})",
    )
    parser.add_argument(
        "--shutdown-sentinel", default=SENTINEL_PATH_DEFAULT, help="Sentinel file path"
    )
    parser.add_argument(
        "--context-file",
        default="",
        help="Read context from a file (alternative to --context)",
    )
    parser.add_argument(
        "--profile",
        default="",
        help="Hermes profile for spawned sessions (e.g. 'work')",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model override for spawned sessions (e.g. 'anthropic/claude-sonnet-4')",
    )
    parser.add_argument(
        "--provider",
        default="",
        help="Provider override for spawned sessions (e.g. 'openrouter')",
    )
    parser.add_argument(
        "--http-callback",
        default="",
        help="HTTP POST URL for iteration JSON (like --notify-cmd but via HTTP)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without spawning any sessions",
    )
    parser.add_argument(
        "--keep-iterations",
        type=int,
        default=0,
        help="Auto-shrink ledger to keep only last N iterations (0=keep all). Removes when > 2N.",
    )

    # Archive flags
    parser.add_argument(
        "--archive-dir",
        default=os.path.expanduser("~/.hermes/infinite-loop-archives"),
        help="Directory to store archived iteration files (default: ~/.hermes/infinite-loop-archives)",
    )
    parser.add_argument(
        "--archive-retention",
        type=int,
        default=30,
        help="Days to keep archived iterations (0=keep forever, default: 30)",
    )
    parser.add_argument(
        "--archive-max-size",
        type=int,
        default=0,
        help="Max total size of archive directory in MB before oldest files are purged "
        "(0=unlimited, default: 0). Combined with --archive-retention, the stricter constraint wins.",
    )

    parser.add_argument("--run", action="store_true", help="Start the actual loop")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test suite and exit",
    )

    # v9.1.0 flags
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Retry a failed iteration up to N times (0=no retry)",
    )
    parser.add_argument(
        "--on-error-cmd",
        default="",
        help="Shell command when an iteration fails (JSON on stdin)",
    )
    parser.add_argument(
        "--tag",
        default="",
        help="Label/identifier for the run (e.g. 'project:fix-auth')",
    )
    parser.add_argument(
        "--prompt-suffix",
        default="",
        help="Extra text appended to every spawned prompt",
    )
    parser.add_argument(
        "--force-reset",
        action="store_true",
        help="Clear existing ledger and start fresh",
    )

    # v11.1.0 flags
    parser.add_argument(
        "--no-auto-toolsets",
        action="store_true",
        help="Disable automatic toolset enrichment based on task type",
    )
    parser.add_argument(
        "--no-failure-learning",
        action="store_true",
        help="Disable injection of past failure context into spawned sessions",
    )
    parser.add_argument(
        "--task-type",
        default="auto",
        help="Force a specific task type (research|code-fix|code-build|system-admin|data-processing|content|general). "
        "Default: auto-detect from --goal.",
    )

    # v11.2.0 flags — webhook, log file, HTML dashboard, file watcher
    parser.add_argument(
        "--webhook-port",
        type=int,
        default=0,
        help="Port for HTTP webhook server (0=disabled). POST /webhook triggers iteration, GET /health, GET /status",
    )
    parser.add_argument(
        "--log-file",
        default="",
        help="Path to daemon log file (e.g. /tmp/infinite-loop.log). Adds file logging alongside stdout.",
    )
    parser.add_argument(
        "--log-max-mb",
        type=int,
        default=10,
        help="Max log file size in MB before rotation (default: 10, only used with --log-file)",
    )
    parser.add_argument(
        "--status-html",
        default="",
        help="Path to self-contained HTML status dashboard (e.g. /tmp/loop-status.html). Updated after each iteration.",
    )
    parser.add_argument(
        "--watch-dir",
        default="",
        help="Watch a directory/file for changes and trigger an iteration when a file is modified. Uses os.stat() polling.",
    )
    parser.add_argument(
        "--watch-poll",
        type=float,
        default=5.0,
        help="File watcher poll interval in seconds (default: 5.0, only used with --watch-dir)",
    )
    parser.add_argument(
        "--worker-url",
        default="auto",
        help="Hermes worker URL. 'auto' (default) = start worker internally. "
        "http://host:port = connect to external worker. "
        "'' = direct subprocess mode (no worker).",
    )

    # v11.4.0 flags — cooldown, goals file, stop at goals end
    parser.add_argument(
        "--cooldown",
        type=int,
        default=0,
        help="Wait N seconds between iterations for rate-limit awareness (default: 0). "
        "Useful when many short iterations would hit API rate limits.",
    )
    parser.add_argument(
        "--goals-file",
        default="",
        help="Path to file with one goal per line. Each iteration pops the next goal "
        "from the file. Useful for batch processing (e.g., fix 50 lint errors). "
        "Lines starting with '#' are ignored as comments.",
    )
    parser.add_argument(
        "--stop-at-goals-end",
        action="store_true",
        help="When used with --goals-file, stop the loop when all goals are exhausted "
        "instead of wrapping around and reusing them.",
    )

    # v13.1.0 flags — Idempotent Goal Execution
    parser.add_argument(
        "--track-goals",
        action="store_true",
        default=False,
        help="When used with --goals-file, track completed goals so crashed/restarted "
        "runs automatically skip already-finished goals.",
    )
    parser.add_argument(
        "--reset-goals",
        action="store_true",
        default=False,
        help="When used with --track-goals, clear the goals_completed ledger on startup "
        "and re-process all goals from scratch.",
    )

    # v14.0.0 flags — Heartbeat-Based Session Self-Healing
    parser.add_argument(
        "--heartbeat-timeout",
        type=int,
        default=0,
        help="Enable heartbeat-based session health monitoring. "
        "Set to seconds of inactivity before a session is considered hung (default: 0 = disabled). "
        "Grace period is always heartbeat_timeout * 2 (total window = timeout * 3). "
        "When a session's heartbeat stops, the daemon kills it and retries.",
    )

    # v11.5.0 flags — structured output, adaptive cooldown, convergence, diff storage
    parser.add_argument(
        "--output-schema",
        default="",
        help="Inline JSON Schema as JSON string to validate spawned session output. "
        "Uses stdlib-only validation (required fields, types, enum, length/range checks). "
        'Example: \'{"type":"object","required":["summary"],"properties":{"summary":{"type":"string"}}}\'',
    )
    parser.add_argument(
        "--output-schema-file",
        default="",
        help="Path to a JSON Schema file for spawned output validation. "
        "Alternative to --output-schema for complex schemas.",
    )
    parser.add_argument(
        "--startup-delay",
        type=float,
        default=0.0,
        help="Wait N seconds before the first iteration (default: 0). Useful for debugging.",
    )
    parser.add_argument(
        "--notify-desktop",
        action="store_true",
        help="Send desktop notifications via notify-send on each iteration result (Linux only)",
    )
    parser.add_argument(
        "--notify-on-completion",
        action="store_true",
        help="Send a summary notification when the daemon finishes",
    )
    parser.add_argument(
        "--notify-pushbullet",
        default="",
        help="Pushbullet API access token for mobile notifications. "
        "If set, sends iteration results to your phone. "
        "Get token at https://www.pushbullet.com/#settings",
    )
    parser.add_argument(
        "--notify-ntfy",
        default="",
        help="ntfy topic name for push notifications. "
        "If set, sends iteration results via ntfy.sh (or your own server with --notify-ntfy-server). "
        "Example: 'my-loop-alerts'",
    )
    parser.add_argument(
        "--notify-ntfy-server",
        default="https://ntfy.sh",
        help="ntfy server URL (default: https://ntfy.sh). "
        "Use a self-hosted ntfy server URL for private notifications.",
    )
    parser.add_argument(
        "--save-config",
        default="",
        help="Save current configuration to a JSON file and exit. Path to output file.",
    )
    parser.add_argument(
        "--config",
        default="",
        help="Load configuration from a JSON file. Overrides default values, command-line flags take precedence.",
    )
    parser.add_argument(
        "--cooldown-mode",
        default="fixed",
        choices=["fixed", "adaptive"],
        help="Cooldown mode: 'fixed' = wait exactly --cooldown seconds (default), "
        "'adaptive' = auto-calculate delay based on average iteration duration. "
        "Fast iterations get longer cooldowns (rate-limit protection), "
        "long iterations get shorter cooldowns. Default: fixed",
    )
    parser.add_argument(
        "--convergence-stop",
        action="store_true",
        help="Auto-stop when N consecutive iterations produce similar summaries "
        "(stuck detection). Uses word-overlap Jaccard similarity.",
    )
    parser.add_argument(
        "--convergence-threshold",
        type=float,
        default=DEFAULT_CONVERGENCE_THRESHOLD,
        help=f"Similarity threshold for convergence detection (0.0-1.0, default: {DEFAULT_CONVERGENCE_THRESHOLD}). "
        "Higher = more permissive (only identical summaries trigger). "
        "Lower = more aggressive (similar but not identical triggers).",
    )
    parser.add_argument(
        "--convergence-window",
        type=int,
        default=DEFAULT_CONVERGENCE_WINDOW,
        help=f"Number of recent iterations to compare for convergence (default: {DEFAULT_CONVERGENCE_WINDOW}). "
        "All pairs in the window must exceed the threshold.",
    )
    parser.add_argument(
        "--store-git-diff",
        action="store_true",
        help="Store the actual git diff (not just stats) in the ledger. "
        "Capped at 10KB per iteration to prevent ledger bloat. "
        "Useful for reviewing changes without shell access.",
    )

    # v11.11.0 flags — AIAgent library mode, session tracking, checkpoints
    parser.add_argument(
        "--use-library",
        action="store_true",
        help="Use AIAgent.run_conversation() in-process instead of spawning "
        "a subprocess. Falls back to subprocess mode automatically if the "
        "AIAgent library is not importable. Compatible with --workers > 1 "
        "(uses multiprocessing for true parallelism).",
    )
    parser.add_argument(
        "--pass-session-id",
        action="store_true",
        help="Pass session ID to spawned sessions. The spawned Hermes session "
        "prints its session_id at the end of output. In subprocess mode, the "
        "daemon extracts it and stores it in the ledger as spawned_session_id. "
        "In library mode, the session_id is obtained directly from AIAgent.",
    )
    parser.add_argument(
        "--checkpoints",
        action="store_true",
        help="Enable file checkpoints in spawned sessions. Passes --checkpoints "
        "to the spawned chat -q command (subprocess mode) or sets "
        "checkpoints_enabled=True (library mode). Auto-enabled when --git is set.",
    )

    # v11.12.0 flags — session chaining, skills, ignore-rules
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Chain spawned sessions across iterations — each new session inherits "
        "the full conversation history of the previous one via --resume SESSION_ID. "
        "Requires --pass-session-id to populate the session_id in the ledger.",
    )
    parser.add_argument(
        "--skills",
        default="",
        help="Skills to preload in spawned Hermes sessions (comma-separated or repeat flag). "
        "For subprocess mode only; ignored in library mode.",
    )
    parser.add_argument(
        "--ignore-rules",
        action="store_true",
        help="Start spawned sessions without loading AGENTS.md, memory, or rules "
        "(clean-slate mode). Passes --ignore-rules to spawned hermes chat -q.",
    )

    # v11.13.0 flags — yolo mode, ignore-user-config, source tagging
    parser.add_argument(
        "--yolo",
        action="store_true",
        help="Bypass all dangerous command approval prompts in spawned sessions. "
        "Combine with --ignore-rules for fully autonomous operation.",
    )
    parser.add_argument(
        "--ignore-user-config",
        action="store_true",
        help="Pass --ignore-user-config to spawned sessions so they skip "
        "~/.hermes/config.yaml and fall back to built-in defaults.",
    )
    parser.add_argument(
        "--spawn-source",
        default="infinite-loop",
        help="Source tag for spawned sessions (passed as --source to hermes chat -q). "
        "Default: 'infinite-loop'. Set to empty string '' for no source tag.",
    )

    # v11.14.0 flags — safe-mode, accept-hooks, worktree, continue for spawned sessions
    parser.add_argument(
        "--safe-mode",
        action="store_true",
        help="Troubleshooting mode: disable ALL customizations in spawned sessions — "
        "user config, AGENTS.md/memory injection, plugins, and MCP servers. "
        "Implies --ignore-user-config and --ignore-rules. Passes --safe-mode to spawned chat -q.",
    )
    parser.add_argument(
        "--accept-hooks",
        action="store_true",
        help="Auto-approve shell hooks in spawned sessions. "
        "Passes --accept-hooks to spawned hermes chat -q.",
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="Run spawned sessions in an isolated git worktree. "
        "Passes --worktree to spawned hermes chat -q.",
    )
    parser.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="Resume the most recent session in spawned sessions. "
        "Passes --continue to spawned hermes chat -q.",
    )

    # v11.8.0 flags — preflight health checks
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Run preflight health checks and exit (or before loop when --run is used). "
        "Checks: hermes binary, workdir, git repo, sentinel, context/goals/schema files, "
        "webhook port, disk space.",
    )
    parser.add_argument(
        "--preflight-fail-fast",
        action="store_true",
        help="Exit immediately on the first preflight check failure.",
    )

    parser.add_argument(
        "--evolve",
        action="store_true",
        help="Let iterations propose the next goal (self-directing)",
    )
    parser.add_argument(
        "--git", action="store_true", help="Capture git diff stats per iteration"
    )
    parser.add_argument(
        "--git-commit",
        action="store_true",
        help="Auto-commit changes per iteration (implies --git)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Run N concurrent Hermes sessions per iteration",
    )
    parser.add_argument(
        "--notify-cmd",
        default="",
        help="Shell command to run after each iteration (receives JSON on stdin)",
    )
    parser.add_argument(
        "--max-output-chars",
        type=int,
        default=2000,
        help="Max chars of spawned output to store (0=unlimited)",
    )
    parser.add_argument(
        "--max-idle-iterations",
        type=int,
        default=0,
        help="Stop after N consecutive iterations with no git changes (requires --git)",
    )
    parser.add_argument(
        "--status-file",
        default=STATUS_FILE_DEFAULT,
        help="Path to write one-line JSON status file for external monitoring",
    )

    args = parser.parse_args()
    toolsets_list = [t.strip() for t in args.toolsets.split(",") if t.strip()]

    # Ensure delegation is in toolsets
    if "delegation" not in toolsets_list:
        toolsets_list.append("delegation")
        _log("[INFO] Added 'delegation' to toolsets (required for subagent spawning)")

    # Validate
    if args.git_commit and not args.git:
        _log("[INFO] --git-commit implies --git, enabling --git automatically")
        args.git = True
    if args.workers < 1:
        _log("[ERROR] --workers must be >= 1")
        sys.exit(1)
    if args.max_idle_iterations > 0 and not args.git:
        _log(
            "[WARN] --max-idle-iterations requires --git to detect changes. Idle detection will be disabled."
        )
        args.max_idle_iterations = 0
    if args.use_library and args.workers > 1:
        _log("[NOTE] --use-library with --workers > 1 -> using multiprocessing.Pool")
    if args.checkpoints and not args.git:
        _log(
            "[INFO] --checkpoints auto-enabled (implied by --git is not set but flag is active)"
        )

    # Check hermes is available
    hermes_bin = find_hermes()
    if (
        not shutil.which(hermes_bin)
        and hermes_bin == "hermes"
        and not shutil.which("hermes")
    ):
        _log("[WARN] 'hermes' binary not found on PATH.")
        _log(
            "[WARN] Install: curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
        )
        _log(
            "[WARN] The loop will fail on the first iteration if hermes is not available."
        )

    # Preflight health checks
    if args.preflight or args.run:
        results = PreflightChecker.run_all(
            hermes_required=True,
            workdir=args.workdir,
            sentinel_path=args.shutdown_sentinel,
            webhook_port=args.webhook_port,
            context_file=args.context_file,
            goals_file=args.goals_file,
            schema_file=args.output_schema_file,
            check_git=args.git or args.git_commit,
            check_disk="/tmp",
            fail_fast=args.preflight_fail_fast,
        )
        _log(PreflightChecker.format_results(results))
        all_passed = all(r["passed"] for r in results)
        if args.preflight:
            _log("[PREFLIGHT] --preflight specified. Exiting.")
            sys.exit(0 if all_passed else 1)
        if not all_passed:
            _log(
                "[WARN] Some preflight checks failed. Continuing anyway (use --preflight-fail-fast to abort)."
            )

    _log("═══════════════════════════════════════════════════════════════════")
    _log(f"  Infinite Loop Daemon v{LAUNCH_LOOP_VERSION}")
    _log("═══════════════════════════════════════════════════════════════════")
    _log("  Features: evolve | workers | cooldown | convergence | preflight")
    _log("            git | goals-file | webhook | SSE dashboard | heartbeat")
    _log("            desktop/Pushbullet/ntfy | library mode | yolo | safe-mode")
    _log("            self-test | status-html | checkpoint | resume | archiving")
    _log("═══════════════════════════════════════════════════════════════════")

    # Clean up stale heartbeat files from previous daemon instances
    if args.heartbeat_timeout > 0:
        _cleanup_stale_heartbeats()
    _log(f"  Goal:           {args.goal}")
    _log(f"  Context:        {len(args.context)} chars")
    _log(f"  Toolsets:       {toolsets_list}")
    if args.context_file:
        _log(f"  Context file:   {args.context_file}")
    else:
        _log(f"  Context file:   (none, using --context)")
    _log(f"  Workdir:        {args.workdir or os.getcwd()}")
    _log(
        f"  Max iterations: {args.max_iterations if args.max_iterations > 0 else 'infinite'}"
    )
    _log(f"  Compact:        every {args.compact_every} iterations")
    _log(f"  Max turns:      {args.max_turns} per spawned session")
    _log(f"  Retry delay:    {args.retry_delay}s")
    _log(f"  Session timeout: {args.session_timeout}s")
    _log(f"  Hermes binary:  {hermes_bin}")
    mode_str = args.worker_url if args.worker_url else "(none, direct subprocess)"
    if args.worker_url == "auto":
        mode_str = "auto (embedded worker)"
    _log(f"  Worker URL:     {mode_str}")
    _log(f"  Evolve:         {'yes' if args.evolve else 'no'}")
    _log(f"  Git snapshots:  {'yes' if args.git else 'no'}")
    _log(f"  Auto-commit:    {'yes' if args.git_commit else 'no'}")
    _log(f"  Workers:        {args.workers}")
    _log(f"  Notify cmd:     {args.notify_cmd or 'none'}")
    _log(
        f"  Output cap:     {args.max_output_chars if args.max_output_chars > 0 else 'unlimited'} chars"
    )
    _log(
        f"  Max idle iters: {args.max_idle_iterations if args.max_idle_iterations > 0 else 'off'}"
    )
    _log(f"  Status file:    {args.status_file or 'none'}")
    _log(f"  Profile:        {args.profile or '(default)'}")
    _log(f"  Model:          {args.model or '(default)'}")
    _log(f"  Provider:       {args.provider or '(default)'}")
    _log(f"  HTTP callback:  {args.http_callback or 'none'}")
    _log(
        f"  Keep iterations:{args.keep_iterations if args.keep_iterations > 0 else 'all'}"
    )
    _log(f"  Archive dir:    {args.archive_dir or 'disabled'}")
    _log(
        f"  Archive retention: {args.archive_retention}d"
        if args.archive_retention > 0
        else "  Archive retention: forever"
    )
    _log(f"  Max retries:    {args.max_retries}")
    _log(f"  On-error cmd:   {args.on_error_cmd or 'none'}")
    _log(f"  Tag:            {args.tag or '(none)'}")
    _log(f"  Prompt suffix:  {args.prompt_suffix or '(none)'}")
    _log(f"  Force reset:    {'yes' if args.force_reset else 'no'}")
    _log(f"  Auto toolsets:  {'yes' if not args.no_auto_toolsets else 'no'}")
    _log(
        f"  Auto task type: {args.task_type if args.task_type != 'auto' else 'auto-detect'}"
    )
    _log(f"  Failure learn:  {'yes' if not args.no_failure_learning else 'no'}")
    _log(
        f"  Webhook port:   {args.webhook_port if args.webhook_port > 0 else 'disabled'}"
    )
    _log(f"  Log file:       {args.log_file or 'stdout only'}")
    _log(f"  HTML dashboard: {args.status_html or 'disabled'}")
    _log(f"  Watch dir:      {args.watch_dir or 'disabled'}")
    _log(f"  Watch poll:     {args.watch_poll}s")
    _log(f"  Cooldown:       {args.cooldown}s, mode={args.cooldown_mode}")
    _log(
        f"  Convergence:    {'stop at threshold=' + str(args.convergence_threshold) if args.convergence_stop else 'disabled'}"
    )
    _log(f"  Store git diff: {'yes' if args.store_git_diff else 'no'}")
    _log(f"  Use library:    {'yes' if args.use_library else 'no'}")
    _log(f"  Pass session ID:{'yes' if args.pass_session_id else 'no'}")
    _log(f"  Checkpoints:    {'yes' if args.checkpoints else 'no'}")
    _log(f"  Resume sessions:{'yes' if args.resume else 'no'}")
    _log(f"  Skills:         {args.skills or 'none'}")
    _log(f"  Ignore rules:   {'yes' if args.ignore_rules else 'no'}")
    _log(f"  YOLO mode:      {'yes' if args.yolo else 'no'}")
    _log(f"  Ignore user cfg:{'yes' if args.ignore_user_config else 'no'}")
    _log(f"  Spawn source:   {args.spawn_source or '(default)'}")
    _log(f"  Safe mode:      {'yes' if args.safe_mode else 'no'}")
    _log(f"  Accept hooks:   {'yes' if args.accept_hooks else 'no'}")
    _log(f"  Worktree:       {'yes' if args.worktree else 'no'}")
    _log(f"  Continue:       {'yes' if args.continue_session else 'no'}")
    _log(
        f"  Output schema:  {args.output_schema_file or 'inline' if args.output_schema else ('file: ' + args.output_schema_file) if args.output_schema_file else 'none'}"
    )
    _log(f"  Goals file:     {args.goals_file or 'none'}")
    _log(f"  Stop at goals:  {'yes' if args.stop_at_goals_end else 'no (wrap)'}")
    _log(f"  Track goals:    {'yes' if args.track_goals else 'no'}")
    _log(f"  Reset goals:    {'yes' if args.reset_goals else 'no'}")
    _log(f"  Dry run:        {'yes' if args.dry_run else 'no'}")
    _log(f"  Ledger:         {LEDGER_PATH}")
    _log(f"  Sentinel:       echo 'stop' > {args.shutdown_sentinel}")
    _log("")

    if not args.run:
        _log("  Run with --run to start the actual loop.")
        _log("")
        if args.dry_run:
            _log("  [DRY RUN] No sessions will be spawned. Exiting.")
            sys.exit(0)

    # Resolve context
    resolved_context = args.context
    if args.context_file:
        try:
            with open(args.context_file) as cf:
                resolved_context = cf.read().strip()
            _log(
                f"[INFO] Read context from {args.context_file} ({len(resolved_context)} chars)"
            )
        except (FileNotFoundError, IOError) as e:
            _log(f"[ERROR] Could not read --context-file {args.context_file}: {e}")
            sys.exit(1)

    # Force reset
    if args.force_reset and os.path.exists(LEDGER_PATH):
        try:
            os.remove(LEDGER_PATH)
            _log("[INFO] Forced reset: removed existing ledger")
        except OSError as e:
            _log(f"[WARN] Could not remove ledger: {e}")

    state = load_or_create_ledger(
        goal=args.goal,
        context=resolved_context,
        sentinel_path=args.shutdown_sentinel,
        reset_goals=args.reset_goals,
    )
    state["toolsets"] = toolsets_list
    state["compact_every"] = args.compact_every
    state["max_iterations"] = args.max_iterations
    state["retry_delay"] = args.retry_delay
    state["workdir"] = args.workdir or ""
    state["session_timeout"] = args.session_timeout
    state["evolve"] = args.evolve
    state["git"] = args.git
    state["git_commit"] = args.git_commit
    state["workers"] = args.workers
    state["notify_cmd"] = args.notify_cmd
    state["max_output_chars"] = args.max_output_chars
    state["max_idle_iterations"] = args.max_idle_iterations
    state["status_file"] = args.status_file
    state["profile"] = args.profile
    state["model"] = args.model
    state["provider"] = args.provider
    state["http_callback"] = args.http_callback
    state["keep_iterations"] = args.keep_iterations
    state["tag"] = args.tag
    state["prompt_suffix"] = args.prompt_suffix
    state["max_turns"] = args.max_turns
    state["output_schema_file"] = args.output_schema_file or ""
    state["output_schema_inline"] = args.output_schema or ""
    state["yolo"] = args.yolo
    state["ignore_user_config"] = args.ignore_user_config
    state["spawn_source"] = args.spawn_source
    write_ledger(state)

    # Load config from file (command-line args override file values)
    if args.config:
        config_path = os.path.expanduser(args.config)
        try:
            with open(config_path) as f:
                file_config = json.load(f)
            # Apply file config values, but CLI args take precedence
            for key, val in file_config.items():
                if (
                    key in args
                    and getattr(args, key) not in (None, "", False, 0)
                    and key not in ("config", "run", "force_reset")
                ):
                    continue  # CLI arg takes precedence
                if hasattr(args, key):
                    setattr(args, key, val)
            _log(f"[CONFIG] Loaded config from {config_path}")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            _log(f"[CONFIG] WARN: Could not load config from {config_path}: {e}")

    # Save config and exit
    if args.save_config:
        config_path = os.path.expanduser(args.save_config)
        # Collect all non-None, non-default args into a config dict
        config_dict = {
            key: val
            for key, val in vars(args).items()
            if val not in (None, "") and not key.startswith("_")
        }
        config_dict["version"] = VERSION
        os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config_dict, f, indent=2)
        _log(f"[CONFIG] Saved configuration to {config_path}")
        sys.exit(0)

    # Resolve task type
    resolved_task_type = args.task_type
    if resolved_task_type == "auto":
        resolved_task_type, _, _ = detect_task_type(args.goal)

    if args.run:
        # Initialize daemon log file before the loop
        if args.log_file:
            _init_daemon_log(args.log_file, args.log_max_mb)

        _log("  Starting loop...")
        _log(f"  Sentinel: echo 'stop' > {args.shutdown_sentinel}")
        _log("")
        run_loop(
            goal=args.goal,
            context=resolved_context,
            toolsets=toolsets_list,
            workdir=args.workdir or None,
            sentinel_path=args.shutdown_sentinel,
            max_iterations=args.max_iterations,
            compact_every=args.compact_every,
            retry_delay=args.retry_delay,
            session_timeout=args.session_timeout,
            state=state,
            status_file=args.status_file,
            max_idle_iterations=args.max_idle_iterations,
            evolve=args.evolve,
            git=args.git,
            git_commit=args.git_commit,
            workers=args.workers,
            notify_cmd=args.notify_cmd or None,
            max_output_chars=args.max_output_chars,
            profile=args.profile,
            model=args.model,
            provider=args.provider,
            http_callback=args.http_callback,
            keep_iterations=args.keep_iterations,
            archive_dir=args.archive_dir,
            archive_retention=args.archive_retention,
            archive_max_size=args.archive_max_size,
            max_retries=args.max_retries,
            on_error_cmd=args.on_error_cmd or None,
            tag=args.tag,
            prompt_suffix=args.prompt_suffix,
            max_turns=args.max_turns,
            auto_toolsets=not args.no_auto_toolsets,
            failure_learning=not args.no_failure_learning,
            # v11.2.0 new features
            html_dashboard=args.status_html,
            webhook_port=args.webhook_port,
            watch_dir=args.watch_dir,
            watch_poll=args.watch_poll,
            # v11.3.0: Hermes worker URL for self-reference
            worker_url=args.worker_url,
            # v11.4.0: Cooldown and goals file
            cooldown=args.cooldown,
            goals_file=args.goals_file,
            stop_at_goals_end=args.stop_at_goals_end,
            # v11.5.0: Structured output, adaptive cooldown, convergence, diff storage
            output_schema=(
                json.loads(args.output_schema) if args.output_schema else None
            )
            or (
                load_json_schema(args.output_schema_file)
                if args.output_schema_file
                else None
            ),
            cooldown_mode=args.cooldown_mode,
            convergence_threshold=args.convergence_threshold,
            convergence_window=args.convergence_window,
            convergence_stop=args.convergence_stop,
            store_git_diff=args.store_git_diff,
            # v11.7.0: startup delay, desktop notifications, completion notification
            startup_delay=args.startup_delay,
            notify_desktop=args.notify_desktop,
            notify_on_completion=args.notify_on_completion,
            # v11.9.0: Pushbullet and ntfy push notifications
            notify_pushbullet=args.notify_pushbullet,
            notify_ntfy=args.notify_ntfy,
            notify_ntfy_server=args.notify_ntfy_server,
            # v11.11.0: AIAgent library mode, session tracking, checkpoints
            use_library=args.use_library,
            pass_session_id=args.pass_session_id,
            checkpoints=args.checkpoints,
            # v11.12.0: session chaining, skills, ignore-rules
            resume=args.resume,
            resume_session_id=state.get("resume_session_id", ""),
            skills=args.skills,
            ignore_rules=args.ignore_rules,
            # v11.13.0: yolo mode, ignore-user-config, source tagging
            yolo=args.yolo,
            ignore_user_config=args.ignore_user_config,
            spawn_source=args.spawn_source,
            # v11.14.0: safe-mode, accept-hooks, worktree, continue
            safe_mode=args.safe_mode,
            accept_hooks=args.accept_hooks,
            worktree=args.worktree,
            continue_session=args.continue_session,
            # v13.1.0: Idempotent Goal Execution
            track_goals=args.track_goals,
            reset_goals=args.reset_goals,
            # v14.0.0: Heartbeat-based session self-healing
            heartbeat_timeout=args.heartbeat_timeout,
        )

    # After the loop ends, send completion notification if requested
    if args.notify_on_completion or args.notify_pushbullet or args.notify_ntfy:
        _send_completion_notification(
            state,
            notify_pushbullet=args.notify_pushbullet,
            notify_ntfy=args.notify_ntfy,
            notify_ntfy_server=args.notify_ntfy_server,
        )

    _log("Done.")


if __name__ == "__main__":
    main()
