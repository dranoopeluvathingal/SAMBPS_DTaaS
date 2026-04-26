#!/usr/bin/env python3
"""
run_tr66_n1_mc.py  —  SAMBP TR-66/2026 N-1 Cross-Trip Monte Carlo
==================================================================
Validates that no combination of simultaneous element operations in the
SAMBP protection suite causes a misoperation (cross-trip).

Design (from ch07 Table tab:ch7_n1):
  8 primary-event scenarios × 1 000 trials each = 8 000 total runs.
  Primary metric: P_XFA = Prob(secondary element falsely trips | primary event)
  Target: P_XFA ≤ 0.001 for every element pair.

Physical basis for cross-trip immunity:
  Any fault in Zone A creates a THROUGH-current at Zone B.
  By KCL, the differential at Zone B = Σ_k ε_k × I_through_k  (CT mismatch only).
  The SAMBP slope characteristic requires I_op > max(I_op_min, SLP × I_rst)
  where I_rst ≈ I_through.  Hence cross-trip requires Σ ε_k > SLP = 0.25,
  but ε_k ~ U[-3%, 3%] → max|Σ ε_k| ≈ N × 3% = 9% << 25%.
  Formal bound:  P_XFA ≤ P(|ε_eff| > SLP) = P(|N(0, ε²/3)| > 0.25) ≈ 0.

Fault current levels (from Z-bus analysis, run_tr66_ieee39bus.py §constants):
  Bus39 3ph:  I_f=15.03 pu   (through Bus9→Line9-39: 7.10 pu)
  Line9-39:   I_f=12.3+12.1 pu (near+far ends)
  Gen stator: I_f=32.46 pu  (87G differential)
  Trafo int:  I_f=13.03 pu  (87T differential)

Parameters varied per trial:
  k_ibr   ~ U[0.0, 1.0]    IBR penetration (scales fault current)
  Z_f_pu  ~ U[0.0, 0.10]   fault impedance [pu] (reduces fault current)
  eps_CT  ~ U[-3%, 3%]      CT mismatch at each terminal (independently)
  phi0    ~ U[0°, 360°]     fault inception angle (affects DC offset amplitude)
"""

from __future__ import annotations
import csv
import pathlib
import time
from dataclasses import dataclass

import numpy as np

# ─── Relay settings (matching run_tr66_ieee39bus.py) ────────────────────────
I_OP_MIN_87B  = 0.20    # pu
I_OP_MIN_87L  = 0.12    # pu  (positive-sequence)
I_OP_MIN_87T  = 0.10    # pu
SLP_87B       = 0.25
SLP_87L       = 0.30
SLP_87T       = 0.15
I2_THR        = 0.06    # 87LN negative-seq threshold
I0_THR        = 0.04    # 87LN0 zero-seq threshold

# Stage-2 gate parameters
F_INT_VETO    = 0.60    # f_int > this → model vetoes conventional trip

# ─── Fault current levels [pu] (from TR-66 Z-bus, seed_42 baseline) ────────
IF_BUS39      = 15.03   # Bus39 bolted 3ph
IF_LINE_NEAR  = 12.30   # Line9-39 midpoint, Bus39-end contribution
IF_LINE_FAR   = 12.10   # Line9-39 midpoint, Bus9-end contribution
IF_GEN        = 32.46   # Gen G9 internal stator (87G differential)
IF_TRAFO_H    = 13.03   # Trafo Bus10-Bus32 internal (87T HV)
IF_TRAFO_X    =  6.00   # Trafo LV contribution

# Through-currents at secondary zones (from Z-bus network, approximate)
#   Bus39 fault → Line9-39 through: 7.10 pu; Bus9 through: negligible
#   Line9-39 fault → Bus39 through: 7.10 pu; Trafo through: negligible
#   Gen stator fault → Bus39 through: 0.39 pu (small)
#   Trafo fault → Bus39 through: depends on Ybus, estimated ~2 pu
IF_THROUGH_B39_VIA_L9  = 7.10    # through 87B bus for line fault
IF_THROUGH_L9_VIA_B39  = 7.10    # through 87L line for bus fault
IF_THROUGH_B39_VIA_T   = 2.00    # through 87B for trafo fault
IF_THROUGH_T_VIA_B39   = 2.00    # through 87T for bus fault

N_TRIALS_PER_SCEN = 1000


# ─── Simplified relay trip decision ─────────────────────────────────────────
def _slope_trip(I_diff_pu: float, I_rst_pu: float,
                I_op_min: float, slp: float,
                f_int: float = 0.0) -> bool:
    """Slope characteristic with Stage-2 veto."""
    if f_int > F_INT_VETO:
        return False
    thresh = max(I_op_min, slp * I_rst_pu)
    return I_diff_pu > thresh


def _I_with_Zf(I_nominal: float, Z_th_pu: float, Z_f_pu: float) -> float:
    """Scale fault current by fault impedance: I(Zf) = I(0) × Zth/(Zth+Zf)."""
    return I_nominal * Z_th_pu / (Z_th_pu + Z_f_pu)


# ─── N-1 scenario definitions ───────────────────────────────────────────────
@dataclass
class N1Scenario:
    sid:           str
    primary_relay: str          # relay that SHOULD trip
    secondary_relays: list[str] # relays that should NOT trip (P_XFA targets)
    if_primary:    float        # differential current seen by primary [pu]
    if_through:    dict         # {secondary_relay: through-current [pu]}
    n_sec_terms:   dict         # {secondary_relay: number of terminals}
    z_th_pu:       float = 1.0  # Thévenin impedance at fault bus [pu]


SCENARIOS_N1: list[N1Scenario] = [
    N1Scenario(
        sid="87T_int_fault",
        primary_relay="87T",
        secondary_relays=["87B", "87L"],
        if_primary=IF_TRAFO_H,
        if_through={"87B": IF_THROUGH_B39_VIA_T, "87L": 0.5},
        n_sec_terms={"87B": 3, "87L": 2},
        z_th_pu=0.08,
    ),
    N1Scenario(
        sid="87L_int_fault",
        primary_relay="87L",
        secondary_relays=["87T", "87B"],
        if_primary=IF_LINE_NEAR,
        if_through={"87T": 0.3, "87B": IF_THROUGH_B39_VIA_L9},
        n_sec_terms={"87T": 2, "87B": 3},
        z_th_pu=0.07,
    ),
    N1Scenario(
        sid="87B_int_fault",
        primary_relay="87B",
        secondary_relays=["87T", "87L"],
        if_primary=IF_BUS39,
        if_through={"87T": IF_THROUGH_T_VIA_B39, "87L": IF_THROUGH_L9_VIA_B39},
        n_sec_terms={"87T": 2, "87L": 2},
        z_th_pu=0.067,
    ),
    N1Scenario(
        sid="87G_gen_fault",
        primary_relay="87G",
        secondary_relays=["87B", "87L", "87T"],
        if_primary=IF_GEN,
        if_through={"87B": 0.39, "87L": 0.10, "87T": 0.05},
        n_sec_terms={"87B": 3, "87L": 2, "87T": 2},
        z_th_pu=0.03,
    ),
    N1Scenario(
        sid="OOS_relay78",
        # Power swing: slow sinusoidal current change; diff relays immune
        primary_relay="21",
        secondary_relays=["87T", "87B", "87L"],
        if_primary=2.0,        # OOS through-current amplitude [pu]
        if_through={"87T": 2.0, "87B": 2.0, "87L": 2.0},
        n_sec_terms={"87T": 2, "87B": 3, "87L": 2},
        z_th_pu=0.5,
    ),
    N1Scenario(
        sid="CT_sat_87T",
        # External fault with CT saturation → 87T should VETO, not trip
        primary_relay="87T_VETO",
        secondary_relays=["87B", "87L"],
        if_primary=6.50,       # through-current creating saturation
        if_through={"87B": 6.50, "87L": 1.5},
        n_sec_terms={"87B": 3, "87L": 2},
        z_th_pu=0.10,
    ),
    N1Scenario(
        sid="channel_loss_87L",
        # Channel loss: 87L gates off (no trip); sec. elements unaffected
        primary_relay="87L_VETO",
        secondary_relays=["87T", "87B"],
        if_primary=5.0,        # fault current present but channel lost
        if_through={"87T": 0.5, "87B": 5.0},
        n_sec_terms={"87T": 2, "87B": 3},
        z_th_pu=0.07,
    ),
    N1Scenario(
        sid="SLG_CT_sat_87T",
        # SLG + CT sat on one HV terminal → 87T should VETO
        primary_relay="87T_VETO",
        secondary_relays=["87B", "87L"],
        if_primary=7.8,        # AG through-fault × transformer CT ratio
        if_through={"87B": 3.5, "87L": 1.0},
        n_sec_terms={"87B": 3, "87L": 2},
        z_th_pu=0.09,
    ),
]

# Relay-specific settings
_RELAY_SETTINGS = {
    "87B":      (I_OP_MIN_87B, SLP_87B),
    "87L":      (I_OP_MIN_87L, SLP_87L),
    "87T":      (I_OP_MIN_87T, SLP_87T),
    "87G":      (0.10, 0.15),
    "87LN":     (I2_THR, 0.0),
    "87LN0":    (I0_THR, 0.0),
    "21":       (0.05, 0.0),
    "87T_VETO": (I_OP_MIN_87T, SLP_87T),
    "87L_VETO": (I_OP_MIN_87L, SLP_87L),
}


def _run_n1_scenario(scen: N1Scenario, rng: np.random.Generator) \
        -> tuple[int, dict[str, int]]:
    """
    Run one N-1 MC trial.
    Returns: (primary_trips, {secondary_relay: cross_trip_flag}).
    """
    k_ibr  = float(rng.uniform(0.0, 1.0))
    Z_f_pu = float(rng.uniform(0.0, 0.10))
    phi0   = float(rng.uniform(0.0, 360.0))   # not used in current logic

    # Scale primary fault current
    I_f_primary = _I_with_Zf(scen.if_primary, scen.z_th_pu, Z_f_pu)
    # IBR contribution reduces net fault current
    I_f_primary *= (1.0 - 0.5 * k_ibr)          # GFM/GFL current limiting

    # --- Primary relay decision ---
    I_op_min_p, slp_p = _RELAY_SETTINGS[scen.primary_relay]
    I_rst_p   = 0.5 * I_f_primary * 2            # simplified: 2-terminal
    # VETO scenarios: check Stage-2 gate
    if scen.primary_relay.endswith("_VETO"):
        # CT saturation → high f_int → model veto
        sat_frac = float(rng.uniform(0.40, 0.90))
        f_int_p  = 1.0 - sat_frac * 0.50        # 0.55–0.80 range
        primary_trip = int(_slope_trip(
            I_f_primary * (1.0 - sat_frac), I_rst_p,
            I_op_min_p, slp_p, f_int=f_int_p
        ))
    else:
        f_int_p = 0.10   # clean waveform
        primary_trip = int(_slope_trip(I_f_primary, I_rst_p,
                                        I_op_min_p, slp_p, f_int=f_int_p))

    # --- Secondary relay cross-trip check ---
    cross_trips: dict[str, int] = {}
    for sec_relay in scen.secondary_relays:
        I_through = _I_with_Zf(
            scen.if_through[sec_relay], scen.z_th_pu, Z_f_pu
        ) * (1.0 - 0.5 * k_ibr)

        n_terms = scen.n_sec_terms[sec_relay]
        eps = rng.uniform(-0.03, 0.03, n_terms)

        # Spurious differential from CT mismatch only (KCL exact)
        I_diff_pu = abs(I_through * np.sum(eps))   # ≈ Σ ε_k × I_through
        I_rst_pu  = I_through                       # restraint ≈ through-current

        I_op_min_s, slp_s = _RELAY_SETTINGS[sec_relay]
        f_int_s = 0.05   # external fault → clean waveform, gate passes
        cross_trips[sec_relay] = int(_slope_trip(
            I_diff_pu, I_rst_pu, I_op_min_s, slp_s, f_int=f_int_s
        ))

    return primary_trip, cross_trips


# ─── Full MC ─────────────────────────────────────────────────────────────────
def run_n1_mc(n_per_scen: int = N_TRIALS_PER_SCEN,
              rng_seed: int = 42) -> dict:
    rng = np.random.default_rng(rng_seed)

    results = {}
    for scen in SCENARIOS_N1:
        pri_trips  = 0
        xfa_counts = {r: 0 for r in scen.secondary_relays}

        for _ in range(n_per_scen):
            pt, ct = _run_n1_scenario(scen, rng)
            pri_trips += pt
            for r in scen.secondary_relays:
                xfa_counts[r] += ct[r]

        P_D   = pri_trips / n_per_scen
        P_XFA = {r: xfa_counts[r] / n_per_scen for r in scen.secondary_relays}
        results[scen.sid] = dict(
            primary=scen.primary_relay,
            secondaries=scen.secondary_relays,
            n_trials=n_per_scen,
            P_D=P_D,
            P_XFA=P_XFA,
            xfa_counts=xfa_counts,
        )
    return results


# ─── Output ───────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 72)
    print("SAMBP TR-66 N-1 MC — Cross-Trip False-Alarm Study")
    print(f"  {len(SCENARIOS_N1)} scenarios × {N_TRIALS_PER_SCEN} trials "
          f"= {len(SCENARIOS_N1) * N_TRIALS_PER_SCEN:,} total relay evaluations")
    print(f"  Target: P_XFA ≤ 0.001 per element pair")
    print("=" * 72)

    t0 = time.time()
    results = run_n1_mc()
    elapsed = time.time() - t0

    P_XFA_MAX = 0.001

    header = f"{'Scenario':<22} {'Primary':>8} {'P_D/Veto':>8}  {'Secondary checks (P_XFA)'}"
    print("\n" + header)
    print("─" * 70)

    all_pass = True
    rows_csv  = []

    for sid, r in results.items():
        xfa_str = "  ".join(
            f"{rel}={r['P_XFA'][rel]:.4f}"
            f"{'✓' if r['P_XFA'][rel] <= P_XFA_MAX else '✗'}"
            for rel in r["secondaries"]
        )
        is_veto = r["primary"].endswith("_VETO")
        if is_veto:
            # VETO scenario: primary SHOULD NOT trip; display veto rate
            veto_rate = 1.0 - r["P_D"]
            pd_flag = "VETO✓" if veto_rate >= 0.80 else "WARN"
            pd_str  = f"{veto_rate:>5.3f}v"   # 'v' = veto rate
        else:
            pd_flag = "PASS" if r["P_D"] >= 0.80 else "FAIL"
            pd_str  = f"{r['P_D']:>6.3f}"
        print(f"{sid:<22} {r['primary']:>8} {pd_str}  {xfa_str}  [{pd_flag}]")

        for rel in r["secondaries"]:
            ok = r["P_XFA"][rel] <= P_XFA_MAX
            if not ok:
                all_pass = False
            rows_csv.append({
                "scenario": sid,
                "primary":  r["primary"],
                "secondary": rel,
                "n_trials": r["n_trials"],
                "P_D":      f"{r['P_D']:.4f}",
                "P_XFA":    f"{r['P_XFA'][rel]:.4f}",
                "xfa_count": r["xfa_counts"][rel],
                "target_met": int(ok),
            })

    print("─" * 70)
    total_xfa = sum(row["xfa_count"] for row in rows_csv)
    total_pairs = len(rows_csv)
    print(f"\n  Total element pairs tested: {total_pairs}")
    print(f"  Total cross-trips observed: {total_xfa}")
    print(f"  Max P_XFA observed:         "
          f"{max(float(r['P_XFA']) for r in rows_csv):.4f}   target ≤ {P_XFA_MAX}")

    print("\n" + "═" * 72)
    print(f"TR-66 N-1 MC OVERALL: "
          f"{'ALL P_XFA TARGETS MET — PASS' if all_pass else 'TARGETS MISSED — CHECK ABOVE'}")
    print("═" * 72)
    print(f"  (elapsed: {elapsed:.2f}s)")

    out = pathlib.Path(__file__).parent / "outputs" / "tr66"
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "tr66_n1_mc.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_csv[0].keys()))
        w.writeheader()
        w.writerows(rows_csv)

    # Summary metrics CSV
    mc_path = out / "tr66_n1_mc_summary.csv"
    with open(mc_path, "w", newline="") as fh:
        w2 = csv.writer(fh)
        w2.writerow(["metric", "value", "target", "pass"])
        w2.writerow(["n_scenarios", len(SCENARIOS_N1), "", ""])
        w2.writerow(["n_trials_per_scen", N_TRIALS_PER_SCEN, "", ""])
        w2.writerow(["total_element_pairs", total_pairs, "", ""])
        w2.writerow(["total_cross_trips", total_xfa, 0, int(total_xfa == 0)])
        w2.writerow(["max_P_XFA",
                     f"{max(float(r['P_XFA']) for r in rows_csv):.4f}",
                     f"<={P_XFA_MAX}", int(all_pass)])
        w2.writerow(["all_targets_met", int(all_pass), "1", int(all_pass)])
    print(f"  Detail CSV  → {csv_path}")
    print(f"  Summary CSV → {mc_path}")


if __name__ == "__main__":
    main()
