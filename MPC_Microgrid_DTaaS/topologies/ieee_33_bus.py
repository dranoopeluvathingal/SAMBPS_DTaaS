"""IEEE 33-bus radial distribution test feeder.

Reference: M. E. Baran and F. F. Wu, "Network Reconfiguration in
Distribution Systems for Loss Reduction and Load Balancing," IEEE Trans.
Power Delivery, 1989.

Line impedances are the canonical Baran-Wu values, transcribed from
`pandapower.networks.case33bw` (pandapower 3.4.0).
"""

from __future__ import annotations

from fs_mpc_mg.cmc import Topology, BusNode, ICANode, LoadNode
from fs_mpc_mg.cmc.topology import SwitchEdge, LineEdge


# 32 series feeder lines: (from_bus_idx, to_bus_idx, length_km, R_ohm_per_km, X_ohm_per_km).
# Extracted from pandapower.networks.case33bw, indices shifted +1 to match our 1-indexed
# "bus1".."bus33" naming (pandapower uses 0-indexed bus 0 as the substation head).
_LINES: tuple[tuple[int, int, float, float, float], ...] = (
    ( 1,  2, 1.0, 0.0922, 0.0470),
    ( 2,  3, 1.0, 0.4930, 0.2511),
    ( 3,  4, 1.0, 0.3660, 0.1864),
    ( 4,  5, 1.0, 0.3811, 0.1941),
    ( 5,  6, 1.0, 0.8190, 0.7070),
    ( 6,  7, 1.0, 0.1872, 0.6188),
    ( 7,  8, 1.0, 0.7114, 0.2351),
    ( 8,  9, 1.0, 1.0300, 0.7400),
    ( 9, 10, 1.0, 1.0440, 0.7400),
    (10, 11, 1.0, 0.1966, 0.0650),
    (11, 12, 1.0, 0.3744, 0.1238),
    (12, 13, 1.0, 1.4680, 1.1550),
    (13, 14, 1.0, 0.5416, 0.7129),
    (14, 15, 1.0, 0.5910, 0.5260),
    (15, 16, 1.0, 0.7463, 0.5450),
    (16, 17, 1.0, 1.2890, 1.7210),
    (17, 18, 1.0, 0.7320, 0.5740),
    ( 2, 19, 1.0, 0.1640, 0.1565),
    (19, 20, 1.0, 1.5042, 1.3554),
    (20, 21, 1.0, 0.4095, 0.4784),
    (21, 22, 1.0, 0.7089, 0.9373),
    ( 3, 23, 1.0, 0.4512, 0.3083),
    (23, 24, 1.0, 0.8980, 0.7091),
    (24, 25, 1.0, 0.8960, 0.7011),
    ( 6, 26, 1.0, 0.2030, 0.1034),
    (26, 27, 1.0, 0.2842, 0.1447),
    (27, 28, 1.0, 1.0590, 0.9337),
    (28, 29, 1.0, 0.8042, 0.7006),
    (29, 30, 1.0, 0.5075, 0.2585),
    (30, 31, 1.0, 0.9744, 0.9630),
    (31, 32, 1.0, 0.3105, 0.3619),
    (32, 33, 1.0, 0.3410, 0.5302),
)


def build() -> Topology:
    t = Topology()
    t.add_bus(BusNode("grid", nominal_voltage=12_660.0, is_grid=True))
    for i in range(1, 34):
        t.add_bus(BusNode(f"bus{i}", nominal_voltage=12_660.0))
    t.add_switch(SwitchEdge("substation", "grid", "bus1", closed=True))

    for k, (a, b, length, r, x) in enumerate(_LINES, start=1):
        t.add_line(LineEdge(
            line_id=f"L{k:02d}", bus_a=f"bus{a}", bus_b=f"bus{b}",
            r_ohm_per_km=r, x_ohm_per_km=x, length_km=length,
        ))

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
