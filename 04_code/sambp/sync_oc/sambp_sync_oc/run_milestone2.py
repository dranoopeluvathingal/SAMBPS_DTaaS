# =============================================================================
# sambp / sambp_sync_oc
# run_milestone2.py
#
# Milestone 2 — High-impedance fault (HIF) batch study.
#
# Sweeps Rf from 0.5 to 1.5 pu for 3PH and SLG fault types and compares
# fixed vs adaptive relay trip times across the resistance range.
#
# Usage
# -----
#   python run_milestone2.py
#
# Outputs
# -------
#   outputs/milestone2_results.csv
#   outputs/plots/milestone2/fig_hif_tclear.pdf
#   outputs/plots/milestone2/fig_hif_tclear.png
# =============================================================================

import os
import copy
import csv
import traceback

import numpy as np

from config.study_cases import HIF_STUDY_CASES
from config.system_config import SYSTEM_CONFIG
from config.relay_config import RELAY_CONFIG
from main_run_case import run_case


# ---------------------------------------------------------------------------
# HIF-specific system config overrides
# ---------------------------------------------------------------------------
HIF_SYSTEM_CFG = copy.deepcopy(SYSTEM_CONFIG)
HIF_SYSTEM_CFG["t_end"]      = 4.0   # HIF trips slowly; 2 s may be insufficient
HIF_SYSTEM_CFG["clear_time"] = 3.5   # long fault window to observe HIF response


# ---------------------------------------------------------------------------
# CSV output columns
# ---------------------------------------------------------------------------
CSV_FIELDS = [
    "case_name",
    "fault_type",
    "fault_R_pu",
    "confidence",
    "fixed_trip_time",
    "adaptive_trip_time",
    "trip_time_delta",
    "fixed_tripped",
    "adaptive_tripped",
    "speed_improvement",
    "pickup_proposed",
    "tms_proposed",
]


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_milestone2():
    """Run all HIF study cases and collect results."""
    rows = []

    for case in HIF_STUDY_CASES:
        case_name = case["case_name"]
        print(f"\n{'='*60}")
        print(f"Running case: {case_name}")
        print(f"{'='*60}")

        try:
            result = run_case(case,
                              system_cfg=HIF_SYSTEM_CFG,
                              relay_cfg=RELAY_CONFIG,
                              save_plots=False)

            prot  = result["protection_metrics"]
            adapt = result.get("adaptive_settings", {})

            rows.append({
                "case_name":          case_name,
                "fault_type":         result["fault_type"],
                "fault_R_pu":         result["fault_R_pu"],
                "confidence":         round(result["confidence"], 4),
                "fixed_trip_time":    prot["fixed_trip_time"],
                "adaptive_trip_time": prot["adaptive_trip_time"],
                "trip_time_delta":    prot["trip_time_delta"],
                "fixed_tripped":      prot["fixed_tripped"],
                "adaptive_tripped":   prot["adaptive_tripped"],
                "speed_improvement":  prot["speed_improvement"],
                "pickup_proposed":    round(adapt.get("pickup_pu", float("nan")), 4),
                "tms_proposed":       round(adapt.get("tms", float("nan")), 4),
            })
            print(f"  fixed={prot['fixed_trip_time']}  "
                  f"adaptive={prot['adaptive_trip_time']}  "
                  f"delta={prot['trip_time_delta']}")

        except Exception as exc:
            print(f"  ERROR in {case_name}: {exc}")
            traceback.print_exc()
            rows.append({
                "case_name":          case_name,
                "fault_type":         case.get("fault_type", ""),
                "fault_R_pu":         case.get("fault_R_pu", float("nan")),
                "confidence":         float("nan"),
                "fixed_trip_time":    "no_trip",
                "adaptive_trip_time": "no_trip",
                "trip_time_delta":    float("nan"),
                "fixed_tripped":      False,
                "adaptive_tripped":   False,
                "speed_improvement":  False,
                "pickup_proposed":    float("nan"),
                "tms_proposed":       float("nan"),
            })

    return rows


# ---------------------------------------------------------------------------
# Save results to CSV
# ---------------------------------------------------------------------------

def save_results_csv(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSummary CSV saved → {path}")


# ---------------------------------------------------------------------------
# Plot: t_clear(Rf) comparison — fixed vs adaptive
# ---------------------------------------------------------------------------

def _safe_float(val):
    """Return float or NaN if val is None / 'no_trip'."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return float("nan")


def plot_hif_tclear(rows, plot_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.style as style

        mplstyle = os.path.join(os.path.dirname(__file__), "..",
                                "..", "thesis_v2.mplstyle")
        if os.path.exists(mplstyle):
            style.use(mplstyle)
    except ImportError:
        print("matplotlib not available — skipping milestone 2 plot")
        return

    os.makedirs(plot_dir, exist_ok=True)

    fault_types = ["3PH", "SLG"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)

    for ax, ft in zip(axes, fault_types):
        subset = [r for r in rows if str(r.get("fault_type", "")) == ft]
        if not subset:
            ax.set_title(f"{ft} — no data")
            continue

        subset.sort(key=lambda r: _safe_float(r["fault_R_pu"]))
        Rf_vals   = [_safe_float(r["fault_R_pu"])         for r in subset]
        t_fixed   = [_safe_float(r["fixed_trip_time"])    for r in subset]
        t_adapt   = [_safe_float(r["adaptive_trip_time"]) for r in subset]

        # Replace NaN with a sentinel for "no trip" markers
        has_fixed = [not np.isnan(v) for v in t_fixed]
        has_adapt = [not np.isnan(v) for v in t_adapt]

        Rf_arr     = np.array(Rf_vals)
        t_fix_arr  = np.array(t_fixed)
        t_adp_arr  = np.array(t_adapt)

        # Plot lines (only where data exists)
        if any(has_fixed):
            mask = np.array(has_fixed)
            ax.semilogy(Rf_arr[mask], t_fix_arr[mask],
                        "o--", color="tab:blue",  lw=1.4, ms=5,
                        label="Fixed relay")
        if any(has_adapt):
            mask = np.array(has_adapt)
            ax.semilogy(Rf_arr[mask], t_adp_arr[mask],
                        "s-",  color="tab:orange", lw=1.4, ms=5,
                        label="Adaptive relay")

        # Mark "no trip" cases at top of y-axis
        no_trip_Rf = [Rf_vals[i] for i in range(len(Rf_vals))
                      if not has_fixed[i] or not has_adapt[i]]
        if no_trip_Rf:
            ylim_top = ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 10.0
            ax.scatter(no_trip_Rf,
                       [ylim_top * 0.9] * len(no_trip_Rf),
                       marker="x", color="tab:red", zorder=5, s=60,
                       label="No trip")

        ax.set_xlabel("Fault resistance $R_f$ (pu)")
        ax.set_ylabel("Trip time (s)  [log scale]")
        ax.set_title(f"HIF trip time vs $R_f$ — {ft}")
        ax.legend(fontsize=8)
        ax.grid(True, which="both", lw=0.4, ls=":")

    fig.suptitle("Milestone 2: Fixed vs Adaptive relay — HIF sweep", fontsize=11)
    fig.tight_layout()

    for ext in ("pdf", "png"):
        fpath = os.path.join(plot_dir, f"fig_hif_tclear.{ext}")
        fig.savefig(fpath, dpi=150)
        print(f"Plot saved → {fpath}")

    plt.close(fig)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    rows = run_milestone2()

    csv_path  = os.path.join("outputs", "milestone2_results.csv")
    plot_dir  = os.path.join("outputs", "plots", "milestone2")

    save_results_csv(rows, csv_path)
    plot_hif_tclear(rows, plot_dir)

    # Quick console summary
    print("\n" + "=" * 60)
    print("Milestone 2 summary")
    print("=" * 60)
    print(f"{'Case':<22} {'Rf':>5}  {'Fixed(s)':>9}  {'Adapt(s)':>9}  {'Delta(s)':>9}")
    print("-" * 60)
    for r in rows:
        t_f = r["fixed_trip_time"]
        t_a = r["adaptive_trip_time"]
        dt  = r["trip_time_delta"]
        fmt_f = f"{t_f:.3f}" if isinstance(t_f, float) else str(t_f)
        fmt_a = f"{t_a:.3f}" if isinstance(t_a, float) else str(t_a)
        fmt_d = f"{dt:.3f}" if isinstance(dt, float) else str(dt)
        print(f"{r['case_name']:<22} {r['fault_R_pu']:>5.2f}  "
              f"{fmt_f:>9}  {fmt_a:>9}  {fmt_d:>9}")
    print("=" * 60)
