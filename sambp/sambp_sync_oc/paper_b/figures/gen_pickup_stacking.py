#!/usr/bin/env python3
"""Generate fig_pickup_stacking.pdf — pickup stacking vs N-generators."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Data from Table II of Paper B
# N=1: single generator baseline (I_p,fixed = 1.200 pu → adapted 1.200)
# N=2: Gen1 (outermost) = 1.550 pu  [from report6]
# N=3: Gen1 = 1.635 pu
# N=4: Gen1 = 2.038 pu
# Extrapolate N=5: Gen1 >= 2.038 + 0.200 = 2.238 pu (projected)

N_vals     = np.array([1, 2, 3, 4])
pickup_out = np.array([1.200, 1.550, 1.635, 2.038])   # outermost relay (Gen1)
pickup_in  = np.array([1.200, 1.350, 1.235, 1.438])   # innermost relay (GenN)

# Projected N=5 extrapolation (linear stacking)
N_proj     = np.array([4, 5])
pickup_proj = np.array([2.038, 2.038 + 0.200])        # conservative lower bound

fig, ax = plt.subplots(figsize=(3.5, 2.6))

ax.plot(N_vals, pickup_out, 'bs-', ms=6, lw=1.5, label='Outermost relay $G_1$')
ax.plot(N_vals, pickup_in,  'g^--', ms=6, lw=1.2, label='Innermost relay $G_N$')
ax.plot(N_proj, pickup_proj, 'b:', lw=1.2, alpha=0.55, label='Projected ($N=5$)')

# Practical relay ceiling
ax.axhline(2.0, color='red', ls='-.', lw=1.0, label='Typical ceiling (2.0 pu)')

# Annotate N=4 outermost value
ax.annotate('2.038 pu', xy=(4, 2.038), xytext=(3.55, 2.12),
            fontsize=7, color='navy',
            arrowprops=dict(arrowstyle='->', color='navy', lw=0.8))

ax.set_xlabel('Number of generators $N$', fontsize=8)
ax.set_ylabel('Pickup setting (pu)', fontsize=8)
ax.set_title('Pickup stacking vs. generator count', fontsize=8)
ax.set_xticks([1, 2, 3, 4, 5])
ax.set_xlim(0.8, 5.2)
ax.set_ylim(1.0, 2.4)
ax.tick_params(labelsize=7)
ax.legend(fontsize=6.5, loc='upper left')
ax.grid(True, ls=':', alpha=0.5)

fig.tight_layout(pad=0.5)
fig.savefig('fig_pickup_stacking.pdf', dpi=300, bbox_inches='tight')
print("Saved fig_pickup_stacking.pdf")
