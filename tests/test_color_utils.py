"""Tests for Colorizer and related utilities."""

import os
import sys

from omp_loop.color_utils import Colorizer, configure_color_mode, strip_ansi


class TestModeNever:
    """Colorizer in 'never' mode should not produce ANSI codes."""

    def setup_method(self):
        self.c = Colorizer(mode="never")

    def test_colorize_returns_plain_text(self):
        """colorize with mode=never returns text unchanged."""
        result = self.c.colorize("hello", "red")
        assert result == "hello"
        # Verify no ANSI escape codes
        assert "\033" not in result

    def test_header_no_color(self):
        """header() in never mode returns plain text."""
        assert self.c.header("Section") == "Section"

    def test_subheader_no_color(self):
        """subheader() in never mode returns plain text."""
        assert self.c.subheader("Sub") == "Sub"

    def test_ok_no_color(self):
        """ok() in never mode returns plain text."""
        assert self.c.ok("Success") == "Success"

    def test_fail_no_color(self):
        """fail() in never mode returns plain text."""
        assert self.c.fail("Error") == "Error"

    def test_warn_no_color(self):
        """warn() in never mode returns plain text."""
        assert self.c.warn("Warning") == "Warning"

    def test_dim_no_color(self):
        """dim() in never mode returns plain text."""
        assert self.c.dim("Detail") == "Detail"

    def test_highlight_no_color(self):
        """highlight() in never mode returns plain text."""
        assert self.c.highlight("Note") == "Note"

    def test_flag_no_color(self):
        """flag() in never mode returns plain text."""
        assert self.c.flag("--option") == "--option"

    def test_value_no_color(self):
        """value() in never mode returns plain text."""
        assert self.c.value("42") == "42"

    def test_group_title_no_color(self):
        """group_title() in never mode returns plain text."""
        assert self.c.group_title("[Group]") == "[Group]"

    def test_summary_ok_no_color(self):
        """summary_ok() in never mode returns plain text."""
        assert self.c.summary_ok("OK") == "OK"

    def test_summary_fail_no_color(self):
        """summary_fail() in never mode returns plain text."""
        assert self.c.summary_fail("FAIL") == "FAIL"

    def test_tag_ok_no_color(self):
        """tag_ok() in never mode returns plain text."""
        assert self.c.tag_ok() == "[OK]"

    def test_tag_fail_no_color(self):
        """tag_fail() in never mode returns plain text."""
        assert self.c.tag_fail() == "[FAIL]"

    def test_tag_warn_no_color(self):
        """tag_warn() in never mode returns plain text."""
        assert self.c.tag_warn() == "[WARN]"

    def test_tag_info_no_color(self):
        """tag_info() in never mode returns plain text."""
        assert self.c.tag_info() == "[INFO]"

    def test_tag_summary_no_color(self):
        """tag_summary() in never mode returns plain text."""
        assert self.c.tag_summary() == "[SUMMARY]"

    def test_tag_suggest_no_color(self):
        """tag_suggest() in never mode returns plain text."""
        assert self.c.tag_suggest() == "[SUGGEST]"

    def test_colorize_with_empty_names(self):
        """colorize with no color names returns text unchanged."""
        assert self.c.colorize("text") == "text"


class TestModeAlways:
    """Colorizer in 'always' mode should produce ANSI codes."""

    def setup_method(self):
        self.c = Colorizer(mode="always")

    def test_colorize_produces_ansi(self):
        """colorize wraps text in ANSI codes."""
        result = self.c.colorize("hello", "red")
        assert result.startswith("\033")
        assert result.endswith(Colorizer.RESET)
        assert "hello" in result

    def test_header_produces_ansi(self):
        """header() produces ANSI codes."""
        result = self.c.header("Section")
        assert "\033" in result

    def test_ok_produces_ansi(self):
        """ok() produces ANSI codes."""
        result = self.c.ok("Success")
        assert "\033" in result

    def test_fail_produces_ansi(self):
        """fail() produces ANSI codes."""
        result = self.c.fail("Error")
        assert "\033" in result

    def test_multiple_color_names(self):
        """Multiple color names are combined."""
        result = self.c.colorize("bold text", "bold", "red")
        assert "\033[1m" in result  # bold
        assert "\033[91m" in result  # red

    def test_unknown_color_name_still_appends_reset(self):
        """Unknown color names produce no color codes but still append RESET."""
        result = self.c.colorize("text", "nonexistent")
        # RESET is always appended even when no color codes matched
        assert result == "text\033[0m"

    def test_dim_produces_grey(self):
        """dim() uses grey color."""
        result = self.c.dim("faint")
        assert "\033[90m" in result

    def test_summary_ok_is_green(self):
        """summary_ok() uses green (not bold_green)."""
        result = self.c.summary_ok("DONE")
        assert "\033[92m" in result  # green

    def test_summary_fail_is_red(self):
        """summary_fail() uses red (not bold_red)."""
        result = self.c.summary_fail("FAILED")
        assert "\033[91m" in result  # red

    def test_tag_methods_produce_bracketed_labels(self):
        """Tag methods produce bracketed labels with ANSI."""
        assert "\033" in self.c.tag_ok()
        assert "\033" in self.c.tag_warn()
        assert "\033" in self.c.tag_info()


class TestAutoMode:
    """Colorizer in 'auto' mode — depends on TTY.

    When stdout is not a TTY (e.g., during pytest), auto mode should
    produce no ANSI codes.
    """

    def test_auto_non_tty_no_color(self):
        """In non-TTY, auto mode produces no ANSI codes."""
        c = Colorizer(mode="auto")
        result = c.colorize("hello", "red")
        # During pytest, stdout is likely not a TTY
        if not sys.stdout.isatty():
            assert result == "hello"
        # If running interactively, just don't crash

    def test_auto_with_no_color_env(self):
        """NO_COLOR env var disables color in auto mode."""
        os.environ["NO_COLOR"] = "1"
        try:
            c = Colorizer(mode="auto")
            result = c.colorize("hello", "red")
            assert result == "hello"
        finally:
            del os.environ["NO_COLOR"]


class TestStripAnsi:
    """Tests for strip_ansi()."""

    def test_strip_ansi_remove_red(self):
        """Strip red ANSI codes."""
        colored = "\033[91mred\033[0m"
        assert strip_ansi(colored) == "red"

    def test_strip_ansi_remove_bold(self):
        """Strip bold ANSI codes."""
        colored = "\033[1mbold\033[0m"
        assert strip_ansi(colored) == "bold"

    def test_strip_ansi_remove_multi(self):
        """Strip multiple ANSI sequences."""
        colored = "\033[1m\033[91mbold red\033[0m"
        assert strip_ansi(colored) == "bold red"

    def test_strip_ansi_plain_text(self):
        """Plain text is unchanged."""
        assert strip_ansi("hello") == "hello"

    def test_strip_ansi_empty(self):
        """Empty string stays empty."""
        assert strip_ansi("") == ""

    def test_strip_ansi_no_match(self):
        """Text without ANSI codes is unchanged."""
        assert strip_ansi("no codes here") == "no codes here"

    def test_strip_ansi_mixed(self):
        """Mixed plain and ANSI text is properly stripped."""
        text = "Normal \033[92mgreen\033[0m and \033[1mbold\033[0m"
        assert strip_ansi(text) == "Normal green and bold"


class TestConfigureColorMode:
    """Tests for configure_color_mode()."""

    def test_configure_mode_never(self):
        """configure_color_mode('never') disables the global colorizer."""
        configure_color_mode("never")
        from omp_loop.color_utils import colorizer

        result = colorizer.colorize("test", "red")
        assert result == "test"

    def test_configure_mode_always(self):
        """configure_color_mode('always') enables the global colorizer."""
        configure_color_mode("always")
        from omp_loop.color_utils import colorizer

        result = colorizer.colorize("test", "red")
        assert "\033" in result

    def test_configure_mode_invalid(self):
        """Invalid mode falls back to auto."""
        configure_color_mode("invalid")
        from omp_loop.color_utils import colorizer

        assert colorizer._mode == "auto"


class TestInvalidMode:
    """Colorizer with invalid mode falls back to auto."""

    def test_invalid_mode_defaults_to_auto(self):
        """Invalid mode defaults to auto."""
        c = Colorizer(mode="invalid")
        assert c._mode == "auto"


class TestColorizeEdgeCases:
    """Edge cases for colorize()."""

    def test_colorize_empty_text(self):
        """colorize with empty text."""
        c = Colorizer(mode="always")
        result = c.colorize("", "red")
        assert "\033" in result
        assert result.endswith(Colorizer.RESET)

    def test_colorize_unknown_only(self):
        """colorize with only unknown names still appends RESET."""
        c = Colorizer(mode="always")
        result = c.colorize("text", "fakecolor")
        assert result == "text\033[0m"
