# =============================================================================
# sambp / sambp_sync_oc
# adaptation/bounded_update.py
#
# Enforce safe bounds on adaptive relay setting updates.
#
# Two functions:
#   clip_relay_settings  — hard clip to [min, max] bounds
#   rate_limit_update    — limit the step size from the previous setting
#                          (prevents large sudden jumps)
#
# Public API
# ----------
# clip_relay_settings(pickup, tms, bounds)                      → (float, float)
# rate_limit_update(pickup_new, tms_new, pickup_old, tms_old,
#                   max_pickup_step, max_tms_step)               → (float, float)
# =============================================================================

import numpy as np


def clip_relay_settings(pickup, tms, bounds):
    """
    Enforce hard bounds on pickup and TMS settings.

    Parameters
    ----------
    pickup : float — proposed pickup setting (pu)
    tms    : float — proposed TMS
    bounds : dict  — from RELAY_CONFIG["adaptive_bounds"]
               keys: pickup_min_pu, pickup_max_pu, tms_min, tms_max

    Returns
    -------
    (pickup_clipped, tms_clipped) : tuple of float
    """
    pickup_clipped = float(np.clip(
        pickup,
        bounds["pickup_min_pu"],
        bounds["pickup_max_pu"],
    ))
    tms_clipped = float(np.clip(
        tms,
        bounds["tms_min"],
        bounds["tms_max"],
    ))
    return pickup_clipped, tms_clipped


def rate_limit_update(
    pickup_new,
    tms_new,
    pickup_old,
    tms_old,
    max_pickup_step=0.3,
    max_tms_step=0.05,
):
    """
    Limit the magnitude of the step change from previous relay settings.

    Prevents aggressive single-event adaptation from causing protection
    coordination failures with upstream/downstream relays.

    Parameters
    ----------
    pickup_new, tms_new   : float — proposed updated settings
    pickup_old, tms_old   : float — current active settings
    max_pickup_step       : float — maximum allowed |Δpickup| per update (pu)
    max_tms_step          : float — maximum allowed |ΔTMS| per update

    Returns
    -------
    (pickup_limited, tms_limited) : tuple of float
    """
    d_pickup = pickup_new - pickup_old
    d_tms    = tms_new    - tms_old

    d_pickup_limited = float(np.clip(d_pickup, -max_pickup_step, max_pickup_step))
    d_tms_limited    = float(np.clip(d_tms,    -max_tms_step,    max_tms_step))

    return (pickup_old + d_pickup_limited,
            tms_old    + d_tms_limited)


def apply_bounded_update(
    pickup_proposed,
    tms_proposed,
    pickup_current,
    tms_current,
    bounds,
    max_pickup_step=0.3,
    max_tms_step=0.05,
):
    """
    Combined update: rate-limit first, then clip to hard bounds.

    This is the recommended single call for the full adaptation step.

    Parameters
    ----------
    pickup_proposed, tms_proposed : float — from adaptive_mapping
    pickup_current, tms_current   : float — currently active relay settings
    bounds                        : dict  — RELAY_CONFIG["adaptive_bounds"]
    max_pickup_step, max_tms_step : float — rate limits

    Returns
    -------
    dict with keys:
        pickup_final : float — bounded updated pickup (pu)
        tms_final    : float — bounded updated TMS
        pickup_step  : float — actual step applied (after rate limit)
        tms_step     : float — actual step applied (after rate limit)
    """
    # Step 1: rate limit
    pickup_rl, tms_rl = rate_limit_update(
        pickup_proposed, tms_proposed,
        pickup_current,  tms_current,
        max_pickup_step, max_tms_step,
    )

    # Step 2: hard clip
    pickup_final, tms_final = clip_relay_settings(pickup_rl, tms_rl, bounds)

    return {
        "pickup_final": pickup_final,
        "tms_final":    tms_final,
        "pickup_step":  pickup_final - pickup_current,
        "tms_step":     tms_final    - tms_current,
    }
