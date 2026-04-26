"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Visualization
"""

import numpy as np
import matplotlib.pyplot as plt

def plot_adaptive_characteristic():
    # Standards: IEEE Moderately Inverse
    k, alpha, L = 0.0515, 0.02, 0.114
    TD = 0.5
    
    # Range of currents (p.u.)
    I = np.linspace(1.06, 5.0, 500)
    
    # Different Pickup Scenarios
    pickups = {
        'Legacy (V=1.0)': 1.5,
        'Proposed (V=0.7)': 1.3,
        'Proposed (V=0.4)': 1.05
    }
    
    plt.figure(figsize=(10, 7))
    colors = ['gray', 'blue', 'red']
    
    for (label, I_set), color in zip(pickups.items(), colors):
        # Calculate trip time
        # Filter I to only those above pickup to avoid negative/inf times
        I_valid = I[I > I_set]
        t_trip = TD * (k / ((I_valid / I_set)**alpha - 1) + L)
        
        plt.plot(I_valid, t_trip, label=label, color=color, linewidth=2, 
                 linestyle='--' if 'Legacy' in label else '-')

    # Mark the IBR Fault Current (1.2 p.u.)
    plt.axvline(x=1.2, color='black', linestyle=':', label='IBR Fault Limit (1.2 p.u.)')
    plt.text(1.22, 10, 'Relay Blindness Region', color='black', fontweight='bold')

    plt.yscale('log')
    plt.grid(True, which="both", ls="-", alpha=0.5)
    plt.title('Adaptive Operating Characteristics: Trip Time vs. Current', fontsize=14)
    plt.xlabel('Current (p.u.)')
    plt.ylabel('Time to Trip (s)')
    plt.legend()
    plt.ylim(0.1, 100)
    
    plt.savefig('adaptive_curves.png', dpi=300)
    print("SUCCESS: adaptive_curves.png generated. Observe how the Red line catches the 1.2 p.u. fault.")

if __name__ == "__main__":
    plot_adaptive_characteristic()