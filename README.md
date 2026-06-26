# Infinite Loop Daemon — v14.0.0

A self-looping background daemon that spawns Hermes sessions with **real tools**
(terminal, file, web, skills, browser, memory) **and** `delegate_task()` for
multi-level delegation trees. It iterates autonomously, tracks progress in a
JSON ledger, and can batch-process hundreds of goals in sequence.

## Origin

This is the **infinite-loop skill** from the Hermes Agent skills repository,
extracted into a standalone project. It lives inside `~/.hermes/skills/software-development/infinite-loop/`
when installed as a Hermes skill, and is mirrored here for independent use,
development, and documentation.

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
  - [Self-Test Mode](#self-test-mode)
  - [Progress Classification](#output-progress-classification)
  - [Convergence Detection](#convergence-detection)
  - [Adaptive Cooldown](#adaptive-cooldown)
  - [Context Propagation](#context-propagation)
  - [Self-Modification](#self-modification)
  - [Hermes Worker Mode](#hermes-worker-mode)
  - [Webhook & REST Control](#webhook--rest-control)
  - [Dashboard v3 SSE](#dashboard-v3-sse)
  - [Session Self-Healing Heartbeat](#session-self-healing-heartbeat)
  - [Pushbullet & ntfy Notifications](#pushbullet--ntfy-notifications)
  - [Preflight Health Checks](#preflight-health-checks)
  - [Ledger Archiving](#ledger-archiving)
  - [Multi-Profile Goals](#multi-profile-goals)
  - [AIAgent Library Mode](#aiagent-library-mode)
- [References](#references)
- [Pitfalls](#pitfalls)

---

## Quick Start

```bash
# Basic loop — one goal, infinite iterations
python3 launch-loop.py \
  --goal "Refactor the auth module to use JWT tokens" \
  --workdir /home/nekophobia/Projects/myapp \
  --run

# Batch — read goals from a file
python3 launch-loop.py \
  --goals-file /tmp/goals.txt \
  --workdir /home/nekophobia/Projects/myapp \
  --git --max-iterations 50 \
  --run

# With status dashboard + webhook
python3 launch-loop.py \
  --goal "Fix lint errors" \
  --status-html /tmp/loop-status.html \
  --webhook-port 8080 \
  --git-commit \
  --run
```

**Monitor progress**:
```bash
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
      │  launch-loop.py loops in the background:
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

1. **You** run the daemon via `python3 launch-loop.py --run` (usually in `terminal(background=true)`)
2. **Daemon** auto-detects task type from the goal and enriches toolsets
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

|| Script | Path | Purpose |
||--------|------|---------|
|| **launch-loop.py** | `launch-loop.py` (root) | Main daemon — the primary loop. Spawns Hermes sessions, manages the JSON ledger, handles all flags. **287 KB, 7,557 lines.** |
|| **session-self-loop.py** | `session-self-loop.py` (root) | Lightweight in-session loop tracker for self-enhancement from within your current Hermes session. |
|| **run-loop.sh** | `scripts/run-loop.sh` | Unified shell wrapper that forwards all flags to launch-loop.py. |
|| **inspect-ledger.sh** | `scripts/inspect-ledger.sh` | View the JSON ledger formatted: default view, `--watch`, `--summary`, `--json`, `--errors-only`, `--last N`. |
|| **archive-state.sh** | `scripts/archive-state.sh` | Archive old iterations to JSONL or Markdown. `--auto` mode with optional `--gzip`. |
|| **replay-ledger.sh** | `scripts/replay-ledger.sh` | Re-run archived iterations from JSONL files. Supports `--from`, `--to`, `--dry-run`, `--goal` prefix. |
|| **verify-delegation-config.sh** | `scripts/verify-delegation-config.sh` | Check Hermes delegation config (historical reference). |

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
| `--preflight` | `false` | Run preflight health checks before loop |
| `--preflight-fail-fast` | `false` | Stop on first preflight failure |
| `--dry-run` | `false` | Print config and exit (no loop) |
| `--self-test` | `false` | Run in-process unit tests (~40 tests) and exit |
| `--save-config` | `""` | Save config to JSON file and exit |
| `--config` | `""` | Load config from JSON file |
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

## Feature Deep-Dive

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

The root-level `research-*.md` files document the design process behind
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
├── LICENSE                      ← MIT
├── .gitignore
├── .env.example                 ← All config parameters as env vars
├── SKILL.md                     ← Original Hermes skill file (83 KB)
│
├── launch-loop.py               ← Main daemon (287 KB, 7,557 lines) ★
├── session-self-loop.py         ← In-session loop tracker ★
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
└── references/                  ← Design docs
    └── ...
```
