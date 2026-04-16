# =============================================================================
# sambp / digital_twin / estimation / bess_ekf.py
#
# BESS Extended Kalman Filter — TR-68 WP 68.4
#
# State vector  x = [SoC, P_dc, Q_ac, V_dc, I_ac_mag, T_cell]  (6 states)
# Observations  z = [Va, Vb, Vc, Ia, Ib, Ic]                   (6 measurements)
#
# Wraps BESSModel.f() as the nonlinear state transition and BESSModel.h() as
# the measurement model.  The Jacobian H is supplied by BESSModel.H_jacobian().
#
# Mode-transition handling
# ------------------------
# A charge-to-discharge (or vice versa) transition causes a step in P_dc.
# When |P_dc_predicted - P_dc_measured| > _MODE_CHANGE_THRESH, the estimator
# inflates the P_dc and Q_ac diagonal blocks of Q by _MODE_Q_INFLATION to
# allow fast re-convergence.  The inflation is applied for _MODE_RESET_STEPS
# cycles then decays back to nominal Q.
#
# Public API
# ----------
# cfg = BESSConfig.li_ion_1mwh()
# est = BESSEKFEstimator(cfg)
# state = est.update(z, u=None, dt=1e-3)
#   → dict {SoC, P_dc, Q_ac, V_dc, I_ac_mag, T_cell, residual, kappa_n, n_updates}
# est.reset(x0=None)
# est.inject_fault(fault_type, t_elapsed)   — force fault-current state
# =============================================================================

from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np

from models.bess_model import BESSConfig, BESSModel

# State indices (mirrors bess_model.py private constants)
_SoC, _P_dc, _Q_ac, _V_dc, _I_ac, _T_cell = 0, 1, 2, 3, 4, 5

# Mode-transition detection
_MODE_CHANGE_THRESH = 0.30     # pu — ΔP_dc step that signals mode change
_MODE_Q_INFLATION   = 50.0    # multiplier on P_dc / Q_ac process noise
_MODE_RESET_STEPS   = 20      # DT cycles (@ 1 ms → 20 ms) of elevated Q

# EKF convergence threshold for condition number (gate for trust)
_KAPPA_TRUST = 50.0


class BESSEKFEstimator:
    """
    Extended Kalman Filter for 6-state BESS estimation.

    Uses BESSModel.f() as the nonlinear state transition and
    BESSModel.h() / BESSModel.H_jacobian() as the measurement model.

    Parameters
    ----------
    cfg        : BESSConfig  — BESS hardware / chemistry configuration.
    x0         : array (6,)  — initial state vector.  None → model default.
    P0_diag    : array (6,)  — initial covariance diagonal.  None → default.
    t_ambient  : float       — ambient temperature [°C] (default 25.0).
    """

    STATE_NAMES = BESSModel.STATE_NAMES   # ('SoC', 'P_dc', 'Q_ac', 'V_dc', 'I_ac_mag', 'T_cell')

    # Default initial covariance diagonal (large uncertainty at start)
    _P0_DEFAULT = np.array([0.02**2, 0.10**2, 0.10**2,
                             0.05**2, 0.10**2, 5.0**2])

    def __init__(self, cfg: Optional[BESSConfig] = None,
                 x0=None, P0_diag=None,
                 t_ambient: float = 25.0) -> None:
        self.cfg   = cfg or BESSConfig.li_ion_1mwh()
        self.model = BESSModel(self.cfg, t_ambient=t_ambient)

        self._x = (np.array(x0, dtype=float) if x0 is not None
                   else self.model.x0())
        P0 = (np.array(P0_diag, dtype=float) if P0_diag is not None
              else self._P0_DEFAULT.copy())
        self._P = np.diag(P0)
        self._Q = self.model.Q.copy()
        self._R = self.model.R.copy()

        self._n_updates:    int   = 0
        self._kappa_n:      float = 1.0
        self._residual:     float = 0.0
        self._mode_steps:   int   = 0    # remaining high-Q cycles

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def update(self, z, u=None, dt: float = 1e-3) -> Dict[str, float]:
        """
        One EKF predict-update step.

        Parameters
        ----------
        z  : array (6,) — [Va, Vb, Vc, Ia, Ib, Ic] measurements [pu]
        u  : array (2,) or None — [P_setpoint_pu, Q_setpoint_pu]
        dt : float             — DT step [s]

        Returns
        -------
        state dict : {SoC, P_dc, Q_ac, V_dc, I_ac_mag, T_cell,
                      residual, kappa_n, n_updates}
        """
        z = np.asarray(z, dtype=float)

        # ── Step 1: Nonlinear state prediction ───────────────────────
        x_pred = self.model.f(self._x, u, dt)

        # ── Step 2: Mode-transition detection & Q inflation ──────────
        Q_eff = self._effective_Q(x_pred)

        # ── Step 3: State Jacobian (F = ∂f/∂x linearised via finite diff) ─
        F = self._state_jacobian(self._x, u, dt)

        # ── Step 4: Covariance prediction ────────────────────────────
        P_pred = F @ self._P @ F.T + Q_eff

        # ── Step 5: Measurement Jacobian H and innovation ────────────
        H   = self.model.H_jacobian(x_pred)
        z_hat = self.model.h(x_pred)
        innov = z - z_hat

        # ── Step 6: Innovation covariance + Kalman gain ───────────────
        S = H @ P_pred @ H.T + self._R
        try:
            K = P_pred @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            self._x = self.model.clamp(x_pred)
            self._P = P_pred
            self._kappa_n  = 1e9
            self._residual = float("inf")
            return self._state_dict()

        # ── Step 7: State update ──────────────────────────────────────
        x_upd = x_pred + K @ innov
        x_upd = self.model.clamp(x_upd)
        P_upd = (np.eye(6) - K @ H) @ P_pred

        self._x = x_upd
        self._P = P_upd

        # ── Step 8: Diagnostics ───────────────────────────────────────
        self._kappa_n  = _condition_number(H)
        z_final        = self.model.h(self._x)
        resid_vec      = z - z_final
        self._residual = float(np.linalg.norm(resid_vec) /
                               max(np.linalg.norm(z), 1e-9))
        self._n_updates += 1
        if self._mode_steps > 0:
            self._mode_steps -= 1

        return self._state_dict()

    def reset(self, x0=None, P0_diag=None) -> None:
        """Reset EKF to initial conditions."""
        self._x = (np.array(x0, dtype=float) if x0 is not None
                   else self.model.x0())
        P0 = (np.array(P0_diag, dtype=float) if P0_diag is not None
              else self._P0_DEFAULT.copy())
        self._P          = np.diag(P0)
        self._n_updates  = 0
        self._kappa_n    = 1.0
        self._residual   = 0.0
        self._mode_steps = 0

    def inject_fault(self, fault_type: str = "3PH", t_elapsed: float = 0.0) -> None:
        """
        Force BESS into fault-current state (used by integration test harness).

        Modifies internal state x so that I_ac_mag reflects the fault current
        limit.  Useful to pre-position the EKF before fault estimation begins.
        """
        self._x = self.model.fault_state(self._x, fault_type, t_elapsed)
        # Inflate current covariance row/col to reflect sudden state jump
        self._P[_I_ac, _I_ac] = max(self._P[_I_ac, _I_ac], 0.05**2)

    # ------------------------------------------------------------------
    # Derived quantities from current estimate
    # ------------------------------------------------------------------

    @property
    def state(self) -> Dict[str, float]:
        return self._state_dict()

    @property
    def covariance(self) -> np.ndarray:
        return self._P.copy()

    @property
    def is_converged(self) -> bool:
        """True when kappa_n < _KAPPA_TRUST and at least 10 updates have run."""
        return self._kappa_n < _KAPPA_TRUST and self._n_updates >= 10

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _effective_Q(self, x_pred: np.ndarray) -> np.ndarray:
        """Return Q with P_dc/Q_ac blocks inflated during mode transitions."""
        dp = abs(float(x_pred[_P_dc]) - float(self._x[_P_dc]))
        if dp > _MODE_CHANGE_THRESH:
            self._mode_steps = _MODE_RESET_STEPS

        if self._mode_steps > 0:
            Q_eff = self._Q.copy()
            Q_eff[_P_dc, _P_dc] *= _MODE_Q_INFLATION
            Q_eff[_Q_ac, _Q_ac] *= _MODE_Q_INFLATION
            return Q_eff
        return self._Q

    def _state_jacobian(self, x: np.ndarray, u, dt: float) -> np.ndarray:
        """
        Finite-difference approximation of ∂f/∂x (6×6).

        Uses a ±ε central difference for each state.  BESSModel.f() is
        nonlinear so this avoids the need to derive an analytic Jacobian.
        """
        eps = 1e-5
        F   = np.zeros((6, 6))
        f0  = self.model.f(x, u, dt)
        for i in range(6):
            x_p = x.copy(); x_p[i] += eps
            x_m = x.copy(); x_m[i] -= eps
            fp  = self.model.f(self.model.clamp(x_p), u, dt)
            fm  = self.model.f(self.model.clamp(x_m), u, dt)
            F[:, i] = (fp - fm) / (2.0 * eps)
        return F

    def _state_dict(self) -> Dict[str, float]:
        return {
            "SoC":       float(self._x[_SoC]),
            "P_dc":      float(self._x[_P_dc]),
            "Q_ac":      float(self._x[_Q_ac]),
            "V_dc":      float(self._x[_V_dc]),
            "I_ac_mag":  float(self._x[_I_ac]),
            "T_cell":    float(self._x[_T_cell]),
            "residual":  float(self._residual),
            "kappa_n":   float(self._kappa_n),
            "n_updates": self._n_updates,
        }

    def __repr__(self) -> str:
        s = self._state_dict()
        return (f"BESSEKFEstimator(chem={self.cfg.chemistry}, "
                f"SoC={s['SoC']:.3f}, I_ac={s['I_ac_mag']:.3f}, "
                f"κ_n={s['kappa_n']:.1f}, n={s['n_updates']})")


# ---------------------------------------------------------------------------
# Module-level helper (mirrors EKFEstimator._condition_number)
# ---------------------------------------------------------------------------

def _condition_number(H: np.ndarray) -> float:
    try:
        sv = np.linalg.svd(H, compute_uv=False)
        sv_nz = sv[sv > 1e-12]
        if len(sv_nz) == 0:
            return 1e9
        return float(sv_nz[0] / sv_nz[-1])
    except Exception:
        return 1e9
