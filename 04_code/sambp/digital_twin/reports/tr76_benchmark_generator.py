#!/usr/bin/env python3
# =============================================================================
# sambp / digital_twin / reports / tr76_benchmark_generator.py
#
# TR-76 Benchmark Report Generator — WP 76.4
#
# Replays all 50 synthetic COMTRADE field records through the DT Replay Engine
# and produces:
#   - 5 matplotlib figures saved to reports/figures/TR76/
#   - LaTeX table snippets saved to reports/TR76_tables.tex
#   - Plain-text benchmark summary saved to reports/TR76_benchmark_summary.txt
#
# Usage (from digital_twin/ root):
#   python reports/tr76_benchmark_generator.py
#   python reports/tr76_benchmark_generator.py --no-plots   # skip matplotlib
#
# Dependencies: numpy, matplotlib, pyyaml (all standard in SAMBP environment)
# =============================================================================

from __future__ import annotations

import argparse
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import numpy as np

# Ensure digital_twin package root is importable
_DT_ROOT = Path(__file__).resolve().parent.parent   # digital_twin/
if str(_DT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_DT_ROOT.parent))        # 04_code/sambp/

from digital_twin import DTEngine
from digital_twin.validation.comtrade_parser import ComtradeParser
from digital_twin.validation.field_comparator import (
    BatchComparisonReport,
    FieldComparator,
    FieldComparisonReport,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPORT_DIR  = Path(__file__).resolve().parent          # reports/
_FIG_DIR     = _REPORT_DIR / "figures" / "TR76"
_INDEX_YAML  = _DT_ROOT / "data" / "field_records" / "record_index.yaml"
_TABLE_TEX   = _REPORT_DIR / "TR76_tables.tex"
_SUMMARY_TXT = _REPORT_DIR / "TR76_benchmark_summary.txt"


# ---------------------------------------------------------------------------
# Colours / style constants (IEEE-friendly, colorblind-safe)
# ---------------------------------------------------------------------------

_BLUE   = "#2166AC"
_GREEN  = "#1B7837"
_AMBER  = "#D6604D"
_GREY   = "#969696"
_LIGHT  = "#F7F7F7"

_FAULT_ORDER = ["SLG", "LL", "DLG", "3PH", "evolving_SLG_to_DLG", "cross_country"]
_IBR_ORDER   = ["SG", "DFIG", "GFM", "GFL", "PV", "BESS"]


# ---------------------------------------------------------------------------
# Helper: run batch
# ---------------------------------------------------------------------------

def run_batch() -> BatchComparisonReport:
    engine = DTEngine(estimator="ekf", n_scenarios=500)
    parser = ComtradeParser()
    fc     = FieldComparator(engine, parser)

    print(f"  Index    : {_INDEX_YAML}")
    print(f"  Base dir : {_DT_ROOT}")
    batch = fc.replay_batch(str(_INDEX_YAML), base_dir=str(_DT_ROOT))
    batch.print_summary()
    return batch


# ---------------------------------------------------------------------------
# Figure 1 — Confusion matrix (DT decision × Field decision)
# ---------------------------------------------------------------------------

def _fig_confusion(batch: BatchComparisonReport, show: bool) -> Path:
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    # Build 2×2 matrix: rows = field (TRIP / BLOCK), cols = DT (TRIP / BLOCK)
    counts = np.zeros((2, 2), dtype=int)
    for r in batch.reports:
        fi = 0 if r.field_decision == "TRIP" else 1
        di = 0 if r.dt_decision in ("AGREE", "FLAG_ELEMENT", "FLAG_CONF") else 1
        # DT predicts TRIP for AGREE, FP, ELEMENT, CONF; BLOCK only for FN
        # Re-derive: field TRIP + DT AGREE → true positive; etc.
        # Simpler: DT "trip" when verdict != FLAG_FN
        #          DT "block" when verdict == FLAG_FN
        di_trip = r.dt_decision != "FLAG_FN"
        di = 0 if di_trip else 1
        counts[fi, di] += 1

    labels = ["TRIP", "BLOCK"]
    fig, ax = plt.subplots(figsize=(4.0, 3.6))

    im = ax.imshow(counts, cmap="Blues", vmin=0, vmax=batch.total_records)
    for i in range(2):
        for j in range(2):
            c = counts[i, j]
            colour = "white" if c > batch.total_records * 0.4 else "black"
            ax.text(j, i, str(c), ha="center", va="center",
                    fontsize=14, fontweight="bold", color=colour)

    ax.set_xticks([0, 1]); ax.set_xticklabels(["DT: TRIP", "DT: BLOCK"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["Field: TRIP", "Field: BLOCK"])
    ax.set_title("DT vs Field Decision\n(N = {})".format(batch.total_records),
                 fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()

    fpath = _FIG_DIR / "fig_confusion_matrix.pdf"
    fig.savefig(fpath, bbox_inches="tight")
    print(f"    saved: {fpath.name}")
    plt.close(fig)
    return fpath


# ---------------------------------------------------------------------------
# Figure 2 — Per-fault-type AGREE rate bar chart
# ---------------------------------------------------------------------------

def _fig_per_fault(batch: BatchComparisonReport, show: bool) -> Path:
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [ft for ft in _FAULT_ORDER if ft in batch.per_fault_type]
    values = [batch.per_fault_type[ft] * 100 for ft in labels]
    # Shorten labels for display
    short  = {"evolving_SLG_to_DLG": "SLG→DLG", "cross_country": "X-cntry"}
    disp   = [short.get(l, l) for l in labels]
    counts = defaultdict(int)
    for r in batch.reports:
        counts[r.fault_type] += 1
    ns = [counts[ft] for ft in labels]

    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    bars = ax.bar(disp, values, color=_BLUE, edgecolor="white", linewidth=0.5)
    ax.axhline(100, color=_GREY, linestyle="--", linewidth=0.8)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Agreement rate [%]", fontsize=9)
    ax.set_xlabel("Fault type", fontsize=9)
    ax.set_title("DT Agreement Rate by Fault Type", fontsize=10)
    for bar, v, n in zip(bars, values, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 1,
                f"{v:.0f}%\n(N={n})", ha="center", va="bottom", fontsize=7.5)
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()

    fpath = _FIG_DIR / "fig_agree_by_fault.pdf"
    fig.savefig(fpath, bbox_inches="tight")
    print(f"    saved: {fpath.name}")
    plt.close(fig)
    return fpath


# ---------------------------------------------------------------------------
# Figure 3 — Per-IBR-type AGREE rate bar chart
# ---------------------------------------------------------------------------

def _fig_per_ibr(batch: BatchComparisonReport, show: bool) -> Path:
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [it for it in _IBR_ORDER if it in batch.per_ibr_type]
    values = [batch.per_ibr_type[it] * 100 for it in labels]
    counts = defaultdict(int)
    for r in batch.reports:
        counts[r.ibr_type] += 1
    ns = [counts[it] for it in labels]

    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    bars = ax.bar(labels, values, color=_GREEN, edgecolor="white", linewidth=0.5)
    ax.axhline(100, color=_GREY, linestyle="--", linewidth=0.8)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Agreement rate [%]", fontsize=9)
    ax.set_xlabel("IBR type", fontsize=9)
    ax.set_title("DT Agreement Rate by IBR Type", fontsize=10)
    for bar, v, n in zip(bars, values, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 1,
                f"{v:.0f}%\n(N={n})", ha="center", va="bottom", fontsize=7.5)
    ax.tick_params(axis="x", labelsize=9)
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()

    fpath = _FIG_DIR / "fig_agree_by_ibr.pdf"
    fig.savefig(fpath, bbox_inches="tight")
    print(f"    saved: {fpath.name}")
    plt.close(fig)
    return fpath


# ---------------------------------------------------------------------------
# Figure 4 — Trip time error histogram
# ---------------------------------------------------------------------------

def _fig_trip_time_error(batch: BatchComparisonReport, show: bool) -> Path:
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    errors = [r.time_error_ms for r in batch.reports if r.time_error_ms is not None]

    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    if errors:
        ax.hist(errors, bins=12, color=_AMBER, edgecolor="white", linewidth=0.5)
        ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
        mean_e = float(np.mean(errors))
        ax.axvline(mean_e, color=_BLUE, linewidth=1.2, linestyle=":",
                   label=f"Mean = {mean_e:.1f} ms")
        ax.legend(fontsize=8)
    else:
        ax.text(0.5, 0.5, "No trip-time data", transform=ax.transAxes,
                ha="center", va="center", color=_GREY)

    ax.set_xlabel("Trip time error: $t_{DT} - t_{field}$ [ms]", fontsize=9)
    ax.set_ylabel("Count", fontsize=9)
    ax.set_title("DT Trip-Time Error Distribution", fontsize=10)
    ax.tick_params(labelsize=8)
    fig.tight_layout()

    fpath = _FIG_DIR / "fig_trip_time_error.pdf"
    fig.savefig(fpath, bbox_inches="tight")
    print(f"    saved: {fpath.name}")
    plt.close(fig)
    return fpath


# ---------------------------------------------------------------------------
# Figure 5 — k_ibr estimation accuracy scatter
# ---------------------------------------------------------------------------

def _fig_kibr_scatter(batch: BatchComparisonReport, show: bool) -> Path:
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Collect (k_ibr_estimated, agreement) pairs
    k_vals  = [r.k_ibr_estimated for r in batch.reports]
    agreed  = [r.agreement for r in batch.reports]
    k_agree = [k for k, a in zip(k_vals, agreed) if a]
    k_flag  = [k for k, a in zip(k_vals, agreed) if not a]

    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    ax.scatter(k_agree, range(len(k_agree)), color=_BLUE, alpha=0.7,
               s=18, label=f"AGREE (N={len(k_agree)})", zorder=3)
    ax.scatter(k_flag,  range(len(k_flag)),  color=_AMBER, alpha=0.7,
               s=18, marker="x", label=f"FLAG (N={len(k_flag)})", zorder=3)
    ax.axvline(1.0, color=_GREY, linewidth=0.8, linestyle="--", label="k=1.0 (full IBR)")
    ax.set_xlabel("$\\hat{k}_{IBR}$ estimated [pu]", fontsize=9)
    ax.set_ylabel("Record index", fontsize=9)
    ax.set_title("k$_{IBR}$ Estimation: AGREE vs FLAG", fontsize=10)
    ax.legend(fontsize=8, loc="lower right")
    ax.tick_params(labelsize=8)
    fig.tight_layout()

    fpath = _FIG_DIR / "fig_kibr_scatter.pdf"
    fig.savefig(fpath, bbox_inches="tight")
    print(f"    saved: {fpath.name}")
    plt.close(fig)
    return fpath


# ---------------------------------------------------------------------------
# LaTeX tables
# ---------------------------------------------------------------------------

def _write_latex_tables(batch: BatchComparisonReport) -> None:
    lines = []
    lines.append("% TR-76 Benchmark Tables — auto-generated by tr76_benchmark_generator.py")
    lines.append("% Do not edit manually.\n")

    # Table 1: Overall summary
    te = batch.time_error_stats
    lines.append(r"\begin{table}[!t]")
    lines.append(r"\caption{TR-76 DT Replay Engine — Overall Benchmark Summary}")
    lines.append(r"\label{tab:tr76_summary}")
    lines.append(r"\centering")
    lines.append(r"\begin{tabular}{lc}")
    lines.append(r"\hline")
    lines.append(r"\textbf{Metric} & \textbf{Value} \\ \hline")
    lines.append(f"Total records & {batch.total_records} \\\\")
    lines.append(f"Overall AGREE rate & {batch.agree_rate*100:.1f}\\% \\\\")
    lines.append(f"Element match rate & {batch.element_match_rate*100:.1f}\\% \\\\")
    if te["mean"] is not None:
        lines.append(f"Trip-time error mean & {te['mean']:.1f}~ms \\\\")
        lines.append(f"Trip-time error std  & {te['std']:.1f}~ms \\\\")
        lines.append(f"Trip-time error max  & {te['max']:.1f}~ms \\\\")
        lines.append(f"N records with trip-time & {te['n']} \\\\")
    lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    lines.append("")

    # Table 2: Per-fault-type
    short = {"evolving_SLG_to_DLG": "SLG$\\to$DLG", "cross_country": "X-country"}
    lines.append(r"\begin{table}[!t]")
    lines.append(r"\caption{TR-76 Agreement Rate by Fault Type}")
    lines.append(r"\label{tab:tr76_fault_type}")
    lines.append(r"\centering")
    lines.append(r"\begin{tabular}{lcc}")
    lines.append(r"\hline")
    lines.append(r"\textbf{Fault type} & \textbf{N} & \textbf{AGREE [\%]} \\ \hline")
    counts = defaultdict(int)
    for r in batch.reports:
        counts[r.fault_type] += 1
    for ft in _FAULT_ORDER:
        if ft in batch.per_fault_type:
            disp = short.get(ft, ft)
            rate = batch.per_fault_type[ft] * 100
            n    = counts[ft]
            lines.append(f"{disp} & {n} & {rate:.1f} \\\\")
    lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    lines.append("")

    # Table 3: Per-IBR-type
    lines.append(r"\begin{table}[!t]")
    lines.append(r"\caption{TR-76 Agreement Rate by IBR Type}")
    lines.append(r"\label{tab:tr76_ibr_type}")
    lines.append(r"\centering")
    lines.append(r"\begin{tabular}{lcc}")
    lines.append(r"\hline")
    lines.append(r"\textbf{IBR type} & \textbf{N} & \textbf{AGREE [\%]} \\ \hline")
    ibr_counts = defaultdict(int)
    for r in batch.reports:
        ibr_counts[r.ibr_type] += 1
    for it in _IBR_ORDER:
        if it in batch.per_ibr_type:
            rate = batch.per_ibr_type[it] * 100
            n    = ibr_counts[it]
            lines.append(f"{it} & {n} & {rate:.1f} \\\\")
    lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    lines.append("")

    _TABLE_TEX.write_text("\n".join(lines))
    print(f"    saved: {_TABLE_TEX.name}")


# ---------------------------------------------------------------------------
# Plain-text summary
# ---------------------------------------------------------------------------

def _write_summary_txt(batch: BatchComparisonReport) -> None:
    te = batch.time_error_stats
    lines = []
    lines.append("=" * 68)
    lines.append("  SAMBP DT Replay Engine — TR-76 Benchmark Summary")
    lines.append("=" * 68)
    lines.append(f"  Total records     : {batch.total_records}")
    lines.append(f"  AGREE             : {batch.agree_count}  ({batch.agree_rate*100:.1f}%)")
    lines.append(f"  FLAG (any)        : {batch.flag_count}  ({(1-batch.agree_rate)*100:.1f}%)")
    lines.append(f"  Element match     : {batch.element_match_rate*100:.1f}%")
    lines.append("")
    lines.append("  Verdict breakdown")
    # gather from reports
    from collections import Counter
    verdict_counts = Counter(r.dt_decision for r in batch.reports)
    for v, c in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        lines.append(f"    {v:<20} {c:>4}  ({c/batch.total_records*100:.1f}%)")
    lines.append("")
    lines.append("  Agreement by fault type")
    short = {"evolving_SLG_to_DLG": "SLG->DLG", "cross_country": "X-country"}
    counts = defaultdict(int)
    for r in batch.reports:
        counts[r.fault_type] += 1
    for ft in _FAULT_ORDER:
        if ft in batch.per_fault_type:
            disp = short.get(ft, ft)
            lines.append(f"    {disp:<22} {batch.per_fault_type[ft]*100:>6.1f}%  (N={counts[ft]})")
    lines.append("")
    lines.append("  Agreement by IBR type")
    ibr_counts = defaultdict(int)
    for r in batch.reports:
        ibr_counts[r.ibr_type] += 1
    for it in _IBR_ORDER:
        if it in batch.per_ibr_type:
            lines.append(f"    {it:<22} {batch.per_ibr_type[it]*100:>6.1f}%  (N={ibr_counts[it]})")
    lines.append("")
    lines.append("  Trip-time error (DT - field) [ms]")
    if te["mean"] is not None:
        lines.append(f"    mean = {te['mean']:.2f} ms")
        lines.append(f"    std  = {te['std']:.2f} ms")
        lines.append(f"    max  = {te['max']:.2f} ms")
        lines.append(f"    N    = {te['n']}")
    else:
        lines.append("    (no trip-time data)")
    lines.append("")
    lines.append("  Individual FLAGS")
    flagged = [r for r in batch.reports if not r.agreement]
    if flagged:
        for r in flagged:
            lines.append(f"    {r.record_id:<42} {r.dt_decision}  {r.reason}")
    else:
        lines.append("    (none)")
    lines.append("=" * 68)

    _SUMMARY_TXT.write_text("\n".join(lines) + "\n")
    print(f"    saved: {_SUMMARY_TXT.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="TR-76 benchmark report generator (WP 76.4)")
    p.add_argument("--no-plots", action="store_true",
                   help="Skip matplotlib figure generation")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    _FIG_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 68)
    print("  SAMBP TR-76 Benchmark Generator — WP 76.4")
    print("=" * 68)

    # 1. Run batch
    print("\n[1/4] Running DT replay batch ...")
    batch = run_batch()

    # 2. Figures
    if not args.no_plots:
        print("\n[2/4] Generating figures ...")
        _fig_confusion(batch, show=False)
        _fig_per_fault(batch, show=False)
        _fig_per_ibr(batch, show=False)
        _fig_trip_time_error(batch, show=False)
        _fig_kibr_scatter(batch, show=False)
    else:
        print("\n[2/4] Skipping figures (--no-plots)")

    # 3. LaTeX tables
    print("\n[3/4] Writing LaTeX tables ...")
    _write_latex_tables(batch)

    # 4. Text summary
    print("\n[4/4] Writing plain-text summary ...")
    _write_summary_txt(batch)

    print("\n" + "=" * 68)
    print("  TR-76 benchmark complete.")
    print(f"  Figures : {_FIG_DIR}")
    print(f"  Tables  : {_TABLE_TEX}")
    print(f"  Summary : {_SUMMARY_TXT}")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
