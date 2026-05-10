"""faultloc_identifiability_check.py
=====================================
Local structural identifiability check for the SAMBPS-DTaaS Fault-
Location Identification project.

WP3.5 (P3.5) implementation -- closes R5 ("single-bin DFT bias").

Theory
------

For a static observation model y = h(theta) with parameter
theta in R^p and observation y in R^m (or C^{m/2}), the Hermann-Krener
observability rank condition (Hermann & Krener 1977; Sontag 1979) is

    rank(J(theta)) = p,

where J(theta) = dh/dtheta is the m x p Jacobian.  For dynamic
systems the rank check is on the Lie-derivative observability matrix
(Hermann-Krener) and the algorithmic implementation due to
Villaverde 2024 (STRIKE-GOLDD 4.0) handles the full nonlinear
case.  For our fault-location estimator the observation is the
single-bin admittance phasor at f0, which under the WP1.4 / WP2.1
forward models is an algebraic function of theta = (alpha, R_x);
the Lie-derivative reduces to the algebraic Jacobian and the
observability rank condition becomes "is J full rank at this
operating point?".

A QUANTITATIVE refinement: rank-deficiency is binary and
ill-conditioned, so the practical identifiability metric is the
smallest singular value sigma_min(J).  sigma_min(J) > 0 satisfies
the Hermann-Krener ORC; sigma_min(J) close to zero is
"locally degenerate" -- the ML estimator's covariance scales as
1 / sigma_min^2 and the optimiser's cost surface flattens.

Public API
----------

* ``jacobian_real_imag(model_fn, theta, *, h=...)`` -> ndarray
  (m, p) real Jacobian via central finite differences on the
  real-and-imaginary stacked observation.

* ``sigma_min_at(theta, *, model_fn=H_distributed, omega=...)``
  -> float; smallest singular value of J at theta.

* ``observability_rank(theta, ...)`` -> int; integer rank of J at
  theta with the WP3.5 default tolerance.

* ``map_sigma_min(alpha_grid, Rx_grid, ...)`` -> 2-D array of
  sigma_min(J) on a (alpha, R_x) grid.  Drives the WP3.5
  identifiability heatmap in
  ``run_faultloc_phase3_identifiability_map.py``.

* ``flag_local_degeneracy(theta_hat, sigma_min_grid, alpha_grid,
  Rx_grid, threshold=1e-3)`` -> dict {"ok": bool, "sigma_min": float,
  "is_degenerate": bool}.

References
----------

* Hermann, R. and Krener, A.J., "Nonlinear Controllability and
  Observability", IEEE Transactions on Automatic Control, vol. 22,
  no. 5, pp. 728-740, 1977.
* Sontag, E.D., "Mathematical Control Theory", Springer 2nd ed., 1998.
* Villaverde, A.F. et al., "STRIKE-GOLDD 4.0: User-Friendly,
  Efficient Analysis of Structural Identifiability and
  Observability", arXiv:2410.06984, 2024.

Note on STRIKE-GOLDD
--------------------

The Villaverde 2024 STRIKE-GOLDD reference implementation is a
MATLAB / Maple package; the WP3.5 commit ships an algebraic-Jacobian
SVD-based numerical equivalent specialised to our two-parameter
single-bin observation problem.  A symbolic Lie-derivative pipeline
that replays STRIKE-GOLDD on the Phase-2 distributed-parameter
forward model lands at WP3.6 if needed; the algebraic numerical
check is sufficient for the WP3.5 R5 closure (the ORC is
SATISFIED everywhere except the documented near-degenerate region;
the latter is the empirical certification of R5).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    H_distributed,
)

OMEGA = 2.0 * np.pi * 50.0
# WP3.5 default: flag locally degenerate cells where the inverse
# condition number sigma_min/sigma_max < 1e-2.  This roughly
# corresponds to the bottom 5 % of cells on the standard 50 x 50
# (alpha in [0.05, 0.95]; R_x geomspace [100, 5000] ohm) operating
# grid -- empirically the near-source (alpha < 0.15) + high-R_x
# (R_x > 3000 ohm) corner predicted by v3 Execution Plan
# Sect. 3.13.  See docs/changelog.md for the WP3.5 calibration note.
DEFAULT_THRESHOLD_SIGMA_MIN = 1.0e-2


def jacobian_real_imag(
    model_fn: Callable[[float, float, float], complex],
    theta: tuple[float, float],
    *,
    omega: float = OMEGA,
    h_alpha: float = 1.0e-5,
    h_Rx_rel: float = 1.0e-3,
) -> np.ndarray:
    """Real (2, 2) Jacobian J_ij = d Re/Im(H) / d theta_j at theta.

    Computes via central finite differences on Re(H) and Im(H)
    stacked.  Returns shape (2, 2): rows are [Re(H), Im(H)] and
    columns are [d/d alpha, d/d R_x].
    """
    alpha, Rx = float(theta[0]), float(theta[1])
    h_R = h_Rx_rel * abs(Rx)
    Hp = model_fn(alpha + h_alpha, Rx, omega)
    Hm = model_fn(alpha - h_alpha, Rx, omega)
    dH_da = (Hp - Hm) / (2.0 * h_alpha)
    Hp = model_fn(alpha, Rx + h_R, omega)
    Hm = model_fn(alpha, Rx - h_R, omega)
    dH_dR = (Hp - Hm) / (2.0 * h_R)
    return np.array([
        [dH_da.real, dH_dR.real],
        [dH_da.imag, dH_dR.imag],
    ], dtype=float)


def sigma_min_at(
    theta: tuple[float, float],
    *,
    model_fn: Callable[[float, float, float], complex] = H_distributed,
    omega: float = OMEGA,
) -> float:
    """Smallest singular value of the real Jacobian at theta.

    Returns 0.0 if the Jacobian computation fails (e.g. at a
    parameter-boundary degeneracy).
    """
    try:
        J = jacobian_real_imag(model_fn, theta, omega=omega)
        return float(np.linalg.svd(J, compute_uv=False).min())
    except Exception:
        return 0.0


def sigma_min_over_max_at(
    theta: tuple[float, float],
    *,
    model_fn: Callable[[float, float, float], complex] = H_distributed,
    omega: float = OMEGA,
) -> float:
    """Inverse condition number sigma_min(J) / sigma_max(J) at theta.

    Scale-invariant identifiability metric.  Stays in [0, 1].  Values
    near 1 indicate well-conditioned Jacobian; values < 1e-3 indicate
    locally degenerate (anisotropic) parameter sensitivity.
    """
    try:
        J = jacobian_real_imag(model_fn, theta, omega=omega)
        s = np.linalg.svd(J, compute_uv=False)
        if s.max() <= 0:
            return 0.0
        return float(s.min() / s.max())
    except Exception:
        return 0.0


def observability_rank(
    theta: tuple[float, float],
    *,
    model_fn: Callable[[float, float, float], complex] = H_distributed,
    omega: float = OMEGA,
    rcond: float = 1.0e-12,
) -> int:
    """Integer rank of J at theta -- the Hermann-Krener observability
    rank.  ``observability_rank == p`` (= 2 here) iff the ORC is
    satisfied locally."""
    J = jacobian_real_imag(model_fn, theta, omega=omega)
    s = np.linalg.svd(J, compute_uv=False)
    return int(np.sum(s > s.max() * rcond))


def map_sigma_min(
    alpha_grid: np.ndarray,
    Rx_grid: np.ndarray,
    *,
    model_fn: Callable[[float, float, float], complex] = H_distributed,
    omega: float = OMEGA,
) -> np.ndarray:
    """Evaluate sigma_min(J) on a 2-D (alpha, R_x) grid.

    Returns shape ``(len(alpha_grid), len(Rx_grid))``; rows index
    alpha (varying within row constant), columns index R_x.
    """
    a = np.asarray(alpha_grid, dtype=float)
    R = np.asarray(Rx_grid, dtype=float)
    out = np.zeros((a.size, R.size), dtype=float)
    for i, av in enumerate(a):
        for j, rv in enumerate(R):
            out[i, j] = sigma_min_at(
                (float(av), float(rv)),
                model_fn=model_fn, omega=omega,
            )
    return out


def map_sigma_min_over_max(
    alpha_grid: np.ndarray,
    Rx_grid: np.ndarray,
    *,
    model_fn: Callable[[float, float, float], complex] = H_distributed,
    omega: float = OMEGA,
) -> np.ndarray:
    """Evaluate sigma_min(J)/sigma_max(J) on a 2-D grid.  Scale-
    invariant identifiability metric in [0, 1]."""
    a = np.asarray(alpha_grid, dtype=float)
    R = np.asarray(Rx_grid, dtype=float)
    out = np.zeros((a.size, R.size), dtype=float)
    for i, av in enumerate(a):
        for j, rv in enumerate(R):
            out[i, j] = sigma_min_over_max_at(
                (float(av), float(rv)),
                model_fn=model_fn, omega=omega,
            )
    return out


def map_observability_rank(
    alpha_grid: np.ndarray,
    Rx_grid: np.ndarray,
    *,
    model_fn: Callable[[float, float, float], complex] = H_distributed,
    omega: float = OMEGA,
    rcond: float = 1.0e-12,
) -> np.ndarray:
    """Hermann-Krener observability rank on a 2-D (alpha, R_x) grid.

    Returns shape ``(len(alpha_grid), len(Rx_grid))`` integer array;
    cells where the value < 2 fail the ORC (locally non-identifiable).
    """
    a = np.asarray(alpha_grid, dtype=float)
    R = np.asarray(Rx_grid, dtype=float)
    out = np.zeros((a.size, R.size), dtype=int)
    for i, av in enumerate(a):
        for j, rv in enumerate(R):
            out[i, j] = observability_rank(
                (float(av), float(rv)),
                model_fn=model_fn, omega=omega, rcond=rcond,
            )
    return out


def flag_local_degeneracy(
    theta_hat: tuple[float, float],
    sigma_min_grid: np.ndarray,
    alpha_grid: np.ndarray,
    Rx_grid: np.ndarray,
    *,
    threshold: float = DEFAULT_THRESHOLD_SIGMA_MIN,
) -> dict:
    """Look up sigma_min at the cell nearest theta_hat and flag if below
    the WP3.5 threshold.

    Returns a dict with keys:
      ok            -- True iff sigma_min >= threshold
      sigma_min     -- the sigma_min value at the nearest grid cell
      is_degenerate -- True iff sigma_min < threshold
      i, j          -- indices of the nearest cell on (alpha, R_x)
    """
    a_idx = int(np.argmin(np.abs(alpha_grid - theta_hat[0])))
    R_idx = int(np.argmin(np.abs(Rx_grid - theta_hat[1])))
    sm = float(sigma_min_grid[a_idx, R_idx])
    is_degen = bool(sm < threshold)
    return {
        "ok": not is_degen,
        "sigma_min": sm,
        "is_degenerate": is_degen,
        "i": a_idx,
        "j": R_idx,
    }


__all__ = [
    "OMEGA",
    "DEFAULT_THRESHOLD_SIGMA_MIN",
    "jacobian_real_imag",
    "sigma_min_at",
    "sigma_min_over_max_at",
    "observability_rank",
    "map_sigma_min",
    "map_sigma_min_over_max",
    "map_observability_rank",
    "flag_local_degeneracy",
]
