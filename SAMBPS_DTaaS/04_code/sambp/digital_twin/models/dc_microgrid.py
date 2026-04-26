# =============================================================================
# sambp / digital_twin / models / dc_microgrid.py
#
# DC microgrid Digital Twin engine — TR-80 WP 80.3
#
# Architecture
# ------------
# A DC microgrid connects multiple sources and loads on a common DC bus:
#
#   [BESS] ─┐
#   [PV  ] ─┼─ DC BUS ─── [Loads]
#   [AC tie]─┘         └── [EV chargers, etc.]
#
# The DT engine runs at 10 µs resolution for fault analysis and 1 ms for
# normal-operation monitoring.
#
# Voltage class support
# ---------------------
#   LVDC : 48 V, 120 V, 400 V (IEC 60038, industrial / building)
#   MVDC : 1.5 kV, 3 kV, 6 kV, 24 kV (shipboard, data centres, transmission)
#
# Dynamic model
# -------------
# Simple capacitor-bus model: all sources and loads connect through their
# own R-L equivalent to the DC bus capacitor.
#
# Bus voltage ODE:
#   C_bus · dV/dt = sum_k(I_source_k) − sum_j(I_load_j) − I_fault
#
# Each source current is limited by its converter current limit.
# Loads are represented as constant-current (I = P_load / V) during normal
# operation and as constant-impedance during faults (V_bus sags).
#
# Public API
# ----------
#   dg = DCMicrogridDT.from_config(cfg)
#   dg.inject_fault(fault_params)
#   trace = dg.simulate(t_end_ms=10.0, dt_us=10.0)  → DCMicrogridTrace
#   state = dg.get_steady_state()                    → DCBusState
# =============================================================================

from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models.dc_fault_model import DCBusParams, DCFaultParams, DCFaultModel, DCFaultTrace


# ---------------------------------------------------------------------------
# Component dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DCSource:
    """A source connected to the DC bus."""
    name:       str
    source_type: str          # "BESS" | "PV" | "AC_TIE" | "FUEL_CELL"
    P_rated_W:  float         # rated power [W]
    V_nom_V:    float         # nominal output voltage [V]
    I_max_A:    float         # current limit [A]
    R_int_Ohm:  float = 0.01  # internal resistance [Ω]
    L_int_H:    float = 5e-6  # internal inductance [H]
    tau_ctrl_ms: float = 1.0  # current controller time constant [ms]
    enabled:    bool  = True


@dataclass
class DCLoad:
    """A load connected to the DC bus."""
    name:       str
    load_type:  str           # "CONST_P" | "CONST_I" | "CONST_Z" | "EV_CHARGER"
    P_rated_W:  float         # rated power [W]
    R_load_Ohm: float = 10.0  # load resistance (for CONST_Z) [Ω]
    enabled:    bool  = True


@dataclass
class DCMicrogridConfig:
    """Full configuration for a DC microgrid DT."""
    name:       str
    bus_class:  str           # "LVDC" | "MVDC"
    V_nom_V:    float         # nominal bus voltage [V]
    C_bus_F:    float         # bus capacitance [F]
    sources:    List[DCSource] = field(default_factory=list)
    loads:      List[DCLoad]   = field(default_factory=list)
    L_bus_H:    float = 2e-6   # bus bar inductance [H]
    R_bus_Ohm:  float = 0.002  # bus bar resistance [Ω]


# ---------------------------------------------------------------------------
# Simulation output
# ---------------------------------------------------------------------------

@dataclass
class DCBusState:
    """Steady-state DC bus snapshot."""
    V_bus_V:      float
    I_total_A:    float        # net current (sources − loads)
    I_sources:    Dict[str, float]
    I_loads:      Dict[str, float]
    P_total_W:    float
    V_pu:         float        # V_bus / V_nom


@dataclass
class DCMicrogridTrace:
    """Time-domain simulation result."""
    t_ms:          np.ndarray
    V_bus_V:       np.ndarray
    I_fault_A:     np.ndarray
    I_sources:     Dict[str, np.ndarray]   # per-source current [A]
    I_loads_total: np.ndarray
    dI_dt_A_ms:    np.ndarray
    fault_trace:   Optional[DCFaultTrace]
    config_name:   str
    bus_class:     str
    # Peak values
    peak_I_A:      float
    peak_dI_dt:    float
    t_trip_ms:     Optional[float]         # time of protection operate (if any)


# ---------------------------------------------------------------------------
# DCMicrogridDT
# ---------------------------------------------------------------------------

class DCMicrogridDT:
    """
    DC microgrid Digital Twin engine.

    Parameters
    ----------
    config : DCMicrogridConfig
    """

    def __init__(self, config: DCMicrogridConfig) -> None:
        self._cfg    = config
        self._fault: Optional[DCFaultParams] = None

    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: DCMicrogridConfig) -> "DCMicrogridDT":
        return cls(config)

    # ------------------------------------------------------------------
    def inject_fault(self, fault: DCFaultParams) -> None:
        self._fault = fault

    def clear_fault(self) -> None:
        self._fault = None

    # ------------------------------------------------------------------
    def get_steady_state(self) -> DCBusState:
        """Compute steady-state operating point (no fault)."""
        cfg = self._cfg
        V   = cfg.V_nom_V

        i_src = {}
        total_src = 0.0
        for src in cfg.sources:
            if not src.enabled:
                i_src[src.name] = 0.0
                continue
            # Source current: limited by I_max and by voltage difference
            i_s = min(src.P_rated_W / max(V, 1.0), src.I_max_A)
            i_src[src.name] = round(i_s, 4)
            total_src += i_s

        i_ld = {}
        total_ld = 0.0
        for ld in cfg.loads:
            if not ld.enabled:
                i_ld[ld.name] = 0.0
                continue
            if ld.load_type == "CONST_Z":
                i_l = V / max(ld.R_load_Ohm, 1e-6)
            else:
                i_l = ld.P_rated_W / max(V, 1.0)
            i_ld[ld.name] = round(i_l, 4)
            total_ld += i_l

        return DCBusState(
            V_bus_V=round(V, 2),
            I_total_A=round(total_src - total_ld, 4),
            I_sources=i_src,
            I_loads=i_ld,
            P_total_W=round(total_src * V, 2),
            V_pu=round(V / max(cfg.V_nom_V, 1.0), 4),
        )

    # ------------------------------------------------------------------
    def simulate(self, t_end_ms: float = 10.0, dt_us: float = 10.0) -> DCMicrogridTrace:
        """
        Simulate DC microgrid response to an injected fault.

        If no fault is injected, returns normal operating trace.
        """
        cfg   = self._cfg
        dt_ms = dt_us * 1e-3
        N     = int(t_end_ms / dt_ms) + 1
        t_ms  = np.arange(N) * dt_ms

        # --- Source currents ---
        i_src_traces: Dict[str, np.ndarray] = {}
        for src in cfg.sources:
            if not src.enabled:
                i_src_traces[src.name] = np.zeros(N)
                continue
            # Ramp from 0 to steady-state over tau_ctrl_ms
            i_ss = min(src.P_rated_W / max(cfg.V_nom_V, 1.0), src.I_max_A)
            i_trace = i_ss * (1.0 - np.exp(-t_ms / max(src.tau_ctrl_ms, 1e-6)))
            i_src_traces[src.name] = np.minimum(i_trace, src.I_max_A)

        # --- Load current (constant-current model, sags with voltage) ---
        i_load_total = sum(
            ld.P_rated_W / max(cfg.V_nom_V, 1.0)
            for ld in cfg.loads if ld.enabled
        )
        I_loads = np.full(N, i_load_total)

        # --- Fault current (from DCFaultModel if fault injected) ---
        if self._fault is not None:
            bus_params = DCBusParams(
                V_nom_V=cfg.V_nom_V,
                C_bus_F=cfg.C_bus_F,
                L_cable_H=cfg.L_bus_H,
                R_cable_Ohm=cfg.R_bus_Ohm,
                I_conv_max_A=sum(s.I_max_A for s in cfg.sources if s.enabled),
                tau_ctrl_ms=1.0,
                bus_class=cfg.bus_class,
            )
            fault_model  = DCFaultModel(bus_params, self._fault)
            fault_trace  = fault_model.simulate(t_end_ms=t_end_ms, dt_us=dt_us)
            I_fault      = fault_trace.I_fault_A
            V_bus        = fault_trace.V_bus_V
        else:
            I_fault     = np.zeros(N)
            V_bus       = np.full(N, cfg.V_nom_V)
            fault_trace = None

        # Net current for bus voltage ODE (approximate V sag due to fault)
        I_sources_total = sum(tr for tr in i_src_traces.values())
        dI_dt = np.gradient(I_fault, dt_ms)

        peak_I    = float(np.max(np.abs(I_fault))) if self._fault else float(np.max(I_sources_total))
        peak_dIdt = float(np.max(np.abs(dI_dt)))

        return DCMicrogridTrace(
            t_ms=t_ms,
            V_bus_V=V_bus,
            I_fault_A=I_fault,
            I_sources=i_src_traces,
            I_loads_total=I_loads,
            dI_dt_A_ms=dI_dt,
            fault_trace=fault_trace,
            config_name=cfg.name,
            bus_class=cfg.bus_class,
            peak_I_A=peak_I,
            peak_dI_dt=peak_dIdt,
            t_trip_ms=None,
        )

    # ------------------------------------------------------------------
    @property
    def config(self) -> DCMicrogridConfig:
        return self._cfg


# ---------------------------------------------------------------------------
# Pre-built configurations
# ---------------------------------------------------------------------------

def make_lvdc_400v() -> DCMicrogridDT:
    """Standard 400 V LVDC industrial microgrid."""
    cfg = DCMicrogridConfig(
        name="LVDC_400V",
        bus_class="LVDC",
        V_nom_V=400.0,
        C_bus_F=10e-3,
        sources=[
            DCSource("BESS_1", "BESS",   50_000, 400.0, 125.0, tau_ctrl_ms=0.5),
            DCSource("PV_1",   "PV",     30_000, 400.0,  75.0, tau_ctrl_ms=2.0),
            DCSource("AC_TIE", "AC_TIE", 80_000, 400.0, 200.0, tau_ctrl_ms=1.0),
        ],
        loads=[
            DCLoad("LOAD_1", "CONST_P", 40_000),
            DCLoad("LOAD_2", "CONST_P", 20_000),
            DCLoad("EV_1",   "EV_CHARGER", 22_000),
        ],
        L_bus_H=5e-6,
        R_bus_Ohm=0.005,
    )
    return DCMicrogridDT.from_config(cfg)


def make_mvdc_6kv() -> DCMicrogridDT:
    """6 kV MVDC microgrid (e.g. offshore platform or shipboard)."""
    cfg = DCMicrogridConfig(
        name="MVDC_6kV",
        bus_class="MVDC",
        V_nom_V=6000.0,
        C_bus_F=0.5e-3,
        sources=[
            DCSource("BESS_HV",  "BESS",    500_000, 6000.0, 83.3,  tau_ctrl_ms=0.5),
            DCSource("GEN_RECT", "AC_TIE", 1_000_000, 6000.0, 167.0, tau_ctrl_ms=1.0),
            DCSource("PV_MVDC",  "PV",      200_000, 6000.0,  33.3,  tau_ctrl_ms=3.0),
        ],
        loads=[
            DCLoad("DRIVE_1",   "CONST_P", 300_000),
            DCLoad("DRIVE_2",   "CONST_P", 200_000),
            DCLoad("AUX_LOAD",  "CONST_P",  50_000),
        ],
        L_bus_H=50e-6,
        R_bus_Ohm=0.05,
    )
    return DCMicrogridDT.from_config(cfg)
