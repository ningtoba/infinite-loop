#!/usr/bin/env python3
"""
session-self-loop.py — In-session infinite loop (v2.10.0)

v2.10.0:
  - Version bump to align with infinite-loop v14.0.0 release
  - Dashboard v3 SSE, Session Self-Healing Heartbeat
  - Hermes Version Check parity

v2.8.0:
  - Version bump to align with infinite-loop v11.14.0 release
  - safe-mode, accept-hooks, worktree, continue flags

v2.5.0:
  - Version bump to align with infinite-loop v11.13.0 release

v2.4.0:
  - Version bump to align with infinite-loop v11.12.0 release

v2.3.0:
  - Version bump to align with infinite-loop v11.11.0 release

HOW IT WORKS:
  Unlike launch-loop.py (which spawns child Hermes sessions), this script
  is meant to be CALLED from a Hermes session via terminal(). The session
  runs the loop in the foreground, using delegate_task() for complex work,
  and using its OWN file/terminal/memory tools for simple work.

  Because the same session runs every iteration:
  - hindsight_retain/recall persist naturally (same session DB)
  - session_search shows ALL iterations (same conversation)
  - Modifying launch-loop.py or SKILL.md works immediately
  - No `need_reload` needed — the loop IS your session

v2.2.0 improvements:
  - Version bump to align with infinite-loop v11.9.0 release
  - Pushbullet/ntfy notification support added to launch-loop.py
  - Added --preflight and --preflight-fail-fast flag support

v2.1.0 improvements:
  - Version bump to align with infinite-loop v11.7.0 release

PREREQUISITES:
  - Python 3.10+ (stdlib only)
  - Run inside an active Hermes terminal session

USAGE:
  python3 scripts/session-self-loop.py --max-iterations 5 --workdir /path
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Text similarity for convergence detection
# ---------------------------------------------------------------------------


def text_similarity(a: str, b: str) -> float:
    """Compute Jaccard word-overlap similarity between two strings.

    Returns 0.0 (completely different) to 1.0 (identical).
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
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
    threshold: float = 0.9,
    window: int = 5,
) -> tuple[bool, float]:
    """Check if the last N summaries indicate convergence.

    Returns (is_converged, avg_similarity).
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
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="In-session infinite loop (v2.10.0) — "
        "tracks iteration state in a JSON file with convergence detection, "
        "context compaction, and progress tracking."
    )
    parser.add_argument(
        "--max-iterations", type=int, default=0, help="Max iterations (0=infinite)"
    )
    parser.add_argument(
        "--state-file",
        default="/tmp/session-loop-state.json",
        help="Iteration state file path",
    )
    parser.add_argument(
        "--force-reset", action="store_true", help="Clear state and start fresh"
    )
    parser.add_argument(
        "--workdir", default="", help="Change to this working directory before loop"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=7200,
        help="Max seconds to wait per iteration (default: 7200)",
    )
    parser.add_argument(
        "--goal-file", default="", help="File containing the primary goal text"
    )
    parser.add_argument(
        "--initial-goal", default="", help="Seed goal printed at each iteration start"
    )
    parser.add_argument(
        "--compact-every",
        type=int,
        default=5,
        help="Compact summaries every N iterations (default: 5, 0=disable)",
    )
    parser.add_argument(
        "--status-file",
        default="",
        help="Write one-line JSON status to this file after each iteration",
    )
    parser.add_argument(
        "--convergence-stop",
        action="store_true",
        help="Auto-stop when consecutive iterations produce similar summaries",
    )
    parser.add_argument(
        "--convergence-threshold",
        type=float,
        default=0.9,
        help="Similarity threshold for convergence detection (0.0-1.0, default: 0.9)",
    )
    parser.add_argument(
        "--convergence-window",
        type=int,
        default=5,
        help="Recent iterations to compare for convergence (default: 5)",
    )
    args = parser.parse_args()

    # Change workdir if requested
    if args.workdir:
        try:
            os.chdir(args.workdir)
            print(f"[WORKDIR] Changed to {args.workdir}")
        except (OSError, FileNotFoundError) as e:
            print(f"[ERROR] Cannot change to {args.workdir}: {e}")
            sys.exit(1)

    # Load goal from file if specified
    goal_text = args.initial_goal or ""
    if args.goal_file:
        try:
            with open(args.goal_file) as gf:
                goal_text = gf.read().strip()
            print(f"[GOAL] Loaded goal from {args.goal_file}: {goal_text[:120]}")
        except (FileNotFoundError, IOError) as e:
            print(f"[ERROR] Cannot read {args.goal_file}: {e}")
            sys.exit(1)

    state_file = args.state_file

    if args.force_reset and os.path.exists(state_file):
        os.remove(state_file)
        print("[STATE] Reset state file")

    # Load or create state
    state = {"iterations": [], "started_at": None, "completed_at": None}
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                state = json.load(f)
            print(
                f"[STATE] Resumed — {len(state.get('iterations', []))} iterations done"
            )
        except (json.JSONDecodeError, IOError):
            pass

    if state.get("started_at") is None:
        state["started_at"] = datetime.now(timezone.utc).isoformat()

    iteration_count = len(state.get("iterations", []))
    existing_summaries = [it.get("summary", "") for it in state.get("iterations", [])]
    print(f"[LOOP] Starting from iteration {iteration_count + 1}")

    while True:
        if args.max_iterations > 0 and iteration_count >= args.max_iterations:
            print(f"[STOP] Reached max_iterations={args.max_iterations}")
            state["completed_at"] = datetime.now(timezone.utc).isoformat()
            _write_state(state, state_file)
            break

        iteration_count += 1
        started = datetime.now(timezone.utc).isoformat()
        iter_start_time = time.time()

        # Context compaction
        if args.compact_every > 0 and iteration_count % args.compact_every == 0:
            keep_full = max(args.compact_every, 10)
            condensed = 0
            new_summaries = []
            for i, s in enumerate(existing_summaries):
                if i >= len(existing_summaries) - keep_full:
                    new_summaries.append(s)
                else:
                    condensed += 1
            if condensed > 0:
                new_summaries.insert(0, f"[{condensed} earlier iterations condensed]")
            existing_summaries = new_summaries

        # Convergence check
        if args.convergence_stop and iteration_count >= args.convergence_window:
            is_converged, avg_sim = check_convergence(
                existing_summaries,
                threshold=args.convergence_threshold,
                window=args.convergence_window,
            )
            if is_converged:
                print(
                    f"[CONVERGENCE] STOP — Last {args.convergence_window} iterations "
                    f"have {avg_sim:.2f} similarity "
                    f"(threshold={args.convergence_threshold})"
                )
                state["status"] = f"stopped: convergence ({avg_sim:.2f})"
                state["completed_at"] = datetime.now(timezone.utc).isoformat()
                _write_state(state, state_file)
                break

        print(f"\n{'=' * 60}")
        print(f"  Session-Loop Iteration {iteration_count}")
        if args.max_iterations > 0:
            print(f"  Progress: {iteration_count}/{args.max_iterations}")
        print(f"{'=' * 60}")

        # Write pending state
        state["pending"] = {
            "iteration": iteration_count,
            "started_at": started,
        }
        _write_state(state, state_file)

        # Print instructions
        print(f"[INFO] State file: {state_file}")
        print(f"[INFO] Write 'stop' to stop: echo 'stop' > {state_file}")
        print("")
        if goal_text:
            print(f"GOAL: {goal_text}")
            print("")

        print("YOUR TASK: Use this Hermes session's tools to accomplish the goal.")
        print("After completing, write to the state file with format:")
        print(f'  echo \'{{"done": true, "summary": "what happened"}}\' > {state_file}')
        print("")
        print("If you want another iteration, write a summary and next_goal:")
        print(
            f'  echo \'{{"done": false, "summary": "...", "next_goal": "..."}}\' > {state_file}'
        )
        print("")
        print("[WAITING] for state file update from the Hermes session...")

        # Wait for state file update with adaptive polling
        last_mtime = os.path.getmtime(state_file) if os.path.exists(state_file) else 0
        deadline = time.time() + args.timeout
        poll_delay = 2.0  # Start at 2s

        result_data = {}
        while time.time() < deadline:
            try:
                current_mtime = os.path.getmtime(state_file)
                if current_mtime > last_mtime + 0.5:
                    with open(state_file) as f:
                        raw = f.read().strip()
                    if raw == "stop":
                        print("[STOP] Stop signal received")
                        state["completed_at"] = datetime.now(timezone.utc).isoformat()
                        state.pop("pending", None)
                        _write_state(state, state_file)
                        print("[DONE] Loop stopped by user")
                        return
                    try:
                        result_data = json.loads(raw)
                        if isinstance(result_data, dict):
                            break
                    except json.JSONDecodeError:
                        pass
                    last_mtime = current_mtime
                    poll_delay = 2.0  # Reset on activity
                else:
                    # Exponential backoff up to 5s max
                    poll_delay = min(poll_delay * 1.2, 5.0)
            except (OSError, IOError):
                poll_delay = min(poll_delay * 1.2, 5.0)
            time.sleep(poll_delay)

        state.pop("pending", None)
        iter_elapsed = time.time() - iter_start_time

        if not result_data:
            print("[TIMEOUT] No result received within deadline")
            record = _make_record(
                iteration_count,
                started,
                "TIMEOUT - no session response",
                error="timeout",
            )
        elif result_data.get("stop") or result_data.get("done"):
            record = _make_record(
                iteration_count,
                started,
                result_data.get("summary", "Completed"),
                next_goal=result_data.get("next_goal", ""),
            )
            state.setdefault("iterations", []).append(record)
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            _write_state(state, state_file)
            print(f"[DONE] Iteration {iteration_count}: {record['summary'][:120]}")
            break
        else:
            record = _make_record(
                iteration_count,
                started,
                result_data.get("summary", ""),
                next_goal=result_data.get("next_goal", ""),
                error=result_data.get("error"),
            )

        record["duration_seconds"] = round(iter_elapsed, 1)
        state.setdefault("iterations", []).append(record)
        existing_summaries.append(result_data.get("summary", "")[:200])
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        _write_state(state, state_file)

        # Write status file
        if args.status_file:
            _write_status_file(args.status_file, state, iteration_count)

        print(f"[DONE] Iteration {iteration_count}: {record.get('summary', '')[:120]}")
        print(f"[STATS] Duration: {iter_elapsed:.1f}s")

        if result_data.get("done"):
            print("[STOP] Session signaled done")
            state["completed_at"] = datetime.now(timezone.utc).isoformat()
            _write_state(state, state_file)
            break

    # Final summary
    iters = state.get("iterations", [])
    total_dur = sum(it.get("duration_seconds", 0) for it in iters)
    success = sum(1 for it in iters if not it.get("error"))
    errors = len(iters) - success
    print(f"\n[DONE] Session loop completed")
    print(f"  Total iterations: {len(iters)}")
    print(f"  Total duration: {total_dur:.0f}s")
    print(f"  Success: {success}, Errors: {errors}")
    print(f"  State file: {state_file}")


def _make_record(
    iteration_count: int,
    started: str,
    summary: str,
    next_goal: str = "",
    error: str | None = None,
) -> dict:
    return {
        "n": iteration_count,
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "next_goal": next_goal,
        "error": error,
    }


def _write_state(state: dict, path: str) -> None:
    try:
        with open(path, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except (OSError, IOError) as e:
        print(f"[ERROR] Failed to write state: {e}")


def _write_status_file(status_path: str, state: dict, iteration: int) -> None:
    try:
        os.makedirs(os.path.dirname(status_path) or ".", exist_ok=True)
        line = json.dumps(
            {
                "pid": os.getpid(),
                "iteration": iteration,
                "status": state.get("status", "running"),
                "total_iterations": len(state.get("iterations", [])),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        )
        with open(status_path, "w") as f:
            f.write(line + "\n")
    except (OSError, IOError) as e:
        print(f"[STATUS] Failed to write status file: {e}")


if __name__ == "__main__":
    main()
