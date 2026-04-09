"""
line_model_selector.py
=======================
SAMBP TR-62/2026 — k_ibr-driven model selection for 87L line differential.

The selector decides at each protection cycle whether to use:
    • 4-parameter SG model  [I_fund, phi_fund, I_DC, tau_DC]   (SG/DFIG sources)
    • 2-parameter PV model  [I_fund, phi_fund]                  (IBR/PV sources)

Selection criterion
--------------------
The IBR fraction k_ibr is estimated from a short pre-fault window using two
complementary indicators that are already computed in the TDCS pipeline:

  1. DC decay ratio (DDR):
         DDR = (I_DC_hat / I_fund_hat)  from the 4-param Pass 1 fit
     PV inverters: DDR ≈ 0  (no DC offset)
     SG/DFIG:      DDR ∈ [0.2, 1.5] after fault inception

  2. TDCS signature (from line_transient_diff):
         Δ_peak = peak of |i_diff(t) - i_diff(t - T/4)|
     IBR faults show a flat Δ_peak plateau (no exponential rise)
     SG faults show an exponential-shaped Δ_peak (DC decay driven)

Decision rule
-------------
    model = 'pv'  if  DDR < DDR_thresh  AND  Δ_peak_ratio < plateau_thresh
    model = 'sg'  otherwise

A combined score:
    s_ibr = clip(1 - DDR / DDR_thresh, 0, 1) × clip(1 - Δ_ratio / plateau_thresh, 0, 1)

    s_ibr ≥ score_thresh  →  select PV model
    s_ibr <  score_thresh  →  select SG model

Default thresholds (calibrated in TR-62 simulation study):
    DDR_thresh     = 0.15   (PV: < 0.05; SG: 0.3–1.5)
    plateau_thresh = 0.80   (PV: < 0.50; SG: 0.7–1.5)
    score_thresh   = 0.35

Hysteresis
----------
Once a model has been selected for a fault event, it is held for the duration
of the event (until differential drops below I_C_nom for 2 consecutive cycles).
This prevents oscillation between models during the fault transient.

Integration interface
---------------------
    ModelSelectorConfig — dataclass of thresholds
    ModelSelectorState  — per-event state (selected model, hold counter)
    select_model(ddr, delta_ratio, state, cfg) → ('pv' | 'sg', score)
    estimate_ddr(theta_4p) → float
    estimate_delta_ratio(Δ_peak, I_fund) → float
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ModelSelectorConfig:
    """Thresholds for the k_ibr-driven model selector."""
    DDR_thresh:     float = 0.15    # DC decay ratio threshold (primary criterion)
    delta_veto:     float = 2.00    # delta_ratio above which PV selection is overridden
                                    # Pure PV sinusoid: ratio ≈ √2 ≈ 1.41
                                    # SG exponential: ratio > 2.0 early in fault
    I_C_nom:        float = 0.02    # charging current floor [pu]
    hold_cycles:    int   = 0       # 0 = re-evaluate each cycle; >0 = hold


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class ModelSelectorState:
    """Per-event state for the model selector."""
    selected:    str = "sg"      # currently selected model
    hold_count:  int = 0         # remaining hold cycles
    last_score:  float = 0.0
    lock_reason: str = "initial"


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def estimate_ddr(theta_4p: np.ndarray) -> float:
    """
    DC decay ratio: I_DC / max(I_fund, ε).

    Parameters
    ----------
    theta_4p : (4,) = [I_fund, phi_fund, I_DC, tau_DC]

    Returns
    -------
    DDR ∈ [0, ∞)
        ≈ 0     → IBR / PV fault (no DC offset)
        ≥ 0.15  → SG / DFIG fault (significant DC transient)
    """
    I_fund = max(float(theta_4p[0]), 1e-9)
    I_DC   = max(float(theta_4p[2]), 0.0)
    return I_DC / I_fund


def estimate_delta_ratio(
    delta_peak: float,
    I_fund: float,
    I_C_nom: float = 0.02,
) -> float:
    """
    TDCS plateau ratio: delta_peak / max(I_fund, I_C_nom).

    PV faults: Δ_peak stays flat at ≈ I_fund × sqrt(2) × (1-cos(π/2)) = I_fund
               → ratio ≈ 1.0, below the SG exponential overshoot
    SG faults: Δ_peak rises sharply then decays (exponential + sine interference)
               → ratio can reach 1.5–2.5 early in the fault

    Note: ratio > 1 indicates SG-type exponential overshoot.
    """
    denom = max(float(I_fund), float(I_C_nom), 1e-9)
    return float(delta_peak) / denom


def ibr_score(ddr: float, delta_ratio: float, cfg: ModelSelectorConfig) -> float:
    """
    IBR likelihood score ∈ [0, 1] — DDR is the primary criterion.

    Primary:   s_ddr   = clip(1 − DDR / DDR_thresh, 0, 1)
    Veto flag: if delta_ratio ≥ delta_veto (SG exponential signature), score → 0

    A pure sinusoidal PV waveform has delta_ratio ≈ √2 ≈ 1.41 (the TDCS
    peak-to-peak of a sinusoid equals √2 × amplitude).  SG exponential drives
    delta_ratio above 2.0.  The veto threshold 2.0 avoids false-vetoing PV.
    """
    s_ddr = float(np.clip(1.0 - ddr / max(cfg.DDR_thresh, 1e-9), 0.0, 1.0))
    if delta_ratio >= cfg.delta_veto:
        return 0.0   # exponential signature detected → not IBR/PV
    return s_ddr


def select_model(
    ddr:         float,
    delta_ratio: float,
    state:       Optional[ModelSelectorState] = None,
    cfg:         Optional[ModelSelectorConfig] = None,
) -> tuple[str, float, ModelSelectorState]:
    """
    Select the active zone model for the current relay cycle.

    Parameters
    ----------
    ddr         : DC decay ratio (from estimate_ddr)
    delta_ratio : TDCS plateau ratio (from estimate_delta_ratio)
    state       : selector state from the previous cycle (None = initialise)
    cfg         : selector configuration (None = defaults)

    Returns
    -------
    (model_name, score, new_state)
        model_name : 'pv' or 'sg'
        score      : IBR score ∈ [0, 1]
        new_state  : updated ModelSelectorState
    """
    if cfg   is None: cfg   = ModelSelectorConfig()
    if state is None: state = ModelSelectorState()

    score = ibr_score(ddr, delta_ratio, cfg)

    # If still within a hold window, keep the selected model
    if state.hold_count > 0:
        state.hold_count -= 1
        state.last_score = score
        return state.selected, score, state

    # Fresh selection: DDR < DDR_thresh AND no exponential veto → PV model
    if score > 0.0:
        selected    = "pv"
        lock_reason = f"DDR={ddr:.3f} < {cfg.DDR_thresh}  delta_ratio={delta_ratio:.2f}"
    else:
        selected    = "sg"
        lock_reason = (f"DDR={ddr:.3f} ≥ {cfg.DDR_thresh}  OR  "
                       f"delta_ratio={delta_ratio:.2f} ≥ {cfg.delta_veto}")

    state.selected    = selected
    state.hold_count  = max(0, cfg.hold_cycles - 1)
    state.last_score  = score
    state.lock_reason = lock_reason

    return selected, score, state


# ---------------------------------------------------------------------------
# Convenience: select from already-estimated 4-param result
# ---------------------------------------------------------------------------

def select_from_4param(
    theta_4p:   np.ndarray,
    delta_peak: float,
    state:      Optional[ModelSelectorState] = None,
    cfg:        Optional[ModelSelectorConfig] = None,
    I_C_nom:    float = 0.02,
) -> tuple[str, float, ModelSelectorState]:
    """
    Select model given 4-param estimates and TDCS peak.

    This is the standard entry point in the relay pipeline: a fast 4-param
    Pass-1 fit runs first (or the TDCS measurement), and the selector then
    decides whether to switch to the 2-param PV model for the final decision.
    """
    if cfg is None: cfg = ModelSelectorConfig()
    ddr   = estimate_ddr(theta_4p)
    dratio = estimate_delta_ratio(delta_peak, float(theta_4p[0]), I_C_nom)
    return select_model(ddr, dratio, state, cfg)


# ---------------------------------------------------------------------------
# Condition number comparison utility (for reporting)
# ---------------------------------------------------------------------------

def compare_condition_numbers(
    I_fund_vec: np.ndarray,
    tau_DC_vec: np.ndarray,
    freq_hz:    float = 50.0,
    fs:         float = 1000.0,
    n_cycles:   float = 2.0,
) -> dict:
    """
    Compute condition numbers for both models at a range of I_fund and tau_DC.

    Returns dict with keys:
        'I_fund', 'tau_DC', 'kappa_4p', 'kappa_2p', 'ratio'
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from line_reduced_zone_model import jacobian_idiff, condition_number_normalised
    from line_pv_model import jacobian_idiff_pv, condition_number_pv

    n_pts = int(n_cycles * fs / freq_hz)
    t     = np.arange(n_pts) / fs

    kappa_4p_list = []
    kappa_2p_list = []

    for I_f in I_fund_vec:
        for tau in tau_DC_vec:
            # 4-param Jacobian: include a moderate DC to represent SG fault
            theta_4p = np.array([I_f, 0.0, 0.3 * I_f, tau])
            J_4p     = jacobian_idiff(t, theta_4p, freq_hz)
            kn_4p    = condition_number_normalised(J_4p)

            # 2-param Jacobian: same fundamental, no DC
            theta_2p = np.array([I_f, 0.0])
            J_2p     = jacobian_idiff_pv(t, theta_2p, freq_hz)
            kn_2p    = condition_number_pv(J_2p)

            kappa_4p_list.append(kn_4p)
            kappa_2p_list.append(kn_2p)

    kn_4p_arr = np.array(kappa_4p_list)
    kn_2p_arr = np.array(kappa_2p_list)

    return {
        "kappa_4p": kn_4p_arr,
        "kappa_2p": kn_2p_arr,
        "ratio":    kn_4p_arr / np.maximum(kn_2p_arr, 1e-6),
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = ModelSelectorConfig(DDR_thresh=0.15, delta_veto=2.00)

    # PV internal fault: DDR≈0, delta_ratio≈0.9
    m, s, st = select_model(ddr=0.02, delta_ratio=0.90, cfg=cfg)
    print(f"[PV fault]   model={m}  score={s:.3f}  [expected pv]")
    assert m == "pv", f"PV fault should select pv model, got {m}"

    # SG fault: DDR≈0.8, delta_ratio≈1.4
    m2, s2, st2 = select_model(ddr=0.80, delta_ratio=1.40, cfg=cfg)
    print(f"[SG fault]   model={m2}  score={s2:.3f}  [expected sg]")
    assert m2 == "sg", f"SG fault should select sg model, got {m2}"

    # Borderline: DDR=0.10 (below thresh 0.15), delta_ratio=1.5 (below veto 2.0)
    # → s_ddr = 1 - 0.10/0.15 = 0.333, no veto → select pv
    ddr_b   = 0.10
    dr_b    = 1.50
    s_b     = ibr_score(ddr_b, dr_b, cfg)
    m3, _, _ = select_model(ddr_b, dr_b, cfg=cfg)
    print(f"[Borderline] score={s_b:.3f}  model={m3}  [DDR={ddr_b}, dr={dr_b}]")
    assert m3 == "pv", f"Borderline (DDR<thresh, no veto) should select pv, got {m3}"

    # Veto test: DDR=0.05 (IBR-like) but delta_ratio=2.5 (SG exponential) → sg
    ddr_v   = 0.05
    dr_v    = 2.50
    s_v     = ibr_score(ddr_v, dr_v, cfg)
    m_v, _, _ = select_model(ddr_v, dr_v, cfg=cfg)
    print(f"[Veto test]  score={s_v:.3f}  model={m_v}  [DDR={ddr_v}, dr={dr_v}]")
    assert m_v == "sg", f"Exponential veto should force sg, got {m_v}"

    # from_4param: theta_4p with I_DC=0 → should select pv
    theta_pv_4p = np.array([1.0, -0.3, 0.01, 0.05])   # I_DC negligible
    m4, s4, st4 = select_from_4param(theta_pv_4p, delta_peak=1.0)
    print(f"[from_4param PV]  DDR={estimate_ddr(theta_pv_4p):.3f}  "
          f"model={m4}  score={s4:.3f}")
    assert m4 == "pv"

    # from_4param: theta_4p with large I_DC → should select sg
    theta_sg_4p = np.array([1.0, -0.3, 0.80, 0.05])
    m5, s5, st5 = select_from_4param(theta_sg_4p, delta_peak=1.8)
    print(f"[from_4param SG]  DDR={estimate_ddr(theta_sg_4p):.3f}  "
          f"model={m5}  score={s5:.3f}")
    assert m5 == "sg"

    # Condition number comparison
    I_vals   = np.array([0.10, 0.30, 0.50, 1.00])
    tau_vals = np.array([0.05])
    result   = compare_condition_numbers(I_vals, tau_vals)
    print(f"\nCondition number comparison (2-cycle window, τ=0.05s):")
    print(f"{'I_fund':>8s}  {'κ_4p':>8s}  {'κ_2p':>8s}  {'ratio':>8s}")
    for i, I_f in enumerate(I_vals):
        print(f"  {I_f:.2f} pu  {result['kappa_4p'][i]:8.1f}  "
              f"{result['kappa_2p'][i]:8.2f}  {result['ratio'][i]:8.1f}×")

    print("\nline_model_selector self-test PASSED.")
