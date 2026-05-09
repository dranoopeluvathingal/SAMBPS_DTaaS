"""
faultloc_identifiability_check.py
==================================
Structural identifiability check for the SAMBP Fault-Location Identification
project.  Implements the Hermann-Krener observability rank condition (ORC)
with a STRIKE-GOLDD style symbolic Lie-derivative computation, and provides
a numerical fallback that maps J(alpha, R_x) on a representative case.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP3.5  J(alpha, R_x) cost-surface mapping; Hermann-Krener ORC
           (Villaverde-2024 STRIKE-GOLDD).

Why this matters
----------------
A single complex H observation is just-determined for two real unknowns
(alpha, R_x) but locally degenerate where dH/dalpha and dH/dRx are colinear.
The check flags such regions before the optimiser is run; the gate
(faultloc_confidence_gate.py) consumes the flag.

Public API (target)
-------------------
    structural_orc(model, theta_grid) -> bool
    map_J_surface(omega, theta_grid, *, model, cost) -> ndarray
    flag_local_degeneracy(theta_hat, J_surface) -> {ok, degenerate}
"""

# Stub: implementation lands in WP3.5 (W14-W18, Phase 3).
