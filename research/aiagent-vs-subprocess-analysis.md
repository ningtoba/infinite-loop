# AIAgent Python Library vs `hermes chat -q` Subprocess: Analysis for infinite-loop

## Sources Examined

- **~/.hermes/hermes-agent/run_agent.py** (5573 lines) — AIAgent class definition, `chat()` and `run_conversation()` methods
- **~/.hermes/hermes-agent/agent/conversation_loop.py** (4656 lines) — The actual `run_conversation()` implementation
- **~/.hermes/hermes-agent/agent/turn_finalizer.py** (485 lines) — Post-loop finalization, return dict assembly
- **scripts/launch-loop.py** (4333 lines) — Current infinite-loop daemon with subprocess spawning
- **scripts/session-self-loop.py** (421 lines) — In-session loop variant
- **scripts/run-loop.sh** (226 lines) — Shell entrypoint
- **https://hermes-agent.nousresearch.com/docs/guides/python-library** — Official Python library docs

---

## (1) Can we import AIAgent directly in launch-loop.py?

**Yes, absolutely.** The `run_agent` module is a normal Python module installed in the same Hermes environment. The import is straightforward:

```python
from run_agent import AIAgent

agent = AIAgent(
    model="anthropic/claude-sonnet-4.6",   # or None to use hermes config default
    quiet_mode=True,                        # suppress CLI spinners/progress
    enabled_toolsets=["terminal", "file", "delegation", "web", "skills",
                      "browser", "memory", "session_search", 
                      "code_execution", "todo", "vision"],
    disabled_toolsets=None,
    max_iterations=90,
    skip_memory=False,
    skip_context_files=False,
)

# Option A: .chat() — simple, returns just the string
response = agent.chat(prompt)

# Option B: .run_conversation() — full control, returns dict
result = agent.run_conversation(
    user_message=prompt,
    task_id=f"iter-{iteration}",
)
```

No `hermes` binary needed. No subprocess. No JSON-in/JSON-out parsing. No shell escaping issues.

---

## (2) Tradeoffs: AIAgent vs Subprocess

| Axis | `hermes chat -q` (current) | `AIAgent.chat()` / `run_conversation()` |
|---|---|---|
| **Startup cost** | Spawns a full Python process → imports everything → connects to provider. Each iteration burns 2-5s in process startup + model warmup (environment is re-loaded from scratch). | Zero process overhead. The agent is already in-memory. First call to `run_conversation()` triggers a provider request immediately. |
| **Memory** | Subprocess allocates ~200-400MB, runs, then disappears. Memory is returned to the OS. | AIAgent stays in the daemon's process memory (~200-400MB resident) for the entire daemon lifetime. More memory pressure but no GC churn from process spawning. |
| **Isolation** | ✅ **Strong**: Each subprocess is a separate OS process. If it crashes/hangs, the daemon only sees `subprocess.TimeoutExpired` or a non-zero exit. | ❌ **Weak**: A runaway tool call, memory leak, or segfault in AIAgent kills the daemon process itself. However, AIAgent handles its own errors — the conversation loop includes retries, fallbacks, error classification, and graceful degradation. |
| **Reliability: timeouts** | ✅ `subprocess.run(timeout=N)` is a hard wall-clock kill. If Hermes hangs (stuck API call, infinite tool loop), the process is SIGTERM'd. | ❌ **No process-level timeout.** AIAgent has `max_iterations` (90 by default) which limits tool-calling turns, and `task_id` for VM isolation, but there's no wall-clock timeout for a single `run_conversation()` call. You'd need a `concurrent.futures` wrapper or `signal.alarm()` to kill a stuck call. |
| **Reliability: crash** | ✅ Subprocess crash does not affect the daemon. | ❌ If AIAgent's internal provider call hangs (network partition, TCP timeout set to infinity), the daemon thread blocks forever. You need a timeout wrapper. |
| **Error handling** | Daemon must parse stdout/stderr, extract JSON from freeform text, handle missing binary, handle non-zero exit codes. ~150 lines of error-scaffold code in `launch-loop.py` (lines 2478-2595). | ✅ `run_conversation()` returns a rich dict: `{"final_response": ..., "messages": ..., "completed": bool, "failed": bool, "interrupted": bool, "api_calls": int, "input_tokens": ..., "output_tokens": ..., "estimated_cost_usd": ..., "session_id": ..., "model": ..., "provider": ...}` |
| **Output parsing** | The spawned Hermes session must print a one-line JSON summary as its LAST output. The daemon has a "robust multi-line JSON parser" (`extract_json_from_output`) that uses brace counting, filters `session_id:` lines, etc. **Fragile.** | ✅ `run_conversation()` returns clean Python dicts. `chat()` returns a plain string. No parsing needed at all. |
| **JSON Schema validation** | Daemon has explicit output schema validation + error classification. | ❌ AIAgent has no native output schema validation. You'd need to add it on top of the returned text. |
| **Multi-turn conversation state** | ❌ Each subprocess is stateless per iteration. Context must be re-built in the prompt by the daemon. | ✅ You can pass `conversation_history` from one `run_conversation()` to the next, maintaining the full context across iterations. |
| **System prompt customization** | ❌ Must inject via `ephemeral_system_prompt` or prompt text. Passing `--system` or custom context is fragile. | ✅ Pass `ephemeral_system_prompt` at construction OR `system_message` per `run_conversation()` call. |
| **Tool control granularity** | CLI: `-t terminal,file,delegation,...` (toolset level, not per-tool) | ✅ Same toolset-level control via `enabled_toolsets`/`disabled_toolsets`. |
| **Callback hooks** | ❌ No way to get progress updates mid-conversation from subprocess (except stdout parsing). | ✅ AIAgent supports: `tool_progress_callback`, `tool_start_callback`, `tool_complete_callback`, `stream_delta_callback`, `event_callback`, `status_callback`, `notice_callback`, and more. |
| **Resource cleanup** | ❌ Subprocess cleanup is implicit on exit (OS reclaims VMs, browser sessions, temp files). But the daemon has explicit `_cleanup_task_resources()`. | ✅ AIAgent's `finalize_turn` runs `_cleanup_task_resources(task_id)` after every turn, cleaning up VMs and browsers. |
| **Session persistence** | Subprocess persistence writes to session DB, but the daemon doesn't track those session IDs. | ✅ AIAgent persists every turn to the session DB automatically. Session IDs are tracked and returned. |
| **Concurrent workers** | ✅ Easy: spawn multiple subprocesses via ThreadPoolExecutor, each is isolated. | ⚠️ Each AIAgent instance is NOT thread-safe. The docs say: *"Always create a new AIAgent instance per thread or task."* You'd need one agent per worker thread. This is doable but adds memory overhead. |
| **Profile/model switching** | Easy: pass `--profile`, `--model`, `--provider` CLI flags per iteration. | ✅ Pass them in the AIAgent constructor per worker/iteration. |
| **Daemon complexity** | ~2500 lines of Python for spawning, capturing, parsing, and error-handling subprocesses. | Would reduce to ~50 lines of agent setup + iteration loop. Much less code. |
| **git / file / side-effect tracking** | Subprocess stdout can contain side-effect info (what files changed, git diff stats). The daemon currently parses and records these. | ✅ AIAgent return dict includes `messages` with full tool call/result history, token usage, model info. You can inspect `messages` for file mutations. But parsing tool results vs. extracting a summary still needs custom code. |

---

## (3) Does AIAgent handle tool execution differently than CLI?

**No — same tool dispatch.** Both `hermes chat -q` and `AIAgent.run_conversation()` go through the same internal code path:

1. Build system prompt (skills, memory, context files)
2. Call the LLM provider with tool definitions
3. Parse tool call requests
4. Execute each tool via `handle_function_call()`
5. Feed tool results back to the model
6. Repeat until done or `max_iterations`

The tool definitions, toolset selection, tool dispatch, and error handling are **identical**. The difference is only in how the agent is configured and how the result is returned.

Specifically, the CLI's `chat -q` mode creates an `AIAgent` internally, calls `run_conversation()`, and prints the response to stdout. The library version skips the CLI wrapper entirely.

---

## (4) Would this be more reliable or less?

### More reliable in these ways:

1. **No process-spawn overhead** — the subprocess approach wastes 2-5s per iteration on Python startup, import time, and environment loading. Every time `hermes` is invoked as a binary, it reloads all of Python, all of Hermes, connects to the provider again. AIAgent in-process skips all of that.

2. **No fragile JSON output parsing** — the current daemon has a ~50-line `extract_json_from_output()` function that uses brace-counting heuristics to find JSON in freeform text, plus special handling for `session_id:` noise lines, stderr interleaving, partial output truncation. This is fundamentally fragile. Any change in Hermes CLI output format breaks the daemon. AIAgent returns structured Python dicts.

3. **No `hermes` binary dependency** — the current code depends on `hermes` being on PATH and compatible. A `hermes update` that changes CLI flags or output format breaks the daemon silently. AIAgent is a stable Python API that follows semantic versioning.

4. **Richer error diagnostics** — `run_conversation()` returns `failed`, `interrupted`, `completed` booleans, token usage breakdowns, cost estimates, exit reasons, and the full message history. The subprocess approach gives you stdout string + exit code + stderr — much less diagnostic value.

5. **Built-in session persistence** — AIAgent automatically writes every turn to the session DB. The subprocess approach does this for the spawned session, but the daemon itself has no record of what happened across iterations.

6. **Cancellation is cleaner** — AIAgent supports `clear_interrupt()` and interrupt callbacks. The subprocess approach uses OS signals.

### Less reliable in these ways:

1. **No wall-clock timeout** — This is the biggest downside. `subprocess.run(timeout=7200)` gives you a hard kill guarantee. AIAgent has no built-in wall-clock timeout. A simple `time.sleep(999999)` in the model or a stuck network connection will block the daemon forever. Mitigation: wrap the call in `concurrent.futures` with a timeout:

```python
with concurrent.futures.ThreadPoolExecutor() as pool:
    future = pool.submit(agent.chat, prompt)
    try:
        response = future.result(timeout=7200)
    except concurrent.futures.TimeoutError:
        # agent is now in an unknown state — must discard it
        response = "TIMEOUT"
        agent = None  # create new agent next iteration
```

2. **No process isolation** — If AIAgent enters an infinite tool loop (the tool-calling loop is bounded by `max_iterations=90` so this is unlikely, but possible if each iteration takes forever), or if the OpenAI SDK hangs on a socket, the daemon process hangs. With subprocesses, you can SIGKILL the child.

3. **Memory accumulates** — AIAgent holds conversation history in memory. Over many iterations, this grows. You must explicitly manage `skip_memory`, `conversation_history` pruning, or create fresh agents. Subprocesses die and free memory.

4. **Thread safety** — The daemon's parallel worker mode (--workers N) creates threads that each spawn a subprocess — OS-level isolation is automatic. With AIAgent, each thread needs its own AIAgent instance, which is memory-expensive (each agent holds tool definitions, system prompt, callback objects).

### Verdict on reliability:

**For single-worker mode (--workers 1), AIAgent is strictly more reliable** — fewer moving parts, no fragile text parsing, no binary dependency, richer diagnostics.

**For multi-worker mode (--workers N), the subprocess approach is more reliable** because OS process isolation prevents any single hang from blocking all workers. You *can* work around this with per-worker AIAgent instances + timeout wrappers, but the memory overhead and complexity increase.

**The wall-clock timeout gap is the critical issue.** Without it, a permanently stuck provider request (rare but possible) blocks the daemon forever. This can be mitigated with a `concurrent.futures.TimeoutError` wrapper (~15 lines of code), but the wrapping is essential.

---

## Summary Recommendation

### For single-worker mode (default):

**Switch to AIAgent.** Replace the 150-line subprocess-spawning + JSON-parsing + error-handling block (~lines 2375-2595 of `launch-loop.py`) with:

```python
from run_agent import AIAgent
import concurrent.futures

agent = AIAgent(
    model=model or None,
    quiet_mode=True,
    enabled_toolsets=toolsets,
    max_iterations=max_turns,
    skip_memory=False,
    skip_context_files=False,
)

with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    future = pool.submit(agent.chat, prompt)
    try:
        response = future.result(timeout=session_timeout)
        # response is clean text — no JSON parsing needed
    except concurrent.futures.TimeoutError:
        response = f"TIMEOUT after {session_timeout}s"
        agent = AIAgent(...)  # old agent in unknown state, create fresh
```

### For multi-worker mode:

**Keep subprocesses** or use one AIAgent per worker thread with timeout wrappers. The isolation advantage of subprocesses is harder to replicate in-process.

### For the "in-session" loop (session-self-loop.py):

**Use AIAgent directly** — the current session-self-loop.py relies on the user writing state file JSON manually, which is fragile. Using `run_conversation()` with `conversation_history` would give the loop proper multi-turn awareness without file-based IPC.

### What you gain:

- **~150 fewer lines of fragile code** (JSON parser, error classification, output truncation, stderr capture, exit code handling)
- **No HTTP/wall-clock timeout issues with worker URL mode** (that code path is also fragile)
- **Richer diagnostics per iteration** (token counts, cost, model info, full message history)
- **No binary dependency** — works even if `hermes` CLI is misconfigured or broken

### What you lose or must add:

- **Wall-clock timeout wrapper** (essential — ~15 lines)
- **Per-worker agent instances** for parallel mode (more memory)
- **No process-level crash isolation** (mitigated by Python's exception safety + AIAgent retry logic)
