# =============================================================================
# sambp / sambp_sync_oc
# config/relay_config.py
#
# Overcurrent relay parameters — fixed settings and adaptive bounds.
# pickup_pu and inst_pickup_pu are multiples of rated current.
# =============================================================================

RELAY_CONFIG = {
    "pickup_pu":       1.2,   # above max load current (I_load≈0.83 pu)
    "inst_pickup_pu":  2.5,   # subtransient I_rms peak ≈3.2 pu; inst at 2.5×
    "tms":             0.05,  # inverse-time backup element
    "curve_type":      "IEC_VeryInverse",

    "adaptive_bounds": {
        "pickup_min_pu":  1.1,
        "pickup_max_pu":  3.0,
        "tms_min":        0.05,
        "tms_max":        0.5,
    },

    "confidence_threshold": 0.7,
}

# ---------------------------------------------------------------------------
# Multi-generator coordination configuration
# ---------------------------------------------------------------------------
MULTI_GEN_CONFIG = {
    "n_generators":       2,
    "delta_I_margin_pu":  0.20,   # minimum pickup separation between relays (pu)
    "delta_t_grade_s":    0.15,   # minimum trip-time grading margin (s)
    "transformer_X_pu":  [0.06, 0.06],   # step-up transformer reactance per gen (pu)
    "transformer_R_pu":  [0.005, 0.005],
    # Generator relay settings (upstream relays, one per generator)
    # These are the initial fixed settings before adaptation
    "gen_relay_settings": [
        {"pickup_pu": 1.3, "inst_pickup_pu": 2.5, "tms": 0.06,
         "curve_type": "IEC_VeryInverse"},
        {"pickup_pu": 1.2, "inst_pickup_pu": 2.5, "tms": 0.05,
         "curve_type": "IEC_VeryInverse"},
    ],
    # Bus relay (downstream of all generator relays)
    "bus_relay": {
        "pickup_pu":      1.0,
        "inst_pickup_pu": 5.0,
        "tms":            0.03,
        "curve_type":     "IEC_VeryInverse",
    },
    "adaptive_bounds": {
        "pickup_min_pu": 1.0,
        "pickup_max_pu": 3.0,
        "tms_min":       0.02,
        "tms_max":       0.5,
    },
    "confidence_threshold": 0.7,
}
