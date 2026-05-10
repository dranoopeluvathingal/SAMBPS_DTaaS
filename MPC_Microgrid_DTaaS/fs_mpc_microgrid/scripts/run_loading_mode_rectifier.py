"""Loading-mode reproduction with the topology-faithful RectifierLoad.

Variant of run_loading_mode.py that swaps the parametric HarmonicLoad
for RectifierLoad — a 6-pulse, 120°-conduction model whose AC-side
currents are produced by selecting which two diodes conduct based on
the instantaneous phase voltages, rather than by injecting prescribed
harmonics.

Key implementation note: RectifierLoad has internal state I_d (the
inductively-smoothed DC-link current) that advances when load.i_l(t, dt=...)
is called with a non-None dt. The standard `Simulator.run()` only calls
`load.i_l(t)` once per outer tick without dt, which (per the
RectifierLoad contract) snaps I_d to its instantaneous target and
defeats the smoothing. This script therefore runs a custom integration
loop that calls `load.i_l(t_sub, dt=T_s/N_sub)` once per plant sub-step,
so I_d evolves at the same rate as the plant integration.

Baseline (HarmonicLoad, run_loading_mode.py): THD i_s ≈ 4.29 %.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Force UTF-8 stdout on Windows so unit symbols don't crash cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fs_mpc_mg.plant import Plant, PlantParams
from fs_mpc_mg.rectifier_load import RectifierLoad, RectifierLoadParams
from fs_mpc_mg.pll import IdealPLL
from fs_mpc_mg.inner_fsmpc import FSMPCController, FSMPCParams
from fs_mpc_mg.outer_energy_pi import EnergyPI, EnergyPIParams


BASELINE_THD_IS_PCT = 4.29   # HarmonicLoad result from run_loading_mode.py


def thd(signal: np.ndarray, fs: float, f_fund: float, n_harmonics: int = 50) -> float:
    """THD as a fraction (0.05 = 5 %) on a single-phase steady-state tail."""
    N = len(signal)
    n_keep = min(int(5.0 * fs / f_fund), N)
    sig = signal[-n_keep:] - np.mean(signal[-n_keep:])
    spectrum = np.abs(np.fft.rfft(sig))

    def amp_at(f: float) -> float:
        idx = int(round(f * len(sig) / fs))
        return spectrum[idx] if 0 <= idx < len(spectrum) else 0.0

    fund = amp_at(f_fund)
    if fund < 1e-9:
        return float("nan")
    harm_sq = sum(amp_at(k * f_fund) ** 2 for k in range(2, n_harmonics + 1))
    return float(np.sqrt(harm_sq) / fund)


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Plant + controllers — same as run_loading_mode.py via scenarios.loading_mode
    plant_p = PlantParams()
    inner = FSMPCController(FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=20e-6,
                                         use_delay_compensation=True))
    outer = EnergyPI(EnergyPIParams(C=plant_p.C, R=plant_p.R, v_dc_ref=plant_p.v_dc_init))
    pll = IdealPLL(f_grid=plant_p.f_grid)
    plant = Plant(plant_p)

    # NEW: rectifier load (topology-faithful 120°-conduction model).
    load = RectifierLoad(RectifierLoadParams(P_dc_demand=25e3))

    # Sim parameters
    T_s = inner.p.T_s          # 20 µs
    N_sub = 5
    dt_sub = T_s / N_sub       # 4 µs — also passed to load.i_l for I_d update
    t_end = 80e-3              # 4 cycles at 50 Hz
    N_steps = int(round(t_end / T_s))
    i_dc = -80.0               # loading mode: DC link sources 80 A

    # Storage
    t_hist = np.zeros(N_steps)
    v_s_hist = np.zeros((N_steps, 3))
    i_l_hist = np.zeros((N_steps, 3))
    i_m_hist = np.zeros((N_steps, 3))
    v_dc_hist = np.zeros(N_steps)
    s_hist = np.zeros((N_steps, 3))
    I_s_amp_hist = np.zeros(N_steps)

    # Initial state
    s_apply = np.zeros(3)
    I_s_amp = 0.0

    for k in range(N_steps):
        t = k * T_s

        # Measurements at t. The first sub-step's load call advances I_d
        # by dt_sub; subsequent sub-step calls inside the plant loop
        # advance it by another (N_sub - 1) * dt_sub, totalling T_s per
        # outer tick — same effective rate as the wall-clock simulation.
        v_s = load.v_s(t)
        i_l = load.i_l(t, dt=dt_sub)
        i_m = plant.i_m.copy()
        v_dc = plant.v_dc

        # Outer + PLL + FS-MPC
        I_s_amp = outer.update(v_dc, dt=T_s)
        _, _, unit_next = pll.update(t + T_s)
        i_s_ref = I_s_amp * unit_next
        s_apply = inner.update(i_m, v_dc, v_s, i_s_ref, i_l)

        # Plant integration over N_sub sub-steps. We also call load.i_l
        # at every sub-step to keep I_d advancing in lockstep with the
        # plant — the plant ODE itself doesn't take i_l, so the returned
        # value is unused; only the side-effect on I_d matters.
        for j in range(N_sub):
            t_sub = t + j * dt_sub
            v_s_sub = load.v_s(t_sub)
            if j > 0:
                load.i_l(t_sub, dt=dt_sub)
            plant.step(s_apply, v_s_sub, i_dc=i_dc, dt=dt_sub)

        # Log
        t_hist[k] = t
        v_s_hist[k] = v_s
        i_l_hist[k] = i_l
        i_m_hist[k] = i_m
        v_dc_hist[k] = v_dc
        s_hist[k] = s_apply
        I_s_amp_hist[k] = I_s_amp

    i_s_hist = i_m_hist + i_l_hist

    # THD
    fs = 1.0 / T_s
    f_grid = load.p.f_grid
    thd_is = thd(i_s_hist[:, 0], fs=fs, f_fund=f_grid)
    thd_il = thd(i_l_hist[:, 0], fs=fs, f_fund=f_grid)

    delta_pp = 100.0 * thd_is - BASELINE_THD_IS_PCT

    # Console
    print(f"THD i_s (phase a) = {100 * thd_is:5.2f} %    "
          f"baseline (HarmonicLoad) = {BASELINE_THD_IS_PCT:.2f} %    "
          f"Δ = {delta_pp:+.2f} pp")
    print(f"THD i_l (phase a) = {100 * thd_il:5.2f} %    "
          f"(rectifier reference; HarmonicLoad baseline ≈ 27.31 %)")
    print(f"v_dc final        = {v_dc_hist[-1]:7.2f} V (target 900 V)")
    print(f"I_d final         = {load.I_d:.2f} A (target {load._target_I_d():.2f} A)")

    if abs(delta_pp) > 2.0:
        print()
        print(f"** THD differs from baseline by {abs(delta_pp):.2f} pp (> 2 pp threshold) **")
        print("Diagnostic checks (run mentally / via figure):")
        print("  1. Phase relationship — RectifierLoad's 120°-pulse-train phase is")
        print("     locked to v_s_a's zero crossings; HarmonicLoad uses textbook")
        print("     negative/positive-sequence orderings. If the harmonic phases")
        print("     don't align, FS-MPC's compensation reference is the same but")
        print("     the residual on i_s differs.")
        print("  2. Edge-softening artefact — RectifierLoadParams.edge_softening_rad")
        print(f"     is {load.p.edge_softening_rad:.3f} rad ≈ {np.degrees(load.p.edge_softening_rad):.1f}°.")
        print("     Softer edges suppress high-order harmonics (29th, 31st...)")
        print("     that the FS-MPC's H_mask is NOT compensating, so they leak")
        print("     through to i_s. Setting eps=0 would reproduce the canonical")
        print("     1/h spectrum but adds simulation ringing.")
        print("  3. I_d transient — smoothing_tau_s = 5 ms means I_d settles in")
        print(f"     ~{5 * load.p.smoothing_tau_s * 1e3:.0f} ms; the THD window covers the last ~80 ms")
        print("     so settling shouldn't dominate, but the early cycles bias the")
        print("     average if the FFT window includes them.")

    # Plot — same 4-panel layout as run_loading_mode.py
    fig, axes = plt.subplots(4, 1, figsize=(9, 9), sharex=True)

    ax = axes[0]
    ax.plot(t_hist * 1e3, v_s_hist[:, 0], label="v_s,a", color="C0", linewidth=0.8)
    ax.set_ylabel("Grid voltage (V)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(t_hist * 1e3, i_s_hist[:, 0], label="i_s,a (PCC)", color="C2", linewidth=0.8)
    ax.set_ylabel("System current (A)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)
    ax.text(
        0.02, 0.95,
        f"THD i_s = {100 * thd_is:.2f} %  (baseline {BASELINE_THD_IS_PCT:.2f} %, Δ {delta_pp:+.2f} pp)",
        transform=ax.transAxes, va="top", fontsize=9, color="C2",
    )

    ax = axes[2]
    ax.plot(t_hist * 1e3, i_m_hist[:, 0], label="i_m,a (converter)", color="C3", linewidth=0.8)
    ax.plot(t_hist * 1e3, i_l_hist[:, 0], label="i_l,a (rectifier)", color="C1", linewidth=0.8, alpha=0.7)
    ax.set_ylabel("Currents (A)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)
    ax.text(
        0.02, 0.95, f"THD i_l = {100 * thd_il:.2f} %",
        transform=ax.transAxes, va="top", fontsize=9, color="C1",
    )

    ax = axes[3]
    ax.plot(t_hist * 1e3, v_dc_hist, label="v_dc", color="C4", linewidth=1.0)
    ax.axhline(900.0, color="k", linestyle="--", alpha=0.5, label="v_dc_ref")
    ax.set_ylabel("DC-link voltage (V)")
    ax.set_xlabel("time (ms)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)

    fig.suptitle(
        "Loading mode — RectifierLoad (6-pulse, 120° conduction) "
        "vs HarmonicLoad parametric baseline"
    )
    fig.tight_layout()

    out_file = out_dir / "loading_mode_rectifier.png"
    fig.savefig(out_file, dpi=140)
    plt.close(fig)
    print(f"Saved: {out_file}")


if __name__ == "__main__":
    main()
