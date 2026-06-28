"""Tests for stats.py — _recalc_stats."""

from __future__ import annotations


from hermes_loop.stats import _recalc_stats


class TestRecalcStats:
    """Tests for _recalc_stats."""

    # -----------------------------------------------------------------------
    # Basic calculations
    # -----------------------------------------------------------------------

    def test_empty_iterations(self, empty_ledger_state):
        """Zero iterations yields zero stats."""
        state = dict(empty_ledger_state)
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["total_duration_seconds"] == 0.0
        assert stats["avg_duration_seconds"] == 0.0
        assert stats["success_count"] == 0
        assert stats["error_count"] == 0
        assert stats["consecutive_errors"] == 0
        assert stats["consecutive_successes"] == 0

    def test_all_success(self, all_success_state):
        """All-success iterations count and average correctly."""
        state = dict(all_success_state)
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["success_count"] == 4
        assert stats["error_count"] == 0
        assert stats["total_duration_seconds"] == 80.0
        assert stats["avg_duration_seconds"] == 20.0
        assert stats["consecutive_errors"] == 0
        assert stats["consecutive_successes"] == 4

    def test_all_error(self, all_error_state):
        """All-error iterations."""
        state = dict(all_error_state)
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["success_count"] == 0
        assert stats["error_count"] == 3
        assert stats["total_duration_seconds"] == 18.0
        assert stats["avg_duration_seconds"] == 6.0
        assert stats["consecutive_errors"] == 3
        assert stats["consecutive_successes"] == 0

    def test_mixed_consecutive_tracking(self, mixed_state):
        """Consecutive counts stop when encountering a different outcome."""
        state = dict(mixed_state)
        _recalc_stats(state)
        stats = state["stats"]
        # Last two iterations are success (#5, #6), then #4 is network error
        assert stats["consecutive_successes"] == 2
        # But overall totals
        assert stats["success_count"] == 4  # idx 0, 2, 5, 6
        assert stats["error_count"] == 3  # idx 1, 3, 4

    def test_sample_ledger(self, sample_ledger_state):
        """Sample ledger with known values."""
        state = dict(sample_ledger_state)
        _recalc_stats(state)
        stats = state["stats"]
        # 30 + 45 + 20 + 60 + 10 = 165
        assert stats["total_duration_seconds"] == 165.0
        assert stats["avg_duration_seconds"] == 33.0
        assert stats["success_count"] == 3
        assert stats["error_count"] == 2

    # -----------------------------------------------------------------------
    # Consecutive tracking edge cases
    # -----------------------------------------------------------------------

    def test_consecutive_errors_at_end(self):
        """Errors at the end of the iteration list are counted."""
        state = {
            "total_iterations": 5,
            "iterations": [
                {"duration_seconds": 30, "error": None},
                {"duration_seconds": 20, "error": None},
                {"duration_seconds": 10, "error": "timeout"},
                {"duration_seconds": 5, "error": "network"},
                {"duration_seconds": 3, "error": "unknown"},
            ],
        }
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["consecutive_errors"] == 3
        assert stats["consecutive_successes"] == 0

    def test_consecutive_mixed_interleaved(self):
        """Interleaved success/error tracks consecutive from the end."""
        state = {
            "total_iterations": 6,
            "iterations": [
                {"duration_seconds": 10, "error": None},
                {"duration_seconds": 10, "error": "timeout"},
                {"duration_seconds": 10, "error": None},
                {"duration_seconds": 10, "error": "timeout"},
                {"duration_seconds": 10, "error": None},
                {"duration_seconds": 10, "error": "timeout"},
            ],
        }
        _recalc_stats(state)
        stats = state["stats"]
        # Last is timeout (error), but looks back: pattern is ...None, timeout
        # Should stop at the last None before the consecutive errors
        assert stats["consecutive_errors"] == 1  # just the last one
        assert stats["consecutive_successes"] == 0

    def test_single_error_at_end(self):
        """Single error at the end of a success streak."""
        state = {
            "total_iterations": 4,
            "iterations": [
                {"duration_seconds": 10, "error": None},
                {"duration_seconds": 10, "error": None},
                {"duration_seconds": 10, "error": None},
                {"duration_seconds": 10, "error": "timeout"},
            ],
        }
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["consecutive_errors"] == 1
        assert stats["consecutive_successes"] == 0

    def test_single_success_at_end(self):
        """Single success at the end of an error streak."""
        state = {
            "total_iterations": 4,
            "iterations": [
                {"duration_seconds": 10, "error": "timeout"},
                {"duration_seconds": 10, "error": "timeout"},
                {"duration_seconds": 10, "error": "timeout"},
                {"duration_seconds": 10, "error": None},
            ],
        }
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["consecutive_successes"] == 1
        assert stats["consecutive_errors"] == 0

    # -----------------------------------------------------------------------
    # Duration calculations
    # -----------------------------------------------------------------------

    def test_duration_rounding(self):
        """Duration is rounded to 1 decimal place."""
        state = {
            "total_iterations": 3,
            "iterations": [
                {"duration_seconds": 10.123, "error": None},
                {"duration_seconds": 20.456, "error": None},
                {"duration_seconds": 30.789, "error": None},
            ],
        }
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["total_duration_seconds"] == 61.4  # 61.368 → 61.4
        assert stats["avg_duration_seconds"] == 20.5  # 20.456 → 20.5

    def test_duration_with_zeros(self):
        """Iterations with zero duration are handled."""
        state = {
            "total_iterations": 3,
            "iterations": [
                {"duration_seconds": 0, "error": None},
                {"duration_seconds": 0, "error": None},
                {"duration_seconds": 0, "error": None},
            ],
        }
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["total_duration_seconds"] == 0.0
        assert stats["avg_duration_seconds"] == 0.0

    # -----------------------------------------------------------------------
    # Remote cleanup totals
    # -----------------------------------------------------------------------

    def test_remote_cleanup_aggregation(self):
        """Remote cleanup values are summed across iterations."""
        state = {
            "total_iterations": 2,
            "iterations": [
                {
                    "duration_seconds": 10,
                    "error": None,
                    "remote_cleanup": {
                        "remote_deleted": 2,
                        "remote_merged": 1,
                        "stale_pruned": 0,
                        "remote_failed": 0,
                    },
                },
                {
                    "duration_seconds": 20,
                    "error": None,
                    "remote_cleanup": {
                        "remote_deleted": 1,
                        "remote_merged": 3,
                        "stale_pruned": 2,
                        "remote_failed": 1,
                    },
                },
            ],
        }
        _recalc_stats(state)
        rc = state["stats"]["remote_cleanup_totals"]
        assert rc["remote_deleted"] == 3
        assert rc["remote_merged"] == 4
        assert rc["stale_pruned"] == 2
        assert rc["remote_failed"] == 1

    def test_remote_cleanup_missing_keys(self):
        """Iterations without remote_cleanup are handled."""
        state = {
            "total_iterations": 2,
            "iterations": [
                {"duration_seconds": 10, "error": None},
                {"duration_seconds": 20, "error": None},
            ],
        }
        _recalc_stats(state)
        rc = state["stats"]["remote_cleanup_totals"]
        assert rc["remote_deleted"] == 0
        assert rc["remote_merged"] == 0
        assert rc["stale_pruned"] == 0
        assert rc["remote_failed"] == 0

    def test_remote_cleanup_partial_keys(self):
        """Iterations with partial remote_cleanup keys."""
        state = {
            "total_iterations": 1,
            "iterations": [
                {
                    "duration_seconds": 10,
                    "error": None,
                    "remote_cleanup": {"remote_deleted": 5},  # missing other keys
                },
            ],
        }
        _recalc_stats(state)
        rc = state["stats"]["remote_cleanup_totals"]
        assert rc["remote_deleted"] == 5
        assert rc["remote_merged"] == 0
        assert rc["stale_pruned"] == 0
        assert rc["remote_failed"] == 0

    # -----------------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------------

    def test_missing_iterations_key(self):
        """State missing 'iterations' key is handled gracefully."""
        state: dict = {"total_iterations": 0}
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["total_duration_seconds"] == 0.0
        assert stats["success_count"] == 0
        assert stats["error_count"] == 0

    def test_iteration_missing_duration(self):
        """Iteration without duration_seconds defaults to 0."""
        state = {
            "total_iterations": 2,
            "iterations": [
                {"error": None},
                {"error": None},
            ],
        }
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["total_duration_seconds"] == 0.0

    def test_large_number_of_iterations(self):
        """Large iteration count is handled efficiently."""
        iterations = [
            {
                "duration_seconds": float(i % 100),
                "error": ("timeout" if i % 5 == 0 else None),
            }
            for i in range(1000)
        ]
        state = {"total_iterations": 1000, "iterations": iterations}
        _recalc_stats(state)
        stats = state["stats"]
        assert stats["error_count"] == 200  # every 5th
        assert stats["success_count"] == 800
