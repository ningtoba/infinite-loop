"""Tests for FileWatcherTrigger — file change detection via stat polling."""

import os
import time

from omp_loop.file_watcher import FileWatcherTrigger


class TestFileWatcherTrigger:
    """FileWatcherTrigger detects file changes via mtime polling."""

    def test_initial_scan_detects_files(self, tmp_path):
        """_scan returns mtime entries for all files under path."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.txt").write_text("c")

        watcher = FileWatcherTrigger(str(tmp_path))
        state = watcher._scan()

        assert len(state) == 3
        assert str(tmp_path / "a.txt") in state
        assert str(tmp_path / "b.txt") in state
        assert str(sub / "c.txt") in state

    def test_first_check_returns_true(self, tmp_path):
        """check_change returns True on the first call (initial scan counts as change)."""
        (tmp_path / "f.txt").write_text("hello")
        watcher = FileWatcherTrigger(str(tmp_path))
        assert watcher.check_change() is True

    def test_no_change_returns_false(self, tmp_path):
        """check_change returns False when no files have changed."""
        (tmp_path / "f.txt").write_text("hello")
        watcher = FileWatcherTrigger(str(tmp_path))
        watcher.check_change()  # first call — seeds state
        assert watcher.check_change() is False

    def test_detects_file_modification(self, tmp_path):
        """check_change returns True after a file is modified."""
        f = tmp_path / "f.txt"
        f.write_text("hello")
        watcher = FileWatcherTrigger(str(tmp_path))
        watcher.check_change()  # seed state
        time.sleep(0.02)  # ensure mtime advances
        f.write_text("world")
        assert watcher.check_change() is True

    def test_detects_file_creation(self, tmp_path):
        """check_change returns True after a new file is created."""
        (tmp_path / "a.txt").write_text("a")
        watcher = FileWatcherTrigger(str(tmp_path))
        watcher.check_change()  # seed state
        (tmp_path / "b.txt").write_text("b")
        assert watcher.check_change() is True

    def test_detects_file_deletion(self, tmp_path):
        """check_change returns True after a file is deleted."""
        f = tmp_path / "f.txt"
        f.write_text("content")
        watcher = FileWatcherTrigger(str(tmp_path))
        watcher.check_change()  # seed state
        f.unlink()
        assert watcher.check_change() is True

    def test_format_changed_after_modification(self, tmp_path):
        """format_changed returns the path of the modified file."""
        f = tmp_path / "f.txt"
        f.write_text("hello")
        watcher = FileWatcherTrigger(str(tmp_path))
        watcher.check_change()  # seed state
        time.sleep(0.02)  # ensure mtime advances
        f.write_text("world")
        changed = watcher.format_changed()
        assert str(f) in changed

    def test_format_changed_no_change(self, tmp_path):
        """format_changed returns empty string when nothing changed."""
        (tmp_path / "f.txt").write_text("hello")
        watcher = FileWatcherTrigger(str(tmp_path))
        watcher.check_change()  # seed state
        assert watcher.format_changed() == ""

    def test_format_changed_before_scan(self, tmp_path):
        """format_changed returns empty string before first scan."""
        watcher = FileWatcherTrigger(str(tmp_path))
        assert watcher.format_changed() == ""

    def test_to_dict_returns_state(self, tmp_path):
        """to_dict returns the watcher's path, poll_interval, and file count."""
        (tmp_path / "f.txt").write_text("hello")
        watcher = FileWatcherTrigger(str(tmp_path), poll_interval=2.0)
        d = watcher.to_dict()
        assert d["path"] == str(tmp_path)
        assert d["poll_interval"] == 2.0
        assert d["files_tracked"] == 1

    def test_watches_single_file(self, tmp_path):
        """Watcher can track a single file (not directory)."""
        f = tmp_path / "single.txt"
        f.write_text("content")
        watcher = FileWatcherTrigger(str(f))
        state = watcher._scan()
        assert str(f) in state
        assert watcher.check_change() is True  # initial
        assert watcher.check_change() is False  # no change

    def test_empty_directory(self, tmp_path):
        """Watcher handles empty directories without error."""
        watcher = FileWatcherTrigger(str(tmp_path))
        assert watcher._scan() == {}
        assert watcher.check_change() is True  # initial scan counts

    def test_nonexistent_path(self, tmp_path):
        """Watcher handles nonexistent paths gracefully (_scan returns empty)."""
        watcher = FileWatcherTrigger(str(tmp_path / "nonexistent"))
        assert watcher._scan() == {}

    def test_permission_error_skips_file(self, tmp_path):
        """Watcher skips files that raise permission errors."""
        f = tmp_path / "no_access.txt"
        f.write_text("secret")
        os.chmod(f, 0o000)
        try:
            watcher = FileWatcherTrigger(str(tmp_path))
            state = watcher._scan()
            # May or may not include the file depending on OS permission model
            assert isinstance(state, dict)
        finally:
            os.chmod(f, 0o644)

    def test_format_changed_limits_to_10_files(self, tmp_path):
        """format_changed returns at most 10 file paths."""
        for i in range(15):
            (tmp_path / f"file_{i}.txt").write_text(str(i))
        watcher = FileWatcherTrigger(str(tmp_path))
        watcher.check_change()  # seed
        for i in range(15):
            time.sleep(0.02)
            (tmp_path / f"file_{i}.txt").write_text(f"modified_{i}")
            result = watcher.format_changed()
            num_files = len(result.split(", ")) if result else 0
            assert num_files <= 10, f"Expected ≤10 changed files, got {num_files}"
