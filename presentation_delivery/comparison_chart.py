"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Presentation Delivery
"""

import matplotlib.pyplot as plt
import pandas as pd

def plot_final_comparison():
    data = {
        'Scenario': ['HIF (A)', 'Motor (B)', 'Clipping (C)', 'Noise (D)', 'Adjacent (E)', 'Cap (F)', 'Harmonic (G)', 'Load Step (H)'],
        'Confidence': [92.4, 8.2, 88.1, 4.5, 34.2, 12.1, 7.4, 3.9],
        'Action': ['TRIP', 'BLOCK', 'TRIP', 'BLOCK', 'BLOCK', 'BLOCK', 'BLOCK', 'BLOCK']
    }
    df = pd.DataFrame(data)
    
    colors = ['crimson' if x == 'TRIP' else 'steelblue' for x in df['Action']]
    plt.figure(figsize=(12, 6))
    plt.bar(df['Scenario'], df['Confidence'], color=colors)
    plt.axhline(y=50, color='black', linestyle='--', label='Trip Threshold (50%)')
    plt.title('Method B: Cross-Scenario Discrimination Integrity', fontsize=14)
    plt.ylabel('AI Fault Probability (%)')
    plt.ylim(0, 100)
    plt.legend()
    plt.grid(axis='y', alpha=0.3)
    plt.savefig('final_results_summary.png')
    print("SUCCESS: final_results_summary.png generated for Slides.")

if __name__ == "__main__":
    plot_final_comparison()