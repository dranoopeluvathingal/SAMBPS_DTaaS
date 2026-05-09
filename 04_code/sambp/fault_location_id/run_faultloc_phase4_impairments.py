"""
run_faultloc_phase4_impairments.py
===================================
Phase-4 field-grade impairments + competitor benchmark + arc-class
diversification runner for the SAMBP Fault-Location Identification project
(W18-W30, overlaps Phase 3, ~45 PD).  Closes deliverable D-E and decision
gate D4.

Pipeline
--------
    WP4.1  Five impairment classes (faultloc_noise_impairments.py):
              impulsive, harmonic, CT/PT saturation, off-nominal, ADC quant.
    WP4.2  Cassie-Mayr-Kizilcay arc (faultloc_arc_models.py).
    WP4.3  Wang-2020 distortion-controllable arc (vendored from MingjieWei
           PSCAD repository).
    WP4.4  Torres-2022 stochastic-configurable arc.
    WP4.5  Re-implement and benchmark four competitors on identical
           720-case waveforms (faultloc_competitor_*.py): Paramo-2023
           eigenvalue, Iurinic-2018 spectral, Cui-Weng-2020 micro-PMU,
           Zeng-2021 double-ended HIF.  Publish numerical Table 3-bis.

Acceptance test (T-E1)
----------------------
< 5 % mean location error at SNR >= 30 dB across all 5 impairment classes
AND numerical superiority over >= 2 of 4 competitors on mean location
error.

Outputs
-------
    outputs/phase4_impairments.mat
    outputs/phase4_table3bis.csv
    outputs/phase4_competitor_scatter.pdf
"""

# Stub: implementation lands across WP4.1-4.6 (W18-W30, Phase 4).
