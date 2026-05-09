"""run_pscad_720.py
====================

Drives the canonical PSCAD case `pscad/HIFL_11kV_100km.pscx` through
its 720-cell multiple-run sweep and stitches the output channels into
`data/pscad_720.mat` with the schema documented in
`pscad/HIFL_11kV_100km_design.md` ("Output bundle").

Two modes
---------

  --automation     Use the Manitoba HVDC `mhi.pscad` Python automation
                   API to launch PSCAD, set the 4 multiple-run
                   parameters, run the sweep, and gather the output
                   channels.  Requires PSCAD installed and the
                   `mhi.pscad` Python module on the runner.

  --gnu-postprocess
                   Skip the PSCAD launch.  Assume the lead engineer has
                   already run the sweep manually in the GUI and the
                   per-cell `.gnu` channel files exist next to the
                   .pscx.  Just gather them, sub-sample to 720, and
                   write the .mat.

If neither flag is given the script prints the usage and exits 2.

Sub-sampling rule
-----------------

PSCAD's 4-parameter sweep yields 10 alpha x 5 Rx x 4 SNR_V x 4 SNR_I
= 800 cells.  The canonical `pscad_720.mat` keeps 9 alpha values
(drop alpha = 0.05; remaining: 0.10, 0.20, ..., 0.90) for the 720
headline.  See `pscad/HIFL_11kV_100km_design.md` "Grid sizing note".

Surrogate fallback
------------------

When PSCAD is not installed (typical on a Linux dev box), this script
exits with a clear error and points the user at
`tools/pscad_surrogate.py`, which produces a Python distributed-
parameter ABCD-cascading reference `data/pscad_720.mat` with the same
schema.  The lead engineer's PSCAD run later overwrites with measured
waveforms.
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
        default=Path("pscad/HIFL_11kV_100km.pscx"),
        help="Path to the canonical PSCAD project file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/pscad_720.mat"),
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
            "\nrun_pscad_720: choose --automation OR --gnu-postprocess",
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
            "run_pscad_720: `mhi.pscad` is not installed on this runner.\n"
            "  Install Manitoba HVDC's PSCAD automation:\n"
            "      pip install mhi.pscad\n"
            "  (Requires a licensed PSCAD installation in the same env.)\n"
            "  Or, on a dev box without PSCAD, run the surrogate:\n"
            "      python tools/pscad_surrogate.py --out data/pscad_720.mat",
            file=sys.stderr,
        )
        return 3

    if not case.exists():
        print(
            f"run_pscad_720: PSCAD case file not found: {case}\n"
            f"  Build it manually from pscad/README_manual_run.md.",
            file=sys.stderr,
        )
        return 4

    # The actual driver below is intentionally a stub - the
    # canonical implementation is finalised on a Windows runner with
    # the licensed PSCAD installation.  Skeleton retained so the
    # lead engineer can fill in the call sequence:
    #
    #     pscad = mhi.pscad.launch()
    #     proj  = pscad.load(str(case))
    #     proj.parameters(alpha=..., Rx=..., snrV_dB=..., snrI_dB=...)
    #     proj.run()
    #     V = proj.outputs('V_in_chan')
    #     I = proj.outputs('I_in_chan')
    #     ... gather all 800 cells, sub-sample to 720, scipy.io.savemat ...
    print(
        "run_pscad_720: --automation skeleton.  Fill in the mhi.pscad\n"
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
            f"run_pscad_720: no .gnu files found next to {case}.\n"
            f"  Run the multiple-run sweep manually in the PSCAD GUI\n"
            f"  (see pscad/README_manual_run.md §B.2) before retrying.",
            file=sys.stderr,
        )
        return 6
    # Likewise stub: parse .gnu files, stitch into (800, 200) arrays,
    # sub-sample to 720, write .mat.
    print(
        f"run_pscad_720: --gnu-postprocess found {len(gnu_files)} .gnu files;\n"
        f"  postprocessor not yet implemented in this skeleton.\n"
        f"  Use tools/pscad_surrogate.py to bootstrap data/pscad_720.mat.",
        file=sys.stderr,
    )
    return 7


if __name__ == "__main__":
    sys.exit(main())
