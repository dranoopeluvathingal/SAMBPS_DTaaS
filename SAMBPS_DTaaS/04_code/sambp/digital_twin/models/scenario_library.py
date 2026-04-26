# =============================================================================
# sambp / digital_twin / models / scenario_library.py
#
# Pre-computed fault scenario library for the SAMBP digital twin.
#
# The library is populated offline at DT initialisation.  During real-time
# operation the DT calls nearest() to retrieve the closest pre-computed
# outcome given the current estimated (k_ibr, alpha) state.
#
# Design (TR-43 §4):
#   • N = 1000 scenarios by default (memory: ~160 kB @ float64)
#   • Each scenario: (k_ibr, alpha, fault_type, r_arc, expected_outcome)
#   • Nearest-neighbour lookup uses weighted L1 distance on (k_ibr, alpha)
#   • Lookup must complete within 1 DT cycle (1 ms at 1 kHz)
#   • Lookup time measured at TR-43 Study D: ~0.16 ms on target hardware
#
# Protection outcome labels
# -------------------------
#   'Z1/87L'   — Zone 1 mho + line differential trip (fastest, ~20 ms)
#   '87L'      — Line differential only (k_ibr < Z1 reach)
#   'EXTERNAL' — Fault outside protected zone (alpha > 1.0)
#   'MISS'     — IBR contribution too small for detection (k_ibr < 0.06)
#
# Public API
# ----------
# lib = ScenarioLibrary(n_scenarios=1000, seed=42)
# lib.nearest(k_ibr, alpha)           → scenario dict
# lib.outcome_counts()                → Counter of expected_outcome
# lib.filter(outcome='Z1/87L')        → list of matching scenarios
# =============================================================================

import random
import math
from collections import Counter


# Protection thresholds (TR-35 / TR-43)
_I_MIN_87L = 0.06    # pu — 87L pickup threshold
_I_MIN_Z1  = 0.10    # pu — Zone 1 mho reach threshold
_X_R1      = 0.040   # pu — Z1 reactance reach
_R_REACH   = 0.030   # pu — Z1 resistance reach (load blinder)

_FAULT_TYPES = ['3PH', 'SLG', 'SLG', 'SLG', 'SLG', 'SLG',   # SLG 6× more likely
                'LL',  'LL',  'LLG']


def _relay_outcome(k, alpha, r_arc=0.0):
    """Deterministic protection outcome for a scenario (no noise)."""
    if alpha > 1.0:
        return 'EXTERNAL'
    x_m = alpha * 0.050          # reactance seen at relay
    r_m = (r_arc * (1.0 + 1.0 / k)) if k > 0.01 else 1e6
    in_z1 = (0.0 <= x_m <= _X_R1) and (r_m <= _R_REACH) and (k >= _I_MIN_Z1)
    if in_z1:
        return 'Z1/87L'
    if k >= _I_MIN_87L:
        return '87L'
    return 'MISS'


class ScenarioLibrary:
    """
    Pre-computed offline fault scenario library.

    Parameters
    ----------
    n_scenarios : int
        Number of scenarios to pre-compute.  Default 1000.
    seed : int
        RNG seed for reproducibility.
    k_range : tuple
        (min, max) for k_ibr sampling.  Default (0.04, 0.50).
    alpha_range : tuple
        (min, max) for fault location sampling.  Includes >1.0 for external.
        Default (0.00, 1.05).
    """

    def __init__(self, n_scenarios=1000, seed=42,
                 k_range=(0.04, 0.50), alpha_range=(0.00, 1.05)):
        self.n_scenarios  = n_scenarios
        self.seed         = seed
        self.k_range      = k_range
        self.alpha_range  = alpha_range
        self._scenarios   = []
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        rng = random.Random(self.seed)

        def _expo_cap(rng, lam, cap):
            v = -math.log(rng.random()) / lam
            return min(v, cap)

        for _ in range(self.n_scenarios):
            k     = rng.uniform(*self.k_range)
            alpha = rng.uniform(*self.alpha_range)
            ft    = rng.choice(_FAULT_TYPES)
            r_arc = _expo_cap(rng, 250, 0.025)   # exponential, mean=4 mΩ, cap 25 mΩ
            outcome = _relay_outcome(k, alpha, r_arc)
            self._scenarios.append({
                'k_ibr':            k,
                'alpha':            alpha,
                'fault_type':       ft,
                'r_arc':            r_arc,
                'expected_outcome': outcome,
            })

    # ------------------------------------------------------------------
    def nearest(self, k_ibr, alpha, k_weight=1.0, alpha_weight=0.5):
        """
        Find the nearest pre-computed scenario by weighted L1 distance.

        Parameters
        ----------
        k_ibr       : float — estimated IBR contribution ratio
        alpha       : float — estimated fault location
        k_weight    : float — weight on k_ibr distance (default 1.0)
        alpha_weight: float — weight on alpha distance (default 0.5,
                              because alpha estimation is noisier)

        Returns
        -------
        scenario : dict — nearest scenario (includes expected_outcome)
        """
        best_d = float('inf')
        best_s = self._scenarios[0]
        for s in self._scenarios:
            d = (k_weight    * abs(s['k_ibr'] - k_ibr) +
                 alpha_weight * abs(s['alpha'] - alpha))
            if d < best_d:
                best_d = d
                best_s = s
        return best_s

    # ------------------------------------------------------------------
    def outcome_counts(self):
        """Return Counter of expected_outcome across the library."""
        return Counter(s['expected_outcome'] for s in self._scenarios)

    # ------------------------------------------------------------------
    def filter(self, outcome=None, k_min=None, k_max=None):
        """
        Filter scenarios by outcome label and/or k_ibr range.

        Returns
        -------
        list of matching scenario dicts
        """
        result = self._scenarios
        if outcome is not None:
            result = [s for s in result if s['expected_outcome'] == outcome]
        if k_min is not None:
            result = [s for s in result if s['k_ibr'] >= k_min]
        if k_max is not None:
            result = [s for s in result if s['k_ibr'] <= k_max]
        return result

    # ------------------------------------------------------------------
    def __len__(self):
        return len(self._scenarios)

    def __repr__(self):
        counts = self.outcome_counts()
        return (f"ScenarioLibrary(n={self.n_scenarios}, "
                f"outcomes={dict(counts)})")
