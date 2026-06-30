"""Status file writer — emits a JSON status snapshot for web UI consumption.

The web_app server reads this file to get live loop status without
importing omp_loop runtime modules directly.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from .config import _get_data_dir

logger = logging.getLogger(__name__)

# Default status file path (overridable via OMP_LOOP_STATUS_FILE)
STATUS_FILE_DEFAULT = os.environ.get("OMP_LOOP_STATUS_FILE", os.path.join(_get_data_dir(), "loop-status.json"))

# Process start time (monotonic clock) — used for accurate uptime calculation.
# Set once at import time, which is effectively when the process starts.
_process_start_time = time.monotonic()


def write_status(
    status_path: str | None = None,
    *,
    running: bool = True,
    pid: int | None = None,
    start_time: str | None = None,
    iteration_count: int = 0,
    last_error: str | None = None,
    version: str = "",
    uptime_seconds: float | None = None,
) -> None:
    """Write a comprehensive status JSON file for the web UI to consume.

    This is called by the daemon loop after every iteration to keep the
    web interface up to date without requiring direct IPC.
    """
    path = status_path or STATUS_FILE_DEFAULT
    if not path:
        return

    if start_time is None:
        start_time = datetime.now(timezone.utc).isoformat()

    if uptime_seconds is None:
        # Use monotonic clock from process start — accurate, portable, simple.
        uptime_seconds = time.monotonic() - _process_start_time

    data: dict[str, Any] = {
        "running": running,
        "pid": pid or os.getpid(),
        "start_time": start_time,
        "iteration_count": iteration_count,
        "last_error": last_error,
        "version": version or "unknown",
        "uptime_seconds": round(uptime_seconds or 0, 1) if uptime_seconds is not None else 0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.write("\n")
    except OSError as e:
        logger.warning("Failed to write status file to %s: %s", path, e)
