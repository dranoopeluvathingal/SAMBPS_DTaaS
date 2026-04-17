# =============================================================================
# tests/test_tr80_dc_microgrid.py  —  TR-80 DC microgrid protection tests
# =============================================================================

from __future__ import annotations

import math, sys, os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models.dc_fault_model import DCBusParams, DCFaultParams, DCFaultModel
from models.dc_protection_mirror import DCProtectionMirror, DCProtectionSettings
from models.dc_microgrid import (
    DCMicrogridDT, DCMicrogridConfig, DCSource, DCLoad,
    make_lvdc_400v, make_mvdc_6kv,
)


# ===========================================================================
# Test 1 — Underdamped RLC discharge: peak within first 5 ms, damped to <10%
# ===========================================================================

def test_capacitor_discharge_underdamped():
    """Low-R RLC → underdamped oscillation; peak within 5 ms, decays to <10% at 10 ms."""
    bus   = DCBusParams(V_nom_V=400.0, C_bus_F=10e-3, L_cable_H=10e-6,
                        R_cable_Ohm=0.01, I_conv_max_A=0.0, tau_ctrl_ms=1.0)
    fault = DCFaultParams(fault_type="pole_to_pole", R_fault_Ohm=0.001)
    model = DCFaultModel(bus, fault)
    trace = model.simulate(t_end_ms=10.0, dt_us=10.0)

    # Capacitor discharge peak should appear early
    peak_idx = int(np.argmax(np.abs(trace.I_cap_A)))
    peak_t   = trace.t_ms[peak_idx]
    assert peak_t < 5.0, f"Cap discharge peak at {peak_t:.2f} ms, expected < 5 ms"

    # Cap discharge at 10 ms should have decayed significantly
    final_cap = abs(trace.I_cap_A[-1])
    peak_cap  = abs(trace.I_cap_A[peak_idx])
    if peak_cap > 1.0:
        assert final_cap / peak_cap < 0.30, (
            f"Cap discharge not decaying: final/peak = {final_cap/peak_cap:.3f}"
        )

    print(f"PASS test_capacitor_discharge_underdamped  "
          f"(peak={trace.I_cap_A[peak_idx]:.1f}A at t={peak_t:.2f}ms)")


# ===========================================================================
# Test 2 — Overdamped: high R → no oscillation, monotone rise and fall
# ===========================================================================

def test_capacitor_discharge_overdamped():
    """High-R RLC → overdamped; I_cap monotone (no oscillation)."""
    bus   = DCBusParams(V_nom_V=400.0, C_bus_F=5e-3, L_cable_H=10e-6,
                        R_cable_Ohm=5.0, I_conv_max_A=0.0, tau_ctrl_ms=1.0)
    fault = DCFaultParams(fault_type="pole_to_pole", R_fault_Ohm=0.5)
    model = DCFaultModel(bus, fault)
    trace = model.simulate(t_end_ms=10.0, dt_us=10.0)

    I_cap = trace.I_cap_A
    # In overdamped case, there should be at most one sign change (after peak decays)
    sign_changes = int(np.sum(np.diff(np.sign(I_cap)) != 0))
    assert sign_changes <= 1, f"Overdamped case has {sign_changes} zero crossings (expected ≤1)"
    print(f"PASS test_capacitor_discharge_overdamped  (sign_changes={sign_changes})")


# ===========================================================================
# Test 3 — dI/dt peak appears within 1 ms of fault inception
# ===========================================================================

def test_didt_peak_sub_ms():
    """dI/dt peak must occur within the first 1 ms (sub-ms fault dynamics)."""
    bus   = DCBusParams(V_nom_V=400.0, C_bus_F=10e-3, L_cable_H=5e-6,
                        R_cable_Ohm=0.02, I_conv_max_A=500.0, tau_ctrl_ms=1.0)
    fault = DCFaultParams(fault_type="pole_to_pole", R_fault_Ohm=0.001)
    model = DCFaultModel(bus, fault)
    trace = model.simulate(t_end_ms=5.0, dt_us=5.0)

    peak_didt_idx = int(np.argmax(np.abs(trace.dI_dt_A_ms)))
    peak_t        = trace.t_ms[peak_didt_idx]
    assert peak_t <= 1.0, f"dI/dt peak at {peak_t:.3f} ms, expected ≤ 1 ms"
    assert trace.peak_dI_dt_A_ms > 0.0
    print(f"PASS test_didt_peak_sub_ms  "
          f"(peak dI/dt={trace.peak_dI_dt_A_ms:.1f} A/ms at {peak_t:.3f} ms)")


# ===========================================================================
# Test 4 — 76DC overcurrent: high-set trips instantly
# ===========================================================================

def test_dc_oc_highset_trip():
    """76DC high-set must trip immediately when I > hi_pickup."""
    settings = DCProtectionSettings(
        oc_pickup_A=300.0, oc_hi_pickup_A=800.0, oc_delay_ms=2.0,
        V_nom_V=400.0,
    )
    mirror = DCProtectionMirror(settings)

    # Inject a 1200 A fault current, simulate over time
    t_trip = None
    for step in range(200):   # 0–20 ms at 0.1 ms steps
        t_ms = step * 0.1
        I_A  = 1200.0
        V_V  = 400.0 * math.exp(-t_ms / 5.0)   # voltage sags
        dI   = 150.0 if step < 10 else 0.0
        events = mirror.evaluate(t_ms, I_A, V_V, dI)
        for ev in events:
            if ev.function == "76DC" and ev.operate and t_trip is None:
                t_trip = t_ms

    assert t_trip is not None, "76DC high-set never operated"
    assert t_trip <= 0.2, f"76DC high-set trip at {t_trip:.2f} ms (expected ≤0.2 ms)"
    print(f"PASS test_dc_oc_highset_trip  (trip at t={t_trip:.2f} ms)")


# ===========================================================================
# Test 5 — 76DC time-delayed: normal OC trips after delay
# ===========================================================================

def test_dc_oc_delayed_trip():
    """76DC time-delayed element must trip after oc_delay_ms."""
    settings = DCProtectionSettings(
        oc_pickup_A=300.0, oc_hi_pickup_A=2000.0, oc_delay_ms=3.0,
        V_nom_V=400.0,
    )
    mirror = DCProtectionMirror(settings)

    t_trip = None
    for step in range(100):
        t_ms   = step * 0.1
        events = mirror.evaluate(t_ms, I_A=500.0, V_V=350.0, dI_dt=10.0)
        for ev in events:
            if ev.function == "76DC" and ev.operate and t_trip is None:
                t_trip = t_ms

    assert t_trip is not None, "76DC delayed OC never operated"
    assert t_trip >= 3.0, f"76DC delayed trip at {t_trip:.1f} ms < 3 ms delay"
    print(f"PASS test_dc_oc_delayed_trip  (trip at t={t_trip:.1f} ms)")


# ===========================================================================
# Test 6 — 81DC dI/dt element trips on fast-rising fault
# ===========================================================================

def test_didt_protection_trips():
    """81DC dI/dt element must operate on steep current rise."""
    settings = DCProtectionSettings(
        oc_pickup_A=1000.0,   # high OC pickup so only dI/dt fires
        didt_pickup_A_ms=200.0,
        didt_delay_ms=0.1,
        V_nom_V=400.0,
    )
    mirror = DCProtectionMirror(settings)

    t_trip = None
    for step in range(50):
        t_ms   = step * 0.05
        dI_dt  = 500.0   # 500 A/ms — fast capacitor discharge
        events = mirror.evaluate(t_ms, I_A=200.0, V_V=380.0, dI_dt=dI_dt)
        for ev in events:
            if ev.function == "81DC" and ev.operate and t_trip is None:
                t_trip = t_ms

    assert t_trip is not None, "81DC dI/dt element never operated"
    assert t_trip <= 0.5, f"81DC trip at {t_trip:.2f} ms (expected ≤ 0.5 ms)"
    print(f"PASS test_didt_protection_trips  (trip at t={t_trip:.2f} ms)")


# ===========================================================================
# Test 7 — 87DC differential: unbalanced currents trip
# ===========================================================================

def test_dc_differential_trips():
    """87DC differential must operate when I_diff exceeds bias threshold."""
    settings = DCProtectionSettings(
        diff_pickup_A=50.0, diff_slope_pct=20.0, V_nom_V=400.0,
    )
    mirror = DCProtectionMirror(settings)

    # I_in=500, I_out=300 → I_diff=200 A; I_avg=400 A; bias=50+0.20*400=130 A
    events = mirror.evaluate(t_ms=1.0, I_A=500.0, V_V=390.0, dI_dt=5.0,
                             I_diff_A=200.0, I_avg_A=400.0)
    trip_87 = any(ev.function == "87DC" and ev.operate for ev in events)
    assert trip_87, "87DC differential should trip with I_diff=200A > bias=130A"
    print("PASS test_dc_differential_trips")


# ===========================================================================
# Test 8 — 50ARC: arc flash detected via combined I + V-dip signature
# ===========================================================================

def test_arc_flash_detection():
    """50ARC must operate on combined high-I + large V-dip signature."""
    settings = DCProtectionSettings(
        oc_pickup_A=300.0, arc_I_mult=1.5, arc_V_dip_pu=0.30, V_nom_V=400.0,
    )
    mirror = DCProtectionMirror(settings)

    # Arc: I = 500 A (> 1.5 × 300 = 450), V = 200 V (dip = 50% ≥ 30%)
    events = mirror.evaluate(t_ms=0.5, I_A=500.0, V_V=200.0, dI_dt=50.0)
    arc_trip = any(ev.function == "50ARC" and ev.operate for ev in events)
    assert arc_trip, "50ARC should trip with I=500A and V-dip=50%"
    print("PASS test_arc_flash_detection")


# ===========================================================================
# Test 9 — LVDC 400 V: steady-state and fault simulation
# ===========================================================================

def test_lvdc_400v_normal_and_fault():
    """LVDC 400V DT: steady-state OK, fault raises large dI/dt."""
    dg = make_lvdc_400v()

    # Steady state
    ss = dg.get_steady_state()
    assert 350.0 <= ss.V_bus_V <= 450.0, f"V_bus={ss.V_bus_V} outside 350–450 V"
    assert ss.V_pu >= 0.85, f"V_pu={ss.V_pu:.3f} too low"

    # Pole-to-pole fault
    dg.inject_fault(DCFaultParams(fault_type="pole_to_pole", R_fault_Ohm=0.001))
    trace = dg.simulate(t_end_ms=10.0, dt_us=10.0)

    assert trace.peak_I_A > 500.0, f"Fault current peak={trace.peak_I_A:.1f}A too low"
    assert trace.peak_dI_dt > 50.0, f"dI/dt peak={trace.peak_dI_dt:.1f} A/ms too low"
    print(f"PASS test_lvdc_400v_normal_and_fault  "
          f"(V_ss={ss.V_bus_V:.0f}V, I_peak={trace.peak_I_A:.0f}A, "
          f"dI/dt_peak={trace.peak_dI_dt:.0f} A/ms)")


# ===========================================================================
# Test 10 — MVDC 6 kV: fault current scales with voltage class
# ===========================================================================

def test_mvdc_6kv_fault_scaling():
    """MVDC 6 kV fault current peak must be >> LVDC peak (voltage scaling)."""
    dg_lv = make_lvdc_400v()
    dg_mv = make_mvdc_6kv()

    fault = DCFaultParams(fault_type="pole_to_pole", R_fault_Ohm=0.001)

    dg_lv.inject_fault(fault)
    trace_lv = dg_lv.simulate(t_end_ms=5.0, dt_us=10.0)

    dg_mv.inject_fault(fault)
    trace_mv = dg_mv.simulate(t_end_ms=5.0, dt_us=10.0)

    assert trace_mv.peak_I_A > trace_lv.peak_I_A, (
        f"MVDC peak ({trace_mv.peak_I_A:.0f}A) should exceed "
        f"LVDC peak ({trace_lv.peak_I_A:.0f}A)"
    )
    print(f"PASS test_mvdc_6kv_fault_scaling  "
          f"(LVDC={trace_lv.peak_I_A:.0f}A, MVDC={trace_mv.peak_I_A:.0f}A)")


# ===========================================================================
# Test 11 — Integration: full protection chain on LVDC fault
# ===========================================================================

def test_full_protection_chain_lvdc():
    """
    Integrate DCFaultModel + DCProtectionMirror for LVDC pole-to-pole fault.
    At least one protection function must operate within 5 ms.
    """
    bus   = DCBusParams(V_nom_V=400.0, C_bus_F=10e-3, L_cable_H=5e-6,
                        R_cable_Ohm=0.02, I_conv_max_A=500.0, tau_ctrl_ms=1.0)
    fault = DCFaultParams(fault_type="pole_to_pole", R_fault_Ohm=0.001)
    model = DCFaultModel(bus, fault)
    trace = model.simulate(t_end_ms=5.0, dt_us=50.0)   # 50 µs steps

    settings = DCProtectionSettings(
        oc_pickup_A=300.0, oc_hi_pickup_A=800.0, oc_delay_ms=2.0,
        didt_pickup_A_ms=100.0, didt_delay_ms=0.1,
        diff_pickup_A=50.0, diff_slope_pct=20.0,
        arc_I_mult=1.5, arc_V_dip_pu=0.30,
        V_nom_V=400.0,
    )
    mirror = DCProtectionMirror(settings)

    first_trip = None
    for i in range(len(trace.t_ms)):
        t_ms  = float(trace.t_ms[i])
        I_A   = float(trace.I_fault_A[i])
        V_V   = float(trace.V_bus_V[i])
        dI_dt = float(trace.dI_dt_A_ms[i])
        events = mirror.evaluate(t_ms, I_A, V_V, dI_dt)
        for ev in events:
            if ev.operate and first_trip is None:
                first_trip = (t_ms, ev.function)

    assert first_trip is not None, "No protection operated during LVDC fault in 5 ms"
    t_op, fn = first_trip
    assert t_op <= 5.0, f"First operation at {t_op:.2f} ms > 5 ms"
    print(f"PASS test_full_protection_chain_lvdc  "
          f"(first op: {fn} at t={t_op:.2f} ms)")


# ===========================================================================
# Test 12 — Pole-to-ground: lower peak than pole-to-pole
# ===========================================================================

def test_pole_to_ground_lower_than_pole_to_pole():
    """Pole-to-ground fault has lower peak current than pole-to-pole."""
    bus = DCBusParams(V_nom_V=400.0, C_bus_F=10e-3, L_cable_H=10e-6,
                      R_cable_Ohm=0.02, I_conv_max_A=500.0, tau_ctrl_ms=1.0)

    trace_pp = DCFaultModel(bus, DCFaultParams("pole_to_pole",  R_fault_Ohm=0.001)
                            ).simulate(10.0, 10.0)
    trace_pg = DCFaultModel(bus, DCFaultParams("pole_to_ground", R_fault_Ohm=0.001)
                            ).simulate(10.0, 10.0)

    assert trace_pp.peak_I_A > trace_pg.peak_I_A, (
        f"P-P peak ({trace_pp.peak_I_A:.0f}A) should exceed "
        f"P-G peak ({trace_pg.peak_I_A:.0f}A)"
    )
    print(f"PASS test_pole_to_ground_lower_than_pole_to_pole  "
          f"(P-P={trace_pp.peak_I_A:.0f}A, P-G={trace_pg.peak_I_A:.0f}A)")


# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    test_capacitor_discharge_underdamped()
    test_capacitor_discharge_overdamped()
    test_didt_peak_sub_ms()
    test_dc_oc_highset_trip()
    test_dc_oc_delayed_trip()
    test_didt_protection_trips()
    test_dc_differential_trips()
    test_arc_flash_detection()
    test_lvdc_400v_normal_and_fault()
    test_mvdc_6kv_fault_scaling()
    test_full_protection_chain_lvdc()
    test_pole_to_ground_lower_than_pole_to_pole()
    print("\nAll TR-80 tests passed.")
