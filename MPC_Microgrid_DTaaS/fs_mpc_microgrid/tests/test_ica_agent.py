"""ICA agent unit tests using the in-memory pub/sub.

These tests exercise the agent in isolation (no plant, no MQTT broker).
"""

import numpy as np
import pytest

from fs_mpc_mg import (
    Plant,
    PlantParams,
    HarmonicLoad,
    HarmonicLoadParams,
    IdealPLL,
    FSMPCController,
    FSMPCParams,
    EnergyPI,
    EnergyPIParams,
)
from fs_mpc_mg.ica_agent import ICAAgent
from fs_mpc_mg.comm.pubsub import InMemoryPubSub
from fs_mpc_mg.comm.topics import topic_ref, topic_telemetry


def _make_agent(agent_id: str = "ica1") -> tuple[ICAAgent, InMemoryPubSub]:
    plant_p = PlantParams()
    inner = FSMPCController(FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=20e-6))
    outer = EnergyPI(EnergyPIParams(C=plant_p.C, R=plant_p.R, v_dc_ref=plant_p.v_dc_init))
    pll = IdealPLL(f_grid=plant_p.f_grid)
    ps = InMemoryPubSub()
    agent = ICAAgent(agent_id, inner, outer, pll, ps, telemetry_decim=10)
    return agent, ps


def test_default_state():
    agent, _ = _make_agent()
    assert agent.state.mode == "running"
    assert agent.state.enabled is True
    assert agent.state.v_dc_ref == pytest.approx(900.0)
    assert agent.state.Q_ref == 0.0


def test_v_dc_ref_subscription_updates_state_and_outer():
    agent, ps = _make_agent("ica1")
    ps.publish_value(topic_ref("ica1", "v_dc_ref"), 950.0)
    assert agent.state.v_dc_ref == pytest.approx(950.0)
    # outer PI energy reference should have updated
    expected_E = 0.5 * agent.outer.p.C * 950.0 ** 2
    assert agent.outer.E_c_ref == pytest.approx(expected_E)


def test_Q_ref_subscription():
    agent, ps = _make_agent()
    ps.publish_value(topic_ref(agent.id, "Q_ref"), 5_000.0)
    assert agent.state.Q_ref == pytest.approx(5_000.0)


def test_enable_disable_blocks_switching():
    agent, ps = _make_agent()
    ps.publish_value(topic_ref(agent.id, "enable"), False)
    s = agent.step(
        t=0.0,
        i_m=np.zeros(3),
        v_dc=900.0,
        v_s=np.array([310.0, -155.0, -155.0]),
        i_l=np.zeros(3),
    )
    assert np.allclose(s, np.zeros(3)), "Disabled agent must output zero switching"


def test_mode_fault_blocks_switching():
    agent, ps = _make_agent()
    ps.publish_value(topic_ref(agent.id, "mode"), "fault")
    s = agent.step(0.0, np.zeros(3), 900.0, np.array([310.0, -155.0, -155.0]), np.zeros(3))
    assert np.allclose(s, np.zeros(3))


def test_step_publishes_telemetry():
    agent, ps = _make_agent("ica1")
    # Run 20 ticks; telemetry_decim=10 => publishes at tick 0 and tick 10
    for k in range(20):
        agent.step(
            t=k * 20e-6,
            i_m=np.zeros(3),
            v_dc=900.0,
            v_s=np.array([310.0, -155.0, -155.0]),
            i_l=np.zeros(3),
        )
    history = ps.history(topic_prefix="/ica/ica1/tel/")
    assert len(history) > 0
    # v_dc telemetry must have been published at least twice
    v_dc_msgs = [h for h in history if h[0] == topic_telemetry("ica1", "v_dc")]
    assert len(v_dc_msgs) >= 2


def test_step_returns_valid_switching_vector():
    agent, _ = _make_agent()
    s = agent.step(
        t=0.0,
        i_m=np.array([10.0, -5.0, -5.0]),
        v_dc=900.0,
        v_s=np.array([310.0, -155.0, -155.0]),
        i_l=np.zeros(3),
    )
    assert s.shape == (3,)
    assert set(s.tolist()) <= {0.0, 1.0}


def test_closed_loop_with_plant_and_load():
    """End-to-end smoke test: agent + plant + load run for ~5 ms without exploding."""
    plant = Plant(PlantParams())
    load = HarmonicLoad(HarmonicLoadParams(P_fund=10e3, Q_fund=0.0))
    inner = FSMPCController(FSMPCParams(L=plant.p.L, r=plant.p.r, T_s=20e-6))
    outer = EnergyPI(EnergyPIParams(C=plant.p.C, R=plant.p.R, v_dc_ref=plant.p.v_dc_init))
    pll = IdealPLL(f_grid=plant.p.f_grid)
    ps = InMemoryPubSub()
    agent = ICAAgent("ica42", inner, outer, pll, ps, telemetry_decim=50)

    T_s = inner.p.T_s
    N_sub = 5
    for k in range(int(5e-3 / T_s)):  # 5 ms
        t = k * T_s
        v_s = load.v_s(t)
        i_l = load.i_l(t)
        s = agent.step(t, plant.i_m, plant.v_dc, v_s, i_l)
        for _ in range(N_sub):
            plant.step(s, v_s, i_dc=-50.0, dt=T_s / N_sub)

    assert np.isfinite(plant.v_dc) and 700.0 < plant.v_dc < 1100.0
    assert np.all(np.isfinite(plant.i_m))
    # telemetry should be flowing
    assert len(ps.history(topic_prefix=f"/ica/{agent.id}/tel/")) > 0
