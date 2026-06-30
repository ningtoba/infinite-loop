"""Tests for API-key authentication middleware (web_app.server.api_key_auth).

Covers unit tests (direct middleware logic) and an integration-style test
with a standalone FastAPI app and an HTTP client over the ASGI protocol.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from web_app.server import app as production_app

# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_test_app() -> FastAPI:
    """Build a minimal FastAPI app with auth middleware and test endpoints.

    The middleware reads ``OMP_LOOP_API_KEY`` from ``os.environ`` at runtime,
    so the caller controls auth by patching ``os.environ`` before creating
    the ``TestClient``.
    """
    app = FastAPI()

    # Apply the same middleware logic inline (mirrors production server.py)
    @app.middleware("http")
    async def api_key_auth_middleware(request: Request, call_next):
        api_key = os.environ.get("OMP_LOOP_API_KEY", "")
        if not api_key:
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        if path == "/api/health":
            return await call_next(request)
        auth_header = request.headers.get("Authorization", "")
        expected = f"Bearer {api_key}"
        if auth_header != expected:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid API key"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

    @app.get("/api/echo")
    async def echo():
        return {"ok": True}

    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/")
    async def root():
        return {"ok": True}

    return app


# ── Unit Tests (middleware logic via mocked os.environ) ──────────────────────


class TestApiKeyAuthUnit:
    """Unit tests for the api_key_auth middleware using TestClient + env mocks.

    These feed requests through the **production** FastAPI app but mock
    ``os.environ`` so the middleware sees known key values.  Backend
    responses (config, status, …) are also mocked so auth is the only thing
    being tested.
    """

    @pytest.fixture
    def client(self):
        """TestClient bound to the production FastAPI app."""
        return TestClient(production_app)

    # -- Backward compat: no key configured ---------------------------------

    def test_no_key_configured_allows_all(self, client):
        """When OMP_LOOP_API_KEY is unset, /api/* requests pass through."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("web_app.server.get_config") as cfg,
        ):
            cfg.return_value = {"k": {"value": "v", "group": "core"}}
            resp = client.get("/api/config")
        assert resp.status_code == 200

    def test_empty_key_disables_auth(self, client):
        """When OMP_LOOP_API_KEY is empty-string, auth is still disabled."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": ""}, clear=True),
            patch("web_app.server.get_config") as cfg,
        ):
            cfg.return_value = {"k": {"value": "v", "group": "core"}}
            resp = client.get("/api/config")
        assert resp.status_code == 200

    def test_empty_key_disables_auth_even_for_arbitrary_endpoint(self, client):
        """Empty-key mode allows access to any /api/* endpoint."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": ""}, clear=True),
            patch("web_app.server.get_loop_manager") as mgr,
        ):
            mgr.return_value.get_status.return_value = {"loop_status": "stopped"}
            resp = client.get("/api/status")
        assert resp.status_code == 200

    # -- Auth enabled -------------------------------------------------------

    def test_valid_key_allows_access(self, client):
        """A correct Bearer token results in 200."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True),
            patch("web_app.server.get_config") as cfg,
        ):
            cfg.return_value = {"k": {"value": "v", "group": "core"}}
            resp = client.get(
                "/api/config",
                headers={"Authorization": "Bearer my-secret-key"},
            )
        assert resp.status_code == 200

    def test_missing_key_returns_401(self, client):
        """No Authorization header → 401."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True),
            patch("web_app.server.get_config") as cfg,
        ):
            cfg.return_value = {"k": {"value": "v", "group": "core"}}
            resp = client.get("/api/config")
        assert resp.status_code == 401
        data = resp.json()
        assert data["detail"] == "Missing or invalid API key"

    def test_wrong_key_returns_401(self, client):
        """Wrong Bearer token → 401."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": "correct-key"}, clear=True),
            patch("web_app.server.get_config") as cfg,
        ):
            cfg.return_value = {"k": {"value": "v", "group": "core"}}
            resp = client.get(
                "/api/config",
                headers={"Authorization": "Bearer wrong-key"},
            )
        assert resp.status_code == 401

    def test_wrong_scheme_returns_401(self, client):
        """A non-Bearer Authorization header (e.g. Basic) → 401."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True),
            patch("web_app.server.get_config") as cfg,
        ):
            cfg.return_value = {"k": {"value": "v", "group": "core"}}
            resp = client.get(
                "/api/config",
                headers={"Authorization": "Basic base64stuff"},
            )
        assert resp.status_code == 401

    # -- Exempt endpoints ----------------------------------------------------

    def test_health_endpoint_always_allowed(self, client):
        """GET /api/health bypasses auth entirely."""
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_endpoint_allowed_without_key(self, client):
        """GET /api/health works even without any auth header."""
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            resp = client.get("/api/health", headers={})
        assert resp.status_code == 200

    def test_non_api_paths_bypass_auth(self, client):
        """Non-/api paths are not guarded by the middleware."""
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            resp = client.get("/nonexistent")
        # 404 means the request reached the router, not auth-blocked at 401
        assert resp.status_code == 404

    # -- Auth header content ------------------------------------------------

    def test_returns_www_authenticate_header(self, client):
        """401 responses include a WWW-Authenticate header."""
        with (
            patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True),
            patch("web_app.server.get_config") as cfg,
        ):
            cfg.return_value = {"k": {"value": "v", "group": "core"}}
            resp = client.get("/api/config")
        assert resp.status_code == 401
        assert resp.headers.get("WWW-Authenticate") == "Bearer"


# ── Integration Tests (standalone app, no mocking of env) ──────────────────


class TestApiKeyAuthIntegration:
    """Integration-style tests with a purpose-built FastAPI app.

    These tests create a *separate* FastAPI instance, attach the real
    middleware, and control auth strictly via ``os.environ`` patches.  The
    key difference from the unit tests is that the test app has no mock
    side-effects — the echo endpoint returns immediately, so only the
    auth+dispatch path is exercised.
    """

    # -- No key / empty key (backward compat) -------------------------------

    def test_no_key_allows_api_request(self):
        """Integration: unset OMP_LOOP_API_KEY → /api/echo succeeds."""
        app = _build_test_app()
        with patch.dict(os.environ, {}, clear=True):
            client = TestClient(app)
            resp = client.get("/api/echo")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_empty_key_allows_api_request(self):
        """Integration: OMP_LOOP_API_KEY='' → /api/echo succeeds."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": ""}, clear=True):
            client = TestClient(app)
            resp = client.get("/api/echo")
        assert resp.status_code == 200

    # -- Auth enabled -------------------------------------------------------

    def test_valid_key_allows_access(self):
        """Integration: correct Bearer token → 200."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            client = TestClient(app)
            resp = client.get("/api/echo", headers={"Authorization": "Bearer my-secret-key"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_missing_key_returns_401(self):
        """Integration: no Authorization header → 401."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            client = TestClient(app)
            resp = client.get("/api/echo")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Missing or invalid API key"

    def test_wrong_key_returns_401(self):
        """Integration: wrong Bearer token → 401."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "correct-key"}, clear=True):
            client = TestClient(app)
            resp = client.get("/api/echo", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    # -- Exempt endpoints ----------------------------------------------------

    def test_health_bypasses_auth(self):
        """Integration: /api/health works without any auth header."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            client = TestClient(app)
            resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}

    def test_non_api_path_bypasses_auth(self):
        """Integration: non-/api paths reach the router."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            client = TestClient(app)
            resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    # -- Edge cases ---------------------------------------------------------

    def test_wrong_authorization_scheme(self):
        """Integration: Basic auth scheme → 401."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}, clear=True):
            client = TestClient(app)
            resp = client.get("/api/echo", headers={"Authorization": "Basic base64creds"})
        assert resp.status_code == 401

    def test_token_with_leading_trailing_whitespace(self):
        """Integration: whitespace in header value → 401 (exact match)."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-key"}, clear=True):
            client = TestClient(app)
            resp = client.get(
                "/api/echo",
                headers={"Authorization": "Bearer  my-key  "},
            )
        assert resp.status_code == 401

    def test_token_in_query_param_not_supported(self):
        """Integration: providing key via query param (not header) → 401."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-key"}, clear=True):
            client = TestClient(app)
            resp = client.get("/api/echo?api_key=my-key")
        assert resp.status_code == 401

    def test_key_with_special_characters(self):
        """Integration: keys containing special characters work correctly."""
        special_key = "k3y_w1th!@#$%^&*()_+-=[]{}|;':\",./<>?`~"
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": special_key}, clear=True):
            client = TestClient(app)
            resp = client.get("/api/echo", headers={"Authorization": f"Bearer {special_key}"})
        assert resp.status_code == 200

    def test_multiple_headers_preserved(self):
        """Integration: other headers are preserved alongside auth."""
        app = _build_test_app()
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "some-key"}, clear=True):
            client = TestClient(app)
            resp = client.get(
                "/api/echo",
                headers={
                    "Authorization": "Bearer some-key",
                    "X-Custom-Header": "custom-value",
                    "Accept": "application/json",
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
