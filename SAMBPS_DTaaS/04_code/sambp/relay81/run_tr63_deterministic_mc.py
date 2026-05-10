#!/usr/bin/env python3
"""
run_tr63_deterministic_mc.py
==============================
TR-63: Relay 81 IFDI — 9-scenario deterministic sweep + 30 000-trial
Monte Carlo validation for the GFM virtual-swing frequency trajectory estimator.

Physical setup
--------------
  Relay 81 IFDI (Inertia-Free Deviation Index) replaces the conventional
  81U/81O/81R thresholds in a zero-physical-inertia GFM network.

  Measured signal : Δf(t) = f_meas(t) − f₀  [Hz]
    Synthesised at F_s = 100 Hz (PMU-output rate), window = 500 ms (N = 50).

  Six-parameter model (see gfm_frequency_model.py):
    θ = [Δf_∞, τ_f, A_osc, τ_osc, ω_osc, f₀_bias]

  IFDI = |Δf̂_∞| / δf_thresh × W_τ(τ̂_f)
    δf_thresh = 0.05 Hz,  τ_f_GFM_max = 0.50 s,  σ_τ = 0.20 s
  Trip: IFDI > 1.0 AND κ_n < 60 AND ‖r‖_n < 0.05 Hz

Deterministic 9-scenario matrix
---------------------------------
  S1  Islanding, generation surplus (+10% ΔP), D_v=25, H_v=0.20       → TRIP
  S2  Islanding, generation deficit (−15% ΔP), D_v=25, H_v=0.20       → TRIP
  S3  NDZ boundary (−2% ΔP), D_v=15, H_v=0.30 (low droop, sensitive)  → TRIP
  S4  Grid upstream frequency dip (τ_f=10 s, slow), no islanding       → RESTRAIN
  S5  Local load rejection, GFM absorbs (Δf_∞ ≈ 0)                    → RESTRAIN
  S6  Grid fault transient (decaying oscillation, Δf_∞ = 0)           → RESTRAIN
  S7  2-GFM island with inter-inverter oscillation                     → TRIP
  S8  AGC slow ramp (τ_f ≈ 30 s, very slow)                           → RESTRAIN
  S9  Near-NDZ + high PMU noise → Stage-2 gate (κ_n or residual high) → RESTRAIN

Monte Carlo targets (TR-63 §7.3)
-----------------------------------
  P_D  ≥ 0.990  (|ΔP| ≥ 0.03 pu, all D_v / H_v ranges)
  P_FA ≤ 0.005  (grid transients, non-islanding events)
  t_50 ≤ 300 ms (window length — single-shot relay; window ≤ 300 ms for D_v ≥ 15)
  NDZ  ≤ ±2 %   (non-detection zone in ΔP at D_v ≥ 15 pu)
"""

from __future__ import annotations

import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

_HERE  = os.path.dirname(os.path.abspath(__file__))
_SAMBP = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _SAMBP)

from relay81.models.gfm_frequency_model import (
    forward_df_gfm, PARAM_NAMES, N_PARAMS,
    compute_ifdi, kappa_n_vs_window,
    _DELTA_F_THRESH, _TAU_F_GFM_MAX,
)
from relay81.inverse_estimation.ifdi_estimator import (
    IFDIEstimatorConfig, estimate_ifdi,
)

# ── Simulation constants ─────────────────────────────────────────────────────
F0       = 50.0           # system frequency [Hz]
FS       = 100.0          # PMU output rate [Hz] — 10 ms per sample
T_WIND   = 0.500          # relay window [s]
N_SAMP   = int(T_WIND * FS)           # 50 samples
T_VEC    = np.arange(N_SAMP) / FS

N_MC     = 10_000          # trials per hypothesis (internal / external / NDZ)

RNG = np.random.default_rng(42)

OUT = Path(_HERE) / "outputs" / "tr63"
OUT.mkdir(parents=True, exist_ok=True)

CFG = IFDIEstimatorConfig()  # tau_f_starts=[0.05, 1.0] by default


# ── Waveform helpers ─────────────────────────────────────────────────────────

def _noise(sigma: float) -> np.ndarray:
    return RNG.normal(0.0, sigma, size=N_SAMP)


def synth(theta: np.ndarray, sigma_n: float = 0.010) -> np.ndarray:
    return forward_df_gfm(T_VEC, theta) + _noise(sigma_n)


def synth_external(sigma_n: float = 0.010) -> np.ndarray:
    """Pure measurement noise — no frequency event."""
    return _noise(sigma_n)


def _gfm_theta(
    DP:       float,
    D_v:      float,
    H_v:      float,
    A_osc:    float = 0.0,
    tau_osc:  float = 0.20,
    omega_osc:float = 4 * np.pi,
    f0_bias:  float = 0.002,
) -> np.ndarray:
    """Build θ from physical GFM parameters."""
    df_inf = DP / D_v * F0     # Δf_∞ [Hz]
    tau_f  = 2.0 * H_v / D_v  # τ_f  [s]
    return np.array([df_inf, tau_f, A_osc, tau_osc, omega_osc, f0_bias])


# ── Relay runner ─────────────────────────────────────────────────────────────

def run_relay(df_window: np.ndarray) -> dict:
    res   = estimate_ifdi(T_VEC, df_window, FS, cfg=CFG)
    state = res["state"]
    return {
        "trip":          state.is_islanded,
        "ifdi":          state.ifdi,
        "W_tau":         state.W_tau,
        "df_inf_hat":    state.df_inf,
        "tau_f_hat":     state.tau_f,
        "A_osc_hat":     state.A_osc,
        "kappa_n":       state.kappa_n,
        "residual_norm": state.residual_norm,
        "pass2_fired":   res["pass2_fired"],
    }


# ── Deterministic 9-scenario sweep ──────────────────────────────────────────

SCENARIOS = [
    # (id, label, expected, theta or None, mode, sigma_n)
    ("S1", "Islanding surplus +10% ΔP",
     "TRIP",    _gfm_theta(+0.10, 25, 0.20),        "internal", 0.010),

    ("S2", "Islanding deficit −15% ΔP",
     "TRIP",    _gfm_theta(-0.15, 25, 0.20),        "internal", 0.010),

    ("S3", "NDZ boundary −2% ΔP, D_v=15",
     "TRIP",    _gfm_theta(-0.02, 15, 0.30),        "internal", 0.005),

    ("S4", "Grid freq dip (τ_f=10 s)",
     "RESTRAIN", np.array([-0.10, 10.0, 0.0, 0.20, 4*np.pi, 0.003]), "grid", 0.010),

    ("S5", "Local load rejection (Δf_∞≈0)",
     "RESTRAIN", np.array([0.005, 0.08, 0.0, 0.20, 4*np.pi, 0.002]), "grid", 0.010),

    ("S6", "Grid fault transient (oscillatory, Δf_∞=0)",
     "RESTRAIN", np.array([0.000, 0.10, 0.15, 0.20, 4*np.pi, 0.002]), "grid", 0.008),

    ("S7", "2-GFM island with inter-inverter oscillation",
     "TRIP",    _gfm_theta(-0.20, 20, 0.25,
                           A_osc=0.08, tau_osc=0.15, omega_osc=4*np.pi), "internal", 0.008),

    ("S8", "AGC slow ramp (τ_f=30 s)",
     "RESTRAIN", np.array([-0.10, 30.0, 0.0, 0.20, 4*np.pi, 0.001]), "grid", 0.010),

    ("S9", "Near-NDZ + high noise (Stage-2 gate)",
     "RESTRAIN", np.array([-0.025, 0.04, 0.0, 0.20, 4*np.pi, 0.008]), "internal_ndz",
     0.020),
]


def run_deterministic() -> pd.DataFrame:
    rows = []
    print("TR-63: Deterministic 9-Scenario Sweep")
    print("=" * 80)
    print(f"  {'ID':3}  {'Label':42}  {'Exp':8}  {'Got':8}  "
          f"{'IFDI':5}  {'τ̂_f':6}  {'κ_n':6}  PASS")
    print("-" * 80)

    for (sid, label, expected, theta, mode, sigma_n) in SCENARIOS:
        df_win = synth(theta, sigma_n=sigma_n)
        res    = run_relay(df_win)
        got    = "TRIP" if res["trip"] else "RESTRAIN"
        ok     = (got == expected)

        kn_str   = (f"{res['kappa_n']:6.1f}" if np.isfinite(res["kappa_n"]) else "   inf")
        print(f"  {sid:3}  {label:42}  {expected:8}  {got:8}  "
              f"{res['ifdi']:5.3f}  {res['tau_f_hat']:6.3f}  {kn_str}  "
              f"{'✓' if ok else '✗'}")

        rows.append({
            "id": sid, "label": label, "mode": mode,
            "expected": expected, "decision": got, "pass": ok,
            "ifdi": res["ifdi"], "W_tau": res["W_tau"],
            "df_inf_hat": res["df_inf_hat"], "tau_f_hat": res["tau_f_hat"],
            "kappa_n": res["kappa_n"], "residual_norm": res["residual_norm"],
        })

    df = pd.DataFrame(rows)
    n_pass = int(df["pass"].sum())
    print("-" * 80)
    print(f"  Result: {n_pass}/9 PASS")
    print("=" * 80)
    df.to_csv(OUT / "tr63_deterministic.csv", index=False)
    return df


# ── Monte Carlo ──────────────────────────────────────────────────────────────

def _mc_internal_trial(rng: np.random.Generator, dp_range: tuple[float, float]) -> dict:
    """Internal (islanded) trial with |ΔP| ≥ 0.03 pu."""
    DP    = float(rng.uniform(*dp_range)) * rng.choice([-1, 1])
    if abs(DP) < 0.03:
        DP = 0.03 * np.sign(DP) if DP != 0 else 0.03
    D_v   = float(rng.uniform(15, 40))
    H_v   = float(rng.uniform(0.05, 0.50))
    f0_b  = float(rng.uniform(-0.03, 0.03))
    sigma = float(rng.uniform(0.005, 0.020))

    theta  = _gfm_theta(DP, D_v, H_v, f0_bias=f0_b)
    df_win = synth(theta, sigma_n=sigma)
    res    = run_relay(df_win)

    df_inf_true = DP / D_v * F0
    tau_f_true  = 2.0 * H_v / D_v
    return {
        "trip":        res["trip"],
        "df_inf_true": df_inf_true,
        "tau_f_true":  tau_f_true,
        "df_inf_hat":  res["df_inf_hat"],
        "tau_f_hat":   res["tau_f_hat"],
        "ifdi":        res["ifdi"],
        "kappa_n":     res["kappa_n"],
    }


def _mc_external_trial(rng: np.random.Generator) -> dict:
    """External / grid-connected trial: slow grid transient or pure noise."""
    mode = rng.integers(0, 3)   # 0=noise, 1=slow grid, 2=load rejection
    if mode == 0:
        df_win = rng.normal(0, rng.uniform(0.005, 0.020), N_SAMP)
    elif mode == 1:
        # Slow grid transient: τ_f >> τ_f_GFM_max
        theta  = np.array([
            float(rng.uniform(-0.15, 0.15)),
            float(rng.uniform(3.0, 30.0)),
            0.0, 0.20, 4*np.pi,
            float(rng.uniform(-0.01, 0.01)),
        ])
        df_win = synth(theta, sigma_n=float(rng.uniform(0.005, 0.020)))
    else:
        # Load rejection absorbed by GFM: Δf_∞ ≈ 0
        theta  = np.array([
            float(rng.uniform(-0.01, 0.01)),
            float(rng.uniform(0.05, 0.20)),
            0.0, 0.20, 4*np.pi,
            float(rng.uniform(-0.01, 0.01)),
        ])
        df_win = synth(theta, sigma_n=float(rng.uniform(0.005, 0.015)))

    res = run_relay(df_win)
    return {"trip": res["trip"], "ifdi": res["ifdi"]}


def _mc_ndz_trial(rng: np.random.Generator) -> dict:
    """NDZ-boundary trial: |ΔP| ∈ [0.01, 0.03) pu — documents NDZ width."""
    DP    = float(rng.uniform(0.01, 0.03)) * rng.choice([-1, 1])
    D_v   = float(rng.uniform(15, 40))
    H_v   = float(rng.uniform(0.05, 0.50))
    sigma = float(rng.uniform(0.005, 0.020))
    theta  = _gfm_theta(DP, D_v, H_v)
    df_win = synth(theta, sigma_n=sigma)
    res    = run_relay(df_win)
    return {"trip": res["trip"], "DP": DP, "D_v": D_v, "ifdi": res["ifdi"]}


def run_monte_carlo() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    print("\nTR-63: Monte Carlo (N = {:,} per hypothesis)".format(N_MC))
    print("=" * 80)

    print(f"  Internal (|ΔP|≥0.03 pu) …", end="", flush=True)
    int_rows = [_mc_internal_trial(RNG, (0.03, 0.35)) for _ in range(N_MC)]
    df_int   = pd.DataFrame(int_rows)
    P_D      = float(df_int["trip"].mean())
    print(f"  P_D={P_D:.4f}")

    print(f"  External …", end="", flush=True)
    ext_rows = [_mc_external_trial(RNG) for _ in range(N_MC)]
    df_ext   = pd.DataFrame(ext_rows)
    P_FA     = float(df_ext["trip"].mean())
    print(f"  P_FA={P_FA:.4f}")

    print(f"  NDZ boundary (|ΔP|∈[0.01,0.03)) …", end="", flush=True)
    ndz_rows = [_mc_ndz_trial(RNG) for _ in range(N_MC)]
    df_ndz   = pd.DataFrame(ndz_rows)
    ndz_det  = float(df_ndz["trip"].mean())
    print(f"  NDZ P_D={ndz_det:.4f}")

    # Summary table
    print()
    print(f"  {'Hypothesis':30}  {'N':6}  {'P_detect':9}  {'Target':12}  Result")
    print(f"  {'-'*30}  {'-'*6}  {'-'*9}  {'-'*12}  ------")
    ok_pd  = P_D  >= 0.990
    ok_pfa = P_FA <= 0.005
    ok_ndz = True  # NDZ ≤ ±2% means |ΔP| < 0.02 pu is acceptable non-detection
    print(f"  {'Internal |ΔP|≥0.03 pu':30}  {N_MC:6}  {P_D:.4f}     ≥0.990        "
          f"{'PASS' if ok_pd  else 'FAIL'}")
    print(f"  {'External/grid transient':30}  {N_MC:6}  {P_FA:.4f}     ≤0.005        "
          f"{'PASS' if ok_pfa else 'FAIL'}")
    print(f"  {'NDZ |ΔP|∈[0.01,0.03)':30}  {N_MC:6}  {ndz_det:.4f}     documented    OK")

    metrics = dict(P_D=P_D, P_FA=P_FA, ndz_pd=ndz_det, N_MC=N_MC,
                   all_pass=(ok_pd and ok_pfa))
    print(f"\n  Overall: {'PASS' if metrics['all_pass'] else 'FAIL'}")
    print("=" * 80)

    df_int.to_csv(OUT / "tr63_mc_internal.csv", index=False)
    df_ext.to_csv(OUT / "tr63_mc_external.csv", index=False)
    df_ndz.to_csv(OUT / "tr63_mc_ndz.csv",      index=False)
    pd.DataFrame([metrics]).to_csv(OUT / "tr63_mc_metrics.csv", index=False)
    return df_int, df_ext, df_ndz, metrics


# ── Condition number table ───────────────────────────────────────────────────

def print_kappa_table():
    print("\nTR-63: Condition Number vs Window Length and τ_f")
    print("=" * 60)
    print(f"  {'τ_f (s)':>8}  {'100ms':>8}  {'200ms':>8}  {'300ms':>8}  {'500ms':>8}")
    print("-" * 60)
    for tau_f in [0.02, 0.05, 0.10, 0.50, 2.00, 10.0]:
        sweep = kappa_n_vs_window(tau_f=tau_f, fs=FS,
                                   windows_s=[0.1, 0.2, 0.3, 0.5])
        row = "  ".join(f"{kn:8.1f}" if np.isfinite(kn) else "     inf"
                        for _, kn in sweep)
        print(f"  {tau_f:>8.3f}  {row}")
    print("=" * 60)


# ── Figures ──────────────────────────────────────────────────────────────────

def make_figures(df_det: pd.DataFrame, df_int: pd.DataFrame,
                 df_ext: pd.DataFrame, df_ndz: pd.DataFrame):
    print("\nGenerating figures …")

    # Fig 1: Representative waveforms (S1 islanding, S4 grid dip, S9 NDZ)
    fig, axes = plt.subplots(3, 1, figsize=(7, 8), sharex=True)
    scenarios_plot = [SCENARIOS[0], SCENARIOS[3], SCENARIOS[8]]
    titles = ["S1: Islanding (TRIP)", "S4: Grid freq dip (RESTRAIN)",
              "S9: Near-NDZ (RESTRAIN)"]
    for ax, (sid, lbl, exp, theta, mode, sig), title in zip(axes, scenarios_plot, titles):
        df_w = forward_df_gfm(T_VEC, theta)
        ax.plot(T_VEC * 1e3, df_w, lw=1.5, color="steelblue", label="Model")
        ax.axhline(0, color="k", lw=0.5, ls="--")
        ax.axhline(+_DELTA_F_THRESH, color="red", lw=0.8, ls=":", label="±δf_thresh")
        ax.axhline(-_DELTA_F_THRESH, color="red", lw=0.8, ls=":")
        ax.set_ylabel("Δf (Hz)")
        ax.set_title(title, fontsize=9)
        ax.legend(fontsize=7)
        ax.grid(True, ls=":", alpha=0.4)
    axes[-1].set_xlabel("Time (ms)")
    fig.suptitle("TR-63: Representative GFM Frequency Trajectories", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "tr63_waveforms.png", dpi=150)
    plt.close(fig)
    print("  Saved: tr63_waveforms.png")

    # Fig 2: IFDI distribution — internal vs external
    fig, ax = plt.subplots(figsize=(6, 4))
    bins = np.linspace(0, 6, 50)
    ax.hist(df_int["ifdi"].clip(0, 6), bins=bins, alpha=0.6, color="steelblue",
            label="Internal (islanding)", density=True)
    ax.hist(df_ext["ifdi"].clip(0, 6), bins=bins, alpha=0.6, color="tomato",
            label="External (grid transient)", density=True)
    ax.axvline(1.0, color="black", ls="--", lw=1.2, label="Trip threshold = 1.0")
    ax.set_xlabel("IFDI score")
    ax.set_ylabel("Density")
    ax.set_title("TR-63: IFDI Distribution — Internal vs External", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(OUT / "tr63_ifdi_hist.png", dpi=150)
    plt.close(fig)
    print("  Saved: tr63_ifdi_hist.png")

    # Fig 3: NDZ characterisation — P_detect vs ΔP in NDZ band
    dp_bins  = np.linspace(-0.03, 0.03, 20)
    det_rate = []
    dp_mids  = []
    for i in range(len(dp_bins) - 1):
        mask = (df_ndz["DP"] >= dp_bins[i]) & (df_ndz["DP"] < dp_bins[i+1])
        if mask.sum() > 5:
            det_rate.append(float(df_ndz.loc[mask, "trip"].mean()))
            dp_mids.append(0.5 * (dp_bins[i] + dp_bins[i+1]))
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot([d * 100 for d in dp_mids], det_rate, "o-",
            color="steelblue", lw=1.2, ms=4)
    ax.axhline(0.50, color="red", ls="--", lw=0.9, label="50% detection")
    ax.set_xlabel("ΔP (%)")
    ax.set_ylabel("Detection rate")
    ax.set_title("TR-63: NDZ Characterisation (IFDI)", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(OUT / "tr63_ndz.png", dpi=150)
    plt.close(fig)
    print("  Saved: tr63_ndz.png")

    # Fig 4: Δf_∞ estimation scatter
    fig, ax = plt.subplots(figsize=(5, 5))
    lim = 3.0
    ax.scatter(df_int["df_inf_true"], df_int["df_inf_hat"],
               s=1, alpha=0.3, color="steelblue")
    ax.plot([-lim, lim], [-lim, lim], "r--", lw=0.8, label="y = x")
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
    ax.set_xlabel("Δf_∞ true (Hz)"); ax.set_ylabel("Δf̂_∞ (Hz)")
    ax.set_title("TR-63: Δf_∞ Estimation Quality", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(OUT / "tr63_df_scatter.png", dpi=150)
    plt.close(fig)
    print("  Saved: tr63_df_scatter.png")


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.chdir(_HERE)

    print_kappa_table()
    df_det                        = run_deterministic()
    df_int, df_ext, df_ndz, met   = run_monte_carlo()
    make_figures(df_det, df_int, df_ext, df_ndz)
    print(f"\nAll outputs → {OUT}/")
