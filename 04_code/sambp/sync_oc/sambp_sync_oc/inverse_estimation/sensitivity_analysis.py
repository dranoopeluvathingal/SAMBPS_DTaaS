# =============================================================================
# sambp / sambp_sync_oc
# inverse_estimation/sensitivity_analysis.py
#
# Evaluate sensitivity and identifiability of estimated parameters.
#
# Stage 1: Jacobian-based metrics (condition number + column norms).
# Stage 2 stubs: Fisher information matrix, Hessian approximation,
#                effective identifiable subset (EIS).
#
# Public API
# ----------
# compute_jacobian_condition_number(jacobian)              → float
# compute_parameter_sensitivities(jacobian, parameter_names) → dict
# fisher_information_matrix(jacobian, sigma)               → ndarray (stub)
# effective_identifiable_subset(jacobian, threshold)       → list   (stub)
# =============================================================================

import numpy as np


# ---------------------------------------------------------------------------
# Stage 1: Jacobian-based metrics
# ---------------------------------------------------------------------------

def compute_jacobian_condition_number(jacobian):
    """
    Return the condition number of the Jacobian matrix.

    A high condition number (> 100) indicates poor identifiability —
    small changes in measurements produce large swings in parameter estimates.

    Parameters
    ----------
    jacobian : ndarray, shape (n_residuals, n_params) — from least_squares result

    Returns
    -------
    float — condition number κ(J)  (np.inf if singular)
    """
    J = np.asarray(jacobian, dtype=float)
    if J.ndim != 2:
        raise ValueError(f"Expected 2D Jacobian, got shape {J.shape}.")

    sv = np.linalg.svd(J, compute_uv=False)
    if sv[-1] < 1e-14:
        return np.inf
    return float(sv[0] / sv[-1])


def compute_parameter_sensitivities(jacobian, parameter_names):
    """
    Compute simple column-norm sensitivity metric for each parameter.

    Sensitivity_k = ‖J[:,k]‖₂ / Σ_j ‖J[:,j]‖₂

    A low relative sensitivity indicates the parameter has little effect
    on the residual — it is poorly identifiable from this data.

    Parameters
    ----------
    jacobian        : ndarray, shape (n_residuals, n_params)
    parameter_names : list[str] — ordered parameter names (matches THETA_KEYS)

    Returns
    -------
    dict — {param_name: relative_sensitivity (float in [0,1])}
    """
    J     = np.asarray(jacobian, dtype=float)
    norms = np.linalg.norm(J, axis=0)
    total = np.sum(norms) + 1e-14

    return {name: float(norms[k] / total)
            for k, name in enumerate(parameter_names)}


# ---------------------------------------------------------------------------
# Stage 2 stubs
# ---------------------------------------------------------------------------

def fisher_information_matrix(jacobian, sigma=1.0):
    """
    (Stub) Compute Fisher information matrix F = (1/σ²)·JᵀJ.

    Parameters
    ----------
    jacobian : ndarray, shape (n_residuals, n_params)
    sigma    : float — assumed measurement noise std (pu)

    Returns
    -------
    ndarray, shape (n_params, n_params)
    """
    raise NotImplementedError(
        "Fisher information matrix planned for Stage 2."
    )


def effective_identifiable_subset(jacobian, threshold=0.05):
    """
    (Stub) Return the subset of parameters that are identifiable
    above a sensitivity threshold.

    Parameters
    ----------
    jacobian  : ndarray
    threshold : float — minimum relative sensitivity to be considered
                        identifiable

    Returns
    -------
    list[int] — column indices of identifiable parameters
    """
    raise NotImplementedError(
        "Effective identifiable subset analysis planned for Stage 2."
    )
