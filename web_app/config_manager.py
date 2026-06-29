"""Configuration manager — reads/writes JSON config and provides config schema.

The web UI is the sole source of truth. Config is persisted via
pi_loop.config_file (no .env file needed).
"""

import json
import logging
from typing import Any

from pi_loop.config_file import CONFIG_PATH, load_config
from pi_loop.config_file import save_config as _save_config

logger = logging.getLogger(__name__)

# Working configuration flags for pi-loop.
# Only flags that pi actually uses are kept.
CONFIG_DEFAULTS: dict[str, dict[str, Any]] = {
    # ── Core Task ──────────────────────────────────────────────────────
    "INFINITE_LOOP_GOAL": {
        "default": "",
        "type": "string",
        "group": "core",
        "label": "Goal",
        "description": "Task description passed to pi",
        "required": True,
        "multiline": True,
    },
    "INFINITE_LOOP_CONTEXT": {
        "default": "",
        "type": "string",
        "group": "core",
        "label": "Context",
        "description": "Initial context appended to pi's system prompt",
        "multiline": True,
    },
    "INFINITE_LOOP_WORKDIR": {
        "default": "",
        "type": "string",
        "group": "core",
        "label": "Working Directory",
        "description": "Working directory. Empty = current dir.",
    },
    # ── Iteration Control ──────────────────────────────────────────────
    "INFINITE_LOOP_MAX_ITERATIONS": {
        "default": "0",
        "type": "int",
        "group": "iteration",
        "label": "Max Iterations",
        "description": "Stop after N iterations. 0 = infinite.",
    },
    "INFINITE_LOOP_SESSION_TIMEOUT": {
        "default": "600",
        "type": "int",
        "group": "iteration",
        "label": "Session Timeout",
        "description": "Max seconds per spawned pi session.",
    },
    "INFINITE_LOOP_COOLDOWN": {
        "default": "0",
        "type": "int",
        "group": "iteration",
        "label": "Cooldown",
        "description": "Wait N seconds between iterations.",
    },
    "INFINITE_LOOP_MAX_OUTPUT_CHARS": {
        "default": "2000",
        "type": "int",
        "group": "iteration",
        "label": "Max Output Chars",
        "description": "Max chars of pi output to store in ledger.",
    },
    "INFINITE_LOOP_SHUTDOWN_SENTINEL": {
        "default": "/tmp/infinite-loop-stop",
        "type": "string",
        "group": "iteration",
        "label": "Shutdown Sentinel",
        "description": "Path to sentinel file for external stop control.",
    },
    # ── Git Integration ────────────────────────────────────────────────
    "INFINITE_LOOP_GIT": {
        "default": "false",
        "type": "bool",
        "group": "git",
        "label": "Git",
        "description": "Capture git diff stats per iteration.",
    },
    "INFINITE_LOOP_GIT_COMMIT": {
        "default": "false",
        "type": "bool",
        "group": "git",
        "label": "Git Commit",
        "description": "Auto-commit changes per iteration.",
    },
    "INFINITE_LOOP_STORE_GIT_DIFF": {
        "default": "false",
        "type": "bool",
        "group": "git",
        "label": "Store Git Diff",
        "description": "Store actual git diff in the ledger.",
    },
    "INFINITE_LOOP_MAX_IDLE_ITERATIONS": {
        "default": "0",
        "type": "int",
        "group": "git",
        "label": "Max Idle Iterations",
        "description": "Stop after N iterations with no git changes.",
    },
    # ── Goal File (Batch) ───────────────────────────────────────────────
    "INFINITE_LOOP_GOALS_FILE": {
        "default": "",
        "type": "string",
        "group": "goals",
        "label": "Goals File",
        "description": "Path to file with one goal per line.",
    },
    "INFINITE_LOOP_STOP_AT_GOALS_END": {
        "default": "false",
        "type": "bool",
        "group": "goals",
        "label": "Stop at Goals End",
        "description": "Stop when all goals exhausted.",
    },
    "INFINITE_LOOP_TRACK_GOALS": {
        "default": "false",
        "type": "bool",
        "group": "goals",
        "label": "Track Goals",
        "description": "Track completed goals in the ledger.",
    },
    "INFINITE_LOOP_RESET_GOALS": {
        "default": "false",
        "type": "bool",
        "group": "goals",
        "label": "Reset Goals",
        "description": "Clear goals_completed tracking.",
    },
    # ── Logging ────────────────────────────────────────────────────────
    "INFINITE_LOOP_LOG_FILE": {
        "default": "",
        "type": "string",
        "group": "logging",
        "label": "Log File",
        "description": "Path to daemon log file.",
    },
    "INFINITE_LOOP_LOG_MAX_MB": {
        "default": "10",
        "type": "int",
        "group": "logging",
        "label": "Log Max MB",
        "description": "Max log file size in MB before rotation.",
    },
    # ── Status ─────────────────────────────────────────────────────────
    "INFINITE_LOOP_STATUS_FILE": {
        "default": "",
        "type": "string",
        "group": "status",
        "label": "Status File",
        "description": "Path to JSON status file.",
    },
    # ── Ledger Management ──────────────────────────────────────────────
    "INFINITE_LOOP_KEEP_ITERATIONS": {
        "default": "0",
        "type": "int",
        "group": "ledger",
        "label": "Keep Iterations",
        "description": "Auto-shrink ledger to last N iterations.",
    },
    "INFINITE_LOOP_FORCE_RESET": {
        "default": "false",
        "type": "bool",
        "group": "ledger",
        "label": "Force Reset",
        "description": "Clear existing ledger and start fresh.",
    },
    "INFINITE_LOOP_TAG": {
        "default": "",
        "type": "string",
        "group": "ledger",
        "label": "Tag",
        "description": "Label/identifier for the run.",
    },
    # ── Notifications ──────────────────────────────────────────────────
    "INFINITE_LOOP_NOTIFY_DESKTOP": {
        "default": "false",
        "type": "bool",
        "group": "notifications",
        "label": "Notify Desktop",
        "description": "Send desktop notifications via notify-send.",
    },
    "INFINITE_LOOP_ON_ERROR_CMD": {
        "default": "",
        "type": "string",
        "group": "notifications",
        "label": "On Error Command",
        "description": "Shell command when iteration fails.",
    },
    # ── Startup ────────────────────────────────────────────────────────
    "INFINITE_LOOP_STARTUP_DELAY": {
        "default": "0.0",
        "type": "float",
        "group": "startup",
        "label": "Startup Delay",
        "description": "Wait N seconds before first iteration.",
    },
    "INFINITE_LOOP_QUIET": {
        "default": "false",
        "type": "bool",
        "group": "startup",
        "label": "Quiet",
        "description": "Suppress verbose startup banner.",
    },
    "INFINITE_LOOP_PREFLIGHT": {
        "default": "false",
        "type": "bool",
        "group": "startup",
        "label": "Preflight",
        "description": "Run preflight health checks.",
    },
    "INFINITE_LOOP_PREFLIGHT_FAIL_FAST": {
        "default": "false",
        "type": "bool",
        "group": "startup",
        "label": "Preflight Fail Fast",
        "description": "Stop on first preflight failure.",
    },
    "INFINITE_LOOP_DRY_RUN": {
        "default": "false",
        "type": "bool",
        "group": "startup",
        "label": "Dry Run",
        "description": "Print config and exit.",
    },
}


# Group definitions for the UI
CONFIG_GROUPS = [
    {"id": "core", "name": "Core Task", "icon": "target"},
    {"id": "iteration", "name": "Iteration Control", "icon": "repeat"},
    {"id": "git", "name": "Git Integration", "icon": "git-branch"},
    {"id": "goals", "name": "Goal File (Batch)", "icon": "list"},
    {"id": "logging", "name": "Logging", "icon": "file-text"},
    {"id": "status", "name": "Status", "icon": "activity"},
    {"id": "ledger", "name": "Ledger Management", "icon": "database"},
    {"id": "notifications", "name": "Notifications", "icon": "bell"},
    {"id": "startup", "name": "Startup", "icon": "play-circle"},
]


def _read_stored() -> dict[str, str]:
    """Read stored config via pi_loop.config_file.load_config()."""
    try:
        stored = load_config()
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read config file: %s; using defaults", exc)
        # Rename corrupt file so it doesn't keep failing
        if CONFIG_PATH.exists():
            backup = CONFIG_PATH.with_suffix(".json.corrupt")
            CONFIG_PATH.rename(backup)
            logger.info("Renamed corrupt config to %s", backup)
        stored = {}

    config: dict[str, str] = {}
    for k, meta in CONFIG_DEFAULTS.items():
        val = stored.get(k)
        if val is None:
            config[k] = meta["default"]
            continue
        t = meta.get("type", "string")
        if t == "bool":
            config[k] = "true" if str(val).lower() == "true" else "false"
        elif t == "int":
            try:
                config[k] = str(int(val))
            except (ValueError, TypeError):
                config[k] = str(val)
        elif t == "float":
            try:
                config[k] = str(float(val))
            except (ValueError, TypeError):
                config[k] = str(val)
        else:
            config[k] = str(val)
    return config


def save_config(config: dict[str, str]) -> None:
    """Persist config dict via pi_loop.config_file.save_config()."""
    _save_config(config)


def validate_config(config: dict[str, str]) -> dict[str, bool | list[str]]:
    """Validate configuration values."""
    errors: list[str] = []
    for key, meta in CONFIG_DEFAULTS.items():
        if meta.get("required") and not config.get(key):
            errors.append(f"{meta['label']} ({key}) is required")
    return {"valid": len(errors) == 0, "errors": errors}


def get_config() -> dict[str, dict[str, Any]]:
    """Get full config schema with current values."""
    current = _read_stored()
    result: dict[str, dict[str, Any]] = {}
    for key, meta in CONFIG_DEFAULTS.items():
        entry = dict(meta)
        entry["value"] = current.get(key, meta["default"])
        result[key] = entry
    return result


def get_raw_config() -> dict[str, str]:
    """Get raw key-value config, filling defaults for unset keys."""
    return _read_stored()


def build_cli_args(config: dict[str, str]) -> list[str]:
    """Build CLI argument list from config dict for pi-loop."""
    args: list[str] = []

    str_flags: dict[str, str] = {
        "INFINITE_LOOP_GOAL": "--goal",
        "INFINITE_LOOP_WORKDIR": "--workdir",
        "INFINITE_LOOP_MAX_ITERATIONS": "--max-iterations",
        "INFINITE_LOOP_SESSION_TIMEOUT": "--session-timeout",
        "INFINITE_LOOP_COOLDOWN": "--cooldown",
        "INFINITE_LOOP_MAX_OUTPUT_CHARS": "--max-output-chars",
        "INFINITE_LOOP_TAG": "--tag",
        "INFINITE_LOOP_SHUTDOWN_SENTINEL": "--shutdown-sentinel",
        "INFINITE_LOOP_LOG_FILE": "--log-file",
        "INFINITE_LOOP_LOG_MAX_MB": "--log-max-mb",
        "INFINITE_LOOP_STATUS_FILE": "--status-file",
        "INFINITE_LOOP_GOALS_FILE": "--goals-file",
        "INFINITE_LOOP_ON_ERROR_CMD": "--on-error-cmd",
        "INFINITE_LOOP_STARTUP_DELAY": "--startup-delay",
        "INFINITE_LOOP_WATCH_DIR": "--watch-dir",
        "INFINITE_LOOP_WATCH_POLL": "--watch-poll",
        "INFINITE_LOOP_KEEP_ITERATIONS": "--keep-iterations",
        "INFINITE_LOOP_MAX_IDLE_ITERATIONS": "--max-idle-iterations",
    }

    for env_key, flag in str_flags.items():
        val = config.get(env_key, "")
        if val and val != CONFIG_DEFAULTS.get(env_key, {}).get("default", ""):
            args.extend([flag, val])

    # Context uses --append-system-prompt (pi's flag name)
    ctx = config.get("INFINITE_LOOP_CONTEXT", "")
    if ctx:
        args.extend(["--append-system-prompt", ctx])

    bool_flags: dict[str, str] = {
        "INFINITE_LOOP_GIT": "--git",
        "INFINITE_LOOP_GIT_COMMIT": "--git-commit",
        "INFINITE_LOOP_STORE_GIT_DIFF": "--store-git-diff",
        "INFINITE_LOOP_NOTIFY_DESKTOP": "--notify-desktop",
        "INFINITE_LOOP_STOP_AT_GOALS_END": "--stop-at-goals-end",
        "INFINITE_LOOP_TRACK_GOALS": "--track-goals",
        "INFINITE_LOOP_RESET_GOALS": "--reset-goals",
        "INFINITE_LOOP_QUIET": "--quiet",
        "INFINITE_LOOP_PREFLIGHT": "--preflight",
        "INFINITE_LOOP_PREFLIGHT_FAIL_FAST": "--preflight-fail-fast",
        "INFINITE_LOOP_DRY_RUN": "--dry-run",
    }

    for env_key, flag in bool_flags.items():
        if config.get(env_key, "").lower() == "true":
            args.append(flag)

    return args
