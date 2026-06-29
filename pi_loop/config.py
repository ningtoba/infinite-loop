"""Constants, paths, and defaults for the pi-loop package."""

import dataclasses
import os
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Unified path resolution
# ---------------------------------------------------------------------------
# All runtime file paths derive from PI_LOOP_DATA_DIR (default /tmp) so that
# a single env var override moves ledger, lock, sentinel, heartbeat dir,
# log file, etc. This is critical for:
#   - running multiple instances on the same host (different data dirs)
#   - deploying in containers where /tmp may not be writable or persistent
#   - switching between ephemeral (/tmp) and persistent data directories
# ---------------------------------------------------------------------------


def _get_data_dir() -> str:
    """Return the base data directory, respecting PI_LOOP_DATA_DIR env var."""
    return os.environ.get("PI_LOOP_DATA_DIR", "/tmp")


def _resolve_path(env_var: str, default_name: str) -> str:
    """Resolve a path from an optional specific env var, else data_dir + name.

    Priority:
      1. Specific env var (e.g. PI_LOOP_LEDGER_PATH) if set and non-empty
      2. os.path.join(PI_LOOP_DATA_DIR or /tmp, default_name)
    """
    explicit = os.environ.get(env_var, "")
    if explicit:
        return explicit
    return os.path.join(_get_data_dir(), default_name)


# Paths
LEDGER_PATH = _resolve_path("PI_LOOP_LEDGER_PATH", "infinite-loop-state.json")
LOCK_PATH = _resolve_path("PI_LOOP_LOCK_PATH", "infinite-loop-state.lock")
SENTINEL_PATH_DEFAULT = _resolve_path("PI_LOOP_SENTINEL_PATH", "infinite-loop-stop")
STATUS_FILE_DEFAULT = ""  # no status file by default
DEFAULT_LOG_FILE = _resolve_path("PI_LOOP_WEB_LOG", "infinite-loop-web.log")

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

# Convergence detection defaults
DEFAULT_CONVERGENCE_WINDOW = 5
DEFAULT_CONVERGENCE_THRESHOLD = 0.9

# Base toolsets
BASE_TOOLSETS = "terminal,file,delegation,web,skills,browser,memory,session_search,code_execution,todo,vision"

# Error severity and thresholds for automatic error recovery
_ERROR_SEVERITY = {
    "timeout": 4,
    "network": 3,
    "schema": 2,
    "unknown": 1,
    "heartbeat": 5,
}

_ERROR_THRESHOLDS: dict[str, dict[str, int | None]] = {
    "timeout": {"mild": 3, "moderate": 5, "stop": 8},
    # Network errors are typically transient (API downtime, rate limiting,
    # DNS flaps).  Never auto-stop for network — just keep backing off.
    "network": {"mild": 2, "moderate": 4, "stop": None},
    "schema": {"mild": 3, "moderate": None, "stop": 5},  # None = skip moderate level
    "unknown": {"mild": 3, "moderate": 5, "stop": 7},
    "heartbeat": {"mild": 3, "moderate": 5, "stop": 7},
}

# Task type auto-detection patterns
TASK_PATTERNS = {
    "research": {
        "keywords": [
            "research",
            "investigate",
            "find",
            "search",
            "learn",
            "study",
            "analyze",
            "explore",
            "discover",
            "look up",
            "what is",
            "how does",
            "compare",
            "survey",
            "literature",
            "paper",
            "article",
            "audit",
            "review",
            "identify",
            "gather",
            "collect",
            "monitor",
            "track",
            "trace",
            "determine",
            "understand",
            "evaluate",
            "assess",
        ],
        "extra_toolsets": ["search", "web"],
        "description": "Information gathering and analysis",
    },
    "code-fix": {
        "keywords": [
            "fix",
            "bug",
            "error",
            "crash",
            "broken",
            "issue",
            "repair",
            "patch",
            "debug",
            "lint",
            "type error",
            "test fails",
            "refactor",
            "rewrite",
            "clean up",
            "resolve",
            "correct",
            "address",
            "remediate",
            "mitigate",
            "workaround",
            "hotfix",
            "revert",
            "rollback",
            "restore",
            "recover",
            "cleanup",
            "rework",
            "revise",
            "reorganize",
        ],
        "extra_toolsets": ["code_execution", "vision"],
        "description": "Code debugging and repair",
    },
    "code-build": {
        "keywords": [
            "build",
            "create",
            "implement",
            "write",
            "develop",
            "add feature",
            "new module",
            "scaffold",
            "generate",
            "construct",
            "compose",
            "architect",
            "design",
            "prototype",
            "extend",
            "enhance",
            "improve",
            "upgrade",
            "migrate",
            "port",
            "integrate",
            "wire up",
            "hook up",
            "connect",
            "initialize",
            "bootstrap",
            "template",
            "boilerplate",
            "skeleton",
        ],
        "extra_toolsets": ["code_execution", "vision"],
        "description": "New code and feature development",
    },
    "system-admin": {
        "keywords": [
            "deploy",
            "configure",
            "setup",
            "install",
            "migrate",
            "backup",
            "restore",
            "monitor",
            "optimize",
            "tune",
            "audit",
            "check health",
            "maintenance",
            "upgrade",
            "update",
            "manage",
            "provision",
            "orchestrate",
            "automate",
            "schedule",
            "scale",
            "replicate",
            "synchronize",
            "distribute",
            "load balance",
            "failover",
            "remediate",
            "patch",
            "harden",
            "secure",
            "encrypt",
        ],
        "extra_toolsets": ["code_execution"],
        "description": "System administration and DevOps",
    },
    "data-processing": {
        "keywords": [
            "process",
            "transform",
            "convert",
            "parse",
            "extract",
            "load",
            "clean",
            "normalize",
            "aggregate",
            "compute",
            "calculate",
            "statistics",
            "analyze data",
            "report",
            "dataset",
            "csv",
            "json",
            "import",
            "export",
            "merge",
            "join",
            "split",
            "deduplicate",
            "validate",
            "sanitize",
            "scrub",
            "anonymize",
            "summarize",
            "enrich",
            "augment",
            "sort",
            "filter",
            "query",
        ],
        "extra_toolsets": ["code_execution"],
        "description": "Data processing and analysis",
    },
    "content": {
        "keywords": [
            "write",
            "document",
            "documentation",
            "readme",
            "blog",
            "post",
            "article",
            "report",
            "summary",
            "explain",
            "describe",
            "draft",
            "tutorial",
            "guide",
            "manual",
            "specification",
            "spec",
            "changelog",
            "release notes",
            "announcement",
            "newsletter",
            "whitepaper",
            "case study",
            "proposal",
            "presentation",
            "slides",
        ],
        "extra_toolsets": ["vision", "image_gen"],
        "description": "Content and documentation creation",
    },
}

# Heartbeat constants for session self-healing
HEARTBEAT_DIR = os.environ.get("PI_LOOP_HEARTBEAT_DIR", _get_data_dir())
HEARTBEAT_PREFIX = "infinite-loop-heartbeat-"
HEARTBEAT_INTERVAL = 30  # seconds between heartbeat writes
HEARTBEAT_GRACE_FACTOR = 2.0  # grace = timeout * 2
HEARTBEAT_POLL_INTERVAL = 5  # daemon polling interval (seconds)
HEARTBEAT_KILL_GRACE = 5  # seconds between SIGTERM and SIGKILL

# Version
VERSION = "14.39.0"


# ---------------------------------------------------------------------------
# LoopConfig — single-source-of-truth for run_loop parameters
# ---------------------------------------------------------------------------
# Encapsulates the 71 positional/keyword parameters that run_loop() previously
# accepted as a sprawling signature.  All callers build a LoopConfig once and
# pass it as the first argument (plus the mutable `state` dict).
#
# Use LoopConfig.from_args(argparse.Namespace) to construct from CLI flags.
# ---------------------------------------------------------------------------


@dataclass
class LoopConfig:
    """Configuration for a run_loop() invocation.

    Every parameter has a default so you can construct partial configs for
    testing.  Use ``from_args()`` to build a full config from CLI flags.
    """

    # ── Core ────────────────────────────────────────────────
    goal: str = ""
    context: str = ""
    workdir: str | None = None
    sentinel_path: str = SENTINEL_PATH_DEFAULT

    # ── Iteration Control ───────────────────────────────────
    max_iterations: int = 0
    max_idle_iterations: int = 0
    compact_every: int = 10
    evolve: bool = False
    convergence_stop: bool = False
    convergence_threshold: float = DEFAULT_CONVERGENCE_THRESHOLD
    convergence_window: int = DEFAULT_CONVERGENCE_WINDOW
    cooldown: int = 0
    cooldown_mode: str = "fixed"
    startup_delay: float = 0.0
    stop_at_goals_end: bool = False
    goals_file: str = ""
    track_goals: bool = False
    reset_goals: bool = False

    # ── Workers ─────────────────────────────────────────────
    workers: int = 1
    session_timeout: int = 7200
    max_turns: int = 500
    max_retries: int = 2
    retry_delay: int = 5
    max_output_chars: int = 2000
    profile: str = ""
    model: str = ""
    provider: str = ""
    prompt_suffix: str = ""
    no_tool_shortcut: bool = False
    auto_toolsets: bool = True
    failure_learning: bool = True
    skills: str = ""
    use_library: bool = False
    pass_session_id: bool = False
    checkpoints: bool = False
    resume: bool = False
    resume_session_id: str = ""
    continue_session: bool = False
    output_schema: dict | None = None

    # ── Git & Files ─────────────────────────────────────────
    git: bool = False
    git_commit: bool = False
    store_git_diff: bool = False
    worktree: bool = False
    watch_dir: str = ""
    watch_poll: float = 5.0

    # ── Notifications & Callbacks ───────────────────────────
    notify_cmd: str | None = None
    on_error_cmd: str | None = None
    notify_desktop: bool = False
    notify_on_completion: bool = False
    notify_pushbullet: str = ""
    notify_ntfy: str = ""
    notify_ntfy_server: str = "https://ntfy.sh"
    http_callback: str = ""
    http_callback_secret: str = ""

    # ── Dashboards & Status ─────────────────────────────────
    html_dashboard: str = ""
    status_file: str = ""
    webhook_port: int = 0

    # ── Archiving ───────────────────────────────────────────
    keep_iterations: int = 0
    archive_dir: str = ""
    archive_retention: int = 30
    archive_max_size: int = 0

    # ── Logging ─────────────────────────────────────────────
    quiet: bool = False
    json_logs: bool = False

    # ── Safety ──────────────────────────────────────────────
    safe_mode: bool = False
    yolo: bool = False
    ignore_rules: bool = False
    ignore_user_config: bool = False
    accept_hooks: bool = False
    spawn_source: str = ""
    tag: str = ""
    heartbeat_timeout: int = 0

    # ── Advanced ────────────────────────────────────────────
    force_reset: bool = False

    @classmethod
    def from_args(cls, args: Any) -> "LoopConfig":
        """Build a LoopConfig from an argparse.Namespace (or any object with
        matching attributes).  Unknown attributes on *args* are silently
        ignored; missing attributes fall back to the dataclass default."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        raw: dict[str, Any] = {name: getattr(args, name, None) for name in known}
        # Strip out attributes set to None that have a non-None default
        for f in cls.__dataclass_fields__.values():
            if (
                raw.get(f.name) is None
                and f.default is not None
                and not isinstance(f.default, dataclasses._MISSING_TYPE)
            ):  # type: ignore[attr-defined]
                raw[f.name] = f.default
        return cls(**raw)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access for backwards compatibility."""
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        """Allow .get() for backwards compatibility with dict access."""
        return getattr(self, key, default)
