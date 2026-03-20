# Physics-Informed Protection for IBR-Dominated Microgrids
**Candidate:** Dr. Anoop Eluvathingal  
**Institution:** IIT Madras  
**Role:** Senior Scientist (Power Systems Protection & AI)

# ⚡ PhD Research Engine: Physics-Informed Microgrid Protection
**Candidate:** Dr. Anoop Eluvathingal  
**Focus:** IBR-Dominated Microgrids & Method B Entropy Logic

## 🚀 Quick Start Guide
To replicate the research environment and execute the core validation suite, follow these steps:

### 1. Environment Initialization
From the root directory, execute the automated setup script. This will create the virtual environment and install all dependencies (NumPy, Pandas, Matplotlib, Seaborn, Tabulate).
```bash
chmod +x setup_empire.sh && ./setup_empire.sh
source phd_env/bin/activate


## Project Overview
This repository contains the complete simulation, analysis, and validation suite for my doctoral thesis. The research addresses the 'Sensitivity-Security Paradox' in modern microgrids by utilizing **Residual Entropy Analysis (Method B)** to decouple fault detection from signal magnitude.

## 📂 Directory Structure

### 1. `/core_engines`
Contains the primary algorithmic contributions of the thesis.
* **`method_b_entropy.py`**: The central logic implementing stochastic chaos detection in the residual domain [cite: 2026-03-01].
* **`hybrid_relay.py`**: Integrates the physics-informed AI layer with standard protective elements [cite: 2026-03-01].
* **`model_b_entropy.pkl`**: Pre-trained MLP weights validated across the 8-scenario stress matrix.

### 2. `/data_processing`
Scripts for generating high-fidelity synthetic datasets and handling raw simulation outputs.
* **`hif_data_generator.py`**: Simulates the arcing physics of High Impedance Faults [cite: 2026-03-14].
* **`fault_data.csv`**: Standardized input data used for comparative performance audits.

### 3. `/analytics_validation`
The "Scientific Audit" suite used to verify the reliability of Method B.
* **`security_audit.py`**: Validates the model against 1.5 p.u. motor starts and capacitor switching [cite: 2026-03-01].
* **`latency_audit.py`**: Confirms sub-millisecond (0.09 ms) algorithmic processing speed [cite: 2026-03-01].
* **`Master_100_Sim_Results.csv`**: The definitive record of all validation test cases.

### 4. `/visualization`
A dedicated suite for generating publication-quality (300 DPI) figures.
* **`plot_integrated_entropy.py`**: Visualizes the temporal alignment of entropy spikes and physical faults [cite: 2026-03-01].
* **`integrated_entropy_plot.png`**: The primary visual proof for the thesis conclusion.

### 5. `/presentation_delivery`
Automated tools for thesis defense and final results reporting.
* **`Anoop_Detailed_PhD_Synopsis.pptx`**: The 15-slide synopsis generated via Python-PPTX automation.
* **`generate_synopsis.py`**: Script to programmatically update and compile the defense slides.

## 🚀 Execution Instructions
1. Initialize the environment: `source phd_env/bin/activate`
2. Run the master audit: `python analytics_validation/batch_processor.py`
3. Generate thesis figures: `python visualization/plot_integrated_entropy.py`