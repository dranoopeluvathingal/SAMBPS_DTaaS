"""
line_pv_estimator.py
=====================
SAMBP TR-62/2026 — Single-pass Levenberg-Marquardt estimator for the
2-parameter Solar PV differential current model.

Because the 2-parameter model has a near-orthogonal Jacobian (κ_n ≈ 1),
a single LM pass converges in ≤ 5 iterations for all practical initial guesses.
The tail-window Pass 2 used in the SG estimator (line_inverse_estimator.py) is
not required: there is no DC component to refine.

Interface
---------
    estimate_pv_zone_parameters(t_window, i_diff_meas, ...) -> dict

    Return dict keys (matching line_inverse_estimator API for drop-in compatibility):
        theta_hat     : (2,) estimated [I_fund, phi_fund]
        residual_norm : normalised residual ‖r‖/sqrt(N)
        jacobian      : (N, 2) Jacobian at θ_hat
        kappa_n       : normalised condition number
        success       : bool
        n_iter        : int
        state         : PVZoneState
        param_names   : list[str]
        model         : 'pv'
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.optimize import least_squares
from typing import Optional

from models.line_pv_model import (
    PARAM_NAMES_PV, N_PARAMS_PV,
    LOWER_BOUNDS_PV, UPPER_BOUNDS_PV,
    forward_idiff_pv, residual_vector_pv, jacobian_idiff_pv,
    condition_number_pv, initial_guess_pv, interpret_theta_pv,
    I_FUND_THRESH_PV_DEFAULT,
)


# ---------------------------------------------------------------------------
# Jacobian wrapper for scipy.optimize.least_squares
# ---------------------------------------------------------------------------

def _jac_wrapper_pv(theta, t, i_diff_meas, freq_hz):
    return jacobian_idiff_pv(t, theta, freq_hz)


# ---------------------------------------------------------------------------
# Single-pass LM
# ---------------------------------------------------------------------------

def _pass1_pv(t, i_diff_meas, x0, freq_hz=50.0, max_nfev=200):
    return least_squares(
        residual_vector_pv,
        x0,
        jac=_jac_wrapper_pv,
        bounds=(LOWER_BOUNDS_PV, UPPER_BOUNDS_PV),
        method="trf",
        ftol=1e-9, xtol=1e-9, gtol=1e-9,
        max_nfev=max_nfev,
        args=(t, i_diff_meas, freq_hz),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_pv_zone_parameters(
    t_window:         np.ndarray,
    i_diff_meas:      np.ndarray,
    freq_hz:          float = 50.0,
    x0:               Optional[np.ndarray] = None,
    kappa_max:        float = 30.0,
    I_fund_thresh:    float = I_FUND_THRESH_PV_DEFAULT,
    I_C_nom:          float = 0.02,
) -> dict:
    """
    Single-pass LM estimator for the 2-parameter PV zone model.

    Parameters
    ----------
    t_window      : (N,) time array [s] (relative to window start)
    i_diff_meas   : (N,) measured differential current [pu]
    freq_hz       : power system frequency [Hz]
    x0            : initial guess (2,) — None for DFT-based auto-guess
    kappa_max     : condition number ceiling for confidence computation
    I_fund_thresh : detection threshold [pu] (default 0.058 pu)
    I_C_nom       : nominal charging current [pu]

    Returns
    -------
    dict with keys:
        theta_hat, residual_norm, jacobian, kappa_n, success, n_iter,
        state (PVZoneState), param_names, model='pv'
    """
    N  = len(t_window)
    if N < 4:
        raise ValueError(f"Window too short: N={N}, need ≥ 4 samples")

    if x0 is None:
        x0 = initial_guess_pv(t_window, i_diff_meas, freq_hz, I_C_nom=I_C_nom)
    x0 = np.clip(x0, LOWER_BOUNDS_PV, UPPER_BOUNDS_PV)

    res      = _pass1_pv(t_window, i_diff_meas, x0, freq_hz)
    theta_hat = res.x

    J  = jacobian_idiff_pv(t_window, theta_hat, freq_hz)
    kn = condition_number_pv(J)

    r  = residual_vector_pv(theta_hat, t_window, i_diff_meas, freq_hz)
    rn = float(np.linalg.norm(r) / max(np.sqrt(N), 1.0))

    state = interpret_theta_pv(theta_hat, kn, rn,
                                I_fund_thresh=I_fund_thresh,
                                kappa_max=kappa_max)

    return {
        "theta_hat":     theta_hat,
        "residual_norm": rn,
        "jacobian":      J,
        "kappa_n":       kn,
        "success":       bool(res.success),
        "n_iter":        int(res.nfev),
        "state":         state,
        "param_names":   PARAM_NAMES_PV,
        "model":         "pv",
    }


# ---------------------------------------------------------------------------
# Unified estimator: auto-selects model based on selector decision
# ---------------------------------------------------------------------------

def estimate_line_zone_adaptive(
    t_window:      np.ndarray,
    i_diff_meas:   np.ndarray,
    model:         str = "sg",
    freq_hz:       float = 50.0,
    x0:            Optional[np.ndarray] = None,
    I_fund_thresh: float = I_FUND_THRESH_PV_DEFAULT,
    I_C_nom:       float = 0.02,
) -> dict:
    """
    Route estimation to either the 2-param PV estimator or the 4-param SG
    estimator based on the model selector decision.

    Parameters
    ----------
    model : 'pv' or 'sg'

    Returns the standard estimator dict with an added 'model' key.
    """
    if model == "pv":
        return estimate_pv_zone_parameters(
            t_window, i_diff_meas, freq_hz, x0,
            I_fund_thresh=I_fund_thresh, I_C_nom=I_C_nom,
        )
    else:
        # Import SG estimator only when needed (avoids circular import)
        from line_inverse_estimator import estimate_line_zone_parameters
        result = estimate_line_zone_parameters(
            t_window, i_diff_meas, freq_hz, x0,
            I_fund_fault_thresh=I_fund_thresh, I_C_nom=I_C_nom,
        )
        result["model"] = "sg"
        return result


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    freq = 50.0
    fs   = 1000.0
    t    = np.arange(0, 0.10, 1.0 / fs)   # 5 cycles

    # Test A: PV healthy (charging current)
    theta_h = np.array([0.022, 1.57])
    i_h     = forward_idiff_pv(t, theta_h, freq) + 0.001 * np.random.randn(len(t))
    res_h   = estimate_pv_zone_parameters(t, i_h, freq)
    s_h     = res_h["state"]
    print(f"[PV Healthy]  θ̂={np.round(res_h['theta_hat'],4)}  "
          f"κ_n={res_h['kappa_n']:.2f}  "
          f"is_internal={s_h.is_internal}  n_iter={res_h['n_iter']}")
    assert not s_h.is_internal, "PV healthy should NOT flag internal"
    assert res_h["kappa_n"] < 3.0, f"κ_n should be ≈1, got {res_h['kappa_n']:.2f}"
    assert res_h["n_iter"] <= 20, f"Should converge fast, n_iter={res_h['n_iter']}"

    # Test B: PV internal fault (k_ibr = 1.0 pu)
    theta_f = np.array([1.0, -0.30])
    i_f     = forward_idiff_pv(t, theta_f, freq) + 0.003 * np.random.randn(len(t))
    res_f   = estimate_pv_zone_parameters(t, i_f, freq)
    s_f     = res_f["state"]
    print(f"[PV Fault]    θ̂={np.round(res_f['theta_hat'],4)}  "
          f"κ_n={res_f['kappa_n']:.2f}  "
          f"is_internal={s_f.is_internal}  n_iter={res_f['n_iter']}")
    assert s_f.is_internal, "PV fault should flag internal"
    assert res_f["kappa_n"] < 3.0

    # Test C: Near-threshold detection (I_fund = 0.060 pu)
    theta_t = np.array([0.060, 0.50])
    i_t     = forward_idiff_pv(t, theta_t, freq) + 0.0005 * np.random.randn(len(t))
    res_t   = estimate_pv_zone_parameters(t, i_t, freq, I_fund_thresh=0.058)
    s_t     = res_t["state"]
    print(f"[PV Thresh]   θ̂={np.round(res_t['theta_hat'],4)}  "
          f"I_fund={s_t.I_fund:.4f}  is_internal={s_t.is_internal}  [expected True]")
    assert s_t.is_internal, "0.060 pu > 0.058 threshold must be detected"

    # Test D: Convergence speed comparison with 4-param estimator
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from line_inverse_estimator import estimate_line_zone_parameters

    # PV fault in 4-param estimator: I_DC=0 but estimator doesn't know that
    theta_4p_gt = np.array([1.0, -0.30, 0.0, 0.05])
    from models.line_reduced_zone_model import forward_idiff
    i_4p = forward_idiff(t, theta_4p_gt, freq) + 0.003 * np.random.randn(len(t))

    res_4p = estimate_line_zone_parameters(t, i_4p, freq)
    res_2p = estimate_pv_zone_parameters(t, i_f, freq)   # same fault, PV model

    print(f"\n[Convergence speed (PV fault)]")
    print(f"  4-param: κ_n={res_4p['kappa_n']:.1f}  n_iter={res_4p['n_iter']}")
    print(f"  2-param: κ_n={res_2p['kappa_n']:.2f}  n_iter={res_2p['n_iter']}")
    assert res_2p["n_iter"] <= res_4p["n_iter"], \
        "2-param should converge no slower than 4-param"

    print("\nline_pv_estimator self-test PASSED.")
