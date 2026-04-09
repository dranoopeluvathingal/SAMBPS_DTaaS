# =============================================================================
# sambp / sambp_sync_oc
# signal_processing/event_detection.py
#
# Detect fault/event inception time from current waveforms.
#
# Supported methods (Stage 1: rms_jump only):
#   "rms_jump"    — detects step-change in sliding RMS magnitude
#   "derivative"  — (stub) derivative threshold crossing
#   "residual"    — (stub) residual energy detection
#   "sequence"    — (stub) negative/zero sequence appearance
#
# Public API
# ----------
# detect_event_time(t, ia, ib, ic, method, threshold) → float or None
# =============================================================================

import numpy as np
from signal_processing.rms_tools import sliding_rms


# ---------------------------------------------------------------------------
# Internal: RMS jump detection
# ---------------------------------------------------------------------------

def _detect_rms_jump(t, ia, ib, ic, threshold, frequency_hz=50.0):
    """
    Detect event by finding the first sample where the sliding RMS of any
    phase increases by more than `threshold` (pu) within one cycle.

    Algorithm
    ---------
    1. Compute one-cycle sliding RMS for each phase.
    2. Compute the sample-to-sample RMS increment over one cycle lag.
    3. Find first index where increment ≥ threshold.
    4. Return corresponding time value.

    Parameters
    ----------
    t         : ndarray — time vector (s)
    ia,ib,ic  : ndarray — phase currents (pu)
    threshold : float   — RMS jump magnitude to declare event (pu)
    frequency_hz : float

    Returns
    -------
    float — estimated event time (s), or None if not detected
    """
    dt    = t[1] - t[0]
    n_cyc = max(1, int(round(1.0 / (frequency_hz * dt))))

    rms_a = sliding_rms(ia, n_cyc)
    rms_b = sliding_rms(ib, n_cyc)
    rms_c = sliding_rms(ic, n_cyc)

    rms_max = np.maximum(np.maximum(rms_a, rms_b), rms_c)

    # RMS jump = current RMS minus RMS one cycle ago
    jump = np.zeros_like(rms_max)
    jump[n_cyc:] = rms_max[n_cyc:] - rms_max[:-n_cyc]

    idx = np.where(jump >= threshold)[0]
    if len(idx) == 0:
        return None

    return float(t[idx[0]])


# ---------------------------------------------------------------------------
# Stubs for future methods
# ---------------------------------------------------------------------------

def _detect_derivative(t, ia, ib, ic, threshold):
    """(Stub) Detect event via di/dt threshold crossing."""
    raise NotImplementedError("derivative method not yet implemented.")


def _detect_residual(t, ia, ib, ic, threshold):
    """(Stub) Detect event via residual energy burst."""
    raise NotImplementedError("residual method not yet implemented.")


def _detect_sequence(t, ia, ib, ic, threshold):
    """(Stub) Detect event via negative/zero sequence appearance."""
    raise NotImplementedError("sequence method not yet implemented.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_event_time(
    t,
    ia,
    ib,
    ic,
    method="rms_jump",
    threshold=0.2,
    frequency_hz=50.0,
):
    """
    Estimate event (fault) inception time t0 from three-phase currents.

    Parameters
    ----------
    t            : ndarray — time vector (s)
    ia, ib, ic   : ndarray — phase currents (pu)
    method       : str     — detection method: "rms_jump" | "derivative" |
                             "residual" | "sequence"
    threshold    : float   — detection sensitivity (pu RMS jump for rms_jump)
    frequency_hz : float   — system frequency (Hz)

    Returns
    -------
    float — estimated t0 (s), or None if no event detected
    """
    t  = np.asarray(t,  dtype=float)
    ia = np.asarray(ia, dtype=float)
    ib = np.asarray(ib, dtype=float)
    ic = np.asarray(ic, dtype=float)

    if method == "rms_jump":
        return _detect_rms_jump(t, ia, ib, ic, threshold, frequency_hz)
    elif method == "derivative":
        return _detect_derivative(t, ia, ib, ic, threshold)
    elif method == "residual":
        return _detect_residual(t, ia, ib, ic, threshold)
    elif method == "sequence":
        return _detect_sequence(t, ia, ib, ic, threshold)
    else:
        raise ValueError(
            f"Unknown method: '{method}'. "
            f"Expected 'rms_jump', 'derivative', 'residual', or 'sequence'."
        )
