# =============================================================================
# sambp / digital_twin / coordination / adaptive_oc.py
#
# Adaptive overcurrent relay coordination during cold-load pickup — TR-85
#
# Problem
# -------
# Standard OC pickup = 1.25 × I_max_load.  During CLPU, I_load can reach
# (1 + K) × I_steady ≈ 4–6 × normal, causing nuisance trips before the
# actual fault current is seen.
#
# Strategy
# --------
# 1. On re-energisation, trigger CLPUEstimator with I_steady from pre-fault
#    metering.
# 2. At each relay update cycle, query the CLPU profile.
# 3. Temporarily raise OC pickup to profile.recommended_pickup_pu.
# 4. Auto-revert to nominal_pickup as soon as CLPUEstimator state → COMPLETE.
# 5. Hard time-out: if CLPU active for > max_clpu_duration_s, revert anyway
#    (safety net against stuck estimator).
#
# The adaptive OC also maintains a time-dial multiplier during CLPU:
#   TDM_clpu = TDM_nominal × (1 + 0.5 × excess_ratio)
# so that coordination with upstream relays is preserved (slower tripping
# for through-fault current during the CLPU window).
#
# Public API
# ----------
#   ctrl = AdaptiveOCController(nominal_pickup_pu, nominal_tdm, i_steady_pu)
#   ctrl.on_reclose(t)                  ← call at re-energisation
#   decision = ctrl.update(t, i_meas_pu) → OCDecision
#   ctrl.reset()
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from estimation.cold_load_estimator import CLPUEstimator, CLPUProfile


_MAX_CLPU_DURATION = 300.0   # hard time-out: 5 minutes [s]


# ---------------------------------------------------------------------------
# OCDecision
# ---------------------------------------------------------------------------

@dataclass
class OCDecision:
    """Adaptive OC relay decision at one update instant."""
    timestamp:       float
    i_measured_pu:   float
    pickup_pu:       float    # current active pickup threshold
    time_dial:       float    # current active time-dial multiplier
    clpu_active:     bool     # True if CLPU window is active
    clpu_multiplier: float    # I_clpu / I_steady (from estimator)
    operate:         bool     # True if relay should trip
    trip_time_s:     float    # estimated trip time (0 if not operating)
    state:           str      # "IDLE" | "CLPU_ACTIVE" | "NORMAL"
    reason:          str


# ---------------------------------------------------------------------------
# AdaptiveOCController
# ---------------------------------------------------------------------------

class AdaptiveOCController:
    """
    Adaptive OC pickup and time-dial controller for CLPU management.

    Parameters
    ----------
    nominal_pickup_pu : base OC pickup setting [pu]  (e.g. 1.25 × I_max_load)
    nominal_tdm       : base time-dial multiplier (IEC 60255 standard inverse)
    i_steady_pu       : steady-state load current before outage [pu]
    K                 : CLPU multiplier estimate (default 3.0)
    tau               : thermal time constant [s] (default 10.0)
    pickup_margin     : envelope margin for pickup (default 1.20)
    """

    def __init__(self,
                 nominal_pickup_pu: float,
                 nominal_tdm:       float,
                 i_steady_pu:       float,
                 K:   float = 3.0,
                 tau: float = 10.0,
                 pickup_margin: float = 1.20) -> None:
        self._nom_pickup = nominal_pickup_pu
        self._nom_tdm    = nominal_tdm
        self._estimator  = CLPUEstimator(i_steady_pu, K=K, tau=tau,
                                          pickup_margin=pickup_margin)
        self._t_reclose: Optional[float] = None

    # ------------------------------------------------------------------
    def on_reclose(self, t: float) -> None:
        """Notify the controller that the feeder has been re-energised at time t."""
        self._t_reclose = t
        self._estimator.trigger(t)

    # ------------------------------------------------------------------
    def update(self, t: float, i_measured_pu: float) -> OCDecision:
        """
        Compute adaptive OC decision at time t.

        Parameters
        ----------
        t             : current time [s]
        i_measured_pu : measured feeder current magnitude [pu]

        Returns
        -------
        OCDecision
        """
        profile = self._estimator.get_profile(t)

        # Hard time-out
        if (self._t_reclose is not None and
                (t - self._t_reclose) > _MAX_CLPU_DURATION):
            profile = CLPUProfile(
                timestamp=t, t_since_reclose=t - self._t_reclose,
                i_clpu_pu=self._estimator.i_steady_pu,
                i_steady_pu=self._estimator.i_steady_pu,
                multiplier=1.0, state="COMPLETE", active=False,
                recommended_pickup_pu=self._nom_pickup,
            )
            self._estimator.reset()
            self._t_reclose = None

        clpu_active = profile.active
        if clpu_active:
            pickup  = profile.recommended_pickup_pu
            excess  = max(0.0, profile.multiplier - 1.0)
            tdm     = self._nom_tdm * (1.0 + 0.5 * min(excess, self._estimator.K))
            state   = "CLPU_ACTIVE"
        else:
            pickup  = self._nom_pickup
            tdm     = self._nom_tdm
            state   = "NORMAL" if self._t_reclose is None else "NORMAL"

        # Standard inverse OC trip time (IEC 60255-151 standard inverse):
        #   t_trip = TDM × 0.14 / ((I/Ipickup)^0.02 – 1)
        operate   = False
        trip_time = 0.0
        if i_measured_pu >= pickup:
            m = i_measured_pu / pickup
            if m > 1.001:
                trip_time = tdm * 0.14 / (m ** 0.02 - 1.0)
                operate   = True
                reason = (f"OC trip: I={i_measured_pu:.3f} pu ≥ pickup={pickup:.3f} pu, "
                          f"t_trip={trip_time:.3f} s")
            else:
                reason = f"I={i_measured_pu:.3f} just at pickup, marginal"
        else:
            reason = f"I={i_measured_pu:.3f} pu < pickup={pickup:.3f} pu — no trip"
            if clpu_active:
                reason += f" (CLPU×{profile.multiplier:.2f})"

        return OCDecision(
            timestamp=t,
            i_measured_pu=round(i_measured_pu, 5),
            pickup_pu=round(pickup, 5),
            time_dial=round(tdm, 4),
            clpu_active=clpu_active,
            clpu_multiplier=round(profile.multiplier, 4),
            operate=operate,
            trip_time_s=round(trip_time, 4),
            state=state,
            reason=reason,
        )

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._estimator.reset()
        self._t_reclose = None
