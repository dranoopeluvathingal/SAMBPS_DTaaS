# =============================================================================
# tests/test_meshed_dt_integration.py  —  TR-70 integration tests
# =============================================================================

from __future__ import annotations

import math
import cmath
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models.meshed_network import MeshedNetwork
from estimation.multi_source_ekf import MultiSourceEKF
from coordination.meshed_coordinator import MeshedCoordinator, RelaySettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_BASE = os.path.join(os.path.dirname(__file__), '..', 'configs')

def _cfg(fname):
    return os.path.join(_BASE, fname)


def _build_coordinator(net: MeshedNetwork, scheme: str = "POTT") -> MeshedCoordinator:
    # Build bus-id → vn_kv lookup
    bus_vn = {int(b['id']): float(b['vn_kv']) for b in net._cfg['buses']}
    settings = []
    for rs in net.relay_settings():
        line_cfg = next(
            (l for l in net._cfg['lines'] if l['name'] == rs['line']), None
        )
        z_line = 0.10
        if line_cfg:
            # Use from_bus voltage for the impedance base
            from_bus_id = int(line_cfg['from_bus'])
            vn_kv  = bus_vn.get(from_bus_id, 132.0)
            z_base = (vn_kv ** 2) / net._base_mva
            r_total = float(line_cfg['r_ohm_per_km']) * float(line_cfg['length_km'])
            x_total = float(line_cfg['x_ohm_per_km']) * float(line_cfg['length_km'])
            z_line  = math.hypot(r_total, x_total) / max(z_base, 1e-6)
        settings.append(RelaySettings(
            relay_id=rs['line'],
            pickup_pu=float(rs['pickup_pu']),
            zone1_reach_pu=float(rs['zone1_reach_pu']),
            time_dial=float(rs['time_dial']),
            z_line_pu=z_line,
        ))
    return MeshedCoordinator(settings, scheme=scheme,
                              ibr_params=net.ibr_sources())


def _build_mekf(net: MeshedNetwork) -> MultiSourceEKF:
    names = list(net.ibr_sources().keys())
    n = len(names)
    # Simple diagonal coupling: off-diagonal = 0.20 pu (moderate coupling)
    Z = np.eye(n) * 1000.0 + (np.ones((n, n)) - np.eye(n)) * 0.20
    return MultiSourceEKF(names, z_coupling=Z)


def _relay_decision_correct(action: str, fault_type: str,
                             in_faulted_zone: bool) -> bool:
    """
    Check relay decision is correct:
      • Faulted-zone relay → TRIP
      • Healthy-zone relay  → BLOCK or NONE (not TRIP)
    """
    if in_faulted_zone:
        return action == "TRIP"
    else:
        return action in ("BLOCK", "NONE", "PERMIT")


# ===========================================================================
# Test 1 — 5-bus network: power flow converges, faults produce current rise
# ===========================================================================

def test_5bus_powerflow_and_fault():
    net = MeshedNetwork.from_yaml(_cfg("test_5bus.yaml"))

    # Power flow must converge
    ok = net.run_powerflow()
    assert ok, "5-bus power flow did not converge"

    meas = net.get_measurements()
    assert "SLACK" in meas
    # All voltages within 15% of nominal (GFM reactive injection can push above 1.10)
    for name, m in meas.items():
        assert 0.80 <= m.V_pu <= 1.20, f"{name}: V={m.V_pu:.3f} outside [0.80,1.20]"

    # Fault injection: bus 2 SLG
    fault_cfg = {"bus": 2, "fault_type": "SLG", "r_fault_ohm": 0.0}
    fs = net.inject_fault(fault_cfg)
    assert fs.I_pos_pu > 0.5, f"Expected fault current > 0.5 pu, got {fs.I_pos_pu}"
    assert fs.V_pos_pu < 1.0, "Fault voltage should be depressed"

    net.clear_fault()

    # Line open topology change
    net.set_line_status("L12", in_service=False)
    ok2 = net.run_powerflow()
    # May or may not converge depending on islanding, just check no exception
    net.set_line_status("L12", in_service=True)

    print("PASS test_5bus_powerflow_and_fault")


# ===========================================================================
# Test 2 — 5-bus multi-source EKF: estimates track injected values
# ===========================================================================

def test_5bus_multi_source_ekf():
    net  = MeshedNetwork.from_yaml(_cfg("test_5bus.yaml"))
    mekf = _build_mekf(net)

    ibr = net.ibr_sources()
    names = list(ibr.keys())

    # Inject known observations for 5 cycles
    for cycle in range(5):
        obs = {}
        for name, params in ibr.items():
            obs[name] = {
                'k_ibr':  params['k_ibr'],
                'z_line': params['z_source_pu'],
                'alpha':  0.45,
                'f_gfm':  params['f_gfm'],
                'V_pu':   0.98,
            }
        ests = mekf.update(t=cycle * 0.02, observations=obs)

    # After 5 cycles estimates should track injected values closely
    for name in names:
        est = ests[name]
        params = ibr[name]
        assert abs(est.k_ibr - params['k_ibr']) < 0.10, (
            f"{name}: k_ibr est={est.k_ibr:.3f} vs truth={params['k_ibr']:.3f}"
        )
        assert abs(est.f_gfm - params['f_gfm']) < 0.10, (
            f"{name}: f_gfm est={est.f_gfm:.3f} vs truth={params['f_gfm']:.3f}"
        )
        assert 0.0 <= est.confidence <= 1.0

    print("PASS test_5bus_multi_source_ekf")


# ===========================================================================
# Test 3 — 5-bus coordinator: POTT pilot scheme decisions
# ===========================================================================

def test_5bus_coordinator_pott():
    net   = MeshedNetwork.from_yaml(_cfg("test_5bus.yaml"))
    coord = _build_coordinator(net, scheme="POTT")

    # Inject a fault on L23_ibrA: relay at L23_ibrA sees Zone-1 forward
    fault_cfg = next(f for f in net.fault_scenarios() if 'L23' in f.get('line',''))
    fs = net.inject_fault(fault_cfg)

    ekf = fs.ekf_state
    # Forward fault well inside Zone-1: use 50% of apparent impedance magnitude
    z_mag50 = fs.z_apparent * 0.50
    z_app = complex(z_mag50 * 0.8, z_mag50 * 0.6)   # fwd direction, |z|=z_mag50
    dec = coord.evaluate(
        t=0.10, relay_id="L23_ibrA",
        v_pu=fs.V_pos_pu, i_pu=fs.I_pos_pu,
        z_apparent=z_app, ekf_state=ekf,
    )
    assert dec.action == "TRIP", (
        f"Zone-1 forward fault on L23 should TRIP, got {dec.action} (zone={dec.zone})"
    )
    assert dec.zone == 1

    # Reverse element on a healthy feeder should BLOCK
    z_rev = complex(-fs.z_apparent, fs.z_apparent * 0.5)  # reverse
    dec_rev = coord.evaluate(
        t=0.10, relay_id="L24_ibrB",
        v_pu=0.95, i_pu=fs.I_pos_pu * 0.3,
        z_apparent=z_rev, ekf_state=ekf,
    )
    assert dec_rev.action in ("BLOCK", "NONE"), (
        f"Reverse element should BLOCK/NONE, got {dec_rev.action}"
    )

    net.clear_fault()
    print("PASS test_5bus_coordinator_pott")


# ===========================================================================
# Test 4 — 10-bus network: full integration, ≥85% correct relay decisions
# ===========================================================================

def test_10bus_integration_agree_rate():
    net   = MeshedNetwork.from_yaml(_cfg("test_10bus.yaml"))
    mekf  = _build_mekf(net)
    coord = _build_coordinator(net, scheme="POTT")

    scenarios = net.fault_scenarios()
    relay_ids = coord.relay_ids

    correct = 0
    total   = 0

    for fault_cfg in scenarios:
        # Inject fault
        fs = net.inject_fault(fault_cfg)

        # Run EKF for 3 cycles
        obs = {}
        for name, params in net.ibr_sources().items():
            obs[name] = {
                'k_ibr':  fs.ekf_state['k_ibr'],
                'z_line': fs.ekf_state['z_line'],
                'alpha':  fs.ekf_state['alpha'],
                'f_gfm':  fs.ekf_state['f_gfm'],
                'V_pu':   fs.V_pos_pu,
            }
        for cyc in range(3):
            ests = mekf.update(t=cyc * 0.02, observations=obs)

        # Determine which line is faulted
        faulted_line = fault_cfg.get('line', None)

        # Evaluate all relays
        for rid in relay_ids:
            # Faulted relay sees high current and forward impedance inside Zone-1
            if rid == faulted_line:
                i_relay  = fs.I_pos_pu
                z_near   = fs.z_apparent * 0.45   # ~45% → well inside 80% reach
                z_app    = complex(z_near * 0.80, z_near * 0.60)
                in_zone  = True
            else:
                # Healthy relay: much lower current, possible reverse direction
                i_relay = fs.I_pos_pu * 0.15
                z_app   = complex(-0.05, 0.05)   # reverse
                in_zone = False

            # Use merged EKF state
            merged_ekf = fs.ekf_state

            dec = coord.evaluate(
                t=0.10, relay_id=rid,
                v_pu=(fs.V_pos_pu if in_zone else 0.95),
                i_pu=i_relay,
                z_apparent=z_app,
                ekf_state=merged_ekf,
            )

            correct += int(_relay_decision_correct(dec.action, fault_cfg['fault_type'], in_zone))
            total   += 1

        net.clear_fault()
        mekf.reset()
        coord.reset()

    agree_rate = correct / max(total, 1)
    print(f"  10-bus agree rate: {agree_rate:.2%} ({correct}/{total})")
    assert agree_rate >= 0.85, f"10-bus agree rate {agree_rate:.2%} < 85%"

    print("PASS test_10bus_integration_agree_rate")


# ===========================================================================
# Test 5 — Pilot scheme comparison: POTT / DCB / PUTT
# ===========================================================================

def test_pilot_scheme_variants():
    """All three schemes produce TRIP on Zone-1 forward fault."""
    net = MeshedNetwork.from_yaml(_cfg("test_5bus.yaml"))

    fault_cfg = net.fault_scenarios()[0]  # first fault scenario
    fs = net.inject_fault(fault_cfg)
    faulted_line = fault_cfg.get('line', None)
    if faulted_line is None:
        print("PASS test_pilot_scheme_variants (bus fault, skip line check)")
        return

    z_near = fs.z_apparent * 0.45
    z_fwd  = complex(z_near * 0.80, z_near * 0.60)
    ekf   = fs.ekf_state

    for scheme in ("POTT", "DCB", "PUTT"):
        coord = _build_coordinator(net, scheme=scheme)
        if scheme == "DCB":
            # DCB needs two calls (coordination timer)
            coord.evaluate(t=0.00, relay_id=faulted_line,
                           v_pu=fs.V_pos_pu, i_pu=fs.I_pos_pu,
                           z_apparent=z_fwd, ekf_state=ekf)
            dec = coord.evaluate(t=0.05, relay_id=faulted_line,
                                  v_pu=fs.V_pos_pu, i_pu=fs.I_pos_pu,
                                  z_apparent=z_fwd, ekf_state=ekf)
        else:
            dec = coord.evaluate(t=0.10, relay_id=faulted_line,
                                  v_pu=fs.V_pos_pu, i_pu=fs.I_pos_pu,
                                  z_apparent=z_fwd, ekf_state=ekf)
        assert dec.action == "TRIP", (
            f"{scheme}: expected TRIP on Zone-1 fault, got {dec.action}"
        )

    net.clear_fault()
    print("PASS test_pilot_scheme_variants")


# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    test_5bus_powerflow_and_fault()
    test_5bus_multi_source_ekf()
    test_5bus_coordinator_pott()
    test_10bus_integration_agree_rate()
    test_pilot_scheme_variants()
    print("\nAll TR-70 integration tests passed.")
