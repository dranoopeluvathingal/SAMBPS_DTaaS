"""
Description: Validation engine for Inverter Control Interaction (ICI) masking effects.
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Analytics Validation
"""

import numpy as np
import pandas as pd
import os

def simulate_inverter_control_noise(duration=0.2, fs=10000, control_mode='droop'):
    """Simulates the harmonic signatures of specific inverter control loops."""
    t = np.linspace(0, duration, int(fs * duration))
    fundamental = 9.0 * np.sin(2 * np.pi * 50 * t)
    
    if control_mode == 'droop':
        # Droop control adds low-frequency modulation (chaos-lite)
        noise = 0.05 * np.sin(2 * np.pi * 7 * t) 
    elif control_mode == 'vsm':
        # Virtual Synchronous Machines add sub-harmonic inertia ripples
        noise = 0.08 * np.sin(2 * np.pi * 12 * t)
    else:
        noise = 0
        
    return t, fundamental + noise

def run_ici_stress_test():
    """Audits Method B sensitivity against masked inverter control signals."""
    print("--- STARTING INVERTER CONTROL INTERACTION (ICI) AUDIT ---")
    modes = ['droop', 'vsm', 'current_limited']
    results = []
    
    # Method B Threshold [cite: 2026-03-01]
    ENTROPY_THRESHOLD = 0.15
    
    for mode in modes:
        t, signal = simulate_inverter_control_noise(control_mode=mode)
        
        # Calculate Method B Entropy [cite: 2026-03-01]
        window = 20
        series = pd.Series(signal)
        fundamental = series.rolling(window=window, center=True).mean()
        residual = series - fundamental
        entropy_density = residual.rolling(window=window).std()
        
        # Check for False Positives (Security Audit)
        max_noise_entropy = entropy_density.max()
        is_secure = max_noise_entropy < ENTROPY_THRESHOLD
        
        results.append({
            "Control_Mode": mode.upper(),
            "Peak_Entropy_Noise": round(max_noise_entropy, 4),
            "Security_Status": "PASSED" if is_secure else "FAILED"
        })
        
    df_results = pd.DataFrame(results)
    output_path = "analytics_validation/ici_audit_results.csv"
    df_results.to_csv(output_path, index=False)
    
    print(df_results.to_markdown(index=False))
    print(f"\nSUCCESS: ICI Audit complete. Results saved to {output_path}")

if __name__ == "__main__":
    run_ici_stress_test()