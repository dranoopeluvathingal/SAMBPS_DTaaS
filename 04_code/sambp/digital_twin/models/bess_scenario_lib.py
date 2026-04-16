# =============================================================================
# sambp / digital_twin / models / bess_scenario_lib.py
#
# BESS fault scenario library — TR-68 WP 68.2
#
# Pre-generates 200+ BESS fault scenarios covering the full parameter space:
#   chemistry × soc_level × operating_mode × control_mode ×
#   fault_type × fault_location × ibr_penetration × scr
#
# Each scenario stores pre-computed expected outputs (protection outcome,
# fault current, relay response) suitable for DT digital-twin replay.
#
# Public API
# ----------
# lib = BESSScenarioLibrary()
# lib.generate_all()                    → list[BESSScenario]
# lib.lookup_nearest(query_params)      → BESSScenario
# lib.coverage_matrix()                 → dict — axis → set of values covered
# lib.filter(**kwargs)                  → list[BESSScenario]
# =============================================================================

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from models.bess_model import BESSConfig, BESSModel


# ---------------------------------------------------------------------------
# Parameter space
# ---------------------------------------------------------------------------

_CHEMISTRIES   = ["li_ion", "flow", "na_ion"]
_SOC_LEVELS    = [0.20, 0.50, 0.80]           # low / mid / high SoC
_OPERATING_MODES = ["charging", "idle", "discharging"]
_CONTROL_MODES = ["grid_following", "grid_forming"]
_FAULT_TYPES   = ["3PH", "SLG", "LL", "DLG"]
_FAULT_LOCS    = [0.1, 0.3, 0.5, 0.7, 0.9]   # alpha: distance along feeder
_IBR_PENS      = [0.20, 0.50, 0.80]           # IBR penetration (k_ibr proxy)
_SCRS          = [1.5, 3.0, 6.0]              # short-circuit ratio

# Pre-built BESS configs keyed by chemistry
_BESS_PRESETS: Dict[str, BESSConfig] = {
    "li_ion": BESSConfig.li_ion_1mwh(),
    "flow":   BESSConfig.flow_5mwh(),
    "na_ion": BESSConfig.na_ion_500kwh(),
}

# Protection thresholds (shared with ScenarioLibrary conventions)
_I_MIN_87L = 0.06   # pu — 87L pickup
_I_MIN_Z1  = 0.10   # pu — Zone 1 mho reach

# Dispatch setpoints by operating mode [P_pu, Q_pu]
_DISPATCH: Dict[str, Tuple[float, float]] = {
    "charging":    (-0.80, 0.0),
    "idle":        ( 0.00, 0.0),
    "discharging": ( 0.80, 0.0),
}


# ---------------------------------------------------------------------------
# BESSScenario dataclass
# ---------------------------------------------------------------------------

@dataclass
class BESSScenario:
    """Single pre-computed BESS fault scenario."""

    # --- Parameter axes ---
    scenario_id:    int
    chemistry:      str
    soc_level:      float
    operating_mode: str
    control_mode:   str
    fault_type:     str
    fault_location: float    # alpha ∈ [0, 1]
    ibr_penetration: float   # k_ibr proxy
    scr:            float    # short-circuit ratio

    # --- Pre-computed state ---
    pre_fault_state: List[float]   # x0 — 6-state vector

    # --- Pre-computed expected outputs ---
    fault_current_pu:   float      # I_ac magnitude at t=0 of fault
    fault_current_pu_50ms: float   # I_ac at t=50 ms (transient decay for GFM)
    r_int_pu:           float      # internal resistance at scenario SoC/T
    protection_outcome: str        # 'Z1/87L' | '87L' | 'EXTERNAL' | 'MISS'
    trip_time_ms:       float      # estimated relay trip time [ms]

    # --- DT input format ---
    dt_input: Dict[str, Any] = field(default_factory=dict)

    def to_dt_input(self) -> Dict[str, Any]:
        """Return dict suitable for DT replay engine / ComtradeParser feed."""
        if self.dt_input:
            return self.dt_input
        return {
            "scenario_id":      self.scenario_id,
            "chemistry":        self.chemistry,
            "soc":              self.soc_level,
            "operating_mode":   self.operating_mode,
            "control_mode":     self.control_mode,
            "fault_type":       self.fault_type,
            "fault_location":   self.fault_location,
            "ibr_penetration":  self.ibr_penetration,
            "scr":              self.scr,
            "pre_fault_state":  self.pre_fault_state,
            "expected": {
                "fault_current_pu":      self.fault_current_pu,
                "fault_current_pu_50ms": self.fault_current_pu_50ms,
                "protection_outcome":    self.protection_outcome,
                "trip_time_ms":          self.trip_time_ms,
            },
        }


# ---------------------------------------------------------------------------
# Protection outcome logic
# ---------------------------------------------------------------------------

def _protection_outcome(i_ac_pu: float, fault_location: float,
                        scr: float) -> str:
    """Deterministic protection outcome from fault scenario parameters."""
    # External fault: alpha > 1.0 (handled by caller normalisation; loc > 0.9
    # approximates a remote bus fault in this simplified model)
    if fault_location > 0.95:
        return "EXTERNAL"
    # Zone 1 mho: fault within first ~80% of line + adequate current
    k_eff = i_ac_pu * (scr / 3.0)   # effective contribution scaled by SCR
    in_z1 = (fault_location <= 0.80) and (k_eff >= _I_MIN_Z1)
    if in_z1:
        return "Z1/87L"
    if i_ac_pu >= _I_MIN_87L:
        return "87L"
    return "MISS"


def _trip_time_ms(outcome: str, fault_location: float) -> float:
    """Estimated trip time [ms] for a given outcome."""
    if outcome == "Z1/87L":
        return 20.0 + fault_location * 5.0    # ~20–25 ms
    if outcome == "87L":
        return 25.0 + fault_location * 15.0   # ~25–40 ms
    if outcome == "EXTERNAL":
        return 80.0                            # back-up time (DTL)
    return 500.0                               # MISS → coordinated DTL (slow)


# ---------------------------------------------------------------------------
# BESSScenarioLibrary
# ---------------------------------------------------------------------------

class BESSScenarioLibrary:
    """
    Pre-computed BESS fault scenario library (TR-68 WP 68.2).

    Extends the ScenarioLibrary pattern with BESS-specific parameter axes:
      chemistry × soc_level × operating_mode × control_mode ×
      fault_type × fault_location × ibr_penetration × scr

    The full grid yields 3×3×3×2×4×5×3×3 = 9720 combinations; by default
    the library draws a reproducible stratified sample of ``n_scenarios``
    (default 240 to ensure ≥200 after any deduplication).

    Parameters
    ----------
    n_scenarios : int
        Target scenario count.  ≥ 200 required.
    seed : int
        RNG seed for reproducibility.
    """

    def __init__(self, n_scenarios: int = 240, seed: int = 42) -> None:
        if n_scenarios < 200:
            raise ValueError("n_scenarios must be ≥ 200 (TR-68 requirement)")
        self.n_scenarios = n_scenarios
        self.seed        = seed
        self._scenarios: List[BESSScenario] = []

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate_all(self) -> List[BESSScenario]:
        """
        Pre-generate all BESS fault scenarios.

        Strategy: enumerate the full parameter grid, shuffle, then take
        ``n_scenarios`` entries so coverage is stratified.  If the grid
        is smaller than ``n_scenarios``, supplement with random samples.

        Returns
        -------
        scenarios : list[BESSScenario]
        """
        rng = random.Random(self.seed)

        # Build full combinatorial grid
        grid: List[Tuple] = []
        for chem in _CHEMISTRIES:
            for soc in _SOC_LEVELS:
                for op_mode in _OPERATING_MODES:
                    # control_mode comes from the preset config for this chemistry
                    cfg = _BESS_PRESETS[chem]
                    ctrl_mode = cfg.control_mode
                    for fault_type in _FAULT_TYPES:
                        for fault_loc in _FAULT_LOCS:
                            for ibr_pen in _IBR_PENS:
                                for scr in _SCRS:
                                    grid.append((chem, soc, op_mode, ctrl_mode,
                                                 fault_type, fault_loc, ibr_pen, scr))

        # Shuffle for stratified sampling
        rng.shuffle(grid)

        # Supplement if grid < n_scenarios
        while len(grid) < self.n_scenarios:
            chem      = rng.choice(_CHEMISTRIES)
            soc       = rng.uniform(0.10, 0.90)
            op_mode   = rng.choice(_OPERATING_MODES)
            ctrl_mode = _BESS_PRESETS[chem].control_mode
            fault_type = rng.choice(_FAULT_TYPES)
            fault_loc  = rng.uniform(0.05, 0.95)
            ibr_pen    = rng.uniform(0.10, 0.90)
            scr        = rng.uniform(1.0, 8.0)
            grid.append((chem, soc, op_mode, ctrl_mode,
                         fault_type, fault_loc, ibr_pen, scr))

        selected = grid[:self.n_scenarios]

        self._scenarios = []
        for idx, (chem, soc, op_mode, ctrl_mode,
                  fault_type, fault_loc, ibr_pen, scr) in enumerate(selected):
            scenario = self._compute_scenario(
                idx, chem, soc, op_mode, ctrl_mode,
                fault_type, fault_loc, ibr_pen, scr
            )
            self._scenarios.append(scenario)

        return self._scenarios

    def _compute_scenario(
        self,
        idx: int,
        chemistry: str,
        soc: float,
        operating_mode: str,
        control_mode: str,
        fault_type: str,
        fault_loc: float,
        ibr_pen: float,
        scr: float,
    ) -> BESSScenario:
        """Compute expected outputs for one scenario."""
        # Override control_mode on a copy of the preset config
        cfg = _BESS_PRESETS[chemistry]
        if cfg.control_mode != control_mode:
            cfg = BESSConfig(
                chemistry=cfg.chemistry,
                capacity_kwh=cfg.capacity_kwh,
                power_rating_kw=cfg.power_rating_kw,
                v_dc_nom=cfg.v_dc_nom,
                i_ac_max_pu=cfg.i_ac_max_pu,
                soc_min=cfg.soc_min,
                soc_max=cfg.soc_max,
                thermal_resistance=cfg.thermal_resistance,
                thermal_capacitance=cfg.thermal_capacitance,
                control_mode=control_mode,
                current_limit_pu=cfg.current_limit_pu,
            )

        model = BESSModel(cfg)

        # Clamp SoC to config limits
        soc_clamped = float(np.clip(soc, cfg.soc_min + 0.01, cfg.soc_max - 0.01))

        # Pre-fault dispatch
        p_sp, q_sp = _DISPATCH[operating_mode]
        x0 = model.x0(soc=soc_clamped, p_dispatch_pu=p_sp)
        # Warm up: run 5 steps at dispatch setpoint
        u = np.array([p_sp, q_sp])
        x = x0.copy()
        for _ in range(5):
            x = model.f(x, u, dt=0.02)

        # Fault state at t=0
        x_fault_0 = model.fault_state(x, fault_type=fault_type, t_elapsed=0.0)
        i_fault_0  = float(x_fault_0[4])   # I_ac_mag

        # Fault state at t=50 ms (GFM transient decay)
        x_fault_50 = model.fault_state(x, fault_type=fault_type, t_elapsed=0.05)
        i_fault_50  = float(x_fault_50[4])

        r_int = model.r_int(soc_clamped, float(x[5]))

        outcome   = _protection_outcome(i_fault_0, fault_loc, scr)
        trip_time = _trip_time_ms(outcome, fault_loc)

        scenario = BESSScenario(
            scenario_id      = idx,
            chemistry        = chemistry,
            soc_level        = soc_clamped,
            operating_mode   = operating_mode,
            control_mode     = control_mode,
            fault_type       = fault_type,
            fault_location   = fault_loc,
            ibr_penetration  = ibr_pen,
            scr              = scr,
            pre_fault_state  = x.tolist(),
            fault_current_pu = i_fault_0,
            fault_current_pu_50ms = i_fault_50,
            r_int_pu         = r_int,
            protection_outcome = outcome,
            trip_time_ms     = trip_time,
        )
        # Cache dt_input
        scenario.dt_input = scenario.to_dt_input()
        return scenario

    # ------------------------------------------------------------------
    # Nearest-neighbour lookup
    # ------------------------------------------------------------------

    def lookup_nearest(self, query_params: Dict[str, Any]) -> BESSScenario:
        """
        Find the nearest pre-computed scenario by weighted L1 distance.

        Continuous axes: soc_level, fault_location, ibr_penetration, scr
        Categorical axes: chemistry, operating_mode, control_mode, fault_type
          — penalty of 0.5 per axis mismatch

        Parameters
        ----------
        query_params : dict
            Keys: any subset of BESSScenario fields.

        Returns
        -------
        BESSScenario — nearest matching scenario.
        """
        if not self._scenarios:
            raise RuntimeError("Call generate_all() before lookup_nearest()")

        # Continuous query values (with sensible defaults)
        q_soc  = float(query_params.get("soc_level",      0.50))
        q_loc  = float(query_params.get("fault_location",  0.50))
        q_ibr  = float(query_params.get("ibr_penetration", 0.50))
        q_scr  = float(query_params.get("scr",             3.0))

        # Categorical
        q_chem = query_params.get("chemistry",      None)
        q_op   = query_params.get("operating_mode", None)
        q_ctrl = query_params.get("control_mode",   None)
        q_ft   = query_params.get("fault_type",     None)

        # Normalisation ranges
        soc_range = 0.80
        loc_range = 1.00
        ibr_range = 0.80
        scr_range = 6.50   # 1.5 → 8.0

        best_d  = float("inf")
        best_sc = self._scenarios[0]

        for sc in self._scenarios:
            d  = abs(sc.soc_level      - q_soc)  / soc_range
            d += abs(sc.fault_location - q_loc)  / loc_range
            d += abs(sc.ibr_penetration - q_ibr) / ibr_range
            d += abs(sc.scr            - q_scr)  / scr_range
            # Categorical penalties
            if q_chem and sc.chemistry      != q_chem: d += 0.5
            if q_op   and sc.operating_mode != q_op:   d += 0.5
            if q_ctrl and sc.control_mode   != q_ctrl: d += 0.5
            if q_ft   and sc.fault_type     != q_ft:   d += 0.5

            if d < best_d:
                best_d  = d
                best_sc = sc

        return best_sc

    # ------------------------------------------------------------------
    # Coverage and filtering
    # ------------------------------------------------------------------

    def coverage_matrix(self) -> Dict[str, set]:
        """Return the set of distinct values observed per axis."""
        if not self._scenarios:
            raise RuntimeError("Call generate_all() first")
        return {
            "chemistry":      {s.chemistry      for s in self._scenarios},
            "soc_level":      {round(s.soc_level, 4) for s in self._scenarios},
            "operating_mode": {s.operating_mode  for s in self._scenarios},
            "control_mode":   {s.control_mode    for s in self._scenarios},
            "fault_type":     {s.fault_type      for s in self._scenarios},
            "fault_location": {round(s.fault_location, 4) for s in self._scenarios},
            "ibr_penetration":{round(s.ibr_penetration, 4) for s in self._scenarios},
            "scr":            {round(s.scr, 4)   for s in self._scenarios},
        }

    def filter(self, **kwargs) -> List[BESSScenario]:
        """
        Filter scenarios by exact-match on any BESSScenario field.

        Example
        -------
        lib.filter(chemistry='li_ion', fault_type='3PH')
        """
        result = self._scenarios
        for key, val in kwargs.items():
            result = [s for s in result if getattr(s, key) == val]
        return result

    def outcome_counts(self) -> Dict[str, int]:
        """Count scenarios by protection_outcome."""
        counts: Dict[str, int] = {}
        for s in self._scenarios:
            counts[s.protection_outcome] = counts.get(s.protection_outcome, 0) + 1
        return counts

    def __len__(self) -> int:
        return len(self._scenarios)

    def __repr__(self) -> str:
        return (f"BESSScenarioLibrary(n={self.n_scenarios}, "
                f"generated={len(self._scenarios)}, "
                f"outcomes={self.outcome_counts()})")
