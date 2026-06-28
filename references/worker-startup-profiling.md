# Worker Startup Profiling Report

**Date:** 2026-06-28
**Hermes version:** v0.17.0
**Model:** DeepSeek-V4-Flash (OpenAI-compatible endpoint)
**Provider:** Custom OpenAI-compatible

## Methodology

Measured the `hermes chat -q` subprocess lifecycle using PTY-based
real-time output capture. Two test scenarios:

- **Test A:** Model-only response (no tools) — measures CLI startup +
  Python imports + model load + first token generation
- **Test B:** Full worker with `--yolo` — measures complete
  spawn-to-JSON cycle including terminal tool execution

Each test ran 5 times (1 cold + 4 warm).

## Results

### Test A: Model-only response

| Metric | Average | Min | Max |
|--------|---------|-----|-----|
| Total elapsed | 6.91s | 6.74s | 7.03s |
| First byte latency | 4.39s | 4.31s | 4.56s |

### Test B: Full worker (with tool execution)

| Metric | Average | Min | Max |
|--------|---------|-----|-----|
| Total elapsed | 8.18s | 7.23s | 9.06s |
| First byte latency | 5.03s | 4.40s | 5.70s |

## Per-Phase Breakdown

```
Phase                          Duration    % of Total
─────────────────────────────────────────────────────
1. Daemon overhead (pre-spawn)    ~10ms       0.1%
2. Hermes CLI startup            236ms       2.9%
   (imports, config, tool reg)
3. Model cold-start + API call   ~4.79s     58.6%
   (connection, load, TTFT)
4. Model inference + tool exec   ~3.14s     38.4%
   (prompt processing, generation)
─────────────────────────────────────────────────────
   Total                         ~8.18s      100%
```

## Bottleneck Analysis

### P0 (Critical): Model cold-start + API call — ~4.8s (59%)

The dominant bottleneck is the time from `hermes chat -q` subprocess
launch to the first byte of model output. This includes:

- OpenAI-compatible API connection setup
- Provider routing & model loading
- First token generation (TTFT)

For DeepSeek-V4-Flash via an OpenAI-compatible endpoint, this is
inherent to the model/provider pairing. Cold start cannot be
eliminated without changing the provider or model.

### P1 (Significant): Model inference + tool execution — ~3.1s (38%)

The second-biggest phase. After the first byte arrives, the model:
1. Processes the full prompt (context, instructions, prior iterations)
2. Generates a tool call (terminal)
3. The tool executes (python3 -c "print(42)")
4. Output is returned

For simple tasks this is fast. For complex goals with large context,
this grows proportionally with context size.

### P2 (Minor): Hermes CLI startup — 236ms (3%)

Pure Python overhead: imports, config file loading, tool registration.
Negligible compared to model time.

## Actionable Recommendations

### 1. Session timeout configuration (immediate)

```
--session-timeout 30    # 3x average worker time
--heartbeat-timeout 12  # > 2x first-byte latency
```

Heartbeat-timeout must account for startup silence (~5s where no
output is produced while the model loads).

### 2. Model-level improvements (medium-term)

- **Keepalive**: Send periodic ping requests to keep the model warm.
  Reduces cold-start penalty from ~4.8s to ~1s on subsequent calls.
- **Streaming**: Use a streaming-enabled endpoint for faster TTFT
  (time-to-first-token).
- **Faster fallback model**: For simple iterations (e.g. "run tests"),
  use a faster/smaller model like DeepSeek-V4-Lite or GPT-4o-mini.

### 3. Daemon-level optimizations (long-term, low ROI)

Current daemon-side overhead is ~10ms — not worth optimizing.
Potential approaches:
- **Pooled subprocess workers**: Keep a pool of `hermes chat -q`
  processes alive between iterations (complex, state management risk).
- **Pre-built prompt cache**: Compute the prompt once and reuse
  (most prompt is static).
- **AIAgent library mode**: Skip subprocess entirely, use
  `AIAgent.run_conversation()` in-process (already supported via
  `--use-library`).

### 4. Observability improvements

- Log first-byte time in iteration records
- Track per-phase timing in dashboard metrics
- Alert on abnormally slow startup (> 15s)

## Raw Data

Full results saved to `/tmp/worker-startup-profile-v2.json`.
Benchmark script at `profile-worker-startup.py` in the project root.
