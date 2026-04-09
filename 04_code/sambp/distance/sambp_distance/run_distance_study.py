"""
run_distance_study.py
=====================
SAMBP TR-18/2026 -- Mho Distance Relay (21/21P) Study.

Study objectives
----------------
1. Zone reach verification: confirm Zone 1/2/3 boundaries on the R-X plane.
2. Selectivity matrix: 5 fault locations × 3 fault types = 15 scenarios,
   each assessed for zone, timing, and coordination with 87B/87L.
3. Coordination with 87B/87L:
   - Internal line fault (0-80% = Zone 1): 87L trips instantly, 21 Zone 1 also.
   - Remote bus fault (>80% of line): 87B trips the remote bus; 21 Zone 2 backs up.
   - Local bus fault: 87B Zone (bus differential); 21 should not respond.
4. Load blinder: verify heavy load (R=0.5 pu) is blocked at all zones.
5. HIF coverage: high-impedance fault (alpha=0.05, Z_arc ≈ 2 pu) — check if
   Zone 1 can detect despite arc resistance.

Network (TR-15/16 Thevenin):
    Z_src = j0.10 pu    (source impedance from infinite bus to local bus)
    Z_line = j0.05 pu   (protected line from local bus to remote bus)
    V_pre = 1.0 pu

Fault impedance model:
    Z_fault(alpha) = Z_arc / alpha² (arc resistance scales with fault level)
    For alpha=1.0, 3ph: Z_arc = 0 (bolted)
    For alpha=0.05 ag HIF: Z_arc ≈ 2.0 pu (high-impedance path)

Measured impedance at relay (local bus):
    Z_m = (V_relay) / (I_relay)
    = Z_line × fault_fraction + Z_arc_total

Outputs
-------
    outputs/tr18_zone_boundaries.csv
    outputs/tr18_selectivity.csv
    outputs/tr18_coordination.csv
    outputs/tr18_summary.txt
"""

from __future__ import annotations

import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from models.mho_relay_model import (
    MhoRelayConfig, MhoZoneState, MhoDecision,
    evaluate_mho_zone, measure_impedance_3ph, measure_impedance_ag,
    _mho_criterion,
)

# ---------------------------------------------------------------------------
# Network constants
# ---------------------------------------------------------------------------

Z_SRC  = 1j * 0.10   # source impedance
Z_LINE = 1j * 0.05   # protected line
V_PRE  = 1.0 + 0j    # pre-fault voltage

# Relay configuration
CFG = MhoRelayConfig(
    Z_line    = Z_LINE,
    MTA_deg   = 80.0,
    k0_factor = 0.667,
    zone1_pct = 0.80,
    zone2_pct = 1.20,
    zone3_pct = 1.80,
    t_zone2   = 0.30,
    t_zone3   = 0.60,
    R_blinder = 0.40,
)

DT = 0.02   # relay evaluation step [s]


# ---------------------------------------------------------------------------
# Fault impedance computation
# ---------------------------------------------------------------------------

def measured_Z_3ph_bolted(fault_fraction: float) -> complex:
    """
    Three-phase bolted fault at fraction d of the line from local bus.
    Measured impedance at the relay (Thevenin: relay sees Z_line × d).
    """
    return Z_LINE * fault_fraction


def measured_Z_ag(fault_fraction: float, Z_arc: complex = 0j) -> complex:
    """
    Phase-A-to-ground fault at fraction d with arc impedance Z_arc.
    The relay measures the loop impedance approximately as:
        Z_m ≈ Z_line × d + Z_arc / (1 + Z_src/(Z_line×d + Z_arc) × 0.5)
    Simplified (arc in shunt with return path):
        Z_m ≈ Z_line × d + Z_arc_apparent
    where Z_arc_apparent = Z_arc × (Z_src + Z_line) / (Z_src)  (infeed correction)
    For the TR-18 network (Z_src=j0.10, Z_line=j0.05):
        infeed_factor = (Z_src + Z_LINE) / Z_src = j0.15 / j0.10 = 1.5
    """
    infeed_factor = (Z_SRC + Z_LINE) / Z_SRC  # ≈ 1.5 for this network
    return Z_LINE * fault_fraction + Z_arc * infeed_factor


# ---------------------------------------------------------------------------
# Study 1: Zone reach verification
# ---------------------------------------------------------------------------

def study_zone_boundaries():
    """
    Sweep fault fraction from 0 to 2.0 × Z_line, record zone entry/exit.
    """
    fractions = np.linspace(0.0, 2.2, 441)
    rows = []
    for d in fractions:
        Z_m  = measured_Z_3ph_bolted(d)
        z1   = _mho_criterion(Z_m, CFG.Z_reach1)
        z2   = _mho_criterion(Z_m, CFG.Z_reach2)
        z3   = _mho_criterion(Z_m, CFG.Z_reach3)
        rows.append({
            "fault_fraction": round(float(d), 3),
            "Z_m_imag": round(float(Z_m.imag), 5),
            "zone1": z1, "zone2": z2, "zone3": z3,
        })
    # Find precise boundaries
    def _boundary(key):
        vals = [r["fault_fraction"] for r in rows if r[key]]
        return (min(vals), max(vals)) if vals else (None, None)

    b1 = _boundary("zone1")
    b2 = _boundary("zone2")
    b3 = _boundary("zone3")
    print(f"  Zone 1: d = {b1[0]:.3f} … {b1[1]:.3f} (expect 0 … 0.80)")
    print(f"  Zone 2: d = {b2[0]:.3f} … {b2[1]:.3f} (expect 0 … 1.20)")
    print(f"  Zone 3: d = {b3[0]:.3f} … {b3[1]:.3f} (expect 0 … 1.80)")
    return rows, (b1, b2, b3)


# ---------------------------------------------------------------------------
# Study 2: Selectivity matrix
# ---------------------------------------------------------------------------

#  (label, description, Z_m, expected_zone, expected_trip, 87B_87L_notes)
SCENARIOS = [
    # ---- Internal faults (Zone 1 — 87L also trips) ------------------------
    ("INT_25",  "25% line fault 3ph (bolted)",
     measured_Z_3ph_bolted(0.25),  1, True, "87L also trips (Zone 1)"),
    ("INT_50",  "50% line fault 3ph (bolted)",
     measured_Z_3ph_bolted(0.50),  1, True, "87L also trips (Zone 1)"),
    ("INT_79",  "79% line fault 3ph (bolted)",
     measured_Z_3ph_bolted(0.79),  1, True, "87L trips (Zone 1)"),
    ("INT_82",  "82% line fault 3ph (just outside Zone 1)",
     measured_Z_3ph_bolted(0.82),  2, True, "87L trips (Zone 2 timed)"),
    # ---- Remote bus fault (Zone 2 — 87B trips remote bus) -----------------
    ("RBUS",    "Remote bus fault 3ph (d=1.05)",
     measured_Z_3ph_bolted(1.05),  2, True, "87B remote trips; 21 Zone 2 backup"),
    # ---- Beyond remote bus (Zone 3 — back-up) -----------------------------
    ("BKUP",    "Beyond remote (d=1.45)",
     measured_Z_3ph_bolted(1.45),  3, True, "Zone 3 back-up only"),
    # ---- Local bus fault (d=0, Z_m→0) — relay should see Zone 1 ----------
    # In practice 87B trips the bus; 21 Z1 may also operate (coordination issue)
    ("LBUS",    "Local bus fault 3ph (d=0.0)",
     measured_Z_3ph_bolted(0.02),  1, True, "87B trips bus; 21 Zone1 overlap"),
    # ---- Ground fault (ag) with arc impedance ------------------------------
    ("AG_50",   "50% ag fault (bolted, d=0.50)",
     measured_Z_ag(0.50, 0j),      1, True, "ag Zone 1 trip"),
    ("AG_HIF",  "ag HIF (d=0.50, Z_arc=1.5)",
     measured_Z_ag(0.50, 1.5j),    0, False,"Outside Zone 1 due to arc R; 87L detects"),
    # ---- Load (must NOT trip) ---------------------------------------------
    ("LOAD_N",  "Normal load (R=0.5 pu, X=0.1 pu)",
     0.50 + 0.10j,                 0, False, "Load blinder: no trip"),
    ("LOAD_H",  "Heavy load (R=0.3 pu, X=0.08 pu)",
     0.30 + 0.08j,                 0, False, "Small R — check blinder margin"),
    # ---- Out-of-zone (too far — no trip expected) -------------------------
    ("OOZ",     "Outside Zone 3 (d=2.0)",
     measured_Z_3ph_bolted(2.0),   0, False, "No trip (outside all zones)"),
]


def study_selectivity():
    rows = []
    for (label, desc, Z_m, exp_zone, exp_trip, notes) in SCENARIOS:
        # Simulate enough time steps for Zone 2/3 timers to expire
        st = MhoZoneState()
        dec = None
        n_steps = max(1, int(0.70 / DT) + 1)  # 0.70 s > Zone 3 timer
        for _ in range(n_steps):
            dec, st = evaluate_mho_zone(Z_m, CFG, st, DT)
            if dec.trip:
                break

        correct = (dec.trip == exp_trip) and (dec.zone == exp_zone or not exp_trip)
        rows.append({
            "label":      label,
            "description":desc,
            "Z_m_real":   round(float(Z_m.real), 4),
            "Z_m_imag":   round(float(Z_m.imag), 4),
            "zone1_in":   dec.zone1_in,
            "zone2_in":   dec.zone2_in,
            "zone3_in":   dec.zone3_in,
            "load_block": dec.load_block,
            "trip":       dec.trip,
            "zone":       dec.zone,
            "exp_zone":   exp_zone,
            "exp_trip":   exp_trip,
            "correct":    correct,
            "notes":      notes,
        })
        status = "OK" if correct else "FAIL"
        print(f"  [{status}] {label:10s}: Z_m={Z_m.real:.3f}+j{Z_m.imag:.3f}  "
              f"zone={dec.zone}  trip={dec.trip}  {'load_block' if dec.load_block else ''}")
    return rows


# ---------------------------------------------------------------------------
# Study 3: Coordination summary
# ---------------------------------------------------------------------------

COORD_SCENARIOS = [
    # (fault_type, fault_location, 87B_trips, 87L_trips, expected_21_zone, notes)
    ("3ph", "INT 0-80%",  False, True,  1, "87L z1 inst; 21 Z1 inst — concurrent"),
    ("3ph", "INT 80-100%",False, True,  2, "87L inst; 21 Zone2 0.3s — 87L faster"),
    ("3ph", "RBUS",        True, False, 2, "87B trips; 21 Zone2 backup 0.3s"),
    ("3ph", "LBUS",        True, False, 1, "87B trips; 21 Zone1 overlap (see note)"),
    ("ag",  "INT (bolted)",False, True, 1, "87L inst; 21 Z1 inst"),
    ("ag",  "HIF (Z_arc)", False, True, 0, "87L detects HIF; 21 cannot reach"),
    ("any", "LOAD",        False, False,0, "No trip: 87B/87L/21 all restrain"),
]

def study_coordination():
    rows = []
    for (ft, floc, b87_trip, l87_trip, z21_zone, notes) in COORD_SCENARIOS:
        rows.append({
            "fault_type":  ft,
            "fault_loc":   floc,
            "87B_trip":    b87_trip,
            "87L_trip":    l87_trip,
            "21_zone":     z21_zone,
            "21_time_s":   {0:"n/a",1:"instant",2:"0.30s",3:"0.60s"}[z21_zone],
            "coord_notes": notes,
        })
    return rows


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

if __name__ == "__main__":
    os.makedirs("outputs", exist_ok=True)

    print("=" * 62)
    print("SAMBP TR-18/2026 Mho Distance Relay (21/21P) Study")
    print("=" * 62)

    print("\nStudy 1 — Zone reach verification:")
    zone_rows, (b1, b2, b3) = study_zone_boundaries()
    _save_csv("outputs/tr18_zone_boundaries.csv", zone_rows)

    print("\nStudy 2 — Selectivity matrix:")
    sel_rows = study_selectivity()
    _save_csv("outputs/tr18_selectivity.csv", sel_rows)
    n_ok = sum(r["correct"] for r in sel_rows)
    print(f"\n  Result: {n_ok}/{len(sel_rows)} correct")

    print("\nStudy 3 — Coordination summary:")
    coord_rows = study_coordination()
    _save_csv("outputs/tr18_coordination.csv", coord_rows)

    # ---- Summary text -------------------------------------------------------
    lines = [
        "SAMBP TR-18/2026 Mho Distance Relay Summary",
        "=" * 60,
        "",
        "Relay configuration",
        "-" * 60,
        f"  Z_line      : {CFG.Z_line}  pu",
        f"  MTA         : {CFG.MTA_deg}°",
        f"  k0_factor   : {CFG.k0_factor}",
        f"  Zone 1 reach: {CFG.zone1_pct} × Z_line = {CFG.Z_reach1}  pu",
        f"  Zone 2 reach: {CFG.zone2_pct} × Z_line = {CFG.Z_reach2}  pu  (t={CFG.t_zone2}s)",
        f"  Zone 3 reach: {CFG.zone3_pct} × Z_line = {CFG.Z_reach3}  pu  (t={CFG.t_zone3}s)",
        f"  R_blinder   : {CFG.R_blinder} pu",
        "",
        "Zone boundary verification (3ph bolted, d=fault fraction)",
        "-" * 60,
        f"  Zone 1: d = {b1[0]:.3f} … {b1[1]:.3f}  (design: 0.000 … 0.800)",
        f"  Zone 2: d = {b2[0]:.3f} … {b2[1]:.3f}  (design: 0.000 … 1.200)",
        f"  Zone 3: d = {b3[0]:.3f} … {b3[1]:.3f}  (design: 0.000 … 1.800)",
        "",
        f"Selectivity: {n_ok}/{len(sel_rows)} correct",
        "-" * 60,
    ]
    for r in sel_rows:
        status = "OK" if r["correct"] else "FAIL"
        lines.append(
            f"  [{status}] {r['label']:10s}: zone={r['zone']}  trip={r['trip']}  "
            f"load_block={r['load_block']}  | {r['notes']}"
        )
    lines += [
        "",
        "Coordination matrix (21 vs 87B/87L)",
        "-" * 60,
    ]
    for r in coord_rows:
        lines.append(
            f"  {r['fault_type']:5s} {r['fault_loc']:15s}: "
            f"87B={r['87B_trip']}  87L={r['87L_trip']}  "
            f"21_zone={r['21_zone']}  "
            f"t={r['21_time_s']}  | {r['coord_notes']}"
        )

    summary_path = "outputs/tr18_summary.txt"
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nSaved: {summary_path}")
    for line in lines:
        print(line)
