"""
pi-loop — A lightweight, self-contained task automation daemon.

Watches files, runs tasks in a loop, tracks progress in a JSON ledger,
and integrates with the pi coding agent as a background worker.
"""

from .config import VERSION
from .cli import main

__version__ = VERSION

__all__ = ["VERSION", "__version__", "main"]
