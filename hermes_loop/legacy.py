"""Legacy helpers and backward compatibility shims."""

# This module provides backward-compatible imports for code that
# references the old monolithic module structure.

from .config import (
    LEDGER_PATH,
    LOCK_PATH,
    SENTINEL_PATH_DEFAULT,
    STATUS_FILE_DEFAULT,
    HERMES_SESSION_TIMEOUT,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    DEFAULT_CONVERGENCE_WINDOW,
    DEFAULT_CONVERGENCE_THRESHOLD,
    BASE_TOOLSETS,
    TASK_PATTERNS,
    LAUNCH_LOOP_VERSION,
)
from .file_utils import (
    FileLock,
    _log,
    _init_logger,
    _init_daemon_log,
    _daemon_logger,
    write_ledger,
    read_ledger,
    write_status_file,
    check_sentinel,
    check_sentinel_no_remove,
    extract_json_from_output,
)
from .signal_handlers import (
    _handle_shutdown,
    _hermes_worker_ref,
    _shutdown_requested,
    _startup_file_snapshots,
    _snapshot_file,
    _check_auto_reload,
)

__all__ = [
    "FileLock",
    "_log",
    "_init_logger",
    "_init_daemon_log",
    "_daemon_logger",
    "write_ledger",
    "read_ledger",
    "write_status_file",
    "check_sentinel",
    "check_sentinel_no_remove",
    "extract_json_from_output",
    "_handle_shutdown",
    "_hermes_worker_ref",
    "_shutdown_requested",
    "_startup_file_snapshots",
    "_snapshot_file",
    "_check_auto_reload",
    "LEDGER_PATH",
    "LOCK_PATH",
    "SENTINEL_PATH_DEFAULT",
    "STATUS_FILE_DEFAULT",
    "HERMES_SESSION_TIMEOUT",
    "LOG_FORMAT",
    "LOG_DATE_FORMAT",
    "DEFAULT_CONVERGENCE_WINDOW",
    "DEFAULT_CONVERGENCE_THRESHOLD",
    "BASE_TOOLSETS",
    "TASK_PATTERNS",
    "LAUNCH_LOOP_VERSION",
]
