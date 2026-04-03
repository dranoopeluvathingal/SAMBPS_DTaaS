"""
run_transient_diff_study.py
============================
SAMBP TR-23/2026 — Transient Differential Current Supervision (TDCS-87L)
for symmetric 3-phase IBR faults below the conventional 87L threshold.

Extends TR-22 (87L + 87LN) by adding TDCS-87L as a third trip path:
    TRIP = 87L  ∨  87LN  ∨  TDCS-87L

Study overview
--------------
Evaluates TDCS-87L across:

  Study A: 3PH internal fault at seven IBR limit levels (k_ibr):
           0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.15 pu
           → Faults at k_ibr ≥ 0.08 pu: 87L OR TDCS trips
           → Fault at k_ibr = 0.07 pu: TDCS trips (87L misses)
           Target: 7/7

  Study B: Balanced load step (0.10–0.50 pu step): no differential created
           → TDCS must NOT trip (security)
           Target: 7/7 no false trips

  Study C: External fault (through-current 1–5 pu): CT mismatch residual only
           → TDCS must NOT trip (security)
           Target: 7/7 no false trips

Combined TR-22+TR-23 metric:
    Baseline (87L only) from TR-22 grid: 12/21
    TR-22 (87L + 87LN):                  17/21
    TR-23 (87L + 87LN + TDCS):           21/21 (target)

TDCS detection limit:
    Effective peak detection: k_ibr ≥ (Δ_thr + rms_pre) × √2 ≈ 0.060 pu
    At 0.07 pu: ΔI_rms = 0.047 > Δ_thr=0.040 → trip ✓
"""

from __future__ import annotations

import sys
import os
import csv
import numpy as np

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
HERE      = os.path.dirname(os.path.abspath(__file__))
SAMBP_DIR = os.path.dirname(HERE)
REPO_DIR  = os.path.dirname(SAMBP_DIR)
for p in [HERE, SAMBP_DIR, REPO_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from sambp_line_diff.models.line_transient_diff import (
    TDCSConfig,
    measure_tdcs,
    make_prefault_diff,
    make_3ph_internal_diff,
    make_load_step_diff,
    make_external_fault_diff,
)

# ---------------------------------------------------------------------------
# Study constants
# ---------------------------------------------------------------------------

FS     = 4000.0
F_NOM  = 50.0
N      = int(FS / F_NOM)    # 1 cycle = 80 samples

I_THRESHOLD  = 0.12         # 87L trip threshold [pu]
I2_THRESHOLD = 0.06         # 87LN trip threshold [pu]  (from TR-22)
I_C_PRE      = 0.003        # Pre-fault charging residual [pu]

CFG = TDCSConfig(delta_thr=0.040, noise_floor=0.010, fs=FS)

# k_ibr levels: cover the 4 TR-22 missed 3PH cases + margins
K_IBR_LEVELS  = [0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.15]
LOAD_LEVELS   = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
EXTERN_LEVELS = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0]

OUT_DIR = os.path.join(HERE, "results_tr23")
os.makedirs(OUT_DIR, exist_ok=True)

# Pre-fault window (shared for all scenarios)
I_PRE_WINDOW = make_prefault_diff(I_C_PRE, F_NOM, FS, N)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _87L_trip(I_fund_post: float) -> bool:
    return I_fund_post >= I_THRESHOLD

def _87LN_trip(I2_post: float) -> bool:
    return I2_post >= I2_THRESHOLD

def _save_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


# ---------------------------------------------------------------------------
# Study A: 3PH internal fault at various k_ibr
# ---------------------------------------------------------------------------

def study_a_3ph() -> list[dict]:
    print("\n=== Study A: 3PH symmetric fault (k_ibr varied) ===")
    results = []

    hdr = (f"{'k_ibr':>6} {'I1_post':>8} {'87L':>5} {'ΔI_rms':>8} "
           f"{'TDCS':>6} {'comb':>6} {'ok':>5}")
    print(hdr)
    print("-" * len(hdr))

    for k in K_IBR_LEVELS:
        i_post = make_3ph_internal_diff(k, F_NOM, FS, N)
        r = measure_tdcs(I_PRE_WINDOW, i_post, CFG)

        # 87L (standard positive-seq threshold on post-fault RMS peak)
        I1_post = float(np.max(np.abs(i_post)))  # peak per phase
        t87L = _87L_trip(I1_post)
        # 87LN: 3PH symmetric → I2 = 0 → no 87LN trip
        t87LN = False
        # Combined
        t_comb = t87L or t87LN or r.trip_tdcs

        expect = True
        ok = (t_comb == expect)
        flag = "PASS" if ok else "FAIL"
        trip87 = "YES" if t87L else " no"
        tdcs  = "YES" if r.trip_tdcs else " no"
        tc    = "YES" if t_comb else " no"
        print(f"{k:6.2f} {I1_post:8.5f} {trip87:>5} {r.delta_I:8.5f} "
              f"{tdcs:>6} {tc:>6} {flag:>5}")
        results.append({
            "study": "A_3ph", "k_ibr": k, "I1_post": I1_post,
            "trip_87L": t87L, "trip_87LN": t87LN,
            "delta_I": r.delta_I, "rms_post": r.rms_post,
            "trip_tdcs": r.trip_tdcs, "trip_combined": t_comb,
            "correct": ok,
        })
    return results


# ---------------------------------------------------------------------------
# Study B: Balanced load step (security)
# ---------------------------------------------------------------------------

def study_b_load_step() -> list[dict]:
    print("\n=== Study B: Balanced load step security (ΔI_diff ≈ 0) ===")
    results = []

    hdr = (f"{'ΔI_load':>8} {'ΔI_rms':>8} {'rms_post':>9} "
           f"{'TDCS':>6} {'ok':>5}")
    print(hdr)
    print("-" * len(hdr))

    for dI in LOAD_LEVELS:
        i_post = make_load_step_diff(dI, F_NOM, FS, N)
        r = measure_tdcs(I_PRE_WINDOW, i_post, CFG)
        ok = not r.trip_tdcs
        flag = "PASS" if ok else "FAIL"
        tdcs = "YES" if r.trip_tdcs else " no"
        print(f"{dI:8.2f} {r.delta_I:8.5f} {r.rms_post:9.5f} "
              f"{tdcs:>6} {flag:>5}")
        results.append({
            "study": "B_load", "k_ibr": dI,
            "delta_I": r.delta_I, "rms_post": r.rms_post,
            "trip_tdcs": r.trip_tdcs, "correct": ok,
        })
    return results


# ---------------------------------------------------------------------------
# Study C: External fault through-current (security)
# ---------------------------------------------------------------------------

def study_c_external() -> list[dict]:
    print("\n=== Study C: External fault through-current (CT mismatch residual) ===")
    results = []

    hdr = (f"{'I_ext':>7} {'ΔI_rms':>8} {'rms_post':>9} "
           f"{'TDCS':>6} {'ok':>5}")
    print(hdr)
    print("-" * len(hdr))

    for I_ext in EXTERN_LEVELS:
        i_post = make_external_fault_diff(I_ext, F_NOM, FS, N)
        r = measure_tdcs(I_PRE_WINDOW, i_post, CFG)
        ok = not r.trip_tdcs
        flag = "PASS" if ok else "FAIL"
        tdcs = "YES" if r.trip_tdcs else " no"
        print(f"{I_ext:7.1f} {r.delta_I:8.5f} {r.rms_post:9.5f} "
              f"{tdcs:>6} {flag:>5}")
        results.append({
            "study": "C_ext", "k_ibr": I_ext,
            "delta_I": r.delta_I, "rms_post": r.rms_post,
            "trip_tdcs": r.trip_tdcs, "correct": ok,
        })
    return results


# ---------------------------------------------------------------------------
# Study D: Summary — cumulative improvement from TR-22 + TR-23
# ---------------------------------------------------------------------------

def study_d_summary(ra, rb, rc):
    print("\n=== Study D: Cumulative selectivity summary ===")
    all_res = ra + rb + rc
    n = len(all_res)

    n_ok = sum(r["correct"] for r in all_res)
    n_ok_a = sum(r["correct"] for r in ra)
    n_ok_b = sum(r["correct"] for r in rb)
    n_ok_c = sum(r["correct"] for r in rc)

    # 3PH faults recovered by TDCS vs 87L
    n_87L_only = sum(r["trip_87L"] for r in ra if "trip_87L" in r)
    n_tdcs_save = sum(
        r["trip_tdcs"] and not r["trip_87L"]
        for r in ra if "trip_87L" in r
    )

    print(f"  Study A (3PH fault):  {n_ok_a}/{len(ra)}  "
          f"({n_87L_only} via 87L, {n_tdcs_save} via TDCS only)")
    print(f"  Study B (load step):  {n_ok_b}/{len(rb)}")
    print(f"  Study C (ext fault):  {n_ok_c}/{len(rc)}")
    print(f"  TR-23 total:          {n_ok}/{n}")
    print()
    print(f"  Cumulative improvement (TR-22 baseline = 17/21):")
    print(f"    TR-22 (87L + 87LN): 17/21")
    print(f"    TR-23 (+ TDCS-87L): {n_ok}/{n}")

    return n_ok, n


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 66)
    print("SAMBP TR-23/2026 — Transient Differential (TDCS-87L) Study")
    print("=" * 66)
    print(f"  TDCS Δ_thr = {CFG.delta_thr} pu  noise_floor = {CFG.noise_floor} pu")
    print(f"  87L  thr   = {I_THRESHOLD} pu")
    print(f"  87LN thr   = {I2_THRESHOLD} pu")

    ra = study_a_3ph()
    rb = study_b_load_step()
    rc = study_c_external()
    n_ok, n = study_d_summary(ra, rb, rc)

    fields = ["study", "k_ibr", "delta_I", "rms_post", "trip_tdcs", "correct"]
    _save_csv(os.path.join(OUT_DIR, "tr23_results.csv"), ra + rb + rc, fields)
    print(f"\n  Results saved to {OUT_DIR}/")

    print()
    if n_ok == n:
        print(f"RESULT: {n_ok}/{n} correct (100%) — TDCS completes 3PH IBR protection gap")
    else:
        print(f"RESULT: {n_ok}/{n} — SOME FAILURES")
        sys.exit(1)
