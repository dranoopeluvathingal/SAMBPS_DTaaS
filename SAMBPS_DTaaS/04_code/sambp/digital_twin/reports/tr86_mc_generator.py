#!/usr/bin/env python3
# =============================================================================
# sambp / digital_twin / reports / tr86_mc_generator.py
#
# TR-86 Monte Carlo runner — IEEE 118-bus large-scale study
# WP 86.4
#
# Usage:
#   python reports/tr86_mc_generator.py
#   python reports/tr86_mc_generator.py --n-scenarios 500 --seed 42
#   python reports/tr86_mc_generator.py --no-plots
# =============================================================================

from __future__ import annotations

import argparse
import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

_DT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_DT_ROOT))

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from models.ieee118_network import IEEE118Config, IEEE118Network, FaultState118
from models.mc_scenario_generator import MCScenarioGenerator, MC86Scenario
from models.sambp_protection_stack import SAMBPStack86, ProtectionDecision86

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPORT_DIR = Path(__file__).resolve().parent
_FIG_DIR    = _REPORT_DIR / "figures" / "TR86"
_FIG_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Colour palette (IEEE colorblind-safe)
# ---------------------------------------------------------------------------

_BLUE   = "#2166AC"
_GREEN  = "#1B7837"
_AMBER  = "#D6604D"
_PURPLE = "#762A83"
_TEAL   = "#4DAC26"
_GREY   = "#878787"

_FUNC_COLOURS = {
    '87L': _BLUE,
    '21':  _GREEN,
    '46':  _AMBER,
    '51':  _PURPLE,
    '67':  _TEAL,
}

_ELEMENTS = ['87L', '21', '46', '51', '67']

# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_mc(n_scenarios: int, seed: int, no_plots: bool) -> Dict:
    """Run Monte Carlo and return results dict."""

    print(f"\n{'='*65}")
    print(f"  TR-86 — IEEE 118-Bus Monte Carlo   (N={n_scenarios}, seed={seed})")
    print(f"{'='*65}\n")

    # ── Generate scenarios ────────────────────────────────────────────
    gen      = MCScenarioGenerator(n_scenarios=n_scenarios, seed=seed)
    scenarios = gen.generate()
    print(f"  Generated {len(scenarios)} scenarios via LHS.\n")

    # ── Run MC loop ───────────────────────────────────────────────────
    stack = SAMBPStack86()

    # Accumulators: {element → {agree_count, total}}
    overall     = {e: {'agree': 0, 'total': 0} for e in _ELEMENTS}
    by_pen      = {p: {e: {'agree': 0, 'total': 0} for e in _ELEMENTS}
                   for p in [0.0, 0.30, 0.50, 1.00]}
    by_ft       = {ft: {e: {'agree': 0, 'total': 0} for e in _ELEMENTS}
                   for ft in ['3PH', 'SLG', 'DLG', 'LL']}
    by_mode     = {m: {e: {'agree': 0, 'total': 0} for e in _ELEMENTS}
                   for m in ['gfl', 'gfm', 'mixed']}
    # For heatmap: (fault_type, ibr_pen) → {agree, total} for element '21'
    hm_21       = defaultdict(lambda: {'agree': 0, 'total': 0})
    # Operate times per element
    op_times    = {e: [] for e in _ELEMENTS}

    # Cache networks by (ibr_penetration, ibr_mode, load_level_bucket)
    # Rebuild network only when config changes significantly
    _net_cache: Dict[Tuple, IEEE118Network] = {}
    skipped = 0

    t_start = time.time()
    for idx, sc in enumerate(scenarios):
        # Progress update every 50 scenarios
        if idx % 50 == 0:
            elapsed = time.time() - t_start
            print(f"  Scenario {idx:4d}/{n_scenarios}  ({elapsed:.1f}s elapsed)")

        # Cache key — load_level bucketed to 0.05 resolution for speed
        ll_bucket = round(sc.load_level * 20) / 20.0
        cache_key = (sc.ibr_penetration, sc.ibr_mode, ll_bucket)

        if cache_key not in _net_cache:
            cfg = IEEE118Config(
                ibr_penetration=sc.ibr_penetration,
                ibr_mode=sc.ibr_mode,
                load_level=sc.load_level,
            )
            try:
                _net_cache[cache_key] = IEEE118Network.from_config(cfg)
            except Exception as e:
                skipped += 1
                continue

        net = _net_cache[cache_key]

        # Inject fault
        try:
            fs = net.inject_fault(
                bus_idx=sc.bus_idx,
                fault_type=sc.fault_type,
                R_f_ohm=sc.R_f_ohm,
                scenario_id=sc.scenario_id,
            )
        except Exception:
            skipped += 1
            continue

        # Evaluate protection stack
        decisions = stack.evaluate(fs)

        # Record results
        pen_key = sc.ibr_penetration
        ft_key  = sc.fault_type
        mode_key = sc.ibr_mode

        for d in decisions:
            agree = 1 if d.verdict == 'TRIP' else 0

            overall[d.element]['agree'] += agree
            overall[d.element]['total'] += 1

            by_pen[pen_key][d.element]['agree'] += agree
            by_pen[pen_key][d.element]['total'] += 1

            by_ft[ft_key][d.element]['agree'] += agree
            by_ft[ft_key][d.element]['total'] += 1

            by_mode[mode_key][d.element]['agree'] += agree
            by_mode[mode_key][d.element]['total'] += 1

            if d.verdict == 'TRIP':
                op_times[d.element].append(d.operate_time_ms)

            if d.element == '21':
                hm_key = (ft_key, pen_key)
                hm_21[hm_key]['agree'] += agree
                hm_21[hm_key]['total'] += 1

        net.clear_fault()

    t_elapsed = time.time() - t_start
    print(f"\n  MC loop complete in {t_elapsed:.1f}s  (skipped={skipped})\n")

    # ── Compute agree_rates ───────────────────────────────────────────
    def rate(d):
        return d['agree'] / max(d['total'], 1)

    overall_rate = {e: rate(overall[e]) for e in _ELEMENTS}
    pen_rate     = {p: {e: rate(by_pen[p][e]) for e in _ELEMENTS}
                    for p in by_pen}
    ft_rate      = {ft: {e: rate(by_ft[ft][e]) for e in _ELEMENTS}
                    for ft in by_ft}
    mode_rate    = {m: {e: rate(by_mode[m][e]) for e in _ELEMENTS}
                    for m in by_mode}
    hm21_rate    = {k: (v['agree'] / max(v['total'], 1)) for k, v in hm_21.items()}

    # ── Print summary ─────────────────────────────────────────────────
    _print_summary(overall_rate, pen_rate, ft_rate, mode_rate,
                   n_scenarios, skipped, t_elapsed)

    # ── Figures ───────────────────────────────────────────────────────
    if not no_plots:
        _plot_figures(overall_rate, pen_rate, ft_rate, hm21_rate, op_times)

    return {
        'overall_rate': overall_rate,
        'pen_rate':     pen_rate,
        'ft_rate':      ft_rate,
        'mode_rate':    mode_rate,
        'hm21_rate':    hm21_rate,
        'op_times':     op_times,
        'n_scenarios':  n_scenarios,
        'skipped':      skipped,
        't_elapsed':    t_elapsed,
    }


# ---------------------------------------------------------------------------
# Summary print
# ---------------------------------------------------------------------------

def _print_summary(overall_rate, pen_rate, ft_rate, mode_rate,
                   n_scenarios, skipped, t_elapsed):
    w = 65
    print("=" * w)
    print("  TR-86 RESULTS SUMMARY")
    print("=" * w)
    print(f"  Scenarios run: {n_scenarios - skipped}  (skipped: {skipped})")
    print(f"  Elapsed:       {t_elapsed:.1f} s")
    print()

    print("  AGREE RATE PER PROTECTION FUNCTION")
    print(f"  {'Element':<8} {'Agree%':>8}")
    print(f"  {'-'*18}")
    for e in _ELEMENTS:
        print(f"  {e:<8} {overall_rate[e]*100:>7.2f}%")
    overall_avg = np.mean([overall_rate[e] for e in _ELEMENTS])
    print(f"  {'OVERALL':<8} {overall_avg*100:>7.2f}%")
    print()

    print("  AGREE RATE BY IBR PENETRATION (element 21 - distance)")
    print(f"  {'Pen%':<8} {'87L':>7} {'21':>7} {'46':>7} {'51':>7} {'67':>7}")
    print(f"  {'-'*43}")
    for p in [0.0, 0.30, 0.50, 1.00]:
        row = "  " + f"{p*100:.0f}%".ljust(8)
        for e in _ELEMENTS:
            row += f" {pen_rate[p][e]*100:>6.1f}%"
        print(row)
    print()

    print("  AGREE RATE BY FAULT TYPE")
    print(f"  {'Type':<8} {'87L':>7} {'21':>7} {'46':>7} {'51':>7} {'67':>7}")
    print(f"  {'-'*43}")
    for ft in ['3PH', 'SLG', 'DLG', 'LL']:
        row = "  " + ft.ljust(8)
        for e in _ELEMENTS:
            row += f" {ft_rate[ft][e]*100:>6.1f}%"
        print(row)
    print()

    print("  AGREE RATE BY IBR MODE")
    print(f"  {'Mode':<8} {'87L':>7} {'21':>7} {'46':>7} {'51':>7} {'67':>7}")
    print(f"  {'-'*43}")
    for m in ['gfl', 'gfm', 'mixed']:
        row = "  " + m.ljust(8)
        for e in _ELEMENTS:
            row += f" {mode_rate[m][e]*100:>6.1f}%"
        print(row)
    print("=" * w)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _plot_figures(overall_rate, pen_rate, ft_rate, hm21_rate, op_times):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 9,
        'axes.labelsize': 10,
        'axes.titlesize': 11,
        'figure.dpi': 150,
    })

    # ── Fig 1: Agree rate per protection function ─────────────────────
    fig1, ax1 = plt.subplots(figsize=(6.5, 4.0))
    bars = ax1.bar(
        _ELEMENTS,
        [overall_rate[e] * 100 for e in _ELEMENTS],
        color=[_FUNC_COLOURS[e] for e in _ELEMENTS],
        edgecolor='black', linewidth=0.6,
    )
    ax1.axhline(y=85.0, color='red', linestyle='--', linewidth=1.0,
                label='85% threshold')
    for bar, e in zip(bars, _ELEMENTS):
        ax1.text(bar.get_x() + bar.get_width() / 2.0,
                 bar.get_height() + 1.0,
                 f"{overall_rate[e]*100:.1f}%",
                 ha='center', va='bottom', fontsize=8)
    ax1.set_ylim(0, 110)
    ax1.set_ylabel('TRIP Agree Rate [%]')
    ax1.set_title('TR-86: SAMBP Agree Rate per Protection Function\n'
                  'IEEE 118-Bus Monte Carlo')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    fig1.tight_layout()
    fig1.savefig(_FIG_DIR / 'fig1_agree_per_function.pdf', bbox_inches='tight')
    fig1.savefig(_FIG_DIR / 'fig1_agree_per_function.png', bbox_inches='tight')
    plt.close(fig1)
    print(f"  Fig 1 saved → {_FIG_DIR / 'fig1_agree_per_function.pdf'}")

    # ── Fig 2: Agree rate vs IBR penetration ─────────────────────────
    fig2, ax2 = plt.subplots(figsize=(6.5, 4.0))
    pen_values = [0.0, 0.30, 0.50, 1.00]
    pen_labels = ['0%', '30%', '50%', '100%']
    for e in _ELEMENTS:
        y_vals = [pen_rate[p][e] * 100 for p in pen_values]
        ax2.plot(pen_labels, y_vals,
                 marker='o', color=_FUNC_COLOURS[e], label=e, linewidth=1.5)
    ax2.axhline(y=85.0, color='red', linestyle='--', linewidth=1.0,
                label='85% threshold')
    ax2.set_ylim(0, 110)
    ax2.set_ylabel('TRIP Agree Rate [%]')
    ax2.set_xlabel('IBR Penetration Level')
    ax2.set_title('TR-86: Agree Rate vs IBR Penetration\nIEEE 118-Bus')
    ax2.legend(loc='lower left', fontsize=8)
    ax2.grid(alpha=0.3)
    fig2.tight_layout()
    fig2.savefig(_FIG_DIR / 'fig2_agree_vs_penetration.pdf', bbox_inches='tight')
    fig2.savefig(_FIG_DIR / 'fig2_agree_vs_penetration.png', bbox_inches='tight')
    plt.close(fig2)
    print(f"  Fig 2 saved → {_FIG_DIR / 'fig2_agree_vs_penetration.pdf'}")

    # ── Fig 3: Agree rate by fault type ──────────────────────────────
    fig3, ax3 = plt.subplots(figsize=(6.5, 4.0))
    fault_types = ['3PH', 'SLG', 'DLG', 'LL']
    x    = np.arange(len(fault_types))
    w    = 0.15
    cols = [_BLUE, _GREEN, _AMBER, _PURPLE, _TEAL]
    for i, e in enumerate(_ELEMENTS):
        y_vals = [ft_rate[ft][e] * 100 for ft in fault_types]
        ax3.bar(x + (i - 2) * w, y_vals, width=w,
                color=cols[i], edgecolor='black', linewidth=0.5, label=e)
    ax3.axhline(y=85.0, color='red', linestyle='--', linewidth=1.0,
                label='85% threshold')
    ax3.set_xticks(x)
    ax3.set_xticklabels(fault_types)
    ax3.set_ylim(0, 115)
    ax3.set_ylabel('TRIP Agree Rate [%]')
    ax3.set_xlabel('Fault Type')
    ax3.set_title('TR-86: Agree Rate by Fault Type\nIEEE 118-Bus')
    ax3.legend(fontsize=7, ncol=3)
    ax3.grid(axis='y', alpha=0.3)
    fig3.tight_layout()
    fig3.savefig(_FIG_DIR / 'fig3_agree_by_fault_type.pdf', bbox_inches='tight')
    fig3.savefig(_FIG_DIR / 'fig3_agree_by_fault_type.png', bbox_inches='tight')
    plt.close(fig3)
    print(f"  Fig 3 saved → {_FIG_DIR / 'fig3_agree_by_fault_type.pdf'}")

    # ── Fig 4: Heatmap — agree_rate[fault_type × IBR_pen] for 21 ────
    fig4, ax4 = plt.subplots(figsize=(6.0, 4.0))
    pen_vals = [0.0, 0.30, 0.50, 1.00]
    ft_vals  = ['3PH', 'SLG', 'DLG', 'LL']
    hm_data  = np.zeros((len(ft_vals), len(pen_vals)))
    for ri, ft in enumerate(ft_vals):
        for ci, p in enumerate(pen_vals):
            key = (ft, p)
            hm_data[ri, ci] = hm21_rate.get(key, 0.0) * 100

    im = ax4.imshow(hm_data, cmap='RdYlGn', vmin=40, vmax=100,
                    aspect='auto')
    ax4.set_xticks(range(len(pen_vals)))
    ax4.set_xticklabels(['0%', '30%', '50%', '100%'])
    ax4.set_yticks(range(len(ft_vals)))
    ax4.set_yticklabels(ft_vals)
    ax4.set_xlabel('IBR Penetration')
    ax4.set_ylabel('Fault Type')
    ax4.set_title('TR-86: Element 21 Agree Rate [%]\nFault Type × IBR Penetration')
    for ri in range(len(ft_vals)):
        for ci in range(len(pen_vals)):
            ax4.text(ci, ri, f"{hm_data[ri, ci]:.0f}",
                     ha='center', va='center', fontsize=9,
                     color='black')
    plt.colorbar(im, ax=ax4, label='Agree Rate [%]')
    fig4.tight_layout()
    fig4.savefig(_FIG_DIR / 'fig4_heatmap_21.pdf', bbox_inches='tight')
    fig4.savefig(_FIG_DIR / 'fig4_heatmap_21.png', bbox_inches='tight')
    plt.close(fig4)
    print(f"  Fig 4 saved → {_FIG_DIR / 'fig4_heatmap_21.pdf'}")

    # ── Fig 5: Operate time histograms ───────────────────────────────
    fig5, axes = plt.subplots(1, len(_ELEMENTS), figsize=(12.0, 3.5), sharey=False)
    for ax, e in zip(axes, _ELEMENTS):
        data = [t for t in op_times[e] if t < 5000.0]
        if data:
            ax.hist(data, bins=20, color=_FUNC_COLOURS[e],
                    edgecolor='black', linewidth=0.4)
            ax.axvline(np.median(data), color='red', linestyle='--',
                       linewidth=1.0, label=f'med={np.median(data):.0f}ms')
            ax.legend(fontsize=7)
        ax.set_title(e, fontsize=10)
        ax.set_xlabel('Operate Time [ms]')
        ax.set_ylabel('Count' if e == '87L' else '')
        ax.grid(axis='y', alpha=0.3)
    fig5.suptitle('TR-86: Operate Time Distribution per Protection Element',
                  fontsize=11)
    fig5.tight_layout()
    fig5.savefig(_FIG_DIR / 'fig5_operate_times.pdf', bbox_inches='tight')
    fig5.savefig(_FIG_DIR / 'fig5_operate_times.png', bbox_inches='tight')
    plt.close(fig5)
    print(f"  Fig 5 saved → {_FIG_DIR / 'fig5_operate_times.pdf'}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="TR-86 IEEE 118-Bus Monte Carlo Runner")
    parser.add_argument('--n-scenarios', type=int, default=500,
                        help='Number of MC scenarios (default 500)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed (default 42)')
    parser.add_argument('--no-plots', action='store_true',
                        help='Skip figure generation')
    args = parser.parse_args()

    results = run_mc(
        n_scenarios=args.n_scenarios,
        seed=args.seed,
        no_plots=args.no_plots,
    )
    return results


if __name__ == '__main__':
    main()
