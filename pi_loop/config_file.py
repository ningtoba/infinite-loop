import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "pi-loop"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS = {
    "INFINITE_LOOP_GOAL": "",
    "INFINITE_LOOP_GOAL_DIR": str(Path.cwd()),
    "INFINITE_LOOP_RUN": "false",
    "INFINITE_LOOP_DRY_RUN": "false",
    "INFINITE_LOOP_JSON_LOGS": "false",
    "INFINITE_LOOP_WATCH": "false",
    "INFINITE_LOOP_WATCH_DIR": "",
    "INFINITE_LOOP_MAX_ITERATIONS": "100",
    "INFINITE_LOOP_TIMEOUT": "600",
    "INFINITE_LOOP_LOG_LEVEL": "INFO",
    "INFINITE_LOOP_PI_MODEL": "",
    "INFINITE_LOOP_ARCHIVE_ENABLED": "false",
    "INFINITE_LOOP_ARCHIVE_DIR": "",
    "INFINITE_LOOP_NOTIFICATION_ENABLED": "false",
    "INFINITE_LOOP_NOTIFICATION_URL": "",
    "INFINITE_LOOP_HEARTBEAT_ENABLED": "false",
    "INFINITE_LOOP_WEB_PORT": "8000",
    "INFINITE_LOOP_SESSION_TIMEOUT": "120",
}


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    ensure_config_dir()
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH) as f:
            return {**DEFAULTS, **json.load(f)}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save_config(config):
    ensure_config_dir()
    merged = {**DEFAULTS, **config}
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(merged, f, indent=2)
    except OSError as e:
        logger.warning("Failed to write config to %s: %s", CONFIG_PATH, e)
    return merged


def get(key):
    return load_config().get(key, DEFAULTS.get(key, ""))


def get_bool(key):
    return get(key).lower() in ("true", "1", "yes")


def apply_to_environ(config=None):
    if config is None:
        config = load_config()
    for key, value in config.items():
        if value is not None:
            os.environ.setdefault(key, str(value))
