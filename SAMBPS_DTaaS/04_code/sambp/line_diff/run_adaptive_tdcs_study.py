"""
run_adaptive_tdcs_study.py
==========================
SAMBP TR-24/2026 — Adaptive TDCS Threshold Study.

Demonstrates that a fixed TDCS threshold (TR-23, Δ_thr = 0.040 pu) can miss
internal faults when the pre-fault differential baseline has drifted upward
(e.g., CT calibration ageing, seasonal charging increase) and that the
adaptive threshold (TR-24) restores detection.

Study design
------------
Four seasonal/operational scenarios characterised by different rolling
pre-fault RMS distributions:

  S1 — Summer nominal    : μ_pre = 0.002 pu, σ_pre = 0.0003 pu
  S2 — Winter high-load  : μ_pre = 0.003 pu, σ_pre = 0.0005 pu
  S3 — Spring light-load : μ_pre = 0.006 pu, σ_pre = 0.0012 pu
  S4 — Drift (aged CT)   : μ_pre = 0.015 pu, σ_pre = 0.0020 pu  ← critical

For each scenario: 3 k_ibr values in the TDCS-only recovery range (0.07,
0.09, 0.11 pu) → 12 internal-fault detection cases.
Security: 7 external fault cases matching TR-23 Study C.

Expected result
---------------
  Fixed threshold:    11/12 detection (misses S4 × k_ibr=0.07)
                       7/7  security
  Adaptive threshold: 12/12 detection
                       7/7  security
"""

from __future__ import annotations

import sys
import os
import numpy as np

# ---------------------------------------------------------------------------
# Path setup — allows running directly: python run_adaptive_tdcs_study.py
# ---------------------------------------------------------------------------
HERE      = os.path.dirname(os.path.abspath(__file__))
SAMBP_DIR = os.path.dirname(HERE)
REPO_DIR  = os.path.dirname(SAMBP_DIR)
for p in [HERE, SAMBP_DIR, REPO_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from sambp_line_diff.models.line_transient_diff import (
    TDCSConfig,
    AdaptiveTDCSConfig,
    AdaptiveTDCSTracker,
    make_prefault_diff,
    make_3ph_internal_diff,
    make_external_fault_diff,
    measure_tdcs,
    _window_rms,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FS     = 4000.0          # Sampling rate [Hz]
F0     = 50.0            # Nominal frequency [Hz]
N_SAMP = int(FS / F0)    # Samples per cycle = 80

CFG_FIXED    = TDCSConfig(delta_thr=0.040)
CFG_ADAPTIVE = AdaptiveTDCSConfig(delta_floor=0.025, k_sigma=3.0)

# ---------------------------------------------------------------------------
# Seasonal scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS = [
    {"label": "S1 Summer nominal",    "mu": 0.002, "sigma": 0.0003, "color": "summer"},
    {"label": "S2 Winter high-load",  "mu": 0.003, "sigma": 0.0005, "color": "winter"},
    {"label": "S3 Spring light-load", "mu": 0.006, "sigma": 0.0012, "color": "spring"},
    {"label": "S4 Drift (aged CT)",   "mu": 0.015, "sigma": 0.0020, "color": "drift"},
]

K_IBR_VALUES = [0.07, 0.09, 0.11]   # pu — TDCS-only recovery range

# External security: same through-current levels as TR-23 Study C
EXT_CURRENTS = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0]   # pu


# ---------------------------------------------------------------------------
# Build adaptive tracker for a scenario
# ---------------------------------------------------------------------------

def build_tracker(mu: float, sigma: float, seed: int = 42) -> AdaptiveTDCSTracker:
    """
    Simulate 60 cycles of normal operation to populate the rolling history.
    """
    rng     = np.random.default_rng(seed)
    samples = rng.normal(loc=mu, scale=sigma, size=60)
    tracker = AdaptiveTDCSTracker(CFG_ADAPTIVE)
    for s in samples:
        tracker.update_baseline(max(s, 0.0))
    return tracker


# ---------------------------------------------------------------------------
# Study A: Internal fault detection (12 cases)
# ---------------------------------------------------------------------------

def run_study_a() -> list[dict]:
    """4 scenarios × 3 k_ibr → 12 detection cases."""
    results = []
    for sc in SCENARIOS:
        tracker = build_tracker(sc["mu"], sc["sigma"])
        i_pre   = make_prefault_diff(sc["mu"], F0, FS, N_SAMP)

        for k in K_IBR_VALUES:
            i_post = make_3ph_internal_diff(k, F0, FS, N_SAMP)

            # Fixed threshold
            r_f = measure_tdcs(i_pre, i_post, CFG_FIXED)

            # Adaptive threshold
            r_a = tracker.measure(i_post)

            results.append({
                "scenario": sc["label"],
                "mu_pre":   sc["mu"],
                "k_ibr":    k,
                "rms_post": r_a.rms_post,
                "delta_I_fixed":  r_f.delta_I,
                "delta_I_adapt":  r_a.delta_I,
                "thr_fixed":      CFG_FIXED.delta_thr,
                "thr_adapt":      r_a.delta_thr,
                "trip_fixed":     r_f.trip_tdcs,
                "trip_adapt":     r_a.trip_tdcs,
                "expect":         True,
            })
    return results


# ---------------------------------------------------------------------------
# Study B: External fault security (7 × 4 scenarios = 28 cases)
# ---------------------------------------------------------------------------

def run_study_b() -> list[dict]:
    """External fault security across all scenarios and current levels."""
    results = []
    for sc in SCENARIOS:
        tracker = build_tracker(sc["mu"], sc["sigma"])
        i_pre   = make_prefault_diff(sc["mu"], F0, FS, N_SAMP)

        for I_ext in EXT_CURRENTS:
            i_post = make_external_fault_diff(I_ext, F0, FS, N_SAMP)

            r_f = measure_tdcs(i_pre, i_post, CFG_FIXED)
            r_a = tracker.measure(i_post)

            ct_mismatch_rms = I_ext * 0.005 / np.sqrt(2)

            results.append({
                "scenario": sc["label"],
                "mu_pre":   sc["mu"],
                "I_ext":    I_ext,
                "ct_rms":   ct_mismatch_rms,
                "delta_I_fixed": r_f.delta_I,
                "delta_I_adapt": r_a.delta_I,
                "thr_fixed":     CFG_FIXED.delta_thr,
                "thr_adapt":     r_a.delta_thr,
                "trip_fixed":    r_f.trip_tdcs,
                "trip_adapt":    r_a.trip_tdcs,
                "expect":        False,
            })
    return results


# ---------------------------------------------------------------------------
# Study C: Threshold-tracking illustration (for figure)
# ---------------------------------------------------------------------------

def run_study_c() -> dict:
    """
    Show how Δ_thr_adaptive evolves as the pre-fault baseline drifts from
    μ=0.002 pu (summer) to μ=0.015 pu (aged CT) over 120 simulated cycles.
    """
    rng = np.random.default_rng(7)

    # Simulate drift: linear ramp in mean over 120 cycles
    mu_start, mu_end = 0.002, 0.015
    sigma            = 0.0012   # growing noise during drift
    n_cycles         = 120
    mu_ramp          = np.linspace(mu_start, mu_end, n_cycles)

    samples   = np.array([
        max(rng.normal(loc=mu_ramp[i], scale=sigma), 0.0)
        for i in range(n_cycles)
    ])

    tracker   = AdaptiveTDCSTracker(AdaptiveTDCSConfig(delta_floor=0.025, k_sigma=3.0))
    thr_track = []
    mu_track  = []
    sig_track = []

    for s in samples:
        tracker.update_baseline(s)
        thr_track.append(tracker.delta_thr_adaptive)
        mu_track.append(tracker.mu_pre)
        sig_track.append(tracker.sigma_pre)

    return {
        "cycles":    np.arange(n_cycles),
        "samples":   samples,
        "thr_adapt": np.array(thr_track),
        "mu_hat":    np.array(mu_track),
        "sigma_hat": np.array(sig_track),
        "thr_fixed": np.full(n_cycles, CFG_FIXED.delta_thr),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_study_a(results: list[dict]) -> None:
    print("=" * 80)
    print("STUDY A — Internal fault detection (12 cases)")
    print("=" * 80)
    hdr = (f"{'Scenario':<28} {'k_ibr':>5} {'rms_post':>9} "
           f"{'ΔI_fix':>7} {'thr_fix':>7} {'F':>4} "
           f"{'ΔI_ada':>7} {'thr_ada':>8} {'A':>4} {'OK?':>5}")
    print(hdr)
    print("-" * 100)

    n_pass_f = n_pass_a = 0
    for r in results:
        ok_f = (r["trip_fixed"] == r["expect"])
        ok_a = (r["trip_adapt"] == r["expect"])
        if ok_f:
            n_pass_f += 1
        if ok_a:
            n_pass_a += 1
        note = "" if (ok_f and ok_a) else " ← FIXED MISS" if (not ok_f and ok_a) else " FAIL"
        print(f"{r['scenario']:<28} {r['k_ibr']:>5.2f} {r['rms_post']:>9.5f} "
              f"{r['delta_I_fixed']:>7.5f} {r['thr_fixed']:>7.4f} "
              f"{'Y' if r['trip_fixed'] else 'n':>4} "
              f"{r['delta_I_adapt']:>7.5f} {r['thr_adapt']:>8.5f} "
              f"{'Y' if r['trip_adapt'] else 'n':>4} {note}")

    print()
    print(f"  Fixed threshold : {n_pass_f:2d}/12 correct")
    print(f"  Adaptive        : {n_pass_a:2d}/12 correct")


def print_study_b(results: list[dict]) -> None:
    print()
    print("=" * 80)
    print("STUDY B — External fault security (28 cases, 4 scenarios × 7 currents)")
    print("=" * 80)

    n_pass_f = n_pass_a = 0
    for r in results:
        ok_f = (r["trip_fixed"] == r["expect"])
        ok_a = (r["trip_adapt"] == r["expect"])
        if ok_f:
            n_pass_f += 1
        if ok_a:
            n_pass_a += 1

    print(f"  Fixed threshold : {n_pass_f:2d}/28 secure (no false trips)")
    print(f"  Adaptive        : {n_pass_a:2d}/28 secure (no false trips)")

    # Show worst-case margin for S4 scenario
    s4_worst = [r for r in results if "Drift" in r["scenario"] and r["I_ext"] == 7.0]
    if s4_worst:
        r = s4_worst[0]
        margin_a = (r["thr_adapt"] - r["delta_I_adapt"]) / r["thr_adapt"] * 100
        margin_f = (r["thr_fixed"] - r["delta_I_fixed"]) / r["thr_fixed"] * 100
        print(f"\n  Worst case: S4 × I_ext=7 pu (CT mismatch 0.5%):")
        print(f"    ΔI_diff = {r['delta_I_adapt']:.5f} pu  "
              f"|  Δ_thr_adapt = {r['thr_adapt']:.5f} pu  "
              f"(margin {margin_a:.1f}%)")
        print(f"    ΔI_diff = {r['delta_I_fixed']:.5f} pu  "
              f"|  Δ_thr_fixed = {r['thr_fixed']:.4f} pu  "
              f"(margin {margin_f:.1f}%)")


def print_summary(res_a: list[dict], res_b: list[dict]) -> None:
    n_a_f = sum(1 for r in res_a if r["trip_fixed"] == r["expect"])
    n_a_a = sum(1 for r in res_a if r["trip_adapt"] == r["expect"])
    n_b_f = sum(1 for r in res_b if r["trip_fixed"] == r["expect"])
    n_b_a = sum(1 for r in res_b if r["trip_adapt"] == r["expect"])

    total = len(res_a) + len(res_b)
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'':30} {'Fixed':>10} {'Adaptive':>10}")
    print(f"  Detection  (Study A, 12 cases)  {n_a_f:>8d}   {n_a_a:>8d}")
    print(f"  Security   (Study B, 28 cases)  {n_b_f:>8d}   {n_b_a:>8d}")
    print(f"  Total      ({total} cases)         "
          f"{n_a_f+n_b_f:>8d}   {n_a_a+n_b_a:>8d}")

    # Verify expected outcome
    assert n_a_f == 11, f"Expected fixed=11/12, got {n_a_f}"
    assert n_a_a == 12, f"Expected adaptive=12/12, got {n_a_a}"
    assert n_b_f == 28, f"Expected fixed=28/28 secure, got {n_b_f}"
    assert n_b_a == 28, f"Expected adaptive=28/28 secure, got {n_b_a}"
    print("\n  ALL ASSERTIONS PASSED — results consistent with TR-24 specification.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    res_a = run_study_a()
    res_b = run_study_b()
    _     = run_study_c()    # computed for figure generation; values printed in report

    print_study_a(res_a)
    print_study_b(res_b)
    print_summary(res_a, res_b)
