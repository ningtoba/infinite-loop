#!/bin/bash
# replay-ledger.sh — Re-run archived iterations from a previous run (v1.0.0)
# Part of the infinite-loop skill
#
# Reads iterations from a JSONL archive file and re-runs them as new
# infinite-loop daemon goals. Useful for re-executing a known sequence
# of goals (e.g., from an evolved run) without manual re-entry.
#
# Usage:
#   bash scripts/replay-ledger.sh /path/to/archive.jsonl
#   bash scripts/replay-ledger.sh /path/to/archive.jsonl --goal "custom goal prefix"
#   bash scripts/replay-ledger.sh /path/to/archive.jsonl --from 3 --to 7
#   bash scripts/replay-ledger.sh /path/to/archive.jsonl --dry-run

set -euo pipefail

ARCHIVE_FILE=""
CUSTOM_GOAL=""
FROM=""
TO=""
DRY_RUN=false

show_help() {
  sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^#//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) show_help ;;
    --goal) CUSTOM_GOAL="$2"; shift 2 ;;
    --from) FROM="$2"; shift 2 ;;
    --to) TO="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -*)
      echo "Unknown option: $1"
      echo "Run with --help for usage."
      exit 1
      ;;
    *)
      if [ -z "$ARCHIVE_FILE" ]; then
        ARCHIVE_FILE="$1"
      else
        echo "Unexpected argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

if [ -z "$ARCHIVE_FILE" ]; then
  echo "ERROR: archive file path required"
  echo "Usage: $0 /path/to/archive.jsonl [options]"
  exit 1
fi

if [ ! -f "$ARCHIVE_FILE" ]; then
  echo "ERROR: archive file not found: $ARCHIVE_FILE"
  exit 1
fi

# Handle gzipped archives transparently
CAT_CMD="cat"
if [[ "$ARCHIVE_FILE" == *.gz ]]; then
  if command -v zcat &>/dev/null; then
    CAT_CMD="zcat"
  elif command -v gzip &>/dev/null; then
    CAT_CMD="gzip -dc"
  else
    echo "ERROR: cannot read gzipped archive (no zcat/gzip)"
    exit 1
  fi
fi

echo "=== Replay Ledger ==="
echo "Archive:  $ARCHIVE_FILE"
echo ""

# Read iterations from JSONL
ITERATIONS=$($CAT_CMD "$ARCHIVE_FILE" | python3 -c "
import json, sys
lines = [json.loads(l) for l in sys.stdin if l.strip()]
from_idx = int('${FROM:-0}')
to_idx = int('${TO:-999999}')
if from_idx > 0 or to_idx < 999999:
    lines = [l for l in lines if (from_idx <= l.get('n', 0) <= to_idx)]
print(json.dumps(lines))
")

COUNT=$(echo "$ITERATIONS" | python3 -c "import json,sys; print(len(json.loads(sys.stdin.read())))")

if [ "$COUNT" -eq 0 ]; then
  echo "No iterations match the filter."
  exit 0
fi

echo "Iterations to replay: $COUNT"
echo ""

# Display what would be replayed
echo "--- Goal Sequence ---"
echo "$ITERATIONS" | python3 -c "
import json, sys
items = json.loads(sys.stdin.read())
for it in items:
    n = it.get('n', '?')
    summary = (it.get('summary') or '')[:100]
    next_goal = it.get('next_goal', '')
    goal = next_goal if next_goal else summary
    print(f'  #{n}: {goal}')
"

echo ""

if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] No sessions spawned. Pass to a running infinite-loop daemon,"
  echo "          or run each goal manually with:"
  echo "    python3 launch-loop.py --goal \"<goal>\" --run"
  exit 0
fi

# Now actually replay: for each iteration, use its next_goal or summary as the goal
echo "--- Starting Replay ---"
echo "$ITERATIONS" | python3 -c "
import json, subprocess, sys, os, time

items = json.loads(sys.stdin.read())
script_dir = os.path.dirname(os.path.abspath('$0'))
skill_dir = os.path.normpath(os.path.join(script_dir, '..'))
launcher = os.path.join(skill_dir, 'launch-loop.py')

for i, it in enumerate(items):
    n = it.get('n', '?')
    next_goal = it.get('next_goal', '')
    summary = (it.get('summary') or '')[:120]
    goal = next_goal if next_goal else summary
    if not goal:
        goal = f'Continue work (iteration #{n})'

    # Build goal with optional custom prefix
    custom = '${CUSTOM_GOAL}' 
    if custom:
        goal = f'{custom}: {goal}'

    print(f'\\n--- Replaying iter #{n} ({i+1}/{len(items)}) ---')
    print(f'Goal: {goal[:120]}')
    
    context = it.get('summary', '')
    if it.get('error'):
        context += f'\\nPrevious error: {it[\"error\"]}'
    
    cmd = [sys.executable, launcher, '--goal', goal, '--context', context[:500], '--run']
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            print(f'OK: iter #{n} completed')
        else:
            print(f'FAIL: iter #{n} exited {result.returncode}')
            if result.stderr:
                print(f'  stderr: {result.stderr[:500]}')
    except subprocess.TimeoutExpired:
        print(f'TIMEOUT: iter #{n} took too long')
    except Exception as e:
        print(f'ERROR: iter #{n}: {e}')
" 2>&1

echo ""
echo "=== Replay Complete ==="
