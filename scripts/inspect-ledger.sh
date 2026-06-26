#!/bin/bash
# Inspect the infinite loop state ledger (v4.3.0)
# Part of the infinite-loop skill
#
# Usage:
#   bash scripts/inspect-ledger.sh                        # default path
#   bash scripts/inspect-ledger.sh /path/to/ledger.json
#   bash scripts/inspect-ledger.sh --watch                # poll every 5s
#   bash scripts/inspect-ledger.sh --watch=10             # poll every 10s
#   bash scripts/inspect-ledger.sh --inotify              # inotify-based watch (no polling)
#   bash scripts/inspect-ledger.sh --summary              # compact one-liner
#   bash scripts/inspect-ledger.sh --json                 # machine-readable JSON output
#   bash scripts/inspect-ledger.sh --json --last 10       # last 10 iterations as JSON
#   bash scripts/inspect-ledger.sh --last 20              # show last 20 iterations
#   bash scripts/inspect-ledger.sh --errors-only          # only show failed iterations
#   bash scripts/inspect-ledger.sh --errors-only --last N # last N errors

set -euo pipefail

LEDGER="${1:-/tmp/infinite-loop-state.json}"
WATCH=false
WATCH_INTERVAL=5
INOTIFY=false
SUMMARY=false
JSON_MODE=false
LAST_N=0
ERRORS_ONLY=false

# Parse positional and flags
POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --watch) WATCH=true; shift ;;
    --watch=*) WATCH=true; WATCH_INTERVAL="${1##*=}"; shift ;;
    --inotify) INOTIFY=true; shift ;;
    --summary) SUMMARY=true; shift ;;
    --json) JSON_MODE=true; shift ;;
    --errors-only) ERRORS_ONLY=true; shift ;;
    --last) LAST_N="$2"; shift 2 ;;
    --last=*) LAST_N="${1##*=}"; shift ;;
    --help)
      sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^#//'
      exit 0
      ;;
    *)
      POSITIONAL_ARGS+=("$1")
      shift
      ;;
  esac
done

# Restore positional (ledger path)
if [ ${#POSITIONAL_ARGS[@]} -gt 0 ]; then
  LEDGER="${POSITIONAL_ARGS[0]}"
fi

show_ledger() {
  local ledger_path="$1"

  if [ ! -f "$ledger_path" ]; then
    echo "No ledger found at $ledger_path"
    echo ""
    echo "Start an infinite loop first, or specify a different path:"
    echo "  $0 /path/to/ledger.json"
    return 1
  fi

  python3 -c "
import json

with open('$ledger_path') as f:
    d = json.load(f)

status = d.get('status', 'unknown')
started = d.get('started_at', '?')
total = d.get('total_iterations', 0)
goal = d.get('initial_command', '?')
tag = d.get('tag', '')
toolsets = d.get('toolsets', [])
compact_every = d.get('compact_every', '?')
last_updated = d.get('last_updated', '?')

errors_only = '$ERRORS_ONLY' == 'true'
max_iterations = d.get('max_iterations', 0)
git_enabled = d.get('git', False)
git_commit = d.get('git_commit', False)
retry_delay = d.get('retry_delay', 0)
notify_cmd = d.get('notify_cmd', '')
workdir = d.get('workdir', '')
evolve = d.get('evolve', False)
workers = d.get('workers', 1)
max_output_chars = d.get('max_output_chars', 2000)
evolved_goal = d.get('evolved_goal', '')
current_goal = d.get('current_goal', '')
iterations = d.get('iterations', [])
stats = d.get('stats', {})
pending = d.get('pending_iteration', None)
prompt_suffix = d.get('prompt_suffix', '')
html_dashboard = d.get('html_dashboard', '')
webhook_port = d.get('webhook_port', 0)
watch_dir = d.get('watch_dir', '')
eta = d.get('eta', {})
per_type = eta.get('per_type', {})
remaining = eta.get('remaining_formatted', '')

print(f'Status:         {status}')
print(f'Version:        {d.get(\"version\", 1)} ({d.get(\"version_detail\", \"\")})')
print(f'Started:        {started}')
print(f'Last updated:   {last_updated}')
print(f'Total iters:    {total}')
print(f'Compact every:  {compact_every}')
print(f\"Max iters:      {max_iterations if max_iterations > 0 else 'infinite'}\")
print(f'Toolsets:       {toolsets}')
print(f'Tag:            {tag if tag else \"(none)\"}')
print(f'Evolve:         {str(evolve).lower()}')
print(f'Workers:        {workers}')
print(f'Git:            {\"yes (auto-commit)\" if git_commit else (\"yes\" if git_enabled else \"no\")}')
print(f'Retry delay:    {retry_delay}s')
print(f'Output cap:     {max_output_chars if max_output_chars > 0 else \"unlimited\"}')
if workdir:
    print(f'Workdir:        {workdir}')
if notify_cmd:
    print(f'Notify cmd:     {notify_cmd[:60]}')
if prompt_suffix:
    print(f'Prompt suffix:  {prompt_suffix[:60]}')
if html_dashboard:
    print(f'HTML dashboard: {html_dashboard}')
if webhook_port:
    print(f'Webhook port:   {webhook_port}')
if watch_dir:
    print(f'Watch dir:      {watch_dir}')
if per_type:
    tt_str = ', '.join(f'{tt}: {v[\"avg\"]:.0f}s (x{v[\"count\"]})' for tt, v in per_type.items())
    print(f'ETA per type:   {tt_str}')
if remaining:
    print(f'ETA remaining:  {remaining}')
print('')
# Show current task type if available
if d.get('iterations') and d['iterations']:
    last_tt = d['iterations'][-1].get('task_type', 'unknown')
    last_toolsets = d['iterations'][-1].get('toolsets', toolsets)
    print(f'Current task:   {last_tt}')
    print(f'Active tools:   {last_toolsets}')
print('')
print(f'Goal: {goal}')
if evolved_goal:
    print(f'Evolved goal:   {evolved_goal[:80]}')
print('')

# Pending iteration warning
if pending:
    n = pending.get('n', '?')
    started_at = pending.get('started_at', '?')[:19]
    print(f'[WARN] Iteration #{n} is PENDING (started at {started_at})')
    print('       The agent has not yet completed this iteration.')
    print('       If this persists >300s, it will be recovered on next daemon start.')
    print('')

if stats:
    avg_dur = stats.get('avg_duration_seconds', 0)
    total_dur = stats.get('total_duration_seconds', 0)
    success_count = stats.get('success_count', 0)
    error_count = stats.get('error_count', 0)
    consecutive = stats.get('consecutive_errors', 0)
    print(f'Stats:  {total_dur:.0f}s total  |  avg {avg_dur:.0f}s/iter  |  {success_count} ok  |  {error_count} errors')
    if consecutive > 0:
        print(f'        [WARN] {consecutive} consecutive errors')
    print('')

if iterations:
    n = len(iterations)
    # Respect --last N if set
    last_n = int('$LAST_N') if '$LAST_N' != '0' else 5
    last_n = min(last_n, n)
    label = f'Last {last_n}' if last_n < n else f'All {n}'
    if errors_only:
        # Filter to error iterations
        err_iters = [it for it in iterations if it.get('error')]
        if not err_iters:
            print('No error iterations found.')
            print('')
            exit(0)
        print(f'Showing {len(err_iters)} error iteration(s):')
        for it in err_iters[-last_n:]:
            n_num = it.get('n', '?')
            dur = it.get('duration_seconds', 0)
            summary = (it.get('summary') or '')[:120]
            started_at = it.get('started_at', '?')[:19]
            err_text = str(it.get('error', ''))
            print(f'  #{n_num:>3}  {started_at}  {dur:>7.1f}s [ERR]')
            if summary:
                print(f'        {summary}')
            if err_text:
                print(f'        Error: {err_text}')
            print('')
        exit(0)
    print(f'{label} of {n} iterations:')
    for it in iterations[-last_n:]:
        n_num = it.get('n', '?')
        dur = it.get('duration_seconds', 0)
        summary = (it.get('summary') or '')[:120]
        compacted = ' [C]' if it.get('compacted') else ''
        has_error = ' [ERR]' if it.get('error') else ''
        started_at = it.get('started_at', '?')[:19]
        has_evolution = ' [EVOLVE]' if it.get('next_goal') else ''
        task_type_str = ''
        tt = it.get('task_type', '')
        if tt:
            task_type_str = f' [{tt}]'
        git_str = ''
        if it.get('git_commit'):
            git_str = ' [git:commit]'
        elif it.get('git_before') or it.get('git_after'):
            after = it.get('git_after', {})
            ds = after.get('diff_stat', '')
            if ds and '(no' not in ds:
                git_str = ' [git:changes]'
        workers_str = ''
        workers_n = it.get('workers', None)
        if workers_n and workers_n > 1:
            worker_errors = sum(1 for wr in (it.get('worker_results') or []) if wr.get('error'))
            workers_str = f' [W:{workers_n}]' + ('[E:{}]'.format(worker_errors) if worker_errors else '')
        throughput_str = ''
        cps = it.get('chars_per_second', 0)
        if cps:
            throughput_str = f' [{cps:.0f}cps]'
        truncated_str = ' [TRUNCATED]' if it.get('truncated') else ''
        total_bytes = it.get('total_output_bytes', 0)
        if total_bytes and not it.get('truncated'):
            # Show actual output size on non-truncated iterations too
            pass  # We just track it; it's in the JSON output
        print(f'  #{n_num:>3}  {started_at}  {dur:>7.1f}s{compacted}{has_error}{has_evolution}{task_type_str}{git_str}{workers_str}{throughput_str}{truncated_str}')
        if summary:
            print(f'        {summary}')
        if has_error:
            err_text = str(it.get('error', ''))
            print(f'        Error: {err_text}')
        if has_evolution:
            nxt = it.get('next_goal', '')
            if nxt:
                print(f'        Next: {nxt[:100]}')
        print('')

    total_duration = sum(it.get('duration_seconds', 0) for it in iterations)
    avg_duration = total_duration / len(iterations) if iterations else 0
    print(f'Total wall time: {total_duration:.0f}s ({total_duration/60:.1f}m)')
    print(f'Avg per iter:    {avg_duration:.0f}s')

    # If max_iterations is set, show ETA
    if max_iterations > 0 and len(iterations) > 0:
        remaining = max_iterations - len(iterations)
        eta_secs = remaining * avg_duration if remaining > 0 else 0
        pct = 100.0 * len(iterations) / max_iterations
        print(f'Progress:        {len(iterations)}/{max_iterations} ({pct:.0f}%)')
        if remaining > 0 and eta_secs > 0:
            if eta_secs >= 3600:
                print(f'ETA:             {eta_secs/3600:.1f}h ({eta_secs/60:.0f}m)')
            elif eta_secs >= 60:
                print(f'ETA:             {eta_secs/60:.0f}m')
            else:
                print(f'ETA:             {eta_secs:.0f}s')
else:
    print('No iterations recorded yet.')
print('')
" 2>&1 || {
  echo "[ERROR] Failed to parse ledger (not valid JSON?)"
  echo "Raw first 200 chars:"
  head -c 200 "$ledger_path"
  return 1
}
}

show_summary() {
  local ledger_path="$1"
  if [ ! -f "$ledger_path" ]; then
    echo "no-ledger"
    return
  fi
  python3 -c "
import json
with open('$ledger_path') as f:
    d = json.load(f)
status = d.get('status', '?')
n = d.get('total_iterations', 0)
goal = d.get('initial_command', '?')
tag = d.get('tag', '')
pending = d.get('pending_iteration', None)
evolved = d.get('evolved_goal', '')
p_str = ' [PENDING]' if pending else ''
e_str = ' [evolved to: {}]'.format(evolved[:40]) if evolved else ''
t_str = ' [tag: {}]'.format(tag) if tag else ''
print(f'{n} iters, {status}{p_str}{t_str}{e_str}: {goal[:60]}')
"
}

if [ "$SUMMARY" = true ]; then
  show_summary "$LEDGER"
  exit 0
fi

if [ "$JSON_MODE" = true ]; then
  # Machine-readable JSON output, optionally filtered to last N iterations
  if [ "$LAST_N" -gt 0 ] 2>/dev/null; then
    python3 -c "
import json
with open('$LEDGER') as f:
    d = json.load(f)
if 'iterations' in d and len(d['iterations']) > $LAST_N:
    d['iterations'] = d['iterations'][-${LAST_N}:]
    d['total_iterations'] = len(d['iterations'])
json.dump(d, indent=2, default=str)
"
  else
    python3 -m json.tool "$LEDGER"
  fi
  exit 0
fi

if [ "$INOTIFY" = true ]; then
  # inotify-based watching — no polling
  if ! command -v inotifywait &>/dev/null; then
    echo "inotifywait not found. Installing inotify-tools..."
    if command -v pacman &>/dev/null; then
      sudo pacman -S --noconfirm inotify-tools 2>/dev/null || true
    elif command -v apt-get &>/dev/null; then
      sudo apt-get install -y inotify-tools 2>/dev/null || true
    fi
  fi

  if command -v inotifywait &>/dev/null; then
    echo "=== Watching $LEDGER (inotify, press Ctrl+C to stop) ==="
    echo ""
    # Initial display
    show_ledger "$LEDGER"
    # Then watch for changes (inotifywait exits after each event)
    while inotifywait -qq -e close_write "$LEDGER" 2>/dev/null; do
      clear 2>/dev/null || true
      show_ledger "$LEDGER"
    done
    echo "inotifywait exited. Falling back to polling..."
  else
    echo "inotify-tools not available. Falling back to polling..."
    INOTIFY=false
    WATCH=true
  fi
fi

if [ "$WATCH" = true ]; then
  echo "=== Watching $LEDGER (poll every ${WATCH_INTERVAL}s, Ctrl+C to stop) ==="
  echo ""
  while true; do
    clear 2>/dev/null || true
    show_ledger "$LEDGER"
    sleep "$WATCH_INTERVAL"
  done
else
  show_ledger "$LEDGER"
fi
