"""
run_goose_study.py
===================
SAMBP GOOSE Integration Study — TR-06/2026

Extends the system selectivity study (TR-05) with IEC 61850 GOOSE
messaging.  For each fault scenario:

  1. Computes per-relay detection times from CT waveforms.
  2. Simulates GOOSE publication and delivery (1-ms discrete time).
  3. Applies zone-acceleration logic.
  4. Records total fault clearance times.

A sensitivity study sweeps network latency (0.5 ms, 1.0 ms, 2.0 ms)
and packet loss (0%, 1%) to quantify GOOSE latency impact on clearance.
"""

from __future__ import annotations

import sys, os, math
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from network.radial_network import generate_network_snapshot, FAULT_LOCATIONS
from goose.goose_engine import GooseBrokerConfig
from goose.sambp_goose_coordinator import (
    run_goose_coordination, GooseCoordinatorResult, GooseRelayResult,
)

FAULT_TYPES  = ["3ph", "ag"]
RELAY_ORDER  = ["OC", "87B_A", "87L", "87B_B", "87T"]

# ---------------------------------------------------------------------------
# Nominal broker configuration
# ---------------------------------------------------------------------------

NOMINAL_CFG = GooseBrokerConfig(
    base_latency_ms = 1.0,
    jitter_ms       = 0.3,
    loss_prob       = 0.0,
    seed            = 42,
)

# ---------------------------------------------------------------------------
# Run full study
# ---------------------------------------------------------------------------

def run_study(broker_cfg: GooseBrokerConfig | None = None) -> list[GooseCoordinatorResult]:
    if broker_cfg is None:
        broker_cfg = NOMINAL_CFG
    results = []
    for loc in FAULT_LOCATIONS:
        for ftype in FAULT_TYPES:
            snap   = generate_network_snapshot(loc, ftype)
            result = run_goose_coordination(snap, broker_cfg)
            results.append(result)
    return results


# ---------------------------------------------------------------------------
# Print clearance table
# ---------------------------------------------------------------------------

def print_clearance_table(results: list[GooseCoordinatorResult]) -> None:
    print(f"\n{'Scenario':<26}  {'Fastest [ms]':>12}  {'Tripped relays':<30}  "
          f"{'GOOSE events':>12}")
    print("-" * 95)
    for res in results:
        label   = f"{res.fault_loc}/{res.fault_type}"
        fastest = res.fastest_clear_ms()
        fstr    = f"{fastest:.1f}" if math.isfinite(fastest) else " n/a"
        trips   = ", ".join(res.tripped_relays) or "(none)"
        n_ev    = len(res.goose_events)
        print(f"{label:<26}  {fstr:>12}  {trips:<30}  {n_ev:>12}")


def print_relay_timing_table(results: list[GooseCoordinatorResult]) -> None:
    print(f"\n{'Scenario':<26}  {'Relay':<7}  {'t_det[ms]':>9}  "
          f"{'t_pub[ms]':>9}  {'t_clear[ms]':>11}  {'Accel':>5}  Source")
    print("-" * 95)
    for res in results:
        label = f"{res.fault_loc}/{res.fault_type}"
        for r in res.relay_results:
            if not r.final_trip:
                continue
            t_d = f"{r.t_detect_ms:7.1f}" if math.isfinite(r.t_detect_ms) else "    n/a"
            t_p = f"{r.t_goose_pub_ms:7.1f}" if math.isfinite(r.t_goose_pub_ms) else "    n/a"
            t_c = f"{r.t_clear_ms:9.1f}" if math.isfinite(r.t_clear_ms) else "      n/a"
            acc = "  YES" if r.accelerated else "   no"
            print(f"{label:<26}  {r.relay_id:<7}  {t_d}  {t_p}  {t_c}  {acc}  "
                  f"{r.source}")
    print()


# ---------------------------------------------------------------------------
# Latency sensitivity sweep
# ---------------------------------------------------------------------------

def run_latency_sweep() -> dict:
    """Sweep latency and loss; return {config_label: [fastest_clear_ms, ...]}."""
    configs = {
        "LAN 0.5ms / 0%":  GooseBrokerConfig(0.5, 0.1, 0.00, seed=42),
        "LAN 1.0ms / 0%":  GooseBrokerConfig(1.0, 0.3, 0.00, seed=42),
        "LAN 2.0ms / 0%":  GooseBrokerConfig(2.0, 0.5, 0.00, seed=42),
        "WAN 5.0ms / 0%":  GooseBrokerConfig(5.0, 1.0, 0.00, seed=42),
        "LAN 1.0ms / 1%":  GooseBrokerConfig(1.0, 0.3, 0.01, seed=42),
    }
    sweep_results = {}
    for label, cfg in configs.items():
        res   = run_study(cfg)
        times = [r.fastest_clear_ms() for r in res]
        sweep_results[label] = times
    return sweep_results


def print_latency_sweep(sweep: dict) -> None:
    locs   = [f"{loc}/{ft}" for loc in FAULT_LOCATIONS for ft in FAULT_TYPES]
    header = f"{'Scenario':<26}" + "".join(f"  {lbl:>18}" for lbl in sweep)
    print("\n--- Latency Sensitivity Sweep (fastest clearance [ms]) ---")
    print(header)
    print("-" * (26 + 20 * len(sweep)))
    for i, loc in enumerate(locs):
        row = f"{loc:<26}"
        for times in sweep.values():
            t = times[i]
            row += f"  {t:>16.1f}" if math.isfinite(t) else f"  {'n/a':>16}"
        print(row)


# ---------------------------------------------------------------------------
# GOOSE event log (first scenario)
# ---------------------------------------------------------------------------

def print_goose_event_log(result: GooseCoordinatorResult, max_events: int = 20) -> None:
    print(f"\n--- GOOSE Event Log: {result.fault_loc}/{result.fault_type} ---")
    print(f"{'t [ms]':>8}  {'Source':>8}  {'Dest':>8}  Event")
    print("-" * 45)
    for i, ev in enumerate(result.goose_events[:max_events]):
        t_s, src, dst, etype = ev
        print(f"{t_s:8.1f}  {str(src):>8}  {str(dst):>8}  {etype}")
    if len(result.goose_events) > max_events:
        print(f"  ... ({len(result.goose_events)} total events)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 95)
    print("SAMBP GOOSE Integration Study — TR-06/2026")
    print("IEC 61850-8-1 GOOSE simulation with SAMBP zone-state messaging")
    print("=" * 95)

    # ---- Nominal study -------------------------------------------------------
    print("\n[1] Nominal GOOSE study (LAN 1.0 ms latency, 0% loss)")
    results = run_study(NOMINAL_CFG)
    print_clearance_table(results)
    print_relay_timing_table(results)

    # ---- GOOSE event log for bus_A/3ph (first scenario) ---------------------
    print_goose_event_log(results[0])

    # ---- Latency sweep -------------------------------------------------------
    print("\n[2] Latency sensitivity sweep")
    sweep = run_latency_sweep()
    print_latency_sweep(sweep)

    # ---- Summary statistics --------------------------------------------------
    nom_times  = [r.fastest_clear_ms() for r in results
                  if math.isfinite(r.fastest_clear_ms())]
    print(f"\n[3] Summary statistics (nominal LAN 1.0 ms)")
    print(f"    Scenarios      : {len(results)}")
    print(f"    Clearance min  : {min(nom_times):.1f} ms")
    print(f"    Clearance max  : {max(nom_times):.1f} ms")
    print(f"    Clearance mean : {np.mean(nom_times):.1f} ms")
    print(f"    CB operate     : 40.0 ms (assumed)")
    print(f"    GOOSE overhead : ~{NOMINAL_CFG.base_latency_ms + 1.0:.1f} ms "
          f"(net + IED proc)")

    print("\n" + "=" * 95)
    print("RESULT: GOOSE integration study COMPLETE.")
    print("=" * 95)
