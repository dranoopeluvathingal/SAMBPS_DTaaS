# =============================================================================
# sambp / digital_twin / models / dc_fault_model.py
#
# DC fault current model — TR-80 WP 80.1
#
# DC faults evolve on sub-millisecond timescales — far faster than AC faults.
# Three physical mechanisms dominate:
#
# 1. CAPACITOR DISCHARGE  — dominates in first 0–5 ms
#    DC bus capacitance C discharges through fault impedance (R_f + L_cable):
#      L·dI/dt + R·I = V0  (with I(0)=0, V_C(0)=V0)
#    Overdamped (R² > 4L/C): I(t) = (V0/Ld)·exp(−α·t)·sinh(ω_d·t)
#    Underdamped (R² < 4L/C): I(t) = (V0/Z)·exp(−α·t)·sin(ω_d·t)
#    where α = R/(2L), Z = sqrt(L/C − (R/2)²), Ld = sqrt((R/2)² − L/C)
#
# 2. CABLE / BUS FAULT — sustained component from source
#    After capacitor discharges, remaining fault current is source-limited:
#      I_sustained = V_source / (R_cable + R_fault)
#
# 3. CONVERTER CURRENT LIMIT — IBR-connected sources clamp at I_max
#    I_conv(t) = I_max × (1 − exp(−t / τ_ctrl))
#    τ_ctrl ≈ 0.5–2 ms (current controller bandwidth)
#
# Combined fault current:
#   I_fault(t) = I_cap(t) + I_conv(t) + I_sustained
#
# Arc flash detection: arc has oscillating, noisy current with concurrent
# V-dip — modelled by adding a noise envelope post-peak.
#
# Public API
# ----------
#   model = DCFaultModel(bus_params, fault_params)
#   trace = model.simulate(t_end_ms=10.0, dt_us=10.0)  → DCFaultTrace
# =============================================================================

from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Parameter dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DCBusParams:
    """DC bus electrical parameters."""
    V_nom_V:      float          # nominal DC bus voltage [V]
    C_bus_F:      float = 5e-3   # bus capacitance [F]  (typical LVDC panel)
    L_cable_H:    float = 10e-6  # cable inductance [H]
    R_cable_Ohm:  float = 0.05   # cable resistance [Ω]
    I_conv_max_A: float = 500.0  # converter current limit [A]
    tau_ctrl_ms:  float = 1.0    # converter current-control time constant [ms]
    bus_class:    str   = "LVDC" # "LVDC" (48–400 V) | "MVDC" (1–35 kV)


@dataclass
class DCFaultParams:
    """DC fault characteristics."""
    fault_type:   str   = "pole_to_pole"  # "pole_to_pole" | "pole_to_ground" | "arc"
    R_fault_Ohm:  float = 0.001           # fault resistance [Ω] (bolted ≈ 0)
    fault_location_pu: float = 0.5        # distance from source [0–1]
    arc_noise_pu: float = 0.0             # arc noise amplitude [pu of peak]


# ---------------------------------------------------------------------------
# DCFaultTrace
# ---------------------------------------------------------------------------

@dataclass
class DCFaultTrace:
    """Time-domain simulation output."""
    t_ms:          np.ndarray   # time vector [ms]
    I_fault_A:     np.ndarray   # total fault current [A]
    I_cap_A:       np.ndarray   # capacitor discharge component [A]
    I_conv_A:      np.ndarray   # converter component [A]
    I_sustained_A: np.ndarray   # sustained (source) component [A]
    V_bus_V:       np.ndarray   # bus voltage [V]
    dI_dt_A_ms:    np.ndarray   # dI/dt [A/ms]
    peak_I_A:      float
    peak_dI_dt_A_ms: float
    fault_type:    str
    bus_class:     str


# ---------------------------------------------------------------------------
# DCFaultModel
# ---------------------------------------------------------------------------

class DCFaultModel:
    """
    Simulate DC fault current evolution with sub-ms resolution.

    Parameters
    ----------
    bus    : DCBusParams
    fault  : DCFaultParams
    """

    def __init__(self, bus: DCBusParams, fault: DCFaultParams) -> None:
        self._bus   = bus
        self._fault = fault

    # ------------------------------------------------------------------
    def simulate(self, t_end_ms: float = 10.0, dt_us: float = 10.0) -> DCFaultTrace:
        """
        Run DC fault simulation.

        Parameters
        ----------
        t_end_ms : simulation duration [ms]
        dt_us    : time step [µs]

        Returns
        -------
        DCFaultTrace
        """
        bus, flt = self._bus, self._fault
        dt_ms = dt_us * 1e-3
        N     = int(t_end_ms / dt_ms) + 1
        t_ms  = np.arange(N) * dt_ms

        # Effective R = cable + fault, scaled by location
        R_eff = bus.R_cable_Ohm * flt.fault_location_pu + flt.R_fault_Ohm
        L_eff = bus.L_cable_H   * flt.fault_location_pu
        C     = bus.C_bus_F
        V0    = bus.V_nom_V

        # Pole-to-ground: half voltage, series resistance for ground path
        if flt.fault_type == "pole_to_ground":
            V0    *= 0.5
            R_eff += 0.5   # ground impedance typical

        # ── Capacitor discharge component ──────────────────────────────
        I_cap = self._cap_discharge(t_ms, V0, R_eff, L_eff, C)

        # ── Converter contribution ──────────────────────────────────────
        tau_ctrl = bus.tau_ctrl_ms
        I_conv   = bus.I_conv_max_A * (1.0 - np.exp(-t_ms / max(tau_ctrl, 1e-6)))
        # Limit converter to not exceed its maximum
        I_conv   = np.minimum(I_conv, bus.I_conv_max_A)

        # ── Sustained source current ────────────────────────────────────
        I_sustained = np.full(N, V0 / max(R_eff + 0.01, 1e-9))
        # Ramp in over first 2 ms (cable inductance limits rise)
        ramp_end = int(2.0 / dt_ms)
        if ramp_end > 0:
            ramp = np.minimum(t_ms[:ramp_end] / 2.0, 1.0)
            I_sustained[:ramp_end] *= ramp

        I_fault = I_cap + I_conv + I_sustained

        # ── Arc noise ──────────────────────────────────────────────────
        if flt.fault_type == "arc" and flt.arc_noise_pu > 0:
            rng  = np.random.default_rng(seed=42)
            peak = float(np.max(I_fault))
            noise = flt.arc_noise_pu * peak * rng.standard_normal(N)
            # Noise amplitude envelope: grows after peak, represents arc instability
            env = np.minimum(t_ms / 5.0, 1.0)
            I_fault += noise * env

        # ── Bus voltage (simple RC discharge model) ─────────────────────
        tau_v  = max(R_eff * C, 1e-9)
        V_bus  = V0 * np.exp(-t_ms / (tau_v * 1e3))   # tau_v in ms
        V_bus  = np.maximum(V_bus, 0.0)

        # ── dI/dt ─────────────────────────────────────────────────────
        dI_dt = np.gradient(I_fault, dt_ms)   # A/ms

        peak_I     = float(np.max(np.abs(I_fault)))
        peak_dIdt  = float(np.max(np.abs(dI_dt)))

        return DCFaultTrace(
            t_ms=t_ms, I_fault_A=I_fault, I_cap_A=I_cap,
            I_conv_A=I_conv, I_sustained_A=I_sustained,
            V_bus_V=V_bus, dI_dt_A_ms=dI_dt,
            peak_I_A=peak_I, peak_dI_dt_A_ms=peak_dIdt,
            fault_type=flt.fault_type, bus_class=bus.bus_class,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _cap_discharge(t_ms: np.ndarray, V0: float,
                       R: float, L: float, C: float) -> np.ndarray:
        """Exact RLC discharge solution."""
        if L <= 0 or C <= 0:
            # Pure RC
            tau = max(R * C, 1e-12)
            return (V0 / max(R, 1e-9)) * np.exp(-t_ms * 1e-3 / tau)

        alpha   = R / (2 * L)          # [rad/s]
        omega_0 = 1.0 / math.sqrt(L * C)
        t_s     = t_ms * 1e-3          # convert to seconds

        disc = alpha ** 2 - omega_0 ** 2

        if disc > 1e-6:
            # Overdamped — use stable form to avoid sinh/exp overflow:
            # I = (V0 / (2L*ω_d)) * (exp(-γ₁·t) − exp(-γ₂·t))
            # where γ₁ = α − ω_d, γ₂ = α + ω_d  (both positive)
            omega_d = math.sqrt(disc)
            gamma1  = alpha - omega_d   # smaller decay rate
            gamma2  = alpha + omega_d   # larger decay rate
            I = (V0 / (2.0 * L * omega_d)) * (
                np.exp(-gamma1 * t_s) - np.exp(-gamma2 * t_s)
            )
        elif disc < -1e-6:
            # Underdamped
            omega_d = math.sqrt(-disc)
            I = (V0 / (L * omega_d)) * np.exp(-alpha * t_s) * np.sin(omega_d * t_s)
        else:
            # Critically damped
            I = (V0 / L) * t_s * np.exp(-alpha * t_s)

        return I
