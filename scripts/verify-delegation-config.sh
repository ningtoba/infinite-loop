#!/bin/bash
# Verify and fix delegation config for infinite-loop
# Part of the infinite-loop skill (v3.0.0)
# Run this before starting the loop to ensure unlimited sub-subagent nesting
#
# Usage:
#   bash scripts/verify-delegation-config.sh
#   bash scripts/verify-delegation-config.sh --quiet   # only show issues, not passes
#
# Returns:
#   0 = all checks passed
#   1 = issues found and fixed (restart required)
#   2 = critical failure (config missing, etc.)

set -euo pipefail

CONFIG_FILE="${HOME}/.hermes/config.yaml"
NEED_FIX=false
QUIET=false

# Parse args
for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=true ;;
  esac
done

log() {
  if [ "$QUIET" = false ] || [ "${1:-}" = "FAIL" ] || [ "${1:-}" = "WARN" ] || [ "${1:-}" = "NOTE" ]; then
    echo "$@"
  fi
}

echo "=== Infinite Loop — Delegation Config Check ==="
echo ""

if [ ! -f "$CONFIG_FILE" ]; then
  echo "[FAIL] Config file not found at $CONFIG_FILE"
  echo "       Run 'hermes setup' to create it first."
  exit 2
fi

# --- max_spawn_depth ---
if grep -qE "^  max_spawn_depth:\s*null\s*$" "$CONFIG_FILE" 2>/dev/null; then
  log "[PASS] max_spawn_depth = null (unlimited nesting allowed)"
elif grep -q "^  max_spawn_depth:" "$CONFIG_FILE" 2>/dev/null; then
  CURRENT=$(grep "^  max_spawn_depth:" "$CONFIG_FILE" | head -1)
  echo "[FAIL] max_spawn_depth is not null"
  echo "       Current: $CURRENT"
  NEED_FIX=true
else
  echo "[FAIL] max_spawn_depth not found in config"
  echo "       Will add it..."
  NEED_FIX=true
fi

# --- orchestrator_enabled ---
if grep -qE "^  orchestrator_enabled:\s*true\s*$" "$CONFIG_FILE" 2>/dev/null; then
  log "[PASS] orchestrator_enabled = true"
elif grep -q "^  orchestrator_enabled:" "$CONFIG_FILE" 2>/dev/null; then
  CURRENT=$(grep "^  orchestrator_enabled:" "$CONFIG_FILE" | head -1)
  echo "[FAIL] orchestrator_enabled is not true"
  echo "       Current: $CURRENT"
  NEED_FIX=true
else
  echo "[WARN] orchestrator_enabled not found — default is true, assuming OK"
fi

# --- max_concurrent_children ---
CURRENT_CHILDREN=$(grep "^  max_concurrent_children:" "$CONFIG_FILE" | head -1 | awk '{print $2}' 2>/dev/null || echo "0")
if [ "$CURRENT_CHILDREN" -ge 2 ] 2>/dev/null; then
  log "[PASS] max_concurrent_children = $CURRENT_CHILDREN (≥2 recommended)"
else
  echo "[WARN] max_concurrent_children = $CURRENT_CHILDREN (recommend ≥2 for parallel delegation)"
  NEED_FIX=true
fi

# --- max_iterations ---
CURRENT_ITER=$(grep "^  max_iterations:" "$CONFIG_FILE" | head -1 | awk '{print $2}' 2>/dev/null || echo "50")
if [ "$CURRENT_ITER" = "0" ] || [ "$CURRENT_ITER" = "null" ]; then
  log "[INFO] max_iterations = $CURRENT_ITER (no cap on child iterations)"
else
  echo "[NOTE] max_iterations = $CURRENT_ITER (children will stop after this many iterations)"
  echo "       Set to 0 for unlimited: hermes config set delegation.max_iterations 0"
fi

# --- child_timeout_seconds (new check) ---
CURRENT_TIMEOUT=$(grep "^  child_timeout_seconds:" "$CONFIG_FILE" | head -1 | awk '{print $2}' 2>/dev/null || echo "0")
if [ "$CURRENT_TIMEOUT" = "0" ]; then
  log "[INFO] child_timeout_seconds = 0 (no wall-clock cap) — good for long subagent iterations"
else
  echo "[NOTE] child_timeout_seconds = $CURRENT_TIMEOUT (may kill long-running subagents)"
  echo "       Set to 0 to disable: hermes config set delegation.child_timeout_seconds 0"
fi

echo ""
if [ "$NEED_FIX" = true ]; then
  echo "=== Applying fixes ==="
  # Note: The 'hermes config set' writes 'null' as a string in YAML.
  # We need to write the bare null value for max_spawn_depth.
  # Since hermes config set may not handle bare null correctly for this key,
  # we use python to modify the YAML directly for reliability.
  python3 -c "
import yaml, os
path = os.path.expanduser('$CONFIG_FILE')
with open(path) as f:
    cfg = yaml.safe_load(f) or {}
if 'delegation' not in cfg:
    cfg['delegation'] = {}
cfg['delegation']['max_spawn_depth'] = None  # YAML null
cfg['delegation']['orchestrator_enabled'] = True
cfg['delegation']['max_concurrent_children'] = 3
with open(path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)
print('Config updated successfully.')
" 2>/dev/null || {
  echo "[WARN] Python YAML update failed, falling back to hermes CLI..."
  hermes config set delegation.max_spawn_depth null 2>/dev/null || true
  hermes config set delegation.orchestrator_enabled true 2>/dev/null || true
  hermes config set delegation.max_concurrent_children 3 2>/dev/null || true
}

  echo ""
  echo "[DONE] Config updated."
  echo "IMPORTANT: Start a new Hermes session (/reset or exit and re-launch)"
  echo "          for these changes to take effect."
  echo ""
  echo "Verify with:"
  echo "  grep -A 8 '^delegation:' $CONFIG_FILE"
  exit 1
else
  echo "[ALL PASS] Config is ready for infinite-loop."
  echo ""
  echo "Summary:"
  grep -A 8 '^delegation:' "$CONFIG_FILE" 2>/dev/null || echo "(delegation section not found)"
  exit 0
fi
