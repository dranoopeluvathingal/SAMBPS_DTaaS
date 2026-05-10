"""Plant unit tests."""

import numpy as np
import pytest

from fs_mpc_mg.plant import Plant, PlantParams, M_MATRIX, SWITCHING_VECTORS


def test_M_matrix_shape_and_balance():
    """M is a 3x3 zero-sequence-removal matrix; rows sum to zero."""
    assert M_MATRIX.shape == (3, 3)
    np.testing.assert_allclose(M_MATRIX.sum(axis=1), 0.0, atol=1e-12)
    np.testing.assert_allclose(M_MATRIX, M_MATRIX.T, atol=1e-12)


def test_switching_vectors_8_unique():
    assert SWITCHING_VECTORS.shape == (8, 3)
    assert set(SWITCHING_VECTORS.flatten().tolist()) == {0.0, 1.0}
    seen = {tuple(s) for s in SWITCHING_VECTORS}
    assert len(seen) == 8


def test_natural_decay_zero_voltage():
    """With s=000 and v_s=0, AC current decays exponentially toward zero."""
    p = Plant(PlantParams(L=1e-3, r=0.1, C=1000e-6, R=1e6, v_dc_init=0.0))
    p.i_m = np.array([10.0, -5.0, -5.0])
    s = np.zeros(3)
    v_s = np.zeros(3)
    dt = 1e-6
    for _ in range(30_000):
        p.step(s, v_s, i_dc=0.0, dt=dt)
    assert np.linalg.norm(p.i_m) < 5.0


def test_dc_link_charge_balance_with_zero_input():
    """No switching, no i_dc -> v_dc decays with R*C time constant only."""
    p = Plant(PlantParams(L=1e-3, r=0.1, C=1000e-6, R=10.0, v_dc_init=900.0))
    s = np.zeros(3)
    v_s = np.zeros(3)
    dt = 1e-5
    for _ in range(5000):
        p.step(s, v_s, i_dc=0.0, dt=dt)
    expected = 900.0 * np.exp(-5.0)
    assert abs(p.v_dc - expected) / expected < 0.05
