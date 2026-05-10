# =============================================================================
# sambp / digital_twin / models / bess_model.py
#
# BESS 6-state nonlinear state-space model — TR-68 WP 68.1
#
# State vector  x = [SoC, P_dc, Q_ac, V_dc, I_ac_mag, T_cell]
#
#   SoC      — state of charge [0, 1]                           (dimensionless)
#   P_dc     — DC power output of BESS cell stack [pu of P_rated]
#   Q_ac     — AC reactive power injection [pu of S_rated]
#   V_dc     — DC bus voltage [pu of V_dc_nom]
#   I_ac_mag — AC current magnitude at PCC [pu of I_rated]
#   T_cell   — average cell temperature [°C]
#
# Chemistry-specific dynamics (Li-ion / flow / Na-ion):
#   - Internal resistance R_int varies with SoC and temperature
#   - Current-limit profile differs per chemistry (thermal headroom)
#   - Fault-current profile: GFL limited to I_max_gfl_pu; GFM has higher
#     transient headroom then decays to steady-state limit
#
# Measurement model h(x):
#   Reconstructs three-phase voltage and current phasors at the PCC from
#   the six state variables, suitable for feeding into the ComtradeParser
#   comparison pipeline.
#
# Public API
# ----------
# cfg   = BESSConfig.li_ion_1mwh()         # preset
# model = BESSModel(cfg)
# x0    = model.x0()                        # default initial state
# x1    = model.f(x0, u, dt)               # state transition (dt seconds)
# z     = model.h(x0)                       # measurement: [Va,Vb,Vc,Ia,Ib,Ic]
# xc    = model.clamp(x)                    # enforce physical bounds
# J     = model.H_jacobian(x0)              # 6×6 linearised ∂h/∂x
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Chemistry parameter table
# ---------------------------------------------------------------------------

# Per-chemistry constants at nominal SoC (0.5) and temperature (25 °C)
_CHEM_PARAMS: Dict[str, Dict] = {
    "li_ion": {
        "r_int_nom":       0.010,    # pu — internal resistance at SoC=0.5, T=25°C
        "r_int_soc_coeff": 0.015,    # pu — ΔR_int for ΔSoC = ±0.5
        "r_int_t_coeff":   -0.0002,  # pu/°C — ΔR_int per °C above 25°C (NTC)
        "soc_tau":         30.0,     # s  — charge redistribution time constant
        "i_max_cont_pu":   1.20,     # pu — continuous current limit (GFL mode)
        "i_max_trans_pu":  1.50,     # pu — transient current limit (GFM mode, <200 ms)
        "trans_decay_tau": 0.10,     # s  — GFM transient decay time constant
        "v_dc_soc_slope":  0.30,     # pu/unit_SoC — DC voltage droop with SoC
        "cp_cell":         800.0,    # J/(kg·K) — cell specific heat capacity
        "density_kgm3":    2500.0,   # kg/m³ — approximate volumetric density
    },
    "flow": {
        "r_int_nom":       0.025,    # higher than Li-ion (electrolyte resistance)
        "r_int_soc_coeff": 0.005,    # weaker SoC dependence (liquid electrolyte)
        "r_int_t_coeff":   -0.0008,  # stronger temperature sensitivity
        "soc_tau":         5.0,      # faster (flowing electrolyte)
        "i_max_cont_pu":   1.00,     # lower peak capability
        "i_max_trans_pu":  1.20,
        "trans_decay_tau": 0.20,
        "v_dc_soc_slope":  0.20,
        "cp_cell":         3500.0,   # high (water-based electrolyte)
        "density_kgm3":    1200.0,
    },
    "na_ion": {
        "r_int_nom":       0.018,
        "r_int_soc_coeff": 0.020,
        "r_int_t_coeff":   -0.0003,
        "soc_tau":         20.0,
        "i_max_cont_pu":   1.10,
        "i_max_trans_pu":  1.40,
        "trans_decay_tau": 0.12,
        "v_dc_soc_slope":  0.25,
        "cp_cell":         900.0,
        "density_kgm3":    2200.0,
    },
}

# State-vector indices (named constants to avoid magic numbers throughout)
_SoC     = 0
_P_dc    = 1
_Q_ac    = 2
_V_dc    = 3
_I_ac    = 4
_T_cell  = 5

# Nominal temperature [°C] used as reference for R_int temperature correction
_T_NOM = 25.0

# Two-pi shorthand
_2PI = 2.0 * math.pi

# Grid frequency (50 Hz)
_F0 = 50.0


# ---------------------------------------------------------------------------
# BESSConfig dataclass
# ---------------------------------------------------------------------------

@dataclass
class BESSConfig:
    """
    Configuration for a single BESS unit.

    Parameters
    ----------
    chemistry         : 'li_ion' | 'flow' | 'na_ion'
    capacity_kwh      : rated energy capacity [kWh]
    power_rating_kw   : rated continuous power [kW]
    v_dc_nom          : nominal DC bus voltage [V]
    i_ac_max_pu       : AC current hard limit [pu of rated AC current]
    soc_min           : minimum allowed SoC (default 0.10)
    soc_max           : maximum allowed SoC (default 0.90)
    thermal_resistance: thermal resistance to ambient [°C/W]
    thermal_capacitance: thermal mass [J/°C]
    control_mode      : 'grid_following' | 'grid_forming'
    current_limit_pu  : fault-current limit [pu]
                         • GFL default 1.2 pu (continuous)
                         • GFM default 1.5 pu (transient; decays to ~1.1 pu)
    """
    chemistry:            str
    capacity_kwh:         float
    power_rating_kw:      float
    v_dc_nom:             float
    i_ac_max_pu:          float
    soc_min:              float = 0.10
    soc_max:              float = 0.90
    thermal_resistance:   float = 0.05    # °C/W
    thermal_capacitance:  float = 5000.0  # J/°C
    control_mode:         str   = "grid_following"
    current_limit_pu:     float = 1.20

    def __post_init__(self) -> None:
        if self.chemistry not in _CHEM_PARAMS:
            raise ValueError(
                f"Unknown chemistry '{self.chemistry}'. "
                f"Choose from {list(_CHEM_PARAMS)}")
        if self.control_mode not in ("grid_following", "grid_forming"):
            raise ValueError(f"Unknown control_mode '{self.control_mode}'")
        if not (0.0 <= self.soc_min < self.soc_max <= 1.0):
            raise ValueError(
                f"Invalid SoC limits: soc_min={self.soc_min}, soc_max={self.soc_max}")

    # ------------------------------------------------------------------
    # Convenience presets
    # ------------------------------------------------------------------

    @classmethod
    def li_ion_1mwh(cls) -> "BESSConfig":
        """1 MWh / 500 kW Li-ion BESS, grid-following, standard SGC installation."""
        return cls(
            chemistry="li_ion",
            capacity_kwh=1000.0,
            power_rating_kw=500.0,
            v_dc_nom=800.0,
            i_ac_max_pu=1.20,
            soc_min=0.10,
            soc_max=0.90,
            thermal_resistance=0.04,
            thermal_capacitance=8000.0,
            control_mode="grid_following",
            current_limit_pu=1.20,
        )

    @classmethod
    def flow_5mwh(cls) -> "BESSConfig":
        """5 MWh / 1 MW vanadium redox flow BESS, grid-following."""
        return cls(
            chemistry="flow",
            capacity_kwh=5000.0,
            power_rating_kw=1000.0,
            v_dc_nom=600.0,
            i_ac_max_pu=1.00,
            soc_min=0.15,
            soc_max=0.85,
            thermal_resistance=0.02,
            thermal_capacitance=50000.0,  # very high thermal mass (electrolyte tanks)
            control_mode="grid_following",
            current_limit_pu=1.00,
        )

    @classmethod
    def na_ion_500kwh(cls) -> "BESSConfig":
        """500 kWh / 250 kW Na-ion BESS, grid-forming (black-start capable)."""
        return cls(
            chemistry="na_ion",
            capacity_kwh=500.0,
            power_rating_kw=250.0,
            v_dc_nom=700.0,
            i_ac_max_pu=1.40,
            soc_min=0.10,
            soc_max=0.90,
            thermal_resistance=0.06,
            thermal_capacitance=4000.0,
            control_mode="grid_forming",
            current_limit_pu=1.40,
        )

    # Derived quantities (properties to avoid stale copies)
    @property
    def chem(self) -> Dict:
        return _CHEM_PARAMS[self.chemistry]

    @property
    def i_rated_a(self) -> float:
        """Rated AC current [A] = power_rating_kw / (√3 × V_LL), V_LL = 66 kV."""
        # For a 66 kV network: I_rated = P / (√3 × 66e3)
        return self.power_rating_kw * 1e3 / (math.sqrt(3.0) * 66e3)

    @property
    def p_rated_w(self) -> float:
        return self.power_rating_kw * 1e3

    @property
    def is_gfm(self) -> bool:
        return self.control_mode == "grid_forming"


# ---------------------------------------------------------------------------
# State bounds table  (indexed by _SoC … _T_cell)
# ---------------------------------------------------------------------------

_STATE_BOUNDS = [
    (0.0,  1.0),    # SoC
    (-1.2, 1.2),    # P_dc  [pu] — negative = charging
    (-1.0, 1.0),    # Q_ac  [pu]
    (0.80, 1.20),   # V_dc  [pu]
    (0.0,  1.6),    # I_ac  [pu]
    (-20.0, 80.0),  # T_cell [°C]
]


# ---------------------------------------------------------------------------
# BESSModel
# ---------------------------------------------------------------------------

class BESSModel:
    """
    Nonlinear 6-state BESS model for the SAMBP Digital Twin.

    Inherits the interface of IBRStateSpaceModel (same method signatures):
      f(x, u, dt) → x_next   — nonlinear state transition
      h(x) → z               — measurement model
      H_jacobian(x) → H      — linearised ∂h/∂x (6 × 6)
      clamp(x) → x_clamped   — enforce physical bounds
      x0() → x               — default initial state

    Additional:
      r_int(soc, t_cell) → float  — chemistry-dependent internal resistance
      fault_current_limit(t_elapsed) → float  — time-varying fault current limit

    Parameters
    ----------
    cfg : BESSConfig
        BESS hardware / control configuration.
    t_ambient : float
        Ambient temperature [°C] (default 25.0).
    """

    STATE_NAMES = ("SoC", "P_dc", "Q_ac", "V_dc", "I_ac_mag", "T_cell")
    N_STATES    = 6
    N_MEAS      = 6    # [Va, Vb, Vc, Ia, Ib, Ic] at fundamental frequency

    def __init__(self, cfg: BESSConfig, t_ambient: float = 25.0) -> None:
        self.cfg       = cfg
        self.t_ambient = t_ambient
        self._chem     = cfg.chem

        # Process noise covariance Q (6×6 diagonal)
        # Tuned to match expected drift rates for each state over 1 ms DT step
        self.Q = np.diag([
            1e-8,   # SoC: very slow drift
            1e-5,   # P_dc: converter control bandwidth ~100 Hz → fast changes
            1e-5,   # Q_ac: reactive power control
            1e-6,   # V_dc: DC bus regulated tightly
            1e-5,   # I_ac: AC current tracks reference
            1e-4,   # T_cell: thermal time constant seconds-to-minutes
        ])

        # Measurement noise R (6×6 diagonal)
        # class 1P VT: σ_V = 0.005 pu; class 1P CT: σ_I = 0.010 pu
        _sv2 = 0.005 ** 2
        _si2 = 0.010 ** 2
        self.R = np.diag([_sv2, _sv2, _sv2, _si2, _si2, _si2])

    # ------------------------------------------------------------------
    # Chemistry helpers
    # ------------------------------------------------------------------

    def r_int(self, soc: float, t_cell: float) -> float:
        """
        Chemistry-dependent internal resistance [pu].

        r_int(SoC, T) = r_int_nom
                      + r_int_soc_coeff × (0.5 − SoC)   (higher at low SoC)
                      + r_int_t_coeff   × (T − T_nom)    (NTC: decreases with T)
        """
        c = self._chem
        r = (c["r_int_nom"]
             + c["r_int_soc_coeff"] * (0.5 - float(soc))
             + c["r_int_t_coeff"]   * (float(t_cell) - _T_NOM))
        return max(r, 1e-4)   # floor to prevent division by zero

    def fault_current_limit(self, t_elapsed: float = 0.0) -> float:
        """
        Time-varying AC fault current limit [pu].

        GFL: constant at cfg.current_limit_pu (hard limit, no transient headroom).
        GFM: starts at i_max_trans_pu, decays exponentially toward
             i_max_cont_pu with time constant trans_decay_tau.

        Parameters
        ----------
        t_elapsed : float
            Time since fault onset [s].
        """
        c = self._chem
        if not self.cfg.is_gfm:
            return self.cfg.current_limit_pu
        # GFM: exponential decay from transient peak to continuous limit
        i_trans = c["i_max_trans_pu"]
        i_cont  = c["i_max_cont_pu"]
        tau     = c["trans_decay_tau"]
        return i_cont + (i_trans - i_cont) * math.exp(-t_elapsed / tau)

    # ------------------------------------------------------------------
    # Default initial state
    # ------------------------------------------------------------------

    def x0(self, soc: float = 0.50, p_dispatch_pu: float = 0.0) -> np.ndarray:
        """
        Default initial state vector.

        Parameters
        ----------
        soc            : initial state of charge [0,1]
        p_dispatch_pu  : initial dispatch setpoint [pu of P_rated], +ve = export

        Returns
        -------
        x : ndarray, shape (6,)
            [SoC, P_dc, Q_ac, V_dc, I_ac_mag, T_cell]
        """
        # DC power = AC power / converter efficiency (≈ 0.97)
        p_dc = p_dispatch_pu / 0.97
        # I_ac from P_dc and V_dc (assuming unity power factor at no-load)
        i_ac = abs(p_dispatch_pu)
        # V_dc: linearly interpolated by SoC
        v_dc = 1.0 + self._chem["v_dc_soc_slope"] * (soc - 0.5)
        v_dc = float(np.clip(v_dc, 0.80, 1.20))
        return np.array([soc, p_dc, 0.0, v_dc, i_ac, self.t_ambient],
                        dtype=float)

    # ------------------------------------------------------------------
    # State transition  f(x, u, dt) → x_next
    # ------------------------------------------------------------------

    def f(self, x: np.ndarray, u: Optional[np.ndarray] = None,
          dt: float = 1e-3) -> np.ndarray:
        """
        Nonlinear discrete-time state transition.

        Parameters
        ----------
        x  : ndarray, shape (6,)  — current state
        u  : ndarray or None       — control input [P_setpoint_pu, Q_setpoint_pu]
             If None, assumes constant-power dispatch (hold previous setpoints).
        dt : float                 — time step [s] (default 1 ms = 1 kHz DT rate)

        Returns
        -------
        x_next : ndarray, shape (6,)
        """
        x    = np.asarray(x, dtype=float)
        soc, p_dc, q_ac, v_dc, i_ac, t_cell = x

        # Control inputs (default: hold current dispatch)
        if u is not None:
            u = np.asarray(u, dtype=float)
            p_sp = float(u[0])
            q_sp = float(u[1]) if len(u) > 1 else 0.0
        else:
            p_sp = p_dc
            q_sp = q_ac

        # ---- 1. SoC dynamics ----
        # dSoC/dt = -P_dc / (3600 × E_rated_kWh)   [1/s]
        # Negative P_dc means charging → SoC increases
        e_rated_kwh = self.cfg.capacity_kwh
        dsoc_dt = -p_dc / (3600.0 * e_rated_kwh) if e_rated_kwh > 0 else 0.0
        soc_next = soc + dsoc_dt * dt

        # ---- 2. P_dc dynamics (first-order lag toward setpoint) ----
        # Converter bandwidth: ~100 Hz (Li-ion / Na-ion) or ~20 Hz (flow)
        bw_hz = 100.0 if self.cfg.chemistry != "flow" else 20.0
        tau_p = 1.0 / (_2PI * bw_hz)
        p_dc_next = p_dc + (p_sp - p_dc) * (dt / tau_p)

        # ---- 3. Q_ac dynamics (same bandwidth as P_dc) ----
        q_ac_next = q_ac + (q_sp - q_ac) * (dt / tau_p)

        # ---- 4. V_dc dynamics (DC bus voltage) ----
        # V_dc regulated by converter: droop with SoC + voltage drop across R_int
        rint   = self.r_int(soc_next, t_cell)
        v_dc_oc = 1.0 + self._chem["v_dc_soc_slope"] * (soc_next - 0.5)
        v_dc_next = v_dc_oc - rint * abs(p_dc_next)   # Thevenin equivalent

        # ---- 5. I_ac dynamics (AC current magnitude) ----
        # Apparent power S = sqrt(P² + Q²); I = S / V_ac (V_ac ≈ 1.0 pu)
        s_app = math.sqrt(p_dc_next ** 2 + q_ac_next ** 2)
        i_ac_next = s_app   # in pu with V_ac = 1.0 pu

        # ---- 6. Thermal dynamics (Newton's law of cooling) ----
        # Q_heat = I² × R_int × P_rated [W]  (losses)
        p_loss_w  = (i_ac_next ** 2) * rint * self.cfg.p_rated_w
        r_th = self.cfg.thermal_resistance
        c_th = self.cfg.thermal_capacitance
        dt_cell   = ((p_loss_w / c_th)
                     - (t_cell - self.t_ambient) / (r_th * c_th)) * dt
        t_cell_next = t_cell + dt_cell

        x_next = np.array([soc_next, p_dc_next, q_ac_next,
                            v_dc_next, i_ac_next, t_cell_next])
        return self.clamp(x_next)

    # ------------------------------------------------------------------
    # Measurement model  h(x) → z = [Va, Vb, Vc, Ia, Ib, Ic]
    # ------------------------------------------------------------------

    def h(self, x: np.ndarray, theta: float = 0.0) -> np.ndarray:
        """
        Reconstruct three-phase voltage and current phasors from state.

        The BESS is modelled as a Thevenin equivalent at the PCC:
          V_abc: balanced 1.0 pu voltages (BESS regulates V_ac)
          I_abc: balanced three-phase currents at I_ac_mag with angle θ

        Parameters
        ----------
        x     : ndarray, shape (6,)  — state vector
        theta : float                — phase angle of phase A at t=0 [rad]
                                       (used for instantaneous waveform; default 0)

        Returns
        -------
        z : ndarray, shape (6,)
            [Va_peak, Vb_peak, Vc_peak, Ia_peak, Ib_peak, Ic_peak] in pu
            (peak values of the fundamental-frequency component)
        """
        x = np.asarray(x, dtype=float)
        _, p_dc, q_ac, v_dc, i_ac, _ = x

        # AC voltage magnitude ≈ 1.0 pu (BESS regulates PCC voltage)
        # V_dc converts through DC/AC stage: V_ac ≈ V_dc × modulation_index / √2
        # Simplification: model V_ac = 1.0 pu (voltage-source behaviour)
        v_ac = 1.0

        # Power-factor angle: φ = atan2(Q_ac, P_dc)
        phi = math.atan2(q_ac, p_dc) if (abs(p_dc) > 1e-6 or abs(q_ac) > 1e-6) else 0.0

        # Three-phase peak voltages (balanced, θ is the instantaneous angle of Va)
        va =  v_ac * math.sqrt(2.0) * math.cos(theta)
        vb =  v_ac * math.sqrt(2.0) * math.cos(theta - _2PI / 3.0)
        vc =  v_ac * math.sqrt(2.0) * math.cos(theta + _2PI / 3.0)

        # Three-phase peak currents (balanced, lagging by φ)
        ia = i_ac * math.sqrt(2.0) * math.cos(theta - phi)
        ib = i_ac * math.sqrt(2.0) * math.cos(theta - phi - _2PI / 3.0)
        ic = i_ac * math.sqrt(2.0) * math.cos(theta - phi + _2PI / 3.0)

        return np.array([va, vb, vc, ia, ib, ic])

    def H_jacobian(self, x: np.ndarray, theta: float = 0.0) -> np.ndarray:
        """
        Linearised measurement Jacobian ∂h/∂x at state x.

        Returns H : ndarray, shape (6, 6)
        Only the I_ac_mag column is non-zero for the current rows;
        voltage rows are independent of state (V_ac ≈ 1.0 pu).
        """
        x = np.asarray(x, dtype=float)
        _, p_dc, q_ac, _, i_ac, _ = x

        phi = math.atan2(q_ac, p_dc) if (abs(p_dc) > 1e-6 or abs(q_ac) > 1e-6) else 0.0
        H = np.zeros((6, 6))

        # ∂[Ia, Ib, Ic] / ∂I_ac_mag  (column _I_ac = 4)
        sqrt2 = math.sqrt(2.0)
        H[3, _I_ac] = sqrt2 * math.cos(theta - phi)
        H[4, _I_ac] = sqrt2 * math.cos(theta - phi - _2PI / 3.0)
        H[5, _I_ac] = sqrt2 * math.cos(theta - phi + _2PI / 3.0)

        # ∂[Ia, Ib, Ic] / ∂phi  (chain rule through P_dc and Q_ac)
        # ∂phi/∂P_dc = -Q_ac / (P_dc² + Q_ac²)
        # ∂phi/∂Q_ac = +P_dc / (P_dc² + Q_ac²)
        denom = p_dc ** 2 + q_ac ** 2
        if denom > 1e-12:
            dphi_dp = -q_ac / denom
            dphi_dq =  p_dc / denom
            d_ia_dphi = i_ac * sqrt2 * math.sin(theta - phi)
            d_ib_dphi = i_ac * sqrt2 * math.sin(theta - phi - _2PI / 3.0)
            d_ic_dphi = i_ac * sqrt2 * math.sin(theta - phi + _2PI / 3.0)
            H[3, _P_dc] = d_ia_dphi * dphi_dp
            H[3, _Q_ac] = d_ia_dphi * dphi_dq
            H[4, _P_dc] = d_ib_dphi * dphi_dp
            H[4, _Q_ac] = d_ib_dphi * dphi_dq
            H[5, _P_dc] = d_ic_dphi * dphi_dp
            H[5, _Q_ac] = d_ic_dphi * dphi_dq

        return H

    # ------------------------------------------------------------------
    # State bounds enforcement
    # ------------------------------------------------------------------

    def clamp(self, x: np.ndarray) -> np.ndarray:
        """Clamp state to physical bounds, applying SoC config limits."""
        x = np.asarray(x, dtype=float).copy()
        # SoC: use config-defined limits
        x[_SoC]    = float(np.clip(x[_SoC],    self.cfg.soc_min,    self.cfg.soc_max))
        x[_P_dc]   = float(np.clip(x[_P_dc],   _STATE_BOUNDS[_P_dc][0],  _STATE_BOUNDS[_P_dc][1]))
        x[_Q_ac]   = float(np.clip(x[_Q_ac],   _STATE_BOUNDS[_Q_ac][0],  _STATE_BOUNDS[_Q_ac][1]))
        x[_V_dc]   = float(np.clip(x[_V_dc],   _STATE_BOUNDS[_V_dc][0],  _STATE_BOUNDS[_V_dc][1]))
        x[_I_ac]   = float(np.clip(x[_I_ac],   _STATE_BOUNDS[_I_ac][0],  _STATE_BOUNDS[_I_ac][1]))
        x[_T_cell] = float(np.clip(x[_T_cell],  _STATE_BOUNDS[_T_cell][0], _STATE_BOUNDS[_T_cell][1]))
        return x

    # ------------------------------------------------------------------
    # Fault injection helper
    # ------------------------------------------------------------------

    def fault_state(self, x: np.ndarray, fault_type: str = "3PH",
                    t_elapsed: float = 0.0) -> np.ndarray:
        """
        Modify state to reflect fault-period BESS current injection.

        Parameters
        ----------
        x           : current state vector (6,)
        fault_type  : 'SLG' | 'LL' | 'DLG' | '3PH'
        t_elapsed   : time since fault onset [s]

        Returns
        -------
        x_fault : ndarray (6,) — state with I_ac_mag set to fault-current level
        """
        x_f = x.copy()
        i_limit = self.fault_current_limit(t_elapsed)

        # Asymmetric faults: negative-sequence injection reduces effective I_mag
        neg_seq_factors = {"SLG": 0.85, "LL": 0.90, "DLG": 0.88, "3PH": 1.00}
        factor = neg_seq_factors.get(fault_type, 1.00)

        x_f[_I_ac] = min(i_limit * factor, self.cfg.i_ac_max_pu)
        return self.clamp(x_f)

    # ------------------------------------------------------------------
    # History management (mirrors IBRStateSpaceModel interface)
    # ------------------------------------------------------------------

    def __init_history(self) -> None:
        if not hasattr(self, "_history"):
            self._history: list = []

    def push(self, state_dict: Dict) -> None:
        """Record an estimated state dict (keys = STATE_NAMES)."""
        self.__init_history()
        self._history.append(state_dict.copy())
        if len(self._history) > 500:
            self._history.pop(0)

    def latest(self) -> Optional[Dict]:
        self.__init_history()
        return self._history[-1] if self._history else None

    def history_array(self) -> np.ndarray:
        self.__init_history()
        if not self._history:
            return np.empty((0, self.N_STATES))
        return np.array([[s.get(n, 0.0) for n in self.STATE_NAMES]
                         for s in self._history])
