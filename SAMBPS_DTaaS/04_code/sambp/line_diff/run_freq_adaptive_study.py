"""
run_freq_adaptive_study.py
===========================
SAMBP TR-20/2026 — Frequency-adaptive 87L charging correction for microgrids.

Study overview
--------------
Evaluates the SAMBP 87L differential element at seven off-nominal frequencies
(47, 48, 49, 50, 51, 52, 53 Hz) for three scenarios:

  A. No-fault, healthy line — residual charging error (false-trip risk)
  B. Internal fault (I_fault = 0.15 pu at f_actual) — detection margin
  C. External fault (I_fault = 0 in zone, current through but balanced) — security

For each scenario the study compares:
  • Fixed correction (TR-15): B_C used at 50 Hz regardless of actual f
  • Adaptive correction (TR-20): B_C × (f_est / f_nom)

Metrics
-------
  eps_rms  : RMS residual after correction [pu]
  alpha50  : normalised α₅₀ = eps_rms / I_nom (false-trip metric, want < 0.03)
  margin   : (I_diff_corrected − I_threshold) / I_threshold (detection margin)
  trip     : bool — corrected differential exceeds threshold (0.12 pu)
"""

from __future__ import annotations

import sys
import os
import csv
import numpy as np
from scipy.signal import hilbert

# ---------------------------------------------------------------------------
# Path bootstrap (resolve package structure)
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
SAMBP_ROOT = os.path.dirname(HERE)
REPO_ROOT  = os.path.dirname(SAMBP_ROOT)
for p in [HERE, SAMBP_ROOT, REPO_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from sambp_line_diff.adaptation.line_freq_adaptive import (
    FreqAdaptiveConfig,
    estimate_frequency_zero_crossing,
    adaptive_charging_correction,
    fixed_charging_correction,
    charging_residual_rms,
)


# ---------------------------------------------------------------------------
# Study constants
# ---------------------------------------------------------------------------

FS          = 4000.0      # Sampling rate [Hz] — 80 samples/cycle at 50 Hz
N_CYCLES    = 4           # Waveform window
B_C_NOM     = 0.079       # 132 kV, 20 km line [pu]  (= 2π×50×C_total)
V_NOM       = 1.0         # Nominal voltage [pu]
F_NOM       = 50.0        # Nominal frequency [Hz]
I_FAULT_PU  = 0.15        # Fault current amplitude [pu] (just above 0.12 threshold)
I_THRESHOLD = 0.12        # 87L trip threshold after correction [pu]
I_NOM       = 1.0         # Nominal line current [pu]

TEST_FREQS  = [47.0, 48.0, 49.0, 50.0, 51.0, 52.0, 53.0]

OUT_DIR = os.path.join(HERE, "results_tr20")
os.makedirs(OUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Waveform generators
# ---------------------------------------------------------------------------

def _three_phase(f: float, n: int, v_amp: float = V_NOM,
                 angle_offset: float = 0.0, phase_offset: float = 0.0,
                 mag_scale: float = 1.0) -> np.ndarray:
    """Generate balanced 3-phase sinusoidal waveform (3, N)."""
    t = np.arange(n) / FS
    phi0 = np.array([0.0, -2*np.pi/3, 2*np.pi/3])
    return np.array([
        v_amp * mag_scale * np.sin(2*np.pi*f*t + phi0[ph] + phase_offset)
        for ph in range(3)
    ])


def _true_charging(v_L: np.ndarray, v_R: np.ndarray,
                   f_actual: float) -> np.ndarray:
    """True pi-section charging at actual frequency (ground truth)."""
    freq_ratio = f_actual / F_NOM
    v_avg = 0.5 * (v_L + v_R)
    i_C = np.zeros_like(v_avg)
    for ph in range(3):
        i_C[ph] = B_C_NOM * freq_ratio * np.imag(hilbert(v_avg[ph]))
    return i_C


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------

def evaluate_scenario(f_actual: float, scenario: str) -> dict:
    """
    Run one (frequency, scenario) combination.

    Parameters
    ----------
    f_actual : actual system frequency [Hz]
    scenario : "no_fault" | "int_fault" | "ext_fault"

    Returns
    -------
    dict with keys: f_actual, scenario, f_est, status,
                    eps_fixed, eps_adapt, alpha50_fixed, alpha50_adapt,
                    trip_fixed, trip_adapt, correct
    """
    N = int(FS * N_CYCLES / F_NOM)   # constant sample count (at 50 Hz reference)

    # Voltages — local and remote, slight imbalance to be realistic
    v_L = _three_phase(f_actual, N, V_NOM, 0.0)
    v_R = _three_phase(f_actual, N, V_NOM, 0.0,
                       phase_offset=-0.03, mag_scale=0.98)  # slight sag

    # True charging at actual frequency
    i_C_true = _true_charging(v_L, v_R, f_actual)

    # Fault current contribution to i_diff
    t = np.arange(N) / FS
    phi0 = np.array([0.0, -2*np.pi/3, 2*np.pi/3])
    if scenario == "no_fault":
        i_fault_waveform = np.zeros((3, N))
    elif scenario == "int_fault":
        # Internal fault: I_fault appears in differential at actual frequency
        i_fault_waveform = np.array([
            I_FAULT_PU * np.sin(2*np.pi*f_actual*t + phi0[ph])
            for ph in range(3)
        ])
    else:  # ext_fault: external — perfectly balanced, no true differential
        i_fault_waveform = np.zeros((3, N))

    # Simulated measured differential = true charging + fault signal
    i_diff_meas = i_C_true + i_fault_waveform

    # Frequency estimation (zero-crossing on pre-fault = full v_L here)
    cfg = FreqAdaptiveConfig(f_nom=F_NOM, f_min=47.0, f_max=53.0)
    f_est, status = estimate_frequency_zero_crossing(v_L, FS, cfg)

    # Fixed correction (TR-15)
    i_C_fixed = fixed_charging_correction(v_L, v_R, B_C_NOM, F_NOM)
    i_diff_fixed = i_diff_meas - i_C_fixed

    # Adaptive correction (TR-20)
    i_C_adapt = adaptive_charging_correction(v_L, v_R, B_C_NOM, f_est, F_NOM)
    i_diff_adapt = i_diff_meas - i_C_adapt

    # Residual RMS (vs true fault current)
    eps_fixed = charging_residual_rms(i_diff_fixed, i_fault_waveform)
    eps_adapt = charging_residual_rms(i_diff_adapt, i_fault_waveform)

    # α₅₀ = residual / I_nom (false-trip normalised metric)
    alpha50_fixed = eps_fixed / I_NOM
    alpha50_adapt = eps_adapt / I_NOM

    # Peak |I_diff| per phase (max absolute value, then max across phases)
    def peak_abs(arr: np.ndarray) -> float:
        return float(np.max(np.abs(arr)))

    peak_fixed = peak_abs(i_diff_fixed)
    peak_adapt = peak_abs(i_diff_adapt)

    trip_fixed = peak_fixed >= I_THRESHOLD
    trip_adapt = peak_adapt >= I_THRESHOLD

    # Correctness: internal fault should trip, no-fault and ext should NOT
    expect_trip = (scenario == "int_fault")
    correct_fixed = (trip_fixed == expect_trip)
    correct_adapt = (trip_adapt == expect_trip)

    return {
        "f_actual":      f_actual,
        "scenario":      scenario,
        "f_est":         f_est,
        "status":        status,
        "eps_fixed":     eps_fixed,
        "eps_adapt":     eps_adapt,
        "alpha50_fixed": alpha50_fixed,
        "alpha50_adapt": alpha50_adapt,
        "peak_fixed":    peak_fixed,
        "peak_adapt":    peak_adapt,
        "trip_fixed":    trip_fixed,
        "trip_adapt":    trip_adapt,
        "correct_fixed": correct_fixed,
        "correct_adapt": correct_adapt,
        "improvement":   eps_fixed / (eps_adapt + 1e-12) if eps_fixed > 0 else None,
    }


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _save_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


# ---------------------------------------------------------------------------
# Study A: No-fault residual error vs frequency
# ---------------------------------------------------------------------------

def study_a_nofault_residual() -> list[dict]:
    print("\n=== Study A: No-fault residual error vs frequency ===")
    results = []
    header = (
        f"{'f[Hz]':>7} {'f_est':>6} {'eps_fixed':>12} {'eps_adapt':>12} "
        f"{'α₅₀_fix':>10} {'α₅₀_adp':>10} {'improv':>8} "
        f"{'fix_trip':>9} {'adp_trip':>9}"
    )
    print(header)
    print("-" * len(header))

    for f in TEST_FREQS:
        r = evaluate_scenario(f, "no_fault")
        impr = f"{r['improvement']:.0f}×" if r["improvement"] is not None else "  —"
        ft = "YES" if r["trip_fixed"] else " no"
        at = "YES" if r["trip_adapt"] else " no"
        print(f"{r['f_actual']:7.1f} {r['f_est']:6.2f} "
              f"{r['eps_fixed']:12.6f} {r['eps_adapt']:12.6f} "
              f"{r['alpha50_fixed']:10.6f} {r['alpha50_adapt']:10.6f} "
              f"{impr:>8} {ft:>9} {at:>9}")
        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Study B: Internal fault detection vs frequency
# ---------------------------------------------------------------------------

def study_b_internal_fault() -> list[dict]:
    print("\n=== Study B: Internal fault (0.15 pu) detection vs frequency ===")
    results = []
    header = (
        f"{'f[Hz]':>7} {'peak_fix':>10} {'peak_adp':>10} "
        f"{'trip_fix':>9} {'trip_adp':>9} {'ok_fix':>7} {'ok_adp':>7}"
    )
    print(header)
    print("-" * len(header))

    for f in TEST_FREQS:
        r = evaluate_scenario(f, "int_fault")
        of = "PASS" if r["correct_fixed"] else "FAIL"
        oa = "PASS" if r["correct_adapt"] else "FAIL"
        ft = "YES" if r["trip_fixed"] else " no"
        at = "YES" if r["trip_adapt"] else " no"
        print(f"{r['f_actual']:7.1f} {r['peak_fixed']:10.5f} {r['peak_adapt']:10.5f} "
              f"{ft:>9} {at:>9} {of:>7} {oa:>7}")
        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Study C: Security (external fault / no differential)
# ---------------------------------------------------------------------------

def study_c_security() -> list[dict]:
    print("\n=== Study C: Security (external fault, no true differential) ===")
    results = []
    header = (
        f"{'f[Hz]':>7} {'peak_fix':>10} {'peak_adp':>10} "
        f"{'trip_fix':>9} {'trip_adp':>9} {'ok_fix':>7} {'ok_adp':>7}"
    )
    print(header)
    print("-" * len(header))

    for f in TEST_FREQS:
        r = evaluate_scenario(f, "ext_fault")
        of = "PASS" if r["correct_fixed"] else "FAIL"
        oa = "PASS" if r["correct_adapt"] else "FAIL"
        ft = "YES" if r["trip_fixed"] else " no"
        at = "YES" if r["trip_adapt"] else " no"
        print(f"{r['f_actual']:7.1f} {r['peak_fixed']:10.5f} {r['peak_adapt']:10.5f} "
              f"{ft:>9} {at:>9} {of:>7} {oa:>7}")
        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Study D: Summary selectivity count
# ---------------------------------------------------------------------------

def study_d_summary(results_a, results_b, results_c) -> None:
    print("\n=== Study D: Selectivity summary ===")
    all_results = results_a + results_b + results_c
    n_total = len(all_results)

    n_ok_fixed = sum(r["correct_fixed"] for r in all_results)
    n_ok_adapt = sum(r["correct_adapt"] for r in all_results)

    print(f"  Fixed  (TR-15): {n_ok_fixed}/{n_total} correct")
    print(f"  Adaptive (TR-20): {n_ok_adapt}/{n_total} correct")
    print()

    # α₅₀ summary from study A
    print("  No-fault α₅₀ summary (threshold 0.030):")
    print(f"  {'f[Hz]':>6}  {'α₅₀_fixed':>12}  {'α₅₀_adapt':>12}  {'below_thr(adp)':>14}")
    for r in results_a:
        ok = "YES" if r["alpha50_adapt"] < 0.030 else " NO"
        print(f"  {r['f_actual']:6.1f}  {r['alpha50_fixed']:12.6f}  {r['alpha50_adapt']:12.6f}  {ok:>14}")

    return n_ok_fixed, n_ok_adapt, n_total


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 64)
    print("SAMBP TR-20/2026 — Frequency-Adaptive 87L Correction Study")
    print("=" * 64)

    results_a = study_a_nofault_residual()
    results_b = study_b_internal_fault()
    results_c = study_c_security()
    ret = study_d_summary(results_a, results_b, results_c)
    n_ok_fixed, n_ok_adapt, n_total = ret

    # Save CSVs
    fields_a = ["f_actual", "f_est", "status", "eps_fixed", "eps_adapt",
                "alpha50_fixed", "alpha50_adapt", "trip_fixed", "trip_adapt",
                "correct_fixed", "correct_adapt", "improvement"]
    _save_csv(os.path.join(OUT_DIR, "tr20_nofault.csv"), results_a, fields_a)

    fields_bc = ["f_actual", "f_est", "scenario", "peak_fixed", "peak_adapt",
                 "trip_fixed", "trip_adapt", "correct_fixed", "correct_adapt"]
    _save_csv(os.path.join(OUT_DIR, "tr20_fault.csv"), results_b + results_c, fields_bc)

    print(f"\n  Results saved to {OUT_DIR}/")

    # Final verdict
    print()
    if n_ok_adapt == n_total:
        print(f"RESULT: {n_ok_adapt}/{n_total} correct with adaptive correction (100%)")
    else:
        print(f"RESULT: {n_ok_adapt}/{n_total} correct — SOME FAILURES")
        sys.exit(1)
