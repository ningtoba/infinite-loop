"""ANSI color support for CLI output with terminal detection.

Provides a Colorizer class with auto/always/never mode and a global
singleton that respects --color=auto|always|never.

Module-level constant: colorizer — ready to use anywhere.
"""

import os
import re
import sys


class Colorizer:
    """ANSI color helper with terminal capability detection.

    Modes:
      auto (default):  emit colors only when stdout is a TTY
      always:          emit colors unconditionally (e.g. for piped output via --color=always)
      never:           strip all ANSI codes

    Color names map to standard 8/16 ANSI escape sequences.
    """

    # ANSI escape sequences
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD_RED = "\033[1;91m"
    BOLD_GREEN = "\033[1;92m"
    BOLD_YELLOW = "\033[1;93m"
    BOLD_BLUE = "\033[1;94m"
    BOLD_CYAN = "\033[1;96m"
    BOLD_MAGENTA = "\033[1;95m"
    GREY = "\033[90m"

    _NAMED = {
        "reset": RESET,
        "bold": BOLD,
        "dim": DIM,
        "red": RED,
        "green": GREEN,
        "yellow": YELLOW,
        "blue": BLUE,
        "magenta": MAGENTA,
        "cyan": CYAN,
        "white": WHITE,
        "bold_red": BOLD_RED,
        "bold_green": BOLD_GREEN,
        "bold_yellow": BOLD_YELLOW,
        "bold_blue": BOLD_BLUE,
        "bold_cyan": BOLD_CYAN,
        "bold_magenta": BOLD_MAGENTA,
        "grey": GREY,
    }

    def __init__(self, mode: str = "auto"):
        if mode not in ("auto", "always", "never"):
            mode = "auto"
        self._mode = mode

    def _enabled(self) -> bool:
        if self._mode == "never":
            return False
        if self._mode == "always":
            return True
        # auto: check TTY + NO_COLOR
        if os.environ.get("NO_COLOR"):
            return False
        return sys.stdout.isatty()

    def colorize(self, text: str, *names: str) -> str:
        """Wrap *text* in ANSI escape sequences for each named color.

        Names are applied in order (e.g. "bold", "green" → bold green).
        If colors are disabled, returns text unchanged.
        """
        if not self._enabled() or not names:
            return text
        codes = "".join(self._NAMED.get(n, "") for n in names)
        return f"{codes}{text}{self.RESET}"

    def header(self, text: str) -> str:
        """Format a section header — bold cyan."""
        return self.colorize(text, "bold_cyan")

    def subheader(self, text: str) -> str:
        """Format a sub-section header — bold blue."""
        return self.colorize(text, "bold_blue")

    def ok(self, text: str) -> str:
        """Format a success message — bold green."""
        return self.colorize(text, "bold_green")

    def fail(self, text: str) -> str:
        """Format an error message — bold red."""
        return self.colorize(text, "bold_red")

    def warn(self, text: str) -> str:
        """Format a warning message — bold yellow."""
        return self.colorize(text, "bold_yellow")

    def dim(self, text: str) -> str:
        """Format dim/low-priority text — grey."""
        return self.colorize(text, "grey")

    def highlight(self, text: str) -> str:
        """Format an inline highlight — bold yellow."""
        return self.colorize(text, "bold_yellow")

    def flag(self, text: str) -> str:
        """Format a CLI flag name — cyan."""
        return self.colorize(text, "cyan")

    def value(self, text: str) -> str:
        """Format a value/example — yellow."""
        return self.colorize(text, "yellow")

    def group_title(self, text: str) -> str:
        """Format a [Group Title] bracket — bold magenta."""
        return self.colorize(text, "bold_magenta")

    def summary_ok(self, text: str) -> str:
        """Format an OK summary line — green."""
        return self.colorize(text, "green")

    def summary_fail(self, text: str) -> str:
        """Format a FAIL summary line — red."""
        return self.colorize(text, "red")

    # ── Tag helpers for log output ──────────────────────────────────────────
    def tag_ok(self) -> str:
        return self.colorize("[OK]", "bold_green")

    def tag_fail(self) -> str:
        return self.colorize("[FAIL]", "bold_red")

    def tag_warn(self) -> str:
        return self.colorize("[WARN]", "bold_yellow")

    def tag_info(self) -> str:
        return self.colorize("[INFO]", "bold_blue")

    def tag_summary(self) -> str:
        return self.colorize("[SUMMARY]", "bold_cyan")

    def tag_suggest(self) -> str:
        return self.colorize("[SUGGEST]", "bold_magenta")


# Module-level singleton — instantiate from main() with the --color arg
colorizer = Colorizer("auto")


def configure_color_mode(mode: str) -> None:
    """Reconfigure the global colorizer singleton.

    Should be called from main() after parsing --color.
    """
    global colorizer
    colorizer = Colorizer(mode)


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from *text*."""

    return re.sub(r"\033\[[0-9;]*m", "", text)
