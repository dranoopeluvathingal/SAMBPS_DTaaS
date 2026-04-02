"""
run_double_bus_study.py
========================
SAMBP Double-Busbar 87B Protection Study — TR-07/2026

Runs three differential zones (Zone 1 / Zone 2 / Check Zone) on the
double-busbar network model for all fault locations and fault types.

Trip logic (IEC-compliant scheme):
    BB1 trip    : Zone 1 AND Check Zone both assert
    BB2 trip    : Zone 2 AND Check Zone both assert
    BC fault    : Check Zone only (both buses de-energised)

This demonstrates that the Check Zone is essential for BC-internal fault
protection, while Zone 1/Zone 2 provide bus-selective clearing for BB1
and BB2 faults.

SAMBP Stage-2 is applied to all three zones via the existing
sambp_bus_diff pipeline.
"""

from __future__ import annotations

import sys, os
import numpy as np
from dataclasses import dataclass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))

from models.double_bus_network import (
    generate_double_bus_snapshot, FAULT_LOCATIONS, DoubleBusSnapshot,
)

# ---- Load sambp_bus_diff pipeline via importlib (avoids models/ conflict) -
import importlib.util as _ilu

def _load(subpkg, modname):
    _BUS = os.path.join(_HERE, "..", "sambp_bus_diff")
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

_b_base = _load("models",              "bus_diff_baseline")
_b_est  = _load("inverse_estimation",  "bus_inverse_estimator")
_b_gate = _load("adaptation",          "bus_confidence_gate")

BusDiffRelayConfig           = _b_base.BusDiffRelayConfig
run_87B_relay                = _b_base.run_87B_relay
estimate_bus_zone_parameters = _b_est.estimate_bus_zone_parameters
BusGateConfig                = _b_gate.BusGateConfig
BusGateState                 = _b_gate.BusGateState
evaluate_87B_confidence_gate = _b_gate.evaluate_87B_confidence_gate

FAULT_TYPES = ["3ph", "ag"]


# ---------------------------------------------------------------------------
# Per-zone result
# ---------------------------------------------------------------------------

@dataclass
class ZoneResult:
    zone:         str           # "Z1" | "Z2" | "CK"
    conv_trip:    bool
    final_trip:   bool
    source:       str
    kappa_n:      float
    f_int:        float
    I_op_peak:    float


@dataclass
class DoubleBusScenarioResult:
    fault_loc:    str
    fault_type:   str
    I_fault_pu:   float
    z1:           ZoneResult
    z2:           ZoneResult
    ck:           ZoneResult

    # Combined bus-selective trip decisions
    bb1_trip:     bool    # Z1 AND CK
    bb2_trip:     bool    # Z2 AND CK
    bc_trip:      bool    # CK only (Z1=0, Z2=0)
    no_trip:      bool    # none of the above

    selective:    bool    # matches expected outcome


# ---------------------------------------------------------------------------
# Expected trip outcomes
# ---------------------------------------------------------------------------

EXPECTED = {
    "bb1":          {"bb1_trip": True},
    "bb2":          {"bb2_trip": True},
    "bc_internal":  {"bc_trip":  True},
    "line_external":{"no_trip":  True},
    "load_external":{"no_trip":  True},
}


def _run_zone(
    t: np.ndarray,
    feeders: list[np.ndarray],
    zone_label: str,
    cfg: BusDiffRelayConfig,
    gate_cfg: BusGateConfig,
) -> ZoneResult:
    dec    = run_87B_relay(t, feeders, cfg)
    i_diff = sum(feeders)[0]             # phase A differential
    est    = estimate_bus_zone_parameters(t, i_diff, freq_hz=50.0)
    gs     = BusGateState()
    gate, _= evaluate_87B_confidence_gate(
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


def run_scenario(snap: DoubleBusSnapshot) -> DoubleBusScenarioResult:
    t = snap.time_s
    n_feeders_z1 = len(snap.i_Z1_feeders)
    n_feeders_z2 = len(snap.i_Z2_feeders)
    n_feeders_ck = len(snap.i_CK_feeders)

    cfg_Z1 = BusDiffRelayConfig(n_feeders=n_feeders_z1, I_bus_rated_A=1.0)
    cfg_Z2 = BusDiffRelayConfig(n_feeders=n_feeders_z2, I_bus_rated_A=1.0)
    cfg_CK = BusDiffRelayConfig(n_feeders=n_feeders_ck, I_bus_rated_A=1.0)
    gate_cfg = BusGateConfig(n_confirm=1)

    z1 = _run_zone(t, snap.i_Z1_feeders, "Z1", cfg_Z1, gate_cfg)
    z2 = _run_zone(t, snap.i_Z2_feeders, "Z2", cfg_Z2, gate_cfg)
    ck = _run_zone(t, snap.i_CK_feeders, "CK", cfg_CK, gate_cfg)

    bb1_trip = z1.final_trip and ck.final_trip
    bb2_trip = z2.final_trip and ck.final_trip
    bc_trip  = (not z1.final_trip and not z2.final_trip and ck.final_trip)
    no_trip  = not (bb1_trip or bb2_trip or bc_trip)

    exp      = EXPECTED.get(snap.fault_loc, {})
    selective = (
        exp.get("bb1_trip", False) == bb1_trip and
        exp.get("bb2_trip", False) == bb2_trip and
        exp.get("bc_trip",  False) == bc_trip  and
        exp.get("no_trip",  False) == no_trip
    )

    return DoubleBusScenarioResult(
        fault_loc  = snap.fault_loc,
        fault_type = snap.fault_type,
        I_fault_pu = snap.I_fault_pu,
        z1 = z1, z2 = z2, ck = ck,
        bb1_trip = bb1_trip,
        bb2_trip = bb2_trip,
        bc_trip  = bc_trip,
        no_trip  = no_trip,
        selective = selective,
    )


# ---------------------------------------------------------------------------
# Print tables
# ---------------------------------------------------------------------------

def print_selectivity_table(results: list[DoubleBusScenarioResult]) -> None:
    print(f"\n{'Scenario':<22}  {'Z1':>5}  {'Z2':>5}  {'CK':>5}  "
          f"{'BB1':>5}  {'BB2':>5}  {'BC':>5}  {'Selective':>10}")
    print("-" * 80)
    n_ok = 0
    for r in results:
        def tf(b): return "T" if b else "·"
        sel = "OK" if r.selective else "FAIL"
        if r.selective:
            n_ok += 1
        print(f"{r.fault_loc+'/'+r.fault_type:<22}  "
              f"{tf(r.z1.final_trip):>5}  {tf(r.z2.final_trip):>5}  "
              f"{tf(r.ck.final_trip):>5}  "
              f"{tf(r.bb1_trip):>5}  {tf(r.bb2_trip):>5}  "
              f"{tf(r.bc_trip):>5}  {sel:>10}")
    print("-" * 80)
    print(f"Selective: {n_ok}/{len(results)}")


def print_sambp_table(results: list[DoubleBusScenarioResult]) -> None:
    print(f"\n{'Scenario':<22}  {'Zone':<4}  {'Trip':<5}  "
          f"{'Source':<16}  {'κ_n':>6}  {'f_int':>6}  {'I_op':>6}")
    print("-" * 78)
    for r in results:
        for z in [r.z1, r.z2, r.ck]:
            kn = f"{z.kappa_n:.1f}" if np.isfinite(z.kappa_n) else "n/a"
            fi = f"{z.f_int:.3f}"   if np.isfinite(z.f_int)   else "n/a"
            print(f"{r.fault_loc+'/'+r.fault_type:<22}  {z.zone:<4}  "
                  f"{str(z.final_trip):<5}  {z.source:<16}  "
                  f"{kn:>6}  {fi:>6}  {z.I_op_peak:>6.2f}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 80)
    print("SAMBP Double-Busbar 87B Study — TR-07/2026")
    print("Zones: Z1 (BB1) · Z2 (BB2) · CK (Check/Overall)")
    print("Trip logic: BB1=Z1∧CK · BB2=Z2∧CK · BC=CK∧¬Z1∧¬Z2")
    print("=" * 80)

    results = []
    for loc in FAULT_LOCATIONS:
        for ftype in FAULT_TYPES:
            snap = generate_double_bus_snapshot(loc, ftype)
            results.append(run_scenario(snap))

    print_selectivity_table(results)
    print_sambp_table(results)

    n_ok  = sum(r.selective for r in results)
    total = len(results)
    print("=" * 80)
    if n_ok == total:
        print(f"RESULT: ALL {total} SCENARIOS SELECTIVE — Study PASSED.")
    else:
        print(f"RESULT: {n_ok}/{total} selective — {total-n_ok} FAILED.")
    print("=" * 80)
