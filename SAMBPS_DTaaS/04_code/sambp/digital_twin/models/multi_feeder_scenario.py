# =============================================================================
# sambp / digital_twin / models / multi_feeder_scenario.py
#
# Multi-feeder sympathetic-tripping scenario library — TR-78 WP 78.2
#
# 15 scenarios across 3 groups:
#   Group A (1–5)  : 2-feeder bus, fault on feeder-0, sympathetic on feeder-1
#   Group B (6–10) : 3-feeder bus, fault on feeder-0, sympathetics on 1 and 2
#   Group C (11–15): False-positive guard — genuine simultaneous faults / healthy
#
# Each scenario produces a sequence of (t, currents_pu) samples
# that exercise SympatheticTripMonitor across the decision space.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class MultiFeederScenario:
    id:               int
    name:             str
    group:            str          # "SYMP_2F" | "SYMP_3F" | "GUARD"
    n_feeders:        int
    fault_feeder_idx: int          # -1 if no single fault feeder
    # Sequence of (time_s, currents_pu list)
    samples:          List[Tuple[float, List[float]]] = field(default_factory=list)
    # Expected action for feeder 0,1,... at the last sample
    expected_actions: List[str] = field(default_factory=list)
    description:      str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ramp(i_start: float, i_end: float, n: int) -> List[float]:
    if n <= 1:
        return [i_end]
    return [i_start + (i_end - i_start) * k / (n - 1) for k in range(n)]


def _samples_2f(fault_I: float, symp_I: float, n: int = 5) -> List[Tuple[float, List[float]]]:
    """2-feeder: feeder-0 faults (fast rise), feeder-1 sympathetic (slow rise)."""
    i0 = _ramp(1.0, fault_I, n)
    i1 = _ramp(1.0, symp_I,  n)
    return [(0.02 * k, [i0[k], i1[k]]) for k in range(n)]


def _samples_3f(fault_I: float, symp_I: float, n: int = 5) -> List[Tuple[float, List[float]]]:
    """3-feeder: feeder-0 faults, feeders 1 & 2 sympathetic."""
    i0 = _ramp(1.0, fault_I, n)
    i1 = _ramp(1.0, symp_I,  n)
    i2 = _ramp(1.0, symp_I * 0.95, n)
    return [(0.02 * k, [i0[k], i1[k], i2[k]]) for k in range(n)]


# ---------------------------------------------------------------------------
# Scenario factory
# ---------------------------------------------------------------------------

def build_scenarios() -> List[MultiFeederScenario]:
    scens: List[MultiFeederScenario] = []

    # ── Group A: 2-feeder sympathetic ────────────────────────────────────────
    group_a = [
        (1,  "A01_2f_symp_light",  2.5, 1.35, "2-feeder, light fault, sympathetic on F1"),
        (2,  "A02_2f_symp_medium", 3.0, 1.45, "2-feeder, medium fault, sympathetic on F1"),
        (3,  "A03_2f_symp_heavy",  4.0, 1.55, "2-feeder, heavy fault, sympathetic on F1"),
        (4,  "A04_2f_symp_severe", 5.5, 1.60, "2-feeder, severe fault, sympathetic on F1"),
        (5,  "A05_2f_symp_3ph",    6.0, 1.65, "2-feeder, 3PH fault, sympathetic on F1"),
    ]
    for sid, name, fi, si, desc in group_a:
        scens.append(MultiFeederScenario(
            id=sid, name=name, group="SYMP_2F", n_feeders=2,
            fault_feeder_idx=0,
            samples=_samples_2f(fi, si),
            expected_actions=["FAULT_FEEDER", "BLOCK"],
            description=desc,
        ))

    # ── Group B: 3-feeder sympathetic ────────────────────────────────────────
    group_b = [
        (6,  "B06_3f_symp_light",  2.5, 1.30, "3-feeder, light fault"),
        (7,  "B07_3f_symp_medium", 3.0, 1.40, "3-feeder, medium fault"),
        (8,  "B08_3f_symp_heavy",  4.0, 1.50, "3-feeder, heavy fault"),
        (9,  "B09_3f_symp_severe", 5.0, 1.55, "3-feeder, severe fault"),
        (10, "B10_3f_symp_ibr",    6.0, 1.60, "3-feeder, IBR-boosted fault"),
    ]
    for sid, name, fi, si, desc in group_b:
        scens.append(MultiFeederScenario(
            id=sid, name=name, group="SYMP_3F", n_feeders=3,
            fault_feeder_idx=0,
            samples=_samples_3f(fi, si),
            expected_actions=["FAULT_FEEDER", "BLOCK", "BLOCK"],
            description=desc,
        ))

    # ── Group C: Guard cases ─────────────────────────────────────────────────
    guard_cases = [
        # (id, name, n_f, samples_func, expected, desc)
        (11, "C11_simultaneous_faults",
         2, _samples_2f(3.0, 3.5),
         ["FAULT_FEEDER", "FAULT_FEEDER"],
         "Simultaneous genuine faults — both should be FAULT_FEEDER or PERMIT"),
        (12, "C12_healthy_no_fault",
         2, [(0.0, [0.8, 0.9]), (0.02, [0.8, 0.9]), (0.04, [0.8, 0.9])],
         ["PERMIT", "PERMIT"],
         "Healthy feeders below threshold — PERMIT"),
        (13, "C13_single_feeder_no_symp",
         2, [(0.0, [1.0, 1.0]), (0.02, [3.0, 1.0]), (0.04, [4.0, 1.05])],
         ["FAULT_FEEDER", "PERMIT"],
         "Fault only on F0, F1 stays healthy — F1 PERMIT not BLOCK"),
        (14, "C14_3f_healthy",
         3, [(0.0, [0.9, 0.8, 0.85]), (0.02, [0.9, 0.8, 0.85])],
         ["PERMIT", "PERMIT", "PERMIT"],
         "3-feeder all healthy — all PERMIT"),
        (15, "C15_block_timeout",
         2, _samples_2f(4.0, 1.50),
         ["FAULT_FEEDER", "BLOCK"],
         "Sympathetic block active within timeout window"),
    ]
    for sid, name, n_f, samps, exp, desc in guard_cases:
        scens.append(MultiFeederScenario(
            id=sid, name=name, group="GUARD", n_feeders=n_f,
            fault_feeder_idx=0 if any("fault" in name.lower() for _ in [1]) else -1,
            samples=samps,
            expected_actions=exp,
            description=desc,
        ))

    return scens


class MultiFeederScenarioLibrary:
    """Container for the 15 multi-feeder sympathetic-tripping scenarios."""

    def __init__(self) -> None:
        self._scenarios = build_scenarios()

    def __len__(self) -> int:
        return len(self._scenarios)

    def __iter__(self):
        return iter(self._scenarios)

    def __getitem__(self, idx: int) -> MultiFeederScenario:
        return self._scenarios[idx]

    def get_by_group(self, group: str) -> List[MultiFeederScenario]:
        return [s for s in self._scenarios if s.group == group]

    def get_by_id(self, scenario_id: int) -> MultiFeederScenario:
        for s in self._scenarios:
            if s.id == scenario_id:
                return s
        raise KeyError(scenario_id)
