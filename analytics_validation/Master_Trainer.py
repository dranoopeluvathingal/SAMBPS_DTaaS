"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Analytics Validation
"""

import pandas as pd
import numpy as np
import joblib
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import RobustScaler

def retrain_entropy_model():
    df = pd.read_csv('Master_100_Sim_Results.csv')
    
    # 1. Feature Engineering: WAVEFORM CHAOS
    # Get the residual (High-frequency noise)
    df['residual'] = df.groupby('sim_id')['ib'].transform(lambda x: x - x.rolling(window=20).mean())
    
    # Feature 1: Noise Density (Standard Deviation of the Residual)
    df['noise_density'] = df.groupby('sim_id')['residual'].transform(lambda x: x.rolling(window=20).std())
    
    # Feature 2: Peak-to-Peak of the Residual (NOT the raw signal)
    df['ripple_p2p'] = df.groupby('sim_id')['residual'].transform(lambda x: x.rolling(window=20).max() - x.rolling(window=20).min())
    
    df = df.dropna()

    # Labels: 0=Normal, 1=Standard, 2=HIF
    mapping = {'Normal': 0, 'Standard': 1, 'HIF': 2}
    y = df['label'].map(mapping).values
    
    # PURE PHYSICS FEATURES (Magnitude is now 100% ignored)
    feature_names = ['noise_density', 'ripple_p2p']
    X = df[feature_names]

    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    # Deeper layers to catch the stochastic arcing pattern
    clf = MLPClassifier(hidden_layer_sizes=(100, 50), max_iter=5000, random_state=42)
    clf.fit(X_scaled, y)

    joblib.dump(clf, 'ibr_fault_classifier.pkl')
    joblib.dump(scaler, 'feature_scaler.pkl')
    print("--- SUCCESS: ENTROPY BRAIN TRAINED (Magnitude-Blind) ---")

if __name__ == "__main__":
    retrain_entropy_model()