# Note
# "What does the code do?": Trains a Support Vector Machine (SVM) to classify microgrid fault types using extracted reduced-order parameters.
# 'Current State': Machine Learning Pipeline - Baseline Classification.
# 'Thesis Logic': Proving that mathematically standardized features (K, tau_d, f_tr) can reliably separate fault classes in a high-dimensional space.
# 'Goal': Build a robust, scaled SVM pipeline that outputs a formal thesis-ready confusion matrix PDF.

import os
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay

# --------------------------------------------------------
# 1. LOCK AESTHETICS
# --------------------------------------------------------
plt.style.use('./thesis.mplstyle')

def execute_svm_classification(feature_csv_filename):
    # Directories
    input_dir = 'Z_Final_Thesis_data/ch6_reduced_order_model'
    output_dir = 'Z_Final_Thesis_figures/ch6_Z_Final_Thesis_scripts/'
    os.makedirs(output_dir, exist_ok=True)
    
    # Load Data
    input_path = os.path.join(input_dir, feature_csv_filename)
    print(f"Loading feature dataset from {input_path}...")
    
    # Load the CSV containing the multiple fault extractions
    df = pd.read_csv(input_path)
    
    # Separate Features (X) and Target (y)
    # * ADJUST 'fault_type' to match the actual label column name in your CSV
    X = df.drop(columns=['fault_type', 'input_csv']) 
    y = df['fault_type']
    
    # Train/Test Split (80% Training, 20% Testing)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # --------------------------------------------------------
    # 2. FEATURE SCALING (CRITICAL FOR SVM)
    # --------------------------------------------------------
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # --------------------------------------------------------
    # 3. TRAIN SUPPORT VECTOR MACHINE
    # --------------------------------------------------------
    # RBF kernel handles non-linear boundaries caused by complex inverter logic
    svm_model = SVC(kernel='rbf', C=1.0, gamma='scale', random_state=42)
    svm_model.fit(X_train_scaled, y_train)
    
    # Evaluate
    y_pred = svm_model.predict(X_test_scaled)
    print("\n--- SVM Classification Report ---")
    print(classification_report(y_test, y_pred))
    
    # --------------------------------------------------------
    # 4. PLOT CONFUSION MATRIX
    # --------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    cm = confusion_matrix(y_test, y_pred, labels=svm_model.classes_)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=svm_model.classes_)
    
    # Use 'Blues' colormap for academic aesthetic
    disp.plot(cmap='Blues', ax=ax, colorbar=True)
    
    plt.title('SVM Fault Classification Confusion Matrix')
    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')
    plt.tight_layout()
    
    # Export as Vector PDF
    output_path = os.path.join(output_dir, 'c6_4_plt_svm_confusion_matrix.pdf')
    plt.savefig(output_path, format='pdf', bbox_inches='tight')
    plt.show()
    
    print(f"✅ Success: SVM Model Trained. Confusion Matrix PDF saved to {output_path}")

if __name__ == "__main__":
    # Ensure this points to the CSV containing ALL your extracted fault scenarios
    execute_svm_classification('reduced_order_model_summary.csv')