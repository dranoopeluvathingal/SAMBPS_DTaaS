"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Core Engines
"""

import pandas as pd
import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import ConfusionMatrixDisplay
import matplotlib.pyplot as plt

def train_fault_classifier(data_file):
    df = pd.read_csv(data_file)
    
    # Feature Engineering
    df['variance'] = df['ib'].rolling(window=20).var()
    df['p2p'] = df['ib'].rolling(window=20).max() - df['ib'].rolling(window=20).min()
    df = df.dropna()

    # Define Features and Target
    X = df[['ib', 'variance', 'p2p']]
    y = np.where(df['time'] > 0.1, 1, 0)

    # Scale and Train
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    clf = MLPClassifier(hidden_layer_sizes=(10, 5), max_iter=1000, random_state=42)
    clf.fit(X_scaled, y)
    
    # RETURN X_scaled and y so the plotting code can use them
    return clf, scaler, X_scaled, y

import joblib

if __name__ == "__main__":
    # 1. Execute Training
    model, scaler, X_train, y_train = train_fault_classifier('pscad_fault_data.csv')
    
    # 2. Generate the Confusion Matrix (The "Evidence")
    plt.figure(figsize=(8, 6))
    ConfusionMatrixDisplay.from_estimator(
        model, X_train, y_train, 
        display_labels=['Normal', 'IBR Fault'],
        cmap='Blues'
    )
    plt.title("Relay AI Decision Matrix (IBR Fault vs Normal)")
    plt.savefig('ai_confusion_matrix.png')
    
    print("\n--- EMPIRE BUILDER AI AUDIT ---")
    print(f"Accuracy: {model.score(X_train, y_train) * 100:.2f}%")
    print("SUCCESS: ai_confusion_matrix.png generated.")
    print("-------------------------------\n")

# 2. THE EXPORT (This creates the missing files)
    joblib.dump(model, 'ibr_fault_classifier.pkl')
    joblib.dump(scaler, 'feature_scaler.pkl')
    
    print("\n--- EMPIRE BUILDER AI EXPORT ---")
    print("SUCCESS: ibr_fault_classifier.pkl and feature_scaler.pkl created.")
    print("---------------------------------\n")

# Save the model and the scaler to disk
joblib.dump(model, 'ibr_fault_classifier.pkl')
joblib.dump(scaler, 'feature_scaler.pkl')
print("EXPERT STATUS: Model and Scaler exported as .pkl files.")