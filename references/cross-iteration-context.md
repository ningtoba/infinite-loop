# Cross-Iteration Context Propagation (v14.0.0+)

## The Problem: Stateless Spawned Sessions

The infinite-loop daemon spawns child Hermes sessions via `hermes chat -q`
as independent subprocesses. Each child is a **fresh process** with:
- A new plugin/skill load
- Empty conversation history (no `session_search` results from prior children)
- Empty `hindsight_recall` (each child's discoveries die with it)
- Only what the daemon injects into the prompt

This means iteration N+1 starts with **zero knowledge** of what iteration N
accomplished, unless the daemon explicitly passes that knowledge forward.

## The Two-Level Fix

### Level 1: JSON `context` field (v11.5.0)

The spawned session includes a `context` field in its JSON output:

```json
{
  "summary": "Added validate_json_output() to launch-loop.py",
  "next_goal": "Update SKILL.md with documentation",
  "context": "Modified launch-loop.py between lines 520-680, added the validate_json_output() function and load_json_schema(). Next step: add --output-schema and --output-schema-file CLI flags in the main() argument parser, then update SKILL.md."
}
```

The daemon stores `next_context` from the first result and injects it as the
PRIMARY context for the next spawned session, replacing the old flat summary:

```python
if next_context:
    progressive_context = (
        f"[Context from previous iteration]: {next_context}"
    )
```

### Level 2: Self-Modification Awareness (v11.5.0)

When the goal mentions keywords like "infinite-loop", "launch-loop", or "skill",
the daemon auto-injects the skill directory path into spawned session prompts:

```
=== SELF-MODIFICATION CONTEXT ===
The daemon's source is at: ~/.hermes/skills/software-development/infinite-loop/scripts/launch-loop.py
The skill documentation is at: ~/.hermes/skills/software-development/infinite-loop/SKILL.md
```

Without this, spawned sessions don't know where the files they need to modify live.

## Why Evolution (`--evolve`) Alone Wasn't Enough

Before v11.5.0, the daemon had `--evolve` mode which used `next_goal` to set
the goal for the next iteration. But `next_goal` is just a short string --
it carries an intent without the context needed to act on it.

The `context` field carries the full state: specific files changed, line
ranges, what was added, what's pending. This is what lets iteration N+1
actually pick up where N left off.

## Why `session_search`/`hindsight_recall` Don't Help

These are natural suggestions that don't work because:

1. **Spawned sessions are independent processes** -- `session_search` searches
   the DAEMON's conversation, not the child's. The daemon doesn't talk to
   the user during iterations.
2. **`hindsight_recall` uses a shared Hindsight bank** -- but the child would
   need to query with the right query string, and the previous child would
   need to have saved findings. This is fragile.
3. **No guarantee** -- even with prompt instructions, the child may skip it.
   The daemon-level `context` field is deterministic.

## Design Rule

> The daemon must be the carrier of cross-iteration state, NOT the spawned
> sessions. Spawned sessions are ephemeral workers. The daemon is the
> persistent orchestrator.

This means:
- The daemon extracts `context` from every spawned JSON output
- The daemon injects it into the next spawned session's prompt
- The daemon stores it in the ledger for crash recovery
- The spawned session never needs to query external stores to know what
  the previous iteration did -- the daemon tells it directly
