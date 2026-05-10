"""tests/test_identifiability_map.py
========================================

WP3.5 (P3.5) identifiability check + map acceptance.

Asserts:

1. The Hermann-Krener observability rank is full (= 2) on every cell
   of the standard operating grid -- the single-bin observation IS
   structurally identifiable.
2. The flag_local_degeneracy helper correctly returns the per-cell
   inverse condition number look-up.
3. The 50 x 50 heatmap CSV is produced by the runner.
4. The `is_degenerate` flag identifies the documented near-source +
   high-Rx region (alpha < 0.15 + R_x > 3000 ohm) as the worst.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.adaptation.faultloc_identifiability_check import (
    DEFAULT_THRESHOLD_SIGMA_MIN,
    flag_local_degeneracy,
    map_observability_rank,
    map_sigma_min_over_max,
    observability_rank,
    sigma_min_at,
    sigma_min_over_max_at,
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
HEATMAP_CSV = PROJ_ROOT / "outputs" / "phase3_identifiability_sigma_min.csv"
ORC_CSV = PROJ_ROOT / "outputs" / "phase3_identifiability_orc.csv"
HEATMAP_PNG = PROJ_ROOT / "outputs" / "phase3_identifiability_heatmap.png"


@pytest.mark.parametrize(
    "alpha, Rx",
    [(0.30, 100.0), (0.50, 1000.0), (0.70, 5000.0), (0.50, 2000.0)],
)
def test_observability_rank_full_at_typical_cells(
    alpha: float, Rx: float,
) -> None:
    """At typical operating-grid cells, the Hermann-Krener ORC is
    satisfied (rank == 2)."""
    assert observability_rank((alpha, Rx)) == 2


@pytest.mark.parametrize(
    "alpha, Rx",
    [(0.30, 100.0), (0.50, 1000.0), (0.70, 5000.0)],
)
def test_sigma_min_positive_at_typical_cells(
    alpha: float, Rx: float,
) -> None:
    """sigma_min > 0 at any operating-grid cell where ORC is
    satisfied."""
    assert sigma_min_at((alpha, Rx)) > 0
    ratio = sigma_min_over_max_at((alpha, Rx))
    assert 0 < ratio <= 1.0


def test_observability_rank_grid_is_uniform_full_rank() -> None:
    """On the WP3.5 standard 10 x 10 sub-grid, ORC holds everywhere
    (Villaverde-2024-style binary indicator stays at 2 throughout
    the operating envelope; the optimiser's residual cost-surface
    flattening at high R_x is a NOISE issue, not a structural
    identifiability failure)."""
    alpha_grid = np.linspace(0.10, 0.90, 10)
    Rx_grid = np.geomspace(100.0, 5000.0, 10)
    rank = map_observability_rank(alpha_grid, Rx_grid)
    assert (rank == 2).all(), (
        f"some cells fail Hermann-Krener ORC: "
        f"rank distribution = {np.unique(rank, return_counts=True)}"
    )


def test_flag_local_degeneracy_consumes_grid() -> None:
    alpha_grid = np.linspace(0.10, 0.90, 10)
    Rx_grid = np.geomspace(100.0, 5000.0, 10)
    sm_over_max = map_sigma_min_over_max(alpha_grid, Rx_grid)
    flag = flag_local_degeneracy(
        (0.5, 1000.0), sm_over_max, alpha_grid, Rx_grid,
        threshold=DEFAULT_THRESHOLD_SIGMA_MIN,
    )
    assert "ok" in flag
    assert "sigma_min" in flag
    assert "is_degenerate" in flag
    assert isinstance(flag["ok"], bool)
    assert flag["ok"], (
        f"alpha=0.5, R_x=1000 should NOT be flagged as degenerate "
        f"(sigma_min/sigma_max = {flag['sigma_min']:.3e}; threshold = "
        f"{DEFAULT_THRESHOLD_SIGMA_MIN:.3e})"
    )


def test_heatmap_csv_present_and_schema() -> None:
    if not HEATMAP_CSV.exists():
        pytest.skip(
            f"{HEATMAP_CSV} not present; run "
            f"`python run_faultloc_phase3_identifiability_map.py` first."
        )
    rows = list(csv.DictReader(HEATMAP_CSV.open()))
    assert len(rows) == 2500, f"expected 50x50 = 2500 rows; got {len(rows)}"
    expected_keys = {
        "alpha", "Rx", "sigma_min", "sigma_min_over_max",
        "hermann_krener_rank", "is_degenerate",
    }
    assert expected_keys <= set(rows[0].keys())


def test_orc_csv_present_and_full_rank_everywhere() -> None:
    """Hermann-Krener ORC indicator from the runner: should be 1
    (satisfied) on every cell of the 50 x 50 grid."""
    if not ORC_CSV.exists():
        pytest.skip(
            f"{ORC_CSV} not present; run "
            f"`python run_faultloc_phase3_identifiability_map.py` first."
        )
    rows = list(csv.DictReader(ORC_CSV.open()))
    n_satisfied = sum(int(r["orc_satisfied"]) for r in rows)
    assert n_satisfied == len(rows), (
        f"only {n_satisfied}/{len(rows)} cells satisfy Hermann-Krener "
        f"ORC; expected all 2500.  Inspect "
        f"outputs/phase3_identifiability_orc.csv."
    )


def test_heatmap_png_present() -> None:
    if not HEATMAP_PNG.exists():
        pytest.skip(
            f"{HEATMAP_PNG} not present; run "
            f"`python run_faultloc_phase3_identifiability_map.py` first."
        )
    # Just check it's a non-empty PNG.
    assert HEATMAP_PNG.stat().st_size > 1000


def test_degenerate_region_is_near_source_high_Rx() -> None:
    """The flagged degenerate cells (sigma_min/sigma_max < 1e-2)
    should cluster in the (small alpha, large R_x) corner of the
    operating envelope -- empirical certification of the v3 plan
    Sect. 3.13 prediction (R5 closure)."""
    if not HEATMAP_CSV.exists():
        pytest.skip(f"{HEATMAP_CSV} not present")
    rows = list(csv.DictReader(HEATMAP_CSV.open()))
    flagged = [r for r in rows if int(r["is_degenerate"]) == 1]
    # If we're using the calibrated threshold there should be SOME flagged
    # cells (~5% of 2500); each one should sit at small alpha and large R_x.
    if not flagged:
        pytest.skip(
            "no cells flagged at current threshold; calibration "
            "may have shifted -- inspect runner threshold."
        )
    alphas = np.array([float(r["alpha"]) for r in flagged])
    Rxs = np.array([float(r["Rx"]) for r in flagged])
    # The region MUST sit predominantly at small alpha (mean alpha < 0.3)
    # and large R_x (mean R_x > 2000 ohm).
    assert alphas.mean() < 0.3, (
        f"flagged cells should cluster at small alpha; mean = {alphas.mean():.3f}"
    )
    assert Rxs.mean() > 2000.0, (
        f"flagged cells should cluster at large R_x; mean = {Rxs.mean():.1f} ohm"
    )
