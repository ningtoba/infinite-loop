# Action Plan — Top 10 Prioritized Items

> Execution plan for pi-loop v14.39.0 engineering backlog.
> Items ranked by **value/effort ratio** and ordered for minimal blocking dependencies.
> Generated: 2026-06-30

---

## Ranking Methodology

Each item is scored on a **Value/Effort** ratio using:

- **Value** = Impact (1–5) × Urgency Multiplier  
  - Security/Critical = 1.5×  
  - Performance = 1.2×  
  - Quality = 1.0×  
  - Polish = 0.8×  
- **Effort** = 1 (trivial) to 5 (XLarge)

The top 10 items maximize engineering ROI — fixing things that hurt the most with the least effort first.

---

## Top 10 Execution Plan

### Phase 1: Foundation Fixes (Weeks 1–2)

These are high-impact, low-effort items that should be addressed immediately.

---

#### 🥇 #1: Wire mypy to actually fail CI

| Field | Value |
|-------|-------|
| **ID** | CICD-001 |
| **Value/Effort** | 4.0 (Impact 4 × 1.0 Quality / Effort 1) |
| **Priority** | 🟠 High |
| **Effort** | 2 / 5 (Medium) |
| **Dependencies** | None |
| **Est. Time** | 1–2 hours |
| **Why Now** | Type checking is the cheapest bug-prevention strategy. Currently it's silently disabled — catching nothing. |

**Steps:**

1. Remove `|| true` and `; true` from `Makefile` `mypy` target
2. Run `make mypy` locally and catalog all current errors
3. Fix or suppress (with `# type: ignore[code]`) each error
4. Update `.github/workflows/ci.yml` to run mypy as a gating step
5. Consider enabling `disallow_untyped_defs = true` for newly written code

**Files:** `Makefile`, `.github/workflows/ci.yml`, multiple `.py` files for fixes

---

#### 🥈 #2: Audit API auth endpoint coverage

| Field | Value |
|-------|-------|
| **ID** | SEC-001 |
| **Value/Effort** | 6.0 (Impact 4 × 1.5 Security / Effort 1) |
| **Priority** | 🟠 High |
| **Effort** | 1 / 5 (Small) |
| **Dependencies** | None |
| **Est. Time** | 30 min |
| **Why Now** | Recently added auth middleware needs verification that it actually protects everything. Cheap audit. |

**Steps:**

1. Enumerate all routes in `server.py`
2. Test each POST/PUT/DELETE endpoint without auth header — verify it's rejected
3. Test auth-disable path (config or flag)
4. Verify API key is not logged anywhere
5. Verify static files and error pages don't leak the key
6. Write parametrized test (see TEST-005)

**Files:** `web_app/server.py`, `tests/test_auth.py`

---

#### 🥉 #3: Fix empty catch blocks in `app.js`

| Field | Value |
|-------|-------|
| **ID** | CLEAN-005 |
| **Value/Effort** | 3.0 (Impact 3 × 1.0 Quality / Effort 1) |
| **Priority** | 🟡 Medium |
| **Effort** | 1 / 5 (Small) |
| **Dependencies** | None |
| **Est. Time** | 15 min |
| **Why Now** | Frontend errors are completely invisible. A single `console.error()` per catch block makes debugging possible. |

**Steps:**

1. Search for `catch` blocks in `app.js` (5+ empty ones)
2. Add `console.error('Error [descriptive label]:', e)` to each
3. Optionally add user-visible toast for critical errors

**Files:** `web_app/static/app.js`

---

#### #4: Add coverage reporting to CI

| Field | Value |
|-------|-------|
| **ID** | CICD-004 |
| **Value/Effort** | 2.5 (Impact 3 × 1.0 Quality / Effort 1.2) |
| **Priority** | 🟡 Medium |
| **Effort** | 1 / 5 (Small) |
| **Dependencies** | None |
| **Est. Time** | 30 min |
| **Why Now** | pytest-cov is installed but unused. Knowing coverage on every PR prevents regressions. |

**Steps:**

1. Add `--cov=pi_loop --cov=web_app --cov-report=term-missing` to `make test`
2. Add coverage step to CI `test` job
3. Set minimum coverage threshold (e.g., 65%) to prevent drops

**Files:** `Makefile`, `.github/workflows/ci.yml`

---

### Phase 2: Observability & Testing (Weeks 2–4)

These items build on the foundation to make the system observable and verifiable.

---

#### #5: Implement structured logging

| Field | Value |
|-------|-------|
| **ID** | FEAT-003 |
| **Value/Effort** | 4.8 (Impact 4 × 1.2 Performance / Effort 1) |
| **Priority** | 🟠 High |
| **Effort** | 3 / 5 (Medium) |
| **Dependencies** | None |
| **Est. Time** | 4–6 hours |
| **Why Now** | Without structured logging, production debugging is manual log scraping. Correlation IDs enable tracing iterations end-to-end. |

**Steps:**

1. Replace all `print()` calls with `structlog` or stdlib `logging` with JSON formatter
2. Define log levels: DEBUG (diagnostics), INFO (normal), WARNING (recoverable), ERROR (failures)
3. Add correlation/iteration/loop IDs to every log line
4. File output: JSON format for aggregators (Loki, ELK)
5. Console output: human-readable format
6. Consistent structured fields: `event`, `iteration`, `duration_ms`, `error_type`

**Files:** `pi_loop/loop.py`, `pi_loop/error_recovery.py`, `pi_loop/git_utils.py`, `pi_loop/heartbeat.py`, `pi_loop/preflight.py`, `web_app/server.py`

---

#### #6: Cover critical modules — `loop.py`, `cli.py`, `status.py`

| Field | Value |
|-------|-------|
| **ID** | TEST-003 |
| **Value/Effort** | 2.4 (Impact 4 × 1.0 Quality / Effort 1.67) |
| **Priority** | 🟠 High |
| **Effort** | 3 / 5 (Medium) |
| **Dependencies** | ARCH-001 (partially — loop tests easier after decomposition) |
| **Est. Time** | 8–12 hours |
| **Why Now** | The core loop and CLI entry point are the most critical code paths and have the lowest coverage. |

**Steps:**

1. **`loop.py`**: Test exit-early conditions (sentinel, max turns, convergence, idle, goal exhausted), iteration lifecycle, notification paths, error/scenario handling
2. **`cli.py`**: Test all 14+ flag combinations, help/doctor/preflight/status/invoke commands, flag interaction errors
3. **`status.py`**: Test all rendering paths (active, idle, error, done) with controlled state dicts

**Files:** `tests/test_loop.py`, `tests/test_cli.py`, `tests/test_status.py`

---

### Phase 3: Architecture & Engineering (Weeks 3–6)

These are the high-impact, higher-effort items that improve the system's structural integrity.

---

#### #7: Decompose monolithic `run_loop()` — Phase 1 (Extract helpers)

| Field | Value |
|-------|-------|
| **ID** | ARCH-001 |
| **Value/Effort** | 3.0 (Impact 5 × 1.0 Quality / Effort 1.67) |
| **Priority** | 🔴 Critical |
| **Effort** | 5 / 5 (XLarge) |
| **Dependencies** | None (can start with Phase 1 independently) |
| **Est. Time** | 3–5 days (split across phases) |
| **Why Now** | Decomposing `run_loop()` unlocks all other loop improvements — testability, error handling, concurrency. The LoopConfig dataclass was the prerequisite; now decompose the body. |

**Phase 1 approach (this sprint):**

1. Extract pure functions first (no IO): convergence check, termination check, progress classification
2. Extract _emit_notifications, _apply_recovery, _build_dashboard_html
3. Write unit tests for each extracted function before touching it (characterization tests)
4. Each extraction is a separate commit for clean review

**Phase 2 (future sprint):**

1. Extract IterationContext preparation
2. Extract subprocess execution into TaskExecutor
3. Refactor main loop body to call extracted functions

**Files:** `pi_loop/loop.py`, new `pi_loop/executor.py`, `pi_loop/orchestrator.py`, `pi_loop/reporter.py`

---

#### #8: Fix config corruption notification + atomic writes

| Field | Value |
|-------|-------|
| **ID** | BUG-001 |
| **Value/Effort** | 3.0 (Impact 3 × 1.0 Quality / Effort 1) |
| **Priority** | 🟡 Medium |
| **Effort** | 1 / 5 (Small) |
| **Dependencies** | None |
| **Est. Time** | 1–2 hours |
| **Why Now** | Silent data loss with no feedback — users lose custom config without knowing. |

**Steps:**

1. Add `corrupt: true` flag to config API response when defaults are used
2. Show warning banner in web UI HTML when `corrupt` is true
3. Log at WARNING level with corrupt file path
4. Implement atomic write pattern: write to `.config.json.tmp`, then `os.rename()`

**Files:** `pi_loop/config_file.py`, `web_app/config_manager.py`, `web_app/static/app.js`, `web_app/static/index.html`

---

#### #9: SSE reconnect with exponential backoff

| Field | Value |
|-------|-------|
| **ID** | PERF-003 |
| **Value/Effort** | 2.4 (Impact 2 × 1.2 Performance / Effort 1) |
| **Priority** | 🟡 Medium |
| **Effort** | 1 / 5 (Small) |
| **Dependencies** | None |
| **Est. Time** | 30 min |
| **Why Now** | Prevent thundering-herd on server restart. Simple change, high reliability impact. |

**Steps:**

1. Replace fixed 5s delay with exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
2. Add ±25% random jitter to prevent synchronized reconnects
3. Reset backoff to minimum on successful SSE connection
4. Merge into `sse.js` when CLEAN-001 is done

**Files:** `web_app/static/app.js`

---

#### #10: Integration tests for subprocess lifecycle

| Field | Value |
|-------|-------|
| **ID** | TEST-001 |
| **Value/Effort** | 1.6 (Impact 4 × 1.0 Quality / Effort 2.5) |
| **Priority** | 🟠 High |
| **Effort** | 5 / 5 (XLarge) |
| **Dependencies** | ARCH-001 (recommended — easier isolation after decomposition) |
| **Est. Time** | 2–3 days |
| **Why Now** | The core value proposition (subprocess task execution) has zero end-to-end verification. |

**Steps:**

1. Create `tests/integration/` with conftest fixtures
2. Build `mock_pi.sh` — shell script emitting realistic NDJSON output
3. Test single iteration end-to-end
4. Test multi-iteration convergence detection
5. Test error recovery with injected subprocess failures
6. Test sentinel-based stop/pause
7. Test web UI endpoints interacting with a running daemon

**Files:** `tests/integration/` (new directory), `tests/integration/conftest.py`, `tests/integration/mock_pi.sh`, `tests/integration/test_subprocess_lifecycle.py`, `tests/integration/test_web_daemon.py`

---

## Execution Timeline

```
Week 1          Week 2          Week 3          Week 4          Week 5-6
──────────────────────────────────────────────────────────────────────────────
#1 mypy CI    ├── #5 logging  ├── #7 run_loop ├── #7 cont'd   ├── #10 integ.
#2 auth audit |               |   Phase 1     |               |   tests
#3 catch blks |── #6 coverage |               ├── #9 SSE      |
#4 CI coverage|   (loop/cli/  ├── #8 config   |   backoff     |
              |    status)    |   atomic write |               |
              |               |               |               |
```

## Dependencies Map

```
#1 mypy CI        ─────────► #5 structured logging  ──► #7 run_loop decomposition
                                                    │      │
#2 auth audit ◄──► TEST-005 (parametrized auth test) │      │
                                                    │      ▼
#3 catch blocks   ─────────► CLEAN-001 (JS modules)  │  #10 integration tests
                                                    │
#4 CI coverage    ─────────► #6 loop/cli/status tests
                                                    │
#8 config atomic  ─────────► (independent)
                                                    │
#9 SSE backoff    ─────────► CLEAN-001 (JS modules)
```

## Effort Estimates for All 42 Items

| Effort | Count | Items |
|--------|-------|-------|
| **1 (Trivial)** | 10 | BUG-004, TOOL-002, TOOL-003, TOOL-004, TOOL-005, CLEAN-004, CLEAN-005, CLEAN-006, CICD-002, CICD-005 |
| **2 (Small)** | 14 | BUG-001, BUG-002, BUG-003, BUG-005, PERF-001, PERF-003, SEC-001, SEC-002, TEST-002, TEST-005, CICD-001, DOC-001, DOC-003, FEAT-004 |
| **3 (Medium)** | 11 | ARCH-004, ARCH-005, PERF-002, TEST-004, CLEAN-001, CLEAN-002, CLEAN-003, CICD-004, FEAT-001, FEAT-002, FEAT-003 |
| **4 (Large)** | 4 | ARCH-002, ARCH-003, TEST-003, FEAT-005 |
| **5 (XLarge)** | 4 | ARCH-001, TEST-001, TOOL-006, CICD-003 |

## Value/Effort Heatmap

```
High Impact ─────────────────────────────────────────────────────
            │                                          │
            │  #2 SEC-001 (6.0)                        │  #7 ARCH-001 (3.0)
            │  #5 FEAT-003 (4.8)                       │  #1 CICD-001 (4.0)
            │  #10 TEST-001 (3.2)                      │  #6 TEST-003 (2.4)
            │                                          │
            │  #3 CLEAN-005 (3.0)                      │  #9 PERF-003 (2.4)
            │  #8 BUG-001 (3.0)                        │  #4 CICD-004 (2.5)
            │                                          │
Low Effort ───────────────────────────────────────────────────── High Effort
```

**Sweet spot (top-right quadrant):** Items #1, #2, #3, #5, #8 deliver the most value per unit effort.
**Strategic investments (bottom-right):** Items #7, #10, #6 require significant effort but provide foundational improvements.

---

## Tracking

- Mark items as 🔄 **In Progress** when started
- Mark as ✅ **Done** when all acceptance criteria are met and verified
- Note blockers with ❌ **Blocked** and the blocking ID
- Re-evaluate priorities quarterly

---

*This plan is designed to be executed sequentially where possible. Items without dependencies can be parallelized. Each item links back to its detailed entry in `ENGINEERING_BACKLOG.md`.*
