"""tests/test_three_phase_skeleton.py
=========================================

WP3.1 smoke tests for the three-phase Y_abc model and the IEEE feeder
hooks.  These tests guard the API surface and basic numerical sanity;
the WP3.7 acceptance test (T-D1, mean loc-err < 3 % on IEEE 34-node)
lands later in Phase 3.

Properties asserted here (refreshed at WP3.1 P3.1):

1. ``H_phase`` returns a (3,) complex vector with finite entries on
   the standard (alpha, R_x) test points.
2. ``build_Y_abc`` returns a 3x3 complex matrix; the diagonal equals
   ``H_phase``.  The off-diagonals follow the proper Z_abc / Y_abc
   coupling, no longer the WP3.1 SKELETON placeholder.
3. ``Y_send`` reduces approximately to the single-phase WP2.1
   ``H_distributed`` on the faulted phase A.
4. ``Y_send`` is symmetric in the off-diagonal block-structure
   inherited from the symmetric (transposed) line approximation:
   ``Y_send[1,2] == Y_send[2,1]``, etc.
5. ``inject_hif`` returns a ``WaveformBundle`` with V and I shaped
   (3, n_samples) and the sampling configuration matches the
   single-phase WP1.1 baseline.
"""

from __future__ import annotations

import numpy as np
import pytest
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    H_distributed,
)
from sambp_fault_location_id.models.faultloc_ieee_feeders import (
    inject_hif,
    load_feeder,
)
from sambp_fault_location_id.models.faultloc_three_phase_model import (
    H_phase,
    Y_send,
    build_Y_abc,
    fault_ABCD,
)

OMEGA = 2 * np.pi * 50.0


@pytest.mark.parametrize(
    "alpha, Rx",
    [(0.30, 100.0), (0.50, 1000.0), (0.70, 5000.0)],
)
def test_H_phase_returns_3vec_finite(alpha: float, Rx: float) -> None:
    H = H_phase(OMEGA, alpha, Rx)
    assert H.shape == (3,)
    assert H.dtype == complex
    assert np.all(np.isfinite(H))
    assert abs(H[0]) > 1e-12
    assert abs(H[1]) > 1e-12
    assert abs(H[2]) > 1e-12


def test_build_Y_abc_diagonal_matches_H_phase() -> None:
    Y = build_Y_abc(0.5, 1000.0, OMEGA)
    assert Y.shape == (3, 3)
    assert Y.dtype == complex
    H = H_phase(OMEGA, 0.5, 1000.0)
    np.testing.assert_allclose(np.diag(Y), H, rtol=1e-12)


def test_Y_send_phase_A_close_to_single_phase_baseline() -> None:
    """The faulted phase Y_aa should be within 5 % of the single-phase
    WP2.1 H_distributed at the same (alpha, R_x).  The mutual-coupling
    perturbation off the WP2.1 result is small because the SLG fault
    is on phase A only and the line is symmetric."""
    omega = OMEGA
    Y = Y_send(0.5, 1000.0, omega)
    H_1ph = H_distributed(0.5, 1000.0, omega)
    rel_err = abs(Y[0, 0] - H_1ph) / abs(H_1ph)
    assert rel_err < 0.05, f"Y_aa vs single-phase H rel-err = {rel_err:.3e}"


def test_Y_send_off_diagonal_symmetric_under_transposed_line() -> None:
    """Under the WP3.1 transposed-line approximation, the only
    asymmetry in Y_send comes from the SLG fault on phase A.  By
    inspection, Y_send[1, 2] == Y_send[2, 1] (phases B and C see the
    same line and the same fault contribution)."""
    Y = Y_send(0.5, 1000.0, OMEGA)
    np.testing.assert_allclose(Y[1, 2], Y[2, 1], rtol=1e-10)


def test_Y_send_recovers_no_fault_baseline_at_high_Rx() -> None:
    """As R_x -> infinity, the fault becomes invisible and Y_send
    should recover the symmetric no-fault baseline (all diagonals
    equal, all off-diagonals equal)."""
    Y = Y_send(0.5, 1.0e12, OMEGA)
    diag = np.diag(Y)
    np.testing.assert_allclose(diag, diag[0], rtol=1e-6)
    off = Y - np.diag(diag)
    off_vals = off[off != 0]
    np.testing.assert_allclose(off_vals, off_vals[0], rtol=1e-6)


def test_fault_ABCD_phase_validation() -> None:
    with pytest.raises(ValueError, match="fault_phase must be"):
        fault_ABCD(1000.0, fault_phase=3)


def test_load_feeder_ieee_13_has_buses() -> None:
    feeder = load_feeder("IEEE_13")
    assert feeder.name == "IEEE_13"
    assert "632" in feeder.buses
    assert "671" in feeder.buses
    assert len(feeder.branches) >= 5


def test_load_feeder_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown feeder name"):
        load_feeder("IEEE_unknown")


def test_inject_hif_returns_3xN_bundle() -> None:
    feeder = load_feeder("IEEE_13")
    bundle = inject_hif(feeder, "632", 0.5, 1000.0, n_samples=200)
    assert bundle.V.shape == (3, 200)
    assert bundle.I.shape == (3, 200)
    assert bundle.fs_hz == 10_000.0
    assert bundle.f0_hz == 50.0
    assert bundle.feeder_name == "IEEE_13"
    assert bundle.fault_bus == "632"
    assert bundle.fault_alpha == 0.5
    assert bundle.fault_Rx_ohm == 1000.0
    assert np.all(np.isfinite(bundle.V))
    assert np.all(np.isfinite(bundle.I))


def test_inject_hif_unknown_bus_raises() -> None:
    feeder = load_feeder("IEEE_13")
    with pytest.raises(ValueError, match="not in feeder"):
        inject_hif(feeder, "bus_NOPE", 0.5, 1000.0)
