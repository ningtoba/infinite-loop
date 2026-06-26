"""Loop process manager — spawns, monitors, and controls the daemon subprocess."""

import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config_manager import build_cli_args, read_env_file

# Paths
LEDGER_PATH = "/tmp/infinite-loop-state.json"
SENTINEL_PATH = "/tmp/infinite-loop-stop"
STATUS_FILE = "/tmp/loop-status.json"


class LoopManager:
    """Manages the infinite-loop daemon as a subprocess."""

    def __init__(self, env_path: str | None = None):
        self._process: asyncio.subprocess.Process | None = None
        self._status: str = "stopped"
        self._logs: list[dict[str, Any]] = []
        self._max_logs = 500
        self._env_path = env_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
        )
        self._log_file = "/tmp/infinite-loop-web.log"
        self._log_fp = None

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
            self._logs = self._logs[-self._max_logs:]

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

        # Read current config
        config = read_env_file(self._env_path)

        # Build CLI args
        cli_args = build_cli_args(config)

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

            # Start log readers
            asyncio.create_task(self._read_stream(self._process.stdout, "stdout"))
            asyncio.create_task(self._read_stream(self._process.stderr, "stderr"))

            # Start process monitor
            asyncio.create_task(self._monitor_process())

            return {"success": True, "pid": self._process.pid}
        except Exception as e:
            self._status = "error"
            self._add_log("error", f"Failed to start daemon: {e}")
            return {"success": False, "error": str(e)}

    async def stop(self) -> dict[str, Any]:
        """Stop the loop daemon via sentinel file."""
        if not self.is_running and self._status != "paused":
            return {"success": False, "error": "Loop is not running"}

        self._add_log("info", "Sending stop signal...")

        try:
            with open(SENTINEL_PATH, "w") as f:
                f.write("stop")
        except OSError as e:
            return {"success": False, "error": f"Failed to write sentinel: {e}"}

        # Wait for process to exit gracefully
        if self._process:
            try:
                await asyncio.wait_for(self._process.wait(), timeout=30)
            except asyncio.TimeoutError:
                self._add_log("warn", "Daemon did not stop gracefully, sending SIGTERM")
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                    await asyncio.wait_for(self._process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    self._add_log("warn", "Force killing daemon...")
                    try:
                        os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                    except OSError:
                        pass

        self._status = "stopped"
        self._process = None
        self._add_log("info", "Daemon stopped")

        # Clean up sentinel
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
            },
            "error_counts": ledger.get("error_type_counts", {}),
            "mitigations": ledger.get("mitigations", {}),
            "eta": ledger.get("eta", {}),
            "latest_iteration": latest,
            "recent_logs": self._logs[-50:],
        }

    async def _read_stream(self, stream, name: str) -> None:
        """Read lines from a subprocess stream and log them."""
        while self._process and stream:
            try:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    self._add_log("info" if name == "stdout" else "warn", text)
            except (ValueError, OSError):
                break

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


def get_loop_manager(env_path: str | None = None) -> LoopManager:
    """Get or create the global loop manager instance."""
    global _loop_manager
    if _loop_manager is None:
        _loop_manager = LoopManager(env_path)
    return _loop_manager
