"""
faultloc_fim_multiport.py
==========================
Multi-port Fisher Information Matrix for the SAMBP Fault-Location
Identification project.  Generalises the single-port CRLB
(faultloc_crlb_proper.py + faultloc_crlb_dualchannel.py) to the 3-phase
case: 3 ports -> 6 real observations per port -> 18 real observations in
total, projected onto (alpha, R_x).

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP3.6   Multi-port FIM extension; update ML cost and CRLB overlays.

Public API (target)
-------------------
    fim_multiport(Y_abc_meas, *, alpha, Rx, sigma_v, sigma_i)
        -> ndarray (2, 2) real
"""

# Stub: implementation lands in WP3.6 (W14-W18, Phase 3).
