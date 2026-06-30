# Engineering Backlog

> **omp-loop** (v14.39.0) — Autonomous task automation daemon  
> **Alias:** hermes-loop  
> Comprehensive engineering backlog covering bugs, tech debt, features, testing, security, performance, documentation, and infrastructure.  
> Generated: 2026-06-30

---

## Table of Contents

- [Project Overview](#project-overview)
- [Current State Assessment](#current-state-assessment)
- [Priority Legend](#priority-legend)
- [Backlog Items](#backlog-items)
  - [🐛 Bugs & Issues](#-bugs--issues)
  - [🔒 Security](#-security)
  - [🏗️ Architecture & Design](#️-architecture--design)
  - [🧪 Testing & Quality](#-testing--quality)
  - [⚡ Performance](#-performance)
  - [🔧 Tooling & Developer Experience](#-tooling--developer-experience)
  - [📚 Documentation](#-documentation)
  - [🔄 CI/CD](#-cicd)
  - [🧹 Code Cleanup & Tech Debt](#-code-cleanup--tech-debt)
  - [✨ Features](#-features)
  - [⬆️ Dependencies & Infrastructure](#️-dependencies--infrastructure)
  - [📊 Observability & Monitoring](#-observability--monitoring)
  - [🤖 Automation](#-automation)
- [Top 10 Prioritized Items](#top-10-prioritized-items)
- [Quick Wins (High Impact, Low Effort)](#quick-wins-high-impact-low-effort)
- [Effort Distribution](#effort-distribution)
- [Dependency Map](#dependency-map)

---

## Project Overview

### What is omp-loop?

**omp-loop** is an autonomous task automation daemon that watches files, iteratively executes goals via the [omp coding agent](https://pi.ai), detects convergence, handles errors with severity-based recovery, and tracks everything in a JSON ledger. It provides both a CLI (`omp-loop`) and a FastAPI-based web dashboard (`omp-loop-web`).

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python ≥3.10 (3.10–3.13 tested, runs on 3.14.5) |
| Build | setuptools ≥64 |
| CLI | argparse (105+ flags, 14 groups) |
| Web Framework | FastAPI + uvicorn + Starlette |
| Frontend | Vanilla HTML/CSS/JS (SPA, dark/light themes) |
| Testing | pytest 9.1.1, pytest-asyncio, pytest-cov, pytest-timeout, httpx2 |
| Linting | ruff (8 rule categories), mypy |
| Security | bandit, safety |
| CI/CD | GitHub Actions (4 parallel jobs) |
| Lockfiles | pip-tools (requirements.txt, requirements-dev.txt) |

### Architecture (3 layers)

```
┌─────────────────┐     ┌──────────────────────────┐     ┌─────────────────┐
│    CLI Layer    │────▶│     Loop Engine          │────▶│    Web UI       │
│  omp_loop/cli.py │     │  omp_loop/loop.py (core)  │     │  web_app/       │
│  omp_loop/parser │     │  omp_loop/functions.py    │     │  server.py      │
│                 │     │  omp_loop/error_recovery  │     │  loop_manager   │
│                 │     │  omp_loop/state.py        │     │  config_manager │
│                 │     │  omp_loop/heartbeat.py    │     │  rate_limiter   │
│                 │     │  omp_loop/git_utils.py    │     └─────────────────┘
│                 │     │  omp_loop/file_utils.py   │
│                 │     │  omp_loop/config.py       │
└─────────────────┘     └──────────────────────────┘
```

### Key Numbers

| Metric | Value |
|--------|-------|
| Source files | 31 (omp_loop: 23, web_app: 6, static: 1) |
| Test files | 28 (pytest) |
| Total tests | 838 |
| Lines of code (est.) | ~8,500 (source) + ~6,000 (tests) |
| Coverage | ~68% overall; **19% on core loop** |
| CLI flags | 105+ across 14 groups |
| Iterations | 213 commits, 2 primary contributors |

---

## Current State Assessment

### What Works Well ✅

| Area | Verdict |
|------|---------|
| **Test suite** | 838 tests, strong isolation with mock/fixtures |
| **Linting** | Ruff — 0 violations across 8 rule categories |
| **Security posture** | API-key auth, rate limiting, CORS, HMAC webhook signing, no hardcoded secrets |
| **Dependency management** | Pinned lockfiles via pip-compile, Dependabot configured |
| **CI/CD** | GitHub Actions: lint + matrix test (4 Python versions) + coverage + security |
| **Code documentation** | Strong inline docstrings, most modules documented |
| **Error recovery** | Severity-based escalation: timeout, network, schema, unknown, heartbeat |
| **Web UI** | FastAPI with SSE live updates, dark/light themes, config editor |
| **Pre-commit** | Both `.pre-commit-config.yaml` and `.githooks/pre-commit` available |
| **Editor consistency** | `.editorconfig` with 120 char lines, spaces, LF endings |

### What Needs Attention 🔴

| Risk | Area | Impact |
|------|------|--------|
| 🔴 | `run_loop()` has **19% test coverage** (435 lines, 60+ locals) | Any change risks regressions; refactoring blocked |
| 🔴 | `loop_manager.py` regex-parses ANSI-colored stdout | Brittle — format changes silently break web UI |
| 🔴 | No end-to-end integration test for `omp` subprocess | Core value prop has zero E2E verification |
| 🟡 | `shell=True` on user-configurable error command | Config compromise → arbitrary command execution |
| 🟡 | `LoopConfig` god dataclass with 71 fields | Monolithic, uses private `dataclasses._MISSING_TYPE` API |
| 🟡 | CLI `main()` only 12% covered | 14+ introspection flags untested |
| 🟡 | JSON extraction brace-depth counting breaks on string-literals | Silent corruption when omp output contains braces in strings |

### Already Completed (from earlier iterations) ✅

1. ✅ Status uptime calculation fix (BUG-013)
2. ✅ HTTP callback URL scheme validation (SEC-001)
3. ✅ Notification failure logging (BUG-002)
4. ✅ Empty catch block logging in app.js (CLEAN-005)
5. ✅ CLI config JSON key validation (BUG-008)
6. ✅ CI coverage reporting (CI-CD-001)
7. ✅ Error classification pattern expansion (BUG-005)
8. ✅ mypy wired as CI gating step (TOOL-001)
9. ✅ HTTP security headers middleware (SEC-003)
10. ✅ Bandit/safety in CI (CI-CD-003)
11. ✅ Stale hermes worktree branches removed (CLEAN-001)
12. ✅ `py.typed` markers added (TOOL-003)
13. ✅ `.editorconfig` added (TOOL-004)
14. ✅ Pre-commit duality documented (TOOL-002)
15. ✅ `OMP_LOOP_API_KEY` read-once at startup (SEC-004)
16. ✅ `shell=True` guardrails for error cmd (SEC-001)

---

## Priority Legend

| Priority | Meaning |
|----------|---------|
| **P0 — Critical** | Data loss, security breach, or blocking failure |
| **P1 — High** | Major feature gap, significant risk, blocks other work |
| **P2 — Medium** | Important but not urgent |
| **P3 — Low** | Nice to have, cosmetic, or speculative |

| Impact | Effort |
|--------|--------|
| **Critical** — System-wide failure | **Small** — <2 hours |
| **High** — Significant degradation | **Medium** — <1 day |
| **Medium** — Moderate inconvenience | **Large** — 2-3 days |
| **Low** — Minor annoyance | **XLarge** — 1+ week |

---

## Backlog Items

---

### 🐛 Bugs & Issues

#### BUG-001 — LoopManager regex-parses ANSI-colored log output instead of consuming structured events

| Field | Value |
|-------|-------|
| **Category** | bug |
| **Priority** | P0 — Critical |
| **Impact** | Critical — Web UI breaks on log format changes |
| **Effort** | Large |
| **Dependencies** | OBS-001 |
| **Status** | In Progress |

- **Description:** `LoopManager._parse_daemon_line()` strips ANSI codes with `_ANSI_ESCAPE.sub("", text)` then applies 6+ fragile regex patterns to extract worker status, duration, error type, heartbeat, and iteration data. Any log format change (timestamp prefix, bracket style, color scheme change) silently breaks all web UI parsers. This is a fundamental architectural flaw — the web UI should consume structured NDJSON events, not reverse-engineer human-readable log strings.
- **Reasoning:** A single log format change by the daemon team (or a omp binary output format change) would completely disable the web UI's live monitoring. The current approach is a leaky abstraction that couples the web layer to display formatting.
- **Suggested Approach:** Phase 1: Write characterization tests capturing current regex behavior with representative log lines. Phase 2: Implement structured event emission from the daemon (OBS-001). Phase 3: Migrate `LoopManager` to consume structured events, keeping regex parsing as fallback.
- **Affected Files:** `web_app/loop_manager.py` (`_parse_daemon_line`, `_ANSI_ESCAPE`, `_parse_daemon_stdout`)

---

#### BUG-002 — JSON extraction breaks on string-literals containing braces

| Field | Value |
|-------|-------|
| **Category** | bug |
| **Priority** | P1 — High |
| **Impact** | High — Silent data corruption |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `extract_json_from_output()` in `file_utils.py` uses simple brace-depth counting (`{` = +1, `}` = -1) with no awareness of JSON string literals. If omp output contains `{` or `}` inside a quoted JSON string (e.g., `"output": "if (x) { y }"`), the brace counter desyncs and extraction returns a partial or corrupted JSON object. Both forward and reverse scan strategies are affected.
- **Reasoning:** This is the critical data path — every omp subprocess output goes through this function. A single malformed extraction corrupts the iteration ledger entry. Since omp outputs frequently contain code with braces, this is a realistic failure mode.
- **Suggested Approach:** Add string-literal awareness during brace scanning: skip counting braces inside quoted strings (respecting escape sequences like `\"`). Replace the O(n²) `list.insert(0, ch)` reverse scan with a single forward pass using a stack-based approach. Add comprehensive test cases.
- **Affected Files:** `omp_loop/file_utils.py:extract_json_from_output()`, `tests/test_file_utils.py`

---

#### BUG-003 — Zsh completion generation excludes all long flags

| Field | Value |
|-------|-------|
| **Category** | bug |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `_generate_completion()` in `cli.py` filters flags with `if not f.startswith("--")` when building `_zsh_flags`. This discards all long flags (e.g., `--goal`, `--max-iterations`, `--workers`), producing completions with only short flags (`-g`, `-m`). Auto-generated zsh completions are missing ~80% of available flags.
- **Reasoning:** Zsh users relying on tab completion get no help for the most commonly used flags. Developers adding new flags must remember to update completions, but the broken filter means no long flag would ever appear regardless.
- **Suggested Approach:** Fix the filter condition to exclude only help flags (`--help`, `-h`) instead of all `--` flags. Add a test case for completion output verification.
- **Affected Files:** `omp_loop/cli.py` (`_generate_completion`, ~line 119)

---

#### BUG-004 — Heartbeat poll interval causes up-to-5s shutdown detection delay

| Field | Value |
|-------|-------|
| **Category** | bug |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `_monitor_heartbeat()` sleeps for `HEARTBEAT_POLL_INTERVAL` (5 seconds) between heartbeat checks. Any iteration completion is detected up to 5 seconds late because the poll cycle must complete before the next heartbeat check. For short iterations (<2s), this doubles the latency.
- **Reasoning:** Users running the daemon with short goals experience noticeable lag between iteration completion and the next iteration starting. This is especially problematic for interactive or demo usage where responsiveness matters.
- **Suggested Approach:** Use `threading.Event.wait(timeout=interval)` with a set-able event for shutdown notification, reducing effective latency to near-zero while maintaining the poll interval.
- **Affected Files:** `omp_loop/heartbeat.py` (`_monitor_heartbeat`, ~line 67)

---

#### BUG-005 — FileLock busy-waits with fixed 100ms sleep under contention

| Field | Value |
|-------|-------|
| **Category** | bug |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `FileLock.__enter__` busy-waits for a lock with `time.sleep(0.1)` — a fixed 100ms interval until the timeout expires. Under contention (multi-worker), this creates unnecessary CPU wakeups. No exponential backoff, no jitter.
- **Reasoning:** With `--workers N` (N > 1), multiple processes contend for the ledger lock. Fixed 100ms sleep means every retry cycle has deterministic collisions. This directly impacts parallel execution efficiency.
- **Suggested Approach:** Implement exponential backoff starting at 10ms, doubling per retry, with ±20% random jitter, capped at ~1s max interval.
- **Affected Files:** `omp_loop/file_utils.py` (`FileLock.__enter__`, lines ~39-48)

---

#### BUG-006 — Config write failures silently discarded

| Field | Value |
|-------|-------|
| **Category** | bug |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `config_file.py:save_config()` catches `OSError: pass` — any filesystem error during config write is discarded with no log, no warning, no user feedback. If `~/.config/omp-loop/` doesn't exist or is read-only, the user's config changes silently disappear.
- **Reasoning:** Users who modify config via the web UI or CLI and see "saved" but whose changes are silently ignored will experience confusing behavior. Config writes are infrequent enough that logging is zero-cost.
- **Suggested Approach:** Log at WARNING level with the error detail before `pass`. Add atomic write pattern (write to `.tmp` then `os.rename`).
- **Affected Files:** `omp_loop/config_file.py` (`save_config`, line 49)

---

#### BUG-007 — loop_manager.py log file handle never rotates

| Field | Value |
|-------|-------|
| **Category** | bug |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `LoopManager._add_log()` opens a log file handle on startup and appends forever. There is no rotation, no size cap, no truncation. On a long-running server, this produces unbounded disk growth. The daemon-side `RotatingFileHandler` mitigates this for the daemon's own logs, but the web app's captured output has no protection.
- **Reasoning:** A web server running for days with active daemon output could fill the disk. Since the web UI logs all daemon stdout/stderr, this is a material risk for production deployments.
- **Suggested Approach:** Add file size check before appending (rotate at 100MB). Use `RotatingFileHandler` from stdlib with `maxBytes=100MB, backupCount=3`.
- **Affected Files:** `web_app/loop_manager.py` (`_add_log`, `_close_log`)

---

#### BUG-008 — CLI help completions have Python < 3.12 legacy workaround

| Field | Value |
|-------|-------|
| **Category** | bug |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | BUG-003 |
| **Status** | Pending |

- **Description:** `_generate_completion()` has a Python < 3.12 workaround (`_zsh_sep = chr(92) + chr(10) + "        "`) for f-string backslash limitations. Given Python 3.10+ requirement, this legacy hack is inscrutable. Minimum Python is 3.10 but this workaround is only needed below 3.12.
- **Reasoning:** This is dead code for the 3.12+ use case and confusing for anyone reading the function. Fix it when fixing the long-flag exclusion bug (BUG-003).
- **Suggested Approach:** Replace with f-string `\n` directly (requires Python 3.12+). Bundle with BUG-003 fix.
- **Affected Files:** `omp_loop/cli.py` (`_generate_completion`)

---

#### BUG-009 — Docstring placed after `if` block in preflight.py

| Field | Value |
|-------|-------|
| **Category** | bug |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** In `preflight.py`, `check_disk_space()` has its docstring positioned after the function body's first `if` block instead of at the top of the method. This makes the docstring invisible to `help()` and IDE tooltips.
- **Reasoning:** Minor issue but breaks tooltip-based documentation for one of the preflight check methods.
- **Suggested Approach:** Move the docstring to the first line of the method body.
- **Affected Files:** `omp_loop/preflight.py` (`check_disk_space`, ~line 100)

---

### 🔒 Security

#### SEC-001 — `shell=True` on user-configurable error command (Bandit B602)

| Field | Value |
|-------|-------|
| **Category** | security |
| **Priority** | P1 — High |
| **Impact** | High — Config compromise → arbitrary code execution |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | ✅ Completed (2026-06-30) |

- **Description:** `loop.py` runs `subprocess.run(on_error_cmd, shell=True, timeout=30)` where `on_error_cmd` is user-configurable via `config.json` or `--on-error-cmd` flag. If an attacker gains write access to `~/.config/omp-loop/config.json`, they can execute arbitrary shell commands. This is an intentional feature but has insufficient guardrails.
- **Reasoning:** The bandit scan flagged this as HIGH severity. While it's intentional, missing guardrails (no command validation, no character restrictions, no length limit, no audit logging) make it a viable attack vector. This is the #1 security risk in the project.
- **Suggested Approach:** (1) Log the full command before execution at INFO level for audit trail. (2) Validate command length (reject >500 chars) and reject shell metacharacters (`;`, `|`, `` ` ``, `$()`) unless explicitly needed. (3) Add a startup WARNING log when `on_error_cmd` is configured. (4) Document the risk explicitly in README security section.
- **Resolution:** Added `_validate_on_error_cmd()` with length check (500 char limit), shell metacharacter rejection, and metacharacter bypass flag (`--allow-error-metachars`). Added startup WARNING log. Updated README with security implications documentation.
- **Affected Files:** `omp_loop/loop.py` (line 727), `README.md`

---

#### SEC-002 — No `.env` in `.gitignore` (currently commented out)

| Field | Value |
|-------|-------|
| **Category** | security |
| **Priority** | P2 — Medium |
| **Impact** | Medium — Accidental secret exposure |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `.gitignore` has `.env` commented out with the note `# config_file used instead`. While the project does use JSON config files, if a developer creates a `.env` file locally with secrets (API keys, callback secrets), those secrets would be committed to git. This is defense-in-depth — the cost is zero.
- **Reasoning:** The project uses `OMP_LOOP_API_KEY` for web auth. A developer testing the web UI might create a `.env` for convenience and accidentally commit it. The `.env` gitignore entry is standard practice in the Python ecosystem.
- **Suggested Approach:** Uncomment `.env` and add `.env.*` (covers `.env.local`, `.env.production`). Add a comment explaining this is a safety net even though `.env` is not the primary config mechanism.
- **Affected Files:** `.gitignore`

---

#### SEC-003 — No secrets scanner in CI

| Field | Value |
|-------|-------|
| **Category** | security |
| **Priority** | P2 — Medium |
| **Impact** | Medium — Regression risk for secret exposure |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The CI pipeline has no secrets scanning. A developer could accidentally commit an API key, token, or password, and it would pass CI without detection. While no secrets are currently in the repo (verified), this is a regression risk.
- **Reasoning:** GitHub has push protection for some patterns, but a dedicated secrets scanner provides defense-in-depth and catches non-GitHub patterns.
- **Suggested Approach:** Add `detect-secrets` as a pre-commit hook and CI step. Alternatively, use `truffleHog` in CI with a `--since` flag to only scan new commits.
- **Affected Files:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`

---

#### SEC-004 — FastAPI web server allows CORS from any origin

| Field | Value |
|-------|-------|
| **Category** | security |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The FastAPI server adds `CORSMiddleware` with `allow_origins=["*"]`. While the server defaults to localhost-only binding, if a user configures `--host 0.0.0.0`, any website can make API requests to the daemon (though API-key auth mitigates this partially).
- **Reasoning:** With API-key auth enabled, this is mitigated. But if auth is disabled (no `OMP_LOOP_API_KEY` set), any website could control the daemon via the exposed API across origins. The CORS permissiveness is the only layer of defense for an unauthenticated setup.
- **Suggested Approach:** Restrict CORS to the origin the server is running on (or localhost). When `--host 0.0.0.0` is used, require explicit `--cors-origins` flag with a comma-separated list. Keep `*` only as fallback for localhost-only mode.
- **Affected Files:** `web_app/server.py` (CORS middleware config)

---

#### SEC-005 — No explicit bounds on sentinel file size

| Field | Value |
|-------|-------|
| **Category** | security |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `file_utils.py:check_sentinel()` reads the full contents of the sentinel file into memory with `f.read()`. An attacker who can write to `/tmp/` could create a very large sentinel file, causing the daemon to allocate excessive memory.
- **Reasoning:** Low risk because sentinel file write requires local access. But this is a simple hardening opportunity — bound the read to a reasonable size.
- **Suggested Approach:** Read only the first 1KB of the sentinel file. Use `f.read(1024)` instead of `f.read()`.
- **Affected Files:** `omp_loop/file_utils.py` (`check_sentinel`, `check_sentinel_no_remove`)

---

### 🏗️ Architecture & Design

#### ARCH-001 — Decompose monolithic `run_loop()` function

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | P0 — Critical |
| **Impact** | Critical — Largest barrier to all loop improvements |
| **Effort** | XLarge |
| **Dependencies** | None (Phase 1 is independent) |
| **Status** | Pending |

- **Description:** `run_loop()` in `loop.py` (~435 lines) handles: subprocess spawning, iteration lifecycle, error classification, recovery adaptation, notification dispatch (desktop, HTTP callback, ntfy), dashboard HTML generation, goal evolution, convergence detection, cooldown handling, heartbeat management, ledger pruning, and git auto-commit. It has 60+ local variables and 20+ condition branches. The `# ruff: noqa: ARG001, F841` at the top acknowledges unused local assignments. Test coverage is ~19% because mocking 60+ variables is impractical.
- **Reasoning:** Every new feature touches `run_loop()`, increasing its complexity and regression risk. It cannot be meaningfully tested as-is. Decomposition is the prerequisite for: integration tests (TEST-002), state machine (ARCH-002), structured logging (OBS-001), and confident iteration on any loop behavior.
- **Suggested Approach:** Phase 1: Write characterization tests for current behavior. Extract pure functions: convergence check, termination check, progress classification. Extract I/O-bound operations: `_emit_notifications()`, `_apply_recovery()`, `_build_dashboard_html()`. Each extraction is a separate commit with passing tests. Phase 2: Create `IterationContext` dataclass, `TaskExecutor` class, `CooldownManager` class. Phase 3: Refactor main loop body into a readable pipeline.
- **Affected Files:** `omp_loop/loop.py`, new `omp_loop/executor.py`, new `omp_loop/convergence.py`

---

#### ARCH-002 — Loop lacks explicit state machine abstraction

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | P1 — High |
| **Impact** | High |
| **Effort** | Large |
| **Dependencies** | ARCH-001 |
| **Status** | Pending |

- **Description:** The main loop is a `while True` with ad-hoc condition checks for shutdown, pause, cooldown, etc. States (running, paused, cooldown, error, stopping) are managed via scattered boolean flags and sentinel file checks. There's no single source of truth for current state, making it hard to add new states (draining, backoff, maintenance).
- **Reasoning:** Adding features like "graceful shutdown on worker drain" or "maintenance mode" requires threading new booleans through the entire loop. A state machine makes transitions explicit, testable, and prevents illegal state transitions.
- **Suggested Approach:** Introduce a `LoopStateMachine` class with explicit enum states and defined transitions. Each state has `enter()` and `exit()` hooks. Replace scattered `if` checks with `state_machine.transition_to()` calls.
- **Affected Files:** `omp_loop/loop.py`, new `omp_loop/state_machine.py`

---

#### ARCH-003 — `LoopConfig` god dataclass with 71 fields

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | P1 — High |
| **Impact** | High |
| **Effort** | Large |
| **Dependencies** | ARCH-001 |
| **Status** | Pending |

- **Description:** `LoopConfig` is a single dataclass spanning iteration control, worker config, git settings, notifications, archiving, logging, safety, and advanced options. It violates the Single Responsibility Principle. `from_args()` imports `dataclasses._MISSING_TYPE` — a private API. When a field is added, all consumers must be checked for compatibility.
- **Reasoning:** The use of private API (`dataclasses._MISSING_TYPE`) means it can break on any Python version update. Adding a new config option requires touching the dataclass, the parser, and potentially multiple consumers. This is a maintenance bottleneck.
- **Suggested Approach:** Split into focused configs: `IterationConfig`, `WorkerConfig`, `GitConfig`, `NotificationConfig`, `ArchiveConfig`, `SafetyConfig`. Compose in a top-level `AppConfig`. Keep backward compatibility via `__getattr__` delegation to child configs.
- **Affected Files:** `omp_loop/config.py` (LoopConfig dataclass, lines ~68-179), `omp_loop/loop.py`, `omp_loop/cli.py`

---

#### ARCH-004 — `/proc` dependency makes the daemon Linux-only

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | P2 — Medium |
| **Impact** | Medium — Blocks macOS/BSD support |
| **Effort** | Large |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `system_utils.py` reads `/proc/[pid]/status` and `/proc/[pid]/stat` for CPU/memory tracking. `server.py` reads `/proc/stat` and `/proc/meminfo`. `status.py` uses `os.sysconf_names["SC_CLK_TCK"]`. All of these are Linux-specific. The daemon cannot run on macOS or BSD without errors.
- **Reasoning:** The project's README and `pyproject.toml` don't mention Linux as a requirement. macOS is a common development platform. This silently fails with cryptic errors on non-Linux systems.
- **Suggested Approach:** Abstract a `SystemResourceProvider` interface with `LinuxProvider` (current), `macOSProvider` (using `sysctl`/`ps`), and `NoopProvider` (returns defaults). Auto-detect platform at import time. Mark platform-specific tests with `@pytest.mark.skipif` for non-Linux.
- **Affected Files:** `omp_loop/system_utils.py`, `omp_loop/status.py`, `web_app/server.py`

---

#### ARCH-005 — `config_file.py` uses module-level mutable state

| Field | Value |
|-------|-------|
| **Category** | architecture |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `config_file.py` caches loaded config in a module-level `_config: dict[str, str] = {}` variable. Functions `get()`, `get_bool()`, `load_config()` all mutate and read this global. This is not thread-safe and makes testing fragile (tests must carefully reset state).
- **Reasoning:** Module-level mutable state is a well-known antipattern. Tests in `test_config_file.py` already work around it. With the web UI's async nature, concurrent access to cached config could cause race conditions.
- **Suggested Approach:** Replace with a `ConfigStore` class that holds the config dict and provides the same API. Create a module-level singleton for backward compatibility, but allow tests and the web UI to create isolated instances.
- **Affected Files:** `omp_loop/config_file.py`

---

### 🧪 Testing & Quality

#### TEST-001 — Zero end-to-end integration tests for omp subprocess lifecycle

| Field | Value |
|-------|-------|
| **Category** | testing |
| **Priority** | P0 — Critical |
| **Impact** | Critical — Core value prop has zero E2E verification |
| **Effort** | Large |
| **Dependencies** | None (can use `mock_pi.sh` which already exists) |
| **Status** | Pending |

- **Description:** The core value proposition (subprocess task execution via `omp`) has zero end-to-end verification. All 838 tests are unit tests that mock subprocess calls. A `omp` binary change (flag rename, output format change, `mode=json` breaking change) goes undetected until production. Only `test_omp_smoke.py` checks that `omp` is on PATH — nothing tests actual output parsing.
- **Reasoning:** This is the #1 testing gap. The entire daemon exists to manage omp subprocesses, but there is no test that actually runs the end-to-end flow. A mock omp binary (`tests/integration/mock_omp.sh`) exists but is only used by deep integration tests, not by `test_loop.py` or `test_integration.py`.
- **Suggested Approach:** Expand `mock_omp.sh` to emit realistic NDJSON output with configurable delay/errors. Create dedicated integration tests: single iteration success, convergence detection, error recovery with injected failures, sentinel stop/pause, multi-worker patterns. Mark with `@pytest.mark.integration`. Run as a separate CI job.
- **Affected Files:** `tests/integration/mock_omp.sh`, new `tests/integration/test_subprocess_lifecycle.py`, `.github/workflows/ci.yml`

---

#### TEST-002 — Core loop (`run_loop`) only 19% covered

| Field | Value |
|-------|-------|
| **Category** | testing |
| **Priority** | P1 — High |
| **Impact** | High |
| **Effort** | Large |
| **Dependencies** | ARCH-001 (easier after decomposition, but can start now) |
| **Status** | Pending |

- **Description:** Only `_execute_task`, `_evolve_goal`, `_build_dashboard_html`, and `_request_shutdown` are tested. The main `run_loop()` function (435 lines), sentinel polling, worker management, convergence detection, checkpointing, and cooldown enforcement are untested. Any refactoring of the core loop risks undetected regressions.
- **Reasoning:** This is the most critical code path in the entire application with the lowest coverage. The function is too large to mock effectively, creating a vicious cycle: low coverage prevents refactoring, and the monolithic function prevents adding coverage.
- **Suggested Approach:** Start with exit-early conditions (sentinel file → clean shutdown, max iterations → stop, convergence → settle). Test iteration lifecycle with mocked `_execute_task`. Write characterization tests before refactoring (capture current behavior, then refactor against captured behavior).
- **Affected Files:** `omp_loop/loop.py`, `tests/test_loop.py`

---

#### TEST-003 — CLI `main()` entry point only 12% covered

| Field | Value |
|-------|-------|
| **Category** | testing |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** Only `_create_parser()` is tested in `test_cli.py`. The `main()` function (~200 lines with 14+ introspection flags, config loading, daemon dispatch) is untested. Command dispatch, help topic rendering, doctor output, healthcheck formatting, status display — all have no test coverage.
- **Reasoning:** The CLI is the primary user interface. Broken introspection flags (`--status`, `--doctor`, `--preflight`) don't crash but produce confusing output. These are the first things a user tries when diagnosing issues.
- **Suggested Approach:** Refactor `main()` to accept an argument list for easier testing. Test each introspection flag independently. Test config file loading with valid/invalid/missing files. Use `capsys` fixture to capture stdout.
- **Affected Files:** `omp_loop/cli.py`, `tests/test_cli.py`

---

#### TEST-004 — `file_watcher.py` has zero test coverage

| Field | Value |
|-------|-------|
| **Category** | testing |
| **Priority** | P1 — High |
| **Impact** | High |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `FileWatcherTrigger` class with 5 methods and polling logic has no dedicated test file. The file watching functionality (polling directory changes, triggering iterations) is entirely untested. With 0% coverage, any regression in file watching goes undetected.
- **Reasoning:** File watching is a core feature (the daemon "watches files"). A regression here means the daemon stops reacting to file changes without any test catching it. The class is small and well-encapsulated — easy to test.
- **Suggested Approach:** Create `tests/test_file_watcher.py`. Use `tmp_path` fixtures to create temporary directory structures. Test: directory creation/deletion triggers, file modification detection, polling interval behavior, edge cases (empty directory, permission errors).
- **Affected Files:** `omp_loop/file_watcher.py`, new `tests/test_file_watcher.py`

---

#### TEST-005 — `server.py` needs coverage for SSE, error handlers, remaining API routes

| Field | Value |
|-------|-------|
| **Category** | testing |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `web_app/server.py` has only 55% coverage. Auth middleware and rate limiting are well-tested, but SSE streaming, config CRUD endpoints, system monitoring endpoints, CORS handling, and error handlers have limited or no test coverage.
- **Reasoning:** SSE is the primary means of live updates in the dashboard. A regression here means the dashboard appears frozen. Config CRUD errors silently corrupt user settings. These are high-value targets for additional coverage.
- **Suggested Approach:** Use `TestClient` from Starlette to test each API route with valid/auth/invalid requests. Test SSE stream initialization and heartbeat events. Test CORS header presence. Test 404/405/500 error handlers.
- **Affected Files:** `web_app/server.py`, `tests/test_server.py`

---

#### TEST-006 — `rate_limiter.py` needs dedicated unit tests

| Field | Value |
|-------|-------|
| **Category** | testing |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `SlidingWindowRateLimiter` (4 async methods) is only tested indirectly through `test_server.py`. There are no direct unit tests for: rate limit check logic, time window rolling, remaining count calculation, reset behavior, concurrent access under `asyncio.Lock`.
- **Reasoning:** The rate limiter is simple and well-encapsulated — it should have dedicated tests. Indirect coverage through server tests may miss edge cases.
- **Suggested Approach:** Create `tests/test_rate_limiter.py` with `pytest-asyncio` tests. Test: single IP stays under limit, burst exceeds limit, window rolls correctly, multiple IPs tracked independently.
- **Affected Files:** `web_app/rate_limiter.py`, new `tests/test_rate_limiter.py`

---

#### TEST-007 — Integration tests are overgrown (4 files, 252KB total)

| Field | Value |
|-------|-------|
| **Category** | testing |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The 4 integration test files (`test_integration.py` [95KB], `test_integration_gaps.py` [63KB], `test_integration_remaining.py` [53KB], `test_integration_deep.py` [41KB]) account for ~252KB of test code. They are large, unstructured, and mix concerns. Finding a specific test requires scrolling through hundreds of lines.
- **Reasoning:** Large test files discourage maintenance. New contributors add tests to the end rather than organizing them. The integration tests should be split into focused, single-concern files matching the module structure.
- **Suggested Approach:** Split each integration file into topic-specific files: `test_integration_lifecycle.py`, `test_integration_error_recovery.py`, `test_integration_cli.py`, `test_integration_web.py`, `test_integration_ledger.py`. Each file under 500 lines. Add a test runner configuration to keep CI unchanged.
- **Affected Files:** `tests/test_integration.py`, `tests/test_integration_gaps.py`, `tests/test_integration_remaining.py`, `tests/test_integration_deep.py`

---

### ⚡ Performance

#### PERF-001 — Dashboard HTML rebuilt from scratch every iteration

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `_build_dashboard_html()` reconstructs the entire 50-iteration HTML table every iteration, including serializing all iteration records to HTML strings. Fine for current scale (<100 iterations), but O(n) in iterations and O(n²) in total data processed across all calls. For long-running daemons with thousands of iterations, this becomes a noticeable lag on each iteration cycle.
- **Reasoning:** As the daemon runs for hours or days, each iteration gets slower as the iteration history grows. The 50-iteration hard cap mitigates this somewhat, but rebuilding even 50 rows per iteration is wasteful.
- **Suggested Approach:** Implement incremental rendering: only append new rows instead of rebuilding. Consider switching to client-side rendering (web API provides JSON, JS renders the table). Cap the total rows to a configurable limit.
- **Affected Files:** `omp_loop/loop.py` (`_build_dashboard_html`)

---

#### PERF-002 — FileWatcher uses full recursive directory scan

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `FileWatcherTrigger.check_change()` calls `sorted(p.rglob("*"))` which scans the entire directory tree and sorts all entries — O(n log n) where n = number of files. For large source trees (e.g., a monorepo with node_modules), this is prohibitively slow on every poll interval.
- **Reasoning:** Users watching large directories will experience significant poll latency. The `rglob` also picks up irrelevant files (`.git`, `node_modules`, `__pycache__`), wasting cycles.
- **Suggested Approach:** Filter `rglob` to relevant file patterns (`.py`, `.md`, `.yaml`, `.json`). Use `os.stat` mtime comparison instead of full content hashing. Consider adding `watchdog` as optional dependency for OS-level file system notifications.
- **Affected Files:** `omp_loop/file_watcher.py`

---

#### PERF-003 — SSE poller runs unconditionally every 2 seconds

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `_status_poller()` reads the entire JSON ledger from disk every 2 seconds and broadcasts to all SSE clients. This creates unnecessary I/O even when nothing has changed. With 0 connected SSE clients, the poller continues reading the ledger and generating events.
- **Reasoning:** For an idle daemon with no dashboard users, the poller creates an unnecessary disk read every 2 seconds. This is wasteful and increases disk wear.
- **Suggested Approach:** Check ledger file mtime before reading — skip if unchanged since last read. Skip the entire poll cycle when `_sse_clients` is empty. Make poll interval configurable.
- **Affected Files:** `web_app/server.py` (`_status_poller`, ~line 225)

---

#### PERF-004 — JSON extraction does two full scans of output text

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | BUG-002 |
| **Status** | Pending |

- **Description:** `extract_json_from_output()` first attempts a reverse scan (building `json_chars` with repeated list `insert(0, ch)` — O(n²) due to left-insert). If that fails, it falls back to a forward scan. For large outputs with no JSON, every character is processed twice with O(n²) insert in the first pass.
- **Reasoning:** This is a correctness bug (BUG-002) first, performance issue second. Fix the correctness first, then optimize.
- **Suggested Approach:** Use a single forward pass with stack-based brace tracking (instead of counter + `insert(0, ch)`). Fix the string-literal awareness bug at the same time. Eliminate the reverse-scan fallback.
- **Affected Files:** `omp_loop/file_utils.py:extract_json_from_output()`

---

#### PERF-005 — Log tag colorization applies 20+ regex substitutions per call

| Field | Value |
|-------|-------|
| **Category** | performance |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `_colorize_log_tags()` iterates over 20+ regex patterns and applies `re.sub()` for each one on every log message. For high-frequency log messages, this is wasteful — most patterns don't match but still incur regex compilation and matching overhead.
- **Reasoning:** Minor optimization. Colorization is a display concern that shouldn't be a performance bottleneck.
- **Suggested Approach:** Pre-compile all regex patterns at module load time. Use a single-pass scanner instead of sequential substitutions. Skip colorization when output is not a TTY.
- **Affected Files:** `omp_loop/file_utils.py` (`_colorize_log_tags`

---

### 🔧 Tooling & Developer Experience

#### DEVX-001 — Pre-commit duality: `.pre-commit-config.yaml` vs `.githooks/pre-commit`

| Field | Value |
|-------|-------|
| **Category** | devx |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** There are two independent pre-commit systems: `.pre-commit-config.yaml` (used by `pre-commit` tool, runs ruff + file checks) and `.githooks/pre-commit` (bash script, also runs ruff check+format on staged files). The `.githooks/README.md` describes a different hook (shell completion regeneration) than what the script actually does (ruff linting). Contributors get inconsistent behavior depending on which system they activate.
- **Reasoning:** New contributors are confused about which system to use. The two systems produce different results for the same commit. This is a workflow documentation and tooling consistency issue.
- **Suggested Approach:** Pick one system and remove the other. Recommended: use `pre-commit` tool exclusively (more maintainable, community standard, supports more hooks). Delete `.githooks/pre-commit` and update `CONTRIBUTING.md` with installation instructions.
- **Affected Files:** `.pre-commit-config.yaml`, `.githooks/pre-commit`, `.githooks/README.md`, `CONTRIBUTING.md`

---

#### DEVX-002 — Coverage settings not centralized in `pyproject.toml`

| Field | Value |
|-------|-------|
| **Category** | devx |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** Coverage settings are partially in `pyproject.toml` but `[tool.coverage.run]` and `[tool.coverage.report]` sections should be fully defined there for consistent behavior across local runs and CI.
- **Reasoning:** Currently, `make test` explicitly passes `--cov=omp_loop --cov=web_app` flags. Centralizing in `pyproject.toml` ensures consistent coverage behavior regardless of how tests are invoked.
- **Suggested Approach:** Add full `[tool.coverage.run]` section with source, omit, and concurrency settings. Add `[tool.coverage.report]` with fail_under, exclude_lines, and precision. Remove redundant CLI flags from Makefile.
- **Affected Files:** `pyproject.toml`, `Makefile`

---

#### DEVX-003 — Safety CLI uses deprecated `check` command

| Field | Value |
|-------|-------|
| **Category** | devx |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `make security` uses `safety check -r requirements.txt -r requirements-dev.txt --continue-on-error`. The `check` command is deprecated in Safety 3.x; the recommended replacement is `safety scan`.
- **Reasoning:** The deprecated command still works for now but may be removed in a future Safety release, breaking the `make security` target and CI.
- **Suggested Approach:** Migrate to `safety scan --continue-on-error --file requirements.txt --file requirements-dev.txt`. Update Makefile and CI.
- **Affected Files:** `Makefile` (security target)

---

#### DEVX-004 — No `make check` target for full pre-commit validation

| Field | Value |
|-------|-------|
| **Category** | devx |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The Makefile has separate `lint`, `format`, `test`, `security` targets but no single `make check` target that runs the full validation suite (lint + type-check + test + security). Contributors must remember to run multiple commands.
- **Reasoning:** A single `make check` command that developers run before pushing ensures nothing is missed. Reduces CI failures due to forgotten validation steps.
- **Suggested Approach:** Add `make check` target that runs: lint → mypy → test → security in sequence. Add a pre-push git hook that runs `make check` (optional, opt-in).
- **Affected Files:** `Makefile`, `CONTRIBUTING.md`

---

### 📚 Documentation

#### DOC-001 — README missing Swagger UI link, screenshot, and omp version requirement

| Field | Value |
|-------|-------|
| **Category** | docs |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** README lacks: (1) link to auto-generated FastAPI `/docs` OpenAPI endpoint, (2) screenshot or preview of the web UI dashboard, (3) minimum required `omp` coding agent version, (4) note that `omp` must be on PATH. These are the first things a new user looks for.
- **Reasoning:** First impressions matter. A screenshot immediately communicates the web UI's capabilities. Missing requirement info causes confusing errors for new users who haven't installed `omp`.
- **Suggested Approach:** Add a "Prerequisites" section with `omp` version requirement and PATH note. Add a link to `/docs` after the web UI features section. Add a screenshot of the dashboard.
- **Affected Files:** `README.md`

---

#### DOC-002 — No CONTRIBUTING.md with development setup guide

| Field | Value |
|-------|-------|
| **Category** | docs |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** There is no CONTRIBUTING.md. A new contributor has no guidance on: development setup, branch strategy, PR workflow, commit message conventions, coding standards, how to run tests, how to debug failures, or where to ask questions. The project has good tooling (pre-commit, Makefile, ruff, mypy) but none of it is documented for contributors.
- **Reasoning:** The project has received contributions from multiple agents. Without contribution guidelines, contributions are inconsistent in style, commit messages, and testing practices.
- **Suggested Approach:** Create CONTRIBUTING.md with sections: Development Setup, Project Structure, Running Tests, Coding Standards, Commit Convention (Conventional Commits), PR Workflow, Issue Templates. Reference existing Makefile targets.
- **Affected Files:** new `CONTRIBUTING.md`

---

#### DOC-003 — No SECURITY.md for vulnerability disclosure

| Field | Value |
|-------|-------|
| **Category** | docs |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The project has security features (API-key auth, rate limiting, CORS, HMAC webhook signing) but no SECURITY.md. Security researchers or users who find vulnerabilities have no guidance on how to report them responsibly.
- **Reasoning:** Without a reporting channel, vulnerabilities may be disclosed publicly before a fix is available. This is a standard practice for any project with security-sensitive features.
- **Suggested Approach:** Create SECURITY.md with: supported versions, reporting process (email or GitHub advisory), expected response timeline, and PGP key if applicable.
- **Affected Files:** new `SECURITY.md`

---

#### DOC-004 — No inline docstring for `set_max_output_chars`/`get_max_output_chars`

| Field | Value |
|-------|-------|
| **Category** | docs |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `functions.py` has two module-level functions (`set_max_output_chars`, `get_max_output_chars`) with zero docstrings. These manage mutable global state — exactly the kind of code that needs clear documentation about side effects.
- **Reasoning:** Minor gap. These functions manage global state and should explain why they exist and what happens when the limit is exceeded.
- **Suggested Approach:** Add docstrings explaining what they do, what the default value is, and that they modify module-level global state (and why).
- **Affected Files:** `omp_loop/functions.py` (lines ~18, ~22)

---

#### DOC-005 — No architecture decision records (ADRs)

| Field | Value |
|-------|-------|
| **Category** | docs |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** There are no architecture decision records. Key decisions (why `LoopConfig` is a single dataclass, why `omp` is spawned as subprocess instead of imported, why Starlette was chosen over other frameworks) are not documented. The `REFACTOR_PLAN.md` and `ARCHITECTURE.md` capture some design intent, but forward-looking decisions are lost.
- **Reasoning:** The project has undergone significant evolution (hermes-agent → omp-agent, monolithic → package). Without ADRs, new contributors and agents lack context for design decisions.
- **Suggested Approach:** Create a `docs/adr/` directory with initial ADRs for: (1) why subprocess-based omp integration, (2) LoopConfig design rationale, (3) JSON ledger schema design, (4) web UI SSE architecture.
- **Affected Files:** new `docs/adr/` directory

---

### 🔄 CI/CD

#### CICD-001 — No release workflow (tag → build → publish)

| Field | Value |
|-------|-------|
| **Category** | ci-cd |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** Despite having version `14.39.0` and 213 commits, there are zero git tags and no release workflow. The version number exists only in source files. There is no automation to build the package, create a GitHub release, or publish to PyPI. Releases are manual (if they happen at all).
- **Reasoning:** Users cannot install a specific version. The project has no release history. Automated releases are standard practice for any Python package.
- **Suggested Approach:** Create `.github/workflows/release.yml` triggered by `v*` tag push. Steps: build distribution (`python -m build`), create GitHub Release with changelog, optionally publish to PyPI via `pypa/gh-action-pypi-publish`. Add `make release` target that tags and pushes.
- **Affected Files:** new `.github/workflows/release.yml`, `Makefile`

---

#### CICD-002 — CI test matrix not aligned with actual supported Python versions

| Field | Value |
|-------|-------|
| **Category** | ci-cd |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** CI tests Python 3.10, 3.11, 3.12, 3.13. The actual runtime is 3.14.5. The test matrix doesn't include 3.14. While 3.14 is very new, the CI should test the actual version the project runs on.
- **Reasoning:** If a future dependency drops 3.10 support, CI would be the first to know. Testing the actual runtime version is standard practice.
- **Suggested Approach:** Add Python 3.14 to the matrix as non-blocking (allow-failure). Remove 3.10 if it becomes a maintenance burden.
- **Affected Files:** `.github/workflows/ci.yml`

---

#### CICD-003 — No Docker build/publish in CI

| Field | Value |
|-------|-------|
| **Category** | ci-cd |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Large |
| **Dependencies** | FEAT-006 |
| **Status** | Pending |

- **Description:** The project has no containerized deployment option. There is no Dockerfile in the main repo. Publishing a Docker image to ghcr.io on version tags would enable containerized deployment.
- **Reasoning:** Low priority until a Dockerfile exists. Add this after FEAT-006 (Dockerfile).
- **Suggested Approach:** After creating a Dockerfile, add a CI job that builds the image and pushes to GitHub Container Registry on version tags.
- **Affected Files:** new `.github/workflows/release.yml` (Docker publish job)

---

#### CICD-004 — Dependabot updates don't auto-merge patch versions

| Field | Value |
|-------|-------|
| **Category** | ci-cd |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** Dependabot creates PRs for dependency updates but they must be manually reviewed and merged. For patch-level security updates, this introduces unnecessary delay. Minor/major updates should still be manually reviewed.
- **Reasoning:** Auto-merging patch versions reduces the window between CVE disclosure and fix deployment. The project already has good CI coverage to catch regressions.
- **Suggested Approach:** Configure Dependabot to auto-merge patch updates that pass CI. Use `dependabot/fetch-metadata` action to categorize PRs by update type.
- **Affected Files:** `.github/dependabot.yml`, new `.github/workflows/dependabot-auto-merge.yml`

---

### 🧹 Code Cleanup & Tech Debt

#### DEBT-001 — Duplicate status file writers: `status.py` and `file_utils.py`

| Field | Value |
|-------|-------|
| **Category** | tech-debt |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `omp_loop/status.py:write_status()` writes a comprehensive status JSON file (pid, version, uptime, iteration count, last error). `omp_loop/file_utils.py:write_status_file()` writes a lightweight one-liner JSON. Both write JSON status about the same daemon process but with different schemas and from different call sites inside `run_loop()`. Adding a field requires updating both — a maintenance liability.
- **Reasoning:** This is a clear case of copy-paste duplication. The lightweight writer adds no value — both are consumed by the web UI's `loop_manager.py` which reads the richer status anyway.
- **Suggested Approach:** Unify into `status.py:write_status()`. Have `file_utils.py` import and call it, or remove the lightweight variant and update `run_loop()` call sites.
- **Affected Files:** `omp_loop/status.py`, `omp_loop/file_utils.py:write_status_file()`, `omp_loop/loop.py`

---

#### DEBT-002 — `error_utils.py: _suggest_actionable_fix()` has complex nested conditionals

| Field | Value |
|-------|-------|
| **Category** | tech-debt |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `_suggest_actionable_fix()` (~130 lines) uses deeply nested if/elif chains for every error-type × classification combination. Some branches return `None` after assembling tips that are then discarded (e.g., the regression branch). The complexity makes it hard to test exhaustively and hard to add new error patterns.
- **Reasoning:** This function is a maintenance bottleneck. Adding a new error type requires understanding 130 lines of conditionals. A data-driven approach would make it trivially extensible.
- **Suggested Approach:** Replace with a lookup table (dict mapping `(error_type, progress_classification) → suggestion_template`). Each entry is a standalone data item, easy to test and extend. This also makes the function pure and testable without mocks.
- **Affected Files:** `omp_loop/error_utils.py` (`_suggest_actionable_fix`)

---

#### DEBT-003 — `loop.py` has unused imports and suppressed lint warnings

| Field | Value |
|-------|-------|
| **Category** | tech-debt |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | ARCH-001 |
| **Status** | Pending |

- **Description:** `loop.py` has `# ruff: noqa: ARG001, F841` at module level to suppress unused argument and variable warnings. The `run_loop` function unpacks 20+ `cfg.*` attributes into local variables, many of which are never used. There are dual imports — both `status.write_status` and `file_utils.write_status_file` are imported but only one is called.
- **Reasoning:** The `noqa` suppression was added as a workaround for the monolithic function's complexity. After decomposition, many of these will naturally resolve.
- **Suggested Approach:** After decomposing `run_loop()` (ARCH-001), clean up unused local variable assignments. Remove the module-level `noqa` comment. Audit and deduplicate imports.
- **Affected Files:** `omp_loop/loop.py`

---

#### DEBT-004 — `config_manager.py` has redundant meta definitions vs config.py

| Field | Value |
|-------|-------|
| **Category** | tech-debt |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `web_app/config_manager.py` maintains its own `CONFIG_META` dict with type, label, group, icon, and help text for each config key. This duplicates information already present in `omp_loop/config.py` (the `LoopConfig` dataclass fields). Adding a config field requires updating both files.
- **Reasoning:** This is a maintenance burden. Every new CLI flag needs both a `LoopConfig` field and a `CONFIG_META` entry. A mismatch means the web UI shows incorrect config.
- **Suggested Approach:** Generate `CONFIG_META` dynamically from `LoopConfig` field annotations. Use field metadata (`field(metadata={"group": "core", "label": "Goal"})`) in the dataclass itself. Remove the hardcoded dict from `config_manager.py`.
- **Affected Files:** `web_app/config_manager.py`, `omp_loop/config.py`

---

### ✨ Features

#### FEAT-001 — Structured JSON logging for the daemon

| Field | Value |
|-------|-------|
| **Category | feature |
| **Priority | P1 — High |
| **Impact | High |
| **Effort | Medium |
| **Dependencies | None |
| **Status | Pending |

- **Description:** All daemon logging uses bare `print()` calls and `logger.info(f"...")` with inline string formatting. No structured fields (event type, iteration number, error code, duration, correlation ID). The web UI's regex-based parsers (BUG-001) exist because there's no structured event stream to consume. Without structured logging, production debugging is manual log scraping.
- **Reasoning:** This is a foundational improvement that unlocks multiple other items: fixing BUG-001 (regex parsing), enabling log aggregation (ELK/Datadog), and improving debuggability. Structured logging is table stakes for production services.
- **Suggested Approach:** Define a `StructuredEvent` TypedDict or dataclass with fields: `event`, `iteration`, `duration_ms`, `error_type`, `worker_id`, `correlation_id`. Create a `log_event()` function that writes JSON lines. Console output stays human-readable (colorized). File output uses JSON format.
- **Affected Files:** `omp_loop/file_utils.py`, `omp_loop/loop.py`, `omp_loop/error_recovery.py`, `omp_loop/git_utils.py`, `omp_loop/heartbeat.py`, `web_app/loop_manager.py`

---

#### FEAT-002 — Support multiple named config profiles

| Field | Value |
|-------|-------|
| **Category** | feature |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** Currently there is a single `~/.config/omp-loop/config.json`. Users who run different loop configurations (e.g., "code review" vs "research" vs "bug fixing") must manually swap config files. Support for named profiles (`--profile research`) would make this seamless.
- **Reasoning:** The project already has 105+ flags — managing multiple configurations via CLI flags alone is impractical. Profile-based config switching is a natural UX evolution.
- **Suggested Approach:** Change `config_file.py` to support a config directory instead of a single file. Add `--profile` CLI flag. Store configs as `config_{profile}.json`. The web UI can add a profile selector dropdown.
- **Affected Files:** `omp_loop/config_file.py`, `omp_loop/cli.py`, `web_app/config_manager.py`, `web_app/static/index.html`

---

#### FEAT-003 — Web UI theme preference persistence (localStorage)

| Field | Value |
|-------|-------|
| **Category** | feature |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The web UI has a theme toggle button (dark/light), but the preference is not persisted across page reloads. Users must re-toggle the theme each time they load the dashboard.
- **Reasoning:** Minor UX gap. The theme toggle is already implemented — only persistence is missing. The CSS already supports both themes.
- **Suggested Approach:** Save theme preference to `localStorage` on toggle. On page load, read `localStorage` and apply the saved theme before rendering (to prevent flash of wrong theme).
- **Affected Files:** `web_app/static/app.js`, `web_app/static/index.html`

---

#### FEAT-004 — Prometheus metrics endpoint

| Field | Value |
|-------|-------|
| **Category** | feature |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The web server exposes iteration counts, error counts, and system resources via the dashboard, but there is no Prometheus `/metrics` endpoint for integration with monitoring stacks. Operators who use Grafana/Prometheus cannot monitor the daemon without custom scraping.
- **Reasoning:** Services that run unattended for days need monitoring integration. Prometheus is the industry standard. This enables alerts on iteration failures, error rate spikes, and heartbeat loss.
- **Suggested Approach:** Add optional Prometheus metrics via `prometheus_fastapi_instrumentator` or manual counter instrumentation. Export: request count/latency by endpoint, iteration rate, iteration duration, worker count, error rate by type. Disabled by default — enabled with `--metrics` flag.
- **Affected Files:** `web_app/server.py`, `omp_loop/config.py`, `pyproject.toml`

---

#### FEAT-005 — Archive old iterations to prevent ledger file bloat

| Field | Value |
|-------|-------|
| **Category** | feature |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The JSON ledger file grows unboundedly with each iteration. After thousands of iterations, the ledger becomes large (>10MB), slowing down every read/write operation. There is no archiving mechanism — all iterations live in a single file forever.
- **Reasoning:** The daemon is designed for long-running autonomous operation. After days of continuous iteration, the ledger will become slow enough to impact performance. An archiving strategy is essential for production durability.
- **Suggested Approach:** Add configurable iteration archive limit (default: keep last 1000 iterations in the main ledger, archive older ones to timestamped archive files). The web UI can still read archived iterations by querying the archive directory. CLI flags: `--archive-limit N`, `--archive-dir PATH`.
- **Affected Files:** `omp_loop/state.py`, `omp_loop/loop.py`, `omp_loop/config.py`, `web_app/server.py`

---

#### FEAT-006 — Dockerfile and docker-compose for containerized deployment

| Field | Value |
|-------|-------|
| **Category** | feature |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The project has no Dockerfile in the main repository. Containerized deployment would make it easy to run omp-loop in CI/CD pipelines, cloud environments, or isolated environments where Python setup is not desired.
- **Reasoning:** Containerization is standard for deployment. Currently, running omp-loop requires Python, pip, a virtual environment, and the `omp` binary on PATH. A Docker image simplifies this to `docker run`.
- **Suggested Approach:** Create a multi-stage Dockerfile: build stage (pip install) → runtime stage (Python slim image, copy installed package). Use `uvicorn` as entry point for web UI. Create `docker-compose.yml` with volume mounts for config, ledger data, and omp binary.
- **Affected Files:** new `Dockerfile`, new `docker-compose.yml`, new `.dockerignore`

---

### ⬆️ Dependencies & Infrastructure

#### DEP-001 — Recompile lockfiles (pydantic version drift)

| Field | Value |
|-------|-------|
| **Category** | infrastructure |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The installed pydantic version (2.12.5) may differ from the lockfile version (2.13.4), suggesting the last `pip install` used range resolution instead of the lockfile. Lockfiles are meant to be the source of truth — drift indicates either manual `pip install` without `--no-deps` or lockfiles not recompiled after the last `pyproject.toml` change.
- **Reasoning:** Lockfile drift undermines reproducibility. If a developer installs from lockfiles and gets different versions than what was tested, bugs may appear that were never seen in CI.
- **Suggested Approach:** Run `make update-lock` to regenerate both lockfiles. Run `make verify-lock` to confirm. Then reinstall from lockfiles: `pip install -r requirements.txt -r requirements-dev.txt`.
- **Affected Files:** `requirements.txt`, `requirements-dev.txt`

---

#### DEP-002 — No explicit dependency auditing in CI

| Field | Value |
|-------|-------|
| **Category** | infrastructure |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** While `safety` checks for known CVEs, there's no license compliance check in CI. Dependencies could introduce incompatible licenses (AGPL, proprietary) without detection. There's also no check for dependency freshness (how outdated each dep is).
- **Reasoning:** License compliance is important for any project that may be distributed or used commercially. The current CI only checks security vulnerabilities.
- **Suggested Approach:** Add `pip-licenses` to the `dev` dependencies. Add a `make licenses` target that checks for forbidden licenses. Run in CI as a non-blocking advisory step.
- **Affected Files:** `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`

---

#### DEP-003 — No strategy for optional dependency groups

| Field | Value |
|-------|-------|
| **Category** | infrastructure |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** Currently all optional features (Prometheus, file watching with watchdog, Sentry error tracking) would require additional dependencies. There is no defined strategy for how optional deps are structured or documented.
- **Reasoning:** As the project grows, optional features should have clear dependency groups. This makes the base installation lean while allowing users to opt into specific capabilities.
- **Suggested Approach:** Define standard optional groups in `pyproject.toml`: `web`, `monitoring`, `notifications`, `watch`, `all`. Document in README which extras provide which features.
- **Affected Files:** `pyproject.toml`, `README.md`

---

### 📊 Observability & Monitoring

#### OBS-001 — Structured event emission from daemon to web UI

| Field | Value |
|-------|-------|
| **Category** | observability |
| **Priority** | P1 — High |
| **Impact** | High — Foundation for BUG-001 fix, log aggregation |
| **Effort** | Medium |
| **Dependencies** | None (can be done incrementally) |
| **Status** | Pending |

- **Description:** The daemon has no structured event bus. All communication between the daemon and external consumers (web UI, external monitoring, log aggregation) passes through unstructured text output. This makes integration brittle and debugging painful.
- **Reasoning:** This is the foundation for fixing BUG-001 (regex parsing) and enabling log aggregation. The web UI should consume NDJSON events, not parse colorized log strings.
- **Suggested Approach:** Add an `EventBus` singleton that accumulates events in a ring buffer. Events are structured dicts with `type`, `timestamp`, `data` fields. The daemon emits events for: iteration started/completed, error classified, recovery action taken, worker spawned/completed, git commit made. Events are written to a structured JSON file that the web UI can poll. Console output stays human-readable.
- **Affected Files:** new `omp_loop/event_bus.py`, `omp_loop/loop.py`, `omp_loop/error_recovery.py`, `omp_loop/git_utils.py`, `web_app/loop_manager.py`

---

#### OBS-002 — Add runtime health check endpoint with component status

| Field | Value |
|-------|-------|
| **Category** | observability |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The current `/api/health` endpoint returns a simple `{"status": "ok"}`. There's no component-level health information: is the daemon process running? Is the ledger readable? Is the omp binary available? Is there sufficient disk space?
- **Reasoning:** For production monitoring, a health endpoint should provide component-level status for dependent services. This enables monitoring systems to distinguish between daemon-down, omp-binary-missing, and disk-full conditions.
- **Suggested Approach:** Expand `/api/health` to return: daemon status (running/stopped), ledger readability, omp binary availability, disk space status, uptime, last successful iteration timestamp. Use HTTP status codes: 200 = healthy, 503 = degraded, with JSON detail.
- **Affected Files:** `web_app/server.py` (/api/health endpoint)

---

#### OBS-003 — Track iteration latency percentiles and success rate over time

| Field | Value |
|-------|-------|
| **Category** | observability |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Small |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** The stats module tracks basic aggregates (total iterations, avg duration, success/error counts) but does not track latency percentiles (p50, p95, p99) or success rate over sliding windows. These are essential for understanding daemon health trends.
- **Reasoning:** Average duration is easily skewed by outliers. Percentiles give a more accurate picture of iteration performance. Sliding-window success rate detects degradation before it becomes critical.
- **Suggested Approach:** Add p50/p95/p99 latency tracking to the ledger stats. Use a rolling window (last 100 iterations) for success rate calculation. Expose via the web API and dashboard.
- **Affected Files:** `omp_loop/stats.py`, `omp_loop/state.py`, `web_app/server.py`

---

### 🤖 Automation

#### AUTO-001 — Automatic task type detection and toolset selection

| Field | Value |
|-------|-------|
| **Category** | automation |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** `config.py` defines `TASK_PATTERNS` with 6 task types (research, code-fix, code-build, system-admin, data-processing, content) and associated toolset extensions. However, the task type is never auto-detected — the user must explicitly set `--task-type`. The keyword matching infrastructure exists but isn't wired into the loop's auto-configuration path.
- **Reasoning:** The infrastructure (keyword matching, extra toolsets) is already built. Wiring it into the auto-config path would mean users get better tooling without manual flag setting. This makes the daemon more autonomous.
- **Suggested Approach:** Add task type auto-detection before iteration start: compare the goal string against `TASK_PATTERNS` keywords, pick the best-matching type, and extend the toolset automatically. Allow manual override via `--task-type`. Log the detected type.
- **Affected Files:** `omp_loop/config.py` (TASK_PATTERNS), `omp_loop/loop.py` (iteration setup), `omp_loop/functions.py`

---

#### AUTO-002 — Goal evolution with learned context from previous iterations

| Field | Value |
|-------|-------|
| **Category** | automation |
| **Priority** | P2 — Medium |
| **Impact** | Medium |
| **Effort** | Large |
| **Dependencies** | ARCH-001 (easier after loop decomposition) |
| **Status** | Pending |

- **Description:** The daemon has `_evolve_goal()` which detects `NEXT_GOAL:` markers in omp output, but the evolved goal is always derived from the current iteration only. There's no mechanism to build context across multiple iterations or to learn from repeated failures. The daemon can get stuck in a loop of the same failure → recovery → retry cycle.
- **Reasoning:** The goal evolution infrastructure exists but is stateless per-iteration. Adding cross-iteration context would enable the daemon to change approach when a strategy repeatedly fails, making it truly autonomous.
- **Suggested Approach:** Add a "context summary" that tracks: (1) last 3 goal attempts and their outcomes, (2) error patterns that recur, (3) files modified in previous iterations. Include this in the goal context sent to omp. The goal can evolve intelligently rather than blindly retrying the same approach.
- **Affected Files:** `omp_loop/loop.py` (`_evolve_goal`, `_build_progressive_context`), new `omp_loop/context.py`

---

#### AUTO-003 — Intelligent convergence detection with content-aware comparison

| Field | Value |
|-------|-------|
| **Category** | automation |
| **Priority** | P3 — Low |
| **Impact** | Low |
| **Effort** | Medium |
| **Dependencies** | None |
| **Status** | Pending |

- **Description:** Convergence detection uses a simple threshold on output similarity (`DEFAULT_CONVERGENCE_THRESHOLD=0.9`). It doesn't consider: (a) whether changes are meaningful (e.g., just timestamp diffs), (b) whether the goal is actually achieved, (c) diminishing returns pattern (improvements getting smaller each iteration).
- **Reasoning:** The current approach can converge prematurely (minor output changes trigger "converged") or never converge (output changes meaningfully each time even though goal is met). Content-aware convergence would make the daemon more reliable.
- **Suggested Approach:** Add content-aware convergence: (1) filter trivial diffs (timestamps, whitespace), (2) detect diminishing returns (improvement delta decreasing over 3+ iterations), (3) add optional goal-achievement check via omp's own assessment. Make convergence detection pluggable.
- **Affected Files:** `omp_loop/loop.py` (convergence check), `omp_loop/config.py` (convergence defaults), new `omp_loop/convergence.py`

---

## Top 10 Prioritized Items

Ranked by **Value/Effort ratio** (higher is better). Security items get a 1.5× impact multiplier.

| Rank | ID | Title | Category | Priority | Impact | Effort | V/E | Phase |
|------|----|-------|----------|----------|--------|--------|-----|-------|
| 1 | TEST-004 | `file_watcher.py` zero coverage | testing | P1 — High | High | Small | **3.0** | Week 1 |
| 2 | BUG-005 | FileLock busywait fixed interval | bug | P2 — Medium | Medium | Small | **2.0** | Week 1 |
| 3 | BUG-004 | Heartbeat 5s poll delay | bug | P2 — Medium | Medium | Small | **2.0** | Week 1 |
| 4 | DEBT-001 | Duplicate status file writers | tech-debt | P2 — Medium | Medium | Small | **2.0** | Week 1 |
| 5 | CICD-001 | Release workflow (tag → publish) | ci-cd | P2 — Medium | Medium | Medium | **1.5** | Week 1 |
| 6 | FEAT-001 | Structured JSON logging | feature | P1 — High | High | Medium | **1.3** | Week 2 |
| 7 | OBS-001 | Structured event emission | observability | P1 — High | High | Medium | **1.3** | Week 2 |
| 8 | TEST-002 | Core loop 19% coverage | testing | P1 — High | High | Large | **1.0** | Week 3 |
| 9 | ARCH-001 | Decompose monolithic `run_loop()` | architecture | P0 — Critical | Critical | XLarge | **0.8** | Week 4+ |
| 10 | TEST-003 | CLI main() coverage | testing | P1 — High | High | Medium | **1.0** | Week 1 |

### Phase Plan

```
Phase 1 — Quick Wins (Week 1)
─────────────────────────────────────────────────────────────
TEST-004 file_watcher.py tests              (Small)
BUG-005  FileLock exponential backoff       (Small)
BUG-004  Heartbeat poll interval            (Small)
DEBT-001 Unify status file writers          (Small)
CICD-001 Release workflow                   (Medium)

Phase 2 — Foundation (Week 2-3)
─────────────────────────────────────────────────────────────
FEAT-001 Structured JSON logging            (Medium)
OBS-001  Structured event emission          (Medium)
SEC-002  .env in .gitignore                 (Small)
DEVX-001 Pre-commit duality resolution      (Small)
BUG-002  JSON extraction string-literals    (Medium)

Phase 3 — Deep Work (Week 4-6)
─────────────────────────────────────────────────────────────
TEST-002 Core loop coverage                 (Large)
ARCH-001 run_loop decomposition Phase 1     (XLarge)
TEST-003 CLI main() coverage                (Medium)
TEST-001 E2E integration tests              (Large)

Phase 4 — Growth (Week 7+)
─────────────────────────────────────────────────────────────
ARCH-002 State machine                      (Large)
ARCH-003 LoopConfig split                   (Large)
FEAT-002 Config profiles                    (Medium)
FEAT-004 Prometheus metrics                 (Medium)
```

---

## Quick Wins (High Impact, Low Effort)

Items deliverable in <2 hours with meaningful impact:

| ID | Item | Est. Time |
|----|------|-----------|
| SEC-002 | `.env` in `.gitignore` (uncomment + add `.env.*`) | 5 min |
| TEST-004 | `file_watcher.py` tests (small class, easy to test) | 1-2 hr |
| BUG-004 | Heartbeat `threading.Event` instead of sleep | 30 min |
| BUG-005 | FileLock exponential backoff + jitter | 30 min |
| BUG-006 | Config write failure logging | 15 min |
| DEBT-001 | Unify status file writers | 30 min |
| PERF-003 | SSE poller mtime check + skip when no clients | 30 min |
| PERF-001 | Dashboard incremental rendering | 1-2 hr |
| DOC-001 | README screenshot, omp version, Swagger link | 30 min |
| DOC-003 | SECURITY.md creation | 30 min |
| DEVX-001 | Pre-commit duality resolution | 30 min |
| DEVX-003 | Safety deprecated command update | 15 min |
| CICD-004 | Dependabot auto-merge patches | 30 min |
| DEP-001 | Recompile lockfiles | 15 min |
| SEC-005 | Sentinel file size bound | 10 min |
| BUG-009 | Docstring position fix | 5 min |
| DOC-004 | Add missing docstrings (2 functions) | 10 min |

---

## Effort Distribution

| Effort | Count | Items |
|--------|-------|-------|
| **Small** (<2 hr) | 21 | SEC-002, SEC-003, SEC-004, SEC-005, BUG-003, BUG-004, BUG-005, BUG-006, BUG-008, BUG-009, TEST-004, TEST-006, PERF-001, PERF-003, PERF-004, PERF-005, DEBT-001, DEBT-003, DEVX-001, DEVX-002, DEVX-003, DEVX-004, DOC-001, DOC-003, DOC-004, DOC-005, CICD-002, CICD-004, DEP-001, DEP-003, OBS-002, OBS-003 |
| **Medium** (<1 day) | 16 | BUG-001, BUG-002, BUG-007, TEST-003, TEST-005, TEST-007, PERF-002, FEAT-001, FEAT-002, FEAT-004, FEAT-005, FEAT-006, DEBT-002, DEBT-004, OBS-001, AUTO-001, AUTO-003, CICD-001, DEP-002 |
| **Large** (2-3 days) | 4 | TEST-001, TEST-002, ARCH-002, ARCH-003 |
| **XLarge** (1+ week) | 2 | ARCH-001, AUTO-002 |

---

## Dependency Map

```
                          ARCH-001 (loop decomposition)
                          ┌──────────────────────────┐
                          │  Blocks:                  │
                          │  ├── ARCH-002 (state m/c) │
                          │  ├── ARCH-003 (LoopConfig)│
                          │  ├── TEST-002 (loop cov)  │
                          │  ├── DEBT-003 (unused      │
                          │  │   imports cleanup)     │
                          │  └── AUTO-002 (goal learn)│
                          └──────────────────────────┘

BUG-002 (JSON extract) ──▶ PERF-004 (two scans)
  │
  └──▶ TEST-005 (string test cases)

BUG-003 (zsh completions) ──▶ BUG-008 (legacy workaround)

BUG-001 (regex parsing) ──▶ OBS-001 (structured events)
  │
  └──▶ (resolved by OBS-001)

SEC-001 (shell=True) ──▶ ✅ Completed (2026-06-30)

FEAT-006 (Dockerfile) ──▶ CICD-003 (Docker CI publish)

ARCH-001 ──▶ (Phase 1: characterization tests first)
  │
  ├── TEST-002 (can start in parallel with extracted fns)
  │
  └── Phase 2/3 only after decomposition is stable

Items without dependencies (can be parallelized):
  SEC-003, SEC-005, BUG-004, BUG-005, BUG-006, BUG-009
  TEST-003, TEST-004, TEST-006, TEST-007, PERF-001, PERF-002, PERF-003
  DEVX-001, DEVX-002, DEVX-003, DOC-001, DOC-003, DOC-004
  CICD-001, CICD-002, CICD-004, DEP-001, DEP-002, DEP-003
  FEAT-001, FEAT-002, FEAT-004, FEAT-005, OBS-002, OBS-003
  AUTO-001, AUTO-003, DEBT-001, DEBT-002, DEBT-004
```

---

## Summary Statistics

| Category | Count | P0 | P1 | P2 | P3 |
|----------|-------|----|----|----|----|
| Bug | 9 | 1 | 1 | 5 | 2 |
| Security | 4 | 0 | 0 | 3 | 1 |
| Architecture | 5 | 1 | 2 | 2 | 0 |
| Testing | 7 | 1 | 2 | 3 | 1 |
| Performance | 5 | 0 | 0 | 3 | 2 |
| DevX | 4 | 0 | 0 | 1 | 3 |
| Docs | 5 | 0 | 0 | 3 | 2 |
| CI/CD | 4 | 0 | 0 | 1 | 3 |
| Tech Debt | 4 | 0 | 0 | 3 | 1 |
| Feature | 6 | 0 | 1 | 3 | 2 |
| Infrastructure | 3 | 0 | 0 | 2 | 1 |
| Observability | 3 | 0 | 1 | 1 | 1 |
| Automation | 3 | 0 | 0 | 2 | 1 |

**Total: 62 items** (2 P0, 7 P1, 32 P2, 21 P3)

**Effort distribution:** 33 Small, 18 Medium, 10 Large, 2 XLarge

**Quick wins (Small + P1/P2):** 19 items deliverable in <2 hours each

---

*This backlog is a living document. Last updated: 2026-06-30. Total items: 62.*
