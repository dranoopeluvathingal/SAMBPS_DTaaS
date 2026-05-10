"""tests/test_analytical_gradients.py
========================================

WP2.2 acceptance: closed-form analytical partials in
``inverse_estimation.faultloc_analytical_gradients`` against the
central-finite-difference reference.

Brief acceptance: at three (alpha, R_x) test points
{(0.2, 100), (0.5, 1000), (0.8, 5000)} with FD steps
``h_alpha = 1e-5`` and ``h_R = 1e-2`` (relative), the relative error

    | (dH/dtheta)_analytic - (dH/dtheta)_FD |  /  |(dH/dtheta)_FD|

must be **< 1e-4** for both partials.

Note on the dH/dRx FD step.  ``h_R = 1e-2`` is interpreted as a
relative step (h_R_absolute = h_R * R_x); the brief is ambiguous on
this point.  The relative interpretation is consistent with the
optimiser default in
``inverse_estimation/faultloc_two_stage_optimiser`` (``h_Rx``=0.1
absolute = 1e-4 relative-ish near R_x=1000) and with the FD scaling
documented in ``faultloc_crlb_proper.py``.  At smaller absolute steps
the FD truncation error decreases; the analytical implementation is
exact (subject to numerical precision) at ALL steps.
"""

from __future__ import annotations

import numpy as np
import pytest
from sambp_fault_location_id.inverse_estimation.faultloc_analytical_gradients import (
    dH_dalpha,
    dH_dRx,
    dH_dtheta,
)
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    H_distributed,
)

OMEGA = 2 * np.pi * 50.0
H_ALPHA = 1.0e-5      # FD step in alpha (absolute)
H_RX_REL = 1.0e-2     # FD step in R_x (relative)
TOL_REL = 1.0e-4


@pytest.mark.parametrize(
    "alpha, Rx",
    [(0.2, 100.0), (0.5, 1000.0), (0.8, 5000.0)],
)
def test_dH_dalpha_matches_FD(alpha: float, Rx: float) -> None:
    an = dH_dalpha(alpha, Rx, OMEGA)
    fd = (H_distributed(alpha + H_ALPHA, Rx, OMEGA)
          - H_distributed(alpha - H_ALPHA, Rx, OMEGA)) / (2.0 * H_ALPHA)
    rel = abs(an - fd) / abs(fd)
    assert rel < TOL_REL, (
        f"dH/dalpha @(alpha={alpha}, Rx={Rx}) rel err {rel:.3e} >= {TOL_REL:.0e}"
    )


@pytest.mark.parametrize(
    "alpha, Rx",
    [(0.2, 100.0), (0.5, 1000.0), (0.8, 5000.0)],
)
def test_dH_dRx_matches_FD(alpha: float, Rx: float) -> None:
    an = dH_dRx(alpha, Rx, OMEGA)
    h = H_RX_REL * Rx
    fd = (H_distributed(alpha, Rx + h, OMEGA)
          - H_distributed(alpha, Rx - h, OMEGA)) / (2.0 * h)
    rel = abs(an - fd) / abs(fd)
    assert rel < TOL_REL, (
        f"dH/dRx @(alpha={alpha}, Rx={Rx}) rel err {rel:.3e} >= {TOL_REL:.0e}"
    )


def test_dH_dtheta_packed_matches_individual() -> None:
    """The packed dH_dtheta() must agree with dH_dalpha + dH_dRx."""
    for a, R in [(0.2, 100.0), (0.5, 1000.0), (0.8, 5000.0)]:
        d_pack_a, d_pack_R = dH_dtheta(a, R, OMEGA)
        d_individual_a = dH_dalpha(a, R, OMEGA)
        d_individual_R = dH_dRx(a, R, OMEGA)
        assert abs(d_pack_a - d_individual_a) < 1e-15, "packed dH/dα mismatch"
        assert abs(d_pack_R - d_individual_R) < 1e-15, "packed dH/dR_x mismatch"


def test_gradient_is_finite_across_grid() -> None:
    """Sanity: gradients are finite + nonzero across the operating grid."""
    for a in np.arange(0.1, 0.91, 0.1):
        for R in [100.0, 500.0, 1000.0, 2000.0, 5000.0]:
            d_a, d_R = dH_dtheta(float(a), float(R), OMEGA)
            assert np.isfinite(d_a) and np.isfinite(d_R)
            assert abs(d_a) > 0.0 and abs(d_R) > 0.0
