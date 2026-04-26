import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

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
# Heuristic family scoring
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
    # smoother bounded oscillatory-control response
    rise = (1.0 - np.exp(-tau / tau_rise))
    fall = np.exp(-tau / tau_fall)
    return K * rise * fall * np.sin(2 * np.pi * f_ctrl * tau + phi)


def model_grid_following_inverter_like_v2(tau, K, tau_rise, tau_fall):
    # current-limited monotone envelope
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
        return {'rmse': np.nan, 'r2': np.nan, 'y_hat_full': np.zeros_like(t)}

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

        y_hat_full = np.zeros_like(t)
        tmp = np.zeros_like(tau)
        tmp[fit_mask] = y_hat
        y_hat_full[mask] = tmp

        return {'rmse': float(rmse), 'r2': float(r2), 'y_hat_full': y_hat_full}

    except Exception:
        return {'rmse': np.nan, 'r2': np.nan, 'y_hat_full': np.zeros_like(t)}


def family_residual_scoring_v2(t, ta, tb, tc, t_event):
    families = [
        'induction_machine_like',
        'dfig_like',
        'full_converter_pmsg_like',
        'grid_following_inverter_like'
    ]

    family_errors = {}
    family_models = {}

    for fam in families:
        fit_a = fit_family_model_to_signal_v2(t, ta, t_event, fam)
        fit_b = fit_family_model_to_signal_v2(t, tb, t_event, fam)
        fit_c = fit_family_model_to_signal_v2(t, tc, t_event, fam)

        rmses = [fit_a['rmse'], fit_b['rmse'], fit_c['rmse']]
        rmses = [r for r in rmses if np.isfinite(r)]
        mean_rmse = np.mean(rmses) if len(rmses) else np.nan

        family_errors[fam] = mean_rmse
        family_models[fam] = {'A': fit_a, 'B': fit_b, 'C': fit_c}

    residual_probs = softmax_like_from_errors(family_errors, sharpness=7.0)
    return family_errors, residual_probs, family_models


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
# Main workflow
# ============================================================

def generator_aware_inverse_model_selector_v3(
    input_csv='Z_Final_Thesis_data/ch6_AI_ML/fault_data.csv',
    output_data_dir='Z_Final_Thesis_data/ch6_generator_aware_selector_v3',
    output_fig_dir='Z_Final_Thesis_figures/ch6_generator_aware_selector_v3',
    f0=50.0
):
    os.makedirs(output_data_dir, exist_ok=True)
    os.makedirs(output_fig_dir, exist_ok=True)

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

    ia_noise = ra2 - ta_fit
    ib_noise = rb2 - tb_fit
    ic_noise = rc2 - tc_fit

    features = extract_selector_features(
        t, ia, ib, ic,
        ia_base, ib_base, ic_base,
        ripple, ta_fit, tb_fit, tc_fit,
        envelope_norm, t_event, tau_d
    )

    raw_scores, heuristic_probs, heuristic_winner, heuristic_p1, heuristic_margin = score_source_families(features)

    family_errors, residual_probs, family_models = family_residual_scoring_v2(t, ta_raw, tb_raw, tc_raw, t_event)

    combined_probs, combined_winner, combined_p1, second_family, combined_p2, combined_margin = combine_family_probabilities(
        heuristic_probs, residual_probs, alpha=0.45
    )

    final_family, final_confidence, unknown_reasons = apply_unknown_mixed_logic(
        combined_probs, combined_winner, combined_p1, combined_margin, family_errors
    )

    best_family_for_plot = combined_winner
    best_model = family_models[best_family_for_plot]
    ta_best = best_model['A']['y_hat_full']
    tb_best = best_model['B']['y_hat_full']
    tc_best = best_model['C']['y_hat_full']

    ia_recon = ia_base + ripple + ta_best
    ib_recon = ib_base + ripple + tb_best
    ic_recon = ic_base + ripple + tc_best

    summary = {
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
        summary[f'heuristic_prob_{k}'] = float(v)
    for k, v in residual_probs.items():
        summary[f'residual_prob_{k}'] = float(v)
    for k, v in combined_probs.items():
        summary[f'combined_prob_{k}'] = float(v)
    for k, v in family_errors.items():
        summary[f'family_rmse_{k}'] = float(v) if np.isfinite(v) else np.nan

    summary_df = pd.DataFrame([summary])
    features_df = pd.DataFrame([features])

    summary_csv = os.path.join(output_data_dir, 'generator_aware_selector_v3_summary.csv')
    features_csv = os.path.join(output_data_dir, 'selector_features.csv')
    extracted_csv = os.path.join(output_data_dir, 'extracted_components.csv')
    json_path = os.path.join(output_data_dir, 'generator_aware_selector_v3_summary.json')

    summary_df.to_csv(summary_csv, index=False)
    features_df.to_csv(features_csv, index=False)

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    extracted_df = pd.DataFrame({
        'time_s': t,
        'Ia_pu': ia,
        'Ib_pu': ib,
        'Ic_pu': ic,
        'Ia_base_pu': ia_base,
        'Ib_base_pu': ib_base,
        'Ic_base_pu': ic_base,
        'ripple_pu': ripple,
        'hf_energy': hf_energy,
        'envelope_norm': envelope_norm,
        'Ia_transient_est_pu': ta_best,
        'Ib_transient_est_pu': tb_best,
        'Ic_transient_est_pu': tc_best,
        'Ia_noise_bg_est_pu': ia_noise,
        'Ib_noise_bg_est_pu': ib_noise,
        'Ic_noise_bg_est_pu': ic_noise,
        'Ia_recon_pu': ia_recon,
        'Ib_recon_pu': ib_recon,
        'Ic_recon_pu': ic_recon,
    })
    extracted_df.to_csv(extracted_csv, index=False)

    plt.figure(figsize=(12, 6), dpi=150)
    plt.plot(t, ia, label='Ia')
    plt.plot(t, ib, label='Ib')
    plt.plot(t, ic, label='Ic')
    plt.axvline(t_event, color='k', linestyle='--', linewidth=2, label=f'Event = {t_event:.6f} s')
    plt.xlabel('Time (s)')
    plt.ylabel('Current (pu)')
    plt.title('Original Currents and Detected Event')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '01_original_and_event.png'), bbox_inches='tight')
    plt.show()

    plt.figure(figsize=(12, 5), dpi=150)
    families = list(combined_probs.keys())
    x = np.arange(len(families))
    hvals = [heuristic_probs[f] for f in families]
    rvals = [residual_probs[f] for f in families]
    cvals = [combined_probs[f] for f in families]
    w = 0.25
    plt.bar(x - w, hvals, width=w, label='Heuristic')
    plt.bar(x, rvals, width=w, label='Residual-v2')
    plt.bar(x + w, cvals, width=w, label='Combined')
    plt.xticks(x, families, rotation=15)
    plt.ylim(0, 1.0)
    plt.ylabel('Probability-like score')
    plt.title(f'Family Scoring Comparison | Final: {final_family}')
    plt.grid(True, axis='y', linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '02_family_score_comparison.png'), bbox_inches='tight')
    plt.show()

    plt.figure(figsize=(10, 5), dpi=150)
    fam_err_keys = list(family_errors.keys())
    fam_err_vals = [family_errors[k] for k in fam_err_keys]
    bars = plt.bar(fam_err_keys, fam_err_vals)
    plt.ylabel('Mean RMSE')
    plt.title('Family-Specific Residual Errors (v3)')
    plt.grid(True, axis='y', linestyle=':')
    plt.xticks(rotation=15)
    for b, v in zip(bars, fam_err_vals):
        plt.text(b.get_x() + b.get_width()/2, v, f'{v:.4f}', ha='center', va='bottom', fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '03_family_residual_errors.png'), bbox_inches='tight')
    plt.show()

    plt.figure(figsize=(12, 6), dpi=150)
    plt.plot(t, ib, label='Ib original')
    plt.plot(t, ib_recon, '--', label=f'Ib recon ({best_family_for_plot})')
    plt.plot(t, ic, label='Ic original')
    plt.plot(t, ic_recon, '--', label=f'Ic recon ({best_family_for_plot})')
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Current (pu)')
    plt.title('Original vs Best-Family Reconstruction')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '04_reconstruction_best_family.png'), bbox_inches='tight')
    plt.show()

    print("\nSUCCESS: Generator-aware selector v3 completed.")
    print(f"Summary CSV    : {os.path.abspath(summary_csv)}")
    print(f"Features CSV   : {os.path.abspath(features_csv)}")
    print(f"Extracted CSV  : {os.path.abspath(extracted_csv)}")
    print(f"Figures folder : {os.path.abspath(output_fig_dir)}")

    print("\nHeuristic winner:")
    print(f"  {heuristic_winner} | prob={heuristic_p1:.3f} | margin={heuristic_margin:.3f}")

    print("\nCombined winner:")
    print(f"  {combined_winner} | prob={combined_p1:.3f} | margin={combined_margin:.3f}")

    print("\nFinal decision:")
    print(f"  {final_family} | confidence={final_confidence:.3f}")
    if unknown_reasons:
        print(f"  reasons: {', '.join(unknown_reasons)}")

    print("\nCombined family probabilities:")
    for k, v in combined_probs.items():
        print(f"  {k:32s}: {v:.3f}")

    return summary_df, features_df, extracted_df


if __name__ == "__main__":
    generator_aware_inverse_model_selector_v3(
        input_csv='Z_Final_Thesis_data/ch6_AI_ML/fault_data.csv'
    )