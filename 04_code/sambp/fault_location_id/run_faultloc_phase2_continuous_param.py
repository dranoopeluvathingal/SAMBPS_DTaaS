"""
run_faultloc_phase2_continuous_param.py
========================================
Phase-2 continuously-parametrised optimiser runner for the SAMBP
Fault-Location Identification project (W6-W16, overlaps Phase 1, ~28 PD).

Mathematical work that retires the 39.44 % section-modelling-error ceiling
identified in Sect. II-D of the IEEE Access manuscript.  Closes deliverable
D-C and decision gate D2.

Pipeline
--------
    WP2.1  Cascaded ABCD / Bergeron / hyperbolic closed-form H(j*omega_0)
           (faultloc_distributed_param_model.py).
    WP2.2  Closed-form dH/dalpha and dH/dRx via cosh/sinh derivatives
           (faultloc_analytical_gradients.py).
    WP2.3  Reproduce 50-section reference within 1 percent across all
           (alpha, R_x); root-cause and iterate if > 1 %.
    WP2.4  Replace finite-difference gradients with analytical gradients
           in the optimiser (faultloc_two_stage_optimiser.py); add the
           hyperparameter sensitivity sub-table.
    WP2.5  Re-run all 720 cases + Monte-Carlo on the new optimiser;
           compare to Phase-1 baseline; report estimator improvement.
    WP2.6  Phase-2 milestone document; revised IEEE Access response or
           TPWRD follow-on draft; D2 review.

Acceptance test (T-C1)
----------------------
Modelling error vs 50-section ref < 5 % across all (alpha, R_x);
estimator improvement >= 30 % at SNR_I <= 30 dB vs Phase-1 baseline.

Outputs
-------
    outputs/phase2_modelfit.csv
    outputs/phase2_montecarlo.mat
    outputs/phase2_estimator_improvement.png
"""

# Stub: implementation lands across WP2.1-2.6 (W6-W16, Phase 2).
