"""
Description:
    Generator-aware reduced-order source-family inverse model selector
    from three-phase current waveform CSV.

Input CSV required columns:
    time_s, Ia_pu, Ib_pu, Ic_pu

Outputs:
    1. Source-family scores:
         - induction_machine_like
         - dfig_like
         - full_converter_pmsg_like
         - grid_following_inverter_like
    2. Reduced-order transient model parameters
    3. Extracted feature table
    4. Plots

Author:
    Anoop-ready research prototype
"""

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
    """
    Fit x(t) ≈ a*sin(wt) + b*cos(wt)
    """
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


def transient_model_tau_known(tau, K, f_tr, phi, tau_d):
    return K * np.exp(-tau / tau_d) * np.sin(2 * np.pi * f_tr * tau + phi)


def fit_decay_constant_from_envelope(t, env, t_event):
    def exp_model(tau, A, tau_d, C):
        return A * np.exp(-tau / tau_d) + C

    mask = t >= t_event
    tau = t[mask] - t_event
    y = env[mask]

    if len(tau) < 20:
        return np.nan, None, None

    ymax = np.max(y)
    fit_mask = (y > 0.1 * ymax) & (tau <= 0.03)
    tau_fit = tau[fit_mask]
    y_fit = y[fit_mask]

    if len(tau_fit) < 10:
        return np.nan, None, None

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
        return popt[1], popt, (tau_fit, y_fit)
    except Exception:
        return np.nan, None, None


def fit_phase_transient(t, x, t_event, tau_d, f_bounds=(200.0, 4000.0)):
    mask = t >= t_event
    tau = t[mask] - t_event
    y = x[mask]

    fit_mask = tau <= 0.03
    tau_fit = tau[fit_mask]
    y_fit = y[fit_mask]

    if len(tau_fit) < 20:
        return {
            'K': np.nan,
            'f_tr': np.nan,
            'phi': np.nan,
            'rmse': np.nan,
            'r2': np.nan,
        }

    K0 = max(np.std(y_fit) * 3.0, 1e-3)
    f0 = 1200.0
    phi0 = 0.0

    try:
        popt, _ = curve_fit(
            lambda tau_local, K, f_tr, phi: transient_model_tau_known(tau_local, K, f_tr, phi, tau_d),
            tau_fit,
            y_fit,
            p0=[K0, f0, phi0],
            bounds=([0.0, f_bounds[0], -2*np.pi], [5.0, f_bounds[1], 2*np.pi]),
            maxfev=30000
        )

        K_hat, f_hat, phi_hat = popt
        y_hat = transient_model_tau_known(tau_fit, K_hat, f_hat, phi_hat, tau_d)
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
            'r2': float(r2),
        }
    except Exception:
        return {
            'K': np.nan,
            'f_tr': np.nan,
            'phi': np.nan,
            'rmse': np.nan,
            'r2': np.nan,
        }


def rebuild_transient(t, t_event, fit_dict, tau_d):
    y = np.zeros_like(t)
    if not (np.isfinite(fit_dict['K']) and np.isfinite(fit_dict['f_tr']) and np.isfinite(fit_dict['phi'])):
        return y
    mask = t >= t_event
    tau = t[mask] - t_event
    valid = tau <= 0.03
    y_part = np.zeros_like(tau)
    y_part[valid] = transient_model_tau_known(
        tau[valid], fit_dict['K'], fit_dict['f_tr'], fit_dict['phi'], tau_d
    )
    y[mask] = y_part
    return y


def safe_div(a, b, default=0.0):
    return a / b if abs(b) > 1e-12 else default


def normalize_0_1(x, xmin, xmax):
    if xmax <= xmin:
        return 0.0
    return float(np.clip((x - xmin) / (xmax - xmin), 0.0, 1.0))


# ============================================================
# Feature extraction
# ============================================================

def extract_selector_features(t, ia, ib, ic, ia_base, ib_base, ic_base,
                              ripple, ta, tb, tc, envelope, t_event, tau_d):
    post_mask = t >= t_event
    tau = t[post_mask] - t_event

    if len(tau) < 5:
        raise ValueError("Insufficient post-event data.")

    # Early and later windows
    early_mask = post_mask & (t <= t_event + 0.005)
    late_mask  = post_mask & (t > t_event + 0.005) & (t <= t_event + 0.020)

    # Peak transient strengths
    Ka = np.max(np.abs(ta[post_mask])) if np.any(post_mask) else 0.0
    Kb = np.max(np.abs(tb[post_mask])) if np.any(post_mask) else 0.0
    Kc = np.max(np.abs(tc[post_mask])) if np.any(post_mask) else 0.0

    # Average base amplitude
    base_avg = np.mean([
        np.sqrt(np.mean(ia_base**2)) * np.sqrt(2),
        np.sqrt(np.mean(ib_base**2)) * np.sqrt(2),
        np.sqrt(np.mean(ic_base**2)) * np.sqrt(2)
    ])

    Kavg = np.mean([Ka, Kb, Kc])
    strength_ratio = safe_div(Kavg, base_avg, default=0.0)

    # Phase selectivity
    Kmax = max(Ka, Kb, Kc)
    Kmin = min(Ka, Kb, Kc)
    selectivity_ratio = safe_div(Kmax, Kmin + 1e-6, default=0.0)

    # B/C dominance
    bc_energy = np.mean(tb[post_mask]**2 + tc[post_mask]**2) if np.any(post_mask) else 0.0
    a_energy  = np.mean(ta[post_mask]**2) if np.any(post_mask) else 0.0
    bc_to_a_ratio = safe_div(bc_energy, a_energy + 1e-9, default=0.0)

    # Current limiting / clipping proxy:
    # ratio of post-event RMS to pre-event RMS
    pre_mask = t < t_event
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

    # Early/late energy ratio
    early_energy = np.mean(ta[early_mask]**2 + tb[early_mask]**2 + tc[early_mask]**2) if np.any(early_mask) else 0.0
    late_energy  = np.mean(ta[late_mask]**2 + tb[late_mask]**2 + tc[late_mask]**2) if np.any(late_mask) else 0.0
    early_late_ratio = safe_div(early_energy, late_energy + 1e-9, default=0.0)

    # Ripple significance
    ripple_rms = np.sqrt(np.mean(ripple**2))
    ripple_ratio = safe_div(ripple_rms, base_avg + 1e-9, default=0.0)

    # Envelope behavior
    env_peak = np.max(envelope) if len(envelope) else 0.0
    env_10ms_idx = np.argmin(np.abs(t - (t_event + 0.010)))
    env_10ms = envelope[env_10ms_idx] if 0 <= env_10ms_idx < len(envelope) else 0.0
    env_decay_10ms = safe_div(env_10ms, env_peak + 1e-9, default=0.0)

    # Symmetry / balance of transient
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
# Source-family scoring
# ============================================================

def score_source_families(features):
    """
    Heuristic first-pass family scorer.
    Scores are later normalized to probabilities-like weights.
    """

    strength = features['strength_ratio']
    selectivity = features['selectivity_ratio']
    bc_to_a = features['bc_to_a_ratio']
    current_limit = features['current_limit_ratio']
    early_late = features['early_late_ratio']
    ripple_ratio = features['ripple_ratio']
    env_decay_10ms = features['env_decay_10ms']
    imbalance = features['imbalance_ratio']
    tau_d = features['tau_decay_s']

    # --- Induction-machine-like ---
    # stronger machine-like burst, less hard limiting, broader multi-phase transient
    score_ind = 0.0
    score_ind += 1.4 * normalize_0_1(strength, 0.05, 0.40)
    score_ind += 1.2 * (1.0 - normalize_0_1(current_limit, 1.05, 1.40))
    score_ind += 1.0 * (1.0 - normalize_0_1(selectivity, 2.0, 8.0))
    score_ind += 1.0 * normalize_0_1(early_late, 1.2, 6.0)
    score_ind += 0.8 * normalize_0_1(tau_d, 0.002, 0.012)

    # --- DFIG-like ---
    # machine + converter protection blend, often strong early burst and selective/asymmetric shaping
    score_dfig = 0.0
    score_dfig += 1.3 * normalize_0_1(strength, 0.05, 0.35)
    score_dfig += 1.2 * normalize_0_1(selectivity, 1.5, 8.0)
    score_dfig += 1.1 * normalize_0_1(bc_to_a, 1.5, 10.0)
    score_dfig += 1.0 * normalize_0_1(early_late, 1.5, 8.0)
    score_dfig += 0.9 * normalize_0_1(tau_d, 0.001, 0.010)
    score_dfig += 0.6 * normalize_0_1(imbalance, 0.1, 0.8)

    # --- Full-converter PMSG-like ---
    # control-shaped and current-limited, usually smoother and more bounded than DFIG
    score_pmsg = 0.0
    score_pmsg += 1.4 * (1.0 - normalize_0_1(strength, 0.12, 0.45))
    score_pmsg += 1.4 * (1.0 - normalize_0_1(tau_d, 0.004, 0.015))
    score_pmsg += 1.2 * (1.0 - normalize_0_1(early_late, 2.0, 8.0))
    score_pmsg += 1.0 * normalize_0_1(current_limit, 0.90, 1.20)
    score_pmsg += 0.8 * normalize_0_1(selectivity, 1.2, 5.0)

    # --- Grid-following inverter-like ---
    # strongly current-limited and control-dominated
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
    if s <= 1e-12:
        probs = {k: 0.25 for k in raw}
    else:
        probs = {k: v / s for k, v in raw.items()}

    winner = max(probs, key=probs.get)
    confidence = probs[winner]

    return raw, probs, winner, confidence


# ============================================================
# Main workflow
# ============================================================

def generator_aware_inverse_model_selector(
    input_csv='Z_Final_Thesis_data/ch6_AI_ML/fault_data.csv',
    output_data_dir='Z_Final_Thesis_data/ch6_generator_aware_selector',
    output_fig_dir='Z_Final_Thesis_figures/ch6_generator_aware_selector',
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

    # Base fit
    ia_base, A_a, ph_a = fit_base_sinusoid(ia, t, f0)
    ib_base, A_b, ph_b = fit_base_sinusoid(ib, t, f0)
    ic_base, A_c, ph_c = fit_base_sinusoid(ic, t, f0)

    ra = ia - ia_base
    rb = ib - ib_base
    rc = ic - ic_base

    # Ripple
    ripple_a = butter_filter(ra, fs, [200.0, min(600.0, 0.45 * fs)], 'bandpass')
    ripple_b = butter_filter(rb, fs, [200.0, min(600.0, 0.45 * fs)], 'bandpass')
    ripple_c = butter_filter(rc, fs, [200.0, min(600.0, 0.45 * fs)], 'bandpass')
    ripple = (ripple_a + ripple_b + ripple_c) / 3.0

    ra2 = ra - ripple
    rb2 = rb - ripple
    rc2 = rc - ripple

    # Event detection
    t_event, idx_event, hf_energy, hf_threshold = detect_event_time_from_hf_energy(
        t, ra2, rb2, rc2, fs
    )

    # Transient band extraction
    ta_raw = butter_filter(ra2, fs, [700.0, min(3000.0, 0.45 * fs)], 'bandpass')
    tb_raw = butter_filter(rb2, fs, [700.0, min(3000.0, 0.45 * fs)], 'bandpass')
    tc_raw = butter_filter(rc2, fs, [700.0, min(3000.0, 0.45 * fs)], 'bandpass')

    pre_mask = t < t_event
    ta_raw[pre_mask] *= 0.15
    tb_raw[pre_mask] *= 0.10
    tc_raw[pre_mask] *= 0.10

    # Envelope and decay
    transient_bc_mag = np.sqrt(tb_raw**2 + tc_raw**2)
    env_raw = np.abs(hilbert(transient_bc_mag))
    env_win = ensure_odd(int(0.002 * fs))
    envelope = savgol_filter(env_raw, env_win, polyorder=2, mode='interp')
    envelope = np.clip(envelope, 0, None)
    envelope_norm = envelope / np.max(envelope) if np.max(envelope) > 0 else envelope.copy()

    tau_d, _, _ = fit_decay_constant_from_envelope(t, envelope_norm, t_event)
    if not np.isfinite(tau_d):
        tau_d = 0.0045

    # Per-phase transient fits
    fitA = fit_phase_transient(t, ta_raw, t_event, tau_d)
    fitB = fit_phase_transient(t, tb_raw, t_event, tau_d)
    fitC = fit_phase_transient(t, tc_raw, t_event, tau_d)

    ta_fit = rebuild_transient(t, t_event, fitA, tau_d)
    tb_fit = rebuild_transient(t, t_event, fitB, tau_d)
    tc_fit = rebuild_transient(t, t_event, fitC, tau_d)

    # Noise estimate
    ia_noise = ra2 - ta_fit
    ib_noise = rb2 - tb_fit
    ic_noise = rc2 - tc_fit

    # Feature extraction
    features = extract_selector_features(
        t, ia, ib, ic,
        ia_base, ib_base, ic_base,
        ripple, ta_fit, tb_fit, tc_fit,
        envelope_norm, t_event, tau_d
    )

    raw_scores, family_probs, selected_family, family_confidence = score_source_families(features)

    # Summary
    summary = {
        'input_csv': os.path.abspath(input_csv),
        'fs_Hz': float(fs),
        't_event_s': float(t_event),
        'tau_decay_s': float(tau_d),
        'Ia_base_amp_pu': float(A_a),
        'Ib_base_amp_pu': float(A_b),
        'Ic_base_amp_pu': float(A_c),
        'selected_family': selected_family,
        'family_confidence': float(family_confidence),
        **features,
        **{f'raw_{k}': float(v) for k, v in raw_scores.items()},
        **{f'prob_{k}': float(v) for k, v in family_probs.items()},
        'Ka_fit': float(fitA['K']) if np.isfinite(fitA['K']) else np.nan,
        'Kb_fit': float(fitB['K']) if np.isfinite(fitB['K']) else np.nan,
        'Kc_fit': float(fitC['K']) if np.isfinite(fitC['K']) else np.nan,
        'fa_fit_Hz': float(fitA['f_tr']) if np.isfinite(fitA['f_tr']) else np.nan,
        'fb_fit_Hz': float(fitB['f_tr']) if np.isfinite(fitB['f_tr']) else np.nan,
        'fc_fit_Hz': float(fitC['f_tr']) if np.isfinite(fitC['f_tr']) else np.nan,
        'r2_a': float(fitA['r2']) if np.isfinite(fitA['r2']) else np.nan,
        'r2_b': float(fitB['r2']) if np.isfinite(fitB['r2']) else np.nan,
        'r2_c': float(fitC['r2']) if np.isfinite(fitC['r2']) else np.nan,
    }

    summary_df = pd.DataFrame([summary])
    summary_csv = os.path.join(output_data_dir, 'generator_aware_selector_summary.csv')
    summary_df.to_csv(summary_csv, index=False)

    with open(os.path.join(output_data_dir, 'generator_aware_selector_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    features_df = pd.DataFrame([features])
    features_csv = os.path.join(output_data_dir, 'selector_features.csv')
    features_df.to_csv(features_csv, index=False)

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
        'Ia_transient_est_pu': ta_fit,
        'Ib_transient_est_pu': tb_fit,
        'Ic_transient_est_pu': tc_fit,
        'Ia_noise_bg_est_pu': ia_noise,
        'Ib_noise_bg_est_pu': ib_noise,
        'Ic_noise_bg_est_pu': ic_noise,
    })
    extracted_csv = os.path.join(output_data_dir, 'extracted_components.csv')
    extracted_df.to_csv(extracted_csv, index=False)

    # --------------------------------------------------------
    # Plots
    # --------------------------------------------------------
    # 1) Original currents and event
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

    # 2) Envelope and transient estimates
    plt.figure(figsize=(12, 5), dpi=150)
    plt.plot(t, envelope_norm, label='Envelope')
    plt.plot(t, ta_fit, label='Transient A')
    plt.plot(t, tb_fit, label='Transient B')
    plt.plot(t, tc_fit, label='Transient C')
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Normalized / pu')
    plt.title('Extracted Envelope and Transient Estimates')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '02_envelope_and_transients.png'), bbox_inches='tight')
    plt.show()

    # 3) Source-family probabilities
    fam_names = list(family_probs.keys())
    fam_vals = [family_probs[k] for k in fam_names]

    plt.figure(figsize=(10, 5), dpi=150)
    bars = plt.bar(fam_names, fam_vals)
    plt.ylabel('Score (normalized)')
    plt.title(f'Source-Family Selector Output: {selected_family}')
    plt.ylim(0, 1.0)
    plt.grid(True, axis='y', linestyle=':')
    plt.xticks(rotation=15)
    for b, v in zip(bars, fam_vals):
        plt.text(b.get_x() + b.get_width()/2, v + 0.02, f'{v:.3f}', ha='center')
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '03_source_family_scores.png'), bbox_inches='tight')
    plt.show()

    # 4) Feature radar-like simple bar chart
    feature_plot_keys = [
        'strength_ratio', 'selectivity_ratio', 'bc_to_a_ratio',
        'current_limit_ratio', 'early_late_ratio', 'ripple_ratio',
        'env_decay_10ms', 'imbalance_ratio'
    ]
    vals = [features[k] for k in feature_plot_keys]
    plt.figure(figsize=(12, 5), dpi=150)
    bars = plt.bar(feature_plot_keys, vals)
    plt.ylabel('Feature value')
    plt.title('Selector Features')
    plt.grid(True, axis='y', linestyle=':')
    plt.xticks(rotation=20)
    for b, v in zip(bars, vals):
        plt.text(b.get_x() + b.get_width()/2, v, f'{v:.3f}', ha='center', va='bottom', fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '04_selector_features.png'), bbox_inches='tight')
    plt.show()

    # 5) Original vs base + ripple + transient reconstruction
    ia_recon = ia_base + ripple + ta_fit
    ib_recon = ib_base + ripple + tb_fit
    ic_recon = ic_base + ripple + tc_fit

    plt.figure(figsize=(12, 6), dpi=150)
    plt.plot(t, ib, label='Ib original')
    plt.plot(t, ib_recon, '--', label='Ib recon')
    plt.plot(t, ic, label='Ic original')
    plt.plot(t, ic_recon, '--', label='Ic recon')
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Current (pu)')
    plt.title('Original vs Reduced-Order Reconstruction')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '05_reconstruction.png'), bbox_inches='tight')
    plt.show()

    print("\nSUCCESS: Generator-aware inverse model selector completed.")
    print(f"Input CSV      : {os.path.abspath(input_csv)}")
    print(f"Summary CSV    : {os.path.abspath(summary_csv)}")
    print(f"Features CSV   : {os.path.abspath(features_csv)}")
    print(f"Extracted CSV  : {os.path.abspath(extracted_csv)}")
    print(f"Figures folder : {os.path.abspath(output_fig_dir)}")

    print("\nSelected family:")
    print(f"  {selected_family}")
    print(f"  confidence = {family_confidence:.3f}")

    print("\nFamily probabilities:")
    for k, v in family_probs.items():
        print(f"  {k:32s}: {v:.3f}")

    return summary_df, features_df, extracted_df


if __name__ == "__main__":
    generator_aware_inverse_model_selector(
        input_csv='Z_Final_Thesis_data/ch6_AI_ML/fault_data.csv'
    )