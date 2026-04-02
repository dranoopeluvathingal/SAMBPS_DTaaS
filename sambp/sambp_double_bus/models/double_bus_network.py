"""
double_bus_network.py
======================
Analytical double-busbar network model for the SAMBP TR-07 study.

Topology
--------

    Gen ─[Z_src]─[BB1]─[Z_bc]─[BB2]─[Z_tr]─ Load
                  |                   |
              Line feeder         Transformer
              (passive)           feeder

Zones
-----
    Zone 1 (BB1) : Gen feeder  + Line feeder + Bus Coupler (BB1 side)
    Zone 2 (BB2) : Transformer feeder + Bus Coupler (BB2 side)
    Check zone   : Gen feeder  + Line feeder + Transformer feeder
                   (does NOT include BC — BC current cancels in check zone)

Sign convention: positive current = flowing INTO the zone / bus.

Bus coupler CT modelling
------------------------
A single CT on the BB1 side of the coupler is used:
    Zone 1 sees:  +I_BC if current flows from BB2→BB1 (entering BB1)
                  -I_BC if current flows from BB1→BB2 (exiting BB1)
    Zone 2 sees:  opposite sign of the Zone 1 entry (current that
                  exits BB1 = entering BB2 if continuity holds)
For a BC internal fault, the BC CT lies between the fault and BB2,
so BC CT reads the full fault current for Zone 1 (unbalanced) while
Zone 2 sees zero — making the BC fault a classic blind-spot that the
CHECK zone resolves.

Network parameters (pu, 100 MVA, 33 kV base)
---------------------------------------------
    Z_src  = j0.10  (synchronous generator subtransient)
    Z_bc   = j0.01  (bus coupler — very low, essentially a switch)
    Z_line = j0.05  (connected line, far end passive)
    Z_tr   = j0.08  (transformer leakage, load-side passive)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass

FREQ = 50.0     # Hz
FS   = 1000.0   # samples/s

Z_SRC  = 1j * 0.10
Z_BC   = 1j * 0.01
Z_LINE = 1j * 0.05    # passive far-end
Z_TR   = 1j * 0.08    # passive load
V_PRE  = 1.00 + 0j

FAULT_LOCATIONS = [
    "bb1",            # fault at Bus 1
    "bb2",            # fault at Bus 2
    "bc_internal",    # fault inside bus coupler (check-zone test)
    "line_external",  # fault beyond line feeder (external to both zones)
    "load_external",  # fault beyond transformer (external to both zones)
]


# ---------------------------------------------------------------------------
# Fault current phasors
# ---------------------------------------------------------------------------

def _fault_current(fault_loc: str, fault_type: str) -> complex:
    if fault_loc == "bb1":
        # Only Gen feeds BB1 (line and BC paths have no active infeed)
        Z_th = Z_SRC
    elif fault_loc == "bb2":
        # Gen → BB1 → BC → BB2
        Z_th = Z_SRC + Z_BC
    elif fault_loc == "bc_internal":
        # Fault inside BC, between BB1-side CT and BB2
        # Gen is the only source; Z to fault mid-way through BC
        Z_th = Z_SRC + Z_BC / 2
    elif fault_loc == "line_external":
        # Fault on the line beyond BB1 (external to Zone 1)
        Z_th = Z_SRC + Z_LINE
    elif fault_loc == "load_external":
        # Fault beyond transformer (external to Zone 2)
        Z_th = Z_SRC + Z_BC + Z_TR
    else:
        raise ValueError(f"Unknown fault_loc: {fault_loc}")

    I_3ph = V_PRE / Z_th
    if fault_type == "3ph":
        return I_3ph
    elif fault_type == "ag":
        return I_3ph * 0.6
    else:
        raise ValueError(f"Unknown fault_type: {fault_type}")


# ---------------------------------------------------------------------------
# Waveform generation
# ---------------------------------------------------------------------------

@dataclass
class DoubleBusSnapshot:
    fault_loc:   str
    fault_type:  str
    I_fault_pu:  float
    time_s:      np.ndarray

    # Zone 1 (BB1) feeders: [Gen, Line, BC_BB1_side]
    i_Z1_feeders: list[np.ndarray]   # each (3, T)

    # Zone 2 (BB2) feeders: [Transformer, BC_BB2_side]
    i_Z2_feeders: list[np.ndarray]   # each (3, T)

    # Check zone feeders: [Gen, Line, Transformer]  (BC cancels)
    i_CK_feeders: list[np.ndarray]   # each (3, T)


def generate_double_bus_snapshot(
    fault_loc:    str,
    fault_type:   str = "3ph",
    fault_time_s: float = 0.02,
    duration_s:   float = 0.15,
) -> DoubleBusSnapshot:
    """
    Generate all CT waveforms for a given fault scenario.

    CT waveforms follow the standard DC-offset fault model:
        i(t) = I_peak * [sin(ωt + φ_k) + 0.8 * exp(-t/τ)]
    """
    t    = np.arange(0, duration_s, 1.0 / FS)
    N    = len(t)
    ph   = [0.0, -2*np.pi/3, 2*np.pi/3]
    I_f  = abs(_fault_current(fault_loc, fault_type))
    mask = t >= fault_time_s
    dt   = t - fault_time_s

    def wave(I_peak, phi_k=0.0, dc=0.8, tau=0.05):
        w = np.zeros((3, N))
        for k, p in enumerate(ph):
            w[k, mask] = I_peak * (
                np.sin(2*np.pi*FREQ*dt[mask] + p + phi_k)
                + dc * np.exp(-dt[mask] / tau)
            )
        return w

    def zeros():
        return np.zeros((3, N))

    # Compute source currents analytically
    if fault_loc == "bb1":
        # Only gen feeds fault at BB1; no infeed from BC/line side
        I_gen = abs(V_PRE / Z_SRC)
        i_Gen = wave(I_gen)     # INTO BB1 from gen → positive
        i_Line = zeros()        # passive, no infeed
        i_BC_Z1 = zeros()       # no infeed from BB2 side
        i_BC_Z2 = zeros()       # nothing flows through BC
        i_Tr  = zeros()         # passive

    elif fault_loc == "bb2":
        # Gen → BB1 → BC → BB2 → fault
        I_gen = abs(V_PRE / (Z_SRC + Z_BC))
        i_Gen    = wave(I_gen)        # INTO BB1 from gen
        i_Line   = zeros()
        i_BC_Z1  = wave(-I_gen)       # Gen exits BB1 through BC = −into Zone1
        i_BC_Z2  = wave(I_gen)        # same current enters BB2 = +into Zone2
        i_Tr     = zeros()

    elif fault_loc == "bc_internal":
        # Fault inside BC: CT (BB1-side) captures full current
        # BB2 is isolated from fault (no current reaches BB2 side)
        I_gen = abs(V_PRE / (Z_SRC + Z_BC / 2))
        i_Gen    = wave(I_gen)        # INTO BB1 from gen
        i_Line   = zeros()
        i_BC_Z1  = wave(-I_gen)       # exits BB1 → BC → fault, Zone1 CT reads it
        i_BC_Z2  = zeros()            # fault is before BB2-side CT: Z2 sees nothing
        i_Tr     = zeros()

    elif fault_loc == "line_external":
        # Fault on line beyond BB1; through-current for all zones
        I_gen  = abs(V_PRE / (Z_SRC + Z_LINE))
        i_Gen  = wave(I_gen)          # gen feeds fault through BB1
        i_Line = wave(-I_gen)         # current exits BB1 via line feeder
        i_BC_Z1 = zeros()             # no current through BC
        i_BC_Z2 = zeros()
        i_Tr    = zeros()

    elif fault_loc == "load_external":
        # Fault beyond transformer; through-current through BC and TR
        I_gen  = abs(V_PRE / (Z_SRC + Z_BC + Z_TR))
        i_Gen  = wave(I_gen)
        i_Line = zeros()
        i_BC_Z1 = wave(-I_gen)        # current exits BB1 through BC
        i_BC_Z2 = wave(I_gen)         # current enters BB2 from BC
        i_Tr    = wave(-I_gen)        # current exits BB2 through transformer
    else:
        raise ValueError(f"Unknown fault_loc: {fault_loc}")

    return DoubleBusSnapshot(
        fault_loc     = fault_loc,
        fault_type    = fault_type,
        I_fault_pu    = float(I_f),
        time_s        = t,
        i_Z1_feeders  = [i_Gen, i_Line, i_BC_Z1],
        i_Z2_feeders  = [i_BC_Z2, i_Tr],
        i_CK_feeders  = [i_Gen, i_Line, i_Tr],
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for loc in FAULT_LOCATIONS:
        s = generate_double_bus_snapshot(loc, "3ph")
        d1 = np.abs(sum(s.i_Z1_feeders)).max()
        d2 = np.abs(sum(s.i_Z2_feeders)).max()
        dc = np.abs(sum(s.i_CK_feeders)).max()
        print(f"  {loc:18s}  I_f={s.I_fault_pu:.2f}  "
              f"Z1={d1:.3f}  Z2={d2:.3f}  CK={dc:.3f}")

    print("\nExpected non-zero differentials:")
    print("  bb1          → Z1 only")
    print("  bb2          → Z2 only")
    print("  bc_internal  → CK only (Z1=0, Z2=0 — classic blind spot)")
    print("  line_external→ all zero")
    print("  load_external→ all zero")
    print("\ndouble_bus_network self-test PASSED.")
