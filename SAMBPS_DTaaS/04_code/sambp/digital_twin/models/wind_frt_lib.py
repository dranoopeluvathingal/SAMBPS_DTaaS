# =============================================================================
# sambp / digital_twin / models / wind_frt_lib.py
#
# FRT (Fault Ride-Through) envelope library — TR-69 WP 69.2
#
# Implements three grid-code FRT profiles:
#   • IEC 61400-27-1 / IEC 61400-21-3  (European standard)
#   • AEMO National Electricity Rules S5.2.5.14  (Australian market)
#   • NERC PRC-024-2 + IEEE 1547-2018  (North American)
#
# Each standard defines:
#   1. Voltage–time FRT envelope (LVRT / HVRT thresholds)
#   2. Reactive current injection requirement during voltage dip
#   3. Active power recovery ramp after fault clearance
#
# Public API
# ----------
#   env   = get_frt_envelope("iec")    → FRTEnvelope
#   q_ref = frt_reactive_injection("iec", v_pu, p_gen_pu, i_max_pu)
#   ok    = in_frt_envelope("iec", v_pu, t_fault_s)
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------------------
# FRTEnvelope data class
# ---------------------------------------------------------------------------

@dataclass
class FRTPoint:
    """One (voltage, time) point on the FRT envelope boundary."""
    v_pu:     float   # terminal voltage [pu]
    t_s:      float   # maximum allowable duration at this voltage [s]


@dataclass
class FRTEnvelope:
    """
    Full FRT specification for one grid code.

    Attributes
    ----------
    standard      : 'iec' | 'aemo' | 'nerc'
    lvrt_curve    : list of (V, t) points for LVRT lower boundary
                    (sorted ascending by t: deeper dip, shorter allowed time)
    hvrt_curve    : list of (V, t) points for HVRT upper boundary
    k_q_iu        : reactive current slope during under-voltage
                    dI_q/d(ΔV) [pu/pu]  (positive = capacitive injection)
    k_q_io        : reactive current slope during over-voltage
                    dI_q/d(ΔV) [pu/pu]  (positive = inductive absorption)
    delta_v_dead  : voltage dead-band [pu] (no reactive injection inside)
    i_q_max_pu    : maximum reactive current injection [pu]
    p_ramp_mw_s   : active power recovery ramp rate [MW/s per MW rated]
                    (expressed as fraction of rated power per second)
    v_reconnect   : terminal voltage above which normal operation resumes
    """
    standard:     str
    lvrt_curve:   List[FRTPoint]
    hvrt_curve:   List[FRTPoint]
    k_q_iu:       float   # under-voltage reactive current slope
    k_q_io:       float   # over-voltage reactive current slope
    delta_v_dead: float   # dead-band half-width
    i_q_max_pu:   float   # max reactive current
    p_ramp_mw_s:  float   # P recovery ramp [pu/s]
    v_reconnect:  float   # reconnect threshold

    def in_envelope(self, v_pu: float, t_fault_s: float) -> bool:
        """
        Return True if the operating point (V, t) is within the FRT envelope
        (i.e., the turbine is expected to remain connected).
        """
        # LVRT check: find minimum allowed voltage at this fault duration
        v_min = self._lvrt_v_at_t(t_fault_s)
        # HVRT check: find maximum allowed voltage
        v_max = self._hvrt_v_at_t(t_fault_s)
        return v_min <= v_pu <= v_max

    def _lvrt_v_at_t(self, t: float) -> float:
        """Minimum voltage [pu] the turbine can sustain for duration t."""
        if not self.lvrt_curve:
            return 0.0
        # Binary search for the segment
        pts = self.lvrt_curve
        if t <= pts[0].t_s:
            return pts[0].v_pu
        if t >= pts[-1].t_s:
            return pts[-1].v_pu
        for i in range(len(pts) - 1):
            if pts[i].t_s <= t <= pts[i + 1].t_s:
                frac = (t - pts[i].t_s) / (pts[i + 1].t_s - pts[i].t_s)
                return pts[i].v_pu + frac * (pts[i + 1].v_pu - pts[i].v_pu)
        return pts[-1].v_pu

    def _hvrt_v_at_t(self, t: float) -> float:
        """Maximum voltage [pu] the turbine can sustain for duration t."""
        if not self.hvrt_curve:
            return 2.0
        pts = self.hvrt_curve
        if t <= pts[0].t_s:
            return pts[0].v_pu
        if t >= pts[-1].t_s:
            return pts[-1].v_pu
        for i in range(len(pts) - 1):
            if pts[i].t_s <= t <= pts[i + 1].t_s:
                frac = (t - pts[i].t_s) / (pts[i + 1].t_s - pts[i].t_s)
                return pts[i].v_pu + frac * (pts[i + 1].v_pu - pts[i].v_pu)
        return pts[-1].v_pu

    def reactive_injection(self, v_pu: float,
                            i_max_pu: float = 1.10) -> float:
        """
        Reactive current setpoint [pu] for the given terminal voltage.

        Positive = capacitive (voltage support during LVRT).
        Negative = inductive (voltage absorption during HVRT).
        """
        dv = 1.0 - v_pu
        if abs(dv) <= self.delta_v_dead:
            return 0.0
        if dv > 0:
            # Under-voltage → capacitive injection
            i_q = self.k_q_iu * (dv - self.delta_v_dead)
        else:
            # Over-voltage → inductive absorption
            i_q = self.k_q_io * (dv + self.delta_v_dead)   # negative
        return float(max(-self.i_q_max_pu, min(self.i_q_max_pu,
                                                min(i_q, i_max_pu))))


# ---------------------------------------------------------------------------
# Grid-code definitions
# ---------------------------------------------------------------------------

def _iec_envelope() -> FRTEnvelope:
    """
    IEC 61400-27-1 Type 4 LVRT/HVRT envelope.

    LVRT: 0 pu for 140 ms, then ramp to 0.9 pu at 1.5 s
    HVRT: 1.20 pu for 100 ms, then 1.15 pu continuous
    Reactive: k_q = 2.0 pu/pu, dead-band 0.05 pu
    """
    return FRTEnvelope(
        standard="iec",
        lvrt_curve=[
            FRTPoint(0.00, 0.0),
            FRTPoint(0.00, 0.140),
            FRTPoint(0.90, 1.500),
            FRTPoint(0.90, 60.0),
        ],
        hvrt_curve=[
            FRTPoint(1.20, 0.0),
            FRTPoint(1.20, 0.100),
            FRTPoint(1.15, 60.0),
        ],
        k_q_iu=2.0,
        k_q_io=2.0,
        delta_v_dead=0.05,
        i_q_max_pu=1.00,
        p_ramp_mw_s=0.20,      # 20% rated/s recovery ramp
        v_reconnect=0.85,
    )


def _aemo_envelope() -> FRTEnvelope:
    """
    AEMO NER S5.2.5.14 LVRT envelope (Australian grid code).

    LVRT: 0 pu for 175 ms, ramp to 0.9 pu at 2.0 s
    Reactive: k_q = 4.0 pu/pu (aggressive support), dead-band 0.0 pu
    Active power recovery: 10%/s minimum
    """
    return FRTEnvelope(
        standard="aemo",
        lvrt_curve=[
            FRTPoint(0.00, 0.0),
            FRTPoint(0.00, 0.175),
            FRTPoint(0.70, 0.500),
            FRTPoint(0.90, 2.000),
            FRTPoint(0.90, 60.0),
        ],
        hvrt_curve=[
            FRTPoint(1.25, 0.0),
            FRTPoint(1.25, 0.060),
            FRTPoint(1.15, 60.0),
        ],
        k_q_iu=4.0,
        k_q_io=4.0,
        delta_v_dead=0.00,     # no dead-band per AEMO NER
        i_q_max_pu=1.10,
        p_ramp_mw_s=0.10,
        v_reconnect=0.80,
    )


def _nerc_envelope() -> FRTEnvelope:
    """
    NERC PRC-024-2 + IEEE 1547-2018 LVRT/HVRT envelope.

    LVRT: 0 pu for 160 ms, ramp to 0.88 pu at 3.0 s
    Reactive: k_q = 1.5 pu/pu (more conservative than IEC), dead-band 0.10 pu
    """
    return FRTEnvelope(
        standard="nerc",
        lvrt_curve=[
            FRTPoint(0.00, 0.0),
            FRTPoint(0.00, 0.160),
            FRTPoint(0.50, 0.300),
            FRTPoint(0.88, 3.000),
            FRTPoint(0.88, 60.0),
        ],
        hvrt_curve=[
            FRTPoint(1.20, 0.0),
            FRTPoint(1.20, 0.160),
            FRTPoint(1.10, 60.0),
        ],
        k_q_iu=1.5,
        k_q_io=1.5,
        delta_v_dead=0.10,
        i_q_max_pu=1.00,
        p_ramp_mw_s=0.15,
        v_reconnect=0.88,
    )


# Registry
_ENVELOPES = {
    "iec":  _iec_envelope,
    "aemo": _aemo_envelope,
    "nerc": _nerc_envelope,
}


def get_frt_envelope(standard: str) -> FRTEnvelope:
    """Return the FRTEnvelope for the named standard."""
    key = standard.lower()
    if key not in _ENVELOPES:
        raise KeyError(f"Unknown FRT standard '{standard}'. "
                       f"Choose from {list(_ENVELOPES)}")
    return _ENVELOPES[key]()


def frt_reactive_injection(standard: str, v_pu: float,
                            p_gen_pu: float, i_max_pu: float = 1.10) -> float:
    """
    Compute reactive current setpoint for FRT according to the named standard.

    The returned Q_ref is in pu of rated apparent power.
    P curtailment during deep LVRT is also embedded:
    at V < 0.1 pu, active power is set to 0 (converter blocks).

    Parameters
    ----------
    standard  : 'iec' | 'aemo' | 'nerc'
    v_pu      : terminal voltage [pu]
    p_gen_pu  : current active power [pu]  (used for priority current calc)
    i_max_pu  : maximum total current limit [pu]

    Returns
    -------
    q_ref : float [pu]  (positive = capacitive)
    """
    env  = get_frt_envelope(standard)
    i_q  = env.reactive_injection(v_pu, i_max_pu)
    # Q_ref = i_q × V (power = current × voltage, pu)
    q_ref = i_q * v_pu
    return float(q_ref)


def in_frt_envelope(standard: str, v_pu: float, t_fault_s: float) -> bool:
    """
    Return True if the (V, t) operating point is within the FRT envelope.
    """
    return get_frt_envelope(standard).in_envelope(v_pu, t_fault_s)
