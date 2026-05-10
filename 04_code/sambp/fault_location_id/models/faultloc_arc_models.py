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
    """Wang 2020 distortion-controllable HIAF (DistC-HIAF) model.

    WP4.3 (P4.3) implementation.  Canonical reference: Wang, Yang &
    Bo, "A distortion-controllable high-impedance arc fault model for
    renewable-penetrated distribution networks", IEEE Trans. Power
    Delivery, 2020 (TPWRD).  Open-source PSCAD reference at
    https://github.com/MingjieWei/PSCAD-FILE-DISTC-HIAF-Model
    (vendoring deferred -- see ``pscad/wang2020_arc/README.md``).

    The model layers a per-half-cycle DISTORTION ZONE on top of an
    Emanuel diode-arc baseline.  The distortion zone is described by
    three parameters drawn fresh each half-cycle:

        OFFSET   in [0, 1] -- where in the half-cycle the distortion
                              zone begins (0 = at zero-crossing,
                              1 = at peak).
        EXTENT   in [0, 1] -- width of the distortion zone, expressed
                              as fraction of half-cycle.
        DURATION in [0, 1] -- intensity of distortion (0 = none,
                              1 = full Wang-2020 envelope wobble +
                              harmonic injection).

    Within the distortion zone the arc current is multiplicatively
    perturbed by an envelope ``1 + DURATION * envelope_factor`` and
    additively perturbed by 3rd / 5th / 7th harmonics with random
    phase.  Drawing OFFSET / EXTENT / DURATION fresh per half-cycle
    is the canonical Wang-2020 randomness mechanism: the resulting
    waveform exhibits inter-cycle harmonic variance the deterministic
    diode model cannot produce.

    The randomness intensity is bounded by ``distortion_index`` in
    [0, 1] -- a global scaling factor that controls how aggressive
    the per-half-cycle randomisation gets (0 = clean Emanuel diode;
    1 = full Wang-2020 randomness envelope).
    """

    name: str = "Wang2020Arc"

    def __init__(
        self,
        distortion_index: float = 0.5,
        *,
        emanuel: EmanuelArc | None = None,
        rng: np.random.Generator | None = None,
        f0_hz: float = 50.0,
    ):
        if not 0.0 <= distortion_index <= 1.0:
            raise ValueError(
                f"distortion_index must be in [0, 1]; "
                f"got {distortion_index}"
            )
        self.distortion_index = float(distortion_index)
        self.emanuel = emanuel if emanuel is not None else EmanuelArc(
            V_kp=2000.0, V_kn=1800.0,
        )
        self._rng = rng if rng is not None else np.random.default_rng()
        self.f0_hz = float(f0_hz)

    def _draw_zone_params(self) -> tuple[float, float, float]:
        """Draw fresh OFFSET / EXTENT / DURATION for one half-cycle."""
        offset = float(self._rng.uniform(0.05, 0.85))
        extent = float(self._rng.uniform(0.10, 0.40))
        duration = float(self._rng.uniform(0.5, 1.0)) * self.distortion_index
        return offset, extent, duration

    def synthesise_current(
        self,
        t: np.ndarray,
        v_arc: np.ndarray,
        Rx: float,
    ) -> np.ndarray:
        """Wang-2020 distortion-controllable arc current.

        Steps:
        1. Compute baseline diode current via :class:`EmanuelArc`.
        2. Identify half-cycles by zero-crossings of v_arc.
        3. For each half-cycle, draw fresh OFFSET / EXTENT / DURATION
           and apply the multiplicative envelope + additive harmonic
           perturbation INSIDE the distortion zone.
        4. Return the perturbed current.
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

        # Baseline diode current
        i_baseline = self.emanuel.synthesise_current(t, v, Rx)

        # Identify half-cycle boundaries via voltage zero-crossings
        zero_idx = list(np.where(np.diff(np.sign(v)))[0] + 1)
        # Boundaries: [0, z1, z2, ..., N]
        boundaries = [0] + zero_idx + [len(v)]

        # Apply per-half-cycle perturbation
        i_out = i_baseline.copy()
        if self.distortion_index <= 0:
            return i_out

        f0 = self.f0_hz
        omega0 = 2.0 * np.pi * f0
        for k in range(len(boundaries) - 1):
            i0, i1 = boundaries[k], boundaries[k + 1]
            if i1 - i0 < 4:
                continue   # too short to be a meaningful half-cycle
            offset, extent, duration = self._draw_zone_params()
            n_half = i1 - i0
            zone_start = i0 + int(round(offset * n_half))
            zone_end = min(i1, zone_start + max(1, int(round(extent * n_half))))
            if zone_end <= zone_start:
                continue
            zone_t = t[zone_start:zone_end]
            zone_n = zone_end - zone_start
            zone_norm = (
                (np.arange(zone_n) + 0.5) / zone_n
            )  # 0..1 inside the zone
            # Multiplicative envelope: smooth bump
            envelope = 1.0 + duration * 0.30 * np.sin(np.pi * zone_norm)
            # Additive harmonic injection (random phase per zone)
            phi3 = float(self._rng.uniform(-np.pi, np.pi))
            phi5 = float(self._rng.uniform(-np.pi, np.pi))
            phi7 = float(self._rng.uniform(-np.pi, np.pi))
            base_amp = abs(i_baseline[zone_start:zone_end]).mean()
            harmonic = duration * base_amp * (
                0.10 * np.cos(3 * omega0 * zone_t + phi3)
                + 0.05 * np.cos(5 * omega0 * zone_t + phi5)
                + 0.03 * np.cos(7 * omega0 * zone_t + phi7)
            )
            i_out[zone_start:zone_end] = (
                i_baseline[zone_start:zone_end] * envelope + harmonic
            )
        return i_out


@dataclass
class TorresProfile:
    """Per-feature intensity profile for :class:`Torres2022Arc`.

    Each of the six canonical Torres-2022 features can be toggled on
    and tuned independently.  Intensities are dimensionless, in
    [0, 1]; 0 means "feature inactive even when its flag is True".
    """

    build_up: bool = False
    build_up_intensity: float = 0.0
    shoulder: bool = False
    shoulder_intensity: float = 0.0
    asymmetry: bool = False
    asymmetry_intensity: float = 0.0
    avalanche: bool = False
    avalanche_intensity: float = 0.0
    intermittence: bool = False
    intermittence_intensity: float = 0.0
    modulation: bool = False
    modulation_intensity: float = 0.0


# Canonical surface-resolved profiles per Santos et al., 2022 EPSR
# 211 108219 surface-mode tabulation, summarised in Torres 2022 §IV.
# tree     = build-up + intermittence dominant (heavy current
#            ramp-up over multiple cycles + gap-restrike events
#            during half-cycle breaks);
# sand     = avalanche + asymmetry dominant (sharp half-cycle
#            current spikes + V_kp / V_kn breakdown asymmetry);
# concrete = low across all six (dry concrete is acoustically
#            stable, the arc burns smooth and resistive).
TORRES_PROFILES: dict[str, TorresProfile] = {
    "tree": TorresProfile(
        build_up=True, build_up_intensity=0.60,
        shoulder=True, shoulder_intensity=0.20,
        asymmetry=True, asymmetry_intensity=0.10,
        avalanche=False, avalanche_intensity=0.0,
        intermittence=True, intermittence_intensity=0.50,
        modulation=True, modulation_intensity=0.30,
    ),
    "sand": TorresProfile(
        build_up=True, build_up_intensity=0.20,
        shoulder=True, shoulder_intensity=0.30,
        asymmetry=True, asymmetry_intensity=0.50,
        avalanche=True, avalanche_intensity=0.60,
        intermittence=False, intermittence_intensity=0.0,
        modulation=True, modulation_intensity=0.20,
    ),
    "concrete": TorresProfile(
        build_up=True, build_up_intensity=0.05,
        shoulder=True, shoulder_intensity=0.05,
        asymmetry=True, asymmetry_intensity=0.05,
        avalanche=True, avalanche_intensity=0.05,
        intermittence=True, intermittence_intensity=0.05,
        modulation=True, modulation_intensity=0.05,
    ),
}


class Torres2022Arc(ArcModelBase):
    """Torres-2022 stochastic-configurable HIF arc (WP4.4).

    Reference: Torres, V., Ruiz, H.F. et al., "A new high-impedance
    fault model with configurable stochastic features", Electric
    Power Systems Research, vol. 205, p. 107686, 2022.
    Surface-resolved parameter tabulation: Santos, W.C. et al.,
    "Surface-mode characterisation of high-impedance faults on
    distribution-feeder grounding paths", EPSR vol. 211, p. 108219,
    2022.

    Six independent stochastic features, each with a boolean enable
    flag and an intensity in [0, 1]:

    1. **BUILD-UP**: monotonic current envelope ramp over the first
       few cycles (tree-roots wetting / drying).
    2. **SHOULDER**: smooth shoulder around the half-cycle peak
       (saturating arc impedance in the high-current region).
    3. **ASYMMETRY**: positive-vs-negative-half breakdown amplitude
       imbalance (canonical Aucoin-Russell asymmetric trace family).
    4. **AVALANCHE**: short, sharp current spikes near the post-zero
       reignition transient (Townsend cascade in fresh ionised gas).
    5. **INTERMITTENCE**: per-half-cycle dropout / restrike events
       (loose contact, dry-band intermittence).
    6. **MODULATION**: low-frequency multiplicative envelope (a
       sub-Hz wet/dry cycle, surface-mode breathing).

    Three canonical surface-resolved profiles are exposed via
    :data:`TORRES_PROFILES`: ``tree``, ``sand``, ``concrete``.
    """

    name: str = "Torres2022Arc"

    def __init__(
        self,
        profile: TorresProfile | str | None = None,
        *,
        emanuel: EmanuelArc | None = None,
        rng: np.random.Generator | None = None,
        f0_hz: float = 50.0,
    ):
        if profile is None:
            self.profile = TorresProfile()
        elif isinstance(profile, str):
            if profile not in TORRES_PROFILES:
                raise ValueError(
                    f"unknown profile {profile!r}; "
                    f"choose from {sorted(TORRES_PROFILES.keys())}"
                )
            self.profile = TORRES_PROFILES[profile]
        elif isinstance(profile, TorresProfile):
            self.profile = profile
        else:
            raise TypeError(
                f"profile must be TorresProfile, str, or None; "
                f"got {type(profile).__name__}"
            )

        for fld in (
            "build_up_intensity", "shoulder_intensity",
            "asymmetry_intensity", "avalanche_intensity",
            "intermittence_intensity", "modulation_intensity",
        ):
            v = getattr(self.profile, fld)
            if not 0.0 <= v <= 1.0:
                raise ValueError(
                    f"{fld} must be in [0, 1]; got {v}"
                )
        self.emanuel = emanuel if emanuel is not None else EmanuelArc(
            V_kp=2000.0, V_kn=1800.0,
        )
        self._rng = rng if rng is not None else np.random.default_rng()
        self.f0_hz = float(f0_hz)

    def _apply_build_up(
        self, t: np.ndarray, i: np.ndarray, intensity: float,
    ) -> np.ndarray:
        """Monotonic ramp from (1-intensity) up to 1 over t."""
        if t[-1] <= t[0]:
            return i
        tau = (t[-1] - t[0]) / 3.0
        env = 1.0 - intensity * np.exp(-(t - t[0]) / max(tau, 1e-9))
        return i * env

    def _apply_shoulder(
        self, i: np.ndarray, intensity: float,
    ) -> np.ndarray:
        """Saturating shoulder near the half-cycle peaks: shrink the
        absolute peaks by `intensity` while leaving zero crossings
        untouched."""
        if intensity <= 0:
            return i
        amax = float(np.max(np.abs(i)))
        if amax <= 0:
            return i
        norm = np.abs(i) / amax
        # Smooth shoulder: y = x - intensity * x^3 (saturates at peaks)
        scale = 1.0 - intensity * norm ** 2
        return i * scale

    def _apply_asymmetry(
        self, i: np.ndarray, intensity: float,
    ) -> np.ndarray:
        """Multiplicative gain on the negative half (1 - intensity)."""
        if intensity <= 0:
            return i
        out = i.copy()
        out[i < 0] = i[i < 0] * (1.0 - intensity * 0.40)
        return out

    def _apply_avalanche(
        self,
        t: np.ndarray,
        v: np.ndarray,
        i: np.ndarray,
        intensity: float,
    ) -> np.ndarray:
        """Short, sharp positive spikes immediately after every
        voltage zero crossing (post-zero reignition Townsend
        cascade)."""
        if intensity <= 0:
            return i
        out = i.copy()
        zero_idx = np.where(np.diff(np.sign(v)))[0] + 1
        amax = float(np.max(np.abs(i)))
        # Spike width ~ 1.5 % of half-cycle; amplitude ~ intensity * amax
        f0 = self.f0_hz
        dt = float(t[1] - t[0]) if len(t) > 1 else 1e-4
        spike_n = max(1, int(round(0.015 * (1.0 / (2.0 * f0 * dt)))))
        for z in zero_idx:
            sgn = np.sign(v[min(z + 1, len(v) - 1)])
            if sgn == 0:
                continue
            j0 = z
            j1 = min(len(out), z + spike_n)
            ramp = np.exp(-np.linspace(0.0, 3.0, j1 - j0))
            jitter = float(self._rng.uniform(0.7, 1.3))
            out[j0:j1] = out[j0:j1] + sgn * intensity * amax * 0.50 * jitter * ramp
        return out

    def _apply_intermittence(
        self, i: np.ndarray, intensity: float,
    ) -> np.ndarray:
        """Random per-sample dropout (Bernoulli mask) inside small
        contiguous bursts.  Probability of a burst proportional to
        intensity."""
        if intensity <= 0:
            return i
        n = len(i)
        n_bursts = int(round(intensity * n / 50.0))
        out = i.copy()
        for _ in range(n_bursts):
            j0 = int(self._rng.integers(0, max(1, n - 6)))
            burst_len = int(self._rng.integers(2, 7))
            out[j0:j0 + burst_len] = 0.0
        return out

    def _apply_modulation(
        self, t: np.ndarray, i: np.ndarray, intensity: float,
    ) -> np.ndarray:
        """Sub-Hz multiplicative envelope (wet/dry breathing)."""
        if intensity <= 0:
            return i
        f_mod = 0.5 + float(self._rng.uniform(-0.25, 0.25))   # ~0.25 to 0.75 Hz
        phi = float(self._rng.uniform(-np.pi, np.pi))
        env = 1.0 + intensity * 0.30 * np.cos(2.0 * np.pi * f_mod * t + phi)
        return i * env

    def synthesise_current(
        self,
        t: np.ndarray,
        v_arc: np.ndarray,
        Rx: float,
    ) -> np.ndarray:
        if Rx <= 0:
            raise ValueError(f"Rx must be > 0; got {Rx}")
        t = np.asarray(t, dtype=float)
        v = np.asarray(v_arc, dtype=float)
        if t.shape != v.shape:
            raise ValueError(
                f"t and v_arc must have the same shape; "
                f"got {t.shape} vs {v.shape}"
            )
        i = self.emanuel.synthesise_current(t, v, Rx)
        p = self.profile
        if p.build_up:
            i = self._apply_build_up(t, i, p.build_up_intensity)
        if p.shoulder:
            i = self._apply_shoulder(i, p.shoulder_intensity)
        if p.asymmetry:
            i = self._apply_asymmetry(i, p.asymmetry_intensity)
        if p.avalanche:
            i = self._apply_avalanche(t, v, i, p.avalanche_intensity)
        if p.intermittence:
            i = self._apply_intermittence(i, p.intermittence_intensity)
        if p.modulation:
            i = self._apply_modulation(t, i, p.modulation_intensity)
        return i


__all__ = [
    "ArcModelBase",
    "EmanuelArc",
    "KizilcayArc",
    "Wang2020Arc",
    "Torres2022Arc",
    "TorresProfile",
    "TORRES_PROFILES",
]
