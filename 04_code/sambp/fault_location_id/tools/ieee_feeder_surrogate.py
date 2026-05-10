"""tools/ieee_feeder_surrogate.py
====================================
PSCAD-equivalent surrogate for the WP3.3 IEEE 13- / 34- / 123-node
test feeder cases.  Produces ``data/ieee13_720.mat``,
``data/ieee34_720.mat``, ``data/ieee123_720.mat`` carrying noiseless
3x3 Y_send per cell across the per-feeder grids.

Per-feeder grid
---------------

Per the WP3.3 brief:

    ``placing the fault at every node at alpha=0.5 of the line into
    the node, sweeping R_x in {100, 500, 1000, 2000, 5000} ohm,
    SNR_V x SNR_I as before.``

So the per-feeder cell count is

    n_cells = (n_buses - 1) * 5 (R_x) * 4 (SNR_V) * 4 (SNR_I)

(we exclude the source bus from the fault locations because there is
no parent line into the source bus).  For IEEE 13 with 13 buses this
gives 12 * 5 * 16 = 960 cells; the file is named ``_720.mat`` for
schema-family consistency with WP1.1 / WP3.1 / WP3.2.

Independence from the closed-form pathway
-----------------------------------------

Since the closed-form ``IEEEFeederNetwork.Y_send`` computes Y_send
through scipy.linalg.expm-based per-segment line ABCD, the surrogate
uses an independent numerical pathway: each per-segment line ABCD is
re-built via a 50-section lumped-pi cascade (matching the WP3.1 /
WP3.2 surrogates) by monkey-patching the ``_line_ABCD_for_branch``
helper at the module level.  The closed-form vs surrogate comparison
is the same expm-vs-pi-cascade comparison as WP3.1 (residual ~1e-7).

When canonical PSCAD output replaces this surrogate, the .mat schema
is preserved so the downstream estimator + tests work unchanged.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from sambp_fault_location_id.models import faultloc_ieee_feeders as ief
from scipy.io import savemat

PROJ_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJ_ROOT / "data"

OMEGA = 2.0 * np.pi * 50.0
RXS = np.array([100.0, 500.0, 1000.0, 2000.0, 5000.0])
SNR_VS = np.array([20.0, 30.0, 40.0, np.inf])
SNR_IS = np.array([20.0, 30.0, 40.0, np.inf])
DEFAULT_N_SECTIONS_PER_SEGMENT = 50


def _line_ABCD_pi_for_branch(
    branch: ief.IEEEBranch,
    line_codes: dict[str, ief.LineCode],
    omega: float,
    n_sections: int = DEFAULT_N_SECTIONS_PER_SEGMENT,
) -> np.ndarray:
    """6x6 ABCD via cascaded lumped-pi sections (independent pathway)."""
    lc = line_codes[branch.line_code]
    Z = lc.Z_abc_per_km
    Y = lc.Y_abc_per_km
    if branch.length_km <= 0:
        return np.eye(6, dtype=complex)
    dx = branch.length_km / n_sections
    Z_sec = Z * dx
    Y_half = (Y * dx) * 0.5
    I3 = np.eye(3, dtype=complex)
    Z3 = np.zeros((3, 3), dtype=complex)
    T_shunt = np.block([[I3, Z3], [Y_half, I3]])
    T_series = np.block([[I3, Z_sec], [Z3, I3]])
    T_section = T_shunt @ T_series @ T_shunt
    T = np.eye(6, dtype=complex)
    for _ in range(n_sections):
        T = T @ T_section
    return T


def Y_send_via_surrogate(
    network: ief.IEEEFeederNetwork,
    *,
    fault_bus: str,
    alpha: float = 0.5,
    Rx: float = 1000.0,
    fault_phase: int = 0,
    n_sections: int = DEFAULT_N_SECTIONS_PER_SEGMENT,
) -> np.ndarray:
    """Y_send computed via the lumped-pi surrogate line ABCD.

    Monkey-patches ``ief._line_ABCD_for_branch`` for the duration of
    the call to use the lumped-pi cascade instead of expm; restores
    the original implementation afterwards.
    """
    orig = ief._line_ABCD_for_branch

    def patched(branch, line_codes, omega):
        return _line_ABCD_pi_for_branch(
            branch, line_codes, omega, n_sections=n_sections,
        )
    ief._line_ABCD_for_branch = patched
    try:
        return network.Y_send(
            OMEGA, fault_bus=fault_bus, alpha=alpha,
            Rx=Rx, fault_phase=fault_phase,
        )
    finally:
        ief._line_ABCD_for_branch = orig


def build_dataset(
    feeder_name: str,
    out_path: Path | None = None,
    *,
    n_sections: int = DEFAULT_N_SECTIONS_PER_SEGMENT,
) -> Path:
    """Build the per-feeder Y_send bundle and save to .mat."""
    builders = {
        "IEEE_13": ief.build_ieee13,
        "IEEE_34": ief.build_ieee34,
        "IEEE_123": ief.build_ieee123,
    }
    if feeder_name not in builders:
        raise ValueError(
            f"unknown feeder {feeder_name!r}; valid: {list(builders.keys())}"
        )
    network = builders[feeder_name]()
    fault_buses = [b for b in network.data.buses
                   if b != network.data.source_bus]

    if out_path is None:
        suffix = feeder_name.lower().replace("ieee_", "ieee")
        out_path = DATA_DIR / f"{suffix}_720.mat"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_cells = len(fault_buses) * RXS.size * SNR_VS.size * SNR_IS.size
    Y_send = np.zeros((n_cells, 3, 3), dtype=complex)
    grid_alpha = np.full(n_cells, 0.5, dtype=float)
    grid_Rx = np.zeros(n_cells, dtype=float)
    grid_SNR_V = np.zeros(n_cells, dtype=float)
    grid_SNR_I = np.zeros(n_cells, dtype=float)
    grid_fault_bus = np.zeros(n_cells, dtype="U16")

    cache: dict[tuple[str, float], np.ndarray] = {}
    k = 0
    for bus in fault_buses:
        for R in RXS:
            key = (bus, float(R))
            if key not in cache:
                cache[key] = Y_send_via_surrogate(
                    network, fault_bus=bus, alpha=0.5, Rx=float(R),
                    n_sections=n_sections,
                )
            for sV in SNR_VS:
                for sI in SNR_IS:
                    Y_send[k] = cache[key]
                    grid_Rx[k] = float(R)
                    grid_SNR_V[k] = float(sV)
                    grid_SNR_I[k] = float(sI)
                    grid_fault_bus[k] = bus
                    k += 1
    assert k == n_cells

    meta = {
        "schema_version": "wp3.3.p3.3",
        "n_sections_per_segment": int(n_sections),
        "feeder_name": feeder_name,
        "n_buses": int(len(network.data.buses)),
        "n_branches": int(len(network.data.branches)),
        "n_fault_buses": int(len(fault_buses)),
        "source_bus": str(network.data.source_bus),
        "nominal_kv_ll": float(network.data.nominal_kv_ll),
        "frequency_Hz": 50.0,
        "Y_send_units": "siemens",
        "fault_alpha_per_unit": 0.5,
        "fault_type": "SLG (phase A)",
        "comment": (
            f"Noiseless 3x3 Y_send per cell for {feeder_name}.  Surrogate "
            f"for canonical PSCAD output; replaced by pscad/run_ieee_"
            f"feeders_pscad.py once licensed PSCAD runs.  Grid: "
            f"{len(fault_buses)} fault_buses x 5 R_x x 4 SNR_V x 4 SNR_I "
            f"= {n_cells} cells; file name '_720.mat' is retained for "
            f"schema-family consistency with WP1.1 / WP3.1 / WP3.2."
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
            "grid_fault_bus": grid_fault_bus,
            "meta": meta,
        },
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--feeder",
        choices=("IEEE_13", "IEEE_34", "IEEE_123", "all"),
        default="all",
        help="Which feeder to build (default: all 3)",
    )
    parser.add_argument(
        "--n-sections",
        type=int,
        default=DEFAULT_N_SECTIONS_PER_SEGMENT,
        help="Lumped-pi sections per uniform segment (default 50)",
    )
    args = parser.parse_args(argv)
    feeders = (
        ("IEEE_13", "IEEE_34", "IEEE_123") if args.feeder == "all"
        else (args.feeder,)
    )
    for f in feeders:
        path = build_dataset(f, n_sections=args.n_sections)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
