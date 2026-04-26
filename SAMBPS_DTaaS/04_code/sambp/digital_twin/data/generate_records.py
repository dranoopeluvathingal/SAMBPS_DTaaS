#!/usr/bin/env python3
# =============================================================================
# sambp / digital_twin / data / generate_records.py
#
# Standalone script: generate 50 synthetic COMTRADE fault records covering
# the SAMBP TR-76 test matrix and update data/field_records/record_index.yaml.
#
# Usage
# -----
#   python data/generate_records.py           # run from digital_twin root
#   python data/generate_records.py --seed 99 # reproducible run
#   python data/generate_records.py --dry-run # print matrix, don't write files
#
# Output
# ------
#   data/field_records/synthetic/<record_id>.cfg
#   data/field_records/synthetic/<record_id>.dat
#   data/field_records/record_index.yaml        (updated in-place)
# =============================================================================

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

# Make digital_twin packages importable when run from the package root
_HERE = Path(__file__).resolve().parent.parent   # digital_twin/
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

from data.synthetic_comtrade_generator import (
    SyntheticComtradeGenerator,
    VALID_FAULT_TYPES,
    VALID_IBR_TYPES,
)


# ---------------------------------------------------------------------------
# Test matrix definition
# ---------------------------------------------------------------------------

# Realistic IBR penetration levels [%]
IBR_PENETRATIONS = [20, 40, 60, 80]

# Grid strengths (SCR)
SCRS = [3, 5, 10, 20]

# Nominal grid voltage [kV]
GRID_VOLTAGE_KV = 66.0

# Target: 50 records. Distribute across fault_types × ibr_types realistically.
# Some combinations are more likely in SP Group's network:
#   - GFL/PV dominate at high penetration
#   - SG present at all penetrations
#   - BESS increasingly common
# We use a weighted sampling scheme to hit 50 distinct records.

FAULT_IBR_MATRIX = [
    # (fault_type, ibr_type, k_pct, scr)  — curated 50-record set
    # ---- SLG (most common, ~40% of faults) ----
    ("SLG",  "SG",   20,  5),
    ("SLG",  "GFL",  40,  5),
    ("SLG",  "GFL",  60, 10),
    ("SLG",  "GFM",  40,  5),
    ("SLG",  "PV",   60,  3),
    ("SLG",  "PV",   80,  3),
    ("SLG",  "BESS", 40, 10),
    ("SLG",  "DFIG", 40,  5),
    ("SLG",  "DFIG", 60,  5),
    ("SLG",  "GFM",  80,  3),
    # ---- LL (phase-to-phase, ~20%) ----
    ("LL",   "SG",   20, 20),
    ("LL",   "GFL",  40,  5),
    ("LL",   "GFL",  60,  3),
    ("LL",   "PV",   60,  3),
    ("LL",   "GFM",  40, 10),
    ("LL",   "BESS", 60, 10),
    ("LL",   "DFIG", 40,  5),
    ("LL",   "PV",   80,  3),
    # ---- DLG (double-line-to-ground, ~15%) ----
    ("DLG",  "SG",   20,  5),
    ("DLG",  "GFL",  40,  5),
    ("DLG",  "PV",   60,  3),
    ("DLG",  "GFM",  40, 10),
    ("DLG",  "BESS", 40,  5),
    ("DLG",  "DFIG", 60,  5),
    ("DLG",  "GFL",  80,  3),
    # ---- 3PH (three-phase, ~15%) ----
    ("3PH",  "SG",   20, 20),
    ("3PH",  "GFL",  40,  5),
    ("3PH",  "GFM",  40,  5),
    ("3PH",  "PV",   60,  3),
    ("3PH",  "BESS", 60, 10),
    ("3PH",  "DFIG", 40,  5),
    ("3PH",  "GFL",  80,  3),
    ("3PH",  "GFM",  80,  3),
    # ---- Evolving faults (SLG → DLG, ~5%) ----
    ("evolving_SLG_to_DLG", "GFL",  40,  5),
    ("evolving_SLG_to_DLG", "PV",   60,  3),
    ("evolving_SLG_to_DLG", "GFM",  40, 10),
    ("evolving_SLG_to_DLG", "BESS", 40,  5),
    # ---- Cross-country faults (~5%) ----
    ("cross_country", "SG",   20, 20),
    ("cross_country", "GFL",  40,  5),
    ("cross_country", "PV",   60,  3),
    ("cross_country", "GFM",  40, 10),
    # ---- High IBR penetration stress cases ----
    ("SLG",  "PV",   80,  3),
    ("3PH",  "GFL",  80,  3),
    ("LL",   "GFL",  80,  3),
    ("DLG",  "PV",   80,  3),
    # ---- Weak grid stress cases (SCR=3) ----
    ("SLG",  "GFM",  60,  3),
    ("3PH",  "BESS", 80,  3),
    ("LL",   "DFIG", 60,  3),
    ("DLG",  "GFM",  60,  3),
    ("SLG",  "BESS", 80,  3),
]

assert len(FAULT_IBR_MATRIX) == 50, f"Expected 50 records, got {len(FAULT_IBR_MATRIX)}"


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

INDEX_PATH = Path(__file__).parent / "field_records" / "record_index.yaml"
SYNTHETIC_DIR = Path(__file__).parent / "field_records" / "synthetic"


def _load_index() -> dict:
    if INDEX_PATH.exists():
        with INDEX_PATH.open() as fh:
            data = yaml.safe_load(fh) or {}
        if "records" not in data:
            data["records"] = []
        return data
    return {"records": []}


def _save_index(data: dict) -> None:
    with INDEX_PATH.open("w") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _existing_ids(data: dict) -> set:
    return {r["record_id"] for r in data.get("records", [])}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_matrix(seed: int, dry_run: bool) -> None:
    gen   = SyntheticComtradeGenerator(output_dir=str(SYNTHETIC_DIR), seed=seed)
    index = _load_index()
    existing = _existing_ids(index)

    total   = len(FAULT_IBR_MATRIX)
    written = 0
    skipped = 0

    print(f"\n{'='*64}")
    print(f"  SAMBP TR-76 synthetic COMTRADE generator")
    print(f"  Target: {total} records → {SYNTHETIC_DIR}")
    print(f"{'='*64}")

    t0 = time.time()
    for i, (fault_type, ibr_type, k_pct, scr) in enumerate(FAULT_IBR_MATRIX, start=1):
        record_id = (f"syn_{i:04d}_{fault_type}_{ibr_type}"
                     f"_k{k_pct:02d}_scr{scr:02d}")
        k_frac = k_pct / 100.0

        if record_id in existing:
            print(f"  [{i:>2}/{total}] SKIP (already indexed): {record_id}")
            skipped += 1
            continue

        print(f"  [{i:>2}/{total}] {fault_type:<22} {ibr_type:<5} "
              f"k={k_pct:>2d}%  SCR={scr:>2d}  → ", end="", flush=True)

        if dry_run:
            print("DRY RUN")
            continue

        cfg_path, dat_path = gen.generate_fault_record(
            fault_type=fault_type,
            ibr_type=ibr_type,
            ibr_penetration=k_frac,
            grid_strength=float(scr),
            record_id=record_id,
        )

        # Make paths relative to repo root (digital_twin parent)
        rel_cfg = Path(cfg_path).relative_to(_HERE)
        rel_dat = Path(dat_path).relative_to(_HERE)

        entry = {
            "record_id":           record_id,
            "fault_type":          fault_type,
            "ibr_type":            ibr_type,
            "ibr_penetration_pct": float(k_pct),
            "scr":                 float(scr),
            "grid_voltage_kv":     GRID_VOLTAGE_KV,
            "cfg_path":            str(rel_cfg),
            "dat_path":            str(rel_dat),
            "source":              "synthetic",
            "notes":               f"seed={seed}",
        }
        index["records"].append(entry)
        existing.add(record_id)
        written += 1
        print(f"{Path(cfg_path).name}")

    if not dry_run:
        _save_index(index)

    elapsed = time.time() - t0
    print(f"\n{'='*64}")
    print(f"  Done in {elapsed:.1f}s  |  written={written}  skipped={skipped}")
    if not dry_run:
        print(f"  Index updated: {INDEX_PATH}")
    print(f"{'='*64}\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate synthetic COMTRADE records (TR-76)")
    p.add_argument("--seed",    type=int,  default=42,    help="RNG seed (default 42)")
    p.add_argument("--dry-run", action="store_true",      help="Print matrix without writing files")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_matrix(seed=args.seed, dry_run=args.dry_run)
