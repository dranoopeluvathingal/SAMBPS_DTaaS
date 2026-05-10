"""CMC unit tests."""

import time
import pytest

from fs_mpc_mg.comm.pubsub import InMemoryPubSub
from fs_mpc_mg.comm.topics import topic_ref, topic_telemetry
from fs_mpc_mg.cmc import (
    Topology, BusNode, ICANode, LoadNode,
    Controller, ControllerConfig,
    ModeArbiter, SystemMode,
    QAllocator, HAllocator,
    StateEstimator, FleetState,
)
from fs_mpc_mg.cmc.topology import SwitchEdge


def _toy_topology(n_icas: int = 4) -> Topology:
    t = Topology()
    t.add_bus(BusNode("grid", is_grid=True))
    t.add_bus(BusNode("pcc"))
    t.add_switch(SwitchEdge("tie", "grid", "pcc", closed=True))
    for i in range(n_icas):
        t.add_ica(ICANode(f"ica{i+1}", "pcc", s_max=80e3))
    t.add_load(LoadNode("load1", "pcc", p_nominal=120e3, q_nominal=20e3, nonlinear=True))
    return t


# -----------------------------------------------------------------
# Topology
# -----------------------------------------------------------------
def test_topology_basic():
    t = _toy_topology()
    assert len(t.icas) == 4
    assert t.grid_tie_switch() is not None
    assert not t.is_islanded()


def test_topology_open_tie():
    t = _toy_topology()
    t.switches["tie"].closed = False
    assert t.is_islanded()


# -----------------------------------------------------------------
# Mode arbiter
# -----------------------------------------------------------------
def test_mode_arbiter_loss_of_grid_then_timeout():
    a = ModeArbiter(transition_timeout_s=0.05)
    assert a.mode == SystemMode.GRID
    a.loss_of_grid(now=0.0)
    assert a.mode == SystemMode.TRANSITION
    a.tick(now=0.10, grid_present=False)
    assert a.mode == SystemMode.ISLAND


def test_mode_arbiter_fault_latches():
    a = ModeArbiter()
    a.declare_fault("over_voltage")
    assert a.mode == SystemMode.FAULT
    assert a.ica_command_mode() == "fault"
    a.tick(now=10.0, grid_present=True)
    assert a.mode == SystemMode.FAULT


def test_mode_arbiter_grid_restored():
    a = ModeArbiter(transition_timeout_s=0.05, mode=SystemMode.ISLAND)
    a.grid_restored(now=0.0)
    a.tick(now=0.1, grid_present=True)
    assert a.mode == SystemMode.GRID


# -----------------------------------------------------------------
# State estimator
# -----------------------------------------------------------------
def test_state_estimator_subscribes_and_aggregates():
    t = _toy_topology(2)
    ps = InMemoryPubSub()
    est = StateEstimator(t, ps)
    ps.publish_value(topic_telemetry("ica1", "v_dc"), 905.0)
    ps.publish_value(topic_telemetry("ica2", "v_dc"), 895.0)
    snap = est.snapshot()
    assert snap.icas["ica1"].v_dc == pytest.approx(905.0)
    assert snap.icas["ica2"].v_dc == pytest.approx(895.0)


def test_state_estimator_active_count_with_heartbeat():
    t = _toy_topology(2)
    ps = InMemoryPubSub()
    est = StateEstimator(t, ps)
    ps.publish_value(topic_telemetry("ica1", "heartbeat"),
                     {"mode": "running", "enabled": True})
    ps.publish_value(topic_telemetry("ica2", "heartbeat"),
                     {"mode": "fault", "enabled": False})
    snap = est.snapshot()
    assert snap.n_active() == 1


# -----------------------------------------------------------------
# Q allocator
# -----------------------------------------------------------------
def test_q_allocator_proportional_zero_p_balanced():
    t = _toy_topology(4)
    est = StateEstimator(t, InMemoryPubSub())
    for iid in t.icas:
        est.force_state(iid, enabled=True, mode="running",
                        i_m_abc=(0.0, 0.0, 0.0), v_s_abc=(310.0, -155.0, -155.0))
    fleet = est.snapshot()
    qa = QAllocator(t)
    out = qa.allocate(20_000.0, fleet)
    assert pytest.approx(sum(out.values()), abs=1e-6) == 20_000.0
    # equal split (4 ICAs, identical capability)
    for q in out.values():
        assert pytest.approx(q, rel=1e-3) == 5_000.0


def test_q_allocator_clips_to_total_capability():
    t = _toy_topology(2)
    for iid in t.icas:
        t.icas[iid].s_max = 10e3   # tiny capacity
    est = StateEstimator(t, InMemoryPubSub())
    for iid in t.icas:
        est.force_state(iid, enabled=True, mode="running",
                        i_m_abc=(0.0, 0.0, 0.0), v_s_abc=(310.0, -155.0, -155.0))
    fleet = est.snapshot()
    qa = QAllocator(t)
    out = qa.allocate(100_000.0, fleet)  # asks for way more than total 20 kVA
    # Should be clipped at total capability (~20 kVA)
    assert sum(out.values()) <= 2 * 10e3 + 1.0


# -----------------------------------------------------------------
# H allocator
# -----------------------------------------------------------------
def test_h_allocator_balanced_full_headroom():
    t = _toy_topology(4)
    est = StateEstimator(t, InMemoryPubSub())
    for iid in t.icas:
        est.force_state(iid, enabled=True, mode="running",
                        i_m_abc=(0.0, 0.0, 0.0))
    fleet = est.snapshot()
    ha = HAllocator(t)
    res = ha.allocate(fleet)
    # All 4 ICAs equal-share -> each fraction = 0.25 -> all masks True
    for iid in t.icas:
        for h in (5, 7, 11, 13):
            assert pytest.approx(res.fractions[iid][h]) == 0.25
            assert res.masks[iid][h] is True


# -----------------------------------------------------------------
# Controller integration
# -----------------------------------------------------------------
def test_controller_publishes_refs_on_start():
    t = _toy_topology(3)
    ps = InMemoryPubSub()
    ctrl = Controller(t, ps, ControllerConfig(v_dc_ref_default=910.0, q_total_target=0.0))
    ctrl.start(now=0.0)
    # Each ICA should have received v_dc_ref, mode, enable
    for iid in t.icas:
        assert ps.latest(topic_ref(iid, "v_dc_ref"))["value"] == pytest.approx(910.0)
        assert ps.latest(topic_ref(iid, "mode"))["value"] == "running"
        assert ps.latest(topic_ref(iid, "enable"))["value"] is True


def test_controller_tick_dispatches_q_and_h():
    t = _toy_topology(3)
    ps = InMemoryPubSub()
    ctrl = Controller(t, ps, ControllerConfig(q_total_target=15_000.0))
    # Mark all ICAs as active
    for iid in t.icas:
        ps.publish_value(topic_telemetry(iid, "heartbeat"),
                         {"mode": "running", "enabled": True})
        ps.publish_value(topic_telemetry(iid, "v_s_abc"), [310.0, -155.0, -155.0])
    ctrl.start(now=0.0)
    rec = ctrl.tick(now=1.0)
    assert rec["sys_mode"] == "grid"
    qs = [rec["published"][iid]["Q_ref"] for iid in t.icas]
    assert pytest.approx(sum(qs), abs=1.0) == 15_000.0
    # Each H_mask should be a dict of bools
    for iid in t.icas:
        mask = rec["published"][iid]["H_mask"]
        assert set(mask.keys()) == {5, 7, 11, 13}


def test_controller_grid_tie_open_transitions_to_island():
    t = _toy_topology(2)
    ps = InMemoryPubSub()
    ctrl = Controller(t, ps, ControllerConfig())
    ctrl.start(now=0.0)
    ctrl.open_grid_tie(now=1.0)
    rec = ctrl.tick(now=1.5, grid_present=False)
    # Initially in TRANSITION; after timeout -> ISLAND
    assert rec["sys_mode"] in ("transition", "island")
    # After 200 ms we're past the 100 ms transition window
    rec2 = ctrl.tick(now=1.21, grid_present=False)
    assert rec2["sys_mode"] == "island"
