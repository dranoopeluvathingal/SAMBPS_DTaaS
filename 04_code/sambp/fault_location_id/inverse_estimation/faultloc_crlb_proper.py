"""
faultloc_crlb_proper.py
========================
Cramer-Rao Lower Bound under the proper-complex-Gaussian-ratio noise model
for the SAMBP Fault-Location Identification project.  Closes the most
consequential audit finding of v2/v3: the IEEE Access manuscript's
Sect. VIII derives the FIM under circular complex Gaussian noise on H_meas,
but H_meas is the ratio of two AWGN channels and the resulting density on
H is non-Gaussian.  The Gaussian-on-H FIM under-estimates the true bound
and is valid only when |I| >> sigma_I -- the opposite of the HIF regime.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP1.6   Re-derive the FIM via the proper-complex-Gaussian-ratio
            framework (Kuruoglu-2018 ASCE).  Cross-check against the joint
            dual-channel FIM (faultloc_crlb_dualchannel.py).  Add the
            Geary-Hinkley validity test.  Produce CRLB-vs-empirical
            overlay plots.

Acceptance test (T-B2)
----------------------
Empirical RMS error within 25 % of proper-complex-Gaussian-ratio CRLB at
SNR >= 30 dB; Geary-Hinkley validity test reported per cell.

Public API (target)
-------------------
    crlb_proper(omega, alpha, Rx, *, snr_v_db, snr_i_db, ...)
        -> CRLBResult(var_alpha, var_Rx, cov_alpha_Rx,
                      gh_validity, regime_flag)
"""

# Stub: implementation lands in WP1.6 (W6-W9, Phase 1).
