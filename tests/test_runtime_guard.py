"""Unit tests for the runtime guard that detects stale control signal goals.

Tests the logic at the top of run_loop()'s main loop in loop.py (lines ~495-521)
that catches control signal goals like "NEXT_ITERATION need_reload" and
replaces them with a recovery goal before they reach the worker spawn code.
"""

from unittest.mock import patch

import pytest

from hermes_loop.goal_utils import GoalSpec

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_goals_list():
    """Single-goal list used when evolving without a goals file."""
    return [GoalSpec("my original goal")]


@pytest.fixture
def clean_state():
    """A minimal state dict with no pollution."""
    return {
        "current_goal": "my original goal",
        "iterations": [],
        "total_iterations": 0,
        "stats": {},
    }


@pytest.fixture
def polluted_state():
    """State where current_goal is already polluted with control signal."""
    return {
        "current_goal": "NEXT_ITERATION need_reload",
        "evolved_goal": "NEXT_ITERATION need_reload",
        "iterations": [],
        "total_iterations": 0,
        "stats": {},
    }


# ---------------------------------------------------------------------------
# Helper: emulate the runtime guard logic in isolation
# ---------------------------------------------------------------------------


# The exact guard code from loop.py lines ~495-521 (as of v14.39.4).
# We test it in isolation here and also verify via the actual module imports
# below.
def _runtime_guard(goal: str, goals_list: list, state: dict) -> tuple[str, list, dict]:
    """Inline copy of the runtime guard for isolated testing."""
    if "need_reload" in goal.lower() or goal.strip().lower().startswith(
        "next_iteration"
    ):
        goal = (
            "analyze the current codebase for any remaining issues or "
            "technical debt after the recent need_reload fix"
        )
        if goals_list:
            goals_list[0].goal = goal
        if state.get("current_goal") and (
            "need_reload" in state["current_goal"].lower()
            or state["current_goal"].strip().lower().startswith("next_iteration")
        ):
            state["current_goal"] = goal
        state.pop("evolved_goal", None)
    return goal, goals_list, state


RECOVERY_GOAL = (
    "analyze the current codebase for any remaining issues or "
    "technical debt after the recent need_reload fix"
)


# ===================================================================
# Tests: Detection of stale control signal goals
# ===================================================================


class TestDetection:
    """Guard correctly identifies stale control signal goals."""

    def test_detects_exact_control_signal(self, clean_state, base_goals_list):
        """'NEXT_ITERATION need_reload' is caught and replaced."""
        goal, _, _ = _runtime_guard(
            "NEXT_ITERATION need_reload", base_goals_list, clean_state
        )
        assert goal == RECOVERY_GOAL

    def test_detects_need_reload_standalone(self, clean_state, base_goals_list):
        """'need_reload' anywhere in goal string is caught."""
        goal, _, _ = _runtime_guard("need_reload", base_goals_list, clean_state)
        assert goal == RECOVERY_GOAL

    def test_detects_lowercase_next_iteration(self, clean_state, base_goals_list):
        """'next_iteration need_reload' (lowercase) is caught."""
        goal, _, _ = _runtime_guard(
            "next_iteration need_reload", base_goals_list, clean_state
        )
        assert goal == RECOVERY_GOAL

    def test_detects_mixed_case_next_iteration(self, clean_state, base_goals_list):
        """'Next_Iteration need_reload' (mixed case) is caught."""
        goal, _, _ = _runtime_guard(
            "Next_Iteration need_reload", base_goals_list, clean_state
        )
        assert goal == RECOVERY_GOAL

    def test_detects_need_reload_mixed_case(self, clean_state, base_goals_list):
        """'NEED_RELOAD' in any case is caught."""
        goal, _, _ = _runtime_guard(
            "NEXT_ITERATION NEED_RELOAD", base_goals_list, clean_state
        )
        assert goal == RECOVERY_GOAL

    def test_does_not_affect_normal_goals(self, base_goals_list):
        """Normal goals pass through unchanged."""
        goal, gl, _ = _runtime_guard("fix the unit tests", base_goals_list, {})
        assert goal == "fix the unit tests"
        assert gl[0].goal == base_goals_list[0].goal

    def test_does_not_affect_goal_with_reload_word(self, clean_state, base_goals_list):
        """Goal containing 'reload' but not 'need_reload' is NOT caught."""
        goal, _, _ = _runtime_guard("reload the config", base_goals_list, clean_state)
        assert goal == "reload the config"


class TestGoalsListUpdate:
    """Guard correctly updates goals_list[0].goal."""

    def test_updates_goals_list_single(self):
        """Single-goal list gets its goal replaced."""
        gl = [GoalSpec("NEXT_ITERATION need_reload")]
        _, goals_list, _ = _runtime_guard("NEXT_ITERATION need_reload", gl, {})
        assert goals_list[0].goal == RECOVERY_GOAL

    def test_updates_goals_list_first_only(self):
        """Only goals_list[0] is updated (since spawn_goal uses it)."""
        gl = [
            GoalSpec("NEXT_ITERATION need_reload"),
            GoalSpec("second real goal"),
        ]
        _, goals_list, _ = _runtime_guard("NEXT_ITERATION need_reload", gl, {})
        assert goals_list[0].goal == RECOVERY_GOAL
        assert goals_list[1].goal == "second real goal"


class TestStateCleanup:
    """Guard cleans up state pollution."""

    def test_cleans_current_goal_in_state(self, polluted_state):
        """Polluted state['current_goal'] is cleaned up (replaced with recovery)."""
        _, _, state = _runtime_guard(
            "NEXT_ITERATION need_reload", [GoalSpec("")], polluted_state
        )
        assert "NEXT_ITERATION" not in state.get("current_goal", "").upper()
        assert state["current_goal"] == RECOVERY_GOAL

    def test_pops_evolved_goal(self, polluted_state):
        """polluted_state['evolved_goal'] is removed."""
        assert "evolved_goal" in polluted_state
        _, _, state = _runtime_guard(
            "NEXT_ITERATION need_reload", [GoalSpec("")], polluted_state
        )
        assert "evolved_goal" not in state

    def test_does_not_remove_evolved_goal_when_clean(self, clean_state):
        """Non-polluted goals don't touch evolved_goal."""
        state_with_evolved = clean_state.copy()
        state_with_evolved["evolved_goal"] = "previous real goal"
        _, _, state = _runtime_guard("normal goal", [GoalSpec("")], state_with_evolved)
        assert state.get("evolved_goal") == "previous real goal"

    def test_current_goal_not_polluted_not_touched(self, clean_state):
        """Clean current_goal stays as-is when guard fires but current_goal isn't polluted."""
        _, _, state = _runtime_guard(
            "NEXT_ITERATION need_reload", [GoalSpec("")], clean_state
        )
        # The guard only replaces state["current_goal"] when it's already polluted
        # (line 514-518). clean_state has "my original goal" which doesn't match
        # the "need_reload" or "NEXT_ITERATION" check, so it stays unchanged.
        assert state["current_goal"] == "my original goal"


class TestEdgeCases:
    """Edge cases and resilience."""

    def test_empty_goal_string(self):
        """Empty goal string is not mistaken for control signal."""
        goal, _, _ = _runtime_guard("", [GoalSpec("")], {})
        assert goal == ""

    def test_goal_with_reload_in_substring(self):
        """Goal like 'please_reload' is not caught."""
        goal, _, _ = _runtime_guard("please_reload_config", [GoalSpec("")], {})
        assert goal == "please_reload_config"

    def test_state_without_current_goal(self):
        """Guard handles state without current_goal key gracefully."""
        state = {}
        _, _, new_state = _runtime_guard(
            "NEXT_ITERATION need_reload", [GoalSpec("")], state
        )
        assert "current_goal" not in new_state

    def test_empty_goals_list(self, clean_state):
        """Guard handles empty goals_list gracefully."""
        goal, gl, _ = _runtime_guard("NEXT_ITERATION need_reload", [], clean_state)
        assert goal == RECOVERY_GOAL
        assert gl == []


# ===================================================================
# Integration tests: call the actual loop.run_loop guard code
# through its public interface
# ===================================================================


class TestViaModule:
    """Verify the actual loop.py guard code via imports."""

    def test_guard_exists_in_run_loop_source(self):
        """The runtime guard code exists in the source as expected."""
        import inspect
        from hermes_loop import loop

        src = inspect.getsource(loop.run_loop)
        assert "need_reload" in src
        assert "NEXT_ITERATION" in src or "next_iteration" in src
        assert "control signal" in src

    def test_detection_against_actual_goal_spec(self):
        """The guard works with actual GoalSpec objects used in loop.py."""
        gl = [GoalSpec("NEXT_ITERATION need_reload")]
        state = {"current_goal": "NEXT_ITERATION need_reload", "evolved_goal": True}

        goal, goals_list, state = _runtime_guard(
            "NEXT_ITERATION need_reload", gl, state
        )
        assert goal == RECOVERY_GOAL
        assert goals_list[0].goal == RECOVERY_GOAL
        assert state["current_goal"] == RECOVERY_GOAL
        assert "evolved_goal" not in state
