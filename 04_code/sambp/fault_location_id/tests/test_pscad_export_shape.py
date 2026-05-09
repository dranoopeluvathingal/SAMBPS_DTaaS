"""tests/test_pscad_export_shape.py
====================================

WP1.1 acceptance check: confirm ``data/pscad_720.mat`` exists and has
the canonical schema (720-cell V/I waveform pairs, four 720-cell grid
arrays, and a meta struct).

If the .mat file is missing the test triggers
``tools/pscad_surrogate.py`` to (re)generate it, so the test is
runnable on machines without PSCAD.  The lead engineer's PSCAD run
later overwrites the file with measured waveforms; this test is
schema-only and passes for either source.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat

PROJ_ROOT = Path(__file__).resolve().parent.parent
MAT_PATH = PROJ_ROOT / "data" / "pscad_720.mat"
SURROGATE = PROJ_ROOT / "tools" / "pscad_surrogate.py"

EXPECTED_SHAPE = (720, 200)
EXPECTED_GRID_LEN = 720


def _ensure_mat_exists() -> None:
    if MAT_PATH.exists():
        return
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, str(SURROGATE), "--out", str(MAT_PATH)],
        cwd=PROJ_ROOT,
        check=True,
    )


@pytest.fixture(scope="module")
def bundle() -> dict:
    _ensure_mat_exists()
    return loadmat(str(MAT_PATH))


def test_mat_file_exists(bundle: dict) -> None:
    """data/pscad_720.mat exists and loads."""
    assert MAT_PATH.exists()
    assert "V" in bundle and "I" in bundle


def test_V_shape_is_720_by_200(bundle: dict) -> None:
    V = bundle["V"]
    assert V.shape == EXPECTED_SHAPE, (
        f"V shape {V.shape} != expected {EXPECTED_SHAPE}"
    )


def test_I_shape_is_720_by_200(bundle: dict) -> None:
    Ic = bundle["I"]
    assert Ic.shape == EXPECTED_SHAPE, (
        f"I shape {Ic.shape} != expected {EXPECTED_SHAPE}"
    )


@pytest.mark.parametrize("key", ["grid_alpha", "grid_Rx", "grid_SNR_V", "grid_SNR_I"])
def test_grid_arrays_have_720_entries(bundle: dict, key: str) -> None:
    arr = bundle[key].squeeze()
    assert arr.shape == (EXPECTED_GRID_LEN,), (
        f"{key} shape {arr.shape} != ({EXPECTED_GRID_LEN},)"
    )


def test_grid_alpha_in_unit_interval(bundle: dict) -> None:
    a = bundle["grid_alpha"].squeeze()
    assert np.all((a > 0.0) & (a < 1.0)), "grid_alpha values must lie in (0, 1)"


def test_grid_Rx_positive(bundle: dict) -> None:
    R = bundle["grid_Rx"].squeeze()
    assert np.all(R > 0), "grid_Rx values must be strictly positive"
