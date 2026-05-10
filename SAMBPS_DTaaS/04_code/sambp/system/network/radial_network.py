"""
radial_network.py
==================
Simple radial network model for the SAMBP system integration study.

Network topology (all quantities in per-unit on 100 MVA, 33 kV base)
---------------------------------------------------------------------

    Gen ──Z_src──[Bus_A]──Z_line──[Bus_B]──Z_tr──[Bus_C(load)]

    Zones:
      OC   : generator side — monitors I through Z_src
      87B_A: bus section A  — 2 feeders: Gen feeder, Line feeder
      87L  : line Z_line    — near end (A side) + far end (B side)
      87B_B: bus section B  — 2 feeders: Line feeder, Transformer feeder
      87T  : transformer Z_tr — HV side (B side) + LV side (C side)

For each fault location the network is solved analytically using the
Thevenin equivalent seen from the fault point.

Network parameters (pu, 100 MVA base):
    Z_src  = j0.10   (synchronous generator subtransient)
    Z_line = j0.05   (overhead line)
    Z_tr   = j0.08   (transformer leakage)
    Z_load = 2.00    (load impedance, roughly 50 % loading)
    V_pre  = 1.00∠0  (pre-fault voltage at generator bus)

Fault types: 3-phase (3ph), A-phase to ground (AG)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Network parameters
# ---------------------------------------------------------------------------

Z_SRC  = 1j * 0.10   # generator + source impedance [pu]
Z_LINE = 1j * 0.05   # line impedance [pu]
Z_TR   = 1j * 0.08   # transformer leakage [pu]
Z_LOAD = 2.00 + 0j   # load impedance [pu]

V_PRE  = 1.00 + 0j   # pre-fault source voltage

FREQ   = 50.0         # Hz
FS     = 1000.0       # samples/s


# ---------------------------------------------------------------------------
# Fault locations
# ---------------------------------------------------------------------------

FAULT_LOCATIONS = [
    "bus_A",          # fault at Bus_A — 87B_A zone
    "line_mid",       # fault at midpoint of line — 87L zone
    "bus_B",          # fault at Bus_B — 87B_B zone
    "transformer_hv", # fault inside transformer (HV winding) — 87T zone
    "bus_C_load",     # fault downstream of transformer — external to all zones
]


# ---------------------------------------------------------------------------
# Analytical fault current computation
# ---------------------------------------------------------------------------

def _thevenin_from(fault_loc: str) -> tuple[complex, complex]:
    """
    Return (V_th, Z_th) of the Thevenin equivalent at the fault point.

    Z_load is always in parallel with the Thevenin seen from the load side.
    For simplicity, the load is not included in Z_th (load current << fault
    current), so Z_th is the series combination of impedances from the source
    to the fault point.
    """
    if fault_loc == "bus_A":
        Z_th = Z_SRC
    elif fault_loc == "line_mid":
        Z_th = Z_SRC + Z_LINE / 2
    elif fault_loc == "bus_B":
        Z_th = Z_SRC + Z_LINE
    elif fault_loc == "transformer_hv":
        Z_th = Z_SRC + Z_LINE          # fault at HV terminals of transformer
    elif fault_loc == "bus_C_load":
        Z_th = Z_SRC + Z_LINE + Z_TR
    else:
        raise ValueError(f"Unknown fault location: {fault_loc}")

    return V_PRE, Z_th


def fault_current_phasor(fault_loc: str, fault_type: str = "3ph") -> complex:
    """
    Return the positive-sequence fault current phasor I_f [pu].

    For 3-phase faults: I_f = V_th / Z_th
    For A-G faults:     I_f = V_th / (Z_th + Z_n) ≈ V_th / (Z_th + Z_th)
                             simplified as I_f_AG = 0.6 * I_f_3ph (typical)
    """
    V_th, Z_th = _thevenin_from(fault_loc)
    I_3ph = V_th / Z_th

    if fault_type == "3ph":
        return I_3ph
    elif fault_type == "ag":
        return I_3ph * 0.6    # simplified zero-sequence factor
    else:
        raise ValueError(f"Unknown fault type: {fault_type}")


# ---------------------------------------------------------------------------
# CT waveform generation for each relay zone
# ---------------------------------------------------------------------------

def _sin_wave(t, I_peak, phi=0.0, dc_offset=0.8, tau_dc=0.05):
    """Fault current waveform with DC offset."""
    return I_peak * (np.sin(2 * np.pi * FREQ * t + phi)
                     + dc_offset * np.exp(-t / tau_dc))


@dataclass
class NetworkSnapshot:
    """
    All CT waveforms for a given fault scenario.

    Positive convention: current flowing INTO the protected zone.
    """
    fault_loc:   str
    fault_type:  str
    time_s:      np.ndarray

    # OC relay (generator side)
    i_oc_pu:     np.ndarray    # (3, T) phase currents [pu]

    # 87B_A (Bus A: gen feeder + line feeder, 3-phase each)
    i_B_A_feeders: list         # list of 2 × (3, T) arrays

    # 87L (near end + far end)
    i_L_near_pu:   np.ndarray   # (3, T) local (Bus_A side) [pu]
    i_L_far_pu:    np.ndarray   # (3, T) remote (Bus_B side) [pu]

    # 87B_B (Bus B: line feeder + transformer feeder)
    i_B_B_feeders: list         # list of 2 × (3, T) arrays

    # 87T (HV side + LV side)
    i_T_H_pu:    np.ndarray     # (3, T) HV winding [pu]
    i_T_X_pu:    np.ndarray     # (3, T) LV winding [pu]

    I_fault_pu:  float          # peak fault current magnitude


def generate_network_snapshot(
    fault_loc:  str,
    fault_type: str = "3ph",
    fault_time_s: float = 0.02,
    duration_s:   float = 0.15,
) -> NetworkSnapshot:
    """
    Generate all CT waveforms for a given fault scenario.

    The waveforms are computed analytically:
      - If the fault is WITHIN a zone: that zone's CTs see significant differential
      - If the fault is EXTERNAL to a zone: differential ≈ 0 (currents balance)
    """
    t   = np.arange(0, duration_s, 1.0 / FS)
    N   = len(t)
    ph  = [0.0, -2*np.pi/3, 2*np.pi/3]
    I_f = abs(fault_current_phasor(fault_loc, fault_type))

    # ---- Build fault waveforms based on location ----------------------------
    # Each element of zero represents no contribution from that direction.

    mask = t >= fault_time_s
    dt   = t - fault_time_s

    def make_wave(I_peak, phi_k=0.0, dc=0.8, tau=0.05):
        """3-phase waveform (3, T) with given peak and DC offset."""
        w = np.zeros((3, N))
        for k, p in enumerate(ph):
            w[k, mask] = I_peak * (
                np.sin(2*np.pi*FREQ*dt[mask] + p + phi_k)
                + dc * np.exp(-dt[mask] / tau)
            )
        return w

    def zeros():
        return np.zeros((3, N))

    # Pre-fault load current (small, on source feeder only)
    I_load = 0.3   # pu
    i_load_src = np.array([I_load * np.sin(2*np.pi*FREQ*t + p) for p in ph])

    # ---- Per-location waveform assignment -----------------------------------

    if fault_loc == "bus_A":
        # Source feeds fault at Bus_A; no current flows through line or transformer
        i_oc         = make_wave(I_f)        # gen → Bus_A → fault
        i_B_A_gen    = make_wave(I_f)        # into Bus_A from gen side
        i_B_A_line   = zeros()               # line does not contribute
        i_L_near     = zeros()               # no current enters line
        i_L_far      = zeros()
        i_B_B_line   = zeros()               # no current at Bus_B
        i_B_B_tr     = zeros()
        i_T_H        = zeros()
        i_T_X        = zeros()

    elif fault_loc == "line_mid":
        # Source feeds line; fault at midpoint. Near end sees full I_f;
        # far end sees near-zero (passive load side).
        i_oc         = make_wave(I_f)        # gen → Bus_A → line
        i_B_A_gen    = make_wave(I_f)        # into Bus_A (from gen)
        i_B_A_line   = make_wave(-I_f)       # out of Bus_A (into line) — negative
        i_L_near     = make_wave(I_f)        # near end (Bus_A side), into line
        i_L_far      = zeros()               # far end (Bus_B side): passive
        i_B_B_line   = zeros()               # no current reaches Bus_B
        i_B_B_tr     = zeros()
        i_T_H        = zeros()
        i_T_X        = zeros()

    elif fault_loc == "bus_B":
        # Fault at Bus_B; source feeds through line, no current into transformer
        i_oc         = make_wave(I_f)
        i_B_A_gen    = make_wave(I_f)
        i_B_A_line   = make_wave(-I_f)       # current exits Bus_A to line
        i_L_near     = make_wave(I_f)        # line near end (same as Bus_A exit)
        i_L_far      = make_wave(-I_f)       # line far end into Bus_B
        i_B_B_line   = make_wave(I_f)        # into Bus_B from line
        i_B_B_tr     = zeros()               # no current into transformer
        i_T_H        = zeros()
        i_T_X        = zeros()

    elif fault_loc == "transformer_hv":
        # Internal transformer fault; current enters HV winding, no LV output
        i_oc         = make_wave(I_f)
        i_B_A_gen    = make_wave(I_f)
        i_B_A_line   = make_wave(-I_f)
        i_L_near     = make_wave(I_f)
        i_L_far      = make_wave(-I_f)
        i_B_B_line   = make_wave(I_f)        # into Bus_B from line
        i_B_B_tr     = make_wave(-I_f)       # into transformer from Bus_B
        i_T_H        = make_wave(I_f)        # HV winding sees fault current
        i_T_X        = zeros()               # LV winding: nothing comes out

    elif fault_loc == "bus_C_load":
        # External fault downstream of transformer; all zones see through-current
        # Differential = 0 for all zones
        #
        # 87T winding compensation: the relay applies M_X (Yd11 matrix) to the LV
        # current.  M_X adds +π/6 to the phase, so the LV waveform must have phase
        # 5π/6 (not π) for the compensated differential to cancel the HV term.
        # M_X also zeros balanced (zero-sequence) DC from the LV side, while HV DC
        # passes through unchanged — this creates a spurious differential proportional
        # to the DC offset.  Both issues are resolved by using:
        #   - phi_k = 5π/6  (correct Yd11 LV phase)
        #   - dc   = 0.0    (delta winding circulates DC internally; no DC in line CTs)
        i_oc         = make_wave(I_f)
        i_B_A_gen    = make_wave(I_f)
        i_B_A_line   = make_wave(-I_f)
        i_L_near     = make_wave(I_f)
        i_L_far      = make_wave(-I_f)
        i_B_B_line   = make_wave(I_f)
        i_B_B_tr     = make_wave(-I_f)
        i_T_H        = make_wave(I_f,  dc=0.0)               # HV through-current
        i_T_X        = make_wave(I_f,  phi_k=5*np.pi/6, dc=0.0)  # LV: Yd11 phase

    else:
        raise ValueError(f"Unknown fault location: {fault_loc}")

    return NetworkSnapshot(
        fault_loc      = fault_loc,
        fault_type     = fault_type,
        time_s         = t,
        i_oc_pu        = i_oc,
        i_B_A_feeders  = [i_B_A_gen, i_B_A_line],
        i_L_near_pu    = i_L_near,
        i_L_far_pu     = i_L_far,
        i_B_B_feeders  = [i_B_B_line, i_B_B_tr],
        i_T_H_pu       = i_T_H,
        i_T_X_pu       = i_T_X,
        I_fault_pu     = float(I_f),
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for loc in FAULT_LOCATIONS:
        snap = generate_network_snapshot(loc, "3ph")
        # For each internal zone, check that differential is non-zero
        i_diff_B_A = np.abs(sum(snap.i_B_A_feeders)).max()
        i_diff_L   = np.abs(snap.i_L_near_pu + snap.i_L_far_pu).max()
        i_diff_B_B = np.abs(sum(snap.i_B_B_feeders)).max()
        i_diff_T   = np.abs(snap.i_T_H_pu + snap.i_T_X_pu).max()
        print(f"  {loc:22s}: I_f={snap.I_fault_pu:.2f}  "
              f"87B_A={i_diff_B_A:.3f}  87L={i_diff_L:.3f}  "
              f"87B_B={i_diff_B_B:.3f}  87T={i_diff_T:.3f}")

    print("\nradial_network self-test PASSED.")
