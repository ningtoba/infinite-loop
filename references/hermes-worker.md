# Hermes Worker — Self-Reference HTTP Server

## Overview

The Hermes Worker is a stdlib-only HTTP server that accepts prompts and
spawns `hermes chat -q` sessions on demand. It solves the **self-reference
problem**: when a spawned session modifies `launch-loop.py`, config, or
the skill itself, the next iteration loads the changes because each call
spawns a fresh Hermes session.

Two modes:

| Mode | Flag | Who starts it | Use case |
|------|------|--------------|----------|
| **Embedded** (`auto`) | `--worker-url auto` (default) | Daemon itself (HermesWorkerManager) | Normal use — no extra steps |
| **External** | `--worker-url http://host:port` | User (separate terminal) | When the worker must survive daemon restarts |

## Source

```
~/.hermes/plugins/hermes-mcp-worker/main.py
```

## Embedded Mode (`auto`)

The `HermesWorkerManager` class in `launch-loop.py`:

1. Finds a free port via `socket.bind(('', 0))`
2. Spawns `python3 main.py --port <random>` as a child process
3. Polls `/health` until ready (10s timeout)
4. Returns the URL to `run_loop()`, which passes it to `spawn_delegation_session`
5. Each iteration sends `POST /chat` to the embedded worker
6. On daemon exit (signal/stop/idle), `atexit` handler kills the child

If the worker script is missing or fails to start, the daemon falls back
to direct subprocess mode with a log warning — never errors.

## External Mode

```bash
# Terminal 1: Start the worker
python3 ~/.hermes/plugins/hermes-mcp-worker/main.py --port 8124

# Terminal 2: Launch loop
python3 scripts/launch-loop.py --goal "..." \
  --worker-url http://localhost:8124 \
  --run
```

Useful when iterating on `launch-loop.py` itself — the worker stays up
while you restart the daemon repeatedly.

## Protocol

### GET /health
```json
{"status": "ok", "hermes_binary": "...", "pid": 12345}
```

### GET /status
```json
{"status": "running", "pid": 12345}
```

### POST /chat
Request:
```json
{
  "prompt": "analyze this",
  "toolsets": "terminal,file,delegation",
  "timeout": 300,
  "workdir": "",
  "max_turns": 500
}
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `prompt` | yes | — | The prompt for the spawned Hermes session |
| `toolsets` | no | `terminal,file,delegation` | Comma-separated toolset names |
| `timeout` | no | `300` | Max seconds for the session |
| `workdir` | no | `""` | Working directory (cwd if empty) |
| `max_turns` | no | `500` | Max turns per spawned Hermes session |

Response (success):
```json
{
  "status": "ok",
  "response": "...",
  "duration_seconds": 8.2,
  "stderr": "",
  "exit_code": 0
}
```

Response (error):
```json
{
  "status": "error",
  "error": "Timeout after 300s",
  "duration_seconds": 300.0
}
```

## Self-Reference Mechanics

When a spawned session modifies the daemon's code:

1. Session edits `launch-loop.py` using `write_file`/`patch`
2. Session prints JSON with `need_reload` signal:
   ```json
   {"summary": "updated launch-loop.py", "next_goal": "NEXT_ITERATION need_reload"}
   ```
3. Daemon detects `need_reload` in the response
4. Daemon calls `os.execv()` to restart with updated code

This works in both embedded and external modes because the daemon always
receives the response JSON and can check for the signal.

## Pitfalls

1. **Embedded mode worker script must exist** — if
   `~/.hermes/plugins/hermes-mcp-worker/main.py` is missing, the daemon
   silently falls back to direct subprocess mode.
2. **Each `/chat` has startup overhead** — ~5-8s for `hermes chat -q`
   to load config/skills/plugins before processing the prompt.
3. **External worker ignores profile/model/provider** — it uses its own
   Hermes config. Run separate workers for different configs.
4. **Worker is stateless** — no session reuse between calls.
6. **`max_turns` now passed through** — v11.5.0 added `max_turns` to the
   worker request protocol. The default is 500, matching the daemon's default.
   Older workers (before this update) ignore the extra field and use their
   hardcoded default (previously 90). If you're running an external worker
   that hasn't been updated, spawned sessions may have lower turn budgets.
