import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def plot_dual_blinder(s, Z_pts, filename):
    """
    EMPIRE BUILDER: ANSI 21LB VISUALIZATION ENGINE (Batch Edition)
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
    print(f"  ✔️ Saved: {out_img}")
    
    # CRITICAL: Close the figure to free up RAM during batch processing
    plt.close(fig) 

if __name__ == "__main__":
    print("\n=== DR. ANOOP - EMPIRE BUILDER BATCH VISUALIZER ===")
    
    # --- 0. DYNAMIC FILE DISCOVERY ---
    files = sorted(glob.glob('Relay_Data_Case_*.xlsx'))
    
    if not files:
        print("❌ No Excel cases found. Run the generator script first!")
    else:
        print(f"🔥 Found {len(files)} test cases. Igniting Batch Processing...\n")
        
        # --- 1. HARDCODE SETTINGS (Define once to save CPU cycles) ---
        rREF_val = 5.0
        angFOR_val = 30.0
        angREV_val = -30.0
        
        s_vis = {
            'R_fw': rREF_val, 
            'R_rv': rREF_val, 
            'Ang_max': angFOR_val, 
            'Ang_min': angREV_val
        }
        
        print(f"✔️ Workspace Initialized. R={rREF_val}, Ang_max={angFOR_val}, Ang_min={angREV_val}\n")
        
        # --- 2. THE MASTER LOOP ---
        for target_file in files:
            print(f"📂 Processing: {target_file}")
            try:
                # Import Data
                df = pd.read_excel(target_file)
                time_vec = df['Time_s'].values
                R_vals = df['R_Ohms'].values
                X_vals = df['X_Ohms'].values
                
                # Create Complex Vectors
                Z_complex = R_vals + 1j * X_vals
                
                # Visual Verification
                plot_dual_blinder(s_vis, Z_complex, target_file)
                
            except Exception as e:
                print(f"  ❌ Error on {target_file}: {e}")
                
        print("\n✅ Batch Visualization Complete! All high-res plots are waiting in your sidebar.")