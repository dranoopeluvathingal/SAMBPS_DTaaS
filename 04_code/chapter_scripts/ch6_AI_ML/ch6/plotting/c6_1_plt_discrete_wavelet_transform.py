"""
Description: Multi-Phase DWT Fault Identification
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Phase Selection + Fault Classification
"""

import numpy as np
import pywt
import matplotlib.pyplot as plt
import os
import pandas as pd

# 1. LOCK AESTHETICS
plt.style.use('./thesis.mplstyle')

def execute_multi_phase_classification(input_csv_filename):
    # Routing
    # Input File Folder: Z_Final_Thesis_data/ch6_AI_ML/  --- (This is where the script looks for fault_data_full.csv)

    input_dir = 'Z_Final_Thesis_data/ch6_AI_ML/' 

    # Output Folder: Z_Final_Thesis_figures/ch6_Z_Final_Thesis_scripts/  --- (This is where the PDF will be saved)
    output_dir = 'Z_Final_Thesis_figures/ch6_Z_Final_Thesis_scripts/'
    os.makedirs(output_dir, exist_ok=True)
    
    input_path = os.path.join(input_dir, input_csv_filename)
    df = pd.read_csv(input_path)

    t = df['time_s'].values
    # LOAD ALL THREE PHASES
    phases = {'A': df['Ia_pu'].values, 'B': df['Ib_pu'].values, 'C': df['Ic_pu'].values}
    
    # 2. GENERATE ENERGY FEATURES FOR ALL PHASES
    energies = {}
    for p, signal in phases.items():
        # .copy() ensures the array is writable for PyWavelets
        signal_writable = signal.copy() 
        
        # Perform DWT
        _, d1 = pywt.dwt(signal_writable, 'db4')
        
        # Sliding Window Energy (Length = 2ms at 10kHz)
        energies[p] = np.convolve(np.square(d1), np.ones(20)/20, mode='same')

    # Define feature time axis once
    t_feat = np.linspace(t.min(), t.max(), len(energies['A']))

    # 3. VISUAL CLASSIFICATION PLOT
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 8))

    # Top Panel: Time-Domain Waveforms
    ax1.plot(t, phases['A'], 'r', label='Phase A', alpha=0.7)
    ax1.plot(t, phases['B'], 'k', label='Phase B')
    ax1.plot(t, phases['C'], 'b', label='Phase C')
    ax1.set_ylabel('Current (pu)')
    ax1.set_xlim(5.98, 6.04)
    ax1.legend(loc='upper right', ncol=3)

    # Bottom Panel: Wavelet Energy Features
    ax2.plot(t_feat, energies['A'], 'r--', label='$E_A$ (Healthy)')
    ax2.plot(t_feat, energies['B'], 'k', label='$E_B$ (Faulted)', linewidth=1.8)
    ax2.plot(t_feat, energies['C'], 'b', label='$E_C$ (Faulted)', linewidth=1.8)
    ax2.set_ylabel('Wavelet Energy')
    ax2.set_xlabel('Time (s)')
    ax2.set_xlim(5.98, 6.04)
    ax2.legend(loc='upper right')

    ## Output File
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'c6_1_plt_bc_fault_identification.pdf')
    plt.savefig(output_path, format='pdf')
    print(f"✅ Success: Multi-Phase Identification PDF Saved to {output_path}")

if __name__ == "__main__":
    execute_multi_phase_classification('fault_data_full.csv')