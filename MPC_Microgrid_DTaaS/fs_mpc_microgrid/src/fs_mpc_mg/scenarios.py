"""Convenience constructors for the three operating modes from [F].

  - loading_mode      : i_dc < 0 (microgrid drawing power from the grid)
  - regenerating_mode : i_dc > 0 (microgrid injecting into the grid)
  - statcom_mode      : i_dc = 0 (pure active-filter / STATCOM)
"""

from __future__ import annotations

from typing import Callable

from .plant import Plant, PlantParams
from .load_model import HarmonicLoad, HarmonicLoadParams
from .pll import IdealPLL
from .inner_fsmpc import FSMPCController, FSMPCParams
from .outer_energy_pi import EnergyPI, EnergyPIParams
from .simulator import Simulator


def _default_load() -> HarmonicLoad:
    return HarmonicLoad(
        HarmonicLoadParams(P_fund=25e3, Q_fund=0.0)
    )


def _build_simulator(i_dc_func: Callable[[float], float]) -> Simulator:
    plant_p = PlantParams()
    inner_p = FSMPCParams(L=plant_p.L, r=plant_p.r, T_s=20e-6, use_delay_compensation=True)
    outer_p = EnergyPIParams(C=plant_p.C, R=plant_p.R, v_dc_ref=plant_p.v_dc_init)
    return Simulator(
        plant=Plant(plant_p),
        load=_default_load(),
        pll=IdealPLL(f_grid=plant_p.f_grid),
        inner=FSMPCController(inner_p),
        outer=EnergyPI(outer_p),
        i_dc_func=i_dc_func,
        N_sub=5,
    )


def loading_mode(i_dc_load_amp: float = 100.0) -> Simulator:
    """Microgrid is drawing `i_dc_load_amp` amps from the DC link (loading)."""
    return _build_simulator(lambda _t: -abs(i_dc_load_amp))


def regenerating_mode(i_dc_inject_amp: float = 100.0) -> Simulator:
    """Microgrid is injecting `i_dc_inject_amp` amps into the DC link (regen)."""
    return _build_simulator(lambda _t: +abs(i_dc_inject_amp))


def statcom_mode() -> Simulator:
    """No bulk DC current — converter acts as pure active filter."""
    return _build_simulator(lambda _t: 0.0)
