"""4-ICA fleet demo with the centralized microgrid controller.

Demonstrates the full Layer-1 + Layer-2 stack:
  - 4 ICAAgents, each driving its own Plant
  - 1 Controller dispatching v_dc_ref, mode, enable, Q_ref, H_mask
  - 1 shared HarmonicLoad providing the load current (the same i_l fed to
    every ICA — emulates them sharing a PCC and seeing identical local
    measurements; a richer harness would use a PCC-aware load partition)
  - 1 InMemoryPubSub broker (no MQTT needed)

The CMC issues a Q_total_target = 5 kVAr at t = 25 ms and a v_dc_ref step
to 880 V at t = 50 ms. The script prints aggregate metrics and saves
figures/fleet_demo.png.

Run:
    python scripts/run_fleet_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fs_mpc_mg import (
    Plant, PlantParams, HarmonicLoad, HarmonicLoadParams,
    IdealPLL, FSMPCController, FSMPCParams, EnergyPI, EnergyPIParams,
    ICAAgent,
)
from fs_mpc_mg.comm.pubsub import InMemoryPubSub
from fs_mpc_mg.cmc import (
    Topology, BusNode, ICANode, LoadNode, Controller, ControllerConfig,
)
from fs_mpc_mg.cmc.topology import SwitchEdge


N_ICAS = 4


def _build_topology() -> Topology:
    t = Topology()
    t.add_bus(BusNode("grid", is_grid=True))
    t.add_bus(BusNode("pcc"))
    t.add_switch(SwitchEdge("tie", "grid", "pcc", closed=True))
    for k in range(N_ICAS):
        t.add_ica(ICANode(f"ica{k+1}", "pcc", s_max=80e3))
    t.add_load(LoadNode("load1", "pcc", p_nominal=100e3, q_nominal=0.0, nonlinear=True))
    return t


def _build_agents(pubsub: InMemoryPubSub):
    agents, plants = [], []
    plant_p = PlantParams()
    for k in range(N_ICAS):
        plant = Plant(plant_p)
        inner = FSMPCController(FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=20e-6))
        outer = EnergyPI(EnergyPIParams(C=plant_p.C, R=plant_p.R, v_dc_ref=plant_p.v_dc_init))
        pll = IdealPLL(f_grid=plant_p.f_grid)
        agent = ICAAgent(f"ica{k+1}", inner, outer, pll, pubsub, telemetry_decim=10)
        plants.append(plant)
        agents.append(agent)
    return agents, plants


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    topology = _build_topology()
    pubsub = InMemoryPubSub()
    agents, plants = _build_agents(pubsub)
    load = HarmonicLoad(HarmonicLoadParams(P_fund=100e3, Q_fund=0.0))

    cmc = Controller(topology, pubsub,
                     ControllerConfig(tick_period_s=0.005, v_dc_ref_default=900.0))
    cmc.start(now=0.0)

    # CMC dispatches scheduled to fire at certain absolute times
    cmc_dispatches = [
        (5e-3,  {"q_total_target": 0.0,    "v_dc_ref_default": 900.0}),
        (25e-3, {"q_total_target": 5_000.0, "v_dc_ref_default": 900.0}),
        (50e-3, {"q_total_target": 5_000.0, "v_dc_ref_default": 880.0}),
    ]

    T_s = agents[0].inner.p.T_s
    t_end = 80e-3
    N_steps = int(round(t_end / T_s))
    N_sub = 5
    i_dc_per_ica = -100.0 / N_ICAS   # split the 100 A loading evenly

    log_t = np.zeros(N_steps)
    log_v_dc = np.zeros((N_steps, N_ICAS))
    log_i_m = np.zeros((N_steps, N_ICAS, 3))
    log_i_s_pcc = np.zeros((N_steps, 3))
    log_i_l_pcc = np.zeros((N_steps, 3))
    log_v_s = np.zeros((N_steps, 3))

    next_dispatch_idx = 0
    last_cmc_tick_t = -1.0

    for k in range(N_steps):
        t = k * T_s

        # Apply scheduled CMC config changes BEFORE the tick
        while (next_dispatch_idx < len(cmc_dispatches)
               and t + 1e-12 >= cmc_dispatches[next_dispatch_idx][0]):
            for key, val in cmc_dispatches[next_dispatch_idx][1].items():
                setattr(cmc.cfg, key, val)
            next_dispatch_idx += 1

        # CMC dispatch tick at its own period
        if (t - last_cmc_tick_t) >= cmc.cfg.tick_period_s - 1e-12:
            cmc.tick(now=t)
            last_cmc_tick_t = t

        v_s = load.v_s(t)
        i_l = load.i_l(t)

        # Each ICA absorbs an equal share of the load current (4-way split at PCC)
        i_l_share = i_l / N_ICAS

        i_m_pcc_sum = np.zeros(3)
        for k_ica, (agent, plant) in enumerate(zip(agents, plants)):
            s = agent.step(t, plant.i_m, plant.v_dc, v_s, i_l_share)
            for _ in range(N_sub):
                plant.step(s, v_s, i_dc=i_dc_per_ica, dt=T_s / N_sub)
            log_v_dc[k, k_ica] = plant.v_dc
            log_i_m[k, k_ica] = plant.i_m
            i_m_pcc_sum += plant.i_m

        log_t[k] = t
        log_i_l_pcc[k] = i_l
        log_v_s[k] = v_s
        log_i_s_pcc[k] = i_m_pcc_sum + i_l   # PCC current = sum(i_m) + i_l

    # ----- analytics -----
    n_ref = len(pubsub.history(topic_prefix="/ica/"))
    n_total = len(pubsub.history())
    n_dispatches = len(cmc.log)
    print(f"Dispatched {n_dispatches} times; pubsub messages: total={n_total}, ica-related={n_ref}")
    final_v_dc = log_v_dc[-1]
    print(f"Final v_dc per ICA: {[f'{v:.1f}' for v in final_v_dc]}  "
          f"(target {cmc.cfg.v_dc_ref_default:.0f} V)")
    last = cmc.log[-1]
    qs = [last["published"][iid]["Q_ref"] for iid in topology.icas]
    print(f"Last Q_ref dispatch: {qs} VAr  (sum={sum(qs):.0f}, target={cmc.cfg.q_total_target:.0f})")

    # ----- plot -----
    fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)

    ax = axes[0]
    ax.plot(log_t * 1e3, log_v_s[:, 0], color="C0", linewidth=0.8, label="v_s,a")
    ax.set_ylabel("Grid v (V)")
    ax.legend(loc="upper right"); ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(log_t * 1e3, log_i_s_pcc[:, 0], color="C2", linewidth=0.9, label="i_s,a (PCC sum)")
    ax.plot(log_t * 1e3, log_i_l_pcc[:, 0], color="C1", linewidth=0.7, alpha=0.6, label="i_l,a")
    ax.set_ylabel("PCC currents (A)")
    ax.legend(loc="upper right"); ax.grid(alpha=0.3)

    ax = axes[2]
    for k_ica in range(N_ICAS):
        ax.plot(log_t * 1e3, log_v_dc[:, k_ica], linewidth=0.9, label=f"ica{k_ica+1}")
    for ts, _patch in cmc_dispatches:
        ax.axvline(ts * 1e3, color="C7", linestyle="--", alpha=0.4)
    ax.axhline(900.0, color="gray", linestyle=":", alpha=0.5)
    ax.axhline(880.0, color="gray", linestyle=":", alpha=0.5)
    ax.set_ylabel("v_dc per ICA (V)")
    ax.legend(loc="lower right", ncol=4); ax.grid(alpha=0.3)

    ax = axes[3]
    for k_ica in range(N_ICAS):
        ax.plot(log_t * 1e3, log_i_m[:, k_ica, 0], linewidth=0.6, alpha=0.8,
                label=f"i_m,a ica{k_ica+1}")
    ax.set_ylabel("i_m,a per ICA (A)")
    ax.set_xlabel("time (ms)")
    ax.legend(loc="upper right", ncol=4); ax.grid(alpha=0.3)

    fig.suptitle("Phase-2: 4-ICA fleet under CMC dispatch (Q step 25 ms, v_dc step 50 ms)")
    fig.tight_layout()
    out_file = out_dir / "fleet_demo.png"
    fig.savefig(out_file, dpi=140)
    plt.close(fig)
    print(f"Saved: {out_file}")


if __name__ == "__main__":
    main()
