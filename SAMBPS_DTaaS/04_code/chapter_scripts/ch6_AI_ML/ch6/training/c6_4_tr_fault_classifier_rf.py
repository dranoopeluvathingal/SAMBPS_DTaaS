"""
Description: Random Forest Classifier for IBR Fault Identification
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Machine Learning Training
"""

import os
import numpy as np
import pandas as pd
import pywt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt

# 1. LOCK AESTHETICS
plt.style.use('./thesis.mplstyle')

def prepare_training_features(csv_filename):
    data_path = f'Z_Final_Thesis_data/ch6_AI_ML/{csv_filename}'
    df = pd.read_csv(data_path)
    
    # Extract signals and labels
    # 1 = Fault (t >= 6.0), 0 = Normal (t < 6.0)
    t = df['time_s'].values
    labels = (t >= 6.0).astype(int)
    
    features = []
    for i in range(len(df)):
        # Sliding Window Feature Extraction (using Phase B)
        # In a real run, we take a 2ms buffer leading to index i
        window = df['Ib_pu'].values[max(0, i-20):i+1]
        if len(window) < 5: # Skip early samples
            features.append([0, 0])
            continue
            
        # Extract DWT Features (Energy and Max Detail)
        _, d1 = pywt.dwt(window.copy(), 'db4')
        energy = np.sum(np.square(d1))
        max_val = np.max(np.abs(d1))
        features.append([energy, max_val])
        
    return np.array(features), labels

def train_and_evaluate():
    # --- ROUTING ---
    output_dir = 'Z_Final_Thesis_figures/ch6_Z_Final_Thesis_scripts/'
    os.makedirs(output_dir, exist_ok=True)

    print("🛰️  Preparing Empire Data...")
    X, y = prepare_training_features('fault_data_full.csv')
    
    # Split: 70% Train, 30% Test
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

    # 2. RANDOM FOREST CORE
    print("🧠 Training Random Forest Classifier...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
    clf.fit(X_train, y_train)

    # 3. METRICS & VALIDATION
    y_pred = clf.predict(X_test)
    report = classification_report(y_test, y_pred)
    print("\n--- EMPIRE CLASSIFIER PERFORMANCE ---")
    print(report)

    # Feature Importance (The "Why" for your Thesis)
    importances = clf.feature_importances_
    
    # Generate Importance Plot
    plt.figure(figsize=(8, 5))
    plt.bar(['Wavelet Energy', 'Peak Detail'], importances, color=['blue', 'red'])
    plt.title('Feature Importance for IBR Fault Detection', fontweight='bold')
    plt.ylabel('Contribution Score')
    plt.savefig(os.path.join(output_dir, 'c6_4_plt_rf_feature_importance.pdf'))
    print(f"✅ Training Complete. Importance Plot saved.")

if __name__ == "__main__":
    train_and_evaluate()