"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt
from sequence_engine import calculate_sequence_components

# 1. Load both datasets
df_ibr = pd.read_csv('pscad_fault_data.csv')
df_sg = pd.read_csv('sg_fault_data.csv')

# 2. Extract Sequences
seq_ibr = calculate_sequence_components(df_ibr['time'].values, df_ibr['ia'].values, df_ibr['ib'].values, df_ibr['ic'].values)
seq_sg = calculate_sequence_components(df_sg['time'].values, df_sg['ia'].values, df_sg['ib'].values, df_sg['ic'].values)

# 3. Plotting
fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True)

# --- LEFT COLUMN: IBR (The Problem) ---
axes[0,0].plot(df_ibr['time'], df_ibr['ib'], 'b', label='Phase B (IBR)')
axes[0,0].set_title('IBR: Current Limiting (1.2 p.u.)', fontsize=12, fontweight='bold')
axes[1,0].plot(seq_ibr['time'], seq_ibr['I2_mag'], 'purple', label='Neg. Seq (I2)')
axes[1,0].set_title('IBR: I2 Suppression (Relay Blindness)', fontsize=12)

# --- RIGHT COLUMN: Synchronous Generator (The Baseline) ---
axes[0,1].plot(df_sg['time'], df_sg['ib'], 'darkblue', label='Phase B (SG)')
axes[0,1].set_title('SG: High Fault Surge (8.0 p.u.)', fontsize=12, fontweight='bold')
axes[1,1].plot(seq_sg['time'], seq_sg['I2_mag'], 'm', label='Neg. Seq (I2)')
axes[1,1].set_title('SG: Massive I2 (Easy Detection)', fontsize=12)

# Formatting
for ax in axes.flat:
    ax.grid(True, linestyle=':')
    ax.legend()
    ax.set_xlim(0.08, 0.18)

plt.tight_layout()
plt.savefig('sg_vs_ibr_comparison.png', dpi=300)
print("SUCCESS: sg_vs_ibr_comparison.png saved.")