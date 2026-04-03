"""
busbar_transfer_engine.py
==========================
SAMBP TR-14/2026 — Dynamic Busbar Transfer Engine.

Purpose
-------
Listens for IEC 61850 GOOSE isolator/disconnector (DS) state-change
messages and re-maps the three 87B zone feeder arrays (Zone 1, Zone 2,
Check Zone) in real time whenever a busbar transfer is initiated or
completed.

Architecture
------------
A double-busbar substation with N feeders and one bus coupler (BC) is
modelled as a topology table: each feeder has two disconnectors,
DS1 (connecting to BB1) and DS2 (connecting to BB2).  The BC has its
own pair of isolators.

    BB1 ─────────────── BC ─────────────── BB2
     │                                       │
    DS1-Gen  DS1-Line             DS2-Tr  DS2-...
     │         │                   │
    Gen       Line                  Tr

Zone membership rules
─────────────────────
    DS1 only closed  → feeder is on BB1 → contributes to Zone 1 and CK
    DS2 only closed  → feeder is on BB2 → contributes to Zone 2 and CK
    Both DS closed   → Transfer-in-Progress (TIP): feeder contributes
                       proportionally to Z1 and Z2, fully to CK
    Neither closed   → feeder is isolated → contributes to no zone

Bus Coupler zone mapping
------------------------
    BC current always contributes to Zone 1 (+) and Zone 2 (−) to
    maintain the check-zone cancellation property.  If the BC isolator
    is OPEN, the BC waveform array is replaced with zeros.

GOOSE sequence model
--------------------
A transfer generates two GOOSE messages:
    1. DS_CLOSE: the new disconnector closes (both DS now closed → TIP)
    2. DS_OPEN:  the old disconnector opens (transfer complete → TC)

The engine processes messages in stNum order (IEC 61850 §8.1).

References
----------
    IEC 61850-8-1:2011 §8 — GOOSE state machine (stNum, sqNum, retransmit)
    IEC 61850-6:2009 — Substation Configuration Language (SCL), DS associations
    SAMBP TR-06/2026 — GOOSE broker and publisher
    SAMBP TR-07/2026 — Double-busbar zone-selective protection
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


# ---------------------------------------------------------------------------
# Isolator / feeder state
# ---------------------------------------------------------------------------

@dataclass
class IsolatorState:
    """Current state of one feeder's disconnectors."""
    feeder_id:     str
    zone_default:  str          # "Z1" | "Z2" — normal (non-transfer) assignment
    ds1_closed:    bool         # disconnector to BB1
    ds2_closed:    bool         # disconnector to BB2
    is_bus_coupler: bool = False # True for the BC pseudo-feeder

    @property
    def zone_current(self) -> str:
        """Effective zone membership given current DS state."""
        if self.ds1_closed and not self.ds2_closed:
            return "Z1"
        elif self.ds2_closed and not self.ds1_closed:
            return "Z2"
        elif self.ds1_closed and self.ds2_closed:
            return "TIP"         # Transfer-in-Progress
        else:
            return "ISO"         # Isolated


# ---------------------------------------------------------------------------
# GOOSE message (DS state change notification)
# ---------------------------------------------------------------------------

@dataclass
class GooseIsolatorMessage:
    """
    Simulated GOOSE PDU carrying isolator position data.

    Follows IEC 61850-8-1 §9.3 state-machine conventions:
        stNum  — increments on each state transition (new value = new state)
        sqNum  — increments on every PDU (retransmissions of same state)
        T      — send timestamp [ms from epoch]
    """
    feeder_id:  str
    ds1_closed: bool
    ds2_closed: bool
    stNum:      int
    sqNum:      int
    T_ms:       float       # absolute send time [ms]

    @property
    def tip_active(self) -> bool:
        return self.ds1_closed and self.ds2_closed


# ---------------------------------------------------------------------------
# Transfer record (audit log)
# ---------------------------------------------------------------------------

@dataclass
class TransferRecord:
    """Log entry for one completed busbar transfer."""
    feeder_id:   str
    from_zone:   str
    to_zone:     str
    t_start_ms:  float      # when DS_CLOSE message received
    t_end_ms:    float      # when DS_OPEN message received
    goose_lag_ms: float     # latency of triggering GOOSE message
    tip_duration_ms: float  # ds_close → ds_open window

    @property
    def zone_config_error_ms(self) -> float:
        """
        Duration during which the zone mapping was stale (goose_lag_ms).
        This is the window where wrong zone config could affect protection.
        """
        return self.goose_lag_ms


# ---------------------------------------------------------------------------
# Bus coupler model
# ---------------------------------------------------------------------------

@dataclass
class BCState:
    """State of the bus coupler isolator/breaker."""
    bc_closed: bool = True      # True = BC is connected (buses coupled)
    bc_trip:   bool = False     # True = BC breaker tripped (opened by protection)


# ---------------------------------------------------------------------------
# Dynamic Busbar Transfer Engine
# ---------------------------------------------------------------------------

class BusbarTransferEngine:
    """
    Processes GOOSE isolator messages and maintains a live zone topology.

    Usage pattern (per relay cycle)
    --------------------------------
        engine = BusbarTransferEngine(initial_topology)
        # ... receive GOOSE messages ...
        for msg in incoming_goose_queue:
            changed = engine.on_goose_message(msg, t_receive_ms=t_now_ms)
        # Get current zone feeder arrays for the relay cycle
        z1, z2, ck = engine.get_zone_feeder_arrays(feeder_waveforms)
        # Pass to existing sambp_bus_diff pipeline
    """

    def __init__(
        self,
        initial_topology: list[IsolatorState],
        bc_state: Optional[BCState] = None,
        goose_lag_ms: float = 2.0,    # nominal GOOSE latency
    ):
        """
        Parameters
        ----------
        initial_topology : list of IsolatorState for all feeders
        bc_state         : initial bus coupler state
        goose_lag_ms     : expected GOOSE network latency [ms]
        """
        self._feeders: dict[str, IsolatorState] = {
            s.feeder_id: s for s in initial_topology
        }
        self._bc = bc_state if bc_state is not None else BCState()
        self._goose_lag_ms = goose_lag_ms
        self._last_stNum: dict[str, int] = {
            s.feeder_id: 0 for s in initial_topology
        }
        self.transfer_log: list[TransferRecord] = []
        self._pending_close: dict[str, float] = {}   # feeder_id → t_close_ms

    # ------------------------------------------------------------------
    # GOOSE message handler
    # ------------------------------------------------------------------

    def on_goose_message(
        self,
        msg: GooseIsolatorMessage,
        t_receive_ms: float,
    ) -> bool:
        """
        Process an incoming GOOSE isolator message.

        Returns True if the topology changed (zone re-mapping required).

        IEC 61850 stNum guard: messages with stNum ≤ last known are
        retransmissions of a stale state and are ignored.
        """
        fid = msg.feeder_id
        if fid not in self._feeders:
            return False

        # Ignore retransmissions (same state, higher sqNum)
        if msg.stNum <= self._last_stNum[fid]:
            return False
        self._last_stNum[fid] = msg.stNum

        old = self._feeders[fid]
        self._feeders[fid] = IsolatorState(
            feeder_id    = fid,
            zone_default = old.zone_default,
            ds1_closed   = msg.ds1_closed,
            ds2_closed   = msg.ds2_closed,
            is_bus_coupler = old.is_bus_coupler,
        )
        new = self._feeders[fid]

        # Detect TIP → TC transition (DS_OPEN after DS_CLOSE)
        was_tip = old.ds1_closed and old.ds2_closed
        is_tc   = (new.zone_current in ("Z1", "Z2"))
        goose_lag = t_receive_ms - msg.T_ms

        if was_tip and is_tc:
            # Transfer just completed
            t_close = self._pending_close.pop(fid, t_receive_ms - 50.0)
            self.transfer_log.append(TransferRecord(
                feeder_id      = fid,
                from_zone      = old.zone_default,
                to_zone        = new.zone_current,
                t_start_ms     = t_close,
                t_end_ms       = t_receive_ms,
                goose_lag_ms   = max(goose_lag, 0.0),
                tip_duration_ms = t_receive_ms - t_close,
            ))
        elif new.zone_current == "TIP":
            # DS_CLOSE message: TIP is starting
            self._pending_close[fid] = t_receive_ms

        return (old.ds1_closed != new.ds1_closed or
                old.ds2_closed != new.ds2_closed)

    # ------------------------------------------------------------------
    # Zone feeder array builder
    # ------------------------------------------------------------------

    def get_zone_feeder_arrays(
        self,
        feeder_waveforms: dict[str, np.ndarray],   # feeder_id → (3, N)
        bc_waveform:      Optional[np.ndarray] = None,  # (3, N) BC CT
        tip_split:        float = 0.5,              # fraction of current to Z1 in TIP
    ) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
        """
        Build Zone 1, Zone 2, and Check Zone feeder arrays for the current topology.

        Parameters
        ----------
        feeder_waveforms : dict mapping feeder_id to (3, N) current waveform [pu]
        bc_waveform      : (3, N) bus-coupler CT reading [pu] (None → zeros)
        tip_split        : during TIP, fraction of feeder current assigned to Z1

        Returns
        -------
        z1_feeders : list of (3, N) arrays for Zone 1
        z2_feeders : list of (3, N) arrays for Zone 2
        ck_feeders : list of (3, N) arrays for Check Zone
        """
        # Determine array shape from first available waveform
        ref = next(iter(feeder_waveforms.values()))
        shape = ref.shape
        zeros = np.zeros(shape)

        z1, z2, ck = [], [], []

        for fid, state in self._feeders.items():
            if state.is_bus_coupler:
                continue   # BC handled separately below
            I = feeder_waveforms.get(fid, zeros)
            zone = state.zone_current

            if zone == "Z1":
                z1.append(I.copy())
                ck.append(I.copy())
            elif zone == "Z2":
                z2.append(I.copy())
                ck.append(I.copy())
            elif zone == "TIP":
                # Split between zones; Check Zone sees full current
                z1.append(I * tip_split)
                z2.append(I * (1.0 - tip_split))
                ck.append(I.copy())
            elif zone == "ISO":
                pass   # isolated feeder contributes to nothing

        # Bus coupler: always in Z1 (positive) and Z2 (negative)
        # so that check-zone cancellation holds.
        # If BC is open or waveform is None, use zeros.
        if bc_waveform is None or not self._bc.bc_closed:
            I_bc = zeros
        else:
            I_bc = bc_waveform

        z1.append(I_bc)           # BC current enters/exits Z1
        z2.append(-I_bc)          # and opposite into Z2

        return z1, z2, ck

    # ------------------------------------------------------------------
    # Topology query helpers
    # ------------------------------------------------------------------

    @property
    def active_zone(self, feeder_id: str) -> str:
        """Current zone assignment of a named feeder."""
        return self._feeders[feeder_id].zone_current

    def n_feeders_per_zone(self) -> dict[str, int]:
        z = {"Z1": 0, "Z2": 0, "TIP": 0, "ISO": 0}
        for s in self._feeders.values():
            if not s.is_bus_coupler:
                z[s.zone_current] += 1
        return z

    def snapshot(self) -> dict:
        """Return a dict representation of the current topology (for logging)."""
        return {fid: s.zone_current for fid, s in self._feeders.items()}

    # ------------------------------------------------------------------
    # Transfer helpers
    # ------------------------------------------------------------------

    def generate_transfer_sequence(
        self,
        feeder_id:  str,
        to_zone:    str,
        t_start_ms: float,
        ds_close_lag_ms: float = 2.0,
        ds_open_lag_ms:  float = 50.0,   # typical CB + DS operate time
    ) -> list[GooseIsolatorMessage]:
        """
        Generate the two GOOSE messages for a make-before-break transfer.

        Sequence:
            1. New DS closes (both DS closed → TIP)
            2. Old DS opens  (transfer complete → TC)

        Parameters
        ----------
        feeder_id       : feeder being transferred
        to_zone         : target zone ("Z1" or "Z2")
        t_start_ms      : time of transfer initiation
        ds_close_lag_ms : GOOSE latency for DS_CLOSE message
        ds_open_lag_ms  : DS_CLOSE to DS_OPEN duration (mechanical operate)

        Returns
        -------
        list of two GooseIsolatorMessage objects
        """
        state = self._feeders[feeder_id]
        st_base = self._last_stNum[feeder_id]

        # Step 1: close new DS (TIP begins)
        msg_close = GooseIsolatorMessage(
            feeder_id  = feeder_id,
            ds1_closed = True,      # both closed during TIP
            ds2_closed = True,
            stNum      = st_base + 1,
            sqNum      = 0,
            T_ms       = t_start_ms + ds_close_lag_ms,
        )

        # Step 2: open old DS (transfer complete)
        ds1_new = (to_zone == "Z1")
        ds2_new = (to_zone == "Z2")
        msg_open = GooseIsolatorMessage(
            feeder_id  = feeder_id,
            ds1_closed = ds1_new,
            ds2_closed = ds2_new,
            stNum      = st_base + 2,
            sqNum      = 0,
            T_ms       = t_start_ms + ds_close_lag_ms + ds_open_lag_ms,
        )

        return [msg_close, msg_open]


# ---------------------------------------------------------------------------
# Convenience factory for standard double-busbar topology (TR-07 baseline)
# ---------------------------------------------------------------------------

def make_norm_topology(bc_closed: bool = True) -> BusbarTransferEngine:
    """
    Standard double-busbar topology:
        Zone 1: Generator (Gen) + Line feeder
        Zone 2: Transformer (Tr)
        BC: connecting both buses

    This matches the TR-07 baseline exactly.
    """
    initial = [
        IsolatorState("Gen",  zone_default="Z1", ds1_closed=True,  ds2_closed=False),
        IsolatorState("Line", zone_default="Z1", ds1_closed=True,  ds2_closed=False),
        IsolatorState("Tr",   zone_default="Z2", ds1_closed=False, ds2_closed=True),
    ]
    return BusbarTransferEngine(initial, BCState(bc_closed=bc_closed))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import numpy as np

    N = 100
    dummy_wave = lambda: np.ones((3, N)) * 0.5
    feeder_waves = {
        "Gen":  dummy_wave(),
        "Line": dummy_wave() * 0.1,
        "Tr":   dummy_wave() * 0.8,
    }
    bc_wave = dummy_wave() * 0.3

    # Test 1: NORM topology (all on correct buses)
    engine = make_norm_topology()
    print(f"Initial: {engine.snapshot()}")
    z1, z2, ck = engine.get_zone_feeder_arrays(feeder_waves, bc_wave)
    print(f"NORM: Z1={len(z1)} arrays, Z2={len(z2)}, CK={len(ck)}")
    assert len(z1) == 3, "Z1 should have Gen + Line + BC"
    assert len(z2) == 2, "Z2 should have Tr + BC(neg)"
    assert len(ck) == 3, "CK should have Gen + Line + Tr"

    # Test 2: Generate transfer sequence (Gen BB1→BB2)
    msgs = engine.generate_transfer_sequence("Gen", to_zone="Z2", t_start_ms=100.0)
    print(f"Transfer messages: {[(m.stNum, m.ds1_closed, m.ds2_closed) for m in msgs]}")
    assert msgs[0].tip_active, "First message should be TIP"
    assert not msgs[1].tip_active, "Second message should be TC"

    # Test 3: Apply GOOSE messages (simulates receiving transfer)
    changed = engine.on_goose_message(msgs[0], t_receive_ms=102.0)
    print(f"After DS_CLOSE: {engine.snapshot()}, changed={changed}")
    assert engine._feeders["Gen"].zone_current == "TIP"

    changed = engine.on_goose_message(msgs[1], t_receive_ms=155.0)
    print(f"After DS_OPEN: {engine.snapshot()}, changed={changed}")
    assert engine._feeders["Gen"].zone_current == "Z2"

    # Test 4: POST-XFER zone arrays
    z1, z2, ck = engine.get_zone_feeder_arrays(feeder_waves, bc_wave)
    print(f"POST-XFER: Z1={len(z1)}, Z2={len(z2)}, CK={len(ck)}")
    assert len(z1) == 2, "Z1 should have Line + BC only (Gen moved)"
    assert len(z2) == 3, "Z2 should have Tr + BC(neg) + Gen"

    # Test 5: Transfer log
    assert len(engine.transfer_log) == 1
    rec = engine.transfer_log[0]
    print(f"Transfer record: {rec.feeder_id} {rec.from_zone}→{rec.to_zone}  "
          f"TIP={rec.tip_duration_ms:.1f}ms  lag={rec.goose_lag_ms:.1f}ms")
    assert rec.feeder_id == "Gen"
    assert rec.from_zone == "Z1"
    assert rec.to_zone == "Z2"

    # Test 6: BC open → z1/z2 both get zeros for BC
    engine_split = make_norm_topology(bc_closed=False)
    z1s, z2s, cks = engine_split.get_zone_feeder_arrays(feeder_waves, bc_wave)
    assert np.allclose(z1s[-1], 0.0), "BC open → Z1 BC term should be zero"
    assert np.allclose(z2s[-1], 0.0), "BC open → Z2 BC term should be zero"
    print("BC-open test passed.")

    print("\nbusbar_transfer_engine self-test PASSED.")
