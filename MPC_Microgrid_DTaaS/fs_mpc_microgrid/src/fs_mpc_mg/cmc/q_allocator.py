"""Reactive-power allocator — splits a Q_total target across the ICA fleet.

Two implementations:

1. ``allocate_proportional`` — closed-form, no dependencies. Distributes Q
   in proportion to each ICA's available reactive headroom
   ``Q_i_max = sqrt(S_i_max^2 - P_i^2)``. Always feasible, fast.

2. ``allocate_qp`` — convex QP via cvxpy if installed:

       minimize    sum_i  (Q_i - share_i)^2
       subject to  |Q_i| <= Q_i_max
                   sum_i Q_i = Q_total_target

   The QP form is the placeholder for the larger optimisation in §9 of the
   plan (which adds bus-voltage error and per-ICA weights). Falls back to
   the proportional version if cvxpy is not available.
"""

from __future__ import annotations

import math
from .state_estimator import FleetState
from .topology import Topology


class QAllocator:
    def __init__(self, topology: Topology) -> None:
        self.topology = topology

    # ------------------------------------------------------------------
    def _per_ica_p_estimate(self, snap) -> float:
        """Estimate fundamental P_i (W) from telemetry as `(3/2) V_peak * I_peak`."""
        v_peak = max(abs(x) for x in snap.v_s_abc) if any(snap.v_s_abc) else 310.0
        i_peak = snap.fundamental_amplitude()
        return 1.5 * v_peak * i_peak * 0.7   # crude PF≈0.7 fallback

    def _per_ica_q_max(self, ica_id: str, p_i: float) -> float:
        s_max = self.topology.icas[ica_id].s_max
        return math.sqrt(max(s_max * s_max - p_i * p_i, 0.0))

    # ------------------------------------------------------------------
    def allocate_proportional(self, q_total: float, fleet: FleetState) -> dict[str, float]:
        """Closed-form proportional allocation respecting per-ICA capability."""
        active = [i for i in fleet.icas.values() if i.enabled and i.mode == "running"]
        if not active:
            return {}
        q_max = {i.ica_id: self._per_ica_q_max(i.ica_id, self._per_ica_p_estimate(i)) for i in active}
        total_max = sum(q_max.values())
        if total_max <= 0.0:
            return {i.ica_id: 0.0 for i in active}
        # Clip target into feasible aggregate
        q_total = max(min(q_total, total_max), -total_max)
        return {iid: q_total * (q_max[iid] / total_max) for iid in q_max}

    # ------------------------------------------------------------------
    def allocate_qp(self, q_total: float, fleet: FleetState) -> dict[str, float]:
        """Convex QP via cvxpy. Falls back to proportional if cvxpy missing."""
        try:
            import cvxpy as cp
            import numpy as np
        except ImportError:
            return self.allocate_proportional(q_total, fleet)

        active = [i for i in fleet.icas.values() if i.enabled and i.mode == "running"]
        if not active:
            return {}
        n = len(active)
        ids = [i.ica_id for i in active]
        p_i = np.array([self._per_ica_p_estimate(i) for i in active])
        q_max = np.array([self._per_ica_q_max(iid, pp) for iid, pp in zip(ids, p_i)])
        share = q_total * (q_max / max(q_max.sum(), 1e-9))

        Q = cp.Variable(n)
        objective = cp.Minimize(cp.sum_squares(Q - share))
        constraints = [Q >= -q_max, Q <= q_max, cp.sum(Q) == q_total]
        prob = cp.Problem(objective, constraints)
        try:
            prob.solve(solver=cp.OSQP, verbose=False)
        except Exception:
            return self.allocate_proportional(q_total, fleet)
        if Q.value is None:
            return self.allocate_proportional(q_total, fleet)
        return {ids[k]: float(Q.value[k]) for k in range(n)}

    # ------------------------------------------------------------------
    def allocate(self, q_total: float, fleet: FleetState, prefer_qp: bool = False) -> dict[str, float]:
        return (self.allocate_qp if prefer_qp else self.allocate_proportional)(q_total, fleet)
