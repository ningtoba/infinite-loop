"""Tests for goal_utils.py — GoalSpec, _goal_hash, _is_goal_completed, _mark_goal_completed."""

from __future__ import annotations


from hermes_loop.goal_utils import (
    GoalSpec,
    _goal_hash,
    _is_goal_completed,
    _mark_goal_completed,
)

# ===================================================================
# _goal_hash
# ===================================================================


class TestGoalHash:
    """Tests for _goal_hash function."""

    def test_deterministic_hash(self):
        """Same input always produces same hash."""
        assert _goal_hash("fix auth bug") == _goal_hash("fix auth bug")

    def test_different_goals_different_hashes(self):
        """Different inputs produce different hashes."""
        assert _goal_hash("fix auth") != _goal_hash("fix auth bug")

    def test_hash_length(self):
        """Hash is always 16 hex characters."""
        h = _goal_hash("any goal text here")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_goal_hash(self):
        """Empty string produces a valid hash."""
        h = _goal_hash("")
        assert len(h) == 16
        assert isinstance(h, str)

    def test_unicode_goal(self):
        """Unicode text works."""
        h = _goal_hash("héllo wörld")
        assert len(h) == 16

    def test_long_goal(self):
        """Very long goal text produces a fixed-length hash."""
        long_goal = "fix " * 1000
        h = _goal_hash(long_goal)
        assert len(h) == 16


# ===================================================================
# GoalSpec
# ===================================================================


class TestGoalSpec:
    """Tests for GoalSpec class."""

    def test_basic_goal(self):
        """Basic goal with no overrides."""
        g = GoalSpec("fix auth")
        assert g.goal == "fix auth"
        assert g.profile == ""
        assert g.model == ""
        assert g.provider == ""

    def test_with_profile(self):
        """Goal with profile override."""
        g = GoalSpec("fix auth", profile="work")
        assert g.goal == "fix auth"
        assert g.profile == "work"
        assert g.model == ""
        assert g.provider == ""

    def test_full_spec(self):
        """Goal with all overrides."""
        g = GoalSpec("fix auth", profile="work", model="gpt4", provider="openai")
        assert g.goal == "fix auth"
        assert g.profile == "work"
        assert g.model == "gpt4"
        assert g.provider == "openai"

    def test_profile_and_model(self):
        """Goal with profile and model but no provider."""
        g = GoalSpec("fix tests", profile="dev", model="claude-opus")
        assert g.goal == "fix tests"
        assert g.profile == "dev"
        assert g.model == "claude-opus"
        assert g.provider == ""

    def test_string_representation(self):
        """__str__ returns truncated goal."""
        g = GoalSpec("this is a very long goal that should be truncated")
        assert len(str(g)) <= 60
        assert str(g).startswith("this is a very long goal")

    def test_str_short_goal(self):
        """__str__ for short goal."""
        g = GoalSpec("fix auth")
        assert str(g) == "fix auth"

    def test_type_annotations(self):
        """All fields are strings."""
        g = GoalSpec("test", profile="p", model="m", provider="pr")
        assert isinstance(g.goal, str)
        assert isinstance(g.profile, str)
        assert isinstance(g.model, str)
        assert isinstance(g.provider, str)

    def test_empty_goal(self):
        """Goal with empty string."""
        g = GoalSpec("")
        assert g.goal == ""

    def test_special_chars_goal(self):
        """Goal with special characters."""
        g = GoalSpec("fix auth! @#$%^ &*()")
        assert g.goal == "fix auth! @#$%^ &*()"


# ===================================================================
# _is_goal_completed / _mark_goal_completed
# ===================================================================


class TestGoalCompleted:
    """Tests for _is_goal_completed and _mark_goal_completed."""

    def test_goal_not_completed(self):
        """Goal not in completed list returns False."""
        state: dict = {"goals_completed": {}}
        assert _is_goal_completed(state, "fix auth bug") is False

    def test_goal_completed(self):
        """Goal in completed list with status 'completed' returns True."""
        state: dict = {"goals_completed": {}}
        gh = _goal_hash("fix authentication bug")
        state["goals_completed"][gh] = {
            "status": "completed",
            "iteration": 3,
            "goal": "fix authentication bug",
        }
        assert _is_goal_completed(state, "fix authentication bug") is True

    def test_mark_goal_completed(self):
        """Marking a goal completed adds it to the state."""
        state: dict = {}
        _mark_goal_completed(state, "fix auth bug", iteration_num=1)
        gh = _goal_hash("fix auth bug")
        assert gh in state["goals_completed"]
        assert state["goals_completed"][gh]["status"] == "completed"
        assert state["goals_completed"][gh]["iteration"] == 1

    def test_mark_then_check(self):
        """After marking, _is_goal_completed returns True."""
        state: dict = {}
        _mark_goal_completed(state, "implement feature", 2)
        assert _is_goal_completed(state, "implement feature") is True

    def test_different_goal_not_affected(self):
        """Marking one goal doesn't affect another."""
        state: dict = {}
        _mark_goal_completed(state, "goal A", 1)
        assert _is_goal_completed(state, "goal A") is True
        assert _is_goal_completed(state, "goal B") is False

    def test_mark_multiple_times(self):
        """Marking same goal multiple times updates the entry."""
        state: dict = {}
        _mark_goal_completed(state, "same goal", 1)
        _mark_goal_completed(state, "same goal", 5)
        gh = _goal_hash("same goal")
        assert state["goals_completed"][gh]["iteration"] == 5

    def test_goal_text_truncated(self):
        """Goal text is truncated to 200 chars in storage."""
        long_goal = "x" * 500
        state: dict = {}
        _mark_goal_completed(state, long_goal, 1)
        gh = _goal_hash(long_goal)
        stored_goal = state["goals_completed"][gh]["goal"]
        assert len(stored_goal) == 200
        assert stored_goal == "x" * 200

    def test_state_missing_goals_completed_key(self):
        """State without 'goals_completed' initializes it."""
        state: dict = {}
        assert _is_goal_completed(state, "any goal") is False
        # Should have added the key
        assert "goals_completed" in state

    def test_goal_with_different_casing(self):
        """Goal completion is case-sensitive (same as hash)."""
        state: dict = {}
        _mark_goal_completed(state, "Fix Auth", 1)
        assert _is_goal_completed(state, "Fix Auth") is True
        assert _is_goal_completed(state, "fix auth") is False

    def test_multiple_goals_in_state(self):
        """Multiple completed goals in state."""
        state: dict = {}
        _mark_goal_completed(state, "goal one", 1)
        _mark_goal_completed(state, "goal two", 2)
        _mark_goal_completed(state, "goal three", 3)
        assert _is_goal_completed(state, "goal two") is True
        assert _is_goal_completed(state, "goal one") is True
        assert _is_goal_completed(state, "goal four") is False

    def test_mark_goal_increments_state(self):
        """State dict has goals_completed after marking."""
        state: dict = {}
        _mark_goal_completed(state, "test", 1)
        assert len(state["goals_completed"]) == 1

    def test_goal_in_state_but_not_completed(self):
        """A goal hash that exists but has different status."""
        state: dict = {
            "goals_completed": {
                _goal_hash("partial"): {
                    "status": "in_progress",
                    "iteration": 1,
                    "goal": "partial",
                }
            }
        }
        assert _is_goal_completed(state, "partial") is False

    def test_empty_goal_completed_tracking(self):
        """Empty goal string can be tracked."""
        state: dict = {}
        _mark_goal_completed(state, "", 1)
        assert _is_goal_completed(state, "") is True
