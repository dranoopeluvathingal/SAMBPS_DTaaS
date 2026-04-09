"""
Description: High-Fidelity Data Generation with 6-Panel Diagnostic Visualization
Project: Thesis AI ML Chapter 6
Author: Dr. Anoop Eluvathingal
Logic Layer: Data Engineering + Component Decomposition
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def generate_full_precision_csv(filename='fault_data_full.csv'):
    # --- INTERNAL ROUTING ---
    data_dir = 'Z_Final_Thesis_data/ch6_AI_ML'
    fig_dir = 'Z_Final_Thesis_figures/ch6_AI_ML'
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(fig_dir, exist_ok=True)
    output_csv = os.path.join(data_dir, filename)

    # --- SIMULATION LOGIC ---
    fs = 10000
    f = 50
    t_start, t_end = 5.98, 6.04
    t = np.arange(t_start, t_end, 1/fs)
    omega = 2 * np.pi * f
    t_fault = 6.0
    transient_duration = 0.01 
    rng = np.random.default_rng(42)

    # 1. Base Balanced Currents
    ia_base = 1.05 * np.sin(omega * t)
    ib_base = 1.05 * np.sin(omega * t - 2 * np.pi / 3)
    ic_base = 1.05 * np.sin(omega * t + 2 * np.pi / 3)

    # 2. Background Noise
    ia_bg = rng.normal(0, 0.008, size=len(t))
    ib_bg = rng.normal(0, 0.008, size=len(t))
    ic_bg = rng.normal(0, 0.008, size=len(t))

    # 3. 7th Harmonic Ripple
    ripple = 0.004 * np.sin(2 * np.pi * (7 * f) * t)

    # 4. Transient Envelope (at t=6.0s)
    tau = t - t_fault
    mask = (tau >= 0) & (tau <= transient_duration)
    envelope = np.zeros_like(t)
    envelope[mask] = np.exp(-tau[mask] / 0.0045)

    # 5. Harmonic Ringing (B-C Fault)
    trans_common = (0.18 * np.sin(2 * np.pi * 900 * tau) + 
                    0.12 * np.sin(2 * np.pi * 1350 * tau + 0.7) + 
                    0.08 * np.sin(2 * np.pi * 2100 * tau - 0.4)) * envelope
    
    trans_a = rng.normal(0, 0.004, len(t)) * envelope
    trans_b = -0.85 * trans_common + (rng.normal(0, 0.06, len(t)) * envelope)
    trans_c = +1.00 * trans_common + (rng.normal(0, 0.06, len(t)) * envelope)

    # 6. Composite Signal (Final)
    ia, ib, ic = ia_base + ia_bg + ripple + trans_a, ib_base + ib_bg + ripple + trans_b, ic_base + ic_bg + ripple + trans_c

    # --- SAVE DETAILED CSV ---
    df = pd.DataFrame({
        'time_s': t, 'Ia_base': ia_base, 'Ib_base': ib_base, 'Ic_base': ic_base,
        'Ia_bg': ia_bg, 'Ib_bg': ib_bg, 'Ic_bg': ic_bg, 'ripple': ripple,
        'envelope': envelope, 'Ia_trans': trans_a, 'Ib_trans': trans_b, 'Ic_trans': trans_c,
        'Ia_pu': ia, 'Ib_pu': ib, 'Ic_pu': ic
    })
    df.to_csv(output_csv, index=False)
    
    return df, output_csv, fig_dir

def plot_diagnostic_decomposition(df, output_dir):
    # STEP 1: LOCK AESTHETICS
    try:
        plt.style.use('./thesis.mplstyle')
    except:
        plt.rcParams.update({'font.family': 'serif', 'font.size': 10, 'axes.grid': True})

    fig, axes = plt.subplots(6, 1, figsize=(10, 14), sharex=True)
    t = df['time_s']

    # Subplot 1: Base Components
    axes[0].plot(t, df['Ia_base'], 'r', label='$I_{a,base}$')
    axes[0].plot(t, df['Ib_base'], 'k', label='$I_{b,base}$')
    axes[0].plot(t, df['Ic_base'], 'b', label='$I_{c,base}$')
    axes[0].set_ylabel('Base (pu)')

    # Subplot 2: Background Noise
    # ADDED LABELS TO REMOVE WARNING
    axes[1].plot(t, df['Ia_bg'], 'r', alpha=0.6, label='Noise A')
    axes[1].plot(t, df['Ib_bg'], 'k', alpha=0.6, label='Noise B')
    axes[1].plot(t, df['Ic_bg'], 'b', alpha=0.6, label='Noise C')
    axes[1].set_ylabel('Noise (pu)')

    # Subplot 3: Ripple
    axes[2].plot(t, df['ripple'], 'g', label='7th Harmonic')
    axes[2].set_ylabel('Ripple (pu)')

    # Subplot 4: Transient Envelope
    axes[3].fill_between(t, 0, df['envelope'], color='orange', alpha=0.3, label='Decay Envelope')
    axes[3].set_ylabel('Envelope')

    # Subplot 5: Pure Transient Components
    # ADDED LABELS TO REMOVE WARNING
    axes[4].plot(t, df['Ia_trans'], 'r', label='Trans. A')
    axes[4].plot(t, df['Ib_trans'], 'k', label='Trans. B')
    axes[4].plot(t, df['Ic_trans'], 'b', label='Trans. C')
    axes[4].set_ylabel('Trans. (pu)')

    # Subplot 6: Final Composite Signal
    axes[5].plot(t, df['Ia_pu'], 'r', label='Total $I_a$')
    axes[5].plot(t, df['Ib_pu'], 'k', label='Total $I_b$')
    axes[5].plot(t, df['Ic_pu'], 'b', label='Total $I_c$')
    axes[5].set_ylabel('Total (pu)')
    axes[5].set_xlabel('Time (s)')

    # Now ax.legend() will find artists with labels for every axis
    for ax in axes:
        ax.set_xlim(5.98, 6.04)
        ax.legend(loc='upper right', fontsize='x-small', framealpha=0.8)

    # STEP 3: EXPORT VECTOR PDF
    plt.tight_layout()
    output_pdf = os.path.join(output_dir, 'c6_1_plt_fault_decomposition.pdf')
    plt.savefig(output_pdf, format='pdf', bbox_inches='tight')
    print(f"✅ Diagnostic Plot Saved (Warning-Free): {output_pdf}")

if __name__ == "__main__":
    data_df, csv_path, figures_path = generate_full_precision_csv()
    plot_diagnostic_decomposition(data_df, figures_path)