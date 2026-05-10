"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt
from sequence_engine import calculate_sequence_components

# 1. Load the SG Data
try:
    df_sg = pd.read_csv('sg_fault_data.csv')
except FileNotFoundError:
    print("ERROR: Run sg_data_generator.py first.")
    exit()

# 2. Extract Symmetrical Components
df_seq_sg = calculate_sequence_components(df_sg['time'].values, df_sg['ia'].values, df_sg['ib'].values, df_sg['ic'].values)

# 3. Setup Integrated Figure (Matching your IBR style)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
plt.subplots_adjust(hspace=0.2)

# TOP: SG Raw Phase Currents (Note the high peaks)
ax1.plot(df_sg['time'], df_sg['ia'], 'r-', label='Phase A', alpha=0.7)
ax1.plot(df_sg['time'], df_sg['ib'], 'b-', label='Phase B', alpha=0.7)
ax1.plot(df_sg['time'], df_sg['ic'], 'g-', label='Phase C', alpha=0.7)
ax1.set_title('Three-Phase Instantaneous Currents: Synchronous Generator Fault Response', fontsize=14)
ax1.set_ylabel('Current (p.u.)')
ax1.grid(True, linestyle=':', alpha=0.6)
ax1.legend(loc='upper right')

# BOTTOM: SG Sequence Components (Note the massive I2)
ax2.plot(df_seq_sg['time'], df_seq_sg['I1_mag'], color='darkorange', label='Positive Sequence ($I_1$)', linewidth=2.5)
ax2.plot(df_seq_sg['time'], df_seq_sg['I2_mag'], color='purple', label='Negative Sequence ($I_2$)', linestyle='--', linewidth=2)
ax2.set_title('Symmetrical Component Extraction: Detection Variables (SG)', fontsize=14)
ax2.set_ylabel('Magnitude (p.u.)')
ax2.set_xlabel('Time (s)')
ax2.grid(True, linestyle=':', alpha=0.6)
ax2.legend(loc='upper right')

# Global Formatting
plt.xlim(0.05, 0.18) 
plt.tight_layout()
plt.savefig('sg_thesis_figure.png', dpi=300)
print("SUCCESS: sg_thesis_figure.png generated. Compare this with your IBR figure.")