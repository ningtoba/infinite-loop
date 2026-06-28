"""Tests for web_app.server — FastAPI web server for pi-loop Web UI."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from web_app.server import app


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


class TestIndex:
    def test_returns_html_when_static_exists(self, client):
        """GET / returns HTML when static/index.html exists."""
        mock_html = "<h1>pi-loop Web UI</h1>"
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
        assert resp.json()["success"] is True

    def test_start_failure(self, client):
        """POST /api/loop/start handles start failure."""
        mock_mgr = MagicMock()
        mock_mgr.start = AsyncMock(return_value={"success": False, "error": "already running"})
        with patch("web_app.server.get_loop_manager", return_value=mock_mgr):
            resp = client.post("/api/loop/start")
        assert resp.status_code == 200
        assert resp.json()["success"] == False


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


class TestValidateConfig:
    def test_validates_required_fields(self):
        """validate_config checks required fields."""
        from web_app.config_manager import validate_config

        result = validate_config({"INFINITE_LOOP_GOAL": ""})
        assert result.get("valid") == False
        errors = result.get("errors", [])
        assert isinstance(errors, list) and len(errors) > 0

    def test_valid_config_passes(self):
        """validate_config passes with valid config."""
        from web_app.config_manager import validate_config

        result = validate_config({"INFINITE_LOOP_GOAL": "my goal"})
        assert result.get("valid") == True
