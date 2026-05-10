"""
run_transformer_diff_study.py
==============================
Batch study runner for the SAMBP 87T transformer differential relay.

Runs all canonical events through:
    1. Conventional 87T relay  (transformer_diff_baseline)
    2. Reduced-zone estimator  (transformer_inverse_estimator)
    3. Confidence gate         (transformer_confidence_gate)

Produces:
    outputs/87T_study_results.csv  — per-event metrics table
    outputs/87T_characteristic.png — I_op vs I_rst scatter plot
    outputs/87T_kappa_bar.png      — κ_n bar chart per event

Usage:
    python run_transformer_diff_study.py [--plot] [--save-csv]
"""

from __future__ import annotations

import sys
import csv
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(__file__))

from models.transformer_diff_baseline import (
    TransformerRelayConfig, run_87T_relay, trip_boundary,
    _rated_current_H, _rated_current_X,
    compensate_winding, compute_operate_restraint,
    _vector_group_matrix,
)
from models.transformer_event_library import (
    event_normal_load, event_inrush, event_overexcitation,
    event_external_fault_ct_sat,
    event_internal_tg_fault, event_internal_ab_fault, event_internal_3ph_fault,
)
from models.transformer_reduced_zone_model import (
    condition_number_normalised, interpret_theta,
)
from inverse_estimation.transformer_inverse_estimator import estimate_zone_parameters
from adaptation.transformer_confidence_gate import (
    ConfidenceGateConfig, GateState, evaluate_confidence_gate,
)

# ---------------------------------------------------------------------------
# Event catalogue
# ---------------------------------------------------------------------------

def build_event_catalogue(cfg: TransformerRelayConfig) -> list[dict]:
    """Return all test events, scaled to relay config rated currents."""
    fs  = cfg.sample_rate_hz
    f   = cfg.freq_nom_hz
    MVA = cfg.MVA_rated
    kH  = cfg.kV_H
    kX  = cfg.kV_X

    kw = dict(sample_rate_hz=fs, freq_hz=f, MVA=MVA, kV_H=kH, kV_X=kX)

    return [
        event_normal_load(duration_s=0.1, **kw),
        event_inrush(duration_s=0.3, **kw),
        event_overexcitation(duration_s=0.2, **kw),
        event_external_fault_ct_sat(duration_s=0.15, **kw),
        event_internal_tg_fault(duration_s=0.2, **kw),
        event_internal_ab_fault(duration_s=0.2, **kw),
        event_internal_3ph_fault(duration_s=0.2, **kw),
    ]


# ---------------------------------------------------------------------------
# Per-event analysis
# ---------------------------------------------------------------------------

def _compute_idiff_pu(ev: dict, cfg: TransformerRelayConfig) -> np.ndarray:
    """
    Compute per-unit phase-A differential current for the estimator.
    Uses the same compensation logic as run_87T_relay but returns the
    signed instantaneous waveform.
    """
    I_H = _rated_current_H(cfg)
    I_X = _rated_current_X(cfg)
    M_H = np.eye(3)
    M_X = _vector_group_matrix(cfg.vector_group)
    tap_H = 1.0 / (1.0 + cfg.tap_deviation_pu)

    i_H_comp = compensate_winding(ev["i_H_abc"], cfg.CT_ratio_H, I_H, M_H, tap_H)
    i_X_comp = compensate_winding(ev["i_X_abc"], cfg.CT_ratio_X, I_X, M_X, 1.0)
    i_diff   = i_H_comp + i_X_comp   # signed, (3, N)
    return i_diff[0]                  # phase A


def analyse_event(
    ev: dict,
    cfg: TransformerRelayConfig,
    gate_cfg: ConfidenceGateConfig,
) -> dict:
    """Full analysis pipeline for a single event."""

    # 1. Conventional 87T relay
    dec_conv = run_87T_relay(ev["time_s"], ev["i_H_abc"], ev["i_X_abc"], cfg)

    # 2. Reduced-zone estimation (phase A differential)
    i_diff_pu = _compute_idiff_pu(ev, cfg)
    t_w = ev["time_s"]

    est = estimate_zone_parameters(t_w, i_diff_pu, freq_hz=cfg.freq_nom_hz)
    state = est["state"]

    # 3. Confidence gate (single window)
    gs = GateState()
    gate_dec, _ = evaluate_confidence_gate(
        state,
        conventional_trip = dec_conv.t_trip_s is not None,
        gate_cfg = gate_cfg,
        gate_state = gs,
    )

    return {
        "event_name":         ev["event_name"],
        "fault_time_s":       ev.get("fault_time"),
        "conv_trip":          dec_conv.t_trip_s is not None,
        "conv_trip_time_s":   dec_conv.t_trip_s,
        "model_trip":         gate_dec.model_trip,
        "final_trip":         gate_dec.final_trip,
        "source":             gate_dec.source,
        "theta_hat":          est["theta_hat"],
        "kappa_n":            est["kappa_n"],
        "residual_norm":      est["residual_norm"],
        "confidence":         state.confidence,
        "is_inrush":          state.is_inrush,
        "is_overexcitation":  state.is_overexcitation,
        "is_ct_saturated":    state.is_ct_saturated,
        "is_internal_fault":  state.is_internal_fault,
        "f_int":              state.f_int,
        "I_op_peak_pu":       float(dec_conv.I_op.max()),
        "I_rst_peak_pu":      float(dec_conv.I_rst.max()),
        "reason":             gate_dec.reason,
        "dec_conv":           dec_conv,
    }


# ---------------------------------------------------------------------------
# Expected outcomes (for assertion checks)
# ---------------------------------------------------------------------------

EXPECTED = {
    "normal_load":            {"should_trip": False},
    "energisation_inrush":    {"should_trip": False},
    "overexcitation":         {"should_trip": False},
    # Stage 2: CT saturation pre-blocking now handled by ε_CT gate.
    # The conventional relay still mal-trips but the SAMBP gate suppresses it.
    "external_fault_ct_sat":  {"should_trip": False},
    "internal_tg_fault_phA":  {"should_trip": True},
    "internal_ab_fault":      {"should_trip": True},
    "internal_3ph_fault":     {"should_trip": True},
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def save_csv(results: list[dict], path: str):
    rows = []
    for r in results:
        th = r["theta_hat"]
        rows.append({
            "event_name":        r["event_name"],
            "conv_trip":         int(r["conv_trip"]),
            "final_trip":        int(r["final_trip"]),
            "source":            r["source"],
            "kappa_n":           f"{r['kappa_n']:.2f}",
            "residual_norm":     f"{r['residual_norm']:.4f}",
            "confidence":        f"{r['confidence']:.3f}",
            "f_int":             f"{r['f_int']:.3f}",
            "is_inrush":         int(r["is_inrush"]),
            "is_overexcitation": int(r["is_overexcitation"]),
            "I_op_peak_pu":      f"{r['I_op_peak_pu']:.3f}",
            "I_rst_peak_pu":     f"{r['I_rst_peak_pu']:.3f}",
            "theta_I_diff_fund": f"{th[0]:.3f}",
            "theta_phi_diff":    f"{th[1]:.3f}",
            "theta_k_inrush":    f"{th[2]:.3f}",
            "theta_k_ovexc":     f"{th[3]:.3f}",
            "theta_epsilon_CT":  f"{th[4]:.3f}",
        })
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  CSV saved → {path}")


def plot_characteristic(results: list[dict], cfg: TransformerRelayConfig, path: str):
    I_rst_line, I_op_thresh = trip_boundary(cfg)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(I_rst_line, I_op_thresh, "r-", lw=2, label="Trip boundary")
    ax.axhline(cfg.I_op_min_pu, color="gray", ls="--", lw=1, label="$I_{op,min}$")

    markers = {"normal_load": ("o","blue"),
               "energisation_inrush": ("s","green"),
               "overexcitation": ("D","purple"),
               "external_fault_ct_sat": ("^","orange"),
               "internal_tg_fault_phA": ("*","red"),
               "internal_ab_fault": ("P","darkred"),
               "internal_3ph_fault": ("X","maroon")}

    for r in results:
        mk, col = markers.get(r["event_name"], ("o","gray"))
        ax.scatter(r["I_rst_peak_pu"], r["I_op_peak_pu"],
                   marker=mk, color=col, s=80,
                   label=r["event_name"].replace("_", " "), zorder=5)

    ax.set_xlabel("$I_{rst}$ peak [pu]")
    ax.set_ylabel("$I_{op}$ peak [pu]")
    ax.set_title("87T Differential Characteristic — All Events")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, None)
    ax.set_ylim(0, None)
    plt.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Characteristic plot → {path}")


def plot_kappa_bar(results: list[dict], path: str):
    names  = [r["event_name"].replace("_", "\n") for r in results]
    kappas = [min(r["kappa_n"], 100.0) for r in results]   # cap for display
    colors = ["#e74c3c" if k > 30 else "#2ecc71" for k in kappas]

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar(range(len(names)), kappas, color=colors, edgecolor="k", lw=0.5)
    ax.axhline(30.0, color="red", ls="--", lw=1.2, label="$\\kappa_{thresh}=30$")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel("$\\kappa_n$ (capped at 100)")
    ax.set_title("Column-Normalised Condition Number per Event")
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
    parser = argparse.ArgumentParser(description="SAMBP 87T differential study")
    parser.add_argument("--plot",     action="store_true", default=True)
    parser.add_argument("--save-csv", action="store_true", default=True)
    args = parser.parse_args()

    cfg      = TransformerRelayConfig()
    gate_cfg = ConfidenceGateConfig(n_confirm=1)   # single-window for batch study

    print("=" * 60)
    print("SAMBP 87T Transformer Differential Study")
    print("=" * 60)

    events  = build_event_catalogue(cfg)
    results = []
    errors  = 0

    for ev in events:
        print(f"\n  → {ev['event_name']}")
        res = analyse_event(ev, cfg, gate_cfg)
        results.append(res)

        exp = EXPECTED.get(ev["event_name"], {})
        should_trip = exp.get("should_trip", None)
        status = "OK"
        if should_trip is not None and res["final_trip"] != should_trip:  # None = skip
            status = f"FAIL (expected trip={should_trip}, got {res['final_trip']})"
            errors += 1

        print(f"     conv_trip={res['conv_trip']}  final_trip={res['final_trip']}  "
              f"source={res['source']}")
        print(f"     κ_n={res['kappa_n']:.1f}  conf={res['confidence']:.3f}  "
              f"f_int={res['f_int']:.3f}  [{status}]")

    print("\n" + "=" * 60)
    print(f"Summary: {len(results)} events, {errors} assertion failures")
    print("=" * 60)

    if args.save_csv:
        save_csv(results, "outputs/87T_study_results.csv")

    if args.plot:
        plot_characteristic(results, cfg, "outputs/87T_characteristic.png")
        plot_kappa_bar(results,           "outputs/87T_kappa_bar.png")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
