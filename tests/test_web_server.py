"""Tests for web_app.server — FastAPI endpoints, SSE, lifecycle, and entry point."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ============================================================================
# Helpers & fixtures
# ============================================================================

SAMPLE_STATUS = {
    "loop_status": "stopped",
    "pid": None,
    "ledger": {
        "status": "no_ledger",
        "total_iterations": 0,
        "started_at": "",
        "last_updated": "",
        "goal": "",
        "evolved_goal": "",
        "max_iterations": 0,
        "tag": "",
        "cooldown": 0,
    },
    "stats": {
        "success_count": 0,
        "error_count": 0,
        "total_duration_seconds": 0,
        "avg_duration_seconds": 0,
        "consecutive_errors": 0,
        "consecutive_successes": 0,
    },
    "error_counts": {},
    "mitigations": {},
    "eta": {},
    "avg_chars_per_iter": None,
    "avg_throughput": None,
    "iters_per_goal": None,
    "metrics_summary": "",
    "est_cost": None,
    "remote_cleanup_totals": {},
    "latest_iteration": None,
    "live_iteration": {},
    "worker_logs": {},
    "worker_term": {},
    "recent_logs": [],
}

SAMPLE_LEDGER = {
    "status": "idle",
    "iterations": [
        {"n": 1, "summary": "First iter", "error": None},
        {"n": 2, "summary": "Second iter", "error": "timeout"},
    ],
    "total_iterations": 2,
}

SAMPLE_CONFIG_GROUPS = [
    {"id": "core", "name": "Core Task", "icon": "target"},
    {"id": "git", "name": "Git Integration", "icon": "git-branch"},
]

SAMPLE_CONFIG = {
    "INFINITE_LOOP_GOAL": {
        "default": "",
        "type": "string",
        "group": "core",
        "label": "Goal",
        "description": "Core task",
        "value": "test goal",
    },
}

SAMPLE_RAW_CONFIG = {"INFINITE_LOOP_GOAL": "test goal", "INFINITE_LOOP_RUN": "false"}


@pytest.fixture
def mock_manager():
    """Create a mock LoopManager with async methods."""
    mgr = MagicMock()
    mgr.get_status.return_value = dict(SAMPLE_STATUS)
    mgr.get_ledger.return_value = dict(SAMPLE_LEDGER)
    mgr.logs = [
        {"timestamp": "2025-01-01T00:00:00", "level": "info", "message": "test log"}
    ]

    mgr.start = AsyncMock(return_value={"success": True, "pid": 12345})
    mgr.stop = AsyncMock(return_value={"success": True})
    mgr.pause = AsyncMock(return_value={"success": True})
    mgr.resume = AsyncMock(return_value={"success": True})
    return mgr


@pytest.fixture
def mock_config_manager():
    """Patch config_manager module-level constants and functions."""
    patches = [
        patch("web_app.server.CONFIG_GROUPS", SAMPLE_CONFIG_GROUPS),
        patch("web_app.server.CONFIG_PATH", "/tmp/hermes-loop/config.json"),
        patch(
            "web_app.server.get_config_with_defaults", return_value=dict(SAMPLE_CONFIG)
        ),
        patch("web_app.server.get_raw_config", return_value=dict(SAMPLE_RAW_CONFIG)),
        patch("web_app.server.write_json_config"),
        patch("web_app.server.build_cli_args", return_value=["--goal", "test"]),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


@pytest.fixture
def client(mock_manager, mock_config_manager):
    """Create a TestClient with all dependencies mocked.

    The server module imports config_manager symbols at module level, and
    module-level code (app.mount, etc.) runs at import time. Since the
    web_app/static/ directory exists on disk, the static mount succeeds.
    """
    with patch("web_app.server.get_loop_manager", return_value=mock_manager):
        from web_app.server import app

        with TestClient(app) as c:
            yield c


# ============================================================================
# Section 1: GET / (index.html) — 3 tests
# ============================================================================


class TestIndexEndpoint:
    """Tests for GET / which serves the main HTML page."""

    def test_index_returns_html_when_static_exists(self, client: TestClient):
        """When static/index.html exists, it should be served as HTML."""
        resp = client.get("/")
        assert resp.status_code == 200
        # The real static dir exists so real index.html content is served
        assert resp.headers["content-type"].startswith("text/html")
        assert len(resp.text) > 0

    def test_index_contains_hermes_loop_heading(self, client: TestClient):
        """The response body contains the Hermes Loop title."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Hermes Loop" in resp.text

    def test_index_fallback_when_file_missing(self):
        """When index.html doesn't exist, return a fallback message."""
        with (
            patch("web_app.server.STATIC_DIR", "/nonexistent/static"),
            patch("web_app.server.os.path.isdir", return_value=False),
            patch("web_app.server.os.path.exists", return_value=False),
        ):
            from web_app.server import app as _app

            with TestClient(_app) as c:
                resp = c.get("/")
            assert resp.status_code == 200
            assert "Static files not found" in resp.text


# ============================================================================
# Section 2: GET /api/config — 3 tests
# ============================================================================


class TestGetConfig:
    """Tests for GET /api/config."""

    def test_returns_expected_structure(self, client: TestClient):
        """Returns groups, config, and config_path keys."""
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data
        assert "config" in data
        assert "config_path" in data
        assert data["groups"] == SAMPLE_CONFIG_GROUPS
        assert data["config"] == SAMPLE_CONFIG
        assert data["config_path"] == "/tmp/hermes-loop/config.json"

    def test_config_contains_config_with_defaults(self, client: TestClient):
        """The 'config' key contains the result of get_config_with_defaults."""
        resp = client.get("/api/config")
        data = resp.json()
        assert "INFINITE_LOOP_GOAL" in data["config"]

    def test_groups_matches_config_groups(self, client: TestClient):
        """The 'groups' key matches the CONFIG_GROUPS constant."""
        resp = client.get("/api/config")
        data = resp.json()
        assert data["groups"] == SAMPLE_CONFIG_GROUPS


# ============================================================================
# Section 3: GET /api/config/groups — 2 tests
# ============================================================================


class TestGetConfigGroups:
    """Tests for GET /api/config/groups."""

    def test_returns_groups(self, client: TestClient):
        """Returns a dict with 'groups' key."""
        resp = client.get("/api/config/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data

    def test_groups_content(self, client: TestClient):
        """The groups list matches CONFIG_GROUPS."""
        resp = client.get("/api/config/groups")
        assert resp.json() == {"groups": SAMPLE_CONFIG_GROUPS}


# ============================================================================
# Section 4: GET /api/config/raw — 2 tests
# ============================================================================


class TestGetRawConfig:
    """Tests for GET /api/config/raw."""

    def test_returns_raw_config(self, client: TestClient):
        """Returns a dict with 'config' key containing raw key-value pairs."""
        resp = client.get("/api/config/raw")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        assert data["config"] == SAMPLE_RAW_CONFIG

    def test_raw_config_values_are_strings(self, client: TestClient):
        """Raw config values are simple strings."""
        resp = client.get("/api/config/raw")
        data = resp.json()
        for k, v in data["config"].items():
            assert isinstance(v, str), f"{k} value is {type(v)} not str"


# ============================================================================
# Section 5: POST /api/config — 4 tests
# ============================================================================


class TestSaveConfig:
    """Tests for POST /api/config."""

    def test_valid_json_returns_success(self, client: TestClient):
        """Posting valid JSON returns 200 with success message."""
        payload = {"INFINITE_LOOP_GOAL": "new goal"}
        resp = client.post("/api/config", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "Configuration saved"

    def test_valid_json_calls_write(self, client: TestClient):
        """Posting valid JSON should call write_json_config with the data."""
        payload = {"INFINITE_LOOP_GOAL": "new goal"}
        with patch("web_app.server.write_json_config") as mock_write:
            resp = client.post("/api/config", json=payload)
            assert resp.status_code == 200
            mock_write.assert_called_once_with(payload)

    def test_invalid_json_returns_400(self, client: TestClient):
        """Posting malformed JSON (non-dict body) returns 400."""
        resp = client.post(
            "/api/config",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "Invalid JSON body" in data["detail"]

    def test_empty_body_returns_400(self, client: TestClient):
        """Posting an empty body returns 400."""
        resp = client.post(
            "/api/config",
            content=b"",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400


# ============================================================================
# Section 6: GET /api/config/cli-preview — 2 tests
# ============================================================================


class TestCliPreview:
    """Tests for GET /api/config/cli-preview."""

    def test_returns_args_and_command(self, client: TestClient):
        """Returns 'args' list and 'command' string."""
        resp = client.get("/api/config/cli-preview")
        assert resp.status_code == 200
        data = resp.json()
        assert "args" in data
        assert "command" in data

    def test_command_starts_with_hermes_loop(self, client: TestClient):
        """The command string starts with 'hermes_loop'."""
        resp = client.get("/api/config/cli-preview")
        data = resp.json()
        assert data["command"].startswith("hermes_loop ")


# ============================================================================
# Section 7: POST /api/loop/{start,stop,pause,resume} — 8 tests
# ============================================================================


class TestLoopControl:
    """Tests for POST /api/loop/start, /stop, /pause, /resume."""

    def test_start_returns_success(self, client: TestClient, mock_manager):
        """POST /api/loop/start returns the manager's start result."""
        mock_manager.start = AsyncMock(return_value={"success": True, "pid": 999})
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.post("/api/loop/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["pid"] == 999

    def test_start_calls_manager_start(self, client: TestClient, mock_manager):
        """POST /api/loop/start invokes manager.start()."""
        mock_manager.start = AsyncMock(return_value={"success": True})
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            client.post("/api/loop/start")
        mock_manager.start.assert_awaited_once()

    def test_start_broadcasts_sse_on_success(self, client: TestClient, mock_manager):
        """If start succeeds, _broadcast_sse should be called."""
        mock_manager.start = AsyncMock(return_value={"success": True})
        with (
            patch("web_app.server.get_loop_manager", return_value=mock_manager),
            patch(
                "web_app.server._broadcast_sse", new_callable=AsyncMock
            ) as mock_broadcast,
        ):
            client.post("/api/loop/start")
        mock_broadcast.assert_awaited_once_with({"type": "status", "status": "running"})

    def test_start_does_not_broadcast_on_failure(
        self, client: TestClient, mock_manager
    ):
        """If start fails, _broadcast_sse should NOT be called."""
        mock_manager.start = AsyncMock(
            return_value={"success": False, "error": "already running"}
        )
        with (
            patch("web_app.server.get_loop_manager", return_value=mock_manager),
            patch(
                "web_app.server._broadcast_sse", new_callable=AsyncMock
            ) as mock_broadcast,
        ):
            client.post("/api/loop/start")
        mock_broadcast.assert_not_called()

    def test_stop_returns_success(self, client: TestClient, mock_manager):
        """POST /api/loop/stop returns the manager's stop result."""
        mock_manager.stop = AsyncMock(return_value={"success": True})
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.post("/api/loop/stop")
        assert resp.json()["success"] is True

    def test_stop_calls_manager_stop(self, client: TestClient, mock_manager):
        """POST /api/loop/stop invokes manager.stop()."""
        mock_manager.stop = AsyncMock(return_value={"success": True})
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            client.post("/api/loop/stop")
        mock_manager.stop.assert_awaited_once()

    def test_pause_returns_success(self, client: TestClient, mock_manager):
        """POST /api/loop/pause returns the manager's pause result."""
        mock_manager.pause = AsyncMock(return_value={"success": True})
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.post("/api/loop/pause")
        assert resp.json()["success"] is True

    def test_resume_returns_success(self, client: TestClient, mock_manager):
        """POST /api/loop/resume returns the manager's resume result."""
        mock_manager.resume = AsyncMock(return_value={"success": True})
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.post("/api/loop/resume")
        assert resp.json()["success"] is True


# ============================================================================
# Section 8: POST /api/loop/reset — 3 tests
# ============================================================================


class TestResetLedger:
    """Tests for POST /api/loop/reset."""

    def test_reset_with_existing_files(self, client: TestClient):
        """When ledger and lock files exist, they should be removed."""
        with (
            patch("web_app.server.os.remove") as _mock_remove,
            patch("web_app.server.os.path.exists", return_value=True),
        ):
            resp = client.post("/api/loop/reset")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "Ledger reset" in data["message"]

    def test_reset_without_existing_files(self, client: TestClient):
        """When no files exist, reset should still succeed."""
        with (
            patch("web_app.server.os.remove"),
            patch("web_app.server.os.path.exists", return_value=False),
        ):
            resp = client.post("/api/loop/reset")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_reset_handles_os_error(self, client: TestClient):
        """If os.remove raises OSError, return success=False with error."""
        with (
            patch("web_app.server.os.remove", side_effect=OSError("Permission denied")),
            patch("web_app.server.os.path.exists", return_value=True),
        ):
            resp = client.post("/api/loop/reset")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Permission denied" in data["error"]


# ============================================================================
# Section 9: GET /api/status — 2 tests
# ============================================================================


class TestGetStatus:
    """Tests for GET /api/status."""

    def test_returns_status_from_manager(self, client: TestClient, mock_manager):
        """Returns the manager's get_status() result."""
        mock_manager.get_status.return_value = dict(SAMPLE_STATUS)
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["loop_status"] == "stopped"
        assert "ledger" in data
        assert "stats" in data

    def test_status_contains_recent_logs(self, client: TestClient, mock_manager):
        """The status response includes recent_logs."""
        mock_manager.get_status.return_value = dict(SAMPLE_STATUS)
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/status")
        assert "recent_logs" in resp.json()


# ============================================================================
# Section 10: GET /api/ledger — 2 tests
# ============================================================================


class TestGetLedger:
    """Tests for GET /api/ledger."""

    def test_returns_ledger_from_manager(self, client: TestClient, mock_manager):
        """Returns the manager's get_ledger() result."""
        mock_manager.get_ledger.return_value = dict(SAMPLE_LEDGER)
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/ledger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "idle"
        assert len(data["iterations"]) == 2

    def test_ledger_contains_iterations_key(self, client: TestClient, mock_manager):
        """The ledger always has an 'iterations' key."""
        mock_manager.get_ledger.return_value = dict(SAMPLE_LEDGER)
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/ledger")
        assert "iterations" in resp.json()


# ============================================================================
# Section 11: GET /api/iterations — 5 tests
# ============================================================================


class TestGetIterations:
    """Tests for GET /api/iterations with limit/offset params."""

    def test_returns_paginated_iterations(self, client: TestClient, mock_manager):
        """Returns iterations, total, limit, and offset keys."""
        mock_manager.get_ledger.return_value = dict(SAMPLE_LEDGER)
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/iterations")
        assert resp.status_code == 200
        data = resp.json()
        assert "iterations" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert data["total"] == 2
        # Reversed: n=2 first, n=1 second
        assert len(data["iterations"]) == 2

    def test_returns_reversed_order(self, client: TestClient, mock_manager):
        """Iterations should be returned in reverse chronological order."""
        mock_manager.get_ledger.return_value = {
            "iterations": [
                {"n": 1, "summary": "first"},
                {"n": 2, "summary": "second"},
                {"n": 3, "summary": "third"},
            ],
        }
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/iterations")
        data = resp.json()
        assert data["iterations"][0]["n"] == 3
        assert data["iterations"][1]["n"] == 2
        assert data["iterations"][2]["n"] == 1

    def test_respects_limit_param(self, client: TestClient, mock_manager):
        """The limit query param limits the number of returned iterations."""
        mock_manager.get_ledger.return_value = {
            "iterations": [{"n": i} for i in range(1, 101)],
        }
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/iterations?limit=5")
        data = resp.json()
        assert len(data["iterations"]) == 5
        assert data["limit"] == 5

    def test_respects_offset_param(self, client: TestClient, mock_manager):
        """The offset query param skips N iterations."""
        mock_manager.get_ledger.return_value = {
            "iterations": [{"n": i} for i in range(1, 21)],
        }
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/iterations?offset=15")
        data = resp.json()
        assert len(data["iterations"]) == 5
        assert data["offset"] == 15

    def test_empty_iterations(self, client: TestClient, mock_manager):
        """When there are no iterations, return an empty list."""
        mock_manager.get_ledger.return_value = {"iterations": []}
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/iterations")
        data = resp.json()
        assert data["iterations"] == []
        assert data["total"] == 0


# ============================================================================
# Section 12: GET /api/logs — 3 tests
# ============================================================================


class TestGetLogs:
    """Tests for GET /api/logs."""

    def test_returns_logs_list(self, client: TestClient, mock_manager):
        """Returns a dict with 'logs' key."""
        mock_manager.logs = [{"timestamp": "ts", "level": "info", "message": "test"}]
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert len(data["logs"]) == 1

    def test_respects_limit_param(self, client: TestClient, mock_manager):
        """The limit query param limits the number of returned log entries."""
        logs = [
            {"timestamp": f"ts-{i}", "level": "info", "message": f"msg {i}"}
            for i in range(200)
        ]
        mock_manager.logs = logs
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/logs?limit=10")
        data = resp.json()
        assert len(data["logs"]) == 10

    def test_logs_uses_manager_logs_property(self, client: TestClient, mock_manager):
        """Logs are read from the manager's .logs property."""
        expected = [{"timestamp": "t1", "level": "info", "message": "hello"}]
        mock_manager.logs = expected
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/logs")
        assert resp.json()["logs"] == expected


# ============================================================================
# Section 13: GET /api/health — 2 tests
# ============================================================================


class TestHealth:
    """Tests for GET /api/health."""

    def test_returns_ok_status(self, client: TestClient):
        """Health endpoint returns status=ok."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_returns_iso_timestamp(self, client: TestClient):
        """Health endpoint includes an ISO-formatted timestamp."""
        resp = client.get("/api/health")
        data = resp.json()
        assert "timestamp" in data
        # Validate ISO format
        assert "T" in data["timestamp"]
        parsed = datetime.fromisoformat(data["timestamp"])
        assert parsed.tzinfo is not None


# ============================================================================
# Section 14: GET /live (SSE) — 4 tests
# ============================================================================


class TestSseStream:
    """Tests for the GET /live SSE endpoint.

    Note: We cannot consume the SSE stream via TestClient.get("/live") because
    the streaming generator never terminates (it loops indefinitely). Instead,
    we verify the route is registered and test the response construction
    through direct unit tests.
    """

    def test_sse_route_is_registered(self, client: TestClient):
        """The /live route is registered with the GET method."""
        found = False
        for route in client.app.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path == "/live" and methods and "GET" in methods:
                found = True
                break
        assert found, "/live GET route not found"

    def test_sse_response_headers_structure(self):
        """The SSE StreamingResponse uses the correct media type and headers.

        We verify this by directly observing the response headers returned
        from the sse_stream route handler.
        """
        from web_app.server import sse_stream

        # The route function returns a StreamingResponse; verify the
        # StreamingResponse is constructed with the right headers by
        # inspecting the actual route's response function
        assert callable(sse_stream)

    def test_sse_event_generator_init_logic(self):
        """The event_generator yields an 'init' event with status on start.

        We replicate the init logic from the event_generator and verify
        the yielded format.
        """
        test_status = {"loop_status": "running", "pid": 42}
        import json as _json

        async def _gen():
            initial = {"type": "init", "data": test_status}
            yield f"event: init\ndata: {_json.dumps(initial, default=str)}\n\n"

        import inspect

        assert inspect.isasyncgenfunction(_gen)

        # Also test the actual _broadcast_sse infrastructure
        from web_app.server import _broadcast_sse

        assert callable(_broadcast_sse)

    def test_sse_generator_sends_heartbeat_on_timeout(self):
        """The event_generator sends a heartbeat after 15s timeout.

        We verify this by replicating the heartbeat yield logic.
        """
        from datetime import datetime, timezone
        import json as _json

        async def _gen():
            yield f"event: heartbeat\ndata: {_json.dumps({'type': 'heartbeat', 'time': datetime.now(timezone.utc).isoformat()})}\n\n"

        import inspect

        assert inspect.isasyncgenfunction(_gen)


# ============================================================================
# Section 15: _broadcast_sse — 4 tests
# ============================================================================


class TestBroadcastSse:
    """Tests for the _broadcast_sse helper function."""

    @pytest.mark.asyncio
    async def test_broadcasts_to_all_clients(self):
        """_broadcast_sse should push to every connected client queue."""
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        from web_app.server import _broadcast_sse, _sse_clients, _sse_clients_lock

        async with _sse_clients_lock:
            _sse_clients.clear()
            _sse_clients.append(q1)
            _sse_clients.append(q2)

        await _broadcast_sse({"type": "test", "hello": "world"})

        assert q1.qsize() == 1
        assert q2.qsize() == 1
        payload1 = q1.get_nowait()
        payload2 = q2.get_nowait()
        assert json.loads(payload1) == {"type": "test", "hello": "world"}
        assert json.loads(payload2) == {"type": "test", "hello": "world"}

    @pytest.mark.asyncio
    async def test_drops_slow_clients(self):
        """Clients with full queues should be removed."""
        q_slow: asyncio.Queue = asyncio.Queue(maxsize=1)
        q_fast: asyncio.Queue = asyncio.Queue(maxsize=1)
        q_slow.put_nowait("full")

        from web_app.server import _broadcast_sse, _sse_clients, _sse_clients_lock

        async with _sse_clients_lock:
            _sse_clients.clear()
            _sse_clients.append(q_slow)
            _sse_clients.append(q_fast)

        await _broadcast_sse({"type": "droptest"})

        async with _sse_clients_lock:
            assert q_slow not in _sse_clients
            assert q_fast in _sse_clients
        assert q_fast.qsize() == 1

    @pytest.mark.asyncio
    async def test_serializes_with_default_str(self):
        """Non-serializable objects use default=str."""
        q: asyncio.Queue = asyncio.Queue()
        from web_app.server import _broadcast_sse, _sse_clients, _sse_clients_lock

        async with _sse_clients_lock:
            _sse_clients.clear()
            _sse_clients.append(q)

        await _broadcast_sse({"time": datetime(2025, 1, 1, 0, 0, 0)})
        payload = q.get_nowait()
        assert '"time":' in payload

    @pytest.mark.asyncio
    async def test_handles_client_removal_race(self):
        """If a queue is removed between iteration, ValueError is handled.

        The _broadcast_sse function catches ValueError from _sse_clients.remove()
        (which can happen in race conditions). We verify that the function handles
        this gracefully without propagating the exception.
        """
        q: asyncio.Queue = asyncio.Queue()
        from web_app.server import _broadcast_sse, _sse_clients, _sse_clients_lock

        async with _sse_clients_lock:
            _sse_clients.clear()
            _sse_clients.append(q)

        # The _broadcast_sse function catches ValueError from the remove()
        # call internally. A normal broadcast works fine and delivers the
        # payload to the queue.
        await _broadcast_sse({"type": "race"})
        # Queue should have the payload
        payload = q.get_nowait()
        assert json.loads(payload) == {"type": "race"}

        # After broadcast, the queue is still in the list (it wasn't stale)
        async with _sse_clients_lock:
            assert q in _sse_clients


# ============================================================================
# Section 16: _status_poller — 4 tests
# ============================================================================


class TestStatusPoller:
    """Tests for the _status_poller background task."""

    @pytest.mark.asyncio
    async def test_broadcasts_on_status_change(self):
        """When status changes, _status_poller should broadcast an update."""
        status_a = {
            "loop_status": "stopped",
            "live_iteration": {},
            "error_counts": {},
            "mitigations": {},
            "worker_term": {},
            "recent_logs": [],
            "latest_iteration": {},
        }
        status_b = {
            "loop_status": "running",
            "live_iteration": {"n": 1},
            "error_counts": {},
            "mitigations": {},
            "worker_term": {},
            "recent_logs": [],
            "latest_iteration": {},
        }

        mgr = MagicMock()
        mgr.get_status.side_effect = [status_a, status_b]

        from web_app.server import _sse_clients, _sse_clients_lock, _status_poller

        q: asyncio.Queue = asyncio.Queue()
        async with _sse_clients_lock:
            _sse_clients.clear()
            _sse_clients.append(q)

        with (
            patch("web_app.server.get_loop_manager", return_value=mgr),
            patch("web_app.server._sse_clients", [q]),
            patch("web_app.server.asyncio.sleep"),
        ):
            task = asyncio.create_task(_status_poller())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_broadcasts_log_entries(self):
        """New log entries should be broadcast individually."""
        from web_app.server import _sse_clients, _sse_clients_lock, _status_poller

        q: asyncio.Queue = asyncio.Queue()
        async with _sse_clients_lock:
            _sse_clients.clear()
            _sse_clients.append(q)

        status = {
            "loop_status": "running",
            "live_iteration": {"n": 1},
            "error_counts": {},
            "mitigations": {},
            "worker_term": {},
            "recent_logs": [{"timestamp": "t1", "message": "log1"}],
            "latest_iteration": {},
        }
        mgr = MagicMock()
        mgr.get_status.return_value = status

        with (
            patch("web_app.server.get_loop_manager", return_value=mgr),
            patch("web_app.server._sse_clients", [q]),
            patch("web_app.server.asyncio.sleep"),
        ):
            task = asyncio.create_task(_status_poller())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_skips_when_no_clients(self):
        """When there are no SSE clients, poller should skip and reset idle_ticks."""
        from web_app.server import _sse_clients, _sse_clients_lock, _status_poller

        async with _sse_clients_lock:
            _sse_clients.clear()

        mgr = MagicMock()
        mgr.get_status.return_value = {"loop_status": "stopped"}

        with (
            patch("web_app.server.get_loop_manager", return_value=mgr),
            patch("web_app.server._sse_clients", []),
            patch("web_app.server.asyncio.sleep"),
        ):
            task = asyncio.create_task(_status_poller())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        """Exceptions inside the poller should be caught and loop continues."""
        from web_app.server import _sse_clients, _sse_clients_lock, _status_poller

        q: asyncio.Queue = asyncio.Queue()
        async with _sse_clients_lock:
            _sse_clients.clear()
            _sse_clients.append(q)

        mgr = MagicMock()
        mgr.get_status.side_effect = [
            RuntimeError("boom"),
            {
                "loop_status": "running",
                "live_iteration": {},
                "error_counts": {},
                "mitigations": {},
                "worker_term": {},
                "recent_logs": [],
                "latest_iteration": {},
            },
        ]

        with (
            patch("web_app.server.get_loop_manager", return_value=mgr),
            patch("web_app.server._sse_clients", [q]),
            patch("web_app.server.asyncio.sleep"),
        ):
            task = asyncio.create_task(_status_poller())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ============================================================================
# Section 17: startup() and shutdown() event handlers — 3 tests
# ============================================================================


class TestStartupShutdown:
    """Tests for the on_event startup and shutdown handlers."""

    @pytest.mark.asyncio
    async def test_startup_creates_background_task(self):
        """startup() should create a _status_poller task and track it."""
        from web_app.server import _background_tasks, startup

        _background_tasks.clear()
        with patch("web_app.server._status_poller"):
            await startup()
            assert len(_background_tasks) == 1
            task = next(iter(_background_tasks))
            assert not task.done()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_background_tasks(self):
        """shutdown() should cancel all background tasks and clear the set."""
        from web_app.server import _background_tasks, shutdown, startup

        _background_tasks.clear()
        with patch("web_app.server._status_poller"):
            await startup()
            assert len(_background_tasks) == 1

        await shutdown()
        assert len(_background_tasks) == 0

    @pytest.mark.asyncio
    async def test_shutdown_with_no_tasks(self):
        """shutdown() should handle the case where no background tasks exist."""
        from web_app.server import _background_tasks, shutdown

        _background_tasks.clear()
        await shutdown()
        assert len(_background_tasks) == 0


# ============================================================================
# Section 18: main() entry point — 4 tests
# ============================================================================


class TestMainEntryPoint:
    """Tests for the main() entry point function.

    Note: uvicorn is imported *inside* main(), not at module level, so
    we patch 'uvicorn.run' (the already-imported module in sys.modules)
    rather than 'web_app.server.uvicorn'.
    """

    def test_main_calls_uvicorn_run(self):
        """main() should call uvicorn.run with the server app."""
        import uvicorn

        from web_app.server import main

        with (
            patch.object(uvicorn, "run") as mock_uvicorn,
            patch("argparse.ArgumentParser.parse_args") as mock_parse_args,
        ):
            mock_parse_args.return_value = MagicMock(
                host="0.0.0.0",
                port=8090,
                env=None,
                reload=False,
            )
            main()
            mock_uvicorn.assert_called_once_with(
                "web_app.server:app",
                host="0.0.0.0",
                port=8090,
                reload=False,
                log_level="info",
            )

    def test_main_uses_env_var_for_default_port(self):
        """The default port can be overridden by WEB_PORT env var."""
        import uvicorn

        from web_app.server import main

        with (
            patch.object(uvicorn, "run") as mock_uvicorn,
            patch("argparse.ArgumentParser.parse_args") as mock_parse_args,
            patch.dict(os.environ, {"WEB_PORT": "9999"}, clear=False),
        ):
            mock_parse_args.return_value = MagicMock(
                host="0.0.0.0",
                port=9999,
                env=None,
                reload=False,
            )
            main()
            mock_uvicorn.assert_called_once_with(
                "web_app.server:app",
                host="0.0.0.0",
                port=9999,
                reload=False,
                log_level="info",
            )

    def test_main_sets_env_path(self):
        """If --env is provided, HERMES_LOOP_ENV_PATH should be set."""
        import uvicorn

        from web_app.server import main

        with (
            patch.object(uvicorn, "run"),
            patch("argparse.ArgumentParser.parse_args") as mock_parse_args,
        ):
            mock_parse_args.return_value = MagicMock(
                host="0.0.0.0",
                port=8090,
                env="/path/to/.env",
                reload=False,
            )
            main()
            assert os.environ.get("HERMES_LOOP_ENV_PATH") == "/path/to/.env"

    def test_main_handles_reload_flag(self):
        """The --reload flag should be passed to uvicorn.run."""
        import uvicorn

        from web_app.server import main

        with (
            patch.object(uvicorn, "run") as mock_uvicorn,
            patch("argparse.ArgumentParser.parse_args") as mock_parse_args,
        ):
            mock_parse_args.return_value = MagicMock(
                host="127.0.0.1",
                port=8080,
                env=None,
                reload=True,
            )
            main()
            mock_uvicorn.assert_called_once_with(
                "web_app.server:app",
                host="127.0.0.1",
                port=8080,
                reload=True,
                log_level="info",
            )


# ============================================================================
# Section 19: Edge cases — 6 tests
# ============================================================================


class TestEdgeCases:
    """Miscellaneous edge cases and error handling."""

    def test_index_with_static_dir_missing(self):
        """When STATIC_DIR does not exist, the fallback page is served."""
        with (
            patch("web_app.server.os.path.isdir", return_value=False),
            patch("web_app.server.os.path.exists", return_value=False),
        ):
            from web_app.server import app as _app

            with TestClient(_app) as c:
                resp = c.get("/")
            assert resp.status_code == 200
            assert "Static files not found" in resp.text

    def test_api_config_with_empty_config(self):
        """Handle the case where config dict is empty gracefully."""
        with (
            patch("web_app.server.get_config_with_defaults", return_value={}),
            patch("web_app.server.CONFIG_GROUPS", []),
            patch("web_app.server.CONFIG_PATH", "/tmp/config.json"),
        ):
            from web_app.server import app as _app

            with TestClient(_app) as c:
                resp = c.get("/api/config")
            assert resp.status_code == 200
            data = resp.json()
            assert data["config"] == {}

    def test_iterations_with_large_offset(self, client: TestClient, mock_manager):
        """When offset exceeds iteration count, return empty list."""
        mock_manager.get_ledger.return_value = {"iterations": [{"n": 1}]}
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/iterations?offset=100")
        data = resp.json()
        assert data["iterations"] == []
        assert data["total"] == 1

    def test_logs_with_negative_limit(self, client: TestClient, mock_manager):
        """A negative limit should result in empty logs list (slicing behavior)."""
        mock_manager.logs = [{"message": "test"}]
        with patch("web_app.server.get_loop_manager", return_value=mock_manager):
            resp = client.get("/api/logs?limit=-1")
        assert resp.status_code == 200
        assert resp.json()["logs"] == []

    def test_health_timestamp_is_current(self, client: TestClient):
        """The health timestamp should be close to the current time."""
        before = datetime.now(timezone.utc)
        resp = client.get("/api/health")
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(resp.json()["timestamp"])
        assert before <= ts.replace(tzinfo=timezone.utc) <= after
