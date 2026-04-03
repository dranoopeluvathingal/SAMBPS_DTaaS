"""
transfer_network.py
====================
Extended double-busbar network model for SAMBP TR-14: Dynamic Busbar Transfer.

Five topology variants for the selectivity matrix:

    T1_NORM   : Gen + Line on BB1;  Tr on BB2;  BC closed (TR-07 baseline).
    T2_TIP    : Gen transferring BB1→BB2, both DS closed (50/50 current split).
    T3_POST   : Transfer complete — Gen moved to BB2; Line on BB1; BC closed.
    T4_SPLIT  : BC breaker open; Gen + Line on BB1; Tr on BB2 (isolated buses).
    T5_LAG    : Physical POST topology (Gen on BB2) but zone engine still uses
                NORM mapping due to 5 ms GOOSE lag.  Snapshot carries both
                correct (post-GOOSE) and stale (pre-GOOSE) zone arrays.

Network constants (100 MVA / 33 kV base, same as double_bus_network.py):
    Z_SRC = j0.10,  Z_BC = j0.01,  Z_LINE = j0.05,  Z_TR = j0.08
"""

from __future__ import annotations

import sys, os
import numpy as np
from dataclasses import dataclass
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from double_bus_network import (
    FREQ, FS, Z_SRC, Z_BC, Z_LINE, Z_TR, V_PRE,
    FAULT_LOCATIONS,
)

TOPOLOGIES  = ["T1_NORM", "T2_TIP", "T3_POST", "T4_SPLIT", "T5_LAG"]
FAULT_TYPES = ["3ph", "ag"]
AG_FACTOR   = 0.6


# ---------------------------------------------------------------------------
# Extended snapshot
# ---------------------------------------------------------------------------

@dataclass
class TransferSnapshot:
    topology:    str
    fault_loc:   str
    fault_type:  str
    I_fault_pu:  float
    time_s:      np.ndarray

    i_Z1_feeders: list[np.ndarray]  # each (3, T)
    i_Z2_feeders: list[np.ndarray]
    i_CK_feeders: list[np.ndarray]

    # T5_LAG only: stale zone assignment (wrong mapping, pre-GOOSE)
    i_Z1_stale:  Optional[list[np.ndarray]] = None
    i_Z2_stale:  Optional[list[np.ndarray]] = None
    i_CK_stale:  Optional[list[np.ndarray]] = None


# ---------------------------------------------------------------------------
# Waveform helpers
# ---------------------------------------------------------------------------

def _wave(
    t: np.ndarray,
    I_peak: float,
    phi_k: float = 0.0,
    dc: float = 0.8,
    tau: float = 0.05,
    fault_time_s: float = 0.02,
) -> np.ndarray:
    """DC-offset fault waveform (3, N).  I_peak may be negative (sign flip)."""
    N    = len(t)
    ph3  = [0.0, -2*np.pi/3, 2*np.pi/3]
    mask = t >= fault_time_s
    dt   = t - fault_time_s
    w    = np.zeros((3, N))
    for k, p in enumerate(ph3):
        w[k, mask] = I_peak * (
            np.sin(2*np.pi*FREQ*dt[mask] + p + phi_k)
            + dc * np.exp(-dt[mask] / tau)
        )
    return w


def _zeros(t: np.ndarray) -> np.ndarray:
    return np.zeros((3, len(t)))


# ---------------------------------------------------------------------------
# T1_NORM topology waveforms (identical to double_bus_network.py)
# Gen + Line on BB1;  Tr on BB2;  BC closed.
# ---------------------------------------------------------------------------

def _gen_T1_NORM(fault_loc, fault_type, t, ft, af):
    if fault_loc == "bb1":
        I = abs(V_PRE / Z_SRC) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_zeros(t),
                    i_BC_Z1=_zeros(t), i_BC_Z2=_zeros(t), i_Tr=_zeros(t),
                    I_f=I)
    elif fault_loc == "bb2":
        I = abs(V_PRE / (Z_SRC + Z_BC)) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_zeros(t),
                    i_BC_Z1=_wave(t,-I,ft=ft), i_BC_Z2=_wave(t,I,ft=ft),
                    i_Tr=_zeros(t), I_f=I)
    elif fault_loc == "bc_internal":
        I = abs(V_PRE / (Z_SRC + Z_BC/2)) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_zeros(t),
                    i_BC_Z1=_wave(t,-I,ft=ft), i_BC_Z2=_zeros(t),
                    i_Tr=_zeros(t), I_f=I)
    elif fault_loc == "line_external":
        I = abs(V_PRE / (Z_SRC + Z_LINE)) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_wave(t,-I,ft=ft),
                    i_BC_Z1=_zeros(t), i_BC_Z2=_zeros(t),
                    i_Tr=_zeros(t), I_f=I)
    elif fault_loc == "load_external":
        I = abs(V_PRE / (Z_SRC + Z_BC + Z_TR)) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_zeros(t),
                    i_BC_Z1=_wave(t,-I,ft=ft), i_BC_Z2=_wave(t,I,ft=ft),
                    i_Tr=_wave(t,-I,ft=ft), I_f=I)


def _zones_T1(d):
    z1 = [d["i_Gen"], d["i_Line"], d["i_BC_Z1"]]
    z2 = [d["i_BC_Z2"], d["i_Tr"]]
    ck = [d["i_Gen"], d["i_Line"], d["i_Tr"]]
    return z1, z2, ck


# Convenience alias for _wave with keyword ft
def _wave(t, I_peak, phi_k=0.0, dc=0.8, tau=0.05, ft=0.02):  # noqa: redefinition
    N    = len(t)
    ph3  = [0.0, -2*np.pi/3, 2*np.pi/3]
    mask = t >= ft
    dt   = t - ft
    w    = np.zeros((3, N))
    for k, p in enumerate(ph3):
        w[k, mask] = I_peak * (
            np.sin(2*np.pi*FREQ*dt[mask] + p + phi_k)
            + dc * np.exp(-dt[mask] / tau)
        )
    return w


# ---------------------------------------------------------------------------
# T2_TIP: Gen in make-before-break transfer (both DS closed, 50/50 split)
# ---------------------------------------------------------------------------

def _gen_T2_TIP(fault_loc, fault_type, t, ft, af, split=0.5):
    # Network is same as T1_NORM (Gen still primarily on BB1 during TIP)
    # but Gen CT delivers split fraction to each zone
    d = _gen_T1_NORM(fault_loc, fault_type, t, ft, af)
    I_G = d["i_Gen"]   # full Gen waveform
    d["i_Gen_Z1"] = I_G * split           # fraction to Zone 1
    d["i_Gen_Z2"] = I_G * (1.0 - split)  # fraction to Zone 2
    return d


def _zones_T2(d):
    # Conservative TIP rule: zone mapping DOES NOT CHANGE until DS_OPEN is received.
    # Gen CT remains in Zone 1 throughout the TIP window.  The zone will only
    # be reconfigured once the GOOSE DS_OPEN message is processed (→ T3_POST).
    # This prevents false differentials on external faults during TIP.
    return _zones_T1(d)


# ---------------------------------------------------------------------------
# T3_POST: Gen moved to BB2 (DS1 open, DS2 closed)
# Gen + Tr on BB2;  Line on BB1;  BC closed.
# ---------------------------------------------------------------------------

def _gen_T3_POST(fault_loc, fault_type, t, ft, af):
    if fault_loc == "bb1":
        # Gen(BB2) → BC → BB1 → fault
        I = abs(V_PRE / (Z_SRC + Z_BC)) * af
        # Gen current: exits BB2 as source feeding the fault; in Z2 context
        # it enters BB2 from the source = positive in Z2.
        # BC current enters BB1 = positive in Z1.
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_zeros(t),
                    i_BC_Z1=_wave(t,I,ft=ft),    # enters BB1 through BC
                    i_BC_Z2=_wave(t,-I,ft=ft),   # exits BB2 through BC
                    i_Tr=_zeros(t), I_f=I)
    elif fault_loc == "bb2":
        # Gen directly feeds BB2 fault; BC carries nothing
        I = abs(V_PRE / Z_SRC) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_zeros(t),
                    i_BC_Z1=_zeros(t), i_BC_Z2=_zeros(t),
                    i_Tr=_zeros(t), I_f=I)
    elif fault_loc == "bc_internal":
        # Gen(BB2) → BB2-side CT → fault inside BC (BB1-side CT sees nothing)
        I = abs(V_PRE / (Z_SRC + Z_BC/2)) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_zeros(t),
                    i_BC_Z1=_zeros(t),          # BB1-side CT: nothing
                    i_BC_Z2=_wave(t,-I,ft=ft),  # BB2-side CT: I_f exits BB2
                    i_Tr=_zeros(t), I_f=I)
    elif fault_loc == "line_external":
        # Gen(BB2) → BC → BB1 → Line → fault external
        I = abs(V_PRE / (Z_SRC + Z_BC + Z_LINE)) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_wave(t,-I,ft=ft),
                    i_BC_Z1=_wave(t,I,ft=ft),   # enters BB1 via BC
                    i_BC_Z2=_wave(t,-I,ft=ft),  # exits BB2 via BC
                    i_Tr=_zeros(t), I_f=I)
    elif fault_loc == "load_external":
        # Gen(BB2) → Tr → fault external; BC carries nothing
        I = abs(V_PRE / (Z_SRC + Z_TR)) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_zeros(t),
                    i_BC_Z1=_zeros(t), i_BC_Z2=_zeros(t),
                    i_Tr=_wave(t,-I,ft=ft), I_f=I)


def _zones_T3(d):
    z1 = [d["i_Line"], d["i_BC_Z1"]]
    z2 = [d["i_BC_Z2"], d["i_Gen"], d["i_Tr"]]
    ck = [d["i_Line"], d["i_Gen"], d["i_Tr"]]
    return z1, z2, ck


# ---------------------------------------------------------------------------
# T4_SPLIT: BC breaker open — buses isolated
# Gen + Line on BB1;  Tr on BB2 (no source).
# ---------------------------------------------------------------------------

def _gen_T4_SPLIT(fault_loc, fault_type, t, ft, af):
    if fault_loc == "bb1":
        I = abs(V_PRE / Z_SRC) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_zeros(t),
                    i_BC_Z1=_zeros(t), i_BC_Z2=_zeros(t),
                    i_Tr=_zeros(t), I_f=I)
    elif fault_loc in ("bb2", "bc_internal", "load_external"):
        # No source on BB2 side; no path through open BC
        return dict(i_Gen=_zeros(t), i_Line=_zeros(t),
                    i_BC_Z1=_zeros(t), i_BC_Z2=_zeros(t),
                    i_Tr=_zeros(t), I_f=0.0)
    elif fault_loc == "line_external":
        I = abs(V_PRE / (Z_SRC + Z_LINE)) * af
        return dict(i_Gen=_wave(t,I,ft=ft), i_Line=_wave(t,-I,ft=ft),
                    i_BC_Z1=_zeros(t), i_BC_Z2=_zeros(t),
                    i_Tr=_zeros(t), I_f=I)


def _zones_T4(d):
    # BC term is zero (BC open); use same structure for consistency
    z1 = [d["i_Gen"], d["i_Line"], d["i_BC_Z1"]]
    z2 = [d["i_BC_Z2"], d["i_Tr"]]
    ck = [d["i_Gen"], d["i_Line"], d["i_Tr"]]
    return z1, z2, ck


# ---------------------------------------------------------------------------
# Snapshot generator
# ---------------------------------------------------------------------------

def generate_transfer_snapshot(
    topology:     str,
    fault_loc:    str,
    fault_type:   str   = "3ph",
    fault_time_s: float = 0.02,
    duration_s:   float = 0.15,
    tip_split:    float = 0.50,
) -> TransferSnapshot:
    t  = np.arange(0, duration_s, 1.0 / FS)
    ft = fault_time_s
    af = AG_FACTOR if fault_type == "ag" else 1.0

    if topology == "T1_NORM":
        d  = _gen_T1_NORM(fault_loc, fault_type, t, ft, af)
        z1, z2, ck = _zones_T1(d)
        snap = TransferSnapshot(topology=topology, fault_loc=fault_loc,
                                fault_type=fault_type, I_fault_pu=float(d["I_f"]),
                                time_s=t, i_Z1_feeders=z1,
                                i_Z2_feeders=z2, i_CK_feeders=ck)

    elif topology == "T2_TIP":
        d  = _gen_T2_TIP(fault_loc, fault_type, t, ft, af, split=tip_split)
        z1, z2, ck = _zones_T2(d)
        snap = TransferSnapshot(topology=topology, fault_loc=fault_loc,
                                fault_type=fault_type, I_fault_pu=float(d["I_f"]),
                                time_s=t, i_Z1_feeders=z1,
                                i_Z2_feeders=z2, i_CK_feeders=ck)

    elif topology == "T3_POST":
        d  = _gen_T3_POST(fault_loc, fault_type, t, ft, af)
        z1, z2, ck = _zones_T3(d)
        snap = TransferSnapshot(topology=topology, fault_loc=fault_loc,
                                fault_type=fault_type, I_fault_pu=float(d["I_f"]),
                                time_s=t, i_Z1_feeders=z1,
                                i_Z2_feeders=z2, i_CK_feeders=ck)

    elif topology == "T4_SPLIT":
        d  = _gen_T4_SPLIT(fault_loc, fault_type, t, ft, af)
        z1, z2, ck = _zones_T4(d)
        snap = TransferSnapshot(topology=topology, fault_loc=fault_loc,
                                fault_type=fault_type, I_fault_pu=float(d["I_f"]),
                                time_s=t, i_Z1_feeders=z1,
                                i_Z2_feeders=z2, i_CK_feeders=ck)

    elif topology == "T5_LAG":
        # Physical: POST topology (Gen on BB2)
        d_post = _gen_T3_POST(fault_loc, fault_type, t, ft, af)
        z1_correct, z2_correct, ck_correct = _zones_T3(d_post)
        # Stale: engine still uses NORM zone assignment with POST physics
        d_norm_physics = _gen_T3_POST(fault_loc, fault_type, t, ft, af)
        d_norm_stale   = _gen_T1_NORM(fault_loc, fault_type, t, ft, af)
        z1_stale, z2_stale, ck_stale = _zones_T1(d_norm_stale)
        snap = TransferSnapshot(
            topology=topology, fault_loc=fault_loc,
            fault_type=fault_type, I_fault_pu=float(d_post["I_f"]),
            time_s=t,
            i_Z1_feeders=z1_correct, i_Z2_feeders=z2_correct,
            i_CK_feeders=ck_correct,
            i_Z1_stale=z1_stale, i_Z2_stale=z2_stale, i_CK_stale=ck_stale,
        )
    else:
        raise ValueError(f"Unknown topology: {topology}")

    return snap


# ---------------------------------------------------------------------------
# Expected outcomes
# ---------------------------------------------------------------------------

EXPECTED = {
    "T1_NORM": {
        "bb1":           {"bb1_trip": True},
        "bb2":           {"bb2_trip": True},
        "bc_internal":   {"bc_trip":  True},
        "line_external": {"no_trip":  True},
        "load_external": {"no_trip":  True},
    },
    "T2_TIP": {
        "bb1":           {"bb1_trip": True},
        "bb2":           {"bb2_trip": True},
        "bc_internal":   {"bc_trip":  True},
        "line_external": {"no_trip":  True},
        "load_external": {"no_trip":  True},
    },
    "T3_POST": {
        "bb1":           {"bb1_trip": True},
        "bb2":           {"bb2_trip": True},
        "bc_internal":   {"bc_trip":  True},
        "line_external": {"no_trip":  True},
        "load_external": {"no_trip":  True},
    },
    "T4_SPLIT": {
        "bb1":           {"bb1_trip":  True},
        "bb2":           {"no_trip":   True},   # no source on BB2
        "bc_internal":   {"no_trip":   True},   # BC open, no path
        "line_external": {"no_trip":   True},
        "load_external": {"no_trip":   True},
    },
    "T5_LAG": {
        # Expected after GOOSE update (POST topology):
        "bb1":           {"bb1_trip": True},
        "bb2":           {"bb2_trip": True},
        "bc_internal":   {"bc_trip":  True},
        "line_external": {"no_trip":  True},
        "load_external": {"no_trip":  True},
    },
}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Topology  Fault              Z1      Z2      CK")
    print("-" * 58)
    all_ok = True
    for topo in TOPOLOGIES:
        for loc in FAULT_LOCATIONS:
            s   = generate_transfer_snapshot(topo, loc, "3ph")
            d1  = float(np.abs(sum(s.i_Z1_feeders)).max())
            d2  = float(np.abs(sum(s.i_Z2_feeders)).max())
            dc  = float(np.abs(sum(s.i_CK_feeders)).max())
            exp = EXPECTED[topo][loc]
            # Check expected non-zero zones
            bb1_ok = ("bb1_trip" in exp) == (d1 > 0.5 and dc > 0.5)
            bb2_ok = ("bb2_trip" in exp) == (d2 > 0.5 and dc > 0.5)
            bc_ok  = ("bc_trip"  in exp) == (dc > 0.5 and d1 < 0.1 and d2 < 0.1)
            no_ok  = ("no_trip"  in exp) == (d1 < 0.1 and d2 < 0.1 and dc < 0.1)
            ok     = bb1_ok and bb2_ok and bc_ok and no_ok
            mark   = "  OK" if ok else "  FAIL ←"
            if not ok:
                all_ok = False
            print(f"  {topo}  {loc:18s}  {d1:6.2f}  {d2:6.2f}  {dc:6.2f}{mark}")
        print()

    if all_ok:
        print("transfer_network self-test PASSED.")
    else:
        print("transfer_network self-test FAILED — see FAIL markers above.")
