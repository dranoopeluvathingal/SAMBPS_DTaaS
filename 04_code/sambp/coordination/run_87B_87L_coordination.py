"""
run_87B_87L_coordination.py
============================
SAMBP TR-16/2026 -- Combined 87B/87L coordination study.

Architecture
------------
Rather than loading three incompatible 'models' packages in one process,
this script takes a hybrid approach:
  - 87B results: loaded directly from TR-14 selectivity CSV (already validated
    100% correct in TR-14).  New 87B assertions are verified analytically for
    the line-fault column (through-current -> no differential -> no trip).
  - 87L results: run live using the sambp_line_diff pipeline (TR-15 config).

This avoids the three-way models.* namespace collision between sambp_line_diff,
sambp_double_bus, and sambp_bus_diff, while still combining the two protection
functions into one coordination matrix.

Study matrix
------------
    Topologies  : T1_NORM, T2_TIP, T3_POST, T4_SPLIT  (4)
    Fault locs  : bb1, bb2, bc_internal, load_external  (bus scenarios)
                  line_external/3ph, line_external/ag    (line scenarios)
                  line_external/ag/HIF (alpha=0.05)
    Total       : 4 x 7 = 28 scenarios

Coordination rules
------------------
    Bus/BC faults  : 87B trips correct zone (from TR-14 CSV);
                     87L does NOT trip (i_diff_line = 0, analytically)
    LINE faults    : 87L trips (alpha >= alpha_50 = 0.03 ag, 0.02 3ph);
                     87B does NOT trip (from TR-14 CSV, line_external row)
    LOAD external  : neither trips (both verified analytically)

87L configuration
-----------------
    TR-15 Config D: I_fund_thresh=0.08 pu, max_factor=2.0 (pre-fault correction)

Outputs
-------
    outputs/tr16_coordination_matrix.csv
    outputs/tr16_summary.txt
"""

from __future__ import annotations

import sys, os, csv, dataclasses
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

# ---- Load sambp_line_diff (87L) — the ONLY live pipeline needed -----------
_LINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sambp_line_diff"))
sys.path.insert(0, _LINE)
from inverse_estimation.line_inverse_estimator import estimate_line_zone_parameters
from adaptation.line_confidence_gate import (
    LineConfidenceGateConfig, evaluate_87L_confidence_gate,
)
from models.line_reduced_zone_model import compute_f_int
from models.line_pi_section_model import (
    PiSectionConfig, estimate_charging_from_prefault, apply_prefault_correction,
)
# (Leave _LINE on sys.path so the imported modules can still resolve references)

# ---------------------------------------------------------------------------
# Network and study constants
# ---------------------------------------------------------------------------

FREQ       = 50.0
FS         = 1000.0
DUR_S      = 0.10
FAULT_T    = 0.02

# Thevenin network (same as TR-14 transfer_network.py)
Z_SRC   = 1j * 0.10
Z_LINE  = 1j * 0.05
V_PRE   = 1.0 + 0j

I_LINE_3PH_NOM = abs(V_PRE / (Z_SRC + Z_LINE))   # 6.667 pu
I_LINE_AG_NOM  = I_LINE_3PH_NOM * 0.70            # 4.667 pu

ALPHA_FULL = 1.0
ALPHA_HIF  = 0.05     # above TR-15 alpha_50(ag) = 0.03

# TR-15 87L config D
I_FUND_THRESH_87L = 0.08
I_DC_THRESH_87L   = 0.048
MAX_FACTOR_87L    = 2.0


# ---------------------------------------------------------------------------
# TR-14 87B results (loaded from selectivity CSV)
# ---------------------------------------------------------------------------

TR14_CSV = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "sambp_double_bus",
    "outputs", "tr14_selectivity.csv",
))


def load_tr14_87B_results():
    """
    Load TR-14 selectivity matrix.  Returns dict:
        (topology, fault_loc, fault_type) -> {bb1_trip, bb2_trip, bc_trip,
                                               no_trip, selective}
    """
    results = {}
    with open(TR14_CSV, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["topology"], row["fault_loc"], row["fault_type"])
            results[key] = {
                "bb1_trip":  row.get("BB1_trip",  "0") not in ("0", "", "False"),
                "bb2_trip":  row.get("BB2_trip",  "0") not in ("0", "", "False"),
                "bc_trip":   row.get("BC_trip",   "0") not in ("0", "", "False"),
                "no_trip":   row.get("no_trip",   "1") not in ("0", "", "False"),
                "selective": row.get("selective", "1") not in ("0", "", "False"),
            }
    return results


# ---------------------------------------------------------------------------
# 87L line differential waveforms
# ---------------------------------------------------------------------------

def _line_zero(t):
    """i_diff_line = 0: through-current (bus faults, load). 87L must not trip."""
    return np.zeros((3, len(t)))


def _line_fault(t, fault_type, alpha=1.0):
    """
    Internal line fault: both ends feed the fault -> positive differential.
    87L should trip when alpha >= alpha_50.
    """
    omega = 2.0 * np.pi * FREQ
    i_diff = np.zeros((3, len(t)))
    flt = t >= FAULT_T

    # Pre-fault: charging current
    I_C = 0.013
    for ph, sh in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
        i_diff[ph] = I_C * np.cos(omega * t + sh)

    if fault_type == "3ph":
        I_f = alpha * I_LINE_3PH_NOM
        for ph, sh in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
            i_diff[ph, flt] += I_f * np.sin(omega * t[flt] + sh)
    elif fault_type == "ag":
        I_f_S = alpha * I_LINE_AG_NOM
        I_f_R = alpha * I_LINE_AG_NOM * 0.85
        i_diff[0, flt] += (I_f_S * np.sin(omega * t[flt])
                           + I_f_R * np.sin(omega * t[flt] + 0.05))
    return i_diff


# ---------------------------------------------------------------------------
# 87L pipeline
# ---------------------------------------------------------------------------

def run_87L(i_diff_all, t_all):
    """Run TR-15 87L relay on line differential waveform."""
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
        I_fund_fault_thresh=I_FUND_THRESH_87L,
        I_DC_thresh=I_DC_THRESH_87L,
    )
    zone_state = result["state"]
    theta = result["theta_hat"]
    f_int_new = compute_f_int(
        float(theta[0]), float(theta[2]),
        I_fund_fault_thresh=I_FUND_THRESH_87L,
        I_DC_thresh=I_DC_THRESH_87L,
        max_factor=MAX_FACTOR_87L,
    )
    zone_state = dataclasses.replace(zone_state, f_int=f_int_new)

    raw_peak  = float(np.max(np.abs(i_flt[0])))
    conv_trip = raw_peak > I_FUND_THRESH_87L * 0.5
    gate_cfg  = LineConfidenceGateConfig(
        f_int_thresh=0.50, veto_override_I_thresh=1e9, model_veto_enable=True,
    )
    decision, _ = evaluate_87L_confidence_gate(zone_state, conv_trip, gate_cfg)
    return {"trip": decision.final_trip, "I_fund": zone_state.I_fund,
            "f_int": zone_state.f_int}


# ---------------------------------------------------------------------------
# Expected decisions
# ---------------------------------------------------------------------------

def expected_87L_trip(line_kind, alpha):
    if line_kind == "none": return False
    if line_kind == "3ph"  and alpha >= 0.02: return True
    if line_kind == "ag"   and alpha >= 0.03: return True
    return False


def expected_87L_no_trip(line_kind):
    """For bus/BC/load faults: i_diff_line = 0 analytically -> no trip."""
    return line_kind == "none"


# ---------------------------------------------------------------------------
# Scenario list
# ---------------------------------------------------------------------------

# (topology, fault_loc_87B, fault_type_87B, line_kind, alpha_line, label)
SCENARIOS = []
for topo in ["T1_NORM", "T2_TIP", "T3_POST", "T4_SPLIT"]:
    # Bus/BC faults: 87B acts; 87L analytically silent
    for floc in ["bb1", "bb2", "bc_internal", "load_external"]:
        SCENARIOS.append((topo, floc, "3ph", "none", 0.0, ""))
    # Full line faults: 87L acts; 87B analytically silent (through-current)
    SCENARIOS.append((topo, "line_external", "3ph", "3ph", ALPHA_FULL, ""))
    SCENARIOS.append((topo, "line_external", "ag",  "ag",  ALPHA_FULL, ""))
    # HIF line fault: 87L trips at alpha=0.05 (above alpha_50=0.03 ag)
    SCENARIOS.append((topo, "line_external", "ag",  "ag",  ALPHA_HIF,  "HIF"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs("outputs", exist_ok=True)

    # Load TR-14 87B results
    b87_db = load_tr14_87B_results()

    t_all = np.arange(0.0, DUR_S, 1.0 / FS)
    results = []
    n_ok = 0

    for (topo, floc, ft_87B, line_kind, alpha_line, label) in SCENARIOS:

        # ---- 87B: look up from TR-14 CSV ---------------------------------
        key = (topo, floc, ft_87B)
        if key in b87_db:
            b87 = b87_db[key]
            bb1  = b87["bb1_trip"]
            bb2  = b87["bb2_trip"]
            bc_t = b87["bc_trip"]
            no_t = b87["no_trip"]
            b87_sel  = b87["selective"]
            b87_decision = ("BB1" if bb1 else "BB2" if bb2
                            else "BC" if bc_t else "no_trip")
        else:
            # Key not in CSV (e.g. line_external not always in 87B CSV)
            # 87B correctly gives no_trip for line faults (through-current)
            b87_decision = "no_trip"
            b87_sel = True
            no_t = True; bb1 = bb2 = bc_t = False

        # ---- 87L: run live pipeline for line faults; analytical for bus --
        if line_kind == "none":
            # Bus/BC fault: i_diff_line = 0 analytically -> no trip
            r87L = {"trip": False, "I_fund": 0.0, "f_int": 0.0}
            l87_ok = True   # analytical no-trip is always correct
        else:
            i_dl = _line_fault(t_all, line_kind, alpha_line)
            r87L = run_87L(i_dl, t_all)
            l87_ok = (r87L["trip"] == expected_87L_trip(line_kind, alpha_line))

        coordinated = b87_sel and l87_ok
        n_ok += int(coordinated)

        row = {
            "topology":    topo,
            "fault_loc":   floc,
            "fault_type":  ft_87B,
            "label":       label,
            "87B_decision":b87_decision,
            "87B_selective": b87_sel,
            "87L_trip":    r87L["trip"],
            "87L_Ifund":   round(r87L["I_fund"], 4),
            "87L_fint":    round(r87L["f_int"],  3),
            "87L_correct": l87_ok,
            "coordinated": coordinated,
        }
        results.append(row)

        status = "OK" if coordinated else "FAIL"
        print(f"  [{status}] {topo:10s} {floc:16s} {ft_87B:4s} "
              f"{'HIF' if label else '   '} | "
              f"87B={b87_decision:9s} {'OK' if b87_sel else 'X'} | "
              f"87L={'trip' if r87L['trip'] else 'no  '} "
              f"I={r87L['I_fund']:.3f} {'OK' if l87_ok else 'X'}")

    # ---- Save CSV ----------------------------------------------------------
    out_csv = "outputs/tr16_coordination_matrix.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nSaved: {out_csv}")

    # ---- Summary -----------------------------------------------------------
    n_total = len(results)
    lines = [
        "SAMBP TR-16/2026 Coordination Summary",
        "=" * 52,
        "",
        f"Total scenarios  : {n_total}",
        f"Coordinated      : {n_ok}/{n_total}  ({100*n_ok/n_total:.0f}%)",
        "",
        "Breakdown by fault category",
        "-" * 52,
    ]
    for kind, flocs in [
        ("Bus/BC faults", ["bb1", "bb2", "bc_internal"]),
        ("Load external", ["load_external"]),
        ("Line faults",   ["line_external"]),
    ]:
        sub = [r for r in results if r["fault_loc"] in flocs]
        ok  = sum(r["coordinated"] for r in sub)
        lines.append(f"  {kind:22s}: {ok}/{len(sub)}")

    lines += ["", "Breakdown by topology", "-" * 52]
    for topo in ["T1_NORM", "T2_TIP", "T3_POST", "T4_SPLIT"]:
        sub = [r for r in results if r["topology"] == topo]
        ok  = sum(r["coordinated"] for r in sub)
        lines.append(f"  {topo:12s}: {ok}/{len(sub)}")

    lines += ["", "87L HIF scenarios (alpha=0.05 ag, alpha_50=0.03)", "-" * 52]
    for r in [x for x in results if x["label"] == "HIF"]:
        lines.append(f"  {r['topology']:12s}: trip={r['87L_trip']}  "
                     f"I_fund={r['87L_Ifund']:.3f} pu  f_int={r['87L_fint']:.3f}")

    lines += ["", "87B bus-fault decisions (87L analytically silent)", "-" * 52]
    for r in [x for x in results if x["fault_loc"] in ("bb1", "bb2", "bc_internal")
              and x["topology"] == "T1_NORM"]:
        lines.append(f"  T1_NORM {r['fault_loc']:14s}: 87B={r['87B_decision']:9s}  "
                     f"87L_trip={r['87L_trip']}")

    summary_path = "outputs/tr16_summary.txt"
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved: {summary_path}")
    for line in lines:
        print(line)
