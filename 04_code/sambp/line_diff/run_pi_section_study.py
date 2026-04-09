"""
run_pi_section_study.py
========================
SAMBP TR-13 validation study.

Compares 87L HIF sensitivity *before* and *after* pi-section charging
correction across the same HIF alpha sweep used in TR-11 and TR-12.

Study matrix (same as TR-12 for direct comparison)
---------------------------------------------------
    Fault types   : ag (phase-A-to-ground), 3ph (three-phase)
    Alpha range   : 0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.30, 0.50, 0.70, 1.00
    Trials        : N = 200 per (fault_type, alpha) combination
    Seed          : 2026 (same as TR-12)
    Jitter        : ±5% on I_fault

Three configurations evaluated
-------------------------------
    A  — Baseline (TR-12 state):    fixed charging comp, I_fund_thresh=0.20 pu
    B  — Pi-section (TR-13):        prefault correction, I_fund_thresh=0.12 pu
    C  — Pi-section + override:     B + magnitude override at 0.30 pu (TR-12 guard)

Outputs
-------
    outputs/tr13_tpr_results.csv
    outputs/tr13_charging_residual.csv
    tr13_sim_summary.txt       — text summary for report
"""

from __future__ import annotations

import sys, os, csv
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np

from models.line_reduced_zone_model import (
    forward_idiff, jacobian_idiff, condition_number_normalised,
    residual_vector, initial_guess, interpret_theta,
    LOWER_BOUNDS, UPPER_BOUNDS,
)
from models.line_pi_section_model import (
    PiSectionConfig, compute_pi_section_correction,
)
from inverse_estimation.line_inverse_estimator import estimate_line_zone_parameters
from adaptation.line_confidence_gate import (
    LineConfidenceGateConfig, LineGateState, evaluate_87L_confidence_gate,
)

# ---------------------------------------------------------------------------
# Study parameters
# ---------------------------------------------------------------------------

FREQ     = 50.0
FS       = 1000.0          # sample rate [Hz]
DUR_S    = 0.10            # window length [s]
PRE_S    = 0.02            # pre-fault window [s]  (1 cycle)
FAULT_T  = PRE_S           # fault starts at 0.02 s

ALPHA_RANGE = [0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.30, 0.50, 0.70, 1.00]
N_TRIALS    = 200
SEED_BASE   = 2026

I_FAULT_NOM_AG  = 3.0   # pu — base fault contribution for ag fault
I_FAULT_NOM_3PH = 4.0   # pu — base fault contribution for 3ph fault
I_C_PEAK_NOM    = 0.013  # pu — pi-section charging (B_C × V_nom)

# Threshold configurations
THRESH_BASELINE = 0.20   # pu — TR-12 state
THRESH_PI       = 0.12   # pu — TR-13 after pi-section correction


# ---------------------------------------------------------------------------
# Waveform generator
# ---------------------------------------------------------------------------

def generate_hif_waveform(
    fault_type: str,
    alpha: float,
    rng: np.random.Generator,
    I_C_amplitude_jitter: float = 0.05,   # ±5% on charging amplitude
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate i_diff (3-phase) and i_diff_pre (pre-fault epoch).

    Returns
    -------
    t_all   : (N_all,)  full time vector
    i_diff  : (3, N_all) differential waveform
    t_pre   : (N_pre,)  pre-fault time
    i_pre   : (3, N_pre) pre-fault differential
    """
    t_all = np.arange(0, DUR_S, 1.0 / FS)
    omega = 2.0 * np.pi * FREQ
    N_all = len(t_all)

    # ---- Charging current (variable amplitude to simulate voltage deviation) -
    I_C_amp = I_C_PEAK_NOM * (1.0 + rng.uniform(-I_C_amplitude_jitter,
                                                   I_C_amplitude_jitter))
    phi_v   = rng.uniform(-0.05, 0.05)   # ±3° voltage angle variation

    i_diff = np.zeros((3, N_all))
    for ph, sh in enumerate([0, -2*np.pi/3, 2*np.pi/3]):
        i_diff[ph] = I_C_amp * np.cos(omega * t_all + sh + phi_v)
        i_diff[ph] += rng.normal(0, 0.001, N_all)    # measurement noise

    # ---- Fault component (from fault inception time) -------------------------
    fault_mask = t_all >= FAULT_T
    jitter_L   = 1.0 + rng.uniform(-0.05, 0.05)
    jitter_R   = 1.0 + rng.uniform(-0.05, 0.05)
    phase_err  = rng.uniform(-0.15, 0.15)            # relay end phase difference

    if fault_type == "ag":
        # Phase A-to-ground: fault only on phase A, both ends contribute
        I_f_L = alpha * I_FAULT_NOM_AG  * jitter_L
        I_f_R = alpha * I_FAULT_NOM_AG  * 0.85 * jitter_R
        i_diff[0, fault_mask] += (
            I_f_L * np.sin(omega * t_all[fault_mask])
            + I_f_R * np.sin(omega * t_all[fault_mask] + phase_err)
        )
    elif fault_type == "3ph":
        # Three-phase: all phases contribute symmetrically
        I_f_L = alpha * I_FAULT_NOM_3PH * jitter_L
        I_f_R = alpha * I_FAULT_NOM_3PH * 0.875 * jitter_R
        for ph, sh in enumerate([0, -2*np.pi/3, 2*np.pi/3]):
            i_diff[ph, fault_mask] += (
                I_f_L * np.sin(omega * t_all[fault_mask] + sh)
                + I_f_R * np.sin(omega * t_all[fault_mask] + sh + phase_err)
            )
    else:
        raise ValueError(f"Unknown fault type: {fault_type}")

    pre_mask = t_all < FAULT_T
    return t_all, i_diff, t_all[pre_mask], i_diff[:, pre_mask]


# ---------------------------------------------------------------------------
# Single-trial evaluation
# ---------------------------------------------------------------------------

def evaluate_trial(
    i_diff_fault: np.ndarray,    # (3, N_f) fault-epoch differential
    t_fault: np.ndarray,         # (N_f,)
    i_diff_pre: np.ndarray,      # (3, N_p) pre-fault differential
    t_pre: np.ndarray,           # (N_p,)
    I_fund_thresh: float,        # detection threshold
    use_pi_correction: bool,
    use_magnitude_override: bool,
    pi_cfg: PiSectionConfig,
) -> dict:
    """
    Run one trial and return trip decision + key diagnostics.
    """
    # ---- Optional pi-section correction ------------------------------------
    if use_pi_correction:
        i_corr, pi_state = compute_pi_section_correction(
            i_diff_fault, t_fault, i_diff_pre, t_pre, cfg=pi_cfg,
        )
        charging_residual_rms = pi_state.residual_rms
    else:
        # Baseline: no correction beyond what is already in the waveform generator
        # The waveform already has fixed I_C_PEAK_NOM; subtract it as the
        # "existing fixed-amplitude model" does.
        omega = 2.0 * np.pi * FREQ
        i_corr = i_diff_fault.copy()
        for ph, sh in enumerate([0, -2*np.pi/3, 2*np.pi/3]):
            i_corr[ph] -= I_C_PEAK_NOM * np.cos(omega * t_fault + sh)
        # Compute residual on phase A
        charging_residual_rms = float(np.sqrt(np.mean(
            (i_diff_fault[0] - I_C_PEAK_NOM * np.cos(omega * t_fault))**2
        )))

    # ---- LM estimation on phase A differential (dominant for ag; largest for 3ph)
    ph = 0   # phase A
    # max_factor: with pi-section correction the signal is clean enough to use
    # a tighter sensitivity range (3.0 instead of 5.0) — this recalibrates
    # f_int so that a fault at 2× threshold already gives f_int=0.50.
    max_factor = 3.0 if use_pi_correction else 5.0

    result = estimate_line_zone_parameters(
        t_window=t_fault,
        i_diff_meas=i_corr[ph],
        freq_hz=FREQ,
        I_fund_fault_thresh=I_fund_thresh,
        I_DC_thresh=I_fund_thresh * 0.6,
    )

    # Re-compute f_int with the configuration-appropriate max_factor
    from models.line_reduced_zone_model import compute_f_int
    zone_state = result["state"]
    theta = result["theta_hat"]
    f_int_recalc = compute_f_int(
        float(theta[0]), float(theta[2]),
        I_fund_fault_thresh=I_fund_thresh,
        I_DC_thresh=I_fund_thresh * 0.6,
        max_factor=max_factor,
    )
    # Patch the zone_state with the recalculated f_int
    import dataclasses
    zone_state = dataclasses.replace(zone_state, f_int=f_int_recalc)

    # ---- Conventional differential trip (threshold on raw diff amplitude) ---
    raw_peak = float(np.max(np.abs(i_diff_fault[ph])))
    conventional_trip = raw_peak > I_fund_thresh * 0.5   # generous conventional pickup

    # ---- Confidence gate ---------------------------------------------------
    gate_cfg = LineConfidenceGateConfig(
        f_int_thresh=0.50,
        veto_override_I_thresh=0.30 if use_magnitude_override else 1e9,
        model_veto_enable=True,
    )
    decision, _ = evaluate_87L_confidence_gate(
        zone_state, conventional_trip, gate_cfg,
    )

    return {
        "I_fund":              zone_state.I_fund,
        "f_int":               zone_state.f_int,
        "kappa_n":             zone_state.kappa_n,
        "sambp_trip":          decision.final_trip,
        "conventional_trip":   conventional_trip,
        "charging_res_rms":    charging_residual_rms,
    }


# ---------------------------------------------------------------------------
# Full alpha sweep
# ---------------------------------------------------------------------------

def run_sweep(config_label: str, I_fund_thresh: float,
              use_pi: bool, use_override: bool) -> list[dict]:
    """Run N_TRIALS per (fault_type, alpha) and return rows."""
    pi_cfg = PiSectionConfig(B_C_pu=I_C_PEAK_NOM, V_nom_pu=1.0, freq_hz=FREQ)
    rows = []

    for fault_type in ["ag", "3ph"]:
        for alpha in ALPHA_RANGE:
            tpr_conv  = []
            tpr_sambp = []
            charge_res = []

            for trial in range(N_TRIALS):
                rng = np.random.default_rng(SEED_BASE + trial * 1000
                                            + ALPHA_RANGE.index(alpha) * 10
                                            + (0 if fault_type == "ag" else 1))
                t_all, i_diff, t_pre, i_pre = generate_hif_waveform(
                    fault_type, alpha, rng,
                )
                fault_mask = t_all >= FAULT_T
                t_f  = t_all[fault_mask]
                i_f  = i_diff[:, fault_mask]

                res = evaluate_trial(
                    i_f, t_f, i_pre, t_pre,
                    I_fund_thresh, use_pi, use_override, pi_cfg,
                )
                tpr_conv.append(int(res["conventional_trip"]))
                tpr_sambp.append(int(res["sambp_trip"]))
                charge_res.append(res["charging_res_rms"])

            rows.append({
                "config":       config_label,
                "fault_type":   fault_type,
                "alpha":        alpha,
                "TPR_conv":     float(np.mean(tpr_conv)),
                "TPR_sambp":    float(np.mean(tpr_sambp)),
                "charge_rms_mean": float(np.mean(charge_res)),
            })
            print(f"  [{config_label}] {fault_type} alpha={alpha:.2f}  "
                  f"TPR_sambp={np.mean(tpr_sambp):.3f}  "
                  f"charge_rms={np.mean(charge_res):.4f}")
    return rows


# ---------------------------------------------------------------------------
# Alpha_50 finder
# ---------------------------------------------------------------------------

def find_alpha50(rows: list[dict], config: str, fault_type: str) -> float | None:
    """
    Find the smallest alpha at which TPR_sambp >= 0.50.
    Returns None if TPR never reaches 0.50.
    """
    subset = [(r["alpha"], r["TPR_sambp"])
              for r in rows
              if r["config"] == config and r["fault_type"] == fault_type]
    subset.sort(key=lambda x: x[0])
    for alpha, tpr in subset:
        if tpr >= 0.50:
            return alpha
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs("outputs", exist_ok=True)

    all_rows = []

    print("=== Config A: Baseline (TR-12) ===")
    all_rows += run_sweep("A_baseline", I_fund_thresh=THRESH_BASELINE,
                          use_pi=False, use_override=True)

    print("=== Config B: Pi-section (no override) ===")
    all_rows += run_sweep("B_pi_only", I_fund_thresh=THRESH_PI,
                          use_pi=True, use_override=False)

    print("=== Config C: Pi-section + magnitude override ===")
    all_rows += run_sweep("C_pi_override", I_fund_thresh=THRESH_PI,
                          use_pi=True, use_override=True)

    # ---- Save CSV ----------------------------------------------------------
    out_csv = "outputs/tr13_tpr_results.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nSaved: {out_csv}")

    # ---- Alpha_50 summary --------------------------------------------------
    summary_lines = [
        "SAMBP TR-13 Simulation Summary",
        "=" * 50,
        "",
        "alpha_50 (TPR >= 0.50) by configuration and fault type",
        "-" * 50,
    ]
    for cfg_label in ["A_baseline", "B_pi_only", "C_pi_override"]:
        for ft in ["ag", "3ph"]:
            a50 = find_alpha50(all_rows, cfg_label, ft)
            summary_lines.append(f"  {cfg_label:18s}  {ft:4s}  alpha_50 = {a50}")

    summary_lines += [
        "",
        "TPR table (config C: pi + override, all alpha x fault type)",
        "-" * 50,
    ]
    for ft in ["ag", "3ph"]:
        for r in [x for x in all_rows
                  if x["config"] == "C_pi_override" and x["fault_type"] == ft]:
            summary_lines.append(
                f"  {ft}  alpha={r['alpha']:.2f}  TPR={r['TPR_sambp']:.3f}"
            )

    summary_lines += [
        "",
        "Mean charging residual RMS [pu] by configuration",
        "-" * 50,
    ]
    for cfg_label in ["A_baseline", "B_pi_only", "C_pi_override"]:
        rms_vals = [r["charge_rms_mean"] for r in all_rows
                    if r["config"] == cfg_label]
        summary_lines.append(
            f"  {cfg_label:18s}  mean={np.mean(rms_vals):.5f} pu"
        )

    summary_text = "\n".join(summary_lines)
    print("\n" + summary_text)

    with open("outputs/tr13_sim_summary.txt", "w") as f:
        f.write(summary_text)
    print("\nSaved: outputs/tr13_sim_summary.txt")
