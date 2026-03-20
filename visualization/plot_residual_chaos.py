"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def analyze_entropy_spike(input_csv='fault_data.csv', output_png='entropy_analysis.png'):
    # Load the high-fidelity data
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print("ERROR: CSV not found. Run the data generation script first.")
        return

    # Method B Logic: Extracting Residual Chaos [cite: 2026-03-01]
    # 1. Rolling Mean (Moving Average) to identify the fundamental 50Hz
    window_size = 20  # Approx 2ms at 10kHz sampling
    df['Va_mean'] = df['Va_kV'].rolling(window=window_size, center=True).mean()
    
    # 2. Residual = Raw Signal - Fundamental [cite: 2026-03-01]
    df['Residual'] = df['Va_kV'] - df['Va_mean']
    
    # 3. Noise Density (Entropy Spike) = Rolling Std Dev of Residual [cite: 2026-03-01]
    df['Entropy_Spike'] = df['Residual'].rolling(window=window_size).std()

    # Create the Dual-Panel Visualization
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, dpi=300)

    # Panel 1: Residual Chaos Signal
    ax1.plot(df['time'], df['Residual'], color='magenta', linewidth=1.0)
    ax1.set_ylabel('Residual Chaos (kV)', fontsize=11)
    ax1.set_title('Method B Extraction: Residual Chaos Signal', fontsize=14, fontweight='bold')
    ax1.grid(True, linestyle='--', alpha=0.5)

    # Panel 2: Entropy Spike (The Decision Metric) [cite: 2026-03-01]
    ax2.plot(df['time'], df['Entropy_Spike'], color='black', linewidth=1.5)
    ax2.axhline(y=0.15, color='red', linestyle='--', label='Relay Trip Threshold')
    ax2.set_ylabel('Entropy Density (σ)', fontsize=11)
    ax2.set_xlabel('Time (s)', fontsize=11)
    ax2.set_title('Calculated Entropy Spike at Fault Inception', fontsize=12)
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.legend(loc='upper right')

    # Formatting and Output
    plt.xlim(1.97, 2.15)
    plt.tight_layout()
    plt.savefig(output_png)
    plt.show()
    print(f"SUCCESS: Entropy analysis saved to {output_png}")

if __name__ == "__main__":
    analyze_entropy_spike()