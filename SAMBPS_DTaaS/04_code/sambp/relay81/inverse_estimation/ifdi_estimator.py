"""
ifdi_estimator.py
==================
SAMBP TR-63/2026 — Two-pass Levenberg-Marquardt estimator for the 6-parameter
GFM frequency-trajectory model driving the Relay 81 IFDI protection index.

Two-pass strategy
------------------
Pass 1 — Monotone kernel (3 free params: Δf_∞, τ_f, f₀_bias; A_osc = 0 fixed).
    Fits the exponential settling trajectory.  Robust to noise because the
    oscillatory term (which has the highest collinearity with the monotone term)
    is excluded.  This gives the primary IFDI trip decision.

Pass 2 — Full 6-param refinement (all params free).
    Activated only when the Pass-1 residual norm exceeds r_p2_trigger (default
    0.03 Hz), indicating significant inter-GFM oscillation.  Starting from
    Pass-1 results, LM frees A_osc, τ_osc, ω_osc to absorb the oscillatory
    residual.

This two-pass structure is identical in spirit to TR-56 (crowbar/post-crowbar
decomposition) and TR-62 (DDR-gated model selector).

Public API
----------
    IFDIEstimatorConfig   — tuning parameters
    estimate_ifdi         — main estimation function
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.optimize import least_squares
from dataclasses import dataclass, field
from typing import Optional

from models.gfm_frequency_model import (
    LOWER_BOUNDS, UPPER_BOUNDS, N_PARAMS, PARAM_NAMES,
    forward_df_gfm, jacobian_df_gfm,
    condition_number_gfm, initial_guess_gfm,
    interpret_theta_gfm, IFDIState,
)


# ---------------------------------------------------------------------------
# Estimator configuration
# ---------------------------------------------------------------------------

@dataclass
class IFDIEstimatorConfig:
    """Tuning parameters for the two-pass IFDI LM estimator."""
    # Pass-1 (monotone: Δf_∞, τ_f, f₀_bias)
    p1_free:        list[int] = field(default_factory=lambda: [0, 1, 5])
    ftol_p1:        float = 1e-9
    xtol_p1:        float = 1e-9
    gtol_p1:        float = 1e-9
    max_nfev_p1:    int   = 1000
    # Pass-2 trigger and config (full 6-param)
    r_p2_trigger:   float = 0.030   # Hz — residual norm above which Pass 2 fires
    ftol_p2:        float = 1e-9
    xtol_p2:        float = 1e-9
    gtol_p2:        float = 1e-9
    max_nfev_p2:    int   = 600
    # Multi-start τ_f values for Pass 1.
    # Two starting points (GFM-like and grid-like) prevent the LM from getting
    # trapped in the fast-τ_f local minimum when the true signal is a slow
    # grid transient.  The result with lower residual is kept.
    tau_f_starts:   list[float] = field(default_factory=lambda: [0.05, 1.0])



# ---------------------------------------------------------------------------
# Residual / Jacobian helpers
# ---------------------------------------------------------------------------

def _residual_full(theta, t, df_meas):
    return df_meas - forward_df_gfm(t, theta)


def _jac_full(theta, t, df_meas):
    return -jacobian_df_gfm(t, theta)


def _residual_p1(theta_free, t, df_meas, lb_f, ub_f, free_idx, fixed_vals, fixed_idx):
    theta = np.empty(N_PARAMS)
    theta[fixed_idx] = fixed_vals
    theta[free_idx]  = theta_free
    return df_meas - forward_df_gfm(t, theta)


def _jac_p1(theta_free, t, df_meas, lb_f, ub_f, free_idx, fixed_vals, fixed_idx):
    theta = np.empty(N_PARAMS)
    theta[fixed_idx] = fixed_vals
    theta[free_idx]  = theta_free
    return -jacobian_df_gfm(t, theta)[:, free_idx]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_ifdi(
    t_window:  np.ndarray,
    df_meas:   np.ndarray,
    fs:        float,
    cfg:       Optional[IFDIEstimatorConfig] = None,
) -> dict:
    """
    Two-pass LM estimator for the 6-parameter GFM frequency model.

    Parameters
    ----------
    t_window : (N,) time array [s], t[0] = 0 is event inception
    df_meas  : (N,) measured frequency deviation f_meas − f₀  [Hz]
    fs       : measurement sampling rate [Hz] (e.g. 100 for PMU 100 Hz output)
    cfg      : estimator configuration

    Returns
    -------
    dict with keys:
        theta_hat      : (6,) estimated parameters
        residual_norm  : scalar ‖r‖ / sqrt(N)  [Hz]
        kappa_n        : condition number
        pass2_fired    : bool — whether Pass 2 was triggered
        n_iter         : total function evaluations
        state          : IFDIState
        param_names    : list[str]
        model          : 'ifdi_gfm'
    """
    if cfg is None:
        cfg = IFDIEstimatorConfig()

    N = len(t_window)

    # ----- Pass 1: multi-start monotone kernel (Δf_∞, τ_f, f₀_bias free; A_osc=0 fixed) -----
    free_idx  = np.array(cfg.p1_free, dtype=int)
    fixed_idx = np.array([i for i in range(N_PARAMS) if i not in cfg.p1_free], dtype=int)
    lb_free   = LOWER_BOUNDS[free_idx]
    ub_free   = UPPER_BOUNDS[free_idx]

    best_res1  = None
    best_rn_p1 = float("inf")
    best_x0    = None
    n_iter     = 0

    for tau_f_0 in cfg.tau_f_starts:
        x0_try     = initial_guess_gfm(t_window, df_meas, tau_f_0=tau_f_0)
        fixed_vals = x0_try[fixed_idx]   # A_osc=0, τ_osc=0.20, ω_osc=4π fixed
        x0_free    = x0_try[free_idx]

        res_try = least_squares(
            _residual_p1,
            x0_free,
            jac=_jac_p1,
            bounds=(lb_free, ub_free),
            method="trf",
            ftol=cfg.ftol_p1, xtol=cfg.xtol_p1, gtol=cfg.gtol_p1,
            max_nfev=cfg.max_nfev_p1,
            args=(t_window, df_meas, lb_free, ub_free, free_idx, fixed_vals, fixed_idx),
        )
        n_iter += int(res_try.nfev)
        rn_try  = float(np.linalg.norm(res_try.fun) / max(np.sqrt(N), 1.0))
        if rn_try < best_rn_p1:
            best_rn_p1 = rn_try
            best_res1  = res_try
            best_x0    = x0_try

    # Reconstruct full θ from best Pass-1 result
    theta_p1 = best_x0.copy()
    theta_p1[free_idx] = best_res1.x

    rn_p1 = best_rn_p1

    # ----- Pass 2: full 6-param refinement (only if large residual) -----
    pass2_fired = False
    theta_hat   = theta_p1.copy()

    if rn_p1 > cfg.r_p2_trigger:
        pass2_fired = True
        res2 = least_squares(
            _residual_full,
            theta_p1,
            jac=_jac_full,
            bounds=(LOWER_BOUNDS, UPPER_BOUNDS),
            method="trf",
            ftol=cfg.ftol_p2, xtol=cfg.xtol_p2, gtol=cfg.gtol_p2,
            max_nfev=cfg.max_nfev_p2,
            args=(t_window, df_meas),
        )
        theta_hat = res2.x
        n_iter   += int(res2.nfev)

    # ----- Jacobian, condition number, residual at final θ -----
    J  = jacobian_df_gfm(t_window, theta_hat)
    kn = condition_number_gfm(J)
    r  = df_meas - forward_df_gfm(t_window, theta_hat)
    rn = float(np.linalg.norm(r) / max(np.sqrt(N), 1.0))

    state = interpret_theta_gfm(theta_hat, kn, rn)

    return {
        "theta_hat":     theta_hat,
        "residual_norm": rn,
        "kappa_n":       kn,
        "pass2_fired":   pass2_fired,
        "n_iter":        n_iter,
        "state":         state,
        "param_names":   PARAM_NAMES,
        "model":         "ifdi_gfm",
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    np.random.seed(42)
    fs  = 100.0
    N   = 50
    t   = np.arange(N) / fs

    # Test A: islanding detection (Δf_∞ = 0.25 Hz, τ_f = 0.04 s)
    theta_gt = np.array([0.25, 0.04, 0.0, 0.20, 4*np.pi, 0.003])
    df_gt    = forward_df_gfm(t, theta_gt)
    df_meas  = df_gt + 0.010 * np.random.randn(N)

    res = estimate_ifdi(t, df_meas, fs)
    st  = res["state"]
    print(f"[Islanding]  IFDI={st.ifdi:.3f}  is_islanded={st.is_islanded}  "
          f"Δf̂_∞={st.df_inf:.4f}Hz  τ̂_f={st.tau_f:.4f}s  "
          f"κ_n={st.kappa_n:.1f}  pass2={res['pass2_fired']}")
    assert st.is_islanded, "Should detect islanding"

    # Test B: external / grid-connected (Δf_∞ ≈ 0)
    theta_ext = np.array([0.0, 0.10, 0.0, 0.20, 4*np.pi, 0.001])
    df_ext    = forward_df_gfm(t, theta_ext) + 0.008 * np.random.randn(N)
    res_ext   = estimate_ifdi(t, df_ext, fs)
    st_ext    = res_ext["state"]
    print(f"[External]   IFDI={st_ext.ifdi:.3f}  is_islanded={st_ext.is_islanded}  "
          f"Δf̂_∞={st_ext.df_inf:.4f}Hz")
    assert not st_ext.is_islanded, "External must RESTRAIN"

    # Test C: slow grid transient (τ_f = 10 s → W_τ ≈ 0)
    theta_grid = np.array([-0.15, 10.0, 0.0, 0.20, 4*np.pi, 0.001])
    df_grid    = forward_df_gfm(t, theta_grid) + 0.008 * np.random.randn(N)
    res_grid   = estimate_ifdi(t, df_grid, fs)
    st_grid    = res_grid["state"]
    print(f"[Grid dip]   IFDI={st_grid.ifdi:.3f}  is_islanded={st_grid.is_islanded}  "
          f"τ̂_f={st_grid.tau_f:.2f}s  W_τ={st_grid.W_tau:.3f}")
    assert not st_grid.is_islanded, "Slow grid transient must RESTRAIN"

    # Test D: inter-GFM oscillation — Pass 2 fires
    theta_osc  = np.array([-0.20, 0.04, 0.08, 0.15, 4*np.pi, 0.001])
    df_osc     = forward_df_gfm(t, theta_osc) + 0.005 * np.random.randn(N)
    res_osc    = estimate_ifdi(t, df_osc, fs)
    st_osc     = res_osc["state"]
    print(f"[Oscillatory] IFDI={st_osc.ifdi:.3f}  is_islanded={st_osc.is_islanded}  "
          f"pass2={res_osc['pass2_fired']}  Â_osc={st_osc.A_osc:.4f}Hz")
    assert st_osc.is_islanded, "Oscillatory islanding should be detected"

    print("\nifdi_estimator self-test PASSED.")
