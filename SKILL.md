---
name: infinite-loop
description: "Self-looping background daemon that spawns Hermes sessions via `hermes chat -q` with REAL tools (terminal, file) AND delegation (delegate_task). v14.1.0: Dashboard SSE error panel, performance metrics, goals visualization; XSS fix; false convergence guard; --quiet mode. v14.0.0: Dashboard v3 SSE, Session Self-Healing Heartbeat, Hermes version check in preflight."
version: "14.1.0"
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [infinite-loop, autonomous, background, looping, delegation, daemon, profile, http-callback, retry, tagging, pause-resume, max-turns, json-parser, auto-toolsets, task-type, failure-learning, worker, self-reference, cooldown, goals-file, progress-bar, signal-safe, output-schema, convergence, adaptive-cooldown, multi-goal-workers, resource-tracking, git-diff, context-propagation, in-session-loop, self-modification, config-file, desktop-notifications, error-classification, startup-delay, pushbullet, ntfy, push-notifications, v14.1.0, xss-fix, dashboard-sse, error-panel, performance-metrics, goals-dashboard, convergence-guard, quiet-mode]
    related_skills: [system-improvement, self-modifying-code, plan, hermes-agent]
---

---

# Infinite Loop — v14.1.0 (Dashboard SSE Error Panel, Performance Metrics, Goals Visualization, XSS Fix, Convergence Guard, --quiet mode)

**Architecture**: Same solid foundation as v10.0.0/v11.0.0 — `hermes chat -q` with
`terminal,file,delegation` toolsets, keeping sessions alive for multiple
turns so `delegate_task()` subagent results arrive and are collected properly.

**v14.1.0 enhancements — Dashboard SSE Error Panel, Performance Metrics, Goals Visualization, XSS Fix, False Convergence Guard, --quiet mode:**

1. **P0: Dashboard XSS Fix** — The SSE live dashboard (`addIterationRow`) previously built HTML rows via `innerHTML` string interpolation with raw `iter.task_type` and `iter.classification` values from spawned sessions. This was a DOM-based XSS vulnerability (MEDIUM severity). Fixed by using `createElement` + `textContent` for all user-data injection points. A `createTag()` helper function creates `<span>` elements with safe `textContent` assignment.

2. **P1: Dashboard Error Panel** — A dedicated error visualization section in the SSE dashboard shows error type counts (timeout, network, schema, unknown) as color-coded cards with a left-border accent. Active mitigations (timeout increased, cooldown elevated, force library disable, worker reduction, consecutive errors) are displayed as tags next to the error cards. The initial fetch and live SSE updates both populate the panel.

3. **P1: Dashboard Performance Metrics** — Four new metric cards: average turns per iteration, estimated tokens per iteration, estimated cost, and iterations per goal (when goals file is active). Data is derived from the latest iteration record's `turns_used`/`tokens_used` fields (populated in library mode) and from goals-completed tracking.

4. **P1: Dashboard Goals Visualization** — When `--goals-file` is active, a dedicated Goals panel shows: a progress bar (completed/total), per-goal status rows with ✓ (done), ▶ (active), ○ (pending) indicators, and a scrollable list (max 30 visible, "+N more" beyond that). The panel is populated from `goals_specs` and `goals_completed` state via `_build_sse_payload()`.

5. **P2: False Convergence Guard** — `_detect_convergence()` now skips the Jaccard similarity check when the combined summary is empty or fewer than 20 characters. Empty summaries from crashed/quiet sessions previously reported 1.0 similarity (identical empty strings), triggering false convergence stops. A log warning `[CONVERGENCE] SKIP` is emitted when skipped.

6. **P3: --quiet mode for run-loop.sh** — New `--quiet` / `-q` flag suppresses the ASCII banner and startup info lines in `run-loop.sh`. Useful for CI/CD pipelines and scripted invocations where the 13-line banner is noise. The daemon's own banner and output are unaffected.

**v14.0.0 enhancements — Dashboard v3 SSE, Session Self-Healing Heartbeat, Hermes Version Check (iteration #10):**

1. **Function Decomposition Phase 2 (P0)** — Extracted 3 more self-contained functions from the `run_loop()` monolith: `_execute_iteration()`, `_merge_worker_results()`, and `_handle_backoff()`. `run_loop()` shrunk by another ~250 lines (total ~450 lines removed from v12.0.0). This makes the iteration lifecycle more readable and testable.

2. **Function Decomposition Phase 3 (P0)** — Extracted 5 post-processing functions from `run_loop()`: `_detect_convergence()`, `_compact_summaries()`, `_build_iteration_record()`, `_handle_notifications()`, and `_handle_callbacks()`. `run_loop()` shrunk by another ~220 lines. The entire post-iteration chain (git snapshot → convergence → compact → record → notify → callbacks → cooldown → recovery) now consists of named, testable function calls.

3. **Self-Test Mode (`--self-test`, P1)** — Runs ~40 in-process unit tests across 8 core daemon functions without spawning any child Hermes sessions. Tests cover: `extract_json_from_output()` (5 edge cases), `classify_error()` (4 error types), `text_similarity()` (3 similarity cases), `check_convergence()` (3 convergence patterns), `validate_json_output()` (3 schema validation cases), `calc_adaptive_cooldown()` (4 duration ranges), `GoalSpec` parsing (3 goal file formats), and `_classify_progress()` (6 classification categories). Each test reports individual pass/fail status.

4. **Output Progress Classification (`_classify_progress()`, P1)** — Each iteration is now classified as `completed`, `progress`, `partial`, `stuck`, `regression`, or `unknown` based on the summary text, git diff changes, and error state. The classification is stored in the ledger per-iteration record. Enables color-coded dashboards and smarter auto-stop criteria (e.g., stop after 3 "stuck" classifications).

5. **Idempotent Goal Execution (`--track-goals`, `--reset-goals`, P2)** — When used with `--goals-file`, completed goals are tracked in the ledger via a hash of the goal text. On restart, already-completed goals are automatically skipped. `--reset-goals` clears the tracking for a fresh run. Prevents wasted re-execution after crashes or restarts.

**v12.0.0 enhancements — Concurrent library mode, auto error recovery, in-process archiving, multi-profile goals (iteration #26):**

1. **Concurrent Library Mode (`--use-library` with `--workers > 1`)** — Previously, `--use-library` was incompatible with `--workers > 1` (silently fell back to subprocess). Now uses `multiprocessing.Pool` with each worker creating a fresh AIAgent in its own process. Falls back gracefully to sequential execution if multiprocessing is unavailable. Based on the proven pattern from Hermes `batch_runner.py`.

2. **Automatic Error Recovery (`--archive-dir`, `--archive-retention`, `--archive-max-size`)** — The daemon now adapts its behavior based on error type and history:
   - 3 consecutive `timeout` errors → auto-double `session_timeout` (capped at 3600s)
   - 2 consecutive `network` errors → force cooldown to 120s minimum
   - 5 consecutive `unknown` errors → force subprocess mode for 10 iterations
   - On successful iteration → gradually reduce mitigations
   - All per-type counters and active mitigations are persisted in the ledger for crash recovery

3. **In-Process Ledger Archiving** — The ledger auto-shrink (`--keep-iterations`) now archives trimmed iterations to gzip-compressed JSONL files before discarding them. Archive files go to `~/.hermes/infinite-loop-archives/iterations-{YYYYMMDD}-{seq}.jsonl.gz` by default. Each archive starts with a `_meta` header line. Auto-cleanup of archives older than `--archive-retention N` days (default: 30). Max total archive size controlled via `--archive-max-size MB` (default: 100 MB).

4. **Multi-Profile Goals File (`--goals-file` pipe format)** — Goal lines can now optionally specify per-goal profile, model, and provider overrides as pipe-separated fields: `goal text|profile|model|provider`. Empty fields fall back to daemon-level CLI args. Backward compatible — plain lines without pipes work exactly as before.

5. **Function Decomposition Phase 1** — Extracted 5 self-contained helper functions from the `run_loop()` monolith: `_load_goals_file()`, `_log_startup_banner()`, `_cycle_goal()`, `_build_progressive_context()`, and `_handle_cooldown()`. `run_loop()` shrunk by ~200 lines.

6. **New CLI flags**: `--archive-dir DIR`, `--archive-retention N`, `--archive-max-size MB`.

**v11.12.0 enhancements — Session chaining, skills preloading, clean-slate mode (iteration #17)**:

1. **Session Chaining (`--resume`)** — Chain spawned Hermes sessions across iterations so each new session inherits the full conversation history of the previous one. Uses `hermes --resume PREV_SESSION_ID chat -q` in subprocess mode, or passes `session_id=PREV_SESSION_ID` to AIAgent in library mode. Requires `--pass-session-id` to populate the spawned session ID in the ledger. The first iteration has no previous session and resume is silently skipped.

2. **Skills Preloading (`--skills`)** — Preload skills into spawned Hermes sessions via the `-s` flag. Pass a comma-separated list of skill names (e.g., `--skills "python-debug,code-review"`) to give spawned sessions specialized knowledge without embedding long strategy prompts.

3. **Clean-Slate Mode (`--ignore-rules`)** — Start spawned sessions without loading AGENTS.md, memory, or custom rules. Creates a truly blank slate for isolated, reproducible spawned sessions — ideal for CI/CD pipelines and troubleshooting.

4. **Session ID History** — The ledger now maintains a rolling list of the last 100 spawned session IDs in `session_id_history`. This enables inspection of past sessions, debugging, and future `--resume` use. Access via `python3 -c "import json; d=json.load(open('/tmp/infinite-loop-state.json')); print(len(d.get('session_id_history',[])))"`.

**v11.13.0 enhancements — YOLO mode, ignore-user-config, source tagging (iteration #19)**:

1. **YOLO Mode (`--yolo`)** — Passes `--yolo` to ALL spawned sessions, bypassing dangerous command approval prompts for fully autonomous operation. Combine with `--ignore-rules` for maximum autonomy: `--yolo --ignore-rules`. Uses Hermes CLI's built-in `--yolo` flag. Subprocess mode only; skipped in library mode with a log warning.

2. **Ignore User Config (`--ignore-user-config`)** — Passes `--ignore-user-config` to spawned sessions so they skip `~/.hermes/config.yaml` and fall back to built-in defaults. Useful for isolated, reproducible runs without user configuration interference.

3. **Source Tagging (`--spawn-source`)** — Tags spawned sessions with a custom source label passed as `--source` to `hermes chat -q`. Defaults to empty (uses Hermes' own default 'cli'). Set to `infinite-loop` for distinguishing loop sessions from manual ones. The source label is stored in the Hermes session DB for filtering.

**v11.14.0 enhancements — safe-mode, accept-hooks, worktree, continue (iteration #22):**

1. **Safe Mode (`--safe-mode`)** — Passes `--safe-mode` to spawned sessions, disabling ALL
   customizations: user config, AGENTS.md/memory injection, plugins, and MCP servers.
   Implies both `--ignore-user-config` and `--ignore-rules`. Perfect for troubleshooting
   and isolating whether a problem comes from the setup or from Hermes itself.
   Subprocess mode only; skipped in library mode with a log note.

2. **Auto-Accept Hooks (`--accept-hooks`)** — Passes `--accept-hooks` to spawned sessions,
   auto-approving any unseen shell hooks declared in config.yaml without a TTY prompt.
   Useful for CI/CD and automated pipelines where interactive prompts would block execution.
   Subprocess mode only.

3. **Git Worktree Mode (`--worktree`)** — Passes `--worktree` to spawned sessions, running
   them in an isolated git worktree. Useful for parallel agents working on the same repo
   without interfering with each other's working state. Subprocess mode only.

4. **Continue Session (`--continue`)** — Passes `--continue` to spawned sessions, resuming
   the most recent session. An alternative to `--resume` that doesn't require a specific
   session ID. Subprocess mode only.

5. **Updated documentation** — SKILL.md, cross-iteration-context.md, and run-loop.sh all
   updated to reflect the 4 new flags.

**v11.11.0 enhancements — AIAgent library mode, session tracking, checkpoints (iteration #14)**:

1. **AIAgent Library Mode (`--use-library`)** — Instead of spawning `hermes chat -q`
   as a subprocess, the daemon can now import `AIAgent` from `run_agent` and run
   the conversation in-process. This eliminates subprocess overhead, simplifies
   error handling, and provides direct access to the result dict (including
   session_id, token usage, and cost data). Falls back to subprocess mode
   automatically if the library is not importable. Incompatible with `--workers > 1`.

2. **Session Tracking (`--pass-session-id`)** — Passes `--pass-session-id` to
   spawned Hermes sessions. In subprocess mode, the daemon extracts the
   `session_id:` line from spawned stdout and stores it in the ledger as
   `spawned_session_id`. In library mode, the session_id is obtained directly
   from the AIAgent object. This enables session tracking and potential
   `--resume` in future iterations.

3. **Checkpoints Flag (`--checkpoints`)** — Enables file checkpoints in spawned
   sessions. Passes `--checkpoints` to the spawned `chat -q` command
   (subprocess mode) or sets `checkpoints_enabled=True` (library mode).
   Auto-enabled when `--git` is set.

**v11.10.0 enhancements — Banner cleanup, dashboard version sync, worker bugfix (iteration #7)**:

1. **Fixed `output_cap` in worker URL mode** — The worker HTTP code path used a hacky
   `"output_cap" in dir()` fallback to cap the summary field. Now properly calculates
   the cap from `max_output_chars` or stdout/raw length. No more potential NameError.

2. **All banners synced to VERSION constant** — The DAEMON log banner (was listing only
   v11.7.0 features), the startup banner (was listing only v11.8.0 features), and the
   HTML dashboard header/footer (was hardcoded as v11.8.0) now all use `{VERSION}` and
   reflect all current features including push notifications.

3. **HTML dashboard version dynamic** — Header `<h1>` and footer now use `{VERSION}`
   placeholder, replaced at render time via `.replace("{VERSION}", LAUNCH_LOOP_VERSION)`.
   No more stale version numbers in the HTML output when the daemon is updated.

4. **DAEMON log banner completeness** — The per-iteration log banner now lists all
   features: Pushbullet/ntfy push notifications, preflight checks, /api/status, REST
   control, dashboard v2, config file, desktop notifications, startup delay, error
   classification.

**Two modes**: The daemon (launch-loop.py) runs in the background for autonomous
looping. The **session-self-loop** pattern runs inside your current Hermes session
for self-enhancement — no separate daemon, no child sessions, full visibility.

**v11.9.0 enhancements — Pushbullet & ntfy push notifications (iteration #5)**:

1. **Pushbullet Mobile Notifications** — `--notify-pushbullet TOKEN` sends iteration results
   to your phone via Pushbullet. Each iteration gets a "Infinite Loop Iteration" push with
   the summary and duration. Completion sends full stats. Uses Pushbullet API v2 with
   stdlib urllib — no external dependencies. Get your API token at
   https://www.pushbullet.com/#settings.

2. **ntfy Push Notifications** — `--notify-ntfy TOPIC` sends pushes via ntfy.sh (or any
   self-hosted ntfy server). No API key required for public ntfy.sh. Configure a custom
   server with `--notify-ntfy-server URL`. Uses ntfy's simple HTTP PUT API.

3. **Unified Notification Dispatcher** — `_send_per_iteration_notifications()` sends to
   ALL configured channels (desktop notify-send, Pushbullet, and ntfy) in a single call.
   Each channel is independent — configure one, two, or all three. The completion
   notification also uses all channels when Pushbullet/ntfy tokens are provided.

4. **Dead Code Cleanup** — Removed the old v11.7.0 `_send_completion_notification()`
   (desktop-only) and replaced it with the new unified version that supports all
   notification channels.

**v11.8.0 enhancements — 4 new features**:

1. **Preflight Health Checks** — `--preflight` runs a comprehensive health check before the loop starts. It verifies the hermes binary is on PATH, workdir exists and is a directory, git repo is present (when `--git` is set), parent directories are writable, files are readable, webhook port is available, and disk has enough free space. Results are displayed in a clean table with ✓/✗ indicators. Use `--preflight-fail-fast` to stop on the first failure instead of running all checks.

2. **`/api/status` API Endpoint** — `GET /api/status` at the webhook port returns the full ledger state as JSON (not just the compact `/status` view). This enables external monitoring tools, custom dashboards, and scripts to consume the complete iteration state programmatically.

3. **REST API Control Endpoints** — `POST /control/stop`, `POST /control/pause`, and `POST /control/resume` let you control the loop via HTTP without touching the sentinel file. Each returns a JSON acknowledgement response. Perfect for integration with CI/CD pipelines, web UIs, and monitoring systems.

4. **Status Dashboard v2** — The `--status-html` dashboard now features auto-refresh every 30 seconds via `<meta http-equiv="refresh">`, an inline SVG favicon to eliminate browser console 404 errors, system resource cards (CPU, memory, RAM %) from `/proc` tracking data, an ETA column showing estimated time remaining, a cooldown indicator displaying the current cooldown delay, and dark/light mode support via `prefers-color-scheme`.

**v11.7.0 enhancements — 8 new features**:

1. **Daemon Status API** — The webhook server now serves `GET /api/status` returning the full iteration state as JSON (not just the compact `/status` endpoint). External monitoring tools, dashboards, and scripts can consume the complete ledger state programmatically.

2. **Desktop Notifications** — `--notify-desktop` sends a notification via `notify-send` after each iteration (Linux only). See the iteration summary, duration, and error status without checking the terminal.

3. **Config File Support** — `--save-config PATH` saves the current daemon configuration (all CLI flags) to a JSON file and exits. `--config PATH` loads a saved configuration, with CLI flags taking precedence over file values. Perfect for complex setups with many flags.

4. **Startup Delay** — `--startup-delay N` waits N seconds before the first iteration. Useful for debugging, coordinating with external services that need time to start, or delaying iteration start in CI/CD pipelines.

5. **Completion Notification** — `--notify-on-completion` sends a summary notification (via `notify-send`) when the daemon finishes, whether by reaching `--max-iterations`, convergence detection, sentinel file, or error. The notification includes iteration count, status, success/error counts, and total time.

6. **Error Classification** — Iteration errors are now classified in the ledger's `error_type` field as `timeout`, `network`, `schema`, or `unknown`. This enables better monitoring, alerting, and failure analysis without parsing free-text error messages.

7. **Expanded TASK_PATTERNS** — 50+ new keywords added across all six task types (research, code-fix, code-build, system-admin, data-processing, content), improving auto-detection accuracy for a wider range of goals and use cases without requiring explicit `--task-type`.

8. **`_sleep_with_shutdown_check` Helper** — Internal refactoring introduces a reusable helper for pause/sleep loops that respects shutdown signals. Used by startup delay and cooldown logic.

**v11.6.0 enhancements — 8 new features**:

1. **Structured Output Validation** — `--output-schema` and `--output-schema-file`
   accept JSON Schema files to validate spawned session output before accepting it.
   Uses stdlib-only validation (no jsonschema dependency): required fields, type
   checking, enum values, string length, integer range, and nested objects.
   If output fails validation, it's treated as a soft error in the ledger.

2. **System Resource Tracking** — stdlib-only CPU/memory tracking via `/proc`
   (no psutil dependency). Each iteration records RSS/virtual memory, CPU seconds
   used, and memory percentage in the ledger. Diagnose resource pressure without
   dropping into a shell.

3. **Adaptive Cooldown** — `--cooldown-mode adaptive` dynamically adjusts the
   delay between iterations based on average iteration duration. Short, fast
   iterations (< 15s) get longer cooldowns (rate-limit protection). Long iterations
   (> 5min) get minimal cooldown. The best of both worlds: rate-limit safe
   without wasting time between long tasks.

4. **Convergence Detection** — `--convergence-stop` monitors iteration summaries
   for repetitiveness using word-overlap Jaccard similarity. When N consecutive
   iterations say essentially the same thing, the daemon auto-stops (avoids
   spinning on converged tasks). Configurable via `--convergence-threshold`
   (0.0-1.0, default 0.9) and `--convergence-window` (default 5 iterations).

5. **Multi-Goal Parallel Workers** — When `--goals-file` and `--workers > 1` are
   used together, goals from the file are distributed ACROSS workers cyclically.
   Worker 0 gets goal 0, worker 1 gets goal 1, etc. Process a batch of 30 goals
   with 3 workers at once — each worker tackles a different goal in parallel.

6. **Git Diff Storage** — `--store-git-diff` captures the actual unified diff
   (not just `--stat`) in the ledger. Capped at 10KB per iteration to prevent
   ledger bloat. Review exactly what changed without shell access.

7. **Context Propagation** — Spawned sessions can now include a `context` field
   in their JSON output. This context is injected as the primary context for the
   NEXT spawned session, so iteration N+1 knows exactly what iteration N did,
   what files were changed, and where to pick up. This FIXES the core problem
   where spawned sessions started from scratch every iteration.

8. **Self-Modification Awareness** — When the goal mentions "infinite-loop",
   "launch-loop", or "skill", the spawned session automatically gets the skill
   directory path and self-modification instructions injected into its prompt.
  replaying the same goal. Wraps around by default; use `--stop-at-goals-end`
  to stop when all goals are exhausted. Perfect for batch processing:
  fix 50 lint errors, analyze 30 files, process 100 data shards.
- **Progress bar** — For bounded runs (`--max-iterations N`), the daemon now
  displays a compact visual progress bar after each iteration:
  `[████████░░░░░░░░░░] 40% (4/10, ETA: 5m)`
- **Context window tracking** — Each spawned session's prompt size (chars and
  estimated tokens) is logged in the daemon output, so you can see when
  prompts are approaching model context limits.
- **Signal-safe shutdown** — The daemon now writes the ledger immediately on
  SIGTERM/SIGINT (via a signal-safe write to a temp file with atomic rename),
  so mid-subprocess kills no longer lose iteration data. The shutdown signal
  handler persists the current state before Python's normal shutdown logic runs.
- **Self-modification (need_reload implemented)** — The previously
  documentation-only `need_reload` signal is now actually detected and handled.
  When a spawned session modifies `launch-loop.py`, the skill files, or daemon
  config, it includes `"next_goal": "NEXT_ITERATION need_reload"` in its JSON
  output. The daemon detects this, persists the ledger, stops the worker if
  running, and calls `os.execv()` to restart with the updated code.
- **Self-modification prompt instructions** — Spawned sessions now receive
  explicit instructions about the self-modification pattern: use
  `delegate_task()` to dispatch a subagent that makes file changes via
  `write_file`/`patch`, wait for the subagent result, then signal
  `need_reload` in the JSON output. This is Approach D from the skill docs.

**v11.6.0 enhancements — 5 fixes and improvements**:

1. **Fixed version header** — The daemon's docstring said `v11.0.0` since the
   v10.0.0→v11.0.0 rewrite, while the actual code was at v11.5.0. Now synced
   to the actual version number.

2. **`--version` flag** — `launch-loop.py --version` now prints the version
   string (`infinite-loop daemon v11.6.0`) and exits. Useful for scripting and
   CI/CD pipelines.

3. **`VERSION` constant** — Introduced `VERSION = "11.6.0"` as the single
   source of truth at the top of `launch-loop.py`. All version strings
   (docstring, startup banner, daemon log, `--version` output) derive from
   this constant.

4. **Multi-worker context merging fix** — Previously, when `--workers > 1`,
   the daemon only used the context from the **last** worker that provided one.
   Now all worker contexts are collected and combined, each prefixed with its
   worker ID (`[Worker #0]: ...`). This ensures all parallel work streams are
   visible to the next iteration.

5. **session-self-loop.py updated to v2.0.0** — The in-session self-loop script
   was significantly outdated (v1.0.0). v2.0.0 adds: `--workdir`, `--timeout`,
   `--goal-file`, `--initial-goal`, `--compact-every`, convergence detection
   (Jaccard word-overlap similarity), `--status-file` support, progress
   tracking with duration/stat reporting, and improved polling with adaptive
   sleep intervals.

**v11.6.1 bug fixes**:

1. **Fixed missing `logging.handlers` import** — The `_init_logger()` function uses
   `logging.handlers.RotatingFileHandler` but the module was never imported. When
   `--log-file` was used, the daemon crashed with `AttributeError: module 'logging'
   has no attribute 'handlers'`. Added `import logging.handlers`.

2. **Fixed `os.sysconf_names` KeyError on some Python builds** — The system resource
   tracking code used `os.sysconf_names["SC_CLK_TCK"]` which may raise `AttributeError`
   or `KeyError` on Python builds where this constant isn't available. Added a
   try/except fallback that defaults to 100 (Linux standard `CLK_TCK`).

3. **Updated docstring to match actual default toolsets** — The daemon's docstring
   claimed `terminal,file,delegation` as the default toolsets, but the actual default
   is the full `BASE_TOOLSETS` (including web, skills, browser, memory, etc.). Fixed
   the docstring to reflect reality.

4. **Added missing flags to run-loop.sh** — The `run-loop.sh` wrapper was missing
   forwarding for 7 CLI flags: `--webhook-port`, `--log-file`, `--log-max-mb`,
   `--status-html`, `--watch-dir`, `--watch-poll`, `--worker-url`. These are now
   properly forwarded to the daemon.

5. **Stored output schema config in ledger** — Added `output_schema_file` and
   `output_schema_inline` fields to the ledger state for traceability.

**v11.3.0 enhancements**:
- **Hermes Worker mode** — `--worker-url auto` (new default) auto-starts an
  embedded Hermes Worker HTTP server on a random port. The daemon manages
  lifecycle: starts it on init, uses it for all spawned sessions, kills it
  on exit. No separate terminal or management needed.
- **Self-reference support** — spawned sessions that modify `launch-loop.py` or
  the skill file itself can signal `NEXT_ITERATION need_reload` in their JSON
  output; the daemon detects this and calls `os.execv()` to restart with the
  updated code. See `references/hermes-worker.md` for details.
- **Hermes Worker server** at `~/.hermes/plugins/hermes-mcp-worker/main.py` —
  stdlib-only HTTP server, can also be started externally with `--port 8124`.

**v11.2.0 enhancements**:
- **Webhook mode** — `--webhook-port 8080` starts a lightweight HTTP server.
  POST `/webhook` with optional JSON body to trigger the next iteration.
  GET `/health` and GET `/status` for monitoring. Uses Python stdlib only.
- **File watcher** — `--watch-dir /path/to/dir` polls a directory/file for
  changes using `os.stat()` polling (no external dependencies). Triggers an
  iteration when any file is modified.
- **Daemon log file** — `--log-file /tmp/infinite-loop.log` writes structured
  logs to a file alongside stdout. Auto-rotates at configurable size
  (`--log-max-mb N`, default 10MB).
- **Status HTML dashboard** — `--status-html /tmp/loop-status.html` generates
  a self-contained HTML page with iteration history, stats, progress bar,
  and error highlights. Updated after each iteration.
- **ETA tracking** — per-task-type average duration tracking with remaining
  time estimation for `--max-iterations` runs. Displayed in daemon logs and
  inspect-ledger output.

## Architecture

```
You (current Hermes agent session)
  │
  └─ terminal(command="python3 launch-loop.py --goal ... --run", background=true)
      │
      │  launch-loop.py loops in the background:
      │
      ├─ iter 1: spawn `hermes chat -q "<prompt>" -t terminal,file,delegation,web,skills,browser,memory,session_search -Q --max-turns 500`
      │            ↓
      │            Session stays alive for up to 500 turns (NOT -z oneshot)
      │            ↓
      │            Does direct work via terminal/file tools
      │            AND/OR delegates subtasks via delegate_task()
      │            ↓
      │            Subagents can delegate further (multi-level trees)
      │            ↓
      │            Subagent results arrive while session is alive
      │            ↓
      │            Prints JSON summary → daemon parses it → loops
      │
      ├─ iter 2: same (or evolved goal with --evolve)
      │
      └─ ... until stop sentinel or max_iterations
```

## How It Works

A Python daemon runs via `terminal(background=true)`. On each iteration, it
spawns a fresh `hermes chat -q "<prompt>" -t terminal,file,delegation,web,skills,browser,memory,session_search -Q --max-turns 500`
session — the spawned session gets full autonomy and stays alive for up to
500 turns (unlike `-z` oneshot).

The spawned session can:
- Read files with `read_file` / `search_files`
- Run commands with `terminal`
- Make changes with `patch` / `write_file`
- Run sandboxed Python with `code_execute` (via `code_execution` toolset)
- Track progress with `todo()` in-session
- Analyze images with `vision_analyze()`
- **Delegate subtasks with `delegate_task()`** — and receive their results
- Search the web with `web_search` / `web_extract`
- Load workflows with `skill_view` / `skills_list`
- Browse web pages with the browser tool
- **Save findings with `hindsight_retain` / `memory`** — cross-iteration persistence
- **Recall past discoveries with `hindsight_recall` / `session_search`** — learn from previous iterations
- **Query Chroma/Cognee** — vector and knowledge graph search across all past data
- **Subagents can also delegate** — build multi-level delegation trees

It then prints a JSON summary line with what it actually did, and the daemon
captures it using the multi-line brace-counting parser.

The daemon manages:
- **Iteration state** — JSON ledger at `/tmp/infinite-loop-state.json`
- **Git snapshots** — captures diff stats before/after each iteration
- **Auto-commit** — commits changes after each iteration (optional)
- **Evolution** — each iteration can propose the next goal (self-directing)
- **Parallel workers** — run N concurrent Hermes sessions per iteration
- **Sentinel shutdown** — `echo "stop" > /tmp/infinite-loop-stop`
- **Idle detection** — stops after N iterations with no git changes
- **Status file** — writes one-line JSON for external monitoring
- **Notification callback** — runs a shell command after each iteration

## Prerequisites

- `hermes` on PATH — the daemon runs `hermes chat -q "<prompt>"` as a subprocess
- A working Hermes config (same model/provider as your session)
- Python 3.10+ (standard library only — no pip dependencies)

## How to Use

### Basic Loop

```bash
# This is executed inside the Hermes agent session:
terminal(command="""
python3 scripts/launch-loop.py \
  --goal "Refactor the auth module to use JWT tokens" \
  --context "Code lives in src/auth/. Respond in English." \
  --workdir /home/nekophobia/Projects/myapp \
  --run
""", background=true, timeout=300)
```

The command returns immediately (it runs in background). The daemon starts looping.

### Monitor Progress

```bash
terminal(command="cat /tmp/infinite-loop-state.json | python3 -m json.tool")
terminal(command="bash scripts/inspect-ledger.sh")
terminal(command="bash scripts/inspect-ledger.sh --watch")
terminal(command="bash scripts/inspect-ledger.sh --summary")
```

**Note on real-time monitoring from the parent Hermes session**: The daemon
runs via `terminal(background=true)`. Its stdout is buffered and may not
appear in the parent session's output. The JSON ledger at
`/tmp/infinite-loop-state.json` is always authoritative — poll it with
`cat` or the inspect scripts to see actual progress. The `--notify-cmd` and
`--status-file` flags provide out-of-band monitoring paths.

To check if spawned sessions are running:
```bash
# Check if the daemon process exists
ps aux | grep launch-loop | grep -v grep

# Check if spawned hermes sessions exist
ps aux | grep "hermes chat" | grep -v grep

# Check the ledger for iteration results
python3 -c "import json; d=json.load(open('/tmp/infinite-loop-state.json')); print(f'Status: {d.get(\"status\")}'); print(f'Iterations: {d.get(\"total_iterations\")}')"
```

### Stop the Loop

```bash
terminal(command="echo 'stop' > /tmp/infinite-loop-stop")
```

Or set `--max-iterations N` for auto-stop after N iterations.

### Pause and Resume the Loop

```bash
# Pause — the daemon suspends after checking the sentinel on the next iteration
echo "pause" > /tmp/infinite-loop-stop

# Resume — the daemon continues
echo "resume" > /tmp/infinite-loop-stop

# Or just delete the sentinel file to resume
rm /tmp/infinite-loop-stop

# Stop from paused state
echo "stop" > /tmp/infinite-loop-stop
```

When paused, the daemon polls the sentinel file every 5 seconds. Writing
"resume" or deleting the file lets it continue. Writing "stop" terminates
the daemon.

## Cooldown Mode (Rate-Limit Awareness)

With `--cooldown N`, the daemon waits N seconds between iterations, regardless
of success or failure. This is useful when many short iterations would hit API
rate limits.

```bash
# Wait 15 seconds between each iteration
python3 scripts/launch-loop.py --goal "Fix lint errors" \
    --cooldown 15 --max-iterations 50 --run
```

The cooldown sleeps in 1-second increments, checking for shutdown signals
during each tick, so the daemon still stops promptly when sentinel is set.

## Goals File (Batch Processing)

With `--goals-file PATH`, each iteration uses the next goal from the file
instead of reusing the same `--goal`. This is perfect for batch processing:

```bash
# goals.txt:
# Fix type errors in src/auth/login.py
# Fix type errors in src/api/users.py
# Fix type errors in src/db/models.py

python3 scripts/launch-loop.py \
    --goals-file /tmp/goals.txt \
    --workdir /home/nekophobia/Projects/myapp \
    --git --max-iterations 50 --run
```

The file format:
- One goal per line
- Lines starting with `#` are ignored as comments
- Non-empty lines become goals
- Default behavior: goals wrap around (reuse cyclically)
- With `--stop-at-goals-end`: loop stops when all goals are exhausted

Each iteration records which goal it used in the ledger.

## Progress Bar

For bounded runs (`--max-iterations N`), the daemon displays a compact
visual progress bar after each iteration. Example daemon log output:

```
[01:23:45] [PROGRESS] [████████░░░░░░░░░░] 4/10 (40%) | ETA: 15m
```

The progress bar uses Unicode block characters and always shows:
- Filled blocks (█) for completed fraction
- Empty blocks (░) for remaining fraction
- Numeric progress (iterations done / total)
- Percentage
- ETA (estimated time remaining)

## Context Window Tracking

Each spawned session's prompt size (in chars and estimated tokens) is logged
in the daemon output. This helps you monitor when prompts are approaching
model context limits:

```
[01:23:45] [SPAWN] Prompt: ~4,200 chars (~1,050 tokens)
```

If you see prompts growing large, consider:
- Using `--compact-every N` more aggressively (lower N)
- Using `--keep-iterations N` to shrink the ledger
- Setting `--prompt-suffix` to reduce context injection

## All Options

| Flag | Default | Description |
|------|---------|-------------|
| `--goal` | (required) | Core task description for spawned sessions |
| `--context` | `""` | Initial context (paths, constraints, language) |
| `--context-file` | `""` | Path to file containing context (alternative to --context) |
| `--workdir` | cwd | Working directory |
| `--toolsets` | `terminal,file,delegation,web,skills,browser,memory,session_search,code_execution,todo,vision` | Toolsets for spawned sessions |
| `--max-iterations` | `0` | Stop after N iterations (0 = infinite) |
| `--max-turns` | `500` | Max turns per spawned Hermes session (deep delegation) |
| `--compact-every` | `5` | Compact context every N iterations |
| `--retry-delay` | `0` | Backoff seconds on consecutive errors |
| `--session-timeout` | `7200` | Max seconds per spawned Hermes session |
| `--shutdown-sentinel` | `/tmp/infinite-loop-stop` | Sentinel file path |
| `--evolve` | `false` | Let each iteration propose the next goal |
| `--git` | `false` | Capture git diff stats per iteration |
| `--git-commit` | `false` | Auto-commit changes (implies --git) |
| `--workers` | `1` | Run N concurrent Hermes sessions per iteration |
| `--notify-cmd` | `""` | Shell command after each iteration (JSON on stdin) |
| `--http-callback` | `""` | HTTP POST URL for iteration JSON (alternative to --notify-cmd) |
| `--max-output-chars` | `2000` | Max chars of spawned output to store (0=unlimited) |
| `--max-idle-iterations` | `0` | Stop after N iterations with no git changes (needs --git) |
| `--max-retries` | `0` | Retry a failed iteration up to N times (0=no retry) |
| `--on-error-cmd` | `""` | Shell command when an iteration fails (JSON on stdin) |
| `--tag` | `""` | Label/identifier for the run (e.g. 'fix-auth-2026') |
| `--prompt-suffix` | `""` | Extra text appended to every spawned prompt |
| `--force-reset` | `false` | Clear existing ledger and start fresh |
| `--status-file` | `""` | Write one-line JSON status file for external monitoring |
| `--profile` | `""` | Hermes profile for spawned sessions (e.g. 'work') |
| `--model` | `""` | Model override for spawned sessions |
| `--provider` | `""` | Provider override for spawned sessions |
| `--dry-run` | `false` | Print config and exit without spawning any sessions |
| `--keep-iterations` | `0` | Auto-shrink ledger to last N iterations (0=keep all) |
| `--run` | `false` | Start the actual loop (without it, prints config and exits) |
| `--no-auto-toolsets` | `false` | Disable automatic toolset enrichment based on task type |
| `--no-failure-learning` | `false` | Disable injection of past failure context into spawned sessions |
| `--task-type` | `auto` | Force task type (research/code-fix/code-build/system-admin/data-processing/content/general) |
| `--webhook-port` | `0` | Port for HTTP webhook server (0=disabled). POST /webhook triggers iteration, GET /health and GET /status for monitoring |
| `--log-file` | `""` | Path to daemon log file (e.g. /tmp/infinite-loop.log). Adds file logging alongside stdout |
| `--log-max-mb` | `10` | Max log file size in MB before rotation (only with --log-file) |
| `--status-html` | `""` | Path to self-contained HTML status dashboard (e.g. /tmp/loop-status.html). Updated after each iteration |
| `--watch-dir` | `""` | Watch a directory/file for modifications via os.stat() polling. Triggers an iteration on change |
| `--watch-poll` | `5.0` | File watcher poll interval in seconds (only with --watch-dir) |
| `--worker-url` | `"auto"` | Hermes Worker mode. `"auto"` (default) = daemon auto-starts an embedded worker on a random port. `"http://host:port"` = connect to external worker. `""` = direct subprocess mode (no worker). See «Hermes Worker Mode» section. |
| `--cooldown` | `0` | Wait N seconds between iterations. Useful for rate-limit awareness when many short iterations would hit API limits. The daemon sleeps in 1s increments and checks for shutdown signals during the cooldown. |
| `--cooldown-mode` | `"fixed"` | Cooldown mode: `fixed` = wait exactly --cooldown seconds (default), `adaptive` = auto-calculate delay based on average iteration duration. Fast iterations get longer cooldowns (rate-limit protection), long iterations get shorter cooldowns. |
| `--goals-file` | `""` | Path to a file with one goal per line. Each iteration uses the next goal from the file instead of reusing the same --goal. Lines starting with `#` are ignored. Wraps around by default (repeats from the start). |
| `--stop-at-goals-end` | `false` | When used with `--goals-file`, stop the loop when all goals are exhausted instead of wrapping around and reusing them. |
| `--output-schema` | `""` | Inline JSON Schema as JSON string to validate spawned session output. Uses stdlib-only validation (required fields, types, enum, length/range checks). |
| `--output-schema-file` | `""` | Path to a JSON Schema file for spawned output validation. Alternative to --output-schema for complex schemas. |
| `--convergence-stop` | `false` | Auto-stop when N consecutive iterations produce similar summaries (stuck detection). Uses word-overlap Jaccard similarity. |
| `--convergence-threshold` | `0.9` | Similarity threshold for convergence detection (0.0-1.0). Higher = more permissive, Lower = more aggressive. |
| `--convergence-window` | `5` | Number of recent iterations to compare for convergence. All pairs in the window must exceed the threshold. |
| `--store-git-diff` | `false` | Store the actual git diff (not just stats) in the ledger. Capped at 10KB per iteration to prevent ledger bloat. |
| `--startup-delay` | `0.0` | Wait N seconds before the first iteration. Useful for debugging or coordinating with external services that need time to start. |
| `--notify-desktop` | `false` | Send desktop notifications via notify-send after each iteration (Linux only). Shows summary, duration, and error status. |
| `--notify-on-completion` | `false` | Send a summary notification when the daemon finishes (all iterations done, convergence, error, or manual stop). Includes iteration count, status, and stats. |
| `--save-config` | `` | Save current configuration to a JSON file and exit. All CLI flags are serialized for later reloading with `--config`. |
| `--config` | `` | Load daemon configuration from a JSON file (previously saved with `--save-config`). CLI flags override corresponding file values. |
| `--preflight` | `false` | Run comprehensive health checks before the loop starts. Verifies hermes binary, workdir, git repo, sentinel writability, file readability, port availability, and disk space. Results shown in a table with ✓/✗ indicators. |
| `--preflight-fail-fast` | `false` | When used with `--preflight`, stop on the first failing check instead of running all checks. Exits with a non-zero code and error message. |
| `--notify-pushbullet` | `` | Pushbullet API access token for mobile notifications. Sends iteration results to your phone via push. Get token at https://www.pushbullet.com/#settings. |
| `--notify-ntfy` | `` | ntfy topic name for push notifications. Sends iteration results via ntfy.sh (or your own server with --notify-ntfy-server). Example: 'my-loop-alerts' |
| `--notify-ntfy-server` | `https://ntfy.sh` | ntfy server URL. Use a self-hosted ntfy server URL for private notifications. Default uses the public ntfy.sh. |
| `--use-library` | `false` | Use AIAgent.run_conversation() in-process instead of spawning a subprocess. Falls back to subprocess mode automatically if AIAgent is not importable. Incompatible with --workers > 1. |
| `--pass-session-id` | `false` | Pass session ID to spawned sessions. The daemon extracts the session_id line from spawned stdout and stores it in the ledger as spawned_session_id. In library mode, obtained directly from AIAgent. |
| `--checkpoints` | `false` | Enable file checkpoints in spawned sessions. Passes --checkpoints to spawned chat -q or sets checkpoints_enabled=True in library mode. Auto-enabled when --git is set. |
| `--resume` | `false` | Chain spawned sessions across iterations — each new session inherits the full conversation history of the previous one via `hermes --resume SESSION_ID chat -q`. Requires `--pass-session-id`. |
| `--skills` | `` | Skills to preload in spawned Hermes sessions (comma-separated, e.g. `python-debug,code-review`). Passed as `-s SKILLS` to spawned `chat -q`. |
| `--ignore-rules` | `false` | Start spawned sessions without loading AGENTS.md, memory, or rules. Creates a clean-slate session for isolated, reproducible runs. |
| `--yolo` | `false` | Bypass all dangerous command approval prompts in spawned sessions. Combine with `--ignore-rules` for fully autonomous operation. |
| `--ignore-user-config` | `false` | Pass `--ignore-user-config` to spawned sessions so they skip `~/.hermes/config.yaml`. |
| `--spawn-source` | `` | Source tag for spawned sessions (passed as `--source` to `hermes chat -q`). Use `infinite-loop` to distinguish loop sessions. |
| `--safe-mode` | `false` | Troubleshooting mode: disable ALL customizations in spawned sessions — user config, AGENTS.md/memory injection, plugins, MCP servers. Implies `--ignore-user-config` and `--ignore-rules`. Subprocess mode only. |
| `--accept-hooks` | `false` | Auto-approve shell hooks in spawned sessions without a TTY prompt. Passes `--accept-hooks` to spawned `hermes chat -q`. Subprocess mode only. |
| `--worktree` | `false` | Run spawned sessions in an isolated git worktree. Passes `--worktree` to spawned `hermes chat -q`. Subprocess mode only. |
| `--continue` | `false` | Resume the most recent session in spawned sessions. Passes `--continue` to spawned `hermes chat -q`. Subprocess mode only. |
| `--self-test` | `false` | Run in-process self-tests (groups/cases auto-detected at runtime) and exit without spawning any sessions. Tests JSON parsing, error classification, text similarity, convergence detection, schema validation, adaptive cooldown, GoalSpec parsing, progress classification, and actionable suggestions. |
| `--track-goals` | `false` | Track completed goals in the ledger when using --goals-file. Completed goals are automatically skipped on restart (avoids re-doing work after crashes). |
| `--reset-goals` | `false` | Clear the goals_completed tracking in the ledger for a fresh start. Use with --goals-file when you want to re-execute all goals. |

## How the Loop Actually Works

Step by step:

1. **You (Hermes agent)** run the daemon via `terminal(background=true)`
2. **Daemon** auto-detects the task type from the goal and enriches toolsets
3. **Daemon** spawns `hermes chat -q "<prompt>" -t terminal,file,delegation,... -Q --max-turns 500` on each iteration
4. **Spawned Hermes** gets task-optimized prompts, past failure context, and the right tools — full autonomy
5. **Spawned Hermes** stays alive for multiple turns (not -z oneshot), so delegate_task() results arrive
6. **Spawned Hermes** can build deep delegation trees: it delegates → subagents delegate → sub-subagents work
7. **Spawned Hermes** prints a JSON summary line with what it did
8. **Daemon** parses the JSON (multi-line brace-counting), captures git state, writes to ledger
9. **Daemon** loops back to step 2 (or exits if max_iterations/sentinel is hit)

The JSON that the spawned session must print on its last line:
```json
{"summary": "what was done with details", "duration_seconds": 123, "error": null, "next_goal": "optional next step if --evolve", "context": "detailed context for the next iteration to continue from here"}
```

The `context` field is critical for iterative work — it tells the NEXT spawned
session what was done, what files changed, and where to pick up. Without it,
each iteration starts from scratch.

## Evolution Mode (Self-Directing Loop)

With `--evolve`, each iteration proposes the next goal. The spawned session includes a `next_goal` field in its JSON output, and the daemon uses it as the goal for the next iteration. This creates a self-directing improvement loop where the LLM decides what to focus on next.

## Parallel Workers

With `--workers N`, the daemon spawns N concurrent Hermes sessions per iteration. Each worker gets the same goal and context, but with a worker ID so they know which parallel slice they own.

Use this for batch processing where work can be divided:
- `--workers 3` for fixing errors across 3 modules
- `--workers 5` for processing 5 dataset shards

### Multi-Goal Parallel Workers (v11.6.0)

When `--goals-file` is used together with `--workers > 1`, goals from the file
are distributed ACROSS workers cyclically instead of giving all workers the same
goal. Worker 0 gets goal 0, worker 1 gets goal 1, worker 2 gets goal 2, etc.

```bash
# Process 30 type-fix goals with 3 workers — each worker gets a different goal
python3 scripts/launch-loop.py \
    --goals-file /tmp/type-fix-goals.txt \
    --workers 3 \
    --workdir /home/nekophobia/Projects/myapp \
    --git --max-iterations 30 --run
```

In this example, each of the 3 workers tackles a different goal in parallel.
After all 3 finish, the daemon moves to the next 3 goals. Total iterations
still counts each goal individually so `--max-iterations` limits total work.

## Git Integration

With `--git`, the daemon captures git diff stats before and after each iteration. With `--git-commit`, it auto-commits changes with a descriptive message.

Idle detection (`--max-idle-iterations`) monitors git changes — if N consecutive iterations produce no file changes, the daemon stops (avoids infinite loops on converged codebases).

### Git Diff Storage (v11.6.0)

With `--store-git-diff`, the daemon stores the actual unified diff in the
ledger iteration record (not just `--stat`). Capped at 10KB per iteration:

```bash
python3 scripts/launch-loop.py --goal "Fix type errors" \
  --git --store-git-diff --run
```

The diff is stored in the `git_after.diff` field of each iteration record.
Combine with `--keep-iterations N` to limit ledger growth. Review changes
by inspecting the ledger JSON directly:

```bash
python3 -c "import json; d=json.load(open('/tmp/infinite-loop-state.json')); it=d['iterations'][-1]; print(it.get('git_after',{}).get('diff','(no diff)'))"
```

## Structured Output Validation (v11.6.0)

With `--output-schema` or `--output-schema-file`, you can validate that spawned
sessions return well-formed output before the daemon accepts it. If validation
fails, the error is recorded in the ledger as a soft error (treated as a failed
iteration for retry purposes).

```bash
# Inline schema (simple — validates summary and duration_seconds exist)
python3 scripts/launch-loop.py --goal "Fix type errors" \
  --output-schema '{"type":"object","required":["summary","duration_seconds"],"properties":{"summary":{"type":"string","minLength":5},"duration_seconds":{"type":"integer"}}}' \
  --max-retries 2 --run

# Schema file (complex — email notifications with specific fields)
python3 scripts/launch-loop.py --goal "Send batch emails" \
  --output-schema-file /tmp/email-schema.json --run
```

The validator uses stdlib only (no `jsonschema` dependency) and supports:
- Required fields, type checking (string, integer, number, boolean, object, array)
- Enum values, string min/max length, integer min/max range
- Nested object properties (1 level deep)

## Adaptive Cooldown (v11.6.0)

With `--cooldown-mode adaptive`, the daemon dynamically calculates the delay
between iterations based on average iteration duration. Short, fast iterations
get longer cooldowns (protecting against API rate limits). Long, slow iterations
get shorter cooldowns (avoiding wasted idle time between expensive tasks).

```bash
# Adaptive cooldown — auto-calculated from average iteration duration
python3 scripts/launch-loop.py --goal "Fix lint errors" \
  --cooldown-mode adaptive --max-iterations 50 --run

# Can combine with --cooldown as a fallback for the first iteration
python3 scripts/launch-loop.py --goal "Fix lint errors" \
  --cooldown 5 --cooldown-mode adaptive --max-iterations 50 --run
```

How it works:
- Iterations < 5s → 60s cooldown (rate-limit protection)
- Iterations 5-15s → 30s cooldown
- Iterations 15-300s → linear interpolation between 30s and 2s
- Iterations > 300s → 2s cooldown (minimal delay)

## Convergence Detection (v11.6.0)

With `--convergence-stop`, the daemon monitors iteration summaries for
repetitiveness and auto-stops when the agent is stuck in a loop — producing
essentially the same output every time without making real progress.

```bash
# Stop if 5 consecutive iterations have >90% similar summaries
python3 scripts/launch-loop.py --goal "Refactor auth" \
  --convergence-stop --run

# More sensitive: stop if 3 iterations have >70% similar summaries
python3 scripts/launch-loop.py --goal "Fix lint errors" \
  --convergence-stop --convergence-window 3 --convergence-threshold 0.7 --run
```

The detection uses word-overlap (Jaccard) similarity:
- 1.0 = identical summaries (identical word sets)
- 0.5 = half the words overlap
- 0.0 = completely different

When triggered, the daemon writes `stopped: convergence` to the ledger with
the average similarity and window size.

## Output Progress Classification (v13.0.0)

Each iteration is now classified to indicate whether the loop is making
meaningful progress, stuck, or done. The classification is stored in each
iteration's record as the `classification` field and uses 6 categories:

| Classification | Meaning | Example summary |
|---------------|---------|-----------------|
| `completed` | Goal explicitly declared done | "All 15 type errors fixed" |
| `progress` | Changes were made, not done yet | "Fixed 5/15 type errors" |
| `partial` | Some analysis done, no changes | "Analyzed the auth module" |
| `stuck` | No changes, short/repetitive output | "Can't reproduce the bug" |
| `regression` | Error occurred after progress | "Tests failing after refactor" |
| `unknown` | Default when no pattern matches | (miscellaneous) |

The classification is heuristic-based (keyword matching + git diff checking) —
no model calls are needed per iteration. It's stored in the ledger as:

```json
{
  "iterations": [
    {
      "classification": "progress",
      "summary": "Fixed 5/15 type errors in the API layer"
    }
  ]
}
```

Use cases:
- **Dashboard color-coding**: green=completed, blue=progress, yellow=partial, red=stuck, orange=regression
- **Smarter auto-stop**: stop after N consecutive "stuck" classifications
- **Monitoring**: quickly identify unproductive loops

## System Resource Tracking (v11.6.0)

Every iteration now captures CPU and memory usage from `/proc` (Linux) —
no psutil dependency needed. The data is stored in each iteration's `system`
field in the ledger:

```json
{
  "system": {
    "cpu_seconds_used": 12.345,
    "memory_rss_mb": 156.2,
    "memory_vms_mb": 890.1,
    "memory_percent": 0.019,
    "memory_peak_mb": 200.4
  }
}
```

This helps diagnose resource pressure without dropping into a shell. On macOS,
resource tracking silently returns empty dicts (no `/proc` available).

## Profile, Model, and Provider Overrides

With `--profile`, `--model`, and `--provider`, you can control which Hermes
profile and LLM configuration the spawned sessions use.

Example:
```bash
python3 scripts/launch-loop.py --goal "Fix type errors" \
  --profile work --model "anthropic/claude-sonnet-4" --run
```

## HTTP Callback

With `--http-callback URL`, the daemon POSTs a JSON payload to the specified URL
after each iteration.

## Webhook Mode

With `--webhook-port PORT`, the daemon starts a lightweight HTTP server that runs
alongside the main loop. It provides:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Returns `{"status": "ok"}` when the daemon is running |
| `/status` | GET | Returns current iteration count, success/error counts, and status |
| `/webhook` | POST | Triggers the next iteration. Optional JSON body: `{"goal": "override goal", "context": "override context"}` |

All endpoints use stdlib `http.server` — no external dependencies. The server
runs in a daemon thread alongside the main loop.

```bash
# Start with webhook mode
python3 scripts/launch-loop.py --goal "Fix lint errors" --webhook-port 8080 --run

# Trigger an iteration from another process
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"goal": "Fix only the Python files"}'

# Check health
curl http://localhost:8080/health

# Get status
curl http://localhost:8080/status
```

## File Watcher Mode

With `--watch-dir PATH`, the daemon polls a directory or file for changes
using `os.stat()` mtime polling — no external dependencies like inotify needed.
When a file modification is detected, the next iteration is triggered.

```bash
# Trigger an iteration whenever any file in src/ changes
python3 scripts/launch-loop.py --goal "Fix type errors" \
  --watch-dir src/ --watch-poll 5.0 --run

# Trigger on a specific file
python3 scripts/launch-loop.py --goal "Process config" \
  --watch-dir /etc/myapp/config.yaml --run
```

The watcher uses polling (configurable via `--watch-poll`, default 5s), so it
works on any filesystem including NFS and FUSE mounts. The initial scan counts
as a "change" to trigger the first iteration immediately.

## Status HTML Dashboard

With `--status-html PATH`, the daemon generates a self-contained HTML page
after each iteration showing:

- Current status badge (running, paused, stopped)
- Iteration count, goal, timeline
- Stats cards (success, errors, total time, avg time)
- Progress bar (when --max-iterations is set)
- Iteration history table with error highlighting
- Dark theme (GitHub-dark inspired)

```bash
# Generate status page
python3 scripts/launch-loop.py --goal "..." \
  --status-html /tmp/loop-status.html --run

# Serve it (any static file server)
python3 -m http.server 8080 --directory /tmp/
# Then open http://localhost:8080/loop-status.html
```

**v11.8.0 Dashboard improvements**: The dashboard now auto-refreshes every 30
seconds (`<meta http-equiv="refresh">`), includes an inline SVG favicon to
eliminate browser console 404 errors, shows system resource cards (CPU, memory,
RAM %) from the `/proc` tracking data, displays an ETA column with estimated
time remaining, a cooldown indicator, and respects the system's dark/light mode
preference via CSS `prefers-color-scheme`.

## Self-Test Mode

With `--self-test`, the daemon runs ~40 in-process unit tests across 8 core
functions and exits (no child Hermes sessions are spawned). Each test function
runs multiple sub-tests with known inputs and expected outputs:

| Function | Sub-tests | What's tested |
|----------|-----------|---------------|
| `extract_json_from_output` | 6 | Single-line JSON, multi-line JSON, code-fenced JSON, embedded text with session_id lines, truncated brace edge case, broken JSON error handling |
| `classify_error` | 5 | Timeout messages, network/connection errors, JSON schema failures, unknown errors, empty/error-free output |
| `text_similarity` | 5 | Identical texts, completely different texts, partial overlap (Jaccard), one empty string, both empty strings |
| `check_convergence` | 3 | Below-threshold similarity, above-threshold similarity, empty/window-too-small edge case |
| `validate_json_output` | 4 | Valid schema match, missing required field, wrong type, empty schema/no validation required |
| `calc_adaptive_cooldown` | 4 | Very short iteration (<5s), medium (15s), long (>300s), edge case (0s) |
| `GoalSpec` parsing | 3 | Plain goal, pipe with profile override, pipe with all overrides |
| `_classify_progress` | 4 | Completed, progress with git diff, stuck with error, unknown/empty |

```bash
# Run self-tests
python3 scripts/launch-loop.py --self-test
# Output:
# [SELF-TEST] ✓ test_extract_json_output (6/6 cases passed)
# [SELF-TEST] ✓ test_classify_error (5/5 cases passed)
# [SELF-TEST] ✓ test_text_similarity (5/5 cases passed)
# [SELF-TEST] ✓ test_check_convergence (3/3 cases passed)
# [SELF-TEST] ✓ test_validate_json_output (4/4 cases passed)
# [SELF-TEST] ✓ test_calc_adaptive_cooldown (4/4 cases passed)
# [SELF-TEST] ✓ test_goal_spec (3/3 cases passed)
# [SELF-TEST] ✓ test_classify_progress (4/4 cases passed)
# Result: 8/8 tests passed, all OK
```

Self-test mode requires no external dependencies (stdlib-only) and is safe to
run in CI/CD pipelines. Use as a quick smoke test after updating the daemon.

## Preflight Health Checks

With `--preflight`, the daemon runs a comprehensive health check **before** the
loop starts — so you know everything is ready before the first iteration. This
catches common configuration errors early instead of failing silently on
iteration 1.

```bash
# Run preflight checks and start the loop
python3 scripts/launch-loop.py --goal "Fix lint errors" \
  --preflight --run

# Stop on first failure — exit immediately if any check fails
python3 scripts/launch-loop.py --goal "Fix lint errors" \
  --preflight --preflight-fail-fast --run
```

The following checks are performed:

| Check | What it validates |
|-------|-------------------|
| `hermes_binary` | `hermes` is on PATH and executable |
| `workdir_exists` | `--workdir` path exists (created if missing) |
| `workdir_is_dir` | `--workdir` is a directory, not a file |
| `git_repo` | Workdir has a `.git` directory (when `--git` is set) |
| `sentinel_writable` | Sentinel parent directory is writable |
| `file_readable` | `--context-file` exists and is readable |
| `port_available` | `--webhook-port` is not already in use |
| `disk_space` | At least 0.5 GB free on the target filesystem |

Each check prints a result row like:

```
  ✓ hermes_binary        found at /home/user/.local/bin/hermes
  ✗ port_available       port 8080 is in use: [Errno 98] Address already in use
```

With `--preflight-fail-fast`, the daemon exits immediately on the first ✗
instead of running all remaining checks. Use this in CI/CD pipelines where
a single misconfiguration should abort early.

## Daemon Log File

With `--log-file PATH`, the daemon writes structured logs to a file alongside
stdout output. Auto-rotates at a configurable size:

```bash
python3 scripts/launch-loop.py --goal "..." \
  --log-file /tmp/infinite-loop.log --log-max-mb 10 --run

# Tail the log while the daemon runs
tail -f /tmp/infinite-loop.log
```

## ETA Tracking

The daemon automatically tracks average iteration duration per task type.
When `--max-iterations` is set, it estimates remaining time and displays it
in the daemon's [STATS] log line and in `inspect-ledger.sh` output.

## Hermes Worker Mode (Self-Reference Support)

With `--worker-url auto` (the **default**), the daemon auto-starts an
embedded Hermes Worker HTTP server on a random port and uses it for all
spawned sessions. The worker runs as a child process and is automatically
killed when the daemon exits. No separate terminal, tmux, or management
needed — just invoke `--run` as usual.

With `--worker-url http://host:port`, you can connect to an externally-
managed worker (worker survives daemon restarts).

With `--worker-url ''`, direct subprocess mode (no worker, original
behavior).

This solves the **self-reference problem**: spawned sessions that modify
the daemon's own code or skill files are picked up on the next iteration
because each `/chat` call spawns a fresh `hermes chat -q`.

### How `auto` Mode Works

```
launch-loop.py --run
  │
  ├─ HermesWorkerManager.start()
  │   └─ binds random port via socket
  │   └─ spawns: python3 hermes-mcp-worker/main.py --port <random>
  │   └─ polls /health until ready (10s timeout)
  │   └─ if worker fails → falls back to direct subprocess
  │
  ├─ run_loop()
  │   └─ each iteration: POST /chat → worker → hermes chat -q → JSON
  │
  └─ on exit: atexit → worker_manager.stop() → kills child
```

The worker is a stdlib HTTP server (`http.server` + `urllib`). Source at
`~/.hermes/plugins/hermes-mcp-worker/main.py`.

### Self-Modification Signal

When a spawned session edits `launch-loop.py`, include `need_reload` in
its JSON:
```json
{"summary": "edited launch-loop.py", "next_goal": "NEXT_ITERATION need_reload"}
```
The daemon detects `need_reload` and calls `os.execv()` to restart with
updated code.

### Explicit Worker URL

```bash
# Terminal 1: Start an external worker
python3 ~/.hermes/plugins/hermes-mcp-worker/main.py --port 8124

# Terminal 2: Launch loop pointing at it
python3 scripts/launch-loop.py --goal "..." \
  --worker-url http://localhost:8124 \
  --run
```

Useful when iterating on launch-loop.py itself (worker survives restarts).

### Avoiding Worker Mode

```bash
python3 scripts/launch-loop.py --goal "..." --worker-url '' --run
```

## Delegation in Spawned Sessions (Deep Trees with Memory)

v11.0.0 defaults to `terminal,file,delegation,web,skills,browser,memory,session_search`
toolsets with 500 turns. Each spawned session can call `delegate_task()` to dispatch
background subagents, and THOSE subagents can also delegate — building
multi-level delegation trees for complex work.

Because the session uses `chat -q` (not `-z` oneshot), it stays alive for
all subagent results to arrive. With 500 turns, even the deepest delegation
chain has room to complete.

| Level | What they get | Example |
|-------|---------------|---------|
| V1 (spawned session) | terminal, file, web, skills, browser, memory, session_search, delegation | Reads code, delegates analysis, saves findings with hindsight_retain |
| V2 (subagent) | terminal, file (default), delegation allowed | Analyzes module, delegates sub-fixes, recalls past work |
| V3 (sub-subagent) | terminal, file (default) | Makes targeted file changes |

Cross-iteration knowledge flow:
1. **V1 spawn discovers a finding** → calls `hindsight_retain('lib X deprecated', tags=['project:fix-auth'])`
2. **Next iteration's V1** → calls `hindsight_recall(query='fix-auth')` at startup → knows about lib X
3. **V1 can also `session_search()`** → see what previous iterations actually did (not just summaries)
4. **Chroma & Cognee** → deeper vector/knowledge-graph search across all past data

The spawned session's prompt explains:
- Break goals into parallel sub-tasks and delegate them
- While subagents work, do direct work with your own tools
- Subagents can delegate further — build deep trees naturally
- **Save findings with hindsight_retain** for future iterations
- **Recall past discoveries with hindsight_recall** at the start of each iteration
- **Search past iterations with session_search** for full context
- Combine all results into the final output

## Dry-Run Mode

With `--dry-run`, the daemon prints its configuration and exits without spawning
any Hermes sessions.

## Replaying Archived Iterations

The `replay-ledger.sh` script reads an archived JSONL file and re-runs each
iteration's goal as a new infinite-loop daemon.

```bash
# Re-run all iterations from an archive
bash scripts/replay-ledger.sh ~/.hermes/infinite-loop-archives/iterations-20260625.jsonl

# Re-run with a custom goal prefix
bash scripts/replay-ledger.sh archive.jsonl --goal "Fix type errors"

# Re-run a subset
bash scripts/replay-ledger.sh archive.jsonl --from 3 --to 7

# Preview without running
bash scripts/replay-ledger.sh archive.jsonl --dry-run

# Read gzipped archives transparently
bash scripts/replay-ledger.sh archive.jsonl.gz
```

## Ledger Auto-Shrink

With `--keep-iterations N`, the daemon automatically trims the in-memory
ledger to the last N iterations when it reaches 2N entries.

```bash
# Keep only the last 50 iterations in the ledger
python3 scripts/launch-loop.py --goal "..." --keep-iterations 50 --run
```

## Retry Failed Iterations

With `--max-retries N`, the daemon automatically retries a failed iteration up
to N times before recording it as an error. Each retry uses an increasing backoff
(if `--retry-delay` is also set).

```bash
# Retry up to 3 times with backoff
python3 scripts/launch-loop.py --goal "fix lint errors" --max-retries 3 \
    --retry-delay 5 --run
```

## Error-Specific Callbacks

With `--on-error-cmd`, you can run a command ONLY when an iteration fails.

```bash
# Send a failure alert via desktop notification
python3 scripts/launch-loop.py --goal "..." \
    --on-error-cmd 'notify-send "Loop failed" "$(cat)"' --run
```

## Tagging Runs

With `--tag LABEL`, you can label a run with a project or run identifier.

```bash
python3 scripts/launch-loop.py --goal "fix type errors" --tag "project:hermes-v2" --run
```

## Custom Prompt Suffix

With `--prompt-suffix TEXT`, you can append extra instructions to every spawned
session's prompt.

```bash
python3 scripts/launch-loop.py --goal "refactor auth" \
    --prompt-suffix "Focus only on Python files. Do not modify tests." --run
```

## Force Reset

With `--force-reset`, the existing ledger is deleted before starting.

## Inspect

```bash
bash scripts/inspect-ledger.sh                              # default view
bash scripts/inspect-ledger.sh --watch                      # auto-refresh
bash scripts/inspect-ledger.sh --summary                    # compact one-liner
bash scripts/inspect-ledger.sh --json                       # machine-readable
bash scripts/inspect-ledger.sh --errors-only                # only failed iterations
bash scripts/inspect-ledger.sh --last 20                    # last 20 iterations
```

## Archive Auto-Mode

The `archive-state.sh --auto` mode archives all iterations and trims the
ledger to the last 100 entries in one shot:

```bash
bash scripts/archive-state.sh --auto
bash scripts/archive-state.sh --auto --gzip   # compress too
```

## JSON State Ledger

Location: `/tmp/infinite-loop-state.json`

```json
{
  "version": 11,
  "version_detail": "v12.0.0 -- Concurrent Library Mode (multiprocessing.Pool for --use-library + --workers > 1), Automatic Error Recovery (_adapt_to_error with per-type counters), In-Process Ledger Archiving (auto-archive trimmed iterations to gzip JSONL), Multi-Profile Goals File (pipe-separated goal|profile|model|provider format), Function Decomposition Phase 1 (5 helpers extracted from run_loop()), 3 new archive CLI flags: --archive-dir, --archive-retention, --archive-max-size",
  "initial_command": "refactor auth to use JWT",
  "started_at": "2026-06-25T19:30:00+00:00",
  ...
}
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/launch-loop.py` | Main daemon — spawns hermes chat -q with delegation, manages loop state |
| `scripts/session-self-loop.py` | In-session self-loop — run from your current Hermes session, no daemon needed |
| `scripts/run-loop.sh` | Unified wrapper entrypoint |
| `scripts/inspect-ledger.sh` | View ledger (one-shot, --watch, --summary, --json, --last N, --errors-only) |
| `scripts/archive-state.sh` | Archive old iterations to JSONL or Markdown (--auto, --gzip) |
| `scripts/replay-ledger.sh` | Re-run archived iterations from JSONL archives |
| `scripts/verify-delegation-config.sh` | Check Hermes delegation config (historical) |
| `~/.hermes/plugins/hermes-mcp-worker/main.py` | Hermes Worker HTTP server — stdlib-only, start with `--port 8124` |

## In-Session Self-Loop (for self-enhancement)

**This is what you want when the goal is to enhance Hermes itself or the
infinite-loop skill.** Instead of running a background daemon that spawns
anonymous child sessions, the **current Hermes session does the work directly**.

### Why the daemon doesn't work for self-enhancement

The daemon (`launch-loop.py`) spawns child Hermes sessions via `chat -q`.
Those children:

1. **Don't know where the skill files live** — they need explicit path context
2. **Have limited turn budgets** — enhancing multi-file skills eats turns fast
3. **Can't modify the parent** — they edit files and signal `need_reload`, but
   the parent daemon restarts; the USER's Hermes session is unaffected
4. **No visibility** — you can't see what the child is doing in real-time

### The in-session pattern

Instead of a background daemon, use **delegate_task() in a loop** from your
current Hermes session. Each iteration:

1. **Dispatches a subagent** via delegate_task() with the enhancement goal
2. **Waits for the subagent's result** — which includes file diffs, test results
3. **Evaluates the result** — was it successful? What's next?
4. **Loops** — calls delegate_task() again for the next improvement
5. **Stops** — when the goal is complete

The session's own tools (`read_file`, `patch`, `write_file`, `terminal`)
are available for verification between iterations.

### Example: Enhance the infinite-loop skill from your session

```
You (current session):
  Iteration 1 → delegate_task(goal="add output schema validation to launch-loop.py")
  ├─ Subagent reads launch-loop.py, adds the feature
  └─ Returns: "Added validate_json_output(), added --output-schema flag"
  
  Iteration 2 → delegate_task(goal="update SKILL.md to document output schema")
  ├─ Subagent reads SKILL.md, appends documentation
  └─ Returns: "Updated options table and added feature section"
  
  Iteration 3 → Verify
  └─ Your session uses read_file/terminal to confirm everything works
```

### Script-based helper

The `scripts/session-self-loop.py` script tracks iteration state in a JSON
file, so you can use it as a lightweight state tracker:

```bash
# Start the loop in background (it just tracks state)
python3 scripts/session-self-loop.py --max-iterations 10 &
LOOP_PID=$!

# Each iteration, update the state file after your work:
echo '{"summary": "added feature X", "next_goal": "add feature Y"}' > /tmp/session-loop-state.json

# Stop the loop:
echo '{"done": true, "summary": "All enhancements complete"}' > /tmp/session-loop-state.json
# Or just kill the loop:
kill $LOOP_PID
```

### When to use each approach

| Situation | Use |
|-----------|-----|
| Autonomous batch processing (fix 50 lint errors) | daemon (`launch-loop.py --goals-file`) |
| Self-enhancement of Hermes/skills | in-session loop (`delegate_task` iterations) |
| Monitoring a directory for changes | daemon (`launch-loop.py --watch-dir`) |
| Webhook-triggered processing | daemon (`launch-loop.py --webhook-port`) |
| Iterating on the daemon itself | in-session loop (modify files, run daemon to test) |

## References

- `references/cross-iteration-context.md` — why spawned sessions start blank, the context propagation fix, design rules for cross-iteration state
- `references/yaml-null-pitfall.md` — `hermes config set` quirk with null values
- `references/config-requirements.md` — delegation config requirements
- `references/hermes-delegate-protocol.md` — deprecated v3.x file-based protocol (historical reference)
- `references/spawn-toolset-restriction.md` — why `-z` + `delegation` is broken, and the correct `chat -q` pattern
- `references/terminal-timeout-trap.md` — parent `terminal()` timeout kills the daemon; how to avoid
- `references/hermes-worker.md` — Hermes Worker protocol, edge cases, and troubleshooting

## Pitfalls

1. **`hermes` must be on PATH** — the daemon calls `hermes chat -q` as a subprocess.
2. **`hermes chat -q` is used instead of `-z`** — this is intentional. `-z` oneshot mode exits before delegate_task() results arrive. `chat -q` with `--max-turns 500` keeps the session alive for deep delegation.
3. **`delegation` is included in toolsets by default** — if you explicitly set `--toolsets` without `delegation`, it will be auto-added.
4. **Session timeout** — default 7200s (2 hours) per iteration. If a task takes longer, the spawn will timeout. Increase with `--session-timeout N`.
5. **Ledger grows unboundedly** — use `--keep-iterations N` for auto-shrink.
6. **Sentinel file must be local** — `os.path.exists()` checks are fast.
7. **`--git-commit` stages ALL changes** — uncommitted work will be included.
8. **Idle detection requires `--git`** — without it, `--max-idle-iterations` is silently disabled.
9. **With `--workers N`, each worker spawns a full Hermes session** — cost scales linearly.
10. **Evolution mode** — the spawned session's JSON MUST include a `next_goal` field.
11. **Long context via --context** — shell command-line limits may truncate very long contexts. Use `--context-file PATH` for large contexts.
12. **Profile/model/provider flags apply to spawned sessions** — they do NOT affect the daemon process.
13. **`--http-callback` uses urllib** — no external dependencies, but only supports basic HTTP POST.
14. **`--max-retries` only applies to single-worker mode** — parallel workers are not retried individually.
15. **`--force-reset` is destructive** — deletes the current ledger without archiving.
16. **`--on-error-cmd` runs AFTER the notification callback** — it supplements, not replaces, `--notify-cmd`.
17. **`--prompt-suffix` appends to ALL iterations** — including evolved goals.
18. **`--tag` is not propagated to spawned sessions** — it's metadata for the ledger only.
19. **`chat -q` output includes a `session_id:` line** — the multi-line JSON parser explicitly filters these out before JSON extraction.
20. **`delegate_task()` subagents run in the spawned session's context** — they inherit the spawned session's model and tools, NOT the daemon's.
21. **--max-turns affects spawned session longevity** - very complex delegation chains may need all 500 turns. Monitor the ledger for timed out errors and increase with --max-turns 1000 if needed.
22. **JSON output is now parsed with brace-counting** — the `multi-line JSON parser` replaces the old single-line scan. It handles wrapped JSON and code fences, but the spawned session MUST still print a valid JSON object somewhere in its output.
23. **Pause/resume polls the sentinel file** — when paused, the daemon checks the sentinel every 5 seconds. This is a blocking sleep — the daemon does NOT spawn iterations while paused.
24. **Pause/resume requires the sentinel file to exist** — if you delete the sentinel file while the daemon is running normally (not paused), the daemon will NOT stop. Deletion only triggers resume from the paused state.
25. **Parent `terminal()` timeout can kill the daemon** — `terminal(background=true)` still has a timeout (default 180s). If the daemon hasn't completed its startup within that window, the process tree gets SIGTERM. Always set `timeout=300` on the launch command. See `references/terminal-timeout-trap.md`.
26. **Spawned sessions use hindsight_retain only if told to** — the prompt now includes memory usage instructions, but the spawned session may still skip it. Use `--prompt-suffix` to add extra emphasis like `"--prompt-suffix", "IMPORTANT: Call hindsight_retain() for any discovery future iterations need."`.
27. **`truncated` flag in the ledger** — when `[TRUNCATED]` appears in the inspect output, the spawned session produced more output than `--max-output-chars` can hold. Either increase the cap or reduce the spawned session's verbosity via `--prompt-suffix`.
28. **Rolling window compaction preserves context** — unlike the old destructive compaction, only the earliest entries are condensed to one-liners. The most recent `compact_every` (or at least 10) entries stay at full detail.
29. **Auto-toolsets only adds tools** — it never removes tools you explicitly set with `--toolsets`. If you pass `--toolsets terminal,file`, delegation is auto-added but auto-enrichment will also add task-specific tools on top.
30. **`--no-auto-toolsets` disables enrichment** — use this if you've hand-picked the perfect toolset and don't want keyword scanning to add more.
31. **Failure learning reads from the current ledger** — only iterations that completed with an error are injected. If you cleared the ledger with `--force-reset`, no failure context is available.
32. **`--task-type` overrides auto-detection entirely** — the keyword scanner is skipped when you pass an explicit task type. Useful for running the same type of prompt repeatedly.
33. **`--worker-url auto` (default) requires the worker script** — if `~/.hermes/plugins/hermes-mcp-worker/main.py` is missing, it falls back to direct subprocess mode. No error, just a log warning.
34. **Worker mode still spawns subprocesses** — the worker itself spawns `hermes chat -q` per call. The benefit is embedded lifecycle (auto-start/stop) and self-reference support, not speed.
35. **`--worker-url` with an explicit URL ignores profile/model/provider** — the external worker uses its own Hermes config. Run separate worker instances for different configs. The embedded `auto` mode always uses the same config as the parent session.
36. **`--cooldown` applies even when error-free** — it's a fixed delay between all iterations, not just error backoff. Combine with `--retry-delay` for both rate limiting and exponential backoff on errors.
37. **`--goals-file` conflicts with `--evolve`** — when a goals file is active, evolution is automatically disabled (the file controls the goal sequence). Use one or the other, not both.
38. **`--goals-file` wraps around by default** — if you don't set `--stop-at-goals-end`, the goals repeat cyclically after the last one. This is useful for monitoring loops but surprising if you expect exhaust-able batch processing.
39. **Signal handler uses best-effort write** — the SIGTERM/SIGINT handler writes the ledger with a temp-file + atomic-rename pattern (signal-safe on POSIX), but if the handler itself is interrupted, the state may be incomplete. The main loop also checks for shutdown signals on each iteration, providing a second layer of safety.
40. **`--output-schema` validation is a DISABLED feature by default** — if you don't pass `--output-schema` or `--output-schema-file`, no validation occurs. Validation is stdlib-based and supports a subset of JSON Schema (required fields, types, enum, string min/max length, integer range, nested objects). It does NOT support `$ref`, `oneOf`, `anyOf`, `allOf`, `not`, or pattern matching.
41. **`--cooldown-mode adaptive` requires iteration history** — the first iteration always uses your `--cooldown` value as a fallback. The adaptive calculation kicks in once the ETA tracker has recorded at least one iteration duration.
42. **`--convergence-stop` uses word-overlap (Jaccard) similarity** — short summaries (< 5 words) may report artificially high similarity because the word sets are too small. Consider lowering `--convergence-threshold` for tasks with very brief summaries.
43. **`--convergence-stop` only works on single-worker mode** — in multi-worker mode, the summary is merged from all workers and convergence detection may be less reliable.
44. **System resource tracking uses /proc (Linux only)** — on macOS, the `/proc` filesystem is not available and resource tracking returns empty dicts silently. No error, just no data.
45. **`--store-git-diff` can bloat the ledger with many iterations** — each diff is capped at 10KB, so 100 iterations = up to 1MB of diff data. Combine with `--keep-iterations N` to auto-shrink.
46. **`--use-library` requires the Hermes run_agent module** — if Hermes is installed in a different venv or the import path is wrong, the daemon falls back gracefully to subprocess mode. A log warning is emitted on fallback.
47. **`--use-library` is incompatible with multi-worker mode** — when `--workers > 1`, the daemon automatically disables library mode and falls back to subprocess. The `--checkpoints` flag still works in subprocess mode with workers.
48. **`--pass-session-id` stores session IDs in the ledger** — each session_id is a UUID that identifies the spawned Hermes session. These can be used with `hermes resume SESSION_ID` to inspect or continue a session's history. The ledger can grow by ~40 bytes per iteration from session IDs.
49. **`--checkpoints` works differently in library vs subprocess mode** — in subprocess mode, `--checkpoints` is passed as a CLI flag to `chat -q`. In library mode, it sets `checkpoints_enabled=True` on the AIAgent. Both enable file snapshotting, but the behavior may differ slightly (subprocess uses the CLI's checkpoint defaults, library uses AIAgent defaults).
50. **`--resume` requires `--pass-session-id`** — without session tracking, there's no session_id to resume from. The daemon silently skips resume if no previous session_id is available.
51. **`--resume` loads full history** — chained sessions see ALL tool calls and responses from the previous session. This can consume significant context. Use with `--compact-every` or `--keep-iterations` for long runs.
52. **`--skills` is subprocess-only** — skills preloading via `-s` doesn't work in library mode (AIAgent). The daemon automatically falls back to subprocess mode when `--skills` is combined with `--use-library`.
53. **First iteration has no resume target** — `--resume` is silently skipped on the first iteration because there's no previous session_id yet.
54. **`--ignore-rules` bypasses AGENTS.md** — use with caution if your spawned sessions depend on project guidelines defined in AGENTS.md.
55. **`--yolo` bypasses all security approval prompts** — spawned sessions can execute dangerous commands without confirmation. Use only in trusted environments and with code you've reviewed.
56. **`--yolo` is subprocess-only** — library mode (--use-library) silently skips --yolo with a log warning. No AIAgent equivalent exists.
57. **`--safe-mode` is subprocess-only** — library mode (--use-library) silently skips --safe-mode with a log note. No AIAgent equivalent exists. Combine with `--ignore-rules` and `--ignore-user-config` outside of library mode for equivalent isolation.
58. **`--accept-hooks` is subprocess-only** — library mode silently skips --accept-hooks. For library mode, pre-configure hooks in the Hermes config.
59. **`--worktree` is subprocess-only** — library mode silently skips --worktree. For isolated workspaces in library mode, set the workdir manually.
60. **`--continue` is subprocess-only** — library mode silently skips --continue. For session continuity in library mode, use --resume with a specific session_id.
61. **`--ignore-user-config` creates isolated runs** — spawned sessions will not load plugins, MCP servers, or custom tool configurations. Use for troubleshooting only.

## When to Use

Use this skill when you need to loop work in the background and delegate
subtasks to subagents. The daemon runs as a background process, spawns
Hermes CLI sessions with real tools + delegation, and manages the loop state.

Good use cases:
- Progressive codebase fixes (fix type errors one category at a time)
- Iterative refactoring (refactor module by module with delegated analysis)
- Batch data processing (process chunks of a dataset via parallel subagents)
- Continuous improvement loops (audit → delegate fixes → measure → repeat)
- Git-aware evolution (auto-commit improvements, stop when no more changes)
