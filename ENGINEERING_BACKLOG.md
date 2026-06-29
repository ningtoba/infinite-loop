# Engineering Backlog

## How to Use This Backlog

This backlog consolidates all engineering concerns discovered during the comprehensive codebase audit of **pi-loop v14.39.0**. Each item is actionable, specific, and references actual source locations.

**Organization**: Items are sorted by priority (critical → high → medium → low), and within each priority tier by impact (critical impact first).

**Status lifecycle**: `backlog` → `researching` → `in-progress` → `completed`

**Maintenance**: When starting work on an item, move it to `in-progress`. When adding new discoveries, insert them at the correct priority/impact position and renumber all subsequent B-IDs. Keep descriptions crisp — 2–4 sentences plus the suggested approach. Archive completed items to a `## Completed` section at the bottom.

---

## Backlog Items

### B-001 | Escape HTML in dashboard HTML generation

| Field | Value |
|---|---|
| **Category** | security |
| **Priority** | critical |
| **Impact** | critical |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/loop.py` |

**Description**: `_build_dashboard_html()` in `loop.py` interpolates iteration summaries directly into HTML via f-strings without escaping. If a pi session outputs `<script>alert('XSS')</script>`, it will execute when the dashboard is viewed. This is a reflected XSS vulnerability.

**Suggested Approach**: Wrap all interpolated values (`summary`, `status`, `duration`, etc.) with `html.escape()` before inserting into HTML template strings. Validate that the dashboard HTML generation uses consistent escaping for every interpolated variable.

---

### B-002 | Escape HTML in web SPA frontend

| Field | Value |
|---|---|
| **Category** | security |
| **Priority** | critical |
| **Impact** | critical |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `web_app/static/app.js` |

**Description**: Multiple locations in `app.js` use `insertAdjacentHTML` and `innerHTML` with template-literal string interpolation (iteration rows, error rows, worker output). The `escapeHtml()` helper exists but is used inconsistently — many template interpolations bypass it, creating client-side XSS vectors.

**Suggested Approach**: Audit every `innerHTML` / `insertAdjacentHTML` call in `app.js`. Apply `escapeHtml()` to all user-controlled data at every interpolation point. Consider migrating to `textContent` + DOM element creation for high-risk areas.

---

### B-003 | Silent I/O failure swallowing in config, git, and status writers

| Field | Value |
|---|---|
| **Category** | tech-debt |
| **Priority** | critical |
| **Impact** | high |
| **Effort** | medium |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/config_file.py:49`, `pi_loop/git_utils.py:22,35`, `pi_loop/status.py:58`, `pi_loop/heartbeat.py:37,40,57` |

**Description**: At least 6 locations across 4 modules catch OSError or generic exceptions and silently `pass`, swallowing I/O failures. This includes config file writes, git operations, status file writes, and heartbeat touches. Silent failures make debugging production issues extremely difficult — a config change that fails to persist or a git commit that silently fails will go undetected.

**Suggested Approach**: Replace bare `pass` with `logger.warning("...")` calls that include the exception message. For non-fatal failures, still log at warning level. For git operations, consider a `_safe_git_call()` wrapper that always logs on failure. Use `logger.exception()` at debug level when re-raising is inappropriate.

---

### B-004 | Mutable module-level global state across multiple modules

| Field | Value |
|---|---|
| **Category** | architecture |
| **Priority** | critical |
| **Impact** | high |
| **Effort** | medium |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/error_recovery.py:14-18`, `pi_loop/functions.py:15-20`, `pi_loop/heartbeat.py:23`, `pi_loop/file_utils.py:20`, `web_app/server.py` (multiple) |

**Description**: Five modules use mutable module-level globals (`_ORIGINAL_*`, `_max_output_chars_global`, `_shutdown_requested`, `_daemon_logger`, `_last_cpu_*`) that are mutated at runtime. Module-level mutable state makes testing (state leaks between tests), concurrent access, and reasoning about data flow unpredictable.

**Suggested Approach**: Encapsulate each set of related globals into a class or dataclass instance. Use dependency injection where appropriate (pass `daemon_logger` to `FileLock` constructor, pass `max_output_chars` as a parameter). For `error_recovery.py`, turn `_ORIGINAL_*` into instance attributes of an `ErrorRecoveryStrategy` class.

---

### B-005 | LoopConfig god dataclass with 50+ fields

| Field | Value |
|---|---|
| **Category** | architecture |
| **Priority** | critical |
| **Impact** | high |
| **Effort** | medium |
| **Dependencies** | B-001 (indirect — large refactors should follow XSS fixes) |
| **Status** | backlog |
| **Affected Files** | `pi_loop/config.py:68-179` |

**Description**: `LoopConfig` is a single dataclass with 50+ fields covering iteration control, workers, git, notifications, archiving, logging, safety, and advanced options. It violates the Single Responsibility Principle. The `from_args()` method imports `dataclasses._MISSING_TYPE` — a private API that could break between Python versions.

**Suggested Approach**: Split into focused config dataclasses: `IterationConfig`, `WorkerConfig`, `GitConfig`, `NotificationConfig`, `ArchiveConfig`, `SafetyConfig`, `LoggingConfig`. Compose them in a top-level `AppConfig` container. Replace the `_MISSING_TYPE` import with a sentinel value defined in the project.

---

### B-006 | Monolithic run_loop function in loop.py (300+ lines)

| Field | Value |
|---|---|
| **Category** | architecture |
| **Priority** | critical |
| **Impact** | high |
| **Effort** | large |
| **Dependencies** | B-005 (LoopConfig extraction enables cleaner parameter passing) |
| **Status** | backlog |
| **Affected Files** | `pi_loop/loop.py` |

**Description**: The `run_loop()` function is a 300+ line monolithic function that handles worker spawning, iteration lifecycle, error classification, notification dispatch, dashboard HTML generation, goal evolution, convergence detection, heartbeat management, cooldown handling, and ledger pruning. This makes it extremely difficult to test, debug, or modify individual concerns.

**Suggested Approach**: Extract distinct concerns into dedicated classes: `IterationEngine` (iteration lifecycle), `WorkerPool` (subprocess management), `NotificationDispatcher` (desktop/callback/ntfy), `DashboardBuilder` (HTML generation), `ConvergenceDetector` (idle/converged logic). Each class should have a single responsibility and be independently testable.

---

### B-007 | Potential XSS via http-callback-secret leaking into logs

| Field | Value |
|---|---|
| **Category** | security |
| **Priority** | critical |
| **Impact** | high |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/parser.py:207`, `pi_loop/loop.py` |

**Description**: The `--http-callback-secret` flag allows passing a secret that gets printed in verbose logging. If the secret ends up in log files or the JSON ledger, it creates a credential exposure risk. Additionally, the secret is stored in the config file unencrypted.

**Suggested Approach**: Mask the secret value in log output (show only first/last 2 characters with `****` in between). Add a note in docs about secure storage of the callback secret. Consider supporting file-based secrets (`--http-callback-secret-file`) that are read from a restricted-permissions file.

---

### B-008 | No automated security scanning in CI

| Field | Value |
|---|---|
| **Category** | ci-cd |
| **Priority** | high |
| **Impact** | critical |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `.github/workflows/ci.yml`, `pyproject.toml` |

**Description**: There is no security scanning in CI — no `bandit` for static analysis, no `safety`/`pip-audit` for dependency vulnerability scanning, no codeql or semgrep. Given that the project handles secrets (API keys, callback secrets) and has already addressed a starlette CVE, baseline scanning should be automatic.

**Suggested Approach**: Add `bandit` and `safety` to `requirements-dev.txt` (or use `pip-audit` which is built-in via `pip install pip-audit`). Add a `make security` target. Add a `security` job to `.github/workflows/ci.yml` that runs bandit on `pi_loop/` and `web_app/`, and safety on `requirements.txt`.

---

### B-009 | No version tags or release workflow

| Field | Value |
|---|---|
| **Category** | ci-cd |
| **Priority** | high |
| **Impact** | critical |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pyproject.toml`, `.github/workflows/` |

**Description**: Despite mentioning v14.39.0 everywhere in the codebase, there are zero git tags and no release workflow. There is no way to `git checkout v14.4.0` or identify which commit corresponds to a given version. No CI job publishes to PyPI or creates GitHub releases.

**Suggested Approach**: Create a `release.yml` GitHub Actions workflow that runs on tag push (`v*`). The workflow should run tests, build the package, create a GitHub release with auto-generated changelog, and optionally publish to PyPI. Add a `make release` target that tags and pushes.

---

### B-010 | /proc filesystem dependency makes project Linux-only

| Field | Value |
|---|---|
| **Category** | architecture |
| **Priority** | high |
| **Impact** | high |
| **Effort** | medium |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/system_utils.py`, `web_app/server.py:166-199`, `pi_loop/status.py:39` |

**Description**: CPU/memory monitoring in `system_utils.py` reads `/proc/[pid]/status` and `/proc/stat`. The web app's `_get_cpu_percent()` reads `/proc/stat` and `/proc/meminfo`. `status.py` uses `os.sysconf_names["SC_CLK_TCK"]`. These assumptions prevent the project from running on macOS/BSD without crashing on system monitoring features.

**Suggested Approach**: Create a `SystemResourceProvider` abstract base class with methods `get_cpu_percent()`, `get_memory_info()`, `get_process_usage()`. Implement `LinuxProvider` (current `/proc` logic) and `NoopProvider` (returns 0/empty dict with a warning log). Auto-detect OS at import time and choose the appropriate provider.

---

### B-011 | JSON extraction performs two full scans of output

| Field | Value |
|---|---|
| **Category** | performance |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/file_utils.py` (JSON extraction logic, ~line 120) |

**Description**: The `extract_json_from_output()` function performs two full scans of the output text (backward and forward) searching for balanced braces to extract JSON objects. For large outputs, this doubles the work. Additionally, the function uses naive brace counting that can break on strings containing braces.

**Suggested Approach**: Implement a single-pass parser that tracks brace depth while accounting for string literals (skip braces inside `"..."`). Use a stack-based approach: push on `{`, pop on `}`, and record string start/end positions. This is O(n) single-pass and correctly handles braces in strings.

---

### B-012 | Busy-wait with no backoff in file lock

| Field | Value |
|---|---|
| **Category** | performance |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/file_utils.py:45-46` |

**Description**: The `FileLock.__enter__()` busy-waits with a fixed 100ms sleep interval until the timeout is reached. Under contention (two pi-loop instances, or pi-loop + web UI simultaneously), this creates unnecessary wakeups and CPU usage. No exponential backoff is used.

**Suggested Approach**: Replace the fixed `time.sleep(0.1)` with exponential backoff: start at 10ms, double up to ~1s max, cap at remaining timeout. Use `min(backoff, remaining)` to avoid overshooting the deadline.

---

### B-013 | Cooldown implementation blocks with synchronous sleep

| Field | Value |
|---|---|
| **Category** | performance |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/functions.py:104-107` |

**Description**: The cooldown handler in `_handle_cooldown()` uses `time.sleep(1)` in a loop until the cooldown elapses. This blocks the main thread for seconds at a time and prevents clean cancellation (SIGTERM/SIGINT won't interrupt `time.sleep` until it wakes).

**Suggested Approach**: Replace `time.sleep(1)` with `_shutdown_event.wait(timeout=1)`. This allows immediate cancellation when the shutdown event is set while still ticking at 1-second intervals. The shutdown event comes from `heartbeat.py`'s `_shutdown_requested` — ensure it's passed into the cooldown function.

---

### B-014 | No testing documentation despite 25+ test files

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | high |
| **Impact** | high |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `README.md`, `tests/` (all) |

**Description**: The project has 25+ test files with 481 tests, but there is zero documentation on how to run, write, or understand tests. No explanation of the `smoke` marker, no guidance on using `conftest.py` fixtures, no testing conventions, no coverage thresholds or expectations.

**Suggested Approach**: Add a "Testing" section to `README.md` or create `CONTRIBUTING.md` with: how to run specific test subsets (`pytest tests/test_loop.py`), what `smoke` tests are and when to run them (`pytest -m smoke`), how to use shared fixtures from `conftest.py`, and coverage expectations. Document the `@pytest.mark.smoke` practice.

---

### B-015 | No CONTRIBUTING.md for new developers

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | high |
| **Impact** | high |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | (new file) |

**Description**: There is no contributor guide. A new developer cloning the repo has no guidance on: how to set up the dev environment, commit message conventions (though the project uses Conventional Commits), PR workflow, code review expectations, or testing requirements.

**Suggested Approach**: Create `CONTRIBUTING.md` covering: development setup (`. venv/bin/activate && make install-dev`), commit message format (Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `perf:`, `test:`), pre-commit hooks setup, how to run lint/format/test, and PR checklist. Reference the existing `Makefile` targets.

---

### B-016 | No CHANGELOG.md or release history

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | B-009 (tagging should precede changelog generation) |
| **Status** | backlog |
| **Affected Files** | (new file) |

**Description**: Version 14.39.0 exists in `__init__.py` and commit messages, but there is no changelog. A user or developer cannot determine what changed between versions, what features were added, what bugs were fixed, or whether upgrading introduces breaking changes.

**Suggested Approach**: Create `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/) format. Populate initial entries from git history (commit messages with `feat:`, `fix:`, `perf:`, `refactor:` prefixes). Add a `make changelog` target for auto-generation. Consider using `git-cliff` or a similar tool for structured changelog generation.

---

### B-017 | No deployment documentation (Docker, systemd, reverse proxy)

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | medium |
| **Dependencies** | B-010 (/proc abstraction needed for cross-platform Docker images) |
| **Status** | backlog |
| **Affected Files** | `README.md`, (new files: `Dockerfile`, `docker-compose.yml`) |

**Description**: The project implements security features (API keys, rate limiting, CORS) that anticipate production use, but there is no deployment guide. No Dockerfile, no docker-compose.yml, no systemd service file, no reverse proxy (nginx/Caddy) example config, no production-vs-development guidance.

**Suggested Approach**: Create `Dockerfile` (multi-stage: build in one stage, run in a slimmer Python-slim stage). Create `docker-compose.yml` with service definition, volume mounts for config/ledger, env vars, and port mapping. Create a `deploy/` directory with systemd service file and example nginx config. Add a "Production Deployment" section to `README.md`.

---

### B-018 | REST API has no documentation or OpenAPI spec

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `web_app/server.py`, `README.md` |

**Description**: The FastAPI server exposes 20+ REST endpoints (loop control, config CRUD, status, ledger, iterations, logs, system, SSE streams), but there is no API documentation anywhere. A developer cannot programmatically interact with the daemon without reading the source. FastAPI's automatic OpenAPI generation appears to be disabled or undocumented.

**Suggested Approach**: Ensure FastAPI's automatic OpenAPI docs are accessible (route for `/docs` and `/openapi.json`). Add docstrings to every endpoint function in `server.py` describing purpose, request schema, response schema, and error codes. Add a "REST API" section to `README.md` with key endpoints and example `curl` commands.

---

### B-019 | No standalone security documentation (SECURITY.md)

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | (new file) |

**Description**: The project has implemented security features (API-key auth middleware with timing-safe comparison, rate limiting, CORS hardening, localhost-only default binding), but there is no `SECURITY.md` to guide responsible disclosure or describe the security posture.

**Suggested Approach**: Create `SECURITY.md` with: supported versions, how to report a vulnerability (email or GitHub private vulnerability reporting), current security controls (auth, rate limiting, CORS), and security recommendations for deployment (TLS termination at reverse proxy, API key management, binding to localhost + reverse proxy).

---

### B-020 | No API endpoint reference in README or docs

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | B-018 (API docs prerequisite) |
| **Status** | backlog |
| **Affected Files** | `README.md` |

**Description**: The README has excellent sections for CLI usage and security, but there is no REST API endpoint reference. A developer integrating pi-loop into a larger system must reverse-engineer the endpoints from `server.py`.

**Suggested Approach**: After adding FastAPI docstrings (B-018), create an API reference table in `README.md` with: method, path, description, auth required (yes/no), and key parameters. Include example `curl` commands for the most common operations (start loop, get status, update config, stream logs via SSE).

---

### B-021 | No automated dependency vulnerability scanning

| Field | Value |
|---|---|
| **Category** | dependency |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `.github/workflows/ci.yml`, `requirements.txt` |

**Description**: The project uses `pip-compile` for lock files and has Dependabot configured for weekly updates, but there is no automated vulnerability scanning. The prior starlette CVE was discovered and fixed manually. A `safety` or `pip-audit` scan in CI would catch newly discovered CVEs automatically.

**Suggested Approach**: Add `pip-audit` (or `safety`) to dev dependencies. Add a `make audit` target that runs `pip-audit -r requirements.txt -r requirements-dev.txt`. Add an `audit` job to `.github/workflows/ci.yml`. Configure Dependabot to alert on security advisories (it does this by default for pip).

---

### B-022 | Lock files stale — installed versions lag behind lockfile

| Field | Value |
|---|---|
| **Category** | dependency |
| **Priority** | high |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `requirements.txt`, `requirements-dev.txt` |

**Description**: The installed packages in `.venv` lag behind the pinned lockfile versions (e.g., pydantic 2.12.5 installed vs 2.13.4 in lockfile). This suggests the last `pip install` used range resolution instead of the lockfile, or the lockfile was updated without re-installing. Lockfile drift can lead to inconsistent environments.

**Suggested Approach**: Run `make update-lock` (which calls `pip-compile`) and then `pip install -e ".[test,dev]" --no-deps` to ensure only locked deps are installed. Add `make verify-install` that checks `pip list --format=columns --exclude-editable` against `requirements.txt` versions. Consider pinning pip-tools version in `requirements-dev.txt`.

---

### B-023 | No pytype or pyright config — mypy is the sole type checker

| Field | Value |
|---|---|
| **Category** | devx |
| **Priority** | medium |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pyproject.toml` |

**Description**: The project only runs `mypy` for type checking (configured in `pyproject.toml`). MyPy is configured with `ignore_missing_imports` which limits its usefulness. 15+ functions still lack type hints, and mypy doesn't catch all type errors that a stricter checker like `pyright` would.

**Suggested Approach**: Add dedicated `mypy.ini` with stricter settings (remove `ignore_missing_imports`, enable `disallow_untyped_defs` in `pi_loop/` gradually). Consider adding `pyright` for an additional pass, or enable `--strict` mode incrementally using per-file-level config. Add a `make types` target.

---

### B-024 | Missing type hints on ~15 functions in config_file.py and friends

| Field | Value |
|---|---|
| **Category** | tech-debt |
| **Priority** | medium |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/config_file.py`, `pi_loop/functions.py`, `pi_loop/cli.py` |

**Description**: Approximately 15 functions across 3 files are missing return type annotations: `ensure_config_dir()`, `load_config()`, `save_config()`, `get()`, `get_bool()`, `apply_to_environ()`, `set_max_output_chars()`, `get_max_output_chars()`, `_dump_env()`, and others. This reduces IDE support quality and makes mypy less effective.

**Suggested Approach**: Add return type annotations to all public and private functions. For `load_config()` return `dict | None`, for `save_config()` return `bool`, for `get()`/`get_bool()` return `Any`/`bool`, for `set_max_output_chars()` return `None`. Run `mypy --strict` on the patched files to verify.

---

### B-025 | Unused dependency: python-dotenv pulled in by uvicorn[standard]

| Field | Value |
|---|---|
| **Category** | dependency |
| **Priority** | medium |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `requirements.txt`, `pyproject.toml` |

**Description**: `python-dotenv` is pulled in as a transitive dependency of `uvicorn[standard]` but is never imported or used by pi-loop code. It adds ~5KB to the install size and one more dependency in the vulnerability surface for zero benefit.

**Suggested Approach**: Either remove the `[standard]` extras from uvicorn and explicitly list the needed extras (`uvloop`, `httptools`, `websockets`), or document that `python-dotenv` is an unused transitive dep. Consider switching to `uvicorn[standard]` and adding a note in `DEPS.md` documenting intentional unused deps.

---

### B-026 | No dotenv/secrets documentation for environment variables

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | medium |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `README.md`, `pi_loop/env_utils.py` |

**Description**: While `env_utils.py` has comprehensive environment variable handling (4-tier resolution, fuzzy typo detection), only `PI_LOOP_API_KEY` and `PI_LOOP_CORS_ORIGINS` are documented in the README. The ~120 known `INFINITE_LOOP_*` env vars are not documented anywhere users can find them.

**Suggested Approach**: Add an "Environment Variables" section to `README.md` documenting all commonly used env vars: `PI_LOOP_API_KEY`, `PI_LOOP_CORS_ORIGINS`, `PI_LOOP_BIND`, `PI_LOOP_PORT`, `NO_COLOR`, `PI_LOOP_CONFIG_DIR`, `PI_LOOP_DATA_DIR`. Cross-reference the CLI flags table. Consider generating env var docs from the KNOWN_ENV_VARS list in `env_utils.py`.

---

### B-027 | No .editorconfig for cross-editor consistency

| Field | Value |
|---|---|
| **Category** | devx |
| **Priority** | medium |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | (new file) |

**Description**: There is no `.editorconfig` file to enforce consistent editor settings (indentation, line endings, charset, trailing whitespace) across different editors and IDEs. While ruff handles formatting, `.editorconfig` catches things at edit time that ruff fixes after-the-fact.

**Suggested Approach**: Create `.editorconfig` with: `root = true`, `[*]` with `charset = utf-8`, `end_of_line = lf`, `insert_final_newline = true`, `trim_trailing_whitespace = true`, `[*.py]` with `indent_style = space`, `indent_size = 4`, `[Makefile]` with `indent_style = tab`.

---

### B-028 | No `pip-tools` or `pre-commit` declared as dev dependencies

| Field | Value |
|---|---|
| **Category** | dependency |
| **Priority** | medium |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pyproject.toml`, `requirements-dev.txt` |

**Description**: `pip-tools` is required for `make update-lock` and `make verify-lock`, and `pre-commit` is required for `make pre-commit` / `make pre-commit-run`. Neither is declared as a dependency in `pyproject.toml` or `requirements-dev.txt`. A new developer running `make install-dev` would get `make update-lock` failures.

**Suggested Approach**: Add `pip-tools>=7.0.0` and `pre-commit>=3.0.0` to the `[project.optional-dependencies] dev` group in `pyproject.toml`. Re-run `pip-compile` to regenerate `requirements-dev.txt` with the new deps.

---

### B-029 | Missing test for critical error recovery escalation path

| Field | Value |
|---|---|
| **Category** | test |
| **Priority** | medium |
| **Impact** | high |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `tests/test_error_recovery.py`, `pi_loop/error_recovery.py` |

**Description**: The error recovery module has 3-level mitigation escalation (mild → moderate → stop) with exponential backoff and success-based ramp-down. However, there is no test that verifies the full escalation chain: a test that feeds consecutive errors of the same type and asserts the correct progression through levels 1→2→3 with appropriate backoff values.

**Suggested Approach**: Add a parametrized test that simulates 5+ consecutive errors of each type (timeout, network, schema, unknown) and asserts: level 1 after first error, level 2 after second, level 3 after third, and correct timeout/cooldown values at each level. Also test success-before-escalation resets to baseline.

---

### B-030 | Missing test for ledger stale-iteration crash recovery

| Field | Value |
|---|---|
| **Category** | test |
| **Priority** | medium |
| **Impact** | high |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `tests/test_state.py`, `pi_loop/state.py:31` |

**Description**: `state.py` has crash recovery logic: if an iteration is pending/stuck and `elapsed >= 300` (5 minutes), it's considered a stale agent crash and recovered. There is no test for this critical recovery path — scenarios where the ledger has a pending iteration older than 300s, or iterations with different statuses that should/shouldn't trigger recovery.

**Suggested Approach**: Add tests that create a ledger with a pending iteration timestamped 301+ seconds ago, call the recovery function, and verify the iteration is marked as failed/abandoned. Test boundary condition (299s should NOT trigger recovery). Test that already-completed iterations are untouched.

---

### B-031 | Missing tests for git_utils auto-commit with edge cases

| Field | Value |
|---|---|
| **Category** | test |
| **Priority** | medium |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `tests/test_git_utils.py`, `pi_loop/git_utils.py` |

**Description**: The git auto-commit logic (`_git_auto_commit`) handles git state capture, diff stat computation, and commit message construction. The existing tests may not cover edge cases: empty diffs (no changes), binary file changes, merge conflicts, large diffs exceeding 10KB cap, non-ASCII file names, `.gitignore`-excluded files appearing in `git add -A`.

**Suggested Approach**: Add parameterized tests covering: empty diff (should skip commit), changes only in `.gitignore`-d files (should not commit), changes exceeding 10KB cap (should truncate diff output), binary file modification (should not crash on encoding), and git repo with no commits yet (initial state).

---

### B-032 | Missing tests for SSE endpoint reconnection and event types

| Field | Value |
|---|---|
| **Category** | test |
| **Priority** | medium |
| **Impact** | medium |
| **Effort** | medium |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `tests/test_server.py`, `web_app/server.py` (SSE endpoints) |

**Description**: The server implements SSE streaming with event types (status, iteration, log, heartbeat, keepalive), exponential backoff reconnection, and broadcast to multiple clients. The existing test suite may not cover: multiple simultaneous SSE connections, client disconnect handling, event ordering, keepalive on idle, and reconnection with `Last-Event-ID`.

**Suggested Approach**: Add tests using httpx's async streaming client or an SSE client library: connect multiple clients, verify each receives the same events, disconnect one client (close stream), verify other clients unaffected, send events and verify correct `event:` and `data:` formatting.

---

### B-033 | Missing performance benchmark tests

| Field | Value |
|---|---|
| **Category** | test |
| **Priority** | medium |
| **Impact** | medium |
| **Effort** | medium |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `tests/` (new benchmark test file) |

**Description**: There are no performance benchmarks in the test suite. Key operations that should have regression-sensitive benchmarks: JSON extraction from large outputs, file lock acquisition under contention, JSON schema validation of large documents, stats recalculation with thousands of iterations, SSE broadcast to multiple clients.

**Suggested Approach**: Create `tests/test_benchmarks.py` with `pytest-benchmark` (add to dev deps if needed) or simple time-based assertions. Target: JSON extraction of 1MB output under 100ms, file lock under 50ms (no contention), schema validation of 1MB document under 500ms. Run in CI as a non-blocking informational job.

---

### B-034 | CSS and JS should be minified for production web UI

| Field | Value |
|---|---|
| **Category** | performance |
| **Priority** | medium |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `web_app/static/style.css`, `web_app/static/app.js` |

**Description**: The web UI static assets serve un-minified CSS (12 KB) and JavaScript (25 KB) as-is. For a production daemon that may be accessed over a network, this adds unnecessary bandwidth. The files lack cache headers and ETags, so they're re-fetched on every page load.

**Suggested Approach**: Add a `make build-web` target that minifies CSS (using `cssnano` or `clean-css`) and JS (using `terser` or `esbuild --minify`). Serve minified files in production mode (`--prod` flag or `PI_LOOP_WEB_PROD=1`). Add `Cache-Control: public, max-age=3600` headers for static assets in production mode.

---

### B-035 | CORS configuration accepts wildcard in production mode

| Field | Value |
|---|---|
| **Category** | security |
| **Priority** | medium |
| **Impact** | high |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `web_app/server.py` (CORS middleware config, ~line 100) |

**Description**: The CORS configuration reads `PI_LOOP_CORS_ORIGINS` from the environment (default `http://localhost:8090`) and splits on comma. The error message warns about wildcard `*` but the implementation still accepts it. A misconfigured deployment could expose the API to any origin.

**Suggested Approach**: Add explicit validation: if `*` is in the origins list, log a warning and reject it in production mode (or require `PI_LOOP_CORS_WILDCARD_ALLOW=1` to override). In production, default to the same origin (`localhost:8090`). Consider supporting regex patterns for subdomain matching.

---

### B-036 | No `@atexit` or context manager cleanup for loop resources

| Field | Value |
|---|---|
| **Category** | tech-debt |
| **Priority** | medium |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/loop.py`, `pi_loop/heartbeat.py`, `web_app/loop_manager.py` |

**Description**: Cleanup relies on `__del__` in `web_app/loop_manager.py` (unreliable in Python — may never be called or may fire during interpreter shutdown in unpredictable order). Heartbeat cleanup and sentinel removal are done in procedural code rather than through guaranteed cleanup paths.

**Suggested Approach**: Register `atexit` handlers for critical cleanup (sentinel file removal, heartbeat file cleanup, subprocess termination). Use `contextlib.suppress` or `try/finally` blocks in main entry points. Replace `__del__` in `loop_manager.py` with explicit `close()` method called via `atexit` and documented as required cleanup.

---

### B-037 | No integration test that runs the full loop end-to-end

| Field | Value |
|---|---|
| **Category** | test |
| **Priority** | medium |
| **Impact** | high |
| **Effort** | large |
| **Dependencies** | B-004 (global state cleanup needed for clean test isolation) |
| **Status** | backlog |
| **Affected Files** | `tests/` (new integration test), `pi_loop/loop.py` |

**Description**: The test suite has excellent unit coverage (481 tests) but no end-to-end integration test that starts the loop, runs a mock worker, checks ledger updates, and verifies convergence detection. The closest is `test_pi_smoke.py` which only checks that the `pi` binary exists on PATH.

**Suggested Approach**: Create `tests/test_integration.py` with a fixture that starts `run_loop()` in a subprocess (or thread with controlled lifecycle). Use a mock goal file that completes in 1-2 iterations. Verify: ledger file is created, iterations increment, stats are computed, convergence is detected, heartbeat file is updated, sentinel file triggers clean shutdown. Mark as `@pytest.mark.slow` (not run by default).

---

### B-038 | Rate limits hardcoded in web_app/server.py

| Field | Value |
|---|---|
| **Category** | tech-debt |
| **Priority** | low |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `web_app/server.py:51` |

**Description**: Rate limits (30 req/min for general, 120 req/min for loop control) are hardcoded constants in `server.py`. They cannot be adjusted without modifying source code.

**Suggested Approach**: Move rate limit configuration to environment variables: `PI_LOOP_RATE_LIMIT_GENERAL` (default 30), `PI_LOOP_RATE_LIMIT_CONTROL` (default 120). Add them to the web UI config panel. Document in README environment variables section.

---

### B-039 | No health check endpoint returns comprehensive system status

| Field | Value |
|---|---|
| **Category** | observability |
| **Priority** | low |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `web_app/server.py` |

**Description**: The `/health` endpoint exists but may not return comprehensive status: loop running state, last iteration age, disk space for ledger, memory usage, uptime, git state. A production deployment needs a richer health check for load balancer/monitoring integration.

**Suggested Approach**: Enhance `/health` to return a JSON response with: `status` (ok/degraded/down), `loop_running` (bool), `last_iteration_seconds_ago` (int or null), `ledger_size_bytes`, `memory_mb`, `uptime_seconds`, `version`. Consider adding a `/ready` endpoint that returns 200 only when the loop is fully initialized. Add response time measurement.

---

### B-040 | Colorize_log_tags applies 20+ regex substitutions per log call

| Field | Value |
|---|---|
| **Category** | performance |
| **Priority** | low |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/file_utils.py:31-62` |

**Description**: Every `_log()` call applies 20+ separate `re.sub()` calls from `_tag_color_map` to the message. For high-frequency log messages (heartbeat ticks, SSE keepalives), this is wasteful CPU spent on terminal coloring.

**Suggested Approach**: Compile all regexes at module load time (pre-compile `_tag_color_map` patterns). Consider a single-pass regex alternation (`pattern1|pattern2|...`) using a combined regex with a replacement function. Skip colorization altogether when output is not a TTY (`not sys.stderr.isatty()`).

---

### B-041 | Magic numbers throughout error handling and recovery

| Field | Value |
|---|---|
| **Category** | tech-debt |
| **Priority** | low |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/error_recovery.py`, `pi_loop/state.py:31`, `pi_loop/functions.py:107` |

**Description**: Multiple magic numbers appear throughout the codebase: `150 // 100` (effectively 1), `min(120, ...)` (max cooldown 120s), `min(1800, base * (2 ** min(count, 10)))` (max backoff 1800s), `if elapsed >= 300` (stale iteration 300s), `max(5, min(120, ...))` (cooldown bounds). These are undocumented and untestable.

**Suggested Approach**: Extract all magic numbers into named constants at the top of each module or in a shared `constants.py`: `MAX_COOLDOWN_SECONDS = 120`, `STALE_ITERATION_THRESHOLD = 300`, `MAX_BACKOFF_SECONDS = 1800`, `MAX_BACKOFF_EXPONENT = 10`. Add docstrings explaining why each value was chosen.

---

### B-042 | No backup/rotation strategy for JSON ledger

| Field | Value |
|---|---|
| **Category** | reliability |
| **Priority** | low |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/state.py`, `pi_loop/config.py` |

**Description**: The JSON ledger is the single source of truth for all iteration data. There is no backup mechanism, no automatic rotation, and no corruption recovery beyond the atomic `.tmp`→rename write. A bug in ledger write logic (or disk full) could silently truncate the file, losing all historical iteration data.

**Suggested Approach**: Implement automatic ledger backup: rename previous ledger to `ledger.json.bak` before writing new one. Keep 3 rotating backups: `ledger.json.0`, `ledger.json.1`, `ledger.json.2`. Add a `--recover-ledger` CLI flag that reads the latest backup if the primary file is corrupt. Add a `max_ledger_size` config option that triggers archiving when exceeded.

---

### B-043 | Split dual backlog files into single source of truth

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | low |
| **Impact** | medium |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | completed |
| **Affected Files** | `BACKLOG.md`, `ENGINEERING_BACKLOG.md` |

**Description**: The repository has two backlog files — `BACKLOG.md` (legacy, 36 KB, 36 items) and `ENGINEERING_BACKLOG.md` (consolidated). Maintaining two backlogs creates confusion about which is authoritative. The ENGINEERING_BACKLOG.md should become the single source of truth.

**Suggested Approach**: ✅ Completed — this file (`ENGINEERING_BACKLOG.md`) is now the consolidated source of truth. `BACKLOG.md` can be deleted or renamed to `BACKLOG_ARCHIVE.md` once the migration is verified.

---

### B-044 | Clean up stale hermes-era git branches and worktrees

| Field | Value |
|---|---|
| **Category** | devx |
| **Priority** | low |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | git branches: `hermes/hermes-bd038f68`, `hermes/hermes-d19eb158`, `hermes/hermes-edaf42c8` |

**Description**: Three stale local branches and `.worktrees/` directories remain from the hermes-agent era. They haven't been touched in ~30+ commits and their content has been carried forward into main. They create confusion during branch listing and waste disk space.

**Suggested Approach**: If the worktree content exists on main: `git branch -d hermes/hermes-*` and `rm -rf .worktrees/`. If not, cherry-pick any useful remaining content (bounded-queue tests, config annotations) to main first, then delete. Add a `make clean-branches` target.

---

### B-045 | Add `make security` target for bandit + safety scanning

| Field | Value |
|---|---|
| **Category** | automation |
| **Priority** | medium |
| **Impact** | high |
| **Effort** | small |
| **Dependencies** | B-008 (depends on adding bandit/safety to deps) |
| **Status** | backlog |
| **Affected Files** | `Makefile` |

**Description**: The Makefile has `install`, `lint`, `test`, `format`, `web`, `clean` targets but no security scanning target. Developers must manually run security tools.

**Suggested Approach**: Add `make security` target that runs: `bandit -r pi_loop web_app -f json -o bandit-report.json` and `safety check -r requirements.txt -r requirements-dev.txt`. Add `make security-ci` that exits non-zero on any findings. Add help text comment above the target.

---

### B-046 | Add automated lockfile freshness check to CI

| Field | Value |
|---|---|
| **Category** | ci-cd |
| **Priority** | medium |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `.github/workflows/ci.yml`, `Makefile` |

**Description**: The CI `lint` job already runs `make verify-lock` (which checks lockfile consistency via pip-compile comparison). This is good practice but should also check that the installed environment matches the lockfile (no drift). Additionally, `verify-lock` should run in the test job, not just lint.

**Suggested Approach**: Add a `verify-install` Makefile target that compares `pip list --format=json` against the versions in `requirements.txt`. Add it to CI's test job. Ensure `make verify-lock` also produces clear output on failure (diff between current and expected requirements).

---

### B-047 | Log tag colorization should be skipped when not a TTY

| Field | Value |
|---|---|
| **Category** | performance |
| **Priority** | low |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `pi_loop/file_utils.py` (daemon logger), `pi_loop/color_utils.py` |

**Description**: ANSI color codes in log output are stripped when writing to files (the log file on disk has ANSI noise), but the 20+ regex substitutions for tag colorization still run even when output is redirected to a file. This wastes CPU on coloring that's immediately discarded.

**Suggested Approach**: Check `sys.stderr.isatty()` (or the configured `NO_COLOR`/`CLI_COLOR` mode) before applying tag colorization regexes. If output is not a TTY or color is disabled, skip all regex substitutions entirely. The `Colorizer` class already has mode support — use it earlier in the log pipeline.

---

### B-048 | Add `completed` status section for tracking resolved items

| Field | Value |
|---|---|
| **Category** | docs |
| **Priority** | low |
| **Impact** | low |
| **Effort** | small |
| **Dependencies** | none |
| **Status** | backlog |
| **Affected Files** | `ENGINEERING_BACKLOG.md` |

**Description**: When backlog items are completed, they should be moved to a `## Completed` section at the bottom of this file with the date and commit hash of completion. Currently there is no way to track what was resolved and when.

**Suggested Approach**: Add a `## Completed` section to this file. When moving an item to completed, append a line like `_Resolved in abc1234 on 2026-06-30_` to the item's description and move it below the `## Completed` header. Keep the original B-ID for traceability.
