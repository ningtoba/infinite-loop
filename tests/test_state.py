"""Tests for pi_loop.state — ledger loading and creation."""

from unittest.mock import patch

from pi_loop.state import _version_detail, load_or_create_ledger


class TestVersionDetail:
    def test_contains_version_string(self):
        """_version_detail returns a string containing the version."""
        result = _version_detail()
        assert isinstance(result, str)
        assert "v" in result


class TestLoadOrCreateLedger:
    def _mock_state(self, **overrides):
        base = {
            "goal": "Test goal",
            "initial_command": "Test goal",
            "iterations": [],
            "total_iterations": 0,
            "status": "running",
            "last_updated": "2025-01-01T00:00:00",
            "stats": {},
            "error_type_counts": {
                "timeout": 0,
                "network": 0,
                "schema": 0,
                "unknown": 0,
                "heartbeat": 0,
            },
            "mitigations": {
                "timeout_increased": False,
                "cooldown_elevated": False,
                "force_subprocess": False,
                "reduced_workers": False,
                "mitigation_level": 0,
                "last_applied": "",
                "actions": [],
            },
            "goals_completed": {},
        }
        base.update(overrides)
        return base

    def test_creates_fresh_ledger(self):
        """load_or_create_ledger creates a fresh ledger when none exists."""
        with patch("pi_loop.state.read_ledger", return_value=None):
            result = load_or_create_ledger("my goal", "some context")
        assert result["initial_command"] == "my goal"
        assert result["initial_context"] == "some context"
        assert result["status"] == "running"
        assert result["version"] == 11
        assert result["total_iterations"] == 0
        assert result["stats"]["success_count"] == 0

    def test_removes_stale_sentinel(self):
        """load_or_create_ledger removes stale sentinel file."""
        with (
            patch("pi_loop.state.read_ledger", return_value=None),
            patch("os.path.exists", return_value=True),
            patch("os.remove") as mock_remove,
        ):
            load_or_create_ledger("goal", "ctx", sentinel_path="/tmp/stale-sentinel")
        mock_remove.assert_called_with("/tmp/stale-sentinel")

    def test_resumes_existing_ledger(self):
        """load_or_create_ledger resumes existing ledger with same goal."""
        existing = self._mock_state(initial_command="same goal", total_iterations=5)
        with (
            patch("pi_loop.state.read_ledger", return_value=existing),
            patch("pi_loop.state.write_ledger") as mock_write,
        ):
            result = load_or_create_ledger("same goal", "")
        assert result["total_iterations"] == 5
        assert result["status"] == "running"
        mock_write.assert_called_once()

    def test_starts_fresh_with_different_goal(self):
        """load_or_create_ledger starts fresh when goal differs."""
        existing = self._mock_state(initial_command="old goal")
        with patch("pi_loop.state.read_ledger", return_value=existing):
            result = load_or_create_ledger("new goal", "ctx")
        assert result["initial_command"] == "new goal"
        assert result["total_iterations"] == 0

    def test_adds_missing_error_type_counts_on_resume(self):
        """load_or_create_ledger adds missing error_type_counts on resume."""
        existing = {"initial_command": "goal", "total_iterations": 0, "status": "running"}
        with patch("pi_loop.state.read_ledger", return_value=existing), patch("pi_loop.state.write_ledger"):
            result = load_or_create_ledger("goal", "")
        assert "error_type_counts" in result
        assert result["error_type_counts"]["timeout"] == 0

    def test_adds_missing_mitigations_on_resume(self):
        """load_or_create_ledger adds missing mitigations on resume."""
        existing = {"initial_command": "goal", "total_iterations": 0, "status": "running"}
        with patch("pi_loop.state.read_ledger", return_value=existing), patch("pi_loop.state.write_ledger"):
            result = load_or_create_ledger("goal", "")
        assert "mitigations" in result
        assert result["mitigations"]["mitigation_level"] == 0

    def test_reset_goals_clears_goals_completed(self):
        """load_or_create_ledger with reset_goals=True clears goals_completed."""
        existing = self._mock_state(goals_completed={"goal1": True, "goal2": True})
        existing["initial_command"] = "goal"
        with patch("pi_loop.state.read_ledger", return_value=existing), patch("pi_loop.state.write_ledger"):
            result = load_or_create_ledger("goal", "", reset_goals=True)
        assert result["goals_completed"] == {}

    def test_recovers_stale_pending_iteration(self):
        """load_or_create_ledger recovers stale pending_iteration (>=300s old)."""
        old_ts = "2025-01-01T00:00:00"
        existing = self._mock_state(
            initial_command="goal",
            pending_iteration={"n": 3, "started_at": old_ts},
        )
        with patch("pi_loop.state.read_ledger", return_value=existing), patch("pi_loop.state.write_ledger"):
            result = load_or_create_ledger("goal", "")
        assert len(result["iterations"]) == 1
        assert result["iterations"][0]["n"] == 3
        assert result["iterations"][0]["error"] == "agent_crashed"
        assert "RECOVERED" in result["iterations"][0]["summary"]
        assert "pending_iteration" not in result

    def test_fresh_ledger_has_error_type_counts(self):
        """A fresh ledger has all error type counters initialized."""
        with patch("pi_loop.state.read_ledger", return_value=None):
            result = load_or_create_ledger("goal", "ctx")
        expected_keys = {"timeout", "network", "schema", "unknown", "heartbeat"}
        assert set(result["error_type_counts"].keys()) == expected_keys

    def test_fresh_ledger_has_mitigations_block(self):
        """A fresh ledger has the mitigations block initialized."""
        with patch("pi_loop.state.read_ledger", return_value=None):
            result = load_or_create_ledger("goal", "ctx")
        assert result["mitigations"]["mitigation_level"] == 0
        assert result["mitigations"]["actions"] == []

    def test_fresh_ledger_has_goals_completed(self):
        """A fresh ledger has an empty goals_completed dict."""
        with patch("pi_loop.state.read_ledger", return_value=None):
            result = load_or_create_ledger("goal", "ctx")
        assert result["goals_completed"] == {}
