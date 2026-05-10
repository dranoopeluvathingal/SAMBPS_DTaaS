"""tests/test_phase4_impairments.py
=====================================

WP4.1 (P4.1) impairment-generator unit tests + Phase-4 K07
acceptance.

Per-generator unit tests assert:
* clean input passes through under degenerate parameters (e.g.,
  prob = 0 for impulsive; bits = 24 for ADC; df = 0 for off-nominal);
* corrupted output departs from the input by the expected magnitude
  under the canonical defaults;
* input-validation raises on out-of-range parameters.

Phase-4 K07 acceptance asserts mean loc-err < 5 % across all 5
impairment classes individually at SNR_I >= 30 dB on the IEEE 34
sub-sample.  This is xfail-strict per the established R-class
escalation pattern (the load-dominated IEEE 34 + single-bin DFT
identifiability floor drives the clean baseline well above 5 %).
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.models.faultloc_noise_impairments import (
    CT_CLASSES,
    DEFAULT_HARMONICS,
    add_adc_quantisation,
    add_composite_field_grade,
    add_ct_saturation,
    add_harmonic_background,
    add_impulsive,
    add_off_nominal_frequency,
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_CSV = PROJ_ROOT / "outputs" / "phase4_impairments_summary.csv"
PARQUET = PROJ_ROOT / "outputs" / "phase4_impairments_results.parquet"

FS = 10_000.0
F0 = 50.0


def _clean_pair(N: int = 200) -> tuple[np.ndarray, np.ndarray]:
    t = np.arange(N) / FS
    return (
        100.0 * np.cos(2 * np.pi * F0 * t),
        1.0 * np.cos(2 * np.pi * F0 * t + 0.3),
    )


# =============================================================================
# (1) Impulsive
# =============================================================================

def test_impulsive_zero_prob_passes_through() -> None:
    v, i = _clean_pair()
    rng = np.random.default_rng(1)
    vp, ip = add_impulsive(v, i, prob=0.0, mag_db=20.0, rng=rng)
    np.testing.assert_array_equal(vp, v)
    np.testing.assert_array_equal(ip, i)


def test_impulsive_with_prob_inflates_rms() -> None:
    v, i = _clean_pair()
    rng = np.random.default_rng(1)
    vp, ip = add_impulsive(v, i, prob=0.05, mag_db=20.0, rng=rng)
    rms_v_clean = float(np.sqrt(np.mean(v ** 2)))
    rms_v_imp = float(np.sqrt(np.mean(vp ** 2)))
    assert rms_v_imp > rms_v_clean, (
        f"impulsive should inflate rms; clean={rms_v_clean}, imp={rms_v_imp}"
    )


def test_impulsive_input_validation() -> None:
    v, i = _clean_pair()
    with pytest.raises(ValueError, match="prob must be"):
        add_impulsive(v, i, prob=-0.1, mag_db=10.0)
    with pytest.raises(ValueError, match="prob must be"):
        add_impulsive(v, i, prob=1.5, mag_db=10.0)
    with pytest.raises(ValueError, match="must have the same shape"):
        add_impulsive(v, np.zeros(50), prob=0.01, mag_db=10.0)


# =============================================================================
# (2) Harmonic background
# =============================================================================

def test_harmonics_empty_dict_passes_through() -> None:
    v, i = _clean_pair()
    rng = np.random.default_rng(2)
    vp, ip = add_harmonic_background(
        v, i, fs=FS, f0=F0, harmonics={}, rng=rng,
    )
    np.testing.assert_array_equal(vp, v)
    np.testing.assert_array_equal(ip, i)


def test_harmonics_default_modifies_signal() -> None:
    v, i = _clean_pair()
    rng = np.random.default_rng(2)
    vp, ip = add_harmonic_background(
        v, i, fs=FS, f0=F0, harmonics=DEFAULT_HARMONICS, rng=rng,
    )
    # Should have non-zero signal at the harmonic bins (e.g., 5th).
    Ns = v.size
    k5 = int(round(5 * F0 * Ns / FS))
    n = np.arange(Ns)
    bin_vp = abs((2.0 / Ns) * np.sum(vp * np.exp(-1j * 2 * np.pi * k5 * n / Ns)))
    bin_v_clean = abs((2.0 / Ns) * np.sum(v * np.exp(-1j * 2 * np.pi * k5 * n / Ns)))
    assert bin_vp > bin_v_clean + 1.0, (
        f"5th-harmonic bin should grow; clean={bin_v_clean}, imp={bin_vp}"
    )


# =============================================================================
# (3) CT saturation
# =============================================================================

def test_ct_saturation_linear_regime_passthrough() -> None:
    """For currents well below the knee, output should equal input."""
    i = np.cos(2 * np.pi * F0 * np.arange(200) / FS)  # peak 1A << knee
    i_sat = add_ct_saturation(i, remanence_pu=0.0, burden_ohm=2.0, ct_class="5P20")
    np.testing.assert_allclose(i_sat, i, rtol=1e-2)


def test_ct_saturation_clips_at_knee() -> None:
    """For currents at the knee, output must be bounded."""
    v_knee = CT_CLASSES["5P20"]
    burden = 2.0
    i_knee = v_knee / burden
    i = 10 * i_knee * np.cos(2 * np.pi * F0 * np.arange(200) / FS)  # 10x knee
    i_sat = add_ct_saturation(i, remanence_pu=0.0, burden_ohm=burden, ct_class="5P20")
    assert np.max(np.abs(i_sat)) <= i_knee + 1e-6


def test_ct_saturation_higher_remanence_clips_earlier() -> None:
    v_knee = CT_CLASSES["5P20"]
    burden = 2.0
    i_knee = v_knee / burden
    i = 5 * i_knee * np.cos(2 * np.pi * F0 * np.arange(200) / FS)
    rms_low = float(np.sqrt(np.mean(
        add_ct_saturation(i, remanence_pu=0.0, burden_ohm=burden) ** 2
    )))
    rms_high = float(np.sqrt(np.mean(
        add_ct_saturation(i, remanence_pu=0.5, burden_ohm=burden) ** 2
    )))
    assert rms_high < rms_low, (
        f"higher remanence -> earlier saturation -> smaller rms; "
        f"low={rms_low}, high={rms_high}"
    )


def test_ct_saturation_input_validation() -> None:
    i = np.zeros(100)
    with pytest.raises(ValueError, match="ct_class must be"):
        add_ct_saturation(i, ct_class="bogus")
    with pytest.raises(ValueError, match="remanence_pu"):
        add_ct_saturation(i, remanence_pu=-0.1)
    with pytest.raises(ValueError, match="remanence_pu"):
        add_ct_saturation(i, remanence_pu=1.0)
    with pytest.raises(ValueError, match="burden_ohm"):
        add_ct_saturation(i, burden_ohm=0.0)


# =============================================================================
# (4) Off-nominal frequency
# =============================================================================

def test_off_nominal_zero_df_passes_through() -> None:
    v, i = _clean_pair()
    vp, ip = add_off_nominal_frequency(v, i, fs=FS, f0=F0, df_hz=0.0)
    np.testing.assert_array_equal(vp, v)
    np.testing.assert_array_equal(ip, i)


def test_off_nominal_shifts_signal() -> None:
    """At df = 0.5 Hz, the shifted signal must differ from the clean
    signal sample-by-sample.  We can't simply check the f0-bin energy
    drops because a 1-cycle window has negligible spectral leakage of
    a 0.5 Hz shift on a 50 Hz fundamental (~1 % leakage), which is
    well below the test's noise floor.  The shift IS present in the
    time-domain trace and shows up downstream when integrated over
    multiple cycles -- the canonical regime where off-nominal-
    frequency drift biases the static-phasor DFT estimator."""
    v, i = _clean_pair()
    vp, ip = add_off_nominal_frequency(v, i, fs=FS, f0=F0, df_hz=0.5)
    diff_v = float(np.max(np.abs(vp - v)))
    diff_i = float(np.max(np.abs(ip - i)))
    assert diff_v > 0.1, (
        f"off-nominal shift should perturb v sample-by-sample; max diff = {diff_v}"
    )
    assert diff_i > 0.001, (
        f"off-nominal shift should perturb i sample-by-sample; max diff = {diff_i}"
    )


def test_off_nominal_input_validation() -> None:
    v, i = _clean_pair()
    with pytest.raises(ValueError, match="df_hz outside"):
        add_off_nominal_frequency(v, i, df_hz=10.0)


# =============================================================================
# (5) ADC quantisation
# =============================================================================

def test_adc_quantisation_high_bits_near_passthrough() -> None:
    v, i = _clean_pair()
    vp, ip = add_adc_quantisation(v, i, bits=24, vref_v=200, iref_a=2)
    np.testing.assert_allclose(vp, v, atol=1e-4)
    np.testing.assert_allclose(ip, i, atol=1e-6)


def test_adc_quantisation_low_bits_loses_precision() -> None:
    v, i = _clean_pair()
    vp, ip = add_adc_quantisation(v, i, bits=8, vref_v=200, iref_a=2)
    # 8 bits over +/- 200 V = step ~ 1.56 V; quantisation error should
    # be visible on a 100 V signal.
    err = float(np.max(np.abs(vp - v)))
    assert err > 0.5, f"8-bit quantiser should produce >= 0.5 V error; got {err}"


def test_adc_quantisation_clips_at_full_scale() -> None:
    v = np.full(100, 1000.0)
    i = np.zeros(100)
    vp, _ = add_adc_quantisation(v, i, bits=14, vref_v=100, iref_a=10)
    assert vp.max() <= 100.0 + 1e-6, (
        f"quantiser should clip at vref; got max {vp.max()}"
    )


def test_adc_quantisation_input_validation() -> None:
    v, i = _clean_pair()
    with pytest.raises(ValueError, match="bits must be"):
        add_adc_quantisation(v, i, bits=2, vref_v=100, iref_a=10)
    with pytest.raises(ValueError, match="vref_v and iref_a"):
        add_adc_quantisation(v, i, bits=14, vref_v=-1, iref_a=10)


# =============================================================================
# Composite
# =============================================================================

def test_composite_runs_and_changes_signal() -> None:
    v, i = _clean_pair()
    rng = np.random.default_rng(99)
    vp, ip = add_composite_field_grade(
        v, i, fs=FS, f0=F0, rng=rng,
        vref_v=200.0, iref_a=2.0,
    )
    assert vp.shape == v.shape
    assert ip.shape == i.shape
    assert not np.allclose(vp, v), "composite should modify v"
    assert not np.allclose(ip, i), "composite should modify i"


# =============================================================================
# Phase-4 K07 acceptance
# =============================================================================

def _load_summary() -> list[dict]:
    if not SUMMARY_CSV.exists():
        pytest.skip(
            f"{SUMMARY_CSV} not present; run "
            f"`python run_faultloc_phase4_impairments.py` first."
        )
    return list(csv.DictReader(SUMMARY_CSV.open()))


def test_summary_csv_present_and_schema() -> None:
    rows = _load_summary()
    assert len(rows) >= 5, f"expected >= 5 condition rows; got {len(rows)}"
    expected_keys = {
        "condition", "n_cells",
        "loc_err_mean_pct", "loc_err_p95_pct",
        "Rx_err_mean_pct", "Rx_err_p95_pct",
    }
    assert expected_keys <= set(rows[0].keys())


def test_parquet_produced() -> None:
    if not PARQUET.exists():
        pytest.skip(
            f"{PARQUET} not present; run "
            f"`python run_faultloc_phase4_impairments.py` first."
        )
    assert PARQUET.stat().st_size > 1000


@pytest.mark.xfail(
    strict=True,
    reason=(
        "WP4.1 R1 escalation: K07 (Phase 4) requires mean loc-err < "
        "5 % at SNR_I >= 30 dB across all 5 impairment classes "
        "individually on the IEEE 34 sub-sample.  Measured ~62 % mean "
        "across all conditions including the CLEAN baseline -- the "
        "structural single-bin DFT identifiability floor on the load-"
        "dominated IEEE 34 (R-WP3.4-1 escalation in WP3.4 + WP3.7) "
        "drives the residual; the per-impairment delta from clean is "
        "< 1 % so the impairment generators are correct -- the "
        "framework just inherits the underlying R-WP3.4-1 / R5-floor "
        "issue.  Closure path: WP3.5 + WP3.6 multi-bin / multi-port "
        "extension lifts the per-entry SNR + WP3.3 follow-up canonical "
        "IEEE 34 line codes reduce the load-dominated baseline."
    ),
)
def test_K07_phase4_loc_err_below_5pct_per_class() -> None:
    rows = _load_summary()
    # Test asserts that EVERY one of the 5 individual impairment
    # classes (NOT the composite, NOT the clean baseline) sits below
    # 5 % mean loc-err.  Brief target.
    individual_classes = (
        "impulsive", "harmonics", "ct_saturation",
        "off_nominal", "adc_quantisation",
    )
    failures: list[tuple[str, float]] = []
    for r in rows:
        if r["condition"] not in individual_classes:
            continue
        loc_mean = float(r["loc_err_mean_pct"])
        if loc_mean >= 5.0:
            failures.append((r["condition"], loc_mean))
    assert not failures, (
        f"K07 (Phase 4) FAIL: {len(failures)}/5 impairment classes "
        f"exceed 5 % mean loc-err.  Failing: "
        f"{', '.join(f'{n}={v:.2f}%' for n, v in failures)}"
    )
