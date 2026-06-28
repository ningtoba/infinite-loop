"""Configuration manager — reads/writes JSON config and provides config schema.

The web UI is the sole source of truth. Config is persisted as a flat
JSON dict at CONFIG_PATH (no .env file needed).
"""

import json
import os
from typing import Any

# Where the config JSON is stored
CONFIG_PATH = "/tmp/hermes-loop/config.json"


# Default configuration values matching .env.example
CONFIG_DEFAULTS: dict[str, dict[str, Any]] = {
    "INFINITE_LOOP_GOAL": {
        "default": "",
        "type": "string",
        "group": "core",
        "label": "Goal",
        "description": "Core task description for spawned Hermes sessions",
        "required": True,
        "multiline": True,
    },
    "INFINITE_LOOP_CONTEXT": {
        "default": "",
        "type": "string",
        "group": "core",
        "label": "Context",
        "description": "Initial context (paths, constraints, language)",
        "multiline": True,
    },
    "INFINITE_LOOP_CONTEXT_FILE": {
        "default": "",
        "type": "string",
        "group": "core",
        "label": "Context File",
        "description": "Path to file containing context",
    },
    "INFINITE_LOOP_WORKDIR": {
        "default": "",
        "type": "string",
        "group": "core",
        "label": "Working Directory",
        "description": "Working directory for spawned sessions. Empty = current dir. Set to your project path (e.g. /home/nekophobia/Projects/video-analysis). Docker overrides this to /workdir automatically.",
    },
    "INFINITE_LOOP_TOOLSETS": {
        "default": "terminal,file,delegation,web,skills,browser,memory,session_search,code_execution,todo,vision",
        "type": "string",
        "group": "core",
        "label": "Toolsets",
        "description": "Comma-separated toolsets for spawned sessions",
    },
    "INFINITE_LOOP_NO_AUTO_TOOLSETS": {
        "default": "false",
        "type": "bool",
        "group": "core",
        "label": "No Auto Toolsets",
        "description": "Disable automatic toolset enrichment",
    },
    "INFINITE_LOOP_NO_FAILURE_LEARNING": {
        "default": "false",
        "type": "bool",
        "group": "core",
        "label": "No Failure Learning",
        "description": "Skip injecting past failure context",
    },
    "INFINITE_LOOP_MAX_ITERATIONS": {
        "default": "0",
        "type": "int",
        "group": "iteration",
        "label": "Max Iterations",
        "description": "Stop after N iterations. 0 = infinite",
    },
    "INFINITE_LOOP_MAX_TURNS": {
        "default": "500",
        "type": "int",
        "group": "iteration",
        "label": "Max Turns",
        "description": "Max turns per spawned Hermes session",
    },
    "INFINITE_LOOP_COMPACT_EVERY": {
        "default": "5",
        "type": "int",
        "group": "iteration",
        "label": "Compact Every",
        "description": "Compact context every N iterations",
    },
    "INFINITE_LOOP_EVOLVE": {
        "default": "false",
        "type": "bool",
        "group": "iteration",
        "label": "Evolve",
        "description": "Let each iteration propose the next goal",
    },
    "INFINITE_LOOP_RUN": {
        "default": "false",
        "type": "bool",
        "group": "iteration",
        "label": "Run",
        "description": "Start the loop (managed by web UI)",
    },
    "INFINITE_LOOP_WORKERS": {
        "default": "1",
        "type": "int",
        "group": "parallelism",
        "label": "Workers",
        "description": "Number of concurrent Hermes sessions per iteration",
    },
    "INFINITE_LOOP_SESSION_TIMEOUT": {
        "default": "7200",
        "type": "int",
        "group": "timeouts",
        "label": "Session Timeout",
        "description": "Max seconds per spawned Hermes session",
    },
    "INFINITE_LOOP_RETRY_DELAY": {
        "default": "0",
        "type": "int",
        "group": "timeouts",
        "label": "Retry Delay",
        "description": "Backoff seconds on consecutive errors",
    },
    "INFINITE_LOOP_MAX_RETRIES": {
        "default": "0",
        "type": "int",
        "group": "timeouts",
        "label": "Max Retries",
        "description": "Retry a failed iteration up to N times",
    },
    "INFINITE_LOOP_HEARTBEAT_TIMEOUT": {
        "default": "0",
        "type": "int",
        "group": "timeouts",
        "label": "Heartbeat Timeout",
        "description": "Seconds of inactivity before session considered hung",
    },
    "INFINITE_LOOP_GIT": {
        "default": "false",
        "type": "bool",
        "group": "git",
        "label": "Git",
        "description": "Capture git diff stats per iteration",
    },
    "INFINITE_LOOP_GIT_COMMIT": {
        "default": "false",
        "type": "bool",
        "group": "git",
        "label": "Git Commit",
        "description": "Auto-commit changes per iteration",
    },
    "INFINITE_LOOP_STORE_GIT_DIFF": {
        "default": "false",
        "type": "bool",
        "group": "git",
        "label": "Store Git Diff",
        "description": "Store actual git diff in the ledger",
    },
    "INFINITE_LOOP_MAX_IDLE_ITERATIONS": {
        "default": "0",
        "type": "int",
        "group": "git",
        "label": "Max Idle Iterations",
        "description": "Stop after N iterations with no git changes",
    },
    "INFINITE_LOOP_GOALS_FILE": {
        "default": "",
        "type": "string",
        "group": "goals",
        "label": "Goals File",
        "description": "Path to file with one goal per line",
    },
    "INFINITE_LOOP_STOP_AT_GOALS_END": {
        "default": "false",
        "type": "bool",
        "group": "goals",
        "label": "Stop at Goals End",
        "description": "Stop when all goals exhausted",
    },
    "INFINITE_LOOP_TRACK_GOALS": {
        "default": "false",
        "type": "bool",
        "group": "goals",
        "label": "Track Goals",
        "description": "Track completed goals in the ledger",
    },
    "INFINITE_LOOP_RESET_GOALS": {
        "default": "false",
        "type": "bool",
        "group": "goals",
        "label": "Reset Goals",
        "description": "Clear goals_completed tracking",
    },
    "INFINITE_LOOP_COOLDOWN": {
        "default": "0",
        "type": "int",
        "group": "rate-limiting",
        "label": "Cooldown",
        "description": "Wait N seconds between iterations",
    },
    "INFINITE_LOOP_COOLDOWN_MODE": {
        "default": "fixed",
        "type": "select",
        "group": "rate-limiting",
        "label": "Cooldown Mode",
        "description": "Cooldown mode",
        "options": ["fixed", "adaptive"],
    },
    "INFINITE_LOOP_CONVERGENCE_STOP": {
        "default": "false",
        "type": "bool",
        "group": "convergence",
        "label": "Convergence Stop",
        "description": "Auto-stop on convergence detection",
    },
    "INFINITE_LOOP_CONVERGENCE_THRESHOLD": {
        "default": "0.9",
        "type": "float",
        "group": "convergence",
        "label": "Convergence Threshold",
        "description": "Similarity threshold (0.0-1.0)",
    },
    "INFINITE_LOOP_CONVERGENCE_WINDOW": {
        "default": "5",
        "type": "int",
        "group": "convergence",
        "label": "Convergence Window",
        "description": "Number of recent iterations to compare",
    },
    "INFINITE_LOOP_OUTPUT_SCHEMA": {
        "default": "",
        "type": "string",
        "group": "output",
        "label": "Output Schema",
        "description": "Inline JSON Schema for spawned output validation",
        "multiline": True,
    },
    "INFINITE_LOOP_OUTPUT_SCHEMA_FILE": {
        "default": "",
        "type": "string",
        "group": "output",
        "label": "Output Schema File",
        "description": "Path to JSON Schema file for output validation",
    },
    "INFINITE_LOOP_MAX_OUTPUT_CHARS": {
        "default": "2000",
        "type": "int",
        "group": "output",
        "label": "Max Output Chars",
        "description": "Max chars of spawned output to store",
    },
    "INFINITE_LOOP_SHUTDOWN_SENTINEL": {
        "default": "/tmp/infinite-loop-stop",
        "type": "string",
        "group": "sentinel",
        "label": "Shutdown Sentinel",
        "description": "Path to sentinel file for external control",
    },
    "INFINITE_LOOP_PROFILE": {
        "default": "",
        "type": "string",
        "group": "hermes",
        "label": "Profile",
        "description": "Hermes profile for spawned sessions",
    },
    "INFINITE_LOOP_MODEL": {
        "default": "",
        "type": "string",
        "group": "hermes",
        "label": "Model",
        "description": "Model override for spawned sessions",
    },
    "INFINITE_LOOP_PROVIDER": {
        "default": "",
        "type": "string",
        "group": "hermes",
        "label": "Provider",
        "description": "Provider override for spawned sessions",
    },
    "INFINITE_LOOP_WEBHOOK_PORT": {
        "default": "0",
        "type": "int",
        "group": "webhook",
        "label": "Webhook Port",
        "description": "Port for HTTP webhook server (0 = disabled)",
    },
    "INFINITE_LOOP_HTTP_CALLBACK": {
        "default": "",
        "type": "string",
        "group": "notifications",
        "label": "HTTP Callback",
        "description": "HTTP POST URL for iteration JSON",
    },
    "INFINITE_LOOP_NOTIFY_CMD": {
        "default": "",
        "type": "string",
        "group": "notifications",
        "label": "Notify Command",
        "description": "Shell command after each iteration",
    },
    "INFINITE_LOOP_ON_ERROR_CMD": {
        "default": "",
        "type": "string",
        "group": "notifications",
        "label": "On Error Command",
        "description": "Shell command when iteration fails",
    },
    "INFINITE_LOOP_NOTIFY_DESKTOP": {
        "default": "false",
        "type": "bool",
        "group": "notifications",
        "label": "Notify Desktop",
        "description": "Send desktop notifications via notify-send",
    },
    "INFINITE_LOOP_NOTIFY_ON_COMPLETION": {
        "default": "false",
        "type": "bool",
        "group": "notifications",
        "label": "Notify on Completion",
        "description": "Send summary notification on completion",
    },
    "INFINITE_LOOP_NOTIFY_PUSHBULLET": {
        "default": "",
        "type": "string",
        "group": "notifications",
        "label": "Notify Pushbullet",
        "description": "Pushbullet API access token",
    },
    "INFINITE_LOOP_NOTIFY_NTFY": {
        "default": "",
        "type": "string",
        "group": "notifications",
        "label": "Notify ntfy",
        "description": "ntfy topic name for push notifications",
    },
    "INFINITE_LOOP_NOTIFY_NTFY_SERVER": {
        "default": "https://ntfy.sh",
        "type": "string",
        "group": "notifications",
        "label": "Notify ntfy Server",
        "description": "ntfy server URL",
    },
    "INFINITE_LOOP_LOG_FILE": {
        "default": "",
        "type": "string",
        "group": "logging",
        "label": "Log File",
        "description": "Path to daemon log file",
    },
    "INFINITE_LOOP_LOG_MAX_MB": {
        "default": "10",
        "type": "int",
        "group": "logging",
        "label": "Log Max MB",
        "description": "Max log file size in MB before rotation",
    },
    "INFINITE_LOOP_STATUS_HTML": {
        "default": "",
        "type": "string",
        "group": "status",
        "label": "Status HTML",
        "description": "Path to static HTML dashboard",
    },
    "INFINITE_LOOP_STATUS_FILE": {
        "default": "",
        "type": "string",
        "group": "status",
        "label": "Status File",
        "description": "Path to JSON status file",
    },
    "INFINITE_LOOP_KEEP_ITERATIONS": {
        "default": "0",
        "type": "int",
        "group": "ledger",
        "label": "Keep Iterations",
        "description": "Auto-shrink ledger to last N iterations",
    },
    "INFINITE_LOOP_FORCE_RESET": {
        "default": "false",
        "type": "bool",
        "group": "ledger",
        "label": "Force Reset",
        "description": "Clear existing ledger and start fresh",
    },
    "INFINITE_LOOP_TAG": {
        "default": "",
        "type": "string",
        "group": "ledger",
        "label": "Tag",
        "description": "Label/identifier for the run",
    },
    "INFINITE_LOOP_ARCHIVE_DIR": {
        "default": "$HOME/.hermes/infinite-loop-archives",
        "type": "string",
        "group": "archiving",
        "label": "Archive Dir",
        "description": "Directory for archived iteration files",
    },
    "INFINITE_LOOP_ARCHIVE_RETENTION": {
        "default": "30",
        "type": "int",
        "group": "archiving",
        "label": "Archive Retention",
        "description": "Days to keep archived iterations",
    },
    "INFINITE_LOOP_ARCHIVE_MAX_SIZE": {
        "default": "0",
        "type": "int",
        "group": "archiving",
        "label": "Archive Max Size",
        "description": "Max archive directory size in MB",
    },
    "INFINITE_LOOP_WATCH_DIR": {
        "default": "",
        "type": "string",
        "group": "file-watcher",
        "label": "Watch Dir",
        "description": "Watch directory for file changes",
    },
    "INFINITE_LOOP_WATCH_POLL": {
        "default": "5.0",
        "type": "float",
        "group": "file-watcher",
        "label": "Watch Poll",
        "description": "File watcher poll interval in seconds",
    },
    "INFINITE_LOOP_WORKER_URL": {
        "default": "",
        "type": "string",
        "group": "worker",
        "label": "Worker URL",
        "description": "Hermes Worker URL. Empty = direct subprocess (live stdout streaming). 'auto' = embedded worker (buffered).",
    },
    "INFINITE_LOOP_USE_LIBRARY": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Use Library",
        "description": "Use AIAgent.run_conversation() in-process",
    },
    "INFINITE_LOOP_PASS_SESSION_ID": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Pass Session ID",
        "description": "Store session_id in the ledger",
    },
    "INFINITE_LOOP_CHECKPOINTS": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Checkpoints",
        "description": "Enable file checkpoints in spawned sessions",
    },
    "INFINITE_LOOP_RESUME": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Resume",
        "description": "Chain spawned sessions via --resume",
    },
    "INFINITE_LOOP_SKILLS": {
        "default": "",
        "type": "string",
        "group": "spawned",
        "label": "Skills",
        "description": "Skills to preload in spawned sessions",
    },
    "INFINITE_LOOP_IGNORE_RULES": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Ignore Rules",
        "description": "Start sessions without rules",
    },
    "INFINITE_LOOP_IGNORE_USER_CONFIG": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Ignore User Config",
        "description": "Skip ~/.hermes/config.yaml",
    },
    "INFINITE_LOOP_SPAWN_SOURCE": {
        "default": "infinite-loop",
        "type": "string",
        "group": "spawned",
        "label": "Spawn Source",
        "description": "Source tag for spawned sessions",
    },
    "INFINITE_LOOP_YOLO": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "YOLO",
        "description": "Bypass dangerous command approvals",
    },
    "INFINITE_LOOP_SAFE_MODE": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Safe Mode",
        "description": "Disable ALL customizations in sessions",
    },
    "INFINITE_LOOP_ACCEPT_HOOKS": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Accept Hooks",
        "description": "Auto-approve shell hooks",
    },
    "INFINITE_LOOP_WORKTREE": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Worktree",
        "description": "Run in isolated git worktree",
    },
    "INFINITE_LOOP_CONTINUE": {
        "default": "false",
        "type": "bool",
        "group": "spawned",
        "label": "Continue",
        "description": "Resume most recent session",
    },
    "INFINITE_LOOP_PROMPT_SUFFIX": {
        "default": "",
        "type": "string",
        "group": "prompt",
        "label": "Prompt Suffix",
        "description": "Extra text appended to every session prompt",
    },
    "INFINITE_LOOP_TASK_TYPE": {
        "default": "auto",
        "type": "select",
        "group": "prompt",
        "label": "Task Type",
        "description": "Force task type",
        "options": [
            "auto",
            "research",
            "code-fix",
            "code-build",
            "system-admin",
            "data-processing",
            "content",
            "general",
        ],
    },
    "INFINITE_LOOP_STARTUP_DELAY": {
        "default": "0.0",
        "type": "float",
        "group": "startup",
        "label": "Startup Delay",
        "description": "Wait N seconds before first iteration",
    },
    "INFINITE_LOOP_QUIET": {
        "default": "false",
        "type": "bool",
        "group": "startup",
        "label": "Quiet",
        "description": "Suppress verbose startup banner",
    },
    "INFINITE_LOOP_PREFLIGHT": {
        "default": "false",
        "type": "bool",
        "group": "startup",
        "label": "Preflight",
        "description": "Run preflight health checks",
    },
    "INFINITE_LOOP_PREFLIGHT_FAIL_FAST": {
        "default": "false",
        "type": "bool",
        "group": "startup",
        "label": "Preflight Fail Fast",
        "description": "Stop on first preflight failure",
    },
    "INFINITE_LOOP_DRY_RUN": {
        "default": "false",
        "type": "bool",
        "group": "startup",
        "label": "Dry Run",
        "description": "Print config and exit",
    },
    "INFINITE_LOOP_SELF_TEST": {
        "default": "false",
        "type": "bool",
        "group": "startup",
        "label": "Self Test",
        "description": "Run in-process self-tests",
    },
}


# Group definitions for the UI
CONFIG_GROUPS = [
    {"id": "core", "name": "Core Task", "icon": "target"},
    {"id": "iteration", "name": "Iteration Control", "icon": "repeat"},
    {"id": "parallelism", "name": "Parallelism", "icon": "layers"},
    {"id": "timeouts", "name": "Timeouts", "icon": "clock"},
    {"id": "git", "name": "Git Integration", "icon": "git-branch"},
    {"id": "goals", "name": "Goal File (Batch)", "icon": "list"},
    {"id": "rate-limiting", "name": "Rate Limiting", "icon": "pause-circle"},
    {"id": "convergence", "name": "Convergence Detection", "icon": "trending-down"},
    {"id": "output", "name": "Structured Output", "icon": "file-code"},
    {"id": "sentinel", "name": "Sentinel / Shutdown", "icon": "shield"},
    {"id": "hermes", "name": "Hermes Profile / Model", "icon": "cpu"},
    {"id": "notifications", "name": "Notifications", "icon": "bell"},
    {"id": "webhook", "name": "Webhook", "icon": "send"},
    {"id": "logging", "name": "Logging", "icon": "file-text"},
    {"id": "status", "name": "Status / Dashboard", "icon": "activity"},
    {"id": "ledger", "name": "Ledger Management", "icon": "database"},
    {"id": "archiving", "name": "Archiving", "icon": "archive"},
    {"id": "file-watcher", "name": "File Watcher", "icon": "eye"},
    {"id": "worker", "name": "Hermes Worker", "icon": "server"},
    {"id": "spawned", "name": "Spawned Session Flags", "icon": "terminal"},
    {"id": "prompt", "name": "Prompt Customization", "icon": "edit-3"},
    {"id": "startup", "name": "Startup", "icon": "play-circle"},
]


def read_json_config(path: str | None = None) -> dict[str, str]:
    """Read persisted JSON config. Returns empty dict if file doesn't exist."""
    target = path or CONFIG_PATH
    if not os.path.exists(target):
        return {}
    try:
        with open(target, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {
                k: str(v) for k, v in data.items() if k.startswith("INFINITE_LOOP_")
            }
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_json_config(config: dict[str, str], path: str | None = None) -> None:
    """Persist config dict as JSON."""
    target = path or CONFIG_PATH
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w") as f:
        json.dump(config, f, indent=2)


def get_config_with_defaults() -> dict[str, dict[str, Any]]:
    """Get full config schema with current values from persisted JSON."""
    current = read_json_config()
    result: dict[str, dict[str, Any]] = {}

    for key, meta in CONFIG_DEFAULTS.items():
        entry = dict(meta)
        entry["value"] = current.get(key, meta["default"])
        result[key] = entry

    return result


def get_raw_config() -> dict[str, str]:
    """Get raw key-value config, filling defaults for unset keys."""
    current = read_json_config()
    result: dict[str, str] = {}
    for key, meta in CONFIG_DEFAULTS.items():
        result[key] = current.get(key, meta["default"])
    return result


def build_cli_args(config: dict[str, str]) -> list[str]:
    """Build CLI argument list from config dict for launch-loop.py."""
    args: list[str] = []

    # String/int/float values
    str_flags = {
        "INFINITE_LOOP_GOAL": "--goal",
        "INFINITE_LOOP_CONTEXT": "--context",
        "INFINITE_LOOP_CONTEXT_FILE": "--context-file",
        "INFINITE_LOOP_TOOLSETS": "--toolsets",
        "INFINITE_LOOP_WORKDIR": "--workdir",
        "INFINITE_LOOP_MAX_ITERATIONS": "--max-iterations",
        "INFINITE_LOOP_MAX_TURNS": "--max-turns",
        "INFINITE_LOOP_COMPACT_EVERY": "--compact-every",
        "INFINITE_LOOP_WORKERS": "--workers",
        "INFINITE_LOOP_SESSION_TIMEOUT": "--session-timeout",
        "INFINITE_LOOP_RETRY_DELAY": "--retry-delay",
        "INFINITE_LOOP_MAX_RETRIES": "--max-retries",
        "INFINITE_LOOP_COOLDOWN": "--cooldown",
        "INFINITE_LOOP_COOLDOWN_MODE": "--cooldown-mode",
        "INFINITE_LOOP_MAX_OUTPUT_CHARS": "--max-output-chars",
        "INFINITE_LOOP_TAG": "--tag",
        "INFINITE_LOOP_PROFILE": "--profile",
        "INFINITE_LOOP_MODEL": "--model",
        "INFINITE_LOOP_PROVIDER": "--provider",
        "INFINITE_LOOP_SHUTDOWN_SENTINEL": "--shutdown-sentinel",
        "INFINITE_LOOP_LOG_FILE": "--log-file",
        "INFINITE_LOOP_LOG_MAX_MB": "--log-max-mb",
        "INFINITE_LOOP_STATUS_HTML": "--status-html",
        "INFINITE_LOOP_STATUS_FILE": "--status-file",
        "INFINITE_LOOP_GOALS_FILE": "--goals-file",
        "INFINITE_LOOP_WEBHOOK_PORT": "--webhook-port",
        "INFINITE_LOOP_WORKER_URL": "--worker-url",
        "INFINITE_LOOP_NOTIFY_CMD": "--notify-cmd",
        "INFINITE_LOOP_ON_ERROR_CMD": "--on-error-cmd",
        "INFINITE_LOOP_HTTP_CALLBACK": "--http-callback",
        "INFINITE_LOOP_NOTIFY_PUSHBULLET": "--notify-pushbullet",
        "INFINITE_LOOP_NOTIFY_NTFY": "--notify-ntfy",
        "INFINITE_LOOP_NOTIFY_NTFY_SERVER": "--notify-ntfy-server",
        "INFINITE_LOOP_SKILLS": "--skills",
        "INFINITE_LOOP_CONVERGENCE_THRESHOLD": "--convergence-threshold",
        "INFINITE_LOOP_CONVERGENCE_WINDOW": "--convergence-window",
        "INFINITE_LOOP_OUTPUT_SCHEMA": "--output-schema",
        "INFINITE_LOOP_OUTPUT_SCHEMA_FILE": "--output-schema-file",
        "INFINITE_LOOP_STARTUP_DELAY": "--startup-delay",
        "INFINITE_LOOP_PROMPT_SUFFIX": "--prompt-suffix",
        "INFINITE_LOOP_WATCH_DIR": "--watch-dir",
        "INFINITE_LOOP_WATCH_POLL": "--watch-poll",
        "INFINITE_LOOP_ARCHIVE_DIR": "--archive-dir",
        "INFINITE_LOOP_ARCHIVE_RETENTION": "--archive-retention",
        "INFINITE_LOOP_ARCHIVE_MAX_SIZE": "--archive-max-size",
        "INFINITE_LOOP_KEEP_ITERATIONS": "--keep-iterations",
        "INFINITE_LOOP_TASK_TYPE": "--task-type",
        "INFINITE_LOOP_HEARTBEAT_TIMEOUT": "--heartbeat-timeout",
        "INFINITE_LOOP_MAX_IDLE_ITERATIONS": "--max-idle-iterations",
        "INFINITE_LOOP_SPAWN_SOURCE": "--spawn-source",
    }

    for env_key, flag in str_flags.items():
        val = config.get(env_key, "")
        if val and val != CONFIG_DEFAULTS.get(env_key, {}).get("default", ""):
            args.extend([flag, val])

    # Boolean flags
    bool_flags = {
        "INFINITE_LOOP_EVOLVE": "--evolve",
        "INFINITE_LOOP_RUN": "--run",
        "INFINITE_LOOP_GIT": "--git",
        "INFINITE_LOOP_GIT_COMMIT": "--git-commit",
        "INFINITE_LOOP_STORE_GIT_DIFF": "--store-git-diff",
        "INFINITE_LOOP_NOTIFY_DESKTOP": "--notify-desktop",
        "INFINITE_LOOP_NOTIFY_ON_COMPLETION": "--notify-on-completion",
        "INFINITE_LOOP_CONVERGENCE_STOP": "--convergence-stop",
        "INFINITE_LOOP_QUIET": "--quiet",
        "INFINITE_LOOP_NO_AUTO_TOOLSETS": "--no-auto-toolsets",
        "INFINITE_LOOP_NO_FAILURE_LEARNING": "--no-failure-learning",
        "INFINITE_LOOP_STOP_AT_GOALS_END": "--stop-at-goals-end",
        "INFINITE_LOOP_TRACK_GOALS": "--track-goals",
        "INFINITE_LOOP_RESET_GOALS": "--reset-goals",
        "INFINITE_LOOP_USE_LIBRARY": "--use-library",
        "INFINITE_LOOP_PASS_SESSION_ID": "--pass-session-id",
        "INFINITE_LOOP_CHECKPOINTS": "--checkpoints",
        "INFINITE_LOOP_RESUME": "--resume",
        "INFINITE_LOOP_IGNORE_RULES": "--ignore-rules",
        "INFINITE_LOOP_IGNORE_USER_CONFIG": "--ignore-user-config",
        "INFINITE_LOOP_YOLO": "--yolo",
        "INFINITE_LOOP_SAFE_MODE": "--safe-mode",
        "INFINITE_LOOP_ACCEPT_HOOKS": "--accept-hooks",
        "INFINITE_LOOP_WORKTREE": "--worktree",
        "INFINITE_LOOP_CONTINUE": "--continue",
        "INFINITE_LOOP_PREFLIGHT": "--preflight",
        "INFINITE_LOOP_PREFLIGHT_FAIL_FAST": "--preflight-fail-fast",
        "INFINITE_LOOP_DRY_RUN": "--dry-run",
        "INFINITE_LOOP_SELF_TEST": "--self-test",
    }

    for env_key, flag in bool_flags.items():
        if config.get(env_key, "").lower() == "true":
            args.append(flag)

    return args
