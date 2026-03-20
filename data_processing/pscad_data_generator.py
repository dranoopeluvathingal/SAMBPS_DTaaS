"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Data Processing
"""

import numpy as np
import pandas as pd

# Parameters for IIT-level simulation
fs = 10000  # 10kHz sampling (PSCAD-like)
f0 = 50     # System frequency
t_end = 0.2
t = np.linspace(0, t_end, int(fs * t_end))

# Normal Load Current (1.0 p.u.)
ia = 1.0 * np.sin(2 * np.pi * f0 * t)
ib = 1.0 * np.sin(2 * np.pi * f0 * t - 2 * np.pi / 3)
ic = 1.0 * np.sin(2 * np.pi * f0 * t + 2 * np.pi / 3)

# Fault Injection at t = 0.1s (L-B to L-C Fault)
fault_idx = np.where(t >= 0.1)[0]

# --- IBR Fault Physics Logic ---
# In a legacy system, current would jump to 10 p.u.
# Here, we limit it to 1.2 p.u. to mimic IBR control saturation.
limit = 1.2

# Phase A remains healthy
# Phase B and C are faulted
ia[fault_idx] = 1.0 * np.sin(2 * np.pi * f0 * t[fault_idx])
ib[fault_idx] = limit * np.sin(2 * np.pi * f0 * t[fault_idx] - 2 * np.pi / 3)
ic[fault_idx] = limit * np.sin(2 * np.pi * f0 * t[fault_idx] + 2 * np.pi / 3)

# Create DataFrame
df = pd.DataFrame({
    'time': t,
    'ia': ia,
    'ib': ib,
    'ic': ic
})

# Save for sequence_engine.py
df.to_csv('pscad_fault_data.csv', index=False)
print("SUCCESS: pscad_fault_data.csv generated with IBR Current-Limiting behavior.")

