"""
run_voltage_correction_study.py
================================
SAMBP TR-15 validation study.

Demonstrates voltage-based pi-section charging correction (Mode 1) as the
final step in the TR-11 -> TR-12 -> TR-13 -> TR-15 sensitivity improvement
chain.  Both-end voltage measurements allow the charging current to be
predicted sample-by-sample without requiring a pre-fault window, reducing
the residual noise floor from ~0.003 pu (pre-fault blind, TR-13) to
~0.001 pu (voltage-based, limited by PT noise only).

Study matrix
------------
    Fault types : ag (phase-A-to-ground), 3ph (three-phase)
    Alpha range : 0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.30, 0.50
    Trials      : N = 200 per (fault_type, alpha)
    Seed        : 2026

Three configurations compared
------------------------------
    B  -- Pre-fault blind (TR-13 best):  thresh=0.12, max_factor=3.0
    D  -- Voltage-based (TR-15):         thresh=0.08, max_factor=2.0
    E  -- Voltage-based + override:      D + magnitude override at 0.20 pu

Voltage-waveform model
----------------------
For each trial the local (S) and remote (R) terminal voltages are generated
with independent amplitude deviations delta_S, delta_R in [-10%, +10%] and
independent phase offsets phi_S, phi_R in [-5 deg, +5 deg].  The
differential charging current is computed ANALYTICALLY from these voltages
(so the waveform is exactly consistent) and then the voltages are corrupted
with 0.1% PT noise before being passed to compute_charging_from_voltages().
The residual after subtraction therefore reflects only the PT noise floor.

Outputs
-------
    outputs/tr15_tpr_results.csv
    outputs/tr15_residual_comparison.csv
    outputs/tr15_sim_summary.txt
"""

from __future__ import annotations

import sys, os, csv
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from scipy.signal import hilbert

from models.line_reduced_zone_model import compute_f_int
from models.line_pi_section_model import (
    PiSectionConfig,
    compute_pi_section_correction,
    compute_charging_from_voltages,
    estimate_charging_from_prefault,
    apply_prefault_correction,
)
from inverse_estimation.line_inverse_estimator import estimate_line_zone_parameters
from adaptation.line_confidence_gate import (
    LineConfidenceGateConfig, evaluate_87L_confidence_gate,
)

# ---------------------------------------------------------------------------
# Study parameters (same base as TR-13 for direct comparison)
# ---------------------------------------------------------------------------

FREQ        = 50.0
FS          = 1000.0          # sample rate [Hz]
DUR_S       = 0.10            # total window [s]
PRE_S       = 0.02            # pre-fault length [s]
FAULT_T     = PRE_S

ALPHA_RANGE = [0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.30, 0.50]
N_TRIALS    = 200
SEED_BASE   = 2026

I_FAULT_NOM_AG  = 3.0     # pu — nominal fault contribution (ag)
I_FAULT_NOM_3PH = 4.0     # pu — nominal fault contribution (3ph)
B_C_PU          = 0.013   # total line susceptance [pu]
V_NOM_PU        = 1.0

# Threshold configurations
THRESH_PREFAULT = 0.12    # pu — TR-13 Config B/C
THRESH_VOLTAGE  = 0.08    # pu — TR-15 Config D/E (voltage-based)

# PT noise: 0.1% accuracy class (sigma per unit)
PT_NOISE_SIGMA  = 0.001   # pu RMS


# ---------------------------------------------------------------------------
# Voltage waveform generation  (consistent with charging in i_diff)
# ---------------------------------------------------------------------------

def _voltage_for_charging(
    I_C_amp: float,
    omega: float,
    t: np.ndarray,
    sh: float,
    phi_v: float,
) -> np.ndarray:
    """
    Return the voltage waveform whose Hilbert-based charging estimate is
    exactly I_C_amp * cos(omega*t + sh + phi_v).

    Derivation:
        compute_charging_from_voltages uses:
            i_C = B_C * Im{ hilbert(v_avg) }
        For v(t) = A*sin(omega*t + psi):
            Im{ hilbert(sin) } = -cos(omega*t + psi)
        So: B_C * (-A) * cos(omega*t + psi) = I_C_amp * cos(omega*t + phi)
        => A = -I_C_amp / B_C,  psi = sh + phi_v
        => v(t) = -(I_C_amp/B_C) * sin(omega*t + sh + phi_v)
    """
    return -(I_C_amp / B_C_PU) * np.sin(omega * t + sh + phi_v)


def generate_hif_waveform_voltage(
    fault_type: str,
    alpha: float,
    rng: np.random.Generator,
) -> tuple:
    """
    Generate:
        t_all       : (N,)   full time vector
        i_diff      : (3, N) differential waveform (charging + fault + noise)
        t_pre       : (N_p,) pre-fault time
        i_pre       : (3, N_p) pre-fault differential
        v_S_noisy   : (3, N) local voltage + PT noise
        v_R_noisy   : (3, N) remote voltage + PT noise
    """
    t_all = np.arange(0.0, DUR_S, 1.0 / FS)
    omega = 2.0 * np.pi * FREQ
    N     = len(t_all)

    # ---- Per-end voltage amplitude/phase deviations -----------------------
    # Each end has its own deviation; average gives the v_avg used for i_C
    delta_S = rng.uniform(-0.10, 0.10)          # local end amplitude deviation
    delta_R = rng.uniform(-0.10, 0.10)          # remote end amplitude deviation
    phi_S   = rng.uniform(-np.deg2rad(5.0), np.deg2rad(5.0))
    phi_R   = rng.uniform(-np.deg2rad(5.0), np.deg2rad(5.0))

    # Effective amplitude jitter on the average charging
    delta_avg = 0.5 * (delta_S + delta_R)
    phi_avg   = 0.5 * (phi_S + phi_R)

    I_C_amp = B_C_PU * V_NOM_PU * (1.0 + delta_avg)   # peak charging current

    # ---- Generate voltages per phase (3-phase) ----------------------------
    phase_shifts = [0.0, -2*np.pi/3, 2*np.pi/3]
    v_S = np.zeros((3, N))
    v_R = np.zeros((3, N))

    for ph, sh in enumerate(phase_shifts):
        # Sending-end voltage
        v_S[ph] = -(B_C_PU * V_NOM_PU * (1.0 + delta_S) / B_C_PU) * \
                   np.sin(omega * t_all + sh + phi_S)
        # Remote-end voltage
        v_R[ph] = -(B_C_PU * V_NOM_PU * (1.0 + delta_R) / B_C_PU) * \
                   np.sin(omega * t_all + sh + phi_R)

    # Analytic charging from averaged voltage  (truth, no noise)
    v_avg = 0.5 * (v_S + v_R)
    i_C_true = np.zeros((3, N))
    for ph in range(3):
        analytic = hilbert(v_avg[ph])
        i_C_true[ph] = B_C_PU * np.imag(analytic)

    # ---- Build differential waveform: charging + fault + thermal noise ----
    i_diff = i_C_true.copy()
    i_diff += rng.normal(0, 0.001, (3, N))         # thermal/CT noise

    fault_mask = t_all >= FAULT_T
    jit_L = 1.0 + rng.uniform(-0.05, 0.05)
    jit_R = 1.0 + rng.uniform(-0.05, 0.05)
    phase_err = rng.uniform(-0.15, 0.15)

    if fault_type == "ag":
        I_f_L = alpha * I_FAULT_NOM_AG  * jit_L
        I_f_R = alpha * I_FAULT_NOM_AG  * 0.85 * jit_R
        i_diff[0, fault_mask] += (
            I_f_L * np.sin(omega * t_all[fault_mask])
            + I_f_R * np.sin(omega * t_all[fault_mask] + phase_err)
        )
    elif fault_type == "3ph":
        I_f_L = alpha * I_FAULT_NOM_3PH * jit_L
        I_f_R = alpha * I_FAULT_NOM_3PH * 0.875 * jit_R
        for ph, sh in enumerate(phase_shifts):
            i_diff[ph, fault_mask] += (
                I_f_L * np.sin(omega * t_all[fault_mask] + sh)
                + I_f_R * np.sin(omega * t_all[fault_mask] + sh + phase_err)
            )
    else:
        raise ValueError(f"Unknown fault_type: {fault_type}")

    # ---- Add 0.1% PT noise to voltages before handing to estimator --------
    v_S_noisy = v_S + rng.normal(0, PT_NOISE_SIGMA, v_S.shape)
    v_R_noisy = v_R + rng.normal(0, PT_NOISE_SIGMA, v_R.shape)

    pre_mask = t_all < FAULT_T
    return (
        t_all,
        i_diff,
        t_all[pre_mask],
        i_diff[:, pre_mask],
        v_S_noisy,
        v_R_noisy,
    )


# ---------------------------------------------------------------------------
# Single-trial evaluation
# ---------------------------------------------------------------------------

def evaluate_trial(
    i_diff_fault: np.ndarray,     # (3, N_f) fault-epoch differential
    t_fault: np.ndarray,
    i_diff_pre: np.ndarray,       # (3, N_p) pre-fault
    t_pre: np.ndarray,
    v_S_fault: np.ndarray,        # (3, N_f) local voltage (fault epoch)
    v_R_fault: np.ndarray,        # (3, N_f) remote voltage (fault epoch)
    I_fund_thresh: float,
    max_factor: float,
    use_voltage: bool,
    use_magnitude_override: bool,
    pi_cfg: PiSectionConfig,
) -> dict:
    """Run one trial, return trip decision + diagnostics."""

    # ---- Charging correction -----------------------------------------------
    if use_voltage:
        i_C_est = compute_charging_from_voltages(
            v_S_fault, v_R_fault, pi_cfg.B_C_pu, pi_cfg.freq_hz,
        )
        i_corr = i_diff_fault - i_C_est
        # Residual: RMS of corrected pre-fault applied to phase A
        # (measure how much non-fault residual remains in the fault epoch)
        charging_residual_rms = float(np.sqrt(np.mean(i_corr[0]**2)))
    else:
        # Pre-fault blind (TR-13 Config B)
        A_C_abc, BC_abc = estimate_charging_from_prefault(
            i_diff_pre, t_pre, pi_cfg.freq_hz,
        )
        i_corr = apply_prefault_correction(
            i_diff_fault, t_fault, A_C_abc, BC_abc, pi_cfg.freq_hz,
        )
        # Residual quality: residual on pre-fault window
        i_pre_recon = apply_prefault_correction(
            i_diff_pre, t_pre, A_C_abc, BC_abc, pi_cfg.freq_hz,
        )
        charging_residual_rms = float(np.sqrt(np.mean(i_pre_recon[0]**2)))

    # ---- LM estimation on phase A -----------------------------------------
    result = estimate_line_zone_parameters(
        t_window=t_fault,
        i_diff_meas=i_corr[0],
        freq_hz=FREQ,
        I_fund_fault_thresh=I_fund_thresh,
        I_DC_thresh=I_fund_thresh * 0.6,
    )
    zone_state = result["state"]
    theta      = result["theta_hat"]

    # Recalculate f_int with config-appropriate max_factor
    import dataclasses
    f_int_recalc = compute_f_int(
        float(theta[0]), float(theta[2]),
        I_fund_fault_thresh=I_fund_thresh,
        I_DC_thresh=I_fund_thresh * 0.6,
        max_factor=max_factor,
    )
    zone_state = dataclasses.replace(zone_state, f_int=f_int_recalc)

    # ---- Conventional threshold trip --------------------------------------
    raw_peak = float(np.max(np.abs(i_diff_fault[0])))
    conventional_trip = raw_peak > I_fund_thresh * 0.5

    # ---- Confidence gate --------------------------------------------------
    gate_cfg = LineConfidenceGateConfig(
        f_int_thresh=0.50,
        veto_override_I_thresh=0.20 if use_magnitude_override else 1e9,
        model_veto_enable=True,
    )
    decision, _ = evaluate_87L_confidence_gate(zone_state, conventional_trip, gate_cfg)

    return {
        "I_fund":             zone_state.I_fund,
        "f_int":              zone_state.f_int,
        "sambp_trip":         decision.final_trip,
        "conventional_trip":  conventional_trip,
        "charging_res_rms":   charging_residual_rms,
    }


# ---------------------------------------------------------------------------
# Full alpha sweep
# ---------------------------------------------------------------------------

def run_sweep(
    config_label: str,
    I_fund_thresh: float,
    max_factor: float,
    use_voltage: bool,
    use_override: bool,
) -> list[dict]:
    """Run N_TRIALS per (fault_type, alpha); return result rows."""
    pi_cfg = PiSectionConfig(B_C_pu=B_C_PU, V_nom_pu=V_NOM_PU, freq_hz=FREQ)
    rows   = []

    for fault_type in ["ag", "3ph"]:
        for alpha in ALPHA_RANGE:
            tpr_sambp   = []
            tpr_conv    = []
            charge_res  = []
            i_fund_vals = []
            f_int_vals  = []

            for trial in range(N_TRIALS):
                seed = (SEED_BASE
                        + trial * 1000
                        + ALPHA_RANGE.index(alpha) * 10
                        + (0 if fault_type == "ag" else 1))
                rng = np.random.default_rng(seed)

                (t_all, i_diff, t_pre, i_pre,
                 v_S_noisy, v_R_noisy) = generate_hif_waveform_voltage(
                    fault_type, alpha, rng,
                )

                fault_mask = t_all >= FAULT_T
                t_f  = t_all[fault_mask]
                i_f  = i_diff[:, fault_mask]
                v_Sf = v_S_noisy[:, fault_mask]
                v_Rf = v_R_noisy[:, fault_mask]

                res = evaluate_trial(
                    i_f, t_f, i_pre, t_pre, v_Sf, v_Rf,
                    I_fund_thresh, max_factor,
                    use_voltage, use_override, pi_cfg,
                )
                tpr_sambp.append(int(res["sambp_trip"]))
                tpr_conv.append(int(res["conventional_trip"]))
                charge_res.append(res["charging_res_rms"])
                i_fund_vals.append(res["I_fund"])
                f_int_vals.append(res["f_int"])

            rows.append({
                "config":          config_label,
                "fault_type":      fault_type,
                "alpha":           alpha,
                "TPR_sambp":       float(np.mean(tpr_sambp)),
                "TPR_conv":        float(np.mean(tpr_conv)),
                "charge_rms_mean": float(np.mean(charge_res)),
                "charge_rms_p95":  float(np.percentile(charge_res, 95)),
                "I_fund_mean":     float(np.mean(i_fund_vals)),
                "f_int_mean":      float(np.mean(f_int_vals)),
            })
            print(f"  [{config_label}] {fault_type} alpha={alpha:.2f}  "
                  f"TPR={np.mean(tpr_sambp):.3f}  "
                  f"I_fund={np.mean(i_fund_vals):.3f}  "
                  f"res_rms={np.mean(charge_res):.5f}")
    return rows


# ---------------------------------------------------------------------------
# Alpha_50 finder
# ---------------------------------------------------------------------------

def find_alpha50(rows: list[dict], config: str, fault_type: str) -> float | None:
    subset = sorted(
        [(r["alpha"], r["TPR_sambp"])
         for r in rows if r["config"] == config and r["fault_type"] == fault_type],
        key=lambda x: x[0],
    )
    for alpha, tpr in subset:
        if tpr >= 0.50:
            return alpha
    return None


# ---------------------------------------------------------------------------
# Residual comparison table
# ---------------------------------------------------------------------------

def collect_residuals(rows: list[dict], config: str) -> dict:
    """Mean charging residual RMS across all (fault_type, alpha) for a config."""
    subset = [r for r in rows if r["config"] == config]
    if not subset:
        return {}
    return {
        "mean_rms": float(np.mean([r["charge_rms_mean"] for r in subset])),
        "p95_rms":  float(np.mean([r["charge_rms_p95"]  for r in subset])),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs("outputs", exist_ok=True)
    all_rows: list[dict] = []

    print("=== Config B: Pre-fault blind (TR-13 baseline) ===")
    all_rows += run_sweep(
        "B_prefault",
        I_fund_thresh=THRESH_PREFAULT,
        max_factor=3.0,
        use_voltage=False,
        use_override=False,
    )

    print("=== Config D: Voltage-based correction (TR-15) ===")
    all_rows += run_sweep(
        "D_voltage",
        I_fund_thresh=THRESH_VOLTAGE,
        max_factor=2.0,
        use_voltage=True,
        use_override=False,
    )

    print("=== Config E: Voltage-based + magnitude override ===")
    all_rows += run_sweep(
        "E_voltage_override",
        I_fund_thresh=THRESH_VOLTAGE,
        max_factor=2.0,
        use_voltage=True,
        use_override=True,
    )

    # ---- Save TPR CSV ------------------------------------------------------
    out_csv = "outputs/tr15_tpr_results.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nSaved: {out_csv}")

    # ---- Save residual comparison ------------------------------------------
    res_rows = []
    for cfg in ["B_prefault", "D_voltage", "E_voltage_override"]:
        d = collect_residuals(all_rows, cfg)
        res_rows.append({"config": cfg, **d})
    res_csv = "outputs/tr15_residual_comparison.csv"
    with open(res_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(res_rows[0].keys()))
        writer.writeheader()
        writer.writerows(res_rows)
    print(f"Saved: {res_csv}")

    # ---- Summary -----------------------------------------------------------
    lines = [
        "SAMBP TR-15 Simulation Summary",
        "=" * 50,
        "",
        "alpha_50 (TPR >= 0.50) by configuration and fault type",
        "-" * 50,
    ]
    for cfg in ["B_prefault", "D_voltage", "E_voltage_override"]:
        for ft in ["ag", "3ph"]:
            a50 = find_alpha50(all_rows, cfg, ft)
            lines.append(f"  {cfg:22s}  {ft:4s}  alpha_50 = {a50}")

    lines += [
        "",
        "Mean charging residual RMS [pu] by configuration",
        "-" * 50,
    ]
    for cfg in ["B_prefault", "D_voltage", "E_voltage_override"]:
        d = collect_residuals(all_rows, cfg)
        lines.append(f"  {cfg:22s}  mean={d['mean_rms']:.5f} pu  "
                     f"p95={d['p95_rms']:.5f} pu")

    lines += [
        "",
        "TPR detail: Config D (voltage, no override) — ag faults",
        "-" * 50,
    ]
    for r in [x for x in all_rows
              if x["config"] == "D_voltage" and x["fault_type"] == "ag"]:
        lines.append(f"  alpha={r['alpha']:.2f}  "
                     f"TPR={r['TPR_sambp']:.3f}  "
                     f"I_fund_mean={r['I_fund_mean']:.3f} pu  "
                     f"f_int_mean={r['f_int_mean']:.3f}")

    lines += [
        "",
        "TPR detail: Config D (voltage, no override) — 3ph faults",
        "-" * 50,
    ]
    for r in [x for x in all_rows
              if x["config"] == "D_voltage" and x["fault_type"] == "3ph"]:
        lines.append(f"  alpha={r['alpha']:.2f}  "
                     f"TPR={r['TPR_sambp']:.3f}  "
                     f"I_fund_mean={r['I_fund_mean']:.3f} pu")

    summary_path = "outputs/tr15_sim_summary.txt"
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved: {summary_path}")
    for line in lines:
        print(line)
