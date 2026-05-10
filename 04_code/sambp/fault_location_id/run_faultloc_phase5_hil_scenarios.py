"""
run_faultloc_phase5_hil_scenarios.py
======================================

WP5.3 (P5.3) HIL scenario campaign — **dev-box simulation mode**.

This runner ships the 25 + 5 scenario test campaign on the
dev-box mock SV pipeline (SVSubscriber dev-box mode + Wang-2020 /
Torres-2022 arc stimulus + IEEE 34 single-section forward model).
The hardware-side equivalent (real IED + real Merging Unit + SV
capture) is gated on the WP5.1 partner-window confirmation; this
runner produces the CSV + diagnostic plots that the HIL site will
re-run end-to-end.

Scenario design
---------------

Per the WP5.3 brief:

* **Primary 25**: 5 fault locations × 5 R_x values × 1 fault-type
  (SLG) × 1 arc profile (Wang-2020 default).
* **Cross-arc subset 5**: re-run 5 of the primary cells with the
  Torres-2022 ``tree`` profile to demonstrate cross-arc robustness.

Both subsets generate the *same* (alpha_true, R_x_true) injection
through the SVSubscriber + WP1.4 single-bin DFT optimiser
pipeline; the only difference is the arc stimulus.

Outputs
-------

* ``outputs/phase5_hil_scenario_results.csv`` — per-scenario row
  with (scenario_id, alpha_true, Rx_true, arc_profile,
  alpha_est, Rx_est, loc_err_pct, Rx_err_pct, latency_ms).
* ``outputs/phase5_figs/scenario_NN_*.pdf`` — per-scenario
  diagnostic plot (V/I waveform + estimated alpha vs cycle index).
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from sambp_fault_location_id.dtaas.protection_validation.sv_subscriber import (
    SAMPLES_PER_CYCLE,
    SV_RATE_HZ,
    SVSubscriber,
)
from sambp_fault_location_id.models.faultloc_arc_models import (
    EmanuelArc,
    Torres2022Arc,
    Wang2020Arc,
)

PROJ_ROOT = Path(__file__).resolve().parent
OUT_CSV = PROJ_ROOT / "outputs" / "phase5_hil_scenario_results.csv"
OUT_FIG_DIR = PROJ_ROOT / "outputs" / "phase5_figs"

F0_HZ = 50.0
N_CYCLES = 5
N_SAMPLES = N_CYCLES * SAMPLES_PER_CYCLE   # 5 × 96 = 480 samples


PRIMARY_ALPHAS = (0.1, 0.3, 0.5, 0.7, 0.9)
PRIMARY_RX = (200.0, 500.0, 1000.0, 2000.0, 5000.0)
TORRES_SUBSET_INDICES = (0, 6, 12, 18, 24)   # 5 of 25 primary cells


def _build_scenarios():
    """Build the 25 + 5 scenario list."""
    rows = []
    sid = 1
    for alpha in PRIMARY_ALPHAS:
        for Rx in PRIMARY_RX:
            rows.append({
                "scenario_id": sid,
                "alpha_true": alpha,
                "Rx_true": Rx,
                "fault_type": "SLG",
                "arc_profile": "wang2020_default",
            })
            sid += 1
    # Torres subset: 5 cells re-run with Torres tree
    primary_25 = list(rows)
    for k in TORRES_SUBSET_INDICES:
        cell = primary_25[k]
        rows.append({
            "scenario_id": sid,
            "alpha_true": cell["alpha_true"],
            "Rx_true": cell["Rx_true"],
            "fault_type": "SLG",
            "arc_profile": "torres_tree",
        })
        sid += 1
    return rows


def _generate_sv_stream(arc, Rx: float, snr_i_db: float = 40.0):
    """Generate (V_abc, I_abc) sample tuples at SV rate."""
    t = np.arange(N_SAMPLES) / SV_RATE_HZ
    V_peak = 11.0e3 * np.sqrt(2.0 / 3.0)
    omega = 2.0 * np.pi * F0_HZ
    v_a = V_peak * np.cos(omega * t)
    v_b = V_peak * np.cos(omega * t - 2.0 * np.pi / 3.0)
    v_c = V_peak * np.cos(omega * t + 2.0 * np.pi / 3.0)
    i_a = arc.synthesise_current(t, v_a, Rx)
    i_b = arc.synthesise_current(t, v_b, Rx)
    i_c = arc.synthesise_current(t, v_c, Rx)
    rms = float(np.sqrt(np.mean(i_a ** 2)))
    rng = np.random.default_rng(42)
    sigma = rms * 10.0 ** (-snr_i_db / 20.0)
    i_a = i_a + rng.standard_normal(N_SAMPLES) * sigma
    i_b = i_b + rng.standard_normal(N_SAMPLES) * sigma
    i_c = i_c + rng.standard_normal(N_SAMPLES) * sigma
    v_stream = [np.array([v_a[k], v_b[k], v_c[k]]) for k in range(N_SAMPLES)]
    i_stream = [np.array([i_a[k], i_b[k], i_c[k]]) for k in range(N_SAMPLES)]
    return v_stream, i_stream, t, np.column_stack([v_a, v_b, v_c]), np.column_stack([i_a, i_b, i_c])


def _arc_for_scenario(profile: str) -> EmanuelArc | Wang2020Arc | Torres2022Arc:
    em = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    if profile == "wang2020_default":
        return Wang2020Arc(distortion_index=0.5, emanuel=em,
                           rng=np.random.default_rng(101))
    if profile == "torres_tree":
        return Torres2022Arc(profile="tree", emanuel=em,
                             rng=np.random.default_rng(202))
    raise ValueError(f"unknown arc profile {profile!r}")


def _emit_diagnostic_plot(
    scenario_id: int,
    arc_profile: str,
    alpha_true: float,
    Rx_true: float,
    t: np.ndarray,
    v_abc: np.ndarray,
    i_abc: np.ndarray,
    estimates: list,
) -> Path | None:
    """Two-panel diagnostic plot: V/I phase-A waveform + per-cycle
    alpha-hat vs alpha_true."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"matplotlib not available; skipping plot: {exc}")
        return None

    OUT_FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, axs = plt.subplots(2, 1, figsize=(8, 5.5), sharex=False)
    ax_wf, ax_alpha = axs
    ax_wf2 = ax_wf.twinx()
    ax_wf.plot(t * 1000, v_abc[:, 0] / 1000.0, "C0-", lw=0.8, label="V_a (kV)")
    ax_wf2.plot(t * 1000, i_abc[:, 0], "C1-", lw=0.8, label="I_a (A)")
    ax_wf.set_xlabel("time (ms)")
    ax_wf.set_ylabel("V_a (kV)", color="C0")
    ax_wf2.set_ylabel("I_a (A)", color="C1")
    ax_wf.set_title(
        f"Scenario {scenario_id:02d} ({arc_profile}) — "
        f"alpha_true={alpha_true:.2f}, R_x_true={Rx_true:.0f} Ω"
    )
    ax_wf.grid(alpha=0.3)

    if estimates:
        cycle_idx = [e.cycle_index for e in estimates]
        alpha_hat = [e.alpha_pu for e in estimates]
        ax_alpha.plot(cycle_idx, alpha_hat, "C2o-", lw=1.0, ms=4,
                      label=r"$\hat\alpha$ per cycle")
        ax_alpha.axhline(alpha_true, color="C3", ls="--",
                         label=r"$\alpha_\mathrm{true}$")
    ax_alpha.set_xlabel("cycle index")
    ax_alpha.set_ylabel(r"$\alpha$ (pu)")
    ax_alpha.set_ylim(-0.1, 1.1)
    ax_alpha.legend(fontsize=8, loc="upper right")
    ax_alpha.grid(alpha=0.3)

    fig.tight_layout()
    out = OUT_FIG_DIR / f"scenario_{scenario_id:02d}_{arc_profile}.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def run() -> int:
    scenarios = _build_scenarios()
    print(
        f"WP5.3 simulation campaign: {len(scenarios)} scenarios "
        f"(25 primary Wang2020 + 5 Torres tree)"
    )
    rows = []
    t0 = time.perf_counter()
    for sc in scenarios:
        arc = _arc_for_scenario(sc["arc_profile"])
        v_stream, i_stream, t_axis, v_abc, i_abc = _generate_sv_stream(
            arc, sc["Rx_true"],
        )
        sub = SVSubscriber(ied_iec61850=False, estimator="dft")
        estimates = sub.feed(v_stream, i_stream)
        if not estimates:
            row = {
                **sc,
                "alpha_est": float("nan"),
                "Rx_est": float("nan"),
                "loc_err_pct": float("nan"),
                "Rx_err_pct": float("nan"),
                "latency_ms_max": float("nan"),
                "latency_ms_mean": float("nan"),
                "n_cycles": 0,
            }
            rows.append(row)
            continue
        last = estimates[-1]
        loc_err_pct = (
            100.0 * abs(last.alpha_pu - sc["alpha_true"]) / max(sc["alpha_true"], 1e-9)
            if np.isfinite(last.alpha_pu) else float("nan")
        )
        Rx_err_pct = (
            100.0 * abs(last.Rx_ohm - sc["Rx_true"]) / max(sc["Rx_true"], 1e-9)
            if np.isfinite(last.Rx_ohm) else float("nan")
        )
        max_lat_ms = max(e.sv_to_estimate_us / 1000.0 for e in estimates)
        mean_lat_ms = float(np.mean([
            e.sv_to_estimate_us / 1000.0 for e in estimates
        ]))
        row = {
            **sc,
            "alpha_est": float(last.alpha_pu),
            "Rx_est": float(last.Rx_ohm),
            "loc_err_pct": float(loc_err_pct),
            "Rx_err_pct": float(Rx_err_pct),
            "latency_ms_max": float(max_lat_ms),
            "latency_ms_mean": mean_lat_ms,
            "n_cycles": len(estimates),
        }
        rows.append(row)
        _emit_diagnostic_plot(
            sc["scenario_id"], sc["arc_profile"],
            sc["alpha_true"], sc["Rx_true"],
            t_axis, v_abc, i_abc, estimates,
        )
        print(
            f"  scenario {sc['scenario_id']:2d}  "
            f"{sc['arc_profile']:18s}  alpha_true={sc['alpha_true']:.2f}  "
            f"R_x_true={sc['Rx_true']:6.0f} -> "
            f"alpha_hat={last.alpha_pu:.3f}  "
            f"loc_err={loc_err_pct:.2f}%  "
            f"max_lat={max_lat_ms:.1f}ms"
        )
    print(f"runner done in {time.perf_counter() - t0:.1f}s")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {OUT_CSV} ({len(rows)} rows)")

    primary = [r for r in rows if r["arc_profile"] == "wang2020_default"]
    torres = [r for r in rows if r["arc_profile"] == "torres_tree"]
    loc_p = np.array([r["loc_err_pct"] for r in primary
                      if np.isfinite(r["loc_err_pct"])])
    loc_t = np.array([r["loc_err_pct"] for r in torres
                      if np.isfinite(r["loc_err_pct"])])
    print()
    print("=== WP5.3 simulation campaign summary ===")
    print(
        f"  Wang2020 (n={len(loc_p)})  mean loc-err={loc_p.mean():.2f}%  "
        f"p95={np.percentile(loc_p, 95):.2f}%"
    )
    if len(loc_t):
        print(
            f"  Torres   (n={len(loc_t)})  mean loc-err={loc_t.mean():.2f}%  "
            f"p95={np.percentile(loc_t, 95):.2f}%"
        )
    print(
        "Note: SIMULATION ONLY — HIL CAMPAIGN PENDING per WP5.1 "
        "partner-window confirmation."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.parse_args(argv)
    return run()


if __name__ == "__main__":
    sys.exit(main())
