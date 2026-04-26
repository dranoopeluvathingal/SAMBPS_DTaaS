"""Generate a self-contained operator dashboard HTML from a fleet+CMC+DT run.

Run:
    python scripts/run_dashboard_demo.py
    -> figures/dashboard.html  (open in any browser)
"""

from __future__ import annotations

from pathlib import Path
import sys
import numpy as np

from fs_mpc_mg import (
    Plant, PlantParams, HarmonicLoad, HarmonicLoadParams,
    SOGIPLL, SOGIPLLParams,
    FSMPCController, FSMPCParams, EnergyPI, EnergyPIParams,
    ICAAgent,
)
from fs_mpc_mg.comm.pubsub import InMemoryPubSub
from fs_mpc_mg.comm.topics import topic_ref
from fs_mpc_mg.cmc import (
    Topology, BusNode, ICANode, LoadNode, Controller, ControllerConfig,
)
from fs_mpc_mg.cmc.topology import SwitchEdge
from fs_mpc_mg.dt import MicrogridDigitalTwin, TwinConfig
from fs_mpc_mg.dashboard import build_report


N_ICAS = 4


def _build_topology() -> Topology:
    t = Topology()
    t.add_bus(BusNode("grid", is_grid=True))
    t.add_bus(BusNode("pcc"))
    t.add_switch(SwitchEdge("tie", "grid", "pcc", closed=True))
    for k in range(N_ICAS):
        t.add_ica(ICANode(f"ica{k+1}", "pcc", s_max=80e3))
    t.add_load(LoadNode("load1", "pcc", p_nominal=40e3, nonlinear=True))
    return t


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    topology = _build_topology()
    ps = InMemoryPubSub()

    plant_p = PlantParams()
    agents, plants = [], []
    for k in range(N_ICAS):
        plant = Plant(plant_p)
        inner = FSMPCController(FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=20e-6))
        outer = EnergyPI(EnergyPIParams(C=plant_p.C, R=plant_p.R, v_dc_ref=plant_p.v_dc_init))
        pll = SOGIPLL(SOGIPLLParams(T_s=20e-6, omega_n=120.0))
        agents.append(ICAAgent(f"ica{k+1}", inner, outer, pll, ps, telemetry_decim=10))
        plants.append(plant)

    load = HarmonicLoad(HarmonicLoadParams(P_fund=40e3, Q_fund=0.0))
    cmc = Controller(topology, ps, ControllerConfig(tick_period_s=5e-3, v_dc_ref_default=900.0))
    cmc.start(now=0.0)

    twin = MicrogridDigitalTwin([f"ica{k+1}" for k in range(N_ICAS)], ps,
                                TwinConfig(T_s=20e-6, n_sub_per_ica_tick=5))
    for det in twin.anomaly.values():
        det.warmup_samples = 200
        det.n_sigma = 6.0
        det.dwell_count = 8

    # CMC events
    cmc_events = [
        (25e-3, dict(q_total_target=4_000.0)),
        (50e-3, dict(v_dc_ref_default=880.0, q_total_target=4_000.0)),
    ]

    T_s = agents[0].inner.p.T_s
    t_end = 80e-3
    N_steps = int(round(t_end / T_s))
    N_sub = 5

    cmc_last_t = -1.0
    twin_last_t = -1.0
    next_evt = 0

    for k in range(N_steps):
        t = k * T_s
        while next_evt < len(cmc_events) and t + 1e-12 >= cmc_events[next_evt][0]:
            for key, val in cmc_events[next_evt][1].items():
                setattr(cmc.cfg, key, val)
            next_evt += 1
        if (t - cmc_last_t) >= cmc.cfg.tick_period_s - 1e-12:
            cmc.tick(now=t)
            cmc_last_t = t

        v_s = load.v_s(t)
        i_l_share = load.i_l(t) / N_ICAS

        for agent, plant in zip(agents, plants):
            s = agent.step(t, plant.i_m, plant.v_dc, v_s, i_l_share)
            for _ in range(N_sub):
                plant.step(s, v_s, i_dc=0.0, dt=T_s / N_sub)

        if (t - twin_last_t) >= 100e-6 - 1e-12:
            twin.tick(t=t)
            twin_last_t = t

    # ----- generate report -----
    report = build_report(
        title="fs_mpc_mg — 4-ICA fleet under CMC + DT (STATCOM mode)",
        sim_t_end_s=t_end,
        fleet_ica_ids=[f"ica{k+1}" for k in range(N_ICAS)],
        pubsub_history=ps.history(),
        cmc_dispatches=cmc.log,
        dt_summary=twin.summary(),
        extra_notes=(
            "Generated from scripts/run_dashboard_demo.py.\n"
            "Topology: 1 grid bus, 1 PCC, 4 ICAs (S_max=80kVA each), 1 nonlinear load.\n"
            "PLL: SOGIPLL (omega_n=120 rad/s). Mode: STATCOM (i_dc=0).\n"
            "CMC events: Q_total = 4 kVAr at 25ms; v_dc_ref step to 880V at 50ms."
        ),
    )
    out_html = out_dir / "dashboard.html"
    report.save(out_html)
    print(f"DT summary: {twin.summary()}")
    print(f"CMC dispatches: {len(cmc.log)}")
    print(f"PubSub messages: {len(ps.history())}")
    print(f"Saved: {out_html}")


if __name__ == "__main__":
    main()
