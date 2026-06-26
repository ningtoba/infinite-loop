#!/usr/bin/env python3
"""
launch-loop.py — Thin import shim for the hermes_loop package.

All functionality has been refactored into the hermes_loop/ package.
This file exists for backward compatibility.
"""

import sys
import os

# Ensure the package directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hermes_loop import main, VERSION, LAUNCH_LOOP_VERSION  # noqa: E402, F401

if __name__ == "__main__":
    main()
