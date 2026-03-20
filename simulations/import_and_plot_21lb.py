import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def select_test_case():
    """Terminal-based file selector (Headless alternative to uigetfile)"""
    files = sorted(glob.glob('Relay_Data_Case_*.xlsx'))
    if not files:
        print("❌ No Excel cases found. Run the generator script first!")
        return None
    
    print("\n=== DR. ANOOP - EMPIRE BUILDER FILE SELECTOR ===")
    for i, f in enumerate(files):
        print(f"[{i+1}] {f}")
        
    try:
        choice = int(input("\n👉 Select a file number (or press Ctrl+C to cancel): ")) - 1
        if 0 <= choice < len(files):
            return files[choice]
        else:
            print("Invalid selection. Empire building paused.")
            return None
    except ValueError:
        print("Invalid input. Try typing a number next time, Doctor.")
        return None

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def plot_dual_blinder(s, Z_pts, filename):
    """
    EMPIRE BUILDER: ANSI 21LB VISUALIZATION ENGINE (Python Edition)
    Direct translation of Dr. Anoop's MATLAB graphics engine.
    """
    R_fw, R_rv = s['R_fw'], s['R_rv']
    Ang_max, Ang_min = np.radians(s['Ang_max']), np.radians(s['Ang_min'])
    
    real_Z = np.real(Z_pts)
    imag_Z = np.imag(Z_pts)

    # Dynamic limit scaling based on maximum trajectory
    limit = max([R_fw, R_rv, np.max(np.abs(real_Z))]) * 1.5
    
    r_f = np.linspace(R_fw, limit, 100)
    r_r = np.linspace(-limit, -R_rv, 100)
    
    xf_max = r_f * np.tan(Ang_max)
    xf_min = r_f * np.tan(Ang_min)
    xr_max = np.abs(r_r) * np.tan(Ang_max)
    xr_min = np.abs(r_r) * np.tan(Ang_min)

    fig, ax = plt.subplots(figsize=(10, 10), facecolor='w')
    
    # 1. Plot Blinder Zones (using polygon fill logic)
    poly_xf = np.concatenate([r_f, r_f[::-1]])
    poly_yf = np.concatenate([xf_max, xf_min[::-1]])
    ax.fill(poly_xf, poly_yf, color=(0.9, 0.9, 0.9), edgecolor='b', alpha=0.4, label='Forward Load Area')
    
    poly_xr = np.concatenate([r_r, r_r[::-1]])
    poly_yr = np.concatenate([xr_max, xr_min[::-1]])
    ax.fill(poly_xr, poly_yr, color=(0.9, 0.9, 0.9), edgecolor='r', alpha=0.4, label='Reverse Load Area')

    # 2. Plot Impedance Trajectory
    ax.plot(real_Z, imag_Z, 'k-', linewidth=1.5, label='Impedance Trajectory')
    
    # Highlight Start and End points
    ax.plot(real_Z[0], imag_Z[0], 'go', markersize=6, markerfacecolor='g', label='Start Point')
    ax.plot(real_Z[-1], imag_Z[-1], 'ro', markersize=6, markerfacecolor='r', label='End Point')
    
    # 3. Reference Symmetrical Circle
    circle = patches.Circle((0, 0), limit/2, edgecolor=(0.7, 0.7, 0.7), linestyle='--', fill=False)
    ax.add_patch(circle)

    # 4. Axis Centering & Formatting (MATLAB origin snapping)
    ax.spines['left'].set_position('zero')
    ax.spines['bottom'].set_position('zero')
    ax.spines['right'].set_color('none')
    ax.spines['top'].set_color('none')
    
    ax.set_aspect('equal', adjustable='datalim')
    ax.grid(True, linestyle=':', alpha=0.7)
    
    # Setting labels relative to the new axis positions
    ax.set_xlabel(r'Resistance (R) [$\Omega$]', loc='right')
    ax.set_ylabel(r'Reactance (X) [$\Omega$]', loc='top')
    ax.set_title(r'$\bf{ANSI\ 21LB:\ High-Resolution\ Load\ Encroachment\ Locus}$', pad=20)
    
    ax.legend(loc='upper right', bbox_to_anchor=(1.25, 1))

    # Save Output
    out_img = filename.replace('.xlsx', '_Empire_Plot.png')
    plt.savefig(out_img, dpi=300, bbox_inches='tight')
    print(f"✔️ High-Res Visual Engine Output Saved: {out_img}")

if __name__ == "__main__":
    # --- 0. DYNAMIC FILE SELECTION ---
    target_file = select_test_case()
    
    if target_file:
        print(f"\n📂 Loading Test Case: {target_file}")
        
        try:
            # --- 1. IMPORT DATA ---
            # Instead of messy MATLAB cell targeting, we read our clean Pandas DataFrame
            df = pd.read_excel(target_file)
            
            time_vec = df['Time_s'].values
            R_vals = df['R_Ohms'].values
            X_vals = df['X_Ohms'].values
            
            # --- 2. CREATE COMPLEX VECTORS ---
            Z_complex = R_vals + 1j * X_vals
            
            # --- 3. HARDCODE SETTINGS ---
            rREF_val = 5.0
            angFOR_val = 30.0
            angREV_val = -30.0
            
            # Pack the dictionary (just like your MATLAB struct 's_vis')
            s_vis = {
                'R_fw': rREF_val, 
                'R_rv': rREF_val, 
                'Ang_max': angFOR_val, 
                'Ang_min': angREV_val
            }
            
            print(f"✔️ Workspace Initialized. R={rREF_val}, Ang_max={angFOR_val}, Ang_min={angREV_val}")
            
            # --- 4. VISUAL VERIFICATION ---
            # Call the new Empire Builder visualization engine
            plot_dual_blinder(s_vis, Z_complex, target_file)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Did you leave the Excel file open somewhere? Close it and try again.")