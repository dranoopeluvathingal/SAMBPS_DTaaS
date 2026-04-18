#!/usr/bin/env python3
"""
TR-90 PV Full EMT Runner
=========================
Six canonical scenarios, 7 publication figures.

Scenarios
---------
  S1  Normal MPPT + 50% voltage dip (150 ms) — PLL tracking, LVRT
  S2  Deep 20% retained dip — LVRT reactive injection priority
  S3  Irradiance step  1.0 → 0.5 pu (cloud shadow) — DC voltage sag
  S4  Irradiance ramp  1.0 → 0.3 pu (slow cloud)
  S5  PLL bandwidth comparison — narrow (Kp=20) vs wide (Kp=100) under dip
  S6  Q droop control  Qe_ref = 0.30 pu + 50% dip

Usage
-----
  python tr90_runner.py
  python tr90_runner.py --figures-only
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_FIGS = _ROOT / "reports" / "figures" / "TR90"
_RES  = _ROOT / "results"
_FIGS.mkdir(parents=True, exist_ok=True)
_RES.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pv_emt import PVEmtEngine, PVParams, PVState


# ---------------------------------------------------------------------------
# Scenario functions
# ---------------------------------------------------------------------------

def run_s1() -> List[PVState]:
    """S1 — Normal operation + 50% retained dip, 150 ms."""
    eng = PVEmtEngine()
    eng.set_operating_point(Pe0=0.9, Qe0=0.0)
    eng.apply_voltage_dip(depth=0.50, t_start=0.10, t_end=0.25)
    return eng.run(t_end=0.50, dt=100e-6)


def run_s2() -> List[PVState]:
    """S2 — Deep 20% retained dip — LVRT reactive priority."""
    eng = PVEmtEngine()
    eng.set_operating_point(Pe0=0.9, Qe0=0.0)
    eng.apply_voltage_dip(depth=0.20, t_start=0.10, t_end=0.30)
    return eng.run(t_end=0.60, dt=100e-6)


def run_s3() -> List[PVState]:
    """S3 — Irradiance step 1.0 → 0.5 pu (cloud shadow)."""
    eng = PVEmtEngine()
    eng.set_operating_point(Pe0=0.9, Qe0=0.0)
    eng.set_irradiance_step(G_new=0.5, t_step=0.15)
    return eng.run(t_end=0.60, dt=100e-6)


def run_s4() -> List[PVState]:
    """S4 — Irradiance step 1.0 → 0.3 pu (deep cloud)."""
    eng = PVEmtEngine()
    eng.set_operating_point(Pe0=0.9, Qe0=0.0)
    eng.set_irradiance_step(G_new=0.3, t_step=0.15)
    return eng.run(t_end=0.70, dt=100e-6)


def run_s5_narrow() -> List[PVState]:
    """S5a — Narrow PLL bandwidth (Kp_pll=20) under 50% dip."""
    p = PVParams()
    p.Kp_pll = 20.0
    p.Ki_pll = 200.0
    eng = PVEmtEngine(params=p)
    eng.set_operating_point(Pe0=0.9, Qe0=0.0)
    eng.apply_voltage_dip(depth=0.50, t_start=0.10, t_end=0.25)
    return eng.run(t_end=0.50, dt=100e-6)


def run_s5_wide() -> List[PVState]:
    """S5b — Wide PLL bandwidth (Kp_pll=100) under 50% dip."""
    p = PVParams()
    p.Kp_pll = 100.0
    p.Ki_pll = 5000.0
    eng = PVEmtEngine(params=p)
    eng.set_operating_point(Pe0=0.9, Qe0=0.0)
    eng.apply_voltage_dip(depth=0.50, t_start=0.10, t_end=0.25)
    return eng.run(t_end=0.50, dt=100e-6)


def run_s6() -> List[PVState]:
    """S6 — Q droop 0.3 pu + 50% dip → LVRT override."""
    eng = PVEmtEngine()
    eng.set_operating_point(Pe0=0.9, Qe0=0.30)
    eng.apply_voltage_dip(depth=0.50, t_start=0.10, t_end=0.25)
    return eng.run(t_end=0.50, dt=100e-6)


SCENARIOS = {
    'S1 — 50% dip, 150 ms':      run_s1,
    'S2 — 20% dip (deep LVRT)':  run_s2,
    'S3 — irradiance 1.0→0.5':   run_s3,
    'S4 — irradiance 1.0→0.3':   run_s4,
    'S5a — PLL narrow (Kp=20)':  run_s5_narrow,
    'S5b — PLL wide  (Kp=100)':  run_s5_wide,
    'S6 — Q droop + dip':         run_s6,
}


# ---------------------------------------------------------------------------
# Array helpers
# ---------------------------------------------------------------------------
def _a(states, attr): return np.array([getattr(s, attr) for s in states])
def _t(s):   return _a(s, 't')
def _Pe(s):  return _a(s, 'Pe')
def _Qe(s):  return _a(s, 'Qe')
def _id(s):  return _a(s, 'id')
def _iq(s):  return _a(s, 'iq')
def _vdc(s): return _a(s, 'vdc')
def _vq(s):  return _a(s, 'vq_grid')
def _wr(s):  return _a(s, 'ω_pll')
def _ppv(s): return _a(s, 'Ppv')
def _idref(s): return _a(s, 'id_ref')
def _iqref(s): return _a(s, 'iq_ref')
def _lvrt(s): return _a(s, 'lvrt_active').astype(float)


def _save(fig, name):
    import matplotlib.pyplot as plt
    for ext in ('pdf', 'png'):
        fig.savefig(_FIGS / f'{name}.{ext}', bbox_inches='tight', dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 1 — Pe and Qe for S1, S2, S6 (voltage-dip scenarios)
# ---------------------------------------------------------------------------
def fig1_pq_dip(s1, s2, s6):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(13, 6), sharey='row')
    for col, (states, label) in enumerate([
            (s1, 'S1 — 50% retained'),
            (s2, 'S2 — 20% retained'),
            (s6, 'S6 — Q=0.3 + dip'),
    ]):
        t = _t(states)
        axes[0, col].plot(t, _Pe(states), 'C0', lw=1.3, label='$P_e$')
        axes[0, col].set_title(label, fontsize=9.5)
        axes[0, col].set_ylabel('$P_e$ [pu]')
        axes[0, col].grid(linestyle=':', alpha=0.4)
        axes[0, col].set_ylim(-0.2, 1.2)

        axes[1, col].plot(t, _Qe(states), 'C1', lw=1.3, label='$Q_e$')
        axes[1, col].set_ylabel('$Q_e$ [pu]')
        axes[1, col].set_xlabel('t [s]')
        axes[1, col].grid(linestyle=':', alpha=0.4)
        axes[1, col].set_ylim(-0.5, 1.2)

        # Shade LVRT period
        lvrt = _lvrt(states)
        for ax in axes[:, col]:
            ax.fill_between(t, ax.get_ylim()[0], ax.get_ylim()[1],
                            where=lvrt > 0.5, alpha=0.10, color='C3',
                            label='LVRT active')
    fig.suptitle('PV Inverter EMT — Active/Reactive Power during Voltage Dips\n'
                 'Red shading: LVRT active (|Vt| < 0.90 pu)', y=1.01)
    fig.tight_layout()
    _save(fig, 'fig1_pq_dip')


# ---------------------------------------------------------------------------
# Figure 2 — dq currents: id_ref, id, iq_ref, iq for S1 and S2
# ---------------------------------------------------------------------------
def fig2_dq_currents(s1, s2):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(11, 6), sharex=False)
    for col, (states, title) in enumerate([
            (s1, 'S1 — 50% dip'),
            (s2, 'S2 — 20% dip (LVRT)'),
    ]):
        t = _t(states)
        ax_d, ax_q = axes[0, col], axes[1, col]

        ax_d.plot(t, _idref(states), 'C0--', lw=1.0, label=r'$i_{d,\mathrm{ref}}$')
        ax_d.plot(t, _id(states),    'C0',   lw=1.5, label='$i_d$')
        ax_d.set_title(title, fontsize=10)
        ax_d.set_ylabel('$i_d$ [pu]')
        ax_d.legend(fontsize=8)
        ax_d.grid(linestyle=':', alpha=0.4)

        ax_q.plot(t, _iqref(states), 'C1--', lw=1.0, label=r'$i_{q,\mathrm{ref}}$')
        ax_q.plot(t, _iq(states),    'C1',   lw=1.5, label='$i_q$')
        ax_q.set_ylabel('$i_q$ [pu]')
        ax_q.set_xlabel('t [s]')
        ax_q.legend(fontsize=8)
        ax_q.grid(linestyle=':', alpha=0.4)

        lvrt = _lvrt(states)
        for ax in (ax_d, ax_q):
            ax.fill_between(t, -1.5, 1.5, where=lvrt > 0.5,
                            alpha=0.10, color='C3')
            ax.set_ylim(-1.3, 1.5)

    fig.suptitle('PV Inverter EMT — dq Current Tracking\n'
                 'Dashed: reference; solid: actual. LVRT: reactive priority.')
    fig.tight_layout()
    _save(fig, 'fig2_dq_currents')


# ---------------------------------------------------------------------------
# Figure 3 — DC-link voltage and PV power (S3 and S4 irradiance steps)
# ---------------------------------------------------------------------------
def fig3_dc_irradiance(s3, s4):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 2, figsize=(11, 8), sharex=False)
    for col, (states, title) in enumerate([
            (s3, 'S3 — G: 1.0 → 0.5 pu'),
            (s4, 'S4 — G: 1.0 → 0.3 pu'),
    ]):
        t = _t(states)
        axes[0, col].plot(t, _vdc(states),  'C2', lw=1.3)
        axes[0, col].axhline(1.07, color='k', linestyle='--', lw=0.8,
                              label=r'$V_{dc,\mathrm{nom}}$')
        axes[0, col].set_title(title, fontsize=10)
        axes[0, col].set_ylabel('$V_{dc}$ [pu]')
        axes[0, col].legend(fontsize=8)
        axes[0, col].grid(linestyle=':', alpha=0.4)

        axes[1, col].plot(t, _ppv(states), 'C3', lw=1.3, label='$P_{pv}$')
        axes[1, col].plot(t, _Pe(states),  'C0', lw=1.0, label='$P_e$', alpha=0.7)
        axes[1, col].set_ylabel('Power [pu]')
        axes[1, col].legend(fontsize=8)
        axes[1, col].grid(linestyle=':', alpha=0.4)

        axes[2, col].plot(t, _id(states), 'C0', lw=1.2, label='$i_d$')
        axes[2, col].plot(t, _iq(states), 'C1', lw=1.2, label='$i_q$')
        axes[2, col].set_ylabel('Current [pu]')
        axes[2, col].set_xlabel('t [s]')
        axes[2, col].legend(fontsize=8)
        axes[2, col].grid(linestyle=':', alpha=0.4)

    fig.suptitle('PV Inverter EMT — DC-link and Power response to Irradiance Steps')
    fig.tight_layout()
    _save(fig, 'fig3_dc_irradiance')


# ---------------------------------------------------------------------------
# Figure 4 — PLL frequency and vq_grid for S1 vs narrow vs wide PLL
# ---------------------------------------------------------------------------
def fig4_pll_comparison(s1, s_narrow, s_wide):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    for states, label, color in [
            (s1,       'Nominal (Kp=50)',  'C0'),
            (s_narrow, 'Narrow  (Kp=20)', 'C2'),
            (s_wide,   'Wide    (Kp=100)', 'C3'),
    ]:
        t = _t(states)
        axes[0].plot(t, _wr(states), color=color, lw=1.3, label=label)
        axes[1].plot(t, _vq(states), color=color, lw=1.3, label=label)

    axes[0].axhline(1.0, color='k', linestyle=':', lw=0.8)
    axes[0].set_ylabel('PLL freq $\\omega_{pll}$ [pu]')
    axes[0].legend(fontsize=8)
    axes[0].grid(linestyle=':', alpha=0.4)
    axes[0].set_ylim(0.85, 1.15)

    axes[1].axhline(0.0, color='k', linestyle=':', lw=0.8)
    axes[1].set_ylabel(r'$v_{q,\mathrm{grid}}$ (PLL error) [pu]')
    axes[1].set_xlabel('t [s]')
    axes[1].legend(fontsize=8)
    axes[1].grid(linestyle=':', alpha=0.4)

    fig.suptitle('PV Inverter EMT — PLL Bandwidth Comparison under 50% Dip\n'
                 'S1 (nominal), narrow PLL (Kp=20), wide PLL (Kp=100)')
    fig.tight_layout()
    _save(fig, 'fig4_pll_bandwidth')


# ---------------------------------------------------------------------------
# Figure 5 — LVRT: reactive injection vs terminal voltage (S2)
# ---------------------------------------------------------------------------
def fig5_lvrt(s2):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
    t   = _t(s2)
    vd  = np.array([s.vd_grid for s in s2])
    vq  = _vq(s2)
    Vt  = np.hypot(vd, vq)

    axes[0].plot(t, Vt, 'C3', lw=1.4)
    axes[0].axhline(0.9, color='k', linestyle='--', lw=0.9,
                    label='LVRT threshold (0.9 pu)')
    axes[0].set_ylabel('|$V_t$| [pu]')
    axes[0].legend(fontsize=8)
    axes[0].grid(linestyle=':', alpha=0.4)

    axes[1].plot(t, _iqref(s2), 'C1--', lw=1.0, label=r'$i_{q,\mathrm{ref}}$')
    axes[1].plot(t, _iq(s2),    'C1',   lw=1.5, label='$i_q$ (actual)')
    axes[1].set_ylabel('$i_q$ [pu]')
    axes[1].legend(fontsize=8)
    axes[1].grid(linestyle=':', alpha=0.4)

    axes[2].plot(t, _Pe(s2), 'C0', lw=1.3, label='$P_e$')
    axes[2].plot(t, _Qe(s2), 'C1', lw=1.3, label='$Q_e$')
    axes[2].set_ylabel('Power [pu]')
    axes[2].set_xlabel('t [s]')
    axes[2].legend(fontsize=8)
    axes[2].grid(linestyle=':', alpha=0.4)

    lvrt = _lvrt(s2)
    for ax in axes:
        ax.fill_between(t, ax.get_ylim()[0], ax.get_ylim()[1],
                        where=lvrt > 0.5, alpha=0.10, color='C3')

    fig.suptitle('PV Inverter EMT — LVRT Reactive Current Injection\n'
                 'S2: 20% retained dip; reactive priority per IEC 61400-21')
    fig.tight_layout()
    _save(fig, 'fig5_lvrt')


# ---------------------------------------------------------------------------
# Figure 6 — Phase portrait: Pe vs ω_pll (all dip scenarios)
# ---------------------------------------------------------------------------
def fig6_phase(s1, s2, s6):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 5))
    for states, label, color in [
            (s1, 'S1 — 50% dip',  'C0'),
            (s2, 'S2 — 20% dip',  'C3'),
            (s6, 'S6 — Q droop+dip', 'C2'),
    ]:
        pe = _Pe(states)
        wr = _wr(states)
        ax.plot(wr, pe, color=color, lw=1.1, label=label, alpha=0.85)
        ax.scatter([wr[0]], [pe[0]],  color=color, marker='o', s=40, zorder=5)
        ax.scatter([wr[-1]], [pe[-1]], color=color, marker='s', s=40, zorder=5)
    ax.set_xlabel('PLL freq $\\omega_{pll}$ [pu]')
    ax.set_ylabel('$P_e$ [pu]')
    ax.set_title('PV Inverter EMT — Phase Portrait $P_e$ vs $\\omega_{pll}$\n'
                 'Circle=start, square=end')
    ax.legend(fontsize=9)
    ax.grid(linestyle=':', alpha=0.4)
    _save(fig, 'fig6_phase_portrait')


# ---------------------------------------------------------------------------
# Figure 7 — Converter voltage commands (S1 and S2)
# ---------------------------------------------------------------------------
def fig7_vconv(s1, s2):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(11, 6), sharex=False)
    for col, (states, title) in enumerate([
            (s1, 'S1 — 50% dip'),
            (s2, 'S2 — 20% dip'),
    ]):
        t = _t(states)
        vd = np.array([s.vd_conv for s in states])
        vq = np.array([s.vq_conv for s in states])
        V  = np.hypot(vd, vq)

        axes[0, col].plot(t, vd, 'C0', lw=1.2, label=r'$v_{d,\mathrm{conv}}$')
        axes[0, col].plot(t, vq, 'C1', lw=1.2, label=r'$v_{q,\mathrm{conv}}$')
        axes[0, col].axhline( 1.15, color='k', linestyle='--', lw=0.8)
        axes[0, col].axhline(-1.15, color='k', linestyle='--', lw=0.8)
        axes[0, col].set_title(title, fontsize=10)
        axes[0, col].set_ylabel('Conv. voltage [pu]')
        axes[0, col].legend(fontsize=8)
        axes[0, col].grid(linestyle=':', alpha=0.4)
        axes[0, col].set_ylim(-1.4, 1.4)

        axes[1, col].plot(t, V, 'C4', lw=1.4, label=r'$|v_\mathrm{conv}|$')
        axes[1, col].axhline(1.15, color='k', linestyle='--', lw=0.8,
                              label='SVPWM limit')
        axes[1, col].set_ylabel(r'|$v_\mathrm{conv}$| [pu]')
        axes[1, col].set_xlabel('t [s]')
        axes[1, col].legend(fontsize=8)
        axes[1, col].grid(linestyle=':', alpha=0.4)
        axes[1, col].set_ylim(0, 1.4)

    fig.suptitle('PV Inverter EMT — VSC Converter Voltage Commands (SVPWM)\n'
                 'Dashed: ±1.15 pu SVPWM modulation limit')
    fig.tight_layout()
    _save(fig, 'fig7_vconv')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all():
    all_states = []
    t0 = time.time()
    print(f"\n{'='*57}")
    print('  TR-90  PV Full EMT — 7 Scenarios')
    print(f"{'='*57}")
    for name, fn in SCENARIOS.items():
        t1 = time.time()
        states = fn()
        elapsed = time.time() - t1
        Pe_min = min(s.Pe for s in states)
        iq_max = max(abs(s.iq) for s in states)
        lvrt   = any(s.lvrt_active for s in states)
        print(f'  {name[:36]:36s}  Pe_min={Pe_min:+.3f}  '
              f'|iq|_max={iq_max:.3f}  LVRT={"Y" if lvrt else "N"}  '
              f'({elapsed:.1f}s)')
        all_states.append(states)
    print(f'\n  Wall time: {time.time()-t0:.1f}s')
    return all_states


def save_npz(all_states):
    tags = ['S1','S2','S3','S4','S5a','S5b','S6']
    for tag, states in zip(tags, all_states):
        np.savez_compressed(
            _RES / f'tr90_{tag.lower()}.npz',
            t   = np.array([s.t   for s in states], np.float32),
            Pe  = np.array([s.Pe  for s in states], np.float32),
            Qe  = np.array([s.Qe  for s in states], np.float32),
            id  = np.array([s.id  for s in states], np.float32),
            iq  = np.array([s.iq  for s in states], np.float32),
            vdc = np.array([s.vdc for s in states], np.float32),
            wpll= np.array([s.ω_pll for s in states], np.float32),
            Ppv = np.array([s.Ppv for s in states], np.float32),
            lvrt= np.array([s.lvrt_active for s in states], np.bool_),
        )
    print(f'  Saved {len(tags)} .npz files → {_RES}/')


def generate_figures(all_states):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.family':   'serif',
        'font.size':     9,
        'axes.labelsize':10,
        'axes.titlesize':11,
        'figure.dpi':    150,
        'savefig.dpi':   300,
    })
    s1, s2, s3, s4, s5a, s5b, s6 = all_states
    fig1_pq_dip(s1, s2, s6)
    fig2_dq_currents(s1, s2)
    fig3_dc_irradiance(s3, s4)
    fig4_pll_comparison(s1, s5a, s5b)
    fig5_lvrt(s2)
    fig6_phase(s1, s2, s6)
    fig7_vconv(s1, s2)
    print(f'  7 figures saved → {_FIGS}/')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures-only', action='store_true')
    args = parser.parse_args()

    if args.figures_only:
        tags = ['S1','S2','S3','S4','S5a','S5b','S6']
        all_states = []
        for tag in tags:
            d = np.load(_RES / f'tr90_{tag.lower()}.npz')
            from pv_emt import PVState
            states = [
                PVState(
                    t=float(d['t'][i]), id=float(d['id'][i]),
                    iq=float(d['iq'][i]), vdc=float(d['vdc'][i]),
                    θ_pll=0.0, ω_pll=float(d['wpll'][i]),
                    vd_grid=1.0, vq_grid=0.0,
                    Pe=float(d['Pe'][i]), Qe=float(d['Qe'][i]),
                    Ppv=float(d['Ppv'][i]),
                    id_ref=0.0, iq_ref=0.0,
                    pll_locked=True,
                    lvrt_active=bool(d['lvrt'][i]),
                    vd_conv=0.0, vq_conv=0.0,
                )
                for i in range(len(d['t']))
            ]
            all_states.append(states)
        generate_figures(all_states)
    else:
        all_states = run_all()
        save_npz(all_states)
        generate_figures(all_states)
        print('TR-90 complete.')
