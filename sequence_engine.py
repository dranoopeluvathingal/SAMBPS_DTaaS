import numpy as np
import pandas as pd
import sys

# --- ENVIRONMENT CHECK ---
if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    print("WARNING: Not running in a Virtual Environment. Please run 'source phd_env/bin/activate'")

def analyze_relay_health(df_seq):
    """
    Senior Scientist Audit: Detects IBR-induced Relay Blindness.
    """
    print("\n--- RELAY PERFORMANCE AUDIT ---")
    for index, row in df_seq.iterrows():
        # Check during fault period (t > 0.1)
        if row['time'] > 0.11:
            i1 = row['I1_mag']
            i2 = row['I2_mag']
            
            status = "HEALTHY"
            if i1 < 1.3 and i2 < 0.1:
                status = "!!! RELAY BLIND !!! (IBR Current Limiting & Neg. Seq. Suppression)"
            
            print(f"Time: {row['time']:.3f} | I1: {i1:.2f} | I2: {i2:.2f} | Status: {status}")
            break # Just show the first fault sample for brevity

# (Insert your existing calculate_sequence_components function here)

def calculate_sequence_components(time, ia, ib, ic, freq=50):
    """
    Performs sliding window DFT and Fortescue Transformation.
    """
    dt = time[1] - time[0]
    samples_per_cycle = int(1 / (freq * dt))
    
    # Fortescue Matrix (A)
    alpha = np.exp(1j * 2 * np.pi / 3)
    A = (1/3) * np.array([
        [1, 1, 1],
        [1, alpha, alpha**2],
        [1, alpha**2, alpha]
    ])
    
    results = []
    
    # Sliding window for phasor extraction
    for i in range(samples_per_cycle, len(time)):
        # Extract one cycle of data
        window_a = ia[i-samples_per_cycle:i]
        window_b = ib[i-samples_per_cycle:i]
        window_c = ic[i-samples_per_cycle:i]
        
        # Fundamental Frequency Phasors (DFT)
        t_window = np.arange(samples_per_cycle) * dt
        phasor_a = (2/samples_per_cycle) * np.sum(window_a * np.exp(-1j * 2 * np.pi * freq * t_window))
        phasor_b = (2/samples_per_cycle) * np.sum(window_b * np.exp(-1j * 2 * np.pi * freq * t_window))
        phasor_c = (2/samples_per_cycle) * np.sum(window_c * np.exp(-1j * 2 * np.pi * freq * t_window))
        
        # Transformation to Sequence Components [I0, I1, I2]
        phasors = np.array([phasor_a, phasor_b, phasor_c])
        seq_components = A.dot(phasors)
        
        results.append({
            'time': time[i],
            'I0_mag': np.abs(seq_components[0]),
            'I1_mag': np.abs(seq_components[1]),
            'I2_mag': np.abs(seq_components[2])
        })
    
    return pd.DataFrame(results)

# --- EMPIRE BUILDER EXECUTION ---
# data = pd.read_csv('pscad_fault_data.csv')
# df_seq = calculate_sequence_components(data['time'], data['ia'], data['ib'], data['ic'])
# print(df_seq.head())

# --- EMPIRE BUILDER EXECUTION ---
# 1. Load the generated sample data
data = pd.read_csv('pscad_fault_data.csv')

# 2. Process the data
df_seq = calculate_sequence_components(data['time'], data['ia'], data['ib'], data['ic'])

# 3. Filter for the fault period (t > 0.1s) to see the result
print("--- SEQUENCE COMPONENT ANALYSIS (DURING FAULT) ---")
print(df_seq[df_seq['time'] > 0.105].head(10))

import matplotlib.pyplot as plt

plt.figure(figsize=(10,6))
plt.plot(df_seq['time'], df_seq['I1_mag'], label='Positive Sequence (I1)')
plt.plot(df_seq['time'], df_seq['I2_mag'], label='Negative Sequence (I2)', linestyle='--')
plt.axvline(x=0.1, color='r', linestyle=':', label='Fault Initiation')
plt.title('IBR Fault Signature: Sequence Component Magnitudes')
plt.xlabel('Time (s)')
plt.ylabel('Magnitude (p.u.)')
plt.legend()
plt.grid(True)
plt.show()

# THE CRITICAL LINE FOR VPS:
plt.savefig('sequence_analysis_plot.png') 
print("SUCCESS: Plot saved as /root/phd_thesis/sequence_analysis_plot.png")