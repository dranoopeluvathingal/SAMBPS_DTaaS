"""PLL unit tests (IdealPLL + SOGIPLL)."""

import math
import numpy as np
import pytest

from fs_mpc_mg.pll import IdealPLL, SOGIPLL, SOGIPLLParams


def _three_phase_sin(t, V=310.0, f=50.0, distortion=None):
    theta = 2 * math.pi * f * t
    fund = V * np.array([
        math.sin(theta),
        math.sin(theta - 2 * math.pi / 3),
        math.sin(theta + 2 * math.pi / 3),
    ])
    if distortion is None:
        return fund
    extra = np.zeros(3)
    for h, amp in distortion.items():
        extra += V * amp * np.array([
            math.sin(h * theta),
            math.sin(h * theta - 2 * math.pi / 3),
            math.sin(h * theta + 2 * math.pi / 3),
        ])
    return fund + extra


def test_ideal_pll_returns_correct_unit_vector():
    pll = IdealPLL(f_grid=50.0)
    theta, omega, unit = pll.update(t=0.005)        # quarter cycle
    assert omega == pytest.approx(2 * math.pi * 50.0)
    assert theta == pytest.approx(2 * math.pi * 50.0 * 0.005)
    assert unit.shape == (3,)


# -----------------------------------------------------------------
# SOGI-PLL
# -----------------------------------------------------------------

def test_sogi_pll_locks_on_clean_sine():
    """After ~5 cycles (100 ms) the PLL should be within 0.5% of nominal omega."""
    T_s = 50e-6
    pll = SOGIPLL(SOGIPLLParams(T_s=T_s, omega_n=100.0))
    t_end = 0.2  # 10 cycles
    N = int(t_end / T_s)
    for k in range(N):
        t = k * T_s
        v_s = _three_phase_sin(t)
        pll.update(t, v_s_abc=v_s)
    omega_err = abs(pll.omega - 2 * math.pi * 50.0) / (2 * math.pi * 50.0)
    assert omega_err < 5e-3, f"omega error {omega_err*100:.2f}% too large"
    assert pll.locked


def test_sogi_pll_phase_alignment_after_lock():
    """θ_pll should align with the grid θ within a few degrees after lock."""
    T_s = 50e-6
    pll = SOGIPLL(SOGIPLLParams(T_s=T_s, omega_n=100.0))
    t_end = 0.4   # 20 cycles for tight lock
    N = int(t_end / T_s)
    for k in range(N):
        t = k * T_s
        pll.update(t, v_s_abc=_three_phase_sin(t))
    # θ_pll mod 2π should match (omega * t) mod 2π
    expected = (2 * math.pi * 50.0 * (N - 1) * T_s) % (2 * math.pi)
    err = abs(pll.theta - expected)
    err = min(err, 2 * math.pi - err)
    assert err < math.radians(5.0), f"phase error {math.degrees(err):.2f}° too large"


def test_sogi_pll_rejects_5pct_harmonic():
    """5th- and 7th-order harmonic at 5% should not destabilise lock."""
    T_s = 50e-6
    pll = SOGIPLL(SOGIPLLParams(T_s=T_s, omega_n=100.0))
    t_end = 0.4
    N = int(t_end / T_s)
    for k in range(N):
        t = k * T_s
        v_s = _three_phase_sin(t, distortion={5: 0.05, 7: 0.05})
        pll.update(t, v_s_abc=v_s)
    omega_err = abs(pll.omega - 2 * math.pi * 50.0) / (2 * math.pi * 50.0)
    assert omega_err < 1e-2, f"omega ripple {omega_err*100:.2f}% too large"


def test_sogi_pll_query_without_v_s_returns_unit_at_t():
    """update(t) without v_s_abc should just query the locked state."""
    T_s = 50e-6
    pll = SOGIPLL(SOGIPLLParams(T_s=T_s))
    # Lock first
    for k in range(8000):
        t = k * T_s
        pll.update(t, v_s_abc=_three_phase_sin(t))
    last_t = (8000 - 1) * T_s
    # Query the unit vector at t = last_t + Δ
    delta = 1e-3
    _, _, unit_pred = pll.update(last_t + delta)
    expected_theta = pll.theta + pll.omega * delta
    expected_unit = np.array([
        math.sin(expected_theta),
        math.sin(expected_theta - 2 * math.pi / 3),
        math.sin(expected_theta + 2 * math.pi / 3),
    ])
    np.testing.assert_allclose(unit_pred, expected_unit, atol=1e-6)
