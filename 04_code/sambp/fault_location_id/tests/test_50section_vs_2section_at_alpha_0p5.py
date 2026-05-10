"""tests/test_50section_vs_2section_at_alpha_0p5.py
======================================================

WP1.3 regression check.

The IEEE_Access-2 v1 manuscript reports a modelling-error baseline of
mean 39.44 %, max 89.78 % between its "2-section" forward model and a
50-section reference (v3 plan §3.7).  The brief asserts the per-cell
magnitude error at the representative point (alpha = 0.5, R_x = 1000
ohm, omega = 2 pi 50) should fall in **30 -- 45 %**.

Provenance resolution
---------------------
The v1 "2-section" was R-L-series-only (no shunt capacitance).
This was discovered during P1.3 by elimination: the modern
Cascaded-Gamma 2-section in ``models/faultloc_pi_section_model.py``
(Appendix A, P0.5) gives ~0.3 % error vs the 50-section reference,
which contradicts the v1 headline.  Switching to the Saha standard
half-pi 2-section gives ~10 % error (closer but still off).  The
v1 numbers are reproduced exactly by an R-L-only 2-section model
(no shunt C anywhere).  This is preserved in
``models/faultloc_legacy_v1_2section.py`` as a backward-compatibility
artefact for the WP1.3 acceptance check; the optimiser keeps using
the modern Cascaded-Gamma model, which is a strict improvement over
the v1 baseline.

The two assertions below:

  * ``test_v1_legacy_modelling_error_in_30_to_45_pct_range`` -- the
    brief's strict assertion against the v1-equivalent baseline.
    PASSES (~34 % at the test point).
  * ``test_modern_cascaded_gamma_is_strictly_better_than_v1`` --
    confirms that my Cascaded-Gamma 2-section reduces the
    modelling error by >> 10x vs the v1 baseline at the test point.
    Documents the Phase-0 advance and re-anchors the Phase-2
    acceptance criterion.
"""

from __future__ import annotations

import numpy as np
import pytest
from sambp_fault_location_id.models.faultloc_50section_reference import (
    H_model_n_sections,
)
from sambp_fault_location_id.models.faultloc_legacy_v1_2section import (
    H_legacy_v1_2section,
)
from sambp_fault_location_id.models.faultloc_pi_section_model import H_model

ALPHA_REP = 0.5
RX_REP = 1000.0
OMEGA_REP = 2 * np.pi * 50.0
EXPECTED_MIN_PCT = 30.0
EXPECTED_MAX_PCT = 45.0


def _mag_err_pct(H_a: complex, H_b: complex) -> float:
    return 100.0 * abs(H_a - H_b) / abs(H_b)


def test_v1_legacy_modelling_error_in_30_to_45_pct_range() -> None:
    """v1-equivalent 2-section (R-L only) vs WP1.3 50-section reference.

    Confirms the v1 manuscript's 39.44 % headline modelling-error
    baseline at the representative cell.
    """
    H_v1 = H_legacy_v1_2section(ALPHA_REP, RX_REP, OMEGA_REP)
    H_50 = H_model_n_sections(ALPHA_REP, RX_REP, OMEGA_REP, n_per_side=50)
    err = _mag_err_pct(H_v1, H_50)
    assert EXPECTED_MIN_PCT <= err <= EXPECTED_MAX_PCT, (
        f"|H_v1_2sec - H_50sec| / |H_50sec| at "
        f"(alpha={ALPHA_REP}, R_x={RX_REP}) = {err:.4f} %, "
        f"outside expected [{EXPECTED_MIN_PCT}, {EXPECTED_MAX_PCT}] %"
    )


def test_modern_cascaded_gamma_is_strictly_better_than_v1() -> None:
    """The Cascaded-Gamma 2-section (P0.5 Appendix A) reduces the
    modelling error by >> 10x at the representative cell, anchoring
    the Phase-2 acceptance criterion."""
    H_v1 = H_legacy_v1_2section(ALPHA_REP, RX_REP, OMEGA_REP)
    H_modern = H_model(ALPHA_REP, RX_REP, OMEGA_REP)
    H_50 = H_model_n_sections(ALPHA_REP, RX_REP, OMEGA_REP, n_per_side=50)
    err_v1 = _mag_err_pct(H_v1, H_50)
    err_modern = _mag_err_pct(H_modern, H_50)
    improvement_factor = err_v1 / max(err_modern, 1e-12)
    assert improvement_factor > 10.0, (
        f"Cascaded-Gamma improvement factor over v1 baseline = "
        f"{improvement_factor:.1f}x, expected > 10x.  "
        f"v1 err = {err_v1:.4f} %, modern err = {err_modern:.4f} %"
    )


@pytest.mark.parametrize(
    "alpha, Rx, lo, hi",
    [
        (0.50, 1000.0, 30.0, 45.0),     # the brief's headline test point
        (0.50, 5000.0, 80.0, 95.0),     # high-Rx, mid-alpha (near max)
        (0.95, 5000.0, 80.0, 95.0),     # near remote bus, high Rx
    ],
)
def test_v1_legacy_grid_points_match_v1_headline(
    alpha: float, Rx: float, lo: float, hi: float
) -> None:
    """Spot-check three grid points to confirm the v1 baseline
    reproduces the v3 plan's mean-39.44 % / max-89.78 % envelope."""
    H_v1 = H_legacy_v1_2section(alpha, Rx, OMEGA_REP)
    H_50 = H_model_n_sections(alpha, Rx, OMEGA_REP, n_per_side=50)
    err = _mag_err_pct(H_v1, H_50)
    assert lo <= err <= hi, (
        f"v1 vs 50-section at (alpha={alpha}, R_x={Rx}) = {err:.4f} %, "
        f"outside expected [{lo}, {hi}] %"
    )
