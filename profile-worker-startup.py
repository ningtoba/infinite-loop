#!/usr/bin/env python3
"""
profile-worker-startup.py v2 — Profile the infinite-loop worker startup time.

Measures `hermes chat -q` from invocation to first output and first tool result.
Handles models that output minimal/no stderr (DeepSeek-V4-Flash).
Uses --yolo to avoid permission blocks.
"""

import json
import os
import select
import shutil
import subprocess
import sys
import time

NUM_RUNS = 5
WORKDIR = os.getcwd()
HERMES_BIN = (
    shutil.which("hermes") or os.path.expanduser("~/.local/bin/hermes") or "hermes"
)

# The prompt asks for a simple terminal command, then JSON output.
# We use --yolo to auto-approve tool calls.
MINIMAL_PROMPT = (
    "You are a benchmarking agent. Do ONE thing:\n"
    '1. Run `python3 -c "print(42)"` via the terminal tool.\n'
    "2. Print your final result as a single JSON line:\n"
    '   {"summary": "done", "value": 42}\n'
    "No other work, no thinking aloud.\n"
)

# Prompt that avoids tool calls entirely (just model response)
NO_TOOL_PROMPT = (
    'Respond ONLY with this exact JSON: {"summary": "ping", "value": 1}\n'
    "No other text whatsoever.\n"
)


def green(s):
    return f"\033[92m{s}\033[0m"


def yellow(s):
    return f"\033[93m{s}\033[0m"


def cyan(s):
    return f"\033[96m{s}\033[0m"


def bold(s):
    return f"\033[1m{s}\033[0m"


def dim(s):
    return f"\033[2m{s}\033[0m"


def red(s):
    return f"\033[91m{s}\033[0m"


def profile_with_pty(cmd: list[str], run_id: int, label: str) -> dict:
    """Use a PTY to capture combined stdout+stderr in real-time."""
    import pty as pty_module

    t0 = time.perf_counter()

    master_fd, slave_fd = pty_module.openpty()
    spawn_time = time.perf_counter()

    proc = subprocess.Popen(
        cmd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=WORKDIR,
        text=True,
        start_new_session=True,
    )
    os.close(slave_fd)
    os.set_blocking(master_fd, False)

    first_byte_time = None
    first_json_time = None
    buffer = ""
    lines = []
    last_output_time = time.time()

    deadline = time.time() + 120  # 2 min max

    while True:
        now = time.time()
        if now > deadline:
            os.close(master_fd)
            proc.kill()
            proc.wait()
            return {"error": "timeout after 120s"}

        try:
            rlist, _, _ = select.select([master_fd], [], [], 0.5)
        except (ValueError, OSError):
            break

        if master_fd in rlist:
            try:
                chunk = os.read(master_fd, 4096).decode("utf-8", errors="replace")
                if chunk:
                    last_output_time = time.time()
                    if first_byte_time is None:
                        first_byte_time = time.perf_counter()
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.rstrip("\r")
                        if line.strip():
                            lines.append(line)
            except (OSError, UnicodeDecodeError):
                break

        if proc.poll() is not None and not buffer:
            break

    # Drain remaining buffer
    if buffer.strip():
        lines.append(buffer.strip())

    os.close(master_fd)
    exit_code = proc.wait()
    total_time = time.perf_counter()

    full_output = "\n".join(lines)

    # Find the JSON summary in the output
    last_json = None
    import re

    for line in reversed(lines):
        line_s = line.strip()
        if line_s:
            m = re.search(r'\{[^{}]*"summary"[^{}]*\}', line_s)
            if m:
                try:
                    last_json = json.loads(m.group())
                except json.JSONDecodeError:
                    pass
            if last_json is None:
                try:
                    lj = json.loads(line_s)
                    if isinstance(lj, dict):
                        last_json = lj
                except json.JSONDecodeError:
                    pass

    # Detect tool calls in output lines
    first_tool_call_index = None
    for i, line in enumerate(lines):
        tl = line.lower()
        if any(
            p in tl
            for p in [
                "terminal",
                "python3",
                "print(42)",
                "tool call",
                "calling",
                "running",
                "command:",
                "```bash",
                "```shell",
                "running command",
            ]
        ):
            if first_tool_call_index is None:
                first_tool_call_index = i

    return {
        "run_id": run_id,
        "label": label,
        "total_elapsed_seconds": round(total_time - t0, 3),
        "phase_spawn_seconds": round(spawn_time - t0, 3),
        "phase_first_byte_seconds": (
            round(first_byte_time - t0, 3) if first_byte_time else None
        ),
        "phase_first_tool_call_index": first_tool_call_index,
        "exit_code": exit_code,
        "output_lines": len(lines),
        "output_chars": len(full_output),
        "last_json": last_json,
    }


def main():
    print(bold("\n╔══════════════════════════════════════════════════════════════╗"))
    print(bold("║  Worker Startup Profiler v2                                ║"))
    print(bold("╚══════════════════════════════════════════════════════════════╝"))
    print(f"\nHermes: {cyan(HERMES_BIN)}")
    print(f"Runs:   {yellow(str(NUM_RUNS))}")
    print(f"Model:  {dim('DeepSeek-V4-Flash (via OpenAI-compatible endpoint)')}")
    print()

    # ── Test A: Model-only response (no tool calls) ──
    print(bold("═══ Test A: Model-only response (no tools) ═══"))
    print(
        dim(
            "  Measures: hermes CLI startup + Python imports + model load + first token"
        )
    )
    print()

    results_a = []
    base_cmd_no_tool = [
        HERMES_BIN,
        "chat",
        "-q",
        NO_TOOL_PROMPT,
        "-t",
        "terminal",
        "-Q",
        "--max-turns",
        "3",
    ]
    for i in range(NUM_RUNS):
        label = f"A{i+1} {'(cold)' if i == 0 else '(warm)'}"
        print(f"  {bold(f'▶ {label}')} ... ", end="", flush=True)
        result = profile_with_pty(base_cmd_no_tool, i + 1, label)
        results_a.append(result)
        if "error" in result:
            print(red(f"ERROR: {result['error']}"))
        else:
            fb = result.get("phase_first_byte_seconds", 0)
            tes = result["total_elapsed_seconds"]
            print(f"{green(f'{tes:.2f}s')}  (first byte: {fb:.2f}s)")

    # ── Test B: Full worker (with --yolo for tool approval) ──
    print()
    print(bold("═══ Test B: Full worker (with --yolo, terminal tool) ═══"))
    print(dim("  Measures: complete spawn-to-JSON cycle with tool execution"))
    print()

    results_b = []
    base_cmd_full = [
        HERMES_BIN,
        "chat",
        "-q",
        MINIMAL_PROMPT,
        "-t",
        "terminal",
        "-Q",
        "--max-turns",
        "5",
        "--yolo",
    ]
    for i in range(NUM_RUNS):
        label = f"B{i+1} {'(cold)' if i == 0 else '(warm)'}"
        print(f"  {bold(f'▶ {label}')} ... ", end="", flush=True)
        result = profile_with_pty(base_cmd_full, i + 1, label)
        results_b.append(result)
        if "error" in result:
            print(red(f"ERROR: {result['error']}"))
        else:
            fb = result.get("phase_first_byte_seconds", 0)
            tes = result["total_elapsed_seconds"]
            print(f"{green(f'{tes:.2f}s')}  (first byte: {fb:.2f}s)")

    # ── Compute statistics ──
    def stats(results, label):
        totals = [r["total_elapsed_seconds"] for r in results if "error" not in r]
        first_bytes = [
            r.get("phase_first_byte_seconds")
            for r in results
            if r.get("phase_first_byte_seconds") is not None
        ]
        if not totals:
            print(f"\n{red(f'{label}: No valid runs')}")
            return

        avg_t = sum(totals) / len(totals)
        min_t = min(totals)
        max_t = max(totals)
        avg_fb = sum(first_bytes) / len(first_bytes) if first_bytes else None

        print(f"\n{bold(f'─── {label} Statistics ───')}")
        print(
            f"  Total elapsed:    {green(f'{avg_t:.2f}s')}  [{min_t:.2f}s, {max_t:.2f}s]"
        )
        if avg_fb:
            print(f"  First byte:       {green(f'{avg_fb:.2f}s')}")
            print(
                f"  After first byte: {yellow(f'{avg_t - avg_fb:.2f}s')}  (model inference + tool execution)"
            )
            print(
                f"  hermes overhead:  {dim(f'{avg_fb:.2f}s')}  (imports, config, model load)"
            )

    stats(results_a, "Test A (model-only)")
    stats(results_b, "Test B (full worker)")

    # ── Bottleneck analysis ──
    print(f"\n{bold('─── Bottleneck Analysis ───')}")
    fb_all = [
        r.get("phase_first_byte_seconds")
        for r in results_a + results_b
        if r.get("phase_first_byte_seconds") is not None
    ]
    if fb_all:
        avg_fb = sum(fb_all) / len(fb_all)
        print(f"\n  Average time to first output byte: {green(f'{avg_fb:.2f}s')}")
        if avg_fb < 3:
            print(f"  {green('✓ Very fast startup (< 3s)')}")
            print(f"    Model load + Python init is not a bottleneck")
        elif avg_fb < 8:
            print(f"  {yellow('⚠ Moderate startup (3-8s)')}")
            print(f"    Model load is ~{avg_fb:.1f}s of startup time")
            print(f"    This is normal for DeepSeek-V4-Flash via OpenAI API")
            print(
                f"    Mitigation: consider --session-timeout to avoid premature timeout"
            )
        elif avg_fb < 15:
            print(f"  {red('✗ Slow startup (8-15s)')}")
            print(f"    Model load dominates startup time")
            print(f"    Mitigation: keep GPU warm, use keepalive")
        else:
            print(f"  {red('✗ Very slow startup (>15s) - critical bottleneck')}")

    totals_b = [r["total_elapsed_seconds"] for r in results_b if "error" not in r]
    if totals_b:
        avg_b = sum(totals_b) / len(totals_b)
        fb_b = [
            r.get("phase_first_byte_seconds")
            for r in results_b
            if r.get("phase_first_byte_seconds") is not None
        ]
        avg_fb_b = sum(fb_b) / len(fb_b) if fb_b else 0
        post_fb = avg_b - avg_fb_b
        total_overhead = avg_fb_b  # time before model starts responding

        print(f"\n  Full worker lifecycle breakdown:")
        print(
            f"    hermes startup + model load:    {green(f'{avg_fb_b:.2f}s')} ({avg_fb_b/avg_b*100:.0f}%)"
        )
        print(
            f"    model inference + tool exec:     {yellow(f'{post_fb:.2f}s')} ({post_fb/avg_b*100:.0f}%)"
        )
        print(f"    total:                           {bold(f'{avg_b:.2f}s')}")

        print(f"\n  Recommendations:")
        if avg_fb_b > 5:
            print(
                f"    • First-output latency ({avg_fb_b:.1f}s) is the main bottleneck"
            )
            print(f"    • This is dominated by model cold-start + API call overhead")
            print(
                f"    • DeepSeek-V4-Flash via OpenAI-compatible API requires ~{avg_fb_b:.0f}s per call"
            )
        print(f"    • RETRY and SESSION-TIMEOUT must be > {max(totals_b):.0f}s")
        print(
            f"    • For --session-timeout, set to at least {max(totals_b)*3:.0f}s for safe margin"
        )
        print(
            f"    • If using heartbeat-timeout, set > {avg_fb_b*2:.0f}s (startup silence is normal)"
        )

    # ── Save full results ──
    summary = {
        "version": 2,
        "hermes_binary": HERMES_BIN,
        "model": "DeepSeek-V4-Flash (OpenAI-compatible endpoint)",
        "num_runs": NUM_RUNS,
        "results_a": results_a,
        "results_b": results_b,
        "analysis": {
            "avg_first_byte_a": round(
                sum(
                    r.get("phase_first_byte_seconds", 0)
                    for r in results_a
                    if r.get("phase_first_byte_seconds")
                )
                / max(
                    len([r for r in results_a if r.get("phase_first_byte_seconds")]), 1
                ),
                3,
            ),
            "avg_total_a": round(
                sum(r["total_elapsed_seconds"] for r in results_a if "error" not in r)
                / max(len([r for r in results_a if "error" not in r]), 1),
                3,
            ),
            "avg_first_byte_b": round(
                sum(
                    r.get("phase_first_byte_seconds", 0)
                    for r in results_b
                    if r.get("phase_first_byte_seconds")
                )
                / max(
                    len([r for r in results_b if r.get("phase_first_byte_seconds")]), 1
                ),
                3,
            ),
            "avg_total_b": round(
                sum(r["total_elapsed_seconds"] for r in results_b if "error" not in r)
                / max(len([r for r in results_b if "error" not in r]), 1),
                3,
            ),
        },
    }

    out_path = "/tmp/worker-startup-profile-v2.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n{dim(f'Full data saved to {out_path}')}")


if __name__ == "__main__":
    main()
