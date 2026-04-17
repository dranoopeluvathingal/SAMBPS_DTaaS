# =============================================================================
# sambp / digital_twin / models / gic_model.py
#
# Geomagnetically Induced Current (GIC) flow calculator — TR-81 WP 81.1
#
# Theory — Lehtinen-Pirjola (LP) method
# --------------------------------------
# A geomagnetic disturbance (GMD) induces a quasi-DC electric field E [V/km]
# at the Earth's surface.  This drives GIC through the power network via
# grounded transformer neutrals.
#
# The LP formulation (Lehtinen & Pirjola, 1985):
#
#   (Yn + Ye) · V = Je
#
# where:
#   Yn   = network nodal admittance matrix (from line conductances)
#   Ye   = earthing admittance matrix (diagonal — grounding at each bus)
#   V    = induced substation voltage vector [V]
#   Je   = current injection vector from geo-electric field [A]
#          Je_k = sum_j (E · L_kj / R_kj)  over all lines adjacent to bus k
#
# GIC at each grounded bus (transformer neutral):
#   I_GIC_k = Ye_kk · V_k   [A, quasi-DC]
#
# Geo-electric field model
# ------------------------
# Uniform field over the network (first-order approximation):
#   E_x [V/km], E_y [V/km]  (geographic East and North components)
#
# For each transmission line between buses i and j with geographic
# coordinates (x_i, y_i) and (x_j, y_j) [km]:
#   EMF_ij = E_x·(x_j−x_i) + E_y·(y_j−y_i)   [V]
#
# The sign convention: current flows from lower to higher geopotential.
#
# Validation benchmark
# --------------------
# 3-bus network from Lehtinen & Pirjola (1985), Table 1:
#   Bus 1: (0, 0) km, R_earth = 2.0 Ω
#   Bus 2: (0, 200) km, R_earth = 2.0 Ω
#   Bus 3: (200, 100) km, R_earth = 2.0 Ω
# Lines: R_12=2.0 Ω, R_13=2.0 Ω, R_23=2.0 Ω
# E_x=1 V/km, E_y=0
# Expected: I_GIC_1 ≈ 50 A, I_GIC_2 ≈ −25 A, I_GIC_3 ≈ −25 A (approx.)
#
# Public API
# ----------
#   net = GICNetwork.from_buses_lines(buses, lines)
#   result = net.solve(E_x_V_km, E_y_V_km)  → GICResult
# =============================================================================

from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Input structures
# ---------------------------------------------------------------------------

@dataclass
class GICBus:
    """A substation bus with geographic coordinates and earthing resistance."""
    id:          int
    name:        str
    x_km:        float   # geographic Easting [km]
    y_km:        float   # geographic Northing [km]
    R_earth_Ohm: float   # substation earthing resistance [Ω] (grounded)
    V_nom_kV:    float = 220.0   # nominal voltage for per-unit conversion
    grounded:    bool  = True    # False = delta or ungrounded wye → no GIC path

    @property
    def Y_earth(self) -> float:
        """Earthing admittance [S]. Zero if ungrounded."""
        if not self.grounded or self.R_earth_Ohm <= 0:
            return 0.0
        return 1.0 / self.R_earth_Ohm


@dataclass
class GICLine:
    """A transmission line between two buses."""
    id:      int
    from_id: int
    to_id:   int
    R_Ohm:   float   # line DC resistance [Ω]  (series resistance only for GIC)

    @property
    def Y_line(self) -> float:
        return 1.0 / max(self.R_Ohm, 1e-9)


# ---------------------------------------------------------------------------
# GICResult
# ---------------------------------------------------------------------------

@dataclass
class GICResult:
    """Output of the Lehtinen-Pirjola GIC solver."""
    bus_ids:      List[int]
    bus_names:    List[str]
    V_node_V:     np.ndarray     # node voltages (geo-induced) [V]
    I_GIC_A:      np.ndarray     # GIC at each bus neutral [A]
    I_line_A:     Dict[int, float]  # GIC in each line (line_id → A)
    E_x_V_km:     float
    E_y_V_km:     float
    E_magnitude:  float          # |E| [V/km]
    max_I_GIC_A:  float          # peak bus GIC magnitude [A]


# ---------------------------------------------------------------------------
# GICNetwork
# ---------------------------------------------------------------------------

class GICNetwork:
    """
    Lehtinen-Pirjola GIC flow solver.

    Parameters
    ----------
    buses : List[GICBus]
    lines : List[GICLine]
    """

    def __init__(self, buses: List[GICBus], lines: List[GICLine]) -> None:
        self._buses = buses
        self._lines = lines
        self._bus_idx: Dict[int, int] = {b.id: i for i, b in enumerate(buses)}

    # ------------------------------------------------------------------
    @classmethod
    def from_buses_lines(cls, buses: List[GICBus],
                         lines: List[GICLine]) -> "GICNetwork":
        return cls(buses, lines)

    # ------------------------------------------------------------------
    def solve(self, E_x_V_km: float, E_y_V_km: float) -> GICResult:
        """
        Solve GIC flow using the Lehtinen-Pirjola method.

        Parameters
        ----------
        E_x_V_km : geo-electric field East component [V/km]
        E_y_V_km : geo-electric field North component [V/km]

        Returns
        -------
        GICResult
        """
        n  = len(self._buses)
        Yn = np.zeros((n, n))
        Ye = np.zeros((n, n))
        Je = np.zeros(n)

        # ── Build network admittance matrix Yn ──────────────────────────
        for line in self._lines:
            i = self._bus_idx[line.from_id]
            j = self._bus_idx[line.to_id]
            y = line.Y_line
            Yn[i, i] += y
            Yn[j, j] += y
            Yn[i, j] -= y
            Yn[j, i] -= y

        # ── Build earthing admittance matrix Ye (diagonal) ──────────────
        for bus in self._buses:
            i = self._bus_idx[bus.id]
            Ye[i, i] = bus.Y_earth

        # ── Compute current injections Je from geo-electric field ────────
        for line in self._lines:
            i  = self._bus_idx[line.from_id]
            j  = self._bus_idx[line.to_id]
            bi = self._buses[i]
            bj = self._buses[j]
            # Induced EMF along the line [V]
            emf = (E_x_V_km * (bj.x_km - bi.x_km) +
                   E_y_V_km * (bj.y_km - bi.y_km))
            # EMF acts as a voltage source in series with line conductance:
            # current injection at "from" bus = emf × Y_line
            # (positive into from_bus, negative into to_bus)
            Je[i] += emf * line.Y_line
            Je[j] -= emf * line.Y_line

        # ── Solve (Yn + Ye) · V = Je ────────────────────────────────────
        A = Yn + Ye
        # Handle ungrounded buses: if row/col is all zero in Ye and bus has
        # no earthing, voltage at that bus floats (add small regularisation)
        for idx in range(n):
            if abs(A[idx, idx]) < 1e-12:
                A[idx, idx] = 1e-9   # regularise isolated bus

        try:
            V = np.linalg.solve(A, Je)
        except np.linalg.LinAlgError:
            V = np.linalg.lstsq(A, Je, rcond=None)[0]

        # ── GIC at each bus neutral ──────────────────────────────────────
        I_GIC = np.array([Ye[i, i] * V[i] for i in range(n)])

        # ── GIC in each line ─────────────────────────────────────────────
        I_line: Dict[int, float] = {}
        for line in self._lines:
            i  = self._bus_idx[line.from_id]
            j  = self._bus_idx[line.to_id]
            bi = self._buses[i]
            bj = self._buses[j]
            emf = (E_x_V_km * (bj.x_km - bi.x_km) +
                   E_y_V_km * (bj.y_km - bi.y_km))
            # Line current = (V_i - V_j + EMF) / R_line
            I_line[line.id] = float((V[i] - V[j] + emf) * line.Y_line)

        E_mag  = math.sqrt(E_x_V_km**2 + E_y_V_km**2)
        max_gic = float(np.max(np.abs(I_GIC)))

        return GICResult(
            bus_ids=[b.id for b in self._buses],
            bus_names=[b.name for b in self._buses],
            V_node_V=V,
            I_GIC_A=I_GIC,
            I_line_A=I_line,
            E_x_V_km=E_x_V_km,
            E_y_V_km=E_y_V_km,
            E_magnitude=E_mag,
            max_I_GIC_A=max_gic,
        )


# ---------------------------------------------------------------------------
# Benchmark network (Lehtinen & Pirjola 1985, 3-bus example)
# ---------------------------------------------------------------------------

def make_lp_benchmark() -> GICNetwork:
    """
    3-bus benchmark from Lehtinen & Pirjola (1985).
    Bus 1: (0,0), Bus 2: (0,200), Bus 3: (200,100) km
    Line R = 2 Ω each; earthing R = 2 Ω each.
    """
    buses = [
        GICBus(id=1, name="Bus1", x_km=0.0,   y_km=0.0,   R_earth_Ohm=2.0),
        GICBus(id=2, name="Bus2", x_km=0.0,   y_km=200.0, R_earth_Ohm=2.0),
        GICBus(id=3, name="Bus3", x_km=200.0, y_km=100.0, R_earth_Ohm=2.0),
    ]
    lines = [
        GICLine(id=1, from_id=1, to_id=2, R_Ohm=2.0),
        GICLine(id=2, from_id=1, to_id=3, R_Ohm=2.0),
        GICLine(id=3, from_id=2, to_id=3, R_Ohm=2.0),
    ]
    return GICNetwork.from_buses_lines(buses, lines)


def make_5bus_gic_network() -> GICNetwork:
    """
    5-bus 400 kV network for integration testing.
    Loosely based on a north-south corridor (high GMD vulnerability).
    """
    buses = [
        GICBus(id=1, name="North_A",  x_km=0.0,   y_km=0.0,   R_earth_Ohm=1.5, V_nom_kV=400),
        GICBus(id=2, name="North_B",  x_km=100.0, y_km=50.0,  R_earth_Ohm=1.5, V_nom_kV=400),
        GICBus(id=3, name="Centre",   x_km=150.0, y_km=200.0, R_earth_Ohm=2.0, V_nom_kV=400),
        GICBus(id=4, name="South_A",  x_km=50.0,  y_km=350.0, R_earth_Ohm=2.5, V_nom_kV=400),
        GICBus(id=5, name="South_B",  x_km=200.0, y_km=350.0, R_earth_Ohm=2.5, V_nom_kV=400),
    ]
    lines = [
        GICLine(id=1, from_id=1, to_id=2, R_Ohm=1.8),
        GICLine(id=2, from_id=1, to_id=3, R_Ohm=3.5),
        GICLine(id=3, from_id=2, to_id=3, R_Ohm=2.2),
        GICLine(id=4, from_id=3, to_id=4, R_Ohm=3.0),
        GICLine(id=5, from_id=3, to_id=5, R_Ohm=2.8),
        GICLine(id=6, from_id=4, to_id=5, R_Ohm=1.5),
    ]
    return GICNetwork.from_buses_lines(buses, lines)
