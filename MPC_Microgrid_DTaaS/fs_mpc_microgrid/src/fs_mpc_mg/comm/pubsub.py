"""Abstract PubSub interface + in-memory implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Callable
import json
import time


class PubSubBase(ABC):
    @abstractmethod
    def publish(self, topic: str, payload: Any) -> None: ...

    @abstractmethod
    def subscribe(self, topic: str, callback: Callable[[str, Any], None]) -> None: ...

    def publish_value(self, topic: str, value: Any, ts: float | None = None) -> None:
        """Publish a {value, ts} envelope. `ts` defaults to wall-clock time."""
        if ts is None:
            ts = time.time()
        self.publish(topic, {"value": value, "ts": ts})


class InMemoryPubSub(PubSubBase):
    """Synchronous in-memory broker for offline simulation and unit tests."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[str, Any], None]]] = defaultdict(list)
        self._log: list[tuple[str, Any]] = []

    def publish(self, topic: str, payload: Any) -> None:
        try:
            payload = json.loads(json.dumps(payload))
        except (TypeError, ValueError):
            pass
        self._log.append((topic, payload))
        for cb in self._subs.get(topic, []):
            cb(topic, payload)

    def subscribe(self, topic: str, callback: Callable[[str, Any], None]) -> None:
        self._subs[topic].append(callback)

    def history(self, topic_prefix: str | None = None) -> list[tuple[str, Any]]:
        if topic_prefix is None:
            return list(self._log)
        return [(t, p) for (t, p) in self._log if t.startswith(topic_prefix)]

    def latest(self, topic: str) -> Any | None:
        for t, p in reversed(self._log):
            if t == topic:
                return p
        return None
