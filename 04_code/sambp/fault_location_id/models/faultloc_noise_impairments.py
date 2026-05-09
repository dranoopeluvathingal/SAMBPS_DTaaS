"""
faultloc_noise_impairments.py
==============================
Field-grade impairment library for the SAMBP Fault-Location Identification
project.  Replaces the AWGN-only assumption of the IEEE Access manuscript's
Sect. V-B with five impairment classes covering the dominant non-Gaussian
phenomena seen in distribution feeders.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP4.1  Add five impairment classes:
              1. Impulsive noise         (Bernoulli-Gaussian)
              2. Harmonic background     (2nd / 5th / 7th / 11th)
              3. CT/PT saturation        (IEEE C37.110, remanence + burden)
              4. +/- 0.5 Hz off-nominal  (IEEE C37.118.1 P-class)
              5. ADC quantisation        (12 / 14 / 16 bit)

           Re-run the 720-grid for each impairment class; report mean +
           95th-percentile location error.

Public API (target)
-------------------
    add_impulsive(x, *, p=0.01, sigma_high=10.0)
    add_harmonics(x, *, harmonics=(2, 5, 7, 11), levels_pu=(0.05,)*4)
    add_ct_saturation(i_primary, *, remanence=0.5, burden_va=10)
    shift_off_nominal(x, *, delta_hz=0.5)
    quantise_adc(x, *, n_bits=14, full_scale=1.0)

Acceptance test (T-E1)
----------------------
< 5 % mean location error at SNR >= 30 dB across all 5 impairment classes.
"""

# Stub: implementation lands in WP4.1 (W18-W20, Phase 4).
