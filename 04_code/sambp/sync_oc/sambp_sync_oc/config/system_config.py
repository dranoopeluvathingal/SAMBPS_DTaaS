# =============================================================================
# sambp / sambp_sync_oc
# config/system_config.py
#
# Central system-level parameters shared across all pipeline stages.
# All quantities in per-unit (pu) on the machine base unless stated otherwise.
# =============================================================================

SYSTEM_CONFIG = {
    "frequency_hz":  50.0,
    "sampling_hz":   10000.0,
    "t_start":       0.0,
    "t_end":         2.0,   # extended to 2 s to allow IEC curve trip accumulation
    "fault_time":    0.1,
    "clear_time":    0.25,

    "generator": {
        "V_nom_pu":       1.0,
        "Xd_pu":          1.8,
        "Xdp_pu":         0.3,
        "Xdpp_pu":        0.2,
        "Tdp_s":          0.8,
        "Tdpp_s":         0.03,
        "Ra_pu":          0.01,
        "P_prefault_pu":  0.8,
        "Q_prefault_pu":  0.2,
    },

    "network": {
        "X_th_pu":    0.15,
        "R_th_pu":    0.01,
        "line_R_pu":  0.02,
        "line_X_pu":  0.08,
        "fault_R_pu": 0.01,
    },
}

# ---------------------------------------------------------------------------
# Stage 2: Park dq 6th-order synchronous machine parameters
# ---------------------------------------------------------------------------
SYSTEM_CONFIG.update({
    "park_dq": {
        # Machine parameters (6th-order model)
        "Xq_pu":    1.7,    # q-axis synchronous reactance
        "Xqp_pu":   0.5,    # q-axis transient reactance
        "Xqpp_pu":  0.2,    # q-axis subtransient reactance
        "Tdp0_s":   0.8,    # d-axis open-circuit transient time constant (= Td' in existing params)
        "Tdpp0_s":  0.03,   # d-axis open-circuit subtransient (= Tdpp in existing params)
        "Tqp0_s":   0.4,    # q-axis open-circuit transient time constant
        "Tqpp0_s":  0.05,   # q-axis open-circuit subtransient time constant
        "H_s":      3.5,    # inertia constant (MW·s/MVA)
        "D_pu":     2.0,    # damping coefficient (pu torque / pu speed deviation)
        # AVR (simple first-order exciter)
        "Ka":       200.0,  # exciter gain
        "Ta_s":     0.02,   # exciter time constant (s)
        "Efd_max":  5.0,    # field voltage ceiling (pu)
        "Efd_min":  0.0,
        "Vref_pu":  1.05,   # reference voltage (pu)
        # PSS (lead-lag on speed deviation)
        "Kpss":     5.0,    # PSS gain
        "Tw_s":     5.0,    # washout time constant (s)
        "T1_s":     0.1,    # lead time constant (s)
        "T2_s":     0.02,   # lag time constant (s)
        # Governor (simple first-order droop)
        "R_droop":  0.05,   # speed droop (pu)
        "Tch_s":    0.3,    # turbine time constant (s)
        "Tm_max":   1.2,    # max mechanical torque (pu)
        "Tm_min":   0.0,
    }
})
