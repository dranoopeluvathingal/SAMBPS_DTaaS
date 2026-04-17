# =============================================================================
# sambp / digital_twin / estimation / fault_evolution.py
#
# Evolving fault detector — TR-72 WP 72.1
#
# Applies CUSUM change-point detection on the time derivatives of EKF state
# estimates to detect in-flight fault type transitions.
#
# Detected transitions
# --------------------
#   SLG  → DLG    single-line-to-ground evolves to double-line-to-ground
#   SLG  → 3PH    single evolves to three-phase
#   DLG  → 3PH    double evolves to three-phase
#   any  → RST    fault restrike (cleared fault re-establishes)
#   any  → INT    intermittent fault (repeated open/close)
#
# Public API
# ----------
#   det = FaultEvolutionDetector()
#   evt = det.update(t, ekf_state)   → FaultEvolutionEvent | None
#   det.reset()
# =============================================================================

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FaultEvolutionEvent:
    """Emitted when a fault type transition is detected."""
    timestamp:   float   # seconds since epoch / simulation start
    from_type:   str     # e.g. "SLG", "DLG", "3PH", "NONE"
    to_type:     str     # e.g. "DLG", "3PH", "RST", "INT"
    confidence:  float   # [0, 1]


# ---------------------------------------------------------------------------
# CUSUM accumulator (scalar, one-sided)
# ---------------------------------------------------------------------------

class _CUSUMDetector:
    """
    One-sided CUSUM for detecting a positive mean shift in a scalar signal.

    Parameters
    ----------
    k       : slack (half the expected shift magnitude)
    h       : decision threshold (multiples of process std)
    """

    def __init__(self, k: float = 0.5, h: float = 4.0):
        self._k  = k
        self._h  = h
        self._s  = 0.0   # CUSUM statistic

    def update(self, x: float) -> bool:
        """Return True if change-point detected."""
        self._s = max(0.0, self._s + x - self._k)
        if self._s > self._h:
            self._s = 0.0   # reset after alarm
            return True
        return False

    def reset(self):
        self._s = 0.0


# ---------------------------------------------------------------------------
# Fault type classifier from EKF state
# ---------------------------------------------------------------------------

def _classify_fault(i_neg_norm: float, i_zero_norm: float,
                    k_drop: float) -> str:
    """
    Map normalised sequence component magnitudes to fault class.

    Parameters
    ----------
    i_neg_norm  : I_neg / I_pos  (negative-sequence ratio)
    i_zero_norm : proxy for zero-sequence  (alpha deviation from 0.5)
    k_drop      : fractional drop in k_ibr from pre-fault baseline
    """
    if k_drop < 0.05:
        return "NONE"
    # 3PH: very low negative sequence — tighter threshold avoids onset artifacts
    if i_neg_norm < 0.05 and i_zero_norm < 0.05:
        return "3PH"
    if i_neg_norm > 0.35:
        return "DLG" if i_zero_norm > 0.15 else "SLG"
    if i_neg_norm > 0.12:
        return "SLG"
    return "NONE"


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

_WINDOW   = 40    # samples for derivative rolling window (≈ 2 cycles @ 1 kHz)
_MIN_HOLD = 10    # minimum dwell before re-classification
_INT_GAP  = 8     # samples: max gap to call adjacent restrikes "intermittent"


class FaultEvolutionDetector:
    """
    CUSUM-based detector for in-flight fault type evolution.

    Tracks the rolling derivative of EKF state quantities and fires a
    FaultEvolutionEvent when a CUSUM alarm coincides with a change in the
    fault classifier output.

    Parameters
    ----------
    cusum_k   : CUSUM slack parameter (default 0.5)
    cusum_h   : CUSUM threshold (default 4.0)
    min_conf  : minimum confidence to emit an event (default 0.60)
    """

    def __init__(self,
                 cusum_k:  float = 0.50,
                 cusum_h:  float = 4.00,
                 min_conf: float = 0.60):
        self._cusum_k_ibr  = _CUSUMDetector(cusum_k, cusum_h)
        self._cusum_i_neg  = _CUSUMDetector(cusum_k, cusum_h)
        self._cusum_alpha  = _CUSUMDetector(cusum_k, cusum_h)

        self._min_conf  = min_conf
        self._window:    Deque[dict] = deque(maxlen=_WINDOW)
        self._cur_type:  str         = "NONE"
        self._hold:      int         = 0
        self._restrike_buf: Deque[float] = deque(maxlen=8)
        self._pre_fault_k: Optional[float] = None

    # ------------------------------------------------------------------
    def update(self, t: float, ekf_state: dict) -> Optional[FaultEvolutionEvent]:
        """
        Ingest one EKF state snapshot and return an event if a transition
        is detected, else None.

        Parameters
        ----------
        t         : current time [s]
        ekf_state : dict with keys k_ibr, z_line, alpha, f_gfm, residual
                    (output of EKFEstimator.update() or BESSEKFEstimator.update())
        """
        k    = float(ekf_state.get("k_ibr",   0.20))
        al   = float(ekf_state.get("alpha",    0.50))
        fg   = float(ekf_state.get("f_gfm",    0.50))
        resid = float(ekf_state.get("residual", 0.0))

        # ── Pre-fault baseline ────────────────────────────────────────
        if self._pre_fault_k is None:
            self._pre_fault_k = k

        # ── Derived features ──────────────────────────────────────────
        # negative-sequence proxy: alpha deviation from balanced (0.5)
        i_neg_norm  = abs(al - 0.50) * 2.0
        # zero-sequence proxy: residual elevated AND GFM contribution low
        i_zero_norm = resid if resid < 1.0 else 1.0
        k_drop      = max(0.0, (self._pre_fault_k - k) / max(self._pre_fault_k, 1e-6))

        self._window.append({
            "t": t, "k": k, "al": al, "fg": fg,
            "i_neg": i_neg_norm, "i_zero": i_zero_norm, "k_drop": k_drop,
        })

        # ── Need at least half a window to compute derivatives ────────
        if len(self._window) < _WINDOW // 2:
            return None

        # ── State derivatives (slope over trailing half-window) ───────
        half = _WINDOW // 4
        recent  = list(self._window)[-half:]
        older   = list(self._window)[-(2 * half):-half]
        if not older:
            return None

        dk  = self._mean(recent, "k")    - self._mean(older, "k")
        dal = self._mean(recent, "al")   - self._mean(older, "al")
        di  = self._mean(recent, "i_neg")- self._mean(older, "i_neg")

        # ── Feed CUSUM detectors ───────────────────────────────────────
        alarm_k   = self._cusum_k_ibr.update(abs(dk)   * 100)
        alarm_neg = self._cusum_i_neg.update(abs(di)   * 20)
        alarm_al  = self._cusum_alpha.update(abs(dal)  * 20)

        any_alarm = alarm_k or alarm_neg or alarm_al

        # ── Re-classify current fault state ──────────────────────────
        cur_i_neg = self._mean(list(self._window)[-half:], "i_neg")
        cur_i_z   = self._mean(list(self._window)[-half:], "i_zero")
        cur_kd    = self._mean(list(self._window)[-half:], "k_drop")
        new_type  = _classify_fault(cur_i_neg, cur_i_z, cur_kd)

        # ── Hold counter prevents chattering ─────────────────────────
        self._hold = max(0, self._hold - 1)

        event: Optional[FaultEvolutionEvent] = None

        # ── Restrike detection ────────────────────────────────────────
        # Record clearance on state transition (not requiring CUSUM alarm,
        # since _cur_type → NONE happens before alarm builds up).
        if self._cur_type != "NONE" and new_type == "NONE":
            self._restrike_buf.append(t)

        elif new_type != "NONE" and self._cur_type == "NONE" and self._restrike_buf:
            # Fault (re-)appearing after clear — restrike or intermittent.
            # No CUSUM gate here: the restrike_buf already records a previous
            # clearance, so the transition itself is sufficient evidence.
            if True:
                last_clear = self._restrike_buf[-1]
                gap_samples = (t - last_clear) * 1000  # assume 1 kHz
                if gap_samples <= _INT_GAP * 5:        # intermittent ≤ ~40 ms
                    conf = self._confidence(alarm_k, alarm_neg, alarm_al, resid, "INT")
                    if conf >= self._min_conf:
                        event = FaultEvolutionEvent(t, "NONE", "INT", conf)
                else:
                    conf = self._confidence(alarm_k, alarm_neg, alarm_al, resid, "RST")
                    if conf >= self._min_conf:
                        event = FaultEvolutionEvent(t, "NONE", "RST", conf)
            self._restrike_buf.clear()

        # ── Type-to-type transition ───────────────────────────────────
        elif (new_type != self._cur_type
              and new_type  != "NONE"
              and self._cur_type != "NONE"
              and any_alarm
              and self._hold == 0):
            conf = self._confidence(alarm_k, alarm_neg, alarm_al, resid, new_type)
            if conf >= self._min_conf:
                event = FaultEvolutionEvent(t, self._cur_type, new_type, conf)

        # ── Update state ──────────────────────────────────────────────
        if event is not None:
            self._hold = _MIN_HOLD

        if new_type != "NONE":
            self._cur_type = new_type
        elif self._cur_type != "NONE" and new_type == "NONE" and k_drop < 0.02:
            self._cur_type = "NONE"
            self._pre_fault_k = k   # refresh baseline after clearance

        return event

    # ------------------------------------------------------------------
    def reset(self):
        """Reset all state (call between fault scenarios)."""
        self._cusum_k_ibr.reset()
        self._cusum_i_neg.reset()
        self._cusum_alpha.reset()
        self._window.clear()
        self._restrike_buf.clear()
        self._cur_type    = "NONE"
        self._hold        = 0
        self._pre_fault_k = None

    # ------------------------------------------------------------------
    @property
    def current_fault_type(self) -> str:
        return self._cur_type

    # ------------------------------------------------------------------
    @staticmethod
    def _mean(records: list[dict], key: str) -> float:
        vals = [r[key] for r in records]
        return sum(vals) / len(vals) if vals else 0.0

    @staticmethod
    def _confidence(alarm_k: bool, alarm_neg: bool, alarm_al: bool,
                    resid: float, to_type: str) -> float:
        """
        Heuristic confidence score combining alarm count, residual, and
        transition plausibility.

        For RST/INT the transition evidence comes from the restrike_buf (a
        recorded clearance), not the CUSUM, so a higher base is appropriate.
        """
        n_alarms = sum([alarm_k, alarm_neg, alarm_al])
        if to_type in ("RST", "INT"):
            # Restrike evidence: restrike_buf provides the primary signal.
            base = 0.70 + 0.08 * n_alarms               # 0.70 – 0.94
        else:
            base = 0.50 + 0.15 * n_alarms               # 0.50 – 0.95
        # Residual penalty: high residual = uncertain measurement
        residual_factor = max(0.5, 1.0 - resid * 0.5)
        # Plausibility bonus for physically expected transitions
        plaus = {"DLG": 1.0, "3PH": 1.05, "RST": 0.95, "INT": 0.92}.get(to_type, 1.0)
        return min(1.0, base * residual_factor * plaus)
