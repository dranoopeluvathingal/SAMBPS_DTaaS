#!/usr/bin/env python3
# =============================================================================
# sambp / digital_twin / reports / tr68_bess_report_generator.py
#
# TR-68 BESS Report Generator — WP 68.6
#
# Runs 240 BESS scenarios through the EKF + protection mirror pipeline and
# produces four matplotlib figures saved to reports/figures/TR68/:
#
#   Fig 1 — AGREE rate by chemistry (bar chart)
#   Fig 2 — AGREE rate by SoC level (bar chart)
#   Fig 3 — AGREE rate by fault type (bar chart)
#   Fig 4 — Protection outcome distribution (stacked bar by chemistry)
#
# Usage (from digital_twin/ root):
#   python reports/tr68_bess_report_generator.py
#   python reports/tr68_bess_report_generator.py --no-plots
#   python reports/tr68_bess_report_generator.py --n-scenarios 40
#
# Dependencies: numpy, matplotlib (standard SAMBP environment)
# =============================================================================

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import math

import numpy as np

_DT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_DT_ROOT))

from models.bess_scenario_lib import BESSScenarioLibrary, BESSScenario
from models.bess_model import BESSModel, BESSConfig
from estimation.bess_ekf import BESSEKFEstimator
from models.bess_protection_mirror import (
    BESSProtectionMirror, ProtectionDecision, _I_AC_PICKUP_PU,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPORT_DIR = Path(__file__).resolve().parent
_FIG_DIR    = _REPORT_DIR / "figures" / "TR68"
_FIG_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Colour palette (IEEE colorblind-safe)
# ---------------------------------------------------------------------------

_BLUE   = "#2166AC"
_GREEN  = "#1B7837"
_AMBER  = "#D6604D"
_GREY   = "#878787"
_TEAL   = "#4DAC26"

_CHEM_COLOURS = {
    "li_ion": _BLUE,
    "flow":   _GREEN,
    "na_ion": _AMBER,
}

# ---------------------------------------------------------------------------
# Pipeline (mirrors test_bess_dt_integration.py but for all N scenarios)
# ---------------------------------------------------------------------------

_DISPATCH = {
    "charging":    np.array([-0.80, 0.0]),
    "idle":        np.array([ 0.00, 0.0]),
    "discharging": np.array([ 0.80, 0.0]),
}

_N_PRE   = 30    # pre-fault warm-up steps (30 ms)
_N_FAULT = 30    # fault observation window (30 ms)
_DT_S    = 1e-3


def _run_scenario(scenario: BESSScenario) -> Dict:
    preset_map = {
        "li_ion": BESSConfig.li_ion_1mwh,
        "flow":   BESSConfig.flow_5mwh,
        "na_ion": BESSConfig.na_ion_500kwh,
    }
    cfg   = preset_map[scenario.chemistry]()
    model = BESSModel(cfg)
    est   = BESSEKFEstimator(cfg)
    mirror = BESSProtectionMirror(cfg)

    u = _DISPATCH.get(scenario.operating_mode, np.array([0.0, 0.0]))
    x = np.array(scenario.pre_fault_state, dtype=float)
    rng_pre = np.random.default_rng(scenario.scenario_id)

    for _ in range(_N_PRE):
        z = model.h(x) + rng_pre.normal(0, 0.005, 6)
        est.update(z, u=u, dt=_DT_S)
        x = model.f(x, u, _DT_S)

    mirror.reset()
    relay_decision = None
    for step in range(_N_FAULT):
        rng_f   = np.random.default_rng(scenario.scenario_id * 1000 + step)
        x_fault = model.fault_state(x, scenario.fault_type, step * _DT_S)
        z_fault = model.h(x_fault) + rng_f.normal(0, 0.005, 6)
        ek      = est.update(z_fault, u=u, dt=_DT_S)
        i_ac_raw = float(math.sqrt(float(np.mean(z_fault[3:] ** 2))))
        i_dc_raw = i_ac_raw * abs(ek["P_dc"]) / max(abs(ek["I_ac_mag"]), 0.01)
        meas    = {
            "i_ac_pu":    i_ac_raw,
            "i_dc_pu":    i_dc_raw,
            "v_dc_pu":    ek["V_dc"],
            "p_ac_pu":    ek["P_dc"],
            "freq_hz":    50.0,
            "rocof_hz_s": 0.0,
            "t_cell_c":   ek["T_cell"],
            "dt_s":       _DT_S,
        }
        d = mirror.predict(meas)
        if d.is_trip and relay_decision is None:
            relay_decision = d

    if relay_decision is None:
        relay_decision = ProtectionDecision(
            element="NONE", action="BLOCK",
            confidence=1.0, function_id="NONE", details={}
        )

    expected_trip = scenario.fault_current_pu > _I_AC_PICKUP_PU
    relay_trips   = relay_decision.is_trip
    if relay_trips == expected_trip:
        verdict = "AGREE"
    elif relay_trips and not expected_trip:
        verdict = "FLAG_FP"
    else:
        verdict = "FLAG_FN"

    return {
        "chemistry":        scenario.chemistry,
        "soc_level":        round(scenario.soc_level, 2),
        "fault_type":       scenario.fault_type,
        "expected_outcome": scenario.protection_outcome,
        "relay_trips":      relay_trips,
        "verdict":          verdict,
    }


def run_pipeline(n_scenarios: int = 240) -> List[Dict]:
    print(f"[TR-68] Generating {n_scenarios} BESS scenarios…")
    lib = BESSScenarioLibrary(n_scenarios=n_scenarios, seed=42)
    lib.generate_all()
    results = []
    for i, sc in enumerate(lib._scenarios):
        r = _run_scenario(sc)
        results.append(r)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{n_scenarios} scenarios processed")
    return results


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def _agree_rate_by(results: List[Dict], key: str) -> Dict[str, float]:
    groups: Dict[str, List] = defaultdict(list)
    for r in results:
        groups[str(r[key])].append(r["verdict"] == "AGREE")
    return {k: sum(v) / len(v) for k, v in sorted(groups.items())}


def _outcome_counts_by_chemistry(results: List[Dict]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        out[r["chemistry"]][r["expected_outcome"]] += 1
    return {k: dict(v) for k, v in out.items()}


def _overall_agree_rate(results: List[Dict]) -> float:
    return sum(1 for r in results if r["verdict"] == "AGREE") / len(results)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def _save_fig(fig, name: str) -> None:
    path = _FIG_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved: {path.relative_to(_DT_ROOT)}")


def plot_agree_by_chemistry(results, ax=None, save=True):
    import matplotlib.pyplot as plt
    rates = _agree_rate_by(results, "chemistry")
    chems = list(rates.keys())
    vals  = [rates[c] * 100 for c in chems]
    colours = [_CHEM_COLOURS.get(c, _GREY) for c in chems]

    fig, ax = plt.subplots(figsize=(5, 3.5)) if ax is None else (ax.figure, ax)
    bars = ax.bar(chems, vals, color=colours, edgecolor="k", linewidth=0.6)
    ax.axhline(90, color="red", linestyle="--", linewidth=0.8, label="90% threshold")
    ax.set_ylim(0, 105)
    ax.set_ylabel("AGREE rate [%]")
    ax.set_title("TR-68: BESS AGREE rate by chemistry")
    ax.legend(fontsize=8)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 1,
                f"{v:.1f}%", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    if save:
        _save_fig(fig, "fig1_agree_by_chemistry.pdf")
    return fig


def plot_agree_by_soc(results, ax=None, save=True):
    import matplotlib.pyplot as plt
    rates = _agree_rate_by(results, "soc_level")
    socs  = list(rates.keys())
    vals  = [rates[s] * 100 for s in socs]

    fig, ax = plt.subplots(figsize=(5, 3.5)) if ax is None else (ax.figure, ax)
    ax.bar(socs, vals, color=_BLUE, edgecolor="k", linewidth=0.6)
    ax.axhline(90, color="red", linestyle="--", linewidth=0.8, label="90% threshold")
    ax.set_ylim(0, 105)
    ax.set_xlabel("SoC level [pu]")
    ax.set_ylabel("AGREE rate [%]")
    ax.set_title("TR-68: BESS AGREE rate by SoC level")
    ax.legend(fontsize=8)
    fig.tight_layout()
    if save:
        _save_fig(fig, "fig2_agree_by_soc.pdf")
    return fig


def plot_agree_by_fault_type(results, ax=None, save=True):
    import matplotlib.pyplot as plt
    rates = _agree_rate_by(results, "fault_type")
    fts   = list(rates.keys())
    vals  = [rates[f] * 100 for f in fts]

    fig, ax = plt.subplots(figsize=(5, 3.5)) if ax is None else (ax.figure, ax)
    ax.bar(fts, vals, color=_TEAL, edgecolor="k", linewidth=0.6)
    ax.axhline(90, color="red", linestyle="--", linewidth=0.8, label="90% threshold")
    ax.set_ylim(0, 105)
    ax.set_xlabel("Fault type")
    ax.set_ylabel("AGREE rate [%]")
    ax.set_title("TR-68: BESS AGREE rate by fault type")
    ax.legend(fontsize=8)
    fig.tight_layout()
    if save:
        _save_fig(fig, "fig3_agree_by_fault_type.pdf")
    return fig


def plot_outcome_distribution(results, ax=None, save=True):
    import matplotlib.pyplot as plt
    data = _outcome_counts_by_chemistry(results)
    chems    = list(data.keys())
    outcomes = ["Z1/87L", "87L", "EXTERNAL", "MISS"]
    opal     = [_BLUE, _GREEN, _AMBER, _GREY]

    fig, ax = plt.subplots(figsize=(6, 4)) if ax is None else (ax.figure, ax)
    bottoms = np.zeros(len(chems))
    for outcome, colour in zip(outcomes, opal):
        vals = [data[c].get(outcome, 0) for c in chems]
        ax.bar(chems, vals, bottom=bottoms, label=outcome,
               color=colour, edgecolor="k", linewidth=0.5)
        bottoms += np.array(vals)
    ax.set_ylabel("Scenario count")
    ax.set_title("TR-68: Protection outcome distribution by chemistry")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    if save:
        _save_fig(fig, "fig4_outcome_distribution.pdf")
    return fig


# ---------------------------------------------------------------------------
# Text summary
# ---------------------------------------------------------------------------

def print_summary(results: List[Dict]) -> None:
    from collections import Counter
    n    = len(results)
    rate = _overall_agree_rate(results) * 100
    verd = Counter(r["verdict"] for r in results)
    print()
    print("=" * 60)
    print("TR-68 BESS Protection Mirror — Integration Report")
    print("=" * 60)
    print(f"  Total scenarios     : {n}")
    print(f"  Overall AGREE rate  : {rate:.1f}%")
    for v, c in sorted(verd.items()):
        print(f"  {v:<16}: {c:3d} ({c/n*100:.1f}%)")
    print()
    print("  AGREE by chemistry:")
    for chem, r in _agree_rate_by(results, "chemistry").items():
        print(f"    {chem:<10}: {r*100:.1f}%")
    print()
    print("  AGREE by fault type:")
    for ft, r in _agree_rate_by(results, "fault_type").items():
        print(f"    {ft:<6}: {r*100:.1f}%")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="TR-68 BESS report generator")
    parser.add_argument("--no-plots", action="store_true",
                        help="Skip matplotlib figure generation")
    parser.add_argument("--n-scenarios", type=int, default=240,
                        help="Number of scenarios to run (default 240)")
    args = parser.parse_args()

    results = run_pipeline(n_scenarios=args.n_scenarios)
    print_summary(results)

    if not args.no_plots:
        try:
            import matplotlib
            matplotlib.use("Agg")
            print("\n[TR-68] Generating figures…")
            plot_agree_by_chemistry(results)
            plot_agree_by_soc(results)
            plot_agree_by_fault_type(results)
            plot_outcome_distribution(results)
            print("[TR-68] All figures saved.")
        except ImportError:
            print("[TR-68] matplotlib not available — skipping figures.")


if __name__ == "__main__":
    main()
