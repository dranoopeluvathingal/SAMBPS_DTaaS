# =============================================================================
# sambp / sambp_sync_oc
# inverse_estimation/parameter_estimator.py
#
# Run scipy.optimize.least_squares to estimate reduced source parameters.
#
# Public API
# ----------
# estimate_reduced_source_parameters(t_window, ia_meas, ib_meas, ic_meas,
#                                    initial_guess, bounds,
#                                    frequency_hz)
#   → dict {theta_hat, success, cost, residual_norm, jacobian}
#
# estimate_reduced_source_parameters_two_pass(t_window, ia_meas, ib_meas,
#                                    ic_meas, initial_guess, bounds,
#                                    frequency_hz, tail_cycles)
#   → dict — same keys as above, plus pass1_theta_hat
#   Pass 1: Phase-A fit of all 6 params on full window
#           → locks tau_dc, I_sub, phi_a, t0  (well-identified from transient)
#   Pass 2: Fix t0, phi_a, I_sub, tau_dc; refine I_ss + tau_ac on window tail
#           → removes I_ss/tau_ac collinearity with the decaying envelope
# =============================================================================

import numpy as np
from scipy.optimize import least_squares

from models.reduced_source_model import (
    reduced_sync_current_model,
    theta_to_vector,
    theta_from_vector,
    THETA_KEYS,
)
from inverse_estimation.objective_functions import residual_vector, residual_vector_phaseA


# ---------------------------------------------------------------------------
# Default parameter bounds aligned with SYSTEM_CONFIG / RELAY_CONFIG ranges
# ---------------------------------------------------------------------------
DEFAULT_BOUNDS = {
    # Physics constraints:
    #   I_sub > I_ss  — subtransient always larger (generator fault)
    #   tau_ac ≈ Td'' (0.01–0.15 s typical)
    #   tau_dc ≈ X''/(ωR) (0.02–0.15 s typical)
    # I_dc removed — derived from I_sub and phi_a inside the model
    "t0":     (0.0,    2.0),
    "I_ss":   (0.05,   5.0),
    "I_sub":  (0.5,    15.0),
    "tau_ac": (0.005,  1.0),   # Td' up to 1 s for large machines
    "tau_dc": (0.01,   0.5),   # X''/ωR — always > 10 ms physically
    "phi_a":  (-np.pi, np.pi),
}


def _build_bounds(bounds_dict):
    """
    Convert bounds dict {key: (lo, hi)} → two arrays ([lo,...], [hi,...])
    ordered by THETA_KEYS.
    """
    lo = [bounds_dict[k][0] for k in THETA_KEYS]
    hi = [bounds_dict[k][1] for k in THETA_KEYS]
    return (lo, hi)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_reduced_source_parameters(
    t_window,
    ia_meas,
    ib_meas,
    ic_meas,
    initial_guess,
    bounds=None,
    frequency_hz=50.0,
    model_fn=None,
    optimizer_kwargs=None,
    fit_phase="A",
):
    """
    Estimate reduced source parameters by minimising the waveform residual.

    Uses scipy.optimize.least_squares (Levenberg-Marquardt / trust-region
    reflective).

    fit_phase : "A" (default) — fit phase A only (avoids DC cross-cancellation
                across B/C phases which collapses tau_dc to its lower bound);
                "ABC" — fit all three phases simultaneously.

    Parameters
    ----------
    t_window      : ndarray — windowed time vector (s), from preprocessing
    ia_meas, ib_meas, ic_meas : ndarray — measured phase currents (pu)
    initial_guess : dict    — theta dict with starting values
    bounds        : dict or None — {key: (lo, hi)} per THETA_KEYS.
                    Defaults to DEFAULT_BOUNDS if None.
    frequency_hz  : float   — system frequency (Hz)
    model_fn      : callable or None — model function; defaults to
                    reduced_sync_current_model
    optimizer_kwargs : dict or None — extra kwargs forwarded to least_squares
                       e.g. {"method": "trf", "max_nfev": 500, "verbose": 0}

    Returns
    -------
    dict with keys:
        theta_hat      : dict    — estimated parameters (THETA_KEYS)
        success        : bool    — True if optimizer converged
        cost           : float   — final cost (0.5 · ‖r‖²)
        residual_norm  : float   — ‖r‖ at solution
        jacobian       : ndarray — Jacobian matrix at solution (or None)
        message        : str     — optimizer status message
        n_evaluations  : int     — number of function evaluations
    """
    t_window  = np.asarray(t_window,  dtype=float)
    ia_meas   = np.asarray(ia_meas,   dtype=float)
    ib_meas   = np.asarray(ib_meas,   dtype=float)
    ic_meas   = np.asarray(ic_meas,   dtype=float)

    if model_fn is None:
        model_fn = reduced_sync_current_model

    if bounds is None:
        bounds = DEFAULT_BOUNDS

    x0         = theta_to_vector(initial_guess)
    lo_hi      = _build_bounds(bounds)
    opt_kwargs = {"method": "trf", "max_nfev": 1000, "verbose": 0}
    if optimizer_kwargs:
        opt_kwargs.update(optimizer_kwargs)

    def _residual(theta_vec):
        if fit_phase == "A":
            return residual_vector_phaseA(
                theta_vec, t_window, ia_meas, model_fn, frequency_hz,
            )
        else:
            return residual_vector(
                theta_vec, t_window,
                ia_meas, ib_meas, ic_meas,
                model_fn, frequency_hz,
            )

    result = least_squares(
        _residual,
        x0,
        bounds=lo_hi,
        **opt_kwargs,
    )

    theta_hat     = theta_from_vector(result.x)
    residual_norm = float(np.linalg.norm(result.fun))

    return {
        "theta_hat":     theta_hat,
        "success":       bool(result.success),
        "cost":          float(result.cost),
        "residual_norm": residual_norm,
        "jacobian":      result.jac if hasattr(result, "jac") else None,
        "message":       result.message,
        "n_evaluations": result.nfev,
    }


# ---------------------------------------------------------------------------
# Two-pass estimator
# ---------------------------------------------------------------------------

def estimate_reduced_source_parameters_two_pass(
    t_window,
    ia_meas,
    ib_meas,
    ic_meas,
    initial_guess,
    bounds=None,
    frequency_hz=50.0,
    model_fn=None,
    tail_cycles=2,
):
    """
    Two-pass inverse estimator that separates the identification of transient
    parameters (I_sub, tau_dc, phi_a, t0) from the steady-state parameters
    (I_ss, tau_ac).

    The single-pass phase-A fit correctly recovers the fast transient parameters
    but leaves I_ss high (≈ 1.9 pu vs physical 0.51 pu) because the decaying
    AC envelope in the 145 ms fault window is partially absorbed into I_ss.

    Two-pass strategy
    -----------------
    Pass 1 — Full window, all 6 params, phase-A fit (identical to single-pass):
        → Reliable: t0, phi_a, I_sub, tau_dc   (driven by the early transient)
        → Unreliable: I_ss, tau_ac             (decaying tail is too short to
                                                 cleanly resolve steady-state)

    Pass 2 — Tail window (last `tail_cycles` cycles of fault window), phase-A fit:
        → Fixed:  t0, phi_a, I_sub, tau_dc     (from pass 1)
        → Free:   I_ss, tau_ac                 (2-param problem, well-conditioned
                                                 because AC envelope ≈ I_ss here)

    Parameters
    ----------
    t_window, ia_meas, ib_meas, ic_meas : ndarray — full fault window
    initial_guess : dict    — theta dict with starting values
    bounds        : dict or None — per DEFAULT_BOUNDS
    frequency_hz  : float   — system frequency (Hz)
    model_fn      : callable or None
    tail_cycles   : int     — number of AC cycles at the end of the window to
                              use for pass 2 (default 2, ≈ 40 ms at 50 Hz)

    Returns
    -------
    dict — same keys as estimate_reduced_source_parameters, plus:
        pass1_theta_hat : dict — raw pass-1 result (for diagnostics)
        n_evaluations   : int  — total across both passes
    """
    t_window = np.asarray(t_window, dtype=float)
    ia_meas  = np.asarray(ia_meas,  dtype=float)
    ib_meas  = np.asarray(ib_meas,  dtype=float)
    ic_meas  = np.asarray(ic_meas,  dtype=float)

    if model_fn is None:
        model_fn = reduced_sync_current_model
    if bounds is None:
        bounds = DEFAULT_BOUNDS

    # ------------------------------------------------------------------
    # Pass 1 — identical to single-pass phase-A fit
    # ------------------------------------------------------------------
    est1 = estimate_reduced_source_parameters(
        t_window      = t_window,
        ia_meas       = ia_meas,
        ib_meas       = ib_meas,
        ic_meas       = ic_meas,
        initial_guess = initial_guess,
        bounds        = bounds,
        frequency_hz  = frequency_hz,
        model_fn      = model_fn,
        fit_phase     = "A",
    )
    theta1 = est1["theta_hat"]
    total_nfev = est1["n_evaluations"]

    # ------------------------------------------------------------------
    # Pass 2 — tail window, 2 free params: I_ss, tau_ac
    # ------------------------------------------------------------------
    dt             = float(t_window[1] - t_window[0])
    n_per_cycle    = max(1, int(round(1.0 / (frequency_hz * dt))))
    n_tail         = tail_cycles * n_per_cycle

    # Need at least one full pass-2 window; fall back to pass-1 result if too short
    if len(t_window) <= n_tail + n_per_cycle:
        return {
            **est1,
            "pass1_theta_hat": theta1,
        }

    t_tail  = t_window[-n_tail:]
    ia_tail = ia_meas[-n_tail:]

    # Build a residual that freezes t0, phi_a, I_sub, tau_dc and only
    # exposes [I_ss, tau_ac] to the optimiser via a closure.
    fixed = {k: theta1[k] for k in ("t0", "phi_a", "I_sub", "tau_dc")}
    FREE_KEYS = ["I_ss", "tau_ac"]

    def _residual_pass2(x2):
        theta_p2 = {
            **fixed,
            "I_ss":   x2[0],
            "tau_ac": x2[1],
        }
        from models.reduced_source_model import theta_to_vector
        theta_vec = theta_to_vector(theta_p2)
        return residual_vector_phaseA(
            theta_vec, t_tail, ia_tail, model_fn, frequency_hz,
        )

    x2_0  = np.array([theta1["I_ss"],   theta1["tau_ac"]])
    lo2   = np.array([bounds["I_ss"][0], bounds["tau_ac"][0]])
    hi2   = np.array([bounds["I_ss"][1], bounds["tau_ac"][1]])

    result2 = least_squares(
        _residual_pass2,
        x2_0,
        bounds=(lo2, hi2),
        method="trf",
        max_nfev=500,
        verbose=0,
    )
    total_nfev += result2.nfev

    # Merge: pass-1 transient params + pass-2 steady-state params
    theta_hat = {
        **theta1,
        "I_ss":   float(result2.x[0]),
        "tau_ac": float(result2.x[1]),
    }

    # Recompute full residual with merged theta for reporting
    from models.reduced_source_model import theta_to_vector
    theta_vec_final = theta_to_vector(theta_hat)
    r_final = residual_vector_phaseA(
        theta_vec_final, t_window, ia_meas, model_fn, frequency_hz,
    )
    residual_norm = float(np.linalg.norm(r_final))
    cost          = 0.5 * float(np.dot(r_final, r_final))

    return {
        "theta_hat":      theta_hat,
        "success":        bool(result2.success),
        "cost":           cost,
        "residual_norm":  residual_norm,
        "jacobian":       est1["jacobian"],   # from pass 1 (6×6 for sensitivity)
        "message":        result2.message,
        "n_evaluations":  total_nfev,
        "pass1_theta_hat": theta1,
    }
