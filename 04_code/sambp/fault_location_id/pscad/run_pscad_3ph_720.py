"""run_pscad_3ph_720.py
========================

Three-phase analogue of `pscad/run_pscad_720.py` (WP1.1).  Drives the
canonical PSCAD case `pscad/HIFL_11kV_100km_3ph.pscx` through its
720-cell multiple-run sweep and stitches the output channels into
`data/pscad_3ph_720.mat` with the schema documented in
`pscad/HIFL_11kV_100km_3ph_design.md` ("Output bundle schema").

WP3.1 (P3.1) status: skeleton.  PSCAD is not on the dev box; the
canonical .pscx is authored on the lead engineer's licensed Windows
station per `pscad/README_manual_run_3ph.md`.  Until then,
`tools/pscad_surrogate_3ph.py` builds an independent-pathway
surrogate at the same path with the same schema.

Two modes
---------

  --automation     Use the Manitoba HVDC `mhi.pscad` Python automation
                   API to launch PSCAD, set the 4 multiple-run
                   parameters, run the sweep, and gather the per-phase
                   V/I channels (V_a_in, V_b_in, V_c_in, I_a_in,
                   I_b_in, I_c_in).  After gathering, computes the
                   single-bin DFT per phase and the 3x3 Y_send per cell
                   in line with the surrogate's schema.

  --gnu-postprocess
                   Skip the PSCAD launch.  Assume the lead engineer
                   has already run the sweep manually in the GUI and
                   the per-cell .gnu channel files exist next to the
                   .pscx.  Just gather, sub-sample to 720, and write
                   the .mat.

If neither flag is given the script prints the usage and exits 2.

Surrogate fallback
------------------

When PSCAD is not installed (typical on a Linux dev box), this script
exits with a clear error and points the user at
`tools/pscad_surrogate_3ph.py`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--case",
        type=Path,
        default=Path("pscad/HIFL_11kV_100km_3ph.pscx"),
        help="Path to the canonical PSCAD project file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/pscad_3ph_720.mat"),
        help="Path to write the stitched 720-cell .mat file.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--automation",
        action="store_true",
        help="Use mhi.pscad to launch PSCAD and run the sweep.",
    )
    mode.add_argument(
        "--gnu-postprocess",
        action="store_true",
        help="Assume the GUI sweep has already produced .gnu files; "
        "just gather and stitch.",
    )
    args = parser.parse_args(argv)

    if not (args.automation or args.gnu_postprocess):
        parser.print_help()
        print(
            "\nrun_pscad_3ph_720: choose --automation OR --gnu-postprocess",
            file=sys.stderr,
        )
        return 2

    if args.automation:
        return _run_automation(args.case, args.out)
    else:
        return _run_postprocess(args.case, args.out)


def _run_automation(case: Path, out: Path) -> int:
    """Drive PSCAD via the Manitoba HVDC `mhi.pscad` automation API."""
    try:
        import mhi.pscad  # noqa: F401
    except ImportError:
        print(
            "run_pscad_3ph_720: `mhi.pscad` is not installed on this runner.\n"
            "  Install Manitoba HVDC's PSCAD automation:\n"
            "      pip install mhi.pscad\n"
            "  (Requires a licensed PSCAD installation in the same env.)\n"
            "  Or, on a dev box without PSCAD, run the surrogate:\n"
            "      python tools/pscad_surrogate_3ph.py "
            "--out data/pscad_3ph_720.mat",
            file=sys.stderr,
        )
        return 3

    if not case.exists():
        print(
            f"run_pscad_3ph_720: PSCAD case file not found: {case}\n"
            f"  Build it manually from pscad/HIFL_11kV_100km_3ph_design.md\n"
            f"  and pscad/README_manual_run_3ph.md.",
            file=sys.stderr,
        )
        return 4

    # Skeleton retained so the lead engineer fills in the mhi.pscad
    # call sequence on the licensed station:
    #
    #     pscad = mhi.pscad.launch()
    #     proj  = pscad.load(str(case))
    #     proj.parameters(alpha=..., Rx=..., snrV_dB=..., snrI_dB=...)
    #     proj.run()
    #     V_abc = stack([proj.outputs(f'V_{p}_in') for p in 'abc'])
    #     I_abc = stack([proj.outputs(f'I_{p}_in') for p in 'abc'])
    #     # single-bin DFT per phase, build 3x3 Y_send per cell, save
    print(
        "run_pscad_3ph_720: --automation skeleton.  Fill in the mhi.pscad\n"
        "  call sequence on the licensed PSCAD station.  See in-line\n"
        "  comment for the expected pattern.",
        file=sys.stderr,
    )
    return 5


def _run_postprocess(case: Path, out: Path) -> int:
    """Gather .gnu channel files emitted by a manual PSCAD run."""
    case_dir = case.parent
    gnu_files = sorted(case_dir.glob("*.gnu"))
    if not gnu_files:
        print(
            f"run_pscad_3ph_720: no .gnu files found next to {case}.\n"
            f"  Run the 3-phase multiple-run sweep manually in the PSCAD GUI\n"
            f"  (see pscad/README_manual_run_3ph.md, when authored).",
            file=sys.stderr,
        )
        return 6
    print(
        f"run_pscad_3ph_720: --gnu-postprocess found {len(gnu_files)} .gnu\n"
        f"  files; postprocessor not yet implemented in this skeleton.\n"
        f"  Use tools/pscad_surrogate_3ph.py to bootstrap "
        f"data/pscad_3ph_720.mat.",
        file=sys.stderr,
    )
    return 7


if __name__ == "__main__":
    sys.exit(main())
