"""
run_ct_study.py
================
SAMBP TR-10/2026 — CT Saturation Injection Study

Tests the Stage-2 confidence gate's core function: suppressing spurious
87B/87L/87T trips caused by CT saturation on through-current feeders,
while maintaining sensitivity on internal faults under concurrent CT
saturation of the fault-current CT.

CT Saturation Model
-------------------
A saturated CT output is modelled as:

    i_CT_sat(t) = i_true(t) + ε_CT · I_peak · sgn(sin(ω t + φ))

The second term is a bipolar square wave at power frequency that represents
the clipping distortion of a saturated core.  When the differential zone
sums CT outputs, any feeder with ε_CT > 0 contributes apparent differential.

Study Design
------------
Two test families, each 200 trials × 10 scenarios:

  Family A — External-fault / CT saturation (should NOT trip):
    For each external-fault scenario, the feeder carrying the largest
    through-current is injected with ε_CT ~ U(ε_min, ε_max).  The
    conventional relay will trip for ε_CT above its pickup; the Stage-2
    gate should veto by detecting ε_CT > 0.

  Family B — Internal fault + concurrent CT saturation (should trip):
    For each internal-fault scenario, the differential CT (which carries
    the fault current) is injected with ε_CT ~ U(0, 0.15).  Saturation
    degrades the waveform quality but the fault must still be detected.

Metrics:
    External-fault FPR:   fraction of CT-sat external trials that trip.
    Internal-fault TPR:   fraction of CT-sat internal trials that trip.
    Veto accuracy:        fraction of vetoes that were correct.

Threshold sweep:
    ε_CT is swept over [0.02, 0.05, 0.10, 0.15, 0.20, 0.25] to
    characterise the Stage-2 gate's ε_CT detection threshold.
"""

from __future__ import annotations

import sys, os
import numpy as np
from dataclasses import dataclass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))

from network.radial_network import (
    generate_network_snapshot, FAULT_LOCATIONS, NetworkSnapshot
)
from coordinator.system_coordinator import run_system_coordination
from run_system_study import EXPECTED_TRIPS

FAULT_TYPES = ["3ph", "ag"]
N_TRIALS    = 200
RNG_SEED    = 2026

# ε_CT levels for threshold sweep (fraction of fundamental amplitude)
EPSILONS = [0.00, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25]

RELAY_ORDER = ["OC", "87B_A", "87L", "87B_B", "87T"]


# ---------------------------------------------------------------------------
# CT saturation injection
# ---------------------------------------------------------------------------

def inject_ct_saturation(
    w: np.ndarray,
    epsilon_ct: float,
    fault_inception_s: float = 0.02,
    freq_hz: float = 50.0,
) -> np.ndarray:
    """
    Add bipolar square-wave CT saturation distortion to a (3, N) waveform.

    The distortion begins at fault inception (t >= fault_inception_s):

        i_CT_sat[k](t) = i_true[k](t)
                       + ε_CT · I_peak[k] · sgn(sin(2π f (t - t_fault) + φ_k))

    where φ_k ∈ {0, −2π/3, +2π/3} are the per-phase template phases and
    I_peak[k] = max|i_true[k]|.

    Parameters
    ----------
    w            : (3, N) nominal waveform array
    epsilon_ct   : saturation factor ε_CT ∈ [0, 1]
    fault_inception_s : fault inception time [s]

    Returns
    -------
    (3, N) waveform with CT saturation injected.
    """
    if epsilon_ct < 1e-9:
        return w.copy()

    result = w.copy()
    N = w.shape[1]
    t  = np.linspace(0, (N - 1) / 1000.0, N)   # 1 kHz sampling
    dt = t - fault_inception_s
    mask = dt >= 0
    ph  = [0.0, -2*np.pi/3, 2*np.pi/3]

    for k, p in enumerate(ph):
        w_k   = w[k, :]
        I_pk  = np.max(np.abs(w_k))
        if I_pk < 1e-9:
            continue
        # Bipolar square wave: +1 in positive half-cycle, -1 in negative
        sq = np.sign(np.sin(2 * np.pi * freq_hz * dt + p))
        sq[~mask] = 0.0
        result[k, :] += epsilon_ct * I_pk * sq

    return result


def inject_into_snapshot_external(
    snap: NetworkSnapshot,
    relay_id: str,
    epsilon_ct: float,
) -> NetworkSnapshot:
    """
    Inject CT saturation into the largest through-current feeder for a
    given relay zone.  Used for external-fault (should-NOT-trip) scenarios.

    Relay zones and their feeders:
        87B_A : i_B_A_feeders — inject into the feeder with max |I|
        87L   : i_L_near_pu or i_L_far_pu — inject into the larger
        87B_B : i_B_B_feeders — inject into the feeder with max |I|
        87T   : i_T_H_pu — inject into the HV winding CT
    """
    kwargs = dict(
        fault_loc  = snap.fault_loc,
        fault_type = snap.fault_type,
        time_s     = snap.time_s,
        i_oc_pu    = snap.i_oc_pu,
        i_B_A_feeders = list(snap.i_B_A_feeders),
        i_L_near_pu   = snap.i_L_near_pu,
        i_L_far_pu    = snap.i_L_far_pu,
        i_B_B_feeders = list(snap.i_B_B_feeders),
        i_T_H_pu      = snap.i_T_H_pu,
        i_T_X_pu      = snap.i_T_X_pu,
        I_fault_pu    = snap.I_fault_pu,
    )

    if relay_id == "87B_A":
        # Inject into the feeder with the largest peak current
        peaks = [np.max(np.abs(f)) for f in snap.i_B_A_feeders]
        idx = int(np.argmax(peaks))
        feeders = list(snap.i_B_A_feeders)
        feeders[idx] = inject_ct_saturation(feeders[idx], epsilon_ct)
        kwargs["i_B_A_feeders"] = feeders

    elif relay_id == "87L":
        # Inject into whichever terminal has the larger through-current
        if np.max(np.abs(snap.i_L_near_pu)) >= np.max(np.abs(snap.i_L_far_pu)):
            kwargs["i_L_near_pu"] = inject_ct_saturation(snap.i_L_near_pu, epsilon_ct)
        else:
            kwargs["i_L_far_pu"] = inject_ct_saturation(snap.i_L_far_pu, epsilon_ct)

    elif relay_id == "87B_B":
        peaks = [np.max(np.abs(f)) for f in snap.i_B_B_feeders]
        idx = int(np.argmax(peaks))
        feeders = list(snap.i_B_B_feeders)
        feeders[idx] = inject_ct_saturation(feeders[idx], epsilon_ct)
        kwargs["i_B_B_feeders"] = feeders

    elif relay_id == "87T":
        kwargs["i_T_H_pu"] = inject_ct_saturation(snap.i_T_H_pu, epsilon_ct)

    return NetworkSnapshot(**kwargs)


def inject_into_snapshot_internal(
    snap: NetworkSnapshot,
    relay_id: str,
    epsilon_ct: float,
) -> NetworkSnapshot:
    """
    Inject CT saturation into the differential-current CT for an internal
    fault scenario.  Used for should-trip scenarios.

    For internal faults the differential CT carries the fault current,
    so saturation degrades the differential waveform quality.
    """
    kwargs = dict(
        fault_loc  = snap.fault_loc,
        fault_type = snap.fault_type,
        time_s     = snap.time_s,
        i_oc_pu    = snap.i_oc_pu,
        i_B_A_feeders = list(snap.i_B_A_feeders),
        i_L_near_pu   = snap.i_L_near_pu,
        i_L_far_pu    = snap.i_L_far_pu,
        i_B_B_feeders = list(snap.i_B_B_feeders),
        i_T_H_pu      = snap.i_T_H_pu,
        i_T_X_pu      = snap.i_T_X_pu,
        I_fault_pu    = snap.I_fault_pu,
    )

    if relay_id == "87B_A":
        # Inject into all bus-A feeders (all CTs on the faulted bus saturate)
        kwargs["i_B_A_feeders"] = [
            inject_ct_saturation(f, epsilon_ct) for f in snap.i_B_A_feeders
        ]
    elif relay_id == "87L":
        kwargs["i_L_near_pu"] = inject_ct_saturation(snap.i_L_near_pu, epsilon_ct)
        kwargs["i_L_far_pu"]  = inject_ct_saturation(snap.i_L_far_pu,  epsilon_ct)
    elif relay_id == "87B_B":
        kwargs["i_B_B_feeders"] = [
            inject_ct_saturation(f, epsilon_ct) for f in snap.i_B_B_feeders
        ]
    elif relay_id == "87T":
        kwargs["i_T_H_pu"] = inject_ct_saturation(snap.i_T_H_pu, epsilon_ct)

    return NetworkSnapshot(**kwargs)


# ---------------------------------------------------------------------------
# Single-ε sweep for one scenario × relay
# ---------------------------------------------------------------------------

@dataclass
class CTSatResult:
    scenario:     str
    relay_id:     str
    epsilon_ct:   float
    family:       str       # "external" or "internal"
    n_trials:     int
    conv_trips:   int
    sambp_trips:  int
    sambp_vetoes: int

    @property
    def conv_rate(self) -> float:
        return self.conv_trips / self.n_trials

    @property
    def sambp_rate(self) -> float:
        return self.sambp_trips / self.n_trials

    @property
    def veto_rate(self) -> float:
        return self.sambp_vetoes / self.n_trials


def run_epsilon_sweep(
    scenario_key: str,
    fault_loc: str,
    fault_type: str,
    relay_id: str,
    family: str,
    epsilons: list[float],
    n_trials: int,
    rng_seed: int,
) -> list[CTSatResult]:
    """
    Run CT saturation sweep for one scenario × relay × family.
    Returns one CTSatResult per ε_CT level.
    """
    snap_nom = generate_network_snapshot(fault_loc, fault_type)
    rng = np.random.default_rng(rng_seed)

    inject_fn = (inject_into_snapshot_internal
                 if family == "internal" else inject_into_snapshot_external)

    results = []
    for eps in epsilons:
        conv_trips = 0
        sambp_trips = 0
        sambp_vetoes = 0

        for _ in range(n_trials):
            # Small amplitude jitter (±5%) to avoid all-identical trials
            delta_I = rng.uniform(-0.05, 0.05)
            snap_p = NetworkSnapshot(
                fault_loc     = snap_nom.fault_loc,
                fault_type    = snap_nom.fault_type,
                time_s        = snap_nom.time_s,
                i_oc_pu       = snap_nom.i_oc_pu * (1 + delta_I),
                i_B_A_feeders = [f * (1 + delta_I) for f in snap_nom.i_B_A_feeders],
                i_L_near_pu   = snap_nom.i_L_near_pu * (1 + delta_I),
                i_L_far_pu    = snap_nom.i_L_far_pu  * (1 + delta_I),
                i_B_B_feeders = [f * (1 + delta_I) for f in snap_nom.i_B_B_feeders],
                i_T_H_pu      = snap_nom.i_T_H_pu * (1 + delta_I),
                i_T_X_pu      = snap_nom.i_T_X_pu * (1 + delta_I),
                I_fault_pu    = snap_nom.I_fault_pu * (1 + delta_I),
            )
            snap_sat = inject_fn(snap_p, relay_id, eps)
            dec = run_system_coordination(snap_sat)
            rr  = {r.relay_id: r for r in dec.relay_results}

            if relay_id not in rr:
                continue
            r = rr[relay_id]
            if r.conv_trip:
                conv_trips += 1
            if r.final_trip:
                sambp_trips += 1
            if r.source == "model_veto":
                sambp_vetoes += 1

        results.append(CTSatResult(
            scenario     = scenario_key,
            relay_id     = relay_id,
            epsilon_ct   = eps,
            family       = family,
            n_trials     = n_trials,
            conv_trips   = conv_trips,
            sambp_trips  = sambp_trips,
            sambp_vetoes = sambp_vetoes,
        ))

    return results


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------

def main():
    print("=" * 90)
    print("SAMBP CT Saturation Injection Study — TR-10/2026")
    print(f"N_TRIALS = {N_TRIALS} per (scenario, relay, ε_CT)")
    print(f"ε_CT levels: {EPSILONS}")
    print("=" * 90)

    # Define test matrix
    # Family A: external fault scenarios (should NOT trip a specific relay)
    # Family B: internal fault scenarios (should trip a specific relay)
    test_matrix = [
        # (fault_loc,       fault_type, relay_id, family)
        ("bus_A",    "3ph",  "87B_A",  "internal"),
        ("bus_A",    "ag",   "87B_A",  "internal"),
        ("bus_A",    "3ph",  "87B_A",  "external"),   # external = line_mid fault, 87B_A should NOT trip
        ("line_mid", "3ph",  "87L",    "internal"),
        ("line_mid", "ag",   "87L",    "internal"),
        ("line_mid", "3ph",  "87L",    "external"),   # external = bus_A fault, 87L should NOT trip
        ("bus_B",    "3ph",  "87B_B",  "internal"),
        ("bus_B",    "3ph",  "87B_B",  "external"),   # external = transformer_hv fault, 87B_B should NOT trip
        ("transformer_hv", "3ph", "87T", "internal"),
        ("transformer_hv", "3ph", "87T", "external"), # external = bus_C_load fault, 87T should NOT trip
    ]

    # Re-map "external" family to the correct fault location
    external_map = {
        ("bus_A",    "87B_A"): ("line_mid",     "3ph"),
        ("line_mid", "87L"):   ("bus_A",         "3ph"),
        ("bus_B",    "87B_B"): ("transformer_hv","3ph"),
        ("transformer_hv", "87T"): ("bus_C_load","3ph"),
    }

    all_results: list[CTSatResult] = []

    for (fault_loc, fault_type, relay_id, family) in test_matrix:
        if family == "external":
            ext_loc, ext_type = external_map.get((fault_loc, relay_id),
                                                  (fault_loc, fault_type))
            scan_loc, scan_type = ext_loc, ext_type
        else:
            scan_loc, scan_type = fault_loc, fault_type

        key = f"{fault_loc}/{fault_type}/{relay_id}/{family}"
        print(f"  Sweeping {key} ...", end="", flush=True)
        res = run_epsilon_sweep(
            scenario_key = key,
            fault_loc    = scan_loc,
            fault_type   = scan_type,
            relay_id     = relay_id,
            family       = family,
            epsilons     = EPSILONS,
            n_trials     = N_TRIALS,
            rng_seed     = RNG_SEED,
        )
        all_results.extend(res)
        print(" done")

    # ---- Print threshold sweep table ----------------------------------------
    print()
    print(f"{'Scenario':<40}  {'ε_CT':>5}  "
          f"{'Conv':>6}  {'SAMBP':>6}  {'Veto%':>6}")
    print("-" * 75)

    cur_key = None
    for r in all_results:
        if r.scenario != cur_key:
            print()
            cur_key = r.scenario
        conv_rate  = r.conv_rate
        sambp_rate = r.sambp_rate
        veto_rate  = r.veto_rate
        flag = ""
        if r.family == "external" and conv_rate > 0 and sambp_rate == 0:
            flag = " [VETO OK]"
        elif r.family == "external" and sambp_rate > 0:
            flag = " [MISS]"
        elif r.family == "internal" and sambp_rate < 1.0:
            flag = " [TPR LOSS]"

        print(f"  {r.scenario:<38}  {r.epsilon_ct:5.2f}  "
              f"{conv_rate:6.3f}  {sambp_rate:6.3f}  {veto_rate:6.3f}{flag}")

    # ---- Aggregate by ε_CT level ---------------------------------------------
    print()
    print("--- Aggregate by ε_CT (all scenarios) ---")
    print(f"{'ε_CT':>6}  {'ExtFPR Conv':>12}  {'ExtFPR SAMBP':>13}  "
          f"{'IntTPR Conv':>12}  {'IntTPR SAMBP':>13}  {'Veto OK%':>9}")
    print("-" * 75)

    for eps in EPSILONS:
        subset = [r for r in all_results if abs(r.epsilon_ct - eps) < 1e-9]
        ext  = [r for r in subset if r.family == "external"]
        intr = [r for r in subset if r.family == "internal"]

        def agg_rate(rows, attr):
            total_n = sum(r.n_trials for r in rows)
            if total_n == 0: return float("nan")
            total_t = sum(getattr(r, attr)() if callable(getattr(r, attr))
                          else getattr(r, attr) * r.n_trials
                          for r in rows)
            # Actually use the integer counts
            return sum(getattr(r, attr.replace("_rate", "_trips") if "rate" in attr
                               else attr) for r in rows) / total_n

        def pool(rows, attr_trips):
            n  = sum(r.n_trials for r in rows)
            tr = sum(getattr(r, attr_trips) for r in rows)
            return tr / n if n > 0 else float("nan")

        ext_conv_fpr  = pool(ext,  "conv_trips")
        ext_sambp_fpr = pool(ext,  "sambp_trips")
        int_conv_tpr  = pool(intr, "conv_trips")
        int_sambp_tpr = pool(intr, "sambp_trips")

        # Correct veto rate: vetoes that were on external-fault scenarios
        total_vetoes   = sum(r.sambp_vetoes for r in subset)
        correct_vetoes = sum(r.sambp_vetoes for r in ext)
        veto_acc = correct_vetoes / total_vetoes if total_vetoes > 0 else float("nan")

        print(f"  {eps:5.2f}  {ext_conv_fpr:12.3f}  {ext_sambp_fpr:13.3f}  "
              f"{int_conv_tpr:12.3f}  {int_sambp_tpr:13.3f}  {veto_acc:9.3f}")

    print()
    print("=" * 90)
    print("RESULT: CT Saturation Injection Study COMPLETE.")
    print("=" * 90)


if __name__ == "__main__":
    main()
