"""Centralized Microgrid Controller (CMC) layer.

Implements the Layer-2 functional decomposition from the implementation plan
(§8). The CMC subscribes to all ICA telemetry, maintains a fleet state,
arbitrates mode (grid/island/transition), and dispatches references
(v_dc_ref, Q_ref, H_mask, mode, enable) to each ICA via the same pub/sub
abstraction the agent uses.

Public API:
    Topology         — graph of buses/ICAs/loads
    FleetState       — aggregated telemetry snapshot
    StateEstimator   — subscribes to ICA telemetry, builds FleetState
    ModeArbiter      — finite-state machine for system mode
    QAllocator       — splits a Q_total target across ICAs (proportional or QP)
    HAllocator       — splits load harmonics by ICA headroom
    Controller       — orchestrates the periodic dispatch tick
"""

from .topology import Topology, BusNode, ICANode, LoadNode
from .state_estimator import FleetState, ICASnapshot, StateEstimator
from .mode_arbiter import ModeArbiter, SystemMode
from .q_allocator import QAllocator
from .h_allocator import HAllocator
from .controller import Controller, ControllerConfig

__all__ = [
    "Topology",
    "BusNode",
    "ICANode",
    "LoadNode",
    "FleetState",
    "ICASnapshot",
    "StateEstimator",
    "ModeArbiter",
    "SystemMode",
    "QAllocator",
    "HAllocator",
    "Controller",
    "ControllerConfig",
]
