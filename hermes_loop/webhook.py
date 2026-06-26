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
    _SSE_DASHBOARD_HTML_TPL,
    _broadcast_to_sse_clients,
    _build_sse_payload,
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
                self._send_json(200, state)
            else:
                self._send_json(200, {"status": "no_ledger"})
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

        q: queue.Queue = queue.Queue(maxsize=1)
        with _sse_clients_lock:
            _sse_clients.append(q)

        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    self.wfile.write(
                        f"event: iteration\ndata: {data}\n\n".encode("utf-8")
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
