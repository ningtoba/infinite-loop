# Improvement Plan

Created: 2026-06-28T15:44:00+08:00 | Last updated: 2026-06-28T15:46:00+08:00

## 📊 Progress Summary

| Category      | Completed | Remaining |
|---------------|-----------|-----------|
| 🐛 Bugs       | 0         | 1         |
| 🧪 Tests      | 0         | 0         |
| 📖 Docs        | 0         | 0         |
| 🔧 Refactor   | 0         | 2         |
| ⚡ Perf       | 0         | 0         |
| 🔒 Security   | 0         | 0         |
| ✨ Features   | 0         | 1         |
| 🧹 Hygiene    | 0         | 3         |
| 🌐 Web UI     | 0         | 0         |
| 🏗️ Infra/CI  | 0         | 2         |

## Completed

<!-- Move items here when done. Format: [DATE] [CATEGORY] Description — commit <hash> -->

## Backlog (prioritized — highest impact first)

<!-- Add findings here during research iterations -->

### 🐛 Bugs Found

- **`hermes_loop/system_utils.py:65-69` — `os.sysconf_names.get("SC_CLK_TCK")` uses deprecated API**: `os.sysconf_names` was deprecated in Python 3.13 and removed in 3.14. Use `os.sysconf_names` directly (it's a mapping) or hardcode 100 as fallback. This will crash on Python 3.14+.
- **`hermes_loop/validation.py` — Recursive validation doesn't handle circular references**: `_validate` calls itself recursively for nested objects with `"properties"` in field_schema but has no depth limit or cycle detection. A deeply nested schema can cause stack overflow.

### 🧪 Test Gaps

*(No test gaps — pytest tests were intentionally removed in b60539f. Self-tests cover 12 groups.)*

### 📖 Documentation Gaps

*(None found during scan.)*

### 🔧 Refactoring Candidates

- **`hermes_loop/heartbeat.py` — `_monitor_heartbeat` IO with GIL**: `_write_heartbeat_file` does file I/O inside the hot loop. For a daemon thread, this is fine, but the `_read_heartbeat` call on every poll cycle does JSON parsing and file open — could batch reads.
- **`hermes_loop/preflight.py` — Duplicated check list between `run_all()` and `run_all_checks()`**: Both instance method and static method duplicate the same list of checks. One should delegate to the other.

### ⚡ Performance Issues

*(None found during scan.)*

### 🔒 Security Concerns

*(None found during scan — no eval/exec, no shell injection paths, no credential logging.)*

### ✨ Missing Features / Enhancements

- **`hermes_loop/notifications.py` — No webhook body signing**: Pushbullet and ntfy notifications send API tokens and topics in URL form. No HMAC signing for webhook payloads.

### 🧹 Code Hygiene (lint, types, dead code, imports)

- **`hermes_loop/preflight.py:150` — `import socket as _sock`** inside method body: Should be at module top level for consistency with other stdlib imports.
- **`hermes_loop/heartbeat.py:187` — `import glob` inside function body**: Should be at module top level.
- **`hermes_loop/library_worker.py:106-108` — `import concurrent.futures as _cf` inside try block inside function**: Should be at module top level.

### 🌐 Web UI / Frontend (web_app/, dashboard.py)

*(None found during scan.)*

### 🏗️ Build / CI / Infra

- **`Makefile:138-139` — `make test` references deleted `tests/` directory**: Since b60539f removed all 33 pytest test files, `make test` now fails with `pytest: error: unrecognized arguments: tests/`. Should either remove the target or skip it gracefully.
- **`Makefile:231-233` — `make check` step 2 tries to run `make test` which fails**: Same root cause — references deleted test files. `make check` is now broken.
- **`pyproject.toml:23-28` — `[tool.pytest.ini_options]` references deleted `tests/` path**: Should be removed or updated since tests directory no longer exists.
- **`Makefile:286` — `ruff check` still references `tests/` directory**: The lint target runs `ruff check hermes_loop/ web_app/ tests/ ...` but `tests/` no longer exists. Currently harmless (ruff ignores missing dirs) but should be cleaned up.
