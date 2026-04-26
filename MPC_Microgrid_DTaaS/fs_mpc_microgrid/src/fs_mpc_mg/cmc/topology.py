"""Topology — directed graph of buses, ICAs, loads, and switches.

The CMC needs an explicit topology so that:
  - the Q-allocator knows which ICAs share a PCC,
  - the mode-arbiter knows which switch separates grid from island,
  - the state-estimator can attribute load currents to buses.

For the Phase-2 skeleton we provide a minimal but extensible graph. The
focal use case is: 1 grid bus -> tie switch -> 1 PCC bus with N ICAs and 1
aggregated load.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class BusNode:
    bus_id: str
    nominal_voltage: float = 380.0      # line-line RMS V
    is_grid: bool = False                # True if this is the external-grid bus


@dataclass
class ICANode:
    ica_id: str
    bus_id: str                          # bus this ICA attaches to
    s_max: float = 100e3                 # apparent-power rating (VA)
    v_dc_nominal: float = 900.0


@dataclass
class LoadNode:
    load_id: str
    bus_id: str
    p_nominal: float = 0.0               # W
    q_nominal: float = 0.0               # VAr
    nonlinear: bool = False              # rectifier-style harmonic source


@dataclass
class SwitchEdge:
    """A breaker/contactor between two buses. Closed means the buses are tied."""
    switch_id: str
    bus_a: str
    bus_b: str
    closed: bool = True


@dataclass
class Topology:
    buses: dict[str, BusNode] = field(default_factory=dict)
    icas: dict[str, ICANode]  = field(default_factory=dict)
    loads: dict[str, LoadNode] = field(default_factory=dict)
    switches: dict[str, SwitchEdge] = field(default_factory=dict)

    # ------------------------------------------------------------------ adders
    def add_bus(self, bus: BusNode) -> "Topology":
        self.buses[bus.bus_id] = bus
        return self

    def add_ica(self, ica: ICANode) -> "Topology":
        if ica.bus_id not in self.buses:
            raise KeyError(f"ICA {ica.ica_id}: bus {ica.bus_id} not in topology")
        self.icas[ica.ica_id] = ica
        return self

    def add_load(self, load: LoadNode) -> "Topology":
        if load.bus_id not in self.buses:
            raise KeyError(f"Load {load.load_id}: bus {load.bus_id} not in topology")
        self.loads[load.load_id] = load
        return self

    def add_switch(self, sw: SwitchEdge) -> "Topology":
        for bid in (sw.bus_a, sw.bus_b):
            if bid not in self.buses:
                raise KeyError(f"Switch {sw.switch_id}: bus {bid} not in topology")
        self.switches[sw.switch_id] = sw
        return self

    # ----------------------------------------------------------------- queries
    def icas_on_bus(self, bus_id: str) -> list[ICANode]:
        return [i for i in self.icas.values() if i.bus_id == bus_id]

    def loads_on_bus(self, bus_id: str) -> list[LoadNode]:
        return [l for l in self.loads.values() if l.bus_id == bus_id]

    def grid_tie_switch(self) -> SwitchEdge | None:
        for sw in self.switches.values():
            if self.buses[sw.bus_a].is_grid or self.buses[sw.bus_b].is_grid:
                return sw
        return None

    def is_islanded(self) -> bool:
        gts = self.grid_tie_switch()
        return gts is not None and not gts.closed

    # ------------------------------------------------------------------ debug
    def summary(self) -> str:
        lines = [
            f"Topology: {len(self.buses)} buses, {len(self.icas)} ICAs, "
            f"{len(self.loads)} loads, {len(self.switches)} switches"
        ]
        for b in self.buses.values():
            tag = " [GRID]" if b.is_grid else ""
            lines.append(f"  bus {b.bus_id}{tag} V={b.nominal_voltage:.0f}")
        for i in self.icas.values():
            lines.append(f"  ica {i.ica_id} -> bus {i.bus_id} S_max={i.s_max/1e3:.0f} kVA")
        for l in self.loads.values():
            kind = "NL" if l.nonlinear else "L"
            lines.append(f"  load {l.load_id} -> bus {l.bus_id} P={l.p_nominal/1e3:.0f} kW [{kind}]")
        for s in self.switches.values():
            state = "CLOSED" if s.closed else "OPEN"
            lines.append(f"  switch {s.switch_id}: {s.bus_a} <-> {s.bus_b} [{state}]")
        return "\n".join(lines)
