# =============================================================================
# sambp / sambp_sync_oc
# main_batch_study.py
#
# Run all study cases defined in config/study_cases.py and aggregate results.
#
# Usage
# -----
#   python main_batch_study.py                # run all STUDY_CASES
#   python main_batch_study.py --no-plots     # skip individual case plots
#   python main_batch_study.py --cases 0 2   # run only cases at index 0 and 2
#
# Outputs
# -------
#   outputs/tables/batch_summary.csv          — aggregated result table
#   outputs/plots/batch_comparison.png        — trip time comparison bar chart
#   outputs/plots/batch_confidence.png        — confidence score bar chart
#   outputs/logs/<case>_*.log                 — per-case logs (from run_case)
# =============================================================================

import argparse
import os
import sys
import traceback

from config.study_cases   import STUDY_CASES
from main_run_case        import run_case
from evaluation.comparison import summarise_batch
from evaluation.reporting  import save_case_summary_csv, print_batch_summary


# ===========================================================================
# Batch runner
# ===========================================================================

def run_batch(case_indices=None, save_plots=True):
    """
    Run selected cases and aggregate results.

    Parameters
    ----------
    case_indices : list[int] or None — indices into STUDY_CASES.
                   None runs all cases.
    save_plots   : bool — generate per-case plots (passed to run_case)

    Returns
    -------
    list[dict] — one case_result dict per completed case
    """
    if case_indices is None:
        case_indices = list(range(len(STUDY_CASES)))

    selected = [STUDY_CASES[i] for i in case_indices]
    results  = []
    failed   = []

    print(f"\n{'='*60}")
    print(f"  sambp_sync_oc — Batch Study")
    print(f"  Cases to run: {[c['case_name'] for c in selected]}")
    print(f"{'='*60}\n")

    for i, case in zip(case_indices, selected):
        print(f"\n--- Running case [{i}]: {case['case_name']} ---")
        try:
            result = run_case(case, save_plots=save_plots)
            results.append(result)
        except Exception as e:
            print(f"[ERROR] Case '{case['case_name']}' failed: {e}")
            traceback.print_exc()
            failed.append(case["case_name"])

    print(f"\n{'='*60}")
    print(f"  Completed: {len(results)} / {len(selected)} cases")
    if failed:
        print(f"  Failed   : {failed}")
    print(f"{'='*60}\n")

    return results


# ===========================================================================
# Aggregation
# ===========================================================================

def aggregate_and_save(results):
    """
    Aggregate case results, print batch summary table, and save outputs.

    Parameters
    ----------
    results : list[dict] — from run_batch()
    """
    if not results:
        print("No results to aggregate.")
        return

    summaries = summarise_batch(results)

    # --- Console table ---
    print_batch_summary(summaries)

    # --- Batch summary CSV ---
    csv_path = os.path.join("outputs", "tables", "batch_summary.csv")
    save_case_summary_csv(summaries, csv_path)
    print(f"Batch summary → {csv_path}")

    # --- Comparison plots ---
    _save_batch_plots(summaries)


# ===========================================================================
# Batch comparison plots
# ===========================================================================

def _save_batch_plots(summaries):
    """Generate trip time and confidence bar charts for the batch."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping batch plots")
        return

    plot_dir = os.path.join("outputs", "plots")
    os.makedirs(plot_dir, exist_ok=True)

    names  = [s["case_name"]          for s in summaries]
    t_fix  = [s.get("fixed_trip_time",    None) for s in summaries]
    t_adp  = [s.get("adaptive_trip_time", None) for s in summaries]
    gammas = [s.get("confidence",         0.0)  for s in summaries]
    x      = range(len(names))
    w      = 0.35

    # --- Trip time comparison ---
    fig, ax = plt.subplots(figsize=(max(7, len(names) * 2), 4))

    t_fix_ms = [v * 1000 if v is not None else 0.0 for v in t_fix]
    t_adp_ms = [v * 1000 if v is not None else 0.0 for v in t_adp]

    bars_f = ax.bar([i - w/2 for i in x], t_fix_ms, w, label="Fixed",    color="steelblue")
    bars_a = ax.bar([i + w/2 for i in x], t_adp_ms, w, label="Adaptive", color="darkorange")

    ax.set_xticks(list(x))
    ax.set_xticklabels(names, rotation=15, ha="right", fontsize=8)
    ax.set_ylabel("Trip time (ms)")
    ax.set_title("Fixed vs Adaptive trip time — batch comparison")
    ax.legend(fontsize=8)
    ax.grid(axis="y", lw=0.4)

    # Annotate bars
    for bar in list(bars_f) + list(bars_a):
        h = bar.get_height()
        if h > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, h + 1,
                    f"{h:.1f}", ha="center", va="bottom", fontsize=7)

    # Mark "no trip"
    for i, (f, a) in enumerate(zip(t_fix, t_adp)):
        if f is None:
            ax.text(i - w/2, 2, "NT", ha="center", va="bottom",
                    fontsize=7, color="red")
        if a is None:
            ax.text(i + w/2, 2, "NT", ha="center", va="bottom",
                    fontsize=7, color="red")

    fig.tight_layout()
    trip_fig = os.path.join(plot_dir, "batch_comparison.png")
    fig.savefig(trip_fig, dpi=150)
    plt.close(fig)
    print(f"Trip comparison plot → {trip_fig}")

    # --- Confidence score bar chart ---
    fig, ax = plt.subplots(figsize=(max(7, len(names) * 2), 3))
    colors  = ["seagreen" if g >= 0.7 else "tomato" for g in gammas]
    ax.bar(list(x), gammas, color=colors)
    ax.axhline(0.7, color="gray", ls="--", lw=1.0, label="threshold = 0.7")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, rotation=15, ha="right", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Confidence γ")
    ax.set_title("Confidence score per case")
    ax.legend(fontsize=8)
    ax.grid(axis="y", lw=0.4)
    for i, g in enumerate(gammas):
        ax.text(i, g + 0.02, f"{g:.2f}", ha="center", va="bottom", fontsize=7)

    fig.tight_layout()
    conf_fig = os.path.join(plot_dir, "batch_confidence.png")
    fig.savefig(conf_fig, dpi=150)
    plt.close(fig)
    print(f"Confidence plot      → {conf_fig}")


# ===========================================================================
# CLI entry point
# ===========================================================================

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Run batch of sambp_sync_oc study cases."
    )
    parser.add_argument(
        "--cases", nargs="+", type=int, default=None,
        metavar="IDX",
        help="Case indices to run (default: all). E.g. --cases 0 2"
    )
    parser.add_argument(
        "--no-plots", action="store_true",
        help="Skip per-case waveform/relay plots"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args    = _parse_args()
    results = run_batch(
        case_indices = args.cases,
        save_plots   = not args.no_plots,
    )
    aggregate_and_save(results)
