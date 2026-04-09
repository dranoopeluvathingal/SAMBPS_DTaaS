#!/usr/bin/env python3
"""Generate fig_kappa_comparison.pdf — kappa_n across all four SAMBP functions."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Data extracted from study result CSVs
# SyncOC (from paper A: 3PH/LL/SLG; kappa_n from Table I of Paper A)
syncoc_events = ['3PH\nfault', 'LL\nfault', 'SLG\nfault']
syncoc_kn     = [10.17, 17.2, 17.2]   # from paper results (67ms window)

# 87T (from 87T_study_results.csv)
t87_events = ['load', 'inrush', 'overexc', 'ext+CT', 'int-A', 'int-AB', 'int-3PH']
t87_kn     = [4.97, 5.16, 6.74, 4.95, 4.83, 4.83, 4.83]

# 87L (from 87L_study_results.csv — same kappa for all: 2.45)
l87_events = ['H-heal', 'H-ext', 'H-AG', 'H-3PH',
              'D-heal', 'D-ext', 'D-AG', 'D-3PH',
              'L-heal', 'L-ext', 'L-AG', 'L-3PH']
l87_kn     = [2.45]*12

# 87B (from 87B_study_results.csv)
b87_events = ['load', 'ext', 'ext+CT', 'int-AG', 'int-3PH', 'CT-open']
b87_kn     = [4.36, 4.27, 2.73, 4.27, 4.27, 4.36]

# Hypothetical unconstrained 7-param OC (from sweep_kappa.py)
unconstrained_kn = 2.39e8   # at 67 ms window

fig, axes = plt.subplots(1, 4, figsize=(7.0, 2.8), sharey=False)
fig.suptitle('Column-normalised Jacobian condition number $\\kappa_n$ by function and event',
             fontsize=8)

colors = ['#2166ac', '#4dac26', '#d01c8b', '#f4a582']
data   = [(syncoc_events, syncoc_kn, 'SyncOC\n(6-param)'),
          (t87_events,    t87_kn,    '87T\n(5-param)'),
          (l87_events,    l87_kn,    '87L\n(4-param)'),
          (b87_events,    b87_kn,    '87B\n(3-param)')]

for ax, (evts, kn, title), col in zip(axes, data, colors):
    x = np.arange(len(evts))
    bars = ax.bar(x, kn, color=col, alpha=0.75, width=0.6, linewidth=0.4,
                  edgecolor='k')
    ax.axhline(30, color='red', ls='--', lw=0.8, label='$\\kappa_{thresh}=30$')
    ax.set_xticks(x)
    ax.set_xticklabels(evts, fontsize=5, rotation=45, ha='right')
    ax.set_title(title, fontsize=7)
    ax.set_ylim(0, 32)
    ax.tick_params(axis='y', labelsize=6)
    ax.grid(axis='y', ls=':', alpha=0.4)
    if ax == axes[0]:
        ax.set_ylabel('$\\kappa_n$', fontsize=7)
        ax.legend(fontsize=5.5, loc='upper right')

# Annotate the unconstrained kn on first axis with a text box
axes[0].text(0.5, 28.5,
             f'7-param $\\kappa_n \\approx 2\\times10^8$\n(unconstrained)',
             ha='center', va='top', fontsize=5.5,
             color='darkred',
             bbox=dict(boxstyle='round,pad=0.2', fc='#fff3f3', ec='red', lw=0.5))

fig.tight_layout(pad=0.6, rect=[0, 0, 1, 0.93])
fig.savefig('fig_kappa_comparison.pdf', dpi=300, bbox_inches='tight')
print("Saved fig_kappa_comparison.pdf")
