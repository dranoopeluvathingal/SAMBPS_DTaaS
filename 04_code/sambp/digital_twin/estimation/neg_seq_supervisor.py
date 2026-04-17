# =============================================================================
# sambp / digital_twin / estimation / neg_seq_supervisor.py
#
# Negative-sequence supervision — TR-73 WP 73.1
#
# Extracts symmetrical-component phasors via the Fortescue transform and
# implements negative-sequence current (I2) supervision logic that
# discriminates between:
#
#   a) IBR negative-sequence distortion (high I2/I1 ratio but NO fault)
#   b) Real asymmetric fault (SLG, DLG) — should trip
#
# When a high I2/I1 ratio is detected on an IBR-dominated bus the
# NegSeqSupervisor emits a NegSeqAlarm that blocks or allows the
# over-current (OC) element trip, preventing mal-operation.
#
# References
# ----------
#   TR-73 §2.1  — supervision algorithm and thresholds
#   IEEE C37.113-2015 §8.3 — negative-sequence relay applications
#
# Public API
# ----------
#   ext = SequenceExtractor(fs=1000, f0=50)
#   ext.push(v_abc, i_abc)
#   seqs = ext.extract()   → dict with V0/V1/V2/I0/I1/I2 and ratio fields
#
#   sup = NegSeqSupervisor(k_ibr_threshold=0.30)
#   alarm = sup.update(t, seqs, k_ibr)  → NegSeqAlarm | None
#   sup.reset()
# =============================================================================

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from estimation.phasor_dft import PhasorDFT


# ---------------------------------------------------------------------------
# NegSeqAlarm
# ---------------------------------------------------------------------------

@dataclass
class NegSeqAlarm:
    """
    Emitted whenever the supervisor makes a supervision decision.

    Fields
    ------
    timestamp      : time [s]
    I2_I1_ratio    : |I2| / |I1| at the decision instant
    V2_V1_ratio    : |V2| / |V1| at the decision instant
    action         : "BLOCK"  — suppress OC trip (IBR distortion)
                     "PERMIT" — allow OC trip (real fault confirmed)
                     "ALERT"  — high ratio but ambiguous; raise attention
    classification : "IBR_DISTORTION" | "REAL_FAULT" | "AMBIGUOUS"
    confidence     : float [0, 1]
    """
    timestamp:      float
    I2_I1_ratio:    float
    V2_V1_ratio:    float
    action:         str
    classification: str
    confidence:     float


# ---------------------------------------------------------------------------
# SequenceExtractor  (thin wrapper around PhasorDFT)
# ---------------------------------------------------------------------------

class SequenceExtractor:
    """
    Extracts positive-, negative-, and zero-sequence phasors from raw
    three-phase voltage and current samples using the Fortescue transform.

    Wraps PhasorDFT and adds convenience ratio fields.

    Parameters
    ----------
    fs : sample rate [Hz]  (default 1000)
    f0 : nominal frequency [Hz]  (default 50)
    """

    def __init__(self, fs: float = 1000.0, f0: float = 50.0):
        self._dft = PhasorDFT(fs=fs, f0=f0)

    # ------------------------------------------------------------------
    def push(self, v_abc, i_abc) -> None:
        """Push one sample (arrays of length 3)."""
        self._dft.push(v_abc, i_abc)

    # ------------------------------------------------------------------
    def extract(self) -> dict:
        """
        Return symmetrical component phasors and derived ratios.

        Keys (inherits all PhasorDFT keys plus extras)
        ------------------------------------------------
        V0, V1, V2         : complex voltage sequence phasors
        I0, I1, I2         : complex current sequence phasors
        I_pos_mag          : |I1|
        I_neg_mag          : |I2|
        I_zero_mag         : |I0|
        V_pos_mag          : |V1|
        V_neg_mag          : |V2|
        V_zero_mag         : |V0|
        I2_I1_ratio        : |I2| / max(|I1|, ε)
        V2_V1_ratio        : |V2| / max(|V1|, ε)
        I0_I1_ratio        : |I0| / max(|I1|, ε)
        ready              : bool — True when one full cycle accumulated
        """
        raw = self._dft.extract()
        i1 = abs(raw['I1'])
        i2 = abs(raw['I2'])
        i0 = abs(raw['I0'])
        v1 = abs(raw['V1'])
        v2 = abs(raw['V2'])
        v0 = abs(raw['V0'])
        eps = 1e-6
        return {
            **raw,
            'I_zero_mag':   i0,
            'V_neg_mag':    v2,
            'V_zero_mag':   v0,
            'I2_I1_ratio':  i2 / max(i1, eps),
            'V2_V1_ratio':  v2 / max(v1, eps),
            'I0_I1_ratio':  i0 / max(i1, eps),
            'ready':        self.ready,
        }

    # ------------------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self._dft.ready

    def reset(self) -> None:
        self._dft.reset()

    def __repr__(self) -> str:
        return f"SequenceExtractor(ready={self.ready})"


# ---------------------------------------------------------------------------
# Supervision thresholds (TR-73 §2.1)
# ---------------------------------------------------------------------------

# I2/I1 thresholds
_I21_ALERT_LO  = 0.05   # below this: balanced, no action needed
_I21_ALERT_HI  = 0.15   # above this: definitely asymmetric
_I21_FAULT_THR = 0.30   # above this: high probability of real fault

# V2/V1 thresholds — real faults depress V1 AND raise V2
_V21_IBR_MAX   = 0.08   # IBR distortion: V2/V1 stays low
_V21_FAULT_THR = 0.12   # real fault: V2/V1 typically > 0.10

# I2/I1 threshold above which IBR distortion is likely when k_ibr is high
_I21_IBR_DIST  = 0.10

# k_ibr threshold: IBR-dominated bus
_K_IBR_DOM     = 0.25

# Minimum samples in rolling window before issuing a BLOCK
_MIN_WINDOW    = 3

# Hysteresis: BLOCK stays active this many samples after ratio drops
_BLOCK_HOLD    = 5


class NegSeqSupervisor:
    """
    Negative-sequence supervision logic.

    Compares the I2/I1 and V2/V1 ratios against thresholds and the
    estimated k_ibr to decide whether a high I2 signal indicates:

      - IBR distortion  → emit BLOCK alarm (suppress OC element)
      - Real fault      → emit PERMIT alarm (allow OC element)
      - Ambiguous       → emit ALERT alarm (raise flag, do not trip)

    Parameters
    ----------
    k_ibr_threshold : float
        k_ibr above which the bus is considered IBR-dominated (default 0.30).
    min_confidence  : float
        Minimum confidence to emit any alarm (default 0.55).
    """

    def __init__(self,
                 k_ibr_threshold: float = 0.30,
                 min_confidence:  float = 0.55):
        self._k_thr  = k_ibr_threshold
        self._min_c  = min_confidence
        self._hold   = 0
        self._window: Deque[dict] = deque(maxlen=8)
        self._last_action: Optional[str] = None

    # ------------------------------------------------------------------
    def update(self,
               t: float,
               seqs: dict,
               k_ibr: float = 0.0) -> Optional[NegSeqAlarm]:
        """
        Process one set of sequence components and return a supervision alarm.

        Parameters
        ----------
        t      : current time [s]
        seqs   : output of SequenceExtractor.extract()
        k_ibr  : estimated IBR penetration on the bus (0..1)

        Returns
        -------
        NegSeqAlarm if a supervision decision is warranted, else None.
        """
        i21 = float(seqs.get('I2_I1_ratio', 0.0))
        v21 = float(seqs.get('V2_V1_ratio', 0.0))
        i01 = float(seqs.get('I0_I1_ratio', 0.0))

        self._window.append({'i21': i21, 'v21': v21, 'i01': i01})
        self._hold = max(0, self._hold - 1)

        if len(self._window) < _MIN_WINDOW:
            return None

        # Rolling mean to smooth noise
        w = list(self._window)
        i21_mean = sum(r['i21'] for r in w) / len(w)
        v21_mean = sum(r['v21'] for r in w) / len(w)
        i01_mean = sum(r['i01'] for r in w) / len(w)

        # ── Decision logic ────────────────────────────────────────────
        action, cls, conf = self._classify(i21_mean, v21_mean, i01_mean, k_ibr)

        if conf < self._min_c:
            return None

        # Hysteresis: if BLOCK is active, hold it for _BLOCK_HOLD samples
        if self._hold > 0 and action == "PERMIT":
            action = "BLOCK"
            cls    = "IBR_DISTORTION"
            conf   = max(self._min_c, conf * 0.85)

        if action == "BLOCK":
            self._hold = _BLOCK_HOLD

        self._last_action = action
        return NegSeqAlarm(
            timestamp=t,
            I2_I1_ratio=i21_mean,
            V2_V1_ratio=v21_mean,
            action=action,
            classification=cls,
            confidence=conf,
        )

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset state (call between fault scenarios)."""
        self._window.clear()
        self._hold = 0
        self._last_action = None

    @property
    def last_action(self) -> Optional[str]:
        return self._last_action

    # ------------------------------------------------------------------
    @staticmethod
    def _classify(i21: float, v21: float, i01: float,
                  k_ibr: float) -> tuple[str, str, float]:
        """
        Map sequence ratios and k_ibr to (action, classification, confidence).

        Decision table (TR-73 §2.1 Table 1)
        ------------------------------------
        High I2/I1 + low V2/V1 + high k_ibr  → BLOCK  (IBR distortion)
        High I2/I1 + high V2/V1               → PERMIT (real fault)
        High I2/I1 + moderate V2/V1           → ALERT  (ambiguous)
        Low  I2/I1                             → None   (balanced, no alarm)
        """
        ibr_dominated = k_ibr >= _K_IBR_DOM

        # ── Not alarming ─────────────────────────────────────────────
        if i21 < _I21_ALERT_LO:
            return "PERMIT", "REAL_FAULT", 0.40   # below threshold, conf < min

        # ── Clear real fault: high V2/V1 (voltage unbalance from fault) ─
        if i21 >= _I21_FAULT_THR and v21 >= _V21_FAULT_THR:
            conf = _conf_fault(i21, v21, i01)
            return "PERMIT", "REAL_FAULT", conf

        # ── Clear IBR distortion: high I2 but low V2 on IBR-dominated bus ─
        if (i21 >= _I21_IBR_DIST
                and v21 <= _V21_IBR_MAX
                and ibr_dominated):
            conf = _conf_ibr(i21, v21, k_ibr)
            return "BLOCK", "IBR_DISTORTION", conf

        # ── High I2/I1 but moderate V2/V1 and IBR-dominated bus ──────
        if (i21 >= _I21_ALERT_HI
                and ibr_dominated
                and v21 < _V21_FAULT_THR):
            conf = _conf_ibr(i21, v21, k_ibr) * 0.85  # less certain
            return "BLOCK", "IBR_DISTORTION", conf

        # ── High I2/I1, non-IBR bus or unclear V2 ────────────────────
        if i21 >= _I21_ALERT_HI:
            conf = min(0.75, 0.50 + 0.5 * (i21 - _I21_ALERT_HI) / _I21_ALERT_HI)
            return "ALERT", "AMBIGUOUS", conf

        # ── Low-moderate I2/I1: alert only ───────────────────────────
        conf = 0.45 + 0.15 * (i21 / _I21_ALERT_HI)
        return "ALERT", "AMBIGUOUS", conf


# ---------------------------------------------------------------------------
# Confidence helpers
# ---------------------------------------------------------------------------

def _conf_fault(i21: float, v21: float, i01: float) -> float:
    """Confidence that I2 elevation is due to a real asymmetric fault."""
    i21_score = min(1.0, (i21 - _I21_FAULT_THR) / 0.20 + 0.70)
    v21_score = min(1.0, (v21 - _V21_FAULT_THR) / 0.15 + 0.65)
    # Zero-sequence confirms SLG/DLG (ground fault)
    i01_score = min(1.0, 0.60 + 0.40 * (i01 / max(i21, 1e-6)))
    return min(1.0, (i21_score * 0.45 + v21_score * 0.35 + i01_score * 0.20))


def _conf_ibr(i21: float, v21: float, k_ibr: float) -> float:
    """Confidence that I2 elevation is IBR distortion, not a fault."""
    # High I2 with low V2 and high k_ibr is the signature of IBR distortion
    i21_score = min(1.0, 0.55 + (i21 - _I21_IBR_DIST) / 0.30)
    v21_score = min(1.0, 0.55 + (_V21_IBR_MAX - v21) / _V21_IBR_MAX)
    k_score   = min(1.0, 0.50 + (k_ibr - _K_IBR_DOM) / 0.50)
    return min(1.0, i21_score * 0.40 + v21_score * 0.35 + k_score * 0.25)
