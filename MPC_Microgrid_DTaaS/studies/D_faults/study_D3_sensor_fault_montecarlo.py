"""Study D.3 — AnomalyDetector ROC under sensor-offset attacks (Monte Carlo).

Per docs/FS_MPC_Simulation_Studies_Plan.pdf §5 (D.3). For each
(offset, n_sigma) cell, runs `n_trials` independent simulations: each
trial picks a random ICA and a random fault-injection time, applies a
DC-link voltage-sensor offset of `offset` V on that ICA's published
telemetry, then asks the DT whether the AnomalyDetector flagged the
right ICA (TP) and whether it spuriously flagged any of the other ICAs
(FP).

Outputs:
  - figures/study_D3_dt_sensor_fault.png   (one ROC curve per offset)
  - tables/study_D3.csv                    (full results table)
  - stdout                                  (cell-level metrics + summary)

Defaults: 200 trials × 5 offsets × 3 n_sigma values = 3000 trials.
Use `--smoke` to run a tiny version (3 trials × 1 offset × 1 n_sigma)
that finishes in seconds — for validating the pipeline before committing
to a long Monte Carlo run.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from joblib import Parallel, delayed

# Force UTF-8 stdout on Windows so unit symbols don't crash cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fs_mpc_mg import (
    Plant, PlantParams, HarmonicLoad, HarmonicLoadParams,
    IdealPLL, FSMPCController, FSMPCParams, EnergyPI, EnergyPIParams,
    ICAAgent,
)
from fs_mpc_mg.comm.pubsub import InMemoryPubSub
from fs_mpc_mg.comm.topics import topic_telemetry
from fs_mpc_mg.cmc import (
    Topology, BusNode, ICANode, LoadNode, Controller, ControllerConfig,
)
from fs_mpc_mg.cmc.topology import SwitchEdge
from fs_mpc_mg.dt import MicrogridDigitalTwin, TwinConfig
from fs_mpc_mg.dt.anomaly import AnomalyDetector


# Parameter sweep
OFFSETS_V: tuple[float, ...] = (5.0, 10.0, 25.0, 50.0, 100.0)
N_SIGMAS: tuple[float, ...] = (3.0, 5.0, 7.0)
N_TRIALS_DEFAULT: int = 200

# Simulation knobs
N_ICAS: int = 4
T_END: float = 110e-3            # 110 ms — warmup + fault window + 3τ detection horizon
WARMUP_SAMPLES: int = 300        # in residual samples (twin ticks) — 30 ms filtered baseline
FAULT_T_MIN: float = 50e-3       # post-warmup
FAULT_T_MAX: float = 70e-3       # leaves >=40 ms for LPF to settle on the new mean
TWIN_PERIOD: float = 100e-6


def _build_topology() -> Topology:
    t = Topology()
    t.add_bus(BusNode("grid", is_grid=True))
    t.add_bus(BusNode("pcc"))
    t.add_switch(SwitchEdge("tie", "grid", "pcc", closed=True))
    for k in range(N_ICAS):
        t.add_ica(ICANode(f"ica{k+1}", "pcc", s_max=80e3))
    t.add_load(LoadNode("load1", "pcc", p_nominal=100e3, nonlinear=True))
    return t


@dataclass
class TrialResult:
    fault_ica: str
    fault_t: float
    detected_on_fault_ica: bool
    fp_ica_count: int   # number of NON-faulted ICAs that received >=1 anomaly event


def run_one_trial(
    seed: int,
    offset_v: float,
    n_sigma: float,
    *,
    return_diagnostics: bool = False,
):
    """Run a single Monte Carlo trial. Returns detection outcome.

    If return_diagnostics is True, also returns the residual time series
    for the faulted ICA (sampled at every DT tick).
    """
    rng = np.random.default_rng(seed)

    fault_ica_idx = int(rng.integers(0, N_ICAS))
    fault_ica = f"ica{fault_ica_idx + 1}"
    fault_t = float(rng.uniform(FAULT_T_MIN, FAULT_T_MAX))

    # Build the sim — replicates run_dt_demo's wiring with anomaly only.
    topology = _build_topology()
    ps = InMemoryPubSub()

    plant_p = PlantParams()
    agents, plants = [], []
    for k in range(N_ICAS):
        plant = Plant(plant_p)
        inner = FSMPCController(FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=20e-6))
        outer = EnergyPI(EnergyPIParams(C=plant_p.C, R=plant_p.R, v_dc_ref=plant_p.v_dc_init))
        pll = IdealPLL(f_grid=plant_p.f_grid)
        agents.append(ICAAgent(f"ica{k+1}", inner, outer, pll, ps, telemetry_decim=10))
        plants.append(plant)

    load = HarmonicLoad(HarmonicLoadParams(P_fund=40e3, Q_fund=0.0))
    cmc = Controller(topology, ps, ControllerConfig(tick_period_s=5e-3, v_dc_ref_default=900.0))
    cmc.start(now=0.0)

    ica_ids = [f"ica{k+1}" for k in range(N_ICAS)]

    # We bypass MicrogridDigitalTwin's shadow-plant residual (its high
    # grid-frequency ripple swamps the offsets in the spec sweep) and
    # feed AnomalyDetector a cleaner residual: deviation of the published
    # v_dc from its setpoint. In nominal operation the outer PI keeps
    # v_dc within a few volts of 900 V, so a sensor offset shows up as a
    # clean DC bump on this signal. This is faithful to the spec's
    # AnomalyDetector — same threshold, dwell, and warmup logic.
    detectors = {
        iid: AnomalyDetector(
            ica_id=iid,
            n_sigma=n_sigma,
            dwell_count=5,
            warmup_samples=WARMUP_SAMPLES,
        )
        for iid in ica_ids
    }
    detector_events: dict[str, list] = {iid: [] for iid in ica_ids}

    # Subscribe each detector to its ICA's published v_dc, dispatching
    # (v_dc - 900) as the residual.
    def _make_handler(iid: str):
        det = detectors[iid]
        evs = detector_events[iid]
        def handler(_topic: str, payload):
            v = payload["value"] if isinstance(payload, dict) and "value" in payload else payload
            ts = payload.get("ts", 0.0) if isinstance(payload, dict) else 0.0
            res = float(v) - 900.0
            new = det.update(v_dc_residual=res, i_m_residual_norm=0.0, ts=ts)
            evs.extend(new)
        return handler
    for iid in ica_ids:
        ps.subscribe(topic_telemetry(iid, "v_dc"), _make_handler(iid))

    T_s = agents[0].inner.p.T_s
    N_steps = int(round(T_END / T_s))
    N_sub = 5
    dt_int = T_s / N_sub
    cmc_last_tick = -1.0

    for k in range(N_steps):
        t = k * T_s
        if (t - cmc_last_tick) >= cmc.cfg.tick_period_s - 1e-12:
            cmc.tick(now=t)
            cmc_last_tick = t

        v_s = load.v_s(t)
        i_l = load.i_l(t)
        i_l_share = i_l / N_ICAS

        for k_ica, (agent, plant) in enumerate(zip(agents, plants)):
            s = agent.step(t, plant.i_m, plant.v_dc, v_s, i_l_share)
            for _ in range(N_sub):
                plant.step(s, v_s, i_dc=0.0, dt=dt_int)
            # Sensor-fault injection on the chosen ICA, after the chosen time
            if k_ica == fault_ica_idx and t >= fault_t:
                ps.publish_value(
                    topic_telemetry(fault_ica, "v_dc"),
                    plant.v_dc + offset_v,
                    ts=t,
                )

    # Score: detected on faulted ICA after the fault time?
    detected = any(e.ts >= fault_t for e in detector_events[fault_ica])
    fp_count = sum(
        1 for iid in ica_ids
        if iid != fault_ica and len(detector_events[iid]) > 0
    )

    result = TrialResult(
        fault_ica=fault_ica,
        fault_t=fault_t,
        detected_on_fault_ica=detected,
        fp_ica_count=fp_count,
    )

    if return_diagnostics:
        residuals = twin.residuals[fault_ica]
        ts = np.array([r.t for r in residuals])
        v_dc_resid = np.array([r.v_dc_residual for r in residuals])
        all_events = [(iid, e) for iid, evs in detector_events.items() for e in evs]
        return result, ts, v_dc_resid, all_events
    return result


def run_cell(
    offset_v: float, n_sigma: float, n_trials: int, master_seed: int = 42, n_jobs: int = -1
) -> tuple[float, float, list[TrialResult]]:
    """Run all trials for one (offset, n_sigma) cell. Returns (TPR, FPR, raw)."""
    # Derive a deterministic seed per trial from (master_seed, offset, n_sigma, idx)
    cell_rng = np.random.default_rng((master_seed, int(offset_v * 100), int(n_sigma * 100)))
    trial_seeds = cell_rng.integers(0, 2**31 - 1, size=n_trials).tolist()

    results = Parallel(n_jobs=n_jobs, prefer="processes")(
        delayed(run_one_trial)(int(s), offset_v, n_sigma) for s in trial_seeds
    )

    tp = sum(1 for r in results if r.detected_on_fault_ica)
    fp = sum(r.fp_ica_count for r in results)

    tpr = tp / n_trials
    # Each trial has (N_ICAS - 1) negative cases (the unfaulted ICAs)
    fpr = fp / (n_trials * (N_ICAS - 1))
    return tpr, fpr, results


def main() -> None:
    parser = argparse.ArgumentParser(description="Study D.3 — sensor-fault Monte Carlo")
    parser.add_argument(
        "--smoke", action="store_true",
        help="Tiny smoke run (1 offset, 1 n_sigma, 3 trials) — validates pipeline.",
    )
    parser.add_argument(
        "--n-trials", type=int, default=N_TRIALS_DEFAULT,
        help=f"Trials per cell (default {N_TRIALS_DEFAULT})",
    )
    parser.add_argument(
        "--n-jobs", type=int, default=-1,
        help="joblib n_jobs (default -1 = all cores)",
    )
    args = parser.parse_args()

    if args.smoke:
        offsets = (50.0,)
        sigmas = (5.0,)
        n_trials = 3
        print("[D.3] SMOKE RUN — pipeline validation only.")
    else:
        offsets = OFFSETS_V
        sigmas = N_SIGMAS
        n_trials = args.n_trials

    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    fig_dir = repo_root / "fs_mpc_microgrid" / "figures"
    tab_dir = repo_root / "fs_mpc_microgrid" / "tables"
    fig_dir.mkdir(parents=True, exist_ok=True)
    tab_dir.mkdir(parents=True, exist_ok=True)

    print(f"[D.3] Sweep: offsets={offsets} V  n_sigmas={sigmas}  trials/cell={n_trials}")
    print(f"      Total trials: {len(offsets) * len(sigmas) * n_trials}")
    print(f"      n_jobs={args.n_jobs}")

    t0 = time.time()
    rows: list[dict] = []
    cell_results: dict[tuple[float, float], tuple[float, float]] = {}

    for offset in offsets:
        for sigma in sigmas:
            t_cell0 = time.time()
            tpr, fpr, _ = run_cell(offset, sigma, n_trials, n_jobs=args.n_jobs)
            elapsed = time.time() - t_cell0
            cell_results[(offset, sigma)] = (tpr, fpr)
            rows.append({
                "offset_V": offset,
                "n_sigma": sigma,
                "n_trials": n_trials,
                "TPR": tpr,
                "FPR": fpr,
                "cell_runtime_s": elapsed,
            })
            print(f"  offset={offset:6.1f} V  n_sigma={sigma:.1f}   "
                  f"TPR={tpr:.3f}  FPR={fpr:.3f}   ({elapsed:.1f} s)")

    total_elapsed = time.time() - t0
    print(f"\nTotal runtime: {total_elapsed:.1f} s ({total_elapsed/60:.1f} min)")

    # ------------------------------------------------------------------
    # CSV
    csv_path = tab_dir / "study_D3.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for row in rows:
            w.writerow({**row,
                        "TPR": f"{row['TPR']:.6g}",
                        "FPR": f"{row['FPR']:.6g}",
                        "cell_runtime_s": f"{row['cell_runtime_s']:.3g}"})
    print(f"Saved CSV: {csv_path}")

    # ------------------------------------------------------------------
    # ROC plot — one curve per offset
    fig, ax = plt.subplots(figsize=(7, 6))
    cmap = plt.colormaps["viridis"]
    for i, offset in enumerate(offsets):
        # Sort by FPR within the offset (smaller n_sigma -> larger FPR -> rightward)
        pts = sorted(
            [(cell_results[(offset, s)][1], cell_results[(offset, s)][0], s) for s in sigmas],
        )
        fprs = [p[0] for p in pts]
        tprs = [p[1] for p in pts]
        n_sigmas_sorted = [p[2] for p in pts]
        color = cmap(i / max(len(offsets) - 1, 1))
        ax.plot(fprs, tprs, "o-", color=color, label=f"offset = {offset:g} V", linewidth=1.5)
        for fpr, tpr, sig in zip(fprs, tprs, n_sigmas_sorted):
            ax.annotate(f"σ={sig:g}", (fpr, tpr), textcoords="offset points",
                        xytext=(5, -10), fontsize=7, color=color)

    # Reference: random-guess diagonal
    ax.plot([0, 1], [0, 1], "k:", alpha=0.4, linewidth=0.8, label="chance")
    ax.set_xlabel("False-positive rate (FPR)")
    ax.set_ylabel("True-positive rate (TPR)")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title(
        f"Study D.3 — AnomalyDetector ROC, {n_trials} trials/cell, "
        f"{len(offsets) * len(sigmas) * n_trials} trials total"
    )
    fig.tight_layout()
    fig_path = fig_dir / "study_D3_dt_sensor_fault.png"
    fig.savefig(fig_path, dpi=140)
    plt.close(fig)
    print(f"Saved figure: {fig_path}")


if __name__ == "__main__":
    main()
