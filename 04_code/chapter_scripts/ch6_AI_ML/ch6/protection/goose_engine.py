"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Core Engines
"""

import pandas as pd
import numpy as np

def simulate_goose_coordination(local_data, neighbor_data):
    # Logic: If both see V_dip AND local I > 1.1, force a permissive trip.
    
    # 1. Local Relay Perspective (The 1.13 p.u. case)
    local_v_dip = local_data['V1_mag'] < 0.9
    local_i_high = local_data['I1_mag'] > 1.1 # Reduced threshold due to context
    
    # 2. Neighbor Relay Perspective (Directional Check)
    # If the neighbor sees NO fault current, the fault is between them.
    neighbor_healthy = neighbor_data['I1_mag'] < 1.05 
    
    # 3. GOOSE PERMISSIVE SIGNAL
    permissive_signal = local_v_dip and neighbor_healthy
    
    # 4. FINAL HYBRID DECISION
    if local_i_high and permissive_signal:
        return "TRIP (GOOSE PERMISSIVE)"
    else:
        return "HOLD"

# --- TEST CASE: The 'Blind' 1.13 p.u. Fault ---
local_state = {'time': 0.12, 'V1_mag': 0.4, 'I1_mag': 1.13}
neighbor_state = {'time': 0.12, 'V1_mag': 0.4, 'I1_mag': 0.05} # Neighbor sees no current

decision = simulate_goose_coordination(local_state, neighbor_state)
print(f"--- CHAPTER 4 VALIDATION ---")
print(f"Local Logic Result: {decision}")