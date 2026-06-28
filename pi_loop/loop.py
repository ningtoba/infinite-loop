"""Main loop logic — run_loop function.

Simplified task execution loop that spawns subprocess workers and tracks
progress in a JSON ledger.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from .config import VERSION, DEFAULT_CONVERGENCE_THRESHOLD, DEFAULT_CONVERGENCE_WINDOW
from .file_utils import _log, write_ledger, write_status_file
from .error_recovery import _adapt_to_error, _set_originals
from .error_utils import _suggest_actionable_fix
from .functions import (
    _load_goals_file,
    _log_startup_banner,
    _build_progressive_context,
    _handle_cooldown,
)
from .git_utils import _capture_git_state, _git_auto_commit
from .system_utils import get_system_usage, get_system_usage_diff
from .color_utils import colorizer
from .stats import _recalc_stats
from .status import write_status as _write_status_file

# Module-level shutdown flag
_shutdown_requested = False


def _request_shutdown() -> None:
    """Set the shutdown flag — called by signal handler."""
    global _shutdown_requested
    _shutdown_requested = True


def _execute_task(
    goal: str,
    context: str,
    workdir: str | None,
    session_timeout: int,
    max_output_chars: int = 2000,
    max_turns: int = 500,
    max_retries: int = 0,
    retry_delay: int = 5,
) -> dict:
    """Execute a single task via pi subprocess.

    Streams pi output line-by-line with [TERM (worker #1)] prefix so the
    web UI's existing xterm.js terminal shows real-time output.
    Returns a result dict with 'output', 'error', 'duration_seconds', etc.
    """
    cmd = ["pi", "-a", "-p", goal]
    if context:
        cmd.extend(["--append-system-prompt", context])

    print(f"[SPAWN (worker #1)] pi -p {goal[:60]}")
    sys.stdout.flush()

    start_time = time.time()
    attempts = 0
    max_attempts = max(1, max_retries + 1)
    last_error = None
    all_output = []

    def _prefix(line: str) -> None:
        """Write a TERM-prefixed line to daemon stdout for web UI consumption."""
        sys.stdout.write(f"[TERM (worker #1)] {line}\n")
        sys.stdout.flush()

    while attempts < max_attempts:
        attempts += 1
        attempt_start = time.time()
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=workdir or os.getcwd(),
            )
            stdout_lines = []

            # Stream stdout line-by-line
            if proc.stdout is None:
                raise RuntimeError("pi subprocess has no stdout pipe")
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\n").rstrip("\r")
                stdout_lines.append(line)
                _prefix(line)

            proc.wait(timeout=session_timeout)
            duration = time.time() - attempt_start
            stdout_text = "\n".join(stdout_lines)

            # Read any remaining stderr
            stderr_text = ""
            if proc.stderr:
                stderr_text = proc.stderr.read()

            print(
                f"[WORKER (worker #1)] Response in {duration:.1f}s (status={'ok' if proc.returncode == 0 else 'failed'})"
            )
            sys.stdout.flush()

            if proc.returncode == 0:
                return {
                    "output": stdout_text[:max_output_chars]
                    if max_output_chars
                    else stdout_text,
                    "error": None,
                    "duration_seconds": round(duration, 1),
                    "returncode": 0,
                }
            else:
                last_error = f"exit code {proc.returncode}: {stderr_text[:500] or stdout_text[:500]}"
                if attempts < max_attempts:
                    _log(
                        f"[RETRY] Attempt {attempts}/{max_attempts} failed: {last_error[:120]}"
                    )
                    time.sleep(retry_delay)
                else:
                    all_output.append(stdout_text)

        except subprocess.TimeoutExpired:
            duration = time.time() - attempt_start
            last_error = f"timeout after {session_timeout}s"
            if attempts < max_attempts:
                _log(
                    f"[RETRY] Attempt {attempts}/{max_attempts} timed out ({session_timeout}s)"
                )
                time.sleep(retry_delay)

        except FileNotFoundError:
            return {
                "output": "",
                "error": "'pi' binary not found on PATH",
                "duration_seconds": round(time.time() - start_time, 1),
                "returncode": -1,
            }
        except Exception as e:
            duration = time.time() - attempt_start
            last_error = str(e)
            if attempts < max_attempts:
                time.sleep(retry_delay)

    return {
        "output": "\n".join(all_output)[:max_output_chars]
        if max_output_chars
        else "\n".join(all_output),
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
    iters = state.get("iterations", [])
    total = iteration_count
    total_dur = state.get("stats", {}).get("total_duration_seconds", 0)
    success_count = sum(
        1 for it in iters if not it.get("error") and it.get("classification") != "stuck"
    )
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
    _log(
        f"    {c.dim('View ledger:')}     cat /tmp/infinite-loop-state.json | python3 -m json.tool"
    )
    _log(f'    {c.dim("Re-run:")}          pi-loop --goal "..." --run')
    _log(f"    {c.dim('Help:')}            pi-loop --help")
    _log(f"{c.header('══════════════════════════════════════════════')}")
    _log("")


def run_loop(
    goal: str,
    context: str,
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
    http_callback_secret: str = "",
    keep_iterations: int = 0,
    archive_dir: str = "",
    archive_retention: int = 30,
    archive_max_size: int = 0,
    max_retries: int = 0,
    on_error_cmd: str | None = None,
    tag: str = "",
    prompt_suffix: str = "",
    no_tool_shortcut: bool = False,
    max_turns: int = 500,
    auto_toolsets: bool = True,
    failure_learning: bool = True,
    html_dashboard: str = "",
    webhook_port: int = 0,
    watch_dir: str = "",
    watch_poll: float = 5.0,
    cooldown: int = 0,
    goals_file: str = "",
    stop_at_goals_end: bool = False,
    output_schema: dict | None = None,
    cooldown_mode: str = "fixed",
    convergence_threshold: float = DEFAULT_CONVERGENCE_THRESHOLD,
    convergence_window: int = DEFAULT_CONVERGENCE_WINDOW,
    convergence_stop: bool = False,
    store_git_diff: bool = False,
    startup_delay: float = 0.0,
    notify_desktop: bool = False,
    notify_on_completion: bool = False,
    notify_pushbullet: str = "",
    notify_ntfy: str = "",
    notify_ntfy_server: str = "https://ntfy.sh",
    use_library: bool = False,
    pass_session_id: bool = False,
    checkpoints: bool = False,
    resume: bool = False,
    resume_session_id: str = "",
    skills: str = "",
    ignore_rules: bool = False,
    yolo: bool = False,
    ignore_user_config: bool = False,
    spawn_source: str = "",
    safe_mode: bool = False,
    accept_hooks: bool = False,
    worktree: bool = False,
    continue_session: bool = False,
    track_goals: bool = False,
    reset_goals: bool = False,
    heartbeat_timeout: int = 0,
    quiet: bool = False,
    force_reset: bool = False,
    json_logs: bool = False,
) -> None:
    global _shutdown_requested  # noqa: used in while-loop body below

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

    write_status_file(status_file, state, iteration_count, "running")
    _write_status_file(
        status_file, running=True, iteration_count=iteration_count, version=VERSION
    )

    _log_startup_banner(
        task_type="generic",
        task_type_desc="Generic loop",
        profile=profile,
        model=model,
        max_iterations=max_iterations,
        max_retries=max_retries,
        max_turns=max_turns,
        tag=tag,
        goal=goal,
        toolsets=[],
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
        quiet=quiet,
    )

    if startup_delay > 0 and iteration_count == 0:
        _log(f"[DAEMON] Startup delay: {startup_delay}s before first iteration")
        time.sleep(startup_delay)

    while True:
        if _shutdown_requested:
            _log("[STOP] Shutdown signal received. Stopping.")
            stop_reason = "stopped: signal"
            state["status"] = stop_reason
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, stop_reason)
            _write_status_file(
                status_file,
                running=False,
                iteration_count=iteration_count,
                last_error=stop_reason,
                version=VERSION,
            )
            _print_shutdown_summary(
                state, iteration_count, stop_reason, goal=goal, git=git, workers=workers
            )
            return

        # Sentinel check
        if sentinel_path:
            from .file_utils import check_sentinel

            stop_signal = check_sentinel(sentinel_path)
            if stop_signal:
                _log(f"[STOP] Sentinel detected ('{stop_signal}'). Stopping.")
                stop_reason = f"stopped: {stop_signal}"
                state["status"] = stop_reason
                state["last_updated"] = datetime.now(timezone.utc).isoformat()
                write_ledger(state)
                write_status_file(status_file, state, iteration_count, stop_reason)
                _write_status_file(
                    status_file,
                    running=False,
                    iteration_count=iteration_count,
                    last_error=stop_reason,
                    version=VERSION,
                )
                _print_shutdown_summary(
                    state,
                    iteration_count,
                    stop_reason,
                    goal=goal,
                    git=git,
                    workers=workers,
                )
                return

        if max_iterations > 0 and iteration_count >= max_iterations:
            _log(f"[STOP] Reached max_iterations={max_iterations}. Stopping.")
            state["status"] = f"stopped: max_iterations ({max_iterations})"
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(
                status_file, state, iteration_count, "stopped: max_iterations"
            )
            _write_status_file(
                status_file,
                running=False,
                iteration_count=iteration_count,
                version=VERSION,
            )
            _print_shutdown_summary(
                state,
                iteration_count,
                "stopped: max_iterations",
                goal=goal,
                git=git,
                workers=workers,
            )
            return

        if max_idle_iterations > 0 and consecutive_idle >= max_idle_iterations:
            _log(
                f"[STOP] Idle limit reached ({consecutive_idle} iterations). Stopping."
            )
            stop_reason = (
                f"stopped: idle ({consecutive_idle} iterations without changes)"
            )
            state["status"] = stop_reason
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, "stopped: idle")
            _write_status_file(
                status_file,
                running=False,
                iteration_count=iteration_count,
                version=VERSION,
            )
            _print_shutdown_summary(
                state, iteration_count, stop_reason, goal=goal, git=git, workers=workers
            )
            return

        iteration_count += 1
        iteration_start_time = datetime.now(timezone.utc).isoformat()

        if quiet:
            _log(
                f"[ITER #{iteration_count}] {goal[:80]}{'...' if len(goal) > 80 else ''}"
            )
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
            goal_text, exhausted = _cycle_goal_simple(
                goals_list, goals_index - 1, stop_at_goals_end
            )
            if exhausted:
                state["status"] = "stopped: goals-exhausted"
                state["last_updated"] = datetime.now(timezone.utc).isoformat()
                write_ledger(state)
                write_status_file(
                    status_file, state, iteration_count, "stopped: goals-exhausted"
                )
                _print_shutdown_summary(
                    state,
                    iteration_count,
                    "stopped: goals-exhausted",
                    goal=goal,
                    git=git,
                    workers=workers,
                )
                return
        else:
            goal_text = goal

        # Build context from progressive summaries
        progressive_context = _build_progressive_context(context, existing_summaries)

        git_before = (
            _capture_git_state(workdir, store_diff=store_git_diff) if git else {}
        )
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

        git_after = (
            _capture_git_state(workdir, store_diff=store_git_diff) if git else {}
        )
        git_commit_hash = None
        if git_commit and not combined_error:
            git_commit_hash = _git_auto_commit(
                workdir, iteration_count, combined_summary
            )

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
        write_status_file(status_file, state, iteration_count, "running")
        _write_status_file(
            status_file,
            running=True,
            iteration_count=iteration_count,
            last_error=combined_error,
            version=VERSION,
        )

        status_icon = "✓" if combined_error is None else "✗"
        _log(
            f"{status_icon} Iteration {iteration_count} ({total_duration}s): {combined_summary[:100]}"
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
                        "pi-loop",
                        combined_summary[:100] or f"Iteration {iteration_count}",
                    ],
                    timeout=5,
                )
            except Exception:
                pass

        if html_dashboard:
            try:
                html = _build_dashboard_html(state)
                with open(html_dashboard, "w") as f:
                    f.write(html)
            except Exception:
                pass

        if http_callback:
            try:
                import urllib.request

                data = json.dumps(record).encode()
                req = urllib.request.Request(
                    http_callback,
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                if http_callback_secret:
                    req.add_header("Authorization", http_callback_secret)
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass

        # On-error command
        if combined_error and on_error_cmd:
            try:
                subprocess.run(on_error_cmd, shell=True, timeout=30)
            except Exception:
                pass

        # Cooldown
        _handle_cooldown(cooldown, cooldown_mode, None, "generic")

        # Error recovery adaptation
        if primary_error_type:
            (
                session_timeout,
                cooldown,
                cooldown_mode,
                use_library,
                workers,
                adapt_actions,
            ) = _adapt_to_error(
                error_type=primary_error_type,
                mitigations=state.get("mitigations", {}),
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
                state["status"] = stop_reason
                state["last_updated"] = datetime.now(timezone.utc).isoformat()
                write_ledger(state)
                write_status_file(status_file, state, iteration_count, stop_reason)
                _write_status_file(
                    status_file,
                    running=False,
                    iteration_count=iteration_count,
                    last_error=stop_reason,
                    version=VERSION,
                )
                _print_shutdown_summary(
                    state,
                    iteration_count,
                    stop_reason,
                    goal=goal,
                    git=git,
                    workers=workers,
                )
                return

        # Keep iteration cap
        if (
            keep_iterations > 0
            and len(state.get("iterations", [])) > keep_iterations * 2
        ):
            state["iterations"] = state["iterations"][-keep_iterations:]
            state["total_iterations"] = iteration_count
            _recalc_stats(state)
            write_ledger(state)

        # Evolve: check pi output for NEXT_GOAL: marker
        if evolve and not combined_error and len(goals_list) <= 1:
            _evolve_goal(result.get("output", ""), state, iteration_count)


def _evolve_goal(output: str, state: dict, iteration: int) -> None:
    """Check pi output for NEXT_GOAL: header, update state if found."""
    for line in output.split("\n"):
        if line.strip().upper().startswith("NEXT_GOAL:"):
            next_goal = line.split(":", 1)[1].strip()
            if next_goal:
                _log(f"[EVOLVE] Iteration {iteration} proposed next goal: {next_goal[:80]}")
                state["evolved_goal"] = next_goal


def _build_dashboard_html(state: dict) -> str:
    """Build a minimal HTML dashboard for the loop state."""
    iters = state.get("iterations", [])
    rows = ""
    for it in reversed(iters[-50:]):
        n = it.get("n", "?")
        status = "❌" if it.get("error") else "✅"
        dur = it.get("duration_seconds", 0)
        summary = (it.get("summary") or "")[:100]
        rows += (
            f"<tr><td>{n}</td><td>{status}</td><td>{dur}s</td><td>{summary}</td></tr>\n"
        )

    return f"""<!DOCTYPE html>
<html><head><title>pi-loop Dashboard</title>
<meta charset="utf-8"><meta http-equiv="refresh" content="5">
<style>
body {{ font-family: sans-serif; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px 12px; text-align: left; }}
th {{ background: #f0f0f0; }}
tr:nth-child(even) {{ background: #fafafa; }}
</style></head><body>
<h1>pi-loop Dashboard</h1>
<p>Status: <strong>{state.get("status", "unknown")}</strong>
| Iterations: {len(iters)}
| Total: {state.get("stats", {}).get("total_duration_seconds", 0):.0f}s</p>
<table><thead><tr><th>#</th><th>Status</th><th>Duration</th><th>Summary</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>"""


def _cycle_goal_simple(
    goals_list: list, index: int, stop_at_end: bool
) -> tuple[str, bool]:
    """Cycle goals helper."""
    if len(goals_list) <= 1:
        return ("", False)
    idx = index % len(goals_list)
    spec = goals_list[idx]
    goal_text = spec[0] if isinstance(spec, tuple) else str(spec)
    if stop_at_end and index >= len(goals_list):
        return ("", True)
    return (goal_text, False)
