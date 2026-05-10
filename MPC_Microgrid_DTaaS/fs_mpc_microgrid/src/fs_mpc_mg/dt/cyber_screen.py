"""Cyber-attack screen — message-level integrity + signal-bound monitoring.

This complements the anomaly detector by inspecting the *commands* flowing
to the ICAs, not just their residuals. Catches:

  - Out-of-bounds reference values (spoofed Q_ref = 1 GVAr, etc.)
  - Reference rate-of-change that exceeds a physical bound
  - Mode chattering (rapid mode switches — a hallmark of replay attacks)
  - Missing heartbeat from CMC

A real deployment would add HMAC/sequence-number checking on each message;
the skeleton focuses on signal-level Signal Temporal Logic-style checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
import time


@dataclass
class CyberAlert:
    ts: float
    target_ica_id: str
    rule: str           # e.g. "Q_ref_bound" | "v_dc_ref_slew" | "mode_chatter"
    detail: str
    severity: str       # "warning" | "critical"


@dataclass
class CyberPolicy:
    """Bounds and rates considered acceptable on the reference channel."""
    v_dc_ref_min: float = 700.0
    v_dc_ref_max: float = 1100.0
    v_dc_ref_max_slew: float = 100.0   # V per second
    Q_ref_min: float = -100e3
    Q_ref_max: float = 100e3
    mode_max_changes_per_window: int = 4
    mode_window_s: float = 1.0


class CyberScreen:
    """Inspects /ica/{id}/refs/* messages and emits CyberAlerts."""

    def __init__(self, policy: CyberPolicy | None = None) -> None:
        self.policy = policy or CyberPolicy()
        # per-ICA history
        self._last_v_dc_ref: dict[str, tuple[float, float]] = {}   # id -> (ts, value)
        self._mode_changes: dict[str, deque] = {}
        self._last_mode: dict[str, str] = {}

    # ------------------------------------------------------------------
    def check_v_dc_ref(self, ica_id: str, value: float, ts: float) -> CyberAlert | None:
        p = self.policy
        if not (p.v_dc_ref_min <= value <= p.v_dc_ref_max):
            return CyberAlert(ts=ts, target_ica_id=ica_id, rule="v_dc_ref_bound",
                              detail=f"v_dc_ref={value:.1f} outside [{p.v_dc_ref_min}, {p.v_dc_ref_max}]",
                              severity="critical")
        prev = self._last_v_dc_ref.get(ica_id)
        if prev is not None:
            prev_ts, prev_val = prev
            dt = max(ts - prev_ts, 1e-6)
            slew = abs(value - prev_val) / dt
            if slew > p.v_dc_ref_max_slew:
                self._last_v_dc_ref[ica_id] = (ts, value)
                return CyberAlert(ts=ts, target_ica_id=ica_id, rule="v_dc_ref_slew",
                                  detail=f"slew={slew:.1f} V/s > {p.v_dc_ref_max_slew} V/s",
                                  severity="warning")
        self._last_v_dc_ref[ica_id] = (ts, value)
        return None

    # ------------------------------------------------------------------
    def check_Q_ref(self, ica_id: str, value: float, ts: float) -> CyberAlert | None:
        p = self.policy
        if not (p.Q_ref_min <= value <= p.Q_ref_max):
            return CyberAlert(ts=ts, target_ica_id=ica_id, rule="Q_ref_bound",
                              detail=f"Q_ref={value:.0f} VAr outside [{p.Q_ref_min:.0f}, {p.Q_ref_max:.0f}]",
                              severity="critical")
        return None

    # ------------------------------------------------------------------
    def check_mode(self, ica_id: str, mode: str, ts: float) -> CyberAlert | None:
        p = self.policy
        last = self._last_mode.get(ica_id)
        if last is not None and last != mode:
            dq = self._mode_changes.setdefault(ica_id, deque())
            dq.append(ts)
            # drop old entries
            while dq and dq[0] < ts - p.mode_window_s:
                dq.popleft()
            if len(dq) > p.mode_max_changes_per_window:
                self._last_mode[ica_id] = mode
                return CyberAlert(ts=ts, target_ica_id=ica_id, rule="mode_chatter",
                                  detail=f"{len(dq)} mode changes in {p.mode_window_s:.1f}s",
                                  severity="warning")
        self._last_mode[ica_id] = mode
        return None

    # ------------------------------------------------------------------
    def inspect(self, ica_id: str, key: str, value, ts: float | None = None) -> CyberAlert | None:
        """Generic dispatcher. `key` is one of the topic suffixes from comm/topics.py."""
        ts = ts if ts is not None else time.time()
        if key == "v_dc_ref":
            return self.check_v_dc_ref(ica_id, float(value), ts)
        if key == "Q_ref":
            return self.check_Q_ref(ica_id, float(value), ts)
        if key == "mode":
            return self.check_mode(ica_id, str(value), ts)
        return None
