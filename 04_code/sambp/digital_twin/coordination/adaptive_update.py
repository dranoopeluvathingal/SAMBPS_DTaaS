# =============================================================================
# sambp / digital_twin / coordination / adaptive_update.py
#
# Adaptive relay setting updater — TR-72 WP 72.3
#
# When the FaultEvolutionDetector fires a FaultEvolutionEvent the DT pushes
# revised relay settings to a relay interface so that protection remains
# co-ordinated for the new fault type.
#
# Design rules
# ------------
#   • Relay settings are represented as a flat dict (matches RelayInterface
#     payload format used in integration/relay_interface.py).
#   • Each fault-type transition maps to a SettingAdjustment recipe that
#     scales pick-up, time-dial, and reach parameters.
#   • A RateLimiter prevents flooding the relay with updates: at most one
#     update per _MIN_UPDATE_GAP seconds.
#   • All pushed updates are appended to an audit log for post-event review.
#
# Public API
# ----------
#   mgr = AdaptiveUpdateManager(relay_interface)
#   pushed = mgr.on_evolution_event(evt, current_settings)  → dict | None
#   mgr.audit_log   → list[AuditRecord]
#   mgr.reset()
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from estimation.fault_evolution import FaultEvolutionEvent


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SettingAdjustment:
    """
    Multiplicative scaling factors applied to relay settings on a transition.

    Fields
    ------
    pickup_scale    : multiply over-current pick-up threshold
    time_dial_scale : multiply TCC time-dial setting
    reach_scale     : multiply distance relay reach (zone 1/2)
    directional     : override directional element (None = no change)
    description     : human-readable reason for the adjustment
    """
    pickup_scale:   float
    time_dial_scale: float
    reach_scale:    float
    directional:    Optional[str]  # "forward" | "reverse" | None
    description:    str


@dataclass
class AuditRecord:
    """Immutable record of one relay setting push."""
    timestamp:   float
    from_type:   str
    to_type:     str
    confidence:  float
    old_settings: Dict[str, Any]
    new_settings: Dict[str, Any]
    accepted:    bool   # False if rate-limited or relay rejected


# ---------------------------------------------------------------------------
# Transition recipe table
# ---------------------------------------------------------------------------

# Key: (from_type, to_type)  Value: SettingAdjustment
_RECIPES: Dict[tuple[str, str], SettingAdjustment] = {
    # SLG evolves to DLG — increase reach slightly, lower pickup
    ("SLG", "DLG"): SettingAdjustment(
        pickup_scale=0.90, time_dial_scale=0.95, reach_scale=1.10,
        directional=None,
        description="SLG→DLG: lower pickup 10%, extend reach 10%",
    ),
    # SLG evolves to 3PH — significant reach and time-dial reduction for speed
    ("SLG", "3PH"): SettingAdjustment(
        pickup_scale=0.80, time_dial_scale=0.85, reach_scale=1.20,
        directional="forward",
        description="SLG→3PH: lower pickup 20%, extend reach 20%, accelerate",
    ),
    # DLG evolves to 3PH — similar to SLG→3PH but already widened
    ("DLG", "3PH"): SettingAdjustment(
        pickup_scale=0.85, time_dial_scale=0.88, reach_scale=1.10,
        directional="forward",
        description="DLG→3PH: lower pickup 15%, extend reach 10%",
    ),
    # Restrike — restore pre-fault settings (undo previous scaling)
    ("NONE", "RST"): SettingAdjustment(
        pickup_scale=1.00, time_dial_scale=1.00, reach_scale=1.00,
        directional=None,
        description="restrike: restore nominal settings",
    ),
    # Intermittent — tighten pickup to catch small-magnitude events
    ("NONE", "INT"): SettingAdjustment(
        pickup_scale=0.75, time_dial_scale=0.90, reach_scale=1.05,
        directional=None,
        description="intermittent: reduce pickup 25% for repeated events",
    ),
}

_MIN_UPDATE_GAP = 0.020   # 20 ms rate limit between successive pushes


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class AdaptiveUpdateManager:
    """
    Listens for FaultEvolutionEvents and pushes adapted relay settings
    through a relay interface.

    Parameters
    ----------
    relay_interface : object with a push_settings(settings_dict) method.
                      Pass None to operate in log-only mode.
    min_confidence  : minimum event confidence to act on (default 0.65)
    """

    def __init__(self,
                 relay_interface=None,
                 min_confidence: float = 0.65):
        self._ri      = relay_interface
        self._min_c   = min_confidence
        self._last_t  = -999.0
        self._log: List[AuditRecord] = []

    # ------------------------------------------------------------------
    def on_evolution_event(
        self,
        evt: FaultEvolutionEvent,
        current_settings: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Process a FaultEvolutionEvent and (conditionally) push new settings.

        Parameters
        ----------
        evt              : FaultEvolutionEvent from FaultEvolutionDetector
        current_settings : relay settings dict (keys: pickup, time_dial, reach, ...)

        Returns
        -------
        new_settings dict if a push was made, else None.
        """
        # ── Gate 1: confidence ────────────────────────────────────────
        if evt.confidence < self._min_c:
            return None

        # ── Gate 2: rate limit ────────────────────────────────────────
        rate_limited = (evt.timestamp - self._last_t) < _MIN_UPDATE_GAP

        # ── Compute new settings ──────────────────────────────────────
        key = (evt.from_type, evt.to_type)
        recipe = _RECIPES.get(key)
        if recipe is None:
            return None

        new_settings = self._apply_recipe(current_settings, recipe)

        # ── Audit record (always) ─────────────────────────────────────
        accepted = not rate_limited
        record = AuditRecord(
            timestamp=evt.timestamp,
            from_type=evt.from_type,
            to_type=evt.to_type,
            confidence=evt.confidence,
            old_settings=dict(current_settings),
            new_settings=new_settings,
            accepted=accepted,
        )
        self._log.append(record)

        if rate_limited:
            return None

        # ── Push to relay ─────────────────────────────────────────────
        self._last_t = evt.timestamp
        if self._ri is not None:
            try:
                self._ri.push_settings(new_settings)
            except Exception:
                record.accepted = False
                return None

        return new_settings

    # ------------------------------------------------------------------
    def reset(self):
        """Reset rate limiter and audit log."""
        self._last_t = -999.0
        self._log.clear()

    @property
    def audit_log(self) -> List[AuditRecord]:
        return list(self._log)

    # ------------------------------------------------------------------
    @staticmethod
    def _apply_recipe(
        settings: Dict[str, Any],
        recipe: SettingAdjustment,
    ) -> Dict[str, Any]:
        """Return a new settings dict with the recipe scales applied."""
        new = dict(settings)
        for key in ("pickup", "pickup_pu", "i_pickup"):
            if key in new and isinstance(new[key], (int, float)):
                new[key] = float(new[key]) * recipe.pickup_scale
        for key in ("time_dial", "td", "tms"):
            if key in new and isinstance(new[key], (int, float)):
                new[key] = float(new[key]) * recipe.time_dial_scale
        for key in ("reach", "reach_pu", "zone1_reach", "zone2_reach"):
            if key in new and isinstance(new[key], (int, float)):
                new[key] = float(new[key]) * recipe.reach_scale
        if recipe.directional is not None:
            new["directional"] = recipe.directional
        new["_update_reason"] = recipe.description
        return new
