"""compare_pscad_emtp_50sec.py
================================

WP1.3 triangulation: pairwise per-cell RMS comparison across the
three Phase-1 datasets.

  data/pscad_720.mat            cosh/sinh ABCD distributed-parameter
  data/emtp_720.mat             50-section pi-model state-space
  data/ref_50section_720.mat    50-section pi-model state-space (canonical
                                WP1.3 reference; independent rng seed)

Writes ``outputs/phase1_simulator_disagreement.csv`` with columns:

  cell, alpha, Rx_ohm, SNR_V_dB, SNR_I_dB,
  rms_pscad_emtp_pct, rms_pscad_ref50_pct, rms_emtp_ref50_pct, max_pct

Stat summary (median, p95, max per pair) is printed to stdout.

Usage
-----
    python tools/compare_pscad_emtp_50sec.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def per_cell_rms_pct(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    diff = a - b
    rms_diff = np.sqrt(np.mean(diff ** 2, axis=1))
    rms_ref = np.sqrt(np.mean(a ** 2, axis=1))
    rms_ref = np.where(rms_ref == 0, np.finfo(float).eps, rms_ref)
    return 100.0 * rms_diff / rms_ref


def stats(label: str, x: np.ndarray) -> str:
    return (
        f"  {label:<22s}  min={x.min():.4f}  median={np.median(x):.4f}  "
        f"p95={np.percentile(x, 95):.4f}  max={x.max():.4f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pscad", type=Path, default=Path("data/pscad_720.mat"))
    parser.add_argument("--emtp", type=Path, default=Path("data/emtp_720.mat"))
    parser.add_argument(
        "--ref50",
        type=Path,
        default=Path("data/ref_50section_720.mat"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/phase1_simulator_disagreement.csv"),
    )
    args = parser.parse_args(argv)

    for p in (args.pscad, args.emtp, args.ref50):
        if not p.exists():
            print(f"compare_pscad_emtp_50sec: missing {p}", file=sys.stderr)
            return 2

    A = loadmat(str(args.pscad))
    B = loadmat(str(args.emtp))
    R = loadmat(str(args.ref50))
    n_cells = A["V"].shape[0]
    if not (A["V"].shape == B["V"].shape == R["V"].shape):
        print("compare_pscad_emtp_50sec: shape mismatch", file=sys.stderr)
        return 3

    # Use V channel for the headline RMS; do the same on I for the CSV.
    rms_pe_V = per_cell_rms_pct(A["V"], B["V"])
    rms_pe_I = per_cell_rms_pct(A["I"], B["I"])
    rms_pr_V = per_cell_rms_pct(A["V"], R["V"])
    rms_pr_I = per_cell_rms_pct(A["I"], R["I"])
    rms_er_V = per_cell_rms_pct(B["V"], R["V"])
    rms_er_I = per_cell_rms_pct(B["I"], R["I"])

    rms_pe = np.maximum(rms_pe_V, rms_pe_I)
    rms_pr = np.maximum(rms_pr_V, rms_pr_I)
    rms_er = np.maximum(rms_er_V, rms_er_I)
    max_per_cell = np.maximum.reduce([rms_pe, rms_pr, rms_er])

    grid_alpha = A["grid_alpha"].squeeze()
    grid_Rx = A["grid_Rx"].squeeze()
    grid_SNR_V = A["grid_SNR_V"].squeeze()
    grid_SNR_I = A["grid_SNR_I"].squeeze()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "cell", "alpha", "Rx_ohm", "SNR_V_dB", "SNR_I_dB",
                "rms_pscad_emtp_pct", "rms_pscad_ref50_pct",
                "rms_emtp_ref50_pct", "max_pct",
            ]
        )
        for k in range(n_cells):
            w.writerow(
                [
                    k,
                    f"{float(grid_alpha[k]):.3f}",
                    f"{float(grid_Rx[k]):.1f}",
                    f"{float(grid_SNR_V[k]):.1f}",
                    f"{float(grid_SNR_I[k]):.1f}",
                    f"{rms_pe[k]:.6f}",
                    f"{rms_pr[k]:.6f}",
                    f"{rms_er[k]:.6f}",
                    f"{max_per_cell[k]:.6f}",
                ]
            )

    print(f"compare_pscad_emtp_50sec: cells = {n_cells}")
    print("Per-cell max(V, I) RMS-diff (%):")
    print(stats("PSCAD vs EMTP", rms_pe))
    print(stats("PSCAD vs ref50", rms_pr))
    print(stats("EMTP vs ref50", rms_er))
    print(stats("max across pairs", max_per_cell))

    # Filter to noiseless cells for the pure model gap
    mask = np.isinf(grid_SNR_V) & np.isinf(grid_SNR_I)
    if mask.sum():
        print(f"\nNoiseless subset ({int(mask.sum())} cells):")
        print(stats("PSCAD vs EMTP", rms_pe[mask]))
        print(stats("PSCAD vs ref50", rms_pr[mask]))
        print(stats("EMTP vs ref50", rms_er[mask]))

    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
