"""compare_pscad_emtp.py
==========================

Loads ``data/pscad_720.mat`` and ``data/emtp_720.mat``, computes per-
cell RMS difference of V and I waveforms over the 200-sample window,
prints a text-mode histogram and summary statistics, and writes the
per-cell breakdown to ``outputs/phase1_pscad_vs_emtp.csv``.

Cells whose RMS difference exceeds ``--flag`` (default 2 %) are
marked ``flagged=1`` in the CSV for inspection.

Acceptance thresholds (enforced by ``tests/test_pscad_emtp_consistency.py``):

  median per-cell RMS diff < 1 %
  95th percentile RMS diff < 3 %

# TODO Phase1 PSCAD/EMTP discrepancy
# ----------------------------------
# Currently both `data/pscad_720.mat` and `data/emtp_720.mat` are
# Python surrogates (cosh/sinh ABCD vs 50-section pi-model) using
# **independent noise rng seeds** (42 vs 4242).  As a result the
# time-domain RMS difference is dominated by noise variance rather
# than by model-vs-model disagreement: cells at SNR_I = 20 dB show
# ~14 % RMS diff (noise-floor), driving the consistency test to
# xfail.
#
# This is *not* a real PSCAD-vs-EMTP modelling discrepancy; it is a
# comparator-design artefact of comparing two surrogates with
# independent rng seeds.  Two valid resolutions:
#
#   (a) Replace either surrogate with the canonical PSCAD or EMTP-RV
#       output via run_pscad_720.py / run_emtp_720.py on a licensed
#       Windows station, and configure both simulators with a
#       synchronised cell-indexed noise seed (standard practice for
#       cross-simulator validation).
#   (b) Run the consistency test on the (Inf, Inf) noiseless subset
#       only (45 of 720 cells), which measures pure model-vs-model
#       disagreement; pass --noiseless-only.  This is a useful
#       regression check but does NOT discharge the brief's
#       acceptance, which is over the full 720-cell grid.
#
# Per the WP1.2 brief, this discrepancy is *escalated* (R1) - engage
# Prof. Christian Rehtanz / TU Dortmund for an independent EMTP
# cross-check before WP1.4 cross-platform optimiser re-run.

Usage
-----
    python tools/compare_pscad_emtp.py
    python tools/compare_pscad_emtp.py --flag 2 \\
        --pscad data/pscad_720.mat --emtp data/emtp_720.mat \\
        --out outputs/phase1_pscad_vs_emtp.csv
    python tools/compare_pscad_emtp.py --noiseless-only
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def per_cell_rms_pct(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-cell RMS difference between rows of a and b, normalised by RMS(a)."""
    diff = a - b
    rms_diff = np.sqrt(np.mean(diff ** 2, axis=1))
    rms_ref = np.sqrt(np.mean(a ** 2, axis=1))
    rms_ref = np.where(rms_ref == 0, np.finfo(float).eps, rms_ref)
    return 100.0 * rms_diff / rms_ref


def text_histogram(values: np.ndarray, *, n_bins: int = 12, width: int = 40) -> str:
    """Return a small ASCII bar histogram of values."""
    if len(values) == 0:
        return "(empty)"
    vmin = float(np.min(values))
    vmax = float(np.max(values))
    if vmax == vmin:
        vmax = vmin + 1e-12
    edges = np.linspace(vmin, vmax, n_bins + 1)
    counts, _ = np.histogram(values, bins=edges)
    cmax = max(int(counts.max()), 1)
    lines = []
    for k in range(n_bins):
        bar = "█" * int(round(counts[k] / cmax * width))
        lines.append(
            f"  [{edges[k]:7.3f}, {edges[k+1]:7.3f})  {counts[k]:4d}  {bar}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pscad", type=Path, default=Path("data/pscad_720.mat"))
    parser.add_argument("--emtp", type=Path, default=Path("data/emtp_720.mat"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/phase1_pscad_vs_emtp.csv"),
    )
    parser.add_argument(
        "--flag",
        type=float,
        default=2.0,
        help="RMS-diff threshold (in %%) above which a cell is flagged.",
    )
    parser.add_argument(
        "--noiseless-only",
        action="store_true",
        help="Filter to (SNR_V=Inf, SNR_I=Inf) cells only - measures the "
        "pure model-vs-model gap without noise contamination.  See the "
        "TODO Phase1 block in the docstring.",
    )
    args = parser.parse_args(argv)

    if not args.pscad.exists():
        print(f"compare_pscad_emtp: missing {args.pscad}", file=sys.stderr)
        return 2
    if not args.emtp.exists():
        print(f"compare_pscad_emtp: missing {args.emtp}", file=sys.stderr)
        return 2

    A = loadmat(str(args.pscad))
    B = loadmat(str(args.emtp))
    Va, Ia = A["V"], A["I"]
    Vb, Ib = B["V"], B["I"]
    if Va.shape != Vb.shape or Ia.shape != Ib.shape:
        print(
            f"compare_pscad_emtp: shape mismatch "
            f"V:{Va.shape}/{Vb.shape}  I:{Ia.shape}/{Ib.shape}",
            file=sys.stderr,
        )
        return 3

    grid_alpha = A["grid_alpha"].squeeze()
    grid_Rx = A["grid_Rx"].squeeze()
    grid_SNR_V = A["grid_SNR_V"].squeeze()
    grid_SNR_I = A["grid_SNR_I"].squeeze()

    if args.noiseless_only:
        mask = np.isinf(grid_SNR_V) & np.isinf(grid_SNR_I)
        Va, Ia = Va[mask], Ia[mask]
        Vb, Ib = Vb[mask], Ib[mask]
        grid_alpha = grid_alpha[mask]
        grid_Rx = grid_Rx[mask]
        grid_SNR_V = grid_SNR_V[mask]
        grid_SNR_I = grid_SNR_I[mask]
        print(
            f"compare_pscad_emtp: --noiseless-only filter "
            f"-> {len(grid_alpha)} of 720 cells retained"
        )

    n_cells = Va.shape[0]
    rms_V = per_cell_rms_pct(Va, Vb)
    rms_I = per_cell_rms_pct(Ia, Ib)
    rms_combined = np.maximum(rms_V, rms_I)
    flagged = rms_combined > args.flag

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["cell", "alpha", "Rx_ohm", "SNR_V_dB", "SNR_I_dB",
             "rms_V_pct", "rms_I_pct", "rms_max_pct", "flagged"]
        )
        for k in range(n_cells):
            w.writerow(
                [
                    k,
                    f"{float(grid_alpha[k]):.3f}",
                    f"{float(grid_Rx[k]):.1f}",
                    f"{float(grid_SNR_V[k]):.1f}",
                    f"{float(grid_SNR_I[k]):.1f}",
                    f"{rms_V[k]:.6f}",
                    f"{rms_I[k]:.6f}",
                    f"{rms_combined[k]:.6f}",
                    int(flagged[k]),
                ]
            )

    print(f"compare_pscad_emtp: cells = {n_cells}")
    print(
        "  per-cell V RMS-diff (%):  "
        f"min={rms_V.min():.4f}  median={np.median(rms_V):.4f}  "
        f"p95={np.percentile(rms_V, 95):.4f}  max={rms_V.max():.4f}"
    )
    print(
        "  per-cell I RMS-diff (%):  "
        f"min={rms_I.min():.4f}  median={np.median(rms_I):.4f}  "
        f"p95={np.percentile(rms_I, 95):.4f}  max={rms_I.max():.4f}"
    )
    print(
        "  per-cell max(V,I) (%):    "
        f"min={rms_combined.min():.4f}  median={np.median(rms_combined):.4f}  "
        f"p95={np.percentile(rms_combined, 95):.4f}  "
        f"max={rms_combined.max():.4f}"
    )
    print(f"  flagged (> {args.flag} %): {int(flagged.sum())} / {n_cells}")
    print()
    print("Histogram (combined max per cell, %):")
    print(text_histogram(rms_combined))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
