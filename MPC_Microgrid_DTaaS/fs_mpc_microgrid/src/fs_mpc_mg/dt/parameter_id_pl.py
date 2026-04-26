"""Phase-locked-decimated RLS identifier.

Wraps :class:`RLSIdentifier` so that updates are committed only once per
fundamental cycle (default: every 20 ms at 50 Hz). Each commit uses the
**most recent FS-MPC sample** (not a cycle-average) at a fixed phase
position within the cycle, which preserves the regressor's information
content while suppressing the high-bandwidth switching ripple via the
lower effective update rate.

This is the simpler, more reliable cousin of cycle-averaging: averaging
a sinusoidal regressor over a full cycle nulls its mean and destroys the
identification signal. Phase-locked decimation keeps the per-sample
regressor intact and just slows the RLS dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .parameter_id import RLSIdentifier, RLSResult


@dataclass
class PhaseLockedRLSParams:
    T_s: float = 20e-6
    f_grid: float = 50.0
    samples_per_cycle: int = 1000
    forgetting: float = 0.99
    init_L: float = 1e-3
    init_r: float = 50e-3
    min_cycles: int = 4


class PhaseLockedRLS:
    """Cycle-decimated RLS for slow plant-parameter drift."""

    def __init__(self, params: PhaseLockedRLSParams | None = None) -> None:
        self.p = params or PhaseLockedRLSParams()
        # Use the original per-sample T_s for the inner RLS so the discrete
        # predictor coefficient (a, b) interpretation is unchanged.
        self._rls = RLSIdentifier(
            T_s=self.p.T_s,
            forgetting=self.p.forgetting,
            init_L=self.p.init_L,
            init_r=self.p.init_r,
            min_samples=self.p.min_cycles,
        )
        self._n = 0
        self._n_cycles_seen = 0

    # ------------------------------------------------------------------
    def push(
        self,
        i_m_now: np.ndarray,
        v_s_now: np.ndarray,
        s_now: np.ndarray,
        v_dc_now: float,
        i_m_next: np.ndarray,
    ) -> RLSResult:
        """Buffer the sample; commit once per cycle."""
        self._n += 1
        if self._n >= self.p.samples_per_cycle:
            self._rls.update(
                i_m_next=np.asarray(i_m_next, dtype=float),
                i_m_now=np.asarray(i_m_now, dtype=float),
                v_s_now=np.asarray(v_s_now, dtype=float),
                s_now=np.asarray(s_now, dtype=float),
                v_dc_now=float(v_dc_now),
            )
            self._n = 0
            self._n_cycles_seen += 1
        return self.estimate

    # ------------------------------------------------------------------
    @property
    def estimate(self) -> RLSResult:
        return self._rls.estimate

    @property
    def n_cycles(self) -> int:
        return self._n_cycles_seen

    def reset(self) -> None:
        self.__init__(self.p)
