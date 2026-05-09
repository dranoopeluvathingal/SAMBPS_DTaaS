"""run_emtp_720.py
====================

Drives the canonical EMTP-RV case `emtp/HIFL_11kV_100km.ecf` through
its 720-cell multiple-run sweep and stitches the output channels into
`data/emtp_720.mat` with the schema documented in
`emtp/HIFL_11kV_100km_design.md` ("Output bundle").

Two modes
---------

  --automation        Drive the EMTP-RV CLI in batch mode via subprocess.
                      Requires EMTP-RV installed and on PATH.

  --scv-postprocess   Skip the EMTP launch.  Assume the engineer has
                      already run the sweep manually in the GUI and the
                      per-cell ScopeView `.scv` files exist in the
                      working directory; gather, sub-sample to 720, and
                      write the .mat.

Sub-sampling rule
-----------------

Mirror of the PSCAD case: drop alpha = 0.05 and alpha = 0.15 from each
(Rx, snrV, snrI) combination, keeping 9 alpha values
{0.10, 0.20, ..., 0.90} -> 720 cells.

Surrogate fallback
------------------

When EMTP-RV is not installed (typical on a Linux dev box), this
script exits with a clear error and points the user at
`tools/emtp_surrogate.py`, which produces a Python 50-section
pi-model state-space reference at `data/emtp_720.mat` with the same
schema (independent numerical pathway from the PSCAD surrogate).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--case",
        type=Path,
        default=Path("emtp/HIFL_11kV_100km.ecf"),
        help="Path to the canonical EMTP-RV project file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/emtp_720.mat"),
        help="Path to write the stitched 720-cell .mat file.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--automation", action="store_true")
    mode.add_argument("--scv-postprocess", action="store_true")
    args = parser.parse_args(argv)

    if not (args.automation or args.scv_postprocess):
        parser.print_help()
        print(
            "\nrun_emtp_720: choose --automation OR --scv-postprocess",
            file=sys.stderr,
        )
        return 2

    if args.automation:
        return _run_automation(args.case, args.out)
    return _run_postprocess(args.case, args.out)


def _run_automation(case: Path, out: Path) -> int:
    """Drive EMTP-RV via its batch CLI."""
    emtp_exe = shutil.which("emtprv") or shutil.which("EMTP-RV")
    if emtp_exe is None:
        print(
            "run_emtp_720: EMTP-RV is not on PATH on this runner.\n"
            "  EMTP-RV is a proprietary Windows simulator from Powersys /\n"
            "  EMTP Alliance.  On a dev box without it, run the surrogate:\n"
            "      python tools/emtp_surrogate.py --out data/emtp_720.mat",
            file=sys.stderr,
        )
        return 3

    if not case.exists():
        print(
            f"run_emtp_720: EMTP-RV case file not found: {case}\n"
            f"  Build it manually from emtp/README_manual_run.md.",
            file=sys.stderr,
        )
        return 4

    # Skeleton driver - finalised on the licensed Windows EMTP-RV
    # station.  Expected pattern:
    #
    #     subprocess.run([emtp_exe, '/batch', str(case),
    #                     '/multirun', 'design_tool.dtd',
    #                     '/scopeview', 'export.svm'])
    #     # then gather ScopeView output, sub-sample to 720,
    #     # scipy.io.savemat into out
    print(
        "run_emtp_720: --automation skeleton.  Fill in the EMTP-RV CLI\n"
        "  invocation on the licensed Windows station; see in-line\n"
        "  comment for the expected pattern.",
        file=sys.stderr,
    )
    return 5


def _run_postprocess(case: Path, out: Path) -> int:
    """Gather ScopeView .scv files emitted by a manual EMTP-RV run."""
    case_dir = case.parent
    scv_files = sorted(case_dir.glob("*.scv"))
    if not scv_files:
        print(
            f"run_emtp_720: no .scv files found next to {case}.\n"
            f"  Run the multiple-run sweep manually in the EMTP-RV GUI\n"
            f"  (see emtp/README_manual_run.md §B.2) before retrying.",
            file=sys.stderr,
        )
        return 6
    print(
        f"run_emtp_720: --scv-postprocess found {len(scv_files)} .scv files;\n"
        f"  postprocessor not yet implemented in this skeleton.\n"
        f"  Use tools/emtp_surrogate.py to bootstrap data/emtp_720.mat.",
        file=sys.stderr,
    )
    return 7


if __name__ == "__main__":
    sys.exit(main())
