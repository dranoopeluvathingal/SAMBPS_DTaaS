"""State estimator — aggregates ICA telemetry into a fleet-level snapshot.

Subscribes to /ica/{id}/tel/* topics for every ICA in the topology and
maintains the most-recent value for each. Provides a `FleetState` snapshot
on demand (called by the Controller at each dispatch tick).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from .topology import Topology
from ..comm.pubsub import PubSubBase
from ..comm.topics import topic_telemetry


@dataclass
class ICASnapshot:
    """Latest known state of one ICA."""
    ica_id: str
    v_dc: float = 0.0
    i_m_abc: tuple[float, float, float] = (0.0, 0.0, 0.0)
    i_s_abc: tuple[float, float, float] = (0.0, 0.0, 0.0)
    i_l_abc: tuple[float, float, float] = (0.0, 0.0, 0.0)
    v_s_abc: tuple[float, float, float] = (0.0, 0.0, 0.0)
    I_s_amp: float = 0.0
    s_applied: tuple[float, float, float] = (0.0, 0.0, 0.0)
    last_update_ts: float = 0.0
    last_heartbeat_ts: float = 0.0
    mode: str = "unknown"
    enabled: bool = False

    def is_stale(self, now: float, timeout_s: float = 0.5) -> bool:
        return (now - self.last_update_ts) > timeout_s

    def fundamental_amplitude(self) -> float:
        """Approximate peak fundamental |i_m| from instantaneous abc value."""
        # Crude: max(|i_m_abc|) is a proxy. A real estimator would do
        # SOGI/dq decomposition. Sufficient for headroom calculations.
        return max(abs(x) for x in self.i_m_abc)


@dataclass
class FleetState:
    """Aggregated snapshot of all ICAs at a given instant."""
    ts: float
    icas: dict[str, ICASnapshot] = field(default_factory=dict)

    def n_active(self) -> int:
        return sum(1 for s in self.icas.values() if s.enabled and s.mode == "running")

    def mean_v_dc(self) -> float:
        actives = [s.v_dc for s in self.icas.values() if s.enabled]
        return sum(actives) / len(actives) if actives else 0.0

    def total_i_l_a(self) -> float:
        """Sum of phase-a load current across all ICA observations.
        (One ICA's i_l reading at the PCC — first ICA is canonical.)"""
        if not self.icas:
            return 0.0
        first = next(iter(self.icas.values()))
        return first.i_l_abc[0]


class StateEstimator:
    """Subscribes to all ICA telemetry topics and answers ``snapshot()`` queries."""

    def __init__(self, topology: Topology, pubsub: PubSubBase):
        self.topology = topology
        self.pubsub = pubsub
        self._snaps: dict[str, ICASnapshot] = {}
        for ica_id in topology.icas:
            self._snaps[ica_id] = ICASnapshot(ica_id=ica_id)
            self._subscribe_ica(ica_id)

    # ------------------------------------------------------------------
    def _subscribe_ica(self, ica_id: str) -> None:
        for key in ("v_dc", "i_m_abc", "i_s_abc", "i_l_abc", "v_s_abc",
                    "I_s_amp", "s_applied", "heartbeat"):
            self.pubsub.subscribe(topic_telemetry(ica_id, key),
                                  self._make_handler(ica_id, key))

    def _make_handler(self, ica_id: str, key: str):
        def handler(_topic: str, payload: Any) -> None:
            if isinstance(payload, dict) and "value" in payload:
                value = payload["value"]
                ts = payload.get("ts", time.time())
            else:
                value, ts = payload, time.time()
            snap = self._snaps[ica_id]
            snap.last_update_ts = ts
            if key == "v_dc":
                snap.v_dc = float(value)
            elif key in ("i_m_abc", "i_s_abc", "i_l_abc", "v_s_abc", "s_applied"):
                setattr(snap, key, tuple(float(x) for x in value))
            elif key == "I_s_amp":
                snap.I_s_amp = float(value)
            elif key == "heartbeat":
                snap.last_heartbeat_ts = ts
                if isinstance(value, dict):
                    snap.mode = str(value.get("mode", snap.mode))
                    snap.enabled = bool(value.get("enabled", snap.enabled))
        return handler

    # ------------------------------------------------------------------
    def snapshot(self, ts: float | None = None) -> FleetState:
        ts = ts if ts is not None else time.time()
        return FleetState(ts=ts, icas={k: v for k, v in self._snaps.items()})

    def force_state(self, ica_id: str, **kwargs) -> None:
        """Test helper: directly set fields on an ICA snapshot."""
        if ica_id not in self._snaps:
            self._snaps[ica_id] = ICASnapshot(ica_id=ica_id)
        for k, v in kwargs.items():
            setattr(self._snaps[ica_id], k, v)
