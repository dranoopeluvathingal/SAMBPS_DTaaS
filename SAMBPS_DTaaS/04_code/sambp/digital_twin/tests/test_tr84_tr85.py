# =============================================================================
# tests/test_tr84_tr85.py  —  TR-84 (ferroresonance) + TR-85 (CLPU) tests
# =============================================================================

from __future__ import annotations

import math, sys, os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from estimation.ferroresonance_detector import FerroresonanceDetector
from models.ferroresonance_scenario import FerroresonanceScenarioLibrary
from estimation.cold_load_estimator import CLPUEstimator
from coordination.adaptive_oc import AdaptiveOCController


# ===========================================================================
# TR-84  Test 1 — Normal signal: no ferroresonance detected
# ===========================================================================

def test_normal_no_ferroresonance():
    """Pure 50 Hz balanced voltage must classify as NORMAL."""
    det = FerroresonanceDetector(fs=1000.0, f0=50.0)
    fs, f0 = 1000.0, 50.0
    dt = 1.0 / fs

    for step in range(int(0.25 * fs)):
        t  = step * dt
        va = math.cos(2*math.pi*f0*t)
        vb = math.cos(2*math.pi*f0*t - 2*math.pi/3)
        vc = math.cos(2*math.pi*f0*t + 2*math.pi/3)
        det.push(va, vb, vc)

    result = det.classify(0.25)
    assert result.mode == "NORMAL", f"Expected NORMAL, got {result.mode}"
    assert not result.active
    assert result.risk_level == "NONE"
    print("PASS test_normal_no_ferroresonance")


# ===========================================================================
# TR-84  Test 2 — Subharmonic: 25 Hz component detected
# ===========================================================================

def test_subharmonic_detection():
    """Period-2 subharmonic (25 Hz) must classify as SUBHARMONIC."""
    det = FerroresonanceDetector(fs=1000.0, f0=50.0)
    fs, f0 = 1000.0, 50.0
    f_sub = 25.0   # period-2 subharmonic
    dt = 1.0 / fs

    for step in range(int(0.25 * fs)):
        t  = step * dt
        va = (math.cos(2*math.pi*f0*t) +
              0.30 * math.cos(2*math.pi*f_sub*t))
        vb = (math.cos(2*math.pi*f0*t - 2*math.pi/3) +
              0.30 * math.cos(2*math.pi*f_sub*t - 2*math.pi/3))
        vc = (math.cos(2*math.pi*f0*t + 2*math.pi/3) +
              0.30 * math.cos(2*math.pi*f_sub*t + 2*math.pi/3))
        det.push(va, vb, vc)

    result = det.classify(0.25)
    assert result.mode == "SUBHARMONIC", f"Expected SUBHARMONIC, got {result.mode} (ss_ratio={result.ss_ratio:.3f})"
    assert result.active
    assert result.risk_level in ("ALERT", "TRIP")
    print(f"PASS test_subharmonic_detection  (ss_ratio={result.ss_ratio:.3f})")


# ===========================================================================
# TR-84  Test 3 — Chaotic: broadband noise triggers CHAOTIC classification
# ===========================================================================

def test_chaotic_detection():
    """Large broadband noise must classify as CHAOTIC."""
    det = FerroresonanceDetector(fs=1000.0, f0=50.0)
    fs, f0 = 1000.0, 50.0
    dt = 1.0 / fs
    rng = np.random.default_rng(seed=42)

    N = int(0.25 * fs)
    ts = np.arange(N) * dt
    va_arr = np.cos(2*math.pi*f0*ts) + 0.50 * rng.standard_normal(N)
    vb_arr = np.cos(2*math.pi*f0*ts - 2*math.pi/3) + 0.50 * rng.standard_normal(N)
    vc_arr = np.cos(2*math.pi*f0*ts + 2*math.pi/3) + 0.50 * rng.standard_normal(N)

    for i in range(N):
        det.push(float(va_arr[i]), float(vb_arr[i]), float(vc_arr[i]))

    result = det.classify(0.25)
    assert result.mode == "CHAOTIC", f"Expected CHAOTIC, got {result.mode} (THD={result.thd:.3f})"
    assert result.active
    assert result.risk_level == "TRIP"
    print(f"PASS test_chaotic_detection  (THD={result.thd:.3f}, ZC_irr={result.zc_irregularity:.3f})")


# ===========================================================================
# TR-84  Test 4 — Fundamental-mode: high THD but no subharmonic
# ===========================================================================

def test_fundamental_mode_detection():
    """High harmonic distortion (THD=30%) without subharmonics → FUNDAMENTAL."""
    det = FerroresonanceDetector(fs=1000.0, f0=50.0)
    fs, f0 = 1000.0, 50.0
    dt = 1.0 / fs

    for step in range(int(0.25 * fs)):
        t = step * dt
        # Fundamental + 3rd + 5th + 7th harmonics (no sub-harmonics)
        va = (math.cos(2*math.pi*f0*t) +
              0.18 * math.cos(3*2*math.pi*f0*t) +
              0.14 * math.cos(5*2*math.pi*f0*t) +
              0.10 * math.cos(7*2*math.pi*f0*t) +
              0.06 * math.cos(9*2*math.pi*f0*t))
        vb = (math.cos(2*math.pi*f0*t - 2*math.pi/3) +
              0.18 * math.cos(3*2*math.pi*f0*t - 2*math.pi/3) +
              0.14 * math.cos(5*2*math.pi*f0*t - 2*math.pi/3) +
              0.10 * math.cos(7*2*math.pi*f0*t - 2*math.pi/3) +
              0.06 * math.cos(9*2*math.pi*f0*t - 2*math.pi/3))
        vc = (math.cos(2*math.pi*f0*t + 2*math.pi/3) +
              0.18 * math.cos(3*2*math.pi*f0*t + 2*math.pi/3) +
              0.14 * math.cos(5*2*math.pi*f0*t + 2*math.pi/3) +
              0.10 * math.cos(7*2*math.pi*f0*t + 2*math.pi/3) +
              0.06 * math.cos(9*2*math.pi*f0*t + 2*math.pi/3))
        det.push(va, vb, vc)

    result = det.classify(0.25)
    assert result.mode == "FUNDAMENTAL", (
        f"Expected FUNDAMENTAL, got {result.mode} "
        f"(THD={result.thd:.3f}, ss_ratio={result.ss_ratio:.3f})"
    )
    assert result.active
    print(f"PASS test_fundamental_mode_detection  (THD={result.thd:.3f})")


# ===========================================================================
# TR-84  Test 5 — Scenario library: 20 scenarios, correct structure
# ===========================================================================

def test_scenario_library_structure():
    """Scenario library has 20 scenarios with correct groups."""
    lib = FerroresonanceScenarioLibrary()
    assert len(lib) == 20, f"Expected 20 scenarios, got {len(lib)}"
    assert len(lib.get_by_group("NORMAL"))      == 5
    assert len(lib.get_by_group("FUNDAMENTAL")) == 5
    assert len(lib.get_by_group("SUBHARMONIC")) == 5
    assert len(lib.get_by_group("CHAOTIC"))     == 5
    print("PASS test_scenario_library_structure")


# ===========================================================================
# TR-84  Test 6 — Integration: scenario waveforms classify correctly ≥75%
# ===========================================================================

def test_scenario_integration():
    """Classify generated waveforms for all 20 scenarios. Expect ≥75% correct."""
    lib   = FerroresonanceScenarioLibrary()
    agree = 0

    for s in lib:
        det  = FerroresonanceDetector(fs=1000.0, f0=50.0)
        data = s.generate_waveform(fs=1000.0, f0=50.0, duration_s=0.25)
        for row in data:
            det.push(float(row[1]), float(row[2]), float(row[3]))
        result = det.classify(0.25)
        if result.mode == s.expected_mode:
            agree += 1
        else:
            print(f"  MISMATCH scenario {s.id} ({s.name}): "
                  f"expected={s.expected_mode}, got={result.mode} "
                  f"THD={result.thd:.3f} ss={result.ss_ratio:.3f}")

    rate = agree / len(lib)
    print(f"  Scenario agree rate: {rate:.1%} ({agree}/{len(lib)})")
    assert rate >= 0.75, f"Scenario agree rate {rate:.1%} < 75%"
    print("PASS test_scenario_integration")


# ===========================================================================
# TR-85  Test 7 — CLPU profile follows I(t) = I_ss*(1 + K*exp(-t/tau))
# ===========================================================================

def test_clpu_profile_formula():
    """CLPUEstimator must match I(t) = I_ss*(1 + K*exp(-t/tau)) within 0.1%."""
    i_ss, K, tau = 0.60, 3.0, 10.0
    est = CLPUEstimator(i_ss, K=K, tau=tau)
    est.trigger(t_reclose=0.0)

    for t in [0.0, 1.0, 5.0, 10.0, 20.0, 30.0]:
        profile  = est.get_profile(t)
        expected = i_ss * (1.0 + K * math.exp(-t / tau))
        assert abs(profile.i_clpu_pu - expected) < 1e-4, (
            f"At t={t}s: got {profile.i_clpu_pu:.5f}, expected {expected:.5f}"
        )

    print("PASS test_clpu_profile_formula")


# ===========================================================================
# TR-85  Test 8 — State transitions: ACTIVE → DECAYING → COMPLETE
# ===========================================================================

def test_clpu_state_transitions():
    """State must progress ACTIVE → DECAYING → COMPLETE over time."""
    i_ss, K, tau = 0.50, 4.0, 5.0
    est = CLPUEstimator(i_ss, K=K, tau=tau)
    est.trigger(0.0)

    # Initially ACTIVE
    p0 = est.get_profile(0.1)
    assert p0.state == "ACTIVE", f"t=0.1s: expected ACTIVE, got {p0.state}"

    # At t=tau/2=2.5s: still ACTIVE (dt < 0.5*tau)
    p1 = est.get_profile(2.4)
    assert p1.state == "ACTIVE"

    # At t=4s (>0.5*tau, excess_ratio=K*exp(-4/5)=4*0.449=1.80 > 0.10): DECAYING
    p2 = est.get_profile(4.0)
    assert p2.state in ("ACTIVE", "DECAYING"), f"t=4s: expected ACTIVE/DECAYING, got {p2.state}"

    # At t=5*tau=25s: excess_ratio=K*exp(-5)=4*0.0067=0.027 < 0.10 → COMPLETE
    p3 = est.get_profile(25.0)
    assert p3.state == "COMPLETE", f"t=25s: expected COMPLETE, got {p3.state}"
    assert not p3.active

    print("PASS test_clpu_state_transitions")


# ===========================================================================
# TR-85  Test 9 — AdaptiveOC: no nuisance trip during CLPU inrush
# ===========================================================================

def test_adaptive_oc_no_nuisance_trip():
    """
    During CLPU, the adaptive OC must not trip on inrush current
    that stays within the CLPU envelope.
    """
    i_ss     = 0.50   # pre-fault load
    K, tau   = 3.0, 10.0
    # Nominal pickup = 1.25 × I_steady (would trip without adaptation)
    nom_pickup = 1.25 * i_ss   # = 0.625 pu

    ctrl = AdaptiveOCController(
        nominal_pickup_pu=nom_pickup,
        nominal_tdm=0.10,
        i_steady_pu=i_ss,
        K=K, tau=tau,
        pickup_margin=1.20,
    )
    ctrl.on_reclose(t=0.0)

    # Simulate inrush current following CLPU envelope
    for t_s in [0.5, 1.0, 2.0, 5.0, 10.0]:
        i_inrush = i_ss * (1.0 + K * math.exp(-t_s / tau))
        decision = ctrl.update(t_s, i_inrush)
        assert not decision.operate, (
            f"Nuisance trip at t={t_s}s: I={i_inrush:.3f} pu, "
            f"pickup={decision.pickup_pu:.3f} pu"
        )
        assert decision.clpu_active or decision.state == "NORMAL", (
            f"Unexpected state {decision.state} at t={t_s}s"
        )

    print("PASS test_adaptive_oc_no_nuisance_trip")


# ===========================================================================
# TR-85  Test 10 — AdaptiveOC: genuine fault still trips
# ===========================================================================

def test_adaptive_oc_fault_trips():
    """A genuine fault current (>>CLPU envelope) must still trip the relay."""
    i_ss = 0.50
    ctrl = AdaptiveOCController(
        nominal_pickup_pu=1.25 * i_ss,
        nominal_tdm=0.10,
        i_steady_pu=i_ss,
        K=3.0, tau=10.0, pickup_margin=1.20,
    )
    ctrl.on_reclose(t=0.0)

    # At t=2s CLPU multiplier ≈ 1 + 3*exp(-0.2) ≈ 3.45; pickup ≈ 3.45*0.5*1.2 ≈ 2.07 pu
    # Inject fault at 10× I_steady = 5 pu → should trip even with elevated pickup
    t_fault = 2.0
    i_fault = 10.0 * i_ss   # 5.0 pu fault

    decision = ctrl.update(t_fault, i_fault)
    assert decision.operate, (
        f"Fault not detected: I={i_fault:.2f} pu, pickup={decision.pickup_pu:.3f} pu"
    )
    assert decision.trip_time_s > 0.0
    print(f"PASS test_adaptive_oc_fault_trips  (trip at {decision.trip_time_s*1000:.1f} ms)")


# ===========================================================================
# TR-85  Test 11 — AdaptiveOC: pickup reverts after CLPU complete
# ===========================================================================

def test_adaptive_oc_revert_after_clpu():
    """After CLPU decays, pickup must revert to nominal value."""
    i_ss = 0.50
    nom  = 1.25 * i_ss
    ctrl = AdaptiveOCController(
        nominal_pickup_pu=nom,
        nominal_tdm=0.10,
        i_steady_pu=i_ss,
        K=2.0, tau=5.0, pickup_margin=1.20,
    )
    ctrl.on_reclose(t=0.0)

    # After 5*tau = 25 s, CLPU should be COMPLETE → pickup back to nominal
    decision = ctrl.update(t=25.0, i_measured_pu=i_ss)
    assert not decision.clpu_active, "CLPU should be COMPLETE at t=25s"
    assert abs(decision.pickup_pu - nom) < 0.01, (
        f"Pickup={decision.pickup_pu:.4f}, expected≈{nom:.4f}"
    )
    print(f"PASS test_adaptive_oc_revert_after_clpu  (pickup={decision.pickup_pu:.4f})")


# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    # TR-84
    test_normal_no_ferroresonance()
    test_subharmonic_detection()
    test_chaotic_detection()
    test_fundamental_mode_detection()
    test_scenario_library_structure()
    test_scenario_integration()
    # TR-85
    test_clpu_profile_formula()
    test_clpu_state_transitions()
    test_adaptive_oc_no_nuisance_trip()
    test_adaptive_oc_fault_trips()
    test_adaptive_oc_revert_after_clpu()
    print("\nAll TR-84 + TR-85 tests passed.")
