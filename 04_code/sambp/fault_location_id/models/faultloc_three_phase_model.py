"""
faultloc_three_phase_model.py
==============================
Three-phase Y_abc admittance model for the SAMBP Fault-Location Identification
project.  Generalises the single-phase 2-section pi-model
(faultloc_pi_section_model.py) and the closed-form distributed-parameter
formulation (faultloc_distributed_param_model.py) to a 3-port admittance
matrix Y_abc(j*omega_0).

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP3.1  Generalise state-space to 3-port admittance Y_abc(j*omega_0);
           derive multi-port closed-form H per Phase 2.
    WP3.2  Add laterals, tap loads, >= 1 distributed generator (DG);
           parameterise upstream Thevenin source.
    WP3.4  Add SLG, LL, LLG fault types in addition to single-phase HIF.

Public API (target)
-------------------
    build_Y_abc(alpha, Rx, fault_type, *, line_length_km, conductor_geom,
                soil_resistivity, frequency=50.0) -> ndarray (3x3 complex)

    H_phase(j*omega, alpha, Rx, fault_type, ...)
        -> ndarray (3,) complex   # phase-to-source admittance vector
"""

# Stub: implementation lands in WP3.1-3.4 (W10-W18, Phase 3).
