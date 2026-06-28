# pi-loop

A lightweight, self-contained task automation daemon that watches files, runs tasks iteratively in a loop, and tracks progress in a JSON ledger. Designed to integrate with the **pi coding agent** as a background worker.

## Quick Start

```bash
# Install
pip install -e .

# Run with a goal
pi-loop --goal "Fix all lint errors" --git --git-commit --run

# See all flags
pi-loop --help

# Check environment before running
pi-loop --preflight
```

## Features

- **Iterative task execution** — runs a worker subprocess repeatedly until the goal is met or a limit is reached
- **JSON ledger** — full iteration history stored at `/tmp/infinite-loop-state.json`
- **Sentinel control** — `echo stop > /tmp/infinite-loop-stop` to gracefully stop
- **Git integration** — auto-commit changes, track git diff stats
- **Convergence detection** — stops when iteration outputs become repetitive
- **Adaptive cooldown** — adjusts wait time between iterations based on task duration
- **Multi-worker** — parallel execution with multiple workers
- **Error recovery** — automatic retry and mitigation escalation
- **Goals file** — batch-process multiple goals from a file
- **Webhook & REST control** — trigger iterations via HTTP
- **HTML dashboard** — live status page
- **Desktop & push notifications** — notify-send, PushBullet, ntfy.sh
- **Self-healing heartbeat** — detect and recover hung sessions
- **Shell completion** — tab completion for bash/zsh

## CLI Flags

See `pi-loop --list-flags` for the full categorized reference.

Basic usage:

```
pi-loop --goal "<task description>" --run
pi-loop --goal "<task>" --git --git-commit --run
pi-loop --goals-file goals.txt --workers 3 --run
pi-loop --preflight
pi-loop --status
pi-loop --healthcheck
```

## Configuration

Set options via CLI flags or a `.env` file. See `.env.example` for all supported variables.

```bash
# Create .env from template
cp .env.example .env
# Edit .env with your preferences
pi-loop --goal "..." --run   # reads .env automatically
```

## Architecture

```
┌─────────────────────────────────────────────┐
│                   pi-loop                    │
│                                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │ CLI      │──▶│ Loop     │──▶│ Worker   │ │
│  │ argparse │   │ Engine   │   │ (pi -q)  │ │
│  └──────────┘   └──────────┘   └──────────┘ │
│                       │                      │
│                 ┌─────▼──────┐               │
│                 │ JSON       │               │
│                 │ Ledger     │               │
│                 └────────────┘               │
└─────────────────────────────────────────────┘
```

The daemon spawns a `pi -q <goal>` subprocess for each iteration, captures its output, records results in the ledger, and either continues or stops based on configured limits.

## Development

```bash
# Install in editable mode
pip install -e .

# Lint and format
make lint
make format

# Clean up temp files
make clean
```

## License

MIT
