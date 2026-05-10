r"""faultloc_crlb_proper.py
============================

Proper-complex-Gaussian-ratio Cramér-Rao bound for the SAMBPS DTaaS
HIF-TF locator (WP1.6, closes R1 + R9).

Closes the most consequential audit finding of v2/v3:
``manuscript_v2.tex`` §V-B specifies dual-channel AWGN on V and I,
ratioed to form ``H_meas = I_bin / V_bin``.  The §VIII Fisher
information matrix in the v1 manuscript was computed under a
*circular complex Gaussian* noise model directly on ``H_meas``,
which is **not** the correct density.  ``H_meas`` is the ratio of
two independent complex Gaussians, whose true density is the
Marsaglia--Nadarajah--Pogány form.  At high signal-to-noise on V
(Geary--Hinkley regime) the ratio is well-approximated by a
*proper complex Gaussian with a SIGNAL-DEPENDENT variance*

    sigma_H^2  =  ( sigma_I^2  +  |H|^2 * sigma_V^2 ) / |V_phasor|^2

(per real/imag), where ``|H|^2 sigma_V^2`` is the "ratio-shot" term
that the v1 ``Gaussian-on-H'' linearisation drops.  This module
implements the FIM under that proper density, plus the
Geary--Hinkley validity flag that gates the high-SNR Gaussian
approximation.

References
----------
* Kuruoğlu, E. E. (2018). Cram\'er--Rao bounds under the
  proper-complex-Gaussian-ratio density.  ASCE J.\ Eng.\ Mech.\
  144(9), \texttt{04018068}.
* Marsaglia, G. (1965; 2006).  Ratios of normal variables.
  J.\ Amer.\ Statist.\ Assoc.\ 60(309); J.\ Statist.\ Software 16(4).
* Nadarajah, S. \& Pog\'any, T.\,K. (2018).  On the distribution of
  the product / ratio of two correlated complex Gaussian random
  variables.  IEEE Trans.\ Signal Process.\ 66(11).
* Geary, R.\,C. (1930) and Hinkley, D.\,V. (1969).  On the ratio of
  two correlated normal variables.

WP-trace
--------
* WP1.6   This module + ``faultloc_crlb_dualchannel.py``.
* WP2.2   Phase-2 swaps the central-FD partials below for the
          closed-form symbolic ones from
          ``inverse_estimation/faultloc_analytical_gradients`` (when
          the Python port lands).

Public API
----------

    crlb_proper(alpha, Rx, omega, *, snr_v_db, snr_i_db,
                v_phase=V_PHASE, ns=NS) -> CRLBResult

    geary_hinkley_valid(snr_v_db, *, threshold=4.0) -> bool

The threshold defaults to 4 (i.e. |V_phasor| > 4 sigma_V), which
corresponds to SNR_V >= ~12 dB on the underlying time-domain channel
after the one-cycle Ns=200 single-bin DFT averages by sqrt(Ns/2).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sambp_fault_location_id.models.faultloc_pi_section_model import H_model

# Defaults mirror models.faultloc_pi_section_model and
# tools.pscad_surrogate.
V_PHASE = 11000.0 / np.sqrt(3.0) * np.sqrt(2.0)   # peak of V at the bus
F0 = 50.0
FS = 10000.0
NS = 200

# Default FD step for partials (matches the optimiser).
H_ALPHA_DEFAULT = 1.0e-4
H_RX_RELATIVE = 1.0e-4

# Geary--Hinkley validity threshold:
# require |V_phasor| / sigma_V_bin > THRESHOLD.
GH_THRESHOLD = 4.0


@dataclass(frozen=True)
class CRLBResult:
    """One cell's CRLB report under the proper-ratio density.

    ``var_*`` are the diagonal of the inverse FIM, in the natural
    units of the parameter (``alpha`` is dimensionless, ``Rx`` is in
    ohm).  ``rmse_*`` are sqrt of those (units sqrt unit), and
    ``rmse_*_pct`` express them as percent of the true value (so they
    are directly comparable with the empirical loc_err_pct /
    Rx_err_pct from P1.5).
    """

    var_alpha: float
    var_Rx: float
    cov_alpha_Rx: float
    rmse_alpha: float
    rmse_Rx: float
    rmse_alpha_pct: float
    rmse_Rx_pct: float
    geary_hinkley_valid: bool
    sigma_H_sq: float
    fim: np.ndarray   # 2 x 2


# ---------------------------------------------------------------------------
# Numerical partials d H / d theta via central finite differences
# ---------------------------------------------------------------------------
def _dH_dtheta(
    alpha: float, Rx: float, omega: float,
    *, h_alpha: float = H_ALPHA_DEFAULT, h_Rx_rel: float = H_RX_RELATIVE,
) -> tuple[complex, complex]:
    """Central-FD partials at (alpha, Rx).  WP2.2 will swap for closed form."""
    H_a_p = H_model(alpha + h_alpha, Rx, omega)
    H_a_m = H_model(alpha - h_alpha, Rx, omega)
    dH_da = (H_a_p - H_a_m) / (2.0 * h_alpha)
    h_Rx = h_Rx_rel * Rx
    H_R_p = H_model(alpha, Rx + h_Rx, omega)
    H_R_m = H_model(alpha, Rx - h_Rx, omega)
    dH_dR = (H_R_p - H_R_m) / (2.0 * h_Rx)
    return dH_da, dH_dR


# ---------------------------------------------------------------------------
# Noise variance translation: time-domain dB <-> single-bin DFT variance
# ---------------------------------------------------------------------------
def _sigma_bin_per_component(rms_clean: float, snr_db: float, ns: int) -> float:
    """Variance of Re(X_bin) (and Im(X_bin)) for a single-bin DFT of
    a length-ns signal whose underlying time-domain noise variance
    is sigma_t^2 = rms_clean^2 / 10^(SNR/10)."""
    if not np.isfinite(snr_db):
        return 0.0
    sigma_t_sq = rms_clean ** 2 / (10.0 ** (snr_db / 10.0))
    return 2.0 * sigma_t_sq / ns   # variance per real/imag component


def crlb_proper(
    alpha: float,
    Rx: float,
    omega: float = 2.0 * np.pi * F0,
    *,
    snr_v_db: float,
    snr_i_db: float,
    v_phase: float = V_PHASE,
    ns: int = NS,
) -> CRLBResult:
    """Proper-ratio CRLB on (alpha, Rx) for one cell.

    Σ_H (per real/imag of H_meas) =
        ( sigma_I^2  +  |H|^2 * sigma_V^2 ) / |V_phase|^2

    F_kl = (1 / sigma_H^2) * Re( (dH/dtheta_k)^* (dH/dtheta_l) )

    CRLB(theta_k) = (F^-1)_{kk}.
    """
    H_at = H_model(alpha, Rx, omega)
    dH_da, dH_dR = _dH_dtheta(alpha, Rx, omega)

    # rms_clean for V is V_phase (ideal cos source); for I it is |H| * V_phase
    rms_v_clean = abs(v_phase) / np.sqrt(2.0)
    rms_i_clean = abs(H_at * v_phase) / np.sqrt(2.0)

    # Variance per real/imag component in the single-bin DFT
    sig_V_sq = _sigma_bin_per_component(rms_v_clean, snr_v_db, ns)
    sig_I_sq = _sigma_bin_per_component(rms_i_clean, snr_i_db, ns)

    sigma_H_sq = (sig_I_sq + abs(H_at) ** 2 * sig_V_sq) / abs(v_phase) ** 2

    if sigma_H_sq <= 0.0:
        # Both channels noiseless -> bound is zero (degenerate)
        sigma_H_sq = np.finfo(float).tiny

    # Build 2x2 FIM
    F = np.zeros((2, 2))
    grads = (dH_da, dH_dR)
    for k in range(2):
        for l_ in range(2):
            F[k, l_] = (1.0 / sigma_H_sq) * (
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

    # Geary-Hinkley validity: |V_phase| / sigma_V_bin > GH_THRESHOLD
    sig_V = float(np.sqrt(sig_V_sq)) if sig_V_sq > 0 else 0.0
    gh_valid = (
        not np.isfinite(snr_v_db) or sig_V == 0.0
        or (abs(v_phase) / sig_V) > GH_THRESHOLD
    )

    return CRLBResult(
        var_alpha=var_a,
        var_Rx=var_R,
        cov_alpha_Rx=float(cov[0, 1]),
        rmse_alpha=rmse_a,
        rmse_Rx=rmse_R,
        rmse_alpha_pct=100.0 * rmse_a / alpha,
        rmse_Rx_pct=100.0 * rmse_R / Rx,
        geary_hinkley_valid=gh_valid,
        sigma_H_sq=float(sigma_H_sq),
        fim=F,
    )


def geary_hinkley_valid(
    snr_v_db: float,
    *,
    v_phase: float = V_PHASE,
    ns: int = NS,
    threshold: float = GH_THRESHOLD,
) -> bool:
    """Standalone GH check on the V-channel SNR."""
    if not np.isfinite(snr_v_db):
        return True
    rms_v_clean = abs(v_phase) / np.sqrt(2.0)
    sig_V_sq = _sigma_bin_per_component(rms_v_clean, snr_v_db, ns)
    if sig_V_sq <= 0:
        return True
    return bool((abs(v_phase) / float(np.sqrt(sig_V_sq))) > threshold)
