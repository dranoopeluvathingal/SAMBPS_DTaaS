# =============================================================================
# sambp / digital_twin / models / dc_protection_mirror.py
#
# DC protection relay mirror — TR-80 WP 80.2
#
# DC microgrids require dedicated protection because:
#   • No zero-crossings → no natural current interruption
#   • Fault currents rise in <1 ms → must detect in <500 µs for fast CBs
#   • Capacitor discharge can pre-empt converter overcurrent
#   • Arc faults have intermittent, noisy current signatures
#
# Protection functions implemented
# ---------------------------------
# 76DC  — DC Overcurrent (instantaneous + time-delayed)
# 87DC  — DC Differential (for bus/zone protection)
# 81DC  — DC dI/dt rate-of-rise (catches fast capacitor discharge)
# 50ARC — Arc flash detection (combined I-spike + V-dip + noise)
# 27DC  — DC undervoltage (sustained low V → converter block / alarm)
#
# Each function emits a DCProtectionEvent when its operate condition is met.
#
# Public API
# ----------
#   mirror = DCProtectionMirror(settings)
#   events = mirror.evaluate(t_ms, I_A, V_A, dI_dt)   → List[DCProtectionEvent]
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# DCProtectionSettings
# ---------------------------------------------------------------------------

@dataclass
class DCProtectionSettings:
    """Threshold settings for all DC protection functions."""
    # 76DC — overcurrent
    oc_pickup_A:     float = 300.0    # instantaneous pickup [A]
    oc_delay_ms:     float = 2.0      # time-delay for inverse-time element [ms]
    oc_hi_pickup_A:  float = 1000.0   # high-set instantaneous (no delay) [A]

    # 87DC — differential
    diff_pickup_A:   float = 50.0     # differential current pickup [A]
    diff_slope_pct:  float = 20.0     # percentage bias slope [%]

    # 81DC — dI/dt rate-of-rise
    didt_pickup_A_ms: float = 200.0   # dI/dt pickup [A/ms]
    didt_delay_ms:    float = 0.1     # confirmation window [ms]

    # 50ARC — arc flash
    arc_I_mult:      float = 1.5      # arc pickup as multiple of OC pickup
    arc_V_dip_pu:    float = 0.30     # minimum V dip (fraction of nominal)
    arc_noise_pu:    float = 0.05     # noise-energy threshold [pu]

    # 27DC — undervoltage
    uv_pickup_pu:    float = 0.80     # undervoltage pickup [pu of Vnom]
    uv_delay_ms:     float = 100.0    # time-delay [ms]

    # System base
    V_nom_V:         float = 400.0    # nominal DC bus voltage [V]


# ---------------------------------------------------------------------------
# DCProtectionEvent
# ---------------------------------------------------------------------------

@dataclass
class DCProtectionEvent:
    """Operate event from one DC protection function."""
    t_ms:       float    # time of operation [ms]
    function:   str      # "76DC" | "87DC" | "81DC" | "50ARC" | "27DC"
    operate:    bool
    I_A:        float    # current at operate time [A]
    V_V:        float    # voltage at operate time [V]
    dI_dt:      float    # dI/dt [A/ms] at operate time
    reason:     str
    severity:   str      # "ALARM" | "TRIP"


# ---------------------------------------------------------------------------
# DCProtectionMirror
# ---------------------------------------------------------------------------

class DCProtectionMirror:
    """
    DC protection relay mirror — evaluates all functions at each time step.

    Parameters
    ----------
    settings : DCProtectionSettings
    """

    def __init__(self, settings: DCProtectionSettings) -> None:
        self._s = settings
        # Timer state for delayed elements
        self._oc_timer_start:  Optional[float] = None
        self._uv_timer_start:  Optional[float] = None
        self._didt_timer_start: Optional[float] = None
        # Differential: requires measured I_in and I_out separately (or I_diff directly)
        self._last_I_diff: float = 0.0
        # Arc noise energy accumulator (rolling 1-ms window)
        self._arc_noise_buf: List[float] = []

    # ------------------------------------------------------------------
    def evaluate(self,
                 t_ms:    float,
                 I_A:     float,
                 V_V:     float,
                 dI_dt:   float,
                 I_diff_A: float = 0.0,
                 I_avg_A:  float = 0.0) -> List[DCProtectionEvent]:
        """
        Evaluate all protection functions at time t_ms.

        Parameters
        ----------
        t_ms     : current time [ms]
        I_A      : measured DC current [A]
        V_V      : measured DC bus voltage [V]
        dI_dt    : rate of current rise [A/ms]
        I_diff_A : differential current (I_in − I_out) for 87DC [A]
        I_avg_A  : average (restraint) current (I_in + I_out)/2 for 87DC [A]
        """
        events = []
        s = self._s

        # ── 76DC: Overcurrent ──────────────────────────────────────────
        if I_A >= s.oc_hi_pickup_A:
            # High-set: operate instantly
            events.append(DCProtectionEvent(
                t_ms=t_ms, function="76DC", operate=True,
                I_A=I_A, V_V=V_V, dI_dt=dI_dt,
                reason=f"76DC HI: I={I_A:.1f}A ≥ {s.oc_hi_pickup_A:.0f}A",
                severity="TRIP",
            ))
            self._oc_timer_start = None
        elif I_A >= s.oc_pickup_A:
            if self._oc_timer_start is None:
                self._oc_timer_start = t_ms
            elif (t_ms - self._oc_timer_start) >= s.oc_delay_ms:
                events.append(DCProtectionEvent(
                    t_ms=t_ms, function="76DC", operate=True,
                    I_A=I_A, V_V=V_V, dI_dt=dI_dt,
                    reason=(f"76DC: I={I_A:.1f}A ≥ {s.oc_pickup_A:.0f}A "
                            f"for {t_ms - self._oc_timer_start:.2f} ms"),
                    severity="TRIP",
                ))
        else:
            self._oc_timer_start = None

        # ── 87DC: Differential ────────────────────────────────────────
        bias_thresh = s.diff_pickup_A + (s.diff_slope_pct / 100.0) * max(I_avg_A, 0.0)
        if abs(I_diff_A) >= bias_thresh:
            events.append(DCProtectionEvent(
                t_ms=t_ms, function="87DC", operate=True,
                I_A=I_A, V_V=V_V, dI_dt=dI_dt,
                reason=(f"87DC: |I_diff|={abs(I_diff_A):.1f}A ≥ "
                        f"bias_thresh={bias_thresh:.1f}A"),
                severity="TRIP",
            ))

        # ── 81DC: dI/dt rate-of-rise ──────────────────────────────────
        if dI_dt >= s.didt_pickup_A_ms:
            if self._didt_timer_start is None:
                self._didt_timer_start = t_ms
            elif (t_ms - self._didt_timer_start) >= s.didt_delay_ms:
                events.append(DCProtectionEvent(
                    t_ms=t_ms, function="81DC", operate=True,
                    I_A=I_A, V_V=V_V, dI_dt=dI_dt,
                    reason=f"81DC: dI/dt={dI_dt:.1f} A/ms ≥ {s.didt_pickup_A_ms:.0f} A/ms",
                    severity="TRIP",
                ))
        else:
            self._didt_timer_start = None

        # ── 50ARC: Arc flash ──────────────────────────────────────────
        v_dip = 1.0 - V_V / max(s.V_nom_V, 1.0)
        arc_I_trip = s.oc_pickup_A * s.arc_I_mult
        if (I_A >= arc_I_trip and
                v_dip >= s.arc_V_dip_pu):
            events.append(DCProtectionEvent(
                t_ms=t_ms, function="50ARC", operate=True,
                I_A=I_A, V_V=V_V, dI_dt=dI_dt,
                reason=(f"50ARC: I={I_A:.1f}A, V_dip={v_dip*100:.0f}% "
                        f"(≥{s.arc_V_dip_pu*100:.0f}%)"),
                severity="TRIP",
            ))

        # ── 27DC: Undervoltage ────────────────────────────────────────
        v_pu = V_V / max(s.V_nom_V, 1.0)
        if v_pu < s.uv_pickup_pu:
            if self._uv_timer_start is None:
                self._uv_timer_start = t_ms
            elif (t_ms - self._uv_timer_start) >= s.uv_delay_ms:
                events.append(DCProtectionEvent(
                    t_ms=t_ms, function="27DC", operate=True,
                    I_A=I_A, V_V=V_V, dI_dt=dI_dt,
                    reason=f"27DC: V={V_V:.1f}V ({v_pu:.2f}pu) < {s.uv_pickup_pu:.2f}pu",
                    severity="ALARM",
                ))
        else:
            self._uv_timer_start = None

        return events

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._oc_timer_start   = None
        self._uv_timer_start   = None
        self._didt_timer_start = None
        self._arc_noise_buf    = []
