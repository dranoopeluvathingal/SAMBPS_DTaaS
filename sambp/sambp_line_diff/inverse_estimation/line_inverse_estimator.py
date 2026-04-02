"""
line_inverse_estimator.py
==========================
Two-pass Levenberg-Marquardt estimator for the 87L line zone model.

Pass 1 — Full window, all 4 parameters (I_fund, phi_fund, I_DC, tau_DC)
Pass 2 — Tail window, refine DC component (I_DC, tau_DC)
         fixing I_fund and phi_fund from Pass 1

The DC offset decays quickly; the tail window captures its late behaviour
more accurately for τ estimation.
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.optimize import least_squares
from typing import Optional

from models.line_reduced_zone_model import (
    LOWER_BOUNDS, UPPER_BOUNDS, N_PARAMS, PARAM_NAMES,
    forward_idiff, residual_vector, jacobian_idiff,
    condition_number_normalised, initial_guess, interpret_theta,
    LineZoneState,
)


# ---------------------------------------------------------------------------
# Pass 1
# ---------------------------------------------------------------------------

def _jac_wrapper(theta, t, i_diff_meas, freq_hz):
    return jacobian_idiff(t, theta, freq_hz)


def _pass1(t, i_diff_meas, x0, freq_hz=50.0, max_nfev=1000):
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
# Pass 2: refine DC component (I_DC, tau_DC) in tail window
# ---------------------------------------------------------------------------

_PASS2_FREE_IDX  = [2, 3]   # I_DC, tau_DC
_PASS2_FIXED_IDX = [0, 1]   # I_fund, phi_fund — fixed


def _residual_p2(theta_free, t, i_diff, theta_fixed, freq_hz):
    theta_full = np.empty(N_PARAMS)
    theta_full[_PASS2_FIXED_IDX] = theta_fixed
    theta_full[_PASS2_FREE_IDX]  = theta_free
    return residual_vector(theta_full, t, i_diff, freq_hz)


def _jac_p2(theta_free, t, i_diff, theta_fixed, freq_hz):
    theta_full = np.empty(N_PARAMS)
    theta_full[_PASS2_FIXED_IDX] = theta_fixed
    theta_full[_PASS2_FREE_IDX]  = theta_free
    return jacobian_idiff(t, theta_full, freq_hz)[:, _PASS2_FREE_IDX]


def _pass2(t_tail, i_diff_tail, theta_p1, freq_hz=50.0, max_nfev=400):
    x0_free    = theta_p1[_PASS2_FREE_IDX]
    lb_free    = LOWER_BOUNDS[_PASS2_FREE_IDX]
    ub_free    = UPPER_BOUNDS[_PASS2_FREE_IDX]
    theta_fixed = theta_p1[_PASS2_FIXED_IDX]

    return least_squares(
        _residual_p2,
        x0_free,
        jac=_jac_p2,
        bounds=(lb_free, ub_free),
        method="trf",
        ftol=1e-9, xtol=1e-9, gtol=1e-9,
        max_nfev=max_nfev,
        args=(t_tail, i_diff_tail, theta_fixed, freq_hz),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_line_zone_parameters(
    t_window: np.ndarray,
    i_diff_meas: np.ndarray,
    freq_hz: float = 50.0,
    x0: Optional[np.ndarray] = None,
    tail_cycles: float = 2.0,
    kappa_max: float = 80.0,
    f_int_thresh: float = 0.40,
    I_DC_thresh: float = 0.10,
    I_fund_fault_thresh: float = 0.20,
    I_C_nom: float = 0.02,
) -> dict:
    """
    Two-pass LM estimator for the 87L line zone model (4 parameters).

    Returns
    -------
    dict: theta_hat, residual_norm, jacobian, kappa_n, success, n_iter, state
    """
    N  = len(t_window)
    dt = float(t_window[1] - t_window[0]) if N > 1 else 1e-3
    fs = 1.0 / dt

    if x0 is None:
        x0 = initial_guess(t_window, i_diff_meas, freq_hz, I_C_nom=I_C_nom)
    x0 = np.clip(x0, LOWER_BOUNDS, UPPER_BOUNDS)

    # Pass 1
    res1     = _pass1(t_window, i_diff_meas, x0, freq_hz)
    theta_p1 = res1.x

    # Pass 2: tail window
    spc    = int(round(fs / freq_hz))
    n_tail = max(int(round(tail_cycles * spc)), 10)
    n_tail = min(n_tail, N)
    t_tail = t_window[-n_tail:]
    i_tail = i_diff_meas[-n_tail:]

    res2      = _pass2(t_tail, i_tail, theta_p1, freq_hz)
    theta_hat = theta_p1.copy()
    theta_hat[_PASS2_FREE_IDX] = res2.x

    # Jacobian + condition number
    J  = jacobian_idiff(t_window, theta_hat, freq_hz)
    kn = condition_number_normalised(J)

    # Residual
    r  = residual_vector(theta_hat, t_window, i_diff_meas, freq_hz)
    rn = float(np.linalg.norm(r) / max(np.sqrt(N), 1.0))

    state = interpret_theta(
        theta_hat, kn, rn,
        I_fund_fault_thresh = I_fund_fault_thresh,
        I_DC_thresh         = I_DC_thresh,
        f_int_thresh        = f_int_thresh,
        kappa_max           = kappa_max,
    )

    return {
        "theta_hat":     theta_hat,
        "residual_norm": rn,
        "jacobian":      J,
        "kappa_n":       kn,
        "success":       bool(res1.success or res2.success),
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
    t    = np.arange(0, 0.12, 1.0 / fs)

    # Test A: healthy
    theta_h = np.array([0.022, 1.57, 0.0, 0.05])
    i_h = forward_idiff(t, theta_h, freq) + 0.001*np.random.randn(len(t))
    res_h = estimate_line_zone_parameters(t, i_h, freq)
    s_h   = res_h["state"]
    print(f"[Healthy]  θ̂={np.round(res_h['theta_hat'],3)}  "
          f"κ_n={res_h['kappa_n']:.1f}  f_int={s_h.f_int:.3f}  "
          f"is_int={s_h.is_internal}")
    assert not s_h.is_internal, "Healthy should NOT flag internal"

    # Test B: fault (large sinusoidal + DC offset)
    theta_f = np.array([3.5, -0.2, 1.2, 0.05])
    i_f = forward_idiff(t, theta_f, freq) + 0.005*np.random.randn(len(t))
    res_f = estimate_line_zone_parameters(t, i_f, freq)
    s_f   = res_f["state"]
    print(f"[Fault]    θ̂={np.round(res_f['theta_hat'],3)}  "
          f"κ_n={res_f['kappa_n']:.1f}  f_int={s_f.f_int:.3f}  "
          f"is_int={s_f.is_internal}")
    assert s_f.is_internal, "Fault should flag internal"

    # Test C: sync error only
    theta_s = np.array([0.10, 0.4, 0.0, 0.05])
    i_s = forward_idiff(t, theta_s, freq) + 0.001*np.random.randn(len(t))
    res_s = estimate_line_zone_parameters(t, i_s, freq)
    s_s   = res_s["state"]
    print(f"[Sync]     θ̂={np.round(res_s['theta_hat'],3)}  "
          f"is_sync={s_s.is_sync_error}  is_int={s_s.is_internal}")
    assert s_s.is_sync_error,   "Sync should flag sync_error"
    assert not s_s.is_internal, "Sync error alone should NOT flag internal"

    print("\nline_inverse_estimator self-test PASSED.")
