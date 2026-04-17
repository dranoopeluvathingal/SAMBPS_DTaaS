# =============================================================================
# sambp / digital_twin / models / fuse_failure_scenario.py
#
# Fuse-failure / open-conductor scenario library — TR-77 WP 77.2
#
# 20 scenarios across 4 groups:
#   Group A (1–5)  : Phase-A open conductor (overhead line break)
#   Group B (6–10) : Phase-B fuse failure (distribution feeder)
#   Group C (11–15): Phase-C open conductor under heavy load
#   Group D (16–20): Healthy / near-threshold ambiguous cases
#
# Each scenario produces synthetic SequenceExtractor output dicts
# (I2_I1_ratio, V2_V1_ratio, I0_I1_ratio, I2 phasor) that exercise
# OpenConductorDetector across the classification space.
# =============================================================================

from __future__ import annotations

import math
import cmath
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FuseFailureScenario:
    id:             int
    name:           str
    group:          str          # "A_OPEN" | "B_FUSE" | "C_OPEN" | "HEALTHY"
    open_phase:     str          # "A" | "B" | "C" | "NONE"
    load_mw:        float        # pre-fault load [MW]
    expected_action: str         # "OPEN_CONDUCTOR" | "HEALTHY" | "AMBIGUOUS"
    # Synthesised sequence ratios
    I2_I1_ratio:    float
    V2_V1_ratio:    float
    I0_I1_ratio:    float
    I2_angle_deg:   float        # angle of I2 phasor [°]
    description:    str = ""

    def to_seqs_dict(self) -> dict:
        """Return a seqs dict compatible with OpenConductorDetector.update()."""
        i2_mag = self.I2_I1_ratio
        i2_phasor = cmath.rect(i2_mag, math.radians(self.I2_angle_deg))
        return {
            'I2_I1_ratio': self.I2_I1_ratio,
            'V2_V1_ratio': self.V2_V1_ratio,
            'I0_I1_ratio': self.I0_I1_ratio,
            'I2': i2_phasor,
        }


# ---------------------------------------------------------------------------
# Open-phase angle references per phase
# ---------------------------------------------------------------------------
_ANG = {"A": -30.0, "B": 90.0, "C": -150.0}


def _oc_seqs(phase: str, load: float) -> tuple:
    """Generate typical open-conductor sequence ratios for a given phase + load."""
    # I2/I1 scales slightly with load level
    i21 = 0.55 + 0.10 * min(load / 5.0, 1.0)
    v21 = 0.20 + 0.05 * (load / 10.0)          # small V2 — no fault voltage collapse
    i01 = 0.50 + 0.05 * (load / 10.0)          # significant zero-sequence
    ang  = _ANG[phase]
    return i21, v21, i01, ang


def _fuse_seqs(phase: str, load: float) -> tuple:
    """Fuse failure: slightly less severe than open conductor."""
    i21 = 0.52 + 0.08 * min(load / 5.0, 1.0)
    v21 = 0.15 + 0.04 * (load / 10.0)
    i01 = 0.45 + 0.05 * (load / 10.0)
    ang  = _ANG[phase]
    return i21, v21, i01, ang


# ---------------------------------------------------------------------------
# Scenario factory
# ---------------------------------------------------------------------------

def build_scenarios() -> List[FuseFailureScenario]:
    scens: List[FuseFailureScenario] = []

    # ── Group A: Phase-A open conductor ──────────────────────────────────────
    for idx, (load, desc) in enumerate([
        (2.0, "A-open, light load 2 MW"),
        (5.0, "A-open, medium load 5 MW"),
        (8.0, "A-open, heavy load 8 MW"),
        (10.0, "A-open, near-rated load 10 MW"),
        (3.5, "A-open, intermediate load 3.5 MW"),
    ], start=1):
        i21, v21, i01, ang = _oc_seqs("A", load)
        scens.append(FuseFailureScenario(
            id=idx, name=f"A{idx:02d}_phA_open",
            group="A_OPEN", open_phase="A", load_mw=load,
            expected_action="OPEN_CONDUCTOR",
            I2_I1_ratio=round(i21, 3), V2_V1_ratio=round(v21, 3),
            I0_I1_ratio=round(i01, 3), I2_angle_deg=ang,
            description=desc,
        ))

    # ── Group B: Phase-B fuse failure ────────────────────────────────────────
    for idx, (load, desc) in enumerate([
        (1.5, "B-fuse, light load 1.5 MW"),
        (4.0, "B-fuse, medium load 4 MW"),
        (7.0, "B-fuse, heavy load 7 MW"),
        (9.5, "B-fuse, heavy load 9.5 MW"),
        (6.0, "B-fuse, medium-heavy 6 MW"),
    ], start=6):
        i21, v21, i01, ang = _fuse_seqs("B", load)
        scens.append(FuseFailureScenario(
            id=idx, name=f"B{idx:02d}_phB_fuse",
            group="B_FUSE", open_phase="B", load_mw=load,
            expected_action="OPEN_CONDUCTOR",
            I2_I1_ratio=round(i21, 3), V2_V1_ratio=round(v21, 3),
            I0_I1_ratio=round(i01, 3), I2_angle_deg=ang,
            description=desc,
        ))

    # ── Group C: Phase-C open conductor ──────────────────────────────────────
    for idx, (load, desc) in enumerate([
        (2.5, "C-open, light load 2.5 MW"),
        (5.5, "C-open, medium load 5.5 MW"),
        (8.5, "C-open, heavy load 8.5 MW"),
        (10.5, "C-open, overload 10.5 MW"),
        (4.5, "C-open, moderate 4.5 MW"),
    ], start=11):
        i21, v21, i01, ang = _oc_seqs("C", load)
        scens.append(FuseFailureScenario(
            id=idx, name=f"C{idx:02d}_phC_open",
            group="C_OPEN", open_phase="C", load_mw=load,
            expected_action="OPEN_CONDUCTOR",
            I2_I1_ratio=round(i21, 3), V2_V1_ratio=round(v21, 3),
            I0_I1_ratio=round(i01, 3), I2_angle_deg=ang,
            description=desc,
        ))

    # ── Group D: Healthy / ambiguous ─────────────────────────────────────────
    healthy_cases = [
        # (I21, V21, I01, ang, expected, desc)
        (0.02, 0.01, 0.01,  0.0, "HEALTHY", "Balanced load, no fault"),
        (0.04, 0.02, 0.02,  0.0, "HEALTHY", "Slight unbalance, healthy"),
        (0.10, 0.05, 0.03,  0.0, "HEALTHY", "IBR distortion, not open-cond"),
        (0.38, 0.20, 0.30, -30.0, "AMBIGUOUS", "Ambiguous — partial conductor contact"),
        (0.45, 0.35, 0.40,  90.0, "AMBIGUOUS", "Near-threshold, ambiguous"),
    ]
    for idx, (i21, v21, i01, ang, exp, desc) in enumerate(healthy_cases, start=16):
        scens.append(FuseFailureScenario(
            id=idx, name=f"D{idx:02d}_{exp.lower()}",
            group="HEALTHY", open_phase="NONE", load_mw=0.0,
            expected_action=exp,
            I2_I1_ratio=i21, V2_V1_ratio=v21,
            I0_I1_ratio=i01, I2_angle_deg=ang,
            description=desc,
        ))

    return scens


class FuseFailureScenarioLibrary:
    """Container for the 20 fuse-failure / open-conductor scenarios."""

    def __init__(self) -> None:
        self._scenarios = build_scenarios()

    def __len__(self) -> int:
        return len(self._scenarios)

    def __iter__(self):
        return iter(self._scenarios)

    def __getitem__(self, idx: int) -> FuseFailureScenario:
        return self._scenarios[idx]

    def get_by_group(self, group: str) -> List[FuseFailureScenario]:
        return [s for s in self._scenarios if s.group == group]

    def get_by_id(self, scenario_id: int) -> FuseFailureScenario:
        for s in self._scenarios:
            if s.id == scenario_id:
                return s
        raise KeyError(scenario_id)
