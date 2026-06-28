"""Tests for file_watcher.py — FileWatcherTrigger class."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from hermes_loop.file_watcher import FileWatcherTrigger

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_watch_dir(tmp_path: Path) -> Path:
    """Create a temporary directory to watch."""
    return tmp_path


# ---------------------------------------------------------------------------
# _scan tests
# ---------------------------------------------------------------------------


class TestScan:
    """Tests for FileWatcherTrigger._scan()."""

    def test_scan_single_file(self, tmp_path: Path):
        """_scan returns {path: mtime} for a single file."""
        f = tmp_path / "target.txt"
        f.write_text("hello")
        trigger = FileWatcherTrigger(str(f))
        state = trigger._scan()
        assert str(f) in state
        assert isinstance(state[str(f)], float)
        assert state[str(f)] > 0

    def test_scan_directory_with_files(self, tmp_path: Path):
        """_scan returns {path: mtime} for all files in a directory."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "sub" / "b.txt"
        f1.parent.mkdir(exist_ok=True)
        f2.parent.mkdir(parents=True, exist_ok=True)
        f1.write_text("a")
        f2.write_text("b")

        trigger = FileWatcherTrigger(str(tmp_path))
        state = trigger._scan()

        assert str(f1) in state
        assert str(f2) in state
        assert len(state) == 2

    def test_scan_empty_directory(self, tmp_path: Path):
        """_scan returns empty dict for empty directory."""
        trigger = FileWatcherTrigger(str(tmp_path))
        assert trigger._scan() == {}

    def test_scan_nonexistent_path(self, tmp_path: Path):
        """_scan returns empty dict for nonexistent path."""
        missing = tmp_path / "does_not_exist"
        trigger = FileWatcherTrigger(str(missing))
        assert trigger._scan() == {}

    def test_scan_directory_ignores_subdirs(self, tmp_path: Path):
        """_scan only includes files, not directories."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        f = sub / "file.txt"
        f.write_text("content")

        trigger = FileWatcherTrigger(str(tmp_path))
        state = trigger._scan()

        # Directory itself is not included
        paths = list(state.keys())
        assert all(os.path.isfile(p) for p in paths)
        assert str(f) in state

    def test_scan_oserror_on_file_is_skipped(self, tmp_path: Path, monkeypatch):
        """_scan silently skips files that raise OSError on stat."""
        f = tmp_path / "broken.txt"
        f.write_text("data")

        original_stat = Path.stat

        def broken_stat(self):
            if "broken" in str(self):
                raise OSError("Permission denied")
            return original_stat(self)

        monkeypatch.setattr(Path, "stat", broken_stat)

        trigger = FileWatcherTrigger(str(tmp_path))
        state = trigger._scan()
        assert str(f) not in state

    def test_scan_recursive_subdirectories(self, tmp_path: Path):
        """_scan recurses into nested subdirectories."""
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        f = nested / "deep.txt"
        f.write_text("deep")
        (tmp_path / "root.txt").write_text("root")

        trigger = FileWatcherTrigger(str(tmp_path))
        state = trigger._scan()
        assert str(f) in state
        assert len(state) == 2


# ---------------------------------------------------------------------------
# check_change tests
# ---------------------------------------------------------------------------


class TestCheckChange:
    """Tests for FileWatcherTrigger.check_change()."""

    def test_first_call_returns_true(self, tmp_path: Path):
        """First call to check_change always returns True (initial scan)."""
        (tmp_path / "f.txt").write_text("data")
        trigger = FileWatcherTrigger(str(tmp_path))
        assert trigger.check_change() is True

    def test_no_change_returns_false(self, tmp_path: Path):
        """Second call with no modifications returns False."""
        (tmp_path / "f.txt").write_text("data")
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()  # first call — initial
        assert trigger.check_change() is False

    def test_new_file_detected(self, tmp_path: Path):
        """Adding a new file triggers change."""
        (tmp_path / "a.txt").write_text("a")
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()  # initial scan
        (tmp_path / "b.txt").write_text("b")
        assert trigger.check_change() is True

    def test_modified_file_detected(self, tmp_path: Path):
        """Modifying a file's content triggers change."""
        f = tmp_path / "watch.txt"
        f.write_text("v1")
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()  # initial scan
        time.sleep(0.02)  # ensure mtime changes
        f.write_text("v2")
        assert trigger.check_change() is True

    def test_deleted_file(self, tmp_path: Path):
        """Deleting a watched file is not reported since _scan no longer sees it."""
        f = tmp_path / "gone.txt"
        f.write_text("data")
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()  # initial scan
        f.unlink()
        # After deletion, the file is no longer in _scan results,
        # so check_change returns False (no files to compare)
        assert trigger.check_change() is False

    def test_empty_dir_first_call_true(self, tmp_path: Path):
        """check_change returns True on first call even for empty dir."""
        trigger = FileWatcherTrigger(str(tmp_path))
        assert trigger.check_change() is True

    def test_empty_dir_no_change(self, tmp_path: Path):
        """check_change returns False on second call for empty dir."""
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()
        assert trigger.check_change() is False

    def test_replaces_last_state_on_change(self, tmp_path: Path):
        """check_change updates _last_state after returning True."""
        (tmp_path / "f.txt").write_text("v1")
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()  # initial
        assert trigger._last_state is not None
        old_state = trigger._last_state.copy()
        time.sleep(0.02)
        (tmp_path / "f.txt").write_text("v2")
        assert trigger.check_change() is True  # change detected
        new_state = trigger._last_state
        # _last_state was updated
        assert new_state is not None
        assert new_state != old_state


# ---------------------------------------------------------------------------
# format_changed tests
# ---------------------------------------------------------------------------


class TestFormatChanged:
    """Tests for FileWatcherTrigger.format_changed()."""

    def test_first_call_returns_empty(self, tmp_path: Path):
        """First call to format_changed returns empty string (no previous state)."""
        (tmp_path / "f.txt").write_text("data")
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()  # initialize last_state
        result = trigger.format_changed()
        assert result == ""

    def test_new_file_appears_in_changed(self, tmp_path: Path):
        """New files show up in format_changed."""
        (tmp_path / "a.txt").write_text("a")
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()
        (tmp_path / "b.txt").write_text("b")
        result = trigger.format_changed()
        assert "b.txt" in result

    def test_modified_file_appears_in_changed(self, tmp_path: Path):
        """Modified files show up in format_changed."""
        f = tmp_path / "watch.txt"
        f.write_text("v1")
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()
        time.sleep(0.02)
        f.write_text("v2")
        result = trigger.format_changed()
        assert str(f) in result

    def test_changed_list_limited_to_10(self, tmp_path: Path):
        """format_changed limits output to first 10 changed files."""
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()
        for i in range(15):
            (tmp_path / f"file_{i}.txt").write_text(str(i))
        result = trigger.format_changed()
        assert len(result.split(", ")) == 10

    def test_no_change_returns_empty(self, tmp_path: Path):
        """No changes returns empty string."""
        (tmp_path / "f.txt").write_text("data")
        trigger = FileWatcherTrigger(str(tmp_path))
        trigger.check_change()
        result = trigger.format_changed()
        assert result == ""


# ---------------------------------------------------------------------------
# to_dict tests
# ---------------------------------------------------------------------------


class TestToDict:
    """Tests for FileWatcherTrigger.to_dict()."""

    def test_basic_to_dict(self, tmp_path: Path):
        """to_dict returns config dict with path, poll_interval, files_tracked."""
        (tmp_path / "f.txt").write_text("data")
        trigger = FileWatcherTrigger(str(tmp_path), poll_interval=2.5)
        d = trigger.to_dict()
        assert d["path"] == str(tmp_path)
        assert d["poll_interval"] == 2.5
        assert d["files_tracked"] == 1

    def test_to_dict_empty_dir(self, tmp_path: Path):
        """to_dict returns 0 files_tracked for empty directory."""
        trigger = FileWatcherTrigger(str(tmp_path), poll_interval=10.0)
        d = trigger.to_dict()
        assert d["files_tracked"] == 0
        assert d["poll_interval"] == 10.0

    def test_to_dict_default_poll_interval(self, tmp_path: Path):
        """to_dict shows default poll_interval of 5.0 when not specified."""
        trigger = FileWatcherTrigger(str(tmp_path))
        d = trigger.to_dict()
        assert d["poll_interval"] == 5.0


# ---------------------------------------------------------------------------
# Integration / edge case tests
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end FileWatcherTrigger integration tests."""

    def test_full_lifecycle_single_file(self, tmp_path: Path):
        """Full lifecycle: init → scan → check → format → to_dict on single file."""
        f = tmp_path / "target.txt"
        f.write_text("initial")

        trigger = FileWatcherTrigger(str(f))
        assert trigger.check_change() is True  # initial triggers
        assert trigger.check_change() is False  # no change

        time.sleep(0.02)
        f.write_text("modified")

        # format_changed detects the change
        changed = trigger.format_changed()
        assert str(f) in changed

        # check_change after format_changed: format_changed updates _last_state,
        # so check_change sees no further change
        assert trigger.check_change() is False

        d = trigger.to_dict()
        assert d["path"] == str(f)
        assert d["files_tracked"] == 1

    def test_poll_interval_passed_but_not_used_by_class(self):
        """poll_interval is stored but FileWatcherTrigger doesn't sleep internally."""
        trigger = FileWatcherTrigger("/tmp", poll_interval=60.0)
        assert trigger.poll_interval == 60.0

    def test_symlink_to_file_not_followed(self, tmp_path: Path):
        """Symlinks are NOT followed - rglob returns symlinks, stat works on them."""
        real = tmp_path / "real.txt"
        real.write_text("real")
        link = tmp_path / "link.txt"
        link.symlink_to(real)

        trigger = FileWatcherTrigger(str(tmp_path))
        state = trigger._scan()
        # Symlink itself should appear (it's a file from rglob's perspective)
        assert str(link) in state
        assert str(real) in state
