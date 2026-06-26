"""Constants, paths, and defaults for the hermes_loop package."""

import os

# Paths
LEDGER_PATH = "/tmp/infinite-loop-state.json"
LOCK_PATH = "/tmp/infinite-loop-state.lock"
SENTINEL_PATH_DEFAULT = "/tmp/infinite-loop-stop"
STATUS_FILE_DEFAULT = ""  # no status file by default
HERMES_SESSION_TIMEOUT = 7200

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

_ERROR_THRESHOLDS = {
    "timeout": {"mild": 3, "moderate": 5, "stop": 8},
    "network": {"mild": 2, "moderate": 4, "stop": 6},
    "schema": {"mild": 3, "moderate": None, "stop": 5},
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
HEARTBEAT_DIR = "/tmp"
HEARTBEAT_PREFIX = "infinite-loop-heartbeat-"
HEARTBEAT_INTERVAL = 30  # seconds between heartbeat writes
HEARTBEAT_GRACE_FACTOR = 2.0  # grace = timeout * 2
HEARTBEAT_POLL_INTERVAL = 5  # daemon polling interval (seconds)
HEARTBEAT_KILL_GRACE = 5  # seconds between SIGTERM and SIGKILL

# Version
LAUNCH_LOOP_VERSION = "14.31.0"
