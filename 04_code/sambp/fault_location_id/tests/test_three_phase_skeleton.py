"""tests/test_three_phase_skeleton.py
=========================================

WP3.1 SKELETON smoke tests for the three-phase Y_abc model and the
IEEE feeder hooks.  These tests guard the API surface and the basic
shape / numerical sanity of the WP3.1 implementation; the WP3.4
acceptance test (T-D1, mean loc-err < 3 % on IEEE 34-node) lands at
WP3.7.

The three properties asserted here:

1. `H_phase` returns a (3,) complex vector with finite entries on
   the standard (alpha, R_x) test points.
2. `build_Y_abc` returns a 3x3 complex matrix; the diagonal is the
   `H_phase` vector and the off-diagonals are non-zero (the WP3.1
   placeholder mutual-coupling rule).
3. `inject_hif` returns a `WaveformBundle` with V and I shaped
   (3, n_samples) and the sampling configuration matches the
   single-phase WP1.1 baseline.
"""

from __future__ import annotations

import numpy as np
import pytest
from sambp_fault_location_id.models.faultloc_ieee_feeders import (
    inject_hif,
    load_feeder,
)
from sambp_fault_location_id.models.faultloc_three_phase_model import (
    MUTUAL_OVER_SELF_RATIO,
    H_phase,
    build_Y_abc,
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
    # Phase A carries the SLG signature; should be non-trivially
    # different from phases B and C.
    assert abs(H[0]) > 1e-12
    assert abs(H[1]) > 1e-12
    assert abs(H[2]) > 1e-12


def test_build_Y_abc_shape_and_diagonal() -> None:
    Y = build_Y_abc(0.5, 1000.0, OMEGA)
    assert Y.shape == (3, 3)
    assert Y.dtype == complex
    H = H_phase(OMEGA, 0.5, 1000.0)
    np.testing.assert_allclose(np.diag(Y), H, rtol=1e-12)
    # Off-diagonals follow the WP3.1 placeholder rule.
    for k in range(3):
        for j in range(3):
            if j != k:
                np.testing.assert_allclose(
                    Y[k, j], MUTUAL_OVER_SELF_RATIO * H[k], rtol=1e-12
                )


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


def test_fault_phase_nonzero_not_yet_implemented() -> None:
    """WP3.4 lifts this restriction; the skeleton only does SLG-on-A."""
    with pytest.raises(NotImplementedError, match="WP3.4"):
        H_phase(OMEGA, 0.5, 1000.0, fault_phase=1)
