"""
setup.py — hermetic setuptools shim for pip-level git hooks auto-configuration.

This file exists alongside pyproject.toml to provide post-install hooks that
automatically configure git core.hooksPath = .githooks when installing in
editable/development mode from a git checkout.

For most installs the pyproject.toml [project] section is sufficient; this file
adds the post-install UX that pyproject.toml alone cannot express.

The configuration values are kept in sync with [tool.hermes_loop] in
pyproject.toml as the single source of truth.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_HOOKS_RELPATH = ".githooks"
_HOOKS_METHOD = "core.hooksPath"


def _post_install() -> None:
    """Offer to configure git hooks path after editable/dev installs.

    Runs only when:
      - Installing from a git checkout (not from PyPI)
      - core.hooksPath is not already set to the project's .githooks/
      - stderr is a terminal (interactive shell)
    """
    try:
        repo_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return  # Not a git repo or git not available

    # Normalize paths — only auto-configure when installing from this repo
    install_dir = Path(__file__).resolve().parent
    repo_dir = Path(repo_root).resolve()
    if install_dir != repo_dir:
        return  # Installing from elsewhere (e.g. PyPI)

    # Check current hooks path
    current = ""
    try:
        current = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except subprocess.SubprocessError:
        pass

    hooks_abs = repo_dir / _HOOKS_RELPATH
    if current == str(hooks_abs):
        return  # Already configured correctly

    if current:
        print(
            f"\n  [setup.py] git core.hooksPath is currently '{current}'",
            file=sys.stderr,
        )

    if not sys.stderr.isatty():
        print(
            f"\n  [setup.py] To enable pre-commit hooks, run:\n"
            f"    git config core.hooksPath {_HOOKS_RELPATH}\n"
            f"    # Or: make install-hooks-path",
            file=sys.stderr,
        )
        return

    try:
        resp = (
            input(f"\n  Configure git hooks path to '{_HOOKS_RELPATH}' ? [Y/n] ")
            .strip()
            .lower()
        )
    except (EOFError, KeyboardInterrupt):
        resp = ""

    if resp in ("", "y", "yes"):
        try:
            subprocess.run(
                ["git", "config", "core.hooksPath", _HOOKS_RELPATH],
                check=True,
                timeout=5,
            )
            print(
                f"  ✓ core.hooksPath = {_HOOKS_RELPATH}  "
                f"(hooks auto-update on pull/branch/checkout)",
                file=sys.stderr,
            )
        except subprocess.SubprocessError as exc:
            print(
                f"  ✗ Failed to set core.hooksPath: {exc}",
                file=sys.stderr,
            )
    else:
        print(
            f"  Skipped. To enable later: make install-hooks-path",
            file=sys.stderr,
        )


# ── Post-install hook ────────────────────────────────────────────────────────
# Called after pip install -e . or pip install . from a git checkout.
# setuptools>=64 is required (as declared in pyproject.toml).

try:
    from setuptools import setup as _setup
    from setuptools.command.develop import develop as _DevelopCommand
    from setuptools.command.install import install as _InstallCommand

    class _HookedDevelop(_DevelopCommand):
        def run(self):
            super().run()
            _post_install()

    class _HookedInstall(_InstallCommand):
        def run(self):
            super().run()
            _post_install()

except ImportError:
    from setuptools import setup as _setup  # type: ignore[no-redef]

    _setup()
else:
    _setup(
        cmdclass={
            "develop": _HookedDevelop,
            "install": _HookedInstall,
        },
    )
