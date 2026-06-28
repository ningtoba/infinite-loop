# pi-loop Web App — Architecture & Developer Guide

## Overview

The web app (`web_app/`) provides a REST API and browser-based UI for managing
the pi-loop autonomous task daemon. It lives alongside `pi_loop/` and depends
on it for configuration schemas but does **not** import the daemon's runtime
modules — the daemon is launched as a **subprocess** whose stdout/stderr are
parsed for live worker progress.

## File Map

| File | Role |
|------|------|
| `__init__.py` | Package metadata |
| `__main__.py` | Entry point: `python -m web_app [--host HOST] [--port PORT] [--reload]` |
| `server.py` | FastAPI server — REST endpoints + SSE + static file serving |
| `config_manager.py` | Config schema, JSON I/O, CLI-arg builder, validation |
| `loop_manager.py` | Subprocess lifecycle (start/stop/pause/resume), stdout parsing, SSE |
| `static/index.html` | Single-page application shell |
| `static/style.css` | Themed CSS with dark/light support |
| `static/app.js` | SPA — REST fetches, SSE listener, DOM rendering |

**Note:** The `web_app/` package is the **current, actively maintained** web interface.
It was preserved and enhanced after a prior `hermes_loop` → `pi_loop` rename;
see the integration notes at the bottom of this document.

## Data Flow

```
Browser (SPA)
  │
  ├── REST (fetch) ──► server.py ──► loop_manager.py ──► subprocess: pi_loop
  │                                    │
  │                                    └── stdout parser (regex)
  │                                    │
  │                                    └── _logs[] (in-memory ring buffer)
  │
  └── SSE (EventSource) ◄─── /api/live ◄─── _sse_clients[]
                        ◄─── /live (legacy)
```

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Combined loop + ledger status |
| `/api/ledger` | GET | Raw ledger JSON |
| `/api/config` | GET | Full config schema with values |
| `/api/config/raw` | GET | Flat key-value config dict |
| `/api/config` | POST | Save config to JSON file |
| `/api/config/groups` | GET | Config group definitions |
| `/api/config/cli-preview` | GET | CLI args that would be used |
| `/api/iterations` | GET | Paginated iteration history |
| `/api/logs` | GET | Recent daemon log entries |
| `/api/system` | GET | CPU / memory / disk usage |
| `/api/health` | GET | Health check |
| `/api/loop/start` | POST | Start daemon subprocess |
| `/api/loop/stop` | POST | Stop daemon (sentinel + SIGTERM) |
| `/api/loop/pause` | POST | Pause daemon (sentinel) |
| `/api/loop/resume` | POST | Resume daemon |
| `/api/loop/reset` | POST | Clear iteration state files |
| `/api/live` | GET | SSE stream (canonical) |
| `/live` | GET | SSE stream (legacy, same handler) |

### SSE Stream

The `/api/live` endpoint returns `text/event-stream` with events:

- **`init`** — initial full status snapshot on connect
- **`update`** — status changes, new log entries
- **`heartbeat`** — keepalive every 15s

A background `_status_poller()` coroutine runs every 2s, computes a hash of
the current state, and broadcasts via `_broadcast_sse()` only when the hash
changes (plus a periodic keepalive every ~10s).

## Config Persistence

The config layer uses **two storage mechanisms**:

1. **JSON file** (`/tmp/pi-loop/config.json` by default, overridable via
   `PI_LOOP_DATA_DIR` or `CONFIG_PATH` env vars):
   - Flat `dict[str, str]` (all values serialised as strings).
   - Read by `read_json_config()` -> `get_config_with_defaults()`.
   - Written by `write_json_config()` (from Save Config button).

2. **`.env` file** (optional, pointed at via `--env` or `PI_LOOP_ENV_PATH`):
   - Not currently read by the web app; the daemon subprocess inherits
     the web server's environment (supplemented by `os.environ.copy()`).

### Type Coercion

`read_json_config()` coerces values according to each key's `meta["type"]`:

- `bool` → `"true"` / `"false"`
- `int` → `str(int(v))`
- `float` → `str(float(v))`
- `select` / `string` → `str(v)`

This ensures round-trip consistency between `read`→`display`→`save` cycles.

## Subprocess Lifecycle (loop_manager.py)

```
start()
  ├── read config → build_cli_args()
  ├── create_subprocess_exec(pi_loop, ...)  (with 30s timeout)
  ├── verify process alive (sleep 0.1, check returncode)
  ├── status = "running"
  ├── spawn: _read_stream(stdout), _read_stream(stderr)
  └── spawn: _monitor_process()

stop()
  ├── write sentinel file
  ├── os.killpg(pgid, SIGTERM) + wait 5s
  ├── on timeout: killpg(pgid, SIGKILL) + wait 5s
  └── close log file handle

_monitor_process()
  └── await process.wait() → update status
```

### Stdout Parsing

Lines from the daemon's stdout are parsed via regex in `_parse_daemon_line()`:

- `[HH:MM:SS] Iteration N` → new iteration started
- `[BEAT] Iteration N still running (Ns)` → elapsed seconds
- `[SPAWN (worker #N)]` → worker created
- `[WORKER (worker #N)] Response in Xs (status=Y)` → worker completed
- `[STDOUT (worker #N)]`, `[STDERR (worker #N)]` → log/error lines
- `[TERM (worker #N)]` → terminal output for xterm.js
- `[ERROR-TYPE] Foo` → error classification

## Themes (light/dark)

The app has a two-way theme toggle (toggle button in sidebar footer):

1. **CSS media query** `@media (prefers-color-scheme: light)` — default theme.
2. **`[data-theme="light"]`** — overrides to light when user toggles.
3. **`[data-theme="dark"]`** — overrides to dark when user toggles back.

The toggle saves preference to `localStorage` under `pi-loop-theme`.

## SSE Client Cleanup

- New SSE connections push an `asyncio.Queue(maxsize=32)` to `_sse_clients`.
- `_broadcast_sse()` removes queues that raise `QueueFull` (stale clients).
- `_sse_stream_impl()` removes its queue in the `finally` block.
- `_status_poller()` tracks a tick counter and broadcasts stale client
  removals on every iteration (not yet periodic-watchdog gated).

## Log File Handle

`LoopManager` writes logs to `_log_file` (configurable via `PI_LOOP_WEB_LOG`
env var, default `/tmp/infinite-loop-web.log`). The file handle is closed by
`close()` which is called from `stop()` and `__del__()`.

## Paths (all configurable)

| Path | Env Var | Default |
|------|---------|---------|
| Ledger state | `PI_LOOP_LEDGER_PATH` | `/tmp/infinite-loop-state.json` |
| Sentinel | `PI_LOOP_SENTINEL_PATH` | `/tmp/infinite-loop-stop` |
| Status file | `PI_LOOP_STATUS_FILE` | `/tmp/loop-status.json` |
| Web log | `PI_LOOP_WEB_LOG` | `/tmp/infinite-loop-web.log` |
| Config JSON | `PI_LOOP_DATA_DIR` + `/pi-loop/config.json` | `/tmp/pi-loop/config.json` |

## Skeleton Loading

The CSS includes `.skeleton` and `@keyframes shimmer` animations (by default
inactive, usable via the `data-loaded="false"` attribute on `.status-card`).

---

---

## Status File Protocol

The daemon (`pi_loop/`) writes a lightweight JSON status file to
`/tmp/loop-status.json` (configurable via `PI_LOOP_STATUS_FILE` env var)
after every iteration and on shutdown. This file is written by
`pi_loop/status.py` on top of the existing `write_status_file()` in
`pi_loop/file_utils.py`.

**Status file fields:** `running`, `pid`, `start_time`, `iteration_count`,
`last_error`, `version`, `uptime`, `last_updated`.

The web app's `loop_manager.get_status()` reads the ledger for rich status;
the status file provides a minimal fallback for external monitoring.

---

*This document was originally the `hermes_loop` → `pi_loop` refactor plan
and was converted into the web-app architecture guide when the UI was
preserved and enhanced.*
