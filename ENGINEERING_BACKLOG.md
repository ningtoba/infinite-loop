# Engineering Backlog

> Living document — comprehensive engineering backlog for the pi-loop autonomous task automation daemon.
> Last updated: 2026-06-30
> Version: 14.39.0

---

## Project Overview

**pi-loop** is a self-contained Python daemon that runs tasks iteratively in a loop, tracks progress in a JSON ledger, and surfaces everything through a dark-theme web dashboard. It delegates each iteration to the [pi coding agent](https://pi.ai) and handles orchestration — convergence detection, error recovery, cooldown management, git auto-commit, multi-worker parallelism, and real-time monitoring via SSE.

### Architecture & Tech Stack

| Layer | Technology |
|-------|-----------|
| **Language** | Python ≥3.10, JavaScript (vanilla SPA) |
| **Web framework** | FastAPI 0.138.1 + Starlette 1.3.1 |
| **Server** | uvicorn 0.49.0 (with httptools, uvloop) |
| **Validation** | Pydantic 2.13.4 |
| **Frontend** | Vanilla HTML/CSS/JS (no framework), xterm.js for terminal, SSE for live updates |
| **Testing** | pytest 9.1, pytest-asyncio, pytest-cov, pytest-timeout (440+ tests across 25+ files) |
| **Linting** | Ruff 0.15.20 |
| **Type checking** | mypy 2.1.0 |
| **CI/CD** | GitHub Actions (Python 3.10–3.13 matrix, lint, mypy, security, coverage) |
| **Worktrees** | 3 active feature worktrees (`bd038f68`, `edaf42c8`, `d19eb158`) plus extensive research/design docs |

### Structure

```
pi_loop/       → Core daemon package (cli, loop engine, config, error recovery, git utils, heartbeat)
web_app/       → FastAPI web server + SPA frontend (server.py, loop_manager.py, config_manager.py, static/)
tests/         → 25+ test files covering pi_loop and web_app modules
```

### Current State

- **460+ tests** across 19 test modules
- **CI fully operational** with Python matrix (3.10–3.13), lint, mypy, security, verify-lock, multi-version coverage merge
- **All known security issues resolved** — dashboard XSS eliminated via `escapeHtml()`, security scanning (`safety` + `bandit`) automated in CI and **actually fails on vulnerabilities** (no `|| true` masking), Dependabot configured for weekly updates
- **Mypy enforced** in CI, no redundant second run (merged into `make lint-all`)
- **Coverage reporting** — matrix builds upload raw `.coverage` files per Python version, combined via `coverage combine` into a single merged report
- **SSE reconnect** uses exponential backoff with jitter (no thundering herd)
- **10 bugs/quality issues fixed** in latest iteration: broken Makefile quoting, `--shutdown-sentinel` CLI arg propagation, `_MISSING_TYPE` → `dataclasses.MISSING`, `_request_shutdown()` wired to signal handlers, hardcoded `/tmp` path in web UI, `$(PYTHON)` consistency, stale BACKLOG.md deleted
- **Major remaining debt**: monolithic `run_loop()` (300+ lines, 60+ locals), `LoopConfig` god dataclass (63 fields), no release workflow, no CHANGELOG, `/proc`-only system monitoring

---

## Quick Reference

| Priority | Count |
|----------|-------|
| 🔴 **P0 — Critical** | 1 |
| 🟠 **P1 — High** | 9 |
| 🟡 **P2 — Medium** | 9 |
| 🔵 **P3 — Low** | 5 |
| ⚪ **P4 — Wishlist** | 4 |
| **Total Active** | **28** |

| Category | Count |
|----------|-------|
| Tech Debt | 5 |
| Performance | 4 |
| Architecture | 3 |
| Reliability | 3 |
| DevX | 3 |
| CI/CD | 2 |
| Testing | 1 |
| Documentation | 2 |
| Frontend/CSS | 2 |
| Security | 1 |
| Observability | 1 |
| Feature | 1 |

---

## Top 5 — Immediate Action Items

| Rank | ID | Title | Priority | Effort | Category |
|------|-----|-------|----------|--------|----------|
| 1 | **BACKLOG-002** | Consolidate hardcoded `/tmp` paths under `PI_LOOP_DATA_DIR` | P0 🔴 | Medium | Reliability |
| 2 | **BACKLOG-005** | Implement structured logging with correlation IDs | P1 🟠 | Medium | Observability |
| 3 | **BACKLOG-006** | Split LoopConfig god dataclass into focused config classes | P1 🟠 | Medium | Architecture |
| 4 | **BACKLOG-007** | Decompose monolithic `run_loop()` into focused modules | P1 🟠 | X-Large | Architecture |
| 5 | **BACKLOG-008** | Add noop/fallback system monitoring for non-Linux platforms | P1 🟠 | Medium | Architecture |

---

## Backlog Items

### P0 — Critical

---

### BACKLOG-002 — Consolidate hardcoded `/tmp` paths under `PI_LOOP_DATA_DIR`

| Field | Value |
|-------|-------|
| **Category** | reliability |
| **Priority** | 🔴 P0 Critical |
| **Impact** | high |
| **Effort** | medium |
| **Reasoning** | `PI_LOOP_DATA_DIR` env var exists in `config.py` and drives ledger/lock/sentinel paths, but 5+ locations still hardcode `/tmp`: HTML dashboard suggestions (`loop.py`), help examples (`help_topics.py`), preflight disk check default (`preflight.py`), status file default (`status.py`). Breaks container deployments and multi-instance setups. |
| **Affected files** | `pi_loop/loop.py` (~line 305), `pi_loop/help_topics.py` (lines 145–159), `pi_loop/preflight.py` (~line 35), `pi_loop/status.py` (~line 14) |
| **Progress** | `web_app/config_manager.py` fixed (now uses `SENTINEL_PATH_DEFAULT`); 4 locations remain |

---

### P1 — High

---

### BACKLOG-005 — Implement structured logging with correlation IDs

| Field | Value |
|-------|-------|
| **Category** | observability |
| **Priority** | 🟠 P1 High |
| **Impact** | high |
| **Effort** | medium |
| **Reasoning** | The codebase uses `print()` and `_log()` with no structured fields, no correlation IDs, no log levels for filtering. Production debugging requires manual log scraping. Adopt a structured approach (stdlib `logging` with JSON formatter or `structlog`) with `iteration_id`, `loop_id`, `duration_ms`, `event` fields. |
| **Affected files** | `pi_loop/loop.py`, `pi_loop/error_recovery.py`, `pi_loop/git_utils.py`, `pi_loop/heartbeat.py`, `pi_loop/preflight.py`, `web_app/server.py` |

---

### BACKLOG-006 — Split LoopConfig god dataclass into focused config classes

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | 🟠 P1 High |
| **Impact** | high |
| **Effort** | medium |
| **Reasoning** | `LoopConfig` in `config.py` has 63 fields spanning iteration control, workers, git, notifications, archiving, logging, safety, and advanced options — violating SRP. The `from_args()` method imports `dataclasses._MISSING_TYPE` (private API that may break). Split into `IterationConfig`, `WorkerConfig`, `GitConfig`, `NotificationConfig`, `ArchiveConfig`, `SafetyConfig`, `LoggingConfig` composed in an `AppConfig` container. |
| **Affected files** | `pi_loop/config.py`, `pi_loop/loop.py`, `pi_loop/functions.py` |

---

### BACKLOG-007 — Decompose monolithic `run_loop()` into focused modules

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | 🟠 P1 High |
| **Impact** | high |
| **Effort** | xlarge |
| **Reasoning** | `run_loop()` is 300+ lines handling shutdown, git state capture, notification dispatch, error recovery adaptation, cooldown logic, dashboard HTML generation, HTTP callbacks, goal cycling, convergence detection, and heartbeat management. The function body is ~200 lines of mixed concerns with 60+ local variables. Extract into `IterationEngine`, `NotificationDispatcher`, `DashboardBuilder`, `ConvergenceDetector` classes. |
| **Affected files** | `pi_loop/loop.py`, new `pi_loop/executor.py`, `pi_loop/orchestrator.py`, `pi_loop/reporter.py` |

---

### BACKLOG-008 — Add noop/fallback system monitoring for non-Linux platforms

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | 🟠 P1 High |
| **Impact** | medium |
| **Effort** | medium |
| **Reasoning** | CPU/memory monitoring reads `/proc/[pid]/status`, `/proc/stat`, `/proc/meminfo`, and uses `os.sysconf_names["SC_CLK_TCK"]`. These are Linux-specific. On macOS/BSD the system monitoring endpoints crash with `FileNotFoundError`. Create an abstract `SystemResourceProvider` with `LinuxProvider` and `NoopProvider` (returns 0s with a warning). |
| **Affected files** | `pi_loop/system_utils.py`, `web_app/server.py`, `pi_loop/status.py` |

---

### BACKLOG-010 — Fix iterator-start detection failure on colorized output

| Field | Value |
|-------|-------|
| **Category** | reliability |
| **Priority** | 🟠 P1 High |
| **Impact** | medium |
| **Effort** | small |
| **Reasoning** | `_parse_daemon_line` in `loop_manager.py` checks for `"[ITERATION"` but if daemon logs use ANSI color codes, the bracket prefix can be broken across color escape sequences. Parse with a regex that handles ANSI escapes, or strip ANSI before matching. |
| **Affected files** | `web_app/loop_manager.py` |

---

### BACKLOG-011 — Make config writes atomic (write .tmp → rename)

| Field | Value |
|-------|-------|
| **Category** | reliability |
| **Priority** | 🟠 P1 High |
| **Impact** | medium |
| **Effort** | small |
| **Reasoning** | Config files are written directly, risking partial/corrupt writes on crash or power loss. Use the atomic pattern: write to `.config.json.tmp`, then `os.rename()` (which is atomic on POSIX). Add corruption detection on read with automatic backup restoration. |
| **Affected files** | `pi_loop/config_file.py`, `web_app/config_manager.py` |

---

### BACKLOG-012 — Add release workflow and version tags

| Field | Value |
|-------|-------|
| **Category** | ci-cd |
| **Priority** | 🟠 P1 High |
| **Impact** | medium |
| **Effort** | medium |
| **Reasoning** | Despite version `14.39.0` appearing in `__init__.py` and commits, there are zero git tags and no release workflow. No `git checkout v14.4.0` possible. No CI publishes to PyPI or creates GitHub releases. Create `release.yml` triggered on `v*` tags: run tests, build package, create GitHub release with auto-changelog, optionally publish to PyPI. |
| **Affected files** | `.github/workflows/release.yml` (new), `pyproject.toml` |

---

### BACKLOG-013 — Create integration test suite for subprocess lifecycle

| Field | Value |
|-------|-------|
| **Category** | testing |
| **Priority** | 🟠 P1 High |
| **Impact** | high |
| **Effort** | large |
| **Reasoning** | The core value proposition (subprocess task execution via `pi`) has zero end-to-end verification. Create `tests/integration/` with `mock_pi.sh` emitting realistic NDJSON output. Test single iteration, convergence detection, error recovery with injected failures, sentinel stop/pause, and web UI daemon interaction. |
| **Affected files** | `tests/integration/` (new dir), `tests/integration/mock_pi.sh`, `tests/integration/conftest.py` |

---

### BACKLOG-014 — Remove dead code: `validate_json_output()`, unused imports

| Field | Value |
|-------|-------|
| **Category** | tech-debt |
| **Priority** | 🟠 P1 High |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | `validate_json_output()` in `validation.py` is defined but never called anywhere. `cli.py` has unused imports (vestiges of hermes-to-pi migration). Dead code rots and distorts coverage metrics. Remove `validate_json_output()` and `_classify_progress()`, clean up `cli.py` imports. |
| **Affected files** | `pi_loop/validation.py`, `pi_loop/loop.py`, `pi_loop/cli.py` |

---

### P2 — Medium

---

### BACKLOG-015 — Fix blocking cooldown: replace `time.sleep(1)` with event-based wait

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | 🟡 P2 Medium |
| **Impact** | medium |
| **Effort** | small |
| **Reasoning** | Cooldown in `_handle_cooldown()` uses `time.sleep(1)` in a loop, blocking the main thread and preventing clean cancellation (SIGTERM won't interrupt `time.sleep`). Replace with `_shutdown_event.wait(timeout=1)` for immediate cancellation while still ticking at 1-second intervals. |
| **Affected files** | `pi_loop/functions.py` (~lines 104–107) |

---

### BACKLOG-016 — Replace busy-wait file lock with exponential backoff

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | 🟡 P2 Medium |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | `FileLock.__enter__()` busy-waits with fixed 100ms sleep until timeout. Under contention (two pi-loop instances or pi-loop + web UI), this creates unnecessary CPU wakeups. Use exponential backoff: 10ms → 20ms → 40ms → ... → ~1s max, capped at remaining timeout. |
| **Affected files** | `pi_loop/file_utils.py` (~lines 45–46) |

---

### BACKLOG-017 — Make on-success/on-error commands non-blocking

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | 🟡 P2 Medium |
| **Impact** | medium |
| **Effort** | medium |
| **Reasoning** | `run_loop()` runs on-success/on-error commands via blocking `subprocess.call()`, delaying the next iteration until the command completes. For slow commands (e.g., deploying, syncing), this adds minutes to iteration time. Use `subprocess.Popen()` and continue the loop, tracking completions in a background thread. |
| **Affected files** | `pi_loop/loop.py` (on-success/on-error sections) |

---

### BACKLOG-018 — Fix duplicate `content_block_stop` handler in `_execute_task`

| Field | Value |
|-------|-------|
| **Category** | tech-debt |
| **Priority** | 🟡 P2 Medium |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | `_execute_task` in `loop.py` has two separate `content_block_stop` handler blocks with overlapping logic. This could cause double-counting of tool calls and confusing output. Merge into a single handler. |
| **Affected files** | `pi_loop/loop.py` (~lines 210–240) |

---

### BACKLOG-019 — Fix `_get_cpu_percent()` returning 0 on first call

| Field | Value |
|-------|-------|
| **Category** | tech-debt |
| **Priority** | 🟡 P2 Medium |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | `_get_cpu_percent()` returns 0 on the first call because `_prev_*` values haven't been set yet for delta calculation. This makes the first monitoring sample always show 0% CPU, confusing operators. Return `None` on first call instead and have callers handle it gracefully. |
| **Affected files** | `pi_loop/system_utils.py` |

---

### BACKLOG-020 — Fix inconsistent HTTP status codes for logical errors

| Field | Value |
|-------|-------|
| **Category** | tech-debt |
| **Priority** | 🟡 P2 Medium |
| **Impact** | medium |
| **Effort** | medium |
| **Reasoning** | Config save and loop control endpoints return HTTP 200 with `{"success": false}` for logical errors instead of proper 4xx status codes. Clients can't distinguish logical (422, 400, 409) from server (500) errors. Return appropriate HTTP status codes with structured error bodies. |
| **Affected files** | `web_app/server.py` |

---

### BACKLOG-021 — Add OpenAPI documentation to all web endpoints

| Field | Value |
|-------|-------|
| **Category** | documentation |
| **Priority** | 🟡 P2 Medium |
| **Impact** | medium |
| **Effort** | medium |
| **Reasoning** | The FastAPI app has no auto-generated docs beyond the minimal title/description. All endpoints need proper response models, docstrings, and OpenAPI metadata. FastAPI supports this natively — add Pydantic response models, operation IDs, and summary/description tags. |
| **Affected files** | `web_app/server.py` |

---

### BACKLOG-022 — Create CHANGELOG.md and configure auto-generation

| Field | Value |
|-------|-------|
| **Category** | documentation |
| **Priority** | 🟡 P2 Medium |
| **Impact** | medium |
| **Effort** | small |
| **Reasoning** | Version 14.39.0 exists but there is no changelog. Users cannot determine what changed between versions. Since the project uses Conventional Commits, auto-generate a CHANGELOG from git history via `git-cliff` or similar. Keep a manually curated `CHANGELOG.md` for the initial baseline. |
| **Affected files** | `CHANGELOG.md` (new), `pyproject.toml` for cliff config |

---

### BACKLOG-023 — Migrate CSS to custom properties and remove dead toggle CSS

| Field | Value |
|-------|-------|
| **Category** | frontend |
| **Priority** | 🟡 P2 Medium |
| **Impact** | low |
| **Effort** | medium |
| **Reasoning** | `style.css` has ~50+ hardcoded `#rrggbb` hex values and ~800 lines of nearly identical light/dark theme duplication. Migrate to CSS custom properties (`--color-bg`, `--color-text`, etc.) with a theme-switching class. Remove dead `.toggle` / `.toggle-slider` CSS (no corresponding HTML elements exist). |
| **Affected files** | `web_app/static/style.css` |

---

### P3 — Low

---

### BACKLOG-026 — Remove redundant `pip install` in `make test`

| Field | Value |
|-------|-------|
| **Category** | devx |
| **Priority** | 🔵 P3 Low |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | `make test` runs `pip install -e ".[test]"` before every `pytest` invocation, wasting 2–3 seconds per local test run. The `install-dev` target already installs test deps. Remove the pip install from the test target. |
| **Affected files** | `Makefile` |

---

### BACKLOG-027 — Add `[tool.ruff.lint]` section to `pyproject.toml`

| Field | Value |
|-------|-------|
| **Category** | devx |
| **Priority** | 🔵 P3 Low |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | While `[tool.ruff]` line-length config exists, there's no `[tool.ruff.lint]` section selecting specific rule sets. Default rules may be too permissive. Add explicit select (E, F, W, I, N, UP, B, SIM, ARG, RUF100 — already in ruff config). |
| **Affected files** | `pyproject.toml` |

---

### BACKLOG-029 — Add keyboard-focus indicators and `aria-live` regions

| Field | Value |
|-------|-------|
| **Category** | frontend |
| **Priority** | 🔵 P3 Low |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | Buttons lack `:focus-visible` keyboard focus indicators. Dynamic content containers (log entries, status updates, iteration tables) lack `aria-live` attributes for screen readers. Add minimal accessibility improvements. |
| **Affected files** | `web_app/static/style.css`, `web_app/static/index.html`, `web_app/static/app.js` |

---

### BACKLOG-030 — Add pi binary availability check to CI

| Field | Value |
|-------|-------|
| **Category** | ci-cd |
| **Priority** | 🔵 P3 Low |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | CI doesn't verify that the `pi` CLI is available. A `pi` API change (removed flag, different output format) could silently break the daemon. Add a CI step to check `pi --help` or `pi --version`. |
| **Affected files** | `.github/workflows/ci.yml` |

---

### BACKLOG-031 — Downgrade expected-error log levels in daemon poll

| Field | Value |
|-------|-------|
| **Category** | tech-debt |
| **Priority** | 🔵 P3 Low |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | Logging at ERROR level for expected conditions — e.g., `Connection refused` during normal retry, or process-not-started-yet during heartbeat polling. These flood production logs. Downgrade to WARNING or INFO as appropriate. |
| **Affected files** | `pi_loop/heartbeat.py`, `pi_loop/loop.py` |

---

### P4 — Wishlist

---

### BACKLOG-032 — Add HTTP callback secret masking in logs

| Field | Value |
|-------|-------|
| **Category** | security |
| **Priority** | ⚪ P4 Wishlist |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | `--http-callback-secret` is logged verbosely if debug logging is enabled. Mask to first/last 2 characters with `****` in between. Add support for `--http-callback-secret-file` (reads from a restricted-permissions file). |
| **Affected files** | `pi_loop/parser.py`, `pi_loop/loop.py` |

---

### BACKLOG-033 — Add configurable static asset base path

| Field | Value |
|-------|-------|
| **Category** | devx |
| **Priority** | ⚪ P4 Wishlist |
| **Impact** | low |
| **Effort** | small |
| **Reasoning** | Script/link tags in `index.html` hardcode `/static/app.js` and `/static/style.css`. Add a configurable base path or use a FastAPI template context so assets can be served from a CDN or different prefix. |
| **Affected files** | `web_app/static/index.html`, `web_app/server.py` |

---

### BACKLOG-034 — Add heartbeat/runtime guard for hung iterations

| Field | Value |
|-------|-------|
| **Category** | feature |
| **Priority** | ⚪ P4 Wishlist |
| **Impact** | medium |
| **Effort** | medium |
| **Reasoning** | A stuck pi subprocess can hang the daemon indefinitely with no recovery. Add a heartbeat/runtime guard to the main `while True` loop so that if an iteration exceeds `max_iteration_wall_time`, the daemon can self-recover by killing the subprocess and moving on. |
| **Affected files** | `pi_loop/loop.py` (~line 310) |

---

### BACKLOG-035 — Implement JSON extraction as single-pass parser

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | ⚪ P4 Wishlist |
| **Impact** | low |
| **Effort** | medium |
| **Reasoning** | `extract_json_from_output()` does two full scans (backward and forward) with naive brace counting that breaks on strings containing braces. Implement a single-pass O(n) parser using a stack that tracks brace depth while accounting for string literals. |
| **Affected files** | `pi_loop/file_utils.py` (~line 120) |

---

## Completed Items (prior sprint)

| ID | Title | Category | Completed |
|----|-------|----------|-----------|
| | Subprocess zombie leak (timeout) — `proc.kill()` + `proc.wait()` | Bug | ✅ |
| | Race condition in `loop_manager.stop()` — `self._lock` | Bug | ✅ |
| | TOCTOU race in `loop_manager.stop()` — PID ownership check | Bug | ✅ |
| | Race: status='running' set before monitors created | Bug | ✅ |
| | Race: `_read_stream` AttributeError on stale `self._process` | Bug | ✅ |
| | Silent error recovery mitigation loss (`state.get("mitigations", {})`) | Bug | ✅ |
| | Duplicated shutdown logic (extracted `_shutdown()`, -134 lines) | Tech Debt | ✅ |
| | Silent exception swallowing (bare `except: pass` everywhere) | Tech Debt | ✅ |
| | Stored XSS in `_build_dashboard_html()` — `html.escape()` | Security | ✅ |
| | `validate_config()` wired into `save_config_api()` | Security | ✅ |
| | Config file corruption → graceful defaults instead of 500 | Reliability | ✅ |
| | Silent I/O failure logging (config_file, git_utils, heartbeat, status) | Reliability | ✅ |
| | Circular import `cli.py` ↔ `help_topics.py` (extracted `parser.py`) | Architecture | ✅ |
| | Duplicate `worker_term` init in `_parse_daemon_line` | Cleanup | ✅ |
| | `import urllib.request` inside function body → top of module | Cleanup | ✅ |
| | Duplicate `write_status_file()` calls removed | Cleanup | ✅ |
| | Downgraded heartbeat ERROR log levels for normal startup | Cleanup | ✅ |
| | 440+ tests across 19 test files (was 0) | Testing | ✅ |
| | CI pipeline with Python 3.10–3.13 matrix | CI/CD | ✅ |
| | Pre-commit hook rewritten (ruff check + format) | CI/CD | ✅ |
| | Dev/test dependencies in `pyproject.toml` | CI/CD | ✅ |
| | mypy config in `pyproject.toml` | DX | ✅ |
| | Ruff config in `pyproject.toml` | DX | ✅ |
| | Worker terminal state persists across UI navigation | Feature | ✅ |

---

## Iteration 6 — Completed

| ID | Title | Category | Completed |
|----|-------|----------|-----------|
| BACKLOG-001 | Fix DOM XSS in web app frontend (app.js) — consistent `escapeHtml()` on all template-literal interpolations | Security | ✅ |
| BACKLOG-009 | Fix SSE reconnect using exponential backoff with jitter (1s–30s, ±25%) | Reliability | ✅ |
| BACKLOG-028 | Fix empty catch blocks in app.js — all catches log via `console.warn`/`console.error` | Frontend/CSS | ✅ |
| BACKLOG-003 | Wire mypy to actually fail CI (remove `|| true`) —`make mypy` no longer masks errors | CI/CD | ✅ |
| BACKLOG-004 | Automate security scanning in CI (bandit + safety) — `make security`, GitHub Actions security job | CI/CD | ✅ |
| BACKLOG-024 | Add Dependabot config for weekly pip updates | CI/CD | ✅ |

---

## Iteration 7 — Completed

| ID | Title | Category | Completed |
|----|-------|----------|-----------|
| BACKLOG-025 | Add coverage reporting to CI — proper multi-version merge via raw `.coverage` artifacts + `coverage combine` | CI/CD | ✅ |
| | Remove `|| true` from safety check so CI security job actually fails on vulnerabilities | CI/CD | ✅ |
| | Fix broken quoting in `Makefile` `help` target (unclosed quotes lines 17–18, triple quote line 19) | Bug | ✅ |
| | Remove duplicate `make mypy` from CI lint job (already covered by `make lint-all`) | CI/CD | ✅ |
| | Use `$(PYTHON)` consistently across `Makefile` — replaces bare `python`/`pip` with `$(PYTHON) -m pip` in all targets | DevX | ✅ |
| | Fix hardcoded `/tmp/infinite-loop-stop` in `web_app/config_manager.py` — import and use `SENTINEL_PATH_DEFAULT` from `pi_loop.config` | Reliability | ✅ |
| | Wire `--shutdown-sentinel` CLI arg to `LoopConfig.sentinel_path` (was silently dropped by `from_args()`) | Bug | ✅ |
| | Replace private `dataclasses._MISSING_TYPE` with public `dataclasses.MISSING` in `pi_loop/config.py` | Tech Debt | ✅ |
| | Wire `_request_shutdown()` to SIGINT/SIGTERM handlers in `pi_loop/cli.py` — graceful shutdown instead of abrupt `KeyboardInterrupt` | Tech Debt | ✅ |
| | Delete stale `BACKLOG.md` (superseded by `ENGINEERING_BACKLOG.md`) | Documentation | ✅ |

### Partially Addressed

| Item | Progress | Remaining |
|------|----------|-----------|
| BACKLOG-002 (/tmp consolidation) | Fixed `web_app/config_manager.py` hardcoded path | `pi_loop/loop.py`, `pi_loop/help_topics.py`, `pi_loop/preflight.py`, `pi_loop/status.py` still hardcode `/tmp` |
| BACKLOG-006 (config split) | Replaced private `_MISSING_TYPE` with public `dataclasses.MISSING` | God dataclass still has 63 fields; split into focused config classes not started |
| BACKLOG-014 (dead code) | `_request_shutdown()` is now reachable from production (signal handlers) | `validate_json_output()`, `_classify_progress()` still dead; `cli.py` has unused imports |

---

## File-by-File Issue Density

| File | Active Issues |
|------|---------------|
| `pi_loop/loop.py` | 5 (BACKLOG-002, -007, -014, -018, -034) |
| `pi_loop/help_topics.py` | 1 (BACKLOG-002) |
| `pi_loop/preflight.py` | 1 (BACKLOG-002) |
| `pi_loop/status.py` | 1 (BACKLOG-002) |
| `pi_loop/cli.py` | 1 (BACKLOG-014) |
| `pi_loop/validation.py` | 1 (BACKLOG-014) |
| `pi_loop/config.py` | 1 (BACKLOG-006) |
| `pi_loop/system_utils.py` | 2 (BACKLOG-008, -019) |
| `pi_loop/functions.py` | 1 (BACKLOG-015) |
| `pi_loop/file_utils.py` | 2 (BACKLOG-016, -035) |
| `pi_loop/heartbeat.py` | 1 (BACKLOG-031) |
| `pi_loop/config_file.py` | 1 (BACKLOG-011) |
| `web_app/server.py` | 2 (BACKLOG-020, -021) |
| `web_app/loop_manager.py` | 1 (BACKLOG-010) |
| `web_app/config_manager.py` | 1 (BACKLOG-011) |
| `web_app/static/style.css` | 2 (BACKLOG-023, -029) |
| `web_app/static/index.html` | 1 (BACKLOG-029, -033) |
| `Makefile` | 1 (BACKLOG-026) |
| `.github/workflows/ci.yml` | 1 (BACKLOG-030) |
| `.github/workflows/release.yml` | 1 (BACKLOG-012) |
| `pyproject.toml` | 1 (BACKLOG-027) |

---

## Effort Distribution

| Effort | Count | Items |
|--------|-------|-------|
| **Small** | 13 | BACKLOG-010, -011, -014, -015, -016, -019, -022, -026, -027, -029, -030, -031, -032, -033 |
| **Medium** | 11 | BACKLOG-002, -005, -006, -008, -012, -017, -020, -021, -023, -034, -035 |
| **Large** | 2 | BACKLOG-007, -013 |
| **X-Large** | 1 | BACKLOG-007 internal note (project-wide decomposition) |

---

## Priority vs Effort Matrix

```
High Impact ─────────────────────────────────────────────────────
            │                                          │
            │  BACKLOG-002 (/tmp consolidation)        │  BACKLOG-007 (run_loop decomp)
            │  BACKLOG-005 (structured logging)        │  BACKLOG-013 (integration tests)
            │  BACKLOG-006 (config split)              │
            │  BACKLOG-008 (non-Linux monitoring)       │
            │                                          │
            │  BACKLOG-011 (atomic config)             │  BACKLOG-012 (release workflow)
            │  BACKLOG-010 (colorized parse)           │  BACKLOG-017 (non-blocking cmds)
            │                                          │
Low Effort ───────────────────────────────────────────────────── High Effort
```

**Sweet spot (top-left):** Highest value per unit effort — tackle BACKLOG-002 *(4 remaining /tmp paths)*, BACKLOG-011, BACKLOG-010, BACKLOG-005 next.
**Strategic investments (bottom-right):** BACKLOG-007 and BACKLOG-013 require significant effort but provide foundational improvements.

---

## Execution Ripple Effects

| Item | Blocks | Blocked By |
|------|--------|------------|
| BACKLOG-007 (run_loop decomp) | BACKLOG-013 (integration tests), BACKLOG-017 (non-blocking cmds) | BACKLOG-006 (config split — recommended) |
| BACKLOG-023 (CSS custom props) | — | — (independent) |
| BACKLOG-012 (release workflow) | BACKLOG-022 (CHANGELOG) | — (independent — release should gate on clean CI) |
| BACKLOG-011 (atomic config) | — | — (independent) |

---

*This backlog is a living document. Items should be re-prioritized quarterly. The top 5 (BACKLOG-002, -005, -006, -007, -008) represent the highest-value work for the next sprint.*
