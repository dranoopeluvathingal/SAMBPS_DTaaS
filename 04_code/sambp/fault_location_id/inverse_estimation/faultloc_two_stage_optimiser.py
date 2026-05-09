"""
faultloc_two_stage_optimiser.py
================================
Two-stage joint estimator for (alpha, R_x) for the SAMBP Fault-Location
Identification project.  Stage 1 = 100 x 50 grid + top-3 multi-start +
8-neighbour steepest descent.  Stage 2 = gradient descent with Armijo
line-search and box constraints (alpha in [0,1], R_x in [100, 5000] ohm).

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP2.4   Replace finite-difference gradients with analytical gradients
            (faultloc_analytical_gradients.py); add hyperparameter
            sensitivity sub-table; re-verify Armijo line-search behaviour.
    WP0.4-6 Add global-optimum capture statistic over 720-grid.
    WP0.4-7 Add hyperparameter sensitivity sub-table.
    WP0.4-8 Report median + 95th-percentile CPU time (tic/toc over 1000 calls).

Cost function
-------------
The legacy Euclidean cost is replaced by the maximum-likelihood / whitened-
Mahalanobis cost so that the optimiser is consistent with the corrected FIM
(faultloc_crlb_proper.py + faultloc_crlb_dualchannel.py):

    J_ML(alpha, R_x) = (Delta H)^H * Sigma^{-1} * (Delta H)
    Delta H          = H_meas(j*omega_0) - H_model(j*omega_0; alpha, R_x)
    Sigma            = covariance of Delta H under the true noise model
                       (proper-complex-Gaussian-ratio, NOT circular Gaussian)

Public API (target)
-------------------
    estimate_alpha_Rx(H_meas, *, model='pi2_section'|'distributed',
                      cost='ml'|'euclid', hyper=DEFAULT_HYPER)
        -> EstimateResult(alpha, Rx, J_min, kappa_n, residual, cpu_time_ms)
"""

# Stub: implementation upgraded across WP2.4 (W12-W14, Phase 2).
