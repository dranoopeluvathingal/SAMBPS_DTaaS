"""Phase-locked RLS unit tests."""

import math
import numpy as np

from fs_mpc_mg import Plant, PlantParams
from fs_mpc_mg.dt.parameter_id_pl import PhaseLockedRLS, PhaseLockedRLSParams


def test_phase_locked_rls_converges_on_known_plant():
    """Drive PL-RLS with synthetic data from a known plant; estimates should converge after a few cycles."""
    L_true, r_true = 1e-3, 50e-3
    p = Plant(PlantParams(L=L_true, r=r_true))
    T_s = 20e-6
    f = 50.0
    samples_per_cycle = int(round(1.0 / (f * T_s)))
    rls = PhaseLockedRLS(PhaseLockedRLSParams(
        T_s=T_s, f_grid=f, samples_per_cycle=samples_per_cycle, min_cycles=4,
        init_L=2e-3, init_r=200e-3,
    ))
    s = np.array([1.0, 0.0, 0.0])
    n_cycles = 20
    for k in range(samples_per_cycle * n_cycles):
        v_s = 310.0 * np.array([
            math.sin(2 * math.pi * f * k * T_s),
            math.sin(2 * math.pi * f * k * T_s - 2 * math.pi / 3),
            math.sin(2 * math.pi * f * k * T_s + 2 * math.pi / 3),
        ])
        i_m_now = p.i_m.copy()
        v_dc_now = p.v_dc
        p.step(s, v_s, i_dc=0.0, dt=T_s)
        rls.push(i_m_now=i_m_now, v_s_now=v_s, s_now=s,
                 v_dc_now=v_dc_now, i_m_next=p.i_m)
    res = rls.estimate
    assert rls.n_cycles >= n_cycles - 1
    # Cycle averaging removes the fast switching transients; estimate should
    # be in the right ballpark (within 50% — coarser than per-sample RLS but
    # robust to the kind of switching noise the regular RLS struggles with).
    assert 0.0001 < res.L < 0.01


def test_phase_locked_rls_n_cycles_count():
    rls = PhaseLockedRLS(PhaseLockedRLSParams(samples_per_cycle=10, min_cycles=2))
    for _ in range(35):  # 3 full cycles + 5 leftover
        rls.push(
            i_m_now=np.zeros(3), v_s_now=np.zeros(3),
            s_now=np.zeros(3), v_dc_now=900.0, i_m_next=np.zeros(3),
        )
    assert rls.n_cycles == 3
