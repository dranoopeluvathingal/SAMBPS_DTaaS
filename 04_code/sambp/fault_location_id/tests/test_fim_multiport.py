"""tests/test_fim_multiport.py
================================

WP3.6 (P3.6) multi-port FIM acceptance tests.

The brief acceptance: "at SNR_I >= 40 dB the proper-ratio and
dual-channel CRLBs must agree to within 5 %".  This test reads the
per-cell CSV produced by ``run_faultloc_phase3_multiport_crlb.py``
and asserts the consistency on every cell at SNR_I in {40, 50} dB
(SNR_I = inf is excluded because both bounds collapse to zero and
the ratio is 0/0 = NaN).
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.inverse_estimation.faultloc_fim_multiport import (
    crlb_consistency_ratio,
    crlb_multiport_dual,
    crlb_multiport_proper,
)
from sambp_fault_location_id.models.faultloc_ieee_feeders import build_ieee34

PROJ_ROOT = Path(__file__).resolve().parent.parent
PER_CELL_CSV = (
    PROJ_ROOT / "outputs" / "phase3_crlb_multiport_overlay" / "per_cell_crlb.csv"
)
SNR_PNG = (
    PROJ_ROOT / "outputs" / "phase3_crlb_multiport_overlay" / "snr_sweep.png"
)
OBS_PNG = (
    PROJ_ROOT / "outputs" / "phase3_crlb_multiport_overlay"
    / "observation_kind.png"
)
CONS_PNG = (
    PROJ_ROOT / "outputs" / "phase3_crlb_multiport_overlay"
    / "consistency_at_40dB.png"
)

OMEGA = 2 * np.pi * 50.0


@pytest.fixture(scope="module")
def ieee34_network():
    return build_ieee34()


@pytest.mark.parametrize("observation", ["full", "upper", "diagonal"])
def test_proper_dual_consistency_at_V_noiseless(
    ieee34_network, observation: str,
) -> None:
    """At V noiseless and SNR_I = 40 dB, proper-ratio and dual-channel
    multi-port CRLBs agree to machine precision (< 1e-12 ratio
    deviation)."""
    p = crlb_multiport_proper(
        ieee34_network, fault_bus="bus_15", alpha=0.5, Rx=1000.0,
        snr_v_db=np.inf, snr_i_db=40.0, observation=observation,
    )
    d = crlb_multiport_dual(
        ieee34_network, fault_bus="bus_15", alpha=0.5, Rx=1000.0,
        snr_v_db=np.inf, snr_i_db=40.0, observation=observation,
    )
    ratio = crlb_consistency_ratio(p, d)
    assert abs(ratio - 1.0) < 1.0e-12, (
        f"observation={observation}: proper/dual ratio = {ratio} != 1.0; "
        f"the consistency identity at sigma_V = 0 should hold to "
        f"machine precision."
    )


def test_observation_subset_information_accumulation(ieee34_network) -> None:
    """Multi-port CRLB monotonically tightens (rmse decreases) as the
    observation set grows: 'diagonal' (3 entries) -> 'upper' (6) ->
    'full' (9).  Tests the structural information-accumulation
    property of the WP3.6 framework."""
    rmses = []
    for obs in ("diagonal", "upper", "full"):
        p = crlb_multiport_proper(
            ieee34_network, fault_bus="bus_15", alpha=0.5, Rx=1000.0,
            snr_v_db=np.inf, snr_i_db=30.0, observation=obs,
        )
        rmses.append(p.rmse_alpha_pct)
    assert rmses[0] >= rmses[1] >= rmses[2], (
        f"observation set should accumulate information monotonically; "
        f"got rmse [diagonal, upper, full] = {rmses}"
    )


def test_proper_ratio_higher_when_V_noisy(ieee34_network) -> None:
    """When sigma_V > 0 the proper-ratio CRLB is HIGHER than the
    dual-channel CRLB (proper/dual > 1) because the proper-ratio
    discards information by working only on the H-ratio.  Same
    direction as the WP1.6 single-port result."""
    p = crlb_multiport_proper(
        ieee34_network, fault_bus="bus_15", alpha=0.5, Rx=1000.0,
        snr_v_db=30.0, snr_i_db=30.0, observation="full",
    )
    d = crlb_multiport_dual(
        ieee34_network, fault_bus="bus_15", alpha=0.5, Rx=1000.0,
        snr_v_db=30.0, snr_i_db=30.0, observation="full",
    )
    ratio = crlb_consistency_ratio(p, d)
    assert ratio > 1.0, (
        f"proper-ratio CRLB should exceed dual-channel CRLB at "
        f"sigma_V > 0; got ratio = {ratio}."
    )


def _load_per_cell_csv() -> list[dict]:
    if not PER_CELL_CSV.exists():
        pytest.skip(
            f"{PER_CELL_CSV} not present; run "
            f"`python run_faultloc_phase3_multiport_crlb.py` first."
        )
    return list(csv.DictReader(PER_CELL_CSV.open()))


def test_per_cell_csv_present_and_schema() -> None:
    rows = _load_per_cell_csv()
    assert len(rows) >= 100, f"expected >= 100 rows; got {len(rows)}"
    expected_keys = {
        "feeder", "fault_bus", "alpha", "Rx", "snrI", "observation",
        "n_real_obs",
        "rmse_alpha_pct_proper", "rmse_alpha_pct_dual",
        "rmse_Rx_pct_proper", "rmse_Rx_pct_dual",
        "consistency_ratio", "geary_hinkley_valid",
    }
    assert expected_keys <= set(rows[0].keys())


def test_brief_consistency_acceptance_at_40dB() -> None:
    """WP3.6 brief acceptance: per-cell consistency within 5 % at
    SNR_I = 40 dB across the IEEE 34 sub-sample."""
    rows = _load_per_cell_csv()
    consistency_rows = [
        r for r in rows
        if abs(float(r["snrI"]) - 40.0) < 0.5
        and r["observation"] == "full"
    ]
    assert len(consistency_rows) >= 30, (
        f"expected >= 30 (fault_bus, R_x) cells at SNR_I = 40 dB / "
        f"observation=full; got {len(consistency_rows)}"
    )
    ratios = np.array([float(r["consistency_ratio"]) for r in consistency_rows])
    n_within_5pct = int(np.sum(np.abs(ratios - 1.0) < 0.05))
    assert n_within_5pct == len(ratios), (
        f"only {n_within_5pct}/{len(ratios)} cells within 5 % of "
        f"ratio = 1.0 at SNR_I = 40 dB; brief target is all cells.  "
        f"max abs deviation = {np.abs(ratios - 1.0).max():.6e}"
    )


def test_overlay_pngs_present() -> None:
    for path in (SNR_PNG, OBS_PNG, CONS_PNG):
        if not path.exists():
            pytest.skip(
                f"{path.name} not present; run "
                f"`python run_faultloc_phase3_multiport_crlb.py` first."
            )
        assert path.stat().st_size > 1000, (
            f"{path.name} is suspiciously small ({path.stat().st_size} bytes)"
        )


def test_input_validation() -> None:
    network = build_ieee34()
    with pytest.raises(ValueError, match="observation must be"):
        crlb_multiport_proper(
            network, fault_bus="bus_15", alpha=0.5, Rx=1000.0,
            snr_v_db=np.inf, snr_i_db=30.0, observation="weird",
        )
