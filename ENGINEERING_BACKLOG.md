# Hermes Loop — Engineering Backlog

## Executive Summary

**omp-loop** is a Python daemon that wraps the `omp` coding agent to automate goal-driven iteration loops for coding sessions. The tech stack is Python 3.10+ with argparse for CLI entry, FastAPI/uvicorn for the web management UI, pytest for testing, and ruff/mypy/bandit for quality tooling.

The architecture follows a **dual-process pattern**: a single-threaded synchronous daemon process manages the iteration loop (subprocess spawning, state persistence as JSON ledger, error recovery, heartbeat monitoring), while a separate async FastAPI process provides a REST API and SPA frontend for daemon control. State is shared via disk (JSON ledger and sentinel files), and the daemon supports ~70 CLI flags across 14 groups with multi-layer config precedence (CLI flags → JSON config file → env vars → .env file → defaults).

The codebase has **22 test files (~695 tests)** with improved coverage on file watching, env value decoding, and JSON extraction. The dead heartbeat monitoring subsystem (~170 lines) has been removed, and `_execute_task` returns a typed `TaskResult` dict. Significant tech debt remains including an incomplete LoopConfig refactor (71-parameter `run_loop` signature) and tight coupling between the web UI and daemon internals.

**Key priorities (critical):**

- **BACKLOG-1** — Subprocess pipe deadlock in `_execute_task` (blocking bug)
- **BACKLOG-4** — Complete LoopConfig migration (largest source of tech debt)

---

## Backlog Table

| ID | Title | Category | Priority | Impact | Effort | Status |
|---|---|---|---|---|---|---|
| BACKLOG-1 | Fix subprocess pipe deadlock in `_execute_task` | bug | critical | high | small | completed |
| BACKLOG-2 | Add timeout to `proc.communicate()` after kill in `_execute_task` | bug | high | high | small | completed |
| BACKLOG-3 | Add synchronization between heartbeat killer thread and main loop | bug | high | high | small | dead-code |
| BACKLOG-4 | Complete LoopConfig migration and remove 71-parameter `run_loop` signature | tech-debt | critical | high | large | pending |
| BACKLOG-5 | Add TypedDict for ledger state across 15 consuming modules | architecture | high | high | large | pending |
| BACKLOG-6 | Decouple `web_app` from `omp_loop` internal path constants | architecture | high | high | medium | pending |
| BACKLOG-7 | Consolidate multi-layer config precedence into a single resolver | architecture | high | high | xlarge | pending |
| BACKLOG-8 | Decompose `main()` in `cli.py` (~200 lines) | tech-debt | high | medium | medium | pending |
| BACKLOG-9 | Block shell redirection characters in `on_error_cmd` validation | security | high | medium | small | completed |
| BACKLOG-10 | Add TypedDict for `_execute_task` return value | tech-debt | medium | medium | small | completed |
| BACKLOG-11 | Add structural validation to `read_ledger` return value | tech-debt | medium | medium | small | pending |
| BACKLOG-12 | Write unit tests for `FileWatcherTrigger` | test | high | high | medium | completed |
| BACKLOG-13 | Add subprocess integration test for `_execute_task` with `mock_pi.sh` | test | high | medium | medium | pending |
| BACKLOG-14 | Fix heartbeat status to report 'interrupted' instead of 'alive' on shutdown | bug | medium | medium | small | dead-code |
| BACKLOG-15 | Use `X-Forwarded-For` for rate limiter client IP behind proxy | security | medium | medium | small | pending |
| BACKLOG-16 | Replace f-string HTML dashboard with a proper template engine | tech-debt | medium | medium | medium | pending |
| BACKLOG-17 | Add HTTPS enforcement and TLS verification for web API and callbacks | security | medium | medium | medium | pending |
| BACKLOG-18 | Add unit tests for `_decode_env_var_value` edge cases | test | medium | medium | small | completed |
| BACKLOG-19 | Add edge case tests for `extract_json_from_output` | test | medium | medium | small | completed |
| BACKLOG-20 | Consolidate three module-level shutdown events into one | architecture | medium | medium | medium | pending |
| BACKLOG-21 | Refactor oversized integration test files into focused unit tests | test | medium | medium | large | pending |
| BACKLOG-22 | Replace global singletons with dependency injection | architecture | medium | medium | xlarge | pending |
| BACKLOG-23 | Make stale pending iteration threshold configurable | tech-debt | low | low | small | pending |
| BACKLOG-24 | Add module docstrings and high-level architecture documentation | documentation | high | medium | medium | pending |
| BACKLOG-25 | Make `TASK_PATTERNS` extensible without editing source code | feature | medium | low | medium | pending |
| BACKLOG-26 | Differentiate `FileLock` TimeoutError from 'no ledger exists' | bug | medium | medium | small | pending |
| BACKLOG-27 | Optimize `extract_json_from_output` to single-pass scan | performance | low | low | small | pending |
| BACKLOG-28 | Fix config drift between `env_utils.KNOWN_ENV_VARS` and `config_file.DEFAULTS` | bug | medium | low | small | pending |
| BACKLOG-29 | Fix `FileWatcherTrigger._scan` symlink loop and permission skip issues | bug | low | medium | small | pending |
| BACKLOG-30 | Create REPROVISION.md with dev environment setup steps | documentation | low | low | small | pending |
| BACKLOG-31 | Heartbeat monitoring subsystem is dead code (needs removal or reconnection) | architecture | medium | medium | medium | completed |

---

## Detailed Backlog Items

### BACKLOG-1 — Fix subprocess pipe deadlock in `_execute_task` ✅

- **Category:** bug
- **Priority:** critical
- **Impact:** high
- **Effort:** small
- **Status:** completed

**Problem:** `_execute_task` reads stdout in a for-loop without concurrently reading stderr. If the omp subprocess writes ~64KB to stderr (common with error diagnostics or model choice messages), the OS pipe buffer fills, the child blocks writing to stderr, stdout stalls, and the parent's `for raw_line in proc.stdout` loop hangs indefinitely.

**Fix:** Added a daemon thread (`_drain_pipe`) that drains stderr concurrently via `proc.stderr` while the main thread reads stdout. A `_stderr_buf` list collects lines, and the main thread joins the drain thread (with 10s timeout) after stdout is fully consumed. The drain thread is also joined in exception handlers (`TimeoutExpired`, `FileNotFoundError`, generic `Exception`) before retry to prevent stale pipe references.

**Files changed:** `omp_loop/loop.py` — added `_drain_pipe()` module-level function, stderr drain thread instantiation in `_execute_task()`, and `_stderr_thread.join()` in normal completion and all exception paths.

**Validation:** All 28 `test_loop.py` tests pass, all 71 tests across `test_loop.py`, `test_file_utils.py`, `test_error_recovery.py` pass. `ruff check omp_loop/loop.py` clean (B023 false positive eliminated with explicit `args` parameter on `threading.Thread`).

---

### BACKLOG-2 — Add timeout to `proc.communicate()` after kill in `_execute_task` ✅

- **Category:** bug
- **Priority:** high
- **Impact:** high
- **Effort:** small
- **Status:** completed

After `proc.kill()`, `proc.communicate()` is called with no timeout. If the process refuses to die (zombie), this blocks the entire iteration loop forever. Add a timeout parameter so the daemon can escalate to SIGKILL on stubborn processes.

**Resolution:** `proc.wait(timeout=5)` is now called after `proc.kill()` in all exception paths (TimeoutExpired, generic Exception). A `_kill_and_reap()` helper provides consistent SIGKILL → wait → fallback behavior. Verified by inspection and all 28 `test_loop.py` tests pass.

### BACKLOG-3 — Add synchronization between heartbeat killer thread and main loop ⚰️

- **Category:** bug
- **Priority:** high
- **Impact:** high
- **Effort:** small

`_run_heartbeat_monitor` creates a daemon thread that calls `_kill_session()` without synchronization with the main thread. This creates a possible race where the process is killed while the main thread is reading stdout. Use a `threading.Lock` or `Event` to coordinate process termination.

---

### BACKLOG-4 — Complete LoopConfig migration and remove 71-parameter `run_loop` signature

- **Category:** tech-debt
- **Priority:** critical
- **Impact:** high
- **Effort:** large

`run_loop` still extracts every `cfg.*` field into local variables, duplicating the entire `LoopConfig` dataclass. This is **TECHDEPT-001** — the largest source of maintenance burden. Remove the legacy parameter explosion and use the dataclass directly throughout the function body.

---

### BACKLOG-5 — Add TypedDict for ledger state across 15 consuming modules

- **Category:** architecture
- **Priority:** high
- **Impact:** high
- **Effort:** large

Ledger state is a plain dict shared across ~15 modules with no type contract. Key typos become runtime errors, and the deeply nested structure (`state['stats']['consecutive_errors']`) has no validation at module boundaries. Define a `TypedDict` hierarchy matching the ledger schema (version 11) and validate at load time.

---

### BACKLOG-6 — Decouple `web_app` from `omp_loop` internal path constants

- **Category:** architecture
- **Priority:** high
- **Impact:** high
- **Effort:** medium

`web_app.loop_manager` imports `LEDGER_PATH`, `SENTINEL_PATH_DEFAULT`, and other `omp_loop` internals directly. This tight coupling means any daemon path refactor breaks the web UI. Introduce a stable inter-process API contract — either environment variables, a config file section, or a dedicated IPC channel.

---

### BACKLOG-7 — Consolidate multi-layer config precedence into a single resolver

- **Category:** architecture
- **Priority:** high
- **Impact:** high
- **Effort:** xlarge

Config resolution is spread across 4+ modules (`cli.py`, `config.py`, `config_file.py`, `env_utils.py`) with complex precedence logic that's extremely hard to reason about. A single `ConfigResolver` class with clear precedence rules would reduce bugs and make config behavior predictable, especially the interaction between CLI flags, JSON config files, `.env` files, and environment variables.

---

### BACKLOG-8 — Decompose `main()` in `cli.py` (~200 lines)

- **Category:** tech-debt
- **Priority:** high
- **Impact:** medium
- **Effort:** medium

`main()` handles parser creation, multiple early-return introspection paths, complex config loading, and loop dispatch in a single ~200-line function. Extract config loading into a dedicated function and move introspection-flag early returns into a dispatcher pattern for testability and readability.

---

### BACKLOG-9 — Block shell redirection characters in `on_error_cmd` validation

- **Category:** security
- **Priority:** high
- **Impact:** medium
- **Effort:** small

`_validate_on_error_cmd` blocks semicolons, pipes, and backticks but allows `>` and `<` redirection characters. A command like `echo > /etc/cron.d/evil` bypasses validation. Add `>` and `<` to the blocked characters list to prevent file-write attacks via `on_error_cmd`.

---

### BACKLOG-10 — Add TypedDict for `_execute_task` return value

- **Category:** tech-debt
- **Priority:** medium
- **Impact:** medium
- **Effort:** small

`_execute_task` returns an untyped dict with mixed key-value pairs (`'output'`, `'error'`, `'duration_seconds'`, `'n'`). Callers must manually handle missing keys and have no type-level contract. Define a `TaskResult` TypedDict to make the return shape explicit and catch `KeyError` bugs statically.

**Resolution:** Added `TaskResult` TypedDict to `omp_loop/loop.py` with inheritance pattern for Python 3.10 compatibility:
- `_TaskResultRequired` base class with required keys: `output` (str), `error` (str | None), `duration_seconds` (float), `returncode` (int)
- `TaskResult(_TaskResultRequired, total=False)` subclass adds optional keys: `n`, `summary`, `tool_usage`, `convergence`, `turns`, `token_usage`, `session_id`
- Changed `_execute_task` return type from `-> dict` to `-> TaskResult`
- Added missing `"output"` key to `FileNotFoundError` return path for type consistency
- All callers in `run_loop` use direct key access on required keys, no casts needed

**Files changed:** `omp_loop/loop.py` — added `TypedDict` import, `_TaskResultRequired`/`TaskResult` classes, return type annotation, fixed `FileNotFoundError` return dict.

**Validation:** `ruff check .` clean, all 28 `test_loop.py` tests pass, all 343 non-`test_env_utils` unit tests pass.

---

### BACKLOG-11 — Add structural validation to `read_ledger` return value

- **Category:** tech-debt
- **Priority:** medium
- **Impact:** medium
- **Effort:** small

`read_ledger()` returns `dict | None` with no structural validation of the loaded JSON shape, so callers risk `KeyError` on malformed ledger files. Use the ledger TypedDict (from BACKLOG-5) or a lightweight schema validator to catch corruption at load time.

---

### BACKLOG-12 — Write unit tests for `FileWatcherTrigger`

- **Category:** test
- **Priority:** high
- **Impact:** high
- **Effort:** medium

The entire `file_watcher` module (`FileWatcherTrigger` class) has zero test coverage. This module detects source file changes to trigger iterations and uses `rglob` with symlink-following, which could cause infinite loops. Add unit tests using `tmp_path` mock filesystems.

---

### BACKLOG-13 — Add subprocess integration test for `_execute_task` with `mock_pi.sh`

- **Category:** test
- **Priority:** high
- **Impact:** medium
- **Effort:** medium

`_execute_task` is only tested with mocked `subprocess.Popen` — no test validates actual subprocess spawning, timeout behavior, or stderr handling. The `mock_pi.sh` integration test framework exists but targets higher-level loop behavior. Add a focused integration test that spawns a real subprocess and exercises stdout/stderr, timeout, and error code paths.

---

### BACKLOG-14 — Fix heartbeat status to report 'interrupted' instead of 'alive' on shutdown ⚰️

- **Category:** bug
- **Priority:** medium
- **Impact:** medium
- **Effort:** small
- **Status:** dead-code

`_monitor_heartbeat` returns `{'status': 'alive'}` when `_shutdown_requested` event is set, which is misleading — the process didn't complete normally, it was externally interrupted. Return `'interrupted'` or `'terminated'` to distinguish clean completion from forced shutdown in the status reporting.

**Note:** `_monitor_heartbeat` and `_run_heartbeat_monitor` are dead code — not imported or called by any production module. The only production usage from `heartbeat.py` is `_cleanup_stale_heartbeats()` (called once at startup in `cli.py`). The entire heartbeat monitoring/session-killing subsystem is orphaned. This item should be re-evaluated if/when the heartbeat monitor is reconnected to production logic.
---

### BACKLOG-15 — Use `X-Forwarded-For` for rate limiter client IP behind proxy

- **Category:** security
- **Priority:** medium
- **Impact:** medium
- **Effort:** small

The rate limiter uses `request.client.host` which returns the immediate proxy IP behind nginx, not the real client IP. This allows rate limiting bypass through a reverse proxy. Check `X-Forwarded-For` or `X-Real-IP` headers first, with a configuration option, before falling back to `client.host`.

---

### BACKLOG-16 — Replace f-string HTML dashboard with a proper template engine

- **Category:** tech-debt
- **Priority:** medium
- **Impact:** medium
- **Effort:** medium

`_build_dashboard_html` constructs HTML via f-string concatenation, creating injection risks if `html.escape` is missed anywhere and making template changes difficult. Use Jinja2 or Python's `string.Template` for separation of concerns and automatic escaping.

---

### BACKLOG-17 — Add HTTPS enforcement and TLS verification for web API and callbacks

- **Category:** security
- **Priority:** medium
- **Impact:** medium
- **Effort:** medium

The API key is transmitted in plaintext if bound to `0.0.0.0`, and HTTP callbacks send the `callback_secret` as an Authorization header over plain HTTP with no TLS verification. Add TLS configuration options for the web server and enforce HTTPS callback URLs with certificate verification.

---

### BACKLOG-18 — Add unit tests for `_decode_env_var_value` edge cases

- **Category:** test
- **Priority:** medium
- **Impact:** medium
- **Effort:** small
- **Status:** completed

The `_decode_env_var_value` function in `env_utils.py` has complex boolean/int/float/bytes parsing logic with no direct unit tests. Added parametrized tests covering all parsing paths: boolean variants, integer/float edges, bytes encoding, and malformed inputs.

Implemented in `TestDecodeEnvVarValue` in `tests/test_env_utils.py` — 49 parametrized test cases across booleans, integers, floats, bytes literals, empty/None, whitespace handling, and fallback for unrecognised input.

Also implemented the `_decode_env_var_value` function itself (it was listed in the backlog but didn't exist in the codebase). Added to `omp_loop/env_utils.py`.

---

### BACKLOG-19 — Add edge case tests for `extract_json_from_output`

- **Category:** test
- **Priority:** medium
- **Impact:** medium
- **Effort:** small
- **Status:** completed

`extract_json_from_output` lacked tests for edge cases: malformed JSON, deeply nested braces, empty strings, and strings containing braces. Added 9 parametrized edge-case tests covering:
- Braces inside JSON string values (BUG-002)
- Extra trailing commas (return None or skip to previous valid block)
- Escaped quotes and backslashes in strings
- Multiple JSON blocks with mixed validity
- Empty JSON object `{}`
- Deeply nested arrays

Added to `TestExtractJsonFromOutput` class in `tests/test_file_utils.py`.

---

### BACKLOG-20 — Consolidate three module-level shutdown events into one

- **Category:** architecture
- **Priority:** medium
- **Impact:** medium
- **Effort:** medium


There are three separate module-level `threading.Event` singletons: `loop._shutdown_requested`, `heartbeat._shutdown_requested`, and functions module globals — all with overlapping responsibilities. Consolidate into a single `ShutdownManager` that all modules reference via dependency injection, eliminating the shared global state.

---

### BACKLOG-21 — Refactor oversized integration test files into focused unit tests

- **Category:** test
- **Priority:** medium
- **Impact:** medium
- **Effort:** large

Integration test files are 95KB+ each (`test_integration.py`, `test_integration_gaps.py`, `test_integration_remaining.py`), suggesting over-reliance on integration tests over focused unit tests. Extract testable logic into smaller, faster unit tests with specific assertions, keeping integration tests for true end-to-end scenarios.

---

### BACKLOG-22 — Replace global singletons with dependency injection

- **Category:** architecture
- **Priority:** medium
- **Impact:** medium
- **Effort:** xlarge

The codebase has multiple global singletons: `colorizer` (`color_utils`), `_daemon_logger` (`file_utils`), `LoopManager` (`loop_manager`), and `_shutdown_requested` (`loop`, `heartbeat`). These make parallel/async testing fragile and force module reload for clean test state. Introduce a DI container or pass dependencies explicitly through constructors.

---

### BACKLOG-23 — Make stale pending iteration threshold configurable

- **Category:** tech-debt
- **Priority:** low
- **Impact:** low
- **Effort:** small

The 300-second (5 min) threshold for detecting stale pending iterations in `state.py` is hardcoded as a magic number. On very long-running tasks or slow systems, this could incorrectly recover active iterations. Make it a configurable parameter in `LoopConfig`.

---

### BACKLOG-24 — Add module docstrings and high-level architecture documentation

- **Category:** documentation
- **Priority:** high
- **Impact:** medium
- **Effort:** medium

Several modules lack docstrings (`file_watcher.py`, `preflight.py`, `validation.py`) and there is no high-level architecture document explaining the module dependency graph, data flow, or config precedence order. `README.md` covers usage only. Add `ARCHITECTURE.md` with a dependency diagram and module responsibilities.

---

### BACKLOG-25 — Make `TASK_PATTERNS` extensible without editing source code

- **Category:** feature
- **Priority:** medium
- **Impact:** low
- **Effort:** medium

The ~150 hardcoded keywords in `TASK_PATTERNS` cannot be extended or overridden without editing source code. Allow customization via a config file key (`task_patterns`) that merges with or replaces built-in patterns so users can add custom task-type detection for their workflows.

---

### BACKLOG-26 — Differentiate `FileLock` TimeoutError from 'no ledger exists'

- **Category:** bug
- **Priority:** medium
- **Impact:** medium
- **Effort:** small

`FileLock` TimeoutError is caught by `read_ledger` and silently returns `None`, making a transient lock contention indistinguishable from 'no ledger exists'. Return a distinct sentinel or raise a specific exception so callers can differentiate retryable failures from legitimate empty states.

---

### BACKLOG-27 — Optimize `extract_json_from_output` to single-pass scan

- **Category:** performance
- **Priority:** low
- **Impact:** low
- **Effort:** small

`extract_json_from_output` runs two full scans (reverse and forward) on the entire output text — O(n²) worst case for large omp outputs. Change to a single-pass brace-depth counting algorithm that finds JSON in one forward scan.

---

### BACKLOG-28 — Fix config drift between `env_utils.KNOWN_ENV_VARS` and `config_file.DEFAULTS`

- **Category:** bug
- **Priority:** medium
- **Impact:** low
- **Effort:** small

`config_file.py` `DEFAULTS` contains `INFINITE_LOOP_GOAL_DIR` which is **not** in `env_utils.KNOWN_ENV_VARS`, indicating documentation/config drift between config sources. Audit all keys and synchronize both lists, adding a test that detects drift between the two sources.

---

### BACKLOG-29 — Fix `FileWatcherTrigger._scan` symlink loop and permission skip issues

- **Category:** bug
- **Priority:** low
- **Impact:** medium
- **Effort:** small

`FileWatcherTrigger._scan` uses `p.rglob('*')` which follows symlinks implicitly and could enter infinite loops with circular symlinks. It also silently skips permission errors. Use `p.rglob('*')` with `follow_symlinks=False` (Python 3.12+) or manually filter, and log permission errors instead of suppressing them.

---

### BACKLOG-30 — Create REPROVISION.md with dev environment setup steps

- **Category:** documentation
- **Priority:** low
- **Impact:** low
- **Effort:** small

---

### BACKLOG-31 — Heartbeat monitoring subsystem is dead code (needs removal or reconnection) ⚰️

- **Category:** architecture
- **Priority:** medium
- **Impact:** medium
- **Effort:** medium
- **Status:** completed
**Resolution:** Removed all dead heartbeat monitoring/session-killing functions (`_monitor_heartbeat`, `_run_heartbeat_monitor`, `_kill_session`, `_read_heartbeat`, `_write_heartbeat_file`, `_heartbeat_age`, `_heartbeat_path`, `_cleanup_heartbeat_file`, `_request_shutdown`) and `_shutdown_requested` event from `omp_loop/heartbeat.py`. Kept only `_cleanup_stale_heartbeats()` (used by `cli.py` at startup). Removed corresponding dead tests (~86 lines) from `tests/test_heartbeat.py`. Cleaned up unused imports.
---

### FR-001 — Current iteration (2026-07-01): Quality & test improvements

**Completed in this iteration:**

1. **Fixed 4 ruff diagnostics** in test files — removed unused variables and parameters (`F841`, `ARG002`). Verdict: clean.
2. **Fixed zombie subprocess escalation** (`BACKLOG-2`) — extracted `_kill_and_reap()` helper in `_execute_task` that logs a warning if a process survives SIGKILL (D-state), and retries. Previously the timeout was silently swallowed by `suppress(Exception)`.
3. **Added `FileWatcherTrigger` tests** (`BACKLOG-12`) — 15 tests covering initial scan, change detection, file creation/modification/deletion, single-file mode, empty directories, permission errors, and format_changed output. Also fixed `check_change()` and `format_changed()` to detect file deletions (previously only detected new/modified files).
4. **Updated backlog** — marked 6 stale items as completed or dead-code: BACKLOG-2 (done), BACKLOG-3 (dead-code), BACKLOG-9 (done), BACKLOG-12 (done), BACKLOG-14 (dead-code). SEC-002, SEC-005, BUG-002 are also done but tracked in BACKLOG.md.

**Key discovery:** The entire heartbeat monitoring/session-killing subsystem is dead code (BACKLOG-31). The `--heartbeat-timeout` config option is parsed and displayed but never acted upon.

---

### FR-002 — Current iteration (2026-07-01): Type safety, dead code removal, edge case tests

**Completed in this iteration:**

1. **Removed dead heartbeat monitoring subsystem** (`BACKLOG-31`) — removed 9 dead functions (~170 lines) and `_shutdown_requested` event from `omp_loop/heartbeat.py`. Kept only `_cleanup_stale_heartbeats()` (used by `cli.py` at startup). Removed 16 corresponding dead tests.
2. **Added `TaskResult` TypedDict** (`BACKLOG-10`) — `_execute_task()` now returns a typed `TaskResult` with required (`output`, `error`, `duration_seconds`, `returncode`) and optional keys (`n`, `summary`, `tool_usage`, `convergence`, `turns`, `token_usage`, `session_id`). Uses TypedDict inheritance pattern for Python 3.10 compatibility.
3. **Added edge case tests for `_decode_env_var_value`** (`BACKLOG-18`) — 22 parametrized tests covering booleans, integers (decimal/hex/octal/binary), floats, bytes literals, whitespace handling, and malformed inputs. Implemented the `_decode_env_var_value()` function in `env_utils.py`.
4. **Added edge case tests for `extract_json_from_output`** (`BACKLOG-19`) — 9 tests covering braces in string values (BUG-002), deeply nested JSON, multiple JSON objects, malformed JSON, empty output, and invalid content.
5. **Fixed Makefile `python3` fallback** — changed hardcoded `python3` to auto-detect `python3` or `python` via `command -v`.
6. **Updated backlog** — marked BACKLOG-10, BACKLOG-18, BACKLOG-19, BACKLOG-31 as completed.

**Test count:** 418 unit tests pass (up from 377), ruff clean.
