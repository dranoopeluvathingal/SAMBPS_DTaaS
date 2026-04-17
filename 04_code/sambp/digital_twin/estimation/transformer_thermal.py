# =============================================================================
# sambp / digital_twin / estimation / transformer_thermal.py
#
# Transformer hot-spot thermal model with GIC loading — TR-81 WP 81.2
#
# Standard: IEC 60076-7:2018 (Loading guide for oil-immersed transformers)
#
# Thermal model (simplified — IEC 60076-7 Annex A, Thermal model 1)
# ------------------------------------------------------------------
# Two coupled first-order thermal differential equations:
#
# Top-oil temperature rise:
#   τ_TO · dΔΘ_TO/dt = ΔΘ_TO_R·[(K²+R)/(1+R)]^n_TO − ΔΘ_TO
#
# Hot-spot rise over top-oil:
#   τ_HS · dΔΘ_HS/dt = ΔΘ_HS_R·K^(2n_HS) − ΔΘ_HS
#
# Where:
#   K        = load factor = I / I_rated  (≥0)
#   R        = ratio of load losses to no-load losses at rated current
#   n_TO     = oil exponent (0.8 for ONAN, 0.9 for ONAF)
#   n_HS     = winding exponent (1.3 for ONAN, 1.1 for ONAF)
#   ΔΘ_TO_R  = rated top-oil rise over ambient [°C]
#   ΔΘ_HS_R  = rated hot-spot rise over top-oil [°C]
#   τ_TO     = oil thermal time constant [min]
#   τ_HS     = winding thermal time constant [min]
#
# Hot-spot temperature:
#   Θ_HS = Θ_ambient + ΔΘ_TO + ΔΘ_HS
#
# GIC additional heating
# ----------------------
# GIC drives half-cycle saturation of the transformer core, increasing
# magnetising current and reactive power absorption.  The additional heating
# is modelled as an equivalent additional load factor increment:
#
#   K_eff = sqrt(K² + K_GIC²)
#   K_GIC = (I_GIC / I_rated) × k_gic_factor
#
# k_gic_factor ≈ 0.3–1.0 depending on transformer design; default 0.5.
# (This is a conservative linearised approximation — CIGRE TB 501.)
#
# Alarm levels (IEEE C57.91 / IEC 60076-7):
#   NORMAL   : Θ_HS < 98°C
#   ELEVATED : 98°C ≤ Θ_HS < 120°C
#   CRITICAL : 120°C ≤ Θ_HS < 140°C
#   TRIP     : Θ_HS ≥ 140°C  (imminent insulation damage)
#
# Ageing acceleration factor (IEC 60076-7 Eq. 2):
#   V = exp(15000/383 − 15000/(Θ_HS + 273))
#   V=1 at Θ_HS=98°C (rated hotspot temperature)
#
# Public API
# ----------
#   model = TransformerThermalModel(params)
#   model.step(dt_min, K_load, I_GIC_A, Theta_ambient)  → ThermalState
#   model.reset(Theta_ambient)
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# TransformerThermalParams
# ---------------------------------------------------------------------------

@dataclass
class TransformerThermalParams:
    """IEC 60076-7 transformer thermal parameters."""
    # Rated quantities
    S_rated_MVA:   float = 100.0   # rated apparent power [MVA]
    I_rated_A:     float = 262.4   # rated current (HV side, 220 kV) [A]
    V_rated_kV:    float = 220.0   # HV rated voltage [kV]

    # IEC 60076-7 thermal parameters
    dTheta_TO_R:   float = 40.0    # rated top-oil rise over ambient [°C]
    dTheta_HS_R:   float = 26.0    # rated hot-spot rise over top-oil [°C]
    tau_TO_min:    float = 210.0   # oil thermal time constant [min]
    tau_HS_min:    float = 7.0     # winding time constant [min]
    R_loss:        float = 6.0     # load/no-load loss ratio
    n_TO:          float = 0.8     # oil exponent (ONAN)
    n_HS:          float = 1.3     # winding exponent (ONAN)

    # GIC additional heating factor
    k_gic:         float = 0.50    # GIC heating factor [pu]

    # Cooling class
    cooling_class: str  = "ONAN"   # "ONAN" | "ONAF" | "ODAF"


# ---------------------------------------------------------------------------
# ThermalState
# ---------------------------------------------------------------------------

@dataclass
class ThermalState:
    """Transformer thermal state at one time step."""
    theta_ambient:   float   # ambient temperature [°C]
    dTheta_TO:       float   # top-oil rise over ambient [°C]
    dTheta_HS:       float   # hot-spot rise over top-oil [°C]
    theta_hotspot:   float   # absolute hot-spot temperature [°C]
    K_load:          float   # load factor [pu]
    I_GIC_A:         float   # GIC neutral current [A]
    K_eff:           float   # effective load factor including GIC
    alarm_level:     str     # "NORMAL" | "ELEVATED" | "CRITICAL" | "TRIP"
    ageing_factor:   float   # V (1.0 at rated hot-spot)
    active_alarm:    bool    # True if not NORMAL


# ---------------------------------------------------------------------------
# TransformerThermalModel
# ---------------------------------------------------------------------------

class TransformerThermalModel:
    """
    IEC 60076-7 hot-spot thermal model with GIC additional heating.

    Parameters
    ----------
    params : TransformerThermalParams
    theta_init : initial hot-spot temperature [°C]  (default: ambient + rated rises)
    """

    def __init__(self, params: TransformerThermalParams,
                 theta_ambient_init: float = 20.0) -> None:
        self._p   = params
        # Initial state: steady-state at K=1, no GIC
        self._dTO = params.dTheta_TO_R   # top-oil rise [°C]
        self._dHS = params.dTheta_HS_R   # hot-spot rise [°C]
        self._Ta  = theta_ambient_init

    # ------------------------------------------------------------------
    def step(self,
             dt_min:    float,
             K_load:    float,
             I_GIC_A:   float = 0.0,
             theta_ambient: Optional[float] = None) -> ThermalState:
        """
        Advance thermal state by dt_min minutes.

        Parameters
        ----------
        dt_min        : time step [minutes]
        K_load        : load factor = I / I_rated [pu]
        I_GIC_A       : GIC neutral current magnitude [A]
        theta_ambient : ambient temperature [°C]; None = use last value
        """
        p = self._p
        if theta_ambient is not None:
            self._Ta = theta_ambient
        Ta = self._Ta

        # Effective load factor with GIC heating
        K_GIC = (I_GIC_A / max(p.I_rated_A, 1.0)) * p.k_gic
        K_eff = math.sqrt(max(K_load, 0.0) ** 2 + K_GIC ** 2)

        # Steady-state targets
        loss_factor = (K_eff**2 + p.R_loss) / (1.0 + p.R_loss)
        dTO_ss = p.dTheta_TO_R * (loss_factor ** p.n_TO)
        dHS_ss = p.dTheta_HS_R * (K_eff ** (2.0 * p.n_HS))

        # Euler integration
        dt_ratio_TO = dt_min / max(p.tau_TO_min, 1e-6)
        dt_ratio_HS = dt_min / max(p.tau_HS_min, 1e-6)

        self._dTO += dt_ratio_TO * (dTO_ss - self._dTO)
        self._dHS += dt_ratio_HS * (dHS_ss - self._dHS)

        # Clamp (temperatures cannot go below ambient)
        self._dTO = max(self._dTO, 0.0)
        self._dHS = max(self._dHS, 0.0)

        theta_hs = Ta + self._dTO + self._dHS

        alarm, active = self._alarm_level(theta_hs)
        V_age = self._ageing_factor(theta_hs)

        return ThermalState(
            theta_ambient=round(Ta, 2),
            dTheta_TO=round(self._dTO, 3),
            dTheta_HS=round(self._dHS, 3),
            theta_hotspot=round(theta_hs, 3),
            K_load=round(K_load, 4),
            I_GIC_A=round(I_GIC_A, 3),
            K_eff=round(K_eff, 4),
            alarm_level=alarm,
            ageing_factor=round(V_age, 4),
            active_alarm=active,
        )

    # ------------------------------------------------------------------
    def reset(self, theta_ambient: float = 20.0, K_init: float = 1.0) -> None:
        """Reset to steady-state at given ambient and load factor."""
        p = self._p
        self._Ta  = theta_ambient
        loss_factor = (K_init**2 + p.R_loss) / (1.0 + p.R_loss)
        self._dTO = p.dTheta_TO_R * (loss_factor ** p.n_TO)
        self._dHS = p.dTheta_HS_R * (K_init ** (2.0 * p.n_HS))

    @property
    def theta_hotspot(self) -> float:
        return self._Ta + self._dTO + self._dHS

    # ------------------------------------------------------------------
    @staticmethod
    def _alarm_level(theta_hs: float) -> tuple:
        if theta_hs >= 140.0:
            return "TRIP", True
        elif theta_hs >= 120.0:
            return "CRITICAL", True
        elif theta_hs >= 98.0:
            return "ELEVATED", True
        return "NORMAL", False

    @staticmethod
    def _ageing_factor(theta_hs: float) -> float:
        """IEC 60076-7 Eq. 2: ageing acceleration factor V."""
        try:
            return math.exp(15000.0 / 383.0 - 15000.0 / (theta_hs + 273.0))
        except (OverflowError, ZeroDivisionError):
            return 1e6
