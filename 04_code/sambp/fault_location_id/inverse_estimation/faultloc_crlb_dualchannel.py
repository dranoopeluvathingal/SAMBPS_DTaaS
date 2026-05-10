r"""faultloc_crlb_dualchannel.py
=================================

Joint dual-channel Cramér-Rao bound in the (V(t), I(t)) time-domain
space (Nehorai & Hawkes, IEEE Trans.\ Signal Process.\ 48(6),
2000), projected onto (alpha, R_x) via the chain rule using the
analytic partials from
``models/faultloc_pi_section_model.py``.  This is the **ground-truth
information bound** in the dual-channel (V, I) measurement space,
against which ``faultloc_crlb_proper.py`` is cross-checked at high
SNR.

Signal model
------------

    v(t_n) = V_phase * cos(omega_0 t_n) + n_v(n)
    i(t_n) = Re{ H(theta) * V_phase * exp(j omega_0 t_n) } + n_i(n)

with n_v(n), n_i(n) ~ N(0, sigma_v_t^2), N(0, sigma_i_t^2)
independent across channels and across samples.  The source v is
treated as ideal, so dv_clean/dtheta == 0 and the V channel
contributes zero to the Fisher information about theta = (alpha, R_x).
The I channel carries all the signal-dependent information.

Fisher information
------------------

For each parameter index k,

    d i_clean(t_n) / d theta_k
        = Re{ (dH/dtheta_k) * V_phase * exp(j omega_0 t_n) }

so

    [J^T J]_{kl}
       = sum_{n=0}^{Ns-1}
           Re{ (dH/dtheta_k) V_phase exp(j omega t_n) }
           Re{ (dH/dtheta_l) V_phase exp(j omega t_n) }
       = (Ns / 2) * V_phase^2 * Re( (dH/dtheta_k)^* (dH/dtheta_l) )

(over a one-cycle window with Ns samples per cycle).  The dual-
channel FIM is then

    F_dual = (1 / sigma_i_t^2) * J^T J

and the CRLB is F_dual^{-1}, projected diagonally onto (alpha, R_x).

Relationship to ``faultloc_crlb_proper``
----------------------------------------

The two FIMs are related by

    F_proper / F_dual = sigma_I^2 / (sigma_I^2 + |H|^2 sigma_V^2)

where sigma_I^2 = 2 sigma_i_t^2 / Ns and sigma_V^2 = 2 sigma_v_t^2 / Ns
are the variances per real/imag component of the single-bin DFT
phasors I_bin and V_bin.  At sigma_V -> 0 (V perfectly known) the two
agree exactly; at finite sigma_V the proper-ratio bound is looser
because it represents the loss of information when only the ratio
H_meas = I_bin / V_bin is observed (rather than the raw V and I
waveforms).  Equivalent at high SNR_V (Geary--Hinkley regime).

References
----------

* Nehorai, A. \& Hawkes, M. (2000). Performance bounds for estimating
  vector systems.  IEEE Trans.\ Signal Process.\ 48(6), 1737--1749.
* Kay, S.\,M. (1993).  Fundamentals of Statistical Signal Processing,
  Volume I: Estimation Theory, Chapter 3 (vector parameter CRB).

WP-trace
--------
* WP1.6   This module + ``faultloc_crlb_proper.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sambp_fault_location_id.inverse_estimation.faultloc_crlb_proper import (
    H_ALPHA_DEFAULT,
    H_RX_RELATIVE,
    _dH_dtheta,
)
from sambp_fault_location_id.models.faultloc_pi_section_model import H_model

V_PHASE = 11000.0 / np.sqrt(3.0) * np.sqrt(2.0)
F0 = 50.0
NS = 200


@dataclass(frozen=True)
class DualCRLBResult:
    var_alpha: float
    var_Rx: float
    cov_alpha_Rx: float
    rmse_alpha: float
    rmse_Rx: float
    rmse_alpha_pct: float
    rmse_Rx_pct: float
    fim: np.ndarray
    sigma_i_t_sq: float


def crlb_dualchannel(
    alpha: float,
    Rx: float,
    omega: float = 2.0 * np.pi * F0,
    *,
    snr_i_db: float,
    v_phase: float = V_PHASE,
    ns: int = NS,
    h_alpha: float = H_ALPHA_DEFAULT,
    h_Rx_rel: float = H_RX_RELATIVE,
) -> DualCRLBResult:
    """Joint dual-channel CRLB on (alpha, R_x) for one cell.

    Note: V channel has zero contribution to F_dual under the ideal-
    source assumption (dv_clean/dtheta = 0), so ``snr_v_db`` does
    not appear in the result; only ``snr_i_db`` matters.
    """
    H_at = H_model(alpha, Rx, omega)
    dH_da, dH_dR = _dH_dtheta(
        alpha, Rx, omega, h_alpha=h_alpha, h_Rx_rel=h_Rx_rel
    )

    # Time-domain noise variance on i(t)
    rms_i_clean = abs(H_at * v_phase) / np.sqrt(2.0)
    if not np.isfinite(snr_i_db):
        sigma_i_t_sq = np.finfo(float).tiny
    else:
        sigma_i_t_sq = rms_i_clean ** 2 / (10.0 ** (snr_i_db / 10.0))

    if sigma_i_t_sq <= 0:
        sigma_i_t_sq = np.finfo(float).tiny

    # F_kl = (Ns/2) V_phase^2 / sigma_i_t^2 * Re(dH_k^* dH_l)
    pref = (ns / 2.0) * (v_phase ** 2) / sigma_i_t_sq
    F = np.zeros((2, 2))
    grads = (dH_da, dH_dR)
    for k in range(2):
        for l_ in range(2):
            F[k, l_] = pref * (
                grads[k].real * grads[l_].real
                + grads[k].imag * grads[l_].imag
            )

    try:
        cov = np.linalg.inv(F)
    except np.linalg.LinAlgError:
        cov = np.full((2, 2), np.nan)

    var_a = float(cov[0, 0])
    var_R = float(cov[1, 1])
    rmse_a = float(np.sqrt(max(var_a, 0.0)))
    rmse_R = float(np.sqrt(max(var_R, 0.0)))

    return DualCRLBResult(
        var_alpha=var_a,
        var_Rx=var_R,
        cov_alpha_Rx=float(cov[0, 1]),
        rmse_alpha=rmse_a,
        rmse_Rx=rmse_R,
        rmse_alpha_pct=100.0 * rmse_a / alpha,
        rmse_Rx_pct=100.0 * rmse_R / Rx,
        fim=F,
        sigma_i_t_sq=float(sigma_i_t_sq),
    )
