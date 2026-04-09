# =============================================================================
# sambp / sambp_sync_oc
# signal_processing/preprocessing.py
#
# Extract and condition the event window for inverse estimation.
#
# Public API
# ----------
# extract_event_window(t, signals, t0, pre_s, post_s) → dict
# normalize_currents(ia, ib, ic, base_current)         → dict
# =============================================================================

import numpy as np


def extract_event_window(t, signals, t0, pre_s=0.01, post_s=0.08):
    """
    Extract a short window around the detected event time t0.

    Parameters
    ----------
    t       : ndarray — full time vector (s)
    signals : dict    — keyed signal arrays, e.g. {"ia": ..., "ib": ..., ...}
                        All arrays must have the same length as t.
    t0      : float   — event inception time (s)
    pre_s   : float   — window start before t0 (s), default 0.01
    post_s  : float   — window end after t0 (s), default 0.08

    Returns
    -------
    dict with keys matching `signals` plus:
        "t"      : windowed time vector (s)
        "t0"     : event time (s) — unchanged, for downstream reference
        "t_start": actual window start time (s)
        "t_end"  : actual window end time (s)
        "mask"   : boolean index array into original t
    """
    t    = np.asarray(t, dtype=float)
    mask = (t >= t0 - pre_s) & (t <= t0 + post_s)

    if not np.any(mask):
        raise ValueError(
            f"Event window [{t0 - pre_s:.4f}, {t0 + post_s:.4f}] s "
            f"falls outside time vector [{t[0]:.4f}, {t[-1]:.4f}] s."
        )

    result = {
        "t":       t[mask],
        "t0":      t0,
        "t_start": float(t[mask][0]),
        "t_end":   float(t[mask][-1]),
        "mask":    mask,
    }

    for key, arr in signals.items():
        arr = np.asarray(arr, dtype=float)
        if arr.shape[0] != len(t):
            raise ValueError(
                f"Signal '{key}' length {arr.shape[0]} does not match "
                f"time vector length {len(t)}."
            )
        result[key] = arr[mask]

    return result


def normalize_currents(ia, ib, ic, base_current=1.0):
    """
    Convert phase currents to per-unit (pu).

    Parameters
    ----------
    ia, ib, ic    : array-like — phase currents (any consistent unit)
    base_current  : float      — base current for pu conversion (same unit)
                                 Default 1.0 assumes input is already pu.

    Returns
    -------
    dict with keys: ia_pu, ib_pu, ic_pu  (ndarray)
    """
    ia = np.asarray(ia, dtype=float)
    ib = np.asarray(ib, dtype=float)
    ic = np.asarray(ic, dtype=float)

    if base_current <= 0.0:
        raise ValueError(f"base_current must be > 0, got {base_current}.")

    return {
        "ia_pu": ia / base_current,
        "ib_pu": ib / base_current,
        "ic_pu": ic / base_current,
    }
