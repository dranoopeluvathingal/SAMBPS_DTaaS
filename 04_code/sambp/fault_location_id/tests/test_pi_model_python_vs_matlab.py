"""tests/test_pi_model_python_vs_matlab.py
============================================

WP0.5 cross-runtime check.

Compares the Python implementation of the two-section cascaded-Gamma
state-space model
(``models.faultloc_pi_section_model.H_model``) against a golden CSV
of expected H values on a 5-cell grid.

The golden file ``tests/data/H_golden.csv`` is bootstrapped from the
Python implementation now (see WP0.5 changelog) and cross-validated by
``matlab/tests/generate_golden_H.m`` whenever a licensed MATLAB run
(local or CI) regenerates it.  Because both runtimes encode the same
state-space, the values agree to numerical precision; a tightening
threshold of ``< 1e-9`` enforces that the Python implementation does
not silently drift away from the canonical algebra.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sambp_fault_location_id.models.faultloc_pi_section_model import H_model

GOLDEN_PATH = Path(__file__).parent / "data" / "H_golden.csv"
TOLERANCE = 1.0e-9


def _load_golden() -> list[dict]:
    rows: list[dict] = []
    with GOLDEN_PATH.open(newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append(
                {
                    "alpha": float(r["alpha"]),
                    "Rx": float(r["Rx_ohm"]),
                    "omega": float(r["omega_rad_s"]),
                    "H": complex(float(r["H_real"]), float(r["H_imag"])),
                }
            )
    return rows


@pytest.mark.parametrize("row", _load_golden(), ids=lambda r: f"a{r['alpha']}_R{int(r['Rx'])}")
def test_python_H_matches_golden_within_1e9(row: dict) -> None:
    H_py = H_model(row["alpha"], row["Rx"], row["omega"])
    err = abs(H_py - row["H"])
    assert err < TOLERANCE, (
        f"alpha={row['alpha']}, Rx={row['Rx']}: "
        f"|H_py - H_golden| = {err:.3e} >= {TOLERANCE:.0e}"
    )


def test_max_abs_err_below_threshold() -> None:
    """Single aggregate assertion mirroring the WP0.5 acceptance line."""
    rows = _load_golden()
    errs = [abs(H_model(r["alpha"], r["Rx"], r["omega"]) - r["H"]) for r in rows]
    max_err = max(errs)
    assert max_err < TOLERANCE, (
        f"max |H_py - H_golden| over {len(rows)} cells = {max_err:.3e} "
        f"(threshold {TOLERANCE:.0e})"
    )
