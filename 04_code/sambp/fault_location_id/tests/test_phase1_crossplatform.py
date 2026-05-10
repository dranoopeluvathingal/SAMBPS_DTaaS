"""tests/test_phase1_crossplatform.py
========================================

WP1.4 cross-platform optimiser re-run acceptance.

Loads ``outputs/phase1_crossplatform_results.csv`` (produced by
``run_faultloc_phase1_crossplatform.py``) and asserts the v3 plan's
D1 / T-B1 thresholds:

    mean location error < 2 % at SNR_I >= 30 dB across all 3 datasets
    max  location error < 5 % at SNR_I >= 30 dB across all 3 datasets

Per-cell 95 % CI coverage is informational only at this point;
canonical Monte-Carlo CI lives in WP1.5 / P1.5.

# TODO Phase1 single-bin DFT identifiability
# ------------------------------------------
# Empirically (this commit), with the P0.5 Cascaded-Gamma 2-section
# optimiser running on the three independent waveform sets:
#
#                   noiseless (SNR_V=SNR_I=Inf, 45 cells per dataset):
#     pscad / emtp / ref50:  ~19 % mean loc_err  (model-mismatch driven)
#     self_consistent     :  ~0.005 % mean loc_err
#
#                   high-SNR (SNR_V & SNR_I >= 30 dB, 405 cells):
#     pscad / emtp / ref50:  23-25 % mean loc_err
#     self_consistent     :  ~13 %    mean loc_err  (noise x conditioning)
#
# Two distinct failure modes are revealed:
#
#   (a) Forward-model mismatch.  Although the H magnitude difference
#       between the Cascaded-Gamma 2-section and the distributed-
#       parameter / 50-section reference is < 1 % (P1.3 finding), the
#       inverse-problem ill-conditioning amplifies that into ~19 %
#       loc-error on PSCAD/EMTP/ref50 data.  Closes when WP2.1 lands
#       the closed-form distributed-parameter forward model that
#       MATCHES the data-generating physics.
#
#   (b) Noise x conditioning amplification.  Even on self-consistent
#       data the noiseless cells recover (a, R_x) to 0.005 %, but
#       cells with even mild noise (SNR_I = 30-40 dB on V or I)
#       blow up to 13 %+.  The single complex H bin has 2 real DOF
#       for 2 unknowns, but the cost surface is near-degenerate over
#       a curve in (alpha, R_x) space (manifestation of the v3 §3.13
#       "near-source alpha < 0.2 floor" extended to all alpha under
#       finite SNR).  Closes when WP1.6 lands the corrected
#       proper-complex-Gaussian-ratio CRLB and WP3.5/3.6 add the
#       Taylor-Fourier multi-bin estimator and multi-port FIM.
#
# Per the WP1.4 brief, this failure is *escalated* (R1) - do not auto-
# fix.  Both tests are MARKED `pytest.mark.xfail(strict=False)` with
# a reason linking to this TODO; the test runs to completion in CI
# and surfaces the discrepancy without breaking the build.  Remove
# the xfail markers once WP2.1 (closed-form distributed-parameter)
# and WP1.6 (corrected CRLB) bring the cross-platform mean below
# the 2 % D1 threshold.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

PROJ_ROOT = Path(__file__).resolve().parent.parent
RESULTS_CSV = PROJ_ROOT / "outputs" / "phase1_crossplatform_results.csv"

DATASETS_REQUIRED = {"pscad", "emtp", "ref50"}


def _load_rows() -> list[dict]:
    if not RESULTS_CSV.exists():
        pytest.skip(
            f"{RESULTS_CSV} not present; run "
            f"`.venv/bin/python run_faultloc_phase1_crossplatform.py` first."
        )
    return list(csv.DictReader(RESULTS_CSV.open()))


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return _load_rows()


@pytest.fixture(scope="module")
def per_dataset(rows: list[dict]) -> dict[str, dict]:
    """Returns {dataset: {snrI, loc, Rx}} arrays."""
    out: dict[str, dict] = {}
    for ds in DATASETS_REQUIRED | {"self_consistent"}:
        sub = [r for r in rows if r["dataset"] == ds]
        out[ds] = {
            "snrI": np.array([float(r["snrI"]) for r in sub]),
            "loc": np.array([float(r["loc_err_pct"]) for r in sub]),
            "Rx": np.array([float(r["Rx_err_pct"]) for r in sub]),
            "n": len(sub),
        }
    return out


def _high_snrI_mask(snrI: np.ndarray) -> np.ndarray:
    return (snrI >= 30) | ~np.isfinite(snrI)


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Phase1 single-bin DFT identifiability.  Cascaded-Gamma 2-section "
        "optimiser cannot achieve <2 % mean loc-err on PSCAD/EMTP/ref50 "
        "data: noiseless model-mismatch ~19 %, high-SNR ~23-25 %.  Two "
        "drivers: forward-model mismatch (closes at WP2.1 closed-form "
        "distributed-parameter) and noise x cost-surface ill-conditioning "
        "(closes at WP1.6 corrected CRLB + WP3.5/3.6 Taylor-Fourier + "
        "multi-port FIM).  Self_consistent confirms optimiser is sound "
        "(0.005 % noiseless).  See TODO Phase1 in this test file's "
        "docstring; remove this xfail once WP1.6 + WP2.1 land."
    ),
)
@pytest.mark.parametrize("dataset", sorted(DATASETS_REQUIRED))
def test_mean_loc_err_below_2pct_high_snrI(
    per_dataset: dict[str, dict], dataset: str
) -> None:
    d = per_dataset[dataset]
    sel = _high_snrI_mask(d["snrI"])
    mean_pct = float(d["loc"][sel].mean())
    assert mean_pct < 2.0, (
        f"{dataset}: mean loc-err = {mean_pct:.3f} % at SNR_I>=30dB "
        f"across {int(sel.sum())} cells (>= 2 % D1 threshold)"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Phase1 single-bin DFT identifiability.  See companion mean-err "
        "test above for full diagnosis.  Max loc-err is dominated by "
        "the same model-mismatch + noise x conditioning amplification."
    ),
)
@pytest.mark.parametrize("dataset", sorted(DATASETS_REQUIRED))
def test_max_loc_err_below_5pct_high_snrI(
    per_dataset: dict[str, dict], dataset: str
) -> None:
    d = per_dataset[dataset]
    sel = _high_snrI_mask(d["snrI"])
    max_pct = float(d["loc"][sel].max())
    assert max_pct < 5.0, (
        f"{dataset}: max loc-err = {max_pct:.3f} % at SNR_I>=30dB "
        f"across {int(sel.sum())} cells (>= 5 % D1 threshold)"
    )


def test_self_consistent_passes_d1_thresholds(
    per_dataset: dict[str, dict],
) -> None:
    """Companion check: self-consistent baseline DOES meet D1 on
    noiseless cells (0.005 % mean), confirming the optimiser is
    sound and the failure modes above are model-mismatch and
    noise x conditioning, not optimiser bugs.  Only enforced on
    the noiseless subset because even self-consistent shows noise x
    conditioning amplification at finite SNR (see TODO)."""
    d = per_dataset["self_consistent"]
    snrV = np.array(
        [float(r["snrV"])
         for r in _load_rows() if r["dataset"] == "self_consistent"]
    )
    nl = ~np.isfinite(snrV) & ~np.isfinite(d["snrI"])
    assert nl.sum() == 45, f"expected 45 noiseless cells, got {int(nl.sum())}"
    mean_pct = float(d["loc"][nl].mean())
    max_pct = float(d["loc"][nl].max())
    assert mean_pct < 0.1, (
        f"self_consistent noiseless mean loc-err = {mean_pct:.4f} %, "
        f"expected < 0.1 % - if this fails the optimiser itself has "
        f"a bug, investigate before WP1.6"
    )
    assert max_pct < 0.5, (
        f"self_consistent noiseless max loc-err = {max_pct:.4f} %, "
        f"expected < 0.5 %"
    )


def test_phase1_csv_schema(rows: list[dict]) -> None:
    """Schema check: 4 datasets x 720 cells = 2880 rows; all columns
    populated."""
    assert len(rows) == 2880, f"expected 2880 rows, got {len(rows)}"
    expected_cols = {
        "dataset", "cell", "alpha", "Rx", "snrV", "snrI",
        "loc_err_pct", "Rx_err_pct", "J_final", "n_iters", "cpu_ms",
    }
    assert set(rows[0].keys()) == expected_cols
    datasets = {r["dataset"] for r in rows}
    assert datasets == {"pscad", "emtp", "ref50", "self_consistent"}
    for ds in datasets:
        assert sum(1 for r in rows if r["dataset"] == ds) == 720
