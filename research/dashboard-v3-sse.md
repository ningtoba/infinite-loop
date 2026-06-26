# Dashboard v3 — Server-Sent Events (SSE) Design Document

**Target file:** `scripts/launch-loop.py` (v13.0.0, 6799 lines)  
**Author:** Infinite Loop Engineering  
**Status:** Research / Design  
**Date:** 2026-06-26

---

## 1. Motivation

The existing dashboard (`--status-html`) uses a static HTML file with `<meta http-equiv="refresh" content="30">` that the browser polls every 30 seconds. This is simple but wasteful (full page reload, no real-time updates, flashing UX). The daemon already has a persistent HTTP server (`WebhookHandler` running in a `ThreadedHTTPServer`) that could serve live data via Server-Sent Events (SSE) with zero additional dependencies.

---

## 2. Existing Architecture (Relevant Pieces)

### 2.1 WebhookHandler (`class WebhookHandler`, line 869)

- Extends `http.server.BaseHTTPRequestHandler`
- Class-level attributes: `_trigger_fn` (callable) and `_shutdown_sentinel` (sentinel path string)
- Serves on a configurable port via `ThreadedHTTPServer`
- Existing routes: `GET /health`, `GET /status`, `GET /api/status`, `POST /webhook`, `POST /control/{stop,pause,resume}`
- Uses `_send_json()` for JSON responses (line 979)

### 2.2 ThreadedHTTPServer (line 988)

```python
class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
```

- `daemon_threads = True` — handler threads are daemon threads; they die when the main thread exits.
- Each connection gets its own handler instance in its own thread.

### 2.3 run_loop() (line 4635)

- The main loop: for each iteration, it spawns sessions, merges results, writes the ledger, writes the HTML dashboard, and loops.
- After each iteration completes (around line 5188–5219):
  ```python
  write_ledger(state)                        # line 5188
  write_status_file(...)                     # line 5189
  if html_dashboard:
      _write_status_html(html_dashboard, state)  # line 5219
  ```
- The `state` dict is mutated in-place throughout the life of the loop.

### 2.4 State / Ledger

- `state` dict lives in the `run_loop()` stack frame.
- Written to disk via `write_ledger(state)` → `/tmp/infinite-loop-state.json`
- Read by `read_ledger()` (line 2110) using a file lock.

---

## 3. Design: Adding SSE to WebhookHandler

### 3.1 Overview

Two new routes:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /live` | GET | SSE stream: pushes `event: iteration` JSON events on each completion |
| `GET /dashboard` | GET | Serves the dashboard HTML page with embedded JavaScript that consumes `/live` |

The SSE stream must outlive any single request/response cycle — it is a long-lived HTTP connection. Each connected browser gets its own daemon thread (already the case thanks to `ThreadedHTTPServer` + `daemon_threads = True`).

### 3.2 The Notification Mechanism

**Problem:** The SSE handler thread lives in a different thread than `run_loop()`. When an iteration completes in `run_loop()`, we must notify **all currently connected SSE clients**.

**Recommended approach: A module-level `threading.Event` + `threading.Condition` + iteration data cache.**

```python
# Module-level globals (near line 869, before the class)
_sse_clients: list[queue.Queue] = []       # List of per-client queues
_sse_clients_lock = threading.Lock()       # Protects _sse_clients
_last_iteration_event: dict | None = None   # Cached last event data
```

**Flow:**

1. **SSE client connects** → `do_GET` for `/live` creates a `queue.Queue`, adds it to `_sse_clients` under the lock.
2. **run_loop() completes an iteration** → calls a helper `_broadcast_iteration(state)` which:
   - Builds a JSON payload (subset of `state` + the latest iteration record)
   - Under `_sse_clients_lock`: puts the JSON into every client queue
   - Removes any queue that raises `queue.Full` (client disconnected)
   - Also sets `_last_iteration_event`
3. **SSE handler thread** loops: blocks on `queue.get(timeout=30)`, sends `event: iteration\ndata: {json}\n\n` to `self.wfile`. Sends `event: heartbeat\ndata: {}\n\n` every 30 seconds if nothing arrives.
4. **Client disconnects** → `wfile.write()` raises `BrokenPipeError` / `ConnectionResetError` → handler exits, the thread dies, the queue is abandoned.

**Alternative considered — shared `_state_ref` + polling (rejected):**
Instead of push via queues, the SSE handler could poll `read_ledger()` every second. This works with zero changes to `run_loop()`, but wastes I/O (file lock contention, disk reads every second) and adds latency. The queue approach is more efficient and more responsive.

**Alternative considered — global `threading.Condition` (rejected):**
Could use a single `Condition` that `run_loop()` notifies and all SSE handlers wait on. However, this requires the SSE handlers to share a single `state` reference and all race to read it, which is more complex than per-client queues.

### 3.3 SSE Wire Format

Following the [SSE specification](https://html.spec.whatwg.org/multipage/server-sent-events.html):

```
event: iteration
data: {"iteration": 42, "status": "running", "total_iterations": 42, "success_count": 35, "error_count": 7, ...}

event: heartbeat
data: {}

```

- Each event is terminated by `\n\n`.
- `event:` field is optional but included for clarity.
- `data:` can be multiple lines (they are joined by `\n` in the browser), but our payloads are single-line JSON.
- Heartbeat events sent every ~30s to prevent proxies from closing idle connections (and to detect dead clients).

### 3.4 JSON Payload for `event: iteration`

The payload sent on each iteration should contain everything the dashboard needs to render without additional fetches:

```json
{
  "iteration": {
    "n": 42,
    "started_at": "2026-06-26T06:30:00",
    "duration_seconds": 127,
    "summary": "Fixed the widget alignment",
    "task_type": "coding",
    "error": null,
    "next_goal": null
  },
  "status": "running",
  "total_iterations": 42,
  "max_iterations": 100,
  "goal": "Build a web app",
  "evolved_goal": "",
  "started_at": "2026-06-25T12:00:00",
  "last_updated": "2026-06-26T06:32:07",
  "stats": {
    "success_count": 35,
    "error_count": 7,
    "total_duration_seconds": 4290,
    "avg_duration_seconds": 102
  },
  "consecutive_errors": 2,
  "consecutive_successes": 5,
  "cooldown": 15,
  "eta": {
    "remaining_seconds": 5916,
    "remaining_formatted": "1.6h"
  }
}
```

**Note:** We do **not** push the full iteration history (which could be thousands of entries). The initial page load can fetch history separately via `GET /api/status` (already exists). The SSE stream only pushes deltas — the latest iteration.

### 3.5 Pipeline Endpoint Security / CORS

The dashboard may be accessed from a different origin. Add CORS headers to the SSE endpoint:

```python
self.send_header("Access-Control-Allow-Origin", "*")
```

### 3.6 HTML Dashboard Page (`GET /dashboard`)

A new endpoint serving a self-contained HTML page. The page:

1. Calls `fetch('/api/status')` on load to get the complete state + history
2. Opens an `EventSource('/live')` for real-time updates
3. Renders the same visual cards / tables as the static dashboard but updates them in-place via DOM manipulation

Since this is a design doc, the full HTML template is not included here, but the key JavaScript pattern is:

```javascript
const evtSource = new EventSource('/live');

evtSource.addEventListener('iteration', (event) => {
    const data = JSON.parse(event.data);
    updateDashboard(data);
});

evtSource.addEventListener('heartbeat', () => {
    // Keep-alive, nothing to do
});

evtSource.onerror = (err) => {
    console.error('SSE error, reconnecting...', err);
    // EventSource auto-reconnects
};
```

### 3.7 Connection Lifecycle

| Phase | Behavior |
|-------|----------|
| Client opens `/live` | Handler creates a `queue.Queue`, adds to `_sse_clients`, sends initial headers (200, `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`), sends a current state snapshot as the first event. |
| Iteration completes in `run_loop()` | `_broadcast_iteration()` pushes JSON to all queues. |
| Data available on queue | Handler immediately writes `event: iteration\ndata: {json}\n\n` to `self.wfile` and flushes. |
| No data for 30s | Handler sends `event: heartbeat\ndata: {}\n\n` to keep the connection alive. |
| Client disconnects | `wfile.write()` raises exception → handler exits → thread dies → queue is abandoned (will be removed on next broadcast via `queue.Full` or on a separate cleanup path). |
| Server shutdown | Daemon threads die with the main process; SSE connections are aborted. |

### 3.8 Determining Client Disconnection

The `queue.Queue` approach uses a small `maxsize=1` (or uses `put_nowait`). When a client disconnects, its queue is never consumed. On the next broadcast, `put_nowait` raises `queue.Full`. We catch this and remove the queue:

```python
with _sse_clients_lock:
    alive = []
    for q in _sse_clients:
        try:
            q.put_nowait(payload)
            alive.append(q)
        except queue.Full:
            pass  # Client disconnected — drop queue
    _sse_clients = alive
```

Alternatively, use `queue.Queue()` (unbounded) and track last-read time, but the `Full` approach is simpler.

---

## 4. Changes Required in `launch-loop.py`

### 4.1 New Module-Level Globals (after imports, ~line 216)

```python
# SSE globals — thread-safe iteration broadcasting
_sse_clients: list[queue.Queue] = []
_sse_clients_lock = threading.Lock()
```

### 4.2 New Helper Functions (near `_write_status_html`, ~line 1922)

```python
def _broadcast_iteration(state: dict) -> None:
    """Push the latest iteration as an SSE event to all connected clients."""
    payload = _build_sse_payload(state)
    payload_json = json.dumps(payload, default=str)
    with _sse_clients_lock:
        alive = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload_json)
                alive.append(q)
            except queue.Full:
                pass  # Client disconnected
        _sse_clients = alive


def _build_sse_payload(state: dict) -> dict:
    """Build a compact JSON payload from the full ledger state for SSE push."""
    stats = state.get("stats", {})
    iterations = state.get("iterations", [])
    latest = iterations[-1] if iterations else {}
    return {
        "iteration": latest,
        "status": state.get("status", "unknown"),
        "total_iterations": state.get("total_iterations", 0),
        "max_iterations": state.get("max_iterations", 0),
        "goal": (state.get("initial_command") or "")[:80],
        "evolved_goal": state.get("evolved_goal", ""),
        "started_at": state.get("started_at", ""),
        "last_updated": state.get("last_updated", ""),
        "stats": {
            "success_count": stats.get("success_count", 0),
            "error_count": stats.get("error_count", 0),
            "total_duration_seconds": stats.get("total_duration_seconds", 0),
            "avg_duration_seconds": stats.get("avg_duration_seconds", 0),
        },
        "consecutive_errors": stats.get("consecutive_errors", 0),
        "consecutive_successes": state.get("consecutive_successes", 0),
        "cooldown": state.get("cooldown", 0),
        "eta": state.get("eta", {}),
    }
```

### 4.3 New SSE Handler Methods on `WebhookHandler` (in `do_GET`, ~line 890)

Extend the `do_GET` dispatch:

```python
elif parsed.path == "/dashboard":
    self._serve_dashboard_html()
elif parsed.path == "/live":
    self._handle_sse()
```

### 4.4 `_handle_sse()` Method (new)

```python
def _handle_sse(self):
    """Handle GET /live — Server-Sent Events stream."""
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
    self.send_header("Connection", "keep-alive")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("X-Accel-Buffering", "no")  # Disable nginx buffering if proxied
    self.end_headers()

    q: queue.Queue = queue.Queue(maxsize=1)
    with _sse_clients_lock:
        _sse_clients.append(q)

    try:
        while True:
            try:
                data = q.get(timeout=30)
                self.wfile.write(f"event: iteration\ndata: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
            except queue.Empty:
                self.wfile.write(b"event: heartbeat\ndata: {}\n\n")
                self.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass  # Client disconnected
    finally:
        with _sse_clients_lock:
            try:
                _sse_clients.remove(q)
            except ValueError:
                pass
```

### 4.5 `_serve_dashboard_html()` Method (new)

```python
def _serve_dashboard_html(self):
    """Serve the SSE-powered dashboard HTML page."""
    html = _generate_sse_dashboard_html()
    body = html.encode("utf-8")
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)
```

### 4.6 Dashboard HTML Template (new constant, near `_STATUS_HTML_TPL`)

This is a new template — `_SSE_DASHBOARD_HTML_TPL` — that produces a live-updating dashboard using the same CSS as `_STATUS_HTML_TPL` but with JavaScript that:

1. Fetches `GET /api/status` on load for initial state
2. Opens `EventSource('/live')` for real-time updates
3. Updates DOM elements in-place instead of reloading the page

The HTML template should be self-contained (inline CSS + JS, same as the static version).

### 4.7 Insert Broadcast Call in `run_loop()` (line ~5219)

After the HTML dashboard write, add:

```python
# Broadcast iteration state to SSE clients
_broadcast_iteration(state)
```

This goes right after line 5219 (`_write_status_html(...)`) so the SSE event fires at the same logical point as the static HTML update.

### 4.8 New import

Add `import queue` to the imports section (line ~190–215).

---

## 5. Thread Safety Analysis

| Shared data | Protected by | Access pattern |
|---|---|---|
| `_sse_clients` (list of Queues) | `_sse_clients_lock` (RLock) | Short-lived: append during do_GET, remove during broadcast or disconnect |
| `queue.Queue` objects | Per-queue internal lock | `put_nowait` from broadcast thread, `get` from SSE handler thread. Standard thread-safe. |
| `state` dict in `run_loop()` | Not shared directly — only read by `_broadcast_iteration()` from the same thread that holds `state` | Single-threaded access; no lock needed |
| `self.wfile` (the socket) | Per-connection / per-thread | Only accessed by one SSE handler thread |

**No shared mutable state is accessed concurrently without locking.** The per-client queue is the synchronization point.

---

## 6. Edge Cases

| Scenario | Behavior |
|----------|----------|
| No SSE clients connected | `_broadcast_iteration` iterates empty list — cheap no-op. |
| 100 clients connected | Each client has its own thread and queue. Sending to 100 queues is O(n) but each `put_nowait` is just a memory copy of the JSON string. Acceptable for typical usage; if needed, cap max clients. |
| Client with slow network | Queue has `maxsize=1`, so `put_nowait` will raise `Full` if the client's thread hasn't consumed the previous event. We drop that client. This is intentional — slow clients get booted. |
| `run_loop()` spins very fast | If iterations complete faster than SSE clients can consume, slow clients drop. The broadcast to responsive clients is synchronous inside `run_loop()` — if `run_loop()` is latency-sensitive, consider offloading broadcast to a thread. |
| Multiple daemon instances | `_sse_clients` is process-local, so there's no cross-process confusion. Each daemon serves its own clients. |
| Reverse proxy (nginx) buffering | The `X-Accel-Buffering: no` header and `Cache-Control: no-cache` instruct nginx not to buffer the SSE stream. |

---

## 7. Migration / Coexistence with v2

The static HTML dashboard (`--status-html`) and the SSE dashboard (`--sse-dashboard`) are **independent features** that can coexist:

- `--status-html` continues to write the static HTML file on each iteration (no change).
- `--sse-dashboard` enables the SSE endpoints (`/live` and `/dashboard`) on the webhook server.
- Both can be enabled simultaneously.
- The webhook server must be running for SSE to work (since the endpoints live on it). If `--webhook-port=0`, the SSE dashboard is unavailable.

Suggested CLI flag: `--sse-dashboard`

---

## 8. Files Changed Summary

| File | Change |
|------|--------|
| `scripts/launch-loop.py` | Add `import queue` |
| `scripts/launch-loop.py` | Add module-level `_sse_clients`, `_sse_clients_lock` |
| `scripts/launch-loop.py` | Add `_broadcast_iteration()`, `_build_sse_payload()` helpers |
| `scripts/launch-loop.py` | Add `_SSE_DASHBOARD_HTML_TPL` template constant |
| `scripts/launch-loop.py` | Extend `WebhookHandler.do_GET()` with `/live` and `/dashboard` routes |
| `scripts/launch-loop.py` | Add `WebhookHandler._handle_sse()` method |
| `scripts/launch-loop.py` | Add `WebhookHandler._serve_dashboard_html()` method |
| `scripts/launch-loop.py` | Add `_broadcast_iteration(state)` call in `run_loop()` after line 5219 |
| `scripts/launch-loop.py` | Add `--sse-dashboard` CLI arg to argparse |

No new files. No external dependencies.

---

## 9. Appendix: Full SSE Handler Pseudocode

```
do_GET:
  if path == "/live":
      _handle_sse()
  elif path == "/dashboard":
      _serve_dashboard_html()
  ...

_handle_sse():
  send 200 + SSE headers
  q = Queue(maxsize=1)
  lock: _sse_clients.append(q)
  try:
      while True:
          try:
              data = q.get(timeout=30)
              write "event: iteration\ndata: {data}\n\n"
          except Empty:
              write "event: heartbeat\ndata: {}\n\n"
          flush
  except (BrokenPipeError, ConnectionResetError):
      pass
  finally:
      lock: _sse_clients.remove(q)

_broadcast_iteration(state):
  payload = build_sse_payload(state)
  lock:
      alive = []
      for q in _sse_clients:
          try:
              q.put_nowait(payload)
              alive.append(q)
          except Full:
              pass  # dead client
      _sse_clients = alive
```

---

## 10. Appendix: Dashboard HTML Template Outline

The SSE dashboard HTML template (`_SSE_DASHBOARD_HTML_TPL`) should be a self-contained page with:

- **Same CSS** as the v2 static dashboard (dark/light theme, cards, table, status badges)
- **No `<meta http-equiv="refresh">`** — replaced by JavaScript
- **On load**: `fetch('/api/status').then(r => r.json()).then(render)`
- **EventSource('/live')**: `addEventListener('iteration', updateDash)`
- **render(data)**: Updates meta cards, stats grid, iteration table (prepend row), progress bar, ETA, status badge — all in-place via `innerHTML` or `textContent`
- **Reconnection**: `EventSource` auto-reconnects on error; the page re-renders with the latest data on the next event
- **Compact mode**: Preserved from v2
