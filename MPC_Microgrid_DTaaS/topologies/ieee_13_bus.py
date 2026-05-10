"""ieee_13_bus — TODO: fill in bus/load/line data."""

from fs_mpc_mg.cmc import Topology, BusNode, ICANode, LoadNode
from fs_mpc_mg.cmc.topology import SwitchEdge


def build() -> Topology:
    t = Topology()
    t.add_bus(BusNode("grid", nominal_voltage=20_000.0, is_grid=True))
    t.add_bus(BusNode("pcc",  nominal_voltage=20_000.0))
    t.add_switch(SwitchEdge("tie", "grid", "pcc", closed=True))
    t.add_ica(ICANode("ica1", bus_id="pcc", s_max=200e3))
    t.add_load(LoadNode("aggregate", bus_id="pcc",
                         p_nominal=100e3, q_nominal=30e3, nonlinear=True))
    # TODO: replace with the real ieee_13_bus bus/line/load data.
    return t
