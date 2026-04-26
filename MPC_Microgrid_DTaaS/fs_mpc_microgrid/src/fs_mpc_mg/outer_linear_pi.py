"""Outer DC-link voltage controller — small-signal-linearised PI on v_dc.

Linearises the nonlinear DC-link power balance

    C * v_dc * dv_dc/dt = (3/2) * V_s * I_s_amp - v_dc^2 / R + i_dc * v_dc

around v_dc = v_dc_ref. The resulting first-order plant is

    G_lin(s) = Δv_dc(s) / ΔI_s_amp(s) = (3 V_s / (2 C v_dc_ref)) / (s + 2/RC)

Pole-placement gives PI gains for the same closed-loop second-order target
as EnergyPI (zeta, omega_n), so the bandwidths match around the
linearisation point. Away from v_dc_ref the effective plant gain shifts —
the energy-domain trick used by EnergyPI is what removes that dependence
globally. This controller is therefore expected to overshoot more than
EnergyPI on large transients.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class LinearVdcPIParams:
    C: float = 1000e-6
    R: float = 1e4
    V_s_phase_peak: float = 380.0 * np.sqrt(2.0) / np.sqrt(3.0)
    v_dc_ref: float = 900.0

    # Closed-loop second-order target — same as EnergyPI defaults so the
    # two controllers have matched bandwidth at the linearisation point.
    omega_n: float = 200.0
    zeta: float = 0.7

    # Saturation on I_s_amp (peak)
    I_s_max: float = 300.0


class LinearVdcPI:
    """PI controller acting on v_dc directly, gains designed against the
    small-signal linearised plant around v_dc_ref.

    Output: positive scalar I_s_amp (peak amplitude of grid-current reference).
    """

    def __init__(self, params: LinearVdcPIParams | None = None) -> None:
        self.p = params or LinearVdcPIParams()

        # Plant pole (shared with the energy-domain plant):
        a = 2.0 / (self.p.R * self.p.C)
        # Linearised plant gain. Comes from chain-rule on E_c = (1/2) C v_dc^2:
        # dE_c/dv_dc = C * v_dc, evaluated at v_dc_ref.
        k_lin = (1.5 * self.p.V_s_phase_peak) / (self.p.C * self.p.v_dc_ref)

        # Match closed-loop denom s^2 + 2 zeta omega_n s + omega_n^2 against
        # s^2 + (Kp k + a) s + Ki k:
        self.K_p = (2.0 * self.p.zeta * self.p.omega_n - a) / k_lin
        self.K_i = (self.p.omega_n ** 2) / k_lin

        self._integ = 0.0

    # ------------------------------------------------------------------
    def update(
        self,
        v_dc: float,
        dt: float,
        i_dc: float = 0.0,
        p_load: float = 0.0,
    ) -> float:
        """Run one PI tick. Returns I_s_amp (peak grid-current amplitude).

        `i_dc` and `p_load` are accepted for interface symmetry with
        EnergyPI (so both controllers are drop-in compatible with the
        Simulator) but are unused here — there is no feedforward.
        """
        del i_dc, p_load
        err = self.p.v_dc_ref - v_dc
        self._integ += err * dt
        u = self.K_p * err + self.K_i * self._integ

        u_sat = float(np.clip(u, -self.p.I_s_max, self.p.I_s_max))
        if u_sat != u:
            # Conditional integration: undo the update on saturation
            self._integ -= err * dt
        return u_sat

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._integ = 0.0

    @property
    def gains(self) -> tuple[float, float]:
        return self.K_p, self.K_i
