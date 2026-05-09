"""phase0_synth.py
==================

Producer for ``outputs/phase0_capture_and_timing.csv`` and
``outputs/phase0_hyperparam_sensitivity.csv``.

The canonical implementations live in MATLAB
(``matlab/run_capture_stats.m`` and ``matlab/run_hyperparam_sensitivity.m``)
and are run by the lead engineer once a licensed MATLAB is available.
This Python helper exists so the two CSV artefacts can be regenerated
on machines without MATLAB during P0.4 (and so the CSV format stays in
lockstep between the two runtimes).

Numbers are produced from the IEEE_Access-2 v1 manuscript's reported
headline values, perturbed by a deterministic synthetic noise model.
They are sensible Phase-0 placeholders, not measured results - the
MATLAB scripts will overwrite them with measurements.

Usage
-----
    python tools/phase0_synth.py
    python tools/phase0_synth.py --out-dir outputs/

Output schemas
--------------
    phase0_capture_and_timing.csv
        metric,value,unit,n_samples,notes
    phase0_hyperparam_sensitivity.csv
        h_alpha,beta,mean_loc_err_pct,n_cases
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np


def write_capture_and_timing(out_dir: Path, n_total: int = 720) -> Path:
    """Synthesise the capture + timing CSV.

    Capture statistic: a high but realistic figure for Phase 0 with a
    finite-difference gradient.  Median CPU time on the order of 30 ms,
    95th-percentile around 60 ms - in line with v1 reported behaviour
    on a single-bin DFT cost surface.
    """
    rng = np.random.default_rng(seed=42)
    capture_pct = 99.31
    n_calls = 1000
    samples_ms = rng.lognormal(mean=np.log(28.0), sigma=0.35, size=n_calls)
    median_ms = float(np.median(samples_ms))
    p95_ms = float(np.percentile(samples_ms, 95))

    out_path = out_dir / "phase0_capture_and_timing.csv"
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value", "unit", "n_samples", "notes"])
        w.writerow(
            [
                "global_optimum_capture",
                f"{capture_pct:.4f}",
                "%",
                n_total,
                "J<1e-12 at Stage-2 termination (synth placeholder)",
            ]
        )
        w.writerow(
            [
                "cpu_time_median",
                f"{median_ms:.4f}",
                "ms",
                n_calls,
                "representative cell (alpha=0.5 Rx=1000 noiseless), synth",
            ]
        )
        w.writerow(
            [
                "cpu_time_p95",
                f"{p95_ms:.4f}",
                "ms",
                n_calls,
                "representative cell (alpha=0.5 Rx=1000 noiseless), synth",
            ]
        )
    print(
        f"phase0_synth: wrote {out_path} "
        f"(capture={capture_pct:.2f}%, median={median_ms:.2f} ms, "
        f"p95={p95_ms:.2f} ms)"
    )
    return out_path


def write_hyperparam_sensitivity(out_dir: Path, n_cases: int = 720) -> Path:
    """Synthesise the 9-cell sensitivity CSV.

    Mean location error is centred on the v1 headline value (1.18 % at
    SNR_I = 20 dB averaged across the grid) and varies modestly across
    h_alpha and beta - smaller h_alpha and middle-of-range beta give
    the lowest error.  Numbers are deterministic for reproducibility.
    """
    h_grid = [1e-3, 1e-4, 1e-5]
    beta_grid = [0.3, 0.5, 0.7]

    # Centre value, perturbed deterministically by hyperparameter index.
    base = 1.18

    out_path = out_dir / "phase0_hyperparam_sensitivity.csv"
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["h_alpha", "beta", "mean_loc_err_pct", "n_cases"])
        for ih, h_alpha in enumerate(h_grid):
            for ib, beta in enumerate(beta_grid):
                # h_alpha=1e-4 (ih=1) and beta=0.5 (ib=1) are best.
                penalty = (
                    0.10 * abs(ih - 1)         # truncation bias
                    + 0.06 * abs(ib - 1)       # line-search aggressiveness
                )
                err = base * (1.0 + penalty)
                w.writerow(
                    [
                        f"{h_alpha:.0e}",
                        f"{beta:.1f}",
                        f"{err:.6f}",
                        n_cases,
                    ]
                )
    print(f"phase0_synth: wrote {out_path}")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory to write the two CSVs into (default: outputs/).",
    )
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_capture_and_timing(args.out_dir)
    write_hyperparam_sensitivity(args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
