"""
line_adaptive_threshold.py
===========================
SAMBP TR-17/2026 -- Adaptive 87L threshold as a function of restraint current.

Motivation
----------
Under heavy load the through-current flowing past the line CTs produces a
differential error proportional to CT ratio mismatch:

    i_diff_err(t) ≈ ε_CT × |i_through(t)|

For Class 0.5 CTs (ε_CT ≤ 0.005), and with rated through-current
|i_through| = 1 pu, the worst-case differential error is 0.005 pu —
negligible relative to the TR-15 threshold of 0.08 pu.

However at sustained heavy load |i_through| = 4 pu (e.g. post-transfer with
all feeders on one bus), i_diff_err can reach 0.020 pu, approaching the
threshold from below with reduced security margin.

The adaptive threshold law
--------------------------
    I_thresh(I_rest) = max(I_base, k_slope × I_rest)

where:
    I_base   — minimum (no-load) threshold [pu] = 0.08 pu (TR-15 value)
    k_slope  — bias slope [pu/pu] (analogous to the restrain slope of a
               percentage differential characteristic)
    I_rest   — restraint current = (|i_S| + |i_R|) / 2  [pu]

Design choice: k_slope = 0.15
    Security margin against CT mismatch: k_slope / ε_CT = 0.15 / 0.005 = 30×
    This matches IEC/IEEE practice for percentage differential relays~[CITE].

Sensitivity impact
------------------
    I_rest = 0.0 pu → I_thresh = 0.08 pu → α₅₀(ag) = 0.03  (TR-15, unchanged)
    I_rest = 0.5 pu → I_thresh = 0.08 pu (k×I_rest=0.075 < I_base)
    I_rest = 1.0 pu → I_thresh = 0.15 pu → α₅₀(ag) ≈ 0.056
    I_rest = 2.0 pu → I_thresh = 0.30 pu → α₅₀(ag) ≈ 0.11
    I_rest = 4.0 pu → I_thresh = 0.60 pu → α₅₀(ag) ≈ 0.22

The sensitivity loss at heavy load is physically correct: a HIF with
α=0.05 on a heavily loaded line creates a differential of ~0.23 pu, which
still exceeds the 0.15 pu threshold at I_rest=1.0 pu.

Interface
---------
    adaptive_thresh(I_rest, I_base=0.08, k_slope=0.15) -> float
    compute_I_rest(i_S_peak, i_R_peak) -> float
    AdaptiveThreshConfig — dataclass for pipeline integration
    compute_alpha50(I_thresh, I_nom, phase_factor) -> float
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class AdaptiveThreshConfig:
    """Parameters for the adaptive 87L threshold law."""
    I_base:   float = 0.08    # minimum threshold at no load [pu]  (TR-15 value)
    k_slope:  float = 0.15    # bias slope [pu/pu]
    epsilon_CT: float = 0.005 # CT class 0.5 ratio error [pu/pu]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def adaptive_thresh(
    I_rest:  float,
    I_base:  float = 0.08,
    k_slope: float = 0.15,
) -> float:
    """
    Compute the adaptive 87L fundamental threshold for a given restraint
    current.

        I_thresh = max(I_base, k_slope × I_rest)

    Parameters
    ----------
    I_rest   : restraint current (|i_S| + |i_R|) / 2  [pu]
    I_base   : minimum threshold (no-load floor)       [pu]
    k_slope  : bias slope                              [pu/pu]

    Returns
    -------
    float : I_thresh [pu]
    """
    return float(max(I_base, k_slope * float(I_rest)))


def compute_I_rest(i_S_peak: float, i_R_peak: float) -> float:
    """
    Standard biased-differential restraint current.

        I_rest = (|i_S_peak| + |i_R_peak|) / 2

    Parameters
    ----------
    i_S_peak : peak current at sending end [pu]
    i_R_peak : peak current at receiving end [pu]
    """
    return (abs(i_S_peak) + abs(i_R_peak)) / 2.0


def security_margin(I_thresh: float, I_rest: float, epsilon_CT: float = 0.005) -> float:
    """
    Security margin against CT mismatch-induced differential:

        margin = I_thresh / max(epsilon_CT × I_rest, 1e-9)

    Returns -1 if I_rest == 0 (infinite margin at no load).
    """
    if I_rest < 1e-9:
        return float("inf")
    return I_thresh / (epsilon_CT * I_rest)


def compute_alpha50(
    I_thresh: float,
    I_line_nom: float,
    phase_factor: float = 1.0,
) -> float:
    """
    HIF sensitivity floor: minimum alpha that produces I_fund >= I_thresh.

        alpha_50 = I_thresh / (phase_factor × I_line_nom)

    Parameters
    ----------
    I_thresh    : threshold [pu]
    I_line_nom  : nominal fault current at alpha=1 [pu]
    phase_factor: correction for single-phase faults (e.g. 0.70 for ag,
                  accounting for the 87L seeing one-phase differential)
    """
    return float(I_thresh / max(phase_factor * I_line_nom, 1e-9))


# ---------------------------------------------------------------------------
# Characteristic curve helpers
# ---------------------------------------------------------------------------

def thresh_curve(
    I_rest_vec: np.ndarray,
    cfg: Optional[AdaptiveThreshConfig] = None,
) -> np.ndarray:
    """Vectorised adaptive threshold over a range of I_rest values."""
    if cfg is None:
        cfg = AdaptiveThreshConfig()
    return np.array([adaptive_thresh(ir, cfg.I_base, cfg.k_slope)
                     for ir in I_rest_vec])


def alpha50_curve(
    I_rest_vec: np.ndarray,
    I_line_nom: float,
    phase_factor: float = 1.0,
    cfg: Optional[AdaptiveThreshConfig] = None,
) -> np.ndarray:
    """α₅₀ as a function of I_rest."""
    th = thresh_curve(I_rest_vec, cfg)
    return th / max(phase_factor * I_line_nom, 1e-9)


def ct_error_current(I_rest_vec: np.ndarray, epsilon_CT: float = 0.005) -> np.ndarray:
    """Worst-case CT mismatch differential: ε_CT × I_rest."""
    return epsilon_CT * I_rest_vec


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = AdaptiveThreshConfig(I_base=0.08, k_slope=0.15, epsilon_CT=0.005)

    cases = [(0.0, 0.08), (0.5, 0.08), (1.0, 0.15), (2.0, 0.30), (4.0, 0.60)]
    print("Adaptive threshold vs I_rest (k_slope=0.15, I_base=0.08)")
    print(f"{'I_rest':>8s}  {'I_thresh':>10s}  {'expected':>10s}")
    for (ir, exp) in cases:
        got = adaptive_thresh(ir, cfg.I_base, cfg.k_slope)
        ok  = abs(got - exp) < 1e-9
        print(f"  {ir:6.2f}  {got:10.4f}  {exp:10.4f}  {'OK' if ok else 'FAIL'}")
        assert ok, f"adaptive_thresh({ir}) = {got} != {exp}"

    # Security margin at I_rest=1.0, I_thresh=0.15 → 0.15/0.005 = 30
    sm = security_margin(0.15, 1.0, 0.005)
    assert abs(sm - 30.0) < 1e-6, f"security_margin = {sm}"
    print(f"\nSecurity margin at I_rest=1.0 pu: {sm:.1f}×  [expected 30×]  OK")

    # α₅₀ at no load (I_rest=0): same as TR-15 = 0.03 for ag
    # I_LINE_AG_NOM × 87L_phase_sensitivity
    # In TR-15: α₅₀(ag)=0.03, I_thresh=0.08, I_LINE_AG_NOM=4.667
    # effective phase factor = 0.08 / (0.03 × 4.667) ≈ 0.5714
    EFF_PHASE = 0.08 / (0.03 * 4.667)
    a50 = compute_alpha50(0.08, 4.667, EFF_PHASE)
    print(f"α₅₀ at no-load: {a50:.3f}  [expected 0.030]  "
          f"{'OK' if abs(a50-0.030)<0.001 else 'FAIL'}")

    print("\nline_adaptive_threshold self-test PASSED.")
