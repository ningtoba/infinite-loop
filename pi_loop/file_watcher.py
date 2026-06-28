"""File watcher — poll a directory for changes and trigger iterations."""

import contextlib
import pathlib


class FileWatcherTrigger:
    """Poll a directory/file for modifications and trigger on change.

    Uses os.stat() polling — no external dependencies. Scans mtime of
    all files in the watched directory and triggers an iteration when
    any mtime changes.
    """

    def __init__(self, path: str, poll_interval: float = 5.0):
        self.path = path
        self.poll_interval = poll_interval
        self._last_state: dict[str, float] | None = None

    def _scan(self) -> dict[str, float]:
        """Return {filename: mtime} for all files under the watched path."""
        state = {}
        p = pathlib.Path(self.path)
        if p.is_file():
            with contextlib.suppress(OSError):
                state[self.path] = p.stat().st_mtime
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    with contextlib.suppress(OSError):
                        state[str(child)] = child.stat().st_mtime
        return state

    def check_change(self) -> bool:
        """Return True if any file has changed since last check."""
        current = self._scan()
        if self._last_state is None:
            self._last_state = current
            return True  # Initial scan counts as a "change"
        for path, mtime in current.items():
            old = self._last_state.get(path)
            if old is None or abs(mtime - old) > 0.01:
                self._last_state = current
                return True
        self._last_state = current
        return False

    def format_changed(self) -> str:
        """Human-readable list of changed files since last scan."""
        current = self._scan()
        changed = []
        for path, mtime in current.items():
            old = self._last_state.get(path)
            if old is None or abs(mtime - old) > 0.01:
                changed.append(path)
        self._last_state = current
        return ", ".join(changed[:10]) if changed else ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "poll_interval": self.poll_interval,
            "files_tracked": len(self._scan()),
        }
