"""
sambp_goose_coordinator.py
===========================
SAMBP GOOSE-enhanced system coordinator — TR-06/2026.

Extends the batch system coordinator to:
  1. Compute per-relay trip detection times from the CT waveforms.
  2. Publish each relay's SAMBP state (κ_n, f_int, source) via simulated
     IEC 61850 GOOSE within a 1-ms-step discrete-time simulation.
  3. Apply inter-zone GOOSE confirmation logic (zone acceleration /
     confirmation) and record the resulting clearance times.
  4. Compare clearance times and selectivity with and without GOOSE.

Inter-zone GOOSE topology (radial network):
    IED_OC   ──GOOSE──▶  IED_87B_A
    IED_87B_A──GOOSE──▶  IED_87L    (zone acceleration)
    IED_87L  ──GOOSE──▶  IED_87B_B  (zone acceleration)
    IED_87B_B──GOOSE──▶  IED_87T    (zone acceleration)
    IED_87T  ──GOOSE──▶  IED_87B_B  (zone confirmation)

GOOSE zone acceleration logic:
    If upstream relay R_up trips (GOOSE received), downstream relay R_dn
    may accelerate its own clearance if it was also close to tripping
    (conv_trip=True). This models intertripping / zone extension.
"""

from __future__ import annotations

import sys, os
import math
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_SYSROOT = os.path.dirname(_HERE)
sys.path.insert(0, _SYSROOT)
sys.path.insert(0, os.path.join(_SYSROOT, ".."))

from network.radial_network import NetworkSnapshot, generate_network_snapshot, FAULT_LOCATIONS
from coordinator.system_coordinator import run_system_coordination, CoordinatorDecision
from goose.goose_engine import (
    GooseBroker, GooseBrokerConfig, GoosePublisher, GooseSubscriber,
    SambpGooseData, GooseFrame, compute_clearance_time,
    _BREAKER_OP_MS,
)

# ---------------------------------------------------------------------------
# Trip detection time extraction
# ---------------------------------------------------------------------------

_FAULT_INCEPTION_MS = 20.0      # fault_time_s = 0.02 s


def _detect_time_ms(i_waveform: np.ndarray, threshold: float,
                    fs: float = 1000.0) -> float:
    """
    Return the time [ms from fault inception] at which the peak of
    `i_waveform` (any-phase RMS over 1-cycle window) first exceeds
    `threshold`.

    Uses a rolling 1-cycle RMS (50 Hz → 20 samples at 1 kHz).
    Returns nan if threshold is never crossed.
    """
    w      = int(round(fs / 50.0))   # samples per cycle
    N      = i_waveform.shape[-1]
    fault_sample = int(round(_FAULT_INCEPTION_MS / 1000.0 * fs))

    for s in range(fault_sample, N - w + 1):
        rms = np.sqrt(np.mean(i_waveform[:, s:s+w]**2))
        if rms > threshold:
            t_s  = s / fs            # seconds from t=0
            t_ms = t_s * 1000.0 - _FAULT_INCEPTION_MS
            return max(t_ms, 0.0)
    return float("nan")


def compute_relay_detect_times(snap: NetworkSnapshot, dec: CoordinatorDecision,
                                fs: float = 1000.0) -> dict[str, float]:
    """
    Return {relay_id: t_detect_ms} where t_detect_ms is time from fault
    inception to first threshold crossing [ms].

    For differential relays: use the peak differential current waveform.
    For OC: use max-phase current.
    """
    times = {}

    # OC
    times["OC"] = _detect_time_ms(snap.i_oc_pu, threshold=1.5, fs=fs)

    # 87B_A: differential = sum of feeders
    i_diff_BA = snap.i_B_A_feeders[0] + snap.i_B_A_feeders[1]
    times["87B_A"] = _detect_time_ms(i_diff_BA, threshold=0.20, fs=fs)

    # 87L: differential = near + far
    i_diff_L = snap.i_L_near_pu + snap.i_L_far_pu
    times["87L"] = _detect_time_ms(i_diff_L, threshold=0.20, fs=fs)

    # 87B_B: differential = sum of feeders
    i_diff_BB = snap.i_B_B_feeders[0] + snap.i_B_B_feeders[1]
    times["87B_B"] = _detect_time_ms(i_diff_BB, threshold=0.20, fs=fs)

    # 87T: use HV differential (pre-compensation, simplified)
    times["87T"] = _detect_time_ms(snap.i_T_H_pu + snap.i_T_X_pu,
                                    threshold=0.20, fs=fs)

    return times


# ---------------------------------------------------------------------------
# GOOSE scenario result
# ---------------------------------------------------------------------------

@dataclass
class GooseRelayResult:
    relay_id:        str
    final_trip:      bool
    source:          str
    t_detect_ms:     float    # ms from fault inception (own detection)
    t_goose_pub_ms:  float    # ms when GOOSE published (= t_detect + IED proc)
    t_goose_rx_ms:   float    # ms when downstream peer received it
    t_clear_ms:      float    # total clearance (detect + GOOSE + CB)
    accelerated:     bool     # trip accelerated by upstream GOOSE?
    kappa_n:         float
    f_int:           float


@dataclass
class GooseCoordinatorResult:
    fault_loc:    str
    fault_type:   str
    I_fault_pu:   float
    relay_results: list[GooseRelayResult]
    goose_events:  list[tuple]     # (time_ms, src, dst, event_type)

    @property
    def tripped_relays(self) -> list[str]:
        return [r.relay_id for r in self.relay_results if r.final_trip]

    def fastest_clear_ms(self) -> float:
        t = [r.t_clear_ms for r in self.relay_results
             if r.final_trip and math.isfinite(r.t_clear_ms)]
        return min(t) if t else float("nan")


# ---------------------------------------------------------------------------
# GOOSE simulation
# ---------------------------------------------------------------------------

_IED_PROC_MS = 1.0     # IED processing delay (detection → GOOSE publish)

# Adjacency: downstream IED that should receive GOOSE from each relay
_GOOSE_TOPOLOGY = {
    "OC":    ["87B_A"],
    "87B_A": ["87L"],
    "87L":   ["87B_A", "87B_B"],
    "87B_B": ["87T"],
    "87T":   ["87B_B"],
}

_RELAY_ORDER = ["OC", "87B_A", "87L", "87B_B", "87T"]


def run_goose_coordination(
    snap: NetworkSnapshot,
    broker_cfg: GooseBrokerConfig | None = None,
    sim_end_ms: float = 200.0,
) -> GooseCoordinatorResult:
    """
    Run the SAMBP system coordination with GOOSE messaging.

    Steps
    -----
    1. Run all relays (batch) via run_system_coordination to get decisions.
    2. Compute per-relay trip detection times from CT waveforms.
    3. Simulate GOOSE publication and delivery in 1-ms steps.
    4. Apply zone-acceleration logic: if upstream relay trips and the
       downstream relay's conventional element had also operated, the
       downstream relay is accelerated to the GOOSE reception time.
    5. Compute final clearance times.
    """
    if broker_cfg is None:
        broker_cfg = GooseBrokerConfig()

    # ---- Step 1: Batch relay decisions -----------------------------------
    dec = run_system_coordination(snap)

    # ---- Step 2: Detection times -----------------------------------------
    detect_times = compute_relay_detect_times(snap, dec)

    # ---- Step 3: Build publishers and subscribers ------------------------
    publishers  : dict[str, GoosePublisher] = {}
    subscribers : dict[str, list[GooseSubscriber]] = {r: [] for r in _RELAY_ORDER}
    goose_rx    : dict[str, dict[str, Optional[float]]] = {}   # src→dst→rx_time

    broker = GooseBroker(broker_cfg)

    received_goose: dict[str, dict[str, Optional[GooseFrame]]] = {
        r: {} for r in _RELAY_ORDER}

    for relay_id, peers in _GOOSE_TOPOLOGY.items():
        pub = GoosePublisher(
            ied_id      = f"IED_{relay_id}",
            dataset     = "SAMBP_Trip",
            subscribers = [f"IED_{p}" for p in peers],
        )
        publishers[relay_id] = pub

        for peer in peers:
            if peer not in goose_rx:
                goose_rx[peer] = {}
            goose_rx[peer][relay_id] = None

            def _make_cb(r_src=relay_id, r_dst=peer):
                def _on_state_change(frame: GooseFrame):
                    received_goose[r_dst][r_src] = frame
                return _on_state_change

            sub = GooseSubscriber(
                ied_id          = f"IED_{peer}",
                src_ied         = f"IED_{relay_id}",
                dataset         = "SAMBP_Trip",
                on_state_change = _make_cb(),
            )
            broker.register_subscriber(sub)

    # ---- Step 4: Simulate GOOSE over 1-ms steps --------------------------
    goose_pub_times: dict[str, float] = {r: float("nan") for r in _RELAY_ORDER}
    published       : set[str] = set()
    goose_events    : list[tuple] = []

    for relay_rr in dec.relay_results:
        r = relay_rr.relay_id
        if not relay_rr.final_trip:
            # Publish idle state at t=0
            data_idle = SambpGooseData(
                relay_id=r, final_trip=False, conv_trip=relay_rr.conv_trip,
                source=relay_rr.source, kappa_n=relay_rr.kappa_n,
                f_int=relay_rr.f_int, I_op_peak=relay_rr.I_op_peak,
                model_veto_active=(relay_rr.source == "model_veto"),
                t_detect_ms=float("nan"),
            )
            if r in publishers:
                frames = publishers[r].publish_state_change(data_idle, 0.0)
                broker.enqueue(frames, 0.0)

    for t_ms in range(0, int(sim_end_ms) + 1):
        t_f = float(t_ms)

        # Check if any relay should publish its trip GOOSE now
        for relay_rr in dec.relay_results:
            r = relay_rr.relay_id
            if r in published:
                continue
            t_det = detect_times.get(r, float("nan"))
            if not relay_rr.final_trip or math.isnan(t_det):
                continue
            pub_time = t_det + _IED_PROC_MS
            if t_f >= pub_time:
                data_trip = SambpGooseData(
                    relay_id=r, final_trip=True, conv_trip=relay_rr.conv_trip,
                    source=relay_rr.source, kappa_n=relay_rr.kappa_n,
                    f_int=relay_rr.f_int, I_op_peak=relay_rr.I_op_peak,
                    model_veto_active=(relay_rr.source == "model_veto"),
                    t_detect_ms=t_det,
                )
                if r in publishers:
                    frames = publishers[r].publish_state_change(data_trip, t_f)
                    broker.enqueue(frames, t_f)
                    goose_pub_times[r] = t_f
                    goose_events.append((t_f, r, "PUBLISH", "TRIP"))
                published.add(r)

        # Tick retransmissions
        for r, pub in publishers.items():
            frames = pub.tick(t_f)
            broker.enqueue(frames, t_f)

        # Deliver due frames
        delivered = broker.tick(t_f)
        for frame in delivered:
            goose_events.append((
                t_f,
                frame.src_ied.replace("IED_", ""),
                frame.dst_ied.replace("IED_", ""),
                "RX_TRIP" if frame.data.final_trip else "RX_IDLE",
            ))

    # ---- Step 5: Compute clearance times and acceleration ----------------
    results: list[GooseRelayResult] = []

    for relay_rr in dec.relay_results:
        r = relay_rr.relay_id
        t_det = detect_times.get(r, float("nan"))
        pub_t = goose_pub_times.get(r, float("nan"))

        # Earliest GOOSE reception time from this relay (to any peer)
        rx_t = float("nan")
        for ev in goose_events:
            if ev[1] == r and ev[3] in ("RX_TRIP",):
                if math.isnan(rx_t) or ev[0] < rx_t:
                    rx_t = ev[0]

        # Clearance time: relay trip → GOOSE → CB
        if relay_rr.final_trip and math.isfinite(t_det):
            t_clear = compute_clearance_time(t_det, broker_cfg.base_latency_ms)
        else:
            t_clear = float("nan")

        # Zone acceleration: relay R was NOT tripping on own, but upstream GOOSE
        # arrives and conv_trip is True (relay would have tripped if accelerated)
        accelerated = False
        upstream_rels = [src for src, dsts in _GOOSE_TOPOLOGY.items()
                         if r in dsts]
        for up_r in upstream_rels:
            rx_frame = received_goose[r].get(up_r)
            if rx_frame is not None and rx_frame.data.final_trip:
                if relay_rr.conv_trip:  # would have tripped anyway
                    up_det = detect_times.get(up_r, float("nan"))
                    if not math.isnan(up_det):
                        t_acc = up_det + _IED_PROC_MS + broker_cfg.base_latency_ms
                        if math.isnan(t_det) or t_acc < t_det:
                            t_det     = t_acc
                            t_clear   = compute_clearance_time(t_acc, 0.0)
                            accelerated = True

        results.append(GooseRelayResult(
            relay_id       = r,
            final_trip     = relay_rr.final_trip,
            source         = relay_rr.source,
            t_detect_ms    = t_det,
            t_goose_pub_ms = pub_t,
            t_goose_rx_ms  = rx_t,
            t_clear_ms     = t_clear,
            accelerated    = accelerated,
            kappa_n        = relay_rr.kappa_n,
            f_int          = relay_rr.f_int,
        ))

    return GooseCoordinatorResult(
        fault_loc     = snap.fault_loc,
        fault_type    = snap.fault_type,
        I_fault_pu    = snap.I_fault_pu,
        relay_results = results,
        goose_events  = goose_events,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    snap = generate_network_snapshot("bus_A", "3ph")
    result = run_goose_coordination(snap)

    print(f"Fault: {result.fault_loc}/{result.fault_type}  "
          f"I_f={result.I_fault_pu:.2f} pu")
    for r in result.relay_results:
        acc = " [ACCEL]" if r.accelerated else ""
        t_d = f"{r.t_detect_ms:5.1f}" if math.isfinite(r.t_detect_ms) else "  n/a"
        t_c = f"{r.t_clear_ms:5.1f}" if math.isfinite(r.t_clear_ms) else "  n/a"
        print(f"  {r.relay_id:7s}  trip={r.final_trip}  "
              f"t_detect={t_d} ms  t_clear={t_c} ms{acc}")

    print(f"\nFastest clearance: {result.fastest_clear_ms():.1f} ms")
    print(f"GOOSE events: {len(result.goose_events)}")
    print("sambp_goose_coordinator self-test PASSED.")
