# =============================================================================
# sambp / digital_twin / estimation / ekf_phasor_estimator.py
#
# EKF state estimator using DFT-derived phasor observations.
#
# Replaces the instantaneous-sample approximation of EKFEstimator._seq_magnitude
# with exact Fortescue sequence phasors from PhasorDFT.  All other EKF
# mechanics (state model, Jacobian, condition-number gate) are identical to
# EKFEstimator so both estimators are drop-in interchangeable.
#
# Key difference vs EKFEstimator
# --------------------------------
# EKFEstimator._seq_magnitude: RMS of instantaneous samples, updated at 1 kHz.
#   • Available from the very first sample.
#   • Positive-sequence magnitude ≈ sqrt((a²+b²+c²)/3) — exact only for
#     balanced, constant-envelope signals; biased ~1/√2 for pure sinusoids.
#
# EKFPhasorEstimator: DFT at fundamental bin via PhasorDFT, updated once the
# one-cycle buffer (N = fs/f0 samples) is full.
#   • Exact for integer-cycle sinusoidal signals at the fundamental frequency.
#   • First EKF update deferred by N-1 samples (N-1 ms at 1 kHz / 50 Hz →
#     19 ms = one cycle minus one sample).
#   • Negative-sequence extraction exact via Fortescue; no unbalance proxy.
#
# Latency trade-off
# -----------------
# At fs=1000 Hz, f0=50 Hz: N=20 samples = 20 ms.  This equals the pre-
# convergence window used in Study E.  The estimator therefore provides a
# converged phasor-domain observation at exactly the point the relay fires its
# Z1/87L decision — no additional latency to the protection chain.
#
# Interface contract
# ------------------
# EKFPhasorEstimator is a drop-in replacement for EKFEstimator:
#   • Same __init__ signature (x0, P0)
#   • Same update(t, v_abc, i_abc) → state dict
#   • Same reset(x0, P0)
#   • Same state dict keys: k_ibr, z_line, alpha, f_gfm, kappa_n, residual,
#     n_updates
#   • Additional key: 'dft_ready' (bool) — False until the first DFT update
#
# The caller MUST check 'dft_ready' before trusting the estimate if it
# cannot guarantee at least N samples have been pushed since the last reset().
#
# Public API
# ----------
# est = EKFPhasorEstimator(fs=1000, f0=50, x0=None, P0=1.0)
# state = est.update(t, v_abc, i_abc)
# est.reset(x0=None, P0=1.0)
# =============================================================================

import numpy as np

from .phasor_dft import PhasorDFT


class EKFPhasorEstimator:
    """
    Extended Kalman Filter with DFT phasor observations.

    Parameters
    ----------
    fs  : float — sample rate [Hz].  Default 1000.
    f0  : float — nominal system frequency [Hz].  Default 50.
    x0  : array-like (4,) or None — initial state [k_ibr, z_line, alpha, f_gfm].
    P0  : float — initial diagonal covariance.  Default 1.0.
    """

    # Nominal initial state: [k_ibr, z_line, alpha, f_gfm]
    _X_NOM  = np.array([0.20, 0.050, 0.50, 0.50])
    # Process noise diagonal — identical to EKFEstimator (TR-44)
    _Q_DIAG = np.array([1e-4, 1e-6, 1e-4, 1e-5])
    # Measurement noise diagonal [I_pos, I_neg, Z_app]
    # Same class-1P CT/VT noise as EKFEstimator; phasor domain reduces
    # effective noise by sqrt(N) via DFT averaging — R is adjusted accordingly.
    _R_DIAG_BASE = np.array([0.010**2, 0.010**2, (0.005 / 0.050)**2])

    # Physical bounds [min, max] per state — identical to EKFEstimator
    _BOUNDS = np.array([
        [0.001, 1.00],   # k_ibr
        [0.005, 0.50],   # z_line
        [0.001, 1.05],   # alpha
        [0.000, 1.00],   # f_gfm
    ])

    def __init__(self, fs: float = 1000.0, f0: float = 50.0,
                 x0=None, P0: float = 1.0):
        self.fs = float(fs)
        self.f0 = float(f0)
        self._dft = PhasorDFT(fs=fs, f0=f0)
        N = self._dft.cycle_length

        # DFT averaging reduces measurement noise variance by 1/N
        # (N independent samples averaged in frequency domain)
        self._R = np.diag(self._R_DIAG_BASE / N)
        self._Q = np.diag(self._Q_DIAG)

        self._x = (np.array(x0, dtype=float) if x0 is not None
                   else self._X_NOM.copy())
        self._P         = np.eye(4) * P0
        self._n_updates = 0
        self._kappa_n   = 1.0
        self._residual  = 0.0
        self._dft_ready = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def update(self, t, v_abc, i_abc):
        """
        Push one sample and (if the DFT buffer is full) run an EKF update.

        Parameters
        ----------
        t     : float      — current time [s]  (not used internally; kept for
                             interface compatibility with EKFEstimator)
        v_abc : array (3,) — phase voltages [pu]
        i_abc : array (3,) — phase currents [pu]

        Returns
        -------
        state : dict — k_ibr, z_line, alpha, f_gfm, kappa_n, residual,
                       n_updates, dft_ready
        """
        v_abc = np.asarray(v_abc, dtype=float)
        i_abc = np.asarray(i_abc, dtype=float)

        # Push sample into DFT buffer (always)
        self._dft.push(v_abc, i_abc)

        if not self._dft.ready:
            # Buffer not yet full — return prior state without EKF update
            return self._state_dict()

        self._dft_ready = True

        # ── Extract phasor measurements ───────────────────────────────
        p    = self._dft.extract()
        y    = np.array([p['I_pos_mag'], p['I_neg_mag'],
                         (p['V_pos_mag'] / p['I_pos_mag'])
                         if p['I_pos_mag'] > 1e-4 else 1e6])

        # ── EKF predict ───────────────────────────────────────────────
        x_pred = self._x.copy()      # F = I
        P_pred = self._P + self._Q

        # ── Jacobian ──────────────────────────────────────────────────
        H = self._jacobian(x_pred)

        # ── Innovation covariance + Kalman gain ──────────────────────
        S = H @ P_pred @ H.T + self._R
        try:
            K = P_pred @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            self._x = x_pred
            self._P = P_pred
            self._kappa_n  = 1e9
            self._residual = float('inf')
            return self._state_dict()

        # ── Update ────────────────────────────────────────────────────
        y_hat = self._h(x_pred)
        innov = y - y_hat
        x_upd = x_pred + K @ innov
        P_upd = (np.eye(4) - K @ H) @ P_pred

        # ── Clamp ─────────────────────────────────────────────────────
        for i in range(4):
            x_upd[i] = max(self._BOUNDS[i, 0],
                           min(self._BOUNDS[i, 1], x_upd[i]))

        self._x = x_upd
        self._P = P_upd

        # ── Diagnostics ───────────────────────────────────────────────
        self._kappa_n  = self._condition_number(H)
        resid_vec      = y - self._h(self._x)
        self._residual = float(np.linalg.norm(resid_vec) /
                               max(np.linalg.norm(y), 1e-9))
        self._n_updates += 1

        return self._state_dict()

    # ------------------------------------------------------------------
    def reset(self, x0=None, P0: float = 1.0):
        """
        Reset estimator state and clear the DFT buffer.

        Call this at the start of each new fault event (mirrors EKFEstimator.reset).
        """
        self._x = (np.array(x0, dtype=float) if x0 is not None
                   else self._X_NOM.copy())
        self._P         = np.eye(4) * P0
        self._n_updates = 0
        self._kappa_n   = 1.0
        self._residual  = 0.0
        self._dft_ready = False
        self._dft.reset()

    # ------------------------------------------------------------------
    # Measurement model  (identical to EKFEstimator — single source of truth)
    # ------------------------------------------------------------------
    @staticmethod
    def _h(x):
        """h(x): nonlinear measurement function — mirrors EKFEstimator._h."""
        k, zl, al, fg = x
        I_pos = k
        I_neg = k * (1.0 - fg) * 0.25
        Z_app = (al * zl / k) if k > 1e-4 else 1e6
        return np.array([I_pos, I_neg, Z_app])

    @staticmethod
    def _jacobian(x):
        """∂h/∂x — mirrors EKFEstimator._jacobian."""
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

    @staticmethod
    def _condition_number(H):
        """SVD-based condition number — mirrors EKFEstimator._condition_number."""
        try:
            sv = np.linalg.svd(H, compute_uv=False)
            sv_nz = sv[sv > 1e-12]
            return float(sv_nz[0] / sv_nz[-1]) if len(sv_nz) else 1e9
        except Exception:
            return 1e9

    # ------------------------------------------------------------------
    def _state_dict(self):
        return {
            'k_ibr':     float(self._x[0]),
            'z_line':    float(self._x[1]),
            'alpha':     float(self._x[2]),
            'f_gfm':     float(self._x[3]),
            'kappa_n':   float(self._kappa_n),
            'residual':  float(self._residual),
            'n_updates': self._n_updates,
            'dft_ready': self._dft_ready,
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
        return (f"EKFPhasorEstimator(k={s['k_ibr']:.4f}, α={s['alpha']:.3f}, "
                f"κ_n={s['kappa_n']:.1f}, n={self._n_updates}, "
                f"dft_ready={self._dft_ready})")
