"""Argument parser factory — single-sourced parser for both CLI and introspection.

Extracted from cli.py to break the circular import:
  cli.py → help_topics.py → cli._create_parser

Both modules now import _create_parser from here instead.
"""

import argparse

from .config import (
    BASE_TOOLSETS,
    DEFAULT_CONVERGENCE_THRESHOLD,
    DEFAULT_CONVERGENCE_WINDOW,
    SENTINEL_PATH_DEFAULT,
)


def _create_parser(for_introspection: bool = False) -> argparse.ArgumentParser:
    """Create and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="pi-loop",
        description="pi-loop — Autonomous task automation daemon that watches files, runs tasks, and tracks progress in a JSON ledger.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=not for_introspection,
        epilog="""
Examples:
  pi-loop --goal "Fix all lint errors" --run
  pi-loop --goal "Refactor auth module" --git --git-commit --run
  pi-loop --goals-file goals.txt --workers 3 --run
  pi-loop --preflight
  pi-loop --status

See 'pi-loop --examples' for more usage patterns.
        """,
    )

    # ── Core ───────────────────────────────────────────────
    core = parser.add_argument_group("Core")
    core.add_argument(
        "--goal",
        type=str,
        default="",
        help="The task goal string for each spawned worker",
    )
    core.add_argument("--context", type=str, default="", help="Context/instructions for the worker")
    core.add_argument("--context-file", type=str, default="", help="File to read context from")
    core.add_argument(
        "--goals-file",
        type=str,
        default="",
        help="File with one goal per line (optional profile|model|provider)",
    )
    core.add_argument(
        "--stop-at-goals-end",
        action="store_true",
        help="Stop when goals file is exhausted",
    )

    # ── Iteration Control ──────────────────────────────────
    iter_group = parser.add_argument_group("Iteration Control")
    iter_group.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Maximum iterations (0 = unlimited)",
    )
    iter_group.add_argument(
        "--max-idle-iterations",
        type=int,
        default=0,
        help="Stop after N iterations with no changes (0 = off)",
    )
    iter_group.add_argument(
        "--compact-every",
        type=int,
        default=10,
        help="Compact summaries every N iterations",
    )
    iter_group.add_argument(
        "--evolve",
        action="store_true",
        help="Auto-evolve the goal after each iteration",
    )
    iter_group.add_argument(
        "--convergence-stop",
        action="store_true",
        help="Stop when iterations converge (repetitive)",
    )
    iter_group.add_argument(
        "--convergence-threshold",
        type=float,
        default=DEFAULT_CONVERGENCE_THRESHOLD,
        help=f"Convergence similarity threshold (default: {DEFAULT_CONVERGENCE_THRESHOLD})",
    )
    iter_group.add_argument(
        "--convergence-window",
        type=int,
        default=DEFAULT_CONVERGENCE_WINDOW,
        help=f"Number of iterations to compare (default: {DEFAULT_CONVERGENCE_WINDOW})",
    )

    # ── Parallel & Timeout ─────────────────────────────────
    parallel = parser.add_argument_group("Parallel & Timeout")
    parallel.add_argument("--workers", type=int, default=1, help="Number of parallel workers (default: 1)")
    parallel.add_argument(
        "--session-timeout",
        type=int,
        default=7200,
        help="Worker timeout in seconds (default: 7200)",
    )
    parallel.add_argument("--max-turns", type=int, default=500, help="Max turns per worker (default: 500)")
    parallel.add_argument("--max-retries", type=int, default=0, help="Retry count on worker failure")
    parallel.add_argument("--retry-delay", type=int, default=5, help="Delay between retries in seconds")
    parallel.add_argument("--cooldown", type=int, default=0, help="Cooldown between iterations in seconds")
    parallel.add_argument(
        "--cooldown-mode",
        type=str,
        default="fixed",
        choices=["fixed", "adaptive"],
        help="Cooldown mode (default: fixed)",
    )
    parallel.add_argument(
        "--startup-delay",
        type=float,
        default=0.0,
        help="Delay before first iteration in seconds",
    )

    # ── Worker Model ───────────────────────────────────────
    worker = parser.add_argument_group("Worker Model")
    worker.add_argument("--model", type=str, default="", help="Model name for workers")
    worker.add_argument("--profile", type=str, default="", help="Worker profile")
    worker.add_argument("--provider", type=str, default="", help="Worker provider")
    worker.add_argument(
        "--toolsets",
        type=str,
        default=BASE_TOOLSETS,
        help=f"Comma-separated toolsets (default: {BASE_TOOLSETS})",
    )
    worker.add_argument("--no-auto-toolsets", action="store_true", help="Disable auto toolset detection")
    worker.add_argument(
        "--prompt-suffix",
        type=str,
        default="",
        help="Suffix appended to every worker prompt",
    )
    worker.add_argument("--skills", type=str, default="", help="Skills to enable for workers")
    worker.add_argument(
        "--max-output-chars",
        type=int,
        default=2000,
        help="Max chars of spawned output to store (default: 2000)",
    )
    worker.add_argument(
        "--output-schema",
        type=str,
        default="",
        help="JSON schema to validate worker output",
    )
    worker.add_argument("--output-schema-file", type=str, default="", help="File containing JSON schema")
    worker.add_argument(
        "--pass-session-id",
        action="store_true",
        help="Pass session ID between iterations",
    )
    worker.add_argument("--resume", action="store_true", help="Resume a chained session")
    worker.add_argument(
        "--continue-session",
        action="store_true",
        help="Continue the previous session (--resume alias)",
    )
    worker.add_argument(
        "--use-library",
        action="store_true",
        help="Use in-process execution instead of subprocess",
    )

    # ── Git & File Tracking ────────────────────────────────
    git_group = parser.add_argument_group("Git & File Tracking")
    git_group.add_argument("--git", action="store_true", help="Track git diff stats in the ledger")
    git_group.add_argument("--git-commit", action="store_true", help="Auto-commit after each iteration")
    git_group.add_argument("--store-git-diff", action="store_true", help="Store full git diff in ledger")
    git_group.add_argument("--worktree", action="store_true", help="Use git worktrees for parallel workers")
    git_group.add_argument("--workdir", type=str, default="", help="Working directory for workers")
    git_group.add_argument("--watch-dir", type=str, default="", help="Directory to watch for file changes")
    git_group.add_argument(
        "--watch-poll",
        type=float,
        default=5.0,
        help="File watch poll interval in seconds",
    )

    # ── Notifications ──────────────────────────────────────
    notif = parser.add_argument_group("Notifications")
    notif.add_argument(
        "--notify-desktop",
        action="store_true",
        help="Send desktop notifications via notify-send",
    )
    notif.add_argument(
        "--notify-on-completion",
        action="store_true",
        help="Send notification on daemon completion",
    )
    notif.add_argument(
        "--notify-cmd",
        type=str,
        default="",
        help="Shell command to run after each iteration",
    )
    notif.add_argument(
        "--on-error-cmd",
        type=str,
        default="",
        help="Shell command to run on iteration error",
    )
    notif.add_argument(
        "--allow-error-metachars",
        action="store_true",
        default=False,
        help="Allow shell metacharacters (; | ` $ & > <) in --on-error-cmd (security risk)",
    )
    notif.add_argument(
        "--notify-pushbullet",
        type=str,
        default="",
        help="PushBullet API token for notifications",
    )
    notif.add_argument(
        "--notify-ntfy",
        type=str,
        default="",
        help="ntfy.sh topic for push notifications",
    )
    notif.add_argument(
        "--notify-ntfy-server",
        type=str,
        default="https://ntfy.sh",
        help="ntfy.sh server URL",
    )

    # ── Dashboard & Status ─────────────────────────────────
    dash = parser.add_argument_group("Dashboard & Status")
    dash.add_argument("--status-html", type=str, default="", help="Path for live HTML dashboard file")
    dash.add_argument("--status-file", type=str, default="", help="Path for JSON status file")
    dash.add_argument(
        "--webhook-port",
        type=int,
        default=0,
        help="Port for webhook-triggered iterations (0=off)",
    )

    # ── HTTP Callbacks ─────────────────────────────────────
    http = parser.add_argument_group("HTTP Callbacks")
    http.add_argument("--http-callback", type=str, default="", help="URL to POST iteration results to")
    http.add_argument(
        "--http-callback-secret",
        type=str,
        default="",
        help="Authorization header for callback",
    )

    # ── Archiving ──────────────────────────────────────────
    archive = parser.add_argument_group("Archiving")
    archive.add_argument(
        "--keep-iterations",
        type=int,
        default=0,
        help="Keep only last N iterations in ledger (0=keep all)",
    )
    archive.add_argument("--archive-dir", type=str, default="", help="Directory for archived iterations")
    archive.add_argument(
        "--archive-retention",
        type=int,
        default=30,
        help="Days to keep archived iterations (default: 30)",
    )
    archive.add_argument(
        "--archive-max-size",
        type=int,
        default=0,
        help="Max archive size in MB (0=unlimited)",
    )

    # ── Logging ────────────────────────────────────────────
    log_group = parser.add_argument_group("Logging")
    log_group.add_argument("--log-file", type=str, default="", help="Path for daemon log file")
    log_group.add_argument(
        "--log-max-mb",
        type=int,
        default=10,
        help="Max log file size in MB before rotation",
    )
    log_group.add_argument("--json-logs", action="store_true", help="Output structured JSON logs to stdout")
    log_group.add_argument("--quiet", action="store_true", help="Minimal log output during loop")
    log_group.add_argument(
        "--color",
        type=str,
        default="auto",
        choices=["auto", "always", "never"],
        help="Color mode (auto/always/never)",
    )

    # ── Safety & Mode Flags ────────────────────────────────
    safety = parser.add_argument_group("Safety & Mode Flags")
    safety.add_argument(
        "--safe-mode",
        action="store_true",
        help="Disable all customizations and risky features",
    )
    safety.add_argument("--yolo", action="store_true", help="Bypass all safety prompts")
    safety.add_argument("--ignore-rules", action="store_true", help="Skip rules file")
    safety.add_argument("--ignore-user-config", action="store_true", help="Skip user config")
    safety.add_argument(
        "--no-failure-learning",
        action="store_true",
        help="Disable failure context injection",
    )
    safety.add_argument(
        "--track-goals",
        action="store_true",
        help="Track completed goals to skip on restart",
    )
    safety.add_argument("--reset-goals", action="store_true", help="Reset goals_completed tracking")
    safety.add_argument("--no-tool-shortcut", action="store_true", help="Disable tool shortcuts")
    safety.add_argument(
        "--heartbeat-timeout",
        type=int,
        default=0,
        help="Session heartbeat timeout in seconds (0=off)",
    )
    safety.add_argument(
        "--force-reset",
        action="store_true",
        help="Force reset the ledger before starting",
    )
    safety.add_argument(
        "--tag",
        type=str,
        default="",
        help="Arbitrary tag for the run (stored in ledger)",
    )

    # ── Run Mode ───────────────────────────────────────────
    run = parser.add_argument_group("Run Mode")
    run.add_argument("--run", action="store_true", help="Run the loop")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Show configuration and exit without running",
    )
    run.add_argument(
        "--task-type",
        type=str,
        default="auto",
        help="Force a specific task type (auto = detect from goal)",
    )
    run.add_argument(
        "--shutdown-sentinel",
        type=str,
        default=SENTINEL_PATH_DEFAULT,
        help=f"Sentinel file path (default: {SENTINEL_PATH_DEFAULT})",
    )
    run.add_argument("--config", type=str, default="", help="Load config from JSON file")
    run.add_argument(
        "--save-config",
        type=str,
        default="",
        help="Save current config to JSON file and exit",
    )

    # ── Introspection (handled before --goal check) ─────────
    intro = parser.add_argument_group("Introspection")
    intro.add_argument("--version", action="store_true", help="Print daemon version and exit")
    intro.add_argument("--list-flags", action="store_true", help="Print all flags organized by group")
    intro.add_argument(
        "--list-groups",
        action="store_true",
        help="Print compact group names with flag counts",
    )
    intro.add_argument("--examples", action="store_true", help="Print categorized usage examples")
    intro.add_argument(
        "--explain",
        type=str,
        default="",
        nargs="?",
        const="help",
        help="Show detailed help for a specific flag",
    )
    intro.add_argument(
        "--help-topic",
        type=str,
        default="",
        nargs="?",
        const="introspection",
        help="Show all flags in a single argument group",
    )
    intro.add_argument("--preflight", action="store_true", help="Run environment health checks")
    intro.add_argument("--doctor", action="store_true", help="Run comprehensive self-diagnosis")
    intro.add_argument(
        "--healthcheck",
        action="store_true",
        help="Run structured health check with JSON output",
    )
    intro.add_argument(
        "--status",
        action="store_true",
        help="Show loop status from ledger (no --goal required)",
    )
    intro.add_argument("--dump-env", action="store_true", help="Print all known env vars with defaults")
    intro.add_argument(
        "--check-env",
        action="store_true",
        help="Validate .env file for typos and unknown variables",
    )
    intro.add_argument(
        "--completion-script",
        type=str,
        default="",
        nargs="?",
        const="bash",
        help="Generate shell completion script (bash or zsh)",
    )

    return parser
