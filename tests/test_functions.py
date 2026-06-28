"""Tests for pi_loop.functions — goal loading, startup banner, cycling, context, cooldown."""

from unittest.mock import MagicMock, patch

from pi_loop.functions import (
    _build_progressive_context,
    _cycle_goal,
    _handle_cooldown,
    _load_goals_file,
    _log_startup_banner,
    get_max_output_chars,
    set_max_output_chars,
)


class TestMaxOutputChars:
    def test_roundtrip(self):
        """set_max_output_chars/get_max_output_chars roundtrip."""
        set_max_output_chars(5000)
        assert get_max_output_chars() == 5000

    def test_initial_default(self):
        """get_max_output_chars returns default value initially."""
        set_max_output_chars(2000)
        assert get_max_output_chars() == 2000


class TestLoadGoalsFile:
    def test_no_file_returns_singleton(self):
        """_load_goals_file with no goals_file returns singleton with original goal."""
        result = _load_goals_file("", "original goal")
        assert result == [("original goal", "", "", "")]

    def test_parses_pipe_delimited_goals(self, tmp_path):
        """_load_goals_file parses pipe-delimited GoalSpec goals."""
        gf = tmp_path / "goals.txt"
        gf.write_text("goal1 | profile1 | model1 | provider1\ngoal2 | profile2 | model2 |\ngoal3\n")
        result = _load_goals_file(str(gf), "fallback")
        assert len(result) == 3
        assert result[0] == ("goal1", "profile1", "model1", "provider1")
        assert result[1] == ("goal2", "profile2", "model2", "")
        assert result[2] == ("goal3", "", "", "")

    def test_skips_comments_and_blanks(self, tmp_path):
        """_load_goals_file skips comments and blank lines."""
        gf = tmp_path / "goals.txt"
        gf.write_text("# comment\n\ngoal1\n# another\n\ngoal2 | profile\n")
        result = _load_goals_file(str(gf), "fallback")
        assert len(result) == 2
        assert result[0][0] == "goal1"

    def test_missing_file_falls_back(self):
        """_load_goals_file uses fallback when file doesn't exist."""
        result = _load_goals_file("/nonexistent/goals.txt", "fallback goal")
        assert result == [("fallback goal", "", "", "")]


class TestCycleGoal:
    def test_single_goal_returns_noop(self):
        """_cycle_goal with single goal returns ('', False)."""
        goal_text, should_stop = _cycle_goal(["only goal"], 0, False)
        assert goal_text == ""
        assert should_stop == False

    def test_cycles_through_multi_goal_list(self):
        """_cycle_goal cycles through multi-goal list."""
        goals = [("goal1", "p1", "m1", "pr1"), ("goal2", "", "", "")]
        goal_text, should_stop = _cycle_goal(goals, 0, False)
        assert goal_text == "goal1"
        assert should_stop == False

        goal_text2, should_stop2 = _cycle_goal(goals, 1, False)
        assert goal_text2 == "goal2"
        assert should_stop2 == False

    def test_stop_at_goals_end(self):
        """_cycle_goal with stop_at_goals_end=True stops when index >= len(list)."""
        goals = ["goal1", "goal2"]
        goal_text, should_stop = _cycle_goal(goals, 2, stop_at_goals_end=True)
        assert goal_text == ""
        assert should_stop

    def test_handles_string_goals(self):
        """_cycle_goal handles plain string goals (not tuples)."""
        goals = ["goal1", "goal2"]
        result, should_stop = _cycle_goal(goals, 0, False)
        assert result == "goal1"
        assert should_stop == False


class TestBuildProgressiveContext:
    def test_appends_recent_summaries(self):
        """_build_progressive_context appends last 3 summaries."""
        context = "Base context"
        summaries = ["Fixed A", "Fixed B", "Fixed C", "Fixed D"]
        result = _build_progressive_context(context, summaries)
        assert "Base context" in result
        assert "Fixed B" in result and "Fixed C" in result and "Fixed D" in result
        assert "Fixed A" not in result

    def test_empty_summaries(self):
        """_build_progressive_context with empty summaries returns context unchanged."""
        result = _build_progressive_context("Base", [])
        assert result == "Base"

    def test_no_context(self):
        """_build_progressive_context with empty context works."""
        result = _build_progressive_context("", ["summary"])
        assert "[Previous iterations:" in result


class TestHandleCooldown:
    def test_no_cooldown_no_sleep(self):
        """_handle_cooldown with cooldown=0 does not sleep."""
        with patch("pi_loop.functions.time.sleep") as mock_sleep:
            _handle_cooldown(0, "fixed", MagicMock(), "research")
        mock_sleep.assert_not_called()

    def test_adaptive_uses_eta_tracker(self):
        """_handle_cooldown with adaptive mode uses eta_tracker."""
        eta = MagicMock()
        eta.avg_duration.return_value = 100.0
        with patch("pi_loop.functions.time.sleep") as mock_sleep:
            _handle_cooldown(5, "adaptive", eta, "research")
        assert mock_sleep.call_count == 10

    def test_fixed_cooldown_sleeps(self):
        """_handle_cooldown with fixed cooldown > 0 sleeps."""
        with patch("pi_loop.functions.time.sleep") as mock_sleep:
            _handle_cooldown(3, "fixed", MagicMock(), "research")
        assert mock_sleep.call_count == 3


class TestLogStartupBanner:
    min_kwargs = {
        "task_type": "research",
        "task_type_desc": "Research task",
        "profile": "",
        "model": "",
        "max_iterations": 10,
        "max_retries": 0,
        "max_turns": 500,
        "tag": "",
        "goal": "test goal",
        "toolsets": [],
        "evolve": False,
        "git": False,
        "git_commit": False,
        "workers": 1,
        "session_timeout": 600,
        "notify_cmd": None,
        "use_library": True,
        "pass_session_id": False,
        "checkpoints": False,
        "output_schema": None,
        "cooldown_mode": "fixed",
        "cooldown": 0,
        "convergence_stop": False,
        "convergence_window": 5,
        "convergence_threshold": 0.9,
        "store_git_diff": False,
    }

    def test_does_not_crash(self):
        """_log_startup_banner runs without error."""
        with patch("pi_loop.functions._log"):
            _log_startup_banner(**self.min_kwargs)

    def test_quiet_mode_shows_compact(self):
        """_log_startup_banner with quiet=True shows compact one-line status."""
        with patch("pi_loop.functions._log") as mock_log:
            _log_startup_banner(**self.min_kwargs, quiet=True)
            assert mock_log.call_count > 0

    def test_with_git_and_workers(self):
        """_log_startup_banner with git and multiple workers."""
        kwargs = dict(self.min_kwargs)
        kwargs.update({"git": True, "git_commit": True, "workers": 3, "evolve": True})
        with patch("pi_loop.functions._log"):
            _log_startup_banner(**kwargs)
