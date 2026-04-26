"""
tr75_dfig_runner.py — TR-75 DFIG SSCI EMT Validation Runner
============================================================
Runs 6 compensation-level scenarios with the DFIGSSCIEngine (Radau, 11 states)
and generates 5 publication-quality figures.

Scenarios
---------
  S1  comp =  0%   fr =  0.0 Hz  — no SSCI (baseline)
  S2  comp = 20%   fr = 22.4 Hz  — borderline
  S3  comp = 30%   fr = 27.4 Hz  — SSCI onset
  S4  comp = 40%   fr = 31.6 Hz  — SSCI active
  S5  comp = 50%   fr = 35.4 Hz  — strong SSCI
  S6  comp = 60%   fr = 38.7 Hz  — very strong SSCI

Figures
-------
  fig1_isd_traces.pdf    — is_d(t) for all 6 scenarios
  fig2_fft_spectrum.pdf  — FFT power spectrum (S3–S6), SS peak visible
  fig3_growth_sweep.pdf  — growth rate λ vs comp% (SSCI onset curve)
  fig4_phase_portrait.pdf— is_d vs ωr phase portrait for S5 (growing spiral)
  fig5_criterion_compare.pdf — EMT λ vs impedance Re[Z_tot] comparison
"""

from __future__ import annotations

import argparse
import math
import pathlib
import sys
import os

import numpy as np

# Ensure local models/ is importable when run directly
_HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from dfig_ssci_emt import DFIGSSCIParams, DFIGSSCIEngine, envelope_growth_rate
from models.impedance_scan import SeriesCompLineParams, ConverterParams, OnlineImpedanceScanner

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_FIGS = pathlib.Path(__file__).parent.parent.parent / 'reports' / 'figures' / 'TR75_DFIG'
_RES  = pathlib.Path(__file__).parent.parent.parent / 'results'
_FIGS.mkdir(parents=True, exist_ok=True)
_RES.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------
_COMP_LEVELS = [0, 20, 30, 40, 50, 60]   # %
_LABELS = ['S1 (0%)', 'S2 (20%)', 'S3 (30%)', 'S4 (40%)', 'S5 (50%)', 'S6 (60%)']
_COLORS = ['C0', 'C2', 'C1', 'C3', 'C4', 'C5']

_T_END    = 3.0    # simulation duration [s]
_T_SETTLE = 0.30   # pre-perturbation settle time [s]
_T_PERTURB = 0.05  # perturbation duration [s]
_MAX_STEP  = 1e-4  # Radau max step [s]
_T_ANALYSIS = 0.5  # start of growth-rate analysis window [s]


def _save(fig, name: str) -> None:
    path = _FIGS / f'{name}.pdf'
    fig.savefig(path, bbox_inches='tight')
    print(f'  saved → {path.relative_to(_FIGS.parent.parent.parent)}')


# ---------------------------------------------------------------------------
# Run all scenarios
# ---------------------------------------------------------------------------
def run_all() -> list:
    """Return list of (comp_pct, states, lambda_Np_s, f_ss_Hz)."""
    results = []
    print('\n' + '=' * 60)
    print('  TR-75  DFIG SSCI EMT — 6 Scenarios (Radau, 11 states)')
    print('=' * 60)
    print(f'  {"Scenario":<10} {"comp%":>6} {"fr[Hz]":>8} '
          f'{"λ[Np/s]":>10} {"f_ss[Hz]":>10} {"SSCI?":>7} {"t_sim[s]":>9}')
    print('  ' + '-' * 60)

    for comp in _COMP_LEVELS:
        import time
        p = DFIGSSCIParams(comp_pct=float(comp))
        eng = DFIGSSCIEngine(p)

        t0 = time.time()
        states = eng.run(
            t_settle=_T_SETTLE,
            t_perturb=0.30,
            t_end=_T_END,
            perturb_amp=0.03,
            perturb_freq_Hz=p.fr_Hz if comp > 0 else 0.0,
            max_step=_MAX_STEP,
        )
        elapsed = time.time() - t0

        lam, f_ss = envelope_growth_rate(states, t_start=_T_ANALYSIS)
        ssci = 'YES' if lam > 0.5 else 'no'

        label = f'S{_COMP_LEVELS.index(comp)+1}'
        print(f'  {label:<10} {comp:>6.0f} {p.fr_Hz:>8.1f} '
              f'{lam:>10.2f} {f_ss:>10.1f} {ssci:>7}  ({elapsed:.1f}s)')

        # Save NPZ
        np.savez(
            _RES / f'tr75_dfig_s{_COMP_LEVELS.index(comp)+1}.npz',
            t    = np.array([s.t    for s in states]),
            isd  = np.array([s.is_d for s in states]),
            isq  = np.array([s.is_q for s in states]),
            wr   = np.array([s.ωr   for s in states]),
            vCd  = np.array([s.vCd  for s in states]),
            Pe   = np.array([s.Pe   for s in states]),
            comp_pct=np.array([comp]),
            fr_Hz   =np.array([p.fr_Hz]),
        )

        results.append((comp, states, lam, f_ss))

    print('=' * 60)
    return results


# ---------------------------------------------------------------------------
# Figure 1 — is_d time traces for all 6 scenarios
# ---------------------------------------------------------------------------
def fig1_isd_traces(results: list) -> None:
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 2, figsize=(11, 9), sharex=True)
    axes = axes.flatten()

    for idx, (comp, states, lam, f_ss) in enumerate(results):
        t   = np.array([s.t    for s in states])
        isd = np.array([s.is_d for s in states])
        ax  = axes[idx]
        ax.plot(t, isd, _COLORS[idx], lw=0.8)
        ax.axvline(_T_SETTLE, color='k', linestyle=':', lw=0.7, alpha=0.5)
        ax.set_title(f'{_LABELS[idx]}  fr={results[idx][0]:.0f}% → '
                     f'{DFIGSSCIParams(comp_pct=float(comp)).fr_Hz:.1f} Hz  '
                     f'λ={lam:+.1f} Np/s', fontsize=9)
        ax.set_ylabel('$i_{s,d}$ [pu]', fontsize=8)
        ax.grid(linestyle=':', alpha=0.4)
        ssci_tag = 'SSCI ACTIVE' if lam > 1.0 else 'stable'
        ax.text(0.98, 0.95, ssci_tag, transform=ax.transAxes,
                ha='right', va='top', fontsize=8,
                color='red' if lam > 1.0 else 'green')

    for ax in axes:
        ax.set_xlabel('t [s]', fontsize=8)

    fig.suptitle('TR-75 DFIG SSCI EMT — Stator d-axis Current (all scenarios)\n'
                 'Vertical dotted line: perturbation onset.  '
                 'SSCI onset expected for comp > ~35% (fr < RSC BW ≈ 29 Hz)',
                 fontsize=9)
    fig.tight_layout()
    _save(fig, 'fig1_isd_traces')
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 2 — FFT spectra for SSCI scenarios (S3–S6)
# ---------------------------------------------------------------------------
def fig2_fft_spectrum(results: list) -> None:
    import matplotlib.pyplot as plt
    from scipy.fft import rfft, rfftfreq
    from scipy.signal import butter, filtfilt

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True, sharey=False)
    axes_flat = axes.flatten()

    ssci_results = [(c, s, l, f) for c, s, l, f in results if c >= 30][:4]

    for ax, (comp, states, lam, f_ss) in zip(axes_flat, ssci_results):
        t   = np.array([s.t    for s in states])
        isd = np.array([s.is_d for s in states])
        mask = t >= _T_ANALYSIS
        t_w, isd_w = t[mask], isd[mask]

        fs = 1.0 / np.median(np.diff(t_w))
        t_u = np.arange(t_w[0], t_w[-1], 1.0 / fs)
        isd_u = np.interp(t_u, t_w, isd_w)

        # Remove DC + fundamental with HP filter above 3 Hz
        b, a = butter(4, 3.0 / (0.5 * fs), btype='high')
        isd_hp = filtfilt(b, a, isd_u)

        freqs = rfftfreq(len(isd_hp), 1.0 / fs)
        power = 20 * np.log10(np.abs(rfft(isd_hp)) / len(isd_hp) + 1e-12)

        p_obj = DFIGSSCIParams(comp_pct=float(comp))
        ax.plot(freqs, power, color='C3' if lam > 1.0 else 'C0', lw=0.9)
        ax.axvline(p_obj.fr_Hz, color='k', linestyle='--', lw=1.0,
                   label=f'$f_r$={p_obj.fr_Hz:.1f} Hz')
        if f_ss > 3:
            ax.axvline(f_ss, color='C1', linestyle=':', lw=1.0,
                       label=f'EMT peak={f_ss:.1f} Hz')
        ax.set_xlim(0, 50)
        ax.set_ylim(-100, 20)
        ax.set_title(f'comp={comp}%  λ={lam:+.1f} Np/s', fontsize=9)
        ax.set_xlabel('Frequency [Hz]', fontsize=8)
        ax.set_ylabel('Power [dBpu]', fontsize=8)
        ax.legend(fontsize=7)
        ax.grid(linestyle=':', alpha=0.4)

    fig.suptitle('TR-75 DFIG SSCI EMT — FFT Power Spectrum of $i_{s,d}$ '
                 '(sub-synchronous band, post-perturbation window)',
                 fontsize=9)
    fig.tight_layout()
    _save(fig, 'fig2_fft_spectrum')
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 3 — Growth rate λ vs comp% (onset curve)
# ---------------------------------------------------------------------------
def fig3_growth_sweep(results: list) -> None:
    import matplotlib.pyplot as plt

    comp_arr = np.array([r[0] for r in results], dtype=float)
    lam_arr  = np.array([r[2] for r in results])
    f_ss_arr = np.array([r[3] for r in results])
    fr_arr   = np.array([DFIGSSCIParams(comp_pct=c).fr_Hz for c in comp_arr])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)

    # Growth rate
    ax1.plot(comp_arr, lam_arr, 'o-', color='C3', lw=1.5, ms=6)
    ax1.axhline(0, color='k', lw=0.8, linestyle='--')
    ax1.axhline(1.0, color='gray', lw=0.8, linestyle=':', label='λ=1 Np/s threshold')
    for i, (c, l) in enumerate(zip(comp_arr, lam_arr)):
        ax1.annotate(f'S{i+1}', (c, l), textcoords='offset points',
                     xytext=(4, 4), fontsize=7)
    ax1.set_ylabel('Growth rate λ [Np/s]\n(+ = unstable SSCI)', fontsize=9)
    ax1.set_title('TR-75 DFIG SSCI — EMT Growth Rate vs Series Compensation', fontsize=10)
    ax1.legend(fontsize=8)
    ax1.grid(linestyle=':', alpha=0.4)
    ax1.fill_between(comp_arr, 0, np.maximum(lam_arr, 0), alpha=0.15, color='C3',
                     label='SSCI zone')

    # Resonant freq
    ax2.plot(comp_arr, fr_arr,  's-', color='C0', lw=1.2, ms=5, label='$f_r$ (formula)')
    ax2.plot(comp_arr, f_ss_arr, '^--', color='C1', lw=1.0, ms=5, label='$f_{ss}$ (EMT FFT)')
    ax2.set_xlabel('Series compensation [%]', fontsize=9)
    ax2.set_ylabel('Frequency [Hz]', fontsize=9)
    ax2.legend(fontsize=8)
    ax2.grid(linestyle=':', alpha=0.4)

    fig.tight_layout()
    _save(fig, 'fig3_growth_sweep')
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 4 — Phase portrait (is_d vs ωr) for the strongest SSCI scenario
# ---------------------------------------------------------------------------
def fig4_phase_portrait(results: list) -> None:
    import matplotlib.pyplot as plt

    # Use the scenario with largest λ
    best = max(results, key=lambda r: r[2])
    comp, states, lam, f_ss = best

    t   = np.array([s.t    for s in states])
    isd = np.array([s.is_d for s in states])
    wr  = np.array([s.ωr   for s in states])
    mask = t >= _T_SETTLE

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))

    # Phase portrait
    sc = ax1.scatter(isd[mask], wr[mask], c=t[mask], cmap='plasma',
                     s=1.0, linewidths=0)
    cb = fig.colorbar(sc, ax=ax1)
    cb.set_label('t [s]', fontsize=8)
    ax1.set_xlabel('$i_{s,d}$ [pu]', fontsize=9)
    ax1.set_ylabel('$\\omega_r$ [pu]', fontsize=9)
    ax1.set_title(f'Phase portrait  (comp={comp}%,  λ={lam:+.1f} Np/s)', fontsize=9)
    ax1.grid(linestyle=':', alpha=0.4)

    # Time trace alongside
    ax2.plot(t[mask], isd[mask], 'C3', lw=0.7, label='$i_{s,d}$')
    ax2r = ax2.twinx()
    ax2r.plot(t[mask], wr[mask], 'C0', lw=0.7, label='$\\omega_r$')
    ax2.set_xlabel('t [s]', fontsize=9)
    ax2.set_ylabel('$i_{s,d}$ [pu]', fontsize=9, color='C3')
    ax2r.set_ylabel('$\\omega_r$ [pu]', fontsize=9, color='C0')
    ax2.set_title('Time series', fontsize=9)
    ax2.grid(linestyle=':', alpha=0.4)

    fig.suptitle(f'TR-75 DFIG SSCI — Growing spiral in phase space  '
                 f'(comp={comp}%, $f_r$={DFIGSSCIParams(comp_pct=float(comp)).fr_Hz:.1f} Hz)',
                 fontsize=9)
    fig.tight_layout()
    _save(fig, 'fig4_phase_portrait')
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 5 — EMT λ vs impedance-domain Re[Z_tot] comparison
# ---------------------------------------------------------------------------
def fig5_criterion_compare(results: list) -> None:
    import matplotlib.pyplot as plt

    comp_arr = np.array([r[0] for r in results], dtype=float)
    lam_arr  = np.array([r[2] for r in results])

    # Compute Re[Z_tot] at fr for each scenario (from TR-75 impedance scanner)
    re_z = []
    for comp in comp_arr:
        if comp <= 0:
            re_z.append(float('nan'))
            continue
        fr = DFIGSSCIParams(comp_pct=float(comp)).fr_Hz
        line_p = SeriesCompLineParams.from_compensation_pct(
            xl_pu=0.300, comp_pct=float(comp), r_pu=0.020)
        # Use DFIG transient inductance L' = σLr ≈ 0.20 pu as effective Lf
        conv_p = ConverterParams(
            L_f_pu=0.20, k_p=2.0 * 314.0, k_i=100.0 * 314.0,
            R_f_pu=0.0054, control_mode='gfl')
        scanner = OnlineImpedanceScanner(line_p, conv_p)
        znet  = scanner._z_network(fr)
        zconv = scanner._z_converter(fr)
        re_z.append((znet + zconv).real)

    re_z = np.array([v if v == v else 0.0 for v in re_z])  # nan→0

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)

    ax1.plot(comp_arr, lam_arr, 'o-C3', lw=1.5, ms=6, label='EMT λ [Np/s]')
    ax1.axhline(0, color='k', lw=0.8, ls='--')
    ax1.set_ylabel('λ [Np/s]', fontsize=9)
    ax1.set_title('TR-75: EMT Growth Rate vs Impedance Criterion Comparison', fontsize=10)
    ax1.legend(fontsize=8); ax1.grid(ls=':', alpha=0.4)
    ax1.fill_between(comp_arr, 0, np.maximum(lam_arr, 0),
                     alpha=0.12, color='C3')

    ax2.plot(comp_arr[comp_arr > 0], re_z[comp_arr > 0],
             's-C0', lw=1.5, ms=6, label=r'Re[$Z_{net}+Z_{conv}$] at $f_r$')
    ax2.axhline(0, color='k', lw=0.8, ls='--',
                label='Re[Z]=0 → SSCI boundary')
    ax2.axhline(-0.005, color='gray', lw=0.8, ls=':',
                label='TR-75 criterion threshold (−0.005 pu)')
    ax2.set_xlabel('Series compensation [%]', fontsize=9)
    ax2.set_ylabel(r'Re[$Z_{tot}$] [pu]', fontsize=9)
    ax2.legend(fontsize=8); ax2.grid(ls=':', alpha=0.4)

    fig.tight_layout()
    _save(fig, 'fig5_criterion_compare')
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    import matplotlib
    matplotlib.use('Agg')
    matplotlib.rcParams.update({
        'font.family':  'serif',
        'font.size':     9,
        'axes.labelsize':10,
        'axes.titlesize':11,
        'figure.dpi':    150,
        'savefig.dpi':   300,
    })

    results = run_all()
    print('\nGenerating figures ...')
    fig1_isd_traces(results)
    fig2_fft_spectrum(results)
    fig3_growth_sweep(results)
    fig4_phase_portrait(results)
    fig5_criterion_compare(results)
    print(f'  5 figures saved → {_FIGS}/')

    # Print SSCI summary table
    print('\n  SSCI onset summary:')
    print(f'  {"S":<4} {"comp%":>6} {"fr[Hz]":>8} {"λ[Np/s]":>10} '
          f'{"f_ss[Hz]":>10} {"SSCI?":>7}')
    print('  ' + '-' * 50)
    for idx, (comp, _, lam, f_ss) in enumerate(results):
        fr = DFIGSSCIParams(comp_pct=float(comp)).fr_Hz
        ssci = 'YES ⚠' if lam > 1.0 else 'no'
        print(f'  S{idx+1:<3} {comp:>6.0f} {fr:>8.1f} {lam:>10.2f} '
              f'{f_ss:>10.1f} {ssci:>7}')
    print()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures-only', action='store_true',
                        help='Reload saved NPZ and regenerate figures only')
    args = parser.parse_args()

    if args.figures_only:
        import matplotlib
        matplotlib.use('Agg')
        results = []
        for i, comp in enumerate(_COMP_LEVELS, 1):
            d = np.load(_RES / f'tr75_dfig_s{i}.npz')
            from dfig_ssci_emt import DFIGSSCIState
            states = [
                DFIGSSCIState(
                    t=float(d['t'][k]), ψs_d=0., ψs_q=0., ψr_d=0., ψr_q=0.,
                    ωr=float(d['wr'][k]),
                    is_d=float(d['isd'][k]), is_q=float(d['isq'][k]),
                    ir_d=0., ir_q=0.,
                    vCd=float(d['vCd'][k]), vCq=0.,
                    Te=0., Pe=float(d['Pe'][k]), Qs=0.,
                    ωslip=0., vr_d=0., vr_q=0.,
                    fr_Hz=float(d['fr_Hz'][0]),
                )
                for k in range(len(d['t']))
            ]
            lam, f_ss = envelope_growth_rate(states, t_start=_T_ANALYSIS)
            results.append((comp, states, lam, f_ss))
        fig1_isd_traces(results)
        fig2_fft_spectrum(results)
        fig3_growth_sweep(results)
        fig4_phase_portrait(results)
        fig5_criterion_compare(results)
    else:
        main()
