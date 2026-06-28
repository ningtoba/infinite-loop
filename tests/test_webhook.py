"""Tests for webhook.py — WebhookHandler, ThreadedHTTPServer, _start_webhook_server."""

from __future__ import annotations

import io
import json
import queue
import http.server
import socketserver
from unittest import mock as _mock
from unittest.mock import MagicMock, patch

from hermes_loop.webhook import (
    WebhookHandler,
    ThreadedHTTPServer,
    _start_webhook_server,
)

# ===================================================================
# Helper factory — bypass BaseHTTPRequestHandler.__init__
# ===================================================================


def _make_handler(
    method="GET",
    path="/health",
    body=b"",
    headers=None,
    client_address=("127.0.0.1", 54321),
) -> WebhookHandler:
    """Create a WebhookHandler without invoking BaseHTTPRequestHandler.__init__."""
    handler = WebhookHandler.__new__(WebhookHandler)
    handler.command = method
    handler.path = path
    handler.headers = headers or {}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.client_address = client_address
    handler.server = MagicMock()
    handler.request = b""
    handler.close_connection = True
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.log_message = MagicMock()
    # Mock server attributes BaseHTTPRequestHandler needs
    handler.server.server_address = ("0.0.0.0", 8888)
    return handler


# ===================================================================
# _send_json — base helper used by all route handlers
# ===================================================================


class TestSendJson:
    def test_sends_200_with_data(self):
        """_send_json writes JSON response with correct status."""
        handler = _make_handler()
        handler._send_json(200, {"status": "ok"})

        written = handler.wfile.getvalue()
        assert b"200 OK" in written
        assert b'"status": "ok"' in written
        assert b"Content-Type: application/json" in written

    def test_sends_404_with_data(self):
        """_send_json supports non-200 status codes."""
        handler = _make_handler()
        handler._send_json(404, {"error": "not_found"})

        written = handler.wfile.getvalue()
        assert b"404" in written

    def test_content_length_header(self):
        """_send_json includes Content-Length matching body size."""
        handler = _make_handler()
        data = {"key": "value"}
        handler._send_json(200, data)
        expected_len = len(json.dumps(data, default=str).encode("utf-8"))
        assert f"Content-Length: {expected_len}".encode() in handler.wfile.getvalue()


# ===================================================================
# do_GET — routing
# ===================================================================


class TestDoGet:
    def test_health_returns_ok(self):
        """GET /health returns 200 with status ok and timestamp."""
        handler = _make_handler(path="/health")
        handler.do_GET()

        written = handler.wfile.getvalue()
        assert b"200 OK" in written
        assert b'"status": "ok"' in written
        assert b'"timestamp"' in written

    def test_status_with_ledger(self):
        """GET /status returns summary fields when ledger exists."""
        handler = _make_handler(path="/status")
        with patch(
            "hermes_loop.webhook.read_ledger",
            return_value={
                "status": "running",
                "total_iterations": 5,
                "last_updated": "2025-01-01T00:00:00+00:00",
                "stats": {"success_count": 3, "error_count": 2},
            },
        ):
            handler.do_GET()

        written = handler.wfile.getvalue().decode()
        assert '"status": "running"' in written
        assert '"total_iterations": 5' in written
        assert '"success_count": 3' in written
        assert '"error_count": 2' in written

    def test_status_no_ledger(self):
        """GET /status returns no_ledger when ledger is None."""
        handler = _make_handler(path="/status")
        with patch("hermes_loop.webhook.read_ledger", return_value=None):
            handler.do_GET()

        written = handler.wfile.getvalue().decode()
        assert '"status": "no_ledger"' in written

    def test_api_status_with_ledger(self):
        """GET /api/status returns wrapped payload when ledger exists."""
        handler = _make_handler(path="/api/status")
        fake_state = {"status": "running", "total_iterations": 3, "stats": {}}
        fake_raw = {"status": "running", "total_iterations": 3}
        fake_wrapped = {
            "type": "status_update",
            "data": {
                "loop_status": "running",
                "ledger": {"status": "running", "total_iterations": 3},
            },
        }
        with patch("hermes_loop.webhook.read_ledger", return_value=fake_state):
            with patch("hermes_loop.webhook._build_sse_payload", return_value=fake_raw):
                with patch(
                    "hermes_loop.webhook._wrap_sse_payload", return_value=fake_wrapped
                ):
                    handler.do_GET()

        written = handler.wfile.getvalue().decode()
        assert '"loop_status": "running"' in written

    def test_api_status_no_ledger(self):
        """GET /api/status returns fallback payload when ledger is None."""
        handler = _make_handler(path="/api/status")
        with patch("hermes_loop.webhook.read_ledger", return_value=None):
            handler.do_GET()

        written = handler.wfile.getvalue().decode()
        assert '"loop_status": "no_ledger"' in written

    def test_live_sse(self):
        """GET /live triggers _handle_sse."""
        handler = _make_handler(path="/live")
        with patch.object(handler, "_handle_sse") as mock_sse:
            handler.do_GET()
        mock_sse.assert_called_once()

    def test_dashboard_serves_html(self):
        """GET /dashboard triggers _serve_dashboard_html."""
        handler = _make_handler(path="/dashboard")
        with patch.object(handler, "_serve_dashboard_html") as mock_dash:
            handler.do_GET()
        mock_dash.assert_called_once()

    def test_api_iterations(self):
        """GET /api/iterations triggers _handle_api_iterations."""
        handler = _make_handler(path="/api/iterations")
        with patch.object(handler, "_handle_api_iterations") as mock_iters:
            handler.do_GET()
        mock_iters.assert_called_once()

    def test_unknown_path_returns_404(self):
        """GET on unknown path returns 404."""
        handler = _make_handler(path="/nonexistent")
        handler.do_GET()

        written = handler.wfile.getvalue().decode()
        assert '"error": "not_found"' in written
        assert "404" in written


# ===================================================================
# do_POST — routing
# ===================================================================


class TestDoPost:
    def test_webhook_with_body(self):
        """POST /webhook with JSON body triggers trigger_fn."""
        handler = _make_handler(
            method="POST",
            path="/webhook",
            body=b'{"goal":"test goal","context":"ctx"}',
            headers={"Content-Length": "36"},
        )
        mock_trigger = MagicMock(return_value={"status": "completed"})
        WebhookHandler._trigger_fn = mock_trigger
        handler.do_POST()

        written = handler.wfile.getvalue().decode()
        assert '"triggered": true' in written
        mock_trigger.assert_called_once_with(goal="test goal", context="ctx")

    def test_webhook_without_body(self):
        """POST /webhook with no body calls trigger_fn with None params."""
        handler = _make_handler(
            method="POST",
            path="/webhook",
            body=b"",
            headers={"Content-Length": "0"},
        )
        mock_trigger = MagicMock(return_value={"status": "completed"})
        WebhookHandler._trigger_fn = mock_trigger
        handler.do_POST()

        mock_trigger.assert_called_once_with(goal=None, context=None)

    def test_webhook_no_trigger_fn(self):
        """POST /webhook returns 503 when trigger_fn not set."""
        handler = _make_handler(
            method="POST",
            path="/webhook",
            body=b"{}",
            headers={"Content-Length": "2"},
        )
        WebhookHandler._trigger_fn = None
        handler.do_POST()

        written = handler.wfile.getvalue().decode()
        assert '"triggered"' not in written
        assert "503" in written

    def test_webhook_invalid_json(self):
        """POST /webhook with invalid JSON returns 400."""
        handler = _make_handler(
            method="POST",
            path="/webhook",
            body=b"not json",
            headers={"Content-Length": "8"},
        )
        WebhookHandler._trigger_fn = MagicMock()
        handler.do_POST()

        written = handler.wfile.getvalue().decode()
        assert "400" in written
        assert "invalid JSON" in written

    def test_control_stop_writes_sentinel(self):
        """POST /control/stop writes 'stop' to sentinel file."""
        handler = _make_handler(method="POST", path="/control/stop")
        WebhookHandler._shutdown_sentinel = "/tmp/test_stop_sentinel"
        with patch("builtins.open", _mock.mock_open()) as mock_open:
            handler.do_POST()
        mock_open.assert_called_once_with("/tmp/test_stop_sentinel", "w")
        handle = mock_open()
        handle.write.assert_called_once_with("stop")

    def test_control_stop_no_sentinel(self):
        """POST /control/stop returns 503 when sentinel not configured."""
        handler = _make_handler(method="POST", path="/control/stop")
        WebhookHandler._shutdown_sentinel = ""
        handler.do_POST()

        written = handler.wfile.getvalue().decode()
        assert "503" in written

    def test_control_stop_oserror(self):
        """POST /control/stop returns 500 on OSError."""
        handler = _make_handler(method="POST", path="/control/stop")
        WebhookHandler._shutdown_sentinel = "/tmp/test_stop_sentinel"
        with patch("builtins.open", side_effect=OSError("permission denied")):
            handler.do_POST()

        written = handler.wfile.getvalue().decode()
        assert "500" in written

    def test_control_pause_writes_sentinel(self):
        """POST /control/pause writes 'pause' to sentinel file."""
        handler = _make_handler(method="POST", path="/control/pause")
        WebhookHandler._shutdown_sentinel = "/tmp/test_pause_sentinel"
        with patch("builtins.open", _mock.mock_open()) as mock_open:
            handler.do_POST()
        handle = mock_open()
        handle.write.assert_called_once_with("pause")

    def test_control_pause_no_sentinel(self):
        """POST /control/pause returns 503 when sentinel not configured."""
        handler = _make_handler(method="POST", path="/control/pause")
        WebhookHandler._shutdown_sentinel = ""
        handler.do_POST()
        written = handler.wfile.getvalue().decode()
        assert "503" in written

    def test_control_pause_oserror(self):
        """POST /control/pause returns 500 on OSError."""
        handler = _make_handler(method="POST", path="/control/pause")
        WebhookHandler._shutdown_sentinel = "/tmp/test_pause_sentinel"
        with patch("builtins.open", side_effect=OSError("permission denied")):
            handler.do_POST()
        written = handler.wfile.getvalue().decode()
        assert "500" in written

    def test_control_resume_removes_sentinel(self):
        """POST /control/resume removes existing sentinel file."""
        handler = _make_handler(method="POST", path="/control/resume")
        WebhookHandler._shutdown_sentinel = "/tmp/test_resume_sentinel"
        with patch("os.path.exists", return_value=True):
            with patch("os.remove") as mock_remove:
                handler.do_POST()
        mock_remove.assert_called_once_with("/tmp/test_resume_sentinel")
        written = handler.wfile.getvalue().decode()
        assert '"status": "sentinel_removed"' in written

    def test_control_resume_no_sentinel(self):
        """POST /control/resume returns 503 when sentinel not configured."""
        handler = _make_handler(method="POST", path="/control/resume")
        WebhookHandler._shutdown_sentinel = ""
        handler.do_POST()
        written = handler.wfile.getvalue().decode()
        assert "503" in written

    def test_control_resume_oserror(self):
        """POST /control/resume returns 500 on OSError."""
        handler = _make_handler(method="POST", path="/control/resume")
        WebhookHandler._shutdown_sentinel = "/tmp/test_resume_sentinel"
        with patch("os.path.exists", return_value=True):
            with patch("os.remove", side_effect=OSError("permission denied")):
                handler.do_POST()
        written = handler.wfile.getvalue().decode()
        assert "500" in written

    def test_unknown_post_returns_404(self):
        """POST on unknown path returns 404."""
        handler = _make_handler(method="POST", path="/unknown")
        handler.do_POST()
        written = handler.wfile.getvalue().decode()
        assert "404" in written


# ===================================================================
# _handle_sse
# ===================================================================
class TestHandleSse:
    def test_sends_init_event_from_ledger(self):
        """SSE handler sends init event with current ledger state."""
        handler = _make_handler(path="/live")
        handler.wfile = io.BytesIO()
        fake_state = {"status": "running", "total_iterations": 1}
        fake_raw = {"status": "running"}
        fake_wrapped = {"type": "status_update", "data": {"loop_status": "running"}}

        with patch("hermes_loop.webhook.read_ledger", return_value=fake_state):
            with patch("hermes_loop.webhook._build_sse_payload", return_value=fake_raw):
                with patch(
                    "hermes_loop.webhook._wrap_sse_payload", return_value=fake_wrapped
                ):
                    with patch("hermes_loop.webhook._sse_clients", []):
                        with patch("hermes_loop.webhook._sse_clients_lock"):
                            # Make the queue.get() raise BrokenPipeError to break loop
                            with patch(
                                "queue.Queue.get",
                                side_effect=BrokenPipeError("broken pipe"),
                            ):
                                handler._handle_sse()

        written = handler.wfile.getvalue()
        assert b"event: init" in written

    def test_sends_heartbeat_on_queue_empty(self):
        """SSE handler sends heartbeat when queue times out."""
        handler = _make_handler(path="/live")
        handler.wfile = io.BytesIO()

        # Setup: make the loop run once: init succeeds, then q.get raises
        # queue.Empty (heartbeat), then next call raises BrokenPipeError (exit loop)
        fake_state = {"status": "running", "total_iterations": 1}
        fake_raw = {"status": "running"}
        fake_wrapped = {"type": "status_update", "data": {"loop_status": "running"}}

        with patch("hermes_loop.webhook.read_ledger", return_value=fake_state):
            with patch("hermes_loop.webhook._build_sse_payload", return_value=fake_raw):
                with patch(
                    "hermes_loop.webhook._wrap_sse_payload", return_value=fake_wrapped
                ):
                    with patch("hermes_loop.webhook._sse_clients", []):
                        with patch("hermes_loop.webhook._sse_clients_lock"):
                            get_side_effect = [
                                queue.Empty("timeout"),
                                BrokenPipeError("broken pipe"),
                            ]
                            with patch("queue.Queue.get", side_effect=get_side_effect):
                                handler._handle_sse()

        written = handler.wfile.getvalue()
        assert b"event: heartbeat" in written

    def test_handles_queue_update_event(self):
        """SSE handler processes data from queue as update events."""
        handler = _make_handler(path="/live")
        handler.wfile = io.BytesIO()

        fake_state = {"status": "running", "total_iterations": 1}
        fake_raw = {"status": "running"}
        fake_wrapped = {"type": "status_update", "data": {"loop_status": "running"}}

        update_data = json.dumps({"status": "running", "iteration": 5})

        with patch("hermes_loop.webhook.read_ledger", return_value=fake_state):
            with patch("hermes_loop.webhook._build_sse_payload", return_value=fake_raw):
                with patch(
                    "hermes_loop.webhook._wrap_sse_payload", return_value=fake_wrapped
                ):
                    with patch("hermes_loop.webhook._sse_clients", []):
                        with patch("hermes_loop.webhook._sse_clients_lock"):
                            get_side_effect = [
                                update_data,
                                BrokenPipeError("broken pipe"),
                            ]
                            with patch("queue.Queue.get", side_effect=get_side_effect):
                                handler._handle_sse()

        written = handler.wfile.getvalue()
        assert b"event: update" in written
        assert b"loop_status" in written

    def test_broken_pipe_during_init_caught_gracefully(self):
        """BrokenPipeError during init event is caught, client is removed."""
        handler = _make_handler(path="/live")
        # Make the init event write fail by replacing wfile.write to fail on event data
        real_wfile = handler.wfile

        with patch(
            "hermes_loop.webhook.read_ledger", return_value={"status": "running"}
        ):
            with patch("hermes_loop.webhook._build_sse_payload", return_value={}):
                with patch("hermes_loop.webhook._wrap_sse_payload", return_value={}):
                    mock_clients = []
                    with patch("hermes_loop.webhook._sse_clients", mock_clients):
                        with patch("hermes_loop.webhook._sse_clients_lock"):
                            # Only fail writes containing event data (after headers are sent)
                            def failing_write(data, _orig=real_wfile.write):
                                if b"event:" in data:
                                    raise BrokenPipeError("broken")
                                return _orig(data)

                            handler.wfile.write = failing_write
                            # Should not raise
                            handler._handle_sse()

                    # Client queue should be removed from list
                    assert len(mock_clients) == 0

    def test_oserror_during_loop_caught_gracefully(self):
        """OSError during SSE loop is caught and final cleanup runs."""
        handler = _make_handler(path="/live")

        with patch("hermes_loop.webhook.read_ledger", return_value=None):
            with patch("hermes_loop.webhook._sse_clients", []):
                with patch("hermes_loop.webhook._sse_clients_lock"):
                    get_side_effect = OSError("connection reset")
                    with patch("queue.Queue.get", side_effect=get_side_effect):
                        handler._handle_sse()  # should not raise


# ===================================================================
# _serve_dashboard_html
# ===================================================================


class TestServeDashboardHtml:
    def test_serves_html_content(self):
        """_serve_dashboard_html returns 200 with HTML content."""
        handler = _make_handler(path="/dashboard")
        handler._serve_dashboard_html()
        written = handler.wfile.getvalue()
        assert b"text/html" in written
        assert b"200 OK" in written

    def test_serves_non_empty_body(self):
        """_serve_dashboard_html returns non-empty HTML body."""
        handler = _make_handler(path="/dashboard")
        with patch("hermes_loop.webhook._SSE_DASHBOARD_HTML_TPL", "<html>test</html>"):
            handler._serve_dashboard_html()
        written = handler.wfile.getvalue()
        assert b"<html>test</html>" in written


# ===================================================================
# _handle_api_iterations
# ===================================================================


class TestHandleApiIterations:
    def test_returns_iterations_from_ledger(self):
        """_handle_api_iterations returns recent iterations from ledger."""
        handler = _make_handler(path="/api/iterations")
        state = {
            "iterations": [
                {"id": 1, "summary": "first"},
                {"id": 2, "summary": "second"},
            ]
        }
        with patch("hermes_loop.webhook.read_ledger", return_value=state):
            handler._handle_api_iterations()
        written = handler.wfile.getvalue().decode()
        assert '"total": 2' in written
        # Reversed order — second should appear first
        assert '"limit": 50' in written

    def test_default_limit_is_50(self):
        """_handle_api_iterations defaults to limit=50 when no query param."""
        handler = _make_handler(path="/api/iterations")
        many_iters = [{"id": i} for i in range(100)]
        with patch(
            "hermes_loop.webhook.read_ledger", return_value={"iterations": many_iters}
        ):
            handler._handle_api_iterations()
        written = handler.wfile.getvalue()
        import json as _json

        if isinstance(written, bytes):
            written = written.decode("utf-8")
        data = _json.loads(written.split("\r\n\r\n")[-1])
        assert data["limit"] == 50
        assert len(data["iterations"]) == 50

    def test_custom_limit_via_query(self):
        """_handle_api_iterations respects ?limit=N query param."""
        handler = _make_handler(path="/api/iterations?limit=10")
        many_iters = [{"id": i} for i in range(100)]
        with patch(
            "hermes_loop.webhook.read_ledger", return_value={"iterations": many_iters}
        ):
            handler._handle_api_iterations()
        written = handler.wfile.getvalue()
        import json as _json

        if isinstance(written, bytes):
            written = written.decode("utf-8")
        data = _json.loads(written.split("\r\n\r\n")[-1])
        assert data["limit"] == 10

    def test_limit_clamped_to_500(self):
        """_handle_api_iterations clamps limit to 500 max."""
        handler = _make_handler(path="/api/iterations?limit=9999")
        many_iters = [{"id": i} for i in range(1000)]
        with patch(
            "hermes_loop.webhook.read_ledger", return_value={"iterations": many_iters}
        ):
            handler._handle_api_iterations()
        written = handler.wfile.getvalue()
        import json as _json

        if isinstance(written, bytes):
            written = written.decode("utf-8")
        data = _json.loads(written.split("\r\n\r\n")[-1])
        assert data["limit"] == 500

    def test_limit_minimum_1(self):
        """_handle_api_iterations clamps limit to minimum 1."""
        handler = _make_handler(path="/api/iterations?limit=0")
        many_iters = [{"id": i} for i in range(10)]
        with patch(
            "hermes_loop.webhook.read_ledger", return_value={"iterations": many_iters}
        ):
            handler._handle_api_iterations()
        written = handler.wfile.getvalue()
        import json as _json

        if isinstance(written, bytes):
            written = written.decode("utf-8")
        data = _json.loads(written.split("\r\n\r\n")[-1])
        assert data["limit"] == 1
        assert len(data["iterations"]) == 1

    def test_invalid_limit_falls_back_to_50(self):
        """_handle_api_iterations falls back to 50 when limit is not an int."""
        handler = _make_handler(path="/api/iterations?limit=abc")
        many_iters = [{"id": i} for i in range(10)]
        with patch(
            "hermes_loop.webhook.read_ledger", return_value={"iterations": many_iters}
        ):
            handler._handle_api_iterations()
        written = handler.wfile.getvalue()
        import json as _json

        if isinstance(written, bytes):
            written = written.decode("utf-8")
        data = _json.loads(written.split("\r\n\r\n")[-1])
        assert data["limit"] == 50

    def test_returns_empty_when_no_ledger(self):
        """_handle_api_iterations returns empty when no ledger state."""
        handler = _make_handler(path="/api/iterations")
        with patch("hermes_loop.webhook.read_ledger", return_value=None):
            handler._handle_api_iterations()
        written = handler.wfile.getvalue()
        import json as _json

        if isinstance(written, bytes):
            written = written.decode("utf-8")
        data = _json.loads(written.split("\r\n\r\n")[-1])
        assert data["total"] == 0
        assert data["iterations"] == []


# ===================================================================
# ThreadedHTTPServer
# ===================================================================


class TestThreadedHTTPServer:
    def test_base_classes(self):
        """ThreadedHTTPServer inherits from ThreadingMixIn and HTTPServer."""
        assert issubclass(ThreadedHTTPServer, http.server.HTTPServer)
        assert issubclass(ThreadedHTTPServer, socketserver.ThreadingMixIn)

    def test_reuse_address(self):
        """ThreadedHTTPServer allows address reuse."""
        assert ThreadedHTTPServer.allow_reuse_address is True

    def test_daemon_threads(self):
        """ThreadedHTTPServer runs threads as daemons."""
        assert ThreadedHTTPServer.daemon_threads is True


# ===================================================================
# _start_webhook_server
# ===================================================================


class TestStartWebhookServer:
    def test_sets_class_vars_and_creates_server(self):
        """_start_webhook_server sets class vars and returns server."""
        mock_fn = MagicMock()
        mock_server = MagicMock()

        with patch(
            "hermes_loop.webhook.ThreadedHTTPServer", return_value=mock_server
        ) as mock_cls:
            with patch("threading.Thread") as mock_thread:
                result = _start_webhook_server(
                    port=8888, trigger_fn=mock_fn, sentinel_path="/tmp/sentinel"
                )

        assert WebhookHandler._trigger_fn is mock_fn
        assert WebhookHandler._shutdown_sentinel == "/tmp/sentinel"
        mock_cls.assert_called_once_with(("", 8888), WebhookHandler)
        mock_thread.assert_called_once_with(
            target=mock_server.serve_forever, daemon=True
        )
        assert result is mock_server

    def test_default_sentinel_path(self):
        """_start_webhook_server defaults to empty sentinel path."""
        mock_fn = MagicMock()
        with patch("hermes_loop.webhook.ThreadedHTTPServer"):
            with patch("threading.Thread"):
                _start_webhook_server(port=9999, trigger_fn=mock_fn)
        assert WebhookHandler._shutdown_sentinel == ""
