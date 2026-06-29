"""Ledger loading/creation — load_or_create_ledger function."""

import os
import time
from datetime import datetime, timezone

from .config import VERSION
from .file_utils import _log, read_ledger, write_ledger
from .stats import _recalc_stats


def _version_detail() -> str:
    return f"v{VERSION} -- WebUI dashboard, SSE live updates, iterative task execution, error recovery, goal tracking."


def load_or_create_ledger(goal: str, context: str, sentinel_path: str = "", reset_goals: bool = False) -> dict:
    existing = read_ledger()

    if sentinel_path and os.path.exists(sentinel_path):
        try:
            os.remove(sentinel_path)
            _log(f"[CLEANUP] Removed stale sentinel file: {sentinel_path}")
        except OSError as e:
            _log(f"[WARN] Could not remove stale sentinel: {e}")

    if existing is not None:
        if existing.get("initial_command") == goal:
            _log(f"[INFO] Resuming from existing ledger ({existing['total_iterations']} iterations done)")
            existing["status"] = "running"
            existing["last_updated"] = datetime.now(timezone.utc).isoformat()
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
                    _log(f"[RECOVER] Stale pending iteration #{pending.get('n')} ({elapsed:.0f}s old)")
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
            if "error_type_counts" not in existing:
                existing["error_type_counts"] = {
                    "timeout": 0,
                    "network": 0,
                    "schema": 0,
                    "unknown": 0,
                    "heartbeat": 0,
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
        "version_detail": _version_detail(),
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
            "consecutive_successes": 0,
        },
        "error_type_counts": {
            "timeout": 0,
            "network": 0,
            "schema": 0,
            "unknown": 0,
            "heartbeat": 0,
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
