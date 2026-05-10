"""
run_faultloc_phase4_benchmark.py
=================================

WP4.5 (P4.5) head-to-head benchmark runner.

Pipeline
--------

For each of three datasets:
  * IEEE 34-node 720-grid (the WP3.3 baseline);
  * Wang-2020 distortion-controllable HIAF
    (`data/wang2020_ieee34_720.mat` if present);
  * Torres-2022 stochastic-configurable arc
    (3 profiles, regenerated in-runner if needed).

Run all five methods:
  * the proposed WP1.4 / WP2.4 single-bin DFT optimiser
    (the "proposed" entry);
  * Paramo-2023 (extended) eigenvalue location;
  * Iurinic-2018 / Orozco-Henao-2020 spectral location;
  * Cui-Weng-2020 micro-PMU two-ended location;
  * Zeng-2021 damping-rate double-ended location.

Per-cell metrics: ``loc_err_pct``, ``Rx_err_pct``, ``cpu_ms``.
Aggregated headline metrics per (method, dataset):
``mean_loc_err_pct``, ``p95_loc_err_pct``, ``mean_Rx_err_pct``,
``mean_cpu_ms``, plus the descriptive columns
``comm_infrastructure``, ``training_data_required``,
``snr_floor_for_5pct_loc_err``.

Output
------

* ``outputs/phase4_table3bis.csv`` -- the full Table 3-bis with
  one row per (method, dataset) pair.
* ``outputs/phase4_figs/table3bis_summary.pdf`` -- single-page
  bar-grouped figure suitable for the IEEE TSG benchmark paper.

Tractable scope
---------------

5 buses x 5 R_x x 4 SNR_I subset x 8 trials = 800 cells per
dataset; 3 datasets x 5 methods = 15 (method, dataset) pairs;
5 methods x 800 cells x 3 datasets = 12 000 estimate calls.
Approx 8-12 min on the dev box.  The full 720-grid x 100-trial
canonical run is queued for the licensed Windows runner.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from sambp_fault_location_id.evaluation.faultloc_competitor_cuiweng import (
    estimate as estimate_cuiweng,
)
from sambp_fault_location_id.evaluation.faultloc_competitor_iurinic import (
    estimate as estimate_iurinic,
)
from sambp_fault_location_id.evaluation.faultloc_competitor_paramo import (
    estimate as estimate_paramo,
)
from sambp_fault_location_id.evaluation.faultloc_competitor_zeng import (
    estimate as estimate_zeng,
)
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    H_meas_from_waveforms,
    estimate_alpha_Rx,
)
from sambp_fault_location_id.models.faultloc_arc_models import (
    EmanuelArc,
    Torres2022Arc,
    Wang2020Arc,
)
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    L_PER_KM,
    LINE_LENGTH_KM,
    R_PER_KM,
    H_distributed,
)
from scipy.io import loadmat

PROJ_ROOT = Path(__file__).resolve().parent
IEEE34_BUNDLE = PROJ_ROOT / "data" / "ieee34_720.mat"
WANG_BUNDLE = PROJ_ROOT / "data" / "wang2020_ieee34_720.mat"
OUT_CSV = PROJ_ROOT / "outputs" / "phase4_table3bis.csv"
OUT_FIG_DIR = PROJ_ROOT / "outputs" / "phase4_figs"

OMEGA = 2.0 * np.pi * 50.0
F0 = 50.0
FS = 10_000.0
N_CYCLES = 1
N_SAMPLES = int(round(N_CYCLES * FS / F0))


# Method-descriptor table (Table 3-bis static columns).
METHOD_DESCRIPTORS = {
    "proposed": {
        "comm_infrastructure": "single-ended (substation-only)",
        "training_data_required": "none (training-free)",
    },
    "paramo2023": {
        "comm_infrastructure": "single-ended PMU",
        "training_data_required": "none",
    },
    "iurinic2018": {
        "comm_infrastructure": "single-ended (3rd-harmonic)",
        "training_data_required": "none",
    },
    "cuiweng2020": {
        "comm_infrastructure": "two-ended (mu-PMU + virtual-DT VR)",
        "training_data_required": "none (DT-bootstrapped)",
    },
    "zeng2021": {
        "comm_infrastructure": "two-ended damping-rate",
        "training_data_required": "calibration table from line params",
    },
}


class _BenchNetwork:
    """Adapter exposing the forward / virtual-PMU / damping APIs the
    competitor modules expect.  Backed by the WP2.1 distributed-
    parameter forward model."""

    f0 = F0
    Z_total = complex(R_PER_KM * LINE_LENGTH_KM,
                      OMEGA * L_PER_KM * LINE_LENGTH_KM)
    zeta_max = 50.0

    def forward(self, alpha: float, Rx: float, harmonic: int = 1) -> complex:
        return H_distributed(alpha, Rx, OMEGA * harmonic)

    def virtual_pmu_VR(self, alpha: float) -> complex:
        # Virtual remote-end voltage from the digital twin: nominal
        # remote-bus voltage scaled by (1 - alpha) drop along the line.
        V_nom = 11.0e3 * np.sqrt(2.0 / 3.0) + 0j
        return V_nom * (1.0 - 0.05 * alpha)

    def zeta_to_alpha(self, zeta: float) -> float:
        return float(np.clip(zeta / max(self.zeta_max, 1e-9), 0.02, 0.98))


def _synth_v(rng, snr_v_db) -> np.ndarray:
    V_peak = 11.0e3 * np.sqrt(2.0 / 3.0)
    n = np.arange(N_SAMPLES)
    t = n / FS
    v = V_peak * np.cos(OMEGA * t)
    if np.isfinite(snr_v_db):
        rms = float(np.sqrt(np.mean(v ** 2)))
        v = v + rng.standard_normal(v.shape) * (
            rms * 10.0 ** (-snr_v_db / 20.0)
        )
    return v


def _add_noise(i, snr_i_db, rng) -> np.ndarray:
    if not np.isfinite(snr_i_db):
        return i
    rms = float(np.sqrt(np.mean(i ** 2)))
    return i + rng.standard_normal(i.shape) * (
        rms * 10.0 ** (-snr_i_db / 20.0)
    )


def _err_pct(hat, true):
    if true <= 0 or not np.isfinite(hat):
        return float("nan")
    return 100.0 * abs(hat - true) / true


def _proposed_estimate(v, i, fs, network):
    """Wrap the WP1.4 / WP2.4 optimiser to the competitor API."""
    t0 = time.perf_counter()
    H = H_meas_from_waveforms(v, i, fs=fs, f0=network.f0)
    try:
        (a, R), _ = estimate_alpha_Rx(H, opts={
            "snr_v_db": np.inf, "snr_i_db": 40.0, "max_iter": 200,
        })
        a, R = float(a), float(R)
    except Exception:
        a, R = float("nan"), float("nan")
    return {
        "alpha": a, "Rx": R,
        "cpu_ms": 1000.0 * (time.perf_counter() - t0),
    }


METHOD_FNS = {
    "proposed": _proposed_estimate,
    "paramo2023": estimate_paramo,
    "iurinic2018": estimate_iurinic,
    "cuiweng2020": estimate_cuiweng,
    "zeng2021": estimate_zeng,
}


def _select_cells(grid_alpha, grid_Rx, grid_SNR_V, grid_SNR_I,
                  fault_bus_strs, n_buses):
    unique_buses = sorted(set(fault_bus_strs))
    if n_buses < len(unique_buses):
        stride = max(1, len(unique_buses) // n_buses)
        chosen = set(unique_buses[::stride][:n_buses])
    else:
        chosen = set(unique_buses)
    return [
        k for k in range(len(fault_bus_strs))
        if fault_bus_strs[k] in chosen
        and (grid_SNR_I[k] >= 30.0 or not np.isfinite(grid_SNR_I[k]))
    ]


def _run_one_dataset(
    dataset_name: str,
    selected: list[int],
    grid_alpha, grid_Rx, grid_SNR_V, grid_SNR_I, fault_bus_strs,
    arc_factory,
    n_trials: int,
    rng_seed: int,
):
    """Run all 5 methods on a (dataset, sub-sample) and return a list
    of per-(cell, trial, method) result dicts."""
    rng = np.random.default_rng(rng_seed)
    network = _BenchNetwork()
    rows = []
    n_total = n_trials * len(selected) * len(METHOD_FNS)
    n_done = 0
    t0 = time.perf_counter()
    for trial in range(n_trials):
        arc = arc_factory(rng)
        for k in selected:
            Rx = float(grid_Rx[k])
            alpha = float(grid_alpha[k])
            snr_v = float(grid_SNR_V[k])
            snr_i = float(grid_SNR_I[k])
            t = np.arange(N_SAMPLES) / FS
            v = _synth_v(rng, snr_v)
            i_clean = arc.synthesise_current(t, v, Rx)
            i = _add_noise(i_clean, snr_i, rng)
            for method_name, fn in METHOD_FNS.items():
                try:
                    out = fn(v, i, FS, network)
                    a_hat = float(out["alpha"])
                    R_hat = float(out["Rx"])
                    cpu_ms = float(out["cpu_ms"])
                except Exception:
                    a_hat = float("nan")
                    R_hat = float("nan")
                    cpu_ms = float("nan")
                rows.append({
                    "dataset": dataset_name,
                    "method": method_name,
                    "trial": trial,
                    "fault_bus": fault_bus_strs[k],
                    "alpha_true": alpha,
                    "Rx_true": Rx,
                    "snr_v_db": snr_v,
                    "snr_i_db": snr_i,
                    "alpha_hat": a_hat,
                    "Rx_hat": R_hat,
                    "loc_err_pct": _err_pct(a_hat, alpha),
                    "Rx_err_pct": _err_pct(R_hat, Rx),
                    "cpu_ms": cpu_ms,
                })
                n_done += 1
                if n_done % max(1, n_total // 5) == 0:
                    elapsed = time.perf_counter() - t0
                    eta = elapsed * (n_total - n_done) / max(n_done, 1)
                    print(
                        f"  [{dataset_name}] [{n_done}/{n_total}] "
                        f"elapsed {elapsed:.0f}s; eta {eta:.0f}s"
                    )
    return rows


def _aggregate_table3bis(per_cell_rows):
    """Aggregate per-cell rows into the (method, dataset) Table 3-bis."""
    out_rows = []
    keys = sorted({(r["method"], r["dataset"]) for r in per_cell_rows})
    for method, dataset in keys:
        subset = [r for r in per_cell_rows
                  if r["method"] == method and r["dataset"] == dataset]
        loc = np.array([r["loc_err_pct"] for r in subset
                        if np.isfinite(r["loc_err_pct"])])
        rx = np.array([r["Rx_err_pct"] for r in subset
                       if np.isfinite(r["Rx_err_pct"])])
        cpu = np.array([r["cpu_ms"] for r in subset
                        if np.isfinite(r["cpu_ms"])])
        # SNR floor for 5 % loc-err: lowest SNR_I bin where the mean
        # loc-err over (cell, trial) is < 5 %.
        snr_bins = sorted({r["snr_i_db"] for r in subset
                           if np.isfinite(r["snr_i_db"])})
        snr_floor = float("nan")
        for s in snr_bins:
            errs = [r["loc_err_pct"] for r in subset
                    if r["snr_i_db"] == s
                    and np.isfinite(r["loc_err_pct"])]
            if len(errs) >= 5 and float(np.mean(errs)) < 5.0:
                snr_floor = float(s)
                break
        descr = METHOD_DESCRIPTORS[method]
        out_rows.append({
            "method": method,
            "dataset": dataset,
            "mean_loc_err_pct": float(loc.mean()) if len(loc) else float("nan"),
            "p95_loc_err_pct": (float(np.percentile(loc, 95))
                                if len(loc) else float("nan")),
            "mean_Rx_err_pct": float(rx.mean()) if len(rx) else float("nan"),
            "mean_cpu_ms": float(cpu.mean()) if len(cpu) else float("nan"),
            "comm_infrastructure": descr["comm_infrastructure"],
            "training_data_required": descr["training_data_required"],
            "snr_floor_for_5pct_loc_err": snr_floor,
        })
    return out_rows


def _emit_figure(table_rows):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"matplotlib not available; skipping figure: {exc}")
        return

    OUT_FIG_DIR.mkdir(parents=True, exist_ok=True)
    methods = list(METHOD_FNS.keys())
    datasets = sorted({r["dataset"] for r in table_rows})

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.5))
    ax_loc, ax_cpu = axs

    width = 0.8 / len(datasets)
    x = np.arange(len(methods))
    for di, ds in enumerate(datasets):
        loc_means = [
            next((r["mean_loc_err_pct"] for r in table_rows
                  if r["method"] == m and r["dataset"] == ds), float("nan"))
            for m in methods
        ]
        cpu_means = [
            next((r["mean_cpu_ms"] for r in table_rows
                  if r["method"] == m and r["dataset"] == ds), float("nan"))
            for m in methods
        ]
        ax_loc.bar(x + di * width - 0.4 + width / 2, loc_means,
                   width=width, label=ds)
        ax_cpu.bar(x + di * width - 0.4 + width / 2, cpu_means,
                   width=width, label=ds)

    ax_loc.set_xticks(x)
    ax_loc.set_xticklabels(methods, rotation=30, ha="right")
    ax_loc.set_ylabel("mean location error (%)")
    ax_loc.set_title("Mean location error per method x dataset")
    ax_loc.legend(fontsize=8)
    ax_loc.grid(axis="y", alpha=0.3)

    ax_cpu.set_xticks(x)
    ax_cpu.set_xticklabels(methods, rotation=30, ha="right")
    ax_cpu.set_ylabel("mean CPU time (ms / cell)")
    ax_cpu.set_title("Compute cost per method x dataset")
    ax_cpu.set_yscale("log")
    ax_cpu.legend(fontsize=8)
    ax_cpu.grid(axis="y", alpha=0.3, which="both")

    fig.suptitle(
        "WP4.5 Table 3-bis -- competitor benchmark "
        "(IEEE 34 sub-sample; 800 cells / dataset)",
        fontsize=11,
    )
    fig.tight_layout()
    out = OUT_FIG_DIR / "table3bis_summary.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def run(*, n_buses: int = 5, n_trials: int = 8, rng_seed: int = 89) -> None:
    if not IEEE34_BUNDLE.exists():
        raise FileNotFoundError(
            f"{IEEE34_BUNDLE} not present"
        )
    bundle = loadmat(str(IEEE34_BUNDLE))
    grid_alpha = bundle["grid_alpha"].squeeze()
    grid_Rx = bundle["grid_Rx"].squeeze()
    grid_SNR_V = bundle["grid_SNR_V"].squeeze()
    grid_SNR_I = bundle["grid_SNR_I"].squeeze()
    grid_fault_bus = bundle["grid_fault_bus"].squeeze()
    fault_bus_strs = [str(b).strip() for b in grid_fault_bus]
    selected = _select_cells(
        grid_alpha, grid_Rx, grid_SNR_V, grid_SNR_I,
        fault_bus_strs, n_buses,
    )
    print(f"WP4.5 benchmark: {len(selected)} cells / dataset, "
          f"{n_trials} trials, {len(METHOD_FNS)} methods, 3 datasets")

    emanuel = EmanuelArc(V_kp=2000.0, V_kn=1800.0)

    def emanuel_factory(_rng):
        return emanuel

    def wang_factory(rng):
        return Wang2020Arc(distortion_index=0.7, emanuel=emanuel, rng=rng)

    def torres_factory(rng):
        # Average three profiles by cycling.
        profile_cycle = ["tree", "sand", "concrete"]
        # Use a deterministic round-robin per trial; the rng still
        # drives the per-feature stochastic noise.
        prof = profile_cycle[int(rng.integers(0, 3))]
        return Torres2022Arc(profile=prof, emanuel=emanuel, rng=rng)

    all_rows = []
    all_rows += _run_one_dataset(
        "ieee34_emanuel", selected,
        grid_alpha, grid_Rx, grid_SNR_V, grid_SNR_I, fault_bus_strs,
        emanuel_factory, n_trials, rng_seed,
    )
    all_rows += _run_one_dataset(
        "ieee34_wang2020", selected,
        grid_alpha, grid_Rx, grid_SNR_V, grid_SNR_I, fault_bus_strs,
        wang_factory, n_trials, rng_seed + 1,
    )
    all_rows += _run_one_dataset(
        "ieee34_torres2022", selected,
        grid_alpha, grid_Rx, grid_SNR_V, grid_SNR_I, fault_bus_strs,
        torres_factory, n_trials, rng_seed + 2,
    )

    table_rows = _aggregate_table3bis(all_rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table_rows[0].keys()))
        w.writeheader()
        for r in table_rows:
            w.writerow(r)
    print(f"wrote {OUT_CSV} ({len(table_rows)} rows)")

    _emit_figure(table_rows)

    print()
    print("=== Table 3-bis headline ===")
    for r in table_rows:
        print(
            f"  {r['method']:12s} {r['dataset']:18s}  "
            f"mean_loc={r['mean_loc_err_pct']:.2f}%  "
            f"p95={r['p95_loc_err_pct']:.2f}%  "
            f"cpu={r['mean_cpu_ms']:.1f}ms"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n-buses", type=int, default=5)
    parser.add_argument("--n-trials", type=int, default=8)
    parser.add_argument("--rng-seed", type=int, default=89)
    args = parser.parse_args(argv)
    run(n_buses=args.n_buses, n_trials=args.n_trials, rng_seed=args.rng_seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
