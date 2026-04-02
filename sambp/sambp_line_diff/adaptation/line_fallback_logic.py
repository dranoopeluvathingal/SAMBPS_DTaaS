"""
line_fallback_logic.py
=======================
Degraded-mode and channel-loss fallback logic for the SAMBP 87L relay.

Motivation
----------
Unlike a bus or transformer, a line protection relay must remain operational
(and secure) even when the communication channel is impaired or lost.  The
87L relay defines three operating modes:

    Mode A — Healthy channel
        Full two-end differential protection active.
        Model-based SAMBP gate supplements conventional trip.

    Mode B — Degraded channel  (jitter / skew within tolerable limits)
        Conventional 87L stays active with tightened thresholds.
        SAMBP gate active but requires n_confirm_degraded ≥ 3 (more hysteresis).
        Skew compensation applied using estimated Δτ from cross-correlation.

    Mode C — Channel loss  (contiguous loss > T_loss_max_s)
        Differential protection suspended.
        Fall back to: single-end distance (21) or overcurrent (50/51) element.
        Simplified local-only OC: trip if I_L_rms > I_loss_trip_pu.

State machine transitions
--------------------------
    Healthy ──(skew/jitter exceed)──▶ Degraded
    Degraded ──(loss exceeds T_loss_max)──▶ Loss
    Loss ──(channel restored for T_restore_s)──▶ Degraded
    Degraded ──(skew/jitter normalise for T_restore_s)──▶ Healthy

References
----------
    IEEE Std C37.243-2015 §8 — Operating Criteria and Security
    Adamiak et al. (2006) — Current Differential Line Protection Without
        Communications
"""

from __future__ import annotations

import numpy as np
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from dataclasses import dataclass, field
from typing import Optional

from models.line_channel_sync_model import ChannelState


# ---------------------------------------------------------------------------
# Fallback configuration
# ---------------------------------------------------------------------------

@dataclass
class FallbackConfig:
    # Mode thresholds
    skew_degraded_thresh: float   = 2.0    # [samples]  Healthy → Degraded
    skew_loss_thresh: float       = 10.0   # [samples]  Degraded → Loss

    # Hysteresis timers [s]
    T_restore_s: float            = 0.5    # channel must be clean before upgrade
    T_loss_max_s: float           = 0.1    # max contiguous loss before Mode C

    # Confirmation windows per mode
    n_confirm_healthy: int        = 2      # cycles for model confirmation
    n_confirm_degraded: int       = 3      # cycles for degraded confirmation

    # Mode C single-end OC backup
    I_loss_trip_pu: float         = 2.5    # OC pickup in channel-loss mode
    I_loss_inst_pu: float         = 6.0    # instantaneous element

    sample_rate_hz: float         = 1000.0


# ---------------------------------------------------------------------------
# Relay mode
# ---------------------------------------------------------------------------

class RelayMode:
    HEALTHY  = "healthy"
    DEGRADED = "degraded"
    LOSS     = "loss"


# ---------------------------------------------------------------------------
# Mode manager
# ---------------------------------------------------------------------------

@dataclass
class ModeManager:
    """Maintains the current relay mode and transitions."""
    current_mode: str           = RelayMode.HEALTHY
    restore_counter_s: float    = 0.0      # how long channel has been clean
    loss_counter_s: float       = 0.0      # how long current loss event has lasted

    def update(
        self,
        channel_state: ChannelState,
        cfg: FallbackConfig,
        dt: float = 0.001,
    ) -> str:
        """
        Update mode based on latest channel state.

        Parameters
        ----------
        channel_state : ChannelState from apply_channel()
        cfg : FallbackConfig
        dt : time step [s]

        Returns
        -------
        current mode string
        """
        cs = channel_state

        # Determine instantaneous channel health
        channel_ok = (
            abs(cs.applied_skew_samples) < cfg.skew_degraded_thresh
            and cs.max_contiguous_loss == 0
        )
        channel_loss = (
            cs.max_contiguous_loss * dt > cfg.T_loss_max_s
        )

        if self.current_mode == RelayMode.HEALTHY:
            if channel_loss:
                self.current_mode = RelayMode.LOSS
                self.restore_counter_s = 0.0
            elif not channel_ok:
                self.current_mode = RelayMode.DEGRADED
                self.restore_counter_s = 0.0

        elif self.current_mode == RelayMode.DEGRADED:
            if channel_loss:
                self.current_mode = RelayMode.LOSS
                self.restore_counter_s = 0.0
            elif channel_ok:
                self.restore_counter_s += dt
                if self.restore_counter_s >= cfg.T_restore_s:
                    self.current_mode = RelayMode.HEALTHY
                    self.restore_counter_s = 0.0
            else:
                self.restore_counter_s = 0.0

        elif self.current_mode == RelayMode.LOSS:
            if channel_ok:
                self.restore_counter_s += dt
                if self.restore_counter_s >= cfg.T_restore_s:
                    self.current_mode = RelayMode.DEGRADED
                    self.restore_counter_s = 0.0
            else:
                self.restore_counter_s = 0.0

        return self.current_mode


# ---------------------------------------------------------------------------
# Mode C: single-end overcurrent backup
# ---------------------------------------------------------------------------

def single_end_oc_trip(
    i_L_abc: np.ndarray,
    cfg: FallbackConfig,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
) -> dict:
    """
    Single-end backup OC protection for Mode C (channel loss).

    Computes RMS over one cycle and evaluates:
        Instantaneous: trip if any-phase peak > I_loss_inst_pu
        Time-overcurrent: trip if RMS > I_loss_trip_pu (inverse-time)

    Parameters
    ----------
    i_L_abc : (3, N) local current [pu]
    cfg : FallbackConfig

    Returns
    -------
    dict: trip (bool), trip_type ('inst'|'oc'|None), I_rms_max
    """
    spc = int(round(sample_rate_hz / freq_hz))
    N   = i_L_abc.shape[1]

    # Peak instantaneous
    I_peak = np.abs(i_L_abc).max()

    # RMS (last cycle)
    n_rms = min(spc, N)
    I_rms = np.sqrt(np.mean(i_L_abc[:, -n_rms:]**2))

    if I_peak > cfg.I_loss_inst_pu:
        return {"trip": True, "trip_type": "inst", "I_rms_max": float(I_rms)}
    elif I_rms > cfg.I_loss_trip_pu:
        return {"trip": True, "trip_type": "oc",   "I_rms_max": float(I_rms)}
    else:
        return {"trip": False, "trip_type": None,  "I_rms_max": float(I_rms)}


# ---------------------------------------------------------------------------
# Confidence gate wrapper for 87L (mode-aware)
# ---------------------------------------------------------------------------

@dataclass
class LineDiffGateDecision:
    final_trip: bool
    mode: str
    source: str       # "model" | "conventional" | "single_end_oc" | "no_trip"
    reason: str
    confidence: float
    f_int: float


def evaluate_line_gate(
    zone_state,                   # LineZoneState
    conventional_trip: bool,
    channel_state: ChannelState,
    i_L_abc: np.ndarray,
    mode: str,
    fallback_cfg: FallbackConfig,
    gate_cfg = None,
    gate_state = None,
) -> tuple[LineDiffGateDecision, object]:
    """
    Mode-aware confidence gate for 87L.

    In Mode A/B:  same SAMBP gate as 87T (require model confirmation).
    In Mode C:    single-end OC backup only.
    """
    # Import here to avoid circular deps
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from adaptation.line_confidence_gate import (
        LineConfidenceGateConfig, LineGateState, evaluate_87L_confidence_gate,
    )

    if gate_cfg is None:
        gate_cfg = LineConfidenceGateConfig()
    if gate_state is None:
        gate_state = LineGateState()

    if mode == RelayMode.LOSS:
        # Mode C: single-end OC backup
        oc = single_end_oc_trip(i_L_abc, fallback_cfg)
        decision = LineDiffGateDecision(
            final_trip = oc["trip"],
            mode       = mode,
            source     = "single_end_oc" if oc["trip"] else "no_trip",
            reason     = f"Mode C — {oc['trip_type']} backup",
            confidence = 0.0,
            f_int      = zone_state.f_int,
        )
        return decision, gate_state

    # Mode A / B: full differential
    n_confirm = (fallback_cfg.n_confirm_degraded
                 if mode == RelayMode.DEGRADED
                 else fallback_cfg.n_confirm_healthy)
    gate_cfg.n_confirm = n_confirm

    dec, gate_state = evaluate_87L_confidence_gate(
        zone_state, conventional_trip, gate_cfg, gate_state,
    )

    return LineDiffGateDecision(
        final_trip = dec.final_trip,
        mode       = mode,
        source     = dec.source,
        reason     = dec.reason,
        confidence = dec.confidence,
        f_int      = zone_state.f_int,
    ), gate_state


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # ---- Mode transitions ---------------------------------------------------
    from models.line_channel_sync_model import ChannelState

    def _cs(skew, contig, total):
        return ChannelState(
            mode="healthy",
            total_lost_samples=total,
            max_contiguous_loss=contig,
            applied_skew_samples=skew,
            effective_delay_samples=5,
        )

    cfg = FallbackConfig(sample_rate_hz=1000.0, T_restore_s=0.05)
    mm  = ModeManager()
    dt  = 0.001

    # 50 steps healthy
    for _ in range(50):
        m = mm.update(_cs(0.5, 0, 0), cfg, dt)
    assert m == RelayMode.HEALTHY, f"Expected HEALTHY got {m}"
    print(f"50 healthy steps → mode={m}")

    # Introduce skew → degraded
    for _ in range(5):
        m = mm.update(_cs(2.5, 0, 0), cfg, dt)
    assert m == RelayMode.DEGRADED, f"Expected DEGRADED got {m}"
    print(f"Skew→ mode={m}")

    # Loss
    for _ in range(5):
        m = mm.update(_cs(0.0, 200, 200), cfg, dt)
    assert m == RelayMode.LOSS, f"Expected LOSS got {m}"
    print(f"Loss → mode={m}")

    # Restore: 50 steps clean → should recover to DEGRADED
    for _ in range(60):
        m = mm.update(_cs(0.0, 0, 0), cfg, dt)
    assert m == RelayMode.DEGRADED, f"Expected DEGRADED after restore got {m}"
    print(f"Restore → mode={m}")

    # ---- Single-end OC backup -----------------------------------------------
    freq = 50.0; fs = 1000.0
    t = np.arange(0, 0.04, 1/fs)
    i_L_fault = np.array([7.0 * np.sin(2*np.pi*freq*t + k*2*np.pi/3)
                           for k in [0,-1,1]])
    oc = single_end_oc_trip(i_L_fault, cfg)
    print(f"OC backup: trip={oc['trip']}  type={oc['trip_type']}  "
          f"I_rms={oc['I_rms_max']:.2f} pu")
    assert oc["trip"] and oc["trip_type"] == "inst", "Should trip instantaneous"

    print("line_fallback_logic self-test PASSED.")
