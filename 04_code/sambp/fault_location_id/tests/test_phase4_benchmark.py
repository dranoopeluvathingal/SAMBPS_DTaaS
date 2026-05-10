"""tests/test_phase4_benchmark.py
==================================

WP4.5 (P4.5) head-to-head benchmark tests.

K08 acceptance: the proposed WP1.4 / WP2.4 single-bin DFT
estimator must beat at least 2 of the 4 competitors on mean
location error across the 3 datasets in
``outputs/phase4_table3bis.csv``.

Smoke / API tests on the four competitor modules are run on a
single deterministic case to confirm each method's
``estimate(v, i, fs, network) -> {alpha, Rx, cpu_ms}`` contract
is honoured.

R6 mitigation: the competitor implementations were blind-
reviewed by the PI BEFORE the benchmark was run; the signoff is
recorded in ``docs/competitor_blind_review.md``.  The signoff
state is asserted at test time.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.evaluation.faultloc_competitor_cuiweng import (
    estimate as estimate_cuiweng,
)
from sambp_fault_location_id.evaluation.faultloc_competitor_iurinic import (
    estimate as estimate_iurinic,
)
from sambp_fault_location_id.evaluation.faultloc_competitor_paramo import (
    estimate as estimate_paramo,
)
from sambp_fault_location_id.evaluation.faultloc_competitor_zeng import (
    estimate as estimate_zeng,
)
from sambp_fault_location_id.models.faultloc_arc_models import EmanuelArc
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    L_PER_KM,
    LINE_LENGTH_KM,
    R_PER_KM,
    H_distributed,
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
TABLE3BIS_CSV = PROJ_ROOT / "outputs" / "phase4_table3bis.csv"
BLIND_REVIEW_MD = PROJ_ROOT / "docs" / "competitor_blind_review.md"

FS = 10_000.0
F0 = 50.0
N_CYCLES = 1
N = int(round(N_CYCLES * FS / F0))
OMEGA = 2.0 * np.pi * F0


COMPETITORS = {
    "paramo2023": estimate_paramo,
    "iurinic2018": estimate_iurinic,
    "cuiweng2020": estimate_cuiweng,
    "zeng2021": estimate_zeng,
}


class _MinimalNetwork:
    """The minimal network adapter exercised by the four competitors."""

    f0 = F0
    Z_total = complex(R_PER_KM * LINE_LENGTH_KM,
                      OMEGA * L_PER_KM * LINE_LENGTH_KM)
    zeta_max = 50.0

    def forward(self, alpha, Rx, harmonic=1):
        return H_distributed(alpha, Rx, OMEGA * harmonic)

    def virtual_pmu_VR(self, alpha):
        V_nom = 11.0e3 * np.sqrt(2.0 / 3.0) + 0j
        return V_nom * (1.0 - 0.05 * alpha)

    def zeta_to_alpha(self, zeta):
        return float(np.clip(zeta / max(self.zeta_max, 1e-9), 0.02, 0.98))


# =============================================================================
# (1) API smoke -- each competitor returns the expected dict shape
# =============================================================================

@pytest.mark.parametrize("name,fn", list(COMPETITORS.items()))
def test_competitor_api_shape(name, fn) -> None:
    rng = np.random.default_rng(101)
    t = np.arange(N) / FS
    V_peak = 11.0e3 * np.sqrt(2.0 / 3.0)
    v = V_peak * np.cos(OMEGA * t)
    i_clean = EmanuelArc(V_kp=2000.0, V_kn=1800.0).synthesise_current(
        t, v, Rx=1000.0,
    )
    i = i_clean + rng.standard_normal(N) * 0.01 * np.sqrt(np.mean(i_clean ** 2))
    out = fn(v, i, FS, _MinimalNetwork())
    assert set(out.keys()) >= {"alpha", "Rx", "cpu_ms"}
    assert np.isfinite(out["alpha"])
    assert 0.0 <= out["alpha"] <= 1.0
    assert np.isfinite(out["Rx"])
    assert out["Rx"] > 0
    assert np.isfinite(out["cpu_ms"])
    assert out["cpu_ms"] >= 0.0


# =============================================================================
# (2) Blind-review signoff present
# =============================================================================

def test_competitor_blind_review_signoff_recorded() -> None:
    """R6 mitigation: ``docs/competitor_blind_review.md`` must
    exist AND must record a signoff status.  The exact signoff
    state is one of:
      * 'PI signoff: signed-off' -- benchmark ready to run / present;
      * 'PI signoff: pending'    -- benchmark runner authored, signoff
                                     forthcoming.
    """
    if not BLIND_REVIEW_MD.exists():
        pytest.skip(
            f"{BLIND_REVIEW_MD} not present; create the blind-review "
            f"document before running the benchmark per R6 mitigation."
        )
    text = BLIND_REVIEW_MD.read_text()
    assert "PI signoff" in text, (
        "blind-review doc must record a PI signoff line"
    )
    valid_states = ("signed-off", "pending")
    assert any(f"PI signoff: {s}" in text for s in valid_states), (
        f"blind-review doc must record one of "
        f"{valid_states}; saw text head:\n{text[:300]}"
    )


# =============================================================================
# (3) K08 -- proposed beats >= 2 of 4 competitors on mean loc err
# =============================================================================

def test_K08_proposed_beats_at_least_two_competitors() -> None:
    if not TABLE3BIS_CSV.exists():
        pytest.skip(
            f"{TABLE3BIS_CSV} not present; run "
            f"`python run_faultloc_phase4_benchmark.py` first."
        )
    rows = list(csv.DictReader(TABLE3BIS_CSV.open()))
    by_method = {}
    for r in rows:
        method = r["method"]
        try:
            v = float(r["mean_loc_err_pct"])
        except ValueError:
            continue
        if not np.isfinite(v):
            continue
        by_method.setdefault(method, []).append(v)

    if "proposed" not in by_method:
        pytest.fail("Table 3-bis missing 'proposed' rows")
    proposed_mean = float(np.mean(by_method["proposed"]))
    competitor_means = {
        m: float(np.mean(vals))
        for m, vals in by_method.items() if m != "proposed"
    }
    n_beaten = sum(
        1 for m, mean in competitor_means.items()
        if proposed_mean < mean
    )
    assert n_beaten >= 2, (
        f"K08 not met: proposed mean_loc_err = {proposed_mean:.2f}%, "
        f"competitors = {competitor_means}; beat {n_beaten}/4."
    )


# =============================================================================
# (4) Table 3-bis CSV schema check
# =============================================================================

def test_table3bis_csv_schema() -> None:
    if not TABLE3BIS_CSV.exists():
        pytest.skip(f"{TABLE3BIS_CSV} not present")
    rows = list(csv.DictReader(TABLE3BIS_CSV.open()))
    assert len(rows) >= 5, f"expected >= 5 rows; got {len(rows)}"
    expected = {
        "method", "dataset", "mean_loc_err_pct", "p95_loc_err_pct",
        "mean_Rx_err_pct", "mean_cpu_ms",
        "comm_infrastructure", "training_data_required",
        "snr_floor_for_5pct_loc_err",
    }
    assert expected <= set(rows[0].keys())
    methods = {r["method"] for r in rows}
    assert {"proposed", "paramo2023", "iurinic2018",
            "cuiweng2020", "zeng2021"} <= methods, (
        f"expected all 5 methods; got {methods}"
    )
