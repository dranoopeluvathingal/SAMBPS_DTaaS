"""
line_harmonic_model.py
======================
Harmonic-component discrimination and pre-filtering for the SAMBP 87L
differential element in inverter-based resource (IBR) rich networks.

Background
----------
The SAMBP 87L LM estimator (line_reduced_zone_model.py) fits a 4-parameter
model to the differential current:

    i_diff(t) = I_fund × sin(ωt + φ_fund)   [power-frequency component]
              + I_DC   × exp(−t / τ_DC)        [decaying DC offset]

In synchronous-generator (SG) dominated networks this model is sufficient:
fault differentials are dominated by the fundamental and an inductive DC
offset with τ ∈ [10, 100] ms.

In IBR-rich networks, inverters inject significant harmonic current even in
the healthy state (THD up to 5% per IEEE 519).  During fault ride-through,
current-limiting control can amplify odd harmonics (3rd, 5th, 7th) in the
differential by factors of 2--5×.  These harmonics appear as residual after
LM fitting, inflating `residual_norm` and depressing the confidence score:

    confidence = κ_n_conf × exp(−residual_norm)

A high residual_norm (e.g. 0.15 vs noise-floor 0.02) can cut confidence
from 0.98 to 0.86, reducing the margin available for the Stage-2 veto gate.

Harmonic pre-filter (TR-21)
---------------------------
Before passing i_diff to the LM estimator, estimate and subtract the
dominant harmonic components using linear least squares (no iteration):

    i_diff_filtered(t) = i_diff(t) − Σ_h [A_h cos(hωt) + B_h sin(hωt)]

where the sum is over h ∈ {3, 5, 7} (odd harmonics dominating IBR output).
Even harmonics (2nd, 4th) are also optionally included; they indicate
transformer inrush (TR-11 restrain logic handles this separately).

The harmonic ratio H_ratio = I_harm_rms / I_fund provides a network-type
discriminator:
    H_ratio < 0.05  → SG-dominated network  (low harmonics)
    H_ratio > 0.20  → IBR-dominated network (high harmonics)

This ratio is logged as a diagnostic metric but does NOT change the trip
threshold — the LM I_fund estimate after pre-filtering is used directly.

References
----------
    IEEE Std 519-2014 §5 — Current distortion limits for IBR.
    IEC 61000-4-7:2002 — Harmonic measurement methods.
    SAMBP TR-15/2026 — Pi-section charging correction.
    SAMBP TR-17/2026 — Adaptive threshold (I_rest dependence).
    SAMBP TR-20/2026 — Frequency-adaptive B_C scaling.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class HarmonicFilterConfig:
    """
    Parameters for the harmonic pre-filter.

    All electrical quantities in per-unit on the relay's base.
    """
    # Harmonics to estimate and subtract (odd IBR harmonics by default)
    harmonics: tuple = (3, 5, 7)

    # Whether to also filter even harmonics (transformer inrush)
    include_even: bool = False

    # Minimum harmonic amplitude to include in subtraction [pu]
    # Below this, assume numerical noise and skip
    min_harm_amplitude: float = 1e-4

    # Network type thresholds for H_ratio diagnostic
    h_ratio_sg_max: float   = 0.05   # below → SG-dominated
    h_ratio_ibr_min: float  = 0.20   # above → IBR-dominated


@dataclass
class HarmonicFilterResult:
    """Output of the harmonic pre-filter for one phase."""
    i_filtered: np.ndarray           # (N,) filtered differential [pu]
    i_harmonics: np.ndarray          # (N,) estimated harmonic signal [pu]
    I_harm_rms: float                # RMS of removed harmonics [pu]
    I_fund_estimate: float           # DFT-based fundamental estimate [pu]
    H_ratio: float                   # I_harm_rms / max(I_fund_estimate, ε)
    coeffs: np.ndarray               # (2×len(harmonics),) LS coefficients
    network_type: str                # "SG" | "IBR" | "mixed"


# ---------------------------------------------------------------------------
# Harmonic pre-filter (single phase)
# ---------------------------------------------------------------------------

def filter_harmonics_single(
    i_diff: np.ndarray,       # (N,) differential waveform [pu]
    t: np.ndarray,            # (N,) time array [s]
    freq_hz: float = 50.0,
    cfg: HarmonicFilterConfig = None,
) -> HarmonicFilterResult:
    """
    Estimate and subtract harmonic components from a single-phase differential.

    Uses linear least-squares on the harmonic regressor matrix — no
    iteration, no convergence issues, O(N) in practice.

    Parameters
    ----------
    i_diff  : (N,) single-phase differential current [pu]
    t       : (N,) time array [s]
    freq_hz : fundamental frequency estimate [Hz]
    cfg     : HarmonicFilterConfig (defaults used if None)

    Returns
    -------
    HarmonicFilterResult
    """
    if cfg is None:
        cfg = HarmonicFilterConfig()

    omega = 2.0 * np.pi * freq_hz
    N = len(t)

    # Build harmonic list
    harm_list = list(cfg.harmonics)
    if cfg.include_even:
        harm_list += [2, 4, 6]
    harm_list = sorted(set(harm_list))

    # --- Regressor matrix: [cos(hωt), sin(hωt)] for each harmonic h -----
    cols = []
    for h in harm_list:
        cols.append(np.cos(h * omega * t))
        cols.append(np.sin(h * omega * t))
    H_mat = np.column_stack(cols)          # (N, 2*len(harm_list))

    # --- Linear least-squares fit -----------------------------------------
    coeffs, _, _, _ = np.linalg.lstsq(H_mat, i_diff, rcond=None)

    # --- Reconstruct and threshold ----------------------------------------
    i_harm_all = H_mat @ coeffs            # full harmonic estimate
    # Zero out harmonics below amplitude floor
    i_harm_masked = np.zeros(N)
    idx = 0
    for h in harm_list:
        A = coeffs[idx]
        B = coeffs[idx + 1]
        amp = np.sqrt(A**2 + B**2)
        if amp >= cfg.min_harm_amplitude:
            i_harm_masked += A * np.cos(h * omega * t) + B * np.sin(h * omega * t)
        idx += 2

    i_filtered = i_diff - i_harm_masked
    I_harm_rms = float(np.sqrt(np.mean(i_harm_masked**2)))

    # --- Fundamental estimate from DFT (for H_ratio) ----------------------
    F = np.fft.rfft(i_diff)
    freqs = np.fft.rfftfreq(N, d=(t[1] - t[0]))
    idx1 = int(np.argmin(np.abs(freqs - freq_hz)))
    I_fund_est = float(abs(F[idx1])) * 2.0 / N

    H_ratio = I_harm_rms / max(I_fund_est, 1e-6)

    # --- Network type diagnostic -------------------------------------------
    if H_ratio < cfg.h_ratio_sg_max:
        network_type = "SG"
    elif H_ratio > cfg.h_ratio_ibr_min:
        network_type = "IBR"
    else:
        network_type = "mixed"

    return HarmonicFilterResult(
        i_filtered     = i_filtered,
        i_harmonics    = i_harm_masked,
        I_harm_rms     = I_harm_rms,
        I_fund_estimate = I_fund_est,
        H_ratio        = H_ratio,
        coeffs         = coeffs,
        network_type   = network_type,
    )


# ---------------------------------------------------------------------------
# Three-phase harmonic pre-filter
# ---------------------------------------------------------------------------

def filter_harmonics_3ph(
    i_diff_abc: np.ndarray,   # (3, N) three-phase differential [pu]
    t: np.ndarray,            # (N,) time array [s]
    freq_hz: float = 50.0,
    cfg: HarmonicFilterConfig = None,
) -> tuple[np.ndarray, list[HarmonicFilterResult]]:
    """
    Apply harmonic pre-filter to all three phases independently.

    Returns
    -------
    i_filtered_abc : (3, N) filtered differential [pu]
    results        : list of 3 HarmonicFilterResult (one per phase)
    """
    if cfg is None:
        cfg = HarmonicFilterConfig()

    i_filt = np.zeros_like(i_diff_abc)
    results = []
    for ph in range(3):
        r = filter_harmonics_single(i_diff_abc[ph], t, freq_hz, cfg)
        i_filt[ph] = r.i_filtered
        results.append(r)

    return i_filt, results


# ---------------------------------------------------------------------------
# Residual norm (used by confidence gate)
# ---------------------------------------------------------------------------

def residual_norm_after_lm(
    i_diff: np.ndarray,
    i_model: np.ndarray,
) -> float:
    """
    Compute the normalised residual norm ||i_diff - i_model|| / ||i_diff||.

    Returns 0 when i_diff is zero (avoids division by zero).
    """
    num = float(np.linalg.norm(i_diff - i_model))
    den = float(np.linalg.norm(i_diff))
    if den < 1e-10:
        return 0.0
    return num / den


def confidence_from_residual(residual_norm: float) -> float:
    """Confidence score: exp(−residual_norm) in [0, 1]."""
    return float(np.exp(-residual_norm))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== line_harmonic_model.py self-test ===\n")

    fs  = 4000.0
    N   = int(fs * 0.04)    # 2 cycles at 50 Hz
    t   = np.arange(N) / fs
    f0  = 50.0
    cfg = HarmonicFilterConfig()

    # Ground-truth parameters — use fault-level I_fund so H_ratio is meaningful
    I_fund_true = 0.150   # pu (internal fault, above 0.12 pu threshold)

    # Expected network_type: H_ratio = I_harm_rms / I_fund_dft
    # I_harm_rms ≈ I_harm/sqrt(2); I_fund_dft ≈ I_fund_true
    # → thresholds: SG: H<0.05, IBR: H>0.20
    # I_harm=0.000 → H=0        → SG
    # I_harm=0.005 → H≈0.024    → SG
    # I_harm=0.030 → H≈0.141    → mixed
    # I_harm=0.060 → H≈0.283    → IBR
    # I_harm=0.090 → H≈0.424    → IBR
    test_cases = [
        ("SG (no harm)",   0.000, "SG"),
        ("mild IBR",       0.005, "SG"),
        ("moderate IBR",   0.030, "mixed"),
        ("heavy IBR",      0.060, "IBR"),
        ("severe IBR",     0.090, "IBR"),
    ]

    print(f"{'Case':<20} {'I_harm':>8} {'H_ratio':>9} {'Net':>6} "
          f"{'res_raw':>9} {'res_filt':>9} {'improve':>8} {'pass':>5}")
    print("-" * 80)

    all_pass = True
    for label, I_harm, expected_net in test_cases:
        # Single-phase differential: fundamental + 3rd harmonic
        i_diff = (I_fund_true * np.sin(2*np.pi*f0*t)
                  + I_harm     * np.sin(6*np.pi*f0*t + 0.3))

        r = filter_harmonics_single(i_diff, t, f0, cfg)

        # Simple sinusoidal model at fundamental (approximating LM output)
        i_model_fund = I_fund_true * np.sin(2*np.pi*f0*t)

        res_raw  = residual_norm_after_lm(i_diff,      i_model_fund)
        res_filt = residual_norm_after_lm(r.i_filtered, i_model_fund)

        improve = res_raw / (res_filt + 1e-9)
        net_ok  = (r.network_type == expected_net)
        res_ok  = (I_harm < 1e-5) or (res_filt < res_raw * 0.5)
        ok = net_ok and res_ok
        if not ok:
            all_pass = False

        flag = "PASS" if ok else "FAIL"
        print(f"{label:<20} {I_harm:8.3f} {r.H_ratio:9.4f} {r.network_type:>6} "
              f"{res_raw:9.5f} {res_filt:9.5f} {improve:7.1f}x  {flag}")

    print()
    if all_pass:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        raise SystemExit(1)
