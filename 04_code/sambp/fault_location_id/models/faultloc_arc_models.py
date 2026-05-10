"""faultloc_arc_models.py
==========================
HIF arc-current stimulus models for the SAMBPS-DTaaS Fault-Location
Identification project.

WP4.2 (P4.2) implementation: ``ArcModelBase`` ABC + the
canonical ``EmanuelArc`` (anti-parallel diode pair, the WP1.1 /
manuscript baseline) + the ``KizilcayArc`` dynamic-conductance
model (Kizilcay 1991 ETEP; Darwish & Elkalashy 2005 IEEE TPWRD
20(2) 772-779).  Wang-2020 distortion-controllable arc + Torres-
2022 stochastic-configurable arc remain stubs pending later WPs.

Why two arc classes
-------------------

The IEEE Access manuscript and the WP1.1 PSCAD case both use the
EMANUEL anti-parallel-diode arc, which captures the asymmetric arc
ignition / extinction breakdown voltages but treats the conductance
as piecewise-constant in each half-cycle.  This produces a current
waveform with sharp transitions at v = +/- V_kp / V_kn breakpoints
and rich odd-harmonic content.

The KIZILCAY dynamic arc (canonical reference: Kizilcay 1991 ETEP
1(1); CAD: Darwish-Elkalashy 2005 IEEE TPWRD 20(2)) treats the arc
conductance g(t) as an internal state evolving via the ODE
::

    d(ln g)/dt = (1/tau) * ( (u(t) * i(t)) / P_0 - 1 ),

where ``tau`` is the arc time constant (default 1.3 ms per
Kizilcay) and ``P_0`` is the steady-state cooling power.  The
arc current is ``i(t) = u(t) * g(t)``.  Near current zero, g(t)
collapses (deionisation), producing a SOFT shoulder absent from the
diode model and reducing the harmonic content of i(t).

The cross-fit experiment in
``run_faultloc_phase4_arc_kizilcay.py`` compares optimiser estimates
when the data-generating arc is Kizilcay but the optimiser's
implicit forward model assumes the diode-shape harmonic content
of the WP1.1 baseline -- the resulting Delta-error quantifies the
arc-model-mismatch contribution to the location-estimate residual.

References
----------

* Kizilcay, M., "Dynamic arc model for arc burning and arcing
  faults", European Transactions on Electrical Power, 1(1):31-38,
  1991.
* Darwish, H.A. and Elkalashy, N.I., "Universal arc representation
  using EMTP", IEEE Trans. Power Delivery, 20(2):772-779, 2005.
  doi:10.1109/TPWRD.2004.838523.
* Aucoin, B.M. and Russell, B.D., "Detection of distribution high
  impedance faults using burst noise signals near 60 Hz", IEEE
  Trans. Power Delivery, 2(2):342-348, 1987.  Cited as the Emanuel
  anti-parallel-diode baseline.
* See ``docs/feeder_assumptions.md`` for the per-class default
  parameter rationale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

# =============================================================================
# Abstract base class
# =============================================================================

class ArcModelBase(ABC):
    """Abstract arc-fault current generator.

    Subclasses provide ``synthesise_current(t, v_arc, Rx)`` returning
    the arc-current waveform i(t) for a given line voltage v_arc(t)
    and HIF arc resistance R_x.  Two canonical concrete classes:

        EmanuelArc   anti-parallel diode pair (the WP1.1 baseline)
        KizilcayArc  dynamic-conductance ODE (this module)

    The simulator can swap classes by instantiating the chosen
    subclass and calling ``synthesise_current`` on the same v_arc(t).
    """

    name: str = "abstract"

    @abstractmethod
    def synthesise_current(
        self,
        t: np.ndarray,
        v_arc: np.ndarray,
        Rx: float,
    ) -> np.ndarray:
        """Return arc current i(t) for the given line voltage v_arc(t)."""
        ...


# =============================================================================
# EmanuelArc -- anti-parallel diode pair (WP1.1 baseline)
# =============================================================================

@dataclass
class EmanuelArc(ArcModelBase):
    """Anti-parallel-diode HIF arc (Aucoin-Russell 1987 trace family).

    Two breakdown voltages V_kp (positive half-cycle) and V_kn
    (negative half-cycle) gate two opposed diode branches.  When
    v_arc > V_kp the positive branch conducts via R_sp + R_x;
    when v_arc < -V_kn the negative branch conducts via R_sn + R_x;
    otherwise the arc is off (i ~ 0 with a tiny leakage R_off).

    Defaults match the WP0.5 provenance citation in the original
    stub docstring (V_kp = 50 V, V_kn = 45 V, R_sp = 5 ohm,
    R_sn = 6 ohm); these are the values the WP1.1 PSCAD case uses
    but they're not on the same MV scale as a real HIF -- they
    represent the secondary-side arc model for a downscaled
    laboratory test feeder.  For an 11 kV system the breakdown
    voltages should be scaled to a kV range; the cross-fit
    experiment in ``run_faultloc_phase4_arc_kizilcay.py`` uses the
    higher MV values via the constructor.
    """

    V_kp: float = 50.0
    V_kn: float = 45.0
    R_sp: float = 5.0
    R_sn: float = 6.0
    R_off: float = 1.0e6
    name: str = "EmanuelArc"

    def synthesise_current(
        self,
        t: np.ndarray,
        v_arc: np.ndarray,
        Rx: float,
    ) -> np.ndarray:
        """Anti-parallel diode arc current.

        For each sample, the active branch is determined by the
        v_arc polarity vs the breakdown threshold.  Series resistance
        is R_sp + R_x (forward) or R_sn + R_x (reverse).  Off-state
        leakage uses R_off in series with R_x.
        """
        if Rx <= 0:
            raise ValueError(f"Rx must be > 0; got {Rx}")
        v = np.asarray(v_arc, dtype=float)
        i = np.zeros_like(v)
        forward = v > self.V_kp
        reverse = v < -self.V_kn
        off_mask = ~(forward | reverse)
        i[forward] = (v[forward] - self.V_kp) / (self.R_sp + Rx)
        i[reverse] = (v[reverse] + self.V_kn) / (self.R_sn + Rx)
        i[off_mask] = v[off_mask] / (self.R_off + Rx)
        return i


# =============================================================================
# KizilcayArc -- dynamic-conductance ODE
# =============================================================================

@dataclass
class KizilcayArc(ArcModelBase):
    """Kizilcay 1991 dynamic-arc model (Darwish-Elkalashy 2005 CAD).

    State: arc conductance g(t).  Constitutive equation
    ``i(t) = u_arc(t) * g(t)`` with the conductance ODE
    ::

        d(ln g)/dt = (1/tau) * ( (u(t) * i(t)) / P_0 - 1 )
                   = (1/tau) * ( (u(t)^2 * g(t))  / P_0 - 1 ).

    Parameters
    ----------
    tau_s : float
        Arc time constant [s].  Default 1.3 ms (Kizilcay 1991 ETEP
        for HIF on sandy soil).
    L_arc_cm : float
        Arc length [cm].  Default 5 cm for a 11 kV / sandy-soil HIF.
    cooling_W_per_cm : float
        Steady-state cooling power per unit arc length [W/cm].
        Default 1000 W/cm = 1 kW/cm; combined with L_arc_cm gives
        P_0 = cooling_W_per_cm * L_arc_cm = 5 kW for the default.
    arc_voltage_gradient_V_per_cm : float
        Arc voltage gradient at steady state [V/cm].  Default
        12 V/cm (Darwish-Elkalashy 2005 Sect. III).  Used to derive
        the steady-state arc voltage U_ss = gradient * L_arc.
    g0 : float
        Initial arc conductance [S].  Default 1 / (10 * Rx) so the
        arc starts in a moderately conducting state and settles
        rapidly under the ODE dynamics.  Set explicitly for
        reproducible MC.
    """

    tau_s: float = 1.3e-3
    L_arc_cm: float = 5.0
    cooling_W_per_cm: float = 1000.0
    arc_voltage_gradient_V_per_cm: float = 12.0
    g0: float | None = None
    name: str = "KizilcayArc"

    @property
    def P0_W(self) -> float:
        """Steady-state cooling power [W] = cooling_W_per_cm * L_arc."""
        return self.cooling_W_per_cm * self.L_arc_cm

    @property
    def U_ss_V(self) -> float:
        """Steady-state arc voltage [V] = gradient * L_arc."""
        return self.arc_voltage_gradient_V_per_cm * self.L_arc_cm

    def synthesise_current(
        self,
        t: np.ndarray,
        v_arc: np.ndarray,
        Rx: float,
    ) -> np.ndarray:
        """Solve the Kizilcay ODE for g(t) and return i(t).

        The arc element + the series HIF resistance R_x sits in
        series across v_arc(t), giving the circuit equation
        ``i(t) = v_arc(t) / (1/g(t) + R_x)``.  Substituting into the
        Kizilcay ODE in ln(g):
        ::

            d(ln g)/dt = (1/tau) * (
                v_arc(t)**2 * g(t) / ((1 + R_x * g(t))**2 * P_0) - 1
            )

        which is stiff for u^2 / P_0 >> 1 (i.e., MV operation +
        small P_0).  Integrated via ``scipy.integrate.solve_ivp`` with
        the LSODA adaptive method that handles stiffness natively.
        ``g`` is clamped to ``[1e-12, 100/R_x]`` so deionised /
        super-conducting numerical excursions don't trip the solver.
        """
        if Rx <= 0:
            raise ValueError(f"Rx must be > 0; got {Rx}")
        t = np.asarray(t, dtype=float)
        v = np.asarray(v_arc, dtype=float)
        if t.shape != v.shape:
            raise ValueError(
                f"t and v_arc must have the same shape; "
                f"got {t.shape} vs {v.shape}"
            )
        n = t.size
        if n < 2:
            return np.zeros_like(v)
        from scipy.integrate import solve_ivp

        P0 = self.P0_W
        tau = self.tau_s
        ln_g_max = float(np.log(100.0 / max(Rx, 1.0e-9)))
        ln_g_min = float(np.log(1.0e-12))

        # Initial conductance: 1 / R_x so the arc starts in the
        # FULLY-CONDUCTING (hot-stable) basin.  The Kizilcay ODE has
        # two attractors -- a cold-stable (g -> 0, deionised) and a
        # hot-stable (g >= 1/R_x, fully ionised) -- and the chosen
        # basin is set by ``g0``.  Real HIF arcs reignite via
        # dielectric breakdown when the recovery voltage exceeds the
        # breakdown threshold (the Emanuel model captures this
        # explicitly via V_kp / V_kn); the Kizilcay model assumes
        # the arc is already established and tracks the conductance
        # dynamics from the ignited state.  Override via self.g0.
        if self.g0 is None:
            g0 = 1.0 / Rx
        else:
            g0 = float(self.g0)
        g0 = max(min(g0, np.exp(ln_g_max)), np.exp(ln_g_min))
        ln_g0 = float(np.log(g0))

        # Pre-build a linear interpolant for v(t) so the ODE RHS can
        # be evaluated at sub-sample times.
        def v_of_t(time_s: float) -> float:
            if time_s <= t[0]:
                return float(v[0])
            if time_s >= t[-1]:
                return float(v[-1])
            return float(np.interp(time_s, t, v))

        def rhs(time_s: float, ln_g_state: np.ndarray) -> np.ndarray:
            ln_g_v = float(ln_g_state[0])
            ln_g_v = min(max(ln_g_v, ln_g_min), ln_g_max)
            g = np.exp(ln_g_v)
            u = v_of_t(time_s)
            denom = (1.0 + Rx * g) ** 2 * P0
            return np.array([(1.0 / tau) * (u * u * g / denom - 1.0)])

        sol = solve_ivp(
            rhs,
            (float(t[0]), float(t[-1])),
            [ln_g0],
            t_eval=t,
            method="LSODA",
            rtol=1.0e-4,
            atol=1.0e-6,
            max_step=tau / 4.0,
        )
        if not sol.success:
            # On solver failure, fall back to the pure-resistive
            # approximation (no arc dynamics).  This shouldn't
            # happen at typical 11 kV / R_x in [100, 5000] but is
            # documented as a graceful degradation path.
            return v / (1.0 / max(g0, 1.0e-12) + Rx)
        ln_g_seq = np.clip(sol.y[0], ln_g_min, ln_g_max)
        g_seq = np.exp(ln_g_seq)
        return v / (1.0 / np.maximum(g_seq, 1.0e-12) + Rx)


# =============================================================================
# Wang-2020 + Torres-2022 (deferred -- WP4.3 / WP4.4)
# =============================================================================

class Wang2020Arc(ArcModelBase):
    """Wang 2020 distortion-controllable HIAF (deferred to WP4.3).

    A skeleton subclass that delegates to ``EmanuelArc`` for now;
    the canonical Wang-2020 implementation lands at WP4.3.
    """

    name: str = "Wang2020Arc"

    def __init__(self, distortion_index: float = 0.5):
        if not 0.0 <= distortion_index <= 1.0:
            raise ValueError(
                f"distortion_index must be in [0, 1]; "
                f"got {distortion_index}"
            )
        self.distortion_index = float(distortion_index)
        self._fallback = EmanuelArc()

    def synthesise_current(
        self,
        t: np.ndarray,
        v_arc: np.ndarray,
        Rx: float,
    ) -> np.ndarray:
        return self._fallback.synthesise_current(t, v_arc, Rx)


class Torres2022Arc(ArcModelBase):
    """Torres-2022 stochastic-configurable arc (deferred to WP4.4).

    A skeleton subclass that delegates to ``EmanuelArc`` for now;
    the canonical Torres-2022 implementation lands at WP4.4.
    """

    name: str = "Torres2022Arc"

    def __init__(self):
        self._fallback = EmanuelArc()

    def synthesise_current(
        self,
        t: np.ndarray,
        v_arc: np.ndarray,
        Rx: float,
    ) -> np.ndarray:
        return self._fallback.synthesise_current(t, v_arc, Rx)


__all__ = [
    "ArcModelBase",
    "EmanuelArc",
    "KizilcayArc",
    "Wang2020Arc",
    "Torres2022Arc",
]
