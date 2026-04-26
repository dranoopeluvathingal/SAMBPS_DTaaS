"""DT demo — fleet + CMC + Digital Twin running together.

Scenario:
  - 4 ICAs with their Plants under CMC dispatch (loading mode).
  - The DT subscribes to all telemetry and runs a ShadowPlant per ICA.
  - At t = 35 ms a sensor fault is injected on ica2: its published v_dc
    suddenly carries a +50 V offset (the actual plant is fine).
  - At t = 55 ms the demo also publishes a *spoofed* Q_ref of 1 GVAr to
    /ica/ica3/refs/Q_ref to test the cyber screen.
  - Expectation: DT raises an anomaly on ica2's v_dc residual, and a
    cyber alert on ica3's Q_ref.

Run:
    python scripts/run_dt_demo.py
    -> figures/dt_demo.png
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
from fs_mpc_mg.comm.topics import topic_ref, topic_telemetry
from fs_mpc_mg.cmc import (
    Topology, BusNode, ICANode, LoadNode, Controller, ControllerConfig,
)
from fs_mpc_mg.cmc.topology import SwitchEdge
from fs_mpc_mg.dt import MicrogridDigitalTwin, TwinConfig
from fs_mpc_mg.dt.topics import topic_dt


N_ICAS = 4


def _build_topology() -> Topology:
    t = Topology()
    t.add_bus(BusNode("grid", is_grid=True))
    t.add_bus(BusNode("pcc"))
    t.add_switch(SwitchEdge("tie", "grid", "pcc", closed=True))
    for k in range(N_ICAS):
        t.add_ica(ICANode(f"ica{k+1}", "pcc", s_max=80e3))
    t.add_load(LoadNode("load1", "pcc", p_nominal=100e3, nonlinear=True))
    return t


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    topology = _build_topology()
    ps = InMemoryPubSub()

    # Build agents and plants
    agents, plants = [], []
    plant_p = PlantParams()
    for k in range(N_ICAS):
        plant = Plant(plant_p)
        inner = FSMPCController(FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=20e-6))
        outer = EnergyPI(EnergyPIParams(C=plant_p.C, R=plant_p.R, v_dc_ref=plant_p.v_dc_init))
        pll = IdealPLL(f_grid=plant_p.f_grid)
        agent = ICAAgent(f"ica{k+1}", inner, outer, pll, ps, telemetry_decim=10)
        agents.append(agent)
        plants.append(plant)

    load = HarmonicLoad(HarmonicLoadParams(P_fund=40e3, Q_fund=0.0))
    cmc = Controller(topology, ps, ControllerConfig(tick_period_s=5e-3, v_dc_ref_default=900.0))
    cmc.start(now=0.0)

    twin = MicrogridDigitalTwin([f"ica{k+1}" for k in range(N_ICAS)], ps,
                                TwinConfig(T_s=20e-6, n_sub_per_ica_tick=5))
    # Lengthen warmup so the startup transient is treated as calibration data
    for det in twin.anomaly.values():
        det.warmup_samples = 250
        det.n_sigma = 6.0
        det.dwell_count = 8

    # --------- attack scripts -------------
    sensor_fault_t = 35e-3
    cyber_attack_t = 55e-3
    spoofed_Q = 1_000_000_000.0
    sensor_offset = +50.0

    T_s = agents[0].inner.p.T_s
    t_end = 80e-3
    N_steps = int(round(t_end / T_s))
    N_sub = 5
    dt_int = T_s / N_sub
    i_dc_per_ica = 0.0  # STATCOM mode for clean v_dc trace

    log_t = np.zeros(N_steps)
    log_v_dc_real = np.zeros((N_steps, N_ICAS))
    log_v_dc_pub = np.zeros((N_steps, N_ICAS))     # what the *agent published* (with offset on ica2)
    log_residual_v_dc = np.zeros((N_steps, N_ICAS))
    log_residual_im = np.zeros((N_steps, N_ICAS))

    cmc_last_tick = -1.0
    twin_last_tick = -1.0
    twin_period = 100e-6   # 10 kHz DT tick (downsampled from FS-MPC)
    cyber_attack_done = False

    for k in range(N_steps):
        t = k * T_s

        # CMC dispatch
        if (t - cmc_last_tick) >= cmc.cfg.tick_period_s - 1e-12:
            cmc.tick(now=t)
            cmc_last_tick = t

        # Cyber attack: publish a spoofed Q_ref to ica3 once
        if (not cyber_attack_done) and t >= cyber_attack_t:
            ps.publish_value(topic_ref("ica3", "Q_ref"), spoofed_Q, ts=t)
            cyber_attack_done = True

        v_s = load.v_s(t)
        i_l = load.i_l(t)
        i_l_share = i_l / N_ICAS

        for k_ica, (agent, plant) in enumerate(zip(agents, plants)):
            s = agent.step(t, plant.i_m, plant.v_dc, v_s, i_l_share)
            for _ in range(N_sub):
                plant.step(s, v_s, i_dc=i_dc_per_ica, dt=dt_int)
            log_v_dc_real[k, k_ica] = plant.v_dc

            # Sensor-fault injection: corrupt the v_dc that ica2 publishes
            # (we override the agent's just-published telemetry by republishing)
            if k_ica == 1 and t >= sensor_fault_t:
                corrupted = plant.v_dc + sensor_offset
                ps.publish_value(topic_telemetry("ica2", "v_dc"), corrupted, ts=t)
                log_v_dc_pub[k, k_ica] = corrupted
            else:
                log_v_dc_pub[k, k_ica] = plant.v_dc

        # DT tick (downsampled — every twin_period)
        if (t - twin_last_tick) >= twin_period - 1e-12:
            twin.tick(t=t)
            twin_last_tick = t

        # Capture residuals from latest DT publications
        for k_ica in range(N_ICAS):
            iid = f"ica{k_ica+1}"
            r_vdc = ps.latest(topic_dt("residual/v_dc", iid))
            r_im  = ps.latest(topic_dt("residual/i_m_norm", iid))
            log_residual_v_dc[k, k_ica] = r_vdc["value"] if r_vdc else 0.0
            log_residual_im[k, k_ica]   = r_im["value"]  if r_im  else 0.0

        log_t[k] = t

    # ---------- print summary ----------
    summary = twin.summary()
    print(f"DT ticks: {summary['n_ticks']}")
    print(f"Anomaly events  : {summary['n_anomaly_events']}")
    print(f"Cyber alerts    : {summary['n_cyber_alerts']}")
    for iid, info in summary["rls"].items():
        print(f"  {iid}: RLS L={info['L']*1e6:.1f} µH  r={info['r']*1e3:.1f} mΩ  "
              f"n={info['n']}  conv={info['converged']}")

    # ---------- print a few events for the report ----------
    if twin.cyber_alerts:
        print("\nFirst 3 cyber alerts:")
        for a in twin.cyber_alerts[:3]:
            print(f"  [{a.severity:8s}] {a.target_ica_id} {a.rule}: {a.detail}")
    if twin.events:
        print("\nFirst 3 anomaly events:")
        for e in twin.events[:3]:
            print(f"  [{e.severity:8s}] {e.ica_id} {e.metric}={e.value:.2f} > {e.threshold:.2f}")

    # Clip event timestamps to simulation window for plotting
    sim_t_max = float(log_t[-1])
    def _clip(ts):
        return ts if 0 <= ts <= sim_t_max + 1e-3 else None
    # ---------- plot ----------
    fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)

    ax = axes[0]
    for k_ica in range(N_ICAS):
        ax.plot(log_t * 1e3, log_v_dc_real[:, k_ica], linewidth=0.7, alpha=0.8,
                label=f"v_dc real ica{k_ica+1}")
    ax.axvline(sensor_fault_t * 1e3, color="r", linestyle="--", alpha=0.5,
               label=f"sensor fault (ica2) @ {sensor_fault_t*1e3:.0f} ms")
    ax.set_ylabel("v_dc actual (V)")
    ax.legend(loc="upper right", ncol=3, fontsize=8); ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(log_t * 1e3, log_v_dc_pub[:, 1] - log_v_dc_real[:, 1],
            color="r", linewidth=0.9, label="ica2 published − real")
    ax.set_ylabel("Sensor-fault offset (V)")
    ax.legend(loc="upper right"); ax.grid(alpha=0.3)

    ax = axes[2]
    for k_ica in range(N_ICAS):
        col = "r" if k_ica == 1 else f"C{k_ica}"
        ax.plot(log_t * 1e3, log_residual_v_dc[:, k_ica], color=col, linewidth=0.8,
                label=f"DT v_dc residual ica{k_ica+1}")
    ax.axhline(0, color="k", linewidth=0.3)
    # Mark anomaly events
    for e in twin.events:
        if e.metric == "v_dc_residual":
            ts_c = _clip(e.ts);
            if ts_c is not None: ax.axvline(ts_c * 1e3, color="orange", linestyle=":", alpha=0.7)
    ax.set_ylabel("v_dc residual (V)")
    ax.legend(loc="upper right", ncol=2, fontsize=8); ax.grid(alpha=0.3)

    ax = axes[3]
    for k_ica in range(N_ICAS):
        col = "r" if k_ica == 1 else f"C{k_ica}"
        ax.plot(log_t * 1e3, log_residual_im[:, k_ica], color=col, linewidth=0.8,
                label=f"DT ‖i_m‖ residual ica{k_ica+1}")
    for a in twin.cyber_alerts:
        ts_c = _clip(a.ts);
        if ts_c is not None: ax.axvline(ts_c * 1e3, color="purple", linestyle=":", alpha=0.7)
    ax.set_xlabel("time (ms)")
    ax.set_ylabel("‖i_m‖ residual (A)")
    ax.legend(loc="upper right", ncol=2, fontsize=8); ax.grid(alpha=0.3)

    fig.suptitle("DT demo — sensor-fault on ica2 @35 ms, Q_ref spoof on ica3 @55 ms")
    fig.tight_layout()
    out_file = out_dir / "dt_demo.png"
    fig.savefig(out_file, dpi=140)
    plt.close(fig)
    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()
