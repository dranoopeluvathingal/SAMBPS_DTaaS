"""
line_reduced_zone_model.py
===========================
Reduced-parameter zone model for the SAMBP 87L line differential relay.

Physical model
--------------
For a faulted transmission line the differential current has two identifiable
structural components that span orthogonal function spaces:

    i_diff(t) = I_fund × sin(ωt + φ_fund)    [power-frequency sinusoid]
              + I_DC × exp(−t / τ_DC)          [DC offset from fault inception]

The two components are distinguishable because:
    • The sinusoidal component is identified via DFT / least-squares
    • The DC component decays with τ_DC ∈ [0.01, 0.5] s (inductive line)

The 4-parameter model θ_L:
    θ_L = [I_fund,    — fundamental differential amplitude [pu]
            phi_fund,  — phase angle [rad]
            I_DC,      — DC offset amplitude [pu]
            tau_DC]    — DC time constant [s]

Internal fault classification (derived, not fitted)
-----------------------------------------------------
    is_internal = (I_fund > I_fund_fault_thresh)
                  OR (I_DC > I_DC_thresh)

    Healthy line:    I_fund ≈ I_C_peak (charging)  +  small sync residual
                     I_DC ≈ 0
    Sync error only: I_fund somewhat elevated, I_DC ≈ 0
    Internal fault:  I_fund >> I_C_peak  AND/OR  I_DC > I_DC_thresh

    f_int = clip(max(I_fund / I_fund_fault_thresh,
                     I_DC   / I_DC_thresh) − 1, 0, 1) / (max_factor − 1)

Parameter bounds
----------------
    I_fund   : [0,   10.0]  pu
    phi_fund : [−π,  +π]   rad
    I_DC     : [0,    5.0]  pu
    tau_DC   : [0.005, 0.5] s
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass

PARAM_NAMES = ["I_fund", "phi_fund", "I_DC", "tau_DC"]
N_PARAMS    = len(PARAM_NAMES)

LOWER_BOUNDS = np.array([0.0,  -np.pi, 0.0,  0.005])
UPPER_BOUNDS = np.array([10.0,  np.pi, 5.0,  0.500])


# ---------------------------------------------------------------------------
# Forward model
# ---------------------------------------------------------------------------

def forward_idiff(
    t: np.ndarray,
    theta: np.ndarray,
    freq_hz: float = 50.0,
) -> np.ndarray:
    """
    Evaluate the 4-parameter line differential current model.

    Parameters
    ----------
    t     : (N,) time array [s]  (relative to window start, i.e. t[0] ≈ 0)
    theta : (4,) parameter vector [I_fund, phi_fund, I_DC, tau_DC]
    freq_hz : float

    Returns
    -------
    (N,) differential current [pu]
    """
    I_f  = float(theta[0])
    phi  = float(theta[1])
    I_dc = float(theta[2])
    tau  = max(float(theta[3]), 1e-4)
    omega = 2.0 * np.pi * freq_hz

    t0 = t - t[0]   # reset to zero for DC exponential
    return I_f * np.sin(omega * t + phi) + I_dc * np.exp(-t0 / tau)


# ---------------------------------------------------------------------------
# Jacobian
# ---------------------------------------------------------------------------

def jacobian_idiff(
    t: np.ndarray,
    theta: np.ndarray,
    freq_hz: float = 50.0,
) -> np.ndarray:
    """Analytical Jacobian ∂i_diff/∂θ — shape (N, 4)."""
    I_f  = float(theta[0])
    phi  = float(theta[1])
    I_dc = float(theta[2])
    tau  = max(float(theta[3]), 1e-4)
    omega = 2.0 * np.pi * freq_hz
    t0   = t - t[0]

    sin_t = np.sin(omega * t + phi)
    cos_t = np.cos(omega * t + phi)
    exp_t = np.exp(-t0 / tau)

    dI_f   = sin_t
    dphi   = I_f * cos_t
    dI_dc  = exp_t
    dtau   = I_dc * (t0 / tau**2) * exp_t   # ∂/∂τ [I_dc * exp(-t/τ)] = I_dc*t/τ² * exp(...)

    return np.column_stack([dI_f, dphi, dI_dc, dtau])


# ---------------------------------------------------------------------------
# Condition number
# ---------------------------------------------------------------------------

def condition_number_normalised(J: np.ndarray) -> float:
    col_norms = np.linalg.norm(J, axis=0)
    col_norms = np.where(col_norms < 1e-12, 1.0, col_norms)
    J_n = J / col_norms[np.newaxis, :]
    sv  = np.linalg.svd(J_n, compute_uv=False)
    if sv[-1] < 1e-14:
        return float("inf")
    return float(sv[0] / sv[-1])


# ---------------------------------------------------------------------------
# Residual vector
# ---------------------------------------------------------------------------

def residual_vector(
    theta: np.ndarray,
    t: np.ndarray,
    i_diff_meas: np.ndarray,
    freq_hz: float = 50.0,
) -> np.ndarray:
    return i_diff_meas - forward_idiff(t, theta, freq_hz)


# ---------------------------------------------------------------------------
# Initial guess
# ---------------------------------------------------------------------------

def initial_guess(
    t: np.ndarray,
    i_diff_meas: np.ndarray,
    freq_hz: float = 50.0,
    I_C_nom: float = 0.02,
) -> np.ndarray:
    """Physics-informed initial guess for θ_L."""
    N   = len(t)
    dt  = float(t[1] - t[0])
    fs  = 1.0 / dt

    F     = np.fft.rfft(i_diff_meas)
    F_mag = np.abs(F) * 2.0 / N
    idx1  = int(round(freq_hz / (fs / N)))
    idx1  = np.clip(idx1, 0, len(F_mag) - 1)

    I_fund = max(float(F_mag[idx1]), I_C_nom)
    phi    = float(np.angle(F[idx1]))

    # DC estimate: mean of residual after subtracting fundamental sine
    sin_ref = I_fund * np.sin(2*np.pi*freq_hz*t + phi)
    residual = i_diff_meas - sin_ref
    I_DC  = max(0.0, float(np.mean(residual[:max(N//4, 1)])))

    return np.array([I_fund, phi, I_DC, 0.05])


# ---------------------------------------------------------------------------
# Derived indicators
# ---------------------------------------------------------------------------

def compute_f_int(
    I_fund: float,
    I_DC: float,
    I_fund_fault_thresh: float = 0.20,
    I_DC_thresh: float         = 0.10,
    max_factor: float          = 5.0,
) -> float:
    """
    Internal fault fraction [0, 1].

    Combines both indicators:
        raw = max(I_fund / I_fund_fault_thresh, I_DC / I_DC_thresh)
        f_int = clip((raw − 1) / (max_factor − 1), 0, 1)

    Below threshold → f_int = 0; at max_factor × threshold → f_int = 1.
    """
    raw = max(
        float(I_fund) / max(I_fund_fault_thresh, 1e-9),
        float(I_DC)   / max(I_DC_thresh, 1e-9),
    )
    return float(np.clip((raw - 1.0) / max(max_factor - 1.0, 1.0), 0.0, 1.0))


# ---------------------------------------------------------------------------
# Parameter interpretation
# ---------------------------------------------------------------------------

@dataclass
class LineZoneState:
    I_fund: float
    phi_fund: float
    I_DC: float
    tau_DC: float
    f_int: float
    kappa_n: float       = float("inf")
    residual_norm: float = float("inf")
    confidence: float    = 0.0
    is_internal: bool    = False
    is_sync_error: bool  = False    # I_fund in "elevated but not fault" range
    I_eps: float         = 0.0      # proxy for sync error magnitude


def interpret_theta(
    theta: np.ndarray,
    kappa_n: float,
    residual_norm: float,
    I_fund_fault_thresh: float = 0.20,
    I_DC_thresh: float         = 0.10,
    I_sync_thresh: float       = 0.05,   # above charging but below fault threshold
    f_int_thresh: float        = 0.40,
    kappa_max: float           = 80.0,
) -> LineZoneState:
    I_f, phi, I_dc, tau = (float(x) for x in theta)
    f_int = compute_f_int(I_f, I_dc, I_fund_fault_thresh, I_DC_thresh)

    kn_conf   = float(np.clip(1.0 - (kappa_n - 1.0) / max(kappa_max - 1.0, 1.0),
                              0.0, 1.0))
    res_conf  = float(np.exp(-residual_norm))
    confidence = kn_conf * res_conf

    # Sync error: I_fund elevated but below fault threshold
    I_eps_proxy = float(np.clip(I_f - 0.03, 0.0, I_fund_fault_thresh))
    is_sync = (I_f > I_sync_thresh) and (I_f < I_fund_fault_thresh)

    return LineZoneState(
        I_fund       = I_f,
        phi_fund     = phi,
        I_DC         = I_dc,
        tau_DC       = tau,
        f_int        = f_int,
        kappa_n      = kappa_n,
        residual_norm = residual_norm,
        confidence   = confidence,
        is_internal  = f_int >= f_int_thresh,
        is_sync_error = is_sync,
        I_eps        = I_eps_proxy,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    freq = 50.0
    fs   = 1000.0
    t    = np.arange(0, 0.1, 1.0 / fs)

    # Test A: healthy (charging only, no DC)
    theta_h = np.array([0.022, 1.57, 0.0, 0.05])
    J_h = jacobian_idiff(t, theta_h, freq)
    kn_h = condition_number_normalised(J_h)
    st_h = interpret_theta(theta_h, kn_h, 0.01)
    print(f"Healthy: κ_n={kn_h:.2f}  f_int={st_h.f_int:.3f}  "
          f"is_internal={st_h.is_internal}  is_sync={st_h.is_sync_error}")
    assert not st_h.is_internal, "Healthy should NOT flag internal"

    # Test B: internal fault (large fundamental + DC offset)
    theta_f = np.array([3.5, -0.2, 1.2, 0.05])
    J_f = jacobian_idiff(t, theta_f, freq)
    kn_f = condition_number_normalised(J_f)
    st_f = interpret_theta(theta_f, kn_f, 0.02)
    print(f"Fault:   κ_n={kn_f:.2f}  f_int={st_f.f_int:.3f}  "
          f"is_internal={st_f.is_internal}")
    assert st_f.is_internal, "Fault should flag internal"

    # Test C: sync error (I_fund mildly elevated, no DC)
    theta_s = np.array([0.10, 0.4, 0.0, 0.05])
    st_s = interpret_theta(theta_s, kappa_n=12.0, residual_norm=0.02)
    print(f"Sync:    f_int={st_s.f_int:.3f}  is_sync={st_s.is_sync_error}  "
          f"is_internal={st_s.is_internal}")
    assert st_s.is_sync_error,   "Sync error scenario should flag sync_error"
    assert not st_s.is_internal, "Sync error alone should NOT flag internal fault"

    x0 = initial_guess(t, forward_idiff(t, theta_f, freq) + 0.005, freq)
    print(f"Initial guess: {dict(zip(PARAM_NAMES, np.round(x0, 3)))}")
    print("line_reduced_zone_model self-test PASSED.")
