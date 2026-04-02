"""
line_confidence_gate.py
========================
SAMBP confidence gate for the 87L line differential relay.

Follows the same pattern as transformer_confidence_gate.py but adapted to
the 87L zone model flags: is_internal, is_sync_error.

Key logic:
    • High confidence: κ_n < κ_thresh  AND  residual < rn_thresh
    • Model confirms internal: f_int > f_int_thresh  AND  NOT is_sync_error
    • If sync error flag is active: raise threshold n_confirm_sync (more
      confirmation cycles required before allowing model-based trip)
    • Falls back to conventional trip if model confidence is low
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class LineConfidenceGateConfig:
    kappa_thresh: float      = 30.0
    residual_thresh: float   = 0.10
    f_int_thresh: float      = 0.50
    n_confirm: int           = 2       # overridden by fallback logic per mode
    n_confirm_sync: int      = 4       # extra caution when sync_error is active
    confidence_min: float    = 0.40
    # Stage 2: suppress conventional trip when model identifies non-internal source
    model_veto_enable: bool  = True


@dataclass
class LineGateState:
    confirm_count: int = 0
    last_source: str   = "conventional"


@dataclass
class LineGateDecision:
    final_trip: bool
    model_trip: bool
    conventional_trip: bool
    confidence: float
    source: str
    reason: str


def evaluate_87L_confidence_gate(
    zone_state,               # LineZoneState
    conventional_trip: bool,
    gate_cfg: Optional[LineConfidenceGateConfig] = None,
    gate_state: Optional[LineGateState] = None,
) -> tuple[LineGateDecision, LineGateState]:
    """
    Evaluate the confidence gate for one 87L relay cycle.

    Uses the same flow as the 87T gate with sync-error awareness.
    """
    if gate_cfg  is None: gate_cfg  = LineConfidenceGateConfig()
    if gate_state is None: gate_state = LineGateState()

    conf  = zone_state.confidence
    kn    = zone_state.kappa_n
    rn    = zone_state.residual_norm
    f_int = zone_state.f_int

    high_confidence = (
        kn   < gate_cfg.kappa_thresh
        and rn   < gate_cfg.residual_thresh
        and conf >= gate_cfg.confidence_min
    )

    # Sync-error → require more confirmation cycles
    n_confirm_needed = (gate_cfg.n_confirm_sync
                        if zone_state.is_sync_error
                        else gate_cfg.n_confirm)

    model_says_internal = (
        high_confidence
        and f_int >= gate_cfg.f_int_thresh
        and not zone_state.is_sync_error   # sync error alone is not a fault
        and conventional_trip
    )

    # Stage 2: model veto of conventional trip.
    # When the model is identifiable (κ_n < thresh) AND f_int clearly says the
    # differential is NOT an internal fault, suppress the conventional trip.
    # This handles degraded-channel scenarios where residual skew creates a
    # spurious differential that crosses I_op_min.
    model_vetoes_conventional = (
        gate_cfg.model_veto_enable
        and kn < gate_cfg.kappa_thresh
        and f_int < gate_cfg.f_int_thresh
    )

    if model_says_internal:
        gate_state.confirm_count += 1
    else:
        gate_state.confirm_count = 0

    confirmed = gate_state.confirm_count >= n_confirm_needed

    if confirmed:
        final_trip = True
        source     = "model"
        reason     = (f"model confirmed: f_int={f_int:.3f}  "
                      f"κ_n={kn:.1f}  n_confirm={gate_state.confirm_count}")
    elif model_vetoes_conventional:
        final_trip = False
        source     = "model_veto"
        reason     = (f"model veto: f_int={f_int:.3f} < {gate_cfg.f_int_thresh:.3f}, "
                      f"κ_n={kn:.1f}")
    elif conventional_trip:
        final_trip = True
        source     = "conventional"
        reason     = "conventional 87L trip (model not confirmed)"
    else:
        final_trip = False
        source     = "no_trip"
        reason     = "no trip condition"

    gate_state.last_source = source

    return LineGateDecision(
        final_trip        = final_trip,
        model_trip        = confirmed,
        conventional_trip = conventional_trip,
        confidence        = conf,
        source            = source,
        reason            = reason,
    ), gate_state


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.line_reduced_zone_model import interpret_theta

    cfg = LineConfidenceGateConfig(n_confirm=2)

    # ----- Scenario 1: internal fault, high confidence ----------------------
    theta_int = np.array([3.5, -0.2, 1.2, 0.05])
    zs = interpret_theta(theta_int, kappa_n=7.0, residual_norm=0.03)
    gs = LineGateState()
    for cy in range(3):
        dec, gs = evaluate_87L_confidence_gate(zs, conventional_trip=True,
                                               gate_cfg=cfg, gate_state=gs)
        print(f"  Internal cycle {cy}: trip={dec.final_trip} source={dec.source}")
    assert dec.final_trip and dec.source == "model"

    # ----- Scenario 2: sync error only — Stage 2 veto should fire -----------
    # Small I_fund (sync-error range), f_int≈0, κ_n=10 → model_vetoes_conventional
    theta_sync = np.array([0.10, 0.4, 0.0, 0.05])
    zs_sync = interpret_theta(theta_sync, kappa_n=10.0, residual_norm=0.02)
    gs2 = LineGateState()
    for cy in range(6):
        dec2, gs2 = evaluate_87L_confidence_gate(zs_sync, conventional_trip=True,
                                                  gate_cfg=cfg, gate_state=gs2)
    # Stage 2: model identifies f_int=0 → veto conventional trip
    print(f"  Sync: trip={dec2.final_trip}  source={dec2.source}  "
          f"f_int={zs_sync.f_int:.3f}")
    assert not dec2.final_trip and dec2.source == "model_veto", \
        "Sync error (f_int=0, κ_n low) must be vetoed by Stage-2 gate"

    # ----- Scenario 3: low confidence → conventional fallback ---------------
    theta_low = np.array([1.5, 0.5, 0.3, 0.05])
    zs_low = interpret_theta(theta_low, kappa_n=200.0, residual_norm=1.5)
    gs3 = LineGateState()
    dec3, _ = evaluate_87L_confidence_gate(zs_low, conventional_trip=True,
                                            gate_cfg=cfg, gate_state=gs3)
    print(f"  Low conf: trip={dec3.final_trip}  source={dec3.source}")
    assert dec3.source == "conventional"

    # ----- Scenario 4: Stage 2 — model veto of spurious conventional trip ----
    # Small I_fund (0.08 pu < 0.20 pu fault threshold), small I_DC → f_int small
    # κ_n=5.0 → identifiable → veto fires
    theta_skew = np.array([0.08, 0.1, 0.02, 0.02])
    zs_skew = interpret_theta(theta_skew, kappa_n=5.0, residual_norm=0.05)
    gs4 = LineGateState()
    dec4, _ = evaluate_87L_confidence_gate(zs_skew, conventional_trip=True,
                                            gate_cfg=cfg, gate_state=gs4)
    print(f"\n  Model-veto: trip={dec4.final_trip}  source={dec4.source}  "
          f"f_int={zs_skew.f_int:.3f}")
    assert not dec4.final_trip and dec4.source == "model_veto", \
        "Skew-induced spurious trip must be vetoed by Stage-2 gate"

    # ----- Scenario 5: genuine internal fault must NOT be vetoed -------------
    theta_int2 = np.array([4.0, -0.1, 1.5, 0.03])
    zs_int2 = interpret_theta(theta_int2, kappa_n=4.5, residual_norm=0.03)
    gs5 = LineGateState()
    for cy in range(3):
        dec5, gs5 = evaluate_87L_confidence_gate(zs_int2, conventional_trip=True,
                                                  gate_cfg=cfg, gate_state=gs5)
    print(f"\n  Int-no-veto: trip={dec5.final_trip}  source={dec5.source}  "
          f"f_int={zs_int2.f_int:.3f}")
    assert dec5.final_trip, "Large internal fault must still trip"

    print("line_confidence_gate self-test PASSED.")
