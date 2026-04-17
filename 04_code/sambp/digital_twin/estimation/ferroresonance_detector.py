# =============================================================================
# sambp / digital_twin / estimation / ferroresonance_detector.py
#
# Ferroresonance detector — TR-84
#
# Ferroresonance arises when a nonlinear transformer inductance interacts with
# a series or shunt capacitance (cable, CVT, grading cap).  Three regimes:
#
#   FUNDAMENTAL   — 50 Hz (or 60 Hz) periodic; modest harmonic content
#   SUBHARMONIC   — period-N: sub-50 Hz components (25 Hz, 16.7 Hz, etc.)
#   QUASI-PERIODIC — multiple incommensurate frequencies → broadband spectrum
#   CHAOTIC       — aperiodic, broadband, high THD, irregular zero-crossings
#
# Detection algorithm
# -------------------
# 1. Maintain a 10-cycle rolling buffer of the terminal voltage waveform.
# 2. Apply a 5-level Haar DWT decomposition to the buffer.
# 3. Compute feature vector:
#      f1 = energy ratio: detail levels D3–D5 / total  (sub-harmonic energy)
#      f2 = THD of voltage FFT (total harmonic distortion)
#      f3 = zero-crossing irregularity (std of ZC intervals / mean)
#      f4 = crest factor (peak / RMS)
#      f5 = sub-harmonic peak ratio (max SS-band magnitude / fundamental)
# 4. Rule-based classifier on (f1, f2, f3, f4, f5):
#      NORMAL        : f2 < 0.08 AND f1 < 0.10
#      FUNDAMENTAL   : f1 < 0.15 AND f2 < 0.25 AND f4 < 1.6×√2
#      SUBHARMONIC   : f5 > 0.15 AND f3 < 0.30
#      QUASI-PERIODIC: f1 > 0.20 AND f3 > 0.20 AND f2 > 0.25
#      CHAOTIC       : f2 > 0.40 OR f3 > 0.50
#
# Public API
# ----------
#   det = FerroresonanceDetector(fs=1000, f0=50)
#   det.push(va, vb, vc)          ← per-sample three-phase voltage [pu]
#   result = det.classify(t)      → FerroresonanceResult
#   det.reset()
# =============================================================================

from __future__ import annotations

import math
import numpy as np
from collections import deque
from dataclasses import dataclass
from typing import Deque, Tuple, Optional


_N_CYCLES    = 10       # buffer length in power-frequency cycles
_HAAR_LEVELS = 5        # DWT decomposition levels

# Sub-harmonic band: 5–45 Hz (same as SSCI band)
_SS_F_LO = 5.0
_SS_F_HI = 45.0


# ---------------------------------------------------------------------------
# FerroresonanceResult
# ---------------------------------------------------------------------------

@dataclass
class FerroresonanceResult:
    timestamp:   float
    mode:        str    # "NORMAL" | "FUNDAMENTAL" | "SUBHARMONIC" | "QUASI_PERIODIC" | "CHAOTIC"
    active:      bool   # True if any ferroresonance mode detected
    thd:         float  # total harmonic distortion [pu]
    crest_factor:float  # peak / RMS
    zc_irregularity: float  # zero-crossing interval std/mean
    ss_ratio:    float  # sub-harmonic peak / fundamental magnitude
    detail_energy_ratio: float  # DWT detail D3–D5 / total energy
    risk_level:  str    # "NONE" | "WATCH" | "ALERT" | "TRIP"
    reason:      str


# ---------------------------------------------------------------------------
# Haar DWT utilities (no scipy dependency)
# ---------------------------------------------------------------------------

def _haar_dwt(signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """One level of Haar DWT. Returns (approx, detail)."""
    N = len(signal) // 2
    approx = (signal[:2*N:2] + signal[1:2*N:2]) / math.sqrt(2)
    detail = (signal[:2*N:2] - signal[1:2*N:2]) / math.sqrt(2)
    return approx, detail


def _haar_energy_ratio(signal: np.ndarray, levels: int = 5) -> float:
    """
    Return energy ratio: sum of squares in detail levels 3–5 divided by
    total signal energy.  Captures sub-harmonic / low-frequency detail.
    """
    total_e = float(np.sum(signal ** 2)) + 1e-12
    detail_e = 0.0
    approx = signal.copy()
    for lv in range(1, levels + 1):
        if len(approx) < 2:
            break
        approx, detail = _haar_dwt(approx)
        if lv >= 3:
            detail_e += float(np.sum(detail ** 2))
    return detail_e / total_e


# ---------------------------------------------------------------------------
# FerroresonanceDetector
# ---------------------------------------------------------------------------

class FerroresonanceDetector:
    """
    Wavelet + spectral ferroresonance classifier.

    Parameters
    ----------
    fs   : sampling frequency [Hz]
    f0   : power frequency [Hz]
    """

    def __init__(self, fs: float = 1000.0, f0: float = 50.0) -> None:
        self._fs   = fs
        self._f0   = f0
        self._N    = int(round(fs / f0)) * _N_CYCLES
        # Store positive-sequence voltage envelope (one float per sample)
        self._v_buf: Deque[Tuple[float, float, float]] = deque(maxlen=self._N)
        self._last: Optional[FerroresonanceResult] = None

    # ------------------------------------------------------------------
    def push(self, va: float, vb: float, vc: float) -> None:
        self._v_buf.append((va, vb, vc))

    # ------------------------------------------------------------------
    def classify(self, t: float) -> FerroresonanceResult:
        if len(self._v_buf) < self._N:
            return FerroresonanceResult(
                timestamp=t, mode="NORMAL", active=False,
                thd=0.0, crest_factor=math.sqrt(2), zc_irregularity=0.0,
                ss_ratio=0.0, detail_energy_ratio=0.0,
                risk_level="NONE", reason="Buffer not full",
            )

        v_arr = np.array(self._v_buf, dtype=float)   # (N, 3)
        # Use positive-sequence voltage for analysis
        a  = np.exp(1j * 2 * math.pi / 3)
        v_pos = ((v_arr[:, 0] + a * v_arr[:, 1] + a**2 * v_arr[:, 2]) / 3.0).real

        f1 = _haar_energy_ratio(v_pos, _HAAR_LEVELS)
        f2 = self._thd(v_pos)
        f3 = self._zc_irregularity(v_pos)
        f4 = self._crest_factor(v_pos)
        f5 = self._ss_ratio(v_pos)

        mode, risk, reason = self._classify(f1, f2, f3, f4, f5)
        active = mode != "NORMAL"

        result = FerroresonanceResult(
            timestamp=t,
            mode=mode,
            active=active,
            thd=round(f2, 4),
            crest_factor=round(f4, 4),
            zc_irregularity=round(f3, 4),
            ss_ratio=round(f5, 4),
            detail_energy_ratio=round(f1, 4),
            risk_level=risk,
            reason=reason,
        )
        self._last = result
        return result

    def reset(self) -> None:
        self._v_buf.clear()
        self._last = None

    @property
    def last_result(self) -> Optional[FerroresonanceResult]:
        return self._last

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _thd(self, v: np.ndarray) -> float:
        """THD = sqrt(sum H2..H10 amplitudes²) / H1 amplitude."""
        V = np.fft.rfft(v)
        freqs = np.fft.rfftfreq(len(v), d=1.0 / self._fs)
        # fundamental bin
        f1_idx = int(round(self._f0 / (self._fs / len(v))))
        if f1_idx >= len(V) or abs(V[f1_idx]) < 1e-9:
            return 0.0
        v1 = abs(V[f1_idx])
        harmonic_pow = 0.0
        for h in range(2, 11):
            idx = int(round(h * self._f0 / (self._fs / len(v))))
            if idx < len(V):
                harmonic_pow += abs(V[idx]) ** 2
        return math.sqrt(harmonic_pow) / v1

    def _zc_irregularity(self, v: np.ndarray) -> float:
        """Std of zero-crossing intervals / mean interval."""
        zc = np.where(np.diff(np.sign(v)))[0]
        if len(zc) < 4:
            return 0.0
        intervals = np.diff(zc).astype(float)
        mean_i = float(np.mean(intervals))
        if mean_i < 1e-9:
            return 0.0
        return float(np.std(intervals) / mean_i)

    def _crest_factor(self, v: np.ndarray) -> float:
        rms = math.sqrt(float(np.mean(v ** 2))) + 1e-12
        return float(np.max(np.abs(v))) / rms

    def _ss_ratio(self, v: np.ndarray) -> float:
        """Peak sub-harmonic (5–45 Hz) magnitude / fundamental magnitude."""
        V = np.fft.rfft(v)
        freqs = np.fft.rfftfreq(len(v), d=1.0 / self._fs)
        f1_idx = int(round(self._f0 / (self._fs / len(v))))
        if f1_idx >= len(V):
            return 0.0
        v1 = abs(V[f1_idx]) + 1e-12
        ss_mask = (freqs >= _SS_F_LO) & (freqs <= _SS_F_HI)
        if not np.any(ss_mask):
            return 0.0
        return float(np.max(np.abs(V[ss_mask]))) / v1

    @staticmethod
    def _classify(f1: float, f2: float, f3: float, f4: float,
                  f5: float) -> Tuple[str, str, str]:
        """
        Rule-based classifier using FFT features (f1 is reported but not used —
        Haar DWT level 4 captures 31-63 Hz and confounds the 50 Hz fundamental).

        f2 = THD, f3 = ZC irregularity, f4 = crest factor, f5 = SS ratio.
        """
        if f2 > 0.40 or f3 > 0.50:
            return ("CHAOTIC", "TRIP",
                    f"Chaotic ferroresonance: THD={f2:.3f}, ZC_irr={f3:.3f}")
        if f5 > 0.10 and f2 > 0.25 and f3 > 0.15:
            return ("QUASI_PERIODIC", "ALERT",
                    f"Quasi-periodic: SS_ratio={f5:.3f}, ZC_irr={f3:.3f}, THD={f2:.3f}")
        if f5 > 0.15 and f3 < 0.30:
            return ("SUBHARMONIC", "ALERT",
                    f"Subharmonic ferroresonance: SS_ratio={f5:.3f}")
        if f2 >= 0.25 or f4 >= 1.6 * math.sqrt(2):
            return ("FUNDAMENTAL", "WATCH",
                    f"Fundamental-mode ferroresonance: THD={f2:.3f}, crest={f4:.3f}")
        return ("NORMAL", "NONE", "No ferroresonance detected")
