"""
Description:
    Reduced-order source model estimation from three-phase current waveform CSV

Input CSV required columns:
    time_s, Ia_pu, Ib_pu, Ic_pu

What it does:
    1. Detects event instant automatically
    2. Estimates base 50 Hz components
    3. Extracts transient-dominant residual
    4. Fits reduced-order transient model per phase:
           i_tr,k(t) = K_k * exp(-(t-t0)/tau_d) * sin(2*pi*f_tr*(t-t0) + phi_k),  t >= t0
    5. Builds confidence metrics and plots

Outputs:
    - reduced_order_model_summary.csv
    - extracted_components.csv
    - graphs in output figure folder

Author:
    Anoop-ready workflow version
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.signal import butter, filtfilt, hilbert, savgol_filter
from scipy.optimize import curve_fit


# 1. LOCK AESTHETICS For plots
plt.style.use('./thesis.mplstyle')

# ============================================================
# Utility functions
# ============================================================

def ensure_odd(n: int) -> int:
    n = int(max(3, n))
    return n if n % 2 == 1 else n + 1


def estimate_sampling_rate(t: np.ndarray) -> float:
    dt = np.median(np.diff(t))
    if dt <= 0:
        raise ValueError("Invalid time vector: non-positive time step.")
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
    """
    Detect disturbance start from combined high-frequency energy.
    Stronger weight on B and C because your target waveforms tend to disturb them more.
    """
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

    if len(candidates) == 0:
        idx_event = int(np.argmax(hf_energy_s))
    else:
        idx_event = int(candidates[0])

    return t[idx_event], idx_event, hf_energy_s, threshold


def transient_model_tau_known(tau, K, f_tr, phi, tau_d):
    return K * np.exp(-tau / tau_d) * np.sin(2 * np.pi * f_tr * tau + phi)


def transient_model_full(tau, K, tau_d, f_tr, phi):
    return K * np.exp(-tau / tau_d) * np.sin(2 * np.pi * f_tr * tau + phi)


def fit_decay_constant_from_envelope(t, env, t_event):
    """
    Fit normalized envelope with A*exp(-tau/tau_d)+C
    """
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
        tau_d = popt[1]
        return tau_d, popt, (tau_fit, y_fit)
    except Exception:
        return np.nan, None, None


def fit_phase_transient(t, x, t_event, tau_d, f_bounds=(200.0, 4000.0)):
    """
    Fit per-phase transient:
        x(t) = K exp(-(t-t0)/tau_d) sin(2*pi*f*(t-t0)+phi), t>=t0
    with tau_d fixed from common envelope.
    """
    mask = t >= t_event
    tau = t[mask] - t_event
    y = x[mask]

    # Focus on first ~30 ms after event for fitting
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
            'y_fit': np.full_like(y, np.nan),
            'tau_fit': tau_fit,
            'y_used': y_fit
        }

    # Initial estimates
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

        y_hat_fit = transient_model_tau_known(tau_fit, K_hat, f_hat, phi_hat, tau_d)
        residual = y_fit - y_hat_fit
        rmse = np.sqrt(np.mean(residual**2))

        ss_res = np.sum(residual**2)
        ss_tot = np.sum((y_fit - np.mean(y_fit))**2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else np.nan

        y_hat_full = np.zeros_like(y)
        y_hat_full[fit_mask] = y_hat_fit

        return {
            'K': float(K_hat),
            'f_tr': float(f_hat),
            'phi': float(phi_hat),
            'rmse': float(rmse),
            'r2': float(r2),
            'y_fit': y_hat_full,
            'tau_fit': tau_fit,
            'y_used': y_fit
        }

    except Exception:
        return {
            'K': np.nan,
            'f_tr': np.nan,
            'phi': np.nan,
            'rmse': np.nan,
            'r2': np.nan,
            'y_fit': np.full_like(y, np.nan),
            'tau_fit': tau_fit,
            'y_used': y_fit
        }


def compute_confidence(common_tau_d, fitA, fitB, fitC):
    """
    Simple relay-friendly confidence score 0..1
    """
    scores = []

    if np.isfinite(common_tau_d):
        if 0.0005 <= common_tau_d <= 0.02:
            scores.append(1.0)
        elif 0.0002 <= common_tau_d <= 0.05:
            scores.append(0.6)
        else:
            scores.append(0.2)
    else:
        scores.append(0.0)

    r2_vals = [fitA['r2'], fitB['r2'], fitC['r2']]
    r2_clean = [r for r in r2_vals if np.isfinite(r)]
    if len(r2_clean) > 0:
        mean_r2 = np.mean(np.clip(r2_clean, 0.0, 1.0))
        scores.append(mean_r2)
    else:
        scores.append(0.0)

    freq_vals = [fitA['f_tr'], fitB['f_tr'], fitC['f_tr']]
    freq_clean = [f for f in freq_vals if np.isfinite(f)]
    if len(freq_clean) > 0:
        spread = np.std(freq_clean)
        if spread < 100:
            scores.append(1.0)
        elif spread < 300:
            scores.append(0.7)
        else:
            scores.append(0.3)
    else:
        scores.append(0.0)

    return float(np.clip(np.mean(scores), 0.0, 1.0))


# ============================================================
# Main estimation function
# ============================================================

def estimate_reduced_order_source_model(
    input_csv='Z_Final_Thesis_data/ch6_AI_ML/fault_data.csv',
    output_data_dir='Z_Final_Thesis_data/ch6_reduced_order_model',
    output_fig_dir='Z_Final_Thesis_figures/ch6_reduced_order_model',
    f0=50.0
):
    os.makedirs(output_data_dir, exist_ok=True)
    os.makedirs(output_fig_dir, exist_ok=True)

    # --------------------------------------------------------
    # Load data
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # Base 50 Hz estimation
    # --------------------------------------------------------
    ia_base, A_a, ph_a = fit_base_sinusoid(ia, t, f0)
    ib_base, A_b, ph_b = fit_base_sinusoid(ib, t, f0)
    ic_base, A_c, ph_c = fit_base_sinusoid(ic, t, f0)

    ra = ia - ia_base
    rb = ib - ib_base
    rc = ic - ic_base

    # --------------------------------------------------------
    # Ripple estimation
    # --------------------------------------------------------
    ripple_band_low = 200.0
    ripple_band_high = min(600.0, 0.45 * fs)

    ripple_a = butter_filter(ra, fs, [ripple_band_low, ripple_band_high], 'bandpass')
    ripple_b = butter_filter(rb, fs, [ripple_band_low, ripple_band_high], 'bandpass')
    ripple_c = butter_filter(rc, fs, [ripple_band_low, ripple_band_high], 'bandpass')

    ripple = (ripple_a + ripple_b + ripple_c) / 3.0

    ra2 = ra - ripple
    rb2 = rb - ripple
    rc2 = rc - ripple

    # --------------------------------------------------------
    # Event detection
    # --------------------------------------------------------
    t_event, idx_event, hf_energy, hf_threshold = detect_event_time_from_hf_energy(
        t, ra2, rb2, rc2, fs
    )

    # --------------------------------------------------------
    # Transient extraction
    # --------------------------------------------------------
    trans_band_low = 700.0
    trans_band_high = min(3000.0, 0.45 * fs)

    ta_raw = butter_filter(ra2, fs, [trans_band_low, trans_band_high], 'bandpass')
    tb_raw = butter_filter(rb2, fs, [trans_band_low, trans_band_high], 'bandpass')
    tc_raw = butter_filter(rc2, fs, [trans_band_low, trans_band_high], 'bandpass')

    # Suppress pre-event leakage
    ta = ta_raw.copy()
    tb = tb_raw.copy()
    tc = tc_raw.copy()

    pre_mask = t < t_event
    ta[pre_mask] *= 0.15
    tb[pre_mask] *= 0.10
    tc[pre_mask] *= 0.10

    # --------------------------------------------------------
    # Common envelope and decay constant
    # --------------------------------------------------------
    transient_bc_mag = np.sqrt(tb**2 + tc**2)
    env_raw = np.abs(hilbert(transient_bc_mag))

    env_win = ensure_odd(int(0.002 * fs))
    envelope = savgol_filter(env_raw, env_win, polyorder=2, mode='interp')
    envelope = np.clip(envelope, 0, None)

    if np.max(envelope) > 0:
        envelope_norm = envelope / np.max(envelope)
    else:
        envelope_norm = envelope.copy()

    tau_d, decay_fit_popt, decay_fit_data = fit_decay_constant_from_envelope(t, envelope_norm, t_event)

    if not np.isfinite(tau_d):
        tau_d = 0.0045  # fallback

    tau_vec = np.maximum(t - t_event, 0.0)
    envelope_fit = np.exp(-tau_vec / tau_d)
    envelope_fit[t < t_event] = 0.0
    if np.max(envelope_fit) > 0:
        envelope_fit = envelope_fit / np.max(envelope_fit)

    # --------------------------------------------------------
    # Per-phase transient model fitting
    # --------------------------------------------------------
    fitA = fit_phase_transient(t, ta, t_event, tau_d)
    fitB = fit_phase_transient(t, tb, t_event, tau_d)
    fitC = fit_phase_transient(t, tc, t_event, tau_d)

    # Rebuild fitted transient over full time axis
    def rebuild_full_fit(t, t_event, fit_dict, tau_d):
        y = np.zeros_like(t)
        mask = t >= t_event
        tau = t[mask] - t_event
        valid = tau <= 0.03
        if np.isfinite(fit_dict['K']) and np.isfinite(fit_dict['f_tr']) and np.isfinite(fit_dict['phi']):
            y_part = np.zeros_like(tau)
            y_part[valid] = transient_model_tau_known(
                tau[valid], fit_dict['K'], fit_dict['f_tr'], fit_dict['phi'], tau_d
            )
            y[mask] = y_part
        return y

    ta_fit = rebuild_full_fit(t, t_event, fitA, tau_d)
    tb_fit = rebuild_full_fit(t, t_event, fitB, tau_d)
    tc_fit = rebuild_full_fit(t, t_event, fitC, tau_d)

    # --------------------------------------------------------
    # Noise background = remaining residual
    # --------------------------------------------------------
    ia_noise_bg = ra2 - ta_fit
    ib_noise_bg = rb2 - tb_fit
    ic_noise_bg = rc2 - tc_fit

    # --------------------------------------------------------
    # Reduced-order model summary
    # --------------------------------------------------------
    confidence = compute_confidence(tau_d, fitA, fitB, fitC)

    # Use B and C average as common transient frequency if both valid
    freq_candidates = [fitB['f_tr'], fitC['f_tr']]
    freq_candidates = [f for f in freq_candidates if np.isfinite(f)]
    f_transient_common = float(np.mean(freq_candidates)) if len(freq_candidates) > 0 else np.nan

    summary = {
        'input_csv': os.path.abspath(input_csv),
        'fs_Hz': float(fs),
        'fundamental_freq_Hz': float(f0),
        't_event_s': float(t_event),
        'tau_decay_s': float(tau_d),
        'f_transient_common_Hz': f_transient_common,
        'Ia_base_amp_pu': float(A_a),
        'Ib_base_amp_pu': float(A_b),
        'Ic_base_amp_pu': float(A_c),
        'Ia_base_phase_rad': float(ph_a),
        'Ib_base_phase_rad': float(ph_b),
        'Ic_base_phase_rad': float(ph_c),
        'K_a_pu': float(fitA['K']) if np.isfinite(fitA['K']) else np.nan,
        'K_b_pu': float(fitB['K']) if np.isfinite(fitB['K']) else np.nan,
        'K_c_pu': float(fitC['K']) if np.isfinite(fitC['K']) else np.nan,
        'f_a_Hz': float(fitA['f_tr']) if np.isfinite(fitA['f_tr']) else np.nan,
        'f_b_Hz': float(fitB['f_tr']) if np.isfinite(fitB['f_tr']) else np.nan,
        'f_c_Hz': float(fitC['f_tr']) if np.isfinite(fitC['f_tr']) else np.nan,
        'phi_a_rad': float(fitA['phi']) if np.isfinite(fitA['phi']) else np.nan,
        'phi_b_rad': float(fitB['phi']) if np.isfinite(fitB['phi']) else np.nan,
        'phi_c_rad': float(fitC['phi']) if np.isfinite(fitC['phi']) else np.nan,
        'rmse_a': float(fitA['rmse']) if np.isfinite(fitA['rmse']) else np.nan,
        'rmse_b': float(fitB['rmse']) if np.isfinite(fitB['rmse']) else np.nan,
        'rmse_c': float(fitC['rmse']) if np.isfinite(fitC['rmse']) else np.nan,
        'r2_a': float(fitA['r2']) if np.isfinite(fitA['r2']) else np.nan,
        'r2_b': float(fitB['r2']) if np.isfinite(fitB['r2']) else np.nan,
        'r2_c': float(fitC['r2']) if np.isfinite(fitC['r2']) else np.nan,
        'confidence_0_to_1': float(confidence),
    }

    summary_df = pd.DataFrame([summary])
    summary_csv = os.path.join(output_data_dir, 'reduced_order_model_summary.csv')
    summary_df.to_csv(summary_csv, index=False)

    with open(os.path.join(output_data_dir, 'reduced_order_model_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    # --------------------------------------------------------
    # Save extracted components
    # --------------------------------------------------------
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
        'envelope_raw': envelope_norm,
        'envelope_fit': envelope_fit,
        'Ia_transient_est_pu': ta_fit,
        'Ib_transient_est_pu': tb_fit,
        'Ic_transient_est_pu': tc_fit,
        'Ia_noise_bg_est_pu': ia_noise_bg,
        'Ib_noise_bg_est_pu': ib_noise_bg,
        'Ic_noise_bg_est_pu': ic_noise_bg,
    })

    extracted_csv = os.path.join(output_data_dir, 'extracted_components.csv')
    extracted_df.to_csv(extracted_csv, index=False)

    # --------------------------------------------------------
    # Reconstructed signal
    # --------------------------------------------------------
    ia_recon = ia_base + ripple + ta_fit
    ib_recon = ib_base + ripple + tb_fit
    ic_recon = ic_base + ripple + tc_fit

    # --------------------------------------------------------
    # Plots in .png format for thesis
    # --------------------------------------------------------
    # 1. Original currents with detected event
    plt.figure(figsize=(12, 6), dpi=150)
    plt.plot(t, ia, label='Ia', linewidth=1.5)
    plt.plot(t, ib, label='Ib', linewidth=1.5)
    plt.plot(t, ic, label='Ic', linewidth=1.5)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=2, label=f'Event = {t_event:.6f} s')
    plt.xlabel('Time (s)')
    plt.ylabel('Current (pu)')
    plt.title('Original Currents and Detected Event')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '01_original_and_event.png'), bbox_inches='tight')
    plt.show()

    # 2. Base components
    plt.figure(figsize=(12, 6), dpi=150)
    plt.plot(t, ia_base, label='Ia_base')
    plt.plot(t, ib_base, label='Ib_base')
    plt.plot(t, ic_base, label='Ic_base')
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Base current (pu)')
    plt.title('Estimated Base Components')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '02_base_components.png'), bbox_inches='tight')
    plt.show()

    # 3. HF energy and threshold
    plt.figure(figsize=(12, 4), dpi=150)
    plt.plot(t, hf_energy, label='HF energy', linewidth=1.8)
    plt.axhline(hf_threshold, color='r', linestyle='--', linewidth=1.5, label='Threshold')
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5, label='Detected event')
    plt.xlabel('Time (s)')
    plt.ylabel('HF energy')
    plt.title('Event Detection Metric')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '03_event_detection_metric.png'), bbox_inches='tight')
    plt.show()

    # 4. Envelope and decay fit
    plt.figure(figsize=(12, 4), dpi=150)
    plt.plot(t, envelope_norm, label='Envelope raw', linewidth=2)
    plt.plot(t, envelope_fit, '--', label=f'Envelope fit (tau={tau_d:.6f} s)', linewidth=2)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Normalized magnitude')
    plt.title('Transient Envelope and Fitted Decay')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '04_envelope_decay_fit.png'), bbox_inches='tight')
    plt.show()

    # 5. Estimated transient components
    plt.figure(figsize=(12, 5), dpi=150)
    plt.plot(t, ta_fit, label='Transient A', linewidth=1.5)
    plt.plot(t, tb_fit, label='Transient B', linewidth=1.5)
    plt.plot(t, tc_fit, label='Transient C', linewidth=1.5)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Transient estimate (pu)')
    plt.title('Reduced-Order Transient Model')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '05_transient_model.png'), bbox_inches='tight')
    plt.show()

    # 6. Original vs reconstructed
    plt.figure(figsize=(12, 6), dpi=150)
    plt.plot(t, ib, label='Ib original', linewidth=1.5)
    plt.plot(t, ib_recon, '--', label='Ib reconstructed', linewidth=2)
    plt.plot(t, ic, label='Ic original', linewidth=1.5)
    plt.plot(t, ic_recon, '--', label='Ic reconstructed', linewidth=2)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Current (pu)')
    plt.title('Original vs Reconstructed Currents')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '06_original_vs_reconstructed.png'), bbox_inches='tight')
    plt.show()

    # 7. Background noise estimate
    plt.figure(figsize=(12, 5), dpi=150)
    plt.plot(t, ia_noise_bg, label='Ia noise', linewidth=1.2)
    plt.plot(t, ib_noise_bg, label='Ib noise', linewidth=1.2)
    plt.plot(t, ic_noise_bg, label='Ic noise', linewidth=1.2)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Noise estimate (pu)')
    plt.title('Estimated Background Noise')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '07_background_noise.png'), bbox_inches='tight')
    plt.show()

    # 8. Compact summary figure
    fig, axes = plt.subplots(5, 1, figsize=(12, 14), dpi=150, sharex=True)

    axes[0].plot(t, ia, label='Ia')
    axes[0].plot(t, ib, label='Ib')
    axes[0].plot(t, ic, label='Ic')
    axes[0].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[0].set_ylabel('Original')
    axes[0].grid(True, linestyle=':')
    axes[0].legend()

    axes[1].plot(t, ia_base, label='Ia_base')
    axes[1].plot(t, ib_base, label='Ib_base')
    axes[1].plot(t, ic_base, label='Ic_base')
    axes[1].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[1].set_ylabel('Base')
    axes[1].grid(True, linestyle=':')
    axes[1].legend()

    axes[2].plot(t, envelope_norm, label='Envelope raw')
    axes[2].plot(t, envelope_fit, '--', label='Envelope fit')
    axes[2].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[2].set_ylabel('Envelope')
    axes[2].grid(True, linestyle=':')
    axes[2].legend()

    axes[3].plot(t, ta_fit, label='Ta')
    axes[3].plot(t, tb_fit, label='Tb')
    axes[3].plot(t, tc_fit, label='Tc')
    axes[3].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[3].set_ylabel('Transient')
    axes[3].grid(True, linestyle=':')
    axes[3].legend()

    axes[4].plot(t, ib, label='Ib original')
    axes[4].plot(t, ib_recon, '--', label='Ib recon')
    axes[4].plot(t, ic, label='Ic original')
    axes[4].plot(t, ic_recon, '--', label='Ic recon')
    axes[4].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[4].set_ylabel('Recon')
    axes[4].set_xlabel('Time (s)')
    axes[4].grid(True, linestyle=':')
    axes[4].legend()

    plt.suptitle('Reduced-Order Source Model Estimation Summary')
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, '08_summary.png'), bbox_inches='tight')
    plt.show()

# Note
# "What does the code do?": Updates all 8 diagnostic plot exports to save as vector-based PDFs using the standard thesis naming convention.
# 'Current State': Vector Graphic Generation.
# 'Thesis Logic': Ensuring all figures in Chapter 6 are mathematically scalable and perfectly match the LaTeX template aesthetics.
# 'Goal': Replace the hardcoded .png exports with compliant .pdf routes.

    # --------------------------------------------------------
    # Plots (Updated for Thesis Vector Output)
    # --------------------------------------------------------
    # 1. Original currents with detected event
    plt.figure(figsize=(12, 6), dpi=150)
    plt.plot(t, ia, label='Ia', linewidth=1.5)
    plt.plot(t, ib, label='Ib', linewidth=1.5)
    plt.plot(t, ic, label='Ic', linewidth=1.5)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=2, label=f'Event = {t_event:.6f} s')
    plt.xlabel('Time (s)')
    plt.ylabel('Current (pu)')
    plt.title('Original Currents and Detected Event')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, 'c6_3_plt_original_and_event.pdf'), format='pdf', bbox_inches='tight')
    plt.show()

    # 2. Base components
    plt.figure(figsize=(12, 6), dpi=150)
    plt.plot(t, ia_base, label='Ia_base')
    plt.plot(t, ib_base, label='Ib_base')
    plt.plot(t, ic_base, label='Ic_base')
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Base current (pu)')
    plt.title('Estimated Base Components')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, 'c6_3_plt_base_components.pdf'), format='pdf', bbox_inches='tight')
    plt.show()

    # 3. HF energy and threshold
    plt.figure(figsize=(12, 4), dpi=150)
    plt.plot(t, hf_energy, label='HF energy', linewidth=1.8)
    plt.axhline(hf_threshold, color='r', linestyle='--', linewidth=1.5, label='Threshold')
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5, label='Detected event')
    plt.xlabel('Time (s)')
    plt.ylabel('HF energy')
    plt.title('Event Detection Metric')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, 'c6_3_plt_event_detection_metric.pdf'), format='pdf', bbox_inches='tight')
    plt.show()

    # 4. Envelope and decay fit
    plt.figure(figsize=(12, 4), dpi=150)
    plt.plot(t, envelope_norm, label='Envelope raw', linewidth=2)
    plt.plot(t, envelope_fit, '--', label=f'Envelope fit (tau={tau_d:.6f} s)', linewidth=2)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Normalized magnitude')
    plt.title('Transient Envelope and Fitted Decay')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, 'c6_3_plt_envelope_decay_fit.pdf'), format='pdf', bbox_inches='tight')
    plt.show()

    # 5. Estimated transient components
    plt.figure(figsize=(12, 5), dpi=150)
    plt.plot(t, ta_fit, label='Transient A', linewidth=1.5)
    plt.plot(t, tb_fit, label='Transient B', linewidth=1.5)
    plt.plot(t, tc_fit, label='Transient C', linewidth=1.5)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Transient estimate (pu)')
    plt.title('Reduced-Order Transient Model')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, 'c6_3_plt_transient_model.pdf'), format='pdf', bbox_inches='tight')
    plt.show()

    # 6. Original vs reconstructed
    plt.figure(figsize=(12, 6), dpi=150)
    plt.plot(t, ib, label='Ib original', linewidth=1.5)
    plt.plot(t, ib_recon, '--', label='Ib reconstructed', linewidth=2)
    plt.plot(t, ic, label='Ic original', linewidth=1.5)
    plt.plot(t, ic_recon, '--', label='Ic reconstructed', linewidth=2)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Current (pu)')
    plt.title('Original vs Reconstructed Currents')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, 'c6_3_plt_original_vs_reconstructed.pdf'), format='pdf', bbox_inches='tight')
    plt.show()

    # 7. Background noise estimate
    plt.figure(figsize=(12, 5), dpi=150)
    plt.plot(t, ia_noise_bg, label='Ia noise', linewidth=1.2)
    plt.plot(t, ib_noise_bg, label='Ib noise', linewidth=1.2)
    plt.plot(t, ic_noise_bg, label='Ic noise', linewidth=1.2)
    plt.axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    plt.xlabel('Time (s)')
    plt.ylabel('Noise estimate (pu)')
    plt.title('Estimated Background Noise')
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, 'c6_3_plt_background_noise.pdf'), format='pdf', bbox_inches='tight')
    plt.show()

    # 8. Compact summary figure
    fig, axes = plt.subplots(5, 1, figsize=(12, 14), dpi=150, sharex=True)

    axes[0].plot(t, ia, label='Ia')
    axes[0].plot(t, ib, label='Ib')
    axes[0].plot(t, ic, label='Ic')
    axes[0].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[0].set_ylabel('Original')
    axes[0].grid(True, linestyle=':')
    axes[0].legend()

    axes[1].plot(t, ia_base, label='Ia_base')
    axes[1].plot(t, ib_base, label='Ib_base')
    axes[1].plot(t, ic_base, label='Ic_base')
    axes[1].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[1].set_ylabel('Base')
    axes[1].grid(True, linestyle=':')
    axes[1].legend()

    axes[2].plot(t, envelope_norm, label='Envelope raw')
    axes[2].plot(t, envelope_fit, '--', label='Envelope fit')
    axes[2].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[2].set_ylabel('Envelope')
    axes[2].grid(True, linestyle=':')
    axes[2].legend()

    axes[3].plot(t, ta_fit, label='Ta')
    axes[3].plot(t, tb_fit, label='Tb')
    axes[3].plot(t, tc_fit, label='Tc')
    axes[3].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[3].set_ylabel('Transient')
    axes[3].grid(True, linestyle=':')
    axes[3].legend()

    axes[4].plot(t, ib, label='Ib original')
    axes[4].plot(t, ib_recon, '--', label='Ib recon')
    axes[4].plot(t, ic, label='Ic original')
    axes[4].plot(t, ic_recon, '--', label='Ic recon')
    axes[4].axvline(t_event, color='k', linestyle='--', linewidth=1.5)
    axes[4].set_ylabel('Recon')
    axes[4].set_xlabel('Time (s)')
    axes[4].grid(True, linestyle=':')
    axes[4].legend()

    plt.suptitle('Reduced-Order Source Model Estimation Summary')
    plt.tight_layout()
    plt.savefig(os.path.join(output_fig_dir, 'c6_3_plt_summary.pdf'), format='pdf', bbox_inches='tight')
    plt.show()


    # --------------------------------------------------------
    # Console output
    # --------------------------------------------------------
    print("\nSUCCESS: Reduced-order source model estimation completed.")
    print(f"Input CSV: {os.path.abspath(input_csv)}")
    print(f"Summary CSV: {os.path.abspath(summary_csv)}")
    print(f"Extracted CSV: {os.path.abspath(extracted_csv)}")
    print(f"Figures folder: {os.path.abspath(output_fig_dir)}")

    print("\nEstimated reduced-order model:")
    print(f"  Event time t0        = {summary['t_event_s']:.6f} s")
    print(f"  Decay constant tau_d = {summary['tau_decay_s']:.6f} s")
    print(f"  Common transient f   = {summary['f_transient_common_Hz']:.2f} Hz")
    print(f"  K_a, K_b, K_c        = {summary['K_a_pu']:.4f}, {summary['K_b_pu']:.4f}, {summary['K_c_pu']:.4f} pu")
    print(f"  Confidence           = {summary['confidence_0_to_1']:.3f}")

    return summary_df, extracted_df


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    estimate_reduced_order_source_model(
        input_csv='Z_Final_Thesis_data/ch6_AI_ML/fault_data.csv'
    )