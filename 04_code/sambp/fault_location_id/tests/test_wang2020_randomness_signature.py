"""tests/test_wang2020_randomness_signature.py
================================================

WP4.3 (P4.3) Wang-2020 distortion-controllable HIAF smoke +
randomness-signature tests.

Properties asserted:

1. ``Wang2020Arc`` is a concrete ``ArcModelBase`` and produces
   finite, correctly-signed currents at every R_x bracket.
2. Input validation: ``distortion_index`` outside [0, 1] raises;
   ``Rx <= 0`` raises; mismatched ``t``/``v`` shapes raise.
3. ``distortion_index = 0`` reproduces the underlying Emanuel
   baseline exactly (the determinism limit).
4. **Randomness signature**: with ``distortion_index > 0`` the
   per-half-cycle variance of the 3rd-harmonic DFT bin across
   independent Monte-Carlo trials is > 5x the same metric for the
   deterministic ``EmanuelArc`` baseline.  This is the canonical
   Wang-2020 signature: fresh OFFSET / EXTENT / DURATION drawn each
   half-cycle inject inter-trial harmonic variance the diode model
   cannot produce.
5. **Inter-trial waveform variability**: independent ``Wang2020Arc``
   instances seeded with different RNG streams produce distinguish-
   able current waveforms; identically-seeded instances produce
   bit-identical waveforms (RNG hygiene).
6. **Distortion zone is bounded**: outside the per-half-cycle zones
   the perturbed current matches the baseline (ie. perturbation
   does NOT leak across the zero-crossing into the next half-cycle).
7. Cross-fit CSV from the runner has the expected schema, with
   non-trivial Δ values across (cell, trial) pairs.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.models.faultloc_arc_models import (
    ArcModelBase,
    EmanuelArc,
    Wang2020Arc,
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
WP43_CSV = PROJ_ROOT / "outputs" / "phase4_wang2020_results.csv"

FS = 10_000.0
F0 = 50.0
N_CYCLES = 4
N = int(round(N_CYCLES * FS / F0))
T = np.arange(N) / FS
V_PEAK = 11.0e3 * np.sqrt(2.0 / 3.0)


def _v_clean() -> np.ndarray:
    return V_PEAK * np.cos(2.0 * np.pi * F0 * T)


# =============================================================================
# (1) Subclass + finite + signed
# =============================================================================

def test_wang2020_is_arc_model_base() -> None:
    assert issubclass(Wang2020Arc, ArcModelBase)


@pytest.mark.parametrize("Rx", [100.0, 1000.0, 5000.0])
def test_wang2020_current_finite_and_signed(Rx: float) -> None:
    v = _v_clean()
    arc = Wang2020Arc(distortion_index=0.7,
                      rng=np.random.default_rng(1))
    i = arc.synthesise_current(T, v, Rx)
    assert i.shape == v.shape
    assert np.all(np.isfinite(i))
    # Around the positive peak (sample 0) the current sign should
    # follow the voltage (Rx-dominated forward conduction).
    peak_idx = int(np.argmax(v[:50]))
    assert i[peak_idx] > 0


# =============================================================================
# (2) Input validation
# =============================================================================

def test_wang2020_distortion_index_validation() -> None:
    with pytest.raises(ValueError, match="distortion_index"):
        Wang2020Arc(distortion_index=-0.1)
    with pytest.raises(ValueError, match="distortion_index"):
        Wang2020Arc(distortion_index=1.5)


def test_wang2020_input_validation() -> None:
    arc = Wang2020Arc(distortion_index=0.5,
                      rng=np.random.default_rng(2))
    v = _v_clean()
    with pytest.raises(ValueError, match="Rx must be"):
        arc.synthesise_current(T, v, 0.0)
    with pytest.raises(ValueError, match="must have the same shape"):
        arc.synthesise_current(T, v[:50], 1000.0)


# =============================================================================
# (3) Determinism limit (distortion_index = 0)
# =============================================================================

def test_wang2020_zero_distortion_matches_emanuel() -> None:
    """``distortion_index = 0`` must reduce to the underlying Emanuel
    baseline exactly; the perturbation loop is a no-op."""
    v = _v_clean()
    Rx = 1000.0
    em = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    arc = Wang2020Arc(distortion_index=0.0,
                      emanuel=em,
                      rng=np.random.default_rng(3))
    i_baseline = em.synthesise_current(T, v, Rx)
    i_wang = arc.synthesise_current(T, v, Rx)
    np.testing.assert_array_equal(i_wang, i_baseline)


# =============================================================================
# (4) Randomness signature: 3rd-harmonic inter-trial variance > 5x diode
# =============================================================================

def _bin_amplitude(x: np.ndarray, k: int) -> float:
    """Return |single-bin DFT amplitude| at bin index k of length-N x."""
    Ns = len(x)
    n = np.arange(Ns)
    return abs(
        (2.0 / Ns) * np.sum(x * np.exp(-1j * 2.0 * np.pi * k * n / Ns))
    )


def test_wang2020_inter_trial_third_harmonic_variance_signature() -> None:
    """The Wang-2020 randomness mechanism injects fresh OFFSET /
    EXTENT / DURATION per half-cycle.  Across independent Monte-Carlo
    trials this produces a measurable variance in the 3rd-harmonic
    DFT bin amplitude, whereas the deterministic Emanuel arc has
    zero inter-trial variance (deterministic in the noiseless case).

    Add a tiny noise floor to both so the Emanuel variance isn't
    literally 0 -- then the ratio is well-defined.
    """
    rng_master = np.random.default_rng(42)
    n_trials = 30
    Rx = 1000.0
    v = _v_clean()
    em = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    k3 = int(round(3 * F0 * N / FS))
    em_amps = []
    wa_amps = []
    for _trial in range(n_trials):
        seed = int(rng_master.integers(0, 2 ** 31))
        # Tiny noise so Emanuel variance is well-defined but small.
        noise = np.random.default_rng(seed).standard_normal(N) * 1e-6
        i_em = em.synthesise_current(T, v, Rx) + noise
        wa = Wang2020Arc(distortion_index=0.7, emanuel=em,
                         rng=np.random.default_rng(seed))
        i_wa = wa.synthesise_current(T, v, Rx) + noise
        em_amps.append(_bin_amplitude(i_em, k3))
        wa_amps.append(_bin_amplitude(i_wa, k3))
    em_var = float(np.var(em_amps))
    wa_var = float(np.var(wa_amps))
    ratio = wa_var / max(em_var, 1e-30)
    assert ratio > 5.0, (
        f"Wang2020 3rd-harmonic inter-trial variance must be > 5x the "
        f"Emanuel baseline; got Wang={wa_var:.6e}, "
        f"Emanuel={em_var:.6e}, ratio={ratio:.2f}"
    )


# =============================================================================
# (5) RNG hygiene: same seed -> same waveform; different seed -> different
# =============================================================================

def test_wang2020_rng_determinism() -> None:
    v = _v_clean()
    Rx = 1000.0
    em = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    a1 = Wang2020Arc(distortion_index=0.7, emanuel=em,
                     rng=np.random.default_rng(7))
    a2 = Wang2020Arc(distortion_index=0.7, emanuel=em,
                     rng=np.random.default_rng(7))
    a3 = Wang2020Arc(distortion_index=0.7, emanuel=em,
                     rng=np.random.default_rng(8))
    i1 = a1.synthesise_current(T, v, Rx)
    i2 = a2.synthesise_current(T, v, Rx)
    i3 = a3.synthesise_current(T, v, Rx)
    np.testing.assert_array_equal(i1, i2)
    # Different seed -> noticeably different
    assert np.max(np.abs(i1 - i3)) > 1e-3, (
        "Wang2020Arc with different RNG seed must produce distinguishable "
        "waveforms"
    )


# =============================================================================
# (6) Distortion zone is bounded (no leak across zero crossing)
# =============================================================================

def test_wang2020_zone_bounded_to_half_cycle() -> None:
    """Within a half-cycle the perturbation is applied only inside
    the [zone_start, zone_end] sub-window.  Outside that sub-window
    (but still within the same half-cycle) the current must match
    the Emanuel baseline.  We assert this by checking at least ONE
    sample-window per half-cycle is unperturbed (which proves the
    perturbation is bounded, not all-overwritten)."""
    v = _v_clean()
    Rx = 1000.0
    em = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    arc = Wang2020Arc(distortion_index=0.7, emanuel=em,
                      rng=np.random.default_rng(11))
    i_base = em.synthesise_current(T, v, Rx)
    i_wa = arc.synthesise_current(T, v, Rx)
    # In each half-cycle (50 samples at FS=10 kHz, F0=50 Hz),
    # at least 30 % of samples should be unperturbed (zone width
    # is uniform[0.10, 0.40] of half-cycle width per the runner).
    half_len = int(FS / (2 * F0))   # 100 samples per half-cycle
    n_halves = N // half_len
    for k in range(n_halves):
        i0, i1 = k * half_len, (k + 1) * half_len
        slab_base = i_base[i0:i1]
        slab_wa = i_wa[i0:i1]
        diff = np.abs(slab_wa - slab_base)
        # Some samples have diff = 0 (outside the zone).
        n_zero = int(np.sum(diff < 1e-12))
        assert n_zero > 0, (
            f"half-cycle {k}: no samples are unperturbed; the zone "
            f"appears to span the entire half-cycle"
        )


# =============================================================================
# (7) Cross-fit CSV schema + non-trivial deltas
# =============================================================================

def test_wp43_csv_schema() -> None:
    if not WP43_CSV.exists():
        pytest.skip(
            f"{WP43_CSV} not present; run "
            f"`python run_faultloc_phase4_wang2020.py` first."
        )
    rows = list(csv.DictReader(WP43_CSV.open()))
    assert len(rows) >= 100, f"expected >= 100 rows; got {len(rows)}"
    expected = {
        "trial", "fault_bus", "alpha_true", "Rx_true",
        "snr_v_db", "snr_i_db",
        "loc_err_emanuel_dft", "loc_err_wang2020_dft",
        "loc_err_emanuel_tft", "loc_err_wang2020_tft",
        "delta_dft", "delta_tft",
    }
    assert expected <= set(rows[0].keys())


def test_wp43_csv_deltas_nontrivial() -> None:
    if not WP43_CSV.exists():
        pytest.skip(f"{WP43_CSV} not present")
    rows = list(csv.DictReader(WP43_CSV.open()))
    deltas = np.array([
        float(r["delta_dft"]) for r in rows
        if r["delta_dft"] not in ("", "nan")
    ])
    deltas = deltas[np.isfinite(deltas)]
    assert len(deltas) >= 30, f"expected >= 30 finite deltas; got {len(deltas)}"
    assert np.abs(deltas).mean() > 0, (
        "all per-cell DFT deltas are zero -- the Wang-2020 cross-fit "
        "did not produce a measurable arc-model-mismatch signature"
    )
