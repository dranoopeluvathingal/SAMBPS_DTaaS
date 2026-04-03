"""
run_hif_study.py
=================
SAMBP TR-11/2026 — High-Impedance Fault (HIF) Sensitivity Margin Study

Characterises the minimum detectable fault current for each relay zone
by scaling the fault current from nominal down to 5% in discrete steps.
For each scale factor the conventional relay and SAMBP Stage-2 trip
decisions are evaluated over N_TRIALS trials with ±5% amplitude jitter.

Scale factors:  α = [1.00, 0.70, 0.50, 0.30, 0.20, 0.15, 0.10, 0.07, 0.05]

For a relay zone with pickup I_op_min = 0.20 pu and nominal fault
current I_f_nom, the theoretical detection threshold is:
    α_thresh = I_op_min / I_f_nom   (without restraint current)

In practice the restraint bias from through-current raises this threshold.
The study quantifies the actual detection threshold empirically.

Metrics:
    TPR(α)  — fraction of N_TRIALS trials that correctly trip at scale α
    α_50    — scale factor at which TPR first drops below 0.50
    α_10    — scale factor at which TPR first drops below 0.10
    I_f_50  — corresponding fault current in pu (α_50 × I_f_nom)
"""

from __future__ import annotations

import sys, os
import numpy as np
from dataclasses import dataclass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))

from network.radial_network import (
    generate_network_snapshot, NetworkSnapshot
)
from coordinator.system_coordinator import run_system_coordination

N_TRIALS = 200
RNG_SEED  = 2026

ALPHA_LEVELS = [1.00, 0.70, 0.50, 0.30, 0.20, 0.15, 0.10, 0.07, 0.05]

# Scenarios: (fault_loc, fault_type, relay_id)
SCENARIOS = [
    ("bus_A",           "3ph", "87B_A"),
    ("bus_A",           "ag",  "87B_A"),
    ("line_mid",        "3ph", "87L"),
    ("line_mid",        "ag",  "87L"),
    ("bus_B",           "3ph", "87B_B"),
    ("bus_B",           "ag",  "87B_B"),
    ("transformer_hv",  "3ph", "87T"),
    ("transformer_hv",  "ag",  "87T"),
    ("bus_C_load",      "3ph", "OC"),
    ("bus_C_load",      "ag",  "OC"),
]


def scale_snapshot(snap: NetworkSnapshot, alpha: float,
                   jitter: float = 0.0) -> NetworkSnapshot:
    """Scale all currents by alpha × (1 + jitter)."""
    s = alpha * (1.0 + jitter)
    return NetworkSnapshot(
        fault_loc     = snap.fault_loc,
        fault_type    = snap.fault_type,
        time_s        = snap.time_s,
        i_oc_pu       = snap.i_oc_pu       * s,
        i_B_A_feeders = [f * s for f in snap.i_B_A_feeders],
        i_L_near_pu   = snap.i_L_near_pu   * s,
        i_L_far_pu    = snap.i_L_far_pu    * s,
        i_B_B_feeders = [f * s for f in snap.i_B_B_feeders],
        i_T_H_pu      = snap.i_T_H_pu      * s,
        i_T_X_pu      = snap.i_T_X_pu      * s,
        I_fault_pu    = snap.I_fault_pu    * s,
    )


@dataclass
class HIFResult:
    fault_loc:   str
    fault_type:  str
    relay_id:    str
    alpha:       float
    I_f_nom_pu:  float     # nominal fault current peak [pu]
    n_trials:    int
    conv_trips:  int
    sambp_trips: int

    @property
    def conv_tpr(self) -> float:
        return self.conv_trips / self.n_trials

    @property
    def sambp_tpr(self) -> float:
        return self.sambp_trips / self.n_trials

    @property
    def I_f_scaled(self) -> float:
        return self.alpha * self.I_f_nom_pu


def run_hif_sweep(fault_loc: str, fault_type: str, relay_id: str,
                  rng: np.random.Generator) -> list[HIFResult]:
    snap_nom = generate_network_snapshot(fault_loc, fault_type)
    I_f_nom  = float(snap_nom.I_fault_pu)

    results = []
    for alpha in ALPHA_LEVELS:
        conv_trips  = 0
        sambp_trips = 0

        for _ in range(N_TRIALS):
            jitter   = rng.uniform(-0.05, 0.05)
            snap_s   = scale_snapshot(snap_nom, alpha, jitter)
            dec      = run_system_coordination(snap_s)
            rr       = {r.relay_id: r for r in dec.relay_results}

            if relay_id not in rr:
                # OC relay result
                tripped_ids = [r.relay_id for r in dec.relay_results if r.final_trip]
                conv_tripped_ids = [r.relay_id for r in dec.relay_results if r.conv_trip]
                if relay_id == "OC":
                    # Check if OC is in tripped list
                    if "OC" in tripped_ids:
                        sambp_trips += 1
                    if "OC" in conv_tripped_ids:
                        conv_trips += 1
                continue

            r = rr[relay_id]
            if r.conv_trip:  conv_trips  += 1
            if r.final_trip: sambp_trips += 1

        results.append(HIFResult(
            fault_loc   = fault_loc,
            fault_type  = fault_type,
            relay_id    = relay_id,
            alpha       = alpha,
            I_f_nom_pu  = I_f_nom,
            n_trials    = N_TRIALS,
            conv_trips  = conv_trips,
            sambp_trips = sambp_trips,
        ))

    return results


def find_alpha_threshold(results: list[HIFResult], tpr_thresh: float,
                         method: str = "conv") -> float | None:
    """Return the largest alpha at which TPR drops below tpr_thresh."""
    attr = "conv_tpr" if method == "conv" else "sambp_tpr"
    for r in sorted(results, key=lambda x: x.alpha, reverse=True):
        if getattr(r, attr) < tpr_thresh:
            return r.alpha
    return None


def main():
    print("=" * 90)
    print("SAMBP HIF Sensitivity Margin Study — TR-11/2026")
    print(f"N_TRIALS = {N_TRIALS} per (scenario, alpha), seed={RNG_SEED}")
    print(f"Alpha levels: {ALPHA_LEVELS}")
    print("=" * 90)

    rng = np.random.default_rng(RNG_SEED)
    all_results: list[list[HIFResult]] = []

    for (fault_loc, fault_type, relay_id) in SCENARIOS:
        key = f"{fault_loc}/{fault_type}/{relay_id}"
        print(f"  Sweeping {key} ...", end="", flush=True)
        res = run_hif_sweep(fault_loc, fault_type, relay_id, rng)
        all_results.append(res)
        print(" done")

    # ---- Per-scenario table --------------------------------------------------
    print()
    hdr = f"{'Scenario':<35}  {'α':>5}  {'I_f(pu)':>7}  "
    hdr += f"{'Conv TPR':>9}  {'SAMBP TPR':>10}"
    print(hdr)
    print("-" * 80)

    for res_list in all_results:
        r0    = res_list[0]
        label = f"{r0.fault_loc}/{r0.fault_type}/{r0.relay_id}"
        for r in res_list:
            flag = ""
            if r.conv_tpr < 0.5 or r.sambp_tpr < 0.5:
                flag = " ←"
            if r.conv_tpr == 0.0 and r.sambp_tpr == 0.0:
                flag = " [blind]"
            print(f"  {label:<33}  {r.alpha:5.2f}  {r.I_f_scaled:7.3f}  "
                  f"{r.conv_tpr:9.3f}  {r.sambp_tpr:10.3f}{flag}")
        print()

    # ---- Summary: detection margins -----------------------------------------
    print()
    print(f"{'Scenario':<35}  {'I_f_nom':>7}  {'α50_conv':>9}  "
          f"{'α50_sambp':>10}  {'I50_conv':>9}  {'I50_sambp':>10}")
    print("-" * 90)

    for res_list in all_results:
        r0    = res_list[0]
        label = f"{r0.fault_loc}/{r0.fault_type}/{r0.relay_id}"
        a50c  = find_alpha_threshold(res_list, 0.50, "conv")
        a50s  = find_alpha_threshold(res_list, 0.50, "sambp")
        I50c  = f"{a50c * r0.I_f_nom_pu:.3f}" if a50c is not None else "---"
        I50s  = f"{a50s * r0.I_f_nom_pu:.3f}" if a50s is not None else "---"
        a50c_ = f"{a50c:.2f}"  if a50c is not None else "---"
        a50s_ = f"{a50s:.2f}"  if a50s is not None else "---"
        print(f"  {label:<33}  {r0.I_f_nom_pu:7.3f}  {a50c_:>9}  "
              f"{a50s_:>10}  {I50c:>9}  {I50s:>10}")

    print()
    print("=" * 90)
    print("RESULT: HIF Sensitivity Margin Study COMPLETE.")
    print("=" * 90)


if __name__ == "__main__":
    main()
