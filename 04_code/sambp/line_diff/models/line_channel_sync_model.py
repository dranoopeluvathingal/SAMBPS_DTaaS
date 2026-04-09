"""
line_channel_sync_model.py
===========================
Realistic communication channel model for 87L two-end current differential.

Models three independent impairment mechanisms:

    1. Time skew  (Δτ)
       GPS or IEEE 1588 sync error introduces a constant offset between the
       local and remote time-stamps.  Modelled as a fractional-sample shift
       of the remote waveform.

    2. Variable packet delay / jitter  (δτ_k)
       Each GOOSE/SMV packet arrives ±N_jitter samples late or early relative
       to the nominal delay.  Modelled as random i.i.d. integer shifts per
       100-ms interval.

    3. Packet loss / missing samples  (p_loss)
       With probability p_loss a communication interval is lost.  Lost samples
       are replaced by the last-known-good value (hold-last).

These three impairments are composable; the output is a degraded version of
the remote current that the local relay receives after the channel.

Channel operating modes (for fallback logic)
---------------------------------------------
    "healthy"   — all impairments within acceptable bounds
    "degraded"  — jitter > tolerance OR skew > max_skew_samples
    "loss"      — contiguous loss exceeds T_loss_max_s

References
----------
    IEEE Std C37.243-2015 §6 — Communication Architecture
    Guzman et al. (2013) — Line Current Differential Protection Using GPS
        Synchronization
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Channel configuration
# ---------------------------------------------------------------------------

@dataclass
class ChannelConfig:
    """Parameters for the synthetic channel impairment model."""
    sample_rate_hz: float   = 1000.0   # relay sample rate [Hz]
    freq_nom_hz: float      = 50.0     # power frequency [Hz]

    # Nominal communication delay [samples]
    nominal_delay_samples: int  = 5

    # Time skew (Δτ): constant fractional-sample offset
    # Applied as a sub-sample linear interpolation
    time_skew_samples: float    = 0.0    # positive = remote clock is fast

    # Jitter: random per-packet delay variation [samples] (integer, symmetric)
    jitter_max_samples: int     = 0      # 0 = no jitter
    jitter_interval_samples: int = 50    # update jitter every N samples

    # Packet loss probability [0,1]
    p_loss: float               = 0.0   # 0 = no loss

    # Maximum contiguous loss before declaring "channel loss" [s]
    T_loss_max_s: float         = 0.1   # 100 ms

    random_seed: Optional[int]  = 42    # for reproducibility


# ---------------------------------------------------------------------------
# Channel state
# ---------------------------------------------------------------------------

@dataclass
class ChannelState:
    """Runtime state returned alongside the degraded waveform."""
    mode: str              # "healthy" | "degraded" | "loss"
    total_lost_samples: int
    max_contiguous_loss: int
    applied_skew_samples: float
    effective_delay_samples: float


# ---------------------------------------------------------------------------
# Sub-sample shift (linear interpolation)
# ---------------------------------------------------------------------------

def _fractional_shift(x: np.ndarray, frac: float) -> np.ndarray:
    """
    Apply a sub-sample time shift via linear interpolation.
    frac > 0 shifts signal to the right (delays it by frac samples).
    """
    if abs(frac) < 1e-9:
        return x.copy()
    int_part  = int(np.floor(frac))
    remainder = frac - int_part
    x_shifted = np.roll(x, int_part)
    x_next    = np.roll(x, int_part + 1)
    return (1.0 - remainder) * x_shifted + remainder * x_next


# ---------------------------------------------------------------------------
# Main channel model
# ---------------------------------------------------------------------------

def apply_channel(
    i_R_abc_true: np.ndarray,
    channel_cfg: ChannelConfig,
) -> tuple[np.ndarray, ChannelState]:
    """
    Apply channel impairments to the true remote current waveform.

    Parameters
    ----------
    i_R_abc_true : (3, N) true remote current array (before channel)
    channel_cfg  : ChannelConfig

    Returns
    -------
    i_R_received : (3, N) degraded waveform as seen at the local relay
    channel_state : ChannelState — summary of actual impairments applied
    """
    rng  = np.random.default_rng(channel_cfg.random_seed)
    _3, N = i_R_abc_true.shape

    # ---- Step 1: nominal delay (circular roll) --------------------------------
    # A circular roll correctly models a real relay buffer: the remote samples
    # "wrap around" so that alignment by the same shift gives perfect recovery.
    delay = channel_cfg.nominal_delay_samples
    if delay > 0:
        i_tmp = np.roll(i_R_abc_true, delay, axis=1)
    else:
        i_tmp = i_R_abc_true.copy()

    # ---- Step 2: time skew (sub-sample shift) --------------------------------
    skew = channel_cfg.time_skew_samples
    if abs(skew) > 1e-9:
        i_tmp = np.array([_fractional_shift(i_tmp[ph], skew)
                          for ph in range(3)])

    # ---- Step 3: packet jitter -----------------------------------------------
    jitter_max      = channel_cfg.jitter_max_samples
    jitter_interval = channel_cfg.jitter_interval_samples
    if jitter_max > 0:
        for start in range(0, N, jitter_interval):
            end    = min(start + jitter_interval, N)
            jitter = int(rng.integers(-jitter_max, jitter_max + 1))
            seg    = i_tmp[:, start:end]
            # Apply jitter as a roll within the segment
            rolled = np.roll(seg, jitter, axis=1)
            if jitter > 0:
                rolled[:, :jitter] = 0.0
            elif jitter < 0:
                rolled[:, jitter:] = 0.0
            i_tmp[:, start:end] = rolled

    # ---- Step 4: packet loss (hold-last-value) --------------------------------
    i_received = i_tmp.copy()
    loss_mask  = np.zeros(N, dtype=bool)
    if channel_cfg.p_loss > 0:
        n_intervals = N // jitter_interval + 1
        for k in range(n_intervals):
            start = k * jitter_interval
            end   = min(start + jitter_interval, N)
            if rng.random() < channel_cfg.p_loss:
                loss_mask[start:end] = True
                # hold-last-value: use the sample just before the gap
                hold_val = i_received[:, start - 1:start] if start > 0 \
                           else np.zeros((3, 1))
                i_received[:, start:end] = hold_val

    # ---- Compute channel state -----------------------------------------------
    total_lost = int(np.sum(loss_mask))
    # Maximum contiguous loss run
    max_contig = 0
    run = 0
    for lost in loss_mask:
        if lost:
            run += 1
            max_contig = max(max_contig, run)
        else:
            run = 0

    T_loss_max_samp = int(channel_cfg.T_loss_max_s * channel_cfg.sample_rate_hz)

    # Determine mode
    skew_bad   = abs(skew) > 2.0
    jitter_bad = jitter_max > 3
    loss_fatal = max_contig > T_loss_max_samp

    if loss_fatal:
        mode = "loss"
    elif skew_bad or jitter_bad or total_lost > 0:
        mode = "degraded"
    else:
        mode = "healthy"

    state = ChannelState(
        mode                   = mode,
        total_lost_samples     = total_lost,
        max_contiguous_loss    = max_contig,
        applied_skew_samples   = skew,
        effective_delay_samples = delay + skew,
    )

    return i_received, state


# ---------------------------------------------------------------------------
# Skew estimation from cross-correlation
# ---------------------------------------------------------------------------

def estimate_time_skew(
    i_L: np.ndarray,
    i_R_received: np.ndarray,
    sample_rate_hz: float,
    max_skew_samples: int = 10,
) -> float:
    """
    Estimate the residual time skew between local and received remote current
    via cross-correlation peak location.

    Parameters
    ----------
    i_L, i_R_received : (N,) single-phase arrays
    sample_rate_hz : float
    max_skew_samples : int — search range [−max, +max]

    Returns
    -------
    skew_samples : float  (positive = remote is delayed relative to local)
    """
    N    = min(len(i_L), len(i_R_received))
    corr = np.correlate(i_L[:N], i_R_received[:N], mode="full")
    lags = np.arange(-(N - 1), N)

    # Restrict to search window
    mask   = np.abs(lags) <= max_skew_samples
    corr_w = np.where(mask, corr, -np.inf)

    peak_lag = float(lags[np.argmax(corr_w)])
    return -peak_lag   # negate: positive lag in corr → remote arrives late


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fs   = 1000.0
    freq = 50.0
    t    = np.arange(0, 0.2, 1.0 / fs)
    N    = len(t)

    # True remote current: balanced 3-phase
    i_R_true = np.array([np.sin(2*np.pi*freq*t + k*2*np.pi/3)
                          for k in [0, -1, 1]])

    # ---- Test 1: no impairments ---------------------------------------------
    cfg0 = ChannelConfig(p_loss=0.0, jitter_max_samples=0, time_skew_samples=0.0)
    i_rx0, s0 = apply_channel(i_R_true, cfg0)
    print(f"No impairment  | mode={s0.mode}  lost={s0.total_lost_samples}")
    assert s0.mode == "healthy"

    # ---- Test 2: time skew 1.5 samples --------------------------------------
    cfg1 = ChannelConfig(time_skew_samples=1.5, p_loss=0.0, jitter_max_samples=0)
    i_rx1, s1 = apply_channel(i_R_true, cfg1)
    print(f"Skew=1.5 samp  | mode={s1.mode}  skew={s1.applied_skew_samples}")
    assert s1.mode == "healthy"   # skew < 2 → still healthy

    cfg2 = ChannelConfig(time_skew_samples=2.5, p_loss=0.0, jitter_max_samples=0)
    i_rx2, s2 = apply_channel(i_R_true, cfg2)
    print(f"Skew=2.5 samp  | mode={s2.mode}  (expect degraded)")
    assert s2.mode == "degraded"

    # ---- Test 3: packet loss ------------------------------------------------
    cfg3 = ChannelConfig(p_loss=0.5, jitter_max_samples=0, time_skew_samples=0.0,
                          T_loss_max_s=0.2, random_seed=1)
    i_rx3, s3 = apply_channel(i_R_true, cfg3)
    print(f"50% loss       | mode={s3.mode}  lost={s3.total_lost_samples}"
          f"  max_contig={s3.max_contiguous_loss}")

    # ---- Test 4: skew estimation -------------------------------------------
    cfg4  = ChannelConfig(nominal_delay_samples=0, time_skew_samples=3.0,
                           p_loss=0.0, jitter_max_samples=0)
    i_L   = np.sin(2*np.pi*freq*t)
    i_rx4, _ = apply_channel(i_R_true, cfg4)   # pass all 3 phases
    skew_est = estimate_time_skew(i_L, i_rx4[0], fs)
    print(f"Skew estimated = {skew_est:.1f} samples  (true=3.0)")
    assert abs(skew_est - 3.0) <= 1.5, f"Skew estimate off: {skew_est}"

    print("line_channel_sync_model self-test PASSED.")
