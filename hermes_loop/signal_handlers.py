"""Signal handlers and auto-reload functionality."""

import os
import signal
import sys
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
_startup_file_snapshots: dict[str, tuple[float, int]] = {}


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


    try:
        _subprocess.run(
            ["pkill", "-9", "-f", "hermes.*chat -q"], capture_output=True, timeout=5
        )
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
        _log(f"    {c.dim('Resume:')}          bash run.sh")
        _log(
            f"    {c.dim('Check status:')}    cat /tmp/infinite-loop-state.json | python3 -m json.tool"
        )
        _log(f"{c.header('══════════════════════════════════════════════')}")
        _log("")
    except Exception:
        pass

    _log(f"[STOP] {signame} received. Worker and child processes cleaned up. Exiting.")
    sys.exit(128 + signum)


def _snapshot_file(path: str) -> tuple[float, int] | None:
    """Return (mtime, size) for a file, or None if it doesn't exist."""
    try:
        s = os.stat(path)
        return (s.st_mtime, s.st_size)
    except (FileNotFoundError, OSError):
        return None


def _check_auto_reload(
    workdir: str | None,
    state: dict,
    worker_manager: object | None,
    status_file: str,
    iteration_count: int,
) -> None:
    """Check if daemon source files changed on disk and restart if so."""
    global _startup_file_snapshots
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
    # Reconstruct argv for -m invocation: sys.argv is ['-m', 'hermes_loop', ...]
    # os.execv replaces the process — everything (env, cwd, fd) is preserved.
    if sys.argv[0] == "-m":
        exec_argv = [sys.executable, "-m"] + sys.argv[1:]
    else:
        exec_argv = [sys.executable] + sys.argv
    _log("[AUTO-RELOAD] Executing os.execv() with updated code...")
    os.execv(sys.executable, exec_argv)


# Register signal handlers at module level (must happen before any imports
# that might set up their own handlers)
signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)
