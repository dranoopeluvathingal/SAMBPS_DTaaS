"""
run_faultloc_phase3_taylor_fourier_bias.py
=============================================

WP3.5 K06 measurement: Taylor-Fourier vs single-bin DFT phasor-bias
on an arc-modulated waveform at the brief representative case
(alpha = 0.5, R_x = 2000 ohm, SNR_I = 30 dB).

For each Monte-Carlo trial, generate a 1-cycle arc-modulated voltage
+ current pair via tools/wang2020_arc_stimulus.py (Wang-2020-style
distortion-controllable surrogate), add SNR_I = 30 dB AWGN to the
current channel, run both estimators on the noisy waveforms, and
record the bias |H_estimator - H_true| / |H_true|.

The brief acceptance K06 = bias improvement (DFT_bias - TFT_bias) /
DFT_bias >= 50 %.

Outputs
-------

* outputs/phase3_tft_vs_dft_bias.csv -- per-trial bias for both
  estimators; summary statistics at the bottom.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    H_meas_from_waveforms,
)
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    H_distributed,
)
from sambp_fault_location_id.models.faultloc_taylor_fourier import (
    H_meas_from_waveforms_tft,
)

from tools.wang2020_arc_stimulus import add_awgn, synthesise_voltage  # noqa: E402

PROJ_ROOT = Path(__file__).resolve().parent
OUT_DIR = PROJ_ROOT / "outputs"

OMEGA = 2.0 * np.pi * 50.0
FS = 10_000.0
F0 = 50.0
N_CYCLES = 1


def run(
    *,
    alpha_true: float = 0.5,
    Rx_true: float = 2000.0,
    snr_i_db: float = 30.0,
    distortion_index: float = 0.5,
    n_trials: int = 200,
    rng_seed: int = 23,
) -> Path:
    """Run the WP3.5 K06 bias measurement and write the per-trial CSV."""
    H_true = H_distributed(alpha_true, Rx_true, OMEGA)
    print(
        f"WP3.5 K06: alpha={alpha_true}, R_x={Rx_true} ohm; "
        f"H_true = {H_true:.6e}"
    )
    print(
        f"  arc distortion_index={distortion_index}, SNR_I={snr_i_db} dB, "
        f"n_trials={n_trials}"
    )

    # Voltage waveform (assumed clean per the WP3.5 brief; the bias
    # measurement is on the current-channel noise).  V_phase = 1 V
    # at unit amplitude; H = I/V so H itself is in siemens.
    rng = np.random.default_rng(rng_seed)

    rows: list[dict] = []
    bias_dft_all: list[float] = []
    bias_tft_all: list[float] = []
    for trial in range(n_trials):
        # Synthesise: voltage at unit amplitude, current = H_true * voltage
        # plus arc distortion (which biases the phasor).  Apply the
        # distortion-controllable arc model to the CURRENT channel only
        # (the standard single-ended assumption is V is dominated by
        # the source and is arc-free; the arc nonlinearity shows up
        # in the current).
        H_v = 1.0 + 0.0j
        _, v = synthesise_voltage(
            H_true=H_v, n_cycles=N_CYCLES, fs=FS, f0=F0,
            distortion_index=0.0,            # voltage clean
        )
        _, i = synthesise_voltage(
            H_true=H_true, n_cycles=N_CYCLES, fs=FS, f0=F0,
            distortion_index=distortion_index,
        )
        i_noisy = add_awgn(i, snr_i_db, rng=rng)

        # Estimator A: single-bin DFT (Phase 1 / 2 baseline)
        H_dft = H_meas_from_waveforms(v, i_noisy, fs=FS, f0=F0)
        bias_dft = abs(H_dft - H_true) / abs(H_true)

        # Estimator B: Taylor-Fourier K = 1 (WP3.5)
        H_tft = H_meas_from_waveforms_tft(v, i_noisy, fs=FS, f0=F0, K=1)
        bias_tft = abs(H_tft - H_true) / abs(H_true)

        bias_dft_all.append(bias_dft)
        bias_tft_all.append(bias_tft)
        rows.append({
            "trial": int(trial),
            "alpha_true": float(alpha_true),
            "Rx_true": float(Rx_true),
            "snr_i_db": float(snr_i_db),
            "distortion_index": float(distortion_index),
            "H_true_real": float(H_true.real),
            "H_true_imag": float(H_true.imag),
            "H_dft_real": float(H_dft.real),
            "H_dft_imag": float(H_dft.imag),
            "H_tft_real": float(H_tft.real),
            "H_tft_imag": float(H_tft.imag),
            "bias_dft_pct": float(100.0 * bias_dft),
            "bias_tft_pct": float(100.0 * bias_tft),
        })

    bias_dft_arr = np.array(bias_dft_all)
    bias_tft_arr = np.array(bias_tft_all)
    mean_dft = float(bias_dft_arr.mean())
    mean_tft = float(bias_tft_arr.mean())
    median_dft = float(np.median(bias_dft_arr))
    median_tft = float(np.median(bias_tft_arr))

    if mean_dft > 0:
        improvement_mean = 100.0 * (mean_dft - mean_tft) / mean_dft
    else:
        improvement_mean = float("nan")
    if median_dft > 0:
        improvement_median = 100.0 * (median_dft - median_tft) / median_dft
    else:
        improvement_median = float("nan")

    print()
    print(f"  DFT  bias  mean = {100*mean_dft:.4f} %, "
          f"median = {100*median_dft:.4f} %")
    print(f"  TFT  bias  mean = {100*mean_tft:.4f} %, "
          f"median = {100*median_tft:.4f} %")
    print(f"  K06  improvement (mean)   = {improvement_mean:.2f} % "
          f"(target: >= 50 %)")
    print(f"  K06  improvement (median) = {improvement_median:.2f} %")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "phase3_tft_vs_dft_bias.csv"
    with out_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
        # Summary footer rows.
        w.writerow({k: "" for k in rows[0]})
        w.writerow({
            "trial": "SUMMARY",
            "alpha_true": float(alpha_true),
            "Rx_true": float(Rx_true),
            "snr_i_db": float(snr_i_db),
            "distortion_index": float(distortion_index),
            "H_true_real": "",
            "H_true_imag": "",
            "H_dft_real": "mean_bias_dft_pct",
            "H_dft_imag": f"{100*mean_dft:.6f}",
            "H_tft_real": "mean_bias_tft_pct",
            "H_tft_imag": f"{100*mean_tft:.6f}",
            "bias_dft_pct": "improvement_mean_pct",
            "bias_tft_pct": f"{improvement_mean:.4f}",
        })
        w.writerow({
            "trial": "SUMMARY",
            "alpha_true": float(alpha_true),
            "Rx_true": float(Rx_true),
            "snr_i_db": float(snr_i_db),
            "distortion_index": float(distortion_index),
            "H_true_real": "",
            "H_true_imag": "",
            "H_dft_real": "median_bias_dft_pct",
            "H_dft_imag": f"{100*median_dft:.6f}",
            "H_tft_real": "median_bias_tft_pct",
            "H_tft_imag": f"{100*median_tft:.6f}",
            "bias_dft_pct": "improvement_median_pct",
            "bias_tft_pct": f"{improvement_median:.4f}",
        })
    print(f"wrote {out_path}")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--Rx", type=float, default=2000.0)
    parser.add_argument("--snr-i-db", type=float, default=30.0)
    parser.add_argument("--distortion-index", type=float, default=0.5)
    parser.add_argument("--n-trials", type=int, default=200)
    parser.add_argument("--rng-seed", type=int, default=23)
    args = parser.parse_args(argv)
    run(
        alpha_true=args.alpha, Rx_true=args.Rx, snr_i_db=args.snr_i_db,
        distortion_index=args.distortion_index, n_trials=args.n_trials,
        rng_seed=args.rng_seed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
