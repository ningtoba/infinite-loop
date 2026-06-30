"""Tests for omp_loop.system_utils — /proc-based CPU/memory tracking."""

from unittest.mock import mock_open, patch

import pytest

from omp_loop.system_utils import get_system_usage, get_system_usage_diff


class TestGetSystemUsage:
    def test_returns_dict_with_defaults_when_no_proc(self):
        """get_system_usage returns a dict even when /proc files are absent."""
        with patch("builtins.open", side_effect=FileNotFoundError("no /proc")):
            result = get_system_usage()
            assert isinstance(result, dict)

    def test_reads_memory_from_status(self):
        """get_system_usage parses VmRSS, VmSize, VmPeak from /proc/pid/status."""
        status_content = "Name:\tpython\nVmPeak:\t200000 kB\nVmSize:\t180000 kB\nVmRSS:\t50000 kB\nThreads:\t4\n"
        with patch("builtins.open", mock_open(read_data=status_content)):
            result = get_system_usage()
            assert result.get("memory_rss_mb") == pytest.approx(50000 / 1024, rel=0.01)
            assert result.get("memory_vms_mb") == pytest.approx(180000 / 1024, rel=0.01)
            assert result.get("memory_peak_mb") == pytest.approx(200000 / 1024, rel=0.01)

    def test_reads_total_ram_from_meminfo(self):
        """get_system_usage parses MemTotal to compute memory_percent."""
        status_content = "VmRSS:\t50000 kB\n"
        meminfo_content = "MemTotal:\t8000000 kB\nMemFree:\t4000000 kB\n"

        with patch("builtins.open") as mock_file:
            mock_file.side_effect = [
                mock_open(read_data=status_content).return_value,
                mock_open(read_data=meminfo_content).return_value,
                mock_open(read_data="").return_value,
            ]
            result = get_system_usage()
            assert "memory_percent" in result
            assert 0 < result["memory_percent"] < 1.0

    def test_reads_cpu_ticks_from_stat(self):
        """get_system_usage parses utime/stime from /proc/pid/stat."""
        # Mock the /proc/pid/stat file content
        stat_content = "12345 (python) S 1 2 3 4 5 6 7 8 9 10 11 100 200 13 14 15 16 17 18 19 20\n"

        # Use patch_open to return specific data based on file path pattern
        handle_status = mock_open(read_data="VmRSS:\t50000 kB\n").return_value
        handle_meminfo = mock_open(read_data="").return_value
        handle_stat = mock_open(read_data=stat_content).return_value

        def side_effect(*args):
            sfile = str(args[0])
            if "status" in sfile:
                return handle_status
            if "meminfo" in sfile:
                return handle_meminfo
            if "stat" in sfile:
                return handle_stat
            return mock_open(read_data="").return_value

        with patch("builtins.open", side_effect=side_effect):
            result = get_system_usage()
        assert "cpu_ticks_used" in result, f"Got keys: {list(result.keys())}"
        assert result["cpu_ticks_used"] == 111  # fields[11]=11 + fields[12]=100
        assert result["cpu_seconds"] > 0

    def test_partial_data_does_not_crash(self):
        """get_system_usage handles partial /proc data gracefully."""
        status_content = "Name:\tpython\nThreads:\t4\n"
        with patch("builtins.open", mock_open(read_data=status_content)):
            result = get_system_usage()
            assert isinstance(result, dict)

    def test_malformed_stat_does_not_crash(self):
        """get_system_usage handles malformed /proc/pid/stat gracefully."""
        status_content = "VmRSS:\t50000 kB\n"
        stat_content = "12345 (python) S\n"

        with patch("builtins.open") as mock_file:
            mock_file.side_effect = [
                mock_open(read_data=status_content).return_value,
                mock_open(read_data="").return_value,
                mock_open(read_data=stat_content).return_value,
            ]
            result = get_system_usage()
            assert isinstance(result, dict)


class TestGetSystemUsageDiff:
    def test_empty_before_returns_empty_dict(self):
        """get_system_usage_diff returns empty dict when before is empty (falsy)."""
        result = get_system_usage_diff({}, {"cpu_seconds": 1.0})
        assert result == {}

    def test_with_before_and_after_diff(self):
        """get_system_usage_diff computes diff when both before and after have cpu_seconds."""
        result = get_system_usage_diff({"cpu_seconds": 10.0}, {"cpu_seconds": 15.5, "memory_rss_mb": 100.0})
        assert result["cpu_seconds_used"] == pytest.approx(5.5, rel=0.01)

    def test_computes_diff_correctly(self):
        """get_system_usage_diff computes cpu_seconds_used."""
        before = {"cpu_seconds": 10.0, "memory_rss_mb": 100.0}
        after = {
            "cpu_seconds": 15.5,
            "memory_rss_mb": 120.0,
            "memory_vms_mb": 200.0,
            "memory_percent": 0.05,
            "memory_peak_mb": 130.0,
        }
        result = get_system_usage_diff(before, after)
        assert result["cpu_seconds_used"] == pytest.approx(5.5, rel=0.01)
        assert result["memory_rss_mb"] == 120.0
        assert result["memory_vms_mb"] == 200.0
        assert result["memory_percent"] == 0.05
        assert result["memory_peak_mb"] == 130.0

    def test_both_none(self):
        """Both before and after are empty."""
        assert get_system_usage_diff({}, {}) == {}

    def test_includes_all_after_fields(self):
        """All fields from after snapshot are included in diff."""
        after = {"memory_rss_mb": 50.0, "memory_vms_mb": 100.0, "memory_percent": 0.02, "memory_peak_mb": 60.0}
        result = get_system_usage_diff({"cpu_seconds": 5.0}, after)
        for key in ("memory_rss_mb", "memory_vms_mb", "memory_percent", "memory_peak_mb"):
            assert key in result
