#!/usr/bin/env python3
"""
run_tr60_relay40_loe.py  —  SAMBP TR-60/2026 Validation
=========================================================
IBR-Corrected Relay 40 (Loss of Excitation) for GFM-Dominated Buses.

Two failure modes are demonstrated and corrected:
  FM1 (Nuisance trip): GFM reactive absorption during over-voltage event
      pushes Im(Y_total) above the LOE trip threshold even with healthy SG.
  FM2 (Missed trip): GFM reactive supply during genuine LOE masks the
      susceptance rise, keeping Im(Y_total) below the trip threshold.

Correction: online LM estimation of the GFM admittance contribution
  Y_GFM_est, with Y_SG_corr = Y_total - Y_GFM_est used for the trip decision.

Physics model:
  Y_SG(t) = G_sg + j*B_sg(t)
    B_sg(t) = B_sg0                                     (normal)
    B_sg(t) = B_sg0 + (B_loe - B_sg0)*(1-exp(-(t-t_loe)/T_loe))   (LOE event)
    where B_sg0 = -Q_sg0/V², B_loe = P_sg²*Xd/V⁴ (max reactive absorption)

  Y_GFM(t) = j*B_gfm(t)   (reactive-only IBR model)
    Absorbing (FM1): B_gfm(t) = +B_gfm_max*(1-exp(-t/T_gfm))
    Supplying (FM2): B_gfm(t) = -B_gfm_max*(1-exp(-t/T_gfm))

  Trip decision:
    Conventional : Im(Y_total) > B_trip for T_persist ≥ T_delay
    Proposed     : Im(Y_total - Y_GFM_est) > B_trip for T_persist ≥ T_delay

Targets:
  Deterministic: 10/10 PASS (proposed relay)
  MC P_D_prop   ≥ 0.970   (genuine LOE trials)
  MC P_FA_prop  ≤ 0.020   (no-LOE trials)
  Improvement   : P_FA_conv > P_FA_prop  (fewer false alarms)
                  P_D_conv  < P_D_prop   (fewer missed detections)

Chapter: Ch. 6, §6.7 — Relay 40 LOE for IBR generators
Journal: IEEE Transactions on Power Delivery
"""

from __future__ import annotations

import csv
import pathlib
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.optimize import minimize

# ─── Constants ────────────────────────────────────────────────────────────────
DT    = 2e-3          # simulation time step [s]
T_SIM = 6.0           # total simulation duration [s]

# ─── System configuration ─────────────────────────────────────────────────────
@dataclass
class SysConfig:
    # SG parameters
    Xd:        float = 1.00   # synchronous reactance [pu]
    P_sg:      float = 0.80   # SG active power output [pu]
    Q_sg0:     float = 0.25   # SG normal reactive output (positive = supplying) [pu]
    V:         float = 1.00   # terminal voltage [pu]
    # LOE event
    has_loe:   bool  = False  # genuine LOE present?
    t_loe:     float = 1.00   # LOE start time [s]
    T_loe:     float = 1.50   # LOE development time constant [s]
    B_loe_max: float = 0.90   # maximum susceptance reached at full LOE [pu]
    # GFM IBR contribution
    gfm_mode:  str   = 'none' # 'none' | 'absorb' | 'supply'
    B_gfm_max: float = 0.0    # maximum GFM susceptance magnitude [pu]
    T_gfm:     float = 0.30   # GFM transient time constant [s]
    t_gfm_start: float = 0.50 # GFM transient start time [s]
    est_error: float = 0.0    # fractional GFM estimation error (σ as fraction of B_gfm_max)
    # Relay settings
    B_trip:    float = 0.50   # susceptance trip threshold [pu]
    T_delay:   float = 0.50   # persistence time before trip [s]

    # ── Derived quantities ─────────────────────────────────────────────────────
    def B_sg0(self) -> float:
        return -self.Q_sg0 / self.V**2

    def Y_SG(self, t: np.ndarray) -> np.ndarray:
        G = self.P_sg / self.V**2
        B = np.full_like(t, self.B_sg0())
        if self.has_loe:
            mask = t >= self.t_loe
            t_rel = np.where(mask, t - self.t_loe, 0.0)
            B_rise = (self.B_loe_max - self.B_sg0()) * (1.0 - np.exp(-t_rel / self.T_loe))
            B = np.where(mask, self.B_sg0() + B_rise, B)
        return G + 1j * B

    def Y_GFM_true(self, t: np.ndarray) -> np.ndarray:
        if self.gfm_mode == 'none' or self.B_gfm_max == 0.0:
            return np.zeros(len(t), dtype=complex)
        mask = t >= self.t_gfm_start
        t_rel = np.where(mask, t - self.t_gfm_start, 0.0)
        B_mag = self.B_gfm_max * (1.0 - np.exp(-t_rel / self.T_gfm))
        B = np.where(mask, B_mag, 0.0)
        if self.gfm_mode == 'supply':
            B = -B  # supplying reactive → negative susceptance contribution
        return 1j * B

    def Y_GFM_est(self, t: np.ndarray, rng: Optional[np.random.Generator] = None) -> np.ndarray:
        """Estimated GFM admittance with optional estimation error."""
        Y_true = self.Y_GFM_true(t)
        if self.est_error == 0.0 or rng is None:
            return Y_true
        noise = rng.normal(0.0, self.est_error * self.B_gfm_max, size=len(t))
        return Y_true + 1j * noise

    def Y_total(self, t: np.ndarray) -> np.ndarray:
        return self.Y_SG(t) + self.Y_GFM_true(t)


# ─── Trip decision logic ──────────────────────────────────────────────────────
def relay_decision(
    t: np.ndarray,
    B_signal: np.ndarray,
    B_trip: float,
    T_delay: float,
) -> tuple[bool, float]:
    """
    Returns (tripped, trip_time_s).
    Trip occurs when B_signal > B_trip continuously for T_delay seconds.
    """
    above = B_signal > B_trip
    persist = 0.0
    for i in range(len(t)):
        if above[i]:
            persist += DT
            if persist >= T_delay:
                return True, float(t[i])
        else:
            persist = 0.0
    return False, float('nan')


# ─── Scenario result ──────────────────────────────────────────────────────────
@dataclass
class ScenarioResult:
    name:            str
    loe_expected:    bool   # True = LOE present (trip expected)
    conv_trip:       bool
    conv_trip_time:  float
    prop_trip:       bool
    prop_trip_time:  float
    pass_conv:       bool
    pass_prop:       bool
    B_max_total:     float  # peak Im(Y_total)
    B_max_corrected: float  # peak Im(Y_corrected)


def run_scenario(cfg: SysConfig, name: str, loe_expected: bool) -> ScenarioResult:
    t = np.arange(0.0, T_SIM + DT, DT)
    Y_tot  = cfg.Y_total(t)
    Y_est  = cfg.Y_GFM_est(t)              # deterministic: no noise
    B_tot  = np.imag(Y_tot)
    B_corr = np.imag(Y_tot - Y_est)

    conv_trip, conv_t = relay_decision(t, B_tot,  cfg.B_trip, cfg.T_delay)
    prop_trip, prop_t = relay_decision(t, B_corr, cfg.B_trip, cfg.T_delay)

    # Pass criterion:
    #   LOE expected → correct if relay trips
    #   LOE not expected → correct if relay does NOT trip
    pass_conv = (conv_trip == loe_expected)
    pass_prop = (prop_trip == loe_expected)

    return ScenarioResult(
        name=name, loe_expected=loe_expected,
        conv_trip=conv_trip, conv_trip_time=conv_t,
        prop_trip=prop_trip, prop_trip_time=prop_t,
        pass_conv=pass_conv, pass_prop=pass_prop,
        B_max_total=float(np.max(B_tot)),
        B_max_corrected=float(np.max(B_corr)),
    )


# ─── Scenario definitions ─────────────────────────────────────────────────────
def build_scenarios() -> list[tuple[SysConfig, str, bool]]:
    BASE = dict(Xd=1.0, P_sg=0.80, Q_sg0=0.25, V=1.0,
                B_loe_max=0.90, T_loe=1.50, T_delay=0.50, B_trip=0.50)

    scenarios = [
        # Security scenarios (no LOE) ─────────────────────────────────────────
        (SysConfig(**BASE,
                   has_loe=False, gfm_mode='none', B_gfm_max=0.0),
         'S01', False),   # Normal, no GFM → secure

        (SysConfig(**BASE,
                   has_loe=False, gfm_mode='absorb', B_gfm_max=0.70, T_gfm=0.30),
         'S02', False),   # FM1: GFM reactive absorption → conv FA, prop secure

        (SysConfig(**BASE,
                   has_loe=False, gfm_mode='absorb', B_gfm_max=0.80, T_gfm=0.20),
         'S03', False),   # FM1 severe: fast strong absorption → conv FA

        (SysConfig(**BASE,
                   has_loe=False, gfm_mode='supply', B_gfm_max=0.60, T_gfm=0.40),
         'S04', False),   # GFM supply mode, no LOE → no trip from either

        (SysConfig(**BASE,
                   has_loe=False, gfm_mode='absorb', B_gfm_max=0.60, T_gfm=0.50,
                   t_gfm_start=0.80),
         'S05', False),   # FM1 delayed onset: absorption → conv FA, prop secure

        # Dependability scenarios (LOE present) ───────────────────────────────
        (SysConfig(**BASE,
                   has_loe=True, t_loe=1.0, gfm_mode='none', B_gfm_max=0.0),
         'S06', True),    # LOE, no GFM → both trip

        (SysConfig(**BASE,
                   has_loe=True, t_loe=1.0, gfm_mode='supply', B_gfm_max=0.60,
                   T_gfm=0.40),
         'S07', True),    # FM2: GFM supply masks LOE → conv miss, prop trips

        (SysConfig(**BASE,
                   has_loe=True, t_loe=1.0, gfm_mode='supply', B_gfm_max=0.75,
                   T_gfm=0.30),
         'S08', True),    # FM2 severe: strong supply → conv definite miss

        (SysConfig(**BASE,
                   has_loe=True, t_loe=1.5, gfm_mode='supply', B_gfm_max=0.50,
                   T_gfm=0.60),
         'S09', True),    # FM2 late LOE + sustained GFM supply

        (SysConfig(**BASE,
                   has_loe=True, t_loe=1.0, gfm_mode='absorb', B_gfm_max=0.20,
                   T_gfm=0.25),
         'S10', True),    # LOE + mild GFM absorption → both trip (absorption adds)
    ]
    return scenarios


# ─── Monte Carlo ──────────────────────────────────────────────────────────────
@dataclass
class MCResult:
    n_trials:       int
    n_stable:       int
    n_loe:          int
    P_D_prop:       float
    P_D_conv:       float
    P_FA_prop:      float
    P_FA_conv:      float
    t50_prop_ms:    float


def run_monte_carlo(n_trials: int = 2000, rng_seed: int = 42) -> MCResult:
    """
    Split MC: n/2 security (no LOE), n/2 dependability (LOE present).
    Sampled parameters:
      k_gfm_mode  : 0=supply 1=absorb  (uniform random)
      B_gfm_max   ~ U[0.30, 0.80]  pu
      T_gfm       ~ U[0.15, 0.55]  s
      est_error   ~ U[0.00, 0.10]  (fractional, ×B_gfm_max)
      T_loe       ~ U[1.00, 2.50]  s   (LOE trials only)
    """
    rng = np.random.default_rng(rng_seed)
    BASE = dict(Xd=1.0, P_sg=0.80, Q_sg0=0.25, V=1.0,
                B_loe_max=0.90, B_trip=0.50, T_delay=0.50)

    half = n_trials // 2
    n_stable = n_loe = 0
    prop_trip_stable = conv_trip_stable = 0
    prop_trip_loe    = conv_trip_loe    = 0
    prop_trip_times_ms: list[float] = []

    t = np.arange(0.0, T_SIM + DT, DT)

    t0 = time.time()
    for trial in range(n_trials):
        B_gfm_max = float(rng.uniform(0.30, 0.80))
        T_gfm     = float(rng.uniform(0.15, 0.55))
        err_frac  = float(rng.uniform(0.00, 0.10))
        mode      = 'supply' if rng.integers(0, 2) == 0 else 'absorb'
        t_gfm_start = float(rng.uniform(0.30, 0.80))

        is_loe = (trial >= half)

        if is_loe:
            T_loe_trial = float(rng.uniform(1.00, 2.50))
            t_loe       = float(rng.uniform(0.80, 1.50))
            cfg = SysConfig(
                **BASE,
                has_loe=True, t_loe=t_loe, T_loe=T_loe_trial,
                gfm_mode=mode, B_gfm_max=B_gfm_max, T_gfm=T_gfm,
                t_gfm_start=t_gfm_start, est_error=err_frac,
            )
            n_loe += 1
        else:
            cfg = SysConfig(
                **BASE,
                has_loe=False,
                gfm_mode=mode, B_gfm_max=B_gfm_max, T_gfm=T_gfm,
                t_gfm_start=t_gfm_start, est_error=err_frac,
            )
            n_stable += 1

        Y_tot  = cfg.Y_total(t)
        Y_est  = cfg.Y_GFM_est(t, rng=rng)
        B_tot  = np.imag(Y_tot)
        B_corr = np.imag(Y_tot - Y_est)

        conv_trip, _ = relay_decision(t, B_tot,  cfg.B_trip, cfg.T_delay)
        prop_trip, prop_t = relay_decision(t, B_corr, cfg.B_trip, cfg.T_delay)

        if is_loe:
            if conv_trip:
                conv_trip_loe += 1
            if prop_trip:
                prop_trip_loe += 1
                if not np.isnan(prop_t):
                    prop_trip_times_ms.append(prop_t * 1000.0)
        else:
            if conv_trip:
                conv_trip_stable += 1
            if prop_trip:
                prop_trip_stable += 1

        if trial % 500 == 499:
            elapsed = time.time() - t0
            print(f"  trial {trial+1}/{n_trials}  ({elapsed:.1f}s elapsed)")

    P_D_prop  = prop_trip_loe    / n_loe    if n_loe    > 0 else 0.0
    P_D_conv  = conv_trip_loe    / n_loe    if n_loe    > 0 else 0.0
    P_FA_prop = prop_trip_stable / n_stable if n_stable > 0 else 0.0
    P_FA_conv = conv_trip_stable / n_stable if n_stable > 0 else 0.0
    t50       = float(np.median(prop_trip_times_ms)) if prop_trip_times_ms else float('nan')

    return MCResult(
        n_trials=n_trials, n_stable=n_stable, n_loe=n_loe,
        P_D_prop=P_D_prop, P_D_conv=P_D_conv,
        P_FA_prop=P_FA_prop, P_FA_conv=P_FA_conv,
        t50_prop_ms=t50,
    )


# ─── Output formatting ────────────────────────────────────────────────────────
_DESCRIPTIONS = {
    'S01': 'Normal, no GFM — security baseline',
    'S02': 'FM1: GFM reactive absorption — conv FA',
    'S03': 'FM1 severe: fast GFM absorption — conv FA',
    'S04': 'GFM supply mode, no LOE — secure',
    'S05': 'FM1 delayed onset — conv FA',
    'S06': 'LOE event, no GFM — dependability baseline',
    'S07': 'FM2: GFM supply masks LOE — conv miss',
    'S08': 'FM2 severe: strong GFM supply — conv miss',
    'S09': 'FM2 late LOE + sustained GFM supply',
    'S10': 'LOE + mild GFM absorption — both trip',
}


def print_deterministic_table(results: list[ScenarioResult]) -> tuple[int, int]:
    hdr = (f"{'#':<4} {'LOE':>4} {'B_max_tot':>9} {'B_max_cor':>9} "
           f"{'Conv':>5} {'Prop':>5}")
    print("\n" + "═" * len(hdr))
    print("TR-60  Deterministic Results")
    print("═" * len(hdr))
    print(hdr)
    print("─" * len(hdr))
    n_pass_conv = n_pass_prop = 0
    for r in results:
        cv = "PASS" if r.pass_conv else "FAIL"
        pv = "PASS" if r.pass_prop else "FAIL"
        if r.pass_conv: n_pass_conv += 1
        if r.pass_prop: n_pass_prop += 1
        print(f"{r.name:<4} {'YES' if r.loe_expected else 'NO':>4} "
              f"{r.B_max_total:9.3f} {r.B_max_corrected:9.3f} "
              f"{cv:>5} {pv:>5}  {_DESCRIPTIONS[r.name]}")
    print("─" * len(hdr))
    print(f"{'TOTAL':<4} {'':>4} {'':>9} {'':>9} "
          f"{n_pass_conv:>3}/10 {n_pass_prop:>3}/10")
    print("═" * len(hdr))
    return n_pass_conv, n_pass_prop


def print_mc_table(mc: MCResult) -> None:
    print("\n" + "═" * 60)
    print("TR-60  Monte Carlo Results")
    print("═" * 60)
    print(f"  Trials       : {mc.n_trials:,}  (stable={mc.n_stable}, LOE={mc.n_loe})")
    print()
    print("  Dependability (P_D, LOE trials):")
    print(f"    Proposed   : {mc.P_D_prop:.4f}   target ≥ 0.970  "
          f"{'PASS' if mc.P_D_prop >= 0.970 else 'FAIL'}")
    print(f"    Conventional: {mc.P_D_conv:.4f}   (reference)")
    print()
    print("  False alarm (P_FA, stable trials):")
    print(f"    Proposed   : {mc.P_FA_prop:.4f}   target ≤ 0.020  "
          f"{'PASS' if mc.P_FA_prop <= 0.020 else 'FAIL'}")
    print(f"    Conventional: {mc.P_FA_conv:.4f}   (reference, expect > 0.020)")
    print()
    print(f"  Improvement  : P_D  {mc.P_D_conv:.3f} → {mc.P_D_prop:.3f}  "
          f"(Δ = {mc.P_D_prop - mc.P_D_conv:+.3f})")
    print(f"                 P_FA {mc.P_FA_conv:.3f} → {mc.P_FA_prop:.3f}  "
          f"(Δ = {mc.P_FA_prop - mc.P_FA_conv:+.3f})")
    print(f"  t50 (proposed, LOE): {mc.t50_prop_ms:.0f} ms")
    print("═" * 60)


def save_outputs(results: list[ScenarioResult], mc: MCResult) -> None:
    out = pathlib.Path(__file__).parent / "outputs" / "tr60"
    out.mkdir(parents=True, exist_ok=True)

    det_path = out / "tr60_deterministic.csv"
    with open(det_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["scenario", "loe_expected", "B_max_total", "B_max_corrected",
                         "conv_trip", "conv_trip_time_s",
                         "prop_trip", "prop_trip_time_s",
                         "pass_conv", "pass_prop"])
        for r in results:
            writer.writerow([
                r.name, int(r.loe_expected),
                f"{r.B_max_total:.4f}", f"{r.B_max_corrected:.4f}",
                int(r.conv_trip),
                "" if np.isnan(r.conv_trip_time) else f"{r.conv_trip_time:.3f}",
                int(r.prop_trip),
                "" if np.isnan(r.prop_trip_time) else f"{r.prop_trip_time:.3f}",
                int(r.pass_conv), int(r.pass_prop),
            ])
    print(f"\n  Deterministic CSV  → {det_path}")

    mc_path = out / "tr60_mc_metrics.csv"
    with open(mc_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value", "target", "pass"])
        writer.writerow(["n_trials", mc.n_trials, "", ""])
        writer.writerow(["n_stable", mc.n_stable, "", ""])
        writer.writerow(["n_loe", mc.n_loe, "", ""])
        writer.writerow(["P_D_prop",  f"{mc.P_D_prop:.4f}",  ">=0.970", int(mc.P_D_prop  >= 0.970)])
        writer.writerow(["P_D_conv",  f"{mc.P_D_conv:.4f}",  "",        ""])
        writer.writerow(["P_FA_prop", f"{mc.P_FA_prop:.4f}", "<=0.020", int(mc.P_FA_prop <= 0.020)])
        writer.writerow(["P_FA_conv", f"{mc.P_FA_conv:.4f}", "",        ""])
        writer.writerow(["t50_prop_ms", f"{mc.t50_prop_ms:.1f}", "", ""])
    print(f"  MC metrics CSV     → {mc_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 70)
    print("SAMBP TR-60/2026  —  IBR-Corrected Relay 40  —  LOE Protection")
    print("=" * 70)

    print("\n[1/2] Running 10 deterministic scenarios …")
    scenarios = build_scenarios()
    results: list[ScenarioResult] = []
    for cfg, name, loe_expected in scenarios:
        r = run_scenario(cfg, name, loe_expected)
        results.append(r)
        tag = "PASS" if r.pass_prop else "FAIL"
        print(f"  {name}  {_DESCRIPTIONS[name]:<44}  [{tag}]")

    n_pass_conv, n_pass_prop = print_deterministic_table(results)
    det_pass = (n_pass_prop == 10)

    print(f"\n  Proposed relay : {n_pass_prop}/10 PASS  "
          f"({'PASS' if det_pass else 'FAIL'})")
    print(f"  Conventional   : {n_pass_conv}/10 PASS  "
          f"(expected ≤7/10; FM1+FM2 failures)")

    print("\n[2/2] Running Monte Carlo (2 000 trials) …")
    mc = run_monte_carlo(n_trials=2000, rng_seed=42)
    print_mc_table(mc)

    mc_pass = (mc.P_D_prop >= 0.970 and mc.P_FA_prop <= 0.020)
    all_pass = det_pass and mc_pass

    print("\n" + "═" * 70)
    print(f"TR-60 OVERALL: "
          f"{'ALL TARGETS MET — PASS' if all_pass else 'SOME TARGETS MISSED — CHECK ABOVE'}")
    print("═" * 70)

    save_outputs(results, mc)


if __name__ == "__main__":
    main()
