"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Analytics Validation
"""

import numpy as np
import matplotlib.pyplot as plt
import joblib
import pandas as pd

def plot_boundaries():
    clf = joblib.load('ibr_fault_classifier.pkl')
    scaler = joblib.load('feature_scaler.pkl')
    
    # Create a grid of points (Current vs Variance)
    # Holding Peak-to-Peak constant at a typical value
    x_min, x_max = 0, 1.5
    y_min, y_max = 0, 0.5
    xx, yy = np.meshgrid(np.linspace(x_min, x_max, 100),
                         np.linspace(y_min, y_max, 100))
    
    # Flatten grid and add a constant p2p value for the 3rd feature
    grid_points = np.c_[xx.ravel(), yy.ravel(), np.full(xx.ravel().shape, 0.5)]
    
    # We need to wrap in a DataFrame because of the feature names warning
    grid_df = pd.DataFrame(grid_points, columns=['ib', 'variance', 'p2p'])
    Z = clf.predict(scaler.transform(grid_df))
    Z = Z.reshape(xx.shape)

    plt.figure(figsize=(10, 7))
    plt.contourf(xx, yy, Z, alpha=0.3, cmap='viridis')
    plt.scatter([0.65], [0.1], color='red', marker='x', s=100, label='Your HIF Detection')
    plt.xlabel('Current Magnitude (p.u.)')
    plt.ylabel('Current Variance (Arcing Signature)')
    plt.title('AI Protection Zones: Normal vs. IBR Fault vs. HIF')
    plt.legend()
    plt.savefig('decision_boundaries.png')
    print("SUCCESS: decision_boundaries.png generated.")

if __name__ == "__main__":
    plot_boundaries()