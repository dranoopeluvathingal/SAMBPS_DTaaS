"""
faultloc_ieee_feeders.py
=========================
IEEE 13- / 34- / 123-node test feeder digital twins for the SAMBP
Fault-Location Identification project.  Replaces the single-feeder /
single-section restriction of the IEEE Access manuscript with the
benchmark feeders used by the HIF location community.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP3.3  Build IEEE 13- / 34- / 123-node test feeder digital twins in
           PSCAD + MATLAB; export V/I waveforms at 10 kHz.
    WP3.7  Validate on the CNRS-2024 IEEE-34 HIF dataset
           (DOI 10.57745/KRYCYY).  Compare against simulator output.

Acceptance test (T-D1)
----------------------
Mean location error < 3 % on IEEE 34-node at SNR >= 30 dB.

Public API (target)
-------------------
    load_feeder(name)              # name in {'IEEE_13', 'IEEE_34', 'IEEE_123'}
        -> FeederModel
    inject_hif(feeder, bus, alpha, Rx, fault_type, arc_model) -> WaveformBundle
"""

# Stub: implementation lands in WP3.3, WP3.7 (W10-W22, Phase 3).
