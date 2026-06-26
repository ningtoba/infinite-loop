"""
hermes_loop — Infinite loop daemon package.

Re-exports the CLI entry point and version constants.
"""

from .config import LAUNCH_LOOP_VERSION
from .cli import main

VERSION = LAUNCH_LOOP_VERSION

__all__ = ["main", "VERSION", "LAUNCH_LOOP_VERSION"]
