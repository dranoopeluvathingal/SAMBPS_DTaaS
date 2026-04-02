"""
bus_confidence_gate.py
=======================
Confidence gate for the SAMBP 87B bus differential relay.

Gate logic (same pattern as 87T/87L)
--------------------------------------
    1. High-confidence check: κ_n < κ_thresh  AND  residual < rn_thresh
    2. model_says_internal: high_conf AND f_int ≥ f_int_thresh AND conv_trip
    3. Confirmation counter: must persist ≥ n_confirm cycles
    4. Stage-2 model_vetoes_conventional: κ_n < thresh AND f_int < thresh
       → suppresses conventional trip from CT-saturation / CT open-circuit
    5. Fallback: if low confidence → pass conventional trip through

The Stage-2 veto is critical for 87B because:
  • External fault + CT saturation creates apparent I_op ∝ ε_CT
  • The zone model identifies ε_CT > 0 → f_int drops below threshold
  • Veto suppresses the conventional trip → no mal-trip

CT open-circuit (complete failure):
  The zone model sees I_op = I_load with ε_CT ≈ 0 (fundamental, no saturation).
  f_int ≈ 1.0 → veto does NOT fire → conventional trip passes through.
  This is documented as an irreducible limitation; a high-impedance bus
  differential scheme is needed for immunity to CT open-circuits.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.bus_reduced_zone_model import BusZoneModelState


@dataclass
class BusGateConfig:
    kappa_thresh: float      = 30.0
    residual_thresh: float   = 0.15
    f_int_trip_thresh: float = 0.60
    n_confirm: int           = 2
    confidence_min: float    = 0.40
    model_veto_enable: bool  = True


@dataclass
class BusGateState:
    confirm_count: int = 0
    last_source: str   = "conventional"


@dataclass
class BusGateDecision:
    final_trip: bool
    model_trip: bool
    conventional_trip: bool
    confidence: float
    source: str
    reason: str


def evaluate_87B_confidence_gate(
    zone_state: BusZoneModelState,
    conventional_trip: bool,
    gate_cfg: Optional[BusGateConfig] = None,
    gate_state: Optional[BusGateState] = None,
) -> tuple[BusGateDecision, BusGateState]:
    """Evaluate the confidence gate for one 87B relay cycle."""
    if gate_cfg  is None: gate_cfg  = BusGateConfig()
    if gate_state is None: gate_state = BusGateState()

    conf   = zone_state.confidence
    kn     = zone_state.kappa_n
    rn     = zone_state.residual_norm
    f_int  = zone_state.f_int
    eps_ct = zone_state.epsilon_CT

    high_confidence = (
        kn   < gate_cfg.kappa_thresh
        and rn   < gate_cfg.residual_thresh
        and conf >= gate_cfg.confidence_min
    )

    # Stage-2 veto: suppress conventional trip when model is identifiable
    # and differential is NOT attributed to an internal fault.
    model_vetoes_conventional = (
        gate_cfg.model_veto_enable
        and kn < gate_cfg.kappa_thresh
        and f_int < gate_cfg.f_int_trip_thresh
    )

    model_says_internal = (
        high_confidence
        and f_int >= gate_cfg.f_int_trip_thresh
        and conventional_trip
    )

    if model_says_internal:
        gate_state.confirm_count += 1
    else:
        gate_state.confirm_count = 0

    confirmed = gate_state.confirm_count >= gate_cfg.n_confirm

    if confirmed:
        final_trip = True
        source     = "model"
        reason     = (f"model confirmed: f_int={f_int:.3f}  "
                      f"κ_n={kn:.1f}  conf={conf:.3f}  "
                      f"n_confirm={gate_state.confirm_count}")
    elif model_vetoes_conventional:
        final_trip = False
        source     = "model_veto"
        reason     = (f"model veto: f_int={f_int:.3f} < {gate_cfg.f_int_trip_thresh:.3f}, "
                      f"κ_n={kn:.1f}  ε_CT={eps_ct:.3f}")
    elif conventional_trip:
        final_trip = True
        source     = "conventional"
        reason     = "conventional 87B trip (model not confirmed or low confidence)"
    else:
        final_trip = False
        source     = "no_trip"
        reason     = "no trip condition"

    gate_state.last_source = source

    return BusGateDecision(
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
    from models.bus_reduced_zone_model import interpret_theta

    cfg = BusGateConfig(n_confirm=2)

    # ----- Scenario 1: internal fault (ε_CT=0, f_int=1.0) --------------------
    theta_int = np.array([5.0, 0.1, 0.0])
    zs_int = interpret_theta(theta_int, kappa_n=4.4, residual_norm=0.02)
    gs = BusGateState()
    for cy in range(3):
        dec, gs = evaluate_87B_confidence_gate(zs_int, conventional_trip=True,
                                               gate_cfg=cfg, gate_state=gs)
        print(f"  Internal cycle {cy}: trip={dec.final_trip}  source={dec.source}")
    assert dec.final_trip and dec.source == "model", "Internal fault must confirm"

    # ----- Scenario 2: CT saturation (ε_CT=0.30, f_int=0.0) ------------------
    theta_sat = np.array([2.0, 0.1, 0.30])
    zs_sat = interpret_theta(theta_sat, kappa_n=6.2, residual_norm=0.04)
    gs2 = BusGateState()
    dec2, _ = evaluate_87B_confidence_gate(zs_sat, conventional_trip=True,
                                           gate_cfg=cfg, gate_state=gs2)
    print(f"\n  CT sat: trip={dec2.final_trip}  source={dec2.source}  "
          f"f_int={zs_sat.f_int:.3f}")
    assert not dec2.final_trip and dec2.source == "model_veto", \
        "CT saturation must be vetoed"

    # ----- Scenario 3: low confidence → conventional fallback -----------------
    theta_low = np.array([1.0, 0.0, 0.0])
    zs_low = interpret_theta(theta_low, kappa_n=150.0, residual_norm=1.5)
    gs3 = BusGateState()
    dec3, _ = evaluate_87B_confidence_gate(zs_low, conventional_trip=True,
                                           gate_cfg=cfg, gate_state=gs3)
    print(f"  Low conf: trip={dec3.final_trip}  source={dec3.source}")
    assert dec3.source == "conventional", "Low confidence must fall back"

    # ----- Scenario 4: no trip (I_op < I_op_min) ------------------------------
    theta_nt = np.array([0.05, 0.0, 0.0])
    zs_nt = interpret_theta(theta_nt, kappa_n=4.5, residual_norm=0.05)
    gs4 = BusGateState()
    dec4, _ = evaluate_87B_confidence_gate(zs_nt, conventional_trip=False,
                                           gate_cfg=cfg, gate_state=gs4)
    assert not dec4.final_trip, "No-fault must not trip"

    print("\nbus_confidence_gate self-test PASSED.")
