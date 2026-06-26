# YAML Null Pitfall — Historical Reference (pre-v7.0.0)

This file is kept for historical reference only. The v7.0.0+ infinite-loop skill
does NOT use the file-based delegation protocol or require delegation config.

The daemon spawns `hermes -z "<prompt>" -t delegation` — the spawned Hermes session
handles delegation via delegate_task() with its own isolated toolset.

## The original pitfall (v3.x — v4.0.0)

If you're reviewing old ledger data or old scripts: `hermes config set
delegation.max_spawn_depth null` writes `null` as a YAML string, not
the bare YAML null value. This meant subagents couldn't delegate further.
The `verify-delegation-config.sh` script handled the fix via Python's
YAML library.

**This is NOT relevant to v7.0.0+.** The daemon spawns independent Hermes
subprocesses that are self-contained — they use the config that's already
on your system. No delegation config changes needed.
