"""
transformer_inverse_estimator.py
=================================
Bounded nonlinear Levenberg-Marquardt estimator for the transformer zone model.

Two-pass strategy (mirrors sambp_sync_oc two-pass design):
    Pass 1 — Full window, all 6 parameters, find global shape
    Pass 2 — Tail window (last N_tail samples), refine slowly-varying
             parameters (k_inrush, k_ovexc, f_int) with I_diff_fund and
             phi_diff fixed from Pass 1.

The output includes:
    theta_hat     : best-fit parameter vector (6,)
    residual_norm : ||r|| / sqrt(N)  (normalised)
    jacobian      : (N, 6) Jacobian at solution
    kappa_n       : column-normalised condition number
    success       : bool
    n_iter        : LM iterations consumed
    state         : ZoneModelState (flags + confidence)

Usage
------
    from inverse_estimation.transformer_inverse_estimator import estimate_zone_parameters
    result = estimate_zone_parameters(t_window, i_diff_meas)
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from typing import Optional

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from models.transformer_reduced_zone_model import (
    LOWER_BOUNDS, UPPER_BOUNDS, N_PARAMS, PARAM_NAMES,
    forward_idiff, residual_vector, jacobian_idiff,
    condition_number_normalised, initial_guess, interpret_theta,
    ZoneModelState,
)


# ---------------------------------------------------------------------------
# Pass 1: full window, all 6 parameters
# ---------------------------------------------------------------------------

def _jac_wrapper(theta, t, i_diff_meas, freq_hz):
    """Adapter: scipy calls jac(x, *args) so args follow theta."""
    return jacobian_idiff(t, theta, freq_hz)


def _pass1(
    t: np.ndarray,
    i_diff_meas: np.ndarray,
    x0: np.ndarray,
    freq_hz: float = 50.0,
    max_nfev: int = 800,
) -> least_squares:
    return least_squares(
        residual_vector,
        x0,
        jac=_jac_wrapper,
        bounds=(LOWER_BOUNDS, UPPER_BOUNDS),
        method="trf",
        ftol=1e-8, xtol=1e-8, gtol=1e-8,
        max_nfev=max_nfev,
        args=(t, i_diff_meas, freq_hz),
    )


# ---------------------------------------------------------------------------
# Pass 2: tail window, refine harmonic and fault indicators
# ---------------------------------------------------------------------------

# Free parameters in Pass 2: indices 2 (k_inrush), 3 (k_ovexc), 4 (epsilon_CT)
_PASS2_FREE_IDX  = [2, 3, 4]
_PASS2_FIXED_IDX = [0, 1]   # I_diff_fund, phi_diff fixed from Pass 1


def _residual_pass2(
    theta_free: np.ndarray,
    t: np.ndarray,
    i_diff_meas: np.ndarray,
    theta_fixed: np.ndarray,
    freq_hz: float,
) -> np.ndarray:
    theta_full = np.empty(N_PARAMS)
    theta_full[_PASS2_FIXED_IDX] = theta_fixed
    theta_full[_PASS2_FREE_IDX]  = theta_free
    return residual_vector(theta_full, t, i_diff_meas, freq_hz)


def _jac_pass2(
    theta_free: np.ndarray,
    t: np.ndarray,
    i_diff_meas: np.ndarray,
    theta_fixed: np.ndarray,
    freq_hz: float,
) -> np.ndarray:
    theta_full = np.empty(N_PARAMS)
    theta_full[_PASS2_FIXED_IDX] = theta_fixed
    theta_full[_PASS2_FREE_IDX]  = theta_free
    J_full = jacobian_idiff(t, theta_full, freq_hz)
    return J_full[:, _PASS2_FREE_IDX]


def _pass2(
    t_tail: np.ndarray,
    i_diff_tail: np.ndarray,
    theta_pass1: np.ndarray,
    freq_hz: float = 50.0,
    max_nfev: int = 400,
) -> least_squares:
    x0_free  = theta_pass1[_PASS2_FREE_IDX]
    lb_free  = LOWER_BOUNDS[_PASS2_FREE_IDX]
    ub_free  = UPPER_BOUNDS[_PASS2_FREE_IDX]
    theta_fixed = theta_pass1[_PASS2_FIXED_IDX]

    return least_squares(
        _residual_pass2,
        x0_free,
        jac=_jac_pass2,
        bounds=(lb_free, ub_free),
        method="trf",
        ftol=1e-9, xtol=1e-9, gtol=1e-9,
        max_nfev=max_nfev,
        args=(t_tail, i_diff_tail, theta_fixed, freq_hz),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_zone_parameters(
    t_window: np.ndarray,
    i_diff_meas: np.ndarray,
    freq_hz: float = 50.0,
    x0: Optional[np.ndarray] = None,
    tail_cycles: float = 2.0,
    kappa_max: float = 50.0,
    H2_thresh: float = 0.15,
    H5_thresh: float = 0.35,
    CT_thresh: float = 0.10,
    f_int_thresh: float = 0.60,
) -> dict:
    """
    Two-pass Levenberg-Marquardt estimator for transformer zone model.

    Parameters
    ----------
    t_window : (N,) time array [s]
    i_diff_meas : (N,) differential current [pu]
    freq_hz : float
    x0 : (6,) initial guess (auto if None)
    tail_cycles : float — length of tail window for Pass 2
    kappa_max : float — condition number threshold for confidence

    Returns
    -------
    dict with keys:
        theta_hat, residual_norm, jacobian, kappa_n, success, n_iter, state
    """
    N  = len(t_window)
    dt = float(t_window[1] - t_window[0]) if N > 1 else 1e-3
    fs = 1.0 / dt

    # --- Initial guess -------------------------------------------------------
    if x0 is None:
        x0 = initial_guess(t_window, i_diff_meas, freq_hz)

    # Clip to bounds
    x0 = np.clip(x0, LOWER_BOUNDS, UPPER_BOUNDS)

    # --- Pass 1 --------------------------------------------------------------
    res1 = _pass1(t_window, i_diff_meas, x0, freq_hz)
    theta_p1 = res1.x

    # --- Pass 2 (tail window) ------------------------------------------------
    spc        = int(round(fs / freq_hz))
    n_tail     = max(int(round(tail_cycles * spc)), 10)
    n_tail     = min(n_tail, N)
    t_tail     = t_window[-n_tail:]
    i_diff_tail = i_diff_meas[-n_tail:]

    res2 = _pass2(t_tail, i_diff_tail, theta_p1, freq_hz)

    # Merge: keep fixed params from Pass 1, update free from Pass 2
    theta_hat = theta_p1.copy()
    theta_hat[_PASS2_FREE_IDX] = res2.x

    # --- Jacobian and condition number ----------------------------------------
    J    = jacobian_idiff(t_window, theta_hat, freq_hz)
    kn   = condition_number_normalised(J)

    # --- Residual -------------------------------------------------------------
    r    = residual_vector(theta_hat, t_window, i_diff_meas, freq_hz)
    rn   = float(np.linalg.norm(r) / max(np.sqrt(N), 1.0))

    # --- Interpret ------------------------------------------------------------
    state = interpret_theta(
        theta_hat, kn, rn,
        H2_thresh=H2_thresh, H5_thresh=H5_thresh,
        CT_thresh=CT_thresh, f_int_thresh=f_int_thresh,
        kappa_max=kappa_max,
    )

    success = bool(res1.success or res2.success)

    return {
        "theta_hat":     theta_hat,
        "residual_norm": rn,
        "jacobian":      J,
        "kappa_n":       kn,
        "success":       success,
        "n_iter":        int(res1.nfev + res2.nfev),
        "state":         state,
        "param_names":   PARAM_NAMES,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    freq = 50.0
    fs   = 1000.0
    t    = np.arange(0, 0.1, 1.0 / fs)

    # --- Test A: inrush scenario (k2=0.45 large) ----------------------------
    theta_inrush = np.array([1.8, 0.2, 0.45, 0.03, 0.06])
    i_diff_A = forward_idiff(t, theta_inrush, freq) + 0.01*np.random.randn(len(t))
    res_A = estimate_zone_parameters(t, i_diff_A, freq)
    s_A   = res_A["state"]
    print(f"[Inrush]   θ̂ = {np.round(res_A['theta_hat'], 3)}")
    print(f"           κ_n={res_A['kappa_n']:.1f}  conf={s_A.confidence:.3f}  "
          f"is_inrush={s_A.is_inrush}  f_int={s_A.f_int:.3f}  "
          f"is_internal={s_A.is_internal_fault}")
    assert s_A.is_inrush, "Should flag inrush"
    assert not s_A.is_internal_fault, "Should NOT flag internal fault"

    # --- Test B: internal fault (k2≈0, k5≈0, clean differential) -----------
    theta_int = np.array([3.0, -0.1, 0.02, 0.01, 0.04])
    i_diff_B = forward_idiff(t, theta_int, freq) + 0.01*np.random.randn(len(t))
    res_B = estimate_zone_parameters(t, i_diff_B, freq)
    s_B   = res_B["state"]
    print(f"\n[Internal] θ̂ = {np.round(res_B['theta_hat'], 3)}")
    print(f"           κ_n={res_B['kappa_n']:.1f}  conf={s_B.confidence:.3f}  "
          f"is_inrush={s_B.is_inrush}  f_int={s_B.f_int:.3f}  "
          f"is_internal={s_B.is_internal_fault}")
    assert s_B.is_internal_fault, "Should flag internal fault (no blocking signatures)"
    assert not s_B.is_inrush, "Should NOT flag inrush"

    print("\ntransformer_inverse_estimator self-test PASSED.")
