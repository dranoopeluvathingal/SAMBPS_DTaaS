"""
faultloc_pi_section_model.py
=============================
Cascaded-Gamma two-section pi-model state-space for the SAMBP
Fault-Location Identification project (HIF-TF locator).

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP0.5  Appendix A: annotated pi-circuit + KVL/KCL -> state-space
           (A, B, C, D) and symbolic dH/dalpha, dH/dRx.
    WP3.4  Single-phase HIF baseline before generalisation to 3-phase
           (faultloc_three_phase_model.py).

Physical model
--------------
11 kV / 100 km feeder split at fault location alpha in (0, 1) with a
single HIF shunt R_x at the split node.  Cascaded-Gamma convention:
each section's series R-L is upstream of a shunt capacitance lumped at
the section's downstream node.  See docs/AppendixA_derivation.tex for
the full KVL/KCL derivation.

Per-unit-length parameters (SI):
    R_per_km = 0.0728   ohm/km        Saha 2010, Springer
    L_per_km = 0.927e-3 H/km          (= 92.7 mH / 100 km)
    C_per_km = 11.6e-9  F/km          (= 1.16 uF / 100 km)

State vector x = [V_C1, V_C2, I_L1, I_L2]^T :
    V_C1   voltage at the fault node (downstream node of section 1)
    V_C2   voltage at the remote-end node (downstream node of section 2)
    I_L1   current entering section 1 at the source end
    I_L2   current entering section 2 at the fault node

Input  u = V_source(t) ;  output y = I_source(t) = I_L1.

The structural property A[0, 0] = -1/(R_x * C_1) is continuously
differentiable in both alpha and R_x; this is what the WP2.2 closed-
form gradient builds on.  A self-consistency check between this Python
implementation and the MATLAB faultloc_pi_state_space.m is the subject
of tests/test_pi_model_python_vs_matlab.py (WP0.5 acceptance).

Public API
----------
    build_pi_state_space(alpha, Rx, *, line_length_km=100.0,
                         R_per_km=0.0728, L_per_km=0.927e-3,
                         C_per_km=11.6e-9, R_load=1e6)
        -> (A, B, C, D)

    H_model(alpha, Rx, omega, **kwargs)
        -> complex   single-frequency transfer function I_source / V_source
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Per-km defaults (Saha 2010; see Appendix A.6 dimensional check)
R_PER_KM = 0.0728     # ohm/km
L_PER_KM = 0.927e-3   # H/km
C_PER_KM = 11.6e-9    # F/km
LINE_LENGTH_KM = 100.0
R_LOAD = 1.0e6        # remote-bus shunt; 1 Mohm = effectively open


@dataclass(frozen=True)
class StateSpace:
    """Standard (A, B, C, D) state-space tuple."""

    A: np.ndarray
    B: np.ndarray
    C: np.ndarray
    D: float


def build_pi_state_space(
    alpha: float,
    Rx: float,
    *,
    line_length_km: float = LINE_LENGTH_KM,
    R_per_km: float = R_PER_KM,
    L_per_km: float = L_PER_KM,
    C_per_km: float = C_PER_KM,
    R_load: float = R_LOAD,
) -> StateSpace:
    """Build the 4x4 state-space for the two-section cascaded-Gamma model.

    Parameters
    ----------
    alpha
        Per-unit fault location, in (0, 1).
    Rx
        HIF arc resistance at the fault node, in ohm.
    line_length_km
        Total feeder length in km (default 100).
    R_per_km, L_per_km, C_per_km
        Per-km line parameters (Saha 2010 lumped-line convention).
    R_load
        Remote-bus shunt resistance in ohm (default 1e6 ~= open).

    Returns
    -------
    StateSpace(A, B, C, D)
    """
    L1_km = alpha * line_length_km
    L2_km = (1.0 - alpha) * line_length_km

    R1 = R_per_km * L1_km
    X1 = L_per_km * L1_km
    C1 = C_per_km * L1_km
    R2 = R_per_km * L2_km
    X2 = L_per_km * L2_km
    C2 = C_per_km * L2_km

    A = np.array(
        [
            [-1.0 / (Rx * C1),       0.0,                 1.0 / C1, -1.0 / C1],
            [0.0,                    -1.0 / (R_load * C2), 0.0,      1.0 / C2],
            [-1.0 / X1,              0.0,                 -R1 / X1,  0.0],
            [1.0 / X2,               -1.0 / X2,           0.0,      -R2 / X2],
        ],
        dtype=float,
    )
    B = np.array([0.0, 0.0, 1.0 / X1, 0.0], dtype=float)
    C = np.array([0.0, 0.0, 1.0, 0.0], dtype=float)
    D = 0.0
    return StateSpace(A=A, B=B, C=C, D=D)


def H_model(
    alpha: float,
    Rx: float,
    omega: float,
    **kwargs,
) -> complex:
    """Compute the single-frequency transfer function H(j*omega; alpha, Rx).

        H(j*omega) = C (j*omega I - A)^{-1} B + D

    Returns the complex admittance I_source / V_source at the requested
    angular frequency.
    """
    ss = build_pi_state_space(alpha, Rx, **kwargs)
    n = ss.A.shape[0]
    M = 1j * omega * np.eye(n) - ss.A
    x = np.linalg.solve(M, ss.B.astype(complex))
    return complex(ss.C @ x + ss.D)


def H_grid(
    alphas: np.ndarray,
    Rxs: np.ndarray,
    omega: float,
    **kwargs,
) -> np.ndarray:
    """Vectorised wrapper. Returns an (n_alpha, n_Rx) complex array."""
    out = np.empty((len(alphas), len(Rxs)), dtype=complex)
    for i, a in enumerate(alphas):
        for j, R in enumerate(Rxs):
            out[i, j] = H_model(float(a), float(R), omega, **kwargs)
    return out
