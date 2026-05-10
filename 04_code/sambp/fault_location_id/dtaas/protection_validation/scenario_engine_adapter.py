"""
scenario_engine_adapter.py
============================

WP5.4 (P5.4) v1.0 SAMBPS DTaaS scenario-engine plugin adapter.

The SAMBPS DTaaS scenario engine drives a sub-station digital
twin through pre-scripted contingencies (faults, switching events,
DG ride-through, etc.) and emits per-contingency V/I waveforms +
metadata.  Each protection sub-project (sync_oc, transformer_diff,
line_diff, bus_diff, fault_location_id) registers as a *plugin*
that consumes the scenario-engine output and emits a per-
contingency protection decision.

Plugin spec (lightweight, codified here for the
fault_location_id sub-project):

* a ``PluginInfo`` dataclass returned by ``get_plugin_info()``;
* a ``configure(config: dict) -> None`` for per-deployment
  parameters;
* a ``handle_scenario(scenario: dict) -> dict`` that consumes one
  scenario emission and returns the protection-decision JSON.

The line_diff sibling project does NOT yet ship a concrete
scenario-engine adapter (it's still at the skeleton stage); this
module is the **first** concrete scenario-engine adapter in the
SAMBPS DTaaS programme.  The plugin-spec shape (PluginInfo +
configure + handle_scenario) is the proposed canonical shape; the
sibling protection sub-projects will mirror this shape at their
WP5.x equivalents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .api import (
    API_VERSION,
    handle_locate,
)


@dataclass(frozen=True)
class PluginInfo:
    """Static metadata describing a SAMBPS DTaaS protection plugin."""

    name: str
    version: str
    description: str
    handles_event_classes: tuple[str, ...]
    required_config_keys: tuple[str, ...]
    optional_config_keys: tuple[str, ...]


PLUGIN_INFO = PluginInfo(
    name="protection_validation.fault_location_id",
    version=API_VERSION,
    description=(
        "SAMBPS DTaaS HIF-locator: single-ended joint estimation "
        "of HIF location and arc resistance via power-frequency "
        "admittance identification."
    ),
    handles_event_classes=("HIF_SLG", "HIF_LL", "HIF_LLG"),
    required_config_keys=("network_id",),
    optional_config_keys=("snr_v_db", "snr_i_db", "max_iter"),
)


def get_plugin_info() -> PluginInfo:
    """Return the static plugin metadata.  Called by the scenario
    engine at plugin discovery time."""
    return PLUGIN_INFO


@dataclass
class _PluginState:
    """Per-deployment plugin configuration."""

    config: dict[str, Any] = field(default_factory=dict)


_state = _PluginState()


def configure(config: dict) -> None:
    """Set per-deployment configuration.  Called once by the
    scenario engine after plugin discovery, before the first
    handle_scenario call."""
    missing = [
        k for k in PLUGIN_INFO.required_config_keys if k not in config
    ]
    if missing:
        raise ValueError(
            f"required config keys missing: {missing}; "
            f"got {sorted(config.keys())}"
        )
    _state.config = dict(config)


def handle_scenario(scenario: dict) -> dict:
    """Consume one scenario emission and return the protection-
    decision JSON.

    Expected scenario shape (per the SAMBPS DTaaS scenario-engine
    contract):

    ::

        {
            "scenario_id": str,
            "timestamp": float,
            "event_class": str,        # one of PluginInfo.handles_event_classes
            "phasors": {
                "V_phasor": [Re, Im],  # phase A
                "I_phasor": [Re, Im],  # phase A
            },
            "metadata": {
                "fault_type": "SLG" | "LL" | "LLG",
                ...
            }
        }

    Returns:

    ::

        {
            "scenario_id": str,
            "decision": "LOCATED" | "UNCERTAIN" | "ERROR",
            "alpha_est": float,
            "Rx_est": float,
            "identifiability_flag": "OK" | "DEGENERATE",
            "plugin_name": str,
            "plugin_version": str,
            "details": dict   # full handle_locate response
        }
    """
    if not _state.config:
        return {
            "scenario_id": scenario.get("scenario_id", "unknown"),
            "decision": "ERROR",
            "error": (
                "plugin not configured; call configure(config) first"
            ),
            "plugin_name": PLUGIN_INFO.name,
            "plugin_version": PLUGIN_INFO.version,
        }
    network_id = _state.config["network_id"]
    phasors = scenario.get("phasors", {})
    fault_type = scenario.get("metadata", {}).get("fault_type", "SLG")
    payload = {
        "V_phasor": phasors.get("V_phasor", [0.0, 0.0]),
        "I_phasor": phasors.get("I_phasor", [0.0, 0.0]),
        "network_id": network_id,
        "fault_type": fault_type,
    }
    response = handle_locate(payload)
    if response.get("status", 200) != 200:
        return {
            "scenario_id": scenario.get("scenario_id", "unknown"),
            "decision": "ERROR",
            "error": response.get("error", "unknown"),
            "plugin_name": PLUGIN_INFO.name,
            "plugin_version": PLUGIN_INFO.version,
            "details": response,
        }
    decision = (
        "UNCERTAIN" if response["identifiability_flag"] == "DEGENERATE"
        else "LOCATED"
    )
    if not np.isfinite(response["alpha_est"]):
        decision = "ERROR"
    return {
        "scenario_id": scenario.get("scenario_id", "unknown"),
        "decision": decision,
        "alpha_est": float(response["alpha_est"]),
        "Rx_est": float(response["Rx_est"]),
        "identifiability_flag": response["identifiability_flag"],
        "plugin_name": PLUGIN_INFO.name,
        "plugin_version": PLUGIN_INFO.version,
        "details": response,
    }


__all__ = [
    "PluginInfo",
    "PLUGIN_INFO",
    "get_plugin_info",
    "configure",
    "handle_scenario",
]
