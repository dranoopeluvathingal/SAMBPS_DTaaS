"""
run_busbar_transfer_study.py
=============================
SAMBP TR-14/2026 — Dynamic Busbar Transfer selectivity validation.

Runs the full 5-topology × 5-fault-location × 2-fault-type = 50 scenario
selectivity matrix, applying the SAMBP 87B pipeline (conventional relay +
Stage-2 confidence gate) to each zone in each scenario.

Topologies
----------
    T1_NORM  : Baseline — Gen + Line on BB1, Tr on BB2 (TR-07 reference)
    T2_TIP   : Transfer-in-Progress — Gen has both DS closed, zones unchanged
    T3_POST  : Transfer complete — Gen zone reconfigured to BB2
    T4_SPLIT : Bus-split — BC breaker open, buses isolated
    T5_LAG   : GOOSE lag — Gen physically on BB2 but engine sees NORM mapping;
               evaluated with BOTH the correct (post-GOOSE) and stale zones

Trip logic (same as TR-07)
--------------------------
    BB1 trip  : Zone 1 AND Check Zone assert
    BB2 trip  : Zone 2 AND Check Zone assert
    BC fault  : Check Zone only (Z1=0, Z2=0)
    No trip   : none of the above

GOOSE lag analysis (T5_LAG)
----------------------------
For each T5_LAG scenario the result is evaluated twice:
    stale    — engine uses NORM zone config (wrong, pre-GOOSE)
    updated  — engine uses POST zone config (correct, post-GOOSE)
The "lag consequence" column shows whether stale→wrong trip decision.

Outputs
-------
    outputs/tr14_selectivity.csv
    outputs/tr14_goose_lag.csv
    outputs/tr14_summary.txt
"""

from __future__ import annotations

import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from dataclasses import dataclass
from typing import Optional

from models.transfer_network import (
    generate_transfer_snapshot, TOPOLOGIES, FAULT_LOCATIONS, FAULT_TYPES,
    EXPECTED, TransferSnapshot,
)

# ---- Load sambp_bus_diff pipeline (namespace isolation same as TR-07) ----
import importlib.util as _ilu

def _load(subpkg, modname):
    _BUS = os.path.join(os.path.dirname(__file__), "..", "sambp_bus_diff")
    for key in [k for k in sys.modules if k == "models" or k.startswith("models.")]:
        del sys.modules[key]
    if _BUS not in sys.path:
        sys.path.insert(0, _BUS)
    path = os.path.join(_BUS, subpkg, modname + ".py")
    qn   = f"_dbus.{subpkg}.{modname}"
    spec = _ilu.spec_from_file_location(qn, path)
    mod  = _ilu.module_from_spec(spec)
    sys.modules[qn] = mod
    spec.loader.exec_module(mod)
    for key in [k for k in sys.modules if k == "models" or k.startswith("models.")]:
        sys.modules[f"_dbus.{key}"] = sys.modules.pop(key)
    return mod

_b_base = _load("models",             "bus_diff_baseline")
_b_est  = _load("inverse_estimation", "bus_inverse_estimator")
_b_gate = _load("adaptation",         "bus_confidence_gate")

BusDiffRelayConfig           = _b_base.BusDiffRelayConfig
run_87B_relay                = _b_base.run_87B_relay
estimate_bus_zone_parameters = _b_est.estimate_bus_zone_parameters
BusGateConfig                = _b_gate.BusGateConfig
BusGateState                 = _b_gate.BusGateState
evaluate_87B_confidence_gate = _b_gate.evaluate_87B_confidence_gate


# ---------------------------------------------------------------------------
# Per-zone result
# ---------------------------------------------------------------------------

@dataclass
class ZoneResult:
    zone:       str
    conv_trip:  bool
    final_trip: bool
    source:     str
    kappa_n:    float
    f_int:      float
    I_op_peak:  float


@dataclass
class TransferScenarioResult:
    topology:   str
    fault_loc:  str
    fault_type: str
    I_fault_pu: float
    z1:         ZoneResult
    z2:         ZoneResult
    ck:         ZoneResult
    bb1_trip:   bool
    bb2_trip:   bool
    bc_trip:    bool
    no_trip:    bool
    selective:  bool
    # T5_LAG only
    z1_stale:   Optional[ZoneResult] = None
    z2_stale:   Optional[ZoneResult] = None
    ck_stale:   Optional[ZoneResult] = None
    bb1_stale:  Optional[bool] = None
    bb2_stale:  Optional[bool] = None
    bc_stale:   Optional[bool] = None
    selective_stale: Optional[bool] = None


# ---------------------------------------------------------------------------
# Zone runner
# ---------------------------------------------------------------------------

def _run_zone(
    t: np.ndarray,
    feeders: list[np.ndarray],
    zone_label: str,
) -> ZoneResult:
    cfg      = BusDiffRelayConfig(n_feeders=len(feeders), I_bus_rated_A=1.0)
    gate_cfg = BusGateConfig(n_confirm=1)
    dec      = run_87B_relay(t, feeders, cfg)
    i_diff   = sum(feeders)[0]
    est      = estimate_bus_zone_parameters(t, i_diff, freq_hz=50.0)
    gs       = BusGateState()
    gate, _  = evaluate_87B_confidence_gate(
        est["state"],
        conventional_trip = dec.t_trip_s is not None,
        gate_cfg          = gate_cfg,
        gate_state        = gs,
    )
    return ZoneResult(
        zone       = zone_label,
        conv_trip  = dec.t_trip_s is not None,
        final_trip = gate.final_trip,
        source     = gate.source,
        kappa_n    = est["kappa_n"],
        f_int      = est["state"].f_int,
        I_op_peak  = float(dec.I_op.max()),
    )


def _trip_logic(z1: ZoneResult, z2: ZoneResult, ck: ZoneResult):
    bb1 = z1.final_trip and ck.final_trip
    bb2 = z2.final_trip and ck.final_trip
    bc  = (not z1.final_trip) and (not z2.final_trip) and ck.final_trip
    no  = not (bb1 or bb2 or bc)
    return bb1, bb2, bc, no


def _is_selective(topology, fault_loc, bb1, bb2, bc, no):
    exp = EXPECTED[topology][fault_loc]
    return (
        exp.get("bb1_trip", False) == bb1 and
        exp.get("bb2_trip", False) == bb2 and
        exp.get("bc_trip",  False) == bc  and
        exp.get("no_trip",  False) == no
    )


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def run_scenario(snap: TransferSnapshot) -> TransferScenarioResult:
    t = snap.time_s

    z1 = _run_zone(t, snap.i_Z1_feeders, "Z1")
    z2 = _run_zone(t, snap.i_Z2_feeders, "Z2")
    ck = _run_zone(t, snap.i_CK_feeders, "CK")
    bb1, bb2, bc, no = _trip_logic(z1, z2, ck)
    sel = _is_selective(snap.topology, snap.fault_loc, bb1, bb2, bc, no)

    res = TransferScenarioResult(
        topology   = snap.topology,
        fault_loc  = snap.fault_loc,
        fault_type = snap.fault_type,
        I_fault_pu = snap.I_fault_pu,
        z1=z1, z2=z2, ck=ck,
        bb1_trip=bb1, bb2_trip=bb2, bc_trip=bc, no_trip=no,
        selective=sel,
    )

    # T5_LAG: also evaluate with stale zone assignment
    if snap.topology == "T5_LAG" and snap.i_Z1_stale is not None:
        z1s = _run_zone(t, snap.i_Z1_stale, "Z1")
        z2s = _run_zone(t, snap.i_Z2_stale, "Z2")
        cks = _run_zone(t, snap.i_CK_stale, "CK")
        bb1s, bb2s, bcs, nos = _trip_logic(z1s, z2s, cks)
        # Expected for stale: NORM topology expectations
        sels = _is_selective("T1_NORM", snap.fault_loc, bb1s, bb2s, bcs, nos)
        res.z1_stale = z1s
        res.z2_stale = z2s
        res.ck_stale = cks
        res.bb1_stale = bb1s
        res.bb2_stale = bb2s
        res.bc_stale  = bcs
        res.selective_stale = sels

    return res


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def _tf(b): return "T" if b else "·"


def print_selectivity_table(results: list[TransferScenarioResult]) -> None:
    header = (f"{'Topology':<9} {'Fault loc':<16} {'Typ':<4} "
              f"{'Z1':>3} {'Z2':>3} {'CK':>3}  "
              f"{'BB1':>4} {'BB2':>4} {'BC':>3} {'Sel':>5}")
    print(header)
    print("-" * 70)
    n_ok = 0
    for r in results:
        if r.topology == "T5_LAG":
            continue   # printed separately
        mark = "OK" if r.selective else "FAIL"
        if r.selective:
            n_ok += 1
        print(f"{r.topology:<9} {r.fault_loc:<16} {r.fault_type:<4} "
              f"{_tf(r.z1.final_trip):>3} {_tf(r.z2.final_trip):>3} "
              f"{_tf(r.ck.final_trip):>3}  "
              f"{_tf(r.bb1_trip):>4} {_tf(r.bb2_trip):>4} "
              f"{_tf(r.bc_trip):>3} {mark:>5}")

    n_total = sum(1 for r in results if r.topology != "T5_LAG")
    print(f"\nT1–T4 selectivity: {n_ok}/{n_total}  "
          f"({'100%' if n_ok == n_total else f'{100*n_ok//n_total}%'})")


def print_lag_table(results: list[TransferScenarioResult]) -> None:
    lag_rows = [r for r in results if r.topology == "T5_LAG"]
    if not lag_rows:
        return
    print(f"\n{'Fault loc':<16} {'Typ':<4}  "
          f"{'Stale BB1':>9} {'Stale BB2':>9} {'Stale sel':>9}  "
          f"{'Corr BB1':>8} {'Corr BB2':>8} {'Corr sel':>8}")
    print("-" * 80)
    n_stale_ok = 0
    n_corr_ok  = 0
    for r in lag_rows:
        stale_sel = "OK" if r.selective_stale else "FAIL"
        corr_sel  = "OK" if r.selective else "FAIL"
        if r.selective_stale:
            n_stale_ok += 1
        if r.selective:
            n_corr_ok += 1
        print(f"{r.fault_loc:<16} {r.fault_type:<4}  "
              f"{_tf(r.bb1_stale):>9} {_tf(r.bb2_stale):>9} {stale_sel:>9}  "
              f"{_tf(r.bb1_trip):>8} {_tf(r.bb2_trip):>8} {corr_sel:>8}")
    n_lag = len(lag_rows)
    print(f"\nT5 stale sel: {n_stale_ok}/{n_lag}   "
          f"T5 corrected sel: {n_corr_ok}/{n_lag}")


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def save_csv(results: list[TransferScenarioResult], path: str) -> None:
    fields = ["topology","fault_loc","fault_type","I_fault_pu",
              "Z1_trip","Z2_trip","CK_trip","BB1_trip","BB2_trip",
              "BC_trip","no_trip","selective",
              "Z1_kn","Z1_fint","Z2_kn","Z2_fint","CK_kn","CK_fint"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({
                "topology":   r.topology,
                "fault_loc":  r.fault_loc,
                "fault_type": r.fault_type,
                "I_fault_pu": f"{r.I_fault_pu:.3f}",
                "Z1_trip":    int(r.z1.final_trip),
                "Z2_trip":    int(r.z2.final_trip),
                "CK_trip":    int(r.ck.final_trip),
                "BB1_trip":   int(r.bb1_trip),
                "BB2_trip":   int(r.bb2_trip),
                "BC_trip":    int(r.bc_trip),
                "no_trip":    int(r.no_trip),
                "selective":  int(r.selective),
                "Z1_kn":      f"{r.z1.kappa_n:.1f}",
                "Z1_fint":    f"{r.z1.f_int:.3f}",
                "Z2_kn":      f"{r.z2.kappa_n:.1f}",
                "Z2_fint":    f"{r.z2.f_int:.3f}",
                "CK_kn":      f"{r.ck.kappa_n:.1f}",
                "CK_fint":    f"{r.ck.f_int:.3f}",
            })


def save_lag_csv(results: list[TransferScenarioResult], path: str) -> None:
    fields = ["fault_loc","fault_type",
              "bb1_stale","bb2_stale","bc_stale","sel_stale",
              "bb1_corr","bb2_corr","bc_corr","sel_corr",
              "lag_consequence"]
    lag_rows = [r for r in results if r.topology == "T5_LAG"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in lag_rows:
            consequence = "wrong" if not r.selective_stale else "ok"
            w.writerow({
                "fault_loc":    r.fault_loc,
                "fault_type":   r.fault_type,
                "bb1_stale":    int(r.bb1_stale or False),
                "bb2_stale":    int(r.bb2_stale or False),
                "bc_stale":     int(r.bc_stale  or False),
                "sel_stale":    int(r.selective_stale or False),
                "bb1_corr":     int(r.bb1_trip),
                "bb2_corr":     int(r.bb2_trip),
                "bc_corr":      int(r.bc_trip),
                "sel_corr":     int(r.selective),
                "lag_consequence": consequence,
            })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs("outputs", exist_ok=True)

    results = []
    n_scen  = 0

    for topo in TOPOLOGIES:
        for loc in FAULT_LOCATIONS:
            for ft in FAULT_TYPES:
                snap = generate_transfer_snapshot(topo, loc, ft)
                res  = run_scenario(snap)
                results.append(res)
                n_scen += 1
                mark = "OK" if res.selective else "FAIL"
                print(f"  {topo}  {loc:<18} {ft}  "
                      f"BB1={_tf(res.bb1_trip)} BB2={_tf(res.bb2_trip)} "
                      f"BC={_tf(res.bc_trip)}  {mark}")

    print(f"\n=== SELECTIVITY TABLE (T1–T4) ===")
    print_selectivity_table(results)

    print(f"\n=== GOOSE LAG ANALYSIS (T5) ===")
    print_lag_table(results)

    save_csv(results, "outputs/tr14_selectivity.csv")
    save_lag_csv(results, "outputs/tr14_goose_lag.csv")

    # --- Summary text ---
    t1t4 = [r for r in results if r.topology != "T5_LAG"]
    n_ok  = sum(r.selective for r in t1t4)
    lag   = [r for r in results if r.topology == "T5_LAG"]
    n_lag_stale = sum(r.selective_stale for r in lag if r.selective_stale is not None)
    n_lag_corr  = sum(r.selective for r in lag)

    summary = [
        "SAMBP TR-14 Simulation Summary — Dynamic Busbar Transfer",
        "=" * 56,
        "",
        f"Total scenarios (T1–T4):    {len(t1t4)}  (4 topologies × 5 faults × 2 types)",
        f"Selective (T1–T4):          {n_ok}/{len(t1t4)}  (100%)" if n_ok == len(t1t4)
            else f"Selective (T1–T4):      {n_ok}/{len(t1t4)}",
        "",
        f"T5 GOOSE-lag scenarios:     {len(lag)}",
        f"  Stale zone (wrong config):{n_lag_stale}/{len(lag)} correct",
        f"  Updated zone (post-GOOSE):{n_lag_corr}/{len(lag)} correct",
        "",
        "Topology breakdown:",
    ]
    for topo in TOPOLOGIES:
        sub = [r for r in results if r.topology == topo]
        if topo == "T5_LAG":
            n_sub_ok = sum(r.selective for r in sub)
            n_stale  = sum(r.selective_stale for r in sub if r.selective_stale is not None)
            summary.append(f"  {topo}: updated {n_sub_ok}/{len(sub)}, "
                           f"stale {n_stale}/{len(sub)}")
        else:
            n_sub_ok = sum(r.selective for r in sub)
            summary.append(f"  {topo}: {n_sub_ok}/{len(sub)}")

    summary_text = "\n".join(summary)
    print("\n" + summary_text)
    with open("outputs/tr14_summary.txt", "w") as f:
        f.write(summary_text)

    print("\nSaved: outputs/tr14_selectivity.csv")
    print("Saved: outputs/tr14_goose_lag.csv")
    print("Saved: outputs/tr14_summary.txt")
