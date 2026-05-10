"""
faultloc_three_phase_model.py
==============================
Closed-form three-phase distributed-parameter Y_send(j*omega_0; alpha,
R_x) for the SAMBPS-DTaaS Fault-Location Identification project.
Extends the WP2.1 single-phase distributed model to three phases under
the symmetric (transposed) line approximation.

WP3.1 implementation (status this commit, P3.1).  The previous
WP3.1 SKELETON (commit ac1e77ef) is REPLACED by a proper 6x6 ABCD
formulation.

Physical model
--------------

Per-unit-length series-impedance and shunt-admittance matrices follow
the symmetric-coupling form
::

    Z'_abc(j*omega) = Z'_s I_3 + Z'_m (J_3 - I_3)
    Y'_abc(j*omega) = Y'_s I_3 + Y'_m (J_3 - I_3)

where I_3 is the 3x3 identity, J_3 is the 3x3 all-ones matrix, and
Z'_s, Z'_m, Y'_s, Y'_m are scalar self / mutual per-unit-length
quantities.  The symmetric form corresponds to a fully transposed
line; untransposed Carson coupling lands at WP3.2 once the IEEE 13 /
34 / 123 line-code geometries are wired in.

The state vector x(x_pos) = [V(x_pos); I(x_pos)] (six elements at any
position 0 <= x_pos <= L from the sender) satisfies the telegraph PDE
::

    d/dx_pos [V; I] = [[0,  -Z'], [-Y',  0]] [V; I]   =:  M_pde [V; I]

so the sender-to-receiver relation is [V_r; I_r] = expm(L * M_pde) [V_s; I_s];
inverting gives the canonical ABCD form
::

    [V_s; I_s] = T_line(L) [V_r; I_r],
        T_line(L) = expm(L * (-M_pde)) = expm(L * [[0, +Z'], [+Y',  0]]).

In the single-phase limit Z' = z, Y' = y, this reduces to
T_line(L) = [[cosh(gamma L), Z_c sinh(gamma L)],
             [sinh(gamma L)/Z_c, cosh(gamma L)]],
exactly matching the WP2.1 ABCD block in
``faultloc_distributed_param_model.py``.

Single-line-to-ground (SLG) HIF
--------------------------------

A shunt admittance Y_f = 1/R_x is inserted on the faulted phase
(default phase A) at distance alpha from the sender; the other two
phases see no fault contribution.  The fault is a 6x6 ABCD
::

    T_f = [[I_3, 0_3], [Y_f_abc, I_3]],
        Y_f_abc = diag(1/R_x, 0, 0)        (SLG-on-A; phase index 0).

The full chain is
::

    T_total(alpha, R_x, L) = T_line(alpha L) * T_f * T_line((1-alpha) L) * T_load

with T_load = [[I_3, 0_3], [(1/R_load) I_3, I_3]] modelling the
remote open-far-end as a high-resistance shunt to ground (default
R_load = 1 MOhm, matching the WP2.1 single-phase boundary condition).

Sending-end admittance matrix
------------------------------

Y_send is the 3x3 complex matrix that the IED actually sees, defined
by I_s = Y_send V_s with [V_s; I_s] = T_total [V_far; I_far_open=0]:
::

    Y_send = T_total[3:, :3] @ inv(T_total[:3, :3]).

This is a direct three-phase generalisation of H_send = C/A from the
single-phase WP2.1 case.

Typical 11 kV overhead distribution-line parameters
----------------------------------------------------

The defaults below match the canonical Saha 2010 single-phase values
on the diagonal (so the 3-phase model reduces to the WP2.1 model in
the no-coupling limit) with mutual-to-self ratios drawn from typical
horizontal 11 kV three-conductor configurations after Kron reduction:
::

    R'_s = 0.0728 Ohm/km     (Saha 2010, Springer Table 3.1)
    L'_s = 0.927 mH/km       (Saha 2010, Springer Table 3.1)
    C'_s = 11.6  nF/km       (Saha 2010, Springer Table 3.1)
    G'_s = 0     S/km

    R'_m = 0.05 * R'_s       (typical resistive coupling, ~5 %)
    L'_m = 0.40 * L'_s       (typical inductive coupling, ~40 %)
    C'_m = 0.30 * C'_s       (typical capacitive coupling, ~30 %)
    G'_m = 0     S/km

The 0.40 / 0.30 mutual-to-self ratios are representative of an 11 kV
horizontal-flat-array overhead line (Kersting 2002, Table 4.1, IEEE
13-node line code 601, after rounding) and converge correctly to a
standard symmetric-component decomposition with positive-sequence
parameters Z_1 = Z_s - Z_m and zero-sequence Z_0 = Z_s + 2 Z_m.

References
----------

* Saha, M.M., Izykowski, J., Rosolowski, E., "Fault Location on Power
  Networks", Springer, 2010.  See in particular Ch. 3 on the 3-phase
  Bergeron model and Appendix B on per-unit-length parameter typical
  values.  (Bib key: ``Saha2010BookFL``.)
* Kang, T. et al., "Closed-form fully distributed-parameter line
  model for time-domain fault location on radial distribution
  feeders", Electric Power Systems Research, 2021.
  DOI 10.1016/j.epsr.2021.107497 ; pii S0378779621006039.
* Kersting, W.H., "Distribution System Modelling and Analysis", 2nd
  ed., CRC Press, 2002 -- Tables 4.1 and 4.2 for IEEE PES test-feeder
  per-unit-length impedance matrices (line codes 601-607).
* IEEE PES Test Feeder Working Group, IEEE 13- / 34- / 123-node test
  feeders, 2010 (revised).

Public API
----------

* ``Z_abc_per_km(omega)`` -> ndarray (3, 3) complex
* ``Y_abc_per_km(omega)`` -> ndarray (3, 3) complex
* ``line_ABCD(length_km, omega)`` -> ndarray (6, 6) complex
* ``fault_ABCD(Rx, fault_phase=0)`` -> ndarray (6, 6) complex
* ``Y_send(alpha, Rx, omega, *, ...)`` -> ndarray (3, 3) complex

Backward-compat aliases for the WP3.1-skeleton callers:

* ``H_phase(omega, alpha, Rx, ...)`` returns ``np.diag(Y_send(...))``.
* ``build_Y_abc(alpha, Rx, omega, ...)`` returns ``Y_send(...)``.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import expm

# --- Per-unit-length parameters at f0 = 50 Hz -------------------------------
# Diagonal values from Saha 2010 Springer Table 3.1; mutual ratios
# typical of horizontal 11 kV flat-array overhead with three phase
# conductors (Kersting 2002 line code 601, post-Kron-reduction
# averaged to enforce the transposed-line approximation).
R_S_OHM_PER_KM = 0.0728
L_S_H_PER_KM = 0.927e-3
C_S_F_PER_KM = 11.6e-9
G_S_S_PER_KM = 0.0

MUTUAL_R_OVER_SELF = 0.05
MUTUAL_L_OVER_SELF = 0.40
MUTUAL_C_OVER_SELF = 0.30
MUTUAL_G_OVER_SELF = 0.0

R_M_OHM_PER_KM = MUTUAL_R_OVER_SELF * R_S_OHM_PER_KM
L_M_H_PER_KM = MUTUAL_L_OVER_SELF * L_S_H_PER_KM
C_M_F_PER_KM = MUTUAL_C_OVER_SELF * C_S_F_PER_KM
G_M_S_PER_KM = MUTUAL_G_OVER_SELF * G_S_S_PER_KM

# Backward-compat re-export for the WP3.1 SKELETON callers.
MUTUAL_OVER_SELF_RATIO = MUTUAL_L_OVER_SELF

DEFAULT_LINE_LENGTH_KM = 100.0
DEFAULT_R_LOAD_OHM = 1.0e6


def _symmetric_3x3(self_value: complex, mutual_value: complex) -> np.ndarray:
    """Build a 3x3 symmetric matrix M = self * I_3 + mutual * (J_3 - I_3)."""
    M = np.full((3, 3), mutual_value, dtype=complex)
    np.fill_diagonal(M, self_value)
    return M


def Z_abc_per_km(omega: float) -> np.ndarray:
    """3x3 series impedance per km at angular frequency omega."""
    z_s = R_S_OHM_PER_KM + 1j * omega * L_S_H_PER_KM
    z_m = R_M_OHM_PER_KM + 1j * omega * L_M_H_PER_KM
    return _symmetric_3x3(z_s, z_m)


def Y_abc_per_km(omega: float) -> np.ndarray:
    """3x3 shunt admittance per km at angular frequency omega."""
    y_s = G_S_S_PER_KM + 1j * omega * C_S_F_PER_KM
    y_m = G_M_S_PER_KM + 1j * omega * C_M_F_PER_KM
    return _symmetric_3x3(y_s, y_m)


def line_ABCD(length_km: float, omega: float) -> np.ndarray:
    """6x6 ABCD matrix for a uniform 3-phase line of length L:
    [V_s; I_s] = T(L) [V_r; I_r].

    Computed as expm(L * [[0, +Z'], [+Y', 0]]).  Reduces to the
    standard cosh/sinh ABCD in the single-phase limit; reduces to the
    sequence-domain decoupled bound (positive / negative / zero) under
    the symmetric-line assumption used here.
    """
    Z = Z_abc_per_km(omega)
    Y = Y_abc_per_km(omega)
    M = np.zeros((6, 6), dtype=complex)
    M[:3, 3:] = Z
    M[3:, :3] = Y
    return expm(length_km * M)


def fault_ABCD(Rx: float, fault_phase: int = 0) -> np.ndarray:
    """6x6 ABCD for an SLG fault: shunt admittance Y_f = 1/R_x on
    `fault_phase` (default 0 = phase A).  T_f = [[I_3, 0_3], [Y_f, I_3]]
    going from downstream (receiver side) to upstream (sender side).
    """
    if not 0 <= fault_phase <= 2:
        raise ValueError(f"fault_phase must be 0, 1, or 2; got {fault_phase}")
    Y_f = np.zeros((3, 3), dtype=complex)
    Y_f[fault_phase, fault_phase] = 1.0 / Rx
    T = np.eye(6, dtype=complex)
    T[3:, :3] = Y_f
    return T


def _load_ABCD(R_load_ohm: float) -> np.ndarray:
    """6x6 ABCD for a far-end shunt load Y_load = (1/R_load) * I_3 to
    ground.  Matches the open-far-end boundary condition of the WP2.1
    single-phase model in the R_load -> infinity limit.
    """
    Y_load = np.eye(3, dtype=complex) / R_load_ohm
    T = np.eye(6, dtype=complex)
    T[3:, :3] = Y_load
    return T


def Y_send(
    alpha: float,
    Rx: float,
    omega: float,
    *,
    line_length_km: float = DEFAULT_LINE_LENGTH_KM,
    R_load_ohm: float = DEFAULT_R_LOAD_OHM,
    fault_phase: int = 0,
) -> np.ndarray:
    """3x3 sending-end admittance matrix at angular frequency omega for
    an SLG-HIF fault on `fault_phase` at per-unit position `alpha` with
    arc resistance `Rx`.

    Parameters
    ----------
    alpha : float in (0, 1)
        Per-unit fault position from the sender.
    Rx : float, ohms
        HIF arc resistance.  Smaller Rx = harder fault; for `Rx -> inf`
        the model recovers the no-fault baseline (verified in tests).
    omega : float
        Angular frequency, rad/s.  At 50 Hz this is 2*pi*50.
    line_length_km : float
        Total line length, km.  Default 100.
    R_load_ohm : float
        Open-far-end shunt load to ground (high R for "open").
    fault_phase : int in {0, 1, 2}
        Which phase carries the SLG fault.  Default 0 (phase A).

    Returns
    -------
    Y_send : ndarray (3, 3) complex
        Sending-end admittance matrix; I_s = Y_send * V_s.

    Raises
    ------
    ValueError if alpha not in (0, 1) or fault_phase not in {0, 1, 2}.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")
    if Rx <= 0.0:
        raise ValueError(f"Rx must be > 0; got {Rx}")

    L = line_length_km
    T1 = line_ABCD(alpha * L, omega)
    Tf = fault_ABCD(Rx, fault_phase=fault_phase)
    T2 = line_ABCD((1.0 - alpha) * L, omega)
    T_load = _load_ABCD(R_load_ohm)

    T = T1 @ Tf @ T2 @ T_load
    T_VV = T[:3, :3]
    T_IV = T[3:, :3]
    return T_IV @ np.linalg.inv(T_VV)


def Y_send_grid(
    alphas: np.ndarray,
    Rxs: np.ndarray,
    omega: float,
    *,
    line_length_km: float = DEFAULT_LINE_LENGTH_KM,
    R_load_ohm: float = DEFAULT_R_LOAD_OHM,
    fault_phase: int = 0,
) -> np.ndarray:
    """Vectorised grid evaluation of Y_send across (alpha, R_x) pairs.

    Returns ndarray of shape (len(alphas), len(Rxs), 3, 3) complex.
    """
    a = np.asarray(alphas, dtype=float)
    R = np.asarray(Rxs, dtype=float)
    out = np.zeros((a.size, R.size, 3, 3), dtype=complex)
    for i, av in enumerate(a):
        for j, rv in enumerate(R):
            out[i, j] = Y_send(
                float(av), float(rv), omega,
                line_length_km=line_length_km,
                R_load_ohm=R_load_ohm,
                fault_phase=fault_phase,
            )
    return out


# --- Backward-compat shims for WP3.1 SKELETON callers ----------------------
# The skeleton API exposed H_phase(omega, alpha, Rx, ...) returning a
# 3-vector and build_Y_abc(alpha, Rx, omega, ...) returning the full
# 3x3.  Keep these names alive so WP3.1-skeleton tests + the IEEE
# feeders module continue to import cleanly.

def H_phase(
    omega: float,
    alpha: float,
    Rx: float,
    *,
    fault_phase: int = 0,
    line_length_km: float = DEFAULT_LINE_LENGTH_KM,
) -> np.ndarray:
    """Diagonal of Y_send: the per-phase self-admittance vector.

    Note: this is a strict subset of the information in Y_send.  The
    WP3.5 / WP3.6 multi-port FIM consumes the full Y_send matrix
    (including off-diagonals) to break the single-bin DFT
    identifiability degeneracy.
    """
    return np.diag(
        Y_send(
            alpha, Rx, omega,
            fault_phase=fault_phase,
            line_length_km=line_length_km,
        )
    ).copy()


def build_Y_abc(
    alpha: float,
    Rx: float,
    omega: float,
    *,
    line_length_km: float = DEFAULT_LINE_LENGTH_KM,
    fault_phase: int = 0,
) -> np.ndarray:
    """Backward-compat alias for :func:`Y_send`."""
    return Y_send(
        alpha, Rx, omega,
        fault_phase=fault_phase,
        line_length_km=line_length_km,
    )


__all__ = [
    "Z_abc_per_km",
    "Y_abc_per_km",
    "line_ABCD",
    "fault_ABCD",
    "Y_send",
    "Y_send_grid",
    "H_phase",
    "build_Y_abc",
    "R_S_OHM_PER_KM",
    "L_S_H_PER_KM",
    "C_S_F_PER_KM",
    "G_S_S_PER_KM",
    "R_M_OHM_PER_KM",
    "L_M_H_PER_KM",
    "C_M_F_PER_KM",
    "G_M_S_PER_KM",
    "MUTUAL_R_OVER_SELF",
    "MUTUAL_L_OVER_SELF",
    "MUTUAL_C_OVER_SELF",
    "MUTUAL_OVER_SELF_RATIO",
    "DEFAULT_LINE_LENGTH_KM",
    "DEFAULT_R_LOAD_OHM",
]
