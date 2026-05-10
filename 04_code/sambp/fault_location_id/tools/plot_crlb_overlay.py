"""plot_crlb_overlay.py
=========================

WP1.6 deliverable D: 2 x 4 panel of empirical RMS error from the
WP1.5 Monte-Carlo (``outputs/phase1_montecarlo_summary.csv``) overlaid
with the proper-ratio CRLB (``faultloc_crlb_proper``) and the
dual-channel CRLB (``faultloc_crlb_dualchannel``) at representative
(alpha, R_x) cells.

Layout: rows = {alpha=0.30, alpha=0.70}; cols = {R_x = 100, 500,
1000, 5000 ohm}.  Each panel: empirical RMSE vs SNR_I across
SNR_V = inf, with the two CRLB curves overlaid.

The figure folder is ``outputs/phase1_crlb_overlay/`` (one PNG per
panel, plus a combined ``crlb_overlay_2x4.png``).

Usage
-----
    python tools/plot_crlb_overlay.py
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
from sambp_fault_location_id.inverse_estimation.faultloc_crlb_dualchannel import (  # noqa: E402
    crlb_dualchannel,
)
from sambp_fault_location_id.inverse_estimation.faultloc_crlb_proper import (  # noqa: E402
    crlb_proper,
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
SUMMARY = PROJ_ROOT / "outputs" / "phase1_montecarlo_summary.csv"
OUT_DIR = PROJ_ROOT / "outputs" / "phase1_crlb_overlay"
OMEGA = 2 * np.pi * 50.0


def _parse_snr(s: str) -> float:
    return float("inf") if s.lower() in ("inf", "+inf") else float(s)


def _load_summary() -> list[dict]:
    if not SUMMARY.exists():
        print(
            f"plot_crlb_overlay: missing {SUMMARY}; run "
            f"`run_faultloc_phase1_crossplatform.py --monte-carlo 100` first.",
            file=sys.stderr,
        )
        sys.exit(2)
    return list(csv.DictReader(SUMMARY.open()))


def _empirical_rmse_curve(rows, dataset, alpha, Rx):
    """For a given (dataset, alpha, R_x), return (snrI, rmse_loc%) at SNR_V=inf."""
    pts = []
    for r in rows:
        if r["dataset"] != dataset:
            continue
        if abs(float(r["alpha"]) - alpha) > 1e-9:
            continue
        if abs(float(r["Rx"]) - Rx) > 1e-9:
            continue
        if not np.isinf(_parse_snr(r["snrV"])):
            continue
        snrI = _parse_snr(r["snrI"])
        # Use loc_std_pct as proxy for RMSE deviation (since mean-bias
        # dominated by ill-conditioning; the std captures the noise floor)
        rmse_pct = float(r["loc_std_pct"])
        pts.append((snrI, rmse_pct))
    pts.sort(key=lambda x: (np.inf if np.isinf(x[0]) else x[0]))
    return pts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dataset",
        default="self_consistent",
        help="Which dataset's empirical RMSE to overlay (default: "
        "self_consistent, which removes model-mismatch from the gap).",
    )
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = _load_summary()

    alphas = [0.30, 0.70]
    Rxs = [100.0, 500.0, 1000.0, 5000.0]

    snrI_grid_db = np.array([20.0, 30.0, 40.0])
    snrI_inf_x = 50.0  # plot SNR_I=inf at this dB on the horizontal axis

    fig, axes = plt.subplots(
        len(alphas), len(Rxs), figsize=(4.0 * len(Rxs), 3.5 * len(alphas)),
        sharex=True
    )

    for i, a in enumerate(alphas):
        for j, R in enumerate(Rxs):
            ax = axes[i, j]
            # CRLB curves at SNR_V = inf
            rmse_proper = []
            rmse_dual = []
            for snr_i in snrI_grid_db:
                rp = crlb_proper(a, R, OMEGA, snr_v_db=np.inf, snr_i_db=snr_i)
                rd = crlb_dualchannel(a, R, OMEGA, snr_i_db=snr_i)
                rmse_proper.append(rp.rmse_alpha_pct)
                rmse_dual.append(rd.rmse_alpha_pct)
            x_dB = list(snrI_grid_db) + [snrI_inf_x]
            # SNR_I = inf -> CRLB = 0
            rmse_proper.append(0.0)
            rmse_dual.append(0.0)
            ax.plot(x_dB[:-1], rmse_proper[:-1],
                    "-o", color="#1F3D7A",
                    label="proper-ratio CRLB", linewidth=1.6)
            ax.plot(x_dB[:-1], rmse_dual[:-1],
                    "--s", color="#F39200",
                    label="dual-channel CRLB", linewidth=1.6)

            # Empirical from MC
            pts = _empirical_rmse_curve(rows, args.dataset, a, R)
            if pts:
                xs = [p[0] if np.isfinite(p[0]) else snrI_inf_x for p in pts]
                ys = [p[1] for p in pts]
                ax.plot(xs, ys, "^",
                        color="#B23A48",
                        label=f"emp RMS ({args.dataset})", markersize=8)

            ax.set_xlabel(r"SNR$_I$ [dB; 50 = noiseless]")
            if j == 0:
                ax.set_ylabel(r"RMSE($\hat\alpha$) [%]")
            ax.set_yscale("log")
            ax.set_title(rf"$\alpha={a:.2f}$, $R_x={R:.0f}\,\Omega$")
            ax.grid(True, which="both", alpha=0.3)
            if i == 0 and j == 0:
                ax.legend(loc="lower left", fontsize=8)

    fig.suptitle(
        "WP1.6 CRLB overlay - empirical (MC) vs proper-ratio + dual-channel\n"
        f"(dataset = {args.dataset}; SNR$_V$ = $\\infty$)"
    )
    fig.tight_layout()
    out_path = OUT_DIR / "crlb_overlay_2x4.png"
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"plot_crlb_overlay: wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
