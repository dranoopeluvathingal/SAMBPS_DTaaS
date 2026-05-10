import numpy as np
import pandas as pd
import time

def evaluate_21lb(R_fault, X_fault, rREF=5.0, angFOR=30.0, angREV=-30.0):
    """Core logic: Returns 'BLOCK' if inside load region, else 'TRIP'"""
    z_angle = np.degrees(np.arctan2(X_fault, R_fault))
    if abs(R_fault) > rREF and (angREV <= z_angle <= angFOR):
        return "BLOCK"
    return "TRIP"

print("🔥 Igniting 100-Simulation Batch Run...")
start_time = time.time()

results = []

# The Master Loop: Running 100 randomized fault scenarios
for i in range(1, 101):
    # Generating random edge-case faults
    R_test = np.random.uniform(2, 20)  # Sweeping Resistance from 2 to 20 Ohms
    X_test = np.random.uniform(0.5, 15) # Sweeping Reactance from 0.5 to 15 Ohms
    
    # Evaluate the logic
    decision = evaluate_21lb(R_test, X_test)
    
    # Log the result
    results.append({
        'Simulation_ID': i,
        'R_Ohms': round(R_test, 2),
        'X_Ohms': round(X_test, 2),
        'Relay_Action': decision
    })

# Save everything to a single Master File
df_results = pd.DataFrame(results)
df_results.to_csv('Master_100_Sim_Results.csv', index=False)

print(f"✅ 100 Simulations completed in {round(time.time() - start_time, 4)} seconds.")
print("Results saved to 'Master_100_Sim_Results.csv'")