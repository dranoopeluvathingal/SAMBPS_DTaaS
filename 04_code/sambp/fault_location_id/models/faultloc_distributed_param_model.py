"""
faultloc_distributed_param_model.py
====================================
Continuously parametrised distributed-parameter line model for the SAMBP
Fault-Location Identification project (HIF-TF locator).

Closes the v2/v3 plan's single-most-important residual issue: the 2-section
pi-model has a 39.44 % mean modelling error vs a 50-section reference.  A
distributed-parameter formulation derives H(j*omega_0; alpha, Rx) in closed
form by inserting the fault as a shunt at distance alpha between two cascaded
ABCD / Bergeron / hyperbolic blocks.  dH/dalpha is then analytic via the
derivative of cosh(gamma*alpha*L) and sinh(gamma*alpha*L).

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP2.1  Derive cascaded ABCD / Bergeron / hyperbolic closed-form H.
    WP2.2  Derive dH/dalpha and dH/dRx in closed form.
    WP2.3  Reproduce 50-section reference within 1 percent across (alpha, Rx).
    WP2.4  Replace finite-difference gradients with analytical gradients in
           the optimiser (faultloc_two_stage_optimiser.py + WP2.4).
    WP2.5  Re-run all 720 cases + Monte-Carlo on the new optimiser.

Public API (target)
-------------------
    H_closedform(omega, alpha, Rx, *, line_length_km, R_per_km, L_per_km,
                 C_per_km, G_per_km=0.0) -> complex

    dH_dalpha_closedform(omega, alpha, Rx, ...) -> complex
    dH_dRx_closedform(omega, alpha, Rx, ...)    -> complex

References
----------
Lopes-2023; Trew-2023; Suonan-2023; Kang-2021; Pozar Microwave Engineering
ABCD chapter.  Acceptance test T-C1 in Sect. 6 of the v3 manual:
    modelling error vs 50-section ref < 5 % across all (alpha, Rx);
    estimator improvement >= 30 % at SNR_I <= 30 dB vs Phase-1 baseline.
"""

# Stub: implementation lands in WP2.1-2.3 (W10-W14, Phase 2).
