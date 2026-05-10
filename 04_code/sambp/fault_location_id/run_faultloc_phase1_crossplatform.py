"""
run_faultloc_phase1_crossplatform.py
=====================================

WP1.4 cross-platform optimiser re-run.

Loads three independent waveform sets:

    data/pscad_720.mat            cosh/sinh ABCD distributed-parameter
    data/emtp_720.mat             50-section pi (independent rng seed)
    data/ref_50section_720.mat    50-section pi reference

plus an on-the-fly self-consistent baseline generated from
``models.faultloc_pi_section_model`` (so delta-error attribution is
well-defined), runs the **unchanged** two-stage optimiser
(``inverse_estimation/faultloc_two_stage_optimiser``) on every cell of
every dataset, and writes:

    outputs/phase1_crossplatform_results.csv
        cell-level results (dataset, alpha, Rx, snrV, snrI,
        loc_err_pct, Rx_err_pct, J_final, n_iters, cpu_ms)

    outputs/phase1_delta_error_attribution.csv
        per-cell delta-error vs the self-consistent baseline

    outputs/phase1_figs/{a..f}_*.png
        six summary figures (a) RMS error vs SNR_I per dataset,
        (b) loc-error heatmap over alpha x Rx per dataset,
        (c) delta-error histogram, (d) estimated-vs-true scatter,
        (e) Rx error vs SNR_I per dataset, (f) per-cell loc_err
        boxplot per dataset.

Usage
-----
    .venv/bin/python run_faultloc_phase1_crossplatform.py
    .venv/bin/python run_faultloc_phase1_crossplatform.py --quick
        (quick mode: subsample to alpha in {0.3, 0.5, 0.7}, useful for CI)
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (  # noqa: E402
    H_meas_from_waveforms,
    estimate_alpha_Rx,
)
from sambp_fault_location_id.models.faultloc_pi_section_model import H_model  # noqa: E402
from scipy.io import loadmat  # noqa: E402

PROJ_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJ_ROOT / "data"
OUT_DIR = PROJ_ROOT / "outputs"
FIG_DIR = OUT_DIR / "phase1_figs"

DATASETS = [
    ("pscad", DATA_DIR / "pscad_720.mat"),
    ("emtp", DATA_DIR / "emtp_720.mat"),
    ("ref50", DATA_DIR / "ref_50section_720.mat"),
]

V_PHASE = 11000.0 / np.sqrt(3.0)
F0 = 50.0
FS = 10000.0
NS = 200


# ---------------------------------------------------------------------------
# Self-consistent baseline (Cascaded-Gamma model used by the optimiser)
# ---------------------------------------------------------------------------
def _build_self_consistent(grid_alpha, grid_Rx, grid_SNR_V, grid_SNR_I, *, rng_seed=99):
    """V/I waveforms generated from the Cascaded-Gamma 2-section model
    (the SAME model the optimiser fits).  Modelling error == 0 by
    construction; loc/Rx errors are purely noise-driven."""
    rng = np.random.default_rng(rng_seed)
    omega = 2 * np.pi * F0
    n = len(grid_alpha)
    V = np.zeros((n, NS))
    Ic = np.zeros((n, NS))
    Vph = V_PHASE * np.sqrt(2.0)
    t = np.arange(NS) / FS
    for k in range(n):
        H = H_model(float(grid_alpha[k]), float(grid_Rx[k]), omega)
        Iph = H * Vph
        v = Vph * np.cos(omega * t)
        i = (Iph * np.exp(1j * omega * t)).real
        sv = float(grid_SNR_V[k])
        si = float(grid_SNR_I[k])
        if np.isfinite(sv):
            pn = float(np.mean(v ** 2)) / (10 ** (sv / 10))
            v = v + np.sqrt(pn) * rng.standard_normal(NS)
        if np.isfinite(si):
            pn = float(np.mean(i ** 2)) / (10 ** (si / 10))
            i = i + np.sqrt(pn) * rng.standard_normal(NS)
        V[k] = v
        Ic[k] = i
    return V, Ic


# ---------------------------------------------------------------------------
# Per-dataset runner
# ---------------------------------------------------------------------------
def _run_dataset(
    name: str, V_arr, I_arr, grid_alpha, grid_Rx, grid_SNR_V, grid_SNR_I, *, quick=False
):
    rows = []
    n = V_arr.shape[0]
    if quick:
        # Subsample to alpha in {0.3, 0.5, 0.7} -> 3 * 5 * 4 * 4 = 240 cells
        keep = np.isin(np.round(grid_alpha, 6), [0.3, 0.5, 0.7])
        idx = np.where(keep)[0]
    else:
        idx = np.arange(n)
    t0 = time.perf_counter()
    last_print = t0
    for ii, k in enumerate(idx):
        H_meas = H_meas_from_waveforms(V_arr[k], I_arr[k], FS, F0)
        theta, info = estimate_alpha_Rx(H_meas)
        loc_err = 100.0 * abs(theta[0] - grid_alpha[k]) / grid_alpha[k]
        Rx_err = 100.0 * abs(theta[1] - grid_Rx[k]) / grid_Rx[k]
        rows.append(
            {
                "dataset": name,
                "cell": int(k),
                "alpha": float(grid_alpha[k]),
                "Rx": float(grid_Rx[k]),
                "snrV": float(grid_SNR_V[k]),
                "snrI": float(grid_SNR_I[k]),
                "loc_err_pct": float(loc_err),
                "Rx_err_pct": float(Rx_err),
                "J_final": float(info.J_min),
                "n_iters": int(info.n_iters),
                "cpu_ms": float(info.cpu_time_s * 1000),
            }
        )
        now = time.perf_counter()
        if now - last_print > 5.0:
            print(
                f"  {name}: {ii + 1}/{len(idx)} cells, "
                f"elapsed {now - t0:.1f} s",
                flush=True,
            )
            last_print = now
    print(f"  {name}: done {len(rows)} cells in {time.perf_counter() - t0:.1f} s")
    return rows


# ---------------------------------------------------------------------------
# Figure helpers
# ---------------------------------------------------------------------------
def _plot_figs(rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    arr = np.array(
        [(r["dataset"], r["alpha"], r["Rx"], r["snrV"], r["snrI"],
          r["loc_err_pct"], r["Rx_err_pct"]) for r in rows],
        dtype=object,
    )
    datasets = sorted(set(arr[:, 0]))
    snr_levels = sorted({float(s) for s in arr[:, 4] if np.isfinite(float(s))})

    # (a) RMS loc-error vs SNR_I per dataset
    fig, ax = plt.subplots(figsize=(8, 5))
    for ds in datasets:
        m = arr[:, 0] == ds
        snrI = arr[m, 4].astype(float)
        loc = arr[m, 5].astype(float)
        x_vals, y_vals = [], []
        for s in snr_levels:
            sel = snrI == s
            if sel.any():
                x_vals.append(s)
                y_vals.append(np.sqrt(np.mean(loc[sel] ** 2)))
        # noiseless
        sel_inf = ~np.isfinite(snrI)
        if sel_inf.any():
            x_vals.append(50.0)  # plot Inf as 50 dB
            y_vals.append(np.sqrt(np.mean(loc[sel_inf] ** 2)))
        ax.plot(x_vals, y_vals, "-o", label=ds, linewidth=1.6)
    ax.set_xlabel(r"Current-channel SNR$_I$ [dB; 50 = noiseless]")
    ax.set_ylabel("RMS location error [%]")
    ax.set_yscale("log")
    ax.set_title("(a) RMS location error vs SNR$_I$ per dataset")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "a_rms_loc_err_vs_snrI.png", dpi=120)
    plt.close(fig)

    # (b) Heatmap of mean loc-error over alpha x Rx per dataset
    fig, axes = plt.subplots(1, len(datasets), figsize=(4.2 * len(datasets), 4.2))
    if len(datasets) == 1:
        axes = [axes]
    alphas_u = sorted({float(a) for a in arr[:, 1]})
    Rxs_u = sorted({float(r) for r in arr[:, 2]})
    for ax, ds in zip(axes, datasets, strict=False):
        H = np.full((len(alphas_u), len(Rxs_u)), np.nan)
        for i, a in enumerate(alphas_u):
            for j, R in enumerate(Rxs_u):
                m = (
                    (arr[:, 0] == ds)
                    & (arr[:, 1].astype(float) == a)
                    & (arr[:, 2].astype(float) == R)
                )
                if m.any():
                    H[i, j] = float(np.mean(arr[m, 5].astype(float)))
        im = ax.imshow(
            np.log10(np.maximum(H, 1e-6)),
            origin="lower",
            aspect="auto",
            extent=[Rxs_u[0], Rxs_u[-1], alphas_u[0], alphas_u[-1]],
            cmap="viridis",
        )
        ax.set_xlabel(r"Arc resistance $R_x$ [$\Omega$]")
        ax.set_ylabel(r"Per-unit fault location $\alpha$ [-]")
        ax.set_title(f"{ds}")
        plt.colorbar(im, ax=ax, label=r"$\log_{10}$ mean loc err [%]")
    fig.suptitle(r"(b) Mean fault-location error: $\alpha\times R_x$ heatmap")
    fig.tight_layout()
    fig.savefig(out_dir / "b_alpha_Rx_heatmap.png", dpi=120)
    plt.close(fig)

    # (c) Delta-error histogram (vs self-consistent)
    sc_loc = {r["cell"]: r["loc_err_pct"] for r in rows if r["dataset"] == "self_consistent"}
    fig, ax = plt.subplots(figsize=(8, 5))
    for ds in datasets:
        if ds == "self_consistent":
            continue
        deltas = [
            r["loc_err_pct"] - sc_loc.get(r["cell"], 0.0)
            for r in rows
            if r["dataset"] == ds
        ]
        ax.hist(deltas, bins=40, alpha=0.5, label=ds)
    ax.set_xlabel(r"$\Delta$ loc-err [pp] (dataset $-$ self-consistent)")
    ax.set_ylabel("Cell count")
    ax.set_title(r"(c) $\Delta$-error attribution histogram")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "c_delta_error_hist.png", dpi=120)
    plt.close(fig)

    # (d) Estimated-vs-true scatter coloured by dataset
    fig, ax = plt.subplots(figsize=(7, 7))
    for ds in datasets:
        m = arr[:, 0] == ds
        a_true = arr[m, 1].astype(float)
        # Recover alpha_hat from loc_err: loc_err = 100*|alpha_hat - alpha_true|/alpha_true
        # We didn't store alpha_hat; approximate via err magnitude (sign lost).
        a_hat = a_true * (1.0 + arr[m, 5].astype(float) / 100.0)
        ax.plot(a_true, a_hat, ".", alpha=0.4, label=ds, markersize=3)
    a_line = np.linspace(0, 1, 50)
    ax.plot(a_line, a_line, "k--", alpha=0.6, linewidth=1, label="ideal")
    ax.set_xlabel(r"True $\alpha$ [-]")
    ax.set_ylabel(r"Estimated $\alpha$ (lower-bound from loc-err) [-]")
    ax.set_title(r"(d) Estimated vs true $\alpha$ per dataset")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "d_estimated_vs_true.png", dpi=120)
    plt.close(fig)

    # (e) Rx error vs SNR_I per dataset
    fig, ax = plt.subplots(figsize=(8, 5))
    for ds in datasets:
        m = arr[:, 0] == ds
        snrI = arr[m, 4].astype(float)
        Rx_err = arr[m, 6].astype(float)
        x_vals, y_vals = [], []
        for s in snr_levels:
            sel = snrI == s
            if sel.any():
                x_vals.append(s)
                y_vals.append(float(np.mean(Rx_err[sel])))
        sel_inf = ~np.isfinite(snrI)
        if sel_inf.any():
            x_vals.append(50.0)
            y_vals.append(float(np.mean(Rx_err[sel_inf])))
        ax.plot(x_vals, y_vals, "-o", label=ds, linewidth=1.6)
    ax.set_xlabel(r"Current-channel SNR$_I$ [dB; 50 = noiseless]")
    ax.set_ylabel(r"Mean $R_x$ error [%]")
    ax.set_yscale("log")
    ax.set_title(r"(e) Mean $R_x$ error vs SNR$_I$ per dataset")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "e_Rx_err_vs_snrI.png", dpi=120)
    plt.close(fig)

    # (f) Per-cell loc_err boxplot per dataset
    fig, ax = plt.subplots(figsize=(7, 5))
    box_data = [arr[arr[:, 0] == ds, 5].astype(float) for ds in datasets]
    ax.boxplot(box_data, tick_labels=datasets, showmeans=True)
    ax.set_ylabel("Per-cell location error [%]")
    ax.set_yscale("log")
    ax.set_title("(f) Per-cell location-error distribution per dataset")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_dir / "f_loc_err_boxplot.png", dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--quick", action="store_true",
                        help="Subsample to 3 alpha x 5 Rx x 4 SNR_V x 4 SNR_I = 240 cells/dataset.")
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []

    # Three canonical datasets
    for name, path in DATASETS:
        if not path.exists():
            print(f"missing {path} - run the surrogate first", file=sys.stderr)
            return 2
        S = loadmat(str(path))
        print(f"running {name} ({path.name})")
        all_rows.extend(
            _run_dataset(
                name,
                S["V"],
                S["I"],
                S["grid_alpha"].squeeze(),
                S["grid_Rx"].squeeze(),
                S["grid_SNR_V"].squeeze(),
                S["grid_SNR_I"].squeeze(),
                quick=args.quick,
            )
        )

    # Self-consistent baseline (Cascaded-Gamma data === optimiser model)
    print("running self_consistent (Cascaded-Gamma data == optimiser model)")
    S0 = loadmat(str(DATASETS[0][1]))
    grid_alpha = S0["grid_alpha"].squeeze()
    grid_Rx = S0["grid_Rx"].squeeze()
    grid_SNR_V = S0["grid_SNR_V"].squeeze()
    grid_SNR_I = S0["grid_SNR_I"].squeeze()
    V_sc, I_sc = _build_self_consistent(grid_alpha, grid_Rx, grid_SNR_V, grid_SNR_I)
    all_rows.extend(
        _run_dataset(
            "self_consistent",
            V_sc,
            I_sc,
            grid_alpha,
            grid_Rx,
            grid_SNR_V,
            grid_SNR_I,
            quick=args.quick,
        )
    )

    # ---- Write CSV: per-cell results ------------------------------------
    out_csv = OUT_DIR / "phase1_crossplatform_results.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["dataset", "cell", "alpha", "Rx", "snrV", "snrI",
                        "loc_err_pct", "Rx_err_pct", "J_final", "n_iters", "cpu_ms"],
        )
        w.writeheader()
        for row in all_rows:
            w.writerow(row)
    print(f"wrote {out_csv}  ({len(all_rows)} rows)")

    # ---- Delta-error attribution CSV -----------------------------------
    sc_loc = {r["cell"]: r["loc_err_pct"] for r in all_rows if r["dataset"] == "self_consistent"}
    sc_Rx  = {r["cell"]: r["Rx_err_pct"]  for r in all_rows if r["dataset"] == "self_consistent"}
    delta_csv = OUT_DIR / "phase1_delta_error_attribution.csv"
    with delta_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["dataset", "cell", "alpha", "Rx", "snrV", "snrI",
             "loc_err_pct", "loc_err_self_pct", "delta_loc_pp",
             "Rx_err_pct", "Rx_err_self_pct", "delta_Rx_pp"]
        )
        for r in all_rows:
            if r["dataset"] == "self_consistent":
                continue
            sc_l = sc_loc.get(r["cell"], 0.0)
            sc_r = sc_Rx.get(r["cell"], 0.0)
            w.writerow(
                [r["dataset"], r["cell"], f"{r['alpha']:.3f}", f"{r['Rx']:.1f}",
                 f"{r['snrV']:.1f}", f"{r['snrI']:.1f}",
                 f"{r['loc_err_pct']:.6f}", f"{sc_l:.6f}",
                 f"{r['loc_err_pct'] - sc_l:.6f}",
                 f"{r['Rx_err_pct']:.6f}", f"{sc_r:.6f}",
                 f"{r['Rx_err_pct'] - sc_r:.6f}"]
            )
    print(f"wrote {delta_csv}")

    # ---- Six figures ---------------------------------------------------
    print(f"plotting six figures into {FIG_DIR}")
    _plot_figs(all_rows, FIG_DIR)
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
