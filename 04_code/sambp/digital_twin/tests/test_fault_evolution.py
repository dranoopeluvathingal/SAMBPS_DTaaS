# =============================================================================
# tests/test_fault_evolution.py
#
# Unit tests for TR-72: evolving fault detector, cross-country classifier,
# and adaptive relay update manager.
#
# Tests
# -----
#   1. test_slg_to_dlg_detection       — SLG→DLG within 2 cycles (40 ms @ 1 kHz)
#   2. test_intermittent_fault         — repeated open-close fires INT event
#   3. test_cross_country              — two simultaneously faulted feeders detected
#   4. test_adaptive_relay_update      — on_evolution_event pushes scaled settings
#   5. test_no_false_evolution         — steady SLG emits no spurious events
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from estimation.fault_evolution import FaultEvolutionDetector, FaultEvolutionEvent
from models.cross_country_scenario import (
    CrossCountryClassifier,
    CrossCountryScenarioLibrary,
)
from coordination.adaptive_update import AdaptiveUpdateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slg_state(k: float = 0.18, alpha: float = 0.60, residual: float = 0.08) -> dict:
    """EKF state consistent with a single-line-to-ground fault.
    alpha=0.60 → i_neg=0.20 (0.12<i_neg<0.35 → SLG classifier)."""
    return {"k_ibr": k, "z_line": 0.050, "alpha": alpha, "f_gfm": 0.50,
            "residual": residual, "kappa_n": 8.0, "n_updates": 1}


def _dlg_state(k: float = 0.13, alpha: float = 0.78, residual: float = 0.28) -> dict:
    """EKF state consistent with a double-line-to-ground fault.
    alpha=0.78 → i_neg=0.56 (>0.35) and residual=0.28 (>0.15) → DLG classifier."""
    return {"k_ibr": k, "z_line": 0.050, "alpha": alpha, "f_gfm": 0.50,
            "residual": residual, "kappa_n": 9.0, "n_updates": 1}


def _healthy_state(k: float = 0.20) -> dict:
    """EKF state in healthy (pre-fault) condition."""
    return {"k_ibr": k, "z_line": 0.050, "alpha": 0.50, "f_gfm": 0.50,
            "residual": 0.01, "kappa_n": 5.0, "n_updates": 1}


def _run_stream(det: FaultEvolutionDetector, states: list[dict],
                dt: float = 1e-3) -> list[FaultEvolutionEvent]:
    """Feed a list of states to the detector; collect all non-None events."""
    events = []
    for i, st in enumerate(states):
        t = i * dt
        evt = det.update(t, st)
        if evt is not None:
            events.append(evt)
    return events


# ---------------------------------------------------------------------------
# Test 1: SLG → DLG detection within 2 cycles
# ---------------------------------------------------------------------------

def test_slg_to_dlg_detection():
    """
    Inject 30 SLG samples then 30 DLG samples.
    Expect a SLG→DLG event within the first 40 DLG samples (≤ 40 ms at 1 kHz).
    """
    det = FaultEvolutionDetector(cusum_h=3.0)

    # warm-up: 5 healthy samples to set baseline
    for i in range(5):
        det.update(i * 1e-3, _healthy_state())

    # 30 SLG samples
    slg_stream = [_slg_state() for _ in range(30)]
    events_slg = _run_stream(det, slg_stream, dt=1e-3)

    # 40 DLG samples
    dlg_stream = [_dlg_state() for _ in range(40)]
    t0 = 35 * 1e-3
    events_dlg = []
    for j, st in enumerate(dlg_stream):
        t = t0 + j * 1e-3
        evt = det.update(t, st)
        if evt is not None:
            events_dlg.append((j, evt))

    # At least one SLG→DLG event must be detected within 40 samples (2 cycles)
    slg_dlg = [(j, e) for j, e in events_dlg
               if e.from_type == "SLG" and e.to_type == "DLG"]
    assert slg_dlg, "Expected SLG→DLG event within 40 DLG samples"
    first_j = slg_dlg[0][0]
    assert first_j <= 40, f"Detection too slow: {first_j} samples"
    # Confidence must be reasonable
    assert slg_dlg[0][1].confidence >= 0.50


# ---------------------------------------------------------------------------
# Test 2: Intermittent fault detection
# ---------------------------------------------------------------------------

def test_intermittent_fault():
    """
    Simulate two fault-clear cycles within 40 ms.
    Expect an INT event (intermittent) to be emitted.
    """
    det = FaultEvolutionDetector(cusum_h=3.0)

    # baseline
    for i in range(10):
        det.update(i * 1e-3, _healthy_state())

    events = []
    t = 10e-3

    # cycle 1: fault ON (25 samples to fill window) then OFF (15 samples)
    for _ in range(25):
        e = det.update(t, _slg_state()); t += 1e-3
        if e: events.append(e)
    for _ in range(15):
        e = det.update(t, _healthy_state(k=0.20)); t += 1e-3
        if e: events.append(e)

    # cycle 2: fault ON again (25 samples)
    for _ in range(25):
        e = det.update(t, _slg_state(k=0.17)); t += 1e-3
        if e: events.append(e)

    int_events = [e for e in events if e.to_type == "INT"]
    assert int_events, f"Expected INT event; got {[e.to_type for e in events]}"
    assert int_events[0].confidence >= 0.50


# ---------------------------------------------------------------------------
# Test 3: Cross-country fault detection
# ---------------------------------------------------------------------------

def test_cross_country():
    """
    Feed simultaneous fault states on feeders 0 and 1.
    Expect CrossCountryResult within 5 update cycles.
    """
    clf = CrossCountryClassifier(n_feeders=2)

    # warm-up: 20 healthy samples on both feeders
    for i in range(20):
        clf.update(i * 1e-3, {0: _healthy_state(0.20), 1: _healthy_state(0.22)})

    # simultaneous SLG on both feeders
    results = []
    for j in range(10):
        t = (20 + j) * 1e-3
        r = clf.update(t, {
            0: _slg_state(k=0.14, alpha=0.72),
            1: _slg_state(k=0.13, alpha=0.75, residual=0.15),
        })
        if r is not None:
            results.append(r)

    assert results, "Expected CrossCountryResult for simultaneous SLG"
    assert results[0].feeder_a == 0
    assert results[0].feeder_b == 1
    assert results[0].confidence >= 0.55

    # Verify scenario library has 30 entries
    lib = CrossCountryScenarioLibrary()
    scenarios = lib.all()
    assert len(scenarios) == 30
    cc = [s for s in scenarios if s.expected_cc]
    assert len(cc) >= 15, "At least 15 scenarios should be cross-country"


# ---------------------------------------------------------------------------
# Test 4: Adaptive relay update
# ---------------------------------------------------------------------------

def test_adaptive_relay_update():
    """
    Fire a SLG→DLG event with high confidence.
    Expect the manager to return scaled settings (pickup reduced, reach extended).
    """

    class _MockRelay:
        def __init__(self):
            self.pushed = []
        def push_settings(self, s):
            self.pushed.append(dict(s))

    relay = _MockRelay()
    mgr   = AdaptiveUpdateManager(relay_interface=relay, min_confidence=0.60)

    settings = {"pickup": 1.20, "time_dial": 0.50, "reach": 0.80}
    evt = FaultEvolutionEvent(
        timestamp=0.100, from_type="SLG", to_type="DLG", confidence=0.82
    )
    new_s = mgr.on_evolution_event(evt, settings)

    assert new_s is not None, "Expected settings push for high-confidence SLG→DLG"
    assert new_s["pickup"] < settings["pickup"], "Pickup should decrease"
    assert new_s["reach"]  > settings["reach"],  "Reach should increase"
    assert len(relay.pushed) == 1
    assert len(mgr.audit_log) == 1
    assert mgr.audit_log[0].accepted is True

    # Low-confidence event should be ignored
    evt_low = FaultEvolutionEvent(0.150, "DLG", "3PH", confidence=0.40)
    result_low = mgr.on_evolution_event(evt_low, settings)
    assert result_low is None, "Low-confidence event must not trigger push"


# ---------------------------------------------------------------------------
# Test 5: No false evolution on steady fault
# ---------------------------------------------------------------------------

def test_no_false_evolution():
    """
    100 steady SLG samples should produce no SLG→DLG or SLG→3PH events.
    Small noise is acceptable but should not trigger a type-change event.
    """
    import random
    rng = random.Random(42)
    det = FaultEvolutionDetector(cusum_h=5.0, min_conf=0.70)

    # baseline
    for i in range(10):
        det.update(i * 1e-3, _healthy_state())

    false_evolutions = []
    for j in range(100):
        # steady SLG with tiny noise
        noise = rng.gauss(0, 0.002)
        st = _slg_state(k=0.18 + noise, alpha=0.70 + noise * 0.5)
        evt = det.update((10 + j) * 1e-3, st)
        if evt is not None and evt.from_type != "NONE" and evt.to_type not in ("RST", "INT"):
            false_evolutions.append(evt)

    assert not false_evolutions, (
        f"False evolution events on steady SLG: "
        f"{[(e.from_type, e.to_type) for e in false_evolutions]}"
    )
