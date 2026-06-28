"""Hermes Worker Manager — auto-starts the worker as a child process."""

import os
import subprocess
import sys
import time
import socket
import urllib.request

from .file_utils import _log


class HermesWorkerManager:
    """Manages a Hermes MCP worker process lifecycle.

    When ``--worker-url auto`` is used, the daemon starts the worker
    as a background subprocess on a random port and kills it on shutdown.

    When ``--worker-url http://...`` is given, this manager is bypassed
    (the user manages the worker externally).

    When ``--worker-url`` is empty, the default subprocess mode is used.
    """

    WORKER_SCRIPT = os.path.expanduser("~/.hermes/plugins/hermes-mcp-worker/main.py")

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._port: int = 0

    def start(self) -> str:
        """Start the worker and return its URL. Returns '' on failure."""

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            self._port = s.getsockname()[1]
        worker_url = f"http://127.0.0.1:{self._port}"

        if not os.path.isfile(self.WORKER_SCRIPT):
            _log(
                f"[WORKER] Script not found at {self.WORKER_SCRIPT}, using direct mode"
            )
            return ""

        try:
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    self.WORKER_SCRIPT,
                    "--port",
                    str(self._port),
                    "--host",
                    "127.0.0.1",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(
                        f"{worker_url}/health", timeout=2
                    ) as resp:
                        if resp.status == 200:
                            _log(
                                f"[WORKER] Started on {worker_url} (PID={self._process.pid})"
                            )
                            return worker_url
                except Exception:
                    pass
                time.sleep(0.5)
            _log("[WORKER] Failed to start within 10s, falling back to direct mode")
            self.stop()
            return ""
        except Exception as e:
            _log(f"[WORKER] Failed to start: {e}")
            return ""

    def stop(self):
        """Kill the worker process."""
        if self._process and self._process.poll() is None:
            _log(f"[WORKER] Stopping worker (PID={self._process.pid})")
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
            self._process = None
            _log("[WORKER] Stopped")

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None
