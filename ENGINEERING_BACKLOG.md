# Engineering Backlog

> Living document — comprehensive engineering backlog for the pi-loop autonomous task automation daemon.
> Last updated: 2026-06-30
> Version: 14.39.0

---

## Repository Overview

**pi-loop** is a self-contained Python daemon that runs tasks iteratively in a loop, tracks progress in a JSON ledger, and surfaces everything through a dark-theme web dashboard. It delegates each iteration to the [pi coding agent](https://pi.ai) and handles orchestration — convergence detection, error recovery, cooldown management, git auto-commit, multi-worker parallelism, and real-time monitoring via SSE.

### Architecture & Tech Stack

| Layer | Technology |
|---|---|
| **Language** | Python ≥3.10, JavaScript (vanilla SPA) |
| **Web framework** | FastAPI 0.138.1 + Starlette 1.3.1 |
| **Server** | uvicorn 0.49.0 (with httptools, uvloop) |
| **Validation** | Pydantic 2.13.4 |
| **Frontend** | Vanilla HTML/CSS/JS (no framework), xterm.js for terminal, SSE for live updates |
| **Testing** | pytest 9.1, pytest-asyncio, pytest-cov, pytest-timeout (460 tests across 25+ test files) |
| **Linting** | Ruff 0.15.20 |
| **Type checking** | mypy 2.1.0 (CI-enforced) |
| **Security scanning** | bandit 1.9.4 + safety 3.8.1 |
| **Dependency management** | pip-tools (lock files for prod and dev) |
| **Pre-commit** | pre-commit 4.6.0 |

### Observed Design Patterns

- **Monolithic orchestration**: `run_loop()` in `loop.py` is a single ~300-line function with 60+ local variables handling shutdown, git state capture, notifications, error recovery, cooldown, dashboard HTML generation, HTTP callbacks, goal cycling, convergence detection, and heartbeat management.
- **LoopConfig dataclass**: A god dataclass with 63 fields, consolidating what was previously a 71-parameter function signature.
- **Ledger-as-state**: All runtime state persists to a JSON file (`/tmp/infinite-loop-state.json`) — the web UI reads this file directly rather than using IPC.
- **Subprocess delegation**: Each task iteration spawns an external `pi -q <goal>` subprocess and parses NDJSON output line-by-line for real-time terminal streaming.
- **Regex-based log parsing**: `loop_manager.py` parses daemon stdout with regex patterns on ANSI-colored text to extract structured iteration data.

### Current Maturity Level

- **Test count**: 460 tests across 19+ test modules
- **CI pipeline**: Python 3.10–3.13 matrix, lint, mypy, security, verify-lock, coverage merge
- **Version**: 14.39.0 (suggestive of rapid iteration rather than semantic versioning)
- **Known fixed issues**: 10+ bugs resolved in recent iterations including XSS in dashboard, `/tmp` path hardening, race conditions, dead code wiring
- **Gaps**: No release workflow, no integration tests, no CHANGELOG in standard format, no typed state model

---

## Backlog Items

### BUG-001 — `_evolve_goal` writes `evolved_goal` to state but `run_loop` never reads it

| Field | Value |
|---|---|
| **Category** | bug |
| **Priority** | High |
| **Impact** | High — `evolve` feature is dead code. The daemon writes `state["evolved_goal"]` every iteration when `--evolve` is set, but `run_loop` never switches to it. Users who enable `--evolve` get a no-op feature. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | `_evolve_goal()` in `functions.py` parses pi output for `NEXT_GOAL:` headers and stores them in `state["evolved_goal"]`. However, `run_loop()` in `loop.py` at no point reads `state["evolved_goal"]` to override the current goal. The feature is mechanically complete (writes) but has no consumer (reads). |
| **Rationale** | The evolve feature was designed to let pi sessions self-direct by proposing the next task. Without the read side, the write is pure overhead — wasted string parsing and dict writes on every iteration. This is a regression or incomplete implementation that should either be completed (wire the read) or removed with clear deprecation messaging. |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/functions.py` |

### BUG-002 — `suppress(Exception)` silently swallows notification and HTTP callback failures

| Field | Value |
|---|---|
| **Category** | bug |
| **Priority** | High |
| **Impact** | High — notification failures and HTTP callback errors disappear without any log. If the callback server is down, credentials expire, or the notification command fails, operators never know. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | In `run_loop()`, the desktop notification block and HTTP callback block both use `with suppress(Exception):` (lines 225, 244 in `loop.py`). Any exception during notification dispatch or HTTP callback is silently swallowed, including connection errors, DNS failures, and invalid notification commands. |
| **Rationale** | Silent exception suppression hides operational problems. At minimum, log the exception with a `WARNING` level before suppressing. For notifications specifically, consider a retry-with-backoff pattern since transient network failures are common. |
| **Affected Files** | `pi_loop/loop.py` |

### BUG-003 — `loop_manager.py` parses daemon stdout with regex on ANSI-colored text — fragile and lossy

| Field | Value |
|---|---|
| **Category** | bug |
| **Priority** | High |
| **Impact** | High — if daemon logging colors change, ANSI escape sequence suppression changes, or log format varies, the web UI will silently lose iteration state tracking, worker status, and error classification. |
| **Effort** | Medium |
| **Status** | pending |
| **Description** | `LoopManager._parse_line()` in `loop_manager.py` applies `_ANSI_ESCAPE.sub("", text)` to strip ANSI codes, then uses 6+ regex patterns (`re.search`) to extract worker status, duration, error type, heartbeat, and iteration data. This is fragile: a log format change (e.g., adding a timestamp prefix, changing bracket style) breaks all parsers silently. Regex patterns include `r"\[TERM.*?\]", r"\[WORKER", r"\[BEAT\]", r"\[ERROR-TYPE\]"`. |
| **Rationale** | The daemon emits structured NDJSON events during task execution (`_execute_task` in `loop.py`), but the web UI's `LoopManager` ignores that structured data and instead reverse-engineers state from human-readable log strings. This is an architectural mismatch. The SSE stream should consume structured events, not regex-parsed ANSI text. |
| **Affected Files** | `web_app/loop_manager.py`, `web_app/server.py` (SSE streaming), `pi_loop/loop.py` |

### BUG-004 — `status.py` uptime calculation uses undocumented `os.sysconf_names` — may crash on some platforms

| Field | Value |
|---|---|
| **Category** | bug |
| **Priority** | Medium |
| **Impact** | Medium — `write_status()` computes uptime from `/proc/[pid]/stat` using `os.sysconf_names["SC_CLK_TCK"]` (an undocumented Python attribute). On platforms where this fails, the status file gets `uptime_seconds: 0.0` and an unhandled `KeyError` could propagate. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | `status.py` line ~48: `clock_ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])`. The `os.sysconf_names` dict is an internal CPython implementation detail, not a documented public API. If the name is not available (e.g., on some alternative Python implementations or restricted environments), this raises `KeyError`. Additionally, the "rough" boot_time comment suggests the calculation is approximate at best. |
| **Rationale** | Using undocumented internal APIs is a maintenance risk. The uptime calculation as a whole is fragile (relies on `/proc`, field offset 21 in `/proc/pid/stat`). Consider using a simpler approach: store the process start time at daemon init and compute uptime as `time.time() - start_time`. |
| **Affected Files** | `pi_loop/status.py` |

### BUG-005 — `classify_error()` misses common timeout and network error patterns

| Field | Value |
|---|---|
| **Category** | bug |
| **Priority** | Medium |
| **Impact** | Medium — errors like `"connection timed out"`, `"timedout"`, `"time_out"`, `"gateway timeout"` (already matches via "gateway timeout"), or `"read timed out"` fall through to "unknown" classification. This reduces the effectiveness of the error-recovery engine's backoff strategy. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | `classify_error()` in `error_utils.py` checks `"timeout"` and `"timed out"` but misses `"timedout"`, `"time_out"`, `"read timed out"`, `"connection timed out"`. The network category misses `"name or service not known"`, `"temporary failure"`, `"name resolution"`, `"no address"`, `"protocol error"`, `"ssl_error"`, `"handshake"`. |
| **Rationale** | Misclassified errors mean the adaptive error recovery engine applies the wrong mitigation strategy. A timeout misclassified as "unknown" gets an elevated cooldown but no timeout extension. A network error misclassified as "unknown" bypasses the exponential backoff entirely. |
| **Affected Files** | `pi_loop/error_utils.py` |

### BUG-006 — `extract_json_from_output()` may return stale JSON from backward scan before forward scan completes

| Field | Value |
|---|---|
| **Category** | bug |
| **Priority** | Low |
| **Impact** | Low — The function runs two strategies: (1) reverse scan returns on first valid `{}` block, (2) forward scan collects all JSON and returns last. If the reverse scan finds a valid but incomplete or outdated `{}` bridge from a previous message, it returns that instead of the more complete forward-scan result. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | `extract_json_from_output()` in `file_utils.py` first scans backwards for the LAST JSON object using brace-depth counting, returning immediately on success. If that brace-counting scan finds a premature match (e.g., a substring that happens to balance `{}` but isn't a valid JSON object), it returns it. The forward scan (strategy 2) is more thorough — it validates via `json.loads()` — but may never run. |
| **Rationale** | The two-strategy approach has a correctness bug: the less reliable strategy (brace counting) takes priority over the more reliable strategy (`json.loads` validation). Reverse the priority or remove strategy 1 entirely. |
| **Affected Files** | `pi_loop/file_utils.py` |

### TECH-DEBT-001 — `run_loop()` monolithic 300+ line function with 60+ local variables

| Field | Value |
|---|---|
| **Category** | technical-debt |
| **Priority** | Critical |
| **Impact** | High — The function handles shutdown, git state capture, notification dispatch, error recovery adaptation, cooldown logic, dashboard HTML generation, HTTP callbacks, goal cycling, convergence detection, and heartbeat management. Every new feature requires touching this function, increasing risk of regressions. Testability is near-zero since mocking 60+ local variables is impractical. |
| **Effort** | X-Large |
| **Status** | pending |
| **Description** | Decompose `run_loop()` into focused classes/modules: `IterationEngine` (iteration loop control), `NotificationDispatcher` (desktop/PushBullet/ntfy callbacks), `DashboardBuilder` (HTML report generation), `ConvergenceDetector` (repetition detection), `GoalCycler` (goals file management), `CooldownManager` (fixed/adaptive cooldown). Each class should be independently testable. |
| **Rationale** | Monolithic functions are the primary source of technical debt. The 60+ local variables are a strong signal that too many concerns coexist in one scope. Decomposition enables unit testing, parallel development, and reduces the blast radius of changes. |
| **Affected Files** | `pi_loop/loop.py` |

### TECH-DEBT-002 — `LoopConfig` god dataclass with 63 fields

| Field | Value |
|---|---|
| **Category** | technical-debt |
| **Priority** | High |
| **Impact** | High — Every new config option adds a field to this single dataclass. `from_args()` uses `getattr` on argparse namespace with implicit field discovery, making it hard to track which fields are used where. |
| **Effort** | Medium |
| **Status** | pending |
| **Description** | Split `LoopConfig` into focused config dataclasses: `CoreConfig` (goal, context, workdir), `IterationConfig` (max_iterations, cooldown, convergence), `WorkerConfig` (workers, timeout, retries), `GitConfig` (git, git_commit, store_git_diff), `NotificationConfig` (notify_cmd, pushbullet, ntfy), `WebConfig` (html_dashboard, status_file, webhook_port), `ArchiveConfig` (keep_iterations, archive_dir, retention). Use composition in a top-level config object. |
| **Rationale** | 63-field dataclasses violate the Single Responsibility Principle. Focused configs improve readability, testability, and documentation. They also enable type-safe subset passing (e.g., `NotificationConfig` to notification code without exposing all 63 fields). |
| **Affected Files** | `pi_loop/config.py`, `pi_loop/loop.py`, `pi_loop/cli.py` |

### TECH-DEBT-003 — `_log_startup_banner()` has 30 parameters

| Field | Value |
|---|---|
| **Category** | technical-debt |
| **Priority** | High |
| **Impact** | Medium — Every new daemon option requires adding a parameter to this function's signature. The function name is misleading (it's not just a "banner" — it logs detailed categorized configuration). |
| **Effort** | Small |
| **Status** | pending |
| **Description** | The function takes 30 named parameters: `task_type`, `task_type_desc`, `profile`, `model`, `max_iterations`, `max_retries`, `_max_turns`, `_tag`, `goal`, `toolsets`, `evolve`, `git`, `git_commit`, `workers`, `session_timeout`, `notify_cmd`, `_use_library`, `pass_session_id`, `checkpoints`, `output_schema`, `cooldown_mode`, `cooldown`, `convergence_stop`, `convergence_window`, `convergence_threshold`, `store_git_diff`, `track_goals`, `reset_goals`, `heartbeat_timeout`, `quiet`. Six of these have underscore prefixes suggesting they should be private. |
| **Rationale** | Accept the `LoopConfig` dataclass instead of 30 individual parameters. This reduces the signature to 2 parameters (`cfg: LoopConfig, quiet: bool = False`) and ensures new config fields are automatically reflected in the startup banner. |
| **Affected Files** | `pi_loop/functions.py` |

### TECH-DEBT-004 — Two env var naming conventions (`PI_LOOP_*` and `INFINITE_LOOP_*`)

| Field | Value |
|---|---|
| **Category** | technical-debt |
| **Priority** | Medium |
| **Impact** | Medium — `config.py` uses `PI_LOOP_DATA_DIR`, `PI_LOOP_LEDGER_PATH`, etc. `config_file.py` and `env_utils.py` use `INFINITE_LOOP_*` (e.g., `INFINITE_LOOP_MAX_ITERATIONS`, `INFINITE_LOOP_GOAL`). `web_app/config_manager.py` defines config schema keys as `INFINITE_LOOP_*` but `build_cli_args()` maps them to `--flag` args. |
| **Effort** | Medium |
| **Status** | pending |
| **Description** | The project's env var namespace is split: newer runtime paths use `PI_LOOP_*` while the web UI's config system (built on `config_file.py`) uses `INFINITE_LOOP_*`. This means a user who reads `PI_LOOP_DATA_DIR` in the docs won't find `INFINITE_LOOP_GOAL` in the same namespace. `env_utils.py` lists both but doesn't enforce a canonical prefix. |
| **Rationale** | A single, consistent namespace reduces cognitive load and prevents configuration bugs. Standardize on `PI_LOOP_*` (shorter, cleaner), migrate `INFINITE_LOOP_*` to `PI_LOOP_*` with backward-compatible aliases, and deprecate the old names. |
| **Affected Files** | `pi_loop/config_file.py`, `pi_loop/env_utils.py`, `web_app/config_manager.py`, `README.md` |

### TECH-DEBT-005 — `loop_manager.py` keeps an open `_log_fp` file handle across the daemon's full lifecycle

| Field | Value |
|---|---|
| **Category** | technical-debt |
| **Priority** | Medium |
| **Impact** | Medium — The `_log_fp` file handle is opened lazily and never closed during normal daemon operation. On long-running daemon sessions (hours/days), the file descriptor stays open. If the underlying log file is rotated externally, writes go to a stale inode. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | `LoopManager._add_log()` opens `self._log_fp` on first call via `self._log_fp = open(self._log_file, "a")` and explicitly keeps the handle open for reuse. The only close happens in `close()` / `__del__()`. If `close()` is called but the file was externally rotated, the stale handle still writes to the old inode. |
| **Rationale** | Use a file handle that re-opens on each write (or every N writes) to handle log rotation gracefully. This also eliminates the `__del__`-based cleanup, which is unreliable in CPython. |
| **Affected Files** | `web_app/loop_manager.py` |

### TECH-DEBT-006 — `state: dict` used everywhere instead of typed state model

| Field | Value |
|---|---|
| **Category** | technical-debt |
| **Priority** | Medium |
| **Impact** | Medium — The ledger state is `dict` everywhere with string-key access. Key typos (`"iterations"` vs `"iteration"`) are runtime errors, not compile-time. The state shape is complex but undocumented — 20+ keys including nested `"stats"`, `"error_type_counts"`, `"mitigations"`, `"goals_completed"` dicts. |
| **Effort** | Medium |
| **Status** | pending |
| **Description** | Define `TypedDict` classes for the ledger state: `LedgerState`, `IterationRecord`, `StatsRecord`, `ErrorTypeCounts`, `MitigationState`, `GoalTrackingState`. Use these types in all state-read/write paths. This catches key errors at mypy-check time and provides auto-completion in IDEs. |
| **Rationale** | Typed dicts are the minimum viable typing for the state shape. Combined with mypy enforcement, this eliminates an entire class of runtime bugs (typos, missing keys, wrong types). |
| **Affected Files** | `pi_loop/state.py`, `pi_loop/loop.py`, `pi_loop/stats.py`, `pi_loop/file_utils.py`, `pi_loop/cli.py`, `web_app/loop_manager.py` |

### TEST-001 — Zero integration tests for the core `pi` subprocess spawning

| Field | Value |
|---|---|
| **Category** | testing |
| **Priority** | Critical |
| **Impact** | High — The core value proposition (subprocess task execution via `pi`) has zero end-to-end verification. All 460 tests are unit tests that mock subprocess calls. A real `pi` binary change (flag rename, output format change, mode=json breaking change) would go undetected until production. |
| **Effort** | Medium |
| **Status** | pending |
| **Description** | Create `tests/integration/` with `mock_pi.sh` that emits realistic NDJSON output (thinking events, tool calls, text responses). Test: single iteration success, convergence detection with repeated output, error recovery with injected failures, sentinel stop/pause, multi-worker parallelism, and web UI daemon interaction. |
| **Rationale** | The daemon's entire purpose is to orchestrate `pi` subprocesses. If the subprocess mode changes (flag names, output format, exit codes), the daemon breaks silently. Integration tests with a realistic mock provide a safety net that unit tests cannot. |
| **Affected Files** | `tests/conftest.py`, `tests/integration/` (new), `pi_loop/loop.py`, `pi_loop/functions.py` |

### TEST-002 — `config_file.py` has no test coverage

| Field | Value |
|---|---|
| **Category** | testing |
| **Priority** | High |
| **Impact** | Medium — `config_file.py` has 7 functions handling config persistence, backup/restore, atomic writes, and env var application. Zero tests. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Write tests for: `load_config()` with missing/corrupted/backup files, `save_config()` atomic write behavior, `_atomic_write()` crash recovery (temp file cleanup), `apply_to_environ()` env var application, `get_bool()` truthiness parsing, `ensure_config_dir()` directory creation. |
| **Rationale** | Config file corruption can leave the daemon in an unrecoverable state. The backup/restore logic is untested. |
| **Affected Files** | `pi_loop/config_file.py`, `tests/test_config_file.py` |

### TEST-003 — `web_app/rate_limiter.py` has no test coverage

| Field | Value |
|---|---|
| **Category** | testing |
| **Priority** | Medium |
| **Impact** | Medium — The sliding-window rate limiter protects all API endpoints from abuse. Zero tests for its sliding-window logic, concurrent access, edge conditions (exactly at limit, reset, negative inputs). |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Write tests for: `check()` allowing requests within limit, `check()` blocking when at limit, timestamp trimming (expired entries removed), `remaining()` accuracy, `reset()` per-IP and global, concurrent `check()` calls from multiple coroutines. |
| **Rationale** | A bug in the rate limiter can either open the API to abuse (false negatives) or block legitimate usage (false positives). Both are hard to diagnose without tests. |
| **Affected Files** | `web_app/rate_limiter.py`, `tests/test_rate_limiter.py` (new) |

### TEST-004 — `pi_loop/validation.py` has minimal test coverage

| Field | Value |
|---|---|
| **Category** | testing |
| **Priority** | Medium |
| **Impact** | Low — `load_json_schema()` handles file loading error cases but has no tests for edge conditions: empty files, non-JSON files, permissions errors, symlink loops. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Add tests for: valid JSON schema loading, invalid JSON in file, empty file, non-JSON content, missing file, permission denied (if testable), non-dict JSON (e.g., array schema). |
| **Rationale** | Schema loading errors produce a WARN log and return None, potentially causing downstream confusion when the output schema is silently ignored. |
| **Affected Files** | `pi_loop/validation.py`, `tests/test_validation.py` (new) |

### PERF-001 — `/api/logs` endpoint re-parses the entire log file on every request

| Field | Value |
|---|---|
| **Category** | performance |
| **Priority** | Medium |
| **Impact** | Medium — Each GET `/api/logs` triggers `LoopManager._hydrate_from_log_file()` which reads the entire persisted log file and re-parses all log entries. On long-running daemon sessions, this file can grow to hundreds of KB. The naïve read-parse-return cycle adds latency proportional to log size. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Cache the parsed log entries and append-only read new lines on subsequent requests (track file position via `tell()`). The SSE poller already calls this every 2s, so the O(n) read on every poll is wasteful. |
| **Rationale** | Log files grow linearly with daemon uptime. An O(n) re-parse every 2s is unnecessary. An incremental reader that only processes new bytes since the last read reduces per-poll overhead to O(1). |
| **Affected Files** | `web_app/loop_manager.py`, `web_app/server.py` (SSE status poller) |

### PERF-002 — SSE status poller reads the entire ledger JSON file every 2 seconds

| Field | Value |
|---|---|
| **Category** | performance |
| **Priority** | Medium |
| **Impact** | Medium — The `_status_poller()` background task in `server.py` reads `loop-status.json` (from `pi_loop/status.py`) and `loop-manager-status.json` (via `LoopManager.status`) every ~2 seconds. The JSON ledger is re-read and re-parsed each cycle. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Track the ledger file's mtime and skip re-parsing if unchanged. The SSE poller already has a `last_status_hash` mechanism, but it still reads and parses the full JSON before computing the hash. Move the mtime check before the JSON parse. |
| **Rationale** | Reading and parsing the full ledger JSON every 2 seconds is wasteful when the ledger only changes once per iteration (potentially minutes apart). An mtime gate eliminates ~99% of unnecessary reads during long-running iterations. |
| **Affected Files** | `web_app/server.py` |

### PERF-003 — `write_ledger()` acquires a file lock and writes the full ledger on every iteration

| Field | Value |
|---|---|
| **Category** | performance |
| **Priority** | Low |
| **Impact** | Low — Each iteration triggers a full JSON serialization and file write of the entire state dict. For configurations with many archived iterations (e.g., `--keep-iterations 500`), this serializes 500+ history records on every iteration cycle. |
| **Effort** | Medium |
| **Status** | pending |
| **Description** | Consider an append-only iteration log (JSON Lines) for iteration records, with the metadata state file kept small and rewritten only when metadata changes. Append-only writes are O(1) instead of O(n) per iteration. |
| **Rationale** | Full-state JSON writes are simple and correct, but they serialize the entire iteration history every time. For long-running loops with many iterations, this adds unnecessary I/O. A hybrid approach (JSON Lines for history + compact JSON for metadata) would be more efficient. |
| **Affected Files** | `pi_loop/file_utils.py`, `pi_loop/loop.py` |

### ARCH-001 — Web server middleware runs rate limiter AFTER auth but BEFORE CORS

| Field | Value |
|---|---|
| **Category** | architecture |
| **Priority** | Medium |
| **Impact** | Medium — `server.py` registers middleware in order: (1) `api_key_auth` (2) `rate_limit_middleware`. The rate limiter is registered after `api_key_auth` but the CORSMiddleware is registered as FastAPI middleware. FastAPI middleware runs inside-out (last registered executes first), meaning CORS headers may not be set before the rate limiter returns a 429, potentially causing browser CORS errors. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | FastAPI's middleware executes in reverse registration order. `CORSMiddleware` is added first, then `api_key_auth`, then `rate_limit_middleware`. When rate_limit returns 429, it does NOT add CORS headers. A browser making cross-origin requests would see a CORS error instead of the 429 body, confusing debugging. |
| **Rationale** | Rate-limited responses should include CORS headers so the client can read the 429 response body. This requires either adding CORS headers in the rate limiter middleware or reordering middleware so CORS runs outermost. |
| **Affected Files** | `web_app/server.py` |

### ARCH-002 — All agent orchestration lives in a single while-loop with no state machine abstraction

| Field | Value |
|---|---|
| **Category** | architecture |
| **Priority** | Medium |
| **Impact** | Medium — The main loop in `run_loop()` is a flat `while True` with condition checks. Loop states (running, paused, stopped, error) are managed via sentinel file checks and `_shutdown_requested` Event. There's no explicit state machine, making it hard to add new states (e.g., "draining" for graceful shutdown, "backoff" for cooldown-only no-op cycles). |
| **Effort** | Medium |
| **Status** | pending |
| **Description** | Introduce a `LoopStateMachine` class with explicit states (IDLE, RUNNING, COOLDOWN, ERROR, STOPPING) and transitions. Each state has an `enter()` and `exit()` hook. This makes the loop behavior explicit, testable, and extensible. |
| **Rationale** | A flat while-loop with ad-hoc condition variables is hard to reason about and harder to extend. An explicit state machine documents legal transitions, prevents invalid state combinations, and enables per-state lifecycle hooks. |
| **Affected Files** | `pi_loop/loop.py` |

### ARCH-003 — `os.sysconf_names` usage ties system monitoring to Linux /proc only

| Field | Value |
|---|---|
| **Category** | architecture |
| **Priority** | Medium |
| **Impact** | Medium — CPU/memory monitoring (`system_utils.py` and `status.py`) reads `/proc/[pid]/status`, `/proc/meminfo`, and `/proc/pid/stat`. These files only exist on Linux. On macOS, BSD, or Windows, the monitoring endpoints crash with `FileNotFoundError` or return unreliable data. |
| **Effort** | Medium |
| **Status** | pending |
| **Description** | Create an abstract `SystemResourceProvider` interface with `LinuxProvider` (current /proc-based), `MacOSProvider` (uses `psutil` or `os.popen("ps")`), and `NoopProvider` (returns zero-filled data with a warning). Auto-detect platform at startup. |
| **Rationale** | The README advertises "stdlib only — no psutil dependency" for system monitoring, but this limits the daemon to Linux. A provider pattern maintains the Linux-optimized path while gracefully degrading on other platforms. |
| **Affected Files** | `pi_loop/system_utils.py`, `pi_loop/status.py`, `pyproject.toml` (optional psutil dep) |

### SEC-001 — `strip_ansi()` only strips `m`-terminated escape sequences, not all ANSI

| Field | Value |
|---|---|
| **Category** | bug / security |
| **Priority** | Medium |
| **Impact** | Medium — `color_utils.strip_ansi()` uses regex `r"\033\[[0-9;]*m"` which only strips CSI sequences ending in `m` (Select Graphic Rendition). Other ANSI escape sequences (cursor movement `[A`, clear screen `[2J`, scroll `[S`) pass through. If task output contains such sequences, they appear as raw control characters in log files and the web UI terminal view. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Use a comprehensive ANSI escape regex: `r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"` (matches all CSI and two-byte escapes). This is already defined as `_ANSI_ESCAPE` in `loop_manager.py` — reuse it from a shared location. |
| **Rationale** | ANSI cursor movement and screen control sequences in log files can corrupt terminal display, make logs unreadable in headless consumers, and in extreme cases could be used to obscure malicious output. |
| **Affected Files** | `pi_loop/color_utils.py`, `pi_loop/file_utils.py`, `web_app/loop_manager.py` |

### SEC-002 — API key is loaded from environment at middleware call time, not server startup

| Field | Value |
|---|---|
| **Category** | security |
| **Priority** | Low |
| **Impact** | Low — The `api_key_auth` middleware reads `PI_LOOP_API_KEY` from `os.environ` on every HTTP request. If the environment variable changes after server startup (possible in container orchestration), authentication behavior changes without warning. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Read `PI_LOOP_API_KEY` once at startup (in `main()`) and pass it as a closure variable to the middleware. Log a warning if the env var changes detection is desired. |
| **Rationale** | Per-request environment lookups are a minor anti-pattern. More importantly, if the env var is accidentally unset after startup, authentication silently disables in a running production server. |
| **Affected Files** | `web_app/server.py` |

### CI-CD-001 — No release workflow (tag → build → publish)

| Field | Value |
|---|---|
| **Category** | ci/cd |
| **Priority** | High |
| **Impact** | High — The project has version 14.39.0, a comprehensive test suite, and CI, but no automated release process. Releases are manual (change pyproject.toml version, tag, push). No changelog management, no PyPI publish automation, no GitHub Release creation. |
| **Effort** | Medium |
| **Status** | pending |
| **Description** | Create `.github/workflows/release.yml` that triggers on version tags (`v*`). Steps: build package (`python -m build`), run full test suite, create GitHub Release with auto-generated changelog, publish to PyPI (if desired). |
| **Rationale** | Manual releases are error-prone and discourage regular releases. The current build number (v14.39.0) suggests many small changes without corresponding releases — a release workflow would incentivize shippable milestones. |
| **Affected Files** | `.github/workflows/release.yml` (new), `pyproject.toml` |

### CI-CD-002 — `httpx2` (test dep) may conflict with `httpx` (safety dep)

| Field | Value |
|---|---|
| **Category** | ci/cd |
| **Priority** | Medium |
| **Impact** | Low — `requirements-dev.txt` lists both `httpx==0.28.1` (pulled by safety) and `httpx2==2.5.0` (pulled by test config). `httpx2` has its own httpcore2 dependency (`httpcore2==2.5.0`). If `httpx` and `httpx2` both depend on `httpcore` (version 1.x vs 2.x), there may be import conflicts in test environments. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Investigate whether `httpx` and `httpx2` can coexist. `httpx2` uses `httpcore2` (dependency-separated), so in theory they don't conflict. Verify this and document in CONTRIBUTING.md. If they do conflict, consider replacing `httpx` in test deps with `httpx2`-only approach. |
| **Rationale** | Undetected dependency conflicts cause mysterious test failures in CI. The lock file (requirements-dev.txt) pins all versions, so pip-compile should catch conflicts, but runtime import-time conflicts are not checked by pip. |
| **Affected Files** | `requirements-dev.txt`, `pyproject.toml` |

### DX-001 — No pre-commit hooks configured for the repository

| Field | Value |
|---|---|
| **Category** | developer-experience |
| **Priority** | Medium |
| **Impact** | Medium — `Makefile` has `pre-commit` and `pre-commit-run` targets, and `requirements-dev.txt` includes `pre-commit==4.6.0`, but there is no `.pre-commit-config.yaml` file in the repo. Running `make pre-commit` installs the tool but adds no hooks. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Create `.pre-commit-config.yaml` with hooks: `ruff` (lint + format check), `mypy` (type checking), `trailing-whitespace`, `end-of-file-fixer`, `check-json`, `check-yaml`, `check-toml`, `check-merge-conflict`, `detect-private-key`. |
| **Rationale** | Pre-commit hooks catch formatting, typing, and common mistakes at commit time, reducing CI round-trips. The tool is already in dev deps. |
| **Affected Files** | `.pre-commit-config.yaml` (new), `Makefile` |

### DX-002 — `env_utils.KNOWN_ENV_VARS` has 100+ entries with no stale-entry detection

| Field | Value |
|---|---|
| **Category** | developer-experience |
| **Priority** | Low |
| **Impact** | Low — `KNOWN_ENV_VARS` is a manually maintained set of every recognized env var. Over time, deprecated vars accumulate. The `check_env_file()` function uses `difflib` to suggest corrections for unknown vars, but doesn't warn about deprecated vars that are still in use. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Add a `DEPRECATED_ENV_VARS` dict mapping old var names to their replacements. In `check_env_file()`, emit warnings for deprecated vars with migration instructions. Remove vars that have been replaced by `PI_LOOP_*` equivalents (e.g., `INFINITE_LOOP_GOAL` → `PI_LOOP_GOAL`). |
| **Rationale** | Stale env vars accumulate and mislead users into thinking a feature is supported when it isn't. A deprecation mechanism makes the migration path explicit. |
| **Affected Files** | `pi_loop/env_utils.py` |

### DOC-001 — No `.pre-commit-config.yaml` despite pre-commit being a dev dependency

| Field | Value |
|---|---|
| **Category** | documentation |
| **Priority** | Low |
| **Impact** | Low — The project ships pre-commit as a dev dependency and documents `make pre-commit` in both the Makefile and CONTRIBUTING.md, but the config file doesn't exist. New contributors who run `pre-commit install` get no hooks and assume the repo doesn't use them. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Create `.pre-commit-config.yaml` (also listed as DX-001 — merge with that effort). Update `CONTRIBUTING.md` to reference the actual hooks. |
| **Rationale** | Inconsistency between documented tooling and actual configuration creates a confused contributor experience. |
| **Affected Files** | `.pre-commit-config.yaml` (new), `CONTRIBUTING.md` |

### DOC-002 — Incomplete docstrings on exported public API functions

| Field | Value |
|---|---|
| **Category** | documentation |
| **Priority** | Low |
| **Impact** | Low — Several exported functions in `pi_loop/` lack docstrings or have minimal `"""One-liner."""` docstrings: `_recalc_stats()` (no return docs), `_evolve_goal()` (outdated description), `check_sentinel()` (no return docs), `extract_json_from_output()` (complex algorithm explained in comments but not docstring). |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Audit all public functions in `pi_loop/` and `web_app/` for docstring completeness. Ensure all functions have: one-line summary, Args section (with types), Returns section (with types and return-value semantics). |
| **Rationale** | The project is at v14.39.0 with 460 tests but incomplete API documentation. As an open-source project (MIT license), missing docstrings reduce adoption. |
| **Affected Files** | `pi_loop/stats.py`, `pi_loop/functions.py`, `pi_loop/file_utils.py`, `pi_loop/loop.py` |

### OBSERV-001 — Version number 14.39.0 is disproportionately high for project scale

| Field | Value |
|---|---|
| **Category** | developer-experience |
| **Priority** | Low |
| **Impact** | Low — The version `14.39.0` suggests 14 major releases and 39 minor releases for a project with ~5,000 lines of Python. This inflates version numbers and makes semantic versioning meaningless. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Consider resetting to a more meaningful versioning scheme. Either: (1) adopt SemVer with `0.x` until API stability, (2) adopt CalVer aligned with release dates, or (3) begin proper SemVer after the next release workflow is established. |
| **Rationale** | Inflated version numbers erode trust. `14.39.0` suggests a maturity that the project's feature set and test coverage don't reflect. It also makes it hard to communicate "breaking change" vs "minor improvement" to users. |
| **Affected Files** | `pi_loop/config.py`, `pi_loop/__init__.py`, `pyproject.toml` |

### OBSERV-002 — `config_file.py` `apply_to_environ()` uses `os.environ.setdefault()` — last-write-wins from `.env` may be silently ignored

| Field | Value |
|---|---|
| **Category** | bug |
| **Priority** | Low |
| **Impact** | Low — `apply_to_environ()` uses `os.environ.setdefault(key, str(value))`. If a `.env` file or previous call already set a value, later calls to `apply_to_environ()` will NOT override it. This means config file changes may not be reflected in the runtime environment until the process is restarted. |
| **Effort** | Small |
| **Status** | pending |
| **Description** | Document the precedence order explicitly in the function docstring: (1) existing `os.environ`, (2) `apply_to_environ()`, (3) `.env` file. Consider adding a `force` parameter to override existing values. |
| **Rationale** | `setdefault()` behavior is non-obvious. When users change a config file setting and expect it to apply, they may not realize a `.env` value takes precedence. |
| **Affected Files** | `pi_loop/config_file.py` |

---

## Initial Assessment

### What the project does well

1. **Comprehensive CI pipeline** — Python 3.10–3.13 matrix, lint, mypy, security scanning, lock file verification, multi-version coverage merge. This is best-in-class for a project of this scale.
2. **Strong security posture** — Stored XSS eliminated, API key auth available, rate limiting, HMAC-signed webhooks. Security scanning actually fails on vulnerabilities (no `|| true` masking).
3. **Excellent test coverage for core logic** — 460 tests across 25+ test files covering most utility modules, error recovery, git utils, preflight checks, stats, and the web server.
4. **Real-time feedback** — SSE streaming, xterm.js terminal integration, per-worker live logs. The web UI provides good operational visibility.
5. **Error recovery engine** — Per-type adaptive backoff, escalation levels, and auto-recovery. This is a sophisticated feature for a daemon of this scope.
6. **Clean code organization** — Modules are well-separated, imports are clean, and the `LoopConfig` dataclass (despite being large) is an improvement over the 71-parameter function signature it replaced.
7. **Thoughtful design decisions** — Unified `_get_data_dir()` path resolution, atomic file writes, file locking for ledger, `PI_LOOP_NO_HYDRATE` for test isolation.

### What needs immediate attention

1. **`_evolve_goal()` dead code** (BUG-001) — The evolve feature is mechanically complete on the write side but has no consumer. Users enabling `--evolve` get silent no-ops.
2. **Silent notification failures** (BUG-002) — `suppress(Exception)` hides failed notifications and HTTP callbacks. At minimum, log them.
3. **No integration tests** (TEST-001) — 460 unit tests but zero end-to-end verification of the core `pi` subprocess spawning. A `pi` CLI change would break the daemon silently.
4. **Monolithic `run_loop()`** (TECH-DEBT-001) — 300+ lines, 60+ locals. Decomposition should be prioritized before any new features.
5. **No release workflow** (CI-CD-001) — v14.39.0 with no automated release process. This blocks users from consuming versioned artifacts.

### Long-term strategic direction

1. **Decompose the monolith** — Split `run_loop()` into focused, testable classes. Split `LoopConfig` into domain-specific config dataclasses. This unlocks parallel development and reduces regression risk.
2. **Structured worker communication** — Replace regex-on-ANSI-text parsing in `loop_manager.py` with structured NDJSON event consumption. The daemon already emits NDJSON; the web UI should consume it directly.
3. **Integration test suite** — Build a realistic mock `pi` CLI and test full iteration cycles end-to-end. This is the highest-leverage testing investment.
4. **Release automation** — Add a release workflow that gates on test suite passing, generates CHANGELOG, creates GitHub Release, and optionally publishes to PyPI.
5. **Cross-platform support** — The `/proc`-only system monitoring blocks macOS/BSD users. A provider pattern would enable graceful degradation.
6. **Typed state model** — Migrate from `state: dict` to `TypedDict`-based state models. This eliminates an entire class of runtime bugs at type-check time.

---

## Quick Reference

| Priority | Count |
|---|---|
| 🔴 **Critical** | 2 |
| 🟠 **High** | 8 |
| 🟡 **Medium** | 12 |
| 🔵 **Low** | 6 |
| **Total** | **28** |

| Category | Count |
|---|---|
| Bug | 6 |
| Technical Debt | 6 |
| Testing | 4 |
| Performance | 3 |
| Architecture | 3 |
| CI/CD | 2 |
| Security | 2 |
| Developer Experience | 2 |
| Documentation | 2 |
| Observability | 1 |

---

*This backlog is a living document. Items should be re-prioritized quarterly. The top 5 (BUG-001, TEST-001, TECH-DEBT-001, TECH-DEBT-002, CI-CD-001) represent the highest-value work for the next sprint.*
