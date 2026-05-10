"""tests/test_3phase_vs_pscad.py
==================================

WP3.1 (P3.1) acceptance test:

    The closed-form three-phase Y_send(j*omega_0; alpha, R_x) of
    `models/faultloc_three_phase_model.py` (a single 6x6 matrix
    exponential per uniform line section) must agree with the PSCAD-
    equivalent surrogate of `tools/pscad_surrogate_3ph.py` (a 50-
    sections-per-side LUMPED-pi cascade) to within 5 % on every
    entry of the 3x3 Y_send matrix at every (alpha, R_x) cell of
    the 720-grid (noiseless slice; SNR_V = SNR_I = inf).

Why these two pathways are independent
--------------------------------------

The closed-form model evaluates `expm(L * M_pde_neg)` where
M_pde_neg = [[0, +Z'_abc], [+Y'_abc, 0]] is the 6x6 system matrix.
The surrogate cascades 50 LUMPED-pi 6x6 ABCD matrices per side,
each of length L/50 km.  In the limit n_sections -> inf the two
agree to floating-point precision; at n_sections = 50 per side on a
100 km line at f0 = 50 Hz the per-section discretisation residual
is ~O((L/n * gamma)^2) which evaluates to ~10 ppm and accumulates
to ~0.05 % across the 100 sections.  The 5 % tolerance gives ample
margin.

When the canonical PSCAD output replaces the surrogate (lead
engineer's licensed Windows station), this test compares the
closed-form against PSCAD's J. Marti FD line model directly with
the same 5 % tolerance; the PSCAD agreement is then a real
cross-platform check rather than the dev-box surrogate
self-consistency check.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.models.faultloc_three_phase_model import (
    Y_send,
)
from scipy.io import loadmat

PROJ_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJ_ROOT / "data" / "pscad_3ph_720.mat"

OMEGA = 2.0 * np.pi * 50.0
TOLERANCE = 0.05  # 5 % per WP3.1 brief acceptance


def _load_pscad_3ph_bundle():
    if not DATA_PATH.exists():
        pytest.skip(
            f"{DATA_PATH} not present; run "
            f"`python tools/pscad_surrogate_3ph.py` to bootstrap."
        )
    S = loadmat(str(DATA_PATH))
    return {
        "Y_send": S["Y_send"],
        "alpha": S["grid_alpha"].squeeze(),
        "Rx": S["grid_Rx"].squeeze(),
        "snrV": S["grid_SNR_V"].squeeze(),
        "snrI": S["grid_SNR_I"].squeeze(),
    }


def test_pscad_bundle_schema() -> None:
    """Schema check: shapes and finite values."""
    S = _load_pscad_3ph_bundle()
    assert S["Y_send"].shape == (720, 3, 3)
    assert S["Y_send"].dtype == complex
    assert S["alpha"].shape == (720,)
    assert S["Rx"].shape == (720,)
    assert S["snrV"].shape == (720,)
    assert S["snrI"].shape == (720,)
    # The bundle stores noiseless physics; same Y_send across the
    # 16-cell noise grid for each (alpha, R_x).
    assert np.all(np.isfinite(S["Y_send"]))


def test_3phase_closed_form_agrees_with_pscad_surrogate_5pct() -> None:
    """Every entry |Y_send_closed_form| vs |Y_send_pscad| within 5 %.

    The bundle covers 9 alpha x 5 R_x = 45 distinct (alpha, R_x) cells
    replicated over the 4x4 noise grid; the noiseless physics is
    identical across replicates, so we evaluate on the 45-cell unique
    set and assert per-entry max relative error below TOLERANCE.
    """
    S = _load_pscad_3ph_bundle()
    seen: set[tuple[float, float]] = set()
    max_rel_err = 0.0
    worst = None
    for k in range(720):
        a = float(S["alpha"][k])
        R = float(S["Rx"][k])
        key = (a, R)
        if key in seen:
            continue
        seen.add(key)
        Y_pscad = S["Y_send"][k]
        Y_cf = Y_send(a, R, OMEGA)
        # Per-entry relative magnitude error
        denom = np.maximum(np.abs(Y_pscad), 1e-15)
        rel = np.abs(np.abs(Y_cf) - np.abs(Y_pscad)) / denom
        rel_max = float(rel.max())
        if rel_max > max_rel_err:
            max_rel_err = rel_max
            worst = (a, R, rel)
        assert rel_max < TOLERANCE, (
            f"cell (alpha={a}, Rx={R}): max per-entry rel error "
            f"= {rel_max:.4e} >= {TOLERANCE}"
        )
    # Sanity: 45 unique (alpha, R_x) cells in the noiseless physics.
    assert len(seen) == 45
    print(
        f"\nWP3.1 closed-form vs PSCAD-surrogate: max per-entry rel err "
        f"across 45 cells = {max_rel_err:.4e} (worst at {worst[:2]})"
    )


def test_3phase_closed_form_phase_imbalance_visible() -> None:
    """Sanity: SLG-on-A makes Y_aa noticeably larger than Y_bb / Y_cc
    for the small-R_x (hard-fault) cells in the bundle.  This
    documents the canonical SLG signature in the 3x3 Y_send."""
    S = _load_pscad_3ph_bundle()
    # Pick the smallest-R_x cells (hardest faults).
    hard_mask = S["Rx"] == S["Rx"].min()
    seen: set[tuple[float, float]] = set()
    for k in np.where(hard_mask)[0]:
        a = float(S["alpha"][k])
        R = float(S["Rx"][k])
        key = (a, R)
        if key in seen:
            continue
        seen.add(key)
        Y = S["Y_send"][k]
        # Y_aa should be at least 1.5x Y_bb (and Y_cc) at R_x = 100 ohm.
        assert abs(Y[0, 0]) > 1.5 * abs(Y[1, 1]), (
            f"cell (alpha={a}, Rx={R}): Y_aa={abs(Y[0, 0]):.3e} "
            f"not >= 1.5x Y_bb={abs(Y[1, 1]):.3e}"
        )
        assert abs(Y[0, 0]) > 1.5 * abs(Y[2, 2]), (
            f"cell (alpha={a}, Rx={R}): Y_aa={abs(Y[0, 0]):.3e} "
            f"not >= 1.5x Y_cc={abs(Y[2, 2]):.3e}"
        )
