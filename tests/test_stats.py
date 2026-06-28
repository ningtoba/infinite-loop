"""Tests for _recalc_stats."""

from pi_loop.stats import _recalc_stats


def test_empty_iterations():
    """_recalc_stats with no iterations produces zeroed stats."""
    state: dict = {"iterations": []}
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["total_duration_seconds"] == 0.0
    assert s["avg_duration_seconds"] == 0.0
    assert s["success_count"] == 0
    assert s["error_count"] == 0
    assert s["consecutive_errors"] == 0
    assert s["consecutive_successes"] == 0
    assert s["remote_cleanup_totals"] == {
        "remote_deleted": 0,
        "remote_merged": 0,
        "stale_pruned": 0,
        "remote_failed": 0,
    }


def test_missing_iterations_key():
    """_recalc_stats handles missing 'iterations' key gracefully."""
    state: dict = {}
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["total_duration_seconds"] == 0.0
    assert s["success_count"] == 0
    assert s["error_count"] == 0


def test_all_successful():
    """All successful iterations produce correct stats."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "A", "error": None, "duration_seconds": 10.0},
            {"index": 1, "summary": "B", "error": None, "duration_seconds": 20.0},
            {"index": 2, "summary": "C", "error": None, "duration_seconds": 30.0},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["total_duration_seconds"] == 60.0
    assert s["avg_duration_seconds"] == 20.0
    assert s["success_count"] == 3
    assert s["error_count"] == 0
    assert s["consecutive_errors"] == 0
    assert s["consecutive_successes"] == 3


def test_all_errors():
    """All error iterations produce correct stats."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "E1", "error": "timeout", "duration_seconds": 5.0},
            {"index": 1, "summary": "E2", "error": "crash", "duration_seconds": 15.0},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["total_duration_seconds"] == 20.0
    assert s["avg_duration_seconds"] == 10.0
    assert s["success_count"] == 0
    assert s["error_count"] == 2
    assert s["consecutive_errors"] == 2
    assert s["consecutive_successes"] == 0


def test_mixed_iterations():
    """Mix of success and error iterations."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "OK", "error": None, "duration_seconds": 10.0},
            {
                "index": 1,
                "summary": "FAIL",
                "error": "network",
                "duration_seconds": 5.0,
            },
            {"index": 2, "summary": "OK2", "error": None, "duration_seconds": 20.0},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["success_count"] == 2
    assert s["error_count"] == 1
    assert s["total_duration_seconds"] == 35.0


def test_consecutive_errors():
    """Consecutive errors at end are counted correctly."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "OK", "error": None, "duration_seconds": 1.0},
            {"index": 1, "summary": "E1", "error": "timeout", "duration_seconds": 2.0},
            {"index": 2, "summary": "E2", "error": "crash", "duration_seconds": 3.0},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["consecutive_errors"] == 2
    assert s["consecutive_successes"] == 0


def test_consecutive_successes():
    """Consecutive successes at end are counted correctly."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "E1", "error": "crash", "duration_seconds": 1.0},
            {"index": 1, "summary": "OK1", "error": None, "duration_seconds": 2.0},
            {"index": 2, "summary": "OK2", "error": None, "duration_seconds": 3.0},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["consecutive_successes"] == 2
    assert s["consecutive_errors"] == 0


def test_consecutive_alternating():
    """Alternating success/error resets consecutive counters."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "OK", "error": None, "duration_seconds": 1.0},
            {"index": 1, "summary": "E", "error": "fail", "duration_seconds": 2.0},
            {"index": 2, "summary": "OK", "error": None, "duration_seconds": 3.0},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["consecutive_successes"] == 1
    assert s["consecutive_errors"] == 0


def test_missing_error_key():
    """Iteration without 'error' key is treated as success."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "OK", "duration_seconds": 5.0},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["success_count"] == 1
    assert s["error_count"] == 0


def test_missing_duration():
    """Iteration without duration_seconds defaults to 0."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "A", "error": None},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["total_duration_seconds"] == 0.0


def test_duration_rounding():
    """Duration is rounded to 1 decimal place."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "A", "error": None, "duration_seconds": 3.14159},
            {"index": 1, "summary": "B", "error": None, "duration_seconds": 1.33333},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["total_duration_seconds"] == 4.5
    assert s["avg_duration_seconds"] == 2.2


def test_remote_cleanup_aggregation():
    """Remote cleanup totals are aggregated across iterations."""
    state: dict = {
        "iterations": [
            {
                "index": 0,
                "summary": "A",
                "error": None,
                "duration_seconds": 1.0,
                "remote_cleanup": {
                    "remote_deleted": 2,
                    "remote_merged": 1,
                    "stale_pruned": 0,
                    "remote_failed": 0,
                },
            },
            {
                "index": 1,
                "summary": "B",
                "error": None,
                "duration_seconds": 1.0,
                "remote_cleanup": {
                    "remote_deleted": 1,
                    "remote_merged": 3,
                    "stale_pruned": 2,
                    "remote_failed": 1,
                },
            },
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["remote_cleanup_totals"]["remote_deleted"] == 3
    assert s["remote_cleanup_totals"]["remote_merged"] == 4
    assert s["remote_cleanup_totals"]["stale_pruned"] == 2
    assert s["remote_cleanup_totals"]["remote_failed"] == 1


def test_missing_remote_cleanup():
    """Iterations without remote_cleanup key don't break aggregation."""
    state: dict = {
        "iterations": [
            {"index": 0, "summary": "A", "error": None, "duration_seconds": 1.0},
            {"index": 1, "summary": "B", "error": None, "duration_seconds": 1.0},
        ]
    }
    _recalc_stats(state)
    s: dict = state["stats"]
    assert s["remote_cleanup_totals"]["remote_deleted"] == 0
    assert s["remote_cleanup_totals"]["remote_merged"] == 0
