"""Tests for cooldown.py — calc_adaptive_cooldown."""

from __future__ import annotations


from hermes_loop.cooldown import calc_adaptive_cooldown


class TestCalcAdaptiveCooldown:
    """Tests for calc_adaptive_cooldown function."""

    # -----------------------------------------------------------------------
    # Boundary/edge cases
    # -----------------------------------------------------------------------

    def test_zero_duration(self):
        """Zero duration returns min_cooldown."""
        assert calc_adaptive_cooldown(0, min_cooldown=2, max_cooldown=60) == 2

    def test_negative_duration(self):
        """Negative duration is treated as <= 0, returns min_cooldown."""
        assert calc_adaptive_cooldown(-1, min_cooldown=2, max_cooldown=60) == 2

    def test_long_duration(self):
        """300+ seconds (5+ minutes) returns min_cooldown."""
        assert calc_adaptive_cooldown(300, min_cooldown=2, max_cooldown=60) == 2

    def test_very_long_duration(self):
        """600 seconds (10 minutes) returns min_cooldown."""
        assert calc_adaptive_cooldown(600, min_cooldown=2, max_cooldown=60) == 2

    # -----------------------------------------------------------------------
    # Linear interpolation
    # -----------------------------------------------------------------------

    def test_short_duration_high_cooldown(self):
        """Short duration (5s) produces high cooldown near max."""
        # 5/300 = 0.0167 → cooldown = 60 - 0.0167*58 = ~59.0
        result = calc_adaptive_cooldown(5, min_cooldown=2, max_cooldown=60)
        assert 55 <= result <= 60  # Should be close to max

    def test_medium_duration_mid_cooldown(self):
        """Medium duration produces mid-range cooldown."""
        # 60/300 = 0.2 → cooldown = 60 - 0.2*58 = 48.4
        result = calc_adaptive_cooldown(60, min_cooldown=2, max_cooldown=60)
        assert 45 <= result <= 50

    def test_half_duration(self):
        """150s (half of 300) produces mid-range."""
        # 150/300 = 0.5 → cooldown = 60 - 0.5*58 = 31
        result = calc_adaptive_cooldown(150, min_cooldown=2, max_cooldown=60)
        # 31, but clamped if needed
        assert 28 <= result <= 35

    def test_high_duration_low_cooldown(self):
        """250s duration produces low cooldown."""
        # 250/300 = 0.833 → cooldown = 60 - 0.833*58 ≈ 11.7
        result = calc_adaptive_cooldown(250, min_cooldown=2, max_cooldown=60)
        assert 8 <= result <= 15

    # -----------------------------------------------------------------------
    # Custom min/max values
    # -----------------------------------------------------------------------

    def test_custom_min_max(self):
        """Custom min_cooldown and max_cooldown."""
        # 30/300 = 0.1 → cooldown = 120 - 0.1*115 = 108.5 → 108
        result = calc_adaptive_cooldown(30, min_cooldown=5, max_cooldown=120)
        assert 100 <= result <= 120

    def test_custom_min_max_zero_duration(self):
        """Zero duration with custom min/max."""
        assert calc_adaptive_cooldown(0, min_cooldown=10, max_cooldown=300) == 10

    def test_custom_min_max_long_duration(self):
        """Long duration with custom min/max."""
        assert (
            calc_adaptive_cooldown(500, min_cooldown=5, max_cooldown=120) == 5
        )  # 500 >= 300 → min_cooldown

    def test_min_equals_max(self):
        """When min == max, result is that value."""
        result = calc_adaptive_cooldown(30, min_cooldown=15, max_cooldown=15)
        assert result == 15

    # -----------------------------------------------------------------------
    # Clamping
    # -----------------------------------------------------------------------

    def test_result_clamped_at_min(self):
        """Result is never below min_cooldown."""
        result = calc_adaptive_cooldown(0, min_cooldown=3, max_cooldown=10)
        assert result >= 3

    def test_result_clamped_at_max(self):
        """Result is never above max_cooldown."""
        result = calc_adaptive_cooldown(1, min_cooldown=2, max_cooldown=60)
        assert result <= 60

    # -----------------------------------------------------------------------
    # Smooth interpolation property
    # -----------------------------------------------------------------------

    def test_monotonically_decreasing(self):
        """Cooldown decreases monotonically as duration increases.
        Note: duration=0 returns min_cooldown (2), while small positive values
        return near max_cooldown — this is by design (zero = no iteration yet).
        So we start monotonic check at duration=1.
        """
        durations = [1, 10, 30, 60, 120, 180, 240, 299]
        previous = calc_adaptive_cooldown(1, min_cooldown=2, max_cooldown=60)
        for d in durations[1:]:
            cd = calc_adaptive_cooldown(d, min_cooldown=2, max_cooldown=60)
            assert cd <= previous, (
                f"Cooldown increased for duration {d}: " f"{previous} → {cd}"
            )
            previous = cd

    def test_no_discontinuities(self):
        """No large jumps in cooldown for small duration changes.
        Note: duration=0 returns min_cooldown (2), duration=1 returns ~59.
        This is not a discontinuity — zero means 'no iteration yet' (min delay).
        We check from duration=1 onward for the smooth interpolation.
        """
        results = [
            calc_adaptive_cooldown(d, min_cooldown=2, max_cooldown=60)
            for d in range(1, 301)
        ]
        for i in range(1, len(results)):
            diff = abs(results[i] - results[i - 1])
            assert diff <= 1, (
                f"Discontinuity at duration {i}: " f"{results[i-1]} → {results[i]}"
            )

    # -----------------------------------------------------------------------
    # Float precision
    # -----------------------------------------------------------------------

    def test_float_duration(self):
        """Float duration values are handled correctly."""
        result = calc_adaptive_cooldown(0.5, min_cooldown=2, max_cooldown=60)
        # Very short duration → near max_cooldown
        assert 55 <= result <= 60

    def test_float_duration_near_boundary(self):
        """Float duration near 300s boundary."""
        result = calc_adaptive_cooldown(299.9, min_cooldown=2, max_cooldown=60)
        assert result >= 2

    # -----------------------------------------------------------------------
    # Return type
    # -----------------------------------------------------------------------

    def test_returns_int(self):
        """Result is always an int."""
        result = calc_adaptive_cooldown(30, min_cooldown=2, max_cooldown=60)
        assert isinstance(result, int)

    def test_returns_int_for_float_inputs(self):
        """Result is int even with float parameters."""
        result = calc_adaptive_cooldown(30.5, min_cooldown=2.0, max_cooldown=60.0)
        assert isinstance(result, int)

    # -----------------------------------------------------------------------
    # Realistic scenarios
    # -----------------------------------------------------------------------

    def test_fast_iteration(self):
        """Fast iteration (< 30s) gets high cooldown."""
        cooldown = calc_adaptive_cooldown(15)
        assert cooldown > 50

    def test_normal_iteration(self):
        """Normal iteration (~60s) gets moderate cooldown."""
        cooldown = calc_adaptive_cooldown(60)
        assert 5 < cooldown < 55

    def test_slow_iteration(self):
        """Slow iteration (> 5min) gets min cooldown."""
        cooldown = calc_adaptive_cooldown(350)
        assert cooldown == 2

    def test_one_minute_default(self):
        """1 minute with defaults."""
        c = calc_adaptive_cooldown(60)
        assert isinstance(c, int)
        assert 2 <= c <= 60

    def test_30_seconds_interpolated(self):
        """30 seconds produces interpolated value."""
        result = calc_adaptive_cooldown(30, min_cooldown=2, max_cooldown=60)
        # 30/300 = 0.1 → 60 - 0.1*58 = 54.2 → 54
        assert 50 <= result <= 58
