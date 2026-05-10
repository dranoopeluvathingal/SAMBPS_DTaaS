"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import matplotlib.pyplot as plt
import pandas as pd

def plot_batch_performance():
    df = pd.read_csv('batch_validation_results.csv')
    df = df.dropna() # Only look at successful trips
    
    detection_delays = (df['time'] - 0.1) * 1000 # Convert to ms
    
    plt.figure(figsize=(10, 6))
    plt.hist(detection_delays, bins=15, color='teal', edgecolor='black', alpha=0.7)
    plt.axvline(detection_delays.mean(), color='red', linestyle='dashed', linewidth=2, label=f'Mean: {detection_delays.mean():.2f}ms')
    plt.xlabel('Detection Delay (ms)')
    plt.ylabel('Frequency')
    plt.title('Relay Response Time Distribution (100 Simulations)')
    plt.legend()
    plt.grid(axis='y', alpha=0.3)
    plt.savefig('batch_delay_histogram.png')
    print("SUCCESS: batch_delay_histogram.png generated.")

if __name__ == "__main__":
    plot_batch_performance()