
"""
Description: Multi-Stage Voltage Dip Plotter
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt
import os

# 1. Lock the aesthetics (Relies on thesis.mplstyle in the root directory)
plt.style.use('./thesis.mplstyle')

def plot_multistage_dip(input_csv='fault_data.csv'):
    # Define input directory
    input_dir = 'Z_Final_Thesis_data/ch4_IPR/'

    # Use given path directly if it already includes a directory
    if os.path.dirname(input_csv):
        input_csv_path = input_csv
    else:
        input_csv_path = os.path.join(input_dir, input_csv)

    # Standardized output route
    output_dir = 'Z_Final_Thesis_figures/ch4_IPR/'
    output_pdf = os.path.join(output_dir, 'c4_3_plt_multistage_voltage_dip.pdf')

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Load the data
    try:
        df = pd.read_csv(input_csv_path)
    except FileNotFoundError:
        print(f"ERROR: {input_csv_path} not found. Generate simulation data first.")
        return

    # 2. Generate Data
    plt.figure() 
    
    # Plot Phases (Map these to your specific MATLAB/PSCAD export headers)
    plt.plot(df['time'], df['Va_kV'], label='Phase A', color='red')
    plt.plot(df['time'], df['Vb_kV'], label='Phase B', color='blue', linestyle='--', alpha=0.8)
    plt.plot(df['time'], df['Vc_kV'], label='Phase C', color='green', linestyle=':', alpha=0.8)

    # Labels and Formatting
    plt.title('Three-Phase Voltage Waveform: Multi-Stage Voltage Dip')
    plt.xlabel('Time (s)')
    plt.ylabel('Voltage (kV)')
    plt.legend(loc='upper right')
    
    # Adjust these limits based on your specific transient window
    # plt.xlim(1.5, 2.5)
    # plt.ylim(-15, 15)
    

    # Define standardized output route
    #output_dir = 'Z_Final_Thesis_figures/ch4_IPR/'
    #output_pdf = os.path.join(output_dir, 'c4_3_plt_multistage_voltage_dip.pdf')

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # 3. Export as PDF Vector
    plt.savefig(output_pdf)
    print(f"SUCCESS: Vector waveform saved to {output_pdf}")

if __name__ == "__main__":
    plot_multistage_dip()

