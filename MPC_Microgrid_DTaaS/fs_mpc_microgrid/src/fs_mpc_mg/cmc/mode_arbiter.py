"""Mode arbiter — finite-state machine for grid/island/transition.

States:
    grid          : tie switch closed, MG synchronized with grid
    transition    : transient state during opening/closing sequence (≤100 ms target)
    island        : tie switch open, MG forming its own voltage
    black_start   : islanded re-energization sequence after total outage
    fault         : safety latch — all ICAs commanded mode='fault'

Transitions are triggered by external events (manual command or detected
loss-of-grid). The arbiter is **stateful** and **deterministic** — same
inputs always produce the same next state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time


class SystemMode(str, Enum):
    GRID = "grid"
    TRANSITION = "transition"
    ISLAND = "island"
    BLACK_START = "black_start"
    FAULT = "fault"


@dataclass
class ModeArbiter:
    """Drives mode transitions based on event inputs and timers."""

    mode: SystemMode = SystemMode.GRID
    transition_started_ts: float = 0.0
    transition_timeout_s: float = 0.1   # 100 ms per implementation plan
    last_transition_reason: str = ""

    # ----- event inputs -----------------------------------------------
    def loss_of_grid(self, now: float) -> SystemMode:
        if self.mode in (SystemMode.GRID, SystemMode.TRANSITION):
            self._start_transition("loss_of_grid", now)
        return self.mode

    def grid_restored(self, now: float) -> SystemMode:
        if self.mode == SystemMode.ISLAND:
            self._start_transition("grid_restored", now)
        return self.mode

    def request_black_start(self, now: float) -> SystemMode:
        if self.mode in (SystemMode.ISLAND, SystemMode.FAULT):
            self.mode = SystemMode.BLACK_START
            self.last_transition_reason = "manual_black_start"
        return self.mode

    def black_start_complete(self) -> SystemMode:
        if self.mode == SystemMode.BLACK_START:
            self.mode = SystemMode.ISLAND
            self.last_transition_reason = "black_start_complete"
        return self.mode

    def declare_fault(self, reason: str) -> SystemMode:
        self.mode = SystemMode.FAULT
        self.last_transition_reason = f"fault: {reason}"
        return self.mode

    def clear_fault(self) -> SystemMode:
        if self.mode == SystemMode.FAULT:
            self.mode = SystemMode.ISLAND   # operator must black-start to grid
            self.last_transition_reason = "fault_cleared"
        return self.mode

    # ----- internals --------------------------------------------------
    def _start_transition(self, reason: str, now: float) -> None:
        self.mode = SystemMode.TRANSITION
        self.transition_started_ts = now
        self.last_transition_reason = reason

    # ----- periodic update --------------------------------------------
    def tick(self, now: float, grid_present: bool) -> SystemMode:
        """Called at every CMC dispatch tick. Resolves TRANSITION timeouts."""
        if self.mode == SystemMode.TRANSITION:
            if (now - self.transition_started_ts) > self.transition_timeout_s:
                self.mode = SystemMode.GRID if grid_present else SystemMode.ISLAND
                self.last_transition_reason = "transition_timeout"
        return self.mode

    # ----- helper for ICA dispatch ------------------------------------
    def ica_command_mode(self) -> str:
        """Map the system-level mode to the per-ICA mode string."""
        if self.mode == SystemMode.FAULT:
            return "fault"
        if self.mode == SystemMode.BLACK_START:
            return "idle"   # black-start requires staged enable; idle until ready
        return "running"
