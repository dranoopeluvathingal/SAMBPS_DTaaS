# =============================================================================
# sambp / digital_twin / estimation / ssci_detector.py
#
# Sub-Synchronous Control Interaction / Oscillation detector — TR-75 WP 75.1
#
# SSCI arises from resonant interaction between GFL converter current control
# loops (bandwidth ~10–100 Hz) and the LC resonant mode of series-compensated
# transmission lines.  The result is a growing oscillation in the
# sub-synchronous frequency range (5–45 Hz for 50 Hz systems).
#
# Detection algorithm
# -------------------
# 1. Maintain a rolling DFT buffer (one power-frequency cycle, N=fs/f0 pts).
# 2. At each sample, compute the DFT spectrum over the full buffer.
# 3. Extract the peak bin in the sub-synchronous band [f_lo, f_hi].
# 4. Track the peak magnitude over successive windows to estimate
#    the exponential growth rate λ: magnitude(t) ≈ A·exp(λ·t).
#    λ > 0 → growing (SSCI);  λ < 0 → decaying (safe).
# 5. Compute the sub-synchronous impedance indicator:
#    Z_ss(f) = |V_ss(f)| / max(|I_ss(f)|, ε)   at the peak SS frequency.
# 6. Emit SSCIAlarm when:
#    • |I_ss| > i_ss_threshold  AND
#    • λ > growth_threshold     (positive growth)
#    Alarm clears when |I_ss| < 0.5 × i_ss_threshold for clear_cycles.
#
# Sub-synchronous frequency band
# --------------------------------
# For a 50 Hz system the complement of line resonance f_r = f_0 – f_mech is:
#   f_mech (mechanical/electrical resonance) ∈ [5, 45] Hz
# For 60 Hz systems adjust f_hi = 55 Hz.
#
# Public API
# ----------
#   det = SSCIDetector(fs=1000, f0=50)
#   det.push(i_a, i_b, i_c, v_a, v_b, v_c)   ← per-sample call
#   alarm = det.check(t)                        → SSCIAlarm | None
#   det.reset()
# =============================================================================

from __future__ import annotations

import math
import cmath
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Sub-synchronous band limits (Hz, 50 Hz base)
# ---------------------------------------------------------------------------
_SS_F_LO    =  5.0
_SS_F_HI    = 45.0

# Alarm thresholds (calibrated on TR-75 study, 100 MVA base, 33 kV)
_I_SS_ALARM_THR  = 0.05   # [pu] — positive-sequence sub-synchronous current
_I_SS_CLEAR_THR  = 0.025  # [pu] — hysteresis clearance threshold
_GROWTH_ALARM    = 0.5    # [Np/s] — positive growth rate to alarm
_CLEAR_CYCLES    = 5      # number of cycles below clear threshold before clearing

# FFT window length: must be long enough for SS frequency resolution.
# With fs=1000 Hz and N_cycles=10, resolution = 1000/(10×20) = 5 Hz
# giving bins at 5, 10, 15, … 45 Hz — exactly the SS band.
# 5 cycles → buffer fills in 100 ms, resolution = fs/(5×N_cyc) = 10 Hz
# giving bins at 10, 20, 30, 40 Hz — sufficient for SS band 5-45 Hz.
_N_CYCLES = 5


# ---------------------------------------------------------------------------
# SSCIAlarm
# ---------------------------------------------------------------------------

@dataclass
class SSCIAlarm:
    """SSCI detection result for one check instant."""
    timestamp:       float   # [s]
    active:          bool    # True = SSCI detected
    f_peak_hz:       float   # dominant sub-synchronous frequency [Hz]
    I_ss_pu:         float   # sub-synchronous current magnitude [pu]
    V_ss_pu:         float   # sub-synchronous voltage magnitude [pu]
    Z_ss_pu:         float   # sub-synchronous impedance |V_ss/I_ss| [pu]
    growth_rate:     float   # estimated exponential growth rate [Np/s]
    risk_level:      str     # "NONE" | "WATCH" | "ALERT" | "TRIP"
    reason:          str


# ---------------------------------------------------------------------------
# SSCIDetector
# ---------------------------------------------------------------------------

class SSCIDetector:
    """
    FFT-based sub-synchronous control interaction detector.

    Parameters
    ----------
    fs              : sampling frequency [Hz]  (default 1000)
    f0              : power frequency [Hz]     (default 50)
    f_ss_lo         : lower edge of SS band [Hz]  (default 5)
    f_ss_hi         : upper edge of SS band [Hz]  (default 45)
    i_ss_threshold  : alarm current threshold [pu]  (default 0.05)
    growth_threshold: growth rate alarm threshold [Np/s]  (default 0.5)
    """

    def __init__(self,
                 fs: float = 1000.0,
                 f0: float = 50.0,
                 f_ss_lo: float = _SS_F_LO,
                 f_ss_hi: float = _SS_F_HI,
                 i_ss_threshold: float = _I_SS_ALARM_THR,
                 growth_threshold: float = _GROWTH_ALARM) -> None:
        self._fs    = fs
        self._f0    = f0
        self._f_lo  = f_ss_lo
        self._f_hi  = f_ss_hi
        self._i_thr = i_ss_threshold
        self._g_thr = growth_threshold

        self._N = int(round(fs / f0)) * _N_CYCLES   # multi-cycle DFT window
        # Three-phase current and voltage buffers
        self._i_buf: Deque[Tuple[float,float,float]] = deque(maxlen=self._N)
        self._v_buf: Deque[Tuple[float,float,float]] = deque(maxlen=self._N)

        # Peak magnitude history for growth rate estimation (last 10 windows)
        self._peak_i_hist: Deque[float] = deque(maxlen=10)
        self._peak_t_hist: Deque[float] = deque(maxlen=10)

        # Alarm state
        self._alarm_active  = False
        self._clear_counter = 0
        self._last_alarm: Optional[SSCIAlarm] = None

        # Frequency bins in SS band (computed once)
        self._freqs    = np.fft.rfftfreq(self._N, d=1.0/self._fs)
        ss_mask        = (self._freqs >= f_ss_lo) & (self._freqs <= f_ss_hi)
        self._ss_bins  = np.where(ss_mask)[0]

    # ------------------------------------------------------------------
    def push(self,
             i_a: float, i_b: float, i_c: float,
             v_a: float, v_b: float, v_c: float) -> None:
        """Append one sample (three-phase current and voltage) [pu]."""
        self._i_buf.append((i_a, i_b, i_c))
        self._v_buf.append((v_a, v_b, v_c))

    # ------------------------------------------------------------------
    def push_sequence(self,
                      i_pos: float, v_pos: float,
                      i_neg: float = 0.0, v_neg: float = 0.0) -> None:
        """
        Convenience push for sequence-component inputs.
        Synthesises balanced three-phase from positive sequence.
        """
        ang = 0.0   # reference angle for this sample (stationary approximation)
        ia = i_pos * math.cos(ang)
        ib = i_pos * math.cos(ang - 2*math.pi/3)
        ic = i_pos * math.cos(ang + 2*math.pi/3)
        va = v_pos * math.cos(ang)
        vb = v_pos * math.cos(ang - 2*math.pi/3)
        vc = v_pos * math.cos(ang + 2*math.pi/3)
        self.push(ia, ib, ic, va, vb, vc)

    # ------------------------------------------------------------------
    def check(self, t: float) -> SSCIAlarm:
        """
        Run detection on the current buffer contents.

        Parameters
        ----------
        t : current time [s]

        Returns
        -------
        SSCIAlarm (always returned; check .active for alarm state)
        """
        if len(self._i_buf) < self._N:
            return SSCIAlarm(
                timestamp=t, active=False, f_peak_hz=0.0,
                I_ss_pu=0.0, V_ss_pu=0.0, Z_ss_pu=0.0,
                growth_rate=0.0, risk_level="NONE",
                reason="Buffer not full",
            )

        i_arr = np.array(self._i_buf, dtype=float)  # (N, 3)
        v_arr = np.array(self._v_buf, dtype=float)

        # Positive-sequence extraction via Fortescue (on buffered waveform)
        i_pos_wave = self._pos_seq_wave(i_arr)
        v_pos_wave = self._pos_seq_wave(v_arr)

        # FFT of positive-sequence waveform
        I_fft = np.fft.rfft(i_pos_wave)
        V_fft = np.fft.rfft(v_pos_wave)

        # Sub-synchronous band magnitudes
        if len(self._ss_bins) == 0:
            i_ss_mag = 0.0
            v_ss_mag = 0.0
            f_peak   = 0.0
        else:
            I_ss_mags = np.abs(I_fft[self._ss_bins]) * 2.0 / self._N
            V_ss_mags = np.abs(V_fft[self._ss_bins]) * 2.0 / self._N
            peak_idx  = int(np.argmax(I_ss_mags))
            i_ss_mag  = float(I_ss_mags[peak_idx])
            v_ss_mag  = float(V_ss_mags[peak_idx])
            f_peak    = float(self._freqs[self._ss_bins[peak_idx]])

        z_ss = v_ss_mag / max(i_ss_mag, 1e-9)

        # Growth rate estimation
        self._peak_i_hist.append(i_ss_mag)
        self._peak_t_hist.append(t)
        growth_rate = self._estimate_growth_rate()

        # Alarm logic
        active, risk, reason = self._alarm_logic(i_ss_mag, growth_rate, f_peak)

        alarm = SSCIAlarm(
            timestamp=t,
            active=active,
            f_peak_hz=round(f_peak, 2),
            I_ss_pu=round(i_ss_mag, 6),
            V_ss_pu=round(v_ss_mag, 6),
            Z_ss_pu=round(z_ss, 4),
            growth_rate=round(growth_rate, 4),
            risk_level=risk,
            reason=reason,
        )
        self._last_alarm = alarm
        return alarm

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._i_buf.clear()
        self._v_buf.clear()
        self._peak_i_hist.clear()
        self._peak_t_hist.clear()
        self._alarm_active  = False
        self._clear_counter = 0
        self._last_alarm    = None

    @property
    def last_alarm(self) -> Optional[SSCIAlarm]:
        return self._last_alarm

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pos_seq_wave(abc: np.ndarray) -> np.ndarray:
        """
        Return the positive-sequence time-domain waveform from a (N,3) array.
        Uses simplified: i_pos ≈ (ia + a·ib + a²·ic) / 3
        where a = exp(j2π/3); we return the real part.
        """
        N = abc.shape[0]
        a  = cmath.exp(1j * 2 * math.pi / 3)
        a2 = a * a
        pos = (abc[:, 0] + a * abc[:, 1] + a2 * abc[:, 2]) / 3.0
        return pos.real

    def _estimate_growth_rate(self) -> float:
        """
        Estimate exponential growth rate λ from the peak magnitude history.
        Fits log(|I_ss(t)|) ≈ log(A) + λ·t by linear regression.
        Returns 0.0 if insufficient data.
        """
        if len(self._peak_i_hist) < 3:
            return 0.0
        mags = np.array(self._peak_i_hist, dtype=float)
        ts   = np.array(self._peak_t_hist, dtype=float)
        # Avoid log of zero
        valid = mags > 1e-9
        if np.sum(valid) < 3:
            return 0.0
        log_m = np.log(mags[valid])
        t_v   = ts[valid]
        # Linear regression: log_m = λ·t + b
        if np.ptp(t_v) < 1e-9:
            return 0.0
        lam = float(np.polyfit(t_v, log_m, 1)[0])
        return lam

    def _alarm_logic(self,
                     i_ss: float,
                     growth: float,
                     f_peak: float) -> Tuple[bool, str, str]:
        """Return (active, risk_level, reason)."""
        # Hysteresis clearance
        if self._alarm_active:
            if i_ss < _I_SS_CLEAR_THR:
                self._clear_counter += 1
                if self._clear_counter >= _CLEAR_CYCLES:
                    self._alarm_active  = False
                    self._clear_counter = 0
            else:
                self._clear_counter = 0

        # New alarm
        if not self._alarm_active:
            if i_ss >= self._i_thr and growth >= self._g_thr:
                self._alarm_active  = True
                self._clear_counter = 0

        # Risk classification
        if self._alarm_active:
            if i_ss >= 3 * self._i_thr or growth >= 5.0:
                risk   = "TRIP"
                reason = (f"SSCI TRIP: I_ss={i_ss:.4f}pu ≥3× thr, "
                          f"f_peak={f_peak:.1f}Hz, λ={growth:.2f}Np/s")
            elif i_ss >= 2 * self._i_thr or growth >= 2.0:
                risk   = "ALERT"
                reason = (f"SSCI ALERT: I_ss={i_ss:.4f}pu, "
                          f"f_peak={f_peak:.1f}Hz, λ={growth:.2f}Np/s")
            else:
                risk   = "WATCH"
                reason = (f"SSCI WATCH: I_ss={i_ss:.4f}pu, "
                          f"f_peak={f_peak:.1f}Hz, λ={growth:.2f}Np/s")
        else:
            if i_ss >= 0.5 * self._i_thr:
                risk   = "WATCH"
                reason = f"SS current I_ss={i_ss:.4f}pu below alarm threshold"
            else:
                risk   = "NONE"
                reason = "No sub-synchronous activity"

        return self._alarm_active, risk, reason
