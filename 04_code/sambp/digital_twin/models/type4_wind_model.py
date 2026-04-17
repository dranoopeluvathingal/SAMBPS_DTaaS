# =============================================================================
# sambp / digital_twin / models / type4_wind_model.py
#
# Type-4 full-converter wind turbine state-space model — TR-69 WP 69.1
#
# State vector  x = [P_gen, Q_gen, V_dc_link, I_grid_mag, omega_rotor, pitch_angle]
#
#   P_gen       — active power output [pu of P_rated]
#   Q_gen       — reactive power output [pu of S_rated]
#   V_dc_link   — DC link voltage [pu of V_dc_nom]
#   I_grid_mag  — grid-side converter current magnitude [pu of I_rated]
#   omega_rotor — rotor angular speed [pu of omega_rated]  (omega_s = 1.0)
#   pitch_angle — blade pitch angle [degrees]
#
# Physics implemented
# -------------------
#   • Cp(λ, β) curve (Heier/Betz polynomial, 5th-order fit)
#   • MPPT: optimal tip-speed-ratio tracking → P_gen setpoint
#   • Pitch control: PI controller with rate/angle limits
#   • DC link capacitor dynamics
#   • Grid-side converter current dynamics (first-order lag)
#   • FRT reactive injection per IEC 61400-27-1 / AEMO / NERC
#   • GFM/VSM: virtual inertia + damping terms
#
# Public API
# ----------
# cfg   = Type4WindConfig.vestas_v164_8mw()
# model = Type4WindModel(cfg)
# x0    = model.x0(wind_speed_mps=12.0)
# x1    = model.f(x0, u, dt, wind_speed_mps=12.0)
# z     = model.h(x0)
# xc    = model.clamp(x)
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_2PI = 2.0 * math.pi
_F0  = 50.0       # grid frequency [Hz]
_SQRT2 = math.sqrt(2.0)
_SQRT3 = math.sqrt(3.0)

# Cp polynomial coefficients (Heier curve — standard Type-4 approximation)
# Cp(λ, β) = c1*(c2/λ_i - c3*β - c4) * exp(-c5/λ_i) + c6*λ
# with 1/λ_i = 1/(λ + 0.08β) - 0.035/(β³+1)
_CP_C = (0.5176, 116.0, 0.4, 5.0, 21.0, 0.0068)

# State vector indices
_P_GEN   = 0
_Q_GEN   = 1
_V_DC    = 2
_I_GRID  = 3
_OMEGA   = 4
_PITCH   = 5


# ---------------------------------------------------------------------------
# Cp(λ, β) power coefficient
# ---------------------------------------------------------------------------

def cp_curve(lam: float, beta: float) -> float:
    """
    Power coefficient Cp(λ, β) using the 6-parameter Heier polynomial.

    Parameters
    ----------
    lam  : tip-speed ratio λ = ω_r × R / v_w
    beta : pitch angle [degrees]

    Returns
    -------
    Cp : float ∈ [0, Cp_max]  (clamped ≥ 0)
    """
    c1, c2, c3, c4, c5, c6 = _CP_C
    beta = max(0.0, float(beta))
    lam  = max(0.1, float(lam))
    lam_i_inv = 1.0 / (lam + 0.08 * beta) - 0.035 / (beta ** 3 + 1.0)
    lam_i = 1.0 / max(lam_i_inv, 1e-6)
    cp = (c1 * (c2 / lam_i - c3 * beta - c4)
          * math.exp(-c5 / lam_i) + c6 * lam)
    return max(0.0, cp)


def cp_max_lambda(beta: float = 0.0, n_pts: int = 200) -> Tuple[float, float]:
    """
    Numerically find λ* that maximises Cp(λ, β).

    Returns (lambda_opt, Cp_max).
    """
    lams = [0.1 + 18.9 * i / (n_pts - 1) for i in range(n_pts)]
    cps  = [cp_curve(l, beta) for l in lams]
    idx  = cps.index(max(cps))
    return lams[idx], cps[idx]


# ---------------------------------------------------------------------------
# Type4WindConfig
# ---------------------------------------------------------------------------

@dataclass
class Type4WindConfig:
    """
    Configuration for a Type-4 full-converter wind turbine generator.

    Parameters
    ----------
    name              : turbine model name
    rated_power_mw    : rated active power [MW]
    rated_voltage_kv  : nominal terminal voltage (line-to-line) [kV]
    rotor_diameter_m  : rotor diameter [m]
    hub_height_m      : hub height [m]
    omega_rated_rpm   : rated rotor speed [rpm]
    omega_min_rpm     : minimum rotor speed [rpm] (cut-in)
    v_cut_in_mps      : cut-in wind speed [m/s]
    v_rated_mps       : rated wind speed [m/s]
    v_cut_out_mps     : cut-out wind speed [m/s]
    v_dc_nom          : nominal DC link voltage [V]
    c_dc_mf           : DC link capacitance [mF]
    control_mode      : 'gfl' | 'gfm_vsm'
    frt_standard      : 'iec' | 'aemo' | 'nerc'
    i_max_cont_pu     : continuous current limit [pu]
    i_max_trans_pu    : transient current limit [pu]  (fault/FRT)
    virtual_inertia_s : VSM virtual inertia constant H [s] (GFM only)
    virtual_damping   : VSM damping coefficient D_p [pu] (GFM only)
    pitch_rate_max    : max pitch rate [deg/s]
    pitch_angle_max   : max pitch angle [deg]
    kp_pitch          : pitch PI proportional gain
    ki_pitch          : pitch PI integral gain
    tau_grid_conv     : grid-converter first-order lag [s]
    """
    name:               str
    rated_power_mw:     float
    rated_voltage_kv:   float
    rotor_diameter_m:   float
    hub_height_m:       float
    omega_rated_rpm:    float
    omega_min_rpm:      float
    v_cut_in_mps:       float
    v_rated_mps:        float
    v_cut_out_mps:      float
    v_dc_nom:           float   # [V]
    c_dc_mf:            float   # [mF]
    control_mode:       str     # 'gfl' | 'gfm_vsm'
    frt_standard:       str     # 'iec' | 'aemo' | 'nerc'
    i_max_cont_pu:      float   = 1.10
    i_max_trans_pu:     float   = 1.30
    virtual_inertia_s:  float   = 5.0    # H [s]
    virtual_damping:    float   = 20.0   # D_p [pu]
    pitch_rate_max:     float   = 8.0    # deg/s
    pitch_angle_max:    float   = 90.0   # deg
    kp_pitch:           float   = 0.10
    ki_pitch:           float   = 0.02
    tau_grid_conv:      float   = 0.020  # 20 ms grid-converter lag

    def __post_init__(self) -> None:
        if self.control_mode not in ("gfl", "gfm_vsm"):
            raise ValueError(f"Unknown control_mode '{self.control_mode}'")
        if self.frt_standard not in ("iec", "aemo", "nerc"):
            raise ValueError(f"Unknown frt_standard '{self.frt_standard}'")

    @property
    def rotor_radius_m(self) -> float:
        return self.rotor_diameter_m / 2.0

    @property
    def swept_area_m2(self) -> float:
        return math.pi * self.rotor_radius_m ** 2

    @property
    def omega_rated_rads(self) -> float:
        """Rated rotor angular speed [rad/s]."""
        return self.omega_rated_rpm * _2PI / 60.0

    @property
    def omega_min_rads(self) -> float:
        return self.omega_min_rpm * _2PI / 60.0

    @property
    def p_rated_w(self) -> float:
        return self.rated_power_mw * 1e6

    @property
    def is_gfm(self) -> bool:
        return self.control_mode == "gfm_vsm"

    # ── Presets ────────────────────────────────────────────────────────

    @classmethod
    def vestas_v164_8mw(cls) -> "Type4WindConfig":
        """Vestas V164-8.0 MW (IEC Class IA, GFL, IEC FRT)."""
        return cls(
            name="Vestas_V164_8MW",
            rated_power_mw=8.0,
            rated_voltage_kv=0.690,
            rotor_diameter_m=164.0,
            hub_height_m=105.0,
            omega_rated_rpm=10.5,
            omega_min_rpm=6.0,
            v_cut_in_mps=3.0,
            v_rated_mps=13.0,
            v_cut_out_mps=25.0,
            v_dc_nom=1100.0,
            c_dc_mf=50.0,
            control_mode="gfl",
            frt_standard="iec",
            i_max_cont_pu=1.10,
            i_max_trans_pu=1.30,
            tau_grid_conv=0.020,
        )

    @classmethod
    def siemens_sg14(cls) -> "Type4WindConfig":
        """Siemens Gamesa SG 14-222 DD (GFM/VSM, AEMO FRT)."""
        return cls(
            name="Siemens_SG14_222",
            rated_power_mw=14.0,
            rated_voltage_kv=0.690,
            rotor_diameter_m=222.0,
            hub_height_m=135.0,
            omega_rated_rpm=7.1,
            omega_min_rpm=3.5,
            v_cut_in_mps=3.0,
            v_rated_mps=12.0,
            v_cut_out_mps=25.0,
            v_dc_nom=1400.0,
            c_dc_mf=80.0,
            control_mode="gfm_vsm",
            frt_standard="aemo",
            i_max_cont_pu=1.10,
            i_max_trans_pu=1.40,
            virtual_inertia_s=6.0,
            virtual_damping=25.0,
            tau_grid_conv=0.015,
        )

    @classmethod
    def goldwind_gwh252_16mw(cls) -> "Type4WindConfig":
        """Goldwind GWH252-16MW (GFL, NERC FRT)."""
        return cls(
            name="Goldwind_GWH252_16MW",
            rated_power_mw=16.0,
            rated_voltage_kv=0.690,
            rotor_diameter_m=252.0,
            hub_height_m=150.0,
            omega_rated_rpm=6.8,
            omega_min_rpm=3.2,
            v_cut_in_mps=3.0,
            v_rated_mps=11.0,
            v_cut_out_mps=25.0,
            v_dc_nom=1600.0,
            c_dc_mf=100.0,
            control_mode="gfl",
            frt_standard="nerc",
            i_max_cont_pu=1.10,
            i_max_trans_pu=1.35,
            tau_grid_conv=0.018,
        )


# ---------------------------------------------------------------------------
# State bounds
# ---------------------------------------------------------------------------

_STATE_BOUNDS = [
    (-0.05, 1.10),   # P_gen  [pu]
    (-0.50, 0.50),   # Q_gen  [pu]
    (0.80,  1.20),   # V_dc   [pu]
    (0.0,   1.40),   # I_grid [pu]
    (0.0,   1.30),   # omega  [pu]
    (0.0,   90.0),   # pitch  [deg]
]


# ---------------------------------------------------------------------------
# Type4WindModel
# ---------------------------------------------------------------------------

class Type4WindModel:
    """
    Nonlinear 6-state Type-4 full-converter wind turbine model.

    Interface mirrors BESSModel (same method signatures):
      f(x, u, dt, wind_speed_mps) → x_next
      h(x, theta) → z = [Va,Vb,Vc,Ia,Ib,Ic]
      H_jacobian(x) → H (6×6)
      clamp(x) → x_clamped
      x0(wind_speed_mps) → x

    Parameters
    ----------
    cfg       : Type4WindConfig
    rho_air   : air density [kg/m³]  (default 1.225)
    t_ambient : ambient temperature [°C]  (not used in wind model, kept for API compat)
    """

    STATE_NAMES = ("P_gen", "Q_gen", "V_dc_link", "I_grid_mag", "omega_rotor", "pitch_angle")
    N_STATES    = 6
    N_MEAS      = 6

    # Optimal TSR at zero pitch (computed from Cp_curve at startup)
    _LAMBDA_OPT: Optional[float] = None
    _CP_MAX:     Optional[float] = None

    def __init__(self, cfg: Type4WindConfig,
                 rho_air: float = 1.225,
                 t_ambient: float = 25.0) -> None:
        self.cfg       = cfg
        self.rho       = rho_air

        # Precompute optimal TSR and Cp_max
        lam_opt, cp_opt = cp_max_lambda(beta=0.0)
        self._lam_opt = lam_opt
        self._cp_max  = cp_opt

        # Pitch integral accumulator (for pitch PI controller)
        self._pitch_int = 0.0

        # Process noise Q (diagonal, in pu)
        self.Q = np.diag([
            1e-5,   # P_gen
            1e-5,   # Q_gen
            1e-6,   # V_dc
            1e-5,   # I_grid
            1e-6,   # omega_rotor
            1e-4,   # pitch_angle (slower)
        ])
        # Measurement noise R (VT 0.5%, CT 1%)
        _sv2 = 0.005 ** 2
        _si2 = 0.010 ** 2
        self.R = np.diag([_sv2, _sv2, _sv2, _si2, _si2, _si2])

    # ------------------------------------------------------------------
    # Aerodynamic helpers
    # ------------------------------------------------------------------

    def tip_speed_ratio(self, omega_pu: float, v_w: float) -> float:
        """λ = ω_r × R / v_w  (ω in rad/s from pu × ω_rated)."""
        if v_w < 0.1:
            return 0.0
        omega_rads = omega_pu * self.cfg.omega_rated_rads
        return omega_rads * self.cfg.rotor_radius_m / v_w

    def aero_power(self, omega_pu: float, pitch_deg: float,
                   v_w: float) -> float:
        """
        Aerodynamic shaft power [pu of P_rated].

        P_aero = 0.5 × ρ × A × v_w³ × Cp(λ, β) / P_rated
        """
        lam = self.tip_speed_ratio(omega_pu, v_w)
        cp  = cp_curve(lam, pitch_deg)
        p_aero_w = 0.5 * self.rho * self.cfg.swept_area_m2 * (v_w ** 3) * cp
        return p_aero_w / self.cfg.p_rated_w

    def mppt_omega_ref(self, v_w: float) -> float:
        """
        MPPT reference rotor speed [pu] via optimal TSR tracking.
        Clamped to [omega_min, omega_rated].
        """
        if v_w < self.cfg.v_cut_in_mps:
            return self.cfg.omega_min_rads / self.cfg.omega_rated_rads
        omega_opt = self._lam_opt * v_w / self.cfg.rotor_radius_m
        omega_pu  = omega_opt / self.cfg.omega_rated_rads
        omega_min_pu = self.cfg.omega_min_rads / self.cfg.omega_rated_rads
        return float(np.clip(omega_pu, omega_min_pu, 1.0))

    # ------------------------------------------------------------------
    # Pitch control
    # ------------------------------------------------------------------

    def pitch_ref(self, p_gen_pu: float, dt: float) -> float:
        """
        PI pitch controller: pitch to limit power above rated.

        Returns pitch angle increment [deg] (caller adds to current pitch).
        """
        err = p_gen_pu - 1.0  # error relative to rated
        if err <= 0.0:
            # Below rated: drive pitch to 0° (MPPT zone)
            self._pitch_int = max(0.0, self._pitch_int)
            return -self.cfg.kp_pitch * abs(err)   # reduce pitch
        # Above rated: increase pitch to limit power
        self._pitch_int += err * dt
        dpitch = self.cfg.kp_pitch * err + self.cfg.ki_pitch * self._pitch_int
        return float(np.clip(dpitch, -self.cfg.pitch_rate_max * dt,
                              self.cfg.pitch_rate_max * dt))

    # ------------------------------------------------------------------
    # FRT reactive injection
    # ------------------------------------------------------------------

    def frt_q_injection(self, v_pu: float, p_gen_pu: float) -> float:
        """
        Reactive current injection during FRT per selected grid code.

        Returns Q_ref [pu] (positive = capacitive / voltage support).
        Delegates to the grid-code-specific logic in WindFRTLib.
        """
        from models.wind_frt_lib import frt_reactive_injection
        return frt_reactive_injection(self.cfg.frt_standard, v_pu, p_gen_pu,
                                       self.cfg.i_max_trans_pu)

    # ------------------------------------------------------------------
    # Default initial state
    # ------------------------------------------------------------------

    def x0(self, wind_speed_mps: float = 12.0) -> np.ndarray:
        """
        Equilibrium initial state for a given wind speed.

        Returns x = [P_gen, Q_gen, V_dc, I_grid, omega, pitch]
        """
        v_w = float(wind_speed_mps)
        if v_w < self.cfg.v_cut_in_mps or v_w > self.cfg.v_cut_out_mps:
            return np.array([0.0, 0.0, 1.0, 0.0, 0.3, 0.0])

        # Rotor at MPPT operating point
        omega_pu = self.mppt_omega_ref(v_w)
        omega_pu = min(omega_pu, 1.0)  # clamp to rated

        # At rated or above: full power, pitch is active
        if v_w >= self.cfg.v_rated_mps:
            p_gen = 1.0
            pitch = max(0.0, (v_w - self.cfg.v_rated_mps) * 1.2)  # approx
        else:
            p_gen = self.aero_power(omega_pu, 0.0, v_w)
            pitch = 0.0

        p_gen = float(np.clip(p_gen, 0.0, 1.05))
        i_grid = p_gen  # unity power factor
        return np.array([p_gen, 0.0, 1.0, i_grid, omega_pu, pitch])

    # ------------------------------------------------------------------
    # State transition  f(x, u, dt, wind_speed_mps) → x_next
    # ------------------------------------------------------------------

    def f(self, x: np.ndarray,
          u: Optional[np.ndarray] = None,
          dt: float = 1e-3,
          wind_speed_mps: float = 12.0,
          v_terminal_pu: float = 1.0) -> np.ndarray:
        """
        Nonlinear discrete-time state transition.

        Parameters
        ----------
        x              : state (6,)
        u              : [P_setpoint_pu, Q_setpoint_pu] or None (MPPT+FRT auto)
        dt             : time step [s]
        wind_speed_mps : hub-height wind speed [m/s]
        v_terminal_pu  : terminal voltage magnitude [pu]  (for FRT logic)

        Returns
        -------
        x_next : ndarray (6,)
        """
        x   = np.asarray(x, dtype=float)
        p_gen, q_gen, v_dc, i_grid, omega, pitch = x
        v_w = float(wind_speed_mps)

        # ── 1. Aerodynamic power ──────────────────────────────────────
        p_aero = self.aero_power(omega, pitch, v_w)

        # ── 2. MPPT / power reference ─────────────────────────────────
        if u is not None and len(u) >= 1 and u[0] is not None:
            p_ref = float(u[0])
        else:
            if v_w < self.cfg.v_cut_in_mps or v_w > self.cfg.v_cut_out_mps:
                p_ref = 0.0
            elif v_w >= self.cfg.v_rated_mps:
                p_ref = 1.0   # rated power
            else:
                p_ref = p_aero   # track aerodynamic power

        # ── 3. FRT / Q reference ─────────────────────────────────────
        in_frt = v_terminal_pu < 0.90
        if u is not None and len(u) >= 2 and u[1] is not None:
            q_ref = float(u[1])
        elif in_frt:
            q_ref = self.frt_q_injection(v_terminal_pu, p_gen)
        else:
            q_ref = 0.0   # unity power factor in normal operation

        # ── 4. Grid-converter P dynamics (first-order lag) ────────────
        tau_conv = self.cfg.tau_grid_conv
        p_gen_next = p_gen + (p_ref - p_gen) * (dt / tau_conv)

        # ── 5. Grid-converter Q dynamics ─────────────────────────────
        q_gen_next = q_gen + (q_ref - q_gen) * (dt / tau_conv)

        # ── 6. DC link voltage dynamics ───────────────────────────────
        # C_dc × dV_dc/dt = I_gen_dc - I_grid_dc
        # I_gen_dc  ≈ P_aero / V_dc  (generator side)
        # I_grid_dc ≈ P_gen  / V_dc  (grid side)
        c_dc_pu = self.cfg.c_dc_mf * 1e-3  # [F] → scale by base
        if c_dc_pu > 1e-6 and v_dc > 0.1:
            i_gen_dc  = p_aero / v_dc
            i_grid_dc = p_gen  / v_dc
            dv_dc = (i_gen_dc - i_grid_dc) / c_dc_pu * dt
        else:
            dv_dc = 0.0
        v_dc_next = v_dc + dv_dc

        # ── 7. I_grid dynamics ────────────────────────────────────────
        s_app = math.sqrt(p_gen_next ** 2 + q_gen_next ** 2)
        i_grid_next = s_app

        # ── 8. Rotor speed dynamics ───────────────────────────────────
        if self.cfg.is_gfm:
            # GFM/VSM: swing equation  M×dω/dt = P_mech - P_elec - D×Δω
            m_vsm = 2.0 * self.cfg.virtual_inertia_s  # M = 2H
            d_vsm = self.cfg.virtual_damping
            p_mech = p_aero
            p_elec = p_gen
            domega = (p_mech - p_elec - d_vsm * (omega - 1.0)) / m_vsm * dt
        else:
            # GFL: first-order lag to MPPT omega reference
            omega_ref = min(self.mppt_omega_ref(v_w), 1.0)
            tau_omega = 0.50   # rotor speed time constant [s]
            domega = (omega_ref - omega) / tau_omega * dt
        omega_next = omega + domega

        # ── 9. Pitch angle dynamics ───────────────────────────────────
        # Pitch acts when P_gen > rated or when shutting down
        if v_w >= self.cfg.v_rated_mps or v_w < self.cfg.v_cut_in_mps:
            dpitch = self.pitch_ref(p_gen, dt)
        else:
            # Below rated: restore to 0° (MPPT zone)
            dpitch = -pitch * min(1.0, dt / 0.50)
        pitch_next = pitch + dpitch

        x_next = np.array([
            p_gen_next, q_gen_next, v_dc_next,
            i_grid_next, omega_next, pitch_next,
        ])
        return self.clamp(x_next)

    # ------------------------------------------------------------------
    # Measurement model  h(x) → [Va,Vb,Vc,Ia,Ib,Ic]
    # ------------------------------------------------------------------

    def h(self, x: np.ndarray, theta: float = 0.0) -> np.ndarray:
        """Reconstruct instantaneous three-phase phasors at the PCC."""
        x = np.asarray(x, dtype=float)
        p_gen, q_gen, _, i_grid, _, _ = x

        v_ac = 1.0  # PCC voltage ≈ 1 pu
        phi  = math.atan2(q_gen, p_gen) if (abs(p_gen) > 1e-6 or abs(q_gen) > 1e-6) else 0.0

        va =  v_ac * _SQRT2 * math.cos(theta)
        vb =  v_ac * _SQRT2 * math.cos(theta - _2PI / 3.0)
        vc =  v_ac * _SQRT2 * math.cos(theta + _2PI / 3.0)

        ia = i_grid * _SQRT2 * math.cos(theta - phi)
        ib = i_grid * _SQRT2 * math.cos(theta - phi - _2PI / 3.0)
        ic = i_grid * _SQRT2 * math.cos(theta - phi + _2PI / 3.0)

        return np.array([va, vb, vc, ia, ib, ic])

    # ------------------------------------------------------------------
    # Jacobian (linearised ∂h/∂x)
    # ------------------------------------------------------------------

    def H_jacobian(self, x: np.ndarray, theta: float = 0.0) -> np.ndarray:
        """6×6 linearised measurement Jacobian at state x."""
        x = np.asarray(x, dtype=float)
        p_gen, q_gen, _, i_grid, _, _ = x
        phi = (math.atan2(q_gen, p_gen)
               if (abs(p_gen) > 1e-6 or abs(q_gen) > 1e-6) else 0.0)
        H = np.zeros((6, 6))

        # ∂[Ia,Ib,Ic]/∂I_grid
        H[3, _I_GRID] = _SQRT2 * math.cos(theta - phi)
        H[4, _I_GRID] = _SQRT2 * math.cos(theta - phi - _2PI / 3.0)
        H[5, _I_GRID] = _SQRT2 * math.cos(theta - phi + _2PI / 3.0)

        denom = p_gen ** 2 + q_gen ** 2
        if denom > 1e-12:
            dphi_dp = -q_gen / denom
            dphi_dq =  p_gen / denom
            for row, off in zip([3, 4, 5], [0.0, -_2PI/3, _2PI/3]):
                d_di_dphi = i_grid * _SQRT2 * math.sin(theta - phi + off)
                H[row, _P_GEN] = d_di_dphi * dphi_dp
                H[row, _Q_GEN] = d_di_dphi * dphi_dq
        return H

    # ------------------------------------------------------------------
    # Clamp
    # ------------------------------------------------------------------

    def clamp(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float).copy()
        for i, (lo, hi) in enumerate(_STATE_BOUNDS):
            x[i] = float(np.clip(x[i], lo, hi))
        # Additional: pitch must satisfy physics (only positive)
        x[_PITCH] = max(0.0, x[_PITCH])
        return x

    # ------------------------------------------------------------------
    # Current limit (for protection mirror integration)
    # ------------------------------------------------------------------

    def fault_current_limit(self, t_elapsed: float = 0.0) -> float:
        """Time-varying AC fault current limit [pu]."""
        if not self.cfg.is_gfm:
            return self.cfg.i_max_cont_pu
        # GFM: exponential decay from transient to continuous
        i_trans = self.cfg.i_max_trans_pu
        i_cont  = self.cfg.i_max_cont_pu
        tau     = 0.10
        return i_cont + (i_trans - i_cont) * math.exp(-t_elapsed / tau)

    # ------------------------------------------------------------------
    # History API (mirrors BESSModel)
    # ------------------------------------------------------------------

    def push(self, state_dict: dict) -> None:
        if not hasattr(self, "_history"):
            self._history: list = []
        self._history.append(state_dict.copy())
        if len(self._history) > 500:
            self._history.pop(0)

    def latest(self) -> Optional[dict]:
        if not hasattr(self, "_history"):
            return None
        return self._history[-1] if self._history else None

    def history_array(self) -> np.ndarray:
        if not hasattr(self, "_history") or not self._history:
            return np.empty((0, self.N_STATES))
        return np.array([[s.get(n, 0.0) for n in self.STATE_NAMES]
                         for s in self._history])
