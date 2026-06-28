"""Loop process manager — spawns, monitors, and controls the daemon subprocess."""

import asyncio
import json
import os
import re
import signal
import sys
from datetime import datetime, timezone
from typing import Any

from .config_manager import build_cli_args, get_raw_config

# Paths
LEDGER_PATH = "/tmp/infinite-loop-state.json"
SENTINEL_PATH = "/tmp/infinite-loop-stop"
STATUS_FILE = "/tmp/loop-status.json"


class LoopManager:
    """Manages the infinite-loop daemon as a subprocess."""

    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None
        self._status: str = "stopped"
        self._logs: list[dict[str, Any]] = []
        self._max_logs = 500
        self._log_file = "/tmp/infinite-loop-web.log"
        self._log_fp = None
        # Live iteration state parsed from daemon stdout
        self._live_iteration: dict[str, Any] = {}
        self._worker_states: dict[str, dict[str, Any]] = {}
        self._worker_logs: dict[str, list[dict[str, Any]]] = {}  # wid -> log entries
        self._worker_term: dict[str, list[str]] = (
            {}
        )  # wid -> raw terminal lines (ANSI intact)

    @property
    def live_iteration(self) -> dict[str, Any]:
        return self._live_iteration

    def _kill_stale_daemons(self) -> None:
        """Kill any hermes_loop daemon processes left over from previous runs.

        Uses a precise pattern to avoid matching non-daemon python processes.
        Only targets processes whose full command line contains
        ``-m hermes_loop --run`` (the exact daemon invocation pattern).
        """
        import subprocess

        try:
            r = subprocess.run(
                ["pkill", "-f", r"python.*-m\s+hermes_loop.*--run"],
                capture_output=True,
                timeout=5,
            )
            if r.returncode == 0:
                self._add_log("info", "Cleaned up stale daemon processes")
        except Exception:
            pass

    @property
    def status(self) -> str:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status == "running" and self._process is not None

    @property
    def logs(self) -> list[dict[str, Any]]:
        return self._logs

    def _add_log(self, level: str, message: str) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
        self._logs.append(entry)
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs :]

        # Also write to log file
        try:
            if self._log_fp is None:
                os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
                self._log_fp = open(self._log_file, "a")
            ts = entry["timestamp"][:19]
            self._log_fp.write(f"[{ts}] [{level}] {message}\n")
            self._log_fp.flush()
        except OSError:
            pass

    async def start(self) -> dict[str, Any]:
        """Start the loop daemon as a subprocess."""
        if self.is_running:
            return {"success": False, "error": "Loop is already running"}

        # Kill any stale daemon processes from previous web server instances
        self._kill_stale_daemons()

        # Read current config from JSON
        config = get_raw_config()

        # When running inside Docker, the workdir is always mounted at /workdir.
        # On the host, use the user's actual path from config (or cwd if empty).
        in_docker = os.path.exists("/.dockerenv") or os.environ.get(
            "DOCKER_CONTAINER", ""
        )
        if in_docker:
            config["INFINITE_LOOP_WORKDIR"] = "/workdir"
        elif config.get("INFINITE_LOOP_WORKDIR", "") == "/workdir":
            # Stale Docker path on host — clear it so daemon uses cwd
            config["INFINITE_LOOP_WORKDIR"] = ""

        # Build CLI args
        cli_args = build_cli_args(config)

        # Force --workdir when in Docker (build_cli_args skips defaults)
        if in_docker and "--workdir" not in cli_args:
            cli_args.extend(["--workdir", "/workdir"])

        # Force --worker-url '' for live stdout streaming (direct subprocess mode).
        # build_cli_args skips empty values, but the daemon defaults to 'auto'.
        if "--worker-url" not in cli_args:
            cli_args.extend(["--worker-url", ""])

        # Only pass --worktree if the workdir is actually a git repo
        workdir = config.get("INFINITE_LOOP_WORKDIR", "") or os.getcwd()
        if not os.path.isdir(os.path.join(workdir, ".git")):
            if "--worktree" in cli_args:
                cli_args.remove("--worktree")

        # Disable auto-reload — the daemon's os.execv crashes when spawned
        # as a subprocess of the web server. The web UI handles restarts.
        os.environ["HERMES_LOOP_NO_AUTO_RELOAD"] = "1"

        # Ensure --run flag is present
        if "--run" not in cli_args:
            cli_args.append("--run")

        # Clean up stale sentinel
        if os.path.exists(SENTINEL_PATH):
            try:
                os.remove(SENTINEL_PATH)
            except OSError:
                pass

        cmd = [sys.executable, "-m", "hermes_loop"] + cli_args

        self._add_log("info", f"Starting daemon: {' '.join(cmd)}")

        # Reset live iteration tracking
        self._live_iteration = {}
        self._worker_states = {}

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
                preexec_fn=os.setsid,
            )

            self._status = "running"
            self._add_log("info", f"Daemon started (PID: {self._process.pid})")

            # Start log readers — store references to prevent GC of pending tasks
            self._tasks: set[asyncio.Task] = set()

            def _bg(task: asyncio.Task) -> None:
                self._tasks.discard(task)

            for coro in (
                self._read_stream(self._process.stdout, "stdout"),
                self._read_stream(self._process.stderr, "stderr"),
                self._monitor_process(),
            ):
                t = asyncio.create_task(coro)
                self._tasks.add(t)
                t.add_done_callback(_bg)

            return {"success": True, "pid": self._process.pid}
        except Exception as e:
            self._status = "error"
            self._add_log("error", f"Failed to start daemon: {e}")
            return {"success": False, "error": str(e)}

    async def stop(self) -> dict[str, Any]:
        """Stop the loop daemon — writes sentinel + immediately kills the
        process group (including any running hermes chat session)."""
        if not self.is_running and self._status != "paused":
            return {"success": False, "error": "Loop is not running"}

        self._add_log("info", "Stopping daemon...")

        # Write sentinel so the daemon knows it was a controlled stop
        try:
            with open(SENTINEL_PATH, "w") as f:
                f.write("stop")
        except OSError:
            pass

        # Immediately kill the process group — the daemon only checks the
        # sentinel between iterations, so we need SIGTERM to stop a running
        # hermes chat session mid-iteration.
        if self._process:
            pgid = None
            try:
                pgid = os.getpgid(self._process.pid)
                os.killpg(pgid, signal.SIGTERM)
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                if pgid is not None:
                    self._add_log("warn", "Force killing...")
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                        await asyncio.wait_for(self._process.wait(), timeout=5)
                    except (asyncio.TimeoutError, OSError):
                        pass
            except (ProcessLookupError, OSError):
                pass

        self._status = "stopped"
        self._process = None
        self._add_log("info", "Daemon stopped")

        try:
            if os.path.exists(SENTINEL_PATH):
                os.remove(SENTINEL_PATH)
        except OSError:
            pass

        return {"success": True}

    async def pause(self) -> dict[str, Any]:
        """Pause the loop daemon."""
        if not self.is_running:
            return {"success": False, "error": "Loop is not running"}

        self._add_log("info", "Sending pause signal...")
        try:
            with open(SENTINEL_PATH, "w") as f:
                f.write("pause")
            self._status = "paused"
            return {"success": True}
        except OSError as e:
            return {"success": False, "error": str(e)}

    async def resume(self) -> dict[str, Any]:
        """Resume the loop daemon."""
        if self._status != "paused":
            return {"success": False, "error": "Loop is not paused"}

        self._add_log("info", "Sending resume signal...")
        try:
            if os.path.exists(SENTINEL_PATH):
                os.remove(SENTINEL_PATH)
            self._status = "running"
            return {"success": True}
        except OSError as e:
            return {"success": False, "error": str(e)}

    def get_ledger(self) -> dict[str, Any]:
        """Read the current ledger state."""
        try:
            if os.path.exists(LEDGER_PATH):
                with open(LEDGER_PATH, "r") as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
        return {"status": "no_ledger", "iterations": [], "total_iterations": 0}

    def get_status(self) -> dict[str, Any]:
        """Get combined status information."""
        ledger = self.get_ledger()
        stats = ledger.get("stats", {})
        iterations = ledger.get("iterations", [])
        latest = iterations[-1] if iterations else None

        # Compute throughput metrics from iteration data (matching _build_sse_payload)
        avg_chars_per_iter_v = None
        avg_throughput_v = None
        if iterations:
            chars_list = [it.get("output_chars", 0) or 0 for it in iterations]
            if chars_list:
                avg_chars_per_iter_v = int(sum(chars_list) // len(chars_list))
            cps_list = [
                it.get("chars_per_second", 0) or 0
                for it in iterations
                if it.get("chars_per_second", 0)
            ]
            if cps_list:
                avg_throughput_v = round(sum(cps_list) / len(cps_list), 1)
        metrics_parts = []
        if avg_chars_per_iter_v is not None:
            metrics_parts.append(f"{avg_chars_per_iter_v} chars/iter")
        if avg_throughput_v is not None:
            metrics_parts.append(f"{avg_throughput_v} cps avg")
        if stats.get("avg_duration_seconds", 0):
            metrics_parts.append(f'{stats["avg_duration_seconds"]:.0f}s avg')
        metrics_summary_v = ", ".join(metrics_parts) if metrics_parts else ""
        iters_per_goal_v = None
        goals_count = len(ledger.get("goals_specs", [])) or 1
        total_iters = ledger.get("total_iterations", 0)
        if total_iters > 0:
            iters_per_goal_v = max(1, total_iters // goals_count)

        return {
            "loop_status": self._status,
            "pid": self._process.pid if self._process else None,
            "ledger": {
                "status": ledger.get("status", "unknown"),
                "total_iterations": ledger.get("total_iterations", 0),
                "started_at": ledger.get("started_at", ""),
                "last_updated": ledger.get("last_updated", ""),
                "goal": (ledger.get("initial_command") or "")[:120],
                "evolved_goal": ledger.get("evolved_goal", ""),
                "max_iterations": ledger.get("max_iterations", 0),
                "tag": ledger.get("tag", ""),
                "cooldown": ledger.get("cooldown", 0),
            },
            "stats": {
                "success_count": stats.get("success_count", 0),
                "error_count": stats.get("error_count", 0),
                "total_duration_seconds": stats.get("total_duration_seconds", 0),
                "avg_duration_seconds": stats.get("avg_duration_seconds", 0),
                "consecutive_errors": stats.get("consecutive_errors", 0),
                "consecutive_successes": stats.get("consecutive_successes", 0),
            },
            "error_counts": ledger.get("error_type_counts", {}),
            "mitigations": ledger.get("mitigations", {}),
            "eta": ledger.get("eta", {}),
            "avg_chars_per_iter": avg_chars_per_iter_v,
            "avg_throughput": avg_throughput_v,
            "iters_per_goal": iters_per_goal_v,
            "metrics_summary": metrics_summary_v,
            "est_cost": ledger.get("est_cost"),
            "latest_iteration": latest,
            "live_iteration": self._live_iteration,
            "worker_logs": {w: logs[-100:] for w, logs in self._worker_logs.items()},
            "worker_term": {w: lines[-500:] for w, lines in self._worker_term.items()},
            "recent_logs": self._logs[-50:],
        }

    async def _read_stream(self, stream, name: str) -> None:
        """Read lines from a subprocess stream, log them, and parse worker events."""
        while self._process and stream:
            try:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    level = "info" if name == "stdout" else "warn"
                    self._add_log(level, text)
                    self._parse_daemon_line(text)
            except (ValueError, OSError):
                break
            except Exception as e:
                self._add_log("error", f"Stream reader crashed ({name}): {e}")
                break

    def _parse_daemon_line(self, text: str) -> None:
        """Parse daemon stdout for live iteration/worker progress and per-worker logs."""
        ts = datetime.now(timezone.utc).isoformat()

        # Iteration start — only match daemon's actual iteration header line.
        # Format: "[HH:MM:SS] Iteration N" where the line starts with a
        # timestamp or is preceded by a separator/blank line context.
        # The line must consist ONLY of the timestamp + "Iteration N" (nothing else).
        m = re.search(r"^\[\d{2}:\d{2}:\d{2}\]\s+Iteration\s+#?(\d+)\s*$", text)
        if m and "still running" not in text.lower():
            it_num = int(m.group(1))
            if self._live_iteration.get("n") != it_num:
                self._live_iteration = {"n": it_num, "workers": [], "started_at": ts}
                self._worker_states = {}
                self._worker_logs = {}

        # Detect worker ID — daemon lines use "(worker #N)" format
        wid = None
        m = re.search(r"\(worker\s+#(\d+)\)", text)
        if m:
            wid = m.group(1)
        # Also check for [STDOUT (worker #N)], [STDERR (worker #N)], [TERM (worker #N)]
        for prefix in ("STDOUT", "STDERR", "MODEL", "TERM"):
            m = re.search(rf"\[{prefix}\s*\(worker\s+#(\d+)\)\]", text)
            if m:
                wid = m.group(1)
                if wid not in self._worker_states:
                    self._worker_states[wid] = {
                        "id": wid,
                        "status": "running",
                        "started_at": ts,
                    }
                if wid not in self._worker_logs:
                    self._worker_logs[wid] = []
                # Store raw terminal output for xterm.js rendering
                if prefix == "TERM":
                    if wid not in self._worker_term:
                        self._worker_term[wid] = []
                    # Extract just the terminal content (strip the [TERM (worker #N)] prefix)
                    term_content = re.sub(
                        rf"\[TERM\s*\(worker\s+#{re.escape(wid)}\)\]\s*",
                        "",
                        text,
                        count=1,
                    )
                    self._worker_term[wid].append(term_content)
                    if len(self._worker_term[wid]) > 1000:
                        self._worker_term[wid] = self._worker_term[wid][-1000:]

        # Worker spawned
        m = re.search(r"\[SPAWN\s+\(worker\s+#(\d+)\)\]", text)
        if m:
            wid = m.group(1)
            self._worker_states[wid] = {
                "id": wid,
                "status": "running",
                "started_at": ts,
            }
            if wid not in self._worker_logs:
                self._worker_logs[wid] = []

        # Worker completed
        m = re.search(
            r"\[WORKER\s+\(worker\s+#(\d+)\)\]\s+Response\s+in\s+([\d.]+)s\s+\(status=(\w+)\)",
            text,
        )
        if m:
            wid = m.group(1)
            self._worker_states[wid] = {
                "id": wid,
                "status": m.group(3),
                "duration_seconds": float(m.group(2)),
                "completed_at": ts,
            }

        # Heartbeat
        m = re.search(
            r"\[BEAT\]\s+Iteration\s+#?(\d+)\s+still\s+running\s+\((\d+)s", text
        )
        if m:
            self._live_iteration["elapsed_seconds"] = int(m.group(2))

        # Error type
        m = re.search(r"\[ERROR-TYPE\]\s+(\w+)", text)
        if m:
            self._live_iteration["error_type"] = m.group(1)

        # Store per-worker log line (skip for TERM lines — already stored as terminal content)
        if wid and wid in self._worker_logs:
            # Check if this is a TERM line (already stored in worker_term above)
            _is_term_line = bool(re.search(r"\[TERM\s*\(worker", text))
            if not _is_term_line:
                entry = {"timestamp": ts, "message": text}
                self._worker_logs[wid].append(entry)
                if len(self._worker_logs[wid]) > 200:
                    self._worker_logs[wid] = self._worker_logs[wid][-200:]

        # Keep worker list in sync
        self._live_iteration["workers"] = list(self._worker_states.values())

    async def _monitor_process(self) -> None:
        """Monitor the process and handle unexpected exits."""
        if not self._process:
            return
        try:
            returncode = await self._process.wait()
            self._add_log(
                "info" if returncode == 0 else "error",
                f"Daemon exited with code {returncode}",
            )
            if self._status in ("running", "paused"):
                self._status = "stopped"
            self._process = None
        except Exception as e:
            self._add_log("error", f"Process monitor error: {e}")


# Global singleton
_loop_manager: LoopManager | None = None


def get_loop_manager() -> LoopManager:
    """Get or create the global loop manager instance."""
    global _loop_manager
    if _loop_manager is None:
        _loop_manager = LoopManager()
    return _loop_manager
