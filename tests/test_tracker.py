"""Tests for tracker.py — ETATracker class."""

from __future__ import annotations


from hermes_loop.tracker import ETATracker

# ===================================================================
# ETATracker tests
# ===================================================================


class TestETATrackerInit:
    """Tests for ETATracker initialization."""

    def test_initial_state(self):
        """New tracker has empty type tracking."""
        tracker = ETATracker()
        assert tracker._type_totals == {}
        assert tracker._type_counts == {}
        assert tracker.avg_duration() == 0.0


class TestETATrackerRecordIteration:
    """Tests for ETATracker.record_iteration."""

    def test_record_single(self):
        """Record one iteration updates counts and totals."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        assert tracker._type_totals["feature"] == 30.0
        assert tracker._type_counts["feature"] == 1

    def test_record_multiple_same_type(self):
        """Multiple records for same type accumulate."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        tracker.record_iteration("feature", 45.0)
        assert tracker._type_totals["feature"] == 75.0
        assert tracker._type_counts["feature"] == 2

    def test_record_multiple_types(self):
        """Multiple task types tracked independently."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        tracker.record_iteration("bugfix", 60.0)
        assert tracker._type_totals["feature"] == 30.0
        assert tracker._type_counts["feature"] == 1
        assert tracker._type_totals["bugfix"] == 60.0
        assert tracker._type_counts["bugfix"] == 1

    def test_record_zero_duration(self):
        """Zero duration is recorded correctly."""
        tracker = ETATracker()
        tracker.record_iteration("test", 0.0)
        assert tracker._type_totals["test"] == 0.0
        assert tracker._type_counts["test"] == 1

    def test_record_float_duration(self):
        """Float duration is stored."""
        tracker = ETATracker()
        tracker.record_iteration("test", 12.5)
        assert tracker._type_totals["test"] == 12.5


class TestETATrackerAvgDuration:
    """Tests for ETATracker.avg_duration."""

    def test_avg_no_data(self):
        """No data returns 0.0."""
        tracker = ETATracker()
        assert tracker.avg_duration() == 0.0

    def test_avg_no_type_returns_overall(self):
        """No type specified returns overall average."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        tracker.record_iteration("bugfix", 50.0)
        assert tracker.avg_duration() == 40.0  # (30+50)/2

    def test_avg_specific_type(self):
        """Specific type returns its average."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        tracker.record_iteration("feature", 50.0)
        tracker.record_iteration("bugfix", 100.0)
        assert tracker.avg_duration("feature") == 40.0

    def test_avg_unknown_type(self):
        """Unknown type falls back to overall average."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        tracker.record_iteration("feature", 50.0)
        # fallback to overall
        assert tracker.avg_duration("unknown_type") == 40.0

    def test_avg_unknown_type_no_data(self):
        """Unknown type with no data at all returns 0.0."""
        tracker = ETATracker()
        assert tracker.avg_duration("unknown_type") == 0.0

    def test_avg_none_type(self):
        """None type returns overall average."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        assert tracker.avg_duration(None) == 30.0

    def test_avg_multiple_records_rounding(self):
        """Overall average is rounded to 1 decimal place."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 10)
        tracker.record_iteration("feature", 11)
        tracker.record_iteration("feature", 12)
        # (10+11+12)/3 = 11.0
        assert tracker.avg_duration() == 11.0

    def test_avg_single_record(self):
        """Single record returns its duration."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 42.5)
        assert tracker.avg_duration("feature") == 42.5


class TestETATrackerEstimateRemaining:
    """Tests for ETATracker.estimate_remaining."""

    def test_estimate_no_records(self):
        """No records estimates 0.0."""
        tracker = ETATracker()
        assert tracker.estimate_remaining("feature", 0, 10) == 0.0

    def test_estimate_simple(self):
        """Basic estimate based on average duration."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        # avg=30, remaining=10-5=5 → 30*5=150
        assert tracker.estimate_remaining("feature", 5, 10) == 150.0

    def test_estimate_zero_max_iterations(self):
        """Zero max iterations returns 0.0."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        assert tracker.estimate_remaining("feature", 0, 0) == 0.0

    def test_estimate_negative_max_iterations(self):
        """Negative max iterations returns 0.0."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        assert tracker.estimate_remaining("feature", 0, -1) == 0.0

    def test_estimate_zero_remaining(self):
        """No remaining iterations returns 0.0."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        assert tracker.estimate_remaining("feature", 10, 10) == 0.0

    def test_estimate_negative_remaining(self):
        """More iterations done than max returns 0.0."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        assert tracker.estimate_remaining("feature", 15, 10) == 0.0

    def test_estimate_uses_type_avg(self):
        """Estimate uses specific type average, not overall."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 10.0)
        tracker.record_iteration("bugfix", 100.0)
        # feature avg=10, remaining=5 → 50.0
        assert tracker.estimate_remaining("feature", 5, 10) == 50.0

    def test_estimate_rounding(self):
        """Estimate is rounded to 1 decimal place."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 33.0)
        # avg=33, remaining=3 → 99.0
        assert tracker.estimate_remaining("feature", 0, 3) == 99.0


class TestETATrackerFormatEta:
    """Tests for ETATracker.format_eta."""

    def test_zero_seconds(self):
        """Zero seconds returns 'N/A'."""
        tracker = ETATracker()
        assert tracker.format_eta(0) == "N/A"

    def test_negative_seconds(self):
        """Negative seconds returns 'N/A'."""
        tracker = ETATracker()
        assert tracker.format_eta(-5) == "N/A"

    def test_seconds_only(self):
        """Under 60 seconds returns seconds format."""
        tracker = ETATracker()
        assert tracker.format_eta(45) == "45s"

    def test_single_second(self):
        """1 second returns '1s'."""
        tracker = ETATracker()
        assert tracker.format_eta(1) == "1s"

    def test_minutes(self):
        """60-3599 seconds returns minutes format."""
        tracker = ETATracker()
        assert tracker.format_eta(120) == "2m"
        assert tracker.format_eta(3600) == "1.0h (60m)"

    def test_exactly_one_hour(self):
        """Exactly 3600 seconds."""
        tracker = ETATracker()
        assert tracker.format_eta(3600) == "1.0h (60m)"

    def test_hours_and_minutes(self):
        """Seconds are formatted as hours with minutes in parens."""
        tracker = ETATracker()
        assert tracker.format_eta(5400) == "1.5h (90m)"
        result = tracker.format_eta(7200)
        assert "2.0h" in result
        assert "(120m)" in result

    def test_boundary_seconds_59(self):
        """59 seconds returns seconds format."""
        tracker = ETATracker()
        assert tracker.format_eta(59) == "59s"

    def test_boundary_minutes_60(self):
        """60 seconds returns minutes format."""
        tracker = ETATracker()
        assert tracker.format_eta(60) == "1m"

    def test_boundary_minutes_3599(self):
        """3599 seconds: 3599/60=59.98 rounds to 60m with :.0f."""
        tracker = ETATracker()
        assert tracker.format_eta(3599) == "60m"

    def test_hours_decimal(self):
        """Hours format with one decimal place."""
        tracker = ETATracker()
        result = tracker.format_eta(3660)
        assert len(result) > 0


class TestETATrackerToDict:
    """Tests for ETATracker.to_dict."""

    def test_empty(self):
        """Empty tracker returns empty dict with 0 overall avg."""
        tracker = ETATracker()
        result = tracker.to_dict()
        assert result == {"per_type": {}, "overall_avg": 0.0}

    def test_single_type(self):
        """Single type with records."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        tracker.record_iteration("feature", 50.0)
        result = tracker.to_dict()
        assert "feature" in result["per_type"]
        assert result["per_type"]["feature"]["avg"] == 40.0
        assert result["per_type"]["feature"]["count"] == 2
        assert result["overall_avg"] == 40.0

    def test_multiple_types(self):
        """Multiple types all appear."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        tracker.record_iteration("bugfix", 60.0)
        result = tracker.to_dict()
        assert "feature" in result["per_type"]
        assert "bugfix" in result["per_type"]
        assert result["per_type"]["feature"]["avg"] == 30.0
        assert result["per_type"]["feature"]["count"] == 1
        assert result["per_type"]["bugfix"]["avg"] == 60.0
        assert result["per_type"]["bugfix"]["count"] == 1
        assert result["overall_avg"] == 45.0

    def test_dict_independence(self):
        """to_dict returns a new dict, not a reference."""
        tracker = ETATracker()
        tracker.record_iteration("feature", 30.0)
        d1 = tracker.to_dict()
        tracker.record_iteration("bugfix", 60.0)
        d2 = tracker.to_dict()
        # d1 should NOT have 'bugfix' type
        assert "bugfix" not in d1["per_type"]
        assert "bugfix" in d2["per_type"]
        # d1 and d2 are different objects
        assert d1 is not d2
