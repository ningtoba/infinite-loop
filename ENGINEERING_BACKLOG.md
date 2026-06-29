# Engineering Backlog — pi-loop v14.39.0

> Living engineering backlog for **pi-loop** — the autonomous task execution daemon powered by the `pi` coding agent.
> Consolidated from `ENGINEERING_BACKLOG.md` and `BACKLOG.md` into a single authoritative document.
> Generated: 2026-06-30

---

## Executive Summary

**pi-loop** is a Python CLI daemon that runs iterative coding-agent tasks in a subprocess loop, tracking progress in a JSON ledger with a FastAPI + SSE web dashboard. It is an early-stage project (~202 commits, single developer, 5-day active development span) transitioning from rapid prototyping toward production readiness.

### What's Good

| Dimension | Status |
|-----------|--------|
| **Architecture** | Clean modular structure (25+ modules, single-responsibility) |
| **Packaging** | Modern PEP 621 with pip-compile lock files |
| **Testing** | 481 tests across 22 test files, all passing in ~3s |
| **CI** | Python 3.10–3.13 matrix with ruff lint + format + pytest |
| **Security** | API-key auth middleware, CORS hardening, SSE backoff |
| **DX** | Ruff lint with 8 rule categories, pre-commit hooks, Makefile targets |
| **Dependabot** | Weekly grouped dependency updates configured |

### What Needs Work

| Dimension | Priority Area |
|-----------|---------------|
| **Architecture** | `run_loop()` is a **435-line monolithic function** with 71 parameters still in the signature — **#1 technical debt** |
| **Testing** | Core loop (`loop.py`) at **19% coverage**, CLI entry point at **12%**, file watcher at **0%** |
| **CI/CD** | Mypy errors silently swallowed (`|| true`), no coverage reporting, no release automation |
| **Observability** | No structured logging (`print()` throughout), no health check endpoint |
| **Documentation** | No API docs, no CONTRIBUTING guide, README version mismatch (0.1.0 vs 14.39.0) |
| **Config** | Schema maintained across 4 locations with no single source of truth |
| **Frontend** | Vanilla JS SPA with global mutable state, no module system |

### Active vs Completed

| Status | Count |
|--------|-------|
| 🔴 **Critical Active** | 3 |
| 🟠 **High Active** | 9 |
| 🟡 **Medium Active** | 17 |
| 🔵 **Low Active** | 13 |
| **Total Active** | **42** |
| ✅ **Completed** | 24 |
| ❌ **Won't Do / Investigated** | 2 |

---

## Quick Wins

These items deliver the highest value-to-effort ratio and should be tackled first:

| Rank | ID | Title | Effort | Impact | Why |
|------|----|-------|--------|--------|-----|
| 1 | CICD-001 | Wire mypy to actually fail CI | Medium | High | Cheapest bug prevention — currently silently disabled |
| 2 | SEC-001 | Audit API auth endpoint coverage | Small | High | Verify the auth middleware actually protects everything |
| 3 | BUG-001 | Config corruption notification | Small | Medium | Silent data loss with no user feedback |
| 4 | CICD-004 | Add coverage reporting to CI | Small | Medium | See exactly what's untested on every push |
| 5 | CLEAN-005 | Fix empty catch blocks in app.js | Small | Medium | Frontend errors are invisible to developers |
| 6 | DOC-003 | Fix README version mismatch | Trivial | Low | First impression for new contributors |
| 7 | CLEAN-004 | Remove dead CSS toggle switch | Trivial | Low | Clean up unused code |
| 8 | TOOL-002 | Add .coverage to .gitignore | Trivial | Low | Prevent accidental binary commits |
| 9 | BUG-004 | Fix first CPU read showing 0% | Small | Low | Confusing monitoring on first access |
| 10 | PERF-003 | SSE reconnect exponential backoff | Small | Medium | Prevents server load spike on restart |

---

## Status Legend

| Status | Meaning |
|--------|---------|
| ⏳ **Pending** | Not yet started |
| 🔄 **In Progress** | Currently being worked on |
| ✅ **Done** | Completed and verified |
| ❌ **Blocked** | Blocked by another item |

---

## Priority Scale

| Label | Meaning | Response Time |
|-------|---------|---------------|
| 🔴 **Critical** | Blocking release, security vulnerability, or data loss | Fix immediately |
| 🟠 **High** | Significant quality/functionality gap | Next iteration |
| 🟡 **Medium** | Important but not urgent | This quarter |
| 🔵 **Low** | Nice to have, polish, or future consideration | When convenient |

---

## 🐛 1. Bugs & Issues

### BUG-001: Config file corruption silently returns defaults

| Field | Value |
|-------|-------|
| **ID** | BUG-001 |
| **Category** | Bugs & Issues |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/config_file.py`, `web_app/config_manager.py` |

**Description:** When the JSON config file is corrupt (partial write, disk full, concurrent write), `_read_stored()` falls back to defaults silently. The web UI shows default config with no indication that custom settings were lost. The corrupt file is backed up with a `.corrupt` suffix but the user receives no feedback.

**Acceptance Criteria:**

- Add `corrupt: true` flag to config API response
- Show warning banner in web UI when config fell back
- Log at WARNING level with corrupt file path
- Add atomic write pattern (write to temp, rename) to prevent future corruption

---

### BUG-002: Duplicate `content_block_stop` handler in `_execute_task`

| Field | Value |
|-------|-------|
| **ID** | BUG-002 |
| **Category** | Bugs & Issues |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/loop.py` |

**Description:** Two separate `content_block_stop` handler blocks exist in `_execute_task` with overlapping logic. This creates potential double-counting of tool calls and confusing code flow.

**Acceptance Criteria:**

- Merge into single handler
- Verify tool call counting is correct (not doubled)
- Add test that asserts correct tool call count for multi-step responses

---

### BUG-003: Colorized output breaks iteration detection in web UI

| Field | Value |
|-------|-------|
| **ID** | BUG-003 |
| **Category** | Bugs & Issues |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/loop_manager.py` |

**Description:** `_parse_daemon_line` in `loop_manager.py` checks for `"[ITERATION"` but if the daemon logs with ANSI color codes, the bracket prefix could be broken across escape sequences, causing the regex to miss iteration starts.

**Acceptance Criteria:**

- Strip ANSI codes before matching
- Add test with colorized and non-colorized daemon output
- Verify iteration counter stays accurate

---

### BUG-004: First CPU read always returns 0%

| Field | Value |
|-------|-------|
| **ID** | BUG-004 |
| **Category** | Bugs & Issues |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/system_utils.py` |

**Description:** `_get_cpu_percent()` returns 0 on first call because it has no `_prev_*` values for delta calculation. This means the first status read in any monitoring session shows 0% CPU.

**Acceptance Criteria:**

- Return `None` or skip the first reading instead of returning 0
- Or pre-warm the initial values on module load
- Document the behavior

---

### BUG-005: Inconsistent HTTP status codes for logical errors

| Field | Value |
|-------|-------|
| **ID** | BUG-005 |
| **Category** | Bugs & Issues |
| **Priority** | 🟡 Medium |
| **Impact** | 2 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/server.py` |

**Description:** Config save and loop control endpoints return HTTP 200 with `{"success": false}` for logical errors (e.g., trying to stop a non-running loop) instead of proper 4xx status codes. This makes it impossible for API clients to distinguish logical errors from server errors without parsing the response body.

**Acceptance Criteria:**

- Return 409 Conflict for loop state conflicts (trying to stop when not running)
- Return 400 Bad Request for invalid parameters
- Return 422 Unprocessable Entity for validation failures (already done for config)
- Keep response bodies consistent (`{"detail": "message"}`)

---

## 🏗️ 2. Architecture & Design

### ARCH-001: Decompose monolithic `run_loop()` function

| Field | Value |
|-------|-------|
| **ID** | ARCH-001 |
| **Category** | Architecture & Design |
| **Priority** | 🔴 Critical |
| **Impact** | 5 / 5 |
| **Effort** | 5 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/loop.py` |

**Description:** `run_loop()` is the core of the daemon — a **~435-line function body** that handles: sentinel checks, iteration counting, goal cycling, progressive context, subprocess execution, git state capture, idle detection, error classification, notification dispatch, HTML dashboard generation, HTTP callbacks, on-error/success commands, cooldown management, error-recovery adaptation, iteration cap trimming, and goal evolution. It violates the Single Responsibility Principle at every level. A `LoopConfig` dataclass was introduced to compress parameters, but the function body was never decomposed. This is the single highest-ROI refactoring available.

**Acceptance Criteria:**

- Extract `_setup_iteration_context(state, config) -> IterationContext`
- Extract `_execute_iteration(context) -> IterationResult`
- Extract `_process_iteration_result(result, state) -> Action` (convergence, next step, exit)
- Extract `_apply_recovery(state, error) -> None`
- Extract `_emit_notifications(result, config) -> None`
- Extract `_check_termination(state, config) -> bool`
- `run_loop()` body reduced to orchestrating these extracted functions
- All extracted functions independently unit-testable without mocks for the subprocess layer

---

### ARCH-002: Separate config from runtime state

| Field | Value |
|-------|-------|
| **ID** | ARCH-002 |
| **Category** | Architecture & Design |
| **Priority** | 🟠 High |
| **Impact** | 4 / 5 |
| **Effort** | 4 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | ARCH-001 |
| **Affected Files** | `pi_loop/config.py`, `pi_loop/state.py`, `pi_loop/loop.py` |

**Description:** Configuration and runtime state are conflated throughout the codebase. `config.py` handles both static settings (user preferences) and dynamic state (current iteration, mitigations, error history). The JSON ledger stores a mix of config values, runtime counters, and iteration records, making it impossible to reset state without losing config.

**Acceptance Criteria:**

- **`LoopConfig`** — Immutable/copy-on-write user settings from CLI + config file (Pydantic model)
- **`LoopState`** — Mutable runtime state: iteration count, errors, mitigations, active context
- **`IterationLedger`** — Append-only iteration history with per-turn output, timestamps, decisions
- Config-only reloads possible without affecting runtime state
- State resets possible without losing config

---

### ARCH-003: Singleton consolidation — introduce dependency injection

| Field | Value |
|-------|-------|
| **ID** | ARCH-003 |
| **Category** | Architecture & Design |
| **Priority** | 🟠 High |
| **Impact** | 4 / 5 |
| **Effort** | 4 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | ARCH-001 |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/heartbeat.py`, `pi_loop/git_utils.py`, `pi_loop/error_recovery.py`, `pi_loop/color_utils.py` |

**Description:** Multiple modules use module-level mutable state (global variables, `threading.Event`, module-scoped flags) for cross-module communication: `_shutdown_requested` in `loop.py`, heartbeat poll flags, counters in `error_recovery.py`, the `colorizer` singleton in `color_utils.py`. This makes testing state-dependent, creates implicit coupling, and prevents multiple concurrent loop instances.

**Acceptance Criteria:**

- Introduce a `LoopContext` object (or extend `LoopConfig`) holding all mutable state
- Pass context explicitly to all functions that need it
- Remove all module-level mutable state
- Each test creates a fresh context — no test pollution
- Enable future multi-instance support

---

### ARCH-004: Quadruple config maintenance — single source of truth

| Field | Value |
|-------|-------|
| **ID** | ARCH-004 |
| **Category** | Architecture & Design |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pyproject.toml`, `pi_loop/config.py`, `pi_loop/config_file.py`, `web_app/config_manager.py` |

**Description:** Config defaults and schema are maintained across four locations: `pyproject.toml` (tool settings), `config.py` (LoopConfig dataclass), `config_file.py` (file I/O + validation), and `config_manager.py` (web API CRUD). Adding a config option requires coordinated changes in all four files, and they have already diverged (e.g., `heartbeat_interval` default differs).

**Acceptance Criteria:**

- `LoopConfig` dataclass becomes the single source of truth for all defaults + schema
- `config_file.py` reads/writes JSON derived from LoopConfig schema
- `config_manager.py` derives CLI arg builder, validation, and web form from LoopConfig
- Automated test that verifies all four layers agree on defaults

---

### ARCH-005: Error recovery path lacks transactional rollback

| Field | Value |
|-------|-------|
| **ID** | ARCH-005 |
| **Category** | Architecture & Design |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | ARCH-002 |
| **Affected Files** | `pi_loop/error_recovery.py`, `pi_loop/loop.py` |

**Description:** When an iteration fails mid-way, the error recovery path updates state (error counts, mitigations, ledger) with no transactional rollback. If recovery itself fails (sentinel write fails, notification fails), the state is left in an inconsistent partial-update state.

**Acceptance Criteria:**

- Introduce `RecoveryTransaction` context manager with `commit()` / `rollback()`
- Or switch to append-only log model where state is reconstructed from events
- Verify no partial state updates survive recovery failures

---

## 🧪 3. Testing & Quality

### TEST-001: Integration tests for real subprocess lifecycle

| Field | Value |
|-------|-------|
| **ID** | TEST-001 |
| **Category** | Testing & Quality |
| **Priority** | 🟠 High |
| **Impact** | 4 / 5 |
| **Effort** | 5 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `tests/` (new `tests/integration/` directory) |

**Description:** All 481 tests are pure unit tests with heavy mocking. There are zero tests that: spawn a real subprocess, run one full iteration lifecycle, test daemon start→iterate→stop, test SSE streaming end-to-end, or test sentinel-based stop/pause with a running loop. The core value proposition is never end-to-end verified.

**Acceptance Criteria:**

- Create `tests/integration/` directory with conftest fixtures
- Build a `mock_pi.sh` shell script that emits realistic NDJSON output
- Integration test: single iteration end-to-end
- Integration test: multi-iteration convergence detection
- Integration test: error recovery (inject subprocess failures)
- Integration test: sentinel-based stop/pause
- Integration test: web UI endpoints → daemon → response

---

### TEST-002: `file_watcher.py` has zero test coverage

| Field | Value |
|-------|-------|
| **ID** | TEST-002 |
| **Category** | Testing & Quality |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/file_watcher.py`, `tests/` (new `tests/test_file_watcher.py`) |

**Description:** The file watcher module — responsible for detecting filesystem changes and triggering re-runs — has zero tests. If file-watching behavior breaks, the daemon silently stops responding to file changes.

**Acceptance Criteria:**

- Watch a file for modifications (mock `os.stat` / `Path.stat`)
- Trigger iteration on file change
- Debounce rapid file changes
- Detect stable vs unstable file state (wait for writes to finish)
- Handle file deletion gracefully

---

### TEST-003: Low coverage on critical modules — `loop.py`, `cli.py`, `status.py`

| Field | Value |
|-------|-------|
| **ID** | TEST-003 |
| **Category** | Testing & Quality |
| **Priority** | 🟠 High |
| **Impact** | 4 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | ARCH-001 |
| **Affected Files** | `pi_loop/loop.py` (19%), `pi_loop/cli.py` (12%), `pi_loop/status.py` (26%) |

**Description:** The three most critical modules for daemon functionality have extremely low coverage. `loop.py` (core iteration engine) is at 19% — the main `run_loop()` orchestration is untested. `cli.py` is at 12% — the `main()` entry point and all command dispatch logic is untested. `status.py` is at 26%.

**Acceptance Criteria (`loop.py`):**

- Test exit-early conditions: sentinel files, max turns, convergence, goal exhausted, idle timeout
- Test iteration lifecycle: setup → execute → process → recover → cycle
- Test all notification paths (desktop, HTTP, HTML dashboard, on-error command)

**Acceptance Criteria (`cli.py`):**

- Test all 14+ CLI flag combinations via argparse directly
- Test `--help`, `--doctor`, `--preflight`, `--status`, `--init`, `--demo`, `--completion-script`
- Test flag interaction errors (incompatible combinations)

**Acceptance Criteria (`status.py`):**

- Test all rendering paths: active, idle, error, done
- Test with controlled state dicts (edge cases: missing keys, zero values, extreme values)

---

### TEST-004: `server.py` coverage below 60%

| Field | Value |
|-------|-------|
| **ID** | TEST-004 |
| **Category** | Testing & Quality |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/server.py` (55%) |

**Description:** The FastAPI server module has 55% coverage. Many API routes (CORS, SSE stream, static file serving, config preview, log retrieval, loop reset) are untested. The auth middleware and rate limiting are well-covered, but the business logic endpoints are not.

**Acceptance Criteria:**

- Test all REST API routes: `/api/status`, `/api/ledger`, `/api/config/groups`, `/api/config/cli-preview`, `/api/iterations`, `/api/logs`, `/api/system`, `/api/health`, `/api/loop/reset`
- Test error handlers (404, 405, 500)
- Test SSE stream with connected client
- Test CORS headers on all origins
- Target minimum 80% coverage on `server.py`

---

### TEST-005: No end-to-end auth test that all mutable endpoints are protected

| Field | Value |
|-------|-------|
| **ID** | TEST-005 |
| **Category** | Testing & Quality |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | SEC-001 |
| **Affected Files** | `tests/test_auth.py` |

**Description:** While `test_auth.py` exists with 23 tests, it doesn't enumerate all routes to verify auth is enforced on every mutable endpoint. New endpoints could be added without auth protection.

**Acceptance Criteria:**

- Add a parametrized test that enumerates all registered routes
- For each non-GET and non-static route, verify auth is required
- For each route, verify auth can be disabled (for local-only mode)
- Add test that static files and index.html don't leak API keys

---

## 🔧 4. Tooling & Developer Experience

### TOOL-001: Missing `.editorconfig` file

| Field | Value |
|-------|-------|
| **ID** | TOOL-001 |
| **Category** | Tooling & DX |
| **Priority** | 🟡 Medium |
| **Impact** | 2 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | Root (new `.editorconfig`) |

**Description:** No `.editorconfig` exists. Developers with different editor settings may accidentally introduce inconsistent indentation across Python, JS, CSS, HTML, YAML, and TOML files.

**Acceptance Criteria:**

- Add `.editorconfig` with: Python (4 spaces), JS/HTML/CSS (2 spaces), YAML (2 spaces), Makefile (tabs)
- Add `end_of_line = lf`, `charset = utf-8`, `trim_trailing_whitespace = true`, `insert_final_newline = true`

---

### TOOL-002: `.coverage` not in `.gitignore`

| Field | Value |
|-------|-------|
| **ID** | TOOL-002 |
| **Category** | Tooling & DX |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `.gitignore` |

**Description:** A 53KB `.coverage` binary file is present in the repo root and not listed in `.gitignore`. If accidentally committed, it adds binary noise to diffs and bloats the repo.

**Acceptance Criteria:**

- Add `.coverage`, `.coverage.*`, `htmlcov/`, `coverage/` to `.gitignore`
- Remove existing `.coverage` from tracking (but don't delete it from disk)

---

### TOOL-003: Redundant `pip install` in `make test`

| Field | Value |
|-------|-------|
| **ID** | TOOL-003 |
| **Category** | Tooling & DX |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `Makefile` |

**Description:** The `test` target runs `pip install -e ".[test]"` before every `python -m pytest` invocation. This wastes 2-3 seconds per local test run. The `install-dev` target already installs test dependencies.

**Acceptance Criteria:**

- Remove the `pip install` line from the `test` target
- Assume dependencies are already installed (add a comment noting this)

---

### TOOL-004: Redundant pre-commit mechanisms — `.pre-commit-config.yaml` vs `.githooks/pre-commit`

| Field | Value |
|-------|-------|
| **ID** | TOOL-004 |
| **Category** | Tooling & DX |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `.pre-commit-config.yaml`, `.githooks/pre-commit`, `.githooks/README.md` |

**Description:** Two parallel pre-commit mechanisms exist: `.pre-commit-config.yaml` (Python `pre-commit` tool with ruff + 5 hooks) and `.githooks/pre-commit` (bash script that runs ruff check + format). These overlap and may conflict. The `.githooks/README.md` describes a different purpose (shell completion regeneration) than what the script actually does (ruff linting).

**Acceptance Criteria:**

- Keep `.pre-commit-config.yaml` as the primary mechanism
- Archive or remove `.githooks/pre-commit` bash script
- Update `.githooks/README.md` or remove it
- Ensure `make pre-commit` installs the YAML-based hooks

---

### TOOL-005: Stale analysis artifacts clutter repo root

| Field | Value |
|-------|-------|
| **ID** | TOOL-005 |
| **Category** | Tooling & DX |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `.analysis/`, `synthesis-output.json`, `tooling-findings.txt` |

**Description:** The repo root contains AI-analysis artifacts (`.analysis/`, `synthesis-output.json`, `tooling-findings.txt`) that are outputs from automated tools, not source code. These clutter the tree and confuse new developers.

**Acceptance Criteria:**

- Move to `.archive/` or delete from working tree
- Add `*.analysis*` and `synthesis-output*` to `.gitignore`
- Evaluate and prune stale worktree branches (`hermes/hermes-*`)

---

### TOOL-006: No Docker or devcontainer for one-command setup

| Field | Value |
|-------|-------|
| **ID** | TOOL-006 |
| **Category** | Tooling & DX |
| **Priority** | 🔵 Low |
| **Impact** | 2 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | Root (new `Dockerfile`, `docker-compose.yml`, `.devcontainer/devcontainer.json`) |

**Description:** Docker and devcontainer files exist only in stale git worktrees. New contributors must manually set up a Python venv, install deps, and configure their environment.

**Acceptance Criteria:**

- Create minimal `Dockerfile` (python:slim + pi + pi-loop)
- Create `docker-compose.yml` with web server + volume mounts
- Create `.devcontainer/devcontainer.json` for VS Code/Cursor remote development
- Include health check endpoint (see FEAT-004)

---

## ⚡ 5. Performance

### PERF-001: Blocking `subprocess.call()` in on-error/success handlers

| Field | Value |
|-------|-------|
| **ID** | PERF-001 |
| **Category** | Performance |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/loop.py` |

**Description:** `run_loop()` calls `subprocess.call()` for on-error and on-success commands. This is a **blocking call** — if the command takes 30 seconds, the entire daemon loop is frozen. No convergence checks, sentinel monitoring, or SSE updates during that time.

**Acceptance Criteria:**

- Replace with `asyncio.create_subprocess_exec()` and timeout (web context)
- For CLI-only mode: `subprocess.Popen()` with non-blocking poll loop
- Configurable timeout (default: 30s) for on-error/on-success commands
- Ensure sentinel file is still polled during command execution

---

### PERF-002: No connection pooling for webhook HTTP calls

| Field | Value |
|-------|-------|
| **ID** | PERF-002 |
| **Category** | Performance |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/loop.py` |

**Description:** Each webhook notification creates a new HTTP connection via `urllib.request`. Under high-iteration scenarios with multiple webhook targets, this adds connection setup latency to every notification.

**Acceptance Criteria:**

- Switch to `httpx` (already available in venv) with shared `AsyncClient` (web path)
- For CLI path: `urllib3.PoolManager` for connection reuse
- Test with 100+ rapid webhook dispatches to verify reuse

---

### PERF-003: SSE reconnect uses fixed delay instead of exponential backoff

| Field | Value |
|-------|-------|
| **ID** | PERF-003 |
| **Category** | Performance |
| **Priority** | 🟡 Medium |
| **Impact** | 2 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/static/app.js` |

**Description:** The SSE reconnect uses a fixed 5s delay. When the server restarts, all connected clients reconnect simultaneously at 5s intervals, creating a thundering-herd load spike.

**Acceptance Criteria:**

- Implement exponential backoff: 1s, 2s, 4s, 8s, max 30s
- Add random jitter (±25%) to prevent synchronized reconnects
- Reset backoff to minimum on successful connection

---

## 🔒 6. Security

### SEC-001: Audit all REST endpoint auth coverage

| Field | Value |
|-------|-------|
| **ID** | SEC-001 |
| **Category** | Security |
| **Priority** | 🟠 High |
| **Impact** | 4 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/server.py` |

**Description:** API-key auth middleware was recently added (commit `08cba91`) to `/api/*` endpoints, but it needs auditing that: all mutable endpoints are covered; auth can't be bypassed by path tricks; the disable path works; and the API key is not logged or exposed in HTML/error responses.

**Acceptance Criteria:**

- Enumerate all routes and verify auth middleware applies to every POST/PUT/DELETE
- Verify static files and index.html don't leak API key via error messages
- Verify auth disable path (`--no-auth` or config) works correctly
- Verify API key is not logged at any log level
- Add parametrized test (TEST-005)

---

### SEC-002: Path sanitization for user-supplied file arguments

| Field | Value |
|-------|-------|
| **ID** | SEC-002 |
| **Category** | Security |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/cli.py`, `pi_loop/config.py`, `pi_loop/file_utils.py` |

**Description:** CLI flags like `--goals-file`, `--cwd`, and config file paths accept user-supplied strings passed directly to filesystem ops without validation. While this is a local CLI tool, path traversal or symlink attacks could cause unintended reads/writes.

**Acceptance Criteria:**

- Resolve all paths to absolute via `os.path.realpath()` before use
- Verify resolved paths are within expected directories (or allowlist)
- Warn on symlinks pointing outside the project tree
- Add tests for path-traversal attempts

---

## 📚 7. Documentation

### DOC-001: No API documentation for REST endpoints

| Field | Value |
|-------|-------|
| **ID** | DOC-001 |
| **Category** | Documentation |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/server.py`, `web_app/config_manager.py`, `web_app/loop_manager.py` |

**Description:** The FastAPI REST API has no formal documentation. While FastAPI supports auto-generated OpenAPI docs, the endpoints need docstrings, Pydantic response models, and proper metadata for this to be useful.

**Acceptance Criteria:**

- Add Pydantic response models for all endpoints
- Add `summary`, `description`, `response_description` to each route decorator
- Add response status code documentation (200, 400, 404, 409, 422, 429, 500)
- Verify `/docs` and `/redoc` are accessible
- Add OpenAPI export to build step

---

### DOC-002: Missing CONTRIBUTING.md and CHANGELOG.md

| Field | Value |
|-------|-------|
| **ID** | DOC-002 |
| **Category** | Documentation |
| **Priority** | 🔵 Low |
| **Impact** | 2 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | Root (new `CONTRIBUTING.md`, `CHANGELOG.md`) |

**Description:** No `CONTRIBUTING.md` (setup, tests, PR workflow, conventions) and no `CHANGELOG.md` (release history based on conventional commits). The repo has ~202 conventional-commit messages that would make changelog generation straightforward.

**Acceptance Criteria:**

- Create `CONTRIBUTING.md`: setup, running tests, lint/format, PR workflow, commit conventions
- Create `CHANGELOG.md` from git log using conventional commit categories
- Update README version to match `pyproject.toml` (14.39.0)

---

### DOC-003: README version mismatch

| Field | Value |
|-------|-------|
| **ID** | DOC-003 |
| **Category** | Documentation |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `README.md` |

**Description:** The README says `0.1.0` while `pyproject.toml` says `14.39.0`. This version mismatch confuses new contributors and integrations that check the version string.

**Acceptance Criteria:**

- Fix README version to match `pyproject.toml`
- Use `VERSION` from `pi_loop/__init__.py` programmatically if possible

---

## 🔄 8. CI/CD

### CICD-001: Mypy errors silently swallowed by `|| true`

| Field | Value |
|-------|-------|
| **ID** | CICD-001 |
| **Category** | CI/CD |
| **Priority** | 🟠 High |
| **Impact** | 4 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `Makefile`, `.github/workflows/ci.yml` |

**Description:** Both the `make mypy` target and the CI lint job append `|| true` / `; true`, meaning mypy exits with code 0 regardless of findings. Type errors never block CI. The entire mypy configuration is essentially decoration.

**Acceptance Criteria:**

- Remove `|| true` / `; true` from Makefile `mypy` target and CI
- Fix all existing mypy errors first (or add per-module `# type: ignore` overrides)
- Add mypy to pre-commit hooks
- Consider `strict = true` and `disallow_untyped_defs = true` once clean

---

### CICD-002: No smoke test in CI pipeline

| Field | Value |
|-------|-------|
| **ID** | CICD-002 |
| **Category** | CI/CD |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `.github/workflows/ci.yml` |

**Description:** CI runs linters and unit tests but never verifies that the package installs and runs. A broken import, missing entry point, or runtime error would not be caught until deployment.

**Acceptance Criteria:**

- Add step to CI `test` job: `pi-loop --help` after pip install
- Add step: `pi-loop-web --help` (if applicable)
- Import test: `python -c "from pi_loop import VERSION; print(VERSION)"`

---

### CICD-003: No release automation

| Field | Value |
|-------|-------|
| **ID** | CICD-003 |
| **Category** | CI/CD |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | DOC-002 |
| **Affected Files** | `.github/workflows/` (new release workflow) |

**Description:** No release automation. Publishing to PyPI, creating GitHub releases, and tagging versions are all manual. The project already uses conventional commit prefixes suitable for auto-changelog generation.

**Acceptance Criteria:**

- Create `.github/workflows/release.yml` triggered on version tag push (`v*`)
- Generate changelog from conventional commits (git-cliff or python-semantic-release)
- Create GitHub Release with auto-generated notes
- Optionally publish to PyPI

---

### CICD-004: No coverage reporting in CI

| Field | Value |
|-------|-------|
| **ID** | CICD-004 |
| **Category** | CI/CD |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `.github/workflows/ci.yml`, `Makefile` |

**Description:** `pytest-cov` is installed but `make test` does not pass `--cov` flags. CI generates no coverage reports. The team can't see whether coverage is improving or regressing.

**Acceptance Criteria:**

- Add `--cov=pi_loop --cov=web_app --cov-report=term-missing` to the `test` target (or a separate `coverage` target)
- Add coverage step to CI `test` job
- Consider Codecov/Coveralls integration for PR coverage comments

---

### CICD-005: No security scanning in CI

| Field | Value |
|-------|-------|
| **ID** | CICD-005 |
| **Category** | CI/CD |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `.github/workflows/ci.yml` |

**Description:** No dependency vulnerability scanning (pip-audit, safety, or Snyk) and no SAST (bandit, semgrep) in CI. Known-vulnerability dependencies may go unnoticed.

**Acceptance Criteria:**

- Add `pip-audit` step to CI lint job (or separate security job)
- Add `bandit` scan for Python source (configure in pyproject.toml)
- Consider GitHub's built-in Dependabot alerts for advisory monitoring

---

## 🧹 9. Code Cleanup

### CLEAN-001: Vanilla JS SPA with global mutable state, no module system

| Field | Value |
|-------|-------|
| **ID** | CLEAN-001 |
| **Category** | Code Cleanup |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 4 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/static/app.js` (~1119 lines) |

**Description:** The SPA has 15+ global state variables and 40+ top-level function declarations in the global namespace. State is mutated freely. Data flow is implicit. Error handling is inconsistent (empty catch blocks). No ES modules, classes, or state management patterns.

**Acceptance Criteria:**

- Split into ES modules (native, no build step): `state.js`, `api.js`, `sse.js`, `ui/dashboard.js`, `ui/config.js`, `ui/logs.js`, `utils.js`
- Centralized state store with getters/setters and pub/sub change notifications
- Consistent error handling: all `catch` blocks at least `console.error`
- All SSE reconnect logic in `sse.js` with exponential backoff

---

### CLEAN-002: 30+ magic numbers scattered across codebase

| Field | Value |
|-------|-------|
| **ID** | CLEAN-002 |
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | 2 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/config.py`, `pi_loop/error_recovery.py`, `web_app/rate_limiter.py`, `web_app/server.py` |

**Description:** 30+ magic numeric literals — timeout values (2000ms, 500ms, 120s, 300s, 600s), limits (10240, 500, 120), rates (0.01, 0.6), retry counts, buffer sizes — scattered across modules with no named constants or documentation.

**Acceptance Criteria:**

- Define all magic numbers as named constants
- Group in a `DEFAULT_CONFIG` dict or per-module `_constants` section
- Add doc-comments explaining why each value was chosen
- `DEFAULT_MAX_TURNS = 2000`, `DEFAULT_COOLDOWN = 5`, `DEFAULT_RATE_LIMIT_CAP = 120`, etc.

---

### CLEAN-003: CSS hardcoded colors and duplicated light/dark themes

| Field | Value |
|-------|-------|
| **ID** | CLEAN-003 |
| **Category** | Code Cleanup |
| **Priority** | 🟡 Medium |
| **Impact** | 2 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/static/style.css` |

**Description:** `style.css` has ~50+ hardcoded `#rrggbb` hex values and ~800 lines of duplicated CSS for light vs dark themes (two nearly identical blocks with different color values).

**Acceptance Criteria:**

- Migrate all colors to CSS custom properties: `--color-bg`, `--color-text`, `--color-accent`, etc.
- Use a single theme block with `[data-theme="dark"]` and `[data-theme="light"]` property overrides
- No duplicated selector blocks between themes

---

### CLEAN-004: Dead CSS toggle switch class

| Field | Value |
|-------|-------|
| **ID** | CLEAN-004 |
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/static/style.css` |

**Description:** The `.toggle` and `.toggle-slider` CSS classes in `style.css` appear to be dead code — no corresponding toggle switches exist in `index.html` or `app.js`.

**Acceptance Criteria:**

- Audit usage of `.toggle` and `.toggle-slider`
- Remove if unused
- Or repurpose if planned for future use

---

### CLEAN-005: Empty catch blocks in `app.js`

| Field | Value |
|-------|-------|
| **ID** | CLEAN-005 |
| **Category** | Code Cleanup |
| **Priority** | 🟡 Medium |
| **Impact** | 2 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/static/app.js` |

**Description:** 5+ empty `catch` blocks in `app.js` swallow exceptions silently. Frontend errors are invisible to developers, making debugging production issues nearly impossible.

**Acceptance Criteria:**

- Add `console.error(e)` to all empty catch blocks
- Consider adding an error display for the user (toast notification for non-critical errors)
- Ensure no sensitive data is logged in error messages

---

### CLEAN-006: Import style inconsistencies and unused imports

| Field | Value |
|-------|-------|
| **ID** | CLEAN-006 |
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/cli.py`, `pi_loop/loop.py`, multiple files |

**Description:** Several modules have unused imports, deferred imports inside function bodies, or mixed import styles (stdlib imports scattered among third-party imports). While ruff catches the most egregious issues, stylistic inconsistencies remain.

**Acceptance Criteria:**

- Remove all unused imports flagged by `ruff check --select=F401`
- Move deferred imports to module top (already done for `urllib.request` — check for others)
- Standardize on: stdlib → third-party → local (PEP 8)

---

## ✨ 10. Features & Ideas

### FEAT-001: Docker image and Docker Compose for containerized deployment

| Field | Value |
|-------|-------|
| **ID** | FEAT-001 |
| **Category** | Features & Ideas |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | Root (new `Dockerfile`, `docker-compose.yml`) |

**Description:** Docker/Compose files exist in stale worktrees but were never ported to main. Containerized deployment provides reproducible environments, easy server deployment, volume mounts, and port mapping.

**Acceptance Criteria:**

- `Dockerfile`: `python:3.12-slim`, install pi + pi-loop, health check endpoint
- `docker-compose.yml`: web service with port mapping (default: 8000), volume mounts for data
- `.dockerignore`: exclude venv, caches, git, tests
- Multi-stage build to minimize image size

---

### FEAT-002: Prometheus metrics endpoint

| Field | Value |
|-------|-------|
| **ID** | FEAT-002 |
| **Category** | Features & Ideas |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `web_app/server.py` (new `/metrics` endpoint) |

**Description:** No Prometheus metrics endpoint exists. Key operational metrics should be exposed for Grafana dashboards and operational monitoring.

**Acceptance Criteria:**

- `pi_loop_iterations_total` (counter by status: success, error, timeout, convergence)
- `pi_loop_iteration_duration_seconds` (histogram, p50/p95/p99)
- `pi_loop_active_workers` (gauge)
- `pi_loop_errors_total` (counter by error type)
- `pi_loop_cooldown_seconds` (gauge)
- Grafana dashboard JSON template in `monitoring/` directory

---

### FEAT-003: Structured logging replacing `print()`

| Field | Value |
|-------|-------|
| **ID** | FEAT-003 |
| **Category** | Features & Ideas |
| **Priority** | 🟠 High |
| **Impact** | 4 / 5 |
| **Effort** | 3 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/error_recovery.py`, `pi_loop/git_utils.py`, `pi_loop/heartbeat.py`, `pi_loop/preflight.py`, `web_app/server.py` |

**Description:** The daemon uses `print()` for all logging — no structured/JSON logging, no log levels (DEBUG, INFO, WARNING, ERROR), no correlation IDs. Tracing a single iteration through `_execute_task` → error recovery requires manually correlating timestamps. The web server uses uvicorn's default access log but application logs are unstructured.

**Acceptance Criteria:**

- Replace all `print()` calls with `structlog` or stdlib `logging` with JSON formatter
- Log levels: DEBUG for diagnostics, INFO for normal ops, WARNING for recoverable issues, ERROR for failures
- Correlation/loop/iteration IDs in every log line
- JSON output for log aggregators (Loki, ELK, Datadog)
- Dual output: human-readable terminal + JSON file
- Structured fields: `event`, `iteration`, `duration_ms`, `error_type`, `worker_id`, etc.

---

### FEAT-004: Health check endpoint for Docker and monitoring

| Field | Value |
|-------|-------|
| **ID** | FEAT-004 |
| **Category** | Features & Ideas |
| **Priority** | 🟡 Medium |
| **Impact** | 3 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | FEAT-001 |
| **Affected Files** | `web_app/server.py` (new `/health` endpoint) |

**Description:** There is no dedicated `/health` endpoint. Docker orchestration and load balancers need liveness/readiness probes. The existing `/api/status` returns 200 even when the daemon is in a broken state.

**Acceptance Criteria:**

- **Liveness**: Server responding (implicitly true)
- **Readiness**: Daemon process alive, config readable, `pi` binary available
- **Dependency check**: JSON ledger readable
- Return 200 with `{"status": "healthy"}` or 503 with `{"status": "unhealthy", "checks": {...}}`
- Docker `HEALTHCHECK` directive using this endpoint

---

### FEAT-005: Webhook notification system

| Field | Value |
|-------|-------|
| **ID** | FEAT-005 |
| **Category** | Features & Ideas |
| **Priority** | 🔵 Low |
| **Impact** | 2 / 5 |
| **Effort** | 2 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/config.py` |

**Description:** The daemon has basic HTTP callback support (`--on-success`, `--on-error`, `--http-callback`) but no structured webhook system with templating, retries, or signing. External integrations rely on parsing the JSON ledger directly.

**Acceptance Criteria:**

- Define webhook payload schema (iteration result, status, timestamps, error details)
- Add configurable webhook URL per event type (iteration_complete, error, convergence, start, stop)
- HMAC signing for payload authenticity (partially done — verify)
- Retry with exponential backoff on failure
- Template support for custom payload format

---

## ⬆️ 11. Dependencies

### DEP-001: Pin `fastapi` minimum to a known-good version

| Field | Value |
|-------|-------|
| **ID** | DEP-001 |
| **Category** | Dependencies |
| **Priority** | 🔵 Low |
| **Impact** | 2 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `pyproject.toml`, `requirements.txt` |

**Description:** `pyproject.toml` specifies `fastapi>=0.100.0`, but the project uses features from `0.138.x`. A fresh install could resolve `0.100.0` which is 38 versions behind and may lack required APIs.

**Acceptance Criteria:**

- Update minimum: `fastapi>=0.115.0` (conservative) or `fastapi>=0.138.0` (current)
- Regenerate lockfiles: `pip-compile --upgrade`

---

### DEP-002: Review and update all dependency pins quarterly

| Field | Value |
|-------|-------|
| **ID** | DEP-002 |
| **Category** | Dependencies |
| **Priority** | 🔵 Low |
| **Impact** | 1 / 5 |
| **Effort** | 1 / 5 |
| **Status** | ⏳ Pending |
| **Dependencies** | None |
| **Affected Files** | `requirements.txt`, `requirements-dev.txt` |

**Description:** No regular dependency review cycle. Dependencies can accumulate CVEs, and dev deps (ruff, mypy, pytest) may lag behind their latest versions.

**Acceptance Criteria:**

- Establish quarterly `pip-compile --upgrade` cycle
- Document in CONTRIBUTING.md
- Dependabot already configured for weekly updates (verify it covers dev deps)

---

## ✅ Appendix A: Completed Items

These items have been resolved in prior iterations and are tracked here for historical reference.

| ID | Title | Category | Fixed When |
|----|-------|----------|-----------|
| — | Subprocess zombie leak — `proc.kill()` + `proc.wait()` | Bug | v14.x (iter #4) |
| — | Race: `loop_manager.stop()` concurrent with `_monitor_process` | Bug | v14.x (iter #4) |
| — | TOCTOU race in `loop_manager.stop()` PID capture | Bug | v14.x (iter #4) |
| — | Race: status='running' set before monitors created | Bug | v14.x (iter #4) |
| — | Race: `_read_stream` AttributeError on stale `self._process` | Bug | v14.x (iter #4) |
| — | Lost error recovery mitigations via `state.get()` → setdefault | Bug | v14.x (iter #4) |
| — | Duplicated shutdown logic — extracted `_shutdown()` | Tech Debt | v14.x (iter #4) |
| — | Silent exception swallowing (bare `except: pass`) | Tech Debt | v14.x (iter #4) |
| — | Circular import `cli.py` ↔ `help_topics.py` — extracted `parser.py` | Architecture | v14.x (iter #4) |
| — | API-key auth middleware on `/api/*` endpoints (SEC-001) | Security | v14.35+ |
| — | CORS tightened to localhost-only by default | Security | v14.35+ |
| — | `validate_config()` wired into `save_config_api()` returns 422 | Security | v14.x (iter #3) |
| — | Config file corruption — graceful degradation, `.corrupt` backup | Reliability | v14.x (iter #3) |
| — | Empty SSE heartbeat listener removed | Cleanup | v14.x |
| — | Duplicate `worker_term` initialization in `_parse_daemon_line` | Cleanup | v14.x |
| — | `import urllib.request` moved from function body to top | Cleanup | v14.x |
| — | Redundant `write_status_file()` calls removed | Performance | v14.39.0 |
| — | Heartbeat log levels downgraded (ERROR→WARNING/DEBUG) | Cleanup | v14.x |
| — | 481 unit tests across 22 test files (was 0) | Testing | v14.x (iter #4) |
| — | CI pipeline with test + lint (Python 3.10–3.13 matrix) | CI/CD | v14.x (iter #4) |
| — | Mypy type-checking target and CI step | CI/CD | v14.x (iter #4) |
| — | Pre-commit hook rewritten (ruff check + format) | CI/CD | v14.x (iter #4) |
| — | Dev/test dependencies defined in pyproject.toml `[project.optional-dependencies]` | Packaging | v14.x (iter #4) |
| — | Dependabot config with grouped weekly updates | CI/CD | v14.x |
| — | Ruff ARG001 unused parameters fixed across codebase | Lint | v14.x |
| — | Mypy type errors fixed across 5 files | Type Check | v14.x |

---

## ❌ Appendix B: Won't Do / Investigated

| ID | Title | Reason |
|----|-------|--------|
| — | Module-level mutable state sync (`_shutdown_requested`) | **Investigated and dismissed.** `_shutdown_requested` uses `threading.Event()`, inherently thread-safe (`.set()`/`.is_set()` are atomic). No fix needed. The two copies (`loop.py` and `heartbeat.py`) are intentionally separate. |
| — | Replace `FileLock` with cross-platform alternative | Current `fcntl.flock` works on Linux/macOS. Cross-platform (Windows) support is out of scope for this project. |

---

## File-by-File Issue Density

| File | Lines | Active Issues | Top Issue |
|------|-------|---------------|-----------|
| `pi_loop/loop.py` | 816 | 7 (ARCH-001, ARCH-002, BUG-002, PERF-001, PERF-002, FEAT-005, FEAT-003) | ARCH-001: run_loop decomposition |
| `web_app/server.py` | 689 | 5 (BUG-005, TEST-004, DOC-001, SEC-001, FEAT-004) | TEST-004: low coverage |
| `web_app/static/app.js` | 1119 | 3 (CLEAN-001, CLEAN-005, PERF-003) | CLEAN-001: global mutable state |
| `web_app/static/style.css` | 1054 | 2 (CLEAN-003, CLEAN-004) | CLEAN-003: hardcoded colors |
| `web_app/loop_manager.py` | 533 | 1 (BUG-003) | BUG-003: colorized output |
| `web_app/config_manager.py` | 371 | 1 (ARCH-004) | ARCH-004: quadruple config |
| `pi_loop/cli.py` | 281 | 1 (TEST-003) | TEST-003: low coverage |
| `pi_loop/status.py` | 75 | 1 (TEST-003) | TEST-003: low coverage |
| `pi_loop/config_file.py` | 69 | 1 (BUG-001) | BUG-001: corruption silence |
| `pi_loop/system_utils.py` | 88 | 1 (BUG-004) | BUG-004: first CPU 0% |
| `pi_loop/file_watcher.py` | 66 | 1 (TEST-002) | TEST-002: zero coverage |
| `pi_loop/file_utils.py` | 287 | 1 (SEC-002) | SEC-002: path sanitization |
| `pi_loop/config.py` | 439 | 2 (ARCH-002, ARCH-004) | ARCH-002: config/state separation |
| `pi_loop/error_recovery.py` | 181 | 1 (ARCH-005) | ARCH-005: transactional rollback |
| `pi_loop/heartbeat.py` | 221 | 1 (ARCH-003) | ARCH-003: dependency injection |
| `pyproject.toml` | — | 1 (DEP-001) | DEP-001: fastapi minimum |
| `Makefile` | — | 2 (CICD-001, TOOL-003) | CICD-001: mypy swallowed |
| `README.md` | — | 1 (DOC-003) | DOC-003: version mismatch |
| `.github/workflows/ci.yml` | — | 4 (CICD-001, CICD-002, CICD-004, CICD-005) | CICD-001: mypy CI gap |
| `.gitignore` | — | 1 (TOOL-002) | TOOL-002: .coverage not ignored |

---

## Priority Heatmap

```
Priority   Count  Categories
────────────────────────────────────────────────────────────
Critical    3    Architecture (ARCH-001, ARCH-005) ...
High        9    Architecture (ARCH-002, ARCH-003),
                 Testing (TEST-001, TEST-003),
                 CI/CD (CICD-001),
                 Security (SEC-001),
                 Features (FEAT-003)
Medium      17   Bugs (BUG-001, BUG-002, BUG-003, BUG-005),
                 Testing (TEST-002, TEST-004, TEST-005),
                 Performance (PERF-001, PERF-003),
                 Security (SEC-002),
                 Documentation (DOC-001),
                 CI/CD (CICD-002, CICD-004, CICD-005),
                 Cleanup (CLEAN-001, CLEAN-003, CLEAN-005),
                 Features (FEAT-001, FEAT-002, FEAT-004)
Low         13   Bugs (BUG-004),
                 Performance (PERF-002),
                 Documentation (DOC-002, DOC-003),
                 CI/CD (CICD-003),
                 Cleanup (CLEAN-002, CLEAN-004, CLEAN-006),
                 Tooling (TOOL-002, TOOL-003, TOOL-004, TOOL-005, TOOL-006),
                 Dependencies (DEP-001, DEP-002),
                 Features (FEAT-005)
```

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-30 | AI Staff Engineer | Consolidation of ENGINEERING_BACKLOG.md and BACKLOG.md into single authoritative document. 42 active items across 11 categories. Executive Summary, Quick Wins, and Action Plan added. |
