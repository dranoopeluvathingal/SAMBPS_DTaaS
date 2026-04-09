# =============================================================================
# sambp / sambp_sync_oc
# inverse_estimation/confidence_logic.py
#
# Decide whether the inverse estimation result is reliable enough to
# allow adaptation of relay settings.
#
# Confidence score γ ∈ [0, 1]:
#   γ = w_r · s_residual + w_c · s_condition + w_b · s_bounds + w_p · s_plausibility
#
# Each sub-score is normalised to [0, 1] where 1 = high confidence.
#
# Public API
# ----------
# compute_confidence_score(residual_norm, condition_number,
#                          bounds_hit_fraction,
#                          parameter_plausibility_score)  → float
# accept_adaptation(confidence_score, threshold)          → bool
# =============================================================================

import numpy as np


# ---------------------------------------------------------------------------
# Sub-score normalisers
# ---------------------------------------------------------------------------

def _score_residual(residual_norm, norm_ref=1.0):
    """
    Map residual norm to [0, 1].
    s_r = exp(−residual_norm / norm_ref)
    A smaller residual gives a higher score.

    norm_ref: expected residual at moderate fit (tunable per application).
    """
    return float(np.exp(-residual_norm / (norm_ref + 1e-12)))


def _score_condition(condition_number, cond_good=10.0, cond_bad=1000.0):
    """
    Map condition number to [0, 1] via log-linear interpolation.
    s_c = 1 when κ ≤ cond_good, 0 when κ ≥ cond_bad.
    """
    if condition_number <= cond_good:
        return 1.0
    if condition_number >= cond_bad:
        return 0.0
    log_k    = np.log10(condition_number)
    log_good = np.log10(cond_good)
    log_bad  = np.log10(cond_bad)
    return float(1.0 - (log_k - log_good) / (log_bad - log_good))


def _score_bounds(bounds_hit_fraction):
    """
    Map fraction of parameters at their bounds to [0, 1].
    s_b = 1 − bounds_hit_fraction
    0 parameters at bounds → s_b = 1.0 (best).
    All parameters at bounds → s_b = 0.0 (worst — optimiser stuck).
    """
    return float(np.clip(1.0 - bounds_hit_fraction, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_confidence_score(
    residual_norm,
    condition_number,
    bounds_hit_fraction,
    parameter_plausibility_score,
    weights=(0.35, 0.30, 0.20, 0.15),
    residual_ref=1.0,
    cond_good=10.0,
    cond_bad=1000.0,
):
    """
    Compute composite confidence score γ ∈ [0, 1].

    Parameters
    ----------
    residual_norm              : float — ‖r‖ at optimiser solution
    condition_number           : float — κ(J), from sensitivity_analysis
    bounds_hit_fraction        : float — fraction of params at their bounds
                                         (0 = none, 1 = all)
    parameter_plausibility_score : float — external physics check score [0,1]
                                           (pass 1.0 if no check performed)
    weights                    : tuple  — (w_r, w_c, w_b, w_p), must sum to 1
    residual_ref               : float  — reference residual for normalisation
    cond_good, cond_bad        : float  — condition number scale limits

    Returns
    -------
    float — γ ∈ [0, 1]
    """
    w_r, w_c, w_b, w_p = weights

    s_r = _score_residual(residual_norm, norm_ref=residual_ref)
    s_c = _score_condition(condition_number, cond_good, cond_bad)
    s_b = _score_bounds(bounds_hit_fraction)
    s_p = float(np.clip(parameter_plausibility_score, 0.0, 1.0))

    gamma = w_r * s_r + w_c * s_c + w_b * s_b + w_p * s_p
    return float(np.clip(gamma, 0.0, 1.0))


def accept_adaptation(confidence_score, threshold):
    """
    Gate adaptation decision on confidence score.

    Parameters
    ----------
    confidence_score : float — γ from compute_confidence_score
    threshold        : float — minimum γ to allow adaptation
                               (from RELAY_CONFIG["confidence_threshold"])

    Returns
    -------
    bool — True if adaptation is permitted
    """
    return bool(confidence_score >= threshold)
