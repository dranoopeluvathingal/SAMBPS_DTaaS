"""
run_faultloc_phase3_fault_types.py
====================================

WP3.4 fault-type classification runner.  For each (fault_bus, R_x,
truth_fault_type, SNR_I, trial) cell, generate a noisy 3x3 Y_send
observation and run the WP3.4 multi-type classifier in
``inverse_estimation/faultloc_two_stage_optimiser.classify_fault_type_3ph``;
record (truth, predicted) for the confusion-matrix output.

Outputs
-------

* ``outputs/phase3_fault_types.parquet`` -- long-format per-trial
  results: feeder, fault_bus, alpha, Rx, fault_type_true, snrI,
  trial, fault_type_hat, alpha_hat, Rx_hat, J_min, J_SLG, J_LL,
  J_LLG, correct.

* ``outputs/phase3_fault_type_confusion.csv`` -- 3x3 confusion matrix
  (truth on rows, predicted on columns) with per-cell counts and
  per-row recall percentages, plus a header row of the overall
  accuracy across SNR_I subsets.

Tractable scope
---------------

The WP3.4 brief asks for the IEEE 34 grid + 100-trial Monte-Carlo;
the dev-box budget would be ~5.5 h at full scale.  This runner
reduces the grid to a representative sub-sample (10 fault buses out
of 33; 10 trials per cell instead of 100; SNR_I in {30, 40, inf}
only -- the "at SNR_I >= 30 dB" subset of the brief acceptance) so
the runner completes in ~10 minutes on the dev box.  The acceptance
test in ``tests/test_fault_type_id.py`` reads the parquet and tests
the same SNR_I subset.

A future commit ("WP3.4 follow-up") can re-run with --full to
cover the full 33 buses x 5 R_x x 3 types x 100 trials grid.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    add_complex_gaussian_noise_to_Y,
    classify_fault_type_3ph,
)
from sambp_fault_location_id.models.faultloc_ieee_feeders import build_ieee34
from sambp_fault_location_id.models.faultloc_three_phase_model import FAULT_TYPES

PROJ_ROOT = Path(__file__).resolve().parent
OUT_DIR = PROJ_ROOT / "outputs"

OMEGA = 2 * np.pi * 50.0
RXS = (100.0, 500.0, 1000.0, 2000.0, 5000.0)
SNR_IS_DEFAULT = (30.0, 40.0, np.inf)
SNR_IS_FULL = (20.0, 30.0, 40.0, np.inf)


def _select_buses(network, n_sample: int | None) -> list[str]:
    candidate = [b for b in network.data.buses if b != network.data.source_bus]
    if n_sample is None or n_sample >= len(candidate):
        return candidate
    # Deterministic stride sample so different runs cover the same buses.
    stride = max(1, len(candidate) // n_sample)
    return candidate[::stride][:n_sample]


def run(
    *,
    n_buses: int | None = 10,
    n_trials: int = 10,
    snr_is: tuple[float, ...] = SNR_IS_DEFAULT,
    rng_seed: int = 17,
) -> tuple[Path, Path]:
    network = build_ieee34()
    rng = np.random.default_rng(rng_seed)
    buses = _select_buses(network, n_buses)
    print(
        f"WP3.4 runner: feeder=IEEE_34, n_buses={len(buses)}, "
        f"R_x={list(RXS)}, fault_types={list(FAULT_TYPES)}, "
        f"SNR_I={list(snr_is)}, n_trials={n_trials}"
    )

    rows: list[dict] = []
    n_cells_total = (
        len(buses) * len(RXS) * len(FAULT_TYPES) * len(snr_is) * n_trials
    )
    print(f"total cells: {n_cells_total}")
    t0 = time.perf_counter()
    k = 0
    for ft_true in FAULT_TYPES:
        for bus in buses:
            for Rx in RXS:
                Y_clean = network.Y_send(
                    OMEGA, fault_bus=bus, alpha=0.5, Rx=Rx,
                    fault_type=ft_true,
                )
                for snrI in snr_is:
                    for trial in range(n_trials):
                        Y_noisy = add_complex_gaussian_noise_to_Y(
                            Y_clean, snrI, rng=rng,
                        )
                        est = classify_fault_type_3ph(
                            Y_noisy, network, fault_bus=bus, omega=OMEGA,
                        )
                        rows.append({
                            "feeder": "IEEE_34",
                            "fault_bus": bus,
                            "alpha": 0.5,
                            "Rx": float(Rx),
                            "fault_type_true": ft_true,
                            "snrI": float(snrI),
                            "trial": int(trial),
                            "fault_type_hat": est.fault_type_hat,
                            "alpha_hat": float(est.alpha_hat),
                            "Rx_hat": float(est.Rx_hat),
                            "J_min": float(est.J_min),
                            "J_SLG": float(est.J_per_type["SLG"]),
                            "J_LL": float(est.J_per_type["LL"]),
                            "J_LLG": float(est.J_per_type["LLG"]),
                            "correct": int(est.fault_type_hat == ft_true),
                        })
                        k += 1
                        if k % max(1, n_cells_total // 20) == 0:
                            elapsed = time.perf_counter() - t0
                            eta = elapsed * (n_cells_total - k) / max(k, 1)
                            print(
                                f"  {k}/{n_cells_total} cells "
                                f"({100*k/n_cells_total:.0f}%); "
                                f"eta {eta:.0f}s"
                            )
    elapsed = time.perf_counter() - t0
    print(f"runner done in {elapsed:.1f}s")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = OUT_DIR / "phase3_fault_types.parquet"
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, str(parquet_path), compression="zstd")
        print(f"wrote {parquet_path} ({len(rows)} rows)")
    except ImportError:
        print("pyarrow not installed; skipping parquet output")

    confusion = _confusion_matrix(rows, snr_is)
    confusion_path = OUT_DIR / "phase3_fault_type_confusion.csv"
    with confusion_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "subset", "truth",
            *[f"pred_{ft}" for ft in FAULT_TYPES],
            "row_total", "recall_pct",
        ])
        for subset_label, mat in confusion.items():
            for i, ft_true in enumerate(FAULT_TYPES):
                row_total = int(sum(mat[i]))
                recall = (
                    100.0 * mat[i][i] / row_total if row_total > 0 else float("nan")
                )
                w.writerow([
                    subset_label, ft_true,
                    *[int(mat[i][j]) for j in range(len(FAULT_TYPES))],
                    row_total, f"{recall:.2f}",
                ])
        # Overall accuracy summary row at the bottom.
        for subset_label, mat in confusion.items():
            n_correct = int(sum(mat[i][i] for i in range(len(FAULT_TYPES))))
            n_total = int(sum(sum(r) for r in mat))
            acc = 100.0 * n_correct / n_total if n_total > 0 else float("nan")
            w.writerow([
                subset_label, "OVERALL",
                "", "", "", n_total, f"{acc:.2f}",
            ])
    print(f"wrote {confusion_path}")

    print("\n=== Confusion (subset = high-SNR_I, >= 30 dB) ===")
    for ft in FAULT_TYPES:
        i = FAULT_TYPES.index(ft)
        mat = confusion["snrI_ge_30dB"]
        row_total = int(sum(mat[i]))
        recall = 100.0 * mat[i][i] / row_total if row_total > 0 else 0.0
        print(
            f"  {ft:>3} (truth): "
            + " ".join(
                f"pred_{FAULT_TYPES[j]}={int(mat[i][j])}"
                for j in range(len(FAULT_TYPES))
            )
            + f"  recall={recall:.2f}%"
        )
    n_correct_high = sum(
        confusion["snrI_ge_30dB"][i][i] for i in range(len(FAULT_TYPES))
    )
    n_total_high = sum(
        sum(r) for r in confusion["snrI_ge_30dB"]
    )
    acc_high = 100.0 * n_correct_high / n_total_high
    print(f"  OVERALL accuracy at SNR_I >= 30 dB: {acc_high:.2f}% "
          f"({int(n_correct_high)}/{int(n_total_high)})")
    return parquet_path, confusion_path


def _confusion_matrix(rows: list[dict], snr_is: tuple[float, ...]) -> dict:
    """Build per-SNR_I-subset 3x3 confusion matrices.

    Subsets:
      "snrI_inf"     -- noiseless cells only
      "snrI_ge_30dB" -- SNR_I in {30, 40, inf}
      "snrI_eq_30dB" -- SNR_I == 30 only
      "snrI_eq_40dB" -- SNR_I == 40 only
      "all"          -- entire bundle
    """
    out: dict[str, list[list[int]]] = {}
    subsets = {
        "snrI_inf": lambda r: not np.isfinite(r["snrI"]),
        "snrI_eq_30dB": lambda r: abs(r["snrI"] - 30.0) < 0.5,
        "snrI_eq_40dB": lambda r: abs(r["snrI"] - 40.0) < 0.5,
        "snrI_ge_30dB": lambda r: r["snrI"] >= 30.0 or not np.isfinite(r["snrI"]),
        "all": lambda r: True,
    }
    for label, predicate in subsets.items():
        mat = [[0] * len(FAULT_TYPES) for _ in FAULT_TYPES]
        for r in rows:
            if not predicate(r):
                continue
            i = FAULT_TYPES.index(r["fault_type_true"])
            j = FAULT_TYPES.index(r["fault_type_hat"])
            mat[i][j] += 1
        out[label] = mat
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n-buses", type=int, default=10,
                        help="Number of fault buses to sample (default 10; "
                             "use 0 or 33 for the full IEEE 34 grid).")
    parser.add_argument("--n-trials", type=int, default=10,
                        help="Monte-Carlo trials per cell (default 10).")
    parser.add_argument("--full", action="store_true",
                        help="Equivalent to --n-buses 33 --n-trials 100; "
                             "~5.5 h on the dev box.")
    parser.add_argument("--include-snrI-20", action="store_true",
                        help="Add SNR_I = 20 dB to the sweep.")
    parser.add_argument("--rng-seed", type=int, default=17)
    args = parser.parse_args(argv)

    n_buses = args.n_buses or None
    n_trials = args.n_trials
    if args.full:
        n_buses = None
        n_trials = 100
    snr_is = SNR_IS_FULL if args.include_snrI_20 else SNR_IS_DEFAULT

    run(
        n_buses=n_buses, n_trials=n_trials,
        snr_is=snr_is, rng_seed=args.rng_seed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
