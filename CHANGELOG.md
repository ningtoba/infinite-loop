# Changelog

All notable changes to the **Infinite Loop Daemon** project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [14.3.0] — 2026-06-26

### Added
- **Organized `--help` output**: All 80+ CLI flags now grouped into 22 logical
  sections (Core Task, Toolsets, Iteration Control, Parallelism, Timeouts &
  Retries, Git Integration, Goals File, Rate Limiting, Convergence Detection,
  Structured Output, Shutdown, Profile/Model, Webhook/HTTP, Notifications,
  Logging, Status/Dashboard, Ledger Management, Archiving, File Watcher,
  Worker, Spawned Session Flags, Startup/Debug) for much more readable
  `--help` output.
- **Structured `--help` description**: Replaced the wall-of-text argparse
  description with a readable multi-line summary: "Features at a glance"
  grouped by category (Iteration, Parallel, Notify, Sessions, Spawn, Debug,
  Git, Web), common usage examples, and stop/pause/status commands. Uses
  `RawDescriptionHelpFormatter` for proper formatting. (`--help` and `--help
  -h` now bypass argparse for instant response.)
- **Friendly missing `--goal` error**: Before argparse's default "required"
  error, prints a clear message: "ERROR: --goal is required (or use
  --goals-file for batch mode)" with usage hint and pointer to `--help`.

### Changed
- **Readable startup banner**: Replaced the 10-line wall-of-features text with
  a compact feature summary (3 lines, pipe-separated categories under a
  Unicode ═ header). No more version-dependent banner drift.
- Bumped `launch-loop.py` from v14.2.0 to v14.3.0

### Fixed
- **`run.sh --dry-run` with `.env` `--run`**: When `--dry-run` is used but
  `.env` has `INFINITE_LOOP_RUN=true`, the `--run` flag was still forwarded
  making dry-run effectively a no-op. Now `--dry-run` strips `--run` from
  the forwarded args.

### Added
- **Makefile**: Convenience targets — `make run`, `make dry-run`, `make self-test`,
  `make lint`, `make status`, `make stop`/`pause`/`resume`, `make clean`,
  `make archive`, `make log`, `make version`, `make env`, `make help`.
- **CONTRIBUTING.md**: Onboarding guide for new contributors covering setup,
  development workflow, code style, submitting changes, and troubleshooting.
- **Improved `run.sh --help`**: Organized sections (General, Actions, Info,
  Examples) with inline quick reference for ledger, status, sentinel, and
  dashboard commands.
- **`run.sh --self-test` and `--version`**: New CLI passthrough flags.
- **`./run.sh` banner**: Now displays v14.2.0 version and new features.

### Fixed
- **SSE broadcast crash**: Added missing `global _sse_clients` declaration in
  `_broadcast_to_sse_clients()` to prevent `UnboundLocalError` on first call.

### Changed
- Bumped `launch-loop.py` from v14.1.0 to v14.2.0
- Bumped `session-self-loop.py` from v2.11.0 to v2.12.0
- Bumped `run-loop.sh` banner and header to v14.2.0
- Updated README: v14.2.0 changelog table, Makefile & CONTRIBUTING.md in
  header, scripts table, and filesystem tree

---

## [14.1.0] — 2026-06-26

### Added
- **Dashboard XSS Fix**: Replaced `innerHTML` string interpolation with `createElement` + `textContent` in SSE dashboard's `addIterationRow()`. Eliminates DOM-based XSS from spawned session output.
- **Dashboard Error Panel**: Error type count cards (timeout, network, schema, unknown) with color-coded left-border accents. Active mitigations displayed as tags.
- **Dashboard Performance Metrics**: Avg turns, estimated tokens/iter, cost estimate, iters/goal metric cards on SSE dashboard.
- **Dashboard Goals Visualization**: Per-goal status with progress bar, ✓/▶/○ indicators, scrollable list. Populated from `goals_specs` + `goals_completed` via SSE payload.
- **False Convergence Guard**: `_detect_convergence()` skips Jaccard similarity check when summary < 20 chars. Prevents false convergence stops from empty/error summaries.
- **`--quiet` / `-q` mode**: Suppresses ASCII banner and startup info in CI/CD and scripted use.

### Changed
- Bumped `run-loop.sh` from v14.0.0 to v14.1.0 (version header + banner)
- Bumped `session-self-loop.py` from v2.10.0 to v2.11.0

### Fixed
- False convergence stops from empty/error summaries

---

## [14.0.0] — 2026-06-24

### Added
- **Dashboard v3 SSE** (Server-Sent Events): `GET /live` SSE stream, `GET /dashboard` live HTML with auto-refresh
- **Session Self-Healing Heartbeat**: `--heartbeat-timeout N` flag with grace period (`timeout × 2`), kill & retry on hung sessions
- **Preflight Hermes Version Check**: `check_hermes_version()` static method on `PreflightChecker`
- **Auto-start Hermes Worker**: `--worker-url auto` (default) auto-starts embedded worker on random port
- **Function Decomposition Phase 2**: extracted `_execute_iteration()`, `_merge_worker_results()`, `_handle_backoff()` from `run_loop()`. Shrunk `run_loop()` by ~250 lines.
- **Function Decomposition Phase 3**: extracted `_detect_convergence()`, `_compact_summaries()`, `_build_iteration_record()`, `_handle_notifications()`, `_handle_callbacks()`. Shrunk `run_loop()` by another ~220 lines.

### Changed
- `lm-eval-harness` reference doc added to project

---

## [13.1.0] — 2026-06-24

### Added
- **Idempotent Goal Execution**: `--track-goals` and `--reset-goals` flags. Completed goals tracked via hash and automatically skipped on restart.
- **Goal Hash Tracking**: `_goal_hash()` uses `hashlib.md5` of goal text + iteration number
- **Webhook Payload Enrichment**: `_handle_callbacks()` already enriches with state, stats, system, pid
- **Multi-Profile Goals**: Pipe-separated format in `--goals-file` supports per-goal profile/model/provider overrides (`goal|profile|model|provider`)

### Fixed
- Version inconsistencies across all reference files bumped to v13.0.0+

---

## [13.0.0] — 2026-06-24

### Added
- **Self-Test Mode**: `--self-test` flag runs ~40 in-process tests across 8 daemon functions
- **Output Progress Classification**: `_classify_progress()` categorizes iterations as completed/progress/partial/stuck/regression/unknown
- **Startup Banner**: Comprehensive listing of all daemon features
- **Enhanced `--help`**: Full options summaries for all 45+ flags
- **50+ TASK_PATTERNS keywords**: Better task-type auto-detection across all 7 categories

### Changed
- Startup banner now dynamically displays version from VERSION constant
- All 34/34 self-tests pass, all syntax checks clean

---

## [12.0.0] — 2026-06-23

### Added
- **Concurrent Library Mode**: `--use-library` now works with `--workers > 1` via `multiprocessing.Pool`
- **Automatic Error Recovery**: `_adapt_to_error()` with behavioral mitigation based on error type and history
- **In-Process Ledger Archiving**: `--archive-dir`, `--archive-retention`, `--archive-max-size` flags
- **Multi-Profile Goals File**: Pipe-separated format (goal|profile|model|provider)

### Changed
- `ThreadPoolExecutor` replaced with `multiprocessing.Pool` for library mode
- Function Decomposition Phase 1: extracted `_load_goals_file()`, `_log_startup_banner()`, `_cycle_goal()`, `_build_progressive_context()`, `_handle_cooldown()` from `run_loop()`

---

## [11.14.0] — 2026-06-23

### Added
- `--safe-mode` flag: Disables ALL customizations (implied `--ignore-rules` + `--ignore-user-config`)
- `--accept-hooks` flag: Auto-approve shell hooks without TTY
- `--worktree` flag: Run spawned sessions in isolated git worktree
- `--continue` flag: Resume most recent session

### Changed
- All 74 Hermes `chat -q` passthrough flags now fully covered
- Argparse flags: 81+ add_argument calls, all properly threaded

---

## [11.13.0] — 2026-06-23

### Added
- `--yolo` flag: Bypass dangerous command approval prompts
- `--ignore-user-config` flag: Skip `~/.hermes/config.yaml` in spawned sessions
- `--spawn-source` flag: Tag spawned sessions with custom source label (default: `infinite-loop`)

---

## [11.12.0] — 2026-06-23

### Added
- **Session Chaining** (`--resume`): Chain spawned sessions across iterations via `--resume SESSION_ID`
- **Skills Flag** (`--skills`): Preload specific skills in spawned sessions (comma-separated)
- **Ignore Rules Flag** (`--ignore-rules`): Clean-slate mode (no AGENTS.md, memory, or rules)
- **Session ID History**: Rolling list of spawned_session_id values (last 100) stored in ledger

---

## [11.11.0] — 2026-06-22

### Added
- **AIAgent Library Mode** (`--use-library`): Run AIAgent.run_conversation() in-process instead of spawning subprocess. Eliminates subprocess overhead, provides direct token/cost data.
- **Session Tracking** (`--pass-session-id`): Store spawned session ID in ledger
- **Checkpoints Flag** (`--checkpoints`): Enable file checkpoints in spawned sessions (auto-enabled with `--git`)

### Changed
- `run-loop.sh` bumped from v11.10.0 to v11.11.0 with all three new flags forwarded

---

## [11.10.0] — 2026-06-22

### Fixed
- `output_cap` undefined variable in worker URL mode
- HTML dashboard now dynamically displays version from VERSION constant

### Changed
- Updated all DAEMON/startup banners to reflect v11.9.0 features
- Added `{VERSION}` placeholder to dashboard footer and header

---

## [11.9.0] — 2026-06-22

### Added
- **Pushbullet mobile notifications**: `--notify-pushbullet TOKEN` via Pushbullet API v2
- **ntfy push notifications**: `--notify-ntfy TOPIC` via ntfy.sh or self-hosted ntfy server
- **Unified notification dispatcher**: `_send_per_iteration_notifications()` sends to all channels in one call
- **Completion notification** now uses all channels when Pushbullet/ntfy set

### Removed
- Old `_send_completion_notification()` replaced with unified version

---

## [11.8.0] — 2026-06-22

### Added
- `/api/status` endpoint: Returns COMPLETE ledger state dict
- **REST API control endpoints**: POST `/control/stop`, `/control/pause`, `/control/resume`
- **Preflight health checks**: `--preflight` and `--preflight-fail-fast` flags
- **Status dashboard improvements**: Auto-refresh (30s), SVG favicon, system resource cards, ETA column, cooldown indicator, dark/light mode, compact summary-only mode

---

## [11.7.0] — 2026-06-21

### Added
- **Daemon status API**: `GET /api/status` at webhook port returns full iteration state as JSON
- **Desktop notifications**: `--notify-desktop` via `notify-send` (Linux)
- **Config file support**: `--save-config` and `--config` flags
- **Startup delay**: `--startup-delay N` before first iteration
- **Completion notification**: `--notify-on-completion` sends summary when daemon finishes
- **Error classification**: Iteration errors classified as network/timeout/schema/unknown

---

## [11.6.1] — 2026-06-21

### Fixed
- Missing `logging.handlers` import (crash with `--log-file`)
- `os.sysconf_names` KeyError on some Python builds

---

## [11.6.0] — 2026-06-21

### Added
- Feature banner: comprehensive list including Dashboard v3 SSE, heartbeat, version check
- Output schema validation: `--output-schema` and `--output-schema-file`
- Resource tracking: CPU, memory from `/proc` (Linux)
- Convergence detection: Jaccard word-overlap with adaptive threshold
- Git diff storage: `--store-git-diff` (capped at 10KB)
- Adaptive cooldown: auto-calculated from avg iteration duration
- `run-loop.sh`: Fixed version header, added `--version` flag

---

## [11.5.0] — 2026-06-21

### Added
- Structured output validation (stdlib-only JSON Schema subset)
- Adaptive cooldown mode (`--cooldown-mode adaptive`)
- Convergence detection with Jaccard similarity
- Git diff storage in ledger (capped 10KB per iteration)
- Resource tracking from `/proc` (Linux-only)

---

## [11.4.0] — 2026-06-20

### Added
- `--evolve` mode: Task evolution (auto-propose next goal)
- `--git` flag: Capture git diff per iteration
- `--git-commit` flag: Auto-commit per iteration
- `--workers N`: Parallel execution
- `--notify-cmd`: Post-iteration shell command
- `--max-output-chars`: Output capture size limit
- Signal handling (SIGTERM/SIGINT with temp-file + atomic-rename)
- JSON-safe prompt construction
- ISO 8601 parsing improvements
- `--cooldown` and `--goals-file` flags
- `--stop-at-goals-end` flag

---

## [11.3.0] — 2026-06-20

### Added
- Hermes Worker URL mode (`--worker-url`)
- Embedded Hermes Worker Manager
- Multi-worker context merging

---

## [11.2.0] — 2026-06-20

### Added
- **Webhook mode**: `--webhook-port N` starts HTTP server with POST /webhook, GET /health, GET /status
- **File watcher**: `--watch-dir` and `--watch-poll` for stat-based file change detection
- **Daemon log file**: `--log-file` with rotating file handler
- **Status HTML dashboard**: `--status-html` generates self-contained HTML
- **ETA tracking**: Rolling average + remaining estimate
- `inspect-ledger.sh`: Updated with `--watch` and `--summary` modes

---

## [11.1.0] — 2026-06-19

### Added
- `--no-auto-toolsets`: Disable automatic toolset enrichment
- `--no-failure-learning`: Disable past failure context injection
- `--task-type`: Manual task type override
- **Failure learning**: Inject past failure context into spawned sessions
- **Auto-toolsets**: Detect task type from goal and add relevant tools

---

## [11.0.0] — 2026-06-19

This was a complete rewrite. Previous versions (v1–v10) used `-z` oneshot mode
which broke delegation. v11.0.0 introduced the correct architecture:

### Changed
- Switched from `-z` (oneshot) to `chat -q` (multi-turn session)
- Sessions stay alive for `--max-turns N` (default 500)
- `delegate_task()` subagent results now arrive and are collected
- Multi-line JSON parser with brace-counting extraction
- Stderr capture and filtering

### Added
- `-t terminal,file,delegation` — spawned sessions have direct tools + delegation
- `--max-turns N` — configurable session lifetime
- Sentinels: `stop`/`pause`/`resume` via `/tmp/infinite-loop-stop`
- JSON state ledger at `/tmp/infinite-loop-state.json`
- Archive directory at `~/.hermes/infinite-loop-archives/`
- Self-modification support via `need_reload` signal
- Profile, model, provider overrides
- Context propagation across iterations

---

## [10.0.0] — 2026-06-18

### Changed
- Switched from `-z` oneshot to `hermes chat -q` (core fix)
- `chat -q -t terminal,file,delegation -Q --max-turns N` means sessions stay alive for multiple turns
- `delegate_task()` subagent results can actually arrive and be collected
- Multi-line JSON parsing with brace counting
- Stderr capture separate from stdout

---

## [9.0.0] — 2026-06-17

### Added
- `--on-error-cmd`: Shell command on failed iteration
- `--tag`: Label/identifier for runs
- `--prompt-suffix`: Extra text appended to spawned prompts
- `--force-reset`: Clear existing ledger

---

## [8.0.0] — 2026-06-17

### Changed
- Switched from delegation-only toolset to full tools (`terminal,file,delegation`)
- Fixed delegation results never arriving (sessions exited before subagent results)
- Introduced `--max-retries` for failed iterations

---

## [7.0.0] — 2026-06-16

### Changed
- Complete skill restructuring
- Removed cron-based mode (banned)
- Background daemon is now the sole mode
- Command references updated from `hermes -z` to `hermes -z -t delegation`

---

## [6.0.0] — 2026-06-16

### Changed
- Two-component architecture: daemon (launch-loop.py) for ledger + Hermes session calls delegate_task() directly
- Background daemon mode introduced

---

## [5.0.0] — 2026-06-15

### Changed
- Restructured to daemon + companion Hermes session pattern
- v5.0.0 was semi-functional

---

## [4.0.0] — 2026-06-15

### Added
- Self-contained loop with `--command`, `--task-list`, `--script` modes
- `--hermes-delegate` mode with shared file protocol
- Three autonomous modes

---

## [3.0.0] — 2026-06-14

### Changed
- Two-component architecture: launch-loop.py as ledger daemon + stdin.readline() protocol
- Blocking stdin made it hang (no stdio connected in background terminal)

---

## [2.0.0] — 2026-06-14

### Added
- Background daemon pattern
- Bash wrapper (run-loop.sh) for safety

---

## [1.0.0] — 2026-06-13

### Added
- Initial infinite-loop skill for Hermes Agent
- Basic looping with subprocess spawning
- SKILL.md with standalone component description
