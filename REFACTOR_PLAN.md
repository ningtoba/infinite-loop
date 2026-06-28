# Code & Docs Refactor — Concrete File-by-File Plan

Based on three independent code reviews covering all 36 Python modules in `hermes_loop/` plus root config files.

## Decisions Summary

| Category | Count | Files |
|----------|-------|-------|
| **REMOVE** (5) | 5 | `worker_manager.py`, `library_worker.py`, `iteration.py`, `wizard.py`, `legacy.py` |
| **REWRITE** (18) | 18 | `cli.py`, `hermes_utils.py`, `config.py`, `state.py`, `preflight.py`, `loop.py`, `completions.py`, `error_utils.py`, `signal_handlers.py`, `worktree_merger.py`, `diagnosis.py`, `self_test.py`, `__init__.py`, `__main__.py`, `archiving.py`, `dashboard.py`, `webhook.py`, `notifications.py` |
| **KEEP as-is** (13) | 13 | `color_utils.py`, `env_utils.py`, `error_recovery.py`, `file_utils.py`, `file_watcher.py`, `functions.py`, `git_utils.py`, `heartbeat.py`, `similarity.py`, `cooldown.py`, `stats.py`, `system_utils.py`, `tracker.py`, `validation.py` |

---

## PHASE 1: Removal (5 files)

These files are Hermes-agent-only and have no place in a generic loop daemon.

### 1. `hermes_loop/worker_manager.py` — REMOVE

- **Why**: Entire file is Hermes MCP Worker subprocess lifecycle management. Spawns `~/.hermes/plugins/hermes-mcp-worker/main.py` via `subprocess.Popen`.
- **Impact**: No other file depends on it (iteration.py, which used it, is also removed).

### 2. `hermes_loop/library_worker.py` — REMOVE

- **Why**: Imports `AIAgent` from Hermes' `run_agent` package to run in-process via multiprocessing. Pure Hermes library-mode worker.
- **Impact**: No other file depends on it.

### 3. `hermes_loop/iteration.py` — REMOVE

- **Why**: Core Hermes session orchestrator. Imports `_build_delegation_prompt` and `spawn_delegation_session` from `.hermes_utils`, `_run_library_workers_parallel` from `.library_worker`. Docstring references "Hermes sessions". Calls `hermes chat -q` indirectly. Entire orchestration layer has nothing to orchestrate without Hermes.
- **Impact**: Removes the iteration engine. The new launcher (e.g., pi-worker based) will replace this.

### 4. `hermes_loop/wizard.py` — REMOVE

- **Why**: Interactive first-time setup wizard. Checks for `hermes` binary, prints `hermes_loop` CLI commands, references `hermes_loop --status`, `hermes_loop --help`. Generates `.env` with `INFINITE_LOOP_*` vars. Hermes-centric CLI examples throughout.

### 5. `hermes_loop/legacy.py` — REMOVE

- **Why**: Pure backward-compat shim for `from hermes_loop import *`. Re-exports from `config.py`, `file_utils.py`, `signal_handlers.py` (including `_hermes_worker_ref`). If no external code still does `from hermes_loop.legacy import X`, this is dead code. After package rename, it would break anyway.

---

## PHASE 2: Rewrite (18 files)

These files need content changes — renaming strings, updating references, restructuring.

### 6. `hermes_loop/__init__.py` — REWRITE (package rename)

- Update module docstring from `"hermes_loop"` to `"infinite_loop"` (or new package name)
- Update `from .config import LAUNCH_LOOP_VERSION` (constant rename: `LAUNCH_LOOP_VERSION` → `VERSION` or keep as-is)
- Update `__all__` if needed

### 7. `hermes_loop/__main__.py` — REWRITE (docstring rename)

- Update `"""hermes_loop entry point."""` → `"""infinite_loop entry point."""`

### 8. `hermes_loop/cli.py` — REWRITE (major simplification)

- Extract `_list_flags()`, `_list_examples()`, `_run_healthcheck()`, `_explain_flag()`, `_help_topic()`, `_run_demo()`, `_simulate_demo_output()` into separate `help_topics.py` module.
- Strip CLI-example strings (hardcoded command blocks in `_list_examples()`).
- Replace Hermes-specific defaults (profile, provider, spawn-source) with generic/pi equivalents.
- Update `hermes_loop` references in help text to new CLI command name.
- Keep only argparse setup and `main()` entry point.

### 9. `hermes_loop/hermes_utils.py` — REWRITE (major restructuring)

This is the Hermes bridge — needs the most surgery.

**Changes:**

- Move `find_hermes()` → `preflight.py` (discovery with version checks).
- Extract `AIAgent` library-mode fallback (the `run_agent` import + `spawn_delegation_session` library path) into `library_mode.py` — BUT since `library_worker.py` is being removed, the library mode path should be redesigned to spawn pi-worker sessions instead.
- The `_build_delegation_prompt()` function needs complete rewriting to build prompts for pi-worker instead of Hermes sessions.
- `_run_hermes_with_pty()` → replace with `_run_worker_with_pty()` (or subprocess call to pi).
- Heartbeat + PTY reading code could live in a `spawn_utils.py` module.
- Rename file from `hermes_utils.py` to `worker_utils.py` or `spawn_utils.py`.

### 10. `hermes_loop/config.py` — REWRITE (constants refresh)

- Rename `LAUNCH_LOOP_VERSION` → `VERSION` for clarity (or keep as alias).
- Sync version string (currently `"14.39.0"`, file header says `v14.39.4`).
- Move `_ERROR_SEVERITY` and `_ERROR_THRESHOLDS` into `error_recovery.py` where they're consumed.
- Remove `HERMES_SESSION_TIMEOUT` if no longer needed.
- Add any new pi-worker related constants.

### 11. `hermes_loop/state.py` — REWRITE (version dynamic)

- The hardcoded `"version": "v11"` in the fresh-ledger dict should read from `VERSION` dynamically.
- No structural changes needed; this is a one-line fix.

### 12. `hermes_loop/preflight.py` — REWRITE (consolidate checks)

- Move `find_hermes()` from `hermes_utils.py` into this module (discovery belongs with version checks).
- Remove `_HERMES_FLAG_MIN_VERSIONS` static dict (only gates `--session-timeout` which is always false — whole version-gating mechanism is dead).
- Simplify `PreflightChecker`: pick either static methods or instance method design (currently mixed).
- Update checks to validate pi binary instead of hermes binary.

### 13. `hermes_loop/loop.py` — REWRITE (replace engine)

- This is the main loop engine. It currently imports `detect_task_type` from `hermes_utils` and prints `hermes_loop --goal` examples in `_print_shutdown_summary()`.
- Move inline example strings from `_print_shutdown_summary()` into config constants.
- The function already has too many parameters (~70) — consider bundling a config dataclass.
- Replace Hermes spawn logic with pi-worker spawn logic.
- Update shutdown summary references.

### 14. `hermes_loop/completions.py` — REWRITE (rename symbols)

- `_hermes_loop_completions` → `_infinite_loop_completions`
- `_hermes_loop_dispatch` → `_infinite_loop_dispatch`
- Docstring references: `hermes_loop` → `infinite-loop`
- Shell script comments referencing `hermes_loop` → `infinite-loop`
- The generated bash/zsh scripts already call the daemon "infinite-loop" in comments — just need function renames.

### 15. `hermes_loop/error_utils.py` — REWRITE (string cleanup)

- Line 74: `"hermes exit"` → `"process exit"`
- Line 167: `~/.hermes/config.yaml` → `~/.config/infinite-loop/config.yaml` (or remove reference)

### 16. `hermes_loop/signal_handlers.py` — REWRITE (rename vars/env)

- `_hermes_worker_ref` → `_worker_ref`
- `HERMES_LOOP_NO_AUTO_RELOAD` env var → `INFINITE_LOOP_NO_AUTO_RELOAD`
- Docstrings: `-m hermes_loop` → new package name

### 17. `hermes_loop/worktree_merger.py` — REWRITE (rename patterns/docs)

- Git branch pattern `"hermes/*"` → `"worktree/*"` (or keep both for backward compat)
- All docstrings/comments: replace "Hermes" with "worker"
- Log messages `[WORKTREE-MERGE]` prefix content — update references

### 18. `hermes_loop/diagnosis.py` — REWRITE (rename paths/refs)

- `hermes_loop --doctor` → `infinite-loop --doctor`
- `~/.hermes/` paths → `~/.config/infinite-loop/`
- `HERMES_GATEWAY_PORT` → `INFINITE_LOOP_GATEWAY_PORT`
- Binary check labels: "hermes" → "worker agent" or generic
- `~/.hermes/plugins/hermes-mcp-worker/` → remove or genericize

### 19. `hermes_loop/self_test.py` — REWRITE (rename mock paths)

- All `hermes_loop.file_utils.*` / `hermes_loop.cli` mock patches → update to new package name
- Test case labels referencing "hermes" binary/version → update
- `_FakeResult.stdout` values: remove "hermes" mentions

### 20. `hermes_loop/archiving.py` — REWRITE (default path)

- Default archive dir `~/.hermes/infinite-loop-archives` → `~/.config/infinite-loop/archives`

### 21. `hermes_loop/dashboard.py` — REWRITE (if it references hermes)

- Check for any hermes references in docstrings/HTML templates. Likely cosmetic only.

### 22. `hermes_loop/webhook.py` — REWRITE (if it references hermes)

- Check for any hermes references. Likely cosmetic only.

### 23. `hermes_loop/notifications.py` — REWRITE (if it references hermes)

- Check for any hermes references. Likely cosmetic only.

---

## PHASE 3: Keep As-Is (14 files)

These files contain pure stdlib logic with zero Hermes references. No changes needed.

| File | What it does |
|------|-------------|
| `color_utils.py` | ANSI color utilities — module-level singleton |
| `env_utils.py` | Env var parsing, validation, fuzzy matching |
| `error_recovery.py` | Error classification, adaptive backoff, recovery |
| `file_utils.py` | File locking, ledger I/O, logging, JSON extraction |
| `file_watcher.py` | Directory polling trigger via os.stat() |
| `functions.py` | Goal loading, startup banner, cooldown display |
| `git_utils.py` | Git state capture, auto-commit |
| `heartbeat.py` | Session self-healing heartbeat |
| `similarity.py` | Jaccard word overlap, convergence check |
| `cooldown.py` | Adaptive cooldown calculation |
| `stats.py` | State metrics recalculation |
| `system_utils.py` | /proc-based CPU/memory tracking |
| `tracker.py` | ETA tracker for iteration timing |
| `validation.py` | JSON Schema validator (stdlib-only) |

---

## PHASE 4: Config & Root Files (5 files)

### 24. `Makefile` — REWRITE

- **Remove**: `install` and `install-dev` targets (or update to new package name)
- **Remove**: `run`, `dry-run`, `demo` targets that reference deleted scripts
- **Remove**: `init`/`wizard` target (wizard.py removed)
- **Remove**: `self-test` entries referencing `run.sh`
- **Update**: All `$(PYTHON) -m hermes_loop` commands → new package name
- **Update**: `help` header text
- **Update**: `lint` target — remove references to deleted files
- **Update**: `completion` target — update package name
- **Remove**: `update-completions` target's `scripts/completion/` paths (scripts dir deleted)
- **Simplify**: Remove `check`, `pre-commit` targets or make them work without deleted files
- **Keep**: `env`, `status`, `log`, `stop`, `pause`, `resume`, `clean` targets (they reference `/tmp/infinite-loop-*` paths which are already generic)

### 25. `pyproject.toml` — REWRITE

- `name = "hermes-loop"` → `name = "infinite-loop"` (or new name)
- Update `description` field
- `[project.scripts]`: `hermes_loop = "hermes_loop.cli:main"` → new command name and package
- Remove `hermes_loop_web = "web_app.server:main"` (web_app/ deleted)
- `[tool.setuptools.packages.find]`: remove `"web_app*"` from include
- Remove `[tool.coverage.run]` section referencing `web_app`
- Remove `[tool.hermes_loop]` section (hermes-specific metadata)

### 26. `README.md` — REWRITE (complete rewrite)

- Remove all Hermes-centric content: "Origin" section, "Hermes Agent" references
- Remove Docker deployment section (docker files deleted)
- Remove "Web UI" section (web_app/ deleted)
- Remove "Two Modes" referencing `session-self-loop.py` and `launch-loop.py`
- Remove all `run.sh` references (deleted)
- Remove changelog history (CHANGELOG.md deleted) — or keep as condensed
- Rewrite "How It Works" to explain pi-worker orchestration instead of Hermes chat
- Update architecture diagram
- Remove feature deep-dive sections for deleted features: Hermes Worker Mode, AIAgent Library Mode, Session Self-Healing Heartbeat (if heartbeat.py kept, keep that section)
- Update all CLI flag examples to new command name
- **Keep**: CLI flags reference table (most flags are still valid)
- **Keep**: Configuration (.env) reference
- **Keep**: Feature deep-dives for convergent features: Convergence Detection, Adaptive Cooldown, Context Propagation, Error Suggestions, Dashboard, Notifications, Shell Completion
- Simplify to a single "Quick Start" path using the new command

### 27. `.env.example` — REWRITE

- Remove `INFINITE_LOOP_USE_LIBRARY` (library_worker.py removed)
- Remove `INFINITE_LOOP_WORKER_URL` (worker_manager.py removed)
- Remove `INFINITE_LOOP_ARCHIVE_DIR` default `$HOME/.hermes/...` → `$HOME/.config/infinite-loop/archives`
- Remove hermes-specific spawned session flags that reference `hermes` or `~/.hermes/`:
  - `INFINITE_LOOP_IGNORE_USER_CONFIG` (references `~/.hermes/config.yaml`)
  - `INFINITE_LOOP_PROFILE` (hermes profile concept)
- Update any remaining `~/.hermes/` path references
- Update comments that mention "Hermes sessions" → "Worker sessions" or pi-specific

### 28. `.gitignore` — MINOR UPDATE

- Already uses `/tmp/infinite-loop-*` paths — already generic, looks fine.
- No hermes-specific entries found.

---

## PHASE 5: New Module (1 file)

### 29. `hermes_loop/help_topics.py` — CREATE

- Extract from `cli.py`:
  - `_list_flags()` — introspection-based flag listing (keep the argparse introspection, remove hardcoded strings)
  - `_list_examples()` — move hardcoded example blocks into structured data
  - `_run_healthcheck()` — move health check logic
  - `_explain_flag()` — detailed flag help
  - `_help_topic()` — group-level flag display
  - `_run_demo()` — interactive walkthrough (rewrite to work without hermes)
  - `_simulate_demo_output()` — demo output simulator (update to not reference hermes)

---

## Execution Order

```
Phase 1: REMOVE files (orphan broken imports first)
  → worker_manager.py
  → library_worker.py
  → iteration.py
  → wizard.py
  → legacy.py

Phase 2A: Create new module
  → help_topics.py (extracted from cli.py)

Phase 2B: Rewrite core modules (fix imports from deletions)
  → config.py (version sync, move error constants)
  → error_recovery.py (receive moved constants)
  → state.py (dynamic version)
  → preflight.py (receive find_hermes, remove version gating)
  → hermes_utils.py (move find_hermes out, rewrite for pi-worker)
  → loop.py (replace engine, update summary strings)
  → __init__.py (docstring rename)
  → __main__.py (docstring rename)
  → cli.py (extract help_topics, simplify)

Phase 2C: String/variable renames
  → signal_handlers.py
  → error_utils.py
  → completions.py
  → worktree_merger.py
  → diagnosis.py
  → self_test.py
  → archiving.py
  → dashboard.py
  → webhook.py
  → notifications.py

Phase 3: Keep as-is (no writes needed)
  → 14 files listed above — verify with grep, then mark done

Phase 4: Root config files
  → pyproject.toml
  → Makefile
  → README.md
  → .env.example
  → .gitignore (verify only)
```
