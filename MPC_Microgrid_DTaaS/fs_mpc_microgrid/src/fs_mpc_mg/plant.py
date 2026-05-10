"""3-phase 2-level VSI + L-filter + DC-link continuous-time plant.

Implements Eqs. (1) and (2) of Perez & Flores-Bahamonde (2016):

    C  dv_dc/dt + v_dc/R    =  s^T i_m  -  i_dc                    (1)
    L  di_m/dt  + r  i_m    =  v_s      -  M s v_dc                (2)

with s = [s_a, s_b, s_c] in {0,1}^3 and the standard zero-sequence-removal
matrix

         | 2  -1  -1 |
    M = -|-1   2  -1 |  / 3
         |-1  -1   2 |

Sign convention: i_dc > 0 means the microgrid is *injecting* current into
the DC link (regenerating), i_dc < 0 means consuming (loading).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

# ---------------------------------------------------------------------------
# Constants

M_MATRIX = (1.0 / 3.0) * np.array(
    [
        [2.0, -1.0, -1.0],
        [-1.0, 2.0, -1.0],
        [-1.0, -1.0, 2.0],
    ]
)

# Eight switching vectors s in {0,1}^3
SWITCHING_VECTORS = np.array(
    [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 0],
        [0, 1, 0],
        [0, 1, 1],
        [0, 0, 1],
        [1, 0, 1],
        [1, 1, 1],
    ],
    dtype=float,
)


# ---------------------------------------------------------------------------
# Parameters


@dataclass
class PlantParams:
    """Plant parameters from Table I of [F] (defaults)."""

    # AC side
    L: float = 1e-3        # filter inductance (H)
    r: float = 50e-3       # parasitic resistance (ohm)
    V_s_rms_ll: float = 380.0   # grid voltage RMS line-to-line (V)
    f_grid: float = 50.0   # grid frequency (Hz)

    # DC side
    C: float = 1000e-6     # DC-link capacitance (F)
    R: float = 1e4         # DC-link parallel-loss resistor (ohm)
    v_dc_init: float = 900.0    # initial DC-link voltage (V)


# ---------------------------------------------------------------------------
# Plant


class Plant:
    """Continuous-time microgrid interface converter plant.

    State: x = [i_m_a, i_m_b, i_m_c, v_dc]

    Inputs:
        s     — switching vector, shape (3,), entries in {0,1}
        v_s   — three-phase grid voltage, shape (3,)  (V)
        i_l   — three-phase load current at PCC, shape (3,)  (A)
                NOTE: not directly used by the plant ODE; included so that the
                Simulator can compute i_s = i_m + i_l outside the plant.
        i_dc  — net DC current into the DC link (A), sign per docstring.

    The integrator is a fixed-step RK4 over a *sub-step* dt small enough
    to handle the stiff AC-side dynamics (typically dt = T_s / N_sub with
    N_sub >= 5). The Simulator manages this.
    """

    def __init__(self, params: PlantParams | None = None) -> None:
        self.p = params or PlantParams()

        # State
        self.i_m = np.zeros(3, dtype=float)
        self.v_dc = float(self.p.v_dc_init)

    # ------------------------------------------------------------------
    # ODE rhs

    def _rhs(
        self,
        x: np.ndarray,
        s: np.ndarray,
        v_s: np.ndarray,
        i_dc: float,
    ) -> np.ndarray:
        """Compute dx/dt with x = [i_m_a, i_m_b, i_m_c, v_dc]."""
        i_m = x[:3]
        v_dc = x[3]

        # AC side: L di_m/dt + r i_m = v_s - M s v_dc
        di_m_dt = (v_s - M_MATRIX @ s * v_dc - self.p.r * i_m) / self.p.L

        # DC side: C dv_dc/dt + v_dc/R = s^T i_m - i_dc
        dv_dc_dt = (s @ i_m - i_dc - v_dc / self.p.R) / self.p.C

        return np.concatenate([di_m_dt, [dv_dc_dt]])

    # ------------------------------------------------------------------
    # RK4 step

    def step(
        self,
        s: np.ndarray,
        v_s: np.ndarray,
        i_dc: float,
        dt: float,
    ) -> None:
        """Advance the plant state by `dt` using RK4 with the given inputs held constant.

        For accurate EMT integration, callers should choose dt < T_s / 5.
        """
        x0 = np.concatenate([self.i_m, [self.v_dc]])

        k1 = self._rhs(x0, s, v_s, i_dc)
        k2 = self._rhs(x0 + 0.5 * dt * k1, s, v_s, i_dc)
        k3 = self._rhs(x0 + 0.5 * dt * k2, s, v_s, i_dc)
        k4 = self._rhs(x0 + dt * k3, s, v_s, i_dc)

        x1 = x0 + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        self.i_m = x1[:3]
        self.v_dc = float(x1[3])

    # ------------------------------------------------------------------
    # Helpers

    def reset(self) -> None:
        self.i_m = np.zeros(3, dtype=float)
        self.v_dc = float(self.p.v_dc_init)

    @property
    def state(self) -> np.ndarray:
        return np.concatenate([self.i_m, [self.v_dc]])
