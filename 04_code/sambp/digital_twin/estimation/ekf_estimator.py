# =============================================================================
# sambp / digital_twin / estimation / ekf_estimator.py
#
# Extended Kalman Filter (EKF) for joint IBR state estimation.
#
# State vector x = [k_ibr, Z_line, alpha, f_gfm]  (4 states)
# Observations  y = [I_pos, I_neg, Z_app]          (3 measurements)
#
# Based on TR-44 Study A.  Replaces the scalar RLS for multi-parameter
# tracking where IBR fleet dispatch changes Z_line, f_gfm, or alpha.
#
# Design choices (TR-44 §2)
# --------------------------
#   • Constant-velocity state model (F = I)
#   • Process noise Q tuned for ±50% k_ibr slow drift over 500 DT cycles
#     (TR-44 Study D, forgetting equivalent λ=0.995)
#   • Two-pass update: first pass at cycle start, second pass refines
#     alpha/Z_line in the tail of the event window (mirrors LM two-pass)
#   • Condition number κ_n of H computed at each step — gates whether
#     the DT estimate is trusted (consistent with confidence gate pattern)
#
# Public API
# ----------
# est = EKFEstimator()
# state = est.update(t, v_abc, i_abc)
#   → dict {k_ibr, z_line, alpha, f_gfm, kappa_n, residual}
# est.reset(x0=None)
# =============================================================================

import numpy as np
import math


class EKFEstimator:
    """
    Extended Kalman Filter for joint estimation of [k_ibr, Z_line, alpha, f_gfm].

    Wraps IBRStateSpaceModel to keep the EKF self-contained; mirrors are
    imported lazily to avoid circular imports.

    Parameters
    ----------
    x0    : array-like (4,) — initial state.  Default: model nominal.
    P0    : float           — initial diagonal covariance.  Default 1.0.
    """

    # Nominal initial state: [k_ibr, z_line, alpha, f_gfm]
    _X_NOM  = np.array([0.20, 0.050, 0.50, 0.50])
    # Process noise diagonal (TR-44, matches IBRStateSpaceModel.Q)
    _Q_DIAG = np.array([1e-4, 1e-6, 1e-4, 1e-5])
    # Measurement noise diagonal [I_pos, I_neg, Z_app] (class 1P CT/VT)
    _R_DIAG = np.array([0.010**2, 0.010**2, (0.005/0.050)**2])

    # Physical bounds [min, max] per state
    _BOUNDS = np.array([
        [0.001, 1.00],   # k_ibr
        [0.005, 0.50],   # z_line
        [0.001, 1.05],   # alpha
        [0.000, 1.00],   # f_gfm
    ])

    def __init__(self, x0=None, P0=1.0):
        self._x = (np.array(x0, dtype=float) if x0 is not None
                   else self._X_NOM.copy())
        self._P = np.eye(4) * P0
        self._Q = np.diag(self._Q_DIAG)
        self._R = np.diag(self._R_DIAG)
        self._n_updates = 0
        self._kappa_n   = 1.0
        self._residual  = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def update(self, t, v_abc, i_abc):
        """
        Run one EKF predict-update cycle.

        Parameters
        ----------
        t     : float      — current time [s]
        v_abc : array (3,) — phase voltages [pu]
        i_abc : array (3,) — phase currents [pu]

        Returns
        -------
        state : dict  — k_ibr, z_line, alpha, f_gfm, kappa_n, residual
        """
        v_abc = np.asarray(v_abc, dtype=float)
        i_abc = np.asarray(i_abc, dtype=float)

        # ── Step 1: Extract measurements ─────────────────────────────
        y = self._measure(v_abc, i_abc)

        # ── Step 2: EKF predict ───────────────────────────────────────
        x_pred = self._x.copy()          # F = I (constant model)
        P_pred = self._P + self._Q

        # ── Step 3: Compute Jacobian H at x_pred ─────────────────────
        H = self._jacobian(x_pred)

        # ── Step 4: Innovation covariance + Kalman gain ───────────────
        S = H @ P_pred @ H.T + self._R
        try:
            K = P_pred @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            # Singular S — skip update, hold prediction
            self._x = x_pred
            self._P = P_pred
            self._kappa_n  = 1e9
            self._residual = float('inf')
            return self._state_dict()

        # ── Step 5: Update ────────────────────────────────────────────
        y_hat    = self._h(x_pred)
        innov    = y - y_hat
        x_upd    = x_pred + K @ innov
        P_upd    = (np.eye(4) - K @ H) @ P_pred

        # ── Step 6: Clamp to physical bounds ──────────────────────────
        for i in range(4):
            x_upd[i] = max(self._BOUNDS[i, 0],
                           min(self._BOUNDS[i, 1], x_upd[i]))

        self._x = x_upd
        self._P = P_upd

        # ── Step 7: Diagnostics ───────────────────────────────────────
        self._kappa_n  = self._condition_number(H)
        y_final        = self._h(self._x)
        resid_vec      = y - y_final
        self._residual = float(np.linalg.norm(resid_vec) /
                               max(np.linalg.norm(y), 1e-9))
        self._n_updates += 1

        return self._state_dict()

    # ------------------------------------------------------------------
    def reset(self, x0=None, P0=1.0):
        """Reset to initial state (call on mode change or new event)."""
        self._x         = (np.array(x0, dtype=float) if x0 is not None
                           else self._X_NOM.copy())
        self._P         = np.eye(4) * P0
        self._n_updates = 0
        self._kappa_n   = 1.0
        self._residual  = 0.0

    # ------------------------------------------------------------------
    # Measurement model
    # ------------------------------------------------------------------
    def _measure(self, v_abc, i_abc):
        """Extract [I_pos, I_neg, Z_app] from raw three-phase samples."""
        I_pos = self._seq_magnitude(i_abc, seq=+1)
        I_neg = self._seq_magnitude(i_abc, seq=-1)
        V_pos = self._seq_magnitude(v_abc, seq=+1)
        Z_app = (V_pos / I_pos) if I_pos > 1e-4 else 1e6
        return np.array([I_pos, I_neg, Z_app])

    def _h(self, x):
        """Nonlinear measurement function h(x) — mirrors IBRStateSpaceModel.h."""
        k, zl, al, fg = x
        I_pos = k
        I_neg = k * (1.0 - fg) * 0.25
        Z_app = (al * zl / k) if k > 1e-4 else 1e6
        return np.array([I_pos, I_neg, Z_app])

    def _jacobian(self, x):
        """Linearised measurement Jacobian ∂h/∂x — mirrors IBRStateSpaceModel.H_jacobian."""
        k, zl, al, fg = x
        H = np.zeros((3, 4))
        H[0, 0] = 1.0
        H[1, 0] = (1.0 - fg) * 0.25
        H[1, 3] = -k * 0.25
        if k > 1e-4:
            H[2, 0] = -al * zl / (k * k)
            H[2, 1] = al / k
            H[2, 2] = zl / k
        return H

    # ------------------------------------------------------------------
    # Condition number (confidence gate metric — mirrors relay families)
    # ------------------------------------------------------------------
    @staticmethod
    def _condition_number(H):
        """
        Compute condition number κ_n of H via SVD.

        κ_n < 30  → EKF Jacobian is well-conditioned, estimates trusted.
        κ_n > 30  → Near-singular; DT falls back to ScenarioLibrary lookup.
        """
        try:
            sv = np.linalg.svd(H, compute_uv=False)
            sv_nonzero = sv[sv > 1e-12]
            if len(sv_nonzero) == 0:
                return 1e9
            return float(sv_nonzero[0] / sv_nonzero[-1])
        except Exception:
            return 1e9

    # ------------------------------------------------------------------
    # Sequence extraction (Fortescue, instantaneous approximation)
    # ------------------------------------------------------------------
    @staticmethod
    def _seq_magnitude(x_abc, seq=+1):
        """
        Approximate positive or negative sequence magnitude from instantaneous
        three-phase samples using RMS (no phasor domain available at 1 kHz).
        """
        a = x_abc[0]
        b = x_abc[1]
        c = x_abc[2]
        if seq == +1:
            # Positive sequence ≈ average magnitude (balanced component)
            return float(math.sqrt((a**2 + b**2 + c**2) / 3.0))
        else:
            # Negative sequence ≈ unbalance = max - min deviation
            mean = (a + b + c) / 3.0
            dev  = [abs(x - mean) for x in [a, b, c]]
            return float(math.sqrt(sum(d**2 for d in dev) / 3.0))

    # ------------------------------------------------------------------
    def _state_dict(self):
        return {
            'k_ibr':    float(self._x[0]),
            'z_line':   float(self._x[1]),
            'alpha':    float(self._x[2]),
            'f_gfm':    float(self._x[3]),
            'kappa_n':  float(self._kappa_n),
            'residual': float(self._residual),
            'n_updates': self._n_updates,
        }

    # ------------------------------------------------------------------
    @property
    def state(self):
        return self._state_dict()

    @property
    def covariance(self):
        return self._P.copy()

    def __repr__(self):
        s = self._state_dict()
        return (f"EKFEstimator(k={s['k_ibr']:.4f}, α={s['alpha']:.3f}, "
                f"κ_n={s['kappa_n']:.1f}, n={self._n_updates})")
