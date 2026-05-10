"""tests/test_distributed_vs_50section.py
============================================

WP2.1 acceptance: closed-form distributed-parameter
``H_distributed`` vs the WP1.3 50-section pi reference
``H_model_n_sections``.

K03 (modelling-error vs 50-section reference, target < 5 % mean):
satisfied to numerical precision (~1e-5 %) on the 10 x 5
(alpha, R_x) grid because the 50-section pi-model converges to the
distributed-parameter limit.  This test is therefore a regression
gate against future drift; the empirical Phase-2 win comes from
*coupling the distributed forward model to the optimiser* (WP2.4),
not from the model fidelity per se (which P1.3 / P0.5's
Cascaded-Gamma 2-section was already inside the threshold).
"""

from __future__ import annotations

import numpy as np
from sambp_fault_location_id.models.faultloc_50section_reference import (
    H_model_n_sections,
)
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    H_distributed,
    H_distributed_grid,
    magnitude_phase_error,
)

OMEGA = 2 * np.pi * 50.0
ALPHAS = np.round(np.arange(0.05, 0.96, 0.10), 6)   # 10 values
RXS = np.array([100.0, 500.0, 1000.0, 2000.0, 5000.0])  # 5 values


def _ref_grid() -> np.ndarray:
    """Compute the 50-section reference grid once."""
    H = np.zeros((len(ALPHAS), len(RXS)), dtype=complex)
    for i, a in enumerate(ALPHAS):
        for j, R in enumerate(RXS):
            H[i, j] = H_model_n_sections(float(a), float(R), OMEGA)
    return H


def test_max_magnitude_error_below_5pct() -> None:
    """K03: max |dist - ref| / |ref| < 5 % across the 10 x 5 grid."""
    H_d = H_distributed_grid(ALPHAS, RXS, OMEGA)
    H_r = _ref_grid()
    mag_err, _ = magnitude_phase_error(H_d, H_r)
    assert mag_err.max() < 5.0, (
        f"max magnitude error = {mag_err.max():.4f} %, exceeds K03 "
        f"threshold of 5 %."
    )


def test_max_magnitude_error_below_1pct_DC_target() -> None:
    """D-C target (WP2.3): tighter < 1 % threshold across the grid.

    Empirical: max ~ 2.65e-5 % across the 10 x 5 grid; the 50-section
    reference's own sectioning floor (vs 100-section) is at the same
    order, so the residual is sectioning-limited, not a real
    distributed-vs-pi gap.  See outputs/phase2_reproduction.csv for
    the per-cell source-of-residual classification.
    """
    H_d = H_distributed_grid(ALPHAS, RXS, OMEGA)
    H_r = _ref_grid()
    mag_err, _ = magnitude_phase_error(H_d, H_r)
    assert mag_err.max() < 1.0, (
        f"max magnitude error = {mag_err.max():.4f} %, exceeds D-C "
        f"target of 1 %."
    )


def test_max_phase_error_below_5_deg_at_noiseless() -> None:
    """At SNR = inf the phase error must be < 5 degrees across the grid."""
    H_d = H_distributed_grid(ALPHAS, RXS, OMEGA)
    H_r = _ref_grid()
    _, phase_err = magnitude_phase_error(H_d, H_r)
    assert phase_err.max() < 5.0, (
        f"max phase error = {phase_err.max():.6f} deg, exceeds 5 deg."
    )


def test_scalar_and_grid_agree() -> None:
    """Vectorised grid form must match the scalar form pointwise."""
    H_d_grid = H_distributed_grid(ALPHAS, RXS, OMEGA)
    for i, a in enumerate(ALPHAS):
        for j, R in enumerate(RXS):
            H_scalar = H_distributed(float(a), float(R), OMEGA)
            assert abs(H_d_grid[i, j] - H_scalar) < 1e-12, (
                f"grid vs scalar diverge at (alpha={a}, Rx={R}): "
                f"grid={H_d_grid[i, j]}, scalar={H_scalar}"
            )


def test_low_loss_limit_reduces_to_pi() -> None:
    """At very low loss (R' -> 0, G' -> 0) the distributed model
    reduces to a lossless lumped pi at low frequency.  Sanity check
    that Z_c is real and gamma is purely imaginary in the limit."""
    from sambp_fault_location_id.models.faultloc_distributed_param_model import (
        _line_constants,
    )
    gamma, Z_c = _line_constants(
        omega=2 * np.pi * 50.0,
        R_per_km=1e-12, L_per_km=0.927e-3,
        C_per_km=11.6e-9, G_per_km=0.0,
    )
    assert abs(gamma.real) < 1e-9 * abs(gamma.imag), \
        "lossless line: gamma should be purely imaginary"
    assert abs(Z_c.imag) < 1e-9 * abs(Z_c.real), \
        "lossless line: Z_c should be purely real"
