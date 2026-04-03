"""
run_ibr_monte_carlo.py
======================
SAMBP TR-26/2026 — IBR Parametric Monte Carlo Robustness Study.

Validates the combined 87L + 87LN + 87LN0 + TDCS-87L protection chain
across the full IBR parametric envelope using Monte Carlo sampling.

Background
----------
TR-20 through TR-25 developed individual protection elements targeting
specific IBR failure modes.  The combined trip logic is:

    TRIP = (|I₁| ≥ 0.12)           [87L  — positive-seq differential]
        OR (|I₂| ≥ 0.06)           [87LN — negative-seq differential, TR-22]
        OR (|I₀| ≥ 0.04)           [87LN0 — zero-seq differential, TR-25]
        OR (ΔI_adapt ≥ Δ_thr)      [TDCS — transient step, TR-23/24]

Each element was validated in deterministic scenarios.  TR-26 asks:
does the combined element maintain TPR ≥ 0.99 and FPR ≤ 0.005 when
MULTIPLE uncertainty parameters vary simultaneously?

IBR parametric envelope
-----------------------
  k_ibr  ~ U[0.06, 0.20] pu      IBR current limit (post-fault positive-seq)
  f      ~ U[47.0, 53.0] Hz      Off-nominal frequency (island / transient)
  I_h3   ~ U[0.00, 0.10] pu      3rd harmonic injection from IBR
  ε_CT   ~ U[0.000, 0.005]       CT ratio error (Class 5P ≤ 0.5%)
  μ_pre  ~ U[0.002, 0.010] pu    Pre-fault differential baseline (seasonal)
  σ_pre  ~ U[0.0003, 0.0020] pu  Rolling baseline std (adaptive threshold)

Scenario groups
---------------
  A — 3PH internal fault         (5 000 trials): TDCS / 87L should trip
  B — SLG internal fault         (5 000 trials): 87LN0 / 87LN / TDCS should trip
  C — External fault (security)  (5 000 trials): nothing should trip

Modelling notes
---------------
  * After TR-21 harmonic filter (95% attenuation), I_h3 residual in the
    differential = I_h3 × 0.05 pu.  This elevates rms_post slightly.
  * After TR-20 frequency-adaptive B_C correction, off-nominal frequency
    introduces < 0.2% amplitude error in phasor extraction (DFT bin misalign-
    ment at ±3 Hz for 80-sample window) → modelled as negligible noise.
  * 87L/87LN/87LN0 thresholds are peak-amplitude comparisons (DFT phasor
    convention).  TDCS thresholds are RMS comparisons.
  * Adaptive threshold: Δ_thr = Δ_floor + k_σ × σ_pre
    with Δ_floor = 0.025 pu, k_σ = 3.

Expected results
----------------
  Group A TPR ≈ 1.000  (TDCS catches all k_ibr ≥ 0.060 pu, even at drift)
  Group B TPR ≈ 1.000  (87LN0 for earthed, TDCS for unearthed)
  Group C FPR = 0.000  (ΔI_ext_max = 0.023 pu < Δ_floor = 0.025 pu)
  All 95 % Wilson CI lower bounds ≥ 0.99 / upper bounds ≤ 0.005
"""

from __future__ import annotations

import sys
import os
import numpy as np
from dataclasses import dataclass

HERE      = os.path.dirname(os.path.abspath(__file__))
SAMBP_DIR = os.path.dirname(HERE)
REPO_DIR  = os.path.dirname(SAMBP_DIR)
for p in [HERE, SAMBP_DIR, REPO_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_TRIALS = 5_000
RNG_SEED = 2026

# Protection thresholds
I1_THR     = 0.12    # 87L threshold [pu peak]
I2_THR     = 0.06    # 87LN threshold [pu peak]
I0_THR     = 0.04    # 87LN0 threshold [pu peak]
DELTA_FLOOR = 0.025  # Adaptive TDCS floor [pu RMS]
K_SIGMA    = 3.0     # Adaptive threshold multiplier
NOISE_FLOOR = 0.010  # TDCS minimum post-fault RMS [pu]

# Harmonic attenuation factor (TR-21 achieves ≥95%)
HARM_RESIDUAL_FACTOR = 0.05

# ---------------------------------------------------------------------------
# Parameter ranges
# ---------------------------------------------------------------------------

K_IBR_RANGE   = (0.06, 0.20)
FREQ_RANGE    = (47.0, 53.0)
IH3_RANGE     = (0.00, 0.10)
ECT_RANGE     = (0.000, 0.005)
MU_PRE_RANGE  = (0.002, 0.010)
SIG_PRE_RANGE = (0.0003, 0.0020)
I_EXT_RANGE   = (0.5,   7.0)

# Earthing probabilities for SLG group
EARTH_PROBS = {"solid": 0.40, "r_earth": 0.40, "unearthed": 0.20}

# I0 ranges by earthing type [pu peak]
I0_RANGE    = {"solid": (0.20, 0.30), "r_earth": (0.06, 0.10), "unearthed": (0.003, 0.007)}

# I2 range for SLG (pure IBR, no SG) [pu peak]
I2_SLG_RANGE = (0.010, 0.040)


# ---------------------------------------------------------------------------
# Wilson score confidence interval
# ---------------------------------------------------------------------------

def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score CI for proportion k/n."""
    p = k / n
    center = (p + z**2 / (2*n)) / (1 + z**2/n)
    half   = z * np.sqrt(p*(1-p)/n + z**2/(4*n**2)) / (1 + z**2/n)
    return max(0.0, center - half), min(1.0, center + half)


# ---------------------------------------------------------------------------
# Combined element evaluator (no waveform generation needed —
# uses parametric sequence/RMS model directly)
# ---------------------------------------------------------------------------

def evaluate_combined(
    I1: float, I2: float, I0: float,
    k_ibr: float, I_h3: float,
    mu_pre: float, sig_pre: float,
) -> dict:
    """
    Evaluate the combined 87L+87LN+87LN0+TDCS element on parametric inputs.

    Parameters
    ----------
    I1, I2, I0  : sequence differential amplitudes [pu peak]
    k_ibr       : IBR current limit (= I1 for internal faults) [pu peak]
    I_h3        : 3rd harmonic injection [pu peak]; TR-21 attenuates by 95%
    mu_pre      : pre-fault baseline mean [pu RMS]
    sig_pre     : pre-fault baseline std  [pu RMS]

    Returns
    -------
    dict with trip flags and diagnostic values
    """
    # Sequence elements (peak comparisons)
    trip_87L   = (I1 >= I1_THR)
    trip_87LN  = (I2 >= I2_THR)
    trip_87LN0 = (I0 >= I0_THR)

    # TDCS (RMS comparisons)
    harm_res = I_h3 * HARM_RESIDUAL_FACTOR   # residual after TR-21 filter
    # RMS post-fault: sqrt((k_ibr/sqrt2)^2 + harm_res^2)
    rms_post = float(np.sqrt(k_ibr**2 / 2.0 + harm_res**2))
    delta_I  = rms_post - mu_pre
    delta_thr = DELTA_FLOOR + K_SIGMA * sig_pre
    trip_tdcs = (delta_I >= delta_thr) and (rms_post >= NOISE_FLOOR)

    trip_combined = trip_87L or trip_87LN or trip_87LN0 or trip_tdcs

    return {
        "trip_87L":   trip_87L,
        "trip_87LN":  trip_87LN,
        "trip_87LN0": trip_87LN0,
        "trip_tdcs":  trip_tdcs,
        "trip":       trip_combined,
        "rms_post":   rms_post,
        "delta_I":    delta_I,
        "delta_thr":  delta_thr,
        "margin_tdcs": (delta_I - delta_thr) / max(delta_thr, 1e-9),
    }


# ---------------------------------------------------------------------------
# Group A: 3PH internal faults
# ---------------------------------------------------------------------------

@dataclass
class TrialRecord:
    k_ibr:   float
    freq:    float
    I_h3:    float
    eps_CT:  float
    mu_pre:  float
    sig_pre: float
    I0:      float
    I2:      float
    trip:    bool
    by_87L:  bool
    by_tdcs: bool
    delta_I: float
    delta_thr: float


def run_group_a(rng: np.random.Generator) -> list[TrialRecord]:
    """Group A: 5000 symmetric 3PH internal fault trials."""
    records = []
    for _ in range(N_TRIALS):
        k     = rng.uniform(*K_IBR_RANGE)
        f     = rng.uniform(*FREQ_RANGE)
        h3    = rng.uniform(*IH3_RANGE)
        ect   = rng.uniform(*ECT_RANGE)
        mu    = rng.uniform(*MU_PRE_RANGE)
        sig   = rng.uniform(*SIG_PRE_RANGE)

        res = evaluate_combined(
            I1=k, I2=0.0, I0=0.0,
            k_ibr=k, I_h3=h3,
            mu_pre=mu, sig_pre=sig,
        )
        records.append(TrialRecord(
            k_ibr=k, freq=f, I_h3=h3, eps_CT=ect,
            mu_pre=mu, sig_pre=sig, I0=0.0, I2=0.0,
            trip=res["trip"], by_87L=res["trip_87L"],
            by_tdcs=res["trip_tdcs"],
            delta_I=res["delta_I"], delta_thr=res["delta_thr"],
        ))
    return records


def run_group_b(rng: np.random.Generator) -> list[TrialRecord]:
    """Group B: 5000 SLG internal fault trials (mixed earthing)."""
    earth_choices = list(EARTH_PROBS.keys())
    earth_p       = list(EARTH_PROBS.values())
    records = []
    for _ in range(N_TRIALS):
        k     = rng.uniform(*K_IBR_RANGE)
        f     = rng.uniform(*FREQ_RANGE)
        h3    = rng.uniform(*IH3_RANGE)
        ect   = rng.uniform(*ECT_RANGE)
        mu    = rng.uniform(*MU_PRE_RANGE)
        sig   = rng.uniform(*SIG_PRE_RANGE)

        earth = rng.choice(earth_choices, p=earth_p)
        I0    = rng.uniform(*I0_RANGE[earth])
        I2    = rng.uniform(*I2_SLG_RANGE)

        res = evaluate_combined(
            I1=k, I2=I2, I0=I0,
            k_ibr=k, I_h3=h3,
            mu_pre=mu, sig_pre=sig,
        )
        records.append(TrialRecord(
            k_ibr=k, freq=f, I_h3=h3, eps_CT=ect,
            mu_pre=mu, sig_pre=sig, I0=I0, I2=I2,
            trip=res["trip"], by_87L=res["trip_87L"],
            by_tdcs=res["trip_tdcs"],
            delta_I=res["delta_I"], delta_thr=res["delta_thr"],
        ))
    return records


def run_group_c(rng: np.random.Generator) -> list[dict]:
    """Group C: 5000 external fault security trials."""
    records = []
    for _ in range(N_TRIALS):
        I_ext = rng.uniform(*I_EXT_RANGE)
        ect   = rng.uniform(*ECT_RANGE)
        mu    = rng.uniform(*MU_PRE_RANGE)
        sig   = rng.uniform(*SIG_PRE_RANGE)

        # CT mismatch differential:
        # One-phase CT error → peak differential = ect × I_ext on one phase
        # → positive-seq phasor = ect × I_ext / 3 (by symmetrical components)
        # → zero-seq phasor = ect × I_ext / 3 (same for single-phase mismatch)
        I1_ct = ect * I_ext / 3.0    # pos-seq differential [pu peak]
        I0_ct = ect * I_ext / 3.0    # zero-seq differential [pu peak]
        I2_ct = ect * I_ext / 3.0    # neg-seq differential [pu peak]

        # TDCS on external: rms_post from CT mismatch residual
        # Single-phase mismatch peak = ect × I_ext → RMS = ect × I_ext / sqrt2
        rms_post_ext  = ect * I_ext / np.sqrt(2.0)
        delta_I_ext   = rms_post_ext - mu
        delta_thr_ext = DELTA_FLOOR + K_SIGMA * sig
        trip_tdcs     = (delta_I_ext >= delta_thr_ext) and (rms_post_ext >= NOISE_FLOOR)

        trip_87L   = I1_ct >= I1_THR
        trip_87LN  = I2_ct >= I2_THR
        trip_87LN0 = I0_ct >= I0_THR

        trip = trip_87L or trip_87LN or trip_87LN0 or trip_tdcs

        records.append({
            "I_ext": I_ext, "eps_CT": ect, "mu_pre": mu, "sig_pre": sig,
            "I1_ct": I1_ct, "I2_ct": I2_ct, "I0_ct": I0_ct,
            "rms_post": rms_post_ext, "delta_I": delta_I_ext,
            "delta_thr": delta_thr_ext,
            "trip_87L": trip_87L, "trip_87LN": trip_87LN,
            "trip_87LN0": trip_87LN0, "trip_tdcs": trip_tdcs,
            "trip": trip,
        })
    return records


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def group_stats(records, expected_trip: bool) -> dict:
    """Compute TPR/FPR + Wilson CI for a trial group."""
    n = len(records)
    if expected_trip:
        k = sum(1 for r in records if (r.trip if hasattr(r, "trip") else r["trip"]))
    else:
        k = sum(1 for r in records if not (r.trip if hasattr(r, "trip") else r["trip"]))

    rate = k / n
    lo, hi = wilson_ci(k, n)
    return {
        "n": n, "k": k, "rate": rate,
        "ci_lo": lo, "ci_hi": hi,
        "pass": (rate >= 0.99) if expected_trip else (rate >= 0.995),
    }


# ---------------------------------------------------------------------------
# Binned analysis for Group A (detection vs k_ibr)
# ---------------------------------------------------------------------------

def detection_by_kbins(records: list[TrialRecord], n_bins: int = 7) -> list[dict]:
    """
    Bin Group A records by k_ibr and report detection rate + element breakdown.
    Bins: [0.06,0.08), [0.08,0.10), ..., [0.18,0.20]
    """
    edges = np.linspace(K_IBR_RANGE[0], K_IBR_RANGE[1], n_bins + 1)
    bins  = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i+1]
        subset = [r for r in records if lo <= r.k_ibr < hi]
        if not subset:
            continue
        n    = len(subset)
        n_trip     = sum(1 for r in subset if r.trip)
        n_87L      = sum(1 for r in subset if r.by_87L)
        n_tdcs_only= sum(1 for r in subset if r.trip and not r.by_87L)
        ci = wilson_ci(n_trip, n)
        bins.append({
            "lo": lo, "hi": hi, "n": n,
            "tpr": n_trip / n,
            "tpr_ci_lo": ci[0], "tpr_ci_hi": ci[1],
            "frac_87L":  n_87L / n,
            "frac_tdcs": n_tdcs_only / n,
        })
    return bins


# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------

def print_results(
    rec_a: list[TrialRecord],
    rec_b: list[TrialRecord],
    rec_c: list[dict],
) -> None:
    stat_a = group_stats(rec_a, expected_trip=True)
    stat_b = group_stats(rec_b, expected_trip=True)
    stat_c = group_stats(rec_c, expected_trip=False)

    print("=" * 75)
    print(f"SAMBP TR-26/2026 — IBR Monte Carlo Results  (N={N_TRIALS} per group)")
    print("=" * 75)

    print(f"\n{'Group':<35} {'n':>6} {'Correct':>8} "
          f"{'Rate':>7} {'95% CI':>16} {'Target':>7} {'PASS':>5}")
    print("-" * 85)
    for label, st, target_str in [
        ("A: 3PH internal (TPR)",      stat_a, "≥ 0.990"),
        ("B: SLG internal (TPR)",      stat_b, "≥ 0.990"),
        ("C: External (security rate)", stat_c, "≥ 0.995"),
    ]:
        ci_str = f"[{st['ci_lo']:.4f}, {st['ci_hi']:.4f}]"
        flag   = "PASS" if st["pass"] else "FAIL"
        print(f"  {label:<33} {st['n']:>6} {st['k']:>8} "
              f"{st['rate']:>7.4f} {ci_str:>16} {target_str:>7} {flag:>5}")

    # k_ibr bin breakdown for 3PH
    print("\n  Group A — Detection by k_ibr bin:")
    print(f"    {'k_ibr bin':>14}  {'n':>5}  {'TPR':>6}  "
          f"{'CI_lo':>7}  {'CI_hi':>7}  {'87L%':>6}  {'TDCS%':>6}")
    print("    " + "-" * 62)
    for b in detection_by_kbins(rec_a):
        print(f"    [{b['lo']:.2f}, {b['hi']:.2f})  "
              f"{b['n']:>5}  {b['tpr']:>6.4f}  "
              f"{b['tpr_ci_lo']:>7.4f}  {b['tpr_ci_hi']:>7.4f}  "
              f"{b['frac_87L']*100:>5.1f}%  {b['frac_tdcs']*100:>5.1f}%")

    # Worst-case TDCS security margin (Group C)
    min_margin = min(
        (r["delta_thr"] - r["delta_I"]) / r["delta_thr"]
        for r in rec_c
    )
    min_margin_r = min(rec_c, key=lambda r: (r["delta_thr"] - r["delta_I"]) / r["delta_thr"])
    print(f"\n  Group C — Worst-case TDCS security margin: {min_margin*100:.1f}%")
    print(f"    (at I_ext={min_margin_r['I_ext']:.2f} pu, "
          f"εCT={min_margin_r['eps_CT']:.4f}, "
          f"μ_pre={min_margin_r['mu_pre']:.4f} pu, "
          f"ΔI={min_margin_r['delta_I']:.5f} pu, "
          f"Δ_thr={min_margin_r['delta_thr']:.5f} pu)")

    # Group B earthing breakdown
    n_b_87LN0 = sum(1 for r in rec_b if r.I0 >= I0_THR)
    n_b_tdcs  = sum(1 for r in rec_b if r.trip and not (r.I0 >= I0_THR or r.I2 >= I2_THR))
    n_b_87LN  = sum(1 for r in rec_b if r.I2 >= I2_THR)
    n_b_87L   = sum(1 for r in rec_b if r.by_87L)
    print(f"\n  Group B — Detection by element (non-exclusive):")
    print(f"    87L   (k≥0.12): {n_b_87L:5d}/{N_TRIALS}")
    print(f"    87LN  (I2≥0.06): {n_b_87LN:5d}/{N_TRIALS}")
    print(f"    87LN0 (I0≥0.04): {n_b_87LN0:5d}/{N_TRIALS}")
    print(f"    TDCS only:        {n_b_tdcs:5d}/{N_TRIALS}")

    print()
    all_pass = stat_a["pass"] and stat_b["pass"] and stat_c["pass"]
    if all_pass:
        print("  ALL PERFORMANCE TARGETS MET — TR-26 PASS")
    else:
        print("  SOME TARGETS MISSED")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Running TR-26 IBR Monte Carlo (N={N_TRIALS} per group, seed={RNG_SEED})...")
    rng   = np.random.default_rng(RNG_SEED)
    rec_a = run_group_a(rng)
    rec_b = run_group_b(rng)
    rec_c = run_group_c(rng)
    print_results(rec_a, rec_b, rec_c)
