# =============================================================================
# sambp / digital_twin / models / bess_protection_mirror.py
#
# BESS protection mirror — TR-68 WP 68.3
#
# Mirrors the 7 protection functions that a modern grid-connected BESS
# protection relay (e.g. SEL-300G, ABB RET670) would execute.  The mirror
# runs on DT-estimated BESS states rather than raw measurements, allowing the
# DecisionComparator to predict what the relay *should* do and flag deviations.
#
# Protection functions (priority order — first to assert wins):
# ------------------------------------------------------------
#   50DC  — DC Bus Overcurrent (instantaneous at 2.0 pu)
#   59DC  — DC Overvoltage (V_dc > 1.15 pu for ≥ 100 ms)
#   27DC  — DC Undervoltage (V_dc < 0.80 pu for ≥ 500 ms)
#   49    — Thermal Overload (I²t accumulator with reset)
#   32    — Reverse Power (unexpected direction, > 10 s)
#   81R   — RoCoF anti-islanding (|df/dt| > 1.0 Hz/s for ≥ 0.5 s)
#   50/51AC — AC Coupling Overcurrent (definite-time + IEC 60255 inverse)
#
# Public API
# ----------
# mirror = BESSProtectionMirror(cfg)
# decision = mirror.predict(measurements)   → ProtectionDecision
# mirror.reset()                            — clear all accumulators
#
# ProtectionDecision fields
# -------------------------
#   element     : str   — 'TRIP_50DC' | 'TRIP_59DC' | 'TRIP_27DC' |
#                         'TRIP_49' | 'TRIP_32' | 'TRIP_81R' |
#                         'TRIP_50_51AC' | 'NONE'
#   action      : str   — 'TRIP' | 'BLOCK'
#   confidence  : float — normalised margin above threshold (0–1)
#   function_id : str   — ANSI function number string
#   details     : dict  — element-specific diagnostics
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from models.bess_model import BESSConfig, BESSModel


# ---------------------------------------------------------------------------
# Thresholds (tuneable, drawn from IEC 62933-5-2 / BESS protection practice)
# ---------------------------------------------------------------------------

# 50DC — DC overcurrent
_I_DC_INST_PU   = 2.00    # pu — instantaneous pickup (hardware fuse level)
_I_DC_PICKUP_PU = 1.20    # pu — definite-time pickup (lower threshold)
_T_50DC_DT_S    = 0.05    # s  — definite-time delay at _I_DC_PICKUP_PU

# 59DC — DC overvoltage
_V_DC_OV_PU     = 1.15    # pu — overvoltage pickup
_T_59DC_S       = 0.10    # s  — time delay

# 27DC — DC undervoltage
_V_DC_UV_PU     = 0.80    # pu — undervoltage pickup
_T_27DC_S       = 0.50    # s  — time delay (longer — allows LVRT)

# 49 — thermal overload
_I_49_BASE_PU   = 1.00    # pu — thermal base current
_I2T_TRIP       = 10.0    # pu²·s — I²t trip threshold (e.g. 1 s at 3.16 pu)
_I2T_RESET_FRAC = 0.10    # fraction of _I2T_TRIP below which accumulator resets

# 32 — reverse power
_P_REVERSE_PU   = -0.05   # pu — negative power threshold (motor-mode import)
_T_32_S         = 10.0    # s  — confirmation time (prevents nuisance trip)

# 81R — RoCoF
_ROCOF_HZ_S     = 1.00    # Hz/s — ROCOF trip threshold (GB Grid Code)
_T_81R_S        = 0.50    # s    — must persist for this long

# 50/51AC — AC coupling overcurrent
_I_AC_INST_PU   = 2.50    # pu — instantaneous pickup (50)
_I_AC_PICKUP_PU = 1.20    # pu — inverse-time pickup (51)
# IEC 60255 Standard Inverse: t = TMS × 0.14 / ((I/Ip)^0.02 − 1)
_TMS_DEFAULT    = 0.30    # time multiplier setting


# ---------------------------------------------------------------------------
# ProtectionDecision
# ---------------------------------------------------------------------------

@dataclass
class ProtectionDecision:
    """Result of a single BESSProtectionMirror.predict() call."""
    element:     str
    action:      str          # 'TRIP' | 'BLOCK'
    confidence:  float        # normalised margin 0–1
    function_id: str          # ANSI number e.g. '50DC'
    details:     Dict[str, Any] = field(default_factory=dict)

    @property
    def is_trip(self) -> bool:
        return self.action == "TRIP"


# ---------------------------------------------------------------------------
# Measurement dict keys (expected from DT estimation pipeline)
# ---------------------------------------------------------------------------
# measurements = {
#   'i_ac_pu'   : float  — AC current magnitude [pu]
#   'i_dc_pu'   : float  — DC bus current [pu]  (≈ P_dc / V_dc)
#   'v_dc_pu'   : float  — DC bus voltage [pu]
#   'p_ac_pu'   : float  — AC active power [pu] (+ve = export, -ve = import)
#   'freq_hz'   : float  — grid frequency [Hz]  (50 Hz nominal)
#   'rocof_hz_s': float  — rate of change of frequency [Hz/s]
#   't_cell_c'  : float  — cell temperature [°C]  (optional)
#   'dt_s'      : float  — DT step time [s]  (for accumulator updates)
# }


# ---------------------------------------------------------------------------
# BESSProtectionMirror
# ---------------------------------------------------------------------------

class BESSProtectionMirror:
    """
    Digital-twin mirror of the BESS protection relay suite (TR-68 WP 68.3).

    Extends the ProtectionMirror pattern with BESS-specific elements.
    All seven protection functions run in priority order; the first to assert
    returns a TRIP decision.  When none assert, returns BLOCK / NONE.

    Stateful accumulators (per IEC 60255 timer model):
      _acc_59dc  — seconds V_dc has been above _V_DC_OV_PU
      _acc_27dc  — seconds V_dc has been below _V_DC_UV_PU
      _acc_i2t   — cumulative I²t [pu²·s]
      _acc_32    — seconds of persistent reverse power
      _acc_81r   — seconds of persistent over-ROCOF

    Parameters
    ----------
    cfg : BESSConfig
        BESS configuration (uses current_limit_pu, control_mode).
    """

    FUNCTION_PRIORITY = [
        "50DC",     # 1 — DC bus overcurrent (hardware-fastest)
        "59DC",     # 2 — DC overvoltage
        "27DC",     # 3 — DC undervoltage
        "49",       # 4 — thermal overload
        "32",       # 5 — reverse power
        "81R",      # 6 — RoCoF anti-islanding
        "50/51AC",  # 7 — AC overcurrent (definite + inverse time)
    ]

    def __init__(self, cfg: Optional[BESSConfig] = None) -> None:
        self.cfg = cfg or BESSConfig.li_ion_1mwh()
        self.reset()

    # ------------------------------------------------------------------
    # Accumulator management
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stateful accumulators (call on BESS startup or relay reset)."""
        self._acc_59dc: float = 0.0
        self._acc_27dc: float = 0.0
        self._acc_i2t:  float = 0.0
        self._acc_32:   float = 0.0
        self._acc_81r:  float = 0.0

    # ------------------------------------------------------------------
    # IEC 60255 Standard Inverse time curve
    # ------------------------------------------------------------------

    @staticmethod
    def iec_si_time(i_pu: float, i_pickup: float, tms: float = _TMS_DEFAULT) -> float:
        """
        IEC 60255 Standard Inverse characteristic.

        t = TMS × 0.14 / ((I / Ip)^0.02 − 1)

        Returns trip time in seconds.  Returns inf if I ≤ Ip.
        """
        ratio = i_pu / max(i_pickup, 1e-9)
        if ratio <= 1.0:
            return math.inf
        return tms * 0.14 / (ratio ** 0.02 - 1.0)

    # ------------------------------------------------------------------
    # Individual protection function evaluators
    # ------------------------------------------------------------------

    def _eval_50dc(self, m: Dict[str, Any], dt: float) -> Optional[ProtectionDecision]:
        """50DC — DC Bus Overcurrent (instantaneous at 2.0 pu; definite at 1.2 pu)."""
        i_dc = float(m.get("i_dc_pu", 0.0))

        # Instantaneous stage
        if i_dc >= _I_DC_INST_PU:
            conf = min(1.0, (i_dc - _I_DC_INST_PU) / _I_DC_INST_PU)
            return ProtectionDecision(
                element="TRIP_50DC", action="TRIP",
                confidence=conf, function_id="50DC",
                details={"i_dc_pu": i_dc, "stage": "instantaneous"},
            )

        # Definite-time stage — modelled via simple pickup confirm
        # (full integrating timer would require carry-over state; use the
        # instantaneous BESS DT step dt here as the confirmation window)
        if i_dc >= _I_DC_PICKUP_PU:
            conf = min(1.0, (i_dc - _I_DC_PICKUP_PU) / (_I_DC_INST_PU - _I_DC_PICKUP_PU))
            # Return a pending indicator; caller must confirm over _T_50DC_DT_S
            # In single-step mode this does not trip — needs sustained exceedance.
            # Implemented as an immediate decision when margin > 0 for DT use.
            return ProtectionDecision(
                element="TRIP_50DC", action="TRIP",
                confidence=conf * (dt / _T_50DC_DT_S),
                function_id="50DC",
                details={"i_dc_pu": i_dc, "stage": "definite_time"},
            )
        return None

    def _eval_59dc(self, m: Dict[str, Any], dt: float) -> Optional[ProtectionDecision]:
        """59DC — DC Overvoltage (V_dc > 1.15 pu for ≥ 100 ms)."""
        v_dc = float(m.get("v_dc_pu", 1.0))
        if v_dc > _V_DC_OV_PU:
            self._acc_59dc += dt
        else:
            self._acc_59dc = max(0.0, self._acc_59dc - dt * 2.0)  # fast reset

        if self._acc_59dc >= _T_59DC_S:
            conf = min(1.0, (v_dc - _V_DC_OV_PU) / (1.20 - _V_DC_OV_PU))
            return ProtectionDecision(
                element="TRIP_59DC", action="TRIP",
                confidence=max(0.0, conf), function_id="59DC",
                details={"v_dc_pu": v_dc, "acc_s": round(self._acc_59dc, 4)},
            )
        return None

    def _eval_27dc(self, m: Dict[str, Any], dt: float) -> Optional[ProtectionDecision]:
        """27DC — DC Undervoltage (V_dc < 0.80 pu for ≥ 500 ms)."""
        v_dc = float(m.get("v_dc_pu", 1.0))
        if v_dc < _V_DC_UV_PU:
            self._acc_27dc += dt
        else:
            self._acc_27dc = max(0.0, self._acc_27dc - dt * 4.0)

        if self._acc_27dc >= _T_27DC_S:
            conf = min(1.0, (_V_DC_UV_PU - v_dc) / _V_DC_UV_PU)
            return ProtectionDecision(
                element="TRIP_27DC", action="TRIP",
                confidence=max(0.0, conf), function_id="27DC",
                details={"v_dc_pu": v_dc, "acc_s": round(self._acc_27dc, 4)},
            )
        return None

    def _eval_49(self, m: Dict[str, Any], dt: float) -> Optional[ProtectionDecision]:
        """49 — Thermal Overload (I²t accumulator)."""
        i_ac = float(m.get("i_ac_pu", 0.0))
        i_rel = i_ac / _I_49_BASE_PU

        # Accumulate I²·dt; allow passive cooling (negative contribution below base)
        self._acc_i2t += (i_rel ** 2 - 1.0) * dt
        self._acc_i2t = max(0.0, self._acc_i2t)    # floor at zero

        if self._acc_i2t >= _I2T_TRIP:
            conf = min(1.0, (self._acc_i2t - _I2T_TRIP) / _I2T_TRIP)
            return ProtectionDecision(
                element="TRIP_49", action="TRIP",
                confidence=max(0.0, conf), function_id="49",
                details={"i_ac_pu": i_ac, "i2t_acc": round(self._acc_i2t, 4)},
            )
        return None

    def _eval_32(self, m: Dict[str, Any], dt: float) -> Optional[ProtectionDecision]:
        """32 — Reverse Power (unexpected import > 10 s)."""
        p_ac = float(m.get("p_ac_pu", 0.0))
        if p_ac < _P_REVERSE_PU:
            self._acc_32 += dt
        else:
            self._acc_32 = 0.0    # instant reset when power direction correct

        if self._acc_32 >= _T_32_S:
            conf = min(1.0, abs(p_ac - _P_REVERSE_PU) / abs(_P_REVERSE_PU))
            return ProtectionDecision(
                element="TRIP_32", action="TRIP",
                confidence=max(0.0, conf), function_id="32",
                details={"p_ac_pu": p_ac, "acc_s": round(self._acc_32, 4)},
            )
        return None

    def _eval_81r(self, m: Dict[str, Any], dt: float) -> Optional[ProtectionDecision]:
        """81R — RoCoF anti-islanding (|df/dt| > 1.0 Hz/s for ≥ 0.5 s)."""
        rocof = float(m.get("rocof_hz_s", 0.0))
        if abs(rocof) > _ROCOF_HZ_S:
            self._acc_81r += dt
        else:
            self._acc_81r = max(0.0, self._acc_81r - dt)

        if self._acc_81r >= _T_81R_S:
            conf = min(1.0, (abs(rocof) - _ROCOF_HZ_S) / _ROCOF_HZ_S)
            return ProtectionDecision(
                element="TRIP_81R", action="TRIP",
                confidence=max(0.0, conf), function_id="81R",
                details={"rocof_hz_s": rocof, "acc_s": round(self._acc_81r, 4)},
            )
        return None

    def _eval_50_51ac(self, m: Dict[str, Any], dt: float) -> Optional[ProtectionDecision]:
        """50/51AC — AC Coupling Overcurrent (instantaneous 50 + IEC 60255 inverse 51)."""
        i_ac = float(m.get("i_ac_pu", 0.0))

        # 50 — Instantaneous stage
        if i_ac >= _I_AC_INST_PU:
            conf = min(1.0, (i_ac - _I_AC_INST_PU) / _I_AC_INST_PU)
            return ProtectionDecision(
                element="TRIP_50_51AC", action="TRIP",
                confidence=conf, function_id="50/51AC",
                details={"i_ac_pu": i_ac, "stage": "instantaneous_50"},
            )

        # 51 — Inverse-time stage (IEC 60255 SI)
        if i_ac > _I_AC_PICKUP_PU:
            t_trip = self.iec_si_time(i_ac, _I_AC_PICKUP_PU)
            # Confidence = fraction of trip time elapsed in this one step
            # (approximation — full timer state not accumulated here;
            #  use single-step confidence for DT mirroring purposes)
            conf = min(1.0, dt / max(t_trip, 1e-6))
            if conf > 0.0:
                return ProtectionDecision(
                    element="TRIP_50_51AC", action="TRIP",
                    confidence=conf, function_id="50/51AC",
                    details={
                        "i_ac_pu": i_ac,
                        "stage": "inverse_time_51",
                        "t_trip_s": round(t_trip, 4),
                    },
                )
        return None

    # ------------------------------------------------------------------
    # Main predict() — first-to-trip priority chain
    # ------------------------------------------------------------------

    def predict(self, measurements: Dict[str, Any]) -> ProtectionDecision:
        """
        Evaluate all 7 protection functions and return the first to trip.

        Parameters
        ----------
        measurements : dict
            Keys: i_dc_pu, i_ac_pu, v_dc_pu, p_ac_pu, freq_hz,
                  rocof_hz_s, t_cell_c, dt_s.
            Missing keys default to safe nominal values.

        Returns
        -------
        ProtectionDecision — first asserting function wins; NONE if all block.
        """
        dt = float(measurements.get("dt_s", 1e-3))

        evaluators = [
            self._eval_50dc,
            self._eval_59dc,
            self._eval_27dc,
            self._eval_49,
            self._eval_32,
            self._eval_81r,
            self._eval_50_51ac,
        ]

        for fn in evaluators:
            decision = fn(measurements, dt)
            if decision is not None and decision.confidence > 0.0:
                return decision

        return ProtectionDecision(
            element="NONE", action="BLOCK",
            confidence=1.0, function_id="NONE",
            details={},
        )

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def accumulator_state(self) -> Dict[str, float]:
        """Return current accumulator values for monitoring / logging."""
        return {
            "acc_59dc_s": self._acc_59dc,
            "acc_27dc_s": self._acc_27dc,
            "acc_i2t":    self._acc_i2t,
            "acc_32_s":   self._acc_32,
            "acc_81r_s":  self._acc_81r,
        }

    def __repr__(self) -> str:
        return (f"BESSProtectionMirror(chemistry={self.cfg.chemistry}, "
                f"control_mode={self.cfg.control_mode})")
