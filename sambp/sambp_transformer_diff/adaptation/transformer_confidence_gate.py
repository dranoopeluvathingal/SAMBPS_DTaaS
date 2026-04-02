"""
transformer_confidence_gate.py
================================
Confidence gate for the model-based 87T differential relay.

Philosophy (same as sambp_sync_oc)
------------------------------------
    • Only issue a model-based trip when the estimator reports high confidence:
          κ_n < κ_thresh  AND  residual_norm < rn_thresh  AND  convergence flag
    • When confidence is low, fall back to the conventional relay decision.
    • The gate also implements a "confirmation window": the internal-fault flag
      must persist for n_confirm consecutive windows before the model-based trip
      overrides blocking.

Gate decision flow:
    ┌──────────────────────────────────────────────┐
    │  input: ZoneModelState, conventional trip     │
    │  1. κ_n check           → reject if too high │
    │  2. residual check      → reject if too high │
    │  3. f_int threshold     → detect internal    │
    │  4. blocking flag check → suppress if active │
    │  5. confirmation counter → hysteresis        │
    │  output: final_trip, source ("model"/"conv") │
    └──────────────────────────────────────────────┘
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from models.transformer_reduced_zone_model import ZoneModelState


# ---------------------------------------------------------------------------
# Gate configuration
# ---------------------------------------------------------------------------

@dataclass
class ConfidenceGateConfig:
    kappa_thresh: float      = 30.0    # max acceptable κ_n
    residual_thresh: float   = 0.15    # max acceptable normalised residual [pu]
    f_int_trip_thresh: float = 0.60    # minimum derived f_int to call internal fault
    n_confirm: int           = 2       # consecutive windows required to confirm
    confidence_min: float    = 0.40    # minimum composite confidence score


# ---------------------------------------------------------------------------
# Gate state (maintains confirmation counter between calls)
# ---------------------------------------------------------------------------

@dataclass
class GateState:
    confirm_count: int = 0
    last_source: str   = "conventional"


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------

@dataclass
class GateDecision:
    final_trip: bool
    model_trip: bool          # would model alone trip?
    conventional_trip: bool
    confidence: float
    source: str               # "model" | "conventional" | "blocked"
    reason: str               # human-readable explanation


def evaluate_confidence_gate(
    zone_state: ZoneModelState,
    conventional_trip: bool,
    gate_cfg: Optional[ConfidenceGateConfig] = None,
    gate_state: Optional[GateState] = None,
) -> tuple[GateDecision, GateState]:
    """
    Evaluate the confidence gate for one relay cycle.

    Parameters
    ----------
    zone_state : ZoneModelState from transformer_inverse_estimator
    conventional_trip : bool — outcome of the conventional 87T relay
    gate_cfg : ConfidenceGateConfig (defaults if None)
    gate_state : GateState (persistent across calls; creates new if None)

    Returns
    -------
    (GateDecision, updated GateState)
    """
    if gate_cfg is None:
        gate_cfg = ConfidenceGateConfig()
    if gate_state is None:
        gate_state = GateState()

    conf   = zone_state.confidence
    kn     = zone_state.kappa_n
    rn     = zone_state.residual_norm
    f_int  = zone_state.f_int

    # ----- Confidence checks -------------------------------------------------
    high_confidence = (
        kn  < gate_cfg.kappa_thresh
        and rn  < gate_cfg.residual_thresh
        and conf >= gate_cfg.confidence_min
    )

    # ----- Model-based internal fault indicator ------------------------------
    # Requires conventional trip as necessary condition: the model gate ONLY
    # overrides blocking (not the trip characteristic itself).  This prevents
    # the model from tripping when I_op < I_op_min (e.g. normal load).
    model_says_internal = (
        high_confidence
        and f_int >= gate_cfg.f_int_trip_thresh
        and not zone_state.is_inrush
        and not zone_state.is_overexcitation
        and conventional_trip   # must also penetrate the trip characteristic
    )

    # ----- Confirmation counter ----------------------------------------------
    if model_says_internal:
        gate_state.confirm_count += 1
    else:
        gate_state.confirm_count = 0

    confirmed = gate_state.confirm_count >= gate_cfg.n_confirm

    # ----- Blocking flags ----------------------------------------------------
    blocking_active = zone_state.is_inrush or zone_state.is_overexcitation

    # ----- Final trip logic --------------------------------------------------
    if confirmed and not blocking_active:
        final_trip = True
        source     = "model"
        reason     = (f"model confirmed: f_int={f_int:.3f}  "
                      f"κ_n={kn:.1f}  conf={conf:.3f}  "
                      f"n_confirm={gate_state.confirm_count}")
    elif conventional_trip and not blocking_active:
        final_trip = True
        source     = "conventional"
        reason     = "conventional 87T trip (model not confirmed or low confidence)"
    elif blocking_active:
        final_trip = False
        source     = "blocked"
        reason     = ("inrush_block" if zone_state.is_inrush
                      else "overexcitation_block")
    else:
        final_trip = False
        source     = "no_trip"
        reason     = "no trip condition met"

    gate_state.last_source = source

    decision = GateDecision(
        final_trip        = final_trip,
        model_trip        = confirmed,
        conventional_trip = conventional_trip,
        confidence        = conf,
        source            = source,
        reason            = reason,
    )

    return decision, gate_state


# ---------------------------------------------------------------------------
# Batch evaluation over a study run
# ---------------------------------------------------------------------------

def run_gate_batch(
    zone_states: list[ZoneModelState],
    conventional_trips: list[bool],
    gate_cfg: Optional[ConfidenceGateConfig] = None,
) -> list[GateDecision]:
    """
    Evaluate the gate over an ordered list of relay cycles.
    The confirmation counter resets between each call to this function.
    """
    gate_state = GateState()
    decisions  = []
    for zs, ct in zip(zone_states, conventional_trips):
        dec, gate_state = evaluate_confidence_gate(zs, ct, gate_cfg, gate_state)
        decisions.append(dec)
    return decisions


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from models.transformer_reduced_zone_model import interpret_theta
    import numpy as np

    cfg = ConfidenceGateConfig(n_confirm=2)

    # ----- Scenario 1: genuine internal fault with high confidence -----------
    # No blocking signatures → f_int derived high
    theta_int = np.array([2.5, 0.1, 0.01, 0.01, 0.03])
    zs_int = interpret_theta(theta_int, kappa_n=8.0, residual_norm=0.04)
    gs = GateState()
    for cycle in range(4):
        dec, gs = evaluate_confidence_gate(zs_int, conventional_trip=True,
                                           gate_cfg=cfg, gate_state=gs)
        print(f"  Int cycle {cycle}: trip={dec.final_trip}  "
              f"source={dec.source}  confirm={gs.confirm_count}")
    assert dec.final_trip and dec.source == "model", "Should confirm internal fault"

    # ----- Scenario 2: inrush (should block) ----------------------------------
    theta_inrush = np.array([3.0, 0.2, 0.50, 0.02, 0.05])
    zs_inrush = interpret_theta(theta_inrush, kappa_n=5.0, residual_norm=0.02)
    gs2 = GateState()
    dec2, _ = evaluate_confidence_gate(zs_inrush, conventional_trip=True,
                                       gate_cfg=cfg, gate_state=gs2)
    print(f"\n  Inrush: trip={dec2.final_trip}  source={dec2.source}")
    assert not dec2.final_trip and dec2.source == "blocked", "Inrush must block"

    # ----- Scenario 3: low confidence — fall back to conventional -----------
    theta_low = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
    zs_low = interpret_theta(theta_low, kappa_n=120.0, residual_norm=0.80)
    gs3 = GateState()
    dec3, _ = evaluate_confidence_gate(zs_low, conventional_trip=True,
                                       gate_cfg=cfg, gate_state=gs3)
    print(f"  Low-conf: trip={dec3.final_trip}  source={dec3.source}")
    assert dec3.final_trip and dec3.source == "conventional", \
        "Low confidence should fall back to conventional"

    print("\ntransformer_confidence_gate self-test PASSED.")
