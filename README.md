# π omp-loop

**Autonomous task loop daemon — powered by the omp coding agent**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](#license) ![Python](https://img.shields.io/badge/python-≥3.10-blue) [![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

</div>

omp-loop is a self-contained Python daemon that runs tasks iteratively in a loop, tracks progress in a JSON ledger, and surfaces everything through a beautiful dark-theme web dashboard. It delegates each iteration to the [omp coding agent](https://pi.ai) and handles the orchestration — convergence detection, error recovery, cooldown management, git auto-commit, multi-worker parallelism, and real-time monitoring.

All configuration is done through the web UI — no `.env` files, no manual config editing.

---

## Features

- **Iterative task execution** — spawns `omp -q <goal>` subprocesses repeatedly until the goal is met or a limit is reached
- **Multi-worker parallelism** — run multiple workers in parallel for faster convergence
- **Convergence detection** — automatically stops when iteration outputs become repetitive
- **Adaptive cooldown** — adjusts wait time between iterations based on task duration
- **Error recovery** — automatic retry with severity-based escalation and actionable fix suggestions
- **Self-healing heartbeat** — detects and recovers hung sessions automatically
- **Git integration** — auto-commit changes and track git diff stats across iterations
- **Goals file** — batch-process multiple goals from a single file with optional profile/model/provider per goal
- **Progressive context** — automatically builds and passes accumulated context to each iteration
- **JSON ledger** — full iteration history stored at `/tmp/infinite-loop-state.json`
- **Web UI dashboard** — live status, iteration history, config editor, system resources, and real-time logs via SSE
- **REST control** — start, stop, pause, resume the daemon via HTTP
- **Webhooks** — trigger iterations via HTTP webhook
- **Sentinel control** — `echo stop > /tmp/infinite-loop-stop` to gracefully stop
- **Desktop & push notifications** — notify-send, PushBullet, ntfy.sh
- **Shell completion** — tab completion for bash and zsh

---

## Prerequisites

- **Python 3.10+** (3.10–3.13 tested in CI)
- **[omp coding agent](https://pi.ai)** — the binary (`omp`) must be on `$PATH` and licensed. Verify with:

  ```bash
  omp --version
  ```

- **Git** (optional, required for `--git` / `--git-commit` features)

## Quick Start

```bash
# Install in editable mode (recommended)
pip install -e .

# Start the web UI dashboard
omp-loop-web

# Open http://localhost:8090 in your browser
```

The web UI includes a **Swagger API reference** at [http://localhost:8090/docs](http://localhost:8090/docs) — interactive documentation for all REST endpoints.

From the web UI, configure your goal and settings, then hit **Start**.

### CLI Quickstart

```bash
# Run a task from the command line
omp-loop --goal "Fix all lint errors" --run

# Run with git auto-commit
omp-loop --goal "Refactor auth module" --git --git-commit --run

# Run multiple goals in parallel
omp-loop --goals-file goals.txt --workers 3 --run

# Preflight check — verify environment before running
omp-loop --preflight

# Check status of a running loop
omp-loop --status
```

---

## Web UI Dashboard

The web UI is a single-page application built with **FastAPI** on the backend and vanilla HTML/CSS/JS on the frontend — no framework dependencies.

![omp-loop Web UI](https://img.shields.io/badge/UI-Dark_Theme-09090b?style=flat-square)

> 📸 A screenshot of the dashboard is coming soon.

| Tab | Description |
|-----|-------------|
| **Dashboard** | Live status cards (loop state, iterations, success/errors, duration, progress bar), goal display, live terminal output via xterm.js, and start/pause/stop/reset controls |
| **Configuration** | Full JSON config editor with grouped settings — core, iteration control, git, error handling, notifications, workers, webhooks, session. Changes take effect immediately. |
| **Iterations** | Paginated iteration history with expandable details — output, errors, git diff stats, duration |
| **Logs** | Real-time daemon log stream with auto-scroll |
| **Workers** | Per-worker status, terminal output, and control |
| **System** | CPU, memory, and disk utilization |

Start the dashboard with:

```bash
omp-loop-web
```

For development (with auto-reload):

```bash
make web-dev
```

The server binds to `0.0.0.0:8090` by default. Pass custom options:

```bash
omp-loop-web --host 127.0.0.1 --port 8080
```

---

## Authentication & Security

omp-loop provides several layers of security for production deployments, all optional and backward-compatible for local development.

### API-Key Authentication

Set the `OMP_LOOP_API_KEY` environment variable to enable Bearer-token authentication on all `/api/*` routes:

```bash
export OMP_LOOP_API_KEY="your-secret-key"
omp-loop-web
```

With the key set, every API request must include:

```
Authorization: Bearer your-secret-key
```

- Requests without a valid `Authorization` header receive `401 Unauthorized` with a `WWW-Authenticate: Bearer` response header.
- The `/api/health` endpoint is always exempt (required for load-balancer health checks).
- Non-`/api/*` paths (static assets, the main HTML page) are also exempt.
- When `OMP_LOOP_API_KEY` is unset or empty, authentication is **disabled** — all requests pass through (local-dev mode).

### Rate Limiting

All `/api/*` routes are protected by a sliding-window rate limiter keyed by client IP:

| Endpoint Type          | Limit       | Window |
|------------------------|-------------|--------|
| Control (POST /api/config, POST /api/loop/*) | 30 requests | 60 seconds |
| Read-only (GET /api/*) | 120 requests | 60 seconds |

- Rate-limited requests receive `429 Too Many Requests` with a `Retry-After` header.
- Every response includes `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers.
- Rate limiting operates independently of authentication — it applies even when `OMP_LOOP_API_KEY` is unset.

### CORS

By default, the server only accepts cross-origin requests from `http://localhost:8090`. Override via the `OMP_LOOP_CORS_ORIGINS` environment variable (comma-separated):

```bash
export OMP_LOOP_CORS_ORIGINS="http://localhost:8090,https://my-dashboard.example.com"
```

Using `*` as an origin is allowed but emits a warning. In production, always specify explicit origins.

### Network Binding

The web server binds to `127.0.0.1` (localhost only) by default, preventing external network access. Override with the `--host` flag:

```bash
omp-loop-web --host 0.0.0.0  # Bind to all interfaces (production with firewall)
```

### On-Error Command Security

`--on-error-cmd` runs arbitrary shell commands via `subprocess.run(..., shell=True)` when an iteration
errors. This is inherently risky:

- **Command injection**: If an attacker gains write access to `~/.config/omp-loop/config.json`, they
  can execute arbitrary commands on the host system.
- **Audit logging**: Every `on_error_cmd` invocation is logged with the full command text.
- **Character restrictions**: By default, shell metacharacters (`;`, `|`, `` ` ``, `$`, `&`, `>`, `<`)
  are **rejected** unless you pass `--allow-error-metachars`. Only enable this flag when your
  command genuinely requires shell features like piping or variable expansion.
- **Length limit**: Commands are limited to 500 characters.

### Security Summary

| Setting | Default | Override |
|---------|---------|----------|
| API key auth | Disabled (no key) | `OMP_LOOP_API_KEY` env var |
| Rate limiting | Control: 30 req/min, Read: 120 req/min | (hardcoded) |
| CORS origins | `http://localhost:8090` | `OMP_LOOP_CORS_ORIGINS` env var |
| Bind address | `127.0.0.1` | `--host` flag |

---

## CLI Usage

```
omp-loop --help
```

### Core commands

| Command | Description |
|---------|-------------|
| `omp-loop --goal "<task>" --run` | Single run |
| `omp-loop --goals-file FILE --workers N --run` | Batch multiple goals |
| `omp-loop --status` | Show current loop status |
| `omp-loop --preflight` | Verify environment readiness |
| `omp-loop --healthcheck` | Run health diagnostics |
| `omp-loop --list-flags` | Full categorized flag reference |
| `omp-loop --doctor` | Diagnose configuration issues |

### Key flags

| Flag | Description |
|------|-------------|
| `--max-iterations N` | Stop after N iterations (0 = unlimited) |
| `--max-idle-iterations N` | Stop after N iterations with no changes |
| `--context "..."` | Context/instructions for the worker |
| `--context-file PATH` | Read context from a file |
| `--git` | Enable git diff tracking |
| `--git-commit` | Auto-commit changes between iterations |
| `--workers N` | Number of parallel workers (default: 1) |
| `--session-timeout SEC` | Worker session timeout in seconds |
| `--no-convergence` | Disable convergence detection |
| `--no-color` | Disable colored output |
| `--webhook URL` | Trigger iterations via HTTP POST |
| `--pushover USER_KEY` | Send Pushover notifications |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        omp-loop                               │
│                                                              │
│  ┌────────────┐    ┌──────────────┐    ┌──────────────────┐ │
│  │   CLI      │───▶│   Loop       │───▶│   Worker(s)      │ │
│  │  argparse  │    │   Engine     │    │   (omp -q goal)   │ │
│  └────────────┘    └──────┬───────┘    └──────────────────┘ │
│                           │                                  │
│                    ┌──────▼───────┐                          │
│                    │   JSON       │                          │
│                    │   Ledger     │                          │
│                    └──────────────┘                          │
│                           │                                  │
│                    ┌──────▼───────┐                          │
│                    │   Web UI     │                          │
│                    │  (FastAPI +  │                          │
│                    │   SPA)       │                          │
│                    └──────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

The daemon operates in three layers:

1. **CLI layer** — `argparse`-based entry point (`omp-loop`) that parses flags, sets up logging, and starts the loop engine
2. **Loop Engine** — the core orchestrator (`loop.py`) that manages iteration scheduling, convergence detection, error recovery, cooldown, worker lifecycle, and ledger persistence
3. **Web UI layer** — FastAPI server (`omp-loop-web`) providing a REST API and real-time SSE stream, backed by a static SPA with dark-theme dashboard

Each iteration spawns a `omp -q <goal>` subprocess, captures its output, records results in the JSON ledger, and determines whether to continue or stop based on configured limits.

---

## Development

```bash
# Clone and install in editable mode
git clone <repo-url>
cd omp-loop
pip install -e .

# Lint and format
make lint
make format

# Run the web UI in development mode (auto-reload on changes)
make web-dev

# Run the web UI in production mode
make web

# Clean up build artifacts and temp files
make clean
```

### Project structure

```
omp-loop/
├── omp_loop/              # Core daemon package
│   ├── cli.py            # CLI entry point and argparse setup
│   ├── loop.py           # Main loop engine
│   ├── config.py         # Constants, paths, and defaults
│   ├── functions.py      # Core helper functions
│   ├── error_recovery.py # Automatic error recovery
│   ├── git_utils.py      # Git integration
│   ├── heartbeat.py      # Heartbeat monitoring
│   ├── state.py          # Ledger state management
│   ├── file_utils.py     # File I/O utilities
│   └── ...
├── web_app/              # Web UI server
│   ├── server.py         # FastAPI application and REST endpoints
│   ├── config_manager.py # Web-based configuration
│   ├── loop_manager.py   # Loop lifecycle management
│   ├── static/           # SPA frontend
│   │   ├── index.html    # Main HTML
│   │   ├── style.css     # Dark theme styles
│   │   └── app.js        # Application logic
│   └── __main__.py       # Web server entry point
├── pyproject.toml        # Package configuration
├── Makefile              # Development targets
└── README.md
```

---

## License

[MIT](LICENSE)
