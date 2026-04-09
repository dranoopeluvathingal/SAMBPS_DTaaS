"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Analytics Validation
"""

# Save as: compare_results.py
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('Master_100_Sim_Results.csv')
df['res'] = df.groupby('sim_id')['ib'].transform(lambda x: x - x.rolling(window=20).mean())

plt.figure(figsize=(10, 5))
plt.subplot(1, 2, 1)
plt.title("Method A: Input (Raw Current)")
plt.plot(df['ib'].iloc[500:1000], color='gray') # Normal/Standard look similar

plt.subplot(1, 2, 2)
plt.title("Method B: Input (Residual Chaos)")
plt.plot(df['res'].iloc[500:1000], color='crimson') # Faults pop out here
plt.savefig('method_comparison_physics.png')
print("SUCCESS: Comparison figure generated.")