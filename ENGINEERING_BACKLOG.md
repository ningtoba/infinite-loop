# Engineering Backlog

> **pi-loop** (v14.39.0) — Autonomous task automation daemon
> Living document synthesizing findings from full-source audit, git analysis, test assessment, security review, dependency inspection, documentation evaluation, and tooling audit.
> Generated: 2026-06-30

---

## Table of Contents

- [How to Use This Backlog](#how-to-use-this-backlog)
- [Executive Summary](#executive-summary)
- [Priority Matrix](#priority-matrix)
- [Status Summary](#status-summary)
- [Quick Wins (High Impact, Low Effort)](#quick-wins-high-impact-low-effort)
- [🐛 Bugs & Issues](#-bugs--issues)
- [🏗️ Architecture & Design](#-architecture--design)
- [🧪 Testing & Quality](#-testing--quality)
- [🔧 Tooling & Developer Experience](#-tooling--developer-experience)
- [⚡ Performance](#-performance)
- [🔒 Security](#-security)
- [📚 Documentation](#-documentation)
- [🔄 CI/CD](#-cicd)
- [🧹 Code Cleanup](#-code-cleanup)
- [✨ Features & Ideas](#-features--ideas)
- [⬆️ Dependencies](#-dependencies)

---

## How to Use This Backlog

This backlog is organized by category, then sorted by priority within each category. Every item follows this schema:

| Field | Description |
|-------|-------------|
| **ID** | Unique identifier (e.g., BUG-001, ARCH-001) |
| **Title** | Short imperative description |
| **Category** | One of: `bug` `architecture` `testing` `tooling` `performance` `security` `documentation` `ci-cd` `cleanup` `feature` `dependency` |
| **Priority** | `Critical` — Data loss, security breach, or blocking failure. `High` — Major feature gap, significant risk. `Medium` — Important but not urgent. `Low` — Nice to have. |
| **Impact** | 1-5 (1 = minor inconvenience, 5 = system-wide failure) |
| **Effort** | 1-5 (1 = <30 min, 2 = <2 hr, 3 = <1 day, 4 = 2-3 days, 5 = 1+ week) |
| **Status** | `Pending` `Researching` `In Progress` `Done` `Won't Do` |
| **Dependencies** | List of IDs this item blocks on, or `None` |
| **Description** | 2-4 sentence explanation with specific code references |
| **Suggested Approach** | Brief notes on how to proceed |
| **Affected Files** | Specific file paths with line numbers where known |

**Maintenance:** Items should be re-prioritized quarterly. Move completed items to the bottom of their category with status `Done`. Add new items at the top within their category.

---

## Executive Summary

### What's Working Well

| Area | Verdict |
|------|---------|
| **Test suite** | 481 tests, all passing in ~3s, strong isolation with mock/fixtures |
| **Linting** | Ruff configured with 8 rule categories, 0 violations |
| **Security posture** | No hardcoded secrets, no `eval`/`pickle`, API-key auth, rate limiting |
| **Dependency management** | Pinned lockfiles via pip-compile, Dependabot configured |
| **CI/CD** | GitHub Actions with lint + test matrix (3.10–3.13) |
| **Code documentation** | Strong inline docstrings, all modules have **doc** |

### What Needs Immediate Attention

| Risk | Area | Impact |
|------|------|--------|
| 🔴 | Core daemon `run_loop()` has ~19% test coverage | Any change risks regressions in the main iteration loop |
| 🔴 | `loop_manager.py` regex-parses ANSI-colored log output | Brittle — log format changes silently break the web UI |
| 🔴 | `classify_error()` misses 10+ common error patterns | Misclassified errors apply wrong mitigation strategies |
| 🟡 | `shell=True` on user-configurable error command | If config file is compromised, arbitrary commands execute |
| 🟡 | No integration tests for `pi` subprocess | The core value proposition has zero end-to-end verification |

### Key Metrics

| Metric | Value |
|--------|-------|
| Source modules | 25 Python files (pi_loop/ + web_app/) |
| Test files | 22 files, 481 tests |
| Test coverage | 68% overall; 19% on core loop, 12% on CLI |
| CI Python matrix | 3.10, 3.11, 3.12, 3.13 |
| Lint violations | 0 (Ruff) |
| mypy status | Configured but **non-gating** (errors suppressed) |
| Security vulns | 0 known (Safety scan) |
| Bandit findings | 1 HIGH (shell=True), 2 MEDIUM, 26 LOW |
| Dependencies | 16 production, 67 dev/test (all pinned) |
| Repo age | 5 days, 213 commits, single contributor |

---

## Priority Matrix

| Impact ↓ / Effort → | Small (1-2) | Medium (3) | Large (4-5) |
|---------------------|-------------|------------|-------------|
| **Critical (5)** | BUG-013, SEC-001 | BUG-003, ARCH-001 | TEST-001, ARCH-002 |
| **High (3-4)** | BUG-002, BUG-008, CI-CD-001, CLEAN-005, FEAT-003 | TEST-003, TEST-005, TEST-008, ARCH-003, ARCH-005, PERF-003 | ARCH-004, FEAT-005 |
| **Medium (2)** | BUG-006, BUG-007, BUG-009, BUG-011, BUG-012, SEC-002, SEC-003, CI-CD-002, CI-CD-004, CLEAN-001, CLEAN-003, CLEAN-006, DOC-001, DOC-004, DEP-001 | BUG-004, BUG-010, TEST-004, TEST-006, TEST-007, PERF-001, PERF-002, SEC-004, DOC-002, DOC-003, CLEAN-004, FEAT-001 | FEAT-002, FEAT-004 |
| **Low (1)** | CLEAN-002, DEP-002 | BUG-001 | CI-CD-005 |

---

## Status Summary

| Status | Count | IDs |
|--------|-------|-----|
| **Pending** | 42 | All unmarked items |
| **Researching** | 0 | — |
| **In Progress** | 1 | BUG-003 |
| **Done** | 8 | BUG-005 (classify_error patterns), TOOL-001 (mypy CI gating), SEC-003 (HTTP headers), CI-CD-003 (bandit/safety CI), BUG-013 (uptime calculation), CLEAN-001 (stale branches/worktrees), TOOL-003 (py.typed markers), TOOL-004 (.editorconfig) |
| **Won't Do** | 0 | — |
| **Total** | 51 | — |

---

## Quick Wins (High Impact, Low Effort)

These items should be tackled first — they deliver outsized value for minimal investment:

| ID | Item | Impact | Effort | Est. Time |
|----|------|--------|--------|-----------|
| BUG-013 | `status.py` uptime calculation is mathematically wrong | 5 | 1 | 15 min |
| TOOL-001 | Wire mypy to actually fail CI (remove `|| true`) | 4 | 2 | 1-2 hr |
| BUG-002 | Log notification failures instead of `suppress(Exception)` | 4 | 1 | 30 min |
| CLEAN-005 | Add `console.error()` to empty `catch` blocks in `app.js` | 3 | 1 | 15 min |
| SEC-001 | Validate `http_callback` URL scheme (reject `file://`) | 5 | 1 | 30 min |
| SEC-002 | Add `.env` to `.gitignore` as defense-in-depth | 3 | 1 | 5 min |
| CI-CD-001 | Add coverage reporting to CI (`--cov` flags) | 3 | 1 | 30 min |
| BUG-008 | CLI `main()` silently accepts invalid `--config` JSON keys | 3 | 1 | 30 min |
| CLEAN-001 | Remove stale `hermes/hermes-*` worktree branches | 2 | 1 | 10 min |
| DEP-001 | Recompile lockfiles (installed pydantic 2.12.5 ≠ lockfile 2.13.4) | 2 | 1 | 15 min |

---

## 🐛 Bugs & Issues

### BUG-001 — Config write failures silently discarded

- **Category:** bug
- **Priority:** Medium
- **Impact:** 3
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `pi_loop/config_file.py:save_config()` catches `OSError: pass` — any filesystem error during config write is discarded with no log, no warning, no user feedback. If `~/.config/pi-loop/` doesn't exist or is read-only, the user's config changes silently disappear.
- **Suggested Approach:** Log at WARNING level with the error detail before `pass`. Add atomic write pattern (write to `.tmp` then `os.rename`).
- **Affected Files:** `pi_loop/config_file.py` line 49

### BUG-002 — Notification and HTTP callback failures silently suppressed

- **Category:** bug
- **Priority:** High
- **Impact:** 4
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `run_loop()` wraps desktop notification and HTTP callback dispatch in `with suppress(Exception):`. Connection errors, DNS failures, credential issues, and invalid notification commands all disappear without trace. Operators never know their callbacks are failing.
- **Suggested Approach:** Replace `suppress(Exception)` with `try/except` that logs at WARNING level with the error detail. Consider a configurable flag to make notifications best-effort (current) vs. required.
- **Affected Files:** `pi_loop/loop.py` lines ~225, ~244

### BUG-003 — LoopManager regex-parses ANSI-colored log output

- **Category:** bug
- **Priority:** Critical
- **Impact:** 5
- **Effort:** 3
- **Status:** In Progress
- **Dependencies:** None
- **Description:** `LoopManager._parse_line()` strips ANSI codes with `_ANSI_ESCAPE.sub("", text)` then applies 6+ fragile regex patterns to extract worker status, duration, error type, heartbeat, and iteration data. Any log format change (timestamp prefix, bracket style, color scheme change) silently breaks all web UI parsers. This is a fundamental architectural flaw — the web UI should consume structured NDJSON events, not reverse-engineer human-readable log strings.
- **Suggested Approach:** Phase 1: Add unit tests capturing current regex behavior with representative log lines. Phase 2: Add structured event emission from the daemon (JSON-format log lines with event types). Phase 3: Migrate `LoopManager` to consume structured events, keeping regex parsing as fallback.
- **Affected Files:** `web_app/loop_manager.py` (`_parse_daemon_stdout`, `_parse_line`, `_ANSI_ESCAPE`)

### BUG-004 — `cli.py` zsh completion excludes all long flags

- **Category:** bug
- **Priority:** Medium
- **Impact:** 3
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `_generate_completion()` at `cli.py:~119` filters flags with `if not f.startswith("--")` when building `_zsh_flags`. This is inverted — it discards all long flags (e.g. `--goal`, `--max-iterations`), producing completions with only short flags (`-g`, `-m`). Auto-generated zsh completions are missing ~80% of available flags.
- **Suggested Approach:** Fix the filter condition to exclude only help flags (`--help`, `-h`) instead of all `--` flags. Add a test case for completion output verification.
- **Affected Files:** `pi_loop/cli.py` ~line 119

### BUG-005 — `classify_error()` misses common timeout/network patterns

- **Category:** bug
- **Priority:** High
- **Impact:** 3
- **Effort:** 1
- **Status:** Done ✅
- **Description:** `classify_error()` checks for `"timeout"` and `"timed out"` but misses `"timedout"`, `"time_out"`, `"read timed out"`, `"connection timed out"`. Network category misses `"name or service not known"`, `"temporary failure"`, `"name resolution"`, `"no address"`, `"protocol error"`, `"ssl_error"`, `"handshake"`. Misclassified errors trigger wrong recovery strategies.
- **Suggested Approach:** ✅ Resolved — added all missing patterns and tested.
- **Affected Files:** `pi_loop/error_utils.py:classify_error()`

### BUG-006 — `file_utils.py` JSON extraction breaks on string-literals with braces

- **Category:** bug
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `extract_json_from_output()` uses simple brace-depth counting (`{` = +1, `}` = -1) with no awareness of JSON string literals. If pi output contains `{` or `}` inside a quoted JSON string (e.g., `"output": "if (x) { y }"`), the brace counter desyncs and extraction returns a partial or corrupted JSON object. Both forward and reverse scan strategies are affected.
- **Suggested Approach:** Add string-literal awareness during brace scanning: skip counts inside quoted strings (respecting escape sequences). Add test cases with braces-in-strings.
- **Affected Files:** `pi_loop/file_utils.py:extract_json_from_output()`

### BUG-007 — `pi_loop/error_recovery.py` has a dead calculation `150 // 100`

- **Category:** bug
- **Priority:** Medium
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `error_recovery.py:38` has `150 // 100` which evaluates to `1` (integer division). This appears to be a leftover from a refactor where a timeout multiplier was supposed to be computed as a float. The intended behavior was likely `150 / 100 = 1.5`. As-is, it's a no-op.
- **Suggested Approach:** Replace with the intended float multiplier `150 / 100` or extract the literal `1.5` with a named constant.
- **Affected Files:** `pi_loop/error_recovery.py` line 38

### BUG-008 — CLI `main()` silently accepts invalid `--config` JSON keys

- **Category:** bug
- **Priority:** High
- **Impact:** 3
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `cli.py:~140` reads `--config` JSON file and applies arbitrary attributes to the argparse Namespace with `setattr(args, key, val)`. There is no validation that the keys in the config file correspond to known CLI flags. A typo in config.json (e.g., `"max-iterration"` instead of `"max_iterations"`) silently creates a new attribute that is never read, while the intended setting stays at default.
- **Suggested Approach:** After loading config, validate each key against the set of known argparse flags. Log warnings for unknown keys. Consider adding a `--validate-config` flag that checks without executing.
- **Affected Files:** `pi_loop/cli.py` lines ~135-150

### BUG-009 — `preflight.py` docstring placed after `if` block

- **Category:** bug
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `preflight.py:~100`, the `check_disk_space` method has its docstring positioned after the function body's first `if` block instead of at the top of the method. This makes the docstring invisible to `help()` and IDE tooltips.
- **Suggested Approach:** Move the docstring to the first line of the method body.
- **Affected Files:** `pi_loop/preflight.py` ~line 100

### BUG-010 — `loop_manager.py` log file handle never rotates

- **Category:** bug
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `LoopManager._add_log()` opens a log file handle on startup and appends forever. There is no rotation, no size cap, no truncation. On a long-running server, this produces unbounded disk growth. The daemon-side `RotatingFileHandler` mitigates this for the daemon's own logs, but the web app's captured output has no protection.
- **Suggested Approach:** Add file size check before appending (e.g., rotate at 100MB). Or use `RotatingFileHandler` from stdlib with a reasonable max size.
- **Affected Files:** `web_app/loop_manager.py` (`_add_log`, `_close_log`)

### BUG-011 — `heartbeat.py` poll interval causes up-to-5s shutdown delay

- **Category:** bug
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `_monitor_heartbeat()` sleeps for `HEARTBEAT_POLL_INTERVAL` (5 seconds) between heartbeat checks. Any iteration completion is detected up to 5 seconds late because the poll cycle must complete before the next heartbeat check. For short iterations (<2s), this doubles the latency.
- **Suggested Approach:** Use `threading.Event.wait(timeout=interval)` with a set-able event for shutdown notification, reducing effective latency to near-zero while maintaining the poll interval.
- **Affected Files:** `pi_loop/heartbeat.py` ~line 67

### BUG-012 — `file_utils.py` file lock busy-waits with fixed 100ms sleep

- **Category:** bug
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `FileLock.__enter__` busy-waits for a lock with `time.sleep(0.1)` — a fixed 100ms interval until the timeout expires. Under contention, this creates unnecessary CPU wakeups. No exponential backoff, no jitter.
- **Suggested Approach:** Implement exponential backoff starting at 10ms, doubling per retry, with ±20% random jitter, capped at ~1s max interval.
- **Affected Files:** `pi_loop/file_utils.py` lines ~39-48

### BUG-013 — `status.py` uptime calculation is mathematically wrong

- **Category:** bug
- **Priority:** Critical
- **Impact:** 5
- **Effort:** 1
- **Status:** Done ✅
- **Dependencies:** None
- **Description:** `write_status()` computed uptime as `time.monotonic() - (time.time() - time.monotonic())` — a meaningless value. The `/proc/pid/stat` fallback path was never successfully used. The status file always reported 0 uptime.
- **Suggested Approach:** ✅ Resolved — replaced with `time.monotonic() - _process_start_time` where `_process_start_time` is set at module load time. Removed the broken `/proc` fallback entirely.
- **Affected Files:** `pi_loop/status.py`

---

## 🏗️ Architecture & Design

### ARCH-001 — `run_loop()` is a 435-line monolithic function

- **Category:** architecture
- **Priority:** Critical
- **Impact:** 5
- **Effort:** 5
- **Status:** Pending
- **Dependencies:** None
- **Description:** `run_loop()` in `loop.py` handles: subprocess spawning, iteration lifecycle, error classification, recovery adaptation, notification dispatch (desktop, HTTP callback, ntfy), dashboard HTML generation, goal evolution, convergence detection, cooldown handling, heartbeat management, ledger pruning, and git auto-commit. It has 60+ local variables and 20+ condition branches. The `# ruff: noqa: ARG001, F841` at the top acknowledges unused local assignments. Test coverage is ~19% because mocking 60+ variables is impractical.
- **Suggested Approach:** Phase 1 (low-risk): Extract pure functions (convergence check, termination check, progress classification). Phase 2: Extract I/O-bound operations (notification dispatcher, dashboard builder). Phase 3: Create `TaskExecutor`, `WorkerPool`, `ConvergenceDetector`, `NotificationDispatcher` classes. Each extraction is a separate commit with characterization tests written before touching the code.
- **Affected Files:** `pi_loop/loop.py`

### ARCH-002 — `LoopConfig` god dataclass with 71 fields

- **Category:** architecture
- **Priority:** Critical
- **Impact:** 4
- **Effort:** 4
- **Status:** Pending
- **Dependencies:** ARCH-001 (recommended — loop changes touch config)
- **Description:** `LoopConfig` is a single dataclass spanning iteration control, worker config, git settings, notifications, archiving, logging, safety, and advanced options. It violates the Single Responsibility Principle. `from_args()` imports `dataclasses._MISSING_TYPE` — a private API. When a field is added, all consumers must be checked for compatibility.
- **Suggested Approach:** Split into focused configs: `IterationConfig`, `WorkerConfig`, `GitConfig`, `NotificationConfig`, `ArchiveConfig`, `SafetyConfig`. Compose in a top-level `AppConfig`. Keep backward compatibility via `__getattr__` delegation to child configs.
- **Affected Files:** `pi_loop/config.py` (LoopConfig dataclass, lines ~68-179), `pi_loop/loop.py`, `pi_loop/cli.py`

### ARCH-003 — Extract `TaskExecutor` from `_execute_task()`

- **Category:** architecture
- **Priority:** High
- **Impact:** 3
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** ARCH-001
- **Description:** `_execute_task()` (~200 lines) handles subprocess spawning, streaming NDJSON, JSON extraction, error classification, retry logic, and result building. It returns a complex result dict. Extracting this into a dedicated `TaskExecutor` class would isolate all subprocess concerns and make the execution path independently testable.
- **Suggested Approach:** Create `pi_loop/executor.py` with `TaskExecutor` class. Move `_execute_task()` body into it, replacing result dict with a typed dataclass. The class can be tested without mocking `run_loop`'s 60 locals.
- **Affected Files:** `pi_loop/loop.py` (`_execute_task`), new `pi_loop/executor.py`

### ARCH-004 — `/proc` dependency makes the daemon Linux-only

- **Category:** architecture
- **Priority:** High
- **Impact:** 2
- **Effort:** 4
- **Status:** Pending
- **Dependencies:** None
- **Description:** `system_utils.py` reads `/proc/[pid]/status` and `/proc/[pid]/stat` for CPU/memory tracking. `server.py` reads `/proc/stat` and `/proc/meminfo`. `status.py` uses `os.sysconf_names["SC_CLK_TCK"]`. All of these are Linux-specific. The daemon cannot run on macOS or BSD without errors.
- **Suggested Approach:** Abstract a `SystemResourceProvider` interface with `LinuxProvider` (current), `macOSProvider` (using `sysctl`/`ps`), and `NoopProvider` (returns defaults). Auto-detect platform at import time. Mark platform-specific tests.
- **Affected Files:** `pi_loop/system_utils.py`, `pi_loop/status.py`, `web_app/server.py`

### ARCH-005 — Loop lacks explicit state machine abstraction

- **Category:** architecture
- **Priority:** High
- **Impact:** 3
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** ARCH-001
- **Description:** The main loop is a `while True` with ad-hoc condition checks for shutdown, pause, cooldown, etc. States (running, paused, cooldown, error, stopping) are managed via scattered boolean flags and sentinel file checks. There's no single source of truth for current state, making it hard to add new states (draining, backoff, maintenance).
- **Suggested Approach:** Introduce a `LoopStateMachine` class with explicit enum states and defined transitions. Each state has `enter()` and `exit()` hooks. Replace scattered `if` checks with `state_machine.transition_to()` calls.
- **Affected Files:** `pi_loop/loop.py`, new `pi_loop/state_machine.py`

---

## 🧪 Testing & Quality

### TEST-001 — Zero integration tests for core pi subprocess lifecycle

- **Category:** testing
- **Priority:** Critical
- **Impact:** 5
- **Effort:** 5
- **Status:** Pending
- **Dependencies:** ARCH-001, ARCH-003 (both recommended for easier isolation)
- **Description:** The core value proposition (subprocess task execution via `pi`) has zero end-to-end verification. All 481 tests are unit tests that mock subprocess calls. A `pi` binary change (flag rename, output format change, mode=json breaking change) goes undetected until production. Only `test_pi_smoke.py` checks that `pi` is on PATH — nothing tests actual output parsing.
- **Suggested Approach:** Create `tests/integration/` directory. Build a `mock_pi.sh` script that emits realistic NDJSON output. Test: single iteration success, convergence detection, error recovery with injected failures, sentinel stop/pause, multi-worker patterns. Mark integration tests with `@pytest.mark.integration`. Run as a separate CI job (not with `make test`).
- **Affected Files:** `tests/integration/` (new), `tests/integration/conftest.py`, `tests/integration/mock_pi.sh`

### TEST-002 — `file_watcher.py` has zero test coverage

- **Category:** testing
- **Priority:** High
- **Impact:** 3
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `FileWatcherTrigger` class with 5 methods and polling logic has no dedicated test file. The file watching functionality (polling directory changes, triggering iterations) is entirely untested. With 0% coverage, any regression in file watching goes undetected.
- **Suggested Approach:** Create `tests/test_file_watcher.py`. Use `tmp_path` fixtures to create temporary directory structures. Test: directory creation/deletion triggers, file modification detection, polling interval behavior, edge cases (empty directory, permission errors).
- **Affected Files:** `pi_loop/file_watcher.py`

### TEST-003 — `loop.py` core loop only 19% covered

- **Category:** testing
- **Priority:** High
- **Impact:** 4
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** ARCH-001 (easier after decomposition, but can start now)
- **Description:** Only `_execute_task`, `_evolve_goal`, `_build_dashboard_html`, and `_request_shutdown` are tested. The main `run_loop()` function (435 lines), sentinel polling, worker management, convergence detection, checkpointing, and cooldown enforcement are untested. Any refactoring of the core loop risks undetected regressions.
- **Suggested Approach:** Start with exit-early conditions (test that sentinel file causes clean shutdown, max iterations stops the loop, convergence detected, idle limit enforced). Then test iteration lifecycle with mocked `_execute_task`. Write characterization tests before refactoring (capture current behavior, then refactor against captured behavior).
- **Affected Files:** `pi_loop/loop.py`, `tests/test_loop.py`

### TEST-004 — `cli.py` main() entry point only 12% covered

- **Category:** testing
- **Priority:** Medium
- **Impact:** 3
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** None
- **Description:** Only `_create_parser()` is tested in `test_cli.py`. The `main()` function (~200 lines with 14+ introspection flags, config loading, daemon dispatch) is untested. Command dispatch, help topic rendering, doctor output, healthcheck formatting, status display — all have no test coverage.
- **Suggested Approach:** Refactor `main()` to accept an argument list for easier testing. Test each introspection flag independently (`--status`, `--doctor`, `--preflight`, `--list-flags`, `--explain`, `--help-topic`). Test config file loading with valid/invalid/missing files.
- **Affected Files:** `pi_loop/cli.py`, `tests/test_cli.py`

### TEST-005 — `file_utils.py` JSON extraction needs string-literal test cases

- **Category:** testing
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** BUG-006
- **Description:** `extract_json_from_output()` has test coverage for basic JSON extraction but no test cases for JSON containing braces inside string values, nested objects with >5 levels, empty objects, or malformed JSON with unmatched braces.
- **Suggested Approach:** Add parametrized test cases covering: braces-in-strings, deeply nested JSON, empty JSON objects, JSON with unicode escapes, JSON with escaped quotes, truncated JSON, and output with multiple JSON objects.
- **Affected Files:** `pi_loop/file_utils.py:extract_json_from_output()`, `tests/test_file_utils.py`

### TEST-006 — `server.py` needs coverage for SSE, error handlers, remaining API routes

- **Category:** testing
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** None
- **Description:** `web_app/server.py` has only 55% coverage. Auth middleware and rate limiting are well-tested, but SSE streaming, config CRUD endpoints, system monitoring endpoints, CORS handling, and error handlers have limited or no test coverage.
- **Suggested Approach:** Use `TestClient` from Starlette to test each API route with valid/auth/invalid requests. Test SSE stream initialization and heartbeat events. Test CORS header presence on all responses. Test 404, 405, and 500 error handlers.
- **Affected Files:** `web_app/server.py`, `tests/test_server.py`

### TEST-007 — `rate_limiter.py` needs direct unit tests

- **Category:** testing
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `SlidingWindowRateLimiter` (4 async methods) is only tested indirectly through `test_server.py`. There are no direct unit tests for: rate limit check logic, time window rolling, remaining count calculation, reset behavior, concurrent access under asyncio.Lock.
- **Suggested Approach:** Create `tests/test_rate_limiter.py` with `pytest-asyncio` tests. Use `asyncio.Lock` directly (no patching needed). Test: single IP stays under limit, burst exceeds limit, window rolls correctly, multiple IPs tracked independently, remaining count accuracy.
- **Affected Files:** `web_app/rate_limiter.py`

### TEST-008 — `env_utils.py` has disproportionately low coverage (75%)

- **Category:** testing
- **Priority:** High
- **Impact:** 3
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** At ~528 lines, `env_utils.py` is the largest module in `pi_loop/` with functions for env var management, .env file parsing, variable validation, fuzzy typo detection via `difflib`, and 100+ `KNOWN_ENV_VARS` entries. Despite its size and complexity, coverage is only 75%, leaving validation edge cases and .env parsing error paths untested.
- **Suggested Approach:** Add parametrized tests for: .env file parsing with various formats (quoted values, comments, blank lines, variable expansion), fuzzy matching edge cases (short strings, empty input, special characters), validation of all 100+ known env vars, error handling (missing files, permission errors, malformed content).
- **Affected Files:** `pi_loop/env_utils.py`, `tests/test_env_utils.py`

---

## 🔧 Tooling & Developer Experience

### TOOL-001 — mypy is configured but non-gating in CI

- **Category:** tooling
- **Priority:** High
- **Impact:** 4
- **Effort:** 2
- **Status:** Done ✅
- **Description:** Both `lint-all` and `mypy` Makefile targets suppress errors with `2>/dev/null; true`. CI runs `make mypy` but never fails — any type error passes silently. Mypy catches real bugs (wrong return types, missing None checks, incorrect optional handling) but isn't allowed to.
- **Suggested Approach:** ✅ Resolved — removed error suppression, fixed existing mypy errors, wired into CI as gating step.
- **Affected Files:** `Makefile` (mypy target), `.github/workflows/ci.yml`

### TOOL-002 — Pre-commit duality — `.pre-commit-config.yaml` and `.githooks/pre-commit` are independent

- **Category:** tooling
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** There are two independent pre-commit systems: `.pre-commit-config.yaml` (used by `pre-commit` tool, runs ruff + file checks) and `.githooks/pre-commit` (bash script, also runs ruff check+format on staged files). The `.githooks/README.md` describes a different hook (shell completion regeneration) than what the script actually does (ruff linting). Contributors get inconsistent behavior depending on which system they activate.
- **Suggested Approach:** Pick one system and remove the other. Either: (a) use `pre-commit` tool exclusively (preferred — more maintainable) and delete `.githooks/pre-commit`, or (b) keep the bash script and delete `.pre-commit-config.yaml`. Document the chosen approach in CONTRIBUTING.md.
- **Affected Files:** `.pre-commit-config.yaml`, `.githooks/pre-commit`, `.githooks/README.md`

### TOOL-003 — No `py.typed` marker for downstream type checking

- **Category:** tooling
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Done ✅
- **Dependencies:** None
- **Description:** Neither `pi_loop/` nor `web_app/` had a `py.typed` marker file. PEP 561 compliance was missing.
- **Suggested Approach:** ✅ Resolved — added empty `py.typed` to both `pi_loop/` and `web_app/` packages.
- **Affected Files:** `pi_loop/py.typed`, `web_app/py.typed`

### TOOL-004 — No `.editorconfig` for cross-editor consistency

- **Category:** tooling
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Done ✅
- **Dependencies:** None
- **Description:** There was no `.editorconfig` file for cross-editor consistency.
- **Suggested Approach:** ✅ Resolved — added `.editorconfig` with `indent_style = space`, `indent_size = 4`, `trim_trailing_whitespace = true`, `insert_final_newline = true`, `max_line_length = 120`, `end_of_line = lf`, and YAML/JSON overrides.
- **Affected Files:** `.editorconfig`

### TOOL-005 — No `pyproject.toml` section for coverage reporting

- **Category:** tooling
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** Coverage settings are not centralized in `pyproject.toml`. The `[tool.coverage.run]` section should define source paths and omit patterns so that `pytest --cov` has consistent behavior across environments.
- **Suggested Approach:** Add `[tool.coverage.run]` section with `source = ["pi_loop", "web_app"]` and `omit = ["*/tests/*", "*/__main__.py"]`. Add `[tool.coverage.report]` with `fail_under = 65`.
- **Affected Files:** `pyproject.toml`

---

## ⚡ Performance

### PERF-001 — Dashboard rebuilt from scratch every iteration

- **Category:** performance
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `_build_dashboard_html()` reconstructs the entire 50-iteration HTML table every iteration, including serializing all iteration records to HTML strings. Fine for current scale (<100 iterations), but O(n) in iterations and O(n²) in total data processed across all calls. For long-running daemons with thousands of iterations, this becomes a noticeable lag on each iteration cycle.
- **Suggested Approach:** Implement incremental rendering: only append new rows instead of rebuilding. Cap the total rows to a configurable limit (currently hardcoded at 50). Consider switching to client-side rendering (web API provides JSON, JS renders).
- **Affected Files:** `pi_loop/loop.py` (`_build_dashboard_html`)

### PERF-002 — `file_watcher.py` uses full directory scan with `sorted(rglob("*"))`

- **Category:** performance
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `FileWatcherTrigger.check_change()` calls `sorted(p.rglob("*"))` which scans the entire directory tree and sorts all entries — O(n log n) where n is the number of files. For large source trees (e.g., a monorepo with node_modules), this is slow on every poll. The scan is also recomputed from scratch rather than using inotify/kqueue for incremental detection.
- **Suggested Approach:** Filter `rglob` to relevant file patterns (`.py`, `.md`, `.yaml`). Use `os.stat` mtime comparison instead of full content hashing. Consider adding `watchdog` as optional dependency for OS-level file system notifications.
- **Affected Files:** `pi_loop/file_watcher.py`

### PERF-003 — SSE poller runs every 2 seconds unconditionally

- **Category:** performance
- **Priority:** High
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `_status_poller()` reads the entire JSON ledger from disk every 2 seconds and broadcasts to all SSE clients. This creates unnecessary I/O even when nothing has changed. With 0 connected SSE clients, the poller continues reading the ledger and generating events.
- **Suggested Approach:** Check ledger file mtime before reading — skip if unchanged since last read. Skip the entire poll cycle when `_sse_clients` is empty. Make poll interval configurable.
- **Affected Files:** `web_app/server.py` (~line 225)

### PERF-004 — Log tag colorization applies 20+ regex substitutions per log call

- **Category:** performance
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `_colorize_log_tags()` iterates over 20+ regex patterns and applies `re.sub()` for each one on every log message. For high-frequency log messages, this is wasteful — most patterns don't match but still incur regex compilation and matching overhead.
- **Suggested Approach:** Pre-compile all regex patterns at module load time. Use a single-pass scanner instead of sequential substitutions. Or: only apply colorization when output is a TTY.
- **Affected Files:** `pi_loop/file_utils.py` (`_colorize_log_tags`, `_tag_color_map`)

### PERF-005 — JSON extraction does two full scans of output text

- **Category:** performance
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** BUG-006
- **Description:** `extract_json_from_output()` first attempts a reverse scan (building `json_chars` with repeated list `insert(0, ch)` — O(n²) due to left-insert). If that fails, it falls back to a forward scan. For large outputs with no JSON, every character is processed twice with O(n²) insert in the first pass.
- **Suggested Approach:** Use a single forward pass with stack-based brace tracking (instead of counter + `insert(0, ch)`). Fix the string-literal awareness bug (BUG-006) at the same time. Eliminate the reverse-scan fallback.
- **Affected Files:** `pi_loop/file_utils.py:extract_json_from_output()`

---

## 🔒 Security

### SEC-001 — `http_callback` URL scheme validation missing (Bandit B310)

- **Category:** security
- **Priority:** Critical
- **Impact:** 5
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `loop.py:~714` invokes `urllib.request.urlopen()` on a user-configurable `http_callback` URL with no scheme validation. A `file://` URL could read local files. A `data://` URL could trigger unexpected behavior. Bandit flags this as B310. While the web UI is localhost-only by default, the CLI daemon can be configured remotely.
- **Suggested Approach:** Add `urlparse` validation that restricts schemes to `http` and `https` only. Log and skip (or warn) on invalid schemes. Add test cases for various scheme inputs.
- **Affected Files:** `pi_loop/loop.py` ~line 714

### SEC-002 — `.env` not in `.gitignore` (currently commented out)

- **Category:** security
- **Priority:** Medium
- **Impact:** 3
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** The `.gitignore` file has `.env` commented out with the note "config_file used instead." While the project does use JSON config files, if a developer creates a `.env` file locally with secrets (API keys, callback secrets), those secrets would be committed to git. This is defense-in-depth — the cost is zero.
- **Suggested Approach:** Uncomment the `.env` entry and add `.env.*` (covers `.env.local`, `.env.production`) as well. Add a comment explaining this is a safety net even though `.env` is not the primary config mechanism.
- **Affected Files:** `.gitignore`

### SEC-003 — No HTTP security headers

- **Category:** security
- **Priority:** Medium
- **Impact:** 3
- **Effort:** 2
- **Status:** Done ✅
- **Description:** The FastAPI web server was missing Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, and X-XSS-Protection headers. While the web UI is localhost-only by default, these headers are standard defense-in-depth for any HTTP service.
- **Suggested Approach:** ✅ Resolved — Added security headers middleware.
- **Affected Files:** `web_app/server.py`

### SEC-004 — `PI_LOOP_API_KEY` read from `os.environ` on every request

- **Category:** security
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** The `api_key_auth` middleware reads `PI_LOOP_API_KEY` from `os.environ` on every HTTP request. If the env var changes after startup (possible in container orchestration or when the env is mutated), auth behavior changes without warning. More critically, if the var is accidentally unset, authentication silently disables.
- **Suggested Approach:** Read `PI_LOOP_API_KEY` once at server startup in `main()` and pass it as a closure variable or module-level constant. Log a warning if auth is enabled/disabled at startup with the detected value (masked).
- **Affected Files:** `web_app/server.py`

### SEC-005 — `shell=True` on user-configurable error command (Bandit B602)

- **Category:** security
- **Priority:** High
- **Impact:** 4
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `loop.py:727` runs `subprocess.run(on_error_cmd, shell=True, timeout=30)` where `on_error_cmd` is user-configurable via `config.json` or `--on-error-cmd` flag. If an attacker gains write access to `~/.config/pi-loop/config.json`, they can execute arbitrary shell commands. This is an intentional feature but has insufficient guardrails.
- **Suggested Approach:** At minimum: (1) log the full command before execution at INFO level, (2) validate command length and character restrictions, (3) document the risk explicitly in README, (4) add a warning on startup when `on_error_cmd` is configured.
- **Affected Files:** `pi_loop/loop.py` line 727

### SEC-006 — No secrets scanner in CI

- **Category:** security
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** The CI pipeline has no secrets scanning. A developer could accidentally commit an API key, token, or password, and it would pass CI without detection. While no secrets are currently in the repo (verified), this is a regression risk.
- **Suggested Approach:** Add `truffleHog`, `ggshield`, or `detect-secrets` to CI. The simplest option is `detect-secrets` which has a pre-commit hook and CI integration.
- **Affected Files:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`

---

## 📚 Documentation

### DOC-001 — README missing Swagger UI link, screenshot, and pi version requirement

- **Category:** documentation
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** README lacks: (1) link to auto-generated FastAPI `/docs` OpenAPI endpoint, (2) screenshot or preview of the web UI dashboard, (3) minimum required `pi` coding agent version, (4) note that `pi` must be on PATH. These are the first things a new user looks for.
- **Suggested Approach:** Add a "Prerequisites" section with `pi` version requirement. Add a link to `/docs` after the web UI features section. Add a screenshot (or placeholder) of the dashboard. The README already has most content — these are small gaps.
- **Affected Files:** `README.md`

### DOC-002 — No CHANGELOG.md for release history

- **Category:** documentation
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** CI-CD-002 (release workflow)
- **Description:** Despite having version `14.39.0` in `pyproject.toml` and `__init__.py`, and 213 commits with descriptive messages, there is no `CHANGELOG.md`. Users and developers cannot see what changed between versions, what bugs were fixed, or when features were added. The changelogs that exist in git worktrees are stale and not synced.
- **Suggested Approach:** Create `CHANGELOG.md` following Keep a Changelog format. Populate with entries from git history (conventional commits can be mapped to changelog sections). Add `make changelog` target for automated generation from git log.
- **Affected Files:** `CHANGELOG.md` (new)

### DOC-003 — No CONTRIBUTING.md

- **Category:** documentation
- **Priority:** Medium
- **Impact:** 3
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** None
- **Description:** There is no CONTRIBUTING.md. A new contributor has no guidance on: development setup, branch strategy, PR workflow, commit message conventions, coding standards, how to run tests, how to debug failures, or where to ask questions. The project has good tooling (pre-commit, Makefile, ruff, mypy) but none of it is documented for contributors.
- **Suggested Approach:** Create CONTRIBUTING.md with sections: Development Setup, Project Structure, Running Tests, Coding Standards (link to pyproject.toml config), Commit Convention (Conventional Commits), PR Workflow, Issue Templates. Reference the existing Makefile targets.
- **Affected Files:** `CONTRIBUTING.md` (new)

### DOC-004 — No SECURITY.md for vulnerability disclosure

- **Category:** documentation
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** The project has security features (API-key auth, rate limiting, CORS, HMAC webhook signing) but no SECURITY.md. Security researchers or users who find vulnerabilities have no guidance on how to report them responsibly.
- **Suggested Approach:** Create SECURITY.md with: supported versions, reporting process (email or GitHub advisory), expected response timeline, and PGP key if applicable.
- **Affected Files:** `SECURITY.md` (new)

### DOC-005 — No inline docstring for `set_max_output_chars`/`get_max_output_chars`

- **Category:** documentation
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `functions.py` has two module-level functions (`set_max_output_chars`, `get_max_output_chars`) with zero docstrings. These manage mutable global state — exactly the kind of code that needs clear documentation about side effects.
- **Suggested Approach:** Add docstrings explaining what they do, what the default value is, and that they modify module-level global state (and why).
- **Affected Files:** `pi_loop/functions.py` lines ~18, ~22

---

## 🔄 CI/CD

### CI-CD-001 — Coverage reporting not wired into CI

- **Category:** ci-cd
- **Priority:** High
- **Impact:** 3
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** TOOL-005 (coverage config in pyproject.toml)
- **Description:** `pytest-cov` is installed and available, but `make test` does not use `--cov` flags. CI runs `make test` without coverage, so coverage cannot decrease without anyone noticing. The coverage report from earlier audits (68% overall, 19% loop.py) cannot be tracked over time.
- **Suggested Approach:** Add `--cov=pi_loop --cov=web_app --cov-report=term-missing` to `make test`. Add coverage threshold in `pyproject.toml` `[tool.coverage.report]` with `fail_under = 65`. Add coverage artifact upload to CI.
- **Affected Files:** `Makefile` (test target), `.github/workflows/ci.yml`, `pyproject.toml`

### CI-CD-002 — No release workflow (tag → build → publish)

- **Category:** ci-cd
- **Priority:** Medium
- **Impact:** 3
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** None
- **Description:** Despite having version `14.39.0` and 213 commits, there are zero git tags and no release workflow. The version number exists only in source files. There is no automation to build the package, create a GitHub release, or publish to PyPI. Releases are manual (if they happen at all).
- **Suggested Approach:** Create `.github/workflows/release.yml` triggered by `v*` tag push. Steps: build distribution (`python -m build`), create GitHub Release with changelog, optionally publish to PyPI via `pypa/gh-action-pypi-publish`. Add `make release` target that tags and pushes.
- **Affected Files:** `.github/workflows/release.yml` (new), `Makefile`

### CI-CD-003 — Security scanning (bandit/safety) not in CI

- **Category:** ci-cd
- **Priority:** Medium
- **Impact:** 3
- **Effort:** 2
- **Status:** Done ✅
- **Description:** Bandit and Safety are installed as dev dependencies but are not run in CI. Security regressions (new CVEs, new vulnerable code patterns) go undetected in pull requests.
- **Suggested Approach:** ✅ Resolved — Added `make security` step to CI, including both bandit and safety scans. Bandit report uploaded as artifact.
- **Affected Files:** `.github/workflows/ci.yml`, `Makefile`

### CI-CD-004 — Safety CLI uses deprecated `check` command

- **Category:** ci-cd
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `make security` uses `safety check -r requirements.txt -r requirements-dev.txt --continue-on-error`. The `check` command is deprecated in Safety 3.x; the recommended replacement is `safety scan`.
- **Suggested Approach:** Migrate to `safety scan -r requirements.txt -r requirements-dev.txt --continue-on-error`. Update Makefile and CI.
- **Affected Files:** `Makefile` (security target)

### CI-CD-005 — No Docker build/release workflow

- **Category:** ci-cd
- **Priority:** Low
- **Impact:** 1
- **Effort:** 4
- **Status:** Pending
- **Dependencies:** CI-CD-002 (release workflow), FEAT-005 (Dockerfile)
- **Description:** The project has no Docker image building or publishing in CI. Dockerfiles exist only in stale git worktrees. Users who want to run pi-loop in a container must create their own Dockerfile.
- **Suggested Approach:** After creating a proper Dockerfile (FEAT-005), add a CI job that builds the Docker image and pushes to GitHub Container Registry (ghcr.io) on version tags.
- **Affected Files:** `.github/workflows/release.yml`

---

## 🧹 Code Cleanup

### CLEAN-001 — Remove stale `hermes/hermes-*` worktree branches

- **Category:** cleanup
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Done ✅
- **Dependencies:** None
- **Description:** Three stale local branches (`hermes/hermes-bd038f68`, `hermes/hermes-d19eb158`, `hermes/hermes-edaf42c8`) remained from the hermes-agent era.
- **Suggested Approach:** ✅ Resolved — removed worktrees with `git worktree remove -f -f`, deleted branches with `git branch -D`, verified `main` unaffected.
- **Affected Files:** Git branches, `.worktrees/` directory

### CLEAN-002 — `loop.py` has unused imports and suppressed lint warnings

- **Category:** cleanup
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** ARCH-001
- **Description:** `loop.py` has `# ruff: noqa: ARG001, F841` at module level to suppress unused argument and variable warnings. The `run_loop` function unpacks 20+ `cfg.*` attributes into local variables, many of which are never used. There are also dual imports — both `status.write_status` and `file_utils.write_status_file` are imported but only one is called.
- **Suggested Approach:** After decomposing `run_loop()` (ARCH-001), clean up unused local variable assignments. Remove the module-level `noqa` comment. Audit and deduplicate imports.
- **Affected Files:** `pi_loop/loop.py`

### CLEAN-003 — `error_utils.py: _suggest_actionable_fix()` (~130 lines) has complex nested conditionals

- **Category:** cleanup
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** None
- **Description:** `_suggest_actionable_fix()` uses deeply nested if/elif chains for every error-type × classification combination (~130 lines). Some branches return `None` after assembling tips that are then discarded (e.g., the regression branch). The complexity makes it hard to test exhaustively and hard to add new error patterns.
- **Suggested Approach:** Replace with a lookup table (dict mapping `(error_type, progress_classification) → suggestion_template`). Each entry is a standalone data item, easy to test and extend. This also makes the function pure and testable without mocks.
- **Affected Files:** `pi_loop/error_utils.py` (`_suggest_actionable_fix`)

### CLEAN-004 — Duplicate status file writers: `status.py` and `file_utils.py`

- **Category:** cleanup
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** `pi_loop/status.py:write_status()` writes a comprehensive status JSON file for the web UI. `pi_loop/file_utils.py:write_status_file()` writes a lightweight one-liner. Both write JSON status about the same daemon process but with different schemas and from different call sites inside `run_loop()`. Adding a field requires updating both — a maintenance liability.
- **Suggested Approach:** Unify into a single writer. `status.py:write_status()` already has the richer schema. Have `file_utils.py` import and call it, or remove the lightweight variant and update `run_loop()` call sites.
- **Affected Files:** `pi_loop/status.py`, `pi_loop/file_utils.py:write_status_file()`, `pi_loop/loop.py`

### CLEAN-005 — `app.js` has multiple empty `catch` blocks

- **Category:** cleanup
- **Priority:** High
- **Impact:** 3
- **Effort:** 1
- **Status:** Done ✅
- **Dependencies:** None
- **Description:** Claimed 5+ empty `catch` blocks in `web_app/static/app.js`.
- **Suggested Approach:** ✅ Resolved upon review: all 14 `catch` blocks already have `console.warn` or `console.error` logging with descriptive labels. No changes needed.
- **Affected Files:** None (already correct)

### CLEAN-006 — CLI help menu has stale/misleading completions

- **Category:** cleanup
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** BUG-004
- **Description:** The `_generate_completion()` function in `cli.py` has a Python < 3.12 workaround (`_zsh_sep = chr(92) + chr(10) + "        "`) for f-string backslash limitations. Given Python 3.10+ requirement, this workaround is already obsolete in 3.12+ and fragile. Together with BUG-004 (long flags excluded), the completions are both incorrect and messy.
- **Suggested Approach:** Use f-string with `\n` directly (requires Python 3.12+, which is reasonable given the 3.10 floor). Fix the long flag filtering (BUG-004). Add tests for generated completion output. Document the minimum Python version for completion generation.
- **Affected Files:** `pi_loop/cli.py` (`_generate_completion`)

---

## ✨ Features & Ideas

### FEAT-001 — Support multiple named config profiles

- **Category:** feature
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** None
- **Description:** Currently there is a single `~/.config/pi-loop/config.json`. Users who run different loop configurations (e.g., "code review" vs "research" vs "bug fixing") must manually swap config files. Support for named profiles (`--profile research`) would make this seamless.
- **Suggested Approach:** Change `config_file.py` to support a config directory instead of a single file. Add `--profile` CLI flag. Store configs as `config_{profile}.json`. The web UI can add a profile selector dropdown.
- **Affected Files:** `pi_loop/config_file.py`, `pi_loop/cli.py`, `web_app/config_manager.py`, `web_app/static/index.html`

### FEAT-002 — Add Prometheus metrics endpoint

- **Category:** feature
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** None
- **Description:** The web server exposes iteration counts, error counts, and system resources via the dashboard, but there is no Prometheus `/metrics` endpoint for integration with monitoring stacks. Operators who use Grafana/Prometheus cannot monitor the daemon without custom scraping.
- **Suggested Approach:** Add optional Prometheus metrics via `prometheus_fastapi_instrumentator`. Export: request count/latency by endpoint, iteration rate, iteration duration, worker count, error rate by type. Disabled by default — enabled with `--metrics` flag or config setting.
- **Affected Files:** `web_app/server.py`, `pi_loop/config.py`, `pyproject.toml` (optional dep)

### FEAT-003 — Structured JSON logging for the daemon

- **Category:** feature
- **Priority:** High
- **Impact:** 4
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** None
- **Description:** All daemon logging uses bare `print()` calls and `logger.info(f"...")` with inline string formatting. No structured fields (event type, iteration number, error code, duration, correlation ID). The web UI's regex-based parsers (BUG-003) exist because there's no structured event stream to consume. Without structured logging, production debugging is manual log scraping.
- **Suggested Approach:** Define a `StructuredEvent` TypedDict or dataclass with fields: `event` (machine-readable name), `iteration`, `duration_ms`, `error_type`, `worker_id`, `correlation_id`. Replace `print()` with a `log_event()` function that writes JSON lines. Console output stays human-readable. File output uses JSON format.
- **Affected Files:** `pi_loop/file_utils.py`, `pi_loop/loop.py`, `pi_loop/error_recovery.py`, `pi_loop/git_utils.py`, `web_app/loop_manager.py`

### FEAT-004 — Web UI dark/light theme persistent toggle

- **Category:** feature
- **Priority:** Low
- **Impact:** 1
- **Effort:** 2
- **Status:** Pending
- **Dependencies:** None
- **Description:** The web UI has a theme toggle button that switches between dark and light themes, but the preference is not persisted across page reloads (no localStorage or cookie). Users must re-toggle the theme each time they load the dashboard.
- **Suggested Approach:** Save theme preference to `localStorage` on toggle. On page load, read `localStorage` and apply the saved theme before rendering the page (to prevent flash of wrong theme). The CSS already supports both themes.
- **Affected Files:** `web_app/static/app.js`, `web_app/static/index.html`

### FEAT-005 — Dockerfile and docker-compose for containerized deployment

- **Category:** feature
- **Priority:** Low
- **Impact:** 2
- **Effort:** 3
- **Status:** Pending
- **Dependencies:** None
- **Description:** The project has no Dockerfile in the main repository. Dockerfiles exist only in stale git worktrees. Containerized deployment would make it easy to run pi-loop in CI/CD pipelines, cloud environments, or isolated environments.
- **Suggested Approach:** Create a multi-stage Dockerfile: build stage (install build tools, compile) → runtime stage (Python slim image, copy installed package). Use `uvicorn` as entry point for web UI. Create `docker-compose.yml` with volume mounts for config, ledger data, and pi binary.
- **Affected Files:** `Dockerfile` (new), `docker-compose.yml` (new), `.dockerignore` (new)

---

## ⬆️ Dependencies

### DEP-001 — Recompile lockfiles (pydantic/lockfile version drift)

- **Category:** dependency
- **Priority:** Medium
- **Impact:** 2
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** The installed pydantic version (2.12.5) differs from the lockfile version (2.13.4), suggesting the last `pip install` used range resolution instead of the lockfile. Lockfiles are meant to be the source of truth — drift indicates either manual `pip install` without `--no-deps` or lockfiles not recompiled after the last `pyproject.toml` change.
- **Suggested Approach:** Run `make update-lock` to regenerate both lockfiles from current `pyproject.toml`. Run `make verify-lock` to confirm. Then reinstall from lockfiles: `pip install -r requirements.txt -r requirements-dev.txt`.
- **Affected Files:** `requirements.txt`, `requirements-dev.txt`

### DEP-002 — `pip-tools` and `pre-commit` not declared as dev dependencies

- **Category:** dependency
- **Priority:** Low
- **Impact:** 1
- **Effort:** 1
- **Status:** Pending
- **Dependencies:** None
- **Description:** `pip-tools` (needed for `make update-lock` and `make verify-lock`) is not declared in `[project.optional-dependencies]`. Neither is `pre-commit` (needed for `make pre-commit`). A developer running `pip install -e ".[test,dev]"` won't get these tools and will get errors when running these Makefile targets.
- **Suggested Approach:** Add `pip-tools>=7.0` and `pre-commit>=3.0` to the `dev` optional dependencies group in `pyproject.toml`. Recompile lockfiles after adding.
- **Affected Files:** `pyproject.toml` `[project.optional-dependencies] dev`

---

*This backlog is a living document. Last updated: 2026-06-30. Total items: 51 (47 pending, 3 done, 1 in progress).*
