# =============================================================================
# sambp / sambp_sync_oc
# adaptation/adaptive_mapping.py
#
# Map inverse-estimated source parameters to proposed relay settings.
#
# Mapping logic (Stage 1)
# -----------------------
# Available fault current:
#     I_avail = I_ss + I_sub   (total peak current, pu)
#
# Proposed pickup:
#     pickup_new = k_pickup · I_ss
#     — set above steady-state component so relay rides through transient
#
# Proposed TMS:
#     tms_new = k_tms · tau_ac
#     — proportional to AC decay constant; longer decay → more time margin
#       clamped so faster faults still get a quick response
#
# Both outputs are passed through bounded_update.clip_relay_settings.
#
# Public API
# ----------
# map_source_estimate_to_oc_settings(theta_hat, relay_config) → dict
# =============================================================================

import numpy as np
from adaptation.bounded_update import clip_relay_settings


# ---------------------------------------------------------------------------
# Tunable mapping coefficients (Stage 1 defaults)
# ---------------------------------------------------------------------------
K_PICKUP     = 0.8    # pickup set at 80% of estimated steady-state fault current
K_TMS        = 0.12   # TMS ≈ 0.12 × tau_ac (s); empirically derived for IEC curves

# HIF-regime constants
I_SS_NOMINAL = 0.51   # bolted-fault reference (Xd''=0.2, V=1.0, X_th=0.15 → I_sub≈2.9, I_ss≈0.51 pu)
K_TMS_HIF    = 0.08   # more aggressive TMS for HIF to maintain trip speed at low current multiples


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_source_estimate_to_oc_settings(theta_hat, relay_config):
    """
    Convert reduced source parameters into proposed adaptive relay settings.

    Parameters
    ----------
    theta_hat    : dict — estimated parameters from parameter_estimator
                   Required keys: "I_ss", "I_sub", "tau_ac"
    relay_config : dict — from RELAY_CONFIG
                   Required keys: "adaptive_bounds"
                     { pickup_min_pu, pickup_max_pu, tms_min, tms_max }

    Returns
    -------
    dict with keys:
        pickup_proposed : float — proposed pickup setting (pu)
        tms_proposed    : float — proposed TMS
        pickup_clipped  : float — after bound enforcement
        tms_clipped     : float — after bound enforcement
        I_avail         : float — estimated total fault current (pu)
        mapping_notes   : str   — brief explanation of applied logic
    """
    I_ss   = float(theta_hat["I_ss"])
    I_sub  = float(theta_hat["I_sub"])
    tau_ac = float(theta_hat["tau_ac"])

    I_avail = I_ss + I_sub   # total estimated peak fault current

    # --- Pickup: fraction of steady-state current ---
    # Rationale: relay should not pick up on load (< I_ss),
    # but must pick up reliably during sustained fault.
    pickup_proposed = K_PICKUP * I_ss

    # --- TMS: proportional to AC decay constant, with HIF-aware correction ---
    # Rationale: a faster-decaying fault (small tau_ac) needs a lower TMS
    # (faster trip); a slowly decaying fault allows slightly more delay.
    # For HIF (low I_ss), scale TMS down to compensate for slow trip at low
    # current multiples — otherwise the inverse-time element is too slow.
    tms_hif_factor   = float(np.clip(I_ss / I_SS_NOMINAL, 0.30, 1.0))
    k_tms_effective  = K_TMS if tms_hif_factor >= 0.9 else K_TMS_HIF
    tms_proposed     = k_tms_effective * tau_ac * tms_hif_factor

    # --- Apply bounds ---
    bounds = relay_config["adaptive_bounds"]
    pickup_clipped, tms_clipped = clip_relay_settings(
        pickup_proposed, tms_proposed, bounds
    )

    notes = (
        f"I_avail={I_avail:.3f} pu | "
        f"pickup={pickup_proposed:.3f}→{pickup_clipped:.3f} pu | "
        f"tms={tms_proposed:.4f}→{tms_clipped:.4f} | "
        f"hif_factor={tms_hif_factor:.3f} k_tms={k_tms_effective:.3f}"
    )

    return {
        "pickup_proposed": pickup_proposed,
        "tms_proposed":    tms_proposed,
        "pickup_clipped":  pickup_clipped,
        "tms_clipped":     tms_clipped,
        "I_avail":         I_avail,
        "mapping_notes":   notes,
    }
