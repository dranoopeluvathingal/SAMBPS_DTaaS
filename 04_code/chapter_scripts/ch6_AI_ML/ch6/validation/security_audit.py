"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Analytics Validation
"""

import pandas as pd
import numpy as np
import joblib

def run_security_audit():
    clf = joblib.load('ibr_fault_classifier.pkl')
    scaler = joblib.load('feature_scaler.pkl')
    df_master = pd.read_csv('Master_100_Sim_Results.csv')
    
    normal_sims = df_master[df_master['label'] == 'Normal'].copy()
    
    # Calculate Chaos Features
    normal_sims['residual'] = normal_sims.groupby('sim_id')['ib'].transform(lambda x: x - x.rolling(window=20).mean())
    normal_sims['noise_density'] = normal_sims.groupby('sim_id')['residual'].transform(lambda x: x.rolling(window=20).std())
    normal_sims['ripple_p2p'] = normal_sims.groupby('sim_id')['residual'].transform(lambda x: x.rolling(window=20).max() - x.rolling(window=20).min())
    
    normal_sims = normal_sims.dropna()
    
    feature_names = ['noise_density', 'ripple_p2p']
    feat_scaled = scaler.transform(normal_sims[feature_names])
    
    probs = clf.predict_proba(feat_scaled)
    max_fault_prob = np.max(probs[:, 1:].sum(axis=1)) 
    
    print(f"--- ENTROPY SECURITY MARGIN AUDIT ---")
    print(f"Total Samples: {len(normal_sims)}")
    print(f"Max False Prob: {max_fault_prob*100:.2f}%")
    
    margin = 0.70 - max_fault_prob
    print(f"Security Margin: {margin*100:.2f}%")
    
    if max_fault_prob < 0.15:
        print("STATUS: DOCTORATE SECURED (Physics-First Discrimination)")
    else:
        print("STATUS: CHECKING NOISE FLOOR...")
    print("---------------------------------------")

if __name__ == "__main__":
    run_security_audit()