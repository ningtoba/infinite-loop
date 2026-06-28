# Worker Startup Profiling Report — v5 (Iteration #26)

**Date:** 2026-06-28
**Hermes:** v0.17.0
**Model:** DeepSeek-V4-Flash (OpenAI-compatible, local vLLM at 192.168.1.10:8000)
**Profiler:** `profile-worker-startup-v5.py` (new, improved over v4)

## Methodology

Three tests, each 3 runs (1 cold + 2 warm):

1. **Phase 0 (pre-spawn):** Time `hermes --help` to measure CLI bootstrap overhead (Python imports, parser building, plugin/MCP discovery)
2. **Test A (model-only):** `hermes chat -q "respond with JSON only" -t terminal -Q --max-turns 3`
3. **Test B (full worker):** `hermes chat -q "execute terminal tool and return JSON" -t terminal -Q --max-turns 5`

Timing via PTY-based real-time output capture with phase-boundary markers.

## Results

### Phase 0: Pre-spawn Overhead

| Metric | Time |
|--------|------|
| hermes --help (CLI init) | 0.225s |
| Subprocess spawn | ~0.001s (negligible) |

### Test A: Model-Only (no tools)

| Metric | Cold | Warm-1 | Warm-2 | Average |
|--------|------|--------|--------|--------|
| First byte | 4.512s | 4.184s | 4.292s | **4.329s** |
| Total elapsed | 6.964s | 6.639s | 6.703s | **6.769s** |
| Post-first-byte | 2.452s | 2.455s | 2.411s | **2.439s** |

### Test B: Full Worker (with tool)

| Metric | Cold (B1) | Warm (B2) | Warm (B3) | Average |
|--------|-----------|-----------|-----------|---------|
| First byte | 5.557s | 4.970s | 4.961s | **5.163s** |
| Tool call detection | 5.557s | N/A | N/A | 5.557s |
| Total elapsed | 9.382s | 9.012s | 8.931s | **9.108s** |
| Max idle period | 5.6s | 5.0s | 5.0s | **5.2s** |
| Tool executed? | ✓ YES | ✗ shortcut | ✗ shortcut | 33% |

**⚠ Key finding: Model shortcut on warm runs.** Only the cold run (B1) actually executed the terminal tool. On B2 and B3, the model returned JSON directly with fake tool output (`1782639026.098516287` was fabricated by the model, not from `date +%s.%N`).

## Bottleneck Breakdown (Cold Worker, B1)

```
Phase                          Duration    % of Total
─────────────────────────────────────────────────────
1. Python imports              0.024s      0.3%
2. Parser/plugin/MCP init      0.201s      2.1%
3. Model API + TTFT            5.332s     56.8%  ← DOMINANT
4. Model inference + tool      3.825s     40.8%
─────────────────────────────────────────────────────
   Total                       9.382s     100%
```

### Sub-Phases of First-Byte Latency (5.557s)

| Component | Time | % of First-Byte |
|-----------|------|-----------------|
| Python imports | 0.024s | 0.4% |
| Parser/plugin/MCP init | 0.200s | 3.6% |
| **Model API connection + TTFT** | **5.333s** | **96.0%** |

## Comparison with v4 (Iteration #25)

The v4 report used socket-level instrumentation and measured:
- Phase 2 (Hermes CLI init): 0.93s vs v5's 0.225s — the v4 number included some overlap with OSV/malware checks
- Phase 3 (OSV checks): 1.0s — not measurable via PTY since they're async
- Phase 4 (Hindsight init): 2.4s — not measurable via PTY since it's part of the model init wait

**v5 shows a cleaner picture**: the CLI init overhead is actually only ~0.225s, and the ~5.3s first-byte wait is dominated by the model API round-trip (TTFT). OSV and Hindsight init happen in parallel during the model API wait.

## Key Insights

1. **The trivial bottleneck is the model API roundtrip, not Python/CLI startup.** 96% of first-byte latency is model TTFT.
2. **CLI init is fast** — 225ms for parser building + plugin discovery + MCP config scan + OSV checks is well-optimized.
3. **Model shortcut is endemic** — only 1/3 runs actually executed the tool. The model learns from the prompt pattern and returns fabricated JSON on subsequent runs.
4. **Cold vs warm first-byte delta**: 0.5-0.6s (5.56s cold vs ~4.97s warm) — the model API has a small cold-start penalty but it's modest.
5. **Post-first-byte time is ~3.8s** — this is the model inference + tool execution + completion. For the cold run this was real, for warm runs the model shortcut makes it ~4.0s of "post-first-byte" that's just model generating output text.

## Bottleneck Visualization

```
time →  
├─ 0.00s  Process spawn
├─ 0.23s  CLI init done (Python + parser + plugins + MCP)
│         ┌─────────────────────────────────┐
│         │ Model API call (no output yet)  │ ← 96% of first-byte
│         │ Connection setup, prompt send,  │
│         │ TTFT wait (4.9-5.3s)           │
├─ 5.56s  └─────────────────────────────────┘
│         ┌─────────────────────────────────┐
│         │ Model inference + tool exec     │ ← post-first-byte (3.8s)
│         │ Generates tool call, terminal   │
│         │ executes, model reads result,   │
│         │ produces final JSON             │
├─ 9.38s  └─────────────────────────────────┘
```

## Recommended Timeouts

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| --session-timeout | 60s | 6x average, allows for occasional slow model responses |
| --heartbeat-timeout | 30s | 5x first-byte; MUST account for ~5.5s startup silence |
| 5 workers (serial) | ~47s | Total iteration wall time, no parallelism |

## Raw Data Location

- Full JSON: `/tmp/worker-startup-profile-v5.json`
- Profiler script: `/home/nekophobia/Projects/hermes-loop/profile-worker-startup-v5.py`

## Next Steps

1. ✅ **Add `--no-tool-shortcut`** to spawned worker sessions to force real tool execution (Done — Iteration #27)
2. **Model-level optimization**: The 5.3s model TTFT is the true bottleneck; consider a faster model for iteration tasks or keepalive pings
3. **Validate with real worker prompts** (not just benchmark prompts) to see if tool shortcut persists with complex goals
