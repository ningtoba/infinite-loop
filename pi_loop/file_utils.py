"""File locking, logging, ledger I/O, sentinel checks, and JSON extraction."""

import fcntl
import json
import logging
import logging.handlers
import os
import re
import time
from datetime import datetime, timezone

from .color_utils import colorizer as _cu
from .config import LEDGER_PATH, LOCK_PATH, LOG_DATE_FORMAT, LOG_FORMAT

# Module-level logger reference
_daemon_logger: logging.Logger | None = None


# ---------------------------------------------------------------------------
# File locking (POSIX flock)
# ---------------------------------------------------------------------------


class FileLock:
    def __init__(self, path: str = LOCK_PATH, timeout: float = 10.0):
        self.path = path
        self.timeout = timeout
        self._fd: int | None = None

    def __enter__(self):
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise TimeoutError(
                        f"Could not acquire lock on {self.path} within {self.timeout}s"
                    ) from None
                time.sleep(0.1)

    def __exit__(self, *args):
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _colorize_log_tags(msg: str) -> str:
    """Auto-colorize known log tags like [INFO], [WARN], [ERROR], etc.

    Uses the global colorizer singleton. If color is disabled, returns
    the original message unchanged.
    """
    if not _cu._enabled():
        return msg

    # Map tag patterns to colorizer helper methods
    _tag_color_map = [
        (r"\[ERROR\]", _cu.fail),
        (r"\[FAIL\]", _cu.fail),
        (r"\[WARN\]", _cu.warn),
        (r"\[SUGGEST\]", _cu.group_title),
        (r"\[OK\]", _cu.ok),
        (r"\[SUMMARY\]", _cu.tag_summary),
        (r"\[DONE\]", _cu.ok),
        (r"\[BEAT\]", _cu.dim),
        (r"\[DAEMON\]", _cu.subheader),
        (r"\[PREFLIGHT\]", _cu.subheader),
        (r"\[GOALS\]", _cu.header),
        (r"\[COOLDOWN\]", _cu.warn),
        (r"\[COMPACT\]", _cu.dim),
        (r"\[ARCHIVE\]", _cu.dim),
        (r"\[STATUS\]", _cu.dim),
        (r"\[LOG\]", _cu.dim),
        (r"\[CONFIG\]", _cu.subheader),
        (r"\[CONTEXT\]", _cu.dim),
        (r"\[OUTPUT\]", _cu.dim),
        (r"\[HEARTBEAT\]", _cu.dim),
        (r"\[AUTO-RELOAD\]", _cu.subheader),
        (r"\[MODE\]", _cu.header),
        (r"\[NOTE\]", _cu.warn),
    ]

    for pattern, formatter in _tag_color_map:
        if formatter in (_cu.tag_summary, _cu.tag_suggest):
            # tag helpers take no text arg — replace the entire match
            msg = re.sub(pattern, formatter(), msg)
        else:
            msg = re.sub(pattern, lambda m, f=formatter: f(m.group(0)), msg)
    return msg


def _log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    colored_msg = _colorize_log_tags(msg)
    print(f"[{ts}] {colored_msg}", flush=True)
    if _daemon_logger is not None:
        log_level = getattr(logging, level.upper(), logging.INFO)
        _daemon_logger.log(log_level, msg)


def _init_logger(log_file: str, max_mb: int = 10) -> logging.Logger:
    """Initialize a file logger with size-based rotation."""
    logger = logging.getLogger("infinite-loop")
    logger.setLevel(logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_mb * 1024 * 1024, backupCount=1
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    logger.addHandler(handler)
    return logger


# ---------------------------------------------------------------------------
# Daemon log file management
# ---------------------------------------------------------------------------


def _init_daemon_log(log_file: str, max_mb: int = 10) -> logging.Logger:
    """Initialize logging to file. Must be called before the main loop."""
    global _daemon_logger
    log_dir = os.path.dirname(os.path.abspath(log_file))
    os.makedirs(log_dir, exist_ok=True)
    _daemon_logger = _init_logger(log_file, max_mb)
    _log(f"[LOG] Logging to {log_file} (max {max_mb}MB, rotation on overflow)")
    return _daemon_logger


# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------


def write_ledger(state: dict) -> None:
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    tmp_path = LEDGER_PATH + ".tmp"
    with FileLock():
        with open(tmp_path, "w") as f:
            json.dump(state, f, indent=2, default=str)
        os.replace(tmp_path, LEDGER_PATH)


def read_ledger() -> dict | None:
    if not os.path.exists(LEDGER_PATH):
        return None
    try:
        with FileLock(), open(LEDGER_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, TimeoutError):
        return None


# ---------------------------------------------------------------------------
# Status file
# ---------------------------------------------------------------------------


def write_status_file(
    status_path: str, state: dict, iteration: int = 0, status: str = "running"
) -> None:
    """Write a lightweight one-line status file for external monitoring."""
    if not status_path:
        return
    try:
        os.makedirs(os.path.dirname(status_path) or ".", exist_ok=True)
        line = json.dumps(
            {
                "pid": os.getpid(),
                "iteration": iteration,
                "status": status,
                "total_iterations": state.get("total_iterations", 0),
                "total_duration_seconds": state.get("stats", {}).get(
                    "total_duration_seconds", 0
                ),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        )
        with open(status_path, "w") as f:
            f.write(line + "\n")
    except OSError as e:
        _log(f"[STATUS] Failed to write status file {status_path}: {e}")


# ---------------------------------------------------------------------------
# Sentinel checks
# ---------------------------------------------------------------------------


def check_sentinel(path: str) -> str | None:
    if path and os.path.exists(path):
        with open(path) as f:
            content = f.read().strip()
        os.remove(path)
        return content
    return None


def check_sentinel_no_remove(path: str) -> str | None:
    """Read sentinel without removing it. Used for pause/resume polling."""
    if path and os.path.exists(path):
        with open(path) as f:
            content = f.read().strip()
        return content
    return None


# ---------------------------------------------------------------------------
# JSON extraction from spawned session output
# ---------------------------------------------------------------------------


def extract_json_from_output(stdout: str) -> dict | None:
    """Extract a JSON object from spawned session output using brace-depth counting."""
    if not stdout:
        return None

    # Strip common trailing noise from chat -q
    lines = []
    for line in stdout.split("\n"):
        stripped = line.strip()
        if stripped.startswith("session_id:"):
            continue
        lines.append(line)

    text = "\n".join(lines)

    # Strategy 1: Scan backwards looking for the LAST JSON object
    brace_depth = 0
    in_json = False
    json_chars = []
    for ch in reversed(text):
        if ch == "}":
            brace_depth += 1
            in_json = True
            json_chars.insert(0, ch)
        elif ch == "{":
            brace_depth -= 1
            in_json = True
            json_chars.insert(0, ch)
            if brace_depth == 0:
                candidate = "".join(json_chars)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
                in_json = False
                json_chars = []
                brace_depth = 0
        elif in_json:
            json_chars.insert(0, ch)

    # Strategy 2: Forward scan — find ALL JSON blocks, return last valid one
    json_objects = []
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start < 0:
            break
        depth = 0
        j = start
        while j < len(text):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : j + 1]
                    try:
                        obj = json.loads(candidate)
                        json_objects.append(obj)
                        i = j + 1
                        break
                    except json.JSONDecodeError:
                        i = j + 1
                        break
            j += 1
        else:
            i = start + 1

    if json_objects:
        return json_objects[-1]

    return None
