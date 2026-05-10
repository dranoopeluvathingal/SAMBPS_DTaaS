r"""faultloc_analytical_gradients.py
=======================================

Closed-form $\partial H/\partial\alpha$ and $\partial H/\partial R_x$
for the distributed-parameter forward model from
``models.faultloc_distributed_param_model`` (P2.1).  Replaces the
central-finite-difference partials currently used by the optimiser
(``inverse_estimation/faultloc_two_stage_optimiser``) and the FIM
constructions (``inverse_estimation/faultloc_crlb_proper`` /
``faultloc_crlb_dualchannel``).

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP2.2  This module.
    WP2.4  Phase-2 swaps the central-FD gradient inside the optimiser
           for the closed-form one here.

Recipe
------

Let $L$ be the feeder length (km), $\gamma = \sqrt{z y}$,
$Z_c = \sqrt{z/y}$ (with $z = R' + j\omega L'$, $y = G' + j\omega C'$).
The cascaded ABCD chain is

    T = T_1(\alpha) \cdot T_f(R_x) \cdot T_2(\alpha) \cdot T_{\text{load}}

with T_1, T_2 the distributed-parameter blocks of length $\alpha L$
and $(1-\alpha) L$, $T_f = [[1, 0], [1/R_x, 1]]$ and
$T_{\text{load}} = [[1, 0], [1/R_{\text{load}}, 1]]$.  The
sending-end admittance is

    H(\alpha, R_x) = C_{\text{end}} / A_{\text{end}}

where $A_{\text{end}}, C_{\text{end}}$ are entries (1,1) and (2,1) of
$T$.

Partials of $T_1$ and $T_2$ w.r.t. $\alpha$
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

$\frac{d}{d\alpha} \cosh(\gamma \alpha L) = \gamma L \sinh(\gamma \alpha L)$
and $\frac{d}{d\alpha} \sinh(\gamma \alpha L) = \gamma L \cosh(\gamma \alpha L)$.
The chain-rule sign flips for $T_2$ because its argument is
$\gamma (1 - \alpha) L$:

$\partial T_1 / \partial\alpha =
   \gamma L
   \begin{bmatrix}
     \sinh(\gamma \alpha L)         & Z_c \cosh(\gamma \alpha L)\\
     \cosh(\gamma \alpha L) / Z_c   & \sinh(\gamma \alpha L)
   \end{bmatrix}$

$\partial T_2 / \partial\alpha =
   -\gamma L
   \begin{bmatrix}
     \sinh(\gamma (1-\alpha) L)         & Z_c \cosh(\gamma (1-\alpha) L)\\
     \cosh(\gamma (1-\alpha) L) / Z_c   & \sinh(\gamma (1-\alpha) L)
   \end{bmatrix}$

Partials of $T_f$ w.r.t. $R_x$
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

$\partial T_f / \partial R_x = [[0, 0], [-1/R_x^2, 0]]$.

Chain rule for the cascaded product
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let $T = T_a T_b T_c T_d$.  Then for any parameter $\theta$:

    $\partial T / \partial \theta
       = (\partial T_a / \partial \theta) T_b T_c T_d
       + T_a (\partial T_b / \partial \theta) T_c T_d
       + T_a T_b (\partial T_c / \partial \theta) T_d
       + T_a T_b T_c (\partial T_d / \partial \theta)$.

For $\theta = \alpha$: only $T_1$ and $T_2$ depend on $\alpha$
(2 of 4 terms above); $T_f, T_{\text{load}}$ are constant.

For $\theta = R_x$: only $T_f$ depends on $R_x$ (1 of 4 terms);
$T_1, T_2, T_{\text{load}}$ are constant in $R_x$.

Sending-end admittance partial
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

$H = C_{\text{end}} / A_{\text{end}}$, so by the quotient rule:

    $\partial H / \partial \theta
        = (\partial C_{\text{end}}/\partial\theta \cdot A_{\text{end}}
           - C_{\text{end}} \cdot \partial A_{\text{end}}/\partial\theta)
          / A_{\text{end}}^2$.

Public API
----------

    dH_dalpha(alpha, Rx, omega, **kwargs) -> complex
    dH_dRx   (alpha, Rx, omega, **kwargs) -> complex
    dH_dtheta(alpha, Rx, omega, **kwargs)
        -> tuple[complex, complex]   # (dH_dalpha, dH_dRx) packed
"""

from __future__ import annotations

import numpy as np
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    C_PER_KM,
    G_PER_KM,
    L_PER_KM,
    LINE_LENGTH_KM,
    R_LOAD,
    R_PER_KM,
    _line_constants,
)


def _block(gamma: complex, Z_c: complex, length_km: float) -> tuple[np.ndarray, np.ndarray]:
    r"""Return (T, dT_d{length}) for a uniform line block.

    T(L) = [[cosh(gL), Z_c sinh(gL)], [sinh(gL)/Z_c, cosh(gL)]]

    dT/dL = gamma * [[sinh(gL), Z_c cosh(gL)],
                     [cosh(gL)/Z_c, sinh(gL)]]
    """
    gL = gamma * length_km
    ch, sh = np.cosh(gL), np.sinh(gL)
    T = np.array([[ch, Z_c * sh], [sh / Z_c, ch]], dtype=complex)
    dT_dL = gamma * np.array([[sh, Z_c * ch], [ch / Z_c, sh]], dtype=complex)
    return T, dT_dL


def _shunt(Y: complex) -> np.ndarray:
    return np.array([[1.0 + 0j, 0.0 + 0j], [Y, 1.0 + 0j]])


def _all_blocks(
    alpha: float, Rx: float, omega: float,
    *, line_length_km: float, R_per_km: float, L_per_km: float,
    C_per_km: float, G_per_km: float, R_load: float,
):
    """Compute (T1, T2, Tf, Tload, dT1/dα, dT2/dα, dTf/dRx)."""
    gamma, Z_c = _line_constants(omega, R_per_km, L_per_km, C_per_km, G_per_km)
    L1 = alpha * line_length_km
    L2 = (1.0 - alpha) * line_length_km
    T1, dT1_dL1 = _block(gamma, Z_c, L1)
    T2, dT2_dL2 = _block(gamma, Z_c, L2)
    Tf = _shunt(1.0 / Rx)
    Tload = _shunt(1.0 / R_load)
    # ∂L1/∂α = +line_length_km;  ∂L2/∂α = -line_length_km
    dT1_dalpha = dT1_dL1 * line_length_km
    dT2_dalpha = dT2_dL2 * (-line_length_km)
    dTf_dRx = np.array([[0.0 + 0j, 0.0 + 0j], [-1.0 / (Rx ** 2), 0.0 + 0j]])
    return T1, T2, Tf, Tload, dT1_dalpha, dT2_dalpha, dTf_dRx


def _quotient_rule_partial(
    T_end_A: complex, T_end_C: complex,
    dT_end_A: complex, dT_end_C: complex,
) -> complex:
    return (dT_end_C * T_end_A - T_end_C * dT_end_A) / (T_end_A ** 2)


def dH_dalpha(
    alpha: float, Rx: float, omega: float,
    *, line_length_km: float = LINE_LENGTH_KM,
    R_per_km: float = R_PER_KM, L_per_km: float = L_PER_KM,
    C_per_km: float = C_PER_KM, G_per_km: float = G_PER_KM,
    R_load: float = R_LOAD,
) -> complex:
    T1, T2, Tf, Tload, dT1_da, dT2_da, _ = _all_blocks(
        alpha, Rx, omega,
        line_length_km=line_length_km,
        R_per_km=R_per_km, L_per_km=L_per_km,
        C_per_km=C_per_km, G_per_km=G_per_km, R_load=R_load,
    )
    # T_end = T1 . Tf . T2 . Tload
    T_end = T1 @ Tf @ T2 @ Tload
    # ∂T_end/∂α = ∂T1/∂α . Tf . T2 . Tload + T1 . Tf . ∂T2/∂α . Tload
    dT_end = (dT1_da @ Tf @ T2 @ Tload
              + T1 @ Tf @ dT2_da @ Tload)
    return complex(_quotient_rule_partial(
        T_end[0, 0], T_end[1, 0],
        dT_end[0, 0], dT_end[1, 0],
    ))


def dH_dRx(
    alpha: float, Rx: float, omega: float,
    *, line_length_km: float = LINE_LENGTH_KM,
    R_per_km: float = R_PER_KM, L_per_km: float = L_PER_KM,
    C_per_km: float = C_PER_KM, G_per_km: float = G_PER_KM,
    R_load: float = R_LOAD,
) -> complex:
    T1, T2, Tf, Tload, _, _, dTf_dR = _all_blocks(
        alpha, Rx, omega,
        line_length_km=line_length_km,
        R_per_km=R_per_km, L_per_km=L_per_km,
        C_per_km=C_per_km, G_per_km=G_per_km, R_load=R_load,
    )
    T_end = T1 @ Tf @ T2 @ Tload
    # ∂T_end/∂Rx = T1 . ∂Tf/∂Rx . T2 . Tload  (only Tf depends on Rx)
    dT_end = T1 @ dTf_dR @ T2 @ Tload
    return complex(_quotient_rule_partial(
        T_end[0, 0], T_end[1, 0],
        dT_end[0, 0], dT_end[1, 0],
    ))


def dH_dtheta(
    alpha: float, Rx: float, omega: float, **kwargs
) -> tuple[complex, complex]:
    """Convenience: returns (dH_dalpha, dH_dRx) computed in a single
    block-evaluation pass to amortise the cosh/sinh calls."""
    T1, T2, Tf, Tload, dT1_da, dT2_da, dTf_dR = _all_blocks(
        alpha, Rx, omega,
        line_length_km=kwargs.pop("line_length_km", LINE_LENGTH_KM),
        R_per_km=kwargs.pop("R_per_km", R_PER_KM),
        L_per_km=kwargs.pop("L_per_km", L_PER_KM),
        C_per_km=kwargs.pop("C_per_km", C_PER_KM),
        G_per_km=kwargs.pop("G_per_km", G_PER_KM),
        R_load=kwargs.pop("R_load", R_LOAD),
    )
    T_end = T1 @ Tf @ T2 @ Tload
    dT_end_da = (dT1_da @ Tf @ T2 @ Tload
                 + T1 @ Tf @ dT2_da @ Tload)
    dT_end_dR = T1 @ dTf_dR @ T2 @ Tload
    dH_da = _quotient_rule_partial(
        T_end[0, 0], T_end[1, 0], dT_end_da[0, 0], dT_end_da[1, 0]
    )
    dH_dR = _quotient_rule_partial(
        T_end[0, 0], T_end[1, 0], dT_end_dR[0, 0], dT_end_dR[1, 0]
    )
    return complex(dH_da), complex(dH_dR)
