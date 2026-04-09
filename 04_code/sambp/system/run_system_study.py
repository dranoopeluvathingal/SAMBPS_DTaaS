"""
run_system_study.py
====================
SAMBP System Integration Study — TR-05/2026

Exercises all fault locations and fault types on the radial network model
and produces a selectivity matrix showing which relays trip for each scenario.

Expected selectivity (radial network, all differential protection):
    bus_A        → OC, 87B_A
    line_mid     → OC, 87L
    bus_B        → OC, 87B_B
    transformer_hv → OC, 87T
    bus_C_load   → OC only  (external fault, no differential)
"""

from __future__ import annotations

import sys, os
import numpy as np

# ---- Project root on path ---------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from network.radial_network import (
    generate_network_snapshot, FAULT_LOCATIONS, NetworkSnapshot
)
from coordinator.system_coordinator import run_system_coordination, CoordinatorDecision

# ---------------------------------------------------------------------------
# Expected trip sets — ground truth for selectivity scoring
# ---------------------------------------------------------------------------

EXPECTED_TRIPS = {
    "bus_A":           {"OC", "87B_A"},
    "line_mid":        {"OC", "87L"},
    "bus_B":           {"OC", "87B_B"},
    "transformer_hv":  {"OC", "87T"},
    "bus_C_load":      {"OC"},          # external fault: differential = 0
}

FAULT_TYPES = ["3ph", "ag"]

RELAY_ORDER = ["OC", "87B_A", "87L", "87B_B", "87T"]


# ---------------------------------------------------------------------------
# Run study
# ---------------------------------------------------------------------------

def run_study() -> list[CoordinatorDecision]:
    decisions = []
    for loc in FAULT_LOCATIONS:
        for ftype in FAULT_TYPES:
            snap = generate_network_snapshot(loc, ftype)
            dec  = run_system_coordination(snap)
            decisions.append(dec)
    return decisions


# ---------------------------------------------------------------------------
# Print selectivity matrix
# ---------------------------------------------------------------------------

def _trip_char(relay_id: str, dec: CoordinatorDecision) -> str:
    """Return a 2-char cell: trip/no-trip × correct/incorrect."""
    rr = next((r for r in dec.relay_results if r.relay_id == relay_id), None)
    if rr is None:
        return " ?"
    expected = EXPECTED_TRIPS[dec.fault_loc]
    should_trip = relay_id in expected

    if rr.final_trip and should_trip:
        return " T"     # correct trip
    elif not rr.final_trip and not should_trip:
        return " ·"     # correct restrain
    elif rr.final_trip and not should_trip:
        return " X"     # spurious trip  (selectivity violation)
    else:
        return " M"     # missed trip    (sensitivity failure)


def print_selectivity_matrix(decisions: list[CoordinatorDecision]) -> None:
    col_w = 9
    relay_w = 6

    # ---- Header ----
    header_parts = [f"{'Scenario':<22}"]
    for r in RELAY_ORDER:
        header_parts.append(f"{r:>{relay_w}}")
    header_parts.append(f"{'Selective':>10}  {'Tripped relays'}")
    print("".join(header_parts))
    print("-" * 100)

    n_correct = 0
    n_total   = 0

    for dec in decisions:
        row = [f"{dec.fault_loc + '/' + dec.fault_type:<22}"]
        for r in RELAY_ORDER:
            row.append(f"{_trip_char(r, dec):>{relay_w}}")

        expected  = EXPECTED_TRIPS[dec.fault_loc]
        selective = dec.is_selective(expected)
        n_total  += 1
        n_correct += int(selective)

        verdict   = "OK" if selective else "FAIL"
        row.append(f"  {verdict:>8}  {dec.tripped_relays}")
        print("".join(row))

    print("-" * 100)
    print(f"Selectivity: {n_correct}/{n_total}  "
          "(T=correct trip, ·=correct restrain, X=spurious, M=missed)")


def print_detail_table(decisions: list[CoordinatorDecision]) -> None:
    """Per-relay SAMBP parameters for each scenario."""
    print("\n--- SAMBP Parameter Detail ---")
    header = (f"{'Scenario':<22}  {'Relay':<7}  {'Trip':<5}  "
              f"{'Source':<16}  {'κ_n':>6}  {'f_int':>6}  {'I_op':>6}")
    print(header)
    print("-" * 85)
    for dec in decisions:
        label = f"{dec.fault_loc}/{dec.fault_type}"
        for rr in dec.relay_results:
            kn_s  = f"{rr.kappa_n:6.1f}" if np.isfinite(rr.kappa_n) else "   n/a"
            fi_s  = f"{rr.f_int:6.3f}"   if np.isfinite(rr.f_int)   else "   n/a"
            print(f"{label:<22}  {rr.relay_id:<7}  {str(rr.final_trip):<5}  "
                  f"{rr.source:<16}  {kn_s}  {fi_s}  {rr.I_op_peak:6.2f}")
        print()


# ---------------------------------------------------------------------------
# Selectivity scoring table
# ---------------------------------------------------------------------------

def compute_selectivity_score(decisions: list[CoordinatorDecision]) -> dict:
    """Return per-relay TP/FP/FN counts."""
    counts = {r: {"TP": 0, "FP": 0, "FN": 0, "TN": 0} for r in RELAY_ORDER}
    for dec in decisions:
        expected = EXPECTED_TRIPS[dec.fault_loc]
        for rr in dec.relay_results:
            r  = rr.relay_id
            st = r in expected
            if rr.final_trip and st:
                counts[r]["TP"] += 1
            elif rr.final_trip and not st:
                counts[r]["FP"] += 1
            elif not rr.final_trip and st:
                counts[r]["FN"] += 1
            else:
                counts[r]["TN"] += 1
    return counts


def print_score_table(decisions: list[CoordinatorDecision]) -> None:
    counts = compute_selectivity_score(decisions)
    print("\n--- Per-Relay Selectivity Score ---")
    print(f"{'Relay':<8} {'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4}  {'Sensitivity':>12}  {'Specificity':>12}")
    print("-" * 60)
    for r in RELAY_ORDER:
        c = counts[r]
        sens = c["TP"] / (c["TP"] + c["FN"]) if (c["TP"] + c["FN"]) > 0 else float("nan")
        spec = c["TN"] / (c["TN"] + c["FP"]) if (c["TN"] + c["FP"]) > 0 else float("nan")
        print(f"{r:<8} {c['TP']:>4} {c['FP']:>4} {c['FN']:>4} {c['TN']:>4}  "
              f"{sens:>12.3f}  {spec:>12.3f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 100)
    print("SAMBP System Integration Study — TR-05/2026")
    print(f"Network: Gen—Z_src—[Bus_A]—Z_line—[Bus_B]—Z_tr—[Bus_C]")
    print(f"Relays:  OC | 87B_A | 87L | 87B_B | 87T")
    print("=" * 100)
    print()

    decisions = run_study()

    print_selectivity_matrix(decisions)
    print_score_table(decisions)
    print_detail_table(decisions)

    # Final verdict
    all_ok = all(
        dec.is_selective(EXPECTED_TRIPS[dec.fault_loc])
        for dec in decisions
    )
    print("\n" + "=" * 100)
    if all_ok:
        print("RESULT: ALL SCENARIOS SELECTIVE — System integration study PASSED.")
    else:
        n_fail = sum(
            not dec.is_selective(EXPECTED_TRIPS[dec.fault_loc])
            for dec in decisions
        )
        print(f"RESULT: {n_fail} SCENARIOS FAILED selectivity check.")
    print("=" * 100)
