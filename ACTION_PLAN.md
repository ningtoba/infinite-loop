# Action Plan — Top 10 Prioritized Items

> Execution plan for **pi-loop** v14.39.0 engineering backlog.
> Items ranked by **value/effort ratio** and ordered for minimal blocking dependencies.
> Generated: 2026-06-30

---

## Ranking Methodology

Each item is scored on a **Value/Effort** ratio where:

- **Impact** = 1–5 (severity of the problem or benefit of solving it)
- **Effort** = 1–5 (estimated cost to implement)
- **Value/Effort** = Impact ÷ Effort (higher is better)
- **Security/Critical items**: Impact multiplied by 1.5× urgency multiplier
- **Performance/Observability items**: Impact multiplied by 1.2× urgency multiplier

The top 10 items maximize engineering ROI — fixing what hurts the most with the least effort first.

---

## Top 10 Execution Plan

### Phase 1: Quick Wins (Week 1)

These are high-impact, low-effort items that deliver immediate value. All can be parallelized.

---

#### 🥇 #1: Fix `status.py` uptime calculation (BUG-013)

| Field | Value |
|-------|-------|
| **ID** | BUG-013 |
| **Value/Effort** | **5.0** (Impact 5 ÷ Effort 1) |
| **Priority** | 🔴 Critical |
| **Impact** | 5 — Status file always reports 0 uptime |
| **Effort** | 1 (Trivial, <30 min) |
| **Dependencies** | None |
| **Est. Time** | 15 minutes |
| **Why Now** | The uptime formula `monotonic() - (time.time() - monotonic())` simplifies to `2×monotonic - time.time()` — a completely meaningless value. The `/proc/pid/stat` fallback is never used because the outer `except` silently catches all errors. Every status file read reports 0 uptime. This is the cheapest fix with the highest correctness impact. |

**Steps:**

1. Track start time as `_start_time = time.monotonic()` at module level in `status.py`
2. Replace broken formula with `uptime_seconds = time.monotonic() - _start_time`
3. Remove the broken `/proc/pid/stat` fallback (it's never reached anyway)
4. Write unit tests confirming uptime increases monotonically

**Files:** `pi_loop/status.py` (line ~62)

---

#### 🥈 #2: Validate `http_callback` URL scheme (SEC-001)

| Field | Value |
|-------|-------|
| **ID** | SEC-001 |
| **Value/Effort** | **7.5** (Impact 5 × 1.5 Security ÷ Effort 1) |
| **Priority** | 🔴 Critical |
| **Impact** | 5 — Unvalidated URL could read local files via `file://` |
| **Effort** | 1 (Trivial, <30 min) |
| **Dependencies** | None |
| **Est. Time** | 30 minutes |
| **Why Now** | Bandit B310 flags this: `urllib.request.urlopen()` on a user-configurable URL with no scheme validation. A `file://` URL reads local files. A `data://` URL triggers unexpected behavior. Adding `urlparse` validation restricts to `http://`/`https://` only. |

**Steps:**

1. Add `from urllib.parse import urlparse` to `loop.py`
2. Before `urllib.request.urlopen()`, validate: `parsed = urlparse(http_callback)` then check `parsed.scheme in ("http", "https")`
3. Log WARNING and skip callback if scheme is invalid
4. Add unit tests for valid/invalid schemes

**Files:** `pi_loop/loop.py` (line ~714)

---

#### 🥉 #3: Log notification/HTTP callback failures (BUG-002)

| Field | Value |
|-------|-------|
| **ID** | BUG-002 |
| **Value/Effort** | **4.0** (Impact 4 ÷ Effort 1) |
| **Priority** | 🟠 High |
| **Impact** | 4 — All notification failures silently disappear |
| **Effort** | 1 (Trivial, <30 min) |
| **Dependencies** | None |
| **Est. Time** | 30 minutes |
| **Why Now** | `run_loop()` wraps desktop notification and HTTP callback dispatch in `with suppress(Exception):`. DNS failures, connection errors, credential issues — all silently vanish. Operators have no idea their notifications are failing. |

**Steps:**

1. Replace each `with suppress(Exception):` with a `try/except Exception` block
2. Log at WARNING level with the error detail and context (notification type, callback URL)
3. Keep the failure non-fatal (notifications are best-effort)
4. Write unit tests that verify WARNING log calls on simulated failures

**Files:** `pi_loop/loop.py` (lines ~225, ~244)

---

#### #4: Add `console.error()` to empty `catch` blocks in `app.js` (CLEAN-005)

| Field | Value |
|-------|-------|
| **ID** | CLEAN-005 |
| **Value/Effort** | **3.0** (Impact 3 ÷ Effort 1) |
| **Priority** | 🟡 Medium |
| **Impact** | 3 — Frontend errors are completely invisible |
| **Effort** | 1 (Trivial, <15 min) |
| **Dependencies** | None |
| **Est. Time** | 15 minutes |
| **Why Now** | 5+ `catch` blocks in `app.js` are empty or contain only `/* ignore */`. Network failures, parse errors, DOM access failures — all invisible. Debugging client-side issues requires catching errors in the debugger before they're lost. |

**Steps:**

1. Search for `catch` blocks in `web_app/static/app.js`
2. Add `console.error('Error [descriptive label]:', e)` to each empty one
3. For user-visible errors (form submission failures, connection loss), add a toast notification
4. Use descriptive labels like `'Error [fetch config]:', e`

**Files:** `web_app/static/app.js`

---

#### #5: Validate CLI `--config` JSON keys (BUG-008)

| Field | Value |
|-------|-------|
| **ID** | BUG-008 |
| **Value/Effort** | **3.0** (Impact 3 ÷ Effort 1) |
| **Priority** | 🟠 High |
| **Impact** | 3 — Config typos silently ignored, settings stay at defaults |
| **Effort** | 1 (Trivial, <30 min) |
| **Dependencies** | None |
| **Est. Time** | 30 minutes |
| **Why Now** | `cli.py` applies arbitrary JSON keys to the argparse Namespace via `setattr(args, key, val)` with no validation. A typo like `"max-iterration"` silently creates an unused attribute while `max_iterations` stays at default. The user's intent is silently lost. |

**Steps:**

1. Collect the set of known argparse dest names from the parser
2. After loading config JSON, check each key against known names
3. Log WARNING for unknown/misspelled keys with the closest match (use `difflib.get_close_matches`)
4. Skip unknown keys instead of silently applying them

**Files:** `pi_loop/cli.py` (lines ~135-150)

---

#### #6: Add coverage reporting to CI (CI-CD-001)

| Field | Value |
|-------|-------|
| **ID** | CI-CD-001 |
| **Value/Effort** | **3.0** (Impact 3 ÷ Effort 1) |
| **Priority** | 🟠 High |
| **Impact** | 3 — Coverage regressions go undetected |
| **Effort** | 1 (Trivial, <30 min) |
| **Dependencies** | None |
| **Est. Time** | 30 minutes |
| **Why Now** | `pytest-cov` is installed but `make test` doesn't use it. Coverage dropped from earlier audits but nobody noticed. Adding `--cov` flags to `make test` and a coverage threshold to CI prevents regressions. |

**Steps:**

1. Add `[tool.coverage.run]` to `pyproject.toml` with `source = ["pi_loop", "web_app"]`
2. Add `[tool.coverage.report]` with `fail_under = 65`
3. Update `make test` to add `--cov=pi_loop --cov=web_app --cov-report=term-missing`
4. Add `--cov-report=xml` to CI test job for artifact upload

**Files:** `Makefile`, `.github/workflows/ci.yml`, `pyproject.toml`

---

### Phase 2: Security & Quality (Weeks 2–3)

---

#### #7: Add guardrails for `shell=True` error command (SEC-005)

| Field | Value |
|-------|-------|
| **ID** | SEC-005 |
| **Value/Effort** | **3.0** (Impact 4 × 1.5 Security ÷ Effort 2) |
| **Priority** | 🟠 High |
| **Impact** | 4 — Config file compromise → arbitrary command execution |
| **Effort** | 2 (Small, <2 hr) |
| **Dependencies** | None |
| **Est. Time** | 1-2 hours |
| **Why Now** | `subprocess.run(on_error_cmd, shell=True)` on a user-configurable command is intentional but under-protected. If `~/.config/pi-loop/config.json` is compromised, arbitrary shell commands execute with daemon privileges. |

**Steps:**

1. Log the full `on_error_cmd` at INFO level before execution (audit trail)
2. Validate command length (reject > 500 chars) and character restrictions (reject shell metacharacters `;`, `|`, `` ` ``, `$()`  unless explicitly needed)
3. Add a startup WARNING log when `on_error_cmd` is configured
4. Document the risk explicitly in README security section

**Files:** `pi_loop/loop.py` (line 727), `README.md`

---

#### #8: Implement structured JSON logging (FEAT-003)

| Field | Value |
|-------|-------|
| **ID** | FEAT-003 |
| **Value/Effort** | **1.6** (Impact 4 × 1.2 Performance ÷ Effort 3) |
| **Priority** | 🟠 High |
| **Impact** | 4 — Without structured logs, debugging is manual scraping |
| **Effort** | 3 (Medium, 4-6 hr) |
| **Dependencies** | None |
| **Est. Time** | 4-6 hours |
| **Why Now** | All daemon logging uses bare `print()` calls and `logger.info(f"...")` with inline formatting. No structured fields (event type, iteration number, error code, duration). The web UI's regex-based parsers (BUG-003) are a direct consequence — they exist because there's no structured event stream. |

**Steps:**

1. Define a `StructuredEvent` dataclass with fields: `event`, `iteration`, `duration_ms`, `error_type`, `worker_id`, `correlation_id`
2. Create a `log_event()` function that writes JSON lines to the log file
3. Console output remains human-readable; file output uses JSON format
4. Add correlation ID per daemon run (generated at startup, logged in every event)
5. Migrate `print()` calls incrementally, starting with iteration lifecycle events

**Files:** `pi_loop/file_utils.py`, `pi_loop/loop.py`, `pi_loop/error_recovery.py`, `pi_loop/git_utils.py`, `pi_loop/heartbeat.py`, `web_app/loop_manager.py`

---

#### #9: Cover critical modules — `loop.py`, `cli.py`, `status.py` (TEST-003)

| Field | Value |
|-------|-------|
| **ID** | TEST-003 |
| **Value/Effort** | **1.3** (Impact 4 ÷ Effort 3) |
| **Priority** | 🟠 High |
| **Impact** | 4 — Core loop is the most critical code path with lowest coverage |
| **Effort** | 3 (Medium, 8-12 hr) |
| **Dependencies** | ARCH-001 (recommended for `loop.py` — easier after decomposition) |
| **Est. Time** | 8-12 hours |
| **Why Now** | `loop.py` has 19% coverage, `cli.py` has 12%, `status.py` has 26%. These are the three most user-facing modules. Any refactoring or feature work risks undetected regressions. |

**Steps:**

1. **`loop.py`**: Write characterization tests first (capture current behavior without changing it). Test exit-early conditions (sentinel, max iterations, convergence, idle), iteration lifecycle, notification paths.
2. **`cli.py`**: Test all 14+ introspection flags (`--status`, `--doctor`, `--preflight`, `--list-flags`, `--explain`, `--help-topic`). Test config file loading with valid/invalid/missing files.
3. **`status.py`**: Test all rendering paths (running, idle, error, done) with controlled state dicts.

**Files:** `tests/test_loop.py`, `tests/test_cli.py`, new `tests/test_status.py`

---

### Phase 3: Architecture (Weeks 3–6)

---

#### #10: Decompose monolithic `run_loop()` — Phase 1 (ARCH-001)

| Field | Value |
|-------|-------|
| **ID** | ARCH-001 |
| **Value/Effort** | **1.0** (Impact 5 ÷ Effort 5) |
| **Priority** | 🔴 Critical |
| **Impact** | 5 — Largest barrier to all other loop improvements |
| **Effort** | 5 (X-Large, 3-5 days) |
| **Dependencies** | None (Phase 1 is independent) |
| **Est. Time** | 3-5 days (split across phases) |
| **Why Now** | `run_loop()` is 435 lines with 60+ local variables and 20+ condition branches. It has 19% test coverage because mocking 60 variables is impractical. Every new feature touches it, increasing regression risk. Decomposition is the prerequisite for: integration tests (TEST-001), state machine (ARCH-005), structured logging (FEAT-003), and confidence in any loop change. |

**Phase 1 approach (this sprint):**

1. Write characterization tests for `run_loop()` — capture current behavior as test assertions
2. Extract pure functions first (no I/O): convergence check, termination check, progress classification
3. Extract I/O-bound operations: `_emit_notifications()`, `_apply_recovery()`, `_build_dashboard_html()`
4. Each extraction is a separate commit with the characterization test passing before and after
5. Update call sites in `run_loop()` to call extracted functions

**Phase 2 (future sprint):**

1. Extract iteration context preparation into `IterationContext` dataclass
2. Extract subprocess execution into `TaskExecutor` class
3. Extract cooldown logic into `CooldownManager`
4. Main loop body becomes a readable pipeline of extracted functions

**Files:** `pi_loop/loop.py`, new `pi_loop/executor.py`, new `pi_loop/convergence.py`, new `pi_loop/notifications.py`

---

## Execution Timeline

```
Week 1                Week 2                Week 3-4              Week 5-6
────────────────────────────────────────────────────────────────────────────────
┌─────────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌───────────┐
│ #1 status uptime    │  │ #7 shell=True   │  │ #10 run_loop    │  │ #10 cont'd│
│ #2 URL validation   │  │ guardrails      │  │ Phase 1         │  │ Phase 2   │
│ #3 notification log │  ├─────────────────┤  │ (extract pure   │  └───────────┘
│ #4 empty catch blks │  │ #8 structured   │  │  functions)     │
│ #5 config key valid │  │ logging (start) │  └─────────────────┘
│ #6 CI coverage      │  └─────────────────┘
│                     │
│ ALL PARALLELIZABLE  │  ├ #9 loop/cli/    │
│ (no dependencies)   │  │ status tests    │
└─────────────────────┘  └─────────────────┘
```

## Dependencies Map

```
                     ┌───────────────────────────────────┐
                     │                                   │
Phase 1 (independent)│  Phase 2 (parallel)               │  Phase 3 (sequential)
                     │                                   │
#1  BUG-013 ──────┐  │  #7  SEC-005 ──────┐              │
#2  SEC-001  ─────┤  │                    ├── (parallel)  │  #10 ARCH-001
#3  BUG-002  ─────┤  │  #8  FEAT-003 ─────┤              │       │
#4  CLEAN-005 ────┤  │                    │              │       ├── TEST-003
#5  BUG-008  ─────┤  │  #9  TEST-003 ─────┘              │       │   (loop tests)
#6  CI-CD-001 ────┘  │                                   │       └── FEAT-003
                     │                                   │           (structured
                     │                                   │            logging)
                     └───────────────────────────────────┘
```

## Effort Distribution

| Effort | Count | Items |
|--------|-------|-------|
| **1 (Trivial)** | 5 | #1 (BUG-013), #2 (SEC-001), #3 (BUG-002), #4 (CLEAN-005), #5 (BUG-008), #6 (CI-CD-001) |
| **2 (Small)** | 1 | #7 (SEC-005) |
| **3 (Medium)** | 2 | #8 (FEAT-003), #9 (TEST-003) |
| **4 (Large)** | 0 | — |
| **5 (X-Large)** | 1 | #10 (ARCH-001) |

## Value/Effort Heatmap

```
Impact High ─────────────────────────────────────────────────────
            │                                          │
            │  #1 BUG-013 (5.0)                        │
            │  #2 SEC-001  (7.5)                       │  #10 ARCH-001 (1.0)
            │  #3 BUG-002  (4.0)                       │
            │  #5 BUG-008  (3.0)                       │  #9 TEST-003  (1.3)
            │  #7 SEC-005  (3.0)                       │
            │  #6 CI-CD-001(3.0)                       │
            │  #4 CLEAN-005(3.0)                       │  #8 FEAT-003  (1.6)
            │                                          │
            └──────────────────────────────────────────┘
Low Effort                                      High Effort
```

**Sweet spot (top-left quadrant — Phase 1):** Items #1, #2, #3, #4, #5, #6, #7 deliver the most value per unit effort. All can be parallelized.
**Strategic investments (bottom-right — Phase 3):** Items #8, #9, #10 require significant effort but provide foundational improvements that unlock everything else.

## Quick Reference

| Rank | ID | Title | V/E | Phase | Est. Time |
|------|----|-------|-----|-------|-----------|
| 1 | BUG-013 | Fix `status.py` uptime calculation | 5.0 | Week 1 | 15 min |
| 2 | SEC-001 | Validate `http_callback` URL scheme | 7.5 | Week 1 | 30 min |
| 3 | BUG-002 | Log notification/HTTP callback failures | 4.0 | Week 1 | 30 min |
| 4 | CLEAN-005 | Add `console.error()` to empty `catch` blocks | 3.0 | Week 1 | 15 min |
| 5 | BUG-008 | Validate CLI `--config` JSON keys | 3.0 | Week 1 | 30 min |
| 6 | CI-CD-001 | Add coverage reporting to CI | 3.0 | Week 1 | 30 min |
| 7 | SEC-005 | Add guardrails for `shell=True` error command | 3.0 | Week 2 | 1-2 hr |
| 8 | FEAT-003 | Implement structured JSON logging | 1.6 | Week 2 | 4-6 hr |
| 9 | TEST-003 | Cover critical modules (loop, cli, status) | 1.3 | Week 2-3 | 8-12 hr |
| 10 | ARCH-001 | Decompose monolithic `run_loop()` | 1.0 | Week 3-6 | 3-5 days |

## Tracking

- Mark items as 🔄 **In Progress** when started
- Mark as ✅ **Done** when all acceptance criteria are met and verified
- Note blockers with ❌ **Blocked** and the blocking ID
- Re-evaluate priorities quarterly

---

*This plan is designed to be executed sequentially where possible. Items without dependencies can be parallelized. Each item links back to its detailed entry in `ENGINEERING_BACKLOG.md`.*
