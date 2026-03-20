import numpy as np
import pandas as pd
from sequence_engine import calculate_sequence_components

def run_adaptive_relay_logic(data_file):
    # 1. Load data and extract sequences
    df = pd.read_csv(data_file)
    # Note: In a real case, you'd also need Voltage data. 
    # For this simulation, we'll assume V drops to 0.4 during the fault.
    df['V1_mag'] = np.where(df['time'] < 0.1, 1.0, 0.4) 
    
    df_seq = calculate_sequence_components(df['time'].values, df['ia'].values, df['ib'].values, df['ic'].values)
    df_seq['V1_mag'] = np.where(df_seq['time'] < 0.1, 1.0, 0.4)

    # 2. Adaptive Parameters
    I_nom = 1.5   # Legacy fixed setting
    I_min = 1.05  # Proposed sensitive limit
    V_th = 0.9    # Threshold for adaptation
    V_fault = 0.2   # Expected voltage during metallic fault (Added this)

    results = []
    for _, row in df_seq.iterrows():
        # 1. Logic for V-dependent I_set
        v_current = row['V1_mag']
        
        if v_current >= V_th:
            I_set = I_nom
        elif v_current <= V_fault:
            I_set = I_min
        else:
            # Aggressive Slope Interpolation
            I_set = I_min + (I_nom - I_min) * ( (v_current - V_fault) / (V_th - V_fault) )
        
        # 2. Trip Logic
        legacy_trip = row['I1_mag'] > I_nom
        adaptive_trip = row['I1_mag'] > I_set
        
        results.append({
            'time': row['time'],
            'I1': row['I1_mag'],
            'I_set': I_set,
            'Legacy': legacy_trip,
            'Proposed': adaptive_trip
        })
    
    return pd.DataFrame(results)

# --- EXECUTION ---
df_results = run_adaptive_relay_logic('pscad_fault_data.csv')
print(df_results[df_results['time'] > 0.12].head(5))