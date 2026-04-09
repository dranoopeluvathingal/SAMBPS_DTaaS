"""
Description: Generate CSV data and plot three-phase current waveform in one run
Project: Thesis AI ML Chapter 6
Author: Dr. Anoop Eluvathingal
Logic Layer: Data Processing + Visualization
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def generate_waveform_csv(filename='fault_data.csv'):
    # -----------------------------
    # Step 1: Internal Routing & Taxonomy
    # -----------------------------
    output_dir = 'Z_Final_Thesis_data/ch6_AI_ML'
    os.makedirs(output_dir, exist_ok=True)
    output_csv = os.path.join(output_dir, filename)

    # -----------------------------
    # Simulation parameters (High Precision)
    # -----------------------------
    fs = 10000          # 10kHz sampling
    f = 50              # Fundamental
    t_start, t_end = 5.98, 6.04
    dt = 1 / fs
    t = np.arange(t_start, t_end, dt)
    omega = 2 * np.pi * f

    # Event timing
    t_fault = 6.0
    transient_duration = 1 / (2 * f) # Half cycle decay
    rng = np.random.default_rng(42)

    # -----------------------------
    # Base balanced three-phase currents
    # -----------------------------
    base_mag = 1.05
    ia_base = base_mag * np.sin(omega * t)
    ib_base = base_mag * np.sin(omega * t - 2 * np.pi / 3)
    ic_base = base_mag * np.sin(omega * t + 2 * np.pi / 3)

    # -----------------------------
    # Background Noise & Ripples
    # -----------------------------
    bg_noise_std = 0.008
    ia_noise_bg = rng.normal(0, bg_noise_std, size=len(t))
    ib_noise_bg = rng.normal(0, bg_noise_std, size=len(t))
    ic_noise_bg = rng.normal(0, bg_noise_std, size=len(t))

    ripple = 0.004 * np.sin(2 * np.pi * (7 * f) * t)

    # -----------------------------
    # Fault Transient Logic (B-C Fault)
    # -----------------------------
    tau = t - t_fault
    transient_mask = (tau >= 0) & (tau <= transient_duration)
    envelope = np.zeros_like(t)
    envelope[transient_mask] = np.exp(-tau[transient_mask] / 0.0045)

    # Multi-Harmonic Ringing (900Hz, 1350Hz, 2100Hz)
    trans_common = (
        0.18 * np.sin(2 * np.pi * 900 * tau) +
        0.12 * np.sin(2 * np.pi * 1350 * tau + 0.7) +
        0.08 * np.sin(2 * np.pi * 2100 * tau - 0.4)
    ) * envelope

    # Burst noise for Phases B and C
    burst_b = np.zeros_like(t)
    burst_c = np.zeros_like(t)
    burst_b[transient_mask] = rng.normal(0, 0.06, np.sum(transient_mask)) * envelope[transient_mask]
    burst_c[transient_mask] = rng.normal(0, 0.06, np.sum(transient_mask)) * envelope[transient_mask]

    # Final Signals
    ia = ia_base + ia_noise_bg + ripple
    ib = ib_base + ib_noise_bg + ripple + (-0.85 * trans_common + burst_b)
    ic = ic_base + ic_noise_bg + ripple + (+1.00 * trans_common + burst_c)

    # Export to Data Directory
    df = pd.DataFrame({'time_s': t, 'Ia_pu': ia, 'Ib_pu': ib, 'Ic_pu': ic})
    df.to_csv(output_csv, index=False)
    return output_csv

def plot_waveform_csv(input_csv):
    # -----------------------------
    # Step 1: Lock Aesthetics
    # -----------------------------
    try:
        plt.style.use('./thesis.mplstyle')
    except:
        plt.rcParams.update({'font.family': 'serif', 'font.weight': 'bold'})

    output_dir = 'Z_Final_Thesis_figures/ch6_AI_ML'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'c6_1_plt_three_phase_current_transient.pdf')

    df = pd.read_csv(input_csv)

    # -----------------------------
    # Step 2: Generate Plot
    # -----------------------------
    plt.figure(figsize=(12, 6))
    plt.plot(df['time_s'], df['Ia_pu'], color='red', label='Phase A')
    plt.plot(df['time_s'], df['Ib_pu'], color='black', label='Phase B')
    plt.plot(df['time_s'], df['Ic_pu'], color='blue', label='Phase C')

    plt.xlabel('Time (S)', fontsize=18, fontweight='bold')
    plt.ylabel('Current (pu)', fontsize=18, fontweight='bold')
    plt.xlim(5.98, 6.04)
    plt.ylim(-1.3, 1.7)
    
    # Grid and Legend Aesthetics
    plt.grid(True, linestyle=':', alpha=0.7)
    plt.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=3, frameon=True)

    # -----------------------------
    # Step 3: Vector Output
    # -----------------------------
    plt.tight_layout()
    plt.savefig(output_path, format='pdf', bbox_inches='tight')
    print(f"✅ SUCCESS: Vector PDF saved to {output_path}")

if __name__ == "__main__":
    csv_path = generate_waveform_csv()
    plot_waveform_csv(csv_path)