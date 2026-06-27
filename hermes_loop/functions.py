"""Goal file loading, startup banner, goal cycling, progressive context, and cooldown handling."""

import os
import time

from .config import SENTINEL_PATH_DEFAULT, LEDGER_PATH, LAUNCH_LOOP_VERSION
from .file_utils import _log
from .cooldown import calc_adaptive_cooldown

# Note: max_output_chars is referenced in _log_startup_banner — it's a global
# in the original but passed via closures. We'll reference it as a parameter here.
_max_output_chars_global = 2000  # default, overridden at runtime


def set_max_output_chars(val: int) -> None:
    global _max_output_chars_global
    _max_output_chars_global = val


def get_max_output_chars() -> int:
    return _max_output_chars_global


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
    max_iterations: int,
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
    quiet: bool = False,
) -> None:
    """Log a readable, categorized startup banner showing what's actually active.

    When quiet=True, only a compact one-line status is shown.
    """
    _log(f"[DAEMON] PID={os.getpid()}")
    _log(f"[DAEMON] ledger={LEDGER_PATH}")
    _log(f"[DAEMON] sentinel={SENTINEL_PATH_DEFAULT}")
    _log(f"[DAEMON] workdir={os.getcwd()}")

    if quiet:
        # Compact one-line status for quiet mode
        parts = []
        if max_iterations > 0:
            parts.append(f"max={max_iterations}")
        if workers > 1:
            parts.append(f"workers={workers}")
        if evolve:
            parts.append("evolve")
        if git:
            parts.append("git")
        _log(
            f"[DAEMON] Running: goal={goal[:80]}{'...' if len(goal) > 80 else ''} | "
            f"{' | '.join(parts) if parts else 'unlimited'} | "
            f"tools={len(toolsets)} | type={task_type}"
        )
        _log("")
        return
    _log(f"[DAEMON] ═════ v{LAUNCH_LOOP_VERSION} Configuration Overview ═════")
    # ── Category: Iteration ──────────────────────────────────────────────────
    parts = []
    if max_iterations > 0:
        parts.append(f"max={max_iterations}")
    if evolve:
        parts.append("evolve")
    if track_goals:
        parts.append("track-goals")
    if convergence_stop:
        parts.append(f"converge({convergence_window}×{convergence_threshold})")
    _log(
        f"[DAEMON]   Iteration: {' | '.join(parts) if parts else '(unlimited, no auto-stop)'}"
    )

    # ── Category: Parallel ───────────────────────────────────────────────────
    parts = [f"workers={workers}", f"timeout={session_timeout}s"]
    if max_retries > 0:
        parts.append(f"retries={max_retries}")
    cooldown_str = "adaptive" if cooldown_mode == "adaptive" else f"{cooldown}s"
    parts.append(f"cooldown={cooldown_str}")
    if heartbeat_timeout > 0:
        parts.append(f"heartbeat={heartbeat_timeout}s")
    _log(f"[DAEMON]   Parallel:   {' | '.join(parts)}")

    # ── Category: Notifications ──────────────────────────────────────────────
    parts = []
    if notify_cmd:
        parts.append("shell-cmd")
    if pass_session_id:
        parts.append("session-id")
    if checkpoints:
        parts.append("checkpoints")
    _log(
        f"[DAEMON]   Sessions:   {' | '.join(parts) if parts else '(direct subprocess)'}"
    )

    # ── Category: Spawn ──────────────────────────────────────────────────────
    parts = []
    if profile:
        parts.append(f"profile={profile}")
    if model:
        parts.append(f"model={model}")
    _log(
        f"[DAEMON]   Spawn:      profile={profile or '(default)'}, model={model or '(default)'}"
    )

    # ── Category: Git ────────────────────────────────────────────────────────
    if git:
        parts = ["capture"]
        if git_commit:
            parts.append("auto-commit")
        if store_git_diff:
            parts.append("store-diff")
        _log(f"[DAEMON]   Git:        {' | '.join(parts)}")
    elif git_commit or store_git_diff:
        _log("[DAEMON]   Git:        (flags set but --git not enabled — ignored)")

    # ── Category: Output ─────────────────────────────────────────────────────
    _log(
        f"[DAEMON]   Output:     max-chars={get_max_output_chars()}, schema={'yes' if output_schema else 'no'}"
    )
    _log("[DAEMON] ══════════════════════════════════════════════════")
    _log(f"[DAEMON] Goal: {goal}")
    _log(f"[DAEMON] Toolsets: {toolsets}")
    _log(f"[DAEMON] Task type: {task_type} ({task_type_desc})")
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
    from .signal_handlers import _shutdown_requested

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
