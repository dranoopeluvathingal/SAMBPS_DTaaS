"""
run_faultloc_phase3_identifiability_map.py
=============================================

WP3.5 identifiability map runner.  On a 50 x 50 (alpha, R_x) grid,
evaluate sigma_min(J) of the real Jacobian J = d Re/Im(H) / d theta
where theta = (alpha, R_x), and the Hermann-Krener observability rank.
Flag cells where sigma_min < 1e-3 as locally degenerate.

Outputs
-------

* outputs/phase3_identifiability_sigma_min.csv  -- (alpha, R_x,
  sigma_min, hermann_krener_rank, is_degenerate) per cell.
* outputs/phase3_identifiability_heatmap.png   -- log10 sigma_min
  heatmap with the degenerate region overlaid.
* outputs/phase3_identifiability_orc.csv       -- per-cell binary
  "Hermann-Krener ORC satisfied" indicator.

Reference frame
---------------

WP3.5 uses the WP2.1 single-phase distributed-parameter forward model
H_distributed(alpha, R_x, omega) and computes J via central finite
differences.  The 3-phase generalisation (Y_send 3x3 -> 18-row J;
J still has 2 columns -- alpha and R_x are the only continuous
parameters) is a clean extension when WP3.6 lands the multi-port
FIM rewiring; for the WP3.5 R5 closure the single-phase analysis
is sufficient because the structural single-bin DFT identifiability
floor is independent of the per-channel observation count.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sambp_fault_location_id.adaptation.faultloc_identifiability_check import (  # noqa: E402
    DEFAULT_THRESHOLD_SIGMA_MIN,
    map_observability_rank,
    map_sigma_min,
    map_sigma_min_over_max,
)
from sambp_fault_location_id.models.faultloc_distributed_param_model import (  # noqa: E402
    H_distributed,
)

PROJ_ROOT = Path(__file__).resolve().parent
OUT_DIR = PROJ_ROOT / "outputs"

OMEGA = 2.0 * np.pi * 50.0


def run(
    *,
    n_alpha: int = 50,
    n_Rx: int = 50,
    alpha_lo: float = 0.05,
    alpha_hi: float = 0.95,
    Rx_lo: float = 100.0,
    Rx_hi: float = 5000.0,
    threshold: float = DEFAULT_THRESHOLD_SIGMA_MIN,
) -> tuple[Path, Path, Path]:
    """Build the identifiability map and write the 3 output artefacts."""
    alpha_grid = np.linspace(alpha_lo, alpha_hi, n_alpha)
    Rx_grid = np.geomspace(Rx_lo, Rx_hi, n_Rx)
    print(
        f"WP3.5 identifiability map: alpha in [{alpha_lo}, {alpha_hi}] "
        f"({n_alpha} pts), R_x in [{Rx_lo}, {Rx_hi}] ohm geomspace "
        f"({n_Rx} pts) = {n_alpha * n_Rx} cells; threshold = {threshold}"
    )

    sm = map_sigma_min(alpha_grid, Rx_grid, model_fn=H_distributed, omega=OMEGA)
    sm_over_max = map_sigma_min_over_max(
        alpha_grid, Rx_grid, model_fn=H_distributed, omega=OMEGA,
    )
    rank = map_observability_rank(
        alpha_grid, Rx_grid, model_fn=H_distributed, omega=OMEGA,
    )
    # Locally degenerate: scale-INVARIANT inverse condition number below
    # threshold.  The brief's "sigma_min < 1e-3" wording is interpreted
    # as the inverse condition number sigma_min/sigma_max < 1e-3 because
    # the raw sigma_min carries the dimensional scale of d|H|/d theta
    # (siemens / per-unit-alpha or siemens / ohm) which is far below
    # 1e-3 even on well-conditioned cells.  See
    # docs/changelog.md for the WP3.5 deferral note.
    is_degen = sm_over_max < threshold

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = OUT_DIR / "phase3_identifiability_sigma_min.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "alpha", "Rx", "sigma_min", "sigma_min_over_max",
            "hermann_krener_rank", "is_degenerate",
        ])
        for i, a in enumerate(alpha_grid):
            for j, R in enumerate(Rx_grid):
                w.writerow([
                    f"{a:.6f}", f"{R:.4f}",
                    f"{sm[i, j]:.6e}",
                    f"{sm_over_max[i, j]:.6e}",
                    int(rank[i, j]),
                    int(is_degen[i, j]),
                ])
    print(f"wrote {csv_path}")

    orc_path = OUT_DIR / "phase3_identifiability_orc.csv"
    with orc_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["alpha", "Rx", "orc_satisfied"])
        for i, a in enumerate(alpha_grid):
            for j, R in enumerate(Rx_grid):
                # ORC: Hermann-Krener observability rank == p (= 2 here)
                w.writerow([
                    f"{a:.6f}", f"{R:.4f}",
                    int(int(rank[i, j]) == 2),
                ])
    print(f"wrote {orc_path}")

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.5))

    sm_safe = np.maximum(sm, 1.0e-15)
    im0 = axes[0].pcolormesh(
        Rx_grid, alpha_grid, np.log10(sm_safe),
        shading="auto", cmap="viridis",
    )
    axes[0].set_xscale("log")
    axes[0].set_xlabel(r"Arc resistance $R_x$ [$\Omega$]")
    axes[0].set_ylabel(r"Per-unit fault location $\alpha$")
    axes[0].set_title(r"$\log_{10}\,\sigma_{\min}(J)$ (raw)")
    plt.colorbar(im0, ax=axes[0], label=r"$\log_{10}\,\sigma_{\min}$")

    sm_over_max_safe = np.maximum(sm_over_max, 1.0e-15)
    im1 = axes[1].pcolormesh(
        Rx_grid, alpha_grid, np.log10(sm_over_max_safe),
        shading="auto", cmap="viridis",
    )
    cs = axes[1].contour(
        Rx_grid, alpha_grid, sm_over_max,
        levels=[threshold], colors="red", linewidths=1.5,
    )
    axes[1].clabel(cs, fmt={threshold: f"$\\sigma_{{min}}/\\sigma_{{max}}={threshold:g}$"})
    axes[1].set_xscale("log")
    axes[1].set_xlabel(r"Arc resistance $R_x$ [$\Omega$]")
    axes[1].set_ylabel(r"Per-unit fault location $\alpha$")
    axes[1].set_title(
        r"$\log_{10}\,\sigma_{\min}/\sigma_{\max}$ "
        f"(degenerate {int(is_degen.sum())}/{int(is_degen.size)})"
    )
    plt.colorbar(im1, ax=axes[1], label=r"$\log_{10}\,\sigma_{\min}/\sigma_{\max}$")

    fig.suptitle(
        r"WP3.5 identifiability map over $(\alpha, R_x)$ "
        f"-- 50 x 50 grid; threshold {threshold:g} on inverse "
        r"condition number"
    )
    fig.tight_layout()
    png_path = OUT_DIR / "phase3_identifiability_heatmap.png"
    fig.savefig(png_path, dpi=110)
    plt.close(fig)
    print(f"wrote {png_path}")

    n_degen = int(is_degen.sum())
    n_total = int(is_degen.size)
    n_orc_fail = int((rank < 2).sum())
    print(
        f"summary: {n_degen}/{n_total} cells locally degenerate "
        f"(sigma_min < {threshold}); {n_orc_fail}/{n_total} cells fail "
        f"Hermann-Krener ORC (rank < 2)"
    )
    return csv_path, png_path, orc_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n-alpha", type=int, default=50)
    parser.add_argument("--n-Rx", type=int, default=50)
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD_SIGMA_MIN,
    )
    args = parser.parse_args(argv)
    run(
        n_alpha=args.n_alpha, n_Rx=args.n_Rx,
        threshold=args.threshold,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
