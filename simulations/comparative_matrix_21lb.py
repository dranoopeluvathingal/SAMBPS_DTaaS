import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

print("🔥 Assembling the 6-Panel Comparative Matrix...")

# 1. Discover the files
files = sorted(glob.glob('Relay_Data_Case_*.xlsx'))
if len(files) == 0:
    print("❌ No Excel cases found. Run the generator script first!")
    exit()

# 2. Hardcode Settings (Requirement 444894)
rREF, angFOR, angREV = 5.0, 30.0, -30.0

# 3. Initialize the 2x3 Figure Engine
fig, axes = plt.subplots(2, 3, figsize=(18, 10), facecolor='w')
fig.suptitle(r'$\bf{ANSI\ 21LB:\ 6-Case\ Comparative\ Validation\ Matrix}$', fontsize=20, y=1.02)

# Map your specific edge cases to titles
case_names = [
    "Case 1: Forward Load -> Fault",
    "Case 2: Reverse Load -> Fault",
    "Case 3: Multi-Stage Transient",
    "Case 4: Smooth Power Swing",
    "Case 5: Boundary Slider",
    "Case 6: Boundary Chatter (Noise)"
]

# 4. The Master Loop (Stitching 6 files into 6 panels)
for i, (ax, file) in enumerate(zip(axes.flatten(), files)):
    # Import Data
    df = pd.read_excel(file)
    R_vals, X_vals = df['R_Ohms'].values, df['X_Ohms'].values
    
    # Draw Origin Axes
    ax.axhline(0, color='black', linewidth=1)
    ax.axvline(0, color='black', linewidth=1)
    
    # Draw Blinder Boundaries
    y_vals = np.linspace(-60, 60, 200)
    x_fwd = rREF + y_vals * np.tan(np.radians(angFOR))
    x_rev = -rREF + y_vals * np.tan(np.radians(angREV))
    
    ax.plot(x_fwd, y_vals, 'r--', linewidth=1.5)
    ax.plot(x_rev, y_vals, 'b--', linewidth=1.5)
    ax.fill_betweenx(y_vals, x_rev, x_fwd, color='gray', alpha=0.15)
    
    # Plot Trajectory
    ax.plot(R_vals, X_vals, 'k-', linewidth=2, label='Z Trajectory')
    ax.plot(R_vals[0], X_vals[0], 'go', markersize=6, label='Start Point')
    ax.plot(R_vals[-1], X_vals[-1], 'ro', markersize=6, label='End Point')
    
    # Formatting (Locking the axes to -60/60 so the comparison is 1:1)
    title = case_names[i] if i < len(case_names) else f"Case {i+1}"
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.set_xlabel('Resistance R ($\Omega$)')
    ax.set_ylabel('Reactance X ($\Omega$)')
    ax.set_xlim(-60, 60)
    ax.set_ylim(-20, 20)
    ax.grid(True, linestyle=':', alpha=0.7)
    
    # Only put the legend in the first box to avoid clutter
    if i == 0:
        ax.legend(loc='upper right', fontsize=9)

plt.tight_layout()

# 5. Save the Master Matrix
out_img = 'Chapter4_Comparative_Matrix.png'
plt.savefig(out_img, dpi=300, bbox_inches='tight')
print(f"✔️ Master Comparative Matrix successfully saved as: {out_img}")
plt.close(fig)