"""tests/test_branched_vs_pscad.py
====================================

WP3.2 (P3.2) acceptance test:

    The closed-form branched 3-phase Y_send from
    `models/faultloc_three_phase_model.Network.Y_send` (look-back
    admittance reduction with single-matrix-exponential line ABCD per
    segment) must agree with the PSCAD-equivalent surrogate from
    `tools/pscad_surrogate_3ph_branched.Y_send_branched_pi_surrogate`
    (same `Network` reduction with a 50-sections-per-segment lumped-pi
    line ABCD) to within 5 % on every entry of the 3x3 Y_send matrix
    at every (alpha, R_x, fault_branch) cell of the 1440-grid noiseless
    slice.

Why these two pathways are independent
--------------------------------------

The closed-form pathway evaluates each uniform line segment ABCD as
``scipy.linalg.expm(L * M_pde_neg)`` where M_pde_neg is the 6x6
system matrix.  The surrogate pathway evaluates each segment as a
cascade of 50 LUMPED-pi 6x6 ABCD matrices of length L_segment / 50.

In the limit n_sections -> infinity the two agree to floating-point
precision; at n_sections = 50 per segment on the WP3.2 topology
(main: 100 km in two sub-sections at the tap; lateral: 20 km in
three sub-sections at DG and tap-load) the per-segment discretisation
residual is ~10 ppm which lifts through the look-back reduction to
~50-200 ppm on the worst Y_send entries.  The 5 % tolerance gives
3-4 orders of magnitude margin.

When the canonical PSCAD output replaces the surrogate (lead
engineer's licensed Windows station), this test compares the
closed-form against PSCAD's J. Marti FD line model directly with the
same 5 % tolerance; the PSCAD agreement is then a real cross-platform
check rather than the dev-box surrogate self-consistency check.

Lateral fault-on-branch case
----------------------------

The brief explicitly requires "lateral fault-on-branch case
validated".  The 1440-grid contains 720 cells with ``fault_branch
== 'lateral'``; this test asserts the 5 % tolerance on every one of
them (collapsed to 45 unique (alpha, R_x) cells).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.models.faultloc_three_phase_model import Network
from scipy.io import loadmat

PROJ_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJ_ROOT / "data" / "pscad_branched_720.mat"

OMEGA = 2.0 * np.pi * 50.0
TOLERANCE = 0.05  # 5 % per WP3.2 brief acceptance


def _load_pscad_branched_bundle():
    if not DATA_PATH.exists():
        pytest.skip(
            f"{DATA_PATH} not present; run "
            f"`python tools/pscad_surrogate_3ph_branched.py` to bootstrap."
        )
    S = loadmat(str(DATA_PATH))
    fb = S["grid_fault_branch"].squeeze()
    fb_list = [str(x).strip() for x in fb]
    return {
        "Y_send": S["Y_send"],
        "alpha": S["grid_alpha"].squeeze(),
        "Rx": S["grid_Rx"].squeeze(),
        "snrV": S["grid_SNR_V"].squeeze(),
        "snrI": S["grid_SNR_I"].squeeze(),
        "fault_branch": fb_list,
    }


def test_pscad_branched_bundle_schema() -> None:
    """Schema check for the WP3.2 branched bundle."""
    S = _load_pscad_branched_bundle()
    assert S["Y_send"].shape == (1440, 3, 3)
    assert S["Y_send"].dtype == complex
    assert S["alpha"].shape == (1440,)
    assert S["Rx"].shape == (1440,)
    assert S["snrV"].shape == (1440,)
    assert S["snrI"].shape == (1440,)
    assert len(S["fault_branch"]) == 1440
    assert set(S["fault_branch"]) == {"main", "lateral"}
    assert np.all(np.isfinite(S["Y_send"]))


def test_branched_closed_form_agrees_with_pscad_surrogate_5pct() -> None:
    """Per-entry magnitude agreement < 5 % on every (alpha, R_x,
    fault_branch) cell of the 1440-grid (90 unique cells)."""
    S = _load_pscad_branched_bundle()
    network = Network()
    seen: set[tuple[float, float, str]] = set()
    max_rel_err = 0.0
    worst = None
    n_main = 0
    n_lateral = 0
    for k in range(S["Y_send"].shape[0]):
        a = float(S["alpha"][k])
        R = float(S["Rx"][k])
        fb = S["fault_branch"][k]
        key = (a, R, fb)
        if key in seen:
            continue
        seen.add(key)
        if fb == "main":
            n_main += 1
        else:
            n_lateral += 1
        Y_pscad = S["Y_send"][k]
        Y_cf = network.Y_send(
            OMEGA, alpha=a, Rx=R, fault_branch=fb,
        )
        denom = np.maximum(np.abs(Y_pscad), 1e-15)
        rel = np.abs(np.abs(Y_cf) - np.abs(Y_pscad)) / denom
        rel_max = float(rel.max())
        if rel_max > max_rel_err:
            max_rel_err = rel_max
            worst = (a, R, fb)
        assert rel_max < TOLERANCE, (
            f"cell (alpha={a}, Rx={R}, fault_branch={fb}): "
            f"max per-entry rel err = {rel_max:.4e} >= {TOLERANCE}"
        )
    assert len(seen) == 90, f"expected 90 unique (a, R, fb) cells; got {len(seen)}"
    assert n_main == 45, f"expected 45 main-fault cells; got {n_main}"
    assert n_lateral == 45, (
        f"expected 45 lateral-fault cells; got {n_lateral}"
    )
    print(
        f"\nWP3.2 closed-form vs PSCAD-surrogate-branched: max per-entry "
        f"rel err across {len(seen)} cells = {max_rel_err:.4e} (worst at "
        f"{worst})"
    )


def test_lateral_fault_changes_Y_send_vs_main_fault() -> None:
    """Sanity: at the same (alpha, R_x) the lateral-fault Y_send is
    DIFFERENT from the main-fault Y_send.  This certifies the
    `fault_branch` axis is wired through the network reduction (not a
    silent no-op)."""
    network = Network()
    Y_main = network.Y_send(OMEGA, alpha=0.3, Rx=1000.0, fault_branch="main")
    Y_lat = network.Y_send(OMEGA, alpha=0.3, Rx=1000.0, fault_branch="lateral")
    rel = np.abs(np.abs(Y_main) - np.abs(Y_lat)) / np.maximum(
        np.abs(Y_main), 1e-15
    )
    # At alpha=0.3 the main-fault sits between sender and tap; the
    # lateral-fault sits between tap and DG.  Per-entry difference
    # should be observable above floating-point noise on at least the
    # diagonal Y_aa entry.
    assert rel[0, 0] > 1e-6, (
        f"Y_aa is identical between main and lateral fault at the same "
        f"(alpha, R_x): rel diff = {rel[0, 0]:.3e}; check fault_branch "
        f"is wired through the network reduction."
    )


def test_no_fault_baseline_independent_of_fault_branch() -> None:
    """As R_x -> infinity the fault becomes invisible; the resulting
    no-fault baseline Y_send must NOT depend on which `fault_branch`
    the (irrelevant) fault was placed on."""
    network = Network()
    Y_main = network.Y_send(
        OMEGA, alpha=0.3, Rx=1.0e12, fault_branch="main",
    )
    Y_lat = network.Y_send(
        OMEGA, alpha=0.3, Rx=1.0e12, fault_branch="lateral",
    )
    np.testing.assert_allclose(Y_main, Y_lat, rtol=1e-6)


def test_network_constructor_validation() -> None:
    """Sanity: bad parameter ranges raise ValueError at construction."""
    with pytest.raises(ValueError, match="tap_position"):
        Network(tap_position=0.0)
    with pytest.raises(ValueError, match="tap_position"):
        Network(tap_position=1.5)
    with pytest.raises(ValueError, match="dg_position"):
        Network(dg_position=-0.1)
    with pytest.raises(ValueError, match="line lengths"):
        Network(main_length_km=0.0)


def test_network_Y_send_validation() -> None:
    """Sanity: bad runtime arguments raise ValueError."""
    network = Network()
    with pytest.raises(ValueError, match="alpha"):
        network.Y_send(OMEGA, alpha=0.0, Rx=1000.0)
    with pytest.raises(ValueError, match="Rx"):
        network.Y_send(OMEGA, alpha=0.5, Rx=-1.0)
    with pytest.raises(ValueError, match="fault_branch"):
        network.Y_send(OMEGA, alpha=0.5, Rx=1000.0, fault_branch="other")
    with pytest.raises(ValueError, match="fault_phase"):
        network.Y_send(OMEGA, alpha=0.5, Rx=1000.0, fault_phase=3)
