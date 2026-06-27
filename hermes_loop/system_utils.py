"""System resource tracking — /proc-based CPU/memory usage (stdlib only)."""

import os


def get_system_usage() -> dict:
    """Read CPU and memory usage from /proc (Linux).

    Returns dict with:
      - cpu_percent: approximate CPU usage as fraction of one core (0.0+)
      - memory_rss_mb: RSS memory in MB
      - memory_vms_mb: virtual memory in MB
      - memory_percent: fraction of total RAM

    Uses stdlib only — no psutil dependency.
    """
    result: dict[str, float] = {}
    pid = os.getpid()

    # Memory from /proc/pid/status
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        result["memory_rss_mb"] = int(parts[1]) / 1024
                elif line.startswith("VmSize:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        result["memory_vms_mb"] = int(parts[1]) / 1024
                elif line.startswith("VmPeak:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        result["memory_peak_mb"] = int(parts[1]) / 1024
    except (FileNotFoundError, IOError, ValueError):
        pass

    # Total RAM
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        total_kb = int(parts[1])
                        rss_kb = result.get("memory_rss_mb", 0) * 1024
                        if total_kb > 0:
                            result["memory_percent"] = round(rss_kb / total_kb, 4)
                    break
    except (FileNotFoundError, IOError, ValueError):
        pass

    # CPU time from /proc/pid/stat (user + system ticks)
    try:
        with open(f"/proc/{pid}/stat") as f:
            stat_data = f.read()
        parts = stat_data.split(")")
        if len(parts) >= 2:
            fields = parts[1].strip().split()
            if len(fields) >= 20:
                utime = int(fields[11])
                stime = int(fields[12])
                try:
                    clk_tck = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", 2))
                except (AttributeError, KeyError, ValueError, OSError):
                    clk_tck = 100
                total_ticks = utime + stime
                result["cpu_ticks_used"] = total_ticks
                result["cpu_seconds"] = total_ticks / clk_tck
    except (FileNotFoundError, IOError, ValueError, AttributeError):
        pass

    return result


def get_system_usage_diff(before: dict, after: dict) -> dict:
    """Compute system usage diff between two snapshots."""
    diff: dict = {}
    if before and after:
        cpu_b = before.get("cpu_seconds", 0)
        cpu_a = after.get("cpu_seconds", 0)
        diff["cpu_seconds_used"] = round(cpu_a - cpu_b, 3)
        diff["memory_rss_mb"] = after.get("memory_rss_mb", 0)
        diff["memory_vms_mb"] = after.get("memory_vms_mb", 0)
        diff["memory_percent"] = after.get("memory_percent", 0)
        diff["memory_peak_mb"] = after.get("memory_peak_mb", 0)
    return diff
