# =============================================================================
# sambp / digital_twin / coordination / sync_check_dt.py
#
# DT synchrocheck relay (function 25) — TR-71 WP 71.3
#
# Mirrors the IEEE C37.2 device function 25 (synchronism-check) inside the
# Digital Twin.  The DT version adds IBR-specific features:
#
#   • Uses EKF-derived phasors (from PhasorDFT / SequenceExtractor) rather
#     than direct CT/VT measurements — allows pre-emptive sync prediction
#   • Accounts for GFM-driven angle stiffening (GFM converters hold angle
#     more tightly than a synchronous machine)
#   • Emits SyncCheckResult with margin values for DT logging
#
# Check criteria (all must be satisfied for PERMIT)
# -------------------------------------------------
#   |ΔV|   ≤ delta_v_max   [pu]   — voltage magnitude mismatch
#   |Δf|   ≤ delta_f_max   [Hz]   — frequency mismatch
#   |Δδ|   ≤ delta_angle_max [°]  — phase angle mismatch
#
# Public API
# ----------
#   rel = SyncCheckRelay(delta_v_max=0.10, delta_f_max=0.20, delta_angle_max=20.0)
#   result = rel.check(bus_phasor, line_phasor, ekf_state)
#       → SyncCheckResult(permit, delta_v, delta_f, delta_angle, margin, reason)
#   rel.update_settings(delta_v_max=..., delta_f_max=..., delta_angle_max=...)
# =============================================================================

from __future__ import annotations

import math
import cmath
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# SyncCheckResult
# ---------------------------------------------------------------------------

@dataclass
class SyncCheckResult:
    """Result of one synchronism check."""
    permit:        bool    # True → close CB (in-sync)
    delta_v_pu:    float   # |V_bus - V_line| [pu]
    delta_f_hz:    float   # |f_bus - f_line| [Hz]
    delta_angle_deg: float # |δ_bus - δ_line| [°]
    margin:        float   # normalised composite margin [0=at limit, 1=well inside]
    reason:        str     # "" if permit, else the violated criterion


# ---------------------------------------------------------------------------
# SyncCheckRelay
# ---------------------------------------------------------------------------

class SyncCheckRelay:
    """
    DT synchrocheck relay (device 25) with IBR-aware angle compensation.

    Parameters
    ----------
    delta_v_max       : voltage mismatch threshold [pu]  (default 0.10)
    delta_f_max       : frequency mismatch threshold [Hz] (default 0.20)
    delta_angle_max   : angle mismatch threshold [°]      (default 20.0)
    gfm_angle_stiff   : GFM angle stiffening factor (reduces effective Δδ
                        by this fraction per unit f_gfm) (default 0.50)
    """

    def __init__(self,
                 delta_v_max: float = 0.10,
                 delta_f_max: float = 0.20,
                 delta_angle_max: float = 20.0,
                 gfm_angle_stiff: float = 0.50) -> None:
        self.delta_v_max     = delta_v_max
        self.delta_f_max     = delta_f_max
        self.delta_angle_max = delta_angle_max
        self._gfm_stiff      = gfm_angle_stiff

    # ------------------------------------------------------------------
    def check(self,
              bus_phasor: complex,
              line_phasor: complex,
              ekf_state: Optional[dict] = None,
              f_bus: float = 50.0,
              f_line: float = 50.0) -> SyncCheckResult:
        """
        Perform synchronism check.

        Parameters
        ----------
        bus_phasor  : complex phasor of the bus-side voltage V1 [pu]
        line_phasor : complex phasor of the line-side voltage V1 [pu]
        ekf_state   : EKF state dict (uses f_gfm for angle compensation)
        f_bus       : bus-side fundamental frequency [Hz]
        f_line      : line-side fundamental frequency [Hz]

        Returns
        -------
        SyncCheckResult
        """
        f_gfm = float(ekf_state.get('f_gfm', 0.0)) if ekf_state else 0.0

        # ── Voltage magnitude mismatch ────────────────────────────────
        v_bus  = abs(bus_phasor)
        v_line = abs(line_phasor)
        dv     = abs(v_bus - v_line)

        # ── Frequency mismatch ────────────────────────────────────────
        df = abs(f_bus - f_line)

        # ── Phase angle mismatch ──────────────────────────────────────
        ang_bus  = math.degrees(cmath.phase(bus_phasor))
        ang_line = math.degrees(cmath.phase(line_phasor))
        d_ang_raw = abs(ang_bus - ang_line)
        # Unwrap to [-180, 180]
        if d_ang_raw > 180.0:
            d_ang_raw = 360.0 - d_ang_raw

        # GFM angle stiffening: GFM converters hold angle → effective mismatch
        # is smaller than the raw measurement suggests
        d_ang = d_ang_raw * (1.0 - self._gfm_stiff * f_gfm)
        d_ang = max(0.0, d_ang)

        # ── Check each criterion ──────────────────────────────────────
        reasons = []
        if dv > self.delta_v_max:
            reasons.append(
                f"ΔV={dv:.4f} > {self.delta_v_max:.4f} pu"
            )
        if df > self.delta_f_max:
            reasons.append(
                f"Δf={df:.4f} > {self.delta_f_max:.4f} Hz"
            )
        if d_ang > self.delta_angle_max:
            reasons.append(
                f"Δδ={d_ang:.2f}° > {self.delta_angle_max:.2f}°"
            )

        permit = (len(reasons) == 0)

        # ── Composite margin (0 = at limit, 1 = well inside limits) ──
        v_margin   = 1.0 - dv   / max(self.delta_v_max,   1e-9)
        f_margin   = 1.0 - df   / max(self.delta_f_max,   1e-9)
        ang_margin = 1.0 - d_ang / max(self.delta_angle_max, 1e-9)
        margin     = min(v_margin, f_margin, ang_margin)

        return SyncCheckResult(
            permit=permit,
            delta_v_pu=round(dv, 6),
            delta_f_hz=round(df, 6),
            delta_angle_deg=round(d_ang, 4),
            margin=round(margin, 4),
            reason="; ".join(reasons),
        )

    # ------------------------------------------------------------------
    def update_settings(self,
                        delta_v_max: Optional[float] = None,
                        delta_f_max: Optional[float] = None,
                        delta_angle_max: Optional[float] = None) -> None:
        """Update one or more threshold settings in-place."""
        if delta_v_max     is not None:
            self.delta_v_max     = float(delta_v_max)
        if delta_f_max     is not None:
            self.delta_f_max     = float(delta_f_max)
        if delta_angle_max is not None:
            self.delta_angle_max = float(delta_angle_max)

    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (f"SyncCheckRelay(ΔV≤{self.delta_v_max}, "
                f"Δf≤{self.delta_f_max}Hz, Δδ≤{self.delta_angle_max}°)")
