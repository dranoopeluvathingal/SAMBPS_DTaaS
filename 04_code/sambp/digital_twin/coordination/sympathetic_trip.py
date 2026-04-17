# =============================================================================
# sambp / digital_twin / coordination / sympathetic_trip.py
#
# Sympathetic-tripping prevention — TR-78 WP 78.1
#
# "Sympathetic tripping" occurs when a fault on feeder-1 causes sufficient
# voltage depression at the bus to drive the OC relay on a healthy feeder-2
# into operation.  In IBR-dominated grids this is exacerbated because:
#
#   • GFM converters inject high fault current → larger V-dip at PCC
#   • GFL converters reduce injection → feeder voltage profile becomes
#     non-uniform across the bus, confusing conventional OC grading
#
# Prevention algorithm (TR-78)
# ----------------------------
#   1. SympatheticTripMonitor maintains a per-feeder state (HEALTHY/FAULT/BLOCKED)
#   2. On each DT cycle, it receives the current magnitude from every feeder
#   3. If feeder-i current exceeds fault_threshold AND feeder-j (j≠i) also
#      shows a rapid current rise:
#        a. Classify feeder-i as the faulted feeder (first to pick up, or
#           the one with highest delta-I)
#        b. Issue BLOCK to all OTHER feeders whose ΔI / I_pre < sympathetic_ratio
#   4. Block expires after block_timeout_s or when faulted feeder clears
#
# Public API
# ----------
#   mon = SympatheticTripMonitor(n_feeders=3)
#   results = mon.update(t, currents_pu, ekf_states)
#       → List[FeederDecision(feeder_id, action, blocked_by, confidence)]
#   mon.reset()
# =============================================================================

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------
_FAULT_THR_PU     = 1.20   # I > 1.20 pu → feeder in overcurrent
_SYMP_RATIO       = 0.30   # ΔI/I_pre < 0.30 → sympathetic (not fault-driven)
_BLOCK_TIMEOUT_S  = 0.200  # block lasts at most 200 ms
_DELTA_I_WINDOW   = 3      # samples used for delta-I calculation
_MIN_CONF         = 0.60   # minimum confidence to issue a BLOCK


# ---------------------------------------------------------------------------
# FeederDecision
# ---------------------------------------------------------------------------

@dataclass
class FeederDecision:
    feeder_id:  int     # 0-based feeder index
    action:     str     # "PERMIT" | "BLOCK" | "FAULT_FEEDER"
    blocked_by: str     # "" or "SYMPATHETIC_TRIP feeder-N"
    confidence: float
    I_pu:       float


# ---------------------------------------------------------------------------
# SympatheticTripMonitor
# ---------------------------------------------------------------------------

class SympatheticTripMonitor:
    """
    Multi-feeder DT coordination to prevent sympathetic OC tripping.

    Parameters
    ----------
    n_feeders          : number of feeders at the common bus
    fault_threshold_pu : overcurrent pickup threshold [pu]
    sympathetic_ratio  : ΔI/I_pre below which a feeder is considered sympathetic
    block_timeout_s    : maximum block duration [s]
    """

    def __init__(self,
                 n_feeders: int = 2,
                 fault_threshold_pu: float = _FAULT_THR_PU,
                 sympathetic_ratio: float = _SYMP_RATIO,
                 block_timeout_s: float = _BLOCK_TIMEOUT_S) -> None:
        self._n        = n_feeders
        self._i_thr    = fault_threshold_pu
        self._s_ratio  = sympathetic_ratio
        self._blk_t    = block_timeout_s

        # Per-feeder history window for delta-I
        self._i_hist: List[Deque[float]] = [
            deque(maxlen=_DELTA_I_WINDOW + 1) for _ in range(n_feeders)
        ]
        # Block state: feeder → time block issued (or None if not blocked)
        self._block_start: Dict[int, Optional[float]] = {i: None for i in range(n_feeders)}
        # Which feeder is the faulted feeder (None if no fault detected)
        self._fault_feeder: Optional[int] = None

    # ------------------------------------------------------------------
    def update(self,
               t: float,
               currents_pu: List[float],
               ekf_states: Optional[List[dict]] = None) -> List[FeederDecision]:
        """
        Process one DT cycle across all feeders.

        Parameters
        ----------
        t            : current time [s]
        currents_pu  : list of length n_feeders, positive-sequence I1 [pu]
        ekf_states   : optional per-feeder EKF state dicts (reserved for
                       k_ibr-weighted threshold adaptation)

        Returns
        -------
        List[FeederDecision], length == n_feeders
        """
        if len(currents_pu) != self._n:
            raise ValueError(f"Expected {self._n} currents, got {len(currents_pu)}")

        # Push to history
        for i, i_pu in enumerate(currents_pu):
            self._i_hist[i].append(i_pu)

        # Compute delta-I for each feeder
        delta_i = []
        i_pre   = []
        for i in range(self._n):
            hist = list(self._i_hist[i])
            if len(hist) >= 2:
                d_i = hist[-1] - hist[0]      # total rise over window
                pre = max(hist[0], 1e-6)
            else:
                d_i = 0.0
                pre = max(currents_pu[i], 1e-6)
            delta_i.append(d_i)
            i_pre.append(pre)

        # Identify feeders in overcurrent
        oc_feeders = [i for i, I in enumerate(currents_pu) if I > self._i_thr]

        # Identify faulted feeder: largest delta_I among overcurrent feeders
        if oc_feeders:
            self._fault_feeder = max(oc_feeders, key=lambda i: delta_i[i])
        elif self._fault_feeder is not None:
            # All overcurrent cleared — check if block timeout applies
            all_clear = all(currents_pu[i] <= self._i_thr for i in range(self._n))
            if all_clear:
                self._fault_feeder = None

        # Determine actions
        decisions = []
        for i in range(self._n):
            I_pu = currents_pu[i]

            # Expire old blocks
            if self._block_start[i] is not None:
                if t - self._block_start[i] > self._blk_t:
                    self._block_start[i] = None

            if i == self._fault_feeder:
                decisions.append(FeederDecision(
                    feeder_id=i, action="FAULT_FEEDER",
                    blocked_by="", confidence=0.90, I_pu=round(I_pu, 4),
                ))
                continue

            # Check if this feeder should be blocked
            if (self._fault_feeder is not None
                    and I_pu > self._i_thr
                    and self._block_start[i] is None):
                # Sympathetic if ΔI/I_pre is small relative to fault feeder's rise
                fault_di = delta_i[self._fault_feeder]
                own_di   = delta_i[i]
                own_pre  = i_pre[i]
                symp_flag = (own_di / own_pre) < self._s_ratio

                if symp_flag and fault_di > 0:
                    conf = min(0.95, 0.70 + 0.25 * (1.0 - own_di / max(fault_di, 1e-6)))
                    if conf >= _MIN_CONF:
                        self._block_start[i] = t
                        decisions.append(FeederDecision(
                            feeder_id=i, action="BLOCK",
                            blocked_by=f"SYMPATHETIC_TRIP feeder-{self._fault_feeder}",
                            confidence=round(conf, 4), I_pu=round(I_pu, 4),
                        ))
                        continue

            # Check if currently blocked
            if self._block_start[i] is not None:
                decisions.append(FeederDecision(
                    feeder_id=i, action="BLOCK",
                    blocked_by=f"SYMPATHETIC_TRIP feeder-{self._fault_feeder}",
                    confidence=0.80, I_pu=round(I_pu, 4),
                ))
                continue

            decisions.append(FeederDecision(
                feeder_id=i, action="PERMIT",
                blocked_by="", confidence=1.0, I_pu=round(I_pu, 4),
            ))

        return decisions

    # ------------------------------------------------------------------
    def reset(self) -> None:
        for h in self._i_hist:
            h.clear()
        for i in range(self._n):
            self._block_start[i] = None
        self._fault_feeder = None

    @property
    def fault_feeder(self) -> Optional[int]:
        return self._fault_feeder
