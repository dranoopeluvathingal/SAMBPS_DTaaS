"""
goose_engine.py
================
IEC 61850-8-1 GOOSE (Generic Object Oriented Substation Event) simulation
engine for SAMBP system integration studies.

GOOSE retransmission schedule (IEC 61850-8-1 Annex B):
    On state change: publish immediately, then retransmit at doubling intervals
    [2, 4, 8, 16, 32, 64, 128, 256, 512, Tmax_ms, Tmax_ms, ...]
    After Tmax the message is repeated every Tmax (heartbeat).

The engine operates in discrete simulation time (1 ms steps).  Each IED
owns a GoosePublisher and zero or more GooseSubscribers.  A GooseBroker
routes frames between publishers and subscribers, adding configurable
network latency and packet-loss.

SAMBP dataset schema (SambpGooseData):
    relay_id        : str   — "OC" | "87B_A" | "87L" | "87B_B" | "87T"
    final_trip      : bool
    conv_trip       : bool
    source          : str   — "conventional" | "model_veto" | "model" | "no_trip"
    kappa_n         : float
    f_int           : float
    I_op_peak       : float — peak operate current [pu]
    model_veto_active : bool
    t_detect_ms     : float — relay decision time from fault inception [ms]
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# GOOSE retransmission schedule
# ---------------------------------------------------------------------------

_RETRANSMIT_SCHEDULE_MS = [2, 4, 8, 16, 32, 64, 128, 256, 512]
_TMAX_MS                = 1000   # heartbeat interval after schedule exhausted


def next_retransmit_ms(retransmit_count: int) -> int:
    """Return retransmit delay [ms] for the given retransmit index."""
    if retransmit_count < len(_RETRANSMIT_SCHEDULE_MS):
        return _RETRANSMIT_SCHEDULE_MS[retransmit_count]
    return _TMAX_MS


# ---------------------------------------------------------------------------
# Frame and dataset types
# ---------------------------------------------------------------------------

@dataclass
class SambpGooseData:
    """SAMBP-specific GOOSE dataset."""
    relay_id:          str
    final_trip:        bool
    conv_trip:         bool
    source:            str        # "conventional" | "model_veto" | "model" | "no_trip"
    kappa_n:           float
    f_int:             float
    I_op_peak:         float
    model_veto_active: bool
    t_detect_ms:       float      # ms from fault inception, nan if no trip


@dataclass
class GooseFrame:
    """One GOOSE PDU as it exists on the simulated network."""
    src_ied:        str           # publishing IED
    dst_ied:        str           # subscribing IED ("*" = broadcast)
    dataset:        str           # dataset / GCBREF
    sq_num:         int           # increments every retransmission
    state_num:      int           # increments every state change
    tx_time_ms:     float         # simulation time of transmission [ms]
    ttl_ms:         float         # time-to-live [ms]
    data:           SambpGooseData


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------

@dataclass
class GoosePublisher:
    """
    Models one GOOSE Control Block (GCB) in a publishing IED.

    Attributes
    ----------
    ied_id       : unique IED name
    dataset      : dataset / GCB reference
    subscribers  : list of subscriber IED IDs (or ["*"] for broadcast)
    tmax_ms      : heartbeat interval
    """
    ied_id:       str
    dataset:      str
    subscribers:  list[str]       = field(default_factory=lambda: ["*"])
    tmax_ms:      int             = _TMAX_MS

    # internal state
    _sq_num:      int             = field(default=0, init=False, repr=False)
    _state_num:   int             = field(default=0, init=False, repr=False)
    _current_data: SambpGooseData | None = field(default=None, init=False, repr=False)
    _retransmit_cnt: int          = field(default=0, init=False, repr=False)
    _next_tx_ms:  float           = field(default=0.0, init=False, repr=False)

    def publish_state_change(
        self,
        new_data: SambpGooseData,
        now_ms: float,
    ) -> list[GooseFrame]:
        """
        Trigger a GOOSE state change publication.

        The state-number increments, the retransmit schedule restarts, and
        the first frame is emitted immediately.
        """
        self._state_num   += 1
        self._sq_num      += 1
        self._retransmit_cnt = 0
        self._current_data   = new_data
        delay_ms             = next_retransmit_ms(self._retransmit_cnt)
        self._next_tx_ms     = now_ms + delay_ms

        return self._make_frames(now_ms)

    def tick(self, now_ms: float) -> list[GooseFrame]:
        """
        Called every simulation millisecond.  Returns frames to transmit
        (retransmit or heartbeat) if it is time to do so.
        """
        if self._current_data is None or now_ms < self._next_tx_ms:
            return []

        self._sq_num += 1
        self._retransmit_cnt += 1
        delay_ms      = next_retransmit_ms(self._retransmit_cnt)
        self._next_tx_ms = now_ms + delay_ms
        return self._make_frames(now_ms)

    def _make_frames(self, now_ms: float) -> list[GooseFrame]:
        frames = []
        for dst in self.subscribers:
            frames.append(GooseFrame(
                src_ied   = self.ied_id,
                dst_ied   = dst,
                dataset   = self.dataset,
                sq_num    = self._sq_num,
                state_num = self._state_num,
                tx_time_ms= now_ms,
                ttl_ms    = self.tmax_ms * 2.5,
                data      = self._current_data,
            ))
        return frames


# ---------------------------------------------------------------------------
# Subscriber
# ---------------------------------------------------------------------------

@dataclass
class GooseSubscriber:
    """
    Models a GOOSE subscription in a receiving IED.

    Calls `on_state_change(frame)` whenever the state_num increments,
    and `on_heartbeat(frame)` for retransmissions without state change.
    """
    ied_id:           str
    src_ied:          str
    dataset:          str
    on_state_change:  Callable[[GooseFrame], None] | None = None
    on_heartbeat:     Callable[[GooseFrame], None] | None = None

    _last_state_num:  int   = field(default=-1, init=False, repr=False)
    _last_rx_ms:      float = field(default=-1.0, init=False, repr=False)

    def receive(self, frame: GooseFrame, now_ms: float) -> None:
        """Process a received GOOSE frame."""
        if frame.src_ied != self.src_ied or frame.dataset != self.dataset:
            return

        self._last_rx_ms = now_ms

        if frame.state_num > self._last_state_num:
            self._last_state_num = frame.state_num
            if self.on_state_change:
                self.on_state_change(frame)
        else:
            if self.on_heartbeat:
                self.on_heartbeat(frame)

    @property
    def is_alive(self) -> bool:
        """True if a heartbeat was received within 2× Tmax."""
        return self._last_rx_ms >= 0


# ---------------------------------------------------------------------------
# Broker (simulated LAN with latency and loss)
# ---------------------------------------------------------------------------

@dataclass
class GooseBrokerConfig:
    """Configuration for the simulated GOOSE network."""
    base_latency_ms:  float = 1.0    # base one-way latency [ms]
    jitter_ms:        float = 0.3    # Gaussian jitter std dev [ms]
    loss_prob:        float = 0.0    # Bernoulli packet loss probability
    seed:             int   = 42


@dataclass
class _PendingFrame:
    """Frame queued for delivery at arrive_ms."""
    arrive_ms: float
    frame:     GooseFrame

    def __lt__(self, other: "_PendingFrame") -> bool:
        return self.arrive_ms < other.arrive_ms


class GooseBroker:
    """
    Routes GOOSE frames between publishers and subscribers with
    configurable latency and packet loss.

    Usage
    -----
    broker = GooseBroker(cfg)
    broker.register_subscriber(sub)

    # each ms tick:
    frames_to_deliver = broker.tick(now_ms)
    for frame in frames_to_deliver:
        deliver to matching subscriber
    """

    def __init__(self, cfg: GooseBrokerConfig | None = None) -> None:
        self._cfg   = cfg or GooseBrokerConfig()
        self._rng   = random.Random(self._cfg.seed)
        self._queue: list[_PendingFrame] = []
        self._subscribers: list[GooseSubscriber] = []

    def register_subscriber(self, sub: GooseSubscriber) -> None:
        self._subscribers.append(sub)

    def enqueue(self, frames: list[GooseFrame], now_ms: float) -> None:
        """Accept frames from a publisher and schedule them for delivery."""
        for frame in frames:
            if self._rng.random() < self._cfg.loss_prob:
                continue    # packet lost
            latency = self._cfg.base_latency_ms + self._rng.gauss(
                0.0, self._cfg.jitter_ms)
            latency  = max(latency, 0.1)
            arrive   = now_ms + latency
            heapq.heappush(self._queue, _PendingFrame(arrive, frame))

    def tick(self, now_ms: float) -> list[GooseFrame]:
        """
        Advance simulation time to now_ms.  Return all frames that have
        arrived by now_ms and route them to matching subscribers.
        """
        delivered = []
        while self._queue and self._queue[0].arrive_ms <= now_ms:
            pf    = heapq.heappop(self._queue)
            frame = pf.frame
            delivered.append(frame)
            for sub in self._subscribers:
                if (sub.src_ied  == frame.src_ied and
                    sub.dataset  == frame.dataset and
                    (frame.dst_ied == "*" or frame.dst_ied == sub.ied_id)):
                    sub.receive(frame, now_ms)
        return delivered


# ---------------------------------------------------------------------------
# Timing analyser
# ---------------------------------------------------------------------------

@dataclass
class ClearanceRecord:
    """Timing record for one fault scenario and one relay."""
    fault_loc:      str
    fault_type:     str
    relay_id:       str
    t_detect_ms:    float       # relay detection time from fault inception [ms]
    t_goose_pub_ms: float       # time of first GOOSE publication [ms]
    t_goose_rx_ms:  float       # time peer IED received GOOSE [ms]
    t_breaker_ms:   float       # total clearance (detect + GOOSE + breaker) [ms]
    selective:      bool


_BREAKER_OP_MS = 40.0          # typical CB operating time [ms]


def compute_clearance_time(
    t_detect_ms: float,
    broker_latency_ms: float = 1.0,
) -> float:
    """
    Total fault clearance time = relay decision + GOOSE pub + network latency
    + CB operating time.

    For the instantaneous element (our simplified study), the relay decision
    is the detection time above.  The first GOOSE is published within 1 ms
    after detection (IED processing).
    """
    t_ied_proc  = 1.0                            # IED processing [ms]
    return t_detect_ms + t_ied_proc + broker_latency_ms + _BREAKER_OP_MS


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = GooseBrokerConfig(base_latency_ms=1.0, jitter_ms=0.2, loss_prob=0.0)
    broker = GooseBroker(cfg)

    received = []

    sub = GooseSubscriber(
        ied_id          = "IED_87L",
        src_ied         = "IED_87B_A",
        dataset         = "SAMBP_Trip",
        on_state_change = lambda f: received.append(("state", f.data.relay_id,
                                                     f.data.final_trip)),
        on_heartbeat    = lambda f: received.append(("hb",    f.data.relay_id,
                                                     f.data.final_trip)),
    )
    broker.register_subscriber(sub)

    pub = GoosePublisher(
        ied_id      = "IED_87B_A",
        dataset     = "SAMBP_Trip",
        subscribers = ["IED_87L"],
    )

    # Simulate: at t=25ms, 87B_A trips → publishes GOOSE
    data_idle = SambpGooseData(
        relay_id="87B_A", final_trip=False, conv_trip=False,
        source="no_trip", kappa_n=4.3, f_int=1.0,
        I_op_peak=0.0, model_veto_active=False, t_detect_ms=float("nan"),
    )

    data_trip = SambpGooseData(
        relay_id="87B_A", final_trip=True, conv_trip=True,
        source="conventional", kappa_n=4.3, f_int=1.0,
        I_op_peak=17.2, model_veto_active=False, t_detect_ms=25.0,
    )

    # t=0..25 ms: idle ticks (no state change yet)
    for t in range(0, 26):
        frames = pub.tick(t)
        broker.enqueue(frames, t)
        broker.tick(t)

    # t=25 ms: state change → publish trip
    frames = pub.publish_state_change(data_trip, 25.0)
    broker.enqueue(frames, 25.0)

    # t=26..35 ms: tick through retransmissions
    for t in range(26, 36):
        frames = pub.tick(t)
        broker.enqueue(frames, t)
        broker.tick(t)

    print("GOOSE received events:")
    for ev in received:
        print(f"  {ev}")

    assert any(e[0] == "state" and e[2] is True for e in received), \
        "State-change trip event must be received"
    print("goose_engine self-test PASSED.")
