"""
TR-90 — PV Inverter Full EMT Simulator
========================================
Open-source replacement for PSCAD VSC/REGCA module.

Architecture
------------
  DC side:  PV array → DC-link capacitor → VSC
  AC side:  VSC → RL filter → grid
  Control:  2nd-order SRF-PLL → cascaded dq current control (REGCA inner loop)

State vector (8 states — pu electrical, physical-second time)
-------------------------------------------------------------
  x[0]  id         — d-axis filter current  [pu]
  x[1]  iq         — q-axis filter current  [pu]
  x[2]  vdc        — DC-link voltage        [pu]
  x[3]  θ_pll      — PLL phase angle        [rad]
  x[4]  ε_pll      — PLL loop-filter integrator (= ∫vq_g dt)
  x[5]  int_id     — d-axis current-loop integrator
  x[6]  int_iq     — q-axis current-loop integrator
  x[7]  int_vdc    — DC-voltage outer loop integrator  (→ id_ref)

Outer Q reference is algebraic (no integrator needed for fixed Qe_ref).

SRF-PLL (Teodorescu 2011, Type II, 2nd-order)
----------------------------------------------
  vq_g = grid Q-axis voltage in PLL frame  (= 0 when locked)
  ω_pll = ω_nom + Kp_pll·vq_g + Ki_pll·ε_pll    [pu, algebraic]
  dθ_pll/dt = ωbase · ω_pll
  dε_pll/dt = vq_g

Filter ODEs (×ωbase converts pu inductance + pu time → physical seconds)
--------------------------------------------------------------------------
  did/dt = ωbase·(vd_conv - vd_g - Rf·id  + ω_pll·Lf·iq)
  diq/dt = ωbase·(vq_conv - vq_g - Rf·iq  - ω_pll·Lf·id)

Decoupling (cancels cross-terms in filter):
  vd_conv = PI_d + vd_g - ω_pll·Lf·iq   (pu — NO ωbase here)
  vq_conv = PI_q + vq_g + ω_pll·Lf·id

DC-link:
  dvdc/dt = (Ppv - Pe) / (Cdc·vdc)

References
----------
  Teodorescu et al., Grid Converters for PV and Wind Power, Wiley 2011.
  WECC REGCA/REECB model spec v2.0, 2019.
  DPsim DP_Ph1_VSI2Bus.cpp.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy.integrate import solve_ivp

# ---------------------------------------------------------------------------
# State indices (8 states)
# ---------------------------------------------------------------------------
_ID, _IQ, _VDC, _TPLL, _EPLL, _IID, _IIQ, _IVDC = range(8)


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

@dataclass
class PVParams:
    """PV inverter pu parameters (machine base)."""
    Sn_MVA:    float = 1.0
    Vn_kV:     float = 0.415
    fn_Hz:     float = 50.0

    # RL filter
    Lf:        float = 0.08     # [pu]
    Rf:        float = 0.005    # [pu]

    # DC-link
    Cdc:       float = 0.05     # [pu·s]
    Vdc_nom:   float = 1.07     # [pu]

    # PV array (quadratic MPP model)
    Vmpp:      float = 1.07     # MPP voltage = Vdc_nom [pu]
    Pmpp:      float = 1.0      # MPP power at STC [pu]

    # SRF-PLL (Teodorescu Type II)
    Kp_pll:    float = 50.0
    Ki_pll:    float = 1000.0
    ω_nom:     float = 1.0      # [pu]

    # Inner current loop
    Kp_i:      float = 0.5
    Ki_i:      float = 15.0

    # DC-voltage outer loop
    Kp_vdc:    float = 1.5
    Ki_vdc:    float = 15.0

    # Q outer loop (proportional-only for simplicity)
    Kp_q:      float = 2.0

    # Limits
    Id_max:    float = 1.10
    Iq_max:    float = 1.10
    I_max:     float = 1.10
    Vconv_max: float = 1.15     # SVPWM modulation limit

    # Derived
    ωbase: float = field(init=False)

    def __post_init__(self):
        self.ωbase = 2.0 * math.pi * self.fn_Hz


# ---------------------------------------------------------------------------
# PV array (quadratic MPP)
# ---------------------------------------------------------------------------

def pv_power(G_pu: float, Vdc: float, p: PVParams) -> float:
    """
    PV P-V curve — smooth quadratic through (0,0), peak at (Vmpp, Pmpp),
    and zero at Voc = 1.25·Vmpp.

    k = 1/(Voc - Vmpp)²  ensures P=0 at Voc with no discontinuity.
    This replicates REGCA curtailment without a hard step at Voc,
    avoiding RK45 stiffness at the Ppv=0 boundary.
    """
    Voc = 1.25 * p.Vmpp
    dv  = Vdc - p.Vmpp
    dvoc = Voc  - p.Vmpp          # = 0.25·Vmpp
    k   = 1.0 / max(dvoc ** 2, 1e-9)
    return p.Pmpp * G_pu * max(0.0, 1.0 - k * dv ** 2)


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

@dataclass
class PVState:
    t:          float
    id:         float
    iq:         float
    vdc:        float
    θ_pll:      float
    ω_pll:      float      # algebraic (not a state)
    vd_grid:    float
    vq_grid:    float
    Pe:         float
    Qe:         float
    Ppv:        float
    id_ref:     float
    iq_ref:     float
    pll_locked: bool
    lvrt_active: bool
    vd_conv:    float
    vq_conv:    float


# ---------------------------------------------------------------------------
# EMT Engine
# ---------------------------------------------------------------------------

class PVEmtEngine:
    """
    Full EMT PV inverter simulator — REGCA-equivalent.

    Usage
    -----
    eng = PVEmtEngine()
    eng.set_operating_point(Pe0=0.9, Qe0=0.0)
    eng.apply_voltage_dip(depth=0.50, t_start=0.10, t_end=0.25)
    eng.set_irradiance_step(G_new=0.5, t_step=0.30)
    states = eng.run(t_end=0.60, dt=100e-6)
    """

    def __init__(self, params: Optional[PVParams] = None):
        self.p = params or PVParams()
        self._x0: Optional[np.ndarray] = None

        self._vg_nom:    float = 1.0
        self._dip_depth: float = 1.0
        self._dip_ts:    float = 1e9
        self._dip_te:    float = 1e9

        self._G_nom:     float = 1.0
        self._G_new:     float = 1.0
        self._G_t_step:  float = 1e9

        self._Pe_ref:    float = 0.9
        self._Qe_ref:    float = 0.0

    # ------------------------------------------------------------------
    def set_operating_point(self, Pe0=0.9, Qe0=0.0, Vg0=1.0) -> None:
        p = self.p
        self._Pe_ref = Pe0
        self._Qe_ref = Qe0
        self._vg_nom = Vg0

        # SS: PLL locked → vd = Vg0, vq = 0
        vd_g = Vg0;  vq_g = 0.0

        # SS currents: Pe = vd·id, Qe = -vd·iq  (vq=0)
        id0 =  Pe0 / max(vd_g, 1e-6)
        iq0 = -Qe0 / max(vd_g, 1e-6)

        # Clamp
        Imag = math.hypot(id0, iq0)
        if Imag > p.I_max:
            id0 *= p.I_max / Imag
            iq0 *= p.I_max / Imag

        # SS converter voltage (decoupled):
        # vd_conv = vd_g + Rf*id0 - ω_nom*Lf*iq0
        # vq_conv = vq_g + Rf*iq0 + ω_nom*Lf*id0
        vd_conv0 = vd_g + p.Rf * id0 - p.ω_nom * p.Lf * iq0
        vq_conv0 = vq_g + p.Rf * iq0 + p.ω_nom * p.Lf * id0

        # Current-loop integrators at SS (err=0):
        # vd_conv = 0 + int_id + vd_g + decoupling → int_id = Rf*id0 - ω*Lf*iq0
        int_id0 = p.Rf * id0 - p.ω_nom * p.Lf * iq0
        int_iq0 = p.Rf * iq0 + p.ω_nom * p.Lf * id0

        # Vdc outer: at SS dvdc/dt = 0 → Ppv = Pe0 → Vdc = Vdc_nom, err=0
        # int_vdc holds id_ref = id0
        int_vdc0 = id0

        x0 = np.zeros(8)
        x0[_ID]   = id0
        x0[_IQ]   = iq0
        x0[_VDC]  = p.Vdc_nom
        x0[_TPLL] = 0.0
        x0[_EPLL] = 0.0       # PLL integral = 0 (locked, vq_g=0)
        x0[_IID]  = int_id0
        x0[_IIQ]  = int_iq0
        x0[_IVDC] = int_vdc0

        self._x0 = x0

    # ------------------------------------------------------------------
    def apply_voltage_dip(self, depth=0.5, t_start=0.10, t_end=0.25):
        self._dip_depth = depth
        self._dip_ts    = t_start
        self._dip_te    = t_end

    def set_irradiance_step(self, G_new=0.5, t_step=0.30):
        self._G_new    = G_new
        self._G_t_step = t_step

    # ------------------------------------------------------------------
    def _vg(self, t: float) -> float:
        if self._dip_ts <= t <= self._dip_te:
            return self._vg_nom * self._dip_depth
        return self._vg_nom

    def _G(self, t: float) -> float:
        return self._G_new if t >= self._G_t_step else self._G_nom

    # ------------------------------------------------------------------
    def _grid_dq(self, t: float, θ_pll: float) -> Tuple[float, float]:
        """Grid voltage resolved into PLL dq frame."""
        Vg = self._vg(t)
        θ_grid = self.p.ωbase * t      # grid angle (phase a, radians)
        δθ = θ_grid - θ_pll
        return Vg * math.cos(δθ), Vg * math.sin(δθ)

    # ------------------------------------------------------------------
    def _omega_pll(self, vq_g: float, ε_pll: float) -> float:
        """2nd-order SRF-PLL: ω_pll is algebraic."""
        p = self.p
        return p.ω_nom + p.Kp_pll * vq_g + p.Ki_pll * ε_pll

    # ------------------------------------------------------------------
    def _current_refs(self, vdc: float, id_: float, iq: float,
                      vd_g: float, vq_g: float,
                      int_vdc: float) -> Tuple[float, float]:
        """Compute (id_ref, iq_ref) from outer loops with LVRT."""
        p = self.p
        Vt = math.hypot(vd_g, vq_g)
        lvrt = Vt < 0.90

        if lvrt:
            # IEC 61400-21 reactive priority: Δiq = 2·(1-Vt), capped at 1.0
            Δiq    = min(1.0, 2.0 * (1.0 - Vt))
            iq_ref = -Δiq                             # inject capacitive
            id_budget = math.sqrt(max(0.0, p.I_max**2 - iq_ref**2))
            id_ref = min(int_vdc, id_budget)
        else:
            # DC-voltage outer loop → id_ref
            # Error: vdc - Vdc_nom > 0 when overvoltage → increase id_ref
            # (more active export → Pe↑ → dvdc/dt = (Ppv-Pe)/Cdc < 0 → discharge)
            vdc_err = vdc - p.Vdc_nom
            id_ref  = p.Kp_vdc * vdc_err + int_vdc
            id_ref  = float(np.clip(id_ref, 0.0, p.Id_max))

            # Q outer loop (proportional): Qe = -vd·iq at vq≈0
            Qe_act = vq_g * id_ - vd_g * iq
            iq_ref = p.Kp_q * (self._Qe_ref - Qe_act)
            iq_ref = float(np.clip(iq_ref, -p.Iq_max, p.Iq_max))

        # Total current limit
        I_mag = math.hypot(id_ref, iq_ref)
        if I_mag > p.I_max:
            scale  = p.I_max / I_mag
            id_ref *= scale
            iq_ref *= scale

        return id_ref, iq_ref

    # ------------------------------------------------------------------
    def _conv_voltage(self, id_: float, iq: float,
                      vd_g: float, vq_g: float,
                      ω_pll: float,
                      err_d: float, err_q: float,
                      int_id: float, int_iq: float
                      ) -> Tuple[float, float]:
        """Compute (vd_conv, vq_conv) with decoupling and SVPWM clamp."""
        p = self.p
        # Decoupling (pu — ωbase is in the ODE, not here)
        vd_ff = -ω_pll * p.Lf * iq
        vq_ff =  ω_pll * p.Lf * id_

        vd = p.Kp_i * err_d + int_id + vd_g + vd_ff
        vq = p.Kp_i * err_q + int_iq + vq_g + vq_ff

        # SVPWM modulation limit
        Vm = math.hypot(vd, vq)
        if Vm > p.Vconv_max:
            vd *= p.Vconv_max / Vm
            vq *= p.Vconv_max / Vm

        return vd, vq

    # ------------------------------------------------------------------
    def _ode(self, t: float, x: np.ndarray) -> np.ndarray:
        """8-state ODE RHS."""
        p = self.p
        dx = np.zeros(8)

        id_ = x[_ID];  iq = x[_IQ];  vdc = x[_VDC]
        θ_pll = x[_TPLL];  ε_pll = x[_EPLL]
        int_id = x[_IID];  int_iq = x[_IIQ]
        int_vdc = x[_IVDC]

        # Grid voltage in PLL frame
        vd_g, vq_g = self._grid_dq(t, θ_pll)

        # SRF-PLL (algebraic ω_pll)
        ω_pll = self._omega_pll(vq_g, ε_pll)
        dx[_TPLL] = p.ωbase * ω_pll
        dx[_EPLL] = vq_g

        # PV power and AC power
        G   = self._G(t)
        Ppv = pv_power(G, vdc, p)
        Pe  = vd_g * id_ + vq_g * iq

        # Current references
        id_ref, iq_ref = self._current_refs(vdc, id_, iq, vd_g, vq_g, int_vdc)

        # Inner loop errors
        err_d = id_ref - id_
        err_q = iq_ref - iq

        # Converter voltage
        vd_c, vq_c = self._conv_voltage(id_, iq, vd_g, vq_g, ω_pll,
                                         err_d, err_q, int_id, int_iq)

        # ── Filter ODEs (×ωbase: pu-induct·pu-current/pu-time → physical) ─
        dx[_ID] = p.ωbase * (vd_c - vd_g - p.Rf * id_ + ω_pll * p.Lf * iq)
        dx[_IQ] = p.ωbase * (vq_c - vq_g - p.Rf * iq  - ω_pll * p.Lf * id_)

        # ── DC-link ────────────────────────────────────────────────────────
        dx[_VDC] = (Ppv - Pe) / (p.Cdc * max(vdc, 0.1))

        # ── Inner current loop integrators ─────────────────────────────────
        dx[_IID] = p.Ki_i * err_d
        dx[_IIQ] = p.Ki_i * err_q

        # ── DC-voltage outer loop integrator (with anti-windup) ────────────
        vdc_err_int = vdc - p.Vdc_nom
        # Freeze integrator if output is saturated and error would worsen windup
        id_ref_unclipped = p.Kp_vdc * vdc_err_int + x[_IVDC]
        saturated_hi = id_ref_unclipped >= p.Id_max and vdc_err_int > 0
        saturated_lo = id_ref_unclipped <= 0.0       and vdc_err_int < 0
        if saturated_hi or saturated_lo:
            dx[_IVDC] = 0.0
        else:
            dx[_IVDC] = p.Ki_vdc * vdc_err_int

        return dx

    # ------------------------------------------------------------------
    def run(self, t_end: float = 0.6, dt: float = 100e-6) -> List[PVState]:
        if self._x0 is None:
            self.set_operating_point()

        bp = sorted({0.0, self._dip_ts, self._dip_te,
                     self._G_t_step, t_end})
        bp = [b for b in bp if 0.0 <= b <= t_end]

        x = self._x0.copy()
        all_states: List[PVState] = []

        for i in range(len(bp) - 1):
            t0, t1 = bp[i], bp[i + 1]
            if t1 - t0 < 1e-12:
                continue
            n  = max(2, int(round((t1 - t0) / dt)) + 1)
            te = np.linspace(t0, t1, n)

            sol = solve_ivp(self._ode, (t0, t1), x.copy(),
                            method='RK45', t_eval=te,
                            max_step=dt, rtol=1e-6, atol=1e-9)

            t_last = all_states[-1].t if all_states else -1.0
            for j, t in enumerate(sol.t):
                if t - t_last < 1e-12:
                    continue
                all_states.append(self._build(t, sol.y[:, j]))
                t_last = t
            x = sol.y[:, -1]

        return all_states

    # ------------------------------------------------------------------
    def _build(self, t: float, x: np.ndarray) -> PVState:
        p  = self.p
        id_ = x[_ID];  iq = x[_IQ];  vdc = x[_VDC]
        θ_pll = x[_TPLL];  ε_pll = x[_EPLL]

        vd_g, vq_g = self._grid_dq(t, θ_pll)
        ω_pll = self._omega_pll(vq_g, ε_pll)

        G   = self._G(t)
        Ppv = pv_power(G, vdc, p)
        Pe  = vd_g * id_ + vq_g * iq
        Qe  = vq_g * id_ - vd_g * iq
        Vt  = math.hypot(vd_g, vq_g)

        id_ref, iq_ref = self._current_refs(vdc, id_, iq, vd_g, vq_g, x[_IVDC])

        err_d = id_ref - id_;  err_q = iq_ref - iq
        vd_c, vq_c = self._conv_voltage(id_, iq, vd_g, vq_g, ω_pll,
                                         err_d, err_q, x[_IID], x[_IIQ])

        return PVState(
            t=t, id=round(id_, 5), iq=round(iq, 5),
            vdc=round(vdc, 5), θ_pll=round(θ_pll, 4),
            ω_pll=round(ω_pll, 6),
            vd_grid=round(vd_g, 5), vq_grid=round(vq_g, 5),
            Pe=round(Pe, 5), Qe=round(Qe, 5), Ppv=round(Ppv, 5),
            id_ref=round(id_ref, 5), iq_ref=round(iq_ref, 5),
            pll_locked=abs(vq_g) < 0.02,
            lvrt_active=Vt < 0.90,
            vd_conv=round(vd_c, 5), vq_conv=round(vq_c, 5),
        )
