"""
Description: Code snippet to verify the presence and functionality of the thesis.mplstyle file for IIT Madras PhD thesis plotting standards.
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Utility/Verification
"""

import matplotlib.pyplot as plt
import os

style_name = 'thesis.mplstyle'

# 1. Check if the file exists in the directory
if os.path.exists(style_name):
    print(f"✅ Success: '{style_name}' found in the current directory.")
else:
    print(f"❌ Error: '{style_name}' NOT found. Check your /root/phd_thesis/ path.")

# 2. Test the loading
try:
    plt.style.use(style_name)
    print(f"✅ Success: Matplotlib successfully applied '{style_name}'.")
except Exception as e:
    print(f"❌ Error: Matplotlib failed to load the style. Reason: {e}")

# 3. Check for PhD-required fonts (e.g., Computer Modern or Serif)
# IIT Madras usually prefers serif fonts for thesis plots.
print(f"Current Font Family: {plt.rcParams['font.family']}")
