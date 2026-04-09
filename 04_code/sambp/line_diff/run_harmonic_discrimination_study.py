"""
run_harmonic_discrimination_study.py
=====================================
SAMBP TR-21/2026 — Harmonic-Component Discrimination for 87L in IBR-Rich Networks.

Study overview
--------------
Evaluates the impact of IBR-injected odd harmonics (3rd, 5th, 7th) on the
SAMBP 87L differential element, and demonstrates that harmonic pre-filtering
restores the LM confidence score.

Three studies:

  A. No-fault, healthy line — confidence vs harmonic injection level
     → Fixed (no pre-filter): confidence degrades at I_harm > 0.02 pu
     → TR-21 (pre-filter):    confidence stays near 1.0 at all harmonic levels

  B. Internal fault (I_fund = 0.15 pu) — trip correctness vs harmonic level
     → Both methods should trip correctly

  C. External fault (no true differential) — security at high harmonic level
     → No false trips in either method

Selectivity target: 21/21 (3 × 7 scenarios) for TR-21 method.
"""

from __future__ import annotations

import sys
import os
import csv
import numpy as np
from scipy.signal import hilbert

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
HERE      = os.path.dirname(os.path.abspath(__file__))
SAMBP_DIR = os.path.dirname(HERE)
REPO_DIR  = os.path.dirname(SAMBP_DIR)
for p in [HERE, SAMBP_DIR, REPO_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from sambp_line_diff.models.line_harmonic_model import (
    HarmonicFilterConfig,
    filter_harmonics_single,
    residual_norm_after_lm,
    confidence_from_residual,
)

# ---------------------------------------------------------------------------
# Study constants
# ---------------------------------------------------------------------------

FS           = 4000.0    # Sampling rate [Hz]
F_NOM        = 50.0      # Nominal frequency [Hz]
N_CYCLES     = 2         # Window: 2 power cycles
N_SAMP       = int(FS * N_CYCLES / F_NOM)
I_THRESHOLD  = 0.12      # 87L trip threshold [pu]
I_FUND_FAULT = 0.15      # Internal fault fundamental amplitude [pu]
I_FUND_HLTHY = 0.003     # Healthy-line charging residual (post TR-20) [pu]
CONF_THRESH  = 0.80      # Minimum acceptable confidence score

# Harmonic injection levels (3rd harmonic amplitude, 3-phase symmetric)
HARM_LEVELS  = [0.000, 0.005, 0.010, 0.030, 0.050, 0.080, 0.100]

OUT_DIR = os.path.join(HERE, "results_tr21")
os.makedirs(OUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _make_t() -> np.ndarray:
    return np.arange(N_SAMP) / FS


def _sine(amp: float, freq: float, phi: float = 0.0) -> np.ndarray:
    t = _make_t()
    return amp * np.sin(2 * np.pi * freq * t + phi)


def _harmonic_burst(I_h3: float) -> np.ndarray:
    """3rd + 5th + 7th harmonic injection (3rd dominant, others 50% and 25%)."""
    return (_sine(I_h3,         3 * F_NOM) +
            _sine(I_h3 * 0.50, 5 * F_NOM) +
            _sine(I_h3 * 0.25, 7 * F_NOM))


def _save_csv(path: str, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def _evaluate(scenario: str, I_harm_3: float) -> dict:
    """
    Evaluate one (scenario, harmonic level) combination.

    Parameters
    ----------
    scenario  : "no_fault" | "int_fault" | "ext_fault"
    I_harm_3  : 3rd harmonic amplitude [pu] (5th and 7th also injected)

    Returns dict with results for fixed (no filter) and TR-21 (filtered).
    """
    t = _make_t()
    harm = _harmonic_burst(I_harm_3)

    if scenario == "no_fault":
        i_fund_component = _sine(I_FUND_HLTHY, F_NOM)
    elif scenario == "int_fault":
        i_fund_component = _sine(I_FUND_FAULT, F_NOM, phi=0.1)
    else:   # ext_fault — no true fundamental differential
        i_fund_component = np.zeros(N_SAMP)

    # Measured differential = fundamental truth + harmonics
    i_diff_meas = i_fund_component + harm

    idx1 = int(round(F_NOM * N_SAMP / FS))   # DFT bin for fundamental

    def _fund_model(sig: np.ndarray) -> tuple[float, np.ndarray]:
        """Extract fundamental component via single-bin IRFFT (phase-correct)."""
        F = np.fft.rfft(sig)
        F_fund = np.zeros_like(F)
        F_fund[idx1] = F[idx1]
        i_mod = np.fft.irfft(F_fund, n=N_SAMP)
        amp = float(abs(F[idx1]) * 2 / N_SAMP)
        return amp, i_mod

    # ---------- Fixed method (no harmonic filter) -------------------------
    I_fund_dft, i_model_fixed = _fund_model(i_diff_meas)

    rn_fixed   = residual_norm_after_lm(i_diff_meas, i_model_fixed)
    conf_fixed = confidence_from_residual(rn_fixed)
    trip_fixed = I_fund_dft >= I_THRESHOLD

    # ---------- TR-21 method (harmonic pre-filter) -------------------------
    cfg = HarmonicFilterConfig(harmonics=(3, 5, 7))
    r   = filter_harmonics_single(i_diff_meas, t, F_NOM, cfg)

    I_fund_filt, i_model_filt = _fund_model(r.i_filtered)

    rn_adapt   = residual_norm_after_lm(r.i_filtered, i_model_filt)
    conf_adapt = confidence_from_residual(rn_adapt)
    trip_adapt = I_fund_filt >= I_THRESHOLD

    # Correctness
    expect_trip = (scenario == "int_fault")
    correct_fixed = (trip_fixed == expect_trip)
    correct_adapt = (trip_adapt == expect_trip)

    # Also check confidence is acceptable (≥ CONF_THRESH)
    conf_ok_fixed = (conf_fixed >= CONF_THRESH)
    conf_ok_adapt = (conf_adapt >= CONF_THRESH)

    return {
        "scenario":       scenario,
        "I_harm_3":       I_harm_3,
        "I_fund_dft":     I_fund_dft,
        "I_fund_filt":    I_fund_filt,
        "H_ratio":        r.H_ratio,
        "network_type":   r.network_type,
        "rn_fixed":       rn_fixed,
        "conf_fixed":     conf_fixed,
        "rn_adapt":       rn_adapt,
        "conf_adapt":     conf_adapt,
        "trip_fixed":     trip_fixed,
        "trip_adapt":     trip_adapt,
        "correct_fixed":  correct_fixed,
        "correct_adapt":  correct_adapt,
        "conf_ok_fixed":  conf_ok_fixed,
        "conf_ok_adapt":  conf_ok_adapt,
    }


# ---------------------------------------------------------------------------
# Study A: No-fault confidence vs harmonic level
# ---------------------------------------------------------------------------

def study_a_nofault() -> list[dict]:
    print("\n=== Study A: No-fault confidence vs harmonic injection ===")
    results = []
    hdr = (f"{'I_h3[pu]':>9} {'I_fund':>8} {'H_ratio':>8} {'Net':>6} "
           f"{'rn_fix':>7} {'conf_fix':>9} {'ok_fix':>7} "
           f"{'rn_adp':>7} {'conf_adp':>9} {'ok_adp':>7}")
    print(hdr)
    print("-" * len(hdr))
    for ih in HARM_LEVELS:
        r = _evaluate("no_fault", ih)
        of = "PASS" if r["conf_ok_fixed"] else "FAIL"
        oa = "PASS" if r["conf_ok_adapt"] else "FAIL"
        print(f"{ih:9.3f} {r['I_fund_dft']:8.5f} {r['H_ratio']:8.4f} {r['network_type']:>6} "
              f"{r['rn_fixed']:7.4f} {r['conf_fixed']:9.4f} {of:>7} "
              f"{r['rn_adapt']:7.4f} {r['conf_adapt']:9.4f} {oa:>7}")
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# Study B: Internal fault trip correctness vs harmonic level
# ---------------------------------------------------------------------------

def study_b_fault() -> list[dict]:
    print("\n=== Study B: Internal fault (0.15 pu) trip correctness vs harmonic level ===")
    results = []
    hdr = (f"{'I_h3[pu]':>9} {'I_fund_dft':>11} {'I_fund_filt':>12} "
           f"{'trip_fix':>9} {'trip_adp':>9} {'ok_fix':>7} {'ok_adp':>7}")
    print(hdr)
    print("-" * len(hdr))
    for ih in HARM_LEVELS:
        r = _evaluate("int_fault", ih)
        of = "PASS" if r["correct_fixed"] else "FAIL"
        oa = "PASS" if r["correct_adapt"] else "FAIL"
        tf = "YES" if r["trip_fixed"] else " no"
        ta = "YES" if r["trip_adapt"] else " no"
        print(f"{ih:9.3f} {r['I_fund_dft']:11.5f} {r['I_fund_filt']:12.5f} "
              f"{tf:>9} {ta:>9} {of:>7} {oa:>7}")
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# Study C: External fault security vs harmonic level
# ---------------------------------------------------------------------------

def study_c_external() -> list[dict]:
    print("\n=== Study C: External fault security (no true differential) ===")
    results = []
    hdr = (f"{'I_h3[pu]':>9} {'I_fund_dft':>11} {'I_fund_filt':>12} "
           f"{'trip_fix':>9} {'trip_adp':>9} {'ok_fix':>7} {'ok_adp':>7}")
    print(hdr)
    print("-" * len(hdr))
    for ih in HARM_LEVELS:
        r = _evaluate("ext_fault", ih)
        of = "PASS" if r["correct_fixed"] else "FAIL"
        oa = "PASS" if r["correct_adapt"] else "FAIL"
        tf = "YES" if r["trip_fixed"] else " no"
        ta = "YES" if r["trip_adapt"] else " no"
        print(f"{ih:9.3f} {r['I_fund_dft']:11.5f} {r['I_fund_filt']:12.5f} "
              f"{tf:>9} {ta:>9} {of:>7} {oa:>7}")
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# Study D: Summary
# ---------------------------------------------------------------------------

def study_d_summary(results_a, results_b, results_c) -> tuple:
    print("\n=== Study D: Selectivity summary ===")
    all_res = results_a + results_b + results_c
    n = len(all_res)

    # Trip correctness
    n_ok_fixed = sum(r["correct_fixed"] for r in all_res)
    n_ok_adapt = sum(r["correct_adapt"] for r in all_res)
    print(f"  Trip correctness — Fixed: {n_ok_fixed}/{n}, Adaptive: {n_ok_adapt}/{n}")

    # Confidence quality (study A only — no-fault confidence)
    n_conf_fixed = sum(r["conf_ok_fixed"] for r in results_a)
    n_conf_adapt = sum(r["conf_ok_adapt"] for r in results_a)
    na = len(results_a)
    print(f"  Confidence ≥ {CONF_THRESH} (Study A) — Fixed: {n_conf_fixed}/{na}, Adaptive: {n_conf_adapt}/{na}")

    # Overall: trip correct AND confidence acceptable
    def overall_ok(r):
        return r["correct_adapt"] and r["conf_ok_adapt"]

    n_overall = sum(overall_ok(r) for r in all_res)
    print(f"  Overall (trip + confidence) — TR-21: {n_overall}/{n}")

    return n_ok_fixed, n_ok_adapt, n_conf_fixed, n_conf_adapt, n_overall, n


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 66)
    print("SAMBP TR-21/2026 — Harmonic Discrimination for IBR-Rich 87L")
    print("=" * 66)

    ra = study_a_nofault()
    rb = study_b_fault()
    rc = study_c_external()
    n_ok_fixed, n_ok_adapt, n_cf, n_ca, n_overall, n = study_d_summary(ra, rb, rc)

    # Save CSVs
    fields = ["scenario", "I_harm_3", "I_fund_dft", "I_fund_filt", "H_ratio",
              "network_type", "rn_fixed", "conf_fixed", "rn_adapt", "conf_adapt",
              "trip_fixed", "trip_adapt", "correct_fixed", "correct_adapt",
              "conf_ok_fixed", "conf_ok_adapt"]
    _save_csv(os.path.join(OUT_DIR, "tr21_results.csv"), ra + rb + rc, fields)
    print(f"\n  Results saved to {OUT_DIR}/")

    print()
    if n_ok_adapt == n and n_ca == len(ra):
        print(f"RESULT: {n_ok_adapt}/{n} trip correct + {n_ca}/{len(ra)} conf OK — 100%")
    else:
        print(f"RESULT: trip {n_ok_adapt}/{n}, conf_a {n_ca}/{len(ra)} — FAILURES")
        sys.exit(1)
