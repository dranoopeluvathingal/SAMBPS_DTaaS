"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Analytics Validation
"""

import pandas as pd
import numpy as np
import joblib
from scipy.fft import fft

# Load Intelligence
clf = joblib.load('ibr_fault_classifier.pkl')
scaler = joblib.load('feature_scaler.pkl')

def calculate_thd(signal):
    """Simple FFT-based THD calculation for one cycle."""
    sample_window = 200 # approx 1 cycle at 10kHz
    if len(signal) < sample_window: return 0
    
    # Use the last cycle of the fault
    window = signal[-sample_window:]
    spectrum = np.abs(fft(window.values))
    fundamental = spectrum[1] # 50Hz component
    harmonics = np.sqrt(np.sum(spectrum[2:10]**2)) # Sum of 2nd through 9th harmonics
    return (harmonics / fundamental) * 100 if fundamental > 0 else 0

def run_batch_analysis(master_file):
    df_master = pd.read_csv(master_file)
    
    # Feature Engineering
    df_master['variance'] = df_master.groupby('sim_id')['ib'].transform(lambda x: x.rolling(window=20).var())
    df_master['p2p'] = df_master.groupby('sim_id')['ib'].transform(lambda x: x.rolling(window=20).max() - x.rolling(window=20).min())
    df_master = df_master.dropna()
    
    results = []
    sim_groups = df_master.groupby('sim_id')

    print(f"--- BATCH AUDIT: {len(sim_groups)} SIMULATIONS ---")
    
    for sim_id, data in sim_groups:
        feature_names = ['ib', 'variance', 'p2p']
        feat_scaled = scaler.transform(data[feature_names])
        preds = clf.predict(feat_scaled)
        
        # FIX: Ensure we only trip AFTER the fault starts (t >= 0.1)
        # Standard: Class 1 | HIF: Class 2
        trip_indices = np.where((data['time'] >= 0.1) & ((preds == 1) | (preds == 2)))[0]
        
        if len(trip_indices) > 0:
            trip_time = data.iloc[trip_indices[0]]['time']
            detection_delay = (trip_time - 0.1) * 1000 # Corrected timing in ms
            
            # Physics Audit: THD
            thd_val = calculate_thd(data['ib'])
            results.append({
                'sim_id': sim_id, 
                'status': 'TRIP', 
                'delay_ms': detection_delay, 
                'thd': thd_val,
                'type': data.iloc[0]['label']
            })
        else:
            results.append({'sim_id': sim_id, 'status': 'MISSED', 'delay_ms': np.nan, 'thd': 0, 'type': data.iloc[0]['label']})

    report = pd.DataFrame(results)
    
    print(f"\n--- REFINED PERFORMANCE SUMMARY ---")
    print(f"Avg Detection Delay: {report['delay_ms'].mean():.2f} ms")
    print(f"Avg THD (Standard Fault): {report[report['type'] == 'Standard']['thd'].mean():.2f}%")
    print(f"Avg THD (HIF Arcing): {report[report['type'] == 'HIF']['thd'].mean():.2f}%")
    print("----------------------------------")
    
    report.to_csv('batch_validation_results.csv', index=False)
    return report

if __name__ == "__main__":
    run_batch_analysis('Master_100_Sim_Results.csv')