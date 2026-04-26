"""Interface Converter Agent (ICA).

Wraps the FS-MPC inner loop and energy-domain outer PI behind a pub/sub
interface so a centralized microgrid controller (CMC) can dispatch
references and receive telemetry. The agent is plant-agnostic: it accepts
measurements via `step()` and returns a switching vector. The plant + load
are external (in simulation, this is the existing `Plant` and `HarmonicLoad`).

Topic schema is defined in `fs_mpc_mg.comm.topics`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import numpy as np

from .inner_fsmpc import FSMPCController
from .outer_energy_pi import EnergyPI
from .pll import IdealPLL
from .comm.pubsub import PubSubBase
from .comm.topics import topic_ref, topic_telemetry


@dataclass
class ICAState:
    """Latest references received from the CMC."""

    v_dc_ref: float = 900.0
    Q_ref: float = 0.0                          # VAr (positive = injecting reactive)
    H_mask: dict[int, bool] = field(default_factory=lambda: {5: True, 7: True, 11: True, 13: True})
    mode: str = "running"                        # running / island / fault / idle
    enabled: bool = True


class ICAAgent:
    """Centralized-controller-facing wrapper around inner FS-MPC + outer PI.

    Lifecycle:
        agent = ICAAgent("ica1", inner, outer, pll, pubsub)
        # in the simulation/HW loop:
        s = agent.step(t, i_m, v_dc, v_s, i_l)
        plant.step(s, ...)
    """

    def __init__(
        self,
        agent_id: str,
        inner: FSMPCController,
        outer: EnergyPI,
        pll: IdealPLL,
        pubsub: PubSubBase,
        telemetry_decim: int = 100,    # publish telemetry every N FS-MPC ticks
    ) -> None:
        self.id = agent_id
        self.inner = inner
        self.outer = outer
        self.pll = pll
        self.pubsub = pubsub
        self.tel_decim = max(int(telemetry_decim), 1)

        self.state = ICAState(v_dc_ref=outer.p.v_dc_ref)
        self._tick = 0

        # Subscribe to all reference topics
        self.pubsub.subscribe(topic_ref(agent_id, "v_dc_ref"), self._on_v_dc_ref)
        self.pubsub.subscribe(topic_ref(agent_id, "Q_ref"),   self._on_Q_ref)
        self.pubsub.subscribe(topic_ref(agent_id, "H_mask"),  self._on_H_mask)
        self.pubsub.subscribe(topic_ref(agent_id, "mode"),    self._on_mode)
        self.pubsub.subscribe(topic_ref(agent_id, "enable"),  self._on_enable)

    # ------------------------------------------------------------------
    # Subscription handlers
    # ------------------------------------------------------------------

    @staticmethod
    def _payload_value(payload: Any) -> Any:
        if isinstance(payload, dict) and "value" in payload:
            return payload["value"]
        return payload

    def _on_v_dc_ref(self, _topic: str, payload: Any) -> None:
        v = float(self._payload_value(payload))
        self.state.v_dc_ref = v
        # update the outer PI's energy reference
        self.outer.E_c_ref = 0.5 * self.outer.p.C * v * v

    def _on_Q_ref(self, _topic: str, payload: Any) -> None:
        self.state.Q_ref = float(self._payload_value(payload))

    def _on_H_mask(self, _topic: str, payload: Any) -> None:
        # Accept either {5: true, 7: false, ...} or a bool list aligned to default orders
        v = self._payload_value(payload)
        if isinstance(v, dict):
            self.state.H_mask = {int(k): bool(val) for k, val in v.items()}
        elif isinstance(v, list):
            orders = [5, 7, 11, 13]
            self.state.H_mask = {orders[i]: bool(b) for i, b in enumerate(v) if i < len(orders)}

    def _on_mode(self, _topic: str, payload: Any) -> None:
        self.state.mode = str(self._payload_value(payload))

    def _on_enable(self, _topic: str, payload: Any) -> None:
        self.state.enabled = bool(self._payload_value(payload))

    # ------------------------------------------------------------------
    # Control tick
    # ------------------------------------------------------------------

    def step(
        self,
        t: float,
        i_m: np.ndarray,
        v_dc: float,
        v_s: np.ndarray,
        i_l: np.ndarray,
    ) -> np.ndarray:
        """One FS-MPC tick. Returns the switching vector to apply.

        If disabled or in fault mode, returns zero (gates blocked at upper-level
        safety logic in real HW).
        """
        if not self.state.enabled or self.state.mode in ("fault", "idle"):
            self._maybe_publish_telemetry(t, i_m, v_dc, v_s, i_l, np.zeros(3), 0.0)
            self._tick += 1
            return np.zeros(3)

        T_s = self.inner.p.T_s

        # Outer loop (run every tick — simple; could decimate for performance)
        I_s_amp = self.outer.update(v_dc, dt=T_s)

        # PLL — feed v_s once so adaptive PLLs (e.g. SOGIPLL) can lock,
        # then query at the next-sample times for active and reactive references.
        self.pll.update(t, v_s_abc=v_s)
        _, _, unit_active = self.pll.update(t + T_s)
        # 90° lead for reactive component (positive Q_ref injects reactive)
        _, _, unit_reactive = self.pll.update(t + T_s + 1.0 / (4.0 * self.pll.f_grid))

        # Convert Q_ref (VAr) into peak-amplitude reactive current at PCC
        # I_q_peak = (2/3) * Q_ref / V_phase_peak
        V_phase_peak = self.outer.p.V_s_phase_peak
        I_q_peak = (2.0 / 3.0) * self.state.Q_ref / max(V_phase_peak, 1e-9)
        i_s_ref = I_s_amp * unit_active + I_q_peak * unit_reactive

        # Apply harmonic mask: zero out the i_l harmonics we *don't* want compensated
        i_l_eff = self._apply_harmonic_mask(t, i_l)

        s = self.inner.update(i_m, v_dc, v_s, i_s_ref, i_l_eff)

        self._maybe_publish_telemetry(t, i_m, v_dc, v_s, i_l, s, I_s_amp)
        self._tick += 1
        return s

    # ------------------------------------------------------------------
    def _apply_harmonic_mask(self, t: float, i_l: np.ndarray) -> np.ndarray:
        """If H_mask says order h is False, do not compensate that order:
        i_l_eff <- i_l with order-h component subtracted."""
        if all(self.state.H_mask.get(h, True) for h in (5, 7, 11, 13)):
            return i_l
        # Recompute fundamental + the kept-harmonic content from scratch
        # via narrow-band extraction. Simplification: leave i_l alone if any
        # order is masked off (the cost function will then NOT see it
        # because we *zero* that harmonic in the predicted ref).
        # For now, this is a no-op stub — full per-order extraction is a
        # next-phase deliverable. The flag still reaches the agent for logging.
        return i_l

    # ------------------------------------------------------------------
    def _maybe_publish_telemetry(
        self,
        t: float,
        i_m: np.ndarray,
        v_dc: float,
        v_s: np.ndarray,
        i_l: np.ndarray,
        s: np.ndarray,
        I_s_amp: float,
    ) -> None:
        if self._tick % self.tel_decim != 0:
            return

        i_s = i_m + i_l
        ps = self.pubsub
        aid = self.id

        ps.publish_value(topic_telemetry(aid, "v_dc"), float(v_dc))
        ps.publish_value(topic_telemetry(aid, "i_m_abc"), [float(x) for x in i_m])
        ps.publish_value(topic_telemetry(aid, "i_s_abc"), [float(x) for x in i_s])
        ps.publish_value(topic_telemetry(aid, "i_l_abc"), [float(x) for x in i_l])
        ps.publish_value(topic_telemetry(aid, "v_s_abc"), [float(x) for x in v_s])
        ps.publish_value(topic_telemetry(aid, "I_s_amp"), float(I_s_amp))
        ps.publish_value(topic_telemetry(aid, "s_applied"), [float(x) for x in s])

        # Heartbeat at 1 Hz (assuming tel_decim => ≥10 ms; emit every 10 telemetries)
        if self._tick % (self.tel_decim * 10) == 0:
            ps.publish_value(
                topic_telemetry(aid, "heartbeat"),
                {
                    "ts": t,
                    "mode": self.state.mode,
                    "enabled": self.state.enabled,
                    "v_dc_ref": self.state.v_dc_ref,
                    "Q_ref": self.state.Q_ref,
                },
            )
