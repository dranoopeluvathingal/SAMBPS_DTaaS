"""
run_faultloc_phase4_torres.py
==============================

WP4.4 (P4.4) Torres-2022 stochastic-configurable arc cross-fit
runner.

Pipeline
--------

For each cell of the WP3.3 IEEE 34 720-grid sub-sample, and for
each canonical Torres profile {tree, sand, concrete}:

* Synthesise a 1-cycle clean phase-A voltage waveform.
* Generate two current waveforms per Monte-Carlo trial:
  (i) ``EmanuelArc`` baseline (the diode-on-diode self-consistent
  reference); (ii) ``Torres2022Arc`` with the chosen profile.
* For each, compute H_meas via single-bin DFT, run the WP1.4 /
  WP2.4 single-bin-DFT optimiser, record the (alpha_hat, R_x_hat)
  and per-cell location / R_x error.
* Compute the Delta-error
  ``loc_err_torres - loc_err_emanuel`` per (cell, trial, profile).

Output
------

``outputs/phase4_torres_results.csv`` -- per-(cell, trial,
profile) optimiser-result CSV with the per-cell Delta-error.

Tractable scope
---------------

5 fault buses x 5 R_x x 4 SNR_I subset (only SNR_I >= 30 dB;
SNR_V = inf) x 3 profiles x 8 MC trials = 1 200 cells x 3 profiles
= 3 600 (cell, trial, profile) triples ~ 7-10 min on the dev box.
Full-grid runs are queued for the licensed Windows runner.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    H_meas_from_waveforms,
    estimate_alpha_Rx,
)
from sambp_fault_location_id.models.faultloc_arc_models import (
    EmanuelArc,
    Torres2022Arc,
)
from scipy.io import loadmat

PROJ_ROOT = Path(__file__).resolve().parent
IEEE34_BUNDLE = PROJ_ROOT / "data" / "ieee34_720.mat"
OUT_CSV = PROJ_ROOT / "outputs" / "phase4_torres_results.csv"

OMEGA = 2.0 * np.pi * 50.0
F0 = 50.0
FS = 10_000.0
N_CYCLES = 1
N_SAMPLES = int(round(N_CYCLES * FS / F0))

PROFILES = ("tree", "sand", "concrete")


def _synth_v(rng, snr_v_db) -> np.ndarray:
    V_peak = 11.0e3 * np.sqrt(2.0 / 3.0)
    n = np.arange(N_SAMPLES)
    t = n / FS
    v = V_peak * np.cos(OMEGA * t)
    if np.isfinite(snr_v_db):
        rms = float(np.sqrt(np.mean(v ** 2)))
        v = v + rng.standard_normal(v.shape) * (
            rms * 10.0 ** (-snr_v_db / 20.0)
        )
    return v


def _add_noise(i, snr_i_db, rng) -> np.ndarray:
    if not np.isfinite(snr_i_db):
        return i
    rms = float(np.sqrt(np.mean(i ** 2)))
    return i + rng.standard_normal(i.shape) * (
        rms * 10.0 ** (-snr_i_db / 20.0)
    )


def _err_pct(hat, true):
    if true <= 0 or not np.isfinite(hat):
        return float("nan")
    return 100.0 * abs(hat - true) / true


def run(*, n_buses: int = 5, n_trials: int = 8, rng_seed: int = 71) -> None:
    if not IEEE34_BUNDLE.exists():
        raise FileNotFoundError(
            f"{IEEE34_BUNDLE} not present; run "
            f"`python tools/ieee_feeder_surrogate.py --feeder IEEE_34` first."
        )
    bundle = loadmat(str(IEEE34_BUNDLE))
    grid_alpha = bundle["grid_alpha"].squeeze()
    grid_Rx = bundle["grid_Rx"].squeeze()
    grid_SNR_V = bundle["grid_SNR_V"].squeeze()
    grid_SNR_I = bundle["grid_SNR_I"].squeeze()
    grid_fault_bus = bundle["grid_fault_bus"].squeeze()
    fault_bus_strs = [str(b).strip() for b in grid_fault_bus]

    unique_buses = sorted(set(fault_bus_strs))
    if n_buses < len(unique_buses):
        stride = max(1, len(unique_buses) // n_buses)
        chosen = set(unique_buses[::stride][:n_buses])
    else:
        chosen = set(unique_buses)

    selected = [
        k for k in range(len(fault_bus_strs))
        if fault_bus_strs[k] in chosen
        and (grid_SNR_I[k] >= 30.0 or not np.isfinite(grid_SNR_I[k]))
    ]
    n_total = len(selected) * n_trials * len(PROFILES)
    print(
        f"WP4.4 Torres runner: {len(selected)} cells x {n_trials} trials "
        f"x {len(PROFILES)} profiles = {n_total} triples"
    )

    emanuel = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    rng = np.random.default_rng(rng_seed)

    rows: list[dict] = []
    t0 = time.perf_counter()
    n_done = 0
    for trial in range(n_trials):
        torres_arcs = {
            p: Torres2022Arc(profile=p, emanuel=emanuel, rng=rng)
            for p in PROFILES
        }
        for k in selected:
            Rx = float(grid_Rx[k])
            alpha = float(grid_alpha[k])
            snr_v = float(grid_SNR_V[k])
            snr_i = float(grid_SNR_I[k])
            bus = fault_bus_strs[k]

            t = np.arange(N_SAMPLES) / FS
            v = _synth_v(rng, snr_v)

            i_em = emanuel.synthesise_current(t, v, Rx)
            i_em = _add_noise(i_em, snr_i, rng)

            H_em = H_meas_from_waveforms(v, i_em, fs=FS, f0=F0)
            opts = {"snr_v_db": snr_v, "snr_i_db": snr_i, "max_iter": 200}

            def _opt(H, _opts=opts):
                try:
                    (a, R), _ = estimate_alpha_Rx(H, opts=_opts)
                    return float(a), float(R)
                except Exception:
                    return float("nan"), float("nan")

            a_em, R_em = _opt(H_em)
            le_em = _err_pct(a_em, alpha)
            re_em = _err_pct(R_em, Rx)

            for prof in PROFILES:
                i_to = torres_arcs[prof].synthesise_current(t, v, Rx)
                i_to = _add_noise(i_to, snr_i, rng)
                H_to = H_meas_from_waveforms(v, i_to, fs=FS, f0=F0)
                a_to, R_to = _opt(H_to)
                le_to = _err_pct(a_to, alpha)
                re_to = _err_pct(R_to, Rx)
                rows.append({
                    "trial": trial,
                    "profile": prof,
                    "fault_bus": bus,
                    "alpha_true": alpha,
                    "Rx_true": Rx,
                    "snr_v_db": snr_v,
                    "snr_i_db": snr_i,
                    "alpha_hat_emanuel": a_em,
                    "Rx_hat_emanuel": R_em,
                    "loc_err_emanuel": le_em,
                    "Rx_err_emanuel": re_em,
                    "alpha_hat_torres": a_to,
                    "Rx_hat_torres": R_to,
                    "loc_err_torres": le_to,
                    "Rx_err_torres": re_to,
                    "delta_loc_err_pct": le_to - le_em,
                    "delta_Rx_err_pct": re_to - re_em,
                })
                n_done += 1
                if n_done % max(1, n_total // 10) == 0:
                    elapsed = time.perf_counter() - t0
                    eta = elapsed * (n_total - n_done) / max(n_done, 1)
                    print(
                        f"  [{n_done}/{n_total}] elapsed {elapsed:.0f}s; "
                        f"eta {eta:.0f}s"
                    )
    print(f"runner done in {time.perf_counter() - t0:.1f}s")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {OUT_CSV} ({len(rows)} rows)")

    # Per-profile headline summary
    print()
    print("=== Per-profile cross-fit summary (loc-err %) ===")
    for prof in PROFILES:
        prof_rows = [r for r in rows if r["profile"] == prof]
        le_em = np.array([
            r["loc_err_emanuel"] for r in prof_rows
            if np.isfinite(r["loc_err_emanuel"])
        ])
        le_to = np.array([
            r["loc_err_torres"] for r in prof_rows
            if np.isfinite(r["loc_err_torres"])
        ])
        delta = np.array([
            r["delta_loc_err_pct"] for r in prof_rows
            if np.isfinite(r["delta_loc_err_pct"])
        ])
        print(
            f"  {prof:8s}  Em mean={le_em.mean():.2f}%  "
            f"To mean={le_to.mean():.2f}%  "
            f"Delta mean={delta.mean():+.2f}%  "
            f"abs.p95={np.percentile(np.abs(delta), 95):.2f}%"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n-buses", type=int, default=5)
    parser.add_argument("--n-trials", type=int, default=8)
    parser.add_argument("--rng-seed", type=int, default=71)
    args = parser.parse_args(argv)
    run(n_buses=args.n_buses, n_trials=args.n_trials, rng_seed=args.rng_seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
