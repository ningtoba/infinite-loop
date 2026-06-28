# Web Stack Architecture

A dedicated reference for web/UI contributors. This document covers the three
web-facing components of the Infinite Loop Daemon — what they are, how they
work, and how to build on them.

| Component | Technology | Purpose | Default Port / Path |
|-----------|-----------|---------|---------------------|
| Static HTML Dashboard | stdlib `http.server`, inline HTML/CSS/JS | Quick monitoring — a self-contained HTML file, no dependencies | Configurable via `--status-html PATH` |
| SSE Live Dashboard | Inline HTML + JS `EventSource` | Live-updating dark-theme dashboard, embedded in the daemon process | Written alongside the static HTML file; serves SSE on the status-HTML path |
| FastAPI SPA (`web_app/`) | FastAPI + uvicorn + xterm.js | Full management UI: start/stop daemon, config editor, iteration browser, live logs, per-worker xterm.js terminal | `http://0.0.0.0:8090` (configurable via `WEB_PORT`) |

All three are powered by the same data source: the JSON ledger at
`/tmp/infinite-loop-state.json`. There is no database, no ORM, no build step —
the entire web stack is zero-dependency for the dashboard layer and only
requires `pip install hermes-loop[web]` for the FastAPI SPA.

---

## 1. Static HTML Dashboard (`hermes_loop/dashboard.py`)

### How It Runs

The static dashboard is a **single self-contained HTML file** written to disk by
`_write_status_html()` after every iteration. It uses `<meta http-equiv="refresh"
content="30">` for polling — no server-side component required beyond the file
being served by any HTTP server.

### Generating the File

```python
# In iteration.py, after _build_iteration_record():
if state.get("status_html_path"):
    _write_status_html(state)
```

The function reads the full ledger, renders all state into an HTML template
(`_STATUS_HTML_TPL`), and writes it to the configured path. The template is a
Python triple-quoted string in `dashboard.py` — no templating engine, no
framework.

### Key Features

- **Compact mode** — stores a toggle in `localStorage`. Hidden by default; when
  enabled, hides all tables and shows a terse one-liner suitable for tmux
  bottom-panels or status-bar widgets.
- **Dark/light mode** — uses `prefers-color-scheme` media query. Two CSS
  variable blocks at `:root`.
- **Inline SVG favicon** — the infinity symbol (♾️) embedded as a data URI.
- **Zero dependencies** — works from Python 3.12 stdlib alone. No `npm install`,
  no `pip install`.

### Limitations

- Polling-based (30s refresh). Not suitable for real-time monitoring at
  sub-second granularity.
- No interactivity beyond compact mode toggle.
- The full template is generated server-side every iteration — large ledgers
  mean large HTML files.

---

## 2. SSE Live Dashboard (`hermes_loop/dashboard.py`)

### How It Runs

The SSE live dashboard shares the same `dashboard.py` module. It adds a
**Server-Sent Events** (SSE) layer so browsers receive live updates without
polling. Enabled automatically when `--status-html PATH` is set and the daemon
calls `_broadcast_to_sse_clients()`.

### Architecture

```
Daemon (loop.py / iteration.py)          SSE Clients (browser)
      │                                        │
      ├─ _build_iteration_record()             │
      ├─ _recalc_stats()                       │
      ├─ _write_status_html(state)             │
      └─ _broadcast_to_sse_clients(state)──────┤
                                               ├─ EventSource('/live')
                                               ├─ {type: "init", data: status}
                                               ├─ {type: "update", data: {...}}
                                               └─ {type: "heartbeat", data: {...}}
```

### Client Management

SSE clients are tracked in a module-level list of `queue.Queue` objects:

```python
_sse_clients: list[queue.Queue] = []
_sse_clients_lock = threading.Lock()
```

- Each browser connection gets a **bounded queue** (max 128 items).
- If `QueueFull` is raised on `put_nowait()`, the slow client is removed
  automatically — this prevents unbounded memory growth from slow/disconnected
  clients.
- **Stale-client detection**: `_sse_client_last_active` maps queue IDs to
  `time.monotonic()` timestamps. Clients with no activity for 60 seconds are
  proactively removed on the next broadcast sweep.
- Broadcast holds `_sse_clients_lock` for the duration of the sweep — keep this
  fast. Dead clients are removed synchronously before releasing the lock.

### SSE Event Types

| Event Name | Payload | Frequency |
|-----------|---------|-----------|
| `init` | Full status snapshot (from `_build_sse_payload()`) | On connection |
| `update` | `{"type":"status_update","data":status}` | On any state change |
| `update` | `{"type":"log_entry","entry":{"timestamp","message"}}` | Per new log line |
| `heartbeat` | `{"type":"heartbeat","time":"..."}` | Every 15s idle |

### Smart Change Detection

`_broadcast_to_sse_clients()` builds a **hash** from:

- Iteration number
- Worker statuses (all workers, `id:status` joined by `|`)
- `error_counts` and `mitigations`
- Log count and total terminal lines
- Latest iteration fields: `worktree_merge`, `error`, `classification`, first 60
  chars of `summary`

Only broadcasts when the hash changes, avoiding redundant pushes. When nothing
changes for 5 idle ticks (~10s), a keepalive status is pushed anyway.

### SSE Payload Shape

The `_build_sse_payload()` function in `dashboard.py` returns:

| Field | Type | Source |
|-------|------|--------|
| `loop_status` | string | `"running"`, `"stopped"`, `"paused"` |
| `status` | dict | Ledger top-level fields |
| `stats` | dict | `_recalc_stats()` output |
| `error_counts` | dict | `ledger["error_type_counts"]` |
| `mitigations` | dict | `ledger["mitigations"]` |
| `eta` | dict | `ledger["eta"]` |
| `avg_chars_per_iter` | int or null | Computed from iteration `output_chars` |
| `avg_throughput` | float or null | Average `chars_per_second` |
| `iters_per_goal` | int | `total_iterations / len(goals_specs)` |
| `metrics_summary` | string | Combined metrics string |
| `est_cost` | dict or null | `ledger["est_cost"]` |
| `remote_cleanup_totals` | dict | Aggregated remote cleanup stats |
| `latest_iteration` | dict | Last iteration record |
| `iterations` | array | Last 20 iterations (newest first) |
| `live_iteration` | dict | In-progress iteration state |
| `worker_logs` | dict | `wid -> [log entries]` |
| `worker_term` | dict | `wid -> [ANSI terminal lines]` |

### Dashboard HTML Features

The SSE dashboard HTML (generated by `_STATUS_HTML_TPL` with the SSE script
block appended) includes:

- **Status badge**: `running` (blue), `stopped` (red), `paused` (yellow)
- **Stats grid**: success/error counts, avg duration, consecutive errors, ETA
- **Progress bar**: % of `max_iterations`
- **Error cards**: colored side-border per error type (timeout=red, network=orange,
  schema=yellow, heartbeat=purple, unknown=gray)
- **Mitigations panel**: active mitigations with left borders
- **Goals panel**: progress bar + per-goal rows — ✓ done, ▶ active, ○ pending
  - Capped at 30 visible goals; "+ N more" overflow indicator
  - Deleted goals shown with strikethrough
- **Metrics panel**: chars/iter, throughput (cps), est cost, iters/goal
- **Worktree merge column**: `wt:3✓ 0✗` with tooltip showing branches,
  per-worker details, merge counts, and conflicts
- **Remote cleanup column**: `clean:r1del/s1` with tooltip
- **Reset detection**: if `total_iterations` drops, table clears
- **Compact mode**: localStorage-persisted toggle
- **Links**: to JSON API (`/api/status`), simple status (`/status`), and
  health-check endpoint (`/health`)

---

## 3. FastAPI SPA (`web_app/`)

### Package Structure

```
web_app/
├── __init__.py           # Package marker, version string
├── __main__.py           # Allows `python -m web_app`
├── server.py             # FastAPI app, all REST endpoints, SSE, background poller
├── config_manager.py     # Config schema (CONFIG_DEFAULTS), JSON persistence, CLI builder
├── loop_manager.py       # Daemon subprocess lifecycle (start/stop/pause/resume)
└── static/
    ├── index.html        # SPA shell: sidebar + 5 tabs (Dashboard, Config, Workers, Logs, Archives)
    ├── app.js            # All UI logic: SSE client, DOM rendering, tab switching, API calls
    └── style.css         # Dark-first design system with prefers-color-scheme light mode
```

### Entry Points

| Method | Command |
|--------|---------|
| Console script | `hermes_loop_web` (registered in `pyproject.toml`) |
| Module invocation | `python -m web_app` |
| Docker | `python -m web_app --host 0.0.0.0` (set in Dockerfile ENTRYPOINT) |

### REST API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve SPA shell (index.html) |
| GET | `/api/config` | Full config with defaults + current values + groups |
| GET | `/api/config/groups` | Config group names/IDs only (lightweight) |
| GET | `/api/config/raw` | Raw key-value config dict |
| POST | `/api/config` | Save config to `/tmp/hermes-loop/config.json` |
| GET | `/api/config/cli-preview` | Preview generated `--flag value` CLI args |
| POST | `/api/loop/start` | Start daemon subprocess |
| POST | `/api/loop/stop` | Write sentinel, SIGTERM, SIGKILL fallback |
| POST | `/api/loop/pause` | Write `"pause"` to sentinel |
| POST | `/api/loop/resume` | Remove sentinel |
| POST | `/api/loop/reset` | Delete ledger + lock file |
| GET | `/api/status` | Combined loop + ledger + live iteration status |
| GET | `/api/ledger` | Full ledger state |
| GET | `/api/iterations` | Paginated iteration history (`?limit=N&offset=M`) |
| GET | `/api/logs` | Last N log entries from the web manager |
| GET | `/api/health` | Health check — `{"status":"ok","timestamp":"..."}` |
| GET | `/live` | SSE EventSource stream |
| GET | `/static/*` | Static files (app.js, style.css) |

### Config Persistence (`config_manager.py`)

The web UI is the **sole source of truth** for configuration. Config is stored
as a flat JSON dict at `/tmp/hermes-loop/config.json` — no `.env` file is
needed or read when using the web UI.

**Schema-driven rendering:**

```python
CONFIG_DEFAULTS = {
    "INFINITE_LOOP_GOAL": {
        "default": "",
        "type": "string",
        "group": "core",
        "label": "Goal",
        "description": "Core task description for spawned Hermes sessions",
        "required": True,
        "multiline": True,
    },
    ...
}
```

Supported field types: `string`, `int`, `float`, `bool`, `select` (with
`options` array), `multiline`. Required fields show a `*` marker. The frontend
renders each field according to its type, grouped by `CONFIG_GROUPS`.

**CLI args builder** (`build_cli_args()`):

Maps env-var names to CLI flags:

```
INFINITE_LOOP_GOAL="Fix lint errors"  →  --goal "Fix lint errors"
INFINITE_LOOP_GIT=true                 →  --git
```

- Skips empty/default values
- Maps `--no-XXX` for boolean flags that default to `true`
- Maps `:` separator for list-type flags (e.g., `--toolsets terminal:file`)
- Forces `--run` so the daemon starts immediately
- Forces `--worker-url ""` for live stdout streaming (direct subprocess mode)

### Daemon Lifecycle (`loop_manager.py`)

`LoopManager` is a singleton that manages the infinite-loop daemon as an
asyncio subprocess.

```python
LoopManager
  ├─ start()       → kills stale daemons (pkill -f), reads JSON config,
  │                  builds CLI args, creates_subprocess_exec,
  │                  starts stdout/stderr readers + process monitor
  ├─ stop()        → writes sentinel, kills process group (SIGTERM,
  │                  SIGKILL after 5s timeout)
  ├─ pause()       → writes "pause" to sentinel
  ├─ resume()      → removes sentinel
  └─ get_status()  → merges ledger state + live iteration state +
                     worker logs + terminal lines + recent web manager logs
```

**Kill Sequence (stop)** — three-tier:

1. Write `stop` to sentinel file (`/tmp/infinite-loop-stop`)
2. `os.killpg(pgid, SIGTERM)` — waits 5s for graceful exit
3. If timeout: `os.killpg(pgid, SIGKILL)` — forced termination

**Stale daemon cleanup** (`_kill_stale_daemons`):

Uses `pkill -f` with a precise pattern:
`python.*-m\s+hermes_loop.*--run`. This avoids matching non-daemon Python
processes. Called at the start of every `start()`.

**Docker awareness:**

```python
in_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER", "")
```

When in Docker:
- Overrides `workdir` to `/workdir`
- Appends `--workdir /workdir` if missing
- Stale `/workdir` paths from the config JSON are auto-cleared when running on
  the host

### Live Stream Parsing (`_parse_daemon_line`)

The LoopManager parses daemon stdout in real-time to extract structured worker
state:

| Log Pattern | Parsed State |
|-------------|-------------|
| `[HH:MM:SS] Iteration N` | `live_iteration.n = N`, resets workers |
| `[STDOUT (worker #N)]` / `[STDERR (worker #N)]` | Worker status = `running` |
| `[TERM (worker #N)] ...` | Appended to `worker_term[N]` (preserves ANSI) |
| `[SPAWN (worker #N)]` | Worker registered as `spawned` |
| `[WORKER (worker #N)] Response in Xs (status=ok)` | Worker completed with duration |
| `[BEAT] Iteration N still running (Xs)` | `live_iteration.elapsed_seconds = X` |
| `[ERROR-TYPE] timeout` | `live_iteration.error_type = timeout` |

The `worker_term` storage powers the xterm.js terminal view in the Workers tab.
Raw ANSI escape sequences are preserved so colored output renders correctly
in-browser.

### SSE in the FastAPI SPA

The FastAPI app provides its own SSE endpoint at `/live`, separate from the
daemon's built-in SSE. The background `_status_poller` task:

- Wakes every **2 seconds**
- Reads the ledger via `LoopManager.get_status()`
- Builds a hash (same change-detection strategy as the daemon's SSE)
- Broadcasts only on hash change, with a fallback keepalive every ~10s
- Dispatches new log entries individually as `log_entry` SSE events
- Dedup via a `_seen_log_keys` set (capped at 5000 entries)
- Absorbs all exceptions silently (poller never crashes)

### CSS Design System (`static/style.css`)

- **Dark-first**: `--bg-primary: #09090b` base
- **Light mode**: secondary `prefers-color-scheme` block
- **Purple accent**: `--accent: #6c5ce7` with glow `--accent-glow: rgba(108, 92, 231, 0.15)`
- **Layout**: 240px sidebar + flex main content area
- **Status cards**: rounded corners with hover border highlight
- **Tables**: sticky headers, hover row highlight, error-row red tint
- **Config page**: split layout (group sidebar + settings panel), inline descriptions
- **Workers tab**: xterm.js terminal per worker via CDN
- **Responsive**: sidebar collapses at 768px, config layout stacks vertically on mobile

### Frontend Architecture (`static/app.js`)

The SPA frontend is a vanilla JS application (no React, no build step):

- **Single entry point**: `index.html` loads `app.js` via `<script>` tag
- **Tab system**: 5 tabs (Dashboard, Config, Workers, Logs, Archives)
- **SSE client**: `EventSource` connects to `/live`, handles `init` and `update`
  events, reconnects automatically on disconnect
- **DOM rendering**: functions like `renderDashboard()`, `renderConfig()`,
  `renderWorkers()`, `renderLogs()`, `renderArchives()` update their respective
  panels
- **API calls**: `fetch()` for all REST endpoints, with error handling and
  loading states
- **Form handling**: config form submits via `POST /api/config`, start/stop
  buttons call their respective endpoints

No bundler, no transpiler, no npm. The entire frontend is served as static
files and works in any modern browser.

---

## 4. Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y git curl procps
WORKDIR /app
COPY pyproject.toml .
RUN pip install fastapi uvicorn python-dotenv
COPY web_app/ ./web_app/
COPY hermes_loop/ ./hermes_loop/
ENV WEB_PORT=8090
HEALTHCHECK --interval=30s ... CMD curl -fs http://localhost:${WEB_PORT}/api/health
ENTRYPOINT ["python", "-m", "web_app", "--host", "0.0.0.0"]
```

### docker-compose.yml

```yaml
services:
  hermes-loop:
    build: .
    network_mode: host
    pid: host               # nsenter needs host PID namespace
    privileged: true        # nsenter needs CAP_SYS_PTRACE
    volumes:
      - ${INFINITE_LOOP_WORKDIR:-/tmp}:/workdir
      - hermes-loop-data:/tmp
```

### Critical Design Decisions

| Decision | Rationale |
|----------|-----------|
| `network_mode: host` | The container uses `nsenter` to run Hermes on the host; needs host networking to reach the Hermes binary |
| `pid: host` | Access the host's process namespace so `nsenter` can enter any host process |
| `privileged: true` | `nsenter` needs `CAP_SYS_PTRACE` to attach to non-child processes |
| Ledger at `/tmp` via named volume | Canonical ledger path must persist across container restarts |
| Workdir as bind mount | `INFINITE_LOOP_WORKDIR` maps to `/workdir` inside the container |
| `python -m web_app` | The container runs only the Web UI — the daemon is spawned as its subprocess, which delegates to host Hermes via nsenter |

### .dockerignore

Excludes: `research/`, `references/`, `scripts/`, `run.sh`, `.env`, `Makefile`,
`CHANGELOG.md`, `CONTRIBUTING.md`, and other runtime-unnecessary files.

---

## 5. How the Three Components Relate

```
                            ┌──────────────────────────────┐
                            │       JSON Ledger             │
                            │  /tmp/infinite-loop-state.json │
                            └──────────────┬───────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
       ┌────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
       │  Static HTML    │  │   SSE Live Dashboard│  │  FastAPI SPA        │
       │  dashboard.py   │  │   dashboard.py (SSE) │  │  web_app/           │
       │                 │  │                     │  │                     │
       │  - Polling      │  │  - Real-time SSE    │  │  - Full management  │
       │  - No deps      │  │  - Embedded in      │  │  - Start/stop       │
       │  - Status-bar   │  │    daemon process   │  │  - Config editor    │
       │    friendly     │  │  - Change detection │  │  - xterm.js workers │
       │                 │  │  - Stale-client     │  │  - LED lifecycle    │
       └────────────────┘  │    cleanup          │  │  - Docker-enabled   │
                           └─────────────────────┘  └─────────────────────┘
```

- All three read the same JSON ledger file.
- The **Static HTML Dashboard** is the most lightweight — suitable for tmux
  panels, status bars, or embedding in other dashboards.
- The **SSE Live Dashboard** is the middle ground — real-time without a
  server-side framework, but still limited to monitoring (no controls).
- The **FastAPI SPA** is the full-featured management interface — controls the
  daemon lifecycle, edits config, shows per-worker xterm.js terminals.

---

## 6. Development Setup

```bash
# Install with web extras
pip install -e ".[web]"

# Start the web UI
hermes_loop_web --port 8090

# Or with auto-reload for development
python -m web_app --reload

# Docker
docker compose up --build
```

### Key Source Files

| File | What You'll Find |
|------|-----------------|
| `hermes_loop/dashboard.py` | `_write_status_html()`, `_broadcast_to_sse_clients()`, `_build_sse_payload()`, `_sse_clients` list, `_STATUS_HTML_TPL` template |
| `web_app/server.py` | FastAPI routes, SSE handler, background `_status_poller`, `main()` entry point |
| `web_app/loop_manager.py` | `LoopManager` class — subprocess lifecycle, stdout parsing, worker state tracking, `_parse_daemon_line()` regex patterns |
| `web_app/config_manager.py` | `CONFIG_DEFAULTS` schema, JSON persistence, `build_cli_args()` |
| `web_app/static/index.html` | SPA shell — sidebar, 5 tab panels, xterm.js CDN link |
| `web_app/static/app.js` | All frontend JS — SSE client, tab rendering, API calls, DOM updates |
| `web_app/static/style.css` | CSS design system — dark-first, purple accent, responsive layout |

---

## 7. Adding a New Feature (Example Walkthrough)

Suppose you want to add a "restart daemon" button to the FastAPI SPA:

1. **Backend** (`server.py`): Add `POST /api/loop/restart` that calls
   `manager.stop()` followed by `manager.start()`:
   ```python
   @app.post("/api/loop/restart")
   async def restart_loop():
       manager = get_loop_manager()
       await manager.stop()
       result = await manager.start()
       await _broadcast_sse({"type": "status", "status": result.get("success", False)})
       return result
   ```

2. **Frontend** (`static/app.js`): Add a "Restart" button next to Start/Stop,
   calling `fetch("/api/loop/restart", {method: "POST"})`.

3. **SSE update**: The `_broadcast_sse` call in step 1 pushes the new status to
   all connected browsers — the dashboard tab updates automatically.

No page reload needed, no database migration, no state schema change.
