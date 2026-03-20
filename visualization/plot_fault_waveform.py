"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt
# 1. Lock the aesthetics
plt.style.use('./thesis.mplstyle')




def plot_waveform_from_csv(input_csv='fault_data.csv', output_png='recreated_waveform.png'):
    # Load the data
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"ERROR: {input_csv} not found. Generate it first.")
        return

    # Initialize the plot with a Senior Researcher aesthetic
    plt.figure(figsize=(12, 5), dpi=300)
    
    # Plot Phases using standard power systems color coding
    plt.plot(df['time'], df['Va_kV'], label='Phase A', color='red', linewidth=1.2)
    plt.plot(df['time'], df['Vb_kV'], label='Phase B', color='blue', linestyle='--', linewidth=1.0, alpha=0.8)
    plt.plot(df['time'], df['Vc_kV'], label='Phase C', color='green', linestyle=':', linewidth=1.0, alpha=0.8)

    # Formatting for IIT Madras Thesis Standards
    plt.title('Three-Phase Voltage Waveform: SLG Fault Inception & Transition', fontsize=14, fontweight='bold')
    plt.xlabel('Time (s)', fontsize=12)
    plt.ylabel('Voltage (kV)', fontsize=12)
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    plt.legend(loc='upper right', frameon=True, shadow=True)
    
    # Set axis limits to match your original reference image
    plt.xlim(1.97, 2.15)
    plt.ylim(-11, 11)

    
    # Save and Close
    plt.tight_layout()
    plt.savefig(output_png)
    plt.show()
    print(f"SUCCESS: Waveform saved to {output_png}")

if __name__ == "__main__":
    plot_waveform_from_csv()