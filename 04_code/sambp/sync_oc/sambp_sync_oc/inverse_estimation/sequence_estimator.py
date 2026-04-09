# =============================================================================
# sambp / sambp_sync_oc
# inverse_estimation/sequence_estimator.py
#
# Sequence-component inverse estimator for asymmetric fault types.
#
# For balanced three-phase (3PH) faults the existing phase-A two-pass estimator
# is sufficient.  For asymmetric faults (LL, SLG) the phase-A signal contains
# a mixture of positive-, negative-, and zero-sequence contributions that the
# single-phase model cannot cleanly separate.
#
# This module decomposes ia, ib, ic into symmetrical sequence components using
# the instantaneous Hilbert-Fortescue transform (from signal_processing/
# sequence_components.py) and then fits the reduced 6-parameter model
# independently to each active sequence signal.
#
# Sequence activity by fault type
# --------------------------------
#   3PH  : I1 non-zero, I2 ≈ 0, I0 ≈ 0  → phase-A estimator (no change)
#   LL   : I1 non-zero, I2 non-zero, I0 ≈ 0
#   SLG  : I1 = I2 = I0  → estimate I1 only, propagate to I2, I0
#   LLG  : I1, I2, I0 all non-zero  (treated same as LL for Stage 1)
#
# The positive-sequence theta_hat is the primary output used for relay
# adaptation (it represents the fault current seen in the protected zone).
#
# Public API
# ----------
# estimate_sequence_parameters(t_window, ia_meas, ib_meas, ic_meas,
#                              fault_type, initial_guess, bounds,
#                              frequency_hz, model_fn, tail_cycles)
#   → dict {
#       "theta_pos"  : dict  — positive-sequence 6-param theta (for adaptation)
#       "theta_neg"  : dict or None
#       "theta_zero" : dict or None
#       "residual_norm_total" : float
#       "jacobian"   : ndarray  — Jacobian from positive-sequence fit
#       "success"    : bool
#       "seq_signals": dict {"I1", "I2", "I0"}  — decomposed waveforms
#       "pass1_theta_hat": dict  — diagnostics from positive-sequence pass 1
#     }
# =============================================================================

import numpy as np

from signal_processing.sequence_components import symmetrical_components
from inverse_estimation.parameter_estimator import (
    estimate_reduced_source_parameters_two_pass,
    DEFAULT_BOUNDS,
)
from models.reduced_source_model import DEFAULT_THETA


# ---------------------------------------------------------------------------
# Symmetry check threshold: if |I2|_rms / |I1|_rms < this, skip I2 fit
# ---------------------------------------------------------------------------
_SEQ_THRESHOLD = 0.05


def _rms(arr):
    """Root-mean-square of a 1-D array."""
    return float(np.sqrt(np.mean(np.asarray(arr, dtype=float) ** 2)))


def _seq_initial_guess(theta_pos, sequence):
    """
    Build a physically motivated initial guess for negative- or zero-sequence
    fit, seeded from the positive-sequence solution.

    Negative sequence: reactances differ → I_sub smaller, tau_ac shorter.
    Zero sequence:     grounding impedance dominates → smaller currents.
    """
    g = {k: v for k, v in theta_pos.items()}

    if sequence == "neg":
        g["I_ss"]   = theta_pos["I_ss"]  * 0.6
        g["I_sub"]  = theta_pos["I_sub"] * 0.7
        g["tau_ac"] = theta_pos["tau_ac"] * 0.5
        g["tau_dc"] = theta_pos["tau_dc"] * 0.8
        # Negative sequence angle lags by ≈π/6 (typical for SLG faults)
        g["phi_a"]  = theta_pos["phi_a"] - np.pi / 6.0

    elif sequence == "zero":
        g["I_ss"]   = theta_pos["I_ss"]  * 0.3
        g["I_sub"]  = theta_pos["I_sub"] * 0.35
        g["tau_ac"] = theta_pos["tau_ac"] * 0.7
        g["tau_dc"] = theta_pos["tau_dc"] * 1.2   # zero-seq tau_dc can be longer

    return g


def estimate_sequence_parameters(
    t_window,
    ia_meas,
    ib_meas,
    ic_meas,
    fault_type,
    initial_guess=None,
    bounds=None,
    frequency_hz=50.0,
    model_fn=None,
    tail_cycles=2,
):
    """
    Estimate reduced source parameters from sequence-component waveforms.

    For 3PH faults this function is equivalent to running the two-pass
    phase-A estimator directly on ia_meas.  For asymmetric faults it first
    decomposes ia/ib/ic into symmetrical components and fits each active
    sequence independently.

    Parameters
    ----------
    t_window               : ndarray — windowed time vector (s)
    ia_meas, ib_meas, ic_meas : ndarray — measured phase currents (pu)
    fault_type             : str    — "3PH" | "LL" | "SLG" | "LLG"
    initial_guess          : dict or None — seeds positive-sequence fit
    bounds                 : dict or None — per DEFAULT_BOUNDS
    frequency_hz           : float  — system frequency (Hz)
    model_fn               : callable or None
    tail_cycles            : int    — passed to two-pass estimator

    Returns
    -------
    dict with keys:
        theta_pos            : dict — positive-sequence theta_hat
        theta_neg            : dict or None
        theta_zero           : dict or None
        residual_norm_total  : float — combined ‖r‖ across active sequences
        jacobian             : ndarray — Jacobian from positive-sequence fit
        success              : bool
        seq_signals          : dict {"I1", "I2", "I0"}
        pass1_theta_hat      : dict — diagnostics
    """
    t_window  = np.asarray(t_window,  dtype=float)
    ia_meas   = np.asarray(ia_meas,   dtype=float)
    ib_meas   = np.asarray(ib_meas,   dtype=float)
    ic_meas   = np.asarray(ic_meas,   dtype=float)

    if initial_guess is None:
        initial_guess = {**DEFAULT_THETA, "t0": float(t_window[0])}
    if bounds is None:
        bounds = DEFAULT_BOUNDS

    # ------------------------------------------------------------------
    # Decompose into symmetrical sequence components
    # ------------------------------------------------------------------
    seq = symmetrical_components(ia_meas, ib_meas, ic_meas,
                                  domain="instantaneous")
    I1 = seq["I1"]   # positive sequence (real, time domain)
    I2 = seq["I2"]   # negative sequence
    I0 = seq["I0"]   # zero sequence

    # For 3PH: use phase A directly (avoids Hilbert edge effects on
    # a perfectly balanced signal where sequence decomposition is redundant)
    if fault_type == "3PH":
        I1 = ia_meas

    # ------------------------------------------------------------------
    # Decide which sequences to fit
    # ------------------------------------------------------------------
    rms_I1 = _rms(I1)
    rms_I2 = _rms(I2)
    rms_I0 = _rms(I0)

    fit_neg  = False
    fit_zero = False

    if fault_type == "LL":
        fit_neg  = (rms_I1 > 1e-6) and (rms_I2 / (rms_I1 + 1e-12) > _SEQ_THRESHOLD)
        fit_zero = False   # I0 ≈ 0 for LL

    elif fault_type == "SLG":
        # For SLG: I1 = I2 = I0 by sequence theory — fit I1 only, propagate
        fit_neg  = False
        fit_zero = False

    elif fault_type == "LLG":
        fit_neg  = (rms_I2 / (rms_I1 + 1e-12) > _SEQ_THRESHOLD)
        fit_zero = (rms_I0 / (rms_I1 + 1e-12) > _SEQ_THRESHOLD)

    elif fault_type == "3PH":
        # Balanced: skip I2, I0 entirely
        fit_neg  = False
        fit_zero = False

    # ------------------------------------------------------------------
    # Pass 1 & 2: Positive-sequence fit
    # ------------------------------------------------------------------
    # The two-pass estimator expects ia_meas, ib_meas, ic_meas but uses
    # only phase A internally (fit_phase="A").  Feed I1 as ia and zeros
    # for ib, ic so the API is satisfied.
    zeros = np.zeros_like(I1)

    est_pos = estimate_reduced_source_parameters_two_pass(
        t_window      = t_window,
        ia_meas       = I1,
        ib_meas       = zeros,
        ic_meas       = zeros,
        initial_guess = initial_guess,
        bounds        = bounds,
        frequency_hz  = frequency_hz,
        model_fn      = model_fn,
        tail_cycles   = tail_cycles,
    )
    theta_pos    = est_pos["theta_hat"]
    residual_tot = est_pos["residual_norm"]
    jac_pos      = est_pos.get("jacobian")
    success      = est_pos["success"]

    # ------------------------------------------------------------------
    # Negative-sequence fit (if applicable)
    # ------------------------------------------------------------------
    theta_neg = None
    if fit_neg:
        guess_neg = _seq_initial_guess(theta_pos, "neg")
        try:
            est_neg = estimate_reduced_source_parameters_two_pass(
                t_window      = t_window,
                ia_meas       = I2,
                ib_meas       = zeros,
                ic_meas       = zeros,
                initial_guess = guess_neg,
                bounds        = bounds,
                frequency_hz  = frequency_hz,
                model_fn      = model_fn,
                tail_cycles   = tail_cycles,
            )
            theta_neg    = est_neg["theta_hat"]
            residual_tot += est_neg["residual_norm"]
            if not est_neg["success"]:
                success = False
        except Exception:
            theta_neg = None   # fit failed — proceed with positive-seq only

    # ------------------------------------------------------------------
    # Zero-sequence fit (if applicable)
    # ------------------------------------------------------------------
    theta_zero = None
    if fit_zero:
        guess_zero = _seq_initial_guess(theta_pos, "zero")
        try:
            est_zero = estimate_reduced_source_parameters_two_pass(
                t_window      = t_window,
                ia_meas       = I0,
                ib_meas       = zeros,
                ic_meas       = zeros,
                initial_guess = guess_zero,
                bounds        = bounds,
                frequency_hz  = frequency_hz,
                model_fn      = model_fn,
                tail_cycles   = tail_cycles,
            )
            theta_zero    = est_zero["theta_hat"]
            residual_tot += est_zero["residual_norm"]
            if not est_zero["success"]:
                success = False
        except Exception:
            theta_zero = None

    # ------------------------------------------------------------------
    # For SLG: propagate positive-sequence result to I2 and I0
    # (by sequence network theory I1 = I2 = I0 for SLG with Zf=0)
    # ------------------------------------------------------------------
    if fault_type == "SLG":
        theta_neg  = {k: v for k, v in theta_pos.items()}
        theta_zero = {k: v for k, v in theta_pos.items()}

    return {
        "theta_pos":           theta_pos,
        "theta_neg":           theta_neg,
        "theta_zero":          theta_zero,
        "residual_norm_total": float(residual_tot),
        "jacobian":            jac_pos,
        "success":             success,
        "seq_signals":         {"I1": I1, "I2": I2, "I0": I0},
        "pass1_theta_hat":     est_pos.get("pass1_theta_hat"),
        "n_evaluations":       est_pos.get("n_evaluations", 0),
    }
