"""Look-ahead Q forecaster.

A simple but useful contribution to the CMC dispatch loop: given a buffer
of recent load-current observations, predict the load's reactive power
demand `H` seconds into the future. This lets the CMC pre-emptively
adjust Q dispatch instead of waiting for the inner-loop transient.

Method (skeleton):
    1. Compute instantaneous q_l(t) ≈ sum_phase v_s_perp * i_l_perp where
       v_s_perp is the 90°-shifted grid voltage. We approximate this with
       a sliding RMS of |i_l|.
    2. Fit a linear trend over the buffer; extrapolate to t + H.

A future deliverable swaps step 2 for an LSTM / Kalman predictor.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import time
import numpy as np


@dataclass
class ForecastResult:
    horizon_s: float
    Q_total_predicted: float
    Q_total_now: float
    trend_slope: float           # VAr per second


class QForecaster:
    """Per-fleet Q forecaster (single bus assumed for the skeleton)."""

    def __init__(
        self,
        f_grid: float = 50.0,
        v_phase_peak: float = 310.0,
        horizon_s: float = 0.2,
        window_s: float = 0.10,    # cycle-aligned at 50 Hz: 5 cycles
        sample_period_s: float = 1e-3,
    ) -> None:
        self.f_grid = float(f_grid)
        self.v_peak = float(v_phase_peak)
        self.horizon_s = float(horizon_s)
        self.window_s = float(window_s)
        self.sample_period_s = float(sample_period_s)
        n_max = int(self.window_s / self.sample_period_s) + 4
        self._t_buf: deque[float] = deque(maxlen=n_max)
        self._q_buf: deque[float] = deque(maxlen=n_max)

    # ------------------------------------------------------------------
    def push(self, t: float, i_l_abc) -> None:
        """Append a new instantaneous Q sample.

        Approximation: Q_inst ≈ (3/2) * V_peak * I_l_perp, where I_l_perp
        is the magnitude of the 90°-shifted load current. We use the
        envelope of |i_l| as a stand-in.
        """
        i = np.asarray(i_l_abc, dtype=float)
        i_l_envelope = float(np.linalg.norm(i)) / math.sqrt(2.0)
        # Crude proxy for Q (positive sign convention)
        q_inst = 1.5 * self.v_peak * i_l_envelope * 0.3   # 0.3 ~ assumed Q/S ratio
        self._t_buf.append(float(t))
        self._q_buf.append(q_inst)

    # ------------------------------------------------------------------
    def predict(self) -> ForecastResult | None:
        if len(self._t_buf) < 5:
            return None
        ts = np.fromiter(self._t_buf, dtype=float)
        qs = np.fromiter(self._q_buf, dtype=float)
        # Linear fit q = m*t + c  (simple least squares)
        a = np.vstack([ts, np.ones_like(ts)]).T
        coef, *_ = np.linalg.lstsq(a, qs, rcond=None)
        m, c = float(coef[0]), float(coef[1])
        t_now = float(ts[-1])
        q_now = m * t_now + c
        q_future = m * (t_now + self.horizon_s) + c
        return ForecastResult(
            horizon_s=self.horizon_s,
            Q_total_predicted=q_future,
            Q_total_now=q_now,
            trend_slope=m,
        )
