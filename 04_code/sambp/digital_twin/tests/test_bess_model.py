# =============================================================================
# tests/test_bess_model.py
#
# Unit tests for models/bess_model.py — TR-68 WP 68.1
#
# Tests
# -----
#   1. test_normal_operation        — f() runs N steps, SoC moves correctly
#   2. test_soc_limits              — SoC clamped at soc_min / soc_max
#   3. test_fault_current_limit_gfl — GFL: constant hard limit, no overshoot
#   4. test_fault_current_limit_gfm — GFM: transient peak → decay to continuous
#   5. test_thermal_model           — T_cell rises under sustained load
#   6. test_chemistry_dynamics      — R_int and bandwidth differ by chemistry
#   7. test_measurement_model       — h(x) returns balanced 3-phase phasors
# =============================================================================

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure digital_twin root is on path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from models.bess_model import (
    BESSConfig,
    BESSModel,
    _CHEM_PARAMS,
    _I_ac,
    _SoC,
    _T_cell,
    _P_dc,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def li_ion_cfg() -> BESSConfig:
    return BESSConfig.li_ion_1mwh()


@pytest.fixture(scope="module")
def flow_cfg() -> BESSConfig:
    return BESSConfig.flow_5mwh()


@pytest.fixture(scope="module")
def na_ion_cfg() -> BESSConfig:
    return BESSConfig.na_ion_500kwh()


@pytest.fixture(scope="module")
def li_ion_model(li_ion_cfg) -> BESSModel:
    return BESSModel(li_ion_cfg)


@pytest.fixture(scope="module")
def flow_model(flow_cfg) -> BESSModel:
    return BESSModel(flow_cfg)


@pytest.fixture(scope="module")
def na_ion_model(na_ion_cfg) -> BESSModel:
    return BESSModel(na_ion_cfg)


# ---------------------------------------------------------------------------
# 1. test_normal_operation
# ---------------------------------------------------------------------------

class TestNormalOperation:
    """BESSModel.f() produces physically sensible state trajectories."""

    def test_discharge_reduces_soc(self, li_ion_model):
        """Discharging (P_dc > 0) must decrease SoC over time."""
        x = li_ion_model.x0(soc=0.70, p_dispatch_pu=0.50)
        # Simulate 1 second at 1 kHz
        for _ in range(1000):
            x = li_ion_model.f(x, u=np.array([0.50, 0.0]), dt=1e-3)
        # SoC should have dropped (though negligibly for 1 s vs 1 MWh capacity)
        assert x[_SoC] < 0.70, "SoC did not decrease during discharge"

    def test_charge_increases_soc(self, li_ion_model):
        """Charging (P_dc < 0) must increase SoC."""
        x = li_ion_model.x0(soc=0.30, p_dispatch_pu=-0.50)
        for _ in range(1000):
            x = li_ion_model.f(x, u=np.array([-0.50, 0.0]), dt=1e-3)
        assert x[_SoC] > 0.30, "SoC did not increase during charging"

    def test_idle_soc_constant(self, li_ion_model):
        """At P_dc = 0 the SoC should remain unchanged (within float precision)."""
        x = li_ion_model.x0(soc=0.50, p_dispatch_pu=0.0)
        x0_soc = x[_SoC]
        for _ in range(500):
            x = li_ion_model.f(x, u=np.array([0.0, 0.0]), dt=1e-3)
        assert abs(x[_SoC] - x0_soc) < 1e-10, "SoC changed unexpectedly at idle"

    def test_output_shape(self, li_ion_model):
        """f() must return a (6,) array."""
        x  = li_ion_model.x0()
        xn = li_ion_model.f(x, dt=1e-3)
        assert xn.shape == (6,)

    def test_v_dc_above_zero(self, li_ion_model):
        """V_dc must remain positive under normal operation."""
        x = li_ion_model.x0(soc=0.50, p_dispatch_pu=0.80)
        for _ in range(100):
            x = li_ion_model.f(x, u=np.array([0.80, 0.0]), dt=1e-3)
        assert x[3] > 0.0, "V_dc became non-positive"

    def test_no_nan_in_trajectory(self, li_ion_model):
        """No NaN or Inf should appear in 5-second simulation."""
        x = li_ion_model.x0(soc=0.60)
        for _ in range(5000):
            x = li_ion_model.f(x, dt=1e-3)
        assert not np.any(np.isnan(x)), "NaN in state vector"
        assert not np.any(np.isinf(x)), "Inf in state vector"


# ---------------------------------------------------------------------------
# 2. test_soc_limits
# ---------------------------------------------------------------------------

class TestSoCLimits:
    """BESSModel.clamp() enforces config SoC limits."""

    def test_soc_min_enforced_by_clamp(self, li_ion_model):
        """clamp() must raise SoC to soc_min when below."""
        x = li_ion_model.x0(soc=0.50)
        x[_SoC] = 0.01   # below soc_min = 0.10
        x_clamped = li_ion_model.clamp(x)
        assert x_clamped[_SoC] == pytest.approx(li_ion_model.cfg.soc_min)

    def test_soc_max_enforced_by_clamp(self, li_ion_model):
        """clamp() must lower SoC to soc_max when above."""
        x = li_ion_model.x0(soc=0.50)
        x[_SoC] = 0.99   # above soc_max = 0.90
        x_clamped = li_ion_model.clamp(x)
        assert x_clamped[_SoC] == pytest.approx(li_ion_model.cfg.soc_max)

    def test_soc_within_bounds_unchanged(self, li_ion_model):
        """clamp() must not alter SoC when already in bounds."""
        x = li_ion_model.x0(soc=0.55)
        x_clamped = li_ion_model.clamp(x)
        assert x_clamped[_SoC] == pytest.approx(0.55, rel=1e-9)

    def test_discharge_stops_at_soc_min(self, li_ion_model):
        """Sustained discharge must stop at soc_min due to clamp in f()."""
        x = li_ion_model.x0(soc=0.12, p_dispatch_pu=1.0)
        # Run many steps; SoC should not go below soc_min
        for _ in range(50000):
            x = li_ion_model.f(x, u=np.array([1.0, 0.0]), dt=1e-3)
        assert x[_SoC] >= li_ion_model.cfg.soc_min - 1e-9

    def test_flow_different_soc_limits(self, flow_model):
        """Flow BESS has soc_min=0.15, soc_max=0.85 — verify these are applied."""
        x = flow_model.x0(soc=0.50)
        x[_SoC] = 0.05   # below flow soc_min = 0.15
        x_c = flow_model.clamp(x)
        assert x_c[_SoC] == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# 3. test_fault_current_limit_gfl
# ---------------------------------------------------------------------------

class TestFaultCurrentLimitGFL:
    """GFL BESS holds a constant hard current limit during faults."""

    def test_gfl_limit_constant_with_time(self, li_ion_model):
        """GFL fault current limit must be constant regardless of t_elapsed."""
        i0  = li_ion_model.fault_current_limit(t_elapsed=0.00)
        i50 = li_ion_model.fault_current_limit(t_elapsed=0.05)
        i200 = li_ion_model.fault_current_limit(t_elapsed=0.20)
        assert i0 == pytest.approx(i50)
        assert i0 == pytest.approx(i200)

    def test_gfl_limit_equals_config(self, li_ion_model):
        """GFL fault current limit must equal cfg.current_limit_pu."""
        i_lim = li_ion_model.fault_current_limit()
        assert i_lim == pytest.approx(li_ion_model.cfg.current_limit_pu)

    def test_gfl_fault_state_does_not_exceed_limit(self, li_ion_model):
        """fault_state() I_ac_mag must not exceed i_ac_max_pu."""
        x = li_ion_model.x0(soc=0.60)
        for ft in ("SLG", "LL", "DLG", "3PH"):
            xf = li_ion_model.fault_state(x, fault_type=ft)
            assert xf[_I_ac] <= li_ion_model.cfg.i_ac_max_pu + 1e-9, \
                f"I_ac_mag exceeded i_ac_max_pu for fault type {ft}"

    def test_gfl_3ph_fault_highest_current(self, li_ion_model):
        """3PH fault (no negative-sequence penalty) should give highest I_ac."""
        x = li_ion_model.x0(soc=0.60)
        i_3ph = li_ion_model.fault_state(x, fault_type="3PH")[_I_ac]
        i_slg = li_ion_model.fault_state(x, fault_type="SLG")[_I_ac]
        assert i_3ph >= i_slg, "3PH fault current not >= SLG fault current"


# ---------------------------------------------------------------------------
# 4. test_fault_current_limit_gfm
# ---------------------------------------------------------------------------

class TestFaultCurrentLimitGFM:
    """GFM BESS has a transient overshoot that decays exponentially."""

    def test_gfm_initial_limit_is_transient_peak(self, na_ion_model):
        """At t=0, GFM limit must equal i_max_trans_pu from chemistry table."""
        c = _CHEM_PARAMS["na_ion"]
        i_t0 = na_ion_model.fault_current_limit(t_elapsed=0.0)
        assert i_t0 == pytest.approx(c["i_max_trans_pu"], rel=1e-6)

    def test_gfm_limit_decays_over_time(self, na_ion_model):
        """GFM limit must strictly decrease as t_elapsed increases."""
        times = [0.0, 0.05, 0.10, 0.20, 0.50, 1.0]
        limits = [na_ion_model.fault_current_limit(t) for t in times]
        for i in range(len(limits) - 1):
            assert limits[i] >= limits[i + 1], \
                f"GFM limit did not decrease: t={times[i]} → {times[i+1]}"

    def test_gfm_approaches_continuous_limit_at_long_time(self, na_ion_model):
        """After 10 × tau, GFM limit should be within 0.01 pu of i_max_cont_pu."""
        c = _CHEM_PARAMS["na_ion"]
        tau = c["trans_decay_tau"]
        i_long = na_ion_model.fault_current_limit(t_elapsed=10.0 * tau)
        assert abs(i_long - c["i_max_cont_pu"]) < 0.01, \
            f"GFM did not converge to continuous limit: {i_long:.4f}"

    def test_gfm_transient_exceeds_gfl_limit(self, na_ion_model, li_ion_model):
        """GFM transient limit must exceed GFL steady-state limit."""
        i_gfm_t0 = na_ion_model.fault_current_limit(0.0)
        i_gfl    = li_ion_model.fault_current_limit(0.0)
        assert i_gfm_t0 > i_gfl, \
            "GFM transient limit should exceed GFL limit at t=0"


# ---------------------------------------------------------------------------
# 5. test_thermal_model
# ---------------------------------------------------------------------------

class TestThermalModel:
    """T_cell rises under sustained load and is bounded correctly."""

    def test_temperature_rises_under_load(self, li_ion_model):
        """Sustained high-power dispatch must raise T_cell above ambient."""
        x = li_ion_model.x0(soc=0.60, p_dispatch_pu=1.0)
        # 30-second simulation at 1 kHz
        for _ in range(30000):
            x = li_ion_model.f(x, u=np.array([1.0, 0.0]), dt=1e-3)
        assert x[_T_cell] > li_ion_model.t_ambient, \
            "T_cell did not rise above ambient under full load"

    def test_idle_temperature_stable(self, li_ion_model):
        """At zero dispatch, T_cell must remain at ambient (no self-heating)."""
        x = li_ion_model.x0(soc=0.50, p_dispatch_pu=0.0)
        for _ in range(10000):
            x = li_ion_model.f(x, u=np.array([0.0, 0.0]), dt=1e-3)
        assert abs(x[_T_cell] - li_ion_model.t_ambient) < 0.1, \
            "T_cell drifted from ambient at zero dispatch"

    def test_temperature_bounded_above(self, li_ion_model):
        """T_cell must not exceed 80 °C (upper bound from _STATE_BOUNDS)."""
        x = li_ion_model.x0(soc=0.60, p_dispatch_pu=1.0)
        for _ in range(300000):
            x = li_ion_model.f(x, u=np.array([1.0, 0.0]), dt=1e-3)
        assert x[_T_cell] <= 80.0 + 1e-9

    def test_r_int_increases_at_low_soc(self, li_ion_model):
        """r_int at SoC=0.1 must exceed r_int at SoC=0.9 (NMC/LFP behaviour)."""
        r_low  = li_ion_model.r_int(soc=0.10, t_cell=25.0)
        r_high = li_ion_model.r_int(soc=0.90, t_cell=25.0)
        assert r_low > r_high, "r_int did not increase at low SoC"

    def test_r_int_decreases_with_temperature(self, li_ion_model):
        """r_int must decrease as temperature rises (NTC electrolyte behaviour)."""
        r_cold = li_ion_model.r_int(soc=0.50, t_cell=10.0)
        r_warm = li_ion_model.r_int(soc=0.50, t_cell=40.0)
        assert r_cold > r_warm, "r_int did not decrease with temperature"


# ---------------------------------------------------------------------------
# 6. test_chemistry_dynamics
# ---------------------------------------------------------------------------

class TestChemistryDynamics:
    """Different chemistries have different R_int and converter bandwidths."""

    def test_flow_r_int_higher_than_li_ion(self, flow_model, li_ion_model):
        """Vanadium flow r_int_nom must exceed Li-ion r_int_nom."""
        r_flow   = flow_model.r_int(soc=0.50, t_cell=25.0)
        r_li_ion = li_ion_model.r_int(soc=0.50, t_cell=25.0)
        assert r_flow > r_li_ion, "Flow r_int not higher than Li-ion"

    def test_flow_slower_p_response(self, flow_model, li_ion_model):
        """Flow BESS (20 Hz BW) tracks P setpoint slower than Li-ion (100 Hz)."""
        x_flow   = flow_model.x0(soc=0.50, p_dispatch_pu=0.0)
        x_li_ion = li_ion_model.x0(soc=0.50, p_dispatch_pu=0.0)
        sp = np.array([1.0, 0.0])
        # Simulate 5 ms
        for _ in range(5):
            x_flow   = flow_model.f(x_flow, u=sp, dt=1e-3)
            x_li_ion = li_ion_model.f(x_li_ion, u=sp, dt=1e-3)
        # Li-ion should have tracked the setpoint more (higher P_dc after 5 ms)
        assert x_li_ion[_P_dc] > x_flow[_P_dc], \
            "Li-ion did not converge faster than flow toward P setpoint"

    def test_all_presets_instantiate(self):
        """All three preset factory methods must return valid BESSConfig."""
        for factory in (BESSConfig.li_ion_1mwh,
                        BESSConfig.flow_5mwh,
                        BESSConfig.na_ion_500kwh):
            cfg = factory()
            assert isinstance(cfg, BESSConfig)
            model = BESSModel(cfg)
            x0 = model.x0()
            assert x0.shape == (6,)

    def test_invalid_chemistry_raises(self):
        """Constructing BESSConfig with unknown chemistry must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown chemistry"):
            BESSConfig(chemistry="lead_acid",
                       capacity_kwh=100.0,
                       power_rating_kw=50.0,
                       v_dc_nom=400.0,
                       i_ac_max_pu=1.0)

    def test_invalid_control_mode_raises(self):
        """Constructing BESSConfig with unknown control_mode must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown control_mode"):
            BESSConfig(chemistry="li_ion",
                       capacity_kwh=100.0,
                       power_rating_kw=50.0,
                       v_dc_nom=400.0,
                       i_ac_max_pu=1.0,
                       control_mode="droop")

    def test_na_ion_is_gfm(self, na_ion_cfg):
        """Na-ion preset must be grid-forming."""
        assert na_ion_cfg.is_gfm

    def test_li_ion_is_not_gfm(self, li_ion_cfg):
        """Li-ion preset must be grid-following."""
        assert not li_ion_cfg.is_gfm


# ---------------------------------------------------------------------------
# 7. test_measurement_model
# ---------------------------------------------------------------------------

class TestMeasurementModel:
    """h(x) reconstructs balanced three-phase phasors from state."""

    def test_output_shape(self, li_ion_model):
        """h(x) must return a (6,) array [Va, Vb, Vc, Ia, Ib, Ic]."""
        x = li_ion_model.x0(soc=0.60, p_dispatch_pu=0.50)
        z = li_ion_model.h(x)
        assert z.shape == (6,)

    def test_voltages_balanced(self, li_ion_model):
        """Three-phase voltages must be balanced: Va+Vb+Vc=0 and constant power."""
        x = li_ion_model.x0(soc=0.60, p_dispatch_pu=0.50)
        # Zero-sequence check holds for any theta
        for theta in [0.0, math.pi / 6, math.pi / 3, math.pi / 2]:
            z = li_ion_model.h(x, theta=theta)
            va, vb, vc = z[0], z[1], z[2]
            # Balanced 3-phase: Va + Vb + Vc = 0 (no zero-sequence component)
            assert abs(va + vb + vc) < 1e-10, \
                f"Va+Vb+Vc != 0 at theta={theta:.4f}: sum={va+vb+vc:.2e}"
            # Constant instantaneous power: Va²+Vb²+Vc² = 3 × V_ac² (peak²)
            # For V_ac = 1.0 pu: Va²+Vb²+Vc² = 3 × (√2)²/2 × 2 = 3.0
            sum_sq = va**2 + vb**2 + vc**2
            assert abs(sum_sq - 3.0) < 1e-10, \
                f"Va²+Vb²+Vc² != 3.0 at theta={theta:.4f}: sum_sq={sum_sq:.6f}"

    def test_voltages_120_degree_apart(self, li_ion_model):
        """Va, Vb, Vc at theta=0 must have 120° phase separation."""
        x = li_ion_model.x0(soc=0.60, p_dispatch_pu=0.0)
        # At theta=0: Va=√2×1, Vb=√2×cos(-2π/3), Vc=√2×cos(+2π/3)
        z = li_ion_model.h(x, theta=0.0)
        va, vb, vc = z[0], z[1], z[2]
        sqrt2 = math.sqrt(2.0)
        assert va == pytest.approx(sqrt2, rel=1e-6)
        assert vb == pytest.approx(sqrt2 * math.cos(-2.0 * math.pi / 3.0), rel=1e-6)
        assert vc == pytest.approx(sqrt2 * math.cos(+2.0 * math.pi / 3.0), rel=1e-6)

    def test_current_magnitude_matches_i_ac_state(self, li_ion_model):
        """Peak current magnitude in h(x) must match I_ac_mag state."""
        x = li_ion_model.x0(soc=0.60, p_dispatch_pu=0.70)
        x[4] = 0.70  # force I_ac_mag directly
        z = li_ion_model.h(x, theta=0.0)
        # RMS of three-phase instantaneous at t=0: sqrt((Ia²+Ib²+Ic²)/3) = I_peak/√2
        i_peak_from_z = math.sqrt((z[3]**2 + z[4]**2 + z[5]**2) * 2.0 / 3.0)
        assert i_peak_from_z == pytest.approx(x[4] * math.sqrt(2.0), rel=1e-5)

    def test_zero_power_zero_current(self, li_ion_model):
        """At P_dc=Q_ac=0, I_ac current phasors should be zero."""
        x = li_ion_model.x0(soc=0.50, p_dispatch_pu=0.0)
        x[4] = 0.0   # force I_ac_mag to zero
        z = li_ion_model.h(x, theta=0.0)
        assert np.allclose(z[3:], 0.0, atol=1e-12), \
            "Non-zero currents at zero dispatch"

    def test_jacobian_shape(self, li_ion_model):
        """H_jacobian must return a (6, 6) matrix."""
        x = li_ion_model.x0(soc=0.60, p_dispatch_pu=0.50)
        H = li_ion_model.H_jacobian(x)
        assert H.shape == (6, 6)

    def test_voltage_rows_independent_of_state(self, li_ion_model):
        """Jacobian rows 0–2 (voltages) must be all-zero (V_ac fixed at 1.0 pu)."""
        x = li_ion_model.x0(soc=0.60, p_dispatch_pu=0.50)
        H = li_ion_model.H_jacobian(x)
        assert np.allclose(H[:3, :], 0.0), \
            "Voltage rows of Jacobian should be zero (V_ac = 1.0 pu constant)"

    def test_current_rows_nonzero_for_nonzero_i_ac(self, li_ion_model):
        """Jacobian rows 3–5 (currents) must have non-zero entries when I_ac > 0."""
        x = li_ion_model.x0(soc=0.60, p_dispatch_pu=0.50)
        H = li_ion_model.H_jacobian(x)
        assert np.any(H[3:, :] != 0.0), \
            "Current rows of Jacobian are all zero (expected non-zero for I_ac > 0)"
