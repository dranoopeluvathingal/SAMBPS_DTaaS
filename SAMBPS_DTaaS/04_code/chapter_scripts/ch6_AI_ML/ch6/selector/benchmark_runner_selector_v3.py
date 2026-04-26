"""
Benchmark runner for generator-aware inverse model selector v3
over the synthetic family-labelled waveform library.

What it does:
    1. Reads library metadata
    2. Runs selector v3 logic on each waveform
    3. Collects predictions and scores
    4. Computes benchmark metrics:
         - classification accuracy
         - known-only accuracy
         - unknown/mixed rate
         - confusion matrices
         - sensitivity vs family, fault type, SCR, noise
    5. Saves benchmark tables

Expected library structure:
    Z_Synthetic_Family_Library/
        waveforms/
        metadata/library_metadata.csv
"""

import os
import json
import time
import numpy as np
import pandas as pd

from scipy.signal import butter, filtfilt, hilbert, savgol_filter
from scipy.optimize import curve_fit


# ============================================================
# Utilities
# ============================================================

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


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


def fit_base_sinusoid(x: np.ndarray, t: np.ndarray, f0: float = 50.0):
    w = 2 * np.pi * f0
    A = np.column_stack([np.sin(w * t), np.cos(w * t)])
    coeffs, _, _, _ = np.linalg.lstsq(A, x, rcond=None)
    a, b = coeffs
    x_fit = A @ coeffs
    amplitude = np.sqrt(a**2 + b**2)
    phase = np.arctan2(b, a)
    return x_fit, amplitude, phase


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


def safe_div(a, b, default=0.0):
    return a / b if abs(b) > 1e-12 else default


def normalize_0_1(x, xmin, xmax):
    if xmax <= xmin:
        return 0.0
    return float(np.clip((x - xmin) / (xmax - xmin), 0.0, 1.0))


def softmax_like_from_errors(error_dict, sharpness=5.0):
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

    p = e / s
    return {k: float(v) for k, v in zip(keys, p)}


# ============================================================
# Generic decomposition
# ============================================================

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
# Feature extraction
# ============================================================

def extract_selector_features(t, ia, ib, ic, ia_base, ib_base, ic_base,
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
# Heuristic scoring
# ============================================================

def score_source_families(features):
    strength = features['strength_ratio']
    selectivity = features['selectivity_ratio']
    bc_to_a = features['bc_to_a_ratio']
    current_limit = features['current_limit_ratio']
    early_late = features['early_late_ratio']
    ripple_ratio = features['ripple_ratio']
    imbalance = features['imbalance_ratio']
    tau_d = features['tau_decay_s']

    score_ind = 0.0
    score_ind += 1.4 * normalize_0_1(strength, 0.05, 0.40)
    score_ind += 1.2 * (1.0 - normalize_0_1(current_limit, 1.05, 1.40))
    score_ind += 1.0 * (1.0 - normalize_0_1(selectivity, 2.0, 8.0))
    score_ind += 1.0 * normalize_0_1(early_late, 1.2, 6.0)
    score_ind += 0.8 * normalize_0_1(tau_d, 0.002, 0.012)

    score_dfig = 0.0
    score_dfig += 1.3 * normalize_0_1(strength, 0.05, 0.35)
    score_dfig += 1.2 * normalize_0_1(selectivity, 1.5, 8.0)
    score_dfig += 1.1 * normalize_0_1(bc_to_a, 1.5, 10.0)
    score_dfig += 1.0 * normalize_0_1(early_late, 1.5, 8.0)
    score_dfig += 0.9 * normalize_0_1(tau_d, 0.001, 0.010)
    score_dfig += 0.6 * normalize_0_1(imbalance, 0.1, 0.8)

    score_pmsg = 0.0
    score_pmsg += 1.4 * (1.0 - normalize_0_1(strength, 0.12, 0.45))
    score_pmsg += 1.4 * (1.0 - normalize_0_1(tau_d, 0.004, 0.015))
    score_pmsg += 1.2 * (1.0 - normalize_0_1(early_late, 2.0, 8.0))
    score_pmsg += 1.0 * normalize_0_1(current_limit, 0.90, 1.20)
    score_pmsg += 0.8 * normalize_0_1(selectivity, 1.2, 5.0)

    score_gfl = 0.0
    score_gfl += 1.6 * (1.0 - normalize_0_1(strength, 0.10, 0.40))
    score_gfl += 1.5 * normalize_0_1(current_limit, 0.85, 1.15)
    score_gfl += 1.1 * (1.0 - normalize_0_1(tau_d, 0.003, 0.010))
    score_gfl += 1.0 * (1.0 - normalize_0_1(early_late, 1.5, 6.0))
    score_gfl += 0.8 * normalize_0_1(selectivity, 1.0, 4.5)
    score_gfl += 0.5 * (1.0 - normalize_0_1(ripple_ratio, 0.01, 0.08))

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
# Stronger family-specific models
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

def combine_family_probabilities(heuristic_probs, residual_probs, alpha=0.45):
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
                              prob_threshold=0.45, margin_threshold=0.10):
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

    if error_spread < 0.01:
        unknown = True
        reasons.append('family_residuals_too_close')

    final_family = 'unknown_or_mixed' if unknown else winner
    final_confidence = winner_prob if not unknown else max(0.0, winner_prob - 0.10)
    return final_family, final_confidence, reasons


# ============================================================
# Single-case selector
# ============================================================

def run_selector_v3_on_file(input_csv, f0=50.0):
    df = pd.read_csv(input_csv)

    required_cols = ['time_s', 'Ia_pu', 'Ib_pu', 'Ic_pu']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    t = df['time_s'].to_numpy()
    ia = df['Ia_pu'].to_numpy()
    ib = df['Ib_pu'].to_numpy()
    ic = df['Ic_pu'].to_numpy()

    fs = estimate_sampling_rate(t)

    ia_base, A_a, ph_a = fit_base_sinusoid(ia, t, f0)
    ib_base, A_b, ph_b = fit_base_sinusoid(ib, t, f0)
    ic_base, A_c, ph_c = fit_base_sinusoid(ic, t, f0)

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

    features = extract_selector_features(
        t, ia, ib, ic,
        ia_base, ib_base, ic_base,
        ripple, ta_fit, tb_fit, tc_fit,
        envelope_norm, t_event, tau_d
    )

    raw_scores, heuristic_probs, heuristic_winner, heuristic_p1, heuristic_margin = score_source_families(features)

    family_errors, family_r2, residual_probs = family_residual_scoring_v2(t, ta_raw, tb_raw, tc_raw, t_event)

    combined_probs, combined_winner, combined_p1, second_family, combined_p2, combined_margin = combine_family_probabilities(
        heuristic_probs, residual_probs, alpha=0.45
    )

    final_family, final_confidence, unknown_reasons = apply_unknown_mixed_logic(
        combined_probs, combined_winner, combined_p1, combined_margin, family_errors
    )

    row = {
        'input_csv': input_csv,
        't_event_s': t_event,
        'tau_decay_s': tau_d,
        'heuristic_winner': heuristic_winner,
        'heuristic_winner_prob': heuristic_p1,
        'heuristic_margin': heuristic_margin,
        'combined_winner': combined_winner,
        'combined_winner_prob': combined_p1,
        'combined_second_family': second_family,
        'combined_second_prob': combined_p2,
        'combined_margin': combined_margin,
        'final_family': final_family,
        'final_confidence': final_confidence,
        'unknown_reasons': '|'.join(unknown_reasons) if unknown_reasons else '',
        **features
    }

    for k, v in heuristic_probs.items():
        row[f'heuristic_prob_{k}'] = v
    for k, v in residual_probs.items():
        row[f'residual_prob_{k}'] = v
    for k, v in combined_probs.items():
        row[f'combined_prob_{k}'] = v
    for k, v in family_errors.items():
        row[f'family_rmse_{k}'] = v
    for k, v in family_r2.items():
        row[f'family_r2_{k}'] = v

    return row


# ============================================================
# Metrics
# ============================================================

def compute_confusion_matrix(df, true_col, pred_col, labels):
    cm = pd.crosstab(
        pd.Categorical(df[true_col], categories=labels),
        pd.Categorical(df[pred_col], categories=labels),
        dropna=False
    )
    cm.index.name = 'true'
    cm.columns.name = 'pred'
    return cm


def summarize_by_group(df, group_cols):
    agg = df.groupby(group_cols).agg(
        n_cases=('case_id', 'count'),
        final_accuracy=('final_correct', 'mean'),
        combined_accuracy=('combined_correct', 'mean'),
        heuristic_accuracy=('heuristic_correct', 'mean'),
        unknown_rate=('is_unknown', 'mean'),
        mean_final_confidence=('final_confidence', 'mean'),
        mean_combined_margin=('combined_margin', 'mean'),
    ).reset_index()
    return agg


# ============================================================
# Main benchmark runner
# ============================================================

def run_benchmark(
    metadata_csv='Z_Synthetic_Family_Library_v2/metadata/library_metadata.csv',
    output_dir='Z_Synthetic_Family_Library_v2/benchmark_results',
    limit_cases=None
):
    ensure_dir(output_dir)

    meta = pd.read_csv(metadata_csv)

    if limit_cases is not None:
        meta = meta.head(limit_cases).copy()

    results = []
    t0 = time.time()

    for idx, row in meta.iterrows():
        try:
            pred = run_selector_v3_on_file(row['filepath'])
            out_row = {**row.to_dict(), **pred}
            results.append(out_row)

            if (idx + 1) % 100 == 0:
                print(f"Processed {idx + 1}/{len(meta)} cases...")
        except Exception as e:
            out_row = row.to_dict()
            out_row.update({
                'run_error': str(e),
                'final_family': 'run_error',
                'combined_winner': 'run_error',
                'heuristic_winner': 'run_error',
                'final_confidence': np.nan,
                'combined_margin': np.nan
            })
            results.append(out_row)

    elapsed = time.time() - t0
    results_df = pd.DataFrame(results)

    # --------------------------------------------------------
    # Accuracy labels
    # --------------------------------------------------------
    results_df['is_unknown'] = results_df['final_family'].eq('unknown_or_mixed')
    results_df['heuristic_correct'] = results_df['heuristic_winner'].eq(results_df['family'])
    results_df['combined_correct'] = results_df['combined_winner'].eq(results_df['family'])
    results_df['final_correct'] = results_df['final_family'].eq(results_df['family'])

    known_mask = ~results_df['is_unknown'] & results_df['final_family'].ne('run_error')

    overall_heuristic_acc = results_df['heuristic_correct'].mean()
    overall_combined_acc = results_df['combined_correct'].mean()
    overall_final_acc = results_df['final_correct'].mean()
    known_only_final_acc = results_df.loc[known_mask, 'final_correct'].mean() if known_mask.any() else np.nan
    unknown_rate = results_df['is_unknown'].mean()

    # --------------------------------------------------------
    # Confusion matrices
    # --------------------------------------------------------
    family_labels = [
        'induction_machine_like',
        'dfig_like',
        'full_converter_pmsg_like',
        'grid_following_inverter_like'
    ]
    final_labels = family_labels + ['unknown_or_mixed', 'run_error']

    cm_heuristic = compute_confusion_matrix(results_df, 'family', 'heuristic_winner', family_labels)
    cm_combined = compute_confusion_matrix(results_df, 'family', 'combined_winner', family_labels)
    cm_final = compute_confusion_matrix(results_df, 'family', 'final_family', final_labels)

    # --------------------------------------------------------
    # Sensitivity summaries
    # --------------------------------------------------------
    by_family = summarize_by_group(results_df, ['family'])
    by_fault = summarize_by_group(results_df, ['fault_type'])
    by_scr = summarize_by_group(results_df, ['scr'])
    by_noise = summarize_by_group(results_df, ['noise_std'])
    by_family_scr = summarize_by_group(results_df, ['family', 'scr'])
    by_family_noise = summarize_by_group(results_df, ['family', 'noise_std'])
    by_family_fault = summarize_by_group(results_df, ['family', 'fault_type'])

    # --------------------------------------------------------
    # Residual separation summary
    # --------------------------------------------------------
    rmse_cols = [c for c in results_df.columns if c.startswith('family_rmse_')]
    residual_sep_rows = []

    for _, r in results_df.iterrows():
        vals = []
        for c in rmse_cols:
            v = r[c]
            if pd.notna(v):
                vals.append(v)
        vals = sorted(vals)
        spread = vals[-1] - vals[0] if len(vals) >= 2 else np.nan
        residual_sep_rows.append(spread)

    results_df['family_residual_spread'] = residual_sep_rows

    residual_summary = pd.DataFrame([{
        'mean_family_residual_spread': results_df['family_residual_spread'].mean(),
        'median_family_residual_spread': results_df['family_residual_spread'].median(),
        'min_family_residual_spread': results_df['family_residual_spread'].min(),
        'max_family_residual_spread': results_df['family_residual_spread'].max(),
    }])

    # --------------------------------------------------------
    # Benchmark summary
    # --------------------------------------------------------
    benchmark_summary = pd.DataFrame([{
        'n_cases': len(results_df),
        'elapsed_seconds': elapsed,
        'overall_heuristic_accuracy': overall_heuristic_acc,
        'overall_combined_accuracy': overall_combined_acc,
        'overall_final_accuracy': overall_final_acc,
        'known_only_final_accuracy': known_only_final_acc,
        'unknown_rate': unknown_rate,
        'mean_final_confidence': results_df['final_confidence'].mean(),
        'mean_combined_margin': results_df['combined_margin'].mean(),
        'mean_family_residual_spread': results_df['family_residual_spread'].mean(),
    }])

    # --------------------------------------------------------
    # Save files
    # --------------------------------------------------------
    results_csv = os.path.join(output_dir, 'benchmark_case_results.csv')
    summary_csv = os.path.join(output_dir, 'benchmark_summary.csv')
    by_family_csv = os.path.join(output_dir, 'benchmark_by_family.csv')
    by_fault_csv = os.path.join(output_dir, 'benchmark_by_fault_type.csv')
    by_scr_csv = os.path.join(output_dir, 'benchmark_by_scr.csv')
    by_noise_csv = os.path.join(output_dir, 'benchmark_by_noise.csv')
    by_family_scr_csv = os.path.join(output_dir, 'benchmark_by_family_scr.csv')
    by_family_noise_csv = os.path.join(output_dir, 'benchmark_by_family_noise.csv')
    by_family_fault_csv = os.path.join(output_dir, 'benchmark_by_family_fault.csv')
    residual_summary_csv = os.path.join(output_dir, 'benchmark_residual_separation_summary.csv')

    cm_heuristic_csv = os.path.join(output_dir, 'confusion_matrix_heuristic.csv')
    cm_combined_csv = os.path.join(output_dir, 'confusion_matrix_combined.csv')
    cm_final_csv = os.path.join(output_dir, 'confusion_matrix_final.csv')

    results_df.to_csv(results_csv, index=False)
    benchmark_summary.to_csv(summary_csv, index=False)
    by_family.to_csv(by_family_csv, index=False)
    by_fault.to_csv(by_fault_csv, index=False)
    by_scr.to_csv(by_scr_csv, index=False)
    by_noise.to_csv(by_noise_csv, index=False)
    by_family_scr.to_csv(by_family_scr_csv, index=False)
    by_family_noise.to_csv(by_family_noise_csv, index=False)
    by_family_fault.to_csv(by_family_fault_csv, index=False)
    residual_summary.to_csv(residual_summary_csv, index=False)

    cm_heuristic.to_csv(cm_heuristic_csv)
    cm_combined.to_csv(cm_combined_csv)
    cm_final.to_csv(cm_final_csv)

    summary_json = os.path.join(output_dir, 'benchmark_summary.json')
    with open(summary_json, 'w', encoding='utf-8') as f:
        json.dump(benchmark_summary.iloc[0].to_dict(), f, indent=2)

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------
    print("\nSUCCESS: Benchmark completed.")
    print(f"Metadata CSV                 : {os.path.abspath(metadata_csv)}")
    print(f"Results CSV                  : {os.path.abspath(results_csv)}")
    print(f"Summary CSV                  : {os.path.abspath(summary_csv)}")
    print(f"Confusion matrix (final)     : {os.path.abspath(cm_final_csv)}")
    print(f"Elapsed time (s)             : {elapsed:.2f}")
    print(f"Total cases                  : {len(results_df)}")
    print(f"Overall heuristic accuracy   : {overall_heuristic_acc:.4f}")
    print(f"Overall combined accuracy    : {overall_combined_acc:.4f}")
    print(f"Overall final accuracy       : {overall_final_acc:.4f}")
    print(f"Known-only final accuracy    : {known_only_final_acc:.4f}" if pd.notna(known_only_final_acc) else "Known-only final accuracy    : NaN")
    print(f"Unknown/mixed rate           : {unknown_rate:.4f}")
    print(f"Mean final confidence        : {results_df['final_confidence'].mean():.4f}")
    print(f"Mean combined margin         : {results_df['combined_margin'].mean():.4f}")
    print(f"Mean family residual spread  : {results_df['family_residual_spread'].mean():.6f}")

    return {
        'results_df': results_df,
        'benchmark_summary': benchmark_summary,
        'cm_heuristic': cm_heuristic,
        'cm_combined': cm_combined,
        'cm_final': cm_final,
        'by_family': by_family,
        'by_fault': by_fault,
        'by_scr': by_scr,
        'by_noise': by_noise,
    }


if __name__ == "__main__":
    run_benchmark(
        metadata_csv='Z_Synthetic_Family_Library_v2/metadata/library_metadata.csv',
        output_dir='Z_Synthetic_Family_Library_v2/benchmark_results',
        limit_cases=None
    )