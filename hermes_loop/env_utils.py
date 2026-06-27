"""
env_utils — Environment variable validation and discovery.

Validates .env files against the canonical set of known INFINITE_LOOP_*
environment variables. Detects typos, unknown variables, and suggests
the closest match for misspelled variable names.
"""

import difflib
import os

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


def _find_closest_match(
    name: str, candidates: set[str], cutoff: float = 0.6
) -> str | None:
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
    """
    if not os.path.isfile(env_path):
        return {}, [f"File not found: {env_path}"]

    vars_found: dict[str, str] = {}
    errors: list[str] = []

    with open(env_path) as f:
        for line_no, raw_line in enumerate(f, 1):
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
                "suggestion": (
                    key.lower().replace("infinite_loop_", "")
                    if key.startswith("INFINITE_LOOP_")
                    else None
                ),
            }
        )

    return results


def _mask_sensitive(key: str, value: str) -> str:
    """Mask sensitive values (tokens, keys) for display."""
    sensitive_patterns = ("TOKEN", "KEY", "SECRET", "PASSWORD", "PUSHBULLET")
    if any(p in key.upper() for p in sensitive_patterns):
        if len(value) > 8:
            return value[:4] + "****" + value[-4:]
        return "****"
    return value


def format_validation_results(results: list[dict], colorize: bool = True) -> str:
    """Format validation results for display."""
    from .color_utils import colorizer

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
    problems = sum(
        counts.get(t, 0)
        for t in ("typo", "unknown", "deprecated", "warning", "missing")
    )
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
    """Validate a .env file and print results. Returns exit code (0=OK, 1=issues)."""
    from .file_utils import _log

    if env_path is None:
        env_path = os.path.join(os.getcwd(), ".env")

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

    has_issues = any(
        r["type"] in ("typo", "unknown", "deprecated", "warning") for r in results
    )
    return 1 if has_issues else 0
