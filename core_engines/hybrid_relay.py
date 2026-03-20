"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Core Engines
"""

import pandas as pd
import numpy as np
import joblib

# 1. Load Intelligence
clf = joblib.load('ibr_fault_classifier.pkl')
scaler = joblib.load('feature_scaler.pkl')

def run_hybrid_relay(live_data_file):
    df = pd.read_csv(live_data_file)
    
    # --- PHASE 1: Adaptive Logic (Chapter 3) ---
    # Simulating the voltage dip context for the relay
    df['V1_mag'] = np.where(df['time'] > 0.1, 0.85, 1.0) 
    I_set = 1.05
    
    # --- PHASE 2: AI Feature Extraction (Chapter 5) ---
    df['variance'] = df['ib'].rolling(window=20).var()
    df['p2p'] = df['ib'].rolling(window=20).max() - df['ib'].rolling(window=20).min()
    df = df.dropna()
    
    feature_names = ['ib', 'variance', 'p2p']

    print(f"--- SCANNING: {live_data_file} ---")
    
    for i, row in df.iterrows():
        # Feature Processing
        feat_df = pd.DataFrame([[row['ib'], row['variance'], row['p2p']]], columns=feature_names)
        feat_scaled = scaler.transform(feat_df)
        
        # AI Inference
        # predict() returns the class: 0 (Normal), 1 (Standard Fault), 2 (HIF)
        ai_class = clf.predict(feat_scaled)[0]
        # predict_proba() gives us the confidence score for the chosen class
        ai_confidence = np.max(clf.predict_proba(feat_scaled))

        # --- THE DECISION ENGINE ---
        
        # Condition A: Standard IBR Fault (High Current + Class 1)
        standard_trip = (abs(row['ib']) > I_set) and (ai_class == 1)
        
        # Condition B: Sensitive HIF Override (Low Current + Class 2 + Voltage Dip)
        hif_trip = (ai_class == 2) and (row['V1_mag'] < 0.9) and (ai_confidence > 0.70)

        if standard_trip or hif_trip:
            trip_type = "STANDARD IBR FAULT" if standard_trip else "HIGH IMPEDANCE FAULT (HIF)"
            print(f"\n[!] {trip_type} CONFIRMED")
            print(f"Time: {row['time']:.4f}s | Current: {abs(row['ib']):.2f} p.u.")
            print(f"AI Class: {ai_class} | Confidence: {ai_confidence*100:.1f}%")
            print(f"Voltage PCC: {row['V1_mag']:.2f} p.u.")
            break

if __name__ == "__main__":
    run_hybrid_relay('hif_fault_data.csv')