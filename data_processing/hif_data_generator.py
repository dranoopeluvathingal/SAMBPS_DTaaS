"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Data Processing
"""

import numpy as np
import pandas as pd

def generate_hif_data():
    fs, f0, t_end = 10000, 50, 0.2
    t = np.linspace(0, t_end, int(fs * t_end))
    
    # Normal Load (Current = 1.0 p.u.)
    ia = 1.0 * np.sin(2 * np.pi * f0 * t)
    ib = 1.0 * np.sin(2 * np.pi * f0 * t - 2 * np.pi / 3)
    ic = 1.0 * np.sin(2 * np.pi * f0 * t + 2 * np.pi / 3)
    
    # HIF starts at t=0.1s on Phase B
    fault_idx = np.where(t >= 0.1)[0]
    
    # Arcing Physics: Asymmetry + Randomness + Low Magnitude
    # We clip the current and add high-frequency "sputtering" noise
    hif_current = 0.8 * np.sin(2 * np.pi * f0 * t[fault_idx] - 2 * np.pi / 3)
    noise = 0.05 * np.random.normal(size=len(fault_idx))
    
    # The Arcing Signature: Non-linear distortion
    ib[fault_idx] = hif_current + noise
    
    df = pd.DataFrame({'time': t, 'ia': ia, 'ib': ib, 'ic': ic})
    df.to_csv('hif_fault_data.csv', index=False)
    print("SUCCESS: hif_fault_data.csv generated (0.8 p.u. Arcing Fault)")

if __name__ == "__main__":
    generate_hif_data()