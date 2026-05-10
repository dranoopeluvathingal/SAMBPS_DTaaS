"""tests/test_cnrs_validation.py
==================================

WP3.7 (P3.7) CNRS IEEE 34-node external validation tests.

Asserts:

1. The MANIFEST.sha256 file is present and contains the expected
   per-file SHA-256 sums for the LIGHT artefacts (data_explanation
   .pdf, data_read.py, IEEE_34_node_HIF.pdf, train.zip).
2. The validation CSV is present with the expected schema.
3. The two overlay PDFs are present and non-empty.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

PROJ_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = PROJ_ROOT / "data" / "cnrs_ieee34" / "MANIFEST.sha256"
VALIDATION_CSV = PROJ_ROOT / "outputs" / "phase3_cnrs_validation.csv"
DIST_PDF = PROJ_ROOT / "outputs" / "phase3_figs" / "cnrs_distribution.pdf"
COMP_PDF = PROJ_ROOT / "outputs" / "phase3_figs" / "cnrs_dft_vs_tft.pdf"

EXPECTED_FILES = {
    "data_explanation.pdf",
    "data_read.py",
    "IEEE_34_node_HIF.pdf",
    "train.zip",
}


def test_manifest_present_and_records_sha256() -> None:
    if not MANIFEST.exists():
        pytest.skip(
            f"{MANIFEST} not present; run "
            f"`python tools/fetch_cnrs_dataset.py` first."
        )
    text = MANIFEST.read_text()
    # Header lines start with #; data lines look like "<sha>  <bytes>  <name>".
    data_lines = [
        ln for ln in text.splitlines() if ln and not ln.startswith("#")
    ]
    assert len(data_lines) >= 4, (
        f"manifest has only {len(data_lines)} entries; expected >= 4"
    )
    seen = set()
    for ln in data_lines:
        parts = ln.split()
        assert len(parts) == 3, f"malformed manifest line: {ln!r}"
        sha, _size, name = parts
        assert len(sha) == 64, (
            f"sha256 hex length should be 64; got {len(sha)} for {name}"
        )
        seen.add(name)
    assert EXPECTED_FILES <= seen, (
        f"missing files in manifest: {EXPECTED_FILES - seen}"
    )


def test_validation_csv_present_and_schema() -> None:
    if not VALIDATION_CSV.exists():
        pytest.skip(
            f"{VALIDATION_CSV} not present; run "
            f"`python run_faultloc_phase3_cnrs_validation.py` first."
        )
    rows = list(csv.DictReader(VALIDATION_CSV.open()))
    assert len(rows) >= 30, f"expected >= 30 rows; got {len(rows)}"
    expected_keys = {
        "trace", "alpha_hat_dft", "Rx_hat_dft",
        "alpha_hat_tft", "Rx_hat_tft",
        "J_min_dft", "J_min_tft",
        "abs_H_dft", "abs_H_tft",
        "source_v_rms", "source_i_rms",
        "cpu_dft_s", "cpu_tft_s",
    }
    assert expected_keys <= set(rows[0].keys())


def test_overlay_pdfs_present() -> None:
    for path in (DIST_PDF, COMP_PDF):
        if not path.exists():
            pytest.skip(
                f"{path.name} not present; run "
                f"`python run_faultloc_phase3_cnrs_validation.py` first."
            )
        assert path.stat().st_size > 1000, (
            f"{path.name} is suspiciously small ({path.stat().st_size} bytes)"
        )


def test_train_zip_sha256_recorded() -> None:
    """Sanity: the train.zip hash recorded in the manifest matches
    the file actually on disk (when the file is present)."""
    if not MANIFEST.exists():
        pytest.skip(f"{MANIFEST} not present")
    train_zip = PROJ_ROOT / "data" / "cnrs_ieee34" / "train.zip"
    if not train_zip.exists():
        pytest.skip(f"{train_zip} not present")
    import hashlib
    h = hashlib.sha256()
    with train_zip.open("rb") as fh:
        while True:
            chunk = fh.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    actual = h.hexdigest()
    text = MANIFEST.read_text()
    matched = [
        ln for ln in text.splitlines()
        if not ln.startswith("#") and ln.endswith("train.zip")
    ]
    assert matched, "train.zip not found in manifest"
    last_recorded = matched[-1].split()[0]
    assert last_recorded == actual, (
        f"train.zip sha256 mismatch:\n"
        f"  manifest:  {last_recorded}\n"
        f"  actual:    {actual}"
    )
