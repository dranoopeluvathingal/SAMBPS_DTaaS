"""
run_faultloc_phase3_threephase.py
==================================
Phase-3 three-phase / IEEE-feeders / Taylor-Fourier runner for the SAMBP
Fault-Location Identification project (W10-W24, ~50 PD).  Closes
deliverable D-D and decision gate D3.

Pipeline
--------
    WP3.1  Generalise state-space to 3-port admittance Y_abc(j*omega_0)
           (faultloc_three_phase_model.py).
    WP3.2  Add laterals, tap loads, >= 1 DG; parameterise upstream
           Thevenin source.
    WP3.3  Build IEEE 13- / 34- / 123-node feeder digital twins
           (faultloc_ieee_feeders.py).
    WP3.4  Add SLG, LL, LLG fault types in addition to single-phase HIF;
           re-run extended 720-grid.
    WP3.5  Replace single-bin DFT with first-order Taylor-Fourier estimator
           (faultloc_taylor_fourier.py); identifiability map via
           Hermann-Krener / STRIKE-GOLDD (faultloc_identifiability_check.py).
    WP3.6  Multi-port FIM (faultloc_fim_multiport.py); update the ML cost
           and CRLB overlays.
    WP3.7  Validate on the CNRS-2024 IEEE-34 HIF dataset
           (DOI 10.57745/KRYCYY).

Acceptance test (T-D1)
----------------------
Mean location error < 3 % on IEEE 34-node at SNR >= 30 dB; phasor-bias
improvement vs single-bin DFT >= 50 % on arc-modulated waveforms;
identifiability map published.

Outputs
-------
    outputs/phase3_3phase.mat
    outputs/phase3_cnrs_validation.csv
    outputs/phase3_J_surface.pdf
    outputs/phase3_identifiability_map.pdf
"""

# Stub: implementation lands across WP3.1-3.8 (W10-W24, Phase 3).
