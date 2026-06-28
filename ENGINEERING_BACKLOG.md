# pi-loop Engineering Backlog

> Generated from deep code analysis — covers all subsystems: loop engine, CLI, web app, frontend, tooling, testing, and CI/CD.

---

## Quick Reference

| Severity | Count |
|----------|-------|
| 🔴 Critical | 1 |
| 🟠 High | 14 |
| 🟡 Medium | 18 |
| 🔵 Low | 15 |
| **Total** | **49** |

| Category | Count |
|----------|-------|
| testing | 2 |
| CI/CD | 3 |
| code-quality | 11 |
| documentation | 1 |
| performance | 3 |
| security | 2 |
| dev-experience | 3 |
| architecture | 8 |
| features | 6 |
| technical-debt | 10 |

---

## Backlog Items

### 🔴 BL-001 — Subprocess leak on timeout (zombie processes) ✅

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | critical |
| **Impact** | 10 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | **completed** |

**Description:** `_execute_task` in `loop.py` calls `proc.wait(timeout=session_timeout)` inside a retry loop. When the timeout fires (`subprocess.TimeoutExpired`), the process is never terminated or killed before the next retry or final return. This can accumulate zombie/orphan `pi` subprocesses that consume PID slots and system resources.

**Fix:** Added `proc.kill()` + `proc.wait(timeout=5)` in the `subprocess.TimeoutExpired` and generic `Exception` handlers, with `if proc is not None` guard. Also fixed adjacent bare `try: ... except: pass` anti-patterns.

**Affected files:**

- `pi_loop/loop.py`

### 🔴 BL-002 — Zero test coverage

| Field | Value |
|-------|-------|
| **Category** | testing |
| **Priority** | critical |
| **Impact** | 9 |
| **Effort** | 8 |
| **Dependencies** | BL-003, BL-005 |
| **Status** | pending |

**Description:** No test files exist anywhere in the project — zero unit tests, integration tests, or end-to-end tests. The `pyproject.toml` has no test framework dependency. The CI pipeline references `make test` which doesn't exist. Refactoring is high-risk without a test safety net.

**Affected files:**

- Entire project (~6661 lines of Python)

### 🟠 BL-003 — Extreme parameter bloat in run_loop()

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | high |
| **Impact** | 8 |
| **Effort** | 6 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** `run_loop()` accepts 60+ parameters covering config, paths, notifications, git, convergence, cooldown, error handling, and more. Makes the function nearly impossible to test, reason about, or document.

**Affected files:**

- `pi_loop/loop.py` (line ~143 signature)

### 🟠 BL-004 — Duplicated shutdown logic (DRY violation)

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | high |
| **Impact** | 7 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** The shutdown sequence is duplicated in ~5 places throughout `run_loop()`. Violates DRY and risks inconsistency.

**Affected files:**

- `pi_loop/loop.py` (lines ~352, plus 4+ other locations)

### 🟠 BL-005 — Dead / broken _evolve_goal feature

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | high |
| **Impact** | 6 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** `_evolve_goal()` writes `state['evolved_goal']` but `run_loop()` never reads it back — the evolved goal is computed but never applied.

**Affected files:**

- `pi_loop/loop.py` (line ~438)

### 🟠 BL-006 — Race condition in loop_manager.stop() concurrent with_monitor_process

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | high |
| **Impact** | 8 |
| **Effort** | 4 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** Both `stop()` and `_monitor_process()` write `self._process = None` with no coordination — can cause `AttributeError`.

**Affected files:**

- `web_app/loop_manager.py` (lines 141–172, 262–275)

### 🟠 BL-007 — No schema validation on save_config_api

| Field | Value |
|-------|-------|
| **Category** | security |
| **Priority** | high |
| **Impact** | 7 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** `save_config_api()` accepts any JSON dict without validation. `validate_config()` exists but is never called (dead code).

**Affected files:**

- `web_app/server.py` (lines 85–90)
- `web_app/config_manager.py`

### 🟠 BL-008 — Circular import: cli.py ↔ help_topics.py

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | high |
| **Impact** | 7 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** Module-level `from .cli import _create_parser` in `help_topics.py` creates a circular import cycle.

**Affected files:**

- `pi_loop/help_topics.py`
- `pi_loop/cli.py`

### 🟠 BL-009 — Python 3.10 f-string escape bug (zsh completion) ✅

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | high |
| **Impact** | 6 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | **completed** |

**Description:** Backslash escapes inside f-string expression parts break on Python <3.12.

**Fix:** Extracted the joined flag string into a local variable computed with `chr(92)` + `chr(10)` to avoid backslash-in-expression syntax errors on Python <3.12.

**Affected files:**

- `pi_loop/cli.py` (line ~808)

### 🟠 BL-010 — CI pipeline references non-existent make targets

| Field | Value |
|-------|-------|
| **Category** | CI/CD |
| **Priority** | high |
| **Impact** | 8 |
| **Effort** | 2 |
| **Dependencies** | BL-002, BL-030 |
| **Status** | pending |

**Description:** CI runs `make test` and `make check` but neither target exists in Makefile. CI also installs `".[dev]"` with no dev dependencies defined.

**Affected files:**

- `.github/workflows/ci.yml`, `Makefile`, `pyproject.toml`

### 🟠 BL-011 — Pre-commit hook disabled (exit 0)

| Field | Value |
|-------|-------|
| **Category** | CI/CD |
| **Priority** | high |
| **Impact** | 7 |
| **Effort** | 1 |
| **Dependencies** | BL-030 |
| **Status** | pending |

**Description:** `.githooks/pre-commit` just does `exit 0`.

**Affected files:**

- `.githooks/pre-commit`

### 🟠 BL-012 — Monolithic run_loop() violates SRP

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | high |
| **Impact** | 7 |
| **Effort** | 7 |
| **Dependencies** | BL-003, BL-004 |
| **Status** | pending |

**Description:** ~200+ lines mixing shutdown, git, notifications, error recovery, cooldown, dashboard HTML, HTTP callbacks, and goal cycling.

**Affected files:**

- `pi_loop/loop.py` (lines ~310–510+)

### 🟠 BL-013 — TOCTOU race in loop_manager.stop()

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | high |
| **Impact** | 7 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** `os.getpgid(pid)` can raise `ProcessLookupError`; PGID could be reassigned between `getpgid` and `killpg`.

**Affected files:**

- `web_app/loop_manager.py` (lines 148–172)

### 🟠 BL-014 — Race: status='running' set before stream readers/monitor created

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | high |
| **Impact** | 6 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** If daemon crashes in the ~1ms window after status set but before readers spawn, orphans are left.

**Affected files:**

- `web_app/loop_manager.py` (lines 96–117)

### 🟠 BL-015 — Race: _read_stream can AttributeError on self._process

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | high |
| **Impact** | 6 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** Stale `self._process` reference used in `_read_stream` while-loop condition — concurrent `stop()` can set it to `None`.

**Affected files:**

- `web_app/loop_manager.py` (line ~243)

### 🟡 BL-016 — Silent exception swallowing (bare except: pass)

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | medium |
| **Impact** | 5 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** Multiple bare `except Exception: pass` clauses throughout `loop.py`.

**Affected files:**

- `pi_loop/loop.py` (line ~340 and several others)

### 🟡 BL-017 — Retry loop output capture is lossy

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | medium |
| **Impact** | 5 |
| **Effort** | 2 |
| **Dependencies** | BL-001 |
| **Status** | pending |

**Description:** Only captures output on final retry; stale data persists across attempts.

**Affected files:**

- `pi_loop/loop.py` (lines ~56–80)

### 🟡 BL-018 — No max-runtime guard in main loop body

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | medium |
| **Impact** | 5 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** No heartbeat/runtime guard in the main `while True` — a stuck iteration hangs the daemon indefinitely.

**Affected files:**

- `pi_loop/loop.py` (line ~310)

### 🟡 BL-019 — config_file.py and env_utils.py overlap

| Field | Value |
|-------|-------|
| **Category** | technical-debt |
| **Priority** | medium |
| **Impact** | 4 |
| **Effort** | 4 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** Both modules define overlapping DEFAULTS dicts with same env var keys. Config layer is redundant.

**Affected files:**

- `pi_loop/config_file.py`, `pi_loop/env_utils.py` (lines 229–259)

### 🟡 BL-020 — Dead code: validate_json_output() / validate_config()

| Field | Value |
|-------|-------|
| **Category** | technical-debt |
| **Priority** | medium |
| **Impact** | 3 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** Functions defined but never imported or called.

**Affected files:**

- `pi_loop/validation.py`, `web_app/config_manager.py`

### 🟡 BL-021 — Blocking synchronous I/O in async endpoints

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | medium |
| **Impact** | 5 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** Blocking `open()`/`read()` in async `index()` endpoint.

**Affected files:**

- `web_app/server.py` (lines 49–53)

### 🟡 BL-022 — Config file corruption causes HTTP 500

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | medium |
| **Impact** | 5 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** No try/except around `load_config()` in `_read_stored()`.

**Affected files:**

- `web_app/config_manager.py` (lines 248–271)

### 🟡 BL-023 — Missing request timeouts, rate limiting, and auth

| Field | Value |
|-------|-------|
| **Category** | security |
| **Priority** | medium |
| **Impact** | 6 |
| **Effort** | 5 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** All endpoints lack auth, rate limiting, timeouts, and request IDs.

**Affected files:**

- `web_app/server.py` (all endpoints)

### 🟡 BL-024 — Global namespace pollution in app.js

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | medium |
| **Impact** | 4 |
| **Effort** | 4 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** 40+ top-level function declarations and 15+ global state variables.

**Affected files:**

- `web_app/static/app.js` (entire file)

### 🟡 BL-025 — Inline onclick handlers in HTML

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | medium |
| **Impact** | 4 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** 14+ onclick attributes coupling to global function names.

**Affected files:**

- `web_app/static/index.html`

### 🟡 BL-026 — Empty catch blocks swallow errors silently (JS)

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | medium |
| **Impact** | 5 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** 5+ empty catch blocks in app.js.

**Affected files:**

- `web_app/static/app.js` (lines 68–70, 255–257, 279–281, 499–506, 544–548)

### 🟡 BL-027 — CSS theme definitions duplicated

| Field | Value |
|-------|-------|
| **Category** | technical-debt |
| **Priority** | medium |
| **Impact** | 3 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** `[data-theme='dark']` block repeats identical values from `:root`.

**Affected files:**

- `web_app/static/style.css` (line ~3 vs line ~350)

### 🟡 BL-028 — No aria-live regions on dynamic content

| Field | Value |
|-------|-------|
| **Category** | documentation |
| **Priority** | medium |
| **Impact** | 4 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** Dynamic containers lack aria-live attributes for screen readers.

**Affected files:**

- `web_app/static/index.html`, `web_app/static/app.js`

### 🟡 BL-029 — No ruff / mypy config in pyproject.toml

| Field | Value |
|-------|-------|
| **Category** | dev-experience |
| **Priority** | medium |
| **Impact** | 4 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** No tool config for ruff or mypy; 3 current lint errors.

**Affected files:**

- `pyproject.toml`

### 🟡 BL-030 — Missing dev/test dependencies in pyproject.toml

| Field | Value |
|-------|-------|
| **Category** | dev-experience |
| **Priority** | medium |
| **Impact** | 5 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** No `[project.optional-dependencies] dev` section.

**Affected files:**

- `pyproject.toml`, `.github/workflows/ci.yml`

### 🟡 BL-031 — pause()/resume() race with stale status

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | medium |
| **Impact** | 4 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Description:** pause/resume set status without confirming process is alive.

**Affected files:**

- `web_app/loop_manager.py` (lines 179–202)

### 🔵 BL-032 — import urllib.request inside function body

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `pi_loop/loop.py` (line ~308)

### 🔵 BL-033 — Hardcoded 'worker #1' string

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `pi_loop/loop.py` (line ~47)

### 🔵 BL-034 — SSE _status_poller runs with zero clients

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/server.py` (lines 278–308)

### 🔵 BL-035 — Wrong HTTP status codes for logical errors

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/server.py` (lines 89–118)

### 🔵 BL-036 — Unbounded limit/offset parameters

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | low |
| **Impact** | 3 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/server.py` (lines 134–152)

### 🔵 BL-037 — CORS allow_origins=['*']

| Field | Value |
|-------|-------|
| **Category** | security |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/server.py` (lines 39–42)

### 🔵 BL-038 — Hardcoded colors not using CSS variables

| Field | Value |
|-------|-------|
| **Category** | technical-debt |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/style.css`, `web_app/static/index.html`

### 🔵 BL-039 — SSE fixed 5s reconnect interval

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 2 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/app.js` (lines ~110–114)

### 🔵 BL-040 — Unused _lastWorkerLogCounts

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | low |
| **Impact** | 1 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/app.js` (line ~286)

### 🔵 BL-041 — Emoji icons without aria-hidden

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/index.html`

### 🔵 BL-042 — SSE redundant re-fetches on every update

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/app.js`

### 🔵 BL-043 — O(n) DOM removal in appendLog

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/app.js` (line ~350)

### 🔵 BL-044 — Worker terminal state lost on navigation

| Field | Value |
|-------|-------|
| **Category** | features |
| **Priority** | low |
| **Impact** | 2 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/app.js` (line ~470)

### 🔵 BL-045 — Empty SSE heartbeat listener

| Field | Value |
|-------|-------|
| **Category** | code-quality |
| **Priority** | low |
| **Impact** | 1 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/app.js` (line ~106)

### 🔵 BL-046 — CSS .system-grid duplicates .status-grid

| Field | Value |
|-------|-------|
| **Category** | technical-debt |
| **Priority** | low |
| **Impact** | 1 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/style.css` (line ~345)

### 🔵 BL-047 — No Python version matrix in CI

| Field | Value |
|-------|-------|
| **Category** | CI/CD |
| **Priority** | low |
| **Impact** | 3 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `.github/workflows/ci.yml`

### 🟡 BL-048 — Feature: Add heartbeat guard to main loop body

| Field | Value |
|-------|-------|
| **Category** | features |
| **Priority** | medium |
| **Impact** | 6 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `pi_loop/loop.py` (line ~310)

### 🟡 BL-049 — Feature: Extract shutdown to _shutdown(reason) helper

| Field | Value |
|-------|-------|
| **Category** | features |
| **Priority** | medium |
| **Impact** | 7 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `pi_loop/loop.py` (lines ~352 and 4+ other locations)

### 🔵 BL-050 — Feature: Config object for run_loop parameters

| Field | Value |
|-------|-------|
| **Category** | features |
| **Priority** | low |
| **Impact** | 8 |
| **Effort** | 6 |
| **Dependencies** | BL-003 |
| **Status** | pending |

**Affected files:**

- `pi_loop/config.py`, `pi_loop/loop.py`

### 🔵 BL-051 — Feature: Subprocess lifecycle with proper timeout cleanup

| Field | Value |
|-------|-------|
| **Category** | features |
| **Priority** | low |
| **Impact** | 9 |
| **Effort** | 3 |
| **Dependencies** | BL-001 |
| **Status** | pending |

**Affected files:**

- `pi_loop/loop.py` (lines 87–95)

### 🟡 BL-052 — Feature: CI pipeline with test + lint + type-check

| Field | Value |
|-------|-------|
| **Category** | features |
| **Priority** | medium |
| **Impact** | 7 |
| **Effort** | 4 |
| **Dependencies** | BL-002, BL-010, BL-030 |
| **Status** | pending |

**Affected files:**

- `.github/workflows/ci.yml`, `Makefile`, `pyproject.toml`, `.githooks/pre-commit`

### 🟡 BL-053 — Feature: Event-loop-safe async I/O in web endpoints

| Field | Value |
|-------|-------|
| **Category** | features |
| **Priority** | medium |
| **Impact** | 5 |
| **Effort** | 3 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/server.py`, `web_app/config_manager.py`

### 🔵 BL-054 — Feature: Exponential backoff for SSE reconnection

| Field | Value |
|-------|-------|
| **Category** | features |
| **Priority** | low |
| **Impact** | 3 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `web_app/static/app.js` (lines 110–114)

### 🔵 BL-055 — Feature: Fix _evolve_goal or remove it

| Field | Value |
|-------|-------|
| **Category** | features |
| **Priority** | low |
| **Impact** | 4 |
| **Effort** | 1 |
| **Dependencies** | none |
| **Status** | pending |

**Affected files:**

- `pi_loop/loop.py` (line ~438)

---

## Top Priority Item

**ID:** BL-001  
**Title:** Subprocess leak on timeout (zombie processes)  
**Priority:** critical  
**Impact:** 10  
**Effort:** 3  

**Why:** Zombie processes leak system resources and undermine trust in the daemon's core value proposition — running unattended. Fix is a focused low-effort change in one function.
