"""
run_faultloc_phase1_crossplatform.py
=====================================
Phase-1 cross-platform validation + corrected-CRLB runner for the SAMBP
Fault-Location Identification project (W2-W10, ~35 PD).

Two work-streams in parallel:
    (a) Independent simulator validation: PSCAD + EMTP-RV + 50-section
        pure-MATLAB reference (WP1.1, WP1.2, WP1.3, WP1.4).  Re-run the
        existing optimiser on each independent dataset and quantify the
        Delta-error attributable to optimiser-vs-data model mismatch.
    (b) Corrected CRLB (WP1.6) -- proper-complex-Gaussian-ratio
        (faultloc_crlb_proper.py) cross-checked with joint dual-channel
        FIM (faultloc_crlb_dualchannel.py); Geary-Hinkley validity test;
        CRLB-vs-empirical overlay plots.

Plus 100-trial Monte-Carlo per grid cell (WP1.5) for mean +/-
95th-percentile and per-cell numerical bias / 95 % CI.

Acceptance test (T-B1)
----------------------
Mean location error < 2 % at SNR_I >= 30 dB across all 3 simulators;
max location error < 5 %; per-cell 95 % CI excludes zero in < 5 % of cells.

Outputs
-------
    outputs/phase1_crossplatform.csv
    outputs/phase1_montecarlo.mat
    outputs/crlb_overlay_*.pdf
    outputs/phase1_arxiv_preprint.pdf
"""

# Stub: implementation lands across WP1.1-1.7 (W2-W10, Phase 1).
