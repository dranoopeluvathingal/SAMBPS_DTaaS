"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def plot_integrated_protection(input_csv='fault_data.csv', output_png='integrated_entropy_plot.png'):
    # Load raw data [cite: 2026-03-01]
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print("ERROR: fault_data.csv not found. Generate it first.")
        return

    # Method B Calculation Pipeline [cite: 2026-03-01]
    window = 20  # 2ms window for entropy stability
    df['Fundamental'] = df['Va_kV'].rolling(window=window, center=True).mean()
    df['Residual'] = df['Va_kV'] - df['Fundamental']
    df['Entropy_Density'] = df['Residual'].rolling(window=window).std()
    
    # Define Trip Threshold [cite: 2026-03-01]
    threshold = 0.15
    # Identify exact trigger point (first crossing)
    trigger_point = df[df['Entropy_Density'] > threshold]['time'].min()

    # Visualization Engine
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True, dpi=300)

    # Subplot 1: Three-Phase Voltage (The Physical Waveform)
    ax1.plot(df['time'], df['Va_kV'], label='Phase A (Faulted)', color='red', alpha=0.9)
    ax1.plot(df['time'], df['Vb_kV'], label='Phase B', color='blue', alpha=0.6, linestyle='--')
    ax1.plot(df['time'], df['Vc_kV'], label='Phase C', color='green', alpha=0.6, linestyle=':')
    ax1.axvline(x=2.0, color='black', linestyle='--', label='Fault Inception')
    ax1.set_ylabel('Voltage (kV)', fontsize=12)
    ax1.set_title('Primary Waveform: Phase-to-Ground Fault Inception', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper right')

    # Subplot 2: Method B Entropy (The Protection Metric)
    ax2.plot(df['time'], df['Entropy_Density'], color='black', linewidth=1.5, label='Residual Entropy (σ)')
    ax2.axhline(y=threshold, color='crimson', linestyle=':', label='Trip Threshold (0.15 p.u.)')
    
    # Highlight the Trip Signal
    if not np.isnan(trigger_point):
        ax2.annotate(f'TRIP SIGNAL\nt={trigger_point:.4f}s', 
                     xy=(trigger_point, threshold), xytext=(trigger_point+0.01, threshold+0.3),
                     arrowprops=dict(facecolor='black', shrink=0.05, width=1),
                     fontsize=10, fontweight='bold', color='crimson')
        ax2.axvline(x=trigger_point, color='crimson', alpha=0.3)

    ax2.set_ylabel('Entropy Density (σ)', fontsize=12)
    ax2.set_xlabel('Time (s)', fontsize=12)
    ax2.set_title('Method B Decision Layer: Stochastic Chaos Detection', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')

    plt.xlim(1.98, 2.12) # Focus on the transition zone
    plt.tight_layout()
    plt.savefig(output_png)
    plt.show()
    print(f"SUCCESS: Integrated plot saved as {output_png}")
    print(f"Relay Trip Triggered at: {trigger_point:.6f} seconds")

if __name__ == "__main__":
    plot_integrated_protection()