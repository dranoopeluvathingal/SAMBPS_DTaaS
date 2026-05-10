"""Phase-locked loops.

Two implementations:

  IdealPLL  : ground-truth phase from grid frequency. Useful for clean tests.

  SOGIPLL   : Three-phase positive-sequence PLL based on Rodriguez et al.
              2006 [16] of the focal paper. Uses a SOGI-QSG bank on (αβ)
              components to extract the fundamental positive sequence,
              then a PI loop on the q-projection drives the locked angle.

Both expose the same ``update(t, v_s_abc=None) -> (theta, omega, unit_3p)``
interface so they are drop-in interchangeable in ICAAgent.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


# ---------------------------------------------------------------------------
# Ideal PLL (legacy)
# ---------------------------------------------------------------------------

@dataclass
class IdealPLL:
    """Ground-truth PLL for noise-free testing.

    Tracks the phase angle of phase-a positive-sequence voltage with no error.
    Compatible signature: ``update(t, v_s_abc=None)`` — v_s_abc is ignored.
    """

    f_grid: float = 50.0
    phase_offset: float = 0.0

    def update(self, t: float, v_s_abc: np.ndarray | None = None
               ) -> tuple[float, float, np.ndarray]:
        omega = 2.0 * np.pi * self.f_grid
        theta = omega * t + self.phase_offset
        unit = np.array([
            math.sin(theta),
            math.sin(theta - 2 * math.pi / 3),
            math.sin(theta + 2 * math.pi / 3),
        ])
        return float(theta), float(omega), unit


# ---------------------------------------------------------------------------
# SOGI-PLL (three-phase, positive-sequence)
# ---------------------------------------------------------------------------

@dataclass
class SOGIPLLParams:
    """Tuning parameters for the SOGI-PLL."""
    f_grid_nominal: float = 50.0
    T_s: float = 20e-6
    k_sogi: float = 1.4142135623730951      # sqrt(2): standard critical damping
    omega_n: float = 100.0                   # PI loop natural freq (rad/s)
    zeta: float = 0.707                      # PI loop damping
    V_phase_peak_nominal: float = 310.0      # for gain normalisation


class SOGIPLL:
    """Three-phase positive-sequence PLL with SOGI-QSG quadrature signal generation.

    Algorithm:
        1. Clarke transform v_abc → (v_α, v_β).
        2. Two SOGI-QSGs (one per αβ component) yield the fundamental in-phase
           y' and 90°-shifted qy'.
        3. Positive-sequence calculator (DDSRF):
                v_α+ = 0.5 (y_α  - q*y_β)
                v_β+ = 0.5 (q*y_α +  y_β)
        4. Sine-convention Park: v_q = v_α+ cos(θ_pll) + v_β+ sin(θ_pll).
           Drives to 0 when θ_pll equals the grid phase angle.
        5. PI on v_q produces Δω; ω_pll = ω_nom + Δω; integrate ω → θ.

    State is advanced once per ``update()`` call **only when v_s_abc is given**;
    subsequent calls without v_s_abc act as queries that extrapolate θ at the
    requested time using the locked ω. This keeps the existing ICAAgent two-call
    pattern (next-sample active reference + 90°-lagged reactive reference)
    working unchanged.
    """

    def __init__(self, params: SOGIPLLParams | None = None) -> None:
        self.p = params or SOGIPLLParams()
        self.f_grid = self.p.f_grid_nominal       # alias kept for ICAAgent compat
        self._omega_nom = 2.0 * math.pi * self.p.f_grid_nominal
        self._omega = self._omega_nom
        self._theta = 0.0
        self._integ = 0.0
        # SOGI-QSG states for v_α, v_β
        self._y_a_alpha = 0.0
        self._y_q_alpha = 0.0
        self._y_a_beta = 0.0
        self._y_q_beta = 0.0
        # PI gains
        Vp = max(self.p.V_phase_peak_nominal, 1e-3)
        self._K_p = 2.0 * self.p.zeta * self.p.omega_n / Vp
        self._K_i = (self.p.omega_n ** 2) / Vp
        # Tracking
        self._last_t: float | None = None

    # ------------------------------------------------------------------
    @staticmethod
    def _clarke(v_abc: np.ndarray) -> tuple[float, float]:
        v_a, v_b, v_c = float(v_abc[0]), float(v_abc[1]), float(v_abc[2])
        v_alpha = v_a
        v_beta = (v_b - v_c) / math.sqrt(3.0)
        return v_alpha, v_beta

    # ------------------------------------------------------------------
    def _tick(self, v_abc: np.ndarray) -> None:
        T = self.p.T_s
        v_alpha, v_beta = self._clarke(v_abc)
        omega = self._omega
        ks = self.p.k_sogi

        # SOGI-QSG on v_alpha
        eps_a = ks * omega * (v_alpha - self._y_a_alpha) - omega * self._y_q_alpha
        self._y_a_alpha += T * eps_a
        self._y_q_alpha += T * omega * self._y_a_alpha

        # SOGI-QSG on v_beta
        eps_b = ks * omega * (v_beta - self._y_a_beta) - omega * self._y_q_beta
        self._y_a_beta += T * eps_b
        self._y_q_beta += T * omega * self._y_a_beta

        # Positive-sequence calculator
        v_alpha_pos = 0.5 * (self._y_a_alpha - self._y_q_beta)
        v_beta_pos = 0.5 * (self._y_q_alpha + self._y_a_beta)

        # Sine-convention Park projection — locks when θ_pll == θ_grid
        c, s = math.cos(self._theta), math.sin(self._theta)
        v_q = v_alpha_pos * c + v_beta_pos * s

        # PI on v_q drives Δω
        self._integ += self._K_i * v_q * T
        delta_omega = self._K_p * v_q + self._integ
        self._omega = self._omega_nom + delta_omega
        self._theta = (self._theta + self._omega * T) % (2.0 * math.pi)

    # ------------------------------------------------------------------
    def update(
        self,
        t: float,
        v_s_abc: np.ndarray | None = None,
    ) -> tuple[float, float, np.ndarray]:
        """Advance state if v_s_abc given. Always returns (theta_at_t, omega, unit)."""
        if v_s_abc is not None:
            if self._last_t is None or t > self._last_t:
                self._tick(np.asarray(v_s_abc, dtype=float))
                self._last_t = t

        if self._last_t is None:
            theta_t = self._omega_nom * t
        else:
            theta_t = self._theta + self._omega * (t - self._last_t)

        unit = np.array([
            math.sin(theta_t),
            math.sin(theta_t - 2.0 * math.pi / 3.0),
            math.sin(theta_t + 2.0 * math.pi / 3.0),
        ])
        return float(theta_t), float(self._omega), unit

    # ------------------------------------------------------------------
    @property
    def theta(self) -> float:
        return self._theta

    @property
    def omega(self) -> float:
        return self._omega

    @property
    def locked(self) -> bool:
        """Heuristic: locked when ω is within 1% of nominal and we've ticked."""
        return self._last_t is not None and abs(self._omega - self._omega_nom) / self._omega_nom < 0.01

    def reset(self) -> None:
        self.__init__(self.p)
