"""CLI entry point — main() function with argparse setup."""

import argparse
import json
import os
import shutil
import sys

from .config import (
    LEDGER_PATH,
    LOCK_PATH,
    SENTINEL_PATH_DEFAULT,
    STATUS_FILE_DEFAULT,
    HERMES_SESSION_TIMEOUT,
    DEFAULT_CONVERGENCE_THRESHOLD,
    DEFAULT_CONVERGENCE_WINDOW,
    BASE_TOOLSETS,
    LAUNCH_LOOP_VERSION,
)
from .file_utils import _log, _init_daemon_log, write_ledger
from .signal_handlers import (
    _handle_shutdown,
    _shutdown_requested,
    _startup_file_snapshots,
    _snapshot_file,
)
from .preflight import PreflightChecker
from .hermes_utils import find_hermes, detect_task_type
from .validation import load_json_schema
from .state import load_or_create_ledger
from .loop import run_loop
from .self_test import _run_self_test
from .heartbeat import _cleanup_stale_heartbeats
from .notifications import _send_completion_notification
from .functions import set_max_output_chars
from .completions import generate_bash_completion, generate_zsh_completion
from .wizard import run_wizard
from .color_utils import colorizer, configure_color_mode
from .env_utils import (
    check_env_file,
    format_validation_results,
    parse_env_vars_from_file,
    validate_env_vars,
)


def _list_flags(show_help=True):
    """Print all CLI flags organized by group. Used by --list-flags / --list-groups.

    Introspects the argparse parser's action groups to build the output,
    eliminating the need for a separate hardcoded flag dictionary that
    would drift from the actual argparse definitions.
    """
    parser = _create_parser(for_introspection=True)
    group_map = {}  # group_title -> [(flag_str, help_text)]
    for group in parser._action_groups:
        title = group.title
        if title in ("positional arguments", "optional arguments", "options"):
            continue  # skip argparse defaults
        entries = []
        for action in group._group_actions:
            if action.option_strings:
                flag = action.option_strings[0]
                help_text = action.help or ""
                # Truncate help to first sentence/line for compact display
                help_short = help_text.split(".")[0].strip()
                if help_short:
                    help_short = help_short[:80]  # cap at 80 chars
                else:
                    help_short = help_text[:80] if help_text else ""
                entries.append((flag, help_short))
        if entries:
            group_map[title] = entries

    # Pre-argparse introspection flags that argparse itself defines
    introspection_flags = {
        "--help": "Show the full detailed help with all 80+ flags and examples",
        "--list-flags": "Print all flags organized by group with help text (this view)",
        "--list-groups": "Print compact group names with flag counts",
        "--examples": "Print categorized real-world usage examples",
        "--version": "Print daemon version and exit",
        "--completion-script": "Generate shell completion script for bash or zsh from live argparse",
        "--status": "Read the ledger and display a compact status summary (no --goal required)",
        "--explain": "Show detailed help for a specific CLI flag (no --goal required)",
        "--help-topic": "Show all flags in a single argument group (no --goal required)",
        "--init": "Interactive setup wizard — walks you through configuration step by step",
        "--wizard": "Alias for --init (interactive setup wizard)",
    }

    total_flags = sum(len(v) for v in group_map.values()) + len(introspection_flags)
    header = f"Infinite Loop Daemon v{LAUNCH_LOOP_VERSION} — CLI Flags Reference"
    print()
    print(f"  {colorizer.colorize(header, 'bold', 'white')}")
    print(
        f"  {colorizer.dim(f'Total: {total_flags} flags in {len(group_map) + (1 if show_help else 0)} groups')}"
    )
    print()
    if show_help:
        for group_name, entries in group_map.items():
            print(f"  {colorizer.group_title(f'[{group_name}]')}")
            for flag, desc in entries:
                print(f"    {colorizer.flag(flag):38s}  {colorizer.dim(desc)}")
            print()
        # Introspection section only in --list-flags mode
        print(f"  {colorizer.group_title('[Introspection]')}")
        for flag, desc in introspection_flags.items():
            print(f"    {colorizer.flag(flag):38s}  {colorizer.dim(desc)}")
        print()
    else:
        for group_name, entries in group_map.items():
            print(
                f"  {colorizer.group_title(f'[{group_name}]')}  {colorizer.dim(f'({len(entries)} flags)')}"
            )
        print(
            f"  {colorizer.group_title('[Introspection]')}  {colorizer.dim(f'({len(introspection_flags)} flags)')}"
        )


def _list_examples():
    """Print categorized real-world usage examples. Used by --examples flag."""
    header = f"Infinite Loop Daemon v{LAUNCH_LOOP_VERSION} — Usage Examples"
    print()
    print(f"  {colorizer.colorize(header, 'bold', 'white')}")
    print(f"  {colorizer.dim('=' * 58)}")
    print()

    def _section(title: str) -> None:
        print(f"  {colorizer.header(title)}")
        print()

    def _cmd(text: str) -> None:
        print(f"    {colorizer.value(text)}")

    def _comment(text: str) -> None:
        print(f"    {colorizer.dim(f'# {text}')}")

    _section("Basic Single-Goal Loop")
    _comment("Run with a single goal — simplest invocation")
    _cmd('hermes_loop --goal "Fix all ESLint errors" --run')
    print()
    _comment("One-shot preview (no loop started)")
    _cmd('hermes_loop --goal "Fix tests" --dry-run')
    print()
    _comment("Run to completion (10 iterations then stop)")
    _cmd('hermes_loop --goal "Refactor auth" --max-iterations 10 --run')
    print()

    _section("Git-Integrated Evolution")
    _comment("Auto-detect, fix, and commit — ideal for linting/formatting")
    _cmd(
        'hermes_loop --goal "Fix lint errors one at a time" --git --git-commit --evolve --run'
    )
    print()
    _comment("Stop once all changes are made")
    _cmd(
        'hermes_loop --goal "Clean up warnings" --git --git-commit --convergence-stop --run'
    )
    print()
    _comment("Store full git diffs in the ledger for review")
    _cmd(
        'hermes_loop --goal "Optimize imports" --git --git-commit --store-git-diff --run'
    )
    print()

    _section("Batch / Goals-File Processing")
    _comment("Process a list of goals, one per line")
    _cmd("hermes_loop --goals-file goals.txt --run")
    print()
    _comment("Batch with 5 parallel workers, stop when done")
    _cmd("hermes_loop --goals-file todos.txt --workers 5 --stop-at-goals-end --run")
    print()
    _comment("Track goals so restarts skip already-finished ones")
    _cmd("hermes_loop --goals-file chores.txt --track-goals --run")
    print()

    _section("Notifications & Monitoring")
    _comment("Get desktop notifications after each iteration (Linux)")
    _cmd('hermes_loop --goal "Fix bugs" --notify-desktop --run')
    print()
    _comment("Push to phone via ntfy.sh (self-hosted available)")
    _cmd('hermes_loop --goal "Run tests" --notify-ntfy my-alerts --run')
    print()
    _comment("Email yourself on errors via shell command")
    _cmd(
        'hermes_loop --goal "Deploy" --on-error-cmd \'mail -s "Loop error" you@x.com\' --run'
    )
    print()
    _comment("Real-time HTML dashboard + JSON status file")
    _cmd(
        'hermes_loop --goal "Refactor" --status-html /tmp/dash.html --status-file /tmp/status.json --run'
    )
    print()

    _section("Monitoring & Control")
    _comment("Follow iteration progress in real-time")
    _cmd("tail -f /tmp/infinite-loop.log")
    print()
    _comment("Check the full iteration ledger")
    _cmd("bash scripts/inspect-ledger.sh")
    _cmd("bash scripts/inspect-ledger.sh --summary   # compact one-liner")
    _cmd("bash scripts/inspect-ledger.sh --errors    # errors only")
    _cmd("cat /tmp/infinite-loop-state.json | python3 -m json.tool")
    print()
    _comment("Control a running daemon")
    _cmd("echo 'stop'    > /tmp/infinite-loop-stop")
    _cmd("echo 'pause'   > /tmp/infinite-loop-stop")
    _cmd("echo 'resume'  > /tmp/infinite-loop-stop")
    print()

    _section("Advanced Patterns")
    _comment("Library mode (in-process AIAgent, no subprocess)")
    _cmd('hermes_loop --goal "Analyze logs" --use-library --run')
    print()
    _comment("Multi-worker parallel analysis")
    _cmd('hermes_loop --goal "Review all modules" --workers 4 --git --run')
    print()
    _comment("File watcher — auto-trigger when files change")
    _cmd('hermes_loop --goal "Run on change" --watch-dir src/ --run')
    print()
    _comment("Webhook-triggered iteration server")
    _cmd('hermes_loop --goal "Trigger me" --webhook-port 9090 --run')
    _comment("Then POST /webhook to trigger an iteration")
    print()
    _comment("Resume a chained session (handoff between iterations)")
    _cmd('hermes_loop --goal "Multi-step refactor" --pass-session-id --resume --run')
    print()
    _comment("Full autonomy: bypass approvals, skip rules, no config")
    _cmd(
        'hermes_loop --goal "Do everything" --yolo --ignore-rules --ignore-user-config --run'
    )
    print()
    _comment("Troubleshooting: safe mode disables all customizations")
    _cmd('hermes_loop --goal "Debug setup" --safe-mode --run')
    print()

    _section("Help & Diagnostics")
    _comment("Quick overview of all flags by category")
    _cmd("hermes_loop --list-flags")
    print()
    _comment("Compact group overview")
    _cmd("hermes_loop --list-groups")
    print()
    _comment("Full detailed flag reference")
    _cmd("hermes_loop --help")
    print()
    _comment("Detailed help on any single flag")
    _cmd("hermes_loop --explain workers")
    _cmd("hermes_loop --explain cooldown")
    _cmd('hermes_loop --explain "max-iterations"')
    print()
    _comment("Help on a specific argument group (notifications, git, toolsets, etc.)")
    _cmd("hermes_loop --help-topic notifications")
    _cmd("hermes_loop --help-topic introspection")
    print()
    _comment("Run self-tests (auto-detected at runtime)")
    _cmd("hermes_loop --self-test")
    print()
    _comment("Health check before running")
    _cmd("hermes_loop --preflight")
    print()
    _comment("Full self-diagnosis (hermes, PATH, .env, git, shell, disk)")
    _cmd("hermes_loop --doctor")
    print()
    _comment("Save current config for reuse")
    _cmd('hermes_loop --goal "Config snapshot" --save-config my-loop.json')
    _cmd('hermes_loop --goal "Load config" --config my-loop.json --run')
    print()
    _comment("Shell tab-completion (one-time setup)")
    _cmd("make completion")
    print()
    _comment("Interactive setup wizard")
    _cmd("hermes_loop --init")
    _cmd("make init")
    print()
    _comment("Quick one-command entrypoint (reads .env)")
    _cmd("bash run.sh")
    _cmd('bash run.sh --goal "Override" --git --quiet')
    print()

    _section("Flag Reference")
    _comment("Detailed help on any single CLI flag")
    _cmd("hermes_loop --explain git")
    _cmd("hermes_loop --explain converge")
    _cmd("hermes_loop --explain workers")
    _cmd("hermes_loop --explain use-library")
    _comment("Help for a specific argument group")
    _cmd("hermes_loop --help-topic notifications")
    _cmd("hermes_loop --help-topic git")
    _cmd("hermes_loop --help-topic introspection")
    _comment("List all flags")
    _cmd("hermes_loop --list-flags")
    _cmd("hermes_loop --list-groups")
    print()

    _section("Status & Monitoring")
    _comment("Quick status of running daemon (reads ledger, no --goal needed)")
    _cmd("hermes_loop --status")
    _cmd("hermes_loop --status --color never   # plain text, no ANSI codes")
    print()
    _comment("Full iteration history")
    _cmd("bash scripts/inspect-ledger.sh")
    _cmd("bash scripts/inspect-ledger.sh --summary   # compact one-liner")
    print()
    _comment("Live log tail / HTML dashboard")
    _cmd("tail -f /tmp/infinite-loop.log")
    _cmd('hermes_loop --goal "..." --status-html /tmp/dash.html --run')
    print()


def _explain_flag(flag_name: str) -> None:
    """Print detailed help for a single CLI flag.

    Searches the argparse parser for the flag by any unambiguous prefix
    (with or without leading '--'), and shows: full help text, type,
    default value, accepted choices, argument group, and related flags.
    """
    parser = _create_parser(for_introspection=True)
    c = colorizer

    # Normalize: strip leading --, strip hyphens
    search = flag_name.lstrip("-").replace("_", "-").lower()

    # Collect all actions with their flag name aliases
    all_actions: list[tuple[str, argparse.Action, str]] = []
    for group in parser._action_groups:
        for action in group._group_actions:
            if not action.option_strings:
                continue
            canonical = action.option_strings[0].lstrip("-").replace("_", "-")
            all_actions.append((canonical, action, group.title))

    # Find match: exact, then prefix, then substring
    matches: list[tuple[str, argparse.Action, str]] = []
    for canonical, action, grp_title in all_actions:
        if canonical == search:
            matches = [(canonical, action, grp_title)]
            break
        if canonical.startswith(search):
            matches.append((canonical, action, grp_title))

    if not matches:
        # Substring search fallback
        for canonical, action, grp_title in all_actions:
            if search in canonical:
                matches.append((canonical, action, grp_title))

    if not matches:
        print()
        print(f"  {c.tag_fail()}  No flag found matching '{flag_name}'.")
        print(
            f"  {c.dim('  Try:')} {c.flag('hermes_loop --list-flags | grep ' + flag_name)}"
        )
        print(f"  {c.dim('  Or:')}  {c.flag('hermes_loop --list-groups')}")
        print()
        return

    if len(matches) > 1:
        print()
        print(
            f"  {c.tag_warn()}  Multiple flags match '{flag_name}': "
            + ", ".join(c.flag(f"--{m[0]}") for m in matches)
        )
        print(
            f"  {c.dim('  Use a more specific name (e.g., --explain')} {c.flag(f'--{matches[0][0]}')}{c.dim(')')}"
        )
        print()
        return

    canonical, action, grp_title = matches[0]
    flag_str = action.option_strings[0]
    help_text = action.help or "(no description)"

    # Default value info
    default = getattr(action, "default", None)
    is_bool = action.nargs == 0 and action.const is True

    print()
    print(f"  {c.colorize(flag_str, 'bold', 'white')}")
    print(f"  {c.dim('=' * (len(flag_str) + 2))}")
    print()
    print(f"  {c.value('Group:')}     {c.group_title(grp_title)}")
    print(f"  {c.value('Type:')}      ", end="")
    if is_bool:
        print(f"{c.flag('boolean (on/off)')}")
    elif action.choices:
        print(f"{c.flag('choice')} — {', '.join(c.value(ch) for ch in action.choices)}")
    elif action.type is int:
        print(f"{c.flag('integer')}")
    elif action.type is float:
        print(f"{c.flag('float')}")
    else:
        print(f"{c.flag('string')}")
    if default is not None and default != "" and default != 0 and not is_bool:
        print(f"  {c.value('Default:')}  {c.dim(str(default))}")
    elif is_bool:
        print(f"  {c.value('Default:')}  {c.dim('off (not set)')}")
    print()
    # Full help text — word-wrap to 80 chars
    print(f"  {c.dim('Description:')}")
    words = help_text.split()
    line = ""
    for w in words:
        if len(line) + len(w) + 1 > 76:
            print(f"    {c.dim(line)}")
            line = w
        else:
            line = f"{line} {w}" if line else w
    if line:
        print(f"    {c.dim(line)}")
    print()

    # Aliases
    if len(action.option_strings) > 1:
        aliases = ", ".join(c.flag(a) for a in action.option_strings)
        print(f"  {c.value('Aliases:')}   {aliases}")
        print()

    # Related flags (same group)
    related = []
    for other_canon, other_action, other_grp in all_actions:
        if other_grp == grp_title and other_canon != canonical:
            related.append(other_action.option_strings[0])
    if related:
        print(f"  {c.value('Related:')}   {'  '.join(c.flag(r) for r in related[:10])}")
        if len(related) > 10:
            print(
                f"              {c.dim(f'... and {len(related) - 10} more in this group')}"
            )
    print()

    # Usage example based on type
    print(f"  {c.value('Usage:')}")
    if is_bool:
        print(f"    {c.flag(flag_str)}            {c.dim('# enable')}")
        print(f"    {c.dim('# (omit to leave disabled)')}")
    elif action.type is int:
        print(
            f"    {c.flag(flag_str)} {c.value('N')}       {c.dim('# e.g.')} {c.flag(flag_str)} {c.value('10')}"
        )
    elif action.type is float:
        print(
            f"    {c.flag(flag_str)} {c.value('N.N')}     {c.dim('# e.g.')} {c.flag(flag_str)} {c.value('2.5')}"
        )
    elif action.choices:
        print(
            f"    {c.flag(flag_str)} {c.value('{choice}')}  {c.dim('# e.g.')} {c.flag(flag_str)} {c.value(action.choices[0])}"
        )
    else:
        print(
            f"    {c.flag(flag_str)} {c.value('VALUE')}  {c.dim('# e.g.')} {c.flag(flag_str)} {c.value('my-value')}"
        )
    print()


def _help_topic(topic: str) -> None:
    """Print flags for a single argument group. Used by --help-topic flag.

    Searches all argparse groups by title (case-insensitive, prefix match),
    then prints only the flags in that group with their full help text.
    Shows available groups if no match is found.
    """
    parser = _create_parser(for_introspection=True)
    c = colorizer

    # Collect all groups
    search = topic.lower().strip()
    groups: list[tuple[str, list[tuple[str, argparse.Action]]]] = []
    for group in parser._action_groups:
        title = group.title
        if title in ("positional arguments", "optional arguments", "options"):
            continue
        if not group._group_actions:
            continue
        entries = [
            (a.option_strings[0], a) for a in group._group_actions if a.option_strings
        ]
        groups.append((title, entries))

    # Add introspection group (not in parser groups)
    introspection_flags_list = [
        ("--help", "Show the full detailed help with all flags and examples"),
        ("--list-flags", "Print all flags organized by group with help text"),
        ("--list-groups", "Print compact group names with flag counts"),
        ("--examples", "Print categorized real-world usage examples"),
        ("--version", "Print daemon version and exit"),
        (
            "--completion-script",
            "Generate shell completion script for bash or zsh from live argparse",
        ),
        ("--status", "Read the ledger and display a compact status summary"),
        ("--explain", "Show detailed help for a specific CLI flag"),
        ("--help-topic", "Show flags for a specific argument group (this command)"),
        ("--init", "Interactive setup wizard"),
        ("--wizard", "Alias for --init"),
        ("--doctor", "Run comprehensive self-diagnosis"),
        ("--check-env", "Validate .env file for typos and mistakes"),
    ]

    # Find matching group
    exact_match = None
    prefix_matches = []
    subtitle_matches = []

    for title, entries in groups:
        if title.lower() == search:
            exact_match = (title, entries)
            break
        if title.lower().startswith(search):
            prefix_matches.append((title, entries))
        # Also check common abbreviations in the search against group flags
        if len(search) >= 3:
            if search in title.lower():
                subtitle_matches.append((title, entries))

    # Also check if the search matches part of the introspection group title
    if search in "introspection" or "intro".startswith(search):
        match_list = introspection_flags_list
        print()
        print(f"  {c.colorize('[Introspection]', 'bold', 'magenta')}")
        print(f"  {c.dim('=' * 48)}")
        print(f"  {c.dim('Pre-argparse flags — no --goal required')}")
        print()
        for flag, desc in match_list:
            help_short = desc.split(".")[0].strip()[:80]
            print(f"    {c.flag(flag):38s}  {c.dim(help_short)}")
        print()
        print(
            f"  {c.dim('Tip: use')} {c.flag('--help')} {c.dim('for the full flag reference.')}"
        )
        print()
        return

    if exact_match:
        title, entries = exact_match
    elif len(prefix_matches) == 1:
        title, entries = prefix_matches[0]
    elif len(prefix_matches) > 1:
        print()
        print(f"  {c.tag_warn()}  Multiple groups match '{topic}':")
        for t, _ in prefix_matches:
            print(f"    {c.flag(t)}")
        print()
        return
    elif len(subtitle_matches) == 1:
        title, entries = subtitle_matches[0]
    else:
        print()
        print(f"  {c.tag_fail()}  No argument group found matching '{topic}'.")
        print(f"  {c.dim('  Available groups:')}")
        for t, _ in groups:
            print(f"    {c.flag(t)}")
        print(
            f"  {c.dim('  Also:')} {c.flag('Introspection')} {c.dim('(pre-argparse flags)')}"
        )
        print(f"  {c.dim('  Use:')} {c.flag('hermes_loop --help-topic notifications')}")
        print()
        return

    print()
    print(f"  {c.colorize(f'[{title}]', 'bold', 'magenta')}")
    group_summary = parser._action_groups
    desc_text = ""
    for grp in group_summary:
        if grp.title == title:
            desc_text = grp.description or ""
            break
    if desc_text:
        print(f"  {c.dim('=' * 48)}")
        print(f"  {c.dim(desc_text)}")
    print()

    for flag_str, action in entries:
        help_text = action.help or "(no description)"
        # Type info
        is_bool = action.nargs == 0 and action.const is True
        type_str = ""
        if is_bool:
            type_str = " [bool]"
        elif action.choices:
            type_str = f" [{', '.join(action.choices)}]"
        elif action.type is int:
            type_str = " [int]"
        elif action.type is float:
            type_str = " [float]"

        # Default info
        default = getattr(action, "default", None)
        default_str = ""
        if default is not None and default != "" and default != 0 and not is_bool:
            default_str = f" (default: {default})"
        elif is_bool:
            default_str = " (default: off)"

        # Word-wrap help to 72 chars
        words = help_text.split()
        line = ""
        first = True
        for w in words:
            if len(line) + len(w) + 1 > 72:
                label = (
                    f"    {c.flag(flag_str + type_str):38s}"
                    if first
                    else "    " + " " * 38
                )
                print(f"{label}  {c.dim(line)}")
                line = w
                first = False
            else:
                line = f"{line} {w}" if line else w
        if line:
            label = (
                f"    {c.flag(flag_str + type_str):38s}" if first else "    " + " " * 38
            )
            print(f"{label}  {c.dim(line)}")

        # Aliases on a second line
        if len(action.option_strings) > 1:
            aliases = ", ".join(c.dim(a) for a in action.option_strings[1:])
            print(f"    {'':38s}  {c.dim('aliases:')} {aliases}")

        if default_str:
            print(f"    {'':38s}  {c.dim(default_str)}")
        print()

    # Show related groups
    all_group_titles = [t for t, _ in groups if t.lower() != title.lower()]
    print(
        f"  {c.dim('Other groups:')}  {' | '.join(c.flag(g) for g in all_group_titles[:5])}"
    )
    if len(all_group_titles) > 5:
        print(f"    {'':14s}{c.dim(f'... and {len(all_group_titles) - 5} more')}")
    print(f"  {c.dim('See all groups:')} {c.flag('hermes_loop --list-groups')}")
    print()


def _display_status():
    """Read the ledger and print a compact colorized status. Used by --status flag."""
    from .file_utils import read_ledger
    from datetime import datetime, timezone
    import time

    ledger = read_ledger()
    c = colorizer

    header = f"Infinite Loop Daemon v{LAUNCH_LOOP_VERSION} \u2014 Status"
    print()
    print(f"  {c.colorize(header, 'bold', 'white')}")
    print(f"  {c.dim('=' * 44)}")
    print()

    if ledger is None:
        print(f"  {c.tag_warn()}  No ledger found at {LEDGER_PATH}")
        print(f"  {c.dim('  The daemon may not be running.')}")
        print(
            f"  {c.dim('  Start with:')} {c.flag('python3 -m hermes_loop --goal ... --run')}"
        )
        print()
        return

    status = ledger.get("status", "unknown")
    status_icon = {
        "running": c.tag_ok(),
        "paused": c.tag_warn(),
        "stopped: signal": c.tag_fail(),
        "stopped: sentinel": c.tag_fail(),
        "stopped: max_iterations": c.tag_fail(),
        "stopped: idle": c.tag_fail(),
    }.get(status, c.dim("\u25cf"))

    total = ledger.get("total_iterations", 0)
    goal = ledger.get("current_goal") or ledger.get("initial_command", "?")
    tag_val = ledger.get("tag", "")
    started_at = ledger.get("started_at", "")
    last_updated = ledger.get("last_updated", "")

    # Duration
    dur_str = "?"
    try:
        if started_at:
            if "Z" in started_at or "+" in started_at:
                start_ts = datetime.fromisoformat(started_at).timestamp()
            else:
                start_ts = datetime.fromisoformat(started_at[:19]).timestamp()
            now_ts = time.time()
            dur_s = now_ts - start_ts
            if dur_s >= 3600:
                dur_str = f"{dur_s / 3600:.1f}h"
            elif dur_s >= 60:
                dur_str = f"{dur_s / 60:.1f}m"
            else:
                dur_str = f"{dur_s:.0f}s"
    except (ValueError, TypeError):
        pass

    # Error counts
    error_type_counts = ledger.get("error_type_counts", {})
    err_count = sum(error_type_counts.values())
    err_types = []
    for etype in ("timeout", "network", "schema", "unknown", "heartbeat"):
        cnt = error_type_counts.get(etype, 0)
        if cnt:
            err_types.append(f"{etype}={cnt}")

    # Last iteration
    iters = ledger.get("iterations", [])
    last_iter = iters[-1] if iters else None

    # Success count
    success_count = sum(
        1 for it in iters if not it.get("error") and it.get("classification") != "stuck"
    )
    stuck_count = sum(
        1 for it in iters if not it.get("error") and it.get("classification") == "stuck"
    )

    print(f"  {c.value('Status:')}        {status_icon} {status}")
    print(
        f"  {c.value('Iterations:')}    {c.flag(str(total))}  ({c.tag_ok()}{success_count} ok",
        end="",
    )
    if err_count:
        print(f" {c.tag_fail()}{err_count} err", end="")
    if stuck_count:
        print(f" {c.dim(str(stuck_count))} stuck", end="")
    print(")")
    if err_types:
        print(f"  {c.value('Errors:')}        {c.dim(', '.join(err_types))}")
    if dur_str != "?":
        print(f"  {c.value('Duration:')}     {c.dim(dur_str)}")
    if tag_val:
        print(f"  {c.value('Tag:')}           {c.flag(tag_val)}")
    print(f"  {c.value('Goal:')}         {c.dim(goal[:100])}")
    print(
        f"  {c.value('Updated:')}      {c.dim(last_updated[:19] if last_updated else '?')}"
    )

    if last_iter:
        n = last_iter.get("n", "?")
        summary = (last_iter.get("summary") or "")[:80]
        last_err = last_iter.get("error", "")
        cls = last_iter.get("classification", "")
        print()
        print(f"  {c.group_title('[Last Iteration]')}")
        print(f"    #{n}  {c.dim(summary)}")
        if last_err:
            print(f"    {c.tag_fail()}error: {last_err[:120]}")
        if cls and cls != "completed":
            print(f"    {c.tag_warn()}classification: {cls}")

    # Worker info
    workers = ledger.get("workers", 1)
    evolve = ledger.get("evolve", False)
    git = ledger.get("git", False)
    print()
    ev_str = "yes" if evolve else "no"
    git_str = "yes" if git else "no"
    print(f"  {c.dim(f'Workers: {workers}  Evolve: {ev_str}  Git: {git_str}')}")

    # Quick actions
    print()
    print(f"  {c.group_title('Quick actions:')}")
    print(f"    {c.dim('Stop:')}   echo stop > {SENTINEL_PATH_DEFAULT}")
    print(f"    {c.dim('Pause:')}  echo pause > {SENTINEL_PATH_DEFAULT}")
    print(f"    {c.dim('Logs:')}   tail -f {LEDGER_PATH}")
    print(f"    {c.dim('Full:')}   bash scripts/inspect-ledger.sh")
    print()


def _create_parser(for_introspection=False):
    """Build and return the argparse parser with all argument groups.

    Args:
        for_introspection: If True, --goal is made non-required so the parser
            can be constructed without a --goal argument (useful for --list-flags).
    """
    parser = argparse.ArgumentParser(
        description=(
            f"Infinite Loop Daemon v{LAUNCH_LOOP_VERSION} — Autonomous Hermes Agent Looping Framework\n\n"
            "Spawns Hermes sessions in a loop with real tools (terminal, file, delegation) + "
            "multi-level delegate_task() trees. Each iteration spawns a `hermes chat -q` session "
            "with configurable toolsets, max-turns, and context propagation.\n\n"
            "Features at a glance:\n"
            "  Iteration:  evolve, max-iterations, goals-file, convergence detection\n"
            "  Parallel:   workers, session-timeout, max-retries, cooldown\n"
            "  Notify:     desktop (Linux), Pushbullet, ntfy, HTTP callback, shell cmd\n"
            "  Sessions:   use-library, pass-session-id, checkpoints, resume, skills\n"
            "  Spawn:      profile, model, provider, yolo, safe-mode, worktree\n"
            "  Debug:      preflight, self-test, dry-run, heartbeat, status-html\n"
            "  Git:        auto-commit, store-git-diff, max-idle-iterations\n"
            "  Web:        webhook REST API, SSE dashboard v3, HTTP callback\n\n"
            "Common usage:\n"
            '  python3 -m hermes_loop --goal "Fix lint errors" --run\n'
            '  python3 -m hermes_loop --goal "Refactor auth" --git --git-commit --evolve --run\n'
            "  python3 -m hermes_loop --goals-file goals.txt --track-goals --workers 5 --run\n"
            "  python3 -m hermes_loop --self-test\n"
            "  python3 -m hermes_loop --dry-run\n"
            "  python3 -m hermes_loop --examples\n"
            "  python3 -m hermes_loop --status\n\n"
            "Stop:  echo 'stop' > /tmp/infinite-loop-stop\n"
            "Pause: echo 'pause' > /tmp/infinite-loop-stop\n"
            "Status: python3 -m hermes_loop --status"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── 1. Core Task ────────────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Core Task", "The primary task definition for the loop"
    )
    group.add_argument(
        "--goal",
        required=not for_introspection,
        help="The core task for spawned sessions",
    )
    group.add_argument(
        "--context", default="", help="Initial context (paths, constraints, language)"
    )
    group.add_argument(
        "--context-file",
        default="",
        help="Read context from a file (alternative to --context)",
    )
    group.add_argument("--workdir", default="", help="Working directory")
    group.add_argument(
        "--prompt-suffix",
        default="",
        help="Extra text appended to every spawned prompt",
    )
    group.add_argument(
        "--task-type",
        default="auto",
        help="Force a specific task type (research|code-fix|code-build|system-admin|"
        "data-processing|content|general). "
        "Default: auto-detect from --goal.",
    )

    # ── 2. Toolsets ─────────────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Toolsets", "Control which toolsets are available in spawned sessions"
    )
    group.add_argument(
        "--toolsets",
        default=BASE_TOOLSETS,
        help=(
            "Comma-separated toolsets for spawned Hermes sessions "
            f"(default: {BASE_TOOLSETS})"
        ),
    )
    group.add_argument(
        "--no-auto-toolsets",
        action="store_true",
        help="Disable automatic toolset enrichment based on task type",
    )
    group.add_argument(
        "--no-failure-learning",
        action="store_true",
        help="Disable injection of past failure context into spawned sessions",
    )

    # ── 3. Iteration Control ───────────────────────────────────────────────
    group = parser.add_argument_group(
        "Iteration Control",
        "How many iterations to run, how often to compact, and whether to evolve goals",
    )
    group.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Auto-stop after N iterations (0=infinite)",
    )
    group.add_argument(
        "--max-turns",
        type=int,
        default=500,
        help="Max turns per spawned Hermes session (default: 500 — high for deep delegation chains)",
    )
    group.add_argument(
        "--compact-every", type=int, default=5, help="Compact context every N iters"
    )
    group.add_argument(
        "--evolve",
        action="store_true",
        help="Let iterations propose the next goal (self-directing)",
    )
    group.add_argument("--run", action="store_true", help="Start the actual loop")

    # ── 4. Parallelism ──────────────────────────────────────────────────────
    group = parser.add_argument_group("Parallelism", "Concurrent execution settings")
    group.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Run N concurrent Hermes sessions per iteration",
    )

    # ── 5. Timeouts & Retries ───────────────────────────────────────────────
    group = parser.add_argument_group(
        "Timeouts & Retries",
        "Session timeouts, retry behavior, and heartbeat-based health monitoring",
    )
    group.add_argument(
        "--session-timeout",
        type=int,
        default=HERMES_SESSION_TIMEOUT,
        help=f"Max seconds per Hermes session (default: {HERMES_SESSION_TIMEOUT})",
    )
    group.add_argument(
        "--retry-delay", type=int, default=0, help="Backoff delay on error"
    )
    group.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Retry a failed iteration up to N times (0=no retry)",
    )
    group.add_argument(
        "--heartbeat-timeout",
        type=int,
        default=0,
        help="Enable heartbeat-based session health monitoring. "
        "Set to seconds of inactivity before a session is considered hung (default: 0 = disabled). "
        "Grace period is always heartbeat_timeout * 2 (total window = timeout * 3). "
        "When a session's heartbeat stops, the daemon kills it and retries.",
    )

    # ── 6. Git Integration ──────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Git Integration", "Automatic git diff capture, commits, and idle detection"
    )
    group.add_argument(
        "--git", action="store_true", help="Capture git diff stats per iteration"
    )
    group.add_argument(
        "--git-commit",
        action="store_true",
        help="Auto-commit changes per iteration (implies --git)",
    )
    group.add_argument(
        "--store-git-diff",
        action="store_true",
        help="Store the actual git diff (not just stats) in the ledger. "
        "Capped at 10KB per iteration to prevent ledger bloat. "
        "Useful for reviewing changes without shell access.",
    )
    group.add_argument(
        "--max-idle-iterations",
        type=int,
        default=0,
        help="Stop after N consecutive iterations with no git changes (requires --git)",
    )

    # ── 7. Goals File (Batch) ───────────────────────────────────────────────
    group = parser.add_argument_group(
        "Goals File (Batch)",
        "Batch-process multiple goals from a file with tracking and reset support",
    )
    group.add_argument(
        "--goals-file",
        default="",
        help="Path to file with one goal per line. Each iteration pops the next goal "
        "from the file. Useful for batch processing (e.g., fix 50 lint errors). "
        "Lines starting with '#' are ignored as comments.",
    )
    group.add_argument(
        "--stop-at-goals-end",
        action="store_true",
        help="When used with --goals-file, stop the loop when all goals are exhausted "
        "instead of wrapping around and reusing them.",
    )
    group.add_argument(
        "--track-goals",
        action="store_true",
        default=False,
        help="When used with --goals-file, track completed goals so crashed/restarted "
        "runs automatically skip already-finished goals.",
    )
    group.add_argument(
        "--reset-goals",
        action="store_true",
        default=False,
        help="When used with --track-goals, clear the goals_completed ledger on startup "
        "and re-process all goals from scratch.",
    )

    # ── 8. Rate Limiting ────────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Rate Limiting", "Cooldown between iterations to respect API rate limits"
    )
    group.add_argument(
        "--cooldown",
        type=int,
        default=0,
        help="Wait N seconds between iterations for rate-limit awareness (default: 0). "
        "Useful when many short iterations would hit API rate limits.",
    )
    group.add_argument(
        "--cooldown-mode",
        default="fixed",
        choices=["fixed", "adaptive"],
        help="Cooldown mode: 'fixed' = wait exactly --cooldown seconds (default), "
        "'adaptive' = auto-calculate delay based on average iteration duration. "
        "Fast iterations get longer cooldowns (rate-limit protection), "
        "long iterations get shorter cooldowns. Default: fixed",
    )

    # ── 9. Convergence Detection ────────────────────────────────────────────
    group = parser.add_argument_group(
        "Convergence Detection",
        "Auto-stop when iterations produce similar results (stuck detection)",
    )
    group.add_argument(
        "--convergence-stop",
        action="store_true",
        help="Auto-stop when N consecutive iterations produce similar summaries "
        "(stuck detection). Uses word-overlap Jaccard similarity.",
    )
    group.add_argument(
        "--convergence-threshold",
        type=float,
        default=DEFAULT_CONVERGENCE_THRESHOLD,
        help=f"Similarity threshold for convergence detection (0.0-1.0, default: {DEFAULT_CONVERGENCE_THRESHOLD}). "
        "Higher = more permissive (only identical summaries trigger). "
        "Lower = more aggressive (similar but not identical triggers).",
    )
    group.add_argument(
        "--convergence-window",
        type=int,
        default=DEFAULT_CONVERGENCE_WINDOW,
        help=f"Number of recent iterations to compare for convergence (default: {DEFAULT_CONVERGENCE_WINDOW}). "
        "All pairs in the window must exceed the threshold.",
    )

    # ── 10. Structured Output ───────────────────────────────────────────────
    group = parser.add_argument_group(
        "Structured Output",
        "Validate and constrain spawned session output with JSON Schema",
    )
    group.add_argument(
        "--output-schema",
        default="",
        help="Inline JSON Schema as JSON string to validate spawned session output. "
        "Uses stdlib-only validation (required fields, types, enum, length/range checks). "
        'Example: \'{"type":"object","required":["summary"],"properties":{"summary":{"type":"string"}}}\'',
    )
    group.add_argument(
        "--output-schema-file",
        default="",
        help="Path to a JSON Schema file for spawned output validation. "
        "Alternative to --output-schema for complex schemas.",
    )
    group.add_argument(
        "--max-output-chars",
        type=int,
        default=2000,
        help="Max chars of spawned output to store (0=unlimited)",
    )

    # ── 11. Shutdown ────────────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Shutdown", "Sentinel file to stop or pause the loop externally"
    )
    group.add_argument(
        "--shutdown-sentinel", default=SENTINEL_PATH_DEFAULT, help="Sentinel file path"
    )

    # ── 12. Profile / Model ─────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Profile / Model",
        "Select which Hermes profile, model, provider, and source to use for spawned sessions",
    )
    group.add_argument(
        "--profile",
        default="",
        help="Hermes profile for spawned sessions (e.g. 'work')",
    )
    group.add_argument(
        "--model",
        default="",
        help="Model override for spawned sessions (e.g. 'anthropic/claude-sonnet-4')",
    )
    group.add_argument(
        "--provider",
        default="",
        help="Provider override for spawned sessions (e.g. 'openrouter')",
    )
    group.add_argument(
        "--spawn-source",
        default="infinite-loop",
        help="Source tag for spawned sessions (passed as --source to hermes chat -q). "
        "Default: 'infinite-loop'. Set to empty string '' for no source tag.",
    )

    # ── 13. Webhook / HTTP ──────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Webhook / HTTP",
        "Webhook server, SSE dashboard, and HTTP callback for iteration data",
    )
    group.add_argument(
        "--webhook-port",
        type=int,
        default=0,
        help="Port for HTTP webhook server (0=disabled). POST /webhook triggers iteration, GET /health, GET /status",
    )
    group.add_argument(
        "--http-callback",
        default="",
        help="HTTP POST URL for iteration JSON (like --notify-cmd but via HTTP)",
    )

    # ── 14. Notifications ───────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Notifications",
        "Desktop, mobile, and shell-command notifications on iteration events",
    )
    group.add_argument(
        "--notify-cmd",
        default="",
        help="Shell command to run after each iteration (receives JSON on stdin)",
    )
    group.add_argument(
        "--on-error-cmd",
        default="",
        help="Shell command when an iteration fails (JSON on stdin)",
    )
    group.add_argument(
        "--notify-desktop",
        action="store_true",
        help="Send desktop notifications via notify-send on each iteration result (Linux only)",
    )
    group.add_argument(
        "--notify-on-completion",
        action="store_true",
        help="Send a summary notification when the daemon finishes",
    )
    group.add_argument(
        "--notify-pushbullet",
        default="",
        help="Pushbullet API access token for mobile notifications. "
        "If set, sends iteration results to your phone. "
        "Get token at https://www.pushbullet.com/#settings",
    )
    group.add_argument(
        "--notify-ntfy",
        default="",
        help="ntfy topic name for push notifications. "
        "If set, sends iteration results via ntfy.sh (or your own server with --notify-ntfy-server). "
        "Example: 'my-loop-alerts'",
    )
    group.add_argument(
        "--notify-ntfy-server",
        default="https://ntfy.sh",
        help="ntfy server URL (default: https://ntfy.sh). "
        "Use a self-hosted ntfy server URL for private notifications.",
    )

    # ── 15. Logging ─────────────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Logging", "Daemon log file with automatic rotation"
    )
    group.add_argument(
        "--log-file",
        default="",
        help="Path to daemon log file (e.g. /tmp/infinite-loop.log). Adds file logging alongside stdout.",
    )
    group.add_argument(
        "--log-max-mb",
        type=int,
        default=10,
        help="Max log file size in MB before rotation (default: 10). Only used with --log-file.",
    )

    # ── 16. Status / Dashboard ──────────────────────────────────────────────
    group = parser.add_argument_group(
        "Status & Dashboard",
        "JSON status file and self-contained HTML dashboard for monitoring",
    )
    group.add_argument(
        "--status-html",
        default="",
        help="Path to self-contained HTML status dashboard (e.g. /tmp/loop-status.html). "
        "Updated after each iteration. Auto-refreshes every 30s in the browser.",
    )
    group.add_argument(
        "--status-file",
        default="",
        help="Path to write one-line JSON status file for external monitoring "
        "(e.g. /tmp/loop-status.json). Updated after each iteration.",
    )

    # ── 17. Ledger Management ───────────────────────────────────────────────
    group = parser.add_argument_group(
        "Ledger Management",
        "Control the persistence and lifecycle of the iteration ledger",
    )
    group.add_argument(
        "--keep-iterations",
        type=int,
        default=0,
        help="Auto-shrink ledger to keep only last N iterations (0=keep all). Removes when > 2N.",
    )
    group.add_argument(
        "--force-reset",
        action="store_true",
        help="Clear existing ledger and start fresh",
    )
    group.add_argument(
        "--tag",
        default="",
        help="Label/identifier for the run (e.g. 'project:fix-auth')",
    )

    # ── 18. Archiving ───────────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Archiving",
        "Archive old iteration files to a separate directory with retention policies",
    )
    group.add_argument(
        "--archive-dir",
        default=os.path.expanduser("~/.hermes/infinite-loop-archives"),
        help="Directory to store archived iteration files (default: ~/.hermes/infinite-loop-archives)",
    )
    group.add_argument(
        "--archive-retention",
        type=int,
        default=30,
        help="Days to keep archived iterations (0=keep forever, default: 30)",
    )
    group.add_argument(
        "--archive-max-size",
        type=int,
        default=0,
        help="Max total size of archive directory in MB before oldest files are purged "
        "(0=unlimited, default: 0). Combined with --archive-retention, the stricter constraint wins.",
    )

    # ── 19. File Watcher ────────────────────────────────────────────────────
    group = parser.add_argument_group(
        "File Watcher",
        "Watch files or directories for changes to trigger new iterations",
    )
    group.add_argument(
        "--watch-dir",
        default="",
        help="Watch a directory/file for changes and trigger an iteration when a file is modified. Uses os.stat() polling.",
    )
    group.add_argument(
        "--watch-poll",
        type=float,
        default=5.0,
        help="File watcher poll interval in seconds (default: 5.0, only used with --watch-dir)",
    )

    # ── 20. Hermes Worker ───────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Hermes Worker",
        "Embedded or external Hermes worker connection for spawned sessions",
    )
    group.add_argument(
        "--worker-url",
        default="auto",
        help="Hermes worker URL. 'auto' (default) = start worker internally. "
        "http://host:port = connect to external worker. "
        "'' = direct subprocess mode (no worker).",
    )

    # ── 21. Spawned Session Flags ───────────────────────────────────────────
    group = parser.add_argument_group(
        "Spawned Session Flags",
        "Flags forwarded to spawned Hermes sessions (chat -q mode)",
    )
    group.add_argument(
        "--use-library",
        action="store_true",
        help="Use AIAgent.run_conversation() in-process instead of spawning "
        "a subprocess. Falls back to subprocess mode automatically if the "
        "AIAgent library is not importable. Compatible with --workers > 1 "
        "(uses multiprocessing for true parallelism).",
    )
    group.add_argument(
        "--pass-session-id",
        action="store_true",
        help="Pass session ID to spawned sessions. The spawned Hermes session "
        "prints its session_id at the end of output. In subprocess mode, the "
        "daemon extracts it and stores it in the ledger as spawned_session_id. "
        "In library mode, the session_id is obtained directly from AIAgent.",
    )
    group.add_argument(
        "--checkpoints",
        action="store_true",
        help="Enable file checkpoints in spawned sessions. Passes --checkpoints "
        "to the spawned chat -q command (subprocess mode) or sets "
        "checkpoints_enabled=True (library mode). Auto-enabled when --git is set.",
    )
    group.add_argument(
        "--resume",
        action="store_true",
        help="Chain spawned sessions across iterations — each new session inherits "
        "the full conversation history of the previous one via --resume SESSION_ID. "
        "Requires --pass-session-id to populate the session_id in the ledger.",
    )
    group.add_argument(
        "--skills",
        default="",
        help="Skills to preload in spawned Hermes sessions (comma-separated or repeat flag). "
        "For subprocess mode only; ignored in library mode.",
    )
    group.add_argument(
        "--ignore-rules",
        action="store_true",
        help="Start spawned sessions without loading AGENTS.md, memory, or rules "
        "(clean-slate mode). Passes --ignore-rules to spawned hermes chat -q.",
    )
    group.add_argument(
        "--ignore-user-config",
        action="store_true",
        help="Pass --ignore-user-config to spawned sessions so they skip "
        "~/.hermes/config.yaml and fall back to built-in defaults.",
    )
    group.add_argument(
        "--yolo",
        action="store_true",
        help="Bypass all dangerous command approval prompts in spawned sessions. "
        "Combine with --ignore-rules for fully autonomous operation.",
    )
    group.add_argument(
        "--safe-mode",
        action="store_true",
        help="Troubleshooting mode: disable ALL customizations in spawned sessions — "
        "user config, AGENTS.md/memory injection, plugins, and MCP servers. "
        "Implies --ignore-user-config and --ignore-rules. Passes --safe-mode to spawned chat -q.",
    )
    group.add_argument(
        "--accept-hooks",
        action="store_true",
        help="Auto-approve shell hooks in spawned sessions. "
        "Passes --accept-hooks to spawned hermes chat -q.",
    )
    group.add_argument(
        "--worktree",
        action="store_true",
        help="Run spawned sessions in an isolated git worktree. "
        "Passes --worktree to spawned hermes chat -q.",
    )
    group.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="Resume the most recent session in spawned sessions. "
        "Passes --continue to spawned hermes chat -q.",
    )

    # ── 22. Startup & Debug ─────────────────────────────────────────────────
    group = parser.add_argument_group(
        "Startup & Debug",
        "Preflight checks, dry-run, self-test, config loading, startup delay, quiet output, and status",
    )
    group.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the verbose startup banner and per-iteration headers. Shows only compact "
        "one-line status updates. Ideal for background daemon runs where output noise is "
        "undesirable.",
    )
    group.add_argument(
        "--startup-delay",
        type=float,
        default=0.0,
        help="Wait N seconds before the first iteration (default: 0). Useful for debugging.",
    )
    group.add_argument(
        "--preflight",
        action="store_true",
        help="Run preflight health checks and exit (or before loop when --run is used). "
        "Checks: hermes binary, workdir, git repo, sentinel, context/goals/schema files, "
        "webhook port, disk space.",
    )
    group.add_argument(
        "--preflight-fail-fast",
        action="store_true",
        help="Exit immediately on the first preflight check failure.",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without spawning any sessions",
    )
    group.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test suite and exit (groups/cases auto-detected at runtime)",
    )
    group.add_argument(
        "--save-config",
        default="",
        help="Save current configuration to a JSON file and exit. Path to output file.",
    )
    group.add_argument(
        "--config",
        default="",
        help="Load configuration from a JSON file. Overrides default values, command-line flags take precedence.",
    )
    group.add_argument(
        "--color",
        default="auto",
        choices=["auto", "always", "never"],
        help="Colorize CLI output: 'auto' (default, uses ANSI when stdout is a TTY), "
        "'always' (force colors even when piped), "
        "'never' (disable all color). "
        "Also respects the NO_COLOR environment variable.",
    )
    group.add_argument(
        "--completion-script",
        default="",
        choices=["bash", "zsh"],
        help="Generate and print a shell completion script for bash or zsh "
        "by introspecting the live argparse parser. "
        "Always up-to-date -- never manually edit completion scripts again. "
        "Example: --completion-script bash | source /dev/stdin",
    )
    group.add_argument(
        "--check-env",
        action="store_true",
        help="Validate the .env file for typos, unknown variables, and common mistakes. "
        "Checks every INFINITE_LOOP_* variable against the canonical list of recognized "
        "variables and suggests corrections for misspelled names. "
        "Pre-argparse -- no --goal required. "
        "Example: python3 -m hermes_loop --check-env",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="Read the ledger and display a compact colorized status summary. "
        "Shows daemon status, iteration count, success/error counts, duration, "
        "goal, last iteration summary, and quick stop/pause/log commands. "
        "Pre-argparse -- no --goal required. "
        "Example: python3 -m hermes_loop --status",
    )
    group.add_argument(
        "--explain",
        default="",
        help="Show detailed help for a specific CLI flag. "
        "Accepts full flag names or unambiguous prefixes (e.g., 'cooldown', "
        "'convergence-stop', 'use-lib'). "
        "Displays: group, type, default, full description, aliases, related "
        "flags, and a usage example. "
        "Pre-argparse -- no --goal required. "
        "Example: python3 -m hermes_loop --explain workers",
    )
    group.add_argument(
        "--help-topic",
        default="",
        help="Show all flags and descriptions for a single argument group. "
        "Accepts group names (case-insensitive, prefix match) — e.g., "
        "'notifications', 'git', 'toolsets'. "
        "Shows available groups if no match is found. "
        "Pre-argparse — no --goal required. "
        "Example: python3 -m hermes_loop --help-topic notifications",
    )
    group.add_argument(
        "--init",
        action="store_true",
        help="Interactive setup wizard — walks you through the most common "
        "configuration options step by step and generates a .env file. "
        "Ideal for first-time users. "
        "Alias: --wizard. "
        "Pre-argparse -- no --goal required. "
        "Example: python3 -m hermes_loop --init",
    )
    group.add_argument(
        "--wizard",
        action="store_true",
        help="Alias for --init. Interactive setup wizard that generates "
        "a .env file by asking about goal, workers, git, notifications, "
        "and other common settings. "
        "Pre-argparse -- no --goal required. "
        "Example: python3 -m hermes_loop --wizard",
    )
    group.add_argument(
        "--doctor",
        action="store_true",
        help="Run comprehensive self-diagnosis and exit. Checks hermes binary, "
        "PATH, .env file validity, git repo, Python version, disk space, "
        "required scripts, shell completion, and gateway connectivity. "
        "Reports pass/warn/fail per check with actionable suggestions. "
        "Pre-argparse -- no --goal required. "
        "Example: python3 -m hermes_loop --doctor",
    )

    return parser


def main():
    # Check --color before argparse so pre-argparse flags respect it too
    color_mode = "auto"
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--color" and i + 2 < len(sys.argv):
            color_mode = sys.argv[i + 2]
            break
        if arg.startswith("--color="):
            color_mode = arg.split("=", 1)[1]
            break
    configure_color_mode(color_mode)

    # Check --version before argparse to avoid required-arg conflicts
    if "--version" in sys.argv:
        print(f"infinite-loop daemon v{LAUNCH_LOOP_VERSION}")
        sys.exit(0)

    # Check --self-test before argparse to avoid required --goal conflict
    if "--self-test" in sys.argv:
        result = _run_self_test()
        sys.exit(0 if result["failed"] == 0 else 1)

    # Check --list-flags / --list-groups before argparse to avoid required --goal conflict
    if "--list-flags" in sys.argv or "--list-groups" in sys.argv:
        _list_flags(show_help=("--list-flags" in sys.argv))
        sys.exit(0)

    # Check --examples before argparse to avoid required --goal conflict
    if "--examples" in sys.argv:
        _list_examples()
        sys.exit(0)

    # Check --completion-script before argparse to avoid required --goal conflict
    comp_script = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--completion-script" and i + 2 < len(sys.argv):
            comp_script = sys.argv[i + 2]
            break
        if arg.startswith("--completion-script="):
            comp_script = arg.split("=", 1)[1]
            break
    if comp_script:
        parser = _create_parser(for_introspection=True)
        if comp_script == "bash":
            print(generate_bash_completion(parser))
        elif comp_script == "zsh":
            print(generate_zsh_completion(parser))
        sys.exit(0)

    # Check --explain before argparse to avoid required --goal conflict
    explain_flag = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--explain" and i + 2 < len(sys.argv):
            explain_flag = sys.argv[i + 2]
            break
        if arg.startswith("--explain="):
            explain_flag = arg.split("=", 1)[1]
            break
    if explain_flag:
        configure_color_mode(color_mode)
        _explain_flag(explain_flag)
        sys.exit(0)

    # Check --help-topic before argparse to avoid required --goal conflict
    help_topic = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--help-topic" and i + 2 < len(sys.argv):
            help_topic = sys.argv[i + 2]
            break
        if arg.startswith("--help-topic="):
            help_topic = arg.split("=", 1)[1]
            break
    if help_topic:
        configure_color_mode(color_mode)
        _help_topic(help_topic)
        sys.exit(0)

    # Check --check-env before argparse to avoid required --goal conflict
    if "--check-env" in sys.argv:
        # Detect color mode early
        color_mode = "auto"
        for i, arg in enumerate(sys.argv[1:], 1):
            if arg.startswith("--color="):
                color_mode = arg.split("=", 1)[1]
                break
            if arg == "--color" and i + 1 < len(sys.argv):
                color_mode = sys.argv[i + 1]
                break
        configure_color_mode(color_mode)
        env_path = os.path.join(os.getcwd(), ".env")
        exit_code = check_env_file(env_path)
        sys.exit(exit_code)

    # Check --status before argparse to avoid required --goal conflict
    if "--status" in sys.argv:
        configure_color_mode(color_mode)
        _display_status()
        sys.exit(0)

    # Check --init / --wizard before argparse to avoid required --goal conflict
    if "--init" in sys.argv or "--wizard" in sys.argv:
        run_wizard()
        sys.exit(0)

    # Check --doctor before argparse to avoid required --goal conflict
    if "--doctor" in sys.argv:
        from .diagnosis import run_diagnosis, print_diagnosis_report

        checks = run_diagnosis()
        print_diagnosis_report(checks, version=LAUNCH_LOOP_VERSION)
        sys.exit(0)

    # Friendly error if --goal is missing (before argparse dry error)
    standalone_flags = {
        "--version",
        "--self-test",
        "--dry-run",
        "--help",
        "-h",
        "--list-flags",
        "--list-groups",
        "--examples",
        "--check-env",
        "--status",
        "--explain",
        "--help-topic",
        "--init",
        "--wizard",
        "--doctor",
    }
    arg_set = set(sys.argv[1:])
    has_goal = any(
        i + 1 < len(sys.argv) and sys.argv[i] == "--goal" for i in range(len(sys.argv))
    )
    has_goals_file = any(
        i + 1 < len(sys.argv) and sys.argv[i] == "--goals-file"
        for i in range(len(sys.argv))
    )
    env_hint = ""
    # Check if .env exists in the project root for an actionable hint
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, ".."))
        env_path = os.path.join(project_root, ".env")
        if os.path.isfile(env_path):
            env_hint = "\nOr use 'bash run.sh' to launch with your .env configuration"
    except Exception:
        pass

    if not has_goal and not has_goals_file and not arg_set & standalone_flags:
        parser = argparse.ArgumentParser(
            description=f"Infinite Loop Daemon v{LAUNCH_LOOP_VERSION}",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        print(
            "ERROR: --goal is required (or use --goals-file for batch mode)\n",
            file=sys.stderr,
        )
        parser.print_usage()
        print(
            "See 'python3 -m hermes_loop --help' for full options",
            file=sys.stderr,
        )
        print(
            "See 'python3 -m hermes_loop --examples' for usage patterns",
            file=sys.stderr,
        )
        print(
            "See 'python3 -m hermes_loop --init' for interactive setup wizard",
            file=sys.stderr,
        )
        if env_hint:
            print(env_hint, file=sys.stderr)
        sys.exit(1)

    parser = _create_parser()
    args = parser.parse_args()
    toolsets_list = [t.strip() for t in args.toolsets.split(",") if t.strip()]

    # Ensure delegation is in toolsets
    if "delegation" not in toolsets_list:
        toolsets_list.append("delegation")
        _log("[INFO] Added 'delegation' to toolsets (required for subagent spawning)")

    # Set max_output_chars for use by _log_startup_banner
    set_max_output_chars(args.max_output_chars)

    # Validate
    if args.git_commit and not args.git:
        _log("[INFO] --git-commit implies --git, enabling --git automatically")
        args.git = True
    if args.workers < 1:
        _log("[ERROR] --workers must be >= 1")
        sys.exit(1)
    if args.max_idle_iterations > 0 and not args.git:
        _log(
            "[WARN] --max-idle-iterations requires --git to detect changes. Idle detection will be disabled."
        )
        args.max_idle_iterations = 0
    if args.use_library and args.workers > 1:
        _log("[NOTE] --use-library with --workers > 1 -> using multiprocessing.Pool")
    if args.checkpoints and not args.git:
        _log(
            "[INFO] --checkpoints auto-enabled (implied by --git is not set but flag is active)"
        )

    # Check hermes is available
    hermes_bin = find_hermes()
    if (
        not shutil.which(hermes_bin)
        and hermes_bin == "hermes"
        and not shutil.which("hermes")
    ):
        _log("[WARN] 'hermes' binary not found on PATH.")
        _log(
            "[WARN] Install: curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
        )
        _log(
            "[WARN] The loop will fail on the first iteration if hermes is not available."
        )

    # Preflight health checks
    if args.preflight or args.run:
        results = PreflightChecker.run_all(
            hermes_required=True,
            workdir=args.workdir,
            sentinel_path=args.shutdown_sentinel,
            webhook_port=args.webhook_port,
            context_file=args.context_file,
            goals_file=args.goals_file,
            schema_file=args.output_schema_file,
            check_git=args.git or args.git_commit,
            check_disk="/tmp",
            fail_fast=args.preflight_fail_fast,
        )
        _log(PreflightChecker.format_results(results))
        all_passed = all(r["passed"] for r in results)
        if args.preflight:
            _log("[PREFLIGHT] --preflight specified. Exiting.")
            sys.exit(0 if all_passed else 1)
        if not all_passed:
            _log(
                "[WARN] Some preflight checks failed. Continuing anyway (use --preflight-fail-fast to abort)."
            )

    _log(
        colorizer.subheader(
            "═══════════════════════════════════════════════════════════════════"
        )
    )
    _log(f"  {colorizer.header(f'Infinite Loop Daemon v{LAUNCH_LOOP_VERSION}')}")
    _log(
        colorizer.subheader(
            "═══════════════════════════════════════════════════════════════════"
        )
    )
    _log(
        f"  {colorizer.dim('Passing through to')} {colorizer.flag('run_loop()')}{colorizer.dim('...')}"
    )

    if not args.quiet:
        _log(
            f"  {colorizer.dim('Features:')} evolve | workers | cooldown | convergence | preflight"
        )
        _log(
            f"            {colorizer.dim('git | goals-file | webhook | SSE dashboard | heartbeat')}"
        )
        _log(
            f"            {colorizer.dim('desktop/Pushbullet/ntfy | library mode | yolo | safe-mode')}"
        )
        _log(
            f"            {colorizer.dim('self-test | status-html | checkpoint | resume | archiving')}"
        )
        _log(
            f"            {colorizer.tag_summary()} {colorizer.dim('summary')} | {colorizer.tag_suggest()} {colorizer.dim('smart fixes')} | {colorizer.flag('--examples')} | {colorizer.flag('--quiet')}"
        )
        _log("═══════════════════════════════════════════════════════════════════")

    # Clean up stale heartbeat files from previous daemon instances
    if args.heartbeat_timeout > 0:
        _cleanup_stale_heartbeats()

    if not args.quiet:
        _log(f"  Goal:           {args.goal}")
        _log(f"  Context:        {len(args.context)} chars")
        _log(f"  Toolsets:       {toolsets_list}")
        if args.context_file:
            _log(f"  Context file:   {args.context_file}")
        else:
            _log(f"  Context file:   (none, using --context)")
        _log(f"  Workdir:        {args.workdir or os.getcwd()}")
        _log(
            f"  Max iterations: {args.max_iterations if args.max_iterations > 0 else 'infinite'}"
        )
        _log(f"  Compact:        every {args.compact_every} iterations")
        _log(f"  Max turns:      {args.max_turns} per spawned session")
        _log(f"  Retry delay:    {args.retry_delay}s")
        _log(f"  Session timeout: {args.session_timeout}s")
        _log(f"  Hermes binary:  {hermes_bin}")
        mode_str = args.worker_url if args.worker_url else "(none, direct subprocess)"
        if args.worker_url == "auto":
            mode_str = "auto (embedded worker)"
        _log(f"  Worker URL:     {mode_str}")
        _log(f"  Evolve:         {'yes' if args.evolve else 'no'}")
        _log(f"  Git snapshots:  {'yes' if args.git else 'no'}")
        _log(f"  Auto-commit:    {'yes' if args.git_commit else 'no'}")
        _log(f"  Workers:        {args.workers}")
        _log(f"  Notify cmd:     {args.notify_cmd or 'none'}")
        _log(
            f"  Output cap:     {args.max_output_chars if args.max_output_chars > 0 else 'unlimited'} chars"
        )
        _log(
            f"  Max idle iters: {args.max_idle_iterations if args.max_idle_iterations > 0 else 'off'}"
        )
        _log(f"  Status file:    {args.status_file or 'none'}")
        _log(f"  Profile:        {args.profile or '(default)'}")
        _log(f"  Model:          {args.model or '(default)'}")
        _log(f"  Provider:       {args.provider or '(default)'}")
        _log(f"  HTTP callback:  {args.http_callback or 'none'}")
        _log(
            f"  Keep iterations:{args.keep_iterations if args.keep_iterations > 0 else 'all'}"
        )
        _log(f"  Archive dir:    {args.archive_dir or 'disabled'}")
        _log(
            f"  Archive retention: {args.archive_retention}d"
            if args.archive_retention > 0
            else "  Archive retention: forever"
        )
        _log(f"  Max retries:    {args.max_retries}")
        _log(f"  On-error cmd:   {args.on_error_cmd or 'none'}")
        _log(f"  Tag:            {args.tag or '(none)'}")
        _log(f"  Prompt suffix:  {args.prompt_suffix or '(none)'}")
        _log(f"  Force reset:    {'yes' if args.force_reset else 'no'}")
        _log(f"  Auto toolsets:  {'yes' if not args.no_auto_toolsets else 'no'}")
        _log(
            f"  Auto task type: {args.task_type if args.task_type != 'auto' else 'auto-detect'}"
        )
        _log(f"  Failure learn:  {'yes' if not args.no_failure_learning else 'no'}")
        _log(
            f"  Webhook port:   {args.webhook_port if args.webhook_port > 0 else 'disabled'}"
        )
        _log(f"  Log file:       {args.log_file or 'stdout only'}")
        _log(f"  HTML dashboard: {args.status_html or 'disabled'}")
        _log(f"  Watch dir:      {args.watch_dir or 'disabled'}")
        _log(f"  Watch poll:     {args.watch_poll}s")
        _log(f"  Cooldown:       {args.cooldown}s, mode={args.cooldown_mode}")
        _log(
            f"  Convergence:    {'stop at threshold=' + str(args.convergence_threshold) if args.convergence_stop else 'disabled'}"
        )
        _log(f"  Store git diff: {'yes' if args.store_git_diff else 'no'}")
        _log(f"  Use library:    {'yes' if args.use_library else 'no'}")
        _log(f"  Pass session ID:{'yes' if args.pass_session_id else 'no'}")
        _log(f"  Checkpoints:    {'yes' if args.checkpoints else 'no'}")
        _log(f"  Resume sessions:{'yes' if args.resume else 'no'}")
        _log(f"  Skills:         {args.skills or 'none'}")
        _log(f"  Ignore rules:   {'yes' if args.ignore_rules else 'no'}")
        _log(f"  YOLO mode:      {'yes' if args.yolo else 'no'}")
        _log(f"  Ignore user cfg:{'yes' if args.ignore_user_config else 'no'}")
        _log(f"  Spawn source:   {args.spawn_source or '(default)'}")
        _log(f"  Safe mode:      {'yes' if args.safe_mode else 'no'}")
        _log(f"  Accept hooks:   {'yes' if args.accept_hooks else 'no'}")
        _log(f"  Worktree:       {'yes' if args.worktree else 'no'}")
        _log(f"  Continue:       {'yes' if args.continue_session else 'no'}")
        _log(
            f"  Output schema:  {args.output_schema_file or 'inline' if args.output_schema else ('file: ' + args.output_schema_file) if args.output_schema_file else 'none'}"
        )
        _log(f"  Goals file:     {args.goals_file or 'none'}")
        _log(f"  Stop at goals:  {'yes' if args.stop_at_goals_end else 'no (wrap)'}")
        _log(f"  Track goals:    {'yes' if args.track_goals else 'no'}")
        _log(f"  Reset goals:    {'yes' if args.reset_goals else 'no'}")
        _log(f"  Dry run:        {'yes' if args.dry_run else 'no'}")
        _log(f"  Ledger:         {LEDGER_PATH}")
        _log(f"  Sentinel:       echo 'stop' > {args.shutdown_sentinel}")
        _log("")

    if not args.run:
        _log(f"  {colorizer.dim('Run with --run to start the actual loop.')}")
        _log("")
        if args.dry_run:
            # Environment variable validation (suggestive, not blocking)
            env_path = os.path.join(os.getcwd(), ".env")
            if os.path.isfile(env_path):
                vars_found, parse_errors = parse_env_vars_from_file(env_path)
                if parse_errors:
                    _log(f"  [WARN] {len(parse_errors)} parse error(s) in .env file:")
                    for err in parse_errors:
                        _log(f"    {err}")
                if vars_found:
                    env_results = validate_env_vars(vars_found)
                    issues = [
                        r
                        for r in env_results
                        if r["type"] in ("typo", "unknown", "deprecated", "warning")
                    ]
                    if issues:
                        _log(
                            f"  [{colorizer.tag_warn()}WARN] {len(issues)} env var issue(s) detected:"
                        )
                        for r in issues:
                            line = (
                                f"    {r['type'].upper()}: {r['key']} — {r['message']}"
                            )
                            _log(line)
                    else:
                        _log(
                            f"  [OK] .env variables validated ({len(vars_found)} recognized, no issues)"
                        )
            else:
                _log(
                    f"  [NOTE] No .env file found at {env_path} — using defaults/CLI flags"
                )
            _log("  [DRY RUN] No sessions will be spawned. Exiting.")
            sys.exit(0)

    # Resolve context
    resolved_context = args.context
    if args.context_file:
        try:
            with open(args.context_file) as cf:
                resolved_context = cf.read().strip()
            _log(
                f"[INFO] Read context from {args.context_file} ({len(resolved_context)} chars)"
            )
        except (FileNotFoundError, IOError) as e:
            _log(f"[ERROR] Could not read --context-file {args.context_file}: {e}")
            sys.exit(1)

    # Force reset
    if args.force_reset and os.path.exists(LEDGER_PATH):
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
    state["keep_iterations"] = args.keep_iterations
    state["tag"] = args.tag
    state["prompt_suffix"] = args.prompt_suffix
    state["max_turns"] = args.max_turns
    state["output_schema_file"] = args.output_schema_file or ""
    state["output_schema_inline"] = args.output_schema or ""
    state["yolo"] = args.yolo
    state["ignore_user_config"] = args.ignore_user_config
    state["spawn_source"] = args.spawn_source
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
        config_dict["version"] = LAUNCH_LOOP_VERSION
        os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config_dict, f, indent=2)
        _log(f"[CONFIG] Saved configuration to {config_path}")
        sys.exit(0)

    # Resolve task type
    resolved_task_type = args.task_type
    if resolved_task_type == "auto":
        resolved_task_type, _, _ = detect_task_type(args.goal)

    if args.run:
        if args.log_file:
            _init_daemon_log(args.log_file, args.log_max_mb)

        global _startup_file_snapshots
        workdir_for_snapshots = args.workdir or os.getcwd()
        for fname in (
            "hermes_loop/__init__.py",
            "hermes_loop/cli.py",
            "hermes_loop/loop.py",
            "launch-loop.py",
            "run.sh",
            ".env",
        ):
            fpath = os.path.join(workdir_for_snapshots, fname)
            snap = _snapshot_file(fpath)
            if snap is not None:
                _startup_file_snapshots[fpath] = snap
        if _startup_file_snapshots:
            _log(
                f"[AUTO-RELOAD] Monitoring {len(_startup_file_snapshots)} source files for hot-reload"
            )

        _log(f"  {colorizer.ok('Starting loop...')}")
        _log(
            f"  {colorizer.dim('Sentinel:')} {colorizer.flag('echo stop >')} {colorizer.value(args.shutdown_sentinel)}"
        )
        _log("")
        run_loop(
            goal=args.goal,
            context=resolved_context,
            toolsets=toolsets_list,
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
            keep_iterations=args.keep_iterations,
            archive_dir=args.archive_dir,
            archive_retention=args.archive_retention,
            archive_max_size=args.archive_max_size,
            max_retries=args.max_retries,
            on_error_cmd=args.on_error_cmd or None,
            tag=args.tag,
            prompt_suffix=args.prompt_suffix,
            max_turns=args.max_turns,
            auto_toolsets=not args.no_auto_toolsets,
            failure_learning=not args.no_failure_learning,
            html_dashboard=args.status_html,
            webhook_port=args.webhook_port,
            watch_dir=args.watch_dir,
            watch_poll=args.watch_poll,
            worker_url=args.worker_url,
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
            checkpoints=args.checkpoints,
            resume=args.resume,
            resume_session_id=state.get("resume_session_id", ""),
            skills=args.skills,
            ignore_rules=args.ignore_rules,
            yolo=args.yolo,
            ignore_user_config=args.ignore_user_config,
            spawn_source=args.spawn_source,
            safe_mode=args.safe_mode,
            accept_hooks=args.accept_hooks,
            worktree=args.worktree,
            continue_session=args.continue_session,
            track_goals=args.track_goals,
            reset_goals=args.reset_goals,
            heartbeat_timeout=args.heartbeat_timeout,
            quiet=args.quiet,
        )

    if args.notify_on_completion or args.notify_pushbullet or args.notify_ntfy:
        _send_completion_notification(
            state,
            notify_pushbullet=args.notify_pushbullet,
            notify_ntfy=args.notify_ntfy,
            notify_ntfy_server=args.notify_ntfy_server,
        )

    _log(f"[DONE] Daemon finished. Ledger at {LEDGER_PATH}")


if __name__ == "__main__":
    main()
