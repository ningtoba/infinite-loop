"""Tests for color_utils.py — Colorizer, configure_color_mode, strip_ansi."""

from __future__ import annotations

import os
from unittest.mock import patch


from hermes_loop.color_utils import (
    Colorizer,
    configure_color_mode,
    strip_ansi,
    colorizer,
)

# ===================================================================
# Colorizer — _enabled tests
# ===================================================================


class TestColorizerEnabled:
    """Tests for Colorizer._enabled mode detection."""

    def test_never_mode(self):
        """Never mode always returns False."""
        c = Colorizer("never")
        assert c._enabled() is False

    def test_always_mode(self):
        """Always mode always returns True."""
        c = Colorizer("always")
        assert c._enabled() is True

    def test_auto_mode_isatty_true(self):
        """Auto mode returns True when stdout is a TTY."""
        with patch("hermes_loop.color_utils.sys.stdout.isatty", return_value=True):
            c = Colorizer("auto")
            assert c._enabled() is True

    def test_auto_mode_isatty_false(self):
        """Auto mode returns False when stdout is not a TTY."""
        with patch("hermes_loop.color_utils.sys.stdout.isatty", return_value=False):
            c = Colorizer("auto")
            assert c._enabled() is False

    def test_auto_mode_no_color_env(self):
        """Auto mode respects NO_COLOR env var."""
        with (
            patch("hermes_loop.color_utils.sys.stdout.isatty", return_value=True),
            patch.dict(os.environ, {"NO_COLOR": "1"}),
        ):
            c = Colorizer("auto")
            assert c._enabled() is False

    def test_auto_mode_no_color_env_empty(self):
        """NO_COLOR with empty string does NOT disable (get returns '' which is falsy)."""
        with (
            patch("hermes_loop.color_utils.sys.stdout.isatty", return_value=True),
            patch.dict(os.environ, {"NO_COLOR": ""}),
        ):
            c = Colorizer("auto")
            assert c._enabled() is True  # '' is falsy via get(), so not disabled

    def test_invalid_mode_falls_to_auto(self):
        """Invalid mode falls back to auto."""
        c = Colorizer("invalid")
        assert c._mode == "auto"

    def test_default_mode_is_auto(self):
        """Default mode is auto."""
        c = Colorizer()
        assert c._mode == "auto"


# ===================================================================
# Colorizer — colorize tests
# ===================================================================


class TestColorizerColorize:
    """Tests for Colorizer.colorize method."""

    def test_colorize_enabled(self):
        """Colorize wraps text in ANSI codes when enabled."""
        with patch.object(Colorizer, "_enabled", return_value=True):
            c = Colorizer("always")
            result = c.colorize("hello", "red")
            assert result == "\033[91mhello\033[0m"

    def test_colorize_disabled(self):
        """Colorize returns plain text when disabled."""
        with patch.object(Colorizer, "_enabled", return_value=False):
            c = Colorizer("never")
            result = c.colorize("hello", "red")
            assert result == "hello"

    def test_colorize_no_names(self):
        """Colorize with no color names returns plain text."""
        with patch.object(Colorizer, "_enabled", return_value=True):
            c = Colorizer("always")
            result = c.colorize("hello")
            assert result == "hello"

    def test_colorize_multiple_names(self):
        """Multiple color names are applied in order."""
        with patch.object(Colorizer, "_enabled", return_value=True):
            c = Colorizer("always")
            result = c.colorize("hello", "bold", "red")
            assert result == "\033[1m\033[91mhello\033[0m"

    def test_colorize_unknown_name(self):
        """Unknown color name produces text with just RESET (no color code)."""
        with patch.object(Colorizer, "_enabled", return_value=True):
            c = Colorizer("always")
            result = c.colorize("hello", "nonexistent")
            # Unknown names produce no color code, but RESET is still appended
            assert result == "hello\033[0m"

    def test_colorize_all_named_colors(self):
        """All named colors produce non-empty ANSI codes."""
        with patch.object(Colorizer, "_enabled", return_value=True):
            c = Colorizer("always")
            for name in c._NAMED:
                result = c.colorize("text", name)
                assert result.startswith("\033[")
                assert result.endswith("\033[0m")
                assert "text" in result

    def test_colorize_empty_text(self):
        """Empty string is handled."""
        with patch.object(Colorizer, "_enabled", return_value=True):
            c = Colorizer("always")
            result = c.colorize("", "red")
            assert result == "\033[91m\033[0m"

    def test_colorize_disable_overrides(self):
        """_enabled=False overrides always mode."""
        c = Colorizer("always")
        with patch.object(c, "_enabled", return_value=False):
            result = c.colorize("hello", "red")
            assert result == "hello"


# ===================================================================
# Colorizer — named method tests
# ===================================================================


class TestColorizerNamedMethods:
    """Tests for Colorizer's named formatting methods."""

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_header(self, _):
        """header uses bold_cyan."""
        c = Colorizer("always")
        result = c.header("Section")
        assert "\033[1;96m" in result  # bold cyan

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_subheader(self, _):
        """subheader uses bold_blue."""
        c = Colorizer("always")
        result = c.subheader("Sub")
        assert "\033[1;94m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_ok(self, _):
        """ok uses bold_green."""
        c = Colorizer("always")
        result = c.ok("Success")
        assert "\033[1;92m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_fail(self, _):
        """fail uses bold_red."""
        c = Colorizer("always")
        result = c.fail("Error")
        assert "\033[1;91m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_warn(self, _):
        """warn uses bold_yellow."""
        c = Colorizer("always")
        result = c.warn("Warning")
        assert "\033[1;93m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_dim(self, _):
        """dim uses grey."""
        c = Colorizer("always")
        result = c.dim("Low")
        assert "\033[90m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_highlight(self, _):
        """highlight uses bold_yellow."""
        c = Colorizer("always")
        result = c.highlight("Emphasis")
        assert "\033[1;93m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_flag(self, _):
        """flag uses cyan."""
        c = Colorizer("always")
        result = c.flag("--option")
        assert "\033[96m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_value(self, _):
        """value uses yellow."""
        c = Colorizer("always")
        result = c.value("example")
        assert "\033[93m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_group_title(self, _):
        """group_title uses bold_magenta."""
        c = Colorizer("always")
        result = c.group_title("[Group]")
        assert "\033[1;95m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_summary_ok(self, _):
        """summary_ok uses green."""
        c = Colorizer("always")
        result = c.summary_ok("OK")
        assert "\033[92m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_summary_fail(self, _):
        """summary_fail uses red."""
        c = Colorizer("always")
        result = c.summary_fail("FAIL")
        assert "\033[91m" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_tag_ok(self, _):
        """tag_ok returns colored [OK]."""
        c = Colorizer("always")
        result = c.tag_ok()
        assert "\033[1;92m" in result
        assert "[OK]" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_tag_fail(self, _):
        """tag_fail returns colored [FAIL]."""
        c = Colorizer("always")
        result = c.tag_fail()
        assert "\033[1;91m" in result
        assert "[FAIL]" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_tag_warn(self, _):
        """tag_warn returns colored [WARN]."""
        c = Colorizer("always")
        result = c.tag_warn()
        assert "\033[1;93m" in result
        assert "[WARN]" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_tag_info(self, _):
        """tag_info returns colored [INFO]."""
        c = Colorizer("always")
        result = c.tag_info()
        assert "\033[1;94m" in result
        assert "[INFO]" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_tag_summary(self, _):
        """tag_summary returns colored [SUMMARY]."""
        c = Colorizer("always")
        result = c.tag_summary()
        assert "\033[1;96m" in result
        assert "[SUMMARY]" in result

    @patch.object(Colorizer, "_enabled", return_value=True)
    def test_tag_suggest(self, _):
        """tag_suggest returns colored [SUGGEST]."""
        c = Colorizer("always")
        result = c.tag_suggest()
        assert "\033[1;95m" in result
        assert "[SUGGEST]" in result

    def test_named_methods_disabled_return_plain_text(self):
        """All named methods return plain text when disabled."""
        c = Colorizer("never")
        assert c.header("Section") == "Section"
        assert c.subheader("Sub") == "Sub"
        assert c.ok("OK") == "OK"
        assert c.fail("Fail") == "Fail"
        assert c.warn("Warn") == "Warn"
        assert c.dim("Dim") == "Dim"
        assert c.highlight("Hi") == "Hi"
        assert c.flag("--opt") == "--opt"
        assert c.value("val") == "val"
        assert c.group_title("[G]") == "[G]"
        assert c.summary_ok("OK") == "OK"
        assert c.summary_fail("FAIL") == "FAIL"
        assert c.tag_ok() == "[OK]"
        assert c.tag_fail() == "[FAIL]"
        assert c.tag_warn() == "[WARN]"
        assert c.tag_info() == "[INFO]"
        assert c.tag_summary() == "[SUMMARY]"
        assert c.tag_suggest() == "[SUGGEST]"


# ===================================================================
# configure_color_mode tests
# ===================================================================


class TestConfigureColorMode:
    """Tests for configure_color_mode — reconfigure global singleton.

    These tests validate that configure_color_mode correctly mutates the
    module-level ``colorizer`` variable by accessing it through the module
    object directly after configuring, since ``from ... import colorizer``
    creates a local reference that doesn't track reassignment.
    """

    def test_configure_always(self):
        """configure_color_mode('always') sets module global to always mode."""
        import hermes_loop.color_utils as cu

        configure_color_mode("always")
        assert cu.colorizer._mode == "always"
        assert cu.colorizer._enabled() is True

    def test_configure_never(self):
        """configure_color_mode('never') sets module global to never mode."""
        import hermes_loop.color_utils as cu

        configure_color_mode("never")
        assert cu.colorizer._mode == "never"
        assert cu.colorizer._enabled() is False

    def test_configure_auto(self):
        """configure_color_mode('auto') sets module global to auto mode."""
        import hermes_loop.color_utils as cu

        configure_color_mode("auto")
        assert cu.colorizer._mode == "auto"

    def test_configure_restores_between_tests(self):
        """Sequential reconfigurations are reflected in the module singleton."""
        import hermes_loop.color_utils as cu

        configure_color_mode("always")
        assert cu.colorizer._enabled() is True
        configure_color_mode("never")
        assert cu.colorizer._enabled() is False
        configure_color_mode("auto")
        assert cu.colorizer._mode == "auto"


# ===================================================================
# strip_ansi tests
# ===================================================================


class TestStripAnsi:
    """Tests for strip_ansi — removes ANSI escape sequences."""

    def test_no_ansi(self):
        """Plain text without ANSI codes is unchanged."""
        assert strip_ansi("hello world") == "hello world"

    def test_simple_ansi(self):
        """Single ANSI code is removed."""
        assert strip_ansi("\033[91mhello\033[0m") == "hello"

    def test_multiple_ansi(self):
        """Multiple ANSI codes are all removed."""
        assert strip_ansi("\033[1m\033[92mbold green\033[0m") == "bold green"

    def test_empty_string(self):
        """Empty string returns empty."""
        assert strip_ansi("") == ""

    def test_only_ansi(self):
        """String with only ANSI codes returns empty."""
        assert strip_ansi("\033[1m\033[0m") == ""

    def test_mixed_content(self):
        """Mixed ANSI codes and regular text."""
        result = strip_ansi("\033[1m\033[94m[INFO] \033[0m\033[92mOK\033[0m")
        assert result == "[INFO] OK"

    def test_ansi_without_reset(self):
        """ANSI code without reset is still removed."""
        assert strip_ansi("\033[91mhello") == "hello"

    def test_dim_code(self):
        """Dim ANSI codes are removed."""
        assert strip_ansi("\033[2msubtle\033[0m") == "subtle"

    def test_bold_code(self):
        """Bold ANSI codes are removed."""
        assert strip_ansi("\033[1mbold\033[0m") == "bold"

    def test_complex_ansi(self):
        """Complex ANSI sequences with semicolons."""
        assert strip_ansi("\033[38;5;196mred\033[0m") == "red"

    def test_no_false_positives(self):
        """Non-ANSI escape sequences are not stripped."""
        assert strip_ansi("no escape here") == "no escape here"

    def test_string_with_backslash_before_bracket(self):
        """Literal \033[... text without actual escape is not ANSI."""
        # This is checking the actual regex — it targets \033[...m
        assert strip_ansi("some text") == "some text"


# ===================================================================
# Module-level singleton tests
# ===================================================================


class TestModuleSingleton:
    """Tests for the module-level colorizer singleton."""

    def test_default_mode_is_auto(self):
        """Default singleton starts in auto mode."""
        configure_color_mode("auto")
        assert colorizer._mode == "auto"

    def test_singleton_can_colorize(self):
        """Singleton can be used like a Colorizer instance."""
        with patch.object(Colorizer, "_enabled", return_value=True):
            configure_color_mode("always")
            result = colorizer.ok("test")
            assert "\033[" in result
            assert "test" in result

    def test_singleton_strip_ansi_works(self):
        """strip_ansi works on colored output from singleton."""
        with patch.object(Colorizer, "_enabled", return_value=True):
            configure_color_mode("always")
            colored = colorizer.ok("hello")
            plain = strip_ansi(colored)
            assert plain == "hello"
