# =============================================================================
# sambp / digital_twin / models / state_space_model.py
#
# IBR protection system state-space model.
#
# State vector  x = [k_ibr, Z_line, alpha, f_gfm]   (4 states)
#
#   k_ibr  — IBR fault current contribution ratio  [0, 1]   (TR-43 §2)
#   Z_line — line impedance [pu]                            (TR-44 §2)
#   alpha  — normalised fault location [0, 1]               (TR-44 §3)
#   f_gfm  — GFM fraction of IBR fleet [0, 1]              (TR-44 §4)
#
# Dynamics: constant model (random walk) — no physical dynamics between
# DT cycles at 1 kHz.  Process noise Q captures slow parameter drift.
#
# Public API
# ----------
# model = IBRStateSpaceModel()
# model.push(state_dict)          # record latest estimate
# model.x_nominal                 # get default operating-point state
# model.Q, model.R                # process / measurement noise matrices
# =============================================================================

import numpy as np


class IBRStateSpaceModel:
    """
    Linearised constant-velocity state-space model for the IBR protection DT.

    Attributes
    ----------
    STATE_NAMES : tuple
        Names of the four state variables in order.
    x_nominal : ndarray, shape (4,)
        Nominal operating point used to initialise estimators.
    Q : ndarray, shape (4,4)
        Process noise covariance (diagonal).  Tuned from TR-44 Study D
        (slow sinusoidal k_ibr drift at ±50% over 500 DT cycles).
    R : ndarray, shape (3,3)
        Measurement noise covariance for observations [I_pos, I_neg, Z_app].
        Diagonal entries from class 1P CT (σ_I = 0.010 pu) and
        class 1P VT (σ_V = 0.005 pu).
    """

    STATE_NAMES = ('k_ibr', 'z_line', 'alpha', 'f_gfm')

    # Nominal operating point (grid-connected, mixed SG+IBR fleet)
    _X_NOM = np.array([0.20, 0.050, 0.50, 0.50])

    # Process noise — calibrated so EKF tracks ±50% k_ibr drift in ~500 steps
    # (TR-44 Study D: forgetting factor λ=0.995 → equivalent Q/R ≈ 0.005)
    _Q_DIAG = np.array([1e-4, 1e-6, 1e-4, 1e-5])

    # Measurement noise — class 1P CT σ=0.010 pu, class 1P VT σ=0.005 pu
    # Observations: [I_positive_seq, I_negative_seq, Z_apparent]
    _R_DIAG = np.array([0.010**2, 0.010**2, (0.005/0.050)**2])

    # State bounds [min, max] — physical constraints
    STATE_BOUNDS = {
        'k_ibr':  (0.001, 1.00),
        'z_line': (0.005, 0.50),
        'alpha':  (0.001, 1.05),   # >1.0 → external fault
        'f_gfm':  (0.000, 1.00),
    }

    def __init__(self):
        self.x_nominal = self._X_NOM.copy()
        self.Q = np.diag(self._Q_DIAG)
        self.R = np.diag(self._R_DIAG)
        self._history = []          # list of state dicts (capped at 500)

    # ------------------------------------------------------------------
    # State transition (F matrix — identity for constant model)
    # ------------------------------------------------------------------
    @property
    def F(self):
        """State transition matrix (4×4 identity for random-walk model)."""
        return np.eye(4)

    # ------------------------------------------------------------------
    # Measurement model h(x) and Jacobian H
    # ------------------------------------------------------------------
    def h(self, x):
        """
        Nonlinear measurement function.

        Parameters
        ----------
        x : array-like, shape (4,)
            [k_ibr, z_line, alpha, f_gfm]

        Returns
        -------
        y : ndarray, shape (3,)
            [I_pos_seq, I_neg_seq, Z_apparent]
        """
        k, zl, al, fg = x
        # Positive sequence current: I1 = k_ibr (fault current in pu)
        I_pos = k
        # Negative sequence: I2/I1 ratio driven by GFM fraction and fault type.
        # GFM inverters inject minimal neg-seq; GFL slightly more.
        # Approximation: I2 ≈ k * (1 - f_gfm) * 0.25
        I_neg = k * (1.0 - fg) * 0.25
        # Apparent impedance seen at relay: Z_app = alpha * Z_line / k_ibr
        # (simplified single-source model)
        Z_app = (al * zl / k) if k > 1e-4 else 1e6
        return np.array([I_pos, I_neg, Z_app])

    def H_jacobian(self, x):
        """
        Linearised measurement Jacobian ∂h/∂x evaluated at x.

        Returns
        -------
        H : ndarray, shape (3, 4)
        """
        k, zl, al, fg = x
        H = np.zeros((3, 4))
        # ∂I_pos/∂x
        H[0, 0] = 1.0                             # ∂I_pos/∂k
        # ∂I_neg/∂x
        H[1, 0] = (1.0 - fg) * 0.25              # ∂I_neg/∂k
        H[1, 3] = -k * 0.25                       # ∂I_neg/∂f_gfm
        # ∂Z_app/∂x
        if k > 1e-4:
            H[2, 0] = -al * zl / (k * k)          # ∂Z_app/∂k
            H[2, 1] = al / k                       # ∂Z_app/∂z_line
            H[2, 2] = zl / k                       # ∂Z_app/∂alpha
        return H

    # ------------------------------------------------------------------
    # Clamp state to physical bounds
    # ------------------------------------------------------------------
    def clamp(self, x):
        """Clamp state vector to physical bounds."""
        x = np.array(x, dtype=float)
        for i, name in enumerate(self.STATE_NAMES):
            lo, hi = self.STATE_BOUNDS[name]
            x[i] = max(lo, min(hi, x[i]))
        return x

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------
    def push(self, state_dict):
        """Record an estimated state (keyed by STATE_NAMES)."""
        self._history.append(state_dict.copy())
        if len(self._history) > 500:
            self._history.pop(0)

    def latest(self):
        """Return the most recently pushed state dict, or None."""
        return self._history[-1] if self._history else None

    def history_array(self):
        """Return state history as ndarray, shape (N, 4)."""
        if not self._history:
            return np.empty((0, 4))
        return np.array([[s[n] for n in self.STATE_NAMES]
                         for s in self._history])
