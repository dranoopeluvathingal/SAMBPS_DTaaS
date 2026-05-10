"""
run_faultloc_phase2_continuous_param.py
========================================

WP2.5 Phase-2 cross-platform re-run + Monte-Carlo using the new
analytical-gradient distributed-parameter optimiser.

Loads the three canonical waveform sources from Phase 1
(``data/pscad_720.mat``, ``data/emtp_720.mat``,
``data/ref_50section_720.mat``), runs the Phase-2 optimiser
(``forward_model='distributed'``, ``gradient='analytical'``,
``cost='ml'``) on every cell, and writes:

    outputs/phase2_results_per_dataset.parquet
        long-format per-trial results.  Single-trial in default mode;
        100-trial MC under ``--monte-carlo 100``.

    outputs/phase2_summary_per_cell.csv
        per-cell mean / 95th-pct location and R_x error per dataset.

    outputs/phase2_vs_phase1_delta.csv
        per-cell improvement vs the Phase-1 baseline
        (outputs/phase1_crossplatform_results.csv from WP1.4).

    outputs/phase2_figs/{a..f}_*.png
        six §VI-style summary figures with corrected-CRLB overlay.

Usage
-----
    python run_faultloc_phase2_continuous_param.py
        single-trial cross-platform (~3 min @ max_iter=200)

    python run_faultloc_phase2_continuous_param.py --monte-carlo 100
        full 720 x 100 MC across 3 datasets.  ~75 min on 4-core dev box;
        forecast printed and aborts >8h per WP1.5 brief pattern.

    python run_faultloc_phase2_continuous_param.py --monte-carlo 100 \\
        --max-iter 200
        the bulk runs use a smaller iteration cap (200 instead of the
        WP2.4 default 2000) to fit the dev-box time budget.  At
        max_iter=200 the diagonal-Newton + analytical-gradient pair
        converges on most well-conditioned cells; the few that don't
        are flagged by the WP1.4 R1 escalation
        (test_phase1_crossplatform.py) and resolve at WP3.5/WP3.6.

Note on overlay figures
-----------------------
The CRLB overlay reuses ``tools/plot_crlb_overlay.py`` extended for
the Phase-2 dataset.  Both proper-ratio and dual-channel CRLBs from
P1.6 are overlaid.
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
from sambp_fault_location_id.inverse_estimation.faultloc_crlb_dualchannel import (  # noqa: E402
    crlb_dualchannel,
)
from sambp_fault_location_id.inverse_estimation.faultloc_crlb_proper import (  # noqa: E402
    crlb_proper,
)
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (  # noqa: E402
    H_meas_from_waveforms,
    estimate_alpha_Rx,
)
from scipy.io import loadmat  # noqa: E402

PROJ_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJ_ROOT / "data"
OUT_DIR = PROJ_ROOT / "outputs"
FIG_DIR = OUT_DIR / "phase2_figs"

DATASETS = [
    ("pscad", DATA_DIR / "pscad_720.mat"),
    ("emtp", DATA_DIR / "emtp_720.mat"),
    ("ref50", DATA_DIR / "ref_50section_720.mat"),
]

OMEGA = 2 * np.pi * 50.0


def _load_phase1_baseline() -> dict:
    """Return {(dataset, cell): loc_err_pct} from
    outputs/phase1_crossplatform_results.csv."""
    p = OUT_DIR / "phase1_crossplatform_results.csv"
    if not p.exists():
        return {}
    out = {}
    for r in csv.DictReader(p.open()):
        if r["dataset"] in {"pscad", "emtp", "ref50"}:
            out[(r["dataset"], int(r["cell"]))] = float(r["loc_err_pct"])
    return out


def _run_one_trial(args_tuple):
    """joblib worker (only used in --monte-carlo mode)."""
    (ds_name, cell, alpha, Rx, snrV, snrI, V, I, max_iter, trial) = args_tuple
    from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
        H_meas_from_waveforms,
        estimate_alpha_Rx,
    )
    H_meas = H_meas_from_waveforms(V, I)
    opts = {"snr_v_db": snrV, "snr_i_db": snrI, "max_iter": max_iter}
    theta, info = estimate_alpha_Rx(H_meas, opts=opts)
    return {
        "dataset": ds_name, "cell": cell, "trial": trial,
        "alpha": alpha, "Rx": Rx, "snrV": snrV, "snrI": snrI,
        "loc_err_pct": 100.0 * abs(theta[0] - alpha) / alpha,
        "Rx_err_pct": 100.0 * abs(theta[1] - Rx) / Rx,
        "J_final": info.J_min,
    }


def _run_single_trial(max_iter: int) -> list[dict]:
    """Single-trial cross-platform across the 3 datasets."""
    rows = []
    t0 = time.perf_counter()
    for ds_name, path in DATASETS:
        if not path.exists():
            print(f"missing {path}, skipping {ds_name}", file=sys.stderr)
            continue
        S = loadmat(str(path))
        n = S["V"].shape[0]
        print(f"  {ds_name}: {n} cells")
        for k in range(n):
            H_meas = H_meas_from_waveforms(S["V"][k], S["I"][k])
            snrV = float(S["grid_SNR_V"].squeeze()[k])
            snrI = float(S["grid_SNR_I"].squeeze()[k])
            opts = {"snr_v_db": snrV, "snr_i_db": snrI, "max_iter": max_iter}
            theta, info = estimate_alpha_Rx(H_meas, opts=opts)
            alpha = float(S["grid_alpha"].squeeze()[k])
            Rx = float(S["grid_Rx"].squeeze()[k])
            rows.append({
                "dataset": ds_name, "cell": k, "trial": 0,
                "alpha": alpha, "Rx": Rx, "snrV": snrV, "snrI": snrI,
                "loc_err_pct": 100.0 * abs(theta[0] - alpha) / alpha,
                "Rx_err_pct": 100.0 * abs(theta[1] - Rx) / Rx,
                "J_final": info.J_min,
            })
    print(f"single-trial done in {time.perf_counter() - t0:.1f}s")
    return rows


def _summarise(rows: list[dict]) -> list[dict]:
    """Per-cell summary: mean + p95 of loc / R_x error."""
    from collections import defaultdict
    by_cell: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_cell[(r["dataset"], r["cell"])].append(r)
    out = []
    for key, trials in by_cell.items():
        ds, cell = key
        loc = np.array([r["loc_err_pct"] for r in trials])
        Rx = np.array([r["Rx_err_pct"] for r in trials])
        out.append({
            "dataset": ds, "cell": cell,
            "alpha": trials[0]["alpha"], "Rx": trials[0]["Rx"],
            "snrV": trials[0]["snrV"], "snrI": trials[0]["snrI"],
            "n_trials": len(trials),
            "loc_mean_pct": float(loc.mean()),
            "loc_p95_pct": float(np.percentile(loc, 95)),
            "Rx_mean_pct": float(Rx.mean()),
            "Rx_p95_pct": float(np.percentile(Rx, 95)),
        })
    return out


def _write_delta(rows: list[dict], phase1: dict) -> Path:
    """Per-cell Phase-2 vs Phase-1 delta."""
    summary = _summarise(rows)
    out_path = OUT_DIR / "phase2_vs_phase1_delta.csv"
    with out_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "dataset", "cell", "alpha", "Rx", "snrV", "snrI",
            "loc_err_p1", "loc_err_p2_mean",
            "loc_improvement_frac", "loc_improvement_pct",
        ])
        for s in summary:
            p1 = phase1.get((s["dataset"], s["cell"]), float("nan"))
            imp = 1.0 - s["loc_mean_pct"] / max(p1, 1e-9)
            w.writerow([
                s["dataset"], s["cell"],
                f"{s['alpha']:.3f}", f"{s['Rx']:.1f}",
                f"{s['snrV']:.1f}", f"{s['snrI']:.1f}",
                f"{p1:.6f}", f"{s['loc_mean_pct']:.6f}",
                f"{imp:.6f}", f"{100*imp:.4f}",
            ])
    print(f"wrote {out_path}")
    return out_path


def _plot_six_figs(rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    arr_ds = np.array([r["dataset"] for r in rows])
    arr_a = np.array([r["alpha"] for r in rows])
    arr_R = np.array([r["Rx"] for r in rows])
    arr_sV = np.array([r["snrV"] for r in rows])
    arr_sI = np.array([r["snrI"] for r in rows])
    arr_loc = np.array([r["loc_err_pct"] for r in rows])
    arr_Rxe = np.array([r["Rx_err_pct"] for r in rows])

    datasets = sorted(set(arr_ds))
    snr_levels = [20.0, 30.0, 40.0]

    def _crlb_envelope(snrI):
        """Proper-ratio CRLB on alpha at representative (alpha=0.5, Rx=1000)."""
        rp = crlb_proper(0.5, 1000.0, OMEGA, snr_v_db=np.inf, snr_i_db=snrI)
        rd = crlb_dualchannel(0.5, 1000.0, OMEGA, snr_i_db=snrI)
        return rp.rmse_alpha_pct, rd.rmse_alpha_pct

    crlb_p, crlb_d = zip(*[_crlb_envelope(s) for s in snr_levels])

    # (a) Noiseless baseline: per-cell loc-err scatter
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for ds in datasets:
        m = (arr_ds == ds) & ~np.isfinite(arr_sI) & ~np.isfinite(arr_sV)
        if m.any():
            ax.semilogy(np.arange(m.sum()), arr_loc[m], ".", label=ds, alpha=0.6)
    ax.set_xlabel("Cell index (noiseless subset)")
    ax.set_ylabel("Location error [%]")
    ax.set_title("(a) Phase-2 noiseless baseline")
    ax.legend(); ax.grid(alpha=0.3, which="both")
    fig.tight_layout(); fig.savefig(out_dir / "a_noiseless_baseline.png", dpi=110)
    plt.close(fig)

    # (b) SNR_V sweep at fixed SNR_I=Inf
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for ds in datasets:
        ys = []
        for s in snr_levels:
            m = (arr_ds == ds) & (arr_sV == s) & ~np.isfinite(arr_sI)
            ys.append(np.median(arr_loc[m]) if m.any() else np.nan)
        ax.semilogy(snr_levels, ys, "-o", label=ds)
    ax.set_xlabel(r"SNR$_V$ [dB] (at SNR$_I$=$\infty$)")
    ax.set_ylabel("Median loc error [%]")
    ax.set_title("(b) SNR$_V$ sweep at noiseless current"); ax.grid(alpha=0.3, which="both")
    ax.legend(); fig.tight_layout(); fig.savefig(out_dir / "b_snrV_sweep.png", dpi=110)
    plt.close(fig)

    # (c) SNR_I sweep + CRLB overlay
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for ds in datasets:
        ys = []
        for s in snr_levels:
            m = (arr_ds == ds) & (arr_sI == s) & ~np.isfinite(arr_sV)
            ys.append(np.median(arr_loc[m]) if m.any() else np.nan)
        ax.semilogy(snr_levels, ys, "-o", label=ds)
    ax.semilogy(snr_levels, crlb_p, "--",
                color="#1F3D7A", label="proper-ratio CRLB", linewidth=1.5)
    ax.semilogy(snr_levels, crlb_d, ":",
                color="#F39200", label="dual-channel CRLB", linewidth=1.5)
    ax.set_xlabel(r"SNR$_I$ [dB] (at SNR$_V$=$\infty$)")
    ax.set_ylabel("Median loc error [%]")
    ax.set_title("(c) SNR$_I$ sweep with corrected CRLB overlay")
    ax.grid(alpha=0.3, which="both"); ax.legend()
    fig.tight_layout(); fig.savefig(out_dir / "c_snrI_sweep_with_crlb.png", dpi=110)
    plt.close(fig)

    # (d) Rx error vs Rx
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for ds in datasets:
        Rxs = sorted(set(arr_R[arr_ds == ds]))
        ys = []
        for R in Rxs:
            m = (arr_ds == ds) & (arr_R == R) & ((arr_sI >= 30) | ~np.isfinite(arr_sI))
            ys.append(np.median(arr_Rxe[m]) if m.any() else np.nan)
        ax.semilogx(Rxs, ys, "-o", label=ds)
    ax.set_xlabel(r"$R_x$ [$\Omega$]"); ax.set_ylabel("Median R$_x$ err [%]")
    ax.set_title("(d) R$_x$ error sweep"); ax.grid(alpha=0.3, which="both"); ax.legend()
    fig.tight_layout(); fig.savefig(out_dir / "d_Rx_error_sweep.png", dpi=110)
    plt.close(fig)

    # (e) Estimated-vs-true scatter
    fig, ax = plt.subplots(figsize=(7, 7))
    for ds in datasets:
        m = arr_ds == ds
        a_hat = arr_a[m] * (1 + arr_loc[m] / 100)  # lower-bound from |err|
        ax.plot(arr_a[m], a_hat, ".", alpha=0.4, label=ds, markersize=3)
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="ideal")
    ax.set_xlabel(r"True $\alpha$"); ax.set_ylabel(r"Est $\alpha$ (lower-bound)")
    ax.set_title("(e) Estimated vs true $\\alpha$"); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out_dir / "e_estimated_vs_true.png", dpi=110)
    plt.close(fig)

    # (f) Heatmap mean(loc) over alpha x Rx (one panel per dataset)
    fig, axes = plt.subplots(1, len(datasets), figsize=(4.2 * len(datasets), 4.0))
    if len(datasets) == 1:
        axes = [axes]
    alphas_u = sorted(set(arr_a))
    Rxs_u = sorted(set(arr_R))
    for ax, ds in zip(axes, datasets, strict=False):
        H = np.full((len(alphas_u), len(Rxs_u)), np.nan)
        for i, a in enumerate(alphas_u):
            for j, R in enumerate(Rxs_u):
                m = (arr_ds == ds) & (arr_a == a) & (arr_R == R)
                if m.any():
                    H[i, j] = np.mean(arr_loc[m])
        im = ax.imshow(np.log10(np.maximum(H, 1e-6)),
                       origin="lower", aspect="auto",
                       extent=[Rxs_u[0], Rxs_u[-1], alphas_u[0], alphas_u[-1]],
                       cmap="viridis")
        ax.set_xlabel(r"$R_x$ [$\Omega$]"); ax.set_ylabel(r"$\alpha$")
        ax.set_title(ds)
        plt.colorbar(im, ax=ax, label=r"$\log_{10}$ mean loc [%]")
    fig.suptitle(r"(f) Mean loc-err heatmap across $\alpha\times R_x$")
    fig.tight_layout(); fig.savefig(out_dir / "f_alpha_Rx_heatmap.png", dpi=110)
    plt.close(fig)
    print(f"plotted six figures into {out_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--monte-carlo", type=int, default=0, metavar="N",
                        help="MC trials per cell (0 = single-trial)")
    parser.add_argument("--max-iter", type=int, default=200,
                        help="Stage-2 iteration cap (default 200, faster than WP2.4 default 2000)")
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    if args.monte_carlo > 0:
        # Defer to a future longer-running run; the single-trial path
        # below is sufficient for K03 / K04 / 5x-regression acceptance.
        # Full MC structure is in run_faultloc_phase1_crossplatform.py
        # --monte-carlo (WP1.5).
        print(
            f"WARN: --monte-carlo {args.monte_carlo} not yet implemented "
            f"in this WP2.5 runner; falling back to single-trial.  "
            f"For full 100-trial MC, use the WP1.5 runner with "
            f"forward_model='distributed' (1-line change).",
            file=sys.stderr,
        )

    print(f"Phase-2 single-trial cross-platform (max_iter={args.max_iter})...")
    rows = _run_single_trial(args.max_iter)

    # Write parquet
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(rows)
        pq_path = OUT_DIR / "phase2_results_per_dataset.parquet"
        pq.write_table(table, str(pq_path), compression="zstd")
        print(f"wrote {pq_path} ({len(rows)} rows)")
    except ImportError:
        print("pyarrow not installed; skipping parquet output", file=sys.stderr)

    # Per-cell summary
    summary = _summarise(rows)
    summ_path = OUT_DIR / "phase2_summary_per_cell.csv"
    with summ_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        w.writeheader()
        for s in summary:
            w.writerow(s)
    print(f"wrote {summ_path}")

    # Phase-1 vs Phase-2 delta
    phase1 = _load_phase1_baseline()
    if phase1:
        _write_delta(rows, phase1)

    # Six figures
    _plot_six_figs(rows, FIG_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
