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

The Infinite Loop Daemon (`launch-loop.py`, ~7.7K lines) is a background daemon
that spawns autonomous Hermes chat sessions, collects their JSON output into a
ledger, and iterates until a stop condition is met.

**Key architecture points:**

- **`launch-loop.py`** — Main daemon. Spawns `hermes chat -q` subprocesses with
  real tools (`terminal`, `file`, `delegation`, `web`, etc.). Sessions stay
  alive for multiple turns (unlike `-z` oneshot), so `delegate_task()` subagent
  results arrive and are collected properly.
- **`session-self-loop.py`** — Lightweight in-session loop for when you want to
  iterate from *within* your current Hermes session rather than a background
  daemon.
- **`run.sh`** — One-command entrypoint. Sources `.env` and forwards all
  settings as CLI flags to `launch-loop.py`. Just `bash run.sh`.
- **`scripts/run-loop.sh`** — Shell wrapper with full flag forwarding (original
  entrypoint before `run.sh` was added).
- **`scripts/inspect-ledger.sh`** — Formatted viewer for the JSON state ledger
  at `/tmp/infinite-loop-state.json`. Supports `--watch`, `--summary`, `--json`,
  `--errors-only`, and `--last N`.
- **`scripts/archive-state.sh`** — Archive old iterations to JSONL or Markdown.
- **`scripts/replay-ledger.sh`** — Re-run archived iterations from JSONL files.

**Version**: The current version is defined as `VERSION = "14.2.0"` at the top
of `launch-loop.py`. The project follows [Semantic Versioning](https://semver.org/).

---

## Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd hermes-loop

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

# 2. Copy the environment template
cp .env.example .env

# 3. Set your goal (minimal config)
#    Edit .env and set at minimum INFINITE_LOOP_GOAL

# 4. Verify the daemon can parse its config
python3 launch-loop.py --dry-run

# 5. Run the self-tests
python3 launch-loop.py --self-test

# 6. (Optional) Create a Python virtual environment
#    Not required — the daemon is stdlib-only — but useful for
#    development tooling like linters.
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"   # if a setup.py/pyproject.toml exists in the future
```

> **No `pip install` is needed** — the daemon uses only Python 3 standard library
> modules. This is intentional: it reduces deployment friction and keeps the
> project dependency-free.

---

## Running the Daemon

### Daemon Mode (background)

```bash
# One-command entrypoint (recommended)
bash run.sh

# Direct invocation
python3 launch-loop.py --goal "Refactor auth module" --run

# With common flags
python3 launch-loop.py \
  --goal "Fix all TypeScript errors in src/" \
  --git \
  --git-commit \
  --max-iterations 20 \
  --run

# As a background process (e.g., in tmux)
tmux new -s loop
python3 launch-loop.py --goal "..." --run
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
| `python3 launch-loop.py --self-test` | Run ~40 in-process unit tests |
| `python3 launch-loop.py --help` | Full CLI reference |
| `python3 launch-loop.py --version` | Print version string |
| `bash scripts/inspect-ledger.sh` | View the state ledger |
| `bash scripts/inspect-ledger.sh --watch` | Auto-refresh every 5 seconds |
| `bash scripts/inspect-ledger.sh --summary` | Compact one-liner status |
| `make run` | Run with .env config (convenience) |
| `make dry-run` | Preview config (convenience) |
| `make self-test` | Run tests (convenience) |
| `make status` | Quick status check |
| `make stop` | Stop the daemon via sentinel |
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

- **`launch-loop.py` is big (~7.7K lines)** — find the right function before
  adding code. The `run_loop()` function has been progressively decomposed:
  look for `_execute_iteration()`, `_build_iteration_record()`,
  `_handle_notifications()`, `_detect_convergence()`, `_handle_backoff()`,
  `_classify_progress()`, and similar extracted helpers.
- **New flags** require additions in:
  1. `argparse` argument definitions in `create_parser()`
  2. `.env.example` documentation
  3. `run.sh` forwarding logic
  4. `README.md` flag table
  5. The `SKILL.md` metadata block (tags, description)
- **Stay stdlib-only** — do not introduce external Python dependencies.
  If you need a utility, implement it with stdlib.
- **Signal safety** — file writes should use temp-file + atomic rename
  patterns (see existing code in `_save_state()`).

### 3. Test

Run the self-tests before committing:

```bash
python3 launch-loop.py --self-test
```

This runs ~40 in-process tests across 8 core functions without spawning any
child Hermes sessions. All tests should pass (exit code 0).

**What the self-tests cover:**

| Function | Tests | What's tested |
|----------|-------|---------------|
| `extract_json_from_output()` | 6 | Edge cases: nested braces, no JSON, multiple JSON objects, malformed output |
| `classify_error()` | 5 | Timeout, network, schema, unknown error types |
| `text_similarity()` | 3 | Jaccard word-overlap for identical, partial, and completely different text |
| `check_convergence()` | 3 | Convergence detection with and without recent history |
| `validate_json_output()` | 3 | Valid JSON Schema, missing fields, type mismatches |
| `calc_adaptive_cooldown()` | 4 | Duration ranges: <5s, 5–15s, 15–300s, >300s |
| `GoalSpec` parsing | 3 | Simple goal, pipe format with profile, trailing spaces |
|| `_classify_progress()` | 6 | Completed, progress, partial, stuck, regression, unknown |
|| `_suggest_actionable_fix()` | 9 | Timeout, network, schema, stuck (workers/library), regression, consecutive errors, completed/progress (no suggestion), unknown |

**If you're adding a new function**, consider adding a self-test for it in the
`run_self_tests()` function at the bottom of `launch-loop.py`.

**Before submitting**, also verify:

```bash
# Python syntax check
python3 -m py_compile launch-loop.py
python3 -m py_compile session-self-loop.py

# Shell script syntax
bash -n scripts/inspect-ledger.sh
bash -n run.sh

# Dry run still parses correctly
python3 launch-loop.py --dry-run

# Help output is well-formed
python3 launch-loop.py --help | head -5
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

1. **Ensure all self-tests pass** — `python3 launch-loop.py --self-test`
2. **Update the CHANGELOG** — Add an entry under a new `## [Unreleased]`
   section at the top of `CHANGELOG.md`. Follow the existing format
   (Keep a Changelog + SemVer).
3. **Update the version** — Bump `VERSION` in `launch-loop.py` if this is
   a release-worthy change. Follow semantic versioning:
   - **Patch** (`14.1.0` → `14.1.1`): Bug fixes, minor doc changes
   - **Minor** (`14.1.0` → `14.2.0`): New features, non-breaking additions
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

- [ ] Self-tests pass (`python3 launch-loop.py --self-test`)
- [ ] CHANGELOG updated
- [ ] Version bumped (if applicable)
- [ ] README / docs updated (if applicable)
- [ ] `.env.example` updated (if new env vars were added)
- [ ] `run.sh` forwarding updated (if new CLI flags were added)
- [ ] `SKILL.md` metadata updated (if relevant)
- [ ] Shell scripts pass `bash -n` syntax check
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

1. **Version** — `python3 launch-loop.py --version`
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
**Command**: python3 launch-loop.py --goal "fix tests" --run
**Expected**: Loop starts and spawns Hermes sessions
**Actual**: TypeError: _classify_progress() missing 1 required positional argument: 'error'
**Ledger**: [paste relevant portion]
**Hermes**: 1.2.3
**OS**: Linux 6.8.0 (Arch)
**Python**: 3.12.0
```

---

## Project Structure

```
hermes-loop/
├── launch-loop.py              # Main daemon (~7.7K lines, 7762 lines)
├── session-self-loop.py        # In-session loop tracker (~440 lines)
├── run.sh                      # One-command entrypoint
├── Makefile                    # Convenience targets (run, self-test, stop, etc.)
├── .env                        # Your local configuration (git-ignored)
├── .env.example                # Documented config template
├── .gitignore
├── README.md                   # Full documentation
├── CHANGELOG.md                # Complete version history
├── SKILL.md                    # Hermes skill metadata
├── CONTRIBUTING.md             # This file
├── scripts/
│   ├── run-loop.sh             # Shell wrapper (original entrypoint)
│   ├── inspect-ledger.sh       # Formatted ledger viewer
│   ├── archive-state.sh        # Archive iterations to JSONL/Markdown
│   ├── replay-ledger.sh        # Re-run archived iterations
│   └── verify-delegation-config.sh  # Historical reference
├── Makefile                     # Convenience targets (run, self-test, stop, etc.)
├── CONTRIBUTING.md              # This file
└── __pycache__/                # Auto-generated (git-ignored)
```

> **Tip**: Use `make help` to see all available convenience targets (run,
> dry-run, self-test, lint, status, stop, clean, archive, log, version).

---

## Questions?

If you have questions about contributing, the architecture, or how the daemon
works, open a [Discussion](https://github.com/ORG/REPO/discussions) or file an
issue. We're happy to help.

Thank you for contributing to the Infinite Loop Daemon! 🚀
