"""
mho_relay_model.py
==================
SAMBP TR-18/2026 -- Mho distance relay (21/21P) model.

Physical model
--------------
The Mho characteristic is a circle on the R-X impedance plane that passes
through the origin and is centred on the angle-of-maximum-torque (AMT) line:

    centre : Z_c = (Z_reach / 2) × e^{j·MTA}
    radius : R_mho = |Z_reach| / 2

A measured impedance Z_m lies inside the Mho circle if:

    |Z_m − Z_c| ≤ R_mho

Equivalently (without expensive modulus):

    Re[(Z_m − Z_reach) × conj(Z_m)] ≤ 0   (polarised Mho)

For a phase element (21P, measures positive-sequence impedance):
    Z_m = V_1 / I_1   [positive-sequence]

For a ground element (21G, measures loop impedance):
    Z_m = V_ph / (I_ph + k_0 × I_0)   [with zero-sequence compensation]

Zones
-----
    Zone 1 : Z_reach_1 = 0.80 × Z_line  (instantaneous, no timer)
    Zone 2 : Z_reach_2 = 1.20 × Z_line  (timer 0.3 s, coordinates with remote)
    Zone 3 : Z_reach_3 = 1.80 × Z_line  (timer 0.6 s, back-up)

Load blinder
------------
To prevent load encroachment, a resistive blinder is applied:

    |Re(Z_m)| > R_load_min = V_min² / S_max

    Default: R_load_min = 0.40 pu (for V_min=0.9 pu, S_max=2.0 pu)

Coordination with 87B/87L
--------------------------
Zone 1 reach (80% of line) keeps the relay from operating on close-in
bus faults that 87B handles.  Zone 2/3 back-up extends beyond the remote
bus, coordinated with 87L (which protects the line with no time delay).

Parameters
----------
    Z_line  : protected line positive-sequence impedance [pu]
    MTA     : maximum torque angle [deg], typically 75-85° for HV lines
    k_0     : zero-sequence compensation factor = (Z_0L - Z_1L) / (3 × Z_1L)
    R_blinder: load blinder minimum resistance [pu]
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class MhoRelayConfig:
    """Parameters for the three-zone Mho distance relay."""
    Z_line:     complex = 1j * 0.05    # protected line impedance [pu]
    MTA_deg:    float   = 80.0         # maximum torque angle [deg]
    k0_factor:  float   = 0.667        # zero-sequence compensation
    zone1_pct:  float   = 0.80         # Zone 1 reach factor
    zone2_pct:  float   = 1.20         # Zone 2 reach factor
    zone3_pct:  float   = 1.80         # Zone 3 reach factor
    t_zone2:    float   = 0.30         # Zone 2 timer [s]
    t_zone3:    float   = 0.60         # Zone 3 timer [s]
    R_blinder:  float   = 0.40         # load blinder [pu]

    @property
    def MTA(self) -> float:
        return np.radians(self.MTA_deg)

    @property
    def Z_reach1(self) -> complex:
        return self.zone1_pct * self.Z_line

    @property
    def Z_reach2(self) -> complex:
        return self.zone2_pct * self.Z_line

    @property
    def Z_reach3(self) -> complex:
        return self.zone3_pct * self.Z_line


# ---------------------------------------------------------------------------
# Mho operating equation
# ---------------------------------------------------------------------------

def _mho_criterion(Z_m: complex, Z_reach: complex) -> bool:
    """
    Polarised Mho criterion (memory-free, self-polarised):

        Re[(Z_m − Z_reach) × conj(Z_m)] ≤ 0

    Returns True if Z_m is inside (or on) the Mho circle.
    """
    return float(((Z_m - Z_reach) * np.conj(Z_m)).real) <= 0.0


def _load_blinder(Z_m: complex, R_blinder: float) -> bool:
    """
    Returns True if the measured impedance is OUTSIDE the load region
    (i.e. the load blinder has NOT blocked the element).

    Load region: Re(Z_m) > R_blinder (large resistive component → heavy load).
    Fault region: Re(Z_m) ≤ R_blinder (mostly reactive → transmission line fault).

    Block condition: Re(Z_m) > R_blinder.
    """
    return float(Z_m.real) <= R_blinder


# ---------------------------------------------------------------------------
# Impedance measurement
# ---------------------------------------------------------------------------

def measure_impedance_3ph(V_abc: np.ndarray, I_abc: np.ndarray) -> complex:
    """
    Positive-sequence impedance estimate from three-phase phasors.

    V_abc, I_abc : (3,) complex phasor arrays [pu]
    Returns Z_1 = V_1 / I_1 (positive-sequence)
    """
    a  = np.exp(1j * 2 * np.pi / 3)
    a2 = a * a
    V1 = (V_abc[0] + a * V_abc[1] + a2 * V_abc[2]) / 3.0
    I1 = (I_abc[0] + a * I_abc[1] + a2 * I_abc[2]) / 3.0
    if abs(I1) < 1e-9:
        return complex(1e9, 1e9)
    return V1 / I1


def measure_impedance_ag(
    V_a: complex, I_a: complex, I0: complex, k0: float
) -> complex:
    """
    Phase-A-to-ground loop impedance (21G, ag element):

        Z_ag = V_a / (I_a + k0 × 3 × I0)

    where I0 is the zero-sequence current.
    """
    denom = I_a + k0 * 3.0 * I0
    if abs(denom) < 1e-9:
        return complex(1e9, 1e9)
    return V_a / denom


# ---------------------------------------------------------------------------
# Zone decision
# ---------------------------------------------------------------------------

@dataclass
class MhoZoneState:
    """State of all three Mho zones."""
    zone1_pickup:  bool  = False
    zone2_pickup:  bool  = False
    zone3_pickup:  bool  = False
    zone2_timer:   float = 0.0      # accumulated time [s]
    zone3_timer:   float = 0.0
    load_blocked:  bool  = False
    Z_measured:    complex = 0j


@dataclass
class MhoDecision:
    """Output of one Mho relay evaluation cycle."""
    trip:        bool
    zone:        int     # 1, 2, 3, or 0 (no trip)
    Z_measured:  complex
    zone1_in:    bool
    zone2_in:    bool
    zone3_in:    bool
    load_block:  bool
    reason:      str


def evaluate_mho_zone(
    Z_m: complex,
    cfg: MhoRelayConfig,
    state: Optional[MhoZoneState] = None,
    dt_s: float = 0.02,
) -> tuple[MhoDecision, MhoZoneState]:
    """
    Evaluate one Mho relay cycle.

    Parameters
    ----------
    Z_m    : measured impedance [pu]
    cfg    : relay configuration
    state  : previous state (for Zone 2/3 timers)
    dt_s   : time step for timer integration [s]

    Returns
    -------
    (decision, new_state)
    """
    if state is None:
        state = MhoZoneState()

    # Load blinder: block if in load region
    not_load = _load_blinder(Z_m, cfg.R_blinder)
    state.load_blocked = not not_load

    z1 = _mho_criterion(Z_m, cfg.Z_reach1) and not_load
    z2 = _mho_criterion(Z_m, cfg.Z_reach2) and not_load
    z3 = _mho_criterion(Z_m, cfg.Z_reach3) and not_load

    state.zone1_pickup = z1
    state.zone2_pickup = z2
    state.zone3_pickup = z3
    state.Z_measured   = Z_m

    # Zone 1 — instantaneous
    if z1:
        return MhoDecision(
            trip=True, zone=1, Z_measured=Z_m,
            zone1_in=z1, zone2_in=z2, zone3_in=z3,
            load_block=not not_load,
            reason=f"Zone 1 trip: |Z_m|={abs(Z_m):.3f} inside Z_reach1={abs(cfg.Z_reach1):.3f}",
        ), state

    # Zone 2 — timed
    if z2:
        state.zone2_timer += dt_s
    else:
        state.zone2_timer = 0.0

    if state.zone2_timer >= cfg.t_zone2:
        return MhoDecision(
            trip=True, zone=2, Z_measured=Z_m,
            zone1_in=z1, zone2_in=z2, zone3_in=z3,
            load_block=not not_load,
            reason=(f"Zone 2 trip (t={state.zone2_timer:.2f}s ≥ {cfg.t_zone2:.2f}s): "
                    f"|Z_m|={abs(Z_m):.3f}"),
        ), state

    # Zone 3 — timed
    if z3:
        state.zone3_timer += dt_s
    else:
        state.zone3_timer = 0.0

    if state.zone3_timer >= cfg.t_zone3:
        return MhoDecision(
            trip=True, zone=3, Z_measured=Z_m,
            zone1_in=z1, zone2_in=z2, zone3_in=z3,
            load_block=not not_load,
            reason=(f"Zone 3 trip (t={state.zone3_timer:.2f}s ≥ {cfg.t_zone3:.2f}s): "
                    f"|Z_m|={abs(Z_m):.3f}"),
        ), state

    # No trip
    return MhoDecision(
        trip=False, zone=0, Z_measured=Z_m,
        zone1_in=z1, zone2_in=z2, zone3_in=z3,
        load_block=not not_load,
        reason="No trip",
    ), state


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = MhoRelayConfig(Z_line=1j*0.05, MTA_deg=80.0)

    # ---- Zone 1 internal fault (Z_m = 0.5 × Z_line = j0.025) ---------------
    Z_int1 = 0.5 * cfg.Z_line   # half-line fault → inside Zone 1
    dec, st = evaluate_mho_zone(Z_int1, cfg)
    print(f"Zone1 fault: trip={dec.trip}  zone={dec.zone}  reason={dec.reason}")
    assert dec.trip and dec.zone == 1

    # ---- Zone 1 boundary (Z_m = 0.80 × Z_line) → should trip ---------------
    Z_b1 = cfg.Z_reach1
    dec, st = evaluate_mho_zone(Z_b1, cfg)
    print(f"Zone1 boundary: trip={dec.trip}  zone={dec.zone}")
    assert dec.trip and dec.zone == 1

    # ---- Outside Zone 1 (Z_m = 0.90 × Z_line) → no Zone1 trip --------------
    Z_out1 = 0.90 * cfg.Z_line
    dec, st = evaluate_mho_zone(Z_out1, cfg)
    print(f"Z=0.90×Zline: zone1_in={dec.zone1_in}  zone2_in={dec.zone2_in}")
    assert not dec.zone1_in and dec.zone2_in

    # ---- Zone 2 timed trip (Z_m between Z_reach1 and Z_reach2) -------------
    Z_z2 = 1.10 * cfg.Z_line
    st2 = MhoZoneState()
    dt = 0.02
    for _ in range(int(0.35 / dt)):
        dec2, st2 = evaluate_mho_zone(Z_z2, cfg, st2, dt)
    print(f"Zone2 (timed): trip={dec2.trip}  zone={dec2.zone}  t={st2.zone2_timer:.2f}s")
    assert dec2.trip and dec2.zone == 2

    # ---- Load blinder blocks trip ------------------------------------------
    Z_load = 0.6 + 0.1j   # resistive: |Re| = 0.6 > R_blinder=0.40 → NOT blocked
    dec_load, _ = evaluate_mho_zone(Z_load, cfg)
    # This is outside the Mho circle (predominantly resistive) anyway:
    print(f"Load (R=0.6): zone1_in={dec_load.zone1_in}  load_block={dec_load.load_block}")

    Z_marginal = 0.50 + 1j * 0.01  # in load region (R=0.50 > R_blinder=0.40)
    dec_m, _ = evaluate_mho_zone(Z_marginal, cfg)
    print(f"Load region (R=0.50): load_block={dec_m.load_block}  trip={dec_m.trip}")
    assert dec_m.load_block and not dec_m.trip

    print("\nmho_relay_model self-test PASSED.")
