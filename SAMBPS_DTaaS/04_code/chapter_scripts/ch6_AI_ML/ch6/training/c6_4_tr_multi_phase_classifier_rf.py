"""
Description: Multi-Phase Random Forest Classifier (Phase Selection)
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Machine Learning Training (Multi-Channel)
"""

import os
import numpy as np
import pandas as pd
import pywt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns

# 1. LOCK AESTHETICS
plt.style.use('./thesis.mplstyle')

def prepare_multi_phase_features(csv_filename):
    data_path = f'Z_Final_Thesis_data/ch6_AI_ML/{csv_filename}'
    df = pd.read_csv(data_path)
    
    t = df['time_s'].values
    # TARGET: 0 = Normal, 1 = B-C Fault
    labels = (t >= 6.0).astype(int)
    
    features = []
    print("🛰️  Decomposing 3-Phase Empire Data...")
    
    # We extract Energy features for ALL THREE PHASES
    for i in range(len(df)):
        # 2ms sliding window (20 samples at 10kHz)
        idx_start = max(0, i-20)
        win_a = df['Ia_pu'].values[idx_start:i+1]
        win_b = df['Ib_pu'].values[idx_start:i+1]
        win_c = df['Ic_pu'].values[idx_start:i+1]

        if len(win_a) < 5:
            features.append([0, 0, 0]) # Zero pad early samples
            continue

        # Extract D1 Energy for each phase
        _, d1_a = pywt.dwt(win_a.copy(), 'db4')
        _, d1_b = pywt.dwt(win_b.copy(), 'db4')
        _, d1_c = pywt.dwt(win_c.copy(), 'db4')

        # Feature Vector: [Energy_A, Energy_B, Energy_C]
        features.append([np.sum(np.square(d1_a)), 
                         np.sum(np.square(d1_b)), 
                         np.sum(np.square(d1_c))])
        
    return np.array(features), labels

def train_multi_phase_model():
    output_dir = 'Z_Final_Thesis_figures/ch6_Z_Final_Thesis_scripts/'
    os.makedirs(output_dir, exist_ok=True)

    X, y = prepare_multi_phase_features('fault_data_full.csv')
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

    # 2. RANDOM FOREST (3-Input Channel)
    clf = RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42)
    clf.fit(X_train, y_train)

    # 3. EVALUATION
    y_pred = clf.predict(X_test)
    print("\n--- MULTI-PHASE CLASSIFIER PERFORMANCE ---")
    print(classification_report(y_test, y_pred, target_names=['Healthy', 'B-C Fault']))

    # Confusion Matrix Plot for Chapter 6
    cm = confusion_matrix(y_test, y_pred)
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                xticklabels=['Healthy', 'B-C Fault'], 
                yticklabels=['Healthy', 'B-C Fault'])
    plt.title('Confusion Matrix: Multi-Phase IBR Protection', fontweight='bold')
    plt.ylabel('True Label')
    plt.xlabel('Predicted Label')
    plt.savefig(os.path.join(output_dir, 'c6_4_plt_multi_phase_confusion_matrix.pdf'))
    
    return clf

if __name__ == "__main__":
    train_multi_phase_model()