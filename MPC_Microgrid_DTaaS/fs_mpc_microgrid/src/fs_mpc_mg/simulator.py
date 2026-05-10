"""Top-level fixed-step simulator.

Ties together the Plant, HarmonicLoad, IdealPLL, FSMPCController, and
EnergyPI into a closed loop. The numerical integration step `dt_int`
should be smaller than the FS-MPC sample time `T_s` (we use T_s / N_sub).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
import numpy as np

from .plant import Plant, PlantParams
from .load_model import HarmonicLoad, HarmonicLoadParams
from .pll import IdealPLL
from .inner_fsmpc import FSMPCController, FSMPCParams
from .outer_energy_pi import EnergyPI, EnergyPIParams


@dataclass
class SimResult:
    """Container for time histories."""

    t: np.ndarray
    v_s: np.ndarray            # (N, 3)
    i_l: np.ndarray            # (N, 3)
    i_m: np.ndarray            # (N, 3)
    i_s: np.ndarray            # (N, 3) = i_m + i_l
    v_dc: np.ndarray           # (N,)
    I_s_amp: np.ndarray        # (N,)
    s_applied: np.ndarray      # (N, 3)
    f_grid: float


class Simulator:
    """Closed-loop simulator with FS-MPC + energy PI + harmonic load."""

    def __init__(
        self,
        plant: Plant,
        load: HarmonicLoad,
        pll: IdealPLL,
        inner: FSMPCController,
        outer: EnergyPI,
        i_dc_func: Callable[[float], float] | None = None,
        N_sub: int = 5,
    ) -> None:
        """
        Parameters
        ----------
        i_dc_func : callable t -> float
            Net DC current injected by the microgrid (positive = regenerating).
            Defaults to zero (STATCOM mode).
        N_sub : int
            Number of integration sub-steps per FS-MPC tick. The plant is
            advanced N_sub times with dt = T_s / N_sub during one T_s.
        """
        self.plant = plant
        self.load = load
        self.pll = pll
        self.inner = inner
        self.outer = outer
        self.i_dc_func = i_dc_func or (lambda _t: 0.0)
        self.N_sub = int(N_sub)

    # ------------------------------------------------------------------
    def run(self, t_end: float) -> SimResult:
        T_s = self.inner.p.T_s
        dt_int = T_s / self.N_sub
        N_steps = int(round(t_end / T_s))

        # storage
        t_hist = np.zeros(N_steps)
        v_s_hist = np.zeros((N_steps, 3))
        i_l_hist = np.zeros((N_steps, 3))
        i_m_hist = np.zeros((N_steps, 3))
        v_dc_hist = np.zeros(N_steps)
        s_hist = np.zeros((N_steps, 3))
        I_s_amp_hist = np.zeros(N_steps)

        # Outer-loop runs every k_outer ticks (here every tick for simplicity;
        # set k_outer = 10 if you want a 200 µs outer @ T_s = 20 µs)
        k_outer_decim = 1

        I_s_amp = 0.0
        s_apply = np.zeros(3)

        for k in range(N_steps):
            t = k * T_s

            # measurements at sample k
            v_s = self.load.v_s(t)
            i_l = self.load.i_l(t)
            i_m = self.plant.i_m.copy()
            v_dc = self.plant.v_dc

            # Outer loop (decimated)
            if k % k_outer_decim == 0:
                I_s_amp = self.outer.update(v_dc, dt=T_s * k_outer_decim)

            # PLL (ideal — get unit sin vector at next sample for ref)
            theta_next, _, unit_next = self.pll.update(t + T_s)
            i_s_ref = I_s_amp * unit_next

            # Inner FS-MPC -> next switching state
            s_apply = self.inner.update(i_m, v_dc, v_s, i_s_ref, i_l)

            # Advance plant by N_sub sub-steps with s_apply (ZOH)
            i_dc = self.i_dc_func(t)
            for _ in range(self.N_sub):
                # use v_s sampled at sub-step time for slightly better fidelity
                tau = t  # could be incremented; effect is tiny at T_s = 20 µs
                v_s_sub = self.load.v_s(tau)
                self.plant.step(s_apply, v_s_sub, i_dc, dt_int)

            # log
            t_hist[k] = t
            v_s_hist[k] = v_s
            i_l_hist[k] = i_l
            i_m_hist[k] = i_m
            v_dc_hist[k] = v_dc
            s_hist[k] = s_apply
            I_s_amp_hist[k] = I_s_amp

        i_s_hist = i_m_hist + i_l_hist
        return SimResult(
            t=t_hist,
            v_s=v_s_hist,
            i_l=i_l_hist,
            i_m=i_m_hist,
            i_s=i_s_hist,
            v_dc=v_dc_hist,
            I_s_amp=I_s_amp_hist,
            s_applied=s_hist,
            f_grid=self.load.p.f_grid,
        )
