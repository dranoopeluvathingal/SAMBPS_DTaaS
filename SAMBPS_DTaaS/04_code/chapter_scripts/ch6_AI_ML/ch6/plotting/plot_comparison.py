"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt
from sequence_engine import calculate_sequence_components

# 1. Load Data
df = pd.read_csv('pscad_fault_data.csv')
df_seq = calculate_sequence_components(df['time'].values, df['ia'].values, df['ib'].values, df['ic'].values)

# 2. Setup Figure
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

# TOP: Raw Phase Currents (The "Evidence")
ax1.plot(df['time'], df['ia'], 'r-', label='Phase A', alpha=0.7)
ax1.plot(df['time'], df['ib'], 'b-', label='Phase B', alpha=0.7)
ax1.plot(df['time'], df['ic'], 'g-', label='Phase C', alpha=0.7)
ax1.set_title('Three-Phase Instantaneous Currents: IBR Fault Response', fontsize=14)
ax1.set_ylabel('Current (p.u.)')
ax1.grid(True, linestyle=':')
ax1.legend(loc='upper right')

# BOTTOM: Sequence Components (The "Analysis")
ax2.plot(df_seq['time'], df_seq['I1_mag'], 'darkorange', label='Positive Sequence ($I_1$)', linewidth=2.5)
ax2.plot(df_seq['time'], df_seq['I2_mag'], 'purple', label='Negative Sequence ($I_2$)', linestyle='--', linewidth=2)
ax2.set_title('Symmetrical Component Extraction: Detection Variables', fontsize=14)
ax2.set_ylabel('Magnitude (p.u.)')
ax2.set_xlabel('Time (s)')
ax2.grid(True, linestyle=':')
ax2.legend(loc='upper right')

# Global Formatting
plt.xlim(0.05, 0.18) # Zoom in on the fault window
plt.tight_layout()
plt.savefig('final_thesis_figure.png', dpi=300)
print("SUCCESS: final_thesis_figure.png generated in ~/phd_thesis/")