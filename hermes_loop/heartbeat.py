"""Heartbeat helpers (Session Self-Healing)."""

import json
import os
import subprocess
import threading
import time

from .config import (
    HEARTBEAT_DIR,
    HEARTBEAT_PREFIX,
    HEARTBEAT_GRACE_FACTOR,
    HEARTBEAT_POLL_INTERVAL,
    HEARTBEAT_KILL_GRACE,
)
from .file_utils import _log
from .signal_handlers import _shutdown_requested


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
    """Run _monitor_heartbeat in a daemon thread with a timeout cap."""
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
