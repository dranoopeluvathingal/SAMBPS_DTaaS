"""Controller — the main CMC orchestrator.

At every dispatch tick (configurable; 1 Hz by default per the plan §3):

    1. Read snapshot from StateEstimator.
    2. Tick the ModeArbiter and resolve the system mode.
    3. Compute Q allocation across ICAs (QAllocator).
    4. Compute harmonic-absorption allocation (HAllocator).
    5. Publish references on the same pub/sub bus the agents listen to:
       /ica/{id}/refs/{v_dc_ref, Q_ref, H_mask, mode, enable}.

The Controller is *plant-agnostic* — it talks to ICAs purely via pub/sub.
This keeps it identical between offline simulation, MQTT-broker, and HIL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from ..comm.pubsub import PubSubBase
from ..comm.topics import topic_ref
from .topology import Topology
from .state_estimator import StateEstimator, FleetState
from .mode_arbiter import ModeArbiter, SystemMode
from .q_allocator import QAllocator
from .h_allocator import HAllocator


@dataclass
class ControllerConfig:
    tick_period_s: float = 1.0          # dispatch period
    v_dc_ref_default: float = 900.0     # nominal target
    q_total_target: float = 0.0         # VAr target across the fleet
    use_qp: bool = False
    enable_on_start: bool = True
    voltage_droop_v_per_var: float = 0.0  # placeholder for secondary droop


class Controller:
    """Centralized microgrid controller.

    Lifecycle:
        ctrl = Controller(topology, pubsub, config)
        ctrl.start()                    # publishes initial enable + mode
        for ...:
            ctrl.tick(now)              # one dispatch
    """

    def __init__(
        self,
        topology: Topology,
        pubsub: PubSubBase,
        config: ControllerConfig | None = None,
    ) -> None:
        self.topology = topology
        self.pubsub = pubsub
        self.cfg = config or ControllerConfig()
        self.estimator = StateEstimator(topology, pubsub)
        self.arbiter = ModeArbiter()
        self.q_alloc = QAllocator(topology)
        self.h_alloc = HAllocator(topology)
        self._last_tick_ts: float = 0.0
        self._dispatch_log: list[dict] = []

    # ------------------------------------------------------------------
    def start(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        for ica_id in self.topology.icas:
            self.pubsub.publish_value(topic_ref(ica_id, "v_dc_ref"), self.cfg.v_dc_ref_default)
            self.pubsub.publish_value(topic_ref(ica_id, "mode"), self.arbiter.ica_command_mode())
            self.pubsub.publish_value(topic_ref(ica_id, "enable"), bool(self.cfg.enable_on_start))
        self._last_tick_ts = now

    # ------------------------------------------------------------------
    def tick(self, now: float | None = None, grid_present: bool = True) -> dict:
        """One dispatch tick. Returns the published ref bundle for inspection."""
        now = now if now is not None else time.time()

        # 1. State
        fleet: FleetState = self.estimator.snapshot(now)

        # 2. Mode
        sys_mode: SystemMode = self.arbiter.tick(now, grid_present=grid_present)
        ica_mode = self.arbiter.ica_command_mode()

        # 3. Q allocation
        q_alloc = self.q_alloc.allocate(self.cfg.q_total_target, fleet, prefer_qp=self.cfg.use_qp)

        # 4. H allocation
        h_alloc = self.h_alloc.allocate(fleet)

        # 5. Publish per-ICA refs
        published = {}
        for ica_id in self.topology.icas:
            refs = {
                "mode": ica_mode,
                "enable": (sys_mode != SystemMode.FAULT) and self.cfg.enable_on_start,
                "v_dc_ref": self.cfg.v_dc_ref_default,
                "Q_ref": q_alloc.get(ica_id, 0.0),
                "H_mask": h_alloc.masks.get(ica_id, {h: True for h in self.h_alloc.orders}),
            }
            for key, value in refs.items():
                self.pubsub.publish_value(topic_ref(ica_id, key), value)
            published[ica_id] = refs

        record = {"ts": now, "sys_mode": sys_mode.value, "fleet_size": len(fleet.icas),
                  "n_active": fleet.n_active(), "q_total_target": self.cfg.q_total_target,
                  "published": published}
        self._dispatch_log.append(record)
        self._last_tick_ts = now
        return record

    # ------------------------------------------------------------------
    @property
    def log(self) -> list[dict]:
        return list(self._dispatch_log)

    def declare_fault(self, reason: str) -> None:
        self.arbiter.declare_fault(reason)

    def open_grid_tie(self, now: float | None = None) -> None:
        sw = self.topology.grid_tie_switch()
        if sw is not None:
            sw.closed = False
        self.arbiter.loss_of_grid(now if now is not None else time.time())

    def close_grid_tie(self, now: float | None = None) -> None:
        sw = self.topology.grid_tie_switch()
        if sw is not None:
            sw.closed = True
        self.arbiter.grid_restored(now if now is not None else time.time())
