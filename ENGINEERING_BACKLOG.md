# Engineering Backlog

> Comprehensive engineering backlog for **pi-loop** — autonomous task loop daemon powered by the pi coding agent.
> Generated: 2026-06-30
> Synthesis: All 28 source files analyzed across `pi_loop/` and `web_app/`, 27 test files, git history (202 commits, 5 days), CI/CD, dependencies, tooling configs, and documentation.

---

## Project Overview

**pi-loop** is a Python CLI daemon that runs iterative tasks in a subprocess loop, tracking progress in a JSON ledger with a dark-theme web dashboard. It delegates each iteration to the **pi coding agent** (`pi -q <goal>`) and handles orchestration — convergence detection, error recovery, cooldown, git auto-commit, multi-worker parallelism, and real-time monitoring via a FastAPI + SSE web UI. The project is in early alpha (~5 days old, 202 commits by a single developer) with a solid test foundation but significant architectural debt from rapid iteration.

## Current State Assessment

**What's good:** Clean modular structure (25+ modules, single-responsibility), modern PEP 621 packaging with pip-compile lock files, comprehensive CI matrix (3.10–3.13), robust ruff lint config, working FastAPI web dashboard with SSE streaming, API-key auth recently added, and solid test foundation (440+ tests, 83% file coverage).

**What needs work:** `run_loop()` is a 435-line monolithic function with 71 parameters, type-checking is silently disabled in CI (`|| true`), critical modules have shallow test coverage, there's no structured logging, no Docker/containerization in main branch, vanilla JS SPA has no module system, error recovery adaptations are silently lost, and the project has no API docs, CONTRIBUTING guide, or changelog.

---

## Quick Reference

| Severity | Count |
|----------|-------|
| 🔴 **Critical (P0)** | 3 |
| 🟠 **High (P1)** | 8 |
| 🟡 **Medium (P2)** | 14 |
| 🔵 **Low (P3)** | 9 |
| **Total Active** | **34** |

| Category | Count |
|----------|-------|
| Bugs | 3 |
| Technical Debt | 5 |
| Refactoring Opportunities | 3 |
| Performance Improvements | 2 |
| Security Improvements | 2 |
| Missing Tests | 3 |
| Missing Documentation | 2 |
| CI/CD Improvements | 3 |
| Developer Experience | 3 |
| Code Cleanup | 2 |
| Dependency Updates | 2 |
| Architecture Improvements | 2 |
| Automation Opportunities | 2 |
| Feature Ideas | 2 |
| Observability/Monitoring | 2 |

---

## Status Legend

| Status | Meaning |
|--------|---------|
| ✅ **Done** | Completed and verified |
| 🔄 **In Progress** | Currently being worked on |
| ⏳ **Pending** | Not yet started |
| ❌ **Blocked** | Blocked by another item |

---

## B-1: Bugs

### B-001: Lost error recovery mitigations silently discarded via `state.get()`

| Field | Value |
|-------|-------|
| **Category** | Bugs |
| **Priority** | 🟠 High |
| **Impact** | High |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/loop.py` |

**Description:**
In `loop.py`, `state.get("mitigations", {})` creates a **new empty dict** when the `"mitigations"` key doesn't exist in the state. This empty dict is passed to `_adapt_to_error()`, which mutates it internally, but the mutated dict is **never written back** to `state["mitigations"]`. All error-recovery adaptations (backoff multipliers, escalation thresholds, retry strategy changes) are silently discarded after every error.

**Research Notes:**
The fix requires changing `mitigations = state.get("mitigations", {})` to `state.setdefault("mitigations", {})` and assigning `state["mitigations"] = mitigations` if using `state.get()`. Additionally, add a logged warning when mitigations are being adapted so operators can see recovery strategy changes in action.

```python
# Current (broken):
mitigations = state.get("mitigations", {})
_adapt_to_error(error_type, mitigations)

# Fix:
state.setdefault("mitigations", {})
_adapt_to_error(error_type, state["mitigations"])
logger.debug("Mitigations adapted: %s", state["mitigations"])
```

---

### B-002: Subprocess zombie leak from unwaited child processes

| Field | Value |
|-------|-------|
| **Category** | Bugs |
| **Priority** | 🟠 High |
| **Impact** | High |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/error_recovery.py` |

**Description:**
When a subprocess times out, is killed, or an exception occurs during iteration, `proc.kill()` is called but `proc.wait()` is not consistently called afterward. On Unix systems, this creates zombie processes that consume PID table entries. Over many iterations (especially under error-heavy scenarios), this can exhaust the system PID limit.

**Research Notes:**
Audit all `proc.kill()` and `proc.terminate()` calls across `loop.py` and `error_recovery.py`. Every kill/terminate must be followed by `proc.wait(timeout=5)` to reap the child process. The `_execute_task()` function and error recovery paths are the primary suspects. Add a utility function `_safe_kill(proc)` that wraps kill + wait + timeout to ensure this pattern is followed consistently.

---

### B-003: Config file corruption silently returns empty defaults without user notification

| Field | Value |
|-------|-------|
| **Category** | Bugs |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/config_file.py`, `web_app/config_manager.py` |

**Description:**
When the JSON config file is corrupt (partial write, disk full), `_read_stored()` falls back to defaults but does not notify the user or log the corruption at an appropriate level. The web UI shows default config silently, leading to confusion when custom settings disappear. The previous corrupt file is backed up with a `.corrupt` suffix but this happens silently.

**Research Notes:**
Add a warning banner in the web UI when config has fallen back to defaults, expose a `corrupt: true` flag in the config API response, and log the corruption at WARNING level with the corrupt file path. Consider adding config save atomicity (write to temp file, then atomic rename) to prevent corruption in the first place.

---

## B-2: Technical Debt

### TEC-001: `run_loop()` is a 435-line monolithic function violating SRP

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🔴 Critical |
| **Impact** | High |
| **Effort** | Large |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/loop.py` |

**Description:**
`run_loop()` at **818 lines total** (with the function body being ~435 lines) accepts **60+ parameters** and handles: sentinel checks, iteration counting, goal cycling, progressive context building, subprocess execution, git state capture, idle detection, error classification, notification dispatch, HTML dashboard generation, HTTP callbacks, on-error command execution, cooldown management, error-recovery adaptation, iteration cap trimming, and goal evolution. Each of these responsibilities should be extracted into focused functions or classes.

**Research Notes:**
This is the single largest source of technical debt. A `LoopConfig` dataclass was introduced in a previous iteration to compress the parameter list, but the function body itself was never decomposed. Recommended decomposition:

1. `_setup_iteration_context(state, config) → IterationContext` — prepares env, goal, context for one iteration
2. `_execute_iteration(context) → IterationResult` — runs the subprocess and captures output
3. `_process_iteration_result(result, state) → Action` — parses output, detects convergence, decides next action
4. `_apply_recovery(state, error) → None` — handles error classification and adaptation
5. `_emit_notifications(result, config) → None` — sends desktop/webhook/push alerts
6. `_check_termination(state, config) → bool` — evaluates all exit conditions

---

### TEC-002: Circular import between `cli.py` and `help_topics.py`

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟠 High |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/cli.py`, `pi_loop/help_topics.py` |

**Description:**
`cli.py` imports from `help_topics.py` for help text display, and `help_topics.py` imports from `cli.py` for flag introspection. This creates a circular import that is only resolved by Python's import system at runtime (lazy imports, late-binding). It makes the module dependency graph non-trivial and can cause import-order bugs.

**Research Notes:**
Extract shared flag definitions into a new `_flags.py` or `constants.py` module. Both `cli.py` and `help_topics.py` import flag metadata from this shared module rather than from each other. Alternatively, move help topic rendering into `cli.py` or make `help_topics.py` not depend on `cli.py` for flag data.

---

### TEC-003: 30+ magic numbers scattered across the codebase

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟡 Medium |
| **Impact** | Low |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/config.py`, `pi_loop/error_recovery.py`, `web_app/rate_limiter.py`, `web_app/server.py` |

**Description:**
The codebase contains 30+ magic numeric literals — timeout values (2000ms, 500ms, 120s, 300s, 600s), limits (10240, 500, 120), rates (0.01, 0.6), retry counts, and buffer sizes. These are scattered across modules with no documentation of what they control or why those specific values were chosen. Changes require grep-searching the entire codebase.

**Research Notes:**
Define all magic numbers as named constants in a `DEFAULT_CONFIG` dict or per-module `_constants` module. For example:

```python
# pi_loop/_constants.py
DEFAULT_MAX_TURNS = 2000
DEFAULT_COOLDOWN_SECONDS = 5
DEFAULT_MAX_ITERATION_AGE = 600  # seconds
DEFAULT_BUFFER_SIZE = 10240
DEFAULT_RATE_LIMIT_WINDOW = 60  # seconds
DEFAULT_RATE_LIMIT_CAP = 120
```

---

### TEC-004: Vanilla JS SPA with global mutable state, no module system

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Large |
| **Dependencies** | B-005 (if any) |
| **Status** | ⏳ Pending |
| **Affected Files** | `web_app/static/app.js` (~1078 lines) |

**Description:**
The single-page application in `app.js` has 15+ global state variables and 40+ top-level function declarations in the global namespace. State is mutated freely by any function. Data flow is implicit and untraceable. Error handling is inconsistent (empty catch blocks in some places, meaningful logging in others). There are no ES modules, classes, or state management patterns.

**Research Notes:**
Refactor into ES modules (native, no build step): `state.js` (centralized state with getters/setters), `api.js` (all fetch calls), `ui.js` (DOM manipulation), `dashboard.js`, `config.js`, `logs.js`. Use a simple pub/sub pattern for state changes. This is a Large effort because the entire ~1078 lines would be restructured, but it's been deferred because the app works and there are higher-priority backend issues.

---

### TEC-005: Quadruple config maintenance — pyproject.toml, config.py, config_file.py, config_manager.py

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pyproject.toml`, `pi_loop/config.py`, `pi_loop/config_file.py`, `web_app/config_manager.py` |

**Description:**
Configuration defaults and schema are maintained across four locations: `pyproject.toml` (tool settings), `config.py` (runtime defaults), `config_file.py` (file I/O + validation), and `config_manager.py` (web API CRUD). Adding a config option requires coordinating changes in all four files, and there's no single source of truth for what valid config looks like.

**Research Notes:**
Centralize config schema into a single Pydantic model (e.g., `LoopConfig` dataclass already partially done). Have each layer derive defaults and validation from this model. The web config manager should use the Pydantic model's schema for validation and auto-generate the config form.

---

## B-3: Refactoring Opportunities

### REF-001: Decompose `run_loop()` into orchestration, execution, and reporting phases

| Field | Value |
|-------|-------|
| **Category** | Refactoring Opportunities |
| **Priority** | 🔴 Critical |
| **Impact** | High |
| **Effort** | XLarge |
| **Dependencies** | TEC-001 (same root cause, shared decomposition plan) |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/loop.py` |

**Description:**
The ~435-line `run_loop()` body mixes three distinct concerns: orchestration (when to run, when to stop), execution (running the subprocess, capturing output), and reporting (notifications, git, HTML dashboard). These should be extracted into separate classes or modules:

- **`LoopOrchestrator`**: Manages the iteration lifecycle, convergence checks, sentinel files, goal cycling
- **`TaskExecutor`**: Manages subprocess lifecycle, environment setup, timeout enforcement, output parsing
- **`ResultReporter`**: Handles git auto-commit, notifications (desktop, push, webhook), HTML dashboard, HTTP callbacks

**Research Notes:**
This is the most impactful refactoring available. It directly enables unit testing of iteration logic without mocks, makes error recovery testable in isolation, and allows future parallel worker implementation without touching orchestration code. Each extracted class should be independently testable. The `LoopConfig` dataclass (already introduced) provides a clean interface boundary.

---

### REF-002: Replace module-level mutable state with dependency injection

| Field | Value |
|-------|-------|
| **Category** | Refactoring Opportunities |
| **Priority** | 🟠 High |
| **Impact** | High |
| **Effort** | Large |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/heartbeat.py`, `pi_loop/git_utils.py`, `pi_loop/error_recovery.py` |

**Description:**
Several modules use module-level mutable state (global variables, `threading.Event`, module-scoped flags) for cross-module communication. `_shutdown_requested` in `loop.py`, the heartbeat poll flag, and various counters in `error_recovery.py` are all module-level mutable objects. This makes testing state-dependent, creates implicit coupling between modules, and makes concurrent usage unsafe.

**Research Notes:**
Introduce a `LoopContext` object (or reuse the existing `LoopConfig` dataclass) that holds all mutable state and is passed explicitly to all functions that need it. This enables:

- Isolated unit tests (create a fresh context per test)
- Multiple concurrent loop instances
- Clean shutdown via context manager
- Type-safe state management

---

### REF-003: Split web frontend into ES modules with explicit state management

| Field | Value |
|-------|-------|
| **Category** | Refactoring Opportunities |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Large |
| **Dependencies** | TEC-004 (same file, same plan) |
| **Status** | ⏳ Pending |
| **Affected Files** | `web_app/static/app.js` (~1078 lines) |

**Description:**
The 1078-line `app.js` file handles SSE streaming, REST API calls, DOM rendering, config editing, logs display, and dashboard metrics — all in one file with global state. This makes any frontend change risky because of implicit state dependencies.

**Research Notes:**
Split into ES modules (native, no build step needed — modern browsers support `type="module"`):

- `state.js` — Centralized reactive state store (pub/sub pattern)
- `api.js` — All `fetch()` calls, error handling, retry logic
- `sse.js` — SSE connection management with exponential backoff
- `components/dashboard.js` — Dashboard rendering
- `components/config.js` — Config editor with validation
- `components/logs.js` — Real-time log viewer
- `utils.js` — Shared helpers (formatting, timestamps)

---

## B-4: Performance Improvements

### PERF-001: Blocking `subprocess.call()` in on-error handler stalls the iteration loop

| Field | Value |
|-------|-------|
| **Category** | Performance Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/loop.py` |

**Description:**
The `run_loop()` function calls `subprocess.call()` for on-error and on-success commands. This is a **blocking call** — if the command takes 30 seconds, the entire daemon iteration loop is frozen for 30 seconds. No convergence checks, no sentinel monitoring, no SSE updates.

**Research Notes:**
Replace `subprocess.call()` with `asyncio.create_subprocess_exec()` and a timeout. The event loop is already running (uvicorn/FastAPI). For the CLI-only mode (no web), use `subprocess.Popen()` with a non-blocking poll loop. Add a configurable timeout (default: 30s) for on-error/on-success commands.

---

### PERF-002: No connection pooling for webhook HTTP calls

| Field | Value |
|-------|-------|
| **Category** | Performance Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/loop.py` |

**Description:**
Each webhook notification creates a new HTTP connection (via `urllib.request`). Under high-iteration scenarios with multiple webhook targets, this adds connection setup latency to every notification.

**Research Notes:**
Use `httpx` (already available in the venv as a transitive dependency) with a shared `AsyncClient` that reuses connections. For the sync CLI path, use `urllib.request` with `urllib3.PoolManager` or `requests.Session`. The async FastAPI path already has `httpx` available.

---

## B-5: Security Improvements

### SEC-001: Audit API authentication coverage — ensure ALL endpoints are protected

| Field | Value |
|-------|-------|
| **Category** | Security Improvements |
| **Priority** | 🟠 High |
| **Impact** | High |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `web_app/server.py` |

**Description:**
API-key auth middleware was recently added (commit `08cba91`) to `/api/*` endpoints, but it's critical to audit that:

1. **All** mutable endpoints are covered (config save, loop start/stop/pause/resume, goal management)
2. The auth middleware can be bypassed by URL path tricks
3. Auth can be disabled via config (for local-only deployments) — verify the disable path works correctly
4. The API key is securely generated and stored

**Research Notes:**
Write a test that enumerates all routes and verifies auth is enforced on every non-GET, non-static endpoint. Double-check that static file serving and the `index.html` route don't leak API keys through error messages. Verify that the API key is not logged or exposed in HTML source.

---

### SEC-002: Input/output path sanitization for user-supplied file and directory arguments

| Field | Value |
|-------|-------|
| **Category** | Security Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/cli.py`, `pi_loop/config.py`, `pi_loop/file_utils.py` |

**Description:**
CLI flags like `--goals-file`, `--cwd`, and config file paths accept user-supplied strings that are passed directly to filesystem operations without validation or sanitization. While this is a local CLI tool, path traversal (`../`, symlink attacks) could cause unintended file reads/writes.

**Research Notes:**
Add path validation:

- Resolve all paths to absolute before use
- Verify resolved paths are within expected directories (or allowlist)
- Warn on symlinks pointing outside the project tree
- Use `os.path.realpath()` to resolve symlinks
- Add tests for path-traversal attempts

---

## B-6: Missing Tests

### TST-001: Zero integration tests for the real subprocess lifecycle

| Field | Value |
|-------|-------|
| **Category** | Missing Tests |
| **Priority** | 🟠 High |
| **Impact** | High |
| **Effort** | Large |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `tests/` (new `tests/integration/` directory) |

**Description:**
All 440+ tests are pure unit tests with heavy mocking. There are zero tests that:

1. Start a real `pi` subprocess (or a shell-script mock of `pi`)
2. Run one full iteration lifecycle (config → execute → parse → recover)
3. Test the daemon lifecycle (start → iterate → stop)
4. Test SSE streaming from the web server to a real client
5. Test sentinel file stop/pause signals with a running loop

**Research Notes:**
Create `tests/integration/` with:

- A `mock_pi.sh` shell script that simulates `pi --mode json` output (NDJSON with stdout, stderr, model info)
- A pytest fixture that starts a daemon process in the background
- A conftest fixture that provides a temporary data directory for each test
- Tests for: single iteration, multi-iteration convergence, error recovery (inject failures), sentinel stop/pause, web UI endpoints talking to the daemon

---

### TST-002: `file_watcher.py` has zero test coverage

| Field | Value |
|-------|-------|
| **Category** | Missing Tests |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/file_watcher.py`, `tests/` (new `tests/test_file_watcher.py`) |

**Description:**
The file watcher module (responsible for detecting filesystem changes and triggering re-runs) has no tests whatsoever. If file-watching behavior breaks, the daemon silently stops responding to file changes.

**Research Notes:**
Write tests for:

- Watching a file for modifications using `inotify`/`watchdog` (or mock the filesystem events)
- Triggering an iteration on file change
- Debouncing rapid file changes
- Stable/unstable file detection (waiting for writes to complete)
- Error handling when the watched file is deleted

---

### TST-003: Low test coverage on critical modules — `cli.py`, `loop.py`, `status.py`

| Field | Value |
|-------|-------|
| **Category** | Missing Tests |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/cli.py`, `pi_loop/loop.py`, `pi_loop/status.py` |

**Description:**
While `loop.py` has some test coverage, the critical paths — CLI argument parsing (`cli.py`), the main `run_loop()` orchestration loop, and status reporting (`status.py`) — have shallow coverage. `cli.py` in particular has no tests for the 14+ CLI flags and their interactions.

**Research Notes:**

- `cli.py`: Add tests for all flag combinations using `argparse` directly. Test `--help`, `--doctor`, `--preflight`, `--status`, `--init`, `--demo`, `--completion-script`, and flag interaction errors.
- `loop.py`: Add tests for the exit-early conditions (sentinel files, max turns reached, convergence detected, goal exhausted, idle timeout). Use dependency-injected subprocess mock.
- `status.py`: Test all rendering paths (active iteration, idle, error, done) with controlled state dicts.

---

## B-7: Missing Documentation

### DOC-001: No API documentation for REST endpoints

| Field | Value |
|-------|-------|
| **Category** | Missing Documentation |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `web_app/server.py`, `web_app/config_manager.py`, `web_app/loop_manager.py` |

**Description:**
The FastAPI-based REST API (endpoints: config CRUD, loop control, status, iterations, SSE stream) has no formal API documentation. While FastAPI supports automatic OpenAPI generation, the endpoints need docstrings and proper response models for this to be useful. External tool users (scripts, other services) have to read the source code to understand the API contract.

**Research Notes:**

- Add Pydantic response models for all endpoints
- Add `summary`, `description`, and `response_description` to each route decorator
- Add response status code documentation (200, 400, 404, 409, 422, 429, 500)
- Verify that `/docs` and `/redoc` are accessible (or enabled with auth)
- Add an `openapi.json` export to the build/docs step

---

### DOC-002: Missing CONTRIBUTING.md and CHANGELOG

| Field | Value |
|-------|-------|
| **Category** | Missing Documentation |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | Root (new files) |

**Description:**
The project has no `CONTRIBUTING.md` (setup, testing, PR workflow, code conventions) and no `CHANGELOG.md` (release history). The README version says `0.1.0` while `pyproject.toml` says `14.39.0` — this version mismatch will confuse new contributors.

**Research Notes:**

- Create `CONTRIBUTING.md` covering: setup (venv, pip install -e), running tests, running lint/format, PR workflow, commit message conventions (conventional commits)
- Create `CHANGELOG.md` based on git log (conventional commit messages already partially used)
- Fix README version to match `pyproject.toml`
- Remove stale `BACKLOG.md` or note that `ENGINEERING_BACKLOG.md` supersedes it

---

## B-8: CI/CD Improvements

### CICD-001: Mypy type errors silently swallowed by `|| true` in both Makefile and CI

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🟠 High |
| **Impact** | High |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `Makefile`, `.github/workflows/ci.yml` |

**Description:**
The `mypy` target in the Makefile appends `; true` which means mypy always exits with code 0 regardless of findings. The CI `lint` job runs `make mypy`, so **type errors never block CI**. This makes the mypy config essentially decoration — developers get no enforcement of type annotations.

**Research Notes:**

1. Remove `|| true` / `; true` from the Makefile `mypy` target
2. Fix all existing mypy errors first (or add per-module `# type: ignore` overrides for legitimate suppression)
3. Add mypy to the pre-commit hooks (`.pre-commit-config.yaml`)
4. Consider enabling `strict = true` in `pyproject.toml [tool.mypy]` once existing errors are resolved
5. Add `disallow_untyped_defs = true` to catch functions missing type annotations (~34% of functions currently lack hints)

---

### CICD-002: No smoke test in CI pipeline

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `.github/workflows/ci.yml` |

**Description:**
The CI workflow runs linters, type-checkers, and unit tests, but never actually runs `pi-loop --help` or verifies that the package installs and runs without import errors. A broken import or missing entry point wouldn't be caught until runtime deployment.

**Research Notes:**
Add a smoke-test step to the CI `test` job:

```yaml
- name: Smoke test
  run: |
    pi-loop --help
    pi-loop --version  # if available
    pi-loop --doctor
```

This verifies that the package installs correctly, entry points resolve, and basic CLI functions work in the CI environment. Consider adding `pi-loop-web --help` as well.

---

### CICD-003: No release automation or changelog generation

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Medium |
| **Dependencies** | DOC-002 |
| **Status** | ⏳ Pending |
| **Affected Files** | `.github/workflows/` (new release workflow) |

**Description:**
There are no release-related GitHub Actions workflows. Publishing to PyPI, creating GitHub releases with auto-generated changelogs, and tagging versions are all manual processes (if done at all). The project uses conventional commit prefixes (`feat:`, `fix:`, `chore:`) which enables auto-changelog generation.

**Research Notes:**
Create a `.github/workflows/release.yml` that:

1. Triggers on version tag push (e.g., `v*`)
2. Generates changelog from conventional commits (`git-cliff` or `python-semantic-release`)
3. Creates a GitHub Release with release notes
4. Optionally publishes to PyPI (when the project is ready for public release)
5. Add a Dependabot config (verify existing one covers all package ecosystems)

---

## B-9: Developer Experience (DX) Improvements

### DX-001: Missing `.editorconfig` — inconsistent indentation risk

| Field | Value |
|-------|-------|
| **Category** | Developer Experience |
| **Priority** | 🟡 Medium |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | Root (new `.editorconfig`) |

**Description:**
There is no `.editorconfig` file. When developers with different editor settings contribute, they may accidentally introduce inconsistent indentation (tabs vs spaces, wrong indent width) in Python, JavaScript, HTML, CSS, YAML, and TOML files.

**Research Notes:**
Create `.editorconfig`:

```ini
root = true

[*]
indent_style = space
indent_size = 4
end_of_line = lf
charset = utf-8
trim_trailing_whitespace = true
insert_final_newline = true

[*.{yml,yaml}]
indent_size = 2

[*.{js,html,css}]
indent_size = 2

[Makefile]
indent_style = tab
```

---

### DX-002: `.coverage` not in `.gitignore` — 53KB binary pollutes the working tree

| Field | Value |
|-------|-------|
| **Category** | Developer Experience |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Trivial |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `.gitignore` |

**Description:**
A 53KB `.coverage` binary file (SQLite coverage database) is present in the repo root and not listed in `.gitignore`. If accidentally committed, it adds binary noise to diffs and bloats the repo.

**Research Notes:**
Add to `.gitignore`:

```gitignore
# Coverage
.coverage
.coverage.*
htmlcov/
coverage/
```

---

### DX-003: No Docker or devcontainer for one-command setup

| Field | Value |
|-------|-------|
| **Category** | Developer Experience |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | Root (new `Dockerfile`, `docker-compose.yml`, `.devcontainer/devcontainer.json`) |

**Description:**
Docker and devcontainer files exist only in stale git worktrees and were never ported to the main branch. New contributors must manually set up a Python virtual environment, install dependencies, and configure their environment.

**Research Notes:**

- Port the `Dockerfile` from the worktree with updates for the current codebase
- Create a `docker-compose.yml` with the web server, volume mounts for config, and port mapping
- Create `.devcontainer/devcontainer.json` for VS Code/Cursor remote container development
- The Docker image should be minimal (slim-bullseye or alpine) with just Python + pi installed

---

## B-10: Code Cleanup

### CLN-001: Stale analysis artifacts and worktree clutter

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `.analysis/`, `synthesis-output.json`, `tooling-findings.txt`, `.worktrees/` |

**Description:**
The repo root contains analysis artifacts (`.analysis/`, `synthesis-output.json`, `tooling-findings.txt`) that are outputs from automated analysis tools, not source code. These clutter the directory tree and confuse new developers. The 3 stale git worktrees in `.worktrees/` contain superseded code that has diverged from main.

**Research Notes:**

- Move analysis artifacts to a `.archive/` or remove them from the working tree
- Add `*.analysis*` and `synthesis-output*` to `.gitignore`
- Evaluate whether the `.worktrees/` directories still have valuable work that should be merged, then prune them

---

### CLN-002: Redundant pre-commit hook mechanisms

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `.pre-commit-config.yaml`, `.githooks/pre-commit` |

**Description:**
There are two parallel pre-commit mechanisms: the `pre-commit` framework (`.pre-commit-config.yaml`) which provides ruff + ruff-format + 5 generic checks, and a bash script (`.githooks/pre-commit`) that runs ruff check + format on staged Python files. These overlap in coverage and may conflict.

**Research Notes:**

- Keep `.pre-commit-config.yaml` as the primary mechanism (richer, maintained, CI-integrated)
- Remove or archive `.githooks/pre-commit` bash script
- Add mypy (post-fix) to the pre-commit config once CICD-001 is resolved
- Ensure the Makefile's `pre-commit` target installs the `.pre-commit-config.yaml` hooks via `pre-commit install`

---

## B-11: Dependency Updates

### DEP-001: `pydantic-core` pinned to outdated minor — update and validate

| Field | Value |
|-------|-------|
| **Category** | Dependency Updates |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `requirements.txt`, `requirements-dev.txt` |

**Description:**
`pydantic-core` is pinned at `2.46.4` but `2.47.0` is available. While this is a minor bump and typically safe, it's a Rust-native core component of Pydantic, so updates can affect behavior.

**Research Notes:**

```bash
pip-compile --upgrade-package pydantic-core
make test
make lint-all
make mypy
```

Verify no test failures or type errors after the update. Commit both regenerated lockfiles.

---

### DEP-002: `fastapi` minimum constraint too loose — tighten to known-good version

| Field | Value |
|-------|-------|
| **Category** | Dependency Updates |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pyproject.toml`, `requirements.txt` |

**Description:**
`pyproject.toml` specifies `fastapi>=0.100.0`, but the project now uses features from `0.138.x`. On a fresh install, pip could resolve `0.100.0` which is 38 versions behind and may lack required APIs (e.g., `lifespan`, certain middleware patterns).

**Research Notes:**
Update the minimum bound: `fastapi>=0.115.0` (a reasonable known-good minimum) or match the installed version: `fastapi>=0.138.0`. Then regenerate lockfiles: `pip-compile --upgrade`.

---

## B-12: Architecture Improvements

### ARC-001: No clean separation between config validation and runtime state

| Field | Value |
|-------|-------|
| **Category** | Architecture Improvements |
| **Priority** | 🟠 High |
| **Impact** | High |
| **Effort** | Large |
| **Dependencies** | TEC-001, REF-001 |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/config.py`, `pi_loop/loop.py`, `pi_loop/state.py` |

**Description:**
Configuration and runtime state are conflated throughout the codebase. `config.py` handles both static config (user settings) and dynamic state (current iteration, mitigations, error history). The JSON ledger (`state.py`) stores a mix of config values, runtime counters, and per-iteration records. This makes it impossible to:

- Reset state without losing config
- Validate config independently of the runtime
- Have multiple iterations running with different configs

**Research Notes:**
Separate into three clear layers:

1. **`LoopConfig`** — Immutable (or copy-on-write) user settings from CLI flags + config file. Pydantic model with validation.
2. **`LoopState`** — Mutable runtime state: current iteration, error count, mitigations, active context. Reset separately from config.
3. **`IterationLedger`** — Persisted iteration history: per-turn output, timestamps, git diffs, decisions. Append-only log.

This architecture enables config-only reloads, state resets without config loss, and clean separation for testing.

---

### ARC-002: Error recovery path lacks transactional rollback for partial state updates

| Field | Value |
|-------|-------|
| **Category** | Architecture Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | B-001, ARC-001 |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/error_recovery.py`, `pi_loop/loop.py` |

**Description:**
When an iteration fails mid-way, the error recovery path updates state (incrementing error counts, adjusting mitigations, updating the JSON ledger) but does not have a transactional rollback mechanism. If the recovery itself fails (e.g., sentinel file write fails, notification fails), the state is left in an inconsistent partial-update state.

**Research Notes:**
Introduce a simple rollback pattern:

```python
class RecoveryTransaction:
    def __init__(self, state):
        self.state = copy.deepcopy(state)
        self.original = state
        
    def commit(self):
        self.original.update(self.state)
        
    def rollback(self):
        pass  # Don't apply changes
```

Or use an append-only log model where state is reconstructed from sequential events (event sourcing). This eliminates partial-update inconsistency entirely.

---

## B-13: Automation Opportunities

### AUT-001: Add mypy to pre-commit hooks for automated type-checking

| Field | Value |
|-------|-------|
| **Category** | Automation Opportunities |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | CICD-001 (must fix mypy errors first) |
| **Status** | ⏳ Pending, ❌ Blocked by CICD-001 |
| **Affected Files** | `.pre-commit-config.yaml` |

**Description:**
The pre-commit config currently runs ruff (lint + format) but does not run mypy. Adding mypy to pre-commit ensures type errors are caught before code is committed, not just in CI (where it's currently silently ignored).

**Research Notes:**
After fixing existing mypy errors (CICD-001), add to `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/pre-commit/mirrors-mypy
  rev: v2.1.0
  hooks:
    - id: mypy
      args: [--config-file=pyproject.toml]
      additional_dependencies: [pydantic, fastapi, httpx]
```

---

### AUT-002: No automated license header or copyright check

| Field | Value |
|-------|-------|
| **Category** | Automation Opportunities |
| **Priority** | 🔵 Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `.pre-commit-config.yaml` |

**Description:**
There is no pre-commit hook checking for consistent license headers or copyright statements in source files. While the project has an MIT `LICENSE` file, individual source files lack the standard MIT copyright header.

**Research Notes:**
Add a pre-commit hook (e.g., `add-license-header` or a custom bash snippet) that verifies each `.py`, `.js`, `.css`, `.html` file has a standard header:

```python
# Copyright 2026 Hermes Agent / Nous Research
# SPDX-License-Identifier: MIT
```

Or use a relaxed approach: only verify that new files have headers, skip existing files.

---

## B-14: Feature Ideas

### FTR-001: Docker image and Docker Compose for containerized deployment

| Field | Value |
|-------|-------|
| **Category** | Feature Ideas |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | Root (new `Dockerfile`, `docker-compose.yml`) |

**Description:**
Docker and docker-compose files exist in stale worktrees but were never ported to main. A containerized deployment would provide:

- Reproducible environment (pin Python + system deps)
- Easy deployment on any Linux server
- Volume mounts for config and data persistence
- Integrated web UI port mapping
- Resource limits (CPU, memory) for the daemon and subprocesses

**Research Notes:**

- Base image: `python:3.12-slim` (or 3.11-slim for maximum compatibility)
- Install pi-coding-agent in the Dockerfile
- Use multi-stage build to minimize image size
- `docker-compose.yml`: services for `pi-loop` (daemon + web), optional `redis` for pub/sub state
- Docker healthcheck endpoint for orchestration platforms

---

### FTR-002: Prometheus metrics endpoint for operational monitoring

| Field | Value |
|-------|-------|
| **Category** | Feature Ideas |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | OBS-002 (same implementation) |
| **Status** | ⏳ Pending |
| **Affected Files** | `web_app/server.py` (new `/metrics` endpoint) |

**Description:**
There is no metrics endpoint for Prometheus/Grafana monitoring. Key operational metrics that should be exposed:

- `pi_loop_iterations_total` — Count of iterations by status (success, error, timeout, convergence)
- `pi_loop_iteration_duration_seconds` — Histogram of subprocess execution time (p50/p95/p99)
- `pi_loop_active_workers` — Current active worker count (gauge)
- `pi_loop_errors_total` — Error count by type (timeout, parse, subprocess, config)
- `pi_loop_convergence_hits_total` — How often convergence detection triggered
- `pi_loop_cooldown_seconds` — Current cooldown time (gauge)

**Research Notes:**
Use `prometheus_client` (check if available or add to deps). Create a `MetricsCollector` that threads through the loop engine and is exposed at `/metrics`. Provide a `monitoring/grafana-dashboard.json` template.

---

## B-15: Observability / Monitoring

### OBS-001: No structured logging — `print()` used throughout with no log levels or correlation IDs

| Field | Value |
|-------|-------|
| **Category** | Observability |
| **Priority** | 🟠 High |
| **Impact** | High |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/error_recovery.py`, `pi_loop/git_utils.py`, `pi_loop/heartbeat.py`, `pi_loop/preflight.py`, `web_app/server.py` |

**Description:**
The daemon uses `print()` for all logging — no structured/JSON logging, no log levels (DEBUG, INFO, WARNING, ERROR), no correlation IDs. Tracing a single iteration's flow from CLI input through `_execute_task` to `run_loop` to error recovery requires manually correlating timestamps across print statements. The web server uses uvicorn's default access log but the application logs are unstructured.

**Research Notes:**
Replace all `print()` calls with `structlog` (check availability) or stdlib `logging` with a JSON formatter:

```python
import structlog
logger = structlog.get_logger()

# Usage
logger.info("iteration.completed", iteration=n, duration=elapsed, status="success")
logger.warning("recovery.adapted", error_type=err_type, mitigations=mitigations)
logger.error("subprocess.failed", exit_code=code, stderr=stderr[:500])

# Correlation ID per run
logger.bind(loop_id=loop_id, iteration=n)
```

Key improvements:

- Structured JSON output for log aggregators (Loki, ELK, Datadog)
- Correlation/iteration IDs for request tracing
- Consistent log levels (DEBUG for development, INFO for production)
- Request IDs in web server logs for API call tracing
- File + console logging with different formats

---

### OBS-002: No health check endpoint or daemon status probe

| Field | Value |
|-------|-------|
| **Category** | Observability |
| **Priority** | 🟡 Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |
| **Affected Files** | `web_app/server.py` (new `/health` endpoint) |

**Description:**
There is no `/health` or similar readiness/liveness endpoint. Docker orchestration platforms (Kubernetes, Nomad, Docker Compose) need a health check to know when the service is ready and whether it's still alive. The existing `/api/status` endpoint returns 200 even if the daemon is in a broken state (no subprocess, corrupted state file).

**Research Notes:**
Add a dedicated `/health` endpoint that performs:

1. **Liveness check**: Is the web server running? (always true if responding)
2. **Readiness check**: Is the daemon process alive? Is the config file readable?
3. **Dependency check**: Is `pi` binary available on PATH?
4. **Database check**: Is the JSON ledger file readable (not corrupt)?

The endpoint should return HTTP 200 with `{"status": "healthy"}` or HTTP 503 with `{"status": "unhealthy", "checks": {"pi": "missing", "ledger": "corrupt"}}`. This enables Docker health checks and load balancer probes.

---

## Appendix: Completed Items Summary

The following items have been addressed in previous iterations but are noted for historical context:

| ID | Title | Category | Status |
|----|-------|----------|--------|
| — | API-key authentication middleware on all `/api/*` endpoints | Security | ✅ Done |
| — | CORS tightened to localhost-only by default | Security | ✅ Done |
| — | HMAC-SHA256 webhook signing | Security | ✅ Done |
| — | Validate_config() wired into save_config_api — returns 422 on invalid input | Security | ✅ Done |
| — | Config file corruption resilience — graceful degradation with default fallback | Reliability | ✅ Done |
| — | Subprocess zombie leak — proc.kill() + proc.wait(timeout=5) | Bug | ✅ Done |
| — | Silent exception swallowing — all bare except:pass replaced with typed, logged handlers | Tech Debt | ✅ Done |
| — | Empty SSE heartbeat listener removed | Cleanup | ✅ Done |
| — | Empty catch blocks in app.js — console.error() added | Cleanup | ✅ Done |
| — | Duplicate worker_term initialization consolidated | Cleanup | ✅ Done |
| — | Ruff ARG001 unused parameters fixed | Cleanup | ✅ Done |
| — | Mypy type errors fixed across 5 files | Cleanup | ✅ Done |
| — | Hard-coded `/tmp` path consolidation (partial — status.py, preflight.py, help_topics.py, loop.py) | Bug | ✅ Done |
| — | 440+ unit tests created across 19 test files | Testing | ✅ Done |
| — | SEC-003 redundant get_auth_config removed | Cleanup | ✅ Done |
| — | validate_json_output() dead code removed | Tech Debt | ✅ Done |

---

## Prioritized Action Plan (Top 10)

| Rank | ID | Title | Priority | Effort | Why Now |
|------|----|-------|----------|--------|---------|
| 1 | **TEC-001 / REF-001** | Decompose `run_loop()` (435 lines, 71 params) | 🔴 Critical | XLarge | Blocks all other improvements to the core loop; highest RO I refactoring |
| 2 | **B-001** | Lost error recovery mitigations silently discarded | 🟠 High | Small | Defect causing silent data loss — trivial fix, high impact |
| 3 | **CICD-001** | Mypy errors swallowed by `|| true` | 🟠 High | Medium | Type enforcement is the cheapest bug-prevention strategy |
| 4 | **ARC-001** | Separate config validation from runtime state | 🟠 High | Large | Enables config-only reloads, multi-instance, clean testing |
| 5 | **OBS-001** | Replace `print()` with structured logging | 🟠 High | Medium | Without this, production debugging is manual and slow |
| 6 | **SEC-001** | Audit API authentication coverage | 🟠 High | Small | Verify all endpoints are actually protected |
| 7 | **TST-001** | Integration tests for real subprocess lifecycle | 🟠 High | Large | Only way to catch regressions in the core value proposition |
| 8 | **TEC-002** | Fix circular import cli.py ↔ help_topics.py | 🟠 High | Medium | Import-order bugs are hard to debug and intermittent |
| 9 | **B-002** | Subprocess zombie leak from unwaited children | 🟠 High | Small | Zombie processes can exhaust PID table on long-running instances |
| 10 | **TST-002** | Test file_watcher.py (zero coverage) | 🟡 Medium | Small | Untested module in the watch-execute pipeline |

---

## Summary

| Metric | Value |
|--------|-------|
| **Total backlog items** | 34 |
| **Critical (P0)** | 3 |
| **High (P1)** | 8 |
| **Medium (P2)** | 14 |
| **Low (P3)** | 9 |
| **All 15 categories covered** | ✅ |
| **Categories with Critical items** | Bugs (0), Technical Debt (1), Refactoring (1) |
| **Top 3 priorities** | `run_loop()` decomposition, lost error recovery fix, mypy enforcement in CI |
