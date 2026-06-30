"""Tests for web_app.server — FastAPI web server for omp-loop Web UI."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from web_app.rate_limiter import SlidingWindowRateLimiter
from web_app.server import app


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


class TestIndex:
    def test_returns_html_when_static_exists(self, client):
        """GET / returns HTML when static/index.html exists."""
        mock_html = "<h1>omp-loop Web UI</h1>"
        with (
            patch("os.path.exists", return_value=True),
            patch(
                "builtins.open",
                MagicMock(
                    return_value=MagicMock(
                        __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=mock_html)))
                    )
                ),
            ),
        ):
            resp = client.get("/")
        assert resp.status_code == 200
        assert mock_html in resp.text

    def test_returns_fallback_when_no_static(self, client):
        """GET / returns fallback when static files not found."""
        with patch("os.path.exists", return_value=False):
            resp = client.get("/")
        assert resp.status_code == 200
        assert "Static files not found" in resp.text


class TestConfigAPI:
    def test_get_config(self, client):
        """GET /api/config returns configuration."""
        with patch("web_app.server.get_config") as mock_get_config:
            mock_get_config.return_value = {
                "INFINITE_LOOP_GOAL": {"value": "test", "group": "core"},
            }
            resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data
        assert "config" in data

    def test_save_config_valid(self, client):
        """POST /api/config saves valid configuration."""
        with (
            patch("web_app.server.save_config"),
            patch("web_app.server.validate_config", return_value={"valid": True, "errors": []}),
        ):
            resp = client.post("/api/config", json={"goal": "test"})
        assert resp.status_code == 200

    def test_save_config_invalid(self, client):
        """POST /api/config returns 422 on validation errors."""
        with patch("web_app.server.validate_config", return_value={"valid": False, "errors": ["Goal required"]}):
            resp = client.post("/api/config", json={"goal": ""})
        assert resp.status_code == 422

    def test_get_config_groups(self, client):
        """GET /api/config returns group definitions."""
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["groups"]) > 0

    def test_save_config_bad_json(self, client):
        """POST /api/config returns 400 on bad JSON body."""
        resp = client.post("/api/config", content=b"not json", headers={"Content-Type": "application/json"})
        assert resp.status_code != 200


class TestStartAPI:
    def test_start_success(self, client):
        """POST /api/loop/start starts the loop."""
        mock_mgr = MagicMock()
        mock_mgr.start = AsyncMock(return_value={"success": True, "pid": 12345})
        with patch("web_app.server.get_loop_manager", return_value=mock_mgr):
            resp = client.post("/api/loop/start")
        assert resp.status_code == 200
        assert resp.json()["success"]

    def test_start_failure(self, client):
        """POST /api/loop/start handles start failure."""
        mock_mgr = MagicMock()
        mock_mgr.start = AsyncMock(return_value={"success": False, "error": "already running"})
        with patch("web_app.server.get_loop_manager", return_value=mock_mgr):
            resp = client.post("/api/loop/start")
        assert resp.status_code == 200
        assert not resp.json()["success"]


class TestStopAPI:
    def test_stop_success(self, client):
        """POST /api/loop/stop stops the loop."""
        mock_mgr = MagicMock()
        mock_mgr.stop = AsyncMock(return_value={"success": True})
        with patch("web_app.server.get_loop_manager", return_value=mock_mgr):
            resp = client.post("/api/loop/stop")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_stop_failure(self, client):
        """POST /api/loop/stop handles stop failure."""
        mock_mgr = MagicMock()
        mock_mgr.stop = AsyncMock(return_value={"success": False, "error": "not running"})
        with patch("web_app.server.get_loop_manager", return_value=mock_mgr):
            resp = client.post("/api/loop/stop")
        assert resp.status_code == 200


class TestPauseResumeAPI:
    def test_pause(self, client):
        """POST /api/loop/pause pauses the loop."""
        mock_mgr = MagicMock()
        mock_mgr.pause = AsyncMock(return_value={"success": True})
        with patch("web_app.server.get_loop_manager", return_value=mock_mgr):
            resp = client.post("/api/loop/pause")
        assert resp.status_code == 200

    def test_resume(self, client):
        """POST /api/loop/resume resumes the loop."""
        mock_mgr = MagicMock()
        mock_mgr.resume = AsyncMock(return_value={"success": True})
        with patch("web_app.server.get_loop_manager", return_value=mock_mgr):
            resp = client.post("/api/loop/resume")
        assert resp.status_code == 200


class TestStatusAPI:
    def test_get_status(self, client):
        """GET /api/status returns loop status."""
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"loop_status": "stopped", "pid": None, "stats": {"success_count": 0}}
        with patch("web_app.server.get_loop_manager", return_value=mock_mgr):
            resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["loop_status"] == "stopped"


class TestLogsAPI:
    def test_get_logs(self, client):
        """GET /api/logs returns recent logs."""
        with patch("web_app.server.get_loop_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_status.return_value = {
                "recent_logs": [{"timestamp": "2025-01-01T00:00:00", "level": "info", "message": "test"}]
            }
            mock_get_mgr.return_value = mock_mgr
            resp = client.get("/api/logs")
        assert resp.status_code == 200


class TestHistoryAPI:
    def test_get_iterations(self, client):
        """GET /api/iterations returns iteration history."""
        with patch("web_app.server.get_loop_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            ledger = {"iterations": [{"n": i, "error": None, "duration_seconds": 10.0} for i in range(10)]}
            mock_mgr.get_ledger.return_value = ledger
            mock_get_mgr.return_value = mock_mgr
            resp = client.get("/api/iterations?limit=5")
        assert resp.status_code == 200

    def test_get_iterations_default_limit(self, client):
        """GET /api/iterations with no limit uses default."""
        with patch("web_app.server.get_loop_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_ledger.return_value = {"iterations": []}
            mock_get_mgr.return_value = mock_mgr
            resp = client.get("/api/iterations")
        assert resp.status_code == 200


class TestSSE:
    def test_sse_connection(self, client):
        """GET /api/events returns SSE events stream."""
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {
            "loop_status": "stopped",
            "ledger": {},
            "stats": {},
            "error_counts": {},
            "mitigations": {},
            "latest_iteration": None,
            "recent_logs": [],
        }
        mock_mgr._add_log = MagicMock()
        with patch("web_app.server.get_loop_manager", return_value=mock_mgr), client.stream("GET", "/api/events"):
            pass


class TestCLIArgs:
    def test_build_cli_args(self):
        """build_cli_args produces correct CLI arguments."""
        from web_app.config_manager import build_cli_args

        config = {"INFINITE_LOOP_GOAL": "test goal", "INFINITE_LOOP_GIT": "true", "INFINITE_LOOP_GIT_COMMIT": "true"}
        args = build_cli_args(config)
        assert "--goal" in args
        assert "--git" in args

    def test_get_raw_config(self):
        """get_raw_config returns stored config."""
        from web_app.config_manager import get_raw_config

        with patch("web_app.config_manager._read_stored", return_value={"INFINITE_LOOP_GOAL": "test"}):
            config = get_raw_config()
        assert config["INFINITE_LOOP_GOAL"] == "test"


class TestApiKeyAuth:
    """Tests for API-key authentication middleware."""

    def test_no_key_configured_allows_all(self, client):
        """When OMP_LOOP_API_KEY is unset, all requests pass through."""
        with patch.dict(os.environ, {}, clear=True), patch("web_app.server.get_config") as mock_get_config:
            mock_get_config.return_value = {"INFINITE_LOOP_GOAL": {"value": "test", "group": "core"}}
            resp = client.get("/api/config")
        assert resp.status_code == 200

    def test_empty_key_disables_auth(self, client):
        """When OMP_LOOP_API_KEY is empty, all requests pass through."""
        # This tests the case where the env var is set but empty — should behave the same as unset
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": ""}, clear=True),
            patch("web_app.server.get_config") as mock_get_config,
        ):
            mock_get_config.return_value = {"INFINITE_LOOP_GOAL": {"value": "test", "group": "core"}}
            resp = client.get("/api/config")
        assert resp.status_code == 200

    def test_valid_key_allows_access(self, client):
        """A request with valid Bearer token gets through."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True),
            patch("web_app.server.get_config") as mock_get_config,
        ):
            mock_get_config.return_value = {"INFINITE_LOOP_GOAL": {"value": "test", "group": "core"}}
            resp = client.get("/api/config", headers={"Authorization": "Bearer my-secret-key"})
        assert resp.status_code == 200

    def test_missing_key_returns_401(self, client):
        """A request with no Authorization header gets 401."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True),
            patch("web_app.server.get_config") as mock_get_config,
        ):
            mock_get_config.return_value = {"INFINITE_LOOP_GOAL": {"value": "test", "group": "core"}}
            resp = client.get("/api/config")
        assert resp.status_code == 401
        data = resp.json()
        assert "detail" in data

    def test_wrong_key_returns_401(self, client):
        """A request with the wrong bearer token gets 401."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": "correct-key"}, clear=True),
            patch("web_app.server.get_config") as mock_get_config,
        ):
            mock_get_config.return_value = {"INFINITE_LOOP_GOAL": {"value": "test", "group": "core"}}
            resp = client.get("/api/config", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_health_endpoint_always_allowed(self, client):
        """The /api/health endpoint bypasses auth."""
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_non_api_paths_bypass_auth(self, client):
        """Non-/api paths bypass auth, returning 404 for unknown paths."""
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            resp = client.get("/nonexistent")
        # Non-/api paths bypass auth; unknown path getting a 404 confirms the
        # request reached the router without being blocked by auth middleware.
        assert resp.status_code == 404


class TestRateLimit:
    """Tests for rate-limiting middleware."""

    @pytest.fixture(autouse=True)
    def _fresh_limiters(self):
        """Replace module-level limiter instances with fresh ones before each test.

        This prevents cross-test pollution since the limiters track timestamps
        in module-level singletons.
        """
        from web_app import server as srv

        original_control = srv._control_limiter
        original_read = srv._read_limiter
        srv._control_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60.0)
        srv._read_limiter = SlidingWindowRateLimiter(max_requests=120, window_seconds=60.0)
        yield
        srv._control_limiter = original_control
        srv._read_limiter = original_read

    @pytest.fixture
    def mock_config(self):
        """Patch config endpoints so they return 200 without side effects."""
        with (
            patch("web_app.server.get_config") as cfg,
            patch("web_app.server.get_raw_config") as raw,
            patch("web_app.server.CONFIG_GROUPS", []),
        ):
            cfg.return_value = {"key": {"value": "val", "group": "core"}}
            raw.return_value = {"key": "val"}
            yield

    # ── Read endpoint tests ───────────────────────────────────────────────

    def test_read_endpoint_allowed_within_limit(self, client):
        """A GET to a read endpoint succeeds when under the limit."""
        with (
            patch("web_app.server.get_config") as cfg,
            patch("web_app.server.CONFIG_GROUPS", []),
        ):
            cfg.return_value = {"key": {"value": "val", "group": "core"}}
            resp = client.get("/api/config")
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") == "120"
        remaining = int(resp.headers.get("X-RateLimit-Remaining", "0"))
        assert remaining >= 119

    def test_read_endpoint_exhausted(self, client):
        """A GET returns 429 after exhausting the read limit."""
        import web_app.server as srv

        # Exhaust by patching the limiter with a max_requests=0 instance
        original = srv._read_limiter
        srv._read_limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60.0)
        try:
            resp = client.get("/api/config")
            assert resp.status_code == 429
            data = resp.json()
            assert "Rate limit exceeded" in data["detail"]
            assert resp.headers.get("Retry-After") == "60"
        finally:
            srv._read_limiter = original

    # ── Control endpoint tests ────────────────────────────────────────────

    def test_control_endpoint_allowed_within_limit(self, client):
        """A POST to a control endpoint succeeds when under the limit."""
        with (
            patch("web_app.server.save_config"),
            patch("web_app.server.validate_config", return_value={"valid": True, "errors": []}),
        ):
            resp = client.post("/api/config", json={"goal": "test"})
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") == "30"
        remaining = int(resp.headers.get("X-RateLimit-Remaining", "0"))
        assert remaining >= 29

    def test_control_endpoint_exhausted(self, client):
        """A POST returns 429 after exhausting the control limit."""
        import web_app.server as srv

        original = srv._control_limiter
        srv._control_limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60.0)
        try:
            with (
                patch("web_app.server.save_config"),
                patch("web_app.server.validate_config", return_value={"valid": True, "errors": []}),
            ):
                resp = client.post("/api/config", json={"goal": "test"})
            assert resp.status_code == 429
        finally:
            srv._control_limiter = original

    # ── Exempt path tests ─────────────────────────────────────────────────

    def test_health_endpoint_bypasses_rate_limit(self, client):
        """GET /api/health always works regardless of limit."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        # No rate-limit headers on exempt endpoints
        assert resp.headers.get("X-RateLimit-Limit") is None

    def test_non_api_path_bypasses_rate_limit(self, client):
        """Non-/api paths are not rate-limited."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") is None

    # ── Rate limiter interop with Auth ─────────────────────────────────────

    def test_rate_limit_applies_when_auth_disabled(self, client):
        """Rate limiting works independently of auth (no key = still rate-limited)."""
        import web_app.server as srv

        original = srv._read_limiter
        srv._read_limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60.0)
        try:
            with patch.dict(os.environ, {}, clear=True):
                resp = client.get("/api/config")
            assert resp.status_code == 429
        finally:
            srv._read_limiter = original

    def test_rate_limit_applies_after_auth(self, client):
        """With auth enabled, an authed request can still be rate-limited."""
        import web_app.server as srv

        original = srv._read_limiter
        srv._read_limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60.0)
        try:
            with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-key"}, clear=True):
                resp = client.get("/api/config", headers={"Authorization": "Bearer my-key"})
            assert resp.status_code == 429
        finally:
            srv._read_limiter = original


class TestValidateConfig:
    def test_validates_required_fields(self):
        """validate_config checks required fields."""
        from web_app.config_manager import validate_config

        result = validate_config({"INFINITE_LOOP_GOAL": ""})
        assert not result.get("valid")
        errors = result.get("errors", [])
        assert isinstance(errors, list) and len(errors) > 0

    def test_valid_config_passes(self):
        """validate_config passes with valid config."""
        from web_app.config_manager import validate_config

        result = validate_config({"INFINITE_LOOP_GOAL": "my goal"})
        assert result.get("valid")
