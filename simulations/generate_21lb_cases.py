import numpy as np
import pandas as pd

def write_case(filename, t, R, X, settings):
    """Replicates your MATLAB write_case to output Excel files."""
    # Storing settings as metadata in the first few rows isn't standard in a clean CSV/Excel,
    # so we'll construct a clean timeseries DataFrame. 
    df = pd.DataFrame({'Time_s': t, 'R_Ohms': R, 'X_Ohms': X})
    df.to_excel(filename, index=False)
    print(f"✔️ Forged: {filename}")

# ---------------------------------------------------------
# EMPIRE BUILDER: ANSI 21LB ULTIMATE TEST MATRIX
# Generates 6 High-Resolution (1ms) Edge-Case Scenarios
# ---------------------------------------------------------

t = np.arange(0, 5.001, 0.001) # 1ms resolution, 5-second simulation
settings = [5, 30, -30, 0.001] # [rREF, angFOR, angREV, cycleTime]

print("Forging Edge Cases...\n")

# =========================================================
# CASE 1: Forward Slow Load Encroachment -> Sudden Fault
# =========================================================
R1, X1 = np.zeros_like(t), np.zeros_like(t)
mask1 = t <= 2
R1[mask1] = np.linspace(50, 4, np.sum(mask1))
X1[mask1] = np.linspace(5, 1, np.sum(mask1))
R1[~mask1] = 2
X1[~mask1] = 15
write_case('Relay_Data_Case_1.xlsx', t, R1, X1, settings)

# =========================================================
# CASE 2: Reverse Load Encroachment -> Sudden Fault
# =========================================================
R2, X2 = np.zeros_like(t), np.zeros_like(t)
mask2 = t <= 2
R2[mask2] = np.linspace(-50, -4, np.sum(mask2))
X2[mask2] = np.linspace(-5, -1, np.sum(mask2))
R2[~mask2] = 2
X2[~mask2] = 15
write_case('Relay_Data_Case_2.xlsx', t, R2, X2, settings)

# =========================================================
# CASE 3: Forward Load -> Fault -> Reverse Load (Multi-Stage)
# =========================================================
R3, X3 = np.zeros_like(t), np.zeros_like(t)
mask3_fwd = t <= 1.5
mask3_flt = (t > 1.5) & (t <= 3)
mask3_rev = t > 3

R3[mask3_fwd] = np.linspace(50, 6, np.sum(mask3_fwd))
X3[mask3_fwd] = 2
R3[mask3_flt] = 1
X3[mask3_flt] = 10
R3[mask3_rev] = np.linspace(-6, -50, np.sum(mask3_rev))
X3[mask3_rev] = -2
write_case('Relay_Data_Case_3.xlsx', t, R3, X3, settings)

# =========================================================
# CASE 4: The Power Swing (Continuous gliding trajectory)
# =========================================================
R4 = np.linspace(20, -20, len(t))
X4 = 2 * np.ones_like(t)
write_case('Relay_Data_Case_4.xlsx', t, R4, X4, settings)

# =========================================================
# CASE 5: The Boundary Slider (High Resistance Fault Edge)
# =========================================================
R5 = 6 * np.ones_like(t)
X5 = np.linspace(10, 2, len(t))
write_case('Relay_Data_Case_5.xlsx', t, R5, X5, settings)

# =========================================================
# CASE 6: The "Chatter" Oscillation (Microgrid Noise on Boundary)
# =========================================================
# R oscillates between 4.9 (Trip Zone) and 5.1 (Block Zone) at 10Hz
R6 = 5 + 0.2 * np.sin(2 * np.pi * 10 * t)
X6 = 1.5 * np.ones_like(t)
write_case('Relay_Data_Case_6.xlsx', t, R6, X6, settings)

print("\n✅ All 6 Test Cases Generated Successfully!")