"""CLI entry point — main() function with argparse setup."""

import argparse
import json
import os
import sys

from . import parser as _parser_mod
from .color_utils import colorizer, configure_color_mode
from .config import (
    BASE_TOOLSETS,
    LEDGER_PATH,
    VERSION,
)
from .env_utils import (
    check_env_file,
)
from .file_utils import _init_daemon_log, _log, read_ledger, write_ledger
from .heartbeat import _cleanup_stale_heartbeats
from .help_topics import (
    _explain_flag,
    _help_topic,
    _list_examples,
    _list_flags,
    _render_status,
    _run_doctor,
    _run_healthcheck,
)
from .loop import run_loop
from .preflight import PreflightChecker
from .state import load_or_create_ledger
from .validation import load_json_schema


def _create_parser(for_introspection: bool = False) -> argparse.ArgumentParser:
    """Create and return the argument parser (re-exported from .parser)."""
    return _parser_mod._create_parser(for_introspection=for_introspection)


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
        except (OSError, FileNotFoundError) as e:
            _log(f"[ERROR] Could not read context file: {e}")
            sys.exit(1)

    # ── Resolve toolsets ───────────────────────────────────
    toolsets_list = [t.strip() for t in (args.toolsets or BASE_TOOLSETS).split(",") if t.strip()]

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
        config_dict = {key: val for key, val in vars(args).items() if val not in (None, "") and not key.startswith("_")}
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
            output_schema=(json.loads(args.output_schema) if args.output_schema else None)
            or (load_json_schema(args.output_schema_file) if args.output_schema_file else None),
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
        _zsh_flags = _zsh_sep.join(f"--{f}" for f in sorted(flag_names) if not f.startswith("--") and f != "--help")
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
