# =============================================================================
# sambp / digital_twin / estimation / open_conductor.py
#
# Open-conductor / fuse-failure detector — TR-77 WP 77.1
#
# An open phase (broken conductor or blown fuse) creates a distinctive
# sequence-component signature that differs from an asymmetric fault:
#
#   Open phase        : I2/I1 > 0.5  AND  V2/V1 < 0.40  (load-driven unbalance,
#                       voltage barely disturbed on LV side of open)
#   SLG fault         : I2/I1 > 0.3  AND  V2/V1 > 0.12  (voltage depression)
#   IBR distortion    : I2/I1 0.10–0.30  AND  V2/V1 < 0.08
#
# Algorithm
# ---------
#   1. Receive sequence ratios from SequenceExtractor output dict
#   2. Apply decision table per (I2/I1, V2/V1, I0/I1) region
#   3. Emit OpenConductorAlarm with classification and affected phase estimate
#
# Affected phase heuristic
# ------------------------
#   Uses I0/I1 ratio and angle of I2 phasor to identify the open phase (A/B/C).
#   A−open → I2 angle ≈ –30°;  B−open → I2 angle ≈ 90°;  C−open → I2 angle ≈ –150°
#   (approximate, 50 Hz, balanced pre-fault load)
#
# Public API
# ----------
#   det = OpenConductorDetector(i21_threshold=0.50)
#   alarm = det.update(t, seqs, ekf_state)  → OpenConductorAlarm | None
#   det.reset()
# =============================================================================

from __future__ import annotations

import math
import cmath
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Thresholds (calibrated on TR-77 synthetic study, N=500 open-phase events)
# ---------------------------------------------------------------------------
_I21_OPEN_THR   = 0.50   # I2/I1 ≥ this required for open-conductor decision
_V21_OPEN_MAX   = 0.40   # V2/V1 must be BELOW this (distinguishes open vs SLG)
_I01_OPEN_THR   = 0.40   # |I0/I1| ≥ this (open phase produces zero-sequence)
_I21_FAULT_THR  = 0.30   # below this, not an open-conductor
_CONF_HIGH      = 0.90
_CONF_MED       = 0.70

# Nominal I2 phasor angle per open phase (degrees, balanced load, 50 Hz)
_OPEN_PHASE_ANGLES = {
    "A": -30.0,
    "B":  90.0,
    "C": -150.0,
}
_PHASE_WINDOW_DEG = 40.0  # ±window for phase identification


# ---------------------------------------------------------------------------
# OpenConductorAlarm
# ---------------------------------------------------------------------------

@dataclass
class OpenConductorAlarm:
    """Result of one open-conductor detection update."""
    timestamp:      float   # [s]
    I2_I1_ratio:    float
    V2_V1_ratio:    float
    I0_I1_ratio:    float
    action:         str     # "OPEN_CONDUCTOR" | "HEALTHY" | "AMBIGUOUS"
    open_phase:     str     # "A" | "B" | "C" | "UNKNOWN"
    confidence:     float   # [0, 1]
    reason:         str


# ---------------------------------------------------------------------------
# OpenConductorDetector
# ---------------------------------------------------------------------------

class OpenConductorDetector:
    """
    Open-conductor / fuse-failure detector using symmetrical components.

    Parameters
    ----------
    i21_threshold : I2/I1 ratio threshold for open-conductor (default 0.50)
    v21_max       : V2/V1 ratio upper bound for open-conductor (default 0.40)
    """

    def __init__(self,
                 i21_threshold: float = _I21_OPEN_THR,
                 v21_max: float = _V21_OPEN_MAX) -> None:
        self._i21_thr = i21_threshold
        self._v21_max = v21_max
        self._last: Optional[OpenConductorAlarm] = None

    # ------------------------------------------------------------------
    def update(self,
               t: float,
               seqs: dict,
               ekf_state: Optional[dict] = None) -> Optional[OpenConductorAlarm]:
        """
        Process one set of sequence-component measurements.

        Parameters
        ----------
        t         : current time [s]
        seqs      : output dict from SequenceExtractor.extract():
                    keys I2_I1_ratio, V2_V1_ratio, I0_I1_ratio,
                    I2 (complex phasor)
        ekf_state : optional EKF state (unused currently, reserved for future
                    k_ibr-aware threshold scaling)

        Returns
        -------
        OpenConductorAlarm  (always — caller may filter on action)
        """
        i21 = float(seqs.get('I2_I1_ratio', 0.0))
        v21 = float(seqs.get('V2_V1_ratio', 0.0))
        i01 = float(seqs.get('I0_I1_ratio', 0.0))
        i2_phasor = seqs.get('I2', None)

        action = "HEALTHY"
        open_phase = "UNKNOWN"
        confidence = 1.0
        reason = ""

        if i21 >= self._i21_thr and v21 <= self._v21_max:
            # Primary open-conductor signature
            action = "OPEN_CONDUCTOR"
            confidence = _CONF_HIGH if i01 >= _I01_OPEN_THR else _CONF_MED
            reason = (f"I2/I1={i21:.3f}≥{self._i21_thr:.2f} "
                      f"V2/V1={v21:.3f}≤{self._v21_max:.2f}")
            open_phase = self._identify_phase(i2_phasor)

        elif i21 >= _I21_FAULT_THR and v21 > self._v21_max:
            # High I2 + significant V2 → SLG/DLG fault, not open conductor
            action = "HEALTHY"
            reason = f"V2/V1={v21:.3f} > {self._v21_max:.2f} → fault, not open-cond"
            confidence = 0.90

        elif i21 >= _I21_FAULT_THR and v21 <= self._v21_max:
            # I2/I1 between fault and open thresholds — ambiguous
            action = "AMBIGUOUS"
            confidence = 0.55
            reason = (f"I2/I1={i21:.3f} in ambiguous range "
                      f"[{_I21_FAULT_THR:.2f},{self._i21_thr:.2f})")
            open_phase = self._identify_phase(i2_phasor)

        alarm = OpenConductorAlarm(
            timestamp=t,
            I2_I1_ratio=round(i21, 4),
            V2_V1_ratio=round(v21, 4),
            I0_I1_ratio=round(i01, 4),
            action=action,
            open_phase=open_phase,
            confidence=round(confidence, 4),
            reason=reason,
        )
        self._last = alarm
        return alarm

    # ------------------------------------------------------------------
    def _identify_phase(self, i2_phasor) -> str:
        if i2_phasor is None:
            return "UNKNOWN"
        try:
            ang = math.degrees(cmath.phase(complex(i2_phasor)))
        except (TypeError, ValueError):
            return "UNKNOWN"
        best_phase = "UNKNOWN"
        best_dist = 9999.0
        for ph, ref_ang in _OPEN_PHASE_ANGLES.items():
            diff = abs(ang - ref_ang)
            if diff > 180.0:
                diff = 360.0 - diff
            if diff < best_dist:
                best_dist = diff
                best_phase = ph
        return best_phase if best_dist <= _PHASE_WINDOW_DEG else "UNKNOWN"

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._last = None

    @property
    def last_alarm(self) -> Optional[OpenConductorAlarm]:
        return self._last
