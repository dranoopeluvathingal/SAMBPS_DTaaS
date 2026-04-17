# =============================================================================
# sambp / digital_twin / coordination / meshed_coordinator.py
#
# Topology-aware meshed coordinator — TR-70 WP 70.3
#
# Provides directional overcurrent / distance coordination and pilot scheme
# logic (POTT / DCB / PUTT) for a multi-source IBR meshed network.
#
# Directional element
# -------------------
# Direction is determined from the sign of the real part of:
#   Z_relay = (V_relay * conj(I_relay)) / |I_relay|²
# Positive Re(Z_relay) → forward (towards fault) — TRIP zone
# Negative Re(Z_relay) → reverse (away from fault) — block zone
#
# Pilot scheme logic  (per IEEE C37.113-2015 §8.2)
# ------------------------------------------------
# POTT  (Permissive Over-reaching Transfer Trip):
#   Local: Zone-2 forward → send PERM signal
#   Remote: receive PERM AND local Zone-1 OR Zone-2 forward → TRIP
#
# DCB   (Directional Comparison Blocking):
#   Local: reverse element → send BLOCK signal
#   Remote: no BLOCK received AND local Zone-2 forward → TRIP after t_coord
#
# PUTT  (Permissive Under-reaching Transfer Trip):
#   Local: Zone-1 forward → send PERM signal
#   Remote: receive PERM → TRIP (without local pickup required)
#
# Public API
# ----------
#   coord = MeshedCoordinator(relay_settings, scheme="POTT")
#   decision = coord.evaluate(t, relay_id, v_pu, i_pu, ekf_state,
#                             pilot_rx=None)
#       → RelayDecision(relay_id, action, zone, pilot_tx, confidence, reason)
#   coord.reset()
# =============================================================================

from __future__ import annotations

import math
import cmath
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_TRIP   = "TRIP"
_BLOCK  = "BLOCK"
_PERMIT = "PERMIT"
_NONE   = "NONE"

# Zone reach multipliers (Zone-2 = 120% of Zone-1 reach)
_ZONE2_MULT = 1.20
_ZONE3_MULT = 1.80

# Coordination time delay for DCB (s)
_T_COORD_DCB = 0.020   # 20 ms

# Minimum current threshold for directional element assertion [pu]
_I_DIR_MIN_PU = 0.05


# ---------------------------------------------------------------------------
# RelayDecision
# ---------------------------------------------------------------------------

@dataclass
class RelayDecision:
    """Output of MeshedCoordinator.evaluate() for one relay."""
    relay_id:   str     # identifies the relay (usually line name)
    action:     str     # "TRIP" | "BLOCK" | "PERMIT" | "NONE"
    zone:       int     # zone that picked up (1, 2, 3) or 0 if none
    pilot_tx:   str     # signal to transmit: "PERM" | "BLOCK" | ""
    confidence: float
    reason:     str


# ---------------------------------------------------------------------------
# RelaySettings (one per line / relay pair)
# ---------------------------------------------------------------------------

@dataclass
class RelaySettings:
    relay_id:       str
    pickup_pu:      float   # OC pickup current [pu]
    zone1_reach_pu: float   # Zone-1 reach [pu of line impedance]
    time_dial:      float   # time dial (seconds at 2× pickup)
    z_line_pu:      float = 0.10   # line impedance for reach calculation


# ---------------------------------------------------------------------------
# MeshedCoordinator
# ---------------------------------------------------------------------------

class MeshedCoordinator:
    """
    Topology-aware relay coordinator with directional elements and pilot logic.

    Parameters
    ----------
    relay_settings : list of RelaySettings
    scheme         : pilot scheme "POTT" | "DCB" | "PUTT"
    ibr_params     : dict source_name → {'f_gfm': float, 'k_ibr': float}
                     used for IBR-aware reach adjustment
    """

    def __init__(self,
                 relay_settings: List[RelaySettings],
                 scheme: str = "POTT",
                 ibr_params: Optional[Dict[str, dict]] = None) -> None:
        self._scheme  = scheme.upper()
        self._ibr     = ibr_params or {}
        self._settings: Dict[str, RelaySettings] = {
            s.relay_id: s for s in relay_settings
        }
        # Pilot channel state: relay_id → last received signal
        self._pilot_rx: Dict[str, str] = {}
        # Timer state for DCB
        self._dcb_t_start: Dict[str, Optional[float]] = {
            s.relay_id: None for s in relay_settings
        }

    # ------------------------------------------------------------------
    def evaluate(self,
                 t: float,
                 relay_id: str,
                 v_pu: float,
                 i_pu: float,
                 z_apparent: Optional[complex] = None,
                 ekf_state: Optional[dict] = None,
                 pilot_rx: Optional[str] = None) -> RelayDecision:
        """
        Evaluate one relay for the current measurement cycle.

        Parameters
        ----------
        t           : current time [s]
        relay_id    : relay / line identifier
        v_pu        : terminal voltage magnitude [pu]
        i_pu        : line current magnitude [pu]
        z_apparent  : complex apparent impedance V/I [pu], or None
        ekf_state   : EKF state dict for IBR-aware adjustments
        pilot_rx    : received pilot signal from remote end ("PERM"/"BLOCK"/"")

        Returns
        -------
        RelayDecision
        """
        if relay_id not in self._settings:
            return RelayDecision(relay_id=relay_id, action=_NONE, zone=0,
                                 pilot_tx="", confidence=0.0,
                                 reason="Unknown relay_id")

        s = self._settings[relay_id]
        if pilot_rx is not None:
            self._pilot_rx[relay_id] = pilot_rx

        # ── IBR-aware reach adjustment ────────────────────────────────
        f_gfm = float((ekf_state or {}).get('f_gfm', 0.5))
        k_ibr = float((ekf_state or {}).get('k_ibr', 0.5))
        # GFM-heavy systems: reduce apparent reach slightly (current limiting)
        ibr_reach_factor = 1.0 - 0.10 * f_gfm * k_ibr
        z1_reach = s.zone1_reach_pu * s.z_line_pu * ibr_reach_factor
        z2_reach = z1_reach * _ZONE2_MULT
        z3_reach = z1_reach * _ZONE3_MULT

        # ── Directional element ───────────────────────────────────────
        if i_pu < _I_DIR_MIN_PU:
            return RelayDecision(relay_id=relay_id, action=_NONE, zone=0,
                                 pilot_tx="", confidence=1.0,
                                 reason=f"I={i_pu:.3f} < min {_I_DIR_MIN_PU}")

        # Determine direction from impedance angle
        if z_apparent is not None:
            direction = "FWD" if z_apparent.real >= 0 else "REV"
            z_mag = abs(z_apparent)
        else:
            # Fall back: overcurrent only (treat as forward if I > pickup)
            direction = "FWD" if i_pu > s.pickup_pu else "NONE"
            z_mag = float((ekf_state or {}).get('z_line', s.z_line_pu))

        # ── Zone pickup ───────────────────────────────────────────────
        in_zone1 = (direction == "FWD" and z_mag <= z1_reach)
        in_zone2 = (direction == "FWD" and z_mag <= z2_reach)
        in_zone3 = (direction == "FWD" and z_mag <= z3_reach)
        is_reverse = (direction == "REV")

        zone = 1 if in_zone1 else (2 if in_zone2 else (3 if in_zone3 else 0))

        # ── Pilot scheme logic ────────────────────────────────────────
        action, pilot_tx, reason, conf = self._pilot_logic(
            t, relay_id, zone, is_reverse, self._pilot_rx.get(relay_id, ""),
            i_pu, s, k_ibr, f_gfm,
        )

        return RelayDecision(
            relay_id=relay_id, action=action, zone=zone,
            pilot_tx=pilot_tx, confidence=round(conf, 4), reason=reason,
        )

    # ------------------------------------------------------------------
    def _pilot_logic(self,
                     t: float,
                     relay_id: str,
                     zone: int,
                     is_reverse: bool,
                     rx_signal: str,
                     i_pu: float,
                     s: RelaySettings,
                     k_ibr: float,
                     f_gfm: float) -> tuple:
        """Return (action, pilot_tx, reason, confidence)."""
        conf = 0.90 - 0.05 * f_gfm  # GFM lowers confidence slightly

        if self._scheme == "POTT":
            return self._pott(relay_id, zone, is_reverse, rx_signal, conf)

        elif self._scheme == "DCB":
            return self._dcb(t, relay_id, zone, is_reverse, rx_signal, conf)

        elif self._scheme == "PUTT":
            return self._putt(relay_id, zone, is_reverse, rx_signal, conf)

        else:  # Zone-based fallback (no pilot)
            return self._zone_trip(relay_id, zone, is_reverse, s, i_pu, conf)

    # ------------------------------------------------------------------
    def _pott(self, relay_id, zone, is_reverse, rx_signal, conf):
        """POTT: Zone-2 forward → send PERM. Receive PERM + Zone-2 → TRIP."""
        pilot_tx = ""
        if zone in (1, 2) and not is_reverse:
            pilot_tx = "PERM"

        if zone == 1:
            return _TRIP, pilot_tx, "Zone-1 TRIP (POTT)", conf

        if zone == 2 and rx_signal == "PERM" and not is_reverse:
            return _TRIP, pilot_tx, "Zone-2 POTT TRIP (PERM rx)", conf * 0.95

        if is_reverse:
            return _BLOCK, "", "Reverse element BLOCK (POTT)", conf

        if zone > 0:
            return _PERMIT, pilot_tx, f"Zone-{zone} forward, awaiting PERM", conf * 0.80

        return _NONE, pilot_tx, "No pickup", 1.0

    # ------------------------------------------------------------------
    def _dcb(self, t, relay_id, zone, is_reverse, rx_signal, conf):
        """DCB: Reverse → send BLOCK. No BLOCK rx + Zone-2 + t_coord → TRIP."""
        pilot_tx = "BLOCK" if is_reverse else ""

        if zone == 1:
            return _TRIP, pilot_tx, "Zone-1 TRIP (DCB)", conf

        if zone == 2 and rx_signal != "BLOCK":
            if self._dcb_t_start[relay_id] is None:
                self._dcb_t_start[relay_id] = t
                return _PERMIT, pilot_tx, "DCB: timing coordination delay", conf * 0.80

            elapsed = t - self._dcb_t_start[relay_id]
            if elapsed >= _T_COORD_DCB:
                self._dcb_t_start[relay_id] = None
                return _TRIP, pilot_tx, f"Zone-2 DCB TRIP (t={elapsed*1000:.0f}ms)", conf * 0.92

            return _PERMIT, pilot_tx, "DCB: timing coordination delay", conf * 0.80

        if is_reverse or rx_signal == "BLOCK":
            self._dcb_t_start[relay_id] = None
            return _BLOCK, pilot_tx, "DCB BLOCK (reverse or BLOCK rx)", conf

        return _NONE, pilot_tx, "No pickup", 1.0

    # ------------------------------------------------------------------
    def _putt(self, relay_id, zone, is_reverse, rx_signal, conf):
        """PUTT: Zone-1 → send PERM. Receive PERM → TRIP immediately."""
        pilot_tx = "PERM" if zone == 1 and not is_reverse else ""

        if zone == 1 and not is_reverse:
            return _TRIP, pilot_tx, "Zone-1 TRIP (PUTT)", conf

        if rx_signal == "PERM" and not is_reverse:
            return _TRIP, pilot_tx, "PUTT TRIP (PERM rx)", conf * 0.90

        if is_reverse:
            return _BLOCK, "", "Reverse element BLOCK (PUTT)", conf

        if zone > 0:
            return _PERMIT, pilot_tx, f"Zone-{zone} forward, no PERM rx", conf * 0.75

        return _NONE, pilot_tx, "No pickup", 1.0

    # ------------------------------------------------------------------
    def _zone_trip(self, relay_id, zone, is_reverse, s, i_pu, conf):
        """Fallback: simple zone trip without pilot."""
        if zone == 1 and not is_reverse:
            return _TRIP, "", "Zone-1 TRIP", conf
        if zone == 2 and not is_reverse:
            return _TRIP, "", "Zone-2 TRIP (no pilot)", conf * 0.85
        if is_reverse:
            return _BLOCK, "", "Reverse element BLOCK", conf
        if i_pu > s.pickup_pu:
            return _PERMIT, "", "OC pickup, no zone", conf * 0.70
        return _NONE, "", "No pickup", 1.0

    # ------------------------------------------------------------------
    def set_pilot_rx(self, relay_id: str, signal: str) -> None:
        """Inject a pilot channel signal for a relay (for simulation)."""
        self._pilot_rx[relay_id] = signal

    def reset(self) -> None:
        self._pilot_rx.clear()
        for k in self._dcb_t_start:
            self._dcb_t_start[k] = None

    @property
    def scheme(self) -> str:
        return self._scheme

    @property
    def relay_ids(self) -> List[str]:
        return list(self._settings.keys())
