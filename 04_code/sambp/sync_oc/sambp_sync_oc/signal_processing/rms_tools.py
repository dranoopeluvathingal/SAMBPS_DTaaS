# =============================================================================
# sambp / sambp_sync_oc
# signal_processing/rms_tools.py
#
# RMS computation utilities shared across relay model and signal processing.
#
# Public API
# ----------
# sliding_rms(signal, samples_per_cycle)  → ndarray
# cycle_rms(signal, samples_per_cycle)    → ndarray (non-overlapping cycles)
# =============================================================================

import numpy as np


def sliding_rms(signal, samples_per_cycle):
    """
    Compute causal sliding RMS over a rectangular window.

    Window length = samples_per_cycle (one full cycle).
    First (samples_per_cycle − 1) samples use an expanding window
    to avoid NaN at signal start.

    Parameters
    ----------
    signal           : array-like — 1D input waveform
    samples_per_cycle: int        — number of samples per fundamental cycle

    Returns
    -------
    ndarray — RMS values, same length as signal
    """
    signal = np.asarray(signal, dtype=float)
    n      = len(signal)
    n_win  = max(1, int(samples_per_cycle))

    sq      = signal ** 2
    cumsum  = np.cumsum(sq)
    out     = np.zeros(n, dtype=float)

    for i in range(n):
        start     = max(0, i - n_win + 1)
        count     = i - start + 1
        sum_sq    = cumsum[i] - (cumsum[start - 1] if start > 0 else 0.0)
        out[i]    = np.sqrt(sum_sq / count)

    return out


def cycle_rms(signal, samples_per_cycle):
    """
    Compute non-overlapping per-cycle RMS values.

    Each output sample represents the RMS of one complete cycle block.
    Trailing samples that do not fill a complete cycle are discarded.

    Parameters
    ----------
    signal           : array-like — 1D input waveform
    samples_per_cycle: int        — number of samples per fundamental cycle

    Returns
    -------
    ndarray — RMS per cycle; length = floor(len(signal) / samples_per_cycle)
    """
    signal = np.asarray(signal, dtype=float)
    n_win  = max(1, int(samples_per_cycle))
    n_cyc  = len(signal) // n_win

    out = np.zeros(n_cyc, dtype=float)
    for k in range(n_cyc):
        block   = signal[k * n_win : (k + 1) * n_win]
        out[k]  = np.sqrt(np.mean(block ** 2))

    return out
