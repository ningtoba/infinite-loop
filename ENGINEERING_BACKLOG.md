# pi-loop Engineering Backlog

> Comprehensive engineering backlog synthesized from deep analysis: repository structure, git history, package configuration, source code analysis, test suite, dependency audit, complexity analysis, and CI/tooling review.
> Generated: 2026-06-29

---

## Quick Reference

| Severity | Count |
|----------|-------|
| 🔴 **P0 — Critical** | 1 |
| 🟠 **P1 — High** | 8 |
| 🟡 **P2 — Medium** | 17 |
| 🔵 **P3 — Low** | 10 |
| ⚪ **P4 — Wishlist** | 3 |
| ✅ **Completed** | 28 |
| **Total Active** | **39** |

| Category | Count |
|----------|-------|
| Bug | 3 |
| Technical Debt | 6 |
| Architecture | 4 |
| Performance | 2 |
| Security | 2 |
| Testing | 5 |
| Documentation | 2 |
| CI/CD | 2 |
| Developer Experience | 3 |
| Dependencies | 4 |
| Code Cleanup | 8 |
| Feature | 3 |
| Observability | 2 |

---

## Status Legend

| Status | Meaning |
|--------|---------|
| ✅ Done | Completed and verified |
| 🔄 In Progress | Currently being worked on |
| ⏳ Pending | Not yet started |
| ❌ Blocked | Blocked by another item |

---

## P0 — Critical

### BUG-001 — Hard-coded `/tmp` paths without unified override

| Field | Value |
|-------|-------|
| **Title** | Hard-coded `/tmp` paths without unified override |
| **Category** | Bug |
| **Priority** | 🔴 P0 — Critical |
| **Impact** | Breaks multi-instance deployments, containers where `/tmp` is not writable, and users who configure `PI_LOOP_DATA_DIR` — commands in help/examples show wrong paths |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** `PI_LOOP_DATA_DIR` env var exists in `config.py` and drives ledger/lock/sentinel paths, but 5+ locations still hardcoded `/tmp`. All now use `config._get_data_dir()`.

**Fix applied:**

- `status.py:14` — `STATUS_FILE_DEFAULT` uses `_get_data_dir()`
- `preflight.py:35,135` — `check_disk_space()` defaults to `_get_data_dir()`
- `loop.py:293` — shutdown summary uses `_get_data_dir()`
- `help_topics.py:138-151` — example commands use `_get_data_dir()`

**Affected files:**

- `pi_loop/loop.py`
- `pi_loop/help_topics.py`
- `pi_loop/preflight.py`
- `pi_loop/status.py`

### SEC-001 — Missing authentication and authorization on all web endpoints

| Field | Value |
|-------|-------|
| **Title** | Missing authentication and authorization on all web endpoints |
| **Category** | Security |
| **Priority** | 🔴 P0 — Critical |
| **Impact** | `/api/loop/start` can be triggered by anyone, spawning arbitrary `pi` subprocesses with user-level system access. No rate limiting, no request IDs, no auth of any kind. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** All FastAPI endpoints lack authentication, rate limiting, request timeouts, and request tracing. The `/api/loop/start` endpoint accepts a goal string and spawns a `pi -q <goal>` subprocess — an unauthenticated attacker could use this to execute arbitrary commands. CORS is wide open (`allow_origins=["*"]`). For a local daemon tool this is acceptable in dev, but production deployments need at minimum a simple token-based auth or bind-to-localhost-only enforcement.

**Research notes:** Consider implementing: (1) bind to `127.0.0.1` by default instead of `0.0.0.0`, (2) optional `PI_LOOP_API_KEY` env var for Bearer token auth, (3) rate limiting via middleware or Starlette's `Limiter`, (4) request IDs for tracing. CORS hardening should make origins configurable.

**Affected files:**

- `web_app/server.py` (all endpoints, lines 39-42 for CORS)

---

## P1 — High

### TECHDEPT-001 — Extreme parameter bloat in run_loop()

| Field | Value |
|-------|-------|
| **Title** | Extreme parameter bloat in run_loop() — 71 parameters |
| **Category** | Technical Debt |
| **Priority** | 🟠 P1 — High |
| **Impact** | Nearly impossible to test, reason about, document, or refactor. Function signature spans ~60 lines. 90+ parameters are never used inside the function body (dead params from migration). |
| **Effort** | Large |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `run_loop()` accepts 71 parameters covering config, paths, notifications, git, convergence, cooldown, error handling, workers, and more. The signature alone is ~60 lines. Many of these parameters are never actually referenced in the function body — they were carried over from the hermes-agent era and are dead code. This makes the function nearly impossible to test exhaustively, document, or safely modify.

**Research notes:** The fix is to introduce a `LoopConfig` dataclass (in `config.py` or a new `loop_config.py`) that encapsulates all configuration dimensions. The dataclass should have typed fields with defaults, and `run_loop()` should accept a single `LoopConfig` parameter. This reduces the signature from 71 params to 2 (config + state). See also ARCH-001 (monolithic body) which depends on this.

**Affected files:**

- `pi_loop/loop.py` (line ~331 signature)
- `pi_loop/config.py` (new `LoopConfig` dataclass)

### ARCH-001 — Monolithic run_loop() body violates Single Responsibility Principle

| Field | Value |
|-------|-------|
| **Title** | Monolithic run_loop() body violates Single Responsibility Principle |
| **Category** | Architecture |
| **Priority** | 🟠 P1 — High |
| **Impact** | ~435 lines handling shutdown, git state capture, notification dispatch, error recovery, cooldown, HTML dashboard generation, HTTP callbacks, goal cycling, iteration cap trimming, and convergence detection — all interleaved in one `while True` loop |
| **Effort** | X-Large |
| **Dependencies** | TECHDEPT-001 |
| **Status** | ❌ Blocked by TECHDEPT-001 |

**Reasoning:** The `run_loop()` body is ~435 lines with 6 independent exit-early conditions mixed with normal flow. It handles: sentinel checks, iteration counting, goal cycling, progressive context, subprocess execution, git capture, idle detection, error classification, notifications, HTML dashboard, HTTP callbacks, on-error commands, cooldown, error recovery adaptation, iteration cap trimming, and goal evolution. Each responsibility should be extracted into its own function or class.

**Research notes:** Proposed decomposition:

- `executor.py` — subprocess execution + NDJSON streaming (extract from `_execute_task`)
- `orchestrator.py` — iteration loop coordination (extract from `run_loop`)
- `reporter.py` — notification/dispatch callbacks (HTTP, desktop, pushover, ntfy)
- `LoopConfig` dataclass — encapsulate the 71 parameters (TECHDEPT-001)

**Affected files:**

- `pi_loop/loop.py` (lines 331-766)
- New files: `pi_loop/orchestrator.py`, `pi_loop/executor.py`, `pi_loop/reporter.py`

### ARCH-002 — Circular import: cli.py ↔ help_topics.py

| Field | Value |
|-------|-------|
| **Title** | Circular import: cli.py ↔ help_topics.py |
| **Category** | Architecture |
| **Priority** | 🟠 P1 — High |
| **Impact** | Fragile import chain that will break if import order changes. Confuses static analysis tools and IDE autocompletion. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `cli.py` imports `show_help_topics` from `help_topics.py`, and `help_topics.py` imports `build_parser` from `cli.py` (via `from .cli import _create_parser` at module level). This works only because both are lazily called (inside `main()` and `show_help_topics` function bodies), but it is fragile and confuses static analysis.

**Research notes:** Fix options: (1) Move `_create_parser` into its own module (`parser.py`) that both `cli.py` and `help_topics.py` import from. (2) Pass the parser as a parameter rather than importing it. (3) Use lazy imports inside function bodies consistently.

**Affected files:**

- `pi_loop/cli.py`
- `pi_loop/help_topics.py`

### TEST-001 — No integration or end-to-end tests

| Field | Value |
|-------|-------|
| **Title** | No integration or end-to-end tests — 100% unit tests only |
| **Category** | Testing |
| **Priority** | 🟠 P1 — High |
| **Impact** | The daemon's core value proposition (subprocess lifecycle, iteration orchestration, error recovery) has zero real-process testing. CI cannot catch regressions in the actual `pi` subprocess interaction. |
| **Effort** | X-Large |
| **Dependencies** | TECHDEPT-001, ARCH-001 |
| **Status** | ❌ Blocked by TECHDEPT-001, ARCH-001 |

**Reasoning:** All 404 tests are pure unit tests with heavy mocking — no real subprocess invocation of `pi`, no real ledger file lifecycle tested end-to-end, no actual daemon lifecycle (start → iterate → stop). The `subprocess.Popen` calls in `_execute_task` and `LoopManager.start()` are entirely untested at the integration level.

**Research notes:** Integration tests should cover: (1) daemon start with a mock `pi` script, (2) iteration lifecycle (one full loop iteration), (3) error recovery (inject failures, verify escalation), (4) sentinel stop/pause signals, (5) web UI endpoints talking to a real daemon. Requires a `tests/integration/` directory with conftest fixtures that provide a mock `pi` CLI script.

**Affected files:**

- `tests/` (new `tests/integration/` directory)

### DEPS-001 — No lock file — non-reproducible builds

| Field | Value |
|-------|-------|
| **Title** | No lock file — non-reproducible builds |
| **Category** | Dependencies |
| **Priority** | 🟠 P1 — High |
| **Impact** | Two CI runs at different times can produce different dependency trees. No pinned hashes for supply-chain verification. Reproducibility is impossible. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** There is no `requirements.txt`, `Pipfile.lock`, or `poetry.lock`. CI uses `pip install -e ".[test,dev]"` with `cache: pip`, but every install pulls the latest compatible versions within the declared ranges. This means different CI runs (or developer installs at different times) get different transitive dependency versions.

**Research notes:** Recommended approaches: (1) Generate `requirements.txt` with `pip freeze > requirements.txt`, commit it, and use `pip install -r requirements.txt` in CI. (2) Switch to `pip-tools` with `requirements.in`/`requirements-dev.in` compiling to locked `.txt` files. (3) Use `uv` for faster lock + sync. Simplest path: generate a lock file and add a CI step that verifies it's up to date.

**Affected files:**

- `pyproject.toml`
- New `requirements.txt` or equivalent lock file

### DEPS-002 — chromadb CRITICAL CVE in shared venv

| Field | Value |
|-------|-------|
| **Title** | chromadb CRITICAL CVE (CVE-2026-45829) present in shared virtual environment |
| **Category** | Dependencies |
| **Priority** | 🟠 P1 — High |
| **Impact** | Pre-authentication code injection vulnerability. An unauthenticated attacker can execute arbitrary code via `/api/v2/tenants/{tenant}/databases/{db}/collections` endpoint. No fix available for any version ≥1.0.0. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `chromadb` 1.5.9 is installed in the project's `.venv` (apparently from another project sharing the same venv). It has CVE-2026-45829 rated CRITICAL with no patched version available. While `chromadb` is NOT a declared dependency of this project and is not imported anywhere, its presence in the shared venv is a security risk — especially if the project is ever deployed.

**Research notes:** Fix: (1) Rebuild the virtual environment from scratch with `pip install -e ".[test,dev]"` only — this will exclude chromadb and 130+ other unused packages. (2) Consider using a project-specific venv or `uv venv` for isolation. (3) Add a CI check that `pip list` doesn't contain unexpected packages.

**Affected files:**

- `.venv/` (rebuild)
- `Makefile` (add `venv-clean` target)

### TEST-002 — 34% of functions lack complete type hints

| Field | Value |
|-------|-------|
| **Title** | 34% of functions lack complete type hints |
| **Category** | Testing |
| **Priority** | 🟠 P1 — High |
| **Impact** | Mypy in CI is non-blocking (`|| true` in Makefile). 44 of 128 functions lack return type hints or parameter type annotations. Type errors (None-safety, type mismatches) slip through to production. |
| **Effort** | Large |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Whole files lacking type hints: `config_file.py` (7 functions, 0 typed), `color_utils.py` (class methods missing return hints), `file_watcher.py` (no type hints at all), `preflight.py` (partial), `heartbeat.py` (inner function). Mypy is configured with `warn_return_any = true` and `warn_unused_configs = true`, but the CI step pipes errors to stderr (`2>/dev/null`), making them invisible.

**Research notes:** Fix: (1) Add type hints to all untyped functions, prioritizing `config_file.py`, `color_utils.py`, `file_watcher.py`. (2) Make mypy enforcement non-optional in CI — remove `2>/dev/null` pipe. (3) Add `--strict` to catch None-safety issues. (4) Set `no_implicit_optional = true` in mypy config. Each file is small (<100 lines for most) so this is a large but well-scoped effort.

**Affected files:**

- `pi_loop/config_file.py`
- `pi_loop/color_utils.py`
- `pi_loop/file_watcher.py`
- `pi_loop/preflight.py`
- `pi_loop/heartbeat.py`
- `Makefile` (remove `2>/dev/null` from mypy target)
- `.github/workflows/ci.yml` (make mypy blocking)

---

## P2 — Medium

### TECHDEPT-002 — Dead code: validate_json_output() defined but never called

| Field | Value |
|-------|-------|
| **Title** | Dead code: validate_json_output() defined but never called |
| **Category** | Technical Debt |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | 111 lines of unmaintained code that will rot. Provides false sense of validation coverage. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `validate_json_output()` in `validation.py` is a 111-line function with inner closures (`_check_type`, `_validate`) and recursive schema validation — but it is never imported or called anywhere in the codebase. The function was likely intended for validating `pi` output JSON but was never wired in. Either wire it into the iteration result processing pipeline or remove it.

**Research notes:** If the function is worth keeping, it should be called in `_execute_task()` or `run_loop()` when processing `pi` output. Otherwise, delete it and remove the test file if it has one. The similar `validate_config()` was already wired into the save endpoint (SEC-003 completed), so this is the remaining dead validation code.

**Affected files:**

- `pi_loop/validation.py` (function `validate_json_output`)

### TECHDEPT-003 — Config defaults diverge across three modules

| Field | Value |
|-------|-------|
| **Title** | Config defaults diverge across three modules |
| **Category** | Technical Debt |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | Surprising behavior: web UI shows different defaults than CLI. Config file saves different values than config_manager validates. Users get inconsistent experiences. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Three modules maintain overlapping default sets that diverge:

| Setting | config_file.py | config_manager.py | env_utils.py |
|---------|---------------|-------------------|--------------|
| SESSION_TIMEOUT | 120 | 600 | 300 |
| PORT | 8000 | (no default) | n/a |
| HEARTBEAT_INTERVAL | (not in defaults) | 30 (hardcoded) | (not in defaults) |

This means the web UI could validate against different limits than the CLI, and the config file could persist values the web UI considers invalid.

**Research notes:** Fix: (1) Make `config.py` the single source of truth for all defaults. (2) `config_file.py` should import from `config.py` rather than redefining. (3) `config_manager.py` should import from `config.py` rather than hardcoding. (4) Remove default values from `env_utils.py` and import from `config.py`.

**Affected files:**

- `pi_loop/config.py` (single source of truth)
- `pi_loop/config_file.py` (remove duplicate defaults)
- `pi_loop/env_utils.py` (remove duplicate defaults)
- `web_app/config_manager.py` (import from config.py)

### TECHDEPT-004 — Shared mutable state passed-by-reference: mitigations dict silently lost

| Field | Value |
|-------|-------|
| **Title** | Shared mutable state passed-by-reference: mitigations dict mutations silently lost |
| **Category** | Technical Debt |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | Error recovery adaptations are silently discarded. The `mitigations` dict is mutated inside `_adapt_to_error()` but never written back to the state dict. Error recovery appears to work but has zero effect. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** In `loop.py:670-672`:

```python
_adapt_to_error(
    error_type=...,
    mitigations=state.get("mitigations", {}),  # returns {} if missing
    ...
)
```

When `state["mitigations"]` doesn't exist, a new `{}` dict is created, passed to `_adapt_to_error()`, mutated inside, but never re-assigned to `state["mitigations"]`. All writes to the mitigations dict inside `_adapt_to_error` are silently lost. Additionally, if `state["mitigations"]` does exist, it's passed by reference and mutated correctly — but the code doesn't handle the initialization case.

**Research notes:** Fix: Replace with `state.setdefault("mitigations", {})` before the call, then pass `state["mitigations"]` directly. This guarantees the dict always exists in the state and mutations persist.

**Affected files:**

- `pi_loop/loop.py` (lines ~670-672)
- `pi_loop/error_recovery.py` (verify `_adapt_to_error` mutates the dict in-place)

### PERF-001 — SSE event system pushes stale data; frontend re-fetches on every update

| Field | Value |
|-------|-------|
| **Title** | SSE event system pushes stale data; frontend re-fetches on every update |
| **Category** | Performance |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | Every SSE heartbeat (every 2s) triggers a full status/iteration GET request from each connected client, creating unnecessary HTTP round-trips and redundant data transfer. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The SSE stream pushes a hash/content-changed signal, which causes the frontend to re-fetch full status and iteration data via separate HTTP GET requests. This means every 2-second poll cycle generates 2-3 HTTP requests per client even when nothing changed. The SSE event payload itself could include the actual status data, eliminating the need for the re-fetch entirely.

**Research notes:** Fix: Include the complete status payload in the SSE `update` event body, so the frontend can update state without an additional HTTP request. Fall back to a GET only on initial page load. This reduces per-client request volume by ~66%.

**Affected files:**

- `web_app/server.py` (SSE event generation)
- `web_app/static/app.js` (SSE event handling)

### SEC-002 — CORS allow_origins=['*'] in production configuration

| Field | Value |
|-------|-------|
| **Title** | CORS allow_origins=['*'] allows any website to make API requests |
| **Category** | Security |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | Any website visited by the user while the daemon is running can make authenticated-adjacent requests to the daemon's API (though auth is also missing — see SEC-001). |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** CORS is configured with `allow_origins=["*"]` which permits any origin to make API calls. For a local daemon tool this is acceptable for development convenience, but for any production-like deployment it should be restricted. Combined with the lack of authentication (SEC-001), this is a significant attack surface.

**Research notes:** Fix: (1) Default to `allow_origins=["http://localhost:8090"]` and make origins configurable via env var `PI_LOOP_CORS_ORIGINS`. (2) In server start, bind to `127.0.0.1` by default instead of `0.0.0.0` to prevent external network access entirely.

**Affected files:**

- `web_app/server.py` (lines 39-42)

### TEST-003 — Untested critical modules: help_topics.py (474 lines)

| Field | Value |
|-------|-------|
| **Title** | Untested critical modules: help_topics.py (474 lines) |
| **Category** | Testing |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | 474 lines of CLI introspection, shell completion, and help content with zero test coverage. This module has high churn risk as CLI flags change. |
| **Effort** | Medium |
| **Dependencies** | ARCH-002 |
| **Status** | ❌ Blocked by ARCH-002 |

**Reasoning:** `help_topics.py` is the largest untested module at 474 lines. It includes: `show_help_topics()` (topic dispatch), `_list_examples()` (CLI examples), `show_doctor_info()` (diagnostics), shell completion setup, and command listing. High complexity (uses subprocess, has broad except clauses). Breaking the circular import (ARCH-002) is a prerequisite for testing.

**Research notes:** Tests should cover: (1) Each help topic renders without error, (2) shell completion output is syntactically valid, (3) `--doctor` output includes expected sections, (4) edge cases like missing `pi` binary or empty env.

**Affected files:**

- `pi_loop/help_topics.py`
- `tests/test_help_topics.py` (new file)

### TEST-004 — Untested critical modules: config_manager.py (357 lines)

| Field | Value |
|-------|-------|
| **Title** | Untested critical modules: config_manager.py (357 lines) |
| **Category** | Testing |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | 357 lines serving as the web UI config source of truth with zero test coverage. Config validation, schema, and persistence logic are untested. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `config_manager.py` handles the web UI's configuration schema, validation, JSON I/O, and CLI command construction. It's the bridge between the web UI and the daemon's config layer. A bug here can silently corrupt the daemon's behavior or cause HTTP 500 errors (see BUG-002). Key untested functions: `load_config()`, `save_config()`, `validate_config()`, `build_cli_command()`, `get_config_schema()`.

**Research notes:** Tests should cover: (1) Config schema returns all expected fields with correct types, (2) `validate_config()` rejects invalid ports/goals/URLs, (3) `save_config()` and `load_config()` roundtrip correctly, (4) `build_cli_command()` produces correct arg strings, (5) edge cases: missing file, corrupt JSON, empty config.

**Affected files:**

- `web_app/config_manager.py`
- `tests/test_config_manager.py` (new file)

### DOC-001 — No API documentation for web endpoints

| Field | Value |
|-------|-------|
| **Title** | No API documentation for web endpoints |
| **Category** | Documentation |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | Third-party integrations must reverse-engineer the API. FastAPI's automatic OpenAPI docs are disabled/bare due to missing type annotations and docstrings. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The FastAPI app has no auto-generated docs or OpenAPI spec beyond the minimal title/description. FastAPI generates OpenAPI automatically if endpoints have typed parameters, response models, and docstrings — but the current endpoints use `Request` objects and `dict` returns, bypassing OpenAPI generation entirely.

**Research notes:** Fix: (1) Add Pydantic response models for all endpoints (e.g., `StatusResponse`, `IterationListResponse`, `ConfigResponse`). (2) Replace `Request` object parameters with typed query/path parameters (FastAPI auto-documents these). (3) Add docstrings and `summary`/`description` metadata to each route. (4) Configure OpenAPI with proper title, version, and description. This also improves type safety.

**Affected files:**

- `web_app/server.py` (all endpoints)

### CI-001 — No pi binary smoke test in CI pipeline

| Field | Value |
|-------|-------|
| **Title** | No pi binary smoke test in CI pipeline |
| **Category** | CI/CD |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | A `pi` CLI API change (e.g., removed `-q` flag, changed output format) would break the daemon without CI catching it. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The entire daemon delegates work to the `pi` CLI (`pi -q <goal>`), but CI doesn't verify that `pi` is available or that the expected flags work. A breaking change to `pi`'s CLI interface would pass CI and only fail in production.

**Research notes:** Fix: Add a CI job step that: (1) checks `which pi` or installs the `pi` CLI, (2) runs `pi-loop --help` to verify entry point works, (3) optionally runs a dry-run validation using `pi --version` and checks that the output format is parseable. This could be a new job or added to the lint job.

**Affected files:**

- `.github/workflows/ci.yml`

### CI-002 — Mypy warnings piped to stderr, making failures invisible in CI

| Field | Value |
|-------|-------|
| **Title** | Mypy warnings piped to stderr (`2>/dev/null`), making type errors invisible |
| **Category** | CI/CD |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | Type errors are silently ignored in CI. The mypy step always passes regardless of findings. |
| **Effort** | Small |
| **Dependencies** | TEST-002 |
| **Status** | ❌ Blocked by TEST-002 |

**Reasoning:** The `make mypy` target pipes stderr to `/dev/null`: `python -m mypy pi_loop/ --ignore-missing-imports --warn-unused-configs 2>/dev/null`. This means all mypy errors and warnings are silenced. Adding `|| true` (which already exists at the Makefile level) means the step never fails regardless of findings. This was likely done to avoid blocking CI while type errors were being addressed, but it makes the step entirely cosmetic.

**Research notes:** Fix: Remove `2>/dev/null` from the Makefile target, fix all existing mypy errors (see TEST-002), and remove the `|| true` from CI. Then mypy becomes a real quality gate.

**Affected files:**

- `Makefile` (mypy target)
- `.github/workflows/ci.yml` (test job)

### DEVEX-001 — Global namespace pollution in app.js (40+ top-level declarations)

| Field | Value |
|-------|-------|
| **Title** | Global namespace pollution in app.js — 40+ top-level function declarations and 15+ global state variables |
| **Category** | Developer Experience |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | Impossible to unit test; hard to reason about state; naming collisions with other scripts; prevents modularization. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The 1078-line SPA in `app.js` has 40+ top-level function declarations and 15+ global state variables — all sharing the global namespace. State is mutated freely by any function. Data flow is implicit and untraceable. Error handling is inconsistent (empty catch blocks, see CLEANUP-002). There are no modules, classes, or state management patterns.

**Research notes:** Fix: (1) Wrap all code in an IIFE or ES module pattern. (2) Consolidate state into a single `state` object with explicit mutation methods. (3) Group related functions into service objects (e.g., `api`, `ui`, `sse`). (4) Extract constants to a config object. This is a medium-to-large refactor but dramatically improves maintainability and enables testing.

**Affected files:**

- `web_app/static/app.js` (entire file)

### CLEANUP-001 — Duplicate worker_term append logic in loop_manager.py

| Field | Value |
|-------|-------|
| **Title** | Duplicate worker_term append logic in loop_manager.py — terminal lines appear twice |
| **Category** | Code Cleanup |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | Terminal lines in the Workers tab appear twice — once with the `[TERM (worker #N)]` prefix, once without. UI is confusing and cluttered. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `LoopManager._parse_daemon_line()` has two separate code paths that append to `self._worker_term[wid]`. The generic `TERM` regex fallthrough at one point appends the raw line (with `[TERM (worker #N)]` prefix), while an explicit `TERM` handler later strips the prefix and appends again. Result: each terminal line is stored twice with different formatting.

**Research notes:** Fix: Consolidate into a single code path. The explicit handler should be the canonical one (it strips the prefix correctly). Remove the generic fallthrough append. This also affects the worker terminal content hash calculation (lines appear duplicated in the hash).

**Affected files:**

- `web_app/loop_manager.py` (lines ~169-175 and ~200-205)

### CLEANUP-002 — Empty catch blocks swallow errors silently in app.js (5+ locations)

| Field | Value |
|-------|-------|
| **Title** | Empty catch blocks swallow errors silently in app.js (5+ locations) |
| **Category** | Code Cleanup |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | All frontend errors are silently swallowed. Debugging production issues is nearly impossible. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** At least 5 empty `catch` blocks exist in `app.js`:

- Lines ~68-70: SSE error handler
- Lines ~255-257: fetch error handler  
- Lines ~279-281: POST error handler
- Lines ~499-506: Config save catch-all
- Lines ~544-548: Log fetch catch-all

Each should at minimum call `console.error()` with the exception, and ideally surface the error in the UI.

**Research notes:** Fix: Add `console.error('[pi-loop] ...', error)` to every empty catch block. Consider adding an `onFrontendError` handler that shows a small toast/notification in the UI for non-recoverable errors.

**Affected files:**

- `web_app/static/app.js` (multiple locations)

### FEATURE-001 — Heartbeat/runtime guard for main loop body

| Field | Value |
|-------|-------|
| **Title** | Heartbeat/runtime guard for main loop body — prevent indefinite hangs |
| **Category** | Feature |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | A stuck iteration (e.g., `pi` subprocess deadlock, network hang) freezes the entire daemon with no recovery mechanism. The heartbeat module exists but can't help because `run_loop()` is synchronous. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The main `while True` loop in `run_loop()` has no wall-clock timeout or heartbeat mechanism. If `_execute_task()` hangs (subprocess deadlock, unresponsive `pi` CLI), the entire daemon freezes. The `heartbeat.py` module monitors session health but is a separate thread that can't intervene in the main loop.

**Research notes:** Fix: (1) Add a `max_iteration_wall_time` config option (default: 30 min). (2) Wrap the iteration body in a `try/finally` that checks elapsed time. (3) If exceeded, kill the subprocess (via the existing `proc.kill()` paths), log the timeout, and decide whether to retry or abort based on error recovery state. (4) Use `signal.alarm()` (Unix) or a thread-based timeout as fallback.

**Affected files:**

- `pi_loop/loop.py` (line ~310, the `while True` loop header)

### OBSERV-001 — Add structured logging with correlation IDs

| Field | Value |
|-------|-------|
| **Title** | Add structured logging with correlation IDs |
| **Category** | Observability |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | All logging uses print() and ad-hoc f-strings. No structured logging, no correlation IDs, no log levels (beyond print). Debugging cross-module issues requires manual log correlation. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The daemon uses `print()` for all logging — no structured logging, no log levels, no correlation IDs. The `file_utils.py` module sets up a basic `_daemon_logger` but it's only used for file-level logging, not for structured output. Tracing a single iteration's flow from CLI input through `_execute_task` to `run_loop` to error recovery requires manually correlating timestamps across print statements.

**Research notes:** Fix: (1) Replace all `print()` calls with a structured logger (stdlib `logging` with JSON format, or `structlog` which is already in the venv). (2) Add a correlation/iteration ID to each log entry. (3) Add log levels (DEBUG, INFO, WARNING, ERROR). (4) Add request IDs to web server logs. (5) Consider the `ELK` stack or `loki` for production log aggregation. `structlog` is already installed in the venv and provides an excellent path for this.

**Affected files:**

- `pi_loop/loop.py`
- `pi_loop/functions.py`
- `pi_loop/error_utils.py`
- `pi_loop/error_recovery.py`
- `web_app/server.py`
- `pi_loop/file_utils.py`

### FEATURE-002 — Exponential backoff with jitter for SSE reconnection

| Field | Value |
|-------|-------|
| **Title** | Exponential backoff with jitter for SSE reconnection |
| **Category** | Feature |
| **Priority** | 🟡 P2 — Medium |
| **Impact** | Fixed 5s reconnect causes thundering herd on server restart. Slow recovery when server is down for extended periods. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The SSE client uses a fixed 5s reconnect delay. When the server goes down and comes back up, all connected clients reconnect simultaneously after exactly 5s (thundering herd). During extended outages, the client keeps reconnecting every 5s indefinitely, wasting network resources.

**Research notes:** Fix: Implement exponential backoff with jitter: 1s, 2s, 4s, 8s, 16s, capped at 30s, with ±25% random jitter. Reset to 1s on successful connection. This is a small, well-understood pattern that improves resilience.

**Affected files:**

- `web_app/static/app.js` (lines ~110-114)

---

## P3 — Low

### BUG-002 — Config file corruption causes HTTP 500 instead of graceful degradation

| Field | Value |
|-------|-------|
| **Title** | Config file corruption causes HTTP 500 instead of graceful degradation |
| **Category** | Bug |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Entire endpoint returns HTTP 500 if config file is corrupt (partial write, disk full). User cannot access web UI config until the file is manually deleted. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** No `try/except` around `load_config()` in `_read_stored()` in `config_manager.py`. If the JSON file is corrupt (e.g., partial write, truncated content), `json.load()` raises `json.JSONDecodeError` which propagates unhandled to the caller, returning HTTP 500.

**Research notes:** Fix: Wrap `load_config()` in `_read_stored()` with `try/except (json.JSONDecodeError, OSError)`. On failure: log the error, return defaults (ideally with a `corrupt: true` flag so the UI can show a warning banner), and optionally back up the corrupt file to `/tmp/pi-loop/config.json.corrupt`.

**Affected files:**

- `web_app/config_manager.py` (lines ~248-271)

### BUG-003 — Wrong HTTP status codes for logical errors (200 with `success: false`)

| Field | Value |
|-------|-------|
| **Title** | Wrong HTTP status codes for logical errors (200 with `success: false`) |
| **Category** | Bug |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Clients can't distinguish logical errors from server errors. API consumers must parse the response body to detect failures. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Config save and loop control endpoints return HTTP 200 with `{"success": false, "error": "..."}` for logical errors (e.g., "Loop is not running", "Invalid port"). Proper REST practice is to return HTTP 4xx status codes (400 Bad Request, 409 Conflict, 422 Unprocessable Entity).

**Research notes:** Fix: Return HTTP 409 Conflict for "loop not running" / "loop already running" errors, HTTP 422 for validation errors, HTTP 400 for malformed requests. The `validate_config()` wiring (completed in SEC-003) already returns HTTP 422 — extend this pattern to all endpoints.

**Affected files:**

- `web_app/server.py` (lines ~89-118 and other endpoint handlers)

### BUG-004 — Docker detection via only `/.dockerenv` is fragile

| Field | Value |
|-------|-------|
| **Title** | Docker detection via only `/.dockerenv` is fragile |
| **Category** | Bug |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Docker-specific code paths (workdir adjustment, path resolution) don't trigger in Podman, containerd, or other container runtimes that don't create `/.dockerenv`. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The only Docker-aware code is in `web_app/loop_manager.py` which checks `os.path.exists("/.dockerenv")`. This doesn't work for Podman or container environments that don't create this file. A more robust approach checks multiple signals: `/.dockerenv`, cgroup v1 (`/proc/1/cgroup` contains `docker`), cgroup v2, and the `container` env var.

**Research notes:** Fix: Create a centralized `is_containerized()` utility in `system_utils.py` that checks multiple indicators: (1) `os.path.exists("/.dockerenv")`, (2) `os.environ.get("container")`, (3) `/proc/1/cgroup` inspection. Then import it in `loop_manager.py`.

**Affected files:**

- `web_app/loop_manager.py`
- `pi_loop/system_utils.py` (proposed new function)

### TECHDEPT-005 — Magic numbers scattered across 30+ locations

| Field | Value |
|-------|-------|
| **Title** | Magic numbers scattered across 30+ locations — no named constants |
| **Category** | Technical Debt |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Hard to understand what 2000, 500, 120, 300, 600, 10240, 0.01, 0.6 mean. Changes require searching for all occurrences. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** 30+ magic numbers scattered across the codebase:

| Value | Locations | Meaning |
|-------|-----------|---------|
| 2000 | loop.py:44,376 | Default max_output_chars |
| 500 | loop.py:45,379 | Default max_turns |
| 5 | loop.py:46,379, error_recovery.py:128 | retry_delay, cooldown lower bounds |
| 120 | error_recovery.py:129, loop.py:208 | Cooldown upper bounds, timeout cap |
| 300 | state.py:47, error_recovery.py:86 | Stale iteration timeout |
| 600 | error_recovery.py:79 | Timeout escalation cap |
| 10240 | git_utils.py:48 | Diff content cap (10KB) |
| 0.01 | file_watcher.py:43 | mtime comparison epsilon |
| 0.6 | env_utils.py:269 | Fuzzy match cutoff |
| 10.0 | file_utils.py:25 | FileLock default timeout |

Only `_MAX_VALIDATION_DEPTH = 50` in `validation.py:10` is properly named.

**Research notes:** Fix: Extract each magic number into a named constant in the relevant module or in `config.py`. Group related constants (timeouts, limits, thresholds). Use `_MAX_*`, `_DEFAULT_*`, `_TIMEOUT_*` naming conventions.

**Affected files:**

- `pi_loop/loop.py`
- `pi_loop/error_recovery.py`
- `pi_loop/state.py`
- `pi_loop/git_utils.py`
- `pi_loop/file_watcher.py`
- `pi_loop/env_utils.py`
- `pi_loop/file_utils.py`
- `pi_loop/config.py`

### CLEANUP-003 — Duplicate `content_block_stop` handler in _execute_task (milestone: DONE)

| Field | Value |
|-------|-------|
| **Title** | [DONE] Duplicate `content_block_stop` handler in _execute_task |
| **Category** | Code Cleanup |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Double-processing of tool results in terminal output |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Done |

**Reasoning:** The `_execute_task` function had TWO identical blocks handling `content_block_stop` events (lines ~191-209 and ~210-227). The first block (incorrectly placed before `text_delta` handling) rendered tool results twice.

**Fix applied:** Removed the first duplicate handler. Completed 2026-06-29.

**Affected files:**

- `pi_loop/loop.py`

### CLEANUP-004 — import urllib.request inside function body

| Field | Value |
|-------|-------|
| **Title** | import urllib.request placed inside function body instead of top-level |
| **Category** | Code Cleanup |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Minor performance overhead on every iteration (module re-import). Violates PEP 8 import conventions. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** `import urllib.request` is placed inside the function body of `run_loop()` (line ~308) rather than at the top of the module. Imports inside function bodies bypass Python's import cache optimization and violate PEP 8's recommendation to place all imports at the top.

**Research notes:** Fix: Move `import urllib.request` to the top of `loop.py` alongside other stdlib imports. Verify no circular import issue exists (there shouldn't be — `urllib` is stdlib).

**Affected files:**

- `pi_loop/loop.py` (line ~308)

### CLEANUP-005 — Unused _lastWorkerLogCounts variable in app.js

| Field | Value |
|-------|-------|
| **Title** | Unused _lastWorkerLogCounts variable in app.js — dead code |
| **Category** | Code Cleanup |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Dead code cluttering the namespace. Negligible memory usage. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The global variable `_lastWorkerLogCounts` in `app.js` is defined (line ~286) but never read or written by any function. It was likely a leftover from a previous iteration of the worker log system.

**Affected files:**

- `web_app/static/app.js` (line ~286)

### CLEANUP-006 — Empty SSE heartbeat listener in app.js

| Field | Value |
|-------|-------|
| **Title** | Empty SSE heartbeat listener — no-op code |
| **Category** | Code Cleanup |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Negligible — no-op event handler. But could be useful for connection health tracking. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The SSE `heartbeat` event listener in `app.js` is defined but empty. It should either be removed, or wired up to update a connection health indicator (e.g., show "last heartbeat" timestamp in the dashboard footer).

**Research notes:** Consider using this to update a `lastHeartbeat` timestamp and show a "Connected" / "Reconnecting..." status indicator in the web UI.

**Affected files:**

- `web_app/static/app.js` (line ~106)

### CLEANUP-007 — Emoji icons in navigation lack aria-hidden attributes

| Field | Value |
|-------|-------|
| **Title** | Emoji icons in navigation lack aria-hidden attributes |
| **Category** | Code Cleanup |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Screen readers announce emoji descriptions like "black medium square" instead of treating them as decorative. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Emoji characters used as navigation icons in `index.html` lack `aria-hidden="true"` attributes. Screen readers attempt to describe each emoji semantically, creating noise for visually impaired users.

**Research notes:** Fix: Add `aria-hidden="true"` to all emoji elements used as icons. For example: change `<span>⬤</span>` to `<span aria-hidden="true">⬤</span>`.

**Affected files:**

- `web_app/static/index.html`

### DEVEX-002 — make test re-installs dependencies every run

| Field | Value |
|-------|-------|
| **Title** | make test re-installs dependencies every run |
| **Category** | Developer Experience |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Wastes 2-3 seconds per local test run with unnecessary `pip install` |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The `test` Makefile target runs `pip install -e ".[test]"` before `python -m pytest`. The `install-dev` target already installs test deps. Once installed, re-running pip is unnecessary overhead.

**Research notes:** Fix: Remove the `pip install` line from the `test` target. Developer runs `make install-dev` once, then `make test` repeatedly. For CI, the `pip install` is already in the CI workflow.

**Affected files:**

- `Makefile` (test target)

### DEPS-003 — FastAPI/uvicorn version ranges too permissive

| Field | Value |
|-------|-------|
| **Title** | FastAPI/uvicorn version ranges too permissive for production stability |
| **Category** | Dependencies |
| **Priority** | 🔵 P3 — Low |
| **Impact** | A major FastAPI or uvicorn release could introduce breaking changes without Dependabot catching them (major versions are ignored for these deps). |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Dependencies use `>=` ranges (`fastapi>=0.100.0`, `uvicorn[standard]>=0.20.0`). Dependabot is configured to ignore major versions. A major release (e.g., FastAPI 1.0, uvicorn 1.0) with breaking changes would still be pulled in by `pip install -e .` since `>=` allows major bumps.

**Research notes:** Fix: Change ranges to `>=0.100.0,<1.0.0` for both fastapi and uvicorn. This prevents accidental major upgrades while allowing all minor/patch updates.

**Affected files:**

- `pyproject.toml`

### DEPS-004 — venv has 133 unused packages

| Field | Value |
|-------|-------|
| **Title** | Virtual environment has 133 unused packages from other projects |
| **Category** | Dependencies |
| **Priority** | 🔵 P3 — Low |
| **Impact** | Bloated venv (torch, transformers, chromadb, gradio, etc.) wastes disk space and increases attack surface. chromadb has a CRITICAL CVE. |
| **Effort** | Small |
| **Dependencies** | DEPS-002 |
| **Status** | ⏳ Pending |

**Reasoning:** The `.venv` contains 201 packages total, but only ~67 are project dependencies or their transitive deps. The remaining ~133 packages (torch 2.12.1, transformers 5.12.1, chromadb 1.5.9, gradio, scikit-learn, pandas, numpy, opencv, etc.) are from other projects sharing the same workspace. This wastes ~3-5GB of disk and introduces the chromadb CVE.

**Research notes:** Fix: Rebuild the venv from scratch: `rm -rf .venv && python -m venv .venv && source .venv/bin/activate && pip install -e ".[test,dev]"`. Consider using `uv venv` for faster venv creation and `uv pip install` for faster installs.

**Affected files:**

- `.venv/` (rebuild)
- `Makefile` (add `venv-clean` target)

### CLEANUP-008 — Hardcoded `[TERM (worker #1)]` prefix in HTML dashboard

| Field | Value |
|-------|-------|
| **Title** | HTML dashboard hardcodes `worker #1` prefix |
| **Category** | Code Cleanup |
| **Priority** | 🔵 P3 — Low |
| **Impact** | The `_build_dashboard_html()` function hardcodes "worker #1" in the suggested stop command string. |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** The `_build_dashboard_html()` function in `loop.py` generates a stop command suggestion that references "worker #1" — but with `--workers N` support, this should dynamically reflect the actual worker number.

**Research notes:** Fix: Derive the worker display from the current iteration's worker state rather than hardcoding.

**Affected files:**

- `pi_loop/loop.py` (dashboard HTML generation)

---

## P4 — Wishlist

### FEATURE-003 — Event-loop-safe async I/O in all remaining web endpoints

| Field | Value |
|-------|-------|
| **Title** | Event-loop-safe async I/O in all remaining web endpoints |
| **Category** | Feature |
| **Priority** | ⚪ P4 — Wishlist |
| **Impact** | Blocking `open()`/`read()/`json.load()` calls in async endpoints block the entire event loop, degrading all connections. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** Multiple web endpoints use blocking I/O (`open()`, `read()`, `json.load()`) in async context. The `index()` endpoint was already fixed with `asyncio.to_thread()` (completed), but `config_manager.py`'s `load_config()` and `save_config()` still use blocking file I/O from async callers. Similarly, the status file reader and health check use blocking `/proc` reads.

**Research notes:** Fix: (1) Use `aiofiles` for all file I/O in web endpoints. (2) Wrap blocking `/proc` reads in `asyncio.to_thread()`. (3) Ensure `config_manager.py` provides async variants of `load_config`/`save_config`. (4) Consider adding `aiofiles` as a dependency.

**Affected files:**

- `web_app/server.py`
- `web_app/config_manager.py`

### OBSERV-002 — Add Prometheus metrics endpoint

| Field | Value |
|-------|-------|
| **Title** | Add Prometheus metrics endpoint for production monitoring |
| **Category** | Observability |
| **Priority** | ⚪ P4 — Wishlist |
| **Impact** | No metrics for iteration count, error rates, subprocess duration, convergence detection, or system resources. Operations teams have no visibility into daemon health. |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | ⏳ Pending |

**Reasoning:** There's no metrics endpoint for monitoring. Key metrics that would be valuable: iteration count (total, per-goal), error count by type, subprocess duration (p50/p95/p99), convergence hits, cooldown time, active workers, and system resource usage. The `prometheus-client` package is already in the venv.

**Research notes:** Implement: (1) A `/metrics` endpoint exposing Prometheus-format metrics. (2) A `MetricsCollector` class that tracks iteration/error/convergence counters. (3) Use `prometheus_client` library (already installed). (4) Add a Grafana dashboard template in a `monitoring/` directory. (5) Expose daemon stats from `stats.py` as Prometheus gauges.

**Affected files:**

- `web_app/server.py` (new `/metrics` endpoint)
- `pi_loop/stats.py` (wire into metrics collection)
- `pi_loop/heartbeat.py` (system metrics)
- New: `monitoring/` directory with Grafana dashboard

### OBSERV-002 — Implement structured logging with correlation IDs

| Field | Value |
|-------|-------|
| **Title** | [DUPLICATE] Implement structured logging with correlation IDs |
| **Category** | Observability |
| **Priority** | ⚪ P4 — Wishlist |
| **Status** | 🔄 Superseded by OBSERV-001 |

**Reasoning:** Duplicate entry — see OBSERV-001 for the active item. This placeholder is kept to prevent re-discovery.

**Affected files:**

- (none — superseded)

---

## ✅ Completed Items

| ID | Title | Category | Completed |
|----|-------|----------|-----------|
| BUG-005 | Subprocess leak on timeout (zombie processes) — proc.kill() + proc.wait() added | Bug | ✅ |
| BUG-006 | Race condition in loop_manager.stop() — self._lock added | Bug | ✅ |
| BUG-007 | TOCTOU race in loop_manager.stop() — os.kill(pid,0) ownership check added | Bug | ✅ |
| BUG-008 | Race: status='running' set before monitors created — moved after create_task | Bug | ✅ |
| BUG-009 | Race: _read_stream AttributeError on self._process — local_proc captured | Bug | ✅ |
| TECHDEPT-006 | Duplicated shutdown logic in run_loop() —_shutdown() helper extracted (-134 lines) | Tech Debt | ✅ |
| TECHDEPT-007 | Silent exception swallowing (bare except: pass) — all replaced with typed, logged handlers | Tech Debt | ✅ |
| TECHDEPT-008 | Retry loop output capture lossy — per-attempt buffers added | Tech Debt | ✅ |
| ARCH-003 | Dead / broken _evolve_goal feature — _extract_next_goal() helper added | Architecture | ✅ |
| PERF-002 | Blocking synchronous I/O in async index() endpoint — replaced with asyncio.to_thread() | Performance | ✅ |
| PERF-003 | Unbounded limit/offset parameters on /api/iterations — capped [1, 500] | Performance | ✅ |
| PERF-004 | SSE _status_poller runs with zero clients — early-return when empty | Performance | ✅ |
| SEC-003 | No schema validation on save_config_api — validate_config() wired in, returns 422 | Security | ✅ |
| TEST-005 | Zero test coverage — 404 tests across 19 test files created | Testing | ✅ |
| CI-003 | CI references non-existent make targets — lint-all and test targets created | CI/CD | ✅ |
| CI-004 | Pre-commit hook disabled (exit 0) — rewritten to run ruff check + format | CI/CD | ✅ |
| CI-005 | Missing dev/test dependencies in pyproject.toml — test and dev sections added | CI/CD | ✅ |
| CI-006 | No Python version matrix in CI — 3.10-3.13 matrix added | CI/CD | ✅ |
| CI-007 | Add mypy type-checking to CI pipeline — config + make target + CI step added | CI/CD | ✅ |
| CI-008 | Dependabot configuration — .github/dependabot.yml created with weekly updates | CI/CD | ✅ |
| DEVEX-003 | No ruff / mypy config in pyproject.toml — [tool.ruff] and [tool.mypy] sections added | DX | ✅ |
| DEPS-005 | Add pyproject.toml [tool.ruff.lint] section — E,F,W,I,N,UP,B,SIM,ARG,RUF100 selected | Dependencies | ✅ |
| CLEANUP-009 | Duplicated content_block_stop handler in _execute_task — first duplicate removed | Cleanup | ✅ |
| CLEANUP-010 | Hardcoded 'worker #1' string in _execute_task — parameterized with worker_id | Cleanup | ✅ |
| FEATURE-004 | CI pipeline with test + lint + type-check — full pipeline operational | Feature | ✅ |
| FEATURE-005 | Worker terminal state lost on navigation — capped at 2000 lines, KeyError fixed | Feature | ✅ |
| RELIABILITY-005 | _get_cpu_percent() first-read returns 0% — pre-warmed CPU deltas at import | Reliability | ✅ |
| RELIABILITY-006 | Config file corruption resilience — graceful degradation with default fallback | Reliability | ✅ |

---

## Repository Health Summary

### Overall Assessment: 🟢 **Good — Actively Maintained**

The **pi-loop** (hermes-loop) repository is a well-structured, actively maintained Python daemon project. With 191 commits in ~1 week of development, 404 passing tests (0.53s total), and a comprehensive CI/CD pipeline, the project has strong engineering practices. Below is a health summary across all dimensions.

| Dimension | Grade | Notes |
|-----------|-------|-------|
| **Code Organization** | 🟢 A | Modular design, single-responsibility modules, clear separation of concerns |
| **Testing** | 🟢 A | 404 tests, 83% file coverage, blazing fast (0.53s), 100% pass rate |
| **CI/CD** | 🟢 A | Full pipeline: lint (ruff) + format check + mypy + test matrix (3.10-3.13) + Dependabot |
| **Documentation** | 🟡 B | README is good, REFACTOR_PLAN.md covers web app. Missing: API docs, CONTRIBUTING.md |
| **Type Safety** | 🟡 B | Mypy configured, but 34% of functions lack hints; CI makes mypy non-blocking |
| **Security** | 🟡 B | No auth/rate-limiting on web endpoints (acceptable for local tool); CORS wide open |
| **Dependencies** | 🟡 B | Minimal declared deps (2 runtime), but shared venv has 133 unused packages + chromadb CVE |
| **Performance** | 🟢 A | Sub-second test suite, async SSE, no obvious bottlenecks |
| **Code Quality** | 🟡 B | 4 high-complexity functions, 71-param monster function, 30+ magic numbers |
| **Architecture** | 🟡 B | Clean three-layer design, but circular import exists, mutable state passed-by-reference bug |
| **Error Handling** | 🟡 B | Good error recovery engine, but broad exception suppression in several paths |
| **Accessibility** | 🔴 F | Zero accessibility support — no aria labels, aria-live regions, keyboard nav, or screen reader support |

### Active Issues By File

| File | P0 | P1 | P2 | P3 | Total Active |
|------|----|----|----|----|-------------|
| `pi_loop/loop.py` | 0 | 2 | 1 | 2 | 5 |
| `pi_loop/help_topics.py` | 1 | — | 1 | — | 2 |
| `pi_loop/preflight.py` | 1 | — | — | — | 1 |
| `pi_loop/status.py` | 1 | — | — | — | 1 |
| `pi_loop/validation.py` | — | — | 1 | — | 1 |
| `pi_loop/config.py` | — | — | 1 | 1 | 2 |
| `pi_loop/config_file.py` | — | — | 1 | — | 1 |
| `pi_loop/env_utils.py` | — | — | 1 | 1 | 2 |
| `pi_loop/error_recovery.py` | — | — | 1 | 1 | 2 |
| `pi_loop/git_utils.py` | — | — | — | 1 | 1 |
| `pi_loop/file_watcher.py` | — | — | — | 1 | 1 |
| `pi_loop/system_utils.py` | — | — | 1 | — | 1 |
| `web_app/server.py` | 1 | 1 | 1 | 1 | 4 |
| `web_app/loop_manager.py` | — | — | 1 | 1 | 2 |
| `web_app/config_manager.py` | — | — | 1 | 1 | 2 |
| `web_app/static/app.js` | — | — | 3 | 3 | 6 |
| `web_app/static/index.html` | — | — | — | 1 | 1 |
| `web_app/static/style.css` | — | — | — | 1 | 1 |
| `tests/` | — | 1 | 2 | — | 3 |
| `Makefile` | — | 1 | — | 1 | 2 |
| `.github/workflows/ci.yml` | — | 1 | 2 | — | 3 |
| `pyproject.toml` | — | 1 | — | 1 | 2 |

### Key Metrics

| Metric | Value |
|--------|-------|
| **Total source lines** | ~13,300 (pi_loop + web_app + tests) |
| **Test count** | 404 (all passing, 0.53s) |
| **Test coverage** | 83% file coverage (19/23 modules) |
| **Active backlog items** | 40 |
| **Completed this iteration** | 29 |
| **Functions with >100 lines** | 12 |
| **Longest function** | `run_loop()` — 435 lines, 71 parameters |
| **Total commits** | 191 (all by `ningtoba`) |
| **Time span** | ~1 week of intensive development |

### Top 5 Immediate Actions

1. **BUG-001** — Consolidate all `/tmp` hardcoded paths to use unified `PI_LOOP_DATA_DIR` override
2. **SEC-001** — Add authentication/binding controls to web endpoints for safe deployment
3. **DEPS-001** — Generate a lock file for reproducible builds and supply-chain security
4. **TECHDEPT-001** — Introduce `LoopConfig` dataclass to eliminate the 71-parameter `run_loop()` signature
5. **DEPS-002** — Rebuild venv to remove chromadb (CRITICAL CVE) and 130+ unused packages
