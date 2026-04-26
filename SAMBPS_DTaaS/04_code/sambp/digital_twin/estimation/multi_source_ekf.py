# =============================================================================
# sambp / digital_twin / estimation / multi_source_ekf.py
#
# Multi-source EKF estimator — TR-70 WP 70.2
#
# Extends the single-source EKFEstimator to handle N simultaneous IBR
# sources in a meshed network.  Each source has its own state vector and
# Kalman filter, but sources share information via a cross-coupling matrix
# that propagates fault current observations between adjacent sources.
#
# State vector per source (same as EKFEstimator):
#   x = [k_ibr, Z_line, alpha, f_gfm]
#
# Cross-coupling
# --------------
# When source j detects a voltage dip (V_j < 0.85 pu) that is also seen
# at source i (V_i < 0.90 pu), the fault-location estimate from j is
# blended into i's estimate with weight w_ij = 1 / (1 + d_ij / d_0)
# where d_ij is the electrical distance between sources (from Z matrix).
#
# Per-source confidence
# ---------------------
# confidence_i = base_conf × (1 – σ_alpha_i / π) × (1 – |f_gfm_i – 0.5|×0.3)
# High f_gfm or high alpha uncertainty → lower confidence.
#
# Public API
# ----------
#   mekf = MultiSourceEKF(source_names, z_coupling_matrix)
#   mekf.update(t, observations)   → Dict[str, SourceEstimate]
#   mekf.reset()
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# SourceEstimate
# ---------------------------------------------------------------------------

@dataclass
class SourceEstimate:
    """EKF state estimate for one IBR source."""
    name:       str
    k_ibr:      float    # IBR penetration at this source [0,1]
    z_line:     float    # apparent line impedance [pu]
    alpha:      float    # fault location [0=near, 1=far]
    f_gfm:      float    # GFM fraction [0,1]
    confidence: float    # estimation confidence [0,1]
    sigma:      float    # state uncertainty (trace of P) [pu]
    ekf_state:  dict     # convenience dict for downstream modules


# ---------------------------------------------------------------------------
# Per-source scalar EKF  (linear approximation — full NL EKF reserved for HIL)
# ---------------------------------------------------------------------------

class _ScalarEKF:
    """
    Lightweight per-source EKF operating on a 4-element state vector.
    Process: random walk. Observation: direct noisy measurement of each state.
    """
    DIM = 4  # [k_ibr, z_line, alpha, f_gfm]

    # Process noise covariance (diagonal)
    _Q_DIAG = np.array([1e-5, 1e-5, 5e-4, 1e-5])
    # Measurement noise covariance (diagonal, per state)
    _R_DIAG = np.array([1e-3, 2e-3, 1e-2, 1e-3])

    def __init__(self, x0: np.ndarray) -> None:
        self._x = x0.copy().astype(float)
        self._P = np.diag([1e-3, 1e-3, 1e-2, 1e-3])
        self._Q = np.diag(self._Q_DIAG)
        self._R = np.diag(self._R_DIAG)
        self._I = np.eye(self.DIM)

    def predict(self) -> None:
        """Time update: random-walk model (F = I)."""
        self._P = self._P + self._Q

    def update(self, z: np.ndarray) -> None:
        """
        Measurement update.  z is a noisy observation of the full state.
        Missing / invalid observations are passed as NaN and skipped.
        """
        valid = ~np.isnan(z)
        if not np.any(valid):
            return
        H = np.diag(valid.astype(float))
        R = self._R.copy()
        R[~valid, ~valid] = 1e6   # inflate noise for missing obs

        S = H @ self._P @ H.T + R
        K = self._P @ H.T @ np.linalg.solve(S.T, H).T
        innov = np.where(valid, z - self._x, 0.0)
        self._x = self._x + K @ innov
        self._P = (self._I - K @ H) @ self._P
        # Clip state to physical bounds
        self._x[0] = np.clip(self._x[0], 0.0, 1.0)   # k_ibr
        self._x[1] = np.clip(self._x[1], 1e-4, 1.0)  # z_line
        self._x[2] = np.clip(self._x[2], 0.0, 1.0)   # alpha
        self._x[3] = np.clip(self._x[3], 0.0, 1.0)   # f_gfm

    @property
    def x(self) -> np.ndarray:
        return self._x.copy()

    @property
    def P(self) -> np.ndarray:
        return self._P.copy()

    @property
    def sigma(self) -> float:
        return float(np.trace(self._P))


# ---------------------------------------------------------------------------
# MultiSourceEKF
# ---------------------------------------------------------------------------

class MultiSourceEKF:
    """
    Simultaneous N-source EKF for a meshed IBR network.

    Parameters
    ----------
    source_names     : ordered list of source identifiers
    z_coupling       : NxN electrical distance matrix [pu]; z_coupling[i,j]
                       is the Thevenin impedance between source i and j.
                       Use None for diagonal (no cross-coupling).
    x0               : optional dict of initial states per source name
    coupling_d0      : reference distance for cross-coupling weight [pu]
    """

    _DEFAULT_X0 = np.array([0.60, 0.050, 0.50, 0.50])  # [k_ibr,z_line,alpha,f_gfm]

    def __init__(self,
                 source_names: List[str],
                 z_coupling: Optional[np.ndarray] = None,
                 x0: Optional[Dict[str, np.ndarray]] = None,
                 coupling_d0: float = 0.10) -> None:
        self._names = list(source_names)
        self._n     = len(source_names)
        self._d0    = coupling_d0

        # Build coupling matrix
        if z_coupling is not None:
            self._Z = np.array(z_coupling, dtype=float)
        else:
            self._Z = np.eye(self._n) * 1000.0  # large → no coupling

        # Initialise per-source EKFs
        self._ekfs: Dict[str, _ScalarEKF] = {}
        for name in self._names:
            init = (x0 or {}).get(name, self._DEFAULT_X0.copy())
            self._ekfs[name] = _ScalarEKF(np.array(init, dtype=float))

        # Last estimates
        self._last: Dict[str, SourceEstimate] = {}

    # ------------------------------------------------------------------
    def update(self,
               t: float,
               observations: Dict[str, dict]) -> Dict[str, SourceEstimate]:
        """
        Run one EKF cycle for all sources.

        Parameters
        ----------
        t            : current time [s]
        observations : dict source_name → observation dict with keys:
                       'k_ibr', 'z_line', 'alpha', 'f_gfm' (NaN if unknown),
                       'V_pu' (terminal voltage, for cross-coupling)

        Returns
        -------
        Dict[str, SourceEstimate]
        """
        # ── Predict step for all sources ─────────────────────────────
        for ekf in self._ekfs.values():
            ekf.predict()

        # ── Cross-coupling: blend alpha estimates between close sources
        alpha_obs = {}
        v_obs     = {}
        for name, obs in observations.items():
            alpha_obs[name] = float(obs.get('alpha', float('nan')))
            v_obs[name]     = float(obs.get('V_pu', 1.0))

        # Detect soureces with voltage dip (fault visibility)
        dip_sources = [n for n in self._names
                       if v_obs.get(n, 1.0) < 0.90]

        # Blend alpha estimates across coupled sources
        blended_alpha = dict(alpha_obs)
        if len(dip_sources) >= 2:
            name_idx = {n: i for i, n in enumerate(self._names)}
            for i, ni in enumerate(self._names):
                if ni not in dip_sources:
                    continue
                contrib_sum  = 0.0
                weight_total = 0.0
                for j, nj in enumerate(self._names):
                    if ni == nj or nj not in dip_sources:
                        continue
                    a_j = alpha_obs.get(nj, float('nan'))
                    if math.isnan(a_j):
                        continue
                    d_ij = float(self._Z[i, j])
                    w    = 1.0 / (1.0 + d_ij / self._d0)
                    contrib_sum  += w * a_j
                    weight_total += w
                if weight_total > 0:
                    own = alpha_obs.get(ni, float('nan'))
                    own_w = 0.70  # own observation weight
                    if not math.isnan(own):
                        blended_alpha[ni] = (own_w * own + (1 - own_w) * contrib_sum / weight_total)
                    else:
                        blended_alpha[ni] = contrib_sum / weight_total

        # ── Update step ───────────────────────────────────────────────
        results: Dict[str, SourceEstimate] = {}
        for name in self._names:
            obs   = observations.get(name, {})
            ekf   = self._ekfs[name]
            z_vec = np.array([
                float(obs.get('k_ibr',  float('nan'))),
                float(obs.get('z_line', float('nan'))),
                blended_alpha.get(name, float(obs.get('alpha', float('nan')))),
                float(obs.get('f_gfm',  float('nan'))),
            ])
            ekf.update(z_vec)
            x = ekf.x
            sigma = ekf.sigma

            # Confidence
            conf = self._confidence(x, sigma)

            est = SourceEstimate(
                name=name,
                k_ibr=round(float(x[0]), 4),
                z_line=round(float(x[1]), 5),
                alpha=round(float(x[2]), 4),
                f_gfm=round(float(x[3]), 4),
                confidence=round(conf, 4),
                sigma=round(sigma, 6),
                ekf_state={
                    'k_ibr':  round(float(x[0]), 4),
                    'z_line': round(float(x[1]), 5),
                    'alpha':  round(float(x[2]), 4),
                    'f_gfm':  round(float(x[3]), 4),
                },
            )
            results[name] = est
            self._last[name] = est

        return results

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset all EKF filters to default initial state."""
        for name in self._names:
            self._ekfs[name] = _ScalarEKF(self._DEFAULT_X0.copy())
        self._last.clear()

    # ------------------------------------------------------------------
    @property
    def source_names(self) -> List[str]:
        return list(self._names)

    @property
    def last_estimates(self) -> Dict[str, SourceEstimate]:
        return dict(self._last)

    # ------------------------------------------------------------------
    @staticmethod
    def _confidence(x: np.ndarray, sigma: float) -> float:
        alpha_unc = min(1.0, sigma / 4.0)
        gfm_pen   = abs(float(x[3]) - 0.5) * 0.3
        return max(0.10, 1.0 - alpha_unc - gfm_pen)
