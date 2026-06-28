"""Status file writer — emits a JSON status snapshot for web UI consumption.

The web_app server reads this file to get live loop status without
importing pi_loop runtime modules directly.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

# Default status file path (overridable via PI_LOOP_STATUS_FILE)
STATUS_FILE_DEFAULT = os.environ.get("PI_LOOP_STATUS_FILE", "/tmp/loop-status.json")


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

    if uptime_seconds is None and pid is not None:
        # Approximate uptime from process start time
        try:
            with open(f"/proc/{pid}/stat") as f:
                parts = f.read().split()
                # starttime is field 21 (0-indexed: 21), in clock ticks
                clock_ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
                start_ticks = int(parts[21])
                boot_time = time.monotonic() - (time.time() - time.monotonic())  # rough
                uptime_seconds = time.time() - (
                    (start_ticks / clock_ticks) + boot_time + 0  # approximate
                )
        except (OSError, IndexError, ValueError, KeyError):
            uptime_seconds = 0.0

    data: dict[str, Any] = {
        "running": running,
        "pid": pid or os.getpid(),
        "start_time": start_time,
        "iteration_count": iteration_count,
        "last_error": last_error,
        "version": version or "unknown",
        "uptime_seconds": round(uptime_seconds or 0, 1)
        if uptime_seconds is not None
        else 0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.write("\n")
    except OSError:
        # Silently fail — status writing is best-effort
        pass
