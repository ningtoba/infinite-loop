"""Tests for system_utils.py — get_system_usage and get_system_usage_diff."""

from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

import pytest

from hermes_loop.system_utils import get_system_usage, get_system_usage_diff

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_status_content(
    vm_rss_kb: int = 10000,
    vm_size_kb: int = 50000,
    vm_peak_kb: int = 60000,
) -> str:
    """Build a fake /proc/pid/status file content."""
    return (
        "Name:   python\n"
        "Umask:  0022\n"
        "State:  S (sleeping)\n"
        f"VmPeak: {vm_peak_kb} kB\n"
        f"VmSize: {vm_size_kb} kB\n"
        f"VmRSS:  {vm_rss_kb} kB\n"
        "VmData: 20000 kB\n"
        "Threads: 1\n"
    )


def _make_meminfo_content(total_kb: int = 16000000) -> str:
    """Build a fake /proc/meminfo file content."""
    return (
        f"MemTotal:     {total_kb} kB\n"
        "MemFree:      8000000 kB\n"
        "MemAvailable: 9000000 kB\n"
        "Buffers:       500000 kB\n"
    )


def _make_stat_content(utime: int = 500, stime: int = 300) -> str:
    """Build a fake /proc/pid/stat file content for parsing.

    The source code does:
        parts = stat_data.split(')')     # split on first ')'
        fields = parts[1].strip().split()
        utime = int(fields[11])          # index 11 in parts[1] split
        stime = int(fields[12])

    Since parts[0] contains "pid (comm", parts[1] contains everything after.
    The fields in parts[1] start with state (original index 2), so we need
    to place utime/stime at original indices 13/14 → parts[1] indices 11/12.
    """
    orig = ["0"] * 24
    orig[0] = "12345"
    orig[1] = "(python)"
    orig[2] = "S"
    # Fill indices 3..12 with zeros (these become parts[1] indices 1..10)
    orig[13] = str(utime)  # → parts[1][11]
    orig[14] = str(stime)  # → parts[1][12]
    return " ".join(orig)


_RAISE = object()  # sentinel: raise FileNotFoundError for this file


def _mock_file_side_effect(
    status: str | object | None = _RAISE,
    meminfo: str | object | None = _RAISE,
    stat: str | object | None = _RAISE,
):
    """Return a side_effect function that serves different /proc files.

    Pass _RAISE (the default, meaning 'raise') to simulate FileNotFoundError.
    Pass a string to use that exact content.
    """
    status_content = _make_status_content() if status is _RAISE else status
    meminfo_content = _make_meminfo_content() if meminfo is _RAISE else meminfo
    stat_content = _make_stat_content() if stat is _RAISE else stat

    def side_effect(path, *args, **kwargs):
        if "status" in str(path):
            if status is _RAISE:
                raise FileNotFoundError("No such file")
            return mock_open(read_data=status_content if status else "").return_value  # type: ignore[arg-type]
        elif "meminfo" in str(path):
            if meminfo is _RAISE:
                raise FileNotFoundError("No such file")
            return mock_open(read_data=meminfo_content if meminfo else "").return_value  # type: ignore[arg-type]
        elif "stat" in str(path):
            if stat is _RAISE:
                raise FileNotFoundError("No such file")
            return mock_open(read_data=stat_content if stat else "").return_value  # type: ignore[arg-type]
        return mock_open(read_data="").return_value

    return side_effect


# ---------------------------------------------------------------------------
# get_system_usage tests
# ---------------------------------------------------------------------------


class TestGetSystemUsage:
    """Tests for get_system_usage()."""

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_basic_memory_parsing(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """Parse VmRSS, VmSize, VmPeak from /proc/pid/status."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        mock_file.side_effect = _mock_file_side_effect(
            status=_make_status_content(
                vm_rss_kb=10240, vm_size_kb=51200, vm_peak_kb=65536
            ),
        )

        result = get_system_usage()

        assert "memory_rss_mb" in result
        assert result["memory_rss_mb"] == pytest.approx(10.0, rel=0.01)  # 10240/1024
        assert "memory_vms_mb" in result
        assert result["memory_vms_mb"] == pytest.approx(50.0, rel=0.01)  # 51200/1024
        assert "memory_peak_mb" in result
        assert result["memory_peak_mb"] == pytest.approx(64.0, rel=0.01)  # 65536/1024

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_memory_percent_computed(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """memory_percent is computed as rss_kb / total_kb."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        mock_file.side_effect = _mock_file_side_effect(
            status=_make_status_content(vm_rss_kb=8192),
            meminfo=_make_meminfo_content(total_kb=16000000),
        )

        result = get_system_usage()
        assert "memory_percent" in result
        # round(x, 4) where x = 8192/16000000 = 0.000512 → 0.0005
        assert result["memory_percent"] == 0.0005

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_cpu_parsing(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """Parse CPU utime+stime from /proc/pid/stat."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        # Only stat file is provided; status and meminfo raise by default (sentinel)
        mock_file.side_effect = _mock_file_side_effect(
            stat=_make_stat_content(utime=100, stime=50),
        )

        result = get_system_usage()
        assert "cpu_ticks_used" in result
        assert result["cpu_ticks_used"] == 150
        assert "cpu_seconds" in result
        # With mock sysconf returning 100, 150 ticks = 1.5 seconds
        assert result["cpu_seconds"] == pytest.approx(1.5, rel=0.01)

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_status_file_not_found(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """FileNotFoundError on /proc/pid/status is handled gracefully."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        # status raises (sentinel), but meminfo and stat have default content
        mock_file.side_effect = _mock_file_side_effect(
            status=_RAISE,  # explicitly raise for status
            meminfo=_make_meminfo_content(),
            stat=_make_stat_content(),
        )

        result = get_system_usage()
        assert "memory_rss_mb" not in result
        # CPU still works
        assert "cpu_ticks_used" in result

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_meminfo_file_not_found(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """FileNotFoundError on /proc/meminfo is handled gracefully."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        # meminfo raises; status and stat have default content
        mock_file.side_effect = _mock_file_side_effect(
            status=_make_status_content(),
            meminfo=_RAISE,
            stat=_make_stat_content(),
        )

        result = get_system_usage()
        assert "memory_rss_mb" in result
        assert "memory_percent" not in result

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_stat_file_not_found(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """FileNotFoundError on /proc/pid/stat is handled gracefully."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        # stat raises; status and meminfo have default content
        mock_file.side_effect = _mock_file_side_effect(
            status=_make_status_content(),
            meminfo=_make_meminfo_content(),
            stat=_RAISE,
        )

        result = get_system_usage()
        assert "memory_rss_mb" in result
        assert "cpu_ticks_used" not in result

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_malformed_status_line(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """Malformed lines in /proc/pid/status (missing kB value) are ignored."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        status_content = (
            "Name:   python\n"
            "VmRSS:\n"  # No kB value
            "VmSize:  50000 kB\n"
        )
        mock_file.side_effect = _mock_file_side_effect(status=status_content)

        result = get_system_usage()
        assert "memory_rss_mb" not in result
        assert "memory_vms_mb" in result

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_all_files_fail_returns_empty(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """When all /proc files raise errors, result is empty dict."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        mock_file.side_effect = FileNotFoundError("No such file")

        result = get_system_usage()
        assert result == {}

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_io_error_on_status(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """IOError on /proc reads is handled gracefully."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100

        def io_error_side(path, *args, **kwargs):
            if "status" in str(path):
                raise IOError("Permission denied")
            # Return default content for all other paths
            return _mock_file_side_effect(
                status=_make_status_content(),
                meminfo=_make_meminfo_content(),
                stat=_make_stat_content(),
            )(path, *args, **kwargs)

        mock_file.side_effect = io_error_side

        result = get_system_usage()
        assert "memory_rss_mb" not in result
        assert "cpu_ticks_used" in result

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_value_error_on_int_parse(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """ValueError when parsing int from /proc is handled gracefully."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        status_content = "Name:   python\nVmRSS:  not_a_number kB\n"
        mock_file.side_effect = _mock_file_side_effect(status=status_content)

        result = get_system_usage()
        assert "memory_rss_mb" not in result

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_all_keys_present_normal(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """Returned dict has expected keys in normal case."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        mock_file.side_effect = _mock_file_side_effect(
            status=_make_status_content(
                vm_rss_kb=8192, vm_size_kb=65536, vm_peak_kb=131072
            ),
            meminfo=_make_meminfo_content(total_kb=16000000),
            stat=_make_stat_content(utime=200, stime=100),
        )

        result = get_system_usage()
        expected_keys = {
            "memory_rss_mb",
            "memory_vms_mb",
            "memory_peak_mb",
            "memory_percent",
            "cpu_ticks_used",
            "cpu_seconds",
        }
        assert set(result.keys()) == expected_keys

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_zero_total_mem_skips_percent(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """If MemTotal is 0, no memory_percent is added."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        mock_file.side_effect = _mock_file_side_effect(
            meminfo=_make_meminfo_content(total_kb=0),
        )

        result = get_system_usage()
        assert "memory_percent" not in result

    @patch("hermes_loop.system_utils.os.sysconf")
    @patch("hermes_loop.system_utils.os.getpid")
    @patch("builtins.open")
    def test_partial_status_only(
        self, mock_file: MagicMock, mock_getpid: MagicMock, mock_sysconf: MagicMock
    ):
        """Only VmRSS present, VmSize and VmPeak missing."""
        mock_getpid.return_value = 12345
        mock_sysconf.return_value = 100
        status_content = "Name:   python\nVmRSS:  4096 kB\n"
        mock_file.side_effect = _mock_file_side_effect(status=status_content)

        result = get_system_usage()
        assert result.get("memory_rss_mb") == pytest.approx(4.0, rel=0.01)
        assert "memory_vms_mb" not in result
        assert "memory_peak_mb" not in result


# ---------------------------------------------------------------------------
# get_system_usage_diff tests
# ---------------------------------------------------------------------------


class TestGetSystemUsageDiff:
    """Tests for get_system_usage_diff()."""

    def test_basic_diff(self):
        """Compute CPU seconds diff between before and after."""
        before = {"cpu_seconds": 10.0, "memory_rss_mb": 50.0}
        after = {
            "cpu_seconds": 15.5,
            "memory_rss_mb": 60.0,
            "memory_vms_mb": 200.0,
        }
        result = get_system_usage_diff(before, after)

        assert result["cpu_seconds_used"] == pytest.approx(5.5, rel=0.001)
        assert result["memory_rss_mb"] == 60.0
        assert result["memory_vms_mb"] == 200.0

    def test_diff_includes_all_keys(self):
        """All expected keys in the diff after dict."""
        before = {"cpu_seconds": 1.0}
        after = {
            "cpu_seconds": 3.0,
            "memory_rss_mb": 45.0,
            "memory_vms_mb": 128.0,
            "memory_percent": 0.003,
            "memory_peak_mb": 100.0,
        }
        result = get_system_usage_diff(before, after)
        assert result["memory_percent"] == 0.003
        assert result["memory_peak_mb"] == 100.0
        assert result["memory_rss_mb"] == 45.0
        assert result["memory_vms_mb"] == 128.0

    def test_before_is_empty_dict(self):
        """When before is empty (falsy), returns empty dict."""
        before: dict = {}
        after = {
            "cpu_seconds": 5.0,
            "memory_rss_mb": 30.0,
            "memory_vms_mb": 128.0,
        }
        result = get_system_usage_diff(before, after)
        # Empty dict is falsy, so the if before and after: clause is False
        assert result == {}

    def test_before_is_none(self):
        """When before is None, returns empty dict."""
        result = get_system_usage_diff({}, {})  # type: ignore[arg-type]
        assert result == {}

    def test_after_is_none(self):
        """When after is None, returns empty dict."""
        result = get_system_usage_diff({}, {})  # type: ignore[arg-type]
        assert result == {}

    def test_both_empty(self):
        """Both empty returns empty dict."""
        result = get_system_usage_diff({}, {})
        assert result == {}

    def test_missing_cpu_seconds_defaults_to_zero(self):
        """If before lacks cpu_seconds, defaults to 0."""
        before = {"memory_rss_mb": 50.0}
        after = {"cpu_seconds": 10.0, "memory_rss_mb": 60.0}
        result = get_system_usage_diff(before, after)
        assert result["cpu_seconds_used"] == pytest.approx(10.0, rel=0.001)

    def test_negative_diff_possible(self):
        """CPU seconds diff can be negative if before > after."""
        before = {"cpu_seconds": 100.0}
        after = {"cpu_seconds": 50.0}
        result = get_system_usage_diff(before, after)
        assert result["cpu_seconds_used"] == pytest.approx(-50.0, rel=0.001)

    def test_missing_after_keys_default_to_zero(self):
        """Missing keys in after default to 0 in the diff."""
        before = {"cpu_seconds": 5.0}
        after = {"cpu_seconds": 10.0}
        result = get_system_usage_diff(before, after)
        assert result["cpu_seconds_used"] == pytest.approx(5.0, rel=0.001)
        assert result["memory_rss_mb"] == 0
        assert result["memory_vms_mb"] == 0

    def test_no_memory_before_after(self):
        """Diff with only CPU keys works fine."""
        before = {"cpu_seconds": 2.0}
        after = {"cpu_seconds": 4.0}
        result = get_system_usage_diff(before, after)
        assert result["cpu_seconds_used"] == pytest.approx(2.0, rel=0.001)
        assert "memory_rss_mb" in result
        assert result["memory_rss_mb"] == 0

    def test_rounding_to_three_decimals(self):
        """cpu_seconds_used is rounded to 3 decimal places."""
        before = {"cpu_seconds": 1.1234}
        after = {"cpu_seconds": 3.4567}
        result = get_system_usage_diff(before, after)
        assert result["cpu_seconds_used"] == pytest.approx(2.333, rel=0.001)
