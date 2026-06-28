#!/bin/bash
# run-loop.sh — Unified entrypoint (v14.37.0 — Demo mode + interactive walkthrough)
#
# THE PRIMARY way to create an autonomous delegation loop. No cron jobs.
#
# Starts the infinite loop daemon that spawns Hermes sessions via `chat -q`
# (NOT -z oneshot). Each spawned session has terminal, file, AND delegation
# tools. Because `chat -q` keeps the session alive for multiple turns (unlike
# -z which exits immediately), delegate_task() subagent results can arrive
# and be collected properly.
#
# v11.6.0 enhancements:
#   - Fixed version header (docstring said v11.0.0, now synced to actual version)
#   - Added --version flag with version string
#   - Introduced VERSION constant as single source of truth
#   - Fixed multi-worker context merging (all worker contexts now merged)
#   - Updated session-self-loop.py to v2.0.0 with workdir, timeout, goal-file, compact-every, convergence detection, status file, better polling
#
# Usage:
#   bash scripts/run-loop.sh --goal "refactor auth to use JWT" \
#       --context "Code in src/auth/. Respond in English." --workdir /path/to/project
#
#   # Or run the daemon directly:
#   python3 launch-loop.py --goal "..." --run
#
# Options:
#   --goal TEXT          Core task for spawned sessions (required)
#   --context TEXT       Initial context
#   --toolsets LIST      Comma-separated toolsets (default: terminal,file,delegation,web,skills,browser,memory,session_search)
#   --workdir PATH       Working directory for spawned Hermes sessions
#   --max-iterations N   Auto-stop after N iterations (0=infinite, default)
#   --max-turns N        Max turns per spawned Hermes session (default: 500)
#   --compact-every N    Compact summaries every N iterations (default: 5)
#   --retry-delay N      Backoff delay on error (default: 0)
#   --session-timeout N  Max seconds per Hermes session (default: 7200)
#   --evolve             Let iterations propose next goal (self-directing)
#   --git                Capture git diff stats per iteration
#   --git-commit         Auto-commit changes per iteration (implies --git)
#   --workers N          Run N concurrent Hermes sessions per iteration (default: 1)
#   --notify-cmd CMD     Shell command after each iteration (JSON on stdin)
#   --http-callback URL  HTTP POST URL for iteration JSON (alternative to --notify-cmd)
#   --max-output-chars N Max chars of output to store (default: 2000, 0=unlimited)
#   --no-run             Only init ledger, don't start daemon
#   --recover            Check for stale pending iteration and recover
#   --max-idle-iterations N  Stop after N consecutive iterations with no git changes
#   --max-retries N      Retry a failed iteration up to N times (0=no retry)
#   --on-error-cmd CMD   Shell command when an iteration fails (JSON on stdin)
#   --tag LABEL          Label/identifier for the run (e.g. 'project:fix-auth')
#   --prompt-suffix TEXT Extra instructions appended to every spawned prompt
#   --force-reset        Clear existing ledger and start fresh
#   --status-file PATH   Write one-line JSON status to this file for monitoring
#   --profile NAME       Hermes profile for spawned sessions
#   --model NAME         Model override for spawned sessions
#   --provider NAME      Provider override for spawned sessions
#   --context-file PATH  Read context from a file
#   --no-auto-toolsets   Disable automatic toolset enrichment based on task type
#   --no-failure-learning Disable injection of past failure context into spawned sessions
#   --task-type TYPE     Force task type (research|code-fix|code-build|system-admin|data-processing|content|general)
#   --dry-run            Print config and exit without spawning
#   --keep-iterations N  Auto-shrink ledger to last N iterations (0=keep all)
#   --cooldown N         Wait N seconds between iterations (rate-limit awareness)
#   --cooldown-mode MODE 'fixed' or 'adaptive' (auto-calculated from avg iteration duration)
#   --goals-file PATH    File with one goal per line for batch processing
#   --stop-at-goals-end  Stop when goals file is exhausted (instead of wrapping)
#   --output-schema JSON Inline JSON Schema to validate spawned output
#   --output-schema-file PATH  Path to JSON Schema file for output validation
#   --convergence-stop   Auto-stop when iterations produce similar summaries
#   --convergence-threshold FLOAT  Similarity threshold (0.0-1.0, default: 0.9)
#   --convergence-window N  Recent iterations to compare (default: 5)
#   --store-git-diff     Store actual git diff in ledger (capped at 10KB)
#   --webhook-port N     Port for HTTP webhook server (POST /webhook triggers iteration)
#   --log-file PATH      Path to daemon log file (adds file logging alongside stdout)
#   --log-max-mb N       Max log file size in MB before rotation (default: 10)
#   --status-html PATH   Generate self-contained HTML status dashboard
#   --watch-dir PATH     Watch directory for file changes (triggers iteration)
#   --watch-poll SECONDS File watcher poll interval (default: 5.0)
#   --worker-url URL     Hermes worker URL ('auto', 'http://host:port', or '' for direct)
#   --startup-delay N   Wait N seconds before first iteration (default: 0)
#   --notify-desktop    Send desktop notifications via notify-send (Linux only)
#   --notify-on-completion  Send summary notification when daemon finishes
#   --save-config PATH  Save current configuration to JSON and exit
#   --config PATH       Load configuration from JSON file
#   --preflight         Run comprehensive health checks before loop starts
#   --preflight-fail-fast  Stop on first preflight failure
#   --notify-pushbullet TOKEN  Pushbullet access token for mobile notifications
#   --notify-ntfy TOPIC       ntfy topic name for push notifications
#   --notify-ntfy-server URL  ntfy server URL (default: https://ntfy.sh)
#   --use-library            Use AIAgent.run_conversation() in-process (no subprocess)
#   --pass-session-id        Pass session ID to spawned sessions for tracking
#   --checkpoints            Enable file checkpoints in spawned sessions
#   --resume                 Chain spawned sessions across iterations (requires --pass-session-id)
#   --skills LIST            Skills to preload in spawned sessions (comma-separated)
#   --ignore-rules           Start spawned sessions without AGENTS.md, memory, or rules
#   --yolo                 Bypass approval prompts in spawned sessions (fully autonomous)
#   --ignore-user-config   Start spawned sessions without loading ~/.hermes/config.yaml
#   --spawn-source TEXT    Source tag for spawned sessions (e.g. 'infinite-loop')
#   --safe-mode           Spawn sessions in troubleshooting mode (disable all customizations)
#   --accept-hooks        Auto-approve shell hooks in spawned sessions
#   --worktree            Run spawned sessions in isolated git worktree
#   --continue            Resume the most recent session in spawned sessions
#   --archive-dir DIR     Archive directory for trimmed iterations (default: ~/.hermes/infinite-loop-archives/)
#   --archive-retention N Days to keep archives (default: 30)
#   --archive-max-size MB Max total archive size in MB (default: 100)
#   --self-test           Run in-process self-tests and exit (no spawning)
#   --track-goals         Track completed goals in ledger, skip on restart
#   --reset-goals         Clear tracked goals for fresh run
#   --shutdown-sentinel PATH  Path to sentinel file (default: /tmp/infinite-loop-stop)
#   --quiet / -q          Suppress banner output (for CI/CD and scripts)
#   --help                   Show this help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"  # scripts/ is sibling of root files
LEDGER_PATH="/tmp/infinite-loop-state.json"

show_help() {
  sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^#//'
  exit 0
}

declare -a DAEMON_ARGS=()
GOAL=""
NO_RUN=false
RECOVER=false
QUIET=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) show_help ;;
    --no-run) NO_RUN=true; shift ;;
    --recover) RECOVER=true; shift ;;
    --goal) GOAL="$2"; DAEMON_ARGS+=("--goal" "$2"); shift 2 ;;
    --context) DAEMON_ARGS+=("--context" "$2"); shift 2 ;;
    --toolsets) DAEMON_ARGS+=("--toolsets" "$2"); shift 2 ;;
    --workdir) DAEMON_ARGS+=("--workdir" "$2"); shift 2 ;;
    --max-iterations) DAEMON_ARGS+=("--max-iterations" "$2"); shift 2 ;;
    --max-turns) DAEMON_ARGS+=("--max-turns" "$2"); shift 2 ;;
    --compact-every) DAEMON_ARGS+=("--compact-every" "$2"); shift 2 ;;
    --retry-delay) DAEMON_ARGS+=("--retry-delay" "$2"); shift 2 ;;
    --session-timeout) DAEMON_ARGS+=("--session-timeout" "$2"); shift 2 ;;
    --evolve) DAEMON_ARGS+=("--evolve"); shift ;;
    --git) DAEMON_ARGS+=("--git"); shift ;;
    --git-commit) DAEMON_ARGS+=("--git-commit"); shift ;;
    --workers) DAEMON_ARGS+=("--workers" "$2"); shift 2 ;;
    --notify-cmd) DAEMON_ARGS+=("--notify-cmd" "$2"); shift 2 ;;
    --http-callback) DAEMON_ARGS+=("--http-callback" "$2"); shift 2 ;;
    --max-output-chars) DAEMON_ARGS+=("--max-output-chars" "$2"); shift 2 ;;
    --max-idle-iterations) DAEMON_ARGS+=("--max-idle-iterations" "$2"); shift 2 ;;
    --max-retries) DAEMON_ARGS+=("--max-retries" "$2"); shift 2 ;;
    --on-error-cmd) DAEMON_ARGS+=("--on-error-cmd" "$2"); shift 2 ;;
    --tag) DAEMON_ARGS+=("--tag" "$2"); shift 2 ;;
    --prompt-suffix) DAEMON_ARGS+=("--prompt-suffix" "$2"); shift 2 ;;
    --force-reset) DAEMON_ARGS+=("--force-reset"); shift ;;
    --status-file) DAEMON_ARGS+=("--status-file" "$2"); shift 2 ;;
    --profile) DAEMON_ARGS+=("--profile" "$2"); shift 2 ;;
    --model) DAEMON_ARGS+=("--model" "$2"); shift 2 ;;
    --provider) DAEMON_ARGS+=("--provider" "$2"); shift 2 ;;
    --context-file) DAEMON_ARGS+=("--context-file" "$2"); shift 2 ;;
    --dry-run) DAEMON_ARGS+=("--dry-run"); shift ;;
    --keep-iterations) DAEMON_ARGS+=("--keep-iterations" "$2"); shift 2 ;;
    --no-auto-toolsets) DAEMON_ARGS+=("--no-auto-toolsets"); shift ;;
    --no-failure-learning) DAEMON_ARGS+=("--no-failure-learning"); shift ;;
    --task-type) DAEMON_ARGS+=("--task-type" "$2"); shift 2 ;;
    --cooldown) DAEMON_ARGS+=("--cooldown" "$2"); shift 2 ;;
    --cooldown-mode) DAEMON_ARGS+=("--cooldown-mode" "$2"); shift 2 ;;
    --goals-file) DAEMON_ARGS+=("--goals-file" "$2"); shift 2 ;;
    --stop-at-goals-end) DAEMON_ARGS+=("--stop-at-goals-end"); shift ;;
    --output-schema) DAEMON_ARGS+=("--output-schema" "$2"); shift 2 ;;
    --output-schema-file) DAEMON_ARGS+=("--output-schema-file" "$2"); shift 2 ;;
    --convergence-stop) DAEMON_ARGS+=("--convergence-stop"); shift ;;
    --convergence-threshold) DAEMON_ARGS+=("--convergence-threshold" "$2"); shift 2 ;;
    --convergence-window) DAEMON_ARGS+=("--convergence-window" "$2"); shift 2 ;;
    --store-git-diff) DAEMON_ARGS+=("--store-git-diff"); shift ;;
    --webhook-port) DAEMON_ARGS+=("--webhook-port" "$2"); shift 2 ;;
    --log-file) DAEMON_ARGS+=("--log-file" "$2"); shift 2 ;;
    --log-max-mb) DAEMON_ARGS+=("--log-max-mb" "$2"); shift 2 ;;
    --status-html) DAEMON_ARGS+=("--status-html" "$2"); shift 2 ;;
    --watch-dir) DAEMON_ARGS+=("--watch-dir" "$2"); shift 2 ;;
    --watch-poll) DAEMON_ARGS+=("--watch-poll" "$2"); shift 2 ;;
    --worker-url) DAEMON_ARGS+=("--worker-url" "$2"); shift 2 ;;
    --startup-delay) DAEMON_ARGS+=("--startup-delay" "$2"); shift 2 ;;
    --notify-desktop) DAEMON_ARGS+=("--notify-desktop"); shift ;;
    --notify-on-completion) DAEMON_ARGS+=("--notify-on-completion"); shift ;;
    --notify-pushbullet) DAEMON_ARGS+=("--notify-pushbullet" "$2"); shift 2 ;;
    --notify-ntfy) DAEMON_ARGS+=("--notify-ntfy" "$2"); shift 2 ;;
    --notify-ntfy-server) DAEMON_ARGS+=("--notify-ntfy-server" "$2"); shift 2 ;;
    --use-library) DAEMON_ARGS+=("--use-library"); shift ;;
    --pass-session-id) DAEMON_ARGS+=("--pass-session-id"); shift ;;
    --checkpoints) DAEMON_ARGS+=("--checkpoints"); shift ;;
    --resume) DAEMON_ARGS+=("--resume"); shift ;;
    --skills) DAEMON_ARGS+=("--skills" "$2"); shift 2 ;;
    --ignore-rules) DAEMON_ARGS+=("--ignore-rules"); shift ;;
    --yolo) DAEMON_ARGS+=("--yolo"); shift ;;
    --ignore-user-config) DAEMON_ARGS+=("--ignore-user-config"); shift ;;
    --spawn-source) DAEMON_ARGS+=("--spawn-source" "$2"); shift 2 ;;
    --safe-mode) DAEMON_ARGS+=("--safe-mode"); shift ;;
    --accept-hooks) DAEMON_ARGS+=("--accept-hooks"); shift ;;
    --worktree) DAEMON_ARGS+=("--worktree"); shift ;;
    --continue) DAEMON_ARGS+=("--continue"); shift ;;
    --archive-dir) DAEMON_ARGS+=("--archive-dir" "$2"); shift 2 ;;
    --archive-retention) DAEMON_ARGS+=("--archive-retention" "$2"); shift 2 ;;
    --archive-max-size) DAEMON_ARGS+=("--archive-max-size" "$2"); shift 2 ;;
    --save-config) DAEMON_ARGS+=("--save-config" "$2"); shift 2 ;;
    --config) DAEMON_ARGS+=("--config" "$2"); shift 2 ;;
    --preflight) DAEMON_ARGS+=("--preflight"); shift ;;
    --preflight-fail-fast) DAEMON_ARGS+=("--preflight-fail-fast"); shift ;;
    --self-test) DAEMON_ARGS+=("--self-test"); shift ;;
    --track-goals) DAEMON_ARGS+=("--track-goals"); shift ;;
    --reset-goals) DAEMON_ARGS+=("--reset-goals"); shift ;;
    --shutdown-sentinel) DAEMON_ARGS+=("--shutdown-sentinel" "$2"); shift 2 ;;
    --quiet|-q) QUIET=true; shift ;;
    *) echo "Unknown option: $1"; show_help ;;
  esac
done

if [ -z "$GOAL" ] && [ "$RECOVER" = false ]; then
  echo "ERROR: --goal is required"
  echo "Run with --help for usage."
  exit 1
fi

if [ "$QUIET" = false ]; then
  echo "╔══════════════════════════════════════════════╗"
  echo "║  Infinite Loop - v14.37.0                       ║"
  echo "║  Makefile, CONTRIBUTING.md,                       ║"
  echo "║  Improved --help, SSE fix, Dashboard v3 SSE,     ║"
  echo "║  Error Panel, Performance Metrics,               ║"
  echo "║  Goals Visualization, XSS Fix, Convergence       ║"
  echo "║  Guard, Idempotent Goal Execution,               ║"
  echo "║  Concurrent Library Mode, Auto Error Recovery,   ║"
  echo "║  In-Process Archiving, Multi-Profile Goals,      ║"
  echo "║  Self-Test Mode, Progress Classification,        ║"
  echo "║  AIAgent library, Session Tracking,              ║"
  echo "║  Pushbullet & ntfy Notifications,                ║"
  echo "║  Preflight, REST Control, Session Self-Healing   ║"
  echo "║  Heartbeat, --quiet mode, No cron. Real loops.   ║"
  echo "╚══════════════════════════════════════════════╝"
  echo ""
fi

# Check hermes is available
if ! command -v hermes &>/dev/null; then
  echo "[WARN] 'hermes' binary not found on PATH."
  echo "[WARN] The loop will fail on the first iteration."
  echo ""
fi

# Stale pending check
if [ -f "$LEDGER_PATH" ]; then
  echo "--- Ledger Recovery Check ---"
  echo "  (Previous run may have been interrupted.)"
  echo ""
fi

if [ "$RECOVER" = true ]; then
  echo "Recovery check complete."
  exit 0
fi

# Init
echo "--- Initializing Loop ---"
python3 "${SKILL_DIR}/launch-loop.py" "${DAEMON_ARGS[@]}" 2>&1
echo ""

if [ "$NO_RUN" = true ]; then
  echo "Ledger initialized. Run with --run to start:"
  echo "  python3 ${SKILL_DIR}/launch-loop.py ${DAEMON_ARGS[*]} --run"
  exit 0
fi

# Run
if [ "$QUIET" = false ]; then
  echo "--- Starting Loop ---"
  echo "PID: $$"
  echo "Ledger: $LEDGER_PATH"
  echo "Sentinel: echo 'stop' > /tmp/infinite-loop-stop (also 'pause' / 'resume')"
  echo ""
  echo "Each iteration spawns 'hermes chat -q' with task-optimized prompts,"
  echo "auto-toolset enrichment, failure learning, and deep multi-level delegation."
  echo "Toolsets: terminal,file,delegation,web,skills,browser,memory,session_search,code_execution,todo,vision"
fi

exec python3 "${SKILL_DIR}/launch-loop.py" "${DAEMON_ARGS[@]}" --run
