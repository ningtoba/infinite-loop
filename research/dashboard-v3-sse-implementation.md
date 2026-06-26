# Dashboard v3 (SSE Real-Time Updates) — Implementation Plan

**Target:** `scripts/launch-loop.py` (v13.0.0, 6799 lines)
**Date:** 2026-06-26
**Status:** Implementation Plan (Ready for patching)

---

## 1. Summary of Changes

Seven atomic edits to `scripts/launch-loop.py`:

| # | Location | Change |
|---|----------|--------|
| 1 | Imports (line ~213) | Add `import queue` |
| 2 | Module globals (line ~232) | Add `_sse_clients` and `_sse_clients_lock` |
| 3 | After `_STATUS_HTML_TPL` (line 1774) | Add `_SSE_DASHBOARD_HTML_TPL` constant |
| 4 | After `_write_status_html()` (line 1931) | Add `_broadcast_to_sse_clients()` and `_build_sse_payload()` |
| 5 | `do_GET` method (line 890–920) | Add `/live` and `/dashboard` route handlers |
| 6 | Before `_send_json` (line ~976) | Add `_handle_sse()` and `_serve_dashboard_html()` |
| 7 | `run_loop()` after `_handle_callbacks` (line ~5228) | Add `_broadcast_to_sse_clients(state)` |

No new files. No external dependencies. Stdlib only.

---

## 2. Architecture (Reference)

### 2.1 Data Flow

```
run_loop()                          WebhookHandler (per-client thread)
   │                                       │
   ├─ _build_iteration_record()            │
   ├─ write_ledger(state)                  │
   ├─ _write_status_html(...)              │
   ├─ _handle_callbacks(...)               │
   └─ NEW: _broadcast_to_sse_clients(state)│
         │                                 │
         ├─ _build_sse_payload(state)      │
         └─ for each q in _sse_clients:    │
              q.put_nowait(json)           │
                                           │
                                     do_GET("/live"):
                                       q = Queue(maxsize=1)
                                       add to _sse_clients
                                       loop:
                                         data = q.get(timeout=30)
                                         wfile.write("event: iteration\ndata: ...\n\n")
```

### 2.2 Thread Safety

| Shared data | Protected by | Access pattern |
|---|---|---|
| `_sse_clients` (list of Queues) | `_sse_clients_lock` | Append during do_GET; remove during broadcast or client disconnect |
| `queue.Queue` objects | Per-queue internal lock | `put_nowait` from broadcast thread, `get` from SSE handler thread |
| `state` dict in `run_loop()` | Not shared — only read by `_broadcast_to_sse_clients()` from the loop's own thread | Single-threaded access |
| `self.wfile` (socket) | Per-connection / per-thread | Only accessed by one SSE handler thread |

### 2.3 Client Disconnection Detection

The `Queue(maxsize=1)` provides natural dead-client detection:
1. SSE handler loop: `q.get(timeout=30)` blocks waiting for data
2. Data arrives: `q.put_nowait(payload)` from broadcast thread
3. Client disconnects: SSE handler's `wfile.write()` raises `BrokenPipeError` or `ConnectionResetError`
4. `finally` block: removes queue from `_sse_clients` under lock
5. Stale queue (client died without clean disconnect): next broadcast's `put_nowait` raises `queue.Full` → queue is discarded

### 2.4 Heartbeat

Every 30 seconds with no data, the SSE handler sends `event: heartbeat\ndata: {}\n\n` to prevent proxies from closing idle connections.

---

## 3. Exact Patches for `launch-loop.py`

### Patch 1 — Add `import queue`

**old_string (lines ~210-214):**
```
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
```

**new_string:**
```
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
```

---

### Patch 2 — Add Module-Level SSE Globals

**Location:** After `_shutdown_state_ref` (end of the ~line 232-234 grouping).

**old_string:**
```
_shutdown_state_ref: dict | None = None


```

**new_string:**
```
_shutdown_state_ref: dict | None = None

# SSE (Server-Sent Events) client tracking for live dashboard
_sse_clients: list[queue.Queue] = []
_sse_clients_lock = threading.Lock()


```

---

### Patch 3 — Add `_SSE_DASHBOARD_HTML_TPL` After `_STATUS_HTML_TPL`

**Location:** Right after the closing `"""` of `_STATUS_HTML_TPL` (line 1774) and before the blank-line + `def _generate_status_html`.

**old_string:**
```
</body></html>"""


def _generate_status_html(state: dict, compact: bool = False) -> str:
```

**new_string:**
```
</body></html>"""

# SSE-powered live dashboard HTML template (no meta-refresh, uses EventSource)
_SSE_DASHBOARD_HTML_TPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Infinite Loop Dashboard (Live)</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%99%BE%EF%B8%8F%3C/text%3E%3C/svg%3E">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root { --bg: #0d1117; --fg: #c9d1d9; --card-bg: #161b22; --border: #30363d; --border-row: #21262d; --accent: #58a6ff; --muted: #8b949e; --dim: #484f58; --err-bg: rgba(218, 54, 51, 0.1); }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --fg: #24292f; --card-bg: #ffffff; --border: #d0d7de; --border-row: #e1e4e8; --accent: #0969da; --muted: #656d76; --dim: #8b949e; --err-bg: rgba(218, 54, 51, 0.05); }
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--fg); padding: 20px; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; color: var(--accent); }
  h2 { font-size: 1.1rem; margin: 1.5rem 0 0.5rem; color: var(--muted); }
  .meta { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .meta-item { background: var(--card-bg); padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; }
  .meta-item .label { color: var(--muted); }
  .meta-item .value { color: var(--fg); font-weight: 600; }
  #status-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
  .running { background: #1f6feb; color: #fff; }
  .stopped { background: #da3633; color: #fff; }
  .paused { background: #d29922; color: #000; }
  .reloading { background: #da3633; color: #fff; }
  .no_ledger { background: var(--dim); color: #fff; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); color: var(--muted); text-transform: uppercase; font-size: 0.75rem; }
  td { padding: 8px 6px; border-bottom: 1px solid var(--border-row); }
  .error-row td { background: var(--err-bg); }
  .summary { max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
  .tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; }
  .tag-ok { background: #1a3a1a; color: #3fb950; }
  .tag-err { background: #3a1a1a; color: #f85149; }
  .tag-evolve { background: #1a1a3a; color: #58a6ff; }
  .progress { height: 8px; background: var(--border); border-radius: 4px; margin: 8px 0; }
  .progress-fill { height: 8px; background: #1f6feb; border-radius: 4px; transition: width 0.3s; }
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .stat-card { background: var(--card-bg); padding: 12px; border-radius: 6px; text-align: center; }
  .stat-card .num { font-size: 1.5rem; font-weight: 700; color: var(--accent); }
  .stat-card .label { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
  #cooldown-display { font-size: 0.85rem; }
  .cooldown-active { color: #d29922; }
  .cooldown-idle { color: var(--muted); }
  .compact-toggle { float: right; font-size: 0.75rem; color: var(--accent); cursor: pointer; text-decoration: underline; margin-top: 1.5rem; }
  .compact-mode .meta, .compact-mode .stats-grid, .compact-mode h2, .compact-mode .progress, .compact-mode .cooldown-row, .compact-mode #iterations-table { display: none; }
  .compact-mode #summary-only { display: block; }
  #summary-only { display: none; }
  #connection-status { font-size: 0.75rem; color: var(--muted); float: right; }
  .connected { color: #3fb950; }
  .disconnected { color: #f85149; }
</style>
</head>
<body>
<h1>&#x267B;&#xFE0F; Infinite Loop <span id="connection-status" class="disconnected">&#x25CF; disconnected</span></h1>
<div class="meta" id="meta-cards">
  <div class="meta-item"><span class="label">Status</span><br><span id="status-badge" class="running">loading...</span></div>
  <div class="meta-item"><span class="label">Total Iterations</span><br><span class="value" id="total-iterations">-</span></div>
  <div class="meta-item"><span class="label">Goal</span><br><span class="value" id="goal">-</span></div>
  <div class="meta-item"><span class="label">Evolved Goal</span><br><span class="value" id="evolved-goal">-</span></div>
  <div class="meta-item"><span class="label">Started At</span><br><span class="value" id="started-at">-</span></div>
  <div class="meta-item"><span class="label">Last Updated</span><br><span class="value" id="last-updated">-</span></div>
</div>

<div class="stats-grid" id="stats-grid">
  <div class="stat-card"><div class="num" id="stat-success">-</div><div class="label">Success</div></div>
  <div class="stat-card"><div class="num" id="stat-error">-</div><div class="label">Errors</div></div>
  <div class="stat-card"><div class="num" id="stat-avg-duration">-</div><div class="label">Avg Duration</div></div>
  <div class="stat-card"><div class="num" id="stat-consec-errors">-</div><div class="label">Consec Errors</div></div>
  <div class="stat-card"><div class="num" id="stat-eta">-</div><div class="label">ETA</div></div>
</div>

<div id="cooldown-display" class="cooldown-idle">Cooldown: idle</div>

<h2>Progress</h2>
<div class="progress" id="progress-bar"><div class="progress-fill" id="progress-fill" style="width:0%"></div></div>

<h2>Latest Iteration <span class="compact-toggle" id="compact-toggle" onclick="toggleCompact()">[compact]</span></h2>
<div id="summary-only"></div>
<table id="iterations-table">
<thead><tr><th>#</th><th>Type</th><th>Duration</th><th>Summary</th><th>Classification</th><th>Error</th></tr></thead>
<tbody id="iterations-body"></tbody>
</table>

<p style="margin-top:1rem;font-size:0.75rem;color:var(--muted);">
  Live updates via SSE &mdash;
  <a href="/api/status" target="_blank" style="color:var(--accent);">JSON API</a> &middot;
  <a href="/status" target="_blank" style="color:var(--accent);">Simple Status</a> &middot;
  <a href="/health" target="_blank" style="color:var(--accent);">Health</a>
</p>

<script>
var compact = false;
function toggleCompact() {
    compact = !compact;
    document.body.classList.toggle('compact-mode', compact);
    document.getElementById('compact-toggle').textContent = compact ? '[expand]' : '[compact]';
}
function updateBadge(status) {
    var badge = document.getElementById('status-badge');
    badge.textContent = status;
    badge.className = '';
    if (status === 'running') badge.classList.add('running');
    else if (status === 'stopped') badge.classList.add('stopped');
    else if (status === 'paused') badge.classList.add('paused');
    else if (status === 'reloading') badge.classList.add('reloading');
    else badge.classList.add('no_ledger');
}
function updateMeta(data) {
    document.getElementById('total-iterations').textContent = data.total_iterations != null ? data.total_iterations : '-';
    document.getElementById('goal').textContent = data.goal || '-';
    document.getElementById('evolved-goal').textContent = data.evolved_goal || '-';
    document.getElementById('started-at').textContent = data.started_at || '-';
    document.getElementById('last-updated').textContent = data.last_updated || '-';
    updateBadge(data.status || 'unknown');
}
function updateStats(data) {
    var s = data.stats || {};
    document.getElementById('stat-success').textContent = s.success_count != null ? s.success_count : '-';
    document.getElementById('stat-error').textContent = s.error_count != null ? s.error_count : '-';
    document.getElementById('stat-avg-duration').textContent = s.avg_duration_seconds != null ? s.avg_duration_seconds + 's' : '-';
    document.getElementById('stat-consec-errors').textContent = data.consecutive_errors != null ? data.consecutive_errors : '-';
    var eta = data.eta || {};
    document.getElementById('stat-eta').textContent = eta.remaining_formatted || '-';
}
function updateProgress(data) {
    var maxIt = data.max_iterations;
    var curIt = data.total_iterations;
    if (maxIt > 0) {
        var pct = Math.min(100.0 * curIt / maxIt, 100.0);
        document.getElementById('progress-fill').style.width = pct + '%';
    } else {
        document.getElementById('progress-fill').style.width = '0%';
    }
}
function updateCooldown(data) {
    var cd = document.getElementById('cooldown-display');
    var seconds = data.cooldown;
    if (seconds > 0) {
        cd.textContent = 'Cooldown: ' + seconds + 's';
        cd.className = 'cooldown-active';
    } else {
        cd.textContent = 'Cooldown: idle';
        cd.className = 'cooldown-idle';
    }
}
function addIterationRow(iter) {
    if (!iter || !iter.n) return;
    var tbody = document.getElementById('iterations-body');
    var tr = document.createElement('tr');
    if (iter.error && iter.error !== 'none' && iter.error !== '') {
        tr.className = 'error-row';
    }
    var typeTag = '';
    if (iter.task_type) {
        var cls = iter.task_type === 'error' ? 'tag-err' : 'tag-ok';
        typeTag = '<span class="tag ' + cls + '">' + iter.task_type + '</span>';
    }
    var classifyTag = '';
    if (iter.classification) {
        var cCls = 'tag-ok';
        if (iter.classification === 'stuck' || iter.classification === 'regression') cCls = 'tag-err';
        else if (iter.classification === 'partial') cCls = 'tag-evolve';
        classifyTag = '<span class="tag ' + cCls + '">' + iter.classification + '</span>';
    }
    var summary = iter.summary || iter.next_goal || '';
    var safeSummary = summary.replace(/"/g, '&quot;');
    var error = iter.error && iter.error !== 'none' ? iter.error.substring(0, 60) + '...' : '';
    tr.innerHTML = '<td>' + iter.n + '</td><td>' + typeTag + '</td><td>' + (iter.duration_seconds != null ? iter.duration_seconds + 's' : '-') + '</td><td class="summary" title="' + safeSummary + '">' + summary.substring(0, 80) + '</td><td>' + classifyTag + '</td><td>' + error + '</td>';
    tbody.insertBefore(tr, tbody.firstChild);
    while (tbody.children.length > 100) {
        tbody.removeChild(tbody.lastChild);
    }
}
function renderDashboard(data) {
    if (!data) return;
    updateMeta(data);
    updateStats(data);
    updateProgress(data);
    updateCooldown(data);
    if (data.iteration && data.iteration.n) {
        addIterationRow(data.iteration);
    }
}
// Initial load: fetch full state from /api/status
fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (fullState) {
        var s = fullState.stats || {};
        var iters = fullState.iterations || [];
        var latest = iters.length > 0 ? iters[iters.length - 1] : {};
        var renderData = {
            iteration: latest,
            status: fullState.status || 'unknown',
            total_iterations: fullState.total_iterations || 0,
            max_iterations: fullState.max_iterations || 0,
            goal: (fullState.initial_command || '') || '-',
            evolved_goal: fullState.evolved_goal || '',
            started_at: fullState.started_at || '',
            last_updated: fullState.last_updated || '',
            stats: {
                success_count: s.success_count,
                error_count: s.error_count,
                total_duration_seconds: s.total_duration_seconds,
                avg_duration_seconds: s.avg_duration_seconds
            },
            consecutive_errors: s.consecutive_errors || 0,
            consecutive_successes: fullState.consecutive_successes || 0,
            cooldown: fullState.cooldown || 0,
            eta: fullState.eta || {}
        };
        renderDashboard(renderData);
        iters.forEach(function(it) {
            if (it.n) addIterationRow(it);
        });
    })
    .catch(function (err) {
        console.error('Initial fetch failed:', err);
        document.getElementById('connection-status').textContent = '\\u25CF fetch error';
        document.getElementById('connection-status').className = 'disconnected';
    });
// Open SSE connection
var evtSource = new EventSource('/live');
evtSource.addEventListener('iteration', function (event) {
    try {
        var data = JSON.parse(event.data);
        renderDashboard(data);
    } catch (e) {
        console.error('SSE parse error:', e);
    }
});
evtSource.addEventListener('heartbeat', function () {});
evtSource.onopen = function () {
    document.getElementById('connection-status').textContent = '\\u25CF connected';
    document.getElementById('connection-status').className = 'connected';
};
evtSource.onerror = function (err) {
    console.error('SSE error, reconnecting...', err);
    document.getElementById('connection-status').textContent = '\\u25CF disconnected (reconnecting...)';
    document.getElementById('connection-status').className = 'disconnected';
};
</script>
</body>
</html>"""


def _generate_status_html(state: dict, compact: bool = False) -> str:
```

> **IMPORTANT:** The `innerHTML` calls in `addIterationRow()` are safe here because we control all the data sources — `iter.n` is a number, `iter.task_type`, `iter.classification` are enum-like strings from `_build_iteration_record()`, and `summary` is truncated to 80 chars. XSS via the spawned Hermes session's output is theoretically possible but would already be an attack on the ledger itself. This matches the existing v2 dashboard's approach.

---

### Patch 4 — Add Broadcast Functions After `_write_status_html()`

**Location:** After `_write_status_html()` (line 1931) and before `def write_status_file`.

**old_string:**
```
        _log(f"[HTML-DASH] Failed to write status page {html_path}: {e}")


def write_status_file(
```

**new_string:**
```
        _log(f"[HTML-DASH] Failed to write status page {html_path}: {e}")


# ---------------------------------------------------------------------------
# SSE broadcast helpers
# ---------------------------------------------------------------------------


def _broadcast_to_sse_clients(state: dict) -> None:
    """Push the latest iteration state as an SSE event to all connected clients.

    Called from run_loop() after each iteration completes.
    Iterates the module-level _sse_clients list under lock and drops
    any queue whose put_nowait() raises queue.Full (dead client).
    """
    payload = _build_sse_payload(state)
    payload_json = json.dumps(payload, default=str)
    with _sse_clients_lock:
        alive = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload_json)
                alive.append(q)
            except queue.Full:
                pass  # Client disconnected or too slow — drop
        _sse_clients = alive


def _build_sse_payload(state: dict) -> dict:
    """Build a compact JSON payload from the full ledger state for SSE push.

    The payload contains everything the live dashboard needs to render
    without additional fetches: the latest iteration record, top-level
    status fields, aggregated stats, and ETA.
    """
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


def write_status_file(
```

---

### Patch 5 — Extend `do_GET` Routing

**Location:** Inside `do_GET` (~line 918), replace the `else` fallthrough.

**old_string:**
```
        else:
            self._send_json(404, {"error": "not_found"})
```

**new_string:**
```
        elif parsed.path == "/live":
            self._handle_sse()
        elif parsed.path == "/dashboard":
            self._serve_dashboard_html()
        else:
            self._send_json(404, {"error": "not_found"})
```

---

### Patch 6 — Add `_handle_sse()` and `_serve_dashboard_html()` Methods

**Location:** Before `_send_json()` (line ~979).

**old_string:**
```
    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
```

**new_string:**
```
    def _handle_sse(self):
        """Handle GET /live — Server-Sent Events stream.

        Creates a per-client Queue(maxsize=1), registers it in the module-level
        _sse_clients list, then enters a blocking loop:
          - q.get(timeout=30) → sends 'event: iteration' with JSON payload
          - queue.Empty after 30s → sends 'event: heartbeat' keepalive
        On client disconnect (BrokenPipeError / ConnectionResetError), removes
        the queue from _sse_clients in a finally block.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Accel-Buffering", "no")
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
            pass  # Client disconnected — thread will die
        finally:
            with _sse_clients_lock:
                try:
                    _sse_clients.remove(q)
                except ValueError:
                    pass

    def _serve_dashboard_html(self):
        """Serve the SSE-powered live dashboard HTML page."""
        html = _SSE_DASHBOARD_HTML_TPL
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
```

---

### Patch 7 — Add Broadcast Call in `run_loop()`

**Location:** After `_handle_callbacks(...)` (~line 5228), before the loop's closing indentation.

**old_string:**
```
        # --- HTTP / Notification / Error callbacks ---
        _handle_callbacks(
            http_callback=http_callback,
            record=record,
            notify_cmd=notify_cmd,
            on_error_cmd=on_error_cmd,
            combined_error=combined_error,
        )


```

**new_string:**
```
        # --- HTTP / Notification / Error callbacks ---
        _handle_callbacks(
            http_callback=http_callback,
            record=record,
            notify_cmd=notify_cmd,
            on_error_cmd=on_error_cmd,
            combined_error=combined_error,
        )

        # Broadcast iteration state to SSE live dashboard clients
        _broadcast_to_sse_clients(state)


```

---

## 4. Verification Checklist

After applying all patches, verify:

1. `python3 -c "import py_compile; py_compile.compile('scripts/launch-loop.py', doraise=True)"` — no syntax errors
2. `grep -n "import queue" scripts/launch-loop.py` — shows `queue` imported
3. `grep -n "_sse_clients" scripts/launch-loop.py` — shows globals defined
4. `grep -n "_SSE_DASHBOARD_HTML_TPL" scripts/launch-loop.py` — shows template constant
5. `grep -n "_broadcast_to_sse_clients" scripts/launch-loop.py` — shows 2 occurrences (def + call)
6. `grep -n "_build_sse_payload" scripts/launch-loop.py` — shows 2 occurrences (def + call)
7. `grep -n "_handle_sse\|_serve_dashboard_html" scripts/launch-loop.py` — shows 3 occurrences each (def + call)
8. Dashboard loads at `http://localhost:<port>/dashboard` without errors
9. `curl -N http://localhost:<port>/live` shows SSE events on each iteration

---

## 5. Optional Enhancements (Not Included)

These are not part of the current plan but could be added later:

- **`--sse-dashboard` CLI flag** to enable/disable SSE endpoints independently of webhook server
- **Rate-limited broadcast** — if `run_loop()` iterations complete faster than SSE clients can consume, consider offloading broadcast to a background thread with a bounded queue
- **Max clients cap** — e.g. `if len(_sse_clients) >= 50: return 503` to prevent resource exhaustion
- **Compression** — the SSE stream is not compressed; for very large payloads, consider gzip or trimming the iteration record
