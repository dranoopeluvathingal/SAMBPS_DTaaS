"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import pandas as pd
import matplotlib.pyplot as plt

def generate_thd_delay_scatter():
    try:
        df = pd.read_csv('batch_validation_results.csv')
    except FileNotFoundError:
        print("ERROR: batch_validation_results.csv not found.")
        return

    plt.figure(figsize=(10, 6))
    
    # Define colors for each fault type
    colors = {'Standard': 'crimson', 'HIF': 'darkorange', 'Normal': 'gray'}
    
    for label, group in df.groupby('type'):
        plt.scatter(
            group['thd'], 
            group['delay_ms'], 
            label=label, 
            color=colors.get(label, 'blue'),
            alpha=0.7, 
            edgecolors='k', 
            s=80
        )

    mean_delay = df['delay_ms'].mean()
    plt.axhline(mean_delay, color='blue', linestyle='--', label=f'Mean: {mean_delay:.2f}ms')

    plt.title('Relay Performance Frontier: Detection Delay vs. THD', fontsize=13)
    plt.xlabel('Total Harmonic Distortion (THD %)')
    plt.ylabel('Detection Delay (ms)')
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(title='Fault Category')
    
    plt.savefig('thd_delay_scatter.png')
    print("SUCCESS: thd_delay_scatter.png generated using Matplotlib.")

if __name__ == "__main__":
    generate_thd_delay_scatter()