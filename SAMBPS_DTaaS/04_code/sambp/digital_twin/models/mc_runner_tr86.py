#!/usr/bin/env python3
# =============================================================================
# sambp / digital_twin / models / mc_runner_tr86.py
#
# TR-86  IEEE 118-bus Large-Scale Monte Carlo
# N = 50,000 trials  |  Latin Hypercube Sampling  |  multiprocessing
#
# Hypothesis H1: SAMBP 87L agree-rate >= 97% for IBR penetration <= 50%
# Hypothesis H2: All-element agree-rate >= 90% for full IBR fleet (100%)
#
# Usage
# -----
#   python mc_runner_tr86.py              # full 50 000 trials
#   python mc_runner_tr86.py --n 500      # quick smoke-test
#   python mc_runner_tr86.py --n 5000 --workers 4
#
# Output
# ------
#   results/tr86_mc_results.npz      — raw arrays
#   reports/figures/TR86/            — 5 publication figures (PDF + PNG)
# =============================================================================

from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ── Path setup ────────────────────────────────────────────────────────────────
_DT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_DT_ROOT))

from models.ieee118_network import IEEE118Config, IEEE118Network, FaultState118
from models.mc_scenario_generator import MCScenarioGenerator, MC86Scenario
from models.sambp_protection_stack import SAMBPStack86

# ── Output directories ────────────────────────────────────────────────────────
_RESULTS_DIR = _DT_ROOT / "results"
_FIGURES_DIR = _DT_ROOT / "reports" / "figures" / "TR86"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
_FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
ELEMENTS        = ['87L', '21', '46', '51', '67']
IBR_PEN_VALS    = [0.0, 0.30, 0.50, 1.00]
FAULT_TYPES     = ['3PH', 'SLG', 'DLG', 'LL']
H1_THRESHOLD    = 0.97   # 97% agree for <=50% IBR penetration (87L)
H2_THRESHOLD    = 0.90   # 90% all-element agree for 100% IBR


# =============================================================================
# Worker function — runs in subprocess
# =============================================================================

def _worker_init():
    """Suppress warnings in worker processes."""
    warnings.filterwarnings("ignore")


def _evaluate_batch(args: Tuple[List[MC86Scenario], int]) -> List[dict]:
    """
    Evaluate one batch of scenarios.  Called in a worker process.
    Returns list of result dicts (one per scenario × element).
    """
    scenarios, worker_id = args
    # Build network cache keyed by (ibr_pen, ibr_mode) to avoid re-building
    # the same IEEE118Network for every scenario.
    net_cache: Dict[Tuple[float, str], IEEE118Network] = {}
    stack = SAMBPStack86()
    results = []

    for sc in scenarios:
        key = (sc.ibr_penetration, sc.ibr_mode)
        if key not in net_cache:
            cfg = IEEE118Config(
                ibr_penetration=sc.ibr_penetration,
                ibr_mode=sc.ibr_mode,
                load_level=sc.load_level,
            )
            net_cache[key] = IEEE118Network.from_config(cfg)

        net = net_cache[key]
        # Update load level (only changes load, not topology)
        net.cfg.load_level = sc.load_level

        try:
            fs = net.inject_fault(
                bus_idx=sc.bus_idx,
                fault_type=sc.fault_type,
                R_f_ohm=sc.R_f_ohm,
                scenario_id=sc.scenario_id,
            )
            decisions = stack.evaluate(fs)
            net.clear_fault()

            for d in decisions:
                results.append({
                    'scenario_id':     sc.scenario_id,
                    'element':         d.element,
                    'verdict':         d.verdict,
                    'operate_time_ms': d.operate_time_ms,
                    'confidence':      d.confidence,
                    'ibr_pen':         sc.ibr_penetration,
                    'ibr_mode':        sc.ibr_mode,
                    'fault_type':      sc.fault_type,
                    'bus_idx':         sc.bus_idx,
                    'R_f_ohm':         sc.R_f_ohm,
                    'load_level':      sc.load_level,
                    'k_ibr':           fs.k_ibr,
                    'f_gfm':           fs.f_gfm,
                    'I_pos_pu':        fs.I_pos_pu,
                    'V_pos_pu':        fs.V_pos_pu,
                    'zone':            fs.protection_zone,
                })

        except Exception as exc:
            # Log fault but don't crash the worker
            for elem in ELEMENTS:
                results.append({
                    'scenario_id':     sc.scenario_id,
                    'element':         elem,
                    'verdict':         'ERROR',
                    'operate_time_ms': 9999.0,
                    'confidence':      0.0,
                    'ibr_pen':         sc.ibr_penetration,
                    'ibr_mode':        sc.ibr_mode,
                    'fault_type':      sc.fault_type,
                    'bus_idx':         sc.bus_idx,
                    'R_f_ohm':         sc.R_f_ohm,
                    'load_level':      sc.load_level,
                    'k_ibr':           0.0,
                    'f_gfm':           0.0,
                    'I_pos_pu':        0.0,
                    'V_pos_pu':        1.0,
                    'zone':            'none',
                })

    return results


# =============================================================================
# Main runner
# =============================================================================

def run_monte_carlo(n_scenarios: int = 50_000,
                    n_workers:   int = 4,
                    seed:        int = 42) -> dict:
    """
    Run the full Monte Carlo study.

    Returns
    -------
    dict with keys:
        raw_results  — list of result dicts
        agree_by_element  — {element: agree_rate}
        agree_by_pen      — {pen_val: {element: agree_rate}}
        agree_by_fault    — {fault_type: {element: agree_rate}}
        op_times          — {element: np.ndarray of operate times (TRIP only)}
    """
    print(f"\n{'='*64}")
    print(f"  TR-86 IEEE 118-bus Monte Carlo  |  N = {n_scenarios:,}")
    print(f"  Workers: {n_workers}  |  Seed: {seed}")
    print(f"{'='*64}\n")

    t0 = time.time()

    # ── Generate LHS scenarios ────────────────────────────────────────
    print("[1/4] Generating LHS scenarios...", flush=True)
    gen = MCScenarioGenerator(n_scenarios=n_scenarios, seed=seed)
    scenarios = gen.generate()
    print(f"      {len(scenarios):,} scenarios generated.")

    # ── Split into batches ────────────────────────────────────────────
    batch_size = max(50, n_scenarios // (n_workers * 4))
    batches = [
        (scenarios[i:i + batch_size], w % n_workers)
        for w, i in enumerate(range(0, len(scenarios), batch_size))
    ]
    print(f"[2/4] Running {len(batches)} batches "
          f"(batch_size={batch_size}) across {n_workers} workers...", flush=True)

    # ── Parallel execution ────────────────────────────────────────────
    all_results: List[dict] = []
    with mp.Pool(processes=n_workers, initializer=_worker_init) as pool:
        done = 0
        for batch_results in pool.imap_unordered(_evaluate_batch, batches):
            all_results.extend(batch_results)
            done += 1
            pct = 100.0 * done / len(batches)
            n_scen_done = len([r for r in all_results
                               if r['element'] == '87L'])
            print(f"      {pct:5.1f}%  |  {n_scen_done:,}/{n_scenarios:,} "
                  f"scenarios  |  {time.time()-t0:.0f}s elapsed",
                  end='\r', flush=True)
    print()

    elapsed = time.time() - t0
    print(f"[3/4] Aggregating {len(all_results):,} decisions "
          f"({elapsed:.1f}s elapsed)...", flush=True)

    # ── Aggregate ─────────────────────────────────────────────────────
    # Filter valid (non-ERROR) results
    valid = [r for r in all_results if r['verdict'] != 'ERROR']
    n_valid = len([r for r in valid if r['element'] == '87L'])
    n_errors = n_scenarios - n_valid
    if n_errors > 0:
        print(f"      WARNING: {n_errors} scenarios failed (excluded from stats)")

    def agree_rate(subset: List[dict]) -> float:
        if not subset:
            return 0.0
        trips = sum(1 for r in subset if r['verdict'] == 'TRIP')
        return trips / len(subset)

    # Overall per-element agree rate
    agree_by_element = {}
    for elem in ELEMENTS:
        sub = [r for r in valid if r['element'] == elem]
        agree_by_element[elem] = agree_rate(sub)

    # Per-penetration per-element agree rate
    agree_by_pen = {}
    for pen in IBR_PEN_VALS:
        agree_by_pen[pen] = {}
        for elem in ELEMENTS:
            sub = [r for r in valid
                   if r['element'] == elem
                   and abs(r['ibr_pen'] - pen) < 0.01]
            agree_by_pen[pen][elem] = agree_rate(sub)

    # Per-fault-type per-element agree rate
    agree_by_fault = {}
    for ft in FAULT_TYPES:
        agree_by_fault[ft] = {}
        for elem in ELEMENTS:
            sub = [r for r in valid
                   if r['element'] == elem and r['fault_type'] == ft]
            agree_by_fault[ft][elem] = agree_rate(sub)

    # Operate times (TRIP only)
    op_times = {}
    for elem in ELEMENTS:
        times = [r['operate_time_ms'] for r in valid
                 if r['element'] == elem and r['verdict'] == 'TRIP']
        op_times[elem] = np.array(times) if times else np.array([])

    # ── Hypothesis tests ──────────────────────────────────────────────
    print("\n[4/4] Hypothesis tests:")
    # H1: 87L agree >= 97% for IBR pen <= 50%
    h1_rates = [agree_by_pen[p]['87L']
                for p in [0.0, 0.30, 0.50]]
    h1_pass = all(r >= H1_THRESHOLD for r in h1_rates)
    print(f"  H1 (87L >= {H1_THRESHOLD:.0%} for pen <= 50%):")
    for p, r in zip([0.0, 0.30, 0.50], h1_rates):
        flag = "✓ PASS" if r >= H1_THRESHOLD else "✗ FAIL"
        print(f"     pen={p:.0%}  →  87L agree = {r:.2%}  {flag}")
    print(f"  H1 overall: {'PASS ✓' if h1_pass else 'FAIL ✗'}")

    # H2: All-element agree >= 90% at 100% IBR
    h2_rates = agree_by_pen[1.0]
    h2_pass = all(r >= H2_THRESHOLD for r in h2_rates.values())
    print(f"\n  H2 (all elements >= {H2_THRESHOLD:.0%} at 100% IBR):")
    for elem, r in h2_rates.items():
        flag = "✓ PASS" if r >= H2_THRESHOLD else "✗ FAIL"
        print(f"     {elem:3s}  →  agree = {r:.2%}  {flag}")
    print(f"  H2 overall: {'PASS ✓' if h2_pass else 'FAIL ✗'}")

    print(f"\n{'='*64}")
    print(f"  Total wall time: {elapsed:.1f}s  |  "
          f"Throughput: {n_scenarios/elapsed:.0f} scenarios/s")
    print(f"{'='*64}\n")

    return {
        'raw_results':       all_results,
        'agree_by_element':  agree_by_element,
        'agree_by_pen':      agree_by_pen,
        'agree_by_fault':    agree_by_fault,
        'op_times':          op_times,
        'n_scenarios':       n_scenarios,
        'n_valid':           n_valid,
        'n_errors':          n_errors,
        'elapsed_s':         elapsed,
        'h1_pass':           h1_pass,
        'h2_pass':           h2_pass,
        'h1_rates':          dict(zip([0.0, 0.30, 0.50], h1_rates)),
        'h2_rates':          h2_rates,
    }


def save_results(res: dict) -> None:
    """Save raw results arrays to NPZ for reproducibility."""
    valid = [r for r in res['raw_results'] if r['verdict'] != 'ERROR']
    if not valid:
        return
    np.savez_compressed(
        _RESULTS_DIR / "tr86_mc_results.npz",
        scenario_id    = np.array([r['scenario_id']     for r in valid], dtype=np.int32),
        element        = np.array([r['element']          for r in valid]),
        verdict        = np.array([r['verdict']          for r in valid]),
        operate_time   = np.array([r['operate_time_ms']  for r in valid], dtype=np.float32),
        confidence     = np.array([r['confidence']       for r in valid], dtype=np.float32),
        ibr_pen        = np.array([r['ibr_pen']          for r in valid], dtype=np.float32),
        ibr_mode       = np.array([r['ibr_mode']         for r in valid]),
        fault_type     = np.array([r['fault_type']       for r in valid]),
        k_ibr          = np.array([r['k_ibr']            for r in valid], dtype=np.float32),
        f_gfm          = np.array([r['f_gfm']            for r in valid], dtype=np.float32),
        I_pos_pu       = np.array([r['I_pos_pu']         for r in valid], dtype=np.float32),
        V_pos_pu       = np.array([r['V_pos_pu']         for r in valid], dtype=np.float32),
        zone           = np.array([r['zone']             for r in valid]),
    )
    print(f"  Results saved → {_RESULTS_DIR / 'tr86_mc_results.npz'}")


# =============================================================================
# Figure generation
# =============================================================================

def generate_figures(res: dict) -> None:
    """Generate 5 publication-quality figures for TR-86."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    plt.rcParams.update({
        'font.family':      'serif',
        'font.size':        10,
        'axes.labelsize':   11,
        'axes.titlesize':   12,
        'legend.fontsize':  9,
        'figure.dpi':       150,
        'savefig.dpi':      300,
        'savefig.bbox':     'tight',
    })

    COLORS = {
        '87L': '#1f77b4',
        '21':  '#ff7f0e',
        '46':  '#2ca02c',
        '51':  '#d62728',
        '67':  '#9467bd',
    }
    PEN_LABELS = {0.0: '0%', 0.30: '30%', 0.50: '50%', 1.00: '100%'}

    # ── Fig 1: Agree rate per protection element (overall) ────────────
    fig, ax = plt.subplots(figsize=(7, 4))
    elems = ELEMENTS
    rates = [res['agree_by_element'][e] * 100 for e in elems]
    bars  = ax.bar(elems, rates,
                   color=[COLORS[e] for e in elems],
                   edgecolor='black', linewidth=0.6, width=0.55)
    ax.axhline(97, color='red', linestyle='--', linewidth=1.2,
               label='H1 threshold (97%)')
    ax.axhline(90, color='orange', linestyle=':', linewidth=1.2,
               label='H2 threshold (90%)')
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.4,
                f'{rate:.1f}%', ha='center', va='bottom', fontsize=9)
    ax.set_ylim(80, 102)
    ax.set_ylabel('TRIP agree-rate [%]')
    ax.set_xlabel('Protection element')
    ax.set_title(f'SAMBP TRIP agree-rate per protection element\n'
                 f'IEEE 118-bus, N = {res["n_scenarios"]:,} LHS trials')
    ax.legend(loc='lower right')
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(1))
    ax.grid(axis='y', linestyle=':', alpha=0.5)
    _save_fig(fig, 'fig1_agree_per_function')

    # ── Fig 2: Agree rate vs IBR penetration (87L highlighted) ───────
    fig, ax = plt.subplots(figsize=(7, 4.5))
    pen_vals = IBR_PEN_VALS
    pen_pct  = [p * 100 for p in pen_vals]
    for elem in ELEMENTS:
        rates = [res['agree_by_pen'][p][elem] * 100 for p in pen_vals]
        lw = 2.5 if elem == '87L' else 1.2
        ls = '-'  if elem == '87L' else '--'
        ax.plot(pen_pct, rates, marker='o', linewidth=lw, linestyle=ls,
                color=COLORS[elem], label=elem, markersize=5)

    ax.axhline(97, color='red', linestyle='--', linewidth=1.0,
               label='H1 = 97%', zorder=1)
    ax.axvline(50, color='gray', linestyle=':', linewidth=1.0,
               label='H1 boundary (50% pen)', zorder=1)
    ax.fill_betweenx([80, 102], 0, 50, alpha=0.05, color='green',
                     label='H1 region')
    ax.set_xlim(-5, 105)
    ax.set_ylim(80, 102)
    ax.set_xticks([0, 30, 50, 100])
    ax.set_xticklabels(['0%', '30%', '50%', '100%'])
    ax.set_xlabel('IBR penetration [%]')
    ax.set_ylabel('TRIP agree-rate [%]')
    ax.set_title(f'Agree-rate vs IBR penetration\n'
                 f'IEEE 118-bus, N = {res["n_scenarios"]:,} LHS trials')
    ax.legend(loc='lower left', ncol=2)
    ax.grid(linestyle=':', alpha=0.4)
    _save_fig(fig, 'fig2_agree_vs_penetration')

    # ── Fig 3: Agree rate by fault type (grouped bar) ────────────────
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ft_labels = FAULT_TYPES
    x = np.arange(len(ft_labels))
    width = 0.15
    for i, elem in enumerate(ELEMENTS):
        rates = [res['agree_by_fault'][ft][elem] * 100 for ft in ft_labels]
        offset = (i - 2) * width
        ax.bar(x + offset, rates, width, label=elem,
               color=COLORS[elem], edgecolor='black', linewidth=0.4)
    ax.axhline(97, color='red', linestyle='--', linewidth=1.0,
               label='97% threshold')
    ax.set_xticks(x)
    ax.set_xticklabels(['3PH\n(3-phase)', 'SLG\n(single-line)',
                        'DLG\n(double-line-gnd)', 'LL\n(line-line)'])
    ax.set_ylim(70, 102)
    ax.set_ylabel('TRIP agree-rate [%]')
    ax.set_title(f'Agree-rate by fault type and protection element\n'
                 f'IEEE 118-bus, N = {res["n_scenarios"]:,} LHS trials')
    ax.legend(ncol=5, loc='lower right', fontsize=8)
    ax.grid(axis='y', linestyle=':', alpha=0.4)
    _save_fig(fig, 'fig3_agree_by_fault_type')

    # ── Fig 4: 2-D heatmap — element × penetration ───────────────────
    fig, ax = plt.subplots(figsize=(6, 3.5))
    matrix = np.array([
        [res['agree_by_pen'][p][elem] for p in IBR_PEN_VALS]
        for elem in ELEMENTS
    ]) * 100

    im = ax.imshow(matrix, vmin=80, vmax=100, cmap='RdYlGn', aspect='auto')
    fig.colorbar(im, ax=ax, label='Agree-rate [%]')
    ax.set_xticks(range(len(IBR_PEN_VALS)))
    ax.set_xticklabels(['0%', '30%', '50%', '100%'])
    ax.set_yticks(range(len(ELEMENTS)))
    ax.set_yticklabels(ELEMENTS)
    ax.set_xlabel('IBR penetration')
    ax.set_ylabel('Protection element')
    ax.set_title('Agree-rate heatmap: element × IBR penetration')
    # Annotate cells
    for i in range(len(ELEMENTS)):
        for j in range(len(IBR_PEN_VALS)):
            val = matrix[i, j]
            color = 'white' if val < 88 else 'black'
            ax.text(j, i, f'{val:.1f}%', ha='center', va='center',
                    fontsize=8.5, color=color, fontweight='bold')
    _save_fig(fig, 'fig4_heatmap_21')

    # ── Fig 5: Operate time CDFs (TRIP-only) ─────────────────────────
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for elem in ELEMENTS:
        times = res['op_times'][elem]
        times = times[times < 5000]   # exclude restrain placeholders
        if len(times) == 0:
            continue
        sorted_t = np.sort(times)
        cdf = np.arange(1, len(sorted_t) + 1) / len(sorted_t)
        ax.plot(sorted_t, cdf * 100, linewidth=1.8,
                color=COLORS[elem], label=elem)
    ax.axvline(100,  color='gray', linestyle=':', linewidth=1.0,
               label='100 ms reference')
    ax.axvline(400,  color='gray', linestyle='--', linewidth=1.0,
               label='400 ms (Zone-2)')
    ax.set_xlim(0, 1000)
    ax.set_ylim(0, 102)
    ax.set_xlabel('Operate time [ms]')
    ax.set_ylabel('Cumulative % of TRIP decisions')
    ax.set_title(f'Operate-time CDF (TRIP decisions only)\n'
                 f'IEEE 118-bus, N = {res["n_scenarios"]:,} LHS trials')
    ax.legend(loc='lower right')
    ax.grid(linestyle=':', alpha=0.4)
    _save_fig(fig, 'fig5_operate_times')

    print(f"  All 5 figures saved → {_FIGURES_DIR}/")


def _save_fig(fig, name: str) -> None:
    for ext in ('pdf', 'png'):
        fig.savefig(_FIGURES_DIR / f'{name}.{ext}')
    import matplotlib.pyplot as plt
    plt.close(fig)


# =============================================================================
# Entry point
# =============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='TR-86 IEEE 118-bus Monte Carlo runner')
    parser.add_argument('--n',       type=int, default=50_000,
                        help='Number of LHS scenarios (default: 50000)')
    parser.add_argument('--workers', type=int,
                        default=max(1, mp.cpu_count() - 1),
                        help='Number of worker processes')
    parser.add_argument('--seed',    type=int, default=42)
    parser.add_argument('--figures-only', action='store_true',
                        help='Reload saved results and regenerate figures only')
    args = parser.parse_args()

    if args.figures_only:
        data = np.load(_RESULTS_DIR / 'tr86_mc_results.npz', allow_pickle=True)
        print("Reloaded saved results — regenerating figures only.")
        # Reconstruct summary dicts from NPZ
        valid_87L = data['element'] == '87L'
        agree_by_element = {}
        for elem in ELEMENTS:
            mask = data['element'] == elem
            agree_by_element[elem] = (data['verdict'][mask] == 'TRIP').mean()
        agree_by_pen = {}
        for pen in IBR_PEN_VALS:
            agree_by_pen[pen] = {}
            for elem in ELEMENTS:
                mask = (data['element'] == elem) & (np.abs(data['ibr_pen'] - pen) < 0.01)
                agree_by_pen[pen][elem] = ((data['verdict'][mask] == 'TRIP').mean()
                                           if mask.sum() > 0 else 0.0)
        agree_by_fault = {}
        for ft in FAULT_TYPES:
            agree_by_fault[ft] = {}
            for elem in ELEMENTS:
                mask = (data['element'] == elem) & (data['fault_type'] == ft)
                agree_by_fault[ft][elem] = ((data['verdict'][mask] == 'TRIP').mean()
                                            if mask.sum() > 0 else 0.0)
        op_times = {}
        for elem in ELEMENTS:
            mask = (data['element'] == elem) & (data['verdict'] == 'TRIP')
            op_times[elem] = data['operate_time'][mask].astype(float)

        res = {
            'agree_by_element': agree_by_element,
            'agree_by_pen':     agree_by_pen,
            'agree_by_fault':   agree_by_fault,
            'op_times':         op_times,
            'n_scenarios':      int(valid_87L.sum()),
            'h1_rates':         {p: agree_by_pen[p]['87L'] for p in [0.0, 0.30, 0.50]},
            'h2_rates':         agree_by_pen[1.0],
        }
        generate_figures(res)
    else:
        res = run_monte_carlo(
            n_scenarios=args.n,
            n_workers=args.workers,
            seed=args.seed,
        )
        save_results(res)
        generate_figures(res)
        print("TR-86 Monte Carlo complete.")
