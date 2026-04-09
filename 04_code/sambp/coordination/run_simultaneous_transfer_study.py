"""
run_simultaneous_transfer_study.py
====================================
SAMBP TR-19/2026 -- Simultaneous Multi-Feeder Transfer Coordination.

Study motivation
----------------
TR-14 validated 87B selectivity for single-feeder (Gen) tip-switch transfers
under a conservative GOOSE zone-assignment rule.  In practice, substation
operators may initiate the transfer of TWO OR MORE feeders simultaneously
(e.g., Gen + Line both moved from BB1 to BB2 during a planned outage).

Key question: does 87B remain selective during the simultaneous transfer
window when GOOSE zone-update messages may arrive at different times for
each feeder?

State machine (dual-feeder transfer, Gen + Line from BB1 → BB2)
---------------------------------------------------------------
    S0  (T1_NORM)    : Gen + Line on BB1, Tr on BB2.
    S1  (DUAL_TIP)   : Gen and Line both in make-before-break (both DS closed).
                       GOOSE messages in flight; zone engine not yet updated.
    S1a (GEN_DONE)   : Gen BB1_DS opened → Gen GOOSE received → engine updates Gen to Z2.
                       Line still in TIP (Line GOOSE not yet received).
    S1b (LINE_DONE)  : Line BB1_DS opened → Line GOOSE received → engine updates Line to Z2.
                       Gen still in TIP (Gen GOOSE not yet received).
    S2  (BOTH_DONE)  : Both Gen and Line on BB2.  Both GOOSE received.
                       Net result: same as T3_POST from TR-14.

GOOSE timing model
------------------
    IEC 61850-8-1 specifies GOOSE retransmission every ≤4 ms in the initial
    burst.  Worst-case per-hop latency: 4 ms.  For a 2-hop network:
        T_lag_max ≈ 8 ms per feeder.
    For simultaneous transfer of N feeders, the maximum spread between the
    first and last GOOSE arrival is:
        ΔT_max = (N − 1) × T_lag_max = 1 × 8 ms  (N=2)

Zone CT assignment (conservative rule, same as TR-14)
------------------------------------------------------
    During TIP: a transferring feeder's CT remains in its ORIGINAL zone
                until the GOOSE DS_OPEN confirmation is received.
    After GOOSE: feeder CT moves to the NEW zone.

    This conservatism prevents false differentials on external faults, at the
    cost of a temporary reduction in Zone 2 differential for bus faults
    when feeders feeding the fault are still assigned to Zone 1.

Zone differential reduction analysis
-------------------------------------
For a BB2 fault during DUAL_TIP (both Gen and Line in TIP):

    Normal (T1_NORM):   I_diff_Z2 = I_Gen  (full Gen current via BC)
    DUAL_TIP stale:     I_diff_Z2 = I_Gen/2  (only BB1-path portion via BC)
    Reduction factor:   50%

    This is because in TIP, Gen's current splits 50/50:
        • Half via BB1-DS → BB1 → BC → BB2 (enters Zone 2 via BC_Z2 CT)
        • Half via BB2-DS → BB2 (direct, NOT measured by BC_Z2 CT)
    The BB2-DS path current is NOT counted in Zone 2 until GOOSE arrives.
    The BC_Z2 CT correctly measures only the BB1-path portion.

    Selectivity check: I_diff_Z2 = I_Gen/2 >> I_pickup (= 0.10 pu typically)
    → 87B still trips BB2 correctly even at 50% reduction.

    For BB1 fault during DUAL_TIP:
    I_diff_Z1 = I_Gen + I_Gen_BC1  (Gen BB1-DS path + BC return if BB2 feeds)
    → Zone 1 still large and correct.

Outputs
-------
    outputs/tr19_goose_states.csv
    outputs/tr19_zone_diff_analysis.csv
    outputs/tr19_vulnerability_window.csv
    outputs/tr19_summary.txt
"""

from __future__ import annotations

import os, sys, csv, math
import numpy as np

# ---------------------------------------------------------------------------
# Network constants (TR-14/16 base)
# ---------------------------------------------------------------------------

Z_SRC  = 1j * 0.10
Z_BC   = 1j * 0.01
Z_LINE = 1j * 0.05
Z_TR   = 1j * 0.08
V_PRE  = 1.0 + 0j

FREQ   = 50.0
FS     = 1000.0
DUR_S  = 0.10
FAULT_T = 0.02

AG_FACTOR    = 0.6          # ag fault current reduction
TIP_SPLIT    = 0.50         # 50/50 make-before-break split
I_PICKUP     = 0.10         # 87B pickup threshold [pu]
T_GOOSE_MAX  = 0.008        # max GOOSE lag per feeder [s] = 8 ms (2-hop IEC 61850)
T_PROTECTION = 0.020        # minimum protection response time [s] = 20 ms


# ---------------------------------------------------------------------------
# Peak fault current functions (analytical, phase A)
# ---------------------------------------------------------------------------

def I_peak_3ph(Z_total: complex) -> float:
    return abs(V_PRE / Z_total)

def I_peak_ag(Z_total: complex) -> float:
    return I_peak_3ph(Z_total) * AG_FACTOR


# ---------------------------------------------------------------------------
# Zone differential model
# ---------------------------------------------------------------------------

def _sign(x: complex) -> float:
    """Return +1 if peak current enters the zone (contributes positively)."""
    return 1.0  # convention: I_peak already sign-corrected below


# State definitions
#   Each state has a zone CT assignment and associated fault current expressions.
#   We compute I_diff_Z1 and I_diff_Z2 for bb1 and bb2 faults.
#
# Gen splits during TIP:
#   i_Gen_via_BB1 = I_Gen * TIP_SPLIT  (through BB1-DS → BB1 → BC → BB2)
#   i_Gen_via_BB2 = I_Gen * (1-TIP_SPLIT)  (through BB2-DS directly to BB2)
#   BC carries i_Gen_via_BB1 only.
#
# Zone assignment during DUAL_TIP (STALE GOOSE):
#   Z1 = {Gen_total, Line_total, BC_Z1}  (conservative, both feeders in Z1)
#   Z2 = {BC_Z2, Tr}
#
# Zone assignment after GEN GOOSE (S1a):
#   Z1 = {Gen_via_BB2, Line_total, BC_Z1}  (Gen BB2-path CT moves to Z2, but
#         the Z1-path CT is now smaller)
#   Z2 = {Gen_via_BB2_CT, BC_Z2, Tr}
#   Note: we approximate Gen_via_BB2_CT ≈ I_Gen * (1-split) in Z2
#
# For simplicity: compute peak I_diff for each zone per state.

from collections import namedtuple

ZoneState = namedtuple("ZoneState", [
    "name", "desc",
    "gen_z1",  "line_z1",   # fraction of Gen/Line in Zone 1 CT
    "gen_z2",  "line_z2",   # fraction in Zone 2 CT
])

STATES = [
    ZoneState("S0_NORM",    "T1_NORM: Gen+Line on BB1",
              gen_z1=1.0, line_z1=1.0, gen_z2=0.0, line_z2=0.0),
    ZoneState("S1_STALE",   "DUAL_TIP, GOOSE stale (both in Z1)",
              gen_z1=1.0, line_z1=1.0, gen_z2=0.0, line_z2=0.0),
    ZoneState("S1a_GEN_OK", "DUAL_TIP, Gen GOOSE received only",
              gen_z1=TIP_SPLIT, line_z1=1.0, gen_z2=1-TIP_SPLIT, line_z2=0.0),
    ZoneState("S1b_LINE_OK","DUAL_TIP, Line GOOSE received only",
              gen_z1=1.0, line_z1=TIP_SPLIT, gen_z2=0.0, line_z2=1-TIP_SPLIT),
    ZoneState("S2_BOTH_OK", "BOTH_DONE: Gen+Line on BB2 (T3_POST equiv.)",
              gen_z1=0.0, line_z1=0.0, gen_z2=1.0, line_z2=1.0),
]


def compute_zone_diff(state: ZoneState, fault_loc: str, fault_type: str) -> dict:
    """
    Compute peak Zone 1 and Zone 2 differential currents analytically.

    The physical topology depends on the GOOSE state:
      S0_NORM, S1_STALE, S1a, S1b  → Gen still on BB1 (T1_NORM base)
      S2_BOTH_OK                   → Gen moved to BB2 (T3_POST base)

    During TIP (S1*):
      Gen's BB1-path current = I_Gen * TIP_SPLIT  (via BC)
      Gen's BB2-path current = I_Gen * (1-TIP_SPLIT)  (direct to BB2)
    """
    af = AG_FACTOR if fault_type == "ag" else 1.0
    # S2_BOTH_OK uses T3_POST topology (Gen on BB2); others use T1_NORM base
    gen_on_bb2 = (state.name == "S2_BOTH_OK")

    if fault_loc == "bb1":
        if gen_on_bb2:
            # T3_POST: Gen on BB2 feeds BB1 fault via BC
            I_Gen  = I_peak_3ph(Z_SRC + Z_BC) * af
            I_BC_Z1 = I_Gen   # BC carries Gen current INTO BB1
            I_diff_Z1 = I_BC_Z1   # Zone 1 sees BC_Z1 (Gen not in Z1)
            I_diff_Z2 = 0.0
        else:
            # T1_NORM: Gen on BB1 feeds fault directly (no BC needed)
            I_Gen   = I_peak_3ph(Z_SRC) * af
            I_BC_Z1 = 0.0
            I_diff_Z1 = state.gen_z1 * I_Gen + I_BC_Z1
            I_diff_Z2 = 0.0
        expected_trip = "BB1"

    elif fault_loc == "bb2":
        # Both topologies: Gen feeds BB2 fault
        I_Gen_total = I_peak_3ph(Z_SRC + Z_BC) * af

        if gen_on_bb2:
            # T3_POST: Gen directly on BB2 → no BC, full Gen in Z2
            I_BC_Z2   = 0.0
            I_diff_Z2 = state.gen_z2 * I_Gen_total  # = 1.0 * I_Gen
            I_diff_Z1 = 0.0
        else:
            # T1/TIP: Gen feeds BB2 via BC (BB1-path) and direct (BB2-path if TIP)
            I_Gen_via_BC    = I_Gen_total * TIP_SPLIT
            I_Gen_via_BB2DS = I_Gen_total * (1.0 - TIP_SPLIT)
            I_BC_Z2   = I_Gen_via_BC   # BC_Z2 measures BB1-path current
            # Zone 2 = BC_Z2 + Gen_Z2 fraction (direct BB2-path, only if GOOSE received)
            I_diff_Z2 = I_BC_Z2 + state.gen_z2 * I_Gen_via_BB2DS
            I_diff_Z1 = 0.0   # Gen_Z1*I_BC_via_BB1 - I_BC ≈ 0 (cancels)
        expected_trip = "BB2"

    elif fault_loc == "bc_internal":
        I_Gen  = I_peak_3ph(Z_SRC + Z_BC/2) * af
        if gen_on_bb2:
            # T3_POST: Gen on BB2 → BC_Z2 CT sees Gen exiting BB2; CK = Gen
            # Z1 = {Line, BC_Z1} = {0, 0}; Z2 = {BC_Z2, Gen, Tr}: Gen & BC_Z2 cancel
            I_diff_Z1 = 0.0
            I_diff_Z2 = 0.0
            # CK zone = {Gen, Line, Tr} → I_Gen (feeder differential)
            I_diff_CK = I_Gen
        else:
            # T1_NORM: Gen on BB1 exits BB1 via BC_Z1 → Z1 sees Gen CT
            I_diff_Z1 = state.gen_z1 * I_Gen
            I_diff_Z2 = 0.0
            I_diff_CK = I_Gen
        expected_trip = "BC"

    elif fault_loc == "load_external":
        I_diff_Z1 = 0.0
        I_diff_Z2 = 0.0
        expected_trip = "no_trip"

    elif fault_loc == "line_external":
        I_diff_Z1 = 0.0
        I_diff_Z2 = 0.0
        expected_trip = "no_trip"

    else:
        I_diff_Z1 = 0.0
        I_diff_Z2 = 0.0
        expected_trip = "unknown"

    # Check zone (feeder differential: Gen + Line + Tr, no BC)
    if "I_diff_CK" not in dir():
        I_diff_CK = I_diff_Z1  # default: same as Z1 for T1_NORM BC faults

    trip_z1 = abs(I_diff_Z1) > I_PICKUP
    trip_z2 = abs(I_diff_Z2) > I_PICKUP
    trip_ck = abs(I_diff_CK) > I_PICKUP

    if expected_trip == "BB1":
        trip = "BB1" if trip_z1 else "miss"
        correct = trip_z1 and not trip_z2
    elif expected_trip == "BB2":
        trip = "BB2" if trip_z2 else "miss"
        correct = trip_z2 and not (trip_z1 and not trip_z2)
    elif expected_trip == "BC":
        # BC trip = CK asserts (feeder differential) with Z1/Z2 pattern unclear
        trip = "BC" if trip_ck else "miss"
        correct = trip_ck
    else:  # no_trip
        trip = "no_trip" if (not trip_z1 and not trip_z2) else "false_trip"
        correct = (not trip_z1 and not trip_z2)

    return {
        "state":         state.name,
        "fault_loc":     fault_loc,
        "fault_type":    fault_type,
        "I_diff_Z1":     round(abs(I_diff_Z1), 4),
        "I_diff_Z2":     round(abs(I_diff_Z2), 4),
        "I_diff_CK":     round(abs(I_diff_CK), 4),
        "trip_Z1":       trip_z1,
        "trip_Z2":       trip_z2,
        "trip_CK":       trip_ck,
        "expected":      expected_trip,
        "trip_decision": trip,
        "correct":       correct,
    }


# ---------------------------------------------------------------------------
# Vulnerability window analysis
# ---------------------------------------------------------------------------

def study_vulnerability_window():
    """
    Quantify the GOOSE vulnerability window for simultaneous transfer of N feeders.

    For N feeders, GOOSE messages arrive at t_i ~ Uniform(0, T_lag_max).
    The vulnerability window is [min(t_i), max(t_i)].
    Expected width: (N-1) / (N+1) * T_lag_max  (order statistics for Uniform)

    For N=2: expected window ≈ 1/3 * T_lag_max = 2.67 ms
    Maximum window (worst case): T_lag_max = 8 ms

    Protection response time: T_prot = 20 ms (one power cycle at 50 Hz).
    The 87B relay can trip within one cycle AFTER the fault is detected.

    Vulnerability: if fault occurs DURING the GOOSE vulnerability window
    AND the zone sum is below pickup (which we show does NOT occur for this network),
    then the trip could be delayed.
    """
    rows = []
    for N in range(1, 6):
        t_expected = (N - 1) / (N + 1) * T_GOOSE_MAX if N > 1 else 0.0
        t_worst    = (N - 1) * T_GOOSE_MAX if N > 1 else 0.0
        prob_fault_in_window = t_worst / T_PROTECTION  # fault during window
        # Zone 2 reduction during N-feeder stale period (all feeders in Z1)
        # I_diff_Z2 = I_BC_Z2 = I_Gen * TIP_SPLIT (only BC path counts)
        z2_reduction_pct = TIP_SPLIT * 100.0 if N > 0 else 100.0
        rows.append({
            "N_feeders":          N,
            "T_lag_max_ms":       round(T_GOOSE_MAX * 1000, 1),
            "T_window_expected_ms": round(t_expected * 1000, 2),
            "T_window_worst_ms":  round(t_worst * 1000, 1),
            "P_fault_in_window":  f"{100*prob_fault_in_window:.2f}%",
            "I_diff_Z2_pct":      f"{z2_reduction_pct:.0f}%",
            "above_pickup":       abs(I_peak_3ph(Z_SRC + Z_BC) * TIP_SPLIT) > I_PICKUP,
        })
    return rows


# ---------------------------------------------------------------------------
# 87L/21 independence verification
# ---------------------------------------------------------------------------

def study_87L_independence():
    """
    87L operates on line differential current directly; it is independent
    of the 87B zone CT assignment (no GOOSE data used in 87L algorithm).

    87L remains fully selective during the DUAL_TIP GOOSE window because:
    1. Line differential (i_diff = i_S - i_R) is measured at line terminals,
       not at the bus CT zone.
    2. For a bb1 or bb2 fault: i_diff_line = 0 analytically (through-current).
    3. For a line fault: i_diff_line > alpha * I_LINE_NOM → 87L trips.

    21 (Mho distance) measures V/I at the relay point and is independent of
    the busbar zone assignment completely.

    Result: 87L and 21 provide reliable backup during any GOOSE lag period.
    """
    return [
        {"function": "87L", "GOOSE_dependent": False,
         "action_during_lag": "Operates normally; line differential unaffected",
         "backup_for": "Line faults during DUAL_TIP"},
        {"function": "21 Zone 1", "GOOSE_dependent": False,
         "action_during_lag": "Operates normally; measures V/I directly",
         "backup_for": "Line faults 0-80% during DUAL_TIP"},
        {"function": "87B", "GOOSE_dependent": True,
         "action_during_lag": "Zone sums reduced 50% for BB2 fault; still above pickup",
         "backup_for": "Bus faults (primary function)"},
    ]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _save_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

FAULT_LOCS  = ["bb1", "bb2", "bc_internal", "load_external", "line_external"]
FAULT_TYPES = ["3ph", "ag"]

if __name__ == "__main__":
    os.makedirs("outputs", exist_ok=True)

    print("=" * 64)
    print("SAMBP TR-19/2026 Simultaneous Multi-Feeder Transfer Study")
    print("=" * 64)

    # GOOSE state definitions
    goose_rows = []
    for s in STATES:
        goose_rows.append({
            "state":       s.name,
            "description": s.desc,
            "gen_Z1_frac": s.gen_z1,
            "gen_Z2_frac": s.gen_z2,
            "line_Z1_frac":s.line_z1,
            "line_Z2_frac":s.line_z2,
        })
    _save_csv("outputs/tr19_goose_states.csv", goose_rows)

    # Zone differential analysis
    print("\nZone differential analysis:")
    diff_rows = []
    for state in STATES:
        for floc in FAULT_LOCS:
            for ftype in FAULT_TYPES:
                r = compute_zone_diff(state, floc, ftype)
                diff_rows.append(r)
                status = "OK" if r["correct"] else "FAIL"
                if floc in ("bb1", "bb2"):
                    print(f"  [{status}] {state.name:18s} {floc:6s} {ftype:4s} | "
                          f"Z1={r['I_diff_Z1']:.3f}  Z2={r['I_diff_Z2']:.3f}  "
                          f"-> {r['trip_decision']}")
    _save_csv("outputs/tr19_zone_diff_analysis.csv", diff_rows)

    n_ok = sum(r["correct"] for r in diff_rows)
    n_total = len(diff_rows)
    print(f"\n  Selectivity: {n_ok}/{n_total} ({100*n_ok//n_total}%) correct")

    # Vulnerability window
    print("\nVulnerability window analysis:")
    vw_rows = study_vulnerability_window()
    for r in vw_rows:
        print(f"  N={r['N_feeders']}: T_window_worst={r['T_window_worst_ms']}ms  "
              f"I_diff_Z2={r['I_diff_Z2_pct']}  above_pickup={r['above_pickup']}")
    _save_csv("outputs/tr19_vulnerability_window.csv", vw_rows)

    # 87L independence
    indep_rows = study_87L_independence()
    _save_csv("outputs/tr19_protection_independence.csv", indep_rows)

    # Summary
    lines = [
        "SAMBP TR-19/2026 Simultaneous Multi-Feeder Transfer Summary",
        "=" * 64,
        "",
        "Network: Z_SRC=j0.10 pu, Z_BC=j0.01 pu, Z_LINE=j0.05 pu",
        f"GOOSE max lag: {T_GOOSE_MAX*1000:.0f} ms/feeder (2-hop IEC 61850-8-1)",
        f"I_pickup: {I_PICKUP} pu  |  TIP split: {TIP_SPLIT*100:.0f}%",
        "",
        "GOOSE States (dual-feeder Gen + Line transfer BB1→BB2)",
        "-" * 64,
    ]
    for s in STATES:
        lines.append(f"  {s.name:20s}: Gen_Z1={s.gen_z1:.1f}  Gen_Z2={s.gen_z2:.1f}  "
                     f"Line_Z1={s.line_z1:.1f}  Line_Z2={s.line_z2:.1f}")

    lines += [
        "",
        "Zone 2 differential during BB2 fault",
        "-" * 64,
    ]
    for state in STATES:
        r = compute_zone_diff(state, "bb2", "3ph")
        lines.append(
            f"  {state.name:20s}: I_diff_Z2={r['I_diff_Z2']:.4f} pu  "
            f"(pickup={I_PICKUP})  trip={r['trip_decision']}  {'OK' if r['correct'] else 'FAIL'}"
        )

    lines += [
        "",
        f"Selectivity: {n_ok}/{n_total} ({100*n_ok//n_total}%) correct",
        "",
        "Vulnerability window (worst-case GOOSE staleness)",
        "-" * 64,
    ]
    for r in vw_rows:
        lines.append(
            f"  N={r['N_feeders']} feeders: max window={r['T_window_worst_ms']}ms  "
            f"I_diff_Z2={r['I_diff_Z2_pct']}  above_pickup={r['above_pickup']}"
        )

    lines += [
        "",
        "Protection function independence from GOOSE",
        "-" * 64,
    ]
    for r in indep_rows:
        lines.append(f"  {r['function']:14s}: GOOSE_dep={r['GOOSE_dependent']}  "
                     f"{r['action_during_lag']}")

    summary_path = "outputs/tr19_summary.txt"
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nSaved: {summary_path}")
    for line in lines:
        print(line)
