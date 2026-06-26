# Toolset Restriction for Spawned Hermes Sessions (v14.0.0+)

## The Correct Pattern: `chat -q` with `terminal,file,delegation`

**v10.0.0 architecture change**: Previous versions used `hermes -z` (oneshot mode),
which was fundamentally incompatible with `delegate_task()`. The `-z` session
exits before subagent results arrive — work is dispatched but never collected.

v10.0.0 fixes this by using `hermes chat -q` (non-interactive query mode):
- `chat -q` keeps the session alive for multiple turns
- `--max-turns 90` gives the session enough turns to delegate AND receive results
- `-Q` suppresses banner/spinner for clean JSON output parsing
- The spawned session has BOTH real tools AND delegation

```bash
# Default: spawned session has terminal, file, AND delegation
hermes chat -q "your prompt" -t terminal,file,delegation -Q --max-turns 90

# For web research with delegation
hermes chat -q "your prompt" -t terminal,file,web,delegation -Q --max-turns 90

# For pure delegation (no direct tools)
hermes chat -q "your prompt" -t delegation -Q --max-turns 90
```

## Why `chat -q` Instead of `-z`

| Feature | `hermes -z` (OLD - v9.x) | `hermes chat -q` (NEW - v10.0+) |
|---------|--------------------------|----------------------------------|
| Session lifetime | Exits after one LLM response | Stays alive for N turns |
| `delegate_task()` support | Broken — exits before results arrive | Works — session waits for subagent results |
| Clean output | Yes, but no subagent results | Yes with `-Q` flag |
| Turn limit | None (one turn only) | Configurable via `--max-turns` |
| Use case | Fire-and-forget tasks | Delegation loops that need results |

## Available Toolset Names

| Toolset | What it allows |
|---------|---------------|
| `terminal` | Shell commands + process management |
| `file` | File read/write/search/patch |
| `web` | Web search + content extraction |
| `search` | Web search only (subset of `web`) |
| `delegation` | delegate_task() — dispatch background subagents |
| `browser` | Browser automation |
| `skills` | Skill browsing and management |
| `memory` | Persistent memory |
| `cronjob` | Scheduled job management |
| `todo` | Task planning |
| `vision` | Image analysis |
| `session_search` | Past session search |

Combine with commas: `-t terminal,file,delegation`

## What About `-z` Mode?

The `-z` (oneshot) flag still exists and is useful for simple fire-and-forget
queries where you don't need delegation. Use it for:
- Quick questions: `hermes -z "what's the weather"`
- Simple commands: `hermes -z "format this code" -t terminal,file`

Do NOT use `-z` when:
- You need `delegate_task()` to return results
- You're building a delegation loop
- The spawned session needs multiple turns to complete work

## When to Use Toolset Restriction

Use toolset restriction when you need the spawned session to play a
specific role and you want to enforce that role at the capability level
rather than hoping it follows a prompt instruction.

Do NOT use toolset restriction when the spawned session needs full
autonomy — for those cases, omit the `-t` flag (it inherits all default
tools, including delegation which still works for `chat -q` sessions).
