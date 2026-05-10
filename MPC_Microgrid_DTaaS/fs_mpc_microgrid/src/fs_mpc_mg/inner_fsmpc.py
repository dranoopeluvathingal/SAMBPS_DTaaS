"""Finite-set MPC inner current controller.

Implements Eqs. (4) and (6) of Perez & Flores-Bahamonde (2016):

    i_m_pred(k+1) = (1 - r*Ts/L) * i_m(k) + (Ts/L) * (v_s(k) - M*s*v_dc(k))     (4)

    g(s) = sum_{phase} ( i_m_pred - i_s_ref + i_l )^2                            (6)

with s ranging over the 8 candidate switching vectors. The vector that minimises
g(s) is applied at the next sample. A 1-step delay-compensation predictor (k+2)
is provided as `predict_with_delay_comp` and recommended for accurate operation
when T_s is comparable to the L/r time constant.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .plant import M_MATRIX, SWITCHING_VECTORS


@dataclass
class FSMPCParams:
    """Inner-loop FS-MPC parameters."""

    L: float = 1e-3       # filter inductance (H), must match plant
    r: float = 50e-3      # parasitic resistance (ohm)
    T_s: float = 20e-6    # control sample time (s)
    use_delay_compensation: bool = True


class FSMPCController:
    """Finite-set model predictive current controller.

    Usage:
        ctrl = FSMPCController(params)
        s = ctrl.update(i_m_now, v_dc_now, v_s_now, i_s_ref_next, i_l_next)
        # apply s as gate signals; advance plant by T_s using same s.
    """

    def __init__(self, params: FSMPCParams | None = None) -> None:
        self.p = params or FSMPCParams()

        # cache decay coefficient
        self._a = 1.0 - self.p.r * self.p.T_s / self.p.L
        self._b = self.p.T_s / self.p.L

        # last applied switching vector (used for delay compensation)
        self._s_last: np.ndarray = np.zeros(3, dtype=float)

    # ------------------------------------------------------------------
    @property
    def s_last(self) -> np.ndarray:
        return self._s_last.copy()

    # ------------------------------------------------------------------
    def predict(self, i_m: np.ndarray, v_s: np.ndarray, v_dc: float, s: np.ndarray) -> np.ndarray:
        """One-step Forward-Euler predictor — Eq. (4)."""
        return self._a * i_m + self._b * (v_s - M_MATRIX @ s * v_dc)

    # ------------------------------------------------------------------
    def predict_with_delay_comp(
        self,
        i_m: np.ndarray,
        v_s: np.ndarray,
        v_dc: float,
        s_candidate: np.ndarray,
    ) -> np.ndarray:
        """Two-step predictor: first roll one step using last-applied s, then test the candidate.

        This compensates for the one-sample computation delay that exists in any
        digital controller. See [F] §3.A and Kouro 2015 [24] of the paper.
        """
        # Step 1: predict state at k+1 using already-applied switching s_last
        i_m_kp1 = self._a * i_m + self._b * (v_s - M_MATRIX @ self._s_last * v_dc)
        # Step 2: predict k+2 using the candidate
        i_m_kp2 = self._a * i_m_kp1 + self._b * (v_s - M_MATRIX @ s_candidate * v_dc)
        return i_m_kp2

    # ------------------------------------------------------------------
    def update(
        self,
        i_m: np.ndarray,
        v_dc: float,
        v_s: np.ndarray,
        i_s_ref: np.ndarray,
        i_l: np.ndarray,
    ) -> np.ndarray:
        """Solve argmin over the 8 switching vectors and return the chosen `s`.

        Reference for converter current: i_m_ref = i_s_ref - i_l   (KCL at PCC).
        """
        i_m_ref = i_s_ref - i_l

        best_s = SWITCHING_VECTORS[0]
        best_cost = np.inf
        for s in SWITCHING_VECTORS:
            if self.p.use_delay_compensation:
                i_pred = self.predict_with_delay_comp(i_m, v_s, v_dc, s)
            else:
                i_pred = self.predict(i_m, v_s, v_dc, s)
            err = i_pred - i_m_ref
            cost = float(err @ err)
            if cost < best_cost:
                best_cost = cost
                best_s = s

        # Memorise for delay-comp on next tick
        self._s_last = best_s.copy()
        return best_s

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._s_last = np.zeros(3, dtype=float)
