"""Communication abstractions for the ICA agent.

Provides a PubSub interface with an in-memory implementation (for tests
and offline demos) and an MQTT-backed implementation (for real deployments).
"""

from .pubsub import PubSubBase, InMemoryPubSub
from .topics import topic_ref, topic_telemetry, REF_KEYS, TEL_KEYS

__all__ = [
    "PubSubBase",
    "InMemoryPubSub",
    "topic_ref",
    "topic_telemetry",
    "REF_KEYS",
    "TEL_KEYS",
]
