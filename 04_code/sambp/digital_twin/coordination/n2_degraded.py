# =============================================================================
# sambp / digital_twin / coordination / n2_degraded.py
#
# N-2 degraded-grid protection coordinator — TR-79 WP 79.1
#
# In an N-2 degraded grid (two transmission elements lost), the system
# topology changes materially:
#
#   • Line impedance seen by distance relays increases (longer path)
#   • Short-circuit level drops → OC pickup margins shrink
#   • IBR output may be curtailed (frequency nadir or reactive capability)
#   • Reach zones on distance relays may need to be extended
#
# This module provides:
#
#   TopologyDetector  — infers grid topology from EKF z_line + k_ibr trends
#   AdaptiveSettingCalculator — re-calculates relay settings for the new topology
#
# Public API
# ----------
#   td  = TopologyDetector()
#   asc = AdaptiveSettingCalculator()
#
#   topo = td.update(t, ekf_state)
#       → TopologyState(n_elements_lost, z_factor, degradation_level, reason)
#
#   settings = asc.calculate(topo, base_settings)
#       → AdjustedSettings(reach_pu, pickup_pu, time_dial, confidence, rationale)
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Degradation thresholds (calibrated on TR-79 study network)
# ---------------------------------------------------------------------------

# z_line increase factor thresholds → N-x state
_Z_FACTOR_N1 = 1.30   # 30% impedance increase → N-1
_Z_FACTOR_N2 = 1.70   # 70% increase → N-2
_Z_FACTOR_N3 = 2.20   # 120% increase → N-3 (severely degraded)

# k_ibr drop threshold indicating IBR curtailment (voltage/frequency event)
_K_IBR_DROP_THR = 0.20   # k_ibr drops by >0.20 pu → IBR curtailment suspected

# Reach extension limits (IEEE C37.113-2015 §11.4)
_REACH_EXTEND_MAX = 2.0   # maximum reach multiplier (2× nominal)
_PICKUP_REDUCE_MIN = 0.70  # minimum pickup (never below 70% of nominal)

# Confidence weights
_CONF_BASE = 0.85
_CONF_PENALTY_PER_LEVEL = 0.08


# ---------------------------------------------------------------------------
# TopologyState
# ---------------------------------------------------------------------------

@dataclass
class TopologyState:
    """Inferred grid topology from EKF measurements."""
    n_elements_lost: int    # 0 = N-0 (intact), 1 = N-1, 2 = N-2, 3+ = severe
    z_factor:        float  # current z_line / nominal z_line
    k_ibr_now:       float  # current IBR penetration fraction
    ibr_curtailed:   bool   # True if IBR output suspected curtailed
    degradation_level: str  # "NORMAL" | "N-1" | "N-2" | "N-3"
    confidence:      float
    reason:          str


# ---------------------------------------------------------------------------
# AdjustedSettings
# ---------------------------------------------------------------------------

@dataclass
class AdjustedSettings:
    """Relay settings adapted for degraded-grid topology."""
    reach_pu:     float   # distance relay zone-1 reach [pu of line impedance]
    pickup_pu:    float   # OC pickup current [pu]
    time_dial:    float   # time dial multiplier
    confidence:   float
    rationale:    str


# ---------------------------------------------------------------------------
# TopologyDetector
# ---------------------------------------------------------------------------

class TopologyDetector:
    """
    Infer N-x topology degradation from EKF state trends.

    Parameters
    ----------
    z_nominal : nominal positive-sequence line impedance [pu] used as reference
    k_ibr_nominal : expected IBR penetration at nominal grid state
    """

    def __init__(self,
                 z_nominal: float = 0.050,
                 k_ibr_nominal: float = 0.60) -> None:
        self._z_nom      = z_nominal
        self._k_ibr_nom  = k_ibr_nominal
        self._k_ibr_prev: Optional[float] = None

    # ------------------------------------------------------------------
    def update(self,
               t: float,
               ekf_state: dict) -> TopologyState:
        """
        Infer topology state from current EKF measurements.

        Parameters
        ----------
        t         : current time [s]
        ekf_state : dict with 'z_line' and 'k_ibr' from EKFEstimator
        """
        z_now   = float(ekf_state.get('z_line', self._z_nom))
        k_now   = float(ekf_state.get('k_ibr',  self._k_ibr_nom))
        f_gfm   = float(ekf_state.get('f_gfm',  0.50))

        z_factor = z_now / max(self._z_nom, 1e-9)

        # Detect IBR curtailment: significant drop in k_ibr
        ibr_curtailed = False
        if self._k_ibr_prev is not None:
            drop = self._k_ibr_prev - k_now
            ibr_curtailed = drop > _K_IBR_DROP_THR
        self._k_ibr_prev = k_now

        # Map z_factor to N-x level
        if z_factor < _Z_FACTOR_N1:
            level = "NORMAL"
            n_lost = 0
        elif z_factor < _Z_FACTOR_N2:
            level = "N-1"
            n_lost = 1
        elif z_factor < _Z_FACTOR_N3:
            level = "N-2"
            n_lost = 2
        else:
            level = "N-3"
            n_lost = 3

        conf = _CONF_BASE - n_lost * _CONF_PENALTY_PER_LEVEL
        conf = max(0.40, round(conf, 4))

        reason_parts = [f"z_factor={z_factor:.2f}→{level}"]
        if ibr_curtailed:
            reason_parts.append(f"IBR curtailed (k_ibr drop)")
        if f_gfm > 0.70:
            reason_parts.append(f"GFM-dominant (f_gfm={f_gfm:.2f})")

        return TopologyState(
            n_elements_lost=n_lost,
            z_factor=round(z_factor, 4),
            k_ibr_now=round(k_now, 4),
            ibr_curtailed=ibr_curtailed,
            degradation_level=level,
            confidence=conf,
            reason="; ".join(reason_parts),
        )


# ---------------------------------------------------------------------------
# AdaptiveSettingCalculator
# ---------------------------------------------------------------------------

class AdaptiveSettingCalculator:
    """
    Calculate adapted relay settings for an N-x degraded grid topology.

    Base settings are the nominal (N-0) values.  The calculator scales them
    according to the detected topology level.

    Parameters
    ----------
    reach_nom    : nominal zone-1 reach [pu]  (default 0.85)
    pickup_nom   : nominal OC pickup [pu]     (default 1.50)
    time_dial_nom: nominal time dial           (default 0.20)
    """

    def __init__(self,
                 reach_nom: float = 0.85,
                 pickup_nom: float = 1.50,
                 time_dial_nom: float = 0.20) -> None:
        self._reach_nom    = reach_nom
        self._pickup_nom   = pickup_nom
        self._td_nom       = time_dial_nom

    # ------------------------------------------------------------------
    def calculate(self,
                  topo: TopologyState,
                  base_settings: Optional[dict] = None) -> AdjustedSettings:
        """
        Compute adapted settings for the given topology state.

        Parameters
        ----------
        topo          : TopologyState from TopologyDetector.update()
        base_settings : optional override dict with keys 'reach_pu',
                        'pickup_pu', 'time_dial'

        Returns
        -------
        AdjustedSettings
        """
        reach_base  = float((base_settings or {}).get('reach_pu',  self._reach_nom))
        pickup_base = float((base_settings or {}).get('pickup_pu', self._pickup_nom))
        td_base     = float((base_settings or {}).get('time_dial', self._td_nom))

        n = topo.n_elements_lost
        zf = topo.z_factor

        # ── Reach extension: scale with z_factor ─────────────────────
        # Zone-1 reach must still cover 85% of the (now-longer) line path
        reach_adj = reach_base * zf
        reach_adj = min(reach_adj, _REACH_EXTEND_MAX * reach_base)

        # ── Pickup reduction: short-circuit level drops with z_factor ─
        # New pickup = nominal / zf  (Isc ∝ 1/Z)
        pickup_adj = pickup_base / max(zf, 1.0)
        pickup_adj = max(pickup_adj, _PICKUP_REDUCE_MIN * pickup_base)

        # ── Time dial increase: extra coordination margin in N-2 ──────
        if n == 0:
            td_adj = td_base
        elif n == 1:
            td_adj = td_base * 1.10
        elif n == 2:
            td_adj = td_base * 1.25
        else:
            td_adj = td_base * 1.50

        # If IBR is curtailed, further reduce pickup (less fault current)
        if topo.ibr_curtailed:
            pickup_adj *= 0.90

        conf = topo.confidence * 0.95  # slight reduction for settings step

        rationale = (
            f"topology={topo.degradation_level} z_factor={zf:.2f} "
            f"reach={reach_base:.2f}→{reach_adj:.2f} "
            f"pickup={pickup_base:.2f}→{pickup_adj:.2f} "
            f"td={td_base:.2f}→{td_adj:.2f}"
            + (" (IBR curtailed)" if topo.ibr_curtailed else "")
        )

        return AdjustedSettings(
            reach_pu=round(reach_adj,  4),
            pickup_pu=round(pickup_adj, 4),
            time_dial=round(td_adj,    4),
            confidence=round(conf,     4),
            rationale=rationale,
        )
