"""
hermes_loop — Infinite loop daemon package.

Re-exports the CLI entry point and version constants.
"""

from .config import LAUNCH_LOOP_VERSION
from .cli import main

VERSION = LAUNCH_LOOP_VERSION
__version__ = VERSION

__all__ = ["LAUNCH_LOOP_VERSION", "VERSION", "__version__", "main"]
