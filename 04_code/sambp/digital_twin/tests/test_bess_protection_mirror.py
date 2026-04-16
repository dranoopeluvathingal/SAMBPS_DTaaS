# =============================================================================
# tests/test_bess_protection_mirror.py
#
# Unit tests for models/bess_protection_mirror.py — TR-68 WP 68.3
#
# Tests
# -----
#   1. test_50dc_instantaneous      — DC overcurrent trips instantly at 2.0 pu
#   2. test_50dc_definite_time      — DC overcurrent at 1.2 pu gives low confidence
#   3. test_59dc_overvoltage        — V_dc > 1.15 pu trips after 100 ms
#   4. test_27dc_undervoltage       — V_dc < 0.80 pu trips after 500 ms
#   5. test_49_thermal_overload     — I²t accumulator trips at threshold
#   6. test_32_reverse_power        — negative P trips after 10 s
#   7. test_81r_rocof               — |df/dt| > 1 Hz/s trips after 0.5 s
#   8. test_50_51ac_instantaneous   — AC overcurrent at 2.5 pu trips instantly
#   9. test_50_51ac_inverse_time    — AC overcurrent at 1.5 pu gives time-graded conf
#  10. test_no_fault_returns_none   — nominal conditions → BLOCK / NONE
#  11. test_priority_50dc_over_59dc — 50DC beats 59DC when both assert
#  12. test_reset_clears_accumulators — reset() zeroes all state
#  13. test_accumulator_state_keys  — accumulator_state() returns expected keys
#  14. test_decision_is_trip_property — ProtectionDecision.is_trip correct
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from models.bess_protection_mirror import (
    BESSProtectionMirror,
    ProtectionDecision,
    _I_DC_INST_PU,
    _I_DC_PICKUP_PU,
    _V_DC_OV_PU,
    _V_DC_UV_PU,
    _T_59DC_S,
    _T_27DC_S,
    _I2T_TRIP,
    _T_32_S,
    _ROCOF_HZ_S,
    _T_81R_S,
    _I_AC_INST_PU,
    _I_AC_PICKUP_PU,
)
from models.bess_model import BESSConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nominal() -> dict:
    """Safe nominal measurement dict (no faults)."""
    return {
        "i_ac_pu":    0.50,
        "i_dc_pu":    0.50,
        "v_dc_pu":    1.00,
        "p_ac_pu":    0.50,
        "freq_hz":    50.0,
        "rocof_hz_s": 0.00,
        "t_cell_c":   25.0,
        "dt_s":       1e-3,
    }


def _mirror() -> BESSProtectionMirror:
    return BESSProtectionMirror(BESSConfig.li_ion_1mwh())


def _run_accumulator(mirror: BESSProtectionMirror,
                     meas: dict, n_steps: int) -> ProtectionDecision:
    """Drive accumulator for n_steps, return last decision."""
    decision = None
    for _ in range(n_steps):
        decision = mirror.predict(meas)
    return decision


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDCOvercurrent50DC:
    def test_instantaneous_trip(self):
        m = _mirror()
        meas = _nominal()
        meas["i_dc_pu"] = _I_DC_INST_PU + 0.10    # well above 2.0 pu
        d = m.predict(meas)
        assert d.is_trip
        assert d.function_id == "50DC"
        assert d.details["stage"] == "instantaneous"
        assert d.confidence > 0.0

    def test_definite_time_gives_partial_confidence(self):
        m = _mirror()
        meas = _nominal()
        meas["i_dc_pu"] = _I_DC_PICKUP_PU + 0.05  # above DT pickup, below inst.
        d = m.predict(meas)
        assert d.function_id == "50DC"
        # Confidence < 1 because it's not the instantaneous stage
        assert 0.0 < d.confidence < 1.0

    def test_below_pickup_no_50dc(self):
        m = _mirror()
        meas = _nominal()
        meas["i_dc_pu"] = 0.50   # well below pickup
        d = m.predict(meas)
        assert d.function_id != "50DC"


class TestDCOvervoltage59DC:
    def test_trips_after_accumulation(self):
        m = _mirror()
        meas = _nominal()
        meas["v_dc_pu"] = _V_DC_OV_PU + 0.05   # 1.20 pu
        meas["dt_s"]    = _T_59DC_S             # one large step = 100 ms
        d = m.predict(meas)
        assert d.is_trip
        assert d.function_id == "59DC"
        assert d.details["v_dc_pu"] > _V_DC_OV_PU

    def test_no_trip_below_threshold(self):
        m = _mirror()
        meas = _nominal()
        meas["v_dc_pu"] = _V_DC_OV_PU - 0.01   # just below
        for _ in range(200):
            d = m.predict(meas)
        assert d.function_id != "59DC"

    def test_accumulator_resets_on_recovery(self):
        m = _mirror()
        meas = _nominal()
        meas["v_dc_pu"] = _V_DC_OV_PU + 0.05
        meas["dt_s"]    = 0.05                  # 50 ms — not enough to trip alone
        m.predict(meas)
        assert m._acc_59dc > 0.0
        meas["v_dc_pu"] = 1.0                   # voltage recovers
        m.predict(meas)
        assert m._acc_59dc < 0.05               # should have decayed


class TestDCUndervoltage27DC:
    def test_trips_after_accumulation(self):
        m = _mirror()
        meas = _nominal()
        meas["v_dc_pu"] = _V_DC_UV_PU - 0.05   # 0.75 pu
        meas["dt_s"]    = _T_27DC_S             # 500 ms single step
        d = m.predict(meas)
        assert d.is_trip
        assert d.function_id == "27DC"

    def test_no_trip_above_threshold(self):
        m = _mirror()
        meas = _nominal()
        meas["v_dc_pu"] = _V_DC_UV_PU + 0.01
        for _ in range(1000):
            d = m.predict(meas)
        assert d.function_id != "27DC"


class TestThermalOverload49:
    def test_trips_when_i2t_exceeds_threshold(self):
        m = _mirror()
        # I = 2.0 pu → I²= 4 → net rate = (4-1) = 3 pu²/s
        # Need 10 pu²·s → time ≈ 3.33 s = 3333 steps at 1 ms
        meas = _nominal()
        meas["i_ac_pu"] = 2.00
        meas["dt_s"]    = 1e-3
        d = None
        for _ in range(4000):
            d = m.predict(meas)
            if d.function_id == "49":
                break
        assert d is not None and d.function_id == "49"
        assert d.is_trip

    def test_accumulator_decays_below_base(self):
        m = _mirror()
        # Pre-charge accumulator
        m._acc_i2t = 5.0
        meas = _nominal()
        meas["i_ac_pu"] = 0.50    # below base → accumulator decays
        meas["dt_s"]    = 1.0
        m.predict(meas)
        assert m._acc_i2t < 5.0

    def test_no_trip_at_nominal(self):
        m = _mirror()
        meas = _nominal()
        for _ in range(1000):
            d = m.predict(meas)
        assert d.function_id != "49"


class TestReversePower32:
    def test_trips_after_sustained_reverse(self):
        m = _mirror()
        meas = _nominal()
        meas["p_ac_pu"] = -0.20   # clear import / reverse
        meas["dt_s"]    = _T_32_S # one step = 10 s
        d = m.predict(meas)
        assert d.is_trip
        assert d.function_id == "32"

    def test_no_trip_on_positive_power(self):
        m = _mirror()
        meas = _nominal()
        meas["p_ac_pu"] = 0.80
        for _ in range(100):
            d = m.predict(meas)
        assert d.function_id != "32"

    def test_accumulator_resets_on_positive(self):
        m = _mirror()
        m._acc_32 = 9.0    # just below trip
        meas = _nominal()
        meas["p_ac_pu"] = 0.50   # normal export
        m.predict(meas)
        assert m._acc_32 == 0.0


class TestRoCoF81R:
    def test_trips_after_sustained_rocof(self):
        m = _mirror()
        meas = _nominal()
        meas["rocof_hz_s"] = _ROCOF_HZ_S + 0.50   # 1.5 Hz/s
        meas["dt_s"]       = _T_81R_S             # 0.5 s single step
        d = m.predict(meas)
        assert d.is_trip
        assert d.function_id == "81R"

    def test_no_trip_below_threshold(self):
        m = _mirror()
        meas = _nominal()
        meas["rocof_hz_s"] = 0.50   # below 1.0 Hz/s
        for _ in range(1000):
            d = m.predict(meas)
        assert d.function_id != "81R"

    def test_negative_rocof_also_trips(self):
        m = _mirror()
        meas = _nominal()
        meas["rocof_hz_s"] = -(  _ROCOF_HZ_S + 0.50)
        meas["dt_s"]       = _T_81R_S
        d = m.predict(meas)
        assert d.is_trip and d.function_id == "81R"


class TestACOvercurrent50_51AC:
    def test_instantaneous_trip(self):
        m = _mirror()
        meas = _nominal()
        meas["i_ac_pu"] = _I_AC_INST_PU + 0.10   # above 2.5 pu
        d = m.predict(meas)
        assert d.is_trip
        assert d.function_id == "50/51AC"
        assert d.details["stage"] == "instantaneous_50"

    def test_inverse_time_gives_time_graded_confidence(self):
        m = _mirror()
        meas = _nominal()
        meas["i_ac_pu"] = _I_AC_PICKUP_PU + 0.20   # 1.4 pu, above 51 pickup
        meas["dt_s"]    = 1e-3
        d = m.predict(meas)
        assert d.function_id == "50/51AC"
        assert d.details["stage"] == "inverse_time_51"
        # Confidence should be very small (trip time >> 1 ms step)
        assert 0.0 < d.confidence < 0.10

    def test_below_51_pickup_no_ac_trip(self):
        m = _mirror()
        meas = _nominal()
        meas["i_ac_pu"] = _I_AC_PICKUP_PU - 0.10   # below pickup
        d = m.predict(meas)
        assert d.function_id != "50/51AC"

    def test_iec_si_time_characteristic(self):
        # At 2× pickup: t = 0.30 × 0.14 / (2^0.02 − 1) ≈ known value
        t = BESSProtectionMirror.iec_si_time(2.0 * _I_AC_PICKUP_PU, _I_AC_PICKUP_PU)
        assert 1.0 < t < 200.0    # reasonable range for TMS=0.30, 2× pickup


class TestNominalConditions:
    def test_no_fault_returns_none_element(self):
        m = _mirror()
        meas = _nominal()
        d = m.predict(meas)
        assert d.element == "NONE"
        assert d.action  == "BLOCK"

    def test_is_trip_false_on_block(self):
        m = _mirror()
        d = m.predict(_nominal())
        assert not d.is_trip


class TestPriorityOrdering:
    def test_50dc_beats_59dc_when_both_assert(self):
        m = _mirror()
        meas = _nominal()
        # Trigger 59DC accumulator enough to trip
        m._acc_59dc = _T_59DC_S + 0.01
        # Also trigger 50DC instantaneous
        meas["i_dc_pu"] = _I_DC_INST_PU + 0.10
        meas["v_dc_pu"] = _V_DC_OV_PU + 0.05
        d = m.predict(meas)
        # 50DC is priority 1, 59DC is priority 2
        assert d.function_id == "50DC"


class TestReset:
    def test_reset_clears_all_accumulators(self):
        m = _mirror()
        m._acc_59dc = 99.0
        m._acc_27dc = 99.0
        m._acc_i2t  = 99.0
        m._acc_32   = 99.0
        m._acc_81r  = 99.0
        m.reset()
        state = m.accumulator_state()
        assert all(v == 0.0 for v in state.values())


class TestAccumulatorState:
    def test_accumulator_state_keys(self):
        m = _mirror()
        state = m.accumulator_state()
        expected = {"acc_59dc_s", "acc_27dc_s", "acc_i2t", "acc_32_s", "acc_81r_s"}
        assert expected == set(state.keys())

    def test_accumulator_state_all_floats(self):
        m = _mirror()
        state = m.accumulator_state()
        assert all(isinstance(v, float) for v in state.values())
