# Improvement Plan

Created: 2026-06-28T15:44:00+08:00 | Last updated: 2026-06-28T16:13:00+08:00

## 📊 Progress Summary

| Category      | Completed | Remaining |
|---------------|-----------|-----------|
| 🐛 Bugs       | 2         | 0         |
| 🧪 Tests      | 0         | 0         |
| 📖 Docs        | 0         | 0         |
| 🔧 Refactor   | 2         | 0         |
| ⚡ Perf       | 0         | 0         |
| 🔒 Security   | 1         | 0         |
| ✨ Features   | 0         | 1         |
| 🧹 Hygiene    | 0         | 3         |
| 🌐 Web UI     | 0         | 0         |
| 🏗️ Infra/CI  | 2         | 0         |

## Completed

- **[2026-06-28] [🔒 Security] HMAC-SHA256 webhook signing for `--http-callback`**: Added `--http-callback-secret` CLI flag. When set, every HTTP callback POST includes an `X-Signature-256` header with the hex-encoded HMAC-SHA256 digest of the JSON body. The receiver verifies authenticity by re-computing the signature with the shared secret. Implemented across `cli.py`, `loop.py`, and `iteration.py` — no behaviour change when secret is absent. — commit (unstaged)

- **[2026-06-28] [🐛 Bugs] Fixed `os.sysconf_names` deprecation in `system_utils.py:65-69`**: Replaced two-step `os.sysconf_names.get("SC_CLK_TCK")` → `os.sysconf()` lookup with direct `os.sysconf("SC_CLK_TCK")` call. Simpler, more readable, and avoids any concern about the deprecated `sysconf_names` mapping behavior on Python 3.14+. — commit (unstaged)
- **[2026-06-28] [🐛 Bugs] Added depth limit + cycle detection to `validation.py:_validate`**: Added `_MAX_VALIDATION_DEPTH=50` depth cap and identity-based cycle detector (`(id(schema_node), id(obj))` pairs) to prevent stack overflow from deeply nested or self-referencing schemas. All 12 self-tests pass with no regressions. — commit (unstaged)
- **[2026-06-28] [🏗️ Infra/CI] Fixed broken `make test` and `make check` targets**: Removed `pytest tests/` command from Makefile, replaced `make test` to delegate to `make self-test`. Removed `[tool.pytest.ini_options]` from pyproject.toml. Removed `tests/` from ruff lint paths. Updated `make check` step 2 to skip `make test` and just run `make self-test`. — commit (unstaged)
- **[2026-06-28] [🔧 Refactor] `preflight.py` — `run_all()` delegates to `run_all_checks()`**: The instance method `run_all()` now delegates to the static `run_all_checks()` instead of duplicating the same check list. `_read_heartbeat` optimized to use `json.load(f)` directly. `import glob` moved to module top level in `heartbeat.py`. — commit fc9fd35
- **[2026-06-28] [🔧 Refactor] `_monitor_heartbeat` batch-reads heartbeat file**: Caches heartbeat data and mtime, only re-opens/parses the file when mtime changes — eliminates redundant `_read_heartbeat` I/O on every poll cycle. — commit (unstaged)

## Backlog (prioritized — highest impact first)

<!-- Add findings here during research iterations -->

### 🐛 Bugs Found

*(All identified bugs are now fixed — see Completed above.)*

### 🧪 Test Gaps

*(No test gaps — pytest tests were intentionally removed in b60539f. Self-tests cover 12 groups.)*

### 📖 Documentation Gaps

*(None found during scan.)*

### 🔧 Refactoring Candidates

*(All identified refactoring candidates are now addressed — see Completed above.)*

### ⚡ Performance Issues

*(None found during scan.)*

### 🔒 Security Concerns

*(All identified security concerns are now addressed — see Completed above.)*

### ✨ Missing Features / Enhancements

- **`hermes_loop/notifications.py` — No webhook body signing**: Pushbullet and ntfy notifications send API tokens and topics in URL form. No HMAC signing for webhook payloads.

### 🧹 Code Hygiene (lint, types, dead code, imports)

- **`hermes_loop/preflight.py:149` — `import socket as _sock`** inside method body: Should be at module top level for consistency with other stdlib imports.
- **`hermes_loop/library_worker.py:106-108` — `import concurrent.futures as _cf`** inside try block inside function: Should be at module top level.

### 🌐 Web UI / Frontend (web_app/, dashboard.py)

*(None found during scan.)*

### 🏗️ Build / CI / Infra

~~All 4 items fixed — see Completed section above.~~
