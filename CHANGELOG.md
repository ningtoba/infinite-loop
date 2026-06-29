# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- feat: implement SEC-001 — Add API-key authentication middleware to all `/api/*` web endpoints
- feat: auto-approve pi commands, add evolve next-goal detection
- feat: restore and enhance web UI for pi-loop
- feat: add web UI, REST API, and Docker deployment for the infinite loop daemon
- feat: real-time stderr token/progress reader + context-aware regression suggestions (v14.33.0)
- feat: make video-analysis goal prompt bias-free — let research discover best tech
- feat: add video-analysis platform goal prompt to `.env`
- feat: make `--preflight`, `--save-config`, and `--dry-run` work without `--goal` (v14.32.0)
- feat: add post-wizard readiness check, fix stale `python3 -m hermes_loop` in wizard (v14.31.0)
- feat: unify CLI help to use `hermes_loop` command, fix stale docs (v14.30.0)
- feat: add `pyproject.toml` with `console_scripts` entry point (`hermes_loop` command, v14.29.0)
- feat: add `--demo` interactive lifecycle walkthrough (v14.27.0)
- feat: add `--help-topic` flag for group-filtered help, make `help-topic` target (v14.26.0)
- feat: add `--doctor` self-diagnosis, fix `CONTRIBUTING.md` staleness, improve onboarding error (v14.25.0)
- feat: enhance `--init` wizard from 8 to 13 steps with convergence, model, logs, toolsets, heartbeat (v14.24.0)
- feat: add `--init` interactive setup wizard for first-time users (v14.23.0)
- feat: add `make check` and `make pre-commit` targets for pre-commit gates (v14.22.0)
- feat: add `--explain` CLI flag for detailed per-flag help (v14.21.0)
- feat: add `--status` CLI flag for compact built-in ledger status viewer (v14.20.0)
- feat: shutdown summary banner on daemon stop — iterations, duration, success/fail, next-steps (v14.19.0)
- feat: auto-detect self-test group/case count, eliminate stale hardcoded references (v14.18.0)
- feat: add `--check-env` flag to validate `.env` for typos and unknown variables (v14.17.0)
- feat: add `--completion-script` to auto-generate shell completions from argparse (v14.16.0)
- feat: auto-colorize all `_log()` tags and startup banner (v14.15.0)
- feat: add `--color` flag with ANSI color support for CLI output (v14.14.0)
- feat: auto-generate `--list-flags` from argparse, eliminate hardcoded flag dict (v14.13.0)
- feat: add `make examples`/`list-flags`/`list-groups` targets, update `run.sh` help and banner (v14.12.0)
- feat: rich `[SUMMARY]` post-iteration banner with ETA, CPU/mem, git changes (v14.10.0)
- feat: add `--examples` flag with 7 categorized usage pattern sections (v14.9.0)
- feat: add shell tab-completion, `--list-flags`, and `--list-groups` (v14.7.0)
- feat: add `--quiet` flag and iteration heartbeat (v14.6.0)
- feat: actionable `[SUGGEST]` messages on errors/stuck/regression (v14.5.0)
- feat: Ctrl+C kills children + auto-reload on source changes (v14.4.0)
- feat: organized `--help` with argument groups, fix dry-run + `--run` conflict (v14.3.0)
- feat: user-friendliness improvements — Makefile, `CONTRIBUTING.md`, improved help, SSE fix (v14.2.0)
- feat: `run.sh` — one-command entrypoint (reads `.env`, v14.1.2)
- feat: Dashboard XSS fix, error panel, metrics, goals visualization, convergence guard, `--quiet` mode (v14.1.0)
- feat: initial commit — infinite-loop daemon v14.0.0
- enhance: comprehensive remote worktree branch cleanup system — detect, merge, delete remote `hermes/*` branches automatically
- enhance: worktree merge source branch tracking, SSE dashboard reset detection, WebUI conflict display
- enhance: SSE dashboard iteration source fix, false error stderr check, worktree merger retry pass
- enhance: WebUI worktree merge display, soft-error detection improvements, worktree merger edge cases
- enhance: worktree merge results in summary + git push after merge/commit
- enhance: WebUI live sync, false error detection, worktree smart merging
- docs: add consolidated engineering backlog and prioritized action plan

### Fixed

- fix: stored XSS in dashboard HTML and log silent I/O failures (iter #6)
- fix: tighten CORS security, default to localhost bind, add SSE exponential backoff
- fix: improve network error resilience with exponential backoff and log hydration
- fix: resolve 5 backlog issues across loop, web UI, and config
- fix: replace all hardcoded `/tmp` paths with unified `config._get_data_dir`
- fix: remove duplicate `content_block_stop` handler, paramize `worker_id`, apply ruff format
- fix: resolve race conditions, silent exception swallowing, per-attempt output buffers, async blocking I/O
- fix: web UI logic bugs — `worker_term` storage cap, SSE hash for content
- fix: suppress noisy `thinking_delta` events, show clean tool/text output
- fix: prevent zombie subprocess leak on timeout, fix Python 3.10 f-string compat
- fix: remove `toolsets` kwarg from `run_loop` call causing `TypeError`
- fix: strip dead hermes-era config flags, keep only working pi flags
- fix: show worker terminal data in Workers tab even after daemon stops
- fix: remove `--tools` flag, pi uses full default toolset
- fix: stream pi output line-by-line with `[TERM (worker #1)]` prefix
- fix: stop passing `--tools` to pi with old hermes toolset names
- fix: pi tool compat, worker lifecycle markers, lint warnings
- fix: replace `pi -q` with `pi -p` for task execution (pi CLI has no `-q` flag)
- fix: remove hermes-era `--worker-url` flag from web app `loop_manager`, ensure `--run` is always passed on start
- fix: missing `--max-output-chars` argparse definition causing `AttributeError`
- fix: resolve all pyflakes warnings and subtle bugs across codebase
- fix: `/api/config` route handler name collision with imported `get_config`
- fix: add HMAC-SHA256 webhook signing for `--http-callback`
- fix: stop passing `--session-timeout` to hermes (removed in v0.17.0)
- fix: heartbeat monitor now kills hung sessions; PTY path gets idle timeout
- fix: `need_reload` control signal no longer pollutes evolved goal (iter #28)
- fix: SSE init handler unwraps wrapped data for `renderDashboard`, heartbeat card in error panel
- fix: shared `_build_exec_argv()` helper, missing `/api/iterations` endpoint, safer daemon `pkill` pattern, self-test
- fix: `self_test` unicode escape regression from parallel subagent (double-escaped `\u2717`/`\u2713`)
- fix: remove `_iterations` from SSE updates, add SSE broadcast on final stop, include heartbeat in `error_counts`
- fix: store `goals_specs` in state for SSE dashboard, recalc stats after ledger trim, sync version docs
- fix: webhook SSE handler emits correct event names and data shape for dashboard JS
- fix: v14.33.0 doc sync — CHANGELOG entry, README/CONTRIBUTING module counts, stale banners
- fix: `os.execv -m` invocation, `run.sh` unbound goal var, `notify-send --` separator
- fix: sync `run.sh` version banners (14.28.0/14.30.0 → 14.33.0)
- fix: version sync (`pyproject.toml` 14.29.0→14.33.0), `consecutive_successes` copy-paste bug, Makefile ruff lint, `.gitignore .worktrees/`
- fix: WebUI SSE dashboard initial fetch path, false error on exit-code stdout, worktree per-worker tracking
- fix: WebUI iteration dedup with `seenNs` Set, SSE dashboard consistent WT column, worktree branch-exists null guard
- fix: WebUI sync via SSE `latest_iteration`, SSE hash coverage for WT merge, worktree merger edge cases
- fix: WebUI `_lastSeenIterationCount` reset, SSE dashboard live events, false error detection
- fix: correct hermes binary mount path, remove vestigial config persistence group
- fix: switch default port to 8090, make it configurable via `WEB_PORT` env var
- fix: stop tracking `.env` — move to gitignore-only (untrack from history)
- fix: v14.28.0 — fix stale versions in `run.sh`, add `--demo` forwarding, no-env early-exit
- fix: `--help` now shows organized argument groups (22 sections)
- fix: WebUI live sync, false error detection, worktree smart merging
- fix: `run.sh`: fix `--preflight` conflict with `--run` (preflight exits when both are set, but `--run` already triggers checks)
- fix: README: fix TOC link slugs for headings containing `&`
- fix: README: fix broken tables, user-specific paths, outdated references
- fix: `Fix lastLogIdx` absolute-epoch tracking bug (bug #1 from iter #2 audit)
- fix(web_app): `preview_cli_args` uses `shlex.join()` instead of `' '.join()`
- fix: signal handler graceful shutdown, fix `_shutdown_state_ref` wiring, fix `_handle_backoff` responsive sleep
- fix: web_app server shutdown hang, redundant imports, dashboard cooldown falsy bug - v14.38.0
- fix: `setdefault` bug, regex precedence in `loop_manager`, dead `QueueFull` catches
- fix: web_app throughput metrics, deduplicate webhook `/api/status`, fix SSE broadcast cleanup, fix cooldown ordering
- fix: add missing throughput/metrics fields to web_app `loop_manager get_status()`
- fix: falsy-metric bugs in `metrics_summary`, add server shutdown handler, remove redundant `spawn_goal` reassign
- fix: RUF006 task GC bugs, RUF001 ambiguous unicode, RUF022 sort all, plus code quality
- fix: SSE init handler unwraps wrapped data for `renderDashboard`, heartbeat card in error panel
- fix: deduplicate SSE wrapping, support `/api/iterations?limit=N`, clean up stale comment
- fix: `avg_chars_per_iter`/`avg_throughput` in webhook `/api/status`, unbounded SSE queue in web_app `server.py`
- fix: `self_test` unicode escape regression from parallel subagent (double-escaped `\u2717`/`\u2713`)
- fix: cooldown smooth interpolation, subprocess `capture_output` fix, `sysconf_names` cleanup, redundant mitigations `setdefault` removal, `maxsize=1` queue fix, cooldown in `loop_manager` status, `self_test` string escape fixes
- fix: worktree remote deletion, webhook SSE init event, loop `need_reload`
- fix: `worktree_path` propagation fix + iter #3 followup
- fix: remove `_iterations` from SSE updates, add SSE broadcast on final stop, include heartbeat in `error_counts`
- fix: 4 bugs + 1 enhancement across 4 files
- fix: 4 bugs + 2 enhancements across 5 files
- fix: store `goals_specs` in state for SSE dashboard, recalc stats after ledger trim, sync version docs
- fix: bugfix + enhancement pass — 5 fixes across 8 files
- fix: webhook SSE handler emits correct event names and data shape for dashboard JS
- fix: version sync to 14.34.0 + cleanup fixes across 8 files
- fix: bugfix + cleanup pass — 7 fixes across 9 files
- fix: `consecutive_successes` init in state, SSE client thread-safety in web_app
- fix: SSE dashboard fixes (unicode, status mapping, missing data fields), `mask_sensitive` edge cases, `_set_originals()` fix, `notify-send --` separator, `init_auto_reload`, stats `consecutive_successes`, `diagnosis.py` doc fix, `state.py` version_detail sync
- fix: v14.33.0 doc sync — CHANGELOG entry, README/CONTRIBUTING module counts, stale banners
- fix: `cleanup_stale_worktrees`, SSE mitigation dict fix, `system_utils clk_tck` fix, version detail sync
- fix: `os.execv -m` invocation, `run.sh` unbound goal var, `notify-send --` separator
- fix: sync `run.sh` version banners (14.28.0/14.30.0 → 14.33.0)
- fix: 1343 ruff lint errors to zero — F401, F841, F821, E402, E501, F541, E741, F811 fixes
- fix: version sync (`pyproject.toml` 14.29.0→14.33.0), `consecutive_successes` copy-paste bug, Makefile ruff lint, `.gitignore .worktrees/`
- fix: WebUI SSE batch-add, false-error threshold, enhanced worktree merger
- fix: WebUI SSE dashboard initial fetch path, false error on exit-code stdout, worktree per-worker tracking
- fix: WebUI iteration dedup with `seenNs` Set, SSE dashboard consistent WT column, worktree branch-exists null guard
- fix: WebUI sync via SSE `latest_iteration`, SSE hash coverage for WT merge, worktree merger edge cases
- fix: WebUI `_lastSeenIterationCount` reset, SSE dashboard live events, false error detection
- fix: WebUI live sync, false error detection, worktree smart merging
- fix: correct hermes binary mount path, remove vestigial config persistence group
- fix: switch default port to 8090, make it configurable via `WEB_PORT` env var
- fix: stop tracking `.env` — move to gitignore-only (untrack from history)

### Changed

- refactor: replace 71-param `run_loop` signature with `LoopConfig` dataclass
- refactor: extract `_create_parser` to separate module, break circular import
- refactor: remove `.env` dependency, rewrite README, add config file
- refactor: convert from hermes-agent to pi coding agent
- refactor: switch config from `.env` to JSON — web UI is the sole source of truth
- refactor: auto-generate `--list-flags` from argparse, eliminate hardcoded flag dict (v14.13.0)
- refactor: 8051-line `launch-loop.py` into structured `hermes_loop/` package (v14.4.0)
- chore: rebuild venv to remove chromadb CVE and 130+ unused packages
- chore: add pinned lock files for reproducible builds
- chore: add Dependabot config, fix CPU first-read showing 0%
- chore: commit iteration 4 work — unified path config, `threading.Event`, race fixes, perf improvements, tests
- chore: update `ENGINEERING_BACKLOG.md` with completed items
- chore: add git pre-commit hook to auto-regenerate completion scripts
- chore: move inline import logging to module level in `library_worker.py`
- chore: remove all pytest tests and coverage artifacts
- chore: bump to v14.37.0
- chore: sync version refs to v14.34.0 (CONTRIBUTING, README, preflight docstring, `run-loop.sh` banner)
- chore: fix '~40 tests' docs mismatch, add missing flags to README/CONTRIBUTING, v14.11.0
- chore: fix 1343 ruff lint errors to zero — F401, F841, F821, E402, E501, F541, E741, F811 fixes
- chore: fix stale version/banner references across docs, bump to 14.20.1 (v14.20.1)

### Documentation

- docs: add consolidated engineering backlog and prioritized action plan
- docs: update backlog — mark 5 completed items, add appendix for iteration 3
- docs: update backlog with Dependabot, cleanup, and CPU fix completions
- docs: annotate schema `moderate=None` threshold in `config.py`
- docs: update docs for `hermes_loop/` package structure, fix stale references
- docs: update improvement plan with scan findings (iter #3)
- docs: improvement plan scan pass (v14.38.2)
- docs: fix stale version/banner references across docs, bump to 14.20.1 (v14.20.1)
- docs: update stale docs and banners for v14.10.0 `[SUMMARY]` output format

### Performance

- perf: remove redundant duplicate status file writes in `run_loop()`

### Security

- fix: tighten CORS security, default to localhost bind, add SSE exponential backoff
- fix: stored XSS in dashboard HTML and log silent I/O failures (iter #6)
- fix: add HMAC-SHA256 webhook signing for `--http-callback`

## [14.39.0] - 2026-06-30

- Port from hermes-agent to pi coding agent with full web UI, REST API, and Docker support
- Refactored monolithic `launch-loop.py` into modular `hermes_loop/` package
- Replaced `.env` configuration with persistent JSON config via web UI
- Added API-key authentication middleware for all `/api/*` endpoints
- Migrated from 71-param `run_loop` to typed `LoopConfig` dataclass
- Eliminated all 1343 ruff lint errors to zero
- Removed all chromadb CVE-vulnerable packages and 130+ unused dependencies
- Added pinned lock files for reproducible builds
- Replaced all hardcoded `/tmp` paths with unified data directory configuration
- Added SSE-based real-time dashboard with worktree merge display
- Added comprehensive remote worktree branch cleanup system
- Added exponential backoff for network resilience
- Added HMAC-SHA256 webhook signing for `--http-callback`
- Added `--init`, `--doctor`, `--demo`, `--explain`, `--status`, `--check-env`, `--quiet`, `--color` CLI flags
- Added `pyproject.toml` with `console_scripts` entry point
- Added `make check`, `make pre-commit`, shell tab-completion targets
- Added Dependabot config for automated dependency updates
- Initial release of the infinite-loop daemon refactored for the pi coding agent

[Unreleased]: https://github.com/nekophobia/hermes-loop/compare/v14.39.0...HEAD
[14.39.0]: https://github.com/nekophobia/hermes-loop/releases/tag/v14.39.0
