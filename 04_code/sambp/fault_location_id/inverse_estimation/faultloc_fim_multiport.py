r"""faultloc_fim_multiport.py
==============================
Multi-port Fisher Information Matrix for the SAMBPS-DTaaS Fault-
Location Identification project.  Generalises the single-port CRLB
(``faultloc_crlb_proper.py`` + ``faultloc_crlb_dualchannel.py``,
WP1.6 / P1.6) to the 3-phase case where the IED's observation is the
3 x 3 sending-end admittance matrix Y_send rather than a single
complex H bin.

WP3.6 (P3.6) implementation.

Why multi-port matters
----------------------

The single-port CRLB derivation in P1.6 is just-determined: 1 complex
bin = 2 real measurements vs 2 real unknowns ``(alpha, R_x)``.  In
the 3-phase case the IED measures Y_send (3 x 3 complex; 9 complex
entries = 18 real values) and the same 2 unknowns underlie all 18
observations.  The problem is over-determined by a factor of 9, so
identifiability is structurally much stronger -- the Fisher
information accumulates across all observed entries:
::

    F = sum over (p, q) entries of   (1 / sigma_Y[p,q]^2) *
        Re[ (dY_pq / dtheta_k)^* (dY_pq / dtheta_l) ]

where the per-entry variance ``sigma_Y[p,q]^2`` follows the WP1.6
proper-complex-Gaussian-ratio form (Geary-Hinkley regime):
::

    sigma_Y[p,q]^2 = ( sigma_I[p]^2 + |Y_pq|^2 * sigma_V[q]^2 ) /
                       |V_phase[q]|^2.

Public API
----------

* ``crlb_multiport_proper(network, fault_bus, alpha, Rx, omega, *,
  snr_v_db, snr_i_db, observation='full', v_phase, ns)`` ->
  ``MultiPortCRLBResult``.

* ``crlb_multiport_dual(network, fault_bus, alpha, Rx, omega, *,
  snr_v_db, snr_i_db, observation='full', v_phase, ns)`` ->
  ``MultiPortCRLBResult``.

* ``observation`` selects which Y_send entries are observed:
    'full'      -- all 9 entries (18 real)
    'upper'     -- 6 upper-triangle entries (12 real)
    'diagonal'  -- 3 diagonal entries (6 real)

* ``crlb_consistency_ratio(proper, dual)`` -> per-cell ratio of
  proper to dual rmse on alpha.  At SNR_I >= 40 dB and V noiseless
  the ratio approaches 1.

Mathematical notes
------------------

The dual-channel form (Nehorai-Hawkes 2000 in waveform space,
projected onto theta) is exactly the same Jacobian-weighted FIM but
with prefactor ``(N_s / 2) * |V_phase|^2 / sigma_I_t^2`` summed over
current channels.  When ``sigma_V -> 0`` (V noiseless) the proper-
ratio sigma_Y^2 reduces to ``sigma_I_bin^2 / |V_phase|^2`` and
``sigma_I_bin^2 = (2 / N_s) * sigma_I_t^2``, so the two FIMs agree
exactly -- the per-cell consistency test asserts this.

References
----------

* Kuruoğlu, E.E., "CRBs Under the Proper-Complex-Gaussian-Ratio
  Density: Applications to Single-Bin Admittance Estimation",
  ASCE-ASME J. Risk and Uncertainty Engineering, 2018 (single-port
  origin; bib key ``Kuruoglu2018ASCE``).
* Nehorai, A. and Hawkes, M., "Performance Bounds for Estimating
  Vector Systems", IEEE Trans. Signal Processing, 48(6), 2000
  (multi-channel projection theorem; bib key ``NehoraiHawkes2000``).
* See ``docs/AppendixB_correctedCRLB.tex`` Sect. B.5 for the
  WP3.6 derivation specialised to ``Y_send`` observations.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

OMEGA = 2.0 * np.pi * 50.0
F0 = 50.0
NS = 200
V_PHASE = 11_000.0 / np.sqrt(3.0)   # 11 kV LL phase-to-ground RMS
GH_THRESHOLD = 4.0

H_ALPHA_DEFAULT = 1.0e-5
H_RX_RELATIVE = 1.0e-3


@dataclass(frozen=True)
class MultiPortCRLBResult:
    """Multi-port CRLB report on (alpha, R_x) for one cell."""

    var_alpha: float
    var_Rx: float
    cov_alpha_Rx: float
    rmse_alpha: float
    rmse_Rx: float
    rmse_alpha_pct: float
    rmse_Rx_pct: float
    fim: np.ndarray              # 2 x 2
    n_observations: int          # number of stacked real obs (e.g., 18)
    observation_kind: str        # 'full' / 'upper' / 'diagonal'
    geary_hinkley_valid: bool


# ---------------------------------------------------------------------------
# Numerical Y_send Jacobian via central finite differences
# ---------------------------------------------------------------------------
def _dY_send_dtheta(
    network,
    fault_bus: str,
    alpha: float,
    Rx: float,
    omega: float,
    *,
    fault_type: str = "SLG",
    fault_phase: int = 0,
    h_alpha: float = H_ALPHA_DEFAULT,
    h_Rx_rel: float = H_RX_RELATIVE,
) -> tuple[np.ndarray, np.ndarray]:
    """Central-FD partials of Y_send (3, 3) complex w.r.t. (alpha, R_x)."""
    Y_p = network.Y_send(
        omega, fault_bus=fault_bus, alpha=alpha + h_alpha, Rx=Rx,
        fault_phase=fault_phase, fault_type=fault_type,
    )
    Y_m = network.Y_send(
        omega, fault_bus=fault_bus, alpha=alpha - h_alpha, Rx=Rx,
        fault_phase=fault_phase, fault_type=fault_type,
    )
    dY_da = (Y_p - Y_m) / (2.0 * h_alpha)
    h_Rx = h_Rx_rel * Rx
    Y_p = network.Y_send(
        omega, fault_bus=fault_bus, alpha=alpha, Rx=Rx + h_Rx,
        fault_phase=fault_phase, fault_type=fault_type,
    )
    Y_m = network.Y_send(
        omega, fault_bus=fault_bus, alpha=alpha, Rx=Rx - h_Rx,
        fault_phase=fault_phase, fault_type=fault_type,
    )
    dY_dR = (Y_p - Y_m) / (2.0 * h_Rx)
    return dY_da, dY_dR


def _entry_indices(observation: str) -> list[tuple[int, int]]:
    """Return the (row, col) indices of Y_send entries to include."""
    if observation == "full":
        return [(p, q) for p in range(3) for q in range(3)]
    if observation == "upper":
        return [(p, q) for p in range(3) for q in range(3) if p <= q]
    if observation == "diagonal":
        return [(p, p) for p in range(3)]
    raise ValueError(
        f"observation must be one of 'full' / 'upper' / 'diagonal'; "
        f"got {observation!r}"
    )


def _sigma_bin_per_component(rms_clean: float, snr_db: float, ns: int) -> float:
    """Variance of Re/Im of single-bin DFT (matches WP1.6 helper)."""
    if not np.isfinite(snr_db):
        return 0.0
    sigma_t_sq = rms_clean ** 2 / (10.0 ** (snr_db / 10.0))
    return 2.0 * sigma_t_sq / ns


def _build_fim_proper(
    Y_send: np.ndarray,
    dY_da: np.ndarray, dY_dR: np.ndarray,
    *,
    snr_v_db: float, snr_i_db: float,
    v_phase: float, ns: int,
    indices: list[tuple[int, int]],
) -> np.ndarray:
    """2 x 2 multi-port proper-ratio FIM."""
    sig_V_sq = _sigma_bin_per_component(v_phase / np.sqrt(2.0), snr_v_db, ns)
    F = np.zeros((2, 2))
    for p, q in indices:
        Y_pq = Y_send[p, q]
        rms_i_clean = abs(Y_pq) * v_phase / np.sqrt(2.0)
        sig_I_sq = _sigma_bin_per_component(rms_i_clean, snr_i_db, ns)
        sigma_Y_sq = (sig_I_sq + abs(Y_pq) ** 2 * sig_V_sq) / v_phase ** 2
        if sigma_Y_sq <= 0.0:
            sigma_Y_sq = np.finfo(float).tiny
        grads = (dY_da[p, q], dY_dR[p, q])
        for r in range(2):
            for c in range(2):
                F[r, c] += (1.0 / sigma_Y_sq) * (
                    grads[r].real * grads[c].real
                    + grads[r].imag * grads[c].imag
                )
    return F


def _build_fim_dual(
    Y_send: np.ndarray,
    dY_da: np.ndarray, dY_dR: np.ndarray,
    *,
    snr_i_db: float,
    v_phase: float, ns: int,
    indices: list[tuple[int, int]],
) -> np.ndarray:
    """2 x 2 multi-port dual-channel FIM in V_abc / I_abc waveform space.

    The per-(p, q) contribution is
    ``(N_s / 2) * |V_phase|^2 / sigma_I_pq_t^2 *
      Re[(dY_pq/dtheta_k)^* (dY_pq/dtheta_l)]``,
    where the per-entry time-domain noise is matched to the proper-
    ratio per-entry rms_clean = |Y_pq| * V_phase so the consistency
    test at sigma_V = 0 holds entry-by-entry.
    """
    if not np.isfinite(snr_i_db):
        return np.full((2, 2), np.inf)
    F = np.zeros((2, 2))
    for p, q in indices:
        Y_pq = Y_send[p, q]
        rms_i_clean = abs(Y_pq) * v_phase / np.sqrt(2.0)
        sigma_I_t_sq = rms_i_clean ** 2 / (10.0 ** (snr_i_db / 10.0))
        if sigma_I_t_sq <= 0.0:
            continue
        prefactor = (ns / 2.0) * (v_phase ** 2) / sigma_I_t_sq
        grads = (dY_da[p, q], dY_dR[p, q])
        for r in range(2):
            for c in range(2):
                F[r, c] += prefactor * (
                    grads[r].real * grads[c].real
                    + grads[r].imag * grads[c].imag
                )
    return F


def _result_from_fim(
    F: np.ndarray,
    *,
    alpha: float, Rx: float,
    n_observations: int,
    observation_kind: str,
    snr_v_db: float, v_phase: float, ns: int,
) -> MultiPortCRLBResult:
    try:
        cov = np.linalg.inv(F)
    except np.linalg.LinAlgError:
        cov = np.full((2, 2), np.nan)
    var_a = float(cov[0, 0])
    var_R = float(cov[1, 1])
    rmse_a = float(np.sqrt(max(var_a, 0.0)))
    rmse_R = float(np.sqrt(max(var_R, 0.0)))
    sig_V_sq = _sigma_bin_per_component(v_phase / np.sqrt(2.0), snr_v_db, ns)
    sig_V = float(np.sqrt(sig_V_sq)) if sig_V_sq > 0 else 0.0
    gh_valid = (
        not np.isfinite(snr_v_db) or sig_V == 0.0
        or (v_phase / sig_V) > GH_THRESHOLD
    )
    return MultiPortCRLBResult(
        var_alpha=var_a,
        var_Rx=var_R,
        cov_alpha_Rx=float(cov[0, 1]),
        rmse_alpha=rmse_a,
        rmse_Rx=rmse_R,
        rmse_alpha_pct=100.0 * rmse_a / alpha,
        rmse_Rx_pct=100.0 * rmse_R / Rx,
        fim=F,
        n_observations=n_observations,
        observation_kind=observation_kind,
        geary_hinkley_valid=gh_valid,
    )


def crlb_multiport_proper(
    network,
    fault_bus: str,
    alpha: float,
    Rx: float,
    omega: float = OMEGA,
    *,
    snr_v_db: float = float("inf"),
    snr_i_db: float,
    v_phase: float = V_PHASE,
    ns: int = NS,
    observation: str = "full",
    fault_type: str = "SLG",
    fault_phase: int = 0,
) -> MultiPortCRLBResult:
    """Multi-port proper-complex-Gaussian-ratio CRLB on (alpha, R_x)."""
    indices = _entry_indices(observation)
    Y = network.Y_send(
        omega, fault_bus=fault_bus, alpha=alpha, Rx=Rx,
        fault_phase=fault_phase, fault_type=fault_type,
    )
    dY_da, dY_dR = _dY_send_dtheta(
        network, fault_bus, alpha, Rx, omega,
        fault_type=fault_type, fault_phase=fault_phase,
    )
    F = _build_fim_proper(
        Y, dY_da, dY_dR,
        snr_v_db=snr_v_db, snr_i_db=snr_i_db,
        v_phase=v_phase, ns=ns,
        indices=indices,
    )
    n_real_obs = 2 * len(indices)
    return _result_from_fim(
        F, alpha=alpha, Rx=Rx,
        n_observations=n_real_obs,
        observation_kind=observation,
        snr_v_db=snr_v_db, v_phase=v_phase, ns=ns,
    )


def crlb_multiport_dual(
    network,
    fault_bus: str,
    alpha: float,
    Rx: float,
    omega: float = OMEGA,
    *,
    snr_v_db: float = float("inf"),
    snr_i_db: float,
    v_phase: float = V_PHASE,
    ns: int = NS,
    observation: str = "full",
    fault_type: str = "SLG",
    fault_phase: int = 0,
) -> MultiPortCRLBResult:
    """Multi-port joint dual-channel FIM in V_abc / I_abc waveform space."""
    indices = _entry_indices(observation)
    Y = network.Y_send(
        omega, fault_bus=fault_bus, alpha=alpha, Rx=Rx,
        fault_phase=fault_phase, fault_type=fault_type,
    )
    dY_da, dY_dR = _dY_send_dtheta(
        network, fault_bus, alpha, Rx, omega,
        fault_type=fault_type, fault_phase=fault_phase,
    )
    F = _build_fim_dual(
        Y, dY_da, dY_dR,
        snr_i_db=snr_i_db,
        v_phase=v_phase, ns=ns,
        indices=indices,
    )
    n_real_obs = 2 * len(indices)
    return _result_from_fim(
        F, alpha=alpha, Rx=Rx,
        n_observations=n_real_obs,
        observation_kind=observation,
        snr_v_db=snr_v_db, v_phase=v_phase, ns=ns,
    )


def crlb_consistency_ratio(
    proper: MultiPortCRLBResult,
    dual: MultiPortCRLBResult,
) -> float:
    """Per-cell ratio rmse_alpha(proper) / rmse_alpha(dual).  Approaches
    1.0 at SNR_I >= 40 dB with V noiseless (per the WP3.6 brief)."""
    if dual.rmse_alpha <= 0.0:
        return float("inf")
    return proper.rmse_alpha / dual.rmse_alpha


__all__ = [
    "MultiPortCRLBResult",
    "OMEGA",
    "F0",
    "NS",
    "V_PHASE",
    "crlb_multiport_proper",
    "crlb_multiport_dual",
    "crlb_consistency_ratio",
]
