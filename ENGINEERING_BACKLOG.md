# Engineering Backlog

> Living document — comprehensive engineering backlog for the pi-loop autonomous task automation daemon.
> Last updated: 2026-06-30
> Version: 14.39.0
> Audit sources: Git history (213 commits, 4-day project), full source analysis (53 .py files), security audit (Bandit + Safety + manual), dependency analysis, documentation assessment, developer experience evaluation.

---

## Priority Legend

| Code | Meaning |
|------|---------|
| **P0** | Critical — security vulnerability, data loss risk, blocking failure |
| **P1** | High — major feature gap, significant improvement, reliability risk |
| **P2** | Medium — important but not urgent; noticeable quality gap |
| **P3** | Low — nice to have; cosmetic or convenience improvement |
| **P4** | Future — long-term strategic direction; research required |

---

## Repository Overview

**pi-loop** is a self-contained Python daemon that runs tasks iteratively in a loop, tracks progress in a JSON ledger, and surfaces everything through a dark-theme web dashboard. It delegates each iteration to the [pi coding agent](https://pi.ai) and handles orchestration — convergence detection, error recovery, cooldown management, git auto-commit, multi-worker parallelism, and real-time monitoring via SSE.

### Architecture & Tech Stack

| Layer | Technology |
|---|---|
| **Language** | Python ≥3.10 (3.14.5 system), JavaScript (vanilla SPA) |
| **Web framework** | FastAPI 0.138.1 + Starlette 1.3.1 |
| **Server** | uvicorn 0.49.0 (with httptools, uvloop) |
| **Validation** | Pydantic 2.13.4 |
| **Frontend** | Vanilla HTML/CSS/JS (no framework), xterm.js for terminal, SSE for live updates |
| **Testing** | pytest 9.1, pytest-asyncio, pytest-cov, pytest-timeout (~460 tests across 24 test files) |
| **Linting** | Ruff 0.15.20 |
| **Type checking** | mypy 2.1.0 (available locally, NOT in CI) |
| **Security scanning** | bandit 1.9.4 + safety 3.8.1 |
| **Dependency management** | pip-tools (lock files for prod and dev) |
| **Pre-commit** | pre-commit 4.6.0 (available, hooks NOT configured) |

### Key Metrics

| Metric | Value |
|---|---|
| Source modules | 25 Python files (pi_loop/ + web_app/) |
| Test files | 24 test files |
| Total tests | ~460 |
| Test coverage target | ≥65% (CI-checked via Codecov) |
| CI Python matrix | 3.10, 3.11, 3.12, 3.13 |
| Production packages | 16 (pinned) |
| Dev/test packages | 67 (pinned) |
| Repository age | 4 days (213 commits) |
| Contributors | 2 (ningtoba: 208, pi-loop agent: 5) |
| Lint violations | 0 (Ruff) |
| Bandit findings | 1 HIGH (shell=True), 2 MEDIUM, 26 LOW |
| Security vulnerabilities | 0 (Safety scan) |

---

## Backlog Items

### BUG-001 — `_evolve_goal` writes `evolved_goal` to state but `run_loop` never reads it

- **Category:** bug
- **Priority:** P1 — High
- **Status:** COMPLETED ✅
- **Description:** Write side was complete — `_evolve_goal()` (lines 798–803) scans pi output for `NEXT_GOAL:` marker and writes `state["evolved_goal"]` — but the read side was missing entirely. A `state.pop("evolved_goal")` at `loop.py:558–563` now gates the feature behind the `--evolve` flag with clean fallback to the original `goal`. All 460 tests pass.
- **Resolution:** Read side wired at loop.py:558–563. Feature works end-to-end.
- **Files:** `pi_loop/loop.py`

---

### BUG-002 — `suppress(Exception)` silently swallows notification and HTTP callback failures

- **Category:** bug
- **Priority:** P1 — High
- **Impact:** High — notification failures and HTTP callback errors disappear without any log. If the callback server is down, credentials expire, or the notification command fails, operators never know.
- **Effort:** Small
- **Status:** pending
- **Description:** In `run_loop()`, the desktop notification block and HTTP callback block both use `with suppress(Exception):`. Any exception during notification dispatch or HTTP callback is silently swallowed, including connection errors, DNS failures, and invalid notification commands.
- **Verification:** Insert a deliberate HTTP callback to a non-routable IP/hostname. The error should appear at WARNING level in the log, not be silently swallowed.
- **Files:** `pi_loop/loop.py` (lines ~225, ~244)

---

### BUG-003 — `loop_manager.py` parses daemon stdout with regex on ANSI-colored text — fragile and lossy

- **Category:** bug / architecture
- **Priority:** P1 — High
- **Impact:** High — if daemon logging colors change, ANSI escape suppression changes, or log format varies, the web UI will silently lose iteration state tracking, worker status, and error classification.
- **Effort:** Medium
- **Status:** pending
- **Description:** `LoopManager._parse_line()` in `loop_manager.py` applies `_ANSI_ESCAPE.sub("", text)` to strip ANSI codes, then uses 6+ regex patterns (`re.search`) to extract worker status, duration, error type, heartbeat, and iteration data. This is fragile: a log format change (e.g., adding a timestamp prefix, changing bracket style) breaks all parsers silently. Regex patterns include `r"\[TERM.*?\]"`, `r"\[WORKER"`, `r"\[BEAT\]"`, `r"\[ERROR-TYPE\]"`.
- **Verification:** Run daemon with a different `--log-format` or add a timestamp prefix. Check whether the web UI still tracks iteration state correctly.
- **Files:** `web_app/loop_manager.py`, `web_app/server.py` (SSE streaming), `pi_loop/loop.py`

---

### BUG-004 — `status.py` uptime calculation uses undocumented `os.sysconf_names` — may crash on non-Linux platforms

- **Category:** bug
- **Priority:** P2 — Medium
- **Impact:** Medium — `write_status()` computes uptime from `/proc/[pid]/stat` using `os.sysconf_names["SC_CLK_TCK"]` (an undocumented CPython internal). On alternative Python implementations or restricted environments, this raises `KeyError`.
- **Effort:** Small
- **Status:** pending
- **Description:** `status.py` line ~48: `clock_ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])`. Also relies on `/proc` and field offset 21 in `/proc/pid/stat`. On macOS, BSD, or Windows, this crashes with `FileNotFoundError` or `KeyError`.
- **Solution:** Store process start time at daemon init and compute uptime as `time.time() - start_time`. Much simpler and cross-platform.
- **Files:** `pi_loop/status.py`, `pi_loop/system_utils.py`

---

### BUG-005 — `classify_error()` misses common timeout and network error patterns

- **Category:** bug
- **Priority:** P2 — Medium
- **Impact:** Medium — misclassified errors mean the adaptive error recovery engine applies the wrong mitigation strategy. A timeout misclassified as "unknown" gets elevated cooldown but no timeout extension. A network error misclassified as "unknown" bypasses exponential backoff entirely.
- **Effort:** Small
- **Status:** pending
- **Description:** `classify_error()` in `error_utils.py` checks `"timeout"` and `"timed out"` but misses `"timedout"`, `"time_out"`, `"read timed out"`, `"connection timed out"`. The network category misses `"name or service not known"`, `"temporary failure"`, `"name resolution"`, `"no address"`, `"protocol error"`, `"ssl_error"`, `"handshake"`.
- **Verification:** Unit-test each missing pattern. Verify the error classifier correctly routes them to the "timeout" or "network" category.
- **Files:** `pi_loop/error_utils.py`

---

### BUG-006 — `extract_json_from_output()` backward-scan priority may return stale JSON before forward scan completes

- **Category:** bug
- **Priority:** P3 — Low
- **Impact:** Low — The function runs two strategies: (1) reverse scan returns on first valid `{}` block, (2) forward scan collects all JSON and returns last. If the reverse scan finds a valid but incomplete/outdated `{}` bridge from a previous message, it returns that instead of the more reliable forward-scan result.
- **Effort:** Small
- **Status:** pending
- **Description:** `extract_json_from_output()` in `file_utils.py` first scans backwards for the LAST JSON object using brace-depth counting, returning immediately on success. If that brace-counting scan finds a premature match (a substring that happens to balance `{}` but isn't valid JSON), it returns it. The forward scan (strategy 2) validates via `json.loads()` but may never run.
- **Solution:** Reverse priority: run the validated forward scan first; fall back to brace-counting backward scan only if forward scan yields nothing.
- **Files:** `pi_loop/file_utils.py`

---

### BUG-007 — `shell=True` on user-configurable `on_error_cmd` at loop.py:727

- **Category:** security / bug
- **Priority:** P2 — Medium
- **Impact:** Medium — Bandit B602: `subprocess.run(on_error_cmd, shell=True, timeout=30)` at loop.py:727 runs a user-configured shell command with `shell=True`. While this is an intentional feature (user-configurable error handling), if an attacker gains write access to `~/.config/pi-loop/config.json`, they can execute arbitrary shell commands with daemon privileges.
- **Effort:** Small
- **Status:** pending
- **Description:** The `on_error_cmd` value comes from `config.json` or `--on-error-cmd` flag. Document the risk explicitly. Consider validating the command (length/character restrictions) or at minimum logging the full command before execution.
- **Mitigation:** Validate `on_error_cmd` is a simple command path (no pipes, redirects, or semicolons). Log the exact command before execution. Expand "shell=True risk" in README security section.
- **Files:** `pi_loop/loop.py`

---

### BUG-008 — No URL scheme validation for `http_callback` — `file://`/`data://` abuse possible

- **Category:** security / bug
- **Impact:** Medium — Bandit B310: `urllib.request.urlopen(req, timeout=10)` at loop.py:720 (approximately) accepts a user-configurable `http_callback` URL with no scheme validation. A `file://` URL could read local files; a `data://` or custom scheme could cause unexpected behavior.
- **Priority:** P2 — Medium
- **Effort:** Small
- **Status:** pending
- **Description:** The `http_callback` URL from config must be restricted to `http://` and `https://` schemes. Add a `urlparse` check that rejects non-HTTP schemes with a clear error/warning.
- **Files:** `pi_loop/loop.py`

---

### BUG-009 — `config_file.apply_to_environ()` uses `setdefault` — config file changes may be silently ignored

- **Category:** bug
- **Priority:** P3 — Low
- **Impact:** Low — `apply_to_environ()` uses `os.environ.setdefault(key, str(value))`. If a `.env` file or previous call already set a value, later calls will NOT override it. Users changing config file settings may expect changes to take effect in the running daemon.
- **Effort:** Small
- **Status:** pending
- **Description:** Document the precedence order explicitly: (1) existing `os.environ`, (2) `apply_to_environ()` (setdefault), (3) `.env` file. Consider adding a `force` parameter to allow overriding existing values.
- **Files:** `pi_loop/config_file.py`

---

### TECH-DEBT-001 — `run_loop()` monolithic 300+ line function with 60+ local variables

- **Category:** refactoring / architecture
- **Priority:** P0 — Critical
- **Impact:** Critical — The function handles shutdown, git state capture, notification dispatch, error recovery adaptation, cooldown logic, dashboard HTML generation, HTTP callbacks, goal cycling, convergence detection, and heartbeat management. Every new feature requires touching this function, increasing risk of regressions. Testability is near-zero since mocking 60+ local variables is impractical.
- **Effort:** X-Large
- **Status:** pending
- **Description:** Decompose `run_loop()` into focused classes/modules:
  - `IterationEngine` — iteration loop control, worker spawning, convergence detection
  - `NotificationDispatcher` — desktop notifications, PushBullet, ntfy callbacks
  - `DashboardBuilder` — HTML report generation
  - `ConvergenceDetector` — repetition detection, convergence thresholds
  - `GoalCycler` — goals file management, evolution coordination
  - `CooldownManager` — fixed and adaptive cooldown, backoff
- **Files:** `pi_loop/loop.py`

---

### TECH-DEBT-002 — `LoopConfig` god dataclass with 63 fields

- **Category:** refactoring / architecture
- **Priority:** P1 — High
- **Impact:** High — Every new config option adds a field to this single dataclass. `from_args()` uses `getattr` on argparse namespace with implicit field discovery, making it hard to track which fields are used where.
- **Effort:** Medium
- **Status:** pending
- **Description:** Split `LoopConfig` into focused config dataclasses:
  - `CoreConfig` — goal, context, workdir
  - `IterationConfig` — max_iterations, cooldown, convergence params
  - `WorkerConfig` — workers, timeout, retries
  - `GitConfig` — git, git_commit, store_git_diff
  - `NotificationConfig` — notify_cmd, pushbullet, ntfy
  - `WebConfig` — html_dashboard, status_file, webhook_port
  - `ArchiveConfig` — keep_iterations, archive_dir, retention
  Use composition in a top-level config object.
- **Files:** `pi_loop/config.py`, `pi_loop/loop.py`, `pi_loop/cli.py`

---

### TECH-DEBT-003 — `_log_startup_banner()` has 30 parameters

- **Category:** refactoring
- **Priority:** P1 — High
- **Impact:** Medium — Every new daemon option requires adding a parameter to this function's signature. Six underscore-prefixed parameters suggest they should be private.
- **Effort:** Small
- **Status:** pending
- **Description:** Accept `LoopConfig` dataclass instead of 30 individual parameters. Reduces signature to 2 params (`cfg: LoopConfig, quiet: bool = False`) and ensures new config fields are automatically reflected in the startup banner.
- **Files:** `pi_loop/functions.py`

---

### TECH-DEBT-004 — Two env var naming conventions (`PI_LOOP_*` and `INFINITE_LOOP_*`)

- **Category:** developer-experience / refactoring
- **Priority:** P2 — Medium
- **Impact:** Medium — Newer runtime paths use `PI_LOOP_*` while the web UI's config system uses `INFINITE_LOOP_*`. A user reading `PI_LOOP_DATA_DIR` won't find `INFINITE_LOOP_GOAL` in the same namespace.
- **Effort:** Medium
- **Status:** pending
- **Description:** Standardize on `PI_LOOP_*`. Migrate `INFINITE_LOOP_*` with backward-compatible aliases. Deprecate old names with clear warnings.
- **Files:** `pi_loop/config_file.py`, `pi_loop/env_utils.py`, `web_app/config_manager.py`, `README.md`

---

### TECH-DEBT-005 — `loop_manager.py` keeps an open `_log_fp` file handle across the daemon's full lifecycle

- **Category:** technical-debt
- **Priority:** P2 — Medium
- **Impact:** Medium — `_log_fp` is opened lazily and never closed during normal operation. On long-running daemon sessions, the FD stays open. If the log file is externally rotated, writes go to a stale inode.
- **Effort:** Small
- **Status:** pending
- **Description:** Use a file handle that re-opens on each write (or every N writes) to handle log rotation gracefully. Eliminate `__del__`-based cleanup.
- **Files:** `web_app/loop_manager.py`

---

### TECH-DEBT-006 — `state: dict` used everywhere instead of typed state model

- **Category:** refactoring / type-safety
- **Priority:** P2 — Medium
- **Impact:** Medium — The ledger state is `dict` everywhere with string-key access. Key typos (`"iterations"` vs `"iteration"`) are runtime errors. The state shape spans 20+ keys including nested dicts.
- **Effort:** Medium
- **Status:** pending
- **Description:** Define `TypedDict` classes: `LedgerState`, `IterationRecord`, `StatsRecord`, `ErrorTypeCounts`, `MitigationState`, `GoalTrackingState`. Use in all state-read/write paths. Catches key errors at mypy-check time.
- **Files:** `pi_loop/state.py`, `pi_loop/loop.py`, `pi_loop/stats.py`, `pi_loop/file_utils.py`, `pi_loop/cli.py`, `web_app/loop_manager.py`

---

### TECH-DEBT-007 — No structured logging — all output is `print()` and `logger.info()` with unformatted strings

- **Category:** observability / technical-debt
- **Priority:** P2 — Medium
- **Impact:** Medium — All daemon logging uses bare `print()` calls and `logger.info(f"...")` with inline string formatting. No structured fields (event type, correlation ID, iteration number, error code). The web UI's regex-based parsers are a direct consequence of this.
- **Effort:** Medium
- **Status:** pending
- **Description:** Introduce structured logging with `structlog` or `logging.StructuredMessage` (Python 3.14+). Key fields: `event`, `iteration`, `worker_id`, `error_code`, `duration_ms`, `goal_hash`. Preserve human-readable console output for terminal users.
- **Files:** `pi_loop/loop.py`, `pi_loop/error_recovery.py`, `pi_loop/heartbeat.py`, `pi_loop/config.py` (log setup)

---

### TECH-DEBT-008 — No `docs/` directory — documentation scattered across top-level files

- **Category:** documentation / developer-experience
- **Priority:** P2 — Medium
- **Impact:** Medium — Critical documentation is embedded in `REFACTOR_PLAN.md` (the best API/architecture guide) and `.worktrees/` (30+ research documents). New contributors must read multiple top-level files to understand the system.
- **Effort:** Medium
- **Status:** pending
- **Description:** Create `docs/` directory with:
  - `docs/architecture.md` — merge from REFACTOR_PLAN.md, README, and worktree findings
  - `docs/api.md` — REST endpoints, SSE protocol, rate limiting headers
  - `docs/configuration.md` — all config options, env vars, JSON schema
  - `docs/development.md` — dev setup, testing guide, common issues
  - `docs/security.md` — auth, rate limiting, CORS, security model
- **Files:** `docs/` (new), `web_app/REFACTOR_PLAN.md`, `README.md`

---

### TECH-DEBT-009 — `REFACTOR_PLAN.md` is mislabeled — it's the primary architecture and API guide

- **Category:** documentation
- **Priority:** P3 — Low
- **Impact:** Low — `web_app/REFACTOR_PLAN.md` contains the best documentation of the web app's architecture (20+ REST endpoints, SSE protocol, subprocess lifecycle, config persistence, path resolution, themes). The name "refactor plan" hides this from new contributors.
- **Effort:** Small
- **Status:** pending
- **Description:** Rename to something descriptive (e.g., `docs/web-app-architecture.md`) and link from README.
- **Files:** `web_app/REFACTOR_PLAN.md`

---

### ARCH-001 — Web server middleware runs rate limiter AFTER auth but BEFORE CORS — 429 responses lack CORS headers

- **Category:** architecture / bug
- **Priority:** P2 — Medium
- **Impact:** Medium — FastAPI middleware executes in reverse registration order. `CORSMiddleware` is added first, then `api_key_auth`, then `rate_limit_middleware`. When rate_limit returns 429, it does NOT add CORS headers. Browsers making cross-origin requests see CORS errors instead of the 429 body.
- **Effort:** Small
- **Status:** pending
- **Description:** Either add CORS headers in the rate limiter middleware or reorder middleware so CORS runs outermost. Verify with a browser cross-origin fetch to an endpoint that hits the rate limit.
- **Files:** `web_app/server.py`

---

### ARCH-002 — All agent orchestration lives in a single while-loop with no state machine abstraction

- **Category:** architecture
- **Priority:** P2 — Medium
- **Impact:** Medium — The main loop in `run_loop()` is a flat `while True` with condition checks. Loop states (running, paused, stopped, error) are managed via sentinel file checks and `_shutdown_requested` Event. No explicit state machine makes it hard to add new states (draining, backoff).
- **Effort:** Medium
- **Status:** pending
- **Description:** Introduce a `LoopStateMachine` class with explicit states (IDLE, RUNNING, COOLDOWN, ERROR, STOPPING) and transitions. Each state has an `enter()` and `exit()` hook.
- **Files:** `pi_loop/loop.py`

---

### ARCH-003 — `os.sysconf_names` and `/proc` usage ties system monitoring to Linux only

- **Category:** architecture
- **Priority:** P2 — Medium
- **Impact:** Medium — CPU/memory monitoring reads `/proc/[pid]/status`, `/proc/meminfo`, and `/proc/pid/stat`. These only exist on Linux. On macOS/BSD, endpoints crash with `FileNotFoundError`.
- **Effort:** Medium
- **Status:** pending
- **Description:** Create abstract `SystemResourceProvider` interface with `LinuxProvider` (current /proc-based), `MacOSProvider` (uses `psutil` or `os.popen("ps")`), and `NoopProvider`. Auto-detect platform at startup.
- **Files:** `pi_loop/system_utils.py`, `pi_loop/status.py`, `pyproject.toml` (optional psutil dep)

---

### ARCH-004 — Web UI reads ledger JSON file directly instead of using IPC or an API contract

- **Category:** architecture
- **Priority:** P2 — Medium
- **Impact:** Medium — The web UI reads `/tmp/infinite-loop-state.json` and `loop-status.json` directly from the filesystem. This couples the web UI to the daemon's file layout, serialization format, and temporary directory location. Any change to the ledger format breaks the web UI silently.
- **Effort:** Large
- **Status:** pending
- **Description:** Replace filesystem-based state sharing with a proper IPC mechanism:
  - Option A: The daemon exposes a local HTTP API (separate port) that the web server queries.
  - Option B: The daemon writes structured NDJSON events to a pipe/socket that the web server consumes.
  - Option C: Use an in-memory shared data structure when both run in the same process.
  This also eliminates the O(n) re-read on every SSE poll cycle.
- **Files:** `pi_loop/loop.py` (status/ledger writes), `web_app/server.py` (SSE poller), `web_app/loop_manager.py`

---

### ARCH-005 — No FastAPI dependency injection for shared state (LoopManager, RateLimiter)

- **Category:** architecture
- **Priority:** P3 — Low
- **Impact:** Low — `web_app/server.py` uses module-level global variables (`loop_manager`, `rate_limiter`) instead of FastAPI's `Depends()` with dependency injection. This makes testing harder and prevents per-request-scoped dependencies.
- **Effort:** Small
- **Status:** pending
- **Description:** Migrate shared state to FastAPI `Depends()` with lifespan-scoped singletons. Makes endpoints independently testable with injected mocks.
- **Files:** `web_app/server.py`

---

### ARCH-006 — No graceful shutdown for web server (SIGTERM/SIGINT handler)

- **Category:** architecture
- **Priority:** P3 — Low
- **Impact:** Low — `web_app/server.py` does not register a shutdown handler. On SIGTERM (e.g., from systemd or container orchestrator), the uvicorn process exits abruptly without cleaning up subprocesses or closing the SSE stream. The loop daemon's subprocess may become orphaned.
- **Effort:** Small
- **Status:** pending
- **Description:** Register a FastAPI `shutdown` event handler that stops the loop daemon process, closes the log file handle, and sends a final SSE "shutdown" event to all connected clients.
- **Files:** `web_app/server.py`, `web_app/loop_manager.py`

---

### TEST-001 — Zero integration tests for the core `pi` subprocess spawning

- **Category:** testing
- **Priority:** P0 — Critical
- **Impact:** Critical — The core value proposition (subprocess task execution via `pi`) has zero end-to-end verification. All ~460 tests are unit tests that mock subprocess calls. A real `pi` binary change (flag rename, output format change, mode=json breaking change) goes undetected until production.
- **Effort:** Medium
- **Status:** pending
- **Description:** Create `tests/integration/` with a `mock_pi.sh` script that emits realistic NDJSON output. Test: single iteration success, convergence detection with repeated output, error recovery with injected failures, sentinel stop/pause, multi-worker parallelism. Mark integration tests with `@pytest.mark.integration`. Run as a separate CI job.
- **Files:** `tests/conftest.py`, `tests/integration/` (new), `pi_loop/loop.py`, `pi_loop/functions.py`

---

### TEST-002 — `config_file.py` has no test coverage (7 functions, 0 tests)

- **Category:** testing
- **Priority:** P1 — High
- **Impact:** Medium — `config_file.py` handles config persistence, backup/restore, atomic writes, and env var application. Zero tests. Config file corruption can leave the daemon in an unrecoverable state.
- **Effort:** Small
- **Status:** pending
- **Description:** Write tests for: `load_config()` with missing/corrupted/backup files, `save_config()` atomic write, `_atomic_write()` crash recovery, `apply_to_environ()` env var application, `get_bool()` truthiness parsing, `ensure_config_dir()` directory creation.
- **Files:** `pi_loop/config_file.py`, `tests/test_config_file.py`

---

### TEST-003 — `web_app/rate_limiter.py` has no test coverage

- **Category:** testing
- **Priority:** P2 — Medium
- **Impact:** Medium — The sliding-window rate limiter protects all API endpoints. Zero tests. A bug can either open the API to abuse or block legitimate usage.
- **Effort:** Small
- **Status:** pending
- **Description:** Write tests for: `check()` allowing requests within limit, `check()` blocking at limit, timestamp trimming (expired entries removed), `remaining()` accuracy, `reset()` per-IP/global, concurrent coroutine access.
- **Files:** `web_app/rate_limiter.py`, `tests/test_rate_limiter.py` (new)

---

### TEST-004 — `pi_loop/validation.py` has minimal test coverage

- **Category:** testing
- **Priority:** P2 — Medium
- **Impact:** Low — `load_json_schema()` handles file loading error cases but has no tests for edge conditions: empty files, non-JSON files, permissions errors, symlink loops.
- **Effort:** Small
- **Status:** pending
- **Description:** Add tests for: valid JSON schema loading, invalid JSON, empty file, non-JSON content, missing file, permission denied (if testable), non-dict JSON.
- **Files:** `pi_loop/validation.py`, `tests/test_validation.py` (new)

---

### TEST-005 — `pi_loop/color_utils.py` has no dedicated test coverage

- **Category:** testing
- **Priority:** P3 — Low
- **Impact:** Low — `Colorizer` class with 3 methods, `strip_ansi()`, and terminal detection. No dedicated tests. `strip_ansi()` uses a limited regex pattern (see SEC-001).
- **Effort:** Small
- **Status:** pending
- **Description:** Test: `strip_ansi()` with various CSI sequences, `Colorizer.method` coloring, terminal detection with mocked `os.isatty`.
- **Files:** `pi_loop/color_utils.py`, `tests/test_color_utils.py` (new)

---

### TEST-006 — No web server endpoint tests for SSE, config CRUD, system info, worker lifecycle

- **Category:** testing
- **Priority:** P2 — Medium
- **Impact:** Medium — `web_app/server.py` has 20+ REST endpoints and SSE streaming. Existing tests (`test_server.py`) cover auth and some CRUD, but SSE streaming, config CRUD with validation, system info endpoints, and worker lifecycle endpoints have minimal or no coverage.
- **Effort:** Medium
- **Status:** pending
- **Description:** Add `httpx2` async tests for: SSE `/api/events` stream parsing and heartbeat delivery, config POST/PUT with invalid values, worker lifecycle (start/stop/pause/resume), system info endpoint. Target ≥75% coverage on `server.py`.
- **Files:** `web_app/server.py`, `tests/test_server.py`

---

### TEST-007 — No CLI parser unit tests for all flag combinations

- **Category:** testing
- **Priority:** P2 — Medium
- **Impact:** Medium — `pi_loop/parser.py` has 20+ CLI flags with complex interactions (mutual exclusion, dependencies, defaults). Dedicated parser tests (`test_parser.py`) cover basic parsing but not edge cases like flag conflicts, type coercion failures, or `--help` override.
- **Effort:** Small
- **Status:** pending
- **Description:** Add parser tests for: mutually exclusive flags (e.g., `--goal` vs `--goals-file`), type coercion edge cases, default value propagation, env var override priority, `--help` with specific topics.
- **Files:** `pi_loop/parser.py`, `tests/test_parser.py`

---

### TEST-008 — `pi_loop/env_utils.py` has no test coverage (500+ lines, 0 tests)

- **Category:** testing
- **Priority:** P2 — Medium
- **Impact:** Medium — `env_utils.py` at ~500 lines is the largest module in `pi_loop/` with functions for env var management, .env file parsing, variable validation, and `KNOWN_ENV_VARS` (100+ entries). Zero tests despite complex string parsing and dict manipulation.
- **Effort:** Medium
- **Status:** pending
- **Description:** Write tests for: `load_dotenv()` with various .env file formats, `check_env_file()` unknown var detection, `apply_to_environ()` env var precedence, `KNOWN_ENV_VARS` consistency, deprecated var warnings.
- **Files:** `pi_loop/env_utils.py`, `tests/test_env_utils.py` (new)

---

### PERF-001 — `/api/logs` endpoint re-parses the entire log file on every request

- **Category:** performance
- **Priority:** P2 — Medium
- **Impact:** Medium — Each GET `/api/logs` triggers `LoopManager._hydrate_from_log_file()` which reads the entire persisted log file and re-parses all entries. The SSE poller calls this every ~2s. Log files grow linearly with daemon uptime.
- **Effort:** Small
- **Status:** pending
- **Description:** Cache parsed log entries and append-only read new lines on subsequent requests (track file position via `tell()`). Makes per-poll overhead O(1) instead of O(n).
- **Files:** `web_app/loop_manager.py`, `web_app/server.py` (SSE status poller)

---

### PERF-002 — SSE status poller reads the entire ledger JSON file every 2 seconds

- **Category:** performance
- **Priority:** P2 — Medium
- **Impact:** Medium — The `_status_poller()` background task reads `loop-status.json` and `loop-manager-status.json` every ~2 seconds. The JSON ledger is re-read and re-parsed each cycle even when unchanged. Ledger only changes once per iteration (potentially minutes apart).
- **Effort:** Small
- **Status:** pending
- **Description:** Track ledger file mtime. Skip re-parsing if unchanged. Move mtime check before JSON parse (current `last_status_hash` mechanism still parses before hashing).
- **Files:** `web_app/server.py`

---

### PERF-003 — `write_ledger()` acquires a file lock and writes the full ledger on every iteration

- **Category:** performance
- **Priority:** P3 — Low
- **Impact:** Low — Each iteration triggers full JSON serialization and file write of the entire state dict. For configurations with many archived iterations (e.g., `--keep-iterations 500`), this serializes 500+ history records each cycle.
- **Effort:** Medium
- **Status:** pending
- **Description:** Consider append-only iteration log (JSON Lines), with metadata file rewritten only when metadata changes. Hybrid approach: JSON Lines for history + compact JSON for metadata.
- **Files:** `pi_loop/file_utils.py`, `pi_loop/loop.py`

---

### PERF-004 — Large dev dependency graph (67 packages) slows CI installs

- **Category:** performance / ci-cd
- **Priority:** P3 — Low
- **Impact:** Low — `requirements-dev.txt` contains 67 packages including transitive deps. CI spends significant time installing these on every run. Many are conditionally useful (safety, pre-commit, coverage).
- **Effort:** Small
- **Status:** pending
- **Description:** Split dev deps into tiers: `dev-core` (pytest, ruff, mypy), `dev-security` (bandit, safety), `dev-all` (everything). CI can install only what each job needs. Use pip-compile with `--extra dev-core --extra dev-security` to produce tiered lock files.
- **Files:** `pyproject.toml`, `requirements-dev.txt`, `.github/workflows/ci.yml`

---

### SEC-001 — `strip_ansi()` only strips `m`-terminated escape sequences, not all ANSI

- **Category:** bug / security
- **Priority:** P2 — Medium
- **Impact:** Medium — `color_utils.strip_ansi()` uses `r"\033\[[0-9;]*m"` which only strips CSI sequences ending in `m` (SGR). Other ANSI escapes (cursor movement `[A`, clear screen `[2J`, scroll `[S`) pass through, appearing as raw control characters in logs and web UI.
- **Effort:** Small
- **Status:** pending
- **Description:** Use comprehensive ANSI escape regex: `r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"` (already defined as `_ANSI_ESCAPE` in `loop_manager.py` — reuse from shared location).
- **Files:** `pi_loop/color_utils.py`, `pi_loop/file_utils.py`, `web_app/loop_manager.py`

---

### SEC-002 — API key is loaded from environment at middleware call time, not server startup

- **Category:** security
- **Priority:** P3 — Low
- **Impact:** Low — The `api_key_auth` middleware reads `PI_LOOP_API_KEY` from `os.environ` on every HTTP request. If the env var changes after startup (possible in container orchestration), authentication behavior changes without warning. More critically, if the var is accidentally unset, auth silently disables.
- **Effort:** Small
- **Status:** pending
- **Description:** Read `PI_LOOP_API_KEY` once at startup (in `main()`) and pass as a closure variable. Log a warning if auth is enabled/disabled at startup.
- **Files:** `web_app/server.py`

---

### SEC-003 — Missing HTTP security headers (CSP, X-Frame-Options, X-Content-Type-Options, HSTS)

- **Category:** security
- **Priority:** P2 — Medium
- **Impact:** Medium — The web server does not set Content-Security-Policy, X-Frame-Options, or X-Content-Type-Options headers. If any user-controlled content is rendered (e.g., iteration results in dashboard), XSS clickjacking and MIME-sniffing attacks are possible. Recent XSS fixes mitigate stored XSS, but defense-in-depth headers are missing.
- **Effort:** Small
- **Status:** pending
- **Description:** Add FastAPI middleware that sets:
  - `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline';`
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `X-XSS-Protection: 0` (deprecated but suppresses legacy browser warnings)
- **Files:** `web_app/server.py`

---

### SEC-004 — No `TrustedHostMiddleware` to prevent host header injection

- **Category:** security
- **Priority:** P3 — Low
- **Impact:** Low — FastAPI's `TrustedHostMiddleware` prevents Host header attacks (cache poisoning, password reset poisoning). Not currently used.
- **Effort:** Small
- **Status:** pending
- **Description:** Add `TrustedHostMiddleware(allowed_hosts=["localhost", "127.0.0.1", "*.pi-loop.local"])`.
- **Files:** `web_app/server.py`

---

### SEC-005 — No `SECURITY.md` file for vulnerability disclosure

- **Category:** security
- **Priority:** P3 — Low
- **Impact:** Low — The project has API-key auth, rate limiting, HMAC webhooks, and security scanning, but no security policy file. Contributors and users have no guidance on reporting vulnerabilities.
- **Effort:** Small
- **Status:** pending
- **Description:** Create `SECURITY.md` with supported versions, how to report vulnerabilities (email, GitHub private vulnerability reporting), and disclosure policy.
- **Files:** `SECURITY.md` (new)

---

### SEC-006 — No `CODE_OF_CONDUCT.md` for community guidelines

- **Category:** community / documentation
- **Priority:** P4 — Future
- **Impact:** Low — Standard for open-source community projects. Not urgent for a project with 2 contributors.
- **Effort:** Small
- **Status:** pending
- **Description:** Create `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1).
- **Files:** `CODE_OF_CONDUCT.md` (new)

---

### SEC-007 — `.env` entry is commented out in `.gitignore` — no protection against accidental secret commits

- **Category:** security
- **Priority:** P2 — Medium
- **Impact:** Medium — The `.gitignore` has a commented `.env` entry (line: `# .env`). The project uses JSON config instead of `.env`, but if someone creates a `.env` locally with secrets (API keys, tokens), it would NOT be protected by `.gitignore`.
- **Effort:** Trivial
- **Status:** pending
- **Description:** Un-comment or add `.env` to `.gitignore` as a defense-in-depth safety net.
- **Files:** `.gitignore`

---

### SEC-008 — No secrets scanner in CI pipeline

- **Category:** ci-cd / security
- **Priority:** P3 — Low
- **Impact:** Low — The CI pipeline has lint, test, coverage, and security (bandit + safety) jobs, but no secrets scanner to detect accidentally committed API keys, tokens, or credentials.
- **Effort:** Small
- **Status:** pending
- **Description:** Add `truffleHog` or `ggshield` scan to the CI security job. Run on `git log --all --diff-filter=A --name-only` to scan all history, not just the latest commit.
- **Files:** `.github/workflows/ci.yml`

---

### CI-CD-001 — No release workflow (tag → build → publish)

- **Category:** ci-cd
- **Priority:** P1 — High
- **Impact:** High — Version 14.39.0 with a comprehensive test suite but no automated release process. Releases are manual (change version, tag, push). No GitHub Release creation, no PyPI publish, no changelog generation.
- **Effort:** Medium
- **Status:** pending
- **Description:** Create `.github/workflows/release.yml` triggered on version tags (`v*`). Steps: build package (`python -m build`), run full test suite, verify lock files match, create GitHub Release with auto-generated changelog, optionally publish to PyPI.
- **Files:** `.github/workflows/release.yml` (new), `pyproject.toml`

---

### CI-CD-002 — `httpx` (safety dependency) and `httpx2` (test dependency) may conflict

- **Category:** ci-cd
- **Priority:** P2 — Medium
- **Impact:** Low — `requirements-dev.txt` lists both `httpx==0.28.1` (pulled by safety) and `httpx2==2.5.0` (test dep). `httpx2` has its own `httpcore2` dependency. While theoretically separated, undetected import-time conflicts cause mysterious CI failures.
- **Effort:** Small
- **Status:** pending
- **Description:** Investigate coexistence. `httpx2` uses `httpcore2` (dependency-separated), so in theory they don't conflict. Verify this explicitly and add a CI check or `pip check` step. If they do conflict, replace `httpx` with `httpx2`-only approach.
- **Files:** `requirements-dev.txt`, `pyproject.toml`

---

### CI-CD-003 — No mypy type checking in CI pipeline

- **Category:** ci-cd
- **Priority:** P2 — Medium
- **Impact:** Medium — mypy 2.1.0 is installed in dev deps and configured in `pyproject.toml`, but the CI pipeline does not run it. Type errors that mypy would catch (e.g., wrong return types, missing attrs on `dict`) pass CI silently.
- **Effort:** Small
- **Status:** pending
- **Description:** Add a `mypy` step to the CI lint job, or create a separate `type-check` job. Run `mypy pi_loop/ web_app/`. Fail CI on errors. Configure `--strict` incrementally.
- **Files:** `.github/workflows/ci.yml`, `pyproject.toml` (mypy config)

---

### CI-CD-004 — No Dependabot configuration for automated dependency updates

- **Category:** ci-cd / dependencies
- **Priority:** P2 — Medium
- **Impact:** Medium — No automated dependency update tooling. Dependencies are manually updated via `make update-lock` (pip-compile). The project uses `requirements.txt` + `requirements-dev.txt` pin files perfectly suited for Dependabot.
- **Effort:** Small
- **Status:** pending
- **Description:** Create `.github/dependabot.yml` with:
  - Weekly schedule (Monday)
  - pip ecosystem (directories: `/`)
  - Max 10 open PRs
  - Labels: `dependencies`, `automated`
  - Reviewers: ningtoba
- **Files:** `.github/dependabot.yml` (new)

---

### CI-CD-005 — Safety uses deprecated `check` command; should migrate to `scan`

- **Category:** ci-cd
- **Priority:** P3 — Low
- **Impact:** Low — `make security` uses `safety check -r requirements.txt -r requirements-dev.txt --continue-on-error`. The `check` command is deprecated in Safety 3.x; the recommended replacement is `safety scan`.
- **Effort:** Small
- **Status:** pending
- **Description:** Migrate to `safety scan -r requirements.txt -r requirements-dev.txt --continue-on-error`. Update Makefile and CI.
- **Files:** `Makefile`, `.github/workflows/ci.yml`

---

### CI-CD-006 — No smoke test stage in CI for `pi-loop`/`pi-loop-web` entry points

- **Category:** ci-cd
- **Priority:** P3 — Low
- **Impact:** Low — CI runs lint, test, coverage, and security jobs, but does not verify that the installed package actually starts. A broken entry point (e.g., typo in `console_scripts`, import error in `__main__`) would only be caught when a user runs the CLI.
- **Effort:** Small
- **Status:** pending
- **Description:** Add a CI step that: (1) `pip install -e .`, (2) `pi-loop --help` (exit code 0), (3) `pi-loop-web --help` (exit code 0). Mark smoke tests explicitly in test files with `@pytest.mark.smoke`.
- **Files:** `.github/workflows/ci.yml`

---

### CI-CD-007 — No Docker image build or publish workflow

- **Category:** ci-cd
- **Priority:** P4 — Future
- **Impact:** Low — Docker is available (v29.5.2) but no Dockerfile exists. The architecture is container-friendly (all paths configurable via env vars, configurable network binding).
- **Effort:** Medium
- **Status:** pending
- **Description:** Create a multi-stage Dockerfile: build stage (pip install -e .), runtime stage (distroless Python). Add CI job to build and optionally publish to GitHub Container Registry.
- **Files:** `Dockerfile` (new), `.dockerignore` (new), `.github/workflows/ci.yml`

---

### DX-001 — No `.pre-commit-config.yaml` despite pre-commit being a dev dependency

- **Category:** developer-experience
- **Priority:** P2 — Medium
- **Impact:** Medium — `pre-commit==4.6.0` is in dev deps, `Makefile` has `pre-commit` and `pre-commit-run` targets, and CONTRIBUTING.md references pre-commit — but no `.pre-commit-config.yaml` exists. Running `pre-commit install` installs no hooks. New contributors assume the repo doesn't use pre-commit.
- **Effort:** Small
- **Status:** pending
- **Description:** Create `.pre-commit-config.yaml` with hooks: `ruff` (lint + format), `trailing-whitespace`, `end-of-file-fixer`, `check-json`, `check-yaml`, `check-toml`, `check-merge-conflict`, `detect-private-key`, `check-added-large-files` (500KB). Do NOT add mypy (too slow for commit-time).
- **Files:** `.pre-commit-config.yaml` (new), `Makefile`, `CONTRIBUTING.md`

---

### DX-002 — Stale env var detection: `KNOWN_ENV_VARS` has 100+ entries with no deprecation mechanism

- **Category:** developer-experience
- **Priority:** P3 — Low
- **Impact:** Low — `KNOWN_ENV_VARS` is a manually maintained set. Deprecated vars accumulate. `check_env_file()` uses `difflib` to suggest corrections but doesn't warn about deprecated vars still in use.
- **Effort:** Small
- **Status:** pending
- **Description:** Add `DEPRECATED_ENV_VARS` dict mapping old names to replacements. In `check_env_file()`, emit warnings with migration instructions. Remove vars replaced by `PI_LOOP_*` equivalents.
- **Files:** `pi_loop/env_utils.py`

---

### DX-003 — No `.env.example` or `.env.template` for quick configuration reference

- **Category:** developer-experience
- **Priority:** P3 — Low
- **Impact:** Low — The project uses JSON config (recommended) and optional .env support. No template file exists for users who prefer `.env`. The worktrees contain `.env.example` files with commented-out documentation.
- **Effort:** Small
- **Status:** pending
- **Description:** Create `.env.example` listing all supported env vars with their `PI_LOOP_*` canonical names, default values, and short descriptions. Link from README quick start.
- **Files:** `.env.example` (new), `README.md`

---

### DX-004 — No Dockerfile or Docker Compose for containerized development

- **Category:** developer-experience
- **Priority:** P4 — Future
- **Impact:** Low — Docker v29.5.2 is available but the project has no container setup. Developers must install Python ≥3.10 and pip deps locally. No Docker Compose for running daemon + web server + optional database.
- **Effort:** Medium
- **Status:** pending
- **Description:** Create `Dockerfile` (multi-stage, distroless runtime) and `docker-compose.yml` (web + daemon service). Link from README as "Docker Quick Start".
- **Files:** `Dockerfile` (new), `docker-compose.yml` (new), `README.md`

---

### DX-005 — No hot-reload support for web UI frontend development

- **Category:** developer-experience
- **Priority:** P3 — Low
- **Impact:** Low — `make web-dev` starts uvicorn with `--reload` for Python hot-reload, but the static frontend files (HTML/CSS/JS) are served from disk with no live reload or HMR. Developers must manually refresh the browser.
- **Effort:** Small
- **Status:** pending
- **Description:** Add a lightweight livereload script to `index.html` (conditional on `__dev__` flag) that polls the server or uses SSE for frontend file changes. Document in CONTRIBUTING.md.
- **Files:** `web_app/static/index.html`, `web_app/server.py`, `CONTRIBUTING.md`

---

### DOC-001 — No `docs/` directory (see TECH-DEBT-008)

- **Category:** documentation
- **Priority:** P2 — Medium
- **Status:** pending
- **Note:** Duplicate of TECH-DEBT-008. Create `docs/` directory with architecture, API, configuration, development, and security docs.
- **Files:** `docs/` (new), `web_app/REFACTOR_PLAN.md`, `README.md`

---

### DOC-002 — Incomplete docstrings on exported public API functions

- **Category:** documentation
- **Priority:** P3 — Low
- **Impact:** Low — Several exported functions lack docstrings or have minimal one-liners: `_recalc_stats()` (no return docs), `_evolve_goal()` (outdated description), `check_sentinel()` (no return docs), `extract_json_from_output()` (complex algorithm in comments, not docstring).
- **Effort:** Small
- **Status:** pending
- **Description:** Audit all public functions. Ensure Args section (with types) and Returns section (with types and semantics). The project has 77% docstring coverage — target 100%.
- **Files:** `pi_loop/stats.py`, `pi_loop/functions.py`, `pi_loop/file_utils.py`, `pi_loop/loop.py`

---

### DOC-003 — README missing several key pieces

- **Category:** documentation
- **Priority:** P2 — Medium
- **Impact:** Medium — README is excellent (8.5/10) but missing:
  1. No link to FastAPI auto-generated `/docs` OpenAPI endpoint
  2. No screenshot/preview of the web UI
  3. No minimum `pi` coding agent version requirement
  4. No LICENSE link (MIT file exists but isn't linked)
  5. No Docker/container usage section
- **Effort:** Small
- **Status:** pending
- **Description:** Add the missing sections. Include a screenshot of the dashboard. Add a "Prerequisites" section listing `pi` binary requirement.
- **Files:** `README.md`

---

### DOC-004 — No FAQ or troubleshooting section

- **Category:** documentation
- **Priority:** P3 — Low
- **Impact:** Low — Common issues (`pi` not found in PATH, port 8090 already in use, ledger file permissions, config file parse errors) are not documented.
- **Effort:** Small
- **Status:** pending
- **Description:** Add FAQ/troubleshooting section to README or CONTRIBUTING.md covering: port conflicts, binary not found, permission errors, config file corruption, `.venv` vs system Python.
- **Files:** `README.md`, `CONTRIBUTING.md`

---

### DOC-005 — No `examples/` directory or step-by-step tutorials

- **Category:** documentation
- **Priority:** P4 — Future
- **Impact:** Low — The CLI has a strong `--examples` flag with 7 categorized usage patterns, but no standalone examples directory or tutorial-style walkthroughs.
- **Effort:** Medium
- **Status:** pending
- **Description:** Create `examples/` directory with: basic loop, multi-worker, git integration, webhook callbacks, error recovery scenarios. Link from README.
- **Files:** `examples/` (new), `README.md`

---

### OBSERV-001 — Version number 14.39.0 is disproportionately high for project scale

- **Category:** developer-experience
- **Priority:** P3 — Low
- **Impact:** Low — Version `14.39.0` suggests 14 major releases and 39 minor releases for ~5,000 lines of Python. Inflated version numbers make SemVer meaningless and erode user trust.
- **Effort:** Small
- **Status:** pending
- **Description:** Consider: (1) reset to SemVer `0.x` until API stability, (2) adopt CalVer aligned with release dates, or (3) begin proper SemVer after release workflow is established. Document the chosen scheme in CONTRIBUTING.md.
- **Files:** `pi_loop/config.py`, `pi_loop/__init__.py`, `pyproject.toml`, `CHANGELOG.md`

---

### OBSERV-002 — No request ID tracking via middleware for log correlation

- **Category:** observability
- **Priority:** P3 — Low
- **Impact:** Low — The web server processes multiple concurrent requests (SSE, REST polls, static files) but there is no request ID middleware to correlate log entries across a single request lifecycle.
- **Effort:** Small
- **Status:** pending
- **Description:** Add a `request_id` middleware that generates a UUID per request, adds it to `request.state`, and includes it in structured log entries. Pass the ID via `X-Request-ID` response header.
- **Files:** `web_app/server.py`

---

### OBSERV-003 — No health check endpoint (`/health` or `/api/health`)

- **Category:** observability / operations
- **Priority:** P2 — Medium
- **Impact:** Medium — The web server has no simple health check endpoint. The `/api/status` endpoint requires auth and reads the ledger file. Container orchestrators, load balancers, and monitoring systems need a lightweight, always-available health endpoint.
- **Effort:** Small
- **Status:** pending
- **Description:** Add `GET /health` that returns `{"status": "ok", "version": "14.39.0", "uptime_seconds": ...}` with HTTP 200. Bypass auth middleware. Include basic checks: loop daemon running (if applicable), ledger file accessible, disk space.
- **Files:** `web_app/server.py`

---

### OBSERV-004 — No metrics or telemetry endpoint

- **Category:** observability
- **Priority:** P4 — Future
- **Impact:** Low — The web server exposes iteration counts, error type counts, and system resources via the dashboard, but there is no Prometheus `/metrics` endpoint or structured telemetry export.
- **Effort:** Medium
- **Status:** pending
- **Description:** Add optional Prometheus metrics via `prometheus_fastapi_instrumentator`: request count, latency histogram, error rate by endpoint, iteration rate, iteration duration, worker count. Disabled by default.
- **Files:** `web_app/server.py`, `pyproject.toml` (optional dep)

---

### FEATURE-001 — Structured worker communication via NDJSON event stream

- **Category:** architecture / feature
- **Priority:** P2 — Medium
- **Impact:** Medium — The daemon's `_execute_task()` in `loop.py` already emits structured NDJSON events (thinking, tool_calls, text, error). The web UI's `LoopManager` ignores this structured data and reverse-engineers state from human-readable ANSI-colored log strings (BUG-003). Fix the root cause, not the symptom.
- **Effort:** Large
- **Status:** pending
- **Description:** Replace the regex-based `_parse_line()` in `loop_manager.py` with an NDJSON event consumer. Thread structured events through the SSE stream to the frontend. This eliminates BUG-003 and PERF-001 together.
- **Files:** `web_app/loop_manager.py`, `web_app/server.py`, `pi_loop/loop.py`, `web_app/static/app.js`

---

### FEATURE-002 — Multi-goal scheduler (not just linear cycling)

- **Category:** feature
- **Priority:** P4 — Future
- **Impact:** Low — Current `--goals-file` cycles through goals linearly. No support for priority queues, weighted distribution, goal dependencies, or conditional branching.
- **Effort:** Large
- **Status:** pending
- **Description:** Design a goal scheduler DSL (YAML or JSON) supporting: priority levels, dependency chains, conditional gates (`retry N times then skip`), time-windowed goals, and post-condition verification.
- **Files:** `pi_loop/loop.py`, `pi_loop/config.py`, `pi_loop/functions.py`

---

### FEATURE-003 — Cross-platform support via system resource provider abstraction

- **Category:** feature / architecture
- **Priority:** P2 — Medium
- **Status:** pending
- **Note:** Duplicate of ARCH-003. Create abstract `SystemResourceProvider` interface with platform-specific providers.
- **Files:** `pi_loop/system_utils.py`, `pi_loop/status.py`

---

### FEATURE-004 — Web UI dark/light theme toggle with persistence

- **Category:** feature
- **Priority:** P4 — Future
- **Impact:** Low — The dashboard has a dark theme (via `style.css`) but no theme toggle. The CSS already has `prefers-color-scheme` media queries suggesting the developer considered theming.
- **Effort:** Small
- **Status:** pending
- **Description:** Add a theme toggle button in the dashboard header. Persist preference in `localStorage`. Apply theme class to `<html>` element. Ensure no XSS vectors in the toggle.
- **Files:** `web_app/static/index.html`, `web_app/static/style.css`, `web_app/static/app.js`

---

## Summary

### By Priority

| Priority | Count | Key Items |
|----------|-------|-----------|
| **P0 — Critical** | 2 | TECH-DEBT-001 (monolithic run_loop), TEST-001 (zero integration tests) |
| **P1 — High** | 8 | BUG-002, BUG-003, TECH-DEBT-002, TECH-DEBT-003, TEST-002, CI-CD-001, CI-CD-006 (smoke tests), DOC-003 |
| **P2 — Medium** | 27 | BUG-004, BUG-005, BUG-007, BUG-008, TECH-DEBT-004..008, SEC-001, SEC-003, SEC-007, ARCH-001..004, TEST-003..004, TEST-006..008, PERF-001..002, CI-CD-002..004, DX-001, DOC-001, OBSERV-003 |
| **P3 — Low** | 14 | BUG-006, BUG-009, TECH-DEBT-009, ARCH-005..006, TEST-005, PERF-003..004, SEC-002, SEC-004..005, SEC-008, CI-CD-005, DX-002..003, DOC-002, DOC-004, OBSERV-001..002 |
| **P4 — Future** | 5 | SEC-006, CI-CD-007, DX-004, DOC-005, FEATURE-002, FEATURE-004, OBSERV-004 |
| **Total** | **56** | |

### By Category

| Category | Count |
|----------|-------|
| Bug | 9 |
| Technical Debt / Refactoring | 9 |
| Testing | 8 |
| Architecture | 6 |
| Security | 8 |
| Performance | 4 |
| CI/CD | 7 |
| Developer Experience | 5 |
| Documentation | 5 |
| Observability | 3 |
| Feature | 3 |

---

## Recommended Sprint Priorities

### Sprint 1: Core Stability & Safety Net

1. ~~BUG-001 — `_evolve_goal()` read side~~ ✅ DONE
2. **TEST-001** — Integration test suite with `mock_pi.sh`
3. **BUG-002** — Log notification/HTTP callback failures instead of silent suppression
4. **SEC-007** — Add `.env` to `.gitignore`
5. **BUG-008** — Validate `http_callback` URL scheme

### Sprint 2: Testing & Quality Infrastructure

1. **TEST-002** — `config_file.py` tests
2. **TEST-003** — `rate_limiter.py` tests
3. **TEST-006** — Web server endpoint tests (SSE, config CRUD)
4. **TEST-007** — CLI parser unit tests
5. ~~DX-001 — `.pre-commit-config.yaml`~~ ✅ DONE

### Sprint 3: Security Hardening

1. ~~SEC-003 — HTTP security headers middleware~~ ✅ DONE
2. ~~BUG-005 — Extend error classifier patterns~~ ✅ DONE
3. **SEC-001** — Comprehensive ANSI escape stripping
4. **CI-CD-003** — mypy in CI
5. **SEC-008** — Secrets scanner in CI

### Sprint 4: Architecture & Performance

1. ~~OBSERV-003 — Health check endpoint~~ ✅ DONE
2. **PERF-002** — SSE poller mtime check
3. **BUG-003** — NDJSON event consumption in loop_manager
4. **TECH-DEBT-007** — Structured logging
5. **TECH-DEBT-006** — Typed state model (TypedDict)

### Sprint 5: Major Refactoring

1. **TECH-DEBT-001** — Decompose `run_loop()` (X-Large effort)
2. **TECH-DEBT-002** — Split `LoopConfig` god dataclass
3. **TECH-DEBT-003** — Reduce 30-param startup banner to 2 params
4. **CI-CD-001** — Release workflow
5. **TECH-DEBT-004** — Standardize env var namespace

---

## Quick Reference

```
P0 Critical  ██░░  2   TECH-DEBT-001 (monolith), TEST-001 (integration)
P1 High      ████  8   BUG-002, BUG-003, TECH-DEBT-002/003, TEST-002, CI-CD-001/006, DOC-003
P2 Medium    ██████████████  27  (bugs, arch, security, testing)
P3 Low       ██████  14  (minor bugs, DX, doc gaps)
P4 Future    ██░░  5   (long-term features, Docker, examples)
Total:       56 items
```

---

*This backlog is a living document. Items should be re-prioritized quarterly. The highest-value work for the next sprint is: integration tests (TEST-001), notification logging (BUG-002), config_file.py tests (TEST-002), and CI type-checking (CI-CD-003).*

---

## Appendices

### A. Analysis Sources

| Source | Date | Scope |
|--------|------|-------|
| Git history analysis | 2026-06-30 | 213 commits, 4-day project lifecycle |
| Source code analysis | 2026-06-30 | All 53 .py files (25 source, 24 test, 4 helpers) |
| Security audit | 2026-06-30 | Bandit + Safety + manual review of all security-relevant code |
| Dependency audit | 2026-06-30 | All 16 prod + 67 dev packages, freshness check |
| Documentation assessment | 2026-06-30 | README, CONTRIBUTING, CHANGELOG, inline docstrings |
| Developer experience evaluation | 2026-06-30 | Setup flow, tooling, CI/CD, onboarding |
| Tech stack & environment | 2026-06-30 | Installed tools, Python/Node/Rust versions, MCP servers |

### B. Completed Items

| ID | Title | Resolution | Sprint |
|----|-------|------------|--------|
| BUG-001 | `_evolve_goal` never consumed | Read side wired at loop.py:558–563; 460 tests pass | Sprint 1 |
| DX-001 | `.pre-commit-config.yaml` | Enhanced with check-json, check-merge-conflict, detect-private-key; all ruff + syntax pass | Sprint 2 |
| SEC-007 | `.env` in `.gitignore` | Uncommented `.env` entry; added `.env.*` glob as defense-in-depth | Sprint 1 |
| BUG-005 | `classify_error()` missing patterns | Added timedout, time_out, read timed out, connection timed out, name/service resolution, handshake/SSL failures, operation timed out; 34 tests passing | Sprint 3 |
| OBSERV-003 | `/api/health` endpoint | Enhanced with version, uptime via monotonic clock; auth + rate-limit already exempted | Sprint 4 |
| SEC-003 | HTTP security headers middleware | CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection added to all responses | Sprint 3 |
| DOC-003 | README missing sections | Added Prerequisites (pi binary requirement), link to /docs Swagger UI, LICENSE link, screenshot placeholder | Sprint 1 |
| — | Pre-existing lint fixes | Fixed E501 long line in SSE heartbeat; added error handling to static file read; defined _read_file helper; set _server_start_time in startup handler | Sprint 2 |
