r"""faultloc_distributed_param_model.py
==========================================

Closed-form distributed-parameter admittance
$H(j\omega_0; \alpha, R_x)$ for the SAMBPS DTaaS HIF-TF locator.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP2.1  Closed-form distributed-parameter forward model.  Replaces
           the cascaded-Gamma 2-section approximation of
           ``faultloc_pi_section_model.py`` for the WP2.4 optimiser
           swap (analytic gradients land in ``faultloc_analytical_gradients.py``).
    WP2.2  ``dH/dalpha`` and ``dH/dR_x`` derived analytically by
           differentiating the cosh/sinh expressions below
           (Phase-2 follow-on; this module ships the forward model).

Mathematical recipe (v3 plan §3.7; brief literal)
-------------------------------------------------

The 100 km feeder is split at the per-unit fault location $\alpha$
into two cascaded distributed-parameter blocks of lengths
$\ell_1 = \alpha L$ and $\ell_2 = (1 - \alpha) L$ with
$L = 100$ km.  The fault is inserted as a shunt admittance
$Y_f = 1/R_x$ at the joint.

1. Per-unit-length series impedance and shunt admittance:
   $z = R' + j\omega_0 L'$, $y = G' + j\omega_0 C'$.
2. Propagation constant and characteristic impedance:
   $\gamma = \sqrt{z\,y}$, $Z_c = \sqrt{z/y}$.
3. ABCD matrix of a uniform distributed line of length $\ell$:
   $$
   T(\ell) =
   \begin{bmatrix}
     \cosh(\gamma\ell)         & Z_c \sinh(\gamma\ell)\\
     \sinh(\gamma\ell)/Z_c     & \cosh(\gamma\ell)
   \end{bmatrix}.
   $$
4. Fault as a shunt admittance:
   $T_f = \begin{bmatrix} 1 & 0 \\ Y_f & 1 \end{bmatrix}$ with $Y_f = 1/R_x$.
5. Total ABCD: $T = T_1 \cdot T_f \cdot T_2$ with
   $T_1 = T(\alpha L)$ and $T_2 = T((1 - \alpha) L)$.
6. Boundary condition: the remote terminal is loaded by
   $R_{\text{load}} = 1$ M$\Omega$ (mirrors the
   ``faultloc_pi_section_model.py`` topology and §V-B of the parent
   manuscript), captured as a shunt $T_{\text{load}} =
   \begin{bmatrix}1 & 0 \\ 1/R_{\text{load}} & 1\end{bmatrix}$.
   The far end is then open: $I_{\text{far}} = 0$.

   Under those boundary conditions, with $T_{\text{end}} = T \cdot
   T_{\text{load}}$ relating sending-end $(V_s, I_s)$ to far-end
   $(V_{\text{far}}, I_{\text{far}}) = (V_{\text{far}}, 0)$:
   $V_s = A_{\text{end}} V_{\text{far}}$ and
   $I_s = C_{\text{end}} V_{\text{far}}$, so the source-end
   admittance is

   $$
   H(j\omega_0; \alpha, R_x) \;=\; \frac{I_s}{V_s}
       \;=\; \frac{C_{\text{end}}}{A_{\text{end}}}.
   $$

References
----------
* Lopes, F. V. and Trew, A. and Liu, Y. (2023).  Distributed-
  parameter closed-form transfer function for single-ended HIF
  location on distribution feeders.  EPSR 223, 109637.
  ScienceDirect S0142061523004155.
* Trew, A. (2023).  Closed-form distributed-parameter fault location
  with hyperbolic-block cascading.  arXiv:2310.13359.
* Kang, N. (2021).  Distributed-parameter line model for fault
  location in distribution networks.  EPSR.
  ScienceDirect S0378779621006039.
* Pozar, D. M. (2012).  Microwave Engineering, 4th ed., Ch. 4
  (Wiley).  Two-port ABCD parameters and cascaded-network analysis.

Public API
----------
    H_distributed(alpha, Rx, omega, *, line_length_km=100.0,
                  R_per_km=0.0728, L_per_km=0.927e-3,
                  C_per_km=11.6e-9, G_per_km=0.0,
                  R_load=1e6) -> complex

    H_distributed_grid(alphas, Rxs, omega, **kwargs)
        -> ndarray (n_alpha, n_Rx) complex

The grid form is fully vectorised across (alpha, R_x) using numpy
broadcasting on the 2x2 ABCD entries; runtime is dominated by the
:math:`\cosh / \sinh / \exp` calls, which are themselves vectorised.
"""

from __future__ import annotations

import numpy as np

# Mirror of models/faultloc_pi_section_model.py
R_PER_KM = 0.0728
L_PER_KM = 0.927e-3
C_PER_KM = 11.6e-9
G_PER_KM = 0.0
LINE_LENGTH_KM = 100.0
R_LOAD = 1.0e6


def _line_constants(omega: float, R_per_km: float, L_per_km: float,
                    C_per_km: float, G_per_km: float) -> tuple[complex, complex]:
    """Return (gamma, Z_c) for the per-unit-length R, L, C, G."""
    z = R_per_km + 1j * omega * L_per_km
    y = G_per_km + 1j * omega * C_per_km
    gamma = np.sqrt(z * y)
    Z_c = np.sqrt(z / y)
    return complex(gamma), complex(Z_c)


def H_distributed(
    alpha: float,
    Rx: float,
    omega: float,
    *,
    line_length_km: float = LINE_LENGTH_KM,
    R_per_km: float = R_PER_KM,
    L_per_km: float = L_PER_KM,
    C_per_km: float = C_PER_KM,
    G_per_km: float = G_PER_KM,
    R_load: float = R_LOAD,
) -> complex:
    """Single-cell closed-form distributed-parameter admittance.

    Returns ``H = I_s / V_s`` at angular frequency ``omega``, with the
    fault as a shunt ``Y_f = 1 / R_x`` at the per-unit location
    ``alpha`` and the far end loaded by ``R_load`` (then open).
    """
    gamma, Z_c = _line_constants(omega, R_per_km, L_per_km, C_per_km, G_per_km)
    L1 = alpha * line_length_km
    L2 = (1.0 - alpha) * line_length_km
    gL1 = gamma * L1
    gL2 = gamma * L2

    # ABCD blocks
    ch1, sh1 = np.cosh(gL1), np.sinh(gL1)
    ch2, sh2 = np.cosh(gL2), np.sinh(gL2)
    T1 = np.array([[ch1, Z_c * sh1], [sh1 / Z_c, ch1]], dtype=complex)
    T2 = np.array([[ch2, Z_c * sh2], [sh2 / Z_c, ch2]], dtype=complex)
    Tf = np.array([[1.0 + 0j, 0.0 + 0j], [1.0 / Rx, 1.0 + 0j]])
    Tl = np.array([[1.0 + 0j, 0.0 + 0j], [1.0 / R_load, 1.0 + 0j]])

    T_end = T1 @ Tf @ T2 @ Tl
    return complex(T_end[1, 0] / T_end[0, 0])


def H_distributed_grid(
    alphas: np.ndarray,
    Rxs: np.ndarray,
    omega: float,
    *,
    line_length_km: float = LINE_LENGTH_KM,
    R_per_km: float = R_PER_KM,
    L_per_km: float = L_PER_KM,
    C_per_km: float = C_PER_KM,
    G_per_km: float = G_PER_KM,
    R_load: float = R_LOAD,
) -> np.ndarray:
    """Vectorised: (n_alpha, n_Rx) complex admittance grid.

    The inner ABCD entries are scalars per (alpha, R_x) pair but
    have a 2x2 structure; we build the 4 entries A, B, C, D as
    (n_alpha, n_Rx) arrays and avoid an explicit Python loop.
    """
    gamma, Z_c = _line_constants(omega, R_per_km, L_per_km, C_per_km, G_per_km)
    aa = np.asarray(alphas, dtype=float).reshape(-1, 1)        # (n_alpha, 1)
    RR = np.asarray(Rxs, dtype=float).reshape(1, -1)           # (1, n_Rx)
    Yf = 1.0 / RR                                               # (1, n_Rx)
    Yl = 1.0 / R_load                                           # scalar

    L1 = aa * line_length_km
    L2 = (1.0 - aa) * line_length_km
    gL1 = gamma * L1
    gL2 = gamma * L2

    ch1, sh1 = np.cosh(gL1), np.sinh(gL1)        # (n_alpha, 1)
    ch2, sh2 = np.cosh(gL2), np.sinh(gL2)
    A1, B1, C1, D1 = ch1, Z_c * sh1, sh1 / Z_c, ch1
    A2, B2, C2, D2 = ch2, Z_c * sh2, sh2 / Z_c, ch2

    # T_f: [[1, 0], [Yf, 1]]
    # T_int = T1 @ T_f
    A_int = A1 + B1 * Yf
    B_int = B1
    C_int = C1 + D1 * Yf
    D_int = D1
    # T_mid = T_int @ T_2
    A_mid = A_int * A2 + B_int * C2
    B_mid = A_int * B2 + B_int * D2
    C_mid = C_int * A2 + D_int * C2
    D_mid = C_int * B2 + D_int * D2
    # T_end = T_mid @ T_load (T_load = [[1,0],[Yl,1]])
    A_end = A_mid + B_mid * Yl
    C_end = C_mid + D_mid * Yl
    return C_end / A_end


def magnitude_phase_error(
    H_a: complex | np.ndarray, H_b: complex | np.ndarray
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """Per-element relative magnitude error (%) and absolute phase error (deg)."""
    mag_err_pct = 100.0 * np.abs(np.abs(H_a) - np.abs(H_b)) / np.abs(H_b)
    phase_err_deg = np.degrees(np.abs(np.angle(H_a) - np.angle(H_b)))
    # wrap to (-180, 180]
    phase_err_deg = np.minimum(phase_err_deg, 360.0 - phase_err_deg)
    return mag_err_pct, phase_err_deg
