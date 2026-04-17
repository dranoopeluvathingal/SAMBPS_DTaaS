# =============================================================================
# sambp / digital_twin / models / cross_country_scenario.py
#
# Cross-country fault classifier — TR-72 WP 72.2
#
# Detects simultaneous faults on two different feeders (cross-country faults)
# by comparing EKF state streams from multiple measurement points.
# Provides a library of 30 evolving fault scenarios for validation.
#
# Public API
# ----------
#   clf = CrossCountryClassifier(n_feeders=2)
#   result = clf.update(t, feeder_states)   → CrossCountryResult | None
#   clf.reset()
#
#   lib = CrossCountryScenarioLibrary()
#   scenarios = lib.all()                   → list[CrossCountryScenario]
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CrossCountryResult:
    """Emitted when simultaneous faults on different feeders are detected."""
    timestamp:    float
    feeder_a:     int       # index of first faulted feeder
    feeder_b:     int       # index of second faulted feeder
    type_a:       str       # fault type on feeder A
    type_b:       str       # fault type on feeder B
    confidence:   float     # [0, 1]


@dataclass
class CrossCountryScenario:
    """Parameterised cross-country evolving fault scenario."""
    scenario_id:   int
    description:   str
    feeder_count:  int
    fault_a_type:  str       # initial fault type on feeder A
    fault_b_type:  str       # initial fault type on feeder B
    evolve_a_to:   Optional[str]   # None = no evolution
    evolve_b_to:   Optional[str]
    evolve_time_a: float     # seconds after fault onset
    evolve_time_b: float
    k_ibr_a:       float     # k_ibr on feeder A (0..1)
    k_ibr_b:       float
    z_line_a:      float
    z_line_b:      float
    expected_cc:   bool      # True if cross-country expected


# ---------------------------------------------------------------------------
# Feeder state fingerprint
# ---------------------------------------------------------------------------

def _fault_energy(state: dict) -> float:
    """Scalar fault energy proxy from EKF state."""
    k   = float(state.get("k_ibr",   0.20))
    al  = float(state.get("alpha",   0.50))
    res = float(state.get("residual", 0.0))
    i_neg = abs(al - 0.50) * 2.0
    return math.sqrt(k * k + i_neg * i_neg + res * res)


def _feeder_fault_type(state: dict, baseline_k: float) -> str:
    """Classify fault type from a single feeder's EKF state."""
    k    = float(state.get("k_ibr",   0.20))
    al   = float(state.get("alpha",   0.50))
    res  = float(state.get("residual", 0.0))
    kd   = max(0.0, (baseline_k - k) / max(baseline_k, 1e-6))
    i_neg = abs(al - 0.50) * 2.0
    i_z   = min(res, 1.0)
    if kd < 0.05:
        return "NONE"
    if i_neg < 0.10 and i_z < 0.10:
        return "3PH"
    if i_neg > 0.35:
        return "DLG" if i_z > 0.15 else "SLG"
    if i_neg > 0.12:
        return "SLG"
    return "NONE"


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

_MIN_FAULT_ENERGY = 0.08    # minimum energy to call a feeder faulted
_MIN_CONF         = 0.60


class CrossCountryClassifier:
    """
    Cross-country fault detector for multiple feeders.

    Compares simultaneous EKF state streams and fires CrossCountryResult
    when two (or more) feeders show fault signatures concurrently.

    Parameters
    ----------
    n_feeders   : number of feeders monitored
    min_conf    : minimum confidence to emit an event
    """

    def __init__(self, n_feeders: int = 2, min_conf: float = _MIN_CONF):
        self._n       = n_feeders
        self._min_c   = min_conf
        self._baselines: Dict[int, float] = {}   # feeder_idx → baseline k_ibr
        self._active:    Dict[int, str]   = {}   # feeder_idx → fault type
        self._n_updates  = 0

    # ------------------------------------------------------------------
    def update(self,
               t: float,
               feeder_states: Dict[int, dict]) -> Optional[CrossCountryResult]:
        """
        Ingest one EKF state snapshot per feeder.

        Parameters
        ----------
        t             : current time [s]
        feeder_states : {feeder_idx: ekf_state_dict}

        Returns
        -------
        CrossCountryResult if two simultaneously-faulted feeders detected, else None.
        """
        self._n_updates += 1

        # ── Update baselines (first 20 samples) ──────────────────────
        for idx, state in feeder_states.items():
            k = float(state.get("k_ibr", 0.20))
            if self._n_updates <= 20:
                self._baselines[idx] = k
            elif idx not in self._baselines:
                self._baselines[idx] = k

        # ── Classify each feeder ───────────────────────────────────────
        faulted: Dict[int, str] = {}
        for idx, state in feeder_states.items():
            baseline = self._baselines.get(idx, 0.20)
            ft = _feeder_fault_type(state, baseline)
            energy = _fault_energy(state)
            if ft != "NONE" and energy >= _MIN_FAULT_ENERGY:
                faulted[idx] = ft
            self._active[idx] = ft

        # ── Cross-country condition: ≥ 2 faulted feeders simultaneously ─
        if len(faulted) < 2:
            return None

        idxs = sorted(faulted.keys())
        a, b = idxs[0], idxs[1]

        # ── Confidence: based on energy disparity + fault type diversity ─
        e_a    = _fault_energy(feeder_states[a])
        e_b    = _fault_energy(feeder_states[b])
        energy_conf  = min(e_a, e_b) / max(max(e_a, e_b), 1e-6)
        type_diverse = 0.10 if faulted[a] == faulted[b] else 0.0   # penalty if same type
        conf = min(1.0, 0.60 + 0.30 * energy_conf - type_diverse)

        if conf < self._min_c:
            return None

        return CrossCountryResult(
            timestamp=t,
            feeder_a=a,
            feeder_b=b,
            type_a=faulted[a],
            type_b=faulted[b],
            confidence=conf,
        )

    # ------------------------------------------------------------------
    def reset(self):
        """Reset state (call between scenarios)."""
        self._baselines.clear()
        self._active.clear()
        self._n_updates = 0

    @property
    def active_fault_types(self) -> Dict[int, str]:
        return dict(self._active)


# ---------------------------------------------------------------------------
# Scenario library (30 evolving fault scenarios)
# ---------------------------------------------------------------------------

class CrossCountryScenarioLibrary:
    """
    Library of 30 cross-country / evolving fault scenarios for TR-72 validation.

    Covers:
      - SLG  → DLG evolution on one feeder while the other stays healthy
      - DLG  → 3PH escalation
      - Simultaneous SLG on both feeders (true cross-country)
      - Simultaneous but different types (SLG + DLG)
      - Evolving cross-country (one feeder escalates, one stays)
      - Restrike on one feeder + healthy on other
      - High / low IBR penetration variants
    """

    def all(self) -> List[CrossCountryScenario]:
        return self._build()

    def by_id(self, scenario_id: int) -> CrossCountryScenario:
        for s in self._build():
            if s.scenario_id == scenario_id:
                return s
        raise KeyError(scenario_id)

    # ------------------------------------------------------------------
    @staticmethod
    def _build() -> List[CrossCountryScenario]:
        rows: List[CrossCountryScenario] = []

        # ── Group 1: single-feeder evolving (not cross-country) ───────
        for i, (fa, fb, ea, eb) in enumerate([
            ("SLG",  "NONE", "DLG",  None),
            ("SLG",  "NONE", "3PH",  None),
            ("DLG",  "NONE", "3PH",  None),
            ("SLG",  "NONE", "DLG",  None),
            ("DLG",  "NONE", "3PH",  None),
        ], start=1):
            rows.append(CrossCountryScenario(
                scenario_id=i, description=f"single-feeder {fa}→{ea}",
                feeder_count=2,
                fault_a_type=fa, fault_b_type=fb,
                evolve_a_to=ea,  evolve_b_to=eb,
                evolve_time_a=0.060, evolve_time_b=0.0,
                k_ibr_a=0.40 + 0.05 * i, k_ibr_b=0.20,
                z_line_a=0.050, z_line_b=0.060,
                expected_cc=False,
            ))

        # ── Group 2: simultaneous same-type cross-country ─────────────
        for i, (ft, k_a, k_b) in enumerate([
            ("SLG", 0.30, 0.35),
            ("SLG", 0.45, 0.25),
            ("DLG", 0.50, 0.40),
            ("DLG", 0.20, 0.60),
            ("SLG", 0.55, 0.30),
        ], start=6):
            rows.append(CrossCountryScenario(
                scenario_id=i, description=f"cross-country {ft}+{ft}",
                feeder_count=2,
                fault_a_type=ft, fault_b_type=ft,
                evolve_a_to=None, evolve_b_to=None,
                evolve_time_a=0.0, evolve_time_b=0.0,
                k_ibr_a=k_a, k_ibr_b=k_b,
                z_line_a=0.050, z_line_b=0.055,
                expected_cc=True,
            ))

        # ── Group 3: simultaneous different-type cross-country ────────
        for i, (fa, fb, k_a, k_b) in enumerate([
            ("SLG", "DLG", 0.30, 0.45),
            ("SLG", "3PH", 0.35, 0.50),
            ("DLG", "3PH", 0.40, 0.55),
            ("SLG", "DLG", 0.50, 0.30),
            ("DLG", "SLG", 0.25, 0.45),
        ], start=11):
            rows.append(CrossCountryScenario(
                scenario_id=i, description=f"cross-country {fa}+{fb}",
                feeder_count=2,
                fault_a_type=fa, fault_b_type=fb,
                evolve_a_to=None, evolve_b_to=None,
                evolve_time_a=0.0, evolve_time_b=0.0,
                k_ibr_a=k_a, k_ibr_b=k_b,
                z_line_a=0.050, z_line_b=0.060,
                expected_cc=True,
            ))

        # ── Group 4: evolving cross-country (one feeder escalates) ────
        for i, (fa, fb, ea, k_a, k_b) in enumerate([
            ("SLG", "SLG", "DLG", 0.35, 0.30),
            ("SLG", "DLG", "3PH", 0.40, 0.45),
            ("DLG", "SLG", "3PH", 0.50, 0.25),
            ("SLG", "SLG", "3PH", 0.45, 0.40),
            ("DLG", "DLG", "3PH", 0.55, 0.50),
        ], start=16):
            rows.append(CrossCountryScenario(
                scenario_id=i, description=f"evolving CC {fa}→{ea} + static {fb}",
                feeder_count=2,
                fault_a_type=fa, fault_b_type=fb,
                evolve_a_to=ea, evolve_b_to=None,
                evolve_time_a=0.050, evolve_time_b=0.0,
                k_ibr_a=k_a, k_ibr_b=k_b,
                z_line_a=0.050, z_line_b=0.055,
                expected_cc=True,
            ))

        # ── Group 5: restrike / intermittent + cross-country ──────────
        for i, (fa, fb, k_a) in enumerate([
            ("SLG", "NONE",  0.40),
            ("SLG", "SLG",   0.35),
            ("DLG", "SLG",   0.50),
            ("SLG", "DLG",   0.45),
            ("3PH", "SLG",   0.55),
        ], start=21):
            rows.append(CrossCountryScenario(
                scenario_id=i, description=f"restrike {fa} + {fb}",
                feeder_count=2,
                fault_a_type=fa, fault_b_type=fb,
                evolve_a_to="RST", evolve_b_to=None,
                evolve_time_a=0.080, evolve_time_b=0.0,
                k_ibr_a=k_a, k_ibr_b=0.30,
                z_line_a=0.050, z_line_b=0.060,
                expected_cc=(fb != "NONE"),
            ))

        # ── Group 6: high IBR penetration ─────────────────────────────
        for i, (fa, fb) in enumerate([
            ("SLG", "SLG"),
            ("DLG", "SLG"),
            ("SLG", "3PH"),
            ("3PH", "3PH"),
            ("DLG", "DLG"),
        ], start=26):
            rows.append(CrossCountryScenario(
                scenario_id=i, description=f"high-IBR CC {fa}+{fb}",
                feeder_count=2,
                fault_a_type=fa, fault_b_type=fb,
                evolve_a_to=None, evolve_b_to=None,
                evolve_time_a=0.0, evolve_time_b=0.0,
                k_ibr_a=0.80, k_ibr_b=0.75,
                z_line_a=0.040, z_line_b=0.045,
                expected_cc=True,
            ))

        assert len(rows) == 30, f"Expected 30 scenarios, got {len(rows)}"
        return rows
