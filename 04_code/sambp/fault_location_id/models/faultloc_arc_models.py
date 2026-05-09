"""
faultloc_arc_models.py
=======================
Arc-fault stimulus library for the SAMBP Fault-Location Identification
project.  Provides four arc classes drawn from the cited HIF literature so
that the locator's robustness can be reported as a Delta-error vs the
manuscript's anti-parallel diode arc baseline.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP0.5  Provenance citations for the diode-arc parameters
           (V_kp=50 V, V_kn=45 V, R_sp=5 ohm, R_sn=6 ohm, R_off=1e6 ohm).
    WP4.2  Cassie-Mayr-Kizilcay dynamic arc (Darwish-Elkalashy-2005).
    WP4.3  Wang-2020 distortion-controllable HIAF model
           (open-source PSCAD vendoring; github.com/MingjieWei).
    WP4.4  Torres-2022 stochastic-configurable arc (build-up, shoulder,
           asymmetry, avalanche, intermittence, modulation).

Public API (target)
-------------------
    diode_arc(V_kp=50, V_kn=45, R_sp=5, R_sn=6, R_off=1e6, eps=1e-3)
    kizilcay_arc(...)
    wang2020_arc(...)
    torres2022_arc(...)
    arc_run(model, t, v) -> i_arc(t)

Acceptance posture
------------------
Phase-4 deliverable D-E requires: < 5 % mean location error at SNR >= 30 dB
across all four arc classes AND numerical superiority over >= 2 of 4
competitor methods (faultloc_competitor_*.py).
"""

# Stub: implementation lands in WP4.2-4.4 (W20-W24, Phase 4).
