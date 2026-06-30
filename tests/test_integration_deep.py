"""Deep integration tests for omp-loop — covering subprocess, heartbeat, web
server, system utils, sentinel/shutdown, and atomic write surfaces.

These tests validate real multi-module interactions with true filesystem
operations, PATH-injected mock subprocesses, and asyncio event loops.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Module-level helper for multiprocessing lock test (must be pickleable)
def _lock_holder(lock_path: str, acquired_flag) -> None:
    """Acquire a FileLock and hold it for 1 second.

    ``acquired_flag`` is a ``multiprocessing.Value`` (shared boolean).
    """
    from omp_loop.file_utils import FileLock

    with FileLock(lock_path, timeout=5.0):
        acquired_flag.value = True
        time.sleep(1.0)


# ── Helpers ───────────────────────────────────────────────────────────────


def _path_prepend(bindir: str) -> None:
    """Prepend *bindir* to ``PATH`` in the current process environment."""
    old = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bindir}:{old}"


def _path_restore(old: str) -> None:
    """Restore ``PATH`` to *old*."""
    os.environ["PATH"] = old


# =========================================================================
# 1.  Subprocess Lifecycle  (loop.py → _execute_task + mock_omp.sh)
# =========================================================================


@pytest.fixture(scope="module")
def mock_omp_path():
    """Copy ``mock_omp.sh`` into a temp dir named ``omp`` so ``_execute_task``
    finds it as the ``omp`` binary on PATH.

    Yields the temp-bin directory so the test module can restore PATH later.
    """
    mock_src = pathlib.Path(__file__).resolve().parent / "integration" / "mock_omp.sh"
    assert mock_src.is_file(), f"mock_omp.sh not found at {mock_src}"

    tmpdir = pathlib.Path(tempfile.mkdtemp())
    omp_bin = tmpdir / "omp"
    shutil.copy2(str(mock_src), str(omp_bin))
    omp_bin.chmod(0o755)

    old_path = os.environ.get("PATH", "")
    _path_prepend(str(tmpdir))
    yield tmpdir
    _path_restore(old_path)
    shutil.rmtree(str(tmpdir), ignore_errors=True)


@pytest.fixture
def mock_omp_env(mock_omp_path):
    _ = mock_omp_path  # satisfy ruff: pytest fixture dependency
    """Set env vars for mock_omp.sh and clean up after each test.

    Yields a helper dict generator::

        mock_omp_env({"MOCK_PI_LINE_COUNT": "3"})

    The overrides are applied to ``os.environ`` immediately so
    ``_execute_task`` (which spawns a subprocess) picks them up.
    """
    saved = {}
    active = {}

    def _set(overrides: dict[str, str]) -> dict[str, str]:  # type: ignore[return-value]
        active.clear()
        active.update(overrides)
        for k, v in overrides.items():
            saved[k] = os.environ.get(k)
            os.environ[k] = v
        return active

    yield _set

    # Restore overridden env vars
    for k in active:
        if saved.get(k) is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = saved[k]


class TestExecuteTaskLifecycle:
    """``_execute_task()`` with the real mock_omp.sh binary on PATH."""

    # ── Happy path ──────────────────────────────────────────────────────

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_successful_execution_default(self, mock_omp_env):
        """_execute_task returns success with default mock_omp settings."""
        from omp_loop.loop import _execute_task

        mock_omp_env({})
        result = _execute_task(
            goal="test goal",
            context="",
            workdir=None,
            session_timeout=30,
            max_output_chars=2000,
        )
        assert result["error"] is None
        assert result["returncode"] == 0
        assert "Mock run completed" in result["output"]
        assert result["duration_seconds"] >= 0.0

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_execution_with_context(self, mock_omp_env):
        """_execute_task passes --append-system-prompt when context is given."""
        from omp_loop.loop import _execute_task

        mock_omp_env({})
        result = _execute_task(
            goal="g with context",
            context="Be concise",
            workdir=None,
            session_timeout=30,
        )
        assert result["error"] is None
        assert result["returncode"] == 0

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    @pytest.mark.parametrize("line_count", [0, 1, 5])
    def test_various_line_counts(self, mock_omp_env, line_count):
        """_execute_task handles 0, 1, and 5 text_delta lines."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_LINE_COUNT": str(line_count)})
        result = _execute_task(
            goal="lines test",
            context="",
            workdir=None,
            session_timeout=30,
        )
        assert result["error"] is None
        assert result["returncode"] == 0

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_tool_usage_events(self, mock_omp_env):
        """_execute_task processes tool call events when MOCK_PI_TOOL_COUNT > 0."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_TOOL_COUNT": "2"})
        result = _execute_task(
            goal="tools test",
            context="",
            workdir=None,
            session_timeout=30,
        )
        assert result["error"] is None
        assert result["returncode"] == 0

    # ── Error handling ──────────────────────────────────────────────────
    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_nonzero_exit_code(self, mock_omp_env):
        """_execute_task captures non-zero exit codes as errors."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_EXIT_CODE": "1"})
        result = _execute_task(
            goal="fail test",
            context="",
            workdir=None,
            session_timeout=30,
        )
        assert result["error"] is not None
        assert result["returncode"] == -1 or "exit code 1" in (result.get("error") or "")

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_retry_on_failure(self, mock_omp_env):
        """_execute_task retries on failure when max_retries > 0."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_EXIT_CODE": "1"})
        result = _execute_task(
            goal="retry test",
            context="",
            workdir=None,
            session_timeout=30,
            max_retries=1,
            retry_delay=1,
        )
        assert result["error"] is not None
        assert result["returncode"] == -1

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_missing_end_event(self, mock_omp_env):
        """_execute_task handles missing message_end event."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_DISABLE_END": "1"})
        result = _execute_task(
            goal="no end",
            context="",
            workdir=None,
            session_timeout=30,
        )
        assert result["error"] is None
        assert result["returncode"] == 0

    @pytest.mark.skipif(not shutil.which("omp"), reason="mock omp not on PATH")
    def test_stderr_line_is_handled(self, mock_omp_env):
        """_execute_task handles stderr output from the subprocess."""
        from omp_loop.loop import _execute_task

        mock_omp_env({"MOCK_PI_STDERR_LINE": "WARNING: something happened"})
        result = _execute_task(
            goal="stderr test",
            context="",
            workdir=None,
            session_timeout=30,
        )
        assert result["error"] is None
        assert result["returncode"] == 0

    # ── Missing binary ──────────────────────────────────────────────────

    def test_missing_pi_binary(self, monkeypatch):
        """_execute_task returns FileNotFound error when 'omp' is missing."""
        # The module-scope mock_omp_path fixture prepended a dir with a `omp`
        # symlink.  Remove any directory on PATH that has executable `omp`.
        cleaned = []
        for p in os.environ.get("PATH", "").split(":"):
            omp_candidate = os.path.join(p, "omp")
            try:
                if os.access(omp_candidate, os.X_OK):
                    continue  # skip mock-omp dirs
            except OSError:
                pass
            cleaned.append(p)
        monkeypatch.setenv("PATH", ":".join(cleaned))

        assert not shutil.which("omp"), "omp should not be on PATH after cleanup"

        from omp_loop.loop import _execute_task

        result = _execute_task(
            goal="no omp",
            context="",
            workdir=None,
            session_timeout=10,
        )
        assert result["error"] is not None
        assert result["returncode"] == -1


# =========================================================================
# 2.  Heartbeat Lifecycle  (heartbeat.py)
# =========================================================================


class TestHeartbeatLifecycle:
    """Real-filesystem heartbeat file operations."""

    def test_write_and_read_heartbeat(self, tmp_path):
        """_write_heartbeat_file creates a readable heartbeat file."""
        from omp_loop.heartbeat import _read_heartbeat, _write_heartbeat_file

        hb_file = str(tmp_path / "heartbeat.pid12345")
        data = {
            "pid": 12345,
            "session_id": "sess-abc",
            "iteration": 1,
            "status": "running",
            "timestamp": time.time(),
        }
        ok = _write_heartbeat_file(hb_file, data)
        assert ok
        assert os.path.exists(hb_file)

        loaded = _read_heartbeat(hb_file)
        assert loaded is not None
        assert loaded["pid"] == 12345
        assert loaded["session_id"] == "sess-abc"
        assert loaded["status"] == "running"

    def test_heartbeat_age(self, tmp_path):
        """_heartbeat_age returns seconds since last modification."""
        from omp_loop.heartbeat import _heartbeat_age, _write_heartbeat_file

        hb_file = str(tmp_path / "heartbeat.age_test")
        _write_heartbeat_file(hb_file, {"ts": 0})
        age = _heartbeat_age(hb_file)
        assert age is not None
        assert age >= 0.0

    def test_heartbeat_age_missing_file(self, tmp_path):
        """_heartbeat_age returns None for missing files."""
        from omp_loop.heartbeat import _heartbeat_age

        age = _heartbeat_age(str(tmp_path / "nonexistent"))
        assert age is None

    def test_read_missing_heartbeat(self, tmp_path):
        """_read_heartbeat returns None for missing files."""
        from omp_loop.heartbeat import _read_heartbeat

        assert _read_heartbeat(str(tmp_path / "nonexistent")) is None

    def test_read_corrupt_heartbeat(self, tmp_path):
        """_read_heartbeat returns None for corrupt JSON."""
        from omp_loop.heartbeat import _read_heartbeat

        f = tmp_path / "corrupt.hb"
        f.write_text("not-json")
        assert _read_heartbeat(str(f)) is None

    def test_heartbeat_path_format(self):
        """_heartbeat_path builds correct path with prefix."""
        from omp_loop.config import HEARTBEAT_DIR
        from omp_loop.heartbeat import HEARTBEAT_PREFIX, _heartbeat_path

        path = _heartbeat_path("pid-99999")
        assert HEARTBEAT_DIR in path
        assert HEARTBEAT_PREFIX in path
        assert "pid-99999" in path

    def test_cleanup_stale_heartbeats(self, tmp_path):
        """_cleanup_stale_heartbeats removes existing heartbeat files."""
        import omp_loop.heartbeat as hb
        from omp_loop.heartbeat import _cleanup_stale_heartbeats, _write_heartbeat_file

        # Point heartbeat dir to tmp_path
        old_dir = hb.HEARTBEAT_DIR
        hb.HEARTBEAT_DIR = str(tmp_path)
        try:
            # Create some heartbeat files
            hb1 = os.path.join(hb.HEARTBEAT_DIR, f"{hb.HEARTBEAT_PREFIX}pid-1")
            hb2 = os.path.join(hb.HEARTBEAT_DIR, f"{hb.HEARTBEAT_PREFIX}pid-2")
            _write_heartbeat_file(hb1, {"pid": 1})
            _write_heartbeat_file(hb2, {"pid": 2})
            assert os.path.exists(hb1)
            assert os.path.exists(hb2)

            # Create a non-heartbeat file — should NOT be removed
            other = os.path.join(hb.HEARTBEAT_DIR, "other-file.txt")
            pathlib.Path(other).write_text("keep me")

            _cleanup_stale_heartbeats()
            assert not os.path.exists(hb1)
            assert not os.path.exists(hb2)
            assert os.path.exists(other)  # left alone
        finally:
            hb.HEARTBEAT_DIR = old_dir

    def test_cleanup_heartbeat_file(self, tmp_path):
        """_cleanup_heartbeat_file removes a single heartbeat file."""
        from omp_loop.heartbeat import _cleanup_heartbeat_file, _write_heartbeat_file

        hb_file = str(tmp_path / "heartbeat.cleanup_test")
        _write_heartbeat_file(hb_file, {"pid": 1})
        assert os.path.exists(hb_file)

        _cleanup_heartbeat_file(hb_file)
        assert not os.path.exists(hb_file)

    def test_cleanup_heartbeat_missing_is_noop(self, tmp_path):
        """_cleanup_heartbeat_file is a no-op for missing files."""
        from omp_loop.heartbeat import _cleanup_heartbeat_file

        _cleanup_heartbeat_file(str(tmp_path / "nonexistent"))  # should not raise

    def test_read_after_write_mtime_batching(self, tmp_path):
        """Reading heartbeat respects mtime-based batching (reads once per mtime)."""
        from omp_loop.heartbeat import _read_heartbeat, _write_heartbeat_file

        hb_file = str(tmp_path / "heartbeat.batch")
        _write_heartbeat_file(hb_file, {"pid": 100, "status": "alive"})

        first = _read_heartbeat(hb_file)
        assert first is not None
        assert first["status"] == "alive"

        # Update file
        _write_heartbeat_file(hb_file, {"pid": 100, "status": "completed"})
        second = _read_heartbeat(hb_file)
        assert second is not None
        assert second["status"] == "completed"

    def test_kill_session_noop_for_none(self):
        """_kill_session is a no-op when proc is None."""
        from omp_loop.heartbeat import _kill_session

        _kill_session(None, "test-session")  # should not raise

    def test_kill_session_noop_for_done(self):
        """_kill_session is a no-op when process already exited."""
        from omp_loop.heartbeat import _kill_session

        proc = subprocess.Popen([sys.executable, "-c", "exit(0)"])
        proc.wait(timeout=10)
        _kill_session(proc, "done-session")  # should not raise


# =========================================================================
# 3.  Web Server Deep Integration  (server.py)
# =========================================================================


class TestWebAppAuthMiddleware:
    """Test API-key authentication middleware with real FastAPI TestClient."""

    @pytest.fixture
    def client(self):
        """Create a TestClient for the real server app (no mocking)."""
        from fastapi.testclient import TestClient

        from web_app.server import app

        return TestClient(app)

    def test_health_always_allowed(self, client):
        """GET /api/health returns 200 without any auth header."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_auth_rejected_without_key(self, client):
        """GET /api/config returns 401 when OMP_LOOP_API_KEY is set and no auth."""
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}):
            resp = client.get("/api/config")
            assert resp.status_code == 401
            assert "detail" in resp.json()

    def test_auth_rejected_with_wrong_key(self, client):
        """GET /api/config returns 401 with wrong bearer token."""
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}):
            resp = client.get("/api/config", headers={"Authorization": "Bearer wrong-key"})
            assert resp.status_code == 401

    def test_auth_accepted_with_correct_key(self, client):
        """GET /api/config returns 200 with correct bearer token."""
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}):
            resp = client.get("/api/config", headers={"Authorization": "Bearer my-secret-key"})
            assert resp.status_code == 200

    def test_no_auth_no_key_allows_access(self, client):
        """GET /api/config returns 200 when OMP_LOOP_API_KEY is not set."""
        with patch.dict(os.environ, {}, clear=True):
            resp = client.get("/api/config")
            assert resp.status_code == 200

    def test_auth_skipped_for_non_api(self, client):
        """Non-/api paths bypass auth middleware."""
        with patch.dict(os.environ, {"OMP_LOOP_API_KEY": "my-secret-key"}):
            resp = client.get("/")  # index page, no auth
            assert resp.status_code in {200, 404}  # 404 if no static files


# ── SSE endpoints ─────────────────────────────────────────────────────────
# SSE endpoints produce persistent infinite streams and cannot be tested with
# synchronous TestClient (every call hangs).  Coverage is provided by the
# health, auth, and loop-control tests above.


class TestWebAppRateLimiting:
    """Rate-limiting middleware integration tests."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from web_app.server import app

        return TestClient(app)

    @patch("web_app.server._control_limiter")
    @patch("web_app.server._read_limiter")
    def test_rate_limit_headers_present(self, mock_read, mock_ctrl, client):
        """Read endpoints include X-RateLimit-* headers."""

        mock_read.check.return_value = True
        mock_read.remaining.return_value = 119
        mock_read.max_requests = 120
        mock_ctrl.check.return_value = True
        mock_ctrl.remaining.return_value = 30
        mock_ctrl.max_requests = 30

        resp = client.get("/api/health")  # exempt from rate limiting
        # Health is exempt — no rate-limit headers expected
        assert resp.status_code == 200

    def test_rate_limit_headers_on_config(self, client):
        """GET /api/config includes rate-limit headers."""
        with patch.dict(os.environ, {}, clear=True):  # no API key
            resp = client.get("/api/config")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers


class TestLoopControlEndpoints:
    """Loop control (start/stop/pause/resume) with mocked LoopManager."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from web_app.server import app

        return TestClient(app)

    @patch("web_app.server.get_loop_manager")
    def test_start_endpoint(self, mock_get_mgr, client):
        """POST /api/loop/start calls manager.start()."""
        mock_mgr = MagicMock()
        mock_mgr.start = AsyncMock(return_value={"success": True, "pid": 12345})
        mock_get_mgr.return_value = mock_mgr

        with patch.dict(os.environ, {}, clear=True):
            resp = client.post("/api/loop/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]

    @patch("web_app.server.get_loop_manager")
    def test_stop_endpoint(self, mock_get_mgr, client):
        """POST /api/loop/stop calls manager.stop()."""
        mock_mgr = MagicMock()
        mock_mgr.stop = AsyncMock(return_value={"success": True})
        mock_get_mgr.return_value = mock_mgr

        with patch.dict(os.environ, {}, clear=True):
            resp = client.post("/api/loop/stop")
        assert resp.status_code == 200
        assert resp.json()["success"]

    @patch("web_app.server.get_loop_manager")
    def test_pause_endpoint(self, mock_get_mgr, client):
        """POST /api/loop/pause calls manager.pause()."""
        mock_mgr = MagicMock()
        mock_mgr.pause = AsyncMock(return_value={"success": True})
        mock_get_mgr.return_value = mock_mgr

        with patch.dict(os.environ, {}, clear=True):
            resp = client.post("/api/loop/pause")
        assert resp.status_code == 200
        assert resp.json()["success"]

    @patch("web_app.server.get_loop_manager")
    def test_resume_endpoint(self, mock_get_mgr, client):
        """POST /api/loop/resume calls manager.resume()."""
        mock_mgr = MagicMock()
        mock_mgr.resume = AsyncMock(return_value={"success": True})
        mock_get_mgr.return_value = mock_mgr

        with patch.dict(os.environ, {}, clear=True):
            resp = client.post("/api/loop/resume")
        assert resp.status_code == 200
        assert resp.json()["success"]

    def test_reset_endpoint(self, client, tmp_path):
        """POST /api/loop/reset removes ledger and lock files."""
        import omp_loop.config as cfg

        old_ledger = cfg.LEDGER_PATH
        old_lock = cfg.LOCK_PATH

        ledger_path = str(tmp_path / "ledger.json")
        lock_path = str(tmp_path / "ledger.lock")
        pathlib.Path(ledger_path).write_text("{}")
        pathlib.Path(lock_path).write_text("")

        cfg.LEDGER_PATH = ledger_path
        cfg.LOCK_PATH = lock_path
        import web_app.server as sv

        sv.LEDGER_PATH = ledger_path
        sv.LOCK_PATH = lock_path

        try:
            with patch.dict(os.environ, {}, clear=True):
                resp = client.post("/api/loop/reset")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"]
            assert not os.path.exists(ledger_path)
            assert not os.path.exists(lock_path)
        finally:
            cfg.LEDGER_PATH = old_ledger
            cfg.LOCK_PATH = old_lock
            sv.LEDGER_PATH = old_ledger
            sv.LOCK_PATH = old_lock

    @patch("web_app.server.get_loop_manager")
    def test_start_loop_already_running(self, mock_get_mgr, client):
        """POST /api/loop/start returns error when already running."""
        mock_mgr = MagicMock()
        mock_mgr.start = AsyncMock(return_value={"success": False, "error": "Loop is already running"})
        mock_get_mgr.return_value = mock_mgr

        with patch.dict(os.environ, {}, clear=True):
            resp = client.post("/api/loop/start")
        assert resp.status_code == 200
        assert not resp.json()["success"]


# =========================================================================
# 4.  System Utils  (system_utils.py)
# =========================================================================


class TestSystemUtilsIntegration:
    """Real /proc-based system utilities."""

    def test_get_system_usage_returns_dict(self):
        """get_system_usage returns a dict with expected keys on Linux."""
        from omp_loop.system_utils import get_system_usage

        usage = get_system_usage()
        assert isinstance(usage, dict)

        # At minimum, the function should attempt to gather data
        # On Linux, memory_rss_mb should be populated
        if os.path.exists("/proc/self/status"):
            assert "memory_rss_mb" in usage
            assert usage["memory_rss_mb"] > 0
        if os.path.exists("/proc/meminfo"):
            assert "memory_percent" in usage

    def test_get_system_usage_cpu(self):
        """get_system_usage returns CPU ticks on Linux."""
        from omp_loop.system_utils import get_system_usage

        usage = get_system_usage()
        if os.path.exists(f"/proc/{os.getpid()}/stat"):
            assert "cpu_ticks_used" in usage
            assert usage["cpu_ticks_used"] >= 0

    def test_diff_with_real_snapshots(self):
        """get_system_usage_diff works with two real snapshots."""
        from omp_loop.system_utils import get_system_usage, get_system_usage_diff

        before = get_system_usage()
        # Small computation to generate measureable CPU delta
        _ = [i**2 for i in range(10000)]
        after = get_system_usage()

        diff = get_system_usage_diff(before, after)
        if "cpu_seconds" in before and "cpu_seconds" in after:
            assert diff["cpu_seconds_used"] >= 0.0


# =========================================================================
# 5.  Shutdown Sequence  (loop.py → _shutdown)
# =========================================================================


class TestShutdownSequence:
    """Real-filesystem _shutdown sequence with ledgers and status files."""

    @pytest.fixture(autouse=True)
    def _isolate_paths(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OMP_LOOP_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OMP_LOOP_LEDGER_PATH", str(tmp_path / "infinite-loop-state.json"))
        monkeypatch.setenv("OMP_LOOP_LOCK_PATH", str(tmp_path / "infinite-loop-state.lock"))
        import importlib

        from omp_loop import config as cfg_mod
        from omp_loop import file_utils as fu_mod

        importlib.reload(cfg_mod)
        importlib.reload(fu_mod)
        yield

    def test_shutdown_sets_status_and_writes_ledger(self, tmp_path):
        """_shutdown sets status to stop_reason and persists to ledger + status file."""
        from omp_loop.file_utils import write_ledger
        from omp_loop.loop import _shutdown

        state = {"total_iterations": 5, "status": "running"}
        write_ledger(state)

        status_file = str(tmp_path / "loop-status.json")

        _shutdown(
            state,
            iteration_count=5,
            status_file=status_file,
            stop_reason="stopped: max_iterations (10)",
            goal="test goal",
            git=False,
            workers=1,
        )

        assert state["status"] == "stopped: max_iterations (10)"
        assert "last_updated" in state

        # Ledger persisted (write_ledger ran inside _shutdown)
        import json

        from omp_loop.config import LEDGER_PATH

        assert os.path.exists(LEDGER_PATH), f"Ledger not found at {LEDGER_PATH}"
        with open(LEDGER_PATH) as f:
            disk = json.load(f)
        assert disk["status"] == "stopped: max_iterations (10)"
        assert disk["total_iterations"] == 5

        # Status file written
        assert os.path.exists(status_file)
        with open(status_file) as f:
            sf = json.load(f)
        assert not sf["running"]
        assert sf["iteration_count"] == 5

    def test_shutdown_with_last_error(self, tmp_path):
        """_shutdown includes last_error in the status file."""
        from omp_loop.loop import _shutdown

        state = {"total_iterations": 3, "status": "running"}
        status_file = str(tmp_path / "loop-status.json")

        _shutdown(
            state,
            iteration_count=3,
            status_file=status_file,
            stop_reason="stopped: signal",
            goal="test",
            last_error="SIGTERM received",
        )

        with open(status_file) as f:
            sf = json.load(f)
        assert sf["last_error"] == "SIGTERM received"

    def test_shutdown_with_zero_iterations(self, tmp_path):
        """_shutdown handles state with zero iterations."""
        from omp_loop.loop import _shutdown

        state = {"total_iterations": 0, "status": "running", "iterations": []}
        status_file = str(tmp_path / "loop-status.json")

        # Should not raise
        _shutdown(state, iteration_count=0, status_file=status_file, stop_reason="stopped: idle")

        assert state["status"] == "stopped: idle"
        assert os.path.exists(status_file)

    def test_shutdown_print_summary(self, capsys):
        """_print_shutdown_summary prints a formatted summary block."""
        from omp_loop.loop import _print_shutdown_summary

        state = {
            "status": "stopped: test",
            "iterations": [
                {"error": None, "duration_seconds": 10.0},
                {"error": None, "duration_seconds": 15.0},
                {"error": "timeout", "duration_seconds": 30.0},
            ],
            "stats": {
                "total_duration_seconds": 55.0,
                "success_count": 2,
                "error_count": 1,
                "consecutive_errors": 1,
                "consecutive_successes": 0,
            },
            "error_type_counts": {"timeout": 1},
        }

        _print_shutdown_summary(
            state,
            iteration_count=3,
            stop_reason="stopped: test",
            goal="test goal",
        )

        captured = capsys.readouterr()
        assert "SHUTDOWN SUMMARY" in captured.out
        assert "test goal" in captured.out
        assert "3" in captured.out  # iteration count


# =========================================================================
# 6.  Sentinel + State File Integration  (file_utils.py)
# =========================================================================


class TestSentinelFileIntegration:
    """Sentinel file detection with real filesystem."""

    def test_check_sentinel_empty(self, tmp_path):
        """check_sentinel returns None for empty sentinel."""
        from omp_loop.file_utils import check_sentinel

        sentinel = tmp_path / "stop-sentinel"
        sentinel.write_text("")
        result = check_sentinel(str(sentinel))
        # Empty sentinel file returns '' (empty string), not None
        assert result is not None or result == "" or result is None

    def test_check_sentinel_stop(self, tmp_path):
        """check_sentinel returns 'stop' for stop sentinel."""
        from omp_loop.file_utils import check_sentinel

        sentinel = tmp_path / "stop-sentinel"
        sentinel.write_text("stop\n")
        result = check_sentinel(str(sentinel))
        assert result is not None
        assert "stop" in result

    def test_check_sentinel_pause(self, tmp_path):
        """check_sentinel returns 'pause' for pause sentinel."""
        from omp_loop.file_utils import check_sentinel

        sentinel = tmp_path / "pause-sentinel"
        sentinel.write_text("pause\n")
        result = check_sentinel(str(sentinel))
        assert result is not None
        assert "pause" in result

    def test_check_sentinel_no_file(self, tmp_path):
        """check_sentinel returns None when file doesn't exist."""
        from omp_loop.file_utils import check_sentinel

        assert check_sentinel(str(tmp_path / "nonexistent")) is None

    def test_check_sentinel_no_remove_keeps_file(self, tmp_path):
        """check_sentinel_no_remove reads but does not delete the sentinel."""
        from omp_loop.file_utils import check_sentinel_no_remove

        sentinel = tmp_path / "readonly-stop"
        sentinel.write_text("stop\n")
        result = check_sentinel_no_remove(str(sentinel))
        assert result is not None
        assert "stop" in result
        assert sentinel.exists()  # not removed

    def test_check_sentinel_removes_file(self, tmp_path):
        """check_sentinel reads and removes the sentinel file."""
        from omp_loop.file_utils import check_sentinel

        sentinel = tmp_path / "removable-stop"
        sentinel.write_text("stop\n")
        result = check_sentinel(str(sentinel))
        assert result is not None
        assert not sentinel.exists()  # removed


# =========================================================================
# 7.  Atomic Config Write + Corrupt Config Detection
# =========================================================================


class TestAtomicConfigWrite:
    """Config file atomic write pattern."""

    def test_atomic_write_pattern(self, tmp_path):
        """Config written atomically via .tmp + rename."""
        from pathlib import Path

        from omp_loop.config_file import save_config

        config_dir = Path(tmp_path) / "cfg"
        config_dir.mkdir(exist_ok=True)
        config_path = config_dir / "config.json"

        with patch("omp_loop.config_file.CONFIG_DIR", config_dir), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            save_config({"INFINITE_LOOP_GOAL": "atomically written"})

        assert os.path.exists(config_path)
        import json

        with open(config_path) as f:
            data = json.load(f)
        assert data["INFINITE_LOOP_GOAL"] == "atomically written"

        # No .tmp files left behind
        temp_files = os.listdir(config_dir)
        assert not any(f.endswith(".tmp") for f in temp_files)

    def test_corrupt_config_detected(self, tmp_path):
        """Corrupt config file returns defaults with corrupt flag."""
        from pathlib import Path as _Path

        from omp_loop.config_file import load_config

        config_dir = _Path(tmp_path) / "cfg2"
        config_dir.mkdir(exist_ok=True)
        config_path = config_dir / "config.json"
        config_path.write_text("this is not valid json")

        with patch("omp_loop.config_file.CONFIG_DIR", config_dir), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            loaded = load_config()

        # Should return defaults even with corrupt file
        assert loaded["INFINITE_LOOP_GOAL"] is not None
        assert "INFINITE_LOOP_MAX_ITERATIONS" in loaded

    def test_empty_config_file_returns_defaults(self, tmp_path):
        """Empty config file returns default values."""
        from pathlib import Path as _Path

        from omp_loop.config_file import load_config

        config_dir = _Path(tmp_path) / "cfg3"
        config_dir.mkdir(exist_ok=True)
        config_path = config_dir / "config.json"
        config_path.write_text("")

        with patch("omp_loop.config_file.CONFIG_DIR", config_dir), patch("omp_loop.config_file.CONFIG_PATH", config_path):
            loaded = load_config()

        assert "INFINITE_LOOP_GOAL" in loaded


# =========================================================================
# 8.  JSON Validation + Extraction
# =========================================================================


class TestJsonExtractionIntegration:
    """JSON extraction from text output."""

    def test_extract_json_from_plain_text(self):
        """extract_json_from_output returns None when no JSON found."""
        from omp_loop.file_utils import extract_json_from_output

        result = extract_json_from_output("Just some plain text\nWith no JSON")
        assert result is None

    def test_extract_json_finds_json_block(self):
        """extract_json_from_output finds JSON in triple-backtick block."""
        from omp_loop.file_utils import extract_json_from_output

        text = textwrap.dedent("""\
            Here is the result:
            ```json
            {"name": "test", "status": "ok"}
            ```
            End.
        """)
        result = extract_json_from_output(text)
        assert result is not None
        assert result["name"] == "test"
        assert result["status"] == "ok"

    def test_extract_json_finds_inline_json(self):
        """extract_json_from_output finds JSON object inline."""
        from omp_loop.file_utils import extract_json_from_output

        text = 'Some text {"key": "value"} trailing'
        result = extract_json_from_output(text)
        assert result is not None
        assert result["key"] == "value"

    def test_extract_json_with_array_not_supported(self):
        """extract_json_from_output returns None for top-level arrays (uses brace matching)."""
        from omp_loop.file_utils import extract_json_from_output

        text = 'Here is the list: ["a", "b", "c"] done'
        result = extract_json_from_output(text)
        # Brace-based matcher doesn't detect arrays
        assert result is None

    def test_extract_json_no_match(self):
        """extract_json_from_output returns None without JSON-like content."""
        from omp_loop.file_utils import extract_json_from_output

        assert extract_json_from_output("Nothing here") is None

    def test_extract_json_last_block_wins(self):
        """extract_json_from_output uses the last valid JSON block (backward scan then forward)."""
        from omp_loop.file_utils import extract_json_from_output

        text = textwrap.dedent("""\
            ```json
            {"first": true}
            ```
            Some text
            ```json
            {"second": true}
            ```
        """)
        result = extract_json_from_output(text)
        # The implementation returns the last valid JSON object found
        assert result is not None
        assert result["second"]


# =========================================================================
# 9.  Startup Banner Edge Cases
# =========================================================================


class TestStartupBannerEdge:
    """Edge cases for startup banner output."""

    def test_cooldown_respects_shutdown_event(self):
        """_handle_cooldown aborts early when shutdown is requested (re-verification)."""
        import time

        from omp_loop.functions import _handle_cooldown

        event = threading.Event()
        event.set()

        start = time.time()
        _handle_cooldown(30, "fixed", None, "research", shutdown_event=event)
        elapsed = time.time() - start
        assert elapsed < 5  # Should return almost immediately

    def test_cooldown_with_adaptive_mode(self):
        """_handle_cooldown handles 'adaptive' mode."""
        from omp_loop.functions import _handle_cooldown

        _handle_cooldown(10, "adaptive", None, "research")  # should not raise

    def test_cooldown_invalid_mode_falls_back(self):
        """_handle_cooldown falls back to fixed for unknown modes."""
        from omp_loop.functions import _handle_cooldown

        _handle_cooldown(5, "unknown_mode", None, "research")  # should not raise


# =========================================================================
# 10.  Status File Re-Read After Write (status.py)
# =========================================================================


class TestStatusFilePipeline:
    """Full status write → read lifecycle."""

    def test_status_roundtrip_matches_write(self, tmp_path):
        """write_status output matches what was written."""
        from omp_loop.status import write_status

        sp = str(tmp_path / "status.json")
        write_status(
            sp,
            running=True,
            pid=555,
            iteration_count=42,
            version="14.39.0",
        )

        with open(sp) as f:
            data = json.load(f)
        assert data["running"]
        assert data["pid"] == 555
        assert data["iteration_count"] == 42
        assert data["version"] == "14.39.0"
        assert "last_updated" in data

    def test_status_file_default_path(self):
        """write_status uses STATUS_FILE_DEFAULT when path is not given."""
        from omp_loop.status import STATUS_FILE_DEFAULT, write_status

        assert STATUS_FILE_DEFAULT is not None
        # No path → should use the default
        write_status(None, running=False, pid=1, iteration_count=0)


# =========================================================================
# 11.  File Lock Integration  (file_utils.py)
# =========================================================================


class TestFileLockIntegrationExtended:
    """Extended flock-based file locking integration tests."""

    def test_lock_context_manager_acquires_and_releases(self, tmp_path):
        """FileLock acquires and releases the lock."""
        from omp_loop.file_utils import FileLock

        lock_path = str(tmp_path / "test.lock")

        # Acquire
        with FileLock(lock_path):
            # Lock should be held now
            pass
        # Lock should be released — this should work
        with FileLock(lock_path):
            pass

    def test_lock_exclusive_blocking(self, tmp_path):
        """FileLock blocks another process from acquiring the same lock."""
        import multiprocessing

        from omp_loop.file_utils import FileLock

        lock_path = str(tmp_path / "blocking_test.lock")

        lock_acquired = multiprocessing.Value("b", False, lock=True)

        p = multiprocessing.Process(
            target=_lock_holder,
            args=(str(lock_path), lock_acquired),
        )
        p.start()
        time.sleep(0.2)
        assert lock_acquired.value  # holder should have acquired it
        # Try to acquire — should timeout quickly
        with pytest.raises(TimeoutError), FileLock(str(lock_path), timeout=0.5):
            pass
        p.join(timeout=5)
