import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 1. Load the Matrix
df = pd.read_csv('Master_100_Sim_Results.csv')

# 2. Setup the R-X Plane
plt.figure(figsize=(10, 10), facecolor='w')
plt.axhline(0, color='black', linewidth=1.2)
plt.axvline(0, color='black', linewidth=1.2)

# 3. Draw the Blinder Boundaries (Requirement 444894)
rREF, angFOR, angREV = 5.0, 30.0, -30.0
y_vals = np.linspace(-20, 20, 100)
x_fwd = rREF + y_vals * np.tan(np.radians(angFOR))
x_rev = -rREF + y_vals * np.tan(np.radians(angREV))

plt.plot(x_fwd, y_vals, 'k--', linewidth=1.5, label='Load Blinder Limits')
plt.plot(x_rev, y_vals, 'k--', linewidth=1.5)
plt.fill_betweenx(y_vals, x_rev, x_fwd, color='gray', alpha=0.2, label='Load Blocked Region')

# 4. Scatter Plot the Autonomous Decisions
trips = df[df['Relay_Action'] == 'TRIP']
blocks = df[df['Relay_Action'] == 'BLOCK']

plt.scatter(trips['R_Ohms'], trips['X_Ohms'], c='green', s=50, edgecolors='k', zorder=5, label='TRIP (Valid Fault)')
plt.scatter(blocks['R_Ohms'], blocks['X_Ohms'], c='red', s=50, edgecolors='k', zorder=5, label='BLOCK (Load Swing)')

# 5. Formatting & Execution
plt.title(r'$\bf{ANSI\ 21LB:\ 100-Point\ Monte\ Carlo\ Validation}$', fontsize=14, pad=15)
plt.xlabel('Resistance R ($\Omega$)', fontsize=12)
plt.ylabel('Reactance X ($\Omega$)', fontsize=12)
plt.xlim(0, 25)
plt.ylim(0, 20)
plt.grid(True, linestyle=':', alpha=0.7)
plt.legend(loc='upper right')

# Save Output
out_img = 'Monte_Carlo_21LB.png'
plt.savefig(out_img, dpi=300, bbox_inches='tight')
print(f"✔️ Validation Scatter Plot saved as: {out_img}")