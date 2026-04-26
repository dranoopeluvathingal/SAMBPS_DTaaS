"""Paho-MQTT-backed PubSub.

Lazy-imports paho-mqtt so the rest of the package works without it.
Install with:
    pip install fs_mpc_mg[mqtt]
or
    pip install paho-mqtt
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable
import json
import time
import threading

from .pubsub import PubSubBase


class MQTTPubSub(PubSubBase):
    """Wraps paho-mqtt's Client into the project's PubSubBase contract."""

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str | None = None,
        keepalive: int = 30,
        tls: bool = False,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as e:
            raise ImportError(
                "paho-mqtt is required for MQTTPubSub. Install with `pip install paho-mqtt`."
            ) from e

        self._mqtt = mqtt
        self._client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5)
        if tls:
            self._client.tls_set()
        if username:
            self._client.username_pw_set(username, password)

        self._subs: dict[str, list[Callable[[str, Any], None]]] = defaultdict(list)
        self._connected = threading.Event()

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        self._broker_host = broker_host
        self._broker_port = broker_port
        self._keepalive = keepalive

    # ------------------------------------------------------------------
    def connect(self, timeout: float = 5.0) -> None:
        self._client.connect(self._broker_host, self._broker_port, self._keepalive)
        self._client.loop_start()
        if not self._connected.wait(timeout):
            raise TimeoutError(f"MQTT broker {self._broker_host}:{self._broker_port} did not respond")

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    # ------------------------------------------------------------------
    def publish(self, topic: str, payload: Any) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self._client.publish(topic, body, qos=1)

    def subscribe(self, topic: str, callback: Callable[[str, Any], None]) -> None:
        self._subs[topic].append(callback)
        self._client.subscribe(topic, qos=1)

    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        self._connected.set()
        # Resubscribe everything (in case of reconnection)
        for t in self._subs:
            client.subscribe(t, qos=1)

    def _on_disconnect(self, client, userdata, *args, **kwargs) -> None:
        self._connected.clear()

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = msg.payload
        for cb in self._subs.get(msg.topic, []):
            try:
                cb(msg.topic, payload)
            except Exception as exc:  # pragma: no cover - log & continue
                print(f"[MQTTPubSub] callback error on {msg.topic}: {exc}")
