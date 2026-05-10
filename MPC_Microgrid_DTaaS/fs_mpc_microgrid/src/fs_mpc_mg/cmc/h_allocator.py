"""Harmonic-absorption allocator.

Per the implementation plan §11 (the novel coordination contribution):
total harmonic load `i_l_h` for each order `h ∈ {5, 7, 11, 13}` is split
across the ICA fleet in proportion to *available current headroom*:

    H_i_h = i_l_h_total * (S_i_max - |I_i_fund|) / sum_j (S_j_max - |I_j_fund|)

The per-ICA result is published as a per-order *boolean mask* (compatible
with the existing ICAAgent topic schema) plus a quantitative fraction that
the agent can use to scale its compensation effort.

This skeleton emits the mask. The fractional weighting is recorded in the
returned dict so a future, finer-grained ICA can use it directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .state_estimator import FleetState
from .topology import Topology


DEFAULT_ORDERS: tuple[int, ...] = (5, 7, 11, 13)


@dataclass
class HAllocation:
    """Result of a harmonic allocation tick."""
    fractions: dict[str, dict[int, float]] = field(default_factory=dict)   # {ica_id: {h: 0..1}}
    masks: dict[str, dict[int, bool]] = field(default_factory=dict)         # {ica_id: {h: True/False}}


class HAllocator:
    def __init__(self, topology: Topology, orders: Iterable[int] = DEFAULT_ORDERS,
                 mask_threshold: float = 0.05) -> None:
        self.topology = topology
        self.orders = tuple(orders)
        self.mask_threshold = mask_threshold

    # ------------------------------------------------------------------
    def _headroom(self, ica_snap) -> float:
        s_max = self.topology.icas[ica_snap.ica_id].s_max
        # crude conversion: assume nominal 380 V LL phase peak ~310 V.
        v_peak = 310.0
        i_max = s_max / (1.5 * v_peak)
        i_fund = ica_snap.fundamental_amplitude()
        return max(i_max - i_fund, 0.0)

    # ------------------------------------------------------------------
    def allocate(self, fleet: FleetState) -> HAllocation:
        active = [s for s in fleet.icas.values() if s.enabled and s.mode == "running"]
        if not active:
            return HAllocation()

        head = {s.ica_id: self._headroom(s) for s in active}
        total_head = sum(head.values()) or 1e-9
        fractions: dict[str, dict[int, float]] = {}
        masks: dict[str, dict[int, bool]] = {}
        for s in active:
            f = head[s.ica_id] / total_head
            fractions[s.ica_id] = {h: f for h in self.orders}
            masks[s.ica_id] = {h: f >= self.mask_threshold for h in self.orders}
        return HAllocation(fractions=fractions, masks=masks)
