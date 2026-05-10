"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Data Processing
"""

import numpy as np
import pandas as pd

def generate_master_batch(num_sims=100):
    fs, f0, t_end = 10000, 50, 0.2
    t = np.linspace(0, t_end, int(fs * t_end))
    all_data = []

    print(f"--- GENERATING {num_sims} SYNTHETIC SCENARIOS ---")
    
    for sim_id in range(num_sims):
        # Randomize parameters
        fault_type = np.random.choice(['Normal', 'Standard', 'HIF'], p=[0.2, 0.4, 0.4])
        noise_lvl = np.random.uniform(0.01, 0.05)
        
        # Base Sinusoids
        ia = 1.0 * np.sin(2 * np.pi * f0 * t) + np.random.normal(0, noise_lvl, len(t))
        ib = 1.0 * np.sin(2 * np.pi * f0 * t - 2 * np.pi/3) + np.random.normal(0, noise_lvl, len(t))
        ic = 1.0 * np.sin(2 * np.pi * f0 * t + 2 * np.pi/3) + np.random.normal(0, noise_lvl, len(t))

        if fault_type != 'Normal':
            fault_idx = np.where(t >= 0.1)[0]
            if fault_type == 'Standard':
                # Clipped IBR waveform (1.2 p.u.)
                ib[fault_idx] = 1.2 * np.sign(np.sin(2 * np.pi * f0 * t[fault_idx] - 2 * np.pi/3))
            else:
                # Arcing HIF (0.6 - 0.8 p.u.)
                mag = np.random.uniform(0.6, 0.8)
                ib[fault_idx] = mag * np.sin(2 * np.pi * f0 * t[fault_idx] - 2 * np.pi/3)
                # Add "Sputter" noise
                ib[fault_idx] += np.random.normal(0, 0.1, len(fault_idx))

        sim_df = pd.DataFrame({'sim_id': sim_id, 'time': t, 'ia': ia, 'ib': ib, 'ic': ic, 'label': fault_type})
        all_data.append(sim_df)

    master_df = pd.concat(all_data)
    master_df.to_csv('Master_100_Sim_Results.csv', index=False)
    print("SUCCESS: Master_100_Sim_Results.csv created.")

if __name__ == "__main__":
    generate_master_batch()