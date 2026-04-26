"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Core Engines
"""

# Save as: method_a_magnitude.py
import pandas as pd
import numpy as np
import joblib
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

def execute_method_a():
    df = pd.read_csv('Master_100_Sim_Results.csv')
    
    # Features: RAW current and simple variance
    df['variance'] = df.groupby('sim_id')['ib'].transform(lambda x: x.rolling(window=20).var())
    df = df.dropna()

    X = df[['ib', 'variance']]
    mapping = {'Normal': 0, 'Standard': 1, 'HIF': 2}
    y = df['label'].map(mapping).values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    clf = MLPClassifier(hidden_layer_sizes=(20, 10), max_iter=1000, random_state=42)
    clf.fit(X_scaled, y)
    
    # Export with unique name
    joblib.dump(clf, 'model_a_magnitude.pkl')
    joblib.dump(scaler, 'scaler_a.pkl')
    print("SUCCESS: Method A (Magnitude) trained. Status: Vulnerable to Load Noise.")

if __name__ == "__main__":
    execute_method_a()