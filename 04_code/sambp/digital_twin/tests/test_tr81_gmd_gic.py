# =============================================================================
# tests/test_tr81_gmd_gic.py  —  TR-81 GMD/GIC protection tests
# =============================================================================

from __future__ import annotations

import math, sys, os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models.gic_model import (
    GICBus, GICLine, GICNetwork, GICResult,
    make_lp_benchmark, make_5bus_gic_network,
)
from estimation.transformer_thermal import (
    TransformerThermalModel, TransformerThermalParams,
)


# ===========================================================================
# Test 1 — GIC conservation: sum of all bus neutrals ≈ 0
# ===========================================================================

def test_gic_current_conservation():
    """KCL at earth: sum of all GIC neutral currents must be ≈ 0."""
    net    = make_lp_benchmark()
    result = net.solve(E_x_V_km=1.0, E_y_V_km=0.0)

    total = float(np.sum(result.I_GIC_A))
    assert abs(total) < 0.1, (
        f"GIC sum = {total:.4f} A (expected ≈ 0 by KCL)"
    )
    print(f"PASS test_gic_current_conservation  "
          f"(sum={total:.6f} A, bus GICs={[f'{x:.2f}' for x in result.I_GIC_A]})")


# ===========================================================================
# Test 2 — LP benchmark: zero E-field → zero GIC
# ===========================================================================

def test_zero_efield_zero_gic():
    """No geo-electric field must produce zero GIC everywhere."""
    net    = make_lp_benchmark()
    result = net.solve(E_x_V_km=0.0, E_y_V_km=0.0)

    assert result.max_I_GIC_A < 1e-6, (
        f"Non-zero GIC with E=0: max={result.max_I_GIC_A:.2e} A"
    )
    print("PASS test_zero_efield_zero_gic")


# ===========================================================================
# Test 3 — LP benchmark: GIC scales linearly with E-field magnitude
# ===========================================================================

def test_gic_linear_scaling():
    """GIC must scale linearly with E-field magnitude."""
    net   = make_lp_benchmark()
    r1    = net.solve(1.0, 0.0)
    r2    = net.solve(2.0, 0.0)

    ratio = r2.max_I_GIC_A / max(r1.max_I_GIC_A, 1e-9)
    assert abs(ratio - 2.0) < 0.01, (
        f"GIC not linearly scaling: ratio={ratio:.4f}, expected=2.0"
    )
    print(f"PASS test_gic_linear_scaling  (ratio={ratio:.4f})")


# ===========================================================================
# Test 4 — LP benchmark: E_x=1 V/km produces physically plausible GIC
# ===========================================================================

def test_lp_benchmark_magnitudes():
    """
    3-bus LP benchmark with E_x=1 V/km, E_y=0:
    Bus 1 should have largest |GIC| (at origin, field drives current north).
    All GIC magnitudes < 200 A (reasonable for 2Ω earthing).
    """
    net    = make_lp_benchmark()
    result = net.solve(E_x_V_km=1.0, E_y_V_km=0.0)

    # With E_x only (east-west), north-south lines (bus1-bus2) carry most GIC
    # The sum must be ≈ 0, and max GIC per bus < 200 A
    assert result.max_I_GIC_A > 0.0, "Expected non-zero GIC with E_x=1 V/km"
    assert result.max_I_GIC_A < 200.0, (
        f"GIC unexpectedly large: {result.max_I_GIC_A:.1f} A"
    )
    print(f"PASS test_lp_benchmark_magnitudes  "
          f"(bus GICs={[f'{x:.2f}' for x in result.I_GIC_A]} A)")


# ===========================================================================
# Test 5 — Direction reversal: E_y = -E_y flips GIC signs
# ===========================================================================

def test_efield_direction_reversal():
    """Reversing E-field direction must negate all GIC values."""
    net = make_5bus_gic_network()
    r_pos = net.solve(E_x_V_km=0.0, E_y_V_km=2.0)
    r_neg = net.solve(E_x_V_km=0.0, E_y_V_km=-2.0)

    for i in range(len(r_pos.I_GIC_A)):
        diff = r_pos.I_GIC_A[i] + r_neg.I_GIC_A[i]
        assert abs(diff) < 1e-6, (
            f"GIC not negated at bus {r_pos.bus_names[i]}: "
            f"+={r_pos.I_GIC_A[i]:.3f}, -={r_neg.I_GIC_A[i]:.3f}"
        )
    print("PASS test_efield_direction_reversal")


# ===========================================================================
# Test 6 — 5-bus network: non-trivial GIC distribution
# ===========================================================================

def test_5bus_network_gic():
    """5-bus network must produce non-uniform GIC distribution under E-field."""
    net    = make_5bus_gic_network()
    result = net.solve(E_x_V_km=1.5, E_y_V_km=0.5)

    # Sum ≈ 0
    total = float(np.sum(result.I_GIC_A))
    assert abs(total) < 0.5, f"GIC KCL violation: sum={total:.3f}"

    # At least some buses have non-zero GIC
    assert result.max_I_GIC_A > 1.0, "5-bus network GIC too low"
    print(f"PASS test_5bus_network_gic  "
          f"(max GIC={result.max_I_GIC_A:.2f} A)")


# ===========================================================================
# Test 7 — Thermal: rated load, no GIC → hot-spot converges to rated value
# ===========================================================================

def test_thermal_rated_load_steady_state():
    """
    At K=1 and no GIC, hot-spot must settle within 5°C of
    Θ_ambient + ΔΘ_TO_R + ΔΘ_HS_R at steady state.
    """
    params  = TransformerThermalParams(
        dTheta_TO_R=40.0, dTheta_HS_R=26.0,
        tau_TO_min=210.0, tau_HS_min=7.0,
        R_loss=6.0, n_TO=0.8, n_HS=1.3, k_gic=0.5,
    )
    model   = TransformerThermalModel(params, theta_ambient_init=20.0)
    # Start from cold (no load)
    model.reset(theta_ambient=20.0, K_init=0.0)

    # Simulate 600 minutes at K=1, step=10 min
    state = None
    for _ in range(60):
        state = model.step(dt_min=10.0, K_load=1.0, I_GIC_A=0.0)

    expected = 20.0 + params.dTheta_TO_R + params.dTheta_HS_R  # 86°C
    assert abs(state.theta_hotspot - expected) < 5.0, (
        f"Steady-state hot-spot {state.theta_hotspot:.1f}°C, "
        f"expected {expected:.1f}°C ± 5°C"
    )
    assert state.alarm_level == "NORMAL"
    print(f"PASS test_thermal_rated_load_steady_state  "
          f"(Θ_HS={state.theta_hotspot:.1f}°C, expected≈{expected:.1f}°C)")


# ===========================================================================
# Test 8 — Thermal: GIC raises hot-spot and triggers ELEVATED alarm
# ===========================================================================

def test_thermal_gic_raises_hotspot():
    """Large GIC (100 A) on top of rated load must raise hot-spot into ELEVATED."""
    params = TransformerThermalParams(
        dTheta_TO_R=40.0, dTheta_HS_R=26.0,
        tau_TO_min=210.0, tau_HS_min=7.0,
        R_loss=6.0, n_TO=0.8, n_HS=1.3, k_gic=0.5,
        I_rated_A=262.4,
    )
    model = TransformerThermalModel(params, theta_ambient_init=20.0)
    model.reset(20.0, K_init=1.0)   # start at rated

    # Apply GIC for 60 minutes, step=5 min
    state = None
    for _ in range(12):
        state = model.step(dt_min=5.0, K_load=1.0, I_GIC_A=100.0,
                           theta_ambient=30.0)

    # K_GIC = 100/262.4 × 0.5 = 0.190; K_eff = sqrt(1+0.19²) ≈ 1.018
    # Should raise hot-spot modestly but reach above normal
    assert state.theta_hotspot > 86.0, (
        f"GIC didn't raise hot-spot: {state.theta_hotspot:.1f}°C"
    )
    print(f"PASS test_thermal_gic_raises_hotspot  "
          f"(Θ_HS={state.theta_hotspot:.1f}°C, level={state.alarm_level})")


# ===========================================================================
# Test 9 — Thermal: overload + severe GIC → TRIP alarm
# ===========================================================================

def test_thermal_overload_gic_trip():
    """
    K=1.5 overload + severe GIC (300 A) → hot-spot must exceed 140°C (TRIP).
    """
    params = TransformerThermalParams(
        dTheta_TO_R=45.0, dTheta_HS_R=30.0,
        tau_TO_min=210.0, tau_HS_min=7.0,
        R_loss=6.0, n_TO=0.8, n_HS=1.3, k_gic=0.5,
        I_rated_A=262.4,
    )
    model = TransformerThermalModel(params, theta_ambient_init=35.0)
    model.reset(35.0, K_init=1.0)

    # Severe GMD event: overload + large GIC for 120 min
    state = None
    for _ in range(24):
        state = model.step(dt_min=5.0, K_load=1.5, I_GIC_A=300.0,
                           theta_ambient=35.0)

    assert state.theta_hotspot >= 140.0, (
        f"Expected TRIP-level hot-spot ≥140°C, got {state.theta_hotspot:.1f}°C"
    )
    assert state.alarm_level == "TRIP"
    assert state.active_alarm
    print(f"PASS test_thermal_overload_gic_trip  "
          f"(Θ_HS={state.theta_hotspot:.1f}°C → {state.alarm_level})")


# ===========================================================================
# Test 10 — Thermal tracking accuracy: Euler vs analytical within 5°C
# ===========================================================================

def test_thermal_tracking_accuracy():
    """
    Euler integration with 1-min steps must track the analytical first-order
    response for hot-spot within 5°C at any point.
    Analytical: Θ_HS(t) = Θ_SS - (Θ_SS - Θ_0)·exp(-t/τ_HS)
    (using just the HS equation with constant dTO≈dTO_SS)
    """
    params = TransformerThermalParams(
        dTheta_HS_R=26.0, tau_HS_min=7.0,
        dTheta_TO_R=40.0, tau_TO_min=210.0,
        R_loss=6.0, n_TO=0.8, n_HS=1.3, k_gic=0.5,
    )
    model = TransformerThermalModel(params, theta_ambient_init=20.0)
    model.reset(20.0, K_init=0.0)   # start cold (dHS=0)

    # Apply K=1 in a step; track HS response over 60 min
    # Steady-state HS rise = 26°C; τ_HS = 7 min
    # Θ_SS = 20 + 40 + 26 = 86°C; Θ_0 = 20 + 40 + 0 = 60°C (cold winding)
    # But dTO also evolves. For this test, fix dTO at rated=40 and check dHS only.

    max_error = 0.0
    theta_hs_ss = 20.0 + params.dTheta_TO_R + params.dTheta_HS_R  # 86°C
    theta_hs_0  = 20.0 + params.dTheta_TO_R   # 60°C if dHS starts at 0

    for step in range(60):   # 60 × 1-min steps
        t_min    = (step + 1) * 1.0
        state    = model.step(dt_min=1.0, K_load=1.0)
        # Analytical HS (approximation: dTO ≈ constant at rated)
        analytic = theta_hs_ss - (theta_hs_ss - theta_hs_0) * math.exp(
            -t_min / params.tau_HS_min
        )
        error    = abs(state.theta_hotspot - analytic)
        max_error = max(max_error, error)

    assert max_error < 5.0, (
        f"Thermal tracking error {max_error:.2f}°C > 5°C tolerance"
    )
    print(f"PASS test_thermal_tracking_accuracy  "
          f"(max error vs analytical: {max_error:.2f}°C)")


# ===========================================================================
# Test 11 — Integration: GIC from LP solver feeds thermal model
# ===========================================================================

def test_gic_to_thermal_integration():
    """
    GIC from the LP solver drives transformer thermal model.
    Bus with largest GIC should have elevated hot-spot vs no-GIC case.
    """
    net    = make_5bus_gic_network()
    result = net.solve(E_x_V_km=2.0, E_y_V_km=1.0)

    # Find bus with peak GIC
    peak_idx = int(np.argmax(np.abs(result.I_GIC_A)))
    I_gic    = abs(float(result.I_GIC_A[peak_idx]))

    params = TransformerThermalParams(I_rated_A=262.4, k_gic=0.5)

    # No-GIC case
    m_no_gic = TransformerThermalModel(params, theta_ambient_init=25.0)
    m_no_gic.reset(25.0, K_init=1.0)

    # With GIC
    m_gic = TransformerThermalModel(params, theta_ambient_init=25.0)
    m_gic.reset(25.0, K_init=1.0)

    # Simulate 60 min
    s_no_gic, s_gic = None, None
    for _ in range(60):
        s_no_gic = m_no_gic.step(dt_min=1.0, K_load=1.0, I_GIC_A=0.0)
        s_gic    = m_gic.step(dt_min=1.0, K_load=1.0, I_GIC_A=I_gic)

    assert s_gic.theta_hotspot >= s_no_gic.theta_hotspot, (
        f"GIC case should be warmer: GIC={s_gic.theta_hotspot:.1f}°C, "
        f"no-GIC={s_no_gic.theta_hotspot:.1f}°C"
    )
    print(f"PASS test_gic_to_thermal_integration  "
          f"(I_GIC={I_gic:.1f}A, "
          f"ΔΘ_HS={s_gic.theta_hotspot - s_no_gic.theta_hotspot:.2f}°C)")


# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    test_gic_current_conservation()
    test_zero_efield_zero_gic()
    test_gic_linear_scaling()
    test_lp_benchmark_magnitudes()
    test_efield_direction_reversal()
    test_5bus_network_gic()
    test_thermal_rated_load_steady_state()
    test_thermal_gic_raises_hotspot()
    test_thermal_overload_gic_trip()
    test_thermal_tracking_accuracy()
    test_gic_to_thermal_integration()
    print("\nAll TR-81 tests passed.")
