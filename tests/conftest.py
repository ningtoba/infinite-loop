"""Shared pytest fixtures for pi-loop tests."""

import pytest


@pytest.fixture
def sample_state():
    """Return a basic state dict with no iterations."""
    return {
        "goal": "Test goal",
        "iterations": [],
        "stats": {},
        "workers": 1,
    }


@pytest.fixture
def state_with_iterations():
    """Return a state with a mix of successful and error iterations."""
    return {
        "goal": "Fix lint errors",
        "iterations": [
            {
                "index": 0,
                "summary": "Fixed eslint errors",
                "error": None,
                "duration_seconds": 12.5,
            },
            {
                "index": 1,
                "summary": "Fixed prettier formatting",
                "error": None,
                "duration_seconds": 8.2,
            },
            {
                "index": 2,
                "summary": "Error occurred",
                "error": "Connection timeout",
                "duration_seconds": 30.0,
            },
            {
                "index": 3,
                "summary": "Fixed remaining issues",
                "error": None,
                "duration_seconds": 15.1,
            },
        ],
        "stats": {},
        "workers": 1,
    }


@pytest.fixture
def state_consecutive_errors():
    """Return a state ending with consecutive errors."""
    return {
        "goal": "Test goal",
        "iterations": [
            {"index": 0, "summary": "OK", "error": None, "duration_seconds": 5.0},
            {
                "index": 1,
                "summary": "Error 1",
                "error": "timeout",
                "duration_seconds": 10.0,
            },
            {
                "index": 2,
                "summary": "Error 2",
                "error": "network error",
                "duration_seconds": 12.0,
            },
        ],
        "stats": {},
        "workers": 1,
    }


@pytest.fixture
def state_consecutive_successes():
    """Return a state ending with consecutive successes."""
    return {
        "goal": "Test goal",
        "iterations": [
            {"index": 0, "summary": "Fail", "error": "crash", "duration_seconds": 5.0},
            {"index": 1, "summary": "OK 1", "error": None, "duration_seconds": 3.0},
            {"index": 2, "summary": "OK 2", "error": None, "duration_seconds": 4.0},
        ],
        "stats": {},
        "workers": 1,
    }


@pytest.fixture
def sample_schema():
    """Return a basic JSON schema for testing validation."""
    return {
        "type": "object",
        "required": ["name", "status"],
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 100},
            "status": {"type": "string", "enum": ["ok", "error", "pending"]},
            "count": {"type": "integer", "minimum": 0, "maximum": 1000},
            "score": {"type": "number"},
            "active": {"type": "boolean"},
            "tags": {"type": "array"},
            "metadata": {
                "type": "object",
                "properties": {
                    "version": {"type": "integer"},
                },
            },
        },
    }


@pytest.fixture
def valid_output():
    """Return output data that validates against sample_schema."""
    return {
        "name": "test-run",
        "status": "ok",
        "count": 42,
        "score": 98.5,
        "active": True,
        "tags": ["a", "b"],
        "metadata": {"version": 1},
    }


@pytest.fixture
def sample_config():
    """Return a config dict mimicking pi_loop.config constants."""
    return {
        "VERSION": "14.39.0",
        "LEDGER_PATH": "/tmp/infinite-loop-state.json",
        "SENTINEL_PATH_DEFAULT": "/tmp/infinite-loop-stop",
        "DEFAULT_CONVERGENCE_WINDOW": 5,
        "DEFAULT_CONVERGENCE_THRESHOLD": 0.9,
    }


@pytest.fixture
def error_iteration():
    """Return a single iteration dict with error info."""
    return {
        "index": 0,
        "summary": "Something timed out",
        "error": "timeout",
        "duration_seconds": 120.0,
    }


@pytest.fixture
def network_error_iteration():
    """Return a single iteration with a network error."""
    return {
        "index": 1,
        "summary": "Connection refused",
        "error": "connection refused",
        "duration_seconds": 60.0,
    }
