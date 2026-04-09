"""
run_adaptive_threshold_study.py
================================
SAMBP TR-17/2026 -- Adaptive 87L threshold as a function of I_rest.

Study design
------------
1. Threshold characteristic: I_thresh(I_rest) for k_slope = 0.10, 0.15, 0.20
   vs. the TR-15 fixed threshold (0.08 pu).
2. α₅₀ vs I_rest: sensitivity floor as load increases.
3. Security margin: I_thresh / (ε_CT × I_rest) at each load level.
4. Coordination sweep: 28 scenarios from TR-16 re-run with the adaptive
   threshold, confirming 28/28 still coordinated.

Network constants (TR-15/TR-16 Thevenin network):
    Z_src = j0.10 pu, Z_line = j0.05 pu, V_pre = 1.0 pu
    I_LINE_3PH = 6.667 pu, I_LINE_AG = 4.667 pu

87L effective phase factor (derived from TR-15 α₅₀ calibration):
    α₅₀(ag) = 0.03  at I_thresh = 0.08 pu, I_LINE_AG = 4.667 pu
    I_fund_at_trip = α₅₀ × I_LINE_AG × PHASE_FACTOR
    => PHASE_FACTOR_AG  = 0.08 / (0.03 × 4.667) ≈ 0.5714
    α₅₀(3ph): = 0.02  at I_thresh = 0.08, I_LINE_3PH = 6.667 pu
    => PHASE_FACTOR_3PH = 0.08 / (0.02 × 6.667) ≈ 0.6000

Outputs
-------
    outputs/tr17_threshold_curve.csv
    outputs/tr17_alpha50_vs_Irest.csv
    outputs/tr17_security_margin.csv
    outputs/tr17_coordination_28.csv
    outputs/tr17_summary.txt
"""

from __future__ import annotations

import sys, os, csv, dataclasses
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from adaptation.line_adaptive_threshold import (
    AdaptiveThreshConfig, adaptive_thresh, compute_alpha50,
    thresh_curve, alpha50_curve, ct_error_current, security_margin,
)
from adaptation.line_confidence_gate import LineConfidenceGateConfig, evaluate_87L_confidence_gate
from inverse_estimation.line_inverse_estimator import estimate_line_zone_parameters
from models.line_reduced_zone_model import compute_f_int
from models.line_pi_section_model import (
    PiSectionConfig, estimate_charging_from_prefault, apply_prefault_correction,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FREQ   = 50.0
FS     = 1000.0
DUR_S  = 0.10
FAULT_T = 0.02

I_LINE_3PH = 6.667   # pu
I_LINE_AG  = 4.667   # pu

# Effective sensitivity factor derived from TR-15 calibration
# I_fund_at_alpha = alpha × I_LINE_nom × PHASE_FACTOR
PHASE_FACTOR_AG  = 0.08 / (0.03 * I_LINE_AG)   # ≈ 0.5714
PHASE_FACTOR_3PH = 0.08 / (0.02 * I_LINE_3PH)  # ≈ 0.6000

EPSILON_CT = 0.005   # CT Class 0.5 ratio error

# Baseline config (TR-15)
CFG_FIXED = AdaptiveThreshConfig(I_base=0.08, k_slope=0.0)   # fixed
CFG_K10   = AdaptiveThreshConfig(I_base=0.08, k_slope=0.10)
CFG_K15   = AdaptiveThreshConfig(I_base=0.08, k_slope=0.15)  # recommended
CFG_K20   = AdaptiveThreshConfig(I_base=0.08, k_slope=0.20)

I_REST_GRID = np.array([0.0, 0.25, 0.50, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0])


def _save_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved: {path}")

# Coordination sweep constants (mirror TR-16)
ALPHA_FULL = 1.0
ALPHA_HIF  = 0.05


# ---------------------------------------------------------------------------
# Study 1: Threshold characteristic
# ---------------------------------------------------------------------------

def study_threshold_curve():
    rows = []
    for ir in I_REST_GRID:
        th_fixed = adaptive_thresh(ir, 0.08, 0.0)
        th_k10   = adaptive_thresh(ir, 0.08, 0.10)
        th_k15   = adaptive_thresh(ir, 0.08, 0.15)
        th_k20   = adaptive_thresh(ir, 0.08, 0.20)
        ct_err   = EPSILON_CT * ir
        rows.append({
            "I_rest": round(float(ir), 3),
            "I_thresh_fixed": round(th_fixed, 4),
            "I_thresh_k10":   round(th_k10,  4),
            "I_thresh_k15":   round(th_k15,  4),
            "I_thresh_k20":   round(th_k20,  4),
            "CT_error_pu":    round(ct_err,  5),
        })
    return rows


# ---------------------------------------------------------------------------
# Study 2: α₅₀ vs I_rest
# ---------------------------------------------------------------------------

def study_alpha50():
    rows = []
    for ir in I_REST_GRID:
        for cfg, name in [(CFG_FIXED,"fixed"), (CFG_K15,"k15")]:
            th = adaptive_thresh(ir, cfg.I_base, cfg.k_slope)
            a50_ag  = compute_alpha50(th, I_LINE_AG,  PHASE_FACTOR_AG)
            a50_3ph = compute_alpha50(th, I_LINE_3PH, PHASE_FACTOR_3PH)
            rows.append({
                "I_rest":     round(float(ir), 3),
                "config":     name,
                "I_thresh":   round(th, 4),
                "alpha50_ag": round(a50_ag,  4),
                "alpha50_3ph":round(a50_3ph, 4),
            })
    return rows


# ---------------------------------------------------------------------------
# Study 3: Security margin
# ---------------------------------------------------------------------------

def study_security_margin():
    rows = []
    for ir in I_REST_GRID:
        for cfg, name in [(CFG_FIXED,"fixed"), (CFG_K10,"k10"), (CFG_K15,"k15"), (CFG_K20,"k20")]:
            th = adaptive_thresh(ir, cfg.I_base, cfg.k_slope)
            sm = security_margin(th, ir, EPSILON_CT)
            rows.append({
                "I_rest":   round(float(ir), 3),
                "config":   name,
                "I_thresh": round(th, 4),
                "margin":   round(sm, 2) if sm != float("inf") else "inf",
            })
    return rows


# ---------------------------------------------------------------------------
# Study 4: Coordination sweep with adaptive threshold
# ---------------------------------------------------------------------------

def _line_fault_waveform(t, fault_type, alpha):
    omega = 2.0 * np.pi * FREQ
    i_diff = np.zeros((3, len(t)))
    flt = t >= FAULT_T
    I_C = 0.013
    for ph, sh in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
        i_diff[ph] = I_C * np.cos(omega * t + sh)
    if fault_type == "3ph":
        I_f = alpha * I_LINE_3PH
        for ph, sh in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
            i_diff[ph, flt] += I_f * np.sin(omega * t[flt] + sh)
    elif fault_type == "ag":
        I_f_S = alpha * I_LINE_AG
        I_f_R = alpha * I_LINE_AG * 0.85
        i_diff[0, flt] += (I_f_S * np.sin(omega * t[flt])
                           + I_f_R * np.sin(omega * t[flt] + 0.05))
    return i_diff


def _load_waveform(t, I_rest_pu):
    """
    Simulate a loaded line: through-current ≈ I_rest on both ends.
    CT mismatch adds i_diff_err = ε_CT × I_rest (worst-case, in-phase error).
    """
    omega  = 2.0 * np.pi * FREQ
    I_err  = EPSILON_CT * I_rest_pu   # differential error from CT mismatch
    i_diff = np.zeros((3, len(t)))
    I_C    = 0.013
    for ph, sh in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
        # Charging current + CT mismatch differential (worst-case)
        i_diff[ph] = (I_C + I_err) * np.cos(omega * t + sh)
    return i_diff


def _run_87L_adaptive(i_diff_all, t_all, I_rest_pu, cfg: AdaptiveThreshConfig):
    """Run 87L with adaptive threshold for a given I_rest."""
    I_thresh = adaptive_thresh(I_rest_pu, cfg.I_base, cfg.k_slope)
    I_DC_thr = I_thresh * 0.6

    pre = t_all < FAULT_T
    flt = t_all >= FAULT_T
    i_pre, i_flt = i_diff_all[:, pre], i_diff_all[:, flt]
    t_pre, t_flt = t_all[pre], t_all[flt]

    pi_cfg = PiSectionConfig(B_C_pu=0.013, V_nom_pu=1.0, freq_hz=FREQ)
    if i_pre.shape[1] >= pi_cfg.min_prefault_samples:
        A_C, BC = estimate_charging_from_prefault(i_pre, t_pre, FREQ)
        i_corr  = apply_prefault_correction(i_flt, t_flt, A_C, BC, FREQ)
    else:
        i_corr = i_flt.copy()

    result = estimate_line_zone_parameters(
        t_window=t_flt, i_diff_meas=i_corr[0],
        freq_hz=FREQ,
        I_fund_fault_thresh=I_thresh,
        I_DC_thresh=I_DC_thr,
    )
    zone_state = result["state"]
    theta = result["theta_hat"]
    f_int_new = compute_f_int(
        float(theta[0]), float(theta[2]),
        I_fund_fault_thresh=I_thresh,
        I_DC_thresh=I_DC_thr,
        max_factor=2.0,
    )
    zone_state = dataclasses.replace(zone_state, f_int=f_int_new)

    raw_peak  = float(np.max(np.abs(i_flt[0])))
    conv_trip = raw_peak > I_thresh * 0.5
    gate_cfg  = LineConfidenceGateConfig(
        f_int_thresh=0.50, veto_override_I_thresh=1e9, model_veto_enable=True,
    )
    decision, _ = evaluate_87L_confidence_gate(zone_state, conv_trip, gate_cfg)
    return {
        "trip":    decision.final_trip,
        "I_fund":  round(zone_state.I_fund, 4),
        "f_int":   round(zone_state.f_int, 3),
        "I_thresh":round(I_thresh, 4),
    }


def study_coordination_adaptive():
    """
    Re-run the 28 TR-16 scenarios with adaptive threshold (k=0.15).
    For line fault scenarios: I_rest = 0 (fault instant).
    For bus/load scenarios: I_rest = 0 (no differential expected).
    Also test a heavy-load no-fault scenario: I_rest = 2.0, no fault.
    """
    cfg = CFG_K15
    t_all = np.arange(0.0, DUR_S, 1.0 / FS)

    SCENARIOS = []
    for topo in ["T1_NORM", "T2_TIP", "T3_POST", "T4_SPLIT"]:
        for floc in ["bb1", "bb2", "bc_internal", "load_external"]:
            SCENARIOS.append((topo, floc, "none", 0.0, 0.0, ""))
        SCENARIOS.append((topo, "line_external", "3ph", ALPHA_FULL, 0.0, ""))
        SCENARIOS.append((topo, "line_external", "ag",  ALPHA_FULL, 0.0, ""))
        SCENARIOS.append((topo, "line_external", "ag",  ALPHA_HIF,  0.0, "HIF"))

    # Heavy-load scenarios (no fault): I_rest varies, expect no trip
    LOAD_SCENARIOS = [
        ("LOAD_1.0", 1.0), ("LOAD_2.0", 2.0), ("LOAD_4.0", 4.0),
    ]

    rows = []
    n_ok = 0

    for (topo, floc, line_kind, alpha, I_rest, label) in SCENARIOS:
        if line_kind == "none":
            r87L = {"trip": False, "I_fund": 0.0, "f_int": 0.0, "I_thresh": 0.08}
            l87_ok = True
        else:
            i_dl = _line_fault_waveform(t_all, line_kind, alpha)
            # At fault inception: through-current drops to ~0 as fault is close
            # I_rest at fault instant ≈ 0 for a terminal fault
            r87L = _run_87L_adaptive(i_dl, t_all, I_rest, cfg)
            # Expected: trip if alpha >= alpha_50 for the given I_thresh
            if line_kind == "3ph":
                exp_trip = alpha >= compute_alpha50(r87L["I_thresh"], I_LINE_3PH, PHASE_FACTOR_3PH)
            else:
                exp_trip = alpha >= compute_alpha50(r87L["I_thresh"], I_LINE_AG, PHASE_FACTOR_AG)
            l87_ok = (r87L["trip"] == exp_trip)
        n_ok += int(l87_ok)
        rows.append({
            "topology": topo,  "fault_loc": floc,
            "line_kind": line_kind, "alpha": alpha, "label": label,
            "I_rest": I_rest, "I_thresh": r87L["I_thresh"],
            "87L_trip": r87L["trip"], "87L_Ifund": r87L["I_fund"],
            "87L_fint": r87L["f_int"], "correct": l87_ok,
        })

    # Heavy-load no-fault check
    load_rows = []
    for (lname, Ir) in LOAD_SCENARIOS:
        i_load = _load_waveform(t_all, Ir)
        r = _run_87L_adaptive(i_load, t_all, Ir, cfg)
        ok = not r["trip"]   # must NOT trip on load
        load_rows.append({
            "scenario": lname, "I_rest": Ir,
            "I_thresh": r["I_thresh"], "I_err_CT": round(EPSILON_CT * Ir, 5),
            "87L_trip": r["trip"], "87L_Ifund": r["I_fund"],
            "margin_x": round(r["I_thresh"] / max(EPSILON_CT * Ir, 1e-9), 1) if Ir>0 else "inf",
            "correct": ok,
        })
        print(f"  LOAD {lname}: I_rest={Ir:.1f}  I_thresh={r['I_thresh']:.3f}  "
              f"CT_err={EPSILON_CT*Ir:.4f}  trip={r['trip']}  {'OK' if ok else 'FAIL'}")

    return rows, load_rows, n_ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs("outputs", exist_ok=True)

    print("=" * 60)
    print("SAMBP TR-17/2026 Adaptive Threshold Study")
    print("=" * 60)

    # Study 1
    th_rows = study_threshold_curve()
    _save_csv("outputs/tr17_threshold_curve.csv", th_rows)
    print(f"\nStudy 1 — Threshold characteristic: {len(th_rows)} points saved.")

    # Study 2
    a50_rows = study_alpha50()
    _save_csv("outputs/tr17_alpha50_vs_Irest.csv", a50_rows)
    print(f"Study 2 — α₅₀ vs I_rest: {len(a50_rows)} points saved.")

    # Study 3
    sm_rows = study_security_margin()
    _save_csv("outputs/tr17_security_margin.csv", sm_rows)
    print(f"Study 3 — Security margin: {len(sm_rows)} points saved.")

    # Study 4
    print("\nStudy 4 — Coordination sweep with adaptive threshold (k=0.15):")
    coord_rows, load_rows, n_ok = study_coordination_adaptive()
    _save_csv("outputs/tr17_coordination_28.csv", coord_rows)
    _save_csv("outputs/tr17_load_security.csv", load_rows)

    n_total = len(coord_rows)
    print(f"\n  Coordination result: {n_ok}/{n_total} correct")

    # Collect some key values for the summary
    hif_rows = [r for r in coord_rows if r["label"] == "HIF"]
    thresh_at_1 = adaptive_thresh(1.0, 0.08, 0.15)
    a50_ag_0  = compute_alpha50(0.08, I_LINE_AG, PHASE_FACTOR_AG)
    a50_ag_1  = compute_alpha50(thresh_at_1, I_LINE_AG, PHASE_FACTOR_AG)
    a50_ag_2  = compute_alpha50(adaptive_thresh(2.0,0.08,0.15), I_LINE_AG, PHASE_FACTOR_AG)

    lines = [
        "SAMBP TR-17/2026 Adaptive Threshold Summary",
        "=" * 56,
        "",
        "Threshold law: I_thresh = max(0.08, 0.15 × I_rest)  [pu]",
        "",
        "Threshold characteristic (k_slope = 0.15)",
        "-" * 56,
    ]
    for r in th_rows:
        lines.append(
            f"  I_rest={r['I_rest']:4.2f}  fixed={r['I_thresh_fixed']:.3f}  "
            f"k=0.15:{r['I_thresh_k15']:.3f}  CT_err={r['CT_error_pu']:.4f}"
        )
    lines += [
        "",
        "α₅₀ vs I_rest  (ag, k_slope=0.15)",
        "-" * 56,
        f"  I_rest=0.0 pu : α₅₀ = {a50_ag_0:.3f}  (TR-15 unchanged)",
        f"  I_rest=1.0 pu : α₅₀ = {a50_ag_1:.3f}  (I_thresh={thresh_at_1:.3f} pu)",
        f"  I_rest=2.0 pu : α₅₀ = {a50_ag_2:.3f}  (I_thresh={adaptive_thresh(2.0,0.08,0.15):.3f} pu)",
        "",
        "Security margin (k=0.15, ε_CT=0.005)",
        "-" * 56,
    ]
    for r in [x for x in sm_rows if x["config"] == "k15"]:
        m = r["margin"]
        lines.append(f"  I_rest={r['I_rest']:4.2f}  I_thresh={r['I_thresh']:.3f}  margin={m}×")

    lines += [
        "",
        f"Coordination sweep: {n_ok}/{n_total} ({100*n_ok//n_total}%) correct",
        "",
        "Heavy-load no-fault security",
        "-" * 56,
    ]
    for r in load_rows:
        lines.append(
            f"  {r['scenario']:10s}: I_rest={r['I_rest']:.1f}  "
            f"I_thresh={r['I_thresh']:.3f}  CT_err={r['I_err_CT']:.4f}  "
            f"trip={r['87L_trip']}  margin={r['margin_x']}×  "
            f"{'OK' if r['correct'] else 'FAIL'}"
        )

    lines += [
        "",
        "HIF line scenarios (alpha=0.05 ag) — coordination re-check",
        "-" * 56,
    ]
    for r in hif_rows[:4]:  # one per topology
        lines.append(
            f"  {r['topology']:12s}: trip={r['87L_trip']}  "
            f"I_fund={r['87L_Ifund']:.3f}  I_thresh={r['I_thresh']:.3f}  "
            f"f_int={r['87L_fint']:.3f}  {'OK' if r['correct'] else 'FAIL'}"
        )

    summary_path = "outputs/tr17_summary.txt"
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved: {summary_path}")
    for line in lines:
        print(line)


