# Contributing to the Infinite Loop Daemon

First off, thank you for considering contributing! The Infinite Loop Daemon is an
open-source project that powers autonomous, multi-turn Hermes sessions with real
tools and delegation. Whether you're fixing a bug, adding a feature, improving
documentation, or just asking a question — your help is welcome.

- [Project Overview](#project-overview)
- [Quick Start](#quick-start)
- [Setting Up the Dev Environment](#setting-up-the-dev-environment)
- [Running the Daemon](#running-the-daemon)
- [Common Commands](#common-commands)
- [Development Workflow](#development-workflow)
  - [1. Branch](#1-branch)
  - [2. Change](#2-change)
  - [3. Test](#3-test)
  - [4. Commit](#4-commit)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)
- [Project Structure](#project-structure)

---

## Project Overview

The Infinite Loop Daemon is a background daemon (split across the `hermes_loop/`
package and two top-level scripts) that spawns autonomous Hermes chat sessions,
collects their JSON output into a ledger, and iterates until a stop condition
is met.

**Key architecture points:**

- **`hermes_loop/`** — Main package (38 modules). Contains all daemon logic:
  `cli.py` (argparse + entry point), `loop.py` (iteration loop),
  `functions.py` (helper functions), `iteration.py` (spawned session execution),
  `error_utils.py` (error classification + actionable suggestions),
  `webhook.py` / `dashboard.py` (HTTP server + SSE dashboard),
  `preflight.py` (health checks), `notifications.py` (Pushbullet/ntfy/desktop),
  and many more. `launch-loop.py` at the repo root is now a thin import shim.
- **`launch-loop.py`** — Thin backward-compatible shim (18 lines). Imports
  `main()` from `hermes_loop` and calls it. All real code lives in the package.
- **`session-self-loop.py`** — Lightweight in-session loop for when you want to
  iterate from *within* your current Hermes session rather than a background
  daemon.
- **`run.sh`** — One-command entrypoint. Sources `.env` and forwards all
  settings as CLI flags to `launch-loop.py` (which delegates to the package).
  Just `bash run.sh`.
| `scripts/inspect-ledger.sh` — Formatted viewer for the JSON state ledger
  at `/tmp/infinite-loop-state.json`. Supports `--watch`, `--summary`, `--json`,
  `--errors-only`, and `--last N`.
- **`scripts/archive-state.sh`** — Archive old iterations to JSONL or Markdown.
- **`scripts/replay-ledger.sh`** — Re-run archived iterations from JSONL files.
- **`HACKING.md`** — Deep-dive reference for third-party tool developers.
  Documents the spawned-session protocol, iteration record schema, JSON ledger
  format, error taxonomy, and module map. Start here if you want to build tools
  that read or write the ledger.

**Version**: The current version is defined as `LAUNCH_LOOP_VERSION = "14.38.0"`
in `hermes_loop/config.py`. The project follows
[Semantic Versioning](https://semver.org/).

---

## Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd hermes-loop

# Enable the pre-commit hook via core.hooksPath (no sync problem)
make install-hooks-path

# Copy and configure environment
make env
# Or: cp .env.example .env
# Then edit .env with your settings

# Run with defaults (reads .env)
bash run.sh

# Or use the Makefile
make run                           # Same as bash run.sh
make dry-run                       # Preview config, don't start
make run ARGS="--max-iterations 10 --quiet"

# Monitor
make status                        # Quick status check
make stop                          # Stop the daemon
```

---

## Setting Up the Dev Environment

### Prerequisites

- **Python 3.10+** (stdlib only — no external dependencies required)
- **Bash 4+** (for shell scripts)
- **Git** (for version control)
- **Hermes Agent** installed and available as `hermes` on your `PATH`
  (needed to actually spawn sessions; the daemon itself uses only stdlib)

### Setup Steps

```bash
# 1. Clone the repo
git clone <repo-url>
cd hermes-loop

# 2. Install the hermes_loop command on your PATH:
make install

#    This runs `pip install -e .` which adds a `hermes_loop` console_scripts
#    entry point. After this, you can use `hermes_loop` directly instead of
#    `python3 -m hermes_loop` or `python3 launch-loop.py`.

# 3. (Recommended) Point git at `.githooks/` for the pre-commit hook
#    This avoids copying files and stays in sync automatically:
git config core.hooksPath .githooks
#    Or use the Makefile shortcut:
#    make install-hooks-path

# 4. Copy the environment template
cp .env.example .env

# 5. Set your goal (minimal config)
#    Edit .env and set at minimum INFINITE_LOOP_GOAL

# 6. Verify the daemon can parse its config
hermes_loop --dry-run

# 7. Run the self-tests
hermes_loop --self-test

# 8. (Optional) Create a Python virtual environment
#    Not required — the daemon is stdlib-only — but useful for
#    development tooling like linters.
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

> **Tip**: `git config core.hooksPath .githooks` is the cleanest way to enable the
> pre-commit hook. Unlike `cp`-based installation (which `make install-hooks` does),
> this approach has **no sync problem** — the hook always reads from the repo tree,
> so `git pull` updates, branch switches, and rebases all keep the hook current
> automatically. Run `make install-hooks-path` to set it in one command.

> **No external dependencies** — the daemon uses only Python 3 standard library
> modules (`argparse`, `json`, `subprocess`, etc.). The `pip install -e .` only
> registers the `hermes_loop` console command; it adds zero runtime dependencies.
> This is intentional: it reduces deployment friction and keeps the project
> dependency-free.

---

## Running the Daemon

### Daemon Mode (background)

```bash
# One-command entrypoint (recommended) — reads .env
bash run.sh

# After installing via `make install`:
hermes_loop --goal "Refactor auth module" --run

# Or via the backward-compatible launch-loop.py shim (always works, no install needed)
python3 launch-loop.py --goal "Refactor auth module" --run

# With common flags
hermes_loop \
  --goal "Fix all TypeScript errors in src/" \
  --git \
  --git-commit \
  --max-iterations 20 \
  --run

# As a background process (e.g., in tmux)
tmux new -s loop
hermes_loop --goal "..." --run
# Ctrl+B, D to detach
```

### In-Session Mode

```bash
# Start from inside a Hermes terminal session
python3 session-self-loop.py --max-iterations 10 &

# Update state per iteration
echo '{"summary": "added feature X", "next_goal": "add feature Y"}' \
  > /tmp/session-loop-state.json

# Stop
echo '{"done": true}' > /tmp/session-loop-state.json
```

### Stopping the Loop

```bash
# Write to the sentinel file (default path)
echo "stop" > /tmp/infinite-loop-stop

# Or SIGINT/SIGTERM the daemon process
kill <PID>
```

---

## Common Commands

| Command | Purpose |
|---------|---------|
| `bash run.sh --dry-run` | Preview the resolved configuration |
| `bash run.sh --force-reset --quiet` | Clear ledger and start fresh, noise-free |
| `make install` | Install `hermes_loop` command on PATH via pip |
| `hermes_loop --self-test` | Run self-tests (count auto-detected at runtime) |
| `hermes_loop --list-flags` | Print all flags organized by group |
| `hermes_loop --list-groups` | Print group names with flag counts |
| `hermes_loop --examples` | Print categorized usage examples |
| `hermes_loop --help` | Full CLI reference |
| `hermes_loop --version` | Print version string |
| `bash scripts/inspect-ledger.sh` | View the state ledger |
| `bash scripts/inspect-ledger.sh --watch` | Auto-refresh every 5 seconds |
| `bash scripts/inspect-ledger.sh --summary` | Compact one-liner status |
| `make run` | Run with .env config (convenience) |
| `make dry-run` | Preview config (convenience) |
| `make self-test` | Run tests (convenience) |
| `make examples` | Print categorized usage examples |
| `make list-flags` | Print all 90 flags organized by group |
| `make list-groups` | Print group names with flag counts |
| `make status` | Show formatted one-line ledger status |
| `make log` | Tail the daemon log file |
| `make stop` | Send stop signal to the daemon |
| `make clean` | Clear all temp/ledger files |
| `echo stop > /tmp/infinite-loop-stop` | Graceful shutdown |

---

## Development Workflow

We use a straightforward feature-branch workflow.

### 1. Branch

Create a branch from `main` with a descriptive name:

```bash
git checkout main
git pull origin main
git checkout -b feature/describe-your-change
# or: fix/issue-123, docs/readme-update, refactor/extract-parser
```

**Branch naming conventions:**

| Prefix | When to use |
|--------|-------------|
| `feature/` | New functionality (flag, mode, feature) |
| `fix/` | Bug fixes |
| `docs/` | Documentation changes |
| `refactor/` | Code restructuring with no behavior change |
| `test/` | Adding or improving tests |
| `chore/` | Build, CI, tooling, meta tasks |

### 2. Change

Make your changes. A few guidelines:

- **`hermes_loop/` is a package (38 modules)** — find the right module before
  adding code. The `cli.py` module has the argparse setup and `main()` entry
  point. `loop.py` has `run_loop()`. `functions.py` has helper functions like
  `_execute_iteration()`, `_build_iteration_record()`,
  `_handle_notifications()`, `_detect_convergence()`, `_handle_backoff()`,
  `_classify_progress()`, and similar extracted helpers.
- **New flags** require additions in:
  1. `argparse` argument definitions in `hermes_loop/cli.py` (`create_parser()`)
  2. `.env.example` documentation
  3. `run.sh` forwarding logic
  4. `README.md` flag table
  5. The `SKILL.md` metadata block (tags, description)
  6. **Completion scripts** — if a `--list-flags` feature or shell completion
     script exists, regenerate or update it so new flags appear in tab-completion.
- **Stay stdlib-only** — do not introduce external Python dependencies.
  If you need a utility, implement it with stdlib.
- **Signal safety** — file writes should use temp-file + atomic rename
  patterns (see existing code in `_save_state()`).

### Setting Up Git Hooks

The repo ships a pre-commit hook at `.githooks/pre-commit` that auto-regenerates
shell completion scripts whenever CLI flags change. Two ways to enable it:

| Method | Command | Pro | Con |
|--------|---------|-----|-----|
| **`core.hooksPath` (recommended)** | `git config core.hooksPath .githooks` | No sync problem — always uses repo version; survives pulls, branches, rebases | Requires explicit `git config` |
| **`make install-hooks-path`** | `make install-hooks-path` | One command wrapping `git config core.hooksPath .githooks`; reads `hooks_method` and `hooks_path` from `[tool.hermes_loop]` in `pyproject.toml`, which is the single source of truth for pip-level auto-configuration | Same — delegates to the git config approach |
| **`cp`-based** | `make install-hooks` | Auto-run by `make install` / `make install-dev` | Stale copy if `.githooks/` updates — must re-run |

**Recommendation:** Run `make install-hooks-path` once to use the `core.hooksPath`
approach. It's cleaner and eliminates the stale-copy problem entirely.

If you already ran `make install` (which triggers `make install-hooks`), you can
switch at any time:

```bash
make install-hooks-path
# Or manually:
git config core.hooksPath .githooks
```

The old copied hook in `.git/hooks/pre-commit` becomes inactive immediately —
git ignores `.git/hooks/` when `core.hooksPath` is set.

#### Pip-Level Auto-Configuration (`setup.py` + `pyproject.toml`)

When someone runs `pip install -e .` or `make install` from a git checkout,
`setup.py` automatically prompts to configure `core.hooksPath = .githooks`.
This is the "zero-config" path for new contributors — they see the prompt
immediately after install, without needing to read this file first.

The authoritative configuration lives in the `[tool.hermes_loop]` section of
`pyproject.toml`. Both `setup.py` and `make install-hooks-path` read their
settings from this section, making it the single source of truth:

```toml
[tool.hermes_loop]
# Recommended hooks installation method: "core.hooksPath" or "cp"
hooks_method = "core.hooksPath"
# Path (relative to repo root) used by core.hooksPath
hooks_path = ".githooks"
# Target path for cp-based installation (relative to repo root)
hooks_cp_target = ".git/hooks/pre-commit"
```

If you add or rename the hooks directory, update `hooks_path` here and both
`setup.py` and `make install-hooks-path` will pick up the change automatically.
Do not hardcode the hooks path in multiple places — `[tool.hermes_loop]` is the
canonical source.

### 3. Test

Run the self-tests before committing:

```bash
hermes_loop --self-test
```

This runs 10 self-test groups (all cases auto-detected at runtime) without spawning any
child Hermes sessions. All tests should pass (exit code 0).

**What the self-tests cover:**

| Function | Tests | What's tested |
|----------|-------|---------------|
| `extract_json_from_output()` | 6 | Edge cases: nested braces, no JSON, multiple JSON objects, malformed output |
| `classify_error()` | 5 | Timeout, network, schema, unknown error types |
| `text_similarity()` | 5 | Jaccard word-overlap for identical, partial, completely-different, both-empty, one-empty |
| `check_convergence()` | 3 | Convergence detection with fewer-than-window, all-identical, all-different |
| `validate_json_output()` | 4 | Valid JSON Schema, missing fields, type mismatches, no schema |
| `calc_adaptive_cooldown()` | 4 | Duration ranges: zero, long, short, interpolated |
| `GoalSpec` parsing | 3 | Simple goal, profile, full spec with model/provider |
| `_classify_progress()` | 4 | Completed, regression, stuck, progress with git changes |
| `_suggest_actionable_fix()` | 11 | Timeout, network, stuck (workers/library), regression, consecutive errors, completed/progress (no suggestion), unknown, error-on-stderr, rate-limit |
| `validate_env_vars()` | 7 | Unknown vars, typo detection, valid prefix, empty value, edge cases |

**If you're adding a new function**, consider adding a self-test for it in the
`run_self_tests()` function at the bottom of `launch-loop.py`.

**Before submitting**, also verify:

```bash
# Python syntax check on all package files
python3 -m py_compile hermes_loop/cli.py
python3 -m py_compile hermes_loop/loop.py
python3 -m py_compile hermes_loop/functions.py
python3 -m py_compile hermes_loop/iteration.py
python3 -m py_compile session-self-loop.py
python3 -m py_compile launch-loop.py

# Shell script syntax
bash -n scripts/inspect-ledger.sh
bash -n run.sh

# Dry run still parses correctly
hermes_loop --dry-run

# Help output is well-formed
hermes_loop --help | head -5
```

### 4. Commit

Write clear, conventional commit messages:

```
<type>: <short description>

<optional body describing motivation and rationale>
```

**Types:**

| Type | Example |
|------|---------|
| `feat` | `feat: add --resume flag for session chaining across iterations` |
| `fix` | `fix: handle KeyError when ledger is empty on restart` |
| `docs` | `docs: clarify --evolve behavior in README` |
| `refactor` | `refactor: extract _detect_convergence from run_loop` |
| `test` | `test: add edge cases for extract_json_from_output` |
| `chore` | `chore: bump version to 14.1.0` |

**Commit message guidelines:**

- First line: max 72 characters, imperative mood ("Add feature" not "Added feature")
- Body: wrap at 72 characters, explain *why* the change was made
- Reference issues when applicable (`Closes #123`)
- If the change affects spawned sessions or the ledger format, mention it

```bash
git add launch-loop.py CHANGELOG.md README.md
git commit -m "feat: add --track-goals for idempotent goal execution

When used with --goals-file, completed goals are now tracked via
MD5 hash. On restart, already-completed goals are skipped
automatically. --reset-goals clears the tracking for a fresh run.

Closes #42"
```

---

## Code Style

The project follows informal but consistent conventions:

### Python (`launch-loop.py`, `session-self-loop.py`)

- **Indentation**: 4 spaces, no tabs.
- **Line length**: Aim for ≤100 characters. Docstrings at ≤80.
- **Quotes**: Double quotes (`"`) for strings, single quotes (`'`) for
  characters or when the string contains a double quote.
- **Naming**:
  - `snake_case` for functions, methods, variables
  - `PascalCase` for classes
  - `SCREAMING_SNAKE_CASE` for constants (e.g., `VERSION`, `DEFAULT_TOOLSETS`)
  - Private functions prefixed with `_` (e.g., `_save_state()`, `_classify_progress()`)
- **Type hints**: Optional but encouraged for new functions (especially
  public ones). The project does not enforce mypy.
- **Docstrings**: Use `"""triple double quotes"""`. For complex functions,
  include a brief description, parameter list, and return value.

```python
def _classify_progress(summary: str, has_git_changes: bool, error: str | None) -> str:
    """Classify iteration progress based on summary text, git changes, and errors.

    Args:
        summary: The iteration summary text from the spawned session.
        has_git_changes: Whether git diff shows file modifications.
        error: Error string if the iteration failed, None otherwise.

    Returns:
        One of: "completed", "progress", "partial", "stuck", "regression", "unknown".
    """
    ...
```

- **Return early**: Prefer early returns and guard clauses over deep nesting.
- **Stdlib only**: No external imports beyond `argparse`, `json`, `os`,
  `subprocess`, `pathlib`, `re`, `time`, `datetime`, `hashlib`, `math`,
  `shutil`, `signal`, `tempfile`, `threading`, `multiprocessing`, `logging`,
  `http.server`, `socketserver`, etc.

### Shell Scripts (`run.sh`, `scripts/*.sh`)

- **Shebang**: `#!/usr/bin/env bash`
- **Strict mode**: `set -euo pipefail` at the top of every script.
- **Naming**: `snake_case` for variables, `UPPER_CASE` for environment-level vars.
- **Error messages** go to stderr (`echo "Error: ..." >&2`).
- **Flag parsing**: Use `while [[ $# -gt 0 ]]; do case "$1" in ... esac; done`.
- **Quote everything**: Always `"$variable"` not `$variable`.

### Documentation (`.md` files)

- Use [GitHub-flavored Markdown](https://github.github.com/gfm/).
- Tables should be pipe-formatted and readable in source.
- Code blocks must specify a language for syntax highlighting.
- Keep line length ≤100 characters in prose when practical.

---

## Submitting Changes

### Pull Request Process

1. **Ensure all self-tests pass** — `hermes_loop --self-test`
2. **Update the CHANGELOG** — Add an entry under a new `## [Unreleased]`
   section at the top of `CHANGELOG.md`. Follow the existing format
   (Keep a Changelog + SemVer).
3. **Update the version** — Bump `LAUNCH_LOOP_VERSION` in `hermes_loop/config.py` if this is
   a release-worthy change. Follow semantic versioning:
   - **Patch** (`14.7.0` → `14.7.1`): Bug fixes, minor doc changes
   - **Minor** (`14.7.0` → `14.8.0`): New features, non-breaking additions
   - **Major** (`14.0.0` → `15.0.0`): Breaking changes to CLI flags, ledger
     format, or spawned session interface
4. **Update docs** — If you added or changed a CLI flag, update `README.md`
   (flag tables), `.env.example`, `run.sh` forwarding, and `SKILL.md` metadata.
5. **Push and open a PR** against the `main` branch.

```bash
# After committing your changes
git push origin feature/your-feature

# Then open a pull request on the repository.
```

### PR Checklist

- [ ] Self-tests pass (`hermes_loop --self-test`)
- [ ] CHANGELOG updated
- [ ] Version bumped (if applicable)
- [ ] README / docs updated (if applicable)
- [ ] `.env.example` updated (if new env vars were added)
- [ ] `run.sh` forwarding updated (if new CLI flags were added)
- [ ] `SKILL.md` metadata updated (if relevant)
- [ ] Shell scripts pass `bash -n` syntax check
- [ ] Completion scripts up-to-date (hooks active? run `make install-hooks-path` or `make install-hooks`)
- [ ] Hooks installed via `core.hooksPath` (recommended: `make install-hooks-path`)
- [ ] No external dependencies introduced
- [ ] Commit messages follow conventions

### What Happens Next

1. A maintainer will review your PR.
2. CI (self-tests + syntax checks) will run automatically.
3. You may be asked to make changes. Please respond promptly.
4. Once approved, a maintainer will merge your PR.

---

## Reporting Issues

### Bug Reports

When filing a bug report, please include:

1. **Version** — `hermes_loop --version`
2. **Command used** — The exact command you ran
3. **Expected behavior** — What you expected to happen
4. **Actual behavior** — What actually happened (include error output)
5. **Ledger state** (if relevant) — `bash scripts/inspect-ledger.sh --json`
   or the relevant portion of `/tmp/infinite-loop-state.json`
6. **Hermes version** — `hermes --version`
7. **Environment** — OS, Python version (`python3 --version`), shell

### Feature Requests

Describe the feature, why it's useful, and (if possible) how you'd implement
it. Examples of good feature requests:

- "Add a `--max-idle-iterations` flag to stop when no git changes occur"
- "Support a `--goals-file` pipe format with per-goal profile overrides"

### Quick Bug Report Template

```
**Version**: 14.1.0
**Command**: hermes_loop --goal "fix tests" --run
**Expected**: Loop starts and spawns Hermes sessions
**Actual**: TypeError: _classify_progress() missing 1 required positional argument: 'error'
**Ledger**: [paste relevant portion]
**Hermes**: 1.2.3
**OS**: Linux 6.8.0 (Arch)
**Python**: 3.12.0
```

---

## Project Structure

```text
hermes-loop/
├── run.sh                      # One-command entrypoint ★
├── Makefile                    # Convenience targets ★
├── launch-loop.py              # Thin backward-compatible shim (18 lines)
├── session-self-loop.py        # In-session loop tracker (~440 lines)
├── CONTRIBUTING.md             # This file
├── README.md                   # Full documentation
├── CHANGELOG.md                # Complete version history
├── SKILL.md                    # Hermes skill metadata
├── .env                        # Your local configuration (git-ignored)
├── .env.example                # Documented config template
├── .gitignore
├── hermes_loop/                # Main package (38 modules) ★
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                  # Argparse + main() entry point
│   ├── loop.py                 # run_loop() iteration logic
│   ├── functions.py            # Helper functions
│   ├── iteration.py            # Spawned session execution
│   ├── config.py               # Constants, paths, defaults
│   ├── error_utils.py          # Error classification + suggestions
│   ├── error_recovery.py       # Automatic error recovery
│   ├── webhook.py              # HTTP webhook server
│   ├── dashboard.py            # SSE status dashboard
│   ├── preflight.py            # Preflight health checks
│   ├── notifications.py        # Pushbullet/ntfy/desktop notifications
│   ├── heartbeat.py            # Session heartbeat monitoring
│   ├── worker_manager.py       # Hermes worker process management
│   ├── library_worker.py       # AIAgent in-process execution
│   ├── state.py                # Ledger state management
│   ├── file_utils.py           # File I/O utilities
│   ├── git_utils.py            # Git diff/commit helpers
│   ├── goal_utils.py           # Goal parsing/tracking
│   ├── signal_handlers.py      # Signal handling (SIGINT/SIGTERM)
│   ├── stats.py                # Statistics and ETA
│   ├── validation.py           # JSON Schema validation
│   ├── similarity.py           # Text similarity (Jaccard)
│   ├── cooldown.py             # Adaptive cooldown calculation
│   ├── hermes_utils.py         # Hermes binary detection
│   ├── system_utils.py         # System resource tracking
│   ├── file_watcher.py         # Directory/file change watcher
│   ├── archiving.py            # Ledger archival
│   ├── self_test.py            # In-process unit tests
│   ├── color_utils.py          # ANSI colorization helpers
│   ├── completions.py          # Shell completion generation
│   ├── diagnosis.py            # --doctor self-diagnosis
│   ├── env_utils.py            # .env file validation
│   ├── wizard.py               # --init interactive setup wizard
│   ├── worktree_merger.py      # Smart git worktree branch merging
│   ├── tracker.py              # Context window tracker
│   └── legacy.py               # Backward compatibility
├── scripts/
│   ├── run-loop.sh             # Shell wrapper (original entrypoint)
│   ├── inspect-ledger.sh       # Formatted ledger viewer
│   ├── archive-state.sh        # Archive iterations to JSONL/Markdown
│   ├── replay-ledger.sh        # Re-run archived iterations
│   └── verify-delegation-config.sh  # Historical reference
├── references/                 # Deep-dive design documents
│   ├── cross-iteration-context.md
│   ├── spawn-toolset-restriction.md
│   ├── terminal-timeout-trap.md
│   ├── hermes-worker.md
│   └── ...
└── research/                   # Feature research documents
    ├── v11.11.0-features.md
    ├── v12.0.0-features.md
    ├── v14.0.0-features.md
    └── ...
```

> **Tip**: Use `make help` to see all available convenience targets (run,
> dry-run, self-test, lint, status, stop, clean, archive, log, version).
> Use `make install-hooks-path` to enable git hooks without the sync problem.

---

## Questions?

If you have questions about contributing, the architecture, or how the daemon
works, open a [Discussion](https://github.com/ORG/REPO/discussions) or file an
issue. We're happy to help.

Thank you for contributing to the Infinite Loop Daemon! 🚀
