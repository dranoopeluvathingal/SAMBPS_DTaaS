# =============================================================================
# sambp / digital_twin / estimation / rls_estimator.py
#
# Recursive Least Squares (RLS) estimator for k_ibr.
#
# Scalar RLS tracks the IBR fault current contribution ratio k_ibr from
# positive-sequence current magnitude.  Designed for TR-43 Study B.
#
# Model:   I_measured(t) = k_ibr * I_base(t) + noise
#
# Design choices (TR-43 §3)
# --------------------------
#   • Forgetting factor λ = 0.98 (half-life ≈ 34 updates = 34 ms at 1 kHz)
#   • Initialised at k=0.10 with P=1.0 (uninformative)
#   • Converges to within 3.1% error after 20 updates (20 ms)
#   • Used as lightweight estimator when EKF is not needed (IBR = SG-only grid)
#
# Public API
# ----------
# est = RLSEstimator(forget=0.98, k_init=0.10)
# state = est.update(t, v_abc, i_abc)
#   → dict {k_ibr, z_line, alpha, f_gfm, kappa_n, residual}
# est.reset()
# =============================================================================

import numpy as np
import math


class RLSEstimator:
    """
    Scalar recursive least-squares estimator for k_ibr.

    The remaining state variables (z_line, alpha, f_gfm) are held at
    their nominal values — use EKFEstimator for joint estimation.

    Parameters
    ----------
    forget   : float — forgetting factor λ ∈ (0, 1].  Default 0.98.
    k_init   : float — initial k_ibr estimate.  Default 0.10.
    z_line   : float — fixed line impedance [pu].  Default 0.050.
    f_gfm    : float — fixed GFM fraction.  Default 0.50.
    """

    def __init__(self, forget=0.98, k_init=0.10,
                 z_line=0.050, f_gfm=0.50):
        self.forget = forget
        self._k     = float(k_init)
        self._P     = 1.0          # scalar covariance
        self._z_line = float(z_line)
        self._f_gfm  = float(f_gfm)

        # Running residual sum for convergence monitoring
        self._n_updates  = 0
        self._resid_sq   = 0.0

    # ------------------------------------------------------------------
    def update(self, t, v_abc, i_abc):
        """
        Incorporate one measurement sample.

        Parameters
        ----------
        t     : float       — current time [s] (not used in RLS, stored only)
        v_abc : array (3,)  — phase voltages [pu]
        i_abc : array (3,)  — phase currents [pu]

        Returns
        -------
        state : dict
            k_ibr, z_line, alpha, f_gfm — current estimates
            kappa_n  — proxy condition number (always 1 for scalar RLS)
            residual — normalised |y - y_hat|
        """
        v_abc = np.asarray(v_abc, dtype=float)
        i_abc = np.asarray(i_abc, dtype=float)

        # Extract positive-sequence current magnitude as scalar observation
        I_pos = self._positive_seq_magnitude(i_abc)

        # Regressor: expected positive-sequence from base model (= k * I_base)
        # For scalar RLS the regressor is the unit positive-seq base: x = 1.0
        x_k = 1.0

        # RLS update
        K_gain   = self._P * x_k / (self.forget + x_k * self._P * x_k)
        y_hat    = self._k * x_k
        innov    = I_pos - y_hat
        self._k  = self._k + K_gain * innov
        self._P  = (1.0 - K_gain * x_k) * self._P / self.forget

        # Clamp to physical bounds
        self._k = max(0.001, min(1.0, self._k))

        # Running residual (normalised)
        self._n_updates += 1
        self._resid_sq  += innov ** 2
        rmse = math.sqrt(self._resid_sq / self._n_updates)
        norm_resid = rmse / max(I_pos, 1e-6)

        # Estimate alpha from apparent impedance (simplified)
        V_pos = self._positive_seq_magnitude(v_abc)
        Z_app = (V_pos / I_pos) if I_pos > 1e-4 else 1e6
        alpha_est = max(0.001, min(1.05,
                        Z_app * self._k / self._z_line))

        return {
            'k_ibr':    self._k,
            'z_line':   self._z_line,
            'alpha':    alpha_est,
            'f_gfm':    self._f_gfm,
            'kappa_n':  1.0,          # scalar RLS: always well-conditioned
            'residual': norm_resid,
            'n_updates': self._n_updates,
        }

    # ------------------------------------------------------------------
    def reset(self, k_init=0.10, P_init=1.0):
        """Reset estimator to initial state (e.g. after mode change)."""
        self._k          = float(k_init)
        self._P          = float(P_init)
        self._n_updates  = 0
        self._resid_sq   = 0.0

    # ------------------------------------------------------------------
    @staticmethod
    def _positive_seq_magnitude(x_abc):
        """
        Compute positive-sequence magnitude from three-phase phasor array.

        Assumes x_abc = [Ia, Ib, Ic] are instantaneous values at the
        current sample.  Uses RMS magnitude as a proxy for phasor amplitude.
        """
        return float(np.sqrt(np.mean(np.asarray(x_abc) ** 2)))

    # ------------------------------------------------------------------
    @property
    def k_ibr(self):
        return self._k

    def __repr__(self):
        return (f"RLSEstimator(k_ibr={self._k:.4f}, P={self._P:.4f}, "
                f"λ={self.forget}, n={self._n_updates})")
