"""
faultloc_legacy_v1_2section.py
================================
**Legacy v1-baseline 2-section forward model.** R-L series only, no
shunt capacitance.  Reproduces the IEEE_Access-2 v1 manuscript's
"2-section" formulation that v3 plan §3.7 quantifies as having mean
39.44 %, max 89.78 % modelling error vs a 50-section reference.

Topology
--------

    source --[ R_1 + j*omega*L_1 ]-- fault_node --[ R_2 + j*omega*L_2 ]-- remote
                                       |                                    |
                                      R_x to ground                       R_load to ground

No shunt C anywhere.  The transfer function reduces to a
series-parallel impedance computation (no state space needed):

    Z_1            = R_1 + j*omega*L_1
    Z_2            = R_2 + j*omega*L_2
    Z_far          = Z_2 + R_load
    Z_fault_combined = R_x || Z_far  =  R_x * Z_far / (R_x + Z_far)
    Z_in           = Z_1 + Z_fault_combined
    H              = 1 / Z_in

Why this module exists
----------------------
WP1.3 acceptance ("the 30-45 % regression test confirms the
modelling-error baseline") is satisfied by comparing this *legacy
v1-style* 2-section against the WP1.3 50-section reference.  The
modern Cascaded-Gamma 2-section in
``models/faultloc_pi_section_model.py`` (Appendix A, P0.5) is a
**strict improvement** over this legacy baseline -- it keeps the line-
charging shunt C terms that v1 dropped and so reduces the modelling
error from ~40 % to <1 %.  This module is therefore a *backward-
compatibility artefact*, useful only for:

  (a) reproducing the v1 manuscript's headline modelling-error
      numbers (39.44 % mean, 89.78 % max);
  (b) providing the comparator for the WP1.3 regression baseline;
  (c) anchoring the Phase-2 acceptance criterion (estimator
      improvement vs the v1 baseline).

**Do NOT use this module in the optimiser.**  The optimiser must
import from ``models/faultloc_pi_section_model.py`` (Cascaded-Gamma)
or, post-WP2.1, from ``models/faultloc_distributed_param_model.py``
(closed-form distributed-parameter).
"""

from __future__ import annotations

# Per-km defaults (mirror of faultloc_pi_section_model.py).
R_PER_KM = 0.0728
L_PER_KM = 0.927e-3
LINE_LENGTH_KM = 100.0
R_LOAD = 1.0e6


def H_legacy_v1_2section(
    alpha: float,
    Rx: float,
    omega: float,
    *,
    line_length_km: float = LINE_LENGTH_KM,
    R_per_km: float = R_PER_KM,
    L_per_km: float = L_PER_KM,
    R_load: float = R_LOAD,
) -> complex:
    """Source-end input admittance H = I_in / V_in for the legacy
    v1-style 2-section R-L-only model (no shunt C)."""
    L1_km = alpha * line_length_km
    L2_km = (1.0 - alpha) * line_length_km
    Z1 = R_per_km * L1_km + 1j * omega * L_per_km * L1_km
    Z2 = R_per_km * L2_km + 1j * omega * L_per_km * L2_km
    Z_far = Z2 + R_load
    Z_fault_combined = (Rx * Z_far) / (Rx + Z_far)
    Z_in = Z1 + Z_fault_combined
    return complex(1.0 / Z_in)
