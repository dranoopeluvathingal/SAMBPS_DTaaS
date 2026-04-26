"""DT-specific MQTT topics.

Layout:
    /dt/{ica_id}/residual/v_dc       float       (measured - predicted)
    /dt/{ica_id}/residual/i_m_norm   float       (||i_m_meas - i_m_pred||)
    /dt/{ica_id}/params/L            float       (identified inductance, H)
    /dt/{ica_id}/params/r            float       (identified resistance, ohm)
    /dt/{ica_id}/anomaly             dict        anomaly event payload
    /dt/{ica_id}/cyber_alert         dict        cyber-screen alert payload
    /dt/forecast/Q_total             float       look-ahead Q (VAr)
    /dt/heartbeat                    dict        DT health
"""

from __future__ import annotations

DT_KEYS = (
    "residual/v_dc",
    "residual/i_m_norm",
    "params/L",
    "params/r",
    "anomaly",
    "cyber_alert",
)

GLOBAL_DT_KEYS = ("forecast/Q_total", "heartbeat")


def topic_dt(key: str, ica_id: str | None = None) -> str:
    """Build a /dt topic. If `ica_id` is given, key is per-ICA; else global."""
    if ica_id is None:
        if key not in GLOBAL_DT_KEYS:
            raise ValueError(f"Global DT key {key!r} not in {GLOBAL_DT_KEYS}")
        return f"/dt/{key}"
    if key not in DT_KEYS:
        raise ValueError(f"Per-ICA DT key {key!r} not in {DT_KEYS}")
    return f"/dt/{ica_id}/{key}"
