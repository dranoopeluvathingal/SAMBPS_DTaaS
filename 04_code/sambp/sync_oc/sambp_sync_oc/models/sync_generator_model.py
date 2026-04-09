# =============================================================================
# sambp / sambp_sync_oc
# models/sync_generator_model.py
#
# Stage 1: Dynamic fault current synthesis model.
#   Computes phase currents and voltages using a three-component model:
#     1. Fundamental AC term         (steady-state fault current)
#     2. Subtransient decaying AC    (Xd'' → Xd' → Xd envelope)
#     3. DC offset term              (asymmetric decay, time const = X/R)
#
# Stage 2 (future): Replace inner _compute_fault_current() with a full
#   6th-order synchronous machine state-space model.
#
# Public API
# ----------
# simulate_sync_generator_currents(time_s, frequency_hz, fault_time_s,
#                                  fault_type, params, network_params)
#   → dict {t, ia, ib, ic, va, vb, vc}
# =============================================================================

import numpy as np

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _prefault_current(params, network_params):
    """
    Compute pre-fault load current magnitude and angle from P, Q, V_nom.
    Returns I_mag (pu), I_angle (rad).
    """
    V   = params["V_nom_pu"]
    P   = params["P_prefault_pu"]
    Q   = params["Q_prefault_pu"]
    S   = complex(P, Q)
    I   = np.conj(S / complex(V, 0.0))
    return abs(I), np.angle(I)


def _fault_impedance(fault_type, params, network_params):
    """
    Return total fault impedance (complex, pu) for each fault type.
    Stage 1 simplification: LL and SLG use scaling factors on 3PH value.
    """
    Xdpp  = params["Xdpp_pu"]
    Ra    = params["Ra_pu"]
    X_th  = network_params["X_th_pu"]
    R_th  = network_params["R_th_pu"]
    R_f   = network_params["fault_R_pu"]

    Z_src = complex(Ra + R_th, Xdpp + X_th)
    Z_f   = complex(R_f, 0.0)

    if fault_type == "3PH":
        return Z_src + Z_f
    elif fault_type == "LL":
        # Simplified: LL fault sees ~√3 × Z (positive + negative seq)
        return Z_src * 1.732 + Z_f
    elif fault_type == "SLG":
        # Simplified: SLG fault sees ~3 × Z (pos + neg + zero seq)
        return Z_src * 3.0 + Z_f
    else:
        raise ValueError(f"Unknown fault_type: '{fault_type}'. "
                         f"Expected '3PH', 'LL', or 'SLG'.")


def _compute_fault_current(t_rel, params, network_params, fault_type, omega):
    """
    Stage 1 three-component fault current synthesis for phase A (pu).

    Components
    ----------
    AC_ss   : steady-state AC from synchronous reactance Xd
    AC_sub  : subtransient/transient decaying AC overlay
    DC      : exponentially decaying DC offset

    Parameters
    ----------
    t_rel : ndarray — time relative to fault instant (t_rel=0 at fault)
    """
    V     = params["V_nom_pu"]
    Xd    = params["Xd_pu"]
    Xdp   = params["Xdp_pu"]
    Xdpp  = params["Xdpp_pu"]
    Tdp   = params["Tdp_s"]
    Tdpp  = params["Tdpp_s"]
    Ra    = params["Ra_pu"]
    X_th  = network_params["X_th_pu"]
    R_th  = network_params["R_th_pu"]

    # Effective reactances including network
    Xd_eff   = Xd   + X_th
    Xdp_eff  = Xdp  + X_th
    Xdpp_eff = Xdpp + X_th
    R_eff    = Ra   + R_th

    # Steady-state, transient, subtransient peak current amplitudes
    I_ss   = V / Xd_eff
    I_tr   = V / Xdp_eff
    I_sub  = V / Xdpp_eff

    # DC time constant  τ = X'' / (ω·R)
    tau_dc = Xdpp_eff / (omega * R_eff)

    # Phase angle at fault instant (assume voltage peak at t=0)
    phi = np.pi / 2.0

    # --- AC fundamental (steady-state envelope) ---
    I_ac_ss = I_ss * np.sin(omega * t_rel + phi)

    # --- Decaying subtransient / transient AC overlay ---
    dI_sub = (I_sub - I_tr)  * np.exp(-t_rel / Tdpp)
    dI_tr  = (I_tr  - I_ss)  * np.exp(-t_rel / Tdp)
    I_ac_decay = (I_ss + dI_sub + dI_tr) * np.sin(omega * t_rel + phi)

    # --- DC offset (maximum asymmetry) ---
    I_dc = -I_sub * np.exp(-t_rel / tau_dc)

    return I_ac_decay + I_dc


def _phase_shift(signal, omega, t_rel, shift_deg):
    """Return signal phase-shifted by shift_deg degrees (temporal shift)."""
    dt_shift = np.deg2rad(shift_deg) / omega
    # Reconstruct with time shift — valid for narrow-band signal approximation
    # Full implementation interpolates; Stage 1 uses angular substitution
    return signal  # placeholder: phase B/C handled via angle in caller


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def simulate_sync_generator_currents(
    time_s,
    frequency_hz,
    fault_time_s,
    fault_type,
    params,
    network_params,
):
    """
    Simulate three-phase fault currents and voltages from a synchronous
    generator using the Stage 1 synthesis model.

    Parameters
    ----------
    time_s        : ndarray  — full simulation time vector (s)
    frequency_hz  : float    — system frequency (Hz)
    fault_time_s  : float    — fault inception time (s)
    fault_type    : str      — "3PH" | "LL" | "SLG"
    params        : dict     — generator parameters (from SYSTEM_CONFIG)
    network_params: dict     — network parameters (from SYSTEM_CONFIG)

    Returns
    -------
    dict with keys: t, ia, ib, ic, va, vb, vc  (all ndarray, pu)
    """
    omega = 2.0 * np.pi * frequency_hz
    t     = time_s
    n     = len(t)

    # --- Pre-fault: sinusoidal load current ---
    I_pre, phi_pre = _prefault_current(params, network_params)

    ia_pre = I_pre * np.sin(omega * t + phi_pre)
    ib_pre = I_pre * np.sin(omega * t + phi_pre - 2 * np.pi / 3)
    ic_pre = I_pre * np.sin(omega * t + phi_pre + 2 * np.pi / 3)

    # --- Fault current synthesis ---
    t_rel = t - fault_time_s   # relative time from fault instant

    # Phase A fault current (t_rel >= 0)
    ia_fault_a = _compute_fault_current(
        t_rel, params, network_params, fault_type, omega
    )
    # Phase B and C: 120° shifted (using angular offset in t_rel)
    ia_fault_b = _compute_fault_current(
        t_rel - (1.0 / (3.0 * frequency_hz)),   # −120° lag in time
        params, network_params, fault_type, omega
    )
    ia_fault_c = _compute_fault_current(
        t_rel + (1.0 / (3.0 * frequency_hz)),   # +120° lead in time
        params, network_params, fault_type, omega
    )

    # --- Apply fault type phase suppression (Stage 1 simplification) ---
    # LL fault: only phases A and B carry fault current; C unaffected
    # SLG fault: only phase A carries fault current; B and C unaffected
    if fault_type == "LL":
        ia_fault_c = ia_pre[:]   # C stays at pre-fault during fault
    elif fault_type == "SLG":
        ia_fault_b = ia_pre[:]
        ia_fault_c = ia_pre[:]

    # --- Stitch pre-fault and fault windows ---
    fault_mask = t >= fault_time_s

    ia = np.where(fault_mask, ia_fault_a, ia_pre)
    ib = np.where(fault_mask, ia_fault_b, ib_pre)
    ic = np.where(fault_mask, ia_fault_c, ic_pre)

    # --- Voltage: pre-fault nominal sinusoid, drops during fault ---
    V_nom = params["V_nom_pu"]
    Z_f   = abs(_fault_impedance(fault_type, params, network_params))

    # Voltage drop approximation: V_fault ≈ I_fault × Z_f (Stage 1)
    v_drop_factor = min(network_params["fault_R_pu"] / (Z_f + 1e-9), 1.0)

    va_pre  = V_nom * np.sin(omega * t)
    vb_pre  = V_nom * np.sin(omega * t - 2 * np.pi / 3)
    vc_pre  = V_nom * np.sin(omega * t + 2 * np.pi / 3)

    va_flt  = V_nom * v_drop_factor * np.sin(omega * t)
    vb_flt  = V_nom * v_drop_factor * np.sin(omega * t - 2 * np.pi / 3)
    vc_flt  = V_nom * v_drop_factor * np.sin(omega * t + 2 * np.pi / 3)

    va = np.where(fault_mask, va_flt, va_pre)
    vb = np.where(fault_mask, vb_flt, vb_pre)
    vc = np.where(fault_mask, vc_flt, vc_pre)

    return {
        "t":  t,
        "ia": ia,
        "ib": ib,
        "ic": ic,
        "va": va,
        "vb": vb,
        "vc": vc,
    }
