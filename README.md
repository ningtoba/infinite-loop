# Infinite Loop Daemon — v14.18.0

A self-looping background daemon that spawns Hermes sessions with **real tools**
(terminal, file, web, skills, browser, memory) **and** `delegate_task()` for
multi-level delegation trees. It iterates autonomously, tracks progress in a
JSON ledger, and can batch-process hundreds of goals in sequence.

> **Changelog**: See [CHANGELOG.md](./CHANGELOG.md) for the complete version history.
> **Contributing**: See [CONTRIBUTING.md](./CONTRIBUTING.md) for onboarding and development guide.
> **Quick reference**: Use `make help` for convenience targets (run, dry-run, self-test, status, stop, clean).

## Origin

This is the **infinite-loop skill** from the [Hermes Agent](https://hermes-agent.nousresearch.com)
skills repository, extracted into a standalone project. It mirrors the original
skill for independent use, development, and documentation.

**Author**: Hermes Agent (Nous Research) — MIT license.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [Scripts](#scripts)
- [All CLI Flags](#all-cli-flags)
- [Configuration (.env)](#configuration-env)
- [Two Modes](#two-modes)
  - [Daemon Mode (launch-loop.py)](#daemon-mode-launch-looppy)
  - [In-Session Self-Loop (session-self-loop.py)](#in-session-self-loop-session-self-looppy)
- [Feature Deep-Dive](#feature-deep-dive)
  - [Actionable Error Suggestions](#actionable-error-suggestions)
  - [Self-Test Mode](#self-test-mode)
  - [Progress Classification](#output-progress-classification)
  - [Convergence Detection](#convergence-detection)
  - [Adaptive Cooldown](#adaptive-cooldown)
  - [Context Propagation](#context-propagation)
  - [Self-Modification](#self-modification)
  - [Hermes Worker Mode](#hermes-worker-mode)
  - [Webhook & REST Control](#webhook-rest-control)
  - [Dashboard v3 SSE](#dashboard-v3-sse)
  - [Session Self-Healing Heartbeat](#session-self-healing-heartbeat)
  - [Pushbullet & ntfy Notifications](#pushbullet-ntfy-notifications)
  - [Preflight Health Checks](#preflight-health-checks)
  - [Ledger Archiving](#ledger-archiving)
  - [Multi-Profile Goals](#multi-profile-goals)
  - [AIAgent Library Mode](#aiagent-library-mode)
  - [Shell Completion](#shell-completion)
- [References](#references)
- [Pitfalls](#pitfalls)

---

## Quick Start

```bash
# One command — reads everything from .env
bash run.sh

# Or with overrides:
bash run.sh --dry-run                           # Preview config, don't run
bash run.sh --max-iterations 10 --quiet         # Run 10 iterations, no banner
bash run.sh --goal "Fix lint errors" --force-reset  # Override goal, clean start

# Or use the Makefile:
make env                                        # Create .env from .env.example
make dry-run                                    # Preview config
make run                                        # Run with .env config
make run ARGS="--goal 'fix lint errors' --git"  # Run with extra flags
make self-test                                  # Run self-tests (count auto-detected at runtime)
make examples                                   # Print categorized usage examples
make list-flags                                 # Print all 90 flags organized by group
make list-groups                                # Print group names with flag counts

# Monitor progress:
cat /tmp/infinite-loop-state.json | python3 -m json.tool    # full ledger
bash scripts/inspect-ledger.sh                               # formatted view
bash scripts/inspect-ledger.sh --watch                       # auto-refresh
bash scripts/inspect-ledger.sh --summary                     # compact one-liner
```

**Stop the loop**:
```bash
echo "stop" > /tmp/infinite-loop-stop
```

---

## Architecture

```
You (current Hermes agent session / terminal)
  │
  └─ python3 launch-loop.py --goal "..." --run
      │
      │  hermes_loop/ package runs the loop in the background:
      │
      ├─ iter 1:  spawns `hermes chat -q "<prompt>" -t terminal,file,delegation,... -Q --max-turns 500`
      │              │
      │              │  Session stays alive for up to 500 turns ← key difference from -z oneshot
      │              │  Does direct work (terminal, file, web, browser)
      │              │  AND delegates subtasks via delegate_task()
      │              │  Subagents can delegate further (multi-level trees)
      │              │  Saved findings → hindsight_retain for next iteration
      │              │  Past discoveries → hindsight_recall / session_search
      │              │
      │              └─ Prints JSON summary → daemon parses it → writes ledger
      │
      ├─ iter 2:  same (or evolved goal, or next from goals file)
      │
      └─ ... until stop sentinel, max_iterations, convergence, or goals exhausted
```

---

## How It Works

1. **You** run the daemon via `python3 launch-loop.py --run` (usually in `terminal(background=true)`). The `launch-loop.py` shim delegates to the `hermes_loop/` package.
2. **Daemon** (`hermes_loop/` package) auto-detects task type from the goal and enriches toolsets
3. **Daemon** spawns `hermes chat -q "..." -t terminal,file,delegation,... -Q --max-turns 500` on each iteration
4. **Spawned Hermes** gets task-optimized prompts, past failure context, and the right tools
5. **Spawned Hermes** stays alive for multiple turns — `delegate_task()` results arrive
6. **Spawned Hermes** prints a JSON summary line with what it did
7. **Daemon** parses the JSON via multi-line brace-counting parser, captures git state, writes to ledger
8. **Daemon** loops back (or exits if max_iterations / sentinel / convergence is hit)

The spawned session must print a JSON object as its last significant output:
```json
{
  "summary": "what was done with details",
  "duration_seconds": 123,
  "error": null,
  "next_goal": "optional next step if --evolve",
  "context": "detailed context for the next iteration to continue from here"
}
```

The `context` field is critical for iterative work — it tells the NEXT spawned session what was done and where to pick up.

---

## Scripts

| Script | Path | Purpose |
|--------|------|---------|
| **launch-loop.py** | `launch-loop.py` (root) | Thin backward-compatible shim (18 lines). Imports `main()` from the `hermes_loop/` package. All real code lives in the package. |
| **hermes_loop/** | `hermes_loop/` (directory) | **Main daemon package** (32 modules). Contains all daemon logic: CLI, loop, functions, iteration, webhook, dashboard, preflight, notifications, and more. See [project structure](#files--structure) for the full module list. |
| **session-self-loop.py** | `session-self-loop.py` (root) | Lightweight in-session loop tracker for self-enhancement from within your current Hermes session. |
| **Makefile** | `Makefile` (root) | Convenience targets: `make run`, `make dry-run`, `make self-test`, `make status`, `make stop`, `make clean`. ★ |
| **run.sh** | `run.sh` (root) | **One-command entrypoint** — sources `.env`, forwards all settings as CLI flags. Just `bash run.sh`. ★ |
| **run-loop.sh** | `scripts/run-loop.sh` | Unified shell wrapper that forwards all flags to launch-loop.py. |
| **inspect-ledger.sh** | `scripts/inspect-ledger.sh` | View the JSON ledger formatted: default view, `--watch`, `--summary`, `--json`, `--errors-only`, `--last N`. |
| **archive-state.sh** | `scripts/archive-state.sh` | Archive old iterations to JSONL or Markdown. `--auto` mode with optional `--gzip`. |
| **replay-ledger.sh** | `scripts/replay-ledger.sh` | Re-run archived iterations from JSONL files. Supports `--from`, `--to`, `--dry-run`, `--goal` prefix. |
| **verify-delegation-config.sh** | `scripts/verify-delegation-config.sh` | Check Hermes delegation config (historical reference). |

### Hermes Worker Server (external)

At `~/.hermes/plugins/hermes-mcp-worker/main.py` — an HTTP server that
spawns `hermes chat -q` sessions on demand. Used by the daemon's Worker mode.

---

## All CLI Flags

Below is the complete flag reference. The **default** column reflects the
daemon's built-in default.

### Core Task

| Flag | Default | Description |
|------|---------|-------------|
| `--goal` | *(required)* | Core task description for spawned sessions |
| `--context` | `""` | Initial context (paths, constraints, language) |
| `--context-file` | `""` | Path to file containing context (alternative to --context) |
| `--workdir` | cwd | Working directory for spawned sessions |
| `--prompt-suffix` | `""` | Extra text appended to every spawned prompt |
| `--task-type` | `auto` | Force task type: `research`, `code-fix`, `code-build`, `system-admin`, `data-processing`, `content`, `general` |

### Toolsets

| Flag | Default | Description |
|------|---------|-------------|
| `--toolsets` | *(see below)* | Comma-separated toolsets. `delegation` auto-added if missing |
| `--no-auto-toolsets` | `false` | Disable automatic toolset enrichment based on task type |
| `--no-failure-learning` | `false` | Disable injection of past failure context into spawned sessions |

Default toolsets: `terminal,file,delegation,web,skills,browser,memory,session_search,code_execution,todo,vision`

### Iteration Control

| Flag | Default | Description |
|------|---------|-------------|
| `--max-iterations` | `0` | Stop after N iterations (0 = infinite) |
| `--max-turns` | `500` | Max turns per spawned Hermes session |
| `--compact-every` | `5` | Compact context every N iterations |
| `--evolve` | `false` | Let each iteration propose the next goal |
| `--run` | `false` | Actually start the loop (without it, config is printed) |

### Parallelism

| Flag | Default | Description |
|------|---------|-------------|
| `--workers` | `1` | Run N concurrent Hermes sessions per iteration |

### Timeouts & Retries

| Flag | Default | Description |
|------|---------|-------------|
| `--session-timeout` | `7200` | Max seconds per spawned Hermes session |
| `--retry-delay` | `0` | Backoff seconds on consecutive errors |
| `--max-retries` | `0` | Retry a failed iteration up to N times (0 = no retry) |
| `--heartbeat-timeout` | `0` | Seconds of inactivity before session considered hung (0 = disabled). Grace period = timeout × 2 |

### Git Integration

| Flag | Default | Description |
|------|---------|-------------|
| `--git` | `false` | Capture git diff stats per iteration |
| `--git-commit` | `false` | Auto-commit changes per iteration (implies --git) |
| `--store-git-diff` | `false` | Store actual git diff (capped 10KB) in ledger |
| `--max-idle-iterations` | `0` | Stop after N iterations with no git changes (needs --git) |

### Goal File (Batch Processing)

| Flag | Default | Description |
|------|---------|-------------|
| `--goals-file` | `""` | Path to file with one goal per line. Pipe format: `goal\|profile\|model\|provider` |
| `--stop-at-goals-end` | `false` | Stop when all goals exhausted (don't wrap around) |
| `--track-goals` | `false` | Track completed goals; skip on restart |
| `--reset-goals` | `false` | Clear goals_completed tracking for fresh run |

### Rate Limiting

| Flag | Default | Description |
|------|---------|-------------|
| `--cooldown` | `0` | Wait N seconds between iterations |
| `--cooldown-mode` | `fixed` | `fixed` or `adaptive`. Adaptive auto-calculates based on avg duration |

### Convergence Detection

| Flag | Default | Description |
|------|---------|-------------|
| `--convergence-stop` | `false` | Auto-stop when stuck (similar summaries) |
| `--convergence-threshold` | `0.9` | Jaccard similarity threshold (0.0–1.0) |
| `--convergence-window` | `5` | Number of recent iterations to compare |

### Structured Output

| Flag | Default | Description |
|------|---------|-------------|
| `--output-schema` | `""` | Inline JSON Schema for spawned output validation |
| `--output-schema-file` | `""` | Path to JSON Schema file |
| `--max-output-chars` | `2000` | Max chars of spawned output to store (0 = unlimited) |

### Shutdown

| Flag | Default | Description |
|------|---------|-------------|
| `--shutdown-sentinel` | `/tmp/infinite-loop-stop` | Sentinel file path |

### Profile / Model Overrides

| Flag | Default | Description |
|------|---------|-------------|
| `--profile` | `""` | Hermes profile for spawned sessions |
| `--model` | `""` | Model override for spawned sessions |
| `--provider` | `""` | Provider override for spawned sessions |
| `--spawn-source` | `infinite-loop` | Source tag for spawned sessions (--source) |

### Webhook / HTTP

| Flag | Default | Description |
|------|---------|-------------|
| `--webhook-port` | `0` | Port for HTTP webhook server (0 = disabled) |
| `--http-callback` | `""` | HTTP POST URL for iteration JSON |

### Notifications

| Flag | Default | Description |
|------|---------|-------------|
| `--notify-cmd` | `""` | Shell command after each iteration (JSON on stdin) |
| `--on-error-cmd` | `""` | Shell command on failed iteration (JSON on stdin) |
| `--notify-desktop` | `false` | Desktop notify-send after each iteration (Linux) |
| `--notify-on-completion` | `false` | Summary notification when daemon finishes |
| `--notify-pushbullet` | `""` | Pushbullet API token for mobile notifications |
| `--notify-ntfy` | `""` | ntfy topic name for push notifications |
| `--notify-ntfy-server` | `https://ntfy.sh` | ntfy server URL |

### Logging

| Flag | Default | Description |
|------|---------|-------------|
| `--log-file` | `""` | Path to daemon log file |
| `--log-max-mb` | `10` | Max log file size in MB before rotation |

### Status / Dashboard

| Flag | Default | Description |
|------|---------|-------------|
| `--status-html` | `""` | Path to self-contained HTML status dashboard |
| `--status-file` | `""` | Path to one-line JSON status file for external monitoring |

### Ledger Management

| Flag | Default | Description |
|------|---------|-------------|
| `--keep-iterations` | `0` | Auto-shrink ledger to last N iterations (0 = keep all) |
| `--force-reset` | `false` | Clear existing ledger and start fresh |
| `--tag` | `""` | Label for the run (e.g. `project:fix-auth`) |

### Archiving

| Flag | Default | Description |
|------|---------|-------------|
| `--archive-dir` | `~/.hermes/infinite-loop-archives` | Directory for archived iteration JSONL.gz files |
| `--archive-retention` | `30` | Days to keep archived iterations (0 = forever) |
| `--archive-max-size` | `0` | Max archive dir size in MB (0 = unlimited, overlaid with retention) |

### File Watcher

| Flag | Default | Description |
|------|---------|-------------|
| `--watch-dir` | `""` | Watch a directory/file for changes via os.stat() polling |
| `--watch-poll` | `5.0` | File watcher poll interval in seconds |

### Hermes Worker

| Flag | Default | Description |
|------|---------|-------------|
| `--worker-url` | `auto` | `"auto"` = embedded worker, `"http://host:port"` = external, `""` = direct subprocess |

### Spawned Session Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--use-library` | `false` | Use AIAgent.run_conversation() in-process |
| `--pass-session-id` | `false` | Store spawned session ID in ledger |
| `--checkpoints` | `false` | Enable file checkpoints in spawned sessions |
| `--resume` | `false` | Chain sessions across iterations (needs --pass-session-id) |
| `--skills` | `""` | Skills to preload (comma-separated, subprocess only) |
| `--ignore-rules` | `false` | Skip AGENTS.md, memory, rules in spawned sessions |
| `--ignore-user-config` | `false` | Skip ~/.hermes/config.yaml in spawned sessions |
| `--yolo` | `false` | Bypass dangerous command approval prompts |
| `--safe-mode` | `false` | Disable ALL customizations (implies ignore-rules + ignore-user-config) |
| `--accept-hooks` | `false` | Auto-approve shell hooks without TTY |
| `--worktree` | `false` | Run in isolated git worktree |
| `--continue` | `false` | Resume most recent session |

### Startup / Debug

| Flag | Default | Description |
|------|---------|-------------|
| `--startup-delay` | `0.0` | Wait N seconds before first iteration |
| `--quiet` | `false` | Suppress verbose startup banner, iteration headers, and config dump. Shows only compact one-line status. Ideal for background runs. |
| `--color` | `auto` | Colorize output: `auto` (TTY only, default), `always` (force), `never` (disable). Respects `NO_COLOR` env. |
| `--preflight` | `false` | Run preflight health checks before loop |
| `--preflight-fail-fast` | `false` | Stop on first preflight failure |
| `--dry-run` | `false` | Print config and exit (no loop) |
| `--self-test` | `false` | Run in-process self-tests (count auto-detected at runtime) and exit |
| `--list-flags` | *(n/a)* | Print all 90 flags organized by group with help text. Pre-argparse (no `--goal` required) |
| `--list-groups` | *(n/a)* | Print only group names with flag counts (compact overview) |
| `--examples` | *(n/a)* | Print categorized real-world usage examples across 7 categories |
| `--save-config` | `""` | Save config to JSON file and exit |
| `--config` | `""` | Load config from JSON file |
| `--completion-script` | *(n/a)* | Generate shell completion for bash/zsh from live argparse. `--completion-script bash | source /dev/stdin` |
| `--check-env` | *(n/a)* | Validate .env for typos, unknown variables, and common mistakes. Pre-argparse, no `--goal` needed. |
| `--version` | *(n/a)* | Print version and exit |
| `--help` | *(n/a)* | Print full help |

---

## Configuration (.env)

A complete `.env.example` file is bundled with this project. It documents
**every** configurable parameter as an environment variable. Copy it:

```bash
cp .env.example .env
# Edit .env with your settings
# Then source it before running:
set -a; source .env; set +a
# Or pass flags directly — CLI flags override .env values.
```

See the [.env.example](./.env.example) file for the full list with
descriptions and default values for each variable.

---

## Two Modes

### Daemon Mode (launch-loop.py)

**For**: Autonomous batch processing, background looping, multi-worker
parallelism, git-aware evolution.

This is the primary mode. A Python daemon runs in the background (via
`terminal(background=true)` or directly in a tmux pane) and manages the
full loop lifecycle.

**When to use**:
- Fix 50 lint errors one at a time
- Refactor module by module with delegated analysis
- Process chunks of a dataset via parallel subagents
- Continuous improvement loops (audit → fix → measure → repeat)
- Git-aware evolution (auto-commit, stop when no more changes)
- Monitor a directory for file changes
- Trigger via webhook

### In-Session Self-Loop (session-self-loop.py)

**For**: Self-enhancement of Hermes itself, the infinite-loop skill, or
any workflow where you want visibility from your current Hermes session.

Instead of a background daemon, your current Hermes session does the work
directly via `delegate_task()` iterations.

**When to use**:
- Enhancing the infinite-loop daemon itself
- Modifying skill files
- Any task where you need to see what's happening in real-time

```bash
# Start the loop tracker
python3 session-self-loop.py --max-iterations 10 &
LOOP_PID=$!

# Each iteration, update the state file:
echo '{"summary": "added feature X", "next_goal": "add feature Y"}' > /tmp/session-loop-state.json

# Stop:
echo '{"done": true}' > /tmp/session-loop-state.json
kill $LOOP_PID
```

---

## v14.18.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| `--check-env` flag | UX | `env_utils.py`, `cli.py`, `run.sh`, `Makefile` | Validate `.env` for typos, unknown variables, and common mistakes. 82 recognized vars. Typo detection via fuzzy matching (e.g. `INFINITE_LOOP_COOL_DOWN` → `INFINITE_LOOP_COOLDOWN`). Pre-argparse, no `--goal` needed. |
| Env validation in `--dry-run` | UX | `cli.py` | `--dry-run` now auto-checks `.env` and reports issues alongside config preview. Non-blocking — issues are suggestive only. |
| `make check-env` target | DX | `Makefile` | Convenience target for env validation. |
| `env_utils.py` module | New | `env_utils.py` | 5 functions for env var parsing, validation, fuzzy matching, formatted output, and orchestration. |
| Self-tests for env validator | Test | `self_test.py` | 7 new test cases: known vars, typos, unknown vars, non-prefix vars, close matches, no-match, missing required. |

---

## v14.15.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| Auto-colorized `_log()` tags | UX | `file_utils.py`, `cli.py` | Every structured log tag (`[INFO]`, `[WARN]`, `[ERROR]`, `[DAEMON]`, `[GOALS]`, `[PREFLIGHT]`, `[COOLDOWN]`, `[BEAT]`, `[NOTE]`, `[SUGGEST]`, `[OK]`, `[DONE]`, `[SUMMARY]`, `[AUTO-RELOAD]`, `[CONFIG]`, `[STATUS]`, `[ARCHIVE]`, `[COMPACT]`, `[LOG]`, `[CONTEXT]`, `[OUTPUT]`, `[HEARTBEAT]`, `[MODE]`) is now automatically colorized by `_log()` — no per-call changes needed. Centralized 24-pattern mapping in `_colorize_log_tags()`. Respects `--color` and `NO_COLOR`. |
| Colorized startup banner | UX | `cli.py` | Separators bold blue, version bold cyan, "Starting loop..." bold green, colored `[SUMMARY]`/`[SUGGEST]` tags and `--examples`/`--quiet` in feature list. |

---

## v14.14.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| `--color=[auto\|always\|never]` flag | UX | `color_utils.py`, `cli.py`, `loop.py` | New ANSI color support for CLI output. `auto` (default) colors on TTY, `always` forces colors, `never` disables. Respects `NO_COLOR`. Colorizes `--list-flags`, `--list-groups`, `--examples`, `--summary`, `--suggest` output. |
| `hermes_loop/color_utils.py` module | New | `color_utils.py` | `Colorizer` class with terminal detection, named color helpers (ok/warn/fail/header/flag/value/dim), tag formatters, and `strip_ansi()`. Module-level singleton usable anywhere. |
| Colorized iteration output | UX | `loop.py` | `[SUMMARY]` bold cyan on success, `[FAIL]` bold red on errors. `[DONE]` bold green/red. `[SUGGEST]` bold magenta. |

---

## v14.13.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| Auto-generated `--list-flags` from argparse | Refactor | `cli.py`, `config.py` | Replaced 134-line hardcoded flag dict with live introspection of argparse parser. `--list-flags` and `--list-groups` now read directly from `add_argument()` calls — zero drift. Extracted `_create_parser()` for shared use. New `[Introspection]` section for pre-argparse flags. |

---

## v14.12.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| `make examples` / `list-flags` / `list-groups` targets | Usability | `Makefile` | Three new convenience targets: `make examples` (categorized usage patterns), `make list-flags` (all 87 flags by group), `make list-groups` (compact group overview). No need to remember CLI flag names. |
| `run.sh --help` documents all introspection flags | Docs | `run.sh` | Added missing `--list-groups` entry, updated `--list-flags` and `--examples` descriptions with counts. Banner now mentions v14.11.0 docs consistency fix. |
| CONTRIBUTING.md `make` targets expanded | Docs | `CONTRIBUTING.md` | Added `make examples/list-flags/list-groups/status/log/stop` to Common Commands table, removed duplicate rows. |

---

## v14.11.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| Fixed "~40 tests" doc mismatch | Docs | 6 files | All docs now say "9 groups, 45 cases" matching actual --self-test output. Added missing --list-flags, --list-groups, --examples to README flag table and CONTRIBUTING common commands. Corrected CONTRIBUTING test coverage table with accurate case counts. |
| Fixed CONTRIBUTING version typo | Docs | `CONTRIBUTING.md` | `"14.10.0` → `"14.10.0"` (missing closing quote) |

## v14.10.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| Rich `[SUMMARY]` line | Usability | `loop.py` | Consolidated post-iteration summary replacing separate [DONE]/[PROGRESS]/[STATS] lines. Shows iteration count, task type, duration, classification, git changes, CPU/memory, worker breakdown, progress bar, and ETA. |

---

## v14.9.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| `--examples` flag | Usability | `cli.py`, `.env.example` | Prints categorized real-world usage examples covering 7 categories. Accessible pre-argparse (no `--goal` required). |
| Missing goal error | Usability | `cli.py` | Now also shows `See --examples for usage patterns` alongside `--help`. |
| Tab-completion update | Usability | `completion/{bash,zsh}` | `--examples` added to both completion scripts. |

---

## v14.7.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| `--list-flags` flag | Usability | `cli.py` | Prints every supported CLI flag as a tab-separated triple (`short`, `long`, `description`) — one per line — for shell autocompletion integration. Machine-parseable output, stable format. |
| `make completion` target | Usability | `Makefile` | Convenience target that generates a list of all CLI flags by running `--list-flags` and writing them to `/tmp/loop-flags.txt`. |

---

## v14.6.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| Quiet mode (`--quiet`) | Usability | `cli.py`, `loop.py`, `functions.py`, `iteration.py`, `run.sh`, `.env.example` | Suppresses verbose startup banner, per-iteration headers, and config dump. Shows only compact one-line status. Ideal for background daemon runs. |
| Iteration heartbeat (`[BEAT]`) | Usability | `iteration.py` | Background thread logs periodic `[BEAT] Iteration #N still running (120s elapsed)...` messages during long-running iterations. No more ambiguous silence. |

---

## v14.5.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| Actionable [SUGGEST] messages | Usability | `error_utils.py`, `loop.py` | Context-aware suggestions after errors (timeout, network, schema) and stuck/regression classifications. Shows specific CLI flags to adjust. |
| Self-tests for suggestion engine | Test | `self_test.py` | 9 test cases covering all suggestion patterns. |

---

## v14.2.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| Makefile | Usability | `Makefile` | Convenience targets: run, dry-run, self-test, lint, status, stop, clean, archive, log, version |
| CONTRIBUTING.md | Documentation | `CONTRIBUTING.md` | Onboarding guide with setup, workflow, code style, troubleshooting |
| Improved run.sh --help | Usability | `run.sh` | Organized sections, quick reference for ledger/status/stop/dashboard |
| `--self-test` / `--version` in run.sh | Usability | `run.sh` | New passthrough flags for testing and version info |
| SSE broadcast fix | Bugfix | `launch-loop.py` | Added missing `global _sse_clients` in `_broadcast_to_sse_clients()` to prevent UnboundLocalError crash |

> **Full changelog**: See [CHANGELOG.md](./CHANGELOG.md) for the complete version history since v1.0.0.

---

## v14.3.0 Changelog

| Feature | Type | Files | Description |
|---------|------|-------|-------------|
| Structured --help description | Usability | `launch-loop.py` | Replaced wall-of-text with "Features at a glance" grouped by category (Iteration, Parallel, Notify, Sessions, Spawn, Debug, Git, Web), common usage examples, and stop/pause/status commands. Uses RawDescriptionHelpFormatter. |
| Friendly missing --goal error | Usability | `launch-loop.py` | Clear "ERROR: --goal is required (or use --goals-file for batch mode)" before argparse's default error, with usage hint and --help pointer. |
| Readable startup banner | Usability | `launch-loop.py` | Replaced 10-line feature dump with compact 3-line pipe-separated summary under Unicode ═ header. |
| Organized --help output | Usability | `launch-loop.py` | Argument groups (Core, Iteration, Notification, Error Recovery, Archival, Behavior) for readable `--help` |
| run.sh dry-run bugfix | Bugfix | `run.sh` | `--dry-run` now sets `DRY_RUN=true` and strips `--run` from daemon args to prevent no-op dry-runs |

---

## Feature Deep-Dive

### Actionable Error Suggestions

When an iteration encounters an error (timeout, network failure, schema mismatch)
or gets classified as stuck/regression, the daemon now prints a `[SUGGEST]` block
with context-aware, actionable advice. Each suggestion maps to a specific CLI flag
or configuration change:

| Situation | Suggests |
|-----------|----------|
| Timeout error | Increase `--session-timeout`, reduce `--max-turns`, check `--workers` |
| Network error | Check connectivity, verify Hermes provider config, add `--retry-delay`, run `--preflight` |
| Schema validation failure | Review `--output-schema`, check `--output-schema-file` format |
| Stuck (consecutive no-progress iterations) | Set `--workers 1`, try `--use-library`, add `--evolve` |
| Regression (error after progress) | Review git diff, run `--force-reset`, add `--git-commit` |
| 3+ consecutive errors | Run `--preflight`, reduce `--workers`, check `--goal` text, add `--context` |
| Partial progress | Normal for iterative tasks; consider `--evolve` |

These suggestions appear in the daemon log right after the `[SUMMARY]` line, so you
see the error + actionable fix in one glance:

```
[SUMMARY] ✔ Iteration 5 | content | (120s) | stuck | cpu=45.2s | mem=128MB | [█████░░░░░░░] 5/10 50% | ETA=5m

[SUGGEST] Suggestions:
[SUGGEST]   • Set --workers 1 to isolate the issue (concurrent sessions may interfere)
[SUGGEST]   • Try --use-library for in-process execution (bypasses subprocess issues)
[SUGGEST]   • Add --evolve to let iterations self-direct when stuck in a loop
```

No extra flags needed — suggestions are always enabled.

---

### Rich Post-Iteration Summary (`[SUMMARY]`)

The daemon displays a consolidated one-line `[SUMMARY]` after every iteration,
replacing the old separate `[DONE]`, `[PROGRESS]`, and `[STATS]` lines. It's
designed for scannability at a glance:

```
[SUMMARY] ✔ Iteration 3 | code-fix | (89s) | progress | git: 4 files changed | cpu=32.1s | mem=112MB | peak=118MB | workers=3/3 | [██░░░░░░░░░] 3/10 30% | ETA=7m
```

**What you see at a glance:**
- **Status**: `✔` success or `✘` error
- **Iteration**: Number and task type
- **Duration**: Wall-clock time in seconds
- **Classification**: `completed`, `progress`, `partial`, `stuck`, `regression`, or the error type
- **Git**: Diff stats or commit hash when `--git` is enabled
- **System**: CPU seconds, current + peak RSS memory
- **Workers**: Success/fail breakdown for multi-worker runs
- **Progress bar**: Visual progress with percentage and ETA

Error iterations prominently show the error type instead of classification,
and include `[SUGGEST]` lines with actionable fixes.

---

### Quiet Mode (`--quiet`)

Suppress the verbose startup banner, per-iteration headers (`=== Iteration N ===`),
and 50+ line config dump. In quiet mode, you get only compact one-line status:

```
[DAEMON] Running: goal=Fix lint errors | max=10 | tools=11 | type=code-fix
[ITER #1] Fix lint errors in src/
...
[SUMMARY] ✔ Iteration 1 | code-fix | (45s) | progress | cpu=18.2s | mem=96MB  | [█░░░░░░░░░] 1/10 10% | ETA=6m45s
```

**Usage**:
```bash
bash run.sh --quiet
# Or via .env:
INFINITE_LOOP_QUIET=true
```

Ideal for background daemon runs or when the daemon logs to a file you already
monitor via `tail -f`.

---

### Iteration Heartbeat (`[BEAT]` Messages)

When a spawned Hermes session runs for more than 2 minutes, the daemon
logs periodic heartbeat messages so you can tell it's still working:

```
[BEAT] Iteration #3 still running (120s elapsed)...
[BEAT] Iteration #3 still running (240s elapsed)...
```

These appear automatically — no flags needed. The heartbeat interval is 120
seconds. The thread is daemon-threaded and stops cleanly when the iteration
completes or is killed.

---

### Self-Test Mode

Run ~40 in-process unit tests across 8 core daemon functions without
spawning any child Hermes sessions:

```bash
python3 launch-loop.py --self-test
```

Tests cover: JSON extraction (6 edge cases), error classification (5 error
types), text similarity (3 cases), convergence detection (3 patterns), schema
validation (3 schema cases), adaptive cooldown (4 duration ranges), GoalSpec
parsing (3 formats), and progress classification (6 categories).

### Output Progress Classification

Each iteration is classified into one of 6 categories:

| Classification | Meaning | Example |
|---------------|---------|---------|
| `completed` | Goal explicitly declared done | "All 15 type errors fixed" |
| `progress` | Changes made, not done yet | "Fixed 5/15 type errors" |
| `partial` | Analysis done, no changes | "Analyzed the auth module" |
| `stuck` | No changes, short output | "Can't reproduce the bug" |
| `regression` | Error after progress | "Tests failing after refactor" |
| `unknown` | No pattern matched | (miscellaneous) |

The classification is stored in each iteration's ledger record and enables
color-coded dashboards and smarter auto-stop criteria.

### Convergence Detection

Uses word-overlap (Jaccard) similarity to detect when spawned sessions
are stuck in a loop producing essentially the same output:

```bash
# Stop if 5 consecutive iterations have >90% similar summaries
python3 launch-loop.py --goal "Refactor auth" \
  --convergence-stop --run

# More sensitive
python3 launch-loop.py --goal "Fix lint errors" \
  --convergence-stop --convergence-window 3 \
  --convergence-threshold 0.7 --run
```

### Adaptive Cooldown

Dynamically adjusts the delay between iterations based on average duration:

- Iterations < 5s → 60s cooldown (rate-limit protection)
- Iterations 5–15s → 30s cooldown
- Iterations 15–300s → linear interpolation 30s to 2s
- Iterations > 300s → 2s cooldown (minimal delay)

```bash
python3 launch-loop.py --goal "Fix lint errors" \
  --cooldown-mode adaptive --max-iterations 50 --run
```

### Context Propagation

Spawned sessions can include a `context` field in their JSON output. This
context is injected into the NEXT spawned session's prompt, so iteration
N+1 knows what iteration N did, what files changed, and where to pick up.

This fixes the core problem where each spawned session started from scratch.

### Self-Modification

The daemon can self-update. When a spawned session modifies `launch-loop.py`,
it includes `"next_goal": "NEXT_ITERATION need_reload"` in its JSON output.
The daemon detects this, persists the ledger, and calls `os.execv()` to
restart with the updated code.

The spawned session's prompt includes explicit instructions for this pattern:
use `delegate_task()` to dispatch a subagent that makes file changes, wait
for the subagent result, then signal `need_reload`.

### Hermes Worker Mode

With `--worker-url auto` (the default), the daemon auto-starts an embedded
Hermes Worker HTTP server on a random port. This solves the **self-reference
problem**: each spawned Hermes session loads the latest config, skills, and
plugins. The daemon never needs to restart for config/skill/plugin changes.

```bash
# auto mode (default) — embedded worker, no extra management
python3 launch-loop.py --goal "..." --run

# External worker — worker survives daemon restarts
# Terminal 1:
python3 ~/.hermes/plugins/hermes-mcp-worker/main.py --port 8124
# Terminal 2:
python3 launch-loop.py --goal "..." \
  --worker-url http://localhost:8124 --run

# Disable worker mode entirely
python3 launch-loop.py --goal "..." --worker-url '' --run
```

### Webhook & REST Control

With `--webhook-port PORT`, the daemon starts a lightweight HTTP server
that runs alongside the main loop:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | `{"status": "ok"}` |
| `/status` | GET | Compact status (ledger summary) |
| `/api/status` | GET | Full ledger state as JSON |
| `/control/stop` | POST | Stop the loop |
| `/control/pause` | POST | Pause the loop |
| `/control/resume` | POST | Resume the loop |
| `/webhook` | POST | Trigger next iteration (optional JSON body) |

```bash
python3 launch-loop.py --goal "Fix lint errors" \
  --webhook-port 8080 --run

# Trigger from another process
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"goal": "Fix only the Python files"}'

# Programmatic control
curl -X POST http://localhost:8080/control/stop
curl -X POST http://localhost:8080/control/resume
```

### Dashboard v3 SSE

With `--status-html PATH`, the daemon generates a self-contained HTML page
with Server-Sent Events (SSE) for **real-time updates**. The dashboard
features:

- Auto-refresh via SSE (no polling needed)
- System resource cards (CPU, memory, RAM %)
- ETA column with estimated time remaining
- Cooldown indicator
- Iteration history table with color-coded progress classifications
- Dark/light mode via `prefers-color-scheme`
- Inline SVG favicon (no browser 404 errors)
- Response to POST /control endpoints on the webhook port

```bash
python3 launch-loop.py --goal "..." \
  --status-html /tmp/loop-status.html --run

# Serve it
python3 -m http.server 8080 --directory /tmp/
# Then open http://localhost:8080/loop-status.html
```

The SSE endpoint streams live updates at `GET /live` — any SSE-capable
client can consume it.

### Session Self-Healing Heartbeat

Introduced in v14.0.0. When `--heartbeat-timeout N` is set, the daemon
monitors spawned Hermes sessions for liveness. Each session must produce
output at least once every N seconds:

| Feature | Description |
|---------|-------------|
| **Heartbeat mechanism** | The daemon times how long since a spawned session last emitted a line of stdout. If the session stays silent beyond the threshold, it's marked as hung. |
| **Grace period** | `heartbeat_timeout × 2` of additional silence before action is taken. Total window = `heartbeat_timeout × 3`. |
| **Kill & retry** | On heartbeat failure, the session process is killed (SIGTERM → SIGKILL), the iteration is marked as a heartbeat error, and retry logic runs. |
| **Stale cleanup** | On startup, stale heartbeat tracking files from previous daemon instances are cleaned up automatically. |

```bash
python3 launch-loop.py --goal "Refactor auth" \
  --heartbeat-timeout 300 --run
```

### Pushbullet & ntfy Notifications

Mobile notifications for iteration results:

```bash
# Pushbullet
python3 launch-loop.py --goal "..." \
  --notify-pushbullet "YOUR_ACCESS_TOKEN" --run

# ntfy (public)
python3 launch-loop.py --goal "..." \
  --notify-ntfy "my-loop-alerts" --run

# ntfy (self-hosted)
python3 launch-loop.py --goal "..." \
  --notify-ntfy "my-loop-alerts" \
  --notify-ntfy-server "https://ntfy.example.com" --run
```

### Preflight Health Checks

With `--preflight`, the daemon runs comprehensive checks before the first
iteration:

| Check | What it validates |
|-------|-------------------|
| `hermes_binary` | `hermes` is on PATH and executable |
| `workdir_exists` | `--workdir` path exists |
| `workdir_is_dir` | `--workdir` is a directory |
| `git_repo` | Workdir has `.git` (when `--git` set) |
| `sentinel_writable` | Sentinel parent dir is writable |
| `file_readable` | `--context-file` exists |
| `port_available` | `--webhook-port` not in use |
| `disk_space` | At least 0.5 GB free |

```bash
python3 launch-loop.py --goal "Fix lint errors" \
  --preflight --preflight-fail-fast --run
```

### Ledger Archiving

With `--keep-iterations N`, the ledger auto-shrinks. Trimmed iterations
are saved to gzip-compressed JSONL files before discarding:

```bash
python3 launch-loop.py --goal "..." \
  --keep-iterations 50 --archive-dir /tmp/loop-archives \
  --archive-retention 30 --archive-max-size 100 \
  --run
```

Archive files go to `~/.hermes/infinite-loop-archives/` by default with
filenames like `iterations-{YYYYMMDD}-{seq}.jsonl.gz`.

### Multi-Profile Goals

Goals file entries can specify per-goal profile, model, and provider
overrides using pipe-separated format. Empty fields fall back to daemon-level
CLI args:

```text
goal text|profile|model|provider
Fix type errors in auth|work|anthropic/claude-sonnet-4|
Refactor database layer|personal||
Write documentation||gpt-4o|openai
Plain goal (no pipes)
```

Backward compatible — plain lines without pipes work exactly as before.

### AIAgent Library Mode

Instead of spawning `hermes chat -q` as a subprocess, the daemon can import
`AIAgent` from `run_agent` and run the conversation in-process:

```bash
python3 launch-loop.py --goal "..." \
  --use-library --pass-session-id --checkpoints --run
```

This eliminates subprocess overhead, simplifies error handling, and provides
direct access to the result dict (session_id, token usage, cost data). Falls
back to subprocess mode automatically if AIAgent is not importable.

Since v12.0.0, `--use-library` works with `--workers > 1` via
`multiprocessing.Pool`, enabling true parallel in-process execution.

---

### Shell Completion

The daemon provides two approaches for shell completion:

**Auto-generated (recommended):** Use `--completion-script` to generate a
complete bash or zsh completion script from the live argparse parser —
always up-to-date and never needs manual maintenance:

```bash
# Bash: use directly
source <(python3 launch-loop.py --completion-script bash)

# Zsh: save to completions directory
mkdir -p ~/.zsh/completion
python3 launch-loop.py --completion-script zsh > ~/.zsh/completion/_hermes_loop
# Then add to ~/.zshrc:
#   fpath=(~/.zsh/completion $fpath)
#   autoload -Uz compinit && compinit

# One-time install via Makefile:
make completion    # installs completion script for your shell
```

**Regenerate from argparse:** After adding/removing flags, update the
static completion scripts:

```bash
make update-completions   # regenerates scripts/completion/{bash,zsh}
make completion            # reinstall them
```

**Legacy `--list-flags` approach:** Each CLI flag is also available as a
tab-separated triple (`short-flag`, `long-flag`, `description`) for
manual integration:

```bash
# View all flags with their short form, long form, and description
python3 launch-loop.py --list-flags | head -20
```

**Usage from a completion script:**

```bash
# Bash: generate completions by parsing --list-flags output
_list_loop_flags() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    COMPREPLY=($(compgen -W "$(python3 launch-loop.py --list-flags 2>/dev/null | cut -f2)" -- "$cur"))
}
complete -F _list_loop_flags launch-loop.py
```

**Makefile convenience target:**

```makefile
completion:
    @echo "Generating shell completion scripts..."
    @python3 launch-loop.py --list-flags 2>/dev/null | cut -f2 > /tmp/loop-flags.txt
    @echo "  ✓ Written to /tmp/loop-flags.txt"
    @echo "Source this in your .bashrc or .zshrc to enable tab-completion for launch-loop.py flags."
```

Run it with:

```bash
make completion
```

This makes it easy to discover and autocomplete the 80+ CLI flags without
referring to `--help` every time. The `--list-flags` output is stable and
machine-parseable — it will not change format across minor releases.

---

## References

The `references/` directory contains deep-dive documentation on design
decisions, edge cases, and troubleshooting:

| File | Description |
|------|-------------|
| `cross-iteration-context.md` | Why spawned sessions start blank, context propagation fix, design rules |
| `spawn-toolset-restriction.md` | Why `-z` + `delegation` breaks, and the correct `chat -q` pattern |
| `terminal-timeout-trap.md` | Parent `terminal()` timeout kills the daemon — how to avoid |
| `hermes-worker.md` | Hermes Worker protocol, edge cases, troubleshooting |
| `config-requirements.md` | Delegation configuration requirements |
| `hermes-delegate-protocol.md` | Deprecated v3.x file-based protocol (historical) |
| `stdlib-daemon-patterns.md` | stdlib-only patterns for the daemon |
| `yaml-null-pitfall.md` | `hermes config set` quirk with null values |

The `research/` directory documents the design process behind
each major version — from v11.11.0 through v14.1.0, including feature
specs, audits, and synthesis documents.

---

## Pitfalls

1. **`hermes` must be on PATH** — the daemon calls `hermes chat -q` as a subprocess.
2. **`chat -q` is used instead of `-z`** — `-z` oneshot exits before `delegate_task()` results arrive.
3. **`delegation` is auto-included** in toolsets — don't omit it explicitly.
4. **Session timeout** default 7200s (2 hours). Increase with `--session-timeout`.
5. **Ledger grows unboundedly** — use `--keep-iterations N` for auto-shrink.
6. **Sentinel file must be local** — `os.path.exists()` checks are fast.
7. **`--git-commit` stages ALL changes** — uncommitted work is included.
8. **`--workers N` cost scales linearly** — each worker is a full Hermes session.
9. **Evolution mode** — spawned JSON MUST include a `next_goal` field.
10. **Long context via --context-file** for large payloads (shell limits).
11. **`--goals-file` conflicts with `--evolve`** — they're mutually exclusive.
12. **`--goals-file` wraps around** by default unless `--stop-at-goals-end`.
13. **Parent `terminal()` timeout** can kill the daemon — always set `timeout=300`+
    when launching from a Hermes session.
14. **Signal handler uses best-effort write** — the temp-file + atomic-rename
    pattern is signal-safe, but interrupted handlers may lose state.
15. **Adaptive cooldown requires iteration history** — first iteration uses
    `--cooldown` as fallback.
16. **Convergence on very short summaries** (<5 words) may be unreliable.
17. **System resource tracking is Linux-only** (uses `/proc`).
18. **Multi-profile goals** — pipe format with empty fields falls back to
    daemon-level args.
19. **Library mode with `--skills`** — falls back to subprocess.
20. **Library mode with `--yolo` / `--safe-mode` / `--accept-hooks`** — silently
    skipped with a log note.
21. **`--resume` requires `--pass-session-id`** — without session tracking,
    there's nothing to resume from.
22. **First iteration has no resume target** — `--resume` is silently skipped.
23. **`--output-schema` validation is stdlib-only** — no `$ref`, `oneOf`, `anyOf`,
    or pattern matching.

---

## Files & Structure

```
infinite-loop/
├── README.md                    ← This file
├── run.sh                       ← One-command entrypoint (reads .env) ★
├── Makefile                     ← Convenience targets ★
├── CONTRIBUTING.md              ← Onboarding & development guide
├── LICENSE                      ← MIT
├── .gitignore
├── .env.example                 ← All config parameters as env vars
├── SKILL.md                     ← Original Hermes skill file (83 KB)
│
│
├── launch-loop.py               ← Thin backward-compatible shim (18 lines) ★
├── session-self-loop.py         ← In-session loop tracker ★
│
├── hermes_loop/                 ← Main daemon package (32 modules) ★
│   ├── __init__.py
│   ├── __main__.py              ← `python3 -m hermes_loop` entry point
│   ├── cli.py                   ← Argparse + main() entry point
│   ├── loop.py                  ← run_loop() iteration logic
│   ├── functions.py             ← Helper functions (execute, merge, notify)
│   ├── iteration.py             ← Spawned session execution
│   ├── config.py                ← Constants, paths, defaults
│   ├── error_utils.py           ← Error classification + actionable suggestions
│   ├── error_recovery.py        ← Automatic error recovery
│   ├── webhook.py               ← HTTP webhook server
│   ├── dashboard.py             ← SSE status dashboard
│   ├── preflight.py             ← Preflight health checks
│   ├── notifications.py         ← Pushbullet/ntfy/desktop notifications
│   ├── heartbeat.py             ← Session heartbeat monitoring
│   ├── worker_manager.py        ← Hermes worker process management
│   ├── library_worker.py        ← AIAgent in-process execution
│   ├── state.py                 ← Ledger state management
│   ├── file_utils.py            ← File I/O utilities
│   ├── git_utils.py             ← Git diff/commit helpers
│   ├── goal_utils.py            ← Goal parsing/tracking
│   ├── signal_handlers.py       ← Signal handling (SIGINT/SIGTERM)
│   ├── stats.py                 ← Statistics and ETA
│   ├── validation.py            ← JSON Schema validation
│   ├── similarity.py            ← Text similarity (Jaccard)
│   ├── cooldown.py              ← Adaptive cooldown calculation
│   ├── hermes_utils.py          ← Hermes binary detection
│   ├── system_utils.py          ← System resource tracking (Linux /proc)
│   ├── file_watcher.py          ← Directory/file change watcher
│   ├── archiving.py             ← Ledger archival
│   ├── self_test.py             ← In-process unit tests
│   ├── tracker.py               ← Context window tracker
│   └── legacy.py                ← Backward compatibility
│
├── scripts/
│   ├── run-loop.sh              ← Unified shell wrapper
│   ├── inspect-ledger.sh        ← Formatted ledger viewer
│   ├── archive-state.sh         ← Archive old iterations
│   ├── replay-ledger.sh         ← Re-run archived iterations
│   └── verify-delegation-config.sh  ← Historical config checker
│
├── references/
│   ├── cross-iteration-context.md
│   ├── spawn-toolset-restriction.md
│   ├── terminal-timeout-trap.md
│   ├── hermes-worker.md
│   ├── config-requirements.md
│   ├── hermes-delegate-protocol.md
│   ├── stdlib-daemon-patterns.md
│   └── yaml-null-pitfall.md
│
├── research/
│   ├── v11.11.0-features.md
│   ├── v12.0.0-features.md
│   ├── v13.0.0-features.md
│   ├── v14.0.0-features.md
│   ├── ... (20+ research documents)
│   └── aiagent-vs-subprocess-analysis.md
│
└── scripts/completion/
    ├── bash                     ← Bash tab-completion script
    └── zsh                      ← Zsh tab-completion script
```
