"""ICA agent end-to-end demo with InMemoryPubSub (no broker needed).

Simulates a centralized controller that:
  1. Starts the agent already running and enabled (no idle phase to keep the
     unswitched dynamics physical).
  2. Drops v_dc_ref from 900 V to 880 V at 30 ms.
  3. Requests 5 kVAr reactive support at 50 ms.
  4. Disables the agent at 70 ms (gate-block, switching freezes).

The demo prints pub/sub message counts and saves figures/ica_agent_demo.png.
"""

from __future__ import annotations

from pathlib import Path
import sys
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fs_mpc_mg import (
    Plant, PlantParams, HarmonicLoad, HarmonicLoadParams,
    IdealPLL, FSMPCController, FSMPCParams, EnergyPI, EnergyPIParams,
)
from fs_mpc_mg.ica_agent import ICAAgent
from fs_mpc_mg.comm.pubsub import InMemoryPubSub
from fs_mpc_mg.comm.topics import topic_ref


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    plant = Plant(PlantParams())
    load  = HarmonicLoad(HarmonicLoadParams(P_fund=25e3, Q_fund=0.0))
    inner = FSMPCController(FSMPCParams(L=plant.p.L, r=plant.p.r, T_s=20e-6))
    outer = EnergyPI(EnergyPIParams(C=plant.p.C, R=plant.p.R, v_dc_ref=plant.p.v_dc_init))
    pll   = IdealPLL(f_grid=plant.p.f_grid)
    ps    = InMemoryPubSub()
    agent = ICAAgent("ica1", inner, outer, pll, ps, telemetry_decim=10)

    # Mock CMC events. Agent starts running/enabled by default.
    cmc_events = [
        (30e-3, "v_dc_ref", 880.0),
        (50e-3, "Q_ref",    5_000.0),
    ]

    T_s = inner.p.T_s
    t_end = 80e-3
    N_steps = int(round(t_end / T_s))
    N_sub = 5
    i_dc_load = -80.0  # negative = loading (matches plant sign convention)

    log_t = np.zeros(N_steps)
    log_v_dc = np.zeros(N_steps)
    log_i_s = np.zeros((N_steps, 3))
    log_i_m = np.zeros((N_steps, 3))
    log_i_l = np.zeros((N_steps, 3))
    log_v_s = np.zeros((N_steps, 3))
    log_I_s_amp = np.zeros(N_steps)

    cmc_iter = iter(cmc_events)
    next_event = next(cmc_iter, None)

    for k in range(N_steps):
        t = k * T_s
        while next_event is not None and t + 1e-12 >= next_event[0]:
            _, key, value = next_event
            ps.publish_value(topic_ref("ica1", key), value)
            next_event = next(cmc_iter, None)

        v_s = load.v_s(t)
        i_l = load.i_l(t)
        s = agent.step(t, plant.i_m, plant.v_dc, v_s, i_l)
        for _ in range(N_sub):
            plant.step(s, v_s, i_dc=i_dc_load, dt=T_s / N_sub)

        log_t[k] = t
        log_v_dc[k] = plant.v_dc
        log_i_m[k] = plant.i_m
        log_i_l[k] = i_l
        log_v_s[k] = v_s
        log_i_s[k] = plant.i_m + i_l
        latest = ps.latest("/ica/ica1/tel/I_s_amp")
        log_I_s_amp[k] = latest["value"] if latest else 0.0

    n_msgs = len(ps.history())
    n_tel = len(ps.history("/ica/ica1/tel/"))
    n_ref = len(ps.history("/ica/ica1/refs/"))
    print(f"Total pubsub messages: {n_msgs}  (refs: {n_ref}, telemetry: {n_tel})")
    print(f"Final v_dc = {plant.v_dc:.2f} V (last v_dc_ref = {agent.state.v_dc_ref:.0f})")
    print(f"Final mode = {agent.state.mode!r}, enabled = {agent.state.enabled}")
    print(f"Final Q_ref = {agent.state.Q_ref:.0f} VAr")

    fig, axes = plt.subplots(4, 1, figsize=(9, 9), sharex=True)

    ax = axes[0]
    ax.plot(log_t * 1e3, log_v_s[:, 0], label="v_s,a", color="C0", linewidth=0.8)
    ax.set_ylabel("Grid voltage (V)")
    ax.legend(loc="upper right"); ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(log_t * 1e3, log_i_s[:, 0], label="i_s,a (PCC)", color="C2", linewidth=0.8)
    ax.plot(log_t * 1e3, log_i_l[:, 0], label="i_l,a (load)", color="C1", linewidth=0.7, alpha=0.7)
    ax.set_ylabel("Currents (A)")
    ax.legend(loc="upper right"); ax.grid(alpha=0.3)

    ax = axes[2]
    ax.plot(log_t * 1e3, log_v_dc, label="v_dc", color="C4", linewidth=1.0)
    for et, key, val in cmc_events:
        if key == "v_dc_ref":
            ax.axhline(val, color="gray", linestyle=":", alpha=0.6)
            ax.axvline(et * 1e3, color="gray", linestyle=":", alpha=0.6)
    ax.axhline(900.0, color="gray", linestyle=":", alpha=0.4)
    ax.set_ylabel("DC-link voltage (V)")
    ax.legend(loc="lower right"); ax.grid(alpha=0.3)

    ax = axes[3]
    ax.plot(log_t * 1e3, log_I_s_amp, label="I_s_amp (telemetry)", color="C5", linewidth=0.9)
    for et, key, _val in cmc_events:
        ax.axvline(et * 1e3, color="C7", linestyle="--", alpha=0.4)
        ax.text(et * 1e3 + 0.3, ax.get_ylim()[1] * 0.85 if ax.get_ylim()[1] > 0 else 1,
                key, rotation=90, fontsize=7, color="C7")
    ax.set_ylabel("I_s_amp (A)")
    ax.set_xlabel("time (ms)")
    ax.legend(loc="upper right"); ax.grid(alpha=0.3)

    fig.suptitle("ICA Agent demo — InMemory CMC drives v_dc_ref (30 ms) and Q_ref (50 ms)")
    fig.tight_layout()
    out_file = out_dir / "ica_agent_demo.png"
    fig.savefig(out_file, dpi=140)
    plt.close(fig)
    print(f"Saved: {out_file}")


if __name__ == "__main__":
    main()
