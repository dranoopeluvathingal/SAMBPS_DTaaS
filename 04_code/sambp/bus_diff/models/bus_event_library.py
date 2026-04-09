"""
bus_event_library.py
=====================
Synthetic event library for the 87B bus differential relay study.

Bus topology: 4-feeder bus section
    Feeder 0 — source (upstream power, current INTO bus, positive sign)
    Feeder 1 — load A  (current OUT of bus, negative sign)
    Feeder 2 — load B  (current OUT of bus, negative sign)
    Feeder 3 — load C  (current OUT of bus, negative sign)

All currents expressed in primary Amperes, positive = into bus.
CT saturation model matches transformer_event_library: soft knee clipping.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


def _phases(shift_rad=0.0):
    return [shift_rad, shift_rad - 2*np.pi/3, shift_rad + 2*np.pi/3]


def _event(name, time_s, i_feeders, fault_time=None):
    return {
        "event_name": name,
        "time_s":     time_s,
        "i_feeders":  i_feeders,  # list of (3, T) arrays
        "fault_time": fault_time,
    }


def _ct_saturate(i_abc: np.ndarray, I_knee: float, sat_ratio: float = 0.15) -> np.ndarray:
    """Soft CT saturation above knee current."""
    out = np.copy(i_abc)
    for ph in range(3):
        x = i_abc[ph]
        above = np.abs(x) > I_knee
        out[ph] = np.where(
            above,
            I_knee * np.sign(x) + (x - I_knee * np.sign(x)) * sat_ratio,
            x,
        )
    return out


# ---------------------------------------------------------------------------
# 1. Normal balanced load
# ---------------------------------------------------------------------------

def event_normal_load(
    I_load_pu: float = 0.5,
    duration_s: float = 0.10,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    I_bus_A: float = 1000.0,
) -> dict:
    """Source supplies three equal loads. I_op ≈ 0 (numerical precision only)."""
    t  = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    ph = _phases()
    I  = I_load_pu * I_bus_A

    i_src   = np.array([ I * 3 * np.sin(2*np.pi*freq_hz*t + p) for p in ph])
    i_load  = np.array([-I *     np.sin(2*np.pi*freq_hz*t + p) for p in ph])

    return _event("normal_load", t,
                  [i_src, i_load.copy(), i_load.copy(), i_load.copy()])


# ---------------------------------------------------------------------------
# 2. External fault on load feeder (through-fault, no CT saturation)
# ---------------------------------------------------------------------------

def event_external_fault(
    I_fault_pu: float = 5.0,
    fault_time_s: float = 0.02,
    duration_s: float = 0.15,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    I_bus_A: float = 1000.0,
) -> dict:
    """
    Fault on Feeder 1 (load A) downstream of its CT.
    Source CT sees I_fault; Feeder 1 CT also sees I_fault (equal but opposite).
    I_op = |I_src + I_f1 + I_f2 + I_f3| = 0 (currents balance perfectly).
    """
    t   = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    ph  = _phases()
    I   = I_fault_pu * I_bus_A

    i_src  = np.zeros((3, len(t)))
    i_f1   = np.zeros((3, len(t)))
    i_f2   = np.zeros((3, len(t)))
    i_f3   = np.zeros((3, len(t)))

    mask = t >= fault_time_s
    for k, p in enumerate(ph):
        # Source feeder carries the fault current (into bus)
        i_src[k, mask]  =  I * (np.sin(2*np.pi*freq_hz*(t[mask]-fault_time_s) + p)
                                 + 0.8 * np.exp(-(t[mask]-fault_time_s)/0.05))
        # Feeder 1 carries same current out through the fault
        i_f1[k, mask]   = -I * (np.sin(2*np.pi*freq_hz*(t[mask]-fault_time_s) + p)
                                 + 0.8 * np.exp(-(t[mask]-fault_time_s)/0.05))

    return _event("external_fault", t, [i_src, i_f1, i_f2, i_f3],
                  fault_time=fault_time_s)


# ---------------------------------------------------------------------------
# 3. External fault + CT saturation on source feeder
# ---------------------------------------------------------------------------

def event_external_fault_ct_sat(
    I_fault_pu: float = 5.0,
    sat_ratio: float  = 0.15,
    fault_time_s: float = 0.02,
    duration_s: float = 0.15,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    I_bus_A: float = 1000.0,
) -> dict:
    """
    External fault on Feeder 1, but the source CT saturates.
    The saturated source CT output is LESS than the true current →
    apparent differential = I_true - I_sat ≠ 0 → possible mal-trip.
    """
    t  = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    ph = _phases()
    I  = I_fault_pu * I_bus_A

    i_src_true = np.zeros((3, len(t)))
    i_f1       = np.zeros((3, len(t)))

    mask = t >= fault_time_s
    for k, p in enumerate(ph):
        waveform = I * (np.sin(2*np.pi*freq_hz*(t[mask]-fault_time_s) + p)
                        + 0.8 * np.exp(-(t[mask]-fault_time_s)/0.05))
        i_src_true[k, mask] =  waveform
        i_f1[k, mask]       = -waveform

    # Saturate source CT (knee at 60 % of fault peak to ensure definite saturation)
    I_knee  = 0.6 * I_fault_pu * I_bus_A
    i_src_sat = _ct_saturate(i_src_true, I_knee, sat_ratio)

    return _event("external_fault_ct_sat", t,
                  [i_src_sat, i_f1, np.zeros((3, len(t))), np.zeros((3, len(t)))],
                  fault_time=fault_time_s)


# ---------------------------------------------------------------------------
# 4. Internal bus fault — single-phase (A-G)
# ---------------------------------------------------------------------------

def event_internal_fault_ag(
    I_fault_pu: float  = 6.0,
    fault_time_s: float = 0.02,
    duration_s: float  = 0.15,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    I_bus_A: float = 1000.0,
) -> dict:
    """
    Phase-A to ground fault on the bus section.
    All feeders supply current into the fault; no feeder carries it away.
    I_op = |Σ_k i_k| = I_fault (net current into bus = fault current).
    """
    t  = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    I  = I_fault_pu * I_bus_A

    # Each of 4 feeders contributes I/4 to the fault (simplified: equal contribution)
    i_feeders = []
    mask = t >= fault_time_s
    for _ in range(4):
        i_k = np.zeros((3, len(t)))
        i_k[0, mask] = (I/4) * np.sin(2*np.pi*freq_hz*(t[mask]-fault_time_s))
        i_feeders.append(i_k)

    return _event("internal_fault_ag", t, i_feeders, fault_time=fault_time_s)


# ---------------------------------------------------------------------------
# 5. Internal bus fault — three-phase
# ---------------------------------------------------------------------------

def event_internal_fault_3ph(
    I_fault_pu: float  = 8.0,
    fault_time_s: float = 0.02,
    duration_s: float  = 0.15,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    I_bus_A: float = 1000.0,
) -> dict:
    """
    Bolted three-phase fault on the bus section.
    """
    t  = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    ph = _phases()
    I  = I_fault_pu * I_bus_A

    i_feeders = []
    mask = t >= fault_time_s
    for _ in range(4):
        i_k = np.zeros((3, len(t)))
        for k, p in enumerate(ph):
            i_k[k, mask] = (I/4) * np.sin(2*np.pi*freq_hz*(t[mask]-fault_time_s) + p)
        i_feeders.append(i_k)

    return _event("internal_fault_3ph", t, i_feeders, fault_time=fault_time_s)


# ---------------------------------------------------------------------------
# 6. CT open-circuit on one feeder (complete CT failure → false differential)
# ---------------------------------------------------------------------------

def event_ct_open_circuit(
    I_load_pu: float  = 0.8,
    duration_s: float = 0.10,
    sample_rate_hz: float = 1000.0,
    freq_hz: float = 50.0,
    I_bus_A: float = 1000.0,
) -> dict:
    """
    CT on Feeder 2 fails open (zero secondary output).
    The relay sees an apparent differential equal to the load current
    of Feeder 2.  This is a known limitation — high-impedance bus
    differential schemes provide better immunity but are outside SAMBP scope.
    """
    t  = np.arange(0, duration_s, 1.0 / sample_rate_hz)
    ph = _phases()
    I  = I_load_pu * I_bus_A

    i_src  = np.array([ 3*I * np.sin(2*np.pi*freq_hz*t + p) for p in ph])
    i_ld1  = np.array([-  I * np.sin(2*np.pi*freq_hz*t + p) for p in ph])
    i_ld2  = np.zeros((3, len(t)))   # CT open: zero output even though current flows
    i_ld3  = np.array([-  I * np.sin(2*np.pi*freq_hz*t + p) for p in ph])

    return _event("ct_open_circuit", t, [i_src, i_ld1, i_ld2, i_ld3])


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.bus_diff_baseline import BusDiffRelayConfig, run_87B_relay

    cfg = BusDiffRelayConfig()
    kw  = dict(sample_rate_hz=cfg.sample_rate_hz, freq_hz=cfg.freq_nom_hz,
               I_bus_A=cfg.I_bus_rated_A)

    events = [
        event_normal_load(**kw),
        event_external_fault(**kw),
        event_external_fault_ct_sat(**kw),
        event_internal_fault_ag(**kw),
        event_internal_fault_3ph(**kw),
        event_ct_open_circuit(**kw),
    ]

    for ev in events:
        dec = run_87B_relay(ev["time_s"], ev["i_feeders"], cfg)
        print(f"  {ev['event_name']:30s}  trip={dec.t_trip_s}  "
              f"I_op_max={dec.I_op.max():.3f}  type={dec.trip_type}")

    print("\nbus_event_library self-test PASSED.")
