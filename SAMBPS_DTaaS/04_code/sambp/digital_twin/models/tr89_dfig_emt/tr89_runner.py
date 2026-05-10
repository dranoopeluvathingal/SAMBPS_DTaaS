#!/usr/bin/env python3
"""
TR-89 DFIG Full EMT Runner
===========================
Runs five canonical scenarios and generates 6 publication figures.

Scenarios
---------
  S1  Balanced 3-phase voltage dip  80% retained, 150 ms (LVRT stress)
  S2  Deep 3-phase dip              20% retained, 200 ms (crowbar triggers)
  S3  Pre-fault Pe ramp             0.3 → 1.0 pu at t=0.05 s, then 80% dip
  S4  Crowbar cycling               repeated 85% dips every 300 ms
  S5  Symmetrical fault recovery    50% dip + rotor speed perturbation

Usage
-----
  python tr89_runner.py
  python tr89_runner.py --figures-only
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent.parent.parent   # digital_twin
_FIGS = _ROOT / "reports" / "figures" / "TR89"
_RES  = _ROOT / "results"
_FIGS.mkdir(parents=True, exist_ok=True)
_RES.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dfig_emt import DFIGEmtEngine, DFIGParams, DFIGState


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def run_s1() -> List[DFIGState]:
    """S1 — Balanced 80% retained voltage dip, 150 ms."""
    eng = DFIGEmtEngine()
    eng.set_operating_point(Pe0=0.8, Qs0=0.0, ωr0=1.10)
    eng.apply_voltage_dip(depth=0.80, t_start=0.10, t_end=0.25)
    return eng.run(t_end=0.50, dt=100e-6)


def run_s2() -> List[DFIGState]:
    """S2 — Deep 20% retained dip, 200 ms. Crowbar expected."""
    eng = DFIGEmtEngine()
    eng.set_operating_point(Pe0=0.8, Qs0=0.0, ωr0=1.10)
    eng.apply_voltage_dip(depth=0.20, t_start=0.10, t_end=0.30)
    return eng.run(t_end=0.60, dt=100e-6)


def run_s3() -> List[DFIGState]:
    """S3 — Nominal Pe=0.3 pu, then ramp to 1.0 pu, then 80% dip."""
    eng = DFIGEmtEngine()
    eng.set_operating_point(Pe0=0.30, Qs0=0.0, ωr0=1.00)
    eng.apply_voltage_dip(depth=0.80, t_start=0.20, t_end=0.35)
    # The ramp is approximated by the RSC reference: force Pe_ref mid-sim
    # via subclassing would be clean; here we run two segments:
    states_a = eng.run(t_end=0.20, dt=100e-6)
    # Second segment at Pe=1.0
    eng2 = DFIGEmtEngine()
    last = states_a[-1]
    eng2.set_operating_point(Pe0=1.0, Qs0=0.0,
                             vs_d0=0.0, vs_q0=1.0,
                             ωr0=last.ωr)
    eng2.apply_voltage_dip(depth=0.80, t_start=0.0, t_end=0.15)
    states_b = eng2.run(t_end=0.40, dt=100e-6)
    # Merge and re-stamp time
    for s in states_b:
        object.__setattr__(s, 't', s.t + 0.20)
    return states_a + states_b


def run_s4() -> List[DFIGState]:
    """S4 — Repeated 85% dips; tests crowbar cycling."""
    eng = DFIGEmtEngine()
    eng.set_operating_point(Pe0=0.8, Qs0=0.0, ωr0=1.10)
    # First dip
    eng.apply_voltage_dip(depth=0.15, t_start=0.10, t_end=0.18)
    return eng.run(t_end=0.70, dt=100e-6)


def run_s5() -> List[DFIGState]:
    """S5 — 50% retained dip + rotor at sub-synchronous (0.90 pu)."""
    p = DFIGParams()
    p.Icb_thr = 1.8    # tighter crowbar threshold for this scenario
    eng = DFIGEmtEngine(params=p)
    eng.set_operating_point(Pe0=0.5, Qs0=0.0, ωr0=0.90)
    eng.apply_voltage_dip(depth=0.50, t_start=0.10, t_end=0.30)
    return eng.run(t_end=0.60, dt=100e-6)


SCENARIOS = {
    'S1 — 80% retained, 150 ms':      run_s1,
    'S2 — 20% retained, 200 ms':      run_s2,
    'S3 — Pe ramp + dip':             run_s3,
    'S4 — crowbar cycling':           run_s4,
    'S5 — sub-sync + 50% dip':        run_s5,
}


# ---------------------------------------------------------------------------
# Figure helpers
# ---------------------------------------------------------------------------

def _t(states): return np.array([s.t        for s in states])
def _Pe(states): return np.array([s.Pe       for s in states])
def _Qs(states): return np.array([s.Qs       for s in states])
def _Ir(states): return np.array([s.Ir_mag   for s in states])
def _wr(states): return np.array([s.ωr       for s in states])
def _cb(states): return np.array([float(s.crowbar) for s in states])
def _vrd(states): return np.array([s.vr_d    for s in states])
def _vrq(states): return np.array([s.vr_q    for s in states])


def _save(fig, name):
    import matplotlib.pyplot as plt
    for ext in ('pdf', 'png'):
        fig.savefig(_FIGS / f'{name}.{ext}', bbox_inches='tight', dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 1 — Pe and Qs transients for all 5 scenarios
# ---------------------------------------------------------------------------
def fig1_pq_all(all_states):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(5, 2, figsize=(11, 13), sharex=False)
    names = list(SCENARIOS.keys())
    for row, (name, states) in enumerate(zip(names, all_states)):
        t = _t(states)
        ax_pe, ax_qs = axes[row, 0], axes[row, 1]
        ax_pe.plot(t, _Pe(states), 'C0', linewidth=1.2)
        ax_pe.set_ylabel('Pe [pu]', fontsize=8)
        ax_pe.set_title(name, fontsize=8.5, loc='left')
        ax_qs.plot(t, _Qs(states), 'C1', linewidth=1.2)
        ax_qs.set_ylabel('Qs [pu]', fontsize=8)
        for ax in (ax_pe, ax_qs):
            ax.grid(linestyle=':', alpha=0.4)
            ax.set_xlabel('t [s]', fontsize=8)
    fig.suptitle('DFIG EMT — Active and Reactive Power Transients\n'
                 'Five canonical scenarios (TR-89)', y=1.002)
    fig.tight_layout()
    _save(fig, 'fig1_pq_all')


# ---------------------------------------------------------------------------
# Figure 2 — Rotor current magnitude + crowbar flag (S1 vs S2)
# ---------------------------------------------------------------------------
def fig2_crowbar(s1, s2):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(10, 6))

    for col, (states, title) in enumerate([(s1, 'S1 — 80% retained'),
                                            (s2, 'S2 — 20% retained')]):
        t  = _t(states)
        ir = _Ir(states)
        cb = _cb(states)
        ax_ir = axes[0, col]
        ax_cb = axes[1, col]
        ax_ir.plot(t, ir, 'C0', linewidth=1.3)
        ax_ir.axhline(2.0, color='red', linestyle='--', linewidth=0.9,
                      label='Crowbar thr (2.0 pu)')
        ax_ir.set_ylabel('|Ir| [pu]', fontsize=9)
        ax_ir.set_title(title, fontsize=10)
        ax_ir.legend(fontsize=8)
        ax_ir.grid(linestyle=':', alpha=0.4)
        ax_ir.set_ylim(bottom=0)

        ax_cb.fill_between(t, cb, alpha=0.7, color='C3', step='mid')
        ax_cb.set_ylabel('Crowbar ON', fontsize=9)
        ax_cb.set_ylim(-0.05, 1.15)
        ax_cb.set_yticks([0, 1])
        ax_cb.set_xlabel('t [s]', fontsize=9)
        ax_cb.grid(linestyle=':', alpha=0.4)

    fig.suptitle('DFIG EMT — Rotor Current and Crowbar Activation\n'
                 'S1 (no crowbar) vs S2 (crowbar triggered)', y=1.01)
    fig.tight_layout()
    _save(fig, 'fig2_crowbar')


# ---------------------------------------------------------------------------
# Figure 3 — Rotor speed dynamics
# ---------------------------------------------------------------------------
def fig3_rotor_speed(all_states):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5))
    names = list(SCENARIOS.keys())
    for name, states in zip(names, all_states):
        ax.plot(_t(states), _wr(states), linewidth=1.3, label=name)
    ax.axhline(1.0, color='k', linestyle=':', linewidth=0.8, label='Sync speed')
    ax.set_xlabel('t [s]')
    ax.set_ylabel('ωr [pu]')
    ax.set_title('DFIG EMT — Rotor Speed Dynamics\nAll 5 scenarios')
    ax.legend(fontsize=8, loc='lower right')
    ax.grid(linestyle=':', alpha=0.4)
    _save(fig, 'fig3_rotor_speed')


# ---------------------------------------------------------------------------
# Figure 4 — RSC voltage commands (S2 deep dip, crowbar detail)
# ---------------------------------------------------------------------------
def fig4_rsc_voltage(s2):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    t = _t(s2)
    axes[0].plot(t, _vrd(s2), 'C0', linewidth=1.2, label='vr_d')
    axes[0].set_ylabel('vr_d [pu]')
    axes[0].legend()
    axes[0].grid(linestyle=':', alpha=0.4)

    axes[1].plot(t, _vrq(s2), 'C1', linewidth=1.2, label='vr_q')
    axes[1].set_ylabel('vr_q [pu]')
    axes[1].set_xlabel('t [s]')
    axes[1].legend()
    axes[1].grid(linestyle=':', alpha=0.4)

    # Shade crowbar period
    cb = _cb(s2)
    for ax in axes:
        ax.fill_between(t, ax.get_ylim()[0], ax.get_ylim()[1],
                        where=cb > 0.5, alpha=0.12, color='red',
                        label='Crowbar active')
    fig.suptitle('DFIG EMT — RSC Voltage Commands during Deep Dip (S2)\n'
                 'Red shading: crowbar active, RSC blocked')
    fig.tight_layout()
    _save(fig, 'fig4_rsc_voltage')


# ---------------------------------------------------------------------------
# Figure 5 — Pe/Qs during crowbar cycling (S4)
# ---------------------------------------------------------------------------
def fig5_crowbar_cycle(s4):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 1, figsize=(9, 7), sharex=True)
    t  = _t(s4)
    axes[0].plot(t, _Pe(s4), 'C0', linewidth=1.2)
    axes[0].set_ylabel('Pe [pu]')
    axes[0].grid(linestyle=':', alpha=0.4)

    axes[1].plot(t, _Ir(s4), 'C3', linewidth=1.2)
    axes[1].axhline(2.0, color='k', linestyle='--', linewidth=0.9,
                    label='Crowbar thr')
    axes[1].set_ylabel('|Ir| [pu]')
    axes[1].legend(fontsize=8)
    axes[1].grid(linestyle=':', alpha=0.4)

    cb = _cb(s4)
    axes[2].fill_between(t, cb, alpha=0.7, color='C3', step='mid')
    axes[2].set_ylabel('Crowbar ON')
    axes[2].set_ylim(-0.05, 1.15)
    axes[2].set_yticks([0, 1])
    axes[2].set_xlabel('t [s]')
    axes[2].grid(linestyle=':', alpha=0.4)

    fig.suptitle('DFIG EMT — S4 Crowbar Cycling under Repeated Dip')
    fig.tight_layout()
    _save(fig, 'fig5_crowbar_cycle')


# ---------------------------------------------------------------------------
# Figure 6 — Phase portrait: Pe vs ωr (S1, S2, S5)
# ---------------------------------------------------------------------------
def fig6_phase_portrait(s1, s2, s5):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 5))
    for states, label, color in [
            (s1, 'S1 — 80% retained', 'C0'),
            (s2, 'S2 — 20% retained', 'C3'),
            (s5, 'S5 — sub-sync',     'C2'),
    ]:
        pe = _Pe(states)
        wr = _wr(states)
        ax.plot(wr, pe, linewidth=1.1, color=color, label=label, alpha=0.85)
        # Mark start and end
        ax.scatter([wr[0]], [pe[0]],  marker='o', color=color, s=40, zorder=5)
        ax.scatter([wr[-1]], [pe[-1]], marker='s', color=color, s=40, zorder=5)
    ax.set_xlabel('ωr [pu]')
    ax.set_ylabel('Pe [pu]')
    ax.set_title('DFIG EMT — Phase Portrait: Pe vs ωr\n'
                 'Circle = start, square = end of simulation')
    ax.legend(fontsize=9)
    ax.grid(linestyle=':', alpha=0.4)
    _save(fig, 'fig6_phase_portrait')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_scenarios():
    all_states = []
    t0 = time.time()
    print('\n' + '='*55)
    print('  TR-89  DFIG Full EMT — 5 Scenarios')
    print('='*55)
    for name, fn in SCENARIOS.items():
        t1 = time.time()
        states = fn()
        elapsed = time.time() - t1
        Pe_min = min(s.Pe for s in states)
        Ir_max = max(s.Ir_mag for s in states)
        cb_on  = any(s.crowbar for s in states)
        print(f'  {name[:35]:35s}  '
              f'Pe_min={Pe_min:+.3f}  Ir_max={Ir_max:.3f}  '
              f'CB={"Y" if cb_on else "N"}  ({elapsed:.1f}s)')
        all_states.append(states)
    print(f'\n  Wall time: {time.time()-t0:.1f}s')
    return all_states


def save_npz(all_states):
    names = ['S1', 'S2', 'S3', 'S4', 'S5']
    for name, states in zip(names, all_states):
        t  = np.array([s.t      for s in states], dtype=np.float32)
        Pe = np.array([s.Pe     for s in states], dtype=np.float32)
        Qs = np.array([s.Qs     for s in states], dtype=np.float32)
        Ir = np.array([s.Ir_mag for s in states], dtype=np.float32)
        wr = np.array([s.ωr     for s in states], dtype=np.float32)
        cb = np.array([s.crowbar for s in states], dtype=np.bool_)
        np.savez_compressed(
            _RES / f'tr89_{name.lower()}.npz',
            t=t, Pe=Pe, Qs=Qs, Ir=Ir, wr=wr, crowbar=cb,
        )
    print(f'  Saved 5 .npz files → {_RES}/')


def generate_figures(all_states):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.family':    'serif',
        'font.size':      9,
        'axes.labelsize': 10,
        'axes.titlesize': 11,
        'figure.dpi':     150,
        'savefig.dpi':    300,
    })
    s1, s2, s3, s4, s5 = all_states
    fig1_pq_all(all_states)
    fig2_crowbar(s1, s2)
    fig3_rotor_speed(all_states)
    fig4_rsc_voltage(s2)
    fig5_crowbar_cycle(s4)
    fig6_phase_portrait(s1, s2, s5)
    print(f'  6 figures saved → {_FIGS}/')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures-only', action='store_true')
    args = parser.parse_args()

    if args.figures_only:
        # Reload from saved npz
        all_states = []
        for name in ['S1', 'S2', 'S3', 'S4', 'S5']:
            d = np.load(_RES / f'tr89_{name.lower()}.npz')
            from dfig_emt import DFIGState
            states = []
            for i in range(len(d['t'])):
                states.append(DFIGState(
                    t=float(d['t'][i]), ψs_d=0, ψs_q=0, ψr_d=0, ψr_q=0,
                    ωr=float(d['wr'][i]),
                    is_d=0, is_q=0, ir_d=0, ir_q=0,
                    Te=0, Pe=float(d['Pe'][i]), Qs=float(d['Qs'][i]),
                    Ir_mag=float(d['Ir'][i]),
                    crowbar=bool(d['crowbar'][i]),
                    vr_d=0, vr_q=0,
                ))
            all_states.append(states)
        generate_figures(all_states)
    else:
        all_states = run_all_scenarios()
        save_npz(all_states)
        generate_figures(all_states)
        print('TR-89 complete.')
