# =============================================================================
# sambp / sambp_sync_oc
# main_run_case.py
#
# End-to-end pipeline for a single study case.
#
# Usage
# -----
#   python main_run_case.py                        # runs default case index 0
#   python main_run_case.py --case 1               # runs study_cases[1]
#   python main_run_case.py --case 2 --no-plots    # skip plot generation
#
# Pipeline steps
# --------------
#   1.  Load case config
#   2.  Simulate detailed fault waveform
#   3.  Run fixed OC relay
#   4.  Detect event
#   5.  Extract event window
#   6.  Estimate reduced source parameters
#   7.  Compute confidence score
#   8.  If accepted → map to adaptive settings → run adaptive relay
#       Else        → keep fixed settings
#   9.  Compare results (fit + protection metrics)
#   10. Save waveform CSV, summary CSV, metadata, plots
# =============================================================================

import argparse
import os
import sys
import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
from config.system_config import SYSTEM_CONFIG
from config.relay_config   import RELAY_CONFIG
from config.study_cases    import STUDY_CASES

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
from models.sync_generator_model import simulate_sync_generator_currents
from models.relay_oc_model        import (
    compute_relay_current_rms,
    run_overcurrent_relay,
)
from models.reduced_source_model  import DEFAULT_THETA

# ---------------------------------------------------------------------------
# Signal processing
# ---------------------------------------------------------------------------
from signal_processing.event_detection import detect_event_time
from signal_processing.preprocessing   import extract_event_window, normalize_currents
from signal_processing.smoothing        import smooth_signal
from signal_processing.rms_tools        import sliding_rms

# ---------------------------------------------------------------------------
# Inverse estimation
# ---------------------------------------------------------------------------
from inverse_estimation.parameter_estimator import (
    estimate_reduced_source_parameters,
    estimate_reduced_source_parameters_two_pass,
    DEFAULT_BOUNDS,
    _build_bounds,
)
from inverse_estimation.sequence_estimator import estimate_sequence_parameters
from inverse_estimation.sensitivity_analysis import (
    compute_jacobian_condition_number,
    compute_parameter_sensitivities,
)
from inverse_estimation.confidence_logic import (
    compute_confidence_score,
    accept_adaptation,
)

# ---------------------------------------------------------------------------
# Adaptation
# ---------------------------------------------------------------------------
from adaptation.adaptive_mapping import map_source_estimate_to_oc_settings
from adaptation.bounded_update   import apply_bounded_update

# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
from evaluation.metrics    import compute_fit_metrics, compute_protection_metrics
from evaluation.comparison import compare_fixed_vs_adaptive
from evaluation.reporting  import print_case_summary, save_case_summary_csv

# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
from io_utils.csv_io      import save_waveform_csv
from io_utils.case_logger import CaseLogger, log_case_metadata


# ===========================================================================
# Pipeline
# ===========================================================================

def run_case(case, system_cfg=None, relay_cfg=None, save_plots=True, model_stage=1):
    """
    Execute the full pipeline for one study case.

    Parameters
    ----------
    case        : dict — one entry from STUDY_CASES
    system_cfg  : dict or None — defaults to SYSTEM_CONFIG
    relay_cfg   : dict or None — defaults to RELAY_CONFIG
    save_plots  : bool — generate and save waveform + result plots
    model_stage : int  — 1 (Stage 1 synthesis) or 2 (Stage 2 Park dq ODE)

    Returns
    -------
    dict — case_result (input to compare_fixed_vs_adaptive)
    """
    if system_cfg is None:
        system_cfg = SYSTEM_CONFIG
    if relay_cfg is None:
        relay_cfg = RELAY_CONFIG

    case_name = case["case_name"]
    log_dir   = os.path.join("outputs", "logs")

    with CaseLogger(log_dir, case_name, echo=True) as log:

        # ------------------------------------------------------------------
        # STEP 1 — Merge case overrides into system config
        # ------------------------------------------------------------------
        log.log_section("Step 1: Case configuration")
        cfg = {**system_cfg}
        cfg["network"] = {**system_cfg["network"]}
        cfg["network"]["fault_R_pu"] = case.get("fault_R_pu",
                                                  system_cfg["network"]["fault_R_pu"])
        fault_time = case.get("fault_time", cfg["fault_time"])
        fault_type = case["fault_type"]
        log.log_dict(case, title="Case parameters")

        # ------------------------------------------------------------------
        # STEP 2 — Forward simulation
        # ------------------------------------------------------------------
        log.log_section("Step 2: Forward simulation")
        fs   = cfg["sampling_hz"]
        t    = np.arange(cfg["t_start"], cfg["t_end"], 1.0 / fs)

        if model_stage == 2:
            from models.park_dq_model import simulate_park_dq_currents
            sim = simulate_park_dq_currents(
                time_s        = t,
                frequency_hz  = cfg["frequency_hz"],
                fault_time_s  = fault_time,
                fault_type    = fault_type,
                params        = cfg["generator"],
                network_params= cfg["network"],
                park_dq_params= cfg.get("park_dq"),
            )
        else:
            sim  = simulate_sync_generator_currents(
                time_s          = t,
                frequency_hz    = cfg["frequency_hz"],
                fault_time_s    = fault_time,
                fault_type      = fault_type,
                params          = cfg["generator"],
                network_params  = cfg["network"],
            )
        ia, ib, ic = sim["ia"], sim["ib"], sim["ic"]
        va, vb, vc = sim["va"], sim["vb"], sim["vc"]
        log.log(f"Waveform generated: {len(t)} samples at {fs} Hz")

        # ------------------------------------------------------------------
        # STEP 3 — Fixed relay response
        # ------------------------------------------------------------------
        log.log_section("Step 3: Fixed relay response")
        n_cyc  = int(round(fs / cfg["frequency_hz"]))
        i_rms  = compute_relay_current_rms(t, ia, ib, ic,
                                            frequency_hz=cfg["frequency_hz"])
        fixed_relay = run_overcurrent_relay(
            t              = t,
            i_rms          = i_rms,
            pickup_pu      = relay_cfg["pickup_pu"],
            inst_pickup_pu = relay_cfg["inst_pickup_pu"],
            tms            = relay_cfg["tms"],
            curve_type     = relay_cfg["curve_type"],
        )
        log.log(f"Fixed relay trip time : {fixed_relay['trip_time']}")

        # ------------------------------------------------------------------
        # STEP 4 — Event detection
        # ------------------------------------------------------------------
        log.log_section("Step 4: Event detection")
        t0_detected = detect_event_time(t, ia, ib, ic,
                                         method="rms_jump",
                                         threshold=0.2,
                                         frequency_hz=cfg["frequency_hz"])
        log.log(f"Detected t0 = {t0_detected}  (true = {fault_time})")
        t0 = t0_detected if t0_detected is not None else fault_time

        # ------------------------------------------------------------------
        # STEP 5 — Extract event window + smooth
        # ------------------------------------------------------------------
        log.log_section("Step 5: Event window extraction")
        signals = {"ia": ia, "ib": ib, "ic": ic}
        # Window: minimal pre-fault, end just before fault clearance
        clear_time = cfg.get("clear_time", t0 + 0.15)
        post_s = min(0.20, clear_time - t0 - 0.005)
        window  = extract_event_window(t, signals, t0, pre_s=0.002, post_s=post_s)
        t_w     = window["t"]
        ia_w    = smooth_signal(window["ia"], method="savgol")
        ib_w    = smooth_signal(window["ib"], method="savgol")
        ic_w    = smooth_signal(window["ic"], method="savgol")
        log.log(f"Window: {t_w[0]:.4f} → {t_w[-1]:.4f} s  ({len(t_w)} samples)")

        # ------------------------------------------------------------------
        # STEP 6 — Inverse estimation
        #
        # 3PH (balanced): two-pass phase-A estimator directly on ia_w
        # LL / SLG / LLG: sequence-component estimator — decomposes ia/ib/ic
        #   into I1/I2/I0, fits each active sequence, returns theta_pos for
        #   relay adaptation (positive sequence governs the fault current
        #   feeding the protected zone)
        # ------------------------------------------------------------------
        log.log_section("Step 6: Inverse parameter estimation")
        initial_guess = {**DEFAULT_THETA, "t0": t0}

        if fault_type == "3PH":
            est = estimate_reduced_source_parameters_two_pass(
                t_window      = t_w,
                ia_meas       = ia_w,
                ib_meas       = ib_w,
                ic_meas       = ic_w,
                initial_guess = initial_guess,
                bounds        = DEFAULT_BOUNDS,
                frequency_hz  = cfg["frequency_hz"],
            )
            theta_hat = est["theta_hat"]
            log.log(f"[3PH two-pass] converged={est['success']}  "
                    f"cost={est['cost']:.5f}  ‖r‖={est['residual_norm']:.5f}  "
                    f"nfev={est['n_evaluations']}")
        else:
            seq_est = estimate_sequence_parameters(
                t_window      = t_w,
                ia_meas       = ia_w,
                ib_meas       = ib_w,
                ic_meas       = ic_w,
                fault_type    = fault_type,
                initial_guess = initial_guess,
                bounds        = DEFAULT_BOUNDS,
                frequency_hz  = cfg["frequency_hz"],
            )
            # Use positive-sequence parameters for relay adaptation
            theta_hat = seq_est["theta_pos"]
            # Reconstruct est dict to be compatible with Step 7 confidence logic
            est = {
                "theta_hat":     theta_hat,
                "success":       seq_est["success"],
                "cost":          0.5 * seq_est["residual_norm_total"] ** 2,
                "residual_norm": seq_est["residual_norm_total"],
                "jacobian":      seq_est["jacobian"],
                "n_evaluations": seq_est.get("n_evaluations", 0),
                "pass1_theta_hat": seq_est.get("pass1_theta_hat"),
            }
            log.log(f"[{fault_type} seq] converged={seq_est['success']}  "
                    f"‖r‖_total={seq_est['residual_norm_total']:.5f}")
            if seq_est["theta_neg"] is not None:
                log.log_dict(seq_est["theta_neg"],  title="theta_neg")
            if seq_est["theta_zero"] is not None:
                log.log_dict(seq_est["theta_zero"], title="theta_zero")

        if est.get("pass1_theta_hat"):
            log.log_dict(est["pass1_theta_hat"], title="Pass-1 theta_hat")
        log.log_dict(theta_hat, title="Final theta_hat")

        # ------------------------------------------------------------------
        # STEP 7 — Sensitivity + confidence
        # ------------------------------------------------------------------
        log.log_section("Step 7: Sensitivity + confidence")
        from models.reduced_source_model import THETA_KEYS, theta_to_vector

        jac = est["jacobian"]   # pass-1 Jacobian (6-param, full window)

        # Condition number on column-normalised Jacobian.
        # Raw κ(J) is inflated by column scale differences (t0 impulse column
        # vs smooth I_ss column).  Normalising focuses on collinearity only.
        if jac is not None:
            J_arr      = np.asarray(jac, dtype=float)
            col_norms  = np.linalg.norm(J_arr, axis=0)
            col_norms  = np.where(col_norms < 1e-12, 1.0, col_norms)
            J_norm     = J_arr / col_norms[np.newaxis, :]
            cond_num   = compute_jacobian_condition_number(J_norm)
            sens       = compute_parameter_sensitivities(J_norm, THETA_KEYS)
        else:
            cond_num = 1e6
            sens     = {}

        # Bounds-hit fraction: how many params landed on a bound?
        lo, hi = _build_bounds(DEFAULT_BOUNDS)
        th_vec = theta_to_vector(theta_hat)
        at_bound = np.sum(
            np.isclose(th_vec, lo, atol=1e-6) | np.isclose(th_vec, hi, atol=1e-6)
        )
        bounds_hit_fraction = float(at_bound) / len(th_vec)

        # Physics plausibility: key monotonicity and range checks
        plausibility = 1.0
        if theta_hat["I_sub"] <= theta_hat["I_ss"]:
            plausibility -= 0.5   # subtransient must exceed steady-state
        if not (0.005 <= theta_hat["tau_dc"] <= 0.5):
            plausibility -= 0.3
        if not (0.003 <= theta_hat["tau_ac"] <= 1.0):
            plausibility -= 0.2
        plausibility = float(np.clip(plausibility, 0.0, 1.0))

        # Use per-sample RMSE (phase A) as residual metric so that the score
        # is independent of window length.  residual_ref=0.15 pu ≈ acceptable
        # RMSE for a pu-normalised fault current.
        gamma = compute_confidence_score(
            residual_norm              = est["residual_norm"] / max(1, len(t_w)**0.5),
            condition_number           = cond_num,
            bounds_hit_fraction        = bounds_hit_fraction,
            parameter_plausibility_score = plausibility,
            residual_ref               = 0.15,
            cond_good                  = 10.0,
            cond_bad                   = 500.0,
        )
        log.log(f"κ_norm(J)={cond_num:.2f}  RMSE_A={est['residual_norm']/len(t_w)**0.5:.4f}"
                f"  bounds_hit={bounds_hit_fraction:.2f}  plaus={plausibility:.2f}"
                f"  γ={gamma:.4f}")

        # ------------------------------------------------------------------
        # STEP 8 — Adaptive relay (if confidence accepted)
        # ------------------------------------------------------------------
        log.log_section("Step 8: Adaptive relay")
        threshold = relay_cfg["confidence_threshold"]

        if accept_adaptation(gamma, threshold):
            log.log(f"Adaptation ACCEPTED (γ={gamma:.3f} ≥ {threshold})")

            mapping = map_source_estimate_to_oc_settings(theta_hat, relay_cfg)
            update  = apply_bounded_update(
                pickup_proposed = mapping["pickup_proposed"],
                tms_proposed    = mapping["tms_proposed"],
                pickup_current  = relay_cfg["pickup_pu"],
                tms_current     = relay_cfg["tms"],
                bounds          = relay_cfg["adaptive_bounds"],
            )
            pickup_adapt = update["pickup_final"]
            tms_adapt    = update["tms_final"]
            log.log_dict(update, title="Bounded update result")
        else:
            log.log(f"Adaptation REJECTED (γ={gamma:.3f} < {threshold}) — keeping fixed settings")
            pickup_adapt = relay_cfg["pickup_pu"]
            tms_adapt    = relay_cfg["tms"]

        adaptive_relay = run_overcurrent_relay(
            t              = t,
            i_rms          = i_rms,
            pickup_pu      = pickup_adapt,
            inst_pickup_pu = relay_cfg["inst_pickup_pu"],
            tms            = tms_adapt,
            curve_type     = relay_cfg["curve_type"],
        )
        log.log(f"Adaptive relay trip time: {adaptive_relay['trip_time']}")

        # ------------------------------------------------------------------
        # STEP 9 — Compare results
        # ------------------------------------------------------------------
        log.log_section("Step 9: Comparison + metrics")
        from models.reduced_source_model import reduced_sync_current_model
        model_out = reduced_sync_current_model(t_w, theta_hat, cfg["frequency_hz"])
        # Fit metrics: phase A is the estimation target (phase-A-only fit);
        # B/C are reported for information but not used for confidence scoring.
        fit  = compute_fit_metrics(ia_w, model_out["ia"],
                                    ib_w, model_out["ib"],
                                    ic_w, model_out["ic"])
        # Primary fit quality: phase A only
        fit["rmse_phaseA"]  = fit["rmse_a"]
        fit["r2_phaseA"]    = fit["r2_a"]
        prot = compute_protection_metrics(fixed_relay, adaptive_relay)
        log.log_dict(fit,  title="Fit metrics")
        log.log_dict(prot, title="Protection metrics")

        case_result = {
            "case_name":          case_name,
            "fault_type":         fault_type,
            "fault_R_pu":         cfg["network"]["fault_R_pu"],
            "fit_metrics":        fit,
            "protection_metrics": prot,
            "confidence":         gamma,
            "theta_hat":          theta_hat,
            "fixed_settings":     {"pickup_pu": relay_cfg["pickup_pu"],
                                   "tms":       relay_cfg["tms"]},
            "adaptive_settings":  {"pickup_pu": pickup_adapt,
                                   "tms":       tms_adapt},
        }
        summary = compare_fixed_vs_adaptive(case_result)
        print_case_summary(summary)

        # ------------------------------------------------------------------
        # STEP 10 — Save outputs
        # ------------------------------------------------------------------
        log.log_section("Step 10: Saving outputs")

        # Waveform CSV
        wf_path = os.path.join("outputs", "waveforms", f"{case_name}_waveform.csv")
        save_waveform_csv(wf_path, {
            "t": t, "ia": ia, "ib": ib, "ic": ic,
            "va": va, "vb": vb, "vc": vc, "i_rms": i_rms,
        })
        log.log(f"Waveform saved → {wf_path}")

        # Summary CSV
        summary_path = os.path.join("outputs", "tables", f"{case_name}_summary.csv")
        save_case_summary_csv([summary], summary_path)
        log.log(f"Summary  saved → {summary_path}")

        # Metadata
        meta_path = os.path.join("outputs", "logs", f"{case_name}_metadata.txt")
        log_case_metadata(meta_path, {
            "case":             case,
            "theta_hat":        theta_hat,
            "confidence":       gamma,
            "condition_number": cond_num,
            "fit_metrics":      fit,
            "protection":       prot,
            "adaptive_settings": {"pickup_pu": pickup_adapt, "tms": tms_adapt},
        })
        log.log(f"Metadata saved → {meta_path}")

        # Plots
        if save_plots:
            _save_plots(case_name, t, ia, ib, ic, i_rms, t_w,
                        model_out, fixed_relay, adaptive_relay, log)

        log.log_section("Pipeline complete")
        return case_result


# ===========================================================================
# Plot helper
# ===========================================================================

def _save_plots(case_name, t, ia, ib, ic, i_rms, t_w, model_out,
                fixed_relay, adaptive_relay, log):
    """Generate and save waveform + relay comparison plots."""
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
        log.log("matplotlib not available — skipping plots")
        return

    plot_dir = os.path.join("outputs", "plots")
    os.makedirs(plot_dir, exist_ok=True)

    # --- Waveform plot ---
    fig, axes = plt.subplots(3, 1, figsize=(12, 7), sharex=True)
    for ax, sig, lbl in zip(axes, [ia, ib, ic], ["ia", "ib", "ic"]):
        ax.plot(t * 1000, sig, lw=0.8, label=f"Simulated {lbl}")
        ax.set_ylabel(f"{lbl} (pu)")
        ax.legend(loc="upper right", fontsize=7)
        ax.grid(True, lw=0.4)
    axes[-1].set_xlabel("Time (ms)")
    axes[0].set_title(f"Three-phase fault currents — {case_name}")
    wf_fig = os.path.join(plot_dir, f"{case_name}_waveform.png")
    fig.tight_layout()
    fig.savefig(wf_fig, dpi=150)
    plt.close(fig)
    log.log(f"Waveform plot → {wf_fig}")

    # --- RMS + relay comparison plot ---
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(t * 1000, i_rms, lw=1.0, label="I_rms")
    if fixed_relay["trip_time"]:
        ax.axvline(fixed_relay["trip_time"] * 1000, color="tab:blue",
                   ls="--", lw=1.2, label=f"Fixed trip {fixed_relay['trip_time']*1000:.1f} ms")
    if adaptive_relay["trip_time"]:
        ax.axvline(adaptive_relay["trip_time"] * 1000, color="tab:orange",
                   ls="--", lw=1.2, label=f"Adaptive trip {adaptive_relay['trip_time']*1000:.1f} ms")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("I_rms (pu)")
    ax.set_title(f"Relay response — {case_name}")
    ax.legend(fontsize=8)
    ax.grid(True, lw=0.4)
    rly_fig = os.path.join(plot_dir, f"{case_name}_relay.png")
    fig.tight_layout()
    fig.savefig(rly_fig, dpi=150)
    plt.close(fig)
    log.log(f"Relay plot   → {rly_fig}")


# ===========================================================================
# CLI entry point
# ===========================================================================

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Run one sambp_sync_oc study case end-to-end."
    )
    parser.add_argument(
        "--case", type=int, default=0,
        help=f"Index into STUDY_CASES (0–{len(STUDY_CASES)-1}), default 0"
    )
    parser.add_argument(
        "--no-plots", action="store_true",
        help="Skip plot generation"
    )
    parser.add_argument(
        "--stage", type=int, default=1, choices=[1, 2],
        help="Forward model stage: 1=synthesis (default), 2=Park dq ODE"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args   = _parse_args()
    case   = STUDY_CASES[args.case]
    result = run_case(case, save_plots=not args.no_plots, model_stage=args.stage)
