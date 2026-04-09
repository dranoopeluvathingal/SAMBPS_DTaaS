"""
dfig_estimator.py
==================
SAMBP TR-56/2026 — Two-pass Levenberg-Marquardt estimator for the 10-parameter
DFIG differential current model (87L/87G protection).

Two-pass strategy
-----------------
Pass 1 — Full window, all 10 parameters.
    Estimates k_ibr, phi_pre, t_cb, I_fund, phi_fund, I_nat, phi_nat,
    omega_slip, tau_s, I_DC simultaneously using the CUSUM crowbar time
    estimate as the initial t_cb.

Pass 2 — Post-crowbar tail window, free: omega_slip, tau_s.
    The tail window (final tail_cycles of data) contains mostly the decaying
    natural response and DC offset.  Refining omega_slip and tau_s in the
    tail, with all amplitude and phase parameters fixed from Pass 1, improves
    identifiability of the slow-varying decay parameters.

Public API
----------
    estimate_dfig_parameters(t, i_diff, fs, cfg) → dict
    CUSUMResult passthrough via detect_crowbar() helper
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.optimize import least_squares
from dataclasses import dataclass
from typing import Optional

from models.dfig_current_model import (
    LOWER_BOUNDS, UPPER_BOUNDS, N_PARAMS, PARAM_NAMES,
    forward_idiff_dfig, jacobian_idiff_dfig,
    condition_number_dfig, initial_guess_dfig,
    interpret_theta_dfig, DFIGZoneState,
)
from detection.crowbar_cusum import (
    CUSUMConfig, CUSUMResult, run_crowbar_detection,
)


# ---------------------------------------------------------------------------
# Estimator configuration
# ---------------------------------------------------------------------------

@dataclass
class DFIGEstimatorConfig:
    """Tuning parameters for the two-pass DFIG LM estimator."""
    freq_hz:            float = 50.0
    # Pass-1 convergence
    ftol_p1:            float = 1e-8
    xtol_p1:            float = 1e-8
    gtol_p1:            float = 1e-8
    max_nfev_p1:        int   = 2000
    # Pass-2 tail refinement
    tail_cycles:        float = 3.0    # tail window for omega_slip / tau_s
    ftol_p2:            float = 1e-9
    xtol_p2:            float = 1e-9
    gtol_p2:            float = 1e-9
    max_nfev_p2:        int   = 600
    # Interpretation thresholds
    kappa_max:          float = 80.0   # max acceptable condition number
    I_fund_fault_thresh:float = 0.10   # min |I_fund| for fault declaration [pu]
    f_int_thresh:       float = 0.35   # min zone confidence for TRIP
    # CUSUM
    cusum_cfg:          Optional[CUSUMConfig] = None


# ---------------------------------------------------------------------------
# Residual  r(θ) = i_diff_meas − i_model(t, θ)
# ---------------------------------------------------------------------------

def _residual(theta, t, i_meas, freq_hz):
    return i_meas - forward_idiff_dfig(t, theta, freq_hz)


def _jac(theta, t, i_meas, freq_hz):
    return -jacobian_idiff_dfig(t, theta, freq_hz)


# ---------------------------------------------------------------------------
# Pass-1 helper
# ---------------------------------------------------------------------------

def _pass1(t, i_meas, x0, cfg: DFIGEstimatorConfig):
    return least_squares(
        _residual,
        x0,
        jac=_jac,
        bounds=(LOWER_BOUNDS, UPPER_BOUNDS),
        method="trf",
        ftol=cfg.ftol_p1, xtol=cfg.xtol_p1, gtol=cfg.gtol_p1,
        max_nfev=cfg.max_nfev_p1,
        args=(t, i_meas, cfg.freq_hz),
    )


# ---------------------------------------------------------------------------
# Pass-2: refine omega_slip and tau_s in the post-crowbar tail
# ---------------------------------------------------------------------------

# Indices of free / fixed parameters in the 10-param vector
_P2_FREE  = [7, 8]         # omega_slip, tau_s
_P2_FIXED = [0,1,2,3,4,5,6,9]  # all others


def _residual_p2(theta_free, t, i_meas, theta_fixed_values, fixed_idx, free_idx, freq_hz):
    theta_full = np.empty(N_PARAMS)
    theta_full[fixed_idx] = theta_fixed_values
    theta_full[free_idx]  = theta_free
    return i_meas - forward_idiff_dfig(t, theta_full, freq_hz)


def _jac_p2(theta_free, t, i_meas, theta_fixed_values, fixed_idx, free_idx, freq_hz):
    theta_full = np.empty(N_PARAMS)
    theta_full[fixed_idx] = theta_fixed_values
    theta_full[free_idx]  = theta_free
    return -jacobian_idiff_dfig(t, theta_full, freq_hz)[:, free_idx]


def _pass2(t_tail, i_tail, theta_p1, cfg: DFIGEstimatorConfig):
    """Refine omega_slip and tau_s on the post-crowbar tail."""
    x0_free       = theta_p1[_P2_FREE]
    lb_free       = LOWER_BOUNDS[_P2_FREE]
    ub_free       = UPPER_BOUNDS[_P2_FREE]
    theta_fixed   = theta_p1[_P2_FIXED]

    return least_squares(
        _residual_p2,
        x0_free,
        jac=_jac_p2,
        bounds=(lb_free, ub_free),
        method="trf",
        ftol=cfg.ftol_p2, xtol=cfg.xtol_p2, gtol=cfg.gtol_p2,
        max_nfev=cfg.max_nfev_p2,
        args=(t_tail, i_tail, theta_fixed, _P2_FIXED, _P2_FREE, cfg.freq_hz),
    )


# ---------------------------------------------------------------------------
# CUSUM crowbar detection helper
# ---------------------------------------------------------------------------

def detect_crowbar(
    i_diff: np.ndarray,
    fs:     float,
    t0:     float = 0.0,
    cusum_cfg: Optional[CUSUMConfig] = None,
) -> CUSUMResult:
    """Run CUSUM crowbar detector. Thin wrapper for convenience."""
    return run_crowbar_detection(i_diff, fs, cusum_cfg, t0=t0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_dfig_parameters(
    t_window:    np.ndarray,
    i_diff_meas: np.ndarray,
    fs:          float,
    cfg:         Optional[DFIGEstimatorConfig] = None,
    t_cb_hint:   Optional[float] = None,
    run_cusum:   bool = True,
) -> dict:
    """
    Two-pass LM estimator for the 10-parameter DFIG differential current model.

    Parameters
    ----------
    t_window    : (N,) time array [s]
    i_diff_meas : (N,) measured differential current [pu]
    fs          : sampling rate [Hz]
    cfg         : estimator configuration (None → defaults)
    t_cb_hint   : crowbar time hint [s] (None → use CUSUM estimate or mid-window)
    run_cusum   : if True, run CUSUM before LM to obtain t_cb_hint if not provided

    Returns
    -------
    dict with keys:
        theta_hat     : (10,) estimated parameters
        residual_norm : scalar residual ||r|| / sqrt(N)
        jacobian      : (N, 10) Jacobian at theta_hat
        kappa_n       : condition number (normalised)
        success       : bool
        n_iter        : total function evaluations (pass1 + pass2)
        state         : DFIGZoneState
        param_names   : list of parameter names
        cusum_result  : CUSUMResult (or None if run_cusum=False)
        model         : 'dfig'
    """
    if cfg is None:
        cfg = DFIGEstimatorConfig()

    N  = len(t_window)
    dt = float(t_window[1] - t_window[0]) if N > 1 else 1.0 / fs

    # Step 1: CUSUM crowbar detection (if requested and no hint provided)
    cusum_result: Optional[CUSUMResult] = None
    if run_cusum and t_cb_hint is None:
        cusum_result = run_crowbar_detection(i_diff_meas, fs, cfg.cusum_cfg,
                                             t0=float(t_window[0]))
        if cusum_result.alarm and cusum_result.t_cb_est is not None:
            t_cb_hint = cusum_result.t_cb_est

    # Fallback: if CUSUM didn't fire, use mid-window as hint
    if t_cb_hint is None:
        t_cb_hint = float(t_window[N // 2])

    # Step 2: physics-based initial guess using t_cb_hint
    x0 = initial_guess_dfig(t_window, i_diff_meas, cfg.freq_hz,
                            t_cb_est=t_cb_hint)

    # Step 3: Pass 1 — all 10 parameters, full window
    res1     = _pass1(t_window, i_diff_meas, x0, cfg)
    theta_p1 = res1.x

    # Step 4: Pass 2 — omega_slip and tau_s, post-crowbar tail window
    spc    = int(round(fs / cfg.freq_hz))
    n_tail = max(int(round(cfg.tail_cycles * spc)), 10)
    n_tail = min(n_tail, N)
    # Tail starts after estimated crowbar time
    t_cb_est = float(theta_p1[2])
    k_cb     = np.searchsorted(t_window, t_cb_est)
    k_tail   = max(k_cb, N - n_tail)
    t_tail   = t_window[k_tail:]
    i_tail   = i_diff_meas[k_tail:]

    theta_hat = theta_p1.copy()
    if len(t_tail) >= 10:
        res2                  = _pass2(t_tail, i_tail, theta_p1, cfg)
        theta_hat[_P2_FREE]   = res2.x
        n_iter_total          = int(res1.nfev + res2.nfev)
        success               = bool(res1.success or res2.success)
    else:
        n_iter_total = int(res1.nfev)
        success      = bool(res1.success)

    # Step 5: evaluate Jacobian and condition number at final theta
    J  = jacobian_idiff_dfig(t_window, theta_hat, cfg.freq_hz)
    kn = condition_number_dfig(J)

    # Residual
    r  = _residual(theta_hat, t_window, i_diff_meas, cfg.freq_hz)
    rn = float(np.linalg.norm(r) / max(np.sqrt(N), 1.0))

    # Interpretation
    state = interpret_theta_dfig(
        theta_hat, kn, rn,
        I_fund_thresh = cfg.I_fund_fault_thresh,
        kappa_max     = cfg.kappa_max,
        freq_hz       = cfg.freq_hz,
    )

    return {
        "theta_hat":     theta_hat,
        "residual_norm": rn,
        "jacobian":      J,
        "kappa_n":       kn,
        "success":       success,
        "n_iter":        n_iter_total,
        "state":         state,
        "param_names":   PARAM_NAMES,
        "cusum_result":  cusum_result,
        "model":         "dfig",
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    freq = 50.0
    fs   = 1000.0
    np.random.seed(0)

    # Ground-truth: crowbar at t=0.10s, 12% slip
    s_gt    = 0.12
    t_cb_gt = 0.10
    theta_gt = np.array([
        1.00,                          # k_ibr
        -0.30,                         # phi_pre
        t_cb_gt,                       # t_cb
        0.70,                          # I_fund
        -0.20,                         # phi_fund
        0.40,                          # I_nat
        0.50,                          # phi_nat
        s_gt * 2 * np.pi * freq,       # omega_slip
        0.08,                          # tau_s
        0.20,                          # I_DC
    ])

    t = np.arange(0, 0.30, 1.0 / fs)
    i_gt   = forward_idiff_dfig(t, theta_gt, freq)
    i_meas = i_gt + 0.005 * np.random.randn(len(t))

    cfg = DFIGEstimatorConfig(freq_hz=freq)

    result = estimate_dfig_parameters(t, i_meas, fs, cfg=cfg, run_cusum=True)

    theta_hat = result["theta_hat"]
    state     = result["state"]
    cusum     = result["cusum_result"]

    print(f"[CUSUM]   alarm={cusum.alarm}  "
          f"t_cb_cusum={cusum.t_cb_est:.3f}s  (true={t_cb_gt:.3f}s)")
    print(f"[Pass1+2] nfev={result['n_iter']}  "
          f"kappa_n={result['kappa_n']:.1f}  "
          f"residual={result['residual_norm']:.4f}")
    print(f"[theta]  true: {np.round(theta_gt, 3)}")
    print(f"         est:  {np.round(theta_hat, 3)}")

    err_tcb = abs(theta_hat[2] - t_cb_gt)
    err_slip = abs(theta_hat[7] - theta_gt[7])
    err_tau  = abs(theta_hat[8] - theta_gt[8])
    print(f"[Error]  t_cb={err_tcb*1000:.1f}ms  "
          f"omega_slip={err_slip:.3f}rad/s  "
          f"tau_s={err_tau*1000:.1f}ms")

    print(f"[State]  slip={state.slip:.3f}  "
          f"crowbar_fired={state.crowbar_fired}  "
          f"is_internal={state.is_internal}")

    assert cusum.alarm, "CUSUM must detect crowbar"
    assert state.crowbar_fired, "State must flag crowbar fired"
    assert err_tcb < 0.025, f"t_cb error {err_tcb*1000:.0f}ms > 25ms"
    assert err_slip < 10.0, f"omega_slip error {err_slip:.2f} rad/s > 10 rad/s"

    # Test B: healthy DFIG (no crowbar, small load current, no slip-freq component)
    # I_nat=0, I_DC=0, I_fund=0.05 (below fault threshold)
    theta_nocb = np.array([0.05, 0.10, 0.25, 0.05, 0.10, 0.0, 0.0, 30.0, 0.08, 0.0])
    i_nocb = forward_idiff_dfig(t, theta_nocb, freq) + 0.003*np.random.randn(len(t))
    res_nocb = estimate_dfig_parameters(t, i_nocb, fs, cfg=cfg, run_cusum=True)
    print(f"[No-CB]  cusum_alarm={res_nocb['cusum_result'].alarm}  "
          f"crowbar_fired={res_nocb['state'].crowbar_fired}  "
          f"is_internal={res_nocb['state'].is_internal}")
    assert not res_nocb["cusum_result"].alarm, "Healthy DFIG must NOT trigger CUSUM"
    assert not res_nocb["state"].is_internal, "Healthy DFIG must NOT flag internal fault"

    print("\ndfig_estimator self-test PASSED.")
