"""ShadowPlant — a parallel instance of the same Plant model, driven by ICA telemetry.

The shadow consumes:
    s_applied  (switching vector commanded by the ICA)
    v_s_abc    (grid voltage)
    v_dc       (measured DC-link voltage — used to bootstrap state and as comparison)
    i_m_abc    (measured AC-side current — used to bootstrap state and as comparison)

It steps its own Plant copy by T_s using the same Eq.(1)(2). The residual
between predicted and measured i_m, v_dc is exposed for the AnomalyDetector
and for parameter-identification updates.

The shadow does NOT close any loop on the physical plant. It is read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ..plant import Plant, PlantParams


@dataclass
class ShadowResidual:
    """Per-tick residual between measured and predicted state."""
    t: float
    v_dc_meas: float
    v_dc_pred: float
    i_m_norm_meas: float
    i_m_norm_pred: float
    v_dc_residual: float          # meas - pred
    i_m_residual_vec: np.ndarray  # 3-vector
    i_m_residual_norm: float      # ||meas - pred||


class ShadowPlant:
    """Reduced-order shadow of one ICA's plant.

    Usage:
        sp = ShadowPlant(PlantParams())
        # at each ICA telemetry tick:
        sp.set_state(measured_i_m, measured_v_dc)   # bootstrap (or reset)
        sp.step(s_applied, v_s, dt, i_dc_estimate)
        residual = sp.compute_residual(t, measured_i_m_next, measured_v_dc_next)
    """

    def __init__(self, params: PlantParams | None = None) -> None:
        self.plant = Plant(params or PlantParams())
        # Tracking history
        self._last_pred_i_m: np.ndarray | None = None
        self._last_pred_v_dc: float | None = None

    # ------------------------------------------------------------------
    def set_state(self, i_m: np.ndarray, v_dc: float) -> None:
        """Bootstrap shadow from measured ICA state."""
        self.plant.i_m = np.asarray(i_m, dtype=float).copy()
        self.plant.v_dc = float(v_dc)

    def step(
        self,
        s: np.ndarray,
        v_s: np.ndarray,
        dt: float,
        i_dc: float = 0.0,
        n_sub: int = 5,
    ) -> tuple[np.ndarray, float]:
        """Advance shadow by `dt` using the given inputs (matching ICA's step)."""
        sub_dt = dt / n_sub
        for _ in range(n_sub):
            self.plant.step(s, v_s, i_dc, sub_dt)
        self._last_pred_i_m = self.plant.i_m.copy()
        self._last_pred_v_dc = float(self.plant.v_dc)
        return self._last_pred_i_m, self._last_pred_v_dc

    # ------------------------------------------------------------------
    def compute_residual(
        self,
        t: float,
        i_m_meas: np.ndarray,
        v_dc_meas: float,
    ) -> ShadowResidual:
        i_m_pred = self._last_pred_i_m if self._last_pred_i_m is not None else self.plant.i_m
        v_dc_pred = self._last_pred_v_dc if self._last_pred_v_dc is not None else self.plant.v_dc
        i_m_residual_vec = np.asarray(i_m_meas, dtype=float) - i_m_pred
        return ShadowResidual(
            t=float(t),
            v_dc_meas=float(v_dc_meas),
            v_dc_pred=float(v_dc_pred),
            i_m_norm_meas=float(np.linalg.norm(i_m_meas)),
            i_m_norm_pred=float(np.linalg.norm(i_m_pred)),
            v_dc_residual=float(v_dc_meas - v_dc_pred),
            i_m_residual_vec=i_m_residual_vec,
            i_m_residual_norm=float(np.linalg.norm(i_m_residual_vec)),
        )

    # ------------------------------------------------------------------
    @property
    def state(self) -> tuple[np.ndarray, float]:
        return self.plant.i_m.copy(), float(self.plant.v_dc)

    def reset(self, params: PlantParams | None = None) -> None:
        self.plant = Plant(params or PlantParams())
        self._last_pred_i_m = None
        self._last_pred_v_dc = None
