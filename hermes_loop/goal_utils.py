"""Goal completion tracking helpers and GoalSpec class."""

import hashlib

from .config import TASK_PATTERNS


def _goal_hash(goal_text: str) -> str:
    """Return a deterministic short hash of a goal text."""
    return hashlib.md5(goal_text.encode()).hexdigest()[:16]


def _is_goal_completed(state: dict, goal_text: str) -> bool:
    """Check if a goal has already been marked completed in the ledger."""
    gh = _goal_hash(goal_text)
    completed = state.setdefault("goals_completed", {})
    return gh in completed and completed[gh].get("status") == "completed"


def _mark_goal_completed(state: dict, goal_text: str, iteration_num: int):
    """Mark a goal as completed in the ledger state (in-memory only)."""
    gh = _goal_hash(goal_text)
    completed = state.setdefault("goals_completed", {})
    completed[gh] = {
        "status": "completed",
        "iteration": iteration_num,
        "goal": goal_text[:200],
    }
    state["goals_completed"] = completed  # ensure serialization


class GoalSpec:
    """A goal with optional profile/model/provider overrides.

    Parsed from pipe-separated goals file format: goal|profile|model|provider.
    Empty fields fall back to daemon-level CLI args.
    """

    def __init__(
        self, goal: str, profile: str = "", model: str = "", provider: str = ""
    ):
        self.goal = goal
        self.profile = profile
        self.model = model
        self.provider = provider

    def __str__(self):
        return self.goal[:60]
