# =============================================================================
# tests/test_tr77_tr78_tr79.py  — quick-win bundle tests
# =============================================================================

from __future__ import annotations

import math
import cmath
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from estimation.open_conductor import OpenConductorDetector
from models.fuse_failure_scenario import FuseFailureScenarioLibrary
from coordination.sympathetic_trip import SympatheticTripMonitor
from models.multi_feeder_scenario import MultiFeederScenarioLibrary
from coordination.n2_degraded import TopologyDetector, AdaptiveSettingCalculator
from models.degraded_grid_scenario import DegradedGridScenarioLibrary


# ===========================================================================
# TR-77: Open-Conductor / Fuse Failure
# ===========================================================================

def test_open_conductor_detection():
    """Clear open-phase signature → OPEN_CONDUCTOR with phase identification."""
    det = OpenConductorDetector()

    # Phase-A open: I2/I1 = 0.60 >> 0.50, V2/V1 = 0.18 << 0.40
    ang_a = -30.0
    i2_phasor = cmath.rect(0.60, math.radians(ang_a))
    seqs = {
        'I2_I1_ratio': 0.60,
        'V2_V1_ratio': 0.18,
        'I0_I1_ratio': 0.52,
        'I2': i2_phasor,
    }
    alarm = det.update(t=0.05, seqs=seqs)
    assert alarm.action == "OPEN_CONDUCTOR", f"Expected OPEN_CONDUCTOR, got {alarm.action}"
    assert alarm.open_phase == "A", f"Expected phase A, got {alarm.open_phase}"
    assert alarm.confidence >= 0.70

    # Phase-B open
    det.reset()
    i2_b = cmath.rect(0.62, math.radians(90.0))
    seqs_b = {'I2_I1_ratio': 0.62, 'V2_V1_ratio': 0.20, 'I0_I1_ratio': 0.55, 'I2': i2_b}
    alarm_b = det.update(t=0.05, seqs=seqs_b)
    assert alarm_b.action == "OPEN_CONDUCTOR"
    assert alarm_b.open_phase == "B"

    # Healthy: I2/I1 = 0.03 → HEALTHY
    det.reset()
    alarm_h = det.update(t=0.0, seqs={'I2_I1_ratio': 0.03, 'V2_V1_ratio': 0.01,
                                      'I0_I1_ratio': 0.01, 'I2': 0.03+0j})
    assert alarm_h.action == "HEALTHY"

    # SLG fault: high V2/V1 → HEALTHY (not open conductor)
    det.reset()
    alarm_slg = det.update(t=0.0, seqs={'I2_I1_ratio': 0.55, 'V2_V1_ratio': 0.50,
                                         'I0_I1_ratio': 0.40, 'I2': 0.55+0j})
    assert alarm_slg.action == "HEALTHY", f"SLG should not be OPEN_CONDUCTOR, got {alarm_slg.action}"

    print("PASS test_open_conductor_detection")


def test_fuse_failure_scenario_library():
    """Library has 20 scenarios; all OPEN_CONDUCTOR scenarios have I2/I1 ≥ 0.50."""
    lib = FuseFailureScenarioLibrary()
    assert len(lib) == 20, f"Expected 20 scenarios, got {len(lib)}"

    # All OC groups should have I2/I1 ≥ 0.50
    for s in lib:
        if s.expected_action == "OPEN_CONDUCTOR":
            assert s.I2_I1_ratio >= 0.50, (
                f"Scenario {s.id}: I2/I1={s.I2_I1_ratio} < 0.50 for OPEN_CONDUCTOR"
            )
        if s.expected_action == "HEALTHY":
            assert s.I2_I1_ratio < 0.45, (
                f"Scenario {s.id}: I2/I1={s.I2_I1_ratio} too high for HEALTHY"
            )

    # Integration: run all 20 through detector
    det = OpenConductorDetector()
    agree = 0
    for s in lib:
        det.reset()
        alarm = det.update(t=0.05, seqs=s.to_seqs_dict())
        if alarm.action == s.expected_action:
            agree += 1
    rate = agree / len(lib)
    assert rate >= 0.85, f"Fuse failure agree rate {rate:.2f} < 0.85"

    print(f"PASS test_fuse_failure_scenario_library (agree={rate:.2%})")


def test_open_conductor_ambiguous():
    """Near-threshold I2/I1 ratios map to AMBIGUOUS."""
    det = OpenConductorDetector()
    seqs = {'I2_I1_ratio': 0.40, 'V2_V1_ratio': 0.18, 'I0_I1_ratio': 0.32, 'I2': 0.40+0j}
    alarm = det.update(t=0.1, seqs=seqs)
    assert alarm.action == "AMBIGUOUS", f"Expected AMBIGUOUS, got {alarm.action}"
    assert alarm.confidence < 0.80

    print("PASS test_open_conductor_ambiguous")


# ===========================================================================
# TR-78: Sympathetic Tripping Prevention
# ===========================================================================

def test_sympathetic_trip_block():
    """Fault on feeder-0 causes BLOCK on sympathetic feeder-1."""
    mon = SympatheticTripMonitor(n_feeders=2)

    # Pre-fault — steady state
    mon.update(t=0.00, currents_pu=[1.0, 1.0])
    mon.update(t=0.02, currents_pu=[1.0, 1.0])
    mon.update(t=0.04, currents_pu=[1.0, 1.0])

    # Fault onset: feeder-0 shoots to 4.0 pu, feeder-1 sympathetically to 1.25 pu
    # (small ΔI/I_pre = 0.25 < 0.30 threshold → classified as sympathetic)
    mon.update(t=0.06, currents_pu=[2.5, 1.10])
    results = mon.update(t=0.08, currents_pu=[4.0, 1.25])

    actions = {r.feeder_id: r.action for r in results}
    assert actions[0] == "FAULT_FEEDER", f"Feeder-0 should be FAULT_FEEDER, got {actions[0]}"
    assert actions[1] == "BLOCK",        f"Feeder-1 should be BLOCK, got {actions[1]}"
    assert "SYMPATHETIC_TRIP" in results[1].blocked_by

    print("PASS test_sympathetic_trip_block")


def test_sympathetic_trip_healthy_permit():
    """Healthy feeders below threshold → PERMIT."""
    mon = SympatheticTripMonitor(n_feeders=3)
    for t in [0.0, 0.02, 0.04]:
        results = mon.update(t=t, currents_pu=[0.9, 0.8, 0.85])
    actions = {r.feeder_id: r.action for r in results}
    for i in range(3):
        assert actions[i] == "PERMIT", f"Feeder-{i} should PERMIT, got {actions[i]}"

    print("PASS test_sympathetic_trip_healthy_permit")


def test_multi_feeder_scenario_library():
    """Library has 15 scenarios; spot-check group sizes."""
    lib = MultiFeederScenarioLibrary()
    assert len(lib) == 15

    grp_a = lib.get_by_group("SYMP_2F")
    grp_b = lib.get_by_group("SYMP_3F")
    grp_c = lib.get_by_group("GUARD")
    assert len(grp_a) == 5
    assert len(grp_b) == 5
    assert len(grp_c) == 5

    # All SYMP groups have expected BLOCK on feeder ≥1
    for s in grp_a + grp_b:
        assert "BLOCK" in s.expected_actions, (
            f"Scenario {s.id} should have BLOCK in expected_actions"
        )

    print("PASS test_multi_feeder_scenario_library")


# ===========================================================================
# TR-79: N-2 Degraded-Grid Protection
# ===========================================================================

def test_topology_detection():
    """TopologyDetector maps z_factor correctly to N-x levels."""
    td = TopologyDetector(z_nominal=0.050)

    # N-0: z_line ≈ nominal
    topo = td.update(t=0.0, ekf_state={'z_line': 0.050, 'k_ibr': 0.60, 'f_gfm': 0.50})
    assert topo.degradation_level == "NORMAL", f"Expected NORMAL, got {topo.degradation_level}"
    assert topo.n_elements_lost == 0

    # N-1: z_line ~40% increase
    topo1 = td.update(t=0.1, ekf_state={'z_line': 0.068, 'k_ibr': 0.55, 'f_gfm': 0.45})
    assert topo1.degradation_level == "N-1", f"Expected N-1, got {topo1.degradation_level}"

    # N-2: z_line ~90% increase
    topo2 = td.update(t=0.2, ekf_state={'z_line': 0.092, 'k_ibr': 0.50, 'f_gfm': 0.40})
    assert topo2.degradation_level == "N-2", f"Expected N-2, got {topo2.degradation_level}"

    # N-3: z_line > 2.2×
    topo3 = td.update(t=0.3, ekf_state={'z_line': 0.120, 'k_ibr': 0.25, 'f_gfm': 0.10})
    assert topo3.degradation_level == "N-3", f"Expected N-3, got {topo3.degradation_level}"

    # IBR curtailment: k_ibr drops by >0.20
    td2 = TopologyDetector(z_nominal=0.050, k_ibr_nominal=0.60)
    td2.update(t=0.0, ekf_state={'z_line': 0.050, 'k_ibr': 0.60, 'f_gfm': 0.50})
    topo_curt = td2.update(t=0.1, ekf_state={'z_line': 0.070, 'k_ibr': 0.30, 'f_gfm': 0.30})
    assert topo_curt.ibr_curtailed, "k_ibr drop > 0.20 should flag IBR curtailment"

    print("PASS test_topology_detection")


def test_adaptive_settings_n2():
    """N-2 topology → reach increases, pickup decreases, time dial increases."""
    td  = TopologyDetector(z_nominal=0.050)
    asc = AdaptiveSettingCalculator(reach_nom=0.85, pickup_nom=1.50, time_dial_nom=0.20)

    topo_n2 = td.update(t=0.0, ekf_state={'z_line': 0.092, 'k_ibr': 0.50, 'f_gfm': 0.40})
    settings = asc.calculate(topo_n2)

    assert settings.reach_pu > 0.85,  f"N-2 reach {settings.reach_pu:.3f} should exceed nominal 0.85"
    assert settings.pickup_pu < 1.50, f"N-2 pickup {settings.pickup_pu:.3f} should be below nominal 1.50"
    assert settings.time_dial > 0.20, f"N-2 time_dial {settings.time_dial:.3f} should exceed 0.20"
    assert 0.0 <= settings.confidence <= 1.0

    # N-0: settings should be close to nominal
    topo_n0 = td.update(t=0.1, ekf_state={'z_line': 0.050, 'k_ibr': 0.60, 'f_gfm': 0.50})
    settings_n0 = asc.calculate(topo_n0)
    assert abs(settings_n0.time_dial - 0.20) < 0.01, (
        f"N-0 time_dial {settings_n0.time_dial} should be ~0.20"
    )

    print("PASS test_adaptive_settings_n2")


def test_degraded_grid_scenario_library():
    """Library has 20 scenarios; N-2 group has 7; integration check ≥90%."""
    lib = DegradedGridScenarioLibrary()
    assert len(lib) == 20

    n2_group = lib.get_by_group("N2_DUAL")
    assert len(n2_group) == 7, f"Expected 7 N-2 scenarios, got {len(n2_group)}"

    td  = TopologyDetector(z_nominal=0.050)
    asc = AdaptiveSettingCalculator()

    agree = 0
    for s in lib:
        topo = td.update(t=0.0, ekf_state={
            'z_line': s.z_line_pu, 'k_ibr': s.k_ibr, 'f_gfm': s.f_gfm,
        })
        settings = asc.calculate(topo)
        level_ok = (topo.degradation_level == s.expected_level)
        reach_ok = (settings.reach_pu > 0.85) == s.expect_reach_increase or not s.expect_reach_increase
        if level_ok and reach_ok:
            agree += 1

    rate = agree / len(lib)
    assert rate >= 0.90, f"Degraded-grid agree rate {rate:.2f} < 0.90"

    print(f"PASS test_degraded_grid_scenario_library (agree={rate:.2%})")


def test_n2_reach_cap():
    """Reach never exceeds 2× nominal regardless of z_factor."""
    td  = TopologyDetector(z_nominal=0.050)
    asc = AdaptiveSettingCalculator(reach_nom=0.85)

    # Extreme degradation
    topo = td.update(t=0.0, ekf_state={'z_line': 0.300, 'k_ibr': 0.10, 'f_gfm': 0.05})
    settings = asc.calculate(topo)
    assert settings.reach_pu <= 2.0 * 0.85 + 1e-6, (
        f"Reach {settings.reach_pu:.3f} exceeds 2× nominal cap"
    )

    print("PASS test_n2_reach_cap")


# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    # TR-77
    test_open_conductor_detection()
    test_fuse_failure_scenario_library()
    test_open_conductor_ambiguous()

    # TR-78
    test_sympathetic_trip_block()
    test_sympathetic_trip_healthy_permit()
    test_multi_feeder_scenario_library()

    # TR-79
    test_topology_detection()
    test_adaptive_settings_n2()
    test_degraded_grid_scenario_library()
    test_n2_reach_cap()

    print("\nAll TR-77/78/79 tests passed.")
