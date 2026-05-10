"""tests/test_arc_kizilcay_smoke.py
=====================================

WP4.2 (P4.2) Kizilcay arc + cross-fit smoke tests.

Properties asserted:

1. ``ArcModelBase`` is an ABC; instantiating raises.
2. ``EmanuelArc`` and ``KizilcayArc`` both produce finite,
   correctly-signed current waveforms.
3. Near voltage zero crossings, the diode-arc current is hard zero
   while the Kizilcay-arc current is smooth and continuous --
   confirming the dynamic-conductance behaviour absent from the
   diode model.
4. The two arc currents differ structurally: peak shoulder shape +
   single-bin DFT phasor magnitudes are different.
5. ``KizilcayArc`` reproduces the documented ODE behaviour: the
   conductance dynamics produce an asymmetric rise/decay rate near
   the arc-zero passage (one of the canonical Kizilcay signatures).
6. The cross-fit CSV from the runner has the expected schema.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.models.faultloc_arc_models import (
    ArcModelBase,
    EmanuelArc,
    KizilcayArc,
    Torres2022Arc,
    Wang2020Arc,
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
CROSS_FIT_CSV = PROJ_ROOT / "outputs" / "phase4_arc_kizilcay_results.csv"

FS = 10_000.0
F0 = 50.0
N = 200
T = np.arange(N) / FS
V_PEAK = 11.0e3 * np.sqrt(2.0 / 3.0)


def _v_arc_clean() -> np.ndarray:
    return V_PEAK * np.cos(2.0 * np.pi * F0 * T)


# =============================================================================
# (1) ABC + class hierarchy
# =============================================================================

def test_arc_model_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        ArcModelBase()


def test_emanuel_and_kizilcay_are_arc_model_base() -> None:
    assert issubclass(EmanuelArc, ArcModelBase)
    assert issubclass(KizilcayArc, ArcModelBase)
    assert issubclass(Wang2020Arc, ArcModelBase)
    assert issubclass(Torres2022Arc, ArcModelBase)


# =============================================================================
# (2) Finite + correct sign
# =============================================================================

@pytest.mark.parametrize("Rx", [100.0, 1000.0, 5000.0])
def test_emanuel_current_finite_and_signed(Rx: float) -> None:
    v = _v_arc_clean()
    arc = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    i = arc.synthesise_current(T, v, Rx)
    assert i.shape == v.shape
    assert np.all(np.isfinite(i))
    # Current should be in phase with v at the peaks.
    peak_idx = int(np.argmax(v))
    assert i[peak_idx] > 0


@pytest.mark.parametrize("Rx", [100.0, 1000.0, 5000.0])
def test_kizilcay_current_finite_and_signed(Rx: float) -> None:
    v = _v_arc_clean()
    arc = KizilcayArc()
    i = arc.synthesise_current(T, v, Rx)
    assert i.shape == v.shape
    assert np.all(np.isfinite(i))
    peak_idx = int(np.argmax(v))
    assert i[peak_idx] > 0


def test_emanuel_input_validation() -> None:
    arc = EmanuelArc()
    v = _v_arc_clean()
    with pytest.raises(ValueError, match="Rx must be"):
        arc.synthesise_current(T, v, 0.0)


def test_kizilcay_input_validation() -> None:
    arc = KizilcayArc()
    v = _v_arc_clean()
    with pytest.raises(ValueError, match="Rx must be"):
        arc.synthesise_current(T, v, 0.0)
    with pytest.raises(ValueError, match="must have the same shape"):
        arc.synthesise_current(T, v[:50], 1000.0)


# =============================================================================
# (3) Current-zero deionisation behaviour
# =============================================================================

def test_emanuel_hard_zero_near_voltage_zero() -> None:
    """The diode arc has |i| == 0 in the |v| < V_kp window around
    the voltage zero crossing.  Sample 50 is the first v=0; samples
    45-55 span |v| < 1500 V which is well below V_kp = 2000."""
    v = _v_arc_clean()
    arc = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    i = arc.synthesise_current(T, v, Rx=1000.0)
    near_zero_v = np.abs(v[45:56])
    near_zero_i = np.abs(i[45:56])
    # All samples here have |v| < 1500 V, which is < V_kp = 2000;
    # diode is OFF so |i| should be < 1e-2 A (off-state leakage).
    assert near_zero_v.max() < 2000.0
    assert near_zero_i.max() < 1.0e-2, (
        f"Emanuel arc must be off near v=0; got max |i| = {near_zero_i.max()}"
    )


def test_kizilcay_smooth_through_voltage_zero() -> None:
    """The Kizilcay arc has smooth, continuous current through the
    voltage zero (the dynamic-conductance behaviour absent from the
    diode model).  |i| around v=0 must be MUCH larger than the
    diode-off floor and the trace must be monotonically decreasing
    on the approach to v=0."""
    v = _v_arc_clean()
    arc = KizilcayArc()
    i = arc.synthesise_current(T, v, Rx=1000.0)
    near_zero_v = np.abs(v[45:56])
    near_zero_i = np.abs(i[45:56])
    assert near_zero_v.max() < 2000.0
    # Kizilcay must conduct meaningfully here -- order of magnitude
    # 0.1 A or larger -- whereas Emanuel is < 1e-2 A.  Confirms the
    # arc is dynamically ionised through v=0.
    assert near_zero_i.max() > 0.1, (
        f"Kizilcay arc must conduct near v=0; got max |i| = {near_zero_i.max()}"
    )
    # Approach to v=0 should be monotonic in magnitude.
    approach = np.abs(i[45:50])
    assert np.all(np.diff(approach) <= 1.0e-3), (
        f"|i| must monotonically decrease toward v=0; got {approach}"
    )


# =============================================================================
# (4) Structural difference (Emanuel vs Kizilcay)
# =============================================================================

def test_emanuel_and_kizilcay_currents_differ_structurally() -> None:
    """Single-bin DFT phasor magnitudes at f0 differ by > 5 % --
    the structural arc-model-mismatch signature."""
    v = _v_arc_clean()
    Rx = 1000.0
    i_em = EmanuelArc(V_kp=2000.0, V_kn=1800.0).synthesise_current(T, v, Rx)
    i_ki = KizilcayArc().synthesise_current(T, v, Rx)
    Ns = N
    n = np.arange(Ns)
    k0 = int(round(F0 * Ns / FS))
    Ip_em = (2.0 / Ns) * np.sum(i_em * np.exp(-1j * 2 * np.pi * k0 * n / Ns))
    Ip_ki = (2.0 / Ns) * np.sum(i_ki * np.exp(-1j * 2 * np.pi * k0 * n / Ns))
    rel = abs(abs(Ip_em) - abs(Ip_ki)) / max(abs(Ip_em), 1e-12)
    assert rel > 0.05, (
        f"single-bin DFT phasor magnitudes should differ by > 5 %; "
        f"|Ip_em| = {abs(Ip_em):.3f}, |Ip_ki| = {abs(Ip_ki):.3f}, "
        f"relative diff = {rel:.4f}"
    )


# =============================================================================
# (5) Asymmetric rise/decay from dynamic conductance
# =============================================================================

def test_kizilcay_asymmetric_rise_vs_decay() -> None:
    """Kizilcay's conductance dynamics produce an asymmetric rise vs
    decay rate around the half-cycle peak (because g responds with
    time constant tau to the heating term).  The local rise rate
    just AFTER a current zero differs from the decay rate just
    BEFORE the next current zero."""
    v = _v_arc_clean()
    arc = KizilcayArc()
    i = arc.synthesise_current(T, v, Rx=1000.0)
    # Sample 0: positive peak; sample 50: zero crossing;
    # sample 100: negative peak; sample 150: next zero.
    # Compare the absolute slope at sample 5 (just after peak,
    # heating-driven) vs sample 45 (approaching zero, cooling-
    # driven).  The ratio should depart meaningfully from 1.
    rise = abs(i[5] - i[0])
    decay = abs(i[50] - i[45])
    if max(rise, decay) > 1e-9:
        ratio = rise / max(decay, 1e-12)
    else:
        ratio = 1.0
    # The asymmetry signature is "ratio meaningfully different from 1";
    # we accept any departure > 5 %.  This documents the dynamic
    # conductance signature without locking down a specific value.
    assert abs(ratio - 1.0) > 0.05, (
        f"Kizilcay rise/decay asymmetry ratio = {ratio:.4f}; expected "
        f"a > 5 % departure from 1.  rise = {rise:.4f}, decay = {decay:.4f}"
    )


# =============================================================================
# (6) Cross-fit CSV schema
# =============================================================================

def test_cross_fit_csv_schema() -> None:
    if not CROSS_FIT_CSV.exists():
        pytest.skip(
            f"{CROSS_FIT_CSV} not present; run "
            f"`python run_faultloc_phase4_arc_kizilcay.py` first."
        )
    rows = list(csv.DictReader(CROSS_FIT_CSV.open()))
    assert len(rows) >= 100, f"expected >= 100 rows; got {len(rows)}"
    expected_keys = {
        "fault_bus", "alpha_true", "Rx_true", "snr_v_db", "snr_i_db",
        "alpha_hat_emanuel", "Rx_hat_emanuel",
        "loc_err_pct_emanuel", "Rx_err_pct_emanuel",
        "alpha_hat_kizilcay", "Rx_hat_kizilcay",
        "loc_err_pct_kizilcay", "Rx_err_pct_kizilcay",
        "delta_loc_err_pct", "delta_Rx_err_pct",
    }
    assert expected_keys <= set(rows[0].keys())


def test_cross_fit_delta_error_quantified() -> None:
    """Sanity: the cross-fit Delta-error is non-trivial (the CSV
    actually carries the per-cell Δ values, not all zeros)."""
    if not CROSS_FIT_CSV.exists():
        pytest.skip(f"{CROSS_FIT_CSV} not present")
    rows = list(csv.DictReader(CROSS_FIT_CSV.open()))
    deltas = [
        float(r["delta_loc_err_pct"]) for r in rows
        if r["delta_loc_err_pct"] not in ("", "nan")
    ]
    deltas = np.array([d for d in deltas if np.isfinite(d)])
    assert len(deltas) >= 30, (
        f"expected >= 30 finite delta values; got {len(deltas)}"
    )
    assert np.abs(deltas).mean() > 0, (
        "all per-cell deltas are zero -- the cross-fit experiment "
        "didn't produce a measurable mismatch"
    )
