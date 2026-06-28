"""CLI entry point — main() function with argparse setup."""

import argparse
import json
import os
import sys

from .config import (
    LEDGER_PATH,
    SENTINEL_PATH_DEFAULT,
    DEFAULT_CONVERGENCE_THRESHOLD,
    DEFAULT_CONVERGENCE_WINDOW,
    BASE_TOOLSETS,
    VERSION,
)
from .file_utils import _log, _init_daemon_log, write_ledger, read_ledger
from .help_topics import (
    _list_flags,
    _list_examples,
    _run_healthcheck,
    _run_doctor,
    _explain_flag,
    _help_topic,
    _render_status,
)
from .preflight import PreflightChecker
from .validation import load_json_schema
from .state import load_or_create_ledger
from .loop import run_loop
from .heartbeat import _cleanup_stale_heartbeats
from .color_utils import colorizer, configure_color_mode
from .env_utils import (
    check_env_file,
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
    core.add_argument(
        "--context", type=str, default="", help="Context/instructions for the worker"
    )
    core.add_argument(
        "--context-file", type=str, default="", help="File to read context from"
    )
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
    parallel.add_argument(
        "--workers", type=int, default=1, help="Number of parallel workers (default: 1)"
    )
    parallel.add_argument(
        "--session-timeout",
        type=int,
        default=7200,
        help="Worker timeout in seconds (default: 7200)",
    )
    parallel.add_argument(
        "--max-turns", type=int, default=500, help="Max turns per worker (default: 500)"
    )
    parallel.add_argument(
        "--max-retries", type=int, default=0, help="Retry count on worker failure"
    )
    parallel.add_argument(
        "--retry-delay", type=int, default=5, help="Delay between retries in seconds"
    )
    parallel.add_argument(
        "--cooldown", type=int, default=0, help="Cooldown between iterations in seconds"
    )
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
    worker.add_argument(
        "--no-auto-toolsets", action="store_true", help="Disable auto toolset detection"
    )
    worker.add_argument(
        "--prompt-suffix",
        type=str,
        default="",
        help="Suffix appended to every worker prompt",
    )
    worker.add_argument(
        "--skills", type=str, default="", help="Skills to enable for workers"
    )
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
    worker.add_argument(
        "--output-schema-file", type=str, default="", help="File containing JSON schema"
    )
    worker.add_argument(
        "--pass-session-id",
        action="store_true",
        help="Pass session ID between iterations",
    )
    worker.add_argument(
        "--resume", action="store_true", help="Resume a chained session"
    )
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
    git_group.add_argument(
        "--git", action="store_true", help="Track git diff stats in the ledger"
    )
    git_group.add_argument(
        "--git-commit", action="store_true", help="Auto-commit after each iteration"
    )
    git_group.add_argument(
        "--store-git-diff", action="store_true", help="Store full git diff in ledger"
    )
    git_group.add_argument(
        "--worktree", action="store_true", help="Use git worktrees for parallel workers"
    )
    git_group.add_argument(
        "--workdir", type=str, default="", help="Working directory for workers"
    )
    git_group.add_argument(
        "--watch-dir", type=str, default="", help="Directory to watch for file changes"
    )
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
    dash.add_argument(
        "--status-html", type=str, default="", help="Path for live HTML dashboard file"
    )
    dash.add_argument(
        "--status-file", type=str, default="", help="Path for JSON status file"
    )
    dash.add_argument(
        "--webhook-port",
        type=int,
        default=0,
        help="Port for webhook-triggered iterations (0=off)",
    )

    # ── HTTP Callbacks ─────────────────────────────────────
    http = parser.add_argument_group("HTTP Callbacks")
    http.add_argument(
        "--http-callback", type=str, default="", help="URL to POST iteration results to"
    )
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
    archive.add_argument(
        "--archive-dir", type=str, default="", help="Directory for archived iterations"
    )
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
    log_group.add_argument(
        "--log-file", type=str, default="", help="Path for daemon log file"
    )
    log_group.add_argument(
        "--log-max-mb",
        type=int,
        default=10,
        help="Max log file size in MB before rotation",
    )
    log_group.add_argument(
        "--json-logs", action="store_true", help="Output structured JSON logs to stdout"
    )
    log_group.add_argument(
        "--quiet", action="store_true", help="Minimal log output during loop"
    )
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
    safety.add_argument(
        "--ignore-user-config", action="store_true", help="Skip user config"
    )
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
    safety.add_argument(
        "--reset-goals", action="store_true", help="Reset goals_completed tracking"
    )
    safety.add_argument(
        "--no-tool-shortcut", action="store_true", help="Disable tool shortcuts"
    )
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
    run.add_argument(
        "--config", type=str, default="", help="Load config from JSON file"
    )
    run.add_argument(
        "--save-config",
        type=str,
        default="",
        help="Save current config to JSON file and exit",
    )

    # ── Introspection (handled before --goal check) ─────────
    intro = parser.add_argument_group("Introspection")
    intro.add_argument(
        "--version", action="store_true", help="Print daemon version and exit"
    )
    intro.add_argument(
        "--list-flags", action="store_true", help="Print all flags organized by group"
    )
    intro.add_argument(
        "--list-groups",
        action="store_true",
        help="Print compact group names with flag counts",
    )
    intro.add_argument(
        "--examples", action="store_true", help="Print categorized usage examples"
    )
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
    intro.add_argument(
        "--preflight", action="store_true", help="Run environment health checks"
    )
    intro.add_argument(
        "--doctor", action="store_true", help="Run comprehensive self-diagnosis"
    )
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
    intro.add_argument(
        "--dump-env", action="store_true", help="Print all known env vars with defaults"
    )
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


def main() -> None:
    """Main CLI entry point — parse args, dispatch."""
    parser = _create_parser()
    args = parser.parse_args()

    # Handle introspection flags that don't require --goal
    if args.healthcheck:
        _run_healthcheck()

    if args.doctor:
        _run_doctor()
        return

    if args.list_flags or args.list_groups:
        _list_flags(show_help=args.list_flags, parser=parser)
        return

    if args.examples:
        _list_examples()
        return

    if args.explain:
        _explain_flag(args.explain, parser=parser)
        return

    if args.help_topic:
        _help_topic(args.help_topic, parser=parser)
        return

    if args.version:
        print(f"pi-loop v{VERSION}")
        return

    if args.dump_env:
        _dump_env()
        return

    if args.check_env:
        check_env_file(".env")
        return

    if args.completion_script:
        _generate_completion(args.completion_script)
        return

    # Configure color mode
    configure_color_mode(args.color)

    # Status (no goal needed)
    if args.status:
        ledger = read_ledger()
        if ledger:
            _render_status(ledger)
        else:
            print(f"\n  {colorizer.dim('No ledger found at')} {LEDGER_PATH}")
            print(f"  {colorizer.dim('The daemon may not be running.')}\n")
        return

    # Preflight
    if args.preflight:
        checker = PreflightChecker(args)
        checker.run_all()
        return

    # All remaining commands need --goal
    if not args.goal and not args.goals_file:
        # If --run is not set either, show help
        if not args.run and not args.dry_run:
            parser.print_help()
            return
        parser.print_help()
        sys.exit(1)

    # ── Resolve context ────────────────────────────────────
    resolved_context = args.context
    if args.context_file:
        try:
            with open(os.path.expanduser(args.context_file)) as cf:
                resolved_context = cf.read().strip()
        except (FileNotFoundError, IOError) as e:
            _log(f"[ERROR] Could not read context file: {e}")
            sys.exit(1)

    # ── Resolve toolsets ───────────────────────────────────
    toolsets_list = [
        t.strip() for t in (args.toolsets or BASE_TOOLSETS).split(",") if t.strip()
    ]

    # ── Clean stale heartbeats ─────────────────────────────
    _cleanup_stale_heartbeats()

    # ── Load or create ledger ──────────────────────────────
    if args.force_reset:
        try:
            os.remove(LEDGER_PATH)
            _log("[INFO] Forced reset: removed existing ledger")
        except OSError as e:
            _log(f"[WARN] Could not remove ledger: {e}")

    state = load_or_create_ledger(
        goal=args.goal,
        context=resolved_context,
        sentinel_path=args.shutdown_sentinel,
        reset_goals=args.reset_goals,
    )
    state["toolsets"] = toolsets_list
    state["compact_every"] = args.compact_every
    state["max_iterations"] = args.max_iterations
    state["retry_delay"] = args.retry_delay
    state["workdir"] = args.workdir or ""
    state["session_timeout"] = args.session_timeout
    state["evolve"] = args.evolve
    state["git"] = args.git
    state["git_commit"] = args.git_commit
    state["workers"] = args.workers
    state["notify_cmd"] = args.notify_cmd
    state["max_output_chars"] = args.max_output_chars
    state["max_idle_iterations"] = args.max_idle_iterations
    state["status_file"] = args.status_file
    state["profile"] = args.profile
    state["model"] = args.model
    state["provider"] = args.provider
    state["http_callback"] = args.http_callback
    state["http_callback_secret"] = args.http_callback_secret
    state["keep_iterations"] = args.keep_iterations
    state["tag"] = args.tag
    state["prompt_suffix"] = args.prompt_suffix
    state["no_tool_shortcut"] = args.no_tool_shortcut
    state["max_turns"] = args.max_turns
    state["output_schema_file"] = args.output_schema_file or ""
    state["output_schema_inline"] = args.output_schema or ""
    state["yolo"] = args.yolo
    state["ignore_user_config"] = args.ignore_user_config
    write_ledger(state)

    # Load config from file (command-line args override file values)
    if args.config:
        config_path = os.path.expanduser(args.config)
        try:
            with open(config_path) as f:
                file_config = json.load(f)
            for key, val in file_config.items():
                if (
                    key in args
                    and getattr(args, key) not in (None, "", False, 0)
                    and key not in ("config", "run", "force_reset")
                ):
                    continue
                if hasattr(args, key):
                    setattr(args, key, val)
            _log(f"[CONFIG] Loaded config from {config_path}")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            _log(f"[CONFIG] WARN: Could not load config from {config_path}: {e}")

    # Save config and exit
    if args.save_config:
        config_path = os.path.expanduser(args.save_config)
        config_dict = {
            key: val
            for key, val in vars(args).items()
            if val not in (None, "") and not key.startswith("_")
        }
        config_dict["version"] = VERSION
        os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config_dict, f, indent=2)
        _log(f"[CONFIG] Saved configuration to {config_path}")
        sys.exit(0)

    if args.run:
        if args.log_file:
            _init_daemon_log(args.log_file, args.log_max_mb)

        _log(f"  {colorizer.ok('Starting loop...')}")
        _log(
            f"  {colorizer.dim('Sentinel:')} {colorizer.flag('echo stop >')} {colorizer.value(args.shutdown_sentinel)}"
        )
        _log("")
        run_loop(
            goal=args.goal,
            context=resolved_context,
            workdir=args.workdir or None,
            sentinel_path=args.shutdown_sentinel,
            max_iterations=args.max_iterations,
            compact_every=args.compact_every,
            retry_delay=args.retry_delay,
            session_timeout=args.session_timeout,
            state=state,
            status_file=args.status_file,
            max_idle_iterations=args.max_idle_iterations,
            evolve=args.evolve,
            git=args.git,
            git_commit=args.git_commit,
            workers=args.workers,
            notify_cmd=args.notify_cmd or None,
            max_output_chars=args.max_output_chars,
            profile=args.profile,
            model=args.model,
            provider=args.provider,
            http_callback=args.http_callback,
            http_callback_secret=args.http_callback_secret,
            keep_iterations=args.keep_iterations,
            archive_dir=args.archive_dir,
            archive_retention=args.archive_retention,
            archive_max_size=args.archive_max_size,
            max_retries=args.max_retries,
            on_error_cmd=args.on_error_cmd or None,
            tag=args.tag,
            prompt_suffix=args.prompt_suffix,
            no_tool_shortcut=args.no_tool_shortcut,
            max_turns=args.max_turns,
            auto_toolsets=not args.no_auto_toolsets,
            failure_learning=not args.no_failure_learning,
            html_dashboard=args.status_html,
            webhook_port=args.webhook_port,
            watch_dir=args.watch_dir,
            watch_poll=args.watch_poll,
            cooldown=args.cooldown,
            goals_file=args.goals_file,
            stop_at_goals_end=args.stop_at_goals_end,
            output_schema=(
                json.loads(args.output_schema) if args.output_schema else None
            )
            or (
                load_json_schema(args.output_schema_file)
                if args.output_schema_file
                else None
            ),
            cooldown_mode=args.cooldown_mode,
            convergence_threshold=args.convergence_threshold,
            convergence_window=args.convergence_window,
            convergence_stop=args.convergence_stop,
            store_git_diff=args.store_git_diff,
            startup_delay=args.startup_delay,
            notify_desktop=args.notify_desktop,
            notify_on_completion=args.notify_on_completion,
            notify_pushbullet=args.notify_pushbullet,
            notify_ntfy=args.notify_ntfy,
            notify_ntfy_server=args.notify_ntfy_server,
            use_library=args.use_library,
            pass_session_id=args.pass_session_id,
            checkpoints=False,
            resume=args.resume,
            resume_session_id=state.get("resume_session_id", ""),
            skills=args.skills,
            ignore_rules=args.ignore_rules,
            yolo=args.yolo,
            ignore_user_config=args.ignore_user_config,
            safe_mode=args.safe_mode,
            accept_hooks=False,
            worktree=args.worktree,
            continue_session=args.continue_session,
            track_goals=args.track_goals,
            reset_goals=args.reset_goals,
            heartbeat_timeout=args.heartbeat_timeout,
            quiet=args.quiet,
            force_reset=args.force_reset,
            json_logs=args.json_logs,
        )

    _log(f"[DONE] Daemon finished. Ledger at {LEDGER_PATH}")


def _dump_env() -> None:
    """Print all known env vars with defaults."""
    from .env_utils import KNOWN_ENV_VARS

    for var in sorted(KNOWN_ENV_VARS):
        val = os.environ.get(var, "")
        print(f"{var}={val}")


def _generate_completion(shell: str) -> None:
    """Generate shell completion script."""
    parser = _create_parser(for_introspection=True)
    flag_names = []
    for action in parser._actions:
        if action.option_strings:
            flag_names.extend(action.option_strings)

    if shell == "bash":
        print(f"""# pi-loop bash completion
_pi_loop_completions() {{
    local cur="${{COMP_WORDS[COMP_CWORD]}}"
    COMPREPLY=( $(compgen -W "{" ".join(sorted(flag_names))}" -- "$cur") )
    return 0
}}
complete -F _pi_loop_completions pi-loop
""")
    elif shell == "zsh":
        # Compute separator outside the f-string to avoid SyntaxError
        # on Python <3.12 (backslash \ in f-string expression parts).
        _zsh_sep = chr(92) + chr(10) + "        "
        _zsh_flags = _zsh_sep.join(
            f"--{f}" for f in sorted(flag_names)
            if not f.startswith("--") and f != "--help"
        )
        print(f"""#compdef pi-loop
compdef _pi_loop pi-loop
function _pi_loop() {{
    _arguments -s -S \\
        {{'--goal','-g'}}[Task goal] \\
        {{'--help','-h'}}[Show help] \\
        {{'--run'}}[Run the loop] \\
        {{'--version'}}[Show version] \\
        {{'--status'}}[Show status] \\
        {_zsh_flags}
}}
""")
    else:
        print(f"Unsupported shell: {shell}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
