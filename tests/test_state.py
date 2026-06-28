"""Tests for state.py — load_or_create_ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch


from hermes_loop.state import load_or_create_ledger

# ===================================================================
# load_or_create_ledger tests
# ===================================================================


class TestLoadOrCreateLedger:
    """Tests for load_or_create_ledger — loads/creates ledger with recovery."""

    def test_no_existing_ledger_creates_new(self):
        """No existing ledger creates a fresh one with defaults."""
        with (
            patch("hermes_loop.state.read_ledger", return_value=None),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
            patch("hermes_loop.state.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(
                2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc
            )
            mock_dt.fromisoformat = datetime.fromisoformat
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
                sentinel_path="",
                reset_goals=False,
            )

        assert result["version"] == 11
        assert result["initial_command"] == "test goal"
        assert result["initial_context"] == "test context"
        assert result["total_iterations"] == 0
        assert result["status"] == "running"
        assert result["iterations"] == []
        assert result["goals_completed"] == {}
        assert "stats" in result
        assert result["stats"]["total_duration_seconds"] == 0.0
        assert "error_type_counts" in result
        assert "mitigations" in result
        assert result["mitigations"]["mitigation_level"] == 0

    def test_resume_existing_ledger_same_goal(self):
        """Existing ledger with same goal resumes."""
        existing = {
            "initial_command": "test goal",
            "total_iterations": 5,
            "iterations": [],
            "status": "running",
            "goals_completed": {"abc": {"status": "completed"}},
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger") as mock_write,
            patch("hermes_loop.state.os.path.exists", return_value=False),
        ):
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
                sentinel_path="",
                reset_goals=False,
            )

        assert mock_write.called
        assert result["status"] == "running"
        assert result["total_iterations"] == 5
        assert result["goals_completed"]["abc"]["status"] == "completed"

    def test_reset_goals_clears_goals_completed(self):
        """reset_goals=True clears goals_completed when resuming."""
        existing = {
            "initial_command": "test goal",
            "total_iterations": 3,
            "iterations": [],
            "status": "running",
            "goals_completed": {"abc": {"status": "completed"}},
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
        ):
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
                sentinel_path="",
                reset_goals=True,
            )

        assert result["goals_completed"] == {}

    def test_different_goal_starts_fresh(self):
        """Existing ledger with different goal starts fresh."""
        existing = {
            "initial_command": "old goal",
            "total_iterations": 10,
            "iterations": [],
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
            patch("hermes_loop.state.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(
                2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc
            )
            mock_dt.fromisoformat = datetime.fromisoformat
            result = load_or_create_ledger(
                goal="new goal",
                context="new context",
                sentinel_path="",
                reset_goals=False,
            )

        assert result["initial_command"] == "new goal"
        assert result["total_iterations"] == 0
        assert result["initial_context"] == "new context"

    def test_sentinel_cleanup(self, tmp_path):
        """Stale sentinel file is removed if it exists."""
        sentinel = tmp_path / "sentinel"
        sentinel.write_text("stop")

        with (
            patch("hermes_loop.state.read_ledger", return_value=None),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=True),
            patch("hermes_loop.state.os.remove") as mock_remove,
            patch("hermes_loop.state.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(
                2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc
            )
            mock_dt.fromisoformat = datetime.fromisoformat
            load_or_create_ledger(
                goal="test goal",
                context="test context",
                sentinel_path=str(sentinel),
            )

        assert mock_remove.called
        assert str(sentinel) == mock_remove.call_args[0][0]

    def test_sentinel_remove_oserror_handled(self, tmp_path):
        """OSError during sentinel removal is handled gracefully."""
        sentinel = tmp_path / "sentinel"

        with (
            patch("hermes_loop.state.read_ledger", return_value=None),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=True),
            patch(
                "hermes_loop.state.os.remove",
                side_effect=OSError("Permission denied"),
            ),
            patch("hermes_loop.state.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(
                2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc
            )
            mock_dt.fromisoformat = datetime.fromisoformat
            # Should not raise
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
                sentinel_path=str(sentinel),
            )
        assert result["initial_command"] == "test goal"

    def test_pending_iteration_stale_recovered(self):
        """Stale pending iteration (>=300s) is recovered as error."""
        start_time = datetime.now(timezone.utc).isoformat()
        existing = {
            "initial_command": "test goal",
            "total_iterations": 0,
            "iterations": [],
            "status": "running",
            "goals_completed": {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "pending_iteration": {
                "n": 1,
                "started_at": start_time,
            },
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
            patch("hermes_loop.state.time") as mock_time,
            patch("hermes_loop.state._recalc_stats") as mock_recalc,
        ):
            mock_time.time.return_value = datetime.now().timestamp() + 301
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
            )

        assert len(result["iterations"]) == 1
        recovered = result["iterations"][0]
        assert recovered["n"] == 1
        assert "[RECOVERED]" in recovered["summary"]
        assert recovered["error"] == "agent_crashed"
        assert result["total_iterations"] == 1
        assert "pending_iteration" not in result
        assert mock_recalc.called

    def test_pending_iteration_recent_not_recovered(self):
        """Recent pending iteration (<300s) is not recovered."""
        start_time = datetime.now(timezone.utc).isoformat()
        existing = {
            "initial_command": "test goal",
            "total_iterations": 0,
            "iterations": [],
            "status": "running",
            "goals_completed": {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "pending_iteration": {
                "n": 1,
                "started_at": start_time,
            },
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
            patch("hermes_loop.state.time") as mock_time,
        ):
            mock_time.time.return_value = (
                datetime.now().timestamp() + 10
            )  # only 10s old
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
            )

        assert len(result["iterations"]) == 0
        assert "pending_iteration" in result

    def test_pending_iteration_missing_started_at(self):
        """Pending iteration without started_at defaults to 0 timestamp."""
        existing = {
            "initial_command": "test goal",
            "total_iterations": 0,
            "iterations": [],
            "status": "running",
            "goals_completed": {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "pending_iteration": {
                "n": 1,
            },
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
            patch("hermes_loop.state.time") as mock_time,
            patch("hermes_loop.state._recalc_stats"),
        ):
            mock_time.time.return_value = 1000000  # big elapsed → stale
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
            )

        # Without started_at, it's 0 elapsed check... actually elapsed = time.time() - 0
        # With time.time()=1000000 and started_ts=0, elapsed = 1000000 >= 300 → recovered
        assert len(result["iterations"]) == 1
        assert result["iterations"][0]["error"] == "agent_crashed"

    def test_pending_iteration_invalid_date_format(self):
        """Invalid date format in started_at falls back to timestamp 0."""
        existing = {
            "initial_command": "test goal",
            "total_iterations": 0,
            "iterations": [],
            "status": "running",
            "goals_completed": {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "pending_iteration": {
                "n": 1,
                "started_at": "not-a-date",
            },
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
            patch("hermes_loop.state.time") as mock_time,
            patch("hermes_loop.state._recalc_stats"),
        ):
            mock_time.time.return_value = 1000000
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
            )

        assert len(result["iterations"]) == 1
        assert result["iterations"][0]["error"] == "agent_crashed"

    def test_missing_goals_completed_added(self):
        """Existing ledger missing goals_completed gets it initialized."""
        existing = {
            "initial_command": "test goal",
            "total_iterations": 0,
            "iterations": [],
            "status": "running",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
        ):
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
            )

        assert "goals_completed" in result
        assert result["goals_completed"] == {}

    def test_missing_error_type_counts_added(self):
        """Existing ledger missing error_type_counts gets initialized."""
        existing = {
            "initial_command": "test goal",
            "total_iterations": 0,
            "iterations": [],
            "status": "running",
            "goals_completed": {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
        ):
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
            )

        assert "error_type_counts" in result
        assert result["error_type_counts"]["timeout"] == 0
        assert result["error_type_counts"]["heartbeat"] == 0

    def test_missing_mitigations_added(self):
        """Existing ledger missing mitigations gets initialized."""
        existing = {
            "initial_command": "test goal",
            "total_iterations": 0,
            "iterations": [],
            "status": "running",
            "goals_completed": {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        with (
            patch("hermes_loop.state.read_ledger", return_value=existing),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
        ):
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
            )

        assert "mitigations" in result
        assert result["mitigations"]["mitigation_level"] == 0
        assert result["mitigations"]["actions"] == []

    def test_new_ledger_defaults_include_all_fields(self):
        """New ledger has all expected default fields."""
        with (
            patch("hermes_loop.state.read_ledger", return_value=None),
            patch("hermes_loop.state.write_ledger"),
            patch("hermes_loop.state.os.path.exists", return_value=False),
            patch("hermes_loop.state.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(
                2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc
            )
            mock_dt.fromisoformat = datetime.fromisoformat
            result = load_or_create_ledger(
                goal="test goal",
                context="test context",
            )

        assert result["version"] == 11
        assert result["version_detail"] is not None
        assert "Self-healing" in result["version_detail"]
        assert result["initial_command"] == "test goal"
        assert result["initial_context"] == "test context"
        assert result["started_at"] is not None
        assert result["iterations"] == []
        assert result["total_iterations"] == 0
        assert result["last_updated"] is not None
        assert result["status"] == "running"
        assert result["stats"]["total_duration_seconds"] == 0.0
        assert result["stats"]["avg_duration_seconds"] == 0.0
        assert result["stats"]["success_count"] == 0
        assert result["stats"]["error_count"] == 0
        assert result["stats"]["consecutive_errors"] == 0
        assert result["stats"]["consecutive_successes"] == 0
        assert result["error_type_counts"]["timeout"] == 0
        assert result["mitigations"]["mitigation_level"] == 0
        assert result["goals_completed"] == {}
