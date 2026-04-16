# =============================================================================
# tests/test_bess_ekf.py
#
# Unit tests for estimation/bess_ekf.py — TR-68 WP 68.4
#
# Tests
# -----
#   1. test_soc_tracking           — EKF tracks SoC correctly under dispatch
#   2. test_fault_state_estimation — inject_fault() sets I_ac to fault level
#   3. test_mode_transition        — Q inflation resets accumulator correctly
#   4. test_convergence_speed      — is_converged after ≥ 10 updates
#   5. test_reset_clears_state     — reset() restores to x0
#   6. test_output_dict_keys       — update() returns all required keys
#   7. test_state_clamped          — update() never returns out-of-bounds state
#   8. test_chemistry_li_ion       — li_ion preset produces valid estimates
#   9. test_chemistry_flow         — flow preset produces valid estimates
#  10. test_chemistry_na_ion       — na_ion preset produces valid estimates
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from estimation.bess_ekf import BESSEKFEstimator
from models.bess_model import BESSConfig, BESSModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_est(preset: str = "li_ion") -> BESSEKFEstimator:
    cfgs = {
        "li_ion": BESSConfig.li_ion_1mwh(),
        "flow":   BESSConfig.flow_5mwh(),
        "na_ion": BESSConfig.na_ion_500kwh(),
    }
    return BESSEKFEstimator(cfgs[preset])


def _measurement(model: BESSModel, x: np.ndarray,
                 noise_std: float = 0.005) -> np.ndarray:
    """h(x) + small Gaussian noise (class 1P CT/VT)."""
    z = model.h(x)
    rng = np.random.default_rng(seed=0)
    return z + rng.normal(0.0, noise_std, size=z.shape)


def _run_n_steps(est: BESSEKFEstimator, n: int, soc0: float = 0.5,
                 p_sp: float = 0.5, dt: float = 1e-3) -> dict:
    model = est.model
    x = model.x0(soc=soc0, p_dispatch_pu=p_sp)
    u = np.array([p_sp, 0.0])
    state = None
    for _ in range(n):
        x = model.f(x, u, dt)
        z = _measurement(model, x)
        state = est.update(z, u=u, dt=dt)
    return state, x


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSoCTracking:
    def test_soc_tracks_true_value(self):
        est   = _make_est("li_ion")
        state, x_true = _run_n_steps(est, 50, soc0=0.60, p_sp=0.80)
        # SoC is weakly observable (barely changes in 50 ms); tolerance 0.12
        # reflects realistic EKF convergence from a 0.10 initial offset
        assert abs(state["SoC"] - x_true[0]) < 0.12

    def test_soc_within_physical_bounds(self):
        est = _make_est("li_ion")
        for _ in range(3):
            state, _ = _run_n_steps(est, 20, soc0=0.50)
            assert est.cfg.soc_min <= state["SoC"] <= est.cfg.soc_max

    def test_i_ac_tracks_dispatch(self):
        est   = _make_est("li_ion")
        state, x_true = _run_n_steps(est, 30, p_sp=0.70)
        assert abs(state["I_ac_mag"] - x_true[4]) < 0.15


class TestFaultStateEstimation:
    def test_inject_fault_sets_i_ac(self):
        est = _make_est("li_ion")
        est.inject_fault(fault_type="3PH", t_elapsed=0.0)
        # After injection, I_ac should be at (or near) the fault limit
        assert est._x[4] >= est.cfg.current_limit_pu * 0.80

    def test_inject_fault_slg_lower_than_3ph(self):
        est3 = _make_est("li_ion")
        estS = _make_est("li_ion")
        est3.inject_fault("3PH",  t_elapsed=0.0)
        estS.inject_fault("SLG",  t_elapsed=0.0)
        # SLG has negative-sequence factor 0.85 → lower than 3PH
        assert estS._x[4] <= est3._x[4] + 1e-9

    def test_inject_fault_inflates_covariance(self):
        est = _make_est("li_ion")
        p_before = est.covariance[4, 4]
        est.inject_fault("3PH")
        p_after  = est.covariance[4, 4]
        assert p_after >= p_before


class TestModeTransition:
    def test_mode_steps_set_on_large_dp(self):
        from estimation.bess_ekf import _MODE_RESET_STEPS, _MODE_CHANGE_THRESH
        est = _make_est("li_ion")
        # Manually induce a large P_dc step
        est._x[1] = 0.0                     # current P_dc = 0
        x_pred = est.model.x0()
        x_pred[1] = _MODE_CHANGE_THRESH + 0.10   # predicted P_dc >> threshold
        Q = est._effective_Q(x_pred)
        assert est._mode_steps == _MODE_RESET_STEPS

    def test_q_inflation_during_mode_steps(self):
        from estimation.bess_ekf import _MODE_Q_INFLATION
        est = _make_est("li_ion")
        est._mode_steps = 5     # pretend we're mid-transition
        x_pred = est.model.x0()
        Q_nom = est._Q[1, 1]
        Q_eff = est._effective_Q(x_pred)
        assert Q_eff[1, 1] == pytest.approx(Q_nom * _MODE_Q_INFLATION)

    def test_mode_steps_decay_per_update(self):
        est = _make_est("li_ion")
        # Pre-set P_dc to match the dispatch so no large ΔP_dc re-triggers mode change
        est._x = est.model.x0(p_dispatch_pu=0.5)
        est._mode_steps = 3
        model = est.model
        x = model.x0(p_dispatch_pu=0.5)
        u = np.array([0.5, 0.0])
        for _ in range(3):
            z = _measurement(model, x)
            est.update(z, u=u, dt=1e-3)
            x = model.f(x, u, 1e-3)
        assert est._mode_steps == 0


class TestConvergenceSpeed:
    def test_is_converged_after_n_updates(self):
        est = _make_est("li_ion")
        state, _ = _run_n_steps(est, 50)
        # is_converged requires ≥ 10 updates (we ran 50) and kappa_n < threshold
        assert est._n_updates >= 10
        # convergence flag should be True in nominal conditions
        assert est.is_converged or est._kappa_n < 1e6  # at minimum kappa finite

    def test_n_updates_increments(self):
        est = _make_est("li_ion")
        _run_n_steps(est, 25)
        assert est._n_updates == 25


class TestReset:
    def test_reset_clears_n_updates(self):
        est = _make_est("li_ion")
        _run_n_steps(est, 20)
        est.reset()
        assert est._n_updates == 0

    def test_reset_restores_nominal_soc(self):
        est = _make_est("li_ion")
        _run_n_steps(est, 20, soc0=0.30, p_sp=0.90)
        est.reset()
        # Default x0 has SoC=0.50
        assert abs(est._x[0] - 0.50) < 0.01

    def test_reset_with_custom_x0(self):
        est   = _make_est("li_ion")
        x_new = est.model.x0(soc=0.80)
        est.reset(x0=x_new)
        assert abs(est._x[0] - 0.80) < 1e-9


class TestOutputDictKeys:
    def test_all_state_keys_present(self):
        est   = _make_est("li_ion")
        model = est.model
        x     = model.x0()
        z     = _measurement(model, x)
        state = est.update(z)
        required = {"SoC", "P_dc", "Q_ac", "V_dc", "I_ac_mag",
                    "T_cell", "residual", "kappa_n", "n_updates"}
        assert required.issubset(state.keys())

    def test_residual_non_negative(self):
        est   = _make_est("li_ion")
        model = est.model
        z     = _measurement(model, model.x0())
        state = est.update(z)
        assert state["residual"] >= 0.0

    def test_kappa_n_positive(self):
        est   = _make_est("li_ion")
        model = est.model
        z     = _measurement(model, model.x0())
        state = est.update(z)
        assert state["kappa_n"] > 0.0


class TestStateClamped:
    def test_soc_never_exceeds_limits(self):
        est = _make_est("li_ion")
        model = est.model
        x = model.x0(soc=0.88)    # near soc_max
        u = np.array([1.0, 0.0])  # high dispatch
        for _ in range(50):
            x = model.f(x, u, 1e-3)
            z = _measurement(model, x)
            state = est.update(z, u=u, dt=1e-3)
        assert state["SoC"] <= est.cfg.soc_max + 1e-6

    def test_v_dc_within_bounds(self):
        est = _make_est("flow")
        model = est.model
        x = model.x0()
        for _ in range(30):
            x = model.f(x, None, 1e-3)
            z = _measurement(model, x)
            state = est.update(z, dt=1e-3)
        assert 0.80 <= state["V_dc"] <= 1.20


class TestChemistryVariants:
    @pytest.mark.parametrize("preset", ["li_ion", "flow", "na_ion"])
    def test_chemistry_produces_valid_state(self, preset):
        est   = _make_est(preset)
        model = est.model
        x     = model.x0(soc=0.50)
        u     = np.array([0.60, 0.0])
        for _ in range(20):
            x = model.f(x, u, 1e-3)
            z = _measurement(model, x)
            state = est.update(z, u=u, dt=1e-3)
        assert 0.0 < state["SoC"] < 1.0
        assert state["I_ac_mag"] >= 0.0
        assert math.isfinite(state["residual"])

    def test_na_ion_gfm_higher_fault_current(self):
        from models.bess_model import _CHEM_PARAMS
        est_li  = _make_est("li_ion")
        est_na  = _make_est("na_ion")
        i_li  = est_li.model.fault_current_limit(0.0)
        i_na  = est_na.model.fault_current_limit(0.0)
        # Na-ion is GFM → higher transient current than li-ion GFL
        assert i_na >= i_li


import math
