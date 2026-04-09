"""
line_diff_baseline.py
======================
Conventional two-end current-differential (87L) relay baseline.

Architecture
------------
    Local end  (L) : CT  → time-sync → I_L(t)  ─┐
                                                   ├─ I_diff = I_L + I_R
    Remote end (R) : CT  → channel  → I_R(t')  ─┘
                                                   I_rst  = (|I_L| + |I_R|) / 2

Current convention (Kirchhoff):  for a healthy line both currents flow INTO
the protected zone, so I_diff = I_L + I_R = I_charging ≈ 0 for no fault.
For an internal fault the fault current adds on both ends → I_diff ≠ 0.

Percentage-differential characteristic (same dual-slope form as 87T):
    Region 1: trip if  I_op > max(I_op_min, SLP1 * I_rst)
    Region 2: trip if  I_op > max(I_op_min,
                           SLP1 * I_rst_k + SLP2 * (I_rst − I_rst_k))

Charging current compensation
------------------------------
The steady-state capacitive charging current of the line is subtracted before
the differential is formed:
    I_diff_comp = I_L + I_R − I_C(t)
where I_C(t) = C_pu * dV/dt  (model: sinusoidal at power frequency).
A simplified model uses I_C = I_C_peak * sin(ωt + π/2).

Channel delay and alignment
-----------------------------
Remote current I_R arrives with latency τ_channel [samples].  The baseline
relay applies a fixed sample shift equal to the nominal delay.  Residual
misalignment is handled by the SAMBP zone model.

References
----------
    IEEE Std C37.243-2015 — Guide for Application of Digital Line Current
        Differential Relays Using Digital Communication
    Schweitzer et al. (2016) — Merging Unit and IEC 61850 Sampled Values
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Relay configuration
# ---------------------------------------------------------------------------

@dataclass
class LineDiffRelayConfig:
    """All user-settable parameters for the 87L relay."""

    # Line electrical parameters
    length_km: float        = 100.0       # protected line length [km]
    z_pu_per_km: float      = 0.003       # series impedance [pu/km] (approx)
    C_pu: float             = 5e-6        # shunt capacitance [pu]  (half-line model)
    I_C_peak_pu: float      = 0.02        # peak charging current [pu of I_rated]

    # CT / system base
    CT_ratio_L: float       = 400.0       # local end CT ratio
    CT_ratio_R: float       = 400.0       # remote end CT ratio
    I_rated_pu: float       = 1.0         # rated line current base [A] — set externally

    # Differential characteristic
    I_op_min_pu: float      = 0.20        # minimum operate threshold [pu]
    SLP1: float             = 0.30        # slope 1
    SLP2: float             = 0.60        # slope 2
    I_rst_k_pu: float       = 1.5         # breakpoint restraint current [pu]

    # Channel model
    channel_delay_samples: int  = 5       # nominal communication delay [samples]
    max_skew_samples: int       = 2       # max acceptable residual time skew

    # Operating mode
    use_charging_comp: bool  = True       # subtract I_C model
    freq_nom_hz: float       = 50.0       # power system frequency
    sample_rate_hz: float    = 1000.0     # waveform sample rate [Hz]


# ---------------------------------------------------------------------------
# Channel alignment
# ---------------------------------------------------------------------------

def align_remote_current(
    i_R_abc: np.ndarray,
    delay_samples: int,
) -> np.ndarray:
    """
    Shift remote current back by the nominal channel delay (circular roll).

    Positive delay_samples means remote data arrived late; we roll left
    so both ends are time-aligned.  Circular roll avoids the zero-padding
    edge artifact that would otherwise create a spurious differential at
    the end of the analysis window.
    """
    if delay_samples == 0:
        return i_R_abc.copy()
    return np.roll(i_R_abc, -delay_samples, axis=1)


# ---------------------------------------------------------------------------
# Charging current model
# ---------------------------------------------------------------------------

def charging_current_model(
    time_s: np.ndarray,
    cfg: LineDiffRelayConfig,
    phase_offset_rad: float = 0.0,
) -> np.ndarray:
    """
    Three-phase capacitive charging current model [pu].

    I_C(t) = I_C_peak * sin(ωt + π/2 + phase_offset)  per phase (120° apart).
    Returns (3, N) array.
    """
    omega = 2.0 * np.pi * cfg.freq_nom_hz
    I_C_peak = cfg.I_C_peak_pu

    i_C = np.array([
        I_C_peak * np.sin(omega * time_s + np.pi/2 + phase_offset_rad + ph * 2*np.pi/3)
        for ph in [0, -1, 1]
    ])
    return i_C


# ---------------------------------------------------------------------------
# Differential and restraint computation
# ---------------------------------------------------------------------------

def compute_diff_restraint(
    i_L_comp: np.ndarray,
    i_R_comp: np.ndarray,
    i_C: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute per-phase operate and restraint currents for 87L.

    Parameters
    ----------
    i_L_comp, i_R_comp : (3, N) compensated per-unit currents (after CT/align)
    i_C : (3, N) or None — charging current to subtract (after compensation)

    Returns
    -------
    I_op  : (3, N) operate current   |I_L + I_R − I_C|
    I_rst : (3, N) restraint current  (|I_L| + |I_R|) / 2
    """
    i_sum = i_L_comp + i_R_comp
    if i_C is not None:
        i_sum = i_sum - i_C

    I_op  = np.abs(i_sum)
    I_rst = (np.abs(i_L_comp) + np.abs(i_R_comp)) / 2.0
    return I_op, I_rst


# ---------------------------------------------------------------------------
# Trip characteristic evaluation
# ---------------------------------------------------------------------------

def evaluate_trip_characteristic(
    I_op: np.ndarray,
    I_rst: np.ndarray,
    cfg: LineDiffRelayConfig,
) -> np.ndarray:
    """
    Dual-slope percentage-differential trip surface (87L).

    Returns bool array — True where characteristic is penetrated.
    """
    I_op_min  = cfg.I_op_min_pu
    SLP1      = cfg.SLP1
    SLP2      = cfg.SLP2
    I_rst_k   = cfg.I_rst_k_pu

    thresh_r1 = np.maximum(I_op_min, SLP1 * I_rst)
    thresh_r2 = np.maximum(I_op_min,
                            SLP1 * I_rst_k + SLP2 * (I_rst - I_rst_k))
    threshold = np.where(I_rst <= I_rst_k, thresh_r1, thresh_r2)
    return I_op > threshold


# ---------------------------------------------------------------------------
# Per-unit compensation (single winding)
# ---------------------------------------------------------------------------

def compensate_end(
    i_abc: np.ndarray,
    ct_ratio: float,
    i_rated: float,
) -> np.ndarray:
    """Per-unitise primary current on rated line current."""
    return i_abc / i_rated


# ---------------------------------------------------------------------------
# Relay decision dataclass
# ---------------------------------------------------------------------------

@dataclass
class LineDiffDecision:
    trip: np.ndarray          # (3, N) bool
    trip_any: np.ndarray      # (N,)   bool
    I_op: np.ndarray          # (3, N) pu
    I_rst: np.ndarray         # (3, N) pu
    t_trip_s: Optional[float] = None


# ---------------------------------------------------------------------------
# Top-level relay runner
# ---------------------------------------------------------------------------

def run_87L_relay(
    time_s: np.ndarray,
    i_L_abc: np.ndarray,
    i_R_abc: np.ndarray,
    cfg: Optional[LineDiffRelayConfig] = None,
) -> LineDiffDecision:
    """
    Run the full 87L relay on three-phase waveforms from both line ends.

    Parameters
    ----------
    time_s   : (N,) time vector [s]
    i_L_abc  : (3, N) local end primary current [A] or [pu]
    i_R_abc  : (3, N) remote end primary current [A] or [pu]
    cfg      : LineDiffRelayConfig

    The inputs are treated as primary Amperes referred to the base I_rated_pu
    set in the config.  For synthetic studies where waveforms are already in
    per-unit, set cfg.I_rated_pu = 1.0.
    """
    if cfg is None:
        cfg = LineDiffRelayConfig()

    N  = len(time_s)
    I_rated = cfg.I_rated_pu

    # --- CT compensation -------------------------------------------------------
    i_L_comp = compensate_end(i_L_abc, cfg.CT_ratio_L, I_rated)
    i_R_comp = compensate_end(i_R_abc, cfg.CT_ratio_R, I_rated)

    # --- Channel alignment -----------------------------------------------------
    i_R_aligned = align_remote_current(i_R_comp, cfg.channel_delay_samples)

    # --- Charging current model ------------------------------------------------
    i_C = None
    if cfg.use_charging_comp:
        i_C = charging_current_model(time_s, cfg)

    # --- Differential and restraint --------------------------------------------
    I_op, I_rst = compute_diff_restraint(i_L_comp, i_R_aligned, i_C)

    # --- Trip characteristic ---------------------------------------------------
    trip = evaluate_trip_characteristic(I_op, I_rst, cfg)    # (3, N)
    trip_any = np.any(trip, axis=0)

    idx    = np.argmax(trip_any)
    t_trip = float(time_s[idx]) if trip_any[idx] else None

    return LineDiffDecision(
        trip     = trip,
        trip_any = trip_any,
        I_op     = I_op,
        I_rst    = I_rst,
        t_trip_s = t_trip,
    )


# ---------------------------------------------------------------------------
# Characteristic boundary helper
# ---------------------------------------------------------------------------

def trip_boundary(cfg: LineDiffRelayConfig,
                  I_rst_max: float = 5.0,
                  n_pts: int = 500) -> tuple[np.ndarray, np.ndarray]:
    I_rst = np.linspace(0.0, I_rst_max, n_pts)
    thresh = np.where(
        I_rst <= cfg.I_rst_k_pu,
        np.maximum(cfg.I_op_min_pu, cfg.SLP1 * I_rst),
        np.maximum(cfg.I_op_min_pu,
                   cfg.SLP1 * cfg.I_rst_k_pu
                   + cfg.SLP2 * (I_rst - cfg.I_rst_k_pu)),
    )
    return I_rst, thresh


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # channel_delay_samples=0: self-test waveforms are already time-aligned
    cfg  = LineDiffRelayConfig(channel_delay_samples=0)
    fs   = cfg.sample_rate_hz
    freq = cfg.freq_nom_hz
    t    = np.arange(0, 0.2, 1.0 / fs)
    N    = len(t)

    # ---- Scenario 1: healthy line — balanced through load -------------------
    # I_L flows in, I_R flows in from the remote side (magnitudes equal, 180° apart
    # after CT convention so they cancel in differential)
    i_L_hl = np.array([1.0 * np.sin(2*np.pi*freq*t + k*2*np.pi/3)
                        for k in [0, -1, 1]])
    i_R_hl = np.array([-1.0 * np.sin(2*np.pi*freq*t + k*2*np.pi/3)
                        for k in [0, -1, 1]])

    dec_hl = run_87L_relay(t, i_L_hl, i_R_hl, cfg)
    print(f"Healthy load   | trip={dec_hl.t_trip_s}  "
          f"I_op_max={dec_hl.I_op.max():.3f} pu")
    assert dec_hl.t_trip_s is None, "Healthy load must NOT trip"

    # ---- Scenario 2: internal fault —both ends see fault current ----------------
    # Convention: I_L + I_R = I_diff.  Healthy: I_R = -I_L (cancel).
    # Internal fault: both ends feed INTO the fault, so the fault contribution
    # at both ends has the SAME sign in the differential summation.
    # I_L increases (local infeed), I_R becomes less negative (remote infeed).
    i_L_int = i_L_hl.copy()
    i_R_int = i_R_hl.copy()
    fi = int(0.05 * fs)
    for ph, shift in enumerate([0, -2*np.pi/3, 2*np.pi/3]):
        i_L_int[ph, fi:] += 3.0 * np.sin(2*np.pi*freq*t[fi:] + shift)
        # Remote: fault reduces the cancellation (i_R becomes less negative)
        i_R_int[ph, fi:] += 2.5 * np.sin(2*np.pi*freq*t[fi:] + shift)

    dec_int = run_87L_relay(t, i_L_int, i_R_int, cfg)
    print(f"Internal fault | trip={dec_int.t_trip_s:.4f} s  "
          f"I_op_max={dec_int.I_op.max():.3f} pu")
    assert dec_int.t_trip_s is not None, "Internal fault MUST trip"

    # ---- Scenario 3: external fault — currents cancel perfectly ---------------
    i_L_ext = np.zeros((3, N))
    i_R_ext = np.zeros((3, N))
    for ph, shift in enumerate([0, -2*np.pi/3, 2*np.pi/3]):
        i_L_ext[ph] = 4.0 * np.sin(2*np.pi*freq*t + shift)
        i_R_ext[ph] = -4.0 * np.sin(2*np.pi*freq*t + shift)

    dec_ext = run_87L_relay(t, i_L_ext, i_R_ext, cfg)
    print(f"External fault | trip={dec_ext.t_trip_s}  "
          f"I_op_max={dec_ext.I_op.max():.4f} pu")
    assert dec_ext.t_trip_s is None, "External fault must NOT trip"

    print("line_diff_baseline self-test PASSED.")
