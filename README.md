# π pi-loop

**Autonomous task loop daemon — powered by the pi coding agent**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](#license) ![Python](https://img.shields.io/badge/python-≥3.10-blue) [![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

</div>

pi-loop is a self-contained Python daemon that runs tasks iteratively in a loop, tracks progress in a JSON ledger, and surfaces everything through a beautiful dark-theme web dashboard. It delegates each iteration to the [pi coding agent](https://pi.ai) and handles the orchestration — convergence detection, error recovery, cooldown management, git auto-commit, multi-worker parallelism, and real-time monitoring.

All configuration is done through the web UI — no `.env` files, no manual config editing.

---

## Features

- **Iterative task execution** — spawns `pi -q <goal>` subprocesses repeatedly until the goal is met or a limit is reached
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
- **[pi coding agent](https://pi.ai)** — the binary (`pi`) must be on `$PATH` and licensed. Verify with:

  ```bash
  pi --version
  ```

- **Git** (optional, required for `--git` / `--git-commit` features)

## Quick Start

```bash
# Install in editable mode (recommended)
pip install -e .

# Start the web UI dashboard
pi-loop-web

# Open http://localhost:8090 in your browser
```

The web UI includes a **Swagger API reference** at [http://localhost:8090/docs](http://localhost:8090/docs) — interactive documentation for all REST endpoints.

From the web UI, configure your goal and settings, then hit **Start**.

### CLI Quickstart

```bash
# Run a task from the command line
pi-loop --goal "Fix all lint errors" --run

# Run with git auto-commit
pi-loop --goal "Refactor auth module" --git --git-commit --run

# Run multiple goals in parallel
pi-loop --goals-file goals.txt --workers 3 --run

# Preflight check — verify environment before running
pi-loop --preflight

# Check status of a running loop
pi-loop --status
```

---

## Web UI Dashboard

The web UI is a single-page application built with **FastAPI** on the backend and vanilla HTML/CSS/JS on the frontend — no framework dependencies.

![pi-loop Web UI](https://img.shields.io/badge/UI-Dark_Theme-09090b?style=flat-square)

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
pi-loop-web
```

For development (with auto-reload):

```bash
make web-dev
```

The server binds to `0.0.0.0:8090` by default. Pass custom options:

```bash
pi-loop-web --host 127.0.0.1 --port 8080
```

---

## Authentication & Security

pi-loop provides several layers of security for production deployments, all optional and backward-compatible for local development.

### API-Key Authentication

Set the `PI_LOOP_API_KEY` environment variable to enable Bearer-token authentication on all `/api/*` routes:

```bash
export PI_LOOP_API_KEY="your-secret-key"
pi-loop-web
```

With the key set, every API request must include:

```
Authorization: Bearer your-secret-key
```

- Requests without a valid `Authorization` header receive `401 Unauthorized` with a `WWW-Authenticate: Bearer` response header.
- The `/api/health` endpoint is always exempt (required for load-balancer health checks).
- Non-`/api/*` paths (static assets, the main HTML page) are also exempt.
- When `PI_LOOP_API_KEY` is unset or empty, authentication is **disabled** — all requests pass through (local-dev mode).

### Rate Limiting

All `/api/*` routes are protected by a sliding-window rate limiter keyed by client IP:

| Endpoint Type          | Limit       | Window |
|------------------------|-------------|--------|
| Control (POST /api/config, POST /api/loop/*) | 30 requests | 60 seconds |
| Read-only (GET /api/*) | 120 requests | 60 seconds |

- Rate-limited requests receive `429 Too Many Requests` with a `Retry-After` header.
- Every response includes `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers.
- Rate limiting operates independently of authentication — it applies even when `PI_LOOP_API_KEY` is unset.

### CORS

By default, the server only accepts cross-origin requests from `http://localhost:8090`. Override via the `PI_LOOP_CORS_ORIGINS` environment variable (comma-separated):

```bash
export PI_LOOP_CORS_ORIGINS="http://localhost:8090,https://my-dashboard.example.com"
```

Using `*` as an origin is allowed but emits a warning. In production, always specify explicit origins.

### Network Binding

The web server binds to `127.0.0.1` (localhost only) by default, preventing external network access. Override with the `--host` flag:

```bash
pi-loop-web --host 0.0.0.0  # Bind to all interfaces (production with firewall)
```

### Security Summary

| Setting | Default | Override |
|---------|---------|----------|
| API key auth | Disabled (no key) | `PI_LOOP_API_KEY` env var |
| Rate limiting | Control: 30 req/min, Read: 120 req/min | (hardcoded) |
| CORS origins | `http://localhost:8090` | `PI_LOOP_CORS_ORIGINS` env var |
| Bind address | `127.0.0.1` | `--host` flag |

---

## CLI Usage

```
pi-loop --help
```

### Core commands

| Command | Description |
|---------|-------------|
| `pi-loop --goal "<task>" --run` | Single run |
| `pi-loop --goals-file FILE --workers N --run` | Batch multiple goals |
| `pi-loop --status` | Show current loop status |
| `pi-loop --preflight` | Verify environment readiness |
| `pi-loop --healthcheck` | Run health diagnostics |
| `pi-loop --list-flags` | Full categorized flag reference |
| `pi-loop --doctor` | Diagnose configuration issues |

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
│                        pi-loop                               │
│                                                              │
│  ┌────────────┐    ┌──────────────┐    ┌──────────────────┐ │
│  │   CLI      │───▶│   Loop       │───▶│   Worker(s)      │ │
│  │  argparse  │    │   Engine     │    │   (pi -q goal)   │ │
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

1. **CLI layer** — `argparse`-based entry point (`pi-loop`) that parses flags, sets up logging, and starts the loop engine
2. **Loop Engine** — the core orchestrator (`loop.py`) that manages iteration scheduling, convergence detection, error recovery, cooldown, worker lifecycle, and ledger persistence
3. **Web UI layer** — FastAPI server (`pi-loop-web`) providing a REST API and real-time SSE stream, backed by a static SPA with dark-theme dashboard

Each iteration spawns a `pi -q <goal>` subprocess, captures its output, records results in the JSON ledger, and determines whether to continue or stop based on configured limits.

---

## Development

```bash
# Clone and install in editable mode
git clone <repo-url>
cd pi-loop
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
pi-loop/
├── pi_loop/              # Core daemon package
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
