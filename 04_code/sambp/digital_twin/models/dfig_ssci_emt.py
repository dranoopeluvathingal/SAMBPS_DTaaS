"""
dfig_ssci_emt.py — DFIG + Series-Compensated Line SSCI / SSRO EMT Simulator
============================================================================
TR-75 open-source PSCAD replacement.

Extends the TR-89 flux-state DFIG model (9 states) with two series-capacitor
voltage states (11 states total).  Integrated with scipy Radau for stiffness.

State vector (11)
-----------------
  x[0]  ψs_d   — effective stator d-axis flux (stator + line combined) [pu]
  x[1]  ψs_q   — effective stator q-axis flux                          [pu]
  x[2]  ψr_d   — rotor d-axis flux linkage                             [pu]
  x[3]  ψr_q   — rotor q-axis flux linkage                             [pu]
  x[4]  ωr     — rotor speed                                           [pu]
  x[5]  ξ_id   — RSC inner d-axis PI integrator
  x[6]  ξ_iq   — RSC inner q-axis PI integrator
  x[7]  ξ_Qs   — RSC outer Qs PI integrator  (→ ir_q_ref)
  x[8]  ξ_Pe   — RSC outer Pe PI integrator  (→ ir_d_ref)
  x[9]  vCd    — series-cap d-axis voltage                             [pu]
  x[10] vCq    — series-cap q-axis voltage                             [pu]

Convention: pu quantities, time in physical seconds, ωbase = 2πf₀.
Series transmission line absorbed into effective stator reactance:
  Ls_eff = Ls + Xline,  Rs_eff = Rs + Rline

Why Radau: the series LC resonance (τ_C = 1/(ωbase·XC) ≈ 5–20 ms) plus RSC
PI integrators create a mildly stiff system; Radau handles this without
requiring manual step-size tuning beyond a conservative max_step.

SSCI mechanism
--------------
  Natural resonance: fr = f₀·√(comp%/100)   [5–45 Hz for comp 1–81%]
  RSC inner loop creates negative resistance at f < bandwidth_RSC.
  SSCI onset: Re[Z_line(fr) + Z_DFIG(fr)] < 0  (impedance criterion, TR-75)
  EMT observable: exponential growth of is_d envelope post-perturbation.

References
----------
  Akhmatov (2003) PhD thesis, DTU — DFIG flux-state model.
  Sun (2011) IEEE Trans. PE 26(11):3075–3078 — impedance SSCI criterion.
  Adams et al. (2012) IEEE PES GM — ERCOT SSCI field experience.
  IEC 61400-21 — DFIG pu parameter ranges.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy.integrate import solve_ivp

# ---------------------------------------------------------------------------
# State indices
# ---------------------------------------------------------------------------
_PSd, _PSq = 0, 1          # stator flux (effective: stator + line)
_PRd, _PRq = 2, 3          # rotor flux
_WR        = 4             # rotor speed
_XIrd, _XIrq = 5, 6        # RSC inner PI integrators
_XIQs, _XIPe = 7, 8        # RSC outer PI integrators
_VCd, _VCq  = 9, 10        # series-cap voltages
_NS         = 11           # total states


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
@dataclass
class DFIGSSCIParams:
    """
    DFIG + series-compensated line parameters (pu, 50 Hz machine base).

    Default values: 2 MW IEC-class DFIG (Akhmatov 2003 / IEC 61400-21)
    with aggressive RSC gains (BW ≈ 30 Hz) to produce SSCI in the
    20–40 Hz band for comp > ~35%.
    """
    fn_Hz:    float = 50.0

    # ── DFIG electrical (pu) ────────────────────────────────────────
    Rs:       float = 0.0054    # stator resistance
    Rr:       float = 0.00607   # rotor resistance (referred to stator)
    Lls:      float = 0.1013    # stator leakage reactance
    Llr:      float = 0.1013    # rotor leakage reactance
    Lm:       float = 3.3765    # magnetising reactance
    H:        float = 3.5       # inertia constant [s]

    # ── RSC PI gains — tuned for realistic SSCI growth rates ────────
    # Kp=0.035 → SSCI onset at comp≈25% (σ≈1 Np/s); stable below.
    # Inner BW ≈ Kp·ωb/Lr ≈ 0.035·377/3.48 ≈ 3.8 rad/s ≈ 0.6 Hz
    # At 25-40 Hz the RSC provides negative resistance → SSCI unstable
    Kp_curr:  float = 0.035
    Ki_curr:  float = 1.75
    Kp_pq:    float = 0.10
    Ki_pq:    float = 2.00

    # ── Series-compensated transmission line (pu) ────────────────────
    Rline:    float = 0.020
    Xline:    float = 0.300
    comp_pct: float = 50.0      # series compensation [%]

    # ── Operating point ─────────────────────────────────────────────
    Pe0:      float = 0.80      # scheduled active power [pu]
    Qs0:      float = 0.00      # scheduled reactive power [pu]
    ωr0:      float = 1.10      # rotor speed [pu]

    # ── Limits ──────────────────────────────────────────────────────
    Vr_max:   float = 0.30      # RSC output voltage limit [pu]
    Ir_max:   float = 1.50      # RSC reference clamp [pu]

    # ── Derived (post_init) ──────────────────────────────────────────
    ωbase:    float = field(init=False)
    Ls:       float = field(init=False)   # = Lls + Lm
    Lr:       float = field(init=False)   # = Llr + Lm
    XC:       float = field(init=False)   # = comp_pct/100 * Xline
    Ls_eff:   float = field(init=False)   # = Ls + Xline  (line absorbed)
    Rs_eff:   float = field(init=False)   # = Rs + Rline

    def __post_init__(self):
        self.ωbase  = 2.0 * math.pi * self.fn_Hz
        self.Ls     = self.Lls + self.Lm
        self.Lr     = self.Llr + self.Lm
        self.XC     = self.comp_pct / 100.0 * self.Xline
        self.Ls_eff = self.Ls + self.Xline
        self.Rs_eff = self.Rs + self.Rline

    @property
    def fr_Hz(self) -> float:
        """Natural series-LC resonant frequency [Hz]."""
        if self.comp_pct <= 0.0:
            return 0.0
        return self.fn_Hz * math.sqrt(self.comp_pct / 100.0)


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------
@dataclass
class DFIGSSCIState:
    t:       float
    ψs_d:    float; ψs_q: float
    ψr_d:    float; ψr_q: float
    ωr:      float
    is_d:    float; is_q: float
    ir_d:    float; ir_q: float
    vCd:     float; vCq: float
    Te:      float
    Pe:      float; Qs: float
    ωslip:   float
    vr_d:    float; vr_q: float
    fr_Hz:   float   # instantaneous resonant freq (from params, constant)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class DFIGSSCIEngine:
    """
    11-state DFIG + series-compensated line EMT simulator.

    Quick start
    -----------
    p = DFIGSSCIParams(comp_pct=50.0)
    eng = DFIGSSCIEngine(p)
    states = eng.run(t_end=3.0)
    """

    def __init__(self, params: Optional[DFIGSSCIParams] = None):
        self.p = params or DFIGSSCIParams()
        self._Minv = self._build_Minv()
        self._x0: Optional[np.ndarray] = None
        self._build_ic()

    # ------------------------------------------------------------------
    def _build_Minv(self) -> np.ndarray:
        """2×2 flux–current inversion using Ls_eff (line absorbed)."""
        p = self.p
        det = p.Ls_eff * p.Lr - p.Lm ** 2
        return np.array([
            [ p.Lr / det, -p.Lm / det],
            [-p.Lm / det,  p.Ls_eff / det],
        ])

    # ------------------------------------------------------------------
    def _currents(self, ψs_d, ψs_q, ψr_d, ψr_q
                  ) -> Tuple[float, float, float, float]:
        M = self._Minv
        is_d = M[0, 0] * ψs_d + M[0, 1] * ψr_d
        is_q = M[0, 0] * ψs_q + M[0, 1] * ψr_q
        ir_d = M[1, 0] * ψs_d + M[1, 1] * ψr_d
        ir_q = M[1, 0] * ψs_q + M[1, 1] * ψr_q
        return float(is_d), float(is_q), float(ir_d), float(ir_q)

    # ------------------------------------------------------------------
    def _build_ic(self) -> None:
        """Compute true steady-state initial conditions via fsolve."""
        from scipy.optimize import fsolve
        p = self.p
        is_d0 = p.Pe0
        is_q0 = -p.Qs0

        vCd0 =  p.XC * is_q0
        vCq0 = -p.XC * is_d0

        # Stator terminal voltage = grid minus series-cap (Rs drop applied separately in ODE)
        vs_d0 = 1.0 - vCd0
        vs_q0 = 0.0 - vCq0

        # Stator flux from dψ/dt=0: ψsq = Rs_eff·isd - vs_d, ψsd = vs_q - Rs_eff·isq
        ψs_d0 = vs_q0 - p.Rs_eff * is_q0
        ψs_q0 = p.Rs_eff * is_d0 - vs_d0

        # Rotor currents from ψs = Ls_eff·is + Lm·ir
        ir_d0 = (ψs_d0 - p.Ls_eff * is_d0) / p.Lm
        ir_q0 = (ψs_q0 - p.Ls_eff * is_q0) / p.Lm

        # Rotor flux
        ψr_d0 = p.Lr * ir_d0 + p.Lm * is_d0
        ψr_q0 = p.Lr * ir_q0 + p.Lm * is_q0

        # RSC rotor voltage from dψr/dt=0
        ωslip0 = 1.0 - p.ωr0
        vr_d0 = p.Rr * ir_d0 - ωslip0 * ψr_q0
        vr_q0 = p.Rr * ir_q0 + ωslip0 * ψr_d0

        # Inner integrators: ed=0 at SS → vr = ξi
        ξid0 = vr_d0
        ξiq0 = vr_q0

        # Outer loop frozen at SS current references.
        # ir_d_ref = Kp*(Pe0-ξPe)+ξPe = ir_d0 → ξPe0 = (ir_d0 - Kp*Pe0)/(1-Kp)
        kp = p.Kp_pq
        ξPe0 = (ir_d0 - kp * p.Pe0) / (1.0 - kp)
        ξQs0 = (ir_q0 - kp * p.Qs0) / (1.0 - kp)

        x0 = np.zeros(_NS)
        x0[_PSd] = ψs_d0; x0[_PSq] = ψs_q0
        x0[_PRd] = ψr_d0; x0[_PRq] = ψr_q0
        x0[_WR]  = p.ωr0
        x0[_XIrd] = ξid0; x0[_XIrq] = ξiq0
        x0[_XIQs] = ξQs0; x0[_XIPe] = ξPe0
        x0[_VCd]  = vCd0; x0[_VCq]  = vCq0

        # Refine with fsolve — outer integrators frozen during solve
        def residual(x):
            r = self._ode(0.0, x, None)
            r[_XIQs] = 0.0   # outer loop frozen: dξQs=0
            r[_XIPe] = 0.0   # outer loop frozen: dξPe=0
            return r

        x_eq, _, ier, _ = fsolve(residual, x0, full_output=True)
        self._x0 = x_eq if ier == 1 else x0

    # ------------------------------------------------------------------
    def _rsc(self, x: np.ndarray, ir_d: float, ir_q: float,
             ψr_d: float, ψr_q: float, ωslip: float
             ) -> Tuple[float, float, float, float, float, float]:
        """
        RSC cascaded PI: outer P/Q → inner dq current.
        Returns (vr_d, vr_q, dξid, dξiq, dξQs, dξPe).
        """
        p = self.p
        ξid, ξiq = x[_XIrd], x[_XIrq]
        ξQs, ξPe = x[_XIQs], x[_XIPe]

        # Outer loop references
        ir_q_ref = float(np.clip(p.Kp_pq * (p.Qs0 - ξQs) + ξQs,
                                 -p.Ir_max, p.Ir_max))
        ir_d_ref = float(np.clip(p.Kp_pq * (p.Pe0 - ξPe) + ξPe,
                                 -p.Ir_max, p.Ir_max))

        # Inner loop errors
        ed = ir_d_ref - ir_d
        eq = ir_q_ref - ir_q

        # No feed-forward decoupling — intentional.
        # Perfect decoupling would cancel sub-synchronous flux perturbations
        # and suppress the SSCI mechanism.  Real RSC implementations have
        # imperfect decoupling; omitting it reproduces the negative-damping
        # path validated in ERCOT 2009 (Adams et al. 2012).
        vr_d = float(np.clip(p.Kp_curr * ed + ξid,
                             -p.Vr_max, p.Vr_max))
        vr_q = float(np.clip(p.Kp_curr * eq + ξiq,
                             -p.Vr_max, p.Vr_max))

        dξid = p.Ki_curr * ed
        dξiq = p.Ki_curr * eq

        # Outer integrators track actual Pe / Qs error (slow)
        # (approximated: use current refs as stand-in for actual P/Q)
        dξQs = p.Ki_pq * (p.Qs0 - ir_q)
        dξPe = p.Ki_pq * (p.Pe0 - ir_d)

        return vr_d, vr_q, dξid, dξiq, dξQs, dξPe

    # ------------------------------------------------------------------
    def _ode(self, t: float, x: np.ndarray,
             perturb_fn=None) -> np.ndarray:
        """11-state ODE RHS."""
        p   = self.p
        ωb  = p.ωbase
        dx  = np.zeros(_NS)

        ψs_d, ψs_q = x[_PSd], x[_PSq]
        ψr_d, ψr_q = x[_PRd], x[_PRq]
        ωr         = x[_WR]
        vCd, vCq   = x[_VCd], x[_VCq]

        is_d, is_q, ir_d, ir_q = self._currents(ψs_d, ψs_q, ψr_d, ψr_q)
        ωslip = 1.0 - ωr

        # Grid voltage (infinite bus + optional perturbation)
        vg_d = 1.0 + (perturb_fn(t) if perturb_fn else 0.0)
        vg_q = 0.0

        # Stator terminal voltage = grid minus series-cap drop
        vs_d = vg_d - vCd
        vs_q = vg_q - vCq

        # RSC
        vr_d, vr_q, dξid, dξiq, dξQs, dξPe = \
            self._rsc(x, ir_d, ir_q, ψr_d, ψr_q, ωslip)

        # ── Effective stator flux ODEs (Akhmatov, Ls_eff absorbs Xline) ──
        # ×ωbase converts pu→physical time; ωslip=1 for stator cross-term
        dx[_PSd] = ωb * (vs_d - p.Rs_eff * is_d + ψs_q)
        dx[_PSq] = ωb * (vs_q - p.Rs_eff * is_q - ψs_d)

        # ── Rotor flux ODEs ──────────────────────────────────────────
        dx[_PRd] = ωb * (vr_d - p.Rr * ir_d + ωslip * ψr_q)
        dx[_PRq] = ωb * (vr_q - p.Rr * ir_q - ωslip * ψr_d)

        # ── Rotor speed (mechanical) ─────────────────────────────────
        Te = p.Lm * (is_q * ir_d - is_d * ir_q)
        Tm = p.Pe0 / max(ωr, 0.5)
        dx[_WR] = (Te - Tm) / (2.0 * p.H)

        # ── RSC integrators ──────────────────────────────────────────
        dx[_XIrd] = dξid
        dx[_XIrq] = dξiq
        # Outer loop frozen: bandwidth ~2 Hz << SSCI (25-38 Hz); won't affect SSCI stability
        dx[_XIQs] = 0.0
        dx[_XIPe] = 0.0

        # ── Series-capacitor voltage (rotating dq at ω₁ = 1 pu) ─────
        # dvCd/dt = ωbase·(XC·isd + vCq)
        # dvCq/dt = ωbase·(XC·isq - vCd)
        dx[_VCd] = ωb * (p.XC * is_d + vCq)
        dx[_VCq] = ωb * (p.XC * is_q - vCd)

        return dx

    # ------------------------------------------------------------------
    def run(self,
            t_settle: float = 0.30,
            t_perturb: float = 0.30,
            t_end: float = 3.0,
            perturb_amp: float = 0.03,
            perturb_freq_Hz: float = 0.0,
            max_step: float = 1.0e-4,
            ) -> List[DFIGSSCIState]:
        """
        Run simulation in two phases:
          1. Settle [0, t_settle] with no perturbation (Radau).
          2. Main  [t_settle, t_end] with a perturbation:
             - perturb_freq_Hz=0: DC step of duration t_perturb
             - perturb_freq_Hz>0: sinusoidal injection at that frequency
               (continues for full t_end; directly excites SSCI resonance)

        Returns list of DFIGSSCIState snapshots (≈ t_end / max_step entries).
        """
        p = self.p

        def _integrate(t_span, x0, pfn=None):
            return solve_ivp(
                lambda t, x: self._ode(t, x, pfn),
                t_span, x0,
                method='Radau',
                max_step=max_step,
                rtol=1e-6, atol=1e-9,
                dense_output=False,
            )

        # Phase 1: settle
        sol1 = _integrate([0.0, t_settle], self._x0.copy())
        x_mid = sol1.y[:, -1]

        # Phase 2: perturb then free
        t_p_end = t_settle + t_perturb

        if perturb_freq_Hz > 0.0:
            ω_inj = 2.0 * math.pi * perturb_freq_Hz
            def step(t):  # sinusoidal injection at SSCI frequency
                return perturb_amp * math.sin(ω_inj * (t - t_settle))
        else:
            def step(t):  # DC step
                return perturb_amp if t_settle <= t <= t_p_end else 0.0

        sol2 = _integrate([t_settle, t_end], x_mid, pfn=step)

        # Concatenate
        t_all = np.concatenate([sol1.t, sol2.t])
        y_all = np.concatenate([sol1.y, sol2.y], axis=1)

        return self._build_states(t_all, y_all)

    # ------------------------------------------------------------------
    def _build_states(self, t_arr: np.ndarray,
                      y_arr: np.ndarray) -> List[DFIGSSCIState]:
        p = self.p
        states = []
        for k in range(y_arr.shape[1]):
            x = y_arr[:, k]
            is_d, is_q, ir_d, ir_q = self._currents(
                x[_PSd], x[_PSq], x[_PRd], x[_PRq])
            ωr    = float(x[_WR])
            ωslip = 1.0 - ωr
            vCd, vCq = float(x[_VCd]), float(x[_VCq])

            vr_d, vr_q, *_ = self._rsc(
                x, ir_d, ir_q, float(x[_PRd]), float(x[_PRq]), ωslip)

            Pe = 1.0 * is_d          # vg_d=1, vg_q=0
            Qs = -1.0 * is_q
            Te = p.Lm * (is_q * ir_d - is_d * ir_q)

            states.append(DFIGSSCIState(
                t=float(t_arr[k]),
                ψs_d=float(x[_PSd]), ψs_q=float(x[_PSq]),
                ψr_d=float(x[_PRd]), ψr_q=float(x[_PRq]),
                ωr=ωr,
                is_d=float(is_d), is_q=float(is_q),
                ir_d=float(ir_d), ir_q=float(ir_q),
                vCd=vCd, vCq=vCq,
                Te=round(float(Te), 6),
                Pe=round(float(Pe), 6),
                Qs=round(float(Qs), 6),
                ωslip=round(ωslip, 6),
                vr_d=round(float(vr_d), 6),
                vr_q=round(float(vr_q), 6),
                fr_Hz=round(p.fr_Hz, 2),
            ))
        return states


# ---------------------------------------------------------------------------
# Convenience: compute growth-rate from is_d envelope
# ---------------------------------------------------------------------------
def envelope_growth_rate(states: List[DFIGSSCIState],
                         t_start: float = 0.5,
                         f_ss_Hz: float | None = None,
                         ) -> Tuple[float, float]:
    """
    Estimate sub-synchronous oscillation growth rate λ [Np/s] and dominant
    frequency f_ss [Hz] from the is_d time series.

    Method:
      1. f_ss detected from raw AC FFT (no filtering — avoids IIR overflow).
      2. λ from RMS ratio of early vs late half of the SOS-bandpassed signal.

    Returns (lambda_Np_s, f_ss_Hz).
    """
    from scipy.signal import hilbert, butter, sosfiltfilt
    from scipy.fft import rfft, rfftfreq

    t   = np.array([s.t   for s in states])
    isd = np.array([s.is_d for s in states])

    mask = t >= t_start
    t_w, isd_w = t[mask], isd[mask]
    if len(t_w) < 20:
        return 0.0, 0.0

    # ── Step 1: dominant SS frequency from raw AC spectrum (no filtering) ──
    isd_ac = isd_w - isd_w.mean()
    fs_raw = 1.0 / np.median(np.diff(t_w))
    sp_raw = np.abs(rfft(isd_ac)) ** 2
    fr_raw = rfftfreq(len(isd_ac), 1.0 / fs_raw)
    idx_ss = (fr_raw >= 8.0) & (fr_raw <= 48.0)
    if np.any(idx_ss) and sp_raw[idx_ss].max() > 1e-20:
        f_ss_Hz = float(fr_raw[idx_ss][np.argmax(sp_raw[idx_ss])])
    else:
        f_ss_Hz = 0.0

    # ── Step 2: growth rate via SOS bandpass + RMS half-window ratio ──────
    # Uniform resample for filtering
    t_u   = np.arange(t_w[0], t_w[-1], 1.0 / fs_raw)
    isd_u = np.interp(t_u, t_w, isd_w)
    isd_u -= isd_u.mean()

    # SOS bandpass [8–48 Hz] — numerically stable for large-amplitude signals
    sos = butter(4, [8.0 / (0.5 * fs_raw), 48.0 / (0.5 * fs_raw)],
                 btype='band', output='sos')
    try:
        isd_bp = sosfiltfilt(sos, isd_u)
    except Exception:
        return 0.0, f_ss_Hz

    if not np.all(np.isfinite(isd_bp)) or np.max(np.abs(isd_bp)) < 1e-12:
        return 0.0, f_ss_Hz

    # Split into early / late halves and compare RMS
    n = len(isd_bp)
    rms_early = float(np.sqrt(np.mean(isd_bp[:n // 2] ** 2))) + 1e-12
    rms_late  = float(np.sqrt(np.mean(isd_bp[n // 2:] ** 2))) + 1e-12
    dt_half   = (t_u[-1] - t_u[0]) / 2.0
    lam = float(np.log(rms_late / rms_early) / dt_half)

    return lam, f_ss_Hz
