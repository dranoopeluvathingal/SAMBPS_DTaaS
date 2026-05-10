#!/usr/bin/env python3
# =============================================================================
# sambp / digital_twin / models / tr88_runner.py
#
# TR-88  N-2 Cascading Contingency Study
# ========================================
# 100 scenarios on IEEE 118-bus | cascade depth up to 8 | misoperation counter
#
# Usage
# -----
#   python tr88_runner.py              # 100 scenarios, default IBR=30%
#   python tr88_runner.py --n 50 --ibr 0.5
#   python tr88_runner.py --figures-only
#
# Output
# ------
#   results/tr88_cascade_results.npz
#   reports/figures/TR88/  (5 figures)
# =============================================================================

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path
from typing import List

import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

_DT_ROOT    = Path(__file__).resolve().parent.parent
_RESULTS    = _DT_ROOT / "results"
_FIGS       = _DT_ROOT / "reports" / "figures" / "TR88"
_RESULTS.mkdir(parents=True, exist_ok=True)
_FIGS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(_DT_ROOT))
from models.cascade_engine import CascadeEngine, CascadeScenario

# ---------------------------------------------------------------------------
IBR_LEVELS = [0.0, 0.30, 0.50, 1.00]   # sweep for sensitivity figures
N_SCENARIOS_DEFAULT = 100


# ---------------------------------------------------------------------------
def run_all(n: int = 100, seed: int = 42) -> List[CascadeScenario]:
    """
    Run n cascade scenarios at each IBR level.
    Returns flat list of all CascadeScenario objects.
    """
    all_scenarios: List[CascadeScenario] = []
    t0 = time.time()

    print(f"\n{'='*60}")
    print(f"  TR-88  N-2 Cascading Contingency Study")
    print(f"  N = {n} scenarios × {len(IBR_LEVELS)} IBR levels = "
          f"{n*len(IBR_LEVELS)} total")
    print(f"{'='*60}")

    for pen in IBR_LEVELS:
        engine = CascadeEngine(ibr_penetration=pen, ibr_mode='mixed', seed=seed)
        contingencies = engine.generate_n2_contingencies(n)
        print(f"\n  IBR pen={pen:.0%} — {len(contingencies)} contingencies", flush=True)

        for i, cont in enumerate(contingencies):
            sc = engine.run_scenario(cont)
            all_scenarios.append(sc)
            pct = 100*(i+1)/len(contingencies)
            print(f"    {pct:5.1f}%  "
                  f"depth={sc.total_depth}  "
                  f"misops={sc.total_misops}  "
                  f"term={sc.terminated_by}",
                  end='\r', flush=True)
        print()

    print(f"\n  Total wall time: {time.time()-t0:.1f}s")
    return all_scenarios


def save_results(scenarios: List[CascadeScenario]) -> None:
    np.savez_compressed(
        _RESULTS / "tr88_cascade_results.npz",
        contingency_id  = np.array([s.contingency_id   for s in scenarios], np.int32),
        ibr_pen         = np.array([s.ibr_penetration   for s in scenarios], np.float32),
        total_depth     = np.array([s.total_depth        for s in scenarios], np.int32),
        total_misops    = np.array([s.total_misops       for s in scenarios], np.int32),
        total_lines_lost= np.array([s.total_lines_lost   for s in scenarios], np.int32),
        total_buses_lost= np.array([s.total_buses_lost   for s in scenarios], np.int32),
        terminated_by   = np.array([s.terminated_by      for s in scenarios]),
        line_a          = np.array([s.line_a              for s in scenarios], np.int32),
        line_b          = np.array([s.line_b              for s in scenarios], np.int32),
    )
    # Per-depth misop table
    max_depth = max((s.total_depth for s in scenarios), default=0)
    misops_by_depth = np.zeros((max_depth+1,), dtype=np.float32)
    count_by_depth  = np.zeros((max_depth+1,), dtype=np.int32)
    for s in scenarios:
        for step in s.steps:
            d = step.depth
            if d <= max_depth:
                misops_by_depth[d] += step.misops_restrain + step.misops_false_trip
                count_by_depth[d]  += 1
    np.savez_compressed(
        _RESULTS / "tr88_depth_misops.npz",
        misops_by_depth = misops_by_depth,
        count_by_depth  = count_by_depth,
    )
    print(f"  Saved → {_RESULTS}/tr88_cascade_results.npz")


def generate_figures(scenarios: List[CascadeScenario]) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    plt.rcParams.update({
        'font.family':    'serif',
        'font.size':      10,
        'axes.labelsize': 11,
        'axes.titlesize': 12,
        'legend.fontsize':9,
        'figure.dpi':     150,
        'savefig.dpi':    300,
        'savefig.bbox':   'tight',
    })

    PEN_COLORS = {0.0:'#1a5276', 0.30:'#1e8449',
                  0.50:'#d35400', 1.00:'#922b21'}
    PEN_LABELS = {0.0:'0% IBR', 0.30:'30% IBR',
                  0.50:'50% IBR', 1.00:'100% IBR'}

    def subs(pen):
        return [s for s in scenarios if abs(s.ibr_penetration - pen) < 0.01]

    # ── Fig 1: Cascade depth histogram by IBR penetration ────────────
    fig, axes = plt.subplots(2, 2, figsize=(9, 6), sharex=True, sharey=True)
    axes = axes.flatten()
    for ax, pen in zip(axes, IBR_LEVELS):
        depths = [s.total_depth for s in subs(pen)]
        ax.hist(depths, bins=range(0, 10), color=PEN_COLORS[pen],
                edgecolor='black', linewidth=0.5, align='left')
        ax.set_title(f'{PEN_LABELS[pen]}', fontsize=11)
        ax.set_xlabel('Cascade depth')
        ax.set_ylabel('Count')
        mean_d = np.mean(depths) if depths else 0
        ax.axvline(mean_d, color='red', linestyle='--', linewidth=1.2,
                   label=f'mean={mean_d:.1f}')
        ax.legend(fontsize=8)
        ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    fig.suptitle('Cascade depth distribution by IBR penetration\n'
                 'IEEE 118-bus, 100 N-2 scenarios per level', y=1.01)
    fig.tight_layout()
    _save(fig, 'fig1_depth_histogram')

    # ── Fig 2: Misoperation count per cascade depth (mean ± std) ─────
    fig, ax = plt.subplots(figsize=(8, 4.5))
    max_depth = max((s.total_depth for s in scenarios), default=0)
    depths_range = range(0, max_depth + 1)

    for pen in IBR_LEVELS:
        sub = subs(pen)
        mean_misops = []
        std_misops  = []
        for d in depths_range:
            vals = []
            for s in sub:
                for step in s.steps:
                    if step.depth == d:
                        vals.append(step.misops_restrain + step.misops_false_trip)
            mean_misops.append(np.mean(vals) if vals else 0)
            std_misops.append(np.std(vals)  if vals else 0)
        mean_misops = np.array(mean_misops)
        std_misops  = np.array(std_misops)
        ax.plot(list(depths_range), mean_misops, marker='o', linewidth=2,
                color=PEN_COLORS[pen], label=PEN_LABELS[pen])
        ax.fill_between(list(depths_range),
                        mean_misops - std_misops,
                        mean_misops + std_misops,
                        alpha=0.15, color=PEN_COLORS[pen])
    ax.set_xlabel('Cascade depth')
    ax.set_ylabel('Mean misoperations per depth')
    ax.set_title('SAMBP misoperation count vs cascade depth\n'
                 'Mean ± 1σ across 100 N-2 scenarios')
    ax.legend()
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    ax.grid(linestyle=':', alpha=0.4)
    ax.set_xlim(-0.3, max_depth + 0.3)
    ax.set_ylim(bottom=0)
    _save(fig, 'fig2_misops_per_depth')

    # ── Fig 3: Total misops vs IBR penetration (box plot) ────────────
    fig, ax = plt.subplots(figsize=(7, 4.5))
    data_box = [[s.total_misops for s in subs(p)] for p in IBR_LEVELS]
    bp = ax.boxplot(data_box, patch_artist=True,
                    medianprops=dict(color='black', linewidth=2))
    for patch, pen in zip(bp['boxes'], IBR_LEVELS):
        patch.set_facecolor(PEN_COLORS[pen])
        patch.set_alpha(0.7)
    ax.set_xticks(range(1, len(IBR_LEVELS)+1))
    ax.set_xticklabels([PEN_LABELS[p] for p in IBR_LEVELS])
    ax.set_ylabel('Total misoperations per scenario')
    ax.set_title('Total SAMBP misoperations per N-2 scenario\n'
                 'IEEE 118-bus, 100 scenarios per IBR level')
    ax.grid(axis='y', linestyle=':', alpha=0.4)
    means = [np.mean([s.total_misops for s in subs(p)]) for p in IBR_LEVELS]
    for i, (m, p) in enumerate(zip(means, IBR_LEVELS)):
        ax.text(i+1, m + 0.05, f'{m:.2f}', ha='center', va='bottom',
                fontsize=8.5, color=PEN_COLORS[p], fontweight='bold')
    _save(fig, 'fig3_misops_boxplot')

    # ── Fig 4: Lines lost vs cascade depth (cumulative mean) ─────────
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for pen in IBR_LEVELS:
        sub = subs(pen)
        cumlines_per_scen = []
        for s in sub:
            cumulative = 0
            row = []
            for d in depths_range:
                for step in s.steps:
                    if step.depth == d:
                        cumulative += len(step.tripped_lines)
                row.append(cumulative)
            cumlines_per_scen.append(row)
        arr = np.array(cumlines_per_scen)
        ax.plot(list(depths_range), arr.mean(axis=0), marker='s',
                linewidth=2, color=PEN_COLORS[pen], label=PEN_LABELS[pen])
        ax.fill_between(list(depths_range),
                        arr.mean(axis=0) - arr.std(axis=0),
                        arr.mean(axis=0) + arr.std(axis=0),
                        alpha=0.12, color=PEN_COLORS[pen])
    ax.set_xlabel('Cascade depth')
    ax.set_ylabel('Cumulative lines lost (mean)')
    ax.set_title('Cumulative lines lost vs cascade depth\n'
                 'Mean ± 1σ across 100 N-2 scenarios')
    ax.legend()
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    ax.grid(linestyle=':', alpha=0.4)
    ax.set_xlim(-0.3, max_depth + 0.3)
    ax.set_ylim(bottom=0)
    _save(fig, 'fig4_lines_lost')

    # ── Fig 5: Termination reason pie charts ─────────────────────────
    fig, axes = plt.subplots(1, 4, figsize=(12, 3.5))
    TERM_COLORS = {'stable':'#2ecc71', 'island':'#f39c12',
                   'blackout':'#e74c3c', 'max_depth':'#9b59b6'}
    for ax, pen in zip(axes, IBR_LEVELS):
        sub = subs(pen)
        counts = {}
        for s in sub:
            counts[s.terminated_by] = counts.get(s.terminated_by, 0) + 1
        labels = list(counts.keys())
        sizes  = list(counts.values())
        colors = [TERM_COLORS.get(l, '#95a5a6') for l in labels]
        ax.pie(sizes, labels=labels, colors=colors, autopct='%1.0f%%',
               startangle=90, textprops={'fontsize': 8})
        ax.set_title(PEN_LABELS[pen], fontsize=10)
    fig.suptitle('Cascade termination reason by IBR penetration\n'
                 '100 N-2 scenarios per level', y=1.02)
    fig.tight_layout()
    _save(fig, 'fig5_termination_pie')

    print(f"  5 figures saved → {_FIGS}/")


def _save(fig, name: str) -> None:
    import matplotlib.pyplot as plt
    for ext in ('pdf', 'png'):
        fig.savefig(_FIGS / f'{name}.{ext}')
    plt.close(fig)


def print_summary(scenarios: List[CascadeScenario]) -> None:
    print(f"\n{'='*60}")
    print("  TR-88  RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  {'IBR pen':>8}  {'Mean depth':>10}  "
          f"{'Mean misops':>12}  {'Stable%':>8}  {'Island/BK%':>10}")
    print(f"  {'-'*8}  {'-'*10}  {'-'*12}  {'-'*8}  {'-'*10}")
    for pen in IBR_LEVELS:
        sub = [s for s in scenarios if abs(s.ibr_penetration - pen) < 0.01]
        if not sub:
            continue
        mean_d     = np.mean([s.total_depth    for s in sub])
        mean_m     = np.mean([s.total_misops   for s in sub])
        pct_stable = 100*sum(1 for s in sub if s.terminated_by=='stable')/len(sub)
        pct_sev    = 100*sum(1 for s in sub
                             if s.terminated_by in ('island','blackout'))/len(sub)
        print(f"  {pen:>7.0%}  {mean_d:>10.2f}  "
              f"{mean_m:>12.2f}  {pct_stable:>7.1f}%  {pct_sev:>9.1f}%")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='TR-88 cascade runner')
    parser.add_argument('--n',     type=int, default=N_SCENARIOS_DEFAULT)
    parser.add_argument('--seed',  type=int, default=42)
    parser.add_argument('--figures-only', action='store_true')
    args = parser.parse_args()

    if args.figures_only:
        data = np.load(_RESULTS / 'tr88_cascade_results.npz', allow_pickle=True)
        # Reconstruct minimal scenario objects for figures
        from models.cascade_engine import CascadeScenario, CascadeStep
        scenarios = []
        for i in range(len(data['contingency_id'])):
            sc = CascadeScenario(
                contingency_id  = int(data['contingency_id'][i]),
                line_a          = int(data['line_a'][i]),
                line_b          = int(data['line_b'][i]),
                ibr_penetration = float(data['ibr_pen'][i]),
                f_ibr           = float(data['ibr_pen'][i]),
                total_depth     = int(data['total_depth'][i]),
                total_misops    = int(data['total_misops'][i]),
                total_lines_lost= int(data['total_lines_lost'][i]),
                total_buses_lost= int(data['total_buses_lost'][i]),
                terminated_by   = str(data['terminated_by'][i]),
            )
            # Reconstruct steps from depth misops
            for d in range(sc.total_depth + 1):
                sc.steps.append(CascadeStep(depth=d, tripped_lines=[],
                                             overloaded_lines=[]))
            scenarios.append(sc)
        generate_figures(scenarios)
    else:
        scenarios = run_all(n=args.n, seed=args.seed)
        print_summary(scenarios)
        save_results(scenarios)
        generate_figures(scenarios)
        print("TR-88 complete.")
