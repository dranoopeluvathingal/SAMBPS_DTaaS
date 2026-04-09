# =============================================================================
# sambp / sambp_sync_oc
# plot_milestone1.py
#
# Paper-quality Milestone 1 figures:
#   Fig 1 — Measured vs fitted waveform (Phase A, 3PH case)
#   Fig 2 — DC offset identification (measured vs model, all 3 phases)
#   Fig 3 — Relay response: I_rms + fixed / adaptive pickup thresholds
#   Fig 4 — Parameter estimation summary table (all 3 cases)
#   Fig 5 — Confidence score bar chart (all 3 cases)
#
# Usage
#   python plot_milestone1.py
# =============================================================================

import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import matplotlib.ticker as ticker

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
mplstyle = os.path.join(os.path.dirname(__file__), "..", "..", "thesis_v2.mplstyle")
if os.path.exists(mplstyle):
    plt.style.use(mplstyle)
else:
    plt.rcParams.update({
        "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 10,
        "legend.fontsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "lines.linewidth": 1.0, "figure.dpi": 150,
        "axes.spines.top": False, "axes.spines.right": False,
    })

PLOT_DIR = os.path.join("outputs", "plots", "milestone1")
os.makedirs(PLOT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Re-run the pipeline for the primary case to capture window + model output
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

from config.system_config   import SYSTEM_CONFIG
from config.relay_config    import RELAY_CONFIG
from config.study_cases     import STUDY_CASES
from models.sync_generator_model import simulate_sync_generator_currents
from models.relay_oc_model        import compute_relay_current_rms, run_overcurrent_relay
from models.reduced_source_model  import DEFAULT_THETA, reduced_sync_current_model
from signal_processing.event_detection import detect_event_time
from signal_processing.preprocessing   import extract_event_window
from signal_processing.smoothing        import smooth_signal
from inverse_estimation.parameter_estimator import (
    estimate_reduced_source_parameters_two_pass,
    DEFAULT_BOUNDS, _build_bounds,
)
from inverse_estimation.sensitivity_analysis import compute_jacobian_condition_number
from inverse_estimation.confidence_logic     import compute_confidence_score
from adaptation.adaptive_mapping  import map_source_estimate_to_oc_settings
from adaptation.bounded_update    import apply_bounded_update


def _run_silent(case_idx):
    """Run pipeline for one case and return all data needed for plots."""
    case       = STUDY_CASES[case_idx]
    cfg        = {**SYSTEM_CONFIG}
    cfg["network"] = {**SYSTEM_CONFIG["network"]}
    cfg["network"]["fault_R_pu"] = case.get("fault_R_pu",
                                             SYSTEM_CONFIG["network"]["fault_R_pu"])
    fault_time = case.get("fault_time", cfg["fault_time"])
    fault_type = case["fault_type"]

    fs = cfg["sampling_hz"]
    t  = np.arange(cfg["t_start"], cfg["t_end"], 1.0 / fs)
    sim = simulate_sync_generator_currents(
        t, cfg["frequency_hz"], fault_time, fault_type,
        cfg["generator"], cfg["network"],
    )
    ia, ib, ic = sim["ia"], sim["ib"], sim["ic"]
    i_rms = compute_relay_current_rms(t, ia, ib, ic, frequency_hz=cfg["frequency_hz"])

    fixed_relay = run_overcurrent_relay(
        t, i_rms,
        pickup_pu      = RELAY_CONFIG["pickup_pu"],
        inst_pickup_pu = RELAY_CONFIG["inst_pickup_pu"],
        tms            = RELAY_CONFIG["tms"],
        curve_type     = RELAY_CONFIG["curve_type"],
    )

    t0 = detect_event_time(t, ia, ib, ic, method="rms_jump",
                           threshold=0.2, frequency_hz=cfg["frequency_hz"])
    if t0 is None:
        t0 = fault_time

    clear_time = cfg.get("clear_time", t0 + 0.15)
    post_s     = min(0.20, clear_time - t0 - 0.005)
    window     = extract_event_window(t, {"ia": ia, "ib": ib, "ic": ic},
                                      t0, pre_s=0.002, post_s=post_s)
    t_w   = window["t"]
    ia_w  = smooth_signal(window["ia"], method="savgol")
    ib_w  = smooth_signal(window["ib"], method="savgol")
    ic_w  = smooth_signal(window["ic"], method="savgol")

    est = estimate_reduced_source_parameters_two_pass(
        t_w, ia_w, ib_w, ic_w,
        initial_guess = {**DEFAULT_THETA, "t0": t0},
        bounds        = DEFAULT_BOUNDS,
        frequency_hz  = cfg["frequency_hz"],
    )
    theta_hat = est["theta_hat"]

    model_out = reduced_sync_current_model(t_w, theta_hat, cfg["frequency_hz"])

    # Condition number (column-normalised)
    jac = est["jacobian"]
    if jac is not None:
        J      = np.asarray(jac, dtype=float)
        cnorms = np.linalg.norm(J, axis=0)
        cnorms = np.where(cnorms < 1e-12, 1.0, cnorms)
        cond_num = compute_jacobian_condition_number(J / cnorms[np.newaxis, :])
    else:
        cond_num = 1e6

    lo, hi  = _build_bounds(DEFAULT_BOUNDS)
    from models.reduced_source_model import theta_to_vector
    th_vec  = theta_to_vector(theta_hat)
    at_bnd  = np.sum(np.isclose(th_vec, lo, atol=1e-6) | np.isclose(th_vec, hi, atol=1e-6))
    bhf     = float(at_bnd) / len(th_vec)

    plausibility = 1.0
    if theta_hat["I_sub"] <= theta_hat["I_ss"]:
        plausibility -= 0.5
    if not (0.005 <= theta_hat["tau_dc"] <= 0.5):
        plausibility -= 0.3
    if not (0.003 <= theta_hat["tau_ac"] <= 1.0):
        plausibility -= 0.2
    plausibility = float(np.clip(plausibility, 0.0, 1.0))

    gamma = compute_confidence_score(
        residual_norm              = est["residual_norm"] / max(1, len(t_w)**0.5),
        condition_number           = cond_num,
        bounds_hit_fraction        = bhf,
        parameter_plausibility_score = plausibility,
        residual_ref = 0.15, cond_good = 10.0, cond_bad = 500.0,
    )

    mapping = map_source_estimate_to_oc_settings(theta_hat, RELAY_CONFIG)
    update  = apply_bounded_update(
        pickup_proposed = mapping["pickup_proposed"],
        tms_proposed    = mapping["tms_proposed"],
        pickup_current  = RELAY_CONFIG["pickup_pu"],
        tms_current     = RELAY_CONFIG["tms"],
        bounds          = RELAY_CONFIG["adaptive_bounds"],
    )

    adaptive_relay = run_overcurrent_relay(
        t, i_rms,
        pickup_pu      = update["pickup_final"],
        inst_pickup_pu = RELAY_CONFIG["inst_pickup_pu"],
        tms            = update["tms_final"],
        curve_type     = RELAY_CONFIG["curve_type"],
    )

    # Residual component sub-scores
    rmse = est["residual_norm"] / max(1, len(t_w)**0.5)
    from inverse_estimation.confidence_logic import (
        _score_residual, _score_condition, _score_bounds,
    )
    subscores = {
        "s_r": _score_residual(rmse, 0.15),
        "s_c": _score_condition(cond_num, 10.0, 500.0),
        "s_b": _score_bounds(bhf),
        "s_p": plausibility,
    }

    return {
        "case":           case,
        "t":              t,
        "ia":             ia, "ib": ib, "ic": ic,
        "i_rms":          i_rms,
        "t_w":            t_w,
        "ia_w":           ia_w, "ib_w": ib_w, "ic_w": ic_w,
        "model_out":      model_out,
        "theta_hat":      theta_hat,
        "pass1_theta":    est.get("pass1_theta_hat", theta_hat),
        "gamma":          gamma,
        "subscores":      subscores,
        "cond_num":       cond_num,
        "rmse_phaseA":    float(np.sqrt(np.mean((ia_w - model_out["ia"])**2))),
        "r2_phaseA":      float(1 - np.var(ia_w - model_out["ia"]) / (np.var(ia_w) + 1e-14)),
        "fixed_relay":    fixed_relay,
        "adaptive_relay": adaptive_relay,
        "pickup_fixed":   RELAY_CONFIG["pickup_pu"],
        "pickup_adapt":   update["pickup_final"],
        "tms_fixed":      RELAY_CONFIG["tms"],
        "tms_adapt":      update["tms_final"],
        "fault_time":     fault_time,
        "freq":           cfg["frequency_hz"],
    }


# ===========================================================================
# Collect all case data
# ===========================================================================
print("Running pipeline for all 3 cases...")
cases_data = [_run_silent(i) for i in range(3)]
print("Done. Generating figures...")


# ===========================================================================
# Fig 1 — Measured vs Fitted Waveform (Phase A, 3PH case)
# ===========================================================================
def fig1_waveform_fit(d, savepath):
    t_w = d["t_w"] * 1000   # ms
    ia_m = d["ia_w"]
    ia_f = d["model_out"]["ia"]
    residual = ia_m - ia_f

    fig, axes = plt.subplots(2, 1, figsize=(8, 5), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1]})

    ax = axes[0]
    ax.plot(t_w, ia_m, lw=1.0, color="tab:blue",
            label="Measured $i_a$ (smoothed)")
    ax.plot(t_w, ia_f, lw=1.2, color="tab:red", ls="--",
            label=f"Model fit  ($R^2={d['r2_phaseA']:.4f}$)")
    ax.set_ylabel("Phase A current (pu)")
    ax.legend(loc="upper right")
    ax.grid(True, lw=0.3, alpha=0.6)
    ax.axvline(d["fault_time"]*1000, color="gray", lw=0.8, ls=":", label="Fault")

    # Annotate estimated parameters
    th = d["theta_hat"]
    txt = (f"$\\hat{{I}}_{{\\rm sub}}$ = {th['I_sub']:.3f} pu\n"
           f"$\\hat{{I}}_{{\\rm ss}}$ = {th['I_ss']:.3f} pu\n"
           f"$\\hat{{\\tau}}_{{\\rm ac}}$ = {th['tau_ac']*1e3:.1f} ms\n"
           f"$\\hat{{\\tau}}_{{\\rm dc}}$ = {th['tau_dc']*1e3:.1f} ms\n"
           f"$\\hat{{\\phi}}_a$ = {th['phi_a']:.3f} rad")
    ax.text(0.02, 0.97, txt, transform=ax.transAxes, va="top",
            fontsize=7.5, family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="gray", alpha=0.85))

    ax2 = axes[1]
    ax2.plot(t_w, residual, lw=0.8, color="tab:gray")
    ax2.axhline(0, color="black", lw=0.5)
    ax2.set_ylabel("Residual (pu)")
    ax2.set_xlabel("Time (ms)")
    ax2.grid(True, lw=0.3, alpha=0.6)

    fig.suptitle("Phase A Inverse Estimation — 3-Phase Fault (low $R_f$)", y=1.01)
    fig.tight_layout()
    fig.savefig(savepath, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {savepath}")


# ===========================================================================
# Fig 2 — DC offset: 3-phase measured vs 3-phase model (envelope + DC)
# ===========================================================================
def fig2_dc_identification(d, savepath):
    t_w = d["t_w"] * 1000
    labels = ["Phase A", "Phase B", "Phase C"]
    meas   = [d["ia_w"],  d["ib_w"],  d["ic_w"]]
    model  = [d["model_out"]["ia"], d["model_out"]["ib"], d["model_out"]["ic"]]
    colors = ["tab:blue", "tab:orange", "tab:green"]

    fig, axes = plt.subplots(3, 1, figsize=(8, 7), sharex=True)
    for ax, lbl, mi, mo, col in zip(axes, labels, meas, model, colors):
        ax.plot(t_w, mi, lw=0.9, color=col, alpha=0.85, label=f"Measured {lbl}")
        ax.plot(t_w, mo, lw=1.3, color="black", ls="--", alpha=0.7,
                label="Model (phase-A params)")
        ax.set_ylabel(f"{lbl}\n(pu)")
        ax.legend(loc="upper right", fontsize=7)
        ax.grid(True, lw=0.3, alpha=0.6)

    axes[-1].set_xlabel("Time (ms)")
    fig.suptitle("Three-Phase Waveform Reconstruction from Phase-A Estimation", y=1.01)
    fig.tight_layout()
    fig.savefig(savepath, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {savepath}")


# ===========================================================================
# Fig 3 — Relay response: I_rms + fixed/adaptive pickup thresholds
# ===========================================================================
def fig3_relay_response(d, savepath):
    t_ms  = d["t"] * 1000
    i_rms = d["i_rms"]
    fr    = d["fixed_relay"]
    ar    = d["adaptive_relay"]

    # Zoom around fault
    mask  = (d["t"] >= 0.07) & (d["t"] <= 0.60)
    tm    = t_ms[mask]
    irm   = i_rms[mask]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(tm, irm, lw=1.0, color="tab:blue", label="$I_{\\rm rms}$ (1-cycle)")

    # Pickup thresholds
    ax.axhline(d["pickup_fixed"],  color="tab:blue",   lw=1.2, ls="-.",
               label=f"Fixed pickup = {d['pickup_fixed']:.3f} pu")
    ax.axhline(d["pickup_adapt"],  color="tab:orange",  lw=1.2, ls="-.",
               label=f"Adaptive pickup = {d['pickup_adapt']:.3f} pu")
    ax.axhline(RELAY_CONFIG["inst_pickup_pu"], color="tab:red", lw=1.0, ls=":",
               label=f"Inst. pickup = {RELAY_CONFIG['inst_pickup_pu']:.1f} pu")

    # Trip time markers
    for rly, col, lbl in [
        (fr, "tab:blue",   f"Fixed trip {fr['trip_time']*1000:.1f} ms"),
        (ar, "tab:orange", f"Adaptive trip {ar['trip_time']*1000:.1f} ms"),
    ]:
        if rly["trip_time"]:
            ax.axvline(rly["trip_time"]*1000, color=col, lw=1.5, ls="--", label=lbl)

    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("$I_{\\rm rms}$ (pu)")
    ax.set_title(f"OC Relay Response — {d['case']['case_name'].replace('_',' ')}")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, lw=0.3, alpha=0.6)
    fig.tight_layout()
    fig.savefig(savepath, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {savepath}")


# ===========================================================================
# Fig 4 — Parameter table (all 3 cases)
# ===========================================================================
def fig4_parameter_table(cases_data, savepath):
    rows = []
    row_labels = []
    truth_3ph = {
        "I_sub":  1.0 / (0.20 + 0.15),   # V/(Xd''+X_th)
        "I_ss":   "—",                     # within-window I_tr ≈ V/(Xd'+X_th)
        "tau_ac": 0.03,
        "tau_dc": 0.35 / (2*np.pi*50*0.02),
        "phi_a":  np.pi/2,
    }
    keys     = ["I_sub", "I_ss", "tau_ac", "tau_dc", "phi_a"]
    col_hdrs = ["$\\hat{I}_{\\rm sub}$ (pu)", "$\\hat{I}_{\\rm ss}$ (pu)",
                "$\\hat{\\tau}_{\\rm ac}$ (ms)", "$\\hat{\\tau}_{\\rm dc}$ (ms)",
                "$\\hat{\\phi}_a$ (rad)"]

    for d in cases_data:
        th = d["theta_hat"]
        rows.append([
            f"{th['I_sub']:.3f}",
            f"{th['I_ss']:.3f}",
            f"{th['tau_ac']*1000:.2f}",
            f"{th['tau_dc']*1000:.2f}",
            f"{th['phi_a']:.4f}",
        ])
        row_labels.append(d["case"]["case_name"].replace("_", "\n"))

    # Append truth row
    rows.append([
        f"{truth_3ph['I_sub']:.3f}",
        "≈ I_tr",
        f"{truth_3ph['tau_ac']*1000:.2f}",
        f"{truth_3ph['tau_dc']*1000:.2f}",
        f"{np.pi/2:.4f}",
    ])
    row_labels.append("Truth\n(3PH)")

    fig, ax = plt.subplots(figsize=(9, 2.5))
    ax.axis("off")
    tbl = ax.table(
        cellText   = rows,
        rowLabels  = row_labels,
        colLabels  = col_hdrs,
        cellLoc    = "center",
        loc        = "center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    tbl.scale(1.1, 1.6)

    # Shade last row (truth) in light yellow
    n_data_rows = len(rows) - 1   # last row is truth
    for col in range(len(col_hdrs)):
        key = (len(rows), col + 1)
        if key in tbl._cells:
            tbl._cells[key].set_facecolor("#FFFDE7")

    ax.set_title("Table I — Estimated Source Parameters (Two-Pass Phase-A Fit)",
                 pad=18, fontsize=10)
    fig.tight_layout()
    fig.savefig(savepath, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {savepath}")


# ===========================================================================
# Fig 5 — Confidence score breakdown (bar chart)
# ===========================================================================
def fig5_confidence_bars(cases_data, savepath):
    n      = len(cases_data)
    labels = [d["case"]["case_name"].replace("_", "\n") for d in cases_data]
    w_r, w_c, w_b, w_p = 0.35, 0.30, 0.20, 0.15

    s_r = [d["subscores"]["s_r"] for d in cases_data]
    s_c = [d["subscores"]["s_c"] for d in cases_data]
    s_b = [d["subscores"]["s_b"] for d in cases_data]
    s_p = [d["subscores"]["s_p"] for d in cases_data]

    x   = np.arange(n)
    fig, ax = plt.subplots(figsize=(7, 4))

    b1 = ax.bar(x, [w_r*v for v in s_r], label=f"$w_r \\cdot s_r$ (residual, w={w_r})",
                color="tab:blue")
    b2 = ax.bar(x, [w_c*v for v in s_c], bottom=[w_r*v for v in s_r],
                label=f"$w_c \\cdot s_c$ (condition, w={w_c})", color="tab:orange")
    b3 = ax.bar(x, [w_b*v for v in s_b],
                bottom=[w_r*s_r[i] + w_c*s_c[i] for i in range(n)],
                label=f"$w_b \\cdot s_b$ (bounds, w={w_b})", color="tab:green")
    b4 = ax.bar(x, [w_p*v for v in s_p],
                bottom=[w_r*s_r[i] + w_c*s_c[i] + w_b*s_b[i] for i in range(n)],
                label=f"$w_p \\cdot s_p$ (plausibility, w={w_p})", color="tab:purple")

    ax.axhline(RELAY_CONFIG["confidence_threshold"], color="red", lw=1.5, ls="--",
               label=f"Threshold γ = {RELAY_CONFIG['confidence_threshold']}")

    for i, d in enumerate(cases_data):
        ax.text(x[i], d["gamma"] + 0.01, f"γ={d['gamma']:.3f}",
                ha="center", va="bottom", fontsize=8, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Confidence score γ")
    ax.set_ylim(0, 1.1)
    ax.set_title("Confidence Score Breakdown — All Study Cases")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(True, axis="y", lw=0.3, alpha=0.6)
    fig.tight_layout()
    fig.savefig(savepath, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {savepath}")


# ===========================================================================
# Generate all figures
# ===========================================================================
d0 = cases_data[0]   # 3PH low-R as primary case

fig1_waveform_fit(d0,
    os.path.join(PLOT_DIR, "fig1_waveform_fit_phaseA.png"))

fig2_dc_identification(d0,
    os.path.join(PLOT_DIR, "fig2_3phase_reconstruction.png"))

for d in cases_data:
    fig3_relay_response(d,
        os.path.join(PLOT_DIR, f"fig3_relay_{d['case']['case_name']}.png"))

fig4_parameter_table(cases_data,
    os.path.join(PLOT_DIR, "fig4_parameter_table.png"))

fig5_confidence_bars(cases_data,
    os.path.join(PLOT_DIR, "fig5_confidence_scores.png"))

print(f"\nAll Milestone 1 figures saved to {PLOT_DIR}/")
