# Stdlib-Only Daemon Patterns

The infinite-loop daemon uses zero pip dependencies — every feature is built
from Python stdlib. This reference documents the reusable patterns.

## Why Stdlib-Only

- No pip install step needed when deploying the skill
- Works on any Python 3.10+ installation
- No version conflicts with the user's Hermes env
- Can be embedded in `terminal(background=true)` without env setup

## Pattern: Importing a Module with a Hyphenated Filename

Python cannot `import launch-loop` directly because of the hyphen.
Use `importlib.util.spec_from_file_location`:

```python
import importlib.util, sys
spec = importlib.util.spec_from_file_location('launch_loop', 'launch-loop.py')
mod = importlib.util.module_from_spec(spec)
sys.modules['launch_loop'] = mod
spec.loader.exec_module(mod)

# Now use:
FileWatcherTrigger = mod.FileWatcherTrigger
_generate_status_html = mod._generate_status_html
```

This works from any working directory — pass an absolute path for the filename.

## Pattern: Lightweight HTTP Server (Webhook)

Python's `http.server` module provides a complete HTTP server with no
external dependencies. Key techniques:

### Daemon-thread server

```python
import http.server, socketserver, threading

class MyHandler(http.server.BaseHTTPRequestHandler):
    _callback = None  # Set externally

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def do_POST(self):
        # Read body
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        # Dispatch
        if self._callback:
            self._callback(body)
        self.send_response(200)
        self.end_headers()

class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

server = ThreadedServer(('', 8080), MyHandler)
t = threading.Thread(target=server.serve_forever, daemon=True)
t.start()
```

### Why `ThreadingMixIn`
- `BaseHTTPServer.HTTPServer` is single-threaded by default.
- `ThreadingMixIn` makes each request a new thread — essential when `do_POST`
  handlers may block on iteration logic.
- `daemon_threads = True` means the whole server dies when the main thread exits.
  No cleanup needed on shutdown.

### Routes
The handler's `self.path` contains the URL path. Parse with `urllib.parse`:

```python
import urllib.parse
parsed = urllib.parse.urlparse(self.path)
if parsed.path == '/webhook':
    # handle webhook
elif parsed.path == '/health':
    # handle health check
```

## Pattern: File Watcher with os.stat() Polling

No inotify, no pyinotify, no watchdog. Pure stdlib:

```python
import pathlib, os, time

class FileWatcher:
    def __init__(self, path: str):
        self.path = path
        self._last_state: dict[str, float] | None = None

    def _scan(self) -> dict[str, float]:
        """Return {absolute_path: mtime} for all file descendants."""
        state = {}
        p = pathlib.Path(self.path)
        if p.is_file():
            state[self.path] = p.stat().st_mtime
        elif p.is_dir():
            for child in sorted(p.rglob('*')):
                if child.is_file():
                    state[str(child)] = child.stat().st_mtime
        return state

    def check(self) -> bool:
        current = self._scan()
        if self._last_state is None:
            self._last_state = current
            return True  # Initial = trigger
        for path, mtime in current.items():
            old = self._last_state.get(path)
            if old is None or abs(mtime - old) > 0.01:
                self._last_state = current
                return True
        self._last_state = current
        return False
```

### Sub-second precision
Use `abs(mtime - old) > 0.01` instead of `!=` because `os.stat().st_mtime`
may have sub-second precision variations on some filesystems.

### Watch a single file vs directory
- Single file: pass the file path, `_scan` returns one entry
- Directory: pass the dir path, `_scan` uses `rglob('*')` recursively

## Pattern: ETA Tracker

Track per-task-type average duration for bounded loops:

```python
class ETATracker:
    def __init__(self):
        self._totals: dict[str, float] = {}
        self._counts: dict[str, int] = {}

    def record(self, task_type: str, duration_s: float):
        self._totals[task_type] = self._totals.get(task_type, 0) + duration_s
        self._counts[task_type] = self._counts.get(task_type, 0) + 1

    def avg(self, task_type: str | None = None) -> float:
        if task_type and task_type in self._counts and self._counts[task_type]:
            return self._totals[task_type] / self._counts[task_type]
        total_s = sum(self._totals.values())
        count = sum(self._counts.values())
        return total_s / count if count else 0.0

    def remaining(self, task_type: str, done: int, total: int) -> float:
        if total <= 0 or done >= total:
            return 0.0
        return self.avg(task_type) * (total - done)

    @staticmethod
    def fmt(seconds: float) -> str:
        if seconds <= 0: return 'N/A'
        if seconds >= 3600: return f'{seconds/3600:.1f}h'
        if seconds >= 60: return f'{seconds/60:.0f}m'
        return f'{seconds:.0f}s'
```

## Pattern: Self-Contained HTML Dashboard

Generate a standalone HTML page with inline CSS — no external assets, no
CDN dependencies, no JS framework. Uses Python string formatting with
placeholder replacement.

Key techniques:
- Single `{PLACEHOLDER}` template string — no Jinja/Mako dependency
- All CSS inline — works when opened directly from disk
- Dark theme using `#0d1117` / `#161b22` / `#c9d1d9` palette (GitHub dark)
- Progress bar as flat `<div>` with percentage width
- Error rows highlighted with CSS class

## Pattern: Size-Rotating Log File

Python `logging.handlers.RotatingFileHandler` provides log rotation with
no external dependency:

```python
import logging.handlers

logger = logging.getLogger('mydaemon')
logger.setLevel(logging.DEBUG)
handler = logging.handlers.RotatingFileHandler(
    '/tmp/mydaemon.log',
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=1                # keep one old file
)
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(handler)
```

Use `logging.Logger.log()` for structured logs alongside `print()` for stdout.
