"""
Description: [Entropy Method for HIF Detection - Magnitude-Invariant Approach]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Core Engines
"""

# Save as: method_b_entropy.py
import pandas as pd
import numpy as np
import joblib
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import RobustScaler

def execute_method_b():
    df = pd.read_csv('Master_100_Sim_Results.csv')
    
    # Physics Engineering: Isolate the "Noise" from the "Sine Wave"
    df['residual'] = df.groupby('sim_id')['ib'].transform(lambda x: x - x.rolling(window=20).mean())
    
    # Feature 1: Noise Density (Stochastic signature of the arc)
    df['noise_density'] = df.groupby('sim_id')['residual'].transform(lambda x: x.rolling(window=20).std())
    # Feature 2: Peak-to-Peak of the Noise (Discriminates arcing from white noise)
    df['ripple_p2p'] = df.groupby('sim_id')['residual'].transform(lambda x: x.rolling(window=20).max() - x.rolling(window=20).min())
    
    df = df.dropna()

    X = df[['noise_density', 'ripple_p2p']]
    mapping = {'Normal': 0, 'Standard': 1, 'HIF': 2}
    y = df['label'].map(mapping).values

    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    clf = MLPClassifier(hidden_layer_sizes=(50, 25), max_iter=2000, random_state=42)
    clf.fit(X_scaled, y)
    
    # Export with unique name
    joblib.dump(clf, 'model_b_entropy.pkl')
    joblib.dump(scaler, 'scaler_b.pkl')
    print("SUCCESS: Method B (Entropy) trained. Status: Magnitude-Invariant.")

if __name__ == "__main__":
    execute_method_b()