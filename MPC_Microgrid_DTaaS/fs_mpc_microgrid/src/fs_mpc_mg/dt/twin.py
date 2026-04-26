"""MicrogridDigitalTwin — orchestrator.

Wires the four DT services together behind a single object that:
  - subscribes to every ICA's telemetry and the CMC's reference channels,
  - runs a ShadowPlant per ICA,
  - feeds residuals to AnomalyDetector and (optionally) RLSIdentifier,
  - publishes alerts and forecasts on /dt/* topics.

The DT does *not* close any control loop on the physical plant; its
outputs are advisory (recommended parameter updates, anomaly events,
cyber alerts, Q forecasts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import time
import numpy as np

from ..plant import PlantParams
from ..comm.pubsub import PubSubBase
from ..comm.topics import topic_telemetry, topic_ref, REF_KEYS
from .topics import topic_dt
from .emt_shadow import ShadowPlant, ShadowResidual
from .parameter_id import RLSIdentifier
from .anomaly import AnomalyDetector, AnomalyEvent
from .cyber_screen import CyberScreen, CyberAlert
from .forecaster import QForecaster


@dataclass
class TwinConfig:
    T_s: float = 20e-6
    n_sub_per_ica_tick: int = 5
    enable_parameter_id: bool = True
    enable_anomaly: bool = True
    enable_cyber_screen: bool = True
    enable_forecaster: bool = True
    plant_params: PlantParams = field(default_factory=PlantParams)
    forecast_horizon_s: float = 0.2


class MicrogridDigitalTwin:
    """Soft-real-time DT for the fleet of ICAs."""

    def __init__(
        self,
        ica_ids: list[str],
        pubsub: PubSubBase,
        config: TwinConfig | None = None,
    ) -> None:
        self.ica_ids = list(ica_ids)
        self.pubsub = pubsub
        self.cfg = config or TwinConfig()

        # Per-ICA components
        self.shadows: dict[str, ShadowPlant] = {iid: ShadowPlant(self.cfg.plant_params) for iid in ica_ids}
        self.rls: dict[str, RLSIdentifier] = {
            iid: RLSIdentifier(self.cfg.T_s) for iid in ica_ids
        }
        self.anomaly: dict[str, AnomalyDetector] = {
            iid: AnomalyDetector(iid) for iid in ica_ids
        }
        self.cyber = CyberScreen()
        self.forecaster = QForecaster(horizon_s=self.cfg.forecast_horizon_s)

        # Per-ICA last telemetry buffer for residual computation
        self._last: dict[str, dict[str, Any]] = {iid: {} for iid in ica_ids}

        # Counters
        self.events: list[AnomalyEvent] = []
        self.cyber_alerts: list[CyberAlert] = []
        self.residuals: dict[str, list[ShadowResidual]] = {iid: [] for iid in ica_ids}
        self._n_ticks: int = 0

        # Wire pubsub
        self._subscribe_all()

    # ------------------------------------------------------------------ subscriptions
    def _subscribe_all(self) -> None:
        for iid in self.ica_ids:
            for key in ("v_dc", "i_m_abc", "v_s_abc", "i_l_abc", "s_applied"):
                self.pubsub.subscribe(topic_telemetry(iid, key), self._make_tel_handler(iid, key))
            if self.cfg.enable_cyber_screen:
                for key in REF_KEYS:
                    self.pubsub.subscribe(topic_ref(iid, key), self._make_ref_handler(iid, key))

    def _make_tel_handler(self, iid: str, key: str):
        def handler(_topic: str, payload: Any) -> None:
            value = payload["value"] if isinstance(payload, dict) and "value" in payload else payload
            ts = payload.get("ts", time.time()) if isinstance(payload, dict) else time.time()
            self._last[iid][key] = (value, ts)
            if key == "i_l_abc" and self.cfg.enable_forecaster:
                self.forecaster.push(ts, value)
        return handler

    def _make_ref_handler(self, iid: str, key: str):
        def handler(_topic: str, payload: Any) -> None:
            value = payload["value"] if isinstance(payload, dict) and "value" in payload else payload
            ts = payload.get("ts", time.time()) if isinstance(payload, dict) else time.time()
            alert = self.cyber.inspect(iid, key, value, ts)
            if alert is not None:
                self.cyber_alerts.append(alert)
                self.pubsub.publish_value(topic_dt("cyber_alert", iid),
                                          {"rule": alert.rule, "detail": alert.detail,
                                           "severity": alert.severity, "ts": alert.ts})
        return handler

    # ------------------------------------------------------------------ tick
    def tick(self, t: float, dt: float | None = None) -> None:
        """Advance the DT one step. Call at telemetry rate (e.g. 100 Hz)."""
        self._n_ticks += 1
        dt = dt if dt is not None else self.cfg.T_s * self.cfg.n_sub_per_ica_tick

        for iid in self.ica_ids:
            d = self._last[iid]
            if not all(k in d for k in ("v_dc", "i_m_abc", "v_s_abc", "s_applied")):
                continue
            v_dc_meas = float(d["v_dc"][0])
            i_m_meas = np.asarray(d["i_m_abc"][0], dtype=float)
            v_s = np.asarray(d["v_s_abc"][0], dtype=float)
            s = np.asarray(d["s_applied"][0], dtype=float)

            shadow = self.shadows[iid]
            # bootstrap shadow on first tick
            if self._n_ticks == 1:
                shadow.set_state(i_m_meas, v_dc_meas)
                continue

            # Step shadow, compute residual against the new measurement
            shadow.step(s, v_s, dt=dt)
            residual = shadow.compute_residual(t, i_m_meas, v_dc_meas)
            self.residuals[iid].append(residual)

            # Publish residual snapshots
            self.pubsub.publish_value(topic_dt("residual/v_dc", iid), residual.v_dc_residual)
            self.pubsub.publish_value(topic_dt("residual/i_m_norm", iid), residual.i_m_residual_norm)

            # Anomaly detection
            if self.cfg.enable_anomaly:
                events = self.anomaly[iid].update(
                    residual.v_dc_residual, residual.i_m_residual_norm, ts=t)
                for e in events:
                    self.events.append(e)
                    self.pubsub.publish_value(
                        topic_dt("anomaly", iid),
                        {"metric": e.metric, "value": e.value, "threshold": e.threshold,
                         "severity": e.severity, "reason": e.reason, "ts": e.ts},
                    )

            # Parameter ID — only when we have two consecutive measurements
            if self.cfg.enable_parameter_id:
                prev = getattr(self, f"_prev_{iid}", None)
                if prev is not None:
                    self.rls[iid].update(
                        i_m_next=i_m_meas,
                        i_m_now=prev["i_m"],
                        v_s_now=prev["v_s"],
                        s_now=prev["s"],
                        v_dc_now=prev["v_dc"],
                    )
                    res = self.rls[iid].estimate
                    self.pubsub.publish_value(topic_dt("params/L", iid), res.L)
                    self.pubsub.publish_value(topic_dt("params/r", iid), res.r)
                setattr(self, f"_prev_{iid}",
                        {"i_m": i_m_meas.copy(), "v_s": v_s.copy(),
                         "s": s.copy(), "v_dc": v_dc_meas})

        # Forecaster — published once per tick
        if self.cfg.enable_forecaster:
            f = self.forecaster.predict()
            if f is not None:
                self.pubsub.publish_value(topic_dt("forecast/Q_total"),
                                          {"horizon_s": f.horizon_s,
                                           "Q_total_predicted": f.Q_total_predicted,
                                           "Q_total_now": f.Q_total_now,
                                           "trend_slope": f.trend_slope})

    # ------------------------------------------------------------------ summary
    def summary(self) -> dict:
        return {
            "n_ticks": self._n_ticks,
            "n_anomaly_events": len(self.events),
            "n_cyber_alerts": len(self.cyber_alerts),
            "rls": {iid: {"L": r.estimate.L, "r": r.estimate.r,
                          "n": r.n, "converged": r.estimate.converged}
                    for iid, r in self.rls.items()},
        }
