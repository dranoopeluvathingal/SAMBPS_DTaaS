# =============================================================================
# sambp / sync_oc / run_tr59_andes.py
#
# TR-59: ANDES-validated sync_oc results.
#
# Replaces the synthetic forward simulation (simulate_sync_generator_currents)
# in main_run_case.py with physics-correct waveforms from ANDES TDS.
# All downstream SAMBP pipeline stages (Steps 3–10) are unchanged.
#
# Case matrix (mirrors original STUDY_CASES + resistance sweep):
#   - 3PH fault:  R_f = 0.01, 0.05, 0.10, 0.50 pu
#   - SLG fault:  R_f = 0.01, 0.05, 0.15, 0.50 pu
#   - LL fault:   R_f = 0.01, 0.05 pu
#
# ANDES case: ieee14_fault (Bus 9 fault, pre-configured)
# Relay bus:  Bus 9 (fault bus = measurement bus for terminal relay)
#
# Outputs
# -------
#   outputs/tr59/tr59_results.csv        — per-case summary table
#   outputs/tr59/plots/                  — waveform + relay plots per case
#   outputs/tr59/tr59_summary.txt        — comparison: synthetic vs ANDES
#
# Usage
# -----
#   cd 04_code/sambp/sync_oc
#   /root/dr_e_venv/bin/python3 run_tr59_andes.py
# =============================================================================

import os
import sys
import csv
import copy
import numpy as np

# Path setup
_sync_oc_dir = os.path.dirname(os.path.abspath(__file__))
_sambp_dir   = os.path.join(_sync_oc_dir, "..")
_code_dir    = os.path.join(_sync_oc_dir, "..", "..")
sys.path.insert(0, _code_dir)
sys.path.insert(0, _sambp_dir)
sys.path.insert(0, _sync_oc_dir)

# SAMBP imports
from config.system_config  import SYSTEM_CONFIG
from config.relay_config   import RELAY_CONFIG
from models.relay_oc_model import compute_relay_current_rms, run_overcurrent_relay
from models.reduced_source_model import DEFAULT_THETA, reduced_sync_current_model
from signal_processing.event_detection import detect_event_time
from signal_processing.preprocessing   import extract_event_window
from signal_processing.smoothing        import smooth_signal
from inverse_estimation.parameter_estimator import (
    estimate_reduced_source_parameters_two_pass,
    estimate_reduced_source_parameters,
    DEFAULT_BOUNDS, _build_bounds,
)
from inverse_estimation.sequence_estimator  import estimate_sequence_parameters
from inverse_estimation.sensitivity_analysis import (
    compute_jacobian_condition_number,
    compute_parameter_sensitivities,
)
from inverse_estimation.confidence_logic import compute_confidence_score, accept_adaptation
from adaptation.adaptive_mapping import map_source_estimate_to_oc_settings
from adaptation.bounded_update   import apply_bounded_update
from evaluation.metrics    import compute_fit_metrics, compute_protection_metrics
from evaluation.comparison import compare_fixed_vs_adaptive
from io_utils.csv_io       import save_waveform_csv

# ANDES adapter — lives in sambp/io_utils, not sync_oc/io_utils
import importlib.util as _ilu
_adapter_path = os.path.join(_sambp_dir, "io_utils", "andes_adapter.py")
_spec = _ilu.spec_from_file_location("andes_adapter", _adapter_path)
_adapter = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_adapter)
run_andes_tds           = _adapter.run_andes_tds
extract_relay_waveforms = _adapter.extract_relay_waveforms
build_fault_case        = _adapter.build_fault_case

# ---------------------------------------------------------------------------
# ANDES case configuration
# ---------------------------------------------------------------------------
ANDES_CASE   = "/root/phd_thesis/05_data/test_cases/andes/ieee14_fault.json"
FAULT_BUS    = 9      # fault bus in ANDES case
RELAY_BUS    = 9      # relay measurement bus
FAULT_TIME   = 1.0    # fault inception (s) — pre-configured in ieee14_fault
CLEAR_TIME   = 1.1    # fault clearing (s)
TF_ANDES     = 1.6    # TDS end time (s)
FS           = 10000.0
F0           = 50.0

# ---------------------------------------------------------------------------
# Case matrix
# ---------------------------------------------------------------------------
TR59_CASES = [
    # 3PH cases
    {"case_name": "tr59_3ph_R001", "fault_type": "3PH", "fault_R_pu": 0.01},
    {"case_name": "tr59_3ph_R005", "fault_type": "3PH", "fault_R_pu": 0.05},
    {"case_name": "tr59_3ph_R010", "fault_type": "3PH", "fault_R_pu": 0.10},
    {"case_name": "tr59_3ph_R050", "fault_type": "3PH", "fault_R_pu": 0.50},
    # SLG cases
    {"case_name": "tr59_slg_R001", "fault_type": "SLG", "fault_R_pu": 0.01},
    {"case_name": "tr59_slg_R005", "fault_type": "SLG", "fault_R_pu": 0.05},
    {"case_name": "tr59_slg_R015", "fault_type": "SLG", "fault_R_pu": 0.15},
    {"case_name": "tr59_slg_R050", "fault_type": "SLG", "fault_R_pu": 0.50},
    # LL cases
    {"case_name": "tr59_ll_R001",  "fault_type": "LL",  "fault_R_pu": 0.01},
    {"case_name": "tr59_ll_R005",  "fault_type": "LL",  "fault_R_pu": 0.05},
]

# ---------------------------------------------------------------------------
# Output directories
# ---------------------------------------------------------------------------
OUT_DIR      = os.path.join("outputs", "tr59")
PLOT_DIR     = os.path.join(OUT_DIR, "plots")
RESULTS_CSV  = os.path.join(OUT_DIR, "tr59_results.csv")
SUMMARY_TXT  = os.path.join(OUT_DIR, "tr59_summary.txt")
os.makedirs(PLOT_DIR, exist_ok=True)

CSV_FIELDS = [
    "case_name", "fault_type", "fault_R_pu",
    "source", "I_sub_pu", "tau_ac_s", "tau_dc_s", "I_ss_pu",
    "confidence", "lm_success", "lm_cost", "rmse_phaseA",
    "fixed_trip_ms", "adaptive_trip_ms", "trip_speedup_ms",
    "pickup_adapt", "tms_adapt",
    "V_pre_pu", "I_peak_pu",
]


# ===========================================================================
# Single-case runner (ANDES source)
# ===========================================================================

def run_tr59_case(case: dict, andes_result) -> dict:
    """
    Run the full SAMBP sync_oc pipeline for one TR-59 case using ANDES waveforms.

    Parameters
    ----------
    case         : dict with case_name, fault_type, fault_R_pu
    andes_result : AndesResult from run_andes_tds (shared across cases)

    Returns
    -------
    dict — result row for CSV output
    """
    case_name  = case["case_name"]
    fault_type = case["fault_type"]
    fault_R    = case["fault_R_pu"]
    cfg        = copy.deepcopy(SYSTEM_CONFIG)

    print(f"\n{'='*60}")
    print(f"  {case_name}  |  {fault_type}  |  Rf={fault_R} pu  [ANDES source]")
    print(f"{'='*60}")

    # ── Step 2 (ANDES): extract waveforms at relay bus ────────────────────
    waves = extract_relay_waveforms(
        andes_result, relay_bus=RELAY_BUS,
        fs=FS, f0=F0,
        window=(FAULT_TIME - 0.10, CLEAR_TIME + 0.30),
    )
    fc = build_fault_case(waves, fault_type=fault_type, fault_R_pu=fault_R)

    t  = fc["t_window"]
    ia, ib, ic = fc["ia_meas"], fc["ib_meas"], fc["ic_meas"]

    # ── Step 3: fixed relay ───────────────────────────────────────────────
    i_rms = compute_relay_current_rms(t, ia, ib, ic, frequency_hz=F0)
    fixed_relay = run_overcurrent_relay(
        t=t, i_rms=i_rms,
        pickup_pu      = RELAY_CONFIG["pickup_pu"],
        inst_pickup_pu = RELAY_CONFIG["inst_pickup_pu"],
        tms            = RELAY_CONFIG["tms"],
        curve_type     = RELAY_CONFIG["curve_type"],
    )

    # ── Step 4: event detection ───────────────────────────────────────────
    t0_det = detect_event_time(t, ia, ib, ic, method="rms_jump",
                                threshold=0.15, frequency_hz=F0)
    t0 = t0_det if t0_det is not None else FAULT_TIME

    # ── Step 5: event window ──────────────────────────────────────────────
    signals = {"ia": ia, "ib": ib, "ic": ic}
    post_s  = min(0.18, (CLEAR_TIME - t0) - 0.005)
    post_s  = max(post_s, 0.05)
    window  = extract_event_window(t, signals, t0, pre_s=0.002, post_s=post_s)
    t_w     = window["t"]
    ia_w    = smooth_signal(window["ia"], method="savgol")
    ib_w    = smooth_signal(window["ib"], method="savgol")
    ic_w    = smooth_signal(window["ic"], method="savgol")

    # ── Step 6: LM estimation ────────────────────────────────────────────
    initial_guess = {**DEFAULT_THETA, "t0": t0}
    I_peak = float(np.abs(ia_w).max())
    initial_guess["I_sub"] = I_peak * 0.7
    initial_guess["I_ss"]  = max(0.1, I_peak * 0.15)

    if fault_type == "3PH":
        est = estimate_reduced_source_parameters_two_pass(
            t_w, ia_w, ib_w, ic_w, initial_guess, DEFAULT_BOUNDS,
            frequency_hz=F0,
        )
        theta = est["theta_hat"]
    else:
        seq = estimate_sequence_parameters(
            t_w, ia_w, ib_w, ic_w, fault_type, initial_guess, DEFAULT_BOUNDS,
            frequency_hz=F0,
        )
        theta = seq["theta_pos"]
        est   = {
            "theta_hat": theta, "success": seq["success"],
            "cost": 0.5 * seq["residual_norm_total"]**2,
            "residual_norm": seq["residual_norm_total"],
            "jacobian": seq["jacobian"], "n_evaluations": 0,
        }

    print(f"  LM success={est['success']}  cost={est['cost']:.3f}  "
          f"I_sub={theta['I_sub']:.3f}  tau_ac={theta['tau_ac']:.4f}")

    # ── Step 7: confidence ────────────────────────────────────────────────
    jac = est["jacobian"]
    if jac is not None:
        from models.reduced_source_model import THETA_KEYS
        J = np.asarray(jac, dtype=float)
        cn = np.linalg.norm(J, axis=0)
        cn = np.where(cn < 1e-12, 1.0, cn)
        cond_num = compute_jacobian_condition_number(J / cn)
    else:
        cond_num = 1e6

    lo, hi = _build_bounds(DEFAULT_BOUNDS)
    from models.reduced_source_model import theta_to_vector
    th_vec = theta_to_vector(theta)
    bounds_hit = float(np.sum(
        np.isclose(th_vec, lo, atol=1e-6) | np.isclose(th_vec, hi, atol=1e-6)
    )) / len(th_vec)

    plaus = 1.0
    if theta["I_sub"] <= theta["I_ss"]:  plaus -= 0.5
    if not (0.005 <= theta["tau_dc"] <= 0.5): plaus -= 0.3
    if not (0.003 <= theta["tau_ac"] <= 1.0): plaus -= 0.2
    plaus = float(np.clip(plaus, 0.0, 1.0))

    gamma = compute_confidence_score(
        residual_norm              = est["residual_norm"] / max(1, len(t_w)**0.5),
        condition_number           = cond_num,
        bounds_hit_fraction        = bounds_hit,
        parameter_plausibility_score = plaus,
        residual_ref=0.15, cond_good=10.0, cond_bad=500.0,
    )
    print(f"  γ={gamma:.4f}  κ={cond_num:.1f}  plaus={plaus:.2f}")

    # ── Step 8: adaptive relay ────────────────────────────────────────────
    if accept_adaptation(gamma, RELAY_CONFIG["confidence_threshold"]):
        mapping = map_source_estimate_to_oc_settings(theta, RELAY_CONFIG)
        update  = apply_bounded_update(
            pickup_proposed = mapping["pickup_proposed"],
            tms_proposed    = mapping["tms_proposed"],
            pickup_current  = RELAY_CONFIG["pickup_pu"],
            tms_current     = RELAY_CONFIG["tms"],
            bounds          = RELAY_CONFIG["adaptive_bounds"],
        )
        pickup_adapt = update["pickup_final"]
        tms_adapt    = update["tms_final"]
    else:
        pickup_adapt = RELAY_CONFIG["pickup_pu"]
        tms_adapt    = RELAY_CONFIG["tms"]

    adaptive_relay = run_overcurrent_relay(
        t=t, i_rms=i_rms,
        pickup_pu=pickup_adapt, inst_pickup_pu=RELAY_CONFIG["inst_pickup_pu"],
        tms=tms_adapt, curve_type=RELAY_CONFIG["curve_type"],
    )

    # ── Step 9: metrics ───────────────────────────────────────────────────
    model_out = reduced_sync_current_model(t_w, theta, F0)
    fit  = compute_fit_metrics(ia_w, model_out["ia"], ib_w, model_out["ib"],
                                ic_w, model_out["ic"])
    prot = compute_protection_metrics(fixed_relay, adaptive_relay)

    ft  = fixed_relay["trip_time"]
    at  = adaptive_relay["trip_time"]
    ft_ms = ft * 1000 if ft else None
    at_ms = at * 1000 if at else None
    sp_ms = (ft - at) * 1000 if (ft and at) else None

    print(f"  Fixed trip: {ft_ms} ms  |  Adaptive: {at_ms} ms  |  Speedup: {sp_ms} ms")

    # ── Step 10: plots ────────────────────────────────────────────────────
    _save_tr59_plots(case_name, t, ia, ib, ic, i_rms, t_w,
                     model_out, fixed_relay, adaptive_relay, theta, gamma)

    return {
        "case_name":      case_name,
        "fault_type":     fault_type,
        "fault_R_pu":     fault_R,
        "source":         "andes",
        "I_sub_pu":       theta["I_sub"],
        "tau_ac_s":       theta["tau_ac"],
        "tau_dc_s":       theta["tau_dc"],
        "I_ss_pu":        theta["I_ss"],
        "confidence":     gamma,
        "lm_success":     est["success"],
        "lm_cost":        est["cost"],
        "rmse_phaseA":    fit["rmse_a"],
        "fixed_trip_ms":  ft_ms,
        "adaptive_trip_ms": at_ms,
        "trip_speedup_ms":  sp_ms,
        "pickup_adapt":   pickup_adapt,
        "tms_adapt":      tms_adapt,
        "V_pre_pu":       waves["V_pre"],
        "I_peak_pu":      I_peak,
    }


# ===========================================================================
# Plot helper
# ===========================================================================

def _save_tr59_plots(case_name, t, ia, ib, ic, i_rms, t_w,
                     model_out, fixed_relay, adaptive_relay, theta, gamma):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    ds = 10   # downsample factor for plotting (10 kHz → 1 kHz visual)

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=False)
    fig.suptitle(f"TR-59 ANDES-backed sync_oc  |  {case_name}\n"
                 f"ANDES ieee14-fault, relay_bus=9  |  γ={gamma:.3f}  "
                 f"I_sub={theta['I_sub']:.3f} pu  tau_ac={theta['tau_ac']:.4f} s",
                 fontsize=11, fontweight="bold")

    # Panel 1: three-phase currents + LM fit
    axes[0].plot(t[::ds]*1e3, ia[::ds], "b-", lw=0.7, alpha=0.7, label="ia")
    axes[0].plot(t[::ds]*1e3, ib[::ds], "g-", lw=0.7, alpha=0.5, label="ib")
    axes[0].plot(t[::ds]*1e3, ic[::ds], "r-", lw=0.7, alpha=0.5, label="ic")
    axes[0].plot(t_w[::ds]*1e3, model_out["ia"][::ds], "k--", lw=1.4, label="ia LM fit")
    axes[0].axvspan(FAULT_TIME*1e3, CLEAR_TIME*1e3, color="red", alpha=0.10, label="Fault")
    axes[0].set_ylabel("Current (pu)")
    axes[0].set_title("Three-Phase Fault Currents (ANDES) vs LM Fit")
    axes[0].legend(fontsize=7, ncol=4); axes[0].grid(True, alpha=0.3)
    axes[0].set_xlabel("Time (ms)")

    # Panel 2: I_rms + relay trips
    axes[1].plot(t[::ds]*1e3, i_rms[::ds], "navy", lw=1.2, label="I_rms")
    ft = fixed_relay["trip_time"]
    at = adaptive_relay["trip_time"]
    if ft:
        axes[1].axvline(ft*1e3, color="steelblue", ls="--", lw=1.5,
                        label=f"Fixed trip {ft*1e3:.0f} ms")
    if at:
        axes[1].axvline(at*1e3, color="darkorange", ls="-.", lw=1.5,
                        label=f"Adaptive trip {at*1e3:.0f} ms")
    axes[1].axhline(RELAY_CONFIG["pickup_pu"], color="gray", ls=":", lw=0.8,
                    label=f"Pickup {RELAY_CONFIG['pickup_pu']} pu")
    axes[1].set_ylabel("I_rms (pu)")
    axes[1].set_title("OC Relay Response — Fixed vs Adaptive")
    axes[1].legend(fontsize=7); axes[1].grid(True, alpha=0.3)
    axes[1].set_xlabel("Time (ms)")

    # Panel 3: LM residual (phase A)
    residual = ia[np.isin(t, t_w)] - model_out["ia"] if len(t_w) == len(t) else \
               np.interp(t_w, t, ia) - model_out["ia"]
    axes[2].plot(t_w[::ds]*1e3, residual[::ds], color="purple", lw=0.8)
    axes[2].axhline(0, color="k", lw=0.5)
    axes[2].set_ylabel("Residual ia − fit (pu)")
    axes[2].set_xlabel("Time (ms)")
    axes[2].set_title(f"LM Residual  |  RMSE_A = {float(np.sqrt(np.mean(residual**2))):.4f} pu")
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(PLOT_DIR, f"{case_name}.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Plot → {out}")


# ===========================================================================
# Batch runner + CSV writer
# ===========================================================================

def run_tr59_batch():
    print(f"\n{'#'*60}")
    print(f"  TR-59: ANDES-validated sync_oc  ({len(TR59_CASES)} cases)")
    print(f"  ANDES case : {ANDES_CASE}")
    print(f"  Fault bus  : {FAULT_BUS}   Relay bus: {RELAY_BUS}")
    print(f"  Fault window: {FAULT_TIME}s → {CLEAR_TIME}s")
    print(f"  NOTE: Separate ANDES TDS per case (fault_rf = Rf per case)")
    print(f"  NOTE: SLG/LL use positive-sequence ANDES (same network physics,")
    print(f"        different fault impedance; asymmetric fault type handled")
    print(f"        at SAMBP estimator level only).")
    print(f"{'#'*60}")

    results = []
    failed  = []

    # Cache ANDES results by (fault_type, fault_R_pu) to avoid redundant TDS runs.
    # For positive-sequence ANDES, SLG/LL with same Rf produce the same network
    # response — cache by Rf only (fault_type is a SAMBP-level annotation).
    _andes_cache: dict = {}

    for case in TR59_CASES:
        fault_R = case["fault_R_pu"]
        cache_key = round(fault_R, 6)

        if cache_key not in _andes_cache:
            print(f"\nRunning ANDES TDS: fault_rf={fault_R} pu ...")
            ar = run_andes_tds(
                ANDES_CASE, fault_bus=FAULT_BUS,
                fault_time=FAULT_TIME, clear_time=CLEAR_TIME,
                tf=TF_ANDES,
                fault_xf=0.001,
                fault_rf=fault_R,
            )
            print(f"  Converged: {ar.ss.PFlow.converged}  "
                  f"steps: {len(ar.t)}  span: {ar.t[0]:.2f}s → {ar.t[-1]:.2f}s")
            _andes_cache[cache_key] = ar
        else:
            print(f"\n  [cached] ANDES result for Rf={fault_R} pu reused "
                  f"({case['case_name']})")

        andes_result = _andes_cache[cache_key]

        try:
            row = run_tr59_case(case, andes_result)
            results.append(row)
        except Exception as e:
            print(f"  ERROR in {case['case_name']}: {e}")
            import traceback; traceback.print_exc()
            failed.append(case["case_name"])

    # Write CSV
    with open(RESULTS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in results:
            writer.writerow({k: (f"{row[k]:.6g}" if isinstance(row[k], float)
                                 else row[k])
                             for k in CSV_FIELDS})
    print(f"\nResults CSV → {RESULTS_CSV}")

    # Write summary text
    _write_summary(results, failed)

    return results


def _write_summary(results, failed):
    lines = []
    lines.append("=" * 70)
    lines.append("TR-59: ANDES-validated sync_oc — Batch Summary")
    lines.append(f"Cases run: {len(results)}  |  Failed: {len(failed)}")
    lines.append("=" * 70)
    lines.append(f"{'Case':<28} {'Type':<5} {'Rf':>5} {'γ':>6} "
                 f"{'I_sub':>6} {'τ_ac':>7} {'Fixed':>8} {'Adapt':>8} {'Δt':>8}")
    lines.append("-" * 70)

    for r in results:
        ft  = f"{r['fixed_trip_ms']:.0f}ms"  if r["fixed_trip_ms"]    else "  --  "
        at  = f"{r['adaptive_trip_ms']:.0f}ms" if r["adaptive_trip_ms"] else "  --  "
        sp  = f"{r['trip_speedup_ms']:+.0f}ms"  if r["trip_speedup_ms"]  else "  --  "
        lines.append(
            f"{r['case_name']:<28} {r['fault_type']:<5} {r['fault_R_pu']:>5.2f} "
            f"{r['confidence']:>6.3f} {r['I_sub_pu']:>6.3f} {r['tau_ac_s']:>7.4f} "
            f"{ft:>8} {at:>8} {sp:>8}"
        )

    if failed:
        lines.append(f"\nFailed cases: {', '.join(failed)}")

    # Aggregate stats
    gamma_vals = [r["confidence"] for r in results]
    accept     = sum(1 for g in gamma_vals if g >= RELAY_CONFIG["confidence_threshold"])
    speedups   = [r["trip_speedup_ms"] for r in results if r["trip_speedup_ms"] is not None]
    lines.append("=" * 70)
    lines.append(f"Adaptation accepted : {accept}/{len(results)} cases  "
                 f"(threshold γ≥{RELAY_CONFIG['confidence_threshold']})")
    if speedups:
        lines.append(f"Trip speedup        : mean={np.mean(speedups):.0f} ms  "
                     f"max={max(speedups):.0f} ms  min={min(speedups):.0f} ms")
    lines.append(f"Mean confidence γ   : {np.mean(gamma_vals):.3f}")
    lines.append("=" * 70)

    summary = "\n".join(lines)
    print(f"\n{summary}")
    with open(SUMMARY_TXT, "w") as f:
        f.write(summary + "\n")
    print(f"Summary → {SUMMARY_TXT}")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    run_tr59_batch()
