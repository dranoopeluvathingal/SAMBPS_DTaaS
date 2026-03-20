import numpy as np

class LoadBlinder21LB:
    def __init__(self, r_reach, angle_fwd, angle_rev):
        """
        Initialize the ANSI 21LB parameters.
        r_reach: Resistive reach of the blinder (Ohms)
        angle_fwd: Forward load angle boundary (degrees)
        angle_rev: Reverse load angle boundary (degrees)
        """
        self.r_reach = r_reach
        self.angle_fwd = angle_fwd
        self.angle_rev = angle_rev
        
    def calculate_impedance(self, v_mag, v_ang, i_mag, i_ang):
        """ Calculate complex apparent impedance. """
        v_phasor = v_mag * np.exp(1j * np.radians(v_ang))
        i_phasor = i_mag * np.exp(1j * np.radians(i_ang))
        return v_phasor / i_phasor

    def check_blocking(self, z_app):
        """ 
        Evaluate if Z_app falls within the load blinder region.
        Returns True if relay should be BLOCKED.
        """
        r_app = z_app.real
        x_app = z_app.imag
        z_angle = np.degrees(np.angle(z_app))

        # Check resistive reach
        if r_app > self.r_reach:
            # Check angle boundaries (load region)
            if self.angle_rev <= z_angle <= self.angle_fwd:
                return True # BLOCKED: It's a heavy load, not a fault
        return False # TRIP ALLOWED: It's outside the load region

if __name__ == "__main__":
    print("=== ANSI 21LB Load Blinder Initialization ===")
    
    # 1. Define Blinder Settings (Requirement 444894 limits)
    blinder = LoadBlinder21LB(r_reach=15.0, angle_fwd=30.0, angle_rev=-30.0)
    
    # 2. Inject Test Phasors (Heavy Load Scenario)
    V_mag, V_ang = 63500, 0     # 63.5 kV, 0 degrees
    I_mag, I_ang = 2500, -15    # 2500 A, lagging 15 degrees
    
    Z_calc = blinder.calculate_impedance(V_mag, V_ang, I_mag, I_ang)
    is_blocked = blinder.check_blocking(Z_calc)
    
    print(f"Calculated Z_app: {Z_calc.real:.2f} + {Z_calc.imag:.2f}j Ohms")
    print(f"Impedance Angle:  {np.degrees(np.angle(Z_calc)):.2f}°")
    print(f"Relay Status:     {'BLOCKED (Load Detected)' if is_blocked else 'TRIP ALLOWED (Fault Detected)'}")