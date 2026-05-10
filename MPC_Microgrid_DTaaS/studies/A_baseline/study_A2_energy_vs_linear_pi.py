"""Study A.2 — EnergyPI vs LinearVdcPI in loading mode (i_dc = -80 A).

Per docs/FS_MPC_Simulation_Studies_Plan.pdf §2 (study A.2). Compares two
DC-link voltage controllers under the same loading-mode disturbance:

  - EnergyPI: PI on capacitor energy E_c. Plant is globally linear in I_s
    so the controller works at any operating point without re-tuning.
  - LinearVdcPI: PI on v_dc directly, gains placed against the small-signal
    plant linearised around v_dc_ref = 900 V. Works near the linearisation
    point; degrades elsewhere.

Outputs:
  - figures/study_A2_energy_vs_linear_pi.png  (4-panel side-by-side)
  - tables/study_A2.csv                       (metrics summary)
  - stdout                                    (overshoot / settling / RMS error)
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Force UTF-8 stdout on Windows so Greek / unit symbols don't crash cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fs_mpc_mg.plant import Plant, PlantParams
from fs_mpc_mg.load_model import HarmonicLoad, HarmonicLoadParams
from fs_mpc_mg.pll import IdealPLL
from fs_mpc_mg.inner_fsmpc import FSMPCController, FSMPCParams
from fs_mpc_mg.simulator import Simulator, SimResult
from fs_mpc_mg.outer_energy_pi import EnergyPI, EnergyPIParams
from fs_mpc_mg.outer_linear_pi import LinearVdcPI, LinearVdcPIParams


V_DC_REF = 900.0
I_DC_LOAD = -80.0
T_END = 80e-3


def build_simulator(outer) -> Simulator:
    """Mirror of scenarios._build_simulator with a configurable outer loop.

    Loading mode: i_dc(t) = -80 A constant from t = 0.
    """
    plant_p = PlantParams()
    inner_p = FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=20e-6, use_delay_compensation=True)
    return Simulator(
        plant=Plant(plant_p),
        load=HarmonicLoad(HarmonicLoadParams(P_fund=25e3, Q_fund=0.0)),
        pll=IdealPLL(f_grid=plant_p.f_grid),
        inner=FSMPCController(inner_p),
        outer=outer,  # duck-typed: Simulator only invokes outer.update(v_dc, dt)
        i_dc_func=lambda _t: I_DC_LOAD,
        N_sub=5,
    )


def metrics(res: SimResult, v_ref: float = V_DC_REF) -> dict[str, float]:
    """Compute overshoot, 1% settling time, and RMS tracking error."""
    err = res.v_dc - v_ref
    overshoot_above = float(max(0.0, np.max(res.v_dc) - v_ref))
    max_deviation = float(np.max(np.abs(err)))

    # 1% settling time: smallest t such that |err(t)|/v_ref < 0.01 from t to end.
    threshold = 0.01 * v_ref
    in_band = np.abs(err) < threshold
    if not in_band.any():
        settle_t = float("nan")
    else:
        # Find the largest contiguous out-of-band region; settling is right after it.
        out_indices = np.where(~in_band)[0]
        if out_indices.size == 0:
            settle_t = 0.0
        else:
            last_out = int(out_indices[-1])
            if last_out + 1 < len(res.t):
                settle_t = float(res.t[last_out + 1])
            else:
                settle_t = float("nan")  # never settled in window

    rms_err = float(np.sqrt(np.mean(err ** 2)))

    return {
        "overshoot_above_V": overshoot_above,
        "max_deviation_V": max_deviation,
        "settling_time_1pct_ms": settle_t * 1e3 if np.isfinite(settle_t) else float("nan"),
        "rms_error_V": rms_err,
        "v_dc_final_V": float(res.v_dc[-1]),
    }


def main() -> None:
    here = Path(__file__).resolve()
    repo_root = here.parents[2]  # studies/A_baseline/file -> repo root
    fig_dir = repo_root / "fs_mpc_microgrid" / "figures"
    tab_dir = repo_root / "fs_mpc_microgrid" / "tables"
    fig_dir.mkdir(parents=True, exist_ok=True)
    tab_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Run both simulations
    e_pi = EnergyPI(EnergyPIParams())
    l_pi = LinearVdcPI(LinearVdcPIParams())

    print(f"[A.2] Loading mode, i_dc = {I_DC_LOAD} A, t_end = {T_END * 1e3:.0f} ms")
    print(f"  EnergyPI    gains: Kp={e_pi.K_p:.4g}  Ki={e_pi.K_i:.4g}")
    print(f"  LinearVdcPI gains: Kp={l_pi.K_p:.4g}  Ki={l_pi.K_i:.4g}")

    print("\nRunning EnergyPI simulation...")
    sim_e = build_simulator(e_pi)
    res_e = sim_e.run(t_end=T_END)
    m_e = metrics(res_e)

    print("Running LinearVdcPI simulation...")
    sim_l = build_simulator(l_pi)
    res_l = sim_l.run(t_end=T_END)
    m_l = metrics(res_l)

    # ------------------------------------------------------------------
    # Print metrics table
    print("\n" + "=" * 72)
    print(f"{'Metric':<28} {'EnergyPI':>14} {'LinearVdcPI':>14} {'ratio':>10}")
    print("-" * 72)
    for key in m_e:
        ratio = (
            m_e[key] / m_l[key]
            if m_l[key] not in (0, float("nan")) and np.isfinite(m_l[key])
            else float("nan")
        )
        print(f"{key:<28} {m_e[key]:>14.4f} {m_l[key]:>14.4f} {ratio:>10.4f}")
    print("=" * 72)

    # ------------------------------------------------------------------
    # CSV
    csv_path = tab_dir / "study_A2.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "EnergyPI", "LinearVdcPI"])
        for key in m_e:
            w.writerow([key, f"{m_e[key]:.6g}", f"{m_l[key]:.6g}"])
        # Also dump the controller gains so the file is self-describing
        w.writerow([])
        w.writerow(["gain", "EnergyPI", "LinearVdcPI"])
        w.writerow(["Kp", f"{e_pi.K_p:.6g}", f"{l_pi.K_p:.6g}"])
        w.writerow(["Ki", f"{e_pi.K_i:.6g}", f"{l_pi.K_i:.6g}"])
    print(f"\nSaved metrics: {csv_path}")

    # ------------------------------------------------------------------
    # Figure: 4 panels side-by-side
    fig, axes = plt.subplots(4, 1, figsize=(10, 11), sharex=True)

    ax = axes[0]
    ax.plot(res_e.t * 1e3, res_e.v_dc, label="EnergyPI", color="C0", linewidth=1.0)
    ax.plot(res_l.t * 1e3, res_l.v_dc, label="LinearVdcPI", color="C3", linewidth=1.0)
    ax.axhline(V_DC_REF, color="k", linestyle="--", alpha=0.5, label="v_dc_ref")
    ax.set_ylabel("v_dc (V)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(res_e.t * 1e3, res_e.i_s[:, 0], label="EnergyPI i_s,a", color="C0", linewidth=0.7)
    ax.plot(res_l.t * 1e3, res_l.i_s[:, 0], label="LinearVdcPI i_s,a", color="C3", linewidth=0.7, alpha=0.8)
    ax.set_ylabel("i_s,a (A)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)

    ax = axes[2]
    ax.plot(res_e.t * 1e3, res_e.v_dc - V_DC_REF, label="EnergyPI", color="C0", linewidth=1.0)
    ax.plot(res_l.t * 1e3, res_l.v_dc - V_DC_REF, label="LinearVdcPI", color="C3", linewidth=1.0)
    ax.axhline(0.0, color="k", linestyle="--", alpha=0.5)
    ax.set_ylabel("error v_dc - v_dc_ref (V)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)

    ax = axes[3]
    ax.axis("off")
    text_lines = [
        "Controller gains (matched closed-loop bandwidth at v_dc_ref = 900 V):",
        f"  EnergyPI:    K_p = {e_pi.K_p:.4g} A/J,  K_i = {e_pi.K_i:.4g} A/(J·s)",
        f"  LinearVdcPI: K_p = {l_pi.K_p:.4g} A/V,  K_i = {l_pi.K_i:.4g} A/(V·s)",
        f"  Ratio (LinearVdcPI / EnergyPI) = C·v_dc_ref = {e_pi.p.C * e_pi.p.v_dc_ref:.4g}",
        "",
        f"Metrics (i_dc = -80 A, t_end = {T_END * 1e3:.0f} ms):",
        f"  Overshoot above ref:     E={m_e['overshoot_above_V']:.2f} V    L={m_l['overshoot_above_V']:.2f} V",
        f"  Max |v_dc - v_ref|:      E={m_e['max_deviation_V']:.2f} V    L={m_l['max_deviation_V']:.2f} V",
        f"  1%-settling time:        E={m_e['settling_time_1pct_ms']:.2f} ms   L={m_l['settling_time_1pct_ms']:.2f} ms",
        f"  RMS error over window:   E={m_e['rms_error_V']:.2f} V    L={m_l['rms_error_V']:.2f} V",
    ]
    ax.text(0.02, 0.98, "\n".join(text_lines), transform=ax.transAxes,
            va="top", ha="left", fontsize=9, family="monospace")

    fig.suptitle("Study A.2 — EnergyPI vs LinearVdcPI (loading mode, i_dc = -80 A)")
    fig.tight_layout()

    fig_path = fig_dir / "study_A2_energy_vs_linear_pi.png"
    fig.savefig(fig_path, dpi=140)
    plt.close(fig)
    print(f"Saved figure:  {fig_path}")


if __name__ == "__main__":
    main()
