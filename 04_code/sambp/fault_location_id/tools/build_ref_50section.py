"""build_ref_50section.py
==========================

Producer for ``data/ref_50section_720.mat`` (WP1.3 canonical reference).

Thin CLI wrapper around
``models.faultloc_50section_reference.build_dataset``.  Default
N_s_per_side = 50, rng_seed = 17 (independent of the PSCAD surrogate's
seed 42 and the EMTP surrogate's seed 4242).

Usage
-----
    python tools/build_ref_50section.py
    python tools/build_ref_50section.py --out data/ref_50section_720.mat \\
                                         --n-per-side 50 --rng-seed 17
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sambp_fault_location_id.models.faultloc_50section_reference import (
    build_dataset,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/ref_50section_720.mat"),
    )
    parser.add_argument("--n-per-side", type=int, default=50)
    parser.add_argument(
        "--rng-seed",
        type=int,
        default=17,
        help="Independent of pscad_surrogate (42) and emtp_surrogate (4242).",
    )
    args = parser.parse_args(argv)
    out = build_dataset(args.out, n_per_side=args.n_per_side, rng_seed=args.rng_seed)
    print(
        f"build_ref_50section: wrote {out}\n"
        f"  N_s per side  {args.n_per_side}\n"
        f"  rng seed      {args.rng_seed}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
