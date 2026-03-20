"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Data Processing
"""

import numpy as np
import pandas as pd

def generate_waveform_csv(filename='fault_data.csv'):
    # Parameters
    fs = 10000  # 10 kHz sampling frequency
    f = 50      # 50 Hz system frequency
    t = np.linspace(1.97, 2.15, int(fs * (2.15 - 1.97)))
    omega = 2 * np.pi * f
    
    # Phase shifts
    phi_a = 0
    phi_b = -2 * np.pi / 3
    phi_c = 2 * np.pi / 3
    
    v_a, v_b, v_c = [], [], []
    
    for ti in t:
        # State 1: Normal Operation (Pre-fault)
        if ti < 2.0:
            mag = 9.0
            va = mag * np.sin(omega * ti + phi_a)
            vb = mag * np.sin(omega * ti + phi_b)
            vc = mag * np.sin(omega * ti + phi_c)
            
        # State 2: SLG Fault on Phase A
        elif 2.0 <= ti < 2.1:
            va = 0.9 * np.sin(omega * ti + phi_a) # 90% Voltage Drop
            vb = 9.0 * np.sin(omega * ti + phi_b)
            vc = 9.0 * np.sin(omega * ti + phi_c)
            
        # State 3: Post-Fault / Transition
        else:
            mag_post = 4.0
            va = mag_post * np.sin(omega * ti + phi_a)
            vb = mag_post * np.sin(omega * ti + phi_b)
            vc = mag_post * np.sin(omega * ti + phi_c)
            
        v_a.append(va)
        v_b.append(vb)
        v_c.append(vc)

    # Create DataFrame and Save
    df = pd.DataFrame({
        'time': t,
        'Va_kV': v_a,
        'Vb_kV': v_b,
        'Vc_kV': v_c
    })
    
    df.to_csv(filename, index=False)
    print(f"SUCCESS: {filename} generated with {len(df)} data points.")

if __name__ == "__main__":
    generate_waveform_csv()