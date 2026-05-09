"""
faultloc_taylor_fourier.py
===========================
First-order Taylor-Fourier phasor estimator for the SAMBP Fault-Location
Identification project.  Replaces the single-bin DFT (Sect. III of the
IEEE Access manuscript) which is biased under the non-stationary
arc-modulated waveforms typical of HIF events.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP3.5  Replace single-bin DFT with 1st-order Taylor-Fourier estimator
           (Platas-Garza-2010; Ortiz-Bejar-2025).  Quantify phasor-bias
           improvement vs single-bin DFT on arc-modulated waveforms.
           Map J(alpha, R_x) on a representative case for identifiability
           inspection (Hermann-Krener observability rank condition via
           STRIKE-GOLDD; faultloc_identifiability_check.py).

Acceptance test (T-D1)
----------------------
Phasor-bias improvement vs single-bin DFT >= 50 % on arc-modulated
waveforms; identifiability map published.

Public API (target)
-------------------
    taylor_fourier(x, *, fs, f0=50.0, K=1, window_cycles=1)
        -> (phasor_complex, dphasor_dt_complex)
"""

# Stub: implementation lands in WP3.5 (W14-W18, Phase 3).
