"""Iteration execution, merging, backoff, convergence, compacting, record building, notifications, and callbacks."""

import concurrent.futures
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone

from .config import DEFAULT_CONVERGENCE_WINDOW, DEFAULT_CONVERGENCE_THRESHOLD
from .file_utils import _log, write_ledger, write_status_file
from .error_utils import _classify_progress, classify_error
from .error_recovery import _pick_primary_error
from .similarity import check_convergence
from .system_utils import get_system_usage, get_system_usage_diff
from .goal_utils import GoalSpec
from .hermes_utils import _build_delegation_prompt, spawn_delegation_session
from .library_worker import _run_library_workers_parallel
from .git_utils import _capture_git_state, _git_auto_commit
from .stats import _recalc_stats
from .notifications import _send_per_iteration_notifications
from .archiving import (
    _archive_iterations,
    _cleanup_old_archives,
    _enforce_archive_max_size,
)

from .signal_handlers import _shutdown_requested


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
    quiet: bool = False,
) -> tuple[list[dict], GoalSpec, bool]:
    """Spawn one or more Hermes sessions for the current iteration."""
    all_results: list[dict] = []

    # Start a background thread for iteration heartbeat updates
    _iter_heartbeat_stop = threading.Event()

    def _iteration_heartbeat(interval: int = 120):
        """Log periodic heartbeat while iteration is running."""
        elapsed = 0
        while not _iter_heartbeat_stop.is_set():
            if _iter_heartbeat_stop.wait(timeout=interval):
                break
            elapsed += interval
            _log(
                f"[BEAT] Iteration #{iteration_count} still running ({elapsed}s elapsed)..."
            )

    spawn_goal = spawn_goal if len(goals_list) > 1 else goals_list[0]

    # Start iteration heartbeat thread (logs every 2 min during long-running spawns)
    heartbeat_thread = threading.Thread(
        target=_iteration_heartbeat, args=(120,), daemon=True
    )
    heartbeat_thread.start()

    if workers > 1:
        if use_library:
            try:
                tasks = []
                for w_id in range(workers):
                    worker_goal_spec = spawn_goal
                    if len(goals_list) > 1:
                        idx = (goals_index + w_id) % len(goals_list)
                        worker_goal_spec = goals_list[idx]
                        _log(f"[WORKER #{w_id}] Goal: {worker_goal_spec.goal[:100]}...")

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

                for r in all_results:
                    r.setdefault("worker_id", 0)

            except Exception as e:
                _log(
                    f"[LIBRARY] Library mode failed in multi-worker: {e}, falling back to subprocess"
                )
                use_library = False

        if not use_library:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for w_id in range(workers):
                    worker_goal_spec = spawn_goal
                    if len(goals_list) > 1:
                        idx = (goals_index + w_id) % len(goals_list)
                        worker_goal_spec = goals_list[idx]
                        _log(f"[WORKER #{w_id}] Goal: {worker_goal_spec.goal[:100]}...")

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
                        heartbeat_timeout=heartbeat_timeout,
                        iteration_count=iteration_count,
                    )
                    futures[fut] = w_id

                for fut in concurrent.futures.as_completed(futures):
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
                heartbeat_timeout=heartbeat_timeout,
                iteration_count=iteration_count,
                worker_id=0,
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
    _iter_heartbeat_stop.set()  # stop the heartbeat thread
    heartbeat_thread.join(timeout=2)
    return all_results, spawn_goal, use_library


def _merge_worker_results(
    all_results: list[dict],
    max_output_chars: int,
    consecutive_errors: int,
    state: dict,
) -> dict:
    """Merge results from one or more workers into a single summary.

    In multi-worker mode, a single worker's non-fatal error (e.g. "exit code 1"
    with useful output) should NOT mark the entire iteration as failed.  Only
    treat the iteration as errored when all workers failed, or when a serious
    error type (timeout/network/schema) dominates and the majority failed.
    """
    num_workers = len(all_results)
    durations = [r.get("duration_seconds", 0) for r in all_results]
    total_duration = max(durations) if len(durations) > 1 else durations[0]

    # --- Soft-error detection: distinguish subprocess exit-code noise from real failures ---
    # A worker's error is "soft" if it looks like an exit-code artifact rather than
    # a genuine hermes failure.  Specifically: error says "exit code N" but the
    # worker produced meaningful output (non-empty summary, non-trivial output).
    def _is_soft_error(r: dict) -> bool:
        err = r.get("error", "")
        if not err:
            return False
        # "exit code N" without any other error content is a soft error
        err_lower = err.lower().strip()
        if err_lower.startswith("exit code") or err_lower.startswith("hermes exit"):
            # Check if the worker actually produced usable output
            summary = r.get("summary", "").strip()
            # A summary that doesn't start with FAILED means work was done
            if summary and not summary.startswith("FAILED"):
                return True
            output_len = len(r.get("output", "") or "")
            if output_len > 200:
                return True
            # A non-trivial next_goal with context suggests partial work done
            next_goal = r.get("next_goal", "") or ""
            if len(next_goal) > 50 and not next_goal.startswith("FAILED"):
                return True
        return False

    # Separate hard errors (genuine failures) from soft errors (exit-code noise)
    hard_errors = []
    soft_errors = []
    for r in all_results:
        if r.get("error"):
            if _is_soft_error(r):
                soft_errors.append(r.get("error"))
            else:
                hard_errors.append(r.get("error"))

    # Determine the final combined_error based on worker count and error severity
    combined_error = None
    if num_workers <= 1:
        # Single-worker: treat as error only if there are HARD errors.
        # Soft errors (exit-code noise with useful output) should not mark
        # the iteration as failed.
        if hard_errors:
            combined_error = "; ".join(hard_errors)
        elif soft_errors:
            # Single soft error — not a real failure; log it for awareness
            _log(f"[SOFT-ERROR] Single worker had soft error: {soft_errors[0][:100]}")
    else:
        # Multi-worker: only treat as error if ALL workers have hard errors,
        # OR if the majority failed with a serious error type
        num_hard = len(hard_errors)
        num_with_any_error = num_hard + len(soft_errors)

        if num_hard == num_workers:
            # All workers have hard errors — genuine failure
            combined_error = "; ".join(hard_errors)
        elif num_with_any_error == num_workers and num_hard > 0:
            # All workers have some error, but some are soft — check error types
            serious_types = {"timeout", "network", "schema"}
            serious_count = sum(
                1 for r in all_results if r.get("error_type") in serious_types
            )
            if serious_count >= num_workers / 2:
                combined_error = "; ".join(hard_errors)
        # else: some workers succeeded or only had soft errors — not a failure

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
            primary_error_type = "unknown"

        state.setdefault("error_type_counts", {})
        state["error_type_counts"][primary_error_type] = (
            state["error_type_counts"].get(primary_error_type, 0) + 1
        )

        _log(
            f"[ERROR-TYPE] {primary_error_type} "
            f"(total: {state['error_type_counts'][primary_error_type]})"
        )
    else:
        consecutive_successes = state.get("consecutive_successes", 0) + 1

    consecutive_errors = 0 if not combined_error else consecutive_errors + 1

    next_goal = None
    next_context = ""

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
            parts = [f"[Worker #{wid}]: {c}" for wid, c in worker_contexts]
            next_context = "\n\n".join(parts)

    summaries = [
        str(r.get("summary", f"Worker #{r.get('worker_id', 0)} completed"))
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
    """Apply exponential backoff delay when errors occur."""
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
    """Check if recent iteration summaries have converged."""
    if convergence_stop and iteration_count >= convergence_window:
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
    """Compact the rolling window of summaries."""
    is_compacted = False
    if compact_every > 0 and iteration_count % compact_every == 0:
        is_compacted = True
        keep_full = max(compact_every, 10)
        condensed = 0
        new_summaries = []
        for i, s in enumerate(existing_summaries):
            if i >= len(existing_summaries) - keep_full:
                new_summaries.append(s)
            else:
                short = s[:80].replace("\n", " ")
                condensed += 1
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
    """Build the per-iteration record dict with all fields."""
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
        "toolsets": toolsets[:],
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

    if all_results and not workers > 1:
        sid = all_results[0].get("spawned_session_id", "")
        if sid:
            record["spawned_session_id"] = sid
    elif workers > 1:
        for wr in record.get("worker_results", []):
            w_id = wr.get("worker", 0)
            for r in all_results:
                if r.get("worker_id") == w_id and r.get("spawned_session_id"):
                    wr["spawned_session_id"] = r["spawned_session_id"]
                    break

    if resume and pass_session_id and all_results:
        if not workers > 1:
            sid = all_results[0].get("spawned_session_id", "")
            if sid:
                state["resume_session_id"] = sid
        state.setdefault("session_id_history", [])
        for r in all_results:
            sid = r.get("spawned_session_id", "")
            if sid and sid not in state["session_id_history"][-100:]:
                state["session_id_history"].append(sid)
        state["session_id_history"] = state["session_id_history"][-100:]

    sys_after = get_system_usage()
    sys_diff = get_system_usage_diff(sys_before, sys_after)
    if sys_diff:
        record["system"] = sys_diff

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
    """Dispatch desktop + pushbullet + ntfy notifications for each iteration."""
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
    """Dispatch HTTP callback, notify-cmd, and on-error-cmd for each iteration."""
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
