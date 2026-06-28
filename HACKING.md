# Hacking on the Infinite Loop Daemon

A deep-dive reference for third-party tool developers, integrators, and
advanced contributors. This document explains the **spawned-session protocol**,
the **iteration record schema**, and the **JSON ledger format** that underpin
the entire daemon.

If you are new to the project, start with
[CONTRIBUTING.md](./CONTRIBUTING.md) for developer onboarding and
[README.md](./README.md) for end-user documentation.

---

- [Overview](#overview)
- [Architecture at a Glance](#architecture-at-a-glance)
- [Spawned-Session Protocol](#spawned-session-protocol)
  - [`hermes chat -q` (Not `-z`)](#hermes-chat--q-not--z)
  - [Prompt Structure](#prompt-structure)
  - [JSON Output Contract](#json-output-contract)
  - [JSON Extraction Algorithm](#json-extraction-algorithm)
  - [Retry & Heartbeat](#retry--heartbeat)
  - [Worker Mode (Multi-Session Parallelism)](#worker-mode-multi-session-parallelism)
- [Iteration Record Schema](#iteration-record-schema)
  - [Top-Level Fields](#top-level-fields)
  - [Worker Results (Multi-Worker Only)](#worker-results-multi-worker-only)
  - [Git Fields](#git-fields)
  - [System Resource Fields](#system-resource-fields)
  - [Worktree Merge Fields](#worktree-merge-fields)
- [JSON Ledger Format](#json-ledger-format)
  - [Ledger Root Fields](#ledger-root-fields)
  - [Stats Sub-Object](#stats-sub-object)
  - [Error Type Counts](#error-type-counts)
  - [Mitigations Sub-Object](#mitigations-sub-object)
  - [Goals Tracking](#goals-tracking)
  - [Pending Iteration Recovery](#pending-iteration-recovery)
- [Ledger Lifecycle](#ledger-lifecycle)
  - [Atomic Writes with File Locking](#atomic-writes-with-file-locking)
  - [Archiving & Shrinking](#archiving--shrinking)
  - [Status File](#status-file)
- [Scripter's Reference](#scripters-reference)
  - [Inspecting the Ledger](#inspecting-the-ledger)
  - [Archiving Iterations](#archiving-iterations)
  - [Replaying Iterations](#replaying-iterations)
- [Error Classification Taxonomy](#error-classification-taxonomy)
  - [`classify_error()` Output](#classify_error-output)
  - [`_classify_progress()` Output](#_classify_progress-output)
- [Convergence Detection](#convergence-detection)
- [HTTP Callback Payload](#http-callback-payload)
- [Sentinel File Protocol](#sentinel-file-protocol)
- [Module Map](#module-map)
- [Web Stack Architecture](#web-stack-architecture)
  - [Static HTML Dashboard (`dashboard.py`)](#static-html-dashboard-dashboardpy)
  - [SSE Live Dashboard (`dashboard.py`)](#sse-live-dashboard-dashboardpy)
  - [FastAPI SPA (`web_app/`)](#fastapi-spa-web_app)
  - [Docker Deployment](#docker-deployment)
- [Iteration Lifecycle (Full Sequence Diagram)](#iteration-lifecycle-full-sequence-diagram)

---

## Overview

The Infinite Loop Daemon is a **background daemon** (stdlib-only Python
package, ~38 modules) that:

1. Spawns `hermes chat -q` sessions as autonomous workers.
2. Collects each worker's JSON output (the **spawned-session protocol**).
3. Parses, merges, and stores results into a **JSON ledger** at
   `/tmp/infinite-loop-state.json`.
4. Repeats until a stop condition is met (max iterations, sentinel file,
   convergence, goals exhausted).

Every iteration produces a **record** appended to the ledger. The record
follows a strict schema documented below.

---

## Architecture at a Glance

```
run.sh / hermes_loop --goal "..." --run
  │
  └─ hermes_loop/  (38 modules)
       │
       ├─ cli.py       → argparse, main()
       ├─ loop.py      → run_loop() — the main iteration loop
       ├─ iteration.py → _execute_iteration(), _merge_worker_results(),
       │                  _build_iteration_record(), _compact_summaries(),
       │                  _detect_convergence(), _handle_backoff()
       ├─ functions.py → startup banner, goal cycling, progressive context
       ├─ hermes_utils.py → find_hermes(), _build_delegation_prompt(),
       │                     spawn_delegation_session()
       ├─ state.py     → load_or_create_ledger()
       ├─ file_utils.py → write_ledger(), read_ledger(), extract_json_from_output()
       ├─ stats.py     → _recalc_stats()
       ├─ config.py    → paths, version, constants
       ├─ error_utils.py, error_recovery.py → classification, mitigation
       ├─ similarity.py → convergence detection (Jaccard word overlap)
       ├─ validation.py → JSON Schema validation (stdlib-only)
       ├─ heartbeat.py → self-healing heartbeat monitor
       ├─ dashboard.py, web_app/ → web UI
       └─ ... (30+ more modules)
```

The spawned session is a **separate `hermes chat -q` subprocess** (or an
in-process AIAgent call when `--use-library` is set). The parent daemon reads
the child's stdout and parses the final JSON line.

---

## Spawned-Session Protocol

### `hermes chat -q` (Not `-z`)

The daemon uses `hermes chat -q` (quiet mode) instead of `-z` (oneshot mode).
This is a **critical design decision**:

| Feature | `-z` (oneshot) | `-q` (chat) |
|---------|----------------|-------------|
| Turns   | Single turn    | Multiple turns (`--max-turns N`) |
| `delegate_task()` | Results never arrive | Results arrive (session stays alive) |
| Multi-level delegation | Not possible | Supported |
| JSON output | One response | Must print JSON as last line |
| Context persistence | Per-message | Full session lifetime |

The spawned command looks like:

```
hermes chat -q "<prompt>" -t terminal,file,delegation,... -Q --max-turns 500
```

- `-q` = quiet mode (no TUI, plain text output)
- `-t` = toolset selection (tools the spawned session can use)
- `-Q` = disable final "how can I help?" prompt
- `--max-turns N` = how many turns the session lives (default 500)

### Prompt Structure

The daemon builds a structured prompt using `_build_delegation_prompt()` in
`hermes_utils.py`. The prompt always contains:

1. **Header**: "You are iteration #N (worker #W) of an autonomous loop daemon."
2. **Goal**: The task description from `--goal` (or goals file).
3. **Context**: Progressive context from past iterations, failure context,
   optional `--context` text, optional `--prompt-suffix`.
4. **Tools list**: The available toolset names.
5. **Task-type strategy**: Task-specific guidance (research vs. code-fix vs.
   code-build vs. system-admin vs. data-processing vs. content).
6. **Memory & delegation guidance**: How to use `hindsight_retain()` / recall,
   `delegate_task()`, and cross-iteration memory.
7. **JSON contract**: Instructions to print one JSON object as the last
   significant output.

### JSON Output Contract

The spawned session **must** print one JSON object as its last significant
output on stdout. The daemon parses this with `extract_json_from_output()`.

```json
{
  "summary": "What was accomplished — detailed, actionable text",
  "duration_seconds": 123,
  "error": null,
  "next_goal": "Suggested next task (only meaningful with --evolve)",
  "context": "Detailed context for the next iteration to continue from here"
}
```

**Field semantics:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `summary` | string | **yes** | Free-text summary of what was done. Capped at 500 characters in the ledger. |
| `duration_seconds` | number | **yes** | Self-reported wall-clock time of the work. Used for ETA tracking. |
| `error` | string\|null | **yes** | `null` on success, error message string on failure. |
| `next_goal` | string | no | Only meaningful with `--evolve`. If it contains `"need_reload"`, the daemon restarts itself via `os.execv()`. |
| `context` | string | no | Arbitrary context text passed to the NEXT spawned session. The primary mechanism for iterative progress. |

**Important notes:**

- The JSON must be *the last or near-last* object in the output. The parser
  scans backwards for balanced braces.
- Extra text before, after, or around the JSON is tolerated — the parser
  extracts only the valid JSON.
- If multiple JSON objects exist in stdout, the **last valid one** wins.
- If no valid JSON is found, the iteration is marked as failed with an
  error like "No valid JSON in output".

### JSON Extraction Algorithm

Found in `file_utils.py:extract_json_from_output()`:

```
Strategy 1 (reverse scan):
  1. Strip lines starting with "session_id:" (chat -q metadata noise)
  2. Scan remaining text character-by-character in REVERSE
  3. Count brace depth ({ = -1, } = +1)
  4. When brace_depth returns to 0, attempt json.loads()
  5. Return first successful parse

Strategy 2 (forward scan, fallback):
  If Strategy 1 fails:
    1. Find all '{' characters (forward)
    2. For each, track brace depth until }
    3. Collect all valid JSON objects
    4. Return the LAST one
```

This two-strategy approach handles:
- Nested braces in JSON strings
- Multiple JSON objects in streamed output
- Malformed JSON attempts before the final valid one
- Terminal escape sequences and TUI artifacts (filtered before parsing)

### Retry & Heartbeat

The daemon supports two mechanisms for handling hung or failed sessions:

**Retry (`--max-retries N`, `--retry-delay S`):**
- If a spawned session returns an error, the daemon can retry it up to N times.
- Exponential backoff: delay is `retry_delay * (attempt_number + 1)`.
- Applies only to single-worker mode.

**Heartbeat self-healing (`--heartbeat-timeout S`):**
- The spawned session writes a heartbeat file every 30 seconds.
- The daemon polls these files every 5 seconds.
- If no heartbeat for `timeout * 3` seconds (timeout + grace), the session is
  killed (SIGTERM, then SIGKILL after 5s) and marked as "heartbeat" error.
- Heartbeat files live at `/tmp/infinite-loop-heartbeat-<session_id>`.

### Worker Mode (Multi-Session Parallelism)

When `--workers N` (N > 1), the daemon spawns N concurrent Hermes sessions:

- Each worker gets a unique `worker_id` (0 to N-1).
- Workers run in a `ThreadPoolExecutor` with `max_workers=N`.
- If a goals file is loaded, workers round-robin through the goals list.
- Results from all workers are merged via `_merge_worker_results()`.

**Merge rules for errors:**
- Single-worker mode: hard errors (timeout, network, schema) mark the iteration.
- Multi-worker mode: only mark as errored when ALL workers have hard errors,
  or a majority have serious error types.
- Soft errors (exit-code noise with meaningful output) are tolerated.

The merged record includes a `worker_results` array with per-worker fields
(see [Worker Results](#worker-results-multi-worker-only)).

---

## Iteration Record Schema

Each iteration produces a record appended to the ledger's `iterations` array.
Built by `_build_iteration_record()` in `iteration.py`.

### Top-Level Fields

| Field | Type | Always present | Description |
|-------|------|----------------|-------------|
| `n` | int | yes | Iteration number (1-indexed) |
| `task_type` | string | yes | Auto-detected: `research`, `code-fix`, `code-build`, `system-admin`, `data-processing`, `content`, `general` |
| `goal` | string | only if `--goals-file` | Per-iteration goal text (empty string for single-goal mode) |
| `started_at` | ISO-8601 | yes | UTC timestamp when iteration was launched |
| `completed_at` | ISO-8601 | yes | UTC timestamp when iteration finished |
| `duration_seconds` | float | yes | Wall-clock duration of the spawned session(s) |
| `summary` | string | yes | Free-text summary (capped at 500 chars) |
| `compacted` | bool | yes | `true` if this iteration triggered summary compaction |
| `error` | string\|null | yes | Error message on failure, `null` on success |
| `exit_code` | int | yes | `0` if no error, `1` if error |
| `toolsets` | array[string] | yes | Toolset names used for this iteration |
| `workers` | int\|null | no | Number of parallel workers (only when > 1) |
| `worker_results` | array\|null | no | Per-worker result objects (only when `workers > 1`) |
| `output_chars` | int | single-worker only | Total characters of raw output |
| `chars_per_second` | float | single-worker only | Output throughput rate |
| `total_output_bytes` | int | single-worker only | Raw output size in bytes |
| `truncated` | bool | single-worker only | Whether output exceeded `--max-output-chars` |
| `stderr` | string\|null | single-worker only | First 500 chars of stderr, if present |
| `schema_valid` | bool\|null | single-worker only | Whether output passed JSON Schema validation |
| `schema_error` | string\|null | single-worker only | Schema validation error message |
| `git_before` | dict\|null | only if `--git` | Git state snapshot before the iteration |
| `git_after` | dict\|null | only if `--git` | Git state snapshot after the iteration |
| `git_commit` | string\|null | only if `--git-commit` | Commit hash of the auto-commit |
| `next_goal` | string\|null | only if spawned session set it | Next goal text (for `--evolve`) |
| `next_context` | string\|null | only if spawned session set it | Context for next iteration |
| `spawned_session_id` | string\|null | only if `--pass-session-id` | The spawned Hermes session ID |
| `system` | dict\|null | yes (may be empty) | System resource usage (CPU, memory) |
| `worktree_merge` | dict\|null | only if `--worktree` | Worktree branch merge summary |
| `remote_cleanup` | dict\|null | only if `--worktree` | Remote branch cleanup summary |
| `classification` | string | yes | Progress classification (see below) |

### Worker Results (Multi-Worker Only)

When `--workers N` with N > 1, each iteration includes a `worker_results` array:

```json
"worker_results": [
  {
    "worker": 0,
    "summary": "Worker's summary text (capped 200 chars)",
    "error": null,
    "error_type": null,
    "duration_seconds": 45.2,
    "output_chars": 12850,
    "chars_per_second": 284.5,
    "total_output_bytes": 13120,
    "truncated": false,
    "spawned_session_id": "20260628_163738_abc123"  // only with --pass-session-id
  }
]
```

### Git Fields

When `--git` is enabled, each record includes `git_before` and `git_after`:

```json
"git_before": {
  "head": "abc123def456...",
  "diff_stat": "3 files changed, 45 insertions(+), 12 deletions(-)",
  "diff_stored": "--- a/foo.py\n+++ b/foo.py\n@@ -1,5 +1,5 @@\n...",  // only with --store-git-diff (capped 10KB)
  "dirty": false,
  "untracked": ["new_file.py"],
  "diff_stat_cached": ""
}
```

When `--git-commit` is also set, `git_commit` contains the commit hash.

### System Resource Fields

```json
"system": {
  "cpu_seconds_used": 12.5,
  "memory_rss_mb": 245.0,
  "memory_peak_mb": 312.0,
  "memory_used_percent": 45.2,
  "cpu_percent": 35.0
}
```

These are **diffs** — resource consumption attributed to this iteration
(calculated as `after - before` from system snapshots).

### Worktree Merge Fields

```json
"worktree_merge": {
  "merged": 3,
  "failed": 0,
  "skipped": 0,
  "per_worker": { "0": "ok", "1": "ok", "2": "ok" },
  "conflicts": 0,
  "source_branches": ["hermes/w0/iter14", "hermes/w1/iter14"]
}
```

Remote cleanup (stale worktree branch pruning):

```json
"remote_cleanup": {
  "stale_pruned": 2,
  "remote_merged": 1,
  "remote_deleted": 1,
  "remote_failed": 0
}
```

---

## JSON Ledger Format

The ledger lives at `/tmp/infinite-loop-state.json` by default (configurable
via constants in `config.py` but not user-overridable via CLI flags).

### Ledger Root Fields

| Field | Type | Always present | Description |
|-------|------|----------------|-------------|
| `version` | int | yes | Schema version (currently 11). Incremented on breaking changes. |
| `version_detail` | string | yes | Human-readable version string describing major features. |
| `initial_command` | string | yes | The `--goal` text the daemon was started with. |
| `initial_context` | string | yes | The `--context` text (may be empty). |
| `started_at` | ISO-8601 | yes | Daemon start timestamp. |
| `iterations` | array[record] | yes | Array of iteration record objects. |
| `total_iterations` | int | yes | Count of iterations (matches `len(iterations)` except after archiving). |
| `last_updated` | ISO-8601 | yes | Last modification timestamp. |
| `status` | string | yes | Current daemon state (see status values below). |
| `stats` | dict | yes | Aggregated statistics (see below). |
| `error_type_counts` | dict | yes | Counter per error type category. |
| `mitigations` | dict | yes | Error recovery/mitigation state (see below). |
| `goals_completed` | dict | only with `--track-goals` | MD5-hashed goal completion tracking. |

**Status values**

| Status | Meaning |
|--------|---------|
| `running` | Daemon is actively iterating. |
| `paused` | Sentinel file contained "pause". Will resume on "resume" or sentinel removal. |
| `stopped: sentinel` | Stopped by writing to sentinel file. |
| `stopped: signal` | Stopped by SIGINT/SIGTERM. |
| `stopped: max_iterations` | Reached `--max-iterations`. |
| `stopped: convergence` | Summaries became repetitive (Jaccard similarity ≥ threshold). |
| `stopped: idle` | No git changes for `--max-idle-iterations`. |
| `stopped: goals-exhausted` | All goals in `--goals-file` processed. |
| `stopped: shutdown-during-backoff` | Shutdown signal during error backoff delay. |
| `stopped: paused-stop` | Stop signal received during pause state. |
| `reloading` | Daemon is restarting via `os.execv()` after self-modification. |

### Stats Sub-Object

Recalculated after each iteration by `_recalc_stats()`:

```json
"stats": {
  "total_duration_seconds": 1523.4,
  "avg_duration_seconds": 152.3,
  "success_count": 8,
  "error_count": 2,
  "consecutive_errors": 0,
  "consecutive_successes": 3,
  "remote_cleanup_totals": {
    "remote_deleted": 1,
    "remote_merged": 0,
    "stale_pruned": 0,
    "remote_failed": 0
  }
}
```

- `consecutive_errors`/`consecutive_successes`: computed by scanning the
  iteration list in reverse until the opposite state is found.
- `remote_cleanup_totals`: aggregate of all remote cleanup operations across
  all iterations.

### Error Type Counts

```json
"error_type_counts": {
  "timeout": 0,
  "network": 0,
  "schema": 0,
  "unknown": 0,
  "heartbeat": 0
}
```

Incremented per iteration when `primary_error_type` is set. These are the
five canonical error types from `classify_error()` (see
[Error Classification Taxonomy](#error-classification-taxonomy)).

### Mitigations Sub-Object

```json
"mitigations": {
  "timeout_increased": false,
  "cooldown_elevated": false,
  "force_subprocess": false,
  "reduced_workers": false,
  "mitigation_level": 0,
  "last_applied": "",
  "actions": []
}
```

Managed by `_adapt_to_error()` in `error_recovery.py`. Mitigations are
applied dynamically when error counts hit severity thresholds (mild=3,
moderate=5, stop=8 for timeout errors, etc.). The `actions` array logs
each mitigation action taken.

### Goals Tracking

When `--track-goals` is enabled:

```json
"goals_completed": {
  "a1b2c3d4e5f6g7h8": {
    "status": "completed",
    "iteration": 5,
    "goal": "Fix lint errors in src/"
  }
}
```

- Keys are MD5 hashes (first 16 hex chars) of the goal text.
- On restart, already-completed goals are skipped.
- `--reset-goals` clears this dictionary for a fresh run.

### Pending Iteration Recovery

The ledger may contain a `pending_iteration` object during an iteration:

```json
"pending_iteration": {
  "n": 7,
  "started_at": "2026-06-28T16:37:38+00:00"
}
```

On daemon restart, any pending iteration older than 300 seconds is recovered:
a synthetic record is appended with error `"agent_crashed"` and the iteration
counter advanced. This prevents stale pending entries from blocking progress.

---

## Ledger Lifecycle

### Atomic Writes with File Locking

All ledger writes use a **temp-file + atomic rename** pattern with POSIX
flock (via `FileLock` in `file_utils.py`):

```
write_ledger(state):
  1. Acquire flock on /tmp/infinite-loop-state.lock (10s timeout)
  2. Write JSON to /tmp/infinite-loop-state.json.tmp
  3. os.replace(tmp_path → final_path)  ← atomic on Linux
  4. Release lock
```

This prevents partial reads and write corruption even with concurrent
processes.

### Archiving & Shrinking

The ledger grows unboundedly. Two mechanisms control size:

1. **`--keep-iterations N`**: When the iteration count exceeds `N * 2`,
   old iterations are moved to the archive directory
   (`~/.hermes/infinite-loop-archives/`) and removed from the ledger.

2. **Archive scripts**: `scripts/archive-state.sh` can be called externally
   (or by the daemon when `--archive-dir` is configured). Archives are
   JSONL files with one iteration per line, optionally gzipped.

3. **`archive-retention`** and **`archive-max-size`**: Control how long
   archives are kept and total archive directory size.

### Status File

An optional lightweight JSON status file (`--status-file PATH`) is written
after every iteration for external monitoring:

```json
{"pid": 12345, "iteration": 7, "status": "running",
 "total_iterations": 7, "total_duration_seconds": 350.0,
 "last_updated": "2026-06-28T16:37:38.123456+00:00"}
```

---

## Scripter's Reference

### Inspecting the Ledger

```bash
scripts/inspect-ledger.sh                          # Default view (last 5 iters)
scripts/inspect-ledger.sh /custom/path/ledger.json # Custom path
scripts/inspect-ledger.sh --summary                # Compact one-liner
scripts/inspect-ledger.sh --json                   # Full JSON output
scripts/inspect-ledger.sh --json --last 10         # Last 10 as JSON
scripts/inspect-ledger.sh --errors-only            # Failed iterations only
scripts/inspect-ledger.sh --watch                  # Auto-refresh every 5s
scripts/inspect-ledger.sh --inotify                # inotify-based watch
```

### Archiving Iterations

```bash
scripts/archive-state.sh --auto                    # Archive + keep last 100
scripts/archive-state.sh --keep 20                 # Keep last 20, archive rest
scripts/archive-state.sh --export-md               # Markdown report
scripts/archive-state.sh --gzip                    # Compressed archive
```

### Replaying Iterations

```bash
scripts/replay-ledger.sh archive.jsonl             # Re-run archived goals
scripts/replay-ledger.sh archive.jsonl --from 3 --to 7  # Range
scripts/replay-ledger.sh archive.jsonl --dry-run   # Preview only
```

---

## Error Classification Taxonomy

### `classify_error()` Output

Applied to each spawned session's error string. Canonical error types:

| Type | Detection Keywords | Severity |
|------|--------------------|----------|
| `heartbeat` | Session heartbeat timeout | 5 (highest) |
| `timeout` | timeout, timed out | 4 |
| `network` | connection refused, connection error, connection reset, network, dns, resolve, refused, no route | 3 |
| `schema` | schema, validation, invalid | 2 |
| `unknown` | Everything else | 1 |

The most severe error type from all workers is chosen as the
`primary_error_type` for the iteration (via `_pick_primary_error()`).

### `_classify_progress()` Output

Applied to each completed iteration record. This classification is stored
in the `classification` field:

| Classification | Conditions | Meaning |
|----------------|------------|---------|
| `completed` | Summary contains "completed", "finished", "all done", "task complete", "goal achieved" | Goal fully met. |
| `regression` | Error present AND no git changes AND not a soft exit-code error | Things got worse. |
| `stuck` | No git changes AND (summary < 30 chars OR contains "still working", "cannot", "unable", "failed to") | Making no progress. |
| `progress` | Git changes present AND positive language ("added", "fixed", "implemented", etc.) | Forward movement. |
| `partial` | Git changes AND (error present OR summary mentions "remaining", "in progress", "partial", "wip") | Some work done, more remains. |
| `unknown` | None of the above | Ambiguous or initial iteration. |

---

## Convergence Detection

Located in `similarity.py`. Uses Jaccard word overlap:

1. Tokenize each summary into lowercase word sets (`re.findall(r"\w+", text)`)
2. `similarity = |intersection| / |union|`
3. Compare the last `N` summaries (default N=5) in all pairwise combinations
4. If ALL pairs exceed `threshold` (default 0.9), declare convergence
5. Stop the daemon with status "stopped: convergence"

Configured via `--convergence-stop`, `--convergence-threshold`,
`--convergence-window`.

---

## HTTP Callback Payload

When `--http-callback URL` is set (optionally with
`--http-callback-secret KEY` for HMAC-SHA256 signing), a POST request is sent
after each iteration with this JSON body:

```json
{
  "iteration": { /* full iteration record */ },
  "state": {
    "status": "running",
    "total_iterations": 7,
    "max_iterations": 0,
    "started_at": "2026-06-28T16:37:38+00:00",
    "last_updated": "2026-06-28T16:38:45+00:00",
    "goal": "Fix lint errors",
    "evolved_goal": "",
    "cooldown": 0,
    "consecutive_errors": 0,
    "eta": { /* ETA tracker state */ }
  },
  "stats": {
    "success_count": 6,
    "error_count": 1,
    "total_duration_seconds": 923.4,
    "avg_duration_seconds": 131.9
  },
  "system": { /* system resource diff */ },
  "pid": 12345
}
```

Signed with HMAC-SHA256 when a secret is configured (header:
`X-Signature-256: <hex>`).

Additionally, `--notify-cmd` receives the iteration record on stdin (pipe
mode), and `--on-error-cmd` receives only error-iteration records.

---

## Sentinel File Protocol

The sentinel file at `/tmp/infinite-loop-stop` (by default) is the primary
external control mechanism:

| Content Written | Effect |
|----------------|--------|
| `stop` | Daemon stops after current iteration. Sentinel file is consumed (deleted). |
| `pause` | Daemon pauses after current iteration. Entered paused state, polls sentinel. |
| `resume` | If paused, daemon resumes. Sentinel file is deleted. |
| *(file removed)* | If paused, daemon resumes (removal = implicit resume). |

The sentinel is checked at the top of each iteration loop via
`check_sentinel()`. The pause loop uses `check_sentinel_no_remove()` (peek
only) to poll every 5 seconds.

---

## Module Map

Source file → primary responsibility:

| Module | Responsibility |
|--------|---------------|
| `config.py` | Constants, paths, error thresholds, task-type pattern definitions |
| `cli.py` | Argparse, main(), `--list-flags`, `--examples`, `--explain`, `--help-topic` |
| `loop.py` | `run_loop()` — main iteration loop, shutdown summary, error recovery integration |
| `iteration.py` | Session spawning, result merging, record building, convergence, backoff, notifications, callbacks |
| `hermes_utils.py` | Hermes binary discovery, delegation prompt builder, PTY-based session spawning, stderr real-time reader |
| `functions.py` | Goal file loading, startup banner, goal cycling, progressive context |
| `state.py` | `load_or_create_ledger()` — ledger init, stale recovery |
| `file_utils.py` | FileLock, write_ledger, read_ledger, write_status_file, sentinel checks, JSON extraction |
| `error_utils.py` | `classify_error()`, `_classify_progress()`, `_suggest_actionable_fix()` |
| `error_recovery.py` | `_adapt_to_error()` — dynamic mitigation (timeout increase, cooldown, subprocess, workers) |
| `validation.py` | JSON Schema validation (stdlib subset) |
| `similarity.py` | Jaccard word overlap for convergence detection |
| `heartbeat.py` | Session heartbeat file management, self-healing kill logic |
| `stats.py` | `_recalc_stats()` — aggregate statistics recalculation |
| `git_utils.py` | Git state capture, auto-commit, diff storage |
| `goal_utils.py` | `GoalSpec`, completion tracking |
| `dashboard.py` | HTML dashboard writer, SSE broadcast |
| `webhook.py` | HTTP webhook server for external iteration triggering |
| `notifications.py` | Desktop, Pushbullet, ntfy notification dispatch |
| `worktree_merger.py` | Git worktree branch creation, merge, conflict tracking |
| `archiving.py` | Iteration archiving to JSONL, retention enforcement |
| `worker_manager.py` | HermesWorkerManager — embedded MCP worker HTTP server |
| `file_watcher.py` | `FileWatcherTrigger` — os.stat() polling for file change detection |
| `completions.py` | Bash/zsh shell completion script generation |
| `cooldown.py` | Adaptive cooldown calculation |
| `signal_handlers.py` | SIGINT/SIGTERM handlers, auto-reload file watching |
| `tracker.py` | `ETATracker` — per-task-type ETA estimation |
| `preflight.py` | Health checks before daemon start |
| `self_test.py` | In-process self-tests |
| `diagnosis.py` | Comprehensive environment diagnosis (`--doctor`) |
| `wizard.py` | Interactive setup wizard (`--init`) |
| `color_utils.py` | ANSI color helpers with `NO_COLOR` support |
| `system_utils.py` | System resource monitoring (cpu, memory) |
| `similarity.py` | Text similarity / convergence detection |
| `library_worker.py` | In-process AIAgent runner (`--use-library`) |
| `env_utils.py` | `.env` file parsing and validation |
|| `web_app/` | FastAPI-based web UI (requires `pip install web` extras) |
|
|---

## Web Stack Architecture

The project ships three distinct web-facing components, each serving a different
audience:

| Component | Technology | Purpose | Port / Path |
|-----------|-----------|---------|-------------|
| Static HTML Dashboard (`dashboard.py`) | stdlib `http.server`, inline HTML/CSS | Quick monitoring (static file, no JS framework) | Configurable via `--status-html PATH` (writes `.html` file) |
| SSE Live Dashboard (`dashboard.py`) | Inline HTML + JS `EventSource`, SSE | Live-updating dark-theme dashboard with iteration rows, error cards, mitigations, goals tracking, worker status | Written to file + SSE broadcast |
| FastAPI Web UI (`web_app/`) | FastAPI + uvicorn + xterm.js | Full SPA: daemon start/stop, config editor, iteration browser, live logs, per-worker xterm.js terminal | Default `http://0.0.0.0:8090` (`/live` for SSE) |

All three share the same data source: the JSON ledger at
`/tmp/infinite-loop-state.json`.

### Static HTML Dashboard (`dashboard.py`)

The simplest monitoring surface. Written by `_write_status_html()` in
`dashboard.py` after every iteration when `--status-html PATH` is set.

- Single self-contained HTML page with inline `<style>` and JS
- Uses `<meta http-equiv="refresh" content="30">` for auto-refresh (no SSE)
- Compact mode toggle (stored in `localStorage`): hides all tables, shows a
  terse one-liner suitable for status-bar widgets or tmux bottom-panels
- Supports both dark and light mode via `prefers-color-scheme`
- Icon: `♾️` (infinity symbol as inline SVG favicon)

**CSS variables** for theming:

```css
:root { --bg: #0d1117; --fg: #c9d1d9; --card-bg: #161b22; --border: #30363d; ... }
@media (prefers-color-scheme: light) {
  :root { --bg: #f6f8fa; --fg: #24292f; --card-bg: #ffffff; ... }
}
```

### SSE Live Dashboard (`dashboard.py`)

A richer version of the static dashboard driven by Server-Sent Events. Enabled
when `--status-html` is set *and* the daemon's loop calls
`_broadcast_to_sse_clients()`.

**Architecture:**

```
Daemon (loop.py)                    SSE Clients (browser)
      │                                     │
      ├─ _build_iteration_record()          │
      ├─ _recalc_stats()                    │
      ├─ _write_status_html(state)          │
      └─ _broadcast_to_sse_clients(state)───┤
                                            ├─ EventSource('/live')
                                            ├─ {type: "init", data: status}
                                            ├─ {type: "update", data: {type:"status_update", data: status}}
                                            └─ {type: "update", data: {type:"log_entry", entry: ...}}
```

**SSE event types:**

| Event Name | Payload | Frequency |
|-----------|---------|-----------|
| `init` | Full status snapshot | On connection |
| `update` | `{"type":"status_update","data":status}` | On any state change (iteration, error, mitigation, log) |
| `update` | `{"type":"log_entry","entry":{"timestamp","message"}}` | Per new log line |
| `heartbeat` | `{"type":"heartbeat","time":"..."}` | Every 15s idle, to detect stale connections |

**Client management:**

- `_sse_clients`: list of `queue.Queue` objects, one per connected browser
- Bounded queues (size 128) prevent unbounded memory growth from slow clients
- Stale-client detection: `QueueFull` or `Exception` on `put_nowait()` →
  client removed
- `_sse_client_last_active`: monotonic-time tracking, stale after 60s

**Smart change detection:**

The `_broadcast_to_sse_clients()` method builds a hash from iteration number,
worker statuses, error_counts, mitigations, log count, terminal lines, and the
latest iteration's key fields (worktree_merge, summary, error, classification).
Only broadcasts when the hash changes, avoiding redundant pushes.

**Dashboard features:**

- Status badge: `running` (blue), `stopped` (red), `paused` (yellow), `reloading` (red)
- Stats grid: success/error counts, avg duration, consecutive errors, ETA
- Progress bar: % of max_iterations
- Error cards: timeout/network/schema/heartbeat/unknown with left-color-border
- Mitigations panel: active mitigations (timeout+, cooldown+, no-library, workers-)
- Goals panel: progress bar + per-goal rows (✓ done, ▶ active, ○ pending)
  - Shows up to 30 goals, "+ N more" overflow indicator
  - Deleted goals with strikethrough
- Metrics panel: chars/iter, throughput (cps), est cost, iters/goal
- Iterations table: newest-first, capped at 100 rows
  - Error rows highlighted with `error-row` class
  - Worktree merge column: `wt:3✓ 0✗` with tooltip (branches, per-worker details,
    merge counts, conflicts)
  - Remote cleanup column: `clean:r1del/s1` with tooltip
  - Reset detection: if total_iterations drops (loop was reset), table clears
- Compact mode toggle (localStorage-persisted)
- Links to JSON API (`/api/status`), simple status (`/status`), health (`/health`)

### FastAPI SPA (`web_app/`)

Full Single-Page Application for managing the daemon from a browser. Requires
`pip install "hermes-loop[web]"` (installs `fastapi`, `uvicorn`,
`python-dotenv`).

**Entry points:**

| Method | Command |
|--------|---------|
| `hermes_loop_web` | Console script registered in `pyproject.toml` |
| `python -m web_app` | Module invocation |
| Docker | `ENTRYPOINT ["python", "-m", "web_app", "--host", "0.0.0.0"]` |

**Package structure:**

```
web_app/
├── __init__.py       # Version marker
├── __main__.py       # Allow python -m web_app
├── server.py         # FastAPI app, REST endpoints, SSE, status poller
├── config_manager.py # Config schema, persistence, CLI args builder
├── loop_manager.py   # Daemon subprocess lifecycle manager
└── static/
    ├── index.html    # SPA shell (sidebar + 5 tabs)
    ├── app.js        # All UI logic, SSE client, rendering
    └── style.css     # Dark-first design system with light mode support
```

**REST API endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve SPA shell |
| GET | `/api/config` | Full config with defaults + current values + groups |
| GET | `/api/config/groups` | Config group names/ids only (lightweight) |
| GET | `/api/config/raw` | Raw key-value config dict |
| POST | `/api/config` | Save config to `/tmp/hermes-loop/config.json` |
| GET | `/api/config/cli-preview` | Preview generated `--flag value` args |
| POST | `/api/loop/start` | Start daemon subprocess |
| POST | `/api/loop/stop` | Write sentinel + SIGTERM + SIGKILL fallback |
| POST | `/api/loop/pause` | Write "pause" to sentinel |
| POST | `/api/loop/resume` | Remove sentinel to wake paused daemon |
| POST | `/api/loop/reset` | Delete ledger + lock file |
| GET | `/api/status` | Combined loop + ledger + live iteration status |
| GET | `/api/ledger` | Full ledger state |
| GET | `/api/iterations` | Paginated iteration history (`?limit=N&offset=M`) |
| GET | `/api/logs` | Last N log entries from the web manager |
| GET | `/api/health` | Health check: `{"status":"ok","timestamp":"..."}` |
| GET | `/live` | SSE stream (EventSource) |
| GET | `/static/*` | Static files (app.js, style.css) |

**Config persistence:**

Config is stored as a flat JSON dict at `/tmp/hermes-loop/config.json` — no
`.env` file needed when using the web UI. The config_manager.py maps env var
names to CLI flags via `build_cli_args()`:

```python
# Example: INFINITE_LOOP_GOAL="Fix lint errors" → --goal "Fix lint errors"
#           INFINITE_LOOP_GIT=true               → --git
```

Each config key has a schema entry:
```python
CONFIG_DEFAULTS = {
    "INFINITE_LOOP_GOAL": {
        "default": "", "type": "string", "group": "core",
        "label": "Goal", "description": "...", "multiline": True,
    },
    ...
}
```

The web UI renders fields dynamically from `CONFIG_DEFAULTS` + `CONFIG_GROUPS`.
Supported types: `string`, `int`, `float`, `bool`, `select` (with `options`
array), `multiline`. Required fields show a `*` marker.

**CSS design system** (`style.css`):

- Dark-first: `--bg-primary: #09090b` base, light mode via `prefers-color-scheme`
- Purple accent: `--accent: #6c5ce7`
- Shadow and glow: `--accent-glow: rgba(108, 92, 231, 0.15)`
- Sidebar layout: 240px sidebar + flex main
- Status cards: rounded with hover border highlight
- Tables: sticky headers, hover rows, error-row highlighting
- Config: split layout (group sidebar + settings panel), inline descriptions
- Workers tab: xterm.js terminal per worker via CDN
- Responsive: sidebar collapses at 768px, config layout stacks vertically

**LoopManager** (`loop_manager.py`) — daemon lifecycle:

```
LoopManager
  ├─ start()      → kills stale daemons (pkill -f), reads config,
  │                 builds CLI args, creates_subprocess_exec,
  │                 starts stdout/stderr readers + process monitor
  ├─ stop()       → writes sentinel, kills process group (SIGTERM,
  │                 SIGKILL after 5s timeout)
  ├─ pause()      → writes "pause" to sentinel
  ├─ resume()     → removes sentinel file
  ├─ get_status() → merges ledger state (JSON file) with live iteration
  │                 state (parsed from daemon stdout) + worker logs
  │                 + recent web manager logs
  └─ get_ledger() → reads /tmp/infinite-loop-state.json
```

**Live stream parsing** (`_parse_daemon_line`):

The LoopManager parses daemon stdout in real-time to extract structured worker
state from log lines:

| Log Pattern | Parsed State |
|-------------|-------------|
| `[HH:MM:SS]   Iteration N` | `live_iteration.n = N`, resets workers |
| `[STDOUT (worker #N)]` / `[STDERR (worker #N)]` | Worker status = running |
| `[TERM (worker #N)] ...` | Appended to `worker_term[N]` for xterm.js |
| `[SPAWN (worker #N)]` | Worker registered as spawned |
| `[WORKER (worker #N)] Response in Xs (status=ok)` | Worker completed with duration |
| `[BEAT] Iteration N still running (Xs)` | `live_iteration.elapsed_seconds = X` |
| `[ERROR-TYPE] timeout` | `live_iteration.error_type = timeout` |

The `worker_term` storage is what powers the xterm.js terminal view in the
Workers tab — raw ANSI sequences are preserved, so colored output renders
correctly in-browser.

**Background status poller:**

A server-side asyncio task (`_status_poller`) wakes every 2 seconds, reads the
ledger via `LoopManager.get_status()`, builds a hash (iteration number × worker
statuses × error counts × mitigations × log count × terminal lines × latest
iteration fields), and broadcasts only on hash change (with a 10s keepalive
fallback). New log entries are dispatched individually as `log_entry` SSE events
with dedup via a `_seen_log_keys` set (capped at 5000 entries).

### Docker Deployment

**`Dockerfile`:**

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y git curl procps
WORKDIR /app
COPY pyproject.toml .
RUN pip install fastapi uvicorn python-dotenv
COPY web_app/ ./web_app/
COPY hermes_loop/ ./hermes_loop/
ENV WEB_PORT=8090
HEALTHCHECK --interval=30s ... CMD curl -fs http://localhost:${WEB_PORT}/api/health
ENTRYPOINT ["python", "-m", "web_app", "--host", "0.0.0.0"]
```

**`docker-compose.yml`:**

```yaml
services:
  hermes-loop:
    build: .
    network_mode: host      # needs host network for nsenter to run hermes on host
    pid: host               # access host process namespace for nsenter
    privileged: true        # nsenter requires CAP_SYS_PTRACE or privileged
    volumes:
      - ${INFINITE_LOOP_WORKDIR:-/tmp}:/workdir  # your target project
      - hermes-loop-data:/tmp                     # ledger persistence
    environment:
      - WEB_PORT=8090
```

**Critical design decisions:**

| Decision | Rationale |
|----------|-----------|
| `network_mode: host` | The container uses `nsenter` to run Hermes on the host, so it needs host networking to reach the Hermes binary's API endpoint |
| `pid: host` | Access the host's process namespace so `nsenter` can enter any host process |
| `privileged: true` | `nsenter` needs `CAP_SYS_PTRACE` to attach to non-child processes |
| Ledger at `/tmp` via named volume | `/tmp/infinite-loop-state.json` is the canonical ledger path; persisting it across restarts is critical |
| Workdir as bind mount | `INFINITE_LOOP_WORKDIR` maps to `/workdir` inside the container; the daemon reads/writes the target project here |
| `python -m web_app` | The container only runs the Web UI, not the daemon directly — the daemon is spawned as a subprocess within the container, which delegates to the host Hermes via nsenter |

**`.dockerignore`** excludes research/, references/, scripts/, run.sh, .env,
Makefile, CHANGELOG.md, CONTRIBUTING.md, and other runtime-unnecessary files.

---

## Iteration Lifecycle (Full Sequence Diagram)

Below is the complete lifecycle of a single iteration in the Infinite Loop
Daemon, shown as a sequence diagram. Each "→" represents a call or message
between components.

```
                                                                  ┌─ Spawned ─┐
                                              ┌─ Daemon Loop ──┐ │ Hermes    │
  User            run.sh          loop.py      iteration.py       │ Session   │
   │               │               │               │             │           │
   │   bash run.sh │               │               │             │           │
   │──────────────→│               │               │             │           │
   │               │──source .env─→│               │             │           │
   │               │──launch-loop→│               │             │           │
   │               │               │               │             │           │
   │               │               │ run_loop()    │             │           │
   │               │               │──────────────→│             │           │
   │               │               │               │             │           │
   │               │               │  ── Phase 1: Pre-Iteration ──           │
   │               │               │               │             │           │
   │               │               │ check_sentinel│             │           │
   │               │               │←─────────────│             │           │
   │               │               │ shutdown?     │             │           │
   │               │               │ max_iters?    │             │           │
   │               │               │ converge?     │             │           │
   │               │               │ idle?         │             │           │
   │               │               │               │             │           │
   │               │               │  ── Phase 2: Goal Selection ──          │
   │               │               │               │             │           │
   │               │               │ _cycle_goal() │             │           │
   │               │               │←─────────────│             │           │
   │               │               │  goal_text    │             │           │
   │               │               │               │             │           │
   │               │               │ _build_progressive_context()            │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │  ── Phase 3: Git Snapshot ──            │
   │               │               │               │             │           │
   │               │               │ git_before    │             │           │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │ cleanup_stale_worktrees()               │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │ _cleanup_stale_remote_branches()         │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │  ── Phase 4: Spawn Session(s) ──         │
   │               │               │               │             │           │
   │               │               │_execute_iteration()                      │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │               │ hermes chat -q ...      │
   │               │               │               │─────────────→│          │
   │               │               │               │             │           │
   │               │               │               │  ┌─ Inside Session ──┐  │
   │               │               │               │  │ read context      │  │
   │               │               │               │  │ read tools        │  │
   │               │               │               │  │ work()            │  │
   │               │               │               │  │ delegate_task() │  │
   │               │               │               │  │   → subagent(s)   │  │
   │               │               │               │  │ print JSON        │  │
   │               │               │               │  │ exit              │  │
   │               │               │               │  └───────────────────┘  │
   │               │               │               │             │           │
   │               │               │               │ stdout JSON │           │
   │               │               │               │←───────────│           │
   │               │               │               │             │           │
   │               │               │  ── Phase 5: Merge Results ──            │
   │               │               │               │             │           │
   │               │               │ _merge_worker_results()                  │
   │               │               │←─────────────│             │           │
   │               │               │  combined_error, total_duration,         │
   │               │               │  primary_error_type, next_goal           │
   │               │               │               │             │           │
   │               │               │  ── Phase 6: Worktree Merge ──           │
   │               │               │               │             │           │
   │               │               │ _merge_worktree_branches()                │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │  ── Phase 7: Git Snapshot ──             │
   │               │               │               │             │           │
   │               │               │ git_after     │             │           │
   │               │               │←─────────────│             │           │
   │               │               │ _git_auto_commit()                        │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │  ── Phase 8: Analysis ────                │
   │               │               │               │             │           │
   │               │               │ _detect_convergence()                     │
   │               │               │←─────────────│             │           │
   │               │               │ _compact_summaries()                      │
   │               │               │←─────────────│             │           │
   │               │               │ _build_iteration_record()                  │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │  ── Phase 9: Ledger Update ──             │
   │               │               │               │             │           │
   │               │               │ state["iterations"].append(record)        │
   │               │               │←─────────────│             │           │
   │               │               │ _recalc_stats()                           │
   │               │               │←─────────────│             │           │
   │               │               │ write_ledger(state) {file lock + atomic}  │
   │               │               │←─────────────│             │           │
   │               │               │ write_status_file()                       │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │  ── Phase 10: Broadcast ──                │
   │               │               │               │             │           │
   │               │               │ _handle_notifications()                   │
   │               │               │←─────────────│             │           │
   │               │               │ _write_status_html()   (if --status-html) │
   │               │               │←─────────────│             │           │
   │               │               │ _handle_callbacks() (HTTP callback / cmd) │
   │               │               │←─────────────│             │           │
   │               │               │ _broadcast_to_sse_clients()               │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │  ── Phase 11: Backoff & Sleep ──          │
   │               │               │               │             │           │
   │               │               │ _adapt_to_error() (mitigate if errors)    │
   │               │               │←─────────────│             │           │
   │               │               │ _handle_backoff()  (sleep if cooldown)    │
   │               │               │←─────────────│             │           │
   │               │               │               │             │           │
   │               │               │  ← back to top of while loop →           │
   │               │               │               │             │           │
```

**Key timing notes:**

- The entire iteration is synchronous from the daemon's perspective — it blocks
  on the spawned Hermes session completion.
- The heartbeat monitor runs on a background thread (polls every 5s). If the
  spawned session's heartbeat file goes stale, the daemon kills the subprocess
  with SIGTERM → SIGKILL and marks the iteration as `heartbeat` error.
- With `--workers N`, Phases 4–7 run in a `ThreadPoolExecutor` with N parallel
  sessions. `_merge_worker_results()` collects all results before proceeding.
- `_handle_backoff()` uses exponential backoff when `consecutive_errors` > 0:
  `delay = retry_delay * (attempt_number + 1)`.
- The SSE broadcast (`_broadcast_to_sse_clients()`) happens inside the main
  thread after the iteration loop, not in a background thread, ensuring that
  the broadcasted state is always consistent with what was written to the ledger.

**Data flow through one iteration:**

```
goal_text + context
        │
        ▼
_build_delegation_prompt()
        │
        ▼
[ "You are iteration #N (worker #W) of an autonomous loop daemon..."
  + goal + context + tools + JSON contract ]
        │
        ▼
hermes chat -q "..." -t terminal,file,delegation -Q --max-turns 500
        │
        ▼  (parsed from stdout)
extract_json_from_output()
  ├─ Strategy 1: reverse brace scan (fast path)
  └─ Strategy 2: forward scan of all JSON objects (fallback)
        │
        ▼
{ summary, duration_seconds, error, next_goal, context }
        │
        ▼
iteration record merged + analyzed → ledger → broadcast
```

**State transitions within a single worker session:**

```
IDLE → SPAWNED (hermes chat -q launched)
            │
            ▼
        RUNNING (stdout streaming, terminal output to web UI)
            │
      ┌─────┴──────┐
      │            │
      ▼            ▼
   SUCCESS       ERROR
   (exit=0,     (exit≠0,
    JSON OK)     no JSON / timeout / network fail)
      │            │
      ▼            ▼
   MERGED → iteration record built → recorded in ledger
```

**Worktree merge sequence** (when `--worktree` is set):

```
Before iteration:
    Per-worker: git worktree add hermes/w0/iterN
                                  hermes/w1/iterN
    Each worker commits to its own branch in the worktree.

After iteration:
    1. git checkout main (or base branch)
    2. For each worker branch:
         git merge hermes/wN/iterN --no-edit
       If merge succeeds: merged++
       If merge conflicts: git merge --abort, failed++
    3. git worktree remove hermes/wN/iterN
    4. git push origin main
    5. Remote cleanup: delete stale hermes/* branches from remote
```

**Error mitigation escalation** (during `_adapt_to_error()`):

```
Error count thresholds:
  timeout=3  → --session-timeout *= 2    (mild)
  timeout=5  → --cooldown elevated        (moderate)
  timeout=8  → force subprocess mode      (severe - stop)
  network=3  → force subprocess mode
  schema=3   → no mitigation (usually content issue)
  heartbeat>0→ force subprocess mode immediately

Each mitigation is tracked in state["mitigations"]["actions"]
and displayed in the SSE dashboard's mitigations panel.
```