"""tools/pscad_surrogate_3ph_branched.py
==========================================
Three-phase BRANCHED PSCAD-equivalent surrogate for the WP3.2 fault-
location case ``pscad/HIFL_11kV_100km_3ph_branched.pscx``.  Produces
``data/pscad_branched_720.mat`` carrying noiseless Y_send (3, 3) per
cell across the 720-grid extended with a 2-axis `fault_branch` factor
(9 alpha x 5 R_x x 4 SNR_V x 4 SNR_I x 2 fault_branch = **1440 cells**;
the file name retains "_720" for consistency with the WP3.1 / WP1.1
schema convention).

Independence from the closed-form ``Network`` reduction
-------------------------------------------------------

The closed-form Network in ``models/faultloc_three_phase_model.py``
reduces the branched topology by propagating look-back admittances
through 6x6 line ABCD matrices computed via ``scipy.linalg.expm`` on
the per-segment 6x6 system matrix.

This surrogate uses an INDEPENDENT numerical pathway: the line ABCD
per segment is built as a cascade of 50 LUMPED-pi 6x6 ABCD matrices
of length L_segment / 50, exactly matching the WP3.1 single-radial
``tools/pscad_surrogate_3ph.py`` pattern.  The Network reduction is
re-used verbatim with the surrogate's lumped-pi line ABCD passed in
via the ``line_abcd_fn`` override; the closed-form-vs-surrogate
agreement is therefore the agreement of the EXPM line model vs the
50-pi cascade, lifted through the same network-reduction algebra.

The two pathways agree to roughly 0.05 % per WP3.1 measurement
(median 6.3e-7; max 1.4e-6 across 45 unique radial cells).  The 5 %
tolerance in ``tests/test_branched_vs_pscad.py`` gives 4 orders of
magnitude margin.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP3.1  Three-phase Y_send (radial; surrogate at
           tools/pscad_surrogate_3ph.py).
    WP3.2  Branched extension: lateral + tap load + DG (THIS surrogate).
    WP3.3  IEEE 13- / 34- / 123-node feeders (replaces the canonical
           branched-100-km topology with the actual feeder).

References
----------

* Saha, M.M. et al., "Fault Location on Power Networks", Springer 2010
  -- Bergeron + 3-phase line model.
* Kang, T. et al., "Closed-form fully distributed-parameter line
  model for time-domain fault location", EPSR 2021,
  pii S0378779621006039.
* docs/feeder_assumptions.md -- DG / tap-load / lateral-length
  defaults for this commit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from sambp_fault_location_id.models.faultloc_three_phase_model import (
    DEFAULT_DG_INTERNAL_IMPEDANCE_OHM,
    DEFAULT_DG_POSITION,
    DEFAULT_LATERAL_LENGTH_KM,
    DEFAULT_LINE_LENGTH_KM,
    DEFAULT_R_LOAD_OHM,
    DEFAULT_TAP_LOAD_IMPEDANCE_OHM,
    DEFAULT_TAP_POSITION,
    Network,
    Y_abc_per_km,
    Z_abc_per_km,
)
from scipy.io import savemat

PROJ_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJ_ROOT / "data"

OMEGA = 2.0 * np.pi * 50.0
ALPHAS = np.round(np.linspace(0.10, 0.90, 9), 3)
RXS = np.array([100.0, 500.0, 1000.0, 2000.0, 5000.0])
SNR_VS = np.array([20.0, 30.0, 40.0, np.inf])
SNR_IS = np.array([20.0, 30.0, 40.0, np.inf])
FAULT_BRANCHES = ("main", "lateral")

DEFAULT_N_SECTIONS_PER_SEGMENT = 50


def _pi_section_ABCD_3ph(
    Z_per_km: np.ndarray, Y_per_km: np.ndarray, dx_km: float
) -> np.ndarray:
    """6x6 ABCD for a single LUMPED-pi 3-phase section of length dx.
    Identical to ``tools/pscad_surrogate_3ph._pi_section_ABCD``."""
    Z = Z_per_km * dx_km
    Y_half = (Y_per_km * dx_km) * 0.5
    I3 = np.eye(3, dtype=complex)
    Z3 = np.zeros((3, 3), dtype=complex)
    T_shunt = np.block([[I3, Z3], [Y_half, I3]])
    T_series = np.block([[I3, Z], [Z3, I3]])
    return T_shunt @ T_series @ T_shunt


def line_ABCD_pi_n_sections(
    length_km: float,
    omega: float,
    n_sections: int = DEFAULT_N_SECTIONS_PER_SEGMENT,
) -> np.ndarray:
    """Cascaded n_sections lumped-pi sections summing to length_km.
    Drop-in replacement for the closed-form ``line_ABCD`` exposed via
    the Network's ``line_abcd_fn`` override hook."""
    Z = Z_abc_per_km(omega)
    Y = Y_abc_per_km(omega)
    dx = length_km / n_sections
    T_section = _pi_section_ABCD_3ph(Z, Y, dx)
    T = np.eye(6, dtype=complex)
    for _ in range(n_sections):
        T = T @ T_section
    return T


def _make_pi_line_fn(n_sections_per_segment: int):
    def _fn(length_km: float, omega: float) -> np.ndarray:
        return line_ABCD_pi_n_sections(length_km, omega, n_sections_per_segment)
    return _fn


def Y_send_branched_pi_surrogate(
    *,
    alpha: float,
    Rx: float,
    omega: float,
    fault_branch: str = "main",
    fault_phase: int = 0,
    network: Network | None = None,
    n_sections_per_segment: int = DEFAULT_N_SECTIONS_PER_SEGMENT,
) -> np.ndarray:
    """3x3 Y_send for the branched 3-phase network using the lumped-pi
    surrogate per line segment.  Re-uses the closed-form
    :class:`Network` reduction with a lumped-pi ``line_abcd_fn``."""
    if network is None:
        network = Network()
    line_fn = _make_pi_line_fn(n_sections_per_segment)
    return network.Y_send(
        omega,
        alpha=alpha,
        Rx=Rx,
        fault_phase=fault_phase,
        fault_branch=fault_branch,
        line_abcd_fn=line_fn,
    )


def build_dataset(
    out_path: Path | None = None,
    *,
    n_sections_per_segment: int = DEFAULT_N_SECTIONS_PER_SEGMENT,
) -> Path:
    """Build the 1440-cell branched 3-phase Y_send bundle and save."""
    if out_path is None:
        out_path = DATA_DIR / "pscad_branched_720.mat"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_cells = (
        ALPHAS.size * RXS.size * SNR_VS.size * SNR_IS.size * len(FAULT_BRANCHES)
    )
    Y_send = np.zeros((n_cells, 3, 3), dtype=complex)
    grid_alpha = np.zeros(n_cells, dtype=float)
    grid_Rx = np.zeros(n_cells, dtype=float)
    grid_SNR_V = np.zeros(n_cells, dtype=float)
    grid_SNR_I = np.zeros(n_cells, dtype=float)
    grid_fault_branch = np.zeros(n_cells, dtype="U16")

    network = Network()

    # Cache Y_send per (alpha, R_x, fault_branch).
    cache: dict[tuple[float, float, str], np.ndarray] = {}
    k = 0
    for fb in FAULT_BRANCHES:
        for a in ALPHAS:
            for R in RXS:
                key = (float(a), float(R), fb)
                if key not in cache:
                    cache[key] = Y_send_branched_pi_surrogate(
                        alpha=float(a),
                        Rx=float(R),
                        omega=OMEGA,
                        fault_branch=fb,
                        network=network,
                        n_sections_per_segment=n_sections_per_segment,
                    )
                for sV in SNR_VS:
                    for sI in SNR_IS:
                        Y_send[k] = cache[key]
                        grid_alpha[k] = float(a)
                        grid_Rx[k] = float(R)
                        grid_SNR_V[k] = float(sV)
                        grid_SNR_I[k] = float(sI)
                        grid_fault_branch[k] = fb
                        k += 1
    assert k == n_cells

    meta = {
        "schema_version": "wp3.2.p3.2",
        "n_sections_per_segment": int(n_sections_per_segment),
        "main_length_km": float(network.main_length_km),
        "tap_position": float(network.tap_position),
        "lateral_length_km": float(network.lateral_length_km),
        "dg_position": float(network.dg_position),
        "tap_load_impedance_ohm_real": float(network.tap_load_impedance_ohm.real),
        "tap_load_impedance_ohm_imag": float(network.tap_load_impedance_ohm.imag),
        "dg_internal_impedance_ohm_real": float(
            network.dg_internal_impedance_ohm.real
        ),
        "dg_internal_impedance_ohm_imag": float(
            network.dg_internal_impedance_ohm.imag
        ),
        "R_load_open_ohm": float(network.R_load_open_ohm),
        "fault_type": "SLG",
        "fault_phase": "A (index 0)",
        "frequency_Hz": 50.0,
        "Y_send_units": "siemens",
        "comment": (
            "Noiseless 3-phase BRANCHED sending-end admittance Y_send "
            "per cell. Surrogate for canonical PSCAD output; replaced by "
            "pscad/run_pscad_branched_720.py once licensed PSCAD runs.  "
            "Grid extended over fault_branch in {main, lateral} = 1440 "
            "cells; file name '_720.mat' is retained for schema-family "
            "consistency with WP1.1 / WP3.1."
        ),
    }

    savemat(
        str(out_path),
        {
            "Y_send": Y_send,
            "grid_alpha": grid_alpha,
            "grid_Rx": grid_Rx,
            "grid_SNR_V": grid_SNR_V,
            "grid_SNR_I": grid_SNR_I,
            "grid_fault_branch": grid_fault_branch,
            "meta": meta,
        },
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output .mat path (default data/pscad_branched_720.mat)",
    )
    parser.add_argument(
        "--n-sections-per-segment",
        type=int,
        default=DEFAULT_N_SECTIONS_PER_SEGMENT,
        help="Lumped-pi sections per uniform segment (default 50)",
    )
    args = parser.parse_args(argv)
    path = build_dataset(
        args.out,
        n_sections_per_segment=args.n_sections_per_segment,
    )
    print(f"wrote {path}")
    return 0


__all__ = [
    "FAULT_BRANCHES",
    "ALPHAS",
    "RXS",
    "SNR_VS",
    "SNR_IS",
    "OMEGA",
    "DEFAULT_DG_INTERNAL_IMPEDANCE_OHM",
    "DEFAULT_DG_POSITION",
    "DEFAULT_LATERAL_LENGTH_KM",
    "DEFAULT_LINE_LENGTH_KM",
    "DEFAULT_R_LOAD_OHM",
    "DEFAULT_TAP_LOAD_IMPEDANCE_OHM",
    "DEFAULT_TAP_POSITION",
    "Y_send_branched_pi_surrogate",
    "line_ABCD_pi_n_sections",
    "build_dataset",
]


if __name__ == "__main__":
    sys.exit(main())
