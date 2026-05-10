"""
run_faultloc_phase4_arc_kizilcay.py
======================================

WP4.2 (P4.2) cross-fit experiment: Kizilcay-arc data through the
WP1.4 / WP2.4 single-bin DFT optimiser whose implicit forward model
assumes the Emanuel diode-arc shape from the WP1.1 PSCAD baseline.

For each cell of the WP3.3 IEEE 34 720-grid (10-bus sub-sample for
tractability):

* Synthesise a 1-cycle clean voltage waveform on phase A.
* Generate two current waveforms: one from EmanuelArc (the diode-on-
  diode baseline) and one from KizilcayArc (the dynamic-conductance
  cross-fit).
* For each, compute H_meas via single-bin DFT and run the WP1.4 /
  WP2.4 optimiser.  Record the (alpha_hat, R_x_hat) estimate, the
  J_min, and the per-cell location error vs the cell's
  (alpha_true, R_x_true).
* Compute the Delta-error
  ``loc_err_kizilcay - loc_err_emanuel`` per cell -- the
  arc-model-mismatch contribution to the optimiser's residual.

Output
------

``outputs/phase4_arc_kizilcay_results.csv`` -- per-cell:
  fault_bus, alpha_true, Rx_true, snr_v_db, snr_i_db,
  alpha_hat_emanuel, Rx_hat_emanuel, loc_err_pct_emanuel,
  Rx_err_pct_emanuel,
  alpha_hat_kizilcay, Rx_hat_kizilcay, loc_err_pct_kizilcay,
  Rx_err_pct_kizilcay,
  delta_loc_err_pct, delta_Rx_err_pct.

K07 (Phase 4) status
--------------------

The same R5 / R-WP3.4-1 / R-WP4.1-1 single-bin DFT identifiability
floor that drives the load-dominated IEEE 34 baseline at ~62 % mean
loc-err is in play here.  The cross-fit Delta-error is the
INCREMENTAL contribution from arc-model mismatch on top of that
floor; we expect the absolute loc-err to remain in the same ~62 %
band but the per-cell deltas to be small.  The K07 (Phase 4)
acceptance is therefore xfail-strict (same R-class escalation as
WP4.1); the per-cell delta CSV is the new acceptance evidence.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    H_meas_from_waveforms,
    estimate_alpha_Rx,
)
from sambp_fault_location_id.models.faultloc_arc_models import (
    EmanuelArc,
    KizilcayArc,
)
from scipy.io import loadmat

PROJ_ROOT = Path(__file__).resolve().parent
IEEE34_BUNDLE = PROJ_ROOT / "data" / "ieee34_720.mat"
OUT_CSV = PROJ_ROOT / "outputs" / "phase4_arc_kizilcay_results.csv"

OMEGA = 2.0 * np.pi * 50.0
F0 = 50.0
FS = 10_000.0
N_CYCLES = 1
N_SAMPLES = int(round(N_CYCLES * FS / F0))


def _synth_v(rng: np.random.Generator, snr_v_db: float) -> np.ndarray:
    """Synthesise 1-cycle phase-A voltage waveform at 11 kV peak."""
    V_peak = 11.0e3 * np.sqrt(2.0 / 3.0)
    n = np.arange(N_SAMPLES)
    t = n / FS
    v = V_peak * np.cos(OMEGA * t)
    if np.isfinite(snr_v_db):
        rms = float(np.sqrt(np.mean(v ** 2)))
        sigma = rms * 10.0 ** (-snr_v_db / 20.0)
        v = v + rng.standard_normal(v.shape) * sigma
    return v


def _add_current_noise(
    i: np.ndarray, snr_i_db: float, rng: np.random.Generator,
) -> np.ndarray:
    if not np.isfinite(snr_i_db):
        return i
    rms = float(np.sqrt(np.mean(i ** 2)))
    sigma = rms * 10.0 ** (-snr_i_db / 20.0)
    return i + rng.standard_normal(i.shape) * sigma


def _run_one_cell(
    Rx_true: float,
    snr_v_db: float, snr_i_db: float,
    *,
    rng: np.random.Generator,
    emanuel: EmanuelArc,
    kizilcay: KizilcayArc,
) -> dict:
    t = np.arange(N_SAMPLES) / FS
    v = _synth_v(rng, snr_v_db)

    i_em = emanuel.synthesise_current(t, v, Rx_true)
    i_ki = kizilcay.synthesise_current(t, v, Rx_true)

    i_em = _add_current_noise(i_em, snr_i_db, rng)
    i_ki = _add_current_noise(i_ki, snr_i_db, rng)

    H_em = H_meas_from_waveforms(v, i_em, fs=FS, f0=F0)
    H_ki = H_meas_from_waveforms(v, i_ki, fs=FS, f0=F0)

    opts = {"snr_v_db": snr_v_db, "snr_i_db": snr_i_db, "max_iter": 200}
    try:
        (a_em, R_em), _ = estimate_alpha_Rx(H_em, opts=opts)
    except Exception:
        a_em, R_em = float("nan"), float("nan")
    try:
        (a_ki, R_ki), _ = estimate_alpha_Rx(H_ki, opts=opts)
    except Exception:
        a_ki, R_ki = float("nan"), float("nan")

    return {
        "alpha_hat_emanuel": float(a_em),
        "Rx_hat_emanuel": float(R_em),
        "alpha_hat_kizilcay": float(a_ki),
        "Rx_hat_kizilcay": float(R_ki),
    }


def _err_pct(hat: float, true: float) -> float:
    if true <= 0 or not np.isfinite(hat):
        return float("nan")
    return 100.0 * abs(hat - true) / true


def run(*, n_buses: int = 5, rng_seed: int = 53) -> Path:
    if not IEEE34_BUNDLE.exists():
        raise FileNotFoundError(
            f"{IEEE34_BUNDLE} not present; run "
            f"`python tools/ieee_feeder_surrogate.py --feeder IEEE_34` first."
        )
    bundle = loadmat(str(IEEE34_BUNDLE))
    grid_alpha = bundle["grid_alpha"].squeeze()
    grid_Rx = bundle["grid_Rx"].squeeze()
    grid_SNR_V = bundle["grid_SNR_V"].squeeze()
    grid_SNR_I = bundle["grid_SNR_I"].squeeze()
    grid_fault_bus = bundle["grid_fault_bus"].squeeze()
    fault_bus_strs = [str(b).strip() for b in grid_fault_bus]

    unique_buses = sorted(set(fault_bus_strs))
    if n_buses < len(unique_buses):
        stride = max(1, len(unique_buses) // n_buses)
        chosen = set(unique_buses[::stride][:n_buses])
    else:
        chosen = set(unique_buses)

    selected = [
        k for k in range(len(fault_bus_strs))
        if fault_bus_strs[k] in chosen
        and (grid_SNR_I[k] >= 30.0 or not np.isfinite(grid_SNR_I[k]))
    ]
    print(
        f"WP4.2 cross-fit runner: {len(selected)} cells "
        f"(after sub-sample to {len(chosen)} buses + SNR_I >= 30 dB); "
        f"per cell = 2 arc-model evaluations + 2 optimiser runs"
    )

    emanuel = EmanuelArc(V_kp=2000.0, V_kn=1800.0)
    kizilcay = KizilcayArc()
    rng = np.random.default_rng(rng_seed)

    rows: list[dict] = []
    t0 = time.perf_counter()
    for k_idx, k in enumerate(selected):
        Rx_true = float(grid_Rx[k])
        alpha_true = float(grid_alpha[k])
        snr_v = float(grid_SNR_V[k])
        snr_i = float(grid_SNR_I[k])
        bus = fault_bus_strs[k]
        per = _run_one_cell(
            Rx_true, snr_v, snr_i, rng=rng,
            emanuel=emanuel, kizilcay=kizilcay,
        )
        loc_em = _err_pct(per["alpha_hat_emanuel"], alpha_true)
        Rxe_em = _err_pct(per["Rx_hat_emanuel"], Rx_true)
        loc_ki = _err_pct(per["alpha_hat_kizilcay"], alpha_true)
        Rxe_ki = _err_pct(per["Rx_hat_kizilcay"], Rx_true)
        rows.append({
            "fault_bus": bus,
            "alpha_true": alpha_true,
            "Rx_true": Rx_true,
            "snr_v_db": snr_v,
            "snr_i_db": snr_i,
            "alpha_hat_emanuel": per["alpha_hat_emanuel"],
            "Rx_hat_emanuel": per["Rx_hat_emanuel"],
            "loc_err_pct_emanuel": loc_em,
            "Rx_err_pct_emanuel": Rxe_em,
            "alpha_hat_kizilcay": per["alpha_hat_kizilcay"],
            "Rx_hat_kizilcay": per["Rx_hat_kizilcay"],
            "loc_err_pct_kizilcay": loc_ki,
            "Rx_err_pct_kizilcay": Rxe_ki,
            "delta_loc_err_pct": loc_ki - loc_em,
            "delta_Rx_err_pct": Rxe_ki - Rxe_em,
        })
        if (k_idx + 1) % max(1, len(selected) // 10) == 0:
            elapsed = time.perf_counter() - t0
            eta = elapsed * (len(selected) - k_idx - 1) / max(k_idx + 1, 1)
            print(
                f"  [{k_idx+1}/{len(selected)}] elapsed {elapsed:.0f}s; "
                f"eta {eta:.0f}s"
            )
    print(f"runner done in {time.perf_counter() - t0:.1f}s")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {OUT_CSV} ({len(rows)} rows)")

    loc_em = np.array([
        r["loc_err_pct_emanuel"] for r in rows
        if np.isfinite(r["loc_err_pct_emanuel"])
    ])
    loc_ki = np.array([
        r["loc_err_pct_kizilcay"] for r in rows
        if np.isfinite(r["loc_err_pct_kizilcay"])
    ])
    delta = np.array([
        r["delta_loc_err_pct"] for r in rows
        if np.isfinite(r["delta_loc_err_pct"])
    ])
    print()
    print("=== Cross-fit summary (loc-err %) ===")
    print(f"  Emanuel-on-diode  baseline:  mean={loc_em.mean():.2f}%, "
          f"p95={np.percentile(loc_em, 95):.2f}%")
    print(f"  Kizilcay-on-diode mismatch:  mean={loc_ki.mean():.2f}%, "
          f"p95={np.percentile(loc_ki, 95):.2f}%")
    print(f"  Delta (Kizilcay - Emanuel):  mean={delta.mean():+.2f}%, "
          f"abs.mean={np.abs(delta).mean():.2f}%, "
          f"abs.p95={np.percentile(np.abs(delta), 95):.2f}%")
    return OUT_CSV


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n-buses", type=int, default=5)
    parser.add_argument("--rng-seed", type=int, default=53)
    args = parser.parse_args(argv)
    run(n_buses=args.n_buses, rng_seed=args.rng_seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
