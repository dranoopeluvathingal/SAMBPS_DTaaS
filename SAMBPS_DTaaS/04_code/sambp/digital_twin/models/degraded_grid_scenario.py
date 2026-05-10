# =============================================================================
# sambp / digital_twin / models / degraded_grid_scenario.py
#
# N-2 degraded-grid scenario library — TR-79 WP 79.2
#
# 20 scenarios across 4 groups:
#   Group A (1–5)  : N-0 normal operation
#   Group B (6–10) : N-1 single contingency
#   Group C (11–17): N-2 dual contingency (target for TR-79)
#   Group D (18–20): N-3+ severe degradation
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DegradedGridScenario:
    id:                int
    name:              str
    group:             str          # "N0_NORMAL" | "N1_SINGLE" | "N2_DUAL" | "N3_SEVERE"
    n_elements_lost:   int          # 0 / 1 / 2 / 3
    z_line_pu:         float        # EKF z_line for this scenario
    k_ibr:             float        # IBR penetration
    f_gfm:             float        # GFM fraction
    ibr_curtailed:     bool         # IBR output curtailed
    expected_level:    str          # "NORMAL" | "N-1" | "N-2" | "N-3"
    # Expected relay settings direction
    expect_reach_increase: bool     # True if reach_adj > reach_nom
    expect_pickup_decrease: bool    # True if pickup_adj < pickup_nom
    description:       str = ""


# ---------------------------------------------------------------------------
# Nominal parameters
# ---------------------------------------------------------------------------
_Z_NOM  = 0.050
_K_NOM  = 0.60
_F_NOM  = 0.50


def build_scenarios() -> List[DegradedGridScenario]:
    scens: List[DegradedGridScenario] = []

    # ── Group A: N-0 normal ──────────────────────────────────────────────────
    group_a = [
        (1, "A01_n0_normal",       0, 0.050, 0.60, 0.50, False, "NORMAL", False, False, "Nominal grid"),
        (2, "A02_n0_high_ibr",     0, 0.048, 0.80, 0.70, False, "NORMAL", False, False, "High IBR, still N-0"),
        (3, "A03_n0_low_ibr",      0, 0.052, 0.20, 0.10, False, "NORMAL", False, False, "SG-dominated, N-0"),
        (4, "A04_n0_gfm_heavy",    0, 0.050, 0.70, 0.90, False, "NORMAL", False, False, "GFM-dominant, N-0"),
        (5, "A05_n0_peak_load",    0, 0.051, 0.65, 0.55, False, "NORMAL", False, False, "Peak load, N-0"),
    ]
    for row in group_a:
        sid, name, n, z, k, f, curt, lvl, ri, pd, desc = row
        scens.append(DegradedGridScenario(
            id=sid, name=name, group="N0_NORMAL", n_elements_lost=n,
            z_line_pu=z, k_ibr=k, f_gfm=f, ibr_curtailed=curt,
            expected_level=lvl, expect_reach_increase=ri,
            expect_pickup_decrease=pd, description=desc,
        ))

    # ── Group B: N-1 single contingency ─────────────────────────────────────
    group_b = [
        (6,  "B06_n1_line_trip",   1, 0.068, 0.60, 0.50, False, "N-1", True,  True,  "One line tripped"),
        (7,  "B07_n1_xfmr_trip",   1, 0.072, 0.55, 0.45, False, "N-1", True,  True,  "One transformer out"),
        (8,  "B08_n1_ibr_trip",    1, 0.065, 0.40, 0.30, True,  "N-1", True,  True,  "IBR unit tripped"),
        (9,  "B09_n1_cable_fault",  1, 0.075, 0.58, 0.48, False, "N-1", True,  True,  "Cable fault, one feeder"),
        (10, "B10_n1_gfm_trip",    1, 0.070, 0.50, 0.20, True,  "N-1", True,  True,  "GFM unit trip, N-1"),
    ]
    for row in group_b:
        sid, name, n, z, k, f, curt, lvl, ri, pd, desc = row
        scens.append(DegradedGridScenario(
            id=sid, name=name, group="N1_SINGLE", n_elements_lost=n,
            z_line_pu=z, k_ibr=k, f_gfm=f, ibr_curtailed=curt,
            expected_level=lvl, expect_reach_increase=ri,
            expect_pickup_decrease=pd, description=desc,
        ))

    # ── Group C: N-2 dual contingency ───────────────────────────────────────
    group_c = [
        (11, "C11_n2_two_lines",   2, 0.092, 0.60, 0.50, False, "N-2", True,  True,  "Two lines tripped"),
        (12, "C12_n2_line_xfmr",  2, 0.095, 0.55, 0.45, False, "N-2", True,  True,  "Line + transformer N-2"),
        (13, "C13_n2_ibr_line",   2, 0.088, 0.35, 0.25, True,  "N-2", True,  True,  "IBR trip + line N-2"),
        (14, "C14_n2_gfm_sg",     2, 0.100, 0.50, 0.15, True,  "N-2", True,  True,  "GFM + SG unit N-2"),
        (15, "C15_n2_cable_ibr",  2, 0.090, 0.45, 0.40, True,  "N-2", True,  True,  "Cable fault + IBR N-2"),
        (16, "C16_n2_peak_stress",2, 0.105, 0.62, 0.52, False, "N-2", True,  True,  "Peak load N-2 stress"),
        (17, "C17_n2_low_scl",    2, 0.098, 0.30, 0.20, True,  "N-2", True,  True,  "Low short-circuit level N-2"),
    ]
    for row in group_c:
        sid, name, n, z, k, f, curt, lvl, ri, pd, desc = row
        scens.append(DegradedGridScenario(
            id=sid, name=name, group="N2_DUAL", n_elements_lost=n,
            z_line_pu=z, k_ibr=k, f_gfm=f, ibr_curtailed=curt,
            expected_level=lvl, expect_reach_increase=ri,
            expect_pickup_decrease=pd, description=desc,
        ))

    # ── Group D: N-3+ severe ─────────────────────────────────────────────────
    group_d = [
        (18, "D18_n3_severe",      3, 0.118, 0.25, 0.10, True,  "N-3", True,  True,  "Severe N-3 degradation"),
        (19, "D19_n3_blackout",    3, 0.130, 0.15, 0.05, True,  "N-3", True,  True,  "Near-blackout, minimal IBR"),
        (20, "D20_n3_island",      3, 0.125, 0.90, 0.80, True,  "N-3", True,  True,  "Islanded GFM network N-3"),
    ]
    for row in group_d:
        sid, name, n, z, k, f, curt, lvl, ri, pd, desc = row
        scens.append(DegradedGridScenario(
            id=sid, name=name, group="N3_SEVERE", n_elements_lost=n,
            z_line_pu=z, k_ibr=k, f_gfm=f, ibr_curtailed=curt,
            expected_level=lvl, expect_reach_increase=ri,
            expect_pickup_decrease=pd, description=desc,
        ))

    return scens


class DegradedGridScenarioLibrary:
    """Container for the 20 N-2 degraded-grid scenarios."""

    def __init__(self) -> None:
        self._scenarios = build_scenarios()

    def __len__(self) -> int:
        return len(self._scenarios)

    def __iter__(self):
        return iter(self._scenarios)

    def __getitem__(self, idx: int) -> DegradedGridScenario:
        return self._scenarios[idx]

    def get_by_group(self, group: str) -> List[DegradedGridScenario]:
        return [s for s in self._scenarios if s.group == group]

    def get_by_id(self, scenario_id: int) -> DegradedGridScenario:
        for s in self._scenarios:
            if s.id == scenario_id:
                return s
        raise KeyError(scenario_id)
