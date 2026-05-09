"""
faultloc_crlb_dualchannel.py
=============================
Joint dual-channel CRLB in (V, I) space for the SAMBP Fault-Location
Identification project.  Cross-checks the proper-complex-Gaussian-ratio
CRLB (faultloc_crlb_proper.py) by computing the FIM directly from the
two AWGN channels and projecting onto (alpha, R_x).

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP1.6   Joint dual-channel FIM in (V, I) projected onto (alpha, R_x)
            via Nehorai-Hawkes-2000 / Kay-1993 Vol. I Ch. 15.
            Cross-check vs faultloc_crlb_proper.py.

Public API (target)
-------------------
    fim_dualchannel(omega, alpha, Rx, *, snr_v_db, snr_i_db, ...)
        -> ndarray (2, 2) real
    crlb_dualchannel(...) -> CRLBResult
"""

# Stub: implementation lands in WP1.6 (W6-W9, Phase 1).
