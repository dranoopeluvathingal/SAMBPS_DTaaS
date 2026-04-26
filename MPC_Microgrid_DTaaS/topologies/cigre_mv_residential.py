"""CIGRE benchmark MV residential microgrid (subset).

Reference: CIGRE Task Force C6.04.02, "Benchmark Systems for Network
Integration of Renewable and Distributed Energy Resources", 2014.

This is a stub — buses and impedances are placeholders. Fill in line
data from the CIGRE report and add inverter ratings appropriate to the
study.
"""

from __future__ import annotations

from fs_mpc_mg.cmc import Topology, BusNode, ICANode, LoadNode
from fs_mpc_mg.cmc.topology import SwitchEdge


def build() -> Topology:
    t = Topology()
    # External grid bus
    t.add_bus(BusNode("grid", nominal_voltage=20_000.0, is_grid=True))
    # 11 internal buses (residential feeders)
    for i in range(1, 12):
        t.add_bus(BusNode(f"bus{i}", nominal_voltage=20_000.0))
    # Tie switch grid <-> bus1
    t.add_switch(SwitchEdge("grid_tie", "grid", "bus1", closed=True))
    # ICAs at PV/BESS connection points
    t.add_ica(ICANode("ica_pv1",  bus_id="bus3",  s_max=200e3))
    t.add_ica(ICANode("ica_pv2",  bus_id="bus6",  s_max=300e3))
    t.add_ica(ICANode("ica_bess", bus_id="bus10", s_max=500e3))
    t.add_ica(ICANode("ica_wind", bus_id="bus11", s_max=400e3))
    # Aggregated residential loads
    for i in (4, 7, 8, 9):
        t.add_load(LoadNode(f"load{i}", bus_id=f"bus{i}",
                             p_nominal=200e3, q_nominal=80e3, nonlinear=False))
    return t
