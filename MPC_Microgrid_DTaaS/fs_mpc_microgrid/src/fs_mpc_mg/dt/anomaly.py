"""Residual-based anomaly detector.

Maintains a sliding-window estimate of the nominal residual mean/std and
raises an `AnomalyEvent` when the most recent residual exceeds
`n_sigma * std` for `dwell_count` consecutive samples.

This is the threshold-based variant from §13 of the implementation plan.
A drop-in replacement with one-class SVM (sklearn) is straightforward and
left to a future deliverable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
import math
import time
from typing import Iterable


@dataclass
class AnomalyEvent:
    ts: float
    ica_id: str
    metric: str           # "v_dc_residual" | "i_m_residual_norm"
    value: float
    threshold: float
    severity: str         # "info" | "warning" | "critical"
    reason: str = ""


class _RunningStats:
    """Welford-style running mean/var with exponential forgetting."""
    def __init__(self, alpha: float = 0.001) -> None:
        self.alpha = float(alpha)
        self.mean = 0.0
        self.var = 1.0
        self.n = 0

    def update(self, x: float) -> None:
        self.n += 1
        if self.n == 1:
            self.mean = x
            self.var = 1e-3
            return
        d = x - self.mean
        self.mean += self.alpha * d
        self.var = (1 - self.alpha) * (self.var + self.alpha * d * d)

    @property
    def std(self) -> float:
        return math.sqrt(max(self.var, 1e-12))


class AnomalyDetector:
    """Tracks one ICA's residual streams (v_dc and ||i_m||).

    Calibrates passively from the first `warmup_samples` ticks, then
    raises events when residuals exceed `n_sigma`.
    """

    def __init__(
        self,
        ica_id: str,
        n_sigma: float = 5.0,
        dwell_count: int = 5,
        warmup_samples: int = 50,
        alpha: float = 0.005,
    ) -> None:
        self.ica_id = ica_id
        self.n_sigma = float(n_sigma)
        self.dwell_count = int(dwell_count)
        self.warmup_samples = int(warmup_samples)

        self._stats: dict[str, _RunningStats] = {
            "v_dc_residual": _RunningStats(alpha=alpha),
            "i_m_residual_norm": _RunningStats(alpha=alpha),
        }
        self._dwell: dict[str, int] = {"v_dc_residual": 0, "i_m_residual_norm": 0}

    # ------------------------------------------------------------------
    def update(
        self,
        v_dc_residual: float,
        i_m_residual_norm: float,
        ts: float | None = None,
    ) -> list[AnomalyEvent]:
        ts = ts if ts is not None else time.time()
        events: list[AnomalyEvent] = []
        signals = {
            "v_dc_residual": abs(float(v_dc_residual)),
            "i_m_residual_norm": float(i_m_residual_norm),
        }

        for metric, value in signals.items():
            stats = self._stats[metric]
            if stats.n < self.warmup_samples:
                # Pure calibration window; never alarm.
                stats.update(value)
                self._dwell[metric] = 0
                continue

            threshold = abs(stats.mean) + self.n_sigma * stats.std
            if value > threshold:
                self._dwell[metric] += 1
                if self._dwell[metric] >= self.dwell_count:
                    severity = "critical" if value > 2.0 * threshold else "warning"
                    events.append(AnomalyEvent(
                        ts=ts, ica_id=self.ica_id, metric=metric,
                        value=value, threshold=threshold, severity=severity,
                        reason=(f"{value:.3g} exceeded {self.n_sigma:g}-sigma "
                                f"(mean={stats.mean:.3g}, std={stats.std:.3g}) "
                                f"for {self._dwell[metric]} ticks"),
                    ))
                    # Hold dwell at threshold so we don't double-fire each tick
                    self._dwell[metric] = self.dwell_count
            else:
                # Slowly track the drift back to nominal
                stats.update(value)
                self._dwell[metric] = 0
        return events

    # ------------------------------------------------------------------
    @property
    def baseline(self) -> dict[str, tuple[float, float]]:
        return {k: (s.mean, s.std) for k, s in self._stats.items()}
