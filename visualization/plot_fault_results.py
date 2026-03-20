"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def generate_thesis_plots(csv_file):
    # 1. Load the generated PSCAD data
    try:
        df = pd.read_csv(csv_file)
    except FileNotFoundError:
        print(f"ERROR: {csv_file} not found. Run the generator first.")
        return

    # 2. Setup Figure for Senior Scientist Level Quality
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    plt.subplots_adjust(hspace=0.3)

    # --- TOP PLOT: Instantaneous Phase Currents ---
    ax1.plot(df['time'], df['ia'], label='Phase A', color='red', alpha=0.8)
    ax1.plot(df['time'], df['ib'], label='Phase B', color='blue', alpha=0.8)
    ax1.plot(df['time'], df['ic'], label='Phase C', color='green', alpha=0.8)
    
    ax1.set_ylabel('Current (p.u.)')
    ax1.set_title('Instantaneous Phase Currents (IBR Control Saturation)')
    ax1.legend(loc='upper right')
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.axvline(x=0.1, color='black', linestyle=':', label='Fault Initiation')

    # --- BOTTOM PLOT: Sequence Component Magnitudes ---
    # (Assuming you have run the sequence_engine to get these, 
    # or we calculate them here on the fly for the plot)
    from sequence_engine import calculate_sequence_components
    df_seq = calculate_sequence_components(df['time'].values, df['ia'].values, df['ib'].values, df['ic'].values)

    ax2.plot(df_seq['time'], df_seq['I1_mag'], label='Pos. Sequence ($I_1$)', color='darkorange', linewidth=2)
    ax2.plot(df_seq['time'], df_seq['I2_mag'], label='Neg. Sequence ($I_2$)', color='purple', linestyle='--')
    
    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel('Magnitude (p.u.)')
    ax2.set_title('Calculated Sequence Magnitudes (Relay Blindness Profile)')
    ax2.legend(loc='upper right')
    ax2.grid(True, linestyle='--', alpha=0.6)
    
    # 3. Save to file for VS Code Remote viewing
    output_filename = 'phd_fault_analysis.png'
    plt.savefig(output_filename, dpi=300)
    print(f"--- SUCCESS ---")
    print(f"Plot saved as: {output_filename}")
    print(f"Action: Refresh your VS Code sidebar and click {output_filename} to view.")

if __name__ == "__main__":
    generate_thesis_plots('pscad_fault_data.csv')