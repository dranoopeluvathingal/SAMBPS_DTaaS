"""
bus_diff_baseline.py
=====================
Conventional 87B percentage-differential bus protection relay.

Protection principle
--------------------
For a bus section with N feeders (currents I_1 … I_N measured into the bus):

    I_op  = |Σ_k I_k|          (differential / operate quantity)
    I_rst = (Σ_k |I_k|) / 2    (restraint quantity)

Trip criterion (dual-slope characteristic, same as 87T):
    I_op > max(I_op_min, SLP1 × I_rst)          when I_rst ≤ I_rst_k
    I_op > max(I_op_min, SLP1×I_rst_k + SLP2×(I_rst - I_rst_k))  otherwise
    OR
    I_op > I_op_hs   (unrestrained high-set)

Notes
-----
* All currents are referred to the HV reference and expressed in per-unit on the
  bus rated current I_bus = Σ_k (I_k_rated).
* No vector-group correction is needed (all feeders at the same bus voltage).
* No second/fifth harmonic blocking (bus faults are not preceded by inrush).
* CT mismatch is the primary source of spurious differential; it appears as a
  small fraction of the restraint current and is handled by the SAMBP Stage 2
  model-veto gate (see bus_confidence_gate.py).
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class BusDiffRelayConfig:
    n_feeders: int            = 4       # number of feeders (1 source + 3 loads)
    freq_nom_hz: float        = 50.0
    sample_rate_hz: float     = 1000.0

    # Percentage-differential characteristic
    I_op_min_pu: float        = 0.20    # minimum operate threshold [pu]
    SLP1: float               = 0.25    # slope 1 (low restraint region)
    SLP2: float               = 0.50    # slope 2 (high restraint, saturation region)
    I_rst_k_pu: float         = 1.0     # breakpoint between SLP1 and SLP2

    # Unrestrained high-set (severe close-in bus fault)
    I_op_hs_pu: float         = 8.0     # high-set trip threshold [pu bus rated]

    # CT ratios (one per feeder — nominally equal)
    CT_ratios: tuple          = (200, 200, 200, 200)   # all 200:1 by default

    # Bus rated current [A primary] — used for pu normalisation
    I_bus_rated_A: float      = 1000.0


# ---------------------------------------------------------------------------
# Per-phase DFT phasor (used for RMS and angle computation)
# ---------------------------------------------------------------------------

def _dft_phasor(x: np.ndarray, sample_rate_hz: float, freq_hz: float) -> complex:
    """Return the fundamental-frequency phasor of signal x (one cycle DFT)."""
    spc = int(round(sample_rate_hz / freq_hz))
    n   = min(spc, len(x))
    t   = np.arange(n) / sample_rate_hz
    e   = np.exp(-1j * 2 * np.pi * freq_hz * t)
    return (2.0 / n) * np.dot(x[-n:], e)


# ---------------------------------------------------------------------------
# Relay output dataclass
# ---------------------------------------------------------------------------

@dataclass
class BusRelayDecision:
    t_trip_s: Optional[float]     # None = no trip
    I_op: np.ndarray              # operate current trace [pu]
    I_rst: np.ndarray             # restraint current trace [pu]
    trip_type: str                # "differential" | "high_set" | None


# ---------------------------------------------------------------------------
# Trip boundary helper (for plotting)
# ---------------------------------------------------------------------------

def trip_boundary(cfg: BusDiffRelayConfig):
    I_rst = np.linspace(0.0, 6.0, 500)
    I_op  = np.where(
        I_rst <= cfg.I_rst_k_pu,
        np.maximum(cfg.I_op_min_pu, cfg.SLP1 * I_rst),
        np.maximum(cfg.I_op_min_pu, cfg.SLP1 * cfg.I_rst_k_pu
                   + cfg.SLP2 * (I_rst - cfg.I_rst_k_pu)),
    )
    return I_rst, I_op


# ---------------------------------------------------------------------------
# Operate / restraint calculation
# ---------------------------------------------------------------------------

def compute_operate_restraint(
    i_feeders_pu: np.ndarray,  # (N_feeders, N_samples), positive = into bus
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute sample-by-sample operate and restraint quantities.

    Parameters
    ----------
    i_feeders_pu : (N, T) array — feeder currents in per-unit

    Returns
    -------
    I_op  : (T,) array — |Σ_k i_k(t)|
    I_rst : (T,) array — (Σ_k |i_k(t)|) / 2
    """
    I_op  = np.abs(np.sum(i_feeders_pu, axis=0))
    I_rst = np.sum(np.abs(i_feeders_pu), axis=0) / 2.0
    return I_op, I_rst


# ---------------------------------------------------------------------------
# Main relay function
# ---------------------------------------------------------------------------

def run_87B_relay(
    time_s: np.ndarray,
    i_feeders_abc: list[np.ndarray],   # list of N arrays, each (3, T)
    cfg: BusDiffRelayConfig,
) -> BusRelayDecision:
    """
    Run the conventional 87B relay on a set of feeder currents.

    Parameters
    ----------
    time_s : (T,) time vector [s]
    i_feeders_abc : list of N (3, T) arrays — feeder phase currents [A primary]
    cfg : BusDiffRelayConfig

    Returns
    -------
    BusRelayDecision
    """
    N       = len(i_feeders_abc)
    T       = time_s.shape[0]
    I_ref   = cfg.I_bus_rated_A

    # Normalise each feeder to per-unit
    i_pu = np.array([
        i_feeders_abc[k] / I_ref
        for k in range(N)
    ])   # (N, 3, T)

    # Per-phase operate and restraint, then take the worst phase
    # i_pu[:, ph, :] → (N, T) for phase ph
    I_op_3ph  = np.array([
        np.abs(np.sum(i_pu[:, ph, :], axis=0))          # |Σ_k i_k_ph|
        for ph in range(3)
    ])   # (3, T)
    I_rst_3ph = np.array([
        np.sum(np.abs(i_pu[:, ph, :]), axis=0) / 2.0    # Σ_k |i_k_ph| / 2
        for ph in range(3)
    ])   # (3, T)

    # Worst-case phase determines the operating point
    I_op  = np.max(I_op_3ph,  axis=0)   # (T,)
    I_rst = np.max(I_rst_3ph, axis=0)   # (T,)

    # Per-sample trip criterion (phase A, same as 87T)
    threshold = np.where(
        I_rst <= cfg.I_rst_k_pu,
        np.maximum(cfg.I_op_min_pu, cfg.SLP1 * I_rst),
        np.maximum(cfg.I_op_min_pu, cfg.SLP1 * cfg.I_rst_k_pu
                   + cfg.SLP2 * (I_rst - cfg.I_rst_k_pu)),
    )

    diff_trip = I_op > threshold
    hs_trip   = I_op > cfg.I_op_hs_pu

    # Find first trip instant
    trip_type = None
    t_trip    = None

    hs_idx   = np.where(hs_trip)[0]
    diff_idx = np.where(diff_trip)[0]

    if len(hs_idx) > 0 and (len(diff_idx) == 0 or hs_idx[0] <= diff_idx[0]):
        t_trip    = float(time_s[hs_idx[0]])
        trip_type = "high_set"
    elif len(diff_idx) > 0:
        t_trip    = float(time_s[diff_idx[0]])
        trip_type = "differential"

    return BusRelayDecision(
        t_trip_s  = t_trip,
        I_op      = I_op,
        I_rst     = I_rst,
        trip_type = trip_type,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    cfg = BusDiffRelayConfig(n_feeders=4, I_bus_rated_A=1000.0)
    fs  = cfg.sample_rate_hz
    f   = cfg.freq_nom_hz
    t   = np.arange(0, 0.10, 1.0 / fs)
    N   = len(t)

    I_ref = cfg.I_bus_rated_A
    ph    = [0.0, -2*np.pi/3, 2*np.pi/3]

    # ----- Test 1: balanced load (no fault) → no trip -------------------------
    # Source supplies 0.5 pu to each of 3 loads.  Differential ≈ 0.
    i_src   = np.array([I_ref * 1.5 * np.sin(2*np.pi*f*t + p) for p in ph])  # into bus
    i_load1 = np.array([-I_ref * 0.5 * np.sin(2*np.pi*f*t + p) for p in ph]) # out
    i_load2 = np.array([-I_ref * 0.5 * np.sin(2*np.pi*f*t + p) for p in ph])
    i_load3 = np.array([-I_ref * 0.5 * np.sin(2*np.pi*f*t + p) for p in ph])

    dec = run_87B_relay(t, [i_src, i_load1, i_load2, i_load3], cfg)
    print(f"No-fault: trip={dec.t_trip_s}  I_op_max={dec.I_op.max():.3f}")
    assert dec.t_trip_s is None, "No-fault must not trip"

    # ----- Test 2: internal bus fault → must trip -----------------------------
    # Fault adds current from all sources but is NOT subtracted by any load CT
    I_fault = 8.0 * I_ref
    i_fault_inject = np.zeros((3, N))
    mask = t >= 0.02
    i_fault_inject[0, mask] = I_fault * np.sin(2*np.pi*f*(t[mask]-0.02))
    i_fault_inject[1, mask] = I_fault * np.sin(2*np.pi*f*(t[mask]-0.02) - 2*np.pi/3)
    i_fault_inject[2, mask] = I_fault * np.sin(2*np.pi*f*(t[mask]-0.02) + 2*np.pi/3)

    # Source and loads as before, but source now also feeds the fault
    i_src_f = i_src + i_fault_inject

    dec2 = run_87B_relay(t, [i_src_f, i_load1, i_load2, i_load3], cfg)
    print(f"Internal fault: trip={dec2.t_trip_s:.4f}s  type={dec2.trip_type}  "
          f"I_op_max={dec2.I_op.max():.2f}")
    assert dec2.t_trip_s is not None, "Internal bus fault must trip"

    print("bus_diff_baseline self-test PASSED.")
