"""
faultloc_three_phase_model.py
==============================
Three-phase Y_abc admittance model for the SAMBP Fault-Location
Identification project.  Generalises the single-phase 2-section pi-model
(faultloc_pi_section_model.py) and the closed-form distributed-parameter
formulation (faultloc_distributed_param_model.py) to a 3-port admittance
matrix Y_abc(j*omega_0).

WP3.1 SKELETON (status this commit).  Implements:

    * Per-phase distributed-parameter 2x2 ABCD blocks reusing the WP2.1
      single-phase formulation per phase, with a Carson-style 3x3 series
      impedance Z_abc and a 3x3 shunt admittance Y_abc derived from the
      single-phase per-unit-length parameters scaled by the symmetric
      mutual-coupling factor in `_carson_coupling()`.
    * Modal (Karrenbauer) decoupling so the 3x3 ABCD chain can be
      evaluated as three decoupled scalar ABCD chains in modal space.
    * Single-line-to-ground (SLG) HIF insertion at per-unit position
      alpha on phase A by default; phase selection via `fault_phase`.

Out of scope for this skeleton (closes at WP3.2 / WP3.3 / WP3.4):

    - Laterals, tap loads, distributed generators (WP3.2).
    - IEEE 13- / 34- / 123-node feeders (WP3.3 -- hooks live in
      faultloc_ieee_feeders.py).
    - LL / LLG / 3PH fault types (WP3.4 -- only SLG is wired up here).

Public API
----------

    build_Y_abc(alpha, Rx, omega, *, line_length_km=100.0)
        -> ndarray (3, 3) complex

    H_phase(omega, alpha, Rx, *, fault_phase=0, line_length_km=100.0)
        -> ndarray (3,) complex

References
----------

    [Carson1926]   Carson, J. R. "Wave propagation in overhead wires
                   with ground return." Bell System Technical Journal,
                   5 (4) 1926.
    [Saha2010]     Saha, M.M., Izykowski, J., Rosolowski, E. "Fault
                   Location on Power Networks." Springer, 2010.
                   (cf. references.bib :: Saha2010BookFL)
    [Lopes2023]    Lopes, F.V. et al. "Distributed-parameter modelling
                   for fault location on radial distribution feeders."
                   EPSR 224 (2023) 109678.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP3.1  Generalise state-space to 3-port admittance Y_abc.
           THIS MODULE.
    WP3.2  Add laterals, tap loads, >= 1 distributed generator.
    WP3.3  Build IEEE 13- / 34- / 123-node feeder digital twins
           (`faultloc_ieee_feeders.py`).
    WP3.4  Add SLG / LL / LLG fault types in addition to SLG-HIF.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# --- Per-unit-length parameters for the canonical 11 kV / 100 km line ----
# Same Saha 2010 Table 3.1 values used by the single-phase WP2.1 model.
R_PRIME_OHM_PER_KM = 0.0728
L_PRIME_H_PER_KM = 0.927e-3
C_PRIME_F_PER_KM = 11.6e-9
G_PRIME_S_PER_KM = 0.0


# --- Mutual-coupling parameters (Carson, fully symmetric placeholder) ----
# A full Carson derivation needs conductor geometry (height, spacing,
# soil resistivity) -- those become inputs in WP3.2 once IEEE feeder
# data lands.  For the WP3.1 skeleton we use a typical mutual / self
# ratio of 0.40 (close to the IEEE 4-node test feeder asymmetry post-
# Kron reduction).
MUTUAL_OVER_SELF_RATIO = 0.40


@dataclass(frozen=True)
class ThreePhaseLineParams:
    """Container for the per-unit-length series + shunt matrices."""

    Z_abc_per_km: np.ndarray  # 3x3 complex, ohms / km at f0
    Y_abc_per_km: np.ndarray  # 3x3 complex, siemens / km at f0
    line_length_km: float


def _carson_coupling(omega: float) -> tuple[np.ndarray, np.ndarray]:
    """Build the 3x3 per-unit-length Z_abc, Y_abc matrices for a fully
    symmetric three-phase line.  Off-diagonal magnitudes are
    `MUTUAL_OVER_SELF_RATIO * Z_self`; WP3.2 replaces this with
    conductor-geometry-driven Carson's equations.
    """
    z_self = R_PRIME_OHM_PER_KM + 1j * omega * L_PRIME_H_PER_KM
    z_mutual = MUTUAL_OVER_SELF_RATIO * z_self
    Z = np.full((3, 3), z_mutual, dtype=complex)
    np.fill_diagonal(Z, z_self)

    y_self = G_PRIME_S_PER_KM + 1j * omega * C_PRIME_F_PER_KM
    y_mutual = MUTUAL_OVER_SELF_RATIO * y_self
    Y = np.full((3, 3), y_mutual, dtype=complex)
    np.fill_diagonal(Y, y_self)
    return Z, Y


def _karrenbauer() -> np.ndarray:
    """Return the 3x3 Karrenbauer modal-transform matrix.  Symmetric
    transposes give the inverse mapping; suitable when Z and Y are
    fully symmetric (the WP3.1-skeleton placeholder coupling above).
    WP3.2 will switch to a Clarke or eigen-modal transform when Carson
    breaks the symmetry.
    """
    return np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, -2.0],
        ]
    ) / np.sqrt(3.0)


def _modal_propagation_constants(
    Z_per_km: np.ndarray, Y_per_km: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return the three modal (gamma_m, Z_c_m) pairs after Karrenbauer
    decoupling.  For the WP3.1 fully-symmetric placeholder the modal
    Z and Y are the eigenvalues of Z_abc and Y_abc.
    """
    eig_Z = np.linalg.eigvals(Z_per_km)
    eig_Y = np.linalg.eigvals(Y_per_km)
    gamma = np.sqrt(eig_Z * eig_Y)
    Z_c = np.sqrt(eig_Z / eig_Y)
    return gamma, Z_c


def _abcd_block(gamma_L: complex, Z_c: complex) -> np.ndarray:
    """Standard distributed 2x2 ABCD for a uniform line section."""
    ch = np.cosh(gamma_L)
    sh = np.sinh(gamma_L)
    return np.array([[ch, Z_c * sh], [sh / Z_c, ch]], dtype=complex)


def _modal_H(
    alpha: float,
    Rx: float,
    omega: float,
    *,
    line_length_km: float,
    R_load_ohm: float = 1.0e6,
) -> np.ndarray:
    """Compute the three modal sending-end admittances H_m(j*omega) for
    a fault inserted at per-unit position alpha on the corresponding
    modal channel.  Mode 0 carries the SLG signature; modes 1 and 2 are
    the inter-phase modes which an SLG fault excites only weakly.

    This is the building block consumed by H_phase().
    """
    Z_per_km, Y_per_km = _carson_coupling(omega)
    gammas, Zcs = _modal_propagation_constants(Z_per_km, Y_per_km)

    L = line_length_km
    H = np.zeros(3, dtype=complex)
    for m in range(3):
        T1 = _abcd_block(gammas[m] * alpha * L, Zcs[m])
        T2 = _abcd_block(gammas[m] * (1.0 - alpha) * L, Zcs[m])
        # Fault shunt only on mode 0 for SLG (mode-0 = zero-sequence
        # current path); modes 1 and 2 see no fault contribution.
        if m == 0:
            T_f = np.array([[1.0, 0.0], [1.0 / Rx, 1.0]], dtype=complex)
        else:
            T_f = np.eye(2, dtype=complex)
        T_load = np.array([[1.0, 0.0], [1.0 / R_load_ohm, 1.0]], dtype=complex)
        T = T1 @ T_f @ T2 @ T_load
        H[m] = T[1, 0] / T[0, 0]
    return H


def H_phase(
    omega: float,
    alpha: float,
    Rx: float,
    *,
    fault_phase: int = 0,
    line_length_km: float = 100.0,
) -> np.ndarray:
    """Phase-to-source admittance vector at f0 for an SLG-HIF fault on
    `fault_phase` at per-unit position `alpha` with arc resistance `Rx`.

    Returns shape (3,) complex; element k is Y_kk_phase = I_k / V_k at
    the sending end.

    This is the WP3.1 skeleton-grade implementation; WP3.4 generalises
    `fault_type` to {SLG, LL, LLG, 3PH}.
    """
    if fault_phase != 0:
        raise NotImplementedError(
            "fault_phase != 0 lands at WP3.4; SLG-on-A is the WP3.1 default."
        )
    K = _karrenbauer()
    Kinv = np.linalg.inv(K)
    H_modal = _modal_H(alpha, Rx, omega, line_length_km=line_length_km)
    H_modal_diag = np.diag(H_modal)
    H_phase_mat = K @ H_modal_diag @ Kinv
    return np.diagonal(H_phase_mat).copy()


def build_Y_abc(
    alpha: float,
    Rx: float,
    omega: float,
    *,
    line_length_km: float = 100.0,
) -> np.ndarray:
    """Full 3x3 Y_abc(j*omega_0) at the sending end.  Diagonal entries
    are the self-admittances H_phase(); off-diagonals are the mutual
    admittance contributions from the SLG fault leaking into the
    healthy phases through the symmetric coupling matrix.

    WP3.1 skeleton: the off-diagonals are populated as
    `MUTUAL_OVER_SELF_RATIO * H_self` so the matrix has the right shape
    and order of magnitude for downstream 3-port FIM construction
    (WP3.6).  WP3.2 replaces this with the proper Carson-derived
    mutual-admittance evaluation.
    """
    H_phases = H_phase(omega, alpha, Rx, line_length_km=line_length_km)
    Y = np.full((3, 3), 0.0 + 0j, dtype=complex)
    for k in range(3):
        Y[k, k] = H_phases[k]
        for j in range(3):
            if j != k:
                Y[k, j] = MUTUAL_OVER_SELF_RATIO * H_phases[k]
    return Y


__all__ = [
    "ThreePhaseLineParams",
    "build_Y_abc",
    "H_phase",
    "R_PRIME_OHM_PER_KM",
    "L_PRIME_H_PER_KM",
    "C_PRIME_F_PER_KM",
    "G_PRIME_S_PER_KM",
    "MUTUAL_OVER_SELF_RATIO",
]
