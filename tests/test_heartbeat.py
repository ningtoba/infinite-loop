"""Tests for omp_loop.heartbeat — heartbeat helpers for session self-healing."""

from unittest.mock import patch

from omp_loop.heartbeat import _cleanup_stale_heartbeats


class TestCleanupStaleHeartbeats:
    def test_removes_matching_files(self, tmp_path):
        """_cleanup_stale_heartbeats removes heartbeat files."""
        with (
            patch("omp_loop.heartbeat.HEARTBEAT_DIR", str(tmp_path)),
            patch("omp_loop.heartbeat.HEARTBEAT_PREFIX", "hb-"),
        ):
            (tmp_path / "hb-123").write_text("data")
            (tmp_path / "hb-456").write_text("data")
            (tmp_path / "other").write_text("data")
            _cleanup_stale_heartbeats()
            assert not (tmp_path / "hb-123").exists()
            assert not (tmp_path / "hb-456").exists()
            assert (tmp_path / "other").exists()
