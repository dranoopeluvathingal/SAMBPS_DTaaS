"""
run_faultloc_phase4_wang2020.py
==================================

WP4.3 (P4.3) Wang-2020 distortion-controllable HIAF runner.

Pipeline
--------

For each cell of the WP3.3 IEEE 34 720-grid sub-sample:

* Synthesise a 1-cycle clean phase-A voltage waveform.
* Generate two current waveforms per Monte-Carlo trial:
  (i) ``EmanuelArc`` baseline (the diode-on-diode self-consistent
  reference); (ii) ``Wang2020Arc`` distortion-controllable
  randomised arc (with fresh OFFSET / EXTENT / DURATION drawn each
  half-cycle).
* For each, compute H_meas via single-bin DFT, run the WP1.4 /
  WP2.4 single-bin-DFT optimiser AND the WP3.5 Taylor-Fourier
  K = 1 estimator, record the (alpha_hat, R_x_hat) and per-cell
  location / R_x error.
* Compute the Delta-error
  ``loc_err_wang2020 - loc_err_emanuel`` per (cell, trial).

Output bundles
--------------

``data/wang2020_ieee34_720.mat`` -- per-(cell, trial) waveform
bundle for downstream R&D (V, I shape (n_trials, n_cells,
N_samples), grid arrays).  Schema follows ``data/ieee34_720.mat``
plus a trial axis.

``outputs/phase4_wang2020_results.csv`` -- per-(cell, trial)
optimiser-result CSV (DFT + TFT estimators on both arc-model
stimuli + per-cell Delta-errors).

Tractable scope
---------------

Full IEEE 34 720-grid x 100 MC trials = 72 k waveforms x 4
optimiser runs each = 288 k runs.  At ~100 ms / run on the dev box
this is ~ 8 hours -- too long.  We sub-sample to 5 fault buses
x 5 R_x x 4 SNR_I subset (only SNR_I >= 30 dB; SNR_V = inf) x
20 MC trials = 2 000 cells x 4 = 8 000 runs ~ 13 min.  The full
720-grid x 100-trial run is queued for the lead engineer's
licensed Windows runner (per the WP4.3 brief follow-up pattern).
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
    Wang2020Arc,
)
from sambp_fault_location_id.models.faultloc_taylor_fourier import (
    H_meas_from_waveforms_tft,
)
from scipy.io import loadmat, savemat

PROJ_ROOT = Path(__file__).resolve().parent
IEEE34_BUNDLE = PROJ_ROOT / "data" / "ieee34_720.mat"
OUT_MAT = PROJ_ROOT / "data" / "wang2020_ieee34_720.mat"
OUT_CSV = PROJ_ROOT / "outputs" / "phase4_wang2020_results.csv"

OMEGA = 2.0 * np.pi * 50.0
F0 = 50.0
FS = 10_000.0
N_CYCLES = 1
N_SAMPLES = int(round(N_CYCLES * FS / F0))


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


def run(*, n_buses: int = 5, n_trials: int = 20, rng_seed: int = 59) -> None:
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
    print(
        f"WP4.3 Wang-2020 runner: {len(selected)} cells "
        f"(after sub-sample to {len(chosen)} buses + SNR_I >= 30 dB) "
        f"x {n_trials} MC trials = "
        f"{len(selected) * n_trials} (cell, trial) pairs"
    )

    emanuel = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    rng = np.random.default_rng(rng_seed)

    n_cells = len(selected)
    V_bundle = np.zeros((n_trials, n_cells, N_SAMPLES), dtype=float)
    I_em_bundle = np.zeros((n_trials, n_cells, N_SAMPLES), dtype=float)
    I_w_bundle = np.zeros((n_trials, n_cells, N_SAMPLES), dtype=float)

    rows: list[dict] = []
    t0 = time.perf_counter()
    n_done = 0
    n_total = n_trials * n_cells
    for trial in range(n_trials):
        wang = Wang2020Arc(distortion_index=0.7, emanuel=emanuel, rng=rng)
        for k_idx, k in enumerate(selected):
            Rx = float(grid_Rx[k])
            alpha = float(grid_alpha[k])
            snr_v = float(grid_SNR_V[k])
            snr_i = float(grid_SNR_I[k])
            bus = fault_bus_strs[k]

            t = np.arange(N_SAMPLES) / FS
            v = _synth_v(rng, snr_v)

            i_em = emanuel.synthesise_current(t, v, Rx)
            i_w = wang.synthesise_current(t, v, Rx)

            i_em = _add_noise(i_em, snr_i, rng)
            i_w = _add_noise(i_w, snr_i, rng)

            V_bundle[trial, k_idx] = v
            I_em_bundle[trial, k_idx] = i_em
            I_w_bundle[trial, k_idx] = i_w

            H_em_dft = H_meas_from_waveforms(v, i_em, fs=FS, f0=F0)
            H_w_dft = H_meas_from_waveforms(v, i_w, fs=FS, f0=F0)
            H_em_tft = H_meas_from_waveforms_tft(v, i_em, fs=FS, f0=F0, K=1)
            H_w_tft = H_meas_from_waveforms_tft(v, i_w, fs=FS, f0=F0, K=1)

            opts = {"snr_v_db": snr_v, "snr_i_db": snr_i, "max_iter": 200}

            def _opt(H, _opts=opts):
                try:
                    (a, R), _ = estimate_alpha_Rx(H, opts=_opts)
                    return float(a), float(R)
                except Exception:
                    return float("nan"), float("nan")

            a_em_dft, R_em_dft = _opt(H_em_dft)
            a_w_dft, R_w_dft = _opt(H_w_dft)
            a_em_tft, R_em_tft = _opt(H_em_tft)
            a_w_tft, R_w_tft = _opt(H_w_tft)

            le_em_dft = _err_pct(a_em_dft, alpha)
            lw_dft = _err_pct(a_w_dft, alpha)
            le_em_tft = _err_pct(a_em_tft, alpha)
            lw_tft = _err_pct(a_w_tft, alpha)

            rows.append({
                "trial": trial,
                "fault_bus": bus,
                "alpha_true": alpha,
                "Rx_true": Rx,
                "snr_v_db": snr_v,
                "snr_i_db": snr_i,
                "loc_err_emanuel_dft": le_em_dft,
                "loc_err_wang2020_dft": lw_dft,
                "loc_err_emanuel_tft": le_em_tft,
                "loc_err_wang2020_tft": lw_tft,
                "delta_dft": lw_dft - le_em_dft,
                "delta_tft": lw_tft - le_em_tft,
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

    # Write the .mat bundle (DOWNSAMPLED to keep file size manageable)
    OUT_MAT.parent.mkdir(parents=True, exist_ok=True)
    grid_arrays = {
        "V": V_bundle,
        "I_emanuel": I_em_bundle,
        "I_wang2020": I_w_bundle,
        "grid_alpha": np.array(
            [grid_alpha[k] for k in selected], dtype=float,
        ),
        "grid_Rx": np.array([grid_Rx[k] for k in selected], dtype=float),
        "grid_SNR_V": np.array(
            [grid_SNR_V[k] for k in selected], dtype=float,
        ),
        "grid_SNR_I": np.array(
            [grid_SNR_I[k] for k in selected], dtype=float,
        ),
        "grid_fault_bus": np.array(
            [fault_bus_strs[k] for k in selected], dtype="U16",
        ),
        "meta": {
            "schema_version": "wp4.3.p4.3",
            "feeder": "IEEE_34",
            "fs_hz": FS,
            "f0_hz": F0,
            "n_cycles": N_CYCLES,
            "n_trials": int(n_trials),
            "n_cells": int(n_cells),
            "wang2020_distortion_index": 0.7,
            "comment": (
                "Wang-2020 distortion-controllable HIAF dataset; per-trial "
                "fresh OFFSET / EXTENT / DURATION drawn for each half-"
                "cycle.  Schema mirrors data/ieee34_720.mat with an added "
                "trial axis on V / I."
            ),
        },
    }
    savemat(str(OUT_MAT), grid_arrays)
    print(f"wrote {OUT_MAT} ({OUT_MAT.stat().st_size // 1024} KB)")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {OUT_CSV} ({len(rows)} rows)")

    # Headline summary
    le_em = np.array([r["loc_err_emanuel_dft"] for r in rows
                      if np.isfinite(r["loc_err_emanuel_dft"])])
    le_w = np.array([r["loc_err_wang2020_dft"] for r in rows
                     if np.isfinite(r["loc_err_wang2020_dft"])])
    le_em_t = np.array([r["loc_err_emanuel_tft"] for r in rows
                        if np.isfinite(r["loc_err_emanuel_tft"])])
    le_w_t = np.array([r["loc_err_wang2020_tft"] for r in rows
                       if np.isfinite(r["loc_err_wang2020_tft"])])
    delta_dft = np.array([r["delta_dft"] for r in rows
                          if np.isfinite(r["delta_dft"])])
    delta_tft = np.array([r["delta_tft"] for r in rows
                          if np.isfinite(r["delta_tft"])])

    print()
    print("=== Cross-fit summary (loc-err %) ===")
    print(f"  Emanuel  DFT:   mean={le_em.mean():.2f}%, "
          f"p95={np.percentile(le_em, 95):.2f}%")
    print(f"  Wang2020 DFT:   mean={le_w.mean():.2f}%, "
          f"p95={np.percentile(le_w, 95):.2f}%")
    print(f"  Emanuel  TFT:   mean={le_em_t.mean():.2f}%, "
          f"p95={np.percentile(le_em_t, 95):.2f}%")
    print(f"  Wang2020 TFT:   mean={le_w_t.mean():.2f}%, "
          f"p95={np.percentile(le_w_t, 95):.2f}%")
    print(f"  Delta DFT (Wang - EM):  mean={delta_dft.mean():+.2f}%, "
          f"abs.mean={np.abs(delta_dft).mean():.2f}%, "
          f"abs.p95={np.percentile(np.abs(delta_dft), 95):.2f}%")
    print(f"  Delta TFT (Wang - EM):  mean={delta_tft.mean():+.2f}%, "
          f"abs.mean={np.abs(delta_tft).mean():.2f}%, "
          f"abs.p95={np.percentile(np.abs(delta_tft), 95):.2f}%")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n-buses", type=int, default=5)
    parser.add_argument("--n-trials", type=int, default=20)
    parser.add_argument("--rng-seed", type=int, default=59)
    args = parser.parse_args(argv)
    run(n_buses=args.n_buses, n_trials=args.n_trials, rng_seed=args.rng_seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
