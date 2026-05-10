"""
line_dfig_estimator.py
======================
SAMBP TR-56 / 2026 — LM estimator for the 10-parameter DFIG fault current
model used in 87L line differential protection.

Two-pass estimation strategy
-----------------------------
Pass 1 — crowbar time identification:
    Fix t_cb to a grid of candidate values [0.005, 0.01, ..., 0.12] s.
    For each candidate, run LM with reduced parameter set:
        θ_1 = [I_sub, tau_ac, I_dc, phi_a, I_ss, phi_cc]
    Select t_cb* that minimises the residual norm.

Pass 2 — full 10-parameter refinement:
    Initialise from Pass-1 best estimate.
    Run LM on the complete θ_DFIG vector.

CUSUM pre-filter:
    If detect_crowbar_cusum() returns a time, use it as t_cb initialisation
    (replacing the Pass-1 grid scan).  This accelerates convergence and
    improves t_cb accuracy.

Public API
----------
    estimate_dfig_parameters(t, ia, theta0, bounds, f0, use_cusum)
        → dict  {theta_hat, success, cost, residual_norm, jacobian,
                 t_cb_hat, pass1_best, n_evaluations}
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from typing import Optional

from models.line_dfig_model import (
    dfig_phase_A,
    dfig_residual,
    detect_crowbar_cusum,
    theta_dfig_to_vector,
    vector_to_theta_dfig,
    THETA_KEYS_DFIG,
    DEFAULT_THETA_DFIG,
    DFIG_BOUNDS,
)


# ---------------------------------------------------------------------------
# Bound helpers
# ---------------------------------------------------------------------------

def _build_dfig_bounds(bounds: list) -> tuple:
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    return lo, hi


# ---------------------------------------------------------------------------
# Pass-1 reduced-parameter scan
# ---------------------------------------------------------------------------

_PASS1_KEYS = ["I_sub", "tau_ac", "tau_dc", "phi_a", "I_dc", "I_ss", "phi_cc", "k_slip"]
_PASS1_IDX  = [THETA_KEYS_DFIG.index(k) for k in _PASS1_KEYS]

_TCB_GRID = np.array([0.005, 0.010, 0.015, 0.020, 0.030, 0.040,
                       0.050, 0.060, 0.080, 0.100, 0.120])


def _pass1_residual(v_reduced: np.ndarray, t: np.ndarray, ia: np.ndarray,
                    t_cb_fixed: float, t0_fixed: float, f0: float) -> np.ndarray:
    """Residual with t_cb and t0 fixed, optimising the 8 remaining parameters."""
    theta = {}
    for i, k in enumerate(_PASS1_KEYS):
        theta[k] = float(v_reduced[i])
    theta["t_cb"] = t_cb_fixed
    theta["t0"]   = t0_fixed
    return dfig_phase_A(t, theta, f0) - ia


def _pass1_scan(t: np.ndarray, ia: np.ndarray, theta0: dict,
                bounds: list, t0: float, f0: float) -> tuple:
    """
    Scan t_cb grid and return (best_t_cb, best_v_full, best_cost).
    """
    lo_full, hi_full = _build_dfig_bounds(bounds)
    lo_p1 = lo_full[_PASS1_IDX]
    hi_p1 = hi_full[_PASS1_IDX]

    v0_full = theta_dfig_to_vector(theta0)
    v0_p1   = v0_full[_PASS1_IDX]
    v0_p1   = np.clip(v0_p1, lo_p1 + 1e-8, hi_p1 - 1e-8)

    best_cost = np.inf
    best_t_cb = _TCB_GRID[0]
    best_v    = v0_full.copy()

    for t_cb_cand in _TCB_GRID:
        try:
            res = least_squares(
                _pass1_residual, v0_p1,
                bounds=(lo_p1, hi_p1),
                args=(t, ia, t_cb_cand, t0, f0),
                method="trf", ftol=1e-6, xtol=1e-6, max_nfev=200,
            )
            cost = float(np.sum(res.fun ** 2))
            if cost < best_cost:
                best_cost = cost
                best_t_cb = t_cb_cand
                v_full    = best_v.copy()
                for i, k in enumerate(_PASS1_KEYS):
                    idx = THETA_KEYS_DFIG.index(k)
                    v_full[idx] = float(res.x[i])
                v_full[THETA_KEYS_DFIG.index("t_cb")] = t_cb_cand
                v_full[THETA_KEYS_DFIG.index("t0")]   = t0
                best_v = v_full
        except Exception:
            continue

    return best_t_cb, best_v, best_cost


# ---------------------------------------------------------------------------
# Pass-2 full LM
# ---------------------------------------------------------------------------

def _pass2_full(t: np.ndarray, ia: np.ndarray, v0: np.ndarray,
                bounds: list, f0: float) -> object:
    lo, hi = _build_dfig_bounds(bounds)
    v0 = np.clip(v0, lo + 1e-8, hi - 1e-8)
    return least_squares(
        dfig_residual, v0,
        bounds=(lo, hi),
        args=(t, ia, f0),
        method="trf", ftol=1e-8, xtol=1e-8, gtol=1e-8,
        max_nfev=1000, verbose=0,
    )


# ---------------------------------------------------------------------------
# Public estimator
# ---------------------------------------------------------------------------

def estimate_dfig_parameters(
    t: np.ndarray,
    ia: np.ndarray,
    theta0: Optional[dict] = None,
    bounds: Optional[list] = None,
    f0: float = 50.0,
    t_fault: Optional[float] = None,
    use_cusum: bool = True,
) -> dict:
    """
    Two-pass LM estimator for the 10-parameter DFIG model.

    Parameters
    ----------
    t        : time vector (event window)
    ia       : phase-A measured current (pu)
    theta0   : initial guess dict; defaults to DEFAULT_THETA_DFIG
    bounds   : list of (lo, hi) per parameter; defaults to DFIG_BOUNDS
    f0       : system frequency [Hz]
    t_fault  : fault inception time; used as t0 init and CUSUM baseline
    use_cusum: if True, attempt CUSUM crowbar detection to seed t_cb

    Returns
    -------
    dict:
        theta_hat      — dict of estimated parameters
        success        — bool
        cost           — scalar (sum of squared residuals)
        residual_norm  — sqrt(2 × cost)
        jacobian       — ndarray or None
        t_cb_hat       — estimated crowbar time (absolute, = t0 + t_cb)
        pass1_best     — (t_cb_grid_winner, pass1_cost)
        n_evaluations  — total function evaluations
    """
    if theta0 is None:
        theta0 = DEFAULT_THETA_DFIG.copy()
    if bounds is None:
        bounds = DFIG_BOUNDS

    t0_init = float(t_fault) if t_fault is not None else float(t[0])
    theta0  = {**theta0, "t0": t0_init}

    n_evals = 0

    # ── CUSUM crowbar time estimate ──────────────────────────────────────────
    t_cb_cusum = None
    if use_cusum and t_fault is not None:
        i_mag = np.abs(ia)
        t_cb_cusum = detect_crowbar_cusum(t, i_mag, t_fault, f0=f0)

    if t_cb_cusum is not None:
        # Use CUSUM result directly — skip t_cb grid scan
        t_cb_delay = max(0.005, t_cb_cusum - t0_init)
        theta0 = {**theta0, "t_cb": t_cb_delay}
        tcb_grid = [t_cb_delay]
    else:
        tcb_grid = None   # triggers full grid scan in pass 1

    # ── Pass 1: t_cb identification ──────────────────────────────────────────
    if tcb_grid is None:
        t_cb_star, v0_p2, pass1_cost = _pass1_scan(t, ia, theta0, bounds, t0_init, f0)
        n_evals += len(_TCB_GRID) * 200
    else:
        t_cb_star = tcb_grid[0]
        theta0["t_cb"] = t_cb_star
        v0_p2 = theta_dfig_to_vector(theta0)
        pass1_cost = float(np.sum((dfig_phase_A(t, theta0, f0) - ia) ** 2))

    # ── Pass 2: full refinement ───────────────────────────────────────────────
    try:
        res = _pass2_full(t, ia, v0_p2, bounds, f0)
        n_evals += res.nfev
        theta_hat = vector_to_theta_dfig(res.x)
        cost      = float(np.sum(res.fun ** 2))
        success   = bool(res.success) or res.cost < 1e3
        jac       = res.jac if hasattr(res, "jac") else None
        res_norm  = float(np.sqrt(2.0 * cost))
    except Exception as exc:
        theta_hat = vector_to_theta_dfig(v0_p2)
        cost      = pass1_cost
        success   = False
        jac       = None
        res_norm  = float(np.sqrt(2.0 * cost))

    t_cb_hat = theta_hat["t0"] + theta_hat["t_cb"]

    return {
        "theta_hat":     theta_hat,
        "success":       success,
        "cost":          cost,
        "residual_norm": res_norm,
        "jacobian":      jac,
        "t_cb_hat":      t_cb_hat,
        "pass1_best":    (t_cb_star, pass1_cost),
        "n_evaluations": n_evals,
    }
