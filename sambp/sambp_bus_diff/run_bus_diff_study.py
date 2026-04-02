"""
run_bus_diff_study.py
======================
Batch study runner for the SAMBP 87B bus differential relay.

Runs 6 canonical events through:
    1. Conventional 87B relay  (bus_diff_baseline)
    2. Reduced-zone estimator  (bus_inverse_estimator)
    3. Confidence gate         (bus_confidence_gate)

Outputs:
    outputs/87B_study_results.csv
    outputs/87B_characteristic.png
    outputs/87B_kappa_bar.png
"""

from __future__ import annotations

import sys, os, csv, argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))

from models.bus_diff_baseline import (
    BusDiffRelayConfig, run_87B_relay, trip_boundary,
)
from models.bus_event_library import (
    event_normal_load, event_external_fault, event_external_fault_ct_sat,
    event_internal_fault_ag, event_internal_fault_3ph, event_ct_open_circuit,
)
from models.bus_reduced_zone_model import condition_number_normalised, interpret_theta
from inverse_estimation.bus_inverse_estimator import estimate_bus_zone_parameters
from adaptation.bus_confidence_gate import BusGateConfig, BusGateState, evaluate_87B_confidence_gate


# ---------------------------------------------------------------------------
# Event catalogue
# ---------------------------------------------------------------------------

def build_event_catalogue(cfg: BusDiffRelayConfig) -> list[dict]:
    kw = dict(sample_rate_hz=cfg.sample_rate_hz,
              freq_hz=cfg.freq_nom_hz,
              I_bus_A=cfg.I_bus_rated_A)
    return [
        event_normal_load(duration_s=0.10, **kw),
        event_external_fault(duration_s=0.15, **kw),
        event_external_fault_ct_sat(duration_s=0.15, **kw),
        event_internal_fault_ag(duration_s=0.15, **kw),
        event_internal_fault_3ph(duration_s=0.15, **kw),
        event_ct_open_circuit(duration_s=0.10, **kw),
    ]


# ---------------------------------------------------------------------------
# Per-event analysis
# ---------------------------------------------------------------------------

def _idiff_pu_phA(ev: dict, cfg: BusDiffRelayConfig) -> np.ndarray:
    """Compute per-unit phase-A differential current for the estimator."""
    i_sum = sum(ev["i_feeders"])   # (3, T)
    return i_sum[0] / cfg.I_bus_rated_A


def analyse_event(
    ev: dict,
    cfg: BusDiffRelayConfig,
    gate_cfg: BusGateConfig,
) -> dict:
    # 1. Conventional relay
    dec_conv = run_87B_relay(ev["time_s"], ev["i_feeders"], cfg)

    # 2. Zone estimator on phase-A differential
    i_diff_pu = _idiff_pu_phA(ev, cfg)
    est = estimate_bus_zone_parameters(ev["time_s"], i_diff_pu,
                                       freq_hz=cfg.freq_nom_hz)
    state = est["state"]

    # 3. Confidence gate (single window)
    gs = BusGateState()
    gate_dec, _ = evaluate_87B_confidence_gate(
        state,
        conventional_trip = dec_conv.t_trip_s is not None,
        gate_cfg  = gate_cfg,
        gate_state = gs,
    )

    return {
        "event_name":       ev["event_name"],
        "conv_trip":        dec_conv.t_trip_s is not None,
        "conv_trip_time_s": dec_conv.t_trip_s,
        "final_trip":       gate_dec.final_trip,
        "source":           gate_dec.source,
        "theta_hat":        est["theta_hat"],
        "kappa_n":          est["kappa_n"],
        "residual_norm":    est["residual_norm"],
        "confidence":       state.confidence,
        "epsilon_CT":       state.epsilon_CT,
        "f_int":            state.f_int,
        "is_ct_saturated":  state.is_ct_saturated,
        "is_internal":      state.is_internal_fault,
        "I_op_peak_pu":     float(dec_conv.I_op.max()),
        "I_rst_peak_pu":    float(dec_conv.I_rst.max()),
        "reason":           gate_dec.reason,
    }


# ---------------------------------------------------------------------------
# Expected outcomes
# ---------------------------------------------------------------------------

EXPECTED = {
    "normal_load":            {"should_trip": False},
    "external_fault":         {"should_trip": False},
    # Stage-2 model-veto handles CT saturation on external fault
    "external_fault_ct_sat":  {"should_trip": False},
    "internal_fault_ag":      {"should_trip": True},
    "internal_fault_3ph":     {"should_trip": True},
    # CT open-circuit: I_op = I_load, f_int ≈ 1 → cannot be discriminated by
    # differential protection alone.  Documented as known limitation.
    "ct_open_circuit":        {"should_trip": None},   # skip assertion
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def save_csv(results: list[dict], path: str):
    rows = []
    for r in results:
        th = r["theta_hat"]
        rows.append({
            "event_name":       r["event_name"],
            "conv_trip":        int(r["conv_trip"]),
            "final_trip":       int(r["final_trip"]),
            "source":           r["source"],
            "kappa_n":          f"{r['kappa_n']:.2f}",
            "residual_norm":    f"{r['residual_norm']:.4f}",
            "confidence":       f"{r['confidence']:.3f}",
            "f_int":            f"{r['f_int']:.3f}",
            "epsilon_CT":       f"{r['epsilon_CT']:.4f}",
            "I_op_peak_pu":     f"{r['I_op_peak_pu']:.3f}",
            "I_rst_peak_pu":    f"{r['I_rst_peak_pu']:.3f}",
            "theta_I_diff":     f"{th[0]:.3f}",
            "theta_phi":        f"{th[1]:.3f}",
            "theta_eps_CT":     f"{th[2]:.4f}",
        })
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  CSV saved → {path}")


def plot_characteristic(results: list[dict], cfg: BusDiffRelayConfig, path: str):
    I_rst_line, I_op_thresh = trip_boundary(cfg)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(I_rst_line, I_op_thresh, "r-", lw=2, label="Trip boundary")
    ax.axhline(cfg.I_op_min_pu, color="gray", ls="--", lw=1, label="$I_{op,min}$")

    markers = {
        "normal_load":           ("o", "blue"),
        "external_fault":        ("s", "green"),
        "external_fault_ct_sat": ("^", "orange"),
        "internal_fault_ag":     ("*", "red"),
        "internal_fault_3ph":    ("X", "darkred"),
        "ct_open_circuit":       ("D", "purple"),
    }
    for r in results:
        mk, col = markers.get(r["event_name"], ("o", "gray"))
        ax.scatter(r["I_rst_peak_pu"], r["I_op_peak_pu"],
                   marker=mk, color=col, s=90,
                   label=r["event_name"].replace("_", " "), zorder=5)

    ax.set_xlabel("$I_{rst}$ peak [pu]")
    ax.set_ylabel("$I_{op}$ peak [pu]")
    ax.set_title("87B Bus Differential Characteristic")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, None); ax.set_ylim(0, None)
    plt.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Characteristic plot → {path}")


def plot_kappa_bar(results: list[dict], path: str):
    names  = [r["event_name"].replace("_", "\n") for r in results]
    kappas = [min(r["kappa_n"], 100.0) for r in results]
    colors = ["#e74c3c" if k > 30 else "#2ecc71" for k in kappas]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(range(len(names)), kappas, color=colors, edgecolor="k", lw=0.5)
    ax.axhline(30.0, color="red", ls="--", lw=1.2, label="$\\kappa_{thresh}=30$")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel("$\\kappa_n$ (capped at 100)")
    ax.set_title("87B Column-Normalised Condition Number per Event")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  κ_n bar chart → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SAMBP 87B bus differential study")
    parser.add_argument("--plot",     action="store_true", default=True)
    parser.add_argument("--save-csv", action="store_true", default=True)
    args = parser.parse_args()

    cfg      = BusDiffRelayConfig()
    gate_cfg = BusGateConfig(n_confirm=1)   # single window for batch study

    print("=" * 60)
    print("SAMBP 87B Bus Differential Study")
    print("=" * 60)

    events  = build_event_catalogue(cfg)
    results = []
    errors  = 0

    for ev in events:
        print(f"\n  → {ev['event_name']}")
        res = analyse_event(ev, cfg, gate_cfg)
        results.append(res)

        exp          = EXPECTED.get(ev["event_name"], {})
        should_trip  = exp.get("should_trip", None)
        status       = "OK"
        if should_trip is not None and res["final_trip"] != should_trip:
            status = f"FAIL (expected trip={should_trip}, got {res['final_trip']})"
            errors += 1

        print(f"     conv={res['conv_trip']}  final={res['final_trip']}  "
              f"source={res['source']}")
        print(f"     κ_n={res['kappa_n']:.1f}  conf={res['confidence']:.3f}  "
              f"f_int={res['f_int']:.3f}  ε_CT={res['epsilon_CT']:.3f}  [{status}]")

    print("\n" + "=" * 60)
    print(f"Summary: {len(results)} events, {errors} assertion failures")
    print("=" * 60)

    if args.save_csv:
        save_csv(results, "outputs/87B_study_results.csv")
    if args.plot:
        plot_characteristic(results, cfg, "outputs/87B_characteristic.png")
        plot_kappa_bar(results,           "outputs/87B_kappa_bar.png")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
