"""Main loop logic — run_loop function."""

import atexit
import os
import sys
import time
from datetime import datetime, timezone

from .config import DEFAULT_CONVERGENCE_THRESHOLD, DEFAULT_CONVERGENCE_WINDOW
from .file_utils import _log, write_ledger, write_status_file
from .signal_handlers import (
    _shutdown_requested,
    _check_auto_reload,
)
from .goal_utils import GoalSpec, _is_goal_completed, _mark_goal_completed
from .error_recovery import (
    _adapt_to_error,
)
from .error_utils import _suggest_actionable_fix
from .tracker import ETATracker
from .file_watcher import FileWatcherTrigger
from .webhook import _start_webhook_server
from .dashboard import _write_status_html, _broadcast_to_sse_clients
from .worker_manager import HermesWorkerManager
from .hermes_utils import detect_task_type
from .git_utils import _capture_git_state, _git_auto_commit
from .system_utils import get_system_usage, get_system_usage_diff
from .color_utils import colorizer
from .functions import (
    _load_goals_file,
    _log_startup_banner,
    _cycle_goal,
    _build_progressive_context,
    _handle_cooldown,
)
from .iteration import (
    _execute_iteration,
    _merge_worker_results,
    _handle_backoff,
    _detect_convergence,
    _compact_summaries,
    _build_iteration_record,
    _handle_notifications,
    _handle_callbacks,
    _sleep_with_shutdown_check,
)
from .worktree_merger import _merge_worktree_branches
from .stats import _recalc_stats
from .color_utils import colorizer as _shutdown_colorizer


def _print_shutdown_summary(
    state: dict,
    iteration_count: int,
    stop_reason: str,
    goal: str = "",
    git: bool = False,
    workers: int = 1,
    gs: dict | None = None,
) -> None:
    """Print a comprehensive shutdown summary banner.

    Shows total iterations, duration, success/fail breakdown, git changes,
    error counts, and actionable next-steps for the user. Called from every
    stop path in run_loop() so the user always gets a clear picture of what
    happened and what to do next.
    """
    from .file_utils import _log as _slog

    iters = state.get("iterations", [])
    total = iteration_count
    total_dur = state.get("stats", {}).get("total_duration_seconds", 0)
    success_count = sum(
        1 for it in iters if not it.get("error") and it.get("classification") != "stuck"
    )
    error_count = sum(1 for it in iters if it.get("error"))
    stuck_count = sum(
        1 for it in iters if not it.get("error") and it.get("classification") == "stuck"
    )
    error_type_counts = state.get("error_type_counts", {})
    err_types = []
    for err_type in ("timeout", "network", "schema", "unknown", "heartbeat"):
        cnt = error_type_counts.get(err_type, 0)
        if cnt:
            err_types.append(f"{err_type}={cnt}")

    c = _shutdown_colorizer
    _slog("")
    _slog(f"{c.header('═══════════════ SHUTDOWN SUMMARY ═══════════════')}")
    _slog(f"  {c.value('Status:')}       {c.flag(stop_reason)}")
    _slog(f"  {c.value('Iterations:')}   {c.flag(str(total))}")
    if total_dur > 0:
        dur_str = f"{total_dur:.0f}s"
        if total_dur >= 60:
            dur_str += f" ({total_dur/60:.1f}m)"
        _slog(f"  {c.value('Duration:')}    {c.dim(dur_str)}")
    _slog(f"  {c.value('Success:')}     {c.tag_ok()}{success_count}")
    if error_count:
        _slog(f"  {c.value('Errors:')}      {c.tag_fail()}{error_count}")
    if stuck_count:
        _slog(f"  {c.value('Stuck:')}       {c.dim(str(stuck_count))}")
    if err_types:
        _slog(f"  {c.value('Breakdown:')}   {c.dim(', '.join(err_types))}")
    if goal:
        _slog(f"  {c.value('Final goal:')}  {c.dim(goal[:80])}")

    # Next-steps
    _slog("")
    _slog(f"  {c.group_title('Next steps:')}")
    _slog(f"    {c.dim('View ledger:')}     bash scripts/inspect-ledger.sh")
    _slog(f"    {c.dim('Summary:')}         bash scripts/inspect-ledger.sh --summary")
    _slog(
        f"    {c.dim('Errors:')}          bash scripts/inspect-ledger.sh --errors-only"
    )
    _slog(f"    {c.dim('Re-run:')}          bash run.sh")
    _slog(f"    {c.dim('Restart with:')}  python3 -m hermes_loop --goal \"...\" --run")
    _slog(f"    {c.dim('Help:')}           python3 -m hermes_loop --help")
    _slog(f"    {c.dim('Examples:')}       python3 -m hermes_loop --examples")
    _slog(f"{c.header('══════════════════════════════════════════════')}")
    _slog("")


# Import archiving (delayed to avoid circular imports in `loop` module)
from .archiving import (  # noqa: E402
    _archive_iterations,
    _cleanup_old_archives,
    _enforce_archive_max_size,
)


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
    html_dashboard: str = "",
    webhook_port: int = 0,
    watch_dir: str = "",
    watch_poll: float = 5.0,
    worker_url: str = "",
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
    global _shutdown_state_ref, _hermes_worker_ref
    _shutdown_state_ref = state
    _hermes_worker_ref = worker_manager

    iteration_count = state["total_iterations"]
    existing_summaries = [it.get("summary", "") for it in state.get("iterations", [])]
    consecutive_errors = state.get("stats", {}).get("consecutive_errors", 0)
    consecutive_idle = 0

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

    goals_tuples = _load_goals_file(goals_file, goal)
    goals_list: list[GoalSpec] = [GoalSpec(g) for g, p, m, v in goals_tuples]
    goals_index = 0

    write_status_file(status_file, state, iteration_count, "running")

    _log_startup_banner(
        task_type=task_type,
        task_type_desc=task_type_desc,
        profile=profile,
        model=model,
        max_iterations=max_iterations,
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
        quiet=quiet,
    )

    eta_tracker = ETATracker()
    state["eta"] = eta_tracker.to_dict()

    # Start webhook server if port configured
    if webhook_port > 0:

        def _webhook_trigger(goal_override=None, context_override=None):
            return {"triggered": True, "iteration": "on_next_loop"}

        _start_webhook_server(webhook_port, _webhook_trigger, sentinel_path)
    state["webhook_port"] = webhook_port

    file_watcher = None
    if watch_dir:
        file_watcher = FileWatcherTrigger(watch_dir, watch_poll)
        _log(
            f"[WATCH] Watching {watch_dir} for file changes (poll every {watch_poll}s)"
        )
        state["watch_dir"] = watch_dir

    if html_dashboard:
        state["html_dashboard"] = html_dashboard
        _write_status_html(html_dashboard, state)
        _log(f"[HTML-DASH] Status dashboard at {html_dashboard}")

    if worker_manager and worker_manager.is_running:
        atexit.register(worker_manager.stop)

    if startup_delay > 0 and iteration_count == 0:
        _log(f"[DAEMON] Startup delay: {startup_delay}s before first iteration")
        _sleep_with_shutdown_check(startup_delay)

    while True:
        if _shutdown_requested:
            _log("[STOP] Shutdown signal received. Stopping.")
            stop_reason = "stopped: signal"
            state["status"] = stop_reason
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, stop_reason)
            _print_shutdown_summary(
                state, iteration_count, stop_reason, goal=goal, git=git, workers=workers
            )
            return

        if file_watcher and file_watcher.check_change():
            changed = file_watcher.format_changed()
            _log(f"[WATCH] File change detected: {changed[:120]}")

        stop_signal = None
        if sentinel_path:
            # Import check_sentinel locally to avoid circular issues
            from .file_utils import check_sentinel, check_sentinel_no_remove

            stop_signal = check_sentinel(sentinel_path)
        if stop_signal:
            if stop_signal.lower() == "pause":
                _log("[PAUSE] Sentinel contains 'pause'. Entering paused state.")
                state["status"] = "paused"
                write_ledger(state)
                write_status_file(status_file, state, iteration_count, "paused")
                _log("[PAUSE] Waiting for 'resume' or 'stop' sentinel...")
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
                continue
            _log(f"[STOP] Sentinel detected ('{stop_signal}'). Stopping.")
            stop_reason = f"stopped: {stop_signal}"
            state["status"] = stop_reason
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, stop_reason)
            _print_shutdown_summary(
                state, iteration_count, stop_reason, goal=goal, git=git, workers=workers
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
                f"[STOP] No changes detected for {consecutive_idle} iterations (max_idle={max_idle_iterations}). Stopping."
            )
            stop_reason = (
                f"stopped: idle ({consecutive_idle} iterations without changes)"
            )
            state["status"] = stop_reason
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, "stopped: idle")
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
                filled = int(pct / 100.0 * bar_width)
                bar = "█" * filled + "░" * (bar_width - filled)
                _log(f"    [{bar}] {iteration_count}/{max_iterations} — {pct:.0f}%")
            _log(f"    Goal: {goal[:100]}{'...' if len(goal) > 100 else ''}")
            parts = [f"workers={workers}"]
            if max_turns:
                parts.append(f"turns={max_turns}")
            _log(f"    {' | '.join(parts)}")
            if len(goals_list) > 1:
                _log(f"    Goals-file: {len(goals_list)} goals loaded")
            _log(f"{'=' * 60}")

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
                _print_shutdown_summary(
                    state,
                    iteration_count,
                    "stopped: goals-exhausted",
                    goal=goal,
                    git=git,
                    workers=workers,
                )
                return

            if track_goals and _is_goal_completed(state, goal_text):
                _log(
                    f"[TRACK-GOALS] Skipping already-completed goal: {goal_text[:120]}..."
                )
                continue

        progressive_context = _build_progressive_context(context, existing_summaries)

        spawn_goal = current_goal_spec if len(goals_list) > 1 else goals_list[0]

        git_before = (
            _capture_git_state(workdir, store_diff=store_git_diff) if git else {}
        )
        sys_before = get_system_usage()

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
            quiet=quiet,
        )

        state.pop("pending_iteration", None)

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

        # Merge worker worktree branches back to main (best-effort)
        worktree_merge_result = {}
        if worktree:
            # Collect worker IDs from results for per-worker tracking
            worker_ids = sorted(
                set(
                    r.get("worker_id", -1)
                    for r in all_results
                    if r.get("worker_id") is not None
                )
            )
            if not worker_ids:
                worker_ids = list(range(workers))
            worktree_merge_result = _merge_worktree_branches(
                workdir=workdir,
                iteration_count=iteration_count,
                worker_count=workers,
                worker_ids=worker_ids,
            )

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
                # Also push committed changes to remote (best-effort)
                try:
                    import subprocess as _sp

                    _sp.run(
                        ["git", "push", "origin", "HEAD"],
                        capture_output=True,
                        cwd=workdir or os.getcwd(),
                        timeout=30,
                    )
                except Exception:
                    pass

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
            _print_shutdown_summary(
                state,
                iteration_count,
                "stopped: convergence",
                goal=goal,
                git=git,
                workers=workers,
            )
            return

        existing_summaries, is_compacted = _compact_summaries(
            existing_summaries=existing_summaries,
            compact_every=compact_every,
            iteration_count=iteration_count,
            combined_summary=combined_summary,
        )

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

        # Store worktree merge results in the record
        if worktree and worktree_merge_result:
            record["worktree_merge"] = {
                "merged": worktree_merge_result.get("merged", 0),
                "failed": worktree_merge_result.get("failed", 0),
                "skipped": worktree_merge_result.get("skipped", 0),
                "per_worker": worktree_merge_result.get("per_worker", {}),
                "conflicts": (worktree_merge_result.get("total_conflicts", 0)),
                "source_branches": worktree_merge_result.get("source_branches", []),
            }

        state["iterations"].append(record)
        state["total_iterations"] = iteration_count
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        state["status"] = "running"

        if evolve and next_goal and len(goals_list) <= 1:
            state["current_goal"] = goal
            goal = next_goal
            state["evolved_goal"] = goal
            _log(f"[EVOLVE] Next goal: {goal[:120]}...")

        if next_context:
            progressive_context = f"[Context from previous iteration]: {next_context}"

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
        if track_goals and len(goals_list) > 1:
            _mark_goal_completed(state, goal_text, iteration_count)
        write_ledger(state)
        write_status_file(status_file, state, iteration_count, "running")

        status_icon = "✓" if combined_error is None else "✗"
        classification = record.get("classification", "unknown")
        done_tag = (
            colorizer.tag_ok() if combined_error is None else colorizer.tag_fail()
        )
        _log(
            f"{done_tag} {status_icon} Iteration {iteration_count}"
            f" ({total_duration}s, {classification})"
            f": {combined_summary[:100]}"
        )

        # ── Rich post-iteration summary banner ────────────────────────────────
        status_icon_display = "✔" if combined_error is None else "✘"
        summary_parts: list[str] = [f"Iteration {iteration_count}"]
        summary_parts.append(f"({total_duration}s)")

        if combined_error:
            summary_parts.append(f"error={combined_error[:60]}")
        else:
            summary_parts.append(classification)

        # Git changes
        if git:
            before_ds = git_before.get("diff_stat", "")
            after_ds = git_after.get("diff_stat", "")
            if before_ds != after_ds:
                summary_parts.append(f"git: {before_ds} → {after_ds}")
            elif git_commit_hash:
                summary_parts.append(f"git: committed {git_commit_hash[:8]}")

        # System resource usage
        sys_after = get_system_usage()
        sys_diff = {}
        if sys_before and sys_after:
            sys_diff = get_system_usage_diff(sys_before, sys_after)
        if sys_diff:
            cpu = sys_diff.get("cpu_seconds_used", 0)
            mem = sys_diff.get("memory_rss_mb", 0)
            mem_peak = sys_diff.get("memory_peak_mb", 0)
            if cpu > 0:
                summary_parts.append(f"cpu={cpu:.1f}s")
            if mem > 0:
                summary_parts.append(f"mem={mem:.0f}MB")
            if mem_peak > 0 and mem_peak > mem:
                summary_parts.append(f"peak={mem_peak:.0f}MB")

        # Worker breakdown
        if workers > 1 and all_results:
            ok_count = sum(1 for r in all_results if not r.get("error"))
            summary_parts.append(f"workers={ok_count}/{len(all_results)}")

        # Worktree merge results
        if worktree and worktree_merge_result:
            wt_merged = worktree_merge_result.get("merged", 0)
            wt_failed = worktree_merge_result.get("failed", 0)
            wt_conflicts = worktree_merge_result.get("total_conflicts", 0)
            if wt_merged > 0 or wt_failed > 0 or wt_conflicts > 0:
                wt_parts = []
                if wt_merged > 0:
                    wt_parts.append(f"{wt_merged} merged")
                if wt_failed > 0:
                    wt_parts.append(f"{wt_failed} failed")
                if wt_conflicts > 0:
                    wt_parts.append(f"{wt_conflicts} conflicts")
                summary_parts.append(f"wtree={'/'.join(wt_parts)}")

        # Task type
        if task_type:
            summary_parts.insert(1, f"{task_type}")

        # ETA
        eta_str = ""
        if max_iterations > 0 and iteration_count > 0:
            eta_rem = eta_tracker.estimate_remaining(
                task_type, iteration_count, max_iterations
            )
            eta_str = eta_tracker.format_eta(eta_rem)
            pct = min(100.0 * iteration_count / max_iterations, 100.0)
            bar_w = 15
            filled = int(pct / 100.0 * bar_w)
            bar = "█" * filled + "░" * (bar_w - filled)
            summary_parts.append(
                f"[{bar}] {iteration_count}/{max_iterations} {pct:.0f}%"
            )
            if eta_str and eta_str != "N/A":
                summary_parts.append(f"ETA={eta_str}")

        summary_str = " | ".join(summary_parts)
        if combined_error:
            _log(f"{colorizer.tag_fail()} {summary_str}")
        else:
            _log(f"{colorizer.tag_summary()} {status_icon_display}  {summary_str}")

        # Show actionable suggestion for blocked/error iterations
        suggestion = _suggest_actionable_fix(
            error_type=primary_error_type,
            classification=classification,
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
                _log(f"{colorizer.tag_suggest()} {line}")

        _handle_notifications(
            notify_desktop=notify_desktop,
            notify_pushbullet=notify_pushbullet,
            notify_ntfy=notify_ntfy,
            combined_summary=combined_summary,
            total_duration=total_duration,
            combined_error=combined_error,
            notify_ntfy_server=notify_ntfy_server,
        )

        if html_dashboard:
            _write_status_html(html_dashboard, state)

        _handle_callbacks(
            http_callback=http_callback,
            record=record,
            notify_cmd=notify_cmd,
            on_error_cmd=on_error_cmd,
            combined_error=combined_error,
            state=state,
        )

        _broadcast_to_sse_clients(state)

        _check_auto_reload(workdir, state, worker_manager, status_file, iteration_count)

        if (
            keep_iterations > 0
            and len(state.get("iterations", [])) > keep_iterations * 2
        ):
            old_count = len(state["iterations"])
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

        _handle_cooldown(
            cooldown=cooldown,
            cooldown_mode=cooldown_mode,
            eta_tracker=eta_tracker,
            task_type=task_type,
        )

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
            _print_shutdown_summary(
                state,
                iteration_count,
                "stopped: error-backoff",
                goal=goal,
                git=git,
                workers=workers,
            )
            return

        if state["mitigations"].get("mitigation_level", 0) >= 3:
            _log("[AUTO-RECOVERY] Persistent failure detected — stopping daemon")
            stop_reason = (
                f"stopped: {primary_error_type}-failure-"
                f"{state.get('error_type_counts', {}).get(primary_error_type, 0)}"
            )
            state["status"] = stop_reason
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            write_ledger(state)
            write_status_file(status_file, state, iteration_count, stop_reason)
            _print_shutdown_summary(
                state, iteration_count, stop_reason, goal=goal, git=git, workers=workers
            )
            return
