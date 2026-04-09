"""
Description: SNR Validation Plot (Ground Truth vs. Estimation)
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Validation & Visualization
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# 1. LOCK AESTHETICS
try:
    plt.style.use('./thesis.mplstyle')
except:
    plt.rcParams.update({'font.family': 'serif', 'axes.grid': True, 'font.size': 12})

def sine_func(t, A, phi):
    return A * np.sin(2 * np.pi * 50 * t + phi)

def plot_snr_effectiveness(full_csv, raw_csv):
    # --- ROUTING ---
    data_dir = 'Z_Final_Thesis_data/ch6_AI_ML/'
    output_dir = 'Z_Final_Thesis_figures/ch6_Z_Final_Thesis_scripts/'
    os.makedirs(output_dir, exist_ok=True)

    df_full = pd.read_csv(os.path.join(data_dir, full_csv))
    df_raw = pd.read_csv(os.path.join(data_dir, raw_csv))

    t = df_full['time_s'].values
    fault_mask = (t >= 5.995) & (t <= 6.015) # Zoomed into fault inception
    t_plot = t[fault_mask]

    # --- METHOD 1: GROUND TRUTH RESIDUAL ---
    # Signal = Pure Transient, Noise = Background + Ripple
    res_full = (df_full.loc[fault_mask, 'Ib_trans'] + 
                df_full.loc[fault_mask, 'Ib_bg'] + 
                df_full.loc[fault_mask, 'ripple']).values

    # --- METHOD 2: RAW ESTIMATION RESIDUAL ---
    sig_raw = df_raw['Ib_pu'].values
    prefault = (t >= 5.98) & (t < 6.00)
    popt, _ = curve_fit(sine_func, t[prefault], sig_raw[prefault])
    res_raw = sig_raw[fault_mask] - sine_func(t_plot, *popt)

    # --- GENERATE PLOT ---
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(t_plot, res_raw, 'k', alpha=0.4, linewidth=4, label='Estimated Residual (Raw CSV)')
    ax.plot(t_plot, res_full, 'r--', linewidth=1.5, label='Ground Truth Residual (Full CSV)')

    # Annotate inception
    ax.axvline(6.0, color='gray', linestyle=':', alpha=0.7)
    ax.annotate('Fault Inception ($t=6.0$s)', xy=(6.0, 0.1), xytext=(6.002, 0.15),
                arrowprops=dict(arrowstyle='->', color='black'))

    ax.set_title('Residual Signal Comparison: Validation of SNR Calculation', fontweight='bold')
    ax.set_ylabel('Amplitude (pu)')
    ax.set_xlabel('Time (s)')
    ax.legend(loc='upper right')
    
    # 3. EXPORT VECTOR PDF
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'c6_3_plt_snr_validation.pdf')
    plt.savefig(output_path, format='pdf', bbox_inches='tight')
    print(f"✅ Validation Plot Saved: {output_path}")

if __name__ == "__main__":
    plot_snr_effectiveness('fault_data_full.csv', 'fault_data.csv')