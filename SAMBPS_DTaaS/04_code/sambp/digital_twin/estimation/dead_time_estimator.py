# =============================================================================
# sambp / digital_twin / estimation / dead_time_estimator.py
#
# IBR-aware dead time estimator — TR-71 WP 71.1
#
# Conventional dead time (the window between CB opening and reclose) is set
# from a fixed table (e.g. 0.3 s, 1 s, 5 s for shots 1–3).  On IBR-dominated
# feeders the fixed table is unsafe:
#
#   • GFM inverters sustain voltage during the dead time → synchronism check
#     criterion must account for GFM-driven voltage recovery
#   • GFL inverters block on under-voltage → feeder voltage decays to zero
#     faster than on a synchronous machine network
#   • High k_ibr → shorter minimum dead time needed (voltage collapses fast)
#   • Low k_ibr (sync-machine dominated) → longer dead time (SG re-magnetises)
#
# Algorithm
# ---------
#   1. Receive EKF state (k_ibr, f_gfm) + fault type + feeder parameters
#   2. Estimate voltage-decay time constant τ_decay from k_ibr and f_gfm
#   3. Estimate feeder de-ionisation time from fault type and line impedance
#   4. Compute recommended dead time = max(τ_deion, τ_sync_recovery)
#   5. Apply shot-specific scaling (shot 2 ≥ 3× shot 1 per IEC 62271-100)
#
# Public API
# ----------
#   est = DeadTimeEstimator()
#   dt  = est.estimate(ekf_state, fault_type, shot_number, feeder_params)
#       → DeadTimeResult(t_dead_s, confidence, rationale)
#   est.reset()
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Constants (calibrated from TR-71 §2.1 study)
# ---------------------------------------------------------------------------

# Minimum dead time per IEC 62271-100 (mechanical CB de-ionisation) [s]
_T_DEION_MIN = 0.200     # 200 ms absolute floor

# Shot multipliers (IEC 62271-100 Table 1)
_SHOT_MULT = {1: 1.0, 2: 3.0, 3: 5.0}

# Decay time constant constants (fitted from IBR fault-recovery study)
_TAU_GFL_BASE = 0.050    # GFL: rapid voltage collapse after trip [s]
_TAU_GFM_BASE = 0.500    # GFM: sustains voltage longer [s]
_TAU_SG_BASE  = 1.500    # SG: de-magnetisation time constant [s]

# De-ionisation time per fault type [s]  (air-insulated overhead line)
_T_DEION_FAULT = {
    "SLG": 0.200,
    "LL":  0.250,
    "DLG": 0.280,
    "3PH": 0.350,
    "NONE": 0.200,
}

# Maximum safe dead time — beyond this synchronism is unlikely anyway [s]
_T_DEAD_MAX = 30.0

# GFM-sustain bonus: extra de-ionisation margin needed because GFM keeps V up
_GFM_MARGIN = 0.100  # 100 ms extra per unit f_gfm above 0.5


# ---------------------------------------------------------------------------
# DeadTimeResult
# ---------------------------------------------------------------------------

@dataclass
class DeadTimeResult:
    """Result of one dead-time estimation call."""
    t_dead_s:    float   # recommended dead time [s]
    confidence:  float   # estimation confidence [0, 1]
    rationale:   str     # human-readable explanation
    tau_decay:   float   # estimated voltage decay τ [s]
    t_deion:     float   # de-ionisation component [s]
    t_sync_rec:  float   # synchronism-recovery component [s]


# ---------------------------------------------------------------------------
# DeadTimeEstimator
# ---------------------------------------------------------------------------

class DeadTimeEstimator:
    """
    IBR-aware dead time estimator for auto-reclose sequencing.

    Parameters
    ----------
    safety_margin : float
        Multiplicative safety factor applied to the raw estimate (default 1.20).
    """

    def __init__(self, safety_margin: float = 1.20) -> None:
        self._margin = safety_margin
        self._history: list[DeadTimeResult] = []

    # ------------------------------------------------------------------
    def estimate(self,
                 ekf_state: dict,
                 fault_type: str = "SLG",
                 shot_number: int = 1,
                 feeder_params: Optional[dict] = None) -> DeadTimeResult:
        """
        Estimate recommended dead time for a reclose shot.

        Parameters
        ----------
        ekf_state     : dict with k_ibr, f_gfm, z_line (from EKFEstimator)
        fault_type    : 'SLG' | 'LL' | 'DLG' | '3PH'
        shot_number   : reclose shot index (1 = first, 2 = second, 3 = third)
        feeder_params : optional dict — {'length_km': float, 'voltage_kv': float}

        Returns
        -------
        DeadTimeResult
        """
        k_ibr = float(ekf_state.get('k_ibr',  0.20))
        f_gfm = float(ekf_state.get('f_gfm',  0.50))
        z_lin = float(ekf_state.get('z_line', 0.050))

        # ── 1. Voltage decay time constant ───────────────────────────
        # Weighted mix of GFL (rapid decay) and GFM (sustained), SG remainder
        f_sg  = max(0.0, 1.0 - k_ibr)          # synchronous machine fraction
        f_gfl = k_ibr * (1.0 - f_gfm)          # GFL fraction
        f_gfm_eff = k_ibr * f_gfm               # GFM fraction

        tau_decay = (f_sg   * _TAU_SG_BASE
                     + f_gfl * _TAU_GFL_BASE
                     + f_gfm_eff * _TAU_GFM_BASE)
        tau_decay = max(tau_decay, _TAU_GFL_BASE)

        # ── 2. De-ionisation time ─────────────────────────────────────
        t_deion = _T_DEION_FAULT.get(fault_type, _T_DEION_FAULT["SLG"])
        # GFM sustains arc voltage → extra de-ionisation margin
        t_deion += _GFM_MARGIN * max(0.0, f_gfm_eff - 0.50)
        t_deion = max(t_deion, _T_DEION_MIN)

        # ── 3. Synchronism recovery window ───────────────────────────
        # SG-heavy: need time for rotor to swing back into synchronism
        # IBR-heavy: no swing; sync check satisfied quickly by converter control
        if f_sg > 0.70:
            # SG-dominated: use 2× electrical time constant (rough SG rule)
            t_sync_rec = 2.0 * _TAU_SG_BASE * f_sg
        elif f_gfm_eff > 0.30:
            # GFM-dominated: GFM holds angle → need settling time only
            t_sync_rec = 0.3 + 0.5 * f_gfm_eff
        else:
            # GFL-dominated: voltage collapsed → wait for decay + restart
            t_sync_rec = tau_decay * 3.0

        # ── 4. Raw dead time ─────────────────────────────────────────
        t_raw = max(t_deion, t_sync_rec)

        # ── 5. Shot scaling ──────────────────────────────────────────
        shot_mult = _SHOT_MULT.get(shot_number, 5.0)
        t_dead = t_raw * shot_mult * self._margin
        t_dead = min(t_dead, _T_DEAD_MAX)

        # ── 6. Confidence ─────────────────────────────────────────────
        # Lower confidence when k_ibr is near 0.5 (mixed fleet — most uncertain)
        conf = 1.0 - 0.4 * math.exp(-8.0 * (k_ibr - 0.5) ** 2)

        rationale = (
            f"shot={shot_number} fault={fault_type} k_ibr={k_ibr:.2f} "
            f"f_gfm={f_gfm:.2f} → τ_decay={tau_decay:.3f}s "
            f"t_deion={t_deion:.3f}s t_sync={t_sync_rec:.3f}s "
            f"t_dead={t_dead:.3f}s (×{shot_mult}×{self._margin})"
        )
        result = DeadTimeResult(
            t_dead_s=round(t_dead, 4),
            confidence=round(conf, 4),
            rationale=rationale,
            tau_decay=round(tau_decay, 4),
            t_deion=round(t_deion, 4),
            t_sync_rec=round(t_sync_rec, 4),
        )
        self._history.append(result)
        return result

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._history.clear()

    @property
    def last_result(self) -> Optional[DeadTimeResult]:
        return self._history[-1] if self._history else None

    @property
    def history(self) -> list[DeadTimeResult]:
        return list(self._history)
