# =============================================================================
# sambp / digital_twin / models / mc_scenario_generator.py
#
# Monte Carlo scenario generator for TR-86 — WP 86.2
#
# Uses Latin Hypercube Sampling (LHS) across 6 dimensions:
#   1. bus_idx          0..117
#   2. fault_type_idx   0..3  → ['3PH','SLG','DLG','LL']
#   3. log_R_f          LogNormal(mu=0.5, sigma=1.0), clipped [0, 20]
#   4. ibr_pen_idx      0..3  → [0.0, 0.30, 0.50, 1.00]
#   5. ibr_mode_idx     0..2  → ['gfl', 'gfm', 'mixed']
#   6. load_level       0.7..1.3 uniform
# =============================================================================

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# MC86Scenario
# ---------------------------------------------------------------------------

@dataclass
class MC86Scenario:
    """Single Monte Carlo scenario for the 118-bus study."""
    scenario_id:     int
    bus_idx:         int     # 0..117
    fault_type:      str     # '3PH','SLG','DLG','LL'
    R_f_ohm:         float   # fault resistance [Ω]
    ibr_penetration: float   # {0.0, 0.30, 0.50, 1.00}
    ibr_mode:        str     # 'gfl','gfm','mixed'
    load_level:      float   # 0.7..1.3


# ---------------------------------------------------------------------------
# MCScenarioGenerator
# ---------------------------------------------------------------------------

_FAULT_TYPES   = ['3PH', 'SLG', 'DLG', 'LL']
_IBR_PEN_VALS  = [0.0, 0.30, 0.50, 1.00]
_IBR_MODE_VALS = ['gfl', 'gfm', 'mixed']

_N_BUSES = 118


class MCScenarioGenerator:
    """
    Latin Hypercube Sampling generator for 118-bus Monte Carlo scenarios.

    Parameters
    ----------
    n_scenarios : int
        Number of scenarios to generate.
    seed : int
        Random seed for reproducibility (default 42).
    """

    def __init__(self, n_scenarios: int, seed: int = 42) -> None:
        self.n_scenarios = n_scenarios
        self.seed        = seed
        self._rng        = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    def generate(self) -> List[MC86Scenario]:
        """
        Generate n_scenarios using LHS over 6 dimensions.

        Returns
        -------
        List[MC86Scenario]
        """
        n = self.n_scenarios
        lhs = self._latin_hypercube(n, n_dims=6)

        scenarios: List[MC86Scenario] = []
        for i in range(n):
            row = lhs[i]

            # Dim 0 — bus_idx (0..117)
            bus_idx = int(row[0] * _N_BUSES) % _N_BUSES

            # Dim 1 — fault_type
            ft_idx     = int(row[1] * len(_FAULT_TYPES)) % len(_FAULT_TYPES)
            fault_type = _FAULT_TYPES[ft_idx]

            # Dim 2 — R_f_ohm from LogNormal(mu=0.5, sigma=1.0) in [0, 20]
            # Inverse CDF of log-normal via normal quantile
            mu_ln, sigma_ln = 0.5, 1.0
            # Map uniform [0,1] → normal quantile → log-normal
            u_rf  = float(np.clip(row[2], 0.001, 0.999))
            z_std = float(np.sqrt(2.0) * _erfinv(2.0 * u_rf - 1.0))
            R_f   = float(np.exp(mu_ln + sigma_ln * z_std))
            R_f   = float(np.clip(R_f, 0.0, 20.0))

            # Dim 3 — IBR penetration
            pen_idx         = int(row[3] * len(_IBR_PEN_VALS)) % len(_IBR_PEN_VALS)
            ibr_penetration = _IBR_PEN_VALS[pen_idx]

            # Dim 4 — IBR mode
            mode_idx = int(row[4] * len(_IBR_MODE_VALS)) % len(_IBR_MODE_VALS)
            ibr_mode = _IBR_MODE_VALS[mode_idx]

            # Dim 5 — load_level in [0.7, 1.3]
            load_level = 0.7 + row[5] * 0.6

            scenarios.append(MC86Scenario(
                scenario_id=i,
                bus_idx=bus_idx,
                fault_type=fault_type,
                R_f_ohm=round(R_f, 4),
                ibr_penetration=ibr_penetration,
                ibr_mode=ibr_mode,
                load_level=round(load_level, 4),
            ))

        return scenarios

    # ------------------------------------------------------------------
    def _latin_hypercube(self, n: int, n_dims: int) -> np.ndarray:
        """
        Generate an n × n_dims Latin Hypercube sample in [0, 1].
        Each dimension is divided into n equal intervals; one sample
        is drawn uniformly within each interval, then permuted.
        """
        rng = self._rng
        sample = np.zeros((n, n_dims))
        for d in range(n_dims):
            # Interval boundaries: [k/n, (k+1)/n] for k = 0..n-1
            perm      = rng.permutation(n)
            offsets   = rng.uniform(0.0, 1.0, size=n)
            sample[:, d] = (perm + offsets) / n
        return sample


# ---------------------------------------------------------------------------
# Numerical erfinv approximation (avoids scipy dependency)
# ---------------------------------------------------------------------------

def _erfinv(x: float) -> float:
    """Rational approximation of erfinv(x) for x in (-1, 1)."""
    # Winitzki (2008) approximation
    x = float(np.clip(x, -0.9999, 0.9999))
    a = 0.147
    ln1mx2 = np.log(1.0 - x * x)
    term   = (2.0 / (np.pi * a) + ln1mx2 / 2.0)
    result = np.sign(x) * np.sqrt(
        np.sqrt(term ** 2 - ln1mx2 / a) - term
    )
    return float(result)
