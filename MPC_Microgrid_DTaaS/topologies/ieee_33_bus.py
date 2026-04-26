"""IEEE 33-bus radial distribution test feeder.

Reference: M. E. Baran and F. F. Wu, "Network Reconfiguration in
Distribution Systems for Loss Reduction and Load Balancing," IEEE Trans.
Power Delivery, 1989.

Standard test case for radial distribution-system DG integration studies.
This stub fills in the bus topology; line impedances and full load data
should be filled in from the standard IEEE PES tables.
"""

from __future__ import annotations

from fs_mpc_mg.cmc import Topology, BusNode, ICANode, LoadNode
from fs_mpc_mg.cmc.topology import SwitchEdge


def build() -> Topology:
    t = Topology()
    t.add_bus(BusNode("grid", nominal_voltage=12_660.0, is_grid=True))
    for i in range(1, 34):
        t.add_bus(BusNode(f"bus{i}", nominal_voltage=12_660.0))
    t.add_switch(SwitchEdge("substation", "grid", "bus1", closed=True))

    # Add 4 PV + 2 BESS at typical locations from literature
    pv_buses = [6, 13, 24, 30]
    bess_buses = [18, 33]
    for k, b in enumerate(pv_buses):
        t.add_ica(ICANode(f"ica_pv{k+1}", bus_id=f"bus{b}", s_max=500e3))
    for k, b in enumerate(bess_buses):
        t.add_ica(ICANode(f"ica_bess{k+1}", bus_id=f"bus{b}", s_max=1_000e3))

    # Standard bus loads (placeholder — copy from IEEE 33-bus table)
    typical_p = {2: 100, 3: 90, 4: 120, 5: 60, 6: 60, 7: 200, 8: 200,
                 9: 60, 10: 60, 11: 45, 12: 60, 13: 60, 14: 120, 15: 60,
                 16: 60, 17: 60, 18: 90, 19: 90, 20: 90, 21: 90, 22: 90,
                 23: 90, 24: 420, 25: 420, 26: 60, 27: 60, 28: 60, 29: 120,
                 30: 200, 31: 150, 32: 210, 33: 60}
    for b, p_kw in typical_p.items():
        t.add_load(LoadNode(f"load{b}", bus_id=f"bus{b}",
                             p_nominal=p_kw * 1e3, q_nominal=p_kw * 0.4 * 1e3,
                             nonlinear=(b in (24, 30))))   # mark a few as nonlinear
    return t
