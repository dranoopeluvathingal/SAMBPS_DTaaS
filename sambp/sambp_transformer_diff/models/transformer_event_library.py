"""
transformer_event_library.py
=============================
Synthetic waveform generators for all canonical 87T test events:

    1. Normal load (through current, no fault)
    2. Energisation inrush
    3. Overexcitation
    4. External fault + CT saturation
    5. Internal winding fault — phase-A turn-to-ground
    6. Internal winding fault — phase-A to phase-B
    7. Internal winding fault — three-phase

Each generator returns:
    {
      "time_s"    : (N,) array,
      "i_H_abc"   : (3, N) array  [A],
      "i_X_abc"   : (3, N) array  [A],
      "event_name": str,
      "fault_time": float or None,
    }

The waveforms are physically motivated parameterised models, NOT full EMTP
simulations.  They are calibrated to exhibit the key harmonic signatures that
the 87T relay must discriminate.

Transformer nameplate defaults
-------------------------------
    MVA  = 10 MVA
    HV   = 33 kV  (Y grounded)
    LV   = 11 kV  (delta, Yd11)
    CT_H = 200:1, CT_X = 600:1
"""

from __future__ import annotations

import numpy as np
from typing import Optional

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _sin3(t, freq, I_peak, phase=0.0):
    return I_peak * np.sin(2 * np.pi * freq * t + phase)


def _three_phase(t, freq, I_peak, phases=(0, -2*np.pi/3, 2*np.pi/3)):
    return np.array([_sin3(t, freq, I_peak, p) for p in phases])


def _rated_currents(MVA=10.0, kV_H=33.0, kV_X=11.0):
    I_H = (MVA * 1e6) / (np.sqrt(3) * kV_H * 1e3)
    I_X = (MVA * 1e6) / (np.sqrt(3) * kV_X * 1e3)
    return I_H, I_X


def _event(name, t, i_H, i_X, fault_time=None):
    return {
        "event_name": name,
        "time_s":     t,
        "i_H_abc":    i_H,
        "i_X_abc":    i_X,
        "fault_time": fault_time,
    }


# ---------------------------------------------------------------------------
# 1. Normal load
# ---------------------------------------------------------------------------

def event_normal_load(
    I_load_pu: float = 1.0,
    duration_s: float = 0.1,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    MVA: float = 10.0, kV_H: float = 33.0, kV_X: float = 11.0,
) -> dict:
    """
    Balanced load — HV lagging LV by 30° (Yd11 vector group).
    LV current has opposite sign convention (power flows in).
    """
    t = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    I_H, I_X = _rated_currents(MVA, kV_H, kV_X)

    i_H = _three_phase(t, freq_hz, I_load_pu * I_H,
                       phases=[0, -2*np.pi/3, 2*np.pi/3])
    # LV current phase for zero differential after Yd11 compensation:
    # (M_X @ i_X_pu)_a = sin(ωt + φ_a + π/6); for cancel with sin(ωt) → φ_a = 5π/6
    # LV convention: positive current = flowing INTO relay zone (leaving transformer)
    i_X = _three_phase(t, freq_hz, I_load_pu * I_X,
                       phases=[5*np.pi/6,
                                5*np.pi/6 - 2*np.pi/3,
                                5*np.pi/6 + 2*np.pi/3])

    return _event("normal_load", t, i_H, i_X)


# ---------------------------------------------------------------------------
# 2. Energisation inrush
# ---------------------------------------------------------------------------

def event_inrush(
    I_peak_pu: float = 8.0,
    I_2nd_ratio: float = 0.40,
    tau_dc_s: float = 0.10,
    duration_s: float = 0.3,
    fault_time_s: float = 0.02,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    MVA: float = 10.0, kV_H: float = 33.0, kV_X: float = 11.0,
) -> dict:
    """
    Transformer energisation: HV sees inrush; LV is open (no load).

    Inrush model (phase A):
        i_H_a = I_peak * [sin(ωt) + I_2nd * sin(2ωt) + DC*exp(-t/τ_dc)]
    Phases B and C: smaller offset, 120° apart.
    """
    t    = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    I_H, _ = _rated_currents(MVA, kV_H, kV_X)
    N    = len(t)

    i_H = np.zeros((3, N))
    i_X = np.zeros((3, N))   # LV open during energisation

    tau = fault_time_s
    for ph, (shift, dc_frac) in enumerate(
            zip([0.0, -2*np.pi/3, 2*np.pi/3], [1.0, 0.3, 0.2])):
        mask = t >= tau
        i_H[ph, mask] = I_peak_pu * I_H * (
            np.sin(2*np.pi*freq_hz*(t[mask] - tau) + shift)
            + I_2nd_ratio * np.sin(2 * 2*np.pi*freq_hz*(t[mask] - tau) + shift)
            + dc_frac * np.exp(-(t[mask] - tau) / tau_dc_s)
        )

    return _event("energisation_inrush", t, i_H, i_X, fault_time=fault_time_s)


# ---------------------------------------------------------------------------
# 3. Overexcitation
# ---------------------------------------------------------------------------

def event_overexcitation(
    I_fund_pu: float = 1.2,
    I_5th_ratio: float = 0.45,
    duration_s: float = 0.2,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    MVA: float = 10.0, kV_H: float = 33.0, kV_X: float = 11.0,
) -> dict:
    """
    V/Hz overexcitation: 5th harmonic content dominates magnetising current.
    The differential current contains fundamental + large 5th harmonic.
    """
    t    = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    I_H, I_X = _rated_currents(MVA, kV_H, kV_X)
    N    = len(t)

    i_H = np.zeros((3, N))
    i_X = np.zeros((3, N))

    for ph, shift in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
        # Load component (balanced through)
        i_H[ph] = I_fund_pu * I_H * np.sin(2*np.pi*freq_hz*t + shift)
        i_X[ph] = -I_fund_pu * I_X * np.sin(2*np.pi*freq_hz*t + shift - np.pi/6)
        # Overexcitation adds magnetising differential current on HV
        i_H[ph] += I_5th_ratio * I_fund_pu * I_H * np.sin(
            5 * 2*np.pi*freq_hz*t + shift)

    return _event("overexcitation", t, i_H, i_X)


# ---------------------------------------------------------------------------
# 4. External fault + CT saturation
# ---------------------------------------------------------------------------

def event_external_fault_ct_sat(
    I_fault_pu: float = 5.0,
    sat_ratio: float = 0.15,
    fault_time_s: float = 0.02,
    duration_s: float = 0.15,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    MVA: float = 10.0, kV_H: float = 33.0, kV_X: float = 11.0,
) -> dict:
    """
    Three-phase external fault downstream of transformer.
    LV CT saturates, reproducing a spurious differential current.

    CT saturation model:
        i_CT_out = i_true  when |i_true| <= I_sat_knee
        i_CT_out = I_sat_knee * sign(i_true) + (i_true - I_sat_knee*sign(i_true)) * sat_ratio
    i.e. soft saturation above knee.
    """
    t  = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    I_H, I_X = _rated_currents(MVA, kV_H, kV_X)
    N  = len(t)

    i_H = np.zeros((3, N))
    i_X = np.zeros((3, N))
    i_X_sat = np.zeros((3, N))

    # Ideal through fault
    for ph, shift in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
        mask = t >= fault_time_s
        i_H[ph, mask] = I_fault_pu * I_H * (
            np.sin(2*np.pi*freq_hz*(t[mask] - fault_time_s) + shift)
            + 0.8 * np.exp(-(t[mask] - fault_time_s) / 0.05)   # DC offset
        )
        i_X[ph, mask] = -I_fault_pu * I_X * (
            np.sin(2*np.pi*freq_hz*(t[mask] - fault_time_s) + shift - np.pi/6)
            + 0.8 * np.exp(-(t[mask] - fault_time_s) / 0.05)
        )

    # CT saturation on LV side
    I_knee = 1.2 * I_fault_pu * I_X   # saturation knee = 120% rated fault
    for ph in range(3):
        x = i_X[ph]
        above = np.abs(x) > I_knee
        i_X_sat[ph] = np.where(
            above,
            I_knee * np.sign(x) + (x - I_knee * np.sign(x)) * sat_ratio,
            x,
        )

    return _event("external_fault_ct_sat", t, i_H, i_X_sat, fault_time=fault_time_s)


# ---------------------------------------------------------------------------
# 5. Internal fault — turn-to-ground (phase A)
# ---------------------------------------------------------------------------

def event_internal_tg_fault(
    I_fault_pu: float = 3.0,
    alpha: float = 0.3,            # fraction of winding involved (0 < α ≤ 1)
    fault_time_s: float = 0.05,
    duration_s: float = 0.2,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    MVA: float = 10.0, kV_H: float = 33.0, kV_X: float = 11.0,
) -> dict:
    """
    Internal turn-to-ground fault in phase A of the HV winding.

    The fault injects additional current I_fault into the HV CT window
    (it is NOT seen by the LV CT), producing a differential current ≈ α * I_fault.
    """
    t  = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    I_H, I_X = _rated_currents(MVA, kV_H, kV_X)
    N  = len(t)

    i_H = np.zeros((3, N))
    i_X = np.zeros((3, N))

    # Pre-fault: 1.0 pu balanced load
    for ph, shift in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
        i_H[ph] = 1.0 * I_H * np.sin(2*np.pi*freq_hz*t + shift)
        i_X[ph] = -1.0 * I_X * np.sin(2*np.pi*freq_hz*t + shift - np.pi/6)

    # Fault injection on phase A only (HV side)
    mask = t >= fault_time_s
    i_H[0, mask] += alpha * I_fault_pu * I_H * (
        np.sin(2*np.pi*freq_hz*(t[mask] - fault_time_s))
        + 0.5 * np.exp(-(t[mask] - fault_time_s) / 0.02)
    )

    return _event("internal_tg_fault_phA", t, i_H, i_X, fault_time=fault_time_s)


# ---------------------------------------------------------------------------
# 6. Internal fault — phase-A to phase-B
# ---------------------------------------------------------------------------

def event_internal_ab_fault(
    I_fault_pu: float = 4.0,
    fault_time_s: float = 0.05,
    duration_s: float = 0.2,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    MVA: float = 10.0, kV_H: float = 33.0, kV_X: float = 11.0,
) -> dict:
    """
    Internal phase-A to phase-B fault.  Current circulates between phases
    — both HV CT phase-A and phase-B see additional current; LV is unaffected.
    """
    t  = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    I_H, I_X = _rated_currents(MVA, kV_H, kV_X)
    N  = len(t)

    i_H = np.zeros((3, N))
    i_X = np.zeros((3, N))

    for ph, shift in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
        i_H[ph] = 1.0 * I_H * np.sin(2*np.pi*freq_hz*t + shift)
        i_X[ph] = -1.0 * I_X * np.sin(2*np.pi*freq_hz*t + shift - np.pi/6)

    mask = t >= fault_time_s
    i_fault = I_fault_pu * I_H * np.sin(
        2*np.pi*freq_hz*(t[mask] - fault_time_s) - np.pi/6)   # between A and B
    i_H[0, mask] += i_fault
    i_H[1, mask] -= i_fault

    return _event("internal_ab_fault", t, i_H, i_X, fault_time=fault_time_s)


# ---------------------------------------------------------------------------
# 7. Internal three-phase fault
# ---------------------------------------------------------------------------

def event_internal_3ph_fault(
    I_fault_pu: float = 5.0,
    fault_time_s: float = 0.05,
    duration_s: float = 0.2,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    MVA: float = 10.0, kV_H: float = 33.0, kV_X: float = 11.0,
) -> dict:
    """
    Symmetric three-phase internal fault.  Full fault current appears in HV
    CTs; LV currents collapse to residual (modelled as zero for simplicity).
    """
    t  = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    I_H, I_X = _rated_currents(MVA, kV_H, kV_X)
    N  = len(t)

    i_H = np.zeros((3, N))
    i_X = np.zeros((3, N))

    for ph, shift in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
        i_H[ph] = 1.0 * I_H * np.sin(2*np.pi*freq_hz*t + shift)
        i_X[ph] = -1.0 * I_X * np.sin(2*np.pi*freq_hz*t + shift - np.pi/6)

    mask = t >= fault_time_s
    for ph, shift in enumerate([0.0, -2*np.pi/3, 2*np.pi/3]):
        i_H[ph, mask] += I_fault_pu * I_H * (
            np.sin(2*np.pi*freq_hz*(t[mask] - fault_time_s) + shift)
            + 0.6 * np.exp(-(t[mask] - fault_time_s) / 0.03)
        )
        # LV sees no additional current (fault inside transformer)
        i_X[ph, mask] = 0.0

    return _event("internal_3ph_fault", t, i_H, i_X, fault_time=fault_time_s)


# ---------------------------------------------------------------------------
# Convenience: all events as a list
# ---------------------------------------------------------------------------

ALL_EVENTS = [
    event_normal_load,
    event_inrush,
    event_overexcitation,
    event_external_fault_ct_sat,
    event_internal_tg_fault,
    event_internal_ab_fault,
    event_internal_3ph_fault,
]


def generate_all_events(**kwargs) -> list[dict]:
    """Return a list of event dicts from every generator with shared kwargs."""
    return [fn(**{k: v for k, v in kwargs.items()
                   if k in fn.__code__.co_varnames}) for fn in ALL_EVENTS]


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    events = [
        event_normal_load(),
        event_inrush(),
        event_overexcitation(),
        event_external_fault_ct_sat(),
        event_internal_tg_fault(),
        event_internal_ab_fault(),
        event_internal_3ph_fault(),
    ]
    for ev in events:
        print(f"  {ev['event_name']:35s} | "
              f"i_H peak = {np.abs(ev['i_H_abc']).max():.1f} A | "
              f"i_X peak = {np.abs(ev['i_X_abc']).max():.1f} A | "
              f"fault_time = {ev['fault_time']}")
    print("event_library self-test PASSED.")
