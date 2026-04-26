# =============================================================================
# sambp / digital_twin / estimation / cold_load_estimator.py
#
# Cold Load PickUp (CLPU) estimator — TR-85
#
# After an extended outage, thermostatically-controlled loads (HVAC, water
# heaters, refrigeration) simultaneously reconnect.  The inrush current
# envelope follows:
#
#   I_clpu(t) = I_steady × (1 + K × exp(–t / τ))
#
# where:
#   I_steady  = pre-fault steady-state load current [pu]
#   K         = cold-load pickup multiplier (typically 2.0–5.0)
#   τ         = thermal time constant (typically 5–30 s)
#   t         = time since reclosing (energisation) [s]
#
# State machine
# -------------
#   IDLE      → no cold-load event active
#   ACTIVE    → CLPU profile in progress (t < 5×τ)
#   DECAYING  → K×exp(–t/τ) < 0.10 × K; profile nearly complete
#   COMPLETE  → current has returned to I_steady ± 5%
#
# Public API
# ----------
#   est = CLPUEstimator(i_steady, K=3.0, tau=10.0)
#   est.trigger(t_reclose)         ← call at the moment of re-energisation
#   profile = est.get_profile(t)   → CLPUProfile (current estimate at time t)
#   est.reset()
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# CLPUProfile
# ---------------------------------------------------------------------------

@dataclass
class CLPUProfile:
    """Estimated CLPU state at a given instant."""
    timestamp:      float
    t_since_reclose: float   # elapsed since re-energisation [s]
    i_clpu_pu:      float   # estimated instantaneous load current [pu]
    i_steady_pu:    float   # steady-state load current [pu]
    multiplier:     float   # I_clpu / I_steady (≥1.0)
    state:          str     # "IDLE" | "ACTIVE" | "DECAYING" | "COMPLETE"
    active:         bool    # True if relay must use elevated pickup
    recommended_pickup_pu: float   # suggested OC pickup for this instant [pu]


# ---------------------------------------------------------------------------
# CLPUEstimator
# ---------------------------------------------------------------------------

class CLPUEstimator:
    """
    Estimate the cold-load pickup current envelope after re-energisation.

    Parameters
    ----------
    i_steady_pu : pre-fault steady-state load current [pu]
    K           : CLPU multiplier (default 3.0 — typical distribution feeder)
    tau         : thermal time constant [s] (default 10 s)
    pickup_margin : safety margin on top of envelope for OC setting (default 1.20)
    """

    def __init__(self,
                 i_steady_pu: float,
                 K:           float = 3.0,
                 tau:         float = 10.0,
                 pickup_margin: float = 1.20) -> None:
        self._i_ss   = i_steady_pu
        self._K      = K
        self._tau    = tau
        self._margin = pickup_margin

        self._t_reclose: Optional[float] = None
        self._active = False

    # ------------------------------------------------------------------
    def trigger(self, t_reclose: float) -> None:
        """Record re-energisation time and activate CLPU profile."""
        self._t_reclose = t_reclose
        self._active    = True

    # ------------------------------------------------------------------
    def get_profile(self, t: float) -> CLPUProfile:
        """
        Return CLPU state estimate at time t [s].

        If not triggered, returns IDLE profile at I_steady.
        """
        if not self._active or self._t_reclose is None:
            return CLPUProfile(
                timestamp=t, t_since_reclose=0.0,
                i_clpu_pu=self._i_ss, i_steady_pu=self._i_ss,
                multiplier=1.0, state="IDLE", active=False,
                recommended_pickup_pu=self._i_ss * self._margin,
            )

        dt = max(0.0, t - self._t_reclose)
        exp_term  = math.exp(-dt / max(self._tau, 1e-9))
        i_clpu    = self._i_ss * (1.0 + self._K * exp_term)
        multiplier = i_clpu / max(self._i_ss, 1e-9)
        excess_ratio = self._K * exp_term   # remaining fractional excess

        if excess_ratio > 0.10:
            if dt < 0.5 * self._tau:
                state = "ACTIVE"
            else:
                state = "DECAYING"
        else:
            state = "COMPLETE"
            self._active = False

        active_flag = state in ("ACTIVE", "DECAYING")
        # Recommended pickup: envelope + margin, never below steady-state × margin
        pickup = max(i_clpu * self._margin, self._i_ss * self._margin)

        return CLPUProfile(
            timestamp=t,
            t_since_reclose=round(dt, 4),
            i_clpu_pu=round(i_clpu, 5),
            i_steady_pu=self._i_ss,
            multiplier=round(multiplier, 4),
            state=state,
            active=active_flag,
            recommended_pickup_pu=round(pickup, 5),
        )

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._t_reclose = None
        self._active    = False

    @property
    def K(self) -> float:
        return self._K

    @property
    def tau(self) -> float:
        return self._tau

    @property
    def i_steady_pu(self) -> float:
        return self._i_ss
