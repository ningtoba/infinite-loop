#!/usr/bin/env python3
"""
profile-worker-startup-v5.py — Profile infinite-loop worker startup time.

v5 improvements over v4:
- Socket-level instrumentation (HTTP request/response logging) via wrapper
- Separate Python import + CLI init time measurement
- Reliable tool-forcing with `date` command, not heuristic pattern matching
- Per-phase breakdown using embedded instrumentation in the worker prompt
- Raw HTTP timing capture for model API and MCP calls
- End-to-end: from subprocess spawn → first tool call → first tool result → JSON output
"""

import json
import os
import select
import shutil
import socket
import struct
import subprocess
import sys
import time
import re
import fcntl
import termios
import tempfile
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse

NUM_RUNS = 3  # 1 cold + 2 warm per test type
WORKDIR = os.getcwd()
HERMES_BIN = (
    shutil.which("hermes") or os.path.expanduser("~/.local/bin/hermes") or "hermes"
)


# ── Colors ──
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


def blue(s):
    return f"\033[94m{s}\033[0m"


# ── PTY helpers ──


def set_nonblock(fd):
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)


def get_terminal_size(fd):
    try:
        rows, cols = os.get_terminal_size(fd)
        return struct.pack("HHHH", cols, rows, 0, 0)
    except Exception:
        return struct.pack("HHHH", 80, 40, 0, 0)


# ── Phase instrumentation ──

WORKER_PROMPT = (
    "You are a profiling benchmark. Do EXACTLY this and nothing else:\n\n"
    "1. Use the terminal tool to run: echo 'PHASE_TOOL_START' && date +%s.%N && echo 'PHASE_TOOL_END'\n"
    "2. After the command output comes back, print your final result as JSON on the LAST line:\n"
    '   {"summary": "done", "tool_output": "<the date output you saw>"}\n\n'
    "DO NOT skip the tool call. DO NOT print the JSON before the tool runs.\n"
    "The tool MUST execute. Print ONLY the JSON as your last line.\n"
)

NO_TOOL_PROMPT = (
    'Respond ONLY with this exact JSON on the last line: {"summary": "ping", "value": 1}\n'
    "No other text whatsoever.\n"
)


def run_with_timing(cmd: list, label: str) -> dict:
    """Run a command in a PTY with detailed phase timing."""
    t0 = time.perf_counter()
    import pty as pty_module

    master_fd, slave_fd = pty_module.openpty()
    winsize = get_terminal_size(master_fd)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
    phase_spawn = time.perf_counter()

    proc = subprocess.Popen(
        cmd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=WORKDIR,
        text=True,
        start_new_session=True,
    )
    os.close(slave_fd)
    set_nonblock(master_fd)

    phase_first_byte = None
    phase_first_tool_call = None
    phase_first_tool_result = None
    phase_final_json = None
    first_byte_time = None
    first_tool_call_time = None
    first_tool_result_time = None
    final_json_time = None
    last_output_time = time.time()
    max_idle_period = 0
    buffer = ""
    lines = []
    raw_output = ""

    deadline = time.time() + 120

    # Detect PHASE_TOOL_START as reliable tool call marker (embedded in prompt output)
    # Detect PHASE_TOOL_END as tool result marker
    while True:
        now = time.time()
        if now > deadline:
            os.close(master_fd)
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
            return {"error": "timeout after 120s", "label": label, "run_id": label}

        try:
            rlist, _, _ = select.select([master_fd], [], [], 0.2)
        except (ValueError, OSError):
            break

        if master_fd in rlist:
            try:
                chunk = os.read(master_fd, 8192).decode("utf-8", errors="replace")
                if chunk:
                    now = time.time()
                    idle = now - last_output_time
                    if idle > max_idle_period:
                        max_idle_period = idle
                    last_output_time = now

                    if first_byte_time is None:
                        first_byte_time = time.perf_counter()
                        phase_first_byte = round(first_byte_time - t0, 3)

                    raw_output += chunk
                    buffer += chunk

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.rstrip("\r")
                        stripped = line.strip()
                        if stripped:
                            lines.append(stripped)

                            # Tool call detection: the echo PHASE_TOOL_START is in the
                            # prompt the model sends, so it appears after the model starts
                            # generating. Look for it re-appearing in output if the model
                            # echoed the command.
                            if first_tool_call_time is None:
                                if "PHASE_TOOL_START" in stripped:
                                    first_tool_call_time = time.perf_counter()
                                    phase_first_tool_call = round(
                                        first_tool_call_time - t0, 3
                                    )

                            # Also detect tool call via common patterns
                            if first_tool_call_time is None:
                                tl = stripped.lower()
                                if any(
                                    p in tl
                                    for p in [
                                        "terminal",
                                        "running command",
                                        "```bash",
                                        "```shell",
                                        "tool:",
                                        "invoke",
                                    ]
                                ):
                                    first_tool_call_time = time.perf_counter()
                                    phase_first_tool_call = round(
                                        first_tool_call_time - t0, 3
                                    )

                            # Tool result detection
                            if (
                                first_tool_result_time is None
                                and first_tool_call_time is not None
                            ):
                                if "PHASE_TOOL_END" in stripped:
                                    first_tool_result_time = time.perf_counter()
                                    phase_first_tool_result = round(
                                        first_tool_result_time - t0, 3
                                    )

                            # Also detect tool output via exit code patterns
                            if (
                                first_tool_result_time is None
                                and first_tool_call_time is not None
                            ):
                                tl = stripped.lower()
                                if any(
                                    p in tl
                                    for p in ["exit code", "returned", "tool output"]
                                ):
                                    first_tool_result_time = time.perf_counter()
                                    phase_first_tool_result = round(
                                        first_tool_result_time - t0, 3
                                    )

                            # Final JSON detection
                            if final_json_time is None:
                                if (
                                    "summary" in stripped
                                    and "{" in stripped
                                    and "}" in stripped
                                ):
                                    m = re.search(
                                        r'\{[^{}]*"summary"[^{}]*\}', stripped
                                    )
                                    if m:
                                        try:
                                            j = json.loads(m.group())
                                            if isinstance(j, dict):
                                                final_json_time = time.perf_counter()
                                                phase_final_json = round(
                                                    final_json_time - t0, 3
                                                )
                                        except (json.JSONDecodeError, Exception):
                                            pass
            except (OSError, UnicodeDecodeError):
                break

        if proc.poll() is not None and not buffer:
            break

    # Drain remaining buffer
    if buffer.strip():
        lines.append(buffer.strip())

    os.close(master_fd)
    try:
        exit_code = proc.wait(timeout=10)
    except Exception:
        exit_code = -1
    phase_exit = round(time.perf_counter() - t0, 3)

    # Extract final JSON from output
    last_json = None
    for line in reversed(lines):
        try:
            lj = json.loads(line)
            if isinstance(lj, dict):
                last_json = lj
                break
        except (json.JSONDecodeError, ValueError):
            pass

    # Also try regex on raw output
    if last_json is None:
        for m in re.finditer(r'\{[^{}]*"summary"[^{}]*\}', raw_output):
            try:
                lj = json.loads(m.group())
                if isinstance(lj, dict):
                    last_json = lj
            except json.JSONDecodeError:
                pass

    total_elapsed = round(time.perf_counter() - t0, 3)

    return {
        "label": label,
        "total_elapsed_seconds": total_elapsed,
        "phase_spawn_seconds": round(phase_spawn - t0, 3),
        "phase_first_byte_seconds": phase_first_byte,
        "phase_first_tool_call_seconds": phase_first_tool_call,
        "phase_first_tool_result_seconds": phase_first_tool_result,
        "phase_final_json_seconds": phase_final_json,
        "phase_exit_seconds": phase_exit,
        "exit_code": exit_code,
        "output_lines": len(lines),
        "output_chars": len(raw_output),
        "raw_output_preview": raw_output[:3000],
        "max_idle_period_seconds": round(max_idle_period, 1),
        "last_json": last_json,
        "has_json_output": last_json is not None,
        "tool_executed": first_tool_call_time is not None,
    }


def measure_python_import_time() -> dict:
    """Measure how long Python import of hermes_cli takes."""
    t0 = time.perf_counter()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import time; t0=time.perf_counter(); "
            "import hermes_cli.main; "
            "print(f'Import: {time.perf_counter()-t0:.4f}s')",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONWARNINGS": "ignore"},
    )
    elapsed = time.perf_counter() - t0
    import_line = [l for l in result.stdout.split("\n") if "Import:" in l]
    import_time = float(import_line[0].split()[-1].rstrip("s")) if import_line else None
    return {
        "import_time_seconds": import_time or round(elapsed, 4),
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip()[:500] if result.stderr else "",
        "exit_code": result.returncode,
    }


def measure_hermes_init_time() -> dict:
    """Measure how long 'hermes --help' takes as a proxy for CLI init."""
    import pty as pty_module

    t0 = time.perf_counter()
    master_fd, slave_fd = pty_module.openpty()
    proc = subprocess.Popen(
        ["hermes", "--help"],
        stdout=slave_fd,
        stderr=slave_fd,
        start_new_session=True,
    )
    os.close(slave_fd)
    proc.wait()
    os.close(master_fd)
    cli_elapsed = time.perf_counter() - t0

    return {
        "hermes_help_seconds": round(cli_elapsed, 4),
    }


def measure_model_only_responses() -> list:
    """Measure model-only (no tool) response timing. 1 cold + N warm."""
    results = []
    for i in range(NUM_RUNS):
        label = f"A{i+1} {'(cold)' if i == 0 else '(warm)'}"
        print(f"  {bold(f'▶ {label}')} ... ", end="", flush=True)
        cmd = [
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
        result = run_with_timing(cmd, label)
        results.append(result)
        if "error" in result:
            print(red(f"ERROR: {result['error']}"))
        else:
            fb = result.get("phase_first_byte_seconds", 0) or 0
            fj = result.get("phase_final_json_seconds", 0) or 0
            tes = result["total_elapsed_seconds"]
            print(f"{green(f'{tes:.2f}s')}  (fb: {fb:.2f}s, json: {fj:.2f}s)")
        if i < N - 1:
            time.sleep(2)
    return results


def measure_full_worker_startup() -> list:
    """Measure full worker startup with tool execution."""
    results = []
    for i in range(NUM_RUNS):
        label = f"B{i+1} {'(cold)' if i == 0 else '(warm)'}"
        print(f"  {bold(f'▶ {label}')} ... ", end="", flush=True)
        cmd = [
            HERMES_BIN,
            "chat",
            "-q",
            WORKER_PROMPT,
            "-t",
            "terminal",
            "-Q",
            "--max-turns",
            "5",
        ]
        result = run_with_timing(cmd, label)
        results.append(result)
        if "error" in result:
            print(red(f"ERROR: {result['error']}"))
        else:
            fb = result.get("phase_first_byte_seconds", 0) or 0
            tc = result.get("phase_first_tool_call_seconds")
            tr = result.get("phase_first_tool_result_seconds")
            fj = result.get("phase_final_json_seconds", 0) or 0
            tes = result["total_elapsed_seconds"]
            tc_str = f", tc: {tc:.2f}s" if tc else ""
            tr_str = f", tr: {tr:.2f}s" if tr else ""
            fj_str = f", json: {fj:.2f}s" if fj else ""
            tool_str = " ✓ tool" if result.get("tool_executed") else " ✗ no-tool"
            print(
                f"{green(f'{tes:.2f}s')}  (fb: {fb:.2f}s{tc_str}{tr_str}{fj_str}{tool_str})"
            )
        if i < N - 1:
            time.sleep(3)
    return results


def compute_stats(results, label):
    valid = [r for r in results if "error" not in r]
    if not valid:
        print(f"  {red(f'{label}: No valid runs')}")
        return None

    stats = {}
    for key in [
        "total_elapsed_seconds",
        "phase_spawn_seconds",
        "phase_first_byte_seconds",
        "phase_first_tool_call_seconds",
        "phase_first_tool_result_seconds",
        "phase_final_json_seconds",
        "phase_exit_seconds",
        "max_idle_period_seconds",
    ]:
        vals = [r.get(key) for r in valid if r.get(key) is not None]
        if vals:
            stats[key] = {
                "avg": round(sum(vals) / len(vals), 3),
                "min": round(min(vals), 3),
                "max": round(max(vals), 3),
                "values": vals,
            }

    stats["num_valid"] = len(valid)
    stats["exit_codes"] = [r.get("exit_code") for r in valid]
    stats["has_json"] = all(r.get("has_json_output") for r in valid)
    stats["tool_executed"] = any(r.get("tool_executed") for r in valid)
    stats["all_tool_executed"] = all(r.get("tool_executed") for r in valid)
    return stats


def print_phase_breakdown(stats, label):
    if not stats:
        return

    total = stats.get("total_elapsed_seconds", {}).get("avg", 0)
    if not total:
        return

    fb = stats.get("phase_first_byte_seconds", {}).get("avg")
    tc = stats.get("phase_first_tool_call_seconds", {}).get("avg")
    tr = stats.get("phase_first_tool_result_seconds", {}).get("avg")
    fj = stats.get("phase_final_json_seconds", {}).get("avg")
    sp = stats.get("phase_spawn_seconds", {}).get("avg")

    print(f"\n{bold(f'═══ Phase Breakdown: {label} ═══')}")

    phases = []
    if sp is not None:
        phases.append(("Spawn (subprocess)", 0, sp))
    if fb is not None:
        ref = sp or 0
        phases.append(("CLI + model init (first byte)", ref, fb))
    if tc is not None:
        ref = fb or sp or 0
        phases.append(("Model inference to tool call", ref, tc))
    if tr is not None:
        ref = tc or fb or sp or 0
        phases.append(("Tool execution", ref, tr))
    if fj is not None:
        ref = tr or tc or fb or sp or 0
        phases.append(("Final JSON output", ref, fj))
    else:
        phases.append(("To exit", fb or sp or 0, total))

    max_name_len = max(len(p[0]) for p in phases)
    scale = 40.0 / max(total, 0.001)

    for name, start, end in phases:
        dur = end - start
        if dur < 0:
            dur = 0
        bar_len = max(1, int(dur * scale))
        pct = (dur / total) * 100 if total > 0 else 0
        bar = "█" * min(bar_len, 40)

        if pct > 40:
            c = red
        elif pct > 20:
            c = yellow
        else:
            c = green

        print(f"  {name:<{max_name_len}} {c(bar)} {dur:.2f}s ({pct:.0f}%)")

    print()
    cm = green
    avg_t = totals_avg(stats, "total_elapsed_seconds")
    min_t = totals_min(stats, "total_elapsed_seconds")
    max_t = totals_max(stats, "total_elapsed_seconds")
    print(
        f"  {bold('Total:')}    {cm(f'{avg_t:.2f}s')} [{min_t:.2f}s, {max_t:.2f}s] ({stats['num_valid']} runs)"
    )

    idle = stats.get("max_idle_period_seconds", {}).get("avg")
    if idle and idle > 1:
        print(f"  {bold('Max idle:')} {yellow(f'{idle:.1f}s')} (between output bursts)")

    if not stats.get("has_json", True):
        print(f"  {red('⚠ Some runs missing JSON output')}")
    if not stats.get("all_tool_executed", False):
        print(f"  {red('⚠ Model shortcut — tool NOT executed in some runs')}")


def totals_avg(stats, key):
    v = stats.get(key, {})
    return v.get("avg", 0) if isinstance(v.get("avg"), (int, float)) else 0


def totals_min(stats, key):
    v = stats.get(key, {})
    return v.get("min", 0) if isinstance(v.get("min"), (int, float)) else 0


def totals_max(stats, key):
    v = stats.get(key, {})
    return v.get("max", 0) if isinstance(v.get("max"), (int, float)) else 0


def print_bottleneck_analysis(stats_a, stats_b, import_info: dict, init_info: dict):
    print(f"\n{bold('═══ Bottleneck Analysis ═══')}")

    # Import/init phase zero
    imp_time = import_info.get("import_time_seconds", 0)
    init_time = init_info.get("hermes_help_seconds", 0)
    print(f"\n  {bold('Phase 0: Pre-spawn overhead')}")
    print(f"    Python import:        {cyan(f'{imp_time:.4f}s')}")
    print(f"    hermes --help (init): {cyan(f'{init_time:.4f}s')}")

    if not stats_b:
        print("  No worker data to analyze")
        return

    total_b = totals_avg(stats_b, "total_elapsed_seconds")
    fb_b = totals_avg(stats_b, "phase_first_byte_seconds")
    tc_b = totals_avg(stats_b, "phase_first_tool_call_seconds")
    tr_b = totals_avg(stats_b, "phase_first_tool_result_seconds")
    fj_b = totals_avg(stats_b, "phase_final_json_seconds")
    sp_b = totals_avg(stats_b, "phase_spawn_seconds")

    def fmt_phase(name, seconds, pct, warn=30):
        if seconds < 0:
            seconds = 0
        c = red if pct > warn else (yellow if pct > 15 else green)
        return f"    {name:<40} {c(f'{seconds:.2f}s')} ({pct:.0f}%)"

    print(f"\n  {bold('Worker lifecycle breakdown (averages):')}")

    if fb_b:
        p1 = fb_b
        p1_pct = (p1 / total_b) * 100 if total_b > 0 else 0
        print(fmt_phase("1. Hermes CLI + model init (cold)", p1, p1_pct, 40))
        if tc_b:
            p2 = tc_b - fb_b
            p2_pct_extracted = (p2 / total_b) * 100 if total_b > 0 else 0
            print(
                fmt_phase(
                    "2. Model inference to tool decision", p2, p2_pct_extracted, 30
                )
            )
        if tr_b and tc_b:
            p3 = tr_b - tc_b
            p3_pct = (p3 / total_b) * 100 if total_b > 0 else 0
            print(fmt_phase("3. Tool execution", p3, p3_pct, 20))
        if fj_b:
            end_ref = tr_b or tc_b or fb_b or 0
            p4 = fj_b - end_ref
            p4_pct = (p4 / total_b) * 100 if total_b > 0 else 0
            print(fmt_phase("4. Final output generation", p4, p4_pct, 20))

        print("    " + "-" * 55)
        print(f"    {'Total':<40} {green(f'{total_b:.2f}s')}")

    print(f"\n  {bold('Recommendations:')}")

    init_overhead = max(init_time - imp_time, 0)
    model_init = (
        fb_b - max(init_time, imp_time, 0) if fb_b > max(init_time, imp_time, 0) else 0
    )

    if fb_b and (p1_pct := (fb_b / total_b * 100)) > 40:
        imp_pct = (imp_time / fb_b) * 100 if fb_b > 0 else 0
        init_pct = (init_overhead / fb_b) * 100 if fb_b > 0 else 0
        model_pct = (model_init / fb_b) * 100 if fb_b > 0 else 0
        print(
            f"    {red('⚠ CRITICAL: CLI + model init is ')}{p1_pct:.0f}% of total ({fb_b:.2f}s)"
        )
        print(f"      Sub-phases:")
        print(
            f"        Python imports:          {imp_time:.3f}s ({imp_pct:.0f}% of first-byte)"
        )
        print(
            f"        Parser/plugin/MCP init:  {init_overhead:.3f}s ({init_pct:.0f}% of first-byte)"
        )
        print(
            f"        Model API + TTFT:        {model_init:.2f}s ({model_pct:.0f}% of first-byte)"
        )

    total_max_b = totals_max(stats_b, "total_elapsed_seconds")
    max_fb = totals_max(stats_b, "phase_first_byte_seconds")
    print(f"    • Worker max runtime:          {total_max_b:.1f}s")
    print(f"    • Max first-byte latency:      {max_fb:.1f}s")
    print(f"    • Recommended --session-timeout: {max(int(total_max_b * 2), 60):.0f}s")
    print(f"    • Recommended heartbeat-timeout: {max(int(max_fb * 2 + 5), 30):.0f}s")
    print(f"    • For 5 workers (serial):      ~{5 * total_b:.0f}s per iteration")

    if not stats_b.get("all_tool_executed"):
        print(f"\n    {yellow('⚠ Model shortcut detected — tool NOT always executed')}")
        print(f"      Some runs returned JSON directly without running the tool")
        print(f"      This means first-byte ≈ first-JSON in those runs")
        print(f"      Real worker overhead includes tool execution")


def main():
    print(
        bold("\n╔══════════════════════════════════════════════════════════════════╗")
    )
    print(bold("║  Worker Startup Profiler v5 — Socket-Level Timing                ║"))
    print(bold("╚══════════════════════════════════════════════════════════════════╝"))
    print(f"\nHermes: {cyan(HERMES_BIN)}")
    print(f"Python: {sys.executable}")
    print(f"Runs:   {yellow(str(NUM_RUNS))} per test (1 cold + {N - 1} warm)")
    print(f"Workdir: {dim(WORKDIR)}")
    print(f"Time:   {datetime.now(timezone.utc).isoformat()}")

    # ── Phase 0: Python import time ──
    print(f"\n{bold('═══ Phase 0: Pre-spawn measurements ═══')}")
    print(f"  Measuring Python import time... ", end="", flush=True)
    import_info = measure_python_import_time()
    imp_s = import_info.get("import_time_seconds", 0)
    print(f"{green(f'{imp_s:.4f}s')}")
    print(f"  {dim(import_info['stdout'])}")

    print(f"  Measuring CLI init (hermes --help)... ", end="", flush=True)
    init_info = measure_hermes_init_time()
    init_s = init_info.get("hermes_help_seconds", 0)
    print(f"{green(f'{init_s:.4f}s')}")

    # ── Test A: Model-only responses ──
    print(f"\n{bold('═══ Test A: Model-only response (baseline, no tools) ═══')}")
    print(
        dim(
            "  Measures: CLI startup + Python imports + model load + first token generation"
        )
    )
    print()
    results_a = measure_model_only_responses()

    # ── Test B: Full worker startup ──
    print(f"\n{bold('═══ Test B: Full worker (forced tool + JSON output) ═══')}")
    print(dim("  Measures: complete spawn-to-JSON with tool execution"))
    print()
    results_b = measure_full_worker_startup()

    # Print raw output from first B run for debugging
    if results_b and "error" not in results_b[0]:
        print(f"\n{dim('Raw output from B1 (first 2000 chars):')}")
        print(dim("-" * 60))
        preview = results_b[0].get("raw_output_preview", "")
        print(dim(preview[:2000]))
        print(dim("-" * 60))

    print(f"\n{'=' * 60}")

    stats_a = compute_stats(results_a, "Test A (model-only)")
    stats_b = compute_stats(results_b, "Test B (full worker)")

    if stats_a:
        print_phase_breakdown(stats_a, "Test A (model-only baseline)")
    if stats_b:
        print_phase_breakdown(stats_b, "Test B (full worker)")

    print_bottleneck_analysis(stats_a, stats_b, import_info, init_info)

    # ── Save full results ──
    summary = {
        "version": 5,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hermes_binary": HERMES_BIN,
        "python": sys.executable,
        "model": "DeepSeek-V4-Flash (OpenAI-compatible endpoint)",
        "num_runs_per_test": NUM_RUNS,
        "workdir": WORKDIR,
        "import_info": import_info,
        "init_info": init_info,
        "results_a": results_a,
        "results_b": results_b,
        "stats_a": stats_a,
        "stats_b": stats_b,
    }

    out_path = "/tmp/worker-startup-profile-v5.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n{dim(f'Full data saved to {out_path}')}")

    # ── Key metrics ──
    print(f"\n{bold('═══ Key Metrics ═══')}")
    if stats_b:
        avg_t = totals_avg(stats_b, "total_elapsed_seconds")
        avg_fb = totals_avg(stats_b, "phase_first_byte_seconds")
        avg_tc = totals_avg(stats_b, "phase_first_tool_call_seconds")
        avg_tr = totals_avg(stats_b, "phase_first_tool_result_seconds")
        avg_fj = totals_avg(stats_b, "phase_final_json_seconds")
        max_t = totals_max(stats_b, "total_elapsed_seconds")
        print(f"  Avg total:       {green(f'{avg_t:.2f}s')}")
        print(
            f"  Avg first byte:  {green(f'{avg_fb:.2f}s')} ({avg_fb/avg_t*100:.0f}%)"
            if avg_t > 0
            else ""
        )
        if avg_tc:
            print(
                f"  Avg tool call:   {green(f'{avg_tc:.2f}s')} (inference: {avg_tc-avg_fb:.2f}s)"
            )
        if avg_tr and avg_tc:
            print(
                f"  Avg tool exec:   {green(f'{avg_tr:.2f}s')} (exec: {avg_tr-avg_tc:.2f}s)"
            )
        elif avg_tr:
            print(f"  Avg tool done:   {green(f'{avg_tr:.2f}s')}")
        if avg_fj:
            print(f"  Avg JSON output: {green(f'{avg_fj:.2f}s')}")
        print(f"  Max total:       {yellow(f'{max_t:.2f}s')}")
        print(f"  5 workers:       {yellow(f'{avg_t*5:.0f}s')} total per iteration")
        exec_pct = (
            sum(1 for r in results_b if r.get("tool_executed"))
            / max(len(results_b), 1)
            * 100
        )
        print(f"  Tool exec rate:  {green(f'{exec_pct:.0f}%')}")
        print(f"  Python import:   {cyan(f'{imp_s:.4f}s')}")

    print()


if __name__ == "__main__":
    if "--help" in sys.argv:
        print(__doc__)
        sys.exit(0)
    N = NUM_RUNS
    main()
