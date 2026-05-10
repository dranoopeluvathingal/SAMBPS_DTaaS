"""Six-pulse diode rectifier load — idealised 120° conduction model.

This replaces the parametric ``HarmonicLoad`` with a topology-faithful
diode-bridge load. The DC side carries an inductively-smoothed current
``I_d`` driven by an external power demand (``P_dc_demand``); the AC side
phase currents follow the canonical 120°-conduction quasi-rectangular
pattern that is the actual harmonic source any active filter compensates.

Model (idealised):

    Phase a current ``i_l_a(θ)`` =  +I_d   for  θ ∈ ( π/6,  5π/6)
                                    -I_d   for  θ ∈ (7π/6, 11π/6)
                                    0      otherwise

    DC bus voltage ``v_d(θ) = max line-to-line at θ``
                          ≈ V_LL_peak * cos(θ_offset_within_60deg_sector)

    DC current  ``I_d = (P_dc_demand / V_d_avg)`` (slow update, with optional
    inductive smoothing if `L_dc` > 0).

The "iterative diode commutation" mentioned in the implementation plan
collapses to selecting which two diodes conduct (one upper, one lower);
the chosen pair is determined deterministically by which phase is the
highest and which is the lowest at the current θ. Commutation overlap is
neglected (dt → 0); a future deliverable can add it.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


@dataclass
class RectifierLoadParams:
    P_dc_demand: float = 25e3       # commanded DC bus power (W)
    V_s_rms_ll: float = 380.0
    f_grid: float = 50.0
    smoothing_tau_s: float = 5e-3   # 1st-order LP on I_d (mimics DC inductor)
    edge_softening_rad: float = 0.10 # smooth the on/off edges to reduce ringing
    enable: bool = True


class RectifierLoad:
    """6-pulse rectifier with 120°-conduction AC-side currents.

    Inputs:
        ``v_s(t)``   — three-phase grid voltage (V).
        ``i_l(t)``   — three-phase load current at PCC (A).
    """

    def __init__(self, params: RectifierLoadParams | None = None) -> None:
        self.p = params or RectifierLoadParams()
        V_phase_rms = self.p.V_s_rms_ll / math.sqrt(3.0)
        self.V_phase_peak = V_phase_rms * math.sqrt(2.0)
        self.V_LL_peak = self.p.V_s_rms_ll * math.sqrt(2.0)
        # Average DC bus voltage of an ideal 6-pulse rectifier:
        #   V_d_avg = (3·sqrt(3)/π) · V_phase_peak  ≈  1.654 · V_phase_peak
        self.V_d_avg = (3.0 * math.sqrt(3.0) / math.pi) * self.V_phase_peak
        self.omega = 2.0 * math.pi * self.p.f_grid
        # Smoothed DC current
        self._I_d = 0.0

    # ------------------------------------------------------------------ updates
    def update_demand(self, P_dc_demand: float) -> None:
        """Change the DC bus power demand (W)."""
        self.p.P_dc_demand = float(P_dc_demand)

    def _target_I_d(self) -> float:
        if self.V_d_avg <= 0:
            return 0.0
        return self.p.P_dc_demand / self.V_d_avg

    def _step_I_d(self, dt: float) -> None:
        """1st-order low-pass on I_d to mimic an inductive DC link."""
        target = self._target_I_d() if self.p.enable else 0.0
        tau = max(self.p.smoothing_tau_s, 1e-6)
        alpha = dt / (tau + dt)
        self._I_d += alpha * (target - self._I_d)

    # ------------------------------------------------------------------ exports
    def v_s(self, t: float) -> np.ndarray:
        theta = self.omega * t
        return self.V_phase_peak * np.array([
            math.sin(theta),
            math.sin(theta - 2 * math.pi / 3),
            math.sin(theta + 2 * math.pi / 3),
        ])

    def _phase_a_pulse(self, theta: float) -> float:
        """1 in (30°, 150°), -1 in (210°, 330°), with soft edges."""
        theta = theta % (2.0 * math.pi)
        eps = self.p.edge_softening_rad
        # Distance to edges of +pulse interval (π/6, 5π/6)
        if math.pi / 6 - eps < theta < 5 * math.pi / 6 + eps:
            return _smooth_window(theta, math.pi / 6, 5 * math.pi / 6, eps)
        if 7 * math.pi / 6 - eps < theta < 11 * math.pi / 6 + eps:
            return -_smooth_window(theta, 7 * math.pi / 6, 11 * math.pi / 6, eps)
        return 0.0

    def i_l(self, t: float, dt: float | None = None) -> np.ndarray:
        """Three-phase load current at time `t`. Caller passes `dt` if it
        wants the internal I_d to advance with the simulation step (for
        accurate inductive smoothing)."""
        if dt is not None and dt > 0.0:
            self._step_I_d(dt)
        else:
            # No dt provided — snap I_d to instantaneous target
            self._I_d = self._target_I_d() if self.p.enable else 0.0
        theta = self.omega * t
        return self._I_d * np.array([
            self._phase_a_pulse(theta),
            self._phase_a_pulse(theta - 2 * math.pi / 3),
            self._phase_a_pulse(theta + 2 * math.pi / 3),
        ])

    @property
    def I_d(self) -> float:
        return self._I_d

    @property
    def grid_phase(self) -> float:
        return float(self.omega)


# ----------------------------------------------------------------------------
def _smooth_window(theta: float, lo: float, hi: float, eps: float) -> float:
    """Linear ramp at the edges, flat = 1 in the middle."""
    if theta < lo + eps:
        return max(0.0, (theta - (lo - eps)) / (2 * eps))
    if theta > hi - eps:
        return max(0.0, ((hi + eps) - theta) / (2 * eps))
    return 1.0
