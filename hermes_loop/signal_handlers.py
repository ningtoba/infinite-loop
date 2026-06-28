"""Signal handlers and auto-reload functionality."""

import os
import signal
import sys
import threading
import time
import subprocess as _subprocess
from datetime import datetime, timezone

import json

from .config import LEDGER_PATH
from .file_utils import _log, write_ledger, write_status_file
from .color_utils import colorizer as _shutdown_signal_colorizer

# Flag set by signal handler for graceful shutdown
_shutdown_requested = False
# References to current state for signal-safe ledger write
_shutdown_state_ref: dict | None = None
_hermes_worker_ref: object | None = None

# Module-level cache: store file mtime and size at daemon startup
# Populated once via init_auto_reload() — never {} at runtime
_startup_file_snapshots: dict[str, tuple[float, int]] = {}
_startup_file_snapshots_initialized: bool = False


def _handle_shutdown(signum, frame):
    """Handle SIGINT/Ctrl+C and SIGTERM by cleaning up child processes and exiting."""
    global _shutdown_requested
    if _shutdown_requested:
        return
    _shutdown_requested = True

    signame = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"

    state = _shutdown_state_ref
    if state is not None:
        state["status"] = f"stopped: {signame}"
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        try:
            tmp_path = LEDGER_PATH + ".sigterm.tmp"
            with open(tmp_path, "w") as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(tmp_path, LEDGER_PATH)
        except Exception:
            pass

    worker = _hermes_worker_ref
    if worker is not None:
        try:
            worker.stop()
        except Exception:
            pass

    pgid = None
    try:
        # Kill descendant processes — try SIGTERM first, then SIGKILL
        # Kill the process group for immediate children, then pkill -P for descendants
        try:
            pgid = os.getpgid(os.getpid())
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, OSError, PermissionError):
            pass
        _subprocess.run(
            ["pkill", "-15", "-P", str(os.getpid())],
            capture_output=True,
            timeout=3,
        )
        time.sleep(2)
        # Force-kill any remaining
        _subprocess.run(
            ["pkill", "-9", "-P", str(os.getpid())],
            capture_output=True,
            timeout=3,
        )
        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, OSError, PermissionError):
                pass
    except Exception:
        pass

    # Print shutdown summary from signal context
    try:
        iteration_count = len(state.get("iterations", [])) if state else 0
        # Avoid circular import — inline a compact summary for signal handler
        c = _shutdown_signal_colorizer
        _log("")
        _log(f"{c.header('═══════════ SHUTDOWN SUMMARY (signal) ═══════════')}")
        _log(f"  {c.value('Signal:')}      {c.flag(signame)}")
        _log(f"  {c.value('Iterations:')}   {c.flag(str(iteration_count))}")
        if state:
            stop_reason = state.get("status", "interrupted")
            _log(f"  {c.value('Status:')}      {c.dim(stop_reason)}")
        _log("")
        _log(f"  {c.group_title('Next steps:')}")
        _log(f"    {c.dim('View ledger:')}     bash scripts/inspect-ledger.sh")
        _log(
            f"    {c.dim('Errors:')}          bash scripts/inspect-ledger.sh --errors-only"
        )
        _log(f"    {c.dim('Resume:')}          bash scripts/run-loop.sh")
        _log(
            f"    {c.dim('Check status:')}    cat /tmp/infinite-loop-state.json | python3 -m json.tool"
        )
        _log(f"{c.header('══════════════════════════════════════════════')}")
        _log("")
    except Exception:
        pass

    _log(
        f"[STOP] {signame} received. "
        f"Workers killed — main loop will handle final cleanup."
    )

    # Fallback: if the main loop is blocked and never checks _shutdown_requested,
    # exit after a timeout. The main loop's _sleep_with_shutdown_check checks
    # every second; subprocess runs have heartbeat_timeout. This is a safety net.
    def _hard_exit() -> None:
        _log("[STOP] Main loop did not clean up — forcing exit.")
        sys.exit(128 + signum)

    timer = threading.Timer(30.0, _hard_exit)
    timer.daemon = True
    timer.start()


def _snapshot_file(path: str) -> tuple[float, int] | None:
    """Return (mtime, size) for a file, or None if it doesn't exist."""
    try:
        s = os.stat(path)
        return (s.st_mtime, s.st_size)
    except (FileNotFoundError, OSError):
        return None


def _build_exec_argv() -> list[str]:
    """Build argv for os.execv, handling -m invocation.

    Reconstructs sys.argv correctly for both direct invocation
    (``python3 launch-loop.py --run``) and module invocation
    (``python3 -m hermes_loop --run``).  In the -m case, sys.argv
    is ``['-m', 'hermes_loop', ...]`` so we need to insert
    ``sys.executable`` before ``-m`` to make os.execv work.
    """
    if sys.argv[0] == "-m":
        return [sys.executable, "-m"] + sys.argv[1:]
    return [sys.executable] + sys.argv


def init_auto_reload(workdir: str | None) -> None:
    """Initialize the file snapshots for auto-reload detection.

    Must be called once at daemon startup (from run_loop or equivalent).
    Snapshots the current mtime/size of launch-loop.py, run.sh, and .env
    so _check_auto_reload can detect subsequent changes.

    Skipped when HERMES_LOOP_NO_AUTO_RELOAD=1 (set by web UI).
    """
    global _startup_file_snapshots, _startup_file_snapshots_initialized
    if os.environ.get("HERMES_LOOP_NO_AUTO_RELOAD") == "1":
        _startup_file_snapshots_initialized = True  # mark done, but empty
        _log("[AUTO-RELOAD] Disabled via HERMES_LOOP_NO_AUTO_RELOAD (web UI mode)")
        return
    if not workdir:
        return
    files_to_check = [
        os.path.join(workdir, "launch-loop.py"),
        os.path.join(workdir, "run.sh"),
        os.path.join(workdir, ".env"),
    ]
    for fpath in files_to_check:
        snap = _snapshot_file(fpath)
        if snap is not None:
            _startup_file_snapshots[fpath] = snap
    _startup_file_snapshots_initialized = True
    if _startup_file_snapshots:
        _log(
            f"[AUTO-RELOAD] Watching {len(_startup_file_snapshots)} file(s) for changes"
        )


def _check_auto_reload(
    workdir: str | None,
    state: dict,
    worker_manager: object | None,
    status_file: str,
    iteration_count: int,
) -> None:
    """Check if daemon source files changed on disk and restart if so."""
    global _startup_file_snapshots
    if os.environ.get("HERMES_LOOP_NO_AUTO_RELOAD") == "1":
        return
    if not _startup_file_snapshots or not workdir:
        return

    files_to_check = [
        os.path.join(workdir, "launch-loop.py"),
        os.path.join(workdir, "run.sh"),
        os.path.join(workdir, ".env"),
    ]

    changed = []
    for fpath in files_to_check:
        current = _snapshot_file(fpath)
        cached = _startup_file_snapshots.get(fpath)
        if current is not None and cached is not None:
            if current != cached:
                changed.append(os.path.basename(fpath))
                _startup_file_snapshots[fpath] = current

    if not changed:
        return

    _log(
        f"[AUTO-RELOAD] Detected changes in: {', '.join(changed)}. Restarting daemon..."
    )
    state["status"] = "reloading"
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    write_ledger(state)
    write_status_file(status_file, state, iteration_count, "reloading")
    if worker_manager is not None:
        try:
            worker_manager.stop()
        except Exception:
            pass
    # Reconstruct argv for -m invocation using shared helper
    exec_argv = _build_exec_argv()
    _log("[AUTO-RELOAD] Executing os.execv() with updated code...")
    os.execv(sys.executable, exec_argv)


# Register signal handlers at module level (must happen before any imports
# that might set up their own handlers)
signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)
