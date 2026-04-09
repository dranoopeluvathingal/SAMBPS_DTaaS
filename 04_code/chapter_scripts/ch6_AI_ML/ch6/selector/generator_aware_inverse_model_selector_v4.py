import os
import json
import numpy as np
import pandas as pd

from scipy.signal import butter, filtfilt, hilbert, savgol_filter
from scipy.optimize import curve_fit


# ============================================================
# Utilities
# ============================================================

def ensure_odd(n: int) -> int:
    n = int(max(3, n))
    return n if n % 2 == 1 else n + 1


def estimate_sampling_rate(t: np.ndarray) -> float:
    dt = np.median(np.diff(t))
    if dt <= 0:
        raise ValueError("Invalid time vector.")
    return 1.0 / dt


def butter_filter(x: np.ndarray, fs: float, cutoff, btype: str, order: int = 4) -> np.ndarray:
    nyq = 0.5 * fs
    wn = np.array(cutoff, dtype=float) / nyq
    b, a = butter(order, wn, btype=btype)
    return filtfilt(b, a, x)


def safe_div(a, b, default=0.0):
    return a / b if np.abs(b) > 1e-12 else default


def normalize_0_1(x, xmin, xmax):
    if xmax <= xmin:
        return 0.0
    return float(np.clip((x - xmin) / (xmax - xmin), 0.0, 1.0))


def softmax_like_from_errors(error_dict, sharpness=6.0):
    keys = list(error_dict.keys())
    vals = np.array([error_dict[k] for k in keys], dtype=float)

    finite_mask = np.isfinite(vals)
    if not np.any(finite_mask):
        return {k: 1.0 / len(keys) for k in keys}

    ref = np.min(vals[finite_mask])
    scores = np.full_like(vals, -np.inf, dtype=float)
    scores[finite_mask] = -sharpness * (vals[finite_mask] - ref)

    m = np.max(scores[finite_mask])
    e = np.zeros_like(vals, dtype=float)
    e[finite_mask] = np.exp(scores[finite_mask] - m)

    s = np.sum(e)
    if s <= 1e-12:
        return {k: 1.0 / len(keys) for k in keys}

    probs = e / s
    return {k: float(v) for k, v in zip(keys, probs)}


# ============================================================
# Base fitting
# ============================================================

def fit_base_sinusoid(x: np.ndarray, t: np.ndarray, f0: float = 50.0):
    w = 2 * np.pi * f0
    A = np.column_stack([np.sin(w * t), np.cos(w * t)])
    coeffs, _, _, _ = np.linalg.lstsq(A, x, rcond=None)
    a, b = coeffs
    x_fit = A @ coeffs
    amplitude = np.sqrt(a**2 + b**2)
    phase = np.arctan2(b, a)
    return x_fit, amplitude, phase


# ============================================================
# Symmetrical components
# ============================================================

def abc_to_sequence(a, b, c):
    """
    Complex symmetrical components from phase phasor-like quantities.
    """
    alpha = np.exp(1j * 2 * np.pi / 3)

    x0 = (a + b + c) / 3.0
    x1 = (a + alpha * b + alpha**2 * c) / 3.0
    x2 = (a + alpha**2 * b + alpha * c) / 3.0

    return x0, x1, x2


def analytic_signal(x):
    return hilbert(x)


def instantaneous_sequence_components(va, vb, vc, ia, ib, ic):
    """
    Use analytic signals to build complex instantaneous symmetrical components.
    """
    Va = analytic_signal(va)
    Vb = analytic_signal(vb)
    Vc = analytic_signal(vc)

    Ia = analytic_signal(ia)
    Ib = analytic_signal(ib)
    Ic = analytic_signal(ic)

    V0, V1, V2 = abc_to_sequence(Va, Vb, Vc)
    I0, I1, I2 = abc_to_sequence(Ia, Ib, Ic)

    return V0, V1, V2, I0, I1, I2


# ============================================================
# Event detection and envelope
# ============================================================

def detect_event_time_from_hf_energy(t, ia, ib, ic, fs):
    hf_low = 700.0
    hf_high = min(3000.0, 0.45 * fs)

    ia_hf = butter_filter(ia, fs, [hf_low, hf_high], 'bandpass')
    ib_hf = butter_filter(ib, fs, [hf_low, hf_high], 'bandpass')
    ic_hf = butter_filter(ic, fs, [hf_low, hf_high], 'bandpass')

    hf_energy = np.sqrt(0.20 * ia_hf**2 + ib_hf**2 + ic_hf**2)

    win = ensure_odd(int(0.0015 * fs))
    hf_energy_s = savgol_filter(hf_energy, win, polyorder=2, mode='interp')

    n_base = max(20, int(0.2 * len(t)))
    mu = np.mean(hf_energy_s[:n_base])
    sigma = np.std(hf_energy_s[:n_base])
    threshold = mu + 6.0 * sigma

    candidates = np.where(hf_energy_s > threshold)[0]
    idx_event = int(candidates[0]) if len(candidates) else int(np.argmax(hf_energy_s))

    return t[idx_event], idx_event, hf_energy_s, threshold


def fit_decay_constant_from_envelope(t, env, t_event):
    def exp_model(tau, A, tau_d, C):
        return A * np.exp(-tau / tau_d) + C

    mask = t >= t_event
    tau = t[mask] - t_event
    y = env[mask]

    if len(tau) < 20:
        return np.nan, None

    ymax = np.max(y)
    fit_mask = (y > 0.1 * ymax) & (tau <= 0.03)
    tau_fit = tau[fit_mask]
    y_fit = y[fit_mask]

    if len(tau_fit) < 10:
        return np.nan, None

    p0 = [np.max(y_fit), 0.0045, np.min(y_fit)]

    try:
        popt, _ = curve_fit(
            exp_model,
            tau_fit,
            y_fit,
            p0=p0,
            bounds=([0.0, 1e-4, -1.0], [10.0, 0.05, 1.0]),
            maxfev=20000
        )
        return popt[1], popt
    except Exception:
        return np.nan, None


# ============================================================
# Generic transient fit
# ============================================================

def fit_phase_transient_fixed_tau(t, x, t_event, tau_d, f_bounds=(200.0, 4000.0)):
    def model(tau, K, f_tr, phi):
        return K * np.exp(-tau / tau_d) * np.sin(2 * np.pi * f_tr * tau + phi)

    mask = t >= t_event
    tau = t[mask] - t_event
    y = x[mask]

    fit_mask = tau <= 0.03
    tau_fit = tau[fit_mask]
    y_fit = y[fit_mask]

    if len(tau_fit) < 20:
        return {'K': np.nan, 'f_tr': np.nan, 'phi': np.nan, 'rmse': np.nan, 'r2': np.nan}

    K0 = max(np.std(y_fit) * 3.0, 1e-3)
    f0 = 1200.0
    phi0 = 0.0

    try:
        popt, _ = curve_fit(
            model,
            tau_fit,
            y_fit,
            p0=[K0, f0, phi0],
            bounds=([0.0, f_bounds[0], -2*np.pi], [5.0, f_bounds[1], 2*np.pi]),
            maxfev=30000
        )
        K_hat, f_hat, phi_hat = popt
        y_hat = model(tau_fit, K_hat, f_hat, phi_hat)

        residual = y_fit - y_hat
        rmse = np.sqrt(np.mean(residual**2))
        ss_res = np.sum(residual**2)
        ss_tot = np.sum((y_fit - np.mean(y_fit))**2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else np.nan

        return {
            'K': float(K_hat),
            'f_tr': float(f_hat),
            'phi': float(phi_hat),
            'rmse': float(rmse),
            'r2': float(r2)
        }
    except Exception:
        return {'K': np.nan, 'f_tr': np.nan, 'phi': np.nan, 'rmse': np.nan, 'r2': np.nan}


def rebuild_transient_fixed_tau(t, t_event, fit_dict, tau_d):
    y = np.zeros_like(t)
    if not (np.isfinite(fit_dict['K']) and np.isfinite(fit_dict['f_tr']) and np.isfinite(fit_dict['phi'])):
        return y

    mask = t >= t_event
    tau = t[mask] - t_event
    valid = tau <= 0.03
    y_part = np.zeros_like(tau)

    y_part[valid] = fit_dict['K'] * np.exp(-tau[valid] / tau_d) * np.sin(
        2 * np.pi * fit_dict['f_tr'] * tau[valid] + fit_dict['phi']
    )
    y[mask] = y_part
    return y


# ============================================================
# Voltage / sequence / impedance / ceiling features
# ============================================================

def compute_voltage_sequence_features(t, V0, V1, V2, I0, I1, I2, t_event):
    pre_mask = t < t_event
    early_mask = (t >= t_event) & (t <= t_event + 0.005)
    late_mask = (t > t_event + 0.005) & (t <= t_event + 0.020)

    V1_pre = np.mean(np.abs(V1[pre_mask])) if np.any(pre_mask) else np.nan
    V1_early = np.mean(np.abs(V1[early_mask])) if np.any(early_mask) else np.nan
    V1_late = np.mean(np.abs(V1[late_mask])) if np.any(late_mask) else np.nan

    I1_pre = np.mean(np.abs(I1[pre_mask])) if np.any(pre_mask) else np.nan
    I1_early = np.mean(np.abs(I1[early_mask])) if np.any(early_mask) else np.nan
    I1_late = np.mean(np.abs(I1[late_mask])) if np.any(late_mask) else np.nan

    I2_early = np.mean(np.abs(I2[early_mask])) if np.any(early_mask) else np.nan
    I2_late = np.mean(np.abs(I2[late_mask])) if np.any(late_mask) else np.nan
    I0_early = np.mean(np.abs(I0[early_mask])) if np.any(early_mask) else np.nan
    I0_late = np.mean(np.abs(I0[late_mask])) if np.any(late_mask) else np.nan

    V2_early = np.mean(np.abs(V2[early_mask])) if np.any(early_mask) else np.nan
    V0_early = np.mean(np.abs(V0[early_mask])) if np.any(early_mask) else np.nan

    return {
        'V1_pre': float(V1_pre),
        'V1_early': float(V1_early),
        'V1_late': float(V1_late),
        'I1_pre': float(I1_pre),
        'I1_early': float(I1_early),
        'I1_late': float(I1_late),
        'I2_early': float(I2_early),
        'I2_late': float(I2_late),
        'I0_early': float(I0_early),
        'I0_late': float(I0_late),
        'V2_early': float(V2_early),
        'V0_early': float(V0_early),
        'I2_I1_ratio_early': float(safe_div(I2_early, I1_early, default=np.nan)),
        'I0_I1_ratio_early': float(safe_div(I0_early, I1_early, default=np.nan)),
        'I2_I1_ratio_late': float(safe_div(I2_late, I1_late, default=np.nan)),
        'I0_I1_ratio_late': float(safe_div(I0_late, I1_late, default=np.nan)),
        'Vdip_ratio_early': float(safe_div(V1_early, V1_pre, default=np.nan)),
        'Vdip_ratio_late': float(safe_div(V1_late, V1_pre, default=np.nan)),
        'Iboost_ratio_early': float(safe_div(I1_early, I1_pre, default=np.nan)),
        'Iboost_ratio_late': float(safe_div(I1_late, I1_pre, default=np.nan)),
    }


def compute_dynamic_impedance_features(t, V1, I1, V2, I2, t_event):
    pre_mask = t < t_event
    early_mask = (t >= t_event) & (t <= t_event + 0.005)
    late_mask = (t > t_event + 0.005) & (t <= t_event + 0.020)

    Z1 = np.abs(V1) / (np.abs(I1) + 1e-9)
    Z2 = np.abs(V2) / (np.abs(I2) + 1e-9)

    Z1_pre = np.mean(Z1[pre_mask]) if np.any(pre_mask) else np.nan
    Z1_early = np.mean(Z1[early_mask]) if np.any(early_mask) else np.nan
    Z1_late = np.mean(Z1[late_mask]) if np.any(late_mask) else np.nan

    Z2_early = np.mean(Z2[early_mask]) if np.any(early_mask) else np.nan
    Z2_late = np.mean(Z2[late_mask]) if np.any(late_mask) else np.nan

    dZ1 = Z1_late - Z1_early if np.isfinite(Z1_late) and np.isfinite(Z1_early) else np.nan

    return {
        'Z1_pre': float(Z1_pre),
        'Z1_early': float(Z1_early),
        'Z1_late': float(Z1_late),
        'Z2_early': float(Z2_early),
        'Z2_late': float(Z2_late),
        'dZ1_late_minus_early': float(dZ1) if np.isfinite(dZ1) else np.nan,
        'Z1_ratio_early_pre': float(safe_div(Z1_early, Z1_pre, default=np.nan)),
        'Z1_ratio_late_pre': float(safe_div(Z1_late, Z1_pre, default=np.nan)),
    }


def compute_current_ceiling_features(t, ia, ib, ic, V1, I1, t_event):
    pre_mask = t < t_event
    early_mask = (t >= t_event) & (t <= t_event + 0.005)
    late_mask = (t > t_event + 0.005) & (t <= t_event + 0.020)

    i_mag = np.sqrt((ia**2 + ib**2 + ic**2) / 3.0)

    pre_rms = np.sqrt(np.mean(i_mag[pre_mask]**2)) if np.any(pre_mask) else np.nan
    early_peak = np.max(np.abs(i_mag[early_mask])) if np.any(early_mask) else np.nan
    late_peak = np.max(np.abs(i_mag[late_mask])) if np.any(late_mask) else np.nan

    I1_pre = np.mean(np.abs(I1[pre_mask])) if np.any(pre_mask) else np.nan
    I1_early = np.max(np.abs(I1[early_mask])) if np.any(early_mask) else np.nan
    I1_late = np.max(np.abs(I1[late_mask])) if np.any(late_mask) else np.nan

    V1_pre = np.mean(np.abs(V1[pre_mask])) if np.any(pre_mask) else np.nan
    V1_early = np.mean(np.abs(V1[early_mask])) if np.any(early_mask) else np.nan

    vdef = np.clip(1.0 - safe_div(V1_early, V1_pre, default=np.nan), 0.0, np.inf) if np.isfinite(V1_early) and np.isfinite(V1_pre) else np.nan

    return {
        'current_peak_ratio_early': float(safe_div(early_peak, pre_rms, default=np.nan)),
        'current_peak_ratio_late': float(safe_div(late_peak, pre_rms, default=np.nan)),
        'I1_peak_ratio_early': float(safe_div(I1_early, I1_pre, default=np.nan)),
        'I1_peak_ratio_late': float(safe_div(I1_late, I1_pre, default=np.nan)),
        'current_support_per_vdip': float(safe_div(I1_early - I1_pre, vdef, default=np.nan))
        if np.isfinite(I1_early) and np.isfinite(I1_pre) and np.isfinite(vdef) else np.nan,
        'vdef_early': float(vdef) if np.isfinite(vdef) else np.nan,
    }


# ============================================================
# Current-only base features
# ============================================================

def extract_current_waveform_features(t, ia, ib, ic, ia_base, ib_base, ic_base,
                                      ripple, ta, tb, tc, envelope, t_event, tau_d):
    post_mask = t >= t_event
    early_mask = post_mask & (t <= t_event + 0.005)
    late_mask = post_mask & (t > t_event + 0.005) & (t <= t_event + 0.020)
    pre_mask = t < t_event

    Ka = np.max(np.abs(ta[post_mask])) if np.any(post_mask) else 0.0
    Kb = np.max(np.abs(tb[post_mask])) if np.any(post_mask) else 0.0
    Kc = np.max(np.abs(tc[post_mask])) if np.any(post_mask) else 0.0

    base_avg = np.mean([
        np.sqrt(np.mean(ia_base**2)) * np.sqrt(2),
        np.sqrt(np.mean(ib_base**2)) * np.sqrt(2),
        np.sqrt(np.mean(ic_base**2)) * np.sqrt(2)
    ])

    Kavg = np.mean([Ka, Kb, Kc])
    strength_ratio = safe_div(Kavg, base_avg, default=0.0)

    Kmax = max(Ka, Kb, Kc)
    Kmin = min(Ka, Kb, Kc)
    selectivity_ratio = safe_div(Kmax, Kmin + 1e-6, default=0.0)

    bc_energy = np.mean(tb[post_mask]**2 + tc[post_mask]**2) if np.any(post_mask) else 0.0
    a_energy = np.mean(ta[post_mask]**2) if np.any(post_mask) else 0.0
    bc_to_a_ratio = safe_div(bc_energy, a_energy + 1e-9, default=0.0)

    pre_rms = np.mean([
        np.sqrt(np.mean(ia[pre_mask]**2)) if np.any(pre_mask) else 0.0,
        np.sqrt(np.mean(ib[pre_mask]**2)) if np.any(pre_mask) else 0.0,
        np.sqrt(np.mean(ic[pre_mask]**2)) if np.any(pre_mask) else 0.0,
    ])
    post_rms_early = np.mean([
        np.sqrt(np.mean(ia[early_mask]**2)) if np.any(early_mask) else 0.0,
        np.sqrt(np.mean(ib[early_mask]**2)) if np.any(early_mask) else 0.0,
        np.sqrt(np.mean(ic[early_mask]**2)) if np.any(early_mask) else 0.0,
    ])
    current_limit_ratio = safe_div(post_rms_early, pre_rms + 1e-9, default=0.0)

    early_energy = np.mean(ta[early_mask]**2 + tb[early_mask]**2 + tc[early_mask]**2) if np.any(early_mask) else 0.0
    late_energy = np.mean(ta[late_mask]**2 + tb[late_mask]**2 + tc[late_mask]**2) if np.any(late_mask) else 0.0
    early_late_ratio = safe_div(early_energy, late_energy + 1e-9, default=0.0)

    ripple_rms = np.sqrt(np.mean(ripple**2))
    ripple_ratio = safe_div(ripple_rms, base_avg + 1e-9, default=0.0)

    env_peak = np.max(envelope) if len(envelope) else 0.0
    env_10ms_idx = np.argmin(np.abs(t - (t_event + 0.010)))
    env_10ms = envelope[env_10ms_idx] if 0 <= env_10ms_idx < len(envelope) else 0.0
    env_decay_10ms = safe_div(env_10ms, env_peak + 1e-9, default=0.0)

    transient_std = np.std([Ka, Kb, Kc])
    transient_mean = np.mean([Ka, Kb, Kc]) + 1e-9
    imbalance_ratio = transient_std / transient_mean

    return {
        'Ka': float(Ka),
        'Kb': float(Kb),
        'Kc': float(Kc),
        'strength_ratio': float(strength_ratio),
        'selectivity_ratio': float(selectivity_ratio),
        'bc_to_a_ratio': float(bc_to_a_ratio),
        'current_limit_ratio': float(current_limit_ratio),
        'early_late_ratio': float(early_late_ratio),
        'ripple_ratio': float(ripple_ratio),
        'env_decay_10ms': float(env_decay_10ms),
        'imbalance_ratio': float(imbalance_ratio),
        'tau_decay_s': float(tau_d),
    }


# ============================================================
# Heuristic family scoring with voltage-informed features
# ============================================================

def score_source_families_v4(features):
    strength = features['strength_ratio']
    selectivity = features['selectivity_ratio']
    bc_to_a = features['bc_to_a_ratio']
    current_limit = features['current_limit_ratio']
    early_late = features['early_late_ratio']
    ripple_ratio = features['ripple_ratio']
    imbalance = features['imbalance_ratio']
    tau_d = features['tau_decay_s']

    I2I1_e = features.get('I2_I1_ratio_early', np.nan)
    I0I1_e = features.get('I0_I1_ratio_early', np.nan)
    Z1ratio = features.get('Z1_ratio_early_pre', np.nan)
    support_per_vdip = features.get('current_support_per_vdip', np.nan)
    I1_peak_ratio = features.get('I1_peak_ratio_early', np.nan)
    Vdip_ratio = features.get('Vdip_ratio_early', np.nan)

    # Induction-machine-like:
    # stronger oscillatory energy, less strict ceiling, more machine-like impedance movement
    score_ind = 0.0
    score_ind += 1.1 * normalize_0_1(strength, 0.05, 0.40)
    score_ind += 1.0 * (1.0 - normalize_0_1(current_limit, 1.05, 1.40))
    score_ind += 0.8 * (1.0 - normalize_0_1(selectivity, 2.0, 8.0))
    score_ind += 0.8 * normalize_0_1(early_late, 1.2, 6.0)
    score_ind += 0.7 * normalize_0_1(tau_d, 0.002, 0.012)
    score_ind += 0.7 * (1.0 - normalize_0_1(I1_peak_ratio, 1.2, 2.3))
    score_ind += 0.5 * normalize_0_1(Z1ratio, 0.4, 1.1)

    # DFIG-like:
    # hybrid response, stronger sequence response and hybrid support/ceiling behavior
    score_dfig = 0.0
    score_dfig += 1.0 * normalize_0_1(strength, 0.05, 0.35)
    score_dfig += 0.9 * normalize_0_1(selectivity, 1.5, 8.0)
    score_dfig += 0.8 * normalize_0_1(bc_to_a, 1.5, 10.0)
    score_dfig += 0.8 * normalize_0_1(early_late, 1.5, 8.0)
    score_dfig += 0.8 * normalize_0_1(tau_d, 0.001, 0.010)
    score_dfig += 0.8 * normalize_0_1(imbalance, 0.1, 0.8)
    score_dfig += 0.7 * normalize_0_1(I2I1_e, 0.02, 0.40)
    score_dfig += 0.7 * normalize_0_1(support_per_vdip, 0.0, 3.0)
    score_dfig += 0.4 * normalize_0_1(I1_peak_ratio, 1.0, 2.0)

    # Full-converter PMSG-like:
    # bounded controlled support, smoother than DFIG, not as monotone as GFL
    score_pmsg = 0.0
    score_pmsg += 0.8 * (1.0 - normalize_0_1(strength, 0.12, 0.45))
    score_pmsg += 0.9 * (1.0 - normalize_0_1(tau_d, 0.004, 0.015))
    score_pmsg += 0.8 * (1.0 - normalize_0_1(early_late, 2.0, 8.0))
    score_pmsg += 0.8 * normalize_0_1(current_limit, 0.90, 1.20)
    score_pmsg += 0.7 * normalize_0_1(selectivity, 1.2, 5.0)
    score_pmsg += 0.8 * normalize_0_1(support_per_vdip, 0.3, 2.5)
    score_pmsg += 0.7 * normalize_0_1(I2I1_e, 0.01, 0.20)
    score_pmsg += 0.6 * normalize_0_1(I1_peak_ratio, 1.0, 1.8)
    score_pmsg += 0.5 * (1.0 - normalize_0_1(I0I1_e, 0.02, 0.20))

    # GFL:
    # current-limited, bounded, monotone, strong ceiling
    score_gfl = 0.0
    score_gfl += 1.1 * (1.0 - normalize_0_1(strength, 0.10, 0.40))
    score_gfl += 1.2 * normalize_0_1(current_limit, 0.85, 1.15)
    score_gfl += 0.8 * (1.0 - normalize_0_1(tau_d, 0.003, 0.010))
    score_gfl += 0.8 * (1.0 - normalize_0_1(early_late, 1.5, 6.0))
    score_gfl += 0.7 * normalize_0_1(selectivity, 1.0, 4.5)
    score_gfl += 0.6 * (1.0 - normalize_0_1(ripple_ratio, 0.01, 0.08))
    score_gfl += 1.0 * normalize_0_1(I1_peak_ratio, 1.0, 1.5)
    score_gfl += 0.9 * normalize_0_1(support_per_vdip, 0.0, 1.5)
    score_gfl += 0.7 * (1.0 - normalize_0_1(I2I1_e, 0.05, 0.40))
    score_gfl += 0.6 * (1.0 - normalize_0_1(Z1ratio, 0.6, 1.4))

    raw = {
        'induction_machine_like': max(score_ind, 0.0),
        'dfig_like': max(score_dfig, 0.0),
        'full_converter_pmsg_like': max(score_pmsg, 0.0),
        'grid_following_inverter_like': max(score_gfl, 0.0),
    }

    s = sum(raw.values())
    probs = {k: (v / s if s > 1e-12 else 1.0 / len(raw)) for k, v in raw.items()}

    sorted_items = sorted(probs.items(), key=lambda x: x[1], reverse=True)
    winner, p1 = sorted_items[0]
    _, p2 = sorted_items[1]
    margin = p1 - p2

    return raw, probs, winner, p1, margin


# ============================================================
# Stronger family residual models
# ============================================================

def model_induction_machine_like(tau, K, tau_d, f, phi):
    return K * np.exp(-tau / tau_d) * np.sin(2 * np.pi * f * tau + phi)


def dfig_gate(tau, tg, sharp=0.0003):
    return 1.0 / (1.0 + np.exp((tau - tg) / sharp))


def model_dfig_like_v2(tau, K1, tau1, f1, phi1, K2, tau2, tg):
    g = dfig_gate(tau, tg)
    early = K1 * np.exp(-tau / tau1) * np.sin(2 * np.pi * f1 * tau + phi1)
    late = K2 * np.exp(-tau / tau2)
    return g * early + (1.0 - g) * late


def model_full_converter_pmsg_like_v2(tau, K, tau_rise, tau_fall, f_ctrl, phi):
    rise = (1.0 - np.exp(-tau / tau_rise))
    fall = np.exp(-tau / tau_fall)
    return K * rise * fall * np.sin(2 * np.pi * f_ctrl * tau + phi)


def model_grid_following_inverter_like_v2(tau, K, tau_rise, tau_fall):
    rise = (1.0 - np.exp(-tau / tau_rise))
    fall = np.exp(-tau / tau_fall)
    return K * rise * fall


def fit_family_model_to_signal_v2(t, y, t_event, family_name):
    mask = t >= t_event
    tau = t[mask] - t_event
    yy = y[mask]

    fit_mask = tau <= 0.03
    tau_fit = tau[fit_mask]
    y_fit = yy[fit_mask]

    if len(tau_fit) < 20:
        return {'rmse': np.nan, 'r2': np.nan}

    try:
        if family_name == 'induction_machine_like':
            p0 = [np.max(np.abs(y_fit)) + 1e-3, 0.006, 1000.0, 0.0]
            bounds = ([0.0, 1e-4, 100.0, -2*np.pi], [5.0, 0.05, 4000.0, 2*np.pi])
            popt, _ = curve_fit(model_induction_machine_like, tau_fit, y_fit, p0=p0, bounds=bounds, maxfev=30000)
            y_hat = model_induction_machine_like(tau_fit, *popt)

        elif family_name == 'dfig_like':
            p0 = [np.max(np.abs(y_fit)) + 1e-3, 0.002, 1400.0, 0.0,
                  0.3 * np.max(np.abs(y_fit)) + 1e-3, 0.010, 0.003]
            bounds = ([0.0, 1e-4, 100.0, -2*np.pi, 0.0, 1e-4, 5e-4],
                      [5.0, 0.02, 4000.0, 2*np.pi, 5.0, 0.05, 0.015])
            popt, _ = curve_fit(model_dfig_like_v2, tau_fit, y_fit, p0=p0, bounds=bounds, maxfev=50000)
            y_hat = model_dfig_like_v2(tau_fit, *popt)

        elif family_name == 'full_converter_pmsg_like':
            p0 = [np.max(np.abs(y_fit)) + 1e-3, 0.001, 0.006, 600.0, 0.0]
            bounds = ([0.0, 1e-4, 1e-4, 50.0, -2*np.pi],
                      [5.0, 0.01, 0.05, 2000.0, 2*np.pi])
            popt, _ = curve_fit(model_full_converter_pmsg_like_v2, tau_fit, y_fit, p0=p0, bounds=bounds, maxfev=50000)
            y_hat = model_full_converter_pmsg_like_v2(tau_fit, *popt)

        elif family_name == 'grid_following_inverter_like':
            p0 = [np.max(np.abs(y_fit)) + 1e-3, 0.001, 0.004]
            bounds = ([0.0, 1e-4, 1e-4], [5.0, 0.01, 0.05])
            popt, _ = curve_fit(model_grid_following_inverter_like_v2, tau_fit, np.abs(y_fit), p0=p0, bounds=bounds, maxfev=40000)
            y_hat_abs = model_grid_following_inverter_like_v2(tau_fit, *popt)
            y_hat = np.sign(y_fit + 1e-12) * y_hat_abs

        else:
            raise ValueError(f"Unknown family: {family_name}")

        residual = y_fit - y_hat
        rmse = np.sqrt(np.mean(residual**2))
        ss_res = np.sum(residual**2)
        ss_tot = np.sum((y_fit - np.mean(y_fit))**2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else np.nan

        return {'rmse': float(rmse), 'r2': float(r2)}

    except Exception:
        return {'rmse': np.nan, 'r2': np.nan}


def family_residual_scoring_v2(t, ta, tb, tc, t_event):
    families = [
        'induction_machine_like',
        'dfig_like',
        'full_converter_pmsg_like',
        'grid_following_inverter_like'
    ]

    family_errors = {}
    family_r2 = {}

    for fam in families:
        fit_a = fit_family_model_to_signal_v2(t, ta, t_event, fam)
        fit_b = fit_family_model_to_signal_v2(t, tb, t_event, fam)
        fit_c = fit_family_model_to_signal_v2(t, tc, t_event, fam)

        rmses = [fit_a['rmse'], fit_b['rmse'], fit_c['rmse']]
        rmses = [r for r in rmses if np.isfinite(r)]
        mean_rmse = np.mean(rmses) if len(rmses) else np.nan

        r2s = [fit_a['r2'], fit_b['r2'], fit_c['r2']]
        r2s = [r for r in r2s if np.isfinite(r)]
        mean_r2 = np.mean(r2s) if len(r2s) else np.nan

        family_errors[fam] = mean_rmse
        family_r2[fam] = mean_r2

    residual_probs = softmax_like_from_errors(family_errors, sharpness=7.0)
    return family_errors, family_r2, residual_probs


# ============================================================
# Decision logic
# ============================================================

def combine_family_probabilities(heuristic_probs, residual_probs, alpha=0.40):
    families = heuristic_probs.keys()
    combined = {}
    for fam in families:
        combined[fam] = alpha * heuristic_probs[fam] + (1.0 - alpha) * residual_probs[fam]

    s = sum(combined.values())
    combined = {k: (v / s if s > 1e-12 else 1.0 / len(combined)) for k, v in combined.items()}

    sorted_items = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    winner, p1 = sorted_items[0]
    second, p2 = sorted_items[1]
    margin = p1 - p2
    return combined, winner, p1, second, p2, margin


def apply_unknown_mixed_logic(combined_probs, winner, winner_prob, margin, family_errors,
                              prob_threshold=0.30, margin_threshold=0.03):
    finite_errors = [v for v in family_errors.values() if np.isfinite(v)]
    error_spread = (max(finite_errors) - min(finite_errors)) if len(finite_errors) >= 2 else 0.0

    unknown = False
    reasons = []

    if winner_prob < prob_threshold:
        unknown = True
        reasons.append('low_winner_probability')

    if margin < margin_threshold:
        unknown = True
        reasons.append('small_top_two_margin')

    if error_spread < 0.003:
        unknown = True
        reasons.append('family_residuals_too_close')

    final_family = 'unknown_or_mixed' if unknown else winner
    final_confidence = winner_prob if not unknown else max(0.0, winner_prob - 0.06)

    return final_family, final_confidence, reasons


# ============================================================
# Main selector v4
# ============================================================

def generator_aware_inverse_model_selector_v4(
    input_csv='Z_Synthetic_Family_Library_v2/waveforms/example.csv',
    output_json=None,
    f0=50.0
):
    df = pd.read_csv(input_csv)

    required_cols = ['time_s', 'Va_pu', 'Vb_pu', 'Vc_pu', 'Ia_pu', 'Ib_pu', 'Ic_pu']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    t = df['time_s'].to_numpy()
    va = df['Va_pu'].to_numpy()
    vb = df['Vb_pu'].to_numpy()
    vc = df['Vc_pu'].to_numpy()
    ia = df['Ia_pu'].to_numpy()
    ib = df['Ib_pu'].to_numpy()
    ic = df['Ic_pu'].to_numpy()

    fs = estimate_sampling_rate(t)

    # Current base
    ia_base, A_a, ph_a = fit_base_sinusoid(ia, t, f0)
    ib_base, A_b, ph_b = fit_base_sinusoid(ib, t, f0)
    ic_base, A_c, ph_c = fit_base_sinusoid(ic, t, f0)

    # Voltage base
    va_base, VA_a, Vph_a = fit_base_sinusoid(va, t, f0)
    vb_base, VA_b, Vph_b = fit_base_sinusoid(vb, t, f0)
    vc_base, VA_c, Vph_c = fit_base_sinusoid(vc, t, f0)

    ra = ia - ia_base
    rb = ib - ib_base
    rc = ic - ic_base

    ripple_a = butter_filter(ra, fs, [200.0, min(600.0, 0.45 * fs)], 'bandpass')
    ripple_b = butter_filter(rb, fs, [200.0, min(600.0, 0.45 * fs)], 'bandpass')
    ripple_c = butter_filter(rc, fs, [200.0, min(600.0, 0.45 * fs)], 'bandpass')
    ripple = (ripple_a + ripple_b + ripple_c) / 3.0

    ra2 = ra - ripple
    rb2 = rb - ripple
    rc2 = rc - ripple

    t_event, idx_event, hf_energy, hf_threshold = detect_event_time_from_hf_energy(t, ra2, rb2, rc2, fs)

    ta_raw = butter_filter(ra2, fs, [700.0, min(3000.0, 0.45 * fs)], 'bandpass')
    tb_raw = butter_filter(rb2, fs, [700.0, min(3000.0, 0.45 * fs)], 'bandpass')
    tc_raw = butter_filter(rc2, fs, [700.0, min(3000.0, 0.45 * fs)], 'bandpass')

    pre_mask = t < t_event
    ta_raw[pre_mask] *= 0.15
    tb_raw[pre_mask] *= 0.10
    tc_raw[pre_mask] *= 0.10

    transient_bc_mag = np.sqrt(tb_raw**2 + tc_raw**2)
    env_raw = np.abs(hilbert(transient_bc_mag))
    env_win = ensure_odd(int(0.002 * fs))
    envelope = savgol_filter(env_raw, env_win, polyorder=2, mode='interp')
    envelope = np.clip(envelope, 0, None)
    envelope_norm = envelope / np.max(envelope) if np.max(envelope) > 0 else envelope.copy()

    tau_d, _ = fit_decay_constant_from_envelope(t, envelope_norm, t_event)
    if not np.isfinite(tau_d):
        tau_d = 0.0045

    fitA = fit_phase_transient_fixed_tau(t, ta_raw, t_event, tau_d)
    fitB = fit_phase_transient_fixed_tau(t, tb_raw, t_event, tau_d)
    fitC = fit_phase_transient_fixed_tau(t, tc_raw, t_event, tau_d)

    ta_fit = rebuild_transient_fixed_tau(t, t_event, fitA, tau_d)
    tb_fit = rebuild_transient_fixed_tau(t, t_event, fitB, tau_d)
    tc_fit = rebuild_transient_fixed_tau(t, t_event, fitC, tau_d)

    # Sequence features from analytic signals
    V0, V1, V2, I0, I1, I2 = instantaneous_sequence_components(va, vb, vc, ia, ib, ic)

    current_features = extract_current_waveform_features(
        t, ia, ib, ic,
        ia_base, ib_base, ic_base,
        ripple, ta_fit, tb_fit, tc_fit,
        envelope_norm, t_event, tau_d
    )

    seq_features = compute_voltage_sequence_features(t, V0, V1, V2, I0, I1, I2, t_event)
    imp_features = compute_dynamic_impedance_features(t, V1, I1, V2, I2, t_event)
    ceiling_features = compute_current_ceiling_features(t, ia, ib, ic, V1, I1, t_event)

    features = {}
    features.update(current_features)
    features.update(seq_features)
    features.update(imp_features)
    features.update(ceiling_features)

    raw_scores, heuristic_probs, heuristic_winner, heuristic_p1, heuristic_margin = score_source_families_v4(features)

    family_errors, family_r2, residual_probs = family_residual_scoring_v2(t, ta_raw, tb_raw, tc_raw, t_event)

    combined_probs, combined_winner, combined_p1, second_family, combined_p2, combined_margin = combine_family_probabilities(
        heuristic_probs, residual_probs, alpha=0.40
    )

    final_family, final_confidence, unknown_reasons = apply_unknown_mixed_logic(
        combined_probs, combined_winner, combined_p1, combined_margin, family_errors,
        prob_threshold=0.30, margin_threshold=0.03
    )

    result = {
        'input_csv': os.path.abspath(input_csv),
        'fs_Hz': float(fs),
        't_event_s': float(t_event),
        'tau_decay_s': float(tau_d),
        'heuristic_winner': heuristic_winner,
        'heuristic_winner_prob': float(heuristic_p1),
        'heuristic_margin': float(heuristic_margin),
        'combined_winner': combined_winner,
        'combined_winner_prob': float(combined_p1),
        'combined_second_family': second_family,
        'combined_second_prob': float(combined_p2),
        'combined_margin': float(combined_margin),
        'final_family': final_family,
        'final_confidence': float(final_confidence),
        'unknown_reasons': '|'.join(unknown_reasons) if unknown_reasons else '',
        **features
    }

    for k, v in heuristic_probs.items():
        result[f'heuristic_prob_{k}'] = float(v)
    for k, v in residual_probs.items():
        result[f'residual_prob_{k}'] = float(v)
    for k, v in combined_probs.items():
        result[f'combined_prob_{k}'] = float(v)
    for k, v in family_errors.items():
        result[f'family_rmse_{k}'] = float(v) if np.isfinite(v) else np.nan
    for k, v in family_r2.items():
        result[f'family_r2_{k}'] = float(v) if np.isfinite(v) else np.nan

    if output_json is not None:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

    print("\nSUCCESS: Generator-aware selector v4 completed.")
    print(f"Input CSV      : {os.path.abspath(input_csv)}")
    print(f"Final family   : {final_family}")
    print(f"Confidence     : {final_confidence:.3f}")
    print(f"Combined winner: {combined_winner} | prob={combined_p1:.3f} | margin={combined_margin:.3f}")

    return result

if __name__ == "__main__":
    import glob
    import os

    waveform_folder = 'Z_Synthetic_Family_Library_v2/waveforms'
    csv_files = sorted(glob.glob(os.path.join(waveform_folder, '*.csv')))

    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {waveform_folder}")

    input_csv = csv_files[0]
    print(f"Using input file: {input_csv}")

    result = generator_aware_inverse_model_selector_v4(
        input_csv=input_csv,
        output_json='selector_v4_result.json'
    )