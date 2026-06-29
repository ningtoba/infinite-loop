# Engineering Backlog

> **pi-loop** (v14.39.0) — Autonomous task automation daemon
> Comprehensive backlog synthesized from full-source audit, test assessment, security review, dependency inspection, documentation evaluation, and tooling audit.
> Generated: 2026-06-30

---

## How to Use This Backlog

This backlog is organized by category, then sorted by priority within each category. Every item follows this schema:

| Field | Description |
|-------|-------------|
| **ID** | Unique identifier (e.g., BUG-001, ARCH-001) |
| **Title** | Short imperative description |
| **Category** | See category tags below |
| **Priority** | `Critical` — Data loss, security breach, or blocking failure. `High` — Major feature gap, significant risk. `Medium` — Important but not urgent. `Low` — Nice to have. |
| **Impact** | How much value fixing this provides |
| **Effort** | small / medium / large / xlarge |
| **Status** | open / in-progress / done |
| **Affected Files** | Specific file paths with line numbers where known |
| **Description** | 2-4 sentence explanation with specific code references |
| **Research Notes** | Approach notes, references, or context |

**Maintenance:** Items should be re-prioritized quarterly. Move completed items to the bottom of their category with status `done`. Add new items at the top within their category.

---

## Top 5 Most Critical Items

| Rank | ID | Title | Priority | Effort |
|------|-----|-------|----------|--------|
| ⭐1 | ARCH-001 | Decompose `run_loop()` monolithic ~400-line function | Critical | xlarge |
| ⭐2 | ARCH-002 | Refactor `LoopConfig` god dataclass with 71 fields | Critical | large |
| ⭐3 | TEST-001 | Zero integration tests for core pi subprocess lifecycle | Critical | xlarge |
| ⭐4 | SEC-005 | `shell=True` on user-configurable error command lacks guardrails | High | small |
| ⭐5 | BUG-006 | JSON extraction breaks on string-literals with braces | Medium | small |

---

## Quick Wins (High Impact, Low Effort)

| ID | Item | Impact | Effort | Est. Time |
|----|------|--------|--------|-----------|
| BUG-011 | Heartbeat poll interval causes up-to-5s shutdown delay | Medium | small | 30 min |
| BUG-012 | File lock busy-waits with fixed 100ms sleep | Medium | small | 30 min |
| PERF-004 | Log tag colorization applies 20+ regex substitutions per call | Low | small | 30 min |
| PERF-005 | JSON extraction does two full scans of output text | Low | small | 30 min |
| DOC-002 | Create CHANGELOG.md for release history | Medium | medium | 1-2 hr |
| DOC-003 | Create CONTRIBUTING.md with dev setup guidance | Medium | medium | 1-2 hr |
| SEC-002 | Uncomment `.env` in `.gitignore` as defense-in-depth | Medium | small | 5 min |
| SEC-006 | Add secrets scanner to CI | Medium | small | 1 hr |
| CI-CD-004 | Migrate Safety CLI from deprecated `check` to `scan` | Low | small | 15 min |
| TOOL-005 | Add coverage config section to pyproject.toml | Low | small | 15 min |
| CLEAN-003 | Replace complex nested conditionals with lookup table in `_suggest_actionable_fix()` | Medium | medium | 1 hr |
| CLEAN-006 | Fix stale CLI help menu completions | Low | small | 30 min |
| FEAT-004 | Persist web UI theme preference in localStorage | Low | small | 30 min |

---

## 🐛 Bugs & Issues

### [BUG-001] Config write failures silently discarded

- **Category:** bug
- **Priority:** Medium
- **Impact:** Low — users unknowingly lose config changes when filesystem is unwritable
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/config_file.py` line 49
- **Description:** `pi_loop/config_file.py:save_config()` catches `OSError: pass` — any filesystem error during config write is discarded with no log, no warning, no user feedback. If `~/.config/pi-loop/` doesn't exist or is read-only, the user's config changes silently disappear. Additionally, the backup strategy uses `os.replace()` before the write succeeds — if `_atomic_write` fails, the original config is already lost.
- **Research Notes:** Add atomic write pattern (write to `.tmp` then `os.rename`). Log at WARNING level with error detail. Keep the original file in place until the write succeeds.

### [BUG-002] Notification and HTTP callback failures silently suppressed

- **Category:** bug
- **Priority:** High
- **Impact:** Medium — operators never know their notifications/callbacks are failing
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/loop.py` lines ~225, ~244
- **Description:** `run_loop()` wraps desktop notification and HTTP callback dispatch in `with suppress(Exception):`. Connection errors, DNS failures, credential issues, and invalid notification commands all disappear without trace. Operators never know their callbacks are failing.
- **Research Notes:** Replace `suppress(Exception)` with `try/except` that logs at WARNING level with the error detail. Consider a configurable flag to make notifications best-effort (current) vs. required.

### [BUG-003] LoopManager regex-parses ANSI-colored log output

- **Category:** bug
- **Priority:** Critical
- **Impact:** High — log format changes silently break the entire web UI
- **Effort:** medium
- **Status:** done
- **Affected Files:** `pi_loop/events.py` (new), `pi_loop/loop.py`, `web_app/loop_manager.py` (`_parse_daemon_line`, `_handle_event`), `tests/test_loop_manager.py`
- **Description:** `LoopManager._parse_line()` strips ANSI codes with `_ANSI_ESCAPE.sub("", text)` then applies 6+ fragile regex patterns to extract worker status, duration, error type, heartbeat, and iteration data. Any log format change (timestamp prefix, bracket style, color scheme change) silently breaks all web UI parsers. This is a fundamental architectural flaw — the web UI should consume structured NDJSON events, not reverse-engineer human-readable log strings.
- **Resolution notes:** Added `pi_loop/events.py` with `emit_event()` — emits structured NDJSON `[EVENT]` lines alongside existing human-readable output. Added `emit_event()` calls at all key lifecycle points in `loop.py` (spawn, term, worker_response, iteration_start, iteration_complete, error_type, shutdown). Updated `LoopManager._parse_daemon_line()` with a fast path that checks `text.startswith("[EVENT] ")` and parses JSON directly via the new `_handle_event()` method; regex fallback is fully preserved. Added 10 unit tests for structured event parsing and fallback behavior.

### [BUG-004] Zsh completion filter excludes all long flags

- **Category:** bug
- **Priority:** Medium
- **Impact:** Medium — auto-generated zsh completions missing ~80% of available flags
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/cli.py` ~line 119
- **Description:** `_generate_completion()` filters flags with `if not f.startswith("--")` when building `_zsh_flags`. This is inverted — it discards all long flags (e.g., `--goal`, `--max-iterations`), producing completions with only short flags (`-g`, `-m`). Auto-generated zsh completions are missing ~80% of available flags.
- **Research Notes:** Fix the filter condition to exclude only help flags (`--help`, `-h`) instead of all `--` flags. Add a test case for completion output verification.

### [BUG-005] `classify_error()` misses common timeout/network patterns

- **Category:** bug
- **Priority:** High
- **Impact:** Medium — misclassified errors trigger wrong recovery strategies
- **Effort:** small
- **Status:** done
- **Affected Files:** `pi_loop/error_utils.py:classify_error()`
- **Description:** `classify_error()` checked for `"timeout"` and `"timed out"` but missed `"timedout"`, `"time_out"`, `"read timed out"`, `"connection timed out"`. Network category missed `"name or service not known"`, `"temporary failure"`, `"name resolution"`, `"no address"`, `"protocol error"`, `"ssl_error"`, `"handshake"`. Misclassified errors trigger wrong recovery strategies.
- **Research Notes:** ✅ Resolved — added all missing patterns and tested.

### [BUG-006] JSON extraction breaks on string-literals with braces

- **Category:** bug
- **Priority:** Medium
- **Impact:** Medium — corrupted JSON extraction when pi output contains braces in strings
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/file_utils.py:extract_json_from_output()`
- **Description:** `extract_json_from_output()` uses simple brace-depth counting (`{` = +1, `}` = -1) with no awareness of JSON string literals. If pi output contains `{` or `}` inside a quoted JSON string (e.g., `"output": "if (x) { y }"`), the brace counter desyncs and extraction returns a partial or corrupted JSON object. Both forward and reverse scan strategies are affected.
- **Research Notes:** Add string-literal awareness during brace scanning: skip counts inside quoted strings (respecting escape sequences). Add test cases with braces-in-strings.

### [BUG-007] `error_recovery.py` had dead calculation `150 // 100`

- **Category:** bug
- **Priority:** Medium (resolved)
- **Impact:** Low — evaluated to `1` instead of `1.5`, slightly less effective timeout scaling
- **Effort:** small
- **Status:** done
- **Affected Files:** `pi_loop/error_recovery.py` line 38
- **Description:** `error_recovery.py` had `150 // 100` which evaluates to `1` (integer division). This was a leftover from a refactor where a timeout multiplier was supposed to be computed as a float. The intended behavior was `150 / 100 = 1.5`.
- **Research Notes:** ✅ Resolved — replaced with a module-level `_TIMEOUT_MULTIPLIER: float = 1.5` named constant.

### [BUG-008] CLI `main()` silently accepted invalid `--config` JSON keys

- **Category:** bug
- **Priority:** High
- **Impact:** Medium — typos in config silently ignored, defaults used instead
- **Effort:** small
- **Status:** done
- **Affected Files:** `pi_loop/cli.py`
- **Description:** `cli.py` applied arbitrary JSON keys to the argparse Namespace via `setattr(args, key, val)` with no validation. A typo like `"max-iterration"` silently created an unused attribute while `max_iterations` stayed at default.
- **Research Notes:** ✅ Resolved — added validation against known argparse dest names using difflib to suggest close matches for typos. Unknown keys are logged as WARNING and skipped.

### [BUG-009] Docstring in `preflight.py` placed after `if` block

- **Category:** bug
- **Priority:** Low
- **Impact:** Low — docstring invisible to `help()` and IDE tooltips
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/preflight.py` ~line 100
- **Description:** `preflight.py:~100`, the `check_disk_space` method has its docstring positioned after the function body's first `if` block instead of at the top of the method. This makes the docstring invisible to `help()` and IDE tooltips.
- **Research Notes:** Move the docstring to the first line of the method body.

### [BUG-010] `loop_manager.py` log file handle never rotates

- **Category:** bug
- **Priority:** Medium
- **Impact:** Medium — unbounded disk growth on long-running servers
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/loop_manager.py` (`_add_log`, `_close_log`)
- **Description:** `LoopManager._add_log()` opens a log file handle on startup and appends forever. There is no rotation, no size cap, no truncation. On a long-running server, this produces unbounded disk growth.
- **Research Notes:** Add file size check before appending (e.g., rotate at 100MB). Or use `RotatingFileHandler` from stdlib with a reasonable max size.

### [BUG-011] Heartbeat poll interval causes up-to-5s shutdown delay

- **Category:** bug
- **Priority:** Medium
- **Impact:** Medium — short iterations see doubled latency
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/heartbeat.py` ~line 67
- **Description:** `_monitor_heartbeat()` sleeps for `HEARTBEAT_POLL_INTERVAL` (5 seconds) between heartbeat checks. Any iteration completion is detected up to 5 seconds late because the poll cycle must complete before the next heartbeat check.
- **Research Notes:** Use `threading.Event.wait(timeout=interval)` with a set-able event for shutdown notification, reducing effective latency to near-zero while maintaining the poll interval.

### [BUG-012] File lock busy-waits with fixed 100ms sleep

- **Category:** bug
- **Priority:** Medium
- **Impact:** Low — unnecessary CPU wakeups under contention
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/file_utils.py` lines ~39-48
- **Description:** `FileLock.__enter__` busy-waits for a lock with `time.sleep(0.1)` — a fixed 100ms interval until the timeout expires. Under contention, this creates unnecessary CPU wakeups. No exponential backoff, no jitter.
- **Research Notes:** Implement exponential backoff starting at 10ms, doubling per retry, with ±20% random jitter, capped at ~1s max interval.

### [BUG-013] `status.py` uptime calculation was mathematically wrong

- **Category:** bug
- **Priority:** Critical
- **Impact:** High — status file always reported 0 uptime
- **Effort:** small
- **Status:** done
- **Affected Files:** `pi_loop/status.py`
- **Description:** `write_status()` computed uptime as `time.monotonic() - (time.time() - time.monotonic())` — a meaningless value. The `/proc/pid/stat` fallback path was never successfully used. The status file always reported 0 uptime.
- **Research Notes:** ✅ Resolved — replaced with `time.monotonic() - _process_start_time` where `_process_start_time` is set at module load time.

### [BUG-014] Fragile ISO datetime parsing uses `"Z" in started_at or "+" in started_at`

- **Category:** bug
- **Priority:** Low
- **Impact:** Low — fragile parsing of ISO 8601 timestamps
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/state.py` lines 44-54
- **Description:** Timezone-aware ISO datetime parsing uses `"Z" in started_at or "+" in started_at` — this is fragile. ISO 8601 timestamps may contain `+` in the timezone offset section or literally in the timestamp value itself.
- **Research Notes:** Use `datetime.fromisoformat()` with proper timezone handling. Python 3.11+ has improved ISO 8601 parsing.

### [BUG-015] `_execute_task` has 13-parameter signature with unused extracted params

- **Category:** bug
- **Priority:** Medium
- **Impact:** Medium — code complexity, suppressed lint warnings hide real issues
- **Effort:** medium
- **Status:** open
- **Affected Files:** `pi_loop/loop.py` (`_execute_task`), `pi_loop/config.py` (`LoopConfig`)
- **Description:** `_execute_task` accepts 71 individual parameters. The `LoopConfig` dataclass exists but `_execute_task` doesn't use it; instead, it extracts params individually. Unused extracted params like `cfg.max_idle_iterations` are collected but never actually used, with `# ruff: noqa: F841` suppressing the warnings project-wide.
- **Research Notes:** Refactor `_execute_task` to accept `LoopConfig` (or a subset config). Remove unused local assignments. Remove the module-level `noqa: F841` suppression.

### [BUG-016] `_get_cpu_percent()` has import-time side effect

- **Category:** bug
- **Priority:** Low
- **Impact:** Low — minor risk of `None` return on first API call
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/server.py` (`_get_cpu_percent`)
- **Description:** Module-level `for _i in range(2)` loop pre-warms `/proc/stat` at import time. If the file read fails on first pass, it breaks the loop but `_last_cpu_total` may remain `None`, causing first API call to return `None`.
- **Research Notes:** Move pre-warm to a lazy initialization pattern. Or handle `None` explicitly at the import level.

### [BUG-017] `read_ledger()` returns `None` on corruption without caller awareness

- **Category:** bug
- **Priority:** Medium
- **Impact:** Medium — callers may not handle `None` properly, causing downstream errors
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/state.py` (`read_ledger`)
- **Description:** `read_ledger()` returns `None` on corrupt ledger with only a quiet `except` — callers must handle `None`, but many don't check properly. This can lead to `AttributeError: 'NoneType' object has no attribute 'get'` in calling code.
- **Research Notes:** Consider returning an empty ledger dict instead of `None` (fail-open). Or raise a specific exception type that callers must handle.

---

## 🏗️ Architecture & Design

### [ARCH-001] Decompose `run_loop()` monolithic ~400-line function

- **Category:** architecture
- **Priority:** Critical
- **Impact:** Very High — blocks testing, refactoring, and extension of core loop logic
- **Effort:** xlarge
- **Status:** open
- **Affected Files:** `pi_loop/loop.py`
- **Description:** `run_loop()` in `loop.py` handles: subprocess spawning, iteration lifecycle, error classification, recovery adaptation, notification dispatch (desktop, HTTP callback, ntfy), dashboard HTML generation, goal evolution, convergence detection, cooldown handling, heartbeat management, ledger pruning, and git auto-commit. It has 60+ local variables and 20+ condition branches. The `# ruff: noqa: ARG001, F841` at the top acknowledges unused local assignments. Test coverage is ~19% because mocking 60+ variables is impractical. The function also has no outer try/except — if any part of the iteration cycle throws, the entire daemon crashes.
- **Research Notes:** Phase 1 (low-risk): Extract pure functions (convergence check, termination check, progress classification). Phase 2: Extract I/O-bound operations (notification dispatcher, dashboard builder). Phase 3: Create `TaskExecutor`, `WorkerPool`, `ConvergenceDetector`, `NotificationDispatcher` classes. Each extraction should be a separate commit with characterization tests written before touching the code.

### [ARCH-002] Refactor `LoopConfig` god dataclass with 71 fields

- **Category:** architecture
- **Priority:** Critical
- **Impact:** High — single-responsibility violation, maintenance burden
- **Effort:** large
- **Status:** open
- **Dependencies:** ARCH-001 (recommended — loop changes touch config heavily)
- **Affected Files:** `pi_loop/config.py` (LoopConfig dataclass, lines ~68-179), `pi_loop/loop.py`, `pi_loop/cli.py`
- **Description:** `LoopConfig` is a single dataclass spanning iteration control, worker config, git settings, notifications, archiving, logging, safety, and advanced options. It violates the Single Responsibility Principle. `from_args()` imports `dataclasses._MISSING_TYPE` — a private API. When a field is added, all consumers must be checked for compatibility.
- **Research Notes:** Split into focused configs: `IterationConfig`, `WorkerConfig`, `GitConfig`, `NotificationConfig`, `ArchiveConfig`, `SafetyConfig`. Compose in a top-level `AppConfig`. Keep backward compatibility via `__getattr__` delegation to child configs.

### [ARCH-003] Extract `TaskExecutor` from `_execute_task()`

- **Category:** architecture
- **Priority:** High
- **Impact:** High — isolate all subprocess concerns, make execution path independently testable
- **Effort:** medium
- **Status:** open
- **Dependencies:** ARCH-001
- **Affected Files:** `pi_loop/loop.py` (`_execute_task`), new `pi_loop/executor.py`
- **Description:** `_execute_task()` (~200 lines) handles subprocess spawning, streaming NDJSON, JSON extraction, error classification, retry logic, and result building. It returns a complex result dict with keys like `output`, `error`, `duration_seconds`, `classification`, and `summary` — none of which are documented. Extracting this into a dedicated `TaskExecutor` class would isolate all subprocess concerns and make the execution path independently testable.
- **Research Notes:** Create `pi_loop/executor.py` with `TaskExecutor` class. Move `_execute_task()` body into it, replacing result dict with a typed dataclass. The class can be tested without mocking `run_loop`'s 60 locals.

### [ARCH-004] Abstract `/proc` dependency for cross-platform support

- **Category:** architecture
- **Priority:** High
- **Impact:** Medium — daemon is currently Linux-only
- **Effort:** large
- **Status:** open
- **Affected Files:** `pi_loop/system_utils.py`, `pi_loop/status.py`, `web_app/server.py`
- **Description:** `system_utils.py` reads `/proc/[pid]/status` and `/proc/[pid]/stat` for CPU/memory tracking. `server.py` reads `/proc/stat` and `/proc/meminfo`. `status.py` uses `os.sysconf_names["SC_CLK_TCK"]`. All of these are Linux-specific. The daemon cannot run on macOS or BSD without errors.
- **Research Notes:** Abstract a `SystemResourceProvider` interface with `LinuxProvider` (current), `macOSProvider` (using `sysctl`/`ps`), and `NoopProvider` (returns defaults). Auto-detect platform at import time. Mark platform-specific tests.

### [ARCH-005] Add explicit state machine abstraction for loop states

- **Category:** architecture
- **Priority:** High
- **Impact:** High — prevents ad-hoc state management, enables new states (draining, backoff)
- **Effort:** medium
- **Status:** open
- **Dependencies:** ARCH-001
- **Affected Files:** `pi_loop/loop.py`, new `pi_loop/state_machine.py`
- **Description:** The main loop is a `while True` with ad-hoc condition checks for shutdown, pause, cooldown, etc. States (running, paused, cooldown, error, stopping) are managed via scattered boolean flags and sentinel file checks. There's no single source of truth for current state, making it hard to add new states (draining, backoff, maintenance). The status is stored as a raw string in a dict — no enum, no transition guards.
- **Research Notes:** Introduce a `LoopStateMachine` class with explicit enum states and defined transitions. Each state has `enter()` and `exit()` hooks. Replace scattered `if` checks with `state_machine.transition_to()` calls.

### [ARCH-006] Add dependency injection for testability

- **Category:** architecture
- **Priority:** High
- **Impact:** High — all modules import globals directly, testing requires extensive patching
- **Effort:** xlarge
- **Status:** open
- **Affected Files:** `pi_loop/` (all modules), `web_app/` (all modules)
- **Description:** All modules import globals directly rather than accepting dependencies. Testing requires extensive `unittest.mock` patching of module-level variables. There is no dependency injection framework or pattern. Module-level mutable globals exist in 8+ modules (`_daemon_logger` in `file_utils.py`, `_shutdown_requested` in both `loop.py` and `heartbeat.py`, `_max_output_chars_global` in `functions.py`, `_API_KEY` in `server.py`, global `colorizer` singleton in `color_utils.py`).
- **Research Notes:** Start with classes that accept dependencies via constructor injection. Phase 1: extract the worst offenders (mutable globals) into configurable parameters. Phase 2: create an `AppContext` or use simple dependency injection. Phase 3: remove module-level mutable state.

### [ARCH-007] Tight coupling between `cli.py` and `loop.py`

- **Category:** architecture
- **Priority:** Medium
- **Impact:** Medium — two representations of same state make maintenance error-prone
- **Effort:** medium
- **Status:** open
- **Affected Files:** `pi_loop/cli.py`, `pi_loop/loop.py`
- **Description:** CLI constructs a raw dict from args and passes it to `run_loop` alongside `LoopConfig` — two representations of the same state. `cli.py` has 20+ lines of `state["key"] = args.key` manual assignments instead of `state.update(vars(args))` or using `LoopConfig.from_args()`.
- **Research Notes:** Use `LoopConfig.from_args()` consistently. Remove the raw dict path. The 20+ manual assignments should become a single bulk method.

### [ARCH-008] Parallel worker model is all-or-nothing

- **Category:** architecture
- **Priority:** Medium
- **Impact:** Medium — race conditions when one worker hangs
- **Effort:** large
- **Status:** open
- **Affected Files:** `pi_loop/loop.py` (worker management)
- **Description:** Workers are all-or-nothing — if one hangs, the heartbeat kills just that worker, but other workers' results may be discarded or cause race conditions. There's no partial progress handling or individual worker lifecycle management.
- **Research Notes:** Implement per-worker state tracking. When a worker is killed, preserve results from completed workers. Add a worker result aggregator that handles partial completion.

### [ARCH-009] `web_app/server.py` imports internal module layout of `pi_loop.config_file`

- **Category:** architecture
- **Priority:** Low
- **Impact:** Low — creates fragile cross-package dependency
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/server.py`, `pi_loop/config_file.py`
- **Description:** `web_app/server.py` imports `pi_loop.config_file.CONFIG_PATH` directly. This creates a dependency on `config_file`'s internal module layout. If the constant is renamed or moved, the web app breaks silently.
- **Research Notes:** Re-export `CONFIG_PATH` through `pi_loop/__init__.py` or create a public API in `pi_loop` that the web app uses.

### [ARCH-010] Two config systems: `config.py` (constants) vs `config_file.py` (user config)

- **Category:** architecture
- **Priority:** Medium
- **Impact:** Medium — naming overlap is confusing for new developers
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/config.py`, `pi_loop/config_file.py`
- **Description:** `config.py` contains `LoopConfig` dataclass and constants. `config_file.py` reads JSON config from disk. The naming overlap (`config` vs `config_file`) with different purposes (constants vs user settings) is confusing. Additionally, `STATUS_FILE_DEFAULT` in `status.py` is calculated at import time via `os.path.join(_get_data_dir(), "loop-status.json")` — fragile since it reads `os.environ` at import.
- **Research Notes:** Rename to clarify: `loop_config.py` for `LoopConfig`, `user_config.py` for config file management. Move `STATUS_FILE_DEFAULT` to lazy initialization.

### [ARCH-011] No API versioning on web endpoints

- **Category:** architecture
- **Priority:** Low
- **Impact:** Low — all endpoints under bare `/api/` with no version prefix
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/server.py`
- **Description:** All API endpoints are under `/api/` with no version prefix (`/api/v1/`). Any future breaking changes to endpoint schemas would break existing clients without clear signaling.
- **Research Notes:** Mount a versioned router at `/api/v1/`. Keep bare `/api/` endpoints as deprecated aliases pointing to v1.

---

## 🧪 Testing & Quality

### [TEST-001] Zero integration tests for core pi subprocess lifecycle

- **Category:** testing
- **Priority:** Critical
- **Impact:** Very High — pi binary changes go undetected until production
- **Effort:** xlarge
- **Status:** open
- **Dependencies:** ARCH-001, ARCH-003 (both recommended for easier isolation)
- **Affected Files:** `tests/integration/` (new), `tests/integration/conftest.py`, `tests/integration/mock_pi.sh`
- **Description:** The core value proposition (subprocess task execution via `pi`) has zero end-to-end verification. All 481+ tests are unit tests that mock subprocess calls. A `pi` binary change (flag rename, output format change, mode=json breaking change) goes undetected until production. The NDJSON streaming, `[TERM]` prefix generation, heartbeat writing during execution, and timeout enforcement are never tested with real subprocess behavior.
- **Research Notes:** Create `tests/integration/` directory. Build a `mock_pi.sh` script that emits realistic NDJSON output. Test: single iteration success, convergence detection, error recovery with injected failures, sentinel stop/pause, multi-worker patterns. Mark integration tests with `@pytest.mark.integration`. Run as a separate CI job (not with `make test`).

### [TEST-002] `file_watcher.py` has zero test coverage

- **Category:** testing
- **Priority:** High
- **Impact:** High — file watching functionality entirely untested
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/file_watcher.py`, `tests/test_file_watcher.py` (new)
- **Description:** `FileWatcherTrigger` class with 5 methods and polling logic has no dedicated test file. The file watching functionality (polling directory changes, triggering iterations) is entirely untested. With 0% coverage, any regression in file watching goes undetected.
- **Research Notes:** Create `tests/test_file_watcher.py`. Use `tmp_path` fixtures to create temporary directory structures. Test: directory creation/deletion triggers, file modification detection, polling interval behavior, edge cases (empty directory, permission errors).

### [TEST-003] `loop.py` core loop only ~19% covered

- **Category:** testing
- **Priority:** High
- **Impact:** High — any refactoring risks undetected regressions
- **Effort:** medium
- **Status:** open
- **Dependencies:** ARCH-001 (easier after decomposition, but can start now)
- **Affected Files:** `pi_loop/loop.py`, `tests/test_loop.py`
- **Description:** Only `_execute_task`, `_evolve_goal`, `_build_dashboard_html`, and `_request_shutdown` are tested. The main `run_loop()` function (435 lines), sentinel polling, worker management, convergence detection, checkpointing, and cooldown enforcement are untested. The `_shutdown()` graceful shutdown sequence is also untested.
- **Research Notes:** Start with exit-early conditions (test that sentinel file causes clean shutdown, max iterations stops the loop, convergence detected, idle limit enforced). Then test iteration lifecycle with mocked `_execute_task`. Write characterization tests before refactoring (capture current behavior, then refactor against captured behavior).

### [TEST-004] `cli.py` entry point only ~12% covered

- **Category:** testing
- **Priority:** Medium
- **Impact:** Medium — CLI dispatch, help topics, doctor output, healthcheck all untested
- **Effort:** medium
- **Status:** open
- **Affected Files:** `pi_loop/cli.py`, `tests/test_cli.py`
- **Description:** Only `_create_parser()` is tested in `test_cli.py`. The `main()` function (~200 lines with 14+ introspection flags, config loading, daemon dispatch) is untested. Command dispatch, help topic rendering, doctor output, healthcheck formatting, status display — all have no test coverage.
- **Research Notes:** Refactor `main()` to accept an argument list for easier testing. Test each introspection flag independently (`--status`, `--doctor`, `--preflight`, `--list-flags`, `--explain`, `--help-topic`). Test config file loading with valid/invalid/missing files.

### [TEST-005] JSON extraction needs string-literal test cases

- **Category:** testing
- **Priority:** Medium
- **Impact:** Medium — edge cases in JSON extraction untested
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/file_utils.py:extract_json_from_output()`, `tests/test_file_utils.py`
- **Description:** `extract_json_from_output()` has test coverage for basic JSON extraction but no test cases for JSON containing braces inside string values, nested objects with >5 levels, empty objects, or malformed JSON with unmatched braces.
- **Research Notes:** Add parametrized test cases covering: braces-in-strings, deeply nested JSON, empty JSON objects, JSON with unicode escapes, JSON with escaped quotes, truncated JSON, and output with multiple JSON objects.

### [TEST-006] `server.py` needs coverage for SSE, error handlers, remaining API routes

- **Category:** testing
- **Priority:** Medium
- **Impact:** Medium — SSE streaming, config CRUD, monitoring endpoints poorly tested
- **Effort:** medium
- **Status:** open
- **Affected Files:** `web_app/server.py`, `tests/test_server.py`
- **Description:** `web_app/server.py` has only ~55% coverage. Auth middleware and rate limiting are well-tested, but SSE streaming, config CRUD endpoints, system monitoring endpoints, CORS handling, and error handlers have limited or no test coverage. The `_status_poller()` SSE background task is not directly tested.
- **Research Notes:** Use `TestClient` from Starlette to test each API route with valid/auth/invalid requests. Test SSE stream initialization and heartbeat events. Test CORS header presence on all responses. Test 404, 405, and 500 error handlers.

### [TEST-007] `rate_limiter.py` needs direct unit tests

- **Category:** testing
- **Priority:** Medium
- **Impact:** Medium — rate limiter only tested indirectly through server tests
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/rate_limiter.py`, `tests/test_rate_limiter.py` (new)
- **Description:** `SlidingWindowRateLimiter` (4 async methods) is only tested indirectly through `test_server.py`. There are no direct unit tests for: rate limit check logic, time window rolling, remaining count calculation, reset behavior, or concurrent access under `asyncio.Lock`.
- **Research Notes:** Create `tests/test_rate_limiter.py` with `pytest-asyncio` tests. Use `asyncio.Lock` directly (no patching needed). Test: single IP stays under limit, burst exceeds limit, window rolls correctly, multiple IPs tracked independently, remaining count accuracy.

### [TEST-008] `env_utils.py` has disproportionately low coverage despite being largest module

- **Category:** testing
- **Priority:** High
- **Impact:** Medium — validation edge cases and .env parsing error paths untested
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/env_utils.py`, `tests/test_env_utils.py`
- **Description:** At ~528 lines, `env_utils.py` is the largest module in `pi_loop/` with functions for env var management, .env file parsing, variable validation, fuzzy typo detection via `difflib`, and 100+ `KNOWN_ENV_VARS` entries. Despite its size and complexity, coverage is only 75%, leaving validation edge cases and .env parsing error paths untested.
- **Research Notes:** Add parametrized tests for: .env file parsing with various formats (quoted values, comments, blank lines, variable expansion), fuzzy matching edge cases (short strings, empty input, special characters), validation of all 100+ known env vars, error handling (missing files, permission errors, malformed content).

### [TEST-009] Git utils tested only through mock patches

- **Category:** testing
- **Priority:** Medium
- **Impact:** Medium — `_capture_git_state` and `_git_auto_commit` never tested with actual git repo
- **Effort:** medium
- **Status:** open
- **Affected Files:** `pi_loop/git_utils.py`, `tests/test_git_utils.py`
- **Description:** `_capture_git_state` and `_git_auto_commit` are tested only through `unittest.mock` patches. There is no integration test with an actual git repository. Edge cases (dirty working tree, detached HEAD, no remote, git not installed) are untested.
- **Research Notes:** Use `tmp_path` with `git init` to create test repositories. Test: clean state capture, dirty state capture, auto-commit with changes, auto-commit with no changes (no-op), git not installed error handling.

### [TEST-010] `system_utils.py` edge case /proc parsing untested

- **Category:** testing
- **Priority:** Low
- **Impact:** Low — edge case /proc formats could silently return incorrect data
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/system_utils.py`, `tests/test_system_utils.py`
- **Description:** `get_system_usage()` reads `/proc` files. Tested with mocks, but the parsing logic for edge case `/proc` formats (missing fields, unusual values, empty files) is uncovered.
- **Research Notes:** Add test cases for malformed `/proc` content, missing fields, and unusual but valid formats.

### [TEST-011] Test files are very large and should be split

- **Category:** testing
- **Priority:** Medium
- **Impact:** Low — maintainability and readability
- **Effort:** medium
- **Status:** open
- **Affected Files:** `tests/test_integration.py` (95KB), `tests/test_integration_gaps.py` (62KB), `tests/test_integration_remaining.py` (53KB)
- **Description:** Test files are very large — `test_integration.py` is 95KB, `test_integration_gaps.py` is 62KB, `test_integration_remaining.py` is 53KB. These should be split into focused test modules by feature area.
- **Research Notes:** Split into: `test_integration_loop.py`, `test_integration_server.py`, `test_integration_notifications.py`, etc. Each focused module has a clear responsibility.

### [TEST-012] Missing conftest fixtures for `loop.py` testing

- **Category:** testing
- **Priority:** Medium
- **Impact:** Medium — no shared fixtures for `run_loop` or `_execute_task` with subprocess mocking
- **Effort:** small
- **Status:** open
- **Affected Files:** `tests/conftest.py`
- **Description:** No `conftest.py` contains fixtures for `loop.py`'s `run_loop` or `_execute_task` with subprocess mocking. Each test file that needs these must replicate setup logic.
- **Research Notes:** Add shared fixtures: `mock_pi_subprocess`, `mock_loop_config`, `mock_ledger`, `mock_file_watcher`, `sample_iteration_result`.

### [TEST-013] No web UI frontend tests

- **Category:** testing
- **Priority:** Medium
- **Impact:** Medium — web UI (38KB JS) has zero test coverage
- **Effort:** large
- **Status:** open
- **Affected Files:** `web_app/static/app.js`, `web_app/static/index.html`, `web_app/static/style.css`
- **Description:** The static frontend (`index.html`, `app.js` at ~38KB, `style.css`) has no tests — no Selenium, no Playwright, no unit tests for the JavaScript application logic. All state management, DOM manipulation, SSE client handling, and UI rendering runs without any automated verification.
- **Research Notes:** Start with lightweight headless browser tests (Playwright). Test: dashboard renders correctly, SSE updates propagate to DOM, theme toggle works, auth flow works, control buttons dispatch correct API calls.

### [TEST-014] `_build_test_app()` in test_auth.py duplicates middleware logic

- **Category:** testing
- **Quality:** Low — duplicated code creates maintenance burden
- **Effort:** small
- **Status:** open
- **Affected Files:** `tests/test_auth.py`
- **Description:** The `_build_test_app()` in `test_auth.py` duplicates middleware logic from `server.py` instead of importing it. If the middleware stack changes, this test helper must be updated independently.
- **Research Notes:** Import and reuse the middleware factory from `server.py`. This ensures tests always reflect the actual middleware configuration.

### [TEST-015] `config_file.py` has minimal test coverage

- **Category:** testing
- **Priority:** Medium
- **Impact:** Medium — config file backup/corruption scenarios untested
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/config_file.py`, `tests/test_config_file.py`
- **Description:** Only basic load/save with small tests. The backup strategy, atomic write, corruption recovery, and permission error paths are untested.
- **Research Notes:** Add tests for: backup file created correctly, recovery from corrupted config, permission denied, disk full, concurrent access.

---

## 🔧 Tooling & Developer Experience

### [TOOL-001] Mypy is configured but non-gating in CI (resolved)

- **Category:** tooling
- **Priority:** High
- **Impact:** High — type errors now actually fail CI
- **Effort:** small
- **Status:** done
- **Affected Files:** `Makefile` (mypy target), `.github/workflows/ci.yml`
- **Description:** Both `lint-all` and `mypy` Makefile targets suppressed errors with `2>/dev/null; true`. CI ran `make mypy` but never failed — any type error passed silently.
- **Research Notes:** ✅ Resolved — removed error suppression, fixed existing mypy errors, wired into CI as gating step.

### [TOOL-002] Pre-commit duality: `.pre-commit-config.yaml` and `.githooks/pre-commit` are independent

- **Category:** tooling
- **Priority:** Medium
- **Impact:** Medium — inconsistent behavior depending on which system is active
- **Effort:** small
- **Status:** open
- **Affected Files:** `.pre-commit-config.yaml`, `.githooks/pre-commit`, `.githooks/README.md`
- **Description:** There are two independent pre-commit systems: `.pre-commit-config.yaml` (used by `pre-commit` tool, runs ruff + file checks) and `.githooks/pre-commit` (bash script, also runs ruff check+format on staged files). The `.githooks/README.md` describes a different hook (shell completion regeneration) than what the script actually does (ruff linting). Contributors get inconsistent behavior depending on which system they activate.
- **Research Notes:** Pick one system and remove the other. Either: (a) use `pre-commit` tool exclusively (preferred — more maintainable) and delete `.githooks/pre-commit`, or (b) keep the bash script and delete `.pre-commit-config.yaml`. Document the chosen approach in CONTRIBUTING.md.

### [TOOL-003] No `py.typed` marker for downstream type checking (resolved)

- **Category:** tooling
- **Priority:** Low
- **Impact:** Low — PEP 561 compliance
- **Effort:** small
- **Status:** done
- **Affected Files:** `pi_loop/py.typed`, `web_app/py.typed`
- **Description:** Neither `pi_loop/` nor `web_app/` had a `py.typed` marker file. PEP 561 compliance was missing.
- **Research Notes:** ✅ Resolved — added empty `py.typed` to both `pi_loop/` and `web_app/` packages.

### [TOOL-004] No `.editorconfig` for cross-editor consistency (resolved)

- **Category:** tooling
- **Priority:** Low
- **Impact:** Low — cross-editor consistency
- **Effort:** small
- **Status:** done
- **Affected Files:** `.editorconfig`
- **Description:** There was no `.editorconfig` file for cross-editor consistency.
- **Research Notes:** ✅ Resolved — added `.editorconfig` with `indent_style = space`, `indent_size = 4`, `trim_trailing_whitespace = true`, `insert_final_newline = true`, `max_line_length = 120`, `end_of_line = lf`, and YAML/JSON overrides.

### [TOOL-005] Add coverage config section to `pyproject.toml`

- **Category:** tooling
- **Priority:** Low
- **Impact:** Low — consistent coverage behavior across environments
- **Effort:** small
- **Status:** open
- **Affected Files:** `pyproject.toml`
- **Description:** Coverage settings are not centralized in `pyproject.toml`. The `[tool.coverage.run]` section should define source paths and omit patterns so that `pytest --cov` has consistent behavior across environments.
- **Research Notes:** Add `[tool.coverage.run]` section with `source = ["pi_loop", "web_app"]` and `omit = ["*/tests/*", "*/__main__.py"]`. Add `[tool.coverage.report]` with `fail_under = 65`.

### [TOOL-006] Pre-commit hook auto-regenerates shell completion scripts

- **Category:** tooling
- **Priority:** Low
- **Impact:** Low — slightly slows every commit, but ensures completions stay fresh
- **Effort:** small
- **Status:** open
- **Affected Files:** `.git/hooks/pre-commit`, `scripts/completion/`
- **Description:** The pre-commit hook regenerates shell completion scripts (`bash` and `zsh`) on every commit by running `python3 -m hermes_loop --completion-script bash/zsh`. This adds overhead to every commit. Consider moving to a less frequent regeneration schedule (e.g., only when files change).
- **Research Notes:** Track file modification times and only regenerate when relevant source files change. Or move to a `make completions` target that's run manually.

---

## ⚡ Performance

### [PERF-001] Dashboard HTML rebuilt from scratch every iteration

- **Category:** performance
- **Priority:** Medium
- **Impact:** Medium — O(n) rebuilds, O(n²) total data processed
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/loop.py` (`_build_dashboard_html`)
- **Description:** `_build_dashboard_html()` reconstructs the entire 50-iteration HTML table every iteration, including serializing all iteration records to HTML strings. Fine for current scale (<100 iterations), but O(n) in iterations and O(n²) in total data processed across all calls.
- **Research Notes:** Implement incremental rendering: only append new rows instead of rebuilding. Cap the total rows to a configurable limit (currently hardcoded at 50). Consider switching to client-side rendering (web API provides JSON, JS renders).

### [PERF-002] `file_watcher.py` uses full directory scan with `sorted(rglob("*"))`

- **Category:** performance
- **Priority:** Medium
- **Impact:** Medium — O(n log n) scan on every poll for large directories
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/file_watcher.py`
- **Description:** `FileWatcherTrigger.check_change()` calls `sorted(p.rglob("*"))` which scans the entire directory tree and sorts all entries — O(n log n) where n is the number of files. For large source trees (e.g., a monorepo with node_modules), this is slow on every poll. No `.gitignore` filtering and no watch limit.
- **Research Notes:** Filter `rglob` to relevant file patterns (`.py`, `.md`, `.yaml`). Use `os.stat` mtime comparison instead of full content hashing. Consider adding `watchdog` as optional dependency for OS-level file system notifications.

### [PERF-003] SSE status poller runs every 2 seconds unconditionally

- **Category:** performance
- **Priority:** High
- **Impact:** Medium — unnecessary I/O even when nothing changed
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/server.py` (~line 225)
- **Description:** `_status_poller()` reads the entire JSON ledger from disk every 2 seconds and broadcasts to all SSE clients. This creates unnecessary I/O even when nothing has changed. With 0 connected SSE clients, the poller continues reading the ledger and generating events.
- **Research Notes:** Check ledger file mtime before reading — skip if unchanged since last read. Skip the entire poll cycle when `_sse_clients` is empty. Make poll interval configurable.

### [PERF-004] Log tag colorization applies 20+ regex substitutions per log call

- **Category:** performance
- **Priority:** Low
- **Impact:** Low — unnecessary CPU for high-frequency logging
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/file_utils.py` (`_colorize_log_tags`, `_tag_color_map`)
- **Description:** `_colorize_log_tags()` iterates over 20+ regex patterns and applies `re.sub()` for each one on every log message. For high-frequency log messages, this is wasteful — most patterns don't match but still incur regex compilation and matching overhead.
- **Research Notes:** Pre-compile all regex patterns at module load time. Use a single-pass scanner instead of sequential substitutions. Only apply colorization when output is a TTY.

### [PERF-005] JSON extraction does two full scans of output text

- **Category:** performance
- **Priority:** Low
- **Impact:** Low — O(2n) scanning of output text
- **Effort:** small
- **Status:** open
- **Dependencies:** BUG-006
- **Affected Files:** `pi_loop/file_utils.py:extract_json_from_output()`
- **Description:** `extract_json_from_output()` first attempts a reverse scan (building `json_chars` with repeated list `insert(0, ch)` — O(n²)). If that fails, it falls back to a forward scan. For large outputs with no JSON, every character is processed twice with O(n²) insert in the first pass.
- **Research Notes:** Use a single forward pass with stack-based brace tracking (instead of counter + `insert(0, ch)`). Fix the string-literal awareness bug (BUG-006) at the same time. Eliminate the reverse-scan fallback.

### [PERF-006] Ledger I/O on every iteration cycle grows unboundedly

- **Category:** performance
- **Priority:** Medium
- **Impact:** Medium — full JSON dump + atomic replace on every iteration
- **Effort:** medium
- **Status:** open
- **Affected Files:** `pi_loop/state.py` (`write_ledger`), `pi_loop/loop.py`
- **Description:** `write_ledger()` does a full JSON dump + atomic file replace on every single iteration. For long-running daemons, this means writing the entire iteration history (which grows unboundedly without `--keep-iterations`) to disk each cycle. The iteration list grows without a maximum unless explicitly configured.
- **Research Notes:** Implement incremental ledger updates (append-only log format with periodic compaction). Enforce a maximum iteration count in the ledger by default.

### [PERF-007] `/api/iterations` reverses full iteration list in memory per request

- **Category:** performance
- **Priority:** Low
- **Impact:** Low — temporary list copy for large ledgers
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/server.py` (`/api/iterations` endpoint)
- **Description:** Paginated endpoint reverses the full iteration list in memory per request. For large ledgers (10K+ iterations), this creates a temporary list copy.
- **Research Notes:** Add server-side pagination with offset/limit. Only load and reverse the requested page instead of the full list.

### [PERF-008] `_build_progressive_context()` concatenates unbounded context string

- **Category:** performance
- **Priority:** Low
- **Impact:** Low — context string grows unboundedly across iterations
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/loop.py` (`_build_progressive_context`)
- **Description:** `_build_progressive_context()` concatenates `summaries[-3:]` using `' | '.join(recent)` — context string grows unboundedly across iterations. No truncation of the progressive context.
- **Research Notes:** Add a maximum context length parameter. Truncate or summarize older context entries when the limit is exceeded.

### [PERF-009] `glob.glob()` in `_cleanup_stale_heartbeats()` called at startup

- **Category:** performance
- **Priority:** Low
- **Impact:** Low — one-time startup cost
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/heartbeat.py`
- **Description:** `_cleanup_stale_heartbeats()` uses `glob.glob()` to find stale heartbeat files at startup. This is acceptable (one-time), but could be slow if the temp directory has many files.
- **Research Notes:** No action needed unless this becomes a bottleneck. Document the one-time nature in a comment.

---

## 🔒 Security

### [SEC-001] `http_callback` URL scheme validation missing (resolved)

- **Category:** security
- **Priority:** Critical
- **Impact:** High — file:// URLs could read local files
- **Effort:** small
- **Status:** done
- **Affected Files:** `pi_loop/loop.py`
- **Description:** `loop.py` invoked `urllib.request.urlopen()` on a user-configurable `http_callback` URL with no scheme validation. A `file://` URL could read local files. A `data://` URL could trigger unexpected behavior. Bandit flagged this as B310.
- **Research Notes:** ✅ Resolved — added `urlparse` validation that restricts schemes to `http` and `https` only. Invalid schemes are logged at WARNING level and the callback is skipped.

### [SEC-002] `.env` not in `.gitignore` (currently commented out)

- **Category:** security
- **Priority:** Medium
- **Impact:** Medium — defense-in-depth: secrets could be committed
- **Effort:** small
- **Status:** open
- **Affected Files:** `.gitignore`
- **Description:** The `.gitignore` file has `.env` commented out with the note "config_file used instead." While the project does use JSON config files, if a developer creates a `.env` file locally with secrets (API keys, callback secrets), those secrets would be committed to git.
- **Research Notes:** Uncomment the `.env` entry and add `.env.*` (covers `.env.local`, `.env.production`) as well. Add a comment explaining this is a safety net even though `.env` is not the primary config mechanism.

### [SEC-003] No HTTP security headers (resolved)

- **Category:** security
- **Priority:** Medium
- **Impact:** Medium — defense-in-depth
- **Effort:** small
- **Status:** done
- **Affected Files:** `web_app/server.py`
- **Description:** The FastAPI web server was missing Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, and X-XSS-Protection headers.
- **Research Notes:** ✅ Resolved — Added security headers middleware with restricted CSP, frame options, content type options, and XSS protection.

### [SEC-004] `PI_LOOP_API_KEY` read from `os.environ` on every request (resolved)

- **Category:** security
- **Priority:** Medium
- **Impact:** Medium — auth behavior could change if env var mutated
- **Effort:** small
- **Status:** done
- **Affected Files:** `web_app/server.py`
- **Description:** The `api_key_auth` middleware read `PI_LOOP_API_KEY` from `os.environ` on every HTTP request. If the env var changed after startup, auth behavior changed without warning.
- **Research Notes:** ✅ Resolved — `main()` now reads `PI_LOOP_API_KEY` once at startup into a module-level `_API_KEY` constant. The middleware uses `_API_KEY` directly, with a backward-compatible `os.environ.get()` fallback for tests. Startup logs whether auth is enabled or disabled.

### [SEC-005] `shell=True` on user-configurable error command (Bandit B602)

- **Category:** security
- **Priority:** High
- **Impact:** High — command injection risk if config file is compromised
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/loop.py` line 727
- **Description:** `loop.py:727` runs `subprocess.run(on_error_cmd, shell=True, timeout=30)` where `on_error_cmd` is user-configurable via `config.json` or `--on-error-cmd` flag. If an attacker gains write access to `~/.config/pi-loop/config.json`, they can execute arbitrary shell commands. The validation blocks certain metachars but still allows space-separated commands. Additionally, `on_error_cmd` is stored in plaintext in the config JSON file, and `config_file.py` creates the config with `0o644` permissions — world-readable.
- **Research Notes:** At minimum: (1) log the full command before execution at INFO level, (2) validate command length and character restrictions rigorously, (3) document the risk explicitly in README, (4) add a warning on startup when `on_error_cmd` is configured, (5) change config file permissions to `0o600`, (6) consider using `shlex.split()` + list form instead of `shell=True`.

### [SEC-006] No secrets scanner in CI

- **Category:** security
- **Priority:** Medium
- **Impact:** Medium — regression risk: secrets could be committed without detection
- **Effort:** small
- **Status:** open
- **Affected Files:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`
- **Description:** The CI pipeline has no secrets scanning. A developer could accidentally commit an API key, token, or password, and it would pass CI without detection. While no secrets are currently in the repo (verified), this is a regression risk.
- **Research Notes:** Add `truffleHog`, `ggshield`, or `detect-secrets` to CI. The simplest option is `detect-secrets` which has a pre-commit hook and CI integration.

### [SEC-007] No input sanitization on Goal in web UI

- **Category:** security
- **Priority:** Medium
- **Impact:** Medium — goal string passed directly to `pi` subprocess
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/server.py`, `web_app/static/app.js`
- **Description:** The `--goal` string from the web UI is passed directly to the `pi` subprocess as a CLI argument. While arg-parsed, malicious goal strings could potentially inject shell characters at the OS level depending on how `subprocess.Popen` handles the argv list.
- **Research Notes:** Validate goal input: reject or escape shell metacharacters. Add length limits for goal strings in the web UI. Apply the same validation in both web UI and CLI entry points.

### [SEC-008] Config file permissions set to 0o644 (world-readable)

- **Category:** security
- **Priority:** Medium
- **Impact:** Medium — config file may contain API keys, error commands
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/config_file.py`
- **Description:** `config_file.py` creates config at `~/.config/pi-loop/config.json` with default `0o644` via `os.open` — world-readable. The config file may contain API keys, callback URLs, or `on_error_cmd` shell commands.
- **Research Notes:** Change default permissions to `0o600` (owner read/write only). Add a note in README about securing the config directory.

### [SEC-009] `--yolo` flag bypass is undocumented

- **Category:** security
- **Priority:** Low
- **Impact:** Low — safety bypass mechanism with no documentation
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/config.py`, `pi_loop/cli.py`
- **Description:** The `--yolo` flag exists as a safety bypass mechanism. It's stored in state but its actual behavior is undocumented in code — what exactly does it bypass? No README mention, no docstring.
- **Research Notes:** Document exactly what `--yolo` bypasses. Consider removing or replacing with a more explicit flag (e.g., `--disable-safety-checks`) that clearly documents what's disabled.

### [SEC-010] CSP allows `data:` images which could enable XSS vectors

- **Category:** security
- **Priority:** Low
- **Impact:** Low — defense-in-depth
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/server.py`
- **Description:** The Content-Security-Policy header has `img-src 'self' data:` which allows data URIs for images. This could potentially enable some XSS vectors, though impact is minimal given the SPA is served locally.
- **Research Notes:** Remove `data:` from `img-src` if no images are loaded via data URIs. Otherwise, document why it's needed.

---

## 📚 Documentation

### [DOC-001] README missing Swagger UI link, screenshot, and pi version requirement

- **Category:** documentation
- **Priority:** Medium
- **Impact:** Medium — first things new users look for
- **Effort:** small
- **Status:** open
- **Affected Files:** `README.md`
- **Description:** README lacks: (1) link to auto-generated FastAPI `/docs` OpenAPI endpoint, (2) screenshot or preview of the web UI dashboard, (3) minimum required `pi` coding agent version, (4) note that `pi` must be on PATH. The `--no-convergence` flag listed in README doesn't exist in `parser.py` — the flag list is stale.
- **Research Notes:** Add a "Prerequisites" section with `pi` version requirement. Add a link to `/docs` after the web UI features section. Add a screenshot (or placeholder) of the dashboard. Audit the README flag list against actual parser.py flags.

### [DOC-002] Create CHANGELOG.md for release history

- **Category:** documentation
- **Priority:** Medium
- **Impact:** Medium — users cannot see what changed between versions
- **Effort:** medium
- **Status:** open
- **Affected Files:** `CHANGELOG.md` (new)
- **Description:** Despite having version `14.39.0` in `pyproject.toml` and `__init__.py`, and 213 commits with descriptive messages, there is no `CHANGELOG.md`. Users and developers cannot see what changed between versions, what bugs were fixed, or when features were added.
- **Research Notes:** Create `CHANGELOG.md` following Keep a Changelog format. Populate with entries from git history (conventional commits can be mapped to changelog sections). Add `make changelog` target for automated generation from git log.

### [DOC-003] Create CONTRIBUTING.md with dev setup guidance

- **Category:** documentation
- **Priority:** Medium
- **Impact:** High — new contributors have no onboarding guidance
- **Effort:** medium
- **Status:** open
- **Affected Files:** `CONTRIBUTING.md` (new)
- **Description:** There is no CONTRIBUTING.md. A new contributor has no guidance on: development setup, branch strategy, PR workflow, commit message conventions, coding standards, how to run tests, how to debug failures, or where to ask questions.
- **Research Notes:** Create CONTRIBUTING.md with sections: Development Setup, Project Structure, Running Tests, Coding Standards (link to pyproject.toml config), Commit Convention (Conventional Commits), PR Workflow, Issue Templates. Reference the existing Makefile targets.

### [DOC-004] Create SECURITY.md for vulnerability disclosure

- **Category:** documentation
- **Priority:** Medium
- **Impact:** Medium — no guidance for reporting vulnerabilities
- **Effort:** small
- **Status:** open
- **Affected Files:** `SECURITY.md` (new)
- **Description:** The project has security features (API-key auth, rate limiting, CORS, HMAC webhook signing) but no SECURITY.md. Security researchers or users who find vulnerabilities have no guidance on how to report them responsibly.
- **Research Notes:** Create SECURITY.md with: supported versions, reporting process (email or GitHub advisory), expected response timeline, and PGP key if applicable.

### [DOC-005] Missing docstrings for `run_loop()` and `_execute_task` return schema

- **Category:** documentation
- **Priority:** Medium
- **Impact:** Medium — maintainers must read implementation to understand function contract
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/loop.py`
- **Description:** `run_loop()` has no function-level docstring (the module docstring describes it briefly). `_execute_task` docstring describes NDJSON streaming but doesn't document the return dict keys (`output`, `error`, `duration_seconds`, `classification`, `summary`).
- **Research Notes:** Add a proper docstring to `run_loop()` describing parameters, preconditions, and behavior. Document `_execute_task` return dict keys in the existing docstring.

### [DOC-006] Missing inline docstrings for `set_max_output_chars` / `get_max_output_chars`

- **Category:** documentation
- **Priority:** Low
- **Impact:** Low — mutable global state needs clear documentation
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/functions.py` lines ~18, ~22
- **Description:** `functions.py` has two module-level functions (`set_max_output_chars`, `get_max_output_chars`) with zero docstrings. These manage mutable global state — exactly the kind of code that needs clear documentation about side effects.
- **Research Notes:** Add docstrings explaining what they do, what the default value is, and that they modify module-level global state (and why).

### [DOC-007] No documentation for `_ERROR_THRESHOLDS` design rationale

- **Category:** documentation
- **Priority:** Low
- **Impact:** Low — maintainers don't know why `network` has `stop: None`
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/config.py`
- **Description:** `_ERROR_THRESHOLDS` has no explanation of why `network` has `stop: None` (intentional "never stop" choice) vs other error types. Also, `_TIMEOUT_MULTIPLIER` docstring says "Evaluates to 1.5 (float), not 1 (integer)" — overly defensive, doesn't explain why 1.5 was chosen.
- **Research Notes:** Add comments explaining the rationale for each error threshold value. Explain the timeout multiplier choice.

### [DOC-008] No documentation for `extract_json_from_output()` strategy ordering

- **Category:** documentation
- **Priority:** Low
- **Impact:** Low — maintainers don't know why backward scan is tried first
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/file_utils.py`
- **Description:** `extract_json_from_output()` has no description of Strategy 1 vs Strategy 2 ordering or why backward scan is tried first.
- **Research Notes:** Add a doc comment explaining the two strategies, their trade-offs, and why backward scan is the primary approach.

### [DOC-009] No inline documentation in `app.js` (38KB JS file)

- **Category:** documentation
- **Priority:** Low
- **Impact:** Low — 38KB JS file with no comments
- **Effort:** medium
- **Status:** open
- **Affected Files:** `web_app/static/app.js`
- **Description:** The main frontend JavaScript file (~38KB) has no inline comments or documentation. All state management, SSE handling, DOM manipulation, and control logic is undocumented.
- **Research Notes:** Add JSDoc comments to major functions and event handlers. Document the SSE event protocol and expected data shapes.

### [DOC-010] `config_file.py` module docstring doesn't document JSON file format

- **Category:** documentation
- **Priority:** Low
- **Impact:** Low — users must read code to understand config file schema
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/config_file.py`
- **Description:** Module docstring mentions it does NOT require `.env` but doesn't document the `~/.config/pi-loop/config.json` file format, available keys, or example values.
- **Research Notes:** Add documented JSON schema (or link to README) in the module docstring.

---

## 🔄 CI/CD

### [CI-CD-001] Coverage reporting wired into CI (resolved)

- **Category:** ci-cd
- **Priority:** High
- **Impact:** High — coverage changes now tracked over time
- **Effort:** small
- **Status:** done
- **Affected Files:** `pyproject.toml`, `.github/workflows/ci.yml`
- **Description:** `pytest-cov` was installed but `make test` didn't use `--cov` flags. CI ran `make test` without coverage, so coverage could decrease without anyone noticing.
- **Research Notes:** ✅ Resolved — added `[tool.coverage.run]` and `[tool.coverage.report]` with `fail_under = 65` to `pyproject.toml`. The `make test` target uses `--cov=pi_loop --cov=web_app` flags.

### [CI-CD-002] Create release workflow (tag → build → publish)

- **Category:** ci-cd
- **Priority:** Medium
- **Impact:** Medium — no automated releases despite versioned software
- **Effort:** medium
- **Status:** open
- **Affected Files:** `.github/workflows/release.yml` (new), `Makefile`
- **Description:** Despite having version `14.39.0` and 213 commits, there are zero git tags and no release workflow. The version number exists only in source files. There is no automation to build the package, create a GitHub release, or publish to PyPI.
- **Research Notes:** Create `.github/workflows/release.yml` triggered by `v*` tag push. Steps: build distribution (`python -m build`), create GitHub Release with changelog, optionally publish to PyPI via `pypa/gh-action-pypi-publish`. Add `make release` target that tags and pushes.

### [CI-CD-003] Security scanning (bandit/safety) in CI (resolved)

- **Category:** ci-cd
- **Priority:** Medium
- **Impact:** Medium — security regressions now detected in CI
- **Effort:** small
- **Status:** done
- **Affected Files:** `.github/workflows/ci.yml`, `Makefile`
- **Description:** Bandit and Safety were installed as dev dependencies but were not run in CI. Security regressions (new CVEs, new vulnerable code patterns) went undetected in pull requests.
- **Research Notes:** ✅ Resolved — Added `make security` step to CI, including both bandit and safety scans. Bandit report uploaded as artifact.

### [CI-CD-004] Migrate Safety CLI from deprecated `check` to `scan`

- **Category:** ci-cd
- **Priority:** Low
- **Impact:** Low — deprecated command may stop working in future Safety versions
- **Effort:** small
- **Status:** open
- **Affected Files:** `Makefile` (security target)
- **Description:** `make security` uses `safety check -r requirements.txt -r requirements-dev.txt --continue-on-error`. The `check` command is deprecated in Safety 3.x; the recommended replacement is `safety scan`.
- **Research Notes:** Migrate to `safety scan -r requirements.txt -r requirements-dev.txt --continue-on-error`. Update Makefile and CI.

### [CI-CD-005] Create Docker build/release workflow

- **Category:** ci-cd
- **Priority:** Low
- **Impact:** Low — enables containerized deployment
- **Effort:** large
- **Status:** open
- **Dependencies:** CI-CD-002 (release workflow), FEAT-005 (Dockerfile)
- **Description:** The project has no Docker image building or publishing in CI. Dockerfiles exist only in stale git worktrees. Users who want to run pi-loop in a container must create their own Dockerfile.
- **Research Notes:** After creating a proper Dockerfile (FEAT-005), add a CI job that builds the Docker image and pushes to GitHub Container Registry (ghcr.io) on version tags.

### [CI-CD-006] Python 3.13 is `continue-on-error` in CI matrix

- **Category:** ci-cd
- **Priority:** Low
- **Impact:** Low — 3.13 failures don't block CI, could mask real issues
- **Effort:** small
- **Status:** open
- **Affected Files:** `.github/workflows/ci.yml`
- **Description:** Python 3.13 in the CI test matrix uses `continue-on-error`, meaning failures on 3.13 don't block the CI pipeline. While reasonable for a pre-release Python, this could mask real compatibility issues.
- **Research Notes:** Monitor 3.13 compatibility. When 3.13 is stable, remove `continue-on-error` and add it to the main test matrix.

---

## 🧹 Code Cleanup

### [CLEAN-001] Remove stale `hermes/hermes-*` worktree branches (resolved)

- **Category:** cleanup
- **Priority:** Low
- **Impact:** Low — cleaner git state
- **Effort:** small
- **Status:** done
- **Affected Files:** Git branches, `.worktrees/` directory
- **Description:** Three stale local branches (`hermes/hermes-bd038f68`, `hermes/hermes-d19eb158`, `hermes/hermes-edaf42c8`) remained from the hermes-agent era.
- **Research Notes:** ✅ Resolved — removed worktrees with `git worktree remove -f -f`, deleted branches with `git branch -D`, verified `main` unaffected.

### [CLEAN-002] Clean up noqa proliferation and unused imports in `loop.py`

- **Category:** cleanup
- **Priority:** Low
- **Impact:** Low — hides real lint issues
- **Effort:** small
- **Status:** open
- **Dependencies:** ARCH-001
- **Affected Files:** `pi_loop/loop.py`
- **Description:** `loop.py` has `# ruff: noqa: ARG001, F841` at module level to suppress unused argument and variable warnings. The `run_loop` function unpacks 20+ `cfg.*` attributes into local variables, many of which are never used. There are also dual imports — both `status.write_status` and `file_utils.write_status_file` are imported but only one is called.
- **Research Notes:** After decomposing `run_loop()` (ARCH-001), clean up unused local variable assignments. Remove the module-level `noqa` comment. Audit and deduplicate imports.

### [CLEAN-003] Replace complex nested conditionals with lookup table in `_suggest_actionable_fix()`

- **Category:** cleanup
- **Priority:** Medium
- **Impact:** Medium — simplifies maintenance and testability of 130-line function
- **Effort:** medium
- **Status:** open
- **Affected Files:** `pi_loop/error_utils.py` (`_suggest_actionable_fix`)
- **Description:** `_suggest_actionable_fix()` (~130 lines) uses deeply nested if/elif chains for every error-type × classification combination. Some branches return `None` after assembling tips that are then discarded (e.g., the regression branch). The complexity makes it hard to test exhaustively and hard to add new error patterns.
- **Research Notes:** Replace with a lookup table (dict mapping `(error_type, progress_classification) → suggestion_template`). Each entry is a standalone data item, easy to test and extend. This also makes the function pure and testable without mocks.

### [CLEAN-004] Duplicate status file writers: `status.py` and `file_utils.py`

- **Category:** cleanup
- **Priority:** Medium
- **Impact:** Medium — maintenance liability, adding a field requires updating both
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/status.py`, `pi_loop/file_utils.py:write_status_file()`, `pi_loop/loop.py`
- **Description:** `pi_loop/status.py:write_status()` writes a comprehensive status JSON file for the web UI. `pi_loop/file_utils.py:write_status_file()` writes a lightweight one-liner. Both write JSON status about the same daemon process but with different schemas and from different call sites inside `run_loop()`. Adding a field requires updating both — a maintenance liability. The function names also clash.
- **Research Notes:** Unify into a single writer. `status.py:write_status()` already has the richer schema. Have `file_utils.py` import and call it, or remove the lightweight variant and update `run_loop()` call sites.

### [CLEAN-005] `app.js` empty catch blocks review (already has logging)

- **Category:** cleanup
- **Priority:** High (resolved)
- **Impact:** Low — all catch blocks already have logging
- **Effort:** small
- **Status:** done
- **Affected Files:** `web_app/static/app.js`
- **Description:** Analysis reported 5+ empty `catch` blocks. Review confirmed all 14 `catch` blocks already have `console.warn` or `console.error` logging with descriptive labels.
- **Research Notes:** ✅ Resolved — no changes needed. All catch blocks have proper error logging.

### [CLEAN-006] Fix stale CLI help menu completions

- **Category:** cleanup
- **Priority:** Low
- **Impact:** Low — cleanup of workaround and incorrect filtering
- **Effort:** small
- **Status:** open
- **Dependencies:** BUG-004
- **Affected Files:** `pi_loop/cli.py` (`_generate_completion`)
- **Description:** The `_generate_completion()` function has a Python < 3.12 workaround (`_zsh_sep = chr(92) + chr(10) + "        "`) for f-string backslash limitations. Given Python 3.10+ requirement, this workaround is already obsolete in 3.12+. Together with BUG-004 (long flags excluded), the completions are both incorrect and messy.
- **Research Notes:** Use f-string with `\n` directly (requires Python 3.12+, which is reasonable). Fix the long flag filtering (BUG-004). Add tests for generated completion output.

### [CLEAN-007] Duplicated `_request_shutdown` and `_shutdown_requested` in `loop.py` and `heartbeat.py`

- **Category:** cleanup
- **Priority:** Low
- **Impact:** Low — same threading.Event pattern duplicated
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/loop.py`, `pi_loop/heartbeat.py`
- **Description:** `_request_shutdown` and `_shutdown_requested` are defined in both `loop.py` and `heartbeat.py` — essentially the same `threading.Event` pattern, separate implementations. Potential confusion about which is authoritative.
- **Research Notes:** Consolidate into a single shared module (e.g., `pi_loop/shutdown.py`). Import from a single source.

### [CLEAN-008] Duplicated `on_error_cmd` validation logic

- **Category:** cleanup
- **Priority:** Medium
- **Impact:** Medium — security validation exists in `loop.py` but not in web UI
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/loop.py`, `web_app/config_manager.py`
- **Description:** `_validate_on_error_cmd()` in `loop.py` has strong security validation for shell metacharacters before `shell=True` execution. However, the web UI's `config_manager.py` stores `--on-error-cmd` without any validation on save. Users can set an invalid command via the web UI that passes validation only when executed.
- **Research Notes:** Extract `_validate_on_error_cmd` to a shared module. Use it in both `loop.py` and `config_manager.py`. Add validation to the web API endpoint that saves config.

### [CLEAN-009] Duplicated `/proc` parsing: `_get_cpu_percent()` vs `get_system_usage()`

- **Category:** cleanup
- **Priority:** Low
- **Impact:** Low — different purposes but overlapping `/proc` parsing
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/server.py`, `pi_loop/system_utils.py`
- **Description:** `_get_cpu_percent()` in `server.py` and `get_system_usage()` in `system_utils.py` both read `/proc/stat` — one for CPU diff, one for process CPU ticks. Different purposes but overlapping `/proc` parsing that could be unified.
- **Research Notes:** Consider unifying `/proc` parsing into `system_utils.py` with a `get_cpu_percent()` function that `server.py` can call.

### [CLEAN-010] Inconsistent env prefix: `INFINITE_LOOP_*` vs `PI_LOOP_*`

- **Category:** cleanup
- **Priority:** Low
- **Impact:** Low — naming inconsistency in environment variables
- **Effort:** medium
- **Status:** open
- **Affected Files:** `pi_loop/env_utils.py`, `pi_loop/config_file.py`, `pi_loop/config_manager.py`
- **Description:** Some modules use `INFINITE_LOOP_*` env var names (legacy) while newer code uses `PI_LOOP_*` prefix. Both coexist in `env_utils.py`. Magic string env var names appear across `env_utils.py`, `config_file.py`, `config_manager.py` with no shared constants.
- **Research Notes:** Standardize on `PI_LOOP_*` prefix. Add backward compatibility aliases for `INFINITE_LOOP_*`. Define all known env var names as constants in `env_utils.py`.

### [CLEAN-011] No `__init__.py` re-exports for public API

- **Category:** cleanup
- **Priority:** Low
- **Impact:** Low — users must know internal module names
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/__init__.py`
- **Description:** `pi_loop/__init__.py` only exports `VERSION` and `main`. Users and internal consumers must know internal module names (`pi_loop.loop`, `pi_loop.state`, etc.) to access functionality.
- **Research Notes:** Re-export core public API: `run_loop`, `LoopConfig`, `read_ledger`, `write_ledger`, etc. This also helps with the web_app's fragile import of `config_file.CONFIG_PATH`.

### [CLEAN-012] `_execute_task` docstring is ~50 lines (too long)

- **Category:** cleanup
- **Priority:** Low
- **Impact:** Low — implementation detail, but docstring is overly long
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/loop.py` (`_execute_task` docstring)
- **Description:** `_execute_task` docstring is ~50 lines — too much detail that will drift from implementation.
- **Research Notes:** Keep high-level description and parameter docs. Move implementation details (NDJSON streaming behavior, error classification) to inline comments near the relevant code.

### [CLEAN-013] `format_validation_results()` has dead `colorize=False` branch

- **Category:** cleanup
- **Priority:** Low
- **Impact:** Low — dead code, never called with `colorize=False`
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/env_utils.py` (`format_validation_results`)
- **Description:** `format_validation_results()` has a `colorize` parameter defaulting to `False`, but `check_env_file()` always passes `True`. The `False` branch may be dead code.
- **Research Notes:** Audit all call sites. If `colorize=False` is never used, remove the parameter and simplify the function.

---

## ✨ Features & Ideas

### [FEAT-001] Support multiple named config profiles

- **Category:** feature
- **Priority:** Medium
- **Impact:** Medium — users running different configurations must manually swap config files
- **Effort:** medium
- **Status:** open
- **Affected Files:** `pi_loop/config_file.py`, `pi_loop/cli.py`, `web_app/config_manager.py`, `web_app/static/index.html`
- **Description:** Currently there is a single `~/.config/pi-loop/config.json`. Users who run different loop configurations (e.g., "code review" vs "research" vs "bug fixing") must manually swap config files. Support for named profiles (`--profile research`) would make this seamless.
- **Research Notes:** Change `config_file.py` to support a config directory instead of a single file. Add `--profile` CLI flag. Store configs as `config_{profile}.json`. The web UI can add a profile selector dropdown.

### [FEAT-002] Add Prometheus metrics endpoint

- **Category:** feature
- **Priority:** Medium
- **Impact:** Medium — no monitoring integration for operators
- **Effort:** medium
- **Status:** open
- **Affected Files:** `web_app/server.py`, `pi_loop/config.py`, `pyproject.toml` (optional dep)
- **Description:** The web server exposes iteration counts, error counts, and system resources via the dashboard, but there is no Prometheus `/metrics` endpoint for integration with monitoring stacks. Operators who use Grafana/Prometheus cannot monitor the daemon without custom scraping.
- **Research Notes:** Add optional Prometheus metrics via `prometheus_fastapi_instrumentator`. Export: request count/latency by endpoint, iteration rate, iteration duration, worker count, error rate by type. Disabled by default — enabled with `--metrics` flag or config setting.

### [FEAT-003] Structured JSON logging for the daemon

- **Category:** feature
- **Priority:** High
- **Impact:** High — enables reliable log parsing, eliminates regex-based web UI parsing
- **Effort:** medium
- **Status:** open
- **Dependencies:** BUG-003 (structured logging would resolve the regex parsing fragility)
- **Affected Files:** `pi_loop/file_utils.py`, `pi_loop/loop.py`, `pi_loop/error_recovery.py`, `pi_loop/git_utils.py`, `web_app/loop_manager.py`
- **Description:** All daemon logging uses bare `print()` calls and `logger.info(f"...")` with inline string formatting. No structured fields (event type, iteration number, error code, duration, correlation ID). The web UI's regex-based parsers (BUG-003) exist because there's no structured event stream to consume. Without structured logging, production debugging is manual log scraping.
- **Research Notes:** Define a `StructuredEvent` TypedDict or dataclass with fields: `event` (machine-readable name), `iteration`, `duration_ms`, `error_type`, `worker_id`, `correlation_id`. Replace `print()` with a `log_event()` function that writes JSON lines. Console output stays human-readable. File output uses JSON format.

### [FEAT-004] Persist web UI theme preference in localStorage

- **Category:** feature
- **Priority:** Low
- **Impact:** Low — minor UX improvement
- **Effort:** small
- **Status:** open
- **Affected Files:** `web_app/static/app.js`, `web_app/static/index.html`
- **Description:** The web UI has a theme toggle button that switches between dark and light themes, but the preference is not persisted across page reloads (no localStorage or cookie). Users must re-toggle the theme each time they load the dashboard.
- **Research Notes:** Save theme preference to `localStorage` on toggle. On page load, read `localStorage` and apply the saved theme before rendering the page (to prevent flash of wrong theme). The CSS already supports both themes.

### [FEAT-005] Create Dockerfile and docker-compose for containerized deployment

- **Category:** feature
- **Priority:** Low
- **Impact:** Medium — enables containerized deployment in CI/CD and cloud
- **Effort:** medium
- **Status:** open
- **Affected Files:** `Dockerfile` (new), `docker-compose.yml` (new), `.dockerignore` (new)
- **Description:** The project has no Dockerfile in the main repository. Dockerfiles exist only in stale git worktrees. Containerized deployment would make it easy to run pi-loop in CI/CD pipelines, cloud environments, or isolated environments.
- **Research Notes:** Create a multi-stage Dockerfile: build stage (install build tools, compile) → runtime stage (Python slim image, copy installed package). Use `uvicorn` as entry point for web UI. Create `docker-compose.yml` with volume mounts for config, ledger data, and pi binary.

### [FEAT-006] Graceful shutdown CLI command (`--shutdown`)

- **Category:** feature
- **Priority:** Low
- **Impact:** Medium — no explicit way to stop the daemon gracefully
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/cli.py`, `pi_loop/loop.py`
- **Description:** The daemon stops via sentinel file or signal handlers — no explicit `--shutdown` CLI command. Users must send signals (SIGINT/SIGTERM) or create sentinel files manually.
- **Research Notes:** Add `--shutdown` CLI flag that writes a sentinel file (or sends signal) to trigger graceful shutdown with cleanup.

### [FEAT-007] Ledger backup mechanism

- **Category:** feature
- **Priority:** Low
- **Impact:** Medium — no backup if ledger is corrupted
- **Effort:** medium
- **Status:** open
- **Affected Files:** `pi_loop/state.py`
- **Description:** If the ledger file gets corrupted, all iteration history is lost. No WAL (write-ahead log) or backup mechanism.
- **Research Notes:** Implement periodic backups (e.g., every 10 iterations or every 5 minutes). Store last N backups with timestamps. Add `--recover-from-backup` CLI flag.

### [FEAT-008] Add `--no-convergence` flag to parser (README references it)

- **Category:** feature
- **Priority:** Low
- **Impact:** Low — README references a flag that doesn't exist in `parser.py`
- **Effort:** small
- **Status:** open
- **Affected Files:** `pi_loop/parser.py`, `README.md`
- **Description:** README lists `--no-convergence` in key flags but no such flag exists in `parser.py`. The flag is `--convergence-stop` (deprecated alias?). The flag list in README is stale.
- **Research Notes:** Either add `--no-convergence` as an actual flag (or alias), or update the README to match reality.

---

## ⬆️ Dependencies

### [DEP-001] Recompile lockfiles (pydantic/lockfile version drift)

- **Category:** dependency
- **Priority:** Medium
- **Impact:** Medium — installed versions differ from lockfile
- **Effort:** small
- **Status:** open
- **Affected Files:** `requirements.txt`, `requirements-dev.txt`
- **Description:** The installed pydantic version (2.12.5) differs from the lockfile version (2.13.4), suggesting the last `pip install` used range resolution instead of the lockfile. Lockfiles are meant to be the source of truth — drift indicates either manual `pip install` without `--no-deps` or lockfiles not recompiled after the last `pyproject.toml` change.
- **Research Notes:** Run `make update-lock` to regenerate both lockfiles from current `pyproject.toml`. Run `make verify-lock` to confirm. Then reinstall from lockfiles: `pip install -r requirements.txt -r requirements-dev.txt`.

### [DEP-002] `pip-tools` and `pre-commit` already declared as dev dependencies

- **Category:** dependency
- **Priority:** Low (already resolved)
- **Impact:** None — both tools are declared
- **Effort:** small
- **Status:** done
- **Affected Files:** `pyproject.toml`
- **Description:** Both `pip-tools>=7.0.0` and `pre-commit>=3.0.0` are listed in the `dev` optional dependencies group. The lockfiles include them. No action needed.
- **Research Notes:** ✅ Already resolved — both dependencies are properly declared in `pyproject.toml`.

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| **Total items** | 74 |
| **Open items** | 59 |
| **In progress** | 0 |
| **Done** | 14 |
| **Critical priority** | 5 |
| **High priority** | 16 |
| **Medium priority** | 32 |
| **Low priority** | 21 |

| Category | Count | Notable Gaps |
|----------|-------|-------------|
| Bugs & Issues | 17 | JSON extraction fragility, heartbeat polling delay, regex parsing brittleness |
| Architecture & Design | 11 | Monolithic `run_loop()`, god `LoopConfig`, no DI, no state machine |
| Testing & Quality | 14 | Zero integration tests, 19% loop coverage, no web UI tests |
| Tooling & DevX | 6 | Pre-commit duality, no coverage config section |
| Performance | 9 | Dashboard rebuild, ledger I/O, unbounded context, SSE polling |
| Security | 10 | `shell=True` guardrails, no secrets scanner, no goal sanitization |
| Documentation | 10 | Missing CHANGELOG, CONTRIBUTING, SECURITY, stale README |
| CI/CD | 6 | No release workflow, Docker, deprecated safety command |
| Code Cleanup | 13 | noqa proliferation, duplicate writers, env prefix inconsistency |
| Features | 8 | Config profiles, Prometheus, Docker, structured logging, ledger backup |
| Dependencies | 2 | Lockfile drift |

---

*This backlog is a living document synthesized from full-source audit, test assessment, security review, dependency inspection, documentation evaluation, and tooling audit.*
*Last updated: 2026-06-30. Total items: 74*
