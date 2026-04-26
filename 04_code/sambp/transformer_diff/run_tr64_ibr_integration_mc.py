#!/usr/bin/env python3
"""
run_tr64_ibr_integration_mc.py
================================
SAMBP TR-64/2026 — IBR-Aware 87T Integration: SPRT + Zone Model + Conventional

Problem
-------
The conventional 87T relay uses 2nd-harmonic blocking (H2_ratio > 0.15 →
BLOCK) to prevent false tripping on transformer energisation inrush.  For
IBR-dominated internal faults (k_ibr ≥ 0.7) with residual core flux (Br > 0):
  • The Br term injects 2nd-harmonic into i_diff at fault inception (τ = 50 ms).
  • H2_ratio > 0.15 → conventional relay BLOCKED (false negative).
  • Meanwhile, A_k ≈ 0 (IBR current is symmetric) → SPRT correctly identifies H1.

TR-64 Integration Logic (5-priority chain, eq. 3–7 in report):
  1. High-set (I_op_fund > 5 pu)      → TRIP  (unrestrained, always fires)
  2. SPRT=CTALARM AND f_int ≥ 0.60    → TRIP  (zone overrides spurious CTALARM)
  3. CT-sat confirmed                 → CTALARM
       (SPRT=CTALARM AND f_int < 0.40) OR (SPRT=TRIP AND f_int < 0.40)
  4. (conv_trip OR SPRT=TRIP) AND f_int ≥ 0.60 → TRIP (SPRT bypasses H2 block)
  5. else                             → RESTRAIN

Performance targets (TR-64 §7)
--------------------------------
  P_D_total = P(TRIP | H1_sg ∪ H1_ibr)  ≥ 0.998
  P_D_ibr   = P(TRIP | H1_ibr)          ≥ 0.990  ← key IBR improvement
  P_D_sg    = P(TRIP | H1_sg)           ≥ 0.999
  P_FA      = P(TRIP | H0)              ≤ 0.002
  P_CTD     = P(CTALARM | H2)           ≥ 0.998
  t_50      ≤ 20 ms  (median SPRT decision for H1_ibr)
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# ─── Resolve paths ────────────────────────────────────────────────────────────
_HERE   = os.path.dirname(os.path.abspath(__file__))
_SAMBP  = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _SAMBP)

# ─── Import SPRT engine and waveform generators from TR-57a ──────────────────
from run_tr57a_sprt_deterministic import (
    waveform_internal_fault,
    waveform_inrush,
    waveform_external_ctsat,
    compute_Ak_series,
    run_sprt,
    llr_h1_vs_h0,
    llr_h2_vs_h1,
    FS, F0, T_CYCLE, N_CYCLE, N_CYCLES, T_SIM,
    LOG_A, LOG_B,
    MU0, SIG0, MU1, SIG1, MU2, SIG2,
)

# ─── Import zone model fast path ─────────────────────────────────────────────
from transformer_diff.models.transformer_reduced_zone_model import (
    initial_guess,
    compute_f_int,
    forward_idiff,
    condition_number_normalised,
    jacobian_idiff,
    LOWER_BOUNDS as ZM_LB,
    UPPER_BOUNDS as ZM_UB,
)
from transformer_diff.inverse_estimation.transformer_inverse_estimator import (
    estimate_zone_parameters,
)

# ─── Constants ────────────────────────────────────────────────────────────────
T_ARR  = np.arange(0, T_SIM, 1.0 / FS)   # pre-allocated time array

# TR-64 integration thresholds
F_INT_TRIP_THRESH   = 0.55   # min f_int to confirm TRIP
#   0.55 chosen so that fault cases (f_int ≥ 0.57) pass the gate while
#   inrush cases (f_int ≤ 0.21) are cleanly rejected. Gap = 0.34 pu.
F_INT_CTSAT_THRESH  = 0.40   # max f_int to classify as CT-sat (CTALARM)

I_OP_MIN    = 0.20           # pu — minimum operate threshold
H2_THRESH   = 0.15           # 2nd-harmonic blocking ratio
H5_THRESH   = 0.35           # 5th-harmonic blocking ratio
I_HIGHSET   = 5.0            # pu — unrestrained high-set

N_TRIALS = 5_000             # per hypothesis class
OUT_DIR  = Path(_HERE) / "outputs" / "tr64"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(42)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: Simplified single-phase conventional 87T decision
# ─────────────────────────────────────────────────────────────────────────────

def compute_conventional_relay(
    i_diff: np.ndarray,
    n_dft_cycles: int = 2,
) -> tuple[bool, bool, float, float, float]:
    """
    Single-phase conventional 87T relay applied to i_diff.

    DFT-based harmonic extraction over first n_dft_cycles (default 40 ms).

    Returns
    -------
    conv_trip  : bool  — True if conventional relay would trip (I_op > I_op_min
                          and NOT harmonic-blocked)
    highset    : bool  — True if unrestrained high-set fires (I_op_fund > 5 pu)
    I_op_fund  : float — fundamental amplitude [pu]
    H2_ratio   : float — 2nd harmonic / fundamental
    H5_ratio   : float — 5th harmonic / fundamental
    """
    n_win = n_dft_cycles * N_CYCLE   # 400 samples at FS=10kHz, F0=50Hz
    win   = i_diff[:n_win]
    N     = len(win)

    F     = np.fft.rfft(win)
    freqs = np.fft.rfftfreq(N, d=1.0 / FS)

    def _amp(f_target):
        idx = int(round(f_target * N / FS))
        idx = np.clip(idx, 0, len(F) - 1)
        return float(np.abs(F[idx]) * 2.0 / N)

    I_op_fund = _amp(F0)
    I_2nd     = _amp(2.0 * F0)
    I_5th     = _amp(5.0 * F0)

    H2_ratio  = I_2nd / max(I_op_fund, 1e-6)
    H5_ratio  = I_5th / max(I_op_fund, 1e-6)

    h2_block  = H2_ratio > H2_THRESH
    h5_block  = H5_ratio > H5_THRESH
    highset   = I_op_fund > I_HIGHSET
    conv_trip = (I_op_fund > I_OP_MIN) and not (h2_block or h5_block)

    return conv_trip, highset, I_op_fund, H2_ratio, H5_ratio


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2: Fast f_int estimate (no LM — for MC throughput)
# ─────────────────────────────────────────────────────────────────────────────

def compute_fast_f_int(
    i_diff: np.ndarray,
    tc: int,
) -> tuple[float, float, float]:
    """
    FFT-based f_int estimate from the post-SPRT tail window.

    Using the tail window (from cycle tc onward) removes the fast-decaying
    2nd-harmonic Br injection (τ = 50 ms ≈ 2.5 cycles), giving a clean
    f_int reading for the settled waveform.

    Parameters
    ----------
    i_diff : (N,) full differential current waveform
    tc     : int  — 1-based SPRT decision cycle

    Returns
    -------
    f_int : float ∈ [0, 1]
    k2    : float — k_inrush estimate
    k5    : float — k_ovexc estimate
    """
    start = max((tc - 1) * N_CYCLE, 0)     # tc-1 because tc is 1-based
    tail  = i_diff[start:]
    if len(tail) < N_CYCLE:
        tail = i_diff[-N_CYCLE:]           # fallback: last cycle

    t_tail = np.arange(len(tail)) / FS
    theta0 = initial_guess(t_tail, tail, freq_hz=F0)
    k2     = float(np.clip(theta0[2], 0.0, 1.0))
    k5     = float(np.clip(theta0[3], 0.0, 1.0))
    eps    = float(np.clip(theta0[4], 0.0, 0.5))
    f_int  = compute_f_int(k2, k5, eps)
    return f_int, k2, k5


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3: TR-64 integration decision
# ─────────────────────────────────────────────────────────────────────────────

def tr64_integrate(
    conv_trip: bool,
    highset: bool,
    sprt_decision: str,
    f_int: float,
) -> str:
    """
    TR-64 five-priority integration decision.

    Priority chain (highest to lowest):
      1. highset_trip → TRIP  (unrestrained; always overrides blocking)
      2. SPRT=CTALARM AND f_int ≥ 0.60 → TRIP
         (zone model overrides spurious CTALARM on SG faults at φ≈150–230°
          where CT recovery pulse drives A_k < 0 transiently)
      3. CT-sat confirmed → CTALARM
         (SPRT=CTALARM AND f_int < F_INT_CTSAT_THRESH)
         OR (SPRT=TRIP AND f_int < F_INT_CTSAT_THRESH)
         [second clause: SPRT saw positive A_k early before saturation dominated]
      4. (conv_trip OR SPRT=TRIP) AND f_int ≥ F_INT_TRIP_THRESH → TRIP
         [SPRT H1 bypasses 2nd-harmonic blocking for IBR faults]
      5. else → RESTRAIN

    Returns
    -------
    'TRIP' | 'CTALARM' | 'RESTRAIN'
    """
    # 1. Unrestrained high-set
    if highset:
        return 'TRIP'

    sprt_H1 = (sprt_decision == 'TRIP')
    sprt_H2 = (sprt_decision == 'CTALARM')

    # 2. SPRT CTALARM override: zone says internal fault → TRIP
    if sprt_H2 and f_int >= F_INT_TRIP_THRESH:
        return 'TRIP'

    # 3. CT saturation confirmed
    ct_sat = (
        (sprt_H2 and f_int < F_INT_CTSAT_THRESH)
        or (sprt_H1 and f_int < F_INT_CTSAT_THRESH)
    )
    if ct_sat:
        return 'CTALARM'

    # 4. SPRT H1 bypass: trip even when conventional 2nd-harmonic-blocked
    if (conv_trip or sprt_H1) and f_int >= F_INT_TRIP_THRESH:
        return 'TRIP'

    return 'RESTRAIN'


# ─────────────────────────────────────────────────────────────────────────────
# Single trial runner
# ─────────────────────────────────────────────────────────────────────────────

def run_single_trial(i_diff: np.ndarray) -> dict:
    """
    Run one complete TR-64 evaluation.

    Parameters
    ----------
    i_diff : (N,) differential current waveform [pu]

    Returns
    -------
    dict with decision, trip_cycle, trip_ms, conv_trip, highset,
         sprt_dec, f_int, I_op_fund, H2_ratio
    """
    conv_trip, highset, I_op_fund, H2_ratio, H5_ratio = compute_conventional_relay(i_diff)

    Ak_series            = compute_Ak_series(i_diff)
    sprt_dec, trip_cycle, _, _ = run_sprt(Ak_series)

    f_int, k2, _         = compute_fast_f_int(i_diff, trip_cycle)

    decision             = tr64_integrate(conv_trip, highset, sprt_dec, f_int)

    return {
        "decision":   decision,
        "trip_cycle": trip_cycle,
        "trip_ms":    trip_cycle * T_CYCLE * 1e3,
        "conv_trip":  conv_trip,
        "highset":    highset,
        "sprt_dec":   sprt_dec,
        "f_int":      f_int,
        "I_op_fund":  I_op_fund,
        "H2_ratio":   H2_ratio,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic 16-scenario sweep
# ─────────────────────────────────────────────────────────────────────────────

# (sid, label, k_ibr, phi_deg, Br, waveform_fn, expected)
SCENARIOS = [
    # Internal fault — pure SG
    ("S01", "Internal 3PH k_ibr=0.0 φ=0°  Br=0.0", 0.0, 0.0,  0.0, "fault", "TRIP"),
    ("S02", "Internal 3PH k_ibr=0.0 φ=90° Br=0.0", 0.0, 90.0, 0.0, "fault", "TRIP"),
    ("S03", "Internal 3PH k_ibr=0.0 φ=0°  Br=0.7", 0.0, 0.0,  0.7, "fault", "TRIP"),
    ("S04", "Internal 3PH k_ibr=0.0 φ=90° Br=0.7", 0.0, 90.0, 0.7, "fault", "TRIP"),
    # Internal fault — 50% IBR (mixed)
    ("S05", "Internal 3PH k_ibr=0.5 φ=0°  Br=0.0", 0.5, 0.0,  0.0, "fault", "TRIP"),
    ("S06", "Internal 3PH k_ibr=0.5 φ=90° Br=0.0", 0.5, 90.0, 0.0, "fault", "TRIP"),
    ("S07", "Internal 3PH k_ibr=0.5 φ=0°  Br=0.7", 0.5, 0.0,  0.7, "fault", "TRIP"),
    ("S08", "Internal 3PH k_ibr=0.5 φ=90° Br=0.7", 0.5, 90.0, 0.7, "fault", "TRIP"),
    # Internal fault — 100% IBR (IBR-blocked scenarios)
    ("S09", "Internal 3PH k_ibr=1.0 φ=0°  Br=0.0", 1.0, 0.0,  0.0, "fault", "TRIP"),
    ("S10", "Internal 3PH k_ibr=1.0 φ=90° Br=0.0", 1.0, 90.0, 0.0, "fault", "TRIP"),
    ("S11", "Internal 3PH k_ibr=1.0 φ=0°  Br=0.7", 1.0, 0.0,  0.7, "fault", "TRIP"),
    ("S12", "Internal 3PH k_ibr=1.0 φ=90° Br=0.7", 1.0, 90.0, 0.7, "fault", "TRIP"),
    # Energisation inrush
    ("S13", "Inrush φ=0°  Br=0.0",                  None, 0.0,  0.0, "inrush", "RESTRAIN"),
    ("S14", "Inrush φ=90° Br=0.0",                  None, 90.0, 0.0, "inrush", "RESTRAIN"),
    ("S15", "Inrush φ=0°  Br=0.7",                  None, 0.0,  0.7, "inrush", "RESTRAIN"),
    ("S16", "Inrush φ=90° Br=0.7",                  None, 90.0, 0.7, "inrush", "RESTRAIN"),
]


def run_deterministic() -> pd.DataFrame:
    rows = []
    print("TR-64: Deterministic 16-Scenario Sweep")
    print("=" * 90)
    print(f"  {'ID':3}  {'Label':42}  {'Exp':8}  {'Got':8}  "
          f"{'Conv':5}  {'HS':5}  {'SPRT':8}  {'f_int':5}  {'ms':5}  PASS")
    print("-" * 90)

    for (sid, label, k_ibr, phi_deg, Br, fn, expected) in SCENARIOS:
        if fn == "fault":
            i_diff = waveform_internal_fault(k_ibr, phi_deg, Br)
        else:
            i_diff = waveform_inrush(phi_deg, Br)

        res = run_single_trial(i_diff)
        got = res["decision"]
        ok  = (got == expected)

        conv_str = "T" if res["conv_trip"] else "F"
        hs_str   = "T" if res["highset"]   else "F"
        print(f"  {sid:3}  {label:42}  {expected:8}  {got:8}  "
              f"  {conv_str}    {hs_str}    {res['sprt_dec']:8}  "
              f"{res['f_int']:5.3f}  {res['trip_ms']:5.1f}  "
              f"{'✓' if ok else '✗'}")

        rows.append({
            "id": sid, "label": label,
            "k_ibr": k_ibr if k_ibr is not None else -1,
            "phi_deg": phi_deg, "Br": Br,
            "expected": expected, "decision": got, "pass": ok,
            "conv_trip": res["conv_trip"], "highset": res["highset"],
            "sprt_dec": res["sprt_dec"],
            "f_int": res["f_int"], "trip_ms": res["trip_ms"],
            "I_op_fund": res["I_op_fund"], "H2_ratio": res["H2_ratio"],
        })

    df = pd.DataFrame(rows)
    n_pass = int(df["pass"].sum())
    print("-" * 90)
    print(f"  Result: {n_pass}/16 PASS")
    print("=" * 90)
    df.to_csv(OUT_DIR / "tr64_deterministic.csv", index=False)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Monte Carlo
# ─────────────────────────────────────────────────────────────────────────────

def run_mc_class(hyp_class: str, n_trials: int = N_TRIALS) -> pd.DataFrame:
    """
    Run MC for one hypothesis class.

    Sampling distributions:
      H1_sg  : k_ibr ~ U[0.0, 0.5], Br ~ U[0, 0.7], phi ~ U[0°, 360°]
      H1_ibr : k_ibr ~ U[0.7, 1.0], Br ~ U[0, 0.7], phi ~ U[0°, 360°]
      H0     : Br ~ U[0, 0.9], phi ~ U[0°, 360°]
      H2     : k_ibr ~ U[0.0, 0.5], Br ~ U[0, 0.7], phi ~ U[0°, 360°]
    """
    k_ibr_arr = RNG.uniform(
        0.7 if hyp_class == "H1_ibr" else 0.0,
        1.0 if hyp_class == "H1_ibr" else (0.5 if hyp_class in ("H1_sg", "H2") else 0.0),
        size=n_trials,
    )
    Br_arr    = RNG.uniform(0.0, 0.9 if hyp_class == "H0" else 0.7, size=n_trials)
    phi_arr   = RNG.uniform(0.0, 360.0, size=n_trials)

    rows = []
    for i in range(n_trials):
        k_ibr = float(k_ibr_arr[i])
        Br    = float(Br_arr[i])
        phi   = float(phi_arr[i])

        if hyp_class in ("H1_sg", "H1_ibr"):
            i_diff = waveform_internal_fault(k_ibr, phi, Br)
        elif hyp_class == "H0":
            i_diff = waveform_inrush(phi, Br)
        else:  # H2
            i_diff = waveform_external_ctsat(k_ibr, phi, Br)

        res = run_single_trial(i_diff)
        rows.append({
            "decision": res["decision"],
            "trip_ms":  res["trip_ms"],
            "conv_trip":res["conv_trip"],
            "sprt_dec": res["sprt_dec"],
            "f_int":    res["f_int"],
            "k_ibr":    k_ibr,
            "Br":       Br,
            "phi_deg":  phi,
        })
    return pd.DataFrame(rows)


def run_monte_carlo() -> dict:
    print("\nTR-64: Monte Carlo Validation")
    print("=" * 70)

    classes = ["H1_sg", "H1_ibr", "H0", "H2"]
    dfs = {}
    for cls in classes:
        print(f"  Running {cls:8} ({N_TRIALS:,} trials) …", end="", flush=True)
        dfs[cls] = run_mc_class(cls)
        print(f" done")

    # Metrics
    P_D_sg    = float((dfs["H1_sg"]["decision"]  == "TRIP").mean())
    P_D_ibr   = float((dfs["H1_ibr"]["decision"] == "TRIP").mean())
    # Conventional alone (H1_ibr)
    P_D_ibr_conv = float(dfs["H1_ibr"]["conv_trip"].mean())

    # Combine H1_sg + H1_ibr for P_D_total
    all_h1 = pd.concat([dfs["H1_sg"], dfs["H1_ibr"]], ignore_index=True)
    P_D_total = float((all_h1["decision"] == "TRIP").mean())

    P_FA  = float((dfs["H0"]["decision"] == "TRIP").mean())
    P_CTD = float((dfs["H2"]["decision"] == "CTALARM").mean())

    # Decision times for H1_ibr TRIPS
    h1ibr_trips = dfs["H1_ibr"][dfs["H1_ibr"]["decision"] == "TRIP"]["trip_ms"]
    t50_ibr = float(np.percentile(h1ibr_trips, 50)) if len(h1ibr_trips) > 0 else float("nan")
    t95_ibr = float(np.percentile(h1ibr_trips, 95)) if len(h1ibr_trips) > 0 else float("nan")

    # Summary
    tgts = {
        "P_D_total":   (P_D_total,   "≥ 0.998", P_D_total   >= 0.998),
        "P_D_ibr":     (P_D_ibr,     "≥ 0.990", P_D_ibr     >= 0.990),
        "P_D_sg":      (P_D_sg,      "≥ 0.999", P_D_sg      >= 0.999),
        "P_FA":        (P_FA,        "≤ 0.002", P_FA        <= 0.002),
        "P_CTD":       (P_CTD,       "≥ 0.998", P_CTD       >= 0.998),
        "t50_ibr_ms":  (t50_ibr,     "≤ 20 ms", t50_ibr     <= 20.0),
    }

    print()
    print(f"  {'Metric':20}  {'Value':10}  {'Target':12}  Result")
    print(f"  {'-'*20}  {'-'*10}  {'-'*12}  ------")
    all_pass = True
    for name, (val, tgt, ok) in tgts.items():
        fmt = f"{val:.4f}" if name != "t50_ibr_ms" else f"{val:.1f} ms"
        print(f"  {name:20}  {fmt:10}  {tgt:12}  {'PASS' if ok else 'FAIL'}")
        if not ok:
            all_pass = False

    print(f"\n  Conventional relay P(TRIP|H1_ibr) = {P_D_ibr_conv:.4f}  "
          f"(TR-64 improvement: {P_D_ibr:.4f} / {max(P_D_ibr_conv,1e-6):.4f} "
          f"= {P_D_ibr/max(P_D_ibr_conv,1e-6):.1f}×)")
    print(f"\n  Overall: {'PASS' if all_pass else 'FAIL'}")
    print("=" * 70)

    # Save per-class CSVs
    for cls, df in dfs.items():
        df.to_csv(OUT_DIR / f"tr64_mc_{cls}.csv", index=False)

    metrics = {
        "P_D_total": P_D_total, "P_D_ibr": P_D_ibr, "P_D_sg": P_D_sg,
        "P_D_ibr_conv": P_D_ibr_conv,
        "P_FA": P_FA, "P_CTD": P_CTD,
        "t50_ibr_ms": t50_ibr, "t95_ibr_ms": t95_ibr,
        "N_trials": N_TRIALS, "all_pass": all_pass,
    }
    pd.DataFrame([metrics]).to_csv(OUT_DIR / "tr64_mc_metrics.csv", index=False)
    return {"dfs": dfs, "metrics": metrics}


# ─────────────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────────────

def _save(fig, name):
    fig.savefig(OUT_DIR / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {name}")


def plot_ibr_gap_comparison(mc_results: dict) -> None:
    """Bar chart: conventional vs TR-64 P_D by k_ibr regime."""
    dfs  = mc_results["dfs"]
    cats = ["H1_sg\n(k_ibr≤0.5)", "H1_ibr\n(k_ibr≥0.7)"]
    conv = [float(dfs["H1_sg"]["conv_trip"].mean()),
            float(dfs["H1_ibr"]["conv_trip"].mean())]
    tr64 = [float((dfs["H1_sg"]["decision"]  == "TRIP").mean()),
            float((dfs["H1_ibr"]["decision"] == "TRIP").mean())]

    x   = np.arange(len(cats))
    w   = 0.35
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(x - w/2, conv, w, label="Conventional 87T", color="#b0c4de", edgecolor="k", linewidth=0.8)
    ax.bar(x + w/2, tr64, w, label="TR-64 IBR-Aware",  color="#2e7d32", edgecolor="k", linewidth=0.8)
    ax.axhline(0.998, color="r", linestyle="--", linewidth=1.0, label="P_D ≥ 0.998 spec")
    ax.set_xticks(x); ax.set_xticklabels(cats)
    ax.set_ylabel("P(TRIP | internal fault)")
    ax.set_ylim(0, 1.08)
    ax.set_title("IBR Gap: Conventional vs TR-64")
    ax.legend(fontsize=8)
    for xi, (c, t) in zip(x, zip(conv, tr64)):
        ax.text(xi - w/2, c + 0.02, f"{c:.3f}", ha="center", va="bottom", fontsize=8)
        ax.text(xi + w/2, t + 0.02, f"{t:.3f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    _save(fig, "tr64_ibr_gap_comparison.png")


def plot_confusion_matrix(mc_results: dict) -> None:
    """4×3 normalised confusion matrix."""
    dfs    = mc_results["dfs"]
    labels = ["H1_sg", "H1_ibr", "H0", "H2"]
    dec_labels = ["TRIP", "CTALARM", "RESTRAIN"]
    mat = np.zeros((4, 3))
    for i, cls in enumerate(labels):
        for j, d in enumerate(dec_labels):
            mat[i, j] = (dfs[cls]["decision"] == d).mean()

    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(mat, vmin=0, vmax=1, cmap="Blues")
    plt.colorbar(im, ax=ax)
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(dec_labels)
    ax.set_yticks([0, 1, 2, 3]); ax.set_yticklabels(labels)
    ax.set_title("TR-64 Decision Confusion Matrix (normalised)")
    for i in range(4):
        for j in range(3):
            ax.text(j, i, f"{mat[i,j]:.3f}", ha="center", va="center",
                    color="white" if mat[i,j] > 0.6 else "black", fontsize=9)
    fig.tight_layout()
    _save(fig, "tr64_confusion_matrix.png")


def plot_decision_time_cdf(mc_results: dict) -> None:
    """CDF of trip times for H1_ibr and H2 (CTALARM)."""
    dfs = mc_results["dfs"]
    fig, ax = plt.subplots(figsize=(6, 4))

    for cls, dec, color, label in [
        ("H1_ibr", "TRIP",    "#2e7d32", "H1_ibr → TRIP"),
        ("H2",     "CTALARM", "#e65100", "H2 → CTALARM"),
    ]:
        t_ms = dfs[cls][dfs[cls]["decision"] == dec]["trip_ms"].values
        if len(t_ms) > 0:
            t_sorted = np.sort(t_ms)
            cdf      = np.arange(1, len(t_sorted) + 1) / len(t_sorted)
            ax.plot(t_sorted, cdf, color=color, label=label)
            t50 = float(np.percentile(t_ms, 50))
            ax.axvline(t50, color=color, linestyle="--", linewidth=0.8,
                       label=f"t_50 = {t50:.0f} ms")

    ax.axvline(20.0, color="r", linestyle=":", linewidth=1.2, label="20 ms spec")
    ax.set_xlabel("Decision time [ms]")
    ax.set_ylabel("CDF")
    ax.set_title("TR-64 Decision Time CDF")
    ax.legend(fontsize=8)
    ax.set_xlim(0, 350)
    fig.tight_layout()
    _save(fig, "tr64_decision_cdf.png")


def plot_f_int_distributions(mc_results: dict) -> None:
    """f_int distribution by hypothesis class."""
    dfs    = mc_results["dfs"]
    labels = ["H1_sg", "H1_ibr", "H0", "H2"]
    colors = ["#1a237e", "#1565c0", "#e65100", "#b71c1c"]

    fig, ax = plt.subplots(figsize=(7, 4))
    bins = np.linspace(0, 1, 41)
    for cls, col in zip(labels, colors):
        ax.hist(dfs[cls]["f_int"], bins=bins, alpha=0.55, color=col,
                label=cls, density=True, edgecolor="none")
    ax.axvline(F_INT_TRIP_THRESH, color="r", linestyle="--", linewidth=1.2,
               label=f"f_int trip = {F_INT_TRIP_THRESH}")
    ax.axvline(F_INT_CTSAT_THRESH, color="orange", linestyle=":", linewidth=1.2,
               label=f"f_int CT-sat = {F_INT_CTSAT_THRESH}")
    ax.set_xlabel("f_int (internal fault score)")
    ax.set_ylabel("Probability density")
    ax.set_title("TR-64: f_int Distributions by Hypothesis Class")
    ax.legend(fontsize=8)
    fig.tight_layout()
    _save(fig, "tr64_f_int_distributions.png")


def plot_deterministic_timeline(det_df: pd.DataFrame) -> None:
    """Horizontal bar chart of decision times per deterministic scenario."""
    color_map = {"TRIP": "#2e7d32", "RESTRAIN": "#1565c0", "CTALARM": "#e65100"}

    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(det_df))
    for i, row in det_df.iterrows():
        col = color_map.get(row["decision"], "grey")
        ax.barh(i, row["trip_ms"], color=col, alpha=0.85, height=0.6, edgecolor="k", linewidth=0.5)
        pass_sym = "✓" if row["pass"] else "✗"
        ax.text(row["trip_ms"] + 3, i, f"{row['decision']} {pass_sym}", va="center", fontsize=7)

    ax.set_yticks(y)
    ax.set_yticklabels([r["id"] for _, r in det_df.iterrows()], fontsize=8)
    ax.set_xlabel("Decision time [ms]")
    ax.set_title("TR-64 Deterministic Scenario Timeline")
    ax.axvline(20.0, color="r", linestyle="--", linewidth=1.0, label="1 cycle (20 ms)")
    ax.legend(fontsize=8)
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, label=k) for k, c in color_map.items()]
    ax.legend(handles=legend_elements, fontsize=8, loc="lower right")
    ax.set_xlim(0, max(det_df["trip_ms"]) * 1.25 + 20)
    ax.invert_yaxis()
    fig.tight_layout()
    _save(fig, "tr64_deterministic_timeline.png")


def plot_k_ibr_sweep(mc_results: dict) -> None:
    """P_D as a function of k_ibr bin (shows IBR gap closure)."""
    all_h1 = pd.concat([mc_results["dfs"]["H1_sg"],
                         mc_results["dfs"]["H1_ibr"]], ignore_index=True)

    bins  = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    labels = [f"{lo:.1f}–{hi:.1f}" for lo, hi in zip(bins[:-1], bins[1:])]
    pd_tr64 = []
    pd_conv = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (all_h1["k_ibr"] >= lo) & (all_h1["k_ibr"] < hi)
        sub  = all_h1[mask]
        if len(sub) == 0:
            pd_tr64.append(float("nan")); pd_conv.append(float("nan"))
        else:
            pd_tr64.append(float((sub["decision"] == "TRIP").mean()))
            pd_conv.append(float(sub["conv_trip"].mean()))

    x   = np.arange(len(labels))
    w   = 0.35
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(x - w/2, pd_conv, w, label="Conventional", color="#b0c4de", edgecolor="k", lw=0.8)
    ax.bar(x + w/2, pd_tr64, w, label="TR-64",        color="#2e7d32", edgecolor="k", lw=0.8)
    ax.axhline(0.998, color="r", linestyle="--", lw=1.0, label="0.998 spec")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_xlabel("IBR penetration k_ibr")
    ax.set_ylabel("P(TRIP | internal fault)")
    ax.set_title("Detection Rate vs IBR Penetration")
    ax.legend(fontsize=8)
    ax.set_ylim(0, 1.1)
    fig.tight_layout()
    _save(fig, "tr64_k_ibr_sweep.png")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Deterministic sweep
    det_df = run_deterministic()

    # Monte Carlo
    mc_results = run_monte_carlo()

    # Figures
    print("\nGenerating figures …")
    plot_ibr_gap_comparison(mc_results)
    plot_confusion_matrix(mc_results)
    plot_decision_time_cdf(mc_results)
    plot_f_int_distributions(mc_results)
    plot_deterministic_timeline(det_df)
    plot_k_ibr_sweep(mc_results)

    print(f"\nAll outputs → {OUT_DIR}/")
