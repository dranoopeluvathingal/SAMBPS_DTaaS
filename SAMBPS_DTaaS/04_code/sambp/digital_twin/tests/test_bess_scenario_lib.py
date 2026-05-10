# =============================================================================
# tests/test_bess_scenario_lib.py
#
# Unit tests for models/bess_scenario_lib.py — TR-68 WP 68.2
#
# Tests
# -----
#   1. test_generate_200_scenarios    — library generates ≥ 200 scenarios
#   2. test_coverage_matrix           — all parameter axes represented
#   3. test_nn_lookup                 — nearest-neighbour returns correct result
#   4. test_scenario_to_dt_input      — to_dt_input() produces valid dict
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from models.bess_scenario_lib import (
    BESSScenarioLibrary,
    BESSScenario,
    _CHEMISTRIES,
    _OPERATING_MODES,
    _CONTROL_MODES,
    _FAULT_TYPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def lib() -> BESSScenarioLibrary:
    l = BESSScenarioLibrary(n_scenarios=240, seed=42)
    l.generate_all()
    return l


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerate200Scenarios:
    def test_count_at_least_200(self, lib):
        assert len(lib) >= 200

    def test_all_scenarios_are_bess_scenario(self, lib):
        for s in lib._scenarios:
            assert isinstance(s, BESSScenario)

    def test_scenario_ids_unique(self, lib):
        ids = [s.scenario_id for s in lib._scenarios]
        assert len(ids) == len(set(ids))

    def test_pre_fault_state_length(self, lib):
        for s in lib._scenarios:
            assert len(s.pre_fault_state) == 6

    def test_fault_current_non_negative(self, lib):
        for s in lib._scenarios:
            assert s.fault_current_pu >= 0.0
            assert s.fault_current_pu_50ms >= 0.0

    def test_outcomes_are_valid(self, lib):
        valid = {"Z1/87L", "87L", "EXTERNAL", "MISS"}
        for s in lib._scenarios:
            assert s.protection_outcome in valid

    def test_trip_time_positive(self, lib):
        for s in lib._scenarios:
            assert s.trip_time_ms > 0.0

    def test_soc_within_bounds(self, lib):
        for s in lib._scenarios:
            assert 0.0 < s.soc_level < 1.0

    def test_r_int_positive(self, lib):
        for s in lib._scenarios:
            assert s.r_int_pu > 0.0


class TestCoverageMatrix:
    def test_all_chemistries_present(self, lib):
        cov = lib.coverage_matrix()
        assert set(_CHEMISTRIES).issubset(cov["chemistry"])

    def test_all_operating_modes_present(self, lib):
        cov = lib.coverage_matrix()
        assert set(_OPERATING_MODES).issubset(cov["operating_mode"])

    def test_both_control_modes_present(self, lib):
        # li_ion / flow → GFL; na_ion → GFM
        cov = lib.coverage_matrix()
        assert "grid_following" in cov["control_mode"]
        assert "grid_forming"   in cov["control_mode"]

    def test_all_fault_types_present(self, lib):
        cov = lib.coverage_matrix()
        assert set(_FAULT_TYPES).issubset(cov["fault_type"])

    def test_multiple_fault_locations(self, lib):
        cov = lib.coverage_matrix()
        assert len(cov["fault_location"]) >= 3

    def test_multiple_ibr_penetrations(self, lib):
        cov = lib.coverage_matrix()
        assert len(cov["ibr_penetration"]) >= 2

    def test_multiple_scr_values(self, lib):
        cov = lib.coverage_matrix()
        assert len(cov["scr"]) >= 2

    def test_outcome_counts_keys(self, lib):
        counts = lib.outcome_counts()
        assert isinstance(counts, dict)
        # At least two distinct outcomes in a 240-scenario library
        assert len(counts) >= 2


class TestNNLookup:
    def test_exact_match_returns_same(self, lib):
        target = lib._scenarios[10]
        q = {
            "chemistry":       target.chemistry,
            "soc_level":       target.soc_level,
            "operating_mode":  target.operating_mode,
            "control_mode":    target.control_mode,
            "fault_type":      target.fault_type,
            "fault_location":  target.fault_location,
            "ibr_penetration": target.ibr_penetration,
            "scr":             target.scr,
        }
        result = lib.lookup_nearest(q)
        assert result.scenario_id == target.scenario_id

    def test_partial_query_returns_a_scenario(self, lib):
        result = lib.lookup_nearest({"chemistry": "li_ion", "fault_type": "3PH"})
        assert isinstance(result, BESSScenario)

    def test_chemistry_bias(self, lib):
        result = lib.lookup_nearest({"chemistry": "flow"})
        assert result.chemistry == "flow"

    def test_empty_query_returns_scenario(self, lib):
        result = lib.lookup_nearest({})
        assert isinstance(result, BESSScenario)

    def test_lookup_before_generate_raises(self):
        fresh_lib = BESSScenarioLibrary(n_scenarios=200, seed=1)
        with pytest.raises(RuntimeError, match="generate_all"):
            fresh_lib.lookup_nearest({"chemistry": "li_ion"})

    def test_lookup_time_reasonable(self, lib):
        import time
        q = {"chemistry": "na_ion", "soc_level": 0.5, "fault_location": 0.3}
        t0 = time.perf_counter()
        for _ in range(10):
            lib.lookup_nearest(q)
        elapsed_ms = (time.perf_counter() - t0) / 10 * 1000
        # Lookup over 240 scenarios should comfortably finish in < 5 ms
        assert elapsed_ms < 5.0, f"Lookup took {elapsed_ms:.2f} ms"


class TestScenarioToDTInput:
    def test_to_dt_input_keys(self, lib):
        s = lib._scenarios[0]
        d = s.to_dt_input()
        required = {
            "scenario_id", "chemistry", "soc", "operating_mode",
            "control_mode", "fault_type", "fault_location",
            "ibr_penetration", "scr", "pre_fault_state", "expected",
        }
        assert required.issubset(d.keys())

    def test_expected_keys(self, lib):
        d = lib._scenarios[5].to_dt_input()
        exp = d["expected"]
        assert "fault_current_pu"      in exp
        assert "fault_current_pu_50ms" in exp
        assert "protection_outcome"    in exp
        assert "trip_time_ms"          in exp

    def test_pre_fault_state_list_of_floats(self, lib):
        d = lib._scenarios[3].to_dt_input()
        state = d["pre_fault_state"]
        assert len(state) == 6
        assert all(isinstance(v, float) for v in state)

    def test_protection_outcome_in_expected(self, lib):
        valid = {"Z1/87L", "87L", "EXTERNAL", "MISS"}
        for s in lib._scenarios[:20]:
            d = s.to_dt_input()
            assert d["expected"]["protection_outcome"] in valid

    def test_dt_input_cached(self, lib):
        s = lib._scenarios[0]
        d1 = s.to_dt_input()
        d2 = s.to_dt_input()
        assert d1 is d2   # same dict object (cached)

    def test_scenario_id_matches(self, lib):
        for s in lib._scenarios[:10]:
            d = s.to_dt_input()
            assert d["scenario_id"] == s.scenario_id
