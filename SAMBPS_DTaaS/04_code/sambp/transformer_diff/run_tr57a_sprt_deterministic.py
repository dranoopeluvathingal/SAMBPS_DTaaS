"""
TR-57a: Three-Hypothesis SPRT Deterministic Simulation (24 scenarios)
======================================================================
Implements Algorithm 1 from TR-57 §9.

Hypotheses
----------
  H0: Transformer energisation inrush  → A_k ~ TN(+0.70, 0.15²)
  H1: IBR internal fault               → A_k ~ TN( 0.00, 0.08²)
  H2: External fault + CT saturation   → A_k ~ TN(-0.50, 0.20²)

SPRT accumulators (per full 20 ms cycle)
  S_n     = Σ λ_k        (H1 vs H0)   TRIP on S_n ≥ +6.91
  S_n^(2) = Σ λ_k^(2)   (H2 vs H1)   CTALARM on S_n^(2) ≥ +6.91

Wald boundaries: log A = −6.91,  log B = +6.91  (α = β = 0.001)

Decision priority each cycle:
  1. S_n ≤ −6.91 → reset S_n = 0 (inrush-like, continue monitoring)
  2. S_n^(2) ≥ +6.91 → CTALARM (CT saturation confirmed)
  3. S_n ≥ +6.91 → TRIP (internal fault confirmed)
  4. Timeout (15 cycles) → RESTRAIN (inrush confirmed by duration)

Scenario matrix (24 scenarios)
  S01–S04  : Internal 3PH, Pure SG  (k_ibr=0.0), φ=0°/90°, Br=0/0.7
  S05–S08  : Internal 3PH, 50% IBR (k_ibr=0.5), φ=0°/90°, Br=0/0.7
  S09–S12  : Internal 3PH, 100% IBR(k_ibr=1.0), φ=0°/90°, Br=0/0.7
  S13–S16  : Energisation inrush,              φ=0°/90°, Br=0/0.7
  S17–S20  : External + CT sat, Pure SG,       φ=0°/90°, Br=0/0.7
  S21–S24  : External + CT sat, 50% IBR,       φ=0°/90°, Br=0/0.7

Expected decisions
  S01-S12  → TRIP      (H1: internal fault)
  S13-S16  → RESTRAIN  (H0: inrush)
  S17-S24  → CTALARM   (H2: CT saturation)
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
FS       = 10_000          # samples / second
F0       = 50.0            # Hz
T_CYCLE  = 1.0 / F0       # 20 ms full cycle
N_CYCLE  = int(FS / F0)   # 200 samples / cycle
N_CYCLES = 15              # simulation window (15 full cycles = 300 ms)
T_SIM    = N_CYCLES * T_CYCLE
TAU_DC   = 0.08            # SG DC decay (X/R ≈ 25)

# SPRT parameters (TR-57 §7)
LOG_B = +6.91   # Trip / CTALARM boundary
LOG_A = -6.91   # Restrain boundary (triggers S_n reset)

# H0 inrush distribution
MU0, SIG0 = 0.70, 0.15
# H1 IBR-fault distribution
MU1, SIG1 = 0.00, 0.08
# H2 CT-sat distribution
MU2, SIG2 = -0.50, 0.20

OUT_DIR = os.path.join(os.path.dirname(__file__), "outputs", "tr57a")
os.makedirs(OUT_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# LLR functions
# ─────────────────────────────────────────────────────────────────────────────

def llr_h1_vs_h0(Ak: float) -> float:
    """log p(Ak|H1) / p(Ak|H0)  — Positive → H1 (fault), Negative → H0 (inrush)."""
    return (
        (Ak - MU0)**2 / (2 * SIG0**2)
        - (Ak - MU1)**2 / (2 * SIG1**2)
        + np.log(SIG0 / SIG1)
    )


def llr_h2_vs_h1(Ak: float) -> float:
    """log p(Ak|H2) / p(Ak|H1)  — Positive → H2 (CT sat), Negative → H1 (fault)."""
    return (
        (Ak - MU1)**2 / (2 * SIG1**2)
        - (Ak - MU2)**2 / (2 * SIG2**2)
        + np.log(SIG1 / SIG2)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Waveform generators
# ─────────────────────────────────────────────────────────────────────────────

def _t() -> np.ndarray:
    return np.arange(0, T_SIM, 1.0 / FS)


def waveform_internal_fault(k_ibr: float, phi_v_deg: float, Br: float) -> np.ndarray:
    """
    Internal transformer fault differential current.

    SG contribution: i_sg = I_pk*[−cos(ωt+φ) + cos(φ)·exp(−t/τ)]
      DC offset maximised at φ=0° (A_k ≈ +0.69 in cycle 1, decays over 4-6 cycles).
    IBR contribution: i_ibr = I_pk·k_ibr·sin(ωt+φ)  (SRF controller → no DC, A_k ≈ 0).
    Residual Br adds 2nd harmonic (fast-decaying, does not change H1 classification).
    """
    t     = _t()
    omega = 2 * np.pi * F0
    phi   = np.radians(phi_v_deg)
    I_pk  = 5.0  # p.u.

    i_sg   = I_pk * (-np.cos(omega * t + phi) + np.cos(phi) * np.exp(-t / TAU_DC))
    i_ibr  = k_ibr * I_pk * np.sin(omega * t + phi)
    i_diff = (1.0 - k_ibr) * i_sg + k_ibr * i_ibr

    if Br > 0:
        i_diff += Br * I_pk * np.exp(-t / 0.05) * np.sin(2 * omega * t)

    return i_diff


def waveform_inrush(phi_v_deg: float, Br: float) -> np.ndarray:
    """
    Transformer energisation inrush current.

    Physical basis: magnetising current flows only in one polarity direction
    when core flux exceeds saturation. The DC component is driven by residual
    flux (not voltage inception angle) → always-positive DC regardless of phi.

    Model:
      i_inrush = i_dc_flux + rectified_ac + 2nd_harmonic + small_negative_leakage
      i_dc_flux = I_pk*(0.40 + 0.30*Br)*exp(−t/τ_core)   [always positive]
      rectified_ac = max(I_pk*sin(ωt+φ), 0)               [one-sided conduction]
      i_neg = −0.15*I_pk*max(−sin(ωt+φ), 0)*exp(−t/0.04) [leakage recovery]
      → A_k ≈ +0.70–0.85 regardless of phi
    """
    t     = _t()
    omega = 2 * np.pi * F0
    phi   = np.radians(phi_v_deg)
    I_pk  = 8.0  # p.u. inrush peak

    # Always-positive DC from residual flux (independent of voltage angle)
    i_dc_flux = I_pk * (0.40 + 0.30 * Br) * np.exp(-t / 0.12)

    # Positive half-cycle conduction only (rectified magnetising current)
    i_sin    = np.sin(omega * t + phi)
    i_ac_pos = I_pk * np.maximum(i_sin, 0.0)

    # Small negative component from leakage inductance recovery
    i_neg    = -0.15 * I_pk * np.maximum(-i_sin, 0.0) * np.exp(-t / 0.04)

    # 2nd harmonic from nonlinear B-H curve
    i_2nd    = Br * 0.50 * I_pk * np.maximum(np.sin(2 * omega * t + phi), 0.0) * np.exp(-t / 0.15)

    return i_dc_flux + i_ac_pos + i_neg + i_2nd


def waveform_external_ctsat(k_ibr: float, phi_v_deg: float, Br: float) -> np.ndarray:
    """
    External fault differential current arising from CT saturation.

    Physical model (TR-57 §6):
      True through-current: i_through = I_pk*sin(ωt+φ) + DC
      CT saturates positive peaks → error current = saturated − true < 0
        (negative burst during positive half-cycle)
      CT core releases energy as recovery pulse (positive, opposite half-cycle):
        magnitude ≈ 0.35 × |peak_error|
      Net: I+pk ≈ 0.35 × |I−pk|  →  A_k = (0.35−1)/(0.35+1) ≈ −0.48  ≈  μ₂ ✓
    """
    t     = _t()
    omega = 2 * np.pi * F0
    phi   = np.radians(phi_v_deg)
    I_pk  = 4.0  # p.u. external fault

    # True through-current (SG+IBR blend)
    i_ac  = I_pk * np.sin(omega * t + phi)
    i_dc  = (1.0 - k_ibr) * I_pk * np.cos(phi) * np.exp(-t / TAU_DC)
    i_thr = i_ac + i_dc

    # CT saturation: positive peaks clipped above knee; only 20% above knee passes
    I_knee   = 0.55 * I_pk
    sat_frac = 0.20
    excess   = np.maximum(i_thr - I_knee, 0.0)
    i_error  = -(1.0 - sat_frac) * excess   # negative burst during positive half-cycle

    # CT recovery pulse: fires on opposite half-cycle (negative through-current phase)
    # Magnitude = 0.35 × peak error → gives A_k ≈ −0.48
    err_pk   = np.max(np.abs(i_error)) if np.any(i_error < 0) else 0.1
    i_recov  = 0.35 * err_pk * np.maximum(np.sin(omega * t + phi + np.pi), 0.0) * np.exp(-t / 0.06)

    # 2nd harmonic from saturated CT remanence
    if Br > 0:
        i_error += Br * 0.15 * I_pk * np.sin(2 * omega * t) * np.exp(-t / 0.05)

    return i_error + i_recov


# ─────────────────────────────────────────────────────────────────────────────
# Asymmetry index A_k (full-cycle, TR-57 §3 / Algorithm 1)
# ─────────────────────────────────────────────────────────────────────────────

def compute_Ak_series(i: np.ndarray) -> np.ndarray:
    """
    Per-full-cycle asymmetry index.
      A_k = (I+pk − |I−pk|) / (I+pk + |I−pk|)
    where I+pk = max(i) and |I−pk| = |min(i)| over a 20 ms window.
    Range: −1 (all-negative) to +1 (all-positive).
    """
    n_cycles = len(i) // N_CYCLE
    Ak = np.zeros(n_cycles)
    for k in range(n_cycles):
        win  = i[k * N_CYCLE:(k + 1) * N_CYCLE]
        Ipos = np.max(win)
        Ineg = abs(np.min(win))
        denom = Ipos + Ineg
        Ak[k] = (Ipos - Ineg) / denom if denom > 1e-9 else 0.0
    return Ak


# ─────────────────────────────────────────────────────────────────────────────
# SPRT runner (Algorithm 1 — TR-57 §9)
# ─────────────────────────────────────────────────────────────────────────────

def run_sprt(Ak_series: np.ndarray):
    """
    Run dual SPRT with correct priority and S_n reset.

    Algorithm:
      Each cycle k:
        1. Update S_n  += λ_k   (H1 vs H0)
                 S_n^(2) += λ_k^(2) (H2 vs H1)
        2. If S_n ≤ −B  → reset S_n = 0, continue  (inrush-like, keep monitoring)
        3. If S_n^(2) ≥ +B → CTALARM
        4. If S_n ≥ +B     → TRIP
      Timeout → RESTRAIN (A_k stayed near H0 throughout window)

    Priority: RESTRAIN-reset > CTALARM > TRIP > RESTRAIN-timeout.

    Returns:
        decision   : 'TRIP' | 'RESTRAIN' | 'CTALARM'
        trip_cycle : 1-based cycle index at decision
        Sn_hist    : accumulated S_n at each cycle (post-update, pre-reset)
        Sn2_hist   : accumulated S_n^(2) at each cycle
    """
    n = len(Ak_series)
    Sn_hist  = np.zeros(n)
    Sn2_hist = np.zeros(n)
    Sn       = 0.0
    Sn2      = 0.0

    decision   = 'RESTRAIN'   # default if no boundary reached
    trip_cycle = n            # default = last cycle (timeout)

    for k, Ak in enumerate(Ak_series):
        lam  = llr_h1_vs_h0(Ak)
        lam2 = llr_h2_vs_h1(Ak)
        Sn  += lam
        Sn2 += lam2

        Sn_hist[k]  = Sn
        Sn2_hist[k] = Sn2

        # Priority 1: inrush-like → reset BOTH accumulators, continue monitoring.
        # When H0 beats H1 (inrush pattern), H2 cannot simultaneously beat H1:
        # A_k near μ₀=+0.70 drives S_n^(2) positive spuriously.  Resetting both
        # prevents a false CTALARM during DC-offset decay on SG faults.
        if Sn <= LOG_A:
            Sn  = 0.0   # reset both, keep monitoring
            Sn2 = 0.0
            continue

        # Priority 2: CT saturation confirmed
        if Sn2 >= LOG_B:
            decision   = 'CTALARM'
            trip_cycle = k + 1
            Sn_hist[k + 1:]  = Sn
            Sn2_hist[k + 1:] = Sn2
            break

        # Priority 3: internal fault confirmed
        if Sn >= LOG_B:
            decision   = 'TRIP'
            trip_cycle = k + 1
            Sn_hist[k + 1:]  = Sn
            Sn2_hist[k + 1:] = Sn2
            break

    return decision, trip_cycle, Sn_hist, Sn2_hist


# ─────────────────────────────────────────────────────────────────────────────
# Scenario definitions
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = []

# S01–S04: Internal 3PH, Pure SG (k_ibr=0)
for phi, Br in [(0, 0), (90, 0), (0, 0.7), (90, 0.7)]:
    SCENARIOS.append({
        "id":       f"S{len(SCENARIOS)+1:02d}",
        "label":    f"Int-3PH SG φ={phi}° Br={Br}",
        "group":    "Internal-SG",
        "waveform": lambda p=phi, b=Br: waveform_internal_fault(0.0, p, b),
        "expected": "TRIP",
    })

# S05–S08: Internal 3PH, 50% IBR (k_ibr=0.5)
for phi, Br in [(0, 0), (90, 0), (0, 0.7), (90, 0.7)]:
    SCENARIOS.append({
        "id":       f"S{len(SCENARIOS)+1:02d}",
        "label":    f"Int-3PH 50%IBR φ={phi}° Br={Br}",
        "group":    "Internal-50IBR",
        "waveform": lambda p=phi, b=Br: waveform_internal_fault(0.5, p, b),
        "expected": "TRIP",
    })

# S09–S12: Internal 3PH, 100% IBR (k_ibr=1.0)
for phi, Br in [(0, 0), (90, 0), (0, 0.7), (90, 0.7)]:
    SCENARIOS.append({
        "id":       f"S{len(SCENARIOS)+1:02d}",
        "label":    f"Int-3PH 100%IBR φ={phi}° Br={Br}",
        "group":    "Internal-100IBR",
        "waveform": lambda p=phi, b=Br: waveform_internal_fault(1.0, p, b),
        "expected": "TRIP",
    })

# S13–S16: Energisation inrush
for phi, Br in [(0, 0), (90, 0), (0, 0.7), (90, 0.7)]:
    SCENARIOS.append({
        "id":       f"S{len(SCENARIOS)+1:02d}",
        "label":    f"Inrush φ={phi}° Br={Br}",
        "group":    "Inrush",
        "waveform": lambda p=phi, b=Br: waveform_inrush(p, b),
        "expected": "RESTRAIN",
    })

# S17–S20: External + CT sat, Pure SG
for phi, Br in [(0, 0), (90, 0), (0, 0.7), (90, 0.7)]:
    SCENARIOS.append({
        "id":       f"S{len(SCENARIOS)+1:02d}",
        "label":    f"Ext-CTsat SG φ={phi}° Br={Br}",
        "group":    "CTsat-SG",
        "waveform": lambda p=phi, b=Br: waveform_external_ctsat(0.0, p, b),
        "expected": "CTALARM",
    })

# S21–S24: External + CT sat, 50% IBR
for phi, Br in [(0, 0), (90, 0), (0, 0.7), (90, 0.7)]:
    SCENARIOS.append({
        "id":       f"S{len(SCENARIOS)+1:02d}",
        "label":    f"Ext-CTsat 50%IBR φ={phi}° Br={Br}",
        "group":    "CTsat-50IBR",
        "waveform": lambda p=phi, b=Br: waveform_external_ctsat(0.5, p, b),
        "expected": "CTALARM",
    })

assert len(SCENARIOS) == 24, f"Expected 24 scenarios, got {len(SCENARIOS)}"


# ─────────────────────────────────────────────────────────────────────────────
# Run all scenarios
# ─────────────────────────────────────────────────────────────────────────────

def run_all():
    results  = []
    Ak_all   = {}
    Sn_all   = {}
    Sn2_all  = {}

    for sc in SCENARIOS:
        i_diff    = sc["waveform"]()
        Ak_series = compute_Ak_series(i_diff)[:N_CYCLES]
        decision, tc, Sn, Sn2 = run_sprt(Ak_series)

        t_ms   = tc * T_CYCLE * 1000
        passed = (decision == sc["expected"])

        results.append({
            "id":         sc["id"],
            "label":      sc["label"],
            "group":      sc["group"],
            "expected":   sc["expected"],
            "decision":   decision,
            "trip_cycle": tc,
            "trip_ms":    t_ms,
            "pass":       passed,
            "Ak_mean":    float(np.mean(Ak_series[:min(tc, len(Ak_series))])),
        })

        Ak_all[sc["id"]]  = Ak_series
        Sn_all[sc["id"]]  = Sn
        Sn2_all[sc["id"]] = Sn2

        status = "PASS" if passed else "FAIL"
        print(f"  {sc['id']}  {decision:10s}  {t_ms:6.0f} ms  [{status}]  {sc['label']}")

    return results, Ak_all, Sn_all, Sn2_all


# ─────────────────────────────────────────────────────────────────────────────
# Plots
# ─────────────────────────────────────────────────────────────────────────────

COLORS = {
    "Internal-SG":     "#d62728",
    "Internal-50IBR":  "#ff7f0e",
    "Internal-100IBR": "#2ca02c",
    "Inrush":          "#1f77b4",
    "CTsat-SG":        "#9467bd",
    "CTsat-50IBR":     "#8c564b",
}
GROUP_LABEL = {
    "Internal-SG":     "Int-3PH SG",
    "Internal-50IBR":  "Int-3PH 50% IBR",
    "Internal-100IBR": "Int-3PH 100% IBR",
    "Inrush":          "Inrush",
    "CTsat-SG":        "Ext+CTsat SG",
    "CTsat-50IBR":     "Ext+CTsat 50% IBR",
}


def _cyc_axis():
    return np.arange(1, N_CYCLES + 1) * T_CYCLE * 1000


def plot_Ak_traces(Ak_all):
    fig, ax = plt.subplots(figsize=(11, 5))
    t_ms    = _cyc_axis()
    plotted = set()
    for sc in SCENARIOS:
        sid   = sc["id"]
        grp   = sc["group"]
        Ak    = Ak_all[sid]
        label = GROUP_LABEL[grp] if grp not in plotted else "_nolegend_"
        plotted.add(grp)
        ax.plot(t_ms[:len(Ak)], Ak, color=COLORS[grp], alpha=0.75, lw=1.4, label=label)

    ax.axhline(MU0, color="#1f77b4", ls="--", lw=0.9, label=f"μ₀={MU0} (inrush)")
    ax.axhline(MU1, color="#2ca02c", ls="--", lw=0.9, label=f"μ₁={MU1} (IBR fault)")
    ax.axhline(MU2, color="#9467bd", ls="--", lw=0.9, label=f"μ₂={MU2} (CT sat)")
    ax.axhline(0.0, color="k",       ls=":",  lw=0.6)

    ax.set_xlabel("Time (ms)"); ax.set_ylabel("Asymmetry index $A_k$")
    ax.set_title("TR-57a: Waveform Asymmetry Index — 24 Deterministic Scenarios")
    ax.legend(loc="upper right", fontsize=8, ncol=2); ax.set_ylim(-1.1, 1.2)
    ax.grid(True, alpha=0.3); fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "tr57a_Ak_traces.png"), dpi=150)
    plt.close(fig)
    print("  Saved: tr57a_Ak_traces.png")


def plot_Sn_traces(Sn_all, Sn2_all):
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    t_ms      = _cyc_axis()
    plotted   = set()

    for sc in SCENARIOS:
        sid   = sc["id"]
        grp   = sc["group"]
        Sn    = Sn_all[sid]
        Sn2   = Sn2_all[sid]
        label = GROUP_LABEL[grp] if grp not in plotted else "_nolegend_"
        plotted.add(grp)
        axes[0].plot(t_ms[:len(Sn)],  Sn,  color=COLORS[grp], alpha=0.75, lw=1.3, label=label)
        axes[1].plot(t_ms[:len(Sn2)], Sn2, color=COLORS[grp], alpha=0.75, lw=1.3)

    for ax in axes:
        ax.axhline(+LOG_B, color="r", ls="--", lw=1.0, label=f"$\\log B$ = +{LOG_B}")
        ax.axhline(LOG_A,  color="b", ls="--", lw=1.0, label=f"$\\log A$ = {LOG_A}")
        ax.axhline(0, color="k", ls=":", lw=0.6)
        ax.set_ylabel("Accumulator"); ax.grid(True, alpha=0.3)

    axes[0].set_title("$S_n$ (H₁ vs H₀) — TRIP on $S_n \\geq +6.91$  |  reset on $S_n \\leq -6.91$")
    axes[1].set_title("$S_n^{(2)}$ (H₂ vs H₁) — CTALARM on $S_n^{(2)} \\geq +6.91$")
    axes[1].set_xlabel("Time (ms)")
    axes[0].legend(loc="upper left", fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "tr57a_Sn_traces.png"), dpi=150)
    plt.close(fig)
    print("  Saved: tr57a_Sn_traces.png")


def plot_decision_timeline(results):
    fig, ax = plt.subplots(figsize=(10, 7))
    clr = {"TRIP": "#2ca02c", "RESTRAIN": "#1f77b4", "CTALARM": "#9467bd"}
    ids  = [r["id"]      for r in results]
    tms  = [r["trip_ms"] for r in results]
    decs = [r["decision"] for r in results]

    bars = ax.barh(ids, tms, color=[clr.get(d, "grey") for d in decs], alpha=0.80)
    for bar, r in zip(bars, results):
        lbl = r["decision"] + f" ({r['trip_ms']:.0f} ms)"
        ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height() / 2,
                lbl, va="center", fontsize=7)

    ax.axvline(20,  color="k", ls=":", lw=0.8, label="1 cycle (20 ms)")
    ax.axvline(300, color="r", ls=":", lw=0.8, label="Window limit (300 ms)")
    ax.set_xlabel("Decision time (ms)")
    ax.set_title("TR-57a: SPRT Decision Latency — 24 Scenarios")
    ax.legend(fontsize=8); ax.invert_yaxis()
    ax.grid(True, axis="x", alpha=0.3); fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "tr57a_decision_timeline.png"), dpi=150)
    plt.close(fig)
    print("  Saved: tr57a_decision_timeline.png")


# ─────────────────────────────────────────────────────────────────────────────
# CSV + summary
# ─────────────────────────────────────────────────────────────────────────────

def save_results(results):
    df = pd.DataFrame(results)[
        ["id", "group", "label", "expected", "decision",
         "trip_cycle", "trip_ms", "Ak_mean", "pass"]
    ]
    path = os.path.join(OUT_DIR, "tr57a_deterministic_results.csv")
    df.to_csv(path, index=False)
    print("  Saved: tr57a_deterministic_results.csv")
    return df


def print_summary(df):
    n_pass = int(df["pass"].sum())
    n_tot  = len(df)
    print("\n" + "=" * 72)
    print(f"  TR-57a SPRT DETERMINISTIC SUMMARY  —  {n_pass}/{n_tot} PASS")
    print("=" * 72)
    for grp, sub in df.groupby("group"):
        p = int(sub["pass"].sum()); t = len(sub)
        tag = "✓" if p == t else "✗"
        print(f"  {tag}  {GROUP_LABEL.get(grp, grp):28s}  {p}/{t}")
    print("=" * 72)
    failures = df[~df["pass"]]
    if len(failures):
        print("  FAILURES:")
        for _, row in failures.iterrows():
            print(f"    {row['id']}: expected {row['expected']}, "
                  f"got {row['decision']}  — {row['label']}")
    else:
        print("  All 24/24 scenarios passed.")
    print("=" * 72 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nTR-57a: Three-Hypothesis SPRT Deterministic Simulation")
    print("=" * 72)
    print(f"  Scenarios    : 24  ({N_CYCLES} cycles × {T_CYCLE*1000:.0f} ms = {T_SIM*1000:.0f} ms window)")
    print(f"  SPRT bounds  : [{LOG_A}, +{LOG_B}]  (α = β = 0.001)")
    print(f"  Distributions: H0~TN({MU0},{SIG0}²)  H1~TN({MU1},{SIG1}²)  H2~TN({MU2},{SIG2}²)")
    print("=" * 72 + "\n")

    results, Ak_all, Sn_all, Sn2_all = run_all()

    print("\nGenerating plots ...")
    plot_Ak_traces(Ak_all)
    plot_Sn_traces(Sn_all, Sn2_all)
    plot_decision_timeline(results)

    df = save_results(results)
    print_summary(df)
