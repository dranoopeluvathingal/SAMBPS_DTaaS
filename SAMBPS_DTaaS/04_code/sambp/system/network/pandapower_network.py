"""
pandapower_network.py
======================
Pandapower-based radial network model for TR-08 v2 Monte Carlo study.

Topology mirrors radial_network.py (analytical model) but uses pandapower
power flow and IEC 60909 short-circuit analysis to derive physically
correct fault parameters:
  - Fault current magnitudes per location (3-phase and A-G)
  - Thevenin X/R ratio → DC time constant per fault location
  - Pre-fault bus voltages from AC power flow

Network topology:
    slack ─ Z_src ─ [Bus_A] ─ Z_line/2 ─ [Bus_mid] ─ Z_line/2 ─ [Bus_B]
                                                                       │
                                                                    Xfmr
                                                                       │
                                                                  [Bus_C (load)]

System base: 100 MVA, 33 kV (HV) / 11 kV (LV).
R/X = 0.0637 for all series elements → τ_dc = X/R/(2πf) ≈ 50 ms.
(Matches the hardcoded τ = 0.05 s in the analytical radial_network.py.)

Per-unit impedances (same as radial_network.py):
    Z_src  = j0.10   (generator + source impedance)
    Z_line = j0.05   (overhead line, split at midpoint for fault location)
    Z_tr   = j0.08   (transformer leakage, HV/LV = 33/11 kV)
    Z_load = 2.00    (resistive load at Bus_C, ≈ 50 MW at 100 MVA base)
"""

from __future__ import annotations

import numpy as np
import pandapower as pp
import pandapower.shortcircuit as sc

# ---------------------------------------------------------------------------
# System base
# ---------------------------------------------------------------------------

SBASE_MVA = 100.0
VN_HV_KV  = 33.0
VN_LV_KV  = 11.0
F_HZ      = 50.0
RX_RATIO  = 0.0637  # R/X for all elements → τ ≈ 50 ms

# Per-unit impedances (match radial_network.py)
Z_SRC_X_PU  = 0.10   # X only [pu]
Z_LINE_X_PU = 0.05   # X only [pu]
Z_TR_X_PU   = 0.08   # X only [pu]
Z_LOAD_PU   = 2.00   # purely resistive [pu]

Z_BASE_HV = VN_HV_KV**2 / SBASE_MVA   # 10.89 Ω
Z_BASE_LV = VN_LV_KV**2 / SBASE_MVA   #  1.21 Ω

I_BASE_HV_A = SBASE_MVA * 1e6 / (np.sqrt(3) * VN_HV_KV * 1e3)  # 1749.6 A
I_BASE_LV_A = SBASE_MVA * 1e6 / (np.sqrt(3) * VN_LV_KV * 1e3)  # 5248.6 A

FAULT_LOCATIONS = [
    "bus_A",
    "line_mid",
    "bus_B",
    "transformer_hv",
    "bus_C_load",
]


# ---------------------------------------------------------------------------
# Network builder
# ---------------------------------------------------------------------------

def build_pandapower_network():
    """
    Build the radial test network in pandapower.

    Returns
    -------
    net : pandapowerNet
    bus_idx : dict mapping fault location name → pandapower bus index
    """
    net = pp.create_empty_network(f_hz=F_HZ, sn_mva=SBASE_MVA)

    # --- Buses ---
    b_sl  = pp.create_bus(net, vn_kv=VN_HV_KV, name='slack')
    b_A   = pp.create_bus(net, vn_kv=VN_HV_KV, name='bus_A')
    b_mid = pp.create_bus(net, vn_kv=VN_HV_KV, name='bus_mid')
    b_B   = pp.create_bus(net, vn_kv=VN_HV_KV, name='bus_B')
    b_C   = pp.create_bus(net, vn_kv=VN_LV_KV, name='bus_C')

    # --- External grid: stiff voltage source behind essentially zero impedance ---
    # The source impedance Z_src is explicitly modeled as a line below.
    pp.create_ext_grid(
        net, bus=b_sl, vm_pu=1.0,
        s_sc_max_mva=1e6, rx_max=1e-4,
        name='generator'
    )

    # --- Z_src: slack → bus_A  (X_pu = 0.10) ---
    X_src_ohm = Z_SRC_X_PU * Z_BASE_HV            # 1.089 Ω
    R_src_ohm = RX_RATIO * X_src_ohm               # 0.0694 Ω
    pp.create_line_from_parameters(
        net, from_bus=b_sl, to_bus=b_A, length_km=1.0,
        r_ohm_per_km=R_src_ohm, x_ohm_per_km=X_src_ohm,
        c_nf_per_km=0.0, max_i_ka=100.0, name='Z_src'
    )

    # --- Z_line/2: bus_A → bus_mid  (X_pu = 0.025 each half) ---
    X_lh_ohm = (Z_LINE_X_PU / 2.0) * Z_BASE_HV    # 0.2723 Ω per half
    R_lh_ohm = RX_RATIO * X_lh_ohm                 # 0.01734 Ω per half
    pp.create_line_from_parameters(
        net, from_bus=b_A, to_bus=b_mid, length_km=1.0,
        r_ohm_per_km=R_lh_ohm, x_ohm_per_km=X_lh_ohm,
        c_nf_per_km=0.0, max_i_ka=100.0, name='Z_line_near'
    )
    pp.create_line_from_parameters(
        net, from_bus=b_mid, to_bus=b_B, length_km=1.0,
        r_ohm_per_km=R_lh_ohm, x_ohm_per_km=X_lh_ohm,
        c_nf_per_km=0.0, max_i_ka=100.0, name='Z_line_far'
    )

    # --- Transformer: bus_B → bus_C  (Z_tr: X_pu = 0.08) ---
    R_tr_pu = RX_RATIO * Z_TR_X_PU                 # 0.005096 pu
    vk_pct  = np.sqrt(Z_TR_X_PU**2 + R_tr_pu**2) * 100   # ≈ 8.016 %
    vkr_pct = R_tr_pu * 100                        # ≈ 0.5096 %
    pp.create_transformer_from_parameters(
        net,
        hv_bus=b_B, lv_bus=b_C,
        sn_mva=SBASE_MVA,
        vn_hv_kv=VN_HV_KV, vn_lv_kv=VN_LV_KV,
        vkr_percent=vkr_pct, vk_percent=vk_pct,
        pfe_kw=0.0, i0_percent=0.0,
        shift_degree=0.0,
        name='Z_tr'
    )

    # --- Load at bus_C: Z_load = 2.00 pu → P = 50 MW ---
    P_load_mw = (1.0 / Z_LOAD_PU) * SBASE_MVA      # 50 MW
    pp.create_load(net, bus=b_C, p_mw=P_load_mw, q_mvar=0.0, name='load')

    bus_idx = {
        'bus_A':          b_A,
        'line_mid':       b_mid,
        'bus_B':          b_B,
        'transformer_hv': b_B,   # HV terminal = bus_B in pandapower model
        'bus_C_load':     b_C,
    }

    return net, bus_idx


# ---------------------------------------------------------------------------
# Fault parameter computation
# ---------------------------------------------------------------------------

def compute_fault_parameters() -> dict:
    """
    Run AC power flow + IEC 60909 three-phase SC analysis and return
    fault parameters at each of the five fault locations.

    Returns
    -------
    dict keyed by fault location name.  Each value is a dict:
        I_f_pu_3ph  : three-phase fault current [pu on HV/LV base]
        I_f_pu_ag   : A-phase-to-ground fault current [pu]  (= 0.6 × 3ph)
        tau_dc_s    : DC time constant [s] = xk / (rk × 2π × f)
        XR_ratio    : Thevenin X/R at fault point
        V_pre_pu    : pre-fault bus voltage magnitude [pu]
        I_base_A    : current base at this bus voltage level [A]
    """
    net, bus_idx = build_pandapower_network()

    # --- Power flow (for pre-fault voltages) ---
    pp.runpp(net, numba=False, verbose=False)
    V_pre_map = dict(zip(net.bus.index, net.res_bus['vm_pu'].values))

    # --- Three-phase SC analysis ---
    sc.calc_sc(net, fault='3ph', case='max')
    res_sc = net.res_bus_sc   # DataFrame, index = bus idx

    params = {}
    seen_buses = {}  # avoid duplicate SC lookups for transformer_hv / bus_B

    for loc in FAULT_LOCATIONS:
        bidx   = bus_idx[loc]
        vn_kv  = float(net.bus.at[bidx, 'vn_kv'])
        I_base = SBASE_MVA * 1e6 / (np.sqrt(3) * vn_kv * 1e3)  # A

        row     = res_sc.loc[bidx]
        ikss_ka = float(row['ikss_ka'])
        rk_ohm  = float(row['rk_ohm'])
        xk_ohm  = float(row['xk_ohm'])

        I_f_pu_3ph = (ikss_ka * 1e3) / I_base
        XR         = xk_ohm / rk_ohm if rk_ohm > 1e-12 else 999.0
        tau_dc     = xk_ohm / (rk_ohm * 2 * np.pi * F_HZ) if rk_ohm > 1e-12 else 0.05

        params[loc] = {
            'I_f_pu_3ph': I_f_pu_3ph,
            'I_f_pu_ag':  I_f_pu_3ph * 0.6,
            'tau_dc_s':   tau_dc,
            'XR_ratio':   XR,
            'V_pre_pu':   float(V_pre_map.get(bidx, 1.0)),
            'I_base_A':   I_base,
        }

    return params


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    params = compute_fault_parameters()

    print(f"\nPandapower network fault parameters (100 MVA, 33/11 kV base)\n")
    print(f"{'Location':<20} {'I_f_3ph':>9} {'I_f_AG':>9} "
          f"{'τ_dc (ms)':>11} {'X/R':>8} {'V_pre':>8}")
    print('-' * 72)
    for loc, p in params.items():
        print(f"  {loc:<18} {p['I_f_pu_3ph']:>9.3f}  {p['I_f_pu_ag']:>9.3f} "
              f"{p['tau_dc_s']*1000:>11.2f} {p['XR_ratio']:>8.2f} "
              f"{p['V_pre_pu']:>8.4f}")

    # --- Compare to analytical network ---
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from radial_network import fault_current_phasor, FAULT_LOCATIONS as FL

    print(f"\nAnalytical network comparison (hardcoded τ = 50 ms):")
    print(f"{'Location':<20} {'I_f_3ph':>9} {'I_f_AG':>9}")
    print('-' * 45)
    for loc in FL:
        I_3ph = abs(fault_current_phasor(loc, '3ph'))
        I_ag  = abs(fault_current_phasor(loc, 'ag'))
        print(f"  {loc:<18} {I_3ph:>9.3f}  {I_ag:>9.3f}")
