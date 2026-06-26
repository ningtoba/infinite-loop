#!/bin/bash
# Archive the infinite loop state during or after a run (v3.1.0).
# Part of the infinite-loop skill
#
# The loop ledger is a single file (/tmp/infinite-loop-state.json) that grows
# unboundedly. Use this script to archive iterations to a dated JSONL file and
# optionally trim the ledger to keep only the last N entries (compact mode).
#
# Usage:
#   bash scripts/archive-state.sh /tmp/infinite-loop-state.json
#   bash scripts/archive-state.sh /tmp/infinite-loop-state.json --keep 10
#   bash scripts/archive-state.sh --all                     # archive + clear
#   bash scripts/archive-state.sh --export-md               # export as markdown report
#   bash scripts/archive-state.sh --export-md --output report.md  # custom output path
#   bash scripts/archive-state.sh --gzip                    # compress archive with gzip
#   bash scripts/archive-state.sh --auto                    # auto mode: archive + keep last 100

set -euo pipefail

LEDGER="${1:-/tmp/infinite-loop-state.json}"
KEEP=""
GZIP=false
ARCHIVE_DIR="${HOME}/.hermes/infinite-loop-archives"
MODE="normal"
OUTPUT_PATH=""

# Parse args
POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) MODE="all"; shift ;;
    --export-md) MODE="export-md"; shift ;;
    --keep) KEEP="$2"; shift 2 ;;
    --keep=*) KEEP="${1##*=}"; shift ;;
    --output) OUTPUT_PATH="$2"; shift 2 ;;
    --output=*) OUTPUT_PATH="${1##*=}"; shift ;;
    --gzip) GZIP=true; shift ;;
    --auto) MODE="auto"; shift ;;
    --init-archive-dir)
      mkdir -p "$ARCHIVE_DIR"
      echo "Archive directory ready: $ARCHIVE_DIR"
      exit 0
      ;;
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

# Restore positional
if [ ${#POSITIONAL_ARGS[@]} -gt 0 ]; then
  LEDGER="${POSITIONAL_ARGS[0]}"
fi

if [ ! -f "$LEDGER" ]; then
  echo "No ledger found at $LEDGER"
  exit 1
fi

mkdir -p "$ARCHIVE_DIR"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

if [ "$MODE" = "export-md" ]; then
  # Export as Markdown report
  MD_FILE="${OUTPUT_PATH:-${ARCHIVE_DIR}/report-${TIMESTAMP}.md}"
  python3 -c "
import json

with open('$LEDGER') as f:
    d = json.load(f)

lines = []
lines.append('# Infinite Loop Report')
lines.append('')
lines.append(f'- **Status:** {d.get(\"status\", \"?\")}')
lines.append(f'- **Version:** {d.get(\"version\", 1)} ({d.get(\"version_detail\", \"\")})')
lines.append(f'- **Started:** {d.get(\"started_at\", \"?\")}')
lines.append(f'- **Last updated:** {d.get(\"last_updated\", \"?\")}')
lines.append(f'- **Total iterations:** {d.get(\"total_iterations\", 0)}')
lines.append(f'- **Max iterations:** {d.get(\"max_iterations\", 0) if d.get(\"max_iterations\", 0) > 0 else \"infinite\"}')
lines.append(f'- **Git:** {d.get(\\"git\\", False)} (auto-commit: {d.get(\\"git_commit\\", False)})')
lines.append(f'- **Workdir:** {d.get(\"workdir\", \"(cwd)\")}')
lines.append(f'- **Goal:** {d.get(\"initial_command\", \"?\")}')
lines.append(f'- **Toolsets:** {d.get(\"toolsets\", [])}')
lines.append('')

iterations = d.get('iterations', [])
if iterations:
    stats = d.get('stats', {})
    total_dur = stats.get('total_duration_seconds', sum(it.get('duration_seconds', 0) for it in iterations))
    avg_dur = total_dur / len(iterations) if iterations else 0
    lines.append(f'## Summary')
    lines.append('')
    lines.append(f'- Total duration: {total_dur:.0f}s ({total_dur/60:.1f}m)')
    lines.append(f'- Average per iteration: {avg_dur:.0f}s')
    lines.append(f'- Successful: {stats.get(\"success_count\", \"?\")}')
    lines.append(f'- Errors: {stats.get(\"error_count\", 0)}')
    lines.append('')
    lines.append(f'## Iterations')
    lines.append('')
    lines.append('| # | Started | Duration | Status | Compacted | Changes | Summary |')
    lines.append('|---|---------|----------|--------|-----------|---------|---------|')
    for it in iterations:
        n = it.get('n', '?')
        started = str(it.get('started_at', '?'))[:19]
        dur = it.get('duration_seconds', 0)
        status = 'ERROR' if it.get('error') else 'OK'
        compacted = 'Yes' if it.get('compacted') else ''
        git = 'git:commit' if it.get('git_commit') else ('git:changes' if it.get('git_after') and it['git_after'].get('diff_stat', '') not in ('(no unstaged changes)', '') else '')
        summary = (it.get('summary') or '')[:80].replace('|', '/')
        lines.append(f'| {n} | {started} | {dur}s | {status} | {compacted} | {git} | {summary} |')
    lines.append('')

output = '\\n'.join(lines)
with open('$MD_FILE', 'w') as f:
    f.write(output)
print(f'Markdown report written to $MD_FILE')
" 2>&1
  exit 0
fi

if [ "$MODE" = "auto" ]; then
  # Auto mode: archive iterations and trim to last 100
  KEEP="${KEEP:-100}"
  # Fall through to default archive logic with keep=100
fi

if [ "$MODE" = "all" ]; then
  # Archive everything, then clear the ledger
  ARCHIVE_FILE="${ARCHIVE_DIR}/ledger-${TIMESTAMP}.json"
  cp "$LEDGER" "$ARCHIVE_FILE"
  python3 -c "
import json
with open('$LEDGER') as f:
    d = json.load(f)
d['iterations'] = []
d['total_iterations'] = 0
d['stats'] = {'total_duration_seconds': 0.0, 'avg_duration_seconds': 0.0, 'success_count': 0, 'error_count': 0, 'consecutive_errors': 0}
d['last_updated'] = '$TIMESTAMP'
d['status'] = 'archived'
d.pop('pending_iteration', None)
with open('$LEDGER', 'w') as f:
    json.dump(d, f, indent=2, default=str)
" 2>&1
  echo "Archived $ARCHIVE_FILE ($(du -h "$ARCHIVE_FILE" | cut -f1))"
  echo "Ledger cleared — ready for fresh run."
  exit 0
fi

# Default: archive to dated JSONL, optionally trim
ARCHIVE_FILE="${ARCHIVE_DIR}/iterations-${TIMESTAMP}.jsonl"
python3 -c "
import json

with open('$LEDGER') as f:
    d = json.load(f)

iterations = d.get('iterations', [])
if not iterations:
    print('No iterations to archive.')
    exit(0)

# Write each iteration as a JSONL line
with open('$ARCHIVE_FILE', 'w') as f:
    for it in iterations:
        f.write(json.dumps(it, default=str) + '\n')

print(f'Archived {len(iterations)} iterations to $ARCHIVE_FILE')

# Compress with gzip if flag set
if [ "$GZIP" = true ]; then
  if command -v gzip &>/dev/null; then
    gzip -f "$ARCHIVE_FILE"
    ARCHIVE_FILE="${ARCHIVE_FILE}.gz"
    echo "Compressed: ${ARCHIVE_FILE}"
  else
    echo "[WARN] gzip not found, skipping compression"
  fi
fi

# Trim if --keep was specified
keep_str = '$KEEP'
if keep_str:
    keep = int(keep_str)
    if keep > 0 and len(iterations) > keep:
        d['iterations'] = iterations[-keep:]
        d['total_iterations'] = len(d['iterations'])
        with open('$LEDGER', 'w') as f:
            json.dump(d, f, indent=2, default=str)
        print(f'Trimmed ledger to last {keep} iterations.')
" 2>&1
