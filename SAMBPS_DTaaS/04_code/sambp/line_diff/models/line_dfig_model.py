"""
line_dfig_model.py
==================
SAMBP TR-56 / 2026 — 10-parameter DFIG piecewise-ODE fault current model
for 87L line differential protection.

Physical basis
--------------
A Doubly-Fed Induction Generator (DFIG, Type-3 wind turbine) exhibits a
two-phase fault current signature fundamentally different from both SG and
PV sources:

  Phase 1 — Pre-crowbar  (t0 ≤ t < t0 + t_cb):
      The rotor-side converter (RSC) attempts current regulation, but the
      dc-link crowbar threshold is not yet exceeded.  The stator current
      decays from the subtransient value with the stator flux time constant:

          i_DFIG(t) = I_sub · exp(-(t-t0)/τ_ac) · cos(ω_s·t + φ_a)
                    + I_dc  · exp(-(t-t0)/τ_dc)

      I_sub > I_ss is the critical diagnostic — distinguishing DFIG from
      PV where I_sub ≡ 0 (no AC transient, only DC component).

  Phase 2 — Post-crowbar  (t ≥ t0 + t_cb):
      The crowbar fires, short-circuiting the rotor windings.  The machine
      now behaves like a squirrel-cage induction machine with rotor
      resistance R_cb.  The post-crowbar current has two components:

          i_post(t) = I_ss · cos(ω_s·t + φ_cc)
                    + I_slip · cos(ω_slip·t + φ_a)

      where ω_slip = k_slip · ω_s (slip-frequency modulation), and
      I_slip decays as the rotor field re-establishes.

  Smoothed transition (Heaviside sigmoid):
      H(t; t_cb, σ) = 1 / (1 + exp(-(t - (t0 + t_cb)) / σ))

      i_DFIG(t) = (1 - H) · i_pre(t)  +  H · i_post(t)

      σ = 0.5 ms controls the sharpness of the transition.

10-parameter vector θ_DFIG
--------------------------
    0  I_sub   — subtransient current amplitude [pu]     ∈ [0.1,  8.0]
    1  tau_ac  — AC stator flux decay time const [s]    ∈ [0.01, 0.5]
    2  tau_dc  — DC decay time constant [s]             ∈ [0.005, 0.2]
    3  phi_a   — initial phase angle, phase A [rad]     ∈ [−π,   +π ]
    4  I_dc    — DC offset magnitude [pu]               ∈ [0.0,  4.0]
    5  I_ss    — post-crowbar steady-state current [pu] ∈ [0.05, 5.0]
    6  t0      — fault inception time [s]               ∈ (free)
    7  t_cb    — crowbar delay after t0 [s]             ∈ [0.005, 0.15]
    8  phi_cc  — post-crowbar current phase [rad]       ∈ [−π,   +π ]
    9  k_slip  — slip-freq multiplier (ω_slip / ω_s)   ∈ [0.0,  0.5]

CUSUM crowbar detector
-----------------------
    Running pre-fault statistics: μ_pre, σ_pre from first cycle.
    CUSUM statistic:
        S_n = max(0, S_{n-1} + (|i_diff(n)| - μ_pre - δ) / σ_pre)
    Alarm when S_n > h (decision threshold).
    Default: δ = 1.5 (half of minimum detectable change = 3σ), h = 5.0.

Public API
----------
    DEFAULT_THETA_DFIG   — dict of default parameter values
    DFIG_BOUNDS          — list of (lo, hi) per parameter, same order as vector
    THETA_KEYS_DFIG      — ordered key list

    dfig_phase_A(t, theta, f0)         → ndarray  phase-A current
    dfig_three_phase(t, theta, f0)     → dict {ia, ib, ic}
    detect_crowbar_cusum(t, i_diff, ...) → float | None  (crowbar time)
    theta_dfig_to_vector(theta)        → ndarray[10]
    vector_to_theta_dfig(v)            → dict
"""

from __future__ import annotations

import numpy as np
from typing import Optional

# ---------------------------------------------------------------------------
# Parameter definition
# ---------------------------------------------------------------------------

THETA_KEYS_DFIG = [
    "I_sub", "tau_ac", "tau_dc", "phi_a",
    "I_dc", "I_ss", "t0", "t_cb", "phi_cc", "k_slip",
]

DEFAULT_THETA_DFIG: dict = {
    "I_sub":  2.0,    # subtransient current [pu]
    "tau_ac": 0.05,   # AC stator flux decay [s]
    "tau_dc": 0.02,   # DC offset decay [s]
    "phi_a":  0.0,    # phase A initial angle [rad]
    "I_dc":   0.5,    # DC offset [pu]
    "I_ss":   1.0,    # post-crowbar steady state [pu]
    "t0":     0.0,    # fault time [s]  — overridden at runtime
    "t_cb":   0.03,   # crowbar delay after t0 [s]
    "phi_cc": 0.1,    # post-crowbar phase [rad]
    "k_slip": 0.05,   # slip-frequency ratio
}

# Bounds: list of (lo, hi) in THETA_KEYS_DFIG order
DFIG_BOUNDS: list = [
    (0.1,  8.0),    # I_sub
    (0.005, 0.5),   # tau_ac
    (0.003, 0.20),  # tau_dc
    (-np.pi, np.pi),# phi_a
    (0.0,  4.0),    # I_dc
    (0.05, 6.0),    # I_ss
    (-1e9, 1e9),    # t0  (unconstrained — event detector sets this)
    (0.003, 0.15),  # t_cb
    (-np.pi, np.pi),# phi_cc
    (0.0,  0.5),    # k_slip
]

_SIGMA_CB = 5e-4  # Heaviside sigmoid sharpness [s] = 0.5 ms


# ---------------------------------------------------------------------------
# Core model
# ---------------------------------------------------------------------------

def _heaviside_smooth(t: np.ndarray, t_switch: float, sigma: float = _SIGMA_CB) -> np.ndarray:
    """Sigmoid approximation to unit step centred at t_switch."""
    arg = (t - t_switch) / sigma
    arg = np.clip(arg, -50.0, 50.0)   # avoid overflow
    return 1.0 / (1.0 + np.exp(-arg))


def dfig_phase_A(t: np.ndarray, theta: dict, f0: float = 50.0) -> np.ndarray:
    """
    Compute the phase-A DFIG fault current for parameter dict theta.

    Parameters
    ----------
    t     : time vector [s]
    theta : dict with keys in THETA_KEYS_DFIG
    f0    : system frequency [Hz]

    Returns
    -------
    ia : ndarray, same shape as t
    """
    I_sub  = float(theta["I_sub"])
    tau_ac = float(theta["tau_ac"])
    tau_dc = float(theta["tau_dc"])
    phi_a  = float(theta["phi_a"])
    I_dc   = float(theta["I_dc"])
    I_ss   = float(theta["I_ss"])
    t0     = float(theta["t0"])
    t_cb   = float(theta["t_cb"])
    phi_cc = float(theta["phi_cc"])
    k_slip = float(theta["k_slip"])

    ws     = 2.0 * np.pi * f0
    wslip  = k_slip * ws
    dt     = np.maximum(t - t0, 0.0)
    t_sw   = t0 + t_cb

    # Pre-crowbar: decaying AC + DC
    i_pre = (I_sub * np.exp(-dt / tau_ac) * np.cos(ws * t + phi_a)
             + I_dc  * np.exp(-dt / tau_dc))

    # Post-crowbar: current-controlled + slip modulation
    dt_cb = np.maximum(t - t_sw, 0.0)
    i_post = (I_ss  * np.cos(ws * t + phi_cc)
              + I_sub * 0.3 * np.exp(-dt_cb / (2 * tau_ac))
                       * np.cos(wslip * t + phi_a))

    # Smooth Heaviside blend
    H  = _heaviside_smooth(t, t_sw)
    ia = (1.0 - H) * i_pre + H * i_post
    return ia


def dfig_three_phase(t: np.ndarray, theta: dict, f0: float = 50.0) -> dict:
    """
    Compute three-phase DFIG fault current.

    Returns dict with keys 'ia', 'ib', 'ic'.
    Phases B and C are 120° displaced but share identical amplitude envelope
    (balanced fault assumption).
    """
    ia = dfig_phase_A(t, theta, f0)

    # B and C: shift phi_a by ∓120°
    theta_b = {**theta, "phi_a": float(theta["phi_a"]) - 2.0 * np.pi / 3.0,
               "phi_cc": float(theta["phi_cc"]) - 2.0 * np.pi / 3.0}
    theta_c = {**theta, "phi_a": float(theta["phi_a"]) + 2.0 * np.pi / 3.0,
               "phi_cc": float(theta["phi_cc"]) + 2.0 * np.pi / 3.0}
    ib = dfig_phase_A(t, theta_b, f0)
    ic = dfig_phase_A(t, theta_c, f0)
    return {"ia": ia, "ib": ib, "ic": ic}


# ---------------------------------------------------------------------------
# CUSUM crowbar detector
# ---------------------------------------------------------------------------

def detect_crowbar_cusum(
    t: np.ndarray,
    i_diff: np.ndarray,
    t_fault: float,
    pre_cycles: float = 1.5,
    delta_sigma: float = 1.5,
    h: float = 5.0,
    f0: float = 50.0,
) -> Optional[float]:
    """
    CUSUM-based crowbar activation detector.

    Monitors the magnitude of the differential current after fault inception.
    The crowbar fires when the CUSUM statistic exceeds threshold h.

    Parameters
    ----------
    t        : time vector
    i_diff   : magnitude of differential current |i_diff(t)|  [pu]
    t_fault  : fault inception time [s] (from event detector)
    pre_cycles: number of pre-fault cycles used for baseline statistics
    delta_sigma: reference level offset (half of detectable change) in σ units
    h        : decision threshold for CUSUM alarm
    f0       : system frequency [Hz]

    Returns
    -------
    t_crowbar : float — time of crowbar activation [s], or None if not detected
    """
    T0 = 1.0 / f0
    t_pre_start = t_fault - pre_cycles * T0
    pre_mask    = (t >= t_pre_start) & (t < t_fault)

    if pre_mask.sum() < 10:
        return None   # insufficient pre-fault data

    baseline    = i_diff[pre_mask]
    mu_pre      = float(baseline.mean())
    sigma_pre   = float(baseline.std())
    if sigma_pre < 1e-6:
        sigma_pre = 1e-6

    # CUSUM over post-fault window
    post_mask = t >= t_fault
    t_post    = t[post_mask]
    x_post    = i_diff[post_mask]

    S = 0.0
    for k, x_k in enumerate(x_post):
        increment = (x_k - mu_pre - delta_sigma * sigma_pre) / sigma_pre
        S = max(0.0, S + increment)
        if S > h:
            return float(t_post[k])

    return None   # crowbar not detected in window


# ---------------------------------------------------------------------------
# Parameter vector conversion
# ---------------------------------------------------------------------------

def theta_dfig_to_vector(theta: dict) -> np.ndarray:
    return np.array([float(theta[k]) for k in THETA_KEYS_DFIG])


def vector_to_theta_dfig(v: np.ndarray) -> dict:
    return {k: float(v[i]) for i, k in enumerate(THETA_KEYS_DFIG)}


# ---------------------------------------------------------------------------
# Residual function for LM estimator
# ---------------------------------------------------------------------------

def dfig_residual(v: np.ndarray, t: np.ndarray, ia_meas: np.ndarray,
                  f0: float = 50.0) -> np.ndarray:
    """
    Residual vector for LM optimisation: r = ia_model(v) − ia_meas.
    """
    theta = vector_to_theta_dfig(v)
    ia_model = dfig_phase_A(t, theta, f0)
    return ia_model - ia_meas


# ---------------------------------------------------------------------------
# 87L differential current construction
# ---------------------------------------------------------------------------

def build_87L_diff_current(
    t: np.ndarray,
    i_L: np.ndarray,
    i_R: np.ndarray,
    fault_type: str = "internal",
    alpha: float = 1.0,
) -> dict:
    """
    Construct 87L operate (differential) and restraint currents.

    For an ideal two-terminal 87L relay:
        i_diff = |i_L + i_R|            (operate current)
        i_rst  = 0.5 × (|i_L| + |i_R|) (restraint current)

    Parameters
    ----------
    t          : time vector
    i_L        : complex positive-sequence current at local (DFIG) terminal
    i_R        : complex positive-sequence current at remote terminal
    fault_type : "external" | "internal" (informational, not used in calc)
    alpha      : current differential factor (1.0 = ideal CTs)

    Returns
    -------
    dict with keys: i_diff_mag, i_rst, i_L_mag, i_R_mag, fault_type
    """
    i_diff_cplx = i_L + alpha * i_R
    i_diff_mag  = np.abs(i_diff_cplx)
    i_rst       = 0.5 * (np.abs(i_L) + np.abs(i_R))
    return {
        "i_diff_mag": i_diff_mag,
        "i_rst":      i_rst,
        "i_L_mag":    np.abs(i_L),
        "i_R_mag":    np.abs(i_R),
        "fault_type": fault_type,
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    f0   = 50.0
    t    = np.linspace(0.0, 0.4, 4000)
    theta = {**DEFAULT_THETA_DFIG, "t0": 0.05, "t_cb": 0.03, "k_slip": 0.04}

    out = dfig_three_phase(t, theta, f0)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t * 1e3, out["ia"], label="ia", lw=0.9)
    ax.plot(t * 1e3, out["ib"], label="ib", lw=0.9, alpha=0.7)
    ax.plot(t * 1e3, out["ic"], label="ic", lw=0.9, alpha=0.7)
    ax.axvline((theta["t0"] + theta["t_cb"]) * 1e3, color="r", ls="--",
               label=f"Crowbar t={theta['t0']+theta['t_cb']:.3f}s")
    ax.set_xlabel("Time (ms)"); ax.set_ylabel("Current (pu)")
    ax.set_title("TR-56: DFIG piecewise-ODE fault current (10-param)")
    ax.legend(); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("dfig_model_test.png", dpi=120)
    print("Saved dfig_model_test.png")
