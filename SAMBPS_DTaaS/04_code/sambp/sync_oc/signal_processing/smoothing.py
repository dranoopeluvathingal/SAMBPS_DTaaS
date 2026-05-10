# =============================================================================
# sambp / sambp_sync_oc
# signal_processing/smoothing.py
#
# Smooth noisy waveforms before inverse estimation.
#
# Supported methods:
#   "savgol"    — Savitzky-Golay filter (default, preserves peak shape)
#   "moving_avg"— uniform moving average (simple, use for quick checks)
#   "gaussian"  — Gaussian kernel smoothing
#   "spline"    — (stub) spline quasi-interpolation (Stage 2)
#
# Public API
# ----------
# smooth_signal(signal, method, **kwargs) → ndarray
# =============================================================================

import numpy as np
from scipy.signal import savgol_filter
from scipy.ndimage import uniform_filter1d, gaussian_filter1d


def smooth_signal(signal, method="savgol", **kwargs):
    """
    Smooth a 1D waveform.

    Parameters
    ----------
    signal : array-like — input waveform (1D)
    method : str        — smoothing method:
                          "savgol"     : Savitzky-Golay (default)
                          "moving_avg" : uniform moving average
                          "gaussian"   : Gaussian kernel
                          "spline"     : spline quasi-interpolation (stub)

    Keyword arguments per method
    ----------------------------
    savgol:
        window_length : int   — must be odd (default 11)
        polyorder     : int   — polynomial order (default 3)

    moving_avg:
        window_length : int   — number of samples (default 11)

    gaussian:
        sigma         : float — std dev in samples (default 3.0)

    Returns
    -------
    ndarray — smoothed signal, same length as input
    """
    signal = np.asarray(signal, dtype=float)

    if method == "savgol":
        wl  = int(kwargs.get("window_length", 11))
        po  = int(kwargs.get("polyorder", 3))
        # window_length must be odd and > polyorder
        if wl % 2 == 0:
            wl += 1
        wl  = max(wl, po + 2 if (po + 2) % 2 == 1 else po + 3)
        wl  = min(wl, len(signal) if len(signal) % 2 == 1 else len(signal) - 1)
        return savgol_filter(signal, window_length=wl, polyorder=po)

    elif method == "moving_avg":
        wl = int(kwargs.get("window_length", 11))
        return uniform_filter1d(signal, size=wl, mode="nearest")

    elif method == "gaussian":
        sigma = float(kwargs.get("sigma", 3.0))
        return gaussian_filter1d(signal, sigma=sigma, mode="nearest")

    elif method == "spline":
        raise NotImplementedError(
            "Spline quasi-interpolation is planned for Stage 2."
        )

    else:
        raise ValueError(
            f"Unknown method: '{method}'. "
            f"Expected 'savgol', 'moving_avg', 'gaussian', or 'spline'."
        )
