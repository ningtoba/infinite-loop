"""Shared pytest fixtures for hermes_loop tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Sample iteration records for stats and error recovery tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_iterations() -> list[dict[str, Any]]:
    """A list of sample iteration records with varied outcomes."""
    return [
        {"duration_seconds": 30, "error": None},
        {"duration_seconds": 45, "error": "timeout"},
        {"duration_seconds": 20, "error": None},
        {"duration_seconds": 60, "error": None},
        {"duration_seconds": 10, "error": "network"},
    ]


@pytest.fixture
def sample_ledger_state(sample_iterations) -> dict[str, Any]:
    """A full sample ledger state dict with stats already computed."""
    return {
        "total_iterations": 5,
        "iterations": sample_iterations,
        "goals_completed": {},
        "stats": {
            "total_duration_seconds": 165.0,
            "avg_duration_seconds": 33.0,
            "success_count": 3,
            "error_count": 2,
            "consecutive_errors": 1,
            "consecutive_successes": 0,
        },
    }


@pytest.fixture
def empty_ledger_state() -> dict[str, Any]:
    """An empty ledger state with no iterations."""
    return {
        "total_iterations": 0,
        "iterations": [],
        "goals_completed": {},
        "stats": {},
    }


@pytest.fixture
def all_success_state() -> dict[str, Any]:
    """State where all iterations succeeded (no errors)."""
    return {
        "total_iterations": 4,
        "iterations": [
            {"duration_seconds": 15, "error": None},
            {"duration_seconds": 25, "error": None},
            {"duration_seconds": 10, "error": None},
            {"duration_seconds": 30, "error": None},
        ],
        "goals_completed": {},
    }


@pytest.fixture
def all_error_state() -> dict[str, Any]:
    """State where all iterations had errors."""
    return {
        "total_iterations": 3,
        "iterations": [
            {"duration_seconds": 10, "error": "timeout"},
            {"duration_seconds": 5, "error": "network"},
            {"duration_seconds": 3, "error": "unknown"},
        ],
        "goals_completed": {},
    }


@pytest.fixture
def mixed_state() -> dict[str, Any]:
    """State with a mix of errors and successes for consecutive tracking."""
    return {
        "total_iterations": 7,
        "iterations": [
            {"duration_seconds": 10, "error": None},  # 0 — success
            {"duration_seconds": 10, "error": "timeout"},  # 1 — error
            {"duration_seconds": 10, "error": None},  # 2 — success
            {"duration_seconds": 10, "error": "timeout"},  # 3 — error
            {"duration_seconds": 10, "error": "network"},  # 4 — error
            {"duration_seconds": 10, "error": None},  # 5 — success
            {"duration_seconds": 10, "error": None},  # 6 — success
        ],
        "goals_completed": {},
    }


# ---------------------------------------------------------------------------
# Error recovery fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def original_values() -> dict[str, Any]:
    """Original baseline values for error recovery tests."""
    return {
        "session_timeout": 120,
        "cooldown": 5,
        "use_library": True,
        "workers": 3,
    }


@pytest.fixture
def empty_mitigations() -> dict[str, Any]:
    """An empty mitigations dict as passed to _adapt_to_error."""
    return {}


@pytest.fixture
def sample_mitigations() -> dict[str, Any]:
    """A mitigations dict with an existing level (e.g., level 1)."""
    return {
        "mitigation_level": 1,
        "timeout_increased": True,
        "cooldown_elevated": False,
        "force_subprocess": False,
        "reduced_workers": False,
    }


# ---------------------------------------------------------------------------
# Temporary ledger file fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_ledger_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for ledger file I/O tests."""
    return tmp_path


@pytest.fixture
def ledger_data() -> dict[str, Any]:
    """Sample ledger data for write/read tests."""
    return {
        "total_iterations": 3,
        "iterations": [
            {"duration_seconds": 30, "error": None, "summary": "test 1"},
            {"duration_seconds": 45, "error": "timeout", "summary": "test 2"},
            {"duration_seconds": 20, "error": None, "summary": "test 3"},
        ],
        "goals_completed": {
            "abc123": {"status": "completed", "iteration": 2, "goal": "fix bug"},
        },
        "stats": {
            "total_duration_seconds": 95.0,
            "avg_duration_seconds": 31.7,
            "success_count": 2,
            "error_count": 1,
            "consecutive_errors": 0,
            "consecutive_successes": 1,
            "remote_cleanup_totals": {
                "remote_deleted": 0,
                "remote_merged": 0,
                "stale_pruned": 0,
                "remote_failed": 0,
            },
        },
    }


# ---------------------------------------------------------------------------
# Goal utils fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def goal_completed_state() -> dict[str, Any]:
    """State with a single completed goal."""
    return {
        "total_iterations": 1,
        "iterations": [],
        "goals_completed": {
            "a1b2c3d4e5f6a7b8": {
                "status": "completed",
                "iteration": 3,
                "goal": "fix authentication bug",
            },
        },
    }
