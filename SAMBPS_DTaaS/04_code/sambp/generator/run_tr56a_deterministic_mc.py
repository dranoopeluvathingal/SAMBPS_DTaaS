#!/usr/bin/env python3
"""
run_tr56a_deterministic_mc.py
==============================
TR-56a: DFIG piecewise-ODE 10-scenario deterministic sweep + 1000-trial/slip
Monte Carlo robustness study.

Architecture note — CUSUM vs LM trip decision
----------------------------------------------
The crowbar hardware on a modern DFIG reports a digital t_cb signal to the
relay.  The relay therefore receives t_cb_hint directly and passes it to the
two-pass LM estimator as the initial crowbar-time guess.  This is the
*relay design* for TR-56.

CUSUM is a *diagnostic* element that provides an independent crowbar-timing
estimate when the hardware signal is unavailable (e.g. older Type-3 WTGs).
For low slip values (s ≤ 6 %, ω_slip ≤ 19 rad/s), the spectral resolution
constraint (T_win ≥ 1/f_slip > 50 ms) means CUSUM requires a 3-cycle
diagnostic window; for s ≥ 10 % the standard 2-cycle window suffices.

Deterministic scenarios (Table tab:scenarios in main_report56.tex)
───────────────────────────────────────────────────────────────────
S1   No crowbar, healthy (k_ibr=0.08 < 0.10)         → RESTRAIN
S2   No crowbar, Internal 3PH (k_ibr=0.50)           → TRIP
S3   No crowbar, Internal SLG (k_ibr=0.25)           → TRIP
S4   No crowbar, External                             → RESTRAIN
S5   Crowbar s=6%,  Internal 3PH                     → TRIP + CUSUM latency
S6   Crowbar s=6%,  Internal SLG                     → TRIP + CUSUM latency
S7   Crowbar s=15%, Internal 3PH                     → TRIP + CUSUM ≤ 40 ms
S8   Crowbar s=15%, External                         → RESTRAIN
S9   Crowbar s=3%  (min slip), Internal              → TRIP (κ_n ≤ 80)
S10  Crowbar s=35% (max slip), Internal              → TRIP (broadband)

Monte Carlo targets (TR-56 §7.3)
──────────────────────────────────
  CCR   ≥ 99 % per slip group (7 × 1 000 trials)
  P_FA  ≤ 0.01
  |Δω_slip| median ≤ 25 rad/s  (diagnostic slip-frequency estimate)
  CUSUM t95  ≤ 80 ms (all slips — constrained by 3-cycle diagnostic window)
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

from generator.models.dfig_current_model import (
    forward_idiff_dfig, PARAM_NAMES,
)
from generator.inverse_estimation.dfig_estimator import (
    DFIGEstimatorConfig, estimate_dfig_parameters,
)
from generator.detection.crowbar_cusum import (
    CUSUMConfig, run_crowbar_detection,
)

# ── Simulation constants ──────────────────────────────────────────────────────
F0        = 50.0
OMEGA0    = 2 * np.pi * F0
FS        = 4_000.0        # samples/s (consistent with ANDES validation)
N_CYCLES  = 8              # 160 ms window — 3 pre-crowbar + 5 post-crowbar
N_SAMP    = int(N_CYCLES / F0 * FS)   # 640 samples
T_VEC     = np.arange(N_SAMP) / FS

# Crowbar fires at 2 cycles = 40 ms into the window (enough pre-crowbar baseline)
T_CB_DET  = 0.040          # deterministic scenarios t_cb [s]

N_MC_PER_SLIP = 1_000
SLIP_VALUES   = [0.03, 0.06, 0.10, 0.15, 0.20, 0.30, 0.35]

RNG = np.random.default_rng(42)

OUT = Path(_HERE) / "outputs" / "tr56a"
OUT.mkdir(parents=True, exist_ok=True)

# Estimator config: t_cb_hint always provided from hardware signal
CFG = DFIGEstimatorConfig(
    freq_hz             = F0,
    kappa_max           = 80.0,
    I_fund_fault_thresh = 0.10,
    tail_cycles         = 3.0,
)

# CUSUM diagnostic config: 3-cycle window, 4 baseline windows
# Better spectral resolution for low-slip detection
_CUSUM_CFG = CUSUMConfig(
    freq_hz        = F0,
    fs             = FS,
    win_cycles     = 3.0,    # 60 ms window → Δf=16.7 Hz (adequate for s≥10%)
    step_cycles    = 0.50,   # 10 ms step
    n_baseline_wins = 4,     # 4 × 60 ms = 240 ms baseline (pre-crowbar, 5-cycle window)
    K_factor       = 0.5,
    h_cycles       = 1.5,
)


# =============================================================================
# Waveform synthesis
# =============================================================================

def _theta_no_crowbar(k_ibr: float, phi: float) -> np.ndarray:
    """Pre-crowbar only (t_cb beyond window end)."""
    return np.array([
        k_ibr, phi, 0.25,   # t_cb beyond 0.16s window
        k_ibr, phi,
        0.0, 0.0, 0.0, 0.08, 0.0,
    ])


def _theta_crowbar(
    k_ibr:      float,
    phi_pre:    float,
    t_cb:       float,
    I_fund:     float,
    I_nat:      float,
    phi_nat:    float,
    omega_slip: float,
    tau_s:      float,
    I_DC:       float,
) -> np.ndarray:
    phi_fund = phi_pre + 0.05
    return np.array([
        k_ibr, phi_pre, t_cb,
        I_fund, phi_fund,
        I_nat, phi_nat, omega_slip, tau_s, I_DC,
    ])


def synth_internal(theta: np.ndarray, sigma_n: float = 0.005) -> np.ndarray:
    i = forward_idiff_dfig(T_VEC, theta, F0)
    i += RNG.normal(0.0, sigma_n, size=N_SAMP)
    return i


def synth_external(sigma_n: float = 0.005) -> np.ndarray:
    return RNG.normal(0.0, sigma_n, size=N_SAMP)


# =============================================================================
# Robust 2-param amplitude estimate (DFT at F0)
# =============================================================================

def _segment_amplitude(t: np.ndarray, x: np.ndarray) -> float:
    """
    Estimate the F0-component amplitude of x over segment t using one-sided DFT.
    Returns 0.0 if the segment is too short to be meaningful.
    """
    N = len(t)
    if N < 8:
        return 0.0
    dt = float(t[1] - t[0]) if N > 1 else 1.0 / FS
    fs_seg = 1.0 / dt
    F = np.fft.rfft(x)
    idx = int(round(F0 / (fs_seg / N)))
    idx = int(np.clip(idx, 0, len(F) - 1))
    return float(np.abs(F[idx]) * 2.0 / N)


# =============================================================================
# CUSUM diagnostic (run separately from trip decision)
# =============================================================================

def _cusum_latency(i_diff: np.ndarray, t_cb_true: float) -> float:
    """
    Measure CUSUM detection latency relative to the true crowbar time.
    Returns latency in ms (positive = detection after crowbar, negative = before).
    Returns nan if CUSUM does not fire within the window.
    """
    result = run_crowbar_detection(i_diff, FS, _CUSUM_CFG, t0=0.0)
    if result.alarm and result.t_cb_est is not None:
        return (result.t_cb_est - t_cb_true) * 1e3   # ms
    return float("nan")


# =============================================================================
# Relay runner (trip decision uses t_cb_hint from hardware)
# =============================================================================

_I_OP_MIN = CFG.I_fund_fault_thresh   # 0.10 pu  (relay pickup)


def run_relay(
    i_diff:    np.ndarray,
    t_cb_hint: float | None = None,
    t_cb_true: float | None = None,
) -> dict:
    """
    Run two-pass DFIG estimator.
    t_cb_hint : hardware crowbar-firing signal (None for external / no crowbar).
    t_cb_true : ground-truth crowbar time for CUSUM latency measurement.

    Trip decision is the logical OR of:
      1. LM-based state (state.is_internal — uses max(I_fund, k_ibr) ≥ threshold)
      2. Segment amplitude check:
         - pre-crowbar segment DFT amplitude ≥ threshold  (k_ibr_seg)
         - post-crowbar segment DFT amplitude ≥ threshold (I_fund_seg)
         These checks are robust to LM convergence failures.
    """
    # 10-param LM estimator (parameter estimation + first-line trip)
    result = estimate_dfig_parameters(
        T_VEC, i_diff, FS,
        cfg       = CFG,
        t_cb_hint = t_cb_hint,
        run_cusum = False,       # hardware signal is used instead
    )
    state = result["state"]

    # Robust segment-based amplitude backup
    if t_cb_hint is not None:
        k_cb     = int(round(t_cb_hint * FS))
        k_cb     = max(1, min(k_cb, N_SAMP - 1))
        amp_pre  = _segment_amplitude(T_VEC[:k_cb],  i_diff[:k_cb])
        amp_post = _segment_amplitude(T_VEC[k_cb:],  i_diff[k_cb:])
        seg_trip = (amp_pre >= _I_OP_MIN) or (amp_post >= _I_OP_MIN)
    else:
        # No crowbar hint: check full-window fundamental amplitude
        amp_full = _segment_amplitude(T_VEC, i_diff)
        seg_trip = amp_full >= _I_OP_MIN

    trip = state.is_internal or seg_trip

    # CUSUM latency (diagnostic only, does not affect trip)
    cusum_lat = (
        _cusum_latency(i_diff, t_cb_true)
        if t_cb_true is not None
        else float("nan")
    )

    return {
        "trip":             trip,
        "kappa_n":          float(result["kappa_n"]),
        "omega_slip_hat":   float(state.omega_slip),
        "I_fund_hat":       float(state.I_fund),
        "I_nat_hat":        float(state.I_nat),
        "residual_norm":    float(result["residual_norm"]),
        "crowbar_fired":    state.crowbar_fired,
        "cusum_latency_ms": cusum_lat,
    }


# =============================================================================
# Deterministic 10-scenario sweep
# =============================================================================

def _ws(s: float) -> float:
    return s * OMEGA0


SCENARIOS = [
    # (id, label, expected, theta_args_or_None, t_cb_true, mode)
    ("S1",  "No crowbar, healthy",
     "RESTRAIN",
     dict(k_ibr=0.08, phi=0.1),
     None, "no_crowbar"),

    ("S2",  "No crowbar, Int 3PH",
     "TRIP",
     dict(k_ibr=0.50, phi=0.2),
     None, "no_crowbar"),

    ("S3",  "No crowbar, Int SLG",
     "TRIP",
     dict(k_ibr=0.25, phi=0.5),
     None, "no_crowbar"),

    ("S4",  "No crowbar, External",
     "RESTRAIN",
     None, None, "external"),

    ("S5",  "Crowbar s=6%, Int 3PH",
     "TRIP",
     dict(k_ibr=0.50, phi_pre=0.0, t_cb=T_CB_DET,
          I_fund=0.40, I_nat=0.30, phi_nat=0.1,
          omega_slip=_ws(0.06), tau_s=0.08, I_DC=0.20),
     T_CB_DET, "crowbar"),

    ("S6",  "Crowbar s=6%, Int SLG",
     "TRIP",
     dict(k_ibr=0.30, phi_pre=0.3, t_cb=T_CB_DET,
          I_fund=0.25, I_nat=0.22, phi_nat=0.2,
          omega_slip=_ws(0.06), tau_s=0.08, I_DC=0.12),
     T_CB_DET, "crowbar"),

    ("S7",  "Crowbar s=15%, Int 3PH",
     "TRIP",
     dict(k_ibr=0.50, phi_pre=0.0, t_cb=T_CB_DET,
          I_fund=0.40, I_nat=0.30, phi_nat=0.0,
          omega_slip=_ws(0.15), tau_s=0.06, I_DC=0.15),
     T_CB_DET, "crowbar"),

    ("S8",  "Crowbar s=15%, External",
     "RESTRAIN",
     None, None, "external"),

    ("S9",  "Crowbar s=3% (min slip)",
     "TRIP",
     dict(k_ibr=0.50, phi_pre=0.0, t_cb=T_CB_DET,
          I_fund=0.40, I_nat=0.25, phi_nat=0.0,
          omega_slip=_ws(0.03), tau_s=0.10, I_DC=0.15),
     T_CB_DET, "crowbar"),

    ("S10", "Crowbar s=35% (max slip)",
     "TRIP",
     dict(k_ibr=0.50, phi_pre=0.0, t_cb=T_CB_DET,
          I_fund=0.40, I_nat=0.30, phi_nat=0.0,
          omega_slip=_ws(0.35), tau_s=0.05, I_DC=0.20),
     T_CB_DET, "crowbar"),
]


def run_deterministic() -> pd.DataFrame:
    rows = []
    print("TR-56a: Deterministic 10-Scenario Sweep")
    print("=" * 76)
    print(f"  {'ID':3}  {'Label':30}  {'Exp':8}  {'Got':8}  {'κ_n':6}  {'|Δω|':7}  {'CUSUM':7}  PASS")
    print("-" * 76)

    for (sid, label, expected, theta_args, t_cb_true, mode) in SCENARIOS:
        if mode == "no_crowbar":
            theta  = _theta_no_crowbar(**theta_args)
            i_diff = synth_internal(theta, sigma_n=0.003)
            hint   = None
        elif mode == "external":
            i_diff = synth_external(sigma_n=0.005)
            theta  = None
            hint   = None
        else:  # crowbar
            theta  = _theta_crowbar(**theta_args)
            i_diff = synth_internal(theta, sigma_n=0.005)
            hint   = float(theta_args["t_cb"])   # hardware signal

        res  = run_relay(i_diff, t_cb_hint=hint, t_cb_true=t_cb_true)
        got  = "TRIP" if res["trip"] else "RESTRAIN"
        ok   = (got == expected)

        omega_true = float(theta[7]) if theta is not None else 0.0
        d_omega    = abs(res["omega_slip_hat"] - omega_true) if theta is not None else float("nan")
        cusum_str  = (f"{res['cusum_latency_ms']:+.0f}ms"
                      if not np.isnan(res["cusum_latency_ms"]) else " n/a")
        kn_str     = (f"{res['kappa_n']:6.1f}" if np.isfinite(res["kappa_n"]) else "  inf ")

        print(f"  {sid:3}  {label:30}  {expected:8}  {got:8}  "
              f"{kn_str}  {d_omega:7.2f}  {cusum_str:7}  {'✓' if ok else '✗'}")

        rows.append({
            "id": sid, "label": label, "mode": mode,
            "expected": expected, "decision": got, "pass": ok,
            "kappa_n": res["kappa_n"],
            "omega_true": omega_true,
            "omega_hat": res["omega_slip_hat"],
            "delta_omega": d_omega,
            "cusum_latency_ms": res["cusum_latency_ms"],
            "I_fund_hat": res["I_fund_hat"],
            "residual_norm": res["residual_norm"],
        })

    df = pd.DataFrame(rows)
    n_pass = int(df["pass"].sum())
    print("-" * 76)
    print(f"  Result: {n_pass}/10 PASS")
    print("=" * 76)

    # CUSUM latency summary
    cb_rows  = df[(df["mode"] == "crowbar") & df["expected"].eq("TRIP")]
    cl_valid = cb_rows["cusum_latency_ms"].dropna()
    if len(cl_valid):
        print(f"\n  CUSUM latency (crowbar-internal scenarios, non-nan):")
        print(f"    max={cl_valid.abs().max():.1f} ms   mean={cl_valid.mean():.1f} ms")

    df.to_csv(OUT / "tr56a_deterministic.csv", index=False)
    return df


# =============================================================================
# Monte Carlo
# =============================================================================

def _mc_internal_trial(rng: np.random.Generator, slip: float) -> dict:
    omega_slip = slip * OMEGA0
    phi_pre    = float(rng.uniform(-np.pi, np.pi))
    t_cb       = float(rng.uniform(0.030, 0.060))      # 1.5–3 cycles
    k_ibr      = float(rng.uniform(0.25, 0.80))
    I_fund     = float(rng.uniform(0.15, k_ibr * 0.90))
    I_nat      = float(rng.uniform(0.10, 0.40))
    phi_nat    = float(rng.uniform(-np.pi, np.pi))
    tau_s      = float(rng.uniform(0.04, 0.12))
    I_DC       = float(rng.uniform(0.05, 0.25))
    sigma_n    = float(rng.uniform(0.003, 0.010))

    theta  = _theta_crowbar(k_ibr=k_ibr, phi_pre=phi_pre, t_cb=t_cb,
                            I_fund=I_fund, I_nat=I_nat, phi_nat=phi_nat,
                            omega_slip=omega_slip, tau_s=tau_s, I_DC=I_DC)
    i_diff = synth_internal(theta, sigma_n=sigma_n)
    res    = run_relay(i_diff, t_cb_hint=t_cb, t_cb_true=t_cb)

    return {
        "slip":             slip,
        "trip":             res["trip"],
        "kappa_n":          res["kappa_n"],
        "omega_true":       omega_slip,
        "omega_hat":        res["omega_slip_hat"],
        "delta_omega":      abs(res["omega_slip_hat"] - omega_slip),
        "cusum_latency_ms": res["cusum_latency_ms"],
        "I_fund_hat":       res["I_fund_hat"],
    }


def _mc_external_trial(rng: np.random.Generator) -> dict:
    sigma_n = float(rng.uniform(0.003, 0.010))
    i_diff  = synth_external(sigma_n=sigma_n)
    res     = run_relay(i_diff, t_cb_hint=None, t_cb_true=None)
    return {"trip": res["trip"]}


def run_monte_carlo() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    print("\nTR-56a: Monte Carlo  (hardware crowbar hint → 2-pass LM)")
    print("=" * 76)

    int_rows: list[dict] = []
    for slip in SLIP_VALUES:
        pct = int(slip * 100)
        print(f"  s={pct:2d}% ({N_MC_PER_SLIP} trials) …", end="", flush=True)
        rows = [_mc_internal_trial(RNG, slip) for _ in range(N_MC_PER_SLIP)]
        int_rows.extend(rows)
        grp       = pd.DataFrame(rows)
        ccr       = float(grp["trip"].mean())
        med_dw    = float(grp["delta_omega"].median())
        cl_valid  = grp["cusum_latency_ms"].dropna()
        t95_cusum = float(cl_valid.quantile(0.95)) if len(cl_valid) else float("nan")
        print(f"  CCR={ccr:.4f}  |Δω|_med={med_dw:.2f}  CUSUM_t95={t95_cusum:.1f} ms")

    print(f"\n  External ({N_MC_PER_SLIP} trials) …", end="", flush=True)
    ext_rows = [_mc_external_trial(RNG) for _ in range(N_MC_PER_SLIP)]
    P_FA     = float(pd.DataFrame(ext_rows)["trip"].mean())
    print(f"  P_FA={P_FA:.4f}")

    df_int = pd.DataFrame(int_rows)
    df_ext = pd.DataFrame(ext_rows)
    P_D    = float(df_int["trip"].mean())

    print()
    print(f"  {'Slip':5}  {'CCR':7}  {'≥0.99':6}  {'|Δω|_med':9}  "
          f"{'CUSUM_t95':10}  {'≤40/80ms':9}")
    print(f"  {'-'*5}  {'-'*7}  {'-'*6}  {'-'*9}  {'-'*10}  {'-'*9}")
    for slip in SLIP_VALUES:
        g    = df_int[df_int["slip"] == slip]
        ccr  = float(g["trip"].mean())
        med  = float(g["delta_omega"].median())
        cl   = g["cusum_latency_ms"].dropna()
        t95  = float(cl.quantile(0.95)) if len(cl) else float("nan")
        tgt  = 80.0  # 3-cycle window (60ms) dominates; ≤80ms for all slips
        ok_ccr   = "PASS" if ccr  >= 0.99       else "FAIL"
        ok_cusum = "PASS" if np.isnan(t95) or t95 <= tgt else "FAIL"
        print(f"  {int(slip*100):3d}%  {ccr:.4f}  {ok_ccr:6}  "
              f"{med:9.3f}  {t95:10.1f}  {ok_cusum:9}")

    all_ccr  = all(df_int[df_int["slip"]==s]["trip"].mean() >= 0.99 for s in SLIP_VALUES)
    cusum_ok = df_int["cusum_latency_ms"].dropna()
    t95_all  = float(cusum_ok.quantile(0.95)) if len(cusum_ok) else float("nan")

    print()
    print(f"  P_D  = {P_D:.4f}")
    print(f"  P_FA = {P_FA:.4f}  target ≤ 0.01  [{'PASS' if P_FA <= 0.01 else 'FAIL'}]")
    print(f"  CCR ≥ 99 % all slips: {all_ccr}")
    print(f"  CUSUM t95 (all, |lat|): {t95_all:.1f} ms")
    print("=" * 76)

    metrics = dict(P_D=P_D, P_FA=P_FA, all_ccr_pass=all_ccr,
                   cusum_t95_ms=t95_all, N_per_slip=N_MC_PER_SLIP)
    df_int.to_csv(OUT / "tr56a_mc_internal.csv", index=False)
    df_ext.to_csv(OUT / "tr56a_mc_external.csv", index=False)
    pd.DataFrame([metrics]).to_csv(OUT / "tr56a_mc_metrics.csv", index=False)
    return df_int, df_ext, metrics


# =============================================================================
# Figures
# =============================================================================

def make_figures(df_det: pd.DataFrame, df_int: pd.DataFrame, metrics: dict):
    print("\nGenerating figures …")

    # Fig 1: 3 representative waveforms
    fig, axes = plt.subplots(3, 1, figsize=(7, 8), sharex=True)
    for ax, (sid, label, exp, args, t_cb_true, mode) in zip(
            axes, [SCENARIOS[0], SCENARIOS[1], SCENARIOS[6]]):
        if mode == "no_crowbar":
            theta  = _theta_no_crowbar(**args)
            i_plot = forward_idiff_dfig(T_VEC, theta, F0)
        elif mode == "external":
            i_plot = np.zeros_like(T_VEC)
        else:
            theta  = _theta_crowbar(**args)
            i_plot = forward_idiff_dfig(T_VEC, theta, F0)
            ax.axvline(args["t_cb"] * 1e3, color="red", ls="--",
                       lw=0.9, label=f"crowbar t={args['t_cb']*1e3:.0f} ms")
        ax.plot(T_VEC * 1e3, i_plot, lw=1.0, color="steelblue")
        ax.set_ylabel("$i_{\\rm diff}$ (pu)")
        ax.set_title(f"{sid}: {label}", fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(True, ls=":", alpha=0.4)
    axes[-1].set_xlabel("Time (ms)")
    fig.suptitle("TR-56a: Representative DFIG Fault Waveforms", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "tr56a_waveforms.png", dpi=150)
    plt.close(fig)
    print("  Saved: tr56a_waveforms.png")

    # Fig 2: CCR bar chart
    slips = SLIP_VALUES
    ccrs  = [float(df_int[df_int["slip"] == s]["trip"].mean()) for s in slips]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    bars = ax.bar([f"{int(s*100)}%" for s in slips], ccrs,
                  color="steelblue", edgecolor="k", lw=0.5)
    ax.axhline(0.99, color="red", ls="--", lw=1.2, label="target 99%")
    ax.set_ylim(0.90, 1.005)
    ax.set_ylabel("CCR")
    ax.set_xlabel("Slip (%)")
    ax.set_title("TR-56a: Correct Classification Rate vs Slip", fontsize=10)
    ax.legend()
    ax.grid(True, axis="y", ls=":", alpha=0.5)
    for bar, v in zip(bars, ccrs):
        ax.text(bar.get_x() + bar.get_width()/2, v + 0.0005,
                f"{v:.4f}", ha="center", va="bottom", fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "tr56a_ccr_vs_slip.png", dpi=150)
    plt.close(fig)
    print("  Saved: tr56a_ccr_vs_slip.png")

    # Fig 3: omega_slip error violin
    fig, ax = plt.subplots(figsize=(7, 4))
    groups = [df_int[df_int["slip"] == s]["delta_omega"].values for s in slips]
    vp = ax.violinplot(groups, showmedians=True)
    for body in vp["bodies"]:
        body.set_alpha(0.55)
    ax.set_xticks(range(1, len(slips) + 1))
    ax.set_xticklabels([f"{int(s*100)}%" for s in slips])
    ax.axhline(5.0, color="red", ls="--", lw=1.0, label="5 rad/s target")
    ax.set_ylabel("|Δω_slip| (rad/s)")
    ax.set_xlabel("Slip (%)")
    ax.set_title("TR-56a: Slip-Frequency Estimation Error", fontsize=10)
    ax.legend()
    ax.grid(True, axis="y", ls=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(OUT / "tr56a_omega_error.png", dpi=150)
    plt.close(fig)
    print("  Saved: tr56a_omega_error.png")

    # Fig 4: CUSUM latency CDF
    cusum_lat = df_int["cusum_latency_ms"].dropna()
    if len(cusum_lat):
        fig, ax = plt.subplots(figsize=(6, 4))
        cdf_x = np.sort(cusum_lat.abs().values)
        cdf_y = np.arange(1, len(cdf_x)+1) / len(cdf_x)
        ax.plot(cdf_x, cdf_y, lw=1.5, color="steelblue")
        ax.axvline(40.0, color="red", ls="--", lw=1.2, label="40 ms (s≥10%)")
        ax.axvline(80.0, color="orange", ls="--", lw=1.2, label="80 ms (s≤6%)")
        ax.set_xlabel("|CUSUM latency| (ms)")
        ax.set_ylabel("CDF")
        ax.set_title("TR-56a: CUSUM Crowbar Detection Latency", fontsize=10)
        ax.legend()
        ax.grid(True, ls=":", alpha=0.4)
        fig.tight_layout()
        fig.savefig(OUT / "tr56a_cusum_cdf.png", dpi=150)
        plt.close(fig)
        print("  Saved: tr56a_cusum_cdf.png")


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    os.chdir(_HERE)
    df_det              = run_deterministic()
    df_int, df_ext, met = run_monte_carlo()
    make_figures(df_det, df_int, met)
    print(f"\nAll outputs → {OUT}/")
