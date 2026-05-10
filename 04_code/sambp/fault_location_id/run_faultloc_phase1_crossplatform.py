"""
run_faultloc_phase1_crossplatform.py
=====================================

WP1.4 cross-platform optimiser re-run + WP1.5 Monte-Carlo wrapper.

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

WP1.5 Monte-Carlo mode (--monte-carlo N) draws N independent noise
realisations per cell per dataset (varying the rng seed away from
rng(42)), then writes:

    outputs/phase1_montecarlo_results.parquet
        long-format (dataset, alpha, Rx, snrV, snrI, trial,
        loc_err_pct, Rx_err_pct, J_final)

    outputs/phase1_montecarlo_summary.csv
        per-cell summary (mean/std/p5/p50/p95 of loc + Rx error,
        one-sided t-test for zero bias, 95 % CI half-width).

    outputs/phase1_figs/mc_distribution_*.png
        empirical CDF of loc-err per cell at SNR_I = 20 dB.

Usage
-----
    .venv/bin/python run_faultloc_phase1_crossplatform.py
    .venv/bin/python run_faultloc_phase1_crossplatform.py --quick
        (quick mode: subsample to alpha in {0.3, 0.5, 0.7}, useful for CI)
    .venv/bin/python run_faultloc_phase1_crossplatform.py --monte-carlo 100
    .venv/bin/python run_faultloc_phase1_crossplatform.py --monte-carlo 100 \\
        --mc-quick     (subsample to 9 cells per dataset, smoke check)
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
sys.path.insert(0, str(PROJ_ROOT))  # so `import tools.*` works for MC mode

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


# ===========================================================================
# WP1.5 Monte-Carlo mode
# ===========================================================================

# Forward-model dispatch per dataset (re-derives noiseless H from
# (alpha, Rx) using the dataset's underlying physics).  Imported
# lazily so --crossplatform mode does not pay the import cost.
def _h_dataset_factory(name: str):
    omega0 = 2.0 * np.pi * F0
    if name == "pscad":
        from tools.pscad_surrogate import H_distributed
        return lambda a, R: H_distributed(a, R, omega0)
    if name == "emtp":
        from tools.emtp_surrogate import H_50section
        return lambda a, R: H_50section(a, R, omega0)
    if name == "ref50":
        from sambp_fault_location_id.models.faultloc_50section_reference import (
            H_model_n_sections,
        )
        return lambda a, R: H_model_n_sections(a, R, omega0)
    if name == "self_consistent":
        return lambda a, R: H_model(a, R, omega0)
    raise KeyError(name)


def _mc_synthesize(H_true: complex, snrV: float, snrI: float, rng) -> complex:
    """Build noisy V/I waveforms for one trial and return H_meas."""
    Vph = V_PHASE * np.sqrt(2.0)
    omega = 2.0 * np.pi * F0
    t = np.arange(NS) / FS
    v = Vph * np.cos(omega * t)
    i = (H_true * Vph * np.exp(1j * omega * t)).real
    if np.isfinite(snrV):
        sigma = np.sqrt(float(np.mean(v ** 2)) / (10 ** (snrV / 10)))
        v = v + sigma * rng.standard_normal(NS)
    if np.isfinite(snrI):
        sigma = np.sqrt(float(np.mean(i ** 2)) / (10 ** (snrI / 10)))
        i = i + sigma * rng.standard_normal(NS)
    from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
        H_meas_from_waveforms,
    )
    return H_meas_from_waveforms(v, i, FS, F0)


def _mc_one_trial(args_tuple):
    """Worker for joblib.Parallel.  Runs one (cell, trial) and returns one row."""
    (dataset, alpha, Rx, snrV, snrI, trial, H_true) = args_tuple
    rng = np.random.default_rng(2026_05_10 + 1_000 * trial + int(alpha * 1000) * 100 + int(Rx))
    H_meas = _mc_synthesize(H_true, snrV, snrI, rng)
    theta, info = estimate_alpha_Rx(H_meas)
    loc_err = 100.0 * abs(theta[0] - alpha) / alpha
    Rx_err = 100.0 * abs(theta[1] - Rx) / Rx
    return {
        "dataset": dataset,
        "alpha": float(alpha),
        "Rx": float(Rx),
        "snrV": float(snrV),
        "snrI": float(snrI),
        "trial": int(trial),
        "loc_err_pct": float(loc_err),
        "Rx_err_pct": float(Rx_err),
        "J_final": float(info.J_min),
    }


def _build_jobs(datasets: list[str], alphas, Rxs, snrVs, snrIs, n_trials: int):
    jobs = []
    htrue_cache: dict = {}
    for ds in datasets:
        h_func = _h_dataset_factory(ds)
        for a in alphas:
            for R in Rxs:
                key = (ds, float(a), float(R))
                if key not in htrue_cache:
                    htrue_cache[key] = h_func(float(a), float(R))
                H_true = htrue_cache[key]
                for sV in snrVs:
                    for sI in snrIs:
                        for t in range(n_trials):
                            jobs.append((ds, float(a), float(R), float(sV),
                                         float(sI), int(t), H_true))
    return jobs


def _summarise_mc(rows: list[dict]) -> list[dict]:
    """Per-cell summary stats + zero-bias t-test + 95% CI half-width."""
    from collections import defaultdict

    from scipy.stats import t as student_t

    by_cell: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r["dataset"], r["alpha"], r["Rx"], r["snrV"], r["snrI"])
        by_cell[key].append(r)

    summary = []
    for key, trials in by_cell.items():
        ds, a, R, sV, sI = key
        loc = np.array([r["loc_err_pct"] for r in trials])
        Rx_e = np.array([r["Rx_err_pct"] for r in trials])
        n = len(loc)
        loc_mean = float(loc.mean())
        loc_std = float(loc.std(ddof=1))
        Rx_mean = float(Rx_e.mean())
        Rx_std = float(Rx_e.std(ddof=1))
        # 95 % CI half-width on mean (Student t)
        tcrit = float(student_t.ppf(0.975, df=n - 1))
        ci_half = tcrit * loc_std / np.sqrt(n)
        # One-sided t-test for zero bias (H1: mean > 0)
        t_stat = loc_mean / (loc_std / np.sqrt(n)) if loc_std > 0 else float("inf")
        p_one = float(1.0 - student_t.cdf(t_stat, df=n - 1))
        ci_excludes_zero = (loc_mean - ci_half) > 0.0
        summary.append({
            "dataset": ds, "alpha": a, "Rx": R, "snrV": sV, "snrI": sI,
            "n_trials": n,
            "loc_mean_pct": loc_mean, "loc_std_pct": loc_std,
            "loc_p5": float(np.percentile(loc, 5)),
            "loc_p50": float(np.percentile(loc, 50)),
            "loc_p95": float(np.percentile(loc, 95)),
            "Rx_mean_pct": Rx_mean, "Rx_std_pct": Rx_std,
            "Rx_p5": float(np.percentile(Rx_e, 5)),
            "Rx_p50": float(np.percentile(Rx_e, 50)),
            "Rx_p95": float(np.percentile(Rx_e, 95)),
            "ci_halfwidth_pct": float(ci_half),
            "ci_excludes_zero": int(ci_excludes_zero),
            "p_one_sided_zero_bias": p_one,
        })
    return summary


def _plot_ecdf_per_cell(rows: list[dict], out_dir: Path) -> None:
    """ECDF of loc-err per dataset at SNR_I=20 dB; one panel per (alpha,Rx)."""
    df = [r for r in rows if r["snrI"] == 20.0]
    if not df:
        return
    alphas = sorted({r["alpha"] for r in df})
    Rxs = sorted({r["Rx"] for r in df})
    out_dir.mkdir(parents=True, exist_ok=True)
    # One file per (alpha, Rx): ECDF of all 4 datasets across all SNR_V values
    for a in alphas:
        for R in Rxs:
            cell_rows = [r for r in df if r["alpha"] == a and r["Rx"] == R]
            if not cell_rows:
                continue
            datasets = sorted({r["dataset"] for r in cell_rows})
            fig, ax = plt.subplots(figsize=(7, 4.5))
            for ds in datasets:
                vals = sorted(r["loc_err_pct"] for r in cell_rows if r["dataset"] == ds)
                if not vals:
                    continue
                xs = np.array(vals)
                ys = np.arange(1, len(xs) + 1) / len(xs)
                ax.step(xs, ys, where="post", label=ds, linewidth=1.4)
            ax.set_xscale("log")
            ax.set_xlabel("Per-trial location error [%]")
            ax.set_ylabel("Empirical CDF [-]")
            ax.set_title(
                rf"ECDF, $\alpha={a:.2f}$, $R_x={R:.0f}\,\Omega$, "
                rf"$\mathrm{{SNR}}_I=20$ dB (across SNR$_V$ trials)"
            )
            ax.grid(alpha=0.3, which="both")
            ax.legend()
            fig.tight_layout()
            fig.savefig(
                out_dir / f"mc_distribution_a{a:.2f}_R{int(R)}.png", dpi=110
            )
            plt.close(fig)


def _run_monte_carlo(
    n_trials: int,
    *,
    n_jobs: int = -1,
    quick: bool = False,
    forecast_only: bool = False,
) -> int:
    """Phase-1 Monte-Carlo driver.  Returns 0 on success."""
    import joblib
    import pyarrow as pa
    import pyarrow.parquet as pq

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    # Grids (mirror of WP1.4 dataset schema)
    if quick:
        alphas = np.array([0.3, 0.5, 0.7])
        Rxs = np.array([1000.0])
        snrVs = np.array([30.0, np.inf])
        snrIs = np.array([20.0, 30.0, np.inf])
    else:
        alphas = np.round(np.arange(0.10, 0.91, 0.10), 6)
        Rxs = np.array([100.0, 500.0, 1000.0, 2000.0, 5000.0])
        snrVs = np.array([20.0, 30.0, 40.0, np.inf])
        snrIs = np.array([20.0, 30.0, 40.0, np.inf])

    datasets = ["pscad", "emtp", "ref50", "self_consistent"]
    n_cells = len(alphas) * len(Rxs) * len(snrVs) * len(snrIs)
    n_total = len(datasets) * n_cells * n_trials
    print(
        f"WP1.5 MC plan: {len(datasets)} datasets x {n_cells} cells x "
        f"{n_trials} trials = {n_total} jobs"
    )

    # Timing forecast: 5 cells x 5 trials
    print("WP1.5 forecast: timing 5 cells x 5 trials (1 dataset)...")
    sample_jobs = _build_jobs(
        ["self_consistent"], alphas[:5] if len(alphas) >= 5 else alphas,
        Rxs[:1], snrVs[:1], snrIs[:1], 5,
    )[:25]
    t0 = time.perf_counter()
    for j in sample_jobs:
        _mc_one_trial(j)
    serial_t = (time.perf_counter() - t0) / max(len(sample_jobs), 1)
    n_workers = (n_jobs if n_jobs > 0 else (joblib.cpu_count() or 1))
    forecast_s = n_total * serial_t / n_workers
    print(
        f"  per-trial wall: {serial_t * 1000:.1f} ms (serial) ; "
        f"workers={n_workers}; forecast = {forecast_s:.0f} s "
        f"= {forecast_s / 60:.1f} min = {forecast_s / 3600:.2f} h"
    )
    if forecast_s > 8 * 3600:
        print(
            "WP1.5 forecast > 8 hours - aborting per brief; "
            "ask the operator before re-running.",
            file=sys.stderr,
        )
        return 5
    if forecast_only:
        return 0

    # Build all jobs
    jobs = _build_jobs(datasets, alphas, Rxs, snrVs, snrIs, n_trials)
    print(f"WP1.5 dispatching {len(jobs)} jobs across {n_workers} workers...")
    t0 = time.perf_counter()
    rows = joblib.Parallel(
        n_jobs=n_jobs, backend="loky", verbose=0
    )(joblib.delayed(_mc_one_trial)(j) for j in jobs)
    print(f"WP1.5 done in {time.perf_counter() - t0:.1f} s ({len(rows)} rows)")

    # Write parquet
    parquet_path = OUT_DIR / "phase1_montecarlo_results.parquet"
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, str(parquet_path), compression="zstd")
    print(f"  wrote {parquet_path}")

    # Per-cell summary
    summary = _summarise_mc(rows)
    summary_csv = OUT_DIR / "phase1_montecarlo_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        w.writeheader()
        for s in summary:
            w.writerow(s)
    print(f"  wrote {summary_csv}  ({len(summary)} cells)")

    # ECDF figures at SNR_I=20 dB
    print("  plotting ECDFs at SNR_I=20 dB...")
    _plot_ecdf_per_cell(rows, FIG_DIR)
    print("WP1.5 done.")
    return 0


# ===========================================================================
# Driver
# ===========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--quick", action="store_true",
                        help="Subsample to 3 alpha x 5 Rx x 4 SNR_V x 4 SNR_I = 240 cells/dataset.")
    parser.add_argument("--monte-carlo", type=int, default=0, metavar="N",
                        help="Run WP1.5 Monte-Carlo with N trials per cell.")
    parser.add_argument("--mc-quick", action="store_true",
                        help="MC sub-grid: 3 alpha x 1 Rx x 2 SNR_V x 3 SNR_I = 18 cells/dataset.")
    parser.add_argument("--mc-jobs", type=int, default=-1,
                        help="joblib n_jobs (default: all cores).")
    parser.add_argument("--mc-forecast-only", action="store_true",
                        help="Print runtime forecast and exit without running MC.")
    args = parser.parse_args(argv)

    if args.monte_carlo > 0:
        return _run_monte_carlo(
            args.monte_carlo,
            n_jobs=args.mc_jobs,
            quick=args.mc_quick,
            forecast_only=args.mc_forecast_only,
        )

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
