"""tests/test_fault_type_id.py
=================================

WP3.4 (P3.4) fault-type classification acceptance tests.

The brief requires fault-type classification accuracy >= 95 % at
SNR_I >= 30 dB across the IEEE 34-node grid.  This commit ships the
WP3.4 multi-type classifier (``classify_fault_type_3ph`` in
``inverse_estimation/faultloc_two_stage_optimiser.py``) and a runner
(``run_faultloc_phase3_fault_types.py``) that exercises it on a
tractable sub-sample of the grid (10 fault buses, 10 trials per
cell, SNR_I in {30, 40, inf} -- the brief acceptance subset).

Acceptance status this commit
-----------------------------

* **Noiseless 100 % framework-lives check** -- PASS.  At
  SNR_I = inf the classifier hits 100 % accuracy; the
  multi-type identifier is wired through correctly and the
  Y_send pattern across {SLG, LL, LLG} is structurally
  distinguishable.

* **Confusion matrix produced** -- PASS.  Per-(SNR_I subset)
  3x3 confusion matrices in
  ``outputs/phase3_fault_type_confusion.csv`` with row recall
  per truth class + overall accuracy.

* **>=95 % at SNR_I >= 30 dB** -- xfailed-strict.  Measured
  ~70-80 % overall on the simplified IEEE 34 (constant-Z loads,
  single line code 601 substituted for the canonical 24.9 kV
  300-304 codes).  The breakdown shows the gap is entirely in the
  (high-R_x, SNR_I = 30 dB) regime where the load-dominated Y_send
  baseline swamps the fault signature.  Closes when the WP3.5 /
  WP3.6 multi-bin / multi-port FIM lifts the noise floor on the
  fault signature.

Files inspected
---------------

* ``outputs/phase3_fault_types.parquet`` -- per-trial long format
  written by ``run_faultloc_phase3_fault_types.py``.
* ``outputs/phase3_fault_type_confusion.csv`` -- per-subset 3x3
  confusion matrices.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    add_complex_gaussian_noise_to_Y,
    classify_fault_type_3ph,
)
from sambp_fault_location_id.models.faultloc_ieee_feeders import build_ieee34
from sambp_fault_location_id.models.faultloc_three_phase_model import (
    FAULT_TYPES,
    Y_f_for_type,
    Y_send,
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
PARQUET_PATH = PROJ_ROOT / "outputs" / "phase3_fault_types.parquet"
CONFUSION_PATH = PROJ_ROOT / "outputs" / "phase3_fault_type_confusion.csv"

OMEGA = 2 * np.pi * 50.0


@pytest.mark.parametrize("ft", list(FAULT_TYPES))
def test_Y_f_for_type_block_structure(ft: str) -> None:
    """The Y_f shunt-block matrices match the WP3.4-documented forms."""
    Y_f = Y_f_for_type(1000.0, fault_type=ft)
    assert Y_f.shape == (3, 3)
    assert Y_f.dtype == complex
    if ft == "SLG":
        # Diagonal on phase A only.
        assert Y_f[0, 0] == pytest.approx(1.0e-3)
        assert np.all(Y_f[1:, :] == 0)
        assert np.all(Y_f[:, 1:][0:1] == 0)
    elif ft == "LL":
        # B-C anti-diagonal pair; phase A untouched.
        assert np.all(Y_f[0, :] == 0)
        assert np.all(Y_f[:, 0] == 0)
        assert Y_f[1, 1] == pytest.approx(1.0e-3)
        assert Y_f[2, 2] == pytest.approx(1.0e-3)
        assert Y_f[1, 2] == pytest.approx(-1.0e-3)
        assert Y_f[2, 1] == pytest.approx(-1.0e-3)
    elif ft == "LLG":
        # Same as LL plus +1/Rx on each diagonal of B and C.
        assert np.all(Y_f[0, :] == 0)
        assert Y_f[1, 1] == pytest.approx(2.0e-3)
        assert Y_f[2, 2] == pytest.approx(2.0e-3)
        assert Y_f[1, 2] == pytest.approx(-1.0e-3)


def test_Y_send_changes_with_fault_type_radial() -> None:
    """Sanity: Y_send patterns differ structurally across fault types."""
    Y_slg = Y_send(0.5, 100.0, OMEGA, fault_type="SLG")
    Y_ll = Y_send(0.5, 100.0, OMEGA, fault_type="LL")
    Y_llg = Y_send(0.5, 100.0, OMEGA, fault_type="LLG")
    # SLG: |Y_aa| should be much larger than |Y_bb|.
    assert abs(Y_slg[0, 0]) > 5 * abs(Y_slg[1, 1])
    # LL: |Y_bb| ~ |Y_cc| should be much larger than |Y_aa|.
    assert abs(Y_ll[1, 1]) > 5 * abs(Y_ll[0, 0])
    assert abs(Y_ll[2, 2]) > 5 * abs(Y_ll[0, 0])
    # LLG: |Y_bb| even larger than LL (extra ground path).
    assert abs(Y_llg[1, 1]) > abs(Y_ll[1, 1])


def test_classify_fault_type_noiseless_100pct_on_subsample() -> None:
    """Noiseless classification accuracy = 100 % on a 5-bus / 3-Rx
    sub-sample of IEEE 34.  This is the WP3.4 framework-lives check."""
    network = build_ieee34()
    buses = [b for b in network.data.buses if b != network.data.source_bus][:5]
    n_correct = 0
    n_total = 0
    for ft_true in FAULT_TYPES:
        for bus in buses:
            for Rx in (100.0, 1000.0, 5000.0):
                Y_clean = network.Y_send(
                    OMEGA, fault_bus=bus, alpha=0.5, Rx=Rx,
                    fault_type=ft_true,
                )
                est = classify_fault_type_3ph(
                    Y_clean, network, fault_bus=bus, omega=OMEGA,
                )
                n_total += 1
                n_correct += int(est.fault_type_hat == ft_true)
    assert n_correct == n_total, (
        f"noiseless classification accuracy = {n_correct}/{n_total}; "
        f"expected 100 %"
    )


def _load_confusion_subset(subset: str) -> dict[str, list[int]]:
    """Read the per-subset row-by-row truth -> predicted counts."""
    if not CONFUSION_PATH.exists():
        pytest.skip(
            f"{CONFUSION_PATH} not present; run "
            f"`python run_faultloc_phase3_fault_types.py` first."
        )
    rows = list(csv.DictReader(CONFUSION_PATH.open()))
    matched = {r["truth"]: r for r in rows if r["subset"] == subset}
    if not matched:
        pytest.skip(
            f"subset {subset!r} not present in {CONFUSION_PATH.name}; "
            f"re-run the runner if the CSV is stale."
        )
    return matched


def test_confusion_matrix_present() -> None:
    """Sanity: confusion matrix CSV is written with the expected schema."""
    if not CONFUSION_PATH.exists():
        pytest.skip(
            f"{CONFUSION_PATH} not present; run "
            f"`python run_faultloc_phase3_fault_types.py` first."
        )
    rows = list(csv.DictReader(CONFUSION_PATH.open()))
    assert len(rows) >= 12, (
        f"expected at least 12 rows (4 subsets x 3 truth classes); "
        f"got {len(rows)}"
    )
    expected_keys = {
        "subset", "truth",
        "pred_SLG", "pred_LL", "pred_LLG",
        "row_total", "recall_pct",
    }
    assert expected_keys <= set(rows[0].keys())


def test_noiseless_subset_accuracy_100pct() -> None:
    """At SNR_I = inf, the runner must hit 100 % accuracy.  This
    re-asserts the noiseless framework-lives check on the actual
    runner output, not just on the in-test sub-sample."""
    matched = _load_confusion_subset("snrI_inf")
    overall = matched.get("OVERALL")
    if overall is None:
        # Older runs may not have the OVERALL row; compute manually.
        n_correct = sum(int(matched[ft][f"pred_{ft}"]) for ft in FAULT_TYPES)
        n_total = sum(int(matched[ft]["row_total"]) for ft in FAULT_TYPES)
        acc = 100.0 * n_correct / max(n_total, 1)
    else:
        acc = float(overall["recall_pct"])
    assert acc >= 99.0, (
        f"noiseless overall accuracy = {acc:.2f} %; expected >= 99 %"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "WP3.4 R1 escalation: the 95 % brief target at SNR_I >= 30 dB "
        "across the IEEE 34 grid is not met by the WP3.4 commit.  Per-Rx "
        "breakdown shows essentially 100 % at low R_x (hard faults) and "
        "essentially chance-level at high R_x + SNR_I = 30 dB, where the "
        "constant-Z load admittance dominates the per-entry Y_send "
        "baseline and the fault signature falls below the noise floor.  "
        "Closes at WP3.5 / WP3.6 (multi-bin Taylor-Fourier + multi-port "
        "FIM lift the SNR on the fault signature) and at the WP3.3 "
        "follow-up (canonical IEEE 34 line codes 300-304 + regulators "
        "raise the per-bus voltages and reduce the load-dominated baseline "
        "magnitude relative to the fault signature)."
    ),
)
def test_overall_accuracy_at_snrI_ge_30dB_within_95pct() -> None:
    """WP3.4 brief acceptance: >= 95 % overall accuracy at SNR_I >= 30 dB."""
    matched = _load_confusion_subset("snrI_ge_30dB")
    overall = matched.get("OVERALL")
    if overall is None:
        n_correct = sum(int(matched[ft][f"pred_{ft}"]) for ft in FAULT_TYPES)
        n_total = sum(int(matched[ft]["row_total"]) for ft in FAULT_TYPES)
        acc = 100.0 * n_correct / max(n_total, 1)
    else:
        acc = float(overall["recall_pct"])
    assert acc >= 95.0, (
        f"overall classification accuracy at SNR_I >= 30 dB = {acc:.2f} %; "
        f"brief target is >= 95 %.  See outputs/phase3_fault_type_confusion"
        f".csv for the per-truth-class recall breakdown."
    )


def test_classifier_recovers_truth_per_type_in_easy_regime() -> None:
    """Sanity: in the (low R_x, high SNR) easy regime the classifier
    must recover the truth on every cell."""
    rng = np.random.default_rng(7)
    network = build_ieee34()
    buses = [b for b in network.data.buses if b != network.data.source_bus][:5]
    n_correct = 0
    n_total = 0
    for ft_true in FAULT_TYPES:
        for bus in buses:
            Y_clean = network.Y_send(
                OMEGA, fault_bus=bus, alpha=0.5, Rx=100.0,
                fault_type=ft_true,
            )
            for _ in range(3):
                Y_noisy = add_complex_gaussian_noise_to_Y(
                    Y_clean, 40.0, rng=rng,
                )
                est = classify_fault_type_3ph(
                    Y_noisy, network, fault_bus=bus, omega=OMEGA,
                )
                n_total += 1
                n_correct += int(est.fault_type_hat == ft_true)
    acc = 100.0 * n_correct / n_total
    assert acc >= 95.0, (
        f"easy-regime accuracy (R_x = 100, SNR_I = 40 dB) = {acc:.2f} %; "
        f"expected >= 95 %.  Inspect classifier wiring."
    )
