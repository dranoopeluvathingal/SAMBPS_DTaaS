"""tests/test_taylor_fourier.py
==================================

WP3.5 (P3.5) Taylor-Fourier estimator + K06 phasor-bias acceptance.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    H_meas_from_waveforms,
    single_bin_dft,
)
from sambp_fault_location_id.models.faultloc_taylor_fourier import (
    H_meas_from_waveforms_tft,
    tft_phasor,
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
K06_REPORT = PROJ_ROOT / "outputs" / "phase3_tft_vs_dft_bias.csv"

FS = 10_000.0
F0 = 50.0


def test_tft_recovers_static_phasor_to_machine_precision() -> None:
    """For a clean cosine v(t) = A cos(w0 t + phi), TFT-K=0 and
    TFT-K=1 must recover H = A e^{j phi} to machine precision."""
    N = 200
    t = np.arange(N) / FS
    H_true = 2.0 * np.exp(1j * 0.3)
    v = np.real(H_true * np.exp(1j * 2 * np.pi * F0 * t))
    H_K0, _ = tft_phasor(v, FS, F0, K=0)
    H_K1, dH = tft_phasor(v, FS, F0, K=1)
    assert abs(H_K0 - H_true) < 1.0e-12
    assert abs(H_K1 - H_true) < 1.0e-12
    # First derivative of a static signal should be ~ 0.
    assert abs(dH) < 1.0e-9


def test_tft_K1_recovers_linear_envelope_to_machine_precision() -> None:
    """For H(t) = H_0 + H_1 t, TFT-K=1 must recover (H_0, H_1) to
    machine precision."""
    N = 200
    t = np.arange(N) / FS
    H_0 = 2.0 * np.exp(1j * 0.3)
    H_1 = 5.0 - 3.0j
    v = np.real((H_0 + H_1 * t) * np.exp(1j * 2 * np.pi * F0 * t))
    H_est, dH_est = tft_phasor(v, FS, F0, K=1)
    assert abs(H_est - H_0) < 1.0e-9, (
        f"TFT-K=1 phasor at t=0: expected {H_0}, got {H_est}"
    )
    assert abs(dH_est - H_1) < 1.0e-9, (
        f"TFT-K=1 dH/dt: expected {H_1}, got {dH_est}"
    )


def test_tft_K0_matches_single_bin_dft() -> None:
    """TFT-K=0 = static-phasor LS fit; numerically equivalent to the
    single-bin DFT under integer-cycle windows."""
    N = 200
    t = np.arange(N) / FS
    H_true = 1.5 * np.exp(1j * 0.7)
    v = np.real(H_true * np.exp(1j * 2 * np.pi * F0 * t))
    H_dft = single_bin_dft(v, FS, F0)
    H_K0, _ = tft_phasor(v, FS, F0, K=0)
    assert abs(H_dft - H_K0) < 1.0e-10


def test_H_meas_from_waveforms_tft_consistency() -> None:
    """H_meas_from_waveforms_tft = (TFT phasor of i) / (TFT phasor of v).
    On clean static signals, equals H_meas_from_waveforms (DFT)."""
    N = 200
    t = np.arange(N) / FS
    H_true = 1.0e-3 * np.exp(1j * 0.4)
    v = np.cos(2 * np.pi * F0 * t)
    i = np.real(H_true * np.exp(1j * 2 * np.pi * F0 * t))
    H_dft = H_meas_from_waveforms(v, i, fs=FS, f0=F0)
    H_tft = H_meas_from_waveforms_tft(v, i, fs=FS, f0=F0, K=1)
    assert abs(H_dft - H_true) < 1.0e-10
    assert abs(H_tft - H_true) < 1.0e-10


def test_tft_input_validation() -> None:
    with pytest.raises(ValueError, match="K must be"):
        tft_phasor(np.zeros(200), FS, F0, K=-1)
    with pytest.raises(ValueError, match="too short"):
        tft_phasor(np.zeros(2), FS, F0, K=1)
    with pytest.raises(ValueError, match="must be 1-D"):
        tft_phasor(np.zeros((10, 10)), FS, F0, K=0)


def _load_k06_report() -> list[dict]:
    if not K06_REPORT.exists():
        pytest.skip(
            f"{K06_REPORT} not present; run "
            f"`python run_faultloc_phase3_taylor_fourier_bias.py` first."
        )
    return list(csv.DictReader(K06_REPORT.open()))


def test_k06_report_present_and_schema() -> None:
    rows = _load_k06_report()
    assert len(rows) >= 100, f"expected >= 100 trial rows; got {len(rows)}"
    expected_keys = {
        "trial", "alpha_true", "Rx_true", "snr_i_db", "distortion_index",
        "H_dft_real", "H_dft_imag", "H_tft_real", "H_tft_imag",
        "bias_dft_pct", "bias_tft_pct",
    }
    assert expected_keys <= set(rows[0].keys())


def test_k06_bias_improvement_at_least_50pct() -> None:
    """WP3.5 K06 brief acceptance: TFT bias improvement vs DFT >= 50 %
    on the (alpha=0.5, R_x=2000, SNR_I=30 dB) representative case."""
    rows = _load_k06_report()
    trial_rows = [r for r in rows if r["trial"] not in ("SUMMARY", "")]
    bias_dft = np.array([float(r["bias_dft_pct"]) for r in trial_rows])
    bias_tft = np.array([float(r["bias_tft_pct"]) for r in trial_rows])
    mean_dft = float(bias_dft.mean())
    mean_tft = float(bias_tft.mean())
    assert mean_dft > 0, f"DFT bias = {mean_dft}; cannot compute improvement"
    improvement = 100.0 * (mean_dft - mean_tft) / mean_dft
    assert improvement >= 50.0, (
        f"K06 bias improvement = {improvement:.2f} %; brief target >= 50 %.  "
        f"DFT mean bias = {mean_dft:.4f} %; TFT mean bias = {mean_tft:.4f} %."
    )
