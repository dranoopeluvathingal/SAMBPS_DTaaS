"""
bus_reduced_zone_model.py
==========================
Reduced-parameter zone model for the 87B bus differential relay.

Model motivation
----------------
For an ideal bus (perfect CTs, no saturation), the differential current
during an internal fault is:

    i_diff(t) = I_f · sin(ωt + φ)

During an external fault with CT saturation, the saturated CT output is
compressed above the knee current, producing a waveform of the form:

    i_diff_sat(t) ≈ ε_CT · I_ref · sgn(sin(ωt))   [odd-harmonic residual]

so the full model is:

    i_diff(t) = I_diff_fund · sin(ωt + φ)
              + ε_CT · I_diff_fund · sgn(sin(ωt))     (3)

Three-parameter model:  θ_B = [I_diff_fund, φ_diff, ε_CT]
Bounds:
    I_diff_fund ∈ [0,   10.0] pu
    φ_diff      ∈ [−π,     π] rad
    ε_CT        ∈ [0,    0.5] pu

Identifiability
---------------
sin(ωt) and sgn(sin(ωt)) are linearly independent (orthogonal to each
other and to cos(ωt)).  The Jacobian has rank 3 for all parameter values,
giving κ_n ≈ 2–6 (well below the 30-threshold).

Internal-fault indicator (derived, not fitted)
----------------------------------------------
    f_int = clip(1 − ε_CT / CT_thresh, 0, 1)

When ε_CT ≈ 0 (clean differential, no CT distortion) → f_int ≈ 1.0 (internal).
When ε_CT ≥ CT_thresh (significant saturation) → f_int ≈ 0 (not internal).
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass

# Parameter index aliases
_IDX_I     = 0
_IDX_PHI   = 1
_IDX_EPS   = 2

PARAM_NAMES  = ["I_diff_fund", "phi_diff", "epsilon_CT"]
LOWER_BOUNDS = np.array([0.0,  -np.pi, 0.0 ])
UPPER_BOUNDS = np.array([10.0,  np.pi, 0.5 ])

# Thresholds for f_int derivation
_CT_THRESH = 0.10   # ε_CT above which saturation is significant


# ---------------------------------------------------------------------------
# Forward model
# ---------------------------------------------------------------------------

def forward_idiff(
    t: np.ndarray,
    theta: np.ndarray,
    freq_hz: float = 50.0,
) -> np.ndarray:
    """
    Evaluate the forward model at times t.

    i_diff(t) = I_f · sin(ωt + φ) + ε_CT · I_f · sgn(sin(ωt))
    """
    I_f   = float(theta[_IDX_I  ])
    phi   = float(theta[_IDX_PHI])
    eps   = float(theta[_IDX_EPS])
    omega = 2.0 * np.pi * freq_hz

    sinwt = np.sin(omega * t)
    return (I_f * np.sin(omega * t + phi)
            + eps * I_f * np.sign(sinwt))


# ---------------------------------------------------------------------------
# Analytical Jacobian  ∂i_diff / ∂θ_j
# ---------------------------------------------------------------------------

def jacobian_idiff(
    t: np.ndarray,
    theta: np.ndarray,
    freq_hz: float = 50.0,
) -> np.ndarray:
    """
    Return Jacobian J ∈ ℝ^{N×3}.

    J[:,0] = ∂/∂I_f   =  sin(ωt+φ) + ε_CT·sgn(sin(ωt))
    J[:,1] = ∂/∂φ      =  I_f·cos(ωt+φ)
    J[:,2] = ∂/∂ε_CT   =  I_f·sgn(sin(ωt))
    """
    I_f   = float(theta[_IDX_I  ])
    phi   = float(theta[_IDX_PHI])
    eps   = float(theta[_IDX_EPS])
    omega = 2.0 * np.pi * freq_hz

    sinwt   = np.sin(omega * t)
    sinwt_p = np.sin(omega * t + phi)
    coswt_p = np.cos(omega * t + phi)
    sgn_sin = np.sign(sinwt)

    J = np.column_stack([
        sinwt_p + eps * sgn_sin,   # ∂/∂I_f
        I_f * coswt_p,             # ∂/∂φ
        I_f * sgn_sin,             # ∂/∂ε_CT
    ])
    return J   # (N, 3)


# ---------------------------------------------------------------------------
# Column-normalised condition number (same as other SAMBP modules)
# ---------------------------------------------------------------------------

def condition_number_normalised(J: np.ndarray) -> float:
    norms = np.linalg.norm(J, axis=0)
    norms = np.where(norms < 1e-12, 1.0, norms)
    Jn    = J / norms
    sv    = np.linalg.svd(Jn, compute_uv=False)
    return float(sv[0] / sv[-1]) if sv[-1] > 1e-12 else float("inf")


# ---------------------------------------------------------------------------
# f_int derivation
# ---------------------------------------------------------------------------

def compute_f_int(
    epsilon_CT: float,
    CT_thresh: float = _CT_THRESH,
) -> float:
    """
    Derive internal-fault indicator from blocking signature.

        f_int = clip(1 − ε_CT / CT_thresh, 0, 1)

    When ε_CT ≈ 0 → f_int ≈ 1  (clean differential → internal fault likely)
    When ε_CT ≥ CT_thresh → f_int = 0  (CT saturation → not internal)
    """
    blocking = np.clip(float(epsilon_CT) / max(CT_thresh, 1e-9), 0.0, 1.0)
    return float(np.clip(1.0 - blocking, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Zone model state
# ---------------------------------------------------------------------------

@dataclass
class BusZoneModelState:
    theta: np.ndarray         # (3,) estimated parameter vector
    I_diff_fund: float        # [pu]
    phi_diff: float           # [rad]
    epsilon_CT: float         # CT mismatch/saturation factor
    f_int: float              # derived internal-fault indicator ∈ [0,1]
    is_ct_saturated: bool     # ε_CT ≥ CT_thresh
    is_internal_fault: bool   # f_int ≥ f_int_thresh AND NOT ct_saturated
    kappa_n: float            # column-normalised condition number
    residual_norm: float      # normalised residual ‖r‖/‖i_diff‖
    confidence: float         # composite score ∈ [0,1]


def interpret_theta(
    theta: np.ndarray,
    kappa_n: float,
    residual_norm: float,
    CT_thresh: float   = _CT_THRESH,
    f_int_thresh: float = 0.60,
) -> BusZoneModelState:
    """Convert raw θ_B into a BusZoneModelState with human-readable flags."""
    I_f  = float(theta[_IDX_I  ])
    phi  = float(theta[_IDX_PHI])
    eps  = float(theta[_IDX_EPS])

    f_int = compute_f_int(eps, CT_thresh)

    # Composite confidence: decay with κ_n and residual_norm
    conf_kn  = np.exp(-0.05 * max(0.0, kappa_n  - 1.0))
    conf_rn  = np.exp(-5.0  * max(0.0, residual_norm))
    confidence = float(conf_kn * conf_rn)

    return BusZoneModelState(
        theta             = theta,
        I_diff_fund       = I_f,
        phi_diff          = phi,
        epsilon_CT        = eps,
        f_int             = f_int,
        is_ct_saturated   = eps >= CT_thresh,
        is_internal_fault = (f_int >= f_int_thresh) and (eps < CT_thresh),
        kappa_n           = kappa_n,
        residual_norm     = residual_norm,
        confidence        = confidence,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Check κ_n for clean internal fault (ε_CT≈0) and CT saturation (ε_CT large)
    t = np.linspace(0, 0.04, 40)

    for label, theta_test in [
        ("Internal fault (ε_CT=0.00)", np.array([3.0,  0.1, 0.00])),
        ("CT saturation  (ε_CT=0.30)", np.array([1.5,  0.1, 0.30])),
        ("Low amplitude  (ε_CT=0.05)", np.array([0.15, 0.2, 0.05])),
    ]:
        J   = jacobian_idiff(t, theta_test)
        kn  = condition_number_normalised(J)
        zs  = interpret_theta(theta_test, kappa_n=kn, residual_norm=0.02)
        print(f"  {label}: κ_n={kn:.2f}  f_int={zs.f_int:.3f}  "
              f"is_internal={zs.is_internal_fault}  is_ct_sat={zs.is_ct_saturated}")
        assert kn < 30.0, f"κ_n={kn:.2f} exceeds threshold for {label}"

    # Check f_int monotonicity
    for eps in [0.0, 0.05, 0.10, 0.20, 0.50]:
        fi = compute_f_int(eps)
        print(f"  ε_CT={eps:.2f}  →  f_int={fi:.3f}")

    assert compute_f_int(0.0)   == 1.0, "ε_CT=0 must give f_int=1"
    assert compute_f_int(0.10)  == 0.0, "ε_CT=CT_thresh must give f_int=0"
    assert compute_f_int(0.50)  == 0.0, "ε_CT>CT_thresh must give f_int=0"

    print("\nbus_reduced_zone_model self-test PASSED.")
