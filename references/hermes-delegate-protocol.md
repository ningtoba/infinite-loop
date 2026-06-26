# Hermes Delegate Protocol (v3.0.0 — DEPRECATED)

> **Deprecated in v5.0.0+** — The loop daemon now spawns `hermes -z -t delegation`
> as a subprocess on each iteration, which has ONLY the `delegation` toolset.
> The spawned session **cannot** do work directly — it has no terminal, file,
> or web tools. It MUST call `delegate_task()`.
>
> This reference is preserved for historical context and for anyone who
> wants to understand the old architecture. **Do not use for new setups.**

The `--hermes-delegate` mode let the loop daemon signal the parent Hermes
agent to call `delegate_task()` on each iteration. This was for tasks that
needed subagent reasoning (not just shell commands).

## File Protocol

The daemon and agent communicated via two files in `/tmp/`:

```
Daemon writes:    /tmp/infinite-loop-needs-agent.json  →  Agent reads this
Agent writes:     /tmp/infinite-loop-agent-result.json →  Daemon reads this
```

### Signal file — written by daemon:

```json
{
  "iteration": 5,
  "goal": "Refactor auth module to JWT",
  "context": "Code lives in src/auth/. Tests in tests/test_auth.py.",
  "toolsets": ["terminal", "file"],
  "signaled_at": "2026-06-25T19:35:00+00:00"
}
```

### Result file — written by agent:

```json
{
  "summary": "Refactored auth/login.py to use JWT with HS256",
  "duration_seconds": 120,
  "error": null,
  "output": "3 files changed, 45 insertions, 12 deletions"
}
```

## Ledger states

| State | Meaning |
|-------|---------|
| `running` | Daemon is working autonomously (command/task-list/script modes) |
| `awaiting_agent` | Daemon wrote signal file, waiting for agent to respond |
| `stopped: sentinel` | Graceful shutdown via `/tmp/infinite-loop-stop` |
| `stopped: max_iterations (N)` | Hit max-iterations limit |
| `stopped: task-generator-empty` | Script mode — generator returned nothing |
| `completed: all N tasks done` | Task-list mode — all tasks consumed |
| `error: *` | Something broke |

## When to use `--hermes-delegate` vs the v5.0+ spawn approach

| Situation | Approach |
|-----------|----------|
| "Run a background loop with enforced delegation" | **v5.0+ (spawn -t delegation)** — spawned session has NO tools except delegate_task() |
| "I want to control each iteration myself" | `--hermes-delegate` (old protocol) |
