"""Tests for adapters/pandapower/topology_to_pp.py.

Skipped if pandapower is not importable (the adapter is in the
`powerflow` extra). The test builds the IEEE 33-bus topology, converts
it, dispatches the sgens to inject roughly nominal load (so voltages
hold within +/- 5% of pu), runs pp.runpp(), and asserts convergence +
voltage bounds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Adapters live outside the package — make `adapters/` importable.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "topologies"))

pandapower = pytest.importorskip("pandapower", reason="pandapower not installed (powerflow extra)")
pp = pandapower

from adapters.pandapower import topology_to_pandapower
from fs_mpc_mg.cmc.topology import (
    Topology, BusNode, ICANode, LoadNode, SwitchEdge, LineEdge,
)


# ---------------------------------------------------------------------------
# Smoke tests on a tiny hand-built topology
# ---------------------------------------------------------------------------
def test_bus_count_matches():
    t = Topology()
    t.add_bus(BusNode("grid", nominal_voltage=12_660.0, is_grid=True))
    t.add_bus(BusNode("b1", nominal_voltage=12_660.0))
    net = topology_to_pandapower(t)
    assert len(net.bus) == 2


def test_grid_bus_gets_ext_grid():
    t = Topology()
    t.add_bus(BusNode("grid", nominal_voltage=12_660.0, is_grid=True))
    t.add_bus(BusNode("b1", nominal_voltage=12_660.0))
    net = topology_to_pandapower(t)
    assert len(net.ext_grid) == 1
    assert net.bus.iloc[net.ext_grid.iloc[0].bus]["name"] == "grid"


def test_ica_becomes_controllable_sgen_with_box_limits():
    t = Topology()
    t.add_bus(BusNode("b1", nominal_voltage=12_660.0))
    t.add_ica(ICANode("ica1", bus_id="b1", s_max=500e3))   # 0.5 MVA
    net = topology_to_pandapower(t)
    assert len(net.sgen) == 1
    sgen = net.sgen.iloc[0]
    assert bool(sgen.controllable) is True
    assert sgen.sn_mva == pytest.approx(0.5)
    assert sgen.max_p_mw == pytest.approx(0.5)
    assert sgen.min_p_mw == pytest.approx(-0.5)
    assert sgen.max_q_mvar == pytest.approx(0.5)
    assert sgen.min_q_mvar == pytest.approx(-0.5)
    # Default operating point is zero (CMC sets later)
    assert sgen.p_mw == 0.0
    assert sgen.q_mvar == 0.0


def test_load_uses_consumer_convention():
    t = Topology()
    t.add_bus(BusNode("b1", nominal_voltage=12_660.0))
    t.add_load(LoadNode("l1", bus_id="b1", p_nominal=100e3, q_nominal=40e3))
    net = topology_to_pandapower(t)
    load = net.load.iloc[0]
    assert load.p_mw == pytest.approx(0.1)
    assert load.q_mvar == pytest.approx(0.04)


def test_switch_becomes_bus_bus_switch():
    t = Topology()
    t.add_bus(BusNode("a"))
    t.add_bus(BusNode("b"))
    t.add_switch(SwitchEdge("sw1", "a", "b", closed=True))
    net = topology_to_pandapower(t)
    assert len(net.switch) == 1
    assert net.switch.iloc[0].et == "b"
    assert bool(net.switch.iloc[0].closed) is True


def test_line_carries_impedance():
    t = Topology()
    t.add_bus(BusNode("a", nominal_voltage=12_660.0))
    t.add_bus(BusNode("b", nominal_voltage=12_660.0))
    t.add_line(LineEdge("L1", "a", "b", r_ohm_per_km=0.5, x_ohm_per_km=0.3, length_km=2.0))
    net = topology_to_pandapower(t)
    line = net.line.iloc[0]
    assert line.r_ohm_per_km == pytest.approx(0.5)
    assert line.x_ohm_per_km == pytest.approx(0.3)
    assert line.length_km == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# IEEE 33-bus end-to-end: convert, dispatch DG, runpp, check voltages
# ---------------------------------------------------------------------------
def test_ieee_33_bus_runpp_converges_with_dg_dispatch():
    """End-to-end: build IEEE 33-bus topology, convert via adapter,
    dispatch the 6 sgens (4 PV + 2 BESS) at 65% of their s_max as P
    injection (typical DG operation), run pp.runpp, and check that all
    bus voltages stay within +/- 5% pu.

    Without DG dispatch the canonical Baran-Wu IEEE 33-bus has min
    voltage ~0.913 pu at the end of the longest feeder; the DG
    injections lift that into the 0.95-1.05 band the test asserts.
    """
    import ieee_33_bus  # from topologies/

    topology = ieee_33_bus.build()
    net = topology_to_pandapower(topology)

    # Dispatch each sgen at 65% of its rated apparent power as P (no Q).
    # This represents typical mid-day DG operation and brings min voltage
    # above 0.95 pu.
    for i in net.sgen.index:
        s_mva = float(net.sgen.at[i, "sn_mva"])
        net.sgen.at[i, "p_mw"] = 0.65 * s_mva

    pp.runpp(net)

    # Convergence
    assert bool(net["converged"]), "pp.runpp did not converge"

    # Voltage bounds
    vm = net.res_bus.vm_pu.dropna().values
    assert (vm >= 0.95).all() and (vm <= 1.05).all(), (
        f"voltage out of [0.95, 1.05] pu: min={vm.min():.4f}, max={vm.max():.4f}"
    )
