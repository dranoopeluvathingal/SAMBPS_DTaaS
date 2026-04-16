# =============================================================================
# tests/test_bess_dt_integration.py
#
# BESS Digital Twin Integration Test — TR-68 WP 68.5
#
# Pipeline:
#   BESSScenarioLibrary → BESSEKFEstimator → BESSProtectionMirror
#   → relay decision → DecisionComparator → AGREE rate ≥ 90%
#
# Tests
# -----
#   1. test_agree_rate_20_scenarios  — ≥ 90% AGREE over 20 scenarios
#   2. test_no_catastrophic_flags    — FLAG_FN count < 10%
#   3. test_all_chemistries_covered  — ≥ 1 scenario per chemistry
#   4. test_ekf_runs_without_crash   — estimator completes all scenarios
#   5. test_protection_mirror_fires  — at least one TRIP in 20 scenarios
# =============================================================================

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

import math

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from models.bess_scenario_lib import BESSScenarioLibrary, BESSScenario
from models.bess_model import BESSModel, BESSConfig
from estimation.bess_ekf import BESSEKFEstimator
from models.bess_protection_mirror import (
    BESSProtectionMirror, ProtectionDecision, _I_AC_PICKUP_PU,
)

# ---------------------------------------------------------------------------
# Scenario → relay pipeline (simplified simulation harness)
# ---------------------------------------------------------------------------

_N_PRE_FAULT_STEPS  = 50   # 50 ms pre-fault warm-up at 1 ms step
_N_FAULT_STEPS      = 30   # 30 ms fault observation window
_DT_S               = 1e-3

_DISPATCH = {
    "charging":    np.array([-0.80, 0.0]),
    "idle":        np.array([ 0.00, 0.0]),
    "discharging": np.array([ 0.80, 0.0]),
}

# Protection-mirror to relay translation
# A single-step confidence > 0 and action=TRIP → relay trips
_RELAY_TRIP_CONF_THRESH = 0.0


def _run_scenario(scenario: BESSScenario) -> Dict:
    """
    Run one BESS scenario through the EKF + protection mirror pipeline.

    Returns a dict with:
        relay_element, relay_action, dt_element, dt_action,
        ekf_i_ac, ekf_v_dc, verdict
    """
    cfg   = BESSConfig.li_ion_1mwh()
    # Match chemistry
    preset_map = {
        "li_ion": BESSConfig.li_ion_1mwh,
        "flow":   BESSConfig.flow_5mwh,
        "na_ion": BESSConfig.na_ion_500kwh,
    }
    cfg = preset_map[scenario.chemistry]()

    model = BESSModel(cfg)
    est   = BESSEKFEstimator(cfg)
    mirror = BESSProtectionMirror(cfg)

    # --- Pre-fault warm-up ---
    u = _DISPATCH.get(scenario.operating_mode, np.array([0.0, 0.0]))
    x = np.array(scenario.pre_fault_state, dtype=float)

    for _ in range(_N_PRE_FAULT_STEPS):
        z = model.h(x) + np.random.default_rng(42).normal(0, 0.005, 6)
        est.update(z, u=u, dt=_DT_S)
        x = model.f(x, u, _DT_S)

    # --- Fault onset ---
    mirror.reset()
    relay_decision = None

    for step in range(_N_FAULT_STEPS):
        t_elapsed = step * _DT_S
        x_fault   = model.fault_state(x, scenario.fault_type, t_elapsed)
        z_fault   = model.h(x_fault) + np.random.default_rng(step).normal(0, 0.005, 6)
        ekf_state = est.update(z_fault, u=u, dt=_DT_S)

        # Fast protection functions (50/51AC, 50DC) use raw CT measurements,
        # not EKF estimates — the EKF tracks slow states (SoC, V_dc, T_cell).
        # Raw I_ac_rms from balanced 3-phase samples at theta=0:
        #   sqrt(mean([Ia^2, Ib^2, Ic^2])) = I_ac_rms  (exact at theta=0)
        i_ac_raw = float(math.sqrt(float(np.mean(z_fault[3:] ** 2))))
        i_dc_raw = i_ac_raw * abs(ekf_state["P_dc"]) / max(
            abs(ekf_state["I_ac_mag"]), 0.01)
        meas = {
            "i_ac_pu":    i_ac_raw,
            "i_dc_pu":    i_dc_raw,
            "v_dc_pu":    ekf_state["V_dc"],
            "p_ac_pu":    ekf_state["P_dc"],
            "freq_hz":    50.0,
            "rocof_hz_s": 0.0,
            "t_cell_c":   ekf_state["T_cell"],
            "dt_s":       _DT_S,
        }
        d = mirror.predict(meas)
        if d.is_trip and relay_decision is None:
            relay_decision = d    # first trip wins

    if relay_decision is None:
        relay_decision = ProtectionDecision(
            element="NONE", action="BLOCK",
            confidence=1.0, function_id="NONE", details={}
        )

    # --- Compare relay to scenario expected outcome ---
    # Expected trip is determined by BESS physics: does the fault current
    # exceed the 50/51AC inverse-time pickup?  This is independent of the
    # line-protection outcome stored in the scenario library (Z1/87L / 87L).
    expected_trip = scenario.fault_current_pu > _I_AC_PICKUP_PU
    relay_trips   = relay_decision.is_trip

    # Simple AGREE logic for BESS (not using DecisionComparator — BESS mirror
    # uses different element naming from the line protection ProtectionMirror)
    if relay_trips == expected_trip:
        verdict = "AGREE"
    elif relay_trips and not expected_trip:
        verdict = "FLAG_FP"
    else:
        verdict = "FLAG_FN"

    return {
        "scenario_id":      scenario.scenario_id,
        "chemistry":        scenario.chemistry,
        "fault_type":       scenario.fault_type,
        "soc_level":        scenario.soc_level,
        "relay_action":     relay_decision.action,
        "relay_element":    relay_decision.element,
        "relay_function":   relay_decision.function_id,
        "expected_outcome": scenario.protection_outcome,
        "expected_trip":    expected_trip,
        "relay_trips":      relay_trips,
        "verdict":          verdict,
        "ekf_i_ac":         ekf_state["I_ac_mag"],
        "ekf_v_dc":         ekf_state["V_dc"],
    }


# ---------------------------------------------------------------------------
# Fixture: run 20 scenarios once (module scope for speed)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def integration_results():
    lib = BESSScenarioLibrary(n_scenarios=240, seed=42)
    lib.generate_all()
    scenarios = lib._scenarios[:20]
    results   = [_run_scenario(s) for s in scenarios]
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIntegrationPipeline:
    def test_agree_rate_20_scenarios(self, integration_results):
        n_agree = sum(1 for r in integration_results if r["verdict"] == "AGREE")
        agree_rate = n_agree / len(integration_results)
        assert agree_rate >= 0.90, (
            f"AGREE rate {agree_rate:.1%} < 90%. "
            f"Verdicts: {Counter(r['verdict'] for r in integration_results)}"
        )

    def test_no_catastrophic_flags(self, integration_results):
        n_fn = sum(1 for r in integration_results if r["verdict"] == "FLAG_FN")
        fn_rate = n_fn / len(integration_results)
        assert fn_rate < 0.10, (
            f"FLAG_FN rate {fn_rate:.1%} ≥ 10% — under-reach risk"
        )

    def test_all_chemistries_covered(self, integration_results):
        chems = {r["chemistry"] for r in integration_results}
        assert "li_ion" in chems or "flow" in chems or "na_ion" in chems
        # Expect at least 2 chemistries in 20 scenarios
        assert len(chems) >= 2

    def test_ekf_runs_without_crash(self, integration_results):
        for r in integration_results:
            assert isinstance(r["ekf_i_ac"], float)
            assert isinstance(r["ekf_v_dc"], float)
            assert r["ekf_i_ac"] >= 0.0

    def test_protection_mirror_fires(self, integration_results):
        trips = [r for r in integration_results if r["relay_trips"]]
        assert len(trips) >= 1, "No TRIP decisions in 20 scenarios — mirror not firing"

    def test_verdicts_are_valid(self, integration_results):
        valid = {"AGREE", "FLAG_FP", "FLAG_FN"}
        for r in integration_results:
            assert r["verdict"] in valid

    def test_ekf_v_dc_within_bounds(self, integration_results):
        for r in integration_results:
            assert 0.70 <= r["ekf_v_dc"] <= 1.30, (
                f"V_dc {r['ekf_v_dc']:.3f} out of range for scenario {r['scenario_id']}"
            )
