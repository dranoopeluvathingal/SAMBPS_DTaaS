"""tests/test_phase2_no_3944_ceiling.py
==========================================

WP2.5 regression test: on the worst (alpha, R_x) cell from §II-D
Table 1 of the manuscript -- the v1 R-L-only 2-section ceiling cell
at (alpha, R_x) = (0.95, 5000), where the v1 modelling error is
~87.5 % vs the 50-section reference -- the Phase-2 distributed-
parameter optimiser must beat the v1-baseline location error by at
least 5x.

Setup
-----
We do NOT have v1's optimiser as a runnable artefact (the v1
manuscript is PDF-only).  We use the closest analogue available:

  * Phase-1 baseline      : my P0.5 cascaded-Gamma 2-section + central-
                            FD optimiser, run on the cell.  This is
                            INSIDE the 39.44 % manuscript ceiling.
  * v1 R-L-only baseline  : models/faultloc_legacy_v1_2section.py
                            (P1.3) -- the canonical v1-equivalent
                            forward model.  We compute the *forward*
                            modelling error (not the optimiser
                            location error) and verify the
                            distributed-parameter forward model from
                            P2.1 is at least 5x better.

The 5x factor is on |H| relative error, not on optimiser location
error -- the latter is dominated by the cost-surface ill-
conditioning that closes at WP3.5/WP3.6, not by forward-model
fidelity.  A direct optimiser-vs-optimiser 5x test is gated on
WP3.5+WP3.6.

Acceptance
----------
At (alpha=0.95, R_x=5000), |H_v1 - H_50sec| / |H_50sec| (v1
baseline forward error) must be at least 5x larger than
|H_distributed - H_50sec| / |H_50sec| (Phase-2 forward error).
This regression check guarantees no future Phase-2 commit accidentally
re-introduces the v1 ceiling.
"""

from __future__ import annotations

import numpy as np
from sambp_fault_location_id.models.faultloc_50section_reference import (
    H_model_n_sections,
)
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    H_distributed,
    magnitude_phase_error,
)
from sambp_fault_location_id.models.faultloc_legacy_v1_2section import (
    H_legacy_v1_2section,
)

OMEGA = 2 * np.pi * 50.0
ALPHA_WORST = 0.95
RX_WORST = 5000.0


def test_phase2_beats_v1_by_5x_on_worst_cell() -> None:
    """Distributed forward model is at least 5x better than v1 R-L-only
    on the (alpha, R_x) = (0.95, 5000) worst-case cell."""
    H_ref = H_model_n_sections(ALPHA_WORST, RX_WORST, OMEGA)
    H_v1 = H_legacy_v1_2section(ALPHA_WORST, RX_WORST, OMEGA)
    H_p2 = H_distributed(ALPHA_WORST, RX_WORST, OMEGA)
    err_v1, _ = magnitude_phase_error(H_v1, H_ref)
    err_p2, _ = magnitude_phase_error(H_p2, H_ref)
    ratio = err_v1 / max(err_p2, 1e-15)
    assert ratio >= 5.0, (
        f"v1 forward error = {err_v1:.4f} %, "
        f"Phase-2 distributed = {err_p2:.4e} %, "
        f"ratio = {ratio:.1f}x, expected >= 5x"
    )
