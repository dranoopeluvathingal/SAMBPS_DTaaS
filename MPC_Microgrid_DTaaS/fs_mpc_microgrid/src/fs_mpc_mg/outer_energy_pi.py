"""Outer DC-link voltage controller in the energy domain.

Implements Eqs. (8)–(11) of Perez & Flores-Bahamonde (2016):

    E_c     = (1/2) * C * v_dc^2
    E_c_ref = (1/2) * C * v_dc_ref^2

    G(s)    = E_c(s) / I_s(s) = (3 V_s / 2) / (s + 2/RC)         (11)

    I_s_amp(t) = K_p * e_E(t) + K_i * integral(e_E)               + (optional feedforward)

The amplitude `I_s_amp` is then multiplied by the PLL unit vector to form
the three-phase grid current reference `i_s_ref(t)` consumed by the inner
FS-MPC. This avoids small-signal linearisation around `v_dc*` because the
plant is globally linear in `I_s` (not in `v_dc`).
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class EnergyPIParams:
    C: float = 1000e-6
    R: float = 1e4
    V_s_phase_peak: float = 380.0 * np.sqrt(2.0) / np.sqrt(3.0)  # peak phase voltage
    v_dc_ref: float = 900.0

    # Closed-loop second-order target: zeta = 0.7, omega_n ~ 200 rad/s
    # gives ~20 ms settling time.
    omega_n: float = 200.0
    zeta: float = 0.7

    # Feedforward toggle: if True, we add (p_dc + p_l) / (3 V_s / 2)
    # to the PI output, eliminating steady-state I_s_amp swings during
    # mode transitions. Disabled by default to mirror [F] exactly.
    feedforward: bool = False

    # Saturation on I_s_amp (peak)
    I_s_max: float = 300.0


class EnergyPI:
    """PI controller acting on capacitor energy E_c (NOT v_dc directly).

    Output: positive scalar I_s_amp (peak amplitude of grid-current reference).
    """

    def __init__(self, params: EnergyPIParams | None = None) -> None:
        self.p = params or EnergyPIParams()

        # Plant gain k = 3 V_s / 2 (treating V_s as PHASE peak here, matching [F])
        # In [F] V_s is phase RMS; we use phase peak so the math sees an
        # equivalent gain. The PI is tuned in continuous-time then digitised.
        k_plant = 1.5 * self.p.V_s_phase_peak

        # Standard pole-placement against (k_plant) / (s + 2/RC)
        a = 2.0 / (self.p.R * self.p.C)  # plant pole
        # Closed loop should be: omega_n^2 / (s^2 + 2 zeta omega_n s + omega_n^2)
        # With PI Kp + Ki/s, closed-loop denom: s^2 + (Kp*k + a) s + Ki*k
        # Match coefficients:
        self.K_p = (2.0 * self.p.zeta * self.p.omega_n - a) / k_plant
        self.K_i = (self.p.omega_n ** 2) / k_plant

        # Integrator state
        self._integ = 0.0
        self.E_c_ref = 0.5 * self.p.C * self.p.v_dc_ref ** 2

    # ------------------------------------------------------------------
    def update(
        self,
        v_dc: float,
        dt: float,
        i_dc: float = 0.0,
        p_load: float = 0.0,
    ) -> float:
        """Run one PI tick. Returns I_s_amp (peak grid-current amplitude).

        `dt` is the controller sample period (typically T_s_outer = 200 µs).
        `i_dc` and `p_load` are used only when feedforward is enabled.
        """
        E_c = 0.5 * self.p.C * v_dc ** 2
        err = self.E_c_ref - E_c
        # anti-windup: simple clamp on integrator
        self._integ += err * dt
        u = self.K_p * err + self.K_i * self._integ

        if self.p.feedforward:
            k_plant = 1.5 * self.p.V_s_phase_peak
            ff = (i_dc * v_dc + p_load) / max(k_plant, 1e-9)
            u = u + ff

        # Saturate (and back-calculate integrator if hitting limit)
        u_sat = np.clip(u, -self.p.I_s_max, self.p.I_s_max)
        if u_sat != u:
            # Conditional integration: undo the update
            self._integ -= err * dt
        return float(u_sat)

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._integ = 0.0

    @property
    def gains(self) -> tuple[float, float]:
        return self.K_p, self.K_i
