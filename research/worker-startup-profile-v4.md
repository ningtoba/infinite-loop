# Worker Startup Profiling Report — Iteration #25

## Summary

Measured `hermes chat -q` startup latency from subprocess spawn to first model
output byte. Ran 5 warm runs each for model-only and full-worker configurations.

## Key Metrics

| Metric | Model-Only | Full Worker |
|--------|-----------|-------------|
| Avg time to first byte | 4.25s | 4.91s |
| Avg total elapsed | 6.63s | 8.92s |
| Avg post-first-byte | 2.38s | 4.00s |
| Max total | 6.74s | 8.97s |
| Tool exec rate | N/A | 0% (model shortcut) |

## Bottleneck Breakdown (from socket-level instrumentation)

### Phase 1: Python imports (0.14s, 2%)
Import `hermes_cli.main` + transitive dependencies. Fast — no issue.

### Phase 2: Hermes CLI init (0.93s, 16%)
- Building 100+ subcommand parsers (parser tree for every command)
- Plugin discovery and loading (11 evey-* plugins)
- MCP server config scanning (18 servers)
- OSV malware check preparation

### Phase 3: OSV malware checks (1.0s, 17%)
16 concurrent HTTPS queries to `https://api.osv.dev/v1/query` (→ ghs.googlehosted.com).
Runs at t=1.07s, completes ~t=2.0s.
*17 connections = 1 per MCP server using npx/uvx.*

### Phase 4: Hindsight init (2.4s, 28%)
HTTP request to `http://localhost:8888/version`.
Runs around t=3.5-4.1s during session initialization.
*This is the single largest tool-level bottleneck.*

### Phase 5: Model API call (0.15s, 2%)
Local vLLM endpoint at 192.168.1.10:8000 responds in ~15ms.
Hermes overhead + prompt processing adds ~135ms.

### Phase 6: Post-first-byte cleanup (3.9s, 44%)
PTY output processing, stderr buffering, process teardown.

## Root Causes

1. **OSV check runs on every chat startup** — queries api.osv.dev for every
   npx/uvx MCP server in config, even though most servers aren't being started.
   Fail-open but still adds latency.

2. **Hindsight memory provider init is slow** — localhost:8888/version takes
   2.4s even on local Docker. This is the biggest single-payer bottleneck.

3. **Parser building is not lazy** — 100+ subcommand parsers built on every
   `chat -q` invocation. Argparse building for commands that will never be
   used is pure overhead.

4. **Model shortcut** — DeepSeek-V4-Flash returns JSON directly without
   executing the tool call when it sees the template in the prompt.
   Real worker startup would include tool execution overhead.

## Recommendations

1. **For immediate worker startup optimization:**
   - Set --session-timeout >= 60s to accommodate 5-9s startup
   - Set heartbeat-timeout >= 30s (first byte silence is normal)
   - Plan ~45s for 5 concurrent workers per iteration

2. **For Hermes startup speed improvement:**
   - Defer OSV checks to actual MCP server start time (not discovery)
   - Cache OSV results for 30-60 minutes
   - Use lazy parser building in main() for chat-only invocations
   - Warm Hindsight connection or check status faster

3. **For the loop daemon specifically:**
   - Consider worker keepalive/pooling to avoid cold start per iteration
   - The actual work time per worker is typically much longer than startup
   - Startup overhead is ~9s on ~600s+ total worker runtime = ~1.5%

## Files

- Profiler script: `/home/nekophobia/Projects/hermes-loop/profile-worker-startup.py` (v4)
- Raw data: `/tmp/worker-startup-profile-v4.json`
