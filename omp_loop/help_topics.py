"""Help topics, examples, and introspection for the omp-loop CLI.

Extracted from cli.py to keep the CLI module focused on argparse setup
and the main() entry point.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from .color_utils import colorizer
from .config import LEDGER_PATH, VERSION, _get_data_dir
from .file_utils import extract_json_from_output, read_ledger, write_ledger


def _introspection_flags() -> dict[str, str]:
    """Return the introspection-only flags and their help text."""
    return {
        "--help": "Show the full detailed help with all flags and examples",
        "--list-flags": "Print all flags organized by group with help text (this view)",
        "--list-groups": "Print compact group names with flag counts",
        "--examples": "Print categorized real-world usage examples",
        "--version": "Print daemon version and exit",
        "--completion-script": "Generate shell completion script for bash or zsh from live argparse",
        "--status": "Read the ledger and display a compact status summary (no --goal required)",
        "--explain": "Show detailed help for a specific CLI flag (no --goal required)",
        "--help-topic": "Show all flags in a single argument group (no --goal required)",
        "--dump-env": "Print all known env vars with their current defaults and exit",
        "--healthcheck": "Run structured pipeline health check. Exits with a JSON report.",
        "--preflight": "Run environment health checks before starting the loop",
        "--doctor": "Run comprehensive self-diagnosis of the environment",
    }


def _list_flags(show_help: bool = True, parser=None) -> None:
    """Print all CLI flags organized by group. Used by --list-flags / --list-groups."""
    if parser is None:
        from .parser import _create_parser

        parser = _create_parser(for_introspection=True)

    group_map = {}
    for group in parser._action_groups:
        title = group.title
        if title in ("positional arguments", "optional arguments", "options"):
            continue
        entries = []
        for action in group._group_actions:
            if action.option_strings:
                flag = action.option_strings[0]
                help_text = action.help or ""
                help_short = help_text.split(".")[0].strip()[:80]
                entries.append((flag, help_short))
        if entries:
            group_map[title] = entries
    iflags = _introspection_flags()
    total_flags = sum(len(v) for v in group_map.values()) + len(iflags)
    header = f"omp-loop v{VERSION} — CLI Flags Reference"
    print()
    print(f"  {colorizer.colorize(header, 'bold', 'white')}")
    print(f"  {colorizer.dim(f'Total: {total_flags} flags')}")
    print()

    if show_help:
        for group_name, entries in group_map.items():
            print(f"  {colorizer.group_title(f'[{group_name}]')}")
            for flag, desc in entries:
                print(f"    {colorizer.flag(flag):38s}  {colorizer.dim(desc)}")
            print()
        print(f"  {colorizer.group_title('[Introspection]')}")
        for flag, desc in iflags.items():
            print(f"    {colorizer.flag(flag):38s}  {colorizer.dim(desc)}")
        print()
    else:
        for group_name, entries in group_map.items():
            print(f"  {colorizer.group_title(f'[{group_name}]')}  {colorizer.dim(f'({len(entries)} flags)')}")
        print(f"  {colorizer.group_title('[Introspection]')}  {colorizer.dim(f'({len(iflags)} flags)')}")


def _list_examples() -> None:
    data_dir = _get_data_dir()
    """Print categorized usage examples. Used by --examples flag."""
    header = f"omp-loop v{VERSION} — Usage Examples"
    print()
    print(f"  {colorizer.colorize(header, 'bold', 'white')}")
    print(f"  {colorizer.dim('=' * 48)}")
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
    _cmd('omp-loop --goal "Fix all ESLint errors" --run')
    print()
    _comment("One-shot preview (no loop started)")
    _cmd('omp-loop --goal "Fix tests" --dry-run')
    print()
    _comment("Run to completion (10 iterations then stop)")
    _cmd('omp-loop --goal "Refactor auth" --max-iterations 10 --run')
    print()

    _section("Git-Integrated Evolution")
    _comment("Auto-detect, fix, and commit — ideal for linting/formatting")
    _cmd('omp-loop --goal "Fix lint errors" --git --git-commit --run')
    print()
    _comment("Stop once all changes are made")
    _cmd('omp-loop --goal "Clean up warnings" --git --git-commit --convergence-stop --run')
    print()

    _section("Batch / Goals-File Processing")
    _comment("Process a list of goals, one per line")
    _cmd("omp-loop --goals-file goals.txt --run")
    print()
    _comment("Batch with 5 parallel workers, stop when done")
    _cmd("omp-loop --goals-file todos.txt --workers 5 --stop-at-goals-end --run")
    print()

    _section("Notifications & Monitoring")
    _comment("Get desktop notifications after each iteration (Linux)")
    _cmd('omp-loop --goal "Fix bugs" --notify-desktop --run')
    print()
    _comment("Push to phone via ntfy.sh")
    _cmd('omp-loop --goal "Run tests" --notify-ntfy my-alerts --run')
    print()
    _comment("Real-time HTML dashboard + JSON status file")
    _cmd(f'omp-loop --goal "Refactor" --status-html {data_dir}/dash.html --status-file {data_dir}/status.json --run')
    print()

    _section("Monitoring & Control")
    _comment("Follow iteration progress in real-time")
    _cmd(f"tail -f {data_dir}/infinite-loop.log")
    print()
    _comment("Check the full iteration ledger")
    _cmd(f"cat {data_dir}/infinite-loop-state.json | python3 -m json.tool")
    print()
    _comment("Control a running daemon")
    _cmd(f"echo 'stop'    > {data_dir}/infinite-loop-stop")
    _cmd(f"echo 'pause'   > {data_dir}/infinite-loop-stop")
    _cmd(f"echo 'resume'  > {data_dir}/infinite-loop-stop")
    print()

    _section("Advanced Patterns")
    _comment("Multi-worker parallel analysis")
    _cmd('omp-loop --goal "Review all modules" --workers 4 --git --run')
    print()
    _comment("Structured JSON logs for programmatic consumption")
    _cmd("omp-loop --goal \"Fix tests\" --json-logs --run 2>&1 | jq '.summary'")
    print()
    _comment("File watcher — auto-trigger when files change")
    _cmd('omp-loop --goal "Run on change" --watch-dir src/ --run')
    print()
    _comment("Webhook-triggered iteration server")
    _cmd('omp-loop --goal "Trigger me" --webhook-port 9090 --run')
    _comment("Then POST /webhook to trigger an iteration")
    print()

    _section("Help & Diagnostics")
    _comment("Quick overview of all flags by category")
    _cmd("omp-loop --list-flags")
    _comment("Full detailed flag reference")
    _cmd("omp-loop --help")
    _comment("Detailed help on any single flag")
    _cmd("omp-loop --explain workers")
    _cmd("omp-loop --explain cooldown")
    _comment("Run environment checks before starting")
    _cmd("omp-loop --preflight")
    _comment("Full self-diagnosis")
    _cmd("omp-loop --doctor")
    _comment("Quick status of running daemon")
    _cmd("omp-loop --status")
    _comment("View all env vars with defaults")
    _cmd("omp-loop --dump-env")
    _comment("Pipeline health check")
    _cmd("omp-loop --healthcheck")
    print()

    _section("Flag Reference")
    _comment("Detailed help on any single CLI flag")
    _cmd("omp-loop --explain git")
    _cmd("omp-loop --explain converge")
    _cmd("omp-loop --explain workers")
    _comment("Help for a specific argument group")
    _cmd("omp-loop --help-topic notifications")
    _cmd("omp-loop --help-topic git")
    _comment("List all flags")
    _cmd("omp-loop --list-flags")
    _cmd("omp-loop --list-groups")
    print()


def _run_healthcheck() -> None:
    """Run structured health check and exit with a JSON report."""
    checks = []
    ts = datetime.now(timezone.utc).isoformat()

    # 1. Python version
    v = sys.version_info
    checks.append(
        {
            "name": "python_version",
            "status": "healthy" if v >= (3, 10) else "critical",
            "detail": f"Python {v.major}.{v.minor}.{v.micro}",
            "suggestion": "" if v >= (3, 10) else "Install Python >= 3.10",
        }
    )

    # 2. omp binary
    omp_bin = shutil.which("omp")
    if omp_bin:
        checks.append(
            {
                "name": "omp_binary",
                "status": "healthy",
                "detail": f"Found at {omp_bin}",
                "suggestion": "",
            }
        )
    else:
        checks.append(
            {
                "name": "omp_binary",
                "status": "critical",
                "detail": "'omp' not found on PATH",
                "suggestion": "Install the omp coding agent",
            }
        )

    # 3. JSON parsing
    extraction_ok = extract_json_from_output('{"test": true}') is not None
    checks.append(
        {
            "name": "json_extraction",
            "status": "healthy" if extraction_ok else "degraded",
            "detail": "JSON extraction works" if extraction_ok else "JSON extraction failed",
            "suggestion": "" if extraction_ok else "Check file_utils.extract_json_from_output",
        }
    )

    # 4. Ledger I/O
    test_data = {"status": "running", "iterations": [], "stats": {}, "total_iterations": 0, "last_updated": ts, "healthcheck": True, "timestamp": ts}
    write_ledger(test_data)
    ledger_read = read_ledger()
    ledger_ok = ledger_read is not None and ledger_read.get("healthcheck")
    checks.append(
        {
            "name": "ledger_io",
            "status": "healthy" if ledger_ok else "critical",
            "detail": "Ledger read/write OK" if ledger_ok else "Ledger I/O failed",
            "suggestion": "" if ledger_ok else f"Check {LEDGER_PATH} permissions",
        }
    )

    # 5. Git
    git_bin = shutil.which("git")
    checks.append(
        {
            "name": "git_availability",
            "status": "healthy" if git_bin else "degraded",
            "detail": f"Found at {git_bin}" if git_bin else "git not on PATH",
            "suggestion": "Install git from your package manager" if not git_bin else "",
        }
    )

    # Summary
    status_counts = {"healthy": 0, "degraded": 0, "critical": 0}
    for c in checks:
        status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1

    if status_counts.get("critical", 0) > 0:
        overall = "critical"
        exit_code = 2
    elif status_counts.get("degraded", 0) > 0:
        overall = "degraded"
        exit_code = 1
    else:
        overall = "healthy"
        exit_code = 0

    report = {
        "status": overall,
        "checks": checks,
        "summary": status_counts,
        "version": VERSION,
        "timestamp": ts,
    }

    print(json.dumps(report, indent=2))
    sys.exit(exit_code)


def _run_doctor() -> None:
    """Run comprehensive self-diagnosis of the environment."""
    from .color_utils import colorizer

    c = colorizer

    print(f"\n  {c.header('═══════════════ omp-loop Doctor ═══════════════')}\n")

    # Python
    v = sys.version_info
    py_ok = v >= (3, 10)
    print(f"  {c.value('Python:')}      {c.tag_ok() if py_ok else c.tag_fail()} {v.major}.{v.minor}.{v.micro}")
    if not py_ok:
        print(f"    {c.dim('Need Python >= 3.10')}")

    # omp binary
    omp_bin = shutil.which("omp")
    if omp_bin:
        try:
            r = subprocess.run([omp_bin, "--version"], capture_output=True, text=True, timeout=10)
            omp_ver = (r.stdout or "").strip()[:80]
        except Exception:
            omp_ver = omp_bin
        print(f"  {c.value('omp binary:'):10s} {c.tag_ok()} {omp_ver}")
    else:
        print(f"  {c.value('omp binary:'):10s} {c.tag_fail()} Not found on PATH")

    # PATH
    path_dirs = os.environ.get("PATH", "").split(":")
    print(f"  {c.value('PATH dirs:'):10s} {c.dim(str(len(path_dirs)))}")

    # .env
    if os.path.exists(".env"):
        print(f"  {c.value('.env:'):10s} {c.tag_ok()} Found")
    else:
        print(f"  {c.value('.env:'):10s} {c.dim('Not found (optional)')}")

    # Git
    git_bin = shutil.which("git")
    if git_bin:
        try:
            r = subprocess.run([git_bin, "--version"], capture_output=True, text=True, timeout=5)
            print(f"  {c.value('git:'):10s} {c.tag_ok()} {(r.stdout or '').strip()[:60]}")
        except Exception:
            print(f"  {c.value('git:'):10s} {c.tag_ok()} {git_bin}")
    else:
        print(f"  {c.value('git:'):10s} {c.dim('Not found')}")

    # Ledger
    if os.path.exists(LEDGER_PATH):
        size = os.path.getsize(LEDGER_PATH)
        print(f"  {c.value('Ledger:'):10s} {c.dim(f'{size:,} bytes at {LEDGER_PATH}')}")
    else:
        print(f"  {c.value('Ledger:'):10s} {c.dim('Not found (daemon not running)')}")

    # Environment
    dotted_envars = sorted(k for k in os.environ if k.startswith("INFINITE_LOOP_") or k.startswith("OMP_LOOP_"))
    if dotted_envars:
        print(f"  {c.value('Env vars:'):10s} {c.dim(str(len(dotted_envars)))} set")
        for ev in dotted_envars:
            print(f"    {c.dim(ev)}={c.value(os.environ[ev][:60])}")
    else:
        print(f"  {c.value('Env vars:'):10s} {c.dim('None set')}")

    print(f"\n  {c.header('══════════════════════════════════════════════')}\n")


def _explain_flag(flag_name: str, parser=None) -> None:
    """Show detailed help for a single CLI flag."""
    if parser is None:
        from .parser import _create_parser

        parser = _create_parser(for_introspection=True)

    alt_names = {}
    for alt in (f"--{flag_name}", f"--{flag_name.replace('_', '-')}", flag_name):
        alt_names[alt] = True

    for action in parser._actions:
        matches = [
            o
            for o in action.option_strings
            if o in alt_names or o.lstrip("-").replace("-", "_") == flag_name.replace("-", "_")
        ]
        if matches:
            print(f"\n  {colorizer.colorize('Flag:', 'bold')}  {colorizer.flag(matches[0])}")
            if len(action.option_strings) > 1:
                print(
                    f"  {colorizer.colorize('Aliases:', 'bold')} {', '.join(colorizer.dim(a) for a in action.option_strings)}"
                )
            if action.help:
                print(f"  {colorizer.colorize('Help:', 'bold')}   {action.help}")
            if action.default is not None and action.default is not argparse.SUPPRESS:
                print(f"  {colorizer.colorize('Default:', 'bold')} {colorizer.dim(str(action.default))}")
            if action.choices:
                print(f"  {colorizer.colorize('Choices:', 'bold')} {', '.join(action.choices)}")
            print()
            return

    print(f"\n  {colorizer.colorize('Unknown flag:', 'bold')} {flag_name}")
    print(f"  {colorizer.dim('Use --list-flags to see all available flags.')}\n")


def _help_topic(topic: str, parser=None) -> None:
    """Show all flags in a single argument group."""
    if parser is None:
        from .parser import _create_parser

        parser = _create_parser(for_introspection=True)

    topic_lower = topic.lower().replace("-", " ").replace("_", " ")
    if topic_lower in ("introspection", "help"):
        iflags = _introspection_flags()
        print(f"\n  {colorizer.group_title('[Introspection]')}")
        for flag, desc in iflags.items():
            print(f"    {colorizer.flag(flag):38s}  {colorizer.dim(desc)}")
        print()
        return

    for group in parser._action_groups:
        title = (group.title or "").lower()
        if topic_lower in title or title in topic_lower:
            print(f"\n  {colorizer.group_title(f'[{group.title}]')}")
            for action in group._group_actions:
                if action.option_strings:
                    flag = action.option_strings[0]
                    help_text = (action.help or "")[:100]
                    print(f"    {colorizer.flag(flag):38s}  {colorizer.dim(help_text)}")
            print()
            return

    print(f"\n  {colorizer.colorize('Unknown topic:', 'bold')} {topic}")
    print(f"  {colorizer.dim('Available topics:')}")
    for group in parser._action_groups:
        title = group.title
        if title not in ("positional arguments", "optional arguments", "options"):
            print(f"    {colorizer.flag(group.title or '')}")
    print("    introspection")
    print()


def _render_status(state: dict) -> None:
    """Render a compact status summary from the ledger."""
    from .color_utils import colorizer

    c = colorizer

    iters = state.get("iterations", [])
    total = state.get("total_iterations", 0)
    status = state.get("status", "unknown")
    stats = state.get("stats", {})
    total_dur = stats.get("total_duration_seconds", 0)

    dur_str = f"{total_dur:.0f}s"
    if total_dur >= 60:
        dur_str += f" ({total_dur / 60:.1f}m)"

    print()
    status_header = f"omp-loop v{VERSION} \u2014 Status"
    print(f"  {c.colorize(status_header, 'bold', 'white')}")
    print(f"  {c.dim('=' * 44)}")
    print(f"  {c.value('Status:')}      {c.flag(status)}")
    print(f"  {c.value('Iterations:')}   {c.flag(str(total))}")
    print(f"  {c.value('Duration:')}     {c.dim(dur_str)}")

    last = iters[-1] if iters else None
    if last:
        print(f"  {c.value('Last:')}         #{last.get('n', '?')} — {(last.get('summary') or '')[:80]}")

    errors = sum(1 for it in iters if it.get("error"))
    if errors:
        print(f"  {c.value('Errors:')}       {c.tag_fail()}{errors}")
    print()
