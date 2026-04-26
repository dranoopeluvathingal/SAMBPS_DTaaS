"""Load model: linear RL load + harmonic current injector.

This is a **simplified proxy** for the 6-pulse diode rectifier described in
the focal paper. We model the load current at the PCC as:

    i_l(t) = I_fund * [sin(theta), sin(theta - 2pi/3), sin(theta + 2pi/3)]
           + sum_h I_h * [sin(h*theta - phi_h_a), ..., ...]

with `theta = 2*pi*f*t`. By default we inject the dominant 6-pulse-rectifier
harmonics (5th and 7th) at the textbook 1/h amplitudes. A future deliverable
(D03 full) will replace this with an iterative diode-commutation solver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np


@dataclass
class HarmonicLoadParams:
    """Linear RL + harmonic injector parameters.

    Fundamental amplitude is computed from S_fund_rms and grid voltage.
    """

    P_fund: float = 25e3            # fundamental active power (W)
    Q_fund: float = 0.0             # fundamental reactive power (VAr)
    V_s_rms_ll: float = 380.0       # line-line RMS grid voltage (V)
    f_grid: float = 50.0            # Hz

    # Harmonic content as a dict { order : relative_amplitude }.
    # Default = textbook 6-pulse rectifier (5th and 7th).
    harmonics: dict[int, float] = field(
        default_factory=lambda: {5: 1.0 / 5.0, 7: 1.0 / 7.0, 11: 1.0 / 11.0, 13: 1.0 / 13.0}
    )
    harmonic_phase_lag: bool = True   # use textbook negative-sequence for 5th, etc.


class HarmonicLoad:
    """Models i_l(t) for a load drawing both fundamental P/Q and characteristic harmonics."""

    def __init__(self, params: HarmonicLoadParams | None = None) -> None:
        self.p = params or HarmonicLoadParams()

        # Convert P, Q into fundamental current amplitude and phase
        V_phase_rms = self.p.V_s_rms_ll / np.sqrt(3.0)
        V_phase_peak = V_phase_rms * np.sqrt(2.0)
        S = np.hypot(self.p.P_fund, self.p.Q_fund)
        I_rms = S / (3.0 * V_phase_rms) if V_phase_rms > 0 else 0.0
        self.I_fund_peak = I_rms * np.sqrt(2.0)
        self.phi_fund = np.arctan2(self.p.Q_fund, self.p.P_fund)
        # Negative => lagging current (inductive). For load convention
        # i_l = I*sin(theta - phi), with phi > 0 if Q > 0.

        self.omega = 2.0 * np.pi * self.p.f_grid
        self.V_phase_peak = V_phase_peak

    # ---------------------------------------------------------------
    def i_l(self, t: float) -> np.ndarray:
        """Return three-phase load current at time `t`."""
        theta = self.omega * t
        # Fundamental
        a = np.sin(theta - self.phi_fund)
        b = np.sin(theta - self.phi_fund - 2 * np.pi / 3)
        c = np.sin(theta - self.phi_fund + 2 * np.pi / 3)
        i = self.I_fund_peak * np.array([a, b, c])

        # Harmonics: rectifier-style
        for h, rel_amp in self.p.harmonics.items():
            sign = 1.0
            # 5th, 11th are negative-sequence; 7th, 13th are positive-sequence
            if self.p.harmonic_phase_lag and (h % 6 == 5):
                sign = -1.0
            ah = np.sin(h * theta - self.phi_fund)
            bh = np.sin(h * theta - self.phi_fund - sign * 2 * np.pi / 3)
            ch = np.sin(h * theta - self.phi_fund + sign * 2 * np.pi / 3)
            i = i + (rel_amp * self.I_fund_peak) * np.array([ah, bh, ch])

        return i

    def v_s(self, t: float) -> np.ndarray:
        """Three-phase ideal grid voltage at time `t`."""
        theta = self.omega * t
        return self.V_phase_peak * np.array(
            [
                np.sin(theta),
                np.sin(theta - 2 * np.pi / 3),
                np.sin(theta + 2 * np.pi / 3),
            ]
        )

    @property
    def grid_phase(self) -> float:
        return float(self.omega)
