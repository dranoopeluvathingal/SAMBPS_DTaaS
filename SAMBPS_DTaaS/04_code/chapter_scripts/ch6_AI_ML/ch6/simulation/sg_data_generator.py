"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Data Processing
"""

import numpy as np
import pandas as pd

# Parameters for SG Fault Physics
fs = 10000  
f0 = 50     
t_end = 0.2
t = np.linspace(0, t_end, int(fs * t_end))

# Normal Load (1.0 p.u.)
ia = 1.0 * np.sin(2 * np.pi * f0 * t)
ib = 1.0 * np.sin(2 * np.pi * f0 * t - 2 * np.pi / 3)
ic = 1.0 * np.sin(2 * np.pi * f0 * t + 2 * np.pi / 3)

# Fault at t = 0.1s (Phase-to-Phase L-B to L-C)
fault_idx = np.where(t >= 0.1)[0]
t_fault = t[fault_idx] - 0.1

# SG Physics: High peak + DC Offset decay
# I_fault = [ (E/X'') - (E/X') ] * exp(-t/T'') + ... (Simplified)
peak_multiplier = 8.0  # 800% of rated current
tau = 0.05             # DC offset decay constant

# Phase A remains healthy (but sees some coupling)
# Phase B and C see massive, opposite surges
ia[fault_idx] = 1.1 * np.sin(2 * np.pi * f0 * t[fault_idx])
ib[fault_idx] = peak_multiplier * np.sin(2 * np.pi * f0 * t[fault_idx] - 2 * np.pi / 3) * np.exp(-t_fault/tau) + \
                5.0 * np.sin(2 * np.pi * f0 * t[fault_idx] - 2 * np.pi / 3)
ic[fault_idx] = -ib[fault_idx] # Opposite for L-L fault logic

df_sg = pd.DataFrame({'time': t, 'ia': ia, 'ib': ib, 'ic': ic})
df_sg.to_csv('sg_fault_data.csv', index=False)
print("SUCCESS: sg_fault_data.csv generated with high-magnitude machine physics.")