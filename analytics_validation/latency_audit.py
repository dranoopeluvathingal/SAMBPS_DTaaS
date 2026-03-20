"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Analytics Validation
"""

import numpy as np

def analyze_coordination_stability(latency_ms):
    # Critical Clearing Time for a microgrid (Total system limit)
    T_critical = 100.0  # ms
    T_local_detect = 10.2 # From your hybrid_relay result
    T_breaker = 50.0 # Standard vacuum circuit breaker
    T_logic = 2.0  # CPU processing time
    
    T_total = T_local_detect + latency_ms + T_logic + T_breaker
    
    margin = T_critical - T_total
    
    status = "STABLE" if margin > 20 else "MARGINAL" if margin > 0 else "UNSTABLE"
    
    print(f"--- LATENCY AUDIT (Delay: {latency_ms}ms) ---")
    print(f"Total Clearing Time: {T_total:.1f}ms")
    print(f"Stability Margin: {margin:.1f}ms")
    print(f"System Status: {status}")
    print("------------------------------------------")

if __name__ == "__main__":
    # Test 1: Ideal Fiber Network (3ms)
    analyze_coordination_stability(3)
    
    # Test 2: Congested Wireless/Ethernet (40ms)
    analyze_coordination_stability(40)