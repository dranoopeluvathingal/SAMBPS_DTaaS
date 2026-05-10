"""
run_faultloc_phase3_threephase.py
==================================
Phase-3 three-phase / IEEE-feeders / Taylor-Fourier runner for the SAMBP
Fault-Location Identification project (W10-W24, ~50 PD).  Closes
deliverable D-D and decision gate D3.

WP3.1 SKELETON (status this commit).  The runner skeleton:
    * Loads the IEEE 13-node feeder via faultloc_ieee_feeders.load_feeder.
    * Sweeps a small (alpha x R_x) grid (3 x 3 = 9 cells) at three
      candidate fault buses (632, 645, 671) using
      faultloc_ieee_feeders.inject_hif (placeholder waveforms from
      the WP3.1 H_phase model).
    * Runs the placeholder pipeline in parallel via joblib (n_jobs=-1
      caps at 4 to fit the dev box) so the parallelisation surface is
      exercised before WP3.2/3.3 plumb in the real feeder waveforms.
    * Writes outputs/phase3_skeleton_smoke.csv (one row per cell) so
      a downstream WP3.2 commit has a regression baseline.

WP3.2-3.7 land the rest of the pipeline:
    WP3.2  Add laterals, tap loads, >= 1 DG; parameterise upstream
           Thevenin source.
    WP3.3  Build IEEE 13- / 34- / 123-node feeder digital twins
           (faultloc_ieee_feeders.py grows here).
    WP3.4  Add SLG, LL, LLG fault types; re-run extended grid.
    WP3.5  Replace single-bin DFT with first-order Taylor-Fourier estimator
           (faultloc_taylor_fourier.py); identifiability map.
    WP3.6  Multi-port FIM (faultloc_fim_multiport.py); update ML cost
           and CRLB overlays.
    WP3.7  Validate on the CNRS-2024 IEEE-34 HIF dataset.

Acceptance test (T-D1, gated on WP3.7)
--------------------------------------
Mean location error < 3 % on IEEE 34-node at SNR >= 30 dB; phasor-bias
improvement vs single-bin DFT >= 50 % on arc-modulated waveforms;
identifiability map published.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from joblib import Parallel, delayed
from sambp_fault_location_id.models.faultloc_ieee_feeders import (
    inject_hif,
    load_feeder,
)
from sambp_fault_location_id.models.faultloc_three_phase_model import (
    H_phase,
)

PROJ_ROOT = Path(__file__).resolve().parent
OUT_DIR = PROJ_ROOT / "outputs"

ALPHAS = (0.30, 0.50, 0.70)
RXS = (100.0, 1000.0, 5000.0)
FAULT_BUSES = ("632", "645", "671")


def _process_one_cell(args):
    """Worker for one (bus, alpha, R_x) cell.  WP3.1 SKELETON: just
    confirms the WP3.1 model returns a 3-vector; downstream WPs swap
    in the real estimator + cost evaluation."""
    bus, alpha, Rx = args
    feeder = load_feeder("IEEE_13")
    bundle = inject_hif(feeder, bus, alpha, Rx)
    omega0 = 2.0 * np.pi * 50.0
    H_pred = H_phase(omega0, alpha, Rx)
    # Skeleton metric: |H_pred| amplitudes and a sanity check on the
    # waveform bundle shape.  WP3.5/3.6 introduce the proper estimator.
    return {
        "feeder": feeder.name,
        "bus": bus,
        "alpha": alpha,
        "Rx": Rx,
        "H_phase_a_mag": float(np.abs(H_pred[0])),
        "H_phase_b_mag": float(np.abs(H_pred[1])),
        "H_phase_c_mag": float(np.abs(H_pred[2])),
        "V_shape": str(bundle.V.shape),
        "I_shape": str(bundle.I.shape),
        "status": "skeleton",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--n-jobs", type=int, default=-1,
        help="joblib n_jobs (default -1 = all cores; capped to 4 on dev box)",
    )
    args = parser.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    n_jobs = min(args.n_jobs, 4) if args.n_jobs > 0 else 4
    cells = [(bus, a, R) for bus in FAULT_BUSES for a in ALPHAS for R in RXS]
    print(f"WP3.1 skeleton runner: {len(cells)} cells, n_jobs={n_jobs}")

    t0 = time.perf_counter()
    rows = Parallel(n_jobs=n_jobs)(
        delayed(_process_one_cell)(c) for c in cells
    )
    elapsed = time.perf_counter() - t0
    print(f"done in {elapsed:.1f}s ({elapsed * 1000 / len(cells):.1f} ms/cell)")

    out_path = OUT_DIR / "phase3_skeleton_smoke.csv"
    with out_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"wrote {out_path} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
