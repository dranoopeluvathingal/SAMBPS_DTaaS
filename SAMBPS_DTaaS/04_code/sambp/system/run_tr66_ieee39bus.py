"""
run_tr66_ieee39bus.py
======================
TR-66/2026 — IEEE 39-Bus Full-System SAMBP Coordination Validation
Chapter 7: System Integration

Nine protection functions deployed on a protection corridor extracted from the
IEEE 39-Bus New England test system (pandapower case39):

    Gen G9 ─── Bus39 ─── Line39-9 ─── Bus9
    (51G,87G)  (87B)   (87L,87LN,87LN0,TDCS)

    + Transformer Bus10→Bus32 (87T)
    + Line Bus8-Bus9 (21 Mho distance, backup)

Nine functions:
    1.  51G   — Generator G9 overcurrent
    2.  87G   — Generator G9 differential (stator ↔ HV terminal)
    3.  87B   — Bus 39 differential (3 feeders: G9 + Line1-39 + Line9-39)
    4.  87L   — Line 9-39 differential (positive-sequence, SAMBP pipeline)
    5.  87LN  — Line 9-39 negative-sequence differential (threshold)
    6.  87LN0 — Line 9-39 zero-sequence differential (threshold)
    7.  TDCS  — Adaptive IBR threshold on Line 9-39
    8.  87T   — Transformer Bus10-Bus32 differential (SAMBP pipeline)
    9.  21    — Line 8-9 Mho distance relay (three zones)

Twelve scenarios covering all protection zones:
    1.  normal_load        — pre-fault load flow only (all no-trip)
    2.  bus39_3ph          — Bus39 bolted 3-phase: 87B
    3.  bus39_ag           — Bus39 A-G: 87B
    4.  gen_stator_3ph     — Gen G9 stator internal 3-phase: 51G + 87G
    5.  line9_39_3ph       — Line9-39 midpoint 3-phase: 87L + TDCS
    6.  line9_39_ag        — Line9-39 midpoint A-G: 87L + 87LN + 87LN0 + TDCS
    7.  line9_39_ibr       — Line9-39 IBR 3-phase (k_ibr=0.08 pu): TDCS only
    8.  bus9_ext_3ph       — Bus9 3-phase (external to all differential): none
    9.  line8_9_z1         — Line8-9 at 40% (Zone1 instant): 21
   10.  line8_9_ext        — Line8-9 at 130% (Zone3 delayed, not instant): none
   11.  trafo_int_3ph      — Trafo Bus10-Bus32 internal 3-phase: 87T
   12.  trafo_ext_3ph      — Bus32 fault (external to transformer zone): none

Expected: 12/12 correct (100 % selectivity).
"""

from __future__ import annotations

import sys, os, csv
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup — load SAMBP relay modules via _load() pattern
# ---------------------------------------------------------------------------
_HERE   = os.path.dirname(os.path.abspath(__file__))
_SAMBP  = os.path.dirname(_HERE)          # .../sambp/
_DIST   = os.path.join(_SAMBP, "distance")

sys.path.insert(0, _HERE)
sys.path.insert(0, _SAMBP)
sys.path.insert(0, _DIST)

import importlib.util as _il_util

def _load(proj: str, subpkg: str, modname: str):
    proj_root = os.path.join(_SAMBP, proj)
    qualname  = f"_tr66.{proj}.{subpkg}.{modname}"
    if qualname in sys.modules:
        return sys.modules[qualname]
    for key in [k for k in sys.modules if k == "models" or k.startswith("models.")]:
        del sys.modules[key]
    if proj_root in sys.path:
        sys.path.remove(proj_root)
    sys.path.insert(0, proj_root)
    path = os.path.join(proj_root, subpkg, modname + ".py")
    spec = _il_util.spec_from_file_location(qualname, path)
    mod  = _il_util.module_from_spec(spec)
    sys.modules[qualname] = mod
    spec.loader.exec_module(mod)
    for key in [k for k in sys.modules if k == "models" or k.startswith("models.")]:
        sys.modules[f"{proj}.{key}"] = sys.modules.pop(key)
    return mod

# 87B bus differential
_b_base = _load("bus_diff", "models",             "bus_diff_baseline")
_b_est  = _load("bus_diff", "inverse_estimation", "bus_inverse_estimator")
_b_gate = _load("bus_diff", "adaptation",         "bus_confidence_gate")

BusDiffRelayConfig           = _b_base.BusDiffRelayConfig
run_87B_relay                = _b_base.run_87B_relay
estimate_bus_zone_parameters = _b_est.estimate_bus_zone_parameters
BusGateConfig                = _b_gate.BusGateConfig
BusGateState                 = _b_gate.BusGateState
evaluate_87B_confidence_gate = _b_gate.evaluate_87B_confidence_gate

# 87L line differential
_l_base = _load("line_diff", "models",             "line_diff_baseline")
_l_est  = _load("line_diff", "inverse_estimation", "line_inverse_estimator")
_l_gate = _load("line_diff", "adaptation",         "line_confidence_gate")

LineDiffRelayConfig           = _l_base.LineDiffRelayConfig
run_87L_relay                 = _l_base.run_87L_relay
estimate_line_zone_parameters = _l_est.estimate_line_zone_parameters
LineConfidenceGateConfig      = _l_gate.LineConfidenceGateConfig
LineGateState                 = _l_gate.LineGateState
evaluate_87L_confidence_gate  = _l_gate.evaluate_87L_confidence_gate

# 87T transformer differential
_t_base = _load("transformer_diff", "models",             "transformer_diff_baseline")
_t_est  = _load("transformer_diff", "inverse_estimation", "transformer_inverse_estimator")
_t_gate = _load("transformer_diff", "adaptation",         "transformer_confidence_gate")

TransformerRelayConfig   = _t_base.TransformerRelayConfig
run_87T_relay            = _t_base.run_87T_relay
_rated_current_H         = _t_base._rated_current_H
_rated_current_X         = _t_base._rated_current_X
compensate_winding       = _t_base.compensate_winding
_vector_group_matrix     = _t_base._vector_group_matrix
tr_estimate              = _t_est.estimate_zone_parameters
ConfidenceGateConfig     = _t_gate.ConfidenceGateConfig
GateState                = _t_gate.GateState
evaluate_confidence_gate = _t_gate.evaluate_confidence_gate

# 21 Mho distance relay (load directly, not via _load() — standalone module)
import importlib.util as _ilu_dist
_mho_spec = _ilu_dist.spec_from_file_location(
    "_tr66_mho",
    os.path.join(_DIST, "models", "mho_relay_model.py"),
)
_mho_mod = _ilu_dist.module_from_spec(_mho_spec)
sys.modules["_tr66_mho"] = _mho_mod
_mho_spec.loader.exec_module(_mho_mod)
MhoRelayConfig    = _mho_mod.MhoRelayConfig
MhoZoneState      = _mho_mod.MhoZoneState
MhoDecision       = _mho_mod.MhoDecision
evaluate_mho_zone = _mho_mod.evaluate_mho_zone
measure_impedance_3ph = _mho_mod.measure_impedance_3ph

# ---------------------------------------------------------------------------
# IEEE 39-bus Z-bus computation
# ---------------------------------------------------------------------------
import pandapower          as pp
import pandapower.networks as pn
from pandapower.pd2ppc          import _pd2ppc
from pandapower.pypower.makeYbus import makeYbus
from pandapower.pypower.idx_bus  import VM, VA


def _build_ieee39():
    """Return (net, Z_bus_pu, V_pre_pu, ppc) for the IEEE 39-bus system."""
    net = pn.case39()
    pp.runpp(net, numba=False)
    ppc, _ = _pd2ppc(net)
    Ybus, _, _ = makeYbus(ppc["baseMVA"], ppc["bus"], ppc["branch"])
    Y = Ybus.toarray()
    Z = np.linalg.inv(Y)
    V_pre = (ppc["bus"][:, VM]
             * np.exp(1j * np.deg2rad(ppc["bus"][:, VA])))
    return net, Z, V_pre, ppc


def _bus_fault(k: int, Z, V_pre) -> tuple[complex, np.ndarray]:
    """Bolted 3-phase fault at bus k.  Returns (I_f_pu, V_fault_pu_array)."""
    Zth  = Z[k, k]
    I_f  = V_pre[k] / Zth
    V_f  = V_pre - Z[:, k] * I_f
    return I_f, V_f


def _line_current(from_idx: int, to_idx: int, V_fault, net) -> complex:
    """Current flowing from from_idx → to_idx during a fault [pu]."""
    rows = net.line[
        ((net.line.from_bus == from_idx) & (net.line.to_bus == to_idx)) |
        ((net.line.from_bus == to_idx)   & (net.line.to_bus == from_idx))
    ]
    row   = rows.iloc[0]
    fb    = row.from_bus; tb = row.to_bus
    Z_ohm = (row.r_ohm_per_km + 1j * row.x_ohm_per_km) * row.length_km
    vbase = net.bus.iloc[fb].vn_kv * 1e3        # V
    Zbase = vbase**2 / (100e6)                  # 100 MVA base
    Z_pu  = Z_ohm / Zbase
    # Current from_bus → to_bus
    I_fb_tb = (V_fault[fb] - V_fault[tb]) / Z_pu
    if fb == from_idx:
        return I_fb_tb
    else:
        return -I_fb_tb                          # flip direction


# ---------------------------------------------------------------------------
# Time-domain constants
# ---------------------------------------------------------------------------
FREQ_HZ  = 50.0      # relay calibration frequency (SAMBP framework is 50 Hz)
FS_HZ    = 1000.0
DT       = 1.0 / FS_HZ
T_WINDOW = 0.060     # 60 ms window (pre + fault)
N_SAMP   = int(T_WINDOW * FS_HZ)           # 60 samples
T        = np.arange(N_SAMP) * DT
OMEGA    = 2.0 * np.pi * FREQ_HZ
T_FAULT  = 0.020     # fault inception at 20 ms
F_IDX    = int(T_FAULT * FS_HZ)            # = 20
K_DC     = 1.6       # IEC 60909 DC factor

# Protection zone constants
I_BUS_RATED = 1.0    # pu (already normalised)
I_OC_PICKUP = 2.5    # pu — generator overcurrent pickup
I87G_PICKUP = 0.10   # pu — generator differential pickup (slope=0.15)
I87G_SLOPE  = 0.15

# Sequence thresholds (from TR-27/2026)
I2_THR      = 0.06   # pu negative-seq 87LN
I0_THR      = 0.04   # pu zero-seq 87LN0

# TDCS parameters (from TR-27/2026)
K_SIGMA     = 3.0
NOISE_FLR   = 0.010
DELTA_FLOOR = 0.025

# Mho distance relay — Line 8-9 (internal idx 7→8, Ohm params)
# Z_line8_9 = (2.7376 + 43.2061j) Ohm/km × 1 km; Zbase at 345 kV, 100 MVA
_Z_LINE89_OHM = (2.7376 + 43.2061j) * 1.0    # 1 km line
_ZBASE_345    = 345e3**2 / 100e6               # = 1190.25 Ω
Z_LINE89_PU   = _Z_LINE89_OHM / _ZBASE_345    # ≈ 0.0023 + 0.0363j pu
MHO_CFG       = MhoRelayConfig(Z_line=Z_LINE89_PU, MTA_deg=80.0,
                                zone1_pct=0.80, zone2_pct=1.20, zone3_pct=1.80,
                                t_zone2=0.30, t_zone3=0.60, R_blinder=0.40)

# Transformer relay config (Trafo Bus10→Bus32, sn_mva=900, vk=18%)
#   I_H_rated = 900 / (√3 × 345) = 1.506 kA → CT ratio 2000:5 → I_H_ref
#   Using default TransformerRelayConfig (230 kV / 115 kV base)
#   We scale pu currents to Amperes for the 87T pipeline
CFG_T = TransformerRelayConfig()
I_H_REF = _rated_current_H(CFG_T)
I_X_REF = _rated_current_X(CFG_T)


# ---------------------------------------------------------------------------
# Waveform synthesis helpers
# ---------------------------------------------------------------------------

def _phasor_to_wave3ph(phasor_pu: complex, tau_dc: float) -> np.ndarray:
    """
    3-phase balanced waveform from a positive-seq phasor.
    Returns shape (3, N_SAMP).  Phases = [0, -2π/3, +2π/3].
    DC offset uses physics-correct sign: dc_coeff = -sin(θ) × K_DC.
    """
    I_pk  = np.sqrt(2) * abs(phasor_pu)
    theta = np.angle(phasor_pu) + np.pi / 2   # cos→sin
    phases = np.array([0.0, -2 * np.pi / 3, 2 * np.pi / 3])
    wave = np.zeros((3, N_SAMP))
    for ph in range(3):
        th_ph = theta + phases[ph]
        dc    = -np.sin(th_ph) * K_DC
        t_rel = T[F_IDX:] - T_FAULT
        wave[ph, F_IDX:] = I_pk * (
            np.sin(OMEGA * t_rel + th_ph) + dc * np.exp(-t_rel / tau_dc)
        )
        # pre-fault: zero (relay starts from fault inception)
    return wave


def _phasor_to_wave_ag(phasor_a_pu: complex, tau_dc: float) -> np.ndarray:
    """
    A-G fault: only phase A carries fault current; phases B,C = 0.
    Returns shape (3, N_SAMP).
    """
    wave = np.zeros((3, N_SAMP))
    I_pk  = np.sqrt(2) * abs(phasor_a_pu)
    theta = np.angle(phasor_a_pu) + np.pi / 2
    dc    = -np.sin(theta) * K_DC
    t_rel = T[F_IDX:] - T_FAULT
    wave[0, F_IDX:] = I_pk * (
        np.sin(OMEGA * t_rel + theta) + dc * np.exp(-t_rel / tau_dc)
    )
    return wave


def _load_wave3ph(load_pu: float) -> np.ndarray:
    """Sinusoidal load current (no DC).  Returns shape (3, N_SAMP)."""
    I_pk  = np.sqrt(2) * load_pu
    phases = np.array([0.0, -2 * np.pi / 3, 2 * np.pi / 3])
    wave = np.zeros((3, N_SAMP))
    for ph in range(3):
        wave[ph, :] = I_pk * np.sin(OMEGA * T + phases[ph])
    return wave


# ---------------------------------------------------------------------------
# Relay evaluation helpers
# ---------------------------------------------------------------------------

def _run_51G(i_gen_wave: np.ndarray) -> tuple[bool, float]:
    """Simple overcurrent: trip if any-phase peak > I_OC_PICKUP."""
    I_pk = float(np.max(np.abs(i_gen_wave)))
    return I_pk > I_OC_PICKUP, I_pk


def _run_87G(i_stator: np.ndarray, i_hv: np.ndarray) -> tuple[bool, float, float]:
    """
    Generator differential (simplified slope characteristic):
        I_op  = |sum of stator + HV per phase, taken as phase-A peak|
        I_rst = 0.5 × (|I_stator| + |I_HV|) peak
    Trip if I_op > max(I87G_PICKUP, I87G_SLOPE × I_rst).
    Returns (trip, I_op_pu, I_rst_pu).
    """
    i_op_ph  = np.abs(i_stator + i_hv)        # shape (3, N)
    i_rst_ph = 0.5 * (np.abs(i_stator) + np.abs(i_hv))
    I_op  = float(i_op_ph.max())
    I_rst = float(i_rst_ph.max())
    thresh = max(I87G_PICKUP, I87G_SLOPE * I_rst)
    return I_op > thresh, I_op, I_rst


def _run_87B(t, feeders: list, n_feeders: int) -> tuple[bool, str, float, float, float, float]:
    """
    Full SAMBP 87B pipeline.
    Returns (final_trip, gate_action, I_op_pk, I_rst_pk, kappa_n, f_int).
    """
    cfg_B = BusDiffRelayConfig(n_feeders=n_feeders, I_bus_rated_A=I_BUS_RATED)
    dec   = run_87B_relay(t, feeders, cfg_B)
    conv  = dec.t_trip_s is not None
    I_op  = float(dec.I_op.max())
    I_rst = float(dec.I_rst.max())

    i_diff = sum(f[0] for f in feeders) / I_BUS_RATED   # phase A, pu
    est    = estimate_bus_zone_parameters(t, i_diff, freq_hz=FREQ_HZ)
    gs     = BusGateState()
    gate, _ = evaluate_87B_confidence_gate(
        est["state"], conv, BusGateConfig(n_confirm=1), gs
    )
    return gate.final_trip, gate.source, I_op, I_rst, est["kappa_n"], est["state"].f_int


def _run_87L(t, i_near: np.ndarray, i_far: np.ndarray) -> tuple[bool, str, float, float]:
    """Full SAMBP 87L pipeline.  Returns (final_trip, gate_action, I_op, kappa_n)."""
    cfg  = LineDiffRelayConfig(channel_delay_samples=0)
    dec  = run_87L_relay(t, i_near, i_far, cfg)
    conv = dec.t_trip_s is not None
    I_op = float(dec.I_op.max())

    i_diff = (i_near + i_far)[0] / I_BUS_RATED  # phase A pu
    est  = estimate_line_zone_parameters(t, i_diff, freq_hz=FREQ_HZ)
    gs   = LineGateState()
    gate, _ = evaluate_87L_confidence_gate(
        est["state"], conv, LineConfidenceGateConfig(), gs
    )
    return gate.final_trip, gate.source, I_op, est["kappa_n"]


def _run_87LN(I2_diff_pu: float) -> bool:
    """Negative-sequence line differential — simple threshold."""
    return I2_diff_pu > I2_THR


def _run_87LN0(I0_diff_pu: float) -> bool:
    """Zero-sequence line differential — simple threshold."""
    return I0_diff_pu > I0_THR


def _run_TDCS(i_diff_wave: np.ndarray) -> tuple[bool, float]:
    """
    Time-domain correlation selectivity (adaptive threshold):
        rms_pre  = RMS of |i_diff| in pre-fault window [0, F_IDX)
        rms_post = RMS of |i_diff| in post-fault window [F_IDX:)
        sigma    = std of pre-fault
        threshold = K_SIGMA × max(sigma, NOISE_FLR) + DELTA_FLOOR
        TDCS trips if rms_post > threshold
    Returns (trip, TDCS_indicator).
    """
    pre  = np.abs(i_diff_wave[:F_IDX])
    post = np.abs(i_diff_wave[F_IDX:])
    mu_pre   = float(np.mean(pre)) if len(pre) > 0 else 0.0
    sig_pre  = float(np.std(pre))  if len(pre) > 0 else NOISE_FLR
    rms_post = float(np.sqrt(np.mean(post**2)))
    thresh   = K_SIGMA * max(sig_pre, NOISE_FLR) + DELTA_FLOOR
    indicator = (rms_post - mu_pre) / max(sig_pre, NOISE_FLR)
    return rms_post > thresh, indicator


def _run_87T(t, i_H_pu: np.ndarray, i_X_pu: np.ndarray) -> tuple[bool, str, float, float]:
    """Full SAMBP 87T pipeline.  Returns (final_trip, gate_action, I_op, kappa_n)."""
    i_H_A = i_H_pu * I_H_REF
    i_X_A = i_X_pu * I_X_REF
    dec   = run_87T_relay(t, i_H_A, i_X_A, CFG_T)
    conv  = dec.t_trip_s is not None
    I_op  = float(dec.I_op.max())

    M_X   = _vector_group_matrix(CFG_T.vector_group)
    i_Hc  = compensate_winding(i_H_A, CFG_T.CT_ratio_H, I_H_REF, np.eye(3), 1.0)
    i_Xc  = compensate_winding(i_X_A, CFG_T.CT_ratio_X, I_X_REF, M_X, 1.0)
    i_diff = (i_Hc + i_Xc)[0]
    est   = tr_estimate(t, i_diff, freq_hz=FREQ_HZ)
    gs    = GateState()
    gate, _ = evaluate_confidence_gate(
        est["state"], conv, ConfidenceGateConfig(n_confirm=1), gs
    )
    return gate.final_trip, gate.source, I_op, est["kappa_n"]


def _run_21(Z_m: complex) -> tuple[bool, int, str]:
    """
    Instantaneous Mho evaluation.  Zone 2/3 timer is integrated with dt=t_zone
    so that Zone 2 trips if fault duration > t_zone2 (used for selectivity
    assessment but NOT counted as 'instant trip').
    Returns (inst_trip, zone, reason).
    """
    dec, _ = evaluate_mho_zone(Z_m, MHO_CFG, dt_s=MHO_CFG.t_zone2 + 0.001)
    inst   = dec.zone == 1
    return inst, dec.zone, dec.reason


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    sid:       str
    label:     str
    expected:  set[str]     # expected tripping relays (instantaneous)


SCENARIOS: list[Scenario] = [
    Scenario("normal_load",    "Normal load (no fault)",              set()),
    Scenario("bus39_3ph",      "Bus39 3-phase (ext gen, int bus)",     {"87B"}),
    Scenario("bus39_ag",       "Bus39 A-G (ext gen, int bus)",         {"87B"}),
    Scenario("gen_stator_3ph", "Gen G9 stator internal 3-phase",       {"51G", "87G"}),
    Scenario("line9_39_3ph",   "Line9-39 midpoint 3-phase",            {"87L", "TDCS"}),
    Scenario("line9_39_ag",    "Line9-39 midpoint A-G",                {"87L", "87LN", "87LN0", "TDCS"}),
    Scenario("line9_39_ibr",   "Line9-39 IBR 3-phase (k=0.08 pu)",    {"TDCS"}),
    Scenario("bus9_ext_3ph",   "Bus9 3-phase (external to all diff)",  set()),
    Scenario("line8_9_z1",     "Line8-9 at 40% (Mho Zone1)",          {"21"}),
    Scenario("line8_9_ext",    "Line8-9 at 130% (Mho Zone3 delayed)",  set()),
    Scenario("trafo_int_3ph",  "Trafo Bus10-Bus32 internal 3-phase",   {"87T"}),
    Scenario("trafo_ext_3ph",  "Bus32 fault (external to trafo)",       set()),
]


# ---------------------------------------------------------------------------
# DC time constants (from Z-bus X/R at 60 Hz network, reported at 50 Hz relay)
# ---------------------------------------------------------------------------
TAU_BUS39  = 81.1e-3    # s  Bus39 Thevenin (X/R=30.6 @ 60 Hz, ÷2π×50)
TAU_BUS9   = 88.8e-3    # s  Bus9 Thevenin  (X/R=33.5 @ 60 Hz)
TAU_LINE39 = 53.0e-3    # s  average for line midpoint
TAU_TRAFO  = 60.0e-3    # s  transformer HV bus

# Pre-fault load current levels (from load flow, per-unit)
I_PRE_GEN_BUS39 = 0.010   # G9 contributes ~5 MW in case39 pu (small share)
I_PRE_LINE9_39  = 0.007   # pre-fault line current (low-load line)
I_PRE_LINE1_39  = 0.010
I_PRE_LINE8_9   = 0.023
I_PRE_TRAFO_HV  = 0.015

# Fault current levels [pu] from Z-bus analysis
#   Bus39: I_f=15.03, Line9-39 contributes 7.10 pu, Line1-39 contributes 7.54 pu
#   Gen G9 contribution to Bus39 fault: 15.03 - 7.10 - 7.54 = 0.39 pu
I_F_BUS39     = 15.03   # total 3ph fault at Bus39 [pu]
I_F_LINE9_39  =  7.10   # Line9-39 contribution to Bus39 fault (from Bus9 side)
I_F_LINE1_39  =  7.54   # Line1-39 contribution to Bus39 fault (from Bus1 side)
I_F_GEN_BUS39 =  0.39   # G9 own contribution to Bus39 fault
I_F_BUS9      = 14.70   # total 3ph fault at Bus9 [pu]
I_F_L9_EXT9   =  5.74   # Line9-39 through-current for Bus9 fault
# Line9-39 midpoint fault: ~24 pu total, 12 from each end
I_F_MID_NEAR  = 12.3    # into zone from Bus39 end (near)
I_F_MID_FAR   = 12.1    # into zone from Bus9 end  (far)
# AG factor (Z0 ≈ 3Z1 approximation): I_ag ≈ 0.60 × I_3ph
AG_FACTOR     = 0.60
# Sequence components for AG: I1=I2=I0 ≈ I_ag/3
SEQ_FACTOR    = AG_FACTOR / 3.0

# Transformer (Bus10→Bus32): fault currents
I_F_TRAFO_INT = 13.03   # HV internal fault [pu]
I_F_TRAFO_GEN =  6.00   # LV generator contribution [pu]
I_F_TRAFO_EXT =  6.50   # through-current for remote fault (no differential)

# IBR scenario
K_IBR = 0.08            # IBR current-limited fault [pu]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RelayDecisions:
    trip_51G:   bool = False; I_51G:    float = 0.0
    trip_87G:   bool = False; I_op_87G: float = 0.0; I_rst_87G: float = 0.0
    trip_87B:   bool = False; I_op_87B: float = 0.0; I_rst_87B: float = 0.0
    kn_87B:     float = float("nan"); fint_87B: float = float("nan")
    trip_87L:   bool = False; I_op_87L: float = 0.0; kn_87L: float = float("nan")
    trip_87LN:  bool = False; I2_diff:  float = 0.0
    trip_87LN0: bool = False; I0_diff:  float = 0.0
    trip_TDCS:  bool = False; TDCS_ind: float = 0.0
    trip_87T:   bool = False; I_op_87T: float = 0.0; kn_87T: float = float("nan")
    trip_21:    bool = False; zone_21:  int   = 0;   Zm_21:  complex = 0j

    @property
    def tripped(self) -> set[str]:
        return {
            r for r, t in [
                ("51G",   self.trip_51G),  ("87G",   self.trip_87G),
                ("87B",   self.trip_87B),  ("87L",   self.trip_87L),
                ("87LN",  self.trip_87LN), ("87LN0", self.trip_87LN0),
                ("TDCS",  self.trip_TDCS), ("87T",   self.trip_87T),
                ("21",    self.trip_21),
            ] if t
        }


# ---------------------------------------------------------------------------
# Per-scenario evaluation
# ---------------------------------------------------------------------------

def _run_scenario(sid: str) -> RelayDecisions:
    dec = RelayDecisions()

    # ------------------------------------------------------------------ #
    #  Build a minimal-length time axis for relay pipelines               #
    # ------------------------------------------------------------------ #
    t = T.copy()

    # ===== 1. Normal load =============================================
    if sid == "normal_load":
        # All feeders carry small pre-fault sinusoidal load
        i_gen    = _load_wave3ph(I_PRE_GEN_BUS39)
        i_l9_39  = _load_wave3ph(I_PRE_LINE9_39)
        i_l1_39  = _load_wave3ph(I_PRE_LINE1_39)
        # 87B: feeders = [gen, line1, line9] into Bus39 (balanced → no diff)
        feeders_B = [i_gen, i_l1_39, i_l9_39]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        # 87L: near = Bus39 end of Line9-39 (carries -i_l9_39 toward Bus9)
        i_near = -i_l9_39; i_far = i_l9_39   # balanced load, no differential
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        # 87T: balanced pre-fault load
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)  # turns ratio approx
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        # 21: load impedance is far outside all Mho zones
        Z_m_load = complex(10.0, 10.0)   # large R,X = load
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m_load)
        dec.Zm_21  = Z_m_load
        return dec

    # ===== 2. Bus39 3-phase fault =====================================
    if sid == "bus39_3ph":
        # All feeders carry current INTO Bus39 (toward fault)
        # Phasors: all approx in phase (positive sequence, 88° phase)
        phi = np.radians(88.0)
        i_gen_ph   = complex(I_F_GEN_BUS39 * np.cos(phi), I_F_GEN_BUS39 * np.sin(phi))
        i_l9_ph    = complex(I_F_LINE9_39  * np.cos(phi), I_F_LINE9_39  * np.sin(phi))
        i_l1_ph    = complex(I_F_LINE1_39  * np.cos(phi), I_F_LINE1_39  * np.sin(phi))
        i_gen   = _phasor_to_wave3ph(i_gen_ph, TAU_BUS39)
        i_l9_39 = _phasor_to_wave3ph(i_l9_ph, TAU_BUS9)
        i_l1_39 = _phasor_to_wave3ph(i_l1_ph, TAU_BUS39)
        # 87B: all feeders into Bus39 (positive into bus = toward fault)
        feeders_B = [i_gen, i_l1_39, i_l9_39]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        # 87G: Bus39 fault is external to gen zone
        #   i_stator (neutral end, INTO zone) = +i_gen
        #   i_hv     (HV terminal, OUT of zone) = -i_gen  → differential = 0
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen, -i_gen)
        # 87L: Line9-39 carries I_F_LINE9_39 as through-current (external to line zone)
        #   near end (Bus39): current flows OUT (toward Bus9) = negative into zone
        i_near = -i_l9_39   # current leaving zone at Bus39 end
        i_far  =  i_l9_39   # current entering zone at Bus9 end (from Bus9 network)
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        # 87T: not in fault path — small load current only
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        # 21 at Line8-9: Bus39 fault seen at ~200% reach (outside Zone3)
        Z_m = 2.0 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        return dec

    # ===== 3. Bus39 A-G fault =========================================
    if sid == "bus39_ag":
        phi = np.radians(85.0)
        I_ag = I_F_BUS39 * AG_FACTOR
        i_gen_ph = I_ag * SEQ_FACTOR * np.exp(1j * phi)  # gen's phase-A share
        i_l9_ph  = I_F_LINE9_39 * AG_FACTOR * np.exp(1j * phi)
        i_l1_ph  = I_F_LINE1_39 * AG_FACTOR * np.exp(1j * phi)
        i_gen   = _phasor_to_wave_ag(i_gen_ph, TAU_BUS39)
        i_l9_39 = _phasor_to_wave_ag(i_l9_ph,  TAU_BUS9)
        i_l1_39 = _phasor_to_wave_ag(i_l1_ph,  TAU_BUS39)
        feeders_B = [i_gen, i_l1_39, i_l9_39]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen, -i_gen)
        i_near = -i_l9_39; i_far = i_l9_39
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        # Sequence components for external AG at Bus39: zero differential on line
        dec.I2_diff = 0.0; dec.I0_diff = 0.0
        dec.trip_87LN  = _run_87LN(dec.I2_diff)
        dec.trip_87LN0 = _run_87LN0(dec.I0_diff)
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        Z_m = 2.0 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        return dec

    # ===== 4. Generator stator internal fault =========================
    if sid == "gen_stator_3ph":
        # Fault is inside generator stator, before HV terminal
        # 87G: i_stator = large fault current; i_HV = 0 (no network contribution)
        I_gen_stator = 10.0    # pu — internal stator fault current
        phi = np.radians(85.0)
        i_stator = _phasor_to_wave3ph(I_gen_stator * np.exp(1j*phi), TAU_BUS39)
        i_hv     = np.zeros((3, N_SAMP))   # no current at HV terminal
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_stator, i_hv)
        # 51G: generator stator carries I_gen_stator → OC trips
        dec.trip_51G, dec.I_51G = _run_51G(i_stator)
        # 87B at Bus39: no fault current at bus (fault is before terminal)
        i_gen_bus  = np.zeros((3, N_SAMP))  # generator does NOT deliver to bus
        i_l9_bus   = _load_wave3ph(I_PRE_LINE9_39)
        i_l1_bus   = _load_wave3ph(I_PRE_LINE1_39)
        feeders_B  = [i_gen_bus, i_l1_bus, i_l9_bus]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        # 87L, 87T, 21: all external / unaffected
        i_near = -i_l9_bus; i_far = i_l9_bus
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        Z_m = 2.0 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        return dec

    # ===== 5. Line9-39 midpoint 3-phase ================================
    if sid == "line9_39_3ph":
        phi = np.radians(87.0)
        i_near_ph  = I_F_MID_NEAR * np.exp(1j * phi)
        i_far_ph   = I_F_MID_FAR  * np.exp(1j * phi)
        i_near     = _phasor_to_wave3ph(i_near_ph,  TAU_BUS39)
        i_far      = _phasor_to_wave3ph(i_far_ph,   TAU_BUS9)
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        dec.I2_diff = 0.0; dec.I0_diff = 0.0
        dec.trip_87LN  = _run_87LN(dec.I2_diff)
        dec.trip_87LN0 = _run_87LN0(dec.I0_diff)
        # 87B at Bus39: through-current, no differential
        i_gen_w   = _load_wave3ph(I_PRE_GEN_BUS39)
        i_l1_w    = _phasor_to_wave3ph((I_F_MID_NEAR - I_PRE_GEN_BUS39)
                                        * np.exp(1j*phi), TAU_BUS39)
        # All near-end current flows from Bus39 into line → bus sees balanced infeed
        i_l9_into = -i_near   # Line9-39 exits Bus39 toward fault
        feeders_B = [i_gen_w, i_l1_w, i_l9_into]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen_w, -i_gen_w)
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        Z_m = 2.5 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        return dec

    # ===== 6. Line9-39 midpoint A-G ====================================
    if sid == "line9_39_ag":
        phi = np.radians(85.0)
        I_ag_near = I_F_MID_NEAR * AG_FACTOR
        I_ag_far  = I_F_MID_FAR  * AG_FACTOR
        i_near    = _phasor_to_wave_ag(I_ag_near * np.exp(1j*phi), TAU_BUS39)
        i_far     = _phasor_to_wave_ag(I_ag_far  * np.exp(1j*phi), TAU_BUS9)
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        # Sequence components (internal fault): I2 = I0 = I_ag_total/3
        I_ag_total  = (I_ag_near + I_ag_far)
        dec.I2_diff = I_ag_total * SEQ_FACTOR / AG_FACTOR
        dec.I0_diff = dec.I2_diff
        dec.trip_87LN  = _run_87LN(dec.I2_diff)
        dec.trip_87LN0 = _run_87LN0(dec.I0_diff)
        # 87B: through-current only
        i_gen_w = _load_wave3ph(I_PRE_GEN_BUS39)
        i_l9_into = -i_near
        i_l1_w    = _phasor_to_wave_ag((I_ag_near * 0.9) * np.exp(1j*phi), TAU_BUS39)
        feeders_B = [i_gen_w, i_l1_w, i_l9_into]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen_w, -i_gen_w)
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        Z_m = 2.5 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        return dec

    # ===== 7. Line9-39 IBR (low k_ibr) ================================
    if sid == "line9_39_ibr":
        # IBR current-limited: k_ibr = 0.08 pu, well below 87L threshold (0.12)
        # Both ends inject equal current toward internal fault
        phi       = np.radians(87.0)
        i_near    = _phasor_to_wave3ph(K_IBR / 2 * np.exp(1j*phi), TAU_LINE39)
        i_far     = _phasor_to_wave3ph(K_IBR / 2 * np.exp(1j*phi), TAU_LINE39)
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        dec.I2_diff = 0.0; dec.I0_diff = 0.0
        dec.trip_87LN  = _run_87LN(dec.I2_diff)
        dec.trip_87LN0 = _run_87LN0(dec.I0_diff)
        # All other relays: not affected
        i_gen_w = _load_wave3ph(I_PRE_GEN_BUS39)
        feeders_B = [i_gen_w, _load_wave3ph(I_PRE_LINE1_39), _load_wave3ph(I_PRE_LINE9_39)]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen_w, -i_gen_w)
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        Z_m = complex(5.0, 5.0)   # large impedance (IBR fault appears high-Z)
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        return dec

    # ===== 8. Bus9 3-phase (external to all differential) ==============
    if sid == "bus9_ext_3ph":
        # Line9-39 carries through-current toward Bus9 fault
        phi       = np.radians(88.0)
        i_through = _phasor_to_wave3ph(I_F_L9_EXT9 * np.exp(1j*phi), TAU_BUS9)
        # 87L: through-current → near = +, far = - (equal and opposite)
        i_near    =  i_through   # current flowing FROM Bus39 INTO zone
        i_far     = -i_through   # current flowing OUT of zone at Bus9 (toward fault)
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        dec.I2_diff = 0.0; dec.I0_diff = 0.0
        dec.trip_87LN  = _run_87LN(dec.I2_diff)
        dec.trip_87LN0 = _run_87LN0(dec.I0_diff)
        # 87B: all bus feeders carry through-current → KCL balances → no differential
        # During Bus9 fault, Gen G9 and Line1-39 supply 5.74 pu into Bus39 → exits via Line9-39
        GEN_FRAC   = I_F_GEN_BUS39 / I_F_BUS39   # ≈0.026
        phi_b9     = np.radians(88.0)
        i_gen_w    = _phasor_to_wave3ph(GEN_FRAC  * I_F_L9_EXT9 * np.exp(1j*phi_b9), TAU_BUS9)
        i_l1_w     = _phasor_to_wave3ph((1-GEN_FRAC)*I_F_L9_EXT9 * np.exp(1j*phi_b9), TAU_BUS9)
        feeders_B = [i_gen_w, i_l1_w, -i_near]  # i_near exits bus → negative into bus
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen_w, -i_gen_w)
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        # 21 at Line8-9: Bus9 fault is at 100% reach → Zone2 (delayed)
        Z_m = 1.0 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        return dec

    # ===== 9. Line8-9 at 40% (Mho Zone1) ==============================
    if sid == "line8_9_z1":
        Z_m = 0.40 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        # All differential relays: not on Line8-9 path
        i_gen_w = _load_wave3ph(I_PRE_GEN_BUS39)
        feeders_B = [i_gen_w, _load_wave3ph(I_PRE_LINE1_39), _load_wave3ph(I_PRE_LINE9_39)]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen_w, -i_gen_w)
        i_near = _load_wave3ph(I_PRE_LINE9_39); i_far = -i_near
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        return dec

    # ===== 10. Line8-9 at 130% (outside Zone2) =========================
    if sid == "line8_9_ext":
        Z_m = 1.30 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        i_gen_w = _load_wave3ph(I_PRE_GEN_BUS39)
        feeders_B = [i_gen_w, _load_wave3ph(I_PRE_LINE1_39), _load_wave3ph(I_PRE_LINE9_39)]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen_w, -i_gen_w)
        i_near = _load_wave3ph(I_PRE_LINE9_39); i_far = -i_near
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        i_H = _load_wave3ph(I_PRE_TRAFO_HV)
        i_X = _load_wave3ph(I_PRE_TRAFO_HV * 0.9)
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        return dec

    # ===== 11. Transformer Bus10→Bus32 internal 3-phase ================
    if sid == "trafo_int_3ph":
        phi  = np.radians(87.0)
        # HV: network feeds into fault (from Bus10 side)
        i_H  = _phasor_to_wave3ph(I_F_TRAFO_INT * np.exp(1j*phi), TAU_TRAFO)
        # LV: no current exits the LV terminal (fault is internal, before LV CT)
        i_X  = np.zeros((3, N_SAMP))
        # For 87T internal: i_H_comp + i_X_comp = i_H_comp ≠ 0 → I_op large → TRIP
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        # All others: unaffected
        i_gen_w = _load_wave3ph(I_PRE_GEN_BUS39)
        feeders_B = [i_gen_w, _load_wave3ph(I_PRE_LINE1_39), _load_wave3ph(I_PRE_LINE9_39)]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen_w, -i_gen_w)
        i_near = _load_wave3ph(I_PRE_LINE9_39); i_far = -i_near
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        Z_m = 3.0 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        return dec

    # ===== 12. Transformer external (Bus32 fault) =======================
    if sid == "trafo_ext_3ph":
        phi_H = np.radians(87.0)
        phi_X = phi_H + 5.0 * np.pi / 6.0   # Yd11 phase shift: after M_X, i_Xc = -i_Hc
        # Through-current: LV has Yd11 offset so differential cancels after compensation
        i_H = _phasor_to_wave3ph(I_F_TRAFO_EXT * np.exp(1j * phi_H), TAU_TRAFO)
        i_X = _phasor_to_wave3ph(I_F_TRAFO_EXT * np.exp(1j * phi_X), TAU_TRAFO)
        # External fault: after Yd11 compensation, i_Hc + i_Xc ≈ 0 → no trip
        dec.trip_87T, _, dec.I_op_87T, dec.kn_87T = _run_87T(t, i_H, i_X)
        i_gen_w = _load_wave3ph(I_PRE_GEN_BUS39)
        feeders_B = [i_gen_w, _load_wave3ph(I_PRE_LINE1_39), _load_wave3ph(I_PRE_LINE9_39)]
        dec.trip_87B, _, dec.I_op_87B, dec.I_rst_87B, dec.kn_87B, dec.fint_87B = \
            _run_87B(t, feeders_B, n_feeders=3)
        dec.trip_87G, dec.I_op_87G, dec.I_rst_87G = _run_87G(i_gen_w, -i_gen_w)
        i_near = _load_wave3ph(I_PRE_LINE9_39); i_far = -i_near
        dec.trip_87L, _, dec.I_op_87L, dec.kn_87L = _run_87L(t, i_near, i_far)
        dec.trip_TDCS, dec.TDCS_ind = _run_TDCS((i_near + i_far)[0])
        Z_m = 3.0 * Z_LINE89_PU
        dec.trip_21, dec.zone_21, _ = _run_21(Z_m)
        dec.Zm_21 = Z_m
        return dec

    raise ValueError(f"Unknown scenario: {sid}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

RELAY_COLS = ["51G", "87G", "87B", "87L", "87LN", "87LN0", "TDCS", "87T", "21"]

RELAY_ORDER = [
    ("51G",   lambda d: d.trip_51G),
    ("87G",   lambda d: d.trip_87G),
    ("87B",   lambda d: d.trip_87B),
    ("87L",   lambda d: d.trip_87L),
    ("87LN",  lambda d: d.trip_87LN),
    ("87LN0", lambda d: d.trip_87LN0),
    ("TDCS",  lambda d: d.trip_TDCS),
    ("87T",   lambda d: d.trip_87T),
    ("21",    lambda d: d.trip_21),
]


def main():
    print("\n" + "=" * 68)
    print("TR-66/2026  IEEE 39-Bus Full-System SAMBP Validation")
    print("=" * 68)
    print(f"{'Scenario':<22}  {'Expected':^20}  {'Got':^20}  OK")
    print("-" * 68)

    results = []
    n_pass = 0

    for scen in SCENARIOS:
        dec  = _run_scenario(scen.sid)
        got  = dec.tripped
        ok   = (got == scen.expected)
        n_pass += int(ok)

        status = "PASS" if ok else "FAIL"
        print(f"{scen.sid:<22}  {str(sorted(scen.expected)):^20}  "
              f"{str(sorted(got)):^20}  {status}")

        row = {
            "scenario":  scen.sid,
            "expected":  ",".join(sorted(scen.expected)) or "none",
            "got":       ",".join(sorted(got)) or "none",
            "correct":   int(ok),
            "I_51G":     f"{dec.I_51G:.4f}",
            "trip_87G":  int(dec.trip_87G),
            "I_op_87G":  f"{dec.I_op_87G:.4f}",
            "trip_87B":  int(dec.trip_87B),
            "I_op_87B":  f"{dec.I_op_87B:.4f}",
            "I_rst_87B": f"{dec.I_rst_87B:.4f}",
            "kn_87B":    f"{dec.kn_87B:.2f}" if not np.isnan(dec.kn_87B) else "",
            "trip_87L":  int(dec.trip_87L),
            "I_op_87L":  f"{dec.I_op_87L:.4f}",
            "kn_87L":    f"{dec.kn_87L:.2f}" if not np.isnan(dec.kn_87L) else "",
            "I2_diff":   f"{dec.I2_diff:.4f}",
            "I0_diff":   f"{dec.I0_diff:.4f}",
            "TDCS_ind":  f"{dec.TDCS_ind:.2f}",
            "trip_87T":  int(dec.trip_87T),
            "I_op_87T":  f"{dec.I_op_87T:.4f}",
            "kn_87T":    f"{dec.kn_87T:.2f}" if not np.isnan(dec.kn_87T) else "",
            "zone_21":   str(dec.zone_21),
            "Zm_21_pu":  f"{abs(dec.Zm_21):.5f}",
        }
        results.append(row)

    print("=" * 68)
    print(f"Results: {n_pass}/{len(SCENARIOS)} correct  "
          f"({'%.1f' % (100*n_pass/len(SCENARIOS))} %)\n")

    # ---- CSV export -------------------------------------------------------
    out_dir = os.path.join(_HERE, "outputs", "tr66")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "tr66_results.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    # ---- Selectivity matrix (console) ------------------------------------
    print("Selectivity matrix  (1=trip, 0=no-trip, *=unexpected)")
    header = f"{'Scenario':<22}  " + "  ".join(f"{r:^5}" for r, _ in RELAY_ORDER)
    print(header)
    print("-" * len(header))
    for scen, row in zip(SCENARIOS, results):
        dec = _run_scenario(scen.sid)
        cells = []
        for rname, getter in RELAY_ORDER:
            trip = getter(dec)
            expected = rname in scen.expected
            marker   = "1" if trip else "0"
            if trip and not expected:
                marker = "1*"   # false positive
            elif not trip and expected:
                marker = "0*"   # missed trip
            cells.append(f"{marker:^5}")
        print(f"{scen.sid:<22}  " + "  ".join(cells))

    print(f"\nCSV: {csv_path}")
    return n_pass == len(SCENARIOS)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
