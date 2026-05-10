"""Convert a fs_mpc_mg.cmc.Topology into a pandapower network.

Element-to-element mapping
--------------------------

| fs_mpc_mg            | pandapower                              |
|----------------------|-----------------------------------------|
| `BusNode`            | `pp.create_bus(vn_kv=...)`              |
| `BusNode(is_grid=True)` | bus + `pp.create_ext_grid(vm_pu=1.0)` |
| `LoadNode`           | `pp.create_load(p_mw, q_mvar)`          |
| `ICANode`            | `pp.create_sgen(controllable=True)`     |
| `SwitchEdge`         | `pp.create_switch(et='b')` (bus-bus)    |
| `LineEdge`           | `pp.create_line_from_parameters(...)`   |

s_max mapping (the non-trivial part)
------------------------------------

Our `ICANode.s_max` is the **apparent-power rating** of an inverter — the
true constraint is the circle |P + jQ| ≤ s_max. Pandapower's
`controllable=True` sgen exposes only **box constraints**:

    min_p_mw ≤ p_mw ≤ max_p_mw
    min_q_mvar ≤ q_mvar ≤ max_q_mvar

There is no native "apparent power" constraint on an sgen; the circle
constraint must be added separately at the OPF level (e.g. via a
`pp.create_polygonal_characteristic` or by adding a manual constraint to
the optimisation model). We map conservatively:

    max_p_mw   = +s_max / 1e6      min_p_mw   = -s_max / 1e6
    max_q_mvar = +s_max / 1e6      min_q_mvar = -s_max / 1e6
    sn_mva     =  s_max / 1e6      (apparent-power rating, advisory)

This **box is a superset of the true circle**: it permits the corner
points (P=s_max, Q=s_max) which would violate apparent-power capability.
For OPF use this means downstream code must either:

  (a) accept the conservative bound and post-solve verify
      sqrt(p² + q²) ≤ s_max, or
  (b) add an explicit apparent-power constraint to the OPF model.

For pure load-flow (`pp.runpp`) the limits are not enforced at all — only
the operating-point setpoints `p_mw` / `q_mvar` matter. The adapter
defaults those to 0 (sgen "off") so the converted network solves the
load flow with the converters acting as observers; the caller can write
non-zero setpoints before `runpp` to model a dispatch scenario.

Active-sign convention
----------------------
Pandapower sgens use the **generator** sign convention: positive `p_mw`
means injection into the network. This matches our intuition (a PV
inverter "produces" P > 0). Loads use the **consumer** convention:
positive `p_mw` means consumption. `LoadNode.p_nominal > 0` ⇒ positive
`pp.create_load(p_mw=...)` ⇒ a real consumer.

Switch handling
---------------
`SwitchEdge` becomes a **bus-bus switch** in pandapower (`et="b"`). Note
that pandapower's bus-bus switches are *fused* by the load-flow solver —
they're zero-impedance connectors with no diagnostic value at runpp
time. If you need physical impedance between two buses, use a
`LineEdge`.

Returns
-------
The converted `pandapowerNet` with no load flow run yet. Callers
should set sgen dispatches as desired and then call `pp.runpp(net)`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pandapower.auxiliary import pandapowerNet

from fs_mpc_mg.cmc.topology import Topology


def topology_to_pandapower(topology: Topology) -> "pandapowerNet":
    """Convert a fs_mpc_mg `Topology` into a pandapower network.

    See module docstring for the element-to-element mapping and the
    documented s_max ↔ max_p_mw / max_q_mvar relationship.
    """
    import pandapower as pp

    net = pp.create_empty_network(name="fs_mpc_mg_topology")

    # 1. Buses (and ext_grid for any is_grid bus)
    bus_idx: dict[str, int] = {}
    for bus_id, bus in topology.buses.items():
        idx = pp.create_bus(
            net,
            name=bus_id,
            vn_kv=bus.nominal_voltage / 1_000.0,   # V → kV
        )
        bus_idx[bus_id] = idx
        if bus.is_grid:
            pp.create_ext_grid(net, bus=idx, vm_pu=1.0, name=f"ext_{bus_id}")

    # 2. Loads (consumer convention: positive p_mw = consumption)
    for load_id, load in topology.loads.items():
        pp.create_load(
            net,
            bus=bus_idx[load.bus_id],
            p_mw=load.p_nominal / 1e6,
            q_mvar=load.q_nominal / 1e6,
            name=load_id,
        )

    # 3. ICAs as controllable sgens. See module docstring for the s_max box-vs-circle
    # tradeoff.
    for ica_id, ica in topology.icas.items():
        s_mva = ica.s_max / 1e6
        pp.create_sgen(
            net,
            bus=bus_idx[ica.bus_id],
            p_mw=0.0,
            q_mvar=0.0,
            sn_mva=s_mva,
            max_p_mw=+s_mva,
            min_p_mw=-s_mva,
            max_q_mvar=+s_mva,
            min_q_mvar=-s_mva,
            controllable=True,
            name=ica_id,
        )

    # 4. Lines (impedance-bearing)
    for line_id, line in topology.lines.items():
        pp.create_line_from_parameters(
            net,
            from_bus=bus_idx[line.bus_a],
            to_bus=bus_idx[line.bus_b],
            length_km=line.length_km,
            r_ohm_per_km=line.r_ohm_per_km,
            x_ohm_per_km=line.x_ohm_per_km,
            c_nf_per_km=line.c_nf_per_km,
            max_i_ka=line.max_i_ka,
            name=line_id,
        )

    # 5. Switches (bus-bus, ideal connector)
    for switch_id, switch in topology.switches.items():
        pp.create_switch(
            net,
            bus=bus_idx[switch.bus_a],
            element=bus_idx[switch.bus_b],
            et="b",
            closed=switch.closed,
            name=switch_id,
        )

    return net
