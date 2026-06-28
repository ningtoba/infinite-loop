"""Webhook server — lightweight HTTP server that triggers iterations."""

import http.server
import json
import os
import queue
import socketserver
import threading
import urllib.parse

from .file_utils import _log, read_ledger
from .dashboard import (
    _sse_clients,
    _sse_clients_lock,
    _build_sse_payload,
    _SSE_DASHBOARD_HTML_TPL,
)
from .goal_utils import _goal_hash
from datetime import datetime, timezone


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    """Accepts POST /webhook to trigger the next iteration.

    Optional JSON body: {"goal": "override goal", "context": "override context"}
    Returns 200 with iteration state JSON on success.

    GET /status returns the current iteration state.
    GET /api/status returns the COMPLETE iteration state from the ledger (full dict).
    GET /health returns 200 when the daemon is running.

    POST /control/stop  writes "stop" to the shutdown sentinel file.
    POST /control/pause writes "pause" to the shutdown sentinel file.
    POST /control/resume deletes the shutdown sentinel file (or writes "resume").
    """

    _trigger_fn = None  # Callback set by the daemon
    _shutdown_sentinel = ""  # Path to sentinel file, set by the daemon

    def log_message(self, format, *args):
        _log(f"[WEBHOOK] {self.client_address[0]} - {format % args}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                200,
                {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()},
            )
        elif parsed.path == "/status":
            state = read_ledger()
            if state:
                stats = state.get("stats", {})
                self._send_json(
                    200,
                    {
                        "status": state.get("status", "unknown"),
                        "total_iterations": state.get("total_iterations", 0),
                        "success_count": stats.get("success_count", 0),
                        "error_count": stats.get("error_count", 0),
                        "last_updated": state.get("last_updated"),
                    },
                )
            else:
                self._send_json(200, {"status": "no_ledger"})
        elif parsed.path == "/api/status":
            state = read_ledger()
            if state:
                stats = state.get("stats", {})
                iterations = state.get("iterations", [])
                total_iters = state.get("total_iterations", 0)
                latest = iterations[-1] if iterations else {}
                et = state.get("error_type_counts", {})
                goals_specs = state.get("goals_specs", [])
                goals_completed = state.get("goals_completed", {})
                goals_list = []
                for idx, spec in enumerate(goals_specs):
                    gtext = spec[0] if isinstance(spec, (tuple, list)) else spec
                    gh = _goal_hash(gtext) if gtext else ""
                    done = (
                        gh in goals_completed
                        and goals_completed[gh].get("status") == "completed"
                    )
                    active = False
                    if state.get("goal_index") is not None:
                        active = idx == state["goal_index"]
                    goals_list.append(
                        {"text": gtext[:100], "done": done, "active": active}
                    )
                # Compute throughput metrics from available iteration data
                # (same logic as _build_sse_payload in dashboard.py)
                avg_chars_per_iter = None
                avg_throughput = None
                if iterations:
                    chars_list = [it.get("output_chars", 0) or 0 for it in iterations]
                    if chars_list:
                        avg_chars_per_iter = int(sum(chars_list) // len(chars_list))
                    cps_list = [
                        it.get("chars_per_second", 0) or 0
                        for it in iterations
                        if it.get("chars_per_second", 0)
                    ]
                    if cps_list:
                        avg_throughput = round(sum(cps_list) / len(cps_list), 1)
                metrics_summary_parts = []
                if avg_chars_per_iter:
                    metrics_summary_parts.append(f"{avg_chars_per_iter} chars/iter")
                if avg_throughput:
                    metrics_summary_parts.append(f"{avg_throughput} cps avg")
                if stats.get("avg_duration_seconds", 0):
                    metrics_summary_parts.append(
                        f'{stats["avg_duration_seconds"]:.0f}s avg'
                    )
                metrics_summary = (
                    ", ".join(metrics_summary_parts) if metrics_summary_parts else ""
                )
                iters_per_goal = None
                if goals_list and total_iters > 0:
                    iters_per_goal = max(1, total_iters // max(len(goals_list), 1))

                self._send_json(
                    200,
                    {
                        "loop_status": state.get("status", "unknown"),
                        "ledger": {
                            "status": state.get("status", "unknown"),
                            "total_iterations": state.get("total_iterations", 0),
                            "max_iterations": state.get("max_iterations", 0),
                            "goal": (state.get("initial_command") or "")[:80],
                            "evolved_goal": state.get("evolved_goal", ""),
                            "started_at": state.get("started_at", ""),
                            "last_updated": state.get("last_updated", ""),
                            "cooldown": state.get("cooldown", 0),
                        },
                        "latest_iteration": latest,
                        "stats": {
                            "success_count": stats.get("success_count", 0),
                            "error_count": stats.get("error_count", 0),
                            "total_duration_seconds": stats.get(
                                "total_duration_seconds", 0
                            ),
                            "avg_duration_seconds": stats.get(
                                "avg_duration_seconds", 0
                            ),
                            "consecutive_errors": stats.get("consecutive_errors", 0),
                            "consecutive_successes": stats.get(
                                "consecutive_successes", 0
                            ),
                        },
                        "error_counts": {
                            "timeout": et.get("timeout", 0),
                            "network": et.get("network", 0),
                            "schema": et.get("schema", 0),
                            "heartbeat": et.get("heartbeat", 0),
                            "unknown": et.get("unknown", 0),
                        },
                        "mitigations": state.get("mitigations", {}),
                        "eta": state.get("eta", {}),
                        "goals": goals_list,
                        "avg_chars_per_iter": avg_chars_per_iter,
                        "avg_throughput": avg_throughput,
                        "est_cost": state.get("est_cost"),
                        "iters_per_goal": iters_per_goal,
                        "metrics_summary": metrics_summary,
                        "consecutive_errors": stats.get("consecutive_errors", 0),
                        "consecutive_successes": stats.get("consecutive_successes", 0),
                        "cooldown": state.get("cooldown", 0),
                        "iteration": latest,
                    },
                )
            else:
                self._send_json(
                    200,
                    {
                        "loop_status": "no_ledger",
                        "ledger": {"status": "no_ledger"},
                        "stats": {},
                        "error_counts": {},
                        "mitigations": {},
                        "goals": [],
                    },
                )
        elif parsed.path == "/live":
            self._handle_sse()
        elif parsed.path == "/dashboard":
            self._serve_dashboard_html()
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/webhook":
            content_length = int(self.headers.get("Content-Length", 0))
            payload = {}
            if content_length > 0:
                try:
                    body = self.rfile.read(content_length).decode("utf-8")
                    payload = json.loads(body) if body.strip() else {}
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    self._send_json(400, {"error": f"invalid JSON: {e}"})
                    return

            trigger_fn = WebhookHandler._trigger_fn
            if trigger_fn:
                goal = payload.get("goal")
                context = payload.get("context")
                result = trigger_fn(goal=goal, context=context)
                self._send_json(200, {"triggered": True, "result": result})
            else:
                self._send_json(503, {"error": "trigger function not set"})
        elif parsed.path == "/control/stop":
            sentinel = WebhookHandler._shutdown_sentinel
            if not sentinel:
                self._send_json(503, {"error": "sentinel path not configured"})
                return
            try:
                with open(sentinel, "w") as f:
                    f.write("stop")
                self._send_json(200, {"action": "stop", "status": "sentinel_written"})
            except OSError as e:
                self._send_json(500, {"error": f"failed to write sentinel: {e}"})
        elif parsed.path == "/control/pause":
            sentinel = WebhookHandler._shutdown_sentinel
            if not sentinel:
                self._send_json(503, {"error": "sentinel path not configured"})
                return
            try:
                with open(sentinel, "w") as f:
                    f.write("pause")
                self._send_json(200, {"action": "pause", "status": "sentinel_written"})
            except OSError as e:
                self._send_json(500, {"error": f"failed to write sentinel: {e}"})
        elif parsed.path == "/control/resume":
            sentinel = WebhookHandler._shutdown_sentinel
            if not sentinel:
                self._send_json(503, {"error": "sentinel path not configured"})
                return
            try:
                if os.path.exists(sentinel):
                    os.remove(sentinel)
                self._send_json(200, {"action": "resume", "status": "sentinel_removed"})
            except OSError as e:
                self._send_json(500, {"error": f"failed to remove sentinel: {e}"})
        else:
            self._send_json(404, {"error": "not_found"})

    def _handle_sse(self):
        """Handle GET /live — Server-Sent Events stream."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        q: queue.Queue = queue.Queue()
        with _sse_clients_lock:
            _sse_clients.append(q)

        # Send init event with current ledger state (so JS renders immediately)
        try:
            state = read_ledger()
            if state:
                init_raw = _build_sse_payload(state)
                init_wrapped = {
                    "type": "status_update",
                    "data": {
                        "loop_status": init_raw.get("status", "unknown"),
                        "ledger": {
                            "status": init_raw.get("status", "unknown"),
                            "total_iterations": init_raw.get("total_iterations", 0),
                            "max_iterations": init_raw.get("max_iterations", 0),
                            "goal": init_raw.get("goal", ""),
                            "evolved_goal": init_raw.get("evolved_goal", ""),
                            "started_at": init_raw.get("started_at", ""),
                            "last_updated": init_raw.get("last_updated", ""),
                            "cooldown": init_raw.get("cooldown", 0),
                        },
                        "latest_iteration": init_raw.get("iteration", {}),
                        "stats": init_raw.get("stats", {}),
                        "error_counts": init_raw.get("error_counts", {}),
                        "mitigations": init_raw.get("mitigations", {}),
                        "eta": init_raw.get("eta", {}),
                        "goals": init_raw.get("goals", []),
                        "avg_chars_per_iter": init_raw.get("avg_chars_per_iter"),
                        "avg_throughput": init_raw.get("avg_throughput"),
                        "est_cost": init_raw.get("est_cost"),
                        "iters_per_goal": init_raw.get("iters_per_goal"),
                        "metrics_summary": init_raw.get("metrics_summary", ""),
                        "consecutive_errors": init_raw.get("consecutive_errors", 0),
                        "consecutive_successes": init_raw.get(
                            "consecutive_successes", 0
                        ),
                        "cooldown": init_raw.get("cooldown", 0),
                        "iteration": init_raw.get("iteration", {}),
                    },
                }
                self.wfile.write(
                    f"event: init\ndata: {json.dumps(init_wrapped, default=str)}\n\n".encode(
                        "utf-8"
                    )
                )
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            with _sse_clients_lock:
                try:
                    _sse_clients.remove(q)
                except ValueError:
                    pass
            return

        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    raw = json.loads(data) if isinstance(data, str) else data
                    # Build a status dict matching the web_app format the SSE dashboard JS expects
                    # (the JS references loop_status, latest_iteration, and ledger sub-keys)
                    wrapped = {
                        "type": "status_update",
                        "data": {
                            "loop_status": raw.get("status", "unknown"),
                            "ledger": {
                                "status": raw.get("status", "unknown"),
                                "total_iterations": raw.get("total_iterations", 0),
                                "max_iterations": raw.get("max_iterations", 0),
                                "goal": raw.get("goal", ""),
                                "evolved_goal": raw.get("evolved_goal", ""),
                                "started_at": raw.get("started_at", ""),
                                "last_updated": raw.get("last_updated", ""),
                                "cooldown": raw.get("cooldown", 0),
                            },
                            "latest_iteration": raw.get("iteration", {}),
                            "stats": raw.get("stats", {}),
                            "error_counts": raw.get("error_counts", {}),
                            "mitigations": raw.get("mitigations", {}),
                            "eta": raw.get("eta", {}),
                            "goals": raw.get("goals", []),
                            "avg_chars_per_iter": raw.get("avg_chars_per_iter"),
                            "avg_throughput": raw.get("avg_throughput"),
                            "est_cost": raw.get("est_cost"),
                            "iters_per_goal": raw.get("iters_per_goal"),
                            "metrics_summary": raw.get("metrics_summary", ""),
                            "consecutive_errors": raw.get("consecutive_errors", 0),
                            "consecutive_successes": raw.get(
                                "consecutive_successes", 0
                            ),
                            "cooldown": raw.get("cooldown", 0),
                            "iteration": raw.get("iteration", {}),
                        },
                    }
                    self.wfile.write(
                        f"event: update\ndata: {json.dumps(wrapped, default=str)}\n\n".encode(
                            "utf-8"
                        )
                    )
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b"event: heartbeat\ndata: {}\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
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
    allow_reuse_address = True
    daemon_threads = True


def _start_webhook_server(
    port: int, trigger_fn, sentinel_path: str = ""
) -> http.server.HTTPServer:
    """Start the webhook server in a daemon thread."""
    WebhookHandler._trigger_fn = trigger_fn
    WebhookHandler._shutdown_sentinel = sentinel_path
    server = ThreadedHTTPServer(("", port), WebhookHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    _log(f"[WEBHOOK] Server listening on http://0.0.0.0:{port}")
    return server
