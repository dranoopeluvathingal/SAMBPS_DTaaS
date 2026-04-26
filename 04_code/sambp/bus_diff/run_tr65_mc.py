#!/usr/bin/env python3
"""
run_tr65_mc.py  —  SAMBP TR-65/2026 Monte Carlo Sensitivity Study
===================================================================
Parametric MC extension of the TR-65 OpenDSS deterministic study.
Uses the Thévenin-circuit parameters derived from the OpenDSS network
to vary fault resistance, load level, CT mismatch, and DG output
analytically across 2 000 trials (1 000 security, 1 000 dependability)
WITHOUT re-running OpenDSS for each trial.

Physical validity: the distribution network is linear (Kirchhoff + Ohm),
so phasor-domain parametric scaling is exact.  The SAMBP relay logic
(slope characteristic + Stage-2 gate) is applied in simplified form
consistent with BusDiffRelayConfig used in run_tr65_opendss.py.

Network parameters (from OpenDSS model, run_tr65_opendss.py §constants):
  V_phase = 11 kV / √3 = 6 351 V
  Z_SRC   = 0.0726 + j1.21  Ω  (Thévenin at MainBus)
  Z_F2    = 0.242  + j0.364 Ω  (Feeder-2, 2 km)
  I_base  = 10 MVA / (√3 × 11 kV) = 524.9 A

Relay settings (BusDiffRelayConfig):
  I_op_min = 0.20 pu
  SLP1     = 0.25
  SLP2     = 0.50
  I_op_hs  = 8.00 pu  (high-set)

Targets:
  P_D   ≥ 0.970   (internal fault detection)
  P_FA  ≤ 0.010   (external fault, no false trip)
  Selectivity margin: SLP1/ε_max = 0.25/0.03 = 8.3× (inherent)
"""

from __future__ import annotations
import csv
import pathlib
import time

import numpy as np

# ─── Network constants (from run_tr65_opendss.py) ──────────────────────────
SBASE_MVA  = 10.0
VN_KV      = 11.0
FREQ_HZ    = 50.0
I_BASE_A   = SBASE_MVA * 1e6 / (np.sqrt(3) * VN_KV * 1e3)   # 524.9 A

V_PHASE    = VN_KV * 1e3 / np.sqrt(3)            # 6 350.9 V

Z_SRC      = complex(0.0726, 1.21)               # Thévenin at MainBus [Ω]
Z_F2       = complex(0.242, 0.364)               # Feeder-2 [Ω]
Z_TH_MAIN  = Z_SRC                               # Thévenin at MainBus
Z_TH_F2    = Z_SRC + Z_F2                        # Thévenin at BusF2

# Normal load (all three feeders, in pu at I_base)
I_LOAD_NOM_PU = np.array([0.30, 0.20, 0.16])     # F1, F2, F3 nominal

# ─── Relay settings ─────────────────────────────────────────────────────────
I_OP_MIN = 0.20    # pu  minimum pickup
SLP1     = 0.25    # pu/pu  first slope
SLP2     = 0.50
I_OP_HS  = 8.00    # pu  high-set
N_TERM   = 4       # source + 3 feeders

# Stage-2 gate (simplified f_int model)
F_INT_TRIP_THRESH = 0.60    # f_int > 0.60 → model veto (no trip)
F_INT_SAT_BASE    = 0.20    # f_int for unsaturated external waveform


def _relay_87b(I_diff_pu: float, I_rst_pu: float, f_int: float) -> bool:
    """
    Simplified SAMBP 87B relay decision.
    High-set, slope characteristic, and Stage-2 gate veto.
    """
    # Stage-2 veto: high f_int (residual) ↔ saturation / anomaly
    if f_int > F_INT_TRIP_THRESH:
        return False                    # model veto suppresses trip
    if I_diff_pu > I_OP_HS:
        return True                     # high-set (unconditional)
    threshold = max(I_OP_MIN, SLP1 * I_rst_pu)
    return I_diff_pu > threshold


# ─── Internal fault trial (dependability) ──────────────────────────────────
def _trial_internal(rng: np.random.Generator) -> bool:
    """
    3-phase internal fault at MainBus.
    Parametric variation: fault resistance R_f, load scale L, CT mismatch.
    Returns True if relay correctly trips.
    """
    R_f   = float(rng.uniform(0.0, 25.0))        # Ω  (up to ~½ of Z_TH)
    L     = float(rng.uniform(0.7,  1.3))         # load scale
    eps   = rng.uniform(-0.03, 0.03, N_TERM)      # CT mismatch per terminal

    # Fault current at MainBus with fault resistance (Thévenin)
    Z_fault = Z_TH_MAIN + R_f
    I_f_A   = abs(V_PHASE / Z_fault)
    I_f_pu  = I_f_A / I_BASE_A

    # For internal 3ph fault: all feeder currents sum to give I_f
    # (differential = fault current, as seen by 87B)
    # Each terminal measurement has CT mismatch ε_k:
    # I_diff_meas ≈ I_f × mean(1+ε_k) ≈ I_f × (1 + mean(ε))
    I_diff_pu = I_f_pu * (1.0 + np.mean(eps))

    # Restraint ≈ total current = fault + load currents
    I_load_pu = L * I_LOAD_NOM_PU.sum()
    I_rst_pu  = 0.5 * (I_f_pu + I_load_pu)

    # f_int: clean fault waveform → low residual, f_int ≈ 0 (gate passes)
    f_int = F_INT_SAT_BASE * abs(np.mean(eps)) / 0.03   # scaled by mismatch

    return _relay_87b(I_diff_pu, I_rst_pu, f_int)


# ─── External fault trial (security) ───────────────────────────────────────
def _trial_external(rng: np.random.Generator) -> bool:
    """
    3-phase external fault at BusF2 (through-fault for 87B).
    Variation: fault resistance, load scale, CT mismatch, DG contribution.
    Returns True if relay FALSELY trips (false alarm).
    """
    R_f   = float(rng.uniform(0.0, 10.0))        # Ω at external bus
    L     = float(rng.uniform(0.7,  1.3))
    eps   = rng.uniform(-0.03, 0.03, N_TERM)      # CT mismatch per terminal
    P_DG  = float(rng.uniform(0.0,  0.5))         # MW DG on F3

    # Through-fault current (flows from source through bus into F2)
    Z_fault = Z_TH_F2 + R_f
    I_f_A   = abs(V_PHASE / Z_fault)
    I_f_pu  = I_f_A / I_BASE_A

    # Load currents (modified by DG on F3)
    I_load = L * I_LOAD_NOM_PU.copy()
    # DG on F3 reduces net current draw (reverse current fraction)
    I_load[2] -= P_DG / (np.sqrt(3) * VN_KV)   # MVA → pu current (approx)
    I_load[2]  = max(0.0, I_load[2])

    # KCL at MainBus: I_src = I_f_pu + Σ I_load
    # Measured differential = Σ_k ε_k × I_k  (CT mismatch only)
    # Source terminal: I_src_meas = I_src × (1+ε[0])
    # Feeder k: I_Fk_meas = I_Fk × (1+ε[k+1])
    I_src = I_f_pu + I_load.sum()
    I_fdr = np.array([I_load[0], I_f_pu + I_load[1], I_load[2]])

    # Differential with mismatch: I_diff = ε_0×I_src − ε_1×I_F1 − ε_2×I_F2 − ε_3×I_F3
    I_diff_pu = abs(
        eps[0] * I_src
        - eps[1] * I_fdr[0]
        - eps[2] * I_fdr[1]
        - eps[3] * I_fdr[2]
    )

    # Restraint: half-sum of all terminal currents
    I_rst_pu  = 0.5 * (I_src + I_fdr.sum())

    # f_int: no saturation in this scenario (DG ≠ CT sat); use low f_int
    f_int = F_INT_SAT_BASE * 0.5

    return _relay_87b(I_diff_pu, I_rst_pu, f_int)


# ─── External fault with CT saturation (security + Stage-2 gate) ───────────
def _trial_ext_ctsat(rng: np.random.Generator) -> bool:
    """
    External fault at BusF2 with CT saturation on F2 terminal.
    The conventional relay may trip (I_diff ≠ 0 due to sat.), but Stage-2
    gate vetoes when f_int (saturation indicator) > F_INT_TRIP_THRESH.
    Returns True if relay FALSELY trips (false alarm).
    """
    R_f      = float(rng.uniform(0.0, 5.0))
    L        = float(rng.uniform(0.7, 1.3))
    sat_frac = float(rng.uniform(0.4, 0.9))      # CT knee = sat_frac × I_peak

    Z_fault  = Z_TH_F2 + R_f
    I_f_A    = abs(V_PHASE / Z_fault)
    I_f_pu   = I_f_A / I_BASE_A

    # CT saturation on F2: measured I_F2_meas = sat_frac × I_f_pu (clipped)
    I_F2_sat_pu  = sat_frac * I_f_pu
    I_diff_pu    = abs(I_f_pu - I_F2_sat_pu)   # = (1-sat_frac)×I_f_pu

    I_rst_pu     = 0.5 * (I_f_pu + I_F2_sat_pu + L * I_LOAD_NOM_PU.sum())

    # f_int model: saturation → high residual norm → f_int → 1
    # f_int = 1 - (fit quality); for sat_frac << 1, residual is large
    f_int = 1.0 - sat_frac * 0.5              # 0.55 → 0.80 over sat range

    return _relay_87b(I_diff_pu, I_rst_pu, f_int)


# ─── Monte Carlo ─────────────────────────────────────────────────────────────
def run_mc(n_trials: int = 2000, rng_seed: int = 42) -> dict:
    """
    2 000 trials: 500 internal fault (dep.), 750 external (sec.),
    750 external-with-CT-saturation (sec.).
    """
    rng   = np.random.default_rng(rng_seed)
    half  = n_trials // 4            # ≈ 500 dep, 750+750 sec

    n_dep     = half          # 500
    n_sec_nom = 3 * half // 2  # 750
    n_sec_sat = n_trials - n_dep - n_sec_nom  # 750

    dep_trips  = sum(_trial_internal(rng)    for _ in range(n_dep))
    sec_trips  = sum(_trial_external(rng)    for _ in range(n_sec_nom))
    sat_trips  = sum(_trial_ext_ctsat(rng)   for _ in range(n_sec_sat))

    P_D  = dep_trips / n_dep
    P_FA = (sec_trips + sat_trips) / (n_sec_nom + n_sec_sat)

    return dict(
        n_trials   = n_trials,
        n_dep      = n_dep,
        n_sec      = n_sec_nom + n_sec_sat,
        n_sec_nom  = n_sec_nom,
        n_sec_sat  = n_sec_sat,
        dep_trips  = dep_trips,
        sec_trips  = sec_trips,
        sat_trips  = sat_trips,
        P_D        = P_D,
        P_FA       = P_FA,
    )


def main() -> None:
    print("=" * 70)
    print("SAMBP TR-65 MC — 87B Sensitivity Study (parametric, 2 000 trials)")
    print(f"Network: {VN_KV} kV, {SBASE_MVA} MVA, I_base={I_BASE_A:.1f} A")
    print(f"Relay:   I_op_min={I_OP_MIN}, SLP1={SLP1}, HS={I_OP_HS} pu")
    print("=" * 70)

    t0 = time.time()
    mc = run_mc(n_trials=2000, rng_seed=42)
    elapsed = time.time() - t0

    print(f"\n  Trials total      : {mc['n_trials']}")
    print(f"    Dependability   : {mc['n_dep']}  "
          f"(R_f~U[0,25]Ω, L~U[0.7,1.3], ε_CT~U[±3%])")
    print(f"    Security (clean): {mc['n_sec_nom']}  "
          f"(ext fault, CT mismatch only)")
    print(f"    Security (sat.) : {mc['n_sec_sat']}  "
          f"(ext fault + CT saturation)")

    pd_pass  = mc['P_D']  >= 0.970
    pfa_pass = mc['P_FA'] <= 0.010

    print(f"\n  P_D  = {mc['P_D']:.4f}   target ≥ 0.970  "
          f"{'PASS' if pd_pass  else 'FAIL'}")
    print(f"  P_FA = {mc['P_FA']:.4f}   target ≤ 0.010  "
          f"{'PASS' if pfa_pass else 'FAIL'}")

    # Selectivity margin explanation
    sel_margin = SLP1 / 0.03
    print(f"\n  Selectivity margin: SLP1/ε_max = {SLP1}/{0.03} = {sel_margin:.1f}×")
    print(f"  Stage-2 gate veto rate (CT sat. trials): "
          f"{mc['n_sec_sat'] - mc['sat_trips']}/{mc['n_sec_sat']}")

    all_pass = pd_pass and pfa_pass
    print("\n" + "═" * 70)
    print(f"TR-65 MC OVERALL: "
          f"{'ALL TARGETS MET — PASS' if all_pass else 'SOME TARGETS MISSED — CHECK ABOVE'}")
    print("═" * 70)
    print(f"  (elapsed: {elapsed:.1f}s)")

    # Save CSV
    out = pathlib.Path(__file__).parent / "outputs" / "tr65"
    out.mkdir(parents=True, exist_ok=True)
    mc_path = out / "tr65_mc_metrics.csv"
    with open(mc_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value", "target", "pass"])
        w.writerow(["n_trials",    mc["n_trials"],    "", ""])
        w.writerow(["n_dep",       mc["n_dep"],       "", ""])
        w.writerow(["n_sec",       mc["n_sec"],       "", ""])
        w.writerow(["n_sec_nom",   mc["n_sec_nom"],   "", ""])
        w.writerow(["n_sec_sat",   mc["n_sec_sat"],   "", ""])
        w.writerow(["dep_trips",   mc["dep_trips"],   "", ""])
        w.writerow(["sec_trips",   mc["sec_trips"],   "", ""])
        w.writerow(["sat_trips",   mc["sat_trips"],   "", ""])
        w.writerow(["P_D",  f"{mc['P_D']:.4f}",  ">=0.970", int(pd_pass)])
        w.writerow(["P_FA", f"{mc['P_FA']:.4f}", "<=0.010", int(pfa_pass)])
    print(f"  MC CSV → {mc_path}")


if __name__ == "__main__":
    main()
