"""Tests for pi_loop.loop — main loop execution logic."""

from unittest.mock import MagicMock, patch

from pi_loop.loop import _build_dashboard_html, _evolve_goal, _execute_task, _request_shutdown, _validate_on_error_cmd


class TestRequestShutdown:
    def test_sets_shutdown_flag(self):
        """_request_shutdown sets the module-level shutdown flag."""
        _request_shutdown()
        from pi_loop.loop import _shutdown_requested

        assert _shutdown_requested.is_set()


class TestExecuteTask:
    def test_returns_result_dict(self):
        """_execute_task returns a result dict."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout.readline.side_effect = [b"", b""]  # Immediate EOF
        mock_proc.communicate.return_value = (b'{"output": "done"}', b"")

        with patch("subprocess.Popen", return_value=mock_proc):
            result = _execute_task("test goal", "", None, 10)
        assert isinstance(result, dict)

    def test_handles_pi_not_found(self):
        """_execute_task handles missing 'pi' binary."""
        with patch("subprocess.Popen", side_effect=FileNotFoundError("pi not found")):
            result = _execute_task("test goal", "", None, 10)
        assert "error" in result
        assert "pi" in result.get("error", "")

    def test_retries_on_failure(self):
        """_execute_task retries on failure up to max_retries."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout.readline.side_effect = [b"", b""]
        mock_proc.communicate.return_value = (b"error output", b"stderr")

        with patch("subprocess.Popen", return_value=mock_proc), patch("pi_loop.loop.time.sleep"):
            result = _execute_task("test goal", "", None, 10, max_retries=1)
        assert "error" in result

    def test_with_context(self):
        """_execute_task passes context to pi."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout.readline.side_effect = [b"", b""]
        mock_proc.communicate.return_value = (b"", b"")

        with patch("subprocess.Popen", return_value=mock_proc):
            result = _execute_task("goal", "context", None, 10)
        assert isinstance(result, dict)


class TestEvolveGoal:
    def test_detects_next_goal(self):
        """_evolve_goal detects NEXT_GOAL: marker."""
        state = {}
        _evolve_goal("Some output\nNEXT_GOAL: Fix the tests\nMore output", state, 5)
        assert state.get("evolved_goal") == "Fix the tests"

    def test_case_insensitive_prefix(self):
        """_evolve_goal matches case-insensitively."""
        state = {}
        _evolve_goal("next_goal: Deploy to prod", state, 1)
        assert state.get("evolved_goal") == "Deploy to prod"

    def test_no_marker_does_nothing(self):
        """_evolve_goal does nothing when no NEXT_GOAL marker."""
        state = {}
        _evolve_goal("Some regular output without marker", state, 1)
        assert "evolved_goal" not in state

    def test_empty_goal_skipped(self):
        """_evolve_goal skips empty NEXT_GOAL."""
        state = {}
        _evolve_goal("NEXT_GOAL:  \n", state, 1)
        assert "evolved_goal" not in state


class TestBuildDashboardHtml:
    def test_returns_html_string(self):
        """_build_dashboard_html returns an HTML string."""
        state = {
            "status": "running",
            "iterations": [
                {"n": 1, "error": None, "duration_seconds": 10.5, "summary": "First iteration"},
                {"n": 2, "error": "timeout", "duration_seconds": 30.0, "summary": "Second failed"},
            ],
            "stats": {"total_duration_seconds": 40.5},
            "total_iterations": 2,
        }
        html = _build_dashboard_html(state)
        assert "<!DOCTYPE html>" in html
        assert "pi-loop Dashboard" in html
        assert "❌" in html  # Error iteration
        assert "✅" in html  # Success iteration
        assert "running" in html

    def test_empty_state(self):
        """_build_dashboard_html handles empty state."""
        state = {}
        html = _build_dashboard_html(state)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

    def test_shows_recent_50_iterations(self):
        """_build_dashboard_html shows only the last 50 iterations."""
        state = {
            "iterations": [
                {"n": i, "error": None, "duration_seconds": 1.0, "summary": f"iter {i}"} for i in range(100)
            ],
            "stats": {"total_duration_seconds": 100.0},
        }
        html = _build_dashboard_html(state)
        assert "iter 0" not in html  # Should be beyond the last 50
        assert "iter 99" in html  # Latest should be present

    def test_reversed_order(self):
        """_build_dashboard_html shows iterations in reverse order (newest first)."""
        state = {
            "iterations": [
                {"n": 1, "error": None, "duration_seconds": 5.0, "summary": "first"},
                {"n": 2, "error": None, "duration_seconds": 10.0, "summary": "second"},
            ],
            "stats": {"total_duration_seconds": 15.0},
        }
        html = _build_dashboard_html(state)
        # The table rows should show latest first
        idx_second = html.index("second") if "second" in html else -1
        idx_first = html.index("first") if "first" in html else -1
        assert idx_second < idx_first  # Latest should appear first


class TestValidateOnErrorCmd:
    """Tests for _validate_on_error_cmd security guardrails."""

    def test_valid_simple_command(self):
        """A simple command without metacharacters returns valid."""
        valid, reason = _validate_on_error_cmd("echo hello")
        assert valid
        assert reason == "OK"

    def test_valid_command_with_path(self):
        """A command with slashes and dashes is valid."""
        valid, reason = _validate_on_error_cmd("/usr/bin/notify-send test")
        assert valid
        assert reason == "OK"

    def test_empty_command(self):
        """Empty command is invalid."""
        valid, reason = _validate_on_error_cmd("")
        assert not valid
        assert "empty" in reason.lower()

    def test_whitespace_only_command(self):
        """Whitespace-only command is invalid."""
        valid, reason = _validate_on_error_cmd("   ")
        assert not valid
        assert "empty" in reason.lower()

    def test_exceeds_500_chars(self):
        """Command over 500 chars is rejected."""
        cmd = "a" * 501
        valid, reason = _validate_on_error_cmd(cmd)
        assert not valid
        assert "500" in reason

    def test_500_chars_is_valid(self):
        """Command exactly 500 chars is allowed."""
        cmd = "a" * 500
        valid, reason = _validate_on_error_cmd(cmd)
        assert valid
        assert reason == "OK"

    def test_rejects_semicolon(self):
        """Semicolon (multi-command) is rejected by default."""
        valid, reason = _validate_on_error_cmd("echo a; echo b")
        assert not valid
        assert "semicolon" in reason.lower()

    def test_rejects_pipe(self):
        """Pipe (chained command) is rejected by default."""
        valid, reason = _validate_on_error_cmd("echo a | grep a")
        assert not valid
        assert "pipe" in reason.lower()

    def test_rejects_backtick(self):
        """Backtick (command substitution) is rejected by default."""
        valid, reason = _validate_on_error_cmd("echo `whoami`")
        assert not valid
        assert "backtick" in reason.lower()

    def test_rejects_dollar_sign(self):
        """Dollar sign (variable expansion) is rejected by default."""
        valid, reason = _validate_on_error_cmd("echo $HOME")
        assert not valid
        assert "dollar" in reason.lower()

    def test_rejects_ampersand(self):
        """Ampersand (backgrounding) is rejected by default."""
        valid, reason = _validate_on_error_cmd("sleep 10 &")
        assert not valid
        assert "ampersand" in reason.lower()

    def test_allows_metachars_when_flag_set(self):
        """Metacharacters are allowed when allow_metachars=True."""
        valid, reason = _validate_on_error_cmd("echo a; echo b", allow_metachars=True)
        assert valid
        assert reason == "OK"

    def test_allows_metachars_with_dollar(self):
        """Dollar sign is allowed when allow_metachars=True."""
        valid, reason = _validate_on_error_cmd("echo $HOME", allow_metachars=True)
        assert valid
        assert reason == "OK"

    def test_allows_metachars_pipe(self):
        """Pipe is allowed when allow_metachars=True."""
        valid, reason = _validate_on_error_cmd("ls -la | head", allow_metachars=True)
        assert valid
        assert reason == "OK"

    def test_multiple_metachars_rejected(self):
        """Multiple metacharacters are all rejected."""
        valid, reason = _validate_on_error_cmd("cmd1; cmd2 | grep x $VAR")
        assert not valid
        # Should report the first metacharacter found
        assert any(w in reason.lower() for w in ["semicolon", "pipe", "dollar"])
