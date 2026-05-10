"""run_ieee_feeders_pscad.py
==============================

WP3.3 PSCAD automation skeleton for the three IEEE feeder cases:

    pscad/IEEE_13.pscx
    pscad/IEEE_34.pscx
    pscad/IEEE_123.pscx

Drives the chosen case through its multiple-run sweep and stitches
the per-cell V/I waveforms (or Y_send 3x3 matrices) into the
`data/ieee{13,34,123}_720.mat` bundle with the schema documented in
`pscad/IEEE_13_design.md` (extended analogously for IEEE 34 / 123).

WP3.3 (P3.3) status: skeleton.  PSCAD is not on the dev box; the
canonical .pscx files are authored on the lead engineer's licensed
Windows station.  Until then,
`tools/ieee_feeder_surrogate.py` builds dev-box surrogate bundles
at the same paths with the same schema.

Two modes
---------

  --automation        Use mhi.pscad to launch PSCAD, set the
                      multiple-run sweep parameters per
                      `pscad/IEEE_{name}_design.md`, run the sweep,
                      gather per-phase V/I channels at the source bus,
                      compute the single-bin DFT and the 3x3 Y_send
                      per cell, write the .mat file.

  --gnu-postprocess   Skip the PSCAD launch.  Assume the lead engineer
                      has already run the sweep manually in the GUI
                      and the per-cell .gnu files exist next to the
                      .pscx.  Just gather, sub-sample, and write.

Surrogate fallback
------------------

When PSCAD is not installed, this script exits with a clear error
and points the user at `tools/ieee_feeder_surrogate.py`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--feeder",
        choices=("IEEE_13", "IEEE_34", "IEEE_123"),
        required=True,
        help="Which IEEE feeder to run.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Output .mat path; defaults to data/ieee{13,34,123}_720.mat "
            "based on --feeder."
        ),
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
        help="Assume the GUI sweep has produced .gnu files; just gather.",
    )
    args = parser.parse_args(argv)

    case = Path(f"pscad/{args.feeder}.pscx")
    if args.out is None:
        suffix = args.feeder.lower().replace("ieee_", "ieee")
        args.out = Path(f"data/{suffix}_720.mat")

    if not (args.automation or args.gnu_postprocess):
        parser.print_help()
        print(
            "\nrun_ieee_feeders_pscad: choose --automation OR --gnu-postprocess",
            file=sys.stderr,
        )
        return 2

    if args.automation:
        return _run_automation(case, args.out, args.feeder)
    else:
        return _run_postprocess(case, args.out, args.feeder)


def _run_automation(case: Path, out: Path, feeder: str) -> int:
    """Drive PSCAD via the Manitoba HVDC `mhi.pscad` automation API."""
    try:
        import mhi.pscad  # noqa: F401
    except ImportError:
        print(
            f"run_ieee_feeders_pscad: `mhi.pscad` is not installed.\n"
            f"  Install Manitoba HVDC's PSCAD automation:\n"
            f"      pip install mhi.pscad\n"
            f"  (Requires a licensed PSCAD installation in the same env.)\n"
            f"  Or, on a dev box without PSCAD, run the surrogate:\n"
            f"      python tools/ieee_feeder_surrogate.py --feeder {feeder}",
            file=sys.stderr,
        )
        return 3

    if not case.exists():
        print(
            f"run_ieee_feeders_pscad: PSCAD case file not found: {case}\n"
            f"  Build it manually from pscad/{feeder}_design.md.",
            file=sys.stderr,
        )
        return 4

    # Skeleton retained so the lead engineer fills in the mhi.pscad
    # call sequence on the licensed station.
    print(
        f"run_ieee_feeders_pscad: --automation skeleton for {feeder}.\n"
        f"  Fill in the mhi.pscad call sequence on the licensed PSCAD\n"
        f"  station per pscad/{feeder}_design.md.",
        file=sys.stderr,
    )
    return 5


def _run_postprocess(case: Path, out: Path, feeder: str) -> int:
    """Gather .gnu channel files emitted by a manual PSCAD run."""
    case_dir = case.parent
    gnu_files = sorted(case_dir.glob("*.gnu"))
    if not gnu_files:
        print(
            f"run_ieee_feeders_pscad: no .gnu files found next to {case}.\n"
            f"  Run the multiple-run sweep manually in the PSCAD GUI per\n"
            f"  pscad/{feeder}_design.md before retrying.",
            file=sys.stderr,
        )
        return 6
    print(
        f"run_ieee_feeders_pscad: --gnu-postprocess found {len(gnu_files)}\n"
        f"  .gnu files; postprocessor not yet implemented in this skeleton.\n"
        f"  Use tools/ieee_feeder_surrogate.py --feeder {feeder} to\n"
        f"  bootstrap data/{out.name}.",
        file=sys.stderr,
    )
    return 7


if __name__ == "__main__":
    sys.exit(main())
