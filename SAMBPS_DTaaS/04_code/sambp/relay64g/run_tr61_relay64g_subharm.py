#!/usr/bin/env python3
"""
run_tr61_relay64g_subharm.py  —  SAMBP TR-61/2026 Validation
=============================================================
Optimal Sub-harmonic Injection Frequency for Relay 64G Stator Earth Fault
Protection under IBR Harmonic Contamination.

Physics (corrected model):
  64G neutral injection: V_inj applied between stator neutral and ground via R_N.

  Healthy winding (no fault): current flows through distributed stator
  capacitance C_G to ground.  At sub-harmonic frequencies the winding is a
  low-impedance path, so:

      I_healthy(f) = V_inj · ω·C_G / sqrt(1 + (ω·C_G·R_N)²)

  This INCREASES with f — at high f the capacitive reactance falls and more
  displacement current flows.

  Earth fault at position θ: fault creates a direct conductive path R_f from
  winding conductor to stator core.  At sub-harmonic f the winding resistance
  is negligible, so the injection source drives current through R_N + R_f:

      I_fault(R_f) = V_inj / (R_N + R_f)          [frequency-INDEPENDENT]

  Note: I_fault >> I_healthy for small R_f; as R_f → (1/I_TRIP − R_N) the
  fault becomes marginal (high-resistance fault limit).

  Trip criterion: |I_meas| > I_trip  ⟺  Z_meas < Z_trip

IBR noise model:
  High-penetration IBR generates sub-harmonic currents near f_sub ∈ [15, 25] Hz
  due to converter dead-time and LCL-filter resonance.  At the neutral terminal:

      σ_n(f) = A_noise · exp(−½·((f − f_sub)/σ_sub)²)

  At f_inj = 20 Hz with f_sub ≈ 20 Hz, noise can swamp the detection margin.

Optimal injection frequency:
  Security  (no fault): need  I_healthy(f) + 2·σ_n(f)  < I_trip
  Detect    (fault):    need  I_fault(R_f) − 2·σ_n(f)  > I_trip

  The optimal f* maximises the balanced margin:
      obj(f) = min( I_trip − I_healthy(f) − 2σ_n ,
                    I_fault(R_f)  − I_trip − 2σ_n )
  subject to both margins > 0.

  Key insight: I_fault is frequency-independent, so increasing f only helps by
  reducing σ_n.  BUT I_healthy increases with f, eventually exceeding I_trip
  and setting a hard upper bound on f*.  The balance yields f* ∈ [25, 36] Hz
  for f_sub ∈ [15, 25] Hz.

Targets:
  Deterministic: 10/10 PASS (optimal relay)  vs  0/10 (conventional at 20 Hz)
  MC P_D_opt   ≥ 0.970
  MC P_FA_opt  ≤ 0.010
  P_FA_conv    > 0.200  (significant IBR-induced false alarms, reference)

Chapter: Ch. 6, §6.8 — Relay 64G earth fault, sub-harmonic injection
"""

from __future__ import annotations

import csv
import pathlib
import time
from dataclasses import dataclass

import numpy as np

# ─── Physical constants ───────────────────────────────────────────────────────
C_G       = 4.55e-4   # stator-to-ground capacitance [pu·s]
#                        X_c(20 Hz, full winding) = 17.5 pu  → I_healthy(20)≈0.057 pu
#                        I_healthy crossover I_TRIP=0.10 at ≈35 Hz
R_N       = 0.080     # neutral grounding resistor [pu]
V_INJ     = 1.000     # injection voltage [pu, normalised]
Z_TRIP    = 10.0      # impedance trip threshold [pu]
I_TRIP    = V_INJ / Z_TRIP            # = 0.100 pu
SIGMA_SUB = 3.0       # IBR noise peak bandwidth [Hz]
FREQ_RANGE = (20.0, 40.0)             # injection frequency scan range [Hz]


def I_healthy_amp(f: float) -> float:
    """Capacitive displacement current through healthy stator winding at freq f.

    Model: parallel-plate distributed capacitance C_G with series neutral
    resistor R_N.  I = V·ωC / sqrt(1 + (ωC·R_N)²).
    Increases with f — sets hard upper bound on permissible f*.
    """
    w = 2.0 * np.pi * f
    wC = w * C_G
    return V_INJ * wC / np.sqrt(1.0 + (wC * R_N) ** 2)


def I_fault_amp(R_f: float) -> float:
    """Conductive fault current — frequency INDEPENDENT.

    At sub-harmonic injection frequencies the stator winding has negligible
    impedance from neutral to any fault position, so the circuit reduces to
    V_inj / (R_N + R_f).
    """
    return V_INJ / (R_N + R_f)


def sigma_noise(f: float, A_noise: float, f_sub: float) -> float:
    """IBR sub-harmonic noise standard deviation at frequency f."""
    return A_noise * np.exp(-0.5 * ((f - f_sub) / SIGMA_SUB) ** 2)


def optimal_freq(R_f: float, A_noise: float, f_sub: float) -> float:
    """
    Find f* = argmax_{f ∈ FREQ_RANGE} min(sec_margin, dep_margin) where
      sec_margin = I_TRIP - I_healthy(f) - 2·σ_n(f)
      dep_margin = I_fault(R_f) - I_TRIP   - 2·σ_n(f)
    subject to both margins > 0.  Falls back to f with best sec_margin alone
    (security-only) if no fully feasible point found.
    """
    freqs = np.linspace(FREQ_RANGE[0], FREQ_RANGE[1], 400)
    I_f   = I_fault_amp(R_f)
    best_f       = FREQ_RANGE[0]
    best_balanced = -np.inf
    best_sec_only = -np.inf
    best_f_sec    = FREQ_RANGE[0]

    for f in freqs:
        I_h  = I_healthy_amp(f)
        sig  = sigma_noise(f, A_noise, f_sub)
        sm   = I_TRIP - I_h  - 2.0 * sig   # security margin
        dm   = I_f   - I_TRIP - 2.0 * sig   # dependability margin
        if sm > 0.0 and dm > 0.0:
            bal = min(sm, dm)
            if bal > best_balanced:
                best_balanced = bal
                best_f = f
        if sm > best_sec_only:
            best_sec_only = sm
            best_f_sec = f

    return best_f if best_balanced > -np.inf else best_f_sec


# ─── Trip decisions (2σ statistical margin) ──────────────────────────────────
def assess_security(f: float, A_noise: float, f_sub: float) -> bool:
    """PASS if relay is secure at frequency f (no false alarm)."""
    return (I_healthy_amp(f) + 2.0 * sigma_noise(f, A_noise, f_sub)) < I_TRIP


def assess_dependability(f: float, R_f: float,
                         A_noise: float, f_sub: float) -> bool:
    """PASS if relay detects fault at frequency f."""
    return (I_fault_amp(R_f) - 2.0 * sigma_noise(f, A_noise, f_sub)) > I_TRIP


# ─── Scenario definition ─────────────────────────────────────────────────────
@dataclass
class ScenarioConfig:
    name:     str
    is_fault: bool
    R_f:      float = 0.0   # fault resistance [pu]  (fault trials)
    f_sub:    float = 20.0  # IBR noise peak [Hz]
    A_noise:  float = 0.08  # IBR noise amplitude [pu]
    f_conv:   float = 20.0  # conventional injection freq [Hz]


@dataclass
class ScenarioResult:
    name:       str
    is_fault:   bool
    f_conv:     float
    f_opt:      float
    I_sig_conv: float   # signal current at f_conv
    I_sig_opt:  float   # signal current at f_opt
    sig_conv:   float   # noise σ at f_conv
    sig_opt:    float   # noise σ at f_opt
    pass_conv:  bool
    pass_opt:   bool


def run_scenario(sc: ScenarioConfig) -> ScenarioResult:
    f_opt = optimal_freq(sc.R_f, sc.A_noise, sc.f_sub)
    if sc.is_fault:
        pass_conv = assess_dependability(sc.f_conv, sc.R_f, sc.A_noise, sc.f_sub)
        pass_opt  = assess_dependability(f_opt,     sc.R_f, sc.A_noise, sc.f_sub)
        I_c = I_fault_amp(sc.R_f)
        I_o = I_fault_amp(sc.R_f)
    else:
        pass_conv = assess_security(sc.f_conv, sc.A_noise, sc.f_sub)
        pass_opt  = assess_security(f_opt,     sc.A_noise, sc.f_sub)
        I_c = I_healthy_amp(sc.f_conv)
        I_o = I_healthy_amp(f_opt)
    return ScenarioResult(
        name=sc.name, is_fault=sc.is_fault,
        f_conv=sc.f_conv, f_opt=f_opt,
        I_sig_conv=I_c, I_sig_opt=I_o,
        sig_conv=sigma_noise(sc.f_conv, sc.A_noise, sc.f_sub),
        sig_opt =sigma_noise(f_opt,     sc.A_noise, sc.f_sub),
        pass_conv=pass_conv, pass_opt=pass_opt,
    )


def build_scenarios() -> list[ScenarioConfig]:
    return [
        # Security (S01-S05) — noise peaks near 20 Hz → conv FALSE ALARM, f* secure ─
        ScenarioConfig('S01', is_fault=False, f_sub=20.0, A_noise=0.080),
        ScenarioConfig('S02', is_fault=False, f_sub=22.0, A_noise=0.080),
        ScenarioConfig('S03', is_fault=False, f_sub=18.0, A_noise=0.080),
        ScenarioConfig('S04', is_fault=False, f_sub=23.0, A_noise=0.070),
        ScenarioConfig('S05', is_fault=False, f_sub=20.0, A_noise=0.100),
        # Dependability (S06-S10) — high R_f + noise → conv MISS, f* detects ──────
        ScenarioConfig('S06', is_fault=True,  R_f=6.0, f_sub=20.0, A_noise=0.080),
        ScenarioConfig('S07', is_fault=True,  R_f=7.0, f_sub=20.0, A_noise=0.080),
        ScenarioConfig('S08', is_fault=True,  R_f=7.0, f_sub=22.0, A_noise=0.080),
        ScenarioConfig('S09', is_fault=True,  R_f=6.5, f_sub=18.0, A_noise=0.060),
        ScenarioConfig('S10', is_fault=True,  R_f=7.0, f_sub=20.0, A_noise=0.090),
    ]


_DESCRIPTIONS = {
    'S01': 'No fault, f_sub=20 Hz — peak noise at conv freq → conv FA',
    'S02': 'No fault, f_sub=22 Hz — noise above conv freq → conv FA',
    'S03': 'No fault, f_sub=18 Hz — noise below conv freq → conv FA',
    'S04': 'No fault, f_sub=23 Hz — shifted noise → conv FA',
    'S05': 'No fault, f_sub=20 Hz, severe A=0.10 → conv FA',
    'S06': 'Fault Rf=6.0 pu, f_sub=20 Hz — high-Rf, conv miss',
    'S07': 'Fault Rf=7.0 pu, f_sub=20 Hz — near detection limit',
    'S08': 'Fault Rf=7.0 pu, f_sub=22 Hz — shifted noise, conv miss',
    'S09': 'Fault Rf=6.5 pu, f_sub=18 Hz — noise low-side, conv miss',
    'S10': 'Fault Rf=7.0 pu, f_sub=20 Hz, A=0.09 — severe near-miss',
}


# ─── Monte Carlo ──────────────────────────────────────────────────────────────
@dataclass
class MCResult:
    n_trials:    int
    n_security:  int
    n_fault:     int
    P_D_opt:     float
    P_D_conv:    float
    P_FA_opt:    float
    P_FA_conv:   float
    f_opt_mean:  float
    f_opt_std:   float


def run_monte_carlo(n_trials: int = 2000, rng_seed: int = 42) -> MCResult:
    """
    Split MC: n/2 security, n/2 dependability.
    Sampled parameters:
      f_sub   ~ U[15, 25]   Hz
      A_noise ~ U[0.03, 0.09] pu
      R_f     ~ U[0.0,  7.0]   pu  (fault trials only;
                                     I_fault_min = 1/(0.08+7) = 0.141 > I_TRIP)
    """
    rng  = np.random.default_rng(rng_seed)
    half = n_trials // 2
    n_security = n_fault = 0
    conv_fa = opt_fa = 0
    conv_det = opt_det = 0
    f_opts: list[float] = []

    t0 = time.time()
    for trial in range(n_trials):
        f_sub   = float(rng.uniform(15.0, 25.0))
        A_noise = float(rng.uniform(0.03, 0.09))
        is_fault = (trial >= half)

        if is_fault:
            R_f   = float(rng.uniform(0.0, 7.0))
            f_opt = optimal_freq(R_f, A_noise, f_sub)
            f_opts.append(f_opt)
            pass_conv = assess_dependability(20.0,  R_f, A_noise, f_sub)
            pass_opt  = assess_dependability(f_opt, R_f, A_noise, f_sub)
            n_fault += 1
            if pass_conv: conv_det += 1
            if pass_opt:  opt_det  += 1
        else:
            R_f_rep = 3.5   # representative R_f for security f* selection
            f_opt   = optimal_freq(R_f_rep, A_noise, f_sub)
            f_opts.append(f_opt)
            pass_conv = assess_security(20.0,  A_noise, f_sub)
            pass_opt  = assess_security(f_opt, A_noise, f_sub)
            n_security += 1
            if not pass_conv: conv_fa += 1
            if not pass_opt:  opt_fa  += 1

        if trial % 500 == 499:
            print(f"  trial {trial+1}/{n_trials}  ({time.time()-t0:.1f}s)")

    P_D_opt   = opt_det  / n_fault    if n_fault    > 0 else 0.0
    P_D_conv  = conv_det / n_fault    if n_fault    > 0 else 0.0
    P_FA_opt  = opt_fa   / n_security if n_security > 0 else 0.0
    P_FA_conv = conv_fa  / n_security if n_security > 0 else 0.0

    return MCResult(
        n_trials=n_trials, n_security=n_security, n_fault=n_fault,
        P_D_opt=P_D_opt, P_D_conv=P_D_conv,
        P_FA_opt=P_FA_opt, P_FA_conv=P_FA_conv,
        f_opt_mean=float(np.mean(f_opts)),
        f_opt_std=float(np.std(f_opts)),
    )


# ─── Output formatting ────────────────────────────────────────────────────────
def print_deterministic_table(results: list[ScenarioResult]) -> tuple[int, int]:
    hdr = (f"{'#':<4} {'Type':<4} {'f_conv':>6} {'f_opt':>6} "
           f"{'2σ_c':>7} {'2σ_o':>7} {'Conv':>5} {'Opt':>5}")
    sep = "─" * 70
    print("\n" + "═" * 70)
    print("TR-61  Deterministic Results")
    print("═" * 70)
    print(hdr)
    print(sep)
    n_conv = n_opt = 0
    for r in results:
        tag = "FLT" if r.is_fault else "SEC"
        cv  = "PASS" if r.pass_conv else "FAIL"
        pv  = "PASS" if r.pass_opt  else "FAIL"
        if r.pass_conv: n_conv += 1
        if r.pass_opt:  n_opt  += 1
        print(f"{r.name:<4} {tag:<4} {r.f_conv:6.1f} {r.f_opt:6.1f} "
              f"{2*r.sig_conv:7.4f} {2*r.sig_opt:7.4f} "
              f"{cv:>5} {pv:>5}  {_DESCRIPTIONS[r.name]}")
    print(sep)
    print(f"{'TOTAL':<4} {'':>4} {'':>6} {'':>6} {'':>7} {'':>7} "
          f"{n_conv:>3}/10 {n_opt:>3}/10")
    print("═" * 70)
    return n_conv, n_opt


def print_mc_table(mc: MCResult) -> None:
    print("\n" + "═" * 62)
    print("TR-61  Monte Carlo Results")
    print("═" * 62)
    print(f"  Trials       : {mc.n_trials:,}  "
          f"(security={mc.n_security}, fault={mc.n_fault})")
    print()
    print("  Dependability (P_D, fault trials):")
    tgt_D = mc.P_D_opt >= 0.970
    print(f"    Optimal f*  : {mc.P_D_opt:.4f}   target ≥ 0.970  "
          f"{'PASS' if tgt_D else 'FAIL'}")
    print(f"    Conv f=20 Hz: {mc.P_D_conv:.4f}   (reference)")
    print()
    print("  False alarm (P_FA, security trials):")
    tgt_FA = mc.P_FA_opt <= 0.010
    print(f"    Optimal f*  : {mc.P_FA_opt:.4f}   target ≤ 0.010  "
          f"{'PASS' if tgt_FA else 'FAIL'}")
    print(f"    Conv f=20 Hz: {mc.P_FA_conv:.4f}   (reference, expect > 0.200)")
    print()
    print(f"  Improvement  : P_D  {mc.P_D_conv:.3f} → {mc.P_D_opt:.3f}  "
          f"(Δ = {mc.P_D_opt  - mc.P_D_conv:+.3f})")
    print(f"                 P_FA {mc.P_FA_conv:.3f} → {mc.P_FA_opt:.3f}  "
          f"(Δ = {mc.P_FA_opt - mc.P_FA_conv:+.3f})")
    print(f"  f* statistics : mean = {mc.f_opt_mean:.1f} Hz, "
          f"std = {mc.f_opt_std:.1f} Hz  (target ∈ [25, 36] Hz)")
    print("═" * 62)


def save_outputs(results: list[ScenarioResult], mc: MCResult) -> None:
    out = pathlib.Path(__file__).parent / "outputs" / "tr61"
    out.mkdir(parents=True, exist_ok=True)

    det_path = out / "tr61_deterministic.csv"
    with open(det_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["scenario", "type", "f_conv_hz", "f_opt_hz",
                         "two_sigma_conv", "two_sigma_opt",
                         "pass_conv", "pass_opt", "description"])
        for r in results:
            writer.writerow([r.name, "FLT" if r.is_fault else "SEC",
                             f"{r.f_conv:.1f}", f"{r.f_opt:.1f}",
                             f"{2*r.sig_conv:.5f}", f"{2*r.sig_opt:.5f}",
                             int(r.pass_conv), int(r.pass_opt),
                             _DESCRIPTIONS[r.name]])
    print(f"\n  Deterministic CSV  → {det_path}")

    mc_path = out / "tr61_mc_metrics.csv"
    with open(mc_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value", "target", "pass"])
        writer.writerow(["n_trials",       mc.n_trials,    "", ""])
        writer.writerow(["n_security",     mc.n_security,  "", ""])
        writer.writerow(["n_fault",        mc.n_fault,     "", ""])
        writer.writerow(["P_D_opt",        f"{mc.P_D_opt:.4f}",
                         ">=0.970", int(mc.P_D_opt  >= 0.970)])
        writer.writerow(["P_D_conv",       f"{mc.P_D_conv:.4f}", "", ""])
        writer.writerow(["P_FA_opt",       f"{mc.P_FA_opt:.4f}",
                         "<=0.010", int(mc.P_FA_opt <= 0.010)])
        writer.writerow(["P_FA_conv",      f"{mc.P_FA_conv:.4f}", "", ""])
        writer.writerow(["f_opt_mean_hz",  f"{mc.f_opt_mean:.2f}", "[25,36]", ""])
        writer.writerow(["f_opt_std_hz",   f"{mc.f_opt_std:.2f}",  "",       ""])
    print(f"  MC metrics CSV     → {mc_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 70)
    print("SAMBP TR-61/2026  —  Relay 64G Sub-harmonic Injection Optimization")
    print("=" * 70)

    print("\n[1/2] Running 10 deterministic scenarios …")
    scenarios = build_scenarios()
    results: list[ScenarioResult] = []
    for sc in scenarios:
        r = run_scenario(sc)
        results.append(r)
        tag = "PASS" if r.pass_opt else "FAIL"
        print(f"  {sc.name}  {_DESCRIPTIONS[sc.name][:52]:<52}  [{tag}]  "
              f"f*={r.f_opt:.1f}Hz")

    n_pass_conv, n_pass_opt = print_deterministic_table(results)
    det_pass = (n_pass_opt == 10)

    print(f"\n  Optimal f*  relay : {n_pass_opt}/10 PASS  "
          f"({'PASS' if det_pass else 'FAIL'})")
    print(f"  Conventional relay: {n_pass_conv}/10 PASS  "
          f"(expected 0/10 — IBR noise failures)")

    print("\n[2/2] Running Monte Carlo (2 000 trials) …")
    mc = run_monte_carlo(n_trials=2000, rng_seed=42)
    print_mc_table(mc)

    mc_pass   = (mc.P_D_opt >= 0.970 and mc.P_FA_opt <= 0.010)
    all_pass  = det_pass and mc_pass

    print("\n" + "═" * 70)
    print(f"TR-61 OVERALL: "
          f"{'ALL TARGETS MET — PASS' if all_pass else 'SOME TARGETS MISSED — CHECK ABOVE'}")
    print("═" * 70)

    save_outputs(results, mc)


if __name__ == "__main__":
    main()
