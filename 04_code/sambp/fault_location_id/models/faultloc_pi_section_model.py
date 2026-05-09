"""
faultloc_pi_section_model.py
=============================
Two-section pi-model state-space for the SAMBP Fault-Location Identification
project (HIF-TF locator).

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP0.5  Appendix A : annotated pi-circuit + KVL/KCL -> state-space (A,B,C,D)
                       and symbolic dH/dalpha, dH/dRx.
    WP3.4  Single-phase HIF baseline before generalisation to 3-phase
                       (faultloc_three_phase_model.py).

Physical model
--------------
11 kV / 100 km feeder split at fault location alpha in (0, 1) with a single
HIF shunt R_x at the split node.  Per-unit-length values per IEEE_Access
manuscript Sect. II-A:

    R'  = 0.0728  ohm/km
    L'  = 0.927   mH/km          (= 4 R' as legacy heuristic, but use SI)
    C'  = 11.6    nF/km          (= 3 R' as legacy heuristic, but use SI)

State vector (2-section pi-model after Sect. II-B):
    x = [V_C1, V_C2, I_L1, I_L2]^T

The 4x4 A-matrix has A_11 = -1 / (R_x * C_1) which is continuously
differentiable in (alpha, R_x) -- this differentiability is the structural
property that the two-stage optimiser exploits.

Public API (target)
-------------------
    build_pi_state_space(alpha, Rx, line_length_km, *, R_per_km, L_per_km, C_per_km)
        -> (A, B, C, D)

    transfer_function_at(omega, A, B, C, D)
        -> H_complex

    dH_dtheta(omega, alpha, Rx, ...)
        -> (dH_dalpha, dH_dRx)   # closed form via faultloc_analytical_gradients

References
----------
Saha-2010; Wang-Lopes-2023 EPSR; Lopes-2023 distributed-parameter formulation.
"""

# Stub: implementation lands in WP0.5 (W2 Mon, Phase 0).
