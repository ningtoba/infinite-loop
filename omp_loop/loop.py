"""Main loop logic — run_loop function.

Simplified task execution loop that spawns subprocess workers and tracks
progress in a JSON ledger.
"""

# ruff: noqa: ARG001, F841 — many run_loop() params are part of the 71-param
# signature tracked as TECHDEPT-001; fixing unused args requires the
# LoopConfig dataclass refactor. F841 covers dead local assignments from
# the cfg.* local-extraction block.

import html
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .color_utils import colorizer
from .config import VERSION, LoopConfig, _get_data_dir
from .error_recovery import _adapt_to_error, _set_originals
from .error_utils import _suggest_actionable_fix
from .events import emit_event
from .file_utils import _log, write_ledger, write_status_file
from .functions import (
    _build_progressive_context,
    _cycle_goal,
    _handle_cooldown,
    _load_goals_file,
    _log_startup_banner,
)
from .git_utils import _capture_git_state, _git_auto_commit
from .stats import _recalc_stats
from .status import write_status as _write_status_file
from .system_utils import get_system_usage, get_system_usage_diff


# ── Security guardrails ───────────────────────────────────▸
def _validate_on_error_cmd(cmd: str, allow_metachars: bool = False) -> tuple[bool, str]:
    """Validate an on_error_cmd before execution with shell=True.

    Returns (is_valid, reason) tuple. When invalid, the caller should
    skip execution and log the reason.
    """
    if not cmd or not cmd.strip():
        return False, "Command is empty"
    if len(cmd) > 500:
        return False, f"Command exceeds 500 character limit ({len(cmd)} chars)"
    if not allow_metachars:
        # Reject shell metacharacters that enable multi-command / injection
        dangerous = {
            ";": "semicolon (multi-command)",
            "|": "pipe (chained command)",
            "`": "backtick (command substitution)",
            "$": "dollar sign (variable expansion)",
            "&": "ampersand (backgrounding)",
            "\n": "newline (multi-line command)",
            "\r": "carriage return",
            ">": "output redirection",
            "<": "input redirection",
        }
        for char, desc in dangerous.items():
            if char in cmd:
                return False, f"Shell metacharacter '{desc}' found in command (use --allow-error-metachars to override)"
    return True, "OK"


# Module-level shutdown flag (threading.Event for safe signal-handler access)
_shutdown_requested = threading.Event()


def _drain_pipe(buf: list[str], stream: Any) -> None:
    """Drain a pipe into a list, used as a concurrent daemon thread target."""
    for line in stream:
        buf.append(line)


def _request_shutdown() -> None:
    """Set the shutdown flag — called by signal handler."""
    global _shutdown_requested
    _shutdown_requested.set()


def _execute_task(
    goal: str,
    context: str,
    workdir: str | None,
    session_timeout: int,
    max_output_chars: int = 2000,
    max_turns: int = 500,
    max_retries: int = 0,
    retry_delay: int = 5,
    worker_id: int = 1,
) -> dict:
    """Execute a single task via omp subprocess with --mode json.

    Streams NDJSON events (thinking, tool calls, responses) line-by-line
    with [TERM (worker #1)] prefix so the web UI's xterm.js terminal
    shows a rich real-time view of the entire omp session.
    Returns a result dict with 'output' (final assistant text), 'error',
    'duration_seconds', etc.
    """
    cmd = ["omp", "-a", "--mode", "json", goal]
    if context:
        cmd.extend(["--append-system-prompt", context])

    print(f"[SPAWN (worker #{worker_id})] omp --mode json -- {goal[:60]}")

    start_time = time.time()
    attempts = 0
    max_attempts = max(1, max_retries + 1)
    last_error = None
    all_attempts_output: list[str] = []
    proc = None

    def _term(line: str) -> None:
        sys.stdout.write(f"[TERM (worker #{worker_id})] {line}\n")
        emit_event("term", worker_id=worker_id, line=line)
        sys.stdout.flush()

    while attempts < max_attempts:
        attempts += 1
        attempt_start = time.time()
        # Reset per-attempt buffers to prevent stale data leak (TECHDEBT-011)
        attempt_final_text_parts: list[str] = []
        attempt_text_buf: list[str] = []
        attempt_raw_lines: list[str] = []
        _stderr_buf: list[str] = []
        _stderr_thread: threading.Thread | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=workdir or os.getcwd(),
            )

            if proc.stdout is None:
                raise RuntimeError("omp subprocess has no stdout pipe")

            # Drain stderr concurrently in a daemon thread to prevent
            # deadlock when the subprocess fills the ~64KB stderr pipe
            # buffer while stdout is still being consumed.
            _stderr_stream: Any = proc.stderr
            if _stderr_stream is not None:
                _stderr_thread = threading.Thread(
                    target=_drain_pipe,
                    args=(_stderr_buf, _stderr_stream),
                    daemon=True,
                )
                _stderr_thread.start()

            for raw_line in proc.stdout:
                # Enforce session timeout between stdout lines
                if time.time() - attempt_start > session_timeout:
                    proc.kill()
                    raise subprocess.TimeoutExpired(cmd, session_timeout)

                line = raw_line.rstrip("\n").rstrip("\r")
                attempt_raw_lines.append(line)
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    _term(line)
                    continue

                etype = event.get("type", "")

                if etype == "message_update":
                    ame = event.get("assistantMessageEvent", {})
                    if not isinstance(ame, dict):
                        continue
                    ame_type = ame.get("type", "")

                    # Skip noisy thinking deltas (token-by-token)
                    if ame_type == "thinking_delta":
                        continue

                    # Text output delta — accumulate chars, emit on line break
                    if ame_type == "text_delta":
                        attempt_text_buf.append(ame.get("delta", ""))
                        full = "".join(attempt_text_buf)
                        if "\n" in full:
                            *done, rest = full.split("\n")
                            for ln in done:
                                if ln.strip():
                                    _term(ln)
                            attempt_text_buf.clear()
                            attempt_text_buf.append(rest)
                        continue

                    # Tool call start
                    if ame_type == "content_block_start":
                        delta = ame.get("delta", {})
                        if isinstance(delta, dict) and delta.get("type") == "tool_use":
                            name = delta.get("name", "tool")
                            inp = delta.get("input", {})
                            inp_str = json.dumps(inp, default=str)[:120]
                            _term(f"[Tool: {name}({inp_str})]")
                        continue

                    # Tool result
                    if ame_type == "content_block_stop":
                        delta = ame.get("delta", {})
                        if isinstance(delta, dict) and delta.get("type") == "tool_result":
                            result_content = delta.get("content", "")
                            if isinstance(result_content, list):
                                for cb in result_content:
                                    if isinstance(cb, dict) and cb.get("type") == "text":
                                        _term(f"[Result: {cb.get('text', '')[:200]}]")
                            elif isinstance(result_content, str):
                                _term(f"[Result: {result_content[:200]}]")
                        continue

                    # Usage info — show as summary line
                    if ame_type == "usage":
                        usage = ame.get("usage", {})
                        if isinstance(usage, dict):
                            tokens = usage.get("totalTokens", "")
                            cost = usage.get("cost", {}).get("total", "")
                            items = []
                            if tokens:
                                items.append(f"{tokens} tokens")
                            if cost:
                                items.append(f"${cost}")
                            if items:
                                _term(f"[Tokens: {', '.join(items)}]")
                        continue

                    # agent_start / turn_start — skip ceremony
                    if ame_type in ("turn_start", "agent_start", "session"):
                        continue

                elif etype == "message_end":
                    msg = event.get("message", {})
                    for block in msg.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            attempt_final_text_parts.append(block.get("text", ""))

            duration = time.time() - attempt_start
            stdout_text = "\n".join(attempt_raw_lines)

            if _stderr_thread is not None:
                _stderr_thread.join(timeout=10)
            stderr_text = "".join(_stderr_buf)

            status_str = "ok" if proc.returncode == 0 else "failed"
            print(f"[WORKER (worker #{worker_id})] Response in {duration:.1f}s (status={status_str})")
            emit_event(
                "worker_response",
                worker_id=worker_id,
                duration=round(duration, 1),
                status=status_str,
                returncode=proc.returncode,
            )
            sys.stdout.flush()

            if proc.returncode == 0:
                final_output = "\n".join(attempt_final_text_parts) if attempt_final_text_parts else stdout_text
                return {
                    "output": final_output[:max_output_chars] if max_output_chars else final_output,
                    "error": None,
                    "duration_seconds": round(duration, 1),
                    "returncode": 0,
                }
            else:
                last_error = f"exit code {proc.returncode}: {stderr_text[:500] or stdout_text[:500]}"
                all_attempts_output.append(f"[Attempt {attempts}] {last_error}")
                if attempts < max_attempts:
                    _log(f"[RETRY] Attempt {attempts}/{max_attempts} failed: {last_error[:120]}")
                    time.sleep(retry_delay)

        except subprocess.TimeoutExpired:
            duration = time.time() - attempt_start
            last_error = f"timeout after {session_timeout}s"
            all_attempts_output.append(f"[Attempt {attempts}] {last_error}")
            _log(f"[RETRY] Attempt {attempts}/{max_attempts} timed out ({session_timeout}s)")
            # Kill the orphaned process to prevent zombie accumulation
            if proc is not None:
                with suppress(Exception):
                    proc.kill()
                    proc.wait(timeout=5)
                # Join the stderr drain thread so its pipe reference is
                # released before the next retry attempt allocates a new proc.
                if _stderr_thread is not None:
                    _stderr_thread.join(timeout=5)
            if attempts < max_attempts:
                time.sleep(retry_delay)

        except FileNotFoundError:
            return {
                "error": "'omp' binary not found on PATH",
                "duration_seconds": round(time.time() - start_time, 1),
                "returncode": -1,
            }
        except Exception as e:
            duration = time.time() - attempt_start
            last_error = str(e)
            all_attempts_output.append(f"[Attempt {attempts}] {e}")
            # Kill any orphaned subprocess on unexpected errors
            if proc is not None:
                with suppress(Exception):
                    proc.kill()
                    proc.wait(timeout=5)
                if _stderr_thread is not None:
                    _stderr_thread.join(timeout=5)
            if attempts < max_attempts:
                time.sleep(retry_delay)

    combined_output = "\n".join(all_attempts_output) if all_attempts_output else ""
    return {
        "output": combined_output[:max_output_chars] if max_output_chars else combined_output,
        "error": last_error,
        "duration_seconds": round(time.time() - start_time, 1),
        "returncode": -1,
    }


def _print_shutdown_summary(
    state: dict,
    iteration_count: int,
    stop_reason: str,
    goal: str = "",
    git: bool = False,
    workers: int = 1,
) -> None:
    """Print a comprehensive shutdown summary banner."""
    data_dir = _get_data_dir()
    iters = state.get("iterations", [])
    total = iteration_count
    total_dur = state.get("stats", {}).get("total_duration_seconds", 0)
    success_count = sum(1 for it in iters if not it.get("error") and it.get("classification") != "stuck")
    error_count = sum(1 for it in iters if it.get("error"))
    error_type_counts = state.get("error_type_counts", {})
    err_types = []
    for err_type in ("timeout", "network", "schema", "unknown", "heartbeat"):
        cnt = error_type_counts.get(err_type, 0)
        if cnt:
            err_types.append(f"{err_type}={cnt}")

    c = colorizer
    _log("")
    _log(f"{c.header('═══════════════ SHUTDOWN SUMMARY ═══════════════')}")
    _log(f"  {c.value('Status:')}       {c.flag(stop_reason)}")
    _log(f"  {c.value('Iterations:')}   {c.flag(str(total))}")
    if total_dur > 0:
        dur_str = f"{total_dur:.0f}s"
        if total_dur >= 60:
            dur_str += f" ({total_dur / 60:.1f}m)"
        _log(f"  {c.value('Duration:')}    {c.dim(dur_str)}")
    _log(f"  {c.value('Success:')}     {c.tag_ok()}{success_count}")
    if error_count:
        _log(f"  {c.value('Errors:')}      {c.tag_fail()}{error_count}")
    if err_types:
        _log(f"  {c.value('Breakdown:')}   {c.dim(', '.join(err_types))}")
    if goal:
        _log(f"  {c.value('Final goal:')}  {c.dim(goal[:80])}")

    _log("")
    _log(f"  {c.group_title('Next steps:')}")
    _log(f'    {c.dim("Re-run:")}          omp-loop --goal "..." --run')
    _log(f"    {c.dim('Help:')}            omp-loop --help")
    _log(f"{c.header('══════════════════════════════════════════════')}")
    _log("")


def _shutdown(
    state: dict,
    iteration_count: int,
    status_file: str,
    stop_reason: str,
    *,
    goal: str = "",
    git: bool = False,
    workers: int = 1,
    last_error: str | None = None,
    write_status_file_entry: bool = True,
) -> None:
    """Unified shutdown sequence — set status, persist state, print summary."""
    state["status"] = stop_reason
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    write_ledger(state)
    write_status_file(status_file, state, iteration_count, stop_reason)
    if write_status_file_entry:
        from typing import Any

        kwargs: dict[str, Any] = {
            "running": False,
            "iteration_count": iteration_count,
            "version": VERSION,
        }
        if last_error is not None:
            kwargs["last_error"] = last_error
        _write_status_file(status_file, **kwargs)
    emit_event(
        "shutdown",
        reason=stop_reason,
        iteration_count=iteration_count,
        last_error=last_error,
    )
    _print_shutdown_summary(state, iteration_count, stop_reason, goal=goal, git=git, workers=workers)


def run_loop(
    cfg: "LoopConfig",
    state: dict,
) -> None:
    """Main task-execution loop.

    Accepts a ``LoopConfig`` dataclass (see omp_loop.config) and a mutable
    ``state`` dict.  All per-iteration configuration lives on ``cfg``.
    """
    global _shutdown_requested

    _shutdown_requested.clear()

    # ── Extract locals from config (for minimal diff vs old signature) ──
    goal = cfg.goal
    context = cfg.context
    workdir = cfg.workdir
    sentinel_path = cfg.sentinel_path
    max_iterations = cfg.max_iterations
    compact_every = cfg.compact_every
    retry_delay = cfg.retry_delay
    session_timeout = cfg.session_timeout
    status_file = cfg.status_file
    max_idle_iterations = cfg.max_idle_iterations
    evolve = cfg.evolve
    git = cfg.git
    git_commit = cfg.git_commit
    workers = cfg.workers
    notify_cmd = cfg.notify_cmd
    max_output_chars = cfg.max_output_chars
    profile = cfg.profile
    model = cfg.model
    provider = cfg.provider
    http_callback = cfg.http_callback
    http_callback_secret = cfg.http_callback_secret
    keep_iterations = cfg.keep_iterations
    archive_dir = cfg.archive_dir
    archive_retention = cfg.archive_retention
    archive_max_size = cfg.archive_max_size
    max_retries = cfg.max_retries
    on_error_cmd = cfg.on_error_cmd
    tag = cfg.tag
    prompt_suffix = cfg.prompt_suffix
    no_tool_shortcut = cfg.no_tool_shortcut
    max_turns = cfg.max_turns
    auto_toolsets = cfg.auto_toolsets
    failure_learning = cfg.failure_learning
    html_dashboard = cfg.html_dashboard
    webhook_port = cfg.webhook_port
    watch_dir = cfg.watch_dir
    watch_poll = cfg.watch_poll
    cooldown = cfg.cooldown
    goals_file = cfg.goals_file
    stop_at_goals_end = cfg.stop_at_goals_end
    output_schema = cfg.output_schema
    cooldown_mode = cfg.cooldown_mode
    convergence_threshold = cfg.convergence_threshold
    convergence_window = cfg.convergence_window
    convergence_stop = cfg.convergence_stop
    store_git_diff = cfg.store_git_diff
    startup_delay = cfg.startup_delay
    notify_desktop = cfg.notify_desktop
    notify_on_completion = cfg.notify_on_completion
    notify_pushbullet = cfg.notify_pushbullet
    notify_ntfy = cfg.notify_ntfy
    notify_ntfy_server = cfg.notify_ntfy_server
    use_library = cfg.use_library
    pass_session_id = cfg.pass_session_id
    checkpoints = cfg.checkpoints
    resume = cfg.resume
    resume_session_id = cfg.resume_session_id
    skills = cfg.skills
    ignore_rules = cfg.ignore_rules
    yolo = cfg.yolo
    ignore_user_config = cfg.ignore_user_config
    spawn_source = cfg.spawn_source
    safe_mode = cfg.safe_mode
    accept_hooks = cfg.accept_hooks
    worktree = cfg.worktree
    continue_session = cfg.continue_session
    track_goals = cfg.track_goals
    reset_goals = cfg.reset_goals
    heartbeat_timeout = cfg.heartbeat_timeout
    quiet = cfg.quiet
    force_reset = cfg.force_reset
    json_logs = cfg.json_logs

    _set_originals(session_timeout, cooldown, use_library, workers)

    iteration_count = state["total_iterations"]
    existing_summaries = [it.get("summary", "") for it in state.get("iterations", [])]
    consecutive_errors = state.get("stats", {}).get("consecutive_errors", 0)
    consecutive_successes = state.get("stats", {}).get("consecutive_successes", 0)
    consecutive_idle = 0

    goals_tuples = _load_goals_file(goals_file, goal)
    # GoalSpec: (goal, profile, model, provider)
    goals_list = list(goals_tuples)
    goals_index = 0
    state["goals_specs"] = goals_tuples

    _write_status_file(status_file, running=True, iteration_count=iteration_count, version=VERSION)

    _log_startup_banner(
        task_type="generic",
        task_type_desc="Generic loop",
        profile=profile,
        model=model,
        max_iterations=max_iterations,
        max_retries=max_retries,
        _max_turns=max_turns,
        _tag=tag,
        goal=goal,
        toolsets=[],
        evolve=evolve,
        git=git,
        git_commit=git_commit,
        workers=workers,
        session_timeout=session_timeout,
        notify_cmd=notify_cmd,
        _use_library=use_library,
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
        quiet=quiet,
    )

    if on_error_cmd:
        _log(f"[WARNING] on_error_cmd is configured: {on_error_cmd[:120]}{'...' if len(on_error_cmd) > 120 else ''}")
        _log(
            "[WARNING] on_error_cmd runs with shell=True. "
            "Review SECURITY implications. Use --allow-error-metachars "
            "only if your command requires shell metacharacters."
        )

    if startup_delay > 0 and iteration_count == 0:
        _log(f"[DAEMON] Startup delay: {startup_delay}s before first iteration")
        time.sleep(startup_delay)

    while True:
        if _shutdown_requested.is_set():
            _log("[STOP] Shutdown signal received. Stopping.")
            _shutdown(
                state,
                iteration_count,
                status_file,
                "stopped: signal",
                goal=goal,
                git=git,
                workers=workers,
                last_error="stopped: signal",
            )
            return

        # Sentinel check
        if sentinel_path:
            from .file_utils import check_sentinel

            stop_signal = check_sentinel(sentinel_path)
            if stop_signal:
                _log(f"[STOP] Sentinel detected ('{stop_signal}'). Stopping.")
                _shutdown(
                    state,
                    iteration_count,
                    status_file,
                    f"stopped: {stop_signal}",
                    goal=goal,
                    git=git,
                    workers=workers,
                    last_error=f"stopped: {stop_signal}",
                )
                return

        if max_iterations > 0 and iteration_count >= max_iterations:
            stop_reason = f"stopped: max_iterations ({max_iterations})"
            _log(f"[STOP] Reached {stop_reason}. Stopping.")
            _shutdown(state, iteration_count, status_file, stop_reason, goal=goal, git=git, workers=workers)
            return

        if max_idle_iterations > 0 and consecutive_idle >= max_idle_iterations:
            stop_reason = f"stopped: idle ({consecutive_idle} iterations without changes)"
            _log(f"[STOP] Idle limit reached ({consecutive_idle} iterations). Stopping.")
            _shutdown(state, iteration_count, status_file, stop_reason, goal=goal, git=git, workers=workers)
            return

        iteration_count += 1
        iteration_start_time = datetime.now(timezone.utc).isoformat()
        emit_event(
            "iteration_start",
            n=iteration_count,
            goal=goal[:200],
        )

        if quiet:
            _log(f"[ITER #{iteration_count}] {goal[:80]}{'...' if len(goal) > 80 else ''}")
        else:
            _log(f"{'=' * 60}")
            _log(f"    Iteration {iteration_count}")
            if max_iterations > 0:
                pct = min(100.0 * iteration_count / max_iterations, 100.0)
                bar_width = 25
                filled = bar_width * iteration_count // max_iterations
                bar = "█" * filled + "░" * (bar_width - filled)
                _log(f"    [{bar}] {iteration_count}/{max_iterations} — {pct:.0f}%")
            _log(f"    Goal: {goal[:100]}{'...' if len(goal) > 100 else ''}")
            _log(f"{'=' * 60}")

        # Cycle goals
        if len(goals_list) > 1:
            goals_index += 1
            goal_text, exhausted = _cycle_goal(goals_list, goals_index - 1, stop_at_goals_end)
            if exhausted:
                _shutdown(
                    state,
                    iteration_count,
                    status_file,
                    "stopped: goals-exhausted",
                    goal=goal,
                    git=git,
                    workers=workers,
                    write_status_file_entry=False,
                )
                return
        else:
            # Prefer evolved goal if one exists (consumed with pop to avoid stale reuse)
            if evolve and "evolved_goal" in state:
                goal_text = state.pop("evolved_goal")
                _log(f"[EVOLVE] Using evolved goal for iteration {iteration_count}")
            else:
                goal_text = goal

        # Build context from progressive summaries
        progressive_context = _build_progressive_context(context, existing_summaries)

        git_before = _capture_git_state(workdir, store_diff=store_git_diff) if git else {}
        sys_before = get_system_usage()

        # Execute task
        result = _execute_task(
            goal=goal_text,
            context=progressive_context,
            workdir=workdir,
            session_timeout=session_timeout,
            max_output_chars=max_output_chars,
            max_turns=max_turns,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        total_duration = result["duration_seconds"]
        combined_error = result["error"]
        combined_summary = result["output"][:500] if result["output"] else ""

        git_after = _capture_git_state(workdir, store_diff=store_git_diff) if git else {}
        git_commit_hash = None
        if git_commit and not combined_error:
            git_commit_hash = _git_auto_commit(workdir, iteration_count, combined_summary)

        # Idle detection
        if git:
            before_ds = git_before.get("diff_stat", "")
            after_ds = git_after.get("diff_stat", "")
            head_before = git_before.get("head", "")
            head_after = git_after.get("head", "")
            had_changes = (
                (before_ds != after_ds)
                or bool(head_before and head_after and head_before != head_after)
                or bool(git_commit_hash)
            )
            if not had_changes:
                consecutive_idle += 1
                _log(
                    f"[IDLE] No changes detected ({consecutive_idle}/{max_idle_iterations if max_idle_iterations > 0 else 'off'})"
                )
            else:
                consecutive_idle = 0

        # Classify error
        from .error_utils import classify_error

        primary_error_type = classify_error(combined_error)
        if primary_error_type:
            emit_event(
                "error_type",
                error_type=primary_error_type,
                iteration_n=iteration_count,
            )

        # Build record
        record = {
            "n": iteration_count,
            "started_at": iteration_start_time,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": total_duration,
            "summary": combined_summary[:200] if combined_summary else "",
            "compacted": False,
            "error": combined_error[:200] if combined_error else None,
            "classification": "error" if combined_error else "completed",
            "git": {
                "before": git_before,
                "after": git_after,
                "commit": git_commit_hash,
            }
            if git
            else {},
            "system": get_system_usage_diff(sys_before, get_system_usage()),
        }

        state["iterations"].append(record)
        state["total_iterations"] = iteration_count
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        state["status"] = "running"

        if combined_error:
            consecutive_errors += 1
            consecutive_successes = 0
            if primary_error_type:
                state.setdefault("error_type_counts", {})
                state["error_type_counts"][primary_error_type] = (
                    state["error_type_counts"].get(primary_error_type, 0) + 1
                )
        else:
            consecutive_successes += 1
            consecutive_errors = 0

        if json_logs:
            json_line = record.copy()
            print(json.dumps(json_line, default=str), flush=True)

        _recalc_stats(state)

        write_ledger(state)
        _write_status_file(
            status_file,
            running=True,
            iteration_count=iteration_count,
            last_error=combined_error,
            version=VERSION,
        )

        status_icon = "✓" if combined_error is None else "✗"
        _log(f"{status_icon} Iteration {iteration_count} ({total_duration}s): {combined_summary[:100]}")
        emit_event(
            "iteration_complete",
            n=iteration_count,
            duration_seconds=total_duration,
            has_error=combined_error is not None,
            error_type=primary_error_type,
        )

        # Suggestion
        suggestion = _suggest_actionable_fix(
            error_type=primary_error_type,
            classification=record.get("classification", "unknown"),
            goal=goal,
            workers=workers,
            use_library=use_library,
            consecutive_errors=consecutive_errors,
            git=git,
            git_commit=git_commit,
            force_reset=force_reset,
        )
        if suggestion:
            for line in suggestion.split("\n"):
                _log(f"[SUGGEST] {line}")

        # Notifications
        if notify_desktop:
            try:
                subprocess.run(
                    [
                        "notify-send",
                        "omp-loop",
                        combined_summary[:100] or f"Iteration {iteration_count}",
                    ],
                    timeout=5,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
                _log(f"[NOTIFY] Desktop notification failed: {e}")

        if html_dashboard:
            try:
                html = _build_dashboard_html(state)
                with open(html_dashboard, "w") as f:
                    f.write(html)
            except (OSError, KeyError, TypeError) as e:
                _log(f"[DASHBOARD] Failed to write HTML dashboard: {e}")

        if http_callback:
            parsed = urlparse(http_callback)
            if parsed.scheme not in ("http", "https"):
                _log(f"[HTTP-CALLBACK] WARNING: Invalid URL scheme '{parsed.scheme}' in http_callback — skipping")
            else:
                try:
                    data = json.dumps(record).encode()
                    req = urllib.request.Request(
                        http_callback,
                        data=data,
                        headers={"Content-Type": "application/json"},
                    )
                    if http_callback_secret:
                        req.add_header("Authorization", http_callback_secret)
                    urllib.request.urlopen(req, timeout=10)
                except (ImportError, OSError, ValueError, json.JSONDecodeError) as e:
                    _log(f"[HTTP-CALLBACK] Failed: {e}")

        # On-error command (with security guardrails)
        if combined_error and on_error_cmd:
            _log(f"[ERROR-CMD] Running: {on_error_cmd}")
            is_valid, reason = _validate_on_error_cmd(on_error_cmd, allow_metachars=cfg.allow_error_metachars)
            if not is_valid:
                _log(f"[ERROR-CMD] WARNING: Skipped — {reason}")
            else:
                try:
                    subprocess.run(on_error_cmd, shell=True, timeout=30)
                except (OSError, subprocess.TimeoutExpired) as e:
                    _log(f"[ERROR-CMD] Failed: {e}")

        # Cooldown
        _handle_cooldown(cooldown, cooldown_mode, None, "generic", shutdown_event=_shutdown_requested)

        # Error recovery adaptation
        if primary_error_type:
            state.setdefault("mitigations", {})
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
            for action in adapt_actions:
                _log(f"[AUTO-RECOVERY] {action}")

            if state.get("mitigations", {}).get("mitigation_level", 0) >= 3:
                _log("[AUTO-RECOVERY] Persistent failure detected — stopping daemon")
                err_type = primary_error_type or "unknown"
                stop_reason = f"stopped: {err_type}-failure"
                _shutdown(
                    state,
                    iteration_count,
                    status_file,
                    stop_reason,
                    goal=goal,
                    git=git,
                    workers=workers,
                    last_error=stop_reason,
                )
                return

        # Keep iteration cap
        if keep_iterations > 0 and len(state.get("iterations", [])) > keep_iterations * 2:
            state["iterations"] = state["iterations"][-keep_iterations:]
            state["total_iterations"] = iteration_count
            _recalc_stats(state)
            write_ledger(state)

        # Evolve: check omp output for NEXT_GOAL: marker
        if evolve and not combined_error and len(goals_list) <= 1:
            _evolve_goal(result.get("output", ""), state, iteration_count)


def _evolve_goal(output: str, state: dict, iteration: int) -> None:
    """Check omp output for NEXT_GOAL: header, update state if found."""
    for line in output.split("\n"):
        if line.strip().upper().startswith("NEXT_GOAL:"):
            next_goal = line.split(":", 1)[1].strip()
            if next_goal:
                _log(f"[EVOLVE] Iteration {iteration} proposed next goal: {next_goal[:80]}")
                state["evolved_goal"] = next_goal


def _build_dashboard_html(state: dict) -> str:
    """Build a minimal HTML dashboard for the loop state.

    IMPORTANT: All user-controlled values are HTML-escaped to prevent stored XSS.
    """
    iters = state.get("iterations", [])
    rows = ""
    for it in reversed(iters[-50:]):
        n = html.escape(str(it.get("n", "?")))
        status = "❌" if it.get("error") else "✅"
        dur = it.get("duration_seconds", 0)
        summary = html.escape((it.get("summary") or "")[:100])
        rows += f"<tr><td>{n}</td><td>{status}</td><td>{dur}s</td><td>{summary}</td></tr>\n"

    status_label = html.escape(str(state.get("status", "unknown")))
    return f"""<!DOCTYPE html>
<html><head><title>omp-loop Dashboard</title>
<meta charset="utf-8"><meta http-equiv="refresh" content="5">
<style>
body {{ font-family: sans-serif; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px 12px; text-align: left; }}
th {{ background: #f0f0f0; }}
tr:nth-child(even) {{ background: #fafafa; }}
</style></head><body>
<h1>omp-loop Dashboard</h1>
<p>Status: <strong>{status_label}</strong>
| Iterations: {len(iters)}
| Total: {state.get("stats", {}).get("total_duration_seconds", 0):.0f}s</p>
<table><thead><tr><th>#</th><th>Status</th><th>Duration</th><th>Summary</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>"""
