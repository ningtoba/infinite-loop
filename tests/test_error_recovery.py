"""Tests for omp_loop.error_recovery — automatic error adaptation engine."""

from unittest.mock import patch

from omp_loop.error_recovery import _adapt_to_error, _pick_primary_error, _set_originals


class TestSetOriginals:
    def test_stores_values(self):
        """_set_originals stores baseline values in module globals."""
        _set_originals(session_timeout=300, cooldown=10, use_library=True, workers=3)
        # After set, mitigation calculations use these as baseline
        # Call with no prior mitigations and a timeout error to verify baselines are used
        with (
            patch("omp_loop.error_recovery._ORIGINAL_SESSION_TIMEOUT", 300),
            patch("omp_loop.error_recovery._ORIGINAL_COOLDOWN", 10),
            patch("omp_loop.error_recovery._ORIGINAL_USE_LIBRARY", True),
            patch("omp_loop.error_recovery._ORIGINAL_WORKERS", 3),
        ):
            result = _adapt_to_error(
                error_type="timeout",
                mitigations={
                    "mitigation_level": 0,
                    "timeout_increased": False,
                    "cooldown_elevated": False,
                    "force_subprocess": False,
                    "reduced_workers": False,
                    "last_applied": "",
                    "actions": [],
                },
                consecutive_successes=0,
                error_type_counts={"timeout": 3, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0},
                session_timeout=300,
                cooldown=10,
                cooldown_mode="fixed",
                use_library=True,
                workers=3,
            )
            new_timeout, new_cooldown, new_mode, new_library, new_workers, actions = result
            assert new_timeout == 450  # 300 * 150%


class TestPickPrimaryError:
    def test_picks_highest_severity(self):
        """_pick_primary_error picks highest severity from list."""
        result = _pick_primary_error(["unknown", "network", "timeout"])
        assert result == "timeout"

    def test_heartbeat_is_highest(self):
        """_pick_primary_error returns 'heartbeat' as highest severity."""
        result = _pick_primary_error(["unknown", "timeout", "heartbeat"])
        assert result == "heartbeat"

    def test_single_item(self):
        """_pick_primary_error returns the only item."""
        result = _pick_primary_error(["network"])
        assert result == "network"

    def test_empty_list_raises(self):
        """_pick_primary_error raises ValueError on empty list."""
        import pytest

        with pytest.raises(ValueError):
            _pick_primary_error([])


class TestAdaptToErrorNoError:
    def test_no_error_no_mitigations(self):
        """_adapt_to_error with no error and no prior mitigations returns original params."""
        result = _adapt_to_error(
            error_type=None,
            mitigations={
                "mitigation_level": 0,
                "timeout_increased": False,
                "cooldown_elevated": False,
                "force_subprocess": False,
                "reduced_workers": False,
                "last_applied": "",
                "actions": [],
            },
            consecutive_successes=0,
            error_type_counts={},
            session_timeout=300,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        new_timeout, new_cooldown, new_mode, new_library, new_workers, actions = result
        assert new_timeout == 300
        assert new_cooldown == 10
        assert new_mode == "fixed"
        assert new_library
        assert new_workers == 2
        assert actions == []

    def test_first_success_ramps_down(self):
        """_adapt_to_error with 1st success ramps down slightly."""
        with (
            patch("omp_loop.error_recovery._ORIGINAL_SESSION_TIMEOUT", 300),
            patch("omp_loop.error_recovery._ORIGINAL_COOLDOWN", 10),
        ):
            result = _adapt_to_error(
                error_type=None,
                mitigations={
                    "mitigation_level": 2,
                    "timeout_increased": True,
                    "cooldown_elevated": True,
                    "force_subprocess": True,
                    "reduced_workers": True,
                    "last_applied": "prev",
                    "actions": [],
                },
                consecutive_successes=1,
                error_type_counts={},
                session_timeout=500,
                cooldown=60,
                cooldown_mode="fixed",
                use_library=False,
                workers=1,
            )
            new_timeout, new_cooldown, new_mode, new_library, new_workers, actions = result
            assert new_timeout >= 300  # Should be > 0
            assert actions != []

    def test_third_success_full_reset(self):
        """_adapt_to_error with 3+ successes fully resets to original values."""
        with (
            patch("omp_loop.error_recovery._ORIGINAL_SESSION_TIMEOUT", 300),
            patch("omp_loop.error_recovery._ORIGINAL_COOLDOWN", 10),
            patch("omp_loop.error_recovery._ORIGINAL_USE_LIBRARY", True),
            patch("omp_loop.error_recovery._ORIGINAL_WORKERS", 2),
        ):
            result = _adapt_to_error(
                error_type=None,
                mitigations={
                    "mitigation_level": 2,
                    "timeout_increased": True,
                    "cooldown_elevated": True,
                    "force_subprocess": True,
                    "reduced_workers": True,
                    "last_applied": "prev",
                    "actions": ["prev action"],
                },
                consecutive_successes=3,
                error_type_counts={},
                session_timeout=500,
                cooldown=60,
                cooldown_mode="fixed",
                use_library=False,
                workers=1,
            )
            new_timeout, new_cooldown, new_mode, new_library, new_workers, actions = result
            assert new_timeout == 300
            assert new_cooldown == 10
            assert new_library
            assert new_workers == 2


class TestAdaptToErrorTimeout:
    def test_mild_threshold_escalates_timeout(self):
        """_adapt_to_error with timeout at mild threshold escalates timeout."""
        result = _adapt_to_error(
            error_type="timeout",
            mitigations={
                "mitigation_level": 0,
                "timeout_increased": False,
                "cooldown_elevated": False,
                "force_subprocess": False,
                "reduced_workers": False,
                "last_applied": "",
                "actions": [],
            },
            consecutive_successes=0,
            error_type_counts={"timeout": 3, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0},
            session_timeout=300,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        new_timeout, new_cooldown, new_mode, new_library, new_workers, actions = result
        assert new_timeout == 450  # 300 * 150% = 450
        assert len(actions) > 0

    def test_moderate_threshold_escalates_both(self):
        """_adapt_to_error with timeout at moderate threshold escalates both timeout and cooldown."""
        result = _adapt_to_error(
            error_type="timeout",
            mitigations={
                "mitigation_level": 1,
                "timeout_increased": True,
                "cooldown_elevated": False,
                "force_subprocess": False,
                "reduced_workers": False,
                "last_applied": "",
                "actions": [],
            },
            consecutive_successes=0,
            error_type_counts={"timeout": 5, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0},
            session_timeout=450,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        _, new_cooldown, new_mode, _, _, actions = result
        assert new_cooldown > 10
        assert new_mode == "fixed"
        assert len(actions) > 0

    def test_stop_threshold(self):
        """_adapt_to_error with timeout at stop threshold returns level 3."""
        result = _adapt_to_error(
            error_type="timeout",
            mitigations={
                "mitigation_level": 2,
                "timeout_increased": True,
                "cooldown_elevated": True,
                "force_subprocess": False,
                "reduced_workers": False,
                "last_applied": "",
                "actions": [],
            },
            consecutive_successes=0,
            error_type_counts={"timeout": 10, "network": 0, "schema": 0, "unknown": 0, "heartbeat": 0},
            session_timeout=600,
            cooldown=20,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        _, _, _, _, _, actions = result
        has_stop = any("STOP" in a for a in actions)
        assert has_stop


class TestAdaptToErrorNetwork:
    def test_mild_threshold_escalates_cooldown(self):
        """_adapt_to_error with network error at mild threshold escalates cooldown."""
        with patch("omp_loop.error_recovery._ORIGINAL_COOLDOWN", 10):
            result = _adapt_to_error(
                error_type="network",
                mitigations={
                    "mitigation_level": 0,
                    "timeout_increased": False,
                    "cooldown_elevated": False,
                    "force_subprocess": False,
                    "reduced_workers": False,
                    "last_applied": "",
                    "actions": [],
                },
                consecutive_successes=0,
                error_type_counts={"timeout": 0, "network": 2, "schema": 0, "unknown": 0, "heartbeat": 0},
                session_timeout=300,
                cooldown=10,
                cooldown_mode="adaptive",
                use_library=True,
                workers=2,
            )
            _, new_cooldown, new_mode, _, _, actions = result
            assert new_cooldown >= 30
            assert new_mode == "adaptive"  # exponential backoff uses adaptive mode
            assert len(actions) > 0

    def test_moderate_threshold_reduces_workers(self):
        """_adapt_to_error with network at moderate threshold reduces workers."""
        result = _adapt_to_error(
            error_type="network",
            mitigations={
                "mitigation_level": 1,
                "timeout_increased": False,
                "cooldown_elevated": True,
                "force_subprocess": False,
                "reduced_workers": False,
                "last_applied": "",
                "actions": [],
            },
            consecutive_successes=0,
            error_type_counts={"timeout": 0, "network": 4, "schema": 0, "unknown": 0, "heartbeat": 0},
            session_timeout=300,
            cooldown=30,
            cooldown_mode="fixed",
            use_library=True,
            workers=2,
        )
        _, _, _, new_library, new_workers, actions = result
        assert not new_library
        assert new_workers == 1
        assert len(actions) > 0

    def test_stop_threshold(self):
        """_adapt_to_error with network at high count — never triggers stop.

        Network errors (API downtime, rate limiting, DNS flaps) are transient
        by nature.  The daemon should keep backing off exponentially rather
        than shutting down.
        """
        # Even at count 100 with mitigation_level 0 (fresh state), network
        # errors should apply backoff but never trigger STOP.
        result = _adapt_to_error(
            error_type="network",
            mitigations={
                "mitigation_level": 0,
                "timeout_increased": False,
                "cooldown_elevated": False,
                "force_subprocess": False,
                "reduced_workers": False,
                "last_applied": "",
                "actions": [],
            },
            consecutive_successes=0,
            error_type_counts={"timeout": 0, "network": 100, "schema": 0, "unknown": 0, "heartbeat": 0},
            session_timeout=300,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=False,
            workers=1,
        )
        _, new_cooldown, new_mode, _, _, actions = result
        has_stop = any("STOP" in a for a in actions)
        assert not has_stop
        # Should apply exponential backoff and cap at 1800s (30 min).
        assert "backoff" in " ".join(actions).lower()
        assert new_cooldown >= 30
        assert new_mode == "adaptive"


class TestAdaptToErrorUnknown:
    def test_mild_threshold(self):
        """_adapt_to_error with unknown error at mild threshold escalates cooldown."""
        with patch("omp_loop.error_recovery._ORIGINAL_COOLDOWN", 10):
            result = _adapt_to_error(
                error_type="unknown",
                mitigations={
                    "mitigation_level": 0,
                    "timeout_increased": False,
                    "cooldown_elevated": False,
                    "force_subprocess": False,
                    "reduced_workers": False,
                    "last_applied": "",
                    "actions": [],
                },
                consecutive_successes=0,
                error_type_counts={"timeout": 0, "network": 0, "schema": 0, "unknown": 3, "heartbeat": 0},
                session_timeout=300,
                cooldown=10,
                cooldown_mode="adaptive",
                use_library=True,
                workers=2,
            )
            _, new_cooldown, new_mode, _, _, actions = result
            assert new_cooldown >= 15
            assert new_mode == "fixed"
            assert len(actions) > 0
