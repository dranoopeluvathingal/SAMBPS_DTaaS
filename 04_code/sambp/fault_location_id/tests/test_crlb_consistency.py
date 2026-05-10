r"""tests/test_crlb_consistency.py
====================================

WP1.6 cross-check: ``faultloc_crlb_proper`` (Kuruoğlu 2018) vs
``faultloc_crlb_dualchannel`` (Nehorai--Hawkes 2000).

Mathematical relationship
-------------------------

Both bounds use the same Fisher kernel
:math:`\mathrm{Re}(dH/d\theta_k^* \cdot dH/d\theta_l)` but differ in
the effective noise variance:

* dual-channel CRLB on V/I waveforms:
    F_dual = (Ns/2) V_phase^2 / sigma_i_t^2 * Re(...)

* proper-ratio CRLB on H_meas = I_bin/V_bin (high-SNR Gaussian
  approximation a la Kuruoğlu 2018):
    F_proper = |V_phase|^2 / (sigma_I^2 + |H|^2 sigma_V^2) * Re(...)

with sigma_I^2 = 2 sigma_i_t^2 / Ns and sigma_V^2 = 2 sigma_v_t^2 / Ns
the variances per real/imag of the single-bin DFT phasors.  Their
ratio is

    F_proper / F_dual = sigma_I^2 / (sigma_I^2 + |H|^2 sigma_V^2)
                      = SNR_V_bin / (SNR_V_bin + SNR_I_bin)

(when both SNRs are referenced to the same |H V_phase|^2 / 2 power).
At sigma_V -> 0 (i.e. SNR_V = inf, V perfectly known) the two are
exactly equal.  At SNR_V = SNR_I they differ by a factor of 2 in
F (factor sqrt(2) in RMSE).

Tests below
-----------

  test_crlb_proper_eq_dual_when_V_noiseless
      Asserts |rmse_proper - rmse_dual| / rmse_dual < 5 % at
      SNR_V = inf, SNR_I in {40, 50, 60} dB.  This is the formal
      WP1.6 brief acceptance ("agree to within 5 % in the
      Geary-Hinkley regime").

  test_crlb_factor_sqrt2_when_snrV_eq_snrI
      Asserts rmse_proper / rmse_dual = sqrt(2) +/- 1 % when
      SNR_V = SNR_I (analytical prediction).

  test_crlb_diverge_at_low_snrV
      Asserts rmse_proper > rmse_dual at SNR_V = 20 dB; documents
      the divergence regime.

  test_geary_hinkley_validity_flag
      Asserts the GH flag is True for SNR_V = inf and >= 30 dB
      (large-|V_phase|/sigma_V regime), False for SNR_V = 0 dB.
"""

from __future__ import annotations

import numpy as np
import pytest
from sambp_fault_location_id.inverse_estimation.faultloc_crlb_dualchannel import (
    crlb_dualchannel,
)
from sambp_fault_location_id.inverse_estimation.faultloc_crlb_proper import (
    crlb_proper,
    geary_hinkley_valid,
)

OMEGA = 2 * np.pi * 50.0


@pytest.mark.parametrize(
    "alpha, Rx, snr_i_db",
    [
        (0.30, 500.0, 40.0),
        (0.50, 1000.0, 40.0),
        (0.50, 1000.0, 50.0),
        (0.70, 2000.0, 60.0),
    ],
)
def test_crlb_proper_eq_dual_when_V_noiseless(
    alpha: float, Rx: float, snr_i_db: float
) -> None:
    """At SNR_V = inf the proper-ratio and dual-channel CRLBs must
    agree to within 5 % (the Geary--Hinkley regime).  Brief acceptance."""
    rp = crlb_proper(alpha, Rx, OMEGA, snr_v_db=np.inf, snr_i_db=snr_i_db)
    rd = crlb_dualchannel(alpha, Rx, OMEGA, snr_i_db=snr_i_db)
    rel = abs(rp.rmse_alpha_pct - rd.rmse_alpha_pct) / rd.rmse_alpha_pct
    assert rel < 0.05, (
        f"alpha={alpha}, Rx={Rx}, SNR_I={snr_i_db}dB:  "
        f"|proper - dual| / dual = {rel:.4f} >= 0.05  "
        f"(proper={rp.rmse_alpha_pct:.6f}%, dual={rd.rmse_alpha_pct:.6f}%)"
    )


@pytest.mark.parametrize("alpha, Rx", [(0.5, 1000.0), (0.3, 500.0)])
def test_crlb_factor_sqrt2_when_snrV_eq_snrI(alpha: float, Rx: float) -> None:
    """At SNR_V = SNR_I, F_proper = F_dual / 2, so RMSE ratio = sqrt(2)."""
    for snr in [30.0, 40.0, 50.0]:
        rp = crlb_proper(alpha, Rx, OMEGA, snr_v_db=snr, snr_i_db=snr)
        rd = crlb_dualchannel(alpha, Rx, OMEGA, snr_i_db=snr)
        ratio = rp.rmse_alpha_pct / rd.rmse_alpha_pct
        assert abs(ratio - np.sqrt(2.0)) / np.sqrt(2.0) < 0.01, (
            f"alpha={alpha}, Rx={Rx}, SNR={snr}dB:  "
            f"proper/dual = {ratio:.6f}, expected sqrt(2)={np.sqrt(2.0):.6f}"
        )


def test_crlb_diverge_at_low_snrV() -> None:
    """At low SNR_V the proper-ratio bound is looser than dual-channel."""
    rp = crlb_proper(0.5, 1000.0, OMEGA, snr_v_db=20.0, snr_i_db=30.0)
    rd = crlb_dualchannel(0.5, 1000.0, OMEGA, snr_i_db=30.0)
    assert rp.rmse_alpha_pct > rd.rmse_alpha_pct, (
        f"expected proper > dual when SNR_V is low; "
        f"proper={rp.rmse_alpha_pct:.4f}, dual={rd.rmse_alpha_pct:.4f}"
    )


def test_geary_hinkley_validity_flag() -> None:
    """GH valid across the operating envelope (SNR_V_bin > 4).

    With Ns = 200 the single-bin DFT averages V noise by a factor
    sqrt(Ns/2) = 10, so a time-domain SNR_V of x dB corresponds to
    SNR_V_bin of x + 20 dB.  GH validity (|V_phase|/sigma_V_bin > 4
    => SNR_V_bin > 12 dB) therefore holds for all time-domain
    SNR_V > -8 dB, which covers the whole 720-case grid (which
    starts at 20 dB).  Test: GH valid at noiseless and 20 dB,
    invalid below the boundary.
    """
    assert geary_hinkley_valid(np.inf) is True
    assert geary_hinkley_valid(20.0) is True
    assert geary_hinkley_valid(0.0) is True   # bin-SNR ~20 dB still > 12
    assert geary_hinkley_valid(-30.0) is False   # below the boundary


def test_crlb_proper_returns_finite_rmse_at_finite_snr() -> None:
    """Sanity: at any finite SNR pair, both bounds are positive and finite."""
    for snr_v in [20.0, 30.0, 40.0]:
        for snr_i in [20.0, 30.0, 40.0]:
            rp = crlb_proper(0.5, 1000.0, OMEGA, snr_v_db=snr_v, snr_i_db=snr_i)
            rd = crlb_dualchannel(0.5, 1000.0, OMEGA, snr_i_db=snr_i)
            assert np.isfinite(rp.rmse_alpha_pct) and rp.rmse_alpha_pct > 0
            assert np.isfinite(rd.rmse_alpha_pct) and rd.rmse_alpha_pct > 0
