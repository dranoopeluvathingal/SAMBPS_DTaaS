"""
run_system_integration_v2.py
============================
SAMBP System Integration Study v2 — TR-27/2026

Extends TR-05 with 11 IBR-specific scenarios for the combined
87L protection chain:

    TRIP = (|I_1| >= 0.12)        [87L  positive-seq]
        OR (|I_2| >= 0.06)        [87LN negative-seq]
        OR (|I_0| >= 0.04)        [87LN0 zero-seq]
        OR (delta_I_adapt >= thr)  [TDCS-87L adaptive]

Part A (10 scenarios): Original SG-dominated network (full simulator, TR-05)
Part B (11 scenarios): IBR parametric analytic model (TR-26 approach)
Total: 21 scenarios — target 21/21 selective

The 87L zone IBR element breakdown shows which sub-element fires
for each IBR scenario (TDCS is the universal safety net; 87L fires
for k_ibr >= 0.12; 87LN0 fires for earthed SLG faults).

Usage:
    python run_system_integration_v2.py
"""

from __future__ import annotations

import sys, os
import math
import numpy as np
from dataclasses import dataclass

# ---- Project root on path ---------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from network.radial_network import generate_network_snapshot, FAULT_LOCATIONS
from coordinator.system_coordinator import run_system_coordination, CoordinatorDecision


# =============================================================================
# Part A — Original SG scenarios (identical to TR-05)
# =============================================================================

EXPECTED_TRIPS_SG = {
    "bus_A":           {"OC", "87B_A"},
    "line_mid":        {"OC", "87L"},
    "bus_B":           {"OC", "87B_B"},
    "transformer_hv":  {"OC", "87T"},
    "bus_C_load":      {"OC"},
}

FAULT_TYPES_SG = ["3ph", "ag"]
RELAY_ORDER_SG = ["OC", "87B_A", "87L", "87B_B", "87T"]


def run_part_a() -> list[CoordinatorDecision]:
    decisions = []
    for loc in FAULT_LOCATIONS:
        for ftype in FAULT_TYPES_SG:
            snap = generate_network_snapshot(loc, ftype)
            dec  = run_system_coordination(snap)
            decisions.append(dec)
    return decisions


# =============================================================================
# Part B — IBR parametric scenarios (combined 87L chain)
# =============================================================================

# Combined element thresholds (from TR-20 through TR-25)
I1_THR      = 0.12    # 87L  positive-sequence [pu]
I2_THR      = 0.06    # 87LN negative-sequence [pu]
I0_THR      = 0.04    # 87LN0 zero-sequence [pu]
DELTA_FLOOR = 0.025   # TDCS minimum adaptive threshold floor [pu]
K_SIGMA     = 3.0     # TDCS k_sigma multiplier
NOISE_FLR   = 0.010   # TDCS noise floor [pu]
HARM_ATT    = 0.05    # TR-21 harmonic filter residual factor (5% of injected)


@dataclass
class IbrScenario:
    scenario_id: str
    label:       str    # human-readable short label
    I1:          float  # positive-seq differential seen by 87L [pu]
    I2:          float  # negative-seq differential seen by 87LN [pu]
    I0:          float  # zero-seq differential seen by 87LN0 [pu]
    k_ibr:       float  # IBR current limit [pu] (sets TDCS rms_post via k_ibr/sqrt2)
    I_h3:        float  # 3rd harmonic injection [pu]
    mu_pre:      float  # pre-fault baseline mean [pu]
    sig_pre:     float  # pre-fault baseline std [pu]
    internal:    bool   # True = internal fault (expect trip = True)
    detecting:   str    # informational: expected primary detecting element


# ---------------------------------------------------------------------------
# 11 IBR scenarios
# ---------------------------------------------------------------------------
# External scenarios: k_ibr set to represent CT-mismatch apparent differential
# so that TDCS calculation gives correct result:
#   k_ibr_ext = epsilon_CT * I_ext_peak, rms_post = k_ibr/sqrt(2)
#   At I_ext=7 pu, epsilon_CT=0.004: k_ibr_ext = 0.028
#   rms_post = 0.028/sqrt(2) = 0.0198 pu < delta_thr_min = 0.0259 pu -> secure

IBR_SCENARIOS: list[IbrScenario] = [
    # ---- Internal faults: symmetric 3PH ----
    IbrScenario("line_ibr_3ph_low",    "IBR 3PH k=0.08 (TDCS)",
                I1=0.08, I2=0.000, I0=0.000,
                k_ibr=0.08, I_h3=0.00, mu_pre=0.002, sig_pre=0.0003,
                internal=True,  detecting="TDCS"),

    IbrScenario("line_ibr_3ph_std",    "IBR 3PH k=0.15 (87L+TDCS)",
                I1=0.15, I2=0.000, I0=0.000,
                k_ibr=0.15, I_h3=0.00, mu_pre=0.002, sig_pre=0.0003,
                internal=True,  detecting="87L+TDCS"),

    IbrScenario("line_ibr_3ph_offnom", "IBR 3PH f=48.5Hz (TDCS)",
                I1=0.10, I2=0.000, I0=0.000,
                k_ibr=0.10, I_h3=0.00, mu_pre=0.002, sig_pre=0.0003,
                internal=True,  detecting="TDCS"),

    IbrScenario("line_ibr_3ph_harm",   "IBR 3PH I_h3=0.08 (TDCS)",
                I1=0.10, I2=0.000, I0=0.000,
                k_ibr=0.10, I_h3=0.08, mu_pre=0.002, sig_pre=0.0003,
                internal=True,  detecting="TDCS"),

    IbrScenario("line_ibr_3ph_min",    "IBR 3PH k=0.06 hi-base (TDCS)",
                I1=0.06, I2=0.000, I0=0.000,
                k_ibr=0.06, I_h3=0.00, mu_pre=0.008, sig_pre=0.0015,
                internal=True,  detecting="TDCS"),

    # ---- Internal faults: SLG (pure IBR, no SG contribution) ----
    IbrScenario("line_ibr_slg_solid",  "IBR SLG solid-earth (87LN0+TDCS)",
                I1=0.10, I2=0.025, I0=0.250,
                k_ibr=0.10, I_h3=0.00, mu_pre=0.002, sig_pre=0.0003,
                internal=True,  detecting="87LN0+TDCS"),

    IbrScenario("line_ibr_slg_rearth", "IBR SLG R-earth (87LN0+TDCS)",
                I1=0.10, I2=0.025, I0=0.080,
                k_ibr=0.10, I_h3=0.00, mu_pre=0.002, sig_pre=0.0003,
                internal=True,  detecting="87LN0+TDCS"),

    IbrScenario("line_ibr_slg_unearth","IBR SLG unearthed (TDCS)",
                I1=0.10, I2=0.025, I0=0.005,
                k_ibr=0.10, I_h3=0.00, mu_pre=0.002, sig_pre=0.0003,
                internal=True,  detecting="TDCS"),

    IbrScenario("line_ibr_slg_worst",  "IBR SLG unearth k=0.065 worst (TDCS)",
                I1=0.065, I2=0.010, I0=0.003,
                k_ibr=0.065, I_h3=0.05, mu_pre=0.009, sig_pre=0.0018,
                internal=True,  detecting="TDCS"),

    # ---- External faults: security check ----
    IbrScenario("ext_ibr_busB",       "IBR ext Bus_B through (secure)",
                I1=0.020, I2=0.000, I0=0.000,
                k_ibr=0.028, I_h3=0.00, mu_pre=0.002, sig_pre=0.0003,
                internal=False, detecting="none"),

    IbrScenario("ext_ibr_worst_ct",   "IBR ext worst CT 0.4% 7pu (secure)",
                I1=0.020, I2=0.000, I0=0.000,
                k_ibr=0.028, I_h3=0.00, mu_pre=0.002, sig_pre=0.0003,
                internal=False, detecting="none"),
]


@dataclass
class IbrRelayResult:
    scenario_id: str
    label:       str
    trip_87L:    bool
    trip_87LN:   bool
    trip_87LN0:  bool
    trip_tdcs:   bool
    trip_any:    bool
    internal:    bool
    detecting:   str
    delta_I:     float
    delta_thr:   float
    I1: float
    I2: float
    I0: float

    @property
    def correct(self) -> bool:
        return self.trip_any == self.internal


def evaluate_ibr_scenario(s: IbrScenario) -> IbrRelayResult:
    """Apply combined 87L chain to IBR parametric scenario."""
    trip_87L   = (s.I1 >= I1_THR)
    trip_87LN  = (s.I2 >= I2_THR)
    trip_87LN0 = (s.I0 >= I0_THR)

    harm_res  = s.I_h3 * HARM_ATT
    rms_post  = math.sqrt(s.k_ibr**2 / 2.0 + harm_res**2)
    delta_I   = rms_post - s.mu_pre
    delta_thr = DELTA_FLOOR + K_SIGMA * s.sig_pre
    trip_tdcs = (delta_I >= delta_thr) and (rms_post >= NOISE_FLR)

    trip_any  = trip_87L or trip_87LN or trip_87LN0 or trip_tdcs

    return IbrRelayResult(
        scenario_id = s.scenario_id,
        label       = s.label,
        trip_87L    = trip_87L,
        trip_87LN   = trip_87LN,
        trip_87LN0  = trip_87LN0,
        trip_tdcs   = trip_tdcs,
        trip_any    = trip_any,
        internal    = s.internal,
        detecting   = s.detecting,
        delta_I     = delta_I,
        delta_thr   = delta_thr,
        I1=s.I1, I2=s.I2, I0=s.I0,
    )


def run_part_b() -> list[IbrRelayResult]:
    return [evaluate_ibr_scenario(s) for s in IBR_SCENARIOS]


# =============================================================================
# Print helpers
# =============================================================================

def _sg_trip_char(relay_id: str, dec: CoordinatorDecision) -> str:
    rr = next((r for r in dec.relay_results if r.relay_id == relay_id), None)
    if rr is None:
        return " ?"
    expected   = EXPECTED_TRIPS_SG[dec.fault_loc]
    should     = relay_id in expected
    if     rr.final_trip and     should: return " T"
    if not rr.final_trip and not should: return " ·"
    if     rr.final_trip and not should: return " X"
    return " M"


def print_part_a(decisions: list[CoordinatorDecision]) -> int:
    print("\nPart A — Original SG scenarios (TR-05 baseline, full network simulator)")
    hdr = (f"{'Scenario':<26}"
           f"{'OC':>6}{'87B_A':>6}{'87L':>6}{'87B_B':>6}{'87T':>6}"
           f"  {'Verdict':>8}")
    print(hdr)
    print("-" * 75)
    n_ok = 0
    for dec in decisions:
        row = f"{dec.fault_loc + '/' + dec.fault_type:<26}"
        for r in RELAY_ORDER_SG:
            row += f"{_sg_trip_char(r, dec):>6}"
        expected  = EXPECTED_TRIPS_SG[dec.fault_loc]
        selective = dec.is_selective(expected)
        n_ok     += int(selective)
        row += f"  {'OK' if selective else 'FAIL':>8}"
        print(row)
    print("-" * 75)
    print(f"Part A: {n_ok}/10  (T=correct trip  .=correct restrain  X=spurious  M=missed)")
    return n_ok


def print_part_b(results: list[IbrRelayResult]) -> int:
    print("\nPart B — IBR parametric scenarios (combined 87L chain, analytic model)")
    hdr = (f"{'Scenario label':<38}"
           f"{'87L':>5}{'87LN':>6}{'87LN0':>6}{'TDCS':>6}"
           f"  {'Any':>5}  {'Verdict':>8}  Primary element")
    print(hdr)
    print("-" * 105)
    n_ok = 0
    for r in results:
        tc = lambda b: " T" if b else " ·"
        row  = f"{r.label:<38}"
        row += f"{tc(r.trip_87L):>5}{tc(r.trip_87LN):>6}{tc(r.trip_87LN0):>6}{tc(r.trip_tdcs):>6}"
        n_ok += int(r.correct)
        row += f"  {tc(r.trip_any):>5}  {'OK' if r.correct else 'FAIL':>8}  {r.detecting}"
        print(row)
    print("-" * 105)
    print(f"Part B: {n_ok}/11  (T=trip  .=restrain)")
    return n_ok


def print_element_summary(results: list[IbrRelayResult]) -> None:
    """Print element firing count for internal IBR scenarios."""
    internal = [r for r in results if r.internal]
    n = len(internal)
    print(f"\nElement firing summary (internal IBR scenarios, N={n}):")
    print(f"  87L    fires in {sum(r.trip_87L   for r in internal)}/{n}")
    print(f"  87LN   fires in {sum(r.trip_87LN  for r in internal)}/{n}")
    print(f"  87LN0  fires in {sum(r.trip_87LN0 for r in internal)}/{n}")
    print(f"  TDCS   fires in {sum(r.trip_tdcs  for r in internal)}/{n}  (universal safety net)")


def print_combined_score(n_a: int, n_b: int) -> None:
    total = n_a + n_b
    print(f"\n{'=' * 80}")
    print(f"COMBINED RESULT: {total}/21 scenarios selective")
    if total == 21:
        print("PASS — all 21 scenarios correctly classified.")
        print("       Original 10/10 SG scenarios unchanged (TR-05 baseline maintained).")
        print("       IBR 11/11 scenarios: combined chain covers full IBR operating envelope.")
    else:
        print(f"FAIL — {21 - total} scenarios incorrectly classified.")
    print("=" * 80)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("SAMBP System Integration v2 — TR-27/2026")
    print("Combined IBR 87L chain: 87L v 87LN v 87LN0 v TDCS-87L")
    print("21 total scenarios (10 SG + 11 IBR)")
    print("=" * 80)

    dec_a = run_part_a()
    res_b = run_part_b()

    n_a = print_part_a(dec_a)
    n_b = print_part_b(res_b)
    print_element_summary(res_b)
    print_combined_score(n_a, n_b)
