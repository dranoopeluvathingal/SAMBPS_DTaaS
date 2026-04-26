"""
TR-87 runner: PSCAD → SAMBP EMT Replay + COMTRADE C37.111 ingest demo.

This script demonstrates the two halves of TR-87:
  (a) PSCAD CSV → comtrade_adapter → SAMBP FaultCase
  (b) COMTRADE field recording → comtrade_adapter → SAMBP FaultCase

For each source it:
  1. Reads waveforms via comtrade_adapter
  2. Extracts relay-bus 3-phase abc waveforms at fs=10 kHz
  3. Validates FaultCase schema against andes_adapter output format
  4. Reports channel inventory, sample rate, window, and metadata
  5. Writes a JSON summary to TR-87 output directory

Usage
-----
  python tr87_pscad_emt_runner.py [--demo]  # uses synthetic waveforms
  python tr87_pscad_emt_runner.py --cfg  path/to/record.cfg
  python tr87_pscad_emt_runner.py --csv  path/to/pscad_export.csv
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2]))   # sambp/
from io_utils.comtrade_adapter import (
    build_fault_case,
    extract_relay_waveforms,
    run_full_pipeline,
    scan_fault_waveform_dir,
    ComtradeResult,
)

_OUT = Path(__file__).parents[4] / \
    "03_technical_reports/phase_8_advanced_extensions/TR87_pscad_emt_replay"
_DATA = Path(__file__).parents[4] / "05_data/fault_waveforms"
_FS   = 10_000.0   # SAMBP target sample rate [Hz]

# ── Synthetic waveform generator (used when no real data available) ──────────

def _make_synthetic_waveform(
    fault_type: str = "3PH",
    f0: float = 50.0,
    fs: float = 10_000.0,
    t_total: float = 0.20,
    t_fault: float = 0.05,
    t_clear: float = 0.12,
    V_pre: float = 1.0,
    I_fault: float = 8.0,
    R_f: float = 0.0,
) -> ComtradeResult:
    """
    Generate a synthetic 3-phase fault waveform and wrap as ComtradeResult.
    Replicates the PSCAD export CSV format so the adapter is exercised end-to-end.
    """
    t = np.arange(0.0, t_total, 1.0 / fs)
    N = len(t)
    omega = 2 * math.pi * f0

    def _v(phi):
        v = V_pre * math.sqrt(2) * np.cos(omega * t + phi)
        # Voltage dip during fault
        mask = (t >= t_fault) & (t < t_clear)
        depth = 0.7 if fault_type == "3PH" else 0.4
        v[mask] *= (1.0 - depth * math.exp(-R_f))
        return v

    def _i(phi):
        i = np.zeros(N)
        mask = (t >= t_fault) & (t < t_clear)
        # Exponentially decaying DC offset + AC fault current
        tau = 0.02
        dt_f = t[mask] - t_fault
        i[mask] = (I_fault * math.sqrt(2) * np.cos(omega * t[mask] + phi)
                   + I_fault * 0.5 * np.exp(-dt_f / tau))
        return i

    va = _v(0);           vb = _v(-2*math.pi/3); vc = _v(2*math.pi/3)
    ia = _i(0);           ib = _i(-2*math.pi/3); ic = _i(2*math.pi/3)

    if fault_type == "SLG":
        # Phase A only — B and C unaffected
        ib[:] = 0.1 * math.sqrt(2) * np.cos(omega * t)
        ic[:] = ib.copy()

    channels = {"Va": va, "Vb": vb, "Vc": vc,
                "Ia": ia, "Ib": ib, "Ic": ic}

    return ComtradeResult(
        t=t, channels=channels, fs=fs,
        meta={
            "station_name": f"SYNTHETIC_{fault_type}",
            "start_time": "0.000000s",
            "frequency": f0,
            "npts": N,
            "n_channels": 6,
        },
        source="synthetic",
        source_file="<generated>",
    )


# ── Validation ───────────────────────────────────────────────────────────────

_REQUIRED_KEYS = {"t", "ia", "ib", "ic", "va", "vb", "vc",
                  "fault_type", "fault_R_pu", "label", "meta", "source"}

def _validate_fault_case(fc: dict, label: str) -> bool:
    missing = _REQUIRED_KEYS - set(fc.keys())
    if missing:
        print(f"  [FAIL] {label}: missing keys {missing}")
        return False
    for key in ("t", "ia", "ib", "ic", "va", "vb", "vc"):
        if not isinstance(fc[key], np.ndarray) or len(fc[key]) == 0:
            print(f"  [FAIL] {label}: key '{key}' empty or wrong type")
            return False
    print(f"  [PASS] {label}: {len(fc['t'])} samples, "
          f"fs={1/(fc['t'][1]-fc['t'][0]):.0f} Hz, "
          f"fault_type={fc['fault_type']}, source={fc['source']}")
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def run(args=None):
    print("=" * 64)
    print("TR-87  PSCAD→SAMBP EMT Replay + COMTRADE C37.111 Ingest")
    print("=" * 64)

    results_summary = []

    # ── 1. Demo mode: synthetic waveforms ─────────────────────────────────
    if args is None or args.demo or (not args.cfg and not args.csv):
        print("\n[DEMO] Generating synthetic fault waveforms …")
        for ft in ("3PH", "SLG"):
            cr = _make_synthetic_waveform(fault_type=ft)
            wf = extract_relay_waveforms(cr, relay_name="", fs_out=_FS)
            fc = build_fault_case(wf, fault_type=ft, fault_R_pu=0.0,
                                  label=f"SYNTHETIC_{ft}")
            ok = _validate_fault_case(fc, f"Synthetic {ft}")
            results_summary.append({
                "label": fc["label"], "source": "synthetic",
                "fault_type": ft, "npts": int(len(fc["t"])),
                "pass": ok,
            })

    # ── 2. COMTRADE field recording ────────────────────────────────────────
    if args is not None and args.cfg:
        print(f"\n[COMTRADE] Loading {args.cfg} …")
        try:
            fc = run_full_pipeline(args.cfg, relay_name=getattr(args, "relay", ""),
                                   fault_type=getattr(args, "fault_type", "3PH"),
                                   fs_out=_FS)
            ok = _validate_fault_case(fc, Path(args.cfg).stem)
            results_summary.append({
                "label": fc["label"], "source": "comtrade",
                "fault_type": fc["fault_type"],
                "npts": int(len(fc["t"])), "pass": ok,
            })
        except Exception as e:
            print(f"  [ERROR] {e}")
            results_summary.append({"label": args.cfg, "pass": False, "error": str(e)})

    # ── 3. PSCAD CSV ───────────────────────────────────────────────────────
    if args is not None and args.csv:
        print(f"\n[PSCAD CSV] Loading {args.csv} …")
        try:
            fc = run_full_pipeline(args.csv, relay_name=getattr(args, "relay", ""),
                                   fault_type=getattr(args, "fault_type", "3PH"),
                                   fs_out=_FS)
            ok = _validate_fault_case(fc, Path(args.csv).stem)
            results_summary.append({
                "label": fc["label"], "source": "pscad",
                "fault_type": fc["fault_type"],
                "npts": int(len(fc["t"])), "pass": ok,
            })
        except Exception as e:
            print(f"  [ERROR] {e}")
            results_summary.append({"label": args.csv, "pass": False, "error": str(e)})

    # ── 4. Scan data directory ─────────────────────────────────────────────
    print(f"\n[SCAN] Fault waveform directory: {_DATA}")
    found = scan_fault_waveform_dir(str(_DATA))
    if found:
        print(f"  Found {len(found)} file(s):")
        for f in found:
            print(f"    {f['source_type']:10s}  {f['path']}")
    else:
        print("  Directory empty — no field recordings loaded yet.")
        print("  Drop COMTRADE (.cfg/.dat) or PSCAD (.csv) files into:")
        print(f"  {_DATA}")

    # ── 5. Save summary ───────────────────────────────────────────────────
    _OUT.mkdir(parents=True, exist_ok=True)
    out_json = _OUT / "tr87_results.json"
    with open(out_json, "w") as f:
        json.dump({
            "tr": "TR-87",
            "title": "PSCAD→SAMBP EMT Replay + COMTRADE C37.111 Ingest",
            "adapter": "io_utils/comtrade_adapter.py",
            "data_dir": str(_DATA),
            "results": results_summary,
        }, f, indent=2)
    print(f"\nSummary written: {out_json}")

    n_pass = sum(r.get("pass", False) for r in results_summary)
    print(f"\n{'='*64}")
    print(f"TR-87  {n_pass}/{len(results_summary)} cases PASS")
    return results_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TR-87 COMTRADE/PSCAD adapter demo")
    parser.add_argument("--cfg",  help="COMTRADE .cfg file path")
    parser.add_argument("--csv",  help="PSCAD CSV file path")
    parser.add_argument("--relay", default="", help="Relay channel prefix")
    parser.add_argument("--fault-type", default="3PH")
    parser.add_argument("--demo", action="store_true",
                        help="Run synthetic demo (default when no files given)")
    run(parser.parse_args())
