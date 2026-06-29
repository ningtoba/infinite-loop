# pi-loop Engineering Backlog

> Generated from comprehensive code analysis covering all subsystems: loop engine, CLI, web app, frontend, tooling, testing, and CI/CD.
> Generated: 2026-06-29

---

## Quick Reference

| Severity | Count |
|----------|-------|
| 🔴 **Critical** | 2 |
| 🟠 **High** | 11 |
| 🟡 **Medium** | 19 |
| 🔵 **Low** | 13 |
| ✅ **Completed** | 24 |
| **Total Active** | **45** |

| Category | Count |
|----------|-------|
| Bugs | 0 |
| Technical Debt | 10 |
| Refactoring Opportunities | 2 |
| Performance Improvements | 2 |
| Security Improvements | 2 |
| Missing Tests | 1 |
| Missing Documentation | 2 |
| CI/CD Improvements | 7 |
| Developer Experience (DX) | 5 |
| Code Cleanup | 8 |
| Dependency Updates | 2 |
| Architecture Improvements | 5 |
| Scalability Improvements | 1 |
| Reliability Improvements | 4 |
| Automation Opportunities | 1 |
| Feature Ideas | 4 |

---

## Status Legend

| Status | Meaning |
|--------|---------|
| ✅ Done | Completed and verified |
| 🔄 In Progress | Currently being worked on |
| ⏳ Pending | Not yet started |
| ❌ Blocked | Blocked by another item |

---

## Bugs

### BUG-001 — Subprocess leak on timeout (zombie processes) ✅

| Field | Value |
|-------|-------|
| **Category** | Bugs |
| **Priority** | 🔴 Critical |
| **Impact** | System resources leak, PID exhaustion |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** `_execute_task` in `loop.py` calls `proc.wait(timeout=session_timeout)` inside a retry loop. When the timeout fires (`subprocess.TimeoutExpired`), the process was never terminated or killed before the next retry or final return. This accumulates zombie/orphan `pi` subprocesses consuming PID slots and system resources.

**Fix applied:** Added `proc.kill()` + `proc.wait(timeout=5)` in the `subprocess.TimeoutExpired` and generic `Exception` handlers, with `if proc is not None` guard. Also fixed adjacent bare `try: except: pass` anti-patterns.

**Affected files:**

- `pi_loop/loop.py`

### BUG-002 — Race condition in loop_manager.stop() concurrent with_monitor_process ✅

| Field | Value |
|-------|-------|
| **Category** | Bugs |
| **Priority** | 🟠 High |
| **Impact** | Can cause AttributeError crash during shutdown |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** Both `stop()` and `_monitor_process()` write `self._process = None` with no coordination — can cause `AttributeError` when one reads `self._process` after the other sets it to `None`. A lock or atomic check-then-set pattern is needed.

**Fix applied:** Added `self._lock` and wrapped `self._process = None` writes in both `stop()` and `_monitor_process()` with the lock. Completed 2026-06-29.

**Affected files:**

- `web_app/loop_manager.py`

### BUG-003 — TOCTOU race in loop_manager.stop() ✅

| Field | Value |
|-------|-------|
| **Category** | Bugs |
| **Priority** | 🟠 High |
| **Impact** | Can crash or send SIGTERM/SIGKILL to wrong process group |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** `os.getpgid(pid)` can raise `ProcessLookupError` if the process exits between the check and the read. The PGID could also be reassigned to another process between `getpgid` and `killpg`. Need to wrap with proper error handling and validate PID/PGID ownership.

**Fix applied:** Added `os.kill(pid, 0)` ownership check before `getpgid()` + `killpg()`, wrapped in try/except with `ProcessLookupError` handling. Completed 2026-06-29.

**Affected files:**

- `web_app/loop_manager.py`

### BUG-004 — Race: status='running' set before stream readers/monitor created ✅

| Field | Value |
|-------|-------|
| **Category** | Bugs |
| **Priority** | 🟠 High |
| **Impact** | Orphaned subprocess if daemon crashes in ~1ms window |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** The status is set to `"running"` before `_read_stream` and `_monitor_process` coroutines are created. If the daemon crashes in this window, the manager believes it's running but no monitors are attached. Should set status after monitors are confirmed active.

**Fix applied:** Moved `self._status = "running"` after `asyncio.create_task(...)` calls. Completed 2026-06-29.

**Affected files:**

- `web_app/loop_manager.py`

### BUG-005 — Race: _read_stream can AttributeError on self._process ✅

| Field | Value |
|-------|-------|
| **Category** | Bugs |
| **Priority** | 🟠 High |
| **Impact** | Stream reader crashes mid-read, losing log output |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** Stale `self._process` reference used in `_read_stream` while-loop condition — concurrent `stop()` can set it to `None` mid-iteration. Should capture process reference locally.

**Fix applied:** Captured `local_proc = self._process` at `_read_stream` start and used `local_proc` in while-loop condition. Completed 2026-06-29.

**Affected files:**

- `web_app/loop_manager.py` (line ~243)

---

## Technical Debt

### TECHDEBT-001 — Extreme parameter bloat in run_loop()

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟠 High |
| **Impact** | Nearly impossible to test, reason about, or document |
| **Effort** | Large |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `run_loop()` accepts 60+ parameters covering config, paths, notifications, git, convergence, cooldown, error handling, and more. Makes the function nearly impossible to test, reason about, or document. The function signature spans ~60 lines.

**Affected files:**

- `pi_loop/loop.py` (line ~143 signature)

### TECHDEBT-002 — Duplicated shutdown logic (DRY violation) ✅

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟠 High |
| **Impact** | Inconsistent shutdown behavior; copy-paste bugs |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ✅ Completed |

**Reasoning:** The shutdown sequence (write state, write status, print summary, return) was duplicated in 6 places throughout `run_loop()`.

**Fix:** Extracted `_shutdown(state, iteration_count, status_file, stop_reason, *, goal, git, workers, last_error, write_status_file_entry)` helper. Replaced all 6 call sites with single-line calls. Preserved behavioral nuance: goals-exhausted skips `_write_status_file` (was already different). Net: -134 lines. Completed 2026-06-29.

**Affected files:**

- `pi_loop/loop.py` (added `_shutdown()` helper, replaced 6 duplicated call sites within `run_loop()`)

### TECHDEBT-003 — Dead code: validate_json_output() / validate_config()

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟡 Medium |
| **Impact** | Unmaintained code that will rot; false sense of coverage |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `validate_json_output()` in `validation.py` and `validate_config()` in `config_manager.py` are defined but never imported or called anywhere. `validate_config()` in particular should be wired into the `/api/config` save endpoint (see SECURITY-001).

**Affected files:**

- `pi_loop/validation.py`
- `web_app/config_manager.py`

### TECHDEBT-004 — Silent exception swallowing (bare except: pass) ✅

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟡 Medium |
| **Impact** | Bugs silently masked; debugging impossible |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** Multiple bare `except Exception: pass` clauses throughout `loop.py` (line ~340 and several others). These swallow all exceptions silently, making debugging near-impossible when something goes wrong. Each should at minimum log the exception.

**Fix applied:** Replaced `with suppress(Exception):` with typed `try/except` blocks that log specific failures in loop.py (HTML dashboard, HTTP callbacks, on-error commands, desktop notifications). Fixed server.py `_status_poller` bare `except: pass` to log via `manager._add_log`. Completed 2026-06-29.

**Affected files:**

- `pi_loop/loop.py`
- `web_app/server.py`

### TECHDEBT-005 — config_file.py and env_utils.py overlap

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟡 Medium |
| **Impact** | Confusion about which defaults take effect |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Both `config_file.py` and `env_utils.py` define overlapping DEFAULTS dicts with same env var keys but different values. Example: `config_file.py` sets `INFINITE_LOOP_SESSION_TIMEOUT=120` while `env_utils.py` sets the same var to `300`. The config layer has no single source of truth.

**Affected files:**

- `pi_loop/config_file.py`
- `pi_loop/env_utils.py` (lines 229–259)

### TECHDEBT-006 — CSS theme definitions duplicated

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🔵 Low |
| **Impact** | CSS maintenance burden; 2KB+ of duplicated tokens |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `[data-theme='dark']` block repeats identical values from `:root`. The dark theme `:root` already sets these values; `[data-theme='dark']` duplicates them entirely. Only `[data-theme='light']` needs explicit overrides.

**Affected files:**

- `web_app/static/style.css` (line ~3 vs line ~350)

### TECHDEBT-007 — Hardcoded colors not using CSS variables

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🔵 Low |
| **Impact** | Theme changes break specific UI elements |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Several inline colors and specific CSS selectors use hardcoded hex values instead of CSS custom properties. These break when the user toggles themes.

**Affected files:**

- `web_app/static/style.css`
- `web_app/static/index.html`

### TECHDEBT-008 — CSS .system-grid duplicates .status-grid

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🔵 Low |
| **Impact** | CSS bloat; confusing naming |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `.system-grid` in CSS is a duplicate of `.status-grid` with identical layout properties. Should use a shared class.

**Affected files:**

- `web_app/static/style.css` (line ~345)

### TECHDEBT-009 — config_file.py port default mismatch with server.py

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🔵 Low |
| **Impact** | Confusion on first run; port already in use errors |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `config_file.py` defaults to `WEB_PORT=8000` while `server.py` uses 8090 as the fallback port. These divergent defaults create confusion when users configure via config file vs CLI.

**Affected files:**

- `pi_loop/config_file.py` (8000)
- `web_app/server.py` (8090)

### TECHDEBT-010 — config_file.py vs config_manager.py defaults divergence

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟡 Medium |
| **Impact** | Inconsistent behavior based on which config layer loads first |
| **Effort** | Medium |
| **Dependencies** | TECHDEBT-005 |
| **Status** | ⏳ Pending |

**Reasoning:** `config_file.py` DEFAULTS set `SESSION_TIMEOUT=120` while `config_manager.py` CONFIG_DEFAULTS set `SESSION_TIMEOUT=600`. These overlapping default sets diverge and cause unpredictable behavior depending on which is loaded first.

**Affected files:**

- `pi_loop/config_file.py`
- `web_app/config_manager.py`

### TECHDEBT-011 — Retry loop output capture is lossy ✅

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🟡 Medium |
| **Impact** | Lost progress data on retry; unreliable error reporting |
| **Effort** | Small |
| **Dependencies** | BUG-001 |
| **Status** | ✅ Done |

**Reasoning:** Retry mechanism only captures output on final retry; stale data from previous attempts persists and may contaminate the final state. Should accumulate output across retries or use a fresh capture on each attempt.

**Fix applied:** Added per-attempt buffers (`attempt_final_text_parts`, `attempt_text_buf`, `attempt_raw_lines`) reset each retry. Accumulated all failure outputs in `all_attempts_output` across attempts. Completed 2026-06-29.

**Affected files:**

- `pi_loop/loop.py`

### TECHDEBT-012 — SSE fixed 5s reconnect interval

| Field | Value |
|-------|-------|
| **Category** | Technical Debt |
| **Priority** | 🔵 Low |
| **Impact** | Thundering herd on server restart; slow reconnect |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** SSE reconnection uses a hardcoded 5s interval. Should use exponential backoff (1s, 2s, 4s, 8s, capped at 30s) to reduce server load during outages.

**Affected files:**

- `web_app/static/app.js` (lines ~110–114)

---

## Refactoring Opportunities

### REFACTOR-001 — Monolithic run_loop() violates Single Responsibility Principle

| Field | Value |
|-------|-------|
| **Category** | Refactoring Opportunities |
| **Priority** | 🟠 High |
| **Impact** | ~200+ lines mixing shutdown, git, notifications, error recovery, cooldown, dashboard HTML, HTTP callbacks, and goal cycling |
| **Effort** | X-Large |
| **Dependencies** | TECHDEBT-001, TECHDEBT-002 |
| **Status** | ⏳ Pending |

**Reasoning:** `run_loop()` is ~200+ lines mixing shutdown handling, git state capture, notification dispatch, error recovery adaptation, cooldown logic, dashboard HTML generation, HTTP callbacks, and goal cycling. Each responsibility should be extracted into its own function or class.

**Affected files:**

- `pi_loop/loop.py` (lines ~310–510+)

### REFACTOR-002 — Extract shutdown to _shutdown(reason) helper ✅

| Field | Value |
|-------|-------|
| **Category** | Refactoring Opportunities |
| **Priority** | 🟡 Medium |
| **Impact** | Cleaner main loop; single point of change for shutdown behavior |
| **Effort** | Medium |
| **Dependencies** | TECHDEBT-002 |
| **Status** | ✅ Completed |

**Reasoning:** Extracted as part of TECHDEBT-002. Completed 2026-06-29.

**Affected files:**

- `pi_loop/loop.py`

### REFACTOR-003 — Config object for run_loop parameters

| Field | Value |
|-------|-------|
| **Category** | Refactoring Opportunities |
| **Priority** | 🔵 Low |
| **Impact** | Makes the function testable and documentable |
| **Effort** | Large |
| **Dependencies** | TECHDEBT-001 |
| **Status** | ⏳ Pending |

**Reasoning:** Replace the 60+ individual parameters to `run_loop()` with a single typed config dataclass/dict. This makes the function testable, documentable, and extensible without signature changes.

**Affected files:**

- `pi_loop/config.py`
- `pi_loop/loop.py`

---

## Performance Improvements

### PERF-001 — Blocking synchronous I/O in async endpoints ✅

| Field | Value |
|-------|-------|
| **Category** | Performance Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | Blocks the entire async event loop; degrades all connections |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** Blocking `open()`/`read()` in async `index()` endpoint blocks the entire async event loop. Should use `aiofiles` or `asyncio.to_thread()` for file I/O.

**Fix applied:** Replaced blocking `open(index_path).read()` with `asyncio.to_thread()`. Completed 2026-06-29.

**Affected files:**

- `web_app/server.py`

### PERF-002 — Unbounded limit/offset parameters ✅

| Field | Value |
|-------|-------|
| **Category** | Performance Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Can return huge payloads; potential OOM on large ledgers |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** `/api/iterations` accepts unbounded `limit` and `offset` parameters. A malicious or misconfigured client could request 10M iterations and cause OOM.

**Fix applied:** Capped `limit` to [1, 500] and clamped `offset` to non-negative. Completed 2026-06-29.

**Affected files:**

- `web_app/server.py`

### PERF-003 — SSE _status_poller runs with zero clients ✅

| Field | Value |
|-------|-------|
| **Category** | Performance Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Wastes CPU with polling work when no one is watching |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** The `_status_poller()` runs every 2s regardless of whether any SSE clients are connected. Should early-return when `_sse_clients` is empty.

**Fix applied:** Added `asyncio.sleep(1)` and tracking state reset when `_sse_clients` is empty. Completed 2026-06-29.

**Affected files:**

- `web_app/server.py`

### PERF-004 — SSE redundant re-fetches on every update

| Field | Value |
|-------|-------|
| **Category** | Performance Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Extra HTTP round-trips; redundant data transfer |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** SSE pushes cause the frontend to re-fetch full status/iteration data even when only a small delta changed. Should use incremental updates or push the actual data in the SSE event payload.

**Affected files:**

- `web_app/static/app.js`

### PERF-005 — O(n) DOM removal in appendLog

| Field | Value |
|-------|-------|
| **Category** | Performance Improvements |
| **Priority** | 🔵 Low |
| **Impact** | UI lag with 500+ log entries |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `appendLog` uses `while (container.children.length > 500)` which triggers O(n) reflow on every removal. Should cap the array or use a linked-list-based log buffer.

**Affected files:**

- `web_app/static/app.js` (line ~350)

---

## Security Improvements

### SECURITY-001 — No schema validation on save_config_api ✅

| Field | Value |
|-------|-------|
| **Category** | Security Improvements |
| **Priority** | 🔴 Critical |
| **Impact** | Arbitrary JSON accepted without validation; can corrupt config |
| **Effort** | Medium |
| **Dependencies** | TECHDEBT-003 |
| **Status** | ✅ Done |

**Reasoning:** `save_config_api()` accepts any JSON dict without validation. `validate_config()` exists but is never called (dead code). A malformed request can write corrupt data to the config file, causing crashes on next `load_config()`.

**Fix applied:** Imported and called `validate_config()` in `save_config_api()` before persisting. Returns HTTP 422 on validation failure. Resolves TECHDEBT-003 for `validate_config()`. Completed 2026-06-29.

**Affected files:**

- `web_app/server.py`
- `web_app/config_manager.py`

### SECURITY-002 — Missing request timeouts, rate limiting, and auth

| Field | Value |
|-------|-------|
| **Category** | Security Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | All endpoints open to abuse; no auth, no rate limits |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** All endpoints lack authentication, rate limiting, request timeouts, and request IDs. The `/api/loop/start` endpoint can be triggered by anyone, which could spawn arbitrary subprocesses.

**Affected files:**

- `web_app/server.py` (all endpoints)

### SECURITY-003 — CORS allow_origins=['*']

| Field | Value |
|-------|-------|
| **Category** | Security Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Any website can make API requests to the daemon |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** CORS is configured with `allow_origins=["*"]` which permits any origin to make API calls. For a local daemon tool this is acceptable for dev, but should be configurable for production deployments.

**Affected files:**

- `web_app/server.py` (lines 39–42)

---

## Missing Tests

### TEST-001 — Zero test coverage (resolved) ✅

| Field | Value |
|-------|-------|
| **Category** | Missing Tests |
| **Priority** | 🔴 Critical |
| **Impact** | Every refactor is blind; no safety net |
| **Effort** | Large |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** The project originally had no test files. Created 7 test modules with 156 unit tests covering stats, validation, error classification, color utils, CLI parsing, config constants, and fixtures. Added pytest and pytest-asyncio as optional test dependencies.

**New test files:**

- `tests/__init__.py`
- `tests/conftest.py`
- `tests/test_cli.py`
- `tests/test_color_utils.py`
- `tests/test_config.py`
- `tests/test_error_utils.py`
- `tests/test_stats.py`
- `tests/test_validation.py`

### TEST-002 — Critical untested modules

| Field | Value |
|-------|-------|
| **Category** | Missing Tests |
| **Priority** | 🟠 High |
| **Impact** | Core loop, web server, and subprocess manager have zero tests |
| **Effort** | X-Large |
| **Dependencies** | REFACTOR-003 |
| **Status** | ⏳ Pending |

**Reasoning:** Current 156 tests cover only: CLI parsing, validation, stats, error_utils, color_utils, config constants. Missing test coverage for:

- `pi_loop/loop.py` (core loop execution engine)
- `web_app/loop_manager.py` (subprocess lifecycle)
- `web_app/server.py` (API endpoints, SSE)
- `pi_loop/error_recovery.py` (adaptive error mitigation)
- `pi_loop/functions.py` (goal cycling, startup banner)
- `pi_loop/git_utils.py` (git state capture)
- `pi_loop/heartbeat.py` (session self-healing)
- `pi_loop/config_manager.py` (config schema, validation)
- `pi_loop/file_utils.py` (file locking, ledger I/O, sentinel)
- `pi_loop/state.py` (ledger load/create/recovery)

**Affected files:**

- `pi_loop/loop.py`
- `web_app/loop_manager.py`
- `web_app/server.py`
- `pi_loop/error_recovery.py`
- `pi_loop/functions.py`
- `pi_loop/git_utils.py`
- `pi_loop/heartbeat.py`
- `web_app/config_manager.py`
- `pi_loop/file_utils.py`
- `pi_loop/state.py`

---

## Missing Documentation

### DOC-001 — No API documentation for web endpoints

| Field | Value |
|-------|-------|
| **Category** | Missing Documentation |
| **Priority** | 🟡 Medium |
| **Impact** | Third-party integrations must reverse-engineer the API |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The FastAPI app has no auto-generated docs or OpenAPI spec beyond the minimal title/description. All endpoints need proper response models, docstrings, and OpenAPI metadata. FastAPI generates OpenAPI automatically if type annotations and docstrings are added.

**Affected files:**

- `web_app/server.py`

### DOC-002 — No aria-live regions on dynamic content

| Field | Value |
|-------|-------|
| **Category** | Missing Documentation |
| **Priority** | 🟡 Medium |
| **Impact** | Screen readers cannot announce dynamic updates |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Dynamic containers (log entries, status updates, iteration tables) lack `aria-live` attributes for screen readers. The app is inaccessible to visually impaired users.

**Affected files:**

- `web_app/static/index.html`
- `web_app/static/app.js`

---

## CI/CD Improvements

### CICD-001 — CI pipeline references non-existent make targets ✅

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🟠 High |
| **Impact** | CI would fail on push |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** CI originally ran `make test` and `make check` but neither target exists in Makefile. **Fixed:** `make lint-all` and `python -m pytest tests/ -v` now exist in CI.

**Affected files:**

- `.github/workflows/ci.yml`, `Makefile`

### CICD-002 — Pre-commit hook disabled (exit 0) ✅

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🟠 High |
| **Impact** | Zero pre-commit enforcement; easy to commit broken code |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** `.githooks/pre-commit` now runs `ruff check` + `ruff format --check` on staged Python files. Note: `.githooks/` is a custom hooks directory; users must run `git config core.hooksPath .githooks` to activate it.

**Affected files:**

- `.githooks/pre-commit`

### CICD-003 — Missing dev/test dependencies in pyproject.toml ✅

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | CI install fails with `".[dev]"` |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** No `[project.optional-dependencies] dev` section originally existed. **Fixed:** `test` and `dev` optional dependencies defined.

**Affected files:**

- `pyproject.toml`

### CICD-004 — No Python version matrix in CI ✅

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Python 3.12/3.13 compatibility issues undetected |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** CI originally tested only a single Python version. **Fixed:** CI now has a 3.10–3.13 test matrix.

**Affected files:**

- `.github/workflows/ci.yml`

### CICD-005 — Add mypy type-checking to CI pipeline

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🟠 High |
| **Impact** | Type errors (None-safety, type mismatches) slip through to production |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** The CI pipeline runs ruff (lint + format) and pytest, but had no type-checking step. **Fixed:** mypy config in `pyproject.toml`, `make mypy` target, and CI step now exist. Current output has warnings (2>/dev/null suppresses) that should be addressed.

**Affected files:**

- `.github/workflows/ci.yml`
- `Makefile`
- `pyproject.toml`

### CICD-006 — No Dependabot/Renovate configuration ✅

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | No automated security updates for dependencies |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** No automated dependency update configuration existed. Dependencies (FastAPI, uvicorn, pytest, ruff) weren't getting automatic PRs for security updates.

**Fix applied:** Created `.github/dependabot.yml` with weekly pip updates (patch/minor grouped, major ignored), weekly GitHub Actions updates, labeled and scoped for clean changelogs.

**Affected files:**

- `.github/dependabot.yml` (new file)

### CICD-007 — No pi binary availability check in CI

| Field | Value |
|-------|-------|
| **Category** | CI/CD Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | A `pi` API change could break the daemon without CI catching it |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The CI pipeline doesn't verify that `pi` (the external CLI used by the daemon) is available. A `pi` API change could break the daemon without CI catching it. Should add a smoke-test step that installs `pi` and runs `pi-loop --help` or a dry-run validation.

**Affected files:**

- `.github/workflows/ci.yml`

---

## Developer Experience (DX) Improvements

### DX-001 — No ruff / mypy config in pyproject.toml ✅

| Field | Value |
|-------|-------|
| **Category** | Developer Experience (DX) |
| **Priority** | 🟡 Medium |
| **Impact** | Inconsistent linting; unused args not flagged |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** No tool config for ruff or mypy in `pyproject.toml`. **Fixed:** Added `[tool.ruff]` and `[tool.mypy]` sections with project-specific rules, including `ARG` check for unused function arguments.

**Affected files:**

- `pyproject.toml`

### DX-002 — make test re-installs dependencies every run

| Field | Value |
|-------|-------|
| **Category** | Developer Experience (DX) |
| **Priority** | 🔵 Low |
| **Impact** | Wastes 2-3 seconds per local test run |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The `Makefile` test target runs `pip install -e ".[test]"` before `python -m pytest`. The `install-dev` target already installs test deps. Remove the pip install line from the test target.

**Affected files:**

- `Makefile` (test target)

### DX-003 — Server auto-reload mode forces full pip install

| Field | Value |
|-------|-------|
| **Category** | Developer Experience (DX) |
| **Priority** | 🔵 Low |
| **Impact** | Slow development iteration cycle |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Both `web` and `web-dev` Makefile targets run `pip install -e .` before starting the server. Once the package is installed, this is unnecessary overhead. Should check if package is already installed before re-installing.

**Affected files:**

- `Makefile` (web, web-dev targets)

### DX-004 — Global namespace pollution in app.js

| Field | Value |
|-------|-------|
| **Category** | Developer Experience (DX) |
| **Priority** | 🟡 Medium |
| **Impact** | Impossible to test; hard to reason about state |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** 40+ top-level function declarations and 15+ global state variables in `app.js`. Should be organized into modules/classes with explicit state management.

**Affected files:**

- `web_app/static/app.js` (entire file)

### DX-005 — Inline onclick handlers in HTML

| Field | Value |
|-------|-------|
| **Category** | Developer Experience (DX) |
| **Priority** | 🟡 Medium |
| **Impact** | Tight coupling between HTML and JS; impossible to CSP |
| **Effort** | Medium |
| **Dependencies** | DX-004 |
| **Status** | ⏳ Pending |

**Reasoning:** 14+ `onclick` attributes in `index.html` couple UI to global function names. Prevents Content Security Policy `script-src` hardening and makes testing difficult.

**Affected files:**

- `web_app/static/index.html`

---

## Code Cleanup

### CLEANUP-001 — Duplicated content_block_stop handler in _execute_task

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🟡 Medium |
| **Impact** | Double-processing of tool results in terminal output |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The `_execute_task` function in `loop.py` has TWO identical blocks handling `content_block_stop` events (lines ~191-209 and ~210-227). Both check if `delta.type == "tool_result"` and render it via `_term()`. This wastes CPU cycles and double-displays tool results.

**Affected files:**

- `pi_loop/loop.py` (lines ~191–227)

### CLEANUP-001 — Duplicated content_block_stop handler in _execute_task ✅

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🟡 Medium |
| **Impact** | Double-processing of tool results in terminal output |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** The `_execute_task` function in `loop.py` had TWO identical blocks handling `content_block_stop` events. The first (incorrectly placed before `text_delta` handling) rendered tool results twice.

**Fix applied:** Removed the first duplicate handler. Completed 2026-06-29.

**Affected files:**

- `pi_loop/loop.py`

### CLEANUP-002 — Duplicate worker_term append logic in loop_manager.py

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🟡 Medium |
| **Impact** | Terminal lines appear twice — once with prefix, once without |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `LoopManager._parse_daemon_line()` has two separate code paths that append to `self._worker_term[wid]` — a generic `TERM` regex fallthrough and an explicit `TERM` handler. The generic path leaves the `[TERM (worker #N)]` prefix in the content; the explicit one strips it. Result: duplicate terminal lines.

**Affected files:**

- `web_app/loop_manager.py` (lines 169–175 and 200–205)

### CLEANUP-003 — import urllib.request inside function body

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | Minor performance overhead on every iteration |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `import urllib.request` is placed inside the function body of `run_loop()` (line ~308) rather than at the top of the module. Should be a top-level import.

**Affected files:**

- `pi_loop/loop.py` (line ~308)

### CLEANUP-004 — Hardcoded 'worker #1' string ✅

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | Multiple workers all show as '#1' in terminal output |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** The string `"worker #1"` was hardcoded in `_execute_task` print statements. When `--workers > 1` is used, all worker terminal output showed as `worker #1`.

**Fix applied:** Added `worker_id: int = 1` parameter to `_execute_task()` and replaced `"worker #1"` with `f"worker #{worker_id}"`. Default 1 preserves single-worker behavior.

**Affected files:**

- `pi_loop/loop.py`

### CLEANUP-005 — Unused _lastWorkerLogCounts

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | Dead code; maintenance burden |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The global variable `_lastWorkerLogCounts` in `app.js` is defined but never read or written in any function.

**Affected files:**

- `web_app/static/app.js` (line ~286)

### CLEANUP-006 — Empty catch blocks swallow errors silently (JS)

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🟡 Medium |
| **Impact** | Errors silently hidden; debugging impossible |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** 5+ empty `catch` blocks in `app.js` (lines 68–70, 255–257, 279–281, 499–506, 544–548). These silently swallow all errors, making debugging near-impossible.

**Affected files:**

- `web_app/static/app.js` (multiple locations)

### CLEANUP-007 — Empty SSE heartbeat listener

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | No-op code; negligible |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The SSE `heartbeat` event listener in `app.js` is defined but empty (no-op). Should either be removed or used for connection health tracking.

**Affected files:**

- `web_app/static/app.js` (line ~106)

### CLEANUP-008 — Emoji icons without aria-hidden

| Field | Value |
|-------|-------|
| **Category** | Code Cleanup |
| **Priority** | 🔵 Low |
| **Impact** | Screen readers announce emoji descriptions |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Emoji icons used for navigation iconography lack `aria-hidden="true"` attributes, causing screen readers to announce emoji descriptions like "black medium square" instead of treating them as decorative.

**Affected files:**

- `web_app/static/index.html`

---

## Dependency Updates

### DEP-001 — Add pyproject.toml [tool.ruff.lint] section ✅

| Field | Value |
|-------|-------|
| **Category** | Dependency Updates |
| **Priority** | 🟡 Medium |
| **Impact** | Linter uses generic defaults; may miss project issues |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** `pyproject.toml` lacked `[tool.ruff.lint]` section. **Fixed:** Added project-specific rule selections (E, F, W, I, N, UP, B, SIM, ARG, RUF100) with E501 ignored for 120-char lines.

**Affected files:**

- `pyproject.toml`

### DEP-002 — FastAPI/uvicorn version pinning

| Field | Value |
|-------|-------|
| **Category** | Dependency Updates |
| **Priority** | 🔵 Low |
| **Impact** | Potential breaking changes from `>=` range |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Dependencies use `>=` ranges (e.g., `fastapi>=0.100.0`). A major FastAPI or uvicorn release could introduce breaking changes. Should pin to known-good versions with a range strategy (e.g., `>=0.100.0,<1.0.0`).

**Affected files:**

- `pyproject.toml`

---

## Architecture Improvements

### ARCH-001 — Dead / broken _evolve_goal feature ✅

| Field | Value |
|-------|-------|
| **Category** | Architecture Improvements |
| **Priority** | 🟠 High |
| **Impact** | Dead code with no effect; misleading user-facing flag |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** `_evolve_goal()` writes `state['evolved_goal']` but `run_loop()` never reads it back — the evolved goal is computed but never applied to the next iteration.

**Fix applied:** Added `_extract_next_goal()` helper that parses pi output for `NEXT_GOAL:` marker. Updated the evolve block to call `_evolve_goal()` with actual output from the last iteration.

**Affected files:**

- `pi_loop/loop.py` (line ~438)

### ARCH-002 — Circular import: cli.py ↔ help_topics.py

| Field | Value |
|-------|-------|
| **Category** | Architecture Improvements |
| **Priority** | 🟠 High |
| **Impact** | Import-time crash if import order changes |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Module-level `from .cli import _create_parser` in `help_topics.py` creates a circular import cycle with `cli.py` importing from `help_topics.py`. Currently works due to import ordering, but fragile.

**Affected files:**

- `pi_loop/help_topics.py`
- `pi_loop/cli.py`

### ARCH-003 — No max-runtime guard in main loop body

| Field | Value |
|-------|-------|
| **Category** | Architecture Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | A stuck iteration hangs the daemon indefinitely |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** No heartbeat/runtime guard in the main `while True` loop. If `_execute_task` hangs (e.g., subprocess deadlock), the entire daemon freezes with no recovery mechanism.

**Affected files:**

- `pi_loop/loop.py` (line ~310)

### ARCH-004 — pause()/resume() race with stale status

| Field | Value |
|-------|-------|
| **Category** | Architecture Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | Status desync between UI and daemon |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** pause/resume set status in the web manager without confirming the daemon process is actually alive. A dead-but-not-cleaned-up daemon shows as "paused" in the UI.

**Affected files:**

- `web_app/loop_manager.py` (lines 179–202)

### ARCH-005 — Docker detection via /.dockerenv is fragile

| Field | Value |
|-------|-------|
| **Category** | Architecture Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Docker-related code paths may not trigger in all container runtimes (Podman, etc.) |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The only Docker-aware code is in `web_app/loop_manager.py` checking `/.dockerenv`. This doesn't work for Podman or container environments that don't create this file. Should add a centralized `is_docker()` utility.

**Affected files:**

- `web_app/loop_manager.py`
- (proposed) `pi_loop/system_utils.py`

---

## Scalability Improvements

### SCALE-001 — Worker terminal state lost on navigation ✅

| Field | Value |
|-------|-------|
| **Category** | Scalability Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Terminal state not preserved across tab switches |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** Worker terminal state lost on navigation. **Fix applied:** Capped `_worker_term[wid]` at 2000 lines in storage. Fixed `KeyError` on first TERM line per worker (initialize before append). Replaced stale `term_total` metric with `term_content_hash` in SSE status poller.

**Affected files:**

- `web_app/loop_manager.py`
- `web_app/server.py`
- `pi_loop/loop.py`

---

## Reliability Improvements

### RELIABILITY-001 — Config file corruption causes HTTP 500

| Field | Value |
|-------|-------|
| **Category** | Reliability Improvements |
| **Priority** | 🟡 Medium |
| **Impact** | Entire status/dashboard breaks if config file is corrupt |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** No try/except around `load_config()` in `_read_stored()` in `config_manager.py`. If the config JSON file is corrupt (e.g., partial write), the entire config endpoint returns HTTP 500.

**Affected files:**

- `web_app/config_manager.py` (lines 248–271)

### RELIABILITY-002 — Wrong HTTP status codes for logical errors

| Field | Value |
|-------|-------|
| **Category** | Reliability Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Clients can't distinguish error types |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Config save and loop control endpoints return HTTP 200 with `{"success": false, "error": "..."}` for logical errors (e.g., "Loop is not running") instead of proper 4xx status codes.

**Affected files:**

- `web_app/server.py` (lines 89–118)

### RELIABILITY-003 — _get_memory_info() path construction bug

| Field | Value |
|-------|-------|
| **Category** | Reliability Improvements |
| **Priority** | 🔵 Low |
| **Impact** | Memory info returns zeros on custom DATA_DIR |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The `_get_memory_info()` function constructs a path using `os.path.join(DATA_DIR, "..", "proc", "meminfo")`. When DATA_DIR is not "/tmp", this constructs an invalid path. Should always read from `/proc/meminfo` directly.

**Affected files:**

- `web_app/server.py` (`_get_memory_info()`)

### RELIABILITY-004 — _get_cpu_percent() first-read returns 0% always ✅

| Field | Value |
|-------|-------|
| **Category** | Reliability Improvements |
| **Priority** | 🔵 Low |
| **Impact** | "0%" CPU shown on initial page load until next poll cycle |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** The first call to `_get_cpu_percent()` always returned 0.0 because no delta for comparison existed.

**Fix applied:** Pre-warm CPU deltas at module import time by reading `/proc/stat` twice with a 1-sample loop. The first call now returns a real value.

**Affected files:**

- `web_app/server.py`

---

## Automation Opportunities

### AUTO-001 — LoopManager log file handle management

| Field | Value |
|-------|-------|
| **Category** | Automation Opportunities |
| **Priority** | 🔵 Low |
| **Impact** | File handle leak if close() not called |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The log file handle opened in `LoopManager._add_log()` is only closed by explicit `close()` or `__del__()`. A context manager or atexit-registered cleanup would ensure the handle is always released.

**Affected files:**

- `web_app/loop_manager.py`

---

## Feature Ideas

### FEATURE-001 — CI pipeline with test + lint + type-check ✅

| Field | Value |
|-------|-------|
| **Category** | Feature Ideas |
| **Priority** | 🟡 Medium |
| **Impact** | No automated quality gates on pull requests |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** CI pipeline now runs: ruff lint, ruff format check, mypy type checking, and pytest across Python 3.10–3.13. **Implemented:** See CICD-001 through CICD-005.

**Affected files:**

- `.github/workflows/ci.yml`
- `Makefile`
- `pyproject.toml`
- `.githooks/pre-commit`

### FEATURE-002 — Event-loop-safe async I/O in web endpoints

| Field | Value |
|-------|-------|
| **Category** | Feature Ideas |
| **Priority** | 🟡 Medium |
| **Impact** | Blocks event loop; degrades all connections |
| **Effort** | Medium |
| **Dependencies** | PERF-001 |
| **Status** | ⏳ Pending |

**Reasoning:** Multiple web endpoints use blocking I/O (`open()`, `read()`, `json.load()`) in async context. Should use `aiofiles`, `asyncio.to_thread()`, or non-blocking alternatives.

**Affected files:**

- `web_app/server.py`
- `web_app/config_manager.py`

### FEATURE-003 — Exponential backoff for SSE reconnection

| Field | Value |
|-------|-------|
| **Category** | Feature Ideas |
| **Priority** | 🔵 Low |
| **Impact** | Server load spikes on restart; slow recovery |
| **Effort** | Small |
| **Dependencies** | TECHDEBT-012 |
| **Status** | ⏳ Pending |

**Reasoning:** Replace fixed 5s SSE reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s) with jitter to reduce server load during outages.

**Affected files:**

- `web_app/static/app.js` (lines 110–114)

### FEATURE-004 — Heartbeat guard in main loop body

| Field | Value |
|-------|-------|
| **Category** | Feature Ideas |
| **Priority** | 🟡 Medium |
| **Impact** | A stuck iteration hangs the daemon indefinitely with no recovery |
| **Effort** | Medium |
| **Dependencies** | ARCH-003 |
| **Status** | ⏳ Pending |

**Reasoning:** Add a heartbeat/runtime guard to the main `while True` loop in `run_loop()` so that if an iteration exceeds `max_iteration_wall_time`, the daemon can self-recover by killing the stuck subprocess and logging the failure.

**Affected files:**

- `pi_loop/loop.py` (line ~310)

---

## Appendix: Status Summary by File

| File | Active Issues |
|------|--------------|
| `pi_loop/loop.py` | 9 (BUG-001✅, TECHDEBT-001, TECHDEBT-002✅, TECHDEBT-004✅, TECHDEBT-011✅, REFACTOR-001, REFACTOR-002✅, REFACTOR-003, CLEANUP-001✅, CLEANUP-003, CLEANUP-004✅, ARCH-001✅, ARCH-003, FEATURE-004, SCALE-001✅) |
| `web_app/loop_manager.py` | 7 (BUG-002, BUG-003, BUG-004, BUG-005, CLEANUP-002, ARCH-004, AUTO-001, SCALE-001✅) |
| `web_app/server.py` | 7 (PERF-001✅, PERF-003✅, SECURITY-001✅, SECURITY-002, SECURITY-003, RELIABILITY-002, RELIABILITY-003, RELIABILITY-004✅, FEATURE-002) |
| `web_app/config_manager.py` | 3 (TECHDEBT-003, RELIABILITY-001, SECURITY-001) |
| `web_app/static/app.js` | 6 (DX-004, PERF-004, PERF-005, CLEANUP-005, CLEANUP-006, CLEANUP-007, TECHDEBT-012, FEATURE-003) |
| `web_app/static/index.html` | 3 (DX-005, DOC-002, CLEANUP-008) |
| `web_app/static/style.css` | 3 (TECHDEBT-006, TECHDEBT-007, TECHDEBT-008) |
| `pi_loop/cli.py` | 1 (ARCH-002) |
| `pi_loop/help_topics.py` | 1 (ARCH-002) |
| `pi_loop/config.py` | 2 (REFACTOR-003, TECHDEBT-005) |
| `pi_loop/config_file.py` | 2 (TECHDEBT-005, TECHDEBT-009, TECHDEBT-010) |
| `pi_loop/env_utils.py` | 1 (TECHDEBT-005) |
| `pi_loop/validation.py` | 1 (TECHDEBT-003) |
| `pi_loop/system_utils.py` | 0 (candidate for ARCH-005) |
| `.github/workflows/ci.yml` | 2 (CICD-001✅, CICD-004✅, CICD-005✅, CICD-006✅, CICD-007) |
| `Makefile` | 2 (DX-002, DX-003) |
| `pyproject.toml` | 2 (DEP-001✅, DEP-002) |
| `tests/` | 1 (TEST-002) |

---

## Appendix: Completed Items

| ID | Title | Category | Completed |
|----|-------|----------|-----------|
| BUG-001 | Subprocess leak on timeout (zombie processes) | Bugs | ✅ |
| TEST-001 | Zero test coverage (156 tests created) | Missing Tests | ✅ |
| ARCH-001 | Dead / broken _evolve_goal feature | Architecture | ✅ |
| CICD-001 | CI pipeline references non-existent make targets | CI/CD | ✅ |
| CICD-002 | Pre-commit hook disabled (exit 0) | CI/CD | ✅ |
| CICD-003 | Missing dev/test dependencies | CI/CD | ✅ |
| CICD-004 | No Python version matrix in CI | CI/CD | ✅ |
| CICD-005 | Add mypy type-checking to CI pipeline | CI/CD | ✅ |
| CICD-006 | Dependabot configuration | CI/CD | ✅ |
| DX-001 | No ruff / mypy config in pyproject.toml | DX | ✅ |
| DEP-001 | Add pyproject.toml [tool.ruff.lint] section | Dependencies | ✅ |
| SCALE-001 | Worker terminal state lost on navigation | Scalability | ✅ |
| FEATURE-001 | CI pipeline with test + lint + type-check | Features | ✅ |
| CLEANUP-001 | Duplicated content_block_stop handler | Code Cleanup | ✅ |
| CLEANUP-004 | Hardcoded 'worker #1' string | Code Cleanup | ✅ |
| RELIABILITY-004 | CPU first-read returns 0% | Reliability | ✅ |

---

## Top 10 Highest Priority Items

| Rank | ID | Title | Priority | Effort | Category |
|------|----|-------|----------|--------|----------|
| 1 | **SECURITY-001** | No schema validation on save_config_api | 🔴 Critical | Medium | Security |
| 2 | **BUG-002** | Race condition in loop_manager.stop() | 🟠 High | Medium | Bugs |
| 3 | **BUG-003** | TOCTOU race in loop_manager.stop() | 🟠 High | Medium | Bugs |
| 4 | **BUG-004** | Race: status='running' set before monitors created | 🟠 High | Medium | Bugs |
| 5 | **BUG-005** | Race: _read_stream can AttributeError on self._process | 🟠 High | Small | Bugs |
| 6 | **TECHDEBT-001** | Extreme parameter bloat in run_loop() | 🟠 High | Large | Tech Debt |
| 7 | **TECHDEBT-002** | Duplicated shutdown logic (DRY violation) | 🟠 High | Medium | Tech Debt |
| 8 | **ARCH-002** | Circular import: cli.py ↔ help_topics.py | 🟠 High | Medium | Architecture |
| 9 | **REFACTOR-001** | Monolithic run_loop() violates SRP | 🟠 High | X-Large | Refactoring |
| 10 | **TEST-002** | Critical untested modules | 🟠 High | X-Large | Missing Tests |
