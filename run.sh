#!/usr/bin/env bash
# run.sh — One-command entrypoint (v14.33.0) for the infinite-loop daemon
#
# Reads everything from .env, so you just run:
#   bash run.sh
#
# For more options:
#   bash run.sh --help       # Show full run.sh help
#   bash run.sh --dry-run    # Show config without starting
#
# All extra args are forwarded to launch-loop.py.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
LEDGER_PATH="/tmp/infinite-loop-state.json"

# ── Early-exit flags (no .env needed) ─────────────────────────────────────
if [[ "${1:-}" == "--demo" ]]; then
  exec python3 "$SCRIPT_DIR/launch-loop.py" "--demo"
fi
if [[ "${1:-}" == "--version" ]]; then
  exec python3 "$SCRIPT_DIR/launch-loop.py" "--version"
fi
if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
  echo "━━━ Infinite Loop Daemon — run.sh (v14.33.0) ━━━"
  echo ""
  echo "USAGE:  bash run.sh [OPTIONS]"
  echo ""
  echo "The one-command entrypoint. Reads everything from .env and forwards"
  echo "all settings as CLI flags to launch-loop.py."
  echo ""
  echo "OVERRIDE OPTIONS (take precedence over .env):"
  echo ""
  echo "  General:"
  echo "    --goal TEXT           Core task description (overrides INFINITE_LOOP_GOAL)"
  echo "    --context TEXT        Initial context (overrides INFINITE_LOOP_CONTEXT)"
  echo "    --max-iterations N    Stop after N iterations (default: 0 = infinite)"
  echo "    --max-turns N         Max turns per session (default: 500)"
  echo "    --workers N           Concurrent Hermes sessions (default: 1)"
  echo "    --tag TEXT            Label for the run (e.g. 'fix-auth')"
  echo "    --quiet / -q          Suppress verbose startup banner and iteration headers"
  echo ""
  echo "  Actions:"
  echo "    --demo                Interactive walkthrough of the daemon lifecycle"
  echo "    --dry-run             Print config and exit"
  echo "    --force-reset         Clear existing ledger, start fresh"
  echo "    --self-test           Run in-process unit tests and exit"
  echo "    --check-env           Validate .env file for typos and unknown variables"
  echo ""
  echo "  Info:"
  echo "    --help / -h           Show this help message"
  echo "    --version             Print daemon version and exit"
  echo "    --list-flags          Print all flags organized by group with help text"
  echo "    --list-groups         Print compact group names with flag counts"
  echo "    --examples            Print categorized real-world usage examples (7 categories)"
  echo "    --check-env           Validate .env file for typos and unknown variables"
  echo "    --doctor              Run comprehensive self-diagnosis"
  echo "    --completion-script {bash|zsh}  Generate shell completion (pipe to source)"
  echo ""
  echo "EXAMPLES:"
  echo "  bash run.sh                           # Run with .env config"
  echo "  bash run.sh --dry-run                 # Preview what would run"
  echo "  bash run.sh --self-test               # Run self-tests"
  echo "  bash run.sh --demo                    # Interactive lifecycle walkthrough"
  echo "  bash run.sh --goal 'Fix tests'        # Override .env goal"
  echo "  bash run.sh --force-reset --quiet     # Clean start, no banner"
  echo "  bash run.sh --git --git-commit        # Enable git auto-commit"
  echo ""
  echo "ALL other flags are forwarded directly to launch-loop.py."
  echo "See: python3 launch-loop.py --help  (for the full flag reference)"
  echo ""
  echo "QUICK REFERENCE:"
  echo "  Install:   make install              # hermes_loop on PATH"
  echo "  Run:       make run                  # reads .env"
  echo "  Ledger:    cat /tmp/infinite-loop-state.json | python3 -m json.tool"
  echo "  Status:    bash scripts/inspect-ledger.sh"
  echo "  Stop:      echo 'stop' > /tmp/infinite-loop-stop"
  echo "  Pause:     echo 'pause' > /tmp/infinite-loop-stop"
  echo "  Resume:    echo 'resume' > /tmp/infinite-loop-stop"
  echo "  Dashboard: python3 -m http.server 8080 --directory /tmp/"
  echo "             → http://localhost:8080/loop-status.html"
  echo "  Completions: make completion"
  exit 0
fi

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: .env not found at $ENV_FILE"
  echo "Copy .env.example to .env and configure it first:"
  echo "  cp .env.example .env"
  exit 1
fi

# Export all .env vars so launch-loop.py can read them via os.environ
set -a
source "$ENV_FILE"
set +a

# ── Build daemon args ─────────────────────────────────────────────────────────
declare -a DAEMON_ARGS=()

# Map .env vars to CLI flags (only set non-empty values)
[ -n "${INFINITE_LOOP_GOAL:-}" ]            && DAEMON_ARGS+=("--goal" "$INFINITE_LOOP_GOAL")
[ -n "${INFINITE_LOOP_CONTEXT:-}" ]         && DAEMON_ARGS+=("--context" "$INFINITE_LOOP_CONTEXT")
[ -n "${INFINITE_LOOP_CONTEXT_FILE:-}" ]    && DAEMON_ARGS+=("--context-file" "$INFINITE_LOOP_CONTEXT_FILE")
[ -n "${INFINITE_LOOP_TOOLSETS:-}" ]        && DAEMON_ARGS+=("--toolsets" "$INFINITE_LOOP_TOOLSETS")
[ -n "${INFINITE_LOOP_WORKDIR:-}" ]         && DAEMON_ARGS+=("--workdir" "$INFINITE_LOOP_WORKDIR")
[ -n "${INFINITE_LOOP_MAX_ITERATIONS:-}" ]  && DAEMON_ARGS+=("--max-iterations" "$INFINITE_LOOP_MAX_ITERATIONS")
[ -n "${INFINITE_LOOP_MAX_TURNS:-}" ]       && DAEMON_ARGS+=("--max-turns" "$INFINITE_LOOP_MAX_TURNS")
[ -n "${INFINITE_LOOP_COMPACT_EVERY:-}" ]   && DAEMON_ARGS+=("--compact-every" "$INFINITE_LOOP_COMPACT_EVERY")
[ "${INFINITE_LOOP_EVOLVE:-false}" == "true" ]     && DAEMON_ARGS+=("--evolve")
[ "${INFINITE_LOOP_RUN:-false}" == "true" ]        && DAEMON_ARGS+=("--run")
[ "${INFINITE_LOOP_GIT:-false}" == "true" ]        && DAEMON_ARGS+=("--git")
[ "${INFINITE_LOOP_GIT_COMMIT:-false}" == "true" ] && DAEMON_ARGS+=("--git-commit")
[ "${INFINITE_LOOP_STORE_GIT_DIFF:-false}" == "true" ] && DAEMON_ARGS+=("--store-git-diff")
[ -n "${INFINITE_LOOP_WORKERS:-}" ]         && DAEMON_ARGS+=("--workers" "$INFINITE_LOOP_WORKERS")
[ -n "${INFINITE_LOOP_SESSION_TIMEOUT:-}" ] && DAEMON_ARGS+=("--session-timeout" "$INFINITE_LOOP_SESSION_TIMEOUT")
[ -n "${INFINITE_LOOP_RETRY_DELAY:-}" ]     && DAEMON_ARGS+=("--retry-delay" "$INFINITE_LOOP_RETRY_DELAY")
[ -n "${INFINITE_LOOP_MAX_RETRIES:-}" ]     && DAEMON_ARGS+=("--max-retries" "$INFINITE_LOOP_MAX_RETRIES")
[ -n "${INFINITE_LOOP_COOLDOWN:-}" ]        && DAEMON_ARGS+=("--cooldown" "$INFINITE_LOOP_COOLDOWN")
[ -n "${INFINITE_LOOP_COOLDOWN_MODE:-}" ]   && DAEMON_ARGS+=("--cooldown-mode" "$INFINITE_LOOP_COOLDOWN_MODE")
[ -n "${INFINITE_LOOP_MAX_OUTPUT_CHARS:-}" ] && DAEMON_ARGS+=("--max-output-chars" "$INFINITE_LOOP_MAX_OUTPUT_CHARS")
[ -n "${INFINITE_LOOP_TAG:-}" ]             && DAEMON_ARGS+=("--tag" "$INFINITE_LOOP_TAG")
[ -n "${INFINITE_LOOP_PROFILE:-}" ]         && DAEMON_ARGS+=("--profile" "$INFINITE_LOOP_PROFILE")
[ -n "${INFINITE_LOOP_MODEL:-}" ]           && DAEMON_ARGS+=("--model" "$INFINITE_LOOP_MODEL")
[ -n "${INFINITE_LOOP_PROVIDER:-}" ]        && DAEMON_ARGS+=("--provider" "$INFINITE_LOOP_PROVIDER")
[ -n "${INFINITE_LOOP_SHUTDOWN_SENTINEL:-}" ] && DAEMON_ARGS+=("--shutdown-sentinel" "$INFINITE_LOOP_SHUTDOWN_SENTINEL")
[ -n "${INFINITE_LOOP_LOG_FILE:-}" ]        && DAEMON_ARGS+=("--log-file" "$INFINITE_LOOP_LOG_FILE")
[ -n "${INFINITE_LOOP_LOG_MAX_MB:-}" ]      && DAEMON_ARGS+=("--log-max-mb" "$INFINITE_LOOP_LOG_MAX_MB")
[ -n "${INFINITE_LOOP_STATUS_HTML:-}" ]     && DAEMON_ARGS+=("--status-html" "$INFINITE_LOOP_STATUS_HTML")
[ -n "${INFINITE_LOOP_STATUS_FILE:-}" ]     && DAEMON_ARGS+=("--status-file" "$INFINITE_LOOP_STATUS_FILE")
[ -n "${INFINITE_LOOP_GOALS_FILE:-}" ]      && DAEMON_ARGS+=("--goals-file" "$INFINITE_LOOP_GOALS_FILE")
[ -n "${INFINITE_LOOP_WEBHOOK_PORT:-}" ]    && DAEMON_ARGS+=("--webhook-port" "$INFINITE_LOOP_WEBHOOK_PORT")
[ -n "${INFINITE_LOOP_WORKER_URL:-}" ]      && DAEMON_ARGS+=("--worker-url" "$INFINITE_LOOP_WORKER_URL")
[ -n "${INFINITE_LOOP_NOTIFY_CMD:-}" ]      && DAEMON_ARGS+=("--notify-cmd" "$INFINITE_LOOP_NOTIFY_CMD")
[ -n "${INFINITE_LOOP_ON_ERROR_CMD:-}" ]    && DAEMON_ARGS+=("--on-error-cmd" "$INFINITE_LOOP_ON_ERROR_CMD")
[ -n "${INFINITE_LOOP_HTTP_CALLBACK:-}" ]   && DAEMON_ARGS+=("--http-callback" "$INFINITE_LOOP_HTTP_CALLBACK")
[ -n "${INFINITE_LOOP_NOTIFY_PUSHBULLET:-}" ] && DAEMON_ARGS+=("--notify-pushbullet" "$INFINITE_LOOP_NOTIFY_PUSHBULLET")
[ -n "${INFINITE_LOOP_NOTIFY_NTFY:-}" ]     && DAEMON_ARGS+=("--notify-ntfy" "$INFINITE_LOOP_NOTIFY_NTFY")
[ -n "${INFINITE_LOOP_NOTIFY_NTFY_SERVER:-}" ] && DAEMON_ARGS+=("--notify-ntfy-server" "$INFINITE_LOOP_NOTIFY_NTFY_SERVER")
[ "${INFINITE_LOOP_NOTIFY_DESKTOP:-false}" == "true" ]   && DAEMON_ARGS+=("--notify-desktop")
[ "${INFINITE_LOOP_NOTIFY_ON_COMPLETION:-false}" == "true" ] && DAEMON_ARGS+=("--notify-on-completion")
# Only add --preflight from .env if --run is NOT also set (--run already triggers checks)
if [ "${INFINITE_LOOP_RUN:-false}" != "true" ]; then
  [ "${INFINITE_LOOP_PREFLIGHT:-false}" == "true" ]        && DAEMON_ARGS+=("--preflight")
fi
[ "${INFINITE_LOOP_PREFLIGHT_FAIL_FAST:-false}" == "true" ] && DAEMON_ARGS+=("--preflight-fail-fast")
[ -n "${INFINITE_LOOP_SKILLS:-}" ]          && DAEMON_ARGS+=("--skills" "$INFINITE_LOOP_SKILLS")
[ "${INFINITE_LOOP_CONVERGENCE_STOP:-false}" == "true" ] && DAEMON_ARGS+=("--convergence-stop")
[ -n "${INFINITE_LOOP_CONVERGENCE_THRESHOLD:-}" ] && DAEMON_ARGS+=("--convergence-threshold" "$INFINITE_LOOP_CONVERGENCE_THRESHOLD")
[ -n "${INFINITE_LOOP_CONVERGENCE_WINDOW:-}" ]   && DAEMON_ARGS+=("--convergence-window" "$INFINITE_LOOP_CONVERGENCE_WINDOW")
[ -n "${INFINITE_LOOP_OUTPUT_SCHEMA:-}" ]   && DAEMON_ARGS+=("--output-schema" "$INFINITE_LOOP_OUTPUT_SCHEMA")
[ -n "${INFINITE_LOOP_OUTPUT_SCHEMA_FILE:-}" ] && DAEMON_ARGS+=("--output-schema-file" "$INFINITE_LOOP_OUTPUT_SCHEMA_FILE")
[ -n "${INFINITE_LOOP_STARTUP_DELAY:-}" ]   && DAEMON_ARGS+=("--startup-delay" "$INFINITE_LOOP_STARTUP_DELAY")
[ "${INFINITE_LOOP_QUIET:-false}" == "true" ]         && DAEMON_ARGS+=("--quiet")
[ -n "${INFINITE_LOOP_PROMPT_SUFFIX:-}" ]   && DAEMON_ARGS+=("--prompt-suffix" "$INFINITE_LOOP_PROMPT_SUFFIX")
[ -n "${INFINITE_LOOP_WATCH_DIR:-}" ]       && DAEMON_ARGS+=("--watch-dir" "$INFINITE_LOOP_WATCH_DIR")
[ -n "${INFINITE_LOOP_WATCH_POLL:-}" ]      && DAEMON_ARGS+=("--watch-poll" "$INFINITE_LOOP_WATCH_POLL")
[ -n "${INFINITE_LOOP_ARCHIVE_DIR:-}" ]     && DAEMON_ARGS+=("--archive-dir" "$INFINITE_LOOP_ARCHIVE_DIR")
[ -n "${INFINITE_LOOP_ARCHIVE_RETENTION:-}" ] && DAEMON_ARGS+=("--archive-retention" "$INFINITE_LOOP_ARCHIVE_RETENTION")
[ -n "${INFINITE_LOOP_ARCHIVE_MAX_SIZE:-}" ] && DAEMON_ARGS+=("--archive-max-size" "$INFINITE_LOOP_ARCHIVE_MAX_SIZE")
[ -n "${INFINITE_LOOP_KEEP_ITERATIONS:-}" ] && DAEMON_ARGS+=("--keep-iterations" "$INFINITE_LOOP_KEEP_ITERATIONS")
[ -n "${INFINITE_LOOP_TASK_TYPE:-}" ]       && DAEMON_ARGS+=("--task-type" "$INFINITE_LOOP_TASK_TYPE")
[ "${INFINITE_LOOP_NO_AUTO_TOOLSETS:-false}" == "true" ]    && DAEMON_ARGS+=("--no-auto-toolsets")
[ "${INFINITE_LOOP_NO_FAILURE_LEARNING:-false}" == "true" ] && DAEMON_ARGS+=("--no-failure-learning")
[ -n "${INFINITE_LOOP_HEARTBEAT_TIMEOUT:-}" ] && DAEMON_ARGS+=("--heartbeat-timeout" "$INFINITE_LOOP_HEARTBEAT_TIMEOUT")
[ -n "${INFINITE_LOOP_MAX_IDLE_ITERATIONS:-}" ] && DAEMON_ARGS+=("--max-idle-iterations" "$INFINITE_LOOP_MAX_IDLE_ITERATIONS")
[ -n "${INFINITE_LOOP_SPAWN_SOURCE:-}" ]    && DAEMON_ARGS+=("--spawn-source" "$INFINITE_LOOP_SPAWN_SOURCE")

# Boolean flags (no value arg)
[ "${INFINITE_LOOP_STOP_AT_GOALS_END:-false}" == "true" ]  && DAEMON_ARGS+=("--stop-at-goals-end")
[ "${INFINITE_LOOP_TRACK_GOALS:-false}" == "true" ]        && DAEMON_ARGS+=("--track-goals")
[ "${INFINITE_LOOP_RESET_GOALS:-false}" == "true" ]        && DAEMON_ARGS+=("--reset-goals")
[ "${INFINITE_LOOP_USE_LIBRARY:-false}" == "true" ]        && DAEMON_ARGS+=("--use-library")
[ "${INFINITE_LOOP_PASS_SESSION_ID:-false}" == "true" ]    && DAEMON_ARGS+=("--pass-session-id")
[ "${INFINITE_LOOP_CHECKPOINTS:-false}" == "true" ]        && DAEMON_ARGS+=("--checkpoints")
[ "${INFINITE_LOOP_RESUME:-false}" == "true" ]             && DAEMON_ARGS+=("--resume")
[ "${INFINITE_LOOP_IGNORE_RULES:-false}" == "true" ]       && DAEMON_ARGS+=("--ignore-rules")
[ "${INFINITE_LOOP_IGNORE_USER_CONFIG:-false}" == "true" ] && DAEMON_ARGS+=("--ignore-user-config")
[ "${INFINITE_LOOP_YOLO:-false}" == "true" ]               && DAEMON_ARGS+=("--yolo")
[ "${INFINITE_LOOP_SAFE_MODE:-false}" == "true" ]          && DAEMON_ARGS+=("--safe-mode")
[ "${INFINITE_LOOP_ACCEPT_HOOKS:-false}" == "true" ]       && DAEMON_ARGS+=("--accept-hooks")
[ "${INFINITE_LOOP_WORKTREE:-false}" == "true" ]           && DAEMON_ARGS+=("--worktree")
[ "${INFINITE_LOOP_CONTINUE:-false}" == "true" ]           && DAEMON_ARGS+=("--continue")

# ── Process overrides from CLI args ───────────────────────────────────────────
declare -a EXTRA_ARGS=()
QUIET=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)    DAEMON_ARGS+=("--dry-run"); DRY_RUN=true; shift ;;
    --force-reset) DAEMON_ARGS+=("--force-reset"); shift ;;
    --self-test)  DAEMON_ARGS+=("--self-test"); shift ;;
    --quiet|-q)   DAEMON_ARGS+=("--quiet"); QUIET=true; shift ;;
    --version)    exec python3 "$SCRIPT_DIR/launch-loop.py" "--version" ;;
    --goal)       DAEMON_ARGS+=("--goal" "$2"); shift 2 ;;
    --context)    DAEMON_ARGS+=("--context" "$2"); shift 2 ;;
    --max-iterations) DAEMON_ARGS+=("--max-iterations" "$2"); shift 2 ;;
    --max-turns)  DAEMON_ARGS+=("--max-turns" "$2"); shift 2 ;;
    --workers)    DAEMON_ARGS+=("--workers" "$2"); shift 2 ;;
    --tag)        DAEMON_ARGS+=("--tag" "$2"); shift 2 ;;
    --help|-h)    echo "See 'bash run.sh --help' for usage."; exit 0 ;;
    --list-flags|--list-groups|--examples) DAEMON_ARGS+=("$1"); shift ;;
    --check-env)  DAEMON_ARGS+=("--check-env"); shift ;;
    --doctor)     DAEMON_ARGS+=("--doctor"); shift ;;
    --demo)       DAEMON_ARGS+=("--demo"); shift ;;
    --completion-script) DAEMON_ARGS+=("$1" "$2"); shift 2 ;;
    *)            EXTRA_ARGS+=("$1"); shift ;;
  esac
done

# ── Banner ────────────────────────────────────────────────────────────────────
if [ "$QUIET" = false ]; then
  echo '╔══════════════════════════════════════════════╗'
  echo '║  Infinite Loop Daemon v14.33.0               ║'
  echo '║  run.sh — one command to start               ║'
  echo '║                                                ║'
  echo '║  What is new ⚡                              ║'
  echo '║  • --demo: interactive lifecycle walkthrough ║'
  echo '║  • --help-topic: group-filtered flag help     ║'
  echo '║  • --doctor: comprehensive self-diagnosis    ║'
  echo '║  • --init wizard: 13 config steps            ║'
  echo '║                                                ║'
  echo '║  Also available:                              ║'
  echo '║  • --status: compact ledger overview          ║'
  echo '║  • Shutdown summary with next-steps           ║'
  echo '║  • Colorized log tags and startup banner     ║'
  echo '║  • [SUMMARY] with ETA/progress bar             ║'
  echo '║  • Shows git changes, CPU/mem per iteration   ║'
  echo '║  • Worker breakdown for multi-worker runs     ║'
  echo '║  • --examples: categorized usage patterns     ║'
  echo '║  • Shell tab-completion for all flags          ║'
  echo '║  • --list-flags and --list-groups quick ref    ║'
  echo '║  • [SUGGEST] smart fixes on errors/stuck      ║'
  echo '║  • --quiet mode: compact per-iteration output ║'
  echo '║  • [BEAT] heartbeat during long iterations    ║'
  echo '║  • --self-test count auto-detected             ║'
  echo '╚══════════════════════════════════════════════╝'
  echo ""
  echo "  Config: .env"
  echo "  Goal: ${INFINITE_LOOP_GOAL:0:80}..."
  echo "  Workers: ${INFINITE_LOOP_WORKERS:-1}  |  Max iters: ${INFINITE_LOOP_MAX_ITERATIONS:-∞}"
  echo "  Mode: quiet=${INFINITE_LOOP_QUIET:-off}  |  Git: ${INFINITE_LOOP_GIT:-off}  |  Evolve: ${INFINITE_LOOP_EVOLVE:-off}"
  echo "  Toolsets: ${INFINITE_LOOP_TOOLSETS:-terminal,file,delegation,web}"
  echo ""
  echo "  Commands:"
  echo "    Stop:   echo 'stop'   > ${INFINITE_LOOP_SHUTDOWN_SENTINEL:-/tmp/infinite-loop-stop}"
  echo "    Pause:  echo 'pause'  > ${INFINITE_LOOP_SHUTDOWN_SENTINEL:-/tmp/infinite-loop-stop}"
  echo "    Status: ${INFINITE_LOOP_STATUS_FILE:-/tmp/loop-status.json}"
  echo "    Log:    tail -f ${INFINITE_LOOP_LOG_FILE:-/tmp/infinite-loop.log}"
  echo "    Help:   python3 launch-loop.py --help"
  echo ""
fi

# ── Launch ────────────────────────────────────────────────────────────────────
# Strip --run when --dry-run is active (--run makes dry-run a no-op)
if [ "${DRY_RUN:-false}" = "true" ]; then
  filtered=()
  for arg in "${DAEMON_ARGS[@]}"; do
    [ "$arg" != "--run" ] && filtered+=("$arg")
  done
  exec python3 "$SCRIPT_DIR/launch-loop.py" "${filtered[@]}" "${EXTRA_ARGS[@]}"
fi
exec python3 "$SCRIPT_DIR/launch-loop.py" "${DAEMON_ARGS[@]}" "${EXTRA_ARGS[@]}"
