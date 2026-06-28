"""Tests for error_recovery.py — _adapt_to_error, _set_originals, _pick_primary_error."""

from __future__ import annotations

import pytest

from hermes_loop.error_recovery import (
    _adapt_to_error,
    _set_originals,
    _pick_primary_error,
)
from hermes_loop.config import _ERROR_SEVERITY

# ===================================================================
# _set_originals — tested via behavior, not direct global reads,
# because import creates copies of immutable ints.
# ===================================================================


class TestSetOriginals:
    """Tests for _set_originals (verified through _adapt_to_error behavior)."""

    def test_set_and_verify_through_recovery(self):
        """Setting originals with values is confirmed by full recovery."""
        _set_originals(session_timeout=120, cooldown=5, use_library=True, workers=3)
        # Confirm by checking that a full recovery resets to these values
        mitigations = {
            "mitigation_level": 2,
            "timeout_increased": True,
            "cooldown_elevated": True,
            "force_subprocess": True,
            "reduced_workers": True,
        }
        _adapt_to_error(
            error_type=None,
            mitigations=mitigations,
            consecutive_successes=3,
            error_type_counts={},
            session_timeout=300,
            cooldown=60,
            cooldown_mode="fixed",
            use_library=False,
            workers=1,
        )
        assert mitigations["mitigation_level"] == 0

    def test_set_different_values_through_recovery(self):
        """Different originals produce different recovery targets."""
        _set_originals(session_timeout=300, cooldown=10, use_library=False, workers=2)
        mitigations = {
            "mitigation_level": 2,
            "timeout_increased": True,
            "cooldown_elevated": True,
            "force_subprocess": True,
            "reduced_workers": True,
        }
        result = _adapt_to_error(
            error_type=None,
            mitigations=mitigations,
            consecutive_successes=3,
            error_type_counts={},
            session_timeout=500,
            cooldown=60,
            cooldown_mode="fixed",
            use_library=False,
            workers=1,
        )
        timeout, cd, mode, lib, workers, actions = result
        assert timeout == 300
        assert cd == 10
        assert lib is False
        assert workers == 2


# ===================================================================
# _pick_primary_error
# ===================================================================


class TestPickPrimaryError:
    """Tests for _pick_primary_error."""

    def test_single_type(self):
        """Single error type returns itself."""
        assert _pick_primary_error(["timeout"]) == "timeout"

    def test_multiple_types_highest_severity(self):
        """Returns the type with highest severity."""
        result = _pick_primary_error(["unknown", "network", "heartbeat"])
        assert result == "heartbeat"

    def test_heartbeat_most_severe(self):
        """Heartbeat is most severe."""
        result = _pick_primary_error(["unknown", "timeout", "heartbeat"])
        assert result == "heartbeat"

    def test_unknown_least_severe(self):
        """Unknown is least severe."""
        result = _pick_primary_error(["unknown", "schema"])
        assert result == "schema"

    def test_empty_list_raises(self):
        """Empty list raises ValueError from max()."""
        with pytest.raises(ValueError):
            _pick_primary_error([])

    def test_single_item(self):
        """Single item list."""
        assert _pick_primary_error(["network"]) == "network"

    def test_severity_all_types(self):
        """All known types sorted by severity."""
        types = list(_ERROR_SEVERITY.keys())
        assert len(types) == 5
        assert _pick_primary_error(types) == "heartbeat"  # severity 5


# ===================================================================
# _adapt_to_error — Setup
# ===================================================================


_set_originals(session_timeout=120, cooldown=5, use_library=True, workers=3)


def _default_kwargs(**overrides):
    """Helper to create default kwargs for _adapt_to_error."""
    kwargs = {
        "error_type": None,
        "mitigations": {},
        "consecutive_successes": 0,
        "error_type_counts": {},
        "session_timeout": 120,
        "cooldown": 5,
        "cooldown_mode": "adaptive",
        "use_library": True,
        "workers": 3,
        "log_fn": None,
    }
    kwargs.update(overrides)
    return kwargs


# ===================================================================
# _adapt_to_error — No error (ramp down)
# ===================================================================


class TestAdaptToErrorNoError:
    """Tests when error_type is None (success — ramp down)."""

    def test_no_error_no_mitigation_level(self):
        """No error and level 0 → no changes, empty actions."""
        kwargs = _default_kwargs(error_type=None, mitigations={"mitigation_level": 0})
        result = _adapt_to_error(**kwargs)
        timeout, cd, mode, lib, workers, actions = result
        assert timeout == 120
        assert cd == 5
        assert mode == "adaptive"
        assert lib is True
        assert workers == 3
        assert actions == []

    def test_no_error_ramp_down_first_success(self):
        """First success at mitigation level 1 partially unwinds."""
        _set_originals(session_timeout=120, cooldown=5, use_library=True, workers=3)
        mitigations = {
            "mitigation_level": 1,
            "timeout_increased": True,
            "cooldown_elevated": False,
            "force_subprocess": False,
            "reduced_workers": False,
        }
        kwargs = _default_kwargs(
            error_type=None,
            mitigations=mitigations,
            consecutive_successes=1,
            session_timeout=180,
            cooldown=5,
        )
        result = _adapt_to_error(**kwargs)
        timeout, cd, mode, lib, workers, actions = result
        # timeout should be reduced: max(120, int(180 * 0.75)) = max(120, 135) = 135
        assert timeout == 135
        assert len(actions) > 0
        assert "Partial unwind" in actions[0]
        assert mitigations["mitigation_level"] == 0

    def test_no_error_full_recovery(self):
        """Three consecutive successes at level > 0 restores all originals."""
        _set_originals(session_timeout=120, cooldown=5, use_library=True, workers=3)
        mitigations = {
            "mitigation_level": 2,
            "timeout_increased": True,
            "cooldown_elevated": True,
            "force_subprocess": True,
            "reduced_workers": True,
        }
        kwargs = _default_kwargs(
            error_type=None,
            mitigations=mitigations,
            consecutive_successes=3,
            session_timeout=300,
            cooldown=60,
            use_library=False,
            workers=1,
        )
        result = _adapt_to_error(**kwargs)
        timeout, cd, mode, lib, workers, actions = result
        assert timeout == 120
        assert cd == 5
        assert lib is True
        assert workers == 3
        assert len(actions) > 0
        assert "Full recovery" in actions[0]
        assert mitigations["mitigation_level"] == 0

    def test_no_error_level_0_second_success(self):
        """Successes at level 0 do nothing."""
        mitigations = {"mitigation_level": 0}
        kwargs = _default_kwargs(
            error_type=None, mitigations=mitigations, consecutive_successes=5
        )
        result = _adapt_to_error(**kwargs)
        timeout, cd, mode, lib, workers, actions = result
        assert timeout == 120
        assert actions == []
        assert mitigations["mitigation_level"] == 0

    def test_no_error_level_1_second_success_no_change(self):
        """Second success at level 1 (< 3 consecutive) — no change."""
        mitigations = {"mitigation_level": 1}
        kwargs = _default_kwargs(
            error_type=None,
            mitigations=mitigations,
            consecutive_successes=2,
            session_timeout=180,
            cooldown=30,
            cooldown_mode="fixed",
        )
        result = _adapt_to_error(**kwargs)
        _, cd, _, _, _, actions = result
        assert actions == []
        assert mitigations["mitigation_level"] == 1

    def test_no_error_elevated_cooldown_unwinds(self):
        """First success with elevated fixed cooldown unwinds it."""
        _set_originals(session_timeout=120, cooldown=5, use_library=True, workers=3)
        mitigations = {
            "mitigation_level": 1,
            "timeout_increased": False,
            "cooldown_elevated": True,
            "force_subprocess": False,
            "reduced_workers": False,
        }
        kwargs = _default_kwargs(
            error_type=None,
            mitigations=mitigations,
            consecutive_successes=1,
            session_timeout=120,
            cooldown=30,
            cooldown_mode="fixed",
        )
        result = _adapt_to_error(**kwargs)
        _, cd, _, _, _, actions = result
        assert cd == 15  # max(5, 30 // 2) = max(5, 15) = 15
        assert len(actions) > 0
        assert "Partial unwind" in actions[0]


# ===================================================================
# _adapt_to_error — Timeout errors (ramp up, one level per call)
# ===================================================================
#
# NOTE: _adapt_to_error escalates by AT MOST ONE level per call.
# Level blocks overwrite new_level (e.g., level 1 block sets new_level=1,
# so level 2 and 3 checks fail). For multi-level escalation,
# call _adapt_to_error repeatedly.
#


class TestAdaptToErrorTimeout:
    """Tests for timeout error handling."""

    def test_timeout_below_threshold(self):
        """Timeout count below mild threshold → no mitigation."""
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations={"mitigation_level": 0},
            error_type_counts={"timeout": 1},
        )
        result = _adapt_to_error(**kwargs)
        timeout, cd, mode, lib, workers, actions = result
        assert timeout == 120
        assert actions == []

    def test_timeout_level_1(self):
        """Timeout count >= mild threshold → level 1, increase timeout."""
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations={"mitigation_level": 0},
            error_type_counts={"timeout": 3},
            session_timeout=120,
        )
        result = _adapt_to_error(**kwargs)
        timeout, cd, mode, lib, workers, actions = result
        assert timeout == 180
        assert len(actions) > 0
        assert "timeout" in actions[0].lower()

    def test_timeout_level_1_to_2(self):
        """Second call from level 1 escalates to level 2 (fixed cooldown)."""
        mitigations = {"mitigation_level": 1}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 5},  # moderate
            session_timeout=180,
            cooldown=5,
            cooldown_mode="adaptive",
        )
        result = _adapt_to_error(**kwargs)
        _, cd, mode, lib, workers, actions = result
        assert cd == 10  # min(120, max(5, 5*2)) = 10
        assert mode == "fixed"

    def test_timeout_level_2_to_3_stop(self):
        """Third call from level 2 escalates to level 3 STOP."""
        mitigations = {"mitigation_level": 2}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 8},  # stop
            session_timeout=180,
            cooldown=10,
            cooldown_mode="fixed",
        )
        _adapt_to_error(**kwargs)
        all_actions = kwargs["mitigations"].get("actions", [])
        assert any(
            "STOP" in a for a in all_actions
        ), f"No STOP in actions: {all_actions}"

    def test_timeout_stop_action_content(self):
        """Level 3 STOP action mentions persistent-timeout-failure."""
        mitigations = {"mitigation_level": 2}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 8},
            session_timeout=180,
            cooldown=10,
            cooldown_mode="fixed",
        )
        _adapt_to_error(**kwargs)
        all_actions = kwargs["mitigations"].get("actions", [])
        matching = [a for a in all_actions if "persistent-timeout-failure" in a]
        assert len(matching) > 0, f"No persistent-timeout-failure in: {all_actions}"


# ===================================================================
# _adapt_to_error — Network errors
# ===================================================================


class TestAdaptToErrorNetwork:
    """Tests for network error handling."""

    def test_network_level_1(self):
        """Network count >= mild → level 1, elevate cooldown."""
        kwargs = _default_kwargs(
            error_type="network",
            mitigations={"mitigation_level": 0},
            error_type_counts={"network": 2},
            cooldown=5,
        )
        result = _adapt_to_error(**kwargs)
        _, cd, mode, _, _, actions = result
        assert cd == 30  # min(300, max(5, 5*4))=20 → <30 → 30
        assert mode == "fixed"
        assert "Network" in actions[0]

    def test_network_level_2(self):
        """Network count >= moderate → level 2, subprocess + 1 worker."""
        kwargs = _default_kwargs(
            error_type="network",
            mitigations={"mitigation_level": 1},
            error_type_counts={"network": 4},
            cooldown=30,
            use_library=True,
            workers=3,
            cooldown_mode="fixed",
        )
        result = _adapt_to_error(**kwargs)
        _, cd, mode, lib, workers, actions = result
        # Still on mild cooldown from level 1 — level 2 only changes lib/workers
        assert lib is False
        assert workers == 1

    def test_network_level_3_stop(self):
        """Network count >= stop from level 2 → STOP."""
        mitigations = {"mitigation_level": 2}
        kwargs = _default_kwargs(
            error_type="network",
            mitigations=mitigations,
            error_type_counts={"network": 6},
            cooldown=30,
            use_library=False,
            workers=1,
            cooldown_mode="fixed",
        )
        _adapt_to_error(**kwargs)
        all_actions = kwargs["mitigations"].get("actions", [])
        assert any("STOP" in a for a in all_actions)


# ===================================================================
# _adapt_to_error — Schema errors
# ===================================================================


class TestAdaptToErrorSchema:
    """Tests for schema error handling."""

    def test_schema_level_1_monitoring(self):
        """Schema errors at mild → level 1, monitoring only."""
        kwargs = _default_kwargs(
            error_type="schema",
            mitigations={"mitigation_level": 0},
            error_type_counts={"schema": 3},
        )
        result = _adapt_to_error(**kwargs)
        timeout, cd, mode, lib, workers, actions = result
        assert timeout == 120
        assert cd == 5
        assert any("monitoring" in a.lower() for a in actions)

    def test_schema_skip_moderate(self):
        """Schema errors skip moderate (None), level 1 but no moderate."""
        kwargs = _default_kwargs(
            error_type="schema",
            mitigations={"mitigation_level": 0},
            error_type_counts={"schema": 4},  # moderate=None → skip, but mild=3 hit
        )
        result = _adapt_to_error(**kwargs)
        _, _, _, _, _, actions = result
        assert any("monitoring" in a.lower() for a in actions)

    def test_schema_level_2_stop(self):
        """Schema at level 0, count >= stop. Escalates one level per call.
        Schema has no moderate level action (None), so call 0→1→2→3 needs
        3 calls (0→1 mild, 1→2 no-op pass-through, 2→3 STOP).
        """
        mitigations = {"mitigation_level": 0}
        kwargs_defaults = dict(
            error_type="schema",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts={"schema": 5},
            session_timeout=120,
            cooldown=5,
            cooldown_mode="adaptive",
            use_library=True,
            workers=3,
        )
        # Call 1: level 0 → level 1 (mild: monitoring)
        _adapt_to_error(**kwargs_defaults)
        assert mitigations["mitigation_level"] == 1
        # Call 2: level 1 → level 2 (no schema-specific action, but level passes through)
        _adapt_to_error(**kwargs_defaults)
        assert mitigations["mitigation_level"] >= 2
        # Call 3: level 2 → level 3 (STOP)
        _adapt_to_error(**kwargs_defaults)
        assert mitigations["mitigation_level"] == 3
        all_actions = mitigations.get("actions", [])
        assert any("STOP" in a for a in all_actions), f"No STOP: {all_actions}"


# ===================================================================
# _adapt_to_error — Unknown errors
# ===================================================================


class TestAdaptToErrorUnknown:
    """Tests for unknown error handling."""

    def test_unknown_level_1(self):
        """Unknown errors at mild → level 1, elevate cooldown."""
        kwargs = _default_kwargs(
            error_type="unknown",
            mitigations={"mitigation_level": 0},
            error_type_counts={"unknown": 3},
            cooldown=5,
        )
        result = _adapt_to_error(**kwargs)
        _, cd, mode, _, _, actions = result
        assert cd == 15  # min(120, max(5, 5*2)) = 10 → <15 → 15
        assert mode == "fixed"
        assert any("Unknown" in a for a in actions)

    def test_unknown_level_2(self):
        """Unknown errors at moderate → level 2, subprocess."""
        mitigations = {"mitigation_level": 1}
        kwargs = _default_kwargs(
            error_type="unknown",
            mitigations=mitigations,
            error_type_counts={"unknown": 5},
            use_library=True,
            workers=3,
            cooldown=15,
            cooldown_mode="fixed",
        )
        result = _adapt_to_error(**kwargs)
        _, _, _, lib, workers, actions = result
        assert lib is False
        assert workers == 1

    def test_unknown_level_3_stop(self):
        """Unknown from level 2 → STOP."""
        mitigations = {"mitigation_level": 2}
        kwargs = _default_kwargs(
            error_type="unknown",
            mitigations=mitigations,
            error_type_counts={"unknown": 7},
            use_library=False,
            workers=1,
            cooldown=15,
            cooldown_mode="fixed",
        )
        _adapt_to_error(**kwargs)
        all_actions = kwargs["mitigations"].get("actions", [])
        assert any("STOP" in a for a in all_actions)


# ===================================================================
# _adapt_to_error — Stateful mitigations dict mutation
# ===================================================================


class TestMitigationsDictMutation:
    """Tests that mitigations dict is correctly mutated in-place."""

    def test_mitigation_level_updated(self):
        """mitigation_level in the dict is updated on error."""
        mitigations = {"mitigation_level": 0}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 3},
        )
        _adapt_to_error(**kwargs)
        assert mitigations["mitigation_level"] >= 1

    def test_mitigation_flags_set(self):
        """Mitigation flags are set on error."""
        mitigations = {"mitigation_level": 0}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 3},
        )
        _adapt_to_error(**kwargs)
        assert "timeout_increased" in mitigations
        assert "cooldown_elevated" in mitigations
        assert "force_subprocess" in mitigations
        assert "reduced_workers" in mitigations

    def test_actions_appended(self):
        """Actions are appended to the rolling log."""
        mitigations = {"mitigation_level": 0, "actions": []}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 3},
        )
        _adapt_to_error(**kwargs)
        assert len(mitigations["actions"]) > 0

    def test_actions_capped(self):
        """Rolling actions log capped at 20."""
        mitigations = {"mitigation_level": 0, "actions": ["old"] * 25}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 3},
        )
        _adapt_to_error(**kwargs)
        assert len(mitigations["actions"]) <= 20

    def test_last_applied_timestamp_set(self):
        """Error path sets last_applied ISO timestamp."""
        mitigations = {"mitigation_level": 0}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 3},
        )
        _adapt_to_error(**kwargs)
        assert "last_applied" in mitigations
        assert isinstance(mitigations["last_applied"], str)
        assert "T" in mitigations["last_applied"]

    def test_no_error_no_timestamp(self):
        """Success path does NOT set last_applied."""
        mitigations = {"mitigation_level": 0}
        kwargs = _default_kwargs(error_type=None, mitigations=mitigations)
        _adapt_to_error(**kwargs)
        assert "last_applied" not in mitigations


# ===================================================================
# _adapt_to_error — Edge cases
# ===================================================================


class TestAdaptToErrorEdgeCases:
    """Edge cases for _adapt_to_error."""

    def test_no_error_no_actions(self):
        """None error_type → success path, no actions."""
        kwargs = _default_kwargs(error_type=None)
        result = _adapt_to_error(**kwargs)
        assert result[5] == []

    def test_unknown_error_type_default_thresholds(self):
        """Unknown type not in thresholds gets defaults (all 999)."""
        kwargs = _default_kwargs(
            error_type="bogus_type",
            mitigations={"mitigation_level": 0},
            error_type_counts={"bogus_type": 1},
        )
        result = _adapt_to_error(**kwargs)
        _, _, _, _, _, actions = result
        assert actions == []

    def test_stay_at_current_level_below_thresholds(self):
        """Count below threshold at current level stays unchanged."""
        mitigations = {"mitigation_level": 2}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 1},
            session_timeout=180,
            cooldown=30,
            cooldown_mode="fixed",
            use_library=False,
            workers=1,
        )
        result = _adapt_to_error(**kwargs)
        timeout, cd, mode, lib, workers, actions = result
        assert timeout == 180
        assert cd == 30
        assert actions == []

    def test_success_from_level_2_unwinds(self):
        """Success from level 2 unwinds once."""
        _set_originals(session_timeout=120, cooldown=5, use_library=True, workers=3)
        mitigations = {"mitigation_level": 2}
        kwargs = _default_kwargs(
            error_type=None,
            mitigations=mitigations,
            consecutive_successes=1,
            session_timeout=180,
            cooldown=30,
            cooldown_mode="fixed",
            use_library=False,
            workers=1,
        )
        result = _adapt_to_error(**kwargs)
        _, cd, _, _, _, actions = result
        assert len(actions) > 0

    def test_empty_mitigations_error_path(self):
        """Empty mitigations dict doesn't crash on error."""
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations={},
            error_type_counts={"timeout": 3},
        )
        result = _adapt_to_error(**kwargs)
        assert len(result) == 6

    def test_mitigations_dict_has_actions_key_added(self):
        """When mitigations lacks 'actions', it's added on error."""
        mitigations = {"mitigation_level": 0}
        kwargs = _default_kwargs(
            error_type="timeout",
            mitigations=mitigations,
            error_type_counts={"timeout": 3},
        )
        _adapt_to_error(**kwargs)
        assert "actions" in mitigations

    def test_multi_call_escalation(self):
        """Call _adapt_to_error multiple times to escalate through levels."""
        _set_originals(session_timeout=120, cooldown=5, use_library=True, workers=3)
        mitigations = {"mitigation_level": 0}
        counts = {"timeout": 10}  # single count above all thresholds
        # Level 1
        r1 = _adapt_to_error(
            error_type="timeout",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=counts,
            session_timeout=120,
            cooldown=5,
            cooldown_mode="adaptive",
            use_library=True,
            workers=3,
        )
        assert mitigations["mitigation_level"] == 1
        assert r1[0] == 180  # timeout increased
        # Level 2
        _adapt_to_error(  # noqa: F841
            error_type="timeout",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=counts,
            session_timeout=180,
            cooldown=5,
            cooldown_mode="adaptive",
            use_library=True,
            workers=3,
        )
        assert mitigations["mitigation_level"] >= 2
        # Level 3
        _adapt_to_error(  # noqa: F841
            error_type="timeout",
            mitigations=mitigations,
            consecutive_successes=0,
            error_type_counts=counts,
            session_timeout=180,
            cooldown=10,
            cooldown_mode="fixed",
            use_library=True,
            workers=3,
        )
        all_actions = mitigations.get("actions", [])
        assert any("STOP" in a for a in all_actions)
