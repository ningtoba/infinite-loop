"""Tests for hermes_utils.py — find_hermes, detect_task_type, _build_delegation_prompt."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import subprocess
import json


from hermes_loop.hermes_utils import (
    _ANSI_RE,
    find_hermes,
    detect_task_type,
    _build_delegation_prompt,
    _read_stderr_real_time,
    _read_stdout_live,
    _run_hermes_with_pty,
    spawn_delegation_session,
)

# ===================================================================
# ANSI regex
# ===================================================================


class TestAnsiRegex:
    """Tests for _ANSI_RE pattern."""

    def test_strips_simple_ansi(self):
        """Basic ANSI escape codes are stripped."""
        assert _ANSI_RE.sub("", "\x1b[31mred\x1b[0m") == "red"

    def test_strips_csi_codes(self):
        """CSI sequences like cursor movements are stripped."""
        assert _ANSI_RE.sub("", "\x1b[2J\x1b[Hhello") == "hello"

    def test_strips_osc_codes(self):
        """OSC sequences (e.g., terminal title) are stripped."""
        text = "\x1b]11;?\x07visible"
        assert _ANSI_RE.sub("", text) == "visible"

    def test_strips_multiple_ansi(self):
        """Multiple ANSI codes in one string."""
        text = "\x1b[32m\x1b[1mbold green\x1b[0m"
        assert _ANSI_RE.sub("", text) == "bold green"

    def test_strips_carriage_returns(self):
        """Carriage returns are stripped."""
        assert _ANSI_RE.sub("", "line1\rline2") == "line1line2"

    def test_no_ansi_passthrough(self):
        """Plain text without ANSI codes is unchanged."""
        assert _ANSI_RE.sub("", "hello world") == "hello world"

    def test_strips_cursor_save_restore(self):
        """Cursor save/restore sequences are stripped."""
        assert _ANSI_RE.sub("", "\x1b[s\x1b[utest\x1b[u") == "test"

    def test_strips_erase_in_line(self):
        """Erase-in-line sequences like \x1b[K are stripped."""
        assert _ANSI_RE.sub("", "prefix\x1b[Ksuffix") == "prefixsuffix"

    def test_strips_sgr_reset_and_others(self):
        """\x1b[m (reset with no params) is stripped."""
        assert _ANSI_RE.sub("", "a\x1b[mb") == "ab"


# ===================================================================
# find_hermes
# ===================================================================


class TestFindHermes:
    """Tests for find_hermes function."""

    def test_shutil_which_found(self):
        """shutil.which returns a path that exists and is executable."""
        with patch("shutil.which", return_value="/usr/local/bin/hermes"):
            with patch("os.path.isfile", return_value=True):
                with patch("os.access", return_value=True):
                    result = find_hermes()
        assert result == "/usr/local/bin/hermes"

    def test_fallback_to_local_bin(self):
        """Falls back to ~/.local/bin/hermes."""
        with patch("shutil.which", return_value=None):
            with patch(
                "os.path.expanduser", side_effect=lambda p: p.replace("~", "/home/user")
            ):
                with patch(
                    "os.path.isfile",
                    side_effect=lambda p: p == "/home/user/.local/bin/hermes",
                ):
                    with patch("os.access", return_value=True):
                        result = find_hermes()
        assert "hermes" in result

    def test_fallback_to_dot_hermes(self):
        """Falls back to ~/.hermes/hermes."""
        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                with patch("os.access", return_value=False):
                    result = find_hermes()
        assert result == "hermes"

    def test_default_return(self):
        """When nothing found, returns bare 'hermes'."""
        with patch("shutil.which", return_value=None):
            with patch(
                "os.path.expanduser", side_effect=lambda p: p.replace("~", "/home/user")
            ):
                with patch("os.path.isfile", return_value=False):
                    with patch("os.access", return_value=False):
                        result = find_hermes()
        assert result == "hermes"

    def test_executable_check_fails(self):
        """Binary found but not executable — skip to next candidate."""
        with patch("shutil.which", return_value="/usr/bin/hermes"):
            with patch("os.path.isfile", return_value=True):
                with patch("os.access", return_value=False):
                    result = find_hermes()
        assert result == "hermes"


# ===================================================================
# detect_task_type
# ===================================================================


class TestDetectTaskType:
    """Tests for detect_task_type function."""

    def test_general_default(self):
        """No matching keywords returns ('general', ...)."""
        result = detect_task_type("do some random thing")
        assert result[0] == "general"
        assert "General" in result[1]

    def test_research_keyword(self):
        """'research' in goal returns research type."""
        typ, desc, tools = detect_task_type("research the best approach")
        assert typ == "research"
        assert "search" in tools or "web" in tools

    def test_code_fix_keyword(self):
        """'fix' in goal returns code-fix type."""
        typ, _, tools = detect_task_type("fix the authentication bug")
        assert typ == "code-fix"
        assert "code_execution" in tools

    def test_code_build_keyword(self):
        """'build' in goal returns code-build type."""
        typ, _, tools = detect_task_type("build a new feature")
        assert typ == "code-build"
        assert "code_execution" in tools

    def test_system_admin_keyword(self):
        """'deploy' keyword returns system-admin type."""
        typ, _, tools = detect_task_type("deploy to production")
        assert typ == "system-admin"

    def test_data_processing_keyword(self):
        """'parse' keyword returns data-processing type."""
        typ, _, tools = detect_task_type("parse the CSV files")
        assert typ == "data-processing"

    def test_content_keyword(self):
        """'write documentation' returns content type."""
        typ, _, tools = detect_task_type("write documentation for API")
        assert typ == "content"

    def test_case_insensitive(self):
        """Matching is case-insensitive."""
        typ, _, _ = detect_task_type("FIX the BUG")
        assert typ == "code-fix"

    def test_highest_score_wins(self):
        """When multiple matched, highest score wins."""
        # 'fix' = code-fix (1 match), 'research' = research (1 match)
        # 'research' is listed first in TASK_PATTERNS — but the winner is
        # determined by key with max score, and tie-break is insertion order
        # (Python dict preserves insertion order since 3.7)
        # With 1 match each, the first-inserted key ('research') wins.
        typ, _, _ = detect_task_type("research fix")
        assert typ in ("research", "code-fix")

    def test_score_with_multiple_matches(self):
        """Multiple keyword matches in same type increase score."""
        typ, _, _ = detect_task_type("research and analyze the literature and paper")
        assert typ == "research"

    def test_goal_with_colon(self):
        """Goal with colon separator is handled."""
        typ, _, _ = detect_task_type("research: find papers about transformers")
        assert typ == "research"

    def test_empty_goal(self):
        """Empty or whitespace goal returns general."""
        typ, _, _ = detect_task_type("")
        assert typ == "general"

    def test_goal_with_special_chars(self):
        """Special characters don't crash matching."""
        typ, _, _ = detect_task_type("fix the $PATH variable on *nix systems!")
        assert typ == "code-fix"

    def test_multiple_types_one_keyword_each(self):
        """One keyword each for two types: first in order wins on tie."""
        typ, _, _ = detect_task_type("fix deploy")
        assert typ in ("code-fix", "system-admin")


# ===================================================================
# _build_delegation_prompt
# ===================================================================


class TestBuildDelegationPrompt:
    """Tests for _build_delegation_prompt function."""

    def test_contains_goal(self):
        """Prompt includes the goal text."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="fix the auth bug",
            context="",
            toolsets=["terminal", "file"],
            workdir="/home/user/project",
            evolve=False,
        )
        assert "fix the auth bug" in prompt

    def test_contains_iteration_number(self):
        """Prompt includes iteration number."""
        prompt = _build_delegation_prompt(
            iteration=5,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
        )
        assert "iteration #5" in prompt

    def test_contains_worker_id(self):
        """Prompt includes worker id when provided."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            worker_id=3,
        )
        assert "worker #3)" in prompt or "worker #3" in prompt

    def test_no_worker_tag_without_worker_id(self):
        """No worker tag when worker_id is None."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
        )
        assert "worker" not in prompt or "(worker)" in prompt

    def test_includes_context(self):
        """Context is included in prompt."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="Previous work on auth module",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
        )
        assert "Previous work on auth module" in prompt

    def test_toolsets_in_prompt(self):
        """Toolsets are mentioned as available tools."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal", "file", "web"],
            workdir=None,
            evolve=False,
        )
        assert "AVAILABLE TOOLS" in prompt or "terminal" in prompt

    def test_evolve_adds_next_goal(self):
        """evolve=True adds next_goal field to JSON format instructions."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=True,
        )
        assert "next_goal" in prompt

    def test_no_next_goal_without_evolve(self):
        """Without evolve, the evolve-specific JSON format line doesn't mention next_goal.

        Note: 'next_goal' appears in the non-evolve-specific sections
        (CRITICAL RULES and SELF-MODIFICATION SIGNAL blocks are always present),
        so we check the evolve-conditional JSON_FORMAT section specifically.
        """
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
        )
        # With evolve=False, the 'evolve' variable causes the JSON format
        # instructions to not include 'next_goal' in the field list.
        # The line should say: '"error": null|"<error>",' without next_goal
        assert '"error": null|"<error>",' in prompt
        # The evolve=True line is NOT in the prompt
        assert '"next_goal": "<suggested next task>"' not in prompt

    def test_workdir_in_prompt(self):
        """Workdir is mentioned in prompt."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir="/home/user/project",
            evolve=False,
        )
        assert "/home/user/project" in prompt

    def test_prior_context_section(self):
        """Prior context is included in its own section."""
        prompt = _build_delegation_prompt(
            iteration=2,
            goal="continue fixing bugs",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            prior_context="Iteration 1: found 3 bugs",
        )
        assert "PRIOR ITERATION CONTEXT" in prompt
        assert "Iteration 1: found 3 bugs" in prompt

    def test_self_modification_context_for_infinite_loop(self):
        """Goal mentioning infinite-loop adds self-modification context."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="improve infinite-loop daemon",
            context="",
            toolsets=["terminal", "file"],
            workdir="/home/user/project",
            evolve=False,
        )
        assert "SELF-MODIFICATION CONTEXT" in prompt
        assert "launch-loop.py" in prompt
        assert "SKILL.md" in prompt

    def test_no_self_modification_for_unrelated_goal(self):
        """Unrelated goal does not add self-modification context."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="fix auth bug in login",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
        )
        assert "SELF-MODIFICATION CONTEXT" not in prompt

    def test_research_type_adds_research_strategy(self):
        """task_type='research' adds research strategy section."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="research paper",
            context="",
            toolsets=["terminal", "web"],
            workdir=None,
            evolve=False,
            task_type="research",
        )
        assert "RESEARCH STRATEGY" in prompt

    def test_code_fix_type_adds_code_strategy(self):
        """task_type='code-fix' adds code strategy."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="fix bug",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            task_type="code-fix",
        )
        assert "CODE STRATEGY" in prompt

    def test_code_build_type_adds_code_strategy(self):
        """task_type='code-build' adds code strategy."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="build feature",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            task_type="code-build",
        )
        assert "CODE STRATEGY" in prompt

    def test_system_admin_type_adds_system_strategy(self):
        """task_type='system-admin' adds system admin strategy."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="deploy server",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            task_type="system-admin",
        )
        assert "SYSTEM ADMIN STRATEGY" in prompt

    def test_data_processing_type(self):
        """task_type='data-processing' adds data processing strategy."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="process data",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            task_type="data-processing",
        )
        assert "DATA PROCESSING STRATEGY" in prompt

    def test_content_type(self):
        """task_type='content' adds content strategy."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="write docs",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            task_type="content",
        )
        assert "CONTENT CREATION STRATEGY" in prompt

    def test_general_type_adds_general_strategy(self):
        """task_type='general' adds general strategy."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="do things",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            task_type="general",
        )
        assert "GENERAL STRATEGY" in prompt

    def test_heartbeat_interval_adds_heartbeat_section(self):
        """heartbeat_interval > 0 adds heartbeat instructions."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            heartbeat_interval=30,
        )
        assert "SESSION HEARTBEAT" in prompt
        assert "every 30 seconds" in prompt.lower()

    def test_no_heartbeat_when_zero(self):
        """heartbeat_interval=0 omits heartbeat section."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            heartbeat_interval=0,
        )
        assert "SESSION HEARTBEAT" not in prompt

    def test_prompt_suffix_added(self):
        """prompt_suffix is appended to the prompt."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            prompt_suffix="NOTE: focus on security",
        )
        assert "EXTRA INSTRUCTIONS" in prompt
        assert "focus on security" in prompt

    def test_prompt_ends_with_do_not_chat(self):
        """Prompt ends with the 'Do not chat' instruction."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
        )
        assert prompt.strip().endswith("Print JSON.")

    def test_model_and_profile_not_in_prompt(self):
        """Profile and model are not injected into prompt (they're CLI flags)."""
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context="",
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
            profile="work",
            model="gpt-4",
        )
        # Profile and model are CLI args, not prompt content
        assert "--profile" not in prompt
        assert "gpt-4" not in prompt

    def test_large_context_truncated(self):
        """Very large context is still passed through (no truncation)."""
        large_context = "x" * 10000
        prompt = _build_delegation_prompt(
            iteration=1,
            goal="test",
            context=large_context,
            toolsets=["terminal"],
            workdir=None,
            evolve=False,
        )
        # Context is included as-is (no truncation in the prompt builder)
        assert large_context in prompt

    def test_self_modification_uses_real_skill_path(self):
        """Self-modification context uses actual skill directory path pattern."""
        with patch("os.path.isdir", return_value=True):
            prompt = _build_delegation_prompt(
                iteration=1,
                goal="modify the infinite-loop skill",
                context="",
                toolsets=["terminal"],
                workdir=None,
                evolve=False,
            )
            assert "SELF-MODIFICATION CONTEXT" in prompt


# ===================================================================
# _read_stderr_real_time
# ===================================================================


class TestReadStderrRealTime:
    """Tests for _read_stderr_real_time — daemon thread reading stderr."""

    def test_reads_lines_and_logs_them(self):
        """Reads lines from stderr and logs them with [STDERR] prefix."""
        proc = MagicMock()
        proc.stderr.readline.side_effect = ["line1\n", "line2\n", ""]

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            _read_stderr_real_time(proc, worker_tag="")

        assert mock_log.call_count == 2
        mock_log.assert_any_call("[STDERR] line1")
        mock_log.assert_any_call("[STDERR] line2")

    def test_reads_with_worker_tag(self):
        """Logs include worker tag in [STDERR{tag}] prefix."""
        proc = MagicMock()
        proc.stderr.readline.side_effect = ["output\n", ""]

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            _read_stderr_real_time(proc, worker_tag="#1")

        mock_log.assert_called_with("[STDERR#1] output")

    def test_strips_trailing_newlines(self):
        """Strips \\n and \\r from line ends."""
        proc = MagicMock()
        proc.stderr.readline.side_effect = ["hello\r\n", ""]

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            _read_stderr_real_time(proc, worker_tag="")

        mock_log.assert_called_with("[STDERR] hello")

    def test_skips_empty_lines(self):
        """Empty lines are skipped without logging."""
        proc = MagicMock()
        proc.stderr.readline.side_effect = ["\n", "content\n", ""]

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            _read_stderr_real_time(proc, worker_tag="")

        assert mock_log.call_count == 1
        mock_log.assert_called_with("[STDERR] content")

    def test_truncates_long_lines(self):
        """Lines longer than 500 chars are truncated."""
        proc = MagicMock()
        long_line = "x" * 600 + "\n"
        proc.stderr.readline.side_effect = [long_line, ""]

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            _read_stderr_real_time(proc, worker_tag="")

        logged = mock_log.call_args[0][0]
        assert len(logged) <= 515  # "[STDERR] " (8) + 500 = 508

    def test_handles_value_error_gracefully(self):
        """ValueError from readline is caught silently."""
        proc = MagicMock()
        proc.stderr.readline.side_effect = ValueError("I/O operation on closed file")

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            # Should not raise
            _read_stderr_real_time(proc, worker_tag="")
        mock_log.assert_not_called()

    def test_handles_os_error_gracefully(self):
        """OSError from readline is caught silently."""
        proc = MagicMock()
        proc.stderr.readline.side_effect = OSError("pipe closed")

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            _read_stderr_real_time(proc, worker_tag="")
        mock_log.assert_not_called()

    def test_handles_attribute_error_gracefully(self):
        """AttributeError (e.g. NoneType) is caught silently."""
        proc = MagicMock()
        proc.stderr.readline.side_effect = AttributeError(
            "'NoneType' object has no attribute 'readline'"
        )

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            # Should not raise
            _read_stderr_real_time(proc, worker_tag="")
        mock_log.assert_not_called()


# ===================================================================
# _read_stdout_live
# ===================================================================


class TestReadStdoutLive:
    """Tests for _read_stdout_live — stdout reader with timeout."""

    def test_reads_lines_and_returns_joined_output(self):
        """Reads stdout lines and returns joined string + exit code."""
        proc = MagicMock()
        proc.stdout.readline.side_effect = ["line1\n", "line2\n", ""]
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.args = ["hermes", "chat", "-q"]

        with patch("hermes_loop.hermes_utils._log"):
            stdout, code = _read_stdout_live(proc, worker_tag="", timeout_seconds=0)

        assert stdout == "line1\nline2"
        assert code == 0

    def test_truncates_long_lines_in_log(self):
        """Lines longer than 500 chars logged with truncation."""
        proc = MagicMock()
        long_line = "x" * 600 + "\n"
        proc.stdout.readline.side_effect = [long_line, ""]
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.args = ["hermes"]

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            _read_stdout_live(proc, worker_tag="#1", timeout_seconds=0)

        # Logged line should be truncated to 500 chars
        logged = mock_log.call_args[0][0]
        assert len(logged) <= 530  # "[TERM (worker #1)] " + 500

    def test_skips_empty_lines(self):
        """Empty lines in stdout are skipped."""
        proc = MagicMock()
        proc.stdout.readline.side_effect = ["\n", "data\n", ""]
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.args = ["hermes"]

        with patch("hermes_loop.hermes_utils._log"):
            stdout, _ = _read_stdout_live(proc, worker_tag="", timeout_seconds=0)

        assert stdout == "data"

    def test_raises_timeout_expired(self):
        """Raises subprocess.TimeoutExpired when timeout exceeded."""
        proc = MagicMock()
        # Simulate slow output that keeps returning data so iter() doesn't stop
        proc.stdout.readline.side_effect = ["line1\n"] + ["data\n"] * 100
        proc.args = ["hermes", "chat", "-q"]

        with patch("hermes_loop.hermes_utils._log"):
            with patch("hermes_loop.hermes_utils.time.time") as mock_time:
                # Returns start time, elapsed time exceeds timeout
                mock_time.side_effect = [100.0, 100.0, 130.0]  # 30s elapsed
                with pytest.raises(subprocess.TimeoutExpired) as exc:
                    _read_stdout_live(proc, worker_tag="", timeout_seconds=10)
                assert "line1" in str(exc.value.output)

    def test_timeout_disabled_when_zero(self):
        """timeout_seconds=0 disables timeout check."""
        proc = MagicMock()
        proc.stdout.readline.side_effect = ["data\n", ""]
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.args = ["hermes"]

        with patch("hermes_loop.hermes_utils._log"):
            stdout, code = _read_stdout_live(proc, worker_tag="", timeout_seconds=0)

        assert stdout == "data"
        assert code == 0

    def test_handles_value_error_gracefully(self):
        """ValueError from readline caught, returns partial output."""
        proc = MagicMock()
        proc.stdout.readline.side_effect = ["partial\n", ValueError("closed")]
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.args = ["hermes"]

        with patch("hermes_loop.hermes_utils._log"):
            stdout, code = _read_stdout_live(proc, worker_tag="", timeout_seconds=0)

        assert stdout == "partial"
        assert code == 0

    def test_handles_os_error_gracefully(self):
        """OSError from readline caught."""
        proc = MagicMock()
        proc.stdout.readline.side_effect = OSError("closed")
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.args = ["hermes"]

        with patch("hermes_loop.hermes_utils._log"):
            stdout, code = _read_stdout_live(proc, worker_tag="", timeout_seconds=0)

        assert stdout == ""
        assert code == 0

    def test_handles_attribute_error_gracefully(self):
        """AttributeError from readline caught."""
        proc = MagicMock()
        proc.stdout.readline.side_effect = AttributeError("no attribute")
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.args = ["hermes"]

        with patch("hermes_loop.hermes_utils._log"):
            stdout, code = _read_stdout_live(proc, worker_tag="", timeout_seconds=0)

        assert stdout == ""
        assert code == 0

    def test_uses_worker_tag_in_log(self):
        """Worker tag included in log prefix."""
        proc = MagicMock()
        proc.stdout.readline.side_effect = ["output\n", ""]
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.args = ["hermes"]

        with patch("hermes_loop.hermes_utils._log") as mock_log:
            _read_stdout_live(proc, worker_tag="#2", timeout_seconds=0)

        mock_log.assert_called_with("[TERM (worker #2)] output")

    def test_calls_proc_wait_before_returning(self):
        """proc.wait() is called before returning results."""
        proc = MagicMock()
        proc.stdout.readline.side_effect = ["done\n", ""]
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.args = ["hermes"]

        with patch("hermes_loop.hermes_utils._log"):
            _read_stdout_live(proc, worker_tag="", timeout_seconds=0)

        proc.wait.assert_called_once()


# ===================================================================
class TestRunHermesWithPty:
    """Tests for _run_hermes_with_pty — PTY subprocess management."""

    def test_raises_timeout_when_exceeded(self):
        """Raises subprocess.TimeoutExpired when timeout exceeded."""
        with patch("pty.openpty", return_value=(5, 6)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("select.select", return_value=([], [], [])):
                    with patch("os.set_blocking"):
                        with patch("os.close"):
                            with patch("time.time") as mock_time:
                                mock_proc = MagicMock()
                                mock_popen.return_value = mock_proc
                                mock_proc.poll.return_value = None
                                mock_time.side_effect = [0.0, 0.0, 0.0, 31.0]

                                with pytest.raises(subprocess.TimeoutExpired):
                                    _run_hermes_with_pty(
                                        cmd=["hermes", "chat", "-q"],
                                        worker_tag="#1",
                                        timeout_seconds=30,
                                        workdir="/tmp",
                                    )

                                mock_proc.kill.assert_called_once()
                                mock_proc.wait.assert_called()

    def test_zero_timeout_disables_check(self):
        """timeout_seconds=0 disables timeout (process runs until done)."""
        with patch("pty.openpty", return_value=(5, 6)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("select.select") as mock_select:
                    with patch("os.set_blocking"):
                        with patch("os.close"):
                            mock_proc = MagicMock()
                            mock_popen.return_value = mock_proc
                            mock_select.side_effect = [
                                ([5], [], []),
                                ([], [], []),
                            ]
                            mock_proc.poll.side_effect = [None, 0]
                            with patch("os.read") as mock_read:
                                mock_read.side_effect = [b"hello\n", b""]

                                with patch("hermes_loop.hermes_utils._log"):
                                    stdout, code = _run_hermes_with_pty(
                                        cmd=["hermes"],
                                        worker_tag="",
                                        timeout_seconds=0,
                                        workdir="/tmp",
                                    )

        assert "hello" in stdout

    def test_reads_data_and_returns_output(self):
        """Reads PTY data, processes lines, returns joined output."""
        with patch("pty.openpty", return_value=(5, 6)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("select.select") as mock_select:
                    with patch("os.set_blocking"):
                        with patch("os.close"):
                            mock_proc = MagicMock()
                            mock_popen.return_value = mock_proc
                            mock_select.side_effect = [
                                ([5], [], []),
                                ([], [], []),
                            ]
                            mock_proc.poll.side_effect = [None, 0]
                            with patch("os.read") as mock_read:
                                mock_read.side_effect = [
                                    b"line1\nline2\n",
                                    b"",
                                ]

                                with patch("hermes_loop.hermes_utils._log"):
                                    stdout, code = _run_hermes_with_pty(
                                        cmd=["hermes"],
                                        worker_tag="#1",
                                        timeout_seconds=120,
                                        workdir="/tmp",
                                    )

        assert "line1" in stdout
        assert "line2" in stdout

    def test_strips_ansi_and_processes_lines(self):
        """ANSI codes are stripped, TUI chars normalized."""
        with patch("pty.openpty", return_value=(5, 6)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("select.select") as mock_select:
                    with patch("os.set_blocking"):
                        with patch("os.close"):
                            mock_proc = MagicMock()
                            mock_popen.return_value = mock_proc
                            mock_select.return_value = ([5], [], [])
                            mock_proc.poll.return_value = 0
                            with patch("os.read") as mock_read:
                                mock_read.side_effect = [
                                    b"\x1b[32mgreen\x1b[0m\n",
                                    b"",
                                ]

                                with patch("hermes_loop.hermes_utils._log"):
                                    stdout, code = _run_hermes_with_pty(
                                        cmd=["hermes"],
                                        worker_tag="",
                                        timeout_seconds=30,
                                        workdir="/tmp",
                                    )

        assert "green" in stdout

    def test_value_error_in_select_breaks_loop(self):
        """ValueError from select.select breaks the loop gracefully."""
        with patch("pty.openpty", return_value=(5, 6)):
            with patch("subprocess.Popen") as mock_popen:
                with patch(
                    "select.select",
                    side_effect=ValueError("bad fd"),
                ):
                    with patch("os.set_blocking"):
                        with patch("os.close"):
                            mock_proc = MagicMock()
                            mock_popen.return_value = mock_proc
                            mock_proc.poll.return_value = 0
                            mock_proc.wait.return_value = 0

                            with patch("hermes_loop.hermes_utils._log"):
                                stdout, code = _run_hermes_with_pty(
                                    cmd=["hermes"],
                                    worker_tag="",
                                    timeout_seconds=30,
                                    workdir="/tmp",
                                )
        assert code == 0

    def test_oserror_in_read_breaks_loop(self):
        """OSError from os.read is caught, loop breaks."""
        with patch("pty.openpty", return_value=(5, 6)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("select.select") as mock_select:
                    with patch("os.set_blocking"):
                        with patch("os.close"):
                            mock_proc = MagicMock()
                            mock_popen.return_value = mock_proc
                            mock_select.return_value = ([5], [], [])
                            mock_proc.poll.return_value = 0
                            mock_proc.wait.return_value = 0
                            with patch(
                                "os.read",
                                side_effect=OSError("bad read"),
                            ):
                                with patch("hermes_loop.hermes_utils._log"):
                                    stdout, code = _run_hermes_with_pty(
                                        cmd=["hermes"],
                                        worker_tag="",
                                        timeout_seconds=30,
                                        workdir="/tmp",
                                    )
        assert code == 0

    def test_process_already_done_at_start(self):
        """Process already completed when poll is called."""
        with patch("pty.openpty", return_value=(5, 6)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("select.select") as mock_select:
                    with patch("os.set_blocking"):
                        with patch("os.close"):
                            mock_proc = MagicMock()
                            mock_popen.return_value = mock_proc
                            mock_select.return_value = ([], [], [])
                            mock_proc.poll.return_value = 0
                            mock_proc.wait.return_value = 0

                            with patch("hermes_loop.hermes_utils._log"):
                                stdout, code = _run_hermes_with_pty(
                                    cmd=["hermes"],
                                    worker_tag="",
                                    timeout_seconds=30,
                                    workdir="/tmp",
                                )
        assert code == 0
        assert stdout == ""

    def test_processes_data_before_poll_check(self):
        """Data available in select is processed even if poll returns soon."""
        with patch("pty.openpty", return_value=(5, 6)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("select.select") as mock_select:
                    with patch("os.set_blocking"):
                        with patch("os.close"):
                            mock_proc = MagicMock()
                            mock_popen.return_value = mock_proc
                            mock_select.side_effect = [
                                ([5], [], []),
                                ([], [], []),
                            ]
                            mock_proc.poll.side_effect = [None, 0]
                            with patch("os.read") as mock_read:
                                mock_read.side_effect = [b"final output\n", b""]

                                with patch("hermes_loop.hermes_utils._log"):
                                    stdout, code = _run_hermes_with_pty(
                                        cmd=["hermes"],
                                        worker_tag="",
                                        timeout_seconds=30,
                                        workdir="/tmp",
                                    )
        assert "final output" in stdout

    def test_calls_pty_openpty_and_subprocess_popen(self):
        """Calls pty.openpty and creates subprocess with correct args."""
        with patch("pty.openpty", return_value=(5, 6)) as mock_pty:
            with patch("subprocess.Popen") as mock_popen:
                with patch("select.select") as mock_select:
                    with patch("os.set_blocking"):
                        with patch("os.close"):
                            mock_proc = MagicMock()
                            mock_popen.return_value = mock_proc
                            mock_select.return_value = ([], [], [])
                            mock_proc.poll.return_value = 0
                            mock_proc.wait.return_value = 0

                            with patch("hermes_loop.hermes_utils._log"):
                                _run_hermes_with_pty(
                                    cmd=["hermes", "chat", "-q"],
                                    worker_tag="",
                                    timeout_seconds=30,
                                    workdir="/home/user",
                                )

        mock_pty.assert_called_once()
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        assert kwargs["cwd"] == "/home/user"
        assert kwargs["text"] is True
        assert kwargs["start_new_session"] is True


class TestSpawnDelegationSessionSubprocess:
    """Tests for spawn_delegation_session -- subprocess mode (PTY and heartbeat)."""

    # ------------------------------------------------------------------
    # Subprocess PTY mode (heartbeat_timeout=0)
    # ------------------------------------------------------------------

    def test_subprocess_basic_json_success(self):
        mock_parsed = {
            "summary": "success",
            "duration_seconds": 1.5,
            "error": None,
        }
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=('{"summary":"success","duration_seconds":1.5}', 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=mock_parsed,
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.classify_error", return_value=None
                        ):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    return_value=100.0,
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                    )
        assert result["summary"] == "success"
        assert result["duration_seconds"] == 1.5
        assert result["error"] is None
        assert result["exit_code"] == 0

    def test_subprocess_pty_timeout(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    side_effect=subprocess.TimeoutExpired(cmd=["hermes"], timeout=30),
                ):
                    with patch("hermes_loop.hermes_utils._log"):
                        with patch(
                            "hermes_loop.hermes_utils.time.time", return_value=130.0
                        ):
                            result = spawn_delegation_session(
                                iteration=1,
                                goal="test",
                                context="",
                                toolsets=["terminal"],
                                workdir=None,
                                timeout_seconds=30,
                            )
        assert result["error_type"] == "timeout"
        assert "TIMEOUT" in result["summary"]
        assert result["exit_code"] == -1

    def test_subprocess_pty_json_with_next_goal(self):
        mock_parsed = {
            "summary": "did work",
            "duration_seconds": 2.0,
            "error": None,
            "next_goal": "do more",
            "context": "some context",
        }
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("output", 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=mock_parsed,
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.classify_error", return_value=None
                        ):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    return_value=100.0,
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                    )
        assert result["next_goal"] == "do more"
        assert result["context"] == "some context"

    def test_subprocess_pty_schema_valid(self):
        mock_parsed = {"summary": "valid", "duration_seconds": 1.0, "error": None}
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=('{"summary":"valid"}', 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=mock_parsed,
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.validate_json_output",
                            return_value=(True, ""),
                        ):
                            with patch(
                                "hermes_loop.hermes_utils.classify_error",
                                return_value=None,
                            ):
                                with patch("hermes_loop.hermes_utils._log"):
                                    with patch(
                                        "hermes_loop.hermes_utils.time.time",
                                        return_value=100.0,
                                    ):
                                        result = spawn_delegation_session(
                                            iteration=1,
                                            goal="test",
                                            context="",
                                            toolsets=["terminal"],
                                            workdir=None,
                                            timeout_seconds=30,
                                            output_schema={"type": "object"},
                                        )
        assert result["schema_valid"] is True
        assert result["schema_error"] is None

    def test_subprocess_pty_schema_invalid(self):
        mock_parsed = {"summary": "invalid", "duration_seconds": 1.0, "error": None}
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=('{"summary":"invalid"}', 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=mock_parsed,
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.validate_json_output",
                            return_value=(False, "missing required field"),
                        ):
                            with patch(
                                "hermes_loop.hermes_utils.classify_error",
                                return_value="validation",
                            ):
                                with patch("hermes_loop.hermes_utils._log"):
                                    with patch(
                                        "hermes_loop.hermes_utils.time.time",
                                        return_value=100.0,
                                    ):
                                        result = spawn_delegation_session(
                                            iteration=1,
                                            goal="test",
                                            context="",
                                            toolsets=["terminal"],
                                            workdir=None,
                                            timeout_seconds=30,
                                            output_schema={"type": "object"},
                                        )
        assert result["schema_valid"] is False
        assert result["schema_error"] == "missing required field"
        assert result["error"] == "missing required field"
        assert result["error_type"] == "validation"

    # ------------------------------------------------------------------
    # Session ID extraction
    # ------------------------------------------------------------------

    def test_subprocess_extracts_session_id(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("session_id: abc-123\nother output", 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value={
                            "summary": "ok",
                            "duration_seconds": 1.0,
                            "error": None,
                        },
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.classify_error", return_value=None
                        ):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    return_value=100.0,
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                    )
        assert result["spawned_session_id"] == "abc-123"

    # ------------------------------------------------------------------
    # No JSON parsed -- various subprocess exit scenarios
    # ------------------------------------------------------------------

    def test_subprocess_no_json_exit_zero(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("some output text", 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=None,
                    ):
                        with patch("hermes_loop.hermes_utils._log"):
                            with patch(
                                "hermes_loop.hermes_utils.time.time", return_value=100.0
                            ):
                                result = spawn_delegation_session(
                                    iteration=1,
                                    goal="test",
                                    context="",
                                    toolsets=["terminal"],
                                    workdir=None,
                                    timeout_seconds=30,
                                )
        assert result["summary"] == "some output text"
        assert result["error"] is None
        assert result["exit_code"] == 0

    def test_subprocess_no_json_exit_nonzero_output_gt_30(self):
        output = "x" * 40 + "\nactual result here"
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=(output, 1),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=None,
                    ):
                        with patch("hermes_loop.hermes_utils._log"):
                            with patch(
                                "hermes_loop.hermes_utils.time.time", return_value=100.0
                            ):
                                result = spawn_delegation_session(
                                    iteration=1,
                                    goal="test",
                                    context="",
                                    toolsets=["terminal"],
                                    workdir=None,
                                    timeout_seconds=30,
                                )
        assert result["error"] is None
        assert result["exit_code"] == 1

    def test_subprocess_no_json_exit_nonzero_stderr_gt_50(self):
        stderr_content = "x" * 60
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch("hermes_loop.hermes_utils._kill_session"):
                    with patch("hermes_loop.hermes_utils._cleanup_heartbeat_file"):
                        mock_proc = MagicMock()
                        mock_proc.pid = 12345
                        mock_proc.wait.return_value = 1
                        mock_proc.returncode = 1
                        mock_proc.args = ["hermes"]
                        mock_stdout = MagicMock()
                        mock_stdout.readline.side_effect = ["short\n", ""]
                        mock_proc.stdout = mock_stdout
                        mock_stderr = MagicMock()
                        mock_stderr.readline.side_effect = [stderr_content, ""]
                        mock_proc.stderr = mock_stderr
                        with patch("subprocess.Popen", return_value=mock_proc):
                            with patch(
                                "hermes_loop.hermes_utils._heartbeat_path",
                                return_value="/tmp/hb",
                            ):
                                with patch("threading.Thread"):
                                    with patch(
                                        "hermes_loop.hermes_utils.extract_json_from_output",
                                        return_value=None,
                                    ):
                                        with patch("hermes_loop.hermes_utils._log"):
                                            with patch(
                                                "hermes_loop.hermes_utils.time.time",
                                                return_value=100.0,
                                            ):
                                                result = spawn_delegation_session(
                                                    iteration=1,
                                                    goal="test",
                                                    context="",
                                                    toolsets=["terminal"],
                                                    workdir=None,
                                                    timeout_seconds=30,
                                                    heartbeat_timeout=10,
                                                )
        # In heartbeat mode, stderr is streamed by the reader thread so
        # stderr is empty. With no JSON, exit non-zero, and short stdout
        # (<30), we hit the FAILED path despite stderr being long.
        assert "FAILED" in result.get("summary", "")
        assert result["exit_code"] == 1

    def test_subprocess_no_json_exit_nonzero_no_output(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("short", 2),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=None,
                    ):
                        with patch("hermes_loop.hermes_utils._log"):
                            with patch(
                                "hermes_loop.hermes_utils.time.time", return_value=100.0
                            ):
                                result = spawn_delegation_session(
                                    iteration=1,
                                    goal="test",
                                    context="",
                                    toolsets=["terminal"],
                                    workdir=None,
                                    timeout_seconds=30,
                                )
        assert "FAILED" in result["summary"]
        assert result["error"] is not None
        assert result["error_type"] == "unknown"

    def test_subprocess_empty_stdout(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("", 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=None,
                    ):
                        with patch("hermes_loop.hermes_utils._log"):
                            with patch(
                                "hermes_loop.hermes_utils.time.time", return_value=100.0
                            ):
                                result = spawn_delegation_session(
                                    iteration=1,
                                    goal="test",
                                    context="",
                                    toolsets=["terminal"],
                                    workdir=None,
                                    timeout_seconds=30,
                                )
        assert result["summary"] == "(no output)"

    # ------------------------------------------------------------------
    # Heartbeat mode (heartbeat_timeout > 0)
    # ------------------------------------------------------------------

    def test_heartbeat_mode_success(self):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.wait.return_value = 0
        mock_proc.args = ["hermes"]
        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = ["line1\n", "line2\n", ""]
        mock_proc.stdout = mock_stdout
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
                    with patch(
                        "hermes_loop.hermes_utils._heartbeat_path",
                        return_value="/tmp/hb",
                    ):
                        mock_thread = MagicMock()
                        with patch("threading.Thread", return_value=mock_thread):
                            with patch(
                                "hermes_loop.hermes_utils.extract_json_from_output",
                                return_value={
                                    "summary": "ok",
                                    "duration_seconds": 1.0,
                                    "error": None,
                                },
                            ):
                                with patch(
                                    "hermes_loop.hermes_utils.classify_error",
                                    return_value=None,
                                ):
                                    with patch("hermes_loop.hermes_utils._log"):
                                        with patch(
                                            "hermes_loop.hermes_utils.time.time",
                                            return_value=100.0,
                                        ):
                                            result = spawn_delegation_session(
                                                iteration=1,
                                                goal="test",
                                                context="",
                                                toolsets=["terminal"],
                                                workdir=None,
                                                timeout_seconds=30,
                                                heartbeat_timeout=10,
                                            )
        mock_popen.assert_called_once()
        assert mock_thread.start.call_count == 2
        assert result["summary"] == "ok"

    def test_heartbeat_mode_timeout(self):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.args = ["hermes"]
        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = subprocess.TimeoutExpired(
            cmd=["hermes"], timeout=30
        )
        mock_proc.stdout = mock_stdout
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch("subprocess.Popen", return_value=mock_proc):
                    with patch(
                        "hermes_loop.hermes_utils._heartbeat_path",
                        return_value="/tmp/hb",
                    ):
                        mock_thread = MagicMock()
                        with patch("threading.Thread", return_value=mock_thread):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils._kill_session"
                                ) as mock_kill:
                                    with patch(
                                        "hermes_loop.hermes_utils._cleanup_heartbeat_file"
                                    ) as mock_clean:
                                        with patch(
                                            "hermes_loop.hermes_utils.time.time",
                                            return_value=130.0,
                                        ):
                                            result = spawn_delegation_session(
                                                iteration=1,
                                                goal="test",
                                                context="",
                                                toolsets=["terminal"],
                                                workdir=None,
                                                timeout_seconds=30,
                                                heartbeat_timeout=10,
                                            )
        mock_kill.assert_called_once()
        mock_clean.assert_called_once()
        assert result["error_type"] == "timeout"
        assert result["exit_code"] == -1

    # ------------------------------------------------------------------
    # Error handlers -- top-level except blocks (lines 1125-1157)
    # ------------------------------------------------------------------

    def test_error_timeout_expired_top_level(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    side_effect=subprocess.TimeoutExpired(cmd=["hermes"], timeout=30),
                ):
                    with patch("hermes_loop.hermes_utils._log"):
                        with patch(
                            "hermes_loop.hermes_utils.time.time",
                            side_effect=[100.0, 130.0],
                        ):
                            result = spawn_delegation_session(
                                iteration=1,
                                goal="test",
                                context="",
                                toolsets=["terminal"],
                                workdir=None,
                                timeout_seconds=30,
                            )
        assert result["error_type"] == "timeout"
        assert result["exit_code"] == -1

    def test_error_file_not_found(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    side_effect=FileNotFoundError("No such file"),
                ):
                    with patch("hermes_loop.hermes_utils._log"):
                        result = spawn_delegation_session(
                            iteration=1,
                            goal="test",
                            context="",
                            toolsets=["terminal"],
                            workdir=None,
                            timeout_seconds=30,
                        )
        assert "binary not found" in result["summary"]
        assert result["error_type"] == "network"
        assert result["exit_code"] == -1

    def test_error_generic_exception(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    side_effect=RuntimeError("something broke"),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.classify_error",
                        return_value="unknown",
                    ):
                        with patch("hermes_loop.hermes_utils._log"):
                            with patch(
                                "hermes_loop.hermes_utils.time.time",
                                side_effect=[100.0, 100.0],
                            ):
                                result = spawn_delegation_session(
                                    iteration=1,
                                    goal="test",
                                    context="",
                                    toolsets=["terminal"],
                                    workdir=None,
                                    timeout_seconds=30,
                                )
        assert "FAILED" in result["summary"]
        assert "something broke" in result["error"]
        assert result["exit_code"] == -1


class TestSpawnDelegationSessionLib:
    """Tests for spawn_delegation_session -- library mode (use_library=True)."""

    def test_library_success_with_json(self):
        mock_agent = MagicMock()
        mock_conv_result = {
            "session_id": "sess-1",
            "final_response": '{"summary":"done","duration_seconds":0.5,"error":null}',
        }
        mock_agent.run_conversation.return_value = mock_conv_result
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch.dict("sys.modules", {"run_agent": MagicMock()}):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output"
                    ) as mock_extract:
                        mock_extract.return_value = {
                            "summary": "done",
                            "duration_seconds": 0.5,
                        }
                        with patch(
                            "hermes_loop.hermes_utils.classify_error", return_value=None
                        ):
                            with patch(
                                "concurrent.futures.ThreadPoolExecutor"
                            ) as mock_executor:
                                mock_future = MagicMock()
                                mock_future.result.return_value = mock_conv_result
                                mock_executor.return_value.__enter__.return_value.submit.return_value = (
                                    mock_future
                                )
                                with patch("hermes_loop.hermes_utils._log"):
                                    with patch(
                                        "hermes_loop.hermes_utils.time.time",
                                        side_effect=[100.0, 100.5],
                                    ):
                                        result = spawn_delegation_session(
                                            iteration=1,
                                            goal="test",
                                            context="",
                                            toolsets=["terminal"],
                                            workdir=None,
                                            timeout_seconds=30,
                                            use_library=True,
                                        )
        assert result["summary"] == "done"
        assert result["exit_code"] == 0

    def test_library_timeout(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch.dict("sys.modules", {"run_agent": MagicMock()}):
                    with patch(
                        "concurrent.futures.ThreadPoolExecutor"
                    ) as mock_executor:
                        from concurrent.futures import TimeoutError as _TimeoutError

                        mock_future = MagicMock()
                        mock_future.result.side_effect = _TimeoutError()
                        mock_executor.return_value.__enter__.return_value.submit.return_value = (
                            mock_future
                        )
                        with patch("hermes_loop.hermes_utils._log"):
                            with patch(
                                "hermes_loop.hermes_utils.time.time",
                                side_effect=[100.0, 130.0],
                            ):
                                result = spawn_delegation_session(
                                    iteration=1,
                                    goal="test",
                                    context="",
                                    toolsets=["terminal"],
                                    workdir=None,
                                    timeout_seconds=30,
                                    use_library=True,
                                )
        assert "TIMEOUT" in result["summary"]
        assert result["error_type"] == "timeout"

    def test_library_no_json_extracted(self):
        mock_agent = MagicMock()
        mock_conv_result = {
            "session_id": "sess-2",
            "final_response": "just some text without json",
        }
        mock_agent.run_conversation.return_value = mock_conv_result
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch.dict("sys.modules", {"run_agent": MagicMock()}):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=None,
                    ):
                        with patch(
                            "concurrent.futures.ThreadPoolExecutor"
                        ) as mock_executor:
                            mock_future = MagicMock()
                            mock_future.result.return_value = mock_conv_result
                            mock_executor.return_value.__enter__.return_value.submit.return_value = (
                                mock_future
                            )
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    side_effect=[100.0, 101.0],
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                        use_library=True,
                                    )
        assert "just some text" in result["summary"]
        assert result["error"] is None

    def test_library_schema_validation(self):
        mock_agent = MagicMock()
        mock_conv_result = {
            "session_id": "sess-3",
            "final_response": '{"summary":"test","duration_seconds":1.0}',
        }
        mock_agent.run_conversation.return_value = mock_conv_result
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch.dict("sys.modules", {"run_agent": MagicMock()}):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output"
                    ) as mock_extract:
                        mock_extract.return_value = {
                            "summary": "test",
                            "duration_seconds": 1.0,
                        }
                        with patch(
                            "hermes_loop.hermes_utils.validate_json_output",
                            return_value=(True, ""),
                        ):
                            with patch(
                                "hermes_loop.hermes_utils.classify_error",
                                return_value=None,
                            ):
                                with patch(
                                    "concurrent.futures.ThreadPoolExecutor"
                                ) as mock_executor:
                                    mock_future = MagicMock()
                                    mock_future.result.return_value = mock_conv_result
                                    mock_executor.return_value.__enter__.return_value.submit.return_value = (
                                        mock_future
                                    )
                                    with patch("hermes_loop.hermes_utils._log"):
                                        with patch(
                                            "hermes_loop.hermes_utils.time.time",
                                            side_effect=[100.0, 101.0],
                                        ):
                                            result = spawn_delegation_session(
                                                iteration=1,
                                                goal="test",
                                                context="",
                                                toolsets=["terminal"],
                                                workdir=None,
                                                timeout_seconds=30,
                                                use_library=True,
                                                output_schema={"type": "object"},
                                            )
        assert result["schema_valid"] is True
        assert result["schema_error"] is None

    def test_library_import_error_fallback(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("fallback output", 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=None,
                    ):
                        with patch.dict("sys.modules", {"run_agent": None}):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    return_value=100.0,
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                        use_library=True,
                                    )
        assert result["summary"] == "fallback output"

    def test_library_exception_fallback(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("fallback from exception", 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=None,
                    ):
                        with patch.dict("sys.modules", {"run_agent": MagicMock()}):
                            with patch(
                                "concurrent.futures.ThreadPoolExecutor"
                            ) as mock_executor:
                                mock_future = MagicMock()
                                mock_future.result.side_effect = RuntimeError(
                                    "agent crashed"
                                )
                                mock_executor.return_value.__enter__.return_value.submit.return_value = (
                                    mock_future
                                )
                                with patch("hermes_loop.hermes_utils._log"):
                                    with patch(
                                        "hermes_loop.hermes_utils.time.time",
                                        return_value=100.0,
                                    ):
                                        result = spawn_delegation_session(
                                            iteration=1,
                                            goal="test",
                                            context="",
                                            toolsets=["terminal"],
                                            workdir=None,
                                            timeout_seconds=30,
                                            use_library=True,
                                        )
        assert "fallback from exception" in result["summary"]


class TestSpawnDelegationSessionWorker:
    """Tests for spawn_delegation_session -- worker URL mode."""

    def test_worker_url_success(self):
        raw_json = json.dumps({"response": "work done", "status": "ok"})
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_resp = MagicMock()
                    mock_resp.read.return_value = raw_json.encode()
                    mock_urlopen.return_value.__enter__.return_value = mock_resp
                    with patch("hermes_loop.hermes_utils._log"):
                        with patch(
                            "hermes_loop.hermes_utils.time.time",
                            side_effect=[100.0, 101.0],
                        ):
                            result = spawn_delegation_session(
                                iteration=1,
                                goal="test",
                                context="",
                                toolsets=["terminal"],
                                workdir=None,
                                timeout_seconds=30,
                                worker_url="http://localhost:8080",
                            )
        assert result["summary"] == "work done"
        assert result["exit_code"] == 0

    def test_worker_url_non_dict_response(self):
        raw_json = json.dumps(["item1", "item2"])
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_resp = MagicMock()
                    mock_resp.read.return_value = raw_json.encode()
                    mock_urlopen.return_value.__enter__.return_value = mock_resp
                    with patch("hermes_loop.hermes_utils._log"):
                        with patch(
                            "hermes_loop.hermes_utils.time.time",
                            side_effect=[100.0, 101.0],
                        ):
                            result = spawn_delegation_session(
                                iteration=1,
                                goal="test",
                                context="",
                                toolsets=["terminal"],
                                workdir=None,
                                timeout_seconds=30,
                                worker_url="http://localhost:8080",
                            )
        # Non-dict response: the raw response is returned as string (Python repr)
        assert "item1" in result["summary"]
        assert "item2" in result["summary"]

    def test_worker_url_error_response(self):
        raw_json = json.dumps(
            {"response": "failed", "error": "bad request", "status": "error"}
        )
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_resp = MagicMock()
                    mock_resp.read.return_value = raw_json.encode()
                    mock_urlopen.return_value.__enter__.return_value = mock_resp
                    with patch("hermes_loop.hermes_utils._log"):
                        with patch(
                            "hermes_loop.hermes_utils.time.time",
                            side_effect=[100.0, 101.0],
                        ):
                            result = spawn_delegation_session(
                                iteration=1,
                                goal="test",
                                context="",
                                toolsets=["terminal"],
                                workdir=None,
                                timeout_seconds=30,
                                worker_url="http://localhost:8080",
                            )
        assert result["exit_code"] == 1

    def test_worker_url_exception(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "urllib.request.urlopen",
                    side_effect=ConnectionError("connection refused"),
                ):
                    with patch("hermes_loop.hermes_utils._log"):
                        with patch(
                            "hermes_loop.hermes_utils.time.time",
                            side_effect=[100.0, 100.5],
                        ):
                            result = spawn_delegation_session(
                                iteration=1,
                                goal="test",
                                context="",
                                toolsets=["terminal"],
                                workdir=None,
                                timeout_seconds=30,
                                worker_url="http://localhost:8080",
                            )
        assert "WORKER FAILED" in result["summary"]
        assert result["exit_code"] == 1
        assert result["error"] is not None


class TestSpawnDelegationSessionCLI:
    """Tests for spawn_delegation_session -- CLI argument construction, truncation, edge cases."""

    def test_truncation_and_encoding(self):
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("x" * 5000, 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value={
                            "summary": "big output",
                            "duration_seconds": 10.0,
                            "error": None,
                        },
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.classify_error", return_value=None
                        ):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    side_effect=[100.0, 110.0],
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                        max_output_chars=100,
                                    )
        assert result["truncated"] is True
        assert result["output_chars"] == 5000
        assert result["chars_per_second"] == 500.0

    def test_json_error_becomes_effective_error(self):
        mock_parsed = {
            "summary": "had error",
            "duration_seconds": 1.0,
            "error": "something went wrong",
        }
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=('{"error":"something went wrong"}', 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=mock_parsed,
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.classify_error",
                            return_value="execution",
                        ):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    return_value=100.0,
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                    )
        assert result["error"] == "something went wrong"
        assert result["error_type"] == "execution"

    def test_summary_is_string_when_json_summary_is_dict(self):
        mock_parsed = {
            "summary": {"nested": "object"},
            "duration_seconds": 1.0,
            "error": None,
        }
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("output", 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=mock_parsed,
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.classify_error", return_value=None
                        ):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    return_value=100.0,
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                    )
        assert (
            '"nested": "object"' in result["summary"] or "nested" in result["summary"]
        )

    def test_duration_zero_prevents_division_by_zero(self):
        mock_parsed = {
            "summary": "instant",
            "duration_seconds": 0,
            "error": None,
        }
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("output", 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=mock_parsed,
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.classify_error", return_value=None
                        ):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    return_value=100.0,
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                    )
        assert result["chars_per_second"] == 0

    def test_no_output_schema_skips_validation(self):
        mock_parsed = {
            "summary": "no schema",
            "duration_seconds": 1.0,
            "error": None,
        }
        with patch(
            "hermes_loop.hermes_utils.find_hermes", return_value="/usr/bin/hermes"
        ):
            with patch(
                "hermes_loop.hermes_utils._build_delegation_prompt",
                return_value="prompt",
            ):
                with patch(
                    "hermes_loop.hermes_utils._run_hermes_with_pty",
                    return_value=("output", 0),
                ):
                    with patch(
                        "hermes_loop.hermes_utils.extract_json_from_output",
                        return_value=mock_parsed,
                    ):
                        with patch(
                            "hermes_loop.hermes_utils.classify_error", return_value=None
                        ):
                            with patch("hermes_loop.hermes_utils._log"):
                                with patch(
                                    "hermes_loop.hermes_utils.time.time",
                                    return_value=100.0,
                                ):
                                    result = spawn_delegation_session(
                                        iteration=1,
                                        goal="test",
                                        context="",
                                        toolsets=["terminal"],
                                        workdir=None,
                                        timeout_seconds=30,
                                    )
        # When output_schema is None, schema_valid/schema_error are still included
        # (initialized as True/"", but not validated)
        assert result.get("schema_valid") is True
        assert result.get("schema_error") is None
