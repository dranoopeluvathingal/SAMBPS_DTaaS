"""Topic schema for ICA <-> CMC communication.

Layout follows the implementation-plan §7:

    /ica/{id}/refs/v_dc_ref     # 1 Hz   float
    /ica/{id}/refs/Q_ref        # 10 Hz  float (VAr)
    /ica/{id}/refs/H_mask       # 1 Hz   list[bool]; index = harmonic order (5,7,11,13,...)
    /ica/{id}/refs/mode         # event  str   ("running"/"island"/"fault"/"idle")
    /ica/{id}/refs/enable       # event  bool

    /ica/{id}/tel/v_dc          # 100 Hz float
    /ica/{id}/tel/i_m_abc       # 100 Hz [3] floats
    /ica/{id}/tel/i_s_abc       # 100 Hz [3] floats
    /ica/{id}/tel/i_l_abc       # 100 Hz [3] floats
    /ica/{id}/tel/v_s_abc       # 100 Hz [3] floats
    /ica/{id}/tel/I_s_amp       # 100 Hz float
    /ica/{id}/tel/s_applied     # 100 Hz [3] floats
    /ica/{id}/tel/heartbeat     # 1 Hz dict   {ts, mode, enabled}

Payload format: JSON object  { "value": <T>, "ts": <unix_seconds> }.
"""

from __future__ import annotations

REF_KEYS = ("v_dc_ref", "Q_ref", "H_mask", "mode", "enable")
TEL_KEYS = ("v_dc", "i_m_abc", "i_s_abc", "i_l_abc", "v_s_abc", "I_s_amp", "s_applied", "heartbeat")


def topic_ref(agent_id: str, key: str) -> str:
    if key not in REF_KEYS:
        raise ValueError(f"Unknown ref key {key!r}; expected one of {REF_KEYS}")
    return f"/ica/{agent_id}/refs/{key}"


def topic_telemetry(agent_id: str, key: str) -> str:
    if key not in TEL_KEYS:
        raise ValueError(f"Unknown telemetry key {key!r}; expected one of {TEL_KEYS}")
    return f"/ica/{agent_id}/tel/{key}"
