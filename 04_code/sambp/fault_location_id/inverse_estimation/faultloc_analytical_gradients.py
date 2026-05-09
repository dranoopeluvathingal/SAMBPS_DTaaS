"""
faultloc_analytical_gradients.py
=================================
Closed-form analytical gradients dH/dalpha and dH/dRx for the SAMBP
Fault-Location Identification project.  Eliminates the central-difference
approximation that the IEEE Access manuscript's Sect. IV optimiser uses:
under the WP2.1 distributed-parameter formulation, both partials are
analytic via the derivative of cosh(gamma*alpha*L), sinh(gamma*alpha*L).

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP2.2   Derive dH/dalpha and dH/dRx in closed form.
    WP0.5   Symbolic verification (MATLAB sym/diff or sympy regression);
            ship in Appendix A.

Public API (target)
-------------------
    dH_dalpha(omega, alpha, Rx, ...) -> complex
    dH_dRx(omega, alpha, Rx, ...)    -> complex
    jacobian(omega, alpha, Rx, ...)  -> ndarray (1, 2) complex
"""

# Stub: implementation lands in WP2.2 (W10-W12, Phase 2).
