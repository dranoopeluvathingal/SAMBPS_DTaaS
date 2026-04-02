"""
bus_inverse_estimator.py
=========================
Two-pass Levenberg-Marquardt estimator for the 87B bus differential zone model.

Pass 1 — full window, all 3 parameters free:
    θ = [I_diff_fund, φ_diff, ε_CT]

Pass 2 — tail window (last 2 cycles), refine ε_CT, fix I_diff_fund and φ:
    Free: [ε_CT]            (index 2)
    Fixed: [I_diff_fund, φ]  (indices 0, 1)

Rationale:  ε_CT captures the saturation distortion, which is most visible
in the steady-state tail after the initial transient.  The fundamental
component (I_diff_fund, φ) settles in the first cycle.

κ_n threshold:  30  (same as 87T/87L — bus model is even better conditioned)
"""

from __future__ import annotations

import numpy as np
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scipy.optimize import least_squares

from models.bus_reduced_zone_model import (
    forward_idiff, jacobian_idiff, condition_number_normalised,
    LOWER_BOUNDS, UPPER_BOUNDS, PARAM_NAMES, interpret_theta,
)

# Pass 2: refine only ε_CT
_PASS2_FREE_IDX  = [2]      # ε_CT
_PASS2_FIXED_IDX = [0, 1]   # I_diff_fund, φ

_KAPPA_MAX_DEFAULT = 30.0
_TAIL_CYCLES       = 2.0


# ---------------------------------------------------------------------------
# Residual and Jacobian wrappers for scipy
# ---------------------------------------------------------------------------

def _residual(theta, t, i_diff_meas, freq_hz):
    return i_diff_meas - forward_idiff(t, theta, freq_hz)


def _jac_wrapper(theta, t, i_diff_meas, freq_hz):
    return -jacobian_idiff(t, theta, freq_hz)


# ---------------------------------------------------------------------------
# Pass 2 helpers (fix selected parameters)
# ---------------------------------------------------------------------------

def _residual_pass2(theta_free, theta_fixed, free_idx, fixed_idx, t, y, freq_hz):
    theta_full = np.empty(3)
    theta_full[free_idx]  = theta_free
    theta_full[fixed_idx] = theta_fixed
    return _residual(theta_full, t, y, freq_hz)


def _jac_pass2(theta_free, theta_fixed, free_idx, fixed_idx, t, y, freq_hz):
    theta_full = np.empty(3)
    theta_full[free_idx]  = theta_free
    theta_full[fixed_idx] = theta_fixed
    J_full = -jacobian_idiff(t, theta_full, freq_hz)
    return J_full[:, free_idx]


# ---------------------------------------------------------------------------
# Main estimator
# ---------------------------------------------------------------------------

def estimate_bus_zone_parameters(
    t_window: np.ndarray,
    i_diff_meas: np.ndarray,
    freq_hz: float = 50.0,
    x0: np.ndarray | None = None,
    tail_cycles: float = _TAIL_CYCLES,
    kappa_max: float   = _KAPPA_MAX_DEFAULT,
    max_nfev: int      = 200,
) -> dict:
    """
    Estimate θ_B = [I_diff_fund, φ_diff, ε_CT] from differential current.

    Parameters
    ----------
    t_window    : (N,) time vector [s]
    i_diff_meas : (N,) differential current [pu]
    freq_hz     : power system frequency [Hz]
    x0          : initial guess (length 3); defaults to [rms, 0, 0]
    tail_cycles : how many cycles from the end to use for Pass 2
    kappa_max   : column-normalised condition number threshold

    Returns
    -------
    dict with keys: theta_hat, kappa_n, residual_norm, converged, state, pass2_used
    """
    N = len(t_window)

    # Default initial guess
    if x0 is None:
        I_rms = float(np.sqrt(np.mean(i_diff_meas**2))) * np.sqrt(2)
        x0 = np.array([max(I_rms, 0.01), 0.0, 0.0])

    # ---- Pass 1: full window -------------------------------------------------
    result1 = least_squares(
        _residual, x0,
        jac   = _jac_wrapper,
        args  = (t_window, i_diff_meas, freq_hz),
        bounds= (LOWER_BOUNDS, UPPER_BOUNDS),
        method= "trf",
        max_nfev = max_nfev,
    )
    theta1 = np.clip(result1.x, LOWER_BOUNDS, UPPER_BOUNDS)

    # ---- Pass 2: tail window, refine ε_CT ------------------------------------
    spc       = int(round(freq_hz / freq_hz))   # samples per cycle at 1 Hz base
    spc_real  = int(round(len(t_window) / (t_window[-1] - t_window[0]) / freq_hz))
    tail_n    = max(int(tail_cycles * spc_real), 10)
    t_tail    = t_window[-tail_n:]
    y_tail    = i_diff_meas[-tail_n:]

    theta_free0  = theta1[_PASS2_FREE_IDX]
    theta_fixed  = theta1[_PASS2_FIXED_IDX]
    lb2 = LOWER_BOUNDS[_PASS2_FREE_IDX]
    ub2 = UPPER_BOUNDS[_PASS2_FREE_IDX]

    result2 = least_squares(
        _residual_pass2, theta_free0,
        jac   = _jac_pass2,
        args  = (theta_fixed, _PASS2_FREE_IDX, _PASS2_FIXED_IDX,
                 t_tail, y_tail, freq_hz),
        bounds= (lb2, ub2),
        method= "trf",
        max_nfev = max_nfev,
    )
    theta2 = theta1.copy()
    theta2[_PASS2_FREE_IDX] = np.clip(result2.x, lb2, ub2)

    # ---- Condition number and residual at Pass 2 solution --------------------
    J_final = jacobian_idiff(t_window, theta2, freq_hz)
    kappa_n = condition_number_normalised(J_final)

    resid       = i_diff_meas - forward_idiff(t_window, theta2, freq_hz)
    i_norm      = max(np.sqrt(np.mean(i_diff_meas**2)), 1e-6)
    resid_norm  = float(np.sqrt(np.mean(resid**2)) / i_norm)

    converged   = kappa_n < kappa_max

    state = interpret_theta(theta2, kappa_n=kappa_n, residual_norm=resid_norm)

    return {
        "theta_hat":    theta2,
        "kappa_n":      kappa_n,
        "residual_norm": resid_norm,
        "converged":    converged,
        "state":        state,
        "pass2_used":   True,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    np.random.seed(42)
    t   = np.linspace(0, 0.06, 60)
    f   = 50.0
    omega = 2 * np.pi * f

    # ----- Test 1: clean internal fault (ε_CT=0) ------------------------------
    theta_true = np.array([4.0, 0.15, 0.0])
    y_true  = forward_idiff(t, theta_true, f)
    y_noisy = y_true + 0.02 * np.random.randn(len(t))

    res = estimate_bus_zone_parameters(t, y_noisy, freq_hz=f)
    print(f"  Internal fault:")
    print(f"    theta_hat = {res['theta_hat']}")
    print(f"    κ_n={res['kappa_n']:.2f}  rn={res['residual_norm']:.4f}  "
          f"f_int={res['state'].f_int:.3f}  converged={res['converged']}")
    assert res["converged"],         "Must converge on clean internal fault"
    assert res["state"].f_int > 0.8, "f_int must be high for clean differential"

    # ----- Test 2: CT saturation (ε_CT=0.30) ---------------------------------
    theta_sat = np.array([2.0, 0.1, 0.30])
    y_sat = forward_idiff(t, theta_sat, f) + 0.02 * np.random.randn(len(t))

    res2 = estimate_bus_zone_parameters(t, y_sat, freq_hz=f)
    print(f"\n  CT saturation:")
    print(f"    theta_hat = {res2['theta_hat']}")
    print(f"    κ_n={res2['kappa_n']:.2f}  rn={res2['residual_norm']:.4f}  "
          f"f_int={res2['state'].f_int:.3f}  converged={res2['converged']}")
    assert res2["state"].f_int < 0.5, "f_int must be low for CT saturation"

    print("\nbus_inverse_estimator self-test PASSED.")
