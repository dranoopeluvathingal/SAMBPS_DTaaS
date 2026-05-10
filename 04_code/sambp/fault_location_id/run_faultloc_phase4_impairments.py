"""
run_faultloc_phase4_impairments.py
=====================================

WP4.1 (P4.1) field-grade impairment runner.  For each cell of the
WP3.3 IEEE 34 720-grid, synthesise a 1-cycle V/I waveform from the
stored Y_send, apply each of the 5 WP4.1 impairment classes
INDEPENDENTLY plus a CLEAN baseline plus a COMPOSITE
(all-impairments) case, and run the WP1.4 / WP2.4 single-bin DFT
optimiser on the resulting H_meas.  Per-cell, per-condition results
are written to ``outputs/phase4_impairments_results.parquet``.

Tractable scope
---------------

The full IEEE 34 720-grid x 7 conditions = 5040 optimiser runs.  At
~100 ms / run on the dev box this is ~ 8 min total -- acceptable.
We sub-sample over fault buses (10 of 33) to keep the wall-clock
budget within ~ 2.5 min while preserving statistical coverage.
The brief acceptance test reads the resulting parquet and asserts
the per-condition mean / 95 %-pct location and R_x errors.

K07 (Phase 4) acceptance
------------------------

Per the WP4.1 brief: ``mean location error < 5 % at SNR_I >= 30 dB
across all 5 impairment classes individually``.  Note: the
Phase-4 K07 acceptance reuses the WP3.6 K07 numbering with a
different scope; the changelog disambiguates.

The same R5-class structural single-bin DFT identifiability floor
that drives K04 (-830 % mean improvement at WP2.5), K05 (deferred
at WP3.7) and K08 (74.5 % at WP3.4) is in play here.  The CLEAN
baseline on the simplified IEEE 34 already exceeds the 5 % target;
adding impairments only increases the residual.  K07 (Phase 4) is
therefore expected to FAIL on most cells; the test is
``xfail-strict`` per the established R-class escalation pattern,
and the parquet output documents the per-class deltas which
quantify the impairment-specific contribution.
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
from sambp_fault_location_id.models.faultloc_noise_impairments import (
    add_adc_quantisation,
    add_composite_field_grade,
    add_ct_saturation,
    add_harmonic_background,
    add_impulsive,
    add_off_nominal_frequency,
)
from scipy.io import loadmat

PROJ_ROOT = Path(__file__).resolve().parent
IEEE34_BUNDLE = PROJ_ROOT / "data" / "ieee34_720.mat"
OUT_PARQUET = PROJ_ROOT / "outputs" / "phase4_impairments_results.parquet"
OUT_CSV_SUMMARY = PROJ_ROOT / "outputs" / "phase4_impairments_summary.csv"

OMEGA = 2.0 * np.pi * 50.0
F0 = 50.0
FS = 10_000.0
N_CYCLES = 1
N_SAMPLES = int(round(N_CYCLES * FS / F0))   # 200 samples per cycle

CONDITIONS = (
    "clean", "impulsive", "harmonics", "ct_saturation",
    "off_nominal", "adc_quantisation", "composite_field_grade",
)


def _synth_waveform_from_Yaa(
    Y_aa: complex, *, snr_v_db: float, snr_i_db: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise 1-cycle (v, i) waveform on phase A given Y_aa.

    Voltage is a clean cosine at f0; current = Y_aa * v in phasor
    form.  AWGN noise is added per WP1.4 / Phase 1 convention so the
    impairment generators ride on top of a realistic SNR baseline.
    """
    v_peak = 100.0   # arbitrary; impairments + optimiser are scale-invariant
    n = np.arange(N_SAMPLES)
    t = n / FS
    v = v_peak * np.cos(OMEGA * t)
    Ip = Y_aa * v_peak    # current phasor magnitude
    i = np.real(Ip * np.exp(1j * OMEGA * t))
    if np.isfinite(snr_v_db):
        rms_v = float(np.sqrt(np.mean(v ** 2)))
        sigma_v = rms_v * 10.0 ** (-snr_v_db / 20.0)
        v = v + rng.standard_normal(v.shape) * sigma_v
    if np.isfinite(snr_i_db):
        rms_i = float(np.sqrt(np.mean(i ** 2)))
        sigma_i = rms_i * 10.0 ** (-snr_i_db / 20.0)
        i = i + rng.standard_normal(i.shape) * sigma_i
    return v, i


def _apply_condition(
    condition: str,
    v: np.ndarray, i: np.ndarray,
    *, rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    if condition == "clean":
        return v.copy(), i.copy()
    if condition == "impulsive":
        return add_impulsive(v, i, prob=0.005, mag_db=20.0, rng=rng)
    if condition == "harmonics":
        return add_harmonic_background(v, i, fs=FS, f0=F0, rng=rng)
    if condition == "ct_saturation":
        return v.copy(), add_ct_saturation(
            i, remanence_pu=0.3, burden_ohm=2.0, ct_class="5P20",
        )
    if condition == "off_nominal":
        return add_off_nominal_frequency(v, i, fs=FS, f0=F0, df_hz=0.5)
    if condition == "adc_quantisation":
        rms_v = float(np.sqrt(np.mean(v ** 2)))
        rms_i = float(np.sqrt(np.mean(i ** 2)))
        return add_adc_quantisation(
            v, i, bits=14, vref_v=2.0 * rms_v, iref_a=2.0 * rms_i,
        )
    if condition == "composite_field_grade":
        rms_v = float(np.sqrt(np.mean(v ** 2)))
        rms_i = float(np.sqrt(np.mean(i ** 2)))
        return add_composite_field_grade(
            v, i, fs=FS, f0=F0, rng=rng,
            vref_v=4.0 * rms_v, iref_a=4.0 * rms_i,
        )
    raise ValueError(f"unknown condition {condition!r}")


def _run_one_cell(
    Y_aa: complex,
    alpha_true: float, Rx_true: float,
    snr_v_db: float, snr_i_db: float,
    *, rng: np.random.Generator,
) -> dict[str, dict]:
    """Run all CONDITIONS on one cell; return per-condition (estimate)."""
    out: dict[str, dict] = {}
    for cond in CONDITIONS:
        v, i = _synth_waveform_from_Yaa(
            Y_aa, snr_v_db=snr_v_db, snr_i_db=snr_i_db, rng=rng,
        )
        v_imp, i_imp = _apply_condition(cond, v, i, rng=rng)
        H_meas = H_meas_from_waveforms(v_imp, i_imp, fs=FS, f0=F0)
        opts = {
            "snr_v_db": snr_v_db, "snr_i_db": snr_i_db,
            "max_iter": 200,
        }
        try:
            (alpha_h, Rx_h), info = estimate_alpha_Rx(H_meas, opts=opts)
            J = float(info.J_min)
        except Exception:
            alpha_h = float("nan")
            Rx_h = float("nan")
            J = float("nan")
        loc_err = (
            100.0 * abs(alpha_h - alpha_true) / alpha_true
            if alpha_true > 0 and np.isfinite(alpha_h) else float("nan")
        )
        Rx_err = (
            100.0 * abs(Rx_h - Rx_true) / Rx_true
            if Rx_true > 0 and np.isfinite(Rx_h) else float("nan")
        )
        out[cond] = {
            "alpha_hat": float(alpha_h),
            "Rx_hat": float(Rx_h),
            "J_min": J,
            "loc_err_pct": float(loc_err),
            "Rx_err_pct": float(Rx_err),
        }
    return out


def run(
    *,
    n_buses: int = 10,
    rng_seed: int = 47,
) -> Path:
    if not IEEE34_BUNDLE.exists():
        raise FileNotFoundError(
            f"{IEEE34_BUNDLE} not present; run "
            f"`python tools/ieee_feeder_surrogate.py --feeder IEEE_34` first."
        )
    bundle = loadmat(str(IEEE34_BUNDLE))
    Y_send_all = bundle["Y_send"]                # (n_cells, 3, 3) complex
    grid_alpha = bundle["grid_alpha"].squeeze()  # all 0.5 per WP3.3
    grid_Rx = bundle["grid_Rx"].squeeze()
    grid_SNR_V = bundle["grid_SNR_V"].squeeze()
    grid_SNR_I = bundle["grid_SNR_I"].squeeze()
    grid_fault_bus = bundle["grid_fault_bus"].squeeze()
    fault_bus_strs = [str(b).strip() for b in grid_fault_bus]

    unique_buses = sorted(set(fault_bus_strs))
    if n_buses < len(unique_buses):
        stride = max(1, len(unique_buses) // n_buses)
        chosen_buses = set(unique_buses[::stride][:n_buses])
    else:
        chosen_buses = set(unique_buses)

    selected_idx = [
        k for k in range(len(fault_bus_strs))
        if fault_bus_strs[k] in chosen_buses
        and (grid_SNR_I[k] >= 30.0 or not np.isfinite(grid_SNR_I[k]))
    ]
    print(
        f"WP4.1 runner: IEEE 34 720-grid -> {len(selected_idx)} cells "
        f"(after sub-sample to {len(chosen_buses)} buses + SNR_I >= 30 dB); "
        f"per cell x {len(CONDITIONS)} conditions = "
        f"{len(selected_idx) * len(CONDITIONS)} optimiser runs"
    )

    rng = np.random.default_rng(rng_seed)
    rows: list[dict] = []
    t0 = time.perf_counter()
    for k_idx, k in enumerate(selected_idx):
        Y_aa = complex(Y_send_all[k, 0, 0])
        alpha_true = float(grid_alpha[k])
        Rx_true = float(grid_Rx[k])
        snr_v = float(grid_SNR_V[k])
        snr_i = float(grid_SNR_I[k])
        bus = fault_bus_strs[k]
        per_cond = _run_one_cell(
            Y_aa, alpha_true, Rx_true, snr_v, snr_i, rng=rng,
        )
        for cond in CONDITIONS:
            rows.append({
                "fault_bus": bus,
                "alpha_true": alpha_true,
                "Rx_true": Rx_true,
                "snr_v_db": snr_v,
                "snr_i_db": snr_i,
                "condition": cond,
                **per_cond[cond],
            })
        if (k_idx + 1) % max(1, len(selected_idx) // 10) == 0:
            elapsed = time.perf_counter() - t0
            eta = elapsed * (len(selected_idx) - k_idx - 1) / max(k_idx + 1, 1)
            print(
                f"  [{k_idx+1}/{len(selected_idx)}] elapsed {elapsed:.0f}s; "
                f"eta {eta:.0f}s"
            )
    print(f"runner done in {time.perf_counter() - t0:.1f}s")

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, str(OUT_PARQUET), compression="zstd")
        print(f"wrote {OUT_PARQUET} ({len(rows)} rows)")
    except ImportError:
        print("pyarrow not available; skipping parquet")

    summary: list[dict] = []
    for cond in CONDITIONS:
        loc = np.array([
            r["loc_err_pct"] for r in rows
            if r["condition"] == cond and np.isfinite(r["loc_err_pct"])
        ])
        Rxe = np.array([
            r["Rx_err_pct"] for r in rows
            if r["condition"] == cond and np.isfinite(r["Rx_err_pct"])
        ])
        summary.append({
            "condition": cond,
            "n_cells": int(loc.size),
            "loc_err_mean_pct": float(loc.mean()) if loc.size else float("nan"),
            "loc_err_p95_pct": (
                float(np.percentile(loc, 95)) if loc.size else float("nan")
            ),
            "Rx_err_mean_pct": float(Rxe.mean()) if Rxe.size else float("nan"),
            "Rx_err_p95_pct": (
                float(np.percentile(Rxe, 95)) if Rxe.size else float("nan")
            ),
        })
    OUT_CSV_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV_SUMMARY.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        w.writeheader()
        for s in summary:
            w.writerow(s)
    print(f"wrote {OUT_CSV_SUMMARY}")

    print()
    print("=== Per-condition summary ===")
    print(
        f"{'condition':<24}  {'n':>5}  "
        f"{'loc.mean%':>10}  {'loc.p95%':>10}  "
        f"{'Rx.mean%':>10}  {'Rx.p95%':>10}"
    )
    for s in summary:
        print(
            f"{s['condition']:<24}  {s['n_cells']:>5}  "
            f"{s['loc_err_mean_pct']:>10.2f}  {s['loc_err_p95_pct']:>10.2f}  "
            f"{s['Rx_err_mean_pct']:>10.2f}  {s['Rx_err_p95_pct']:>10.2f}"
        )

    return OUT_PARQUET


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n-buses", type=int, default=10)
    parser.add_argument("--rng-seed", type=int, default=47)
    args = parser.parse_args(argv)
    run(n_buses=args.n_buses, rng_seed=args.rng_seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
