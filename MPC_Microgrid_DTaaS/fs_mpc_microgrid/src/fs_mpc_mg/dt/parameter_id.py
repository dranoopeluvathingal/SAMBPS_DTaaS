"""Recursive Least Squares (RLS) identifier for plant parameters L and r.

Discretising AC-side Eq. (2) with sample T:
    i_m(k+1) = a * i_m(k) + b * (v_s(k) - M s v_dc(k))      where
    a = 1 - r*T/L,   b = T/L

Per phase, this is linear in [a, b]. We run a per-phase RLS estimator with
forgetting factor `lambda` (close to 1.0 for slow drift). After enough
samples the estimates converge; we recover:

    L = T / b
    r = (1 - a) * L / T = (1 - a) / b

The algorithm is per-phase but we ensemble across phases by averaging
the converged (a, b).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from ..plant import M_MATRIX


@dataclass
class RLSResult:
    L: float = float("nan")
    r: float = float("nan")
    n_samples: int = 0
    converged: bool = False     # True after `min_samples` and bounded conditioning


class RLSIdentifier:
    """Per-ICA RLS estimator. Update once per ICA telemetry tick."""

    def __init__(
        self,
        T_s: float,
        forgetting: float = 0.999,
        init_L: float = 1e-3,
        init_r: float = 50e-3,
        P0: float = 1e3,
        min_samples: int = 200,
    ) -> None:
        self.T_s = float(T_s)
        self.lam = float(forgetting)
        self.min_samples = int(min_samples)
        self.n = 0

        # Per-phase parameter vector theta_phase = [a, b]
        # Initialise from prior knowledge.
        a0 = 1.0 - init_r * T_s / init_L
        b0 = T_s / init_L
        self._theta = [np.array([a0, b0]) for _ in range(3)]
        # Per-phase covariance
        self._P = [P0 * np.eye(2) for _ in range(3)]

        self._last_i_m: np.ndarray | None = None
        self._last_v_s: np.ndarray | None = None
        self._last_s: np.ndarray | None = None
        self._last_v_dc: float | None = None

    # ------------------------------------------------------------------
    def update(
        self,
        i_m_next: np.ndarray,
        i_m_now: np.ndarray,
        v_s_now: np.ndarray,
        s_now: np.ndarray,
        v_dc_now: float,
    ) -> RLSResult:
        """One RLS update. All inputs are at time `k`; `i_m_next` is at time `k+1`."""
        # Per-phase regressor: phi = [i_m_now[ph], v_s[ph] - (M @ s)[ph] * v_dc]
        Msv = M_MATRIX @ np.asarray(s_now, dtype=float) * float(v_dc_now)
        for ph in range(3):
            phi = np.array([float(i_m_now[ph]), float(v_s_now[ph] - Msv[ph])])
            y = float(i_m_next[ph])
            P = self._P[ph]
            # Standard RLS update
            denom = self.lam + phi @ P @ phi
            if denom < 1e-12:
                continue
            K = (P @ phi) / denom
            err = y - phi @ self._theta[ph]
            self._theta[ph] = self._theta[ph] + K * err
            self._P[ph] = (P - np.outer(K, phi @ P)) / self.lam

        self.n += 1
        return self._result()

    # ------------------------------------------------------------------
    def _result(self) -> RLSResult:
        a_avg = float(np.mean([t[0] for t in self._theta]))
        b_avg = float(np.mean([t[1] for t in self._theta]))
        L = self.T_s / b_avg if abs(b_avg) > 1e-12 else float("nan")
        r = (1.0 - a_avg) / b_avg if abs(b_avg) > 1e-12 else float("nan")
        converged = self.n >= self.min_samples and 1e-5 < L < 1.0 and -1.0 < r < 100.0
        return RLSResult(L=L, r=r, n_samples=self.n, converged=converged)

    # ------------------------------------------------------------------
    @property
    def estimate(self) -> RLSResult:
        return self._result()

    def reset(self) -> None:
        self.__init__(self.T_s, self.lam,
                      init_L=self.T_s / float(self._theta[0][1]) if abs(self._theta[0][1]) > 1e-12 else 1e-3,
                      init_r=50e-3,
                      P0=1e3,
                      min_samples=self.min_samples)
