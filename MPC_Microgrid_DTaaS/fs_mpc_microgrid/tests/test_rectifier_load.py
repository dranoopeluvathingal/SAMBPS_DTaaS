"""6-pulse rectifier load tests."""

import math
import numpy as np

from fs_mpc_mg.rectifier_load import RectifierLoad, RectifierLoadParams


def test_phase_a_pulse_pattern():
    """+1 in (30°, 150°), -1 in (210°, 330°), 0 elsewhere — direct check on the shaper."""
    rect = RectifierLoad(RectifierLoadParams(edge_softening_rad=0.0))
    cases = {0: 0.0, 60: 1.0, 90: 1.0, 120: 1.0, 180: 0.0,
             240: -1.0, 270: -1.0, 320: -1.0}
    for deg, expected in cases.items():
        got = rect._phase_a_pulse(math.radians(deg))
        assert got == expected, f"deg={deg} got={got} expected={expected}"


def test_dc_current_smoothing_responds_to_demand_step():
    rect = RectifierLoad(RectifierLoadParams(P_dc_demand=10e3, smoothing_tau_s=1e-3))
    for _ in range(500):
        rect.i_l(t=0.0, dt=1e-5)
    # V_d_avg ≈ 1.654 * 310 ≈ 513 V; I_d ≈ 19.5 A
    assert 18.0 < rect.I_d < 21.0
    rect.update_demand(30e3)
    for _ in range(2000):
        rect.i_l(t=0.0, dt=1e-5)
    assert 55.0 < rect.I_d < 62.0


def test_thd_of_phase_a_current_close_to_textbook():
    """6-pulse rectifier with infinite DC inductance has THD ≈ 31% (textbook)."""
    rect = RectifierLoad(RectifierLoadParams(P_dc_demand=20e3, smoothing_tau_s=10.0,
                                              edge_softening_rad=0.0))
    for _ in range(2000):
        rect.i_l(t=0.0, dt=1e-5)
    f = 50.0
    fs = 50_000
    N = int(5 * fs / f)
    sig = np.array([rect.i_l(k / fs, dt=1e-5)[0] for k in range(N)])
    sig -= sig.mean()
    spec = np.abs(np.fft.rfft(sig))
    fund = spec[int(round(f * N / fs))]
    harm_sq = sum(spec[int(round(h * f * N / fs))] ** 2 for h in range(2, 50)
                  if int(round(h * f * N / fs)) < len(spec))
    thd = math.sqrt(harm_sq) / max(fund, 1e-9)
    assert 0.20 < thd < 0.40, f"THD={thd*100:.1f}% off"


def test_v_s_is_balanced_three_phase_sinusoid():
    rect = RectifierLoad()
    v = rect.v_s(t=0.005)
    assert v.shape == (3,)
    assert abs(v.sum()) < 1.0
