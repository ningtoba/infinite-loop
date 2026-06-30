"""
env_utils — Environment variable validation, discovery, and loading.

Provides safe environment initialisation that does NOT require a .env file.
Loading order (last wins):
  1. omp_loop.config_file defaults (~/.config/omp-loop/config.json)
  2. .env file in CWD (if it exists — optional, no crash if missing)
  3. Existing os.environ values (never overwritten)
"""

import difflib
import os

from .color_utils import colorizer
from .file_utils import _log

# ── Known environment variables — canonical list ──────────────────────────────
# Sorted set of every INFINITE_LOOP_* variable that the daemon recognises.
# This MUST be kept in sync with .env.example and run.sh.
KNOWN_ENV_VARS: set[str] = {
    "INFINITE_LOOP_ACCEPT_HOOKS",
    "INFINITE_LOOP_ARCHIVE_DIR",
    "INFINITE_LOOP_ARCHIVE_MAX_SIZE",
    "INFINITE_LOOP_ARCHIVE_RETENTION",
    "INFINITE_LOOP_CHECKPOINTS",
    "INFINITE_LOOP_COMPACT_EVERY",
    "INFINITE_LOOP_CONFIG",
    "INFINITE_LOOP_CONTEXT",
    "INFINITE_LOOP_CONTEXT_FILE",
    "INFINITE_LOOP_CONTINUE",
    "INFINITE_LOOP_CONVERGENCE_STOP",
    "INFINITE_LOOP_CONVERGENCE_THRESHOLD",
    "INFINITE_LOOP_CONVERGENCE_WINDOW",
    "INFINITE_LOOP_COOLDOWN",
    "INFINITE_LOOP_COOLDOWN_MODE",
    "INFINITE_LOOP_DRY_RUN",
    "INFINITE_LOOP_DUMP_ENV",
    "INFINITE_LOOP_EVOLVE",
    "INFINITE_LOOP_FORCE_RESET",
    "INFINITE_LOOP_GIT",
    "INFINITE_LOOP_GIT_COMMIT",
    "INFINITE_LOOP_GOAL",
    "INFINITE_LOOP_GOALS_FILE",
    "INFINITE_LOOP_HEARTBEAT_TIMEOUT",
    "INFINITE_LOOP_HTTP_CALLBACK",
    "INFINITE_LOOP_IGNORE_RULES",
    "INFINITE_LOOP_IGNORE_USER_CONFIG",
    "INFINITE_LOOP_JSON_LOGS",
    "INFINITE_LOOP_KEEP_ITERATIONS",
    "INFINITE_LOOP_LOG_FILE",
    "INFINITE_LOOP_LOG_MAX_MB",
    "INFINITE_LOOP_MAX_IDLE_ITERATIONS",
    "INFINITE_LOOP_MAX_ITERATIONS",
    "INFINITE_LOOP_MAX_OUTPUT_CHARS",
    "INFINITE_LOOP_MAX_RETRIES",
    "INFINITE_LOOP_MAX_TURNS",
    "INFINITE_LOOP_MODEL",
    "INFINITE_LOOP_NOTIFY_CMD",
    "INFINITE_LOOP_NOTIFY_DESKTOP",
    "INFINITE_LOOP_NOTIFY_NTFY",
    "INFINITE_LOOP_NOTIFY_NTFY_SERVER",
    "INFINITE_LOOP_NOTIFY_ON_COMPLETION",
    "INFINITE_LOOP_NOTIFY_PUSHBULLET",
    "INFINITE_LOOP_NO_AUTO_TOOLSETS",
    "INFINITE_LOOP_NO_FAILURE_LEARNING",
    "INFINITE_LOOP_ON_ERROR_CMD",
    "INFINITE_LOOP_OUTPUT_SCHEMA",
    "INFINITE_LOOP_OUTPUT_SCHEMA_FILE",
    "INFINITE_LOOP_PASS_SESSION_ID",
    "INFINITE_LOOP_PREFLIGHT",
    "INFINITE_LOOP_PREFLIGHT_FAIL_FAST",
    "INFINITE_LOOP_PROFILE",
    "INFINITE_LOOP_PROMPT_SUFFIX",
    "INFINITE_LOOP_PROVIDER",
    "INFINITE_LOOP_QUIET",
    "INFINITE_LOOP_RESET_GOALS",
    "INFINITE_LOOP_RESUME",
    "INFINITE_LOOP_RETRY_DELAY",
    "INFINITE_LOOP_RUN",
    "INFINITE_LOOP_SAFE_MODE",
    "INFINITE_LOOP_SAVE_CONFIG",
    "INFINITE_LOOP_SELF_TEST",
    "INFINITE_LOOP_SESSION_TIMEOUT",
    "INFINITE_LOOP_SHUTDOWN_SENTINEL",
    "INFINITE_LOOP_SKILLS",
    "INFINITE_LOOP_SPAWN_SOURCE",
    "INFINITE_LOOP_STARTUP_DELAY",
    "INFINITE_LOOP_STATUS_FILE",
    "INFINITE_LOOP_STATUS_HTML",
    "INFINITE_LOOP_STOP_AT_GOALS_END",
    "INFINITE_LOOP_STORE_GIT_DIFF",
    "INFINITE_LOOP_TAG",
    "INFINITE_LOOP_TASK_TYPE",
    "INFINITE_LOOP_TOOLSETS",
    "INFINITE_LOOP_TRACK_GOALS",
    "INFINITE_LOOP_USE_LIBRARY",
    "INFINITE_LOOP_WATCH_DIR",
    "INFINITE_LOOP_WATCH_POLL",
    "INFINITE_LOOP_WEBHOOK_PORT",
    "INFINITE_LOOP_WORKDIR",
    "INFINITE_LOOP_WORKERS",
    "INFINITE_LOOP_WORKER_URL",
    "INFINITE_LOOP_WORKTREE",
    "INFINITE_LOOP_YOLO",
}

# Deprecated / removed variables — warn when found
DEPRECATED_ENV_VARS: set[str] = set()

# Internal / non-config env vars that are expected but not user-settable
INTERNAL_ENV_VARS: set[str] = set()

# ── Sensible defaults for every known env var ─────────────────────────────────
# Used when no source (config file, .env, os.environ) provides a value.
SENSIBLE_DEFAULTS: dict[str, str] = {
    "INFINITE_LOOP_GOAL": "",
    "INFINITE_LOOP_GOALS_FILE": "",
    "INFINITE_LOOP_RUN": "false",
    "INFINITE_LOOP_DRY_RUN": "false",
    "INFINITE_LOOP_JSON_LOGS": "false",
    "INFINITE_LOOP_QUIET": "false",
    "INFINITE_LOOP_CONTINUE": "false",
    "INFINITE_LOOP_RESUME": "false",
    "INFINITE_LOOP_FORCE_RESET": "false",
    "INFINITE_LOOP_GIT": "false",
    "INFINITE_LOOP_GIT_COMMIT": "false",
    "INFINITE_LOOP_YOLO": "false",
    "INFINITE_LOOP_SAFE_MODE": "false",
    "INFINITE_LOOP_NO_AUTO_TOOLSETS": "false",
    "INFINITE_LOOP_NO_FAILURE_LEARNING": "false",
    "INFINITE_LOOP_PREFLIGHT": "false",
    "INFINITE_LOOP_PREFLIGHT_FAIL_FAST": "false",
    "INFINITE_LOOP_SELF_TEST": "false",
    "INFINITE_LOOP_DUMP_ENV": "false",
    "INFINITE_LOOP_SAVE_CONFIG": "false",
    "INFINITE_LOOP_STOP_AT_GOALS_END": "false",
    "INFINITE_LOOP_STORE_GIT_DIFF": "false",
    "INFINITE_LOOP_TRACK_GOALS": "false",
    "INFINITE_LOOP_RESET_GOALS": "false",
    "INFINITE_LOOP_PASS_SESSION_ID": "false",
    "INFINITE_LOOP_USE_LIBRARY": "false",
    "INFINITE_LOOP_EVOLVE": "false",
    "INFINITE_LOOP_COOLDOWN": "30",
    "INFINITE_LOOP_COOLDOWN_MODE": "none",
    "INFINITE_LOOP_RETRY_DELAY": "5",
    "INFINITE_LOOP_MAX_ITERATIONS": "100",
    "INFINITE_LOOP_MAX_IDLE_ITERATIONS": "5",
    "INFINITE_LOOP_MAX_RETRIES": "3",
    "INFINITE_LOOP_MAX_TURNS": "20",
    "INFINITE_LOOP_MAX_OUTPUT_CHARS": "10000",
    "INFINITE_LOOP_SESSION_TIMEOUT": "300",
    "INFINITE_LOOP_HEARTBEAT_TIMEOUT": "30",
    "INFINITE_LOOP_STARTUP_DELAY": "0",
    "INFINITE_LOOP_WORKERS": "1",
    "INFINITE_LOOP_WORKER_URL": "",
    "INFINITE_LOOP_WORKDIR": "",
    "INFINITE_LOOP_CONTEXT": "",
    "INFINITE_LOOP_CONTEXT_FILE": "",
    "INFINITE_LOOP_MODEL": "",
    "INFINITE_LOOP_PROVIDER": "",
    "INFINITE_LOOP_PROMPT_SUFFIX": "",
    "INFINITE_LOOP_TAG": "",
    "INFINITE_LOOP_TASK_TYPE": "",
    "INFINITE_LOOP_PROFILE": "",
    "INFINITE_LOOP_LOG_FILE": "",
    "INFINITE_LOOP_LOG_MAX_MB": "10",
    "INFINITE_LOOP_STATUS_FILE": "",
    "INFINITE_LOOP_STATUS_HTML": "",
    "INFINITE_LOOP_IGNORE_RULES": "",
    "INFINITE_LOOP_IGNORE_USER_CONFIG": "false",
    "INFINITE_LOOP_SKILLS": "",
    "INFINITE_LOOP_TOOLSETS": "",
    "INFINITE_LOOP_ACCEPT_HOOKS": "",
    "INFINITE_LOOP_ON_ERROR_CMD": "",
    "INFINITE_LOOP_HTTP_CALLBACK": "",
    "INFINITE_LOOP_NOTIFY_CMD": "",
    "INFINITE_LOOP_NOTIFY_DESKTOP": "false",
    "INFINITE_LOOP_NOTIFY_NTFY": "",
    "INFINITE_LOOP_NOTIFY_NTFY_SERVER": "",
    "INFINITE_LOOP_NOTIFY_ON_COMPLETION": "false",
    "INFINITE_LOOP_NOTIFY_PUSHBULLET": "",
    "INFINITE_LOOP_WATCH_DIR": "",
    "INFINITE_LOOP_WATCH_POLL": "2",
    "INFINITE_LOOP_WEBHOOK_PORT": "0",
    "INFINITE_LOOP_WORKTREE": "false",
    "INFINITE_LOOP_CHECKPOINTS": "",
    "INFINITE_LOOP_COMPACT_EVERY": "0",
    "INFINITE_LOOP_KEEP_ITERATIONS": "50",
    "INFINITE_LOOP_CONVERGENCE_STOP": "false",
    "INFINITE_LOOP_CONVERGENCE_THRESHOLD": "0",
    "INFINITE_LOOP_CONVERGENCE_WINDOW": "5",
    "INFINITE_LOOP_ARCHIVE_DIR": "",
    "INFINITE_LOOP_ARCHIVE_MAX_SIZE": "0",
    "INFINITE_LOOP_ARCHIVE_RETENTION": "7",
    "INFINITE_LOOP_SHUTDOWN_SENTINEL": "",
    "INFINITE_LOOP_SPAWN_SOURCE": "",
    "INFINITE_LOOP_OUTPUT_SCHEMA": "",
    "INFINITE_LOOP_OUTPUT_SCHEMA_FILE": "",
    "INFINITE_LOOP_CONFIG": "",
}


# ---------------------------------------------------------------------------
# Public API: load_env  — safe, no-crash environment initialisation
# ---------------------------------------------------------------------------


def load_env(
    env_path: str | None = None,
) -> dict[str, str]:
    """Load environment variables from available sources without crashing.

    Resolution order (last wins):
        1. IN-MEMORY os.environ — never overwritten
        2. ``omp_loop.config_file``  — ``~/.config/omp-loop/config.json`` (optional)
        3. ``.env`` file in CWD  — ``.env`` (optional, no crash if missing)
        4. Sensible defaults — final fallback for any unset known var

    Args:
        env_path: Path to a ``.env`` file.  Defaults to ``.env`` in CWD.

    Returns:
        A dict of all known env vars with their resolved values (as seen
        in ``os.environ`` after loading).
    """
    if env_path is None:
        env_path = os.path.join(os.getcwd(), ".env")

    # ── Step 1: config_file defaults (optional) ─────────────────────────
    _try_load_config_file()

    # ── Step 2: .env file (optional) ────────────────────────────────────
    if os.path.isfile(env_path):
        vars_from_env, _errors = parse_env_vars_from_file(env_path)
        # .env values fill in gaps (don't override already-set os.environ)
        for key, val in vars_from_env.items():
            os.environ.setdefault(key, val)

    # ── Step 3: sensible defaults for every known var ───────────────────
    for key, val in SENSIBLE_DEFAULTS.items():
        os.environ.setdefault(key, val)

    # Return a snapshot of all known vars
    return {key: os.environ.get(key, "") for key in KNOWN_ENV_VARS}


def _try_load_config_file() -> None:
    """Try to load config_file defaults into ``os.environ`` (no-op on failure)."""
    try:
        from . import config_file  # type: ignore[import-untyped]

        cfg = config_file.load_config()
        for key, val in cfg.items():
            # Normalise to the INFINITE_LOOP_ prefix pattern if needed
            env_key = key.upper() if key.startswith("INFINITE_LOOP_") else key
            if val is not None:
                os.environ.setdefault(env_key, str(val))
    except (ImportError, AttributeError, OSError, ValueError, Exception):
        # config_file module may not exist yet (fresh install) or may fail
        # to read its JSON — safe to ignore.
        pass


# ---------------------------------------------------------------------------
# Existing public API  (unchanged from original)
# ---------------------------------------------------------------------------


def _find_closest_match(name: str, candidates: set[str], cutoff: float = 0.6) -> str | None:
    """Return the closest known env var name, or None if below cutoff.

    Compares only the suffix (after the INFINITE_LOOP_ prefix) to avoid
    false positives from the shared prefix boosting unrelated names.
    """
    prefix = "INFINITE_LOOP_"
    if not name.startswith(prefix):
        return None

    suffix = name[len(prefix) :]
    if not suffix:
        return None

    best_match = None
    best_ratio = 0.0

    for candidate in candidates:
        if not candidate.startswith(prefix):
            continue
        cand_suffix = candidate[len(prefix) :]
        ratio = difflib.SequenceMatcher(None, suffix, cand_suffix).ratio()
        if ratio > best_ratio and ratio >= cutoff:
            best_ratio = ratio
            best_match = candidate

    return best_match


def parse_env_vars_from_file(env_path: str) -> tuple[dict[str, str], list[str]]:
    """Parse a .env file, returning (vars, errors).

    Each non-empty, non-comment line is parsed as KEY=VALUE.
    Errors are lines that could not be parsed (no '=' sign, etc.).
    Returns ({{}}, []) if the file does not exist — **does not crash**.
    """
    if not os.path.isfile(env_path):
        return {}, []  # ← no crash, just empty

    vars_found: dict[str, str] = {}
    errors: list[str] = []

    try:
        with open(env_path) as fh:
            for line_no, raw_line in enumerate(fh, 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                # Skip purely structural comment markers that look like env vars
                if line.startswith("---") or line.startswith("```"):
                    continue

                if "=" not in line:
                    errors.append(f"Line {line_no}: No '=' found in '{line}'")
                    continue

                key, _, val = line.partition("=")
                key = key.strip()
                # Handle quoted values (basic shlex-like split)
                if val:
                    val = val.strip().strip('"').strip("'")
                if not key:
                    errors.append(f"Line {line_no}: Empty key in '{raw_line.strip()}'")
                    continue
                vars_found[key] = val
    except OSError as exc:
        return {}, [f"Cannot open file: {exc}"]

    return vars_found, errors


def validate_env_vars(
    vars_found: dict[str, str],
) -> list[dict]:
    """Validate a dict of env vars against the known set.

    Each result dict has keys: type, key, message, suggestion
    type is one of: ok, unknown, typo, deprecated, warning, missing
    """
    results: list[dict] = []

    for key in sorted(vars_found.keys()):
        if not key.startswith("INFINITE_LOOP_"):
            results.append(
                {
                    "type": "warning",
                    "key": key,
                    "message": "Non-INFINITE_LOOP_ variable (not consumed by daemon)",
                    "suggestion": None,
                }
            )
            continue

        if key in KNOWN_ENV_VARS:
            results.append(
                {
                    "type": "ok",
                    "key": key,
                    "message": f"Recognized, value={_mask_sensitive(key, vars_found[key])}",
                    "suggestion": None,
                }
            )
        elif key in DEPRECATED_ENV_VARS:
            results.append(
                {
                    "type": "deprecated",
                    "key": key,
                    "message": "Deprecated — variable is no longer used",
                    "suggestion": None,
                }
            )
        else:
            # Unknown — check for typo similarity
            closest = _find_closest_match(key, KNOWN_ENV_VARS)
            if closest:
                results.append(
                    {
                        "type": "typo",
                        "key": key,
                        "message": f"Unknown variable — did you mean '{closest}'?",
                        "suggestion": closest,
                    }
                )
            else:
                results.append(
                    {
                        "type": "unknown",
                        "key": key,
                        "message": "Unknown variable — not recognized by the daemon",
                        "suggestion": None,
                    }
                )

    # Report missing known vars that are commonly needed
    common_required = {"INFINITE_LOOP_GOAL"}
    missing_common = common_required - set(vars_found.keys())
    for key in sorted(missing_common):
        results.append(
            {
                "type": "missing",
                "key": key,
                "message": "Not set — required unless --goal is passed as CLI flag",
                "suggestion": (key.lower().replace("infinite_loop_", "") if key.startswith("INFINITE_LOOP_") else None),
            }
        )

    return results


def _mask_sensitive(key: str, value: str) -> str:
    """Mask sensitive values (tokens, keys) for display."""
    sensitive_patterns = ("TOKEN", "KEY", "SECRET", "PASSWORD", "PUSHBULLET")
    if any(p in key.upper() for p in sensitive_patterns):
        if not value:
            return "****"
        if len(value) <= 4:
            return "****"
        # Keep only first 2 and last 2 chars; replace the middle with ****
        if len(value) <= 8:
            return value[:2] + "****" + value[-2:]
        return value[:3] + "****" + value[-3:]
    return value


def format_validation_results(results: list[dict], colorize: bool = True) -> str:
    """Format validation results for display."""

    lines: list[str] = []
    counts: dict[str, int] = {}

    for r in results:
        t = r["type"]
        counts[t] = counts.get(t, 0) + 1

        if colorize:
            if t == "ok":
                prefix = colorizer.tag_ok() + " [OK]"
            elif t == "typo":
                prefix = colorizer.tag_warn() + " [TYPO]"
            elif t == "unknown":
                prefix = colorizer.tag_warn() + " [UNKNOWN]"
            elif t == "deprecated":
                prefix = colorizer.tag_warn() + " [DEPRECATED]"
            elif t == "warning":
                prefix = colorizer.tag_warn() + " [WARN]"
            elif t == "missing":
                prefix = colorizer.tag_warn() + " [MISSING]"
            else:
                prefix = f"[{t.upper()}]"
        else:
            prefix = f"[{t.upper()}]"

        line = f"  {prefix} {r['key']}"
        line += f"  {r['message']}"
        if r.get("suggestion"):
            line += f"  → {r['suggestion']}"
        lines.append(line)

    summary_parts: list[str] = []
    summary_parts.append(f"{counts.get('ok', 0)} recognized")
    problems = sum(counts.get(t, 0) for t in ("typo", "unknown", "deprecated", "warning", "missing"))
    if problems > 0:
        summary_parts.append(f"{problems} issue{'s' if problems != 1 else ''}")
        for t, label in [
            ("typo", "typos"),
            ("unknown", "unknown"),
            ("deprecated", "deprecated"),
            ("warning", "warnings"),
            ("missing", "missing"),
        ]:
            c = counts.get(t, 0)
            if c:
                summary_parts.append(f"  {c} {label}")
    summary_parts.append(f"total: {len(results)} vars")

    header = (
        "Environment Variable Validation:\n"
        if not colorize
        else f"  {colorizer.header('Environment Variable Validation:')}"
    )
    lines.insert(0, header)
    lines.append(f"  {'─' * 50}")
    lines.append(f"  {' | '.join(summary_parts)}")

    return "\n".join(lines)


def check_env_file(env_path: str | None = None) -> int:
    """Validate a .env file and print results. Returns exit code (0=OK, 1=issues).

    **Does not crash** if the file is missing — logs an info message and
    exits cleanly (code 0).
    """

    if env_path is None:
        env_path = os.path.join(os.getcwd(), ".env")

    if not os.path.isfile(env_path):
        _log(f"[INFO] No .env file at {env_path} — skipping validation.")
        _log("[INFO] All env vars will use sensible defaults.")
        return 0

    vars_found, parse_errors = parse_env_vars_from_file(env_path)

    if parse_errors:
        _log("[WARN] Parse errors in .env file:")
        for err in parse_errors:
            _log(f"  {err}")

    if not vars_found and not parse_errors:
        _log(f"[INFO] No INFINITE_LOOP_* variables found in {env_path}")
        _log("[INFO] .env file exists but may be empty or use default values.")
        return 0

    results = validate_env_vars(vars_found)
    output = format_validation_results(results, colorize=True)
    print(output)

    has_issues = any(r["type"] in ("typo", "unknown", "deprecated", "warning") for r in results)
    return 1 if has_issues else 0
