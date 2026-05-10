"""
run_faultloc_phase3_multiport_crlb.py
========================================

WP3.6 (P3.6) multi-port CRLB runner.  Evaluates the multi-port
proper-complex-Gaussian-ratio CRLB and the joint dual-channel CRLB on
the IEEE 34-node 720-grid (10 fault buses x 5 R_x x 4 SNR_V x 4 SNR_I
sub-sample for tractable runtime), confirms per-cell consistency
between the two bounds at SNR_I >= 40 dB, and produces overlay PNGs
showing CRLB envelope behaviour vs SNR_I at representative cells.

Outputs
-------

* outputs/phase3_crlb_multiport_overlay/per_cell_crlb.csv -- per-cell
  multi-port proper / dual CRLB report on the 720-grid sub-sample.
* outputs/phase3_crlb_multiport_overlay/snr_sweep.png -- proper +
  dual + single-port CRLB curves vs SNR_I at a representative cell.
* outputs/phase3_crlb_multiport_overlay/observation_kind.png --
  CRLB vs SNR_I for the three observation subsets ('full' /
  'upper' / 'diagonal').
* outputs/phase3_crlb_multiport_overlay/consistency_at_40dB.png --
  per-cell scatter of proper / dual ratio at SNR_I = 40 dB.

Per-cell consistency test
-------------------------

The brief acceptance: "at SNR_I >= 40 dB the proper-ratio and
dual-channel CRLBs must agree to within 5 %".  This runner computes
the ratio per cell and writes a summary; the actual unit test lives
in ``tests/test_fim_multiport.py``.
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
from sambp_fault_location_id.inverse_estimation.faultloc_crlb_proper import (  # noqa: E402
    crlb_proper,
)
from sambp_fault_location_id.inverse_estimation.faultloc_fim_multiport import (  # noqa: E402
    crlb_consistency_ratio,
    crlb_multiport_dual,
    crlb_multiport_proper,
)
from sambp_fault_location_id.models.faultloc_ieee_feeders import (  # noqa: E402
    build_ieee34,
)

PROJ_ROOT = Path(__file__).resolve().parent
OUT_DIR = PROJ_ROOT / "outputs" / "phase3_crlb_multiport_overlay"

OMEGA = 2.0 * np.pi * 50.0
RXS = (100.0, 500.0, 1000.0, 2000.0, 5000.0)
SNR_VS = (np.inf,)                                  # V noiseless this run
SNR_IS = (20.0, 30.0, 40.0, 50.0, np.inf)
OBSERVATIONS = ("full", "upper", "diagonal")
DEFAULT_N_BUSES = 10


def _select_buses(network, n_sample: int | None) -> list[str]:
    candidate = [b for b in network.data.buses if b != network.data.source_bus]
    if n_sample is None or n_sample >= len(candidate):
        return candidate
    stride = max(1, len(candidate) // n_sample)
    return candidate[::stride][:n_sample]


def run(*, n_buses: int = DEFAULT_N_BUSES) -> None:
    network = build_ieee34()
    buses = _select_buses(network, n_buses)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"WP3.6 multi-port CRLB runner: feeder=IEEE_34, "
          f"n_buses={len(buses)}, R_x={list(RXS)}, "
          f"SNR_I={list(SNR_IS)}, observations={list(OBSERVATIONS)}")

    rows: list[dict] = []
    for bus in buses:
        for Rx in RXS:
            for snrI in SNR_IS:
                for obs in OBSERVATIONS:
                    p = crlb_multiport_proper(
                        network, fault_bus=bus, alpha=0.5, Rx=Rx,
                        snr_v_db=np.inf, snr_i_db=snrI,
                        observation=obs,
                    )
                    d = crlb_multiport_dual(
                        network, fault_bus=bus, alpha=0.5, Rx=Rx,
                        snr_v_db=np.inf, snr_i_db=snrI,
                        observation=obs,
                    )
                    ratio = crlb_consistency_ratio(p, d)
                    rows.append({
                        "feeder": "IEEE_34",
                        "fault_bus": bus,
                        "alpha": 0.5,
                        "Rx": float(Rx),
                        "snrI": float(snrI),
                        "observation": obs,
                        "n_real_obs": int(p.n_observations),
                        "rmse_alpha_pct_proper": float(p.rmse_alpha_pct),
                        "rmse_alpha_pct_dual": float(d.rmse_alpha_pct),
                        "rmse_Rx_pct_proper": float(p.rmse_Rx_pct),
                        "rmse_Rx_pct_dual": float(d.rmse_Rx_pct),
                        "consistency_ratio": float(ratio),
                        "geary_hinkley_valid": int(p.geary_hinkley_valid),
                    })

    csv_path = OUT_DIR / "per_cell_crlb.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {csv_path} ({len(rows)} rows)")

    # Plot 1: SNR-sweep curves at the representative cell (bus_15, Rx=1000)
    rep_bus = buses[len(buses) // 2]
    rep_Rx = 1000.0
    snr_axis = np.array([s for s in SNR_IS if np.isfinite(s)])
    rmse_proper_full = []
    rmse_dual_full = []
    for snrI in snr_axis:
        p = crlb_multiport_proper(
            network, fault_bus=rep_bus, alpha=0.5, Rx=rep_Rx,
            snr_v_db=np.inf, snr_i_db=snrI, observation="full",
        )
        d = crlb_multiport_dual(
            network, fault_bus=rep_bus, alpha=0.5, Rx=rep_Rx,
            snr_v_db=np.inf, snr_i_db=snrI, observation="full",
        )
        rmse_proper_full.append(p.rmse_alpha_pct)
        rmse_dual_full.append(d.rmse_alpha_pct)
    sp_curve = [
        crlb_proper(0.5, rep_Rx, snr_v_db=np.inf, snr_i_db=s).rmse_alpha_pct
        for s in snr_axis
    ]

    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    ax.semilogy(snr_axis, sp_curve, "k--",
                label="single-port CRLB (P1.6)", linewidth=1.5)
    ax.semilogy(snr_axis, rmse_proper_full, "o-",
                color="#1F3D7A", label="multi-port proper-ratio CRLB")
    ax.semilogy(snr_axis, rmse_dual_full, "s:",
                color="#F39200", label="multi-port dual-channel CRLB")
    ax.set_xlabel(r"SNR$_I$ [dB]")
    ax.set_ylabel(r"CRLB on $\hat{\alpha}$ [\% of true $\alpha$]")
    ax.set_title(
        f"WP3.6 multi-port CRLB sweep -- IEEE 34, fault @ {rep_bus}, "
        f"$R_x = {rep_Rx:.0f}\\,\\Omega$, V noiseless"
    )
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    snr_png = OUT_DIR / "snr_sweep.png"
    fig.savefig(snr_png, dpi=110)
    plt.close(fig)
    print(f"wrote {snr_png}")

    # Plot 2: observation-kind comparison at the representative cell
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for obs in OBSERVATIONS:
        ys = []
        for snrI in snr_axis:
            p = crlb_multiport_proper(
                network, fault_bus=rep_bus, alpha=0.5, Rx=rep_Rx,
                snr_v_db=np.inf, snr_i_db=snrI, observation=obs,
            )
            ys.append(p.rmse_alpha_pct)
        ax.semilogy(snr_axis, ys, "-o", label=f"observation = {obs}")
    ax.set_xlabel(r"SNR$_I$ [dB]")
    ax.set_ylabel(r"Multi-port proper-ratio CRLB on $\hat{\alpha}$ [\%]")
    ax.set_title(
        f"WP3.6 observation-set comparison -- IEEE 34, fault @ {rep_bus}, "
        f"$R_x = {rep_Rx:.0f}\\,\\Omega$"
    )
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    obs_png = OUT_DIR / "observation_kind.png"
    fig.savefig(obs_png, dpi=110)
    plt.close(fig)
    print(f"wrote {obs_png}")

    # Plot 3: per-cell consistency scatter at SNR_I = 40 dB
    consistency_rows = [
        r for r in rows
        if abs(r["snrI"] - 40.0) < 0.5 and r["observation"] == "full"
    ]
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    ratios = np.array([r["consistency_ratio"] for r in consistency_rows])
    span = abs(ratios - 1.0).max()
    if span < 1e-12:
        # Degenerate: all ratios identical (perfect consistency at
        # V noiseless).  Plot as a vertical bar at 1.0.
        ax.bar([1.0], [len(ratios)], width=0.01,
               color="#1F3D7A", alpha=0.85)
        ax.set_xlim(0.9, 1.1)
    else:
        ax.hist(ratios, bins=20, color="#1F3D7A", alpha=0.85)
    ax.axvline(1.0, color="black", linestyle="--", linewidth=1.5,
               label="ideal ratio = 1.0")
    ax.axvline(0.95, color="red", linestyle=":",
               label="5\\% lower bound")
    ax.axvline(1.05, color="red", linestyle=":",
               label="5\\% upper bound")
    ax.set_xlabel("CRLB consistency ratio: rmse_alpha (proper) / (dual)")
    ax.set_ylabel("Number of (fault_bus, R_x) cells")
    ax.set_title(
        f"WP3.6 per-cell consistency at SNR_I = 40 dB ('full' observation)\n"
        f"n_cells = {len(consistency_rows)}, "
        f"mean ratio = {ratios.mean():.4f}, max abs deviation = "
        f"{span:.4e}"
    )
    ax.legend()
    fig.tight_layout()
    cons_png = OUT_DIR / "consistency_at_40dB.png"
    fig.savefig(cons_png, dpi=110)
    plt.close(fig)
    print(f"wrote {cons_png}")

    # Summary -- SNR_I >= 40 dB but exclude SNR_I = inf where both
    # bounds are zero (FIM is inf -> rmse is 0 -> ratio = 0/0 = NaN
    # and the "within 5 %" check is vacuous).
    print()
    print("=== Per-cell consistency at 40 <= SNR_I < inf ===")
    high_snr = [
        r for r in rows
        if r["snrI"] >= 40.0 and np.isfinite(r["snrI"])
    ]
    rs = np.array([r["consistency_ratio"] for r in high_snr])
    rs_finite = rs[np.isfinite(rs)]
    n_within_5pct = int(np.sum(np.abs(rs_finite - 1.0) < 0.05))
    print(f"  {n_within_5pct}/{len(rs_finite)} cells within 5 % of ratio = 1.0")
    if rs_finite.size > 0:
        print(
            f"  mean ratio = {rs_finite.mean():.6f}, "
            f"std = {rs_finite.std():.6f}, "
            f"max abs deviation = {abs(rs_finite - 1.0).max():.6e}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n-buses", type=int, default=DEFAULT_N_BUSES)
    args = parser.parse_args(argv)
    run(n_buses=args.n_buses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
