import numpy as np
import matplotlib.pyplot as plt

# 1. Blinder Parameters (Requirement 444894)
r_reach = 15.0
angle_fwd = 30.0
angle_rev = -30.0

# 2. Calculated Apparent Impedance (from previous run)
V_mag, V_ang = 63500, 0
I_mag, I_ang = 2500, -15
z_app = (V_mag * np.exp(1j * np.radians(V_ang))) / (I_mag * np.exp(1j * np.radians(I_ang)))

# 3. Setup the R-X Plane Plot
plt.figure(figsize=(8, 8))
plt.axhline(0, color='black', linewidth=1.5) # R-axis
plt.axvline(0, color='black', linewidth=1.5) # X-axis

# 4. Generate Blinder Lines
y_vals = np.linspace(-30, 30, 100)
x_fwd = r_reach + y_vals * np.tan(np.radians(angle_fwd))
x_rev = r_reach + y_vals * np.tan(np.radians(angle_rev))

plt.plot(x_fwd, y_vals, 'r--', label=f'Forward Load Angle ({angle_fwd}°)')
plt.plot(x_rev, y_vals, 'b--', label=f'Reverse Load Angle ({angle_rev}°)')

# Shade the Load Region (The "Block" Zone)
plt.fill_betweenx(y_vals, x_rev, x_fwd, color='gray', alpha=0.2, label='Load Blinder Region')

# 5. Plot the Z_app Point
plt.plot(z_app.real, z_app.imag, 'go', markersize=10, label=f'Z_app ({z_app.real:.1f} + {z_app.imag:.1f}j $\Omega$)')

# 6. Formatting
plt.title('ANSI 21LB Load Blinder Characteristic (R-X Plane)', fontsize=14, fontweight='bold')
plt.xlabel('Resistance R ($\Omega$)', fontsize=12)
plt.ylabel('Reactance X ($\Omega$)', fontsize=12)
plt.xlim(-10, 50)
plt.ylim(-30, 30)
plt.grid(True, linestyle=':', alpha=0.7)
plt.legend(loc='upper right')

# 7. Save the Output
plt.savefig('rx_diagram.png', dpi=300, bbox_inches='tight')
print("Plot successfully saved as 'rx_diagram.png'.")