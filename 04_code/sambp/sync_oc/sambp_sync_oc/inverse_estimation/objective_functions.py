# =============================================================================
# sambp / sambp_sync_oc
# inverse_estimation/objective_functions.py
#
# Relay-oriented inverse estimation objectives.
#
# Total objective (Stage 1):
#
#   J(θ) = w1·Σ(i_meas − i_model)²
#         + w2·Σ(I_rms_meas − I_rms_model)²
#         + w3·|θ − θ_prior|²
#
# Public API
# ----------
# waveform_mismatch_objective(theta_vec, t, ia_meas, ib_meas, ic_meas,
#                             model_fn)                        → float
# relay_quantity_objective(theta_vec, t, i_rms_meas, model_fn,
#                          frequency_hz, samples_per_cycle)    → float  (stub)
# total_inverse_objective(theta_vec, t, ia_meas, ib_meas, ic_meas,
#                         i_rms_meas, model_fn, theta_prior_vec,
#                         weights, frequency_hz)               → float
# residual_vector(theta_vec, t, ia_meas, ib_meas, ic_meas, model_fn)
#                                                              → ndarray
# =============================================================================

import numpy as np
from signal_processing.rms_tools import sliding_rms


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _model_currents(theta_vec, t, model_fn, frequency_hz):
    """Call model_fn with theta dict and return (ia, ib, ic) arrays."""
    from models.reduced_source_model import theta_from_vector
    theta = theta_from_vector(theta_vec)
    out   = model_fn(t, theta, frequency_hz=frequency_hz)
    return out["ia"], out["ib"], out["ic"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def waveform_mismatch_objective(
    theta_vec,
    t,
    ia_meas,
    ib_meas,
    ic_meas,
    model_fn,
    frequency_hz=50.0,
):
    """
    Scalar least-squares waveform mismatch objective.

    J1(θ) = Σ_phases Σ_t (i_meas(t) − i_model(t, θ))²

    Parameters
    ----------
    theta_vec  : ndarray  — flat parameter vector (ordered by THETA_KEYS)
    t          : ndarray  — time vector (s), windowed to event
    ia_meas, ib_meas, ic_meas : ndarray — measured phase currents (pu)
    model_fn   : callable — reduced_sync_current_model or compatible
    frequency_hz: float

    Returns
    -------
    float — scalar objective value
    """
    ia_m, ib_m, ic_m = _model_currents(theta_vec, t, model_fn, frequency_hz)

    J = (np.sum((ia_meas - ia_m) ** 2) +
         np.sum((ib_meas - ib_m) ** 2) +
         np.sum((ic_meas - ic_m) ** 2))
    return float(J)


def relay_quantity_objective(
    theta_vec,
    t,
    i_rms_meas,
    model_fn,
    frequency_hz=50.0,
    samples_per_cycle=None,
):
    """
    Mismatch in RMS current between measured and model.

    J2(θ) = Σ_t (I_rms_meas(t) − I_rms_model(t, θ))²

    Parameters
    ----------
    theta_vec       : ndarray  — flat parameter vector
    t               : ndarray  — time vector (s)
    i_rms_meas      : ndarray  — measured RMS current (pu)
    model_fn        : callable
    frequency_hz    : float
    samples_per_cycle: int or None — if None, computed from t

    Returns
    -------
    float — scalar objective value
    """
    ia_m, ib_m, ic_m = _model_currents(theta_vec, t, model_fn, frequency_hz)

    if samples_per_cycle is None:
        dt = t[1] - t[0]
        samples_per_cycle = max(1, int(round(1.0 / (frequency_hz * dt))))

    rms_m = np.maximum(
        np.maximum(
            sliding_rms(ia_m, samples_per_cycle),
            sliding_rms(ib_m, samples_per_cycle),
        ),
        sliding_rms(ic_m, samples_per_cycle),
    )

    return float(np.sum((i_rms_meas - rms_m) ** 2))


def total_inverse_objective(
    theta_vec,
    t,
    ia_meas,
    ib_meas,
    ic_meas,
    i_rms_meas,
    model_fn,
    theta_prior_vec,
    weights=(1.0, 0.5, 0.1),
    frequency_hz=50.0,
):
    """
    Weighted total objective:

    J(θ) = w1·J1 + w2·J2 + w3·‖θ − θ_prior‖²

    Parameters
    ----------
    theta_vec       : ndarray — current parameter vector
    t               : ndarray — time vector (s)
    ia_meas,ib_meas,ic_meas : ndarray — measured currents (pu)
    i_rms_meas      : ndarray — measured RMS (pu)
    model_fn        : callable
    theta_prior_vec : ndarray — prior / nominal parameter vector
    weights         : tuple   — (w1, w2, w3), default (1.0, 0.5, 0.1)
    frequency_hz    : float

    Returns
    -------
    float — scalar total objective
    """
    w1, w2, w3 = weights

    J1 = waveform_mismatch_objective(
        theta_vec, t, ia_meas, ib_meas, ic_meas, model_fn, frequency_hz
    )
    J2 = relay_quantity_objective(
        theta_vec, t, i_rms_meas, model_fn, frequency_hz
    )
    J3 = float(np.sum((theta_vec - theta_prior_vec) ** 2))

    return w1 * J1 + w2 * J2 + w3 * J3


def residual_vector_phaseA(
    theta_vec,
    t,
    ia_meas,
    model_fn,
    frequency_hz=50.0,
):
    """
    Single-phase (A only) residual vector for scipy.optimize.least_squares.

    Fitting phase A alone avoids DC cross-cancellation across phases B and C,
    which causes tau_dc to collapse to its lower bound in the 3-phase objective.
    Phases B and C are reconstructed analytically after the fit.

    r(θ) = ia_meas − ia_model

    Returns
    -------
    ndarray, shape (len(t),)
    """
    ia_m, _, _ = _model_currents(theta_vec, t, model_fn, frequency_hz)
    return ia_meas - ia_m


def residual_vector_sequence(
    theta_vec,
    t,
    i_seq_meas,
    model_fn,
    frequency_hz=50.0,
):
    """
    Residual vector for a single sequence component signal.

    Structurally identical to residual_vector_phaseA; the model is evaluated
    for its phase-A output and compared against the sequence waveform
    (I1, I2, or I0 from symmetrical_components).

    r(θ) = i_seq_meas − ia_model(θ)

    Parameters
    ----------
    theta_vec  : ndarray  — flat 6-parameter vector (THETA_KEYS order)
    t          : ndarray  — time vector (s)
    i_seq_meas : ndarray  — sequence component waveform (pu, real-valued)
    model_fn   : callable
    frequency_hz : float

    Returns
    -------
    ndarray, shape (len(t),)
    """
    ia_m, _, _ = _model_currents(theta_vec, t, model_fn, frequency_hz)
    return i_seq_meas - ia_m


def residual_vector(
    theta_vec,
    t,
    ia_meas,
    ib_meas,
    ic_meas,
    model_fn,
    frequency_hz=50.0,
):
    """
    Concatenated residual vector for use with scipy.optimize.least_squares.

    r(θ) = [ia_meas − ia_model | ib_meas − ib_model | ic_meas − ic_model]

    Parameters
    ----------
    (same as waveform_mismatch_objective)

    Returns
    -------
    ndarray, shape (3·len(t),) — residual vector
    """
    ia_m, ib_m, ic_m = _model_currents(theta_vec, t, model_fn, frequency_hz)
    return np.concatenate([
        ia_meas - ia_m,
        ib_meas - ib_m,
        ic_meas - ic_m,
    ])
