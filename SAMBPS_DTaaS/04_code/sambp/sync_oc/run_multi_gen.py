# =============================================================================
# sambp / sambp_sync_oc
# run_multi_gen.py
#
# Multi-generator busbar coordination study.
#
# Simulates N parallel synchronous generators on a common bus, runs the
# inverse estimator independently for each machine, maps adaptive relay
# settings, enforces selectivity coordination, and reports grading margins.
#
# Usage
# -----
#   cd /root/phd_thesis/sambp/sambp_sync_oc
#   python run_multi_gen.py                     # default: 2 generators, 3PH
#   python run_multi_gen.py --n-gen 3 --fault LL
#   python run_multi_gen.py --fault SLG --Rf 0.1
#
# Outputs
# -------
#   outputs/multi_gen/multi_gen_results.csv
#   outputs/plots/multi_gen/fig_multi_gen_coordination.pdf/.png
# =============================================================================

import argparse
import copy
import os
import sys
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
from config.system_config import SYSTEM_CONFIG
from config.relay_config   import RELAY_CONFIG, MULTI_GEN_CONFIG

from models.multi_gen_model import simulate_multi_gen_fault
from models.relay_oc_model  import compute_relay_current_rms, run_overcurrent_relay
from models.reduced_source_model import DEFAULT_THETA

from signal_processing.event_detection import detect_event_time
from signal_processing.preprocessing   import extract_event_window
from signal_processing.smoothing        import smooth_signal

from inverse_estimation.parameter_estimator import (
    estimate_reduced_source_parameters_two_pass,
    DEFAULT_BOUNDS,
    _build_bounds,
)
from inverse_estimation.sequence_estimator  import estimate_sequence_parameters
from inverse_estimation.sensitivity_analysis import compute_jacobian_condition_number
from inverse_estimation.confidence_logic     import (
    compute_confidence_score, accept_adaptation,
)
from adaptation.adaptive_mapping   import map_source_estimate_to_oc_settings
from adaptation.bounded_update     import apply_bounded_update
from adaptation.coordination_logic import (
    check_selectivity, enforce_selectivity,
    check_time_grading, enforce_time_grading,
    compute_coordination_metrics,
)
from evaluation.metrics import compute_protection_metrics
from io_utils.csv_io    import save_waveform_csv


# ===========================================================================
# Generator parameter variants
# ===========================================================================

def _build_gen_params_list(n_gen, base_params, variation_pct=10.0):
    """
    Build a list of generator parameter dicts with slight Xdpp variation.

    Generator 0 uses base_params exactly.  Generators 1..N-1 have Xdpp
    varied by +/- variation_pct% to produce non-identical fault currents,
    which is realistic for machines from different manufacturers or at
    different loading levels.
    """
    params_list = []
    for k in range(n_gen):
        p = copy.deepcopy(base_params)
        if k > 0:
            delta = variation_pct / 100.0 * (1 if k % 2 == 0 else -1)
            p["Xdpp_pu"] = float(base_params["Xdpp_pu"] * (1.0 + delta * k))
            p["Xdp_pu"]  = float(base_params["Xdp_pu"]  * (1.0 + delta * k * 0.5))
        params_list.append(p)
    return params_list


# ===========================================================================
# Per-generator estimation pipeline
# ===========================================================================

def _estimate_and_adapt(gen_idx, t, ia, ib, ic, t0, fault_type, cfg,
                        relay_cfg_k, freq_hz):
    """
    Run steps 4–8 of the main pipeline for one generator's fault current.

    Returns dict with theta_hat, gamma, proposed relay settings.
    """
    # --- Event window ---
    clear_time = cfg.get("clear_time", t0 + 0.15)
    post_s     = min(0.20, clear_time - t0 - 0.005)
    window     = extract_event_window(t, {"ia": ia, "ib": ib, "ic": ic},
                                      t0, pre_s=0.002, post_s=post_s)
    t_w  = window["t"]
    ia_w = smooth_signal(window["ia"], method="savgol")
    ib_w = smooth_signal(window["ib"], method="savgol")
    ic_w = smooth_signal(window["ic"], method="savgol")

    initial_guess = {**DEFAULT_THETA, "t0": t0}

    # --- Estimation ---
    if fault_type == "3PH":
        est = estimate_reduced_source_parameters_two_pass(
            t_window=t_w, ia_meas=ia_w, ib_meas=ib_w, ic_meas=ic_w,
            initial_guess=initial_guess, bounds=DEFAULT_BOUNDS,
            frequency_hz=freq_hz,
        )
        theta_hat = est["theta_hat"]
    else:
        seq_est = estimate_sequence_parameters(
            t_window=t_w, ia_meas=ia_w, ib_meas=ib_w, ic_meas=ic_w,
            fault_type=fault_type, initial_guess=initial_guess,
            bounds=DEFAULT_BOUNDS, frequency_hz=freq_hz,
        )
        theta_hat = seq_est["theta_pos"]
        est = {
            "theta_hat": theta_hat,
            "success": seq_est["success"],
            "residual_norm": seq_est["residual_norm_total"],
            "jacobian": seq_est["jacobian"],
            "n_evaluations": seq_est.get("n_evaluations", 0),
        }

    # --- Confidence ---
    jac = est.get("jacobian")
    if jac is not None:
        from models.reduced_source_model import THETA_KEYS, theta_to_vector
        J_arr     = np.asarray(jac, dtype=float)
        col_norms = np.linalg.norm(J_arr, axis=0)
        col_norms = np.where(col_norms < 1e-12, 1.0, col_norms)
        J_norm    = J_arr / col_norms[np.newaxis, :]
        cond_num  = compute_jacobian_condition_number(J_norm)
    else:
        cond_num = 1e6

    from models.reduced_source_model import theta_to_vector
    lo, hi  = _build_bounds(DEFAULT_BOUNDS)
    th_vec  = theta_to_vector(theta_hat)
    at_bnd  = np.sum(np.isclose(th_vec, lo, atol=1e-6) |
                     np.isclose(th_vec, hi, atol=1e-6))
    bhf     = float(at_bnd) / len(th_vec)

    plaus = 1.0
    if theta_hat["I_sub"] <= theta_hat["I_ss"]:  plaus -= 0.5
    if not (0.005 <= theta_hat["tau_dc"] <= 0.5): plaus -= 0.3
    if not (0.003 <= theta_hat["tau_ac"] <= 1.0): plaus -= 0.2
    plaus = float(np.clip(plaus, 0.0, 1.0))

    gamma = compute_confidence_score(
        residual_norm              = est["residual_norm"] / max(1, len(t_w)**0.5),
        condition_number           = cond_num,
        bounds_hit_fraction        = bhf,
        parameter_plausibility_score = plaus,
        residual_ref=0.15, cond_good=10.0, cond_bad=500.0,
    )

    # --- Adaptive mapping ---
    threshold = relay_cfg_k.get("confidence_threshold",
                                 RELAY_CONFIG["confidence_threshold"])
    if accept_adaptation(gamma, threshold):
        mapping = map_source_estimate_to_oc_settings(theta_hat, relay_cfg_k)
        update  = apply_bounded_update(
            pickup_proposed = mapping["pickup_proposed"],
            tms_proposed    = mapping["tms_proposed"],
            pickup_current  = relay_cfg_k["pickup_pu"],
            tms_current     = relay_cfg_k["tms"],
            bounds          = relay_cfg_k.get("adaptive_bounds",
                                               RELAY_CONFIG["adaptive_bounds"]),
        )
        pickup_adapt = update["pickup_final"]
        tms_adapt    = update["tms_final"]
        adapted      = True
    else:
        pickup_adapt = relay_cfg_k["pickup_pu"]
        tms_adapt    = relay_cfg_k["tms"]
        adapted      = False

    return {
        "gen_idx":       gen_idx,
        "theta_hat":     theta_hat,
        "gamma":         gamma,
        "adapted":       adapted,
        "cond_num":      cond_num,
        "pickup_fixed":  relay_cfg_k["pickup_pu"],
        "tms_fixed":     relay_cfg_k["tms"],
        "pickup_adapt":  pickup_adapt,
        "tms_adapt":     tms_adapt,
    }


# ===========================================================================
# Main study
# ===========================================================================

def run_multi_gen_study(n_gen=2, fault_type="3PH", fault_R_pu=0.01,
                        fault_time=0.10):
    """
    Run the full multi-generator coordination study.

    Returns
    -------
    dict with keys:
        gen_results     : list[dict]  — per-generator estimation + settings
        fixed_settings  : list[dict]  — before adaptation
        adaptive_before : list[dict]  — after adaptation, before coordination
        adaptive_after  : list[dict]  — after adaptation + coordination
        coord_fixed     : dict        — coordination metrics for fixed settings
        coord_before    : dict        — coordination metrics before coordination
        coord_after     : dict        — coordination metrics after coordination
    """
    cfg    = copy.deepcopy(SYSTEM_CONFIG)
    cfg["network"]["fault_R_pu"] = fault_R_pu
    freq_hz = cfg["frequency_hz"]
    fs      = cfg["sampling_hz"]

    # --- Build generator parameter list ---
    gen_params_list = _build_gen_params_list(n_gen, cfg["generator"])

    print(f"[multi_gen] {n_gen} generators | fault={fault_type} | "
          f"Rf={fault_R_pu} pu | t_fault={fault_time} s")

    # --- Simulate multi-generator fault ---
    t = np.arange(cfg["t_start"], cfg["t_end"], 1.0 / fs)

    bus_config = {
        "transformer_X_pu":  MULTI_GEN_CONFIG["transformer_X_pu"][:n_gen],
        "transformer_R_pu":  MULTI_GEN_CONFIG["transformer_R_pu"][:n_gen],
        "include_transformer": True,
    }

    multi_sim = simulate_multi_gen_fault(
        time_s          = t,
        frequency_hz    = freq_hz,
        fault_time_s    = fault_time,
        fault_type      = fault_type,
        gen_params_list = gen_params_list,
        network_params  = cfg["network"],
        bus_config      = bus_config,
    )

    # --- Event detection on generator 0 (reference) ---
    ia0 = multi_sim["gen_0"]["ia"]
    ib0 = multi_sim["gen_0"]["ib"]
    ic0 = multi_sim["gen_0"]["ic"]
    t0_det = detect_event_time(t, ia0, ib0, ic0,
                                method="rms_jump", threshold=0.2,
                                frequency_hz=freq_hz)
    t0 = t0_det if t0_det is not None else fault_time
    print(f"[multi_gen] Detected t0 = {t0:.4f} s")

    # --- Per-generator relay configs ---
    gen_relay_cfgs = MULTI_GEN_CONFIG["gen_relay_settings"][:n_gen]
    # Pad if n_gen > configured
    while len(gen_relay_cfgs) < n_gen:
        gen_relay_cfgs.append(copy.deepcopy(RELAY_CONFIG))
    for rc in gen_relay_cfgs:
        rc.setdefault("adaptive_bounds", RELAY_CONFIG["adaptive_bounds"])
        rc.setdefault("confidence_threshold", RELAY_CONFIG["confidence_threshold"])

    # --- Per-generator estimation + adaptation ---
    gen_results = []
    for k in range(n_gen):
        sim_k = multi_sim[f"gen_{k}"]
        res_k = _estimate_and_adapt(
            gen_idx    = k,
            t          = t,
            ia         = sim_k["ia"],
            ib         = sim_k["ib"],
            ic         = sim_k["ic"],
            t0         = t0,
            fault_type = fault_type,
            cfg        = cfg,
            relay_cfg_k = gen_relay_cfgs[k],
            freq_hz    = freq_hz,
        )
        gen_results.append(res_k)
        print(f"  Gen {k}: γ={res_k['gamma']:.3f}  adapted={res_k['adapted']}  "
              f"pickup_adapt={res_k['pickup_adapt']:.3f}  tms_adapt={res_k['tms_adapt']:.4f}")

    # --- Bus relay (downstream of all generator relays) ---
    bus_relay_cfg = copy.deepcopy(MULTI_GEN_CONFIG["bus_relay"])

    # --- Build relay settings lists (upstream = generator relays, downstream = bus relay) ---
    fixed_settings = [
        {"pickup_pu": r["pickup_fixed"], "tms": r["tms_fixed"],
         "label": f"Gen {r['gen_idx']} (fixed)"}
        for r in gen_results
    ] + [{"pickup_pu": bus_relay_cfg["pickup_pu"], "tms": bus_relay_cfg["tms"],
          "label": "Bus relay"}]

    adaptive_before = [
        {"pickup_pu": r["pickup_adapt"], "tms": r["tms_adapt"],
         "label": f"Gen {r['gen_idx']} (adaptive)"}
        for r in gen_results
    ] + [{"pickup_pu": bus_relay_cfg["pickup_pu"], "tms": bus_relay_cfg["tms"],
          "label": "Bus relay"}]

    # --- Enforce selectivity and time grading on adaptive settings ---
    adaptive_after = enforce_selectivity(
        adaptive_before,
        delta_I_margin_pu = MULTI_GEN_CONFIG["delta_I_margin_pu"],
        pickup_max_pu     = RELAY_CONFIG["adaptive_bounds"]["pickup_max_pu"],
    )
    # Estimate minimum fault current (single-gen, max Rf)
    # For coordination purposes use a conservative I_fault_min based on rated pickup
    I_fault_min = min(r["pickup_adapt"] for r in gen_results) * 1.2
    adaptive_after = enforce_time_grading(
        adaptive_after,
        I_fault_min_pu  = I_fault_min,
        delta_t_grade_s = MULTI_GEN_CONFIG["delta_t_grade_s"],
        tms_min         = RELAY_CONFIG["adaptive_bounds"]["tms_min"],
        tms_max         = RELAY_CONFIG["adaptive_bounds"]["tms_max"],
    )

    # --- Coordination metrics ---
    coord_fixed  = compute_coordination_metrics(
        fixed_settings,   I_fault_min,
        MULTI_GEN_CONFIG["delta_I_margin_pu"],
        MULTI_GEN_CONFIG["delta_t_grade_s"],
    )
    coord_before = compute_coordination_metrics(
        adaptive_before,  I_fault_min,
        MULTI_GEN_CONFIG["delta_I_margin_pu"],
        MULTI_GEN_CONFIG["delta_t_grade_s"],
    )
    coord_after  = compute_coordination_metrics(
        adaptive_after,   I_fault_min,
        MULTI_GEN_CONFIG["delta_I_margin_pu"],
        MULTI_GEN_CONFIG["delta_t_grade_s"],
    )

    print("\n[multi_gen] Coordination results:")
    print(f"  Fixed    — selectivity_ok={coord_fixed['selectivity_ok']}, "
          f"grading_ok={coord_fixed['grading_ok']}")
    print(f"  Before   — selectivity_ok={coord_before['selectivity_ok']}, "
          f"grading_ok={coord_before['grading_ok']}")
    print(f"  After    — selectivity_ok={coord_after['selectivity_ok']}, "
          f"grading_ok={coord_after['grading_ok']}")

    return {
        "gen_results":     gen_results,
        "fixed_settings":  fixed_settings,
        "adaptive_before": adaptive_before,
        "adaptive_after":  adaptive_after,
        "coord_fixed":     coord_fixed,
        "coord_before":    coord_before,
        "coord_after":     coord_after,
        "I_fault_min":     I_fault_min,
    }


# ===========================================================================
# Plot
# ===========================================================================

def plot_coordination(study, out_dir, fault_type, n_gen):
    """
    Two-panel figure:
    Left:  Pickup settings (bar chart) — fixed / adaptive-before / adaptive-after
    Right: Trip times at I_fault_min — three groups
    """
    labels = [s["label"] for s in study["fixed_settings"]]
    n = len(labels)
    x = np.arange(n)
    w = 0.25

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    # --- Panel A: pickup ---
    ax = axes[0]
    p_fixed  = [s["pickup_pu"] for s in study["fixed_settings"]]
    p_before = [s["pickup_pu"] for s in study["adaptive_before"]]
    p_after  = [s["pickup_pu"] for s in study["adaptive_after"]]

    ax.bar(x - w,   p_fixed,  width=w, label="Fixed",    color="#aec6e8", edgecolor="k")
    ax.bar(x,       p_before, width=w, label="Adaptive (before coord.)",
           color="#ff9f9a", edgecolor="k")
    ax.bar(x + w,   p_after,  width=w, label="Adaptive (after coord.)",
           color="#98df8a", edgecolor="k")

    # Margin requirement line between pairs
    delta = study["adaptive_after"][0]["pickup_pu"]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=8)
    ax.set_ylabel("Pickup (pu)", fontsize=9)
    ax.set_title("Relay Pickup Settings", fontsize=10)
    ax.legend(fontsize=7)
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    # --- Panel B: trip times ---
    ax2 = axes[1]
    def _clip_t(times):
        return [min(t, 10.0) if np.isfinite(t) else 10.0 for t in times]

    tt_fixed  = _clip_t(study["coord_fixed"]["trip_times"])
    tt_before = _clip_t(study["coord_before"]["trip_times"])
    tt_after  = _clip_t(study["coord_after"]["trip_times"])

    ax2.bar(x - w,  tt_fixed,  width=w, label="Fixed",    color="#aec6e8", edgecolor="k")
    ax2.bar(x,      tt_before, width=w, label="Before",   color="#ff9f9a", edgecolor="k")
    ax2.bar(x + w,  tt_after,  width=w, label="After",    color="#98df8a", edgecolor="k")

    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=15, ha="right", fontsize=8)
    ax2.set_ylabel(f"Trip time at I_min={study['I_fault_min']:.2f} pu (s)", fontsize=9)
    ax2.set_title("Trip Time Grading", fontsize=10)
    ax2.legend(fontsize=7)
    ax2.grid(axis="y", linestyle=":", alpha=0.5)
    ax2.set_ylim([0, max(max(tt_fixed), max(tt_before), max(tt_after)) * 1.2 + 0.1])

    fig.suptitle(
        f"Multi-Generator Coordination — {n_gen} generators, "
        f"{fault_type} fault",
        fontsize=11,
    )
    fig.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, "fig_multi_gen_coordination.pdf")
    png_path = os.path.join(out_dir, "fig_multi_gen_coordination.png")
    fig.savefig(pdf_path, bbox_inches="tight", dpi=300)
    fig.savefig(png_path, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"\n[multi_gen] Plot → {pdf_path}")
    return pdf_path, png_path


# ===========================================================================
# Save CSV
# ===========================================================================

def save_results_csv(study, csv_path):
    import csv
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    rows = []
    for k, gr in enumerate(study["gen_results"]):
        rows.append({
            "relay":          f"Gen_{k}",
            "gamma":          f"{gr['gamma']:.4f}",
            "adapted":        gr["adapted"],
            "pickup_fixed":   gr["pickup_fixed"],
            "tms_fixed":      gr["tms_fixed"],
            "pickup_before":  study["adaptive_before"][k]["pickup_pu"],
            "tms_before":     study["adaptive_before"][k]["tms"],
            "pickup_after":   study["adaptive_after"][k]["pickup_pu"],
            "tms_after":      study["adaptive_after"][k]["tms"],
        })
    # Bus relay
    k = len(study["gen_results"])
    rows.append({
        "relay":         "Bus",
        "gamma":         "N/A",
        "adapted":       False,
        "pickup_fixed":  study["fixed_settings"][k]["pickup_pu"],
        "tms_fixed":     study["fixed_settings"][k]["tms"],
        "pickup_before": study["adaptive_before"][k]["pickup_pu"],
        "tms_before":    study["adaptive_before"][k]["tms"],
        "pickup_after":  study["adaptive_after"][k]["pickup_pu"],
        "tms_after":     study["adaptive_after"][k]["tms"],
    })

    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[multi_gen] CSV  → {csv_path}")


# ===========================================================================
# CLI entry point
# ===========================================================================

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Multi-generator busbar coordination study."
    )
    parser.add_argument("--n-gen",  type=int,   default=2,
                        help="Number of parallel generators (default 2)")
    parser.add_argument("--fault",  type=str,   default="3PH",
                        choices=["3PH", "LL", "SLG"],
                        help="Fault type (default 3PH)")
    parser.add_argument("--Rf",     type=float, default=0.01,
                        help="Fault resistance pu (default 0.01)")
    parser.add_argument("--no-plots", action="store_true",
                        help="Skip plot generation")
    return parser.parse_args()


if __name__ == "__main__":
    args  = _parse_args()
    study = run_multi_gen_study(
        n_gen      = args.n_gen,
        fault_type = args.fault,
        fault_R_pu = args.Rf,
    )

    out_plots = os.path.join("outputs", "plots", "multi_gen")
    out_csv   = os.path.join("outputs", "multi_gen", "multi_gen_results.csv")

    if not args.no_plots:
        plot_coordination(study, out_plots, args.fault, args.n_gen)

    save_results_csv(study, out_csv)
    print("\n[multi_gen] Done.")
