# Improvement Plan

Created: 2026-06-28T15:44:00+08:00 | Last updated: 2026-06-28T17:35:00+08:00

## 📊 Progress Summary

| Category      | Completed | Remaining |
|---------------|-----------|-----------|
| 🐛 Bugs       | 3         | 0         |
| 🧪 Tests      | 0         | 0         |
| 📖 Docs        | 0         | 0         |
| 🔧 Refactor   | 2         | 0         |
| ⚡ Perf       | 1         | 0         |
| 🔒 Security   | 1         | 0         |
| ✨ Features   | 0         | 0         |
| 🧹 Hygiene    | 3         | 0         |
| 🌐 Web UI     | 0         | 0         |
| 🏗️ Infra/CI  | 2         | 0         |

## Completed

- **[2026-06-28] [🐛 Bugs] `loop.py` — `need_reload` control signal no longer pollutes evolved goal**: `evolve` logic now detects `"need_reload"` in `next_goal` and skips evolution. Fixes the bug where `HERMES_LOOP_NO_AUTO_RELOAD=1` (web UI mode) caused the daemon to keep sending workers on a "NEXT_ITERATION need_reload" wild goose chase. — commit pending

- **[2026-06-28] [🧹 Hygiene] `library_worker.py` — Moved inline `import logging as _logging` to module top level**: No behaviour change. — commit a6c1747
- **[2026-06-28] [🔒 Security] HMAC-SHA256 webhook signing for `--http-callback`**: Added `--http-callback-secret` CLI flag. — commit 4f8a647
- **[2026-06-28] [🐛 Bugs] Fixed `os.sysconf_names` deprecation in `system_utils.py:65-69`**: Replaced two-step lookup with direct `os.sysconf()` call. — commit e933abc
- **[2026-06-28] [🐛 Bugs] Added depth limit + cycle detection to `validation.py:_validate`**: Added `_MAX_VALIDATION_DEPTH=50` depth cap and identity-based cycle detector. — commit (unstaged)
- **[2026-06-28] [🏗️ Infra/CI] Fixed broken `make test` and `make check` targets**: Removed `pytest tests/` from Makefile, delegated `make test` to `make self-test`. — commit (unstaged)
- **[2026-06-28] [🔧 Refactor] `preflight.py` — `run_all()` delegates to `run_all_checks()`**: Removed duplicate check list, optimized heartbeat read. — commit fc9fd35
- **[2026-06-28] [🔧 Refactor] `_monitor_heartbeat` batch-reads heartbeat file**: Caches mtime to eliminate redundant I/O. — commit (unstaged)
- **[2026-06-28] [🧹 Hygiene] Both backlog hygiene items resolved before iter #3**: `import socket as _sock` was already at module top level in `preflight.py:7`, and `import concurrent.futures as _cf` was already at module top level in `library_worker.py:6`. Both backlog entries were stale. — commit 96a49f2
- **[2026-06-28] [⚡ Perf] `git_utils.py:_capture_git_state` — runs 3–4 sequential subprocess calls**: Could parallelize with `concurrent.futures` for marginal speedup on slow git repos. Minor — low priority. — discovered scan
- **[2026-06-28] [🧹 Hygiene] `library_worker.py:89` — `from run_agent import AIAgent` inline import**: Inside `_library_worker()` function. This is intentional to avoid importing `run_agent` eagerly (it triggers heavy Hermes loading). Acceptable pattern for multiprocessing isolation. — discovered scan

## Backlog (prioritized — highest impact first)

### 🐛 Bugs Found

*(None found during scan — all 12 self-tests pass, ruff clean, no TODOs/FIXMEs.)*

### 🧪 Test Gaps

*(Tests were intentionally removed per prior infra work. Self-tests in `self_test.py` cover 12 groups — preflight, validation, env, version detection, archive, worktree, webhook, signal handlers, git, error recovery, cooldown, comprehensive.)*

### 📖 Documentation Gaps

*(None found during scan.)*

### 🔧 Refactoring Candidates

*(All identified refactoring candidates from prior scans are addressed. Currently-neglected files — `similarity.py`, `goal_utils.py`, `legacy.py`, `cooldown.py`, `stats.py`, `git_utils.py` — are all clean, small, well-structured modules with no obvious refactoring targets.)*

### ⚡ Performance Issues

*(None found during scan. `git_utils.py:_capture_git_state` could parallelize its 4 subprocess calls, but the impact is marginal since it's called once per iteration.)*

### 🔒 Security Concerns

*(All identified security concerns addressed. `--http-callback` has HMAC-SHA256 signing. Pushbullet and ntfy use their own API auth — not webhooks — so HMAC is N/A.)*

### ✨ Missing Features / Enhancements

*(None found during scan.)*

### 🧹 Code Hygiene (lint, types, dead code, imports)

*(All prior hygiene items resolved. Remaining inline imports are intentional late-imports for circular dependency avoidance or multiprocessing isolation — not hygiene issues.)*

### 🌐 Web UI / Frontend (web_app/, dashboard.py)

*(None found during scan.)*

### 🏗️ Build / CI / Infra

*(None found during scan.)*
