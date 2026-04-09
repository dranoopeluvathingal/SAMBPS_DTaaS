# =============================================================================
# sambp / sambp_sync_oc
# models/reduced_source_model.py
#
# Reduced parametric source model used by the inverse estimator.
#
# Model equation (per phase k):
#
#   i_k(t) = [I_ss + (I_sub − I_ss)·exp(−t_rel/τ_ac)] · sin(ωt + φ_k)
#           + I_dc_k · exp(−t_rel/τ_dc)
#
#   for t ≥ t0; zero before.
#
# DC offset — physics-derived (current continuity at fault inception):
#
#   I_dc_k = −I_sub · sin(φ_k)
#
#   This ensures i_k(t0) = 0 (zero pre-fault from fault reference frame),
#   eliminates I_dc as a free parameter, and makes B/C DC physically
#   consistent with their phase angles — removing the collinearity that
#   caused poor estimator convergence when I_dc was free.
#
# Free parameters (6):   t0, I_ss, I_sub, tau_ac, tau_dc, phi_a
# Derived (per phase):   phi_b = phi_a − 2π/3,  phi_c = phi_a + 2π/3
#                        I_dc_k = −I_sub · sin(phi_k)
#
# Public API
# ----------
# reduced_sync_current_model(t, theta, frequency_hz=50.0)  → dict {ia,ib,ic}
# theta_to_vector(theta)  → ndarray shape (6,)
# theta_from_vector(vec)  → dict
# =============================================================================

import numpy as np

# ---------------------------------------------------------------------------
# Theta key ordering — 6 free parameters (I_dc removed; derived from phi)
# ---------------------------------------------------------------------------
THETA_KEYS = ["t0", "I_ss", "I_sub", "tau_ac", "tau_dc", "phi_a"]


# ---------------------------------------------------------------------------
# Internal: single-phase model
# ---------------------------------------------------------------------------

def _single_phase_current(t, omega, t0, I_ss, I_sub, tau_ac, tau_dc, phi):
    """
    Compute reduced model current for one phase.

    DC offset amplitude is derived from the continuity condition at t = t0:
        I_dc = −I_sub · sin(φ)
    so that the total fault current starts at zero relative to
    the subtransient AC component (zero-state initialisation).

    Parameters
    ----------
    t      : ndarray — time vector (s)
    omega  : float   — angular frequency (rad/s)
    t0     : float   — fault inception time (s)
    I_ss   : float   — steady-state AC amplitude (pu)
    I_sub  : float   — subtransient AC amplitude (pu)  [I_sub > I_ss always]
    tau_ac : float   — AC envelope decay time constant (s)
    tau_dc : float   — DC decay time constant (s)
    phi    : float   — phase angle at fault instant (rad)

    Returns
    -------
    ndarray — current waveform (pu), zero before t0
    """
    t_rel  = t - t0
    active = t_rel >= 0.0
    tr     = np.where(active, t_rel, 0.0)   # clamp to 0 before fault

    # AC envelope: decays from I_sub → I_ss with time constant tau_ac
    envelope = I_ss + (I_sub - I_ss) * np.exp(-tr / (tau_ac + 1e-12))
    i_ac     = envelope * np.sin(omega * t + phi)

    # DC offset: derived from phase angle — no free parameter
    I_dc = -I_sub * np.sin(phi)
    i_dc = I_dc * np.exp(-tr / (tau_dc + 1e-12))

    return np.where(active, i_ac + i_dc, 0.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reduced_sync_current_model(t, theta, frequency_hz=50.0):
    """
    Return model-based three-phase currents from the reduced parameter vector.

    Parameters
    ----------
    t            : ndarray — full simulation time vector (s)
    theta        : dict    — model parameters (see THETA_KEYS)
    frequency_hz : float   — system frequency (Hz), default 50.0

    theta keys  (6 free parameters)
    ----------
    t0      : fault inception time (s)
    I_ss    : steady-state AC amplitude (pu)
    I_sub   : subtransient AC amplitude (pu)  — must be > I_ss physically
    tau_ac  : AC envelope decay time constant (s)
    tau_dc  : DC decay time constant (s)
    phi_a   : phase A angle at fault instant (rad)

    Derived internally
    ------------------
    phi_b   = phi_a − 2π/3
    phi_c   = phi_a + 2π/3
    I_dc_k  = −I_sub · sin(phi_k)   (per phase, from continuity condition)

    Returns
    -------
    dict with keys: ia, ib, ic  (ndarray, pu)
    """
    t     = np.asarray(t, dtype=float)
    omega = 2.0 * np.pi * frequency_hz

    t0     = float(theta["t0"])
    I_ss   = float(theta["I_ss"])
    I_sub  = float(theta["I_sub"])
    tau_ac = float(theta["tau_ac"])
    tau_dc = float(theta["tau_dc"])
    phi_a  = float(theta["phi_a"])

    phi_b  = phi_a - 2.0 * np.pi / 3.0
    phi_c  = phi_a + 2.0 * np.pi / 3.0

    ia = _single_phase_current(t, omega, t0, I_ss, I_sub, tau_ac, tau_dc, phi_a)
    ib = _single_phase_current(t, omega, t0, I_ss, I_sub, tau_ac, tau_dc, phi_b)
    ic = _single_phase_current(t, omega, t0, I_ss, I_sub, tau_ac, tau_dc, phi_c)

    return {"ia": ia, "ib": ib, "ic": ic}


# ---------------------------------------------------------------------------
# Optimiser interface
# ---------------------------------------------------------------------------

def theta_to_vector(theta):
    """
    Flatten theta dict → numpy array ordered by THETA_KEYS.
    Used to pass theta to scipy.optimize routines.

    Returns
    -------
    ndarray, shape (6,)
    """
    return np.array([float(theta[k]) for k in THETA_KEYS])


def theta_from_vector(vec):
    """
    Reconstruct theta dict from flat numpy array.

    Parameters
    ----------
    vec : array-like, length 6 — ordered as THETA_KEYS

    Returns
    -------
    dict
    """
    if len(vec) != len(THETA_KEYS):
        raise ValueError(
            f"Expected vector of length {len(THETA_KEYS)}, got {len(vec)}."
        )
    return {k: float(v) for k, v in zip(THETA_KEYS, vec)}


# ---------------------------------------------------------------------------
# Default initial guess — physically motivated for generator terminal fault
#
#   I_ss  ≈ V / (Xd  + X_th) = 1.0 / (1.8 + 0.15) ≈ 0.51 pu
#   I_sub ≈ V / (Xd''+ X_th) = 1.0 / (0.2 + 0.15) ≈ 2.86 pu
#   tau_ac ≈ Td''  = 0.03 s
#   tau_dc ≈ (Xd'' + X_th) / (ω · R_eff) = 0.35 / (314 · 0.02) ≈ 0.056 s
#   phi_a  = π/2   (voltage at its positive peak at fault inception)
# ---------------------------------------------------------------------------
DEFAULT_THETA = {
    # phi_a = π/2: truth model uses cos(ωt) convention (voltage peak at t0)
    # I_dc_a = -I_sub·sin(π/2) = -I_sub  (full asymmetric DC offset)
    # tau_dc ≈ X''/(ω·R) = 0.35/(314·0.02) ≈ 0.056 s
    "t0":     0.10,
    "I_ss":   0.51,
    "I_sub":  2.86,
    "tau_ac": 0.03,
    "tau_dc": 0.056,
    "phi_a":  1.5708,   # π/2
}
