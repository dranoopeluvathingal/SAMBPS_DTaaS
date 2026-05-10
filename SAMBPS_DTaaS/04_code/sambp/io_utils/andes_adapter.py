# =============================================================================
# sambp / io_utils / andes_adapter.py
#
# Bridge between ANDES transient simulation and the SAMBP estimator pipeline.
#
# ANDES is a positive-sequence DAE simulator — it produces phasor-domain
# quantities (V, I as real scalars representing magnitudes or state variables).
# SAMBP expects time-domain three-phase abc waveforms at fs = 10 kHz.
#
# This adapter:
#   1. Loads an ANDES case, optionally injects a Fault device
#   2. Runs PFlow + TDS
#   3. Extracts voltage/current at specified relay bus and branch
#   4. Reconstructs three-phase abc waveforms via inverse-symmetrical-components
#   5. Resamples to SAMBP fs and trims to the fault window
#   6. Returns a FaultCase dict ready for parameter_estimator.py
#
# Public API
# ----------
# run_andes_tds(case_file, fault_bus, fault_time, clear_time, **kw)
#     → AndesResult (namedtuple)
#
# extract_relay_waveforms(result, relay_bus, branch, fs, window)
#     → dict {t, ia, ib, ic, va, vb, vc, meta}
#
# build_fault_case(waveforms, fault_type, fault_R_pu)
#     → dict  (direct input to estimate_reduced_source_parameters)
#
# run_full_pipeline(case_file, fault_bus, relay_bus, ...)
#     → dict  (convenience: TDS + extract + build in one call)
#
# =============================================================================

from __future__ import annotations

import os
import warnings
from collections import namedtuple
from typing import Optional

import numpy as np
from scipy.interpolate import interp1d

# ANDES import — only needed at runtime, not at import time
_andes = None


def _import_andes():
    global _andes
    if _andes is None:
        try:
            import andes
            _andes = andes
        except ImportError as e:
            raise ImportError(
                "ANDES is not installed. Run:\n"
                "  pip install andes\n"
                "or activate the venv:  source /root/dr_e_venv/bin/activate"
            ) from e
    return _andes


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

AndesResult = namedtuple("AndesResult", [
    "ss",          # ANDES System object (full access to all models)
    "t",           # ndarray — raw ANDES time vector
    "y",           # ndarray — raw state/algebraic variable matrix [t × vars]
    "case_file",   # str
    "fault_bus",   # int
    "fault_time",  # float
    "clear_time",  # float
])


# ---------------------------------------------------------------------------
# Step 1 — Run TDS
# ---------------------------------------------------------------------------

def run_andes_tds(
    case_file: str,
    fault_bus: int,
    fault_time: float,
    clear_time: float,
    tf: float = None,
    fault_xf: float = 0.001,
    fault_rf: float = 0.0,
    no_output: bool = True,
    disable_togglers: bool = False,
) -> AndesResult:
    """
    Load an ANDES case, inject a 3-phase Fault device, run PFlow + TDS.

    Parameters
    ----------
    case_file  : path to .json or .xlsx ANDES case
    fault_bus  : bus index where fault is applied
    fault_time : fault inception time (s)
    clear_time : fault clearing time (s)
    tf         : TDS end time (s); defaults to clear_time + 1.0
    fault_xf   : fault reactance [pu] (0.001 = near-bolted)
    fault_rf   : fault resistance [pu] (0.0 = bolted, >0 = resistive)
    no_output  : suppress ANDES console output

    Returns
    -------
    AndesResult namedtuple
    """
    andes = _import_andes()

    if tf is None:
        tf = clear_time + 1.0

    # Load without setup so we can inject / override the fault
    ss = andes.load(case_file, setup=False, no_output=no_output)

    # Optionally disable pre-existing Toggler devices (e.g. PVD1 demo cases)
    if disable_togglers and hasattr(ss, 'Toggler') and ss.Toggler.n > 0:
        for i in range(ss.Toggler.n):
            ss.Toggler.u.v[i] = 0.0

    if ss.Fault.n == 0:
        # No fault in case file — inject one
        ss.add("Fault", {
            "bus": fault_bus,
            "tf":  fault_time,
            "tc":  clear_time,
            "xf":  fault_xf,
            "rf":  fault_rf,
        })
    else:
        # Fault already in case — override xf / rf before setup
        ss.Fault.xf.v[0] = fault_xf
        ss.Fault.rf.v[0] = fault_rf

    ss.setup()
    ss.PFlow.run()

    if not ss.PFlow.converged:
        raise RuntimeError(f"Power flow did not converge for case: {case_file}")

    ss.TDS.config.tf = tf
    ss.TDS.run()

    t = np.array(ss.dae.ts.t)
    y = np.array(ss.dae.ts.y)

    return AndesResult(
        ss=ss, t=t, y=y,
        case_file=case_file,
        fault_bus=fault_bus,
        fault_time=fault_time,
        clear_time=clear_time,
    )


# ---------------------------------------------------------------------------
# Step 2 — Extract relay waveforms
# ---------------------------------------------------------------------------

def extract_relay_waveforms(
    result: AndesResult,
    relay_bus: int,
    fs: float = 10000.0,
    window: tuple = None,
    f0: float = 50.0,
) -> dict:
    """
    Extract three-phase abc voltage and current waveforms at a relay bus.

    ANDES is a positive-sequence simulator. This function:
      - Reads the positive-sequence bus voltage magnitude V(t) and angle θ(t)
      - Derives the fault current from the Thevenin equivalent
        I(t) = [V_pre - V(t)] / Z_th  (superposition principle)
      - Reconstructs balanced three-phase abc waveforms at fs via:
          va(t) = V(t)·√2 · cos(2πf₀t + θ(t))
          vb(t) = V(t)·√2 · cos(2πf₀t + θ(t) - 2π/3)
          vc(t) = V(t)·√2 · cos(2πf₀t + θ(t) + 2π/3)
      - For 3-phase fault current the assumption is symmetric — use phase A only
        for the LM estimator (fit_phase='A' is the default)

    Parameters
    ----------
    result    : AndesResult from run_andes_tds()
    relay_bus : bus index at the relay measurement point
    fs        : SAMBP sampling rate (Hz), default 10 000
    window    : (t_start, t_end) trim window; defaults to full simulation
    f0        : system frequency (Hz)

    Returns
    -------
    dict with keys:
        t           — resampled time vector
        va, vb, vc  — three-phase voltages (pu)
        ia, ib, ic  — three-phase currents (pu, estimated from V drop)
        V_mag       — positive-sequence voltage magnitude (pu)
        I_mag       — positive-sequence current magnitude (pu)
        V_pre       — pre-fault voltage at relay bus (pu)
        meta        — dict of simulation metadata
    """
    ss, t_raw, y_raw = result.ss, result.t, result.y

    # ── Find relay bus index in ANDES bus list ───────────────────────────────
    bus_list = list(ss.Bus.idx.v)
    if relay_bus not in bus_list:
        raise ValueError(
            f"relay_bus={relay_bus} not found in case. "
            f"Available buses: {bus_list}"
        )
    b_idx = bus_list.index(relay_bus)

    # ── Extract positive-sequence voltage magnitude and angle ────────────────
    V_mag_raw = y_raw[:, ss.Bus.v.a[b_idx]]    # voltage magnitude [pu]
    V_ang_raw = y_raw[:, ss.Bus.a.a[b_idx]]    # voltage angle [rad]

    # Pre-fault voltage (mean of 10 cycles before fault)
    pre_mask  = t_raw < result.fault_time
    V_pre     = float(V_mag_raw[pre_mask].mean()) if pre_mask.any() else 1.0
    theta_pre = float(V_ang_raw[pre_mask].mean()) if pre_mask.any() else 0.0

    # ── Thevenin impedance from generator parameters (if GENROU present) ─────
    if ss.GENROU.n > 0:
        # Use subtransient reactance of nearest generator as Thevenin Z
        Xdpp = float(np.mean(ss.GENROU.xd2.v))   # d-axis subtransient
        Ra   = float(np.mean(ss.GENROU.ra.v))     # armature resistance
        Z_th = complex(Ra, Xdpp)
    else:
        Z_th = complex(0.01, 0.15)  # default Thevenin Z if no GENROU

    Z_th_mag = abs(Z_th)

    # ── Current magnitude: superposition I = ΔV / Z_th ─────────────────────
    delta_V   = np.maximum(V_pre - V_mag_raw, 0.0)   # voltage drop during fault
    I_mag_raw = delta_V / Z_th_mag                    # positive-sequence current

    # ── Resample to SAMBP fs ─────────────────────────────────────────────────
    t_start = window[0] if window else t_raw[0]
    t_end   = window[1] if window else t_raw[-1]

    t_new  = np.arange(t_start, t_end, 1.0 / fs)
    interp = lambda arr: interp1d(
        t_raw, arr, kind="linear", bounds_error=False,
        fill_value=(arr[0], arr[-1])
    )(t_new)

    V_mag = interp(V_mag_raw)
    V_ang = interp(V_ang_raw)
    I_mag = interp(I_mag_raw)

    # ── Reconstruct three-phase abc waveforms ────────────────────────────────
    # Carrier: instantaneous angle = 2πf₀t + θ(t)  (ANDES angle is slowly varying)
    carrier = 2.0 * np.pi * f0 * t_new + V_ang

    sqrt2 = np.sqrt(2.0)

    va = V_mag * sqrt2 * np.cos(carrier)
    vb = V_mag * sqrt2 * np.cos(carrier - 2.0 * np.pi / 3.0)
    vc = V_mag * sqrt2 * np.cos(carrier + 2.0 * np.pi / 3.0)

    # Current lags voltage by Z_th angle
    phi_z = np.arctan2(Z_th.imag, Z_th.real)
    ia = I_mag * sqrt2 * np.cos(carrier - phi_z)
    ib = I_mag * sqrt2 * np.cos(carrier - phi_z - 2.0 * np.pi / 3.0)
    ic = I_mag * sqrt2 * np.cos(carrier - phi_z + 2.0 * np.pi / 3.0)

    return {
        "t":     t_new,
        "va":    va,   "vb":    vb,   "vc":    vc,
        "ia":    ia,   "ib":    ib,   "ic":    ic,
        "V_mag": V_mag,
        "I_mag": I_mag,
        "V_pre": V_pre,
        "Z_th":  Z_th,
        "meta": {
            "case_file":  result.case_file,
            "fault_bus":  result.fault_bus,
            "relay_bus":  relay_bus,
            "fault_time": result.fault_time,
            "clear_time": result.clear_time,
            "fs_hz":      fs,
            "f0_hz":      f0,
            "V_pre_pu":   V_pre,
            "Z_th_pu":    abs(Z_th),
            "n_samples":  len(t_new),
            "GENROU_n":   ss.GENROU.n,
        },
    }


# ---------------------------------------------------------------------------
# Step 3 — Build FaultCase dict for SAMBP estimator
# ---------------------------------------------------------------------------

def build_fault_case(
    waveforms: dict,
    fault_type: str = "3PH",
    fault_R_pu: float = 0.01,
    window_start: float = None,
    window_end: float = None,
) -> dict:
    """
    Package extracted waveforms as a SAMBP FaultCase dict.

    This is the direct input format for:
        inverse_estimation.parameter_estimator
            .estimate_reduced_source_parameters()

    Parameters
    ----------
    waveforms    : dict from extract_relay_waveforms()
    fault_type   : "3PH" | "LL" | "SLG"
    fault_R_pu   : fault resistance [pu]
    window_start : trim to this start time (s); defaults to waveforms["t"][0]
    window_end   : trim to this end time (s);   defaults to waveforms["t"][-1]

    Returns
    -------
    dict with keys:
        t_window    — trimmed time vector
        ia_meas     — phase-A current (pu) — primary fit target
        ib_meas     — phase-B current (pu)
        ic_meas     — phase-C current (pu)
        va_meas     — phase-A voltage (pu)
        fault_type  — "3PH" | "LL" | "SLG"
        fault_R_pu  — fault resistance
        V_pre_pu    — pre-fault voltage
        source      — "andes"
        meta        — metadata dict
    """
    t  = waveforms["t"]
    ia = waveforms["ia"]
    ib = waveforms["ib"]
    ic = waveforms["ic"]
    va = waveforms["va"]

    # Optional time trimming
    if window_start is not None or window_end is not None:
        ws = window_start if window_start is not None else t[0]
        we = window_end   if window_end   is not None else t[-1]
        mask = (t >= ws) & (t <= we)
        t, ia, ib, ic, va = t[mask], ia[mask], ib[mask], ic[mask], va[mask]

    return {
        "t_window":   t,
        "ia_meas":    ia,
        "ib_meas":    ib,
        "ic_meas":    ic,
        "va_meas":    va,
        "fault_type": fault_type,
        "fault_R_pu": fault_R_pu,
        "V_pre_pu":   waveforms["V_pre"],
        "source":     "andes",
        "meta":       waveforms["meta"],
    }


# ---------------------------------------------------------------------------
# Convenience: full pipeline in one call
# ---------------------------------------------------------------------------

def run_full_pipeline(
    case_file: str,
    fault_bus: int,
    relay_bus: int,
    fault_time: float = 0.1,
    clear_time: float = 0.25,
    fault_type: str = "3PH",
    fault_R_pu: float = 0.01,
    fs: float = 10000.0,
    f0: float = 50.0,
    tf: float = None,
    estimator_window: tuple = None,
) -> dict:
    """
    End-to-end: load case → TDS → extract waveforms → build FaultCase.

    Returns the FaultCase dict directly passable to:
        estimate_reduced_source_parameters(
            fc["t_window"], fc["ia_meas"], fc["ib_meas"], fc["ic_meas"], ...
        )

    Parameters
    ----------
    case_file        : ANDES .json or .xlsx case file path
    fault_bus        : bus where fault is applied
    relay_bus        : bus where relay measurement is taken
    fault_time       : fault inception (s)
    clear_time       : fault clearing (s)
    fault_type       : "3PH" | "LL" | "SLG"
    fault_R_pu       : fault resistance (pu)
    fs               : SAMBP sampling rate (Hz)
    f0               : system frequency (Hz)
    tf               : TDS end time (s)
    estimator_window : (t_start, t_end) for LM estimator input trim

    Returns
    -------
    dict — FaultCase (see build_fault_case)
    """
    result    = run_andes_tds(case_file, fault_bus, fault_time, clear_time, tf=tf)
    waveforms = extract_relay_waveforms(result, relay_bus, fs=fs, f0=f0)
    fault_case = build_fault_case(
        waveforms, fault_type, fault_R_pu,
        window_start=estimator_window[0] if estimator_window else None,
        window_end=estimator_window[1]   if estimator_window else None,
    )
    return fault_case


# ---------------------------------------------------------------------------
# DFIG 87L waveform extraction
# ---------------------------------------------------------------------------

def extract_dfig_87L_waveforms(
    result: AndesResult,
    line_bus1: int,
    line_bus2: int,
    fs: float = 10000.0,
    f0: float = 50.0,
    window: tuple = None,
    z_thevenin_remote: complex = None,
) -> dict:
    """
    Extract 87L line current waveforms for a DFIG-connected line.

    ANDES positive-sequence simulation gives V_mag and V_ang at each bus.
    The line current at each terminal is derived from the π-model:

        I_L = (V1 - V2) / Z_line + j·(b/2)·V1   [local end, bus1]
        I_R = (V2 - V1) / Z_line + j·(b/2)·V2   [remote end, bus2]

    Sign convention (87L standard):
        i_diff = I_L + I_R   (both defined positive INTO the protected zone)
        i_rst  = 0.5·(|I_L| + |I_R|)

    For an **external fault** both are computed from ANDES directly.
    For an **internal fault** I_R is synthesised using the Thevenin network
    equivalent at bus2:
        I_R_internal = V2_pre / Z_th_remote
    so that I_diff = I_L + I_R_internal (fault current both ends flow in).

    Parameters
    ----------
    result              : AndesResult from run_andes_tds()
    line_bus1           : local terminal bus (DFIG side)
    line_bus2           : remote terminal bus (network side)
    fs                  : SAMBP sampling rate (Hz)
    f0                  : system frequency (Hz)
    window              : (t_start, t_end) trim; defaults to full simulation
    z_thevenin_remote   : complex Thevenin Z at bus2 for internal fault synthesis;
                          if None, uses default 0.01+0.12j

    Returns
    -------
    dict with keys:
        t                — resampled time vector
        I_L_cplx         — complex positive-sequence local current [pu]
        I_R_ext_cplx     — complex remote current for external fault scenario
        I_R_int_cplx     — complex remote current for internal fault scenario
        ia_L, ib_L, ic_L — three-phase abc local currents (external fault)
        ia_diff_ext      — phase-A differential: external fault (≈ 0)
        ia_diff_int      — phase-A differential: internal fault (= DFIG contribution)
        i_diff_ext_mag   — |I_L + I_R_ext| (should ≈ 0 for external)
        i_diff_int_mag   — |I_L + I_R_int| (should be large for internal)
        i_rst_ext        — 0.5·(|I_L| + |I_R_ext|)
        i_rst_int        — 0.5·(|I_L| + |I_R_int|)
        V_pre_bus1       — pre-fault voltage at bus1 [pu]
        V_pre_bus2       — pre-fault voltage at bus2 [pu]
        Z_line           — complex line impedance [pu]
        meta             — dict of simulation metadata
    """
    ss, t_raw, y_raw = result.ss, result.t, result.y

    bus_list = list(ss.Bus.idx.v)
    for bus, name in [(line_bus1, "line_bus1"), (line_bus2, "line_bus2")]:
        if bus not in bus_list:
            raise ValueError(f"{name}={bus} not in case buses: {bus_list}")

    b1 = bus_list.index(line_bus1)
    b2 = bus_list.index(line_bus2)

    # Find the line connecting bus1 → bus2 (or bus2 → bus1)
    line_idx = None
    for i in range(ss.Line.n):
        if ((ss.Line.bus1.v[i] == line_bus1 and ss.Line.bus2.v[i] == line_bus2) or
                (ss.Line.bus1.v[i] == line_bus2 and ss.Line.bus2.v[i] == line_bus1)):
            line_idx = i
            break

    if line_idx is None:
        raise ValueError(
            f"No line found between bus {line_bus1} and bus {line_bus2}. "
            f"Available lines: {[(ss.Line.bus1.v[i], ss.Line.bus2.v[i]) for i in range(ss.Line.n)]}"
        )

    r_l = float(ss.Line.r.v[line_idx])
    x_l = float(ss.Line.x.v[line_idx])
    b_l = float(ss.Line.b.v[line_idx])
    Z_line = complex(r_l, x_l) if (r_l != 0 or x_l != 0) else complex(0.0, 0.1)

    if z_thevenin_remote is None:
        z_thevenin_remote = complex(0.01, 0.12)

    # Extract bus voltages
    V1_raw  = y_raw[:, ss.Bus.v.a[b1]]
    th1_raw = y_raw[:, ss.Bus.a.a[b1]]
    V2_raw  = y_raw[:, ss.Bus.v.a[b2]]
    th2_raw = y_raw[:, ss.Bus.a.a[b2]]

    # Pre-fault averages
    pre = t_raw < result.fault_time
    V_pre_bus1 = float(V1_raw[pre].mean()) if pre.any() else 1.0
    V_pre_bus2 = float(V2_raw[pre].mean()) if pre.any() else 1.0

    # Resample
    t_start = window[0] if window else t_raw[0]
    t_end   = window[1] if window else t_raw[-1]
    t_new   = np.arange(t_start, t_end, 1.0 / fs)

    def interp(arr):
        from scipy.interpolate import interp1d
        return interp1d(t_raw, arr, kind="linear", bounds_error=False,
                        fill_value=(arr[0], arr[-1]))(t_new)

    V1  = interp(V1_raw);  th1 = interp(th1_raw)
    V2  = interp(V2_raw);  th2 = interp(th2_raw)

    V1c = V1 * np.exp(1j * th1)
    V2c = V2 * np.exp(1j * th2)

    # Line currents (positive-sequence complex)
    I_L = (V1c - V2c) / Z_line + 1j * (b_l / 2.0) * V1c   # local → into zone
    I_R_ext = (V2c - V1c) / Z_line + 1j * (b_l / 2.0) * V2c  # remote → into zone (external)

    # Internal fault: remote terminal contributes network Thevenin current
    # I_R_int = V2_pre / Z_th_remote  (constant phasor at pre-fault magnitude)
    V2_pre_cplx = V_pre_bus2 * np.exp(1j * float(th2_raw[pre].mean() if pre.any() else 0.0))
    I_R_int_mag = abs(V2_pre_cplx) / abs(z_thevenin_remote)
    I_R_int_ang = np.angle(V2_pre_cplx) - np.angle(z_thevenin_remote)
    I_R_int_cplx = I_R_int_mag * np.exp(1j * I_R_int_ang) * np.ones_like(t_new)
    # During pre-fault ramp in to match actual load (keep as DC phasor for simplicity)

    # Differential and restraint
    i_diff_ext = np.abs(I_L + I_R_ext)
    i_diff_int = np.abs(I_L + I_R_int_cplx)
    i_rst_ext  = 0.5 * (np.abs(I_L) + np.abs(I_R_ext))
    i_rst_int  = 0.5 * (np.abs(I_L) + np.abs(I_R_int_cplx))

    # Reconstruct three-phase abc at local terminal (DFIG side)
    sqrt2   = np.sqrt(2.0)
    carrier = 2.0 * np.pi * f0 * t_new + th1
    I_L_mag = np.abs(I_L)
    phi_L   = np.angle(I_L)

    ia_L = I_L_mag * sqrt2 * np.cos(carrier + phi_L)
    ib_L = I_L_mag * sqrt2 * np.cos(carrier + phi_L - 2.0 * np.pi / 3.0)
    ic_L = I_L_mag * sqrt2 * np.cos(carrier + phi_L + 2.0 * np.pi / 3.0)

    # Phase-A differential waveforms (for DFIG model fitting)
    # External: ia_diff_ext ≈ 0 (security test)
    I_diff_ext_cplx = I_L + I_R_ext
    phi_de = np.angle(I_diff_ext_cplx + 1e-12)
    ia_diff_ext = np.abs(I_diff_ext_cplx) * sqrt2 * np.cos(carrier + phi_de)

    # Internal: ia_diff_int = DFIG contribution (sensitivity test)
    I_diff_int_cplx = I_L + I_R_int_cplx
    phi_di = np.angle(I_diff_int_cplx + 1e-12)
    ia_diff_int = np.abs(I_diff_int_cplx) * sqrt2 * np.cos(carrier + phi_di)

    # WTDTA1 rotor speed (slip tracking) if available
    wg_mean_fault = None
    if ss.WTDTA1.n > 0:
        try:
            wg_raw  = y_raw[:, ss.WTDTA1.wg.a[0]]
            wg_interp = interp(wg_raw)
            fault_m   = (t_new >= result.fault_time) & (t_new <= result.clear_time)
            wg_mean_fault = float(wg_interp[fault_m].mean()) if fault_m.any() else None
        except Exception:
            pass

    return {
        "t":             t_new,
        "I_L_cplx":      I_L,
        "I_R_ext_cplx":  I_R_ext,
        "I_R_int_cplx":  I_R_int_cplx,
        "ia_L":          ia_L,
        "ib_L":          ib_L,
        "ic_L":          ic_L,
        "ia_diff_ext":   ia_diff_ext,
        "ia_diff_int":   ia_diff_int,
        "i_diff_ext_mag": i_diff_ext,
        "i_diff_int_mag": i_diff_int,
        "i_rst_ext":     i_rst_ext,
        "i_rst_int":     i_rst_int,
        "V_pre_bus1":    V_pre_bus1,
        "V_pre_bus2":    V_pre_bus2,
        "Z_line":        Z_line,
        "meta": {
            "case_file":   result.case_file,
            "line_bus1":   line_bus1,
            "line_bus2":   line_bus2,
            "fault_bus":   result.fault_bus,
            "fault_time":  result.fault_time,
            "clear_time":  result.clear_time,
            "fs_hz":       fs,
            "f0_hz":       f0,
            "Z_line_pu":   abs(Z_line),
            "V_pre_bus1":  V_pre_bus1,
            "V_pre_bus2":  V_pre_bus2,
            "Z_th_remote": abs(z_thevenin_remote),
            "wg_mean_fault": wg_mean_fault,
            "WTDTA1_n":    ss.WTDTA1.n,
            "n_samples":   len(t_new),
        },
    }


# ---------------------------------------------------------------------------
# Generator model info (for SAMBP config cross-check)
# ---------------------------------------------------------------------------

def get_genrou_params(result: AndesResult) -> list[dict]:
    """
    Return list of GENROU parameter dicts, one per generator.
    Keys match SAMBP system_config.py naming convention.
    """
    ss = result.ss
    if ss.GENROU.n == 0:
        return []

    params = []
    for i in range(ss.GENROU.n):
        params.append({
            "bus":      ss.GENROU.bus.v[i],
            "Xd_pu":    ss.GENROU.xd.v[i],
            "Xdp_pu":   ss.GENROU.xd1.v[i],
            "Xdpp_pu":  ss.GENROU.xd2.v[i],
            "Xq_pu":    ss.GENROU.xq.v[i],
            "Xqp_pu":   ss.GENROU.xq1.v[i],
            "Xqpp_pu":  ss.GENROU.xq2.v[i],
            "Tdp_s":    ss.GENROU.Td10.v[i],
            "Tdpp_s":   ss.GENROU.Td20.v[i],
            "H_s":      ss.GENROU.M.v[i] / 2.0,   # ANDES stores 2H
            "D_pu":     ss.GENROU.D.v[i],
            "Ra_pu":    ss.GENROU.ra.v[i],
        })
    return params
