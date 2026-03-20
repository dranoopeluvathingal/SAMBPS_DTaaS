import glob
import numpy as np
import pandas as pd

def classify_region(R, X, rREF=5.0, angFOR=30.0, angREV=-30.0):
    """Determines exactly where the impedance settled."""
    angle = np.degrees(np.arctan2(X, R))
    
    # Check if in Forward Blinder
    if R > rREF and (angREV <= angle <= angFOR):
        return "Forward Load (Block)"
    # Check if in Reverse Blinder
    elif R < -rREF and (180 + angREV <= angle or angle <= -180 + angFOR):
        return "Reverse Load (Block)"
    # Otherwise, it's a Trip Zone (Fault)
    else:
        return "Fault Zone (Trip)"

print("📊 Crunching data for Comparative Summary...")

# 1. Discover all cases
files = sorted(glob.glob('Relay_Data_Case_*.xlsx'))
summary_data = []

# 2. Iterate and Extract Metrics
for file in files:
    df = pd.read_excel(file)
    
    # Get Final Coordinates
    r_final = df['R_Ohms'].iloc[-1]
    x_final = df['X_Ohms'].iloc[-1]
    z_mag = np.sqrt(r_final**2 + x_final**2)
    z_ang = np.degrees(np.arctan2(x_final, r_final))
    
    # Determine Logic Outcome
    outcome = classify_region(r_final, x_final)
    
    summary_data.append({
        'Test_Case': file.replace('.xlsx', ''),
        'Final_R_Ohm': round(r_final, 2),
        'Final_X_Ohm': round(x_final, 2),
        'Z_Magnitude': round(z_mag, 2),
        'Z_Angle_Deg': round(z_ang, 2),
        'Relay_Decision': outcome
    })

# 3. Export to CSV
summary_df = pd.DataFrame(summary_data)
summary_df.to_csv('Comparative_Summary.csv', index=False)

print("\n" + "="*50)
print(summary_df.to_string(index=False))
print("="*50)
print("\n✔️ Comparative_Summary.csv has been forged.")