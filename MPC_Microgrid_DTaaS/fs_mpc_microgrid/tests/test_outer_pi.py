"""Outer energy-PI unit tests."""

import numpy as np

from fs_mpc_mg.outer_energy_pi import EnergyPI, EnergyPIParams


def test_zero_error_yields_zero_output():
    pi = EnergyPI(EnergyPIParams())
    out = pi.update(v_dc=pi.p.v_dc_ref, dt=2e-4)
    # Single tick at zero error gives zero PI output
    assert abs(out) < 1e-6


def test_positive_error_yields_positive_amp():
    """v_dc below reference -> needs to draw more grid current -> positive amp."""
    pi = EnergyPI(EnergyPIParams())
    out = pi.update(v_dc=pi.p.v_dc_ref - 50.0, dt=2e-4)
    assert out > 0.0


def test_pi_gains_are_finite():
    pi = EnergyPI(EnergyPIParams())
    Kp, Ki = pi.gains
    assert np.isfinite(Kp) and Kp > 0
    assert np.isfinite(Ki) and Ki > 0
