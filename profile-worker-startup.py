#!/usr/bin/env python3
"""
profile-worker-startup.py v4 — Profile the infinite-loop worker startup time.

v4: Fixes the tool call by using a prompt that FORCES tool use,
and captures raw PTY output for analysis.
"""

import json
import os
import select
import shutil
import struct
import subprocess
import sys
import time
import re
import fcntl
import termios

NUM_RUNS = 5
WORKDIR = os.getcwd()
HERMES_BIN = (
    shutil.which("hermes") or os.path.expanduser("~/.local/bin/hermes") or "hermes"
)

# The working model prompt — DeepSeek-V4-Flash with this toolset + yolo
# Uses a minimal goal that FORCES a tool call by asking for filesystem state
WORKER_PROMPT = (
    "You are a profiling benchmark. Do EXACTLY this and nothing else:\n\n"
    "1. Use the terminal tool to run: ls -la /tmp | head -3\n"
    "2. After the command output comes back, print your final result:\n"
    '   {"summary": "done", "files_seen": "<the first filename you saw>"}\n\n'
    "DO NOT skip the tool call. DO NOT print the JSON before the tool runs.\n"
    "The tool MUST execute. Print ONLY the JSON as your last line.\n"
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


def blue(s):
    return f"\033[94m{s}\033[0m"


def set_nonblock(fd):
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)


def get_terminal_size(fd):
    try:
        return struct.pack("HHHH", 80, 40, 0, 0)
    except Exception:
        return struct.pack("HHHH", 80, 40, 0, 0)


def profile_worker_startup(run_id: int, label: str) -> dict:
    """Profile a single worker startup with PTY capture and phase analysis."""
    import pty as pty_module

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
        "--yolo",
    ]

    t0 = time.perf_counter()
    master_fd, slave_fd = pty_module.openpty()
    winsize = get_terminal_size(master_fd)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
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

    # Tool call patterns — very broad to catch all model output styles
    TOOL_CALL_PATTERNS = [
        "terminal",
        "calling tool",
        "tool_call",
        "running command",
        "running:",
        "```bash",
        "```shell",
        "ls -la",
        "command:",
        "tool:",
        "use tool",
        "executing",
        "invoke",
    ]
    TOOL_RESULT_PATTERNS = [
        "total",
        "drwx",
        "-rw-",
        "srwx",
        "tmp/",
        ".",
        "..",
        ".X",
        "output:",
        "result:",
        "exit code",
        "returned",
        "stdout",
    ]

    while True:
        now = time.time()
        if now > deadline:
            os.close(master_fd)
            proc.kill()
            proc.wait()
            return {"error": "timeout after 120s", "run_id": run_id, "label": label}

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

                    # Process complete lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.rstrip("\r")
                        stripped = line.strip()
                        if stripped:
                            lines.append(stripped)
                            tl = stripped.lower()

                            # Tool call detection
                            if first_tool_call_time is None:
                                is_tool_call = any(p in tl for p in TOOL_CALL_PATTERNS)
                                if is_tool_call:
                                    first_tool_call_time = time.perf_counter()
                                    phase_first_tool_call = round(
                                        first_tool_call_time - t0, 3
                                    )

                            # Tool result detection
                            if (
                                first_tool_result_time is None
                                and first_tool_call_time is not None
                            ):
                                is_tool_result = any(
                                    p in tl for p in TOOL_RESULT_PATTERNS
                                )
                                if is_tool_result:
                                    first_tool_result_time = time.perf_counter()
                                    phase_first_tool_result = round(
                                        first_tool_result_time - t0, 3
                                    )

                            # JSON output detection
                            if final_json_time is None:
                                if "summary" in stripped and (
                                    "{" in stripped and "}" in stripped
                                ):
                                    # Try to extract JSON
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
    exit_code = proc.wait()
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

    # Count tool-indicative lines
    tool_line_count = sum(
        1 for l in lines if any(p in l.lower() for p in TOOL_CALL_PATTERNS)
    )

    return {
        "run_id": run_id,
        "label": label,
        "total_elapsed_seconds": total_elapsed,
        "phase_spawn_seconds": round(spawn_time - t0, 3),
        "phase_first_byte_seconds": phase_first_byte,
        "phase_first_tool_call_seconds": phase_first_tool_call,
        "phase_first_tool_result_seconds": phase_first_tool_result,
        "phase_final_json_seconds": phase_final_json,
        "phase_exit_seconds": phase_exit,
        "exit_code": exit_code,
        "output_lines": len(lines),
        "output_chars": len(raw_output),
        "raw_output_preview": raw_output[:3000],
        "tool_call_lines": tool_line_count,
        "max_idle_period_seconds": round(max_idle_period, 1),
        "last_json": last_json,
        "has_json_output": last_json is not None,
        "tool_executed": first_tool_call_time is not None,
    }


def profile_model_only(run_id: int, label: str) -> dict:
    """Profile a model-only response (no tool calls)."""
    NO_TOOL_PROMPT = (
        'Respond ONLY with this exact JSON: {"summary": "ping", "value": 1}\n'
        "No other text whatsoever.\n"
    )

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
    set_nonblock(master_fd)

    phase_first_byte = None
    phase_final_json = None
    first_byte_time = None
    final_json_time = None
    buffer = ""
    lines = []
    raw_output = ""
    last_output_time = time.time()
    max_idle_period = 0

    deadline = time.time() + 120

    while True:
        now = time.time()
        if now > deadline:
            os.close(master_fd)
            proc.kill()
            proc.wait()
            return {"error": "timeout after 120s", "run_id": run_id, "label": label}

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
                        if line.strip():
                            lines.append(line.strip())
                            if final_json_time is None:
                                if "summary" in line and "{" in line and "}" in line:
                                    m = re.search(r'\{[^{}]*"summary"[^{}]*\}', line)
                                    if m:
                                        try:
                                            j = json.loads(m.group())
                                            if isinstance(j, dict):
                                                final_json_time = time.perf_counter()
                                                phase_final_json = round(
                                                    final_json_time - t0, 3
                                                )
                                        except json.JSONDecodeError:
                                            pass
            except (OSError, UnicodeDecodeError):
                break

        if proc.poll() is not None and not buffer:
            break

    if buffer.strip():
        lines.append(buffer.strip())

    os.close(master_fd)
    exit_code = proc.wait()

    last_json = None
    for line in reversed(lines):
        try:
            lj = json.loads(line)
            if isinstance(lj, dict):
                last_json = lj
                break
        except json.JSONDecodeError:
            pass

    return {
        "run_id": run_id,
        "label": label,
        "total_elapsed_seconds": round(time.perf_counter() - t0, 3),
        "phase_spawn_seconds": round(spawn_time - t0, 3),
        "phase_first_byte_seconds": phase_first_byte,
        "phase_final_json_seconds": phase_final_json,
        "phase_exit_seconds": round(time.perf_counter() - t0, 3),
        "exit_code": exit_code,
        "output_lines": len(lines),
        "output_chars": len(raw_output),
        "max_idle_period_seconds": round(max_idle_period, 1),
        "last_json": last_json,
        "has_json_output": last_json is not None,
    }


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
        phases.append(("First byte from model", sp or 0, fb))
    if tc is not None:
        phases.append(("To first tool call", fb or sp or 0, tc))
    if tr is not None:
        phases.append(("Tool execution", tc or fb or sp or 0, tr))
    if fj is not None:
        end_ref = tr or tc or fb or sp or 0
        phases.append(("To JSON output", end_ref, fj))
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
            color = red
        elif pct > 20:
            color = yellow
        else:
            color = green

        print(f"  {name:<{max_name_len}} {color(bar)} {dur:.2f}s ({pct:.0f}%)")

    print()
    totals = stats.get("total_elapsed_seconds", {})
    avg_t = totals.get("avg", 0) if isinstance(totals.get("avg"), (int, float)) else 0
    min_t = totals.get("min", 0) if isinstance(totals.get("min"), (int, float)) else 0
    max_t = totals.get("max", 0) if isinstance(totals.get("max"), (int, float)) else 0
    print(
        f"  {bold('Total:')}    {green(f'{avg_t:.2f}s')} "
        f"[{min_t:.2f}s, {max_t:.2f}s] "
        f"({stats['num_valid']} runs)"
    )

    idle = stats.get("max_idle_period_seconds", {}).get("avg")
    if idle and idle > 1:
        print(f"  {bold('Max idle:')} {yellow(f'{idle:.1f}s')} (between output bursts)")

    if not stats.get("has_json", True):
        print(f"  {red('⚠ Some runs missing JSON output')}")

    if not stats.get("tool_executed"):
        print(f"  {red('⚠ Model shortcut detected — NO tool was executed')}")
        print(f"  {red('  The model returned JSON directly without running the tool')}")


def print_bottleneck_analysis(stats_a, stats_b):
    print(f"\n{bold('═══ Bottleneck Analysis ═══')}")

    if not stats_b:
        print("  No worker data to analyze")
        return

    total_b = stats_b.get("total_elapsed_seconds", {}).get("avg", 0)
    fb_b = stats_b.get("phase_first_byte_seconds", {}).get("avg")
    tc_b = stats_b.get("phase_first_tool_call_seconds", {}).get("avg")
    tr_b = stats_b.get("phase_first_tool_result_seconds", {}).get("avg")
    fj_b = stats_b.get("phase_final_json_seconds", {}).get("avg")

    print(f"\n  {bold('Worker lifecycle breakdown (averages):')}")

    if fb_b:
        p1 = fb_b
        p1_pct = (p1 / total_b) * 100 if total_b > 0 else 0

        def fmt_phase(name, seconds, pct, warn=30):
            if seconds < 0:
                seconds = 0
            c = red if pct > warn else (yellow if pct > 15 else green)
            return f"    {name:<40} {c(f'{seconds:.2f}s')} ({pct:.0f}%)"

        print(fmt_phase("1. Hermes CLI + model init (cold)", p1, p1_pct, 40))
        if tc_b:
            p2 = tc_b - fb_b
            p2_pct = (p2 / total_b) * 100
            print(fmt_phase("2. Model inference to tool decision", p2, p2_pct, 30))
        if tr_b and tc_b:
            p3 = tr_b - tc_b
            p3_pct = (p3 / total_b) * 100
            print(fmt_phase("3. Tool execution", p3, p3_pct, 20))
        if fj_b:
            end_ref = tr_b or tc_b or fb_b or 0
            p4 = fj_b - end_ref
            p4_pct = (p4 / total_b) * 100
            print(fmt_phase("4. Final output generation", p4, p4_pct, 20))

        print("    " + "-" * 55)
        print(f"    {'Total':<40} {green(f'{total_b:.2f}s')}")

    print(f"\n  {bold('Recommendations:')}")

    if fb_b and (p1_pct := (fb_b / total_b * 100)) > 50:
        print(f"    {red('⚠ CRITICAL')}: CLI + model init is {p1_pct:.0f}% of total")
        print(f"      Time to first byte: {fb_b:.2f}s")
        print(f"      Dominated by:")
        print(f"        • Python import overhead (hermes CLI bootstrap)")
        print(f"        • Config file parsing (hermes.yaml)")
        print(f"        • Provider connection setup (URL, auth headers)")
        print(f"        • Network round-trip to model API")
    elif fb_b:
        p1_pct = fb_b / total_b * 100
        if p1_pct > 30:
            print(f"    {yellow('⚠ SIGNIFICANT')}: Model init takes {p1_pct:.0f}%")
        else:
            print(f"    {green('✓ FAST')}: Model init only {p1_pct:.0f}%")

    total_max = stats_b.get("total_elapsed_seconds", {}).get("max", total_b)
    print(f"    • Worker max runtime: {total_max:.1f}s")
    print(f"    • Recommended --session-timeout: {max(int(total_max * 2), 60):.0f}s")
    print(
        f"    • Recommended heartbeat-timeout: {max(int(fb_b * 2 + 5) if fb_b else 30, 30):.0f}s"
    )
    if total_b:
        print(f"    • For 5 workers: ~{5 * total_b:.0f}s per iteration")

    # Check for model shortcut
    if not stats_b.get("tool_executed"):
        print(f"\n    {yellow('⚠ NOTE: Model shortcut detected')}")
        print(f"      The model returned JSON without executing the tool call")
        print(f"      This means first-byte = first-json in this test")
        print(f"      Real worker output includes tool execution overhead")


def main():
    print(bold("\n╔══════════════════════════════════════════════════════════════╗"))
    print(bold("║  Worker Startup Profiler v4 — Phase-Level Timing            ║"))
    print(bold("╚══════════════════════════════════════════════════════════════╝"))
    print(f"\nHermes: {cyan(HERMES_BIN)}")
    print(f"Runs:   {yellow(str(NUM_RUNS))} per test")
    print(f"Workdir: {dim(str(WORKDIR))}")
    print()

    # ── Test A: Model-only response (baseline) ──
    print(bold("═══ Test A: Model-only response (baseline, no tools) ═══"))
    print(dim("  Measures: CLI startup + Python imports + model load + first token"))
    print()

    results_a = []
    for i in range(NUM_RUNS):
        label = f"A{i+1} {'(cold)' if i == 0 else '(warm)'}"
        print(f"  {bold(f'▶ {label}')} ... ", end="", flush=True)
        result = profile_model_only(i + 1, label)
        results_a.append(result)
        if "error" in result:
            print(red(f"ERROR: {result['error']}"))
        else:
            fb = result.get("phase_first_byte_seconds", 0) or 0
            tes = result["total_elapsed_seconds"]
            fj = result.get("phase_final_json_seconds", 0) or 0
            print(f"{green(f'{tes:.2f}s')}  (fb: {fb:.2f}s, json: {fj:.2f}s)")
        if i < NUM_RUNS - 1:
            time.sleep(3)

    # ── Test B: Full worker (with --yolo, forced tool) ──
    print()
    print(bold("═══ Test B: Full worker (forced tool + JSON output) ═══"))
    print(dim("  Measures: complete spawn-to-JSON with tool execution"))
    print()

    results_b = []
    for i in range(NUM_RUNS):
        label = f"B{i+1} {'(cold)' if i == 0 else '(warm)'}"
        print(f"  {bold(f'▶ {label}')} ... ", end="", flush=True)
        result = profile_worker_startup(i + 1, label)
        results_b.append(result)
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
        if i < NUM_RUNS - 1:
            time.sleep(3)

    # Print raw output from first B run for analysis
    if results_b and "error" not in results_b[0]:
        print(f"\n{dim('Raw output from B1 (first 1500 chars):')}")
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

    print()
    print_bottleneck_analysis(stats_a, stats_b)

    summary = {
        "version": 4,
        "hermes_binary": HERMES_BIN,
        "model": "DeepSeek-V4-Flash (OpenAI-compatible endpoint)",
        "num_runs_per_test": NUM_RUNS,
        "workdir": WORKDIR,
        "results_a": results_a,
        "results_b": results_b,
        "stats_a": stats_a,
        "stats_b": stats_b,
    }

    out_path = "/tmp/worker-startup-profile-v4.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n{dim(f'Full data saved to {out_path}')}")

    print()
    print(bold("═══ Key Metrics ═══"))
    if stats_b:
        avg_t = stats_b.get("total_elapsed_seconds", {}).get("avg", 0)
        avg_fb = stats_b.get("phase_first_byte_seconds", {}).get("avg", 0)
        avg_tc = stats_b.get("phase_first_tool_call_seconds", {}).get("avg")
        avg_tr = stats_b.get("phase_first_tool_result_seconds", {}).get("avg")
        avg_fj = stats_b.get("phase_final_json_seconds", {}).get("avg")
        max_t = stats_b.get("total_elapsed_seconds", {}).get("max", 0)
        print(f"  Avg total:       {green(f'{avg_t:.2f}s')}")
        print(
            f"  Avg first byte:  {green(f'{avg_fb:.2f}s')} "
            f"({avg_fb/avg_t*100:.0f}%)"
            if avg_t > 0
            else ""
        )
        if avg_tc:
            print(
                f"  Avg tool call:   {green(f'{avg_tc:.2f}s')} "
                f"(inference: {avg_tc-avg_fb:.2f}s)"
            )
        if avg_tr:
            print(
                f"  Avg tool done:   {green(f'{avg_tr:.2f}s')} "
                f"(exec: {avg_tr-(avg_tc or avg_fb):.2f}s)"
            )
        if avg_fj:
            print(f"  Avg JSON output: {green(f'{avg_fj:.2f}s')}")
        print(f"  Max total:       {yellow(f'{max_t:.2f}s')}")
        if avg_t > 0:
            print(f"  5 workers:       {yellow(f'{avg_t*5:.0f}s')} total per iteration")
        exec_pct = (
            sum(1 for r in results_b if r.get("tool_executed"))
            / max(len(results_b), 1)
            * 100
        )
        print(f"  Tool exec rate:  {green(f'{exec_pct:.0f}%')}")


if __name__ == "__main__":
    main()
