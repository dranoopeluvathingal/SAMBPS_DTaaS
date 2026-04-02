"""
transformer_reduced_zone_model.py
==================================
Reduced-parameter zone model for the model-based 87T differential relay.

The forward model decomposes the transformer differential current into
identifiable components using a 5-parameter vector θ_T:

    θ_T = [I_diff_fund,   — fundamental-frequency differential amplitude [pu]
            phi_diff,      — differential current phase angle [rad]
            k_inrush,      — 2nd-harmonic content ratio (inrush indicator, 0–1)
            k_ovexc,       — 5th-harmonic content ratio (overexcitation, 0–1)
            epsilon_CT]    — CT saturation distortion amplitude [pu]

Internal fault classification (derived, not fitted)
-----------------------------------------------------
The internal fault indicator is NOT a fitted parameter (doing so creates a
collinearity with I_diff_fund when phi≈0). Instead it is derived from the
estimated blocking signatures:

    blocking_score = k_inrush/H2_thresh + k_ovexc/H5_thresh + epsilon_CT/CT_thresh
    f_int = clip(1 − blocking_score, 0, 1)

Interpretation:  when no blocking component is present (k2≈k5≈eps≈0) and
the differential is large, f_int ≈ 1 → internal fault.

Forward model
-------------
    i_diff(t) = I_diff_fund × sin(2πf·t + phi_diff)
              + k_inrush × I_diff_fund × sin(4πf·t + phi_diff)
              + k_ovexc  × I_diff_fund × sin(10πf·t + phi_diff)
              + epsilon_CT × I_diff_fund × sign(sin(2πf·t))

Parameter bounds
----------------
    I_diff_fund : [0,  10]  pu
    phi_diff    : [-π, +π]  rad
    k_inrush    : [0,  1]
    k_ovexc     : [0,  1]
    epsilon_CT  : [0,  0.5]
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional

# Parameter index map (5 parameters, identifiable)
PARAM_NAMES = ["I_diff_fund", "phi_diff", "k_inrush", "k_ovexc", "epsilon_CT"]
N_PARAMS = len(PARAM_NAMES)

LOWER_BOUNDS = np.array([0.0,  -np.pi, 0.0, 0.0, 0.0])
UPPER_BOUNDS = np.array([10.0,  np.pi, 1.0, 1.0, 0.5])


# ---------------------------------------------------------------------------
# Forward model
# ---------------------------------------------------------------------------

def forward_idiff(
    t: np.ndarray,
    theta: np.ndarray,
    freq_hz: float = 50.0,
) -> np.ndarray:
    """
    Evaluate the 5-parameter reduced-zone differential current model.

    Parameters
    ----------
    t : (N,) time array [s]
    theta : (5,) parameter vector  [I_diff_fund, phi_diff, k_inrush, k_ovexc, epsilon_CT]
    freq_hz : float

    Returns
    -------
    (N,) synthetic differential current [pu]
    """
    I_f  = float(theta[0])
    phi  = float(theta[1])
    k2   = float(theta[2])
    k5   = float(theta[3])
    eps  = float(theta[4])
    omega = 2.0 * np.pi * freq_hz

    i_diff = (
        I_f * np.sin(omega * t + phi)                       # fundamental
        + k2 * I_f * np.sin(2.0 * omega * t + phi)         # 2nd harmonic (inrush)
        + k5 * I_f * np.sin(5.0 * omega * t + phi)         # 5th harmonic (ovexc)
        + eps * I_f * np.sign(np.sin(omega * t))            # CT distortion
    )
    return i_diff


# ---------------------------------------------------------------------------
# Jacobian (analytical)
# ---------------------------------------------------------------------------

def jacobian_idiff(
    t: np.ndarray,
    theta: np.ndarray,
    freq_hz: float = 50.0,
) -> np.ndarray:
    """
    Analytical Jacobian ∂i_diff/∂θ_j — shape (N, 5).
    """
    I_f  = float(theta[0])
    phi  = float(theta[1])
    k2   = float(theta[2])
    k5   = float(theta[3])
    eps  = float(theta[4])
    omega = 2.0 * np.pi * freq_hz

    s1  = np.sin(omega * t + phi)
    c1  = np.cos(omega * t + phi)
    s2  = np.sin(2.0 * omega * t + phi)
    c2  = np.cos(2.0 * omega * t + phi)
    s5  = np.sin(5.0 * omega * t + phi)
    c5  = np.cos(5.0 * omega * t + phi)
    sgn = np.sign(np.sin(omega * t))

    dI_f = s1 + k2*s2 + k5*s5 + eps*sgn
    dphi = I_f * (c1 + k2*c2 + k5*c5)
    dk2  = I_f * s2
    dk5  = I_f * s5
    deps = I_f * sgn

    return np.column_stack([dI_f, dphi, dk2, dk5, deps])


# ---------------------------------------------------------------------------
# Column-normalised condition number
# ---------------------------------------------------------------------------

def condition_number_normalised(J: np.ndarray) -> float:
    """κ_n(J) — removes column scale to give identifiability metric."""
    col_norms = np.linalg.norm(J, axis=0)
    col_norms = np.where(col_norms < 1e-12, 1.0, col_norms)
    J_n = J / col_norms[np.newaxis, :]
    sv = np.linalg.svd(J_n, compute_uv=False)
    if sv[-1] < 1e-14:
        return float("inf")
    return float(sv[0] / sv[-1])


# ---------------------------------------------------------------------------
# Residual vector
# ---------------------------------------------------------------------------

def residual_vector(
    theta: np.ndarray,
    t: np.ndarray,
    i_diff_meas: np.ndarray,
    freq_hz: float = 50.0,
) -> np.ndarray:
    """Residual r = i_diff_meas - forward_idiff(t, theta)."""
    return i_diff_meas - forward_idiff(t, theta, freq_hz)


# ---------------------------------------------------------------------------
# Initial guess heuristic
# ---------------------------------------------------------------------------

def initial_guess(
    t: np.ndarray,
    i_diff_meas: np.ndarray,
    freq_hz: float = 50.0,
) -> np.ndarray:
    """
    Physics-informed starting point for θ_T from raw measurements.
    """
    N   = len(t)
    dt  = float(t[1] - t[0])
    fs  = 1.0 / dt

    freqs = np.fft.rfftfreq(N, d=dt)
    F     = np.fft.rfft(i_diff_meas)
    F_mag = np.abs(F) * 2.0 / N

    def _amp_at(f_target):
        idx = int(round(f_target / (fs / N)))
        idx = np.clip(idx, 0, len(F_mag) - 1)
        return float(F_mag[idx])

    A1 = _amp_at(freq_hz)
    A2 = _amp_at(2.0 * freq_hz)
    A5 = _amp_at(5.0 * freq_hz)

    I_diff_fund = max(A1, 1e-4)
    k_inrush    = float(np.clip(A2 / I_diff_fund, 0.0, 1.0))
    k_ovexc     = float(np.clip(A5 / I_diff_fund, 0.0, 1.0))

    # Phase estimate
    F_full = np.zeros(N, dtype=complex)
    F_full[:len(F)] = F
    F_analytic = np.where(np.fft.fftfreq(N, d=dt) > 0, 2*F_full, F_full)
    F_analytic[0] = F_full[0]
    analytic = np.fft.ifft(F_analytic)
    phi_diff = float(np.angle(np.mean(analytic)))

    return np.array([I_diff_fund, phi_diff, k_inrush, k_ovexc, 0.05])


# ---------------------------------------------------------------------------
# Internal fault score (derived, not fitted)
# ---------------------------------------------------------------------------

def compute_f_int(
    k_inrush: float,
    k_ovexc: float,
    epsilon_CT: float,
    H2_thresh: float = 0.15,
    H5_thresh: float = 0.35,
    CT_thresh: float = 0.10,
) -> float:
    """
    Derived internal-fault indicator.

    Logic: blocking_score = normalised sum of all known blocking contributions.
    f_int = 1 − blocking_score  (clamped to [0,1]).

    When all blocking signatures are absent → f_int ≈ 1 (differential is
    unexplained by known non-fault causes → internal fault likely).
    """
    blocking_score = (
        k_inrush   / max(H2_thresh, 1e-9)  * H2_thresh
        + k_ovexc  / max(H5_thresh, 1e-9)  * H5_thresh
        + epsilon_CT / max(CT_thresh, 1e-9) * CT_thresh
    )
    # Normalise by the sum of thresholds so blocking_score ∈ [0, ∞)
    # Saturate at 1 (fully explained)
    normaliser = H2_thresh + H5_thresh + CT_thresh
    blocking_fraction = float(np.clip(blocking_score / normaliser, 0.0, 1.0))
    return float(np.clip(1.0 - blocking_fraction, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Parameter interpretation
# ---------------------------------------------------------------------------

@dataclass
class ZoneModelState:
    """Interpreted state from the zone model parameters."""
    I_diff_fund: float
    phi_diff: float
    k_inrush: float
    k_ovexc: float
    epsilon_CT: float
    f_int: float             # derived, not fitted
    kappa_n: float           = float("inf")
    residual_norm: float     = float("inf")
    confidence: float        = 0.0

    # Classification flags
    is_inrush: bool          = False
    is_overexcitation: bool  = False
    is_ct_saturated: bool    = False
    is_internal_fault: bool  = False


def interpret_theta(
    theta: np.ndarray,
    kappa_n: float,
    residual_norm: float,
    H2_thresh: float = 0.15,
    H5_thresh: float = 0.35,
    CT_thresh: float = 0.10,
    f_int_thresh: float = 0.60,
    kappa_max: float = 50.0,
) -> ZoneModelState:
    """
    Convert raw θ_T vector into a ZoneModelState with human-readable flags.

    Confidence metric:
        confidence = clip(1 − (κ_n − 1)/(κ_max − 1), 0, 1) × exp(−||r||)
    High confidence requires both low condition number and small residual.
    """
    I_f  = float(theta[0])
    phi  = float(theta[1])
    k2   = float(theta[2])
    k5   = float(theta[3])
    eps  = float(theta[4])

    # Derived internal fault indicator
    f_int = compute_f_int(k2, k5, eps, H2_thresh, H5_thresh, CT_thresh)

    kn_conf   = float(np.clip(1.0 - (kappa_n - 1.0) / max(kappa_max - 1.0, 1.0),
                              0.0, 1.0))
    res_conf  = float(np.exp(-residual_norm))
    confidence = kn_conf * res_conf

    return ZoneModelState(
        I_diff_fund       = I_f,
        phi_diff          = phi,
        k_inrush          = k2,
        k_ovexc           = k5,
        epsilon_CT        = eps,
        f_int             = f_int,
        kappa_n           = kappa_n,
        residual_norm     = residual_norm,
        confidence        = confidence,
        is_inrush         = k2 >= H2_thresh,
        is_overexcitation = k5 >= H5_thresh,
        is_ct_saturated   = eps >= CT_thresh,
        is_internal_fault = (f_int >= f_int_thresh)
                            and not (k2 >= H2_thresh)
                            and not (k5 >= H5_thresh),
    )


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    freq = 50.0
    fs   = 1000.0
    t    = np.arange(0, 0.06, 1.0 / fs)

    # Test A: inrush-like signal (k2=0.42 large)
    theta_inrush = np.array([2.5, 0.3, 0.42, 0.05, 0.08])
    i_diff = forward_idiff(t, theta_inrush, freq)
    noise  = 0.01 * np.random.randn(len(t))
    i_meas = i_diff + noise

    J = jacobian_idiff(t, theta_inrush, freq)
    assert J.shape == (len(t), N_PARAMS), f"Jacobian shape error: {J.shape}"

    kn = condition_number_normalised(J)
    print(f"κ_n (inrush) = {kn:.2f}")

    x0 = initial_guess(t, i_meas, freq)
    print(f"Initial guess: {dict(zip(PARAM_NAMES, np.round(x0, 3)))}")

    r = residual_vector(theta_inrush, t, i_meas, freq)
    print(f"Residual norm at true θ: {np.linalg.norm(r):.4f}")

    state_inrush = interpret_theta(theta_inrush, kn, np.linalg.norm(r))
    print(f"is_inrush={state_inrush.is_inrush}  "
          f"f_int={state_inrush.f_int:.3f}  "
          f"confidence={state_inrush.confidence:.3f}")
    assert state_inrush.is_inrush, "Should detect inrush (k2=0.42 > 0.15)"
    assert not state_inrush.is_internal_fault, "Should NOT flag internal fault for inrush"

    # Test B: clean differential (internal fault: k2≈0, k5≈0)
    theta_int = np.array([3.0, -0.1, 0.02, 0.01, 0.04])
    state_int = interpret_theta(theta_int, kappa_n=8.0, residual_norm=0.04)
    print(f"is_internal_fault={state_int.is_internal_fault}  f_int={state_int.f_int:.3f}")
    assert state_int.is_internal_fault, "Should flag internal fault (no blocking signatures)"

    print("transformer_reduced_zone_model self-test PASSED.")
