# Infinite Loop — v14.0.0 Config Requirements

## What you need

1. **`hermes` on PATH** — the daemon calls `hermes chat -q "<prompt>" -t terminal,file,delegation` as a subprocess.
   Verify: `which hermes`

2. **A working Hermes config** — the spawned sessions use the same model,
   provider, and credentials as the parent session. Override with `--model`,
   `--provider`, or `--profile` flags.

3. **Disk space** — each iteration writes to the JSON ledger at
   `/tmp/infinite-loop-state.json`. Archive periodically:
   `bash scripts/archive-state.sh --auto`
   Or use `--keep-iterations N` for automatic trimming.

4. **Git (optional)** — `--git` and `--git-commit` require a git repo in
   the working directory.

5. **Notify cmd (optional)** — `--notify-cmd` must be a valid shell command.
   The iteration JSON is piped to its stdin.

6. **Context file (optional)** — for large contexts, use `--context-file PATH`
   instead of `--context` to avoid shell command-line length limits.

## No delegation config needed

v10.0.0 spawns `hermes chat -q <prompt> -t terminal,file,delegation` as a
subprocess on each iteration. The spawned Hermes session has real tools +
delegation. You do NOT need to set `max_spawn_depth`, `orchestrator_enabled`,
or any other delegation config for this skill.

## Verification

```bash
# Quick test
which hermes && echo "OK" || echo "NOT FOUND"

# Dry-run the daemon
python3 scripts/launch-loop.py --goal "test" --context "verify setup"

# Verify delegation works (spawn one session manually)
hermes chat -q "Run a quick check: count .py files in /tmp. Use delegate_task() to dispatch a subagent. Print JSON summary." -t terminal,file,delegation -Q --max-turns 10

# Start a real loop (will stop after first iteration)
python3 scripts/launch-loop.py --goal "test" --context "verify" --max-iterations 1 --run
bash scripts/inspect-ledger.sh
```
