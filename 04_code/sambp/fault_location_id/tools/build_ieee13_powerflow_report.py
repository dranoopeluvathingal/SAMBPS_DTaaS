"""tools/build_ieee13_powerflow_report.py
============================================
WP3.3 power-flow validation report builder.

Runs the WP3.3 BFS power-flow solver on the IEEE 13-node feeder
:func:`build_ieee13` (Kersting Tab. 4.5 + 4.7 with the documented
WP3.3 simplifications -- see ``docs/ieee_feeders_assumptions.md``)
and writes a per-bus comparison vs Kersting's Tab. 4.10 published
voltages to ``outputs/phase3_ieee_feeder_powerflow.csv``.

The report is the artefact ``tests/test_ieee_feeders_powerflow.py``
inspects.  The columns are:

    feeder          -- "IEEE_13" (only feeder validated this commit)
    bus             -- e.g. "650", "632", "634", ...
    phase           -- "A" / "B" / "C"
    V_published_pu  -- Kersting Tab. 4.10 magnitude (pu of source)
    V_solver_pu     -- WP3.3 BFS solver magnitude (pu of source)
    abs_err_pu      -- |V_solver - V_published|
    rel_err_pct     -- 100 * abs_err / V_published
    within_1pct     -- 1 / 0 (1 = within the brief acceptance)

Kersting Tab. 4.10 source
-------------------------

The "published" magnitudes here are taken from Kersting (2002)
"Distribution System Modelling and Analysis", 2nd ed., CRC Press,
Tab. 4.10 -- the canonical IEEE 13-node bus voltages with regulator
RG60 active, mixed PQ + Z + I loads, transformer XFM-1 and capacitor
banks.  The WP3.3 BFS solver here uses the IEEE 13 topology with
constant-Z loads only (no regulator, no XFM-1, no caps); the gap
from Kersting's published values is therefore real and is precisely
the gap closed by the WP3.3 follow-up commit (regulators, mixed load
models, transformers, capacitor banks).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from sambp_fault_location_id.models.faultloc_ieee_feeders import build_ieee13

PROJ_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJ_ROOT / "outputs"

# Kersting (2002) Tab. 4.10 magnitudes (per unit).  "--" entries
# correspond to phases not present at single-/two-phase laterals
# (645/646 = B+C; 611 = C; 652 = A; 684 = A+C).
KERSTING_TAB_4_10 = {
    # bus:    (Va_pu, Vb_pu, Vc_pu); None where the phase is absent.
    "650":   (1.0000, 1.0000, 1.0000),
    "RG60":  (1.0625, 1.0500, 1.0625),  # synthetic node not in our topo
    "632":   (1.0210, 1.0420, 1.0174),
    "633":   (1.0180, 1.0401, 1.0148),
    "634":   (0.9940, 1.0218, 0.9960),
    "645":   (None,   1.0329, 1.0155),
    "646":   (None,   1.0311, 1.0134),
    "671":   (0.9900, 1.0529, 0.9778),
    "692":   (0.9900, 1.0529, 0.9777),
    "675":   (0.9835, 1.0553, 0.9758),
    "680":   (0.9900, 1.0529, 0.9778),
    "684":   (0.9881, None,   0.9758),
    "611":   (None,   None,   0.9738),
    "652":   (0.9825, None,   None),
}


def main() -> int:
    network = build_ieee13()
    V = network.power_flow()
    V_source_phase = abs(V["650"][0])

    out_path = OUT_DIR / "phase3_ieee_feeder_powerflow.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for bus in network.data.buses:
        if bus not in KERSTING_TAB_4_10:
            continue
        published = KERSTING_TAB_4_10[bus]
        for phase_idx, phase_name in enumerate("ABC"):
            v_pub = published[phase_idx]
            v_solver_pu = abs(V[bus][phase_idx]) / V_source_phase
            if v_pub is None:
                rows.append({
                    "feeder": "IEEE_13",
                    "bus": bus,
                    "phase": phase_name,
                    "V_published_pu": "n/a",
                    "V_solver_pu": f"{v_solver_pu:.6f}",
                    "abs_err_pu": "n/a",
                    "rel_err_pct": "n/a",
                    "within_1pct": "n/a",
                })
                continue
            abs_err = abs(v_solver_pu - v_pub)
            rel_err_pct = 100.0 * abs_err / v_pub
            rows.append({
                "feeder": "IEEE_13",
                "bus": bus,
                "phase": phase_name,
                "V_published_pu": f"{v_pub:.6f}",
                "V_solver_pu": f"{v_solver_pu:.6f}",
                "abs_err_pu": f"{abs_err:.6f}",
                "rel_err_pct": f"{rel_err_pct:.4f}",
                "within_1pct": "1" if rel_err_pct < 1.0 else "0",
            })

    with out_path.open("w", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "feeder", "bus", "phase",
                "V_published_pu", "V_solver_pu",
                "abs_err_pu", "rel_err_pct", "within_1pct",
            ],
        )
        w.writeheader()
        for row in rows:
            w.writerow(row)

    n_total = sum(1 for r in rows if r["within_1pct"] != "n/a")
    n_within = sum(1 for r in rows if r["within_1pct"] == "1")
    rel_errs = np.array([
        float(r["rel_err_pct"]) for r in rows if r["within_1pct"] != "n/a"
    ])
    print(f"wrote {out_path} ({len(rows)} rows)")
    print(
        f"summary: {n_within}/{n_total} (bus, phase) entries within 1 % of "
        f"Kersting Tab. 4.10; mean rel-err {rel_errs.mean():.3f} %, "
        f"median {np.median(rel_errs):.3f} %, max {rel_errs.max():.3f} %"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
