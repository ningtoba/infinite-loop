"""Loop process manager — spawns, monitors, and controls the daemon subprocess."""

import asyncio
import contextlib
import json
import os
import re
import signal
import sys
from datetime import datetime, timezone
from typing import Any

from omp_loop.config import DEFAULT_LOG_FILE, LEDGER_PATH
from omp_loop.config import SENTINEL_PATH_DEFAULT as SENTINEL_PATH

from .config_manager import build_cli_args, get_raw_config

# Compiled regex to strip ANSI escape sequences from daemon output
# (e.g. color codes) before matching against known patterns.
_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class LoopManager:
    """Manages the infinite-loop daemon as a subprocess."""

    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None
        self._status: str = "stopped"
        self._logs: list[dict[str, Any]] = []
        self._max_logs = 500
        self._ledger_path = LEDGER_PATH
        self._sentinel_path = SENTINEL_PATH
        self._log_file = DEFAULT_LOG_FILE
        self._log_fp = None
        # Lock for coordinated start/stop/monitor to prevent race conditions
        self._lock = asyncio.Lock()
        # Live iteration state parsed from daemon stdout
        self._live_iteration: dict[str, Any] = {}
        self._worker_states: dict[str, dict[str, Any]] = {}
        self._worker_logs: dict[str, list[dict[str, Any]]] = {}  # wid -> log entries
        self._worker_term: dict[str, list[str]] = {}  # wid -> raw terminal lines (ANSI intact)
        # Track reader tasks so they can be cancelled on restart (RACE-2)
        self._reader_tasks: list[asyncio.Task] = []
        # Hydrate in-memory logs from the persisted log file so worker output
        # survives web UI restarts.  Skipped when OMP_LOOP_NO_HYDRATE is set
        # (tests) so that test assertions are not polluted by real log data.
        if not os.environ.get("OMP_LOOP_NO_HYDRATE"):
            self._hydrate_from_log_file()

    @property
    def live_iteration(self) -> dict[str, Any]:
        return self._live_iteration

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
                self._log_fp = open(self._log_file, "a")  # noqa: SIM115  # keep instance attr open for reuse
            ts = entry["timestamp"][:19]
            self._log_fp.write(f"[{ts}] [{level}] {message}\n")
            self._log_fp.flush()
        except OSError:
            pass

    def _hydrate_from_log_file(self) -> None:
        """Replay recent log entries from the persisted log file so that
        worker terminal output and structured logs survive web UI restarts.

        Reads the last 64 KB of the log file and re-parses every line through
        ``_parse_daemon_line`` to reconstruct ``_worker_logs`` and
        ``_worker_term``.
        """
        try:
            if not os.path.isfile(self._log_file):
                return
            file_size = os.path.getsize(self._log_file)
            if file_size == 0:
                return

            # Read the tail of the log file (last 64 KB covers plenty of
            # recent context without loading the whole file into memory).
            tail_bytes = min(file_size, 64 * 1024)
            with open(self._log_file, "rb") as f:
                if file_size > tail_bytes:
                    # Seek back and find start of a complete line (L-5)
                    f.seek(file_size - tail_bytes)
                    # Read forward to find the first newline — stop before it
                    remaining = f.read()
                    first_nl = remaining.find(b"\n")
                    if first_nl >= 0:
                        f.seek(file_size - tail_bytes + first_nl + 1)
                    else:
                        f.seek(file_size - tail_bytes)
                for line in f:
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if not text:
                        continue
                    m = re.match(r"^\[([^\]]+)\] \[(\w+)\] (.*)", text)
                    if m is None:
                        continue
                    level, message = m.group(2), m.group(3)
                    entry = {
                        "timestamp": m.group(1),
                        "level": level,
                        "message": message,
                    }
                    self._logs.append(entry)
                    self._parse_daemon_line(message)

            # Trim to configured limits.
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs :]
        except OSError:
            pass

    async def start(self) -> dict[str, Any]:
        """Start the loop daemon as a subprocess."""
        if self.is_running:
            return {"success": False, "error": "Loop is already running"}

        # Read current config from JSON — copy so mutations don't
        # leak back into the stored config (M-5).
        config = dict(get_raw_config())

        # When running inside Docker, the workdir is always mounted at /workdir.
        # On the host, use the user's actual path from config (or cwd if empty).
        in_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER", "")
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

        # omp-loop uses direct subprocess mode (no worker-url concept).

        # Always pass --run — clicking Start implies the user wants to run
        if "--run" not in cli_args:
            cli_args.append("--run")

        # Only pass --worktree if the workdir is actually a git repo
        workdir = config.get("INFINITE_LOOP_WORKDIR", "") or os.getcwd()
        if not os.path.isdir(os.path.join(workdir, ".git")) and "--worktree" in cli_args:
            cli_args.remove("--worktree")

        # Clean up stale sentinel
        if os.path.exists(SENTINEL_PATH):
            with contextlib.suppress(OSError):
                os.remove(SENTINEL_PATH)

        cmd = [sys.executable, "-m", "omp_loop"] + cli_args

        self._add_log("info", f"Starting daemon: {' '.join(cmd)}")

        # Reset live iteration tracking
        self._live_iteration = {}
        self._worker_states = {}

        # Cancel any stale reader task handles from a prior run
        self._cancel_stale_readers()

        try:
            async with self._lock:
                self._process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env={**os.environ.copy(), "PYTHONUNBUFFERED": "1"},
                        preexec_fn=os.setsid,
                    ),
                    timeout=30,
                )

            # Verify process is alive before setting status
            await asyncio.sleep(0.1)
            if self._process.returncode is not None:
                self._status = "error"
                self._add_log(
                    "error",
                    f"Daemon exited immediately (code {self._process.returncode})",
                )
                return {
                    "success": False,
                    "error": f"Process exited immediately with code {self._process.returncode}",
                }

            self._add_log("info", f"Daemon started (PID: {self._process.pid})")

            # Start log readers — pass stream + pid explicitly to avoid stale references
            # BUS-005: store task handles so they can be cancelled on restart
            self._reader_tasks = [
                asyncio.create_task(self._read_stream(self._process.stdout, "stdout", self._process)),
                asyncio.create_task(self._read_stream(self._process.stderr, "stderr", self._process)),
            ]

            # Start process monitor
            asyncio.create_task(self._monitor_process())

            # Set status AFTER monitors are created — BUG-004 fix
            self._status = "running"

            return {"success": True, "pid": self._process.pid}
        except asyncio.TimeoutError:
            self._status = "error"
            self.close()
            self._add_log("error", "Timed out starting daemon (30s)")
            return {"success": False, "error": "Timed out waiting for daemon to start"}
        except Exception as e:
            self._status = "error"
            self.close()
            self._add_log("error", f"Failed to start daemon: {e}")
            return {"success": False, "error": str(e)}

    async def stop(self) -> dict[str, Any]:
        """Stop the loop daemon — writes sentinel + immediately kills the
        # process group (including any running omp chat session)."""
        # Hold the lock for the ENTIRE kill+cleanup+nullify sequence
        # to prevent concurrent start() from inserting a new process (RACE-1).
        async with self._lock:
            proc = self._process
            if not self.is_running and self._status != "paused":
                return {"success": False, "error": "Loop is not running"}

            self._status = "stopped"
            self._add_log("info", "Stopping daemon...")

        # Write sentinel so the daemon knows it was a controlled stop
        try:
            with open(SENTINEL_PATH, "w") as f:
                f.write("stop")
        except OSError:
            pass

        # Immediately kill the process group — the daemon only checks the
        # sentinel between iterations, so we need SIGTERM to stop a running
        # omp chat session mid-iteration.
        # Capture PID locally to avoid TOCTOU race (BUG-003).
        if proc is not None:
            try:
                pid = proc.pid
            except (AttributeError, ProcessLookupError):
                pid = None
            pgid = None
            if pid is not None:
                try:
                    # Validate PID/PGID ownership before sending signals
                    os.kill(pid, 0)  # Check process still exists
                    pgid = os.getpgid(pid)
                except (ProcessLookupError, PermissionError, OSError):
                    pgid = None
            if pgid is not None:
                try:
                    os.killpg(pgid, signal.SIGTERM)
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._add_log("warn", "Force killing...")
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except (asyncio.TimeoutError, OSError):
                        pass
                except (ProcessLookupError, OSError):
                    pass

        async with self._lock:
            self._process = None
            # Cancel stale reader tasks so they don't accumulate (RACE-2)
            self._cancel_stale_readers()

        self._add_log("info", "Daemon stopped")

        # Close log file handle
        self.close()

        try:
            if os.path.exists(self._sentinel_path):
                os.remove(self._sentinel_path)
        except OSError:
            pass

        return {"success": True}

    async def pause(self) -> dict[str, Any]:
        """Pause the loop daemon."""
        if not self.is_running:
            return {"success": False, "error": "Loop is not running"}

        self._add_log("info", "Sending pause signal...")
        try:
            with open(self._sentinel_path, "w") as f:
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
            if os.path.exists(self._sentinel_path):
                os.remove(self._sentinel_path)
            self._status = "running"
            return {"success": True}
        except OSError as e:
            return {"success": False, "error": str(e)}

    def get_ledger(self) -> dict[str, Any]:
        """Read the current ledger state (synchronous, called from sync contexts)."""
        try:
            if os.path.exists(self._ledger_path):
                with open(self._ledger_path) as f:
                    return json.load(f)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError):
            pass
        return {"status": "no_ledger", "iterations": [], "total_iterations": 0}

    async def async_get_ledger(self) -> dict[str, Any]:
        """Read the ledger asynchronously, offloading file I/O to a thread (M-4)."""
        try:
            exists = await asyncio.to_thread(os.path.exists, self._ledger_path)
            if exists:

                def _read_json():
                    with open(self._ledger_path) as f:
                        return json.load(f)

                return await asyncio.to_thread(_read_json)
        except (json.JSONDecodeError, OSError):
            pass
        return {"status": "no_ledger", "iterations": [], "total_iterations": 0}

    def get_status(self) -> dict[str, Any]:
        """Get combined status information."""
        ledger = self.get_ledger()
        stats = ledger.get("stats", {})
        iterations = ledger.get("iterations", [])
        latest = iterations[-1] if iterations else None

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
            "latest_iteration": latest,
            "live_iteration": self._live_iteration,
            "worker_logs": {w: logs[-100:] for w, logs in self._worker_logs.items()},
            "worker_term": {w: lines[-500:] for w, lines in self._worker_term.items()},
            "recent_logs": self._logs[-50:],
        }

    async def async_get_status(self) -> dict[str, Any]:
        """Async variant of get_status that offloads ledger file I/O to a thread (M-4)."""
        ledger = await self.async_get_ledger()
        stats = ledger.get("stats", {})
        iterations = ledger.get("iterations", [])
        latest = iterations[-1] if iterations else None

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
            "latest_iteration": latest,
            "live_iteration": self._live_iteration,
            "worker_logs": {w: logs[-100:] for w, logs in self._worker_logs.items()},
            "worker_term": {w: lines[-500:] for w, lines in self._worker_term.items()},
            "recent_logs": self._logs[-50:],
        }

    async def _read_stream(self, stream, name: str, proc: asyncio.subprocess.Process | None = None) -> None:
        """Read lines from a subprocess stream, log them, and parse worker events.
        Uses the explicitly-passed process reference instead of capturing self._process (RACE-2).
        """
        while proc and stream:
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

    def _handle_event(self, event: dict, ts: str) -> None:
        """Handle a structured ``[EVENT]`` NDJSON line.

        This is the fast path — the event dict has already been parsed
        from JSON, so no regex is needed.  Falls back to the regex
        parser when the event type is unknown.
        """
        event_type = event.get("type", "")

        if event_type == "spawn":
            wid = str(event.get("worker_id", ""))
            if wid:
                self._worker_states[wid] = {
                    "id": wid,
                    "status": "running",
                    "started_at": ts,
                }
                if wid not in self._worker_logs:
                    self._worker_logs[wid] = []

        elif event_type == "worker_response":
            wid = str(event.get("worker_id", ""))
            if wid:
                self._worker_states[wid] = {
                    "id": wid,
                    "status": event.get("status", "ok"),
                    "duration_seconds": event.get("duration"),
                    "completed_at": ts,
                }

        elif event_type == "term":
            wid = str(event.get("worker_id", ""))
            line = event.get("line", "")
            if wid:
                if wid not in self._worker_term:
                    self._worker_term[wid] = []
                self._worker_term[wid].append(line)
                if len(self._worker_term[wid]) > 2000:
                    self._worker_term[wid] = self._worker_term[wid][-2000:]

        elif event_type == "iteration_start":
            it_num = event.get("n", 0)
            if self._live_iteration.get("n") != it_num:
                self._live_iteration = {
                    "n": it_num,
                    "workers": [],
                    "started_at": ts,
                }
                self._worker_states = {}
                self._worker_logs = {}

        elif event_type == "iteration_complete":
            self._live_iteration["duration_seconds"] = event.get("duration_seconds")
            if event.get("has_error"):
                self._live_iteration["error_type"] = event.get("error_type")

        elif event_type == "heartbeat":
            self._live_iteration["elapsed_seconds"] = event.get("elapsed_seconds")

        elif event_type == "error_type":
            self._live_iteration["error_type"] = event.get("error_type")

        elif event_type == "shutdown":
            self._live_iteration["stop_reason"] = event.get("reason", "")

    def _parse_daemon_line(self, text: str) -> None:
        """Parse daemon stdout for live iteration/worker progress and per-worker logs.

        Fast path: if the line starts with ``[EVENT]``, parse the JSON and
        call ``_handle_event()`` directly without any regex.
        Slow (but compatible) path: strip ANSI codes and apply the existing
        regex patterns.
        """
        ts = datetime.now(timezone.utc).isoformat()

        # ── Fast path: structured [EVENT] JSON ──
        if text.startswith("[EVENT] "):
            try:
                event_data = json.loads(text[len("[EVENT] ") :])
                self._handle_event(event_data, ts)
                return
            except (json.JSONDecodeError, TypeError):
                pass  # Malformed — fall through to regex

        # ── Slow (compatible) path: regex ──
        # Iteration start — only match daemon's actual iteration header line.
        # Format: "[HH:MM:SS] Iteration N" where the line starts with a
        # timestamp or is preceded by a separator/blank line context.
        # The line must consist ONLY of the timestamp + "Iteration N" (nothing else).
        # Strip ANSI escape sequences before matching so colorized output
        # (e.g. "\x1b[32m[HH:MM:SS] Iteration N") is still detected.
        clean_text = _ANSI_ESCAPE.sub("", text)
        m = re.search(r"^\[\d{2}:\d{2}:\d{2}\]\s+Iteration\s+#?(\d+)\s*$", clean_text)
        if m and "still running" not in text.lower():
            try:
                it_num = int(m.group(1))
            except (ValueError, TypeError):
                it_num = 0
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
                    # Extract just the terminal content (strip the [TERM (worker #N)] prefix)
                    term_content = re.sub(
                        rf"\[TERM\s*\(worker\s+#{re.escape(wid)}\)\]\s*",
                        "",
                        text,
                        count=1,
                    )
                    if wid not in self._worker_term:
                        self._worker_term[wid] = []
                    self._worker_term[wid].append(term_content)
                    if len(self._worker_term[wid]) > 2000:
                        self._worker_term[wid] = self._worker_term[wid][-2000:]

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
            try:
                wid = m.group(1)
                self._worker_states[wid] = {
                    "id": wid,
                    "status": m.group(3),
                    "duration_seconds": float(m.group(2)),
                    "completed_at": ts,
                }
            except (ValueError, TypeError):
                pass

        # Heartbeat
        m = re.search(r"\[BEAT\]\s+Iteration\s+#?(\d+)\s+still\s+running\s+\((\d+)s", text)
        if m:
            with contextlib.suppress(ValueError, TypeError):
                self._live_iteration["elapsed_seconds"] = int(m.group(2))

        # Error type
        m = re.search(r"\[ERROR-TYPE\]\s+(\w+)", text)
        if m:
            self._live_iteration["error_type"] = m.group(1)

        # Store per-worker log line
        if wid and wid in self._worker_logs:
            entry = {"timestamp": ts, "message": text}
            self._worker_logs[wid].append(entry)
            if len(self._worker_logs[wid]) > 200:
                self._worker_logs[wid] = self._worker_logs[wid][-200:]

        # Keep worker list in sync
        self._live_iteration["workers"] = list(self._worker_states.values())

    async def _monitor_process(self) -> None:
        """Monitor the process and handle unexpected exits.
        Uses _lock when setting self._process = None to prevent concurrent
        stop() from writing None mid-read (BUG-002).
        """
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
            async with self._lock:
                self._process = None
        except Exception as e:
            self._add_log("error", f"Process monitor error: {e}")

    def close(self):
        """Close the log file handle."""
        try:
            if self._log_fp is not None:
                self._log_fp.close()
        except OSError:
            pass
        finally:
            self._log_fp = None

    def __del__(self):
        self.close()

    def _cancel_stale_readers(self):
        """Cancel any reader tasks from a prior run to prevent zombie coroutines (RACE-2)."""
        for t in self._reader_tasks:
            t.cancel()
        self._reader_tasks = []

    def _close_log(self):
        """Internal alias for close()."""
        self.close()


# Global singleton
_loop_manager: LoopManager | None = None


def get_loop_manager() -> LoopManager:
    """Get or create the global loop manager instance."""
    global _loop_manager
    if _loop_manager is None:
        _loop_manager = LoopManager()
    return _loop_manager
