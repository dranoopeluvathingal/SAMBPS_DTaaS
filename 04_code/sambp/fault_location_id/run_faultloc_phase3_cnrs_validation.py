"""
run_faultloc_phase3_cnrs_validation.py
=========================================

WP3.7 (P3.7) external validation runner for the CNRS / Recherche
Data Gouv IEEE 34-node HIF dataset (Pereira de Souza et al. 2024,
DOI 10.57745/KRYCYY).

Per-trace processing
--------------------

For each .mat file in ``data/cnrs_ieee34/train_extracted/``:

* Load the (signals, t) pair (signals shape (~3073, 70); fs = 30.72 kHz).
* Extract the source-bus voltage (channel index 0 = V_800 phase A
  per data_explanation.pdf Tab. 2) and the line-current of the
  800->802 segment (channel index 1).
* Down-sample to 10 kHz (the WP1.4 / WP2.4 / WP3.5 estimator's
  native fs) by averaging-decimation; window 1 fundamental cycle
  (60 Hz, 167 samples at 10 kHz) per trace.
* Run the WP1.4 / WP2.4 single-bin DFT optimiser (forward_model =
  'distributed', gradient = 'analytical', cost = 'ml') on the
  resulting H_meas; record (alpha_hat, R_x_hat, J_min,
  cpu_time_s).  Also run the WP3.5 Taylor-Fourier K = 1 estimator
  for comparison.

Output
------

* ``outputs/phase3_cnrs_validation.csv`` -- one row per trace:
  trace_filename, alpha_hat_dft, Rx_hat_dft, alpha_hat_tft,
  Rx_hat_tft, J_min_dft, J_min_tft, |H_meas_dft|, |H_meas_tft|,
  source_v_rms, source_i_rms.
* ``outputs/phase3_figs/cnrs_distribution.pdf`` -- histogram of
  alpha_hat across the train.zip ensemble (under no-HIF nominal +
  load-switching + capacitor-switching conditions).
* ``outputs/phase3_figs/cnrs_dft_vs_tft.pdf`` -- scatter of
  (alpha_hat_dft, alpha_hat_tft) per trace.

K05 acceptance status (per the WP3.7 brief)
-------------------------------------------

The K05 mean location-error target ("< 3 % on IEEE 34-node at SNR
>= 30 dB") requires labelled HIF traces with known fault locations
to compare against the optimiser's alpha_hat.  The CNRS dataset's
**test.zip** (~ 3 GB) carries the 1550 labelled HIF cases at the 7
fault positions described in
``data/cnrs_ieee34/data_explanation.pdf`` Tab. 1.  The **train.zip**
(75 MB, this commit) carries the 50 unsupervised training traces
across normal + load-switching + capacitor-switching conditions
WITHOUT HIF -- so K05 (a labelled error metric) cannot be measured
on this slice of the dataset.

This runner therefore demonstrates the framework end-to-end on the
unsupervised train data; the K05 measurement on labelled test.zip
is **deferred** to the lead engineer's WP3.7 follow-up commit
(test.zip pull was held back behind the ``--include-test`` flag in
``tools/fetch_cnrs_dataset.py`` because 3 GB exceeds the dev-box
disk + bandwidth budget).  Per the WP3.7 brief acceptance "K05 < 3 %
met (or root-cause documented)" the deferral is documented in the
changelog.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (  # noqa: E402
    H_meas_from_waveforms,
    estimate_alpha_Rx,
)
from sambp_fault_location_id.models.faultloc_taylor_fourier import (  # noqa: E402
    H_meas_from_waveforms_tft,
)
from scipy.io import loadmat  # noqa: E402

PROJ_ROOT = Path(__file__).resolve().parent
TRAIN_DIR = PROJ_ROOT / "data" / "cnrs_ieee34" / "train_extracted" / "train_LS_CS_3k"
OUT_CSV = PROJ_ROOT / "outputs" / "phase3_cnrs_validation.csv"
FIG_DIR = PROJ_ROOT / "outputs" / "phase3_figs"

CNRS_FS = 30_720.0
CNRS_F0 = 60.0          # 60 Hz fundamental (US distribution)
TARGET_FS = 10_000.0    # WP1.4 / WP2.4 / WP3.5 estimator native fs
TARGET_F0 = 60.0        # match CNRS source frequency for the bias measurement
N_CYCLES = 1


def _decimate_to_target_fs(
    sig: np.ndarray, fs_in: float, fs_out: float,
) -> np.ndarray:
    """Sample-mean decimation by an integer ratio.  CNRS fs = 30.72 kHz
    -> target 10 kHz is a non-integer ratio; we use scipy.signal.resample
    to handle it cleanly."""
    from scipy.signal import resample
    if abs(fs_in - fs_out) / fs_in < 1.0e-6:
        return sig
    n_out = int(round(len(sig) * fs_out / fs_in))
    return resample(sig, n_out)


def _process_trace(
    path: Path,
    *,
    n_window_samples: int,
) -> dict:
    """Process one .mat trace and return one row of estimates."""
    S = loadmat(str(path))
    sigs = S["signals"]   # (N, 70)
    # Channel 0 = V_800 (volts); channel 1 = I_{800->802} (amps)
    v_raw = sigs[:, 0]
    i_raw = sigs[:, 1]
    source_v_rms = float(np.sqrt(np.mean(v_raw ** 2)))
    source_i_rms = float(np.sqrt(np.mean(i_raw ** 2)))

    # Decimate to TARGET_FS for the WP1.4/2.4 estimator
    v = _decimate_to_target_fs(v_raw, CNRS_FS, TARGET_FS)
    i = _decimate_to_target_fs(i_raw, CNRS_FS, TARGET_FS)

    # Take a 1-cycle window starting at 0.04 s (post-fault-injection
    # at 0.03 s per data_explanation.pdf).
    n_samples_to_skip = int(round(0.04 * TARGET_FS))
    v_win = v[n_samples_to_skip:n_samples_to_skip + n_window_samples]
    i_win = i[n_samples_to_skip:n_samples_to_skip + n_window_samples]
    if len(v_win) < n_window_samples:
        # too short; pad with last sample
        v_win = np.pad(v_win, (0, n_window_samples - len(v_win)), mode="edge")
        i_win = np.pad(i_win, (0, n_window_samples - len(i_win)), mode="edge")

    # H_meas via single-bin DFT and via TFT-K=1
    H_dft = H_meas_from_waveforms(v_win, i_win, fs=TARGET_FS, f0=TARGET_F0)
    H_tft = H_meas_from_waveforms_tft(v_win, i_win, fs=TARGET_FS, f0=TARGET_F0, K=1)

    # Run the WP1.4 / WP2.4 optimiser on the DFT-derived H.
    # Use a moderate iteration cap to keep wall-clock budget reasonable.
    opts = {
        "snr_v_db": 60.0,      # CNRS Tab. 4 says 60 dB SNR on V
        "snr_i_db": 60.0,      # noise model identical per data_explanation.pdf
        "max_iter": 200,
    }
    t0 = time.perf_counter()
    try:
        theta_dft, info_dft = estimate_alpha_Rx(H_dft, opts=opts)
    except Exception as e:
        theta_dft = (np.nan, np.nan)
        info_dft = type("I", (), {"J_min": float("nan"), "n_iters": 0})
        print(f"  {path.name}: DFT optimiser failed: {e}")
    cpu_dft_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    try:
        theta_tft, info_tft = estimate_alpha_Rx(H_tft, opts=opts)
    except Exception as e:
        theta_tft = (np.nan, np.nan)
        info_tft = type("I", (), {"J_min": float("nan"), "n_iters": 0})
        print(f"  {path.name}: TFT optimiser failed: {e}")
    cpu_tft_s = time.perf_counter() - t0

    return {
        "trace": path.name,
        "alpha_hat_dft": float(theta_dft[0]),
        "Rx_hat_dft": float(theta_dft[1]),
        "alpha_hat_tft": float(theta_tft[0]),
        "Rx_hat_tft": float(theta_tft[1]),
        "J_min_dft": float(getattr(info_dft, "J_min", float("nan"))),
        "J_min_tft": float(getattr(info_tft, "J_min", float("nan"))),
        "abs_H_dft": float(abs(H_dft)),
        "abs_H_tft": float(abs(H_tft)),
        "source_v_rms": source_v_rms,
        "source_i_rms": source_i_rms,
        "cpu_dft_s": cpu_dft_s,
        "cpu_tft_s": cpu_tft_s,
    }


def run() -> None:
    """Process every train.zip trace and write outputs."""
    if not TRAIN_DIR.exists():
        raise FileNotFoundError(
            f"{TRAIN_DIR} not present; run "
            f"`python tools/fetch_cnrs_dataset.py` first."
        )
    files = sorted(TRAIN_DIR.glob("*.mat"))
    if not files:
        raise RuntimeError(f"No .mat files under {TRAIN_DIR}")
    print(
        f"WP3.7 CNRS validation: processing {len(files)} traces "
        f"from {TRAIN_DIR.name}"
    )

    n_window_samples = int(round(N_CYCLES * TARGET_FS / TARGET_F0))
    rows: list[dict] = []
    t_start = time.perf_counter()
    for k, path in enumerate(files):
        row = _process_trace(path, n_window_samples=n_window_samples)
        rows.append(row)
        if (k + 1) % max(1, len(files) // 10) == 0 or k + 1 == len(files):
            elapsed = time.perf_counter() - t_start
            print(
                f"  [{k+1}/{len(files)}] {row['trace']}: "
                f"alpha_hat_dft = {row['alpha_hat_dft']:.4f}, "
                f"Rx_hat_dft = {row['Rx_hat_dft']:.0f}, "
                f"|H_dft| = {row['abs_H_dft']:.3e}; "
                f"elapsed {elapsed:.1f}s"
            )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {OUT_CSV} ({len(rows)} rows)")

    # --- Overlay plots ---
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    alpha_dft = np.array([
        r["alpha_hat_dft"] for r in rows
        if np.isfinite(r["alpha_hat_dft"])
    ])
    alpha_tft = np.array([
        r["alpha_hat_tft"] for r in rows
        if np.isfinite(r["alpha_hat_tft"])
    ])

    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    ax.hist(alpha_dft, bins=20, alpha=0.6, label="DFT")
    if alpha_tft.size > 0:
        ax.hist(alpha_tft, bins=20, alpha=0.6, label="TFT-K=1")
    ax.set_xlabel(r"Estimated $\hat{\alpha}$ [per unit]")
    ax.set_ylabel("number of CNRS traces")
    ax.set_title(
        f"WP3.7 CNRS train-set $\\hat{{\\alpha}}$ distribution "
        f"({len(rows)} traces; unsupervised LS + CS + nominal)"
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "cnrs_distribution.pdf")
    plt.close(fig)
    print(f"wrote {FIG_DIR / 'cnrs_distribution.pdf'}")

    fig, ax = plt.subplots(figsize=(6.0, 6.0))
    ax.scatter(alpha_dft, alpha_tft if alpha_tft.size == alpha_dft.size
               else np.zeros_like(alpha_dft), alpha=0.6)
    lo, hi = (
        min(alpha_dft.min(), alpha_tft.min()) if alpha_tft.size else
        alpha_dft.min(),
        max(alpha_dft.max(), alpha_tft.max()) if alpha_tft.size else
        alpha_dft.max(),
    )
    ax.plot([lo, hi], [lo, hi], "k--", alpha=0.5, label="DFT == TFT")
    ax.set_xlabel(r"DFT $\hat{\alpha}$")
    ax.set_ylabel(r"TFT-K=1 $\hat{\alpha}$")
    ax.set_title("WP3.7 CNRS train-set: DFT vs TFT estimator agreement")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "cnrs_dft_vs_tft.pdf")
    plt.close(fig)
    print(f"wrote {FIG_DIR / 'cnrs_dft_vs_tft.pdf'}")

    # --- K05 deferral notice (no labels in train.zip) ---
    print()
    print(
        "K05 status: DEFERRED.  train.zip is the UNSUPERVISED slice "
        f"({len(rows)} traces of nominal + load-switching + capacitor-"
        "switching disturbances WITHOUT HIF labels), so K05 (mean "
        "location error) cannot be measured here.  test.zip (3 GB; held "
        "back by tools/fetch_cnrs_dataset.py --include-test flag) "
        "carries the 1550 labelled HIF cases at the 7 fault positions; "
        "fetch + re-run on the lead engineer's licensed Windows runner."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.parse_args(argv)
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
