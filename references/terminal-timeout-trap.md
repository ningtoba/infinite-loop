# Terminal Timeout Trap — Daemon Killed by Parent Terminal Timeout

## The Problem

When launching the daemon via `terminal(command="python3 launch-loop.py ... --run", background=true)`,
the **parent terminal call** has its own timeout (default 180s). Even though the
daemon runs in `background=true` mode, if the parent terminal call times out
before the daemon finishes its startup logging, the entire process tree
(including the background daemon) receives SIGTERM and dies silently.

This manifests as: the ledger at `/tmp/infinite-loop-state.json` is written
but has no iterations, or the daemon starts but vanishes within minutes.

## The Fix

Give the parent `terminal()` call a sufficiently high timeout when launching
the daemon:

```bash
terminal(command="python3 launch-loop.py --goal '...' --run", background=true, timeout=300)
```

The daemon itself uses `subprocess.run(..., timeout=session_timeout)` for its
spawned Hermes sessions, so the daemon's own timeout is controlled by
`--session-timeout` (default 7200s = 2 hours). These two timeouts are
**independent** — the parent terminal timeout only needs to be long enough
for the daemon to print its startup banner and enter the main loop.

A safe rule: set `timeout=300` for the parent terminal call when launching
the daemon. The daemon runs indefinitely in the background after that.

## The Root Cause

`terminal(background=true)` with `notify_on_complete=true` (the default for
bounded tasks) monitors process completion. If the process hasn't exited
within `timeout` seconds, the system sends SIGTERM to the process group.
Since the daemon is in the same process group as the parent terminal call,
it gets killed too.

## Solutions in This Skill

The daemon itself handles this in two ways:
1. Default `--session-timeout 7200` gives spawned sessions 2 hours
2. `signal.signal(signal.SIGTERM, _handle_shutdown)` handles graceful shutdown

But the **caller** (the Hermes agent using `terminal()`) must also set an
appropriate timeout for the launch command itself.
