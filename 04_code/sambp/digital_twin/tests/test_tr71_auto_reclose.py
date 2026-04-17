# =============================================================================
# tests/test_tr71_auto_reclose.py  —  TR-71 auto-reclose sequencing tests
# =============================================================================

import math
import cmath
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from estimation.dead_time_estimator import DeadTimeEstimator
from coordination.auto_reclose import AutoRecloseController, predict_reclose_success
from coordination.sync_check_dt import SyncCheckRelay
from estimation.fault_evolution import FaultEvolutionEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ibr_state(k_ibr=0.80, f_gfm=0.60, z_line=0.040):
    return {'k_ibr': k_ibr, 'f_gfm': f_gfm, 'z_line': z_line}

def _sg_state(k_ibr=0.10, f_gfm=0.10, z_line=0.060):
    return {'k_ibr': k_ibr, 'f_gfm': f_gfm, 'z_line': z_line}

def _make_phasor(v_pu: float, angle_deg: float) -> complex:
    return cmath.rect(v_pu, math.radians(angle_deg))

def _make_evolution_event(to_type: str, confidence: float = 0.80) -> FaultEvolutionEvent:
    return FaultEvolutionEvent(
        timestamp=0.1,
        from_type="SLG",
        to_type=to_type,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Test 1: dead_time_estimation
# ---------------------------------------------------------------------------

def test_dead_time_estimation():
    est = DeadTimeEstimator()

    # IBR-dominated: high k_ibr → fast voltage collapse → shorter dead time (shot 1)
    dt_ibr = est.estimate(_ibr_state(k_ibr=0.90, f_gfm=0.10), "SLG", shot_number=1)
    est.reset()

    # SG-dominated: low k_ibr → slow de-magnetisation → longer dead time (shot 1)
    dt_sg = est.estimate(_sg_state(k_ibr=0.05, f_gfm=0.00), "SLG", shot_number=1)
    est.reset()

    assert dt_ibr.t_dead_s < dt_sg.t_dead_s, (
        f"IBR dead time {dt_ibr.t_dead_s:.3f}s should be < SG dead time {dt_sg.t_dead_s:.3f}s"
    )

    # Shot 2 must be ≥ 3× shot 1 (IEC 62271-100)
    dt_s1 = est.estimate(_ibr_state(), "SLG", shot_number=1)
    est.reset()
    dt_s2 = est.estimate(_ibr_state(), "SLG", shot_number=2)
    est.reset()

    assert dt_s2.t_dead_s >= 2.9 * dt_s1.t_dead_s, (
        f"Shot-2 dead time {dt_s2.t_dead_s:.3f}s should be ≥ 3× shot-1 {dt_s1.t_dead_s:.3f}s"
    )

    # 3PH fault needs longer dead time than SLG
    dt_slg = est.estimate(_ibr_state(), "SLG", shot_number=1)
    est.reset()
    dt_3ph = est.estimate(_ibr_state(), "3PH", shot_number=1)
    est.reset()

    assert dt_3ph.t_dead_s >= dt_slg.t_dead_s, (
        f"3PH dead time {dt_3ph.t_dead_s:.3f}s should be ≥ SLG {dt_slg.t_dead_s:.3f}s"
    )

    # Confidence is a valid float in [0,1]
    assert 0.0 <= dt_s1.confidence <= 1.0

    print("PASS test_dead_time_estimation")


# ---------------------------------------------------------------------------
# Test 2: reclose_success_prediction
# ---------------------------------------------------------------------------

def test_reclose_success_prediction():
    # High-voltage, low fault current (low k_ibr proxy), shot 1 → high P(success)
    p_good = predict_reclose_success(
        ekf_state={'k_ibr': 0.20, 'f_gfm': 0.30, 'z_line': 0.030},
        v_terminal_pu=0.95,
        shot_number=1,
        n_shots=3,
    )

    # Low voltage, high fault current (high k_ibr proxy), shot 3 → lower P(success)
    p_bad = predict_reclose_success(
        ekf_state={'k_ibr': 0.90, 'f_gfm': 0.80, 'z_line': 0.010},
        v_terminal_pu=0.20,
        shot_number=3,
        n_shots=3,
    )

    assert 0.0 <= p_good <= 1.0
    assert 0.0 <= p_bad  <= 1.0
    assert p_good > p_bad, (
        f"P(success|good)={p_good:.3f} should exceed P(success|bad)={p_bad:.3f}"
    )

    # Shot 1 should have higher predicted success than shot 3 (same conditions)
    state = {'k_ibr': 0.40, 'f_gfm': 0.40, 'z_line': 0.040}
    p_shot1 = predict_reclose_success(state, 0.90, 1, 3)
    p_shot3 = predict_reclose_success(state, 0.90, 3, 3)
    assert p_shot1 > p_shot3, (
        f"Shot-1 P={p_shot1:.3f} should exceed shot-3 P={p_shot3:.3f}"
    )

    print("PASS test_reclose_success_prediction")


# ---------------------------------------------------------------------------
# Test 3: sync_check
# ---------------------------------------------------------------------------

def test_sync_check():
    rel = SyncCheckRelay(delta_v_max=0.10, delta_f_max=0.20, delta_angle_max=20.0)

    # In-sync: same phasor → PERMIT
    phasor = _make_phasor(1.00, 0.0)
    r = rel.check(phasor, phasor, ekf_state=None, f_bus=50.0, f_line=50.0)
    assert r.permit, f"Identical phasors should PERMIT, got reason={r.reason}"
    assert r.margin >= 0.99

    # Voltage mismatch exceeds threshold → BLOCK
    bus  = _make_phasor(1.00,  0.0)
    line = _make_phasor(0.85,  0.0)   # ΔV = 0.15 > 0.10
    r = rel.check(bus, line, f_bus=50.0, f_line=50.0)
    assert not r.permit
    assert "ΔV" in r.reason

    # Frequency mismatch exceeds threshold → BLOCK
    bus  = _make_phasor(1.00, 0.0)
    line = _make_phasor(1.00, 0.0)
    r = rel.check(bus, line, f_bus=50.0, f_line=50.35)   # Δf=0.35 > 0.20
    assert not r.permit
    assert "Δf" in r.reason

    # Angle mismatch exceeds threshold → BLOCK
    bus  = _make_phasor(1.00,  0.0)
    line = _make_phasor(1.00, 25.0)   # Δδ=25° > 20°
    r = rel.check(bus, line, f_bus=50.0, f_line=50.0)
    assert not r.permit
    assert "Δδ" in r.reason

    # GFM angle stiffening: high f_gfm reduces effective Δδ
    ekf_stiff = {'f_gfm': 1.0}   # maximum stiffening
    bus  = _make_phasor(1.00,  0.0)
    line = _make_phasor(1.00, 25.0)   # raw 25° but GFM stiffening applied
    r_stiff = rel.check(bus, line, ekf_state=ekf_stiff, f_bus=50.0, f_line=50.0)

    r_no_stiff = rel.check(bus, line, ekf_state=None, f_bus=50.0, f_line=50.0)
    assert r_stiff.delta_angle_deg < r_no_stiff.delta_angle_deg, (
        "GFM stiffening should reduce effective Δδ"
    )

    # update_settings works
    rel.update_settings(delta_v_max=0.05)
    assert rel.delta_v_max == 0.05

    print("PASS test_sync_check")


# ---------------------------------------------------------------------------
# Test 4: reclose_blocking_on_evolving_fault
# ---------------------------------------------------------------------------

def test_reclose_blocking_on_evolving_fault():
    ctrl = AutoRecloseController(n_shots=3, p_success_threshold=0.30)
    ekf  = _ibr_state()

    # Trip at t=0.0
    act = ctrl.trip(t=0.0, ekf_state=ekf, fault_type="SLG")
    assert act.action == "START_DEAD_TIME"
    dead_time = act.dead_time_s

    # Advance to just after dead time — inject evolving fault DLG, confidence=0.80
    evt = _make_evolution_event(to_type="DLG", confidence=0.80)
    t_after = dead_time + 0.01
    act = ctrl.step(t=t_after, ekf_state=ekf, feeder_live=False,
                    v_terminal_pu=0.95, fault_type="SLG", evolution_event=evt)

    assert act.action == "BLOCK", (
        f"Expected BLOCK on evolving DLG fault, got action={act.action}"
    )
    assert act.blocked_by == "EVOLVING_FAULT"

    # Reset and verify no block without evolving event
    ctrl.reset()
    ctrl.trip(t=0.0, ekf_state=ekf, fault_type="SLG")
    act2 = ctrl.step(t=t_after, ekf_state=ekf, feeder_live=False,
                     v_terminal_pu=0.95, fault_type="SLG", evolution_event=None)
    assert act2.action == "RECLOSE", (
        f"Without evolving event expected RECLOSE, got {act2.action}"
    )

    # Low-confidence evolving event (<0.60) should NOT block
    ctrl.reset()
    ctrl.trip(t=0.0, ekf_state=ekf, fault_type="SLG")
    evt_low = _make_evolution_event(to_type="3PH", confidence=0.40)
    act3 = ctrl.step(t=t_after, ekf_state=ekf, feeder_live=False,
                     v_terminal_pu=0.95, fault_type="SLG", evolution_event=evt_low)
    assert act3.action == "RECLOSE", (
        f"Low-confidence evolving event should not block; got {act3.action}"
    )

    # 3-shot lockout sequence
    ctrl.reset()
    ctrl.trip(t=0.0, ekf_state=ekf, fault_type="SLG")
    # Force through 3 failed recloses
    ctrl.step(t=t_after, ekf_state=ekf, feeder_live=False)
    ctrl.on_reclose_result(t=t_after, success=False, ekf_state=ekf)
    # Shot 2
    dt2 = ctrl._t_dead
    ctrl.step(t=t_after + dt2 + 0.01, ekf_state=ekf, feeder_live=False)
    ctrl.on_reclose_result(t=t_after + dt2 + 0.01, success=False, ekf_state=ekf)
    # Shot 3
    dt3 = ctrl._t_dead
    ctrl.step(t=t_after + dt2 + dt3 + 0.02, ekf_state=ekf, feeder_live=False)
    ctrl.on_reclose_result(t=t_after + dt2 + dt3 + 0.02, success=False, ekf_state=ekf)

    assert ctrl.is_locked_out, "Should be locked out after 3 failed shots"

    print("PASS test_reclose_blocking_on_evolving_fault")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_dead_time_estimation()
    test_reclose_success_prediction()
    test_sync_check()
    test_reclose_blocking_on_evolving_fault()
    print("\nAll TR-71 tests passed.")
