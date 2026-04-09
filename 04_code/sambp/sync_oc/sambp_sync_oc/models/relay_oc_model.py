# =============================================================================
# sambp / sambp_sync_oc
# models/relay_oc_model.py
#
# Overcurrent relay model — fixed and adaptive settings.
#
# Implements IEC 60255 inverse-time curves:
#   IEC_Inverse          : α=0.02, β=0.14,  γ=0
#   IEC_VeryInverse      : α=1.00, β=13.5,  γ=0
#   IEC_ExtremelyInverse : α=2.00, β=80.0,  γ=0
#   IEC_LongInverse      : α=1.00, β=120.0, γ=0
#   ANSI_Moderately      : α=0.02, β=0.0515,γ=0.114
#
# Trip criterion:
#   1. Instantaneous: I_rms ≥ inst_pickup_pu → trip immediately
#   2. Inverse-time:  I_rms ≥ pickup_pu → start timing, trip when
#                     accumulated time ≥ operate_time(I_rms/pickup_pu)
#
# Public API
# ----------
# compute_relay_current_rms(t, ia, ib, ic, window_cycles, frequency_hz)
#   → i_rms  (ndarray)
#
# run_overcurrent_relay(t, i_rms, pickup_pu, inst_pickup_pu,
#                       tms, curve_type)
#   → dict {pickup, inst_pickup, trip, trip_time, operate_time_curve}
# =============================================================================

import numpy as np

# ---------------------------------------------------------------------------
# IEC/ANSI curve coefficients  {curve_type: (alpha, beta, gamma)}
# Operate time: t_op = TMS × (β / (M^α − 1) + γ)   where M = I/I_pickup
# ---------------------------------------------------------------------------
_CURVE_COEFFS = {
    "IEC_Inverse":           (0.02,  0.14,   0.0),
    "IEC_VeryInverse":       (1.00,  13.5,   0.0),
    "IEC_ExtremelyInverse":  (2.00,  80.0,   0.0),
    "IEC_LongInverse":       (1.00,  120.0,  0.0),
    "ANSI_Moderately":       (0.02,  0.0515, 0.114),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _operate_time(M, tms, alpha, beta, gamma):
    """
    IEC/ANSI operate time formula.

    t_op = TMS × (β / (M^α − 1) + γ)

    Parameters
    ----------
    M     : array-like — current multiple  I / I_pickup  (must be > 1)
    tms   : float      — time multiplier setting
    alpha, beta, gamma : curve coefficients

    Returns
    -------
    ndarray — operate time (s); np.inf where M ≤ 1
    """
    M   = np.asarray(M, dtype=float)
    t   = np.full_like(M, np.inf)
    idx = M > 1.0
    t[idx] = tms * (beta / (M[idx] ** alpha - 1.0) + gamma)
    return t


def _sliding_rms(signal, n_window):
    """
    Causal sliding RMS over a rectangular window of n_window samples.
    Output is same length as input; first n_window-1 samples use expanding
    window (avoids NaN at start).
    """
    out    = np.zeros_like(signal, dtype=float)
    cumsum = np.cumsum(signal ** 2)
    for i in range(len(signal)):
        start = max(0, i - n_window + 1)
        count = i - start + 1
        out[i] = np.sqrt((cumsum[i] - (cumsum[start - 1] if start > 0 else 0.0))
                         / count)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_relay_current_rms(t, ia, ib, ic,
                               window_cycles=1.0, frequency_hz=50.0):
    """
    Compute the sliding RMS current seen by the relay.

    Uses the maximum of the three phase RMS values at each time step,
    consistent with a maximum-phase overcurrent relay element.

    Parameters
    ----------
    t             : ndarray — time vector (s)
    ia, ib, ic    : ndarray — phase currents (pu)
    window_cycles : float   — RMS window length in cycles (default 1.0)
    frequency_hz  : float   — system frequency (Hz)

    Returns
    -------
    ndarray — i_rms (pu), same length as t
    """
    t  = np.asarray(t,  dtype=float)
    ia = np.asarray(ia, dtype=float)
    ib = np.asarray(ib, dtype=float)
    ic = np.asarray(ic, dtype=float)

    dt       = t[1] - t[0]
    n_window = max(1, int(round(window_cycles / (frequency_hz * dt))))

    rms_a = _sliding_rms(ia, n_window)
    rms_b = _sliding_rms(ib, n_window)
    rms_c = _sliding_rms(ic, n_window)

    return np.maximum(np.maximum(rms_a, rms_b), rms_c)


def run_overcurrent_relay(
    t,
    i_rms,
    pickup_pu,
    inst_pickup_pu,
    tms,
    curve_type="IEC_VeryInverse",
):
    """
    Simulate overcurrent relay operation over the time vector.

    Parameters
    ----------
    t              : ndarray — time vector (s)
    i_rms          : ndarray — relay input RMS current (pu)
    pickup_pu      : float   — inverse-time pickup threshold (pu)
    inst_pickup_pu : float   — instantaneous pickup threshold (pu)
    tms            : float   — time multiplier setting
    curve_type     : str     — IEC/ANSI curve name (see _CURVE_COEFFS)

    Returns
    -------
    dict with keys:
        pickup            : ndarray[bool] — True when I_rms ≥ pickup_pu
        inst_pickup       : ndarray[bool] — True when I_rms ≥ inst_pickup_pu
        trip              : ndarray[bool] — True from trip instant onward
        trip_time         : float or None — time of first trip (s), None if no trip
        operate_time_curve: ndarray       — theoretical operate time at each sample (s)
    """
    if curve_type not in _CURVE_COEFFS:
        raise ValueError(
            f"Unknown curve_type: '{curve_type}'. "
            f"Available: {list(_CURVE_COEFFS.keys())}."
        )

    t     = np.asarray(t,     dtype=float)
    i_rms = np.asarray(i_rms, dtype=float)
    n     = len(t)
    dt    = t[1] - t[0]

    alpha, beta, gamma = _CURVE_COEFFS[curve_type]

    # --- Current multiples and thresholds ---
    M            = i_rms / (pickup_pu + 1e-12)
    pickup       = i_rms >= pickup_pu
    inst_pickup  = i_rms >= inst_pickup_pu

    # --- Operate time curve (theoretical, per sample) ---
    operate_time_curve = _operate_time(M, tms, alpha, beta, gamma)

    # --- Trip logic ---
    trip      = np.zeros(n, dtype=bool)
    trip_time = None

    # Check instantaneous trip first
    inst_idx = np.where(inst_pickup)[0]
    if len(inst_idx) > 0:
        trip_time = float(t[inst_idx[0]])
        trip[inst_idx[0]:] = True
        return {
            "pickup":             pickup,
            "inst_pickup":        inst_pickup,
            "trip":               trip,
            "trip_time":          trip_time,
            "operate_time_curve": operate_time_curve,
        }

    # Inverse-time integration: accumulate timer while in pickup
    timer = 0.0
    for i in range(n):
        if not pickup[i]:
            timer = 0.0   # reset on dropout
            continue

        timer += dt
        t_op = operate_time_curve[i]

        if np.isfinite(t_op) and timer >= t_op:
            trip[i:] = True
            trip_time = float(t[i])
            break

    return {
        "pickup":             pickup,
        "inst_pickup":        inst_pickup,
        "trip":               trip,
        "trip_time":          trip_time,
        "operate_time_curve": operate_time_curve,
    }
