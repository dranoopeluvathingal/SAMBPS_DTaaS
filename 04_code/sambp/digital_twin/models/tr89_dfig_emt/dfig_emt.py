"""
TR-89 — DFIG Full EMT Simulator
================================
Open-source replacement for PSCAD DFIG module.

Physics
-------
5th-order dq EMT model (stator and rotor flux dynamics in synchronous frame):

  dψs_d/dt = vs_d - Rs·is_d + ωs·ψs_q
  dψs_q/dt = vs_q - Rs·is_q - ωs·ψs_d
  dψr_d/dt = vr_d - Rr·ir_d + ωslip·ψr_q
  dψr_q/dt = vr_q - Rr·ir_q - ωslip·ψr_d
  dωr/dt   = (Te - Tm) / (2H)

Algebraic flux–current relations (T-equivalent circuit):

  ψs_d = Ls·is_d + Lm·ir_d
  ψs_q = Ls·is_q + Lm·ir_q
  ψr_d = Lr·ir_d + Lm·is_d
  ψr_q = Lr·ir_q + Lm·is_q

→ inverted to get currents from fluxes.

RSC (Rotor-Side Converter) — cascaded PI control
  Outer loop: Qs → ir_q_ref, Pe → ir_d_ref
  Inner loop: ir_d/q error → vr_d/q_ref

Crowbar — thyristor short across rotor terminals
  Activated: Ir_mag > Icb_thr  (default 2.0 pu)
  De-activated: Ir_mag < 0.9·Icb_thr AND t_cb > T_cb_min (default 50 ms)
  When active: vr_d = vr_q = 0; RSC blocked.

References
----------
Akhmatov (2003) — Analysis of dynamic behaviour of electric power systems
  with large amounts of wind power.  PhD thesis, DTU.
DPsim source: models/SP_Ph1_RXLine.cpp, DP_Ph1_SynchronGeneratorDQ.cpp.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy.integrate import solve_ivp


# ---------------------------------------------------------------------------
# Machine parameters
# ---------------------------------------------------------------------------

@dataclass
class DFIGParams:
    """Per-unit parameters for a DFIG (on machine base)."""
    # Ratings
    Sn_MVA:    float = 2.0      # rated apparent power [MVA]
    Vn_kV:     float = 0.69     # rated stator voltage [kV] (line-line)
    fn_Hz:     float = 50.0     # rated frequency [Hz]
    p_poles:   int   = 2        # number of pole pairs

    # Impedances [pu on machine base]
    Rs:        float = 0.0054   # stator resistance
    Rr:        float = 0.00607  # rotor resistance (referred to stator)
    Lls:       float = 0.1013   # stator leakage inductance
    Llr:       float = 0.1013   # rotor leakage inductance (referred)
    Lm:        float = 3.3765   # magnetising inductance
    H:         float = 3.5      # inertia constant [s]

    # RSC PI gains
    Kp_curr:   float = 0.5      # inner current loop proportional
    Ki_curr:   float = 10.0     # inner current loop integral
    Kp_pq:    float = 0.1      # outer P/Q loop proportional
    Ki_pq:    float = 2.0      # outer P/Q loop integral

    # Crowbar parameters
    Rcb:       float = 0.10     # crowbar resistance [pu]
    Icb_thr:   float = 2.0      # crowbar activation threshold [pu]
    T_cb_min:  float = 0.050    # minimum crowbar engagement time [s]

    # Derived (post-init)
    Ls:    float = field(init=False)
    Lr:    float = field(init=False)
    ωs:    float = field(init=False)   # synchronous angular frequency [rad/s]
    ωbase: float = field(init=False)   # same as ωs (alias for clarity)

    def __post_init__(self):
        self.Ls    = self.Lls + self.Lm
        self.Lr    = self.Llr + self.Lm
        # Akhmatov convention: electrical quantities in pu, time in seconds
        # → flux ODEs multiplied by ωbase = 2π·fn  (rad/s)
        self.ωs    = 2.0 * math.pi * self.fn_Hz
        self.ωbase = self.ωs


# ---------------------------------------------------------------------------
# State vector indices
# ---------------------------------------------------------------------------
# x = [ψs_d, ψs_q, ψr_d, ψr_q, ωr, int_ird, int_irq, int_Qs, int_Pe]
_PSd, _PSq, _PRd, _PRq, _WR, _IIrd, _IIrq, _IQs, _IPe = range(9)


# ---------------------------------------------------------------------------
# DFIGState — snapshot at one time point
# ---------------------------------------------------------------------------

@dataclass
class DFIGState:
    t:        float
    ψs_d:     float
    ψs_q:     float
    ψr_d:     float
    ψr_q:     float
    ωr:       float      # rotor speed [pu]
    is_d:     float      # stator d-current [pu]
    is_q:     float      # stator q-current [pu]
    ir_d:     float      # rotor d-current [pu]
    ir_q:     float      # rotor q-current [pu]
    Te:       float      # electromagnetic torque [pu]
    Pe:       float      # active power [pu]
    Qs:       float      # reactive power [pu]
    Ir_mag:   float      # rotor current magnitude [pu]
    crowbar:  bool       # crowbar active?
    vr_d:     float      # RSC output d-voltage [pu]
    vr_q:     float      # RSC output q-voltage [pu]


# ---------------------------------------------------------------------------
# EMT Engine
# ---------------------------------------------------------------------------

class DFIGEmtEngine:
    """
    Full EMT DFIG simulator.

    Usage
    -----
    engine = DFIGEmtEngine(params)
    engine.set_operating_point(Pe0=0.8, Qs0=0.0, vs_d0=0.0, vs_q0=1.0)
    engine.apply_voltage_dip(depth=0.8, t_start=0.1, t_end=0.25)
    result = engine.run(t_end=0.6, dt=50e-6)
    """

    def __init__(self, params: Optional[DFIGParams] = None):
        self.p = params or DFIGParams()

        # Flux–current inversion matrix (2×2 per dq)
        # [ψs]   [Ls  Lm] [is]
        # [ψr] = [Lm  Lr] [ir]
        # → [is; ir] = M^-1 · [ψs; ψr]
        det = self.p.Ls * self.p.Lr - self.p.Lm ** 2
        self._M_inv = np.array([
            [ self.p.Lr / det, -self.p.Lm / det],
            [-self.p.Lm / det,  self.p.Ls / det],
        ])

        # Voltage dip schedule
        self._dip_depth:  float = 0.0   # fraction remaining (1.0 = no dip)
        self._dip_tstart: float = 1e9
        self._dip_tend:   float = 1e9

        # Initial condition (set by set_operating_point)
        self._x0:       Optional[np.ndarray] = None
        self._vs_d_nom: float = 0.0
        self._vs_q_nom: float = 1.0
        self._Pe_ref:   float = 0.8
        self._Qs_ref:   float = 0.0

        # Crowbar state
        self._cb_active: bool  = False
        self._cb_t_on:   float = 0.0

    # ------------------------------------------------------------------
    def set_operating_point(self,
                            Pe0:  float = 0.8,
                            Qs0:  float = 0.0,
                            vs_d0: float = 0.0,
                            vs_q0: float = 1.0,
                            ωr0:  float = 1.10) -> None:
        """
        Set pre-fault steady state.

        Pe0, Qs0: scheduled P [pu], Q [pu] (on machine base)
        vs_d0/q0: pre-fault stator voltage dq [pu]
        ωr0: initial rotor speed [pu]  (typically 1.05–1.15 for super-sync)
        """
        p = self.p
        self._Pe_ref  = Pe0
        self._Qs_ref  = Qs0
        self._vs_d_nom = vs_d0
        self._vs_q_nom = vs_q0

        # Steady-state stator currents from Pe, Qs and vs
        vs = complex(vs_d0, vs_q0)
        Ss = complex(Pe0, Qs0)
        is_cplx = (Ss / vs).conjugate() if abs(vs) > 1e-9 else complex(0)
        is_d0 = is_cplx.real
        is_q0 = is_cplx.imag

        # Stator flux at steady state (dψs/dt = 0, ×ωbase cancels):
        # 0 = vs_d - Rs·is_d + ψs_q  → ψs_q = Rs·is_d - vs_d
        # 0 = vs_q - Rs·is_q - ψs_d  → ψs_d = vs_q - Rs·is_q
        ψs_d0 = vs_q0 - p.Rs * is_q0
        ψs_q0 = p.Rs * is_d0 - vs_d0

        # Rotor flux from algebraic (Lm known)
        # ψs_d = Ls·is_d + Lm·ir_d  → ir_d = (ψs_d - Ls·is_d)/Lm
        ir_d0 = (ψs_d0 - p.Ls * is_d0) / p.Lm
        ir_q0 = (ψs_q0 - p.Ls * is_q0) / p.Lm
        ψr_d0 = p.Lr * ir_d0 + p.Lm * is_d0
        ψr_q0 = p.Lr * ir_q0 + p.Lm * is_q0

        # RSC integrators initialised to hold steady state (zero error)
        x0 = np.zeros(9)
        x0[_PSd] = ψs_d0
        x0[_PSq] = ψs_q0
        x0[_PRd] = ψr_d0
        x0[_PRq] = ψr_q0
        x0[_WR]  = ωr0
        # inner current integrators: produce steady-state vr
        # at SS, dvr/dt = 0, so integrator holds vr directly — set to 0
        x0[_IIrd] = 0.0
        x0[_IIrq] = 0.0
        # outer loop integrators: at SS hold ir_ref values
        x0[_IQs] = ir_q0   # Qs integrator → ir_q_ref SS value
        x0[_IPe] = ir_d0   # Pe integrator → ir_d_ref SS value

        self._x0 = x0
        self._cb_active = False

    # ------------------------------------------------------------------
    def apply_voltage_dip(self,
                          depth:   float = 0.80,
                          t_start: float = 0.10,
                          t_end:   float = 0.25) -> None:
        """
        Schedule a symmetric voltage dip.
        depth: retained voltage fraction (0.2 = 80% dip, 0.8 = 20% dip).
        """
        self._dip_depth  = depth
        self._dip_tstart = t_start
        self._dip_tend   = t_end

    # ------------------------------------------------------------------
    def run(self, t_end: float = 0.6, dt: float = 50e-6) -> List[DFIGState]:
        """
        Integrate the 9-state ODE from t=0 to t_end.

        Splits at (a) voltage discontinuities, and (b) crowbar switching
        events detected via solve_ivp terminal events.  This avoids the
        classic problem of stateful switching inside an RK45 ODE call.
        """
        if self._x0 is None:
            self.set_operating_point()

        # Deterministic breakpoints (voltage transitions)
        bp_fixed = sorted({0.0, self._dip_tstart, self._dip_tend, t_end})
        bp_fixed = [b for b in bp_fixed if 0.0 <= b <= t_end]

        # Reset crowbar
        self._cb_active = False
        self._cb_t_on   = 0.0

        x = self._x0.copy()
        all_states: List[DFIGState] = []

        seg_starts = list(bp_fixed)
        seg_idx = 0

        while seg_idx < len(seg_starts) - 1:
            t0 = seg_starts[seg_idx]
            t1 = seg_starts[seg_idx + 1]
            if t1 <= t0 + 1e-12:
                seg_idx += 1
                continue

            n_pts = max(2, int(round((t1 - t0) / dt)) + 1)
            t_eval = np.linspace(t0, t1, n_pts)

            # Event: crowbar ON — Ir exceeds threshold
            def ev_cb_on(t, x, _self=self):
                is_d, is_q, ir_d, ir_q = _self._currents(x[0],x[1],x[2],x[3])
                return math.hypot(ir_d, ir_q) - _self.p.Icb_thr

            # Event: crowbar OFF — Ir falls below 90% threshold (only after min time)
            _cb_ton = self._cb_t_on
            def ev_cb_off(t, x, _self=self, _ton=_cb_ton):
                if (t - _ton) < _self.p.T_cb_min:
                    return 1.0   # never fires before minimum time
                is_d, is_q, ir_d, ir_q = _self._currents(x[0],x[1],x[2],x[3])
                return math.hypot(ir_d, ir_q) - 0.9 * _self.p.Icb_thr

            if not self._cb_active:
                ev_cb_on.terminal  = True
                ev_cb_on.direction = 1
                events = [ev_cb_on]
            else:
                ev_cb_off.terminal  = True
                ev_cb_off.direction = -1
                events = [ev_cb_off]

            sol = solve_ivp(
                fun=self._ode,
                t_span=(t0, t1),
                y0=x.copy(),
                method='RK45',
                t_eval=t_eval,
                events=events,
                max_step=dt,
                rtol=1e-6,
                atol=1e-9,
            )

            # Append states for this segment
            t_last = all_states[-1].t if all_states else -1.0
            for j, t in enumerate(sol.t):
                if t - t_last < 1e-12:
                    continue
                state = self._build_state(t, sol.y[:, j])
                all_states.append(state)
                t_last = t

            x = sol.y[:, -1]

            # If event fired, switch crowbar and insert a new breakpoint
            if sol.t_events and sol.t_events[0].size > 0:
                t_event = float(sol.t_events[0][0])
                x_event = sol.y_events[0][0]
                if not self._cb_active:
                    self._cb_active = True
                    self._cb_t_on   = t_event
                else:
                    self._cb_active = False
                # Insert event time as next breakpoint (continue from there)
                seg_starts.insert(seg_idx + 1, t_event)
                x = x_event
            else:
                seg_idx += 1

        return all_states

    def _build_state(self, t: float, x: np.ndarray) -> 'DFIGState':
        """Build DFIGState using CURRENT crowbar flag (no side-effects)."""
        p = self.p
        ψs_d, ψs_q = x[_PSd], x[_PSq]
        ψr_d, ψr_q = x[_PRd], x[_PRq]
        ωr = x[_WR]

        vs_d, vs_q = self._vs(t)
        is_d, is_q, ir_d, ir_q = self._currents(ψs_d, ψs_q, ψr_d, ψr_q)
        Ir_mag = math.hypot(ir_d, ir_q)
        crowbar = self._cb_active

        Te = p.Lm * (is_q * ir_d - is_d * ir_q)
        Pe = vs_d * is_d + vs_q * is_q
        Qs = vs_q * is_d - vs_d * is_q

        if crowbar:
            vr_d = -(p.Rcb * ir_d)
            vr_q = -(p.Rcb * ir_q)
        else:
            vr_d, vr_q, *_ = self._rsc_outputs(t, x, ir_d, ir_q, False)

        return DFIGState(
            t=t, ψs_d=ψs_d, ψs_q=ψs_q, ψr_d=ψr_d, ψr_q=ψr_q, ωr=ωr,
            is_d=is_d, is_q=is_q, ir_d=ir_d, ir_q=ir_q,
            Te=round(Te, 5), Pe=round(Pe, 5), Qs=round(Qs, 5),
            Ir_mag=round(Ir_mag, 5), crowbar=crowbar,
            vr_d=round(vr_d, 5), vr_q=round(vr_q, 5),
        )

    # ------------------------------------------------------------------
    def _vs(self, t: float) -> Tuple[float, float]:
        """Return (vs_d, vs_q) at time t, applying any scheduled dip."""
        if self._dip_tstart <= t <= self._dip_tend:
            return (self._vs_d_nom * self._dip_depth,
                    self._vs_q_nom * self._dip_depth)
        return self._vs_d_nom, self._vs_q_nom

    # ------------------------------------------------------------------
    def _currents(self, ψs_d, ψs_q, ψr_d, ψr_q
                  ) -> Tuple[float, float, float, float]:
        """Invert flux equations to obtain dq currents."""
        M = self._M_inv
        is_d = M[0, 0] * ψs_d + M[0, 1] * ψr_d
        is_q = M[0, 0] * ψs_q + M[0, 1] * ψr_q
        ir_d = M[1, 0] * ψs_d + M[1, 1] * ψr_d
        ir_q = M[1, 0] * ψs_q + M[1, 1] * ψr_q
        return is_d, is_q, ir_d, ir_q

    # ------------------------------------------------------------------
    def _crowbar_check(self, t: float, Ir_mag: float) -> bool:
        """Update crowbar state machine; return True if crowbar is active."""
        p = self.p
        if not self._cb_active:
            if Ir_mag > p.Icb_thr:
                self._cb_active = True
                self._cb_t_on   = t
        else:
            # De-activate if current fallen and minimum time elapsed
            if (Ir_mag < 0.9 * p.Icb_thr and
                    (t - self._cb_t_on) > p.T_cb_min):
                self._cb_active = False
        return self._cb_active

    # ------------------------------------------------------------------
    def _rsc_outputs(self, t: float, x: np.ndarray,
                     ir_d: float, ir_q: float,
                     crowbar: bool
                     ) -> Tuple[float, float, float, float, float, float]:
        """
        Compute RSC outputs and integrator derivatives.

        Returns (vr_d, vr_q, dint_ird, dint_irq, dint_Qs, dint_Pe).
        """
        p = self.p

        # If crowbar active, RSC is blocked
        if crowbar:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

        int_ird = x[_IIrd]
        int_irq = x[_IIrq]
        int_Qs  = x[_IQs]
        int_Pe  = x[_IPe]

        # ── Outer loops ──────────────────────────────────────────────
        # Reactive power outer loop → ir_q_ref
        # Pe outer loop → ir_d_ref
        # (approximation: Pe ≈ vs_q·is_q, Qs ≈ vs_q·is_d at vs_d≈0)
        # Use integrator state as reference — updated below
        ir_q_ref = p.Kp_pq * (self._Qs_ref - x[_IQs]) + int_Qs
        ir_d_ref = p.Kp_pq * (self._Pe_ref - x[_IPe]) + int_Pe

        # Clamp references to ±1.5 pu
        ir_q_ref = max(-1.5, min(1.5, ir_q_ref))
        ir_d_ref = max(-1.5, min(1.5, ir_d_ref))

        # ── Inner current loops ───────────────────────────────────────
        err_d = ir_d_ref - ir_d
        err_q = ir_q_ref - ir_q

        vr_d = p.Kp_curr * err_d + int_ird
        vr_q = p.Kp_curr * err_q + int_irq

        # Clamp rotor voltage to ±0.3 pu (converter DC-link limit)
        vr_d = max(-0.30, min(0.30, vr_d))
        vr_q = max(-0.30, min(0.30, vr_q))

        # Integrator derivatives
        dint_ird = p.Ki_curr * err_d
        dint_irq = p.Ki_curr * err_q

        # Outer integrators track Qs and Pe error
        # (simplified: outer loop uses slower Ki_pq)
        dint_Qs = p.Ki_pq * (self._Qs_ref - 0.0)   # placeholder — see note
        dint_Pe = p.Ki_pq * (self._Pe_ref - 0.0)    # updated in _ode

        return vr_d, vr_q, dint_ird, dint_irq, dint_Qs, dint_Pe

    # ------------------------------------------------------------------
    def _ode(self, t: float, x: np.ndarray) -> np.ndarray:
        """
        9-state ODE — Akhmatov 5th-order DFIG in synchronous dq frame.

        Electrical quantities in pu; time in physical seconds.
        Flux ODEs are multiplied by ωbase = 2π·fn (rad/s) so that the
        natural-flux oscillation runs at fn = 50 Hz in real time.
        Slip is per-unit: ωslip_pu = 1 - ωr_pu.
        """
        p = self.p
        dx = np.zeros(9)

        ψs_d, ψs_q = x[_PSd], x[_PSq]
        ψr_d, ψr_q = x[_PRd], x[_PRq]
        ωr = x[_WR]           # rotor speed [pu] = ωr_rad / ωbase

        vs_d, vs_q = self._vs(t)

        # Current from fluxes
        is_d, is_q, ir_d, ir_q = self._currents(ψs_d, ψs_q, ψr_d, ψr_q)

        # Crowbar state is managed by the event-based run() loop
        crowbar = self._cb_active

        # Slip [pu]: s = (ωs - ωr) / ωs  (positive for sub-sync, neg for super-sync)
        ωslip_pu = 1.0 - ωr

        # Rotor current magnitude (for crowbar vr calculation below)
        Ir_mag = math.hypot(ir_d, ir_q)

        # RSC output
        vr_d, vr_q, dint_ird, dint_irq, dint_Qs, dint_Pe = \
            self._rsc_outputs(t, x, ir_d, ir_q, crowbar)

        # If crowbar active: RSC blocked, rotor shorted through Rcb
        if crowbar:
            vr_d = -(p.Rcb * ir_d)
            vr_q = -(p.Rcb * ir_q)

        # ── Stator flux ODEs  (×ωbase converts pu-time to seconds) ──
        # Ref: Akhmatov (2003) eq. 4.14–4.17; DPsim DP_Ph1_SynGenDQ
        dx[_PSd] = p.ωbase * (vs_d - p.Rs * is_d + ψs_q)
        dx[_PSq] = p.ωbase * (vs_q - p.Rs * is_q - ψs_d)

        # ── Rotor flux ODEs  (ωslip_pu: relative speed of rotor to sync) ─
        dx[_PRd] = p.ωbase * (vr_d - p.Rr * ir_d + ωslip_pu * ψr_q)
        dx[_PRq] = p.ωbase * (vr_q - p.Rr * ir_q - ωslip_pu * ψr_d)

        # ── Electromagnetic torque [pu] ──────────────────────────────
        Te = p.Lm * (is_q * ir_d - is_d * ir_q)

        # Mechanical torque (constant-power turbine model)
        Tm = self._Pe_ref / max(ωr, 0.5)

        # ── Rotor speed [pu/s] ───────────────────────────────────────
        # dωr/dt = (Te - Tm) / (2H)  [pu/s in physical time via ωbase normalisation]
        dx[_WR] = (Te - Tm) / (2.0 * p.H)

        # ── RSC integrators ──────────────────────────────────────────
        dx[_IIrd] = dint_ird
        dx[_IIrq] = dint_irq

        # Outer loop integrators: track actual Pe and Qs
        Pe_act = vs_d * is_d + vs_q * is_q
        Qs_act = vs_q * is_d - vs_d * is_q
        dx[_IQs] = p.Ki_pq * (self._Qs_ref - Qs_act)
        dx[_IPe] = p.Ki_pq * (self._Pe_ref - Pe_act)

        return dx

    # ------------------------------------------------------------------
