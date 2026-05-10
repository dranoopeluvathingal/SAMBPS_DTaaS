"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def generate_ripple_comparison():
    df = pd.read_csv('Master_100_Sim_Results.csv')
    
    # 1. Select representative cases
    normal_case = df[df['label'] == 'Normal'].iloc[200:600] # Steady state snippet
    hif_case = df[(df['label'] == 'HIF') & (df['time'] > 0.12)].iloc[0:400] # Arcing snippet
    
    def get_ripple(signal):
        return signal - signal.rolling(window=20).mean()

    # 2. Setup Plot
    fig, ax = plt.subplots(2, 2, figsize=(12, 8), sharex=False)
    
    # Row 1: Raw Signals (They look similar in magnitude!)
    ax[0, 0].plot(normal_case['time'], normal_case['ib'], color='blue')
    ax[0, 0].set_title('Normal Load: Raw Current')
    ax[0, 0].set_ylabel('Amplitude (p.u.)')

    ax[0, 1].plot(hif_case['time'], hif_case['ib'], color='crimson')
    ax[0, 1].set_title('HIF Arcing: Raw Current')

    # Row 2: Ripple Component (The "Intelligence" Layer)
    ax[1, 0].plot(normal_case['time'], get_ripple(normal_case['ib']), color='navy')
    ax[1, 0].set_title('Normal: Residual Ripple (Pure Sine)')
    ax[1, 0].set_ylim(-0.2, 0.2)
    ax[1, 0].set_ylabel('Ripple (p.u.)')

    ax[1, 1].plot(hif_case['time'], get_ripple(hif_case['ib']), color='darkred')
    ax[1, 1].set_title('HIF: Residual Ripple (High Variance)')
    ax[1, 1].set_ylim(-0.2, 0.2)

    plt.tight_layout()
    plt.savefig('ripple_comparison.png')
    print("SUCCESS: ripple_comparison.png generated.")

if __name__ == "__main__":
    generate_ripple_comparison()