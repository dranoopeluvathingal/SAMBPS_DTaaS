"""
Description: SNR Calculation for both High-Fidelity and Raw CSV Sources
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Metrics & Validation
"""

import os
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

def sine_func(t, A, phi):
    """Reference 50Hz sine wave for noise extraction in raw data."""
    return A * np.sin(2 * np.pi * 50 * t + phi)

def calculate_fault_snr(input_csv):
    # --- INTERNAL ROUTING ---
    data_dir = 'Z_Final_Thesis_data/ch6_AI_ML/'
    input_path = os.path.join(data_dir, input_csv)
    
    if not os.path.exists(input_path):
        print(f"❌ Error: {input_path} not found.")
        return

    df = pd.read_csv(input_path)
    t = df['time_s'].values if 'time_s' in df.columns else df.iloc[:, 0].values
    signal_raw = df['Ib_pu'].values # Target Phase B

    t_fault = 6.0
    fault_mask = (t >= t_fault) & (t <= 6.01)
    prefault_mask = (t >= 5.98) & (t < 6.00)

    # --- LOGIC BRANCH: High-Fidelity vs. Raw ---
    if 'Ib_trans' in df.columns:
        # CASE 1: Full Precision (15-column) - Direct Extraction
        print(f"📂 Mode: High-Fidelity (Ground Truth Available)")
        s_comp = df.loc[fault_mask, 'Ib_trans'].values
        n_comp = (df.loc[fault_mask, 'Ib_bg'] + df.loc[fault_mask, 'ripple']).values
    else:
        # CASE 2: Raw Data (4-column) - Temporal Estimation
        print(f"📂 Mode: Raw Data (Estimation via Temporal Residuals)")
        
        # 1. Estimate Fundamental using pre-fault data
        popt, _ = curve_fit(sine_func, t[prefault_mask], signal_raw[prefault_mask])
        
        # 2. Extract Noise Floor (RMS of residual BEFORE t=6.0)
        fundamental_prefault = sine_func(t[prefault_mask], *popt)
        n_comp = signal_raw[prefault_mask] - fundamental_prefault
        p_noise = np.mean(np.square(n_comp))
        
        # 3. Extract Transient Signal (RMS of residual AFTER t=6.0)
        fundamental_postfault = sine_func(t[fault_mask], *popt)
        s_comp = signal_raw[fault_mask] - fundamental_postfault
        p_signal = np.mean(np.square(s_comp))

    # --- METRIC CALCULATION ---
    p_signal = np.mean(np.square(s_comp))
    p_noise = np.mean(np.square(n_comp))
    snr_db = 10 * np.log10(p_signal / p_noise) if p_noise > 0 else 0

    print("-" * 45)
    print(f"✅ METRIC GENERATED: {input_csv}")
    print(f"Signal Power ($P_s$): {p_signal:.8f}")
    print(f"Noise Power  ($P_n$): {p_noise:.8f}")
    print(f"Calculated SNR:       {snr_db:.2f} dB")
    print("-" * 45)
    
    return snr_db

if __name__ == "__main__":
    # Test both files to ensure workspace consistency
    calculate_fault_snr('fault_data_full.csv')
    calculate_fault_snr('fault_data.csv')